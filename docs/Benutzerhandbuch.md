# Statik3D – Benutzerhandbuch

Statik3D ist ein Finite-Elemente-Programm für Stab-, Flächen- und
Volumentragwerke mit Lastfällen und Kombinationen nach DIN EN 1990, Kontakt,
Nachweisen nach DIN EN 1993-1-1 (Stahlbau) und DIN EN 1993-1-9 (Ermüdung),
Mehrkernrechnung, Rechnerfarm und statischem Bericht.

## 1 Installation und Start

```bash
pip install -r requirements.txt        # numpy, scipy, PySide6, pyvista, pyvistaqt
pip install gmsh                       # optional: CAD-Import STEP/IGES/STL
pip install pypardiso mkl              # Mehrkern-Gleichungslöser (Intel MKL); ohne ihn rechnet
                                       # die Faktorisierung auf genau einem Kern
pip install reportlab svglib           # optional: PDF-Bericht direkt aus dem Programm

python run_gui.py                      # oder: python -m statik3d.gui
python -m statik3d.cli --beispiel hall --nachweise --ermuedung --bericht halle.html
```

Windows-Programm ohne Python: `Statik3D.exe` von
https://github.com/Alex1977-code/Statikprogramm/releases/latest/download/Statik3D.exe
(eine Datei, doppelklicken; SmartScreen beim ersten Start mit „Weitere
Informationen → Trotzdem ausführen“ bestätigen). Der Start dauert zehn bis
dreißig Sekunden — die Datei packt sich aus und lädt die Grafik- und
Rechenbibliotheken. Solange steht ein **Startbild** mit Programmsymbol,
Fassung und der Meldung, was gerade geladen wird; es verschwindet, sobald
das Fenster steht. Kein zweiter Doppelklick nötig. Der Knopf **Update suchen**
unten rechts holt die neueste Version: prüfen, herunterladen, austauschen,
Neustart. Dasselbe leistet Hilfe → Nach Update suchen… in jeder Installation.
Der Austausch läuft nicht, solange eine Berechnung oder Vernetzung läuft — der
Knopf zeigt dann „Update bereit“, und der Austausch folgt auf Knopfdruck nach
dem Ende. Nach dem Schließen beendet sich Statik3D sofort, ohne Modell und
Sicherungen abzuräumen (bei 2 Mio. Elementen 11 s je Kopie); das Skript
wartet bis zu 300 s. Am 11.09.2026 gab es nach 120 s auf, weil das Programm
noch lief, und die neue Fassung startete nicht. Meldet das Skript „läuft
noch“, obwohl kein Fenster offen ist, halten Reste einer früheren Sitzung die
Programmdatei fest (am 11.09.2026 drei Prozesse vom Vorabend, 4 bis 43 MB):
nach 20 s zeigt das Skript diese Prozesse und beendet sie nur auf „J“; der
Knopf „Update bereit“ nennt sie vorher mit ihrer PID, damit sie im
Task-Manager beendet werden können.

Der Austausch läuft über ein kleines Skript `statik3d_update.bat` neben der
exe: Statik3D beendet sich, das Skript ersetzt die Datei und startet die neue
Fassung. Es räumt dabei die internen Umgebungsvariablen des Programmpackers
weg (`_PYI_…`, `_MEIPASS2`) — erbte die neue exe sie, hielte sie sich für
einen Unterprozess der alten und bräche mit „Security validation failure:
parent process has different executable!“ ab. Die neu gestartete Fassung
**meldet sich** beim Skript zurück (Datei `statik3d_update.ok`); bleibt die
Meldung aus, weil die exe beim Start abgebrochen ist, sagt das Skript das und
was zu tun ist, statt sich zu löschen. Ein Protokoll des Austauschs liegt als
`statik3d_update.log` daneben; klappt etwas nicht, bleibt das Fenster mit der
Begründung stehen und die neue Datei liegt bereit.

Erscheint die Sicherheitsmeldung trotzdem einmal — das ist der Fall, wenn die
**alte** exe den Austausch noch ohne diese Vorkehrung ausgeführt hat —, ist
der Austausch selbst schon geschehen: die neue Fassung liegt an Ort und
Stelle. Meldung schließen, `Statik3D.exe` aus dem Explorer heraus starten
(Doppelklick), fertig; der Fensterrahmen zeigt den neuen Stand. Ab dann
laufen alle weiteren Aktualisierungen mit der Vorkehrung.

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
Vierzehn Register nach Arbeitsschritt:

| Register | Inhalt |
|---|---|
| **Datei** | Neu, Öffnen, Speichern, Projektangaben, Übernehmen aus fremden Formaten, Exportieren, Beispiele |
| **Start** | Auswahl, Modellprüfung, doppelte Knoten, freie Stabenden anschließen, Berechnen |
| **Unterlagen** | **Dateien** (Datei hinzufügen: PDF, Bild, Word, Excel …; Unterlage öffnen; Entfernen), **Ansichten** (Ansicht aufnehmen, Skizze aus Ansicht), **Skizze** (Neue Skizze, Bearbeiten), **Bericht** (In den Bericht, Unterlagen zeigen) — seit 16.09.2026, siehe *Unterlagen* |
| **Geometrie** | Knoten, Linien, **Ändern** (Verschieben, Kopieren, Drehen, Spiegeln der Auswahl), **Konstruktion** (Lot / Projektion), Auswahlart in der Ansicht, Koordinatensysteme, Arbeitsebene und Fang (auch „Lot“) |
| **Struktur** | nach Objektart gegliedert: **Stäbe** (Stab, Stabzug, Stäbe für Nachweise, automatisch erkennen, Querschnitt zuweisen), **Flächen** (Schale, Fläche aus Linien, Rechteckplatte, vernetzen, verschneiden, Dicke zuweisen), **Volumen** (Volumen aus Flächen, Quader, vernetzen), **Gelenke** (Gelenk anlegen, Gelenke setzen, Tabelle), Eigenschaften (Querschnitte, Werkstoffe, Dicken, Elemente löschen) |
| **Lager / Kontakt** | Knoten-, Linien-, Flächenlager, Nichtlinearität, Kontakt, Anschlüsse (anlegen, zeigen, löschen) |
| **Lasten** | Lastfälle, Kombinationen, Lastfälle nach DIN 19704, Knoten-, Stab-, Flächen-, Temperaturlast, Zwangsverformung, Vorspannung, Eigengewicht, Generierer Wasserdruck und Wind |
| **Netz** | Vernetzen (Flächen und Volumen), Netzeinstellungen (Netzdichte, Elementform, intelligente Anpassung), Netzqualität, **Netzknoten** (Schalter), Netz löschen, Kontaktfugen |
| **Berechnung** | Berechnen (F5), einzelner Lastfall, Eigenschwingungen, Knicken, alle Stellungen, DIN 19704, Einstellungen, Bedienung im Browser |
| **Nachweise** | EC3, Ermüdung, Verformung (GZG), Beulen (EC3-1-5/-1-6), Lasteinleitung, Konfiguration |
| **Ergebnisse** | Ergebniswahl und die Tabellen |
| **Bericht** | Statischer Bericht, Ansicht übernehmen, **Lastenheft** (anzusetzende Einwirkungen nach DIN 19704/ZTV-ING mit Hintergrund, Ansatz und Skizzen) |
| **Ansicht** | Blickrichtungen, Darstellungsart (Voll, Transparent, Hidden-Line, Drahtmodell), FE-Netz, Knoten, Nummern, Lasten, Stäbe farbig, Lagergröße und Lagerdichte, Einheiten |
| **Messen** | Abstand, Winkel, Koordinaten, Fläche eines Polygons, Länge/Fläche der Auswahl; Bemaßung (Linearmaß, Maßkette, Höhenkote, Winkelmaß, Radius) mit Einstellungen |
| **Extras** | Handbücher, Info, Update |

Links über dem Ribbon die **Schnellzugriffsleiste** (Speichern, Rückgängig,
Wiederholen, Berechnen) — dieselben Befehle, nur schneller erreichbar;
„Alles deselektieren“ steht in der Glasleiste über der Ansicht. Rechts die
**Befehlssuche**: Namen eintippen, Eingabetaste, der Befehl läuft und sein
Register kommt nach vorn.

Die Arbeitsfläche in drei Spalten:

* **links der Modellbaum** — **alles, was modelliert werden kann**, mit Anzahl.
  Mehrere Einträge lassen sich zusammen wählen: **Strg** nimmt einzelne dazu,
  **Umschalt** eine ganze Strecke. Alle Gewählten leuchten dann zusammen im
  Bild, die Statuszeile nennt ihre Zahl, und der Rechtsklick bietet
  *Bearbeiten…* (eine Sammelmaske für alle, unterschiedliche Werte stehen als
  „verschieden“) und *Löschen* mit **einer** Rückfrage für alle. Was nicht
  gelöscht werden kann, bleibt stehen und der Grund steht in der Meldung.
  Der Baum enthält:

  | Zweig | Inhalt |
  |---|---|
  | *Wurzel* (Modellname) | ein Klick zeigt rechts die **Angaben zum Modell**: Anzahl Knoten, Linien, Stäbe, Flächen, Volumen, Lager, Lastfälle und die Abmessungen |
  | Knoten | alle Knoten **numerisch untereinander** (K0, K1, …) mit Koordinaten |
  | Linien | alle Linien, natürlich sortiert (L1, L2, … L10) |
  | Stäbe | zuerst der Zweig **Stäbe mit Nachweis**, darunter alle Stabelemente E0, E1, … |
  | Flächen | die Flächenobjekte, darunter der Zweig „Flächenelemente“ |
  | Volumen | die Volumenkörper, darunter der Zweig „Volumenelemente“ |
  | Eigenschaften | Querschnitte, Werkstoffe, Dicken |
  | Lager | Knoten-, Linien- und Flächenlager, einzeln mit Name und Wirkung |
  | Gelenke | Stabendgelenke mit den freigegebenen Freiheitsgraden; der Zweig steht immer und bietet „+ Gelenk anlegen“ (16.09.2026) |
  | Liniengelenke | aus der Quelldatei (RFEM: LineHinge): jede Fläche mit ihren Gelenklinien und der Wirkung („ux=starr, …, phix=frei“); ein Klick lässt die Linien leuchten, die Maske nennt Fläche, Linien und Wirkung. Der Zweig erscheint, sobald es Liniengelenke gibt (16.09.2026) |
  | Kontaktbedingungen → Flächenkontakte | Kontaktfugen zwischen Flächen und Körpern (in RFEM „Flächenfreigaben“) mit ihrer Wirkung je Freiheitsgrad |
  | Kontaktbedingungen | einseitige Lager, Spaltelemente, Kontaktpaare |
  | Einwirkungen | Lastfälle und Kombinationen. **Unter jedem Lastfall stehen seine Lasten nach Art** (Eigengewicht, Knotenlasten, Stablasten, Linienlasten, Flächenlasten, Temperaturlasten, Vorspannung, Zwangsverformungen), einzeln anklickbar: rechts stehen dann nur diese Lasten, die Tabelle unten zeigt den Lastfall, die belasteten Objekte leuchten; „Lastfall bearbeiten“ holt die Maske des Lastfalls zurück, „Diese Lasten löschen“ nimmt sie heraus |
  | Subsysteme → Stellungen → Situationen | erst die Teile des Tragwerks, dann seine Lagen, dann die Situationen, die einer Stellung ihre Lastfälle und Kombinationen zuordnen |
  | Anschlüsse, Verformungsnachweise, Beulfelder, Volumenbereiche, Lasteinleitung | die Nachweisobjekte |
  | **Ergebnisse** | Umhüllende, Kombinationen, Lastfälle, Nachweise, Eigenformen, Knickfiguren |
  | **Bericht** | die aus der Ansicht übernommenen Ergebnisbilder |

  **Ein Klick wählt aus** — links im Baum, gleichzeitig in der Ansicht: der
  Zweig „Knoten“ wählt **alle** Knoten, der Eintrag „K3“ nur diesen; ebenso
  bei Linien, Stäben, Flächen und Volumen. Die Auswahlart springt mit um.
  Rechts folgt die Anzeige: beim Zweig eine Info mit **Anzahl** und
  **kleinster und größter Nummer**, beim Einzelobjekt seine Felder
  **editierbar** — Nummer und Koordinaten des Knotens, Name und Knoten der
  Linie, Querschnitt und Werkstoff des Stabs, Linien der Fläche, Flächen des
  Volumens. Die **Stabmaske** beginnt seit 13.09.2026 mit dem, was man beim
  Anklicken wissen will, zum Lesen: **Knoten** (Anfang → Ende mit
  Koordinaten, Zwischenknoten), **Länge** und Elementzahl, der
  **Querschnitt** mit Bezeichnung, Art, Maßen in mm (h, b, t_w, t_f, r bzw.
  d und t) und den Kennwerten A, I_y, I_z, I_t, W_el, W_pl, I_w in
  cm-Einheiten, und der **Werkstoff** mit E und f_y (nach Dicke). Bei
  mehreren Querschnitten oder Werkstoffen im Stab stehen alle da. Darunter
  die editierbaren Felder. Ein Stab mit Nachweis zeigt dazu die
  Knicklängenbeiwerte β_y und β_z und den Haken für das Biegedrillknicken;
  der Knopf „Nachweisparameter …“ öffnet alle weiteren (Kipplänge,
  Momentenbeiwerte, Lastangriff, Wölbkrafttorsion, Kerbfall). Der Haken
  **deaktiviert (wirkt nicht)** schaltet den Stab ab, ohne ihn zu löschen:
  er trägt in keiner Situation Steifigkeit oder Last (so kommen in RFEM „für
  Berechnung deaktivierte“ Stäbe herein, `docs/Schnittstellen.md`); ein
  Wechsel verwirft vorhandene Ergebnisse. Eine andere Knotennummer tauscht die beiden Knoten, ein anderer
  Name benennt das Objekt samt aller Verweise um.

  **Rechtsklick → Neu** legt am Zweig ein neues Objekt mit der **nächsten
  fortlaufenden Nummer** an (K17, L8, S3, F5, V2); rechts erscheint seine
  Maske mit **OK** und **Abbrechen**. Ein Knoten steht sofort im Modell (bei
  Nullpunkt, bis man Koordinaten eingibt; Abbrechen nimmt ihn zurück), alles
  andere entsteht erst mit OK.

  **Mit der Tastatur.** Ein Klick in den Baum legt die Tastatur dorthin, und
  sie bleibt dort — auch wenn rechts die Maske des angeklickten Objekts
  aufgeht (die nimmt sie nur, wenn man selbst etwas *anlegt*, denn dann will
  man gleich tippen). Danach gilt:

  | Taste | Wirkung |
  |---|---|
  | ↑ / ↓ | zum vorigen / nächsten Eintrag — die Ansicht und die Maske rechts ziehen mit |
  | Umschalt + ↑ / ↓ | die Strecke dazunehmen (mehrere Einträge derselben Art) |
  | Strg + Klick | einen einzelnen dazunehmen oder wieder abwählen |
  | Umschalt + Klick | alles vom zuletzt angeklickten bis hierher |
  | Pos1 / Ende | zum ersten / letzten Eintrag des Baums |
  | Eingabe | den Eintrag bearbeiten |
  | Entf | den Eintrag löschen (mit Rückfrage) |

  Mehrere gewählte Einträge derselben Art leuchten zusammen in der Ansicht;
  Rechtsklick bietet dann *Bearbeiten …* (Sammelmaske) und *Löschen* für alle
  auf einmal. Einträge **verschiedener** Art sind keine Auswahl — maßgebend
  ist die Art des zuletzt angeklickten.

  **Löschen**: Rechtsklick → „Löschen“ oder den Eintrag anklicken und
  **Entf** drücken. Das Programm fragt nach. Ein Knoten, an dem noch etwas
  hängt, wird mit Grund abgewiesen; eine Fläche oder ein Volumen nimmt seine
  Elemente mit, ein Stab mit Nachweis lässt seine Elemente stehen. Wie alles
  ist auch das Löschen mit **Rückgängig** zurückzunehmen.

  **Ein Doppelklick bearbeitet** die übrigen Objekte in ihrer Maske rechts
  (Querschnitt mit seinen Kennwerten in cm und mm, Werkstoff, Dicke, Gelenk
  mit Wirkung je Freiheitsgrad, Lastfall, Kombination, Stellung,
  Situation, Berichtsbild, Kontaktbedingung …); Lager öffnen ihren Dialog.
  Zweige mit sehr vielen Einträgen zeigen die ersten 20 000 und verweisen für
  den Rest auf die Tabelle unten, wo gefiltert werden kann.
  Die **Stellungen stehen nur hier**, mit „+ Stellung anlegen" am Ende des
  Zweiges; die maßgebende trägt ★.
* **in der Mitte die 3D-Ansicht** — frei für die Grafik.
* **rechts die Eingabemaske** — es ist immer genau **eine** sichtbar: die
  Maske des gewählten Objekts oder das Register zum Befehl im Ribbon; der Titel
  nennt sie. Ist nichts gewählt und kein Befehl aktiv, ist der Bereich leer.
  Die **Projektangaben** stehen nicht von selbst darunter: sie holt der oberste
  Punkt des Modellbaums (der Modellname) oder *Datei → Projektangaben*. Eine
  Registerleiste mit denselben Namen wie im Ribbon gibt es nicht.

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
| Lager | Name und Symbolgröße; Klick oder Doppelklick öffnet rechts die Lagermaske: Wirkung, Feder und Ausfall je Freiheitsgrad, Bettung auf/an Beton als Vorschlag, Schlupf/Reibung/Grenzkraft über den Knopf |
| Gelenke | über die Maske (Doppelklick) |
| Lastfälle | Nr und Beschreibung in der Tabelle; Klick im Modellbaum öffnet rechts **nur den Lastfall**: Nummer, Name, Beschreibung, Einwirkung, darunter alle enthaltenen Lasten nach Art untereinander (dieselben Punkte wie im Modellbaum), dann Ausschlussgruppe, Situation, Theorie, Eigengewicht g_z, ψ-Beiwerte und „aktiver Lastfall“; „Lasten in der Tabelle“ stellt die Lastentabelle auf den Lastfall |
| Kombinationen | Klick im Modellbaum öffnet rechts die Maske: Name, Typ (auch **FAT** für Ermüdung), Beschreibung, Bemessungssituation (nur wenn aus der Quelldatei bekannt, als Angabe), Situation, Theorie, Faktoren als Text („LF1: 1,35, Wind: 1,5“) |
| Kontaktbedingungen | Maske rechts (Klick im Modellbaum, „+ Kontaktbedingung anlegen“ oder *Lager / Kontakt → Kontaktbedingung…*): Körper A und B, Kontaktflächen, Standardkontakt, Zug, Schub x/y, Reibung, Verdrehungen, Suchradius, Anfangsspalt; ausgeführt werden sie beim Vernetzen |
| Flächen, Volumenkörper | über die Maske rechts (Doppelklick): Randlinien bzw. Randflächen — getippt, per **Klick ins Feld** und dann in der Ansicht (seit 15.09.2026) oder mit **„Randlinien anklicken“ / „Randflächen anklicken“** gewählt —, Dicke, Werkstoff, Teilung, Bemerkung, Haken „gleich vernetzen“ |

**Listenfelder der Masken.** Wo eine Maske eine Namensliste zeigt — Randlinien
einer Fläche, Randflächen eines Volumens, Kontaktflächen, Lastfälle einer
Situation —, steht die **Anzahl in der Beschriftung** („Randflächen (13)“),
das Feld beginnt am Textanfang, und der Zeiger darauf zeigt die
**vollständige** Liste, zehn Namen je Zeile. Vorher stand das einzeilige Feld
am Zeilenende: aus dreizehn Randflächen war „9, F64, F71, F98, F46, F52“ zu
sehen, was sich wie „neun Flächen, davon fünf genannt“ liest — und zu der
falschen Diagnose verleitet, es fehlten Flächen. Wird die Liste in der Ansicht
angeklickt, zählt die Beschriftung mit. Bei Randlinien, Randflächen, Körper
A/B, Kontakt- und Gegenflächen macht ein **Klick ins Feld** es scharf (orange
eingerahmt): Klicks in der Ansicht füllen dann dieses Feld; ein Klick in ein
anderes Feld oder Esc beendet das (seit 15.09.2026).
| Bericht | Name, Bildunterschrift, Bemerkung; Reihenfolge mit ▲/▼ |
| Lasten | nur Anzeige und Löschen; das Auswahlfeld links zeigt einen einzelnen Lastfall |

**Lasten anklicken.** Mit der Auswahlart **„Last“** in der Glasleiste trifft
der Klick in der Ansicht die Lastsymbole des aktiven Lastfalls - Pfeile von
Knoten-, Strecken-, Flächen- und Linienlasten, die Temperaturpunkte, Zwangs-
und Vorspannungspfeile. Die getroffene Last leuchtet gelb, rechts steht ihre
Maske mit den Werten (Kräfte, q und q2, Abschnitt, p, ΔT, u, F_v) und dem
Lastfall: Werte ändern und „Übernehmen“, ein anderer Lastfall verschiebt die
Last dorthin, „Löschen“ nimmt sie heraus. Dasselbe geschieht beim Klick auf
eine Zeile der Lastentabelle unten.

**Vorspannung als Last** (*Lasten → Vorspannung*): Stäbe (Zugstange, Seil,
Anker) oder Volumen (Schraubenschaft) in der Ansicht wählen, die Vorspannkraft
F_v in kN eintragen, bei Volumen die Achse (automatisch die längste Abmessung
des Körpers, oder global x/y/z), „Last aufbringen“. Die Vorspannung ist eine
**Anfangsdehnung**: das Bauteil will sich um F_v/(E·A) verkürzen. Hält die
Umgebung es fest, trägt es F_v als Zug und klemmt die Umgebung - wie eine
angezogene Schraube zwischen zwei Platten, deren Kontaktfuge dann die
Klemmkraft F_v überträgt. Ein freies Bauteil verkürzt sich nur, ohne Kraft.
Bei Volumen wirkt sie als einachsige Anfangsspannung −F_v/A längs der Achse
in allen Elementen des Körpers (A = Volumen / Länge, der Schaftquerschnitt);
die Spannungen im Ergebnis enthalten die Vorspannung. In der Ansicht stehen
an beiden Enden violette Pfeile nach außen mit der Kraft, im Modellbaum steht
sie als Unterpunkt „Vorspannung“ des Lastfalls, in Tabelle und Bericht mit
Bauteil, Kraft und Achse.

**Flächenkontakte** (in RFEM „Flächenfreigaben“) sind Kontaktfugen: in der
Fugenebene starr oder frei, senkrecht dazu frei mit Ausfall.

**Wo die Fuge in der RFEM-Datei steht.** Eine Flächenfreigabe führt zwei
Listen: *releasedSolids/releasedSurfaces* — **was** gelöst wird — und
*assignedToObjects* — **woran** die Freigabe hängt. Die Fuge ist die zweite.
Die erste zählt bei einem gelösten Volumen dessen **ganze Außenhaut** auf: bei
der Grundplatte eines Lagerbocks 36 Flächen über 1,65 m² — Ober- und
Unterseite, alle Schmalseiten, alle Buchsenmäntel —, von denen nur ein
Bruchteil an einer Fuge liegt. Die zugeordneten Flächen sind dagegen genau die
Fuge: bei einem Passstift seine beiden Mantelhälften, sonst nichts.

Statik3D nimmt darum die zugeordneten Flächen als Fuge und sucht beim
Vernetzen die Randseiten des gelösten Körpers, die auf ihnen liegen. Im
Modellbaum steht deshalb „V14 an 16 Flächen“ und nicht „36 Flächen“. Nur wenn
eine Freigabe **keinen** gelösten Körper und keine zugeordneten Flächen nennt —
eine reine Flächen-an-Flächen-Freigabe —, sind die freigegebenen Flächen selbst
die Kontaktseite.

*Bis Version 1.x* wurden die freigegebenen Flächen als Kontaktseite genommen.
Das trennte das Netz an Flächen ohne Gegenüber und paarte Knoten über
Zentimeter Luft hinweg; an einer Grundplatte fand nur ein Viertel der
Kontaktseite eine Gegenseite, bei einem mittleren Spalt von 29 mm. **Modelle,
die vorher eingelesen wurden, sind neu zu importieren** — in der gespeicherten
Datei stehen noch die alten Kontaktflächen. Vor dem Vernetzen steht am Eintrag „wird beim Vernetzen
getrennt“ - ohne Warnzeichen, denn ohne Netz gibt es nichts, was zu steif sein
könnte. Ein ⚠ mit „nicht ausgeführt - hier zu steif“ erscheint nur, wenn das
Netz da ist und die Fuge trotzdem nicht getrennt werden konnte; das Protokoll
nennt dann den Grund. Statik3D liest sie
aus der RFEM-Datei vollständig ein und **führt sie beim Vernetzen auch aus**:
die Netze werden an der Fuge getrennt, und je nachdem, ob sie Knoten für Knoten
zusammenpassen, hält sie ein Spaltelement je Knotenpaar oder ein Kontaktpaar
über die Fläche. Die Fuge trägt dann Druck und geht unter Zug auf.

Wer nur einzelne Körper neu vernetzt oder ein Modell von Hand aufgebaut hat,
findet den Befehl auch einzeln: **Netz → Kontaktfugen ausführen**. Die
Spalte „Trennung ausgeführt" sagt, ob und wie es geschehen ist
(„ja (68 Spaltelemente)", „ja (Kontaktpaar)"); steht dort „nein", rechnet das
Modell an dieser Stelle durchverbunden — also **zu steif** —, und das Protokoll
sagt, woran es lag.

#### Geometrischer Spalt an der Fuge

In der Maske einer Kontaktbedingung stehen **Geometrischer Spalt [mm am Ø]**
und **Spalt abtragen** (auf beide verteilen, nur an der Welle, nur an der
Bohrung). Das Eintragen ändert **nichts** am Modell — es ist eine Angabe an
der Fuge, umkehrbar und mit dem Modell gespeichert. Darunter steht, wie viel
davon schon eingearbeitet ist.

**Spalt-Vorschau** zeigt, was geschehen würde: Welle und die Bauteile der
Bohrung leuchten in der Ansicht, die Meldung nennt beide Radien vorher und
nachher und das offene Maß. Die Geometrie bleibt dabei unberührt.

**Eingearbeitet wird beim Vernetzen**, vor dem eigentlichen Vernetzen: das
Programm rückt die Bögen der Welle nach innen und die der Bohrung nach außen,
die Bohrung über ihre ganze Länge in jedem Bauteil, durch das sie geht. Was
eingearbeitet ist, merkt sich die Fuge, damit es sich beim nächsten Vernetzen
nicht wiederholt. Im Protokoll steht eine Zeile je Fuge mit Maß, Aufteilung
und den Volumen, die dadurch ein neues Netz brauchen. In der Rechnung wirkt
der Spalt dann von selbst, weil er im Netz steht.

Der Unterschied zum Feld **Spiel je Seite** darüber: jenes ist ein
rechnerischer Anfangsspalt im Kontakt (die Fuge schließt erst nach diesem
Weg, die Geometrie bleibt), dieses eine wirkliche Lücke im Netz.

#### Spalt / Toleranz: Welle und Bohrung auf ein Spiel bringen

*Geometrie → Spalt / Toleranz* (17.09.2026, „der innere Zylinder sollte als
solcher erkannt werden und der gewünschte Spalt ausgehend vom Nullmaß
eingestellt werden können, gleiches gilt für das Auge/die Bohrung“). Die
Maske nennt oben den gewählten **Zylinder** und darunter das **Nullmaß**, das
das Programm an ihm misst (Radius und Durchmesser), sowie die **Bohrung**:
alle Kreise desselben Radius auf derselben Achse, mit dem Bauteil, zu dem sie
gehören. Ein Passstift durch zwei Bleche hat seine Bohrung in beiden, und
beide stehen da.

Eingetragen wird der **Spalt am Durchmesser**, vom Nullmaß aus. Wo er
abgetragen wird, ist wählbar: auf beide verteilen (je die Hälfte), nur am
Zylinder abziehen, oder nur an der Bohrung zugeben. Die Bohrung wird dabei
**über ihre ganze Länge** angepasst, in jedem Bauteil, durch das sie geht —
sonst bliebe hinter dem ersten Blech ein Kegel stehen.

Was das Programm tut: Stift und Bohrung teilen sich in RFEM Knoten und
Bogenlinien, auch die Kreise in den Öffnungen der Deckflächen. Beide werden
erst voneinander getrennt (eigene Kopien der geteilten Linien und Knoten),
dann rücken die Bögen — der Zylinder nach innen, die Bohrung nach außen. Das
Netz der veränderten Volumen fällt weg; ob gleich neu vernetzt wird,
entscheidet der Haken. Ohne ihn nennt das Protokoll die Volumen, die dran
sind, und das nächste Vernetzen führt ihre Kontaktfugen aus.

Die Funktion ist nicht auf importierte Modelle beschränkt; sie arbeitet an
jeder Geometrie mit Kreisbögen, also auch an selbst erstellten Modellen.

#### Spiel geometrisch geben

*Lager / Kontakt → Spiel geben* (17.09.2026, „zylinderförmige Bauteile
geometrisch mit dem Spiel versehen, ggf. auch Ebenen; dann bräuchte es keine
Sonderbedingungen“). Zylindrische Volumen in der Ansicht wählen (Auswahlart
*Volumen*: Passstifte, Bolzen, Schrauben) oder ebene Flächen (Auswahlart
*Fläche*), dann *Spiel geben*: die Maske nennt, was sie als Zylinder erkennt,
das Spiel in mm eintragen — bei
Zylindern das Spiel am **Durchmesser**, bei Flächen der **Spalt** —, und
anwenden. Was geschieht: Stift und Bohrung teilen sich in RFEM die
Kreisknoten und oft die Bogenlinien; darum wird der Zylinder zuerst von
seinen Nachbarn **getrennt** (geteilte Linien und Knoten bekommen Kopien, die
ihm gehören, die Bohrung behält ihr Maß), dann rücken seine Bögen und Knoten
auf dem Schaftradius um das halbe Spiel zur Achse. Eine gemeinsame
Trennfläche zweier Volumen bekommt für das gewählte Volumen eine eigene
Kopie, die um den Spalt nach innen rückt. Das Netz der veränderten Volumen
wird gelöscht und, wenn der Haken steht, gleich neu erzeugt; ihre
Kontaktfugen werden wieder ausgeführt und bleiben erhalten (auch die von
selbst entstandenen — mit Spiel „berühren“ sich die Teile im Sinn der
Berührungssuche nicht mehr). Das Protokoll nennt je Volumen Radius, Achse,
Spiel und die Zahl der Kopien. Danach trägt der Stift wie in Wirklichkeit auf
der belasteten Seite; an der Fuge genügt „Reibungsbehaftet“.

**Was als Zylinder gilt.** Alle Kreisbögen des Volumens haben denselben
Radius und liegen auf einer Achse, an mindestens zwei Stellen längs dieser
Achse; ein Bolzen mit Kopf hat zwei Radien, der Schaft ist der häufigste, der
Kopf bleibt. Dazu — und das ist die entscheidende Prüfung — liegt **kein
Punkt des Volumens weiter von der Achse entfernt als sein größter Kreis**.
Ohne sie ging eine Rippe als Zylinder durch: ein Blech mit einer Ausrundung
an Ober- und Unterkante hat zwei Kreisbögen gleichen Radius, deren
Mittelpunkte auf einer Geraden längs der Blechdicke liegen. Am Drehlager
bekam V5 auf diesem Weg 0,02 mm Spiel, obwohl seine Ecken bis 297 mm von
dieser vermeintlichen Achse entfernt lagen (behoben 17.09.2026). Wird ein
Volumen abgelehnt, nennt das Protokoll den Punkt und den Radius, an denen es
scheitert.

**Wenn ein Volumen versehentlich Spiel bekommen hat:** *Rückgängig* (Strg+Z)
stellt den Stand davor wieder her. Das ist wichtiger als die Hundertstel am
Radius: Ein Volumen, das Spiel bekommt, wird zuvor von seinen Nachbarn
**getrennt**, verliert also die gemeinsamen Knoten einer verschweißten
Fläche. Bei einer Rippe, die an ihr Blech angeschlossen ist, wäre das ein
Eingriff in den Lastpfad.

#### Passung für viele Fugen auf einmal

*Lager / Kontakt → Passung* setzt Spiel, Lochleibungsgrenze und
Randabminderung für **alle Kontaktfugen der gewählten Volumen** auf einmal
(17.09.2026, „alle betroffenen Volumen selektieren und einmal im rechten
Menü für alle diese Einstellung vornehmen“): Auswahlart *Volumen*, die
Passstifte oder Bolzen in der Ansicht wählen (mehrere mit Strg oder dem
Auswahlfenster), dann *Passung* - die Maske nennt die Volumen und die
betroffenen Fugen (jede, an der eines der Volumen Kontakt- oder Gegenseite
ist), die Werte eintragen, **Auf die Kontaktfugen anwenden**. Ohne Auswahl
gelten die Werte für alle Fugen. Am vorhandenen Netz werden die Fugen gleich
neu ausgeführt; das Protokoll nennt je Fuge die Passung („Spiel 0,020 mm je
Knoten, Lochleibungsgrenze 355 N/mm², 24 Randknoten (1 Reihen) haften
nicht“). RFEM kennt diese Angaben nicht - sie werden hier nach dem Import
gesetzt und mit dem Modell gespeichert.

Warum: Passstift und Bohrung haben am Drehlager beide r = 12,500 mm
(Nullspiel). Rechnerisch liegt der Stift am ganzen Umfang an, haftet dort und
wird am Bohrungsaustritt von der Kante gequetscht - Spannungsspitzen, die
es real nicht gibt: ein Passstift hat Spiel, trägt auf der belasteten Seite,
und Fase und Fließen begrenzen die Kante. Spiel und Lochleibungsgrenze
bilden das ab; die Randabminderung nimmt die Singularität der haftenden
Kante aus der Rechnung. Für den Nachweis zählt ohnehin die Lochleibung
F/(d·t), nicht der Knotenwert.

#### Kontakte entstehen von selbst

Berühren sich zwei Volumen — über eine **gemeinsame** Fläche oder über je
eigene Flächen, die **aufeinanderliegen** —, legt das Programm von selbst eine
Kontaktbedingung an (seit 15.09.2026): bei jedem neuen Modellstand, also nach
dem Import, nach „Volumen aus Flächen“, nach dem Verschieben von Knoten.
Vorgabe ist **starr** (Standardkontakt „Verbund“: Druck, Zug und Schub werden
übertragen, wie verschweißt). Das Modell rechnet damit genau so wie ohne die
Bedingung — aber die Fuge ist jetzt ein Objekt: im Modellbaum anklicken, rechts
die Wirkung umstellen (nur Druck, Reibung, …), fertig. Der kleinere Körper wird
Körper A (er wird an der Fuge gelöst), der andere Körper B; bei gemeinsamer
Fläche steht sie als Kontaktfläche, bei eigenen Flächen die von A als Kontakt-,
die von B als Gegenflächen.

Der **Name trägt die Wirkung** — „Bolzen–Platte starr“, nach dem Umstellen
„Bolzen–Platte nur Druck“ —, solange man den Namen nicht selbst ändert. Die
Wirkungen und ihre **Farbe** (dieselbe im Modellbaum und bei „Kontakte
zeigen“):

| Wirkung | heißt | Farbe |
|---|---|---|
| Zug und Schub übertragen (Verbund) | starr | grau |
| hebt ab, gleitet frei (Reibungsfrei) | nur Druck | rot |
| hebt ab, Coulomb-Reibung (Reibungsbehaftet) | Druck, Reibung | orange |
| hebt ab, haftet (Rau) | Druck/Schub | grün |
| kein Abheben, gleitet frei (Ohne Trennung) | Zug/Druck | blau |
| kein Abheben, mit Reibung | Zug/Druck, Reibung | türkis |
| eine Richtung als Feder | Feder | violett |

Ein **starrer** Kontakt an einer gemeinsamen Fläche ist eine Schweißnaht: er
wird nicht ausgeführt und ist nie „zu steif“ — Zustand „verschweißt (starr an
gemeinsamer Fläche, nichts zu trennen)“, Spalte „Trennung ausgeführt“:
„entfällt (verschweißt)“ —, und für angeschweißte Nachbarn (die sich an einer
Fuge mitlösen) und den Kerbfall der Naht zählt er wie keine Bedingung. Erst
eine andere Wirkung trennt das Netz dort. (Starr zwischen je eigenen,
aufeinanderliegenden Flächen ist dagegen ein Kontaktpaar mit Zug und Haften —
es bindet die beiden Netze.) Einen **gelöschten** automatischen Kontakt legt das Programm nicht
wieder an (das Paar ist als Ausnahme gemerkt; „+ Kontaktbedingung anlegen“
legt von Hand einen an); automatische Kontakte, deren Körper sich nicht mehr
berühren, verschwinden wieder, solange sie noch nicht im Netz ausgeführt sind.

Berührung heißt: näher als 1e-5 der Modellgröße (Drehlager: 55 µm; dort
liegen aufeinanderliegende Flächen unter 1 µm auseinander, das nächste
getrennte Paar — ein Passstift im Loch — bei 0,1 mm), gemessen an inneren
Probepunkten der Flächen; aufliegend ist eine Fläche, wenn mindestens ein
Viertel ihres Inhalts auf der anderen liegt (angrenzende Flächen mit nur einer
gemeinsamen Kante zählen so nicht). Am Drehlager (108 Körper, 1375 Flächen):
145 berührende Paare, davon 25 ohne Kontaktbedingung — alle über gemeinsame
Flächen, also verschweißte Rippen und Deckel —, Suche 1,9 s im Fenster (die
Vielecke der Flächen hat die Ansicht schon; ohne sie 3,4 s); das Anlegen der
25 Kontakte kostet darüber hinaus nichts, weil eine Naht nicht ausgeführt wird
(Modell setzen 10 s; solange jede neue Bedingung sofort ausgeführt wurde,
waren es 73 s, und 22 der 25 standen als „zu steif“, weil die Suche nach der
Gegenseite sich am verschweißten Ring der Rippen festfuhr). Geprüft in
`tests/test_kontakte.py` und `tests/test_fugen.py`
(`test_naht_bleibt_verschweisst`, `test_naht_loest_nachbarn_mit`).

#### Kontaktbedingungen anlegen und einstellen

Ein Kontakt wird **wie in ANSYS** angelegt: zwei Körper, mindestens eine
Fläche, dann die Wirkung an dieser Fläche. Der Weg: im Modellbaum unter
*Kontaktbedingungen → Flächenkontakte* auf **„+ Kontaktbedingung anlegen“**
(oder *Lager / Kontakt → Kontaktbedingung…*, oder Rechtsklick → Neu). Rechts
erscheint die Maske.

**Mit der Maus ausfüllen** (seit 15.09.2026). Ein **Klick ins Feld** *Körper
A*, *Körper B*, *Kontaktflächen* oder *Gegenflächen* macht das Feld **scharf**
(orange eingerahmt): jeder Klick in der Ansicht füllt jetzt dieses Feld.
Eine **neue** Bedingung beginnt gleich mit *Körper A*: Volumen anklicken, das
Programm springt weiter zu *Körper B* und dann zu den *Kontaktflächen*. Beim
Flächenklick füllt die Maske die Körper selbst: ist Körper A noch leer, wird
der Körper der Fläche Körper A; eine Fläche, die **nicht** zu Körper A gehört,
ist die Gegenseite — sie kommt zu den Gegenflächen, und ihr Körper wird
Körper B, wenn dort noch „(alle anderen Körper)“ steht. Eine Fuge ist so mit
zwei Klicks beschrieben: erst die Fläche des einen, dann die des anderen
Körpers. Ein zweiter Klick nimmt eine Fläche wieder heraus. Im Bild leuchten
dabei beide Seiten der Fuge (bei Körper A/B die beiden Volumen). Ein Klick in
ein anderes Feld (Name, μ, Beschreibung …) oder **Esc** beendet die Auswahl per
Maus; ein zweites Esc hebt wie sonst die Auswahl auf. Vorher standen dafür zwei Knöpfe
unter der Maske („Kontaktflächen anklicken“, „Gegenflächen anklicken“), und die
Körper ließen sich nur aus der Liste wählen.

Die Felder:

| Feld | Bedeutung |
|---|---|
| Körper A (Kontaktseite) | der Körper, dessen Flächen die Kontaktseite bilden - er wird an ihnen gelöst; aus der Liste, per Klick ins Feld und dann auf das Volumen, oder aus der ersten angeklickten Kontaktfläche |
| Körper B (Gegenseite) | der Körper, gegen den der Kontakt wirkt; „(alle anderen Körper)“ sucht die Gegenseite unter allen Bauteilen; per Klick ins Feld und auf das Volumen, oder aus der ersten Gegenfläche |
| Kontaktflächen | Flächen von Körper A - getippt oder **ins Feld klicken** und in der Ansicht wählen (jeder Klick nimmt dazu oder heraus). Leer darf das Feld nur bleiben, wenn Gegenflächen genannt sind: dann ist die Kontaktseite, was von Körper A auf ihnen liegt - so kommt jede RFEM-Freigabe herein. Sind beide leer, lehnt „Übernehmen“ eine neue Bedingung ab |
| Gegenflächen | die Flächen der Gegenseite - ebenso per Klick ins Feld in der Ansicht wählbar (seit 14.09.2026; vorher nur Anzeige aus der Quelldatei). Genannt: der Kontakt wirkt **nur auf diesen Flächen** (seit 15.09.2026). Leer: die Gegenseite wird im Suchradius gesucht. Der Klick ins andere Feld schaltet die Auswahl per Maus auf die andere Liste um |
| Standardkontakt | setzt die Richtungen darunter mit einem Griff (Tabelle unten); danach lässt sich jede Richtung von Hand ändern, der Standard wird dann „Benutzerdefiniert“ |
| Druck | wird immer übertragen - das ist Kontakt |
| Zug | *abheben möglich* (die Fuge öffnet unter Zug), *wird übertragen* (Verbund, kein Abheben) oder *Feder* |
| Schub x, Schub y | in der Fugenebene *frei (gleiten)* - mit dem Reibbeiwert als Coulomb-Reibung -, *starr (haften)* oder *Feder* |
| Reibbeiwert μ | Coulomb-Reibung in der Fugenebene; 0 = reibungsfrei |
| Verdrehungen | φx, φy, φz starr oder frei - nur bei Schalen wirksam, Volumen haben keine Verdrehungen |
| Feder c | Steifigkeit [kN/m je m²] für Richtungen mit „Feder“ |
| Suchradius | wie weit die Gegenseite entfernt liegen darf, damit sie noch zur Fuge gehört (ANSYS: „Pinball“); ein Tausendstel davon gilt als Berührung. Das Protokoll nennt den verwendeten Wert (am Drehlager „Achse (Typ 3)“: 50 mm, das Netz der Bohrung). Von Hand nur, wenn Spiel größer als ein Element zur Fuge gehören soll. 0 = automatisch: die größere mittlere Kantenlänge der **beiden Seiten dieser Fuge** — dazu sucht das Programm zweimal, erst weit, um die Gegenseite zu finden, dann mit deren Netz. So bekommt eine feine Fuge nicht die Netzweite eines groben Modells. Damit findet eine fein vernetzte Achse (2 mm) ihre grob vernetzte Bohrung (15 mm) auch mit Spiel; was weiter weg liegt, gehört nicht zur Fuge. Ein eingetragener Wert gilt unverändert |
| Anfangsspalt | *wie modelliert*: ein Spalt bleibt offen, bis die Last ihn schließt. Gemessen wird zur **wahren** Fläche, nicht zur Facette: an einer Bohrung zählt der Bogen, nicht die Sehne, eine passgenaue Achse liegt darum überall an, auch zwischen den Ecken der Bohrung und auch bei verschieden feinen Netzen (seit 13.09.2026); ein Spalt unter einem Tausendstel des Suchradius gilt als Berührung. *auf Berührung setzen*: jeder Knoten gilt in seiner Lage als anliegend - auch ein wirkliches Spiel verschwindet (ANSYS: „adjust to touch“) |
| Spiel je Seite [mm] | **Passung** (17.09.2026): ein Anfangsspalt je Knoten zusätzlich zur Geometrie - bei einer Bohrung das radiale Spiel, also das halbe Durchmesserspiel (H7/h6 bei 25 mm bis 0,02 mm). Ein Passstift trägt dann nur auf der belasteten Seite statt am ganzen Umfang. Verliert ein Teil damit vorübergehend alle Bedingungen, hält die Rechnung es an den drei nächsten Punkten, bis das Spiel durchfahren ist (Abschnitt „Abbruch der Kontakt-Iteration“) |
| Lochleibungsgrenze [N/mm²] | 0 = keine. Sonst ist die Normalkraft jedes Kontaktknotens auf Grenzpressung × Einflussfläche des Knotens begrenzt; darüber **fließt** er mit konstanter Kraft, und die Nachbarn tragen den Rest - wie das örtliche Fließen an der Bohrungskante, das die Spitze in Wirklichkeit begrenzt. Richtwert fy bis 1,5 fy. Das Kontaktergebnis zeigt „Fließen“ und die Grenzkraft je Bedingung |
| Randabminderung [Knotenreihen] | 0 = keine. Sonst haften so viele Knotenreihen am Rand der Kontaktseite nicht, sondern gleiten reibungsfrei: die Kantensingularität der haftenden Fuge am Bohrungsaustritt bleibt aus. Eine Reihe reicht meist. Rand ist, wo eine Facettenkante nur zu einer gepaarten Facette gehört - der Rand der Kontaktseite oder der Rand des Bereichs mit Gegenseite |

Die **Standardkontakte** heißen wie in ANSYS:

| Standard | Zug | Schub | Verdrehungen | Reibung |
|---|---|---|---|---|
| Verbund | wird übertragen | starr (haften) | starr | - |
| Ohne Trennung | wird übertragen | frei (gleiten) | frei | 0 |
| Reibungsfrei | abheben möglich | frei | frei | 0 |
| Reibungsbehaftet | abheben möglich | frei | frei | μ (Vorgabe 0,2) |
| Rau | abheben möglich | starr (haften) | frei | - |

Die Flächen der beiden Körper müssen **weder deckungsgleich noch gleich fein
vernetzt** sein: das Kontaktpaar verbindet jeden Knoten der Kontaktseite mit
der nächsten Facette der Gegenseite im Suchradius (Knoten gegen Fläche). Liegt
ein Knoten der Kontaktseite genau auf einem Knoten der Gegenseite, wird er
ohne Suche direkt mit ihm gepaart. Steht schon ein Netz, wird die Fuge mit
„OK“ bzw. „Übernehmen“ sofort getrennt und das Protokoll sagt, wie viel der
Kontaktseite eine Gegenseite gefunden hat („599 von 3430 cm²“) - die übrige
Kontaktseite liegt weiter als der Suchradius von jedem anderen Bauteil
entfernt. Der **Spalt** ist dabei der Abstand senkrecht zur Fuge; ein Versatz
**in** der Fugenebene zählt nicht mit, denn er bedeutet kein Abheben. Ohne
Netz geschieht es beim Vernetzen.

**Kontakt wirkt nur, wo sich die Flächen gegenüberstehen** (seit 15.09.2026).
Ein Knoten der Kontaktseite, der neben der Gegenfläche liegt — hinter dem Ende
einer Buchse, im Grund einer Stiftbohrung, die tiefer ist als der Stift, am
Rand eines überstehenden Blechs —, bekommt keine Kontaktbedingung und trägt
nicht. Vorher durfte er bis zur Größe einer Facette danebenliegen; am
Drehlager trugen so Knoten der Achse bis 25 mm hinter dem Ende der Buchse
(1982 kN), und ein Passstiftloch trug an seinem Rand, 3 mm hinter dem
Stiftende, 708 kN auf einem Knoten. Das Protokoll nennt diese Knoten beim
Rechnen je Kontaktpaar: „… 240 liegen neben der Gegenfläche: dort steht ihnen
nichts gegenüber, sie tragen nicht“. Das ist kein Fehler des Modells, sondern
die Auskunft, wie weit die Kontaktseite über die Gegenfläche hinausreicht.

Zum Spalt nennt das Protokoll die **Verteilung**, nicht einen Mittelwert:

```
Spalt 41 % aufliegend, Median 24.94 mm, 90 % unter 33.99 mm, größter 60.56 mm
```

Steht dahinter „; 207 durchdringend, tiefste 0.62 mm“, liegen so viele
Knoten schon vor der Last **in** der Gegenseite (seit 15.09.2026 getrennt
genannt; vorher gingen sie als Betrag in „größter“ auf). Eine Durchdringung
wirkt wie ein Übermaß und drückt die Fuge vorab zusammen - bei einer
passgenauen Achse ist sie ein Modellfehler, dem man nachgehen sollte.

Das ist die Auskunft, auf die es ankommt. Eine teilweise anliegende Fuge hat
zwei Gipfel — ein Teil liegt auf null, der Rest steht ab —, und ein Mittelwert
darüber nennt eine Zahl, die an keiner Stelle der Fuge vorkommt. Der Spalt
wird zur **wahren** Fläche gemessen: an einer Bohrung zählt der Bogen, nicht
die Sehne der Facette, auf beiden Seiten. Eine passgenaue Achse meldet darum
„100 % aufliegend“, auch wenn Achse und Bohrung verschieden fein vernetzt
sind; am Drehlager stand vorher „22 % aufliegend, Median 0,35 mm“ — der
Sehnenfehler der 50-mm-Facetten —, und die Achse trug nur auf den Knoten, die
auf einer Ecke der Bohrung lagen (13.09.2026, „der Bolzen muss in den Augen
gelagert sein“). Steht dort
ein kleiner Anteil „aufliegend“ und ein Median in der Größenordnung des
Netzes, berühren sich die Bauteile im Modell nicht wirklich: dann stimmt
entweder die Geometrie nicht oder der Suchradius ist zu groß gewählt. Dieselbe
Auskunft steht beim Rechnen noch einmal je Kontaktpaar, dort für die Knoten,
zusammen mit der Zahl derer, die gar keine Gegenfacette gefunden haben, und
derer, die neben der Gegenfläche liegen.

Zur Fugenebene selbst sagt das Protokoll, was sie hält. Ohne Reibung und ohne
Federn trägt eine Fuge nur senkrecht zu ihren Facetten — ob das Bauteil damit
gleiten kann, entscheidet ihre **Form**: ein Absatz, eine Nut oder eine
Bohrung halten seitlich von selbst. Das Protokoll nennt die Anteile, mit denen
die Fuge in ihren drei Hauptrichtungen trägt:

```
Lagerbock-Grundplatte: keine Reibung, keine Federn - die Fuge hält seitlich
durch ihre Form (Anteile 78% / 13% / 9% in z, x, y). Das Bauteil kann nicht
gleiten.
```

Hält nur eine Richtung — die Fuge ist eben —, kommt stattdessen die Warnung,
dass das gelöste Bauteil frei gleiten kann und eigene Lager braucht. Hält sie
zwei, wird die dritte beim Namen genannt. Ändert man eine Bedingung später, wird ihr
Kontaktpaar ersetzt; Löschen (Rechtsklick oder Entf) nimmt es mit.

Aus RFEM eingelesene Flächenfreigaben stehen in derselben Maske. Nummer und
Ort des RFEM-Freigabetyps stehen seit 15.09.2026 nicht mehr darin - keine
Rechnung liest sie, die Wirkung je Richtung steht in der Maske; sie bleiben im
Modell und in der Tabelle *Kontaktbedingungen* (Spalten „Typ“ und „Ort“). Körper A ist
der gelöste Körper, die Gegenflächen sind die zugeordneten Flächen der
Quelldatei — die Fuge. Der Kontakt wirkt nur auf ihnen, nicht auf
Nachbarflächen desselben Bauteils (seit 15.09.2026; vorher trug am Drehlager
die Achse 109 kN auf Bohrungsstreifen, die in RFEM nicht zugeordnet sind).
„Kontaktflächen“ bleibt dann leer; die Fugenflächen des gelösten Körpers
werden beim Vernetzen geometrisch gesucht. Auch diese
Bedingungen lassen sich auf einen Standardkontakt umstellen oder Richtung für
Richtung ändern.

Gefüllte Flächen — die Hervorhebung der Auswahl, die Kontaktfarben und die
Lastfläche — sparen ihre **Öffnungen** aus. Bis 14.09.2026 füllten sie eine
Flanschfläche mit Bohrungen als volle Scheibe; beim Anklicken einer
Kontaktbedingung sah es dann aus, als deckten sich zwei Fugen („es sieht aus,
als hätte Typ 3 kein Loch, sondern überlappt sich mit Typ 1"). Gefüllt wird
jetzt mit denselben Angaben wie die Geometrie: Öffnungen, Geometrieart und
benannte Ecken.

Ein Klick auf eine Bedingung im Modellbaum lässt **ihre Fuge** kräftig
aufleuchten — die Kontaktflächen und die Gegenflächen, nicht den ganzen
gelösten Körper (bis 14.09.2026 leuchtete am Drehlager die komplette Achse
statt ihrer Bohrung) — und die beiden **beteiligten Volumen blass**
durchscheinend dazu (seit 15.09.2026: „beim Anklicken des Kontakts leuchten die
betroffenen Volumen und die Fläche auf“); die Auswahlzeile nennt sie.
*Selektion anzeigen* isoliert die Fuge wie jedes andere Objekt; gibt es gar
keine Flächen, bleibt der Körper als Ausweg.

**Wo welcher Kontakt wie wirkt** zeigt der Schalter *Lager / Kontakt →
„Kontakte zeigen“*: jede Kontaktbedingung liegt dann in der **Farbe ihrer
Wirkung** (Tabelle unter „Kontakte entstehen von selbst“; bis 15.09.2026 je
Bedingung eine Reihenfarbe) durchscheinend über der Geometrie, mit einem Schild
an ihrer Fuge, das Name und Wirkung nennt — etwa „Achse (Typ 3): Druck, abheben, gleiten“. Ein Modell mit
einem Dutzend Fugen ist sonst nicht zu lesen: die Flächen liegen aufeinander,
und die Wirkung stand nur in Tabellen. Nach dem Rechnen kommt der Zustand
hinzu (Schalter *Kontaktmarken* oder die Färbung *Kontakt Zustand*).

In der Tabelle „Knoten“ wird ein Knoten nur gelöscht, wenn **kein** Element
mehr an ihm hängt — sonst sagt das Programm, welches Element im Weg ist. Der
Befehl *Geometrie → Knoten löschen* (und im Kontextregister „Auswahl“) nimmt
dagegen die gewählten Knoten **mitsamt** ihren Elementen; nur Knoten, die eine
Linie noch braucht, bleiben und werden genannt. Beim Löschen eines Elements
oder Knotens werden Stabzüge, Flächen, Volumen, Lager, Lasten, Anschlüsse und
Beulfelder mitgeführt, die Nummern dahinter rücken auf — und alles ist mit
Rückgängig zurückzunehmen.

### Die Geometriekette: Knoten → Linien → Flächen → Volumen

Modelliert wird wie in RFEM, in vier Stufen. Jede Stufe nimmt, was in der
Ansicht ausgewählt ist:

| Stufe | Befehl | Voraussetzung |
|---|---|---|
| Knoten | *Geometrie → Knoten* | – |
| Linie aus Knoten | *Geometrie → Linien → Linie aus Knoten* | mindestens zwei Knoten ausgewählt |
| **Fläche aus Linien** | *Struktur → Flächen* | die ausgewählten Linien bilden einen **geschlossenen** Rand |
| **Volumen aus Flächen** | *Struktur → Volumen* | mindestens vier Flächen ausgewählt |

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
| alles andere | **freier Vernetzer**: Randflächen in Dreiecke, Hülle prüfen, mit Tetraedern füllen |

Ist eine Randlinie ein **Bogen, Kreis, Spline, Parabel oder eine Ellipse**,
folgen die neuen Netzknoten der wahren Kurve — nicht den Sehnen zwischen den
Stützknoten. Eine Polylinie bleibt dagegen eine Polylinie: dort laufen die
Knoten auf den Sehnen, denn etwas anderes hat der Anwender nicht angegeben.

#### Netzdichte und Netzeinstellungen

*Netz → Vernetzen* vernetzt die gewählten - sonst alle - Flächen und Volumen.
**Randflächen von Volumen ohne eigene Dicke** (in RFEM „Null-Elemente“, die
Hülle jedes Volumenkörpers) bekommen dabei kein Schalennetz: die Tetraeder
des Körpers tragen, Lasten auf solchen Flächen gehen über die Randseiten der
Tetraeder. Ein Schalennetz mit einer Ersatzdicke gäbe der Hülle eine
Steifigkeit, die es nicht gibt; das Protokoll nennt die Zahl dieser Flächen.
Die Elementgröße kommt aus den **Netzeinstellungen** (*Netz →
Netzeinstellungen…*, mit der Datei gespeichert):

| Angabe | Bedeutung |
|---|---|
| Netzdichte | **grob / mittel / fein**: 8 / 16 / 32 Elemente über die größte Abmessung jedes Objekts - ein 4 m langer Träger und eine 8 cm dicke Lasche bekommen so je ihr passendes Netz; **eigene**: die Ziellänge gilt absolut (so übernimmt sie der RFEM-Import) |
| Ziellänge, kleinste und größte Elementgröße | in **mm** (seit 13.09.2026; vorher in m) - so, wie man beim Vernetzen denkt; gespeichert und gerechnet wird in m. Auch die Netzqualität *Kantenlänge* färbt in mm |
| Intelligent anpassen | kleine Kanten (Löcher, Stege, schmale Flächen) verfeinern das Netz **der Flächen** dort, bis zur kleinsten Elementgröße; die größte Elementgröße deckelt nach oben (leer = ¼ bzw. 4-fache der Dichte-Länge). Bei **Volumen** bleibt die Kantenlänge im Feld: eine ganze Platte auf ihre Bohrung herunterzuteilen gäbe nur das Vielfache an Tetraedern. Fein wird es **örtlich**, an drei zusammengehörenden Stellen: die Bohrungsränder nach ihrer Krümmung, eine Linie neben einer viel feineren (die **Mantellinie** einer Bohrung stand sonst mit *einem* Abschnitt über der ganzen Bohrtiefe), Kränze um jede Öffnung in der Fläche, und von dort wachsend ins Innere. Gemessen an einer 20-mm-Bohrung von 35 mm Tiefe in einer 900-mm-Platte: der Anteil der Tetraeder unter der Güte 0,3 an der Bohrungswand fällt von 6,8 % auf 1,0 % — für doppelt so viele Elemente. Ohne den Haken bleibt es bei ⌈L/h⌉ je Linie |
| Höchstzahl Elemente je Objekt | vergröbert, was sonst zu viele Elemente gäbe (Schätzung A/h² bzw. V/(0,12·h³)) |
| Elementform | Dreiecke, Vierecke oder Vierecke mit Dreiecken als Rückfall |
| Elementansatz | **linear** (shell3/shell4, tet4, hex8) oder **quadratisch**: Flächen bekommen Mittenknoten (shell6/shell8), abgebildete Volumen hex20, freie Volumen tet10. Quadratisch braucht für dieselbe Genauigkeit deutlich weniger Elemente, je Element aber mehr Rechenzeit |
| Teilung je Fläche aus der Netzdichte | an (Vorgabe): die Netzdichte bestimmt die Teilung aller Flächen; aus: die eigene Teilung jeder Fläche (Flächenmaske, RFEM) gilt |
| Vernetzer (Volumen) | **eigener Vernetzer** (Vorgabe), **gmsh** oder **Netgen**. Alle drei tetraedern dieselbe geschlossene Hülle, die der eigene Vernetzer aus den Randflächen bildet — die Randknoten bleiben Punkt für Punkt erhalten, gemeinsame Flächen zweier Körper und Kontaktbedingungen greifen wie bisher. Gemessen an einer Platte 1 × 0,6 × 0,2 m mit Bohrung (h = 50 mm, Hülle 870 Punkte): gmsh 4 411 Tetraeder, Güte min 0,418, Netgen 5 811, Güte min 0,493; der eigene Vernetzer kam an V5 des Drehlagers auf 0,001. gmsh rechnet mehrkernig (HXT), beide laufen je Körper in den Arbeitsprozessen. Was nicht installiert ist, steht als „(nicht installiert)“ in der Auswahl; der Knopf **Vernetzer installieren…** unter der Maske (auch *Extras → Vernetzer installieren…*) lädt es nach (Abschnitt „Vernetzer und Nachbesserer nachladen“, Kap. 9). Ein nicht verfügbarer Vernetzer wird abgewiesen, und scheitert der fremde an einem Körper, übernimmt der eigene (Protokoll) |
| Nachbesserung | **MMG3D** optimiert das fertige Tetraedernetz bei fester Hülle (`-nosurf -optim`) — der Weg zu einer Mindestgüte aller Elemente, denn die schlechten Tetraeder sitzen auf der Hülle (V5: alle 55 unter 0,1 mit vier Hüllknoten). Das Programm `mmg3d_O3` (mmgtools.org) lädt **Vernetzer installieren…** nach; es läuft als getrennter Prozess über Dateien im Medit-Format — **ohne
Konsolenfenster**: vorher öffnete sich je Volumen eine Eingabeaufforderung, weil
Windows einem Konsolenprogramm, das ein Fensterprogramm startet, eine eigene
Konsole gibt (behoben 14.09.2026). Wo es liegt, weiß Statik3D selbst (nachgeladen im Werkzeugordner, sonst der Suchpfad) — ein Pfadfeld gibt es seit 13.09.2026 nicht mehr; ein in einer älteren Datei gespeicherter Pfad gilt weiter. Gemessen an der Platte mit Bohrung (13.09.2026, MMG 5.8.0): h = 50 mm Güte min 0,103 → 0,453 (19 614 → 18 815 Tetraeder, 6,1 s), h = 30 mm 0,120 → 0,474 (60 610 → 57 817, 1,7 s); Hülle und Volumen unverändert (Randtreue 100 %). Das Protokoll nennt Güte min vorher/nachher |
| Abgebildetes Netz | wird **nicht eingestellt**: abgebildet wird immer, wo die Form es hergibt — eine Fläche mit vier Randabschnitten als Vierecknetz, ein Körper aus **sechs Vierecken mit acht Eckknoten** als regelmäßiges **Hexaedernetz** (x × y × z, hex8 bzw. hex20), ein Körper aus vier Dreiecken als ein Tetraeder; alles andere geht an den freien Vernetzer. Seit 21.09.2026 trägt der Quader Randseiten (eine Flächenlast darauf kam vorher **nicht** an: 0 kN), teilt seine Knoten mit Nachbarn und folgt an gemeinsamen Kanten deren Teilung. Der Haken „Abgebildetes Netz bevorzugen“ stand bis 13.09.2026 in der Maske, ohne dass ihn etwas las; der Wert kommt aus der RFEM-Datei („mapped mesh preferred”) und wird nur mitgeführt |
| Nebenflächen grob (`nebenflaechen_grob`, seit 20.09.2026) | Bögen an **Nebenflächen** — Flächen ohne Last, Lager, Kontaktbedingung, integrierten Knoten, Netzverfeinerung und ohne zweiten Körper — werden mit 45° statt 18° je Abschnitt geteilt: acht statt zwanzig Abschnitte je Vollkreis. Eine Durchgangsbohrung ohne Bolzen, eine Ausrundung tragen nichts; ihre Form muss stimmen, nicht ihre Kerbspannung. Gemessen an einer Platte 1 × 0,6 × 0,2 m mit fünf Bohrungen: 40 364 → 17 969 Tetraeder. **Vorgabe aus**, weil es die Spannung an unbelasteten Bohrungen ändert (dort 490 → 343 N/mm²); die adaptive Vernetzung schaltet es für ihre Dauer ein und holt zurück, was trägt. Heute nur in der Datei (`netz.nebenflaechen_grob`), kein Feld in der Maske |
| Netzverfeinerungen (`verfeinerungen`) | Wo das Netz fein sein soll, unabhängig von der Geometrie: eine **Kugel** um einen Punkt (`{“art”: “kugel”, “mitte”: [x, y, z], “radius”: r, “h”: h}`), eine **Fläche**, **Linie** oder ein **Körper** mit Namen (`{“art”: “flaeche”, “name”: “F12”, “h”: 0.005}`). Die Kantenlänge wächst von dort mit 0,35 je Meter ins Umfeld. Gemessen (Kugel 5 mm, r = 30 mm am Bohrungsrand): 4,2 mm Kanten in der Kugel, 24 mm im Feld, Abnahme ohne Befund. Heute nur in der Datei |
| Eigene Kantenlänge je Körper (`koerper_h`) | `{Körpername: Kantenlänge in m}` — geht vor Dichte und Ziellänge; die Deckel (kleinste Kante, Dickenmaß, Höchstzahl) gelten weiter. So lässt sich ein Körper gröber lassen als der Rest. Die adaptive Vernetzung schreibt hier ihre Werte hinein |
| Sweep (`sweep`, seit 20.09.2026) | **aus** (Vorgabe seit 21.09.2026), Haken „Sechsflächner sweepen (Hexaeder statt Tetraeder)“ in den Netzeinstellungen: ein Körper, der Grundfläche mal Weg ist — Platte, Ring, Flansch, Rippe, Lasche mit Bohrungen — wird in Lagen durchgezogen und besteht aus Hexaedern (hex8) und Keilen (pent6) statt Tetraedern (Theoriehandbuch § 6a, Sweep). Das Protokoll nennt Lagen, Hexaederanteil und Rauminhalt („3 450 Hexaeder (hex8) + 660 Keile (pent6) gesweept — Grundfläche Boden → Deckel, 10 Lagen à 20,0 mm … Hexaederanteil 83,9 %“) und am Ende die Bilanz aller Volumen („0,87 je Knoten — Hexaeder …, Tetraeder …“). Warum: der lineare Tetraeder sperrt, weil vier Elemente je Knoten je eine Volumenbedingung stellen; ein Hexaedernetz hat eines. Die Lagen: aus Weg und Kantenlänge, mindestens zwei — **mit Fließen mindestens vier** (mit einer und zwei Lagen fließt kein Element, Messung 21.09.2026), sechs bis acht über die Kantenlänge. Mantellinien, die Nachbarn gehören, bekommen ihre Teilung vorab und modellweit („Sweep: Lagen für 2 Körper vorab festgelegt …"), damit der Sweep nicht an verschieden geteilten Nachbarn scheitert. Seit 22.09.2026 auch **verjüngte Züge** (Kegelstumpf, konische Rippe, Nabe mit Anzug): der Deckel darf die skalierte Kopie des Grundes sein, die Lagen führen den Maßstab mit. Und **Drehkörper** (Rohrbogen, Ringsegment): Grund und Deckel stehen um den Drehwinkel gegeneinander, die Lagen liegen auf dem Bogen, der Rauminhalt wird nach Guldin geprüft (Ringsegment 90°: 99,5 %). Ein Körper mit sechs Vierecken und acht Ecken, aber **krummen** Kanten geht nicht mehr in den abgebildeten Quaderpfad — der schnitt die Rundung ab und verlor am 90°-Bogen 36 % des Rauminhalts, ohne eine Meldung. Woran ein Körper sonst scheitert, steht als eine Zeile je Körper im Protokoll („nicht gesweept — Kappen F1 → F2 decken sich weder verschoben (12,3 mm daneben) noch skaliert (0,4 mm, Maßstab 0,830) …"). Seit 21.09.2026 abends: **Zylinder** (vier Flächen: Bolzen, Stifte, Achsen) werden gesweept; der Grund darf aus **mehreren ebenen Flächen** bestehen (Platte mit Fußabdruck einer Nabe); ein Körper, der nicht als Ganzes Grundfläche mal Weg ist, wird an **Fußabdrücken zerlegt** („Volumen V1: nicht als Ganzes sweepbar — an 1 Fußabdruck(en) in 2 Blöcke zerlegt (2 davon sweepbar)"), gesweepte Blöcke wo es geht, Tetraeder für den Rest, knotengenau an der Schnittfläche. Seit 22.09.2026 auch an einer **Ebene**, wenn kein Fußabdruck greift — eine Rippe, die bis an den Rand der Platte läuft, hängt nicht über einer Öffnung; geschnitten wird an der Ebene der Deckfläche („an einer Ebene in 2 Blöcke zerlegt (2 davon sweepbar)“). Und Grund und Deckel dürfen ihren Rand **verschieden in Linien teilen**: die fehlenden Ecken werden übertragen und die Wand dazwischen mitgeteilt, sodass auch ein von Hand gebauter Körper sweepbar wird, dessen Deckel eine Kante in zwei Linien führt. Gemessen: Platte mit Nabe 441 hex8 + 108 pent6 statt 7 595 tet4; abgesetzte Welle 446 hex8 + 28 pent6 statt 2 415 gemischt. Platte mit Randrippe: **124 Elemente und 239 Knoten** statt 685 tet4 — und die Verschiebung 2,0161 mm gegen 0,5811 mm; ein Tetraedernetz braucht dafür 39 891 Elemente und 7 459 Knoten (1,9674 mm). **Warum die Vorgabe trotzdem aus ist:** am Drehlager erzeugte der Sweep am 21.09.2026 **992 entartete Keile** (10,6 % aller pent6, schlechteste Formgüte 0,025 — von 31.108 Hexaedern lag keiner unter 0,10), und derselbe Lastfall rechnete darauf max |u| 1,2335 statt 0,2716 mm, also **Faktor 4,5** daneben. Die Ursache war ein Band feiner Randstrecken gegen ein grobes Flächeninneres; seither folgt das Innennetz dem Rand (`mesher3d.RANDFELD`), und am Prüfkörper fielen die schlechten Keile von 34 auf **null**. **Am Drehlager selbst ist das noch nicht nachgemessen** — bis dahin wird von Hand eingeschaltet. Die Abnahme meldet solche Netze vor dem Rechnen; wer einschaltet, sollte sie lesen. |
| Pyramiden am Übergang (`pyramiden`, seit 21.09.2026) | **Aus** (Vorgabe). Ein Tetraeder-Körper, der an die Vierecke eines gesweepten oder abgebildeten Nachbarn stößt, teilt heute jedes Viereck in zwei Dreiecke — knotengleich, aber mit anderer Interpolation auf der Diagonale. Eingeschaltet bekommt jedes Viereck eine **Pyramide** (pyr5) mit Spitze im Inneren, die Tetraeder folgen dahinter. Gemessen an der Platte mit Pyramidenkörper: 12 Pyramiden statt 33 Tetraeder, Rauminhalt gleich, Verschiebung 0,3588 → 0,3589 mm, Formgüte min 0,185 → 0,154. Aus, weil die Rechnung nichts gewinnt und die Formgüte sinkt; ein für den Kontakt sauberer Übergang ist der Grund, ihn einzuschalten. Heute nur in der Datei |
| Feldpunkte (`feldpunkte`) | `[x, y, z, h]` oder `[x, y, z, h, r]` je Punkt — das, was der Fehlerschätzer aus einem Ergebnis ableitet (Theoriehandbuch § 6c). Werden mit dem Modell gespeichert; beim nächsten Vernetzen entsteht daraus dasselbe Größenfeld |

**Adaptiv vernetzen** (seit 20.09.2026, Theoriehandbuch § 6c): *Netz → Adaptiv vernetzen…*
fragt nach den Verfeinerungsrunden (Vorgabe 2) und dem Ziel des bezogenen Fehlers (Vorgabe
5 %), vernetzt, rechnet den aktiven Lastfall, schätzt je Element den Fehler
(Spannungssprung), macht das Netz dort feiner und im Feld gröber und wiederholt das; der
Verlauf steht im Protokoll und in der Meldung („Adaptiv vernetzt: 3 Durchgänge, 441 Elemente
(13,7 %) → 1 456 (13,4 %) → 4 972 (9,2 %)"). Die Rechnungen dazwischen sind Netzmaß, kein
Ergebnis — die Ergebnisliste wird geleert. Dasselbe über die Befehlszeile: `statik3d
modell.json --adaptiv 2 --lastfall LF1 --speichern modell_adaptiv.json`; `--fehlerziel 0.03`
setzt das Ziel. Die Elementzahl wächst je Runde höchstens auf das Dreifache — die Schleife
misst nach. Seit 21.09.2026 verfeinert sie auch gesweepte Körper (Hexaeder und Keile): die
Lagen folgen der feinsten Kantenlänge, die das Feld am Körper verlangt.
Gerechnet wird je Runde ein **Probelauf** des Lösers (ein Kontaktschritt), solange er das
Fließen mitrechnet; lässt er es aus, rechnet die Schleife das fließende Modell voll und
schreibt es ins Protokoll — ein elastischer Probelauf verfeinerte am Drehlager an den
falschen Stellen (54 von 100 Spitzenelementen, 21.09.2026). `--probelauf ja` erzwingt den
Probelauf, `--probelauf nein` den vollen Lauf.
`--vernetzen` allein vernetzt ohne Oberfläche, in derselben Folge wie *Netz →
Vernetzen*. Was die Schleife setzt (Kantenlänge je Körper, Feldpunkte), steht danach in
den Netzeinstellungen des gespeicherten Modells. Ein Befehl in der Oberfläche ist mit
der Programm-Sitzung abzustimmen.

**Feiner Rand, feines Inneres** (seit 21.09.2026): wo eine Randstrecke einer Fläche
weniger als halb so lang ist wie die Kantenlänge — etwa neben einem winzigen Absatz oder
einer kleinen Bohrung —, folgt das Innennetz ihr und wächst von dort auf die Kantenlänge
zurück. Ohne das stand ein Band feiner Randstrecken gegen ein grobes Inneres, und die
Dreiecke dazwischen waren Splitter; beim Sweep wurde aus jedem ein entarteter Keil.
Gemessen an einer Platte mit einem 0,45-mm-Absatz bei 50 mm Kantenlänge: 34 Elemente unter
der Formgüte 0,10 werden zu **null**, die schlechteste Güte steigt von 0,054 auf 0,122; der
Preis sind 45 % mehr Elemente **an dieser Stelle**. Wo der Rand gleichmäßig ist, ändert
sich nichts.

**Enge Hüllkanten** (seit 21.09.2026): das Vernetzungsprotokoll warnt je Körper, wenn die
Randhülle Kanten unter einem Dreißigstel der Kantenlänge enthält — mit Zahl, kürzester
Kante und Herkunft („`12 Hüllkanten unter der Mindestweite 1.67 mm (kürzeste 0.313 mm) —
8x auf der Linie B1U1, 4x am Innennetz einer Fläche`"). Aus solchen Kanten werden Splitter,
die kein Volumenschritt mehr loswird: die Hüllknoten stehen fest. Die Warnung sagt, wo
anzusetzen wäre — an einer winzigen Bohrung (Krümmungsteilung), an zwei eng
zusammenlaufenden Linien (Geometrie) oder am Innennetz. Sie ändert nichts am Netz.

**Splitter in der Abnahme** (seit 21.09.2026): die Abnahme vor dem Rechnen nennt je Körper die
Elemente mit Formgüte unter 0,10 als **WARNUNG** — Zahl, Körper, die drei schlechtesten mit
Elementnummer („WARNUNG: [Splitter] Volumen V30: 29 von 115 734 Elementen mit Formgüte unter
0.10 — schlechteste: Element 4711 (0.025) …"). Sie hält die Rechnung nicht an; unter 0,05 bleibt
es ein FEHLER mit Rückfrage. Das Vernetzungsprotokoll ordnet die Splitter eines Körpers
außerdem nach ihren Hüllknoten ein („davon mit vier Hüllknoten (Kappen) 12, mit drei 5, mit
zwei (Nadeln) 3, im Inneren 0") — jede Sorte hat eine andere Kur.

**Keine Splitter.** Der freie Vernetzer löst **Kappen** auf — Splitter aus vier
Hüllknoten an gewölbten Wänden, die weder Verfeinerung noch Glättung erreichen (mit
einem Punkt knapp innerhalb der Hülle; wo das nicht greift, wird die Kappe entfernt,
und das Hüllviereck ist über die andere Diagonale geteilt). Das Protokoll nennt Zahl
und Rauminhalt („2 Kappen entfernt … Rauminhalt 5,8e-06 m³”). Was danach noch unter
der Güte 0,1 liegt, steht mit Elementnummer im Protokoll.

**Netz → Netzknoten** zeigt die Knoten des FE-Netzes als kleine graue
Punkte — nur, solange das FE-Netz dargestellt ist (*Ansicht → FE-Netz*,
F9). Der Schalter „Knoten“ im Register *Ansicht* meint die Knoten der
Konstruktion; Netzknoten sind die Knoten der beim Vernetzen erzeugten
Elemente, an denen keine Linie und kein Stabende hängt. Ein Modell ohne
Geometrieobjekte (nur Elemente, etwa ein Import aus Nastran) hat keine
Netzknoten — seine Knoten sind die Konstruktion.

**Netz → Netzqualität…** bewertet die **Form** jedes Elements und färbt die
Ansicht danach ein: grün gut, rot schlecht. Ein FE-Ergebnis ist nur so gut
wie das Netz - lang gezogene und flache Elemente machen vor allem die
Spannungen an dieser Stelle unbrauchbar.

| Maß | Bedeutung | 1 bedeutet |
|---|---|---|
| Formgüte | wie nah das Element an seiner regelmäßigen Gestalt ist | regelmäßiger Tetraeder, Würfel, Quadrat, gleichseitiges Dreieck |
| Seitenverhältnis | kürzeste durch längste Kante | alle Kanten gleich lang |
| Längste Kante [m] | die Elementgröße | – |

Die Maske nennt, wie viele Elemente bewertet wurden, min / Mittel / max, die
Verteilung auf die Stufen (sehr gut, gut, brauchbar, schlecht, unbrauchbar),
die Zahl der **Splitter** (Formgüte unter 0,10) und der **umgestülpten**
Elemente (negative Jacobi-Determinante - die rechnen falsch). Dieselben
Kennwerte und die zwanzig schlechtesten Elemente stehen im Protokoll.
**Schlechte wählen** markiert alle Elemente unter der eingestellten Grenze in
der Ansicht, **Aus** nimmt die Einfärbung wieder weg. Stäbe, Federn und
Grenzschichten haben keine Form in diesem Sinn und bleiben grau.

**Speichern und Öffnen** zeigen ebenfalls einen Fortschrittsbalken mit
Prozentzahl und Laufzeit: „Modell speichern: Drehlager.json …“ mit den
Schritten Knoten, Elemente, Lastfälle und dem Schreiben der Datei; beim
Öffnen zusätzlich, wie viel der Datei schon gelesen ist („Datei lesen (120
von 380 MB)“). Ein Modell mit hunderttausend Knoten braucht dafür Minuten -
abbrechen lässt sich das nicht, eine halb geschriebene Datei wäre unbrauchbar.
Nach dem Lesen steht „Daten auswerten - das kann bei großen Dateien Minuten
dauern, das Fenster antwortet solange nicht“: in diesem Schritt wird die
Datei in einem Zug ausgewertet, er meldet nichts zwischendurch, und der
Balken steht darum still. Das ist kein Absturz; der Text wird vor dem Schritt
gezeichnet und bleibt, bis die Knoten aufgebaut werden.

Die **Netzvorschau** (Schätzung der Elementzahl vor dem Vernetzen, im Ribbon
und in der Maske) gibt es seit 13.09.2026 nicht mehr: sie rechnete mit
A/h² bzw. V/(0,12·h³) und kannte weder die örtliche Verfeinerung an
Bohrungen noch die Nachvernetzung — am Drehlager schätzte sie 76 640
Tetraeder, das fertige Netz hat 1 812 359, je Körper im Median um den
Faktor 758 daneben. Eine Zahl, die um drei Größenordnungen daneben liegt,
ist keine Auskunft. Verlässlich wäre allein eine Vorschau über die
Randhülle (gemessen über alle 108 Körper: 3,1 Tetraeder je Randdreieck,
10–90 %: 2,7–4,8), die je Körper die Hülle rechnen müsste — ein bis zwei
Minuten am Drehlager; sie ist als Folgearbeit vermerkt. Das Protokoll nennt
beim Vernetzen je Objekt die gewählte Elementgröße und ihren Grund, und
nach dem Vernetzen steht die Elementzahl je Objekt im Modellbaum.

Beim Vernetzen zeigt die Statuszeile einen **Fortschrittsbalken** mit
Laufzeit („Vernetze Fläche 120 von 1375: …“, „Vernetze Volumen (108): 12 von
108 fertig, 5 in Arbeit auf 3 Prozessen (V30, V14, …)“). Der Balken ist nach
der **geschätzten Elementzahl** gewichtet, nicht nach Objekten: 1375 Flächen
sind in Sekunden fertig, ein Lagerbock allein braucht Minuten - der Balken
zeigt darum die wirkliche Arbeit, und Zeit und Text laufen auch mitten in
einem großen Volumen im Sekundentakt mit (Randhülle, Tetraedern mit
Verfeinerungsdurchgang, Splitter glätten, Randtreue).

Die **Volumen laufen parallel**: alle Kerne bis auf einen rechnen in
Arbeitsprozessen (der letzte bleibt der Oberfläche, die dabei bedienbar
bleibt), gedeckelt durch *Berechnung → Einstellungen → Prozesse*. Die großen
Körper starten zuerst, damit am Ende nicht ein Prozess allein auf den
Lagerbock wartet; der Einbau ins Modell geschieht in der Reihenfolge des
Fertigwerdens, das Netz ist dasselbe wie nacheinander. **Abbrechen** (Knopf
neben dem Balken oder Esc) wirkt sofort - auch mitten in einem Volumen; die
Arbeitsprozesse werden beendet, das bisher Erzeugte bleibt, die übrigen
Objekte bleiben ohne Netz, das Protokoll sagt es.

#### Der freie Vernetzer

Ein Lagerbock, ein Augenblech mit Bohrung, eine Buchse — nichts davon ist ein
Sechsflächner. Solche Körper vernetzt Statik3D **frei** in Tetraeder. Die
angestrebte Kantenlänge kommt aus den Netzeinstellungen (bei einem RFEM-Import
aus dessen `mesh.xml`); ist sie für ein Bauteil zu grob — weniger als vier
Elemente über seine größte Ausdehnung —, wird sie für dieses Bauteil
verkleinert und das im Protokoll gesagt.

Das Netz folgt der Geometrie: Bohrungen bleiben ausgespart, krumme Flächen
werden auf ihrer wahren Krümmung vernetzt, und um eine kleine Bohrung in einer
großen Platte wird das Netz von selbst feiner, ohne dass die ganze Platte fein
wird. Zwei Körper, die **dieselbe** Randfläche haben, teilen sich dort die
Knoten und hängen zusammen; zwei Flächen, die nur aufeinander liegen, aber
verschiedene Objekte sind, bleiben getrennt — das ist eine Kontaktfuge und
keine Schweißnaht.

Nach jedem Körper steht im Protokoll, was herausgekommen ist:

    Volumen V34: 75437 Tetraeder aus 9174 Randdreiecken (Kantenlänge 50 mm, 14512 Knoten)
      Volumen 0.100611 m^3 gegen 0.100602 m^3 aus der Hülle (Abweichung 0.009 %),
      Güte min 0.005 / Mittel 0.685, Randtreue 99.96 % (größter Abstand zur Hülle 18.01 mm)

**Lineare oder quadratische Elemente.** In den Netzeinstellungen steht die
*Ordnung*: 1 gibt lineare Tetraeder (tet4), 2 quadratische (tet10). Der lineare
hat eine konstante Dehnung und ist unter Biegung deutlich zu steif — bei einem
Kragträger mit 100 mm Kantenlänge kommt er auf 69 % der Balkenlösung, der
quadratische mit demselben Netz auf 99 %. Er kostet dafür mehr Knoten. Für
Spannungsnachweise an Kerben, Augen und Bohrungen gehören die quadratischen
genommen.

**Splitter** — fast flache Elemente — werden herausgeglättet: die *freien*
Knoten wandern so, dass die schlechteste Güte steigt; die Randknoten bleiben,
wo sie sind, damit sich das Volumen nicht ändert. Die Schwelle steht ebenfalls
in den Netzeinstellungen.

Das ist keine Zierde, sondern die Probe: das **Volumen** des Netzes gegen das
Volumen der Randhülle (Gaußscher Satz), die **Güte** der Elemente (1 = regulärer
Tetraeder, 0 = flach) und die **Randtreue** — wieviel des Netzrandes wirklich
auf der Geometrie liegt. Ist die Randhülle nicht dicht, wird gar nicht
vernetzt: ein Netz aus einer undichten Hülle wäre stillschweigend falsch.

**Nachverfeinerung der Hülle ohne Splitter.** Wo der Netzrand nach dem
ersten Durchgang neben der Geometrie liegt (einspringende Ecken, der
Übergang vom feinen Bohrungsring ins grobe Feld), werden die Hülldreiecke
dort feiner gemacht und noch einmal tetraedert. Bis September 2026 wurden
sie dazu im Schwerpunkt geteilt (1 → 3): das hält die Geometrie, macht die
Dreiecke aber mit jeder Runde flacher, denn das Kind behält die lange Kante
und bekommt ein Drittel der Höhe. An V15 des Drehlagers (Hülle 11 824
Dreiecke, Güte min 0,165, kein Splitter) entstanden so in zwei Runden 2 391
Splitterdreiecke (Güte < 0,1, min 0,018), auf der Außenhaut blieben 82, und
daran hingen die Tetraeder mit Güte 0,028, die die Abnahme bemängelte —
„merkwürdige Dreiecke" auf der Fläche neben der Bohrung. Jetzt wird die
**längste Kante halbiert** (Rivara): der neue Punkt ist die Kantenmitte, der
Nachbar über die Kante wird mit halbiert (ist die Kante nicht auch seine
längste, wird erst er halbiert — die Fortpflanzung endet, weil die Kanten
längs des Weges länger werden), und der kleinste Winkel bleibt mindestens die
Hälfte des Ausgangswinkels. Kanten zu einer **gemeinsamen Fläche** oder auf
einer **gemeinsamen Linie** werden nicht geteilt, sonst hinge der neue Knoten
beim Nachbarkörper in der Luft; ist die längste Kante so gesperrt, bleibt
für dieses Dreieck die Teilung im Schwerpunkt. Ergebnis an V15: 1 statt 82
Splitterdreiecke auf der Außenhaut, schlechtester Tetraeder 0,051 statt
0,028, Randtreue 100 % statt 97,6 % (293 000 statt 255 000 Tetraeder,
56 s). Geprüft in `tests/test_mesher3d.py`
(`test_huelle_verfeinern_haelt_form`: Platte mit Bohrung, drei Runden —
Hülle dicht, Volumen unverändert, kein Splitter, geschützter Boden und
gesperrter Deckelring unangetastet; im Schwerpunkt geteilt fiele die Güte
auf 0,029).

**Lasten, die an der Geometrie hängen.** RFEM hängt seine Flächenlasten an die
*Fläche*, nicht an Elemente — beim Import gibt es die Elemente noch gar nicht.
Solche Lasten fallen jetzt nicht mehr unter den Tisch: sie bleiben als
**Geometrielast** am Objekt und werden beim Vernetzen auf die entstandenen
Elemente verteilt. Auf der Randfläche eines Volumenkörpers gibt es keine
Schalenelemente — dort merkt sich das Programm, mit welcher Seite jeder
Tetraeder anliegt, und legt die Last auf diese Seiten. Aus dem Beispielmodell
kommen so 711 Flächenlasten, die vorher verloren gingen.

„Netz löschen" nimmt die Elemente wieder weg, die Geometrie bleibt stehen.
Eine Fläche, die noch einen Volumenkörper berandet, lässt sich nicht löschen —
das Programm sagt, welcher es ist.

**Netz ändern bei vorhandenen Ergebnissen.** *Vernetzen*, *Netz löschen* und
*Kontaktfugen ausführen* fragen, wenn Ergebnisse vorliegen: die Ergebnisse
gehören zum bisherigen Netz und würden durch die Änderung gelöscht — die
Rückfrage „Netz ändern“ nennt ihre Zahl und bietet den Knopf der Aktion
(*Vernetzen*, *Netz löschen*, *Ausführen*) und **Abbrechen**. Abbrechen
lässt Netz und Ergebnisse stehen; bei Zustimmung werden die Ergebnisse
verworfen (Protokollzeile) und das Netz erneuert. Ohne Ergebnisse wird
nicht gefragt. Geprüft in `tests/test_gui_smoke.py`.

### Vernetzer und Nachbesserer nachladen

gmsh, Netgen, MMG3D und der Gleichungslöser MUMPS kommen nicht mit dem
Programm (Lizenzen, nächster Abschnitt). *Extras → Vernetzer installieren…*
oder der Knopf **Vernetzer installieren…** unter den Netzeinstellungen
öffnet den Dialog **Vernetzer, Nachbesserer und Gleichungslöser**: je
Werkzeug Aufgabe, Lizenz, Quelle und Stand, dazu **Installieren** bzw.
**Entfernen**. Installieren lädt das
Werkzeug von seiner Quelle in die Benutzerdaten
(`%LOCALAPPDATA%\Statik3D\Werkzeuge`, unter Linux
`~/.local/share/Statik3D/Werkzeuge`; **Ordner öffnen** zeigt ihn) — nicht
neben die exe, darum überlebt es ein Programm-Update. Der Download läuft
im Hintergrund mit Balken; danach prüft das Programm das Werkzeug (Modul
laden bzw. `mmg3d_O3 -h`), trägt es in die Auswahl der Netzeinstellungen
ein und baut eine offene Maske neu auf. Schlägt die Prüfung fehl, wird das
Werkzeug wieder entfernt und der Grund gemeldet.

Quellen und Größen (gemessen 13.09.2026, Windows, Python 3.11):

| Werkzeug | Quelle | Download | auf der Platte | Dauer |
|---|---|---|---|---|
| gmsh 4.15.2 | PyPI, Rad `gmsh` (py2.py3, win_amd64) | 42 MB | 146 MB | 5 s |
| Netgen 6.2.2607 | PyPI, Räder `netgen-mesher` (cp311) und `netgen-occt` | 8 + 19 MB | 78 MB | 6 s |
| MMG3D 5.8.0 | Release `werkzeuge` dieses Projekts, `mmg3d_O3-windows-x64.zip` — gebaut aus MmgTools/mmg durch `.github/workflows/werkzeuge.yml` (MSVC, ohne Scotch und VTK; LICENSE und COPYING.LESSER liegen bei) | 0,4 MB | 0,7 MB | unter 1 s |
| MUMPS 5.8.2 | Release `werkzeuge`, Rad `mumps-5.8.2-py3-none-win_amd64.whl` aus `packaging/` (eigener Windows-Bau, `docs/MUMPS_Windows_Bauanleitung.md`; der Workflow legt es ab, nachdem er die Prüfsumme gegen die im Programm hinterlegte verglichen hat) | 18 MB | 53 MB | 2 s |

MUMPS ist der Sonderfall: das Rad kommt aus unserem eigenen Release, darum
ist seine **SHA-256-Prüfsumme im Programm hinterlegt** und Pflicht — ein
Rad mit anderer Prüfsumme wird abgelehnt und aufgeräumt. Nach dem Entpacken
rechnet das Programm ein Fünf-Unbekannten-System (Lösung 1 2 3 4 5), denn
die DLLs kommen erst beim ersten Kontext; ein bloßer Import sagt nichts.
Ist das Kästchen **MUMPS beim Programmstart nachladen, wenn es fehlt** an
(Vorgabe), holt das Programm MUMPS einige Sekunden nach dem Start ohne
Rückfrage: Balken in der Statuszeile, danach eine Protokollzeile („MUMPS
5.8.2 nachgeladen (18 MB, … s) — Berechnung → Einstellungen →
Gleichungslöser“). Schlägt es fehl (kein Netz, Prüfsumme), steht das als
eine Zeile im Protokoll, und der nächste Start versucht es erneut; im Dialog
bleibt **Installieren**. Ein neuer Bau (andere Prüfsumme im Programm)
wird beim Start ebenso nachgeladen. Eine eigene Python-Umgebung, in der das
Rad installiert ist, gilt als „vorhanden“ — dann lädt der Start nichts. Die
Löserauswahl unter *Berechnung → Einstellungen* wird nach dem Nachladen
sofort neu aufgebaut: bis 13.09.2026 entstand sie beim Start, bevor MUMPS
da war, und zeigte es bis zum Neustart als „nicht installiert“.
Geprüft in `tests/test_werkzeuge.py` (das echte Rad aus `packaging/` über
die lokale Quelle `STATIK3D_WERKZEUG_QUELLE`: entpacken, im eigenen Prozess
rechnen, falsche Prüfsumme abgelehnt, Entfernen bei geladener DLL) und
`tests/test_gui_smoke.py` (Kästchen, Nachladen mit Balken und Protokollzeile).

Die Räder werden **ohne pip** entpackt (die exe hat keins): Python-Dateien
nach `Lib/site-packages`, Datenanteile wie bei pip relativ dazu
(`gmsh-4.15.dll` nach `Lib`, die OCC-Bibliotheken von Netgen nach `bin`),
und RECORD wird passend geschrieben, weil Netgen seine OCC-Bibliotheken
über `importlib.metadata` sucht. Das Rad wird nach Python-Version (cp311
bzw. py3), System und Prozessor gewählt, die Prüfsumme (SHA-256 laut PyPI)
verglichen. Der Werkzeugordner steht hinten im Suchpfad — eine eigene
Python-Umgebung mit demselben Paket geht vor. War das Modul im laufenden
Programm schon geladen (etwa eine ältere Fassung), wirkt die neue erst
nach dem Neustart; der Dialog sagt es. **Entfernen** löscht den Ordner;
sind Dateien noch in Gebrauch (geladene DLL), verschwindet der Rest beim
nächsten Start. Geprüft in `tests/test_werkzeuge.py` (Radwahl, Entpacken
und RECORD, Installieren mit ausgetauschter Quelle, Prüfsumme, gescheiterte
Prüfung, Entfernen bei gesperrter Datei — ohne Netz; mit
`STATIK3D_NETZTEST=1` echt von PyPI, beide vernetzen danach den
Einheitswürfel aus dem Werkzeugordner) und `tests/test_gui_smoke.py`
(Dialog, Knopf, Ribbon, Installieren im Hintergrund, Entfernen).

### Lizenzen der Rechenwerkzeuge

Statik3D selbst und sein Vernetzer sind eigener Quelltext. Für fremde
Werkzeuge gilt (Stand 13.09.2026):

| Werkzeug | Lizenz | in der exe? |
|---|---|---|
| MKL PARDISO (pypardiso, oneMKL) | Intel Simplified Software License — frei nutzbar und weitergebbar, nicht quelloffen | ja (Vorgabe) |
| SuperLU (scipy) | BSD | ja |
| PyAMG | MIT | ja |
| CHOLMOD (scikit-sparse) | LGPL, das Supernodal-Modul GPL | nein — nur aus der eigenen Python-Umgebung |
| UMFPACK (scikit-umfpack) | GPL | nein — nur aus der eigenen Python-Umgebung |
| MUMPS 5.8.2 (Paket `mumps`, eigener Windows-Bau) | CeCILL-C — LGPL-artig: die Bibliothek bleibt unverändert ein eigenes Modul, Lizenztext und Urheberhinweis liegen im nachgeladenen Paket unter `mumps/LIZENZ` (Art. 5.3.1 und 6.4), das Info-Fenster nennt sie | nein — wird beim ersten Start nachgeladen (Release `werkzeuge`, Kästchen im Dialog *Vernetzer, Nachbesserer und Gleichungslöser*; Bau und Messung in `docs/MUMPS_Windows_Bauanleitung.md`) |
| gmsh | GPL | nein — auf Wunsch nachladbar von PyPI (*Extras → Vernetzer installieren…*) oder `pip install gmsh` in der eigenen Umgebung |
| Netgen (netgen-mesher) | LGPL | nein — auf Wunsch nachladbar von PyPI oder `pip install netgen-mesher` |
| MMG3D | LGPL | nein — getrenntes Programm, auf Wunsch nachladbar aus dem Release `werkzeuge` (dort aus dem Quelltext gebaut, Lizenz liegt bei) |

Die GPL verpflichtet den, der ein Programm **zusammen mit** GPL-Software
weitergibt; darum enthält die exe keine davon. Wer gmsh, Netgen oder MMG3D
nutzen will, lädt sie selbst nach (voriger Abschnitt) — das Programm holt
sie von ihrer Quelle in die Benutzerdaten, und es gelten die Lizenzen der
Werkzeuge; GPL-Löser (CHOLMOD, UMFPACK) kommen weiter nur aus der eigenen
Python-Umgebung (`python run_gui.py`). Das Programm meldet in der Auswahl,
was da ist.

### Statuszeile: Fortschrittsbalken und Abbrechen

Unten rechts in der Statuszeile sitzt **ein** Fortschrittsbalken für alles,
was länger als einen Augenblick dauert, und daneben - wo Anhalten sinnvoll
ist - der Knopf **Abbrechen** (gleichwertig: **Esc**, gleich welches Feld den
Fokus hat; Esc ist das Kürzel von „Alles deselektieren“ und hält, solange der
Knopf zu sehen ist, stattdessen das Laufende an). Der Text links davon nennt den Schritt, den Anteil und die
Laufzeit („Berechnung: Lastfall W (5/12) (48 %, 73 s)“). Ein *bestimmter*
Balken zeigt Prozent; wo das Programm den Anteil noch nicht kennt, läuft ein
Streifen, bis der erste Schritt gemeldet ist.

| Aktion | Balken | Abbrechen |
|---|---|---|
| Modell öffnen, speichern | bestimmt: Datei lesen, Daten auswerten, Knoten, Elemente, Lastfälle, übriges Modell | nein - eine halbe Datei wäre keine |
| Importieren (Datei → Übernehmen) | bestimmt; RFEM 6: Behälter, Knoten, Linien, Stäbe, Lager, Flächen, Volumen, Freigaben, Lastfälle, Lasten, Kombinationen, Prüfung; andere Formate: Lesen und Nachbereitung; danach Stäbe erkennen, Ansicht aufbauen | nein |
| Vernetzen | bestimmt, nach geschätzter Elementzahl gewichtet, Zeit im Sekundentakt | ja, sofort - das bisher Erzeugte bleibt, die übrigen Objekte bleiben ohne Netz |
| Lastgenerierer Wind, Wasserdruck | bestimmt (Strömungsberechnung) | ja - das Modell bleibt unverändert |
| Berechnen (alle Lastfälle, Lastfall, Eigenschwingungen, Knicken), Knicklängen | Streifen bis zum ersten Schritt, dann bestimmt: aufstellen, faktorisieren, Lastfälle, Kontakt-Iteration, Kombinationen, Umhüllende, Nachweise | ja - beim nächsten Rechenschritt |
| Nachweise EC3, Ermüdung (allein gestartet) | bestimmt je Stab | ja |
| Freie Bewegungen | Streifen (die Suche kennt keinen Anteil) | ja |
| Bericht, Lastenheft | bestimmt je Kapitel, dann Ausgabe und Schreiben der Datei | nein |
| Modellprüfung, Kerbfälle vorschlagen, Netz löschen, Beispiel laden | kein Balken - Sekunden | – |

**Abbrechen einer Berechnung** wirkt kooperativ: die Statuszeile sagt
„Abbruch angefordert - die Rechnung hält beim nächsten Rechenschritt an“,
und genau das geschieht. Eine laufende Faktorisierung lässt sich nicht
unterbrechen, sie läuft zu Ende (am Drehlager mit 1 028 724 Freiheitsgraden
bis 13 s); die nächste Meldung des Rechenkerns (Lastfall, Kontakt-Iteration,
Kombination) ist dann der Ausstieg. Danach steht in Statuszeile und Protokoll
„Berechnung abgebrochen (nach x s)“ - keine FEHLER-Zeile, denn es ist keiner.
Das Netz bleibt unverändert, Berechnen und Update sind sofort wieder frei.
Beim Vernetzen bleibt das bisher Erzeugte, bei Wind und Wasserdruck ist das
Modell wie vorher.

**Was gerechnet war, bleibt** (19.09.2026). Wer „Alle Lastfälle und
Kombinationen“ startet und nach dem ersten Lastfall abbricht, hat diesen
Lastfall gerechnet - bis dahin war er trotzdem weg, denn der Abbruch räumte
den ganzen Lauf ab („ich hatte aus Versehen alle Lastfälle und Kombinationen
zur Berechnung gestartet … es wäre gut wenn gerechnete Ergebnisse erhalten
blieben“). Jetzt stehen die fertigen Lastfälle und Kombinationen nach dem
Abbruch in der Ergebnisauswahl und im Modellbaum wie nach einem ganzen Lauf.
Die Statuszeile sagt, was blieb und was offen ist: „Berechnung abgebrochen
(nach 94 s) - 1 Lastfälle bleiben erhalten, 4 Lastfälle und 72 Kombinationen
offen“. Zwei Dinge fehlen ausdrücklich, und das Protokoll sagt es:

* **Keine Umhüllenden.** Eine Umhüllende über zwei von fünf Lastfällen sieht
  aus wie eine über alle fünf und wäre schlicht falsch.
* **Keine Nachweise.** Sie stützen sich auf die Umhüllenden.

Ein neuer Lauf rechnet alles noch einmal - das Teilergebnis ist zum Ansehen
da, nicht als Zwischenstand, auf dem weitergerechnet wird. Bricht es ab,
bevor der erste Lastfall fertig ist, bleibt es beim alten Verhalten: es gibt
nichts zu zeigen, und das vorherige Ergebnis bleibt stehen.

Das Teilergebnis tritt an die Stelle des bisherigen. War das größer, sagt das
Protokoll es ausdrücklich: „Das bisherige Ergebnis (5 Lastfälle, 72
Kombinationen) ist damit ersetzt - es lässt sich nur durch einen neuen Lauf
zurückholen.“ So tauscht ein versehentlich gestarteter und abgebrochener Lauf
keine ganze Rechnung still gegen einen Lastfall.

Damit ein Abbruch in den Kombinationen überhaupt greifen kann, meldet seit
demselben Stand auch der lineare Weg jede Kombination einzeln
(„Kombination GZT-12 (37/422)“). Vorher stand der Balken dort still, bis alle
fertig waren - bei 422 Kombinationen minutenlang - und ein Klick auf
Abbrechen fand keinen Haltepunkt.

### Die Rechenliste: jeder Lastfall mit Zeit, Schritten und Konvergenz

Beim Start von **Berechnen** öffnet sich neben dem Hauptfenster die
**Rechenliste** - eine Zeile je Posten, den dieser Lauf abarbeitet. Bei
„Alle Lastfälle und Kombinationen“ stehen dort erst alle Lastfälle, dann alle
Kombinationen, in der Reihenfolge, in der gerechnet wird; bei „Lastfall“ nur
der aktive. Für Eigenschwingungen und Knicken bleibt sie zu - das ist ein
einziger Lauf, und der Balken in der Statuszeile sagt darüber alles.

Der Anlass: bei 422 Lastfällen sagt ein Balken wenig. Ein warmer Lastfall des
Drehlagers braucht 343 s, 46 Kontakt- und 19 Plastizitätsschritte (gemessen
20.09.2026) - wer wissen will, ob es vorangeht, will die Zahlen sehen, nicht
einen Streifen.

| Spalte | Was darin steht |
|---|---|
| Posten | Name des Lastfalls oder der Kombination |
| Art | Lastfall oder Kombination |
| Zustand | offen, läuft, fertig - und, sobald der Rechenkern es meldet, „läuft (konvergiert)“ bzw. „läuft (nicht konvergiert)“ |
| Schritte | „Kontakt 12 · Plast. 5 (Stufe 2/3)“ - die Zähler der laufenden Iterationen |
| Konvergenz | die zuletzt gemessene Zahl: „Δu 3.2e-05“ der Kontakt-Iteration, „Änderung 8.13e-07“ der Plastizität |
| Zeit | Laufzeit des Postens, im Halbsekundentakt; nach dem Abschluss seine Gesamtzeit |
| Meldung | die letzte Zeile des Rechenkerns im Klartext |

Über der Liste steht, **womit** gerechnet wird: der Prozesspool (Element-
schleifen und Vernetzen) und der Gleichungslöser. Ist die **Rechnerfarm**
eingeschaltet (Kapitel 9 und `docs/Rechnerfarm.md`), kommt ihr Stand alle
zwei Sekunden dazu: „3 von 4 Rechnern aktiv, 18 Aufträge wartend, 141
erledigt“. Nur Rechner, die sich in den letzten 30 s gemeldet haben, zählen
als aktiv - so fällt ein ausgefallener Rechner auf. Bricht die Verbindung zur
Farm ab, sagt die Zeile das; die Rechnung selbst läuft weiter.

Die Liste **folgt** dem gerade rechnenden Posten. Scrollt man selbst, bleibt
sie stehen - sonst ruckt sie beim Lesen unter dem Finger weg. Der Knopf **Dem
Laufenden folgen** springt zurück und schaltet das Folgen wieder ein. Das
Fenster ist nicht modal: das übrige Programm bleibt bedienbar, während
gerechnet wird.

**Abbrechen** in der Rechenliste ist derselbe Weg wie der Knopf in der
Statuszeile: die Rechnung hält beim nächsten Rechenschritt an, eine laufende
Faktorisierung läuft zu Ende, und was gerechnet war, bleibt (siehe oben). Der
Posten, der dabei lief, steht danach auf „abgebrochen“.

Hinter dem letzten Posten läuft noch der Nachlauf - Umhüllende und Nachweise.
Solange steht er in der Fußzeile des Fensters („Kombination 54 von 54 -
Umhüllende GZT-12: 3/7“), damit die Liste dabei nicht wie eingefroren
aussieht.

### Ergebnisse und Bericht

Was gerechnet wurde, steht im **Modellbaum unter „Ergebnisse"**: Umhüllende,
Kombinationen, Lastfälle, die **Schnittgrößen**, die Nachweise, Eigenformen und
Knickfiguren. Ein Klick stellt das Ergebnis in der Ansicht ein — dieselbe
Auswahl, die auch die Maske *Ergebnisse* rechts führt. Dort werden Färbung,
Schnittgrößenverlauf und Überhöhung eingestellt.

Der Zweig **Schnittgrößen** führt N, Vy, Vz, Mt, My und Mz, jede mit ihren
Grenzwerten daneben; ein Klick stellt den Verlauf in der Ansicht ein, „kein
Verlauf" blendet ihn wieder aus.

**Kennwerte im Bild.** Unten links in der Ansicht stehen die Zahlen des
**gewählten Ergebnisses** (seit 15.09.2026; vorher alles zugleich): zur Färbung
|u| die größte Verformung mit Knoten, zu ux, uy oder uz die kleinste und
größte Verformung dieser Richtung, zur Vergleichsspannung die größte mit
Knoten, zu einer Ausnutzung die größte mit ihrem Ort, zu einer
Spannungsgröße (Volumen, Flächen, Stäbe, Kontakt) ihr kleinster und größter
Wert mit Knoten in der Einheit der Farbskala. Steht ein Schnittgrößenverlauf
an, kommt diese Schnittgröße mit dem Stab dazu. Bei *keine Färbung* ohne
Verlauf bleibt die Ecke leer. Der Text gehört zum Bild und kommt darum mit in
den Bericht, wenn man die Ansicht übernimmt. Abschalten: *Ergebnisse →
Kennwerte im Bild*.

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
| Voll | Strg+1 | gefüllte Flächen, farbig; Stäbe als Körper mit ihrer Querschnittskontur |
| Transparent | Strg+2 | durchscheinend — man sieht die innen liegenden Teile; Stäbe als Körper |
| Hidden-Line | Strg+3 | weiße Flächen mit dunklen Kanten, wie eine Zeichnung; Stäbe als Linien |
| Drahtmodell | Strg+4 | nur die Kanten; Stäbe als Linien |

Die vier Arten gelten auch für **Stäbe**: bei Voll und Transparent wird jeder
Stab mit seinem Querschnitt über die Stablänge gezeichnet (ein IPE als
I-Profil, ein Rohr als Rohr, mit dem Drehwinkel des Stabes), bei Hidden-Line
und Drahtmodell als Linie. Ergebnisfarben liegen auf dem Stabkörper genauso
wie auf dem Netz.

Die Darstellungsart gilt ebenso für **Flächen und Volumen ohne Netz** (die
Geometrie eines RFEM-Modells vor dem Vernetzen): Voll deckend, Transparent
durchscheinend, Hidden-Line weiß mit dunklen Randlinien, Drahtmodell nur die
Randlinien der Flächen. Die Dreiecke, aus denen eine gewölbte Fläche
gezeichnet wird, sind kein Netz und werden nie als Kanten gezeigt.

**Krumme Flächen** — der Mantel einer Bohrung, einer Buchse, eines Bolzens,
in RFEM eine Fläche aus zwei Bögen und zwei Geraden — werden als gewölbte
Fläche zwischen ihren vier Randlinien gezeichnet (Coons-Fläche). Vorher
fehlten sie im Bild, weil ihr Rand nicht in einer Ebene liegt, und die
Volumen wirkten offen. Ist eine der Geraden in der Quelldatei in **zwei
Linien geteilt**, hat die Fläche fünf Randseiten; sie werden an der glatten
Ecke wieder zusammengefasst, denn geometrisch ist es eine Vierseitfläche.
Ohne das würde sie als Fächer um ihren Schwerpunkt gezeichnet, und dessen
Dreiecke laufen bei einem Halbkreis quer durch das Bauteil — am geprüften
Drehlagermodell betraf das die vier Bolzenmäntel, gezeichnet mit 2011 statt
645 cm².

**Wo ein Netz steht, wird das Netz gezeichnet.** Die Randflächen eines
vernetzten Volumenkörpers werden nicht mehr zusätzlich als Geometrie darüber
gemalt: beide liegen aufeinander, und um jeden Bildpunkt stritten dann zwei
Dreiecke. Ihre **Umrisse** bleiben — sie zeigen als Linien über dem Netz, wo
die Bauteilkanten laufen. Ein Klick trifft damit das Netz; welche Fläche
darunter liegt, ermittelt das Programm beim Klick, so dass die Auswahlart
„Fläche" unverändert arbeitet.

**Kanten gewinnen gegen die Fläche, auf der sie liegen.** Eine Bauteilkante
ist zweimal im Bild: als Rand der Fläche **und** als Linie des Modells. Beide
liegen auf demselben Fleck im Tiefenspeicher der Grafikkarte, und ohne Regel
entscheidet dort die Rundung — Bildpunkt für Bildpunkt —, welche von beiden
gewinnt. In der gefüllten Ansicht franste das die Umrisse aus und ließ sie
stellenweise ganz verschwinden: Bohrungen, Rippen und Blechkanten waren nicht
zu sehen, obwohl sie gezeichnet wurden. Im Drahtmodell fiel es nicht auf —
dort gibt es keine Fläche, gegen die eine Linie verlieren könnte. Jetzt
rücken die Flächen um Bruchteile einer Tiefenstufe nach hinten und die Linien
nach vorn; am Drehlagermodell kamen damit **46 % der Körperkanten zurück**,
die die gefüllte Ansicht verschluckt hatte.

**F9** blendet das **FE-Netz** (die Elementkanten) ein und aus. Der Schalter
„Knoten" zeigt die **Knoten der Konstruktion** als Punkte: Linienknoten,
Stabenden, frei gesetzte Knoten und die Knoten direkt gesetzter Elemente.
Knoten, an denen noch **kein Element** hängt, sind orange und etwas größer —
so sieht man beim Modellieren, wo man schon war, auch wenn dort noch nichts
steht. Die **Netzknoten** — die Knoten, die das Vernetzen einer Fläche,
eines Körpers oder eines geteilten Stabzugs erzeugt — gehören zum Netz und
werden hier nicht gezeigt (seit 13.09.2026; vorher standen am Drehlager
380 000 Netzkugeln im Bild). Sie schaltet *Netz → Netzknoten* zu: kleine
graue Punkte, solange das FE-Netz dargestellt ist. Die **Knotennummern**
folgen dem: nummeriert wird, was gezeichnet ist. Geprüft in
`tests/test_gui_smoke.py` (vernetzte Platte mit fünf gesetzten Knoten: 5
Konstruktionsknoten, alle übrigen Netzknoten).

**Flächenlasten** sind seit 13.09.2026 als Fläche erkennbar: zu den
Pfeilen kommt eine durchscheinende **Lastfläche** an den Pfeilenden —
je belastetem Vieleck der Fläche bzw. je belasteter Elementseite eines,
in Lastrichtung um die Pfeillänge versetzt („aktuell sehen die aus wie
einzelne Knotenlasten“). Sie folgt dem Schalter *Lasten*. Geprüft in
`tests/test_gui_smoke.py`.

**Ergebnisse zeigen** (Register *Ergebnisse*, seit 14.09.2026) nimmt die
ganze Ergebnisdarstellung aus dem Bild: Färbung, verformtes System, Werte,
Kontaktmarken, Skala und Kopfzeile. Zurück bleibt das Modell, wie es vor der
Rechnung aussah; die Ergebnisse bleiben gerechnet und kommen mit demselben
Schalter zurück. Die Kopfzeile sagt, dass sie ausgeblendet sind. Für die
Färbung allein gibt es weiterhin den Eintrag *keine Färbung* in der Liste.

Die Elementkanten des FE-Netzes sind **1 px** breit. Bis 13.09.2026 waren
es 3 px: die Breite, die ein Stab als Linie bekommt, galt für das ganze
Gitter, und im Bild maßen die Kanten eines Schalen- oder Tetraedernetzes
3–4 px („die Liniendicke des Netzes ist zu dick“). Stäbe als Linien bleiben
3 px — in einem Modell mit Stäben **und** Flächen zeichnet das Programm die
Linien darum als eigenen Darsteller (`netz_linien`), ein reines Stabwerk
bleibt ein Gitter wie bisher. **Transparent** zeichnet Ergebnisse mit
Deckkraft 0,55 statt 0,35 (die Sättigung der Ergebnisfarben lag im
Quader-Beispiel bei 77 gegenüber 178 in Voll, mit 0,55 bei 104), und das
unverformte System liegt dann nur als Umriss darunter, nicht als graues
Drahtnetz — sonst verschwanden die Spannungen hinter Linien („im
Transparentmodus sehe ich keine Spannungen“). Geprüft in
`tests/test_gui_smoke.py`.

#### Nummern: je Objektart ein Schalter

Im Register *Ansicht* steht die Gruppe **Nummern** — ein Schalter je Objektart,
jeder für sich:

| Schalter | zeigt | Farbe |
|---|---|---|
| Knotennummern | die Nummer an jedem Knoten | dunkelgrau |
| Liniennummern | den Namen an jeder Linie, auf der Linie (bei einem Bogen auf der Kurve, nicht auf der Sehne) | blau |
| Stabnummern | den Namen an jedem Stab, in der Mitte seines mittleren Elements | grün |
| Flächennummern | den Namen an jeder Fläche | violett |
| Volumennummern | den Namen an jedem Volumenkörper, in seiner Mitte | petrol |
| Elementnummern | die Nummer an jedem finiten Element | orange |
| Lagernummern | die Nummer (oder den Namen) an jedem Knotenlager | rot |

Die benannten Objekte tragen ihren **Namen**, nicht eine laufende Nummer: in
der Ansicht steht damit dasselbe wie im Modellbaum und in den Tabellen.

Dieselben Schalter liegen im **Rechtsklickmenü der Ansicht** unter *Nummern*,
dort mit den kurzen Namen und mit **„Alle Nummern aus"** als einem Griff. So
lässt sich die Beschriftung beim Arbeiten umlegen, ohne das Register zu
wechseln.

Ausgeblendete Objekte bekommen **keine** Nummer, und was ein
Sichtbarkeitsschalter wegnimmt, auch nicht — eine Nummer ohne ihr Objekt wiese
ins Leere. Schaltet man die Volumen ab, verschwinden mit ihnen auch die
Nummern ihrer Elemente.

Jede Art hat eine **Obergrenze** (Knoten und Elemente 3000, die übrigen 2000).
Mehr Marken überdecken das Modell und bremsen die Ansicht; die Nummern bleiben
dann aus, und die Statuszeile sagt, wie viele es wären. Erst ausblenden, dann
bleiben die Nummern des Restes lesbar.

**Die Glasleiste** liegt mittig oben über der Ansicht, durchscheinend, und
trägt als Symbole die Griffe, die man beim Modellieren dauernd braucht — der
Klartext erscheint beim Überfahren mit der Maus. Von links nach rechts:

| Gruppe | Knöpfe |
|---|---|
| ganz links | **Aufklappliste Lastfall / Kombination** — was die Ansicht zeigt |
| Darstellung | Voll, Transparent, Hidden-Line, Drahtmodell |
| Sichtbarkeit | Knoten (der Konstruktion; Netzknoten: *Netz → Netzknoten*), Linien, Stäbe, Flächen, Volumen, **Lager**, FE-Netz, Lasten — jedes einzeln schaltbar |
| Sicht | Selektion anzeigen, Auswahl ausblenden, Vorherige Sicht, Alles zeigen, **Verborgenes im Hintergrund** (Schalter), **Schnittebene** (Schalter mit Achse und Schieber), **Intelligente Auswahl** (Schalter) |
| Layer | **Aufklappliste** (einen Layer allein zeigen, „Alle Layer“), **Layerliste** (Fenster: sichtbar und gesperrt je Layer, neu aus der Auswahl, Objekte wählen), **Layer aus Auswahl** — seit 16.09.2026 |
| Fang | Fang ein/aus (die Fangarten einzeln: Ribbon *Geometrie → Arbeitsebene*) |
| Auswahlart | was ein Klick trifft, als Knöpfe: Knoten, Linie, Stab, Fläche, Volumen, **Netz** (einzelne Elemente), **Lager** (Knoten-, Linien- und Flächenlager), **Last** — genau einer ist gedrückt |
| ganz rechts | **Alles deselektieren** (✕, auch Esc) — der Griff, der jede Auswahl beendet |

**Lastfall und Kombination aus der Leiste.** Ganz links steht eine
Aufklappliste mit **jedem Lastfall und jeder Kombination**. Sie ist die
Angabe, die man beim Durchsehen am häufigsten wechselt; oben links im Bild
war sie bisher nur zu *lesen*. Ein Lastfall daraus wird der aktive — seine
Lasten stehen im Bild und die Lastentabelle unten zeigt ihn. Eine
Kombination hat erst nach der Berechnung etwas zu zeigen: liegt ein Ergebnis
vor, schaltet die Ergebnisliste mit um, sonst sagt das Protokoll, woran es
liegt. Umgekehrt zieht die Leiste nach, wenn das Ergebnis woanders gewählt
wird — beides zeigt immer dasselbe.

**Verborgenes im Hintergrund.** Der Schalter (Register *Ansicht → Sicht*,
auch in der Glasleiste) zeigt alles Ausgeblendete blass und durchscheinend
als „Geist“ hinter dem Modell: man sieht, wo das Versteckte liegt, und
arbeitet ungestört an dem, was normal dargestellt ist. Der Geist ist
**nicht wählbar** — weder mit der Maus noch im Auswahlfenster. Das ist die
allgemeine Regel der Ansicht: **Was nicht dargestellt ist, lässt sich nicht
wählen.** Ausgeblendete Objekte (Sicht) bleiben außen vor, ebenso alles,
dessen Schalter in der Glasleiste aus ist — mit ausgeschalteten Stäben
wählt weder ein Klick noch ein Fenster einen Stab, mit ausgeschalteten
Knoten keinen Knoten; die Statusleiste sagt dann, warum nichts geschieht.
Lager an ausgeblendeten Knoten und Lasten an ausgeblendeten Teilen sind
ebenso wenig zu treffen; mit ausgeschaltetem Schalter **Lager** (Glasleiste,
zwischen Volumen und FE-Netz; Ribbon *Ansicht → Anzeigen*) verschwinden alle
Knoten-, Linien- und Flächenlager aus dem Bild und sind nicht wählbar — am
Drehlager mit 50 Lagerflächen verdecken die Symbole sonst das Bauteil.

**Schnittebene — hineinsehen statt hineinzoomen.** Von einem Volumennetz wird
immer nur die **Außenhaut** gezeichnet: die inneren Tetraederflächen liegen
zwischen zwei Elementen und werden in keinem FE-Programm gezeichnet. Wer beim
Zoomen durch die Oberfläche fährt, blickt darum auf die Innenseite der
gegenüberliegenden Haut — das *sieht* hohl aus, ist es aber nicht. Ein
massiver Körper ist massiv gefüllt; am Drehlagermodell berühren allein in V31
30 499 der 35 686 Tetraeder die Oberfläche gar nicht.

Wer nachsehen will, schneidet auf: Schalter **Schnittebene** (*Ansicht →
Sicht*), daneben die Achse (x, y, z) und ein Schieber für die Lage im
Bauteil; **Andere Seite** lässt die andere Hälfte stehen. Im Schnitt stehen
die Tetraeder des Inneren, und Füllung, Netzdichte und Elementform sind mit
einem Blick zu prüfen. Ausgeschaltet steht das Bauteil wieder ganz da.

Die Achse **frei** schneidet an **beliebiger Stelle in beliebiger Richtung**:
rechts öffnet sich die Maske *Schnittebene* mit Normale und Ursprung. Statt
Zahlen einzutippen, kann die Ebene **aus der Ansicht** kommen (senkrecht zum
Blick, durch den Blickpunkt — nach dem Zoomen auf eine Bohrung liegt der
genau dort) oder **aus der Arbeitsebene**; mit **Ebene im Bild ziehen** steht
sie als Werkzeug in der Ansicht: der Pfeil dreht die Normale, die Fläche
lässt sich schieben, beim Loslassen wird neu geschnitten, und die Maske
zeigt die neuen Werte. Der Schieber im Ribbon verschiebt die freie Ebene
längs ihrer Normalen (Mitte = durch den Ursprung). Geschnitten wird immer
das, was gerade **gezeichnet** ist — mit Ergebnisfarben: im Schnitt stehen
die Spannungen und Verschiebungen auf den Elementen des Inneren, und
ausgeblendete Teile bleiben ausgeblendet. So lassen sich Ergebnisse im
Volumen an jeder Stelle ansehen, etwa der Spannungsverlauf durch die Wand
einer Bohrung. Geprüft in `tests/test_gui_smoke.py` (Abschnitt Schnittebene:
schräge Ebene durch die Mitte, aus der Ansicht, Werkzeug im Bild).

Es sind dieselben Befehle wie im Ribbon (*Ansicht → Anzeigen* und *Sicht*, der Fang unter *Geometrie → Arbeitsebene*),
nur näher an der Maus. „Alles ins Bild" steht im Ribbon unter *Blickrichtung*
und als **iso** unter dem Ansichtswürfel.

**Sicht — ausblenden und wieder zeigen.** Was man nicht sieht, stört nicht:
*Auswahl ausblenden* nimmt die gewählten Stäbe, Flächen, Volumen, Linien,
Knoten oder die Elemente an den gewählten Knoten aus dem Bild; *Selektion
anzeigen* blendet **alles andere** aus — ist nur ein Volumen gewählt,
verschwinden auch die Stäbe, Linien, Flächen und Knoten des Restmodells samt
ihren Lagern und Lasten. Knoten bleiben nur im Bild, wenn sie gewählt sind
oder an einem sichtbaren Teil hängen; die Netzknoten eines ausgeblendeten
Körpers gehen mit ihm. Beide Befehle heben die Auswahl danach auf — die
Aufgabe ist erledigt, das isolierte Teil leuchtet nicht weiter, und der
nächste Befehl wirkt nicht mehr auf die alte Auswahl (*Selektion anzeigen*
seit 15.09.2026). *Vorherige Sicht* nimmt den letzten Schritt
zurück (bis zu zwanzig Schritte), *Alles zeigen* holt alles wieder her. Die
Ausblendung ist nur eine Sicht — am Modell und an der Berechnung ändert sie
nichts. Ein neues Netz oder ein anderes Modell hebt sie auf. Ein
**Doppelklick mit der mittleren Maustaste** im Bild passt die Kamera auf
alles ein, was gerade zu sehen ist (wie *Zoom alles*); Ausgeblendetes zählt
dabei nicht mit. Er zählt beim Loslassen und nur ohne Ziehbewegung; hat das
Mausrad in den letzten 0,4 s gerollt, gilt er nicht — wer beim Zoomen das Rad
drückt, will nicht alles einpassen (16.09.2026).

**Während einer Rechnung öffnet das Programm kein Fenster.** Fehler,
Warnungen und Rückfragen gehen dann ins Protokoll und in die Statuszeile; eine
Rückfrage, die niemand sehen kann, gilt als verneint. Grund ist ein Absturz
vom 07.09.2026 in Qt selbst, beim **Aufbau** einer Meldungsbox — welches
Kindobjekt dort tot war, ließ sich ohne Symbole nicht klären, und solange das
offen ist, kommt aus dem Rechenpfad kein Dialog. Verloren geht dabei nichts:
das Protokoll lässt sich unter *Extras → Protokoll speichern…* als Datei
sichern.

**Der Ansichtswürfel** oben rechts dreht sich mit der Ansicht und lässt sich
**mit der Maus drehen**: auf den Würfel klicken und ziehen dreht die Kamera um
den Blickpunkt. Ein Klick auf eine Würfelseite stellt die Ansicht senkrecht
auf diese Seite. Die Knöpfe darunter heißen wie die Achsen: **+x +y +z −x
−y −z** (die Richtung, aus der man schaut) und **iso** (isometrisch, alles
im Bild).

**Texte im Bild.** Oben links steht, was die Ansicht zeigt: ohne Ergebnis der
aktive Lastfall mit seiner Lastzahl, mit Ergebnis der Lastfall, die
Kombination oder die Umhüllende samt Färbung, Schnittgrößenverlauf und
Überhöhung. Unten links stehen die **Kennwerte** des gewählten Ergebnisses
(Färbung und Schnittgrößenverlauf, siehe *Kennwerte im Bild*); Auflagerkräfte
stehen in der Tabelle *Auflagerkräfte*. Die Farbskalen stehen rechts, das
Achsenkreuz unten
rechts; der Schalter „Kennwerte im Bild" im Register *Ergebnisse* nimmt die
Texte weg. Beides kommt so auch in den Bericht.

**Drehen großer Modelle.** Ab etwa 20 000 Knoten und Elementen bleiben
während des Drehens, Schiebens und Zoomens die Nebendarsteller
(Knotenpunkte, Linien, Nummern, Lasten) und die Netzkanten weg und kommen
beim Loslassen der Maus wieder — das Bild bleibt dadurch flüssig.
Volumennetze werden nur mit ihrer Oberfläche gezeichnet.

**Unterlagen — Dateien, Ansichten und Skizzen zum Modell** (16.09.2026, analog
InfoCAD). Das Ribbon *Unterlagen* zwischen *Start* und *Geometrie* sammelt, was
zum Modell gehört, aber kein Tragwerk ist: *Datei hinzufügen* nimmt PDF, Bilder,
Word- und Excel-Dateien (oder jede andere) in die Modelldatei auf, *Ansicht
aufnehmen* das Bild der 3D-Ansicht, wie sie gerade steht, *Neue Skizze* öffnet
ein Blatt zum Zeichnen. Alles steht in der Tabelle *Unterlagen* (unten, Gruppe
*Bericht*) und im Modellbaum unter *Unterlagen*; Name, Beschriftung und
Bemerkung sind dort in der Zelle änderbar, Doppelklick öffnet (Skizzen im
Zeichenfenster, Dateien im Programm des Systems).

* **Skizze**: ein Blatt (Vorgabe A4 quer, Maße in mm) mit den Werkzeugen
  *Auswählen*, *Linie* (Anfang, Ende; die nächste hängt an, rechte Taste
  beendet), *Kreis* (Mittelpunkt, Punkt auf dem Kreis), *Bogen* (Anfang, Ende,
  Punkt auf dem Bogen), *Maß* (zwei Punkte, dann die Lage der Maßlinie) und
  *Text*. Der **Fang** rastet an Enden, Mitten, Mittelpunkten und Quadranten
  ein, sonst greift das **Raster** (Schritt einstellbar). Das Rad zoomt zum
  Zeiger, die mittlere Taste schiebt, Entf löscht das gewählte Element,
  Strg+Z nimmt den letzten Schritt zurück. **Maßstab** (1 mm auf dem Blatt =
  x mm am Bauteil) und **Einheit** (mm, cm, m) bestimmen die Maßzahlen; sie
  werden aus der gezeichneten Länge gerechnet, ein eigener Text geht vor.
* **Skizze aus Ansicht** (und im Zeichenfenster *Ansicht* /
  *Bild…*) legt die 3D-Ansicht oder ein Bild hinter das Blatt — das Blatt
  nimmt das Seitenverhältnis des Bildes an —, damit sich eine Darstellung
  bemaßen und beschriften lässt.
* **In den Bericht** macht aus der Unterlage einen Berichtseintrag (Tabelle
  *Bericht*, Kapitel wählbar wie bei jedem Eintrag): Skizzen und Bilder als
  Abbildung mit Bildunterschrift, Dateien wie eingefügte Dateien (Bilder, SVG,
  CSV, XLSX, Markdown/Text werden übernommen; PDF und Word werden genannt und
  sind als Anlage beizulegen). Der Eintrag zeigt immer den letzten Stand der
  Skizze. *Entfernen* nimmt die Unterlage samt ihren Berichtseinträgen weg.

**Layer — Objektgruppen wie die Objektselektionen in RFEM** (16.09.2026).
Ein Layer ist eine benannte Gruppe von Knoten, Linien, Stäben, Flächen und
Volumen. Beim Einlesen einer RFEM-6-Datei (.rf6) werden die
**Objektselektionen** zu Layern — am Drehlager etwa „Bolzen“, „Deckel +y“,
„Augenblech -y“, „Passstifte_außen“ —, das Protokoll nennt jeden mit seinem
Inhalt. Eigene Layer entstehen aus der Auswahl: *Ansicht → Layer aus Auswahl*
(auch im Modellbaum unter *Layer* und in der Layerliste). Ein Objekt darf in
mehreren Layern liegen; die Layer werden mit dem Modell gespeichert.

* **Aufklappliste** im Ribbon *Ansicht*: ein Layer allein im Bild, alles andere
  verschwindet (auch, was in keinem Layer liegt); *Alle Layer* holt alles
  zurück. Ein Volumen bringt seine Flächen, Linien, Knoten und sein Netz mit,
  ein Stab seine Elemente.
* **Layerliste** (Fenster, bleibt offen): je Layer die Haken **sichtbar** und
  **gesperrt**, dazu *Neu aus Auswahl*, *Auswahl hinzufügen*, *Auswahl
  herausnehmen*, *Objekte wählen*, *Nur diesen zeigen*, *Alle zeigen*,
  *Löschen* (die Objekte bleiben) und das Umbenennen in der Tabelle. Jede
  Änderung wirkt sofort und lässt sich mit *Rückgängig* zurücknehmen.
* **Ausgeblendet** ist ein Objekt, sobald *einer* seiner Layer ausgeblendet
  ist. Die Layer wirken neben *Auswahl ausblenden* und *Selektion anzeigen*;
  *Alles zeigen* und *Vorherige Sicht* betreffen nur das von Hand
  Ausgeblendete, die Layer bleiben, wie sie in der Liste stehen.
* **Gesperrt** heißt: nicht wählbar (Klick, Auswahlfenster, Modellbaum) und
  nicht änderbar (die Maske öffnet nicht, die Meldung nennt den Layer). So
  bleibt ein fertiges Bauteil unangetastet, während daneben modelliert wird.
  Der Fang trifft gesperrte Knoten weiterhin.
* **Modellbaum**: der Zweig *Layer* listet alle; Klick wählt die Objekte,
  Doppelklick öffnet die Layerliste, Rechtsklick legt einen Layer aus der
  Auswahl an oder löscht einen.

**Zoomen auf eine Bohrung.** Das Mausrad zoomt auf die **Fläche unter dem
Zeiger** zu, nicht auf die Brennebene der Kamera. Vorher fuhr die Kamera auf
ihren Blickpunkt zu, und der lag irgendwo im Bauteil: beim Zoomen auf eine
Bohrung von V15 am Drehlager war die Fläche nach zehn Radschritten 0,09 m
entfernt und wurde danach wieder *ferner* (Schritt 60: 0,34 m), während der
Blickpunktabstand auf 0,4 mm zusammenschrumpfte — jeder weitere Schritt
bewegte fast nichts mehr, „der Zoom wird langsam". Jetzt nimmt jeder
Radschritt denselben Anteil des Abstands zur Fläche (Faktor 1,15), die
Fläche bleibt unter dem Zeiger liegen, und jede Bohrung ist erreichbar, ohne
durch die Oberfläche zu fahren. Der **Blickpunkt** — die Mitte, um die das
Drehen geht — rückt dabei auf diese Fläche: wer nach dem Zoomen dreht, dreht
um das, was er ansieht. Der Flächenpunkt kommt aus dem Tiefenpuffer des
letzten Bildes (ein Pixel, unter einer Millisekunde; ein Picker brauchte am
Drehlager 60 bis 190 ms je Schritt). Liegt unter dem Zeiger nur Hintergrund,
gilt wie bisher der Punkt in der Brennebene. Geprüft in
`tests/test_gui_smoke.py` (25 Radschritte: der Abstand zur Fläche schrumpft
in jedem Schritt um denselben Anteil und wird nie wieder größer).

**Linien** sind Geometrie, keine Elemente — der Schalter „Linien" zeigt sie.
Bei einem aus RFEM übernommenen Modell besteht die Geometrie fast nur aus
Linien; ohne den Schalter sähe man ein leeres Bild.

**Der Fang** lässt sich je Art umstellen: F3 schaltet ihn ganz aus,
Umschalt+F1 den Knotenfang, Umschalt+F2 den Fang auf Kantenmitten,
Umschalt+F3 den Rasterfang, Umschalt+F4 bis F7 den Fang auf Linien, Stäbe,
Flächen und Volumen. Was gerade gefangen wird, steht in der Statuszeile
(„Fang: alle" oder die Liste der Arten).

**Lagersymbole** — das klassische Bild der Statik; die Form sagt, was das
Lager hält:

| Lager | Symbol |
|---|---|
| Einspannung (alles gehalten) | Würfel |
| Verschiebung gehalten | **Pyramide**, Spitze am Knoten; das Symbol zeigt in die gehaltene Richtung (meist nach unten) |
| eine Verschiebung frei (Rollenlager) | Pyramide auf einer **Gleitebene**, die sich mit zwei Rollen in die freie Richtung streckt |
| alle Verdrehungen frei (Gelenk) | **Kugel** an der Spitze |
| genau eine Verdrehung frei (Scharnier) | **Zylinder** in Richtung der Drehachse |
| Feder | **Schraubenfeder** in Richtung des Freiheitsgrads (in der Achse zwischen Spitze und Ebene, seitlich vom Knoten weg mit Endplatte); eine Drehfeder als Spirale um ihre Achse |

**Farbe und Beschriftung der Lager** (seit 12.09.2026, „man erkennt das
optisch schlecht"): jedes Symbol steht auf einer **Grundplatte mit
Schraffur** — dem Boden des klassischen Lagerbilds —, und die **Farbe** sagt
die Lagerart: dunkelblau fest (Einspannung), grün gelenkig (alle
Verschiebungen gehalten), orange gleitend (eine Verschiebung frei), violett
Feder, grau nur Verdrehungen gehalten. Ein Lager mit Ausfall, Schlupf,
Reibung oder Grenzkraft trägt zusätzlich eine **rote Kugel** am Knoten. Der
Schalter **Lagerbeschriftung** (Ribbon *Ansicht → Anzeigen*, neben *Lager*)
schreibt an jedes Knotenlager, was es hält: „fest", „gelenkig" oder die
gehaltenen Freiheitsgrade („uyz", „rxyz"), Federn mit „k", nichtlinear mit
„*". Geprüft in `tests/test_supports.py` (`test_lagersymbolik`).

**Linienlager** werden mit kleineren Symbolen **entlang der ganzen Linie**
gezeichnet (auf einem Bogen auf der wahren Kurve), dazu die Linie selbst;
**Flächenlager** im Raster **über die ganze gebettete Fläche**, die Symbole
in Richtung der Flächennormale (bei Volumen nach außen) — nicht mehr nur an
den Knoten. Ein aus RFEM übernommenes Flächenlager wirkt in den Achsen seiner
Fläche: die Bettung „uz" in der Flächennormalen, „ux/uy" und die Reibung in
der Fläche. Eine senkrechte Lagerfläche (Knagge) sperrt damit waagerecht; das
Protokoll des Imports nennt je Lager die Zahl der senkrechten Flächen. Ein aus RFEM übernommenes Lager kennt seine Linien bzw. Flächen
der Geometrie; die Symbole belegen darum die ganze Fläche, auch wenn noch
kein Netz vorliegt. Wie dicht die Symbole stehen, sagt die **Lagerdichte**:
Schieber „Dichte" im Register *Ansicht → Symbole* (1,0 = alle 5 % der
Modellgröße ein Symbol; die Ansicht folgt dem Schieber sofort), Rechtsklick
in die Ansicht → „Lagerdichte…" oder auf ein Linien-/Flächenlager. Die
**Größe** stellt der Schieber „Lager" daneben für alle zusammen ein; **ein
Rechtsklick auf ein Lagersymbol** öffnet dessen eigenes Menü mit „Größe
dieses Lagers…", „Größe aller Lager…", „Lager bearbeiten…" (die Maske
rechts) und „Lager löschen". Die eingestellte Größe wird mitgespeichert.

**Lager folgen dem Netz.** Ein Linien- oder Flächenlager mit Geometriebezug
wirkt nach dem Vernetzen auf **alle Netzknoten** seiner Linien bzw. Flächen
— mit den Einflusslängen und Einflussflächen aus dem Netz, nicht nur an den
Eckknoten der Geometrie. Das geschieht beim Vernetzen, beim Löschen des
Netzes (zurück auf die Eckknoten) und vor jeder Rechnung von selbst.

**Lager auswählen**: mit der Auswahlart **Lager** (Glasleiste) trifft ein
Klick ein Knotenlager an seinem Symbol, ein Linien- oder Flächenlager an
einem seiner Symbole; auch das Auswahlfenster fasst Lager. Gewählte Lager
leuchten; Rechtsklick zeigt sie als Gruppe (Bearbeiten, Symbolgröße bzw.
Lagerdichte, Löschen), *Alles deselektieren* leert auch sie.

### Tabellen: filtern, sortieren, ausgeben

**Auswahl in den Tabellen.** Was in der Ansicht gewählt ist, steht in den
Tabellen unten markiert. Zusammenhängende Zeilen werden dabei als ein Bereich
markiert: „Alles auswählen" am Drehlager-Modell (400 000 Knoten) hing bis zum
11.09.2026 über fünf Minuten, weil jede Zeile ein eigener Bereich war und Qt
Hunderttausende Einzelbereiche quadratisch zusammenführt. Als ein Bereich
dauert die Markierung von 200 000 Zeilen 1,1 s (`test_markieren_bereiche`).

**Gewähltes Element → Zeile.** Ein in der Ansicht gewähltes Element (Klick,
Fenster, Auswahlart Netz) markiert seine Zeile in Stabkräfte, Umhüllende,
Nachweise und Ermüdung und holt sie ins Bild — auch am Drehlager mit 1,8 Mio.
Elementen. Bis zum 12.09.2026 unterblieb die Suche ab 50 000 Elementen (die
Schleife über alle Elemente kostete dort 1,0 s je Klick), und kein gewähltes
Element fand seine Zeile; jetzt läuft sie über ein Netzverzeichnis, das einmal
je Netz entsteht (0,9 s) und die Frage danach in 13 ms beantwortet.

**Stabkräfte zur Umhüllenden.** Die Tabelle „Stabkräfte" führt Stabendkräfte
je Element und gehört zu einem Lastfall oder einer Kombination. Ist das
gezeigte Ergebnis eine Umhüllende, bleibt sie leer und sagt neben der
Zeilenzahl, warum: die Extremwerte stehen im Register „Umhüllende", auf das
der Bereich unten dann selbst springt — und zurück auf „Stabkräfte", sobald
wieder ein Lastfall oder eine Kombination gezeigt wird.

Der Bereich unten ist in **zwei Ebenen** gegliedert: oben die Gruppe, darunter
ihre Tabellen als Register. Eine Gruppe mit nur einer Tabelle (Protokoll,
Bericht) zeigt keine zweite Leiste. Ein Klick im Modellbaum holt die
passende Tabelle nach vorn — samt ihrer Gruppe.

| Gruppe | Tabellen |
|---|---|
| Protokoll | das Protokoll der Berechnung und der Modellprüfung |
| Modell | Knoten, Linien, Flächen, Volumenkörper, Stäbe (alle Elemente), Schweißnähte |
| Eigenschaften | Werkstoffe, Querschnitte, Dicken. Ein aus RFEM 6 übernommener Werkstoff bringt seit 13.09.2026 Streckgrenze und Zugfestigkeit **nach Erzeugnisdicke** mit (S355: bis 16 mm 355, bis 40 mm 345 … bis 400 mm 265 N/mm²); der Dialog zeigt die Tabelle unter „nach Dicke“, die Nachweise nehmen den Wert der Bauteildicke, der Bericht führt sie als eigene Tabelle. Vorher fehlten f_y und f_u beim rf6-Import ganz, und der Werkstoff hieß „Material 1 (DB 22175)“ statt „S355“ |
| Lager | Lager, Gelenke, Kontaktbedingungen |
| Lasten | Lastfälle, Lasten, Kombinationen |
| Ergebnisse | Stabkräfte, Auflagerkräfte, Umhüllende, Kontakt |
| Nachweise | Nachweise EC3, Ermüdung, Anschlüsse, Verformungen, Beulfelder, Volumen, Lasteinleitung |
| Bericht | die Einträge des Berichts |

Jede Tabelle unten hat über der Kopfzeile eine **Filterzeile** — ein Feld je
Spalte. Was dort steht, gilt sofort; mehrere Felder wirken zusammen (und, nicht
oder). Die Zählung links („17 von 240 Zeilen") sagt, wie viel übrig ist. Zahlen-
spalten stehen in den Einheiten aus *Ansicht → Einheiten*; Filterwerte werden
in derselben Einheit eingegeben. **Direkt bearbeiten:** in den Modelltabellen
sind die Eigenschaften in der Zelle editierbar (Doppelklick oder F2) - Knoten
x/y/z, bei Linien die Knotenfolge und die Bemerkung, bei Stäben die Knoten,
Werkstoff, Querschnitt bzw. Dicke und die Drehung, bei Flächen Randlinien,
Dicke, Werkstoff, Teilung und Bemerkung, bei Volumenkörpern Randflächen,
Werkstoff, Teilung und Bemerkung, bei Schweißnähten Nahtart, Lage, a, t, ℓ,
Ausführung und „gilt für“. Wo eine Auswahl besteht (Werkstoff, Querschnitt,
Dicke, Nahtart, Lage, Ausführung), öffnet die Zelle eine **Aufklappliste**;
Unzulässiges (unbekannter Knoten, fehlende Linie) wird mit Hinweis
abgewiesen, jede Änderung ist rückgängig machbar. **Mehrfachauswahl:** mit
**Umschalt** markiert ein Klick einen Bereich von Zeilen, mit **Strg** kommen
einzelne Zeilen dazu oder gehen heraus; die Ansicht wählt dann alles
zusammen, was die Zeilen einzeln gewählt hätten (die Knoten mehrerer Stäbe,
mehrere Flächen, Lager, Lasten …), und die Statuszeile nennt die Zahl der
Tabellenzeilen. Spalten werden aus ihrem Inhalt breit,
aber höchstens 360 Punkte (eine Elementliste mit tausend Nummern bleibt
lesbar, ohne die Tabelle über die ganze Wand zu ziehen); die Tabellen
zwingen dem Fenster keine Mindestbreite auf.

| Eingabe | wirkt |
|---|---|
| `> 0,9` | größer als 0,9 — auch `>=`, `<`, `<=`, `!=` |
| `= HEB 200` | genau dieser Wert (Zahl oder Text) |
| `1..5` | Bereich einschließlich der Grenzen |
| `HEB` | Text kommt vor (Groß- und Kleinschreibung egal) |
| `!HEB` | Text kommt **nicht** vor |

`> 1` in der Spalte „Ausnutzung" zeigt in einem Griff alle Überschreitungen.

**Sortieren**: Klick auf die Spaltenüberschrift; Zahlen werden der Größe nach
sortiert, nicht als Text. Namen werden **alphanumerisch** sortiert: die Zahl im
Namen zählt als Zahl, nicht Zeichen für Zeichen. „V2" steht damit vor „V10"
und nicht dahinter — alphabetisch käme die 1 vor der 2, und eine Liste von
hundert Volumen wirkte ungeordnet. Dieselbe Reihenfolge gilt überall, wo
Objekte aufgezählt werden: im **Modellbaum**, in den **Tabellen** und in den
**Aufklapplisten** der Masken. **Spalten** lassen sich über „Spalten…" ein- und
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
werden muss danach neu. **Der Rückgängig-Stapel sichert vor jeder Änderung das
ganze Modell.** Diese Sicherung war ein JSON-Umweg und kostete am
Drehlager-Modell (2 Mio. Elemente) vor jedem ändernden Befehl 105 s — „Stäbe
automatisch erkennen“, „Kontakt löschen“, „Ansicht übernehmen“ standen im
Menüdurchgang vom 11.09.2026 je 113 s. Jetzt wird strukturell kopiert (Knoten
als Feld, Elemente flach, der Rest über pickle): 11 s. Der Stapel hält
höchstens 50 Sicherungen und zusammen höchstens 5 Mio. Elemente (669 Byte je
Element, gemessen): am Drehlager bleiben zwei Sicherungen, rund 2,8 GB; die
letzte bleibt immer. Wer A, Iy, Iz, It oder Wpl,y von Hand ändert, löst den
Querschnitt von der Profildatenbank; sein Typ wird `free`, die Nachweise
laufen dann elastisch.

### Auswahl per Klick

Ein Klick trifft, was gezeichnet ist: Stäbe auch auf ihrem Körper, Flächen
auch auf einem Zylindermantel, Volumen auf ihrer Oberfläche (Zellenpicker
der Grafik, in Millisekunden). Erst wenn dort nichts liegt, sucht das
Programm geometrisch in der Nähe des Klicks. Was ein Klick trifft, sagt die
**Auswahlart** — die Knöpfe in der Glasleiste oder das Feld im Register
*Start*; der Modellbaum stellt sie beim Anklicken eines Zweigs passend um.
Mit der Auswahlart **Netz** trifft ein Klick ein einzelnes Element des
FE-Netzes (Stab-, Flächen- oder Volumenelement); die gewählten Elemente
leuchten in der Ansicht. Steht die Auswahlart auf **Knoten** und liegt unter
dem Zeiger kein Knoten (und keine Maske wartet auf einen Punkt), nimmt der
Klick das Objekt, das dort liegt - Stab, Fläche, Volumen oder Linie - und
stellt die Auswahlart darauf um. Gemessen wird in Bildpunkten um den Zeiger
(14 Bildpunkte, auf skalierten Bildschirmen entsprechend mehr Gerätepixel):
ein Klick knapp neben einem Knoten, einer Linie oder einer Stabachse trifft
noch.

**Die Maustasten in der 3D-Ansicht.**

| Taste | tut |
|---|---|
| **links** | kurzer Klick wählt, was unter dem Zeiger liegt — liegt dort nichts, hebt er die Auswahl auf (seit 16.09.2026); gedrückt halten und ziehen zieht das **Auswahlfenster** auf |
| **Mitte** gedrückt halten | **drehen**; Doppelklick (ohne Zug, nicht beim Rollen) passt alles Sichtbare ins Bild |
| **rechts** gedrückt halten | **schieben**; ohne Ziehbewegung das Kontextmenü |
| **Mausrad** | zoomen, auf die Fläche unter dem Zeiger zu; die Drehmitte folgt |

Seit 15.09.2026 dreht die mittlere und schiebt die rechte Taste; vorher war
es umgekehrt.

Die linke Taste dreht **nicht** mehr — sie gehört ganz der Auswahl. Dadurch
gibt es keinen Fall mehr, in dem eine Zeigerbewegung mal dreht und mal ein
Fenster aufzieht.

**Tasten und Doppelklicks im Bild** (16.09.2026, Meldung „beim Heranzoomen
springt der Zoom auf die Vollansicht zurück“). Nachgestellt wurden drei Wege
dorthin, alle drei sind geschlossen. Ein **Doppelklick mit der rechten oder
linken Taste** erreichte VTK als Tastendruck, das Loslassen aber nicht — VTK
blieb im Zoom- bzw. Drehzustand hängen; danach zoomte jede Mausbewegung ohne
Taste (gemessen: Abstand zur Blickmitte 0,70 → 0,31), und Drehen und Schieben
gingen nicht mehr. Jetzt gilt der zweite Druck wie ein Druck, und eine Bewegung
ohne Taste beendet einen hängenden Zustand. Die **Taste r** setzte die Kamera
auf die Gesamtansicht zurück (VTK-Standard; w und s schalteten Draht und
Fläche, Pfeil auf/ab zoomten): Buchstaben, Ziffern und Pfeiltasten tun in der
Ansicht jetzt nichts, Kürzel mit Strg oder Alt bleiben. Und der **Doppelklick
Mitte** zählt nur noch ohne Zug und nicht beim Rollen (s. o.).

**Auswahlfenster.** Mit gedrückter **linker** Maustaste aufziehen: der
Druckpunkt ist die erste Ecke, der Loslasspunkt die zweite; dazwischen zeigt
ein durchscheinendes Rechteck, was das Fenster fassen wird. Ein kurzer Klick
ins Leere zieht **kein** Fenster mehr auf, sondern hebt die Auswahl auf
(16.09.2026: „kurz = alles deselektieren, lang = Selektionsfenster“); bis dahin
setzte er die erste Ecke, und der nächste Klick die zweite.

| aufgezogen | Rechteck | gewählt wird |
|---|---|---|
| von **links nach rechts** | blau, durchgezogen | nur, was **ganz** im Fenster liegt |
| von **rechts nach links** | grün, gestrichelt | alles im Fenster **und** alles, was das Fenster nur **anschneidet** |

Gefasst wird, was die Auswahlart sagt: Knoten, Linien, Stäbe, Flächen,
Volumen oder Elemente des Netzes. Das Fenster ergänzt die vorhandene
Auswahl; **Esc** bricht es ab, *Alles deselektieren* (Glasleiste, Esc) leert
alles. **Klicken und Ziehen wählt nichts**: gezählt wird der Klick erst beim
Loslassen, und nur, wenn der Zeiger dazwischen höchstens vier Bildpunkte
gewandert ist — wer die Ansicht mit gedrückter Taste dreht, ändert die
Auswahl nicht.

**Intelligente Auswahl.** Der Schalter in der Glasleiste (auch *Start →
Auswahl*, Vorgabe: an) nimmt bei Linien und Stäben die **eindeutige
Fortsetzung** gleich mit: Hängt am Endknoten der angeklickten Linie genau
eine weitere Linie, gehört sie dazu, und so weiter — bis zu einer
Verzweigung (mehrere Linien am Knoten), einem freien Ende oder dem Schluss
eines Rings. Ein Zug aus zwölf Linien ohne Abzweig ist so ein einziger
Klick. Dieselbe Regel gilt **beim Abwählen**: der Klick auf eine gewählte
Linie nimmt den Zug wieder heraus, soweit er gewählt ist. Bei Stäben zählt
der physische Stab (Kette von Elementen) mit seinen beiden Enden. Ist der
Schalter aus, erzwingt **Umschalt + Klick** die Kette für diesen einen
Klick. Der Klickmodus der Flächenmaske (*Randlinien anklicken*) nutzt
dieselbe Kette — ein Klick auf eine Randlinie holt den ganzen geschlossenen
Rand, wenn er sonst nirgends abzweigt.

**Die Auswahl leuchtet.** Gewählte Linien, Stäbe, Flächen und Volumen werden
nicht nur umrandet, sondern gefüllt hervorgehoben: Stäbe und vernetzte
Flächen über ihre Elemente, unvernetzte Flächen als durchscheinendes
Polygon, Volumen über ihre Oberfläche — dieselbe Hervorhebung wie beim
Anklicken im Modellbaum.

Ist **nichts gewählt** und keine Maske offen, bleibt der rechte Bereich
**leer** - kein Netz-, Werkstoff- oder Generatorpanel und auch keine
Projektangaben; die stehen unter dem obersten Punkt des Modellbaums. Solange
eine Maske offen ist, steht rechts nur sie. Stabzug, Platte und Quader sind
Masken im Register *Geometrie*, der Import steht im Register *Datei*.

**Rechtsklick auf die Auswahl.** Sind Knoten, Linien, Stäbe, Flächen,
Volumen oder Elemente gewählt (mit ihren Lagern und Kontaktbedingungen),
öffnet der Rechtsklick in der Ansicht ein Menü: oben *Selektiertes
anzeigen* (alles andere ausblenden) und *Selektiertes ausblenden*, dann
**Verschieben…**, **Kopieren…**, **Drehen…**, **Spiegeln…** (siehe
„Verschieben, Kopieren, Drehen, Spiegeln“), darunter
je Gruppe der markierten Objekte ein Untermenü mit **Bearbeiten…** und
**Löschen**. *Bearbeiten…* öffnet rechts die **Sammelmaske** für alle
Objekte der Gruppe: Felder, in denen sich die Objekte unterscheiden, zeigen
„verschieden“ (bzw. „(unverändert)“) und bleiben so, wie sie je Objekt sind,
solange man nichts einträgt - ein eingetragener Wert gilt für alle. So
bekommen zwanzig Stäbe in einem Schritt denselben Knicklängenbeiwert oder
zehn Flächen dieselbe Dicke. *Löschen* entfernt die ganze Gruppe nach einer
Rückfrage; was nicht gelöscht werden kann (Knoten mit Linien oder
Elementen), nennt die Statuszeile. Rückgängig nimmt beides zurück.

### Lastwerte in der Ansicht

Jede gezeichnete Last trägt ihre **Größe als Zahl**: Knotenlasten den
Betrag der Kraft (und des Moments), Strecken- und Linienlasten q in der
Mitte des belasteten Abschnitts (bei Trapezlasten „q₁→q₂“), Flächen- und
Objektlasten p je Fläche (bei Verläufen „p_min…p_max“), Temperaturlasten ΔT,
Zwangsverformungen die Verschiebung. Die **Einheiten** der gezeichneten
Lastarten stehen oben links in eckigen Klammern unter dem Lastfall, etwa
„[kN, kN/m, kN/m²]“ - in den Einheiten aus *Ansicht → Einheiten*
(Vorgabe kN, kNm, kN/m, kN/m², K und mm). Der Schalter
*Ansicht → Anzeigen → Lastwerte* blendet die Zahlen aus; die Textgröße
folgt den Bemaßungseinstellungen. Bei sehr vielen gleichartigen Lasten
werden höchstens 60 je Lastart beschriftet.

### Einheiten und Genauigkeiten

*Ansicht → Einheiten* (auch *Extras → Einheiten und Genauigkeiten…*) öffnet
rechts die Maske, in der Einheit und Nachkommastellen für die Anzeige gewählt
werden. Gerechnet wird immer in SI (N, m, Pa); die Einstellung betrifft nur,
was gezeigt wird, und sie wird mit dem Modell gespeichert.

| Größe | Einheiten | Nachkommastellen |
|---|---|---|
| Kraft | N, kN, MN | Kraft und Moment |
| Länge | m, cm, mm | Länge |
| Verformung | mm, cm, m | Verformung |
| Spannung | N/mm², MPa, kN/cm² | Spannung |
| Lastwerte in der Ansicht | aus Kraft und Länge | Lasten |
| Winkel, Ausnutzung | °, – | Winkel, Ausnutzung |

Moment, Strecken- und Flächenlast folgen aus Kraft und Länge: bei N und mm
wird aus kNm Nmm, aus kN/m N/mm und aus kN/m² N/mm². Die Einstellung wirkt
auf

* die **Lastwerte** an den Lasten und die Einheitenzeile oben links,
* die **Kennwerte** unten links (Verformung, Schnittgrößen, Vergleichsspannung,
  Ausnutzung - je nach gewähltem Ergebnis),
* alle **Tabellen** unten: Kopfzeile, Zellen, Filter, Sortierung, Max/Min-Zeile,
  Zwischenablage, CSV und Excel. Bearbeitbare Zahlen (Knotenkoordinaten,
  Streckgrenze …) werden in der angezeigten Einheit eingegeben und in der
  Grundeinheit gespeichert; „min / max“-Paare der Umhüllenden werden als Paar
  umgerechnet.

Die Maße im Bild haben eigene Angaben (*Messen → Bemaßung: Einstellungen*),
der Bericht bleibt bei kN, m, mm und N/mm². „Rückgängig“ nimmt auch eine
Einheitenumstellung zurück.

### Messen und Bemaßen (Register Messen)

**Messen** beantwortet eine Frage sofort: *Abstand* (zwei Punkte: Länge,
Δx, Δy, Δz und Abstand in der Ebene), *Winkel* (Schenkel, Scheitel,
Schenkel), *Koordinaten* (ein Punkt), *Fläche* (Polygon aus angeklickten
Punkten, „Anwenden“ schließt es) und *Länge / Fläche* der Auswahl (gewählte
Linien und Stäbe, gewählte Flächen). Die Punkte kommen aus dem Fang -
Knoten, Kantenmitten, Linien, Stabachsen, Raster, sonst die Arbeitsebene -
und legen **keine Knoten** an. Das Ergebnis steht in der Maske, in der
Statuszeile und im Protokoll und wird orange in die Ansicht gezeichnet;
*Messungen löschen* nimmt es wieder weg. Die Maske bleibt für die nächste
Messung offen.

**Bemaßung** legt Maße als Objekte des Modells an (Modellbaum → Bemaßungen,
werden mit der Datei gespeichert und erscheinen in Bildern für den
Bericht):

| Werkzeug | Punkte | Darstellung |
|---|---|---|
| Linearmaß | 2 | Maßhilfslinien, Maßlinie mit Schrägstrichen, Maßzahl; die Maßlinie liegt senkrecht zur Strecke in der Blickebene (beim Anlegen festgehalten, in der Maske umkehrbar) |
| Maßkette | beliebig, „Anwenden“ beendet | Einzelmaße auf einer Linie und das Gesamtmaß darüber |
| Höhenkote | 1 | Kotensymbol mit Fahne und Höhe ab dem Höhenbezug (±0.000) |
| Winkelmaß | 3 | Maßbogen zwischen den Schenkeln mit Winkel in Grad |
| Radius | 2 (Mittelpunkt, Kreispunkt) oder 3 Kreispunkte | Strahl mit Mittelpunktkreuz und „R …“ |

Je Maß lassen sich Einheit, Nachkommastellen, Versatz und ein eigener Text
setzen (Klick auf das Maß im Modellbaum); *Einstellungen…* regelt Einheit
(m, cm, mm), Nachkommastellen, Textgröße, Versatz (0 = 8 % der Modellgröße),
Höhenbezug und Farbe für alle Maße ohne eigene Angabe. *Letzte / Alle
Bemaßungen löschen* und Entf im Modellbaum entfernen Maße; Rückgängig holt
sie zurück.

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

### Verschieben, Kopieren, Drehen, Spiegeln

Was in der Ansicht gewählt ist — Knoten, Linien, Stäbe, Flächen, Volumen,
auch gemischt —, lässt sich seit 15.09.2026 **verschieben, kopieren, drehen
und spiegeln**: Rechtsklick in die Ansicht oder *Geometrie → Ändern*. Rechts
erscheint die Maske; jede hat zwei Wege:

| Befehl | tippen | klicken |
|---|---|---|
| Verschieben | dx, dy, dz [m], „Anwenden“ | zwei Punkte: von → nach |
| Kopieren | dx, dy, dz und Anzahl | zwei Punkte |
| Drehen | Achse x, y oder z durch einen Punkt, Winkel [°] (rechtsdrehend um die Achse), Haken „als Kopie“, Anzahl | zwei Punkte der Achse |
| Spiegeln | Ebene yz, xz oder xy in einer Lage, Haken „als Kopie“ | drei Punkte der Ebene |

Sobald die Punkte beisammen sind (Fang wie überall), geschieht es sofort;
sonst „Anwenden“. Jede weitere Kopie liegt um dieselbe Abbildung weiter
(drei Kopien mit dz = 2: bei 2, 4 und 6 m). Ein Volumen bringt seine Flächen,
die ihre Linien, die ihre Knoten mit — und das Netz: verschobene und gedrehte
Netze bleiben, kopierte kommen mit (Elemente, Randseiten, Stäbe mit
Nachweis; Kopien heißen L…, F…, V…, S… fortlaufend). Ein Knoten, den auch ein
**nicht** gewähltes Objekt benutzt, wandert beim Verschieben mit (so hängt
eine Rippe an ihrem Blech); wer das nicht will, kopiert. **Spiegeln** löscht
das Schalen- und Volumennetz der gespiegelten Objekte — die Elemente wären
umgestülpt —, die Geometrie bleibt, Stabelemente bleiben; danach neu
vernetzen. Bögen, Kreise, Splines nehmen Mittelpunkt, Normale und
Steuerpunkte mit. Lager, Lasten und Kontaktbedingungen werden nicht kopiert;
berührt die Kopie ein anderes Volumen, entsteht der Kontakt von selbst
(„Kontakte entstehen von selbst“). Alles ist mit Rückgängig zurückzunehmen.
Geprüft in `tests/test_transformieren.py` und der Oberflächenprüfung.

### Rückgängig und Wiederholen

**Strg+Z** nimmt die letzte Änderung zurück, **Strg+Y** stellt sie wieder her —
für alles: Geometrie, Netz, Lager, Lasten, Linien. Gesichert wird jeweils das
ganze Modell, darum bleibt auch eine Änderung umkehrbar, die viele Stellen auf
einmal betrifft. Die letzten 50 Schritte werden vorgehalten; die Schnellzugriffs-
leiste zeigt im Hinweistext, worum es beim nächsten Schritt geht.

### Koordinatensysteme, Arbeitsebene, Fang

Im Register **Geometrie** stehen zwei Gruppen für die Eingabehilfen - der Fang gehört zur Arbeitsebene:

* **Koordinatensystem** — das aktive System wählen, ein neues über Ursprung und
  Drehwinkel anlegen oder aus drei gewählten Knoten aufspannen (Ursprung,
  x-Richtung, ein Punkt in der xy-Ebene). Neben kartesisch gibt es
  **zylindrisch** (r, θ, z — für Rohre und Segmentverschlüsse) und
  **sphärisch** (r, θ, φ). Alle Koordinateneingaben beziehen sich auf das
  aktive System; die Statusleiste nennt es.
* **Arbeitsebene** — xy, yz oder xz des aktiven Systems, mit einstellbarer
  Rasterweite (0 = kein Raster).
* **Fang** — ein Klick in der Ansicht wird auf die nächste markante Stelle
  gezogen, in dieser Reihenfolge: **Knoten**, **Kantenmitte** eines Stabes,
  **Lot** (seit 15.09.2026: der Fußpunkt des Lots vom zuletzt gewählten Knoten
  oder Punkt der offenen Maske auf eine Linie oder Stabachse — so trifft die
  nächste Linie rechtwinklig auf eine andere; ohne offene Maske fängt „Lot“
  nichts), **Linie** (der Fußpunkt auf der Linie, auch auf einem Bogen),
  **Stab** (der Fußpunkt auf der Stabachse), **Fläche** (der Punkt auf der
  Fläche oder Schale unter dem Zeiger, auch auf einem Zylindermantel),
  **Volumen** (der Punkt auf der Oberfläche eines Körpers), zuletzt der
  **Rasterpunkt**. Jede Art ist einzeln schaltbar — im Ribbon, in der
  Glasleiste oder mit Umschalt+F1 … F8 (Lot: Umschalt+F8); der Hauptschalter
  (F3) nimmt alles zurück. Die Statusleiste zeigt den Zustand.

### Lot und Projektion

*Geometrie → Konstruktion → Lot / Projektion* (seit 15.09.2026). Erst die
Knoten wählen, von denen das Lot fallen soll, dann die Maske rechts:

| Feld | Bedeutung |
|---|---|
| Ziel | **Arbeitsebene**; **Ebene einer Fläche** (die Ebene der ebenen Fläche, auch über ihren Umriss hinaus); **Fläche (nächster Punkt)** — der nächste Punkt der Fläche selbst, auch einer gewölbten (Zylindermantel), am Rand der Randpunkt; **Linie (nächster Punkt)** — der nächste Punkt der Linie, Bögen und Splines abgetastet |
| Objekt | die Fläche oder Linie: Name tippen oder **ins Feld klicken** und in der Ansicht anklicken (orange = scharf; ein anderes Feld oder Esc beendet das) |
| Ergebnis | **neuer Knoten am Fußpunkt** (die neuen Knoten sind danach gewählt) oder **Knoten dorthin verschieben** — das ist der projizierte Punkt |
| Lotlinie anlegen | zu jedem neuen Fußpunkt eine Linie vom Quellknoten dorthin |

Geprüft in `tests/test_konstruktion.py` (Lot auf Ebene, Strecken, Kreis,
ebene und gewölbte Fläche) und der Oberflächenprüfung.

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

### Flächen: eben oder Regelfläche; Flächen verschneiden

Die Flächenmaske (und „Fläche aus Linien“) hat seit 15.09.2026 das Feld
**Geometrieart**: **eben** — der Rand liegt in einer Ebene — oder
**Regelfläche (Viereck, gewölbt)**: die Fläche spannt sich zwischen vier
Randabschnitten auf und darf gewölbt sein, wie der Mantel einer Bohrung,
einer Buchse oder eines Bolzens (RFEM nennt das Quadrangle). Die Randlinien
dürfen dabei Bögen oder Splines sein; Bild und Netz kommen aus der
Coons-Fläche über den vier Seiten. Eine Fläche aus der Quelldatei kann
außerdem „beschnitten“ sein. Wechselt man die Art einer vernetzten Fläche,
fällt ihr Netz (es gehörte zur alten Form) — neu vernetzen.

**Flächen verschneiden** (*Struktur → Flächen → Flächen verschneiden*): zwei
Flächen wählen, der Befehl legt ihre **Schnittlinie** als Polylinie mit neuen
Knoten an (vorhandene Knoten auf der Linie werden genommen; Zwischenpunkte auf
einer Geraden entfallen) und wählt sie; die Flächen bleiben, wie sie sind —
mit der Linie lassen sie sich dann in Teilflächen zerlegen. Verschnitten
werden die Dreiecke der Flächen, dieselben wie im Bild; darum geht es auch mit
gewölbten Flächen und Spline-Rändern, auf die Genauigkeit der Abtastung (16
Abschnitte je Bogen: ein Viertelkreis kommt auf 1 % Bogenlänge). Aufeinander
liegende Flächen geben keine Linie. Geprüft in `tests/test_verschneiden.py`.

### Ansichtswürfel

Oben rechts in der Ansicht steht der **Ansichtswürfel**. Er zeigt die Lage
der Kamera: die drei Seiten, auf die man gerade schaut, sind sichtbar und mit
ihrer Achse beschriftet (+X, −Y, +Z …), und er dreht sich mit, wenn man die
Ansicht dreht. Drei Wege, ihn zu benutzen:

* **Ziehen** mit gedrückter linker Maustaste auf dem Würfel dreht die
  Ansicht um den Blickpunkt — wie das Drehen in der Ansicht selbst, nur mit
  dem Würfel als Griff.
* **Klick auf eine Seite** stellt die Ansicht senkrecht auf diese Seite.
* **Die Knöpfe darunter** heißen wie die Achsen: **+x +y +z −x −y −z** — die
  Richtung, aus der man schaut (−y ist die Vorderansicht, +z die Draufsicht)
  — und **iso** für die isometrische Ansicht mit allem im Bild. Die Rückseite
  ist damit ein Klick und nicht eine halbe Umdrehung.

Im Ribbon *Ansicht → Blickrichtung* stehen dieselben Richtungen, dazu
„Rückseite (180°)", das die laufende Ansicht am Blickpunkt umkehrt, und
„Zoom alles".

### Querschnitte anlegen: Normprofile, eigene Profile, freier Editor

Ein Klick auf **Querschnitte** im Modellbaum (oder Rechtsklick → *Neu:
Querschnitt*, oder *Struktur → Querschnitt hinzufügen*) zeigt rechts die
Querschnittsmaske. Sie hat drei Teile, von oben nach unten:

1. **Normprofile** aus der Profildatenbank. Oben das Land mit seiner Norm,
   darunter die **Art** als Knöpfe — *Doppel-T* (IPE, HEA, HEB, HEM; UB, UC;
   W), *U* (UPN, UPE; PFC; C), *Hohl* (SHS, RHS, CHS; HSS, PIPE), *T*
   (halbierte Doppel-T: IPET, HEAT, HEBT) und *L* (gleich- und
   ungleichschenklig) —, dann Reihe und Profil. Das Bild und die Kennwerte
   (A, Iy, Iz, It, Wel, Wpl) laufen mit; **Anlegen** nimmt das Profil ins
   Modell. Der Name ist die Profilbezeichnung, wenn das Namensfeld leer bleibt.
2. **Eigene Profile** mit Parametern in mm, wie die Parameterprofile in
   RFEM (16.09.2026): Rechteck, Kreis, Rundrohr, Rechteckrohr, geschweißtes
   Doppel-T, U, T, Winkel, Kasten aus Blechen, **Doppel-T unsymmetrisch**
   (h, b_o, t_o, b_u, t_u, tw), **Z**, **Hut**, **Kreuz**, **Ellipse**,
   **Halbkreis**, **Trapez**, **Dreieck**, **Sechskant** (Schlüsselweite) —
   oder *frei* nach Steifigkeiten (A, Iy, Iz, It). Die neuen Formen werden
   als Polygon gerechnet: Fläche, Schwerpunkt, Trägheitsmomente und
   Hauptachsen exakt, Wel und **Wpl** aus der plastischen Nulllinie, It bei
   dünnwandigen offenen Formen Σ b·t³/3, bei der Ellipse geschlossen, sonst
   nach Saint-Venant (Näherung). Auch hier Bild und Kennwerte, dann
   **Anlegen**.
3. **Profil frei erstellen …** öffnet den Editor. Dort setzt man ein Profil aus
   drei Dingen zusammen:
   * **Standardprofile** (aus der Datenbank oder ein Querschnitt des Modells)
     mit der Lage ihres Schwerpunkts dy, dz [mm], Drehung [°] und Spiegeln;
   * **Knoten** (Nr, y, z in mm; y nach rechts, z nach oben) und **Elemente**:
     Blechstreifen der Dicke t zwischen zwei Knoten — so entstehen
     dünnwandige Profile beliebiger Form;
   * **Flächen**: eine Knotenfolge als geschlossenes Polygon, wahlweise als
     **Loch** (wird von der Fläche abgezogen, in der es liegt) — so entstehen
     Vollquerschnitte und Kästen.

   Rechts stehen Bild und Kennwerte, die bei jeder Änderung mitlaufen; ein
   Fehler (Knoten fehlt, Element ohne Länge) steht rot dort und sperrt OK.
   Das Ergebnis ist ein zusammengesetzter Querschnitt nach dem Satz von
   Steiner mit Hauptachsen und Hauptachsenwinkel; der Editorinhalt reist mit
   und lässt sich über den Editor wieder öffnen. It ist bei Elementen der
   offene Wert Σ L·t³/3, bei Flächen die Näherung nach Saint-Venant (siehe
   Theoriehandbuch 1.4); wer It genauer kennt, trägt ihn in der Tabelle
   „Querschnitte“ ein.
4. **Kontur zeichnen …** öffnet das Zeichenfenster der Skizzen (Register
   Unterlagen) für einen Querschnitt, wie der Querschnittsgenerator in
   InfoCAD: Linien, Bögen und Kreise in mm, Raster und Fang, wahlweise ein
   Bild (eine Zeichnung) als Hintergrund und ein Maßstab (1 Blatt-mm =
   n mm). Jede geschlossene Schleife ist Material, eine Schleife innerhalb
   einer anderen ein **Loch**, eine Schleife in einem Loch wieder Material;
   Bögen werden alle 5° abgetastet, Kreise mit 72 Ecken. Querschnittsachsen:
   y nach rechts, z nach oben (die Blattachse zeigt nach unten, das Programm
   dreht um). **Übernehmen** oder **OK** rechnet das Polygon (Fläche,
   Schwerpunkt, Trägheits- und Widerstandsmomente, Wpl exakt, Hauptachsen)
   und legt den Querschnitt an; die erste Kennwertzeile steht im Fenster.
   Bleibt eine Kontur offen, nennt das Fenster die offenen Enden in mm statt
   ein falsches Polygon zu rechnen. Die Kontur reist mit dem Querschnitt:
   die Aufklappliste neben dem Knopf öffnet eine gezeichnete Kontur des
   Modells wieder, und Übernehmen ersetzt den Querschnitt; Stäbe und
   Elemente behalten ihren Bezug.

**Hauptachsen.** Iy und Iz sind die Hauptwerte; die Hauptachse, die der
Bezugsachse y (waagerecht, wie gezeichnet) näher liegt, heißt y, der
Hauptachsenwinkel liegt zwischen −45° und +45°, bei Symmetrie ist er 0.
Bis zum 16.09.2026 hieß der größere Hauptwert Iy, und ein flach liegendes
Rechteck galt als „um 90° gedreht“ — RFEM und die Stabsteifigkeit rechnen
mit Iy um die waagerechte Achse, so wie es gezeichnet ist. Ein Profil, das
im freien Editor um 90° gedreht wird, tauscht deshalb Iy und Iz.

**Löschen**: ein Querschnitt, den kein Element und kein Stab mehr benutzt,
geht per Rechtsklick → *Löschen* oder Entf aus dem Modellbaum; ein benutzter
wird mit der Zahl seiner Elemente abgewiesen.

### Subsysteme

Standardmäßig ist die ganze Struktur **ein** Subsystem — das *Gesamtsystem*
im Modellbaum unter „Subsysteme“. Ein weiteres Subsystem entsteht mit
**Rechtsklick → Neu: Subsystem** (oder „+ Subsystem anlegen“): Stäbe,
Flächen oder Volumen in der Ansicht anklicken — auch mit dem
Auswahlfenster —, Name eingeben, **OK**. Zum Subsystem gehören dann
**alle zugehörigen Elemente, Knoten, Linien, Lager und Kontakte**. An der
Berührungsstelle zu den übrigen Teilen werden die Elemente **verdoppelt**:
jedes Subsystem hat sie, ähnlich wie bei Kontakten (der Haken
„Berührungselemente mitnehmen“ schaltet das ab). Ein Klick auf ein
Subsystem wählt es in der Ansicht und zeigt rechts, was es enthält; Name
und Beschreibung sind dort änderbar, Entf löscht es. Subsysteme werden mit
dem Modell gespeichert.

### Stellungen: Lage und Wirkung des Systems

Eine **Stellung** ist eine Lage des Systems samt allem, was in ihr nicht
wirkt. Sie wird — wie alles — **rechts in der Maske** angelegt und
geändert: Modellbaum → Stellungen → **Rechtsklick → Neu: Stellung** oder
„+ Stellung anlegen“, im Register *Berechnung → Stellung anlegen* oder
„+ Stellung“ im Register Stellungen; ein Klick auf eine Stellung im Baum
zeigt ihre Maske, Entf löscht sie. Die Maske enthält genau:

| Feld | Bedeutung |
|---|---|
| Bezeichnung | der Name der Stellung |
| Ausgangsstellung | „unbewegtes Modell“ oder eine andere Stellung, auf deren Lage die eigene Verschiebung und Verdrehung **aufsetzen** — so entsteht eine Kette von Stellungen (geschlossen → 30° → 60°) |
| Verschiebung x, y, z [m] | Verschiebung der bewegten Knoten gegen die Ausgangsstellung |
| Verdrehung [°], Drehachse, Punkt der Achse | Drehung der bewegten Knoten um die Achse gegen die Ausgangsstellung (bewegt sind alle nicht gelagerten Knoten bzw. die Elementgruppen der Stellung) |
| Deaktivierte Stäbe, Flächen, Volumen | ihre Elemente tragen in dieser Stellung weder Steifigkeit noch Last, ihre Schnittgrößen sind null; Knoten ohne wirksames Element werden festgehalten |
| Deaktivierte Gelenke | Liste zum Anhaken: diese Gelenke sind in der Stellung **biegesteif** (etwa eine Verriegelung) |
| Deaktivierte Knoten-, Linien-, Flächenlager | Listen zum Anhaken (Namen oder Nummern wie im Modellbaum): sie greifen in dieser Stellung nicht |

**Per Maus statt Tippen.** Solange der Haken *Klick in der Ansicht schaltet
Stab, Fläche oder Volumen aus / ein* oben in der Maske steht, gehen Klicks in
der Ansicht an die Stellung: ein angeklickter Stab, eine Fläche oder ein
Volumen wird ausgeschaltet, steht in der Liste und verschwindet im Bild —
noch ein Klick schaltet es wieder ein. Gelenke und Lager werden in ihren
Listen angehakt. Der alte Weg bleibt: Objekte oder Knoten (für ihre Lager)
wählen und **„Auswahl deaktivieren“** / „Auswahl aktivieren“; „Alle
aktivieren“ leert die Listen. Solange die Maske offen ist, zeigt die Ansicht
die Stellung ohne ihre abgeschalteten Elemente. Stellungen werden mit dem
Modell gespeichert. Geprüft in `tests/test_gui_smoke.py` (Abschnitt
Werkbank: Klick schaltet aus und wieder ein, Listen zum Anhaken).

### Situationen: Stellung und ihre Lastfälle

Unter „Situationen“ steht immer die **Grundstellung**: unbewegt, alles
wirkt; Lastfälle ohne Situation gelten hier. Eine weitere Situation
entsteht mit **Rechtsklick → Neu: Situation** (oder „+ Situation
anlegen“). Ihre Maske hat nur noch drei Angaben: die **Stellung**, die
**Lastfälle** und die **Kombinationen**, die in dieser Situation gelten —
als Listen zum **Anhaken** („Alle Lastfälle und Kombinationen“ hakt alle
an), nicht mehr als getippte Namen.
**OK** legt die Situation an und ordnet die genannten Lastfälle und
Kombinationen zu; nicht mehr genannte fallen in die Grundstellung zurück.
Was in der Stellung nicht wirkt (Stäbe, Flächen, Volumen, Gelenke, Lager),
steht in der Stellung selbst — die Maske der Situation zeigt es nur an.

**Aus RFEM kommen Situationen von selbst mit.** Eine Strukturmodifikation in
der Quelldatei ist ein Ausfallszenario: sie schaltet genannte Stäbe und Lager
ab, und die Lastfälle, die darauf verweisen, rechnen mit diesem verkleinerten
System. Der Import legt daraus eine Stellung und eine Situation an und trägt
sie bei den betroffenen Lastfällen ein; die Kombinationen folgen ihren
Lastfällen. Am geprüften Drehlagermodell heißt sie „Ankerausfall" und betrifft
**128 der 422 Lastfälle** — ohne sie rechneten diese 128 Fälle mit einem Anker
und einem Lager, die ausgefallen sein sollen. Mischt eine Kombination aus
RFEM Lastfälle aus zwei Situationen, sind das zwei Tragwerke — in RFEM eine
Umhüllende über beide Systeme. Der Import teilt sie je Situation
(„… (Grundstellung)“, „… (Ankerausfall)“); beide Teile stehen in derselben
Umhüllenden, und das Protokoll nennt die Teilung. Eine von Hand gemischte
Kombination weist der Löser weiterhin ab.

**Jeder Lastfall und jede Kombination nennt seine Situation** — auch im
Lastfalldialog und im Kombinationsdialog als Feld „Situation“; die
Tabellen unten und der Modellbaum zeigen sie mit. Eine Kombination
überlagert nur Lastfälle **derselben** Situation (die anderen Felder sind
im Dialog gesperrt, die Modellprüfung meldet eine Mischung als Fehler);
die automatischen Kombinationen nach DIN EN 1990 entstehen je Situation.
Gerechnet wird jede Situation mit ihrem eigenen System: die Stellung wird
angewandt (Ausgangsstellung, Verschiebung, Verdrehung, Lager, Gelenke),
die deaktivierten Elemente tragen weder Steifigkeit noch Last, ihre
Schnittgrößen sind null, Knoten ohne wirksames Element werden
festgehalten. Im Ergebnisbild einer solchen Situation fehlen die
abgeschalteten Elemente, und das Modell steht in der Lage, mit der
gerechnet wurde.

### Register „Auswahl"

Sobald Knoten gewählt sind, erscheint rechts im Ribbon ein zusätzliches
Register **„Auswahl: n Knoten"** mit genau den Befehlen, die auf die Auswahl
passen: Querschnitt und Material zuweisen, Gelenke setzen, Elemente oder Knoten
löschen, Lager setzen, Last aufbringen, Auswahl umkehren oder aufheben. Im
Register *Start → Auswahl* steht daneben der Schalter **Intelligente
Auswahl** (siehe „Auswahl per Klick“). Wird
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
8. **Bericht**: Bericht → Bericht (HTML, im Browser druckbar/als PDF
   speichern; PDF direkt bei installiertem reportlab).

Beispiele im Menü **Beispiele** zeigen jeden dieser Schritte fertig
aufgebaut, u. a. der Hallenrahmen (Kombinationen, EC3, Ermüdung), die
Stauwand (Stahlwasserbau, Schalen + Riegel, Wasserdruck) und zwei
Kontaktbeispiele.

## 4 Lastfälle und Kombinationen

### Lasten an der Geometrie überleben Speichern und Laden (seit 21.09.2026)

Eine Last, die an einer **Fläche** oder **Linie** hängt, wird auf die Elemente
verteilt, sobald es dort ein Netz gibt. Diese verteilten Lasten stehen
absichtlich nicht in der Datei — sie entstehen beim nächsten Verteilen neu,
sonst lägen sie doppelt.

**Bis zum 21.09.2026 entstanden sie beim Laden aber nicht neu.** Wer eine
Datei öffnete und rechnete, ohne vorher neu zu vernetzen, rechnete ohne seine
Flächen- und Linienlasten. Knotenlasten, Stablasten und das Eigengewicht waren
nicht betroffen; sie hängen nicht an der Geometrie.

Das ist behoben: beim Laden wird einmal verteilt. **Wer vor diesem Stand eine
gespeicherte Datei geöffnet und gerechnet hat, sollte die Rechnung
wiederholen.** Ob eine alte Rechnung betroffen war, zeigt die
Auflagersumme im Bericht: trägt sie deutlich weniger als die aufgebrachte
Last, hat die Rechnung ohne die Geometrielasten stattgefunden.

### Lastarten

Register **Lasten**, alles mit Symbol. Jede Maske arbeitet auf der
**Auswahl** in der Ansicht (Auswahlart in der Glasleiste, unter *Geometrie →
Auswahl in der Ansicht* oder im Modellbaum) und schreibt in den gewählten Lastfall:

| Last | Ziel | Maske | Was sie kann |
|---|---|---|---|
| Knotenlast | gewählte Knoten | Kräfte F_x…F_z [kN], Momente M_x…M_z [kNm] | — |
| Linienlast | gewählte **Stäbe** oder **Linien** | q [kN/m] am Anfang, q2 am Ende, global oder lokal, **von/bis** [m] | gleichmäßig, trapezförmig, abschnittsweise |
| Flächenlast | gewählte **Flächen** oder **Volumen** | p [kN/m²], Richtung (senkrecht oder global), auf die Projektion, Verlauf | gleichmäßig oder **linear** von Punkt A (p) nach Punkt B (p bei B) |
| Temperatur | gewählte Stäbe, Flächen, Volumen oder alle Elemente | ΔT [K], ΔT_z oben−unten (Stäbe) | — |
| Zwangsverformung | gewählte **gelagerte** Knoten | u_x…u_z [mm], φ_x…φ_z [mrad] | Lagersetzung; fehlende Lager werden auf Wunsch gesetzt |
| Vorspannung | gewählte **Stäbe** oder **Volumen** | F_v [kN], Achse (Volumen) | als Anfangsdehnung: das Bauteil trägt F_v als Zug und klemmt die Umgebung |
| **Übermaß** | eine **Kontaktfuge** (Fläche anklicken) | Gesamtüberdeckung [µm] oder die vier Abmaße der Passung | Presspassung: Pressspannung und Schub über den Reibbeiwert |
| Eigengewicht | Lastfall | Register *Lasten → Weitere* | — |

Lasten auf Stäben, Linien, Flächen und Volumen hängen am **Objekt** und
werden beim Vernetzen (und bei jedem Neuvernetzen) auf die Elemente und
Knoten verteilt: eine Linienlast auf einem Stab wird zu Abschnittslasten auf
seinen Elementen, eine Linienlast auf einer Linie zu Knotenlasten der
Netzknoten auf dieser Linie (nach Zutrittslängen, linear veränderlich), eine
Flächenlast zu Elementflächenlasten, eine Temperatur zu Temperaturlasten
aller Elemente. Die abgeleiteten Elementlasten stehen weder in der Tabelle
noch im Bericht einzeln (bei einem Volumenmodell wären es Hunderttausende);
die Objektlast steht dafür mit dem Vermerk, wie viele Elementlasten sie
erzeugt hat. Eine Flächenlast auf einer noch nicht vernetzten Fläche wird
trotzdem **gezeichnet** — so sieht man die Lasten eines eben eingelesenen
RFEM-Modells.

**Im Bild**: Kräfte und Streckenlasten rot (Pfeile), Temperatur als Punkte
(orange warm, blau kalt), Zwangsverformungen grün, das Fenster einer freien
Rechtecklast als Rahmen. Der Schalter „Lasten“ (Glasleiste, Register
*Ansicht*) blendet sie aus.

**Tabelle Lasten** (unten): jede Last mit Lastfall, Art, Ziel und Wert; ein
Klick auf eine Zeile wählt das Ziel in der Ansicht, „Löschen“ nimmt die
Last heraus (bei Objektlasten samt ihren Elementlasten).

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

### Übermaß: die Presspassung als Last

*Register Lasten → „Übermaß"*

Ein Passstift hält sein Bauteil nicht, weil er im Loch steckt, sondern weil
er zu dick dafür ist. Genau das trägt man hier ein: **Fläche in der Ansicht
anklicken** (Auswahlart „Fläche") — die Maske stellt die Fuge ein, zu der sie
gehört — und die **Gesamtüberdeckung** eingeben. Aus ihr entstehen die
Pressspannung und, über den Reibbeiwert der Fuge, ihre Schubtragfähigkeit.

**Gesamtüberdeckung** heißt: was die beiden Teile zusammen zu viel haben.

* **Ebene Fuge** (Unterlegblech, Beilage) — die Überdeckung senkrecht zur
  Fläche.
* **Zylindrische Fuge** (Bohrung, Passstift, Buchse) — das Übermaß am
  **Durchmesser**, so wie es in der Passungstabelle steht. Radial schließt
  die Fuge davon die Hälfte; das rechnet das Programm um.

Welche Form die Fuge hat, erkennt das Programm selbst — daran, wie weit die
Fugenflächen sich herumlegen — und schreibt es ins Protokoll: „Fuge
zylindrisch — radial wirken 20 µm". **Diese Zeile ist es wert, gelesen zu
werden**: eine verwechselte Fugenform wäre ein Faktor zwei in der Pressung.

**Statt der Überdeckung die Passung.** Wer nur „Ø40 H7/s6" hat, trägt die
vier Abmaße aus der Passungstabelle ein — oberes und unteres Abmaß der
Bohrung (ES, EI) und der Welle (es, ei), in µm mit Vorzeichen. Das Programm
rechnet daraus

* **Höchstübermaß** (größte Welle, kleinste Bohrung) — maßgebend für die
  größte Pressung, also für den Werkstoffnachweis der Nabe,
* **Mindestübermaß** (kleinste Welle, größte Bohrung) — maßgebend für die
  kleinste Haltekraft, also für den Reibschluss,
* das **mittlere Übermaß** als Regelfall,

trägt das gewählte oben ein und schreibt die Rechnung ins Protokoll. Eine
eingebaute ISO-286-Tabelle gibt es bewusst nicht: sie wäre nicht
nachprüfbar, und ein Zahlendreher darin würde still zu einer falschen
Pressspannung führen. Das Kurzzeichen lässt sich als **Bezeichnung**
mitgeben; es steht dann in der Lastentabelle und im Bericht.

**Was daraus wird.** Die Fuge steht schon vor jeder anderen Last unter Druck.
Die Kontaktrechnung liefert die Pressverteilung (Tabelle *Kontakt*: F_n je
Knoten), und solange eine Querlast unter µ·N bleibt, trägt die Fuge sie
vollständig — kein Knoten gleitet. Ohne Übermaß hält in der Fugenebene
nichts; dann sagt es die Anzeige der **freien Bewegungen** mit der Kraft, die
dabei ins Nichts geht.

**In der Kombination** zählt das Übermaß wie jede andere Last: es geht mit
dem Beiwert seines Lastfalls ein. Wer das nicht will, legt es in einen
ständigen Lastfall mit γ = 1,0.

### Lastgenerierer Wasserdruck (Stahlwasserbau)

*Lasten → Generierer → Wasserdruck* (oder Modellbaum → Einwirkungen →
Lastgenerierer → „+ Wasserdruck anlegen“). Die Maske rechts sammelt alles,
was die Strömungsrechnung braucht; die Knöpfe unten schalten einen
**Klickmodus** in der Ansicht: *Benetzt anklicken* (Flächen und Volumen der
Haut), *Dichtlinie anklicken* (Linien der Dichtung, unten), *OW-Fläche
anklicken* und *UW-Fläche anklicken* (je eine **Referenzfläche**, an der
das Ober- bzw. Unterwasser steht; dazu die Angabe, ob das Wasser an der
**Oberseite** (in Richtung der Flächennormale) oder an der **Unterseite**
liegt - daraus folgt die Strömungsrichtung). Derselbe Knopf beendet den
Modus; „Auswahl übernehmen“ nimmt stattdessen die laufende Auswahl. Je
Generierer gilt eine **Situation**; der Lastfall wird angelegt, trägt die
Situation und die **Lastfall-Nr.** aus der Maske (0 = nächste freie).

| Angabe | Bedeutung |
|---|---|
| Verfahren | **strömungsnumerisch** (Vorgabe): Potentialströmung im lotrechten Schnitt durch den Verschluss, Druck aus Bernoulli - die Absenkung an Krone und Unterkante kommt aus der Rechnung; **analytisch**: Näherungsformeln (Poleni, Torricelli, Naudascher) |
| Oberwasser, Unterwasser | Wasserstände in m über dem Bezug des Modells (leer = trocken), je mit Referenzfläche und Seite |
| Sohle z | Unterkante des Wassers; leer = Dichtung minus Öffnung (unterströmt) bzw. Dichtung |
| Dichtung z, Oberkante z, Breite | leer = aus der Dichtlinie bzw. der Geometrie der Flächen |
| Wirkt | senkrecht zur Fläche (aus dem Druckfeld, netto aus beiden Seiten einer Schale) oder in einer globalen Richtung |
| überströmt | Wasser über der Oberkante: Überfallhöhe, Abfluss nach Poleni (μ), kritische Tiefe auf der Krone |
| unterströmt | Öffnung a unter dem Verschluss: Ausfluss nach Torricelli mit Kontraktionsbeiwert μ_a; das Unterwasser ertränkt den Strahl, wenn es über der Dichtung steht |
| Gitter | Zellen über die Verschlusshöhe (40 ist ein guter Anfang; feiner ist genauer und langsamer, gedeckelt bei 250 000 Zellen) |
| Unterdruck ansetzen | Sog unter Atmosphärendruck mitnehmen (bis −70 kN/m²); sonst wird bei null gekappt (belüftet) |
| Absenkung berücksichtigen | nur analytisch: Geschwindigkeitshöhe vom Druck abziehen (⅔·ρ·g·h_ü an der Krone, Strahldruck an der Unterkante) |
| Druckschwankungsbeiwert c_p' | > 0 legt einen zweiten Lastfall mit der Amplitude Δp = c_p'·ρ·v²/2 an (v aus dem Druckfeld) - Eingang für den Schwingungsnachweis |

**Lasten erzeugen** rechnet zuerst das Druckfeld - mit **Fortschrittsbalken**
in der Statuszeile und **Abbrechen** (auch Esc); ein Abbruch lässt das Modell
unverändert. Dann schreibt es Objektlasten (Verlauf „Wasser“) mit dem Druckfeld
an die Flächen; beim Vernetzen wird das Feld je Elementseite vor der Fläche
abgetastet (bei einer dünnen Schale netto aus Vorder- und Rückseite), die
Lasten folgen jedem Neuvernetzen und überleben das Speichern. Das Protokoll
nennt Verfahren, Resultierende, Angriffspunkt, Abfluss, größte Geschwindigkeit,
größten Druck und eine Kontrollsumme der Elementlasten; „Kennwerte“ in der
Maske zeigt sie vorab. Der Bericht (Kapitel „Lastgenerierer“) führt Angaben,
Kennwerte und Erläuterungen auf, zeichnet das **Druckfeld des Schnitts**
(Verschluss dunkel, Wasser blau bis rot, Farbskala in kN/m²) und den **Schnitt
durch den Verschluss** mit Druckfigur und Resultierender. Ein Generierer lässt
sich im Modellbaum anklicken (ändern, erneut erzeugen) und mit Entf samt seinen
Lasten löschen.

Was die Strömungsrechnung annimmt und nicht kann, steht im Theoriehandbuch
(Abschnitt 2.1a): reibungsfreie Potentialströmung in einer Schnittebene,
Wasserspiegel als feste Deckel, keine Wechselsprünge, keine Wellen.

### Lastgenerierer Wind (DIN EN 1991-1-4)

*Lasten → Generierer → Wind* (oder Modellbaum → Lastgenerierer → „+ Wind
anlegen“). Wände und Dach (Auswahlart Fläche) und Stäbe (Auswahlart Stab)
in der Ansicht wählen, „Auswahl übernehmen“, dann:

| Angabe | Bedeutung |
|---|---|
| Windzone / v_b | v_b,0 der Zone 1–4 (22,5 / 25 / 27,5 / 30 m/s) oder v_b unmittelbar; c_dir, c_season |
| Geländekategorie / Profil | 0, I, II, III, IV nach Tab. 4.1 (c_r, v_m, I_v, q_p = (1 + 7·I_v)·½·ρ·v_m²) oder die Mischprofile des NA (Binnenland, Küste, Inseln der Nordsee) |
| Anströmung | ±x, ±y oder ein Winkel von +x; Geländeoberkante (leer = Unterkante der Objekte) |
| Flächen sind | Gebäude (Wände und Dach nach ihrer Normale: Luv D, Lee E, Seiten A/B/C, Flachdach F/G/H/I), freistehende Wand (Tab. 7.9) oder Anzeigetafel (c_f = 1,8) |
| Stäbe | Kraftbeiwert aus dem Querschnitt: Rechteck (Bild 7.23), scharfkantige Profile (2,0), Kreiszylinder (Reynoldszahl, Rauigkeit k), Fachwerk (Völligkeitsgrad φ); Schlankheitsabminderung ψ_λ; oder c_f vorgeben |
| c_pi, c_s·c_d | Innendruck (wird von allen Zonen abgezogen), Strukturbeiwert |

**Lasten erzeugen** schreibt Objektlasten an die Flächen (Verlauf „Wind“:
q_p in der Höhe des Elements mal dem Beiwert seiner Zone) und trapezförmige
Streckenlasten auf die Stäbe (w = c_f·q_p(z)·b_ref) in einen Lastfall der
Kategorie W. Protokoll und Bericht nennen v_b, q_b, das Höhenprofil (v_m,
I_v, q_p), die Beiwerte je Zone und Stab (mit Re, λ, ψ_λ), Resultierende
und Kontrollsummen; der Bericht zeichnet **Höhenprofil und Grundriss** mit
Anströmung und Zonen.

**Numerischer Windkanal.** Mit *Verfahren → numerischer Windkanal* wird die
Strömung um die gewählten Flächen und Stäbe in einem Schnitt gerechnet
(Gitter-Boltzmann-Verfahren, siehe Theoriehandbuch 2.2a): *Grundriss*
(waagerechter Schnitt in der angegebenen Höhe, Vorgabe 0,6·h) oder
*Aufriss* (lotrechter Schnitt in Windrichtung, Boden als Wand). Das Ergebnis
sind **Verwirbelungen, Nachlauf, gegenseitige Beeinflussung und
Verschattung** wie im Windkanal: Flächen, die in der Schnittebene liegen
(Wände im Grundriss; Luv-, Leewand und Dach im Aufriss), bekommen den
zeitlich gemittelten Druckbeiwert c_p aus dem Feld statt der Zonenbeiwerte,
skaliert mit q_p(z) der Norm; die übrigen Flächen behalten die Norm. Stäbe im
Nachlauf tragen (v/v∞)² als Abschirmung. *Zellen über die Breite*,
*Reynolds-Zahl* (Modell, über etwa 300 wird das Verfahren instabil) und
*Zeitschritte* bestimmen Feinheit und Dauer; die Rechnung läuft mit
Fortschrittsbalken und ist abbrechbar. Der Bericht zeigt das c_p-Feld und das
Geschwindigkeitsfeld v/v∞ des Schnitts. Die Beiwerte sind **qualitativ** -
Modell-Reynolds-Zahl, ebener Schnitt - und gegen die Norm zu prüfen; der
Lastfall trägt die Lastfall-Nr. aus der Maske.

## 4a Elemente: was das Programm rechnen kann

Das Netz besteht aus **finiten Elementen**. Welche es gibt, steht im
Verzeichnis der Elementarten; jede Tabelle, die Ansicht, der Bericht und die
Schnittstellen fragen dieses Verzeichnis, deshalb kennt jeder Teil des
Programms jeden Typ.

| Familie | Elemente | wofür |
|---|---|---|
| **Stäbe** | beam, truss, seil | Balken (mit Schub, Gelenken, **Exzentrizität** und **Wölbkrafttorsion**), Fachwerkstab (auch **nur Zug** oder **nur Druck**), Seil |
| **Schalen** | shell3, shell4, shell6, shell8 | dünne und dicke Platten und Schalen; die quadratischen (shell6, shell8) mit Mittenknoten; **geschichtet** (Laminat) möglich |
| **Volumen** | tet4, tet10, hex8, hex20, pent6, pent15, pyr5 | Tetraeder, Hexaeder, Keil und Pyramide, linear und quadratisch |
| **Ebene Elemente** | ebene3, ebene4, ebene6, ebene8 | Scheibe (ebener Spannungszustand), ebener Dehnungszustand und **rotationssymmetrisch** (Rohr, Behälter, Fundament um eine Achse) |
| **Verbindungen** | feder, grenzschicht6/8 | Feder mit sechs Steifigkeiten in eigenen Achsen; Grenzschicht ohne Dicke (Klebefuge, weiche Lagerfuge) |

Dazu kommen Objekte ohne eigenes Netz, die im Modellbaum unter
**Verbindungen** stehen: **Punktmassen** (Masse und Drehträgheit an einem
Knoten - sie wiegen im Eigengewicht und schwingen mit), **Dämpfer**,
**Federn** (die Eigenschaft, die ein Federelement benutzt) und **starre
Körper** (RBE2: die angeschlossenen Knoten folgen einem Masterknoten starr;
RBE3: eine Last am Master verteilt sich auf die Knoten, ohne sie zu
versteifen).

**Zugband und Druckstab.** In der Stabmaske stellt „trägt nur“ auf *Zug* oder
*Druck*. Das Programm rechnet dann mit einer Iteration: Stäbe mit der falschen
Kraft fallen aus, die übrigen tragen weiter, bis sich nichts mehr ändert. Das
Protokoll nennt, wie viele Stäbe ausgefallen sind.

**Seile** rechnen nach Theorie I. Ordnung wie ein Zugband. Wählt man für den
Lastfall **Theorie III. Ordnung**, wird daraus die echte Kettenlinie: das Seil
hängt unter seinem Eigengewicht durch, der Horizontalzug folgt aus der
ungedehnten Länge (Feld „Länge₀“ in der Stabmaske; 0 = die Sehne).

**Wölbkrafttorsion.** Der Haken „Wölbkrafttorsion“ am Stab gibt jedem seiner
Knoten einen siebten Freiheitsgrad, die Verwölbung. Voraussetzung ist ein
Querschnitt mit Wölbwiderstand I_w (die Profildatenbank bringt ihn mit). Am
Lager sagt der Haken „Wölbeinspannung“, ob die Verwölbung dort behindert ist
(Stirnplatte) oder frei (Gabellagerung). Im Ergebnis stehen das **Bimoment**
und die Verwölbung je Knoten.

**Geschichtete Schalen.** Trägt eine Dicke statt eines Werts eine Liste von
Lagen (Dicke, Werkstoff, Winkel), rechnet das Programm mit den
Laminatsteifigkeiten. Ein unsymmetrischer Aufbau koppelt Dehnung und Biegung -
eine Scheibe unter Zug krümmt sich dann.

## 5 Lager: Ausfall, Schlupf, Reibung, Bettung

Jedes Lager wirkt je Freiheitsgrad **starr**, als **Feder** oder ist **frei**.
Eingestellt wird das **in der Lagermaske rechts** (Klick auf das Lager im
Modellbaum, in der Tabelle „Lager" oder in der Ansicht mit der Auswahlart
Lager; Rechtsklick auf das Symbol → „Lager bearbeiten…"): je Freiheitsgrad
Wirkung, Federsteifigkeit (Knotenlager kN/m bzw. kNm/rad, Linienlager je m,
Flächenlager je m²) und Ausfall; Schlupf, Reibung und Grenzkraft öffnet der
Knopf „Schlupf, Reibung, Grenzkraft …" (Register Lager / Kontakt →
**Nichtlinearität…** für die gewählten Knoten; auf dem Handy Modell →
Nichtlineare Lager):

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

**Bettung auf oder an Beton** — ein Vorschlag in der Lagermaske: „auf Beton
(Druckkontakt)" setzt in uz eine Feder mit der Winkler-Bettung
k_s = E_cm / d (E_cm des Betons, d die wirksame Dicke: Fugen- oder
Mörteldicke bzw. mitwirkende Betontiefe) und **Ausfall bei Zug**; „an Beton
(Schubverbund)" setzt in ux und uy die Schubbettung k_t = G / d mit
G = E_cm / (2·(1 + 0,2)). Knotenlager erhalten den Wert mal Einflussfläche,
Linienlager mal Einflussbreite, Flächenlager je m². „Bettung übernehmen"
schreibt die Zahlen in die Felder — sie sind ein Vorschlag und **vor
„Übernehmen" zu prüfen** (Vorgaben: C20/25 30 000, C30/37 33 000, C50/60
37 000 N/mm²).

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

> **Wann ein Kontaktergebnis nicht auskonvergiert ist (seit 22.09.2026).**
> Bei Reibung prüft das Programm die Haft- und Gleitzustände nach jedem
> Schritt nach. Wechseln sie immer weiter, bricht es die Nachprüfung nach 40
> Runden ab und rechnet mit dem zuletzt erreichten Zustand weiter.
>
> Bis zum 21.09.2026 meldete der Bericht in diesem Fall trotzdem
> **„konvergiert"**; der Hinweis stand allein im Kontaktprotokoll. Jetzt
> steht im Protokoll **und** im Fortschrittsbalken „Nachprüfung der Reibung
> nach 40 Zustandswechseln abgebrochen", und der Lastfall gilt als **nicht
> konvergiert**.
>
> Was das heißt: war es der **letzte** Kontaktlauf des Lastfalls, sind
> Verformung und Spannungen der Zustand, bei dem die Nachprüfung aufgegeben
> hat — kein Nachweis. Mit Fließen rechnet ein Lastfall viele Kontaktläufe
> (am Drehlager zwölf); seit dem 22.09.2026 trägt die Meldung darum ihren
> Lauf („… abgebrochen (Kontaktlauf 7)"), und das Ergebnis sagt, ob der
> letzte Lauf konvergiert ist — auch nach einem Abbruch der Kontaktiteration.
> Vorher wurden gleichlautende Meldungen zu einer zusammengefasst, und das
> ließ sich nicht mehr entscheiden. In den Warnungen des Berichts werden sie
> weiterhin gebündelt: die Laufnummer gehört zum Ergebnis, nicht zur Art der
> Meldung.
>
> Am Drehlagerbeispiel hat die Nachprüfung der Reibung im ersten Lastfall in
> **mindestens einem** der zwölf Kontaktläufe nach 40 Zustandswechseln
> aufgegeben. Ob der letzte betroffen ist, aus dem Verformung und Spannung
> stammen, ist nicht belegt. Die einzige Reibstelle dort ist das
> Flächenlager „Starr" mit μ = 0,1; alle zwölf Kontaktpaare haben μ = 0.
> (Eine frühere Fassung sagte hier „derselbe Lauf gibt dasselbe Ergebnis".
> Bitgleich ist er nicht; am Drehlager nahm das ausgelieferte Programm aber in
> drei Läufen denselben Weg, höchstens 0,0004 N/mm² auseinander — siehe „Zwei
> Läufe desselben Modells" weiter unten; Nachprüfung der Lösersitzung vom 22.09.2026.)
>
> Was hilft, ist offen. Mit einer zehnfach kleineren automatischen
> Kontaktsteifigkeit steht die Abbruchmeldung am Drehlager genauso im
> Protokoll (ein Lauf, 22.09.2026). Ob sie Zeit kostet, ist nicht belegt:
> der eine Lauf brauchte 8,6 % länger, lief aber unter Fremdlast, und
> gleichwertige Läufe streuten an diesem Abend um 3 bis 17 %. Der Rat, die
> Kontaktsteifigkeit zu senken, stand hier bis dahin und ist zurückgenommen. Zu versuchen bleiben ein kleinerer
> Reibbeiwert und ein feineres Netz in der Fuge — beides ungemessen.

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

**Z-Achse nach unten (RFEM).** RFEM legt seine Modelle mit der Z-Achse nach
unten an. Das Programm rechnet mit z nach oben. Im Importdialog für .rf6,
.rf5, .rs6 und .rs5 steht darum der Haken „Z-Achse der Datei zeigt nach
unten“ (vorbelegt). Er dreht das Modell beim Einlesen um 180° um die
x-Achse: (x, y, z) → (x, −y, −z). Eine bloße Spiegelung z → −z wäre
falsch, sie machte aus dem rechtshändigen System ein linkshändiges — Momente
und Drehwinkel liefen dann verkehrt. Mitgedreht werden Knoten, Bögen,
Lastvektoren, Richtungen, Lastfenster, Schwerkraft, Zwangsverformungen und
Lagerwerte; das Protokoll vermerkt es. Beim Anhängen an ein vorhandenes
Modell ist der Haken gesperrt.

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
| `.rf6` | RFEM 6 Projektdatei | Knoten, Linien, Stäbe mit Typ, Flächen mit Dicke, Volumenkörper, Lager mit Nichtlinearität, Gelenke, Kontaktbedingungen, Lastfälle mit Flächenlasten |
| `.step`/`.iges`/`.stl` | CAD | Vernetzung mit gmsh (Volumen oder Schale) |

Eine **RFEM-6-Projektdatei** (`.rf6`) wird unmittelbar gelesen – kein Export
nötig. Übernommen werden Knoten, Linien, Stäbe, **jede Fläche und jeder
Volumenkörper als Objekt** (mit Randlinien, Dicke und Werkstoff), die Lager,
die Kontaktbedingungen, alle Lastfälle mit ihren Lasten (Vorspannung als
gleichwertige Temperaturlast), die Kombinationen und die **Netzeinstellungen**
aus `mesh.xml`. Was kein Netz bekommen konnte, steht trotzdem im Modellbaum
und lässt sich dort vernetzen. Während des Lesens zeigt die Statuszeile den
Fortschrittsbalken mit den Phasen (Behälter öffnen, Knoten, Linien, Stäbe,
Lager, Flächen, Volumen, Freigaben, Lastfälle, Lasten, Kombinationen, Modell
prüfen, Ansicht aufbauen); das Drehlager ist in rund einer Sekunde gelesen,
das Vernetzen danach ist die eigentliche Arbeit und hat seinen eigenen
Balken.

**Krumme Linien** kommen mit ihrer wahren Form: Bögen, Kreise, Parabeln,
Ellipsen und NURBS werden über ihre Kontrollpunkte gelesen, nicht als Sehne
durch die Stützknoten. Das ist keine Kleinigkeit der Darstellung — eine
Bohrung, eine Buchse, ein Bolzen oder ein Augenblech besteht in RFEM aus
*zwei Halbbögen zwischen denselben zwei Knoten*; über die Knoten allein wäre
das kein Polygon, und die Fläche fehlte im Bild wie im Modellbaum.

**Aufeinanderliegende Knoten werden nicht zusammengeführt.** In einem
RFEM-Volumenmodell liegen sie an jeder Kontaktfuge und jeder Kontaktbedingung
absichtlich aufeinander; verschweißt wäre das Modell dort zu steif und die
Freigaben liefen ins Leere. Wie viele es sind, steht im Protokoll; wer sie
doch zusammenführen will, liest die Datei mit `merge_nodes=True`. Was gar nicht ging, steht Zeile für Zeile im
Importprotokoll; Einzelheiten im Schnittstellenhandbuch. Die älteren nativen Formate (`.rf5`, `.rs6`, `.fem`)
werden untersucht und, soweit ihr Behälter zugänglich ist, ausgelesen –
andernfalls nennt das Programm den Exportweg (RFEM: IFC-Statikmodell, SAF oder
Tabellen; InfoCAD: IFC-Statikmodell oder DXF).

Aus HiCAD übernommene Stäbe enden an der **Außenkante** des angeschlossenen
Bauteils – ihre Achsen laufen um die halbe Profilhöhe daneben vorbei, das Modell
zerfällt zunächst in Teile. Unter **Start → Modell prüfen**
schließt „Freie Stabenden anschließen" (Suchradius 60 mm) jedes freie Ende an die
Achse des nächsten Stabes an und teilt diesen dort; der Versatz steht im
Protokoll, die Ausmitte des Anschlusses wird nicht abgebildet.

**Der Import ändert die Struktur nicht** (18.09.2026). Das RFEM-Modell kommt
so herein, wie es ist: keine Vorschläge, keine Umstellungen, kein Fenster mit
Änderungen. Der Grund steht in der Sache: Eine Schraube braucht den
Nullspalt, weil sie ihre Zugkraft über Schub und Mantelreibung überträgt, ein
Passstift braucht Spiel — am Modell sind die beiden nicht zu unterscheiden.
Wer eine Fuge anders haben will, stellt sie an ihrer **Kontaktbedingung** ein
(siehe *Geometrischer Spalt an der Fuge*).

**Integrierte Knoten und Linien, Stabenden auf Volumen.** RFEM integriert
einen Knoten, der auf einer Fläche liegt, in deren Netz: ein Zugstab, der in
der Mitte der Stirnfläche eines Schraubenvolumens endet, hängt dort am
Volumen. Der Import liest diese Angaben seit dem 16.09.2026 mit (am
Drehlager: 168 integrierte Knoten an 142 Flächen, 394 integrierte Linien an
14 Flächen — die Kreise der starren Scheiben auf Deckeln und Ringen; 112 der
128 Stabenden sind integrierte Knoten). Vorher endeten alle 64 Zugstäbe der
Deckel- und Augenschrauben an keinem Element: das eine Ende hing an seiner
starren Kreisscheibe, das andere lag genau in der Mitte der Stirnfläche des
Schraubenvolumens (Knoten 1093 auf V49) und an nichts. Die Schrauben trugen
keinen Zug, die Deckel V33 und V35 hoben ab, die Kontakt-Iteration brach ab.
Nach dem Vernetzen hängt jetzt jeder Knoten, der auf oder in einem
vernetzten Volumen liegt und an dem etwas hängt — ein Stabende, eine
Knotenlast, ein Lager, integriert oder nicht —, über starre Kopplungen an
den Knoten des Elements dort (ein integrierter Knoten, an dem nichts hängt,
bleibt frei: er trägt nichts, und jede Straffeder mehr kostet Rechengenauigkeit): drei Knoten auf einer Seitenfläche, vier im
Innern, einer, wenn er mit einem Netzknoten zusammenfällt; bis 0,1 mm
Abstand gilt ein Punkt noch als „auf" der Seite. Das ist dieselbe Umsetzung
wie bei der starren Scheibe, und sie entspricht dem integrierten Knoten in
RFEM. Das Protokoll nennt jeden Anschluss („2 Knoten an Volumen
angeschlossen (Stabende) … Zug (K211) → V1"). Ein Stabende an keinem Volumen
(Ankerstab im Fundament, Kragarm) bleibt frei; ein Knoten, der schon in einer
Kopplung steht (Mitte einer starren Scheibe), wird nicht doppelt
angeschlossen. Beim Öffnen einer älteren Datei mit Netz wird der Anschluss
nachgeholt (Protokoll unten). Die integrierten Linien stehen an der Fläche
(Modelldatei); das Netz folgt ihnen noch nicht — für die starren Scheiben
ist das ohne Folge, ihre Kopplung nimmt die Netzknoten innerhalb des
Kreises.

## 8 Nachweise nach EC3

Stäbe (Kette von Stabelementen) werden beim Erzeugen von Stabzügen und beim
Import automatisch angelegt („Stäbe automatisch erkennen“ verkettet
kollineare Elemente gleichen Querschnitts). Je Stab:

* Querschnittsnachweise an allen Nachweisstellen (Klasse, N, V, M, M+V, M+N,
  Torsion, Vergleichsspannung),
* **Wölbkrafttorsion** bei offenen Querschnitten (I, U): das Torsionsmoment
  wird in den St.-Venant-Anteil und den Wölbanteil aufgeteilt, das
  Wölbbimoment B und die Wölbnormalspannung σ_w werden ausgewiesen und gehen
  in die Vergleichsspannung ein. In der Stabmaske steht dazu, ob die
  Verwölbung am Anfang und am Ende **frei** (Gabellagerung, freies Ende) oder
  **behindert** (Einspannung, Stirnplatte) ist. Vorgabe ist frei/frei — dann
  ändert sich bei konstantem Torsionsmoment nichts. Warum das wichtig ist,
  sagt EC3 selbst: bei I- und H-Profilen darf die St.-Venant-Torsion
  vernachlässigt werden (6.2.7(7)) — es trägt die Wölbkrafttorsion.
* Biegeknicken um y und z (Knicklängen βy·L, βz·L oder explizit),
  Drillknicken, Biegedrillknicken (L_LT, kz, kw, C1 automatisch aus dem
  Momentenverlauf, Lastangriff oben/unten), Interaktion Gl. 6.61/6.62,
* Ermüdung: Kerbfall wählen (Δσc mit Beispielen aus den Tabellen 8.1–8.5),
  Schadensfolge/Konzept für γMf; Ermüdungslasten im Register Lastfälle.

**Eine Ermüdungslast beschreibt entweder zwei Zustände oder einen Verlauf.**
Ein Zustand darf ein Lastfall **oder eine Kombination** sein — die
FAT-Kombinationen aus RFEM sind Kombinationen, und der Nachweis liest beide
aus den Ergebnissen (bis 13.09.2026 wies die Modellprüfung eine Kombination
als „Lastfall unbekannt“ ab; am CBG-Trolley 20 Meldungen).
*Zwei Zustände*: der Lastwechsel pendelt zwischen oben und unten, mit einer
Lastspielzahl — das reicht, solange es wirklich nur zwei Zustände gibt.
*Verlauf*: eine **Folge von Lastfällen** (oder Kombinationen) und die Zahl
der Wiederholungen. Das **Zählverfahren** bestimmt, was aus dem Verlauf wird:

* **spanne** (Vorgabe): eine Stufe mit der Schwingbreite Maximum minus
  Minimum über alle Zustände, ein Spiel je Wiederholung — so bildet RFEM die
  Ermüdungsschwingbreite einer Ergebniskombination, und so kommen die
  Ermüdungslasten aus dem RFEM-Import. Die Reihenfolge der Zustände spielt
  keine Rolle; bei zwei Zuständen ist es dasselbe wie „zwei Zustände".
* **rainflow** / **reservoir** (EN 1993-1-9, Anhang A): für eine echte
  Zeitfolge (Überfahrt, Öffnungsvorgang, Betriebszyklus). Die Zwischenstufen
  tragen eigene, kleinere Spiele bei, und die zählen mit. Lassen Sie den
  Verlauf am größten Wert beginnen und enden — dann liefern beide dasselbe
  Kollektiv und nur ganze Spiele; sonst bleibt bei Rainflow ein Rest, der mit
  halben Spielen zählt (bei nur zwei Zuständen ein halbes Spiel, also die
  halbe Schädigung von „spanne").

Die Schadensakkumulation ist immer Palmgren-Miner über alle Lasten am Ort.

**Grundlast.** Ein Lastfall mit dem Haken „Grundlast“ (Maske Lastfall) wirkt
in jeder direkt gelösten Rechnung mit: in Modellen mit Kontakt oder
Ausfallstäben bei jedem Lastfall, jeder Kombination und jedem Zustand einer
Ermüdungslast, auch ohne dort genannt zu sein. Das ist der Platz für die
Vorspannung der Anker (Lastfall der Art P mit Lasten → Vorspannung) und für
ein ständiges Eigengewicht: ohne sie hätte jeder der 164 Ermüdungszustände
des Drehlagers einen anderen Kontaktzustand. Das Protokoll nennt bei jeder
Rechnung, welche Grundlast mitwirkt; in einem linearen Modell (ohne
Kontakt) bleibt der Lastfall ein gewöhnlicher Lastfall der Überlagerung.
Geprüft am Block mit Reibung: Auflast als Grundlast, Horizontalkraft allein
gerechnet, ergibt dasselbe wie die Kombination aus beiden
(`tests/test_kontaktzustand.py`).

**Kontaktzustand der Ermüdungszustände.** In Modellen mit Kontakt rechnet
das Programm von jeder Ermüdungslast nur den ersten Zustand nichtlinear
(Kontakt-Iteration); die weiteren Zustände übernehmen seinen Kontaktzustand
— welche Knoten anliegen, haften oder gleiten — unverändert und werden damit
linear gelöst: eine Rückwärtseinsetzung statt 30 bis 40 Kontaktschritten je
Zustand. Das setzt voraus, dass die Zustände einer Ermüdungslast kleine
Änderungen um einen Betriebszustand sind; ein Zustand mit ganz anderem
Kontaktbild (abhebende Bauteile) gehört in eine eigene Ermüdungslast, oder
die Einstellung wird abgeschaltet: Nachweise → Konfiguration, Haken
„Ermüdungszustände mit eingefrorenem Kontaktzustand rechnen“. Das Protokoll
nennt zu Beginn der Rechnung, wie viele Zustände so gerechnet werden, und je
Zustand „Kontaktzustand eingefroren“. Geprüft am Block mit Reibung: der
zweite Zustand (1,1-fache Horizontalkraft) weicht eingefroren um 7 % von der
nichtlinearen Lösung ab und braucht keine Faktorisierung. Am Drehlager
(12.09.2026, Zustände LF401 → LF404 einer Zugüberfahrt): der nichtlineare
Zustand 1055–1209 s mit 41–42 Kontaktschritten, der eingefrorene 250 s —
davon 15 s die Lösung (eine Rückwärtseinsetzung ohne Faktorisierung) und
235 s der Nachlauf, die Spannungen der 1,8 Mio. Elemente, der jeden Zustand
gleich trifft; Verschiebungen auf 0,16 % gleich, Spannungen im Median
gleich, 99 % der Elemente innerhalb 0,1 N/mm² — nur an einer
Spannungsspitze (4656 N/mm², Kopplung) weichen 216 N/mm² ab.

**Lastspielzahl.** Die Lastspiele bzw. Wiederholungen jeder Ermüdungslast
sind entweder eigene Werte oder — Haken „globale Lastspielzahl" im Dialog —
die **globale Lastspielzahl** aus Nachweise → Konfiguration (Vorgabe 2·10⁶;
dort steht auch der Bezugszeitraum in Jahren für die Lebensdauer). So wird
die Zahl einmal für alle Lasten gesetzt und je Nachweis überschrieben; die
Tabelle Ermüdungslasten zeigt „global", wo die globale gilt. 0
Wiederholungen heißt: die Last ist unwirksam — so bleiben die Sammlungen aus
dem RFEM-Import stehen, ohne doppelt zu zählen.

**Kerbfälle vorschlagen** (Nachweise → Führen → Kerbfälle vorschlagen; beim
RFEM-Import automatisch): Schweißnähte des Modells liefern den Kerbfall ihrer
Stäbe; Zugstäbe mit Rundquerschnitt bekommen 50 N/mm² (Tabelle 8.1, Kerbfall
14: Stange mit Gewinde unter Zug), gewalzte Querschnitte 160 N/mm² (Kerbfall
1, Grundwerkstoff), Volumen 160 N/mm² (Grundwerkstoff, Strukturspannung) und
an verschweißten Berührungsstellen 90 N/mm² (Anhang B, Tabelle B.1, Detail 7:
Kreuzstoß mit tragenden Kehlnähten; voll durchgeschweißt wäre Detail 3 mit
100). Das sind Vorschläge: die Stabtabelle zeigt „(Vorschlag)", Volumenmaske und
-dialog sagen es im Hinweis. Eine Eingabe in Maske, Tabelle oder Dialog
bestätigt den Wert, und ein bestätigter Wert wird von „Kerbfälle vorschlagen"
nicht mehr überschrieben. Anschlüsse, Steifen und Nähte mindern den Kerbfall
— das Programm kennt sie nur, wenn sie als Schweißnaht oder Anschluss
eingegeben sind.

**Ermüdung für Volumen.** Ein Volumen mit Kerbfall (Maske Volumen, Feld
„Kerbfall Ermüdung"; Tabelle Volumen, Spalte Kerbfall; Dialog Volumenkörper)
wird mit nachgewiesen: je Element und Zustand die vorzeichenbehaftete
Hauptspannung mit dem größten Betrag, daraus das Kollektiv wie beim Stab,
Schädigung nach Miner mit der Wöhlerlinie für Normalspannungen, maßgebend das
Element mit dem größten D. Das Ergebnis steht in der Tabelle Ermüdung
(„Volumen V1", ein Klick wählt den Körper), in der Färbung „Ausnutzung
Ermüdung" je Element und im Bericht (Block „Ermüdungsnachweis Volumen"). Die
Spannung im Element ist eine Struktur- oder Kerbspannung, keine Nennspannung
— der Kerbfall muss dazu passen (Theoriehandbuch 5.5-3).

**Berührungsstellen zwischen Volumen.** Wo zwei Volumen Knoten teilen — der
Vernetzer teilt sie nur über eine gemeinsame Fläche, in RFEM ist das ein
durchverbundener Stoß — und keine Kontaktbedingung zwischen beiden
eingegeben ist, gilt die Stelle als verschweißt: die Elemente mit einem
solchen Knoten rechnen mit dem Feld „Kerbfall Naht" des Volumens (Maske,
Tabelle Volumen, Dialog; leer = wie Kerbfall). Eine eingegebene
Kontaktbedingung zwischen den beiden Körpern macht die Stelle zur Fuge, eine
ausgeführte verdoppelt die Knoten ohnehin. Tabelle und Bericht nennen beide
Kerbfälle („160 / Naht 90"), die Zahl der Elemente an Berührungsstellen und
ob das maßgebende Element dort liegt. Am Drehlager: 47 gemeinsame Flächen
zwischen 25 Körperpaaren, keine davon mit Kontaktbedingung.

**Die Schädigung wird am Ort aufsummiert**, nicht über Orte hinweg: D wird an
jeder Nachweisstelle und an jedem der vier Querschnittseckpunkte gebildet,
maßgebend ist der größte Wert, und der Ort steht im Nachweis. Die größten
Schwingbreiten verschiedener Ermüdungslasten liegen im Allgemeinen an
verschiedenen Stellen; ihre Summe gehört zu keinem Punkt des Bauteils.

Im Bericht steht die Miner-Summe **Stufe für Stufe**: je Stufe Schwingbreite,
Lastspielzahl, ertragbare Lastspielzahl N_R, der Anteil D_i = n/N und die
laufende Summe. Stufen unter dem Schwellenwert stehen mit D_i = 0 darin — sie
sind nicht verschwiegen, sondern nachweislich unschädlich. Ist ein
Bezugszeitraum eingestellt (die Lastspielzahlen gelten für so viele Jahre),
weist der Bericht zusätzlich die rechnerische **Lebensdauer** aus:
Bezugszeitraum / D.

Ergebnis: Tabelle „Nachweise EC3“ mit Ausnutzung, maßgebendem Nachweis,
Kombination und Stelle; Färbung „Ausnutzung EC3“ im Viewport; alle Details
im Bericht.

### Schwingungsnachweis des Verschlusses

*Nachweise → Schwingung → Verschluss* (Ergebnis unten in der Tabelle
„Schwingung“, Eigenformen im Wasser in der Ansicht, Erläuterung im Protokoll
und im Bericht). Der Nachweis nimmt **benetzte Flächen, Wasserstände und
Strömung aus einem Wasserdruck-Generierer** - deshalb zuerst den Wasserdruck
anlegen (mit „unterströmt“ bzw. „überströmt“ für die Strömungsgeschwindigkeit
und c_p' > 0 für die Druckschwankung).

| Angabe | Bedeutung |
|---|---|
| Wasserdruck | Generierer, dessen Flächen, Situation, Wasserstände und Strömung gelten |
| Eigenformen | Anzahl der gerechneten Eigenfrequenzen |
| Hydrodynamische Masse | mitschwingendes Wasser nach Westergaard (m'' = 7/8·ρ·√(H·y)) auf den benetzten Flächen, je Wasserseite, in Richtung der Flächennormalen |
| Dämpfungsgrad ζ | Lehrsches Dämpfungsmaß (Stahlwasserbau 0,01 … 0,03; im Wasser eher mehr) |
| Strouhal-Zahl St, Kantenbreite d | Wirbelablösung f_s = St·v/d an der Unterkante bzw. Dichtung; d ist die Breite der Kante in Strömungsrichtung (leer = Blechdicke) |
| Grenze V_r | reduzierte Geschwindigkeit V_r = v/(f·d); unterhalb der Grenze (≈ 1) sind instabilitäts- oder bewegungsinduzierte Schwingungen nicht zu erwarten |
| Resonanzband | ± um f_s: liegt eine Eigenfrequenz darin, gilt der Nachweis als nicht erfüllt |
| Betrieb, Nutzungsdauer, Kerbfall, γ_Mf, γ_Ff | Ermüdung aus der Antwort auf die Druckschwankung: N = f_s·t Lastspiele, Δσ = 2·V·σ_amp, D = N/N_R ≤ 1 (EN 1993-1-9) |

Die Tabelle nennt je Eigenform f in Luft und im Wasser, das modale
Massenverhältnis m_h/m, V_r, f_s/f, die Vergrößerungsfunktion V und die
Beurteilung (unkritisch, Hinweis V_r, Resonanz). Der Bericht (Kapitel
„Schwingungsnachweis des Verschlusses“) enthält Angaben, Modentabelle,
Antwort auf die Druckschwankung mit Ermüdung, die Erläuterung und das
**Frequenzbild** (Eigenfrequenzen nass und trocken, Band der Wirbelablösung,
Grenze V_r) samt der Westergaard-Verteilung über die Höhe. Die Angaben
bleiben im Modell und werden mit der Datei gespeichert.

### Knicklängen aus der Knickfigur

*Nachweise → Knicklängen → Aus Knickfigur* (oder die Tabelle „Knicklängen“
unten, Gruppe *Nachweise*). Das Programm löst das Verzweigungsproblem —
Grundzustand ist die in der Ergebnismaske gewählte Kombination, sonst der
aktive Lastfall; liegt schon ein Knickergebnis vor, wird die dort gewählte
Knickfigur ausgewertet — und bestimmt für jeden Stab mit Nachweis die Werte
der Tabelle unten. Muss das Verzweigungsproblem erst gelöst werden, läuft es
wie jede Rechnung im Hintergrund, mit Abnahme des Netzes, Balken und
Abbrechen; die Knicklängen erscheinen, sobald es gelöst ist. Bis zum
11.09.2026 rechnete der Knopf im Fenster selbst: am Drehlager-Modell
(2 Mio. Elemente) stand die Oberfläche dabei über fünf Minuten ohne Balken.

| Spalte | Bedeutung |
|---|---|
| N_Ed | die maßgebende Druckkraft des Stabs im Grundzustand |
| α_cr, N_cr | Verzweigungslastfaktor der Knickfigur und N_cr = α_cr·\|N_Ed\| |
| Achse | um welche Achse der Stab in der Knickfigur biegt (aus der Eigenform) |
| L_cr, β | L_cr = π·√(E·I/N_cr), β = L_cr/L für diese Achse; die andere bleibt offen |
| Beteiligung | Anteil des Stabs an der Formänderungsenergie der Knickfigur |

Ein Stab, der in der Knickfigur gerade bleibt (Beteiligung unter 5 %),
bekommt seinen Wert nur als **Obergrenze** gekennzeichnet — die Formel
setzt voraus, dass er es ist, der ausknickt. Für solche Stäbe eine höhere
Knickfigur wählen (Ergebnismaske) und erneut ermitteln. **β übernehmen**
schreibt die Beiwerte der beteiligten Stäbe in die Stäbe; die
Stabilitätsnachweise rechnen dann damit (Rückgängig nimmt es zurück). Die
Tabelle steht auch im Bericht.

### Schweißnähte und Kerbfälle

*Nachweise → Führen → Schweißnähte…* oder Modellbaum → Stäbe → Schweißnähte →
„+ Schweißnaht anlegen“ (Tabelle unten in der Gruppe *Modell*). Vorher die
Stäbe (Auswahlart Stab), Linien oder Flächen wählen, an denen die Naht
liegt, dann „Auswahl übernehmen“.

| Angabe | Bedeutung |
|---|---|
| Nahtart | Stumpfnaht, HV-/DHV-Naht (durchgeschweißt), Kehlnaht, Doppelkehlnaht, Steifenanschluss (Quersteife), Längssteife, Deckblech-Ende |
| Lage | längs oder quer zur Beanspruchung |
| a, t, ℓ | Nahtdicke (Kehlnaht), Blechdicke (Größeneinfluss ab 25 mm, Deckblechdicke), Anschlussbreite in Beanspruchungsrichtung (Steifen, Kreuzstoß) |
| Ausführung, Merkmale | automatisch / mit Ansatzstellen / von Hand; blecheben bearbeitet, geprüft, einseitig, Gegenlage, unterbrochen, Freischnitte |
| äquivalent | Ersatznaht: steht für alle nicht einzeln modellierten Nähte; ohne Zuordnung gilt sie für alle Stäbe, ungünstigere Einzelnähte gehen vor |
| Kerbfall Vorgabe | überschreibt den Wert aus der Nahtart (z. B. aus einer Detailtabelle, die das Programm nicht kennt) |

**Kerbfall ermitteln** zeigt Δσ_C und Δτ_C mit der Fundstelle in DIN EN
1993-1-9 (Tabellen 8.2 bis 8.5, Größeneinfluss k_s = (25/t)^0,2); die
Erläuterung steht im Protokoll. **Übernehmen** schreibt jedem betroffenen
Stab den ungünstigsten Kerbfall aller seiner Nähte - damit rechnet der
Ermüdungsnachweis. Stäbe ohne Naht behalten die Angabe aus der Stabmaske.
Der Schwingungsnachweis des Verschlusses kann seinen Kerbfall „aus
Schweißnähten“ nehmen (Nähte an den benetzten Flächen). Der Bericht führt
im Kapitel System die Nähte und die Kerbfälle der Stäbe auf.

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
* **Erzeugnisdicke**: Die Streckgrenze hängt nach EN 1993-1-1 Tab. 3.1 von der
  Erzeugnisdicke ab (S355: über 40 mm 335 statt 355 N/mm²). Bleibt das Feld
  auf 0, nimmt Statik3D die kleinste Abmessung des ganzen Körpers, zu dem die
  Elemente gehören — bei einem massiven Bauteil ist das richtig. Ist das
  Bauteil aus Blechen **geschweißt**, ist es zu viel: dann die Blechdicke
  eintragen. Die angesetzte Dicke steht im Bericht in der Spalte *t* (mit `*`,
  wenn sie selbst angegeben wurde), und wenn sie f_y abmindert, sagt der
  Bericht es als Hinweis. Bis zum 22.09.2026 rechnete der Volumennachweis
  immer mit der dünnsten Stufe — η fiel bei dicken Bauteilen 6 % zu klein aus.

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

### Theorie je Lastfall und Kombination: I., II., III. Ordnung

Im Lastfall- und im Kombinationsdialog steht das Feld **Theorie**:

| Wahl | Rechnung |
|---|---|
| wie Einstellung | Lastfälle linear; GZT-Kombinationen nach der Einstellung *Nachweise → Konfiguration* (aus / automatisch nach 5.2.1(3) / ein) |
| I. Ordnung | linear, Superposition |
| II. Ordnung | Gleichgewicht am verformten System mit geometrischer Steifigkeit und Ersatzimperfektionen (5.2, 5.3) — immer, unabhängig von der Einstellung |
| III. Ordnung | **große Verformungen** und endliche Drehungen (geometrisch nichtlinear, korotational), Newton-Raphson in Laststufen (Anzahl in der Konfiguration) — nur für Stabtragwerke, ohne Kontakt und Zwangsverformungen |

Nach II. und III. Ordnung gilt keine Superposition: der Lastfall bzw. die
Kombination wird einzeln gerechnet und ersetzt das lineare Ergebnis. Die
Tabellen unten und der Modellbaum zeigen die Wahl; der Bericht führt je
Lastfall und Kombination die Theorie und für III. Ordnung Laststufen,
Iterationen, Residuum, u_max nach I. und III. Ordnung und die größte
Drehung auf.

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

> **Zwei Läufe desselben Modells können sich unterscheiden — und das ist kein
> Fehler (gemessen 22.09.2026).** Der Gleichungslöser summiert die
> Faktorisierung auf mehrere Kerne auf. Wie die Arbeit dabei auf die Kerne
> fällt, hängt am Zeitverhalten des Rechners, und damit die letzten Stellen:
> mit **einem** Kern kommen dreimal bitgleiche Ergebnisse heraus, mit
> sechzehn nicht (Abweichung rund 5·10⁻¹⁶ vom Betrag).
>
> **Am Drehlager, gemessen:** Das ausgelieferte Programm (unsymmetrische Zerlegung) hat am Drehlager in **drei** Läufen von LF1 denselben Kontaktweg genommen — 150 Schritte, 145 Faktorisierungen —, und die Spannungen lagen höchstens **0,0004 N/mm²** auseinander (Verschiebungen relativ 4,3·10⁻⁷): nicht bitgleich, aber derselbe Weg.
> Auseinandergelaufen sind nur zwei Läufe einer **Versuchsfassung mit
> symmetrischer Zerlegung**, die nicht ausgeliefert wird: sie nahmen
> verschiedene Kontaktwege und wichen um bis zu 273 N/mm² voneinander ab. Der
> Verdacht fällt auf die ungesetzten Vorgaben dieser Zerlegung (einer der
> beiden lief außerdem unter starker Fremdlast) — bewiesen ist das mit zwei
> Läufen nicht. (Eine frühere Fassung sprach hier von „derselbe Lauf, 150
> oder 162 Kontaktschritte, vierte Stelle der Verformung"; die beiden Läufe
> stammten aus zwei verschiedenen Programmständen. Nachprüfung der Lösersitzung vom 22.09.2026.)
>
> **Wenn zwei Läufe streng vergleichbar sein müssen** — etwa um zu belegen,
> dass eine Änderung am Modell nichts am Ergebnis ändert —, setzen Sie vor
> dem Start die Umgebungsvariable `MKL_CBWR=AUTO`. An einem Prüfgitter rechnet
> der Löser damit bitgleich, auf **dieser** Maschine, und kostet rund 13 %
> mehr Zeit. Ob das am Drehlager die Kontaktwege gleich macht, ist nicht
> gemessen; die Lösersitzung misst es gerade. In der Auslieferung steht die
> Variable nicht.

* **Alle Lastfälle + Kombinationen**: Standard. Eine Faktorisierung, alle
  Lastfälle, Superposition, Umhüllende, optional Nachweise.
* **Nur aktiver Lastfall**, **Eigenschwingungen**, **Knicken** (Grundzustand
  = aktiver Lastfall).
* **Gleichungslöser** (Auswahl in *Berechnung → Einstellungen*): Vorgabe
  **automatisch** = MKL PARDISO, sonst CHOLMOD, sonst SuperLU. **Weicht
  „automatisch“ aus, steht der Grund im Protokoll** — bei der Grundfaktorisierung
  in der Zeile „Faktorisiert (SuperLU (ausgewichen - PARDISO: …), …)“, bei den
  Faktorisierungen der Kontaktschritte als eigene Zeile „Gleichungslöser
  ausgewichen - …“, einmal je Lastfall. Ein Grund ist dabei jeder Weg vorbei an
  PARDISO: eine Ausnahme, die 32-Bit-Grenze der Schnittstelle, ein installiertes,
  aber scheiterndes CHOLMOD. **Noch nicht** zurück kommt die Meldung aus
  Lastfällen, die in Rechenketten laufen; die rechnen seit dem 22.09.2026 aber
  mit denselben Einstellungen wie der Hauptprozess (vorher begann jede Kette mit
  „automatisch“, auch wenn „MKL PARDISO“ eingestellt war, und wich still aus,
  wo die Rechnung sonst abgebrochen hätte). Bis zum 22.09.2026 wurde ein
  Fehler von PARDISO bei „automatisch“ ohne eine Zeile verworfen; am Drehlager
  scheiterte danach SuperLU selbst („Can't expand MemType 0“), und warum PARDISO
  nicht gerechnet hatte, war nicht mehr festzustellen. Scheitern beide aus einem
  anderen Grund als einer singulären Matrix, bricht die Rechnung mit **beiden**
  Gründen ab und nennt MUMPS oder ama als Ausweg — SuperLU reicht für große
  Modelle nicht. Eine singuläre Matrix wird weiter als solche gemeldet
  („Lagerung prüfen“). Zur Wahl
  stehen **MKL PARDISO** (direkt, mehrkernig — angefordert werden alle Kerne
  bis auf einen, MKL selbst kappt auf die physischen Kerne: 16 auf einem
  Rechner mit 16 Kernen / 32 Threads),
  **CHOLMOD** (direkt, Cholesky, mehrkernig über BLAS), **UMFPACK** (direkt,
  LU), **MUMPS** (direkt, mehrkernig), **ama** (eigener Kern in Rust, direkt,
  mehrkernig: multifrontale LDLᵀ mit Superknoten, symmetrische Jacobi-Skalierung und
  statischer Pivotisierung wie PARDISO; Projekt `Gleichungsloeser`, Installation als
  Wheel `pip install ama-…-win_amd64.whl` in die Python-Umgebung von Statik3D, kein
  Fremdlizenztext nötig; nur für symmetrische Matrizen, sonst bricht die Rechnung mit
  Hinweis auf PARDISO/MUMPS ab. Gemessen 18.09.2026 gegen PARDISO: `cbg.json` 0,45 s
  statt 0,57 s, `modellimport_rf6.json` 0,17 s statt 0,28 s, Verschiebungen gleich auf
  4e-10 relativ), **PyAMG** (iterativ:
  algebraisches Mehrgitter mit CG — speicherarm, aber je rechte Seite neu zu
  iterieren und einkernig) und **SuperLU** (direkt, einkernig, Rückfall).
  **In der exe stecken** MKL PARDISO, ama, PyAMG und SuperLU (PyAMG ist
  MIT-lizenziert, ama ist eigener Kern ohne Fremdlizenz); **MUMPS**
  (CeCILL-C) lädt das Programm beim Start nach (Kästchen im Dialog
  *Vernetzer, Nachbesserer und Gleichungslöser*, Abschnitt „Vernetzer und
  Nachbesserer nachladen“) — der Selbsttest des Baus rechnet das
  Rahmenbeispiel mit jedem mitgelieferten Löser und vergleicht. Geprüft in
  `tests/test_loeser.py` (jeder vorhandene Löser trifft N·L/(E·A)).
* **Was nicht da ist, sagt warum** (19.09.2026). Ein fehlender Löser stand
  bis dahin nur grau als „(nicht installiert)“ in der Liste; warum und was zu
  tun wäre, stand nirgends — der Anwender sah „Gleichungslöser, die mir
  angezeigt werden, die ich aber nicht wählen kann und auch nicht
  installieren“. Jetzt steht der Grund im Eintrag und der ganze Weg im
  Hinweis darunter, und es sind drei verschiedene Gründe:

  | Löser | Eintrag sagt | dahinter steckt |
  |---|---|---|
  | MUMPS | *Extras → Vernetzer installieren…* | nachladbar — danach steht er sofort in der Liste, ohne Neustart |
  | CHOLMOD, UMFPACK | *GPL — nur mit eigenem Python* | die Lizenz verbietet das Mitliefern; wer aus dem Quelltext startet: `pip install scikit-sparse` bzw. `scikit-umfpack` |
  | MKL PARDISO, ama, PyAMG | `pip install …` bzw. *gehört in die exe — bitte melden* | mitgeliefert; fehlt so einer in der exe, ist der Bau fehlerhaft |
  | SuperLU | *scipy fehlt* | kann gar nicht fehlen — dann ist die Installation beschädigt |

  **ama fehlte tatsächlich in der exe.** Er stand weder in der Bauvorschrift
  `packaging/Statik3D.spec` noch im Bauablauf, und er kommt von keinem
  Paketserver: das Rad liegt seit dem 19.09.2026 als
  `packaging/ama-0.1.0-cp311-cp311-win_amd64.whl` im Baum und wird beim Bau
  eingespielt — genau wie das MUMPS-Rad. Geprüft in `tests/test_loeser.py`
  (jeder Löser hat eine Herkunftsangabe; Bauvorschrift und Bauablauf nennen
  das Rad, das wirklich dort liegt).
* **Genauigkeit des Gleichungslösers** (*Berechnung → Einstellungen*,
  17.09.2026): bis zu diesem relativen Residuum |K·u − b| / |b| gilt eine
  Lösung — streng 1e-8, normal 1e-6 (Vorgabe), 1e-5, locker 1e-4, sehr
  locker 1e-3. Liegt das Residuum darüber, iteriert der Löser mit der
  vorhandenen Faktorisierung nach (**Nachiterationen**: keine, bis 1, 2, 3
  (Vorgabe), 5 oder 10; jede kostet eine Vorwärts-Rückwärts-Lösung, keine
  neue Faktorisierung); bleibt es darüber, gilt das System als singulär und
  die Rechnung bricht ab — die Meldung nennt Residuum und Schranke.
  Straffedern (starre Kopplungen, Kontakt, je 1e4-fach die größte
  Hauptdiagonale) kosten die Faktorisierung Stellen: am Drehlager brach LF1
  mit 1,3e-6 ab, obwohl derselbe Aufbau konvergiert; eine Nachiteration
  bringt solche Fälle auf 1e-12. Das Protokoll nennt Löser, Threads und
  Genauigkeit („MUMPS, 31 Threads, Genauigkeit 1e-06 mit bis zu 3
  Nachiterationen“). Beide Werte werden gespeichert.
* **Tetraeder ohne volumetrische Versteifung** (*Berechnung → Einstellungen*,
  bei der Plastizität, 20.09.2026). Der lineare Tetraeder `tet4` hat konstante
  Dehnung und kann die Volumenänderung nicht getrennt von der Gestaltänderung
  darstellen — er **versteift**. Mit diesem Haken wird der volumetrische Anteil
  der Steifigkeit über den Elementverband jedes Knotens gemittelt statt je
  Element genommen; der deviatorische bleibt elementweise. Gemessen am
  Kragträger 0,2 × 0,2 × 2,0 m mit 480 Tetraedern, gegen die Balkenlösung:

  | ν | ohne Haken | mit Haken |
  |---|---|---|
  | 0,300 | 51,0 % | 67,2 % |
  | 0,450 | 30,2 % | 62,4 % |
  | 0,499 | **2,1 %** | **51,1 %** |

  Je näher die Querdehnzahl an 0,5, desto größer der Unterschied — und **genau
  dorthin läuft der Werkstoff beim Fließen**, denn von-Mises-Fließen ist
  volumentreu. Wer mit Plastizität rechnet und lineare Tetraeder im Netz hat,
  sollte den Haken setzen; ohne ihn ist die plastische Zone zu steif.

  Zwei Dinge gehören dazu: Die **Schubversteifung bleibt** — deshalb 67 % statt
  der 99 %, die ein quadratischer Tetraeder erreicht; dagegen hilft nur ein
  feineres Netz oder *Netzeinstellungen → Ordnung: quadratisch*. Und der Preis
  steht in der Matrix: die Knoten eines Verbands werden gekoppelt, am
  Kragträger 38,3 statt 14,8 Einträge je Zeile, die Faktorisierung wird
  teurer. Betrifft nur `tet4`; alle anderen Elementtypen rechnen unverändert.
  Die Einstellung hängt am **Modell** und wird mitgespeichert. Herleitung und
  Nachweise im Theoriehandbuch, Abschnitt 6a.
* **Plastizität der Volumen** (*Berechnung → Einstellungen*, 17.09.2026;
  eine Einstellung **am Modell**, sie reist mit der Datei): mit dem Haken
  fließen Volumenelemente, deren Vergleichsspannung (von Mises) die
  Streckgrenze fy ihres Werkstoffs übersteigt — die Spannung bleibt bei
  fy + H·ε_p, die Kraft verteilt sich um, die Verformung wächst. Werkstoffe
  ohne fy (etwa „Starr“) bleiben elastisch, das Protokoll nennt sie.
  **Verfestigung E_t/E** ist die Tangente nach dem Fließen (0 %
  ideal-plastisch, Vorgabe 1 %), **Laststufen** (Vorgabe 3) bringen die
  Last stufenweise auf, **Schritte je Stufe** (Vorgabe 25) und die
  **Toleranz** (Änderung der plastischen Knotenlasten gegen die Last,
  Vorgabe 1e-3) begrenzen die Iteration. Mit Kontakt ist jeder Schritt eine
  Kontakt-Iteration (warm gestartet); Kombinationen werden dann direkt
  gerechnet, nicht überlagert. Die Spannungen im Ergebnis sind die wahren
  (σ = D(ε − ε_p)), die Auflagerkräfte tragen die Last. Das Protokoll nennt
  je Laststufe und Schritt die fließenden Elemente und die Änderung, die
  Zusammenfassung „Plastizität: n Elemente fließen, ε_p,eq max …, Schritte
  in Laststufen“. Der Zugversuch am Hexaeder trifft σ/E + (σ − fy)/H auf
  1e-6, mit Kontakt bleibt das Gleichgewicht (`tests/test_plastizitaet.py`;
  Verfahren in `docs/Theoriehandbuch.md`, Abschnitt 5e).
* **Verfahren der Plastizität** (20.09.2026): Vorgabe ist die **konsistente
  Tangente** — ein Newton-Verfahren, das die Steifigkeit je Schritt neu
  aufstellt und faktorisiert. Es konvergiert quadratisch und **unabhängig
  von der Verfestigung**: der einachsige Zugversuch bei 1 % Verfestigung
  braucht 7 bis 12 Schritte und trifft die geschlossene Lösung auf 0,2 %.
  Der alte Weg (**Anfangsdehnung**, feste Steifigkeit, eine Faktorisierung
  je Rechnung) zieht sich mit 1 − E_t/E zusammen — bei 1 % Verfestigung
  0,99 je Schritt. Er konvergierte im selben Versuch nicht und lag bei
  1,5 fy um 28,5 % in der Spannung und 9,5 % in der Dehnung daneben.
  Bezahlt wird das mit einer Faktorisierung je Schritt (am Drehlager 3,2 s
  gegen 0,31 s für ein Rückwärtseinsetzen). **Wann zurückschalten:** wenn
  nur örtlich fließt und die Verfestigung bei 10 % oder darüber liegt —
  dort kommt die Anfangsdehnung mit acht bis zehn Rückwärtseinsetzungen
  aus und ist billiger. Bei 0 % Verfestigung (ideal-plastisch) schaltet
  das Programm von selbst zurück, weil die Tangente dann singulär wäre.
* **MUMPS** ist unter Windows ein eigener Bau (gfortran, OpenMP, OpenBLAS,
  METIS — `docs/MUMPS_Windows_Bauanleitung.md`), nachgeladen beim Start. Symmetrische
  Steifigkeitsmatrizen gehen als unteres Dreieck hinein (SYM=2): halber
  Speicher, halbe Flop; ob die Matrix symmetrisch ist, prüft das Programm
  an der Matrix und nimmt sonst die volle. Gemessen am Würfel mit 34.914
  Freiheitsgraden (Ryzen 9 5950X, 16 Kerne): SuperLU 8,25 s, MUMPS 1,26 s
  mit einem und 0,86–1,09 s mit acht Threads, MKL PARDISO 0,45 s; mit
  201.720 Freiheitsgraden MUMPS 22,1 s (1 Thread), 8,1 s (8), 9,8 s (16).
  Mehr als acht Threads oder mehr als physische Kerne machen MUMPS
  langsamer (31 Threads am Würfel: 3,3 s), darum nimmt es höchstens acht;
  `MUMPS_NUM_THREADS` übersteuert das ausdrücklich. Die Statuszeile nennt
  die Threadzahl, die die Laufzeit meldet.
* **Threads des Gleichungslösers** (Auswahl unter dem Gleichungslöser, seit
  13.09.2026): **automatisch** = MKL PARDISO alle Kerne bis auf einen, von
  MKL auf die physischen Kerne gekappt (16 von 32 auf diesem Rechner), MUMPS
  höchstens acht (die Zahlen stehen im Eintrag, so wie die Löser sie selbst
  melden); oder eine feste Zahl
  (1, 2, 4, 6, 8, 12, 16, … bis zur Kernzahl), die dann für **beide** direkten
  Löser gilt — so lässt sich am eigenen Modell messen, ob mehr Threads
  etwas bringen. Die Umstellung wirkt ohne Neustart (MKL über
  `MKL_Set_Num_Threads`, MUMPS über `omp_set_num_threads`); die Statuszeile
  nennt nach der Rechnung die wirklich benutzte Zahl, die der Löser selbst
  meldet (`MKL_Get_Max_Threads`, `omp_get_max_threads`) — bis 13.09.2026
  stand für PARDISO die angeforderte 31 dort, tatsächlich rechnete MKL mit
  16. Löser, Threads und das Kästchen „MUMPS beim Programmstart
  nachladen“ werden in `%LOCALAPPDATA%\Statik3D\einstellungen.json`
  gespeichert und überleben den Neustart. Geprüft in `tests/test_loeser.py`
  (2 Threads → beide Löser melden 2, zurück auf automatisch ohne Neustart)
  und `tests/test_gui_smoke.py`.
* **Eigenschwingungen mit Kontakt.** Kontaktpaare schwingen mit: liegt eine
  gerechnete statische Lösung vor, schwingt das System um ihren
  **Kontaktzustand** (geschlossene Paare übertragen, offene nicht); sonst
  gelten alle Paare als geschlossen und haftend (verklebt). Vorher fehlte der
  Kontakt ganz — am Block mit Reibung kamen sechs Starrkörperformen mit 0 Hz
  heraus, und ein Modell, dessen Körper nur über Kontakt gehalten sind,
  scheiterte an einer singulären Matrix, ohne dass rechts etwas zu sehen war.
  Gelöst wird jetzt um einen leicht negativen Shift (auch freie Körper sind
  damit regulär) mit demselben Löser wie die Statik (MKL PARDISO, wenn
  vorhanden). **Starrkörperformen** (f unter 0,01 Hz) zählt die
  Zusammenfassung: „Bauteile nicht gehalten oder Kontakt offen“. Scheitert
  eine Rechnung, steht der Grund außer im Protokoll auch **rechts in der
  Maske Ergebnisse**, die dazu nach vorn kommt. Geprüft in
  `tests/test_elemente.py` (`test_eigenformen_mit_kontakt`: Block mit
  Reibung verklebt und um den statischen Zustand, freier Würfel mit sechs
  Starrkörperformen) und `tests/test_gui_smoke.py`.
* **Prozesse fürs Vernetzen und die Elemente**: Zahl der Arbeitsprozesse für
  Elementschleifen, Aufträge und die Vernetzung - Vorgabe alle Kerne bis auf
  einen, der bleibt der Oberfläche. Das ist **nicht** dieselbe Zahl wie die
  Threads des Gleichungslösers darunter: die Prozesse stellen die Matrizen
  auf, die Threads lösen damit das Gleichungssystem, und sie laufen
  nacheinander. Beide dürfen gleich groß sein; die Maske sagt es in einem
  Satz (14.09.2026: „Prozesse und Threads des Gleichungslösers ist
  anscheinend doppelt").
* **Backend**: *lokal* oder *lokal und Rechnerfarm* — die Farm kommt zu
  diesem Rechner dazu, sie ersetzt ihn nicht. Server, Port, Schlüssel, die
  Farmknöpfe und der Hinweis für die Rechenhilfe erscheinen **erst**, wenn
  die Farm gewählt ist (seit 14.09.2026); vorher stehen sechs Felder im Weg,
  die niemand braucht. Siehe `Rechnerfarm.md`. **Rechnerfarm einschalten** macht den
  eigenen Rechner zum Arbeitsplatz der Farm (Server, eigene Worker,
  Ankündigung im Netz); auf jedem weiteren Rechner genügt *Extras → Als
  Rechenhilfe arbeiten…* (oder `Statik3D.exe --rechenhilfe`): „Arbeitsplatz
  suchen“, Schlüssel, „Verbinden“ — ohne Kommandozeile, seit 13.09.2026
  („die Rechnerfarm muss benutzerfreundlicher funktionieren“). **Farm-Status**
  zeigt die Rechenhilfen mit Version und Programmstand.
* **Ein stehender Prozesspool je Rechnung.** Bis 13.09.2026 startete jede
  Elementschleife — die Assemblierung und der Nachlauf jedes Lastfalls —
  einen neuen Pool und gab jedem Arbeitsprozess das Modell als Startargument
  mit, im Hauptprozess je Arbeiter neu gepickelt. Am Drehlager (1 812 423
  Elemente, 275 MB) kostete der Nachlauf **eines** Lastfalls so 225–244 s,
  seriell auf einem Kern wären es 60 s gewesen — die Parallelisierung machte
  die Rechnung langsamer. Jetzt schreibt die Rechnung das Modell einmal in
  eine Datei, jeder Arbeiter liest sie beim Start, und der Pool steht bis zum
  Ende der Rechnung (`solve_all`, `solve_static`, `solve_cases`,
  Eigenformen); der Verschiebungsvektor eines Aufrufs geht ebenso über eine
  Datei einmal je Arbeiter. Gemessen: erster Aufruf 98 s (31 Arbeiter starten
  und lesen je 275 MB), jeder weitere **6,5 s** statt 240 s; bei 422
  Lastfällen sind das 47 Minuten statt 28 Stunden Nachlauf. Auch ohne
  offenen Block läuft eine einzelne Elementschleife über eine Modelldatei
  statt über Startargumente. Geprüft in `tests/test_solver_ext.py`
  (`test_stehender_pool`).
* **Kontakt-Iteration und Speicher.** Jeder Schritt der Kontakt-Iteration
  faktorisiert das System neu; der Speicher jeder Faktorisierung wird sofort
  danach zurückgegeben. Am Drehlager (1 028 724 Freiheitsgrade, 7 GB je
  Faktorisierung) wuchs der Prozess vorher je Schritt um 7 GB, bis der Löser
  nach 33 Schritten bei 113 GB aufgab (11.09.2026).
* **Das Kontaktsystem wird einmal gebaut, nicht je Rechenschritt**
  (20.09.2026). Welcher Slave-Knoten auf welche Master-Facette fällt, die
  Normalen, die Flächenquadriken, die Suchbäume — das hängt weder an der Last
  noch am Verformungszustand. Gebaut wurde es trotzdem bei jedem Aufruf neu,
  mit Plastizität also **einmal je Schritt**. Am Drehlager (LF3 warm, 12
  Kontaktfugen, 18 Plastizitätsschritte) waren das 23 Aufbauten: im Profiler
  276 Aufrufe von `contact._build_pair` und 172 s von 542 s — ein Drittel des
  Lastfalls für 23-mal dasselbe Ergebnis. Jetzt hängt das Kontaktsystem am
  `StaticSystem`, dort, wo auch Steifigkeitsmatrix und Faktorisierung liegen;
  der Schlüssel ist das Übermass, denn das geht in den Anfangsspalt jeder
  Bedingung ein. Gemessen am Drehlager, gleiche Sonde vorher und nachher:

  | | vorher | nachher |
  |---|---|---|
  | LF1 (kalt) | 735,2 s | **647,3 s** |
  | LF3 (warm) | 409,2 s | **270,5 s** |
  | max \|u\| | 0,2680 mm | 0,2680 mm |

  Das Ergebnis ändert sich nicht — es wird nur nicht mehr 23-mal dasselbe
  gebaut. Die gemessenen Zeiten enthalten je Lastfall rund 35 s Anlauf des
  Prozesspools, weil die Sonde jeden Lastfall einzeln startete; eine echte
  Rechnung umschließt alle Lastfälle mit **einem** Block und zahlt ihn
  einmal. Ohne diesen Anteil: 374 → 235 s je warmem Lastfall, hochgerechnet
  auf 422 Lastfälle (1 kalt, 421 warm) **43,9 → 27,7 Stunden**. Geprüft in
  `tests/test_plastizitaet.py` (zwei Aufbauten statt 54 bei 28 Läufen, und
  dieselbe Lösung wie beim Bauen in jedem Schritt).
* **Rechenketten: mehrere Lastfälle gleichzeitig** (*Berechnung →
  Einstellungen*, 20.09.2026). „Lastfälle gleichzeitig (Ketten)“ gibt jeder
  Kette einen eigenen Prozess; **innerhalb** einer Kette laufen die Lastfälle
  nacheinander und warm gestartet. Das ist der Kern der Sache: der Warmstart
  ist der größte Einzelgewinn je Lastfall (Drehlager: kalt 112
  Kontaktrunden, warm 41 bis 48). Wer alle Lastfälle einzeln verteilt, macht
  jeden kalt und verliert mehr, als die Parallelität bringt — darum bekommt
  jede Kette eine ganze Folge, und die Aufteilung hält jede Situation
  zusammen (jede Situation hat ihr eigenes System).

  **Die Grenze ist der Speicher, nicht die Kernzahl.** Gemessen am Drehlager
  (20.09.2026): eine Kette mit vollem Pool belegt 36 GB — davon 32,7 GB die
  31 Arbeitsprozesse, die jeder das ganze Modell halten (1,05 GB je Prozess),
  und nur 3,2 GB Steifigkeitsmatrix und Faktorisierung. Darum gibt es
  „Arbeitsprozesse je Kette“: die Elementschleifen sind nur noch ein kleiner
  Teil der Zeit (Element-Nachlauf 2 bis 3 s, Plastizität 8 s von 235 s je
  warmem Lastfall), sechs Prozesse je Kette genügen also, und dann passen bei
  108 GB freiem Speicher etwa elf Ketten statt drei. „automatisch“ nimmt so
  viele, wie drei Viertel des freien Speichers tragen.

  Vorgabe ist **nacheinander**. Bei einem kleinen Modell kostet der
  Prozessanlauf mehr, als die Parallelität bringt (Hallenrahmen: 0,19 s
  nacheinander, 1,02 s in drei Ketten). Nicht geteilt wird, wo es nicht geht:
  wenn ein System für alle genannten Lastfälle vorgegeben ist, und bei den
  eingefrorenen Zuständen einer Ermüdungslast — die brauchen ihren
  Referenzzustand aus demselben Lauf. Geprüft in `tests/test_solver_ext.py`
  (dieselben Lastfälle, dieselben Verschiebungen und Auflagerkräfte wie
  nacheinander).
* **Der Prozesspool läuft einmal an, nicht je Lastfall** (20.09.2026). Beim
  ersten Auftrag lesen alle 31 Arbeiter das Modell aus einer Datei; am
  Drehlager dauert das rund 35 s. Gemessen am selben Modell, 645 170
  Elemente: der erste Element-Nachlauf im stehenden Pool kostet 40,7 s, jeder
  weitere 2,1 bis 3,6 s — und ganz **ohne** stehenden Pool, wenn ein Aufruf
  sich seinen eigenen baut, 96 s. Darum umschließt `parallel.arbeiter` eine
  ganze Rechnung und nicht einen Aufruf. Wer die Zeiten eines einzelnen
  Lastfalls misst, misst diesen Anlauf mit.
* **Warmstart und behaltene Faktorisierung.** Lastfälle derselben Situation
  beginnen die Kontakt-Iteration im Kontaktzustand des vorigen Lastfalls;
  solange sich die Kontaktsteifigkeit nicht ändert, bleibt die Faktorisierung
  und es wird nur rückwärts eingesetzt (am Block mit Reibung 5 statt 21
  Schritte für den Folgezustand). Passt der Zustand nicht — gleitende Knoten
  bewegen sich gegen ihre Richtung —, meldet das Protokoll „Warmstart
  verworfen“ und rechnet von der Geometrie; am Drehlager war das zwischen
  LF401 und LF404 der Fall. Für die Zustände einer Ermüdungslast greift
  stattdessen das Einfrieren des Kontaktzustands (Kapitel 8).
* **Was eine Runde bewegt und was sie kostet** (19.09.2026). Die
  Protokollzeile lautete `Kontakt-Iteration 37: 13300 aktiv` — und diese Zahl
  beantwortet die nächstliegende Frage nicht: „ist das wirklich relevant,
  obwohl sich die Anzahl so gering ändert?“ Sie zählt **offen gegen
  geschlossen**. Der Wechsel *haften → gleiten* lässt den Knoten geschlossen,
  rührt die Zahl also gar nicht — und genau das ist die Arbeit von Phase 2.
  Abgebrochen wird ohnehin nicht nach der Zahl, sondern nach der Menge: es
  wird weitergerechnet, solange **irgendein** Zustand wechselt,
  Gleitrichtungen eingeschlossen. Die Zeile nennt darum zwei weitere Angaben:

  ```
  Kontakt-Iteration 37: 13300 aktiv, Δu 4.9e-04, Matrix bleibt
  ```

  * **Δu** ist die größte Verschiebungsänderung gegenüber der vorigen Runde,
    bezogen auf die größte Verschiebung. Daran sieht man, ob noch etwas
    geschieht.
  * **Matrix neu / Matrix bleibt** sagt, ob neu faktorisiert wurde. Neu wird
    nur bei geänderter Signatur — Aktivmenge, Haften/Gleiten, Fließen;
    Gleitrichtungen und Reibkräfte stehen allein im Lastvektor. Daran liegt
    es, dass die späten Runden rasen: eine Faktorisierung kostet am Drehlager
    4,23 s bei 476 214 Zeilen, das Rückwärtseinsetzen einen Bruchteil davon.

  Am Block mit Reibung: 21 Runden, davon 7 mit neuer Faktorisierung — und
  „20 aktiv“ steht über allen 21, teuren wie billigen. Die Zahl allein sagt
  also wirklich nichts.
* **Die Zusammenfassung zählt alle Läufe eines Lastfalls.** Mit Plastizität
  löst derselbe Lastfall viele Male — am Drehlager 18 Schritte in drei
  Laststufen. Gezählt wurde davon nur der **letzte**: die Zusammenfassung
  meldete „Kontakt-Iterationen: 2“ für eine Rechnung von 2 289 s, und die
  Kontaktmeldungen der früheren Schritte fielen ganz weg. Jetzt steht dort

  ```
  Kontakt-Iterationen     : 546 in 28 Läufen, davon 309 mit neuer Faktorisierung
  ```

  Die Zahl der Faktorisierungen trägt die Rechenzeit, nicht die Zahl der
  Runden. „Nicht konvergiert“ klebt: ein einziger gekappter Lauf genügt, und
  die Meldungen aller Läufe bleiben im Protokoll. Geprüft in
  `tests/test_plastizitaet.py`.
* **Prozesspool und Gleichungslöser sind zweierlei.** Der Pool oben verteilt
  Elementschleifen und die Vernetzung auf Prozesse. Das Lösen des
  Gleichungssystems macht ein einzelner Prozess mit eigenen Threads. Das
  Protokoll nennt beim Start einer Rechnung darum beides getrennt:

  ```
  --- Berechnung gestartet ---
      Prozesspool (Elementschleifen, Vernetzen): lokal, 31 von 32 Kernen
      Gleichungslöser: MKL PARDISO, 16 Threads
  ```

  Genannt wird der **eingestellte** Löser mit seiner Kernzahl, nicht der
  erstbeste vorhandene: wer MUMPS gewählt hat, liest dort seit dem
  14.09.2026 „MUMPS, 8 Threads“ (vorher stand da „MKL PARDISO, 16 Threads“,
  während MUMPS rechnete — nur die Ergebniszeile sagte es richtig). Bei
  *automatisch* steht dahinter „(automatisch)“, und ein eingestellter Löser,
  der nicht installiert ist, wird vor der Rechnung als solcher gemeldet.

  Steht dort „SuperLU, einkernig“, fehlt der Mehrkern-Löser: dann rechnet
  die Faktorisierung auf genau einem Kern, gleichgültig wie viele die
  Maschine hat. Das Windows-Programm bringt Intel MKL mit, so dass PARDISO
  greift - an einem Modell mit 34.914 Freiheitsgraden 1,4 statt 12,3
  Sekunden je Faktorisierung. Wer aus dem Quelltext arbeitet, installiert
  ihn mit `pip install pypardiso mkl`.
* Die Berechnung läuft im Hintergrund. Die Statuszeile zeigt einen
  **Fortschrittsbalken mit Prozentzahl** und daneben, woran das Programm
  gerade ist und wie lange es schon läuft. Der Balken **wächst**: jede
  Kontakt-Iteration rückt ihn im Fenster ihres Lastfalls weiter (1 − 0,85ⁿ,
  denn wie viele Schritte es werden, weiß vorher niemand — am Drehlager 32
  bis 43), und ein **drehendes Zeichen** mit der Laufzeit in der
  Balkenbeschriftung zeigt jede halbe Sekunde, dass die Rechnung lebt — auch
  während einer Faktorisierung von 13 s, in der sich sonst nichts rührt
  (12.09.2026). Ein wandernder Streifen erscheint nur noch, solange der
  Rechenkern noch keinen Anteil gemeldet hat („Berechnung: Lastfall W (5/12)
  (48 %, 73 s)“). Die Schritte sind: Gleichungssystem aufstellen,
  faktorisieren, Lastfälle, Kombinationen, Umhüllende, Nachweise. Jede
  Zeile steht auch im Protokoll. **Abbrechen** (Knopf neben dem Balken oder
  Esc) hält beim nächsten Rechenschritt an - eine laufende Faktorisierung
  läuft zu Ende -, meldet „Berechnung abgebrochen (nach x s)“ und lässt das
  Netz, wie es war. Die bis dahin fertigen Lastfälle und Kombinationen
  bleiben als Ergebnis stehen, ohne Umhüllende und ohne Nachweise
  (Kapitel 2, „Statuszeile“).
* **Das Protokoll überlebt einen Absturz.** Jede Zeile geht sofort in eine
  Mitschrift unter `%LOCALAPPDATA%\Statik3D\Protokolle` (unter Linux
  `~/.local/share/Statik3D/Protokolle`), eine Datei je Programmstart. Stürzt
  das Programm mitten in einer langen Rechnung ab, ist der Verlauf dort
  trotzdem vollständig nachzulesen - im Fenster wäre er weg. Das Fenster
  selbst hält die letzten 20.000 Zeilen; alles Ältere steht nur noch in der
  Datei.
* **Vor dem Rechnen** prüft das Programm die Rechenbarkeit. Flächen und
  Volumen **ohne Netz** tragen nichts (nach einem Import aus RFEM oder
  HiCAD besteht das Modell oft nur aus Geometrie und ein paar Stäben): es
  fragt, ob jetzt mit den Netzeinstellungen vernetzt werden soll, und
  rechnet danach. **Teiltragwerke ohne Lager** (das Netz zerfällt in Teile,
  von denen eines weder ein Lager noch eine Kopplung an ein gelagertes Teil
  hat) machen das Gleichungssystem singulär; die Modellprüfung nennt sie mit
  Knotennummern, statt dass der Solver mit „Factor is exactly singular“
  abbricht. Gibt es dabei **Volumen, die der Vernetzer nicht vernetzen
  konnte**, nennt die Meldung diese als Ursache statt Lager zu empfehlen: das
  Modell zerfällt genau dort, wo ein tragendes Bauteil fehlt, und erst wenn
  dessen Netz steht, hängt der Rest wieder zusammen. Die losen Teile sind die
  Folge, nicht die Ursache. Abgewiesen wird die Rechnung deswegen aber nicht mehr - das
  Programm fragt, ob es trotzdem rechnen soll, hält jede freie Bewegung fest
  und weist danach aus, welche Last in welcher Bewegung ins Nichts geht
  (siehe *Freie Bewegungen* weiter unten). Teile, die nur ein einseitiges Lager oder ein Kontaktpaar hält,
  sind ein Hinweis, kein Fehler - ob sie tragen, entscheidet die
  Kontakt-Iteration. Dabei zählen **beide Seiten** einer Kontaktfuge: ein
  Bauteil, das ausschließlich Gegenseite ist - ein Passstift in seiner
  Bohrung, ein Unterlegblech unter einer Grundplatte -, wird vom Kontakt
  genauso gehalten wie die gelöste Seite. **Entartete Elemente** ohne Ausdehnung (zwei Ecken auf
  demselben Knoten oder alle Punkte in einer Ebene) haben weder Steifigkeit
  noch Masse. Sie **werden bei der Rechnung übergangen** - das ist exakt und
  nicht genähert, denn sie tragen ohnehin nichts - und die Modellprüfung
  nennt sie als **Warnung** mit Elementnummer, Art und Grund. Früher brach
  die ganze Rechnung an ihnen mit „entartetes Tet4“ ab, ohne zu sagen, wo.
  Der Vernetzer legt sie gar nicht erst an: ein Volumenkörper, dessen
  Eckknoten in einer Ebene liegen, bekommt kein Element und eine Warnung mit
  seinem Namen (in Dateien aus RFEM stehen solche Null-Volumen als
  Hilfsobjekte); und beim Zusammenlegen der Knoten auf gemeinsamen Flächen
  fallen flach gewordene Tetraeder heraus. Scheitert doch ein Element in der
  Elementschleife, nennt die Meldung Nummer, Art, Volumenkörper und Knoten.
* **Volumen ohne Rauminhalt** gelten nicht als „unvernetzt“. Sie können gar
  kein Netz bekommen, und so fragte das Programm sonst vor jeder Rechnung
  nach einem Netz, das es nie geben kann. Statt der Warnung „ohne Netz“
  steht ein Hinweis mit ihren Namen im Protokoll, und die Rechnung läuft.
* **Zylinder, Stifte und Bolzen** werden vom freien Vernetzer vernetzt, auch
  wenn sie wie ein Tetraeder aussehen: vier Randflächen und vier Eckknoten
  hat ein Zylinder aus zwei Mantelflächen und zwei Kreisen genauso. Das
  abgebildete Netz greift nur noch, wenn die Randflächen wirklich Dreiecke
  mit geraden Kanten sind - sonst übernimmt der freie Vernetzer.
* Bleiben nach dem Vernetzen **doch Objekte ohne Netz**, bricht das Programm
  nicht mehr ab: es nennt sie beim Namen, sagt, dass Lasten darauf verloren
  gehen, und rechnet ohne sie. Ein zweiter Abbruch wäre eine Sackgasse - was
  der Vernetzer eben nicht vernetzen konnte, kann er auch beim nächsten
  Versuch nicht. Der Grund je Objekt steht im Protokoll und in seiner
  Bemerkung im Modellbaum. War die Randhülle nicht dicht, nennt die Meldung
  die **offenen Kanten selbst** — mit Knotennummern, Koordinaten und den
  Randflächen, aus denen die anliegenden Dreiecke stammen, höchstens zehn und
  den Rest im Protokoll. Eine bloße Zahl („9 Kanten offen“) sagt nicht, wo;
  zwei Zeilen mit derselben Koordinate und verschiedenen Flächen heißen: dort
  stehen zwei Kopien desselben Punktes.
* Der Vernetzer versucht ein Volumen in mehreren Anläufen, von grob nach fein.
  **Reißt die Hülle erst in einem späteren Anlauf**, behält der Körper das
  Netz des früheren — es ist gröber, aber es ist eines. Das Protokoll sagt
  dann, welcher Anlauf stehen blieb und warum nicht feiner. Ohne Netz bleibt
  ein Körper nur, wenn schon der erste Anlauf scheitert.

### Abnahme des Netzes vor dem Rechnen

Vor jedem Lauf nimmt das Programm das Netz ab. Ein Bauteil ist vollständig
angebunden, oder es ist ein **Fehler mit Namen** — nichts halb Gekoppeltes,
nichts stillschweigend Übergangenes:

| Prüfung | Grenze |
|---|---|
| Elemente, die eine ausgeführte Kontaktfuge überspannen | 0 |
| **Gemeinsame Fläche zweier Körper: doppelte und hängende Knoten** | **0** |
| Abdeckung der Kontaktseite | ≥ 95 % |
| Gegenkörper der Kontaktbedingung ohne eine einzige Facette | 0 |
| Haltegüte je Teiltragwerk | ≥ 10⁻⁴ |
| Knoten im Rechennetz ohne Element | 0 |
| Formgüte des schlechtesten Elements je Körper | ≥ 0,05 |
| Randtreue je Körper | ≥ 99 % |

**„Bestanden" heißt nicht „nicht geprüft".** Zwei der Teilprüfungen fingen
eine Ausnahme stumm ab und gaben eine leere Liste zurück — und leer heißt in
der Abnahme ausdrücklich „das Netz ist abgenommen". Ein Modell, dessen
Lagerung in einer Richtung fast nicht hält, wurde damit mit „Abnahme des
Netzes: bestanden" quittiert. Fällt eine Prüfung heute aus, steht sie als
eigene Zeile im Protokoll (`Haltegüte nicht geprüft`, `Elementgüte nicht
geprüft`) und die Überschrift lautet **„bestanden, soweit geprüft (N
Prüfungen fielen aus)"**. Als Warnung und nicht als Fehler: eine ausgefallene
Messung ist keine Verletzung des Modells, sie hält den Lauf also nicht an.

Zwei Einzelheiten dazu, beide gemessen:

* Die Haltegüte wird je Teiltragwerk fortlaufend ermittelt. Brach die Messung
  beim 40. von 60 ab, gingen bis dahin **auch die 39 schon gemessenen Werte**
  verloren. Sie bleiben jetzt stehen — ein gefundener Mangel überlebt den
  Ausfall.
* Ließ sich die Formgüte eines Elements nicht ermitteln, ging sie als 1,000
  in die Splitterprüfung ein — ein nicht messbares Element galt damit als das
  **formbeste überhaupt** (gemessen 1,000 statt 0,039, Faktor 26 zu gut).
  Solche Elemente zählen jetzt nicht mit und werden mit ihrer Anzahl genannt.

Die wichtigste Zeile ist die erste: beim Ausführen einer Fuge werden die
gemeinsamen Randknoten verdoppelt; bliebe danach ein Element mit einem Fuß auf
der alten und einem auf der neuen Seite, überbrückte es genau die Trennung und
die Fuge wirkte dort **nicht**. Von außen sieht man das als „halb vernetzt".

Die zweite ist der stillste aller Netzfehler. Zwei Körper, die *dieselbe*
Randfläche haben, müssen dort dieselben Knoten benutzen — sonst ist die Fläche
zweimal vernetzt, die Kräfte gehen nicht hinüber, und das Netz sieht dabei
tadellos aus. Genannt wird beides getrennt, weil es verschiedene Ursachen hat:
**doppelte** Knoten (gleicher Ort, andere Nummer) heißen, dass die Teilung
passt und die Knoten nur zweimal angelegt wurden; **hängende** heißen, dass
die beiden Körper die gemeinsame Linie oder Fläche verschieden fein geteilt
haben.

Jede Verletzung steht **einzeln** im Protokoll, mit Prüfung, Bauteil, Element,
Knoten, gemessenem Wert und Grenze — keine Sammelmeldung, keine
Auslassungspunkte. Die Rückfrage fasst nur zusammen, wie viele je Prüfung
anstehen; die Entscheidung bleibt beim Anwender. Wer mit 17 % Abdeckung
rechnen will, kann es — aber nachdem er gelesen hat, dass es 17 % sind.

### Abbruch der Kontakt-Iteration: die letzte Verformung bleibt sichtbar

**Vorher greift ein Halt** (17.09.2026): verliert ein Teil in einem Schritt
der Kontakt-Iteration alle seine Bedingungen (ein Passstift, dessen Bohrung
ihn in diesem Schritt nirgends drückt), wäre das Gleichungssystem singulär.
Statt abzubrechen hält das Programm je Teil mindestens drei Bedingungen mit
dem kleinsten Spalt geschlossen und löst den Schritt noch einmal; das
Protokoll nennt jedes gehaltene Teil („Halt für Teile ohne geschlossene
Bedingung: V100: 0 von 62 zu, 3 mit dem kleinsten Spalt (bis 0,012 mm)
gehalten“). Erst wenn auch das nicht hält, bricht die Rechnung ab. Tragen
die gehaltenen Punkte am Ende Zug, hebt das Teil wirklich ab: dann bricht
die Rechnung mit der gehaltenen Lage als Teilergebnis ab, und der Zeiger
sagt „hebt ab und hängt an n gehaltenen Punkten unter F kN Zug“.

Findet die Kontakt-Iteration auch mit Hilfsfesselung kein Gleichgewicht
(„Gleichungssystem singulär“), bricht die Rechnung ab — aber nicht stumm
(16.09.2026: „die Verformung der letzten Iteration anzeigen, damit der
Anwender prüfen kann, woran der Abbruch lag, und Zeiger auf die Teile, die
ihn verursacht haben“). Das Programm hält die **Verschiebung der letzten
gelösten Iteration** fest und stellt sie als Ergebnis *„LF … – Abbruch
(Iteration n)“* in die Ansicht: Verformung mit Überhöhung, Färbung,
Kontaktzustand der Fugen (welche offen waren) und die zur Verschiebung
nachgerechneten Spannungen. Auflagerkräfte gibt es nicht, denn es gab kein
Gleichgewicht; die Zusammenfassung beginnt mit *ABBRUCH*.

Dazu die **Zeiger**: jedes Teil, dessen Kontaktbedingungen in diesem Schritt
alle offen waren, steht als freie Bewegung „hebt ab“ im Modellbaum unter
*Ergebnisse → Freie Bewegungen* — mit dem Pfeil in der Richtung, in die es
sich in der letzten Iteration bewegt hat, der Kraft, die dabei ins Nichts
geht, und den Fugen, an denen es hängt. Ebenso gezeigt wird ein Teil, bei
dem die Mehrheit der Bedingungen offen war und das sich um mindestens das
Fünffache dessen bewegt hat, was die übrigen Teile tun (gemessen am Mittel
seiner Knotenverschiebungen gegen das 90. Perzentil der anderen — eine
Baugruppe, die sich gemeinsam um 0,9 mm bewegt, fällt gegen ihresgleichen
nicht auf, 17.09.2026): der Block, der auf einer Kante kippt, statt glatt
abzuheben, hält an fünf von 25 Punkten noch Kontakt und wäre sonst nicht
genannt worden. Der Text sagt dann „verliert den Halt: hielten nur noch 5
von 25 Kontaktbedingungen“ und nennt die Bewegung in mm; „hebt ab“ steht
nur, wenn keine Bedingung mehr geschlossen war.
Der erste Zeiger ist nach dem Abbruch schon eingestellt; die Auswahl steht
auf dem Lastfall selbst, eine Umhüllende über ein Teilergebnis ohne
Gleichgewicht gibt es nicht. Am Drehlager (16.09.2026) waren das die Deckel
V33 und V35: sie hängen nur an Druck-Fugen ohne Reibung und Verbund, die
Schrauben halten dort keinen Zug — sobald die Last sie nach außen drückt,
öffnen alle Bedingungen, und die Deckel sind frei. Abhilfe: *Verbund* oder
eine *Vorspannung* an den Schraubenfugen, oder die Deckel-Fugen als Verbund.

### Freie Bewegungen (Singularitäten)

*Register Start → Modell prüfen → „Freie Bewegungen suchen“*, und nach jeder
Rechnung im Modellbaum unter *Ergebnisse → Freie Bewegungen*.

„Factor is exactly singular“ nennt weder das Bauteil noch die Richtung. Bei
über hundert Volumen ist das nicht prüfbar. Der Befehl sagt statt dessen für
jedes Bauteil, das sich bewegen kann:

* **welches** - der Name des Bauteils, und ein Klick stellt seine Knoten und
  ein Sinnbild der Bewegung in die Ansicht: einen Pfeil bei einer
  Verschiebung, einen Drehpfeil bei einer Drehung;
* **wie** - „Verschiebung längs (0.00, 0.00, 1.00)“, „Drehung um (1.00, 0.00,
  0.00)“, bei einer Schraubbewegung beides;
* **warum** - „Die Fugen *Achse* übertragen nur Druck senkrecht zur Fläche;
  in der Fugenebene ist nichts gehalten (keine Reibung, keine Federn)“ oder
  „Das Bauteil hat weder Lager noch eine Kopplung an ein gelagertes Teil“;
* **was es kostet** - die Last, die in dieser Bewegung ins Nichts geht.

Der letzte Punkt ist der, auf den es ankommt. Unterschieden wird:

* **„im Gleichgewicht“** - die Last auf dem Bauteil hebt sich in dieser
  Bewegung auf. Spannungen und Verformungen gelten; unbestimmt ist nur die
  Lage des Bauteils im Raum. Ein Bauteil, an dem gar nichts angreift, fällt
  immer hierunter.
* **eine Zahl (z. B. „43,2 kN“)** - genau diese Kraft nimmt kein Lager und
  keine Fuge auf. Im wirklichen Bauwerk würde sich das Bauteil bewegen; für
  dieses Bauteil ist das Ergebnis nicht verwertbar. Nach der Rechnung sagt
  das Programm es zusätzlich als Warnung, mit den betroffenen Bauteilen.

Findet der Befehl **keine** freie Bewegung, ist die Frage nicht mehr *ob*,
sondern *wie fest* gehalten wird. Dazu nennt das Protokoll die **Haltegüte**:

```
Haltegüte: am weichsten V4: in Richtung y nur 4.1e-03 der steifsten Halterung
           (Grenze 1e-04; 17 Teiltragwerke geprüft)
```

Die Zahl ist das Verhältnis der schwächsten zur stärksten Halterichtung eines
Bauteils. 1 hieße allseitig gleich fest; praktisch liegt ein sauber gehaltenes
Bauteil zwischen 0,1 und 0,3, ein nur einseitig gehaltenes deutlich darunter.
Unter 10⁻⁴ steht dort eine **WARNUNG** mit Bauteil, Richtung und Wert: das ist
der Kandidat für die Meldung „Bewegung fast ohne Steifigkeit“ aus der
Rechnung - nur eben schon vorher, ohne Löserlauf. So lässt sich auch
beantworten, warum von mehreren gleich aussehenden Bauteilen nur einige
gemeldet werden.

Meldet die Rechnung „Bewegung fast ohne Steifigkeit“, steht dort jetzt das
**Element**, nicht nur das Bauteil: „V104, Element 312487 (tet4): Bewegung
fast ohne Steifigkeit … Ausschlag 1,0 bei 4·10⁻⁷ der mittleren Steifigkeit
dieses Elements“. Beim Vernetzen nennt das Protokoll ebenso die
schlechtesten Splitterelemente mit Nummer und Güte statt nur ihrer Zahl.

Zwei Arten von Bewegung werden getrennt, weil sie verschiedene Abhilfen
haben:

* **gleitet** - in der Fugenebene hält nichts. Abhilfe: Reibbeiwert an der
  Kontaktbedingung, Schub starr setzen oder eine Führung modellieren.
* **hebt ab** - die Fuge geht auf. Abhilfe: ein Lager, ein Verbund
  (Zug übertragen) oder eine Schraube.

Ein Bauteil, das auf seiner Unterlage liegt, lässt sich immer anheben - das
allein ist noch kein Befund. Gemeldet wird „hebt ab“ mit einer Zahl nur dann,
wenn die Last diese Bewegung auch antreibt; drückt sie in die Fuge, steht
dort „Die Last drückt in die Fuge - das Bauteil bleibt liegen“.

Findet die Suche gar nichts und ist das System dennoch singulär, greift die
**Matrixdiagnose**: sie nennt das Bauteil, dessen Bewegung fast keine Energie
kostet. Das ist der Fall, den die Topologie nicht sehen kann - zwei Körper,
die nur einen Knoten teilen, hängen zusammen und sind trotzdem beweglich.

**Statt abzubrechen wird gerechnet.** Jede freie Bewegung wird mit einer
Hilfsfesselung festgehalten. Die verfälscht die Spannungen nicht (sie wirkt
nur auf den Starrkörperanteil, und der wird nach der Rechnung wieder
herausgenommen); sie macht die Rechnung nur möglich. Deshalb darf man das
Ergebnis für alle **gehaltenen** Bauteile ohne Abstriche verwenden - und
sieht an der Liste, für welche nicht.

Bei vielen losen Teilen werden höchstens 40 Bewegungen angezeigt, die
schwersten zuerst: erst die, in denen wirklich Last ins Nichts geht.

## 10 Ergebnisse und Bericht

* **Färbung**: |u|, ux/uy/uz, Vergleichsspannung (Schalen/Volumen, Randspannung
  bei Stäben), Ausnutzung EC3 / Ermüdung / elastisch — und die **Spannungen je
  Art** analog ANSYS Mechanical, auch im Modellbaum unter „Ergebnisse →
  Spannungen Volumen / Spannungen Flächen / Spannungen Stäbe /
  Kontaktspannungen“ (ein Klick stellt die Färbung ein; seit 12.09.2026):
  - **Volumen**: Grundspannungen σ_x, σ_y, σ_z, τ_xy, τ_yz, τ_zx (global),
    Hauptspannungen σ_1 ≥ σ_2 ≥ σ_3, Vergleichsspannung σ_v (von Mises),
    σ_int = σ_1 − σ_3 (Tresca) und τ_max = σ_int/2 — je Element in der Mitte
    gerechnet und auf die Knoten gemittelt.
  - **Flächen**: σ_x, σ_y, τ_xy, σ_1, σ_2, σ_v je Schalenseite; die Maske
    wählt die **Schalenseite** — oben, unten oder je Element die Seite mit dem
    größeren Betrag (wie Top/Bottom in ANSYS). Scheiben (ebene Elemente)
    liefern ihren ebenen Zustand.
  - **Stäbe**: σ_x Rand = |σ_N| + σ_My + σ_Mz, σ_N = N/A,
    σ_My = |M_y| z_max/I_y, σ_Mz = |M_z| y_max/I_z an den Stabenden, am Knoten
    gemittelt.
  - **Kontakt**: Zustand (Klassen offen, haftet, gleitet, fließt),
    Kontaktdruck p = F_n/A, Reibspannung τ = |F_t|/A, Spalt [mm]
    und Kontaktkraft F_n [kN] an den Kontaktknoten; A ist die Einflussfläche
    des Knotens auf der Kontaktfläche, so dass Σ p·A = Σ F_n (am Block mit
    Reibung 90,00 kN = Auflast). Alle anderen Knoten bleiben grau.

  Spannungen stehen in N/mm². Zu einer **Umhüllenden** gibt es diese Größen
  nicht — sie führt Extremwerte, keine Tensoren; die Statuszeile sagt es, und
  gefärbt wird nichts. Die Größen und ihre Prüfung an geschlossenen Werten:
  `tests/test_spannungen.py`.
**Kontaktergebnisse lesen** (12.09.2026, „ich sehe nicht, dass die Kontakte da
wirken, wo sie sollen"): Die Färbung **Kontakt Zustand** zeigt je Kontaktknoten
eine von vier Klassen in festen Farben — grau offen, grün haftet, orange
gleitet, rot fließt — mit Beschriftung je Klasse statt einer Zahlenskala; die
Statuszeile zählt die Knoten je Klasse. **Kontaktdruck**, **Reibspannung**,
**Spalt** und **Kontaktkraft** färben nur die Kontaktknoten, alle anderen
Knoten bleiben **neutral grau** (bis 12.09.2026 stahlblau, das wie ein kleiner
Wert aussah). Die **Kugeln an den Kontaktknoten** (grün haftet, orange gleitet,
grau offen, blau Kontakt ohne Reibung) erscheinen nur noch mit dem Schalter
*Ergebnisse → Kontaktmarken* — vorher lagen sie über jedem Ergebnis, am
Drehlager 21 586 Kugeln, die man für Kontaktergebnisse hielt, die „nicht
weggehen". Die **Skala** schreibt ihre Zahlen aus („2390" statt „2.39e+03"),
mit Nachkommastellen nach der Spanne (unter 100: eine, unter 10: zwei).

**Zahlen als Dezimalzahl.** Ergebniswerte stehen überall als normale
Dezimalzahl mit Punkt — Skala, Modellbaum (Schnittgrößen „−0.00 … +943 kN"),
Statuszeile, Marken, Kennwerte, Tabellen —, nie mehr als „2.33e-13": die
Nachkommastellen richten sich nach dem Betrag (ab 100 keine, ab 10 eine,
ab 1 zwei, sonst drei), Rundungsschrott wird 0 (`spannungen.dezimal`).

**Zeichenzeit bei großen Netzen.** Am Drehlager (1,8 Mio. Tetraeder) kostete
jedes Neuzeichnen 3,9 s, davon im Profil 6,2 von 7,3 s allein die Suche
nach Knoten ohne Element — sie lief bei jedem Bild über alle Elemente. Seit
12.09.2026 wird sie einmal je Netz gemerkt: **0,8 s je Neuzeichnen**. Große
Tabellen (ab 50 000 Zeilen) füllen sich erst, wenn ihr Register nach vorn
kommt; solange steht „wird beim Anzeigen gefüllt" neben der Zeilenzahl (die
Elementtabelle des Drehlagers kostete 61 s bei jedem Modellstand, ihre
Kennwerte 44 s — jetzt spaltenweise mit numpy; ein Modellstand dauert 22 s
statt 51 s). Ist das **FE-Netz** ausgeschaltet, zeigt das unverformte
System nur noch den **Umriss** der Körper (Kanten ab 35°) statt des
Drahtnetzes, und gewählte, aus dem Modellbaum aufleuchtende oder mit der Maus
überfahrene Flächen und Volumen leuchten **ohne Elementkanten** (seit
15.09.2026; vorher zeigte die Hervorhebung das Netz auch bei ausgeschaltetem
Netz).

**Skala und Kennwerte nur für das Sichtbare.** Sind Teile ausgeblendet
(Sicht → *Selektion anzeigen*, *Auswahl ausblenden*, Schalter der
Glasleiste), gelten die Grenzen der automatischen Werteskala und die
Kennwerte im Bild nur für die sichtbaren Knoten und Elemente; die Kopfzeile
sagt „Skala: nur sichtbare Teile", die Kennwerte tragen die Überschrift „nur
sichtbare Teile". So bewertet man ein einzeln gezeigtes Bauteil an seiner
eigenen Skala: Bauteil wählen, *Selektion anzeigen*, ablesen. Geprüft in
`tests/test_spannungen.py` und der Oberflächenprüfung.

* **Werte im Bild** (Ribbon *Ergebnisse → Werte im Bild*, seit 12.09.2026):
  Schalter **Werte Stäbe**, **Werte Flächen**, **Werte Volumen** schreiben
  Zahlenwerte an die Elemente. Stäbe: die gewählte Schnittgröße (Verlauf N, Vy, Vz, Mt, My, Mz)
  an den Nachweisstellen — Filter in der Maske Ergebnisse: *nur Extremwerte
  je Stab* (Vorgabe: kleinster und größter Wert je Element), *alle Stellen*,
  *nur die Stabenden*, *nur Auswahl* (gewählte Elemente, Stäbe, Flächen,
  Volumen); ohne Verlauf der Färbungswert in der Elementmitte. Flächen: der
  Färbungswert je Element. Volumen: je Volumenkörper der betragsgrößte
  Färbungswert an seinem Ort — ein Wert je Körper, nicht je Element.
  Dazu eine **Schwelle** (nur |Wert| ≥ Schwelle) und *jeder n-te Wert*; mehr
  als 200 Marken zeigt die Ansicht nicht (die betragsgrößten bleiben, die
  Statuszeile sagt es). Die Kopfzeile nennt, was die Marken zeigen; sie
  stehen damit auch im Berichtsbild. Zahlen als normale Dezimalzahl mit
  Punkt wie in Tabellen und Kennwerten, in der Einheit der Größe (kN, kNm,
  N/mm², mm).
* **Sonde** (Ribbon *Ergebnisse → Sonde*, Schalter): solange sie an ist,
  setzt ein Klick auf das Modell eine Marke am nächsten Knoten mit dem Wert
  der aktuellen Färbung — „S1 K312: 187,4". Beliebig viele Sonden; sie
  folgen der Färbung beim Umschalten (Verschiebung, Vergleichsspannung,
  Spannungskomponente) und bleiben, bis *Sonden löschen* sie entfernt.
  Geprüft in `tests/test_gui_smoke.py` (Abschnitt „Werte im Bild und Sonde“).
* **Werteskala** (Maske Ergebnisse, Ribbon *Ergebnisse → Werteskala*): die
  Grenzen der Farbskala sind **automatisch** (kleinster … größter Wert),
  **fest** (unten … oben) oder ein **Grenzwert**: 0 … Grenze, z. B. 355 für
  S355 (bei negativen Werten −Grenze … Grenze). Was über der Grenze liegt,
  bekommt **Magenta** (unter der negativen Grenze Cyan), und die Skala nennt
  darüber den tatsächlichen Größtwert: der oberste Eintrag ist das Maximum,
  der zweite die Grenze. **Farbstufen** wie in ANSYS 9 (bis 256 = stufenlos).
  **Nur Überschreitungen färben**: nur Beträge über der Grenze bekommen Farbe,
  von der Grenze bis zum Größtwert, alles andere bleibt grau — so springen
  die Stellen ins Auge. Der Haken ist in jedem Modus anklickbar und schaltet
  die Skala selbst auf *Grenzwert* um (vorher war er im Modus *automatisch*
  grau, und das las sich als „geht nicht"). Bei einem einzeln gezeigten
  Körper zählen nur dessen Knoten, und die Skala endet an dessen Größtwert.
  Die Statuszeile nennt die Zahl der Knoten über der Grenze und das Maximum
  — oder sagt, dass **nichts** über der Grenze liegt und deshalb alles grau
  bleibt (mit dem Größtwert, damit man weiß, wie weit die Grenze weg ist).
  Kopfzeile und Berichtsbild nennen die Skala. Die Einstellung wird mit dem
  Modell gespeichert.
* **Umhüllende einer Kombination.** Eine Kombination mit Alternativen (aus
  einer RFEM-Ergebniskombination „LF1 oder LF2 oder …") hat kein einzelnes
  Ergebnis, sondern eine Umhüllende: Minimum und Maximum je Größe über ihre
  Alternativen, mit dem maßgebenden Lastfall. Sie steht in Modellbaum,
  Ergebnismaske, Bericht und Browser als „Umhüllende *Name*" neben den
  Umhüllenden je Art (GZT, GZG, Ermüdung), die sie mit enthalten. Im
  Kombinationsdialog zeigt sie ihre Alternativen; die Faktorfelder sind dort
  gesperrt, denn die Alternativen kommen aus der Quelldatei. Ein umbenannter
  oder gelöschter Lastfall zieht durch alle Alternativen.
* Schnittgrößenverläufe N, Vy, Vz, Mt, My, Mz an den Stäben (bei Umhüllenden
  der betragsmäßig größere Extremwert), auswählbar im Modellbaum unter
  „Ergebnisse → Schnittgrößen".
* Kennwerte als Text im Bild: größte Verformung, Grenzwerte der Schnittgrößen,
  größte Ausnutzung und Vergleichsspannung — jeweils mit dem Ort. Sie sind Teil
  des Bildes und stehen damit auch im Bericht.
* Tabellen: Stabkräfte, Auflagerkräfte, Umhüllende, Nachweise, Ermüdung,
  Kontakt, Anschlüsse — filterbar, sortierbar, mit Max-/Min-Zeile, ausgebbar nach
  Zwischenablage, CSV und Excel (Kapitel 2, „Tabellen"). Modellexport
  außerdem CSV, VTK (ParaView).
* Statischer Bericht: Projektdaten, System, Einwirkungen, Kombinationen,
  Ergebnisse, Nachweise mit allen Zwischenwerten, Beulen (EC3-1-5), Ermüdung,
  Anschlüsse (jede Schraube, jede Naht), Verformungen (GZG), Kontakt,
  Zusammenfassung – HTML (Browser: Drucken → PDF), PDF (reportlab) oder
  Markdown.

**Ergebnisse neben der Modelldatei.** Speichern schreibt die Rechnung —
Lastfälle, Kombinationen, Umhüllende, Nachweise — in eine zweite Datei
`<modell>.ergebnisse` neben die Modelldatei; Öffnen liest sie wieder ein,
wenn sie zum Modell passt (Knoten- und Elementzahl, Koordinaten,
Lastfallnamen), und das Programm steht danach wieder auf „berechnet“. Bis
zum 12.09.2026 war nach dem Öffnen jede Rechnung weg — am Drehlager 18
Minuten je Lastfall. Ein Modell, das nach der Rechnung verändert wurde,
passt nicht mehr; das Protokoll sagt es, und die Datei bleibt liegen. Ohne
Rechnung entfernt Speichern eine alte Ergebnisdatei. Die Datei enthält das
Modell nicht (es steht in der Modelldatei) und kann groß werden: je
Lastfall die Verschiebungen aller Knoten und die Spannungen aller Elemente
(Drehlager: rund 90 MB je Lastfall). Geprüft in `tests/test_ergebnisse.py`.

**Kontaktkräfte im Bericht.** Das Kapitel *Kontakt* nennt je
**Kontaktpaar** (Kontaktbedingung, Kontaktpaar Knoten–Fläche, einseitiges
Lager) die **Kontaktkräfte** als Zahl statt nur als Liste der Knoten: die
Summe der Normalkräfte ΣF_n der aktiven Knoten (Druck positiv), die
Resultierende R aller Kontaktkräfte (Normal- und Reibkräfte) auf die
Kontaktknoten mit ihren drei Komponenten, die resultierende Reibkraft |F_t|
(nicht die Summe der Knotenbeträge — am Block mit Reibung 20 kN statt
26 kN), die **mittlere Pressung p_m = ΣF_n/A** und den größten Kontaktdruck
p = F_n/A je Knoten — denn eine Kraft allein sagt nichts über die
Beanspruchung: 10 kN sind viel auf einer kleinen und wenig auf einer großen
Fläche, und der Nachweis läuft über die Pressung; die Kraft selbst braucht
man für Gleichgewicht, Lastpfad und die Bemessung des Gegenstücks —, die
wirksame Fläche
A der aktiven Knoten (aus den Einflussflächen der Kontaktknoten) und die
Zahl der aktiven, haftenden und gleitenden Knoten. **Je Paar oder je
Fläche?** Eine Kontaktbedingung ist *ein* Paar mit allen ihren Flächen;
umfasst sie mehrere, folgen der Zeile des Paars Zeilen **je Fläche** (nach
der Fläche, auf der der Kontaktknoten liegt) — bei einer Fläche je
Bedingung, wie an den Lagerflächen des Drehlagers, ist die Kraft je Paar
die Kraft je Fläche. Dieselben Zahlen stehen in der Oberfläche in der
Tabelle **Kontaktpaare** (*Ergebnisse → Kontaktpaare*, mit Kennwerten,
Filter und Ausgabe wie jede Tabelle) und lassen sich als Berichtseintrag
„Kontaktpaare“ einfügen; die Tabelle **Kontakt** je Knoten nennt jetzt in
der Spalte *Paar*, zu welchem Paar der Knoten gehört. Zuerst steht eine
**Übersicht** mit dem maßgebenden Ergebnis je Kontaktpaar (größte
Normalkraftsumme), dann je Lastfall und Kombination die Tabelle der
Kontaktpaare — in der Kurzform für die ersten 5, im mittleren Umfang für 20
Ergebnisse, in der Langform für alle. Die Liste **je Knoten** (F_n, F_t,
Spalt) gibt es nur noch in der Langform; die Kurzform des Drehlagers blieb
damit lesbar. Am Block mit Reibung (Auflast 90 kN, Horizontalkraft 20 kN)
stehen ΣF_n = 90 kN, ΣF_t = 20 kN und die Aufstandsfläche 0,16 m² — geprüft
in `tests/test_spannungen.py` (`test_kontaktkraefte`) und
`tests/test_report.py`.

**Umfang des Berichts.** Der Dialog (Bericht → Bericht, Strg+R) fragt zuerst
den **Umfang**: **Kurzform** (Vorgabe) nennt Kennwerte, Übersichten und die
Zusammenfassung — ohne Listen je Knoten und Element, ohne Ergebnisse je
Lastfall, ohne Schnittgrößenverläufe und ohne Nachweisdetails je Stab;
**Mittel** fügt je fünf Lastfälle und Kombinationen, zehn Verläufe und die
Nachweisdetails der zwanzig am höchsten ausgenutzten Stäbe hinzu;
**Langform** ist alles. Die Haken darunter zeigen, was der Umfang enthält;
ein von Hand gesetzter Haken macht daraus eine **eigene Auswahl**. Der
gewählte Umfang bleibt am Modell.

**Große Netze.** Ab 200 000 Elementen zeichnet der Bericht in den
Systemdarstellungen die **Umrisse der Volumenkörper** statt der Außenflächen
des Netzes; die Bildunterschrift sagt es. Lastbilder gibt es nur für die
ersten Lastfälle (Kurzform 3, Mittel 10, Langform 30), die übrigen stehen in
den Tabellen. Gemessen am Drehlager (1 812 423 Tetraeder, 422 Lastfälle, drei
gerechnete Ergebnisse, 12.09.2026), vorher → nachher:

| Kapitel | vorher | nachher |
|---|---|---|
| System (drei Ansichten) | 193 s, Facetten des Netzes | 5 s, Umrisse der Körper |
| Einwirkungen (Lastbilder) | 422 Bilder, je etwa 1 min | Kurzform 3 s, Langform 24 s |
| Ergebnisse (Übersicht, Kennwerte) | 154 s (Vergleichsspannung je Element in Python) | 13 s (vektorisiert) |
| Zusammenfassung und Anhang (Modellprüfung) | 58 s (zweimal geprüft) | 16 s (einmal, Teiltragwerke über scipy) |
| **Bericht gesamt** | **Stunden** | **Kurzform 41 s, Langform 120 s** |

Die Kurzform-Datei des Drehlagers ist 21 MB groß (Langform 100 MB) — die
Bilder sind SVG mit den Umrissen und den Lasten. Ein Fehler von gestern ist
dabei behoben: Ermüdungslasten mit globaler Lastspielzahl rissen den Bericht
(„unsupported format string passed to NoneType“); die Tabelle nennt jetzt
„2e+06 (global)“.

**Rahmen des Berichts** (Bericht → Berichtsrahmen, auch im Berichtsdialog): Kopf- und
Fußzeile mit Platzhaltern `{projekt} {bauteil} {position} {auftraggeber}
{bearbeiter} {datum} {modell}` (leere Teile fallen weg), beim Drucken auf
jeder Seite; Ränder in mm, Schriftgröße, Rahmenlinie, Logo (PNG/JPG, Breite
in mm, auf dem Titelblatt), Titelblatt und Inhaltsverzeichnis ein oder aus.
Der Rahmen wird mit dem Modell gespeichert.

**Gliederung analog InfoCAD.** Der Bericht setzt sich aus den Kapiteln des
Programms und den **Einträgen** der Tabelle „Bericht" zusammen (Register
Bericht → Gliederung, oder die Knöpfe an der Tabelle):

* **Ansicht übernehmen** — das Bild der Ansicht samt Ergebnis, Färbung,
  Verlauf und Überhöhung (wie bisher).
* **Text einfügen** — ein eigener Absatz; Leerzeile trennt Absätze, „# Titel"
  wird eine Überschrift, „- Punkt" eine Aufzählung.
* **Tabelle einfügen** — eine Ergebnistabelle zum gezeigten Ergebnis:
  Stabkräfte, Auflagerkräfte, Umhüllende, Nachweise EC3, Ermüdung, Kontakt,
  Lastfälle oder Kombinationen (gekürzt wie im Bericht üblich).
* **Datei einfügen…** — Bilder (PNG, JPG, GIF, WEBP), SVG als Grafik, CSV und
  XLSX (erstes Blatt) als Tabelle, Markdown und Text als Absätze. PDF und DOCX
  werden nicht eingebettet; der Bericht nennt die Datei an der Stelle, sie
  ist als Anlage beizulegen.

Jeder Eintrag hat einen **Platz im Bericht** (Spalte „Nach Kapitel" oder die
Maske per Doppelklick): hinter Allgemeines, System, Einwirkungen,
Ergebnisse, Nachweise EC3, Volumen, Ermüdung, Anschlüsse, Verformungen oder
Zusammenfassung; ohne Angabe stehen die Einträge am Ende unter „Übernommene
Ergebnisse". Reihenfolge, Name, Bildunterschrift und Bemerkung sind in der
Tabelle änderbar (▲ ▼). Geprüft in `tests/test_report.py`
(`test_gliederung_und_rahmen`).

## 11 Tastenkürzel

Strg+N neu, Strg+O öffnen, Strg+S speichern, Strg+I importieren,
Strg+R Bericht, F5 berechnen, Strg+Z rückgängig, Strg+Y wiederholen,
Strg+Umschalt+C vordere Tabelle kopieren.

Ansicht: Strg+1 voll, Strg+2 transparent, Strg+3 Hidden-Line,
Strg+4 Drahtmodell, F9 FE-Netz ein/aus.
Maus im Bild: Rad zoomt zum Zeiger, linke Taste wählt, gedrückte mittlere
dreht, gedrückte rechte schiebt (ohne Zug: Kontextmenü), Doppelklick mit der
mittleren Taste passt alles Sichtbare ein.
Strg+B übernimmt die Ansicht in den Bericht.
Esc bricht ab, was gerade mit Fortschrittsbalken und Abbrechen-Knopf läuft
(Vernetzen, Berechnung, Nachweise, Wind, Wasserdruck) - wie der Knopf
**Abbrechen** neben dem Balken, gleich welches Feld den Fokus hat; läuft
nichts, nimmt Esc ein aufgezogenes Auswahlfenster zurück oder hebt die
Auswahl auf („Alles deselektieren“).
Fang: F3 ein/aus, Umschalt+F1 Knoten, Umschalt+F2 Kantenmitte,
Umschalt+F3 Raster, Umschalt+F4 Linien, Umschalt+F5 Stäbe,
Umschalt+F6 Flächen, Umschalt+F7 Volumen.

Die Kürzel gelten in jedem Register des Ribbons - auch wenn der Befehl in
einem anderen Register steht als dem, das gerade vorn liegt; sie hängen am
Programmfenster, nicht am Knopf. (Gemessen 12.09.2026: vorher wählte Strg+A
im Register „Ansicht“ 0 von 17 Knoten, im Register „Start“ alle 17, weil Qt
ein Kürzel nur auslöst, solange ein Knopf des Befehls sichtbar ist; ebenso
stumm außerhalb ihres Registers waren Strg+N, Strg+O, Strg+I, Strg+E, Strg+Q,
Strg+R, Strg+B, Strg+Umschalt+C und Umschalt+F1 bis F7.) Jede Tastenfolge
gehört genau einem Befehl: Das Register „Auswahl“ zeigt „Alles deselektieren“
noch einmal, das Kürzel Esc trägt aber nur der Befehl im Register „Start“ -
zwei Befehle mit demselben Kürzel blockierten sich in Qt gegenseitig, und Esc
tat nichts, solange das Register „Auswahl“ vorn lag. Kürzel wirken nur,
wenn das Programmfenster aktiv ist. Steht der Cursor in einem Textfeld, geht
Strg+A an das Feld (Text markieren), nicht an das Modell.

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

### Lastfälle nach DIN 19704 anlegen und das Lastenheft

**Lastfälle nach DIN 19704…** (Register *Lasten → Lastfälle*) legt die
Lastfälle eines Stahlwasserbaus mit einem Klick an: rechts in der Maske ein
Haken je Einwirkung — vorgehakt sind Eigengewicht G, Ausrüstung G_A,
Wasserdruck ständig W_S und veränderlich W_V, Wind W, Temperatur T, Eis EIS,
Betriebslast Q_BEW und Antriebsmoment A_M; die übrigen (Verkehr,
Grenzmoment, Wind während der Bewegung, Schwall, Anprall, Verklemmen,
Montage, Erdbeben) nach Bedarf. Jeder Lastfall bekommt das Kürzel als
Namen, die Einwirkungsart, die Beschreibung der Einwirkung und eine
fortlaufende Lastfallnummer ab der eingetragenen ersten Nummer; das
Eigengewicht trägt g. Die Lasten selbst kommen danach aus den Masken und
Generierern (Wasserdruck, Wind) in diese Lastfälle; „Kombinationen nach
DIN 19704 bilden" kombiniert sie je Lastfallklasse.

**Lastenheft** (Register *Bericht*) schreibt ein eigenes Dokument (HTML,
mit Strg+P als PDF; auch Markdown), das **alle anzusetzenden Einwirkungen
erläutert**: je Einwirkung der normative Hintergrund (DIN 19704-1/-2/-3,
ZTV-ING, DIN EN 1990/1991, Betreibervorgaben), was sie ist, wie sie
angesetzt wird (Ansatz und Formel), ihre Lastfallklassen und Beiwerte
(γ_F je Klasse, ψ₀ — Voreinstellungen mit * gekennzeichnet), was das Modell
dazu schon kennt (Lastfälle mit Nummer, Wasserdruck- und Windgenerierer,
Antriebsmomente der Stellungen) und eine **Skizze** des Ansatzes
(hydrostatisches Druckdreieck zwischen Ober- und Unterwasser mit den
Wasserständen des Modells, Wind, Eisdruck am Spiegel, Temperatur,
Antrieb, Betriebslast, Anprall, Schwall, Verklemmen, Montage, Erdbeben).
Dazu die Kombinationsregel der Lastfallklassen, die Teilsicherheitsbeiwerte
der Widerstände und die ZTV-ING-Prüfliste. Zahlenwerte, die als Vorgabe
stehen (Eisdruck, Temperaturunterschied, Betriebswind, Anprall, Wichten),
sind **zu bestätigen** — das Heft weist sie aus; Fundstellen werden als
Norm und Thema genannt.

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

Die Stellungen gehören zum Modell und werden mit ihm gespeichert; eine
**Situation** (Modellbaum → Situationen) verbindet eine Stellung mit den
Elementen, die darin nicht wirken, und wird von Lastfällen und Kombinationen
genannt (siehe „Situationen“ in Kapitel 2).


Im Register **⟳ Stellungen** stehen alle Stellungen in einer Tabelle mit Winkel,
ausgefallenen Lagern, geltenden Lastfällen, η und größter Verformung.
„+ Stellung" und „Ändern" öffnen die **Maske rechts** (Bezeichnung,
Ausgangsstellung, Verschiebung, Verdrehung, deaktivierte Stäbe, Flächen,
Volumen, Gelenke und Lager — siehe „Stellungen: Lage und Wirkung des
Systems“ in Kapitel 2); „Entfernen" arbeitet auf der gewählten Zeile.
Lastfälle je Stellung und Antriebsmoment kommen aus der Python-Schnittstelle
(`Stellung(faelle=…, antrieb=…)`). **▶ Alle Stellungen rechnen** rechnet jede Stellung einzeln
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
