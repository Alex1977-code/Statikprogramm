# Zu zweit (oder zu dritt) an Statik3D arbeiten

Das Repository ist **öffentlich**: <https://github.com/Alex1977-code/Statikprogramm>.
Lesen, herunterladen und die fertige `Statik3D.exe` benutzen kann darum jeder,
auch ohne GitHub-Konto. Nur zum **Schreiben** braucht es eine Freigabe.

## 1 Was der Kollege bekommt

| Er will … | Was er braucht |
|---|---|
| nur das Programm benutzen | nichts – `Statik3D.exe` aus dem Release **latest** herunterladen: <https://github.com/Alex1977-code/Statikprogramm/releases/tag/latest> |
| Fehler melden, Wünsche äußern | ein GitHub-Konto – dann *Issues* im Repository |
| am Code mitarbeiten | ein GitHub-Konto **und** Schreibrecht (unten) – oder er arbeitet über einen Fork |

## 2 Schreibrecht geben

Auf github.com im Repository:

**Settings → Collaborators and teams → Add people →** GitHub-Benutzernamen des
Kollegen eintragen → Rolle **Write**.

Er bekommt eine Einladung per Mail und kann danach klonen, Zweige anlegen und
Pull Requests stellen. **Admin** braucht er nicht; Write genügt für alles, was
zum Entwickeln gehört.

*Ohne* Schreibrecht geht es auch: er drückt oben rechts auf **Fork**, arbeitet
in seiner Kopie und stellt von dort einen Pull Request. Das ist der übliche
Weg, wenn man erst einmal sehen will, ob die Zusammenarbeit passt.

## 3 Die Regel, auf die es ankommt

> **Auf `main` wird nicht unmittelbar gepusht.**

Jeder Push auf `main` baut über GitHub Actions eine neue `Statik3D.exe` und
veröffentlicht sie als Release `latest` – und **jede laufende Installation holt
sich diese Datei beim nächsten Start**. Was auf `main` liegt, ist also nicht
„der Stand der Arbeit", sondern das, was beim Kollegen und beim Kunden startet.

Darum:

1. Für jede Sache einen eigenen Zweig:
   `git switch -c thema/kurzer-name`
2. Dort arbeiten, klein und oft einchecken.
3. **Vor jedem Push die Prüfungen laufen lassen** (siehe unten).
4. Zweig pushen, auf GitHub einen **Pull Request** nach `main` stellen.
5. Der andere liest ihn durch und merged.

## 4 Prüfungen

```bash
python tests/run_all.py          # alle Rechen- und Importprüfungen
python tests/run_all.py --gui    # zusätzlich die Oberfläche (braucht einen Bildschirm)
```

Beides muss **vollständig** durchlaufen (`ALLE TESTS BESTANDEN`). Die Prüfungen
sind der eigentliche Schutz: Sie rechnen gegen geschlossene Lösungen
(Balkenformeln, Gleichgewichtssätze, Volumen aus dem Gaußschen Satz), nicht
gegen frühere Ergebnisse. Wer etwas ändert, das eine Prüfung reißt, hat
entweder einen Fehler gemacht oder muss begründen, warum die Prüfung falsch
war – beides gehört in den Pull Request.

Neue Rechenwege bekommen eine neue Prüfung mit einem Sollwert, den man in einer
Zeile nachrechnen kann. Kein „sieht plausibel aus".

## 5 Wer macht was – die Module sind die Schnittstelle

Der Code ist so geschnitten, dass zwei Leute sich nicht ins Gehege kommen:

| Verzeichnis / Datei | Thema |
|---|---|
| `statik3d/model.py` | Datenmodell (Knoten, Linien, Flächen, Körper, Lasten) – **hier abstimmen**, alles hängt daran |
| `statik3d/mesher.py`, `mesher3d.py` | Vernetzung, freier 3D-Vernetzer |
| `statik3d/assemble.py`, `solver.py`, `elements/` | Steifigkeiten, Gleichungslöser, Elemente |
| `statik3d/ec3/`, `joints/`, `bridges/` | Nachweise |
| `statik3d/importers/` | Schnittstellen (RFEM, IFC, DXF, SAF, …) |
| `statik3d/gui/` | Oberfläche |
| `statik3d/report/` | Bericht |
| `docs/` | Handbücher |

Faustregel: **Ein Pull Request fasst ein Thema an.** Zwei Leute an derselben
Datei gleichzeitig geht gut, solange es verschiedene Funktionen sind; zwei
Leute an `model.py` sollten kurz miteinander reden.

## 6 Umgebung einrichten

```bash
git clone https://github.com/Alex1977-code/Statikprogramm.git
cd Statikprogramm
python -m pip install -r requirements.txt      # numpy, scipy, PySide6, pyvista …
python -m statik3d                              # startet die Oberfläche
```

Python 3.11 oder neuer. Für den Bericht als PDF zusätzlich `reportlab`, für den
CAD-Import `ezdxf` beziehungsweise `ifcopenshell` – beides ist freiwillig, das
Programm sagt selbst, wenn etwas fehlt.

## 7 Claude Code gemeinsam benutzen

Der Kollege kann genauso mit Claude Code an dem Repository arbeiten:
<https://claude.ai/code> → GitHub verbinden → `Alex1977-code/Statikprogramm`
auswählen. Er braucht dafür ein eigenes Anthropic-Konto und (für das Schreiben)
das Schreibrecht aus Abschnitt 2.

**Damit sich nichts überschreibt:** jeder lässt Claude auf einem *eigenen*
Zweig arbeiten und merged über Pull Requests. Zwei Sitzungen auf demselben
Zweig gehen schief.

## 8 Was gerade offen ist

Steht im Bericht der letzten Sitzung und in den Handbüchern; die größeren
Punkte:

* **Starre Fugenebene bei nicht passenden Netzen** – steht in der Freigabe
  „ux/uy starr", die beiden Netze passen an der Fuge aber nicht Knoten für
  Knoten zusammen, trägt das Kontaktpaar nur Druck und Reibung. Eine starre
  Verbindung in der Fugenebene gibt es dort nicht; das wird gemeldet.
* **Wölbkrafttorsion bei statisch unbestimmtem Torsionsweg** – das Stabelement
  hat sechs Freiheitsgrade je Knoten; die Wölbsteifigkeit verteilt die
  Torsionsmomente dann anders auf die Stäbe, als gerechnet wird. Der Weg
  dorthin wäre ein Stabelement mit sieben Freiheitsgraden.
* **Wölbordinaten nur für I und U** – für andere offene Querschnitte wird der
  Momentenanteil ausgewiesen, aber keine Wölbspannung; sie würde geraten.
* **Theorie III. Ordnung** rechnet mit der korotationalen Tangente
  Tᵀ(k_l + k_g)T ohne die Zusatzterme der konsistenten Tangente (Crisfield
  Kap. 17) — Konvergenz linear statt quadratisch; Lasten richtungstreu,
  keine Folgelasten; nur Stabtragwerke. Ein Bogenlängenverfahren für
  Durchschlagprobleme fehlt.
* **Subsysteme** sind bisher eine Gliederung (Auswahl, Baum, Speichern);
  eine Berechnung je Subsystem (Teilsystem freischneiden, Schnittkräfte an
  den verdoppelten Berührungselementen) steht noch aus.
* **Situationen mit Stellung** rechnen auf einer gedrehten Kopie des Modells;
  der Antrieb (`Stellung.antrieb`) und die Lastfallauswahl der Stellung
  (`faelle`) gelten nur in der Stellungsreihe, nicht in der Situation.
* **Torsion freier Polygonquerschnitte** (`sections.polygon`) ist eine
  Näherung nach Saint-Venant (A⁴/(4π²·Ip)); exakt wäre die Lösung der
  Prandtlschen Spannungsfunktion auf dem Polygon (kleines FE-Problem). Der
  Wert lässt sich in der Tabelle „Querschnitte“ von Hand überschreiben.
* **Werkstoff- und Querschnittsnamen** aus der Dlubal-Datenbank
  (`C:\Program Files\Dlubal`) – die Dateien liegen nur lokal vor.
* **Splitter am Rand**: Tetraeder, deren vier Knoten alle auf der Oberfläche
  liegen, lassen sich nicht glätten. Sie werden gezählt und gemeldet.
* **Startbild des Packers** (`Splash` in `packaging/Statik3D.spec`) braucht
  Tcl/Tk des Build-Python; auf dem GitHub-Windows-Läufer ist es dabei. Fehlt
  es einmal, bricht PyInstaller mit einer klaren Meldung ab — dann die
  `Splash`-Zeilen aus dem Rezept nehmen, das Qt-Startbild
  (`statik3d/gui/start.py`) läuft unabhängig davon.
* **RFEM-Linienlasten und Volumen-Temperaturlasten** werden über die
  Spaltennamen der Tabellen `LineLoadImpl*` und `SolidLoadImpl*` gelesen;
  eine Datei mit solchen Lasten lag noch nicht vor, die Namen folgen dem
  Muster der anderen Lasttabellen (magnitude/magnitudeFirst/Second,
  distanceA/B, loadDirection). Beim ersten echten Fall prüfen.
* **Z-Achse nach unten** (Importhaken) ist für RFEM-Dateien vorbelegt; die
  Einstellung `ModelData.globalAxesOrientation` der Datei wird noch nicht
  ausgewertet (0 im Drehlager, vermutlich „Z nach unten“).
* **Fang auf krummen Flächen ohne Netz** greift auf der gezeichneten
  Coons-Fläche (Dreiecke), nicht auf der exakten Zylinderfläche — bei 16
  Stücken je Bogen liegt der Punkt bis 0,5 % des Radius neben dem Mantel.
* **Drehen sehr großer Volumenmodelle**: die Nebendarsteller bleiben beim
  Drehen weg (ab 20 000 Knoten und Elementen); das Netz selbst wird nicht
  vergröbert. Reicht das auf schwachen Grafikkarten nicht, wäre eine
  Detailstufe (LOD) des Netzes der nächste Schritt.
