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
* **Werkstoff- und Querschnittsnamen** aus der Dlubal-Datenbank
  (`C:\Program Files\Dlubal`) – die Dateien liegen nur lokal vor.
* **Splitter am Rand**: Tetraeder, deren vier Knoten alle auf der Oberfläche
  liegen, lassen sich nicht glätten. Sie werden gezählt und gemeldet.
