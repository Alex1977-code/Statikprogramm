# Statik3D

Lineares Finite-Elemente-Programm für **Stabwerke, Flächentragwerke und Volumenmodelle** —
mit Desktop-GUI, 3D-Viewport und CAD-Import.

Alles in Python, verifiziert gegen analytische Lösungen (26 Benchmarks, siehe unten).

---

## Was es kann

| Bereich | Umfang |
|---|---|
| **Stabwerke** | 3D-Balken (12 FHG, Timoshenko-Schub), Fachwerkstäbe, beliebige Querschnitte, Streckenlasten, Schnittgrößen |
| **Flächen** | Ebene Schale = CST-Scheibe + DKT-Platte, Dreiecke und Vierecke, Membran- und Biegeanteil, Flächenlasten |
| **Volumen** | Tet4, **Tet10** (quadratisch), **Hex8 mit inkompatiblen Moden** (biegesteif, kein Locking) |
| **Analysen** | Lineare Statik, Modalanalyse (Eigenfrequenzen/-formen), lineares Knicken für Stabtragwerke |
| **Lasten** | Knotenlasten, Momente, Streckenlasten, Flächendruck, Eigengewicht, vorgegebene Verschiebungen, Federlager |
| **Vernetzung** | Eingebaute strukturierte Netze (Quader, Platte, Stabzug) + **gmsh** für STEP/IGES/BREP/STL |
| **Ergebnisse** | Verformungen, Auflagerreaktionen, Schnittgrößen, Membrankräfte/Momente, Hauptspannungen, Vergleichsspannung, Ausnutzungsgrad |
| **Export** | JSON-Modell, CSV, VTU (ParaView) |

Einheiten durchgängig SI: **m, N, Pa, kg/m³**.

---

## Installation

```bash
pip install numpy scipy PySide6 pyvista pyvistaqt
pip install gmsh          # optional, für CAD-Import
```

Unter Linux zusätzlich `sudo apt install libglu1-mesa` (wird von gmsh gebraucht).

## Starten

```bash
python -m statik3d.gui                                   # grafische Oberfläche
python -m statik3d.cli --beispiel frame --analyse knicken # ohne GUI
python -m tests.test_verification                        # Verifikation nachrechnen
```

In der GUI: Menü **Beispiele → Rahmen / Platte / Konsole** laden und auf
**BERECHNEN** klicken — damit siehst du den kompletten Ablauf in 5 Sekunden.

---

## Arbeitsablauf in der GUI

1. **Modell** — Material, Querschnitt, Schalendicke anlegen
2. **Netz** — Stabzug, Platte, Quader erzeugen oder STEP/STL importieren
3. **Lager/Lasten** — Knoten über ein Koordinatenfenster auswählen
   (z. B. `x min = 0`, `x max = 0` wählt die ganze Einspannebene), dann
   Lager setzen oder Last aufbringen
4. **Berechnung** — Analyseart wählen, `BERECHNEN`
5. **Ergebnisse** — Anzeigegröße wählen, Überhöhung schieben, CSV/VTU exportieren

## Python-API

```python
from statik3d.model import Model, Material, Section
from statik3d import solver, mesher

m = Model("Kragarm")
m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850, fy=355e6))
m.add_section(Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010))

ids = mesher.line_of_beams(m, "S355", "HEA200", (0, 0, 0), (5, 0, 0), n=10)
m.fix(ids[0], "all")
m.load_node(ids[-1], Fz=-20000)

r = solver.solve_static(m)
print(r.summary())
print("Einspannmoment:", r.beam_forces[0]["My"][0] / 1e3, "kNm")
```

---

## Verifikation

`python -m tests.test_verification` → **26/26 bestanden**

| Benchmark | Abweichung |
|---|---|
| Kragarm Einzellast / Einspannmoment / Auflagerkraft | 0,00 % |
| Einfeldträger Gleichlast, Feldmoment | 0,00 % |
| Torsionsstab, Fachwerk | 0,00 % |
| Eulerknicken Fall 2 (10 Elemente) | 0,04 % |
| 1. Eigenfrequenz Kragarm | 0,04 % |
| Scheibe Zug (Verformung + Spannung) | 0,00 % |
| Kragplatte (Schalen) | 0,01 % |
| Quadratplatte 4-seitig gelenkig, Navier | 0,37 % (Dreiecke) / 0,59 % (Vierecke) |
| Patch-Test Tet4 / Hex8 / Tet10 | exakt |
| Volumen-Kragträger Hex8 vs. Timoshenko | 0,12 % |
| Volumen-Kragträger Tet10 vs. Timoshenko | 3,85 % |

---

## Grenzen — bitte lesen

Das Programm ist **linear**. Es kann nicht, was ANSYS kann:

- keine Plastizität, kein Kriechen, keine nichtlinearen Materialgesetze
- **kein Kontakt**, keine Reibung, keine Fügestellen
- keine große-Verformungs-Theorie (Theorie III. Ordnung), kein Beulen von Schalen
  (nur Stabknicken über die geometrische Steifigkeit)
- keine Dynamik im Zeitbereich, keine Thermik, keine Strömung
- keine automatische Vernetzung ohne gmsh, keine Netzadaption

**Für den Stahlwasserbau relevant:** Vorbemessung, Systemverständnis, Variantenvergleich,
Plausibilitätskontrolle fremder Rechenläufe — dafür ist das Werkzeug gut geeignet.
Für **prüffähige Nachweise** ist es das nicht: dafür braucht es geprüfte, validierte
Software. Wenn es nichtlinear werden muss, ist **CalculiX** (Abaqus-kompatibler
Open-Source-Solver) oder **code_aster** der richtige nächste Schritt — das VTU-Export
und das gmsh-Netz aus diesem Programm lassen sich dort weiterverwenden.

---

## Aufbau

```
statik3d/
  model.py            Datenmodell (Knoten, Material, Querschnitt, Lasten)
  assemble.py         Assemblierung K, M, Kg, Lastvektor
  solver.py           Statik, Modalanalyse, Knicken, Postprocessing
  mesher.py           gmsh-Anbindung + strukturierte Netzgeneratoren
  examples_lib.py     fertige Beispielmodelle
  cli.py              Kommandozeile
  elements/
    beam3d.py         Balken/Fachwerk 3D, geometrische Steifigkeit, Massenmatrix
    shell.py          CST + DKT Schale
    solid.py          Tet4, Tet10, Hex8 (inkompatible Moden)
  gui/main.py         PySide6-Oberfläche mit pyvista-Viewport
tests/
  test_verification.py
```

### Erweiterungspunkte

- **Nichtlineare Statik**: Newton-Raphson um `solver.solve_static` legen, Tangenten-
  steifigkeit aus `assemble.geometric_stiffness` (für Stäbe bereits vorhanden)
- **Weitere Elemente**: Muster in `elements/` folgen — Matrix zurückgeben,
  in `assemble.element_matrix` eintragen, Zelltyp in `gui/main.CELL_MAP` ergänzen
- **Lastfallkombinationen**: `Model` mehrfach mit unterschiedlichen Lasten lösen und
  überlagern (linear zulässig)
