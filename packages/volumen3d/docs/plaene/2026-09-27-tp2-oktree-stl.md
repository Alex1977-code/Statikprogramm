# volumen3d Teilprojekt 2: Oktree, hängende Freiheitsgrade, STL – Umsetzungsplan

> Vorgehen: `superpowers:executing-plans` (Aufgaben nacheinander, Prüfung nach jeder Aufgabe).
> Entwurf: `packages/volumen3d/docs/Entwurf.md`, Abschnitt 4b. Läufe aus der Repository-Wurzel
> mit `PYTHONUTF8=1 .venv/Scripts/python.exe -m volumen3d.tests.<suite>`.

**Ziel:** Stufe 1 der Vorgabe vollständig: Verfeinerung mit hängenden Freiheitsgraden, STL-Eingang,
schnellerer Geometriekern; Abnahmen U1–U5 (Entwurf 4b.5); danach Pull Request 1.

**Reihenfolge (jede Aufgabe: Prüfung schreiben → rot → umsetzen → grün → Kernsuite → Commit):**

### Aufgabe 1: Oktree-Gitter (`fcm/gitter.py`, `tests/test_oktree.py`)
- `Verfeinerung(schnitt_ebenen=0, bereiche=(), duenne_waende=False)`; `Gitter(geometrie, h, polster, verfeinerung)`.
- Felder: `ebene`, `ijk` (eigene Ebene), `h_zelle(c)`, `zellbox(c)`, `max_ebene`, `n_ebene(l)`;
  `zelle_finden(P)` über Ebenen (grob → fein, `searchsorted`), `blaetter_in_box(lo, hi)`.
- Aufbau: Wurzelzellen → Regeln bis Fixpunkt → 2:1 über 26 Nachbarn (Ecken eingeschlossen) → OUTSIDE weg.
- Schlüssel: Ecken `(X, Y, Z, -1)` im feinsten verdoppelten Gitter, Kanten/Flächen/Zelle `(X, Y, Z, ebene)`.
- Prüfungen: Kugel mit `schnitt_ebenen=1`: alle CUT-Wurzelzellen geteilt, INSIDE nicht; Bereich um einen Punkt → Ebene 2 dort;
  dünne Platte (3 mm in h = 10) → geteilt; 2:1: kein Blatt hat einen Nachbarn mit Ebenenunterschied > 1 (alle 26 Richtungen, per Punktsuche);
  Punktsuche: 10⁴ Zufallspunkte, jede in genau einem Blatt, Box enthält Punkt; Ecke einer feinen Zelle auf einer groben Ecke: gleiche Nummer;
  gleichmäßiges Gitter (`schnitt_ebenen=0`) liefert genau die Ergebnisse von TP 1 (Modenzahl-Formel).

### Aufgabe 2: Zwangsauflöser (`fcm/zwaenge.py`, `tests/test_zwaenge.py`)
- `Zwaenge(gitter, aggregation: Zellaggregation | None)` → `C` (csr, n_dof × n_frei), `statistik`
  (hängende Flächen/Kanten/Ecken, gebundene Moden, Kettenlänge).
- Hängende Entitäten per Punktsuche (Fläche: Mitte + ε n; Kante: Mitte + ε(d1 + d2); Ecke: acht Oktanten), nur gröbere Treffer.
- Spurabbildungen: Fläche (p+1)² Chebyshev-Lobatto-Punkte, Moden von F mit Index 0/1 in Normalenrichtung; Kante p+1 Punkte; Ecke Punktauswertung.
- Vorrang Fläche > Kante > Ecke > Aggregation; Ketten auflösen; `Zellaggregation` liefert nur noch Rohzwänge (Mode → Wurzelmoden, Koeffizienten), die Matrix baut `Zwaenge`.
- Prüfungen: Spurabbildung reproduziert jedes Tensorpolynom vom Grad p (Zufallskoeffizienten) auf 10⁻¹²;
  Anzahl hängender Entitäten an einem einfach verfeinerten Würfel (eine Ecke Ebene 1: 3 Flächen, 3 Kanten, 1 Ecke … gezählt);
  Patch-Test (T4-Geometrie) mit `schnitt_ebenen=1` und Bereich: u, σ < 10⁻⁶ für p = 1…3; Schnittanteil 10⁻⁶ weiter exakt.

### Aufgabe 3: Zellgrößen überall (`quadratur`, `elastizitaet`, `rand`, `auswertung`, `oberflaeche`, `problem`, `api`)
- `zell_gradienten` mit `h_zelle(c)`; INSIDE-K_e je Ebene skaliert (K ∝ h); Nitsche-β je Zelle; `werkstoffanteile` mit h_c³;
  `aus_dreiecken` über `blaetter_in_box`; Aggregations-Nachbarn per Punktsuche; `api`: `RefinementRegion` → `Verfeinerung.bereiche`,
  `FcmSettings.adaptive_cycles` bleibt 0 (Fehlerschätzer TP 6), Protokoll mit Ebenenverteilung.
- Prüfungen: Kernsuite grün (gleichmäßig unverändert); Lamé mit `schnitt_ebenen=1`, p = 3: σ_r < 0,1 % (Tangentialebenen feiner);
  Kirsch mit Bereich um das Loch (Radius r + h, Zielgröße h/4), p = 3/4, fünf Lagen: Streuung < 1 %, Freiheitsgrade < 40 % des gleichmäßigen h = 2,5.

### Aufgabe 4: STL (`geometry/stl.py`, `tests/test_stl.py`)
- `lies_stl(pfad)` (binär/ASCII) → `Stl(dreiecke, name)` mit `abstand` (Windungszahl-Vorzeichen, Punkt–Dreieck-Abstand),
  `gradient`, `huellquader`, `dreiecke`, `lokale_ebenen` (Ebenen der schneidenden Facetten; `zu_grob`-Signal bei Normalenstreuung > 1°),
  `flaechenfaktor` = 1, `kruemmungsradius` = ∞; CSG-Typ `"stl"`; `api`: `GeometrySourceType.STL` mit `path`.
- Prüfungen: Windungszahl am geschlossenen Würfel (innen 1, außen 0, Kante ½), Würfel mit fehlender Facette (Lücke): Innen/Außen weiter richtig
  (Strahltest würde springen); Abstand zum Würfel; Volumen der Würfel-STL exakt; Lamé-Viertelzylinder als STL (Facette 1 mm) gegen CSG < 0,2 %.

### Aufgabe 5: Geometriekern schneller
- Kinder gemeinsam klassifizieren; Grundform-Abstände je Zelle gebündelt; Modennummerierung vektorisiert; Profil vorher/nachher im Commit.
- Prüfung: alle Suiten unverändert grün; Lamé h = 10, p = 3 Aufbau < 20 s.

### Aufgabe 6: Abschluss
- Theoriehandbuch 11.8 (Oktree, Zwänge, STL, Messwerte), Volumenmodul.md, CI unverändert (Kernsuite), `run_all`, `lint-imports`, mypy;
  zweite Sicht (Subagent) über Aufgaben 1–4; Zusammenfassung für Pull Request 1 (Stufe 1) mit allen Änderungen außerhalb des Pakets.
