# Statik3D

Finite-Elemente-Statikprogramm für **Stabwerke, Flächentragwerke und
Volumenmodelle** – mit Desktop-Oberfläche, 3D-Viewport, Lastfällen und
Kombinationen nach DIN EN 1990, Kontakt, Nachweisen nach DIN EN 1993-1-1
(Stahlbau, Stabilität) und DIN EN 1993-1-9 (Ermüdung), Import gängiger
Formate (u. a. IFC/SAF/Tabellen aus InfoCAD und RFEM), Mehrkernrechnung,
Rechnerfarm und statischem Bericht.

Alles in Python (numpy/scipy), verifiziert gegen analytische Lösungen und
Handrechnungen (über 270 automatisierte Prüfungen, siehe unten).

---

## Was es kann

| Bereich | Umfang |
|---|---|
| **Stabwerke** | 3D-Balken (12 FHG, Timoshenko-Schub), Fachwerkstäbe, Momentengelenke, Profildatenbank (IPE, HEA, HEB, HEM, SHS, RHS, CHS), Trapez- und Temperaturlasten, Schnittgrößen an Zwischenstellen (DIN 1080) |
| **Flächen** | Ebene Schale = CST-Scheibe + DKT-Platte, Dreiecke und Vierecke, Flächenlasten (normal oder gerichtet), Temperatur |
| **Volumen** | Tet4, Tet10 (quadratisch), Hex8 mit inkompatiblen Moden, Flächendruck, Temperatur |
| **Lastfälle** | Einwirkungskategorien mit ψ-Beiwerten (DIN EN 1990/NA), Ausschlussgruppen, Eigengewicht je Lastfall |
| **Kombinationen** | automatisch GZT 6.10 / 6.10a+b, außergewöhnlich 6.11b, GZG charakteristisch/häufig/quasi-ständig; manuell; Superposition mit einer Faktorisierung; Umhüllende mit maßgebender Kombination |
| **Lager** | je Freiheitsgrad starr/Feder/frei mit **Ausfall bei Zug oder Druck, Schlupf, Reibbeiwert und Grenzkraft**; **Linienlager** (Steifigkeit je m) und **Flächenlager/Bettung** (je m²); Stabendgelenke gelenkig oder als Drehfeder |
| **Kontakt** | einseitige Lager (nur Druck, Bettung), Spaltelemente Knoten–Knoten, Kontaktpaare Knoten–Fläche (Schalen/Volumen) mit Coulomb-Reibung; Penalty-Verfahren mit Aktivmengen-Iteration |
| **Querschnitte** | Profildatenbank **nach Land**: Europa (IPE, HEA/B/M, UPN, UPE, Winkel, SHS/RHS/CHS), Großbritannien (UB, UC, PFC), USA (W, C, HSS, Pipe) – 442 Profile; **zusammengesetzte Querschnitte** mit Versatz, Drehung, Spiegelung |
| **Nachweise EC3** | Klassifizierung (Tab. 5.2, wirksame Querschnitte Kl. 4), Querschnittsnachweise 6.2 (N, V, M, M+V, M+N, Torsion, σv), Biegeknicken, Drillknicken, Biegedrillknicken (Mcr, C1 automatisch), Interaktion 6.3.3 Anhang B |
| **Ermüdung** | EN 1993-1-9: Kerbfälle, Wöhlerlinien (m = 3/5, Dauerfestigkeit, Schwellenwert), Palmgren-Miner, γMf nach Schadensfolge |
| **Analysen** | Lineare Statik, Modalanalyse, lineares Knicken (Lastfall oder Kombination als Grundzustand) |
| **Import** | **RFEM/RSTAB-Projektdateien** (.rf5/.rf6/.rs5/.rs6/.rs8/.rs9 – Behälter wird untersucht und gelesen, soweit zugänglich), Statik3D-JSON, DXF, IFC (Statikmodell: InfoCAD, RFEM, Allplan …), SAF (.xlsx: RFEM 6, SCIA …), RFEM/RSTAB-Tabellenexport (.xlsx/.csv), Abaqus/CalculiX .inp, Nastran .bdf, STEP/IGES/BREP/STL über gmsh |
| **Parallel** | Elementschleifen und Aufträge auf mehreren Kernen; Rechnerfarm (Server/Worker/Client) über das Netz; optional MKL-Pardiso-Löser |
| **Dokumentation** | Statischer Bericht (HTML druckbar, PDF, Markdown) mit Systemgrafiken, Schnittgrößenverläufen, allen Nachweiswerten; Benutzer-, Theorie-, Schnittstellen- und Farm-Handbuch in `docs/` |
| **Export** | JSON-Modell, CSV, VTU (ParaView) |
| **Handy / Browser** | Web-Server (`python run_web.py`) mit mobiler Oberfläche: 3D-Ansicht per Touch, Eingabe, Berechnung, Ergebnisse, Nachweise, Bericht; auch aus der Desktop-GUI startbar (gemeinsames Modell) |

Einheiten durchgängig SI: **m, N, Pa, kg/m³**.

---

## Windows-Programm (exe)

**Download, immer die neueste Version:**
https://github.com/Alex1977-code/Statikprogramm/releases/latest/download/Statik3D.exe

Eine einzelne Datei, keine Installation, kein Python nötig. Beim ersten Start meldet
Windows SmartScreen ein unbekanntes Programm: „Weitere Informationen“ → „Trotzdem ausführen“
(das Programm ist nicht signiert). Der erste Start dauert einige Sekunden, weil sich die exe
entpackt. Unten rechts im Fenster sitzt der Knopf **Update suchen**: Er fragt GitHub nach
dem neuesten Stand, lädt die neue exe herunter, tauscht sie aus und startet Statik3D neu.
Die exe wird von GitHub Actions bei jedem Stand von `main` automatisch gebaut
(`.github/workflows/windows-exe.yml`) und als Release „latest“ veröffentlicht.

## Windows: Ein-Klick-Start aus dem Quellcode

1. Python 3.11 oder 3.12 von https://www.python.org/downloads/windows/ installieren („Add python.exe to PATH“ anhaken).
2. Diese Datei in einen eigenen Ordner (z. B. `C:\Statik3D`) speichern:
   **https://raw.githubusercontent.com/Alex1977-code/Statikprogramm/main/Statik3D-Windows.bat**
   (im Browser Strg+S bzw. Rechtsklick → „Ziel speichern unter“).
3. Doppelklick. Die Datei holt bei jedem Start die aktuelle Version von GitHub, richtet einmalig
   die Python-Umgebung ein und startet die Oberfläche. `Statik3D-Windows.bat handy` startet
   stattdessen den Server für Handy und Browser, `Statik3D-Windows.bat offline` startet ohne Aktualisierung.

Eigene Modelle in den Ordner `Projekte` neben der Startdatei legen; der Ordner `Statikprogramm` wird
bei jeder Aktualisierung ersetzt. Ohne Startdatei: der Stand von `main` als ZIP ist immer unter
https://github.com/Alex1977-code/Statikprogramm/archive/refs/heads/main.zip.

## Installation

```bash
pip install -r requirements.txt     # numpy scipy PySide6 pyvista pyvistaqt
pip install gmsh                    # optional: CAD-Import
pip install pypardiso mkl           # optional: Mehrkern-Gleichungslöser (155k FHG: 3 s statt 110 s)
pip install reportlab svglib        # optional: PDF-Bericht direkt aus dem Programm
```

Unter Linux zusätzlich `sudo apt install libglu1-mesa libegl1` (gmsh / Qt).

Windows: Python 3.11/3.12 von python.org („Add to PATH“), dann in PowerShell im
Programmordner `py -m venv .venv`, `.venv\Scripts\activate`, `pip install -r requirements.txt`,
`python run_gui.py`. Beim ersten Start von `run_web.py` den Zugriff in der Windows-Firewall zulassen.

## Starten

```bash
python run_gui.py                                              # grafische Oberfläche
python run_web.py --schluessel geheim                          # Bedienung im Browser / auf dem Handy
python -m statik3d.cli --beispiel hall --nachweise --ermuedung --bericht halle.html
python -m statik3d.cli modell.json --kerne 8                   # alle Lastfälle + Kombinationen
python -m statik3d.cli --import projekt.ifc --staebe --kombinationen --speichern projekt.json
python -m statik3d.farm server --port 5555 --key geheim        # Rechnerfarm
python -m statik3d.farm worker --host 192.168.1.10 --key geheim
```

In der GUI: Menü **Beispiele → Hallenrahmen** laden, **F5** – Lastfälle,
Kombinationen, Umhüllende, EC3-Nachweise und Ermüdung in einem Lauf; danach
**Datei → Statischer Bericht**.

---

## Auf dem Handy

```bash
python run_web.py --schluessel geheim --beispiel hall
```

Der PC rechnet, das Handy bedient: Der Server nennt die Adresse im Netz
(z. B. `http://192.168.1.23:8080/`), diese im Handy-Browser öffnen, Schlüssel
eingeben, optional „Zum Startbildschirm hinzufügen“. Register Modell, Lasten,
Rechnen, Ergebnisse, Nachweise und Bericht wie in der Desktop-GUI, 3D-Ansicht
mit Touch. In der Desktop-GUI startet **Berechnung → Bedienung im Browser /
auf dem Handy…** denselben Server für das geöffnete Modell. Details:
`docs/Benutzerhandbuch.md`, Kapitel 11.

## Arbeitsablauf in der GUI

1. **Modell** – Material (Stahlsorte), Querschnitt (Profildatenbank), Schalendicke
2. **Netz** – Stabzug, Platte, Quader erzeugen oder Datei importieren
3. **Lager/Lasten** – Knoten per Klick oder Koordinatenfenster wählen, Lager setzen, Lasten in den aktiven Lastfall
4. **Lastfälle** – Lastfälle mit Kategorie anlegen, Kombinationen automatisch erzeugen, Ermüdungslasten
5. **Kontakt** – einseitige Lager, Spaltelemente, Kontaktpaare
6. **Nachweise** – Stäbe mit Knicklängen, seitlicher Halterung, Kerbfall
7. **Berechnung** – Kerne/Farm wählen, BERECHNEN
8. **Ergebnisse** – Umhüllende, Färbung nach Ausnutzung, Schnittgrößenverläufe, Bericht

Ausführlich: [docs/Benutzerhandbuch.md](docs/Benutzerhandbuch.md).

## Python-API

```python
from statik3d.model import Model, Material, Section
from statik3d import solver, mesher
from statik3d.combinations import generate_combinations

m = Model("Kragarm")
m.add_material(Material.steel("S355"))
m.add_section(Section.from_profile("HEA 200"))
ids = mesher.line_of_beams(m, "S355", "HEA 200", (0, 0, 0), (5, 0, 0), n=10)
m.fix(ids[0], "all")
m.set_gravity(-9.81)                      # LF1 (G)
m.add_load_case("Q", "Q_B", "Nutzlast")
m.load_node(ids[-1], Fz=-20000)
m.add_member("Kragarm", list(range(10)), beta_y=2.0, beta_z=2.0, detail_category=71e6)
m.add_fatigue_load("Lastspiele", "Q", None, 2e6)
generate_combinations(m)

an = solver.solve_all(m, design=True, fatigue=True)
print(an.summary())
print(an.envelopes["ULS"].extreme_table()[:3])
print(an.design.members["Kragarm"].governing)

from statik3d.report import write_report
write_report(m, an, "kragarm.html")
```

---

## Verifikation

```bash
python -m tests.test_verification     # 26 Benchmarks Stab/Schale/Volumen
python -m tests.test_solver_ext       # 49 Prüfungen: Gelenke, Lasten, Kombinationen, Kontakt, Parallel, Farm
python -m tests.test_supports         # 46 Prüfungen: Ausfall, Schlupf, Reibung, Linien-/Flächenlager
python -m tests.test_sections         # 83 Prüfungen: Profildatenbank nach Land, zusammengesetzte Querschnitte
python -m tests.test_rfem             # 38 Prüfungen: RFEM/RSTAB-Import
python -m tests.test_ec3              # 48 Prüfungen: EC3-Handrechnungen
python -m tests.test_importers        # 126 Prüfungen: Import
python -m tests.test_report           # Bericht
python -m tests.test_web              # 91 Prüfungen: Browser-/Handy-Server (API)
xvfb-run -a python -m tests.test_gui_smoke   # Oberfläche (ohne Benutzer)
```

| Benchmark | Abweichung |
|---|---|
| Kragarm Einzellast / Einspannmoment / Auflagerkraft | 0,00 % |
| Einfeldträger Gleichlast, Feldmoment; Gelenkträger; Dreieckslast (Zwischenstellen) | 0,00 % |
| Torsionsstab, Fachwerk, Temperatur (gehalten/frei) | 0,00 % |
| Eulerknicken Fall 2, 1. Eigenfrequenz Kragarm | 0,04 % |
| Platte 4-seitig gelenkig (Navier) | 0,37 % / 0,59 % |
| Patch-Test Tet4 / Hex8 / Tet10 | exakt |
| Superposition vs. direkte Lösung, seriell vs. parallel | 1e-10 |
| Spaltelement: Kontaktkraft F − 3EI s/L³ | 0,00 % |
| HEB 200 χz (Knicklinie c), IPE 300 Mcr / χLT, Interaktion 6.61 | Handrechnung |
| Wöhlerlinie N_R, Miner-Schädigung | exakt |

---

## Grenzen – bitte lesen

* linear-elastisches Material, kleine Verformungen (Theorie II. Ordnung nur als lineares Verzweigungsproblem)
* Kontakt als Penalty-Näherung ohne Lastgeschichte (monotone Lasten); kein Kontakt Fläche–Fläche
* keine Beulnachweise für Blechfelder (EN 1993-1-5, Hinweis im Nachweis), keine Plastizität, keine Zeitbereichsdynamik
* proprietäre Binärformate (.rf5/.rf6/.fem) sind nicht lesbar – Export als IFC-Statikmodell, SAF oder Tabellen

Das Programm ist gegen analytische Lösungen und Handrechnungen verifiziert,
aber **nicht bauaufsichtlich geprüft**. Die Verantwortung für die Anwendung
und Prüfung der Nachweise liegt beim Anwender.

---

## Aktualisieren

* **exe:** Knopf „Update suchen“ unten rechts (oder Hilfe → Nach Update suchen…).
* **Quellinstallation:** derselbe Knopf führt `git pull` aus (Klon) oder lädt `main.zip`
  und ersetzt die Programmdateien; danach Neustart. Ebenso in der Handy-Oberfläche unter
  Mehr → Verbindung / Info → Update suchen.
* `Statik3D-Windows.bat` aktualisiert ohnehin bei jedem Start.

## Aufbau

```
statik3d/
  model.py           Datenmodell: Knoten, Elemente, Lastfälle, Kombinationen, Stäbe, Kontakt
  assemble.py        Assemblierung K, M, Kg, Lastvektoren (parallel), Gelenke
  solver.py          Statik (viele Lastfälle, Superposition, Umhüllende), Kontakt-Iteration, Modal, Knicken
  contact.py         Kontaktbedingungen (Penalty, Aktivmenge, Reibung)
  combinations.py    Kombinationen nach DIN EN 1990
  profiles.py        Profildatenbank
  parallel.py        Prozess-Pool, Auftrags-Registry
  farm.py            Rechnerfarm (Server / Worker / Client)
  jobs.py            registrierte Auftragsarten
  ec3/               Klassifizierung, Querschnitt, Stabilität, Ermüdung, Nachweisführung
  importers/         DXF, IFC, SAF, RFEM-Tabellen, Abaqus, Nastran, xlsx-Leser
  report/            HTML/PDF/Markdown-Bericht, SVG-Grafiken
  elements/          beam3d, shell, solid
  gui/               PySide6-Oberfläche (main, dialogs, viewport, worker)
  web/               Browser-/Handy-Oberfläche: server.py (HTTP-API), static/ (HTML, CSS, JS)
  update.py          Update von GitHub (exe-Austausch, git pull, ZIP)
  supports.py        Knoten-, Linien- und Flächenlager auf Freiheitsgrade umlegen
  sections.py        zusammengesetzte Querschnitte (Steiner, Hauptachsen)
packaging/           PyInstaller-Rezept, Symbol, Build-Stempel (Windows-exe)
  mesher.py, examples_lib.py, cli.py
docs/                Benutzerhandbuch, Theoriehandbuch, Schnittstellen, Rechnerfarm
tests/               Verifikation
```
