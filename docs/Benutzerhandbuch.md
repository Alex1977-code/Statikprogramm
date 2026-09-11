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
noch lief, und die neue Fassung startete nicht.

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
| **Geometrie** | Knoten, Linien, Auswahlart in der Ansicht, Koordinatensysteme, Arbeitsebene und Fang |
| **Struktur** | nach Objektart gegliedert: **Stäbe** (Stab, Stabzug, Stäbe für Nachweise, automatisch erkennen, Querschnitt zuweisen), **Flächen** (Schale, Fläche aus Linien, Rechteckplatte, vernetzen, Dicke zuweisen), **Volumen** (Volumen aus Flächen, Quader, vernetzen), **Gelenke** (Gelenk anlegen, Gelenke setzen, Tabelle), Eigenschaften (Querschnitte, Werkstoffe, Dicken, Elemente löschen) |
| **Lager / Kontakt** | Knoten-, Linien-, Flächenlager, Nichtlinearität, Kontakt, Anschlüsse (anlegen, zeigen, löschen) |
| **Lasten** | Lastfälle, Kombinationen, Lastfälle nach DIN 19704, Knoten-, Stab-, Flächen-, Temperaturlast, Zwangsverformung, Vorspannung, Eigengewicht, Generierer Wasserdruck und Wind |
| **Netz** | Vernetzen (Flächen und Volumen), Netzeinstellungen (Netzdichte, Elementform, intelligente Anpassung), Netzvorschau, Netz löschen, Kontaktfugen |
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
  | Gelenke | Stabendgelenke mit den freigegebenen Freiheitsgraden (der Zweig erscheint, sobald es Gelenke gibt) |
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
  Volumens. Ein Stab mit Nachweis zeigt dazu die Knicklängenbeiwerte β_y und
  β_z und den Haken für das Biegedrillknicken; der Knopf „Nachweisparameter …“
  öffnet alle weiteren (Kipplänge, Momentenbeiwerte, Lastangriff,
  Wölbkrafttorsion, Kerbfall). Eine andere Knotennummer tauscht die beiden Knoten, ein anderer
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
| Flächen, Volumenkörper | über die Maske rechts (Doppelklick): Randlinien bzw. Randflächen — getippt oder mit **„Randlinien anklicken“ / „Randflächen anklicken“** in der Ansicht gewählt —, Dicke, Werkstoff, Teilung, Bemerkung, Haken „gleich vernetzen“ |

**Listenfelder der Masken.** Wo eine Maske eine Namensliste zeigt — Randlinien
einer Fläche, Randflächen eines Volumens, Kontaktflächen, Lastfälle einer
Situation —, steht die **Anzahl in der Beschriftung** („Randflächen (13)“),
das Feld beginnt am Textanfang, und der Zeiger darauf zeigt die
**vollständige** Liste, zehn Namen je Zeile. Vorher stand das einzeilige Feld
am Zeilenende: aus dreizehn Randflächen war „9, F64, F71, F98, F46, F52“ zu
sehen, was sich wie „neun Flächen, davon fünf genannt“ liest — und zu der
falschen Diagnose verleitet, es fehlten Flächen. Wird die Liste in der Ansicht
angeklickt, zählt die Beschriftung mit.
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

#### Kontaktbedingungen anlegen und einstellen

Ein Kontakt wird **wie in ANSYS** angelegt: zwei Körper, mindestens eine
Fläche, dann die Wirkung an dieser Fläche. Der Weg: im Modellbaum unter
*Kontaktbedingungen → Flächenkontakte* auf **„+ Kontaktbedingung anlegen“**
(oder *Lager / Kontakt → Kontaktbedingung…*, oder Rechtsklick → Neu). Rechts
erscheint die Maske:

| Feld | Bedeutung |
|---|---|
| Körper A (Kontaktseite) | der Körper, dessen Flächen die Kontaktseite bilden - er wird an ihnen gelöst |
| Körper B (Gegenseite) | der Körper, gegen den der Kontakt wirkt; „(alle anderen Körper)“ sucht die Gegenseite unter allen Bauteilen |
| Kontaktflächen | mindestens eine Fläche von Körper A - getippt oder mit **„Kontaktflächen anklicken“** in der Ansicht gewählt (jeder Klick nimmt dazu oder heraus) |
| Standardkontakt | setzt die Richtungen darunter mit einem Griff (Tabelle unten); danach lässt sich jede Richtung von Hand ändern, der Standard wird dann „Benutzerdefiniert“ |
| Druck | wird immer übertragen - das ist Kontakt |
| Zug | *abheben möglich* (die Fuge öffnet unter Zug), *wird übertragen* (Verbund, kein Abheben) oder *Feder* |
| Schub x, Schub y | in der Fugenebene *frei (gleiten)* - mit dem Reibbeiwert als Coulomb-Reibung -, *starr (haften)* oder *Feder* |
| Reibbeiwert μ | Coulomb-Reibung in der Fugenebene; 0 = reibungsfrei |
| Verdrehungen | φx, φy, φz starr oder frei - nur bei Schalen wirksam, Volumen haben keine Verdrehungen |
| Feder c | Steifigkeit [kN/m je m²] für Richtungen mit „Feder“ |
| Suchradius | wie weit die Gegenseite entfernt liegen darf (ANSYS: „Pinball“). 0 = automatisch: die größere mittlere Kantenlänge der **beiden Seiten dieser Fuge** — dazu sucht das Programm zweimal, erst weit, um die Gegenseite zu finden, dann mit deren Netz. So bekommt eine feine Fuge nicht die Netzweite eines groben Modells. Damit findet eine fein vernetzte Achse (2 mm) ihre grob vernetzte Bohrung (15 mm) auch mit Spiel; was weiter weg liegt, gehört nicht zur Fuge. Ein eingetragener Wert gilt unverändert |
| Anfangsspalt | *wie modelliert*: ein Spalt bleibt offen, bis die Last ihn schließt; *auf Berührung setzen*: jeder Knoten gilt in seiner Lage als anliegend - Spiel und Facettenfehler zwischen verschieden feinen Netzen verschwinden (ANSYS: „adjust to touch“) |

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

Zum Spalt nennt das Protokoll die **Verteilung**, nicht einen Mittelwert:

```
Spalt 41 % aufliegend, Median 24.94 mm, 90 % unter 33.99 mm, größter 60.56 mm
```

Das ist die Auskunft, auf die es ankommt. Eine teilweise anliegende Fuge hat
zwei Gipfel — ein Teil liegt auf null, der Rest steht ab —, und ein Mittelwert
darüber nennt eine Zahl, die an keiner Stelle der Fuge vorkommt. Steht dort
ein kleiner Anteil „aufliegend“ und ein Median in der Größenordnung des
Netzes, berühren sich die Bauteile im Modell nicht wirklich: dann stimmt
entweder die Geometrie nicht oder der Suchradius ist zu groß gewählt. Dieselbe
Auskunft steht beim Rechnen noch einmal je Kontaktpaar, dort für die Knoten,
zusammen mit der Zahl derer, die gar keine Gegenfacette gefunden haben.

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

Aus RFEM eingelesene Flächenfreigaben stehen in derselben Maske: Körper A ist
der gelöste Körper, die Gegenflächen sind die zugeordneten Flächen der
Quelldatei — die Fuge. „Kontaktflächen“ bleibt dann leer; die Fugenflächen des
gelösten Körpers werden beim Vernetzen geometrisch gesucht. Auch diese
Bedingungen lassen sich auf einen Standardkontakt umstellen oder Richtung für
Richtung ändern.

Ein Klick auf eine solche Bedingung im Modellbaum wählt die zugeordneten
Flächen **und** den gelösten Körper; *Selektion anzeigen* isoliert sie damit
wie jedes andere Objekt.

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
| Intelligent anpassen | kleine Kanten (Löcher, Stege, schmale Flächen) verfeinern das Netz **der Flächen** dort, bis zur kleinsten Elementgröße; die größte Elementgröße deckelt nach oben (leer = ¼ bzw. 4-fache der Dichte-Länge). Bei **Volumen** bleibt die Kantenlänge im Feld: eine ganze Platte auf ihre Bohrung herunterzuteilen gäbe nur das Vielfache an Tetraedern. Fein wird es **örtlich**, an drei zusammengehörenden Stellen: die Bohrungsränder nach ihrer Krümmung, eine Linie neben einer viel feineren (die **Mantellinie** einer Bohrung stand sonst mit *einem* Abschnitt über der ganzen Bohrtiefe), Kränze um jede Öffnung in der Fläche, und von dort wachsend ins Innere. Gemessen an einer 20-mm-Bohrung von 35 mm Tiefe in einer 900-mm-Platte: der Anteil der Tetraeder unter der Güte 0,3 an der Bohrungswand fällt von 6,8 % auf 1,0 % — für doppelt so viele Elemente. Ohne den Haken bleibt es bei ⌈L/h⌉ je Linie |
| Höchstzahl Elemente je Objekt | vergröbert, was sonst zu viele Elemente gäbe (Schätzung A/h² bzw. V/(0,12·h³)) |
| Elementform | Dreiecke, Vierecke oder Vierecke mit Dreiecken als Rückfall |
| Elementansatz | **linear** (shell3/shell4, tet4, hex8) oder **quadratisch**: Flächen bekommen Mittenknoten (shell6/shell8), abgebildete Volumen hex20, freie Volumen tet10. Quadratisch braucht für dieselbe Genauigkeit deutlich weniger Elemente, je Element aber mehr Rechenzeit |
| Teilung je Fläche aus der Netzdichte | an (Vorgabe): die Netzdichte bestimmt die Teilung aller Flächen; aus: die eigene Teilung jeder Fläche (Flächenmaske, RFEM) gilt |

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

**Vorschau** in der Maske und *Netz → Netzvorschau* schätzen die Elementzahl
je Objekt und gesamt ins Protokoll - vor dem Vernetzen, damit ein Modell
mit hunderttausend Tetraedern nicht überrascht. Das Protokoll nennt beim
Vernetzen je Objekt die gewählte Elementgröße und ihren Grund.

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

### Ergebnisse und Bericht

Was gerechnet wurde, steht im **Modellbaum unter „Ergebnisse"**: Umhüllende,
Kombinationen, Lastfälle, die **Schnittgrößen**, die Nachweise, Eigenformen und
Knickfiguren. Ein Klick stellt das Ergebnis in der Ansicht ein — dieselbe
Auswahl, die auch die Maske *Ergebnisse* rechts führt. Dort werden Färbung,
Schnittgrößenverlauf und Überhöhung eingestellt.

Der Zweig **Schnittgrößen** führt N, Vy, Vz, Mt, My und Mz, jede mit ihren
Grenzwerten daneben; ein Klick stellt den Verlauf in der Ansicht ein, „kein
Verlauf" blendet ihn wieder aus.

**Kennwerte im Bild.** Links oben in der Ansicht stehen die Zahlen, nach denen
zuerst gefragt wird: größte Verformung mit Knoten, kleinste und größte
Verformung je Richtung, kleinste und größte Schnittgröße mit dem Stab, an dem
sie auftritt, die größte Ausnutzung mit ihrem Ort und die größte
Vergleichsspannung. Steht ein Schnittgrößenverlauf an, wird nur diese Größe
ausgeschrieben, sonst alle sechs. Der Text gehört zum Bild und kommt darum mit
in den Bericht, wenn man die Ansicht übernimmt. Abschalten: *Ergebnisse →
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
„Knoten" zeigt die gesetzten Knoten als Punkte: Knoten, an denen noch **kein
Element** hängt, sind orange und etwas größer — so sieht man beim Modellieren,
wo man schon war, auch wenn dort noch nichts steht.

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
| Sichtbarkeit | Knoten, Linien, Stäbe, Flächen, Volumen, FE-Netz, Lasten — jedes einzeln schaltbar |
| Sicht | Selektion anzeigen, Auswahl ausblenden, Vorherige Sicht, Alles zeigen, **Verborgenes im Hintergrund** (Schalter), **Schnittebene** (Schalter mit Achse und Schieber), **Intelligente Auswahl** (Schalter) |
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
ebenso wenig zu treffen.

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
Körpers gehen mit ihm. *Vorherige Sicht* nimmt den letzten Schritt
zurück (bis zu zwanzig Schritte), *Alles zeigen* holt alles wieder her. Die
Ausblendung ist nur eine Sicht — am Modell und an der Berechnung ändert sie
nichts. Ein neues Netz oder ein anderes Modell hebt sie auf. Ein
**Doppelklick mit der mittleren Maustaste** im Bild passt die Kamera auf
alles ein, was gerade zu sehen ist (wie *Zoom alles*); Ausgeblendetes zählt
dabei nicht mit.

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
Überhöhung. Unten links stehen die **Kennwerte**: Verformungen und
Verdrehungen (min/max mit Knoten), Schnittgrößen (min/max mit Stab),
Auflagerkräfte (min/max mit Knoten), die größte Vergleichsspannung und die
größte Ausnutzung. Die Farbskalen stehen rechts, das Achsenkreuz unten
rechts; der Schalter „Kennwerte im Bild" im Register *Ergebnisse* nimmt die
Texte weg. Beides kommt so auch in den Bericht.

**Drehen großer Modelle.** Ab etwa 20 000 Knoten und Elementen bleiben
während des Drehens, Schiebens und Zoomens die Nebendarsteller
(Knotenpunkte, Linien, Nummern, Lasten) und die Netzkanten weg und kommen
beim Loslassen der Maus wieder — das Bild bleibt dadurch flüssig.
Volumennetze werden nur mit ihrer Oberfläche gezeichnet.

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

**Linienlager** werden mit kleineren Symbolen **entlang der ganzen Linie**
gezeichnet (auf einem Bogen auf der wahren Kurve), dazu die Linie selbst;
**Flächenlager** im Raster **über die ganze gebettete Fläche**, die Symbole
in Richtung der Flächennormale (bei Volumen nach außen) — nicht mehr nur an
den Knoten. Ein aus RFEM übernommenes Lager kennt seine Linien bzw. Flächen
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

Der Bereich unten ist in **zwei Ebenen** gegliedert: oben die Gruppe, darunter
ihre Tabellen als Register. Eine Gruppe mit nur einer Tabelle (Protokoll,
Bericht) zeigt keine zweite Leiste. Ein Klick im Modellbaum holt die
passende Tabelle nach vorn — samt ihrer Gruppe.

| Gruppe | Tabellen |
|---|---|
| Protokoll | das Protokoll der Berechnung und der Modellprüfung |
| Modell | Knoten, Linien, Flächen, Volumenkörper, Stäbe (alle Elemente), Schweißnähte |
| Eigenschaften | Werkstoffe, Querschnitte, Dicken |
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
| **links** | wählen (Klick) und das **Auswahlfenster** aufziehen (ziehen) |
| **rechts** | **drehen**; ohne Ziehbewegung das Kontextmenü |
| **Mausrad** | zoomen, zum Zeiger hin |
| **Mitte** | schwenken; Doppelklick passt alles Sichtbare ins Bild |

Die linke Taste dreht **nicht** mehr — sie gehört ganz der Auswahl. Dadurch
gibt es keinen Fall mehr, in dem eine Zeigerbewegung mal dreht und mal ein
Fenster aufzieht.

**Auswahlfenster.** Mit gedrückter **linker** Maustaste aufziehen: der
Druckpunkt ist die erste Ecke, der Loslasspunkt die zweite. Wer lieber
klickt: ein Klick ins Leere setzt ebenfalls die erste Ecke, ein zweiter die
zweite; dazwischen zeigt ein durchscheinendes Rechteck, was das Fenster
fassen wird. Ein Klick auf der ersten Ecke verwirft das Fenster wieder.

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
anzeigen* (alles andere ausblenden) und *Selektiertes ausblenden*, darunter
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
* die **Kennwerte** unten links (Verformung, Schnittgrößen, Auflagerkräfte,
  Vergleichsspannung, Ausnutzung),
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
  **Linie** (der Fußpunkt auf der Linie, auch auf einem Bogen), **Stab** (der
  Fußpunkt auf der Stabachse), **Fläche** (der Punkt auf der Fläche oder
  Schale unter dem Zeiger, auch auf einem Zylindermantel), **Volumen** (der
  Punkt auf der Oberfläche eines Körpers), zuletzt der **Rasterpunkt**. Jede
  Art ist einzeln schaltbar — im Ribbon, in der Glasleiste oder mit
  Umschalt+F1 … F7; der Hauptschalter (F3) nimmt alles zurück. Die
  Statusleiste zeigt den Zustand.

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
2. **Eigene Profile** mit Parametern in mm: Rechteck, Kreis, Rundrohr,
   Rechteckrohr, geschweißtes Doppel-T, U, T, Winkel, Kasten aus Blechen —
   oder *frei* nach Steifigkeiten (A, Iy, Iz, It). Auch hier Bild und
   Kennwerte, dann **Anlegen**.
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
| Deaktivierte Gelenke | diese Gelenke sind in der Stellung **biegesteif** (etwa eine Verriegelung) |
| Deaktivierte Knoten-, Linien-, Flächenlager | sie greifen in dieser Stellung nicht — Namen oder Nummern wie im Modellbaum |

Stäbe, Flächen, Volumen oder Knoten (für ihre Lager) in der Ansicht
anklicken und **„Auswahl deaktivieren“** trägt sie in die Listen ein — sie
verschwinden im Bild; „Auswahl aktivieren“ und „Alle aktivieren“ nehmen es
zurück. Solange die Maske offen ist, zeigt die Ansicht die Stellung ohne
ihre abgeschalteten Elemente. Stellungen werden mit dem Modell gespeichert.

### Situationen: Stellung und ihre Lastfälle

Unter „Situationen“ steht immer die **Grundstellung**: unbewegt, alles
wirkt; Lastfälle ohne Situation gelten hier. Eine weitere Situation
entsteht mit **Rechtsklick → Neu: Situation** (oder „+ Situation
anlegen“). Ihre Maske hat nur noch drei Angaben: die **Stellung**, die
**Lastfälle** und die **Kombinationen**, die in dieser Situation gelten
(Namen, durch Komma; „Alle Lastfälle und Kombinationen“ trägt alle ein).
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
und lässt sich dort vernetzen.

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

* **Alle Lastfälle + Kombinationen**: Standard. Eine Faktorisierung, alle
  Lastfälle, Superposition, Umhüllende, optional Nachweise.
* **Nur aktiver Lastfall**, **Eigenschwingungen**, **Knicken** (Grundzustand
  = aktiver Lastfall).
* Prozesse: Zahl der Arbeitsprozesse für Elementschleifen, Aufträge und die
  Vernetzung - Vorgabe alle Kerne bis auf einen, der bleibt der Oberfläche;
  Backend „Rechnerfarm“ mit Server, Port und
  Schlüssel (siehe `Rechnerfarm.md`). „Lokalen Server + Worker starten“
  macht den eigenen Rechner zum Farm-Server.
* **Kontakt-Iteration und Speicher.** Jeder Schritt der Kontakt-Iteration
  faktorisiert das System neu; der Speicher jeder Faktorisierung wird sofort
  danach zurückgegeben. Am Drehlager (1 028 724 Freiheitsgrade, 7 GB je
  Faktorisierung) wuchs der Prozess vorher je Schritt um 7 GB, bis der Löser
  nach 33 Schritten bei 113 GB aufgab (11.09.2026).
* **Prozesspool und Gleichungslöser sind zweierlei.** Der Pool oben verteilt
  Elementschleifen und die Vernetzung auf Prozesse. Das Lösen des
  Gleichungssystems macht ein einzelner Prozess mit eigenen Threads. Das
  Protokoll nennt beim Start einer Rechnung darum beides getrennt:

  ```
  --- Berechnung gestartet ---
      Prozesspool (Elementschleifen, Vernetzen): lokal, 31 von 32 Kernen
      Gleichungslöser: MKL PARDISO, 31 Threads
  ```

  Steht dort „SuperLU, einkernig“, fehlt der Mehrkern-Löser: dann rechnet
  die Faktorisierung auf genau einem Kern, gleichgültig wie viele die
  Maschine hat. Das Windows-Programm bringt Intel MKL mit, so dass PARDISO
  greift - an einem Modell mit 34.914 Freiheitsgraden 1,4 statt 12,3
  Sekunden je Faktorisierung. Wer aus dem Quelltext arbeitet, installiert
  ihn mit `pip install pypardiso mkl`.
* Die Berechnung läuft im Hintergrund. Die Statuszeile zeigt einen
  **Fortschrittsbalken mit Prozentzahl** und daneben, woran das Programm
  gerade ist und wie lange es schon läuft („Berechnung: Lastfall W (5/12)
  (48 %, 73 s)“). Die Schritte sind: Gleichungssystem aufstellen,
  faktorisieren, Lastfälle, Kombinationen, Umhüllende, Nachweise. Jede
  Zeile steht auch im Protokoll.
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

* Färbung: |u|, ux/uy/uz, Vergleichsspannung (Schalen/Volumen, Randspannung
  bei Stäben), Ausnutzung EC3 / Ermüdung / elastisch.
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

## 11 Tastenkürzel

Strg+N neu, Strg+O öffnen, Strg+S speichern, Strg+I importieren,
Strg+R Bericht, F5 berechnen, Strg+Z rückgängig, Strg+Y wiederholen,
Strg+Umschalt+C vordere Tabelle kopieren.

Ansicht: Strg+1 voll, Strg+2 transparent, Strg+3 Hidden-Line,
Strg+4 Drahtmodell, F9 FE-Netz ein/aus.
Maus im Bild: Rad zoomt zum Zeiger, Doppelklick mit der mittleren Taste
passt alles Sichtbare ein, linke Taste dreht, mittlere schiebt.
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
