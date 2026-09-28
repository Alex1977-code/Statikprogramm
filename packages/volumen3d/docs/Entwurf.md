# Volumenmodul `volumen3d`: Umsetzungsentwurf (Session B)

Stand 27.09.2026, Zweig `feature/volumen3d` (Worktree `Desktop/Statik3D/statik3d-volumen3d`,
abgezweigt von `main` 3267e10). Fachliche Grundlage und verbindlich:
`Schnittstellenvertrag_Statik3D_FCM.md` (2.0.0) und
`Vorgabe_Statik3D_Abschnitt_FCM-Volumenloeser.md`. Dieses Dokument legt fest, **wie** die
Vorgabe umgesetzt wird: Zerlegung in Teilprojekte, Entscheidungen mit Begründung, das erste
Teilprojekt im Einzelnen. Was die Vorgabe schon festlegt, wird hier nicht wiederholt.

Die Entscheidungen in Abschnitt 3 sind Annahmen dieser Sitzung; der Anwender kann jede davon
umstoßen. Sie sind so gewählt, dass eine Korrektur nur `packages/volumen3d` betrifft.

---

## 1. Rahmen

**Rechner (gemessen 27.09.2026):** AMD Ryzen 9 5950X (16 Kerne), 128 GB RAM, NVIDIA GeForce
RTX 3070 mit 8 GB (6,4 GB frei), Treiber 591.86, CUDA-Toolkit 12.4 mit `nvcc`. Die Vorgabe
rechnet mit 16 GB (Abschnitt 9): das lokale Ziel sind darum ~5·10⁶ Freiheitsgrade auf der GPU;
`estimate` weist den Bedarf vorher aus, größere Modelle laufen auf der CPU (128 GB).

**Umgebung des Worktrees:** eigene `.venv` (Python 3.11.9) mit `requirements.txt` des
Hauptprogramms plus `numba 0.67`, `cupy-cuda12x 14.2`, `mypy`. Baseline vor der ersten
Änderung: `tests.contracts.test_vertrag` 43/43, `mypy --strict` für das Vertragspaket sauber,
CuPy sieht die GPU (SGEMM 4000³ ×10 in 0,42 s).

**Abhängigkeiten von `volumen3d`:** `numpy`, `scipy`, `numba`, `statik3d_contracts`; `cupy`
optional (Extra `gpu`); `gmsh` optional für STEP (Teilprojekt 5). Kein `statik3d`-Import
(Vertrag Abschnitt 1), keine Qt-Abhängigkeit.

---

## 2. Zerlegung in Teilprojekte

Regeln des Anwenders (27.09.2026, Startauftrag): Umsetzung in der Reihenfolge von Vorgabe
Abschnitt 12 (Ausbaustufen) bzw. 16.10 (Baugruppen), **Stufe 1 beginnend mit Geometriekern und
Oktree**, geprüft an Patch-Test, Lochscheibe und Lamé-Zylinder; nach jeder abgeschlossenen
Stufe ein Pull Request mit grüner CI, damit die Unterschiede klein bleiben und die Oberfläche
früh gegen den echten Löser statt gegen den Stub prüfen kann. Die Stufen werden in Teilprojekte
(TP) mit eigener Abnahme aus Vorgabe Abschnitt 13 bzw. 16.9 geschnitten; jedes TP bekommt einen
eigenen Plan, und erst wenn seine Prüfungen grün sind, beginnt das nächste. Der Pull Request
kommt je **Stufe**, also nach TP 2 (Stufe 1), TP 4 (Stufe 2 Kern), TP 5, TP 6, TP 7, TP 8.

| TP | Stufe | Inhalt | Vorgabe | Abnahme |
|---|---|---|---|---|
| **1** | 1a | **FCM-Kern als CPU-Referenz:** Geometriekern mit CSG (analytische SDFs), Oktree-Datenstruktur (Morton-Codes) über einem Wurzelgitter würfelförmiger Zellen, in TP 1 noch ohne Verfeinerung; hierarchische Legendre-Basis p = 1…4, rekursive Schnittzellen-Quadratur, Nitsche für Verschiebungsränder, Flächen- und Volumenlasten, assemblierte Steifigkeit mit Direktlöser, Auswertung an der echten Oberfläche, Schnittgrößenkontrolle, Kopplung Stab → Volumen über den Provider, Paket nach Vertrag Abschnitt 1 mit Entry Points `fcm` (echt) und `hybrid` (ehrlicher Platzhalter bis TP 7) | 3–7, 8 (nur Direktlöser), 10 Stufe 1, 11.1 | Patch-Test < 10⁻⁶, Kragarm-Kopplung < 1 %, Lamé < 1 %, Kirsch < 2 %, Schnittlagen-Streuung < 1 % |
| 2 | 1b | **Oktree-Verfeinerung und STL:** Verfeinerung an Schnittzellen, Nutzerbereichen und dünnen Wänden, 2:1-Balancierung, hängende Freiheitsgrade als Zwangsbedingungen, Volumenprüfung je Schnittzelle; STL-Eingang mit BVH und verallgemeinerter Windungszahl, Oberflächendreiecke für Randintegrale und Vorschau. Damit ist Stufe 1 vollständig → **Pull Request 1**. | 3, 4, 6 | Patch-Test mit hängenden Knoten < 10⁻⁶; Kirsch lokal verfeinert bei einem Bruchteil der Freiheitsgrade; kleine Schnittzellen 10⁻⁶ ohne Ausreißer; Lamé aus STL wie aus CSG; Innen/Außen an offenen Netzen |
| 3 | 2a | **Matrixfreier Operator und PCG:** Summenfaktorisierung für INSIDE-Zellen, gespeicherte Quadratur für CUT-Zellen, Zwangsbedingungen im Operator, Jacobi-Vorkonditionierer; CPU mit numba, dann GPU mit CuPy-RawKernels | 8.1, 8.2, 9 | Operator gegen assemblierte Matrix < 10⁻¹², CPU gegen GPU < 10⁻⁶ relativ, Mehrfach-Lastfälle |
| 4 | 2b | **Mehrgitter:** p-Mehrgitter auf feinster Ebene, darunter h-Mehrgitter über die Oktree-Ebenen, Chebyshev-Jacobi-Glätter, Grobgitter direkt; kleine Schnittzellen (Zellaggregation, alternativ Ghost Penalty); gemischte Genauigkeit → **Pull Request 2** | 8.3, 9 | Iterationszahl < 100 für 10⁻⁸ unabhängig von Größe und Schnittlage; 10⁶ Freiheitsgrade < 60 s |
| 5 | 2c | **Effizienz und Nachweise:** Moment Fitting für elastische Schnittzellen, Spannungsrückgewinnung (SPR/L²), Hot-Spot entlang Nahtlinien, Konvergenzkurve, Protokoll; STEP über gmsh-Tessellierung. Schale → Volumen ist Sache des Providers (Hauptprogramm) und braucht hier nur die Prüfung. | 3, 6 (Stufe 2), 11 | Knotenblech-Referenzmodell, Vergleich mit Tet10-Referenz < 3 % |
| 6 | 3 | Punktwolke und Voxel, Fehlerschätzer mit adaptiven hp-Zyklen, Kerbspannungskonzept, Stellungs-Batch | 3, 8.4, 11.2 | Konvergenzaussage nach 2–4 Zyklen; Kerbfall-Referenz |
| 7 | 5 / 16.10 (1–3) | **Baugruppen:** Rotationsvernetzer Hex20/Hex27, J2-Plastizität mit Radial Return und konsistenter Tangente, Newton-Treiber, reibungsfreier Kontakt FE–FE (Augmented Lagrange), Lastpfad mit Checkpoints; `HybridAssemblySolver` wird echt | 16.2–16.6 | Lochscheibe elastoplastisch < 2 %, Hertz < 3 %, Bolzen im Spiel, quadratische Newton-Konvergenz |
| 8 | 5 / 16.10 (4–9) | Plastizität in FCM-Körpern, Kontakt und Tie FE–FCM, Coulomb, Mortar, iterative Löser für Baugruppen, große Verformungen | 16 | Kontakt-Patch-Test, Hybrid-Gleichheitstest, Drehlager-Vergleich |

Stufe 4 (zweiseitige Kopplung, Beulen) und Stufe 6 (Surrogate) folgen nach TP 8. Der Kern
dieser Sitzung („matrixfreies GPU-Mehrgitter“) sind TP 1–4. TP 1 ist absichtlich die
vollständige Rechenkette in langsamer, prüfbarer Form: jede spätere Stufe wird gegen sie
gemessen (Operator gegen Matrix, GPU gegen CPU), nicht gegen Erwartungen. Der bestehende
Kontakt- und Drehlagercode in `statik3d/` wird nicht geändert und dient nur als Vergleich.

---

## 3. Entscheidungen

Jede Entscheidung nennt die erwogenen Alternativen. Die Vorgabe ist technologieneutral; wo sie
eine Empfehlung ausspricht, wird ihr gefolgt, sofern nichts Gemessenes dagegen spricht.

Die drei Abweichungen von der Vorgabe – ebenen-exakte Integration statt Punkttest (3.5),
Zellaggregation schon in Stufe 1 mit α nur für Zellen ohne Wurzel (3.5) und an Schnittebenen
die Normalkomponente punktweise plus drei Mittelwertzwänge statt aller drei Komponenten (3.6) –
hat der Anwender bei der Durchsicht von Pull Request 8 am 27.09.2026 bestätigt.

### 3.1 Sprache und Aufbau
- Bezeichner, Kommentare, Docstrings im Paket auf Deutsch ohne Umlaute (CLAUDE.md). Englisch
  bleiben nur die Namen, die der Vertrag vorgibt: Unterpakete `geometry/ fcm/ hex/ material/
  contact/ nonlinear/ linalg/ postprocess/`, `api.py`, die Vertragstypen und die
  Entry-Point-Namen `fcm` und `hybrid`.
- `packages/volumen3d/` mit eigener `pyproject.toml` (setuptools, `requires-python >= 3.11`,
  Version des Pakets unabhängig von der Vertragsversion), `py.typed`, `mypy --strict` für die
  öffentliche Schicht (`api.py`, Datenklassen); Rechenkerne mit numba bleiben von mypy
  ausgenommen, wo Typen der JIT im Weg stehen.
- Einheiten im Paket durchgängig mm, N, N/mm² (Vertrag Abschnitt 2); die Umrechnung aus SI
  ist Sache des Hauptprogramms an der Grenze.

### 3.2 Rechen-Backends
- **CPU:** numpy für Aufbau und Assemblierung, `numba.njit(parallel=True)` für Zellschleifen
  (Operator, Glätter, Quadraturauswertung). **GPU:** CuPy, rechenintensive Kerne als
  `cupy.RawKernel` (CUDA C in Python-Strings, JIT über NVRTC; `nvcc` ist nicht nötig).
  Array-Code einmal schreiben, `xp = numpy | cupy` nach `FcmSettings.backend`.
- Erwogen: `numba.cuda` (weniger reif für Shared-Memory-Kerne mit Summenfaktorisierung),
  Taichi/Warp (weitere Laufzeit, keine Standardabhängigkeit im Programm), C++/CUDA über
  pybind11 (Vorgabe nennt es als spätere Leistungsstufe; erst, wenn RawKernels gemessen zu
  langsam sind).
- Genauigkeit: TP 1–3 durchgängig FP64. Gemischte Genauigkeit (Operator und Glätter FP32,
  äußeres CG FP64) kommt in TP 4 als Option mit der Abnahme „FP64-Referenz auf 10⁻⁶“.

### 3.3 Ansatzfunktionen
- Hierarchische Basis aus integrierten Legendre-Polynomen (Vorgabe Abschnitt 5), 1D:
  `N1 = (1-ξ)/2`, `N2 = (1+ξ)/2`, `N_{j+1} = φ_j(ξ) = (P_j - P_{j-2}) / sqrt(2 (2j-1))` für
  j = 2…p; 3D als volles Tensorprodukt, (p+1)³ Moden je Zelle, drei Verschiebungen je Mode
  (Nummerierung `3·mode + Komponente`).
- **Volles Tensorprodukt statt Trunk-Raum:** einfacher, und die Summenfaktorisierung (TP 3)
  arbeitet auf der vollen Tensorstruktur; der Trunk-Raum spart bei p = 4 rund 30 % Moden und
  kann später als Option kommen (Maske über die Moden, keine Strukturänderung).
- Erwogen: Lagrange-Basis auf Gauß-Lobatto-Punkten (spektrale Elemente). Gleich gut für
  Summenfaktorisierung, aber p-Mehrgitter und p-Adaptivität brauchen dann Interpolations-
  matrizen statt einfachen Abschneidens; die Vorgabe empfiehlt die hierarchische Basis.
- Moden werden nach Trägerentität sortiert: 8 Ecken, 12·(p−1) Kanten, 6·(p−1)² Flächen,
  (p−1)³ Inneres. Da alle Zellen achsparallel sind und Kanten/Flächen kanonisch in
  +Achsrichtung orientiert werden, entfallen Vorzeichenwechsel zwischen Nachbarzellen.
- p ist in TP 1 modellweit einheitlich; die Datenstruktur führt p je Zelle (Vorgabe 4).

### 3.4 Gitter
- **Wurzelgitter aus würfelförmigen Zellen** der Kantenlänge `base_cell_size_mm` über dem
  Hüllquader der Geometrie (n_x × n_y × n_z Wurzelzellen, Hüllquader um ein Zehntel Zelle
  gepolstert, damit die Oberfläche nie genau auf Zellgrenzen liegt); unter jeder Wurzelzelle
  ein linearer Oktree mit Morton-Codes. In TP 1 haben alle Blätter die Ebene 0.
- Erwogen: ein einziger Oktree über einem Würfel um die Geometrie. Bei plattenförmigen
  Bauteilen (Kirsch: 800 × 400 × 10 mm) verschwendet er Ebenen; das Wurzelgitter trifft die
  Zellgröße direkt.
- Zellklassifikation über die SDF: `|d(Mitte)| > halbe Raumdiagonale·(1+10⁻⁹)` entscheidet
  INSIDE/OUTSIDE sicher, sonst CUT (konservativ; eine fälschlich als CUT geführte Zelle kostet
  nur Quadraturpunkte, nie Genauigkeit).
- Freiheitsgrade hängen an Entitäten (Ecke, Kante, Fläche, Zelle), identifiziert über
  verdoppelte Ganzzahlkoordinaten im feinsten Gitter plus Ebene; diese Schlüssel überleben
  die Verfeinerung in TP 2. Nur Entitäten von INSIDE- und CUT-Zellen tragen Freiheitsgrade.

### 3.5 Integration
- INSIDE: Gauß-Legendre (p+1)³. CUT: rekursive Oktant-Teilung der Zelle; Teilzellen, die
  die SDF sicher als innen/außen ausweist, werden nicht weiter geteilt.
- **Ebenen-exakte Blätter statt Punkttest** (Entscheidung 27.09. nach Messung: der reine
  Punkttest der Vorgabe ist erster Ordnung – Würfel 100³, schräg durch eine Ebene halbiert,
  h = 20, Tiefe 4, 6,5·10⁶ Punkte: Volumenfehler 0,5 %; damit ist der Patch-Test < 10⁻⁶ der
  Vorgabe Abschnitt 13 unerreichbar). In einer geschnittenen Teilzelle nennen die aktiven
  Grundformen (|d| ≤ halbe Raumdiagonale) ihre **lokalen Ebenen**: Halbraum und Quaderseiten
  exakt, Zylinder und Kugel als Tangentialebene im Teilzellenmittelpunkt. Der CSG-Baum prüft
  an den Gauß-Punkten der Teilzelle, ob sich der Gesamtabstand lokal als „Schnitt der
  positiven Formen minus Löcher“ (max) oder als Vereinigung (min) rekonstruieren lässt, und
  zerlegt die Teilzelle dann in **disjunkte konvexe Stücke** (Box ∩ Halbräume; Löcher über die
  Standardzerlegung des Komplements). Jedes Stück wird gegen seine Halbräume geclippt
  (Sutherland–Hodgman auf den Polyederflächen samt Deckelpolygon), vom Schwerpunkt aus in
  Tetraeder zerlegt und mit der konischen Produktregel (Gauß–Jacobi, n = ⌈3p/2⌉ je Richtung,
  exakt bis Gesamtgrad 2n−1 ≥ 3p−1) integriert – genau die Exaktheit, die der Patch-Test für
  ∫∇v braucht. Ebene Geometrie ist damit auf jeder Tiefe exakt (keine Teilung nötig);
  gekrümmte Flächen werden bis Tiefe k (Standard 2) geteilt, Fehler O(κ·Blattkante²) statt
  O(Blattkante). Gemessen am Lamé-Zylinder (h = 10, R = 50): Tiefe 2 begrenzt σ_r auf etwa
  0,3 % unabhängig von p ≥ 3, Tiefe 3 bringt 0,09 % (p = 3) bei vierfacher Punktzahl – die
  Oktree-Verfeinerung an gekrümmten Flächen (TP 2) ist der wirtschaftlichere Weg. Der **fiktive Bereich** kommt ohne negative Gewichte aus: die ganze Teilbox
  mit Gauß (p+1)³ und Gewicht α, die Stücke mit Gewicht (1−α).
- Lässt sich die lokale Semantik nicht rekonstruieren (verschachtelte Booleans, mehrere
  gekrümmte Formen), teilt die Rekursion zwei Stufen tiefer und fällt auf den Punkttest der
  Vorgabe zurück; die Zahl solcher Blätter steht im Protokoll.
- Punkte und Gewichte der CUT-Zellen werden einmal berechnet und gehalten (für alle
  Lastfälle gleich); Basiswerte nicht (Speicher).
- **Zellaggregation schon in TP 1** (Vorgabe 8.3, Gegenmaßnahme 1; Befund 27.09.: im
  Patch-Test-Gitter haben 10 von 118 Zellen einen Werkstoffanteil unter 10⁻⁴, drei sogar 0;
  der Fehler wuchs mit α/Anteil auf 1,4 % bei α = 10⁻⁸). Zellen mit Anteil unter der Schwelle
  (Standard 0,25) bekommen eine wohlgestellte Wurzelzelle (Nachbar mit größtem Anteil, Fläche
  vor Kante vor Ecke, Ketten aufgelöst); Moden, die keine wohlgestellte Zelle trägt, werden an
  die Fortsetzung des Wurzelpolynoms gebunden (Modalprojektion, `M = V_c⁻¹ V_R`, lineare
  Felder exakt). Zwangsmatrix C, gelöst wird CᵀKC. Prinzip der aggregierten finiten Elemente
  (Badia, Verdugo, Martín 2018).
- **α nur noch als Rückfall:** Gebundene Zellen dürfen keine α-Punkte tragen (α wirkt sonst auf
  die extrapolierten Wurzelmoden, Fortsetzung wächst wie (2ξ)ᵖ: gemessen 2·10⁻⁵ statt 3·10⁻⁸),
  und in wohlgestellten Zellen tragen hohe Moden nur ~Anteil^(2p+1) ihrer Energie im
  Werkstoff (0,28⁷ ≈ 10⁻⁴ bei p = 3), sodass α = 10⁻⁸ dort 10⁻⁴ Fehler macht. Mit Aggregation
  bekommen darum nur Zellen **ohne Wurzel** (isolierte Splitter) den Faktor α; alle anderen
  Schnittzellen werden ohne fiktives Gebiet integriert. Ergebnis: Patch-Test 5·10⁻¹⁵ … 5·10⁻⁹
  (p = 1…3) unabhängig von α und β. α bleibt Nutzerparameter (Vertrag `FcmSettings.alpha`) für
  Aggregation aus und den Rückfall.
- Qualitätsprüfung (Vorgabe 6) kommt mit TP 2; in TP 1 misst ein Test das integrierte
  Volumen von Kugel, schräg geschnittenem Würfel und Lochplatte gegen die Formel.

### 3.6 Randbedingungen und Lasten
- Verschiebungsränder (Schnittebenen, Lager, Symmetrie) über **symmetrisches Nitsche** mit
  Projektionsmatrix P (voll oder nur Normalenrichtung, damit Symmetrie und Gleitlager denselben
  Code nutzen): Steifigkeit `- ∫ (σ(u)n)·Pv - ∫ (σ(v)n)·Pu + β ∫ Pu·Pv`, rechte Seite
  entsprechend mit der Vorgabe g. β = C·E·p²/h je Zelle, C = 10 als Startwert; der Wert steht
  im Protokoll. Ein zellweises Eigenwertproblem für β kommt, wenn kleine Schnittanteile in
  TP 2 Stabilitätsprobleme zeigen (dann gemessen, nicht vorab).
- Erwogen: Penalty (einfacher, aber β-abhängig und inkonsistent; nur als Rückfall vorgesehen),
  Lagrange-Multiplikatoren für den ganzen Rand (Sattelpunkt, passt nicht zu CG und Mehrgitter).
- **Schnittebenen zum Stabwerk (Befund 27.09.):** Die ebene Querschnittskinematik eines Stabs
  enthält keine Querkontraktion und keine Schubverwölbung. Mit allen drei Komponenten
  punktweise vorgegeben ist die Schnittebene seitlich gesperrt: am Stub-Kragarm (Segment 3 h)
  war das Moment um 45–53 % zu hoch. Darum gilt an Schnittebenen die Projektion `schnitt`:
  Normalkomponente punktweise über Nitsche (trägt Biegung, Längskraft, Verwölbung), in der
  Ebene nur die drei Resultierenden – zwei Translationen (Querkräfte) und die Drehung um die
  Normale (Torsion) – als Mittelwertzwänge mit **drei Lagrange-Multiplikatoren je Ebene**
  (Sattelpunkt mit nur 3 Zusatzunbekannten je Ebene, für den Direktlöser unkritisch; TP 3
  eliminiert sie per Projektion). Die Multiplikatoren sind die übertragenen Traktionen
  (λ·A = Querkraft) und dienen als Kontrolle. Reine Biegung (exaktes 3D-Feld) bleibt exakt
  (10⁻⁶), Multiplikatoren 10⁻¹⁴.
- **Grenze der Verschiebungskopplung:** Für ein schubweiches Segment mit vorgegebenen
  Euler-Bernoulli-Endverdrehungen folgen andere Schnittgrößen als aus der Balkentheorie
  (Φ = 12EI/(κGAl²), am Stub-Kragarm mit l = 3h: Φ = 0,35, Moment +37 %, Querkraft −24 %).
  Die FCM trifft die unabhängige Timoshenko-Vorhersage auf −0,9 % (Moment) und +2,7 %
  (Querkraft, κ = 5/6). Die Kopplungskontrolle im Ergebnis weist solche Abweichungen aus;
  Empfehlung im Handbuch: Schnittebenen mindestens 4–5 Querschnittshöhen auseinander oder
  schubweiches Globalmodell, sonst Kraftkopplung (TP 5).
- Flächenlasten (Druck, Traktion) und Volumenlasten über Oberflächen- bzw. Volumenquadratur.
- **Oberflächenquadratur:** jede CSG-Grundform liefert eine Tessellierung ihrer Oberfläche
  (Ebenen exakt als Polygone, Zylinder/Kugel parametrisch mit wählbarer Auflösung); Dreiecke
  werden gegen die Zellbox geclippt, mit Gauß-Punkten für Grad 2p belegt, und jeder Punkt
  bleibt nur, wenn er auf der Oberfläche der **Gesamtgeometrie** liegt (`|d| ≤ tol`), damit
  Differenz und Schnitt stimmen (Bohrung nur innerhalb der Platte). Die Normale kommt exakt
  aus dem SDF-Gradienten, nicht aus dem Dreieck; die Tessellierung trägt nur Fläche und Lage
  (Fehler zweiter Ordnung in der Facettenweite, für Lamé mit 1 % Ziel: 360 Segmente ergeben
  10⁻⁵).

### 3.7 Geometrie (TP 1)
- Nur CSG aus analytischen SDFs: Quader, Zylinder (endlich, beliebige Achse), Kugel,
  Halbraum; Operationen Vereinigung (min), Differenz (max(a, −b)), Schnitt (max). Damit sind
  alle Verifikationsmodelle der Vorgabe Abschnitt 13 beschreibbar. STL/STEP folgen in TP 5
  hinter derselben Schnittstelle `GeometrieAbfrage` (`innen(P)`, `abstand(P)`,
  `huellquader()`, `oberflaeche(box)`), alle Aufrufe vektorisiert über Punktlisten (n,3).
- **Schema für `GeometrySource(type=CSG, params=...)`** (JSON-fähig, mm):
  ```
  params = {"csg": KNOTEN}
  KNOTEN = {"typ": "quader",   "min": [x,y,z], "max": [x,y,z]}
         | {"typ": "zylinder", "p0": [x,y,z], "p1": [x,y,z], "radius": r}
         | {"typ": "kugel",    "mitte": [x,y,z], "radius": r}
         | {"typ": "halbraum", "punkt": [x,y,z], "normale": [x,y,z]}   # Werkstoff gegen die Normale
         | {"typ": "vereinigung" | "differenz" | "schnitt", "teile": [KNOTEN, ...]}
  ```
  Benannte Flächen (`"name": "bohrung"` an einer Grundform) bereiten `SurfaceSelector.named_surface`
  (Vertrag 6a) vor.

### 3.8 Löser (TP 1)
- Assemblierte Steifigkeit als `scipy.sparse.csr`, Direktlöser `pypardiso` wenn vorhanden,
  sonst `scipy.sparse.linalg.splu`; mehrere rechte Seiten in einem Lauf (Vertrag: `solve`
  für alle Keys mit einer Diskretisierung). Das bleibt auch später der Referenz- und
  Grobgitterlöser.

### 3.9 Ergebnisse (TP 1)
- Verschiebung und Spannung werden direkt aus der Lösung an beliebigen Punkten ausgewertet
  (Zelle finden, lokale Koordinaten, Basis und Gradienten, σ = D B u); Auswertepunkte sind die
  Ecken der Oberflächentriangulierung (Vorschau und `DetailResult.surface_points`). Bei p ≥ 3
  reicht das für die Abnahmen; Rückgewinnung (SPR/L²) kommt in TP 6.
- Schnittgrößenkontrolle: Integration von σ·n über die Schnittebenen-Quadratur, Vergleich mit
  `GlobalFieldProvider.section_forces` → `DetailResult.coupling_check`.
- Die Oberflächentriangulierung aus den Grundformen ist an CSG-Schnittkurven nicht wasserdicht;
  für Vorschau und Punktauswertung reicht das, Marching Cubes auf der SDF (wasserdicht) kommt
  in TP 5.

### 3.10 Prüfungen und CI
- Suiten unter `packages/volumen3d/volumen3d/tests/` im Stil des Hauptprogramms (`check`, Aufruf
  `python -m volumen3d.tests.test_...`), eine schnelle Sammelsuite `volumen3d.tests.test_kern`
  wird in `tests/run_all.py` eingetragen; die teuren Konvergenz- und Leistungsläufe stehen in
  eigenen Suiten mit Laufzeitangabe im Kopf und laufen vor jedem Merge.
- `.github/workflows/ci.yml` bekommt einen Schritt „volumen3d (CPU)“: Paket installieren,
  mypy für die öffentliche Schicht, Kernsuite. GPU-Prüfungen laufen nur lokal (kein GPU-Runner).
- **Abhängigkeitsregeln per `import-linter`** (Regel des Anwenders, Vertrag Abschnitt 1):
  `.importlinter` an der Repository-Wurzel mit den Verboten `volumen3d → statik3d`,
  `statik3d_contracts → volumen3d | statik3d` und `statik3d → volumen3d` (das Hauptprogramm
  kennt den Löser nur über Entry Points); `lint-imports` läuft in der CI und lokal vor jedem
  Commit.
- **Pull Request je abgeschlossener Stufe** mit grüner CI; kein Merge ohne die Abnahmen aus
  Abschnitt 2, gemessen und mit Zahlen im PR-Text.
- Referenzmodelle `tests/reference_models/` (Vertrag Abschnitt 8) legt Session B **nicht allein**
  an; die Erwartungswerte der TP-1-Abnahmen werden in den Suiten mit Quelle dokumentiert und
  später gemeinsam dorthin übernommen.

### 3.11 Zielhardware
- Lokal 8 GB GPU: `estimate` rechnet Speicher aus Freiheitsgraden, CUT-Quadratur und
  Mehrgitter-Ebenen und meldet, ob das Modell auf die vorhandene GPU passt; sonst CPU-Rückfall
  mit identischem Ergebnis (Vorgabe 9).

---

## 4. Teilprojekt 1 im Einzelnen

### 4.1 Module

```
packages/volumen3d/
├── CLAUDE.md                      Regeln der Sitzung (Anwender, 27.09.2026)
├── pyproject.toml                 Entry Points: statik3d.solid_solvers → fcm = volumen3d.api:FcmSolver,
│                                  statik3d.assembly_solvers → hybrid = volumen3d.api:HybridAssemblySolver
└── volumen3d/
    ├── __init__.py                Paketversion, CONTRACT_VERSION-Prüfung beim Import
    ├── api.py                     FcmSolver (SolidDetailSolver), FcmDiskretisierung (Discretization),
    │                              HybridAssemblySolver (bis TP 7 Platzhalter: capabilities leer,
    │                              estimate nennt „nicht umgesetzt“, prepare wirft SolverError)
    ├── geometry/
    │   ├── sdf.py                 Grundformen (Quader, Zylinder, Kugel, Halbraum): abstand, gradient, huellquader,
    │   │                          lokale Ebenen, Flächenfaktor Bogen/Sehne, Tessellierung
    │   ├── csg.py                 CSG-Baum, Auswertung aus params, innen/abstand/gradient, lokale konvexe Stücke
    │   ├── polyeder.py            Box gegen Halbräume clippen, Tetraeder, konische Gauß-Jacobi-Regel
    │   └── oberflaeche.py         Clipping an Zellboxen, Stücke der Gesamtoberfläche, Flächenquadratur
    ├── fcm/
    │   ├── basis.py               1D integrierte Legendre, 3D-Tensorprodukt, Modenklassen, Gauß-Regeln
    │   ├── gitter.py              Wurzelgitter + Oktree (Ebene 0 in TP 1), Klassifikation, Entitäten, Freiheitsgrade
    │   ├── quadratur.py           INSIDE-Regel, ebenen-exakte CUT-Quadratur, Punkttest als Rückfall, Volumenkontrolle
    │   ├── aggregation.py         Zellaggregation kleiner Schnittzellen (Zwangsmatrix C)
    │   ├── elastizitaet.py        D-Matrix, B-Matrizen, Zellsteifigkeit (BLAS), Assemblierung (CPU-Referenz)
    │   ├── rand.py                Nitsche (voll / normal / schnitt), Mittelwertzwänge, Traktion, Druck, Volumenlast
    │   └── problem.py             FcmProblem: Geometrie + Gitter + Werkstoff + Ränder + Lasten → K, F → Loesung
    ├── linalg/
    │   └── direkt.py              pypardiso/splu mit Mehrfach-RHS
    └── postprocess/
        └── auswertung.py          Punktsuche, u/σ/von Mises an Punkten, Schnittgrößen
```

### 4.2 Datenfluss `FcmSolver`
1. `estimate(spec)`: Hüllquader aus CSG → Wurzelgitter → Zellzahl, geschätzter Anteil
   CUT-Zellen (Oberfläche/Volumen), Freiheitsgrade ≈ 3·(n_x·p+1)(n_y·p+1)(n_z·p+1), Speicher
   für Matrix (Bandbreite) und CUT-Quadratur; Backend „cpu“ (TP 1 kennt kein anderes).
2. `prepare(spec, material, progress)`: CSG bauen → Gitter klassifizieren → Freiheitsgrade
   nummerieren → Quadratur der CUT-Zellen → Oberflächenquadratur der Schnittebenen (Nitsche)
   und der Geometrieoberfläche → K assemblieren und faktorisieren → `FcmDiskretisierung`
   (hält das Problem; `summary`: Zellen je Klasse, p, Freiheitsgrade, CUT-Quadraturpunkte,
   Speicher; `preview_geometry`: Oberflächendreiecke und Zellboxen mit Klasse).
3. `solve(disc, provider, keys, progress, cancel)`: je Key `provider.displacement_at` an den
   Nitsche-Quadraturpunkten der Schnittebenen (NaN → `SolverError` mit Ortsangabe) → rechte
   Seiten → ein Lösungslauf für alle Keys → je Key `DetailResult` (u, σ, von Mises an den
   Oberflächenecken, `coupling_check` mit Schnittgrößenvergleich je Ebene, `protocol` mit allen
   Einstellungen, β, α, k, Zellzahlen, Löser, Laufzeiten). `cancel()` wird zwischen den Stufen
   geprüft und löst `SolverCancelled` aus.

### 4.3 Fehlerbehandlung
- `SolverError` bei: leerer Geometrie (keine INSIDE/CUT-Zelle), unbekanntem CSG-Typ, p außerhalb
  1…4, `base_cell_size_mm ≤ 0`, Provider liefert NaN auf einer Schnittebene, singulärer Matrix
  (Starrkörper ohne Verschiebungsrand: Meldung nennt die freie Bewegung, wie das Hauptprogramm
  in Theoriehandbuch 7b).
- Warnungen in `DetailResult.warnings`: Schnittebene näher als eine Querschnittshöhe an einer
  Verfeinerungsstelle (Saint-Venant, Vorgabe 10), weniger als zwei Zellen über eine Wandstärke
  (gemessen entlang der Zellachsen an CUT-Zellen), Schnittgrößenabweichung über 5 %.

### 4.4 Prüfungen (Reihenfolge = Umsetzungsreihenfolge)
| Nr. | Suite | Prüfung | Kriterium |
|---|---|---|---|
| T1 | `test_basis` | 1D: `∫φ'_i φ'_j = δ_ij`, Eckmoden bilden Partition der Eins, Ableitungen gegen zentrale Differenzen; 3D: Modenanzahl je Klasse, Gauß (p+1) integriert Grad 2p+1 exakt | 10⁻¹² |
| T2 | `test_geometrie` | SDF-Werte und Gradienten der Grundformen, CSG-Kombinationen, Oberflächenquadratur summiert zur Mantelfläche | 10⁻¹⁰ (Ebenen), 10⁻⁵ (Zylinder 360 Segmente) |
| T3 | `test_quadratur` | Volumen von Kugel und schräg geschnittenem Quader je Tiefe k; α-Anteil ausgewiesen | Fehler fällt mit k, k = 4 unter 10⁻⁴ |
| T4 | `test_patch` | Quader, schräg durch zwei Halbräume geschnitten (viele CUT-Zellen), lineares Verschiebungsfeld über Nitsche auf dem ganzen Rand; p = 1…3 | u und σ < 10⁻⁶ relativ |
| T5 | `test_kragarm` | Ausschnitt des Stub-Kragarms (Balkentheorie) zwischen zwei Schnittebenen, Verschiebungen aus `StubGlobalFieldProvider` über Nitsche; Schnittgrößen gegen `section_forces` | < 1 % |
| T6 | `test_lame` | Viertel eines dickwandigen Zylinders unter Innendruck, Symmetrie über Nitsche-Normalprojektion, Druck über Oberflächenquadratur | σ_r, σ_φ < 1 % |
| T7 | `test_kirsch` | Dünne Platte mit Loch, d/W = 0,1, Zug über Traktion; Vergleich mit Howland (K_tg = 3,03) | < 2 % |
| T8 | `test_schnittlage` | Kirsch-Modell, Wurzelgitter um 0,1…0,9 Zellen verschoben | Streuung < 1 % |
| T9 | `test_vertrag_fcm` | `FcmSolver` erfüllt `SolidDetailSolver`, Entry Point `fcm` registriert, `estimate/prepare/solve` mit Stub-Provider, Abbruch, Protokoll; `mypy --strict` für `api.py` | wie `test_vertrag` |

T1–T3 sichern die Bausteine, T4 die gesamte Kette (B, D, α, Nitsche) mit exakter Lösung, T5–T8
die Abnahmen der Vorgabe.

**Gemessen am 27.09.2026** (Ryzen 9 5950X, pypardiso, parallel zu einem Drehlager-Lauf der
Hauptsitzung; Einzelheiten in Theoriehandbuch Kapitel 11):

| Nr. | Ergebnis |
|---|---|
| T1 | 21/21 (Orthonormalität 10⁻¹², Ableitungen 10⁻⁸) |
| T2 | 45/45; Bohrungsmantel und Kugeloberfläche 10⁻⁸, Sechseck der Schnittebene und Würfelseiten < 10⁻¹⁰ |
| T3 | 32/32; ebene Geometrie exakt auf jeder Tiefe, Kugel zweite Ordnung (1,4·10⁻² → 2,1·10⁻⁴ für Tiefe 0…3) |
| T4 | 14/14; p = 1/2/3: u 5·10⁻¹⁵ / 8·10⁻¹⁴ / 5·10⁻¹², σ 8·10⁻¹³ / 5·10⁻¹¹ / 5·10⁻⁹; Schnittanteil 10⁻⁶: 4·10⁻¹¹; unabhängig von α und β |
| T5 | 13/13; reine Biegung exakt (Moment 10⁻⁶, Multiplikatoren 10⁻¹⁴); Stub-Kragarm gegen Timoshenko −0,9 % (M) / +2,7 % (Q), gegen den schubstarren Stub +37 % / −24 % (Kinematik, nicht Rechnung) |
| T6 | h = 10: p = 2 σ_r 1,41 % / σ_φ 0,95 % (36 s), p = 3 0,32 % / 0,03 % (50 s), p = 4 0,28 % / 0,09 % (149 s; Geometriegrenze der Tangentialebenen); Rotationssymmetrie bei 12° und 71° < 0,25 % |
| T7 | p = 4, h = 10, 379 k FHG (195 k frei), 52 s: K_tg Mitte 3,069 gegen 3,028 (+1,35 %, davon etwa +1 % 3D-Effekt bei t/d = 0,25), Oberfläche 2,981 |
| T9 | 25/25; `volumenloeser()` des Hauptprogramms wählt `fcm`, Vertragsprüfung 43/43 |

| T8 | **< 1 % nicht erfüllt** mit dem gleichmäßigen Gitter bei h = r/2: K_tg 3,01…3,26 über fünf Lagen (7,9 %); Ursache Auflösung des Lochs (|σ_r| am freien Rand bis 0,15 σ₀), nicht die Aggregation (Schwellenstudie 0,25/0,10/0,02: 7,7/5,6/18,5 %). Bei h = r/4 (p = 3): 1,42 %, etwa quadratische Konvergenz; die Suite prüft diese Konvergenz, die Abnahme < 1 % kommt mit der Verfeinerung an Bohrungen (TP 2) |

Zweite Sicht (Gutachten 27.09., Subagent): elf Befunde, davon drei schwere (Vorschau-Dreiecke im
Leerraum mit nacktem `ValueError` bei schrägen Schnittebenen, fehlende Singularitätsprüfung,
Kopplungskennzahl bei Nullwerten des Globalmodells) und zwei mittlere (berührende Vereinigung
zählt die innere Seite als Oberfläche, Krümmungsradius kleiner als das Blatt) – alle behoben und
mit Prüfungen belegt (`test_vertrag_fcm.test_gutachten_faelle`, `test_geometrie`,
`test_quadratur.test_kleine_radien`); dazu α-Gewichte vereinheitlicht, Gittertest am echten
Grenzfall, INSIDE-Zellmatrix nur einmal berechnet. Offen (Leistung, TP 2/3): Geometriekern und
Modennummerierung vektorisieren, Tetraederzahl je Stück senken. Erwartungswerte werden mit Quelle und Formel in der Suite genannt
(Lamé geschlossen, Howland/Heywood für Kirsch mit Angabe beider Formeln; zweite unabhängige
Berechnung des Erwartungswerts im Test selbst, siehe Gedächtnisregel „Zahlen erst nach
Gegenprobe“).

### 4.5 Nicht-Ziele von TP 1
Verfeinerung und hängende Knoten (TP 2), matrixfreier Operator und GPU (TP 3/4), STL/STEP
(TP 5), Rückgewinnung, Hot-Spot und Adaptivität (TP 6), alles aus Vorgabe Abschnitt 16.

---

## 5. Änderungen außerhalb `packages/volumen3d`

Der Vertrag beschränkt Session B auf `packages/volumen3d/`. Folgende Stellen außerhalb sind
für TP 1 nötig; sie werden im Pull Request einzeln benannt:

- `tests/contracts/test_vertrag.py`: die Prüfung „`volumenloeser()` liefert den Stub“ gilt nur
  ohne echten Löser; mit installiertem `volumen3d` muss sie `fcm` erwarten. Änderung:
  Erwartung aus den registrierten Entry Points ableiten (kein Eingriff ins Vertragspaket).
- `tests/run_all.py`: Eintrag `volumen3d.tests.test_kern`.
- `.github/workflows/ci.yml`: Schritt für `volumen3d` (CPU).
- `requirements.txt`: `./packages/volumen3d` und `numba`; `cupy-cuda12x` nur als Kommentar
  (GPU-Extra), damit die exe und Linux-Umgebungen ohne CUDA unverändert laufen.
- `docs/Volumenmodul.md`: Abschnitt „Session B“ mit Stand; `docs/Theoriehandbuch.md`: neues
  Kapitel „11 Finite-Cell-Methode“ mit Formeln und Messwerten der Abnahmen.
- `.importlinter` (Wurzel) und der CI-Schritt `lint-imports` (Regel des Anwenders, siehe 3.10).
- `docs/vertrag-aenderungen/`: Vorschläge für Vertragsänderungen (Regel des Anwenders, siehe
  Abschnitt 6). Die Sitzung ändert den Vertrag nie selbst; der Anwender entscheidet und bringt
  die Änderung als eigenen Pull Request auf `main`, beide Sitzungen holen sie per Rebase ab.
  Der angekündigte Stand 2.0.1 lag am 27.09. noch nicht auf `main` (dort 2.0.0); gebaut wird
  gegen 2.0.0, die Major-Nummer passt.

Innerhalb des Pakets verankert `packages/volumen3d/CLAUDE.md` die Regeln des Anwenders (nur in
diesem Paket arbeiten; Vertragspaket, Referenzmodelle und `statik3d/` nur lesen; Vertrag und
Vorgabe verbindlich; Reihenfolge nach Abschnitt 12 bzw. 16.10; Einheiten N, mm, N/mm² an allen
Schnittstellen; Vorschläge statt Vertragsänderungen; Pull Request je Stufe).

Nicht angefasst: `packages/statik3d_contracts/`, `tests/reference_models/`, `statik3d/`.

---

## 6. Offene Fragen an den Anwender (mit gewählter Vorgabe)

1. **Lasten im Detailmodell:** `DetailModelSpec` kennt keine Flächen- oder Volumenlasten
   (Wasserdruck, Eigengewicht im Ausschnitt). TP 1 rechnet sie über die interne Schnittstelle;
   für die Oberfläche bräuchte der Vertrag ein optionales Feld `loads` (Minor 2.1.0).
   *Vorgehen:* Vorschlag in `docs/vertrag-aenderungen/2026-09-27-lasten-im-detailmodell.md`
   mit TP 1; der Anwender entscheidet.
2. **Trunk-Raum** statt vollem Tensorprodukt: erst nach Messung der Rechenzeit in TP 3.
3. **GPU-Speicher 8 GB:** Zielgröße lokal 5·10⁶ Freiheitsgrade; für die 10⁷ der Vorgabe wäre
   eine 16-GB-Karte nötig oder Out-of-Core (nicht geplant).
4. **Speicherort der Referenzmodelle:** gemeinsam mit Session A festlegen, sobald TP 1 steht.


---

## 4b. Teilprojekt 2 im Einzelnen (Stufe 1b, begonnen 27.09.2026)

Ziel: Stufe 1 der Vorgabe vollständig – Verfeinerung an Schnittzellen, Nutzerbereichen und
dünnen Wänden mit hängenden Freiheitsgraden, STL-Eingang, Geometriekern schneller – und damit
Pull Request 1. Die Abnahmen: Patch-Test mit hängenden Knoten < 10⁻⁶, Kirsch mit lokal
verfeinertem Loch (Schnittlagen-Streuung < 1 % bei einem Bruchteil der Freiheitsgrade des
gleichmäßigen Gitters), Lamé aus STL wie aus CSG, Innen/Außen-Test an einem Netz mit Lücke.

### 4b.1 Oktree (`fcm/gitter.py`)

- **Blätter statt Wurzelzellen:** jede aktive Zelle trägt `ebene` ℓ und `ijk` auf ihrer Ebene,
  Kantenlänge h_ℓ = h/2^ℓ, Box aus `ursprung + ijk·h_ℓ`. Aufbau: Wurzelgitter klassifizieren →
  Verfeinerungsregeln anwenden, bis keine Zelle mehr teilt → 2:1-Balancierung über alle 26
  Nachbarn (Ecken eingeschlossen, damit jede hängende Entität genau eine Ebene gröber ist) →
  OUTSIDE-Blätter verwerfen. Regeln (`Verfeinerung`): `schnitt_ebenen` (CUT-Zellen bis zu dieser
  Ebene teilen), `bereiche` (`RefinementRegion` des Vertrags: Kugel um `center` mit
  `target_cell_size_mm` → Ebene), `duenne_waende` (Werkstoffstrecke durch die Zellmitte längs
  einer Achse kürzer als zwei Zellkanten → teilen; Vorgabe Abschnitt 4).
- **Punktsuche vektorisiert:** je Ebene ein sortiertes Feld flacher Indizes; für Punkte werden die
  Indizes aller Ebenen berechnet und von grob nach fein per `searchsorted` gesucht – der erste
  Treffer ist das Blatt. Zellen-in-Box-Abfrage über die Blattlisten der Wurzelzellen (für die
  Flächenquadratur).
- **Entitätsschlüssel:** Ecken ebenenfrei über ihre Lage im feinsten verdoppelten Gitter (eine
  Ecke einer feinen Zelle, die auf einer groben Ecke liegt, ist dieselbe Ecke); Kanten, Flächen
  und Zellinneres mit Ebene (verschiedene Ebenen haben verschiedene Längen). Gleiche Ebene →
  geteilte Nummern wie bisher, ohne Vorzeichenwechsel.
- **Zellgrößen überall:** `zell_gradienten` (2/h_c), Nitsche-β (C·E·p²/h_c), INSIDE-Zellmatrix
  je Ebene (K ∝ h, also einmal berechnen und mit 2^(−ℓ) skalieren), Werkstoffanteil (h_c³),
  Aggregations-Nachbarn per Punktsuche statt Indexrechnung.

### 4b.2 Hängende Freiheitsgrade und ein Zwangsauflöser (`fcm/zwaenge.py`)

- Eine Entität einer feinen Zelle F ist **hängend**, wenn die Punktsuche knapp außerhalb (Fläche:
  Mitte + ε·n; Kante: Mitte diagonal nach außen; Ecke: die acht Oktantrichtungen) eine gröbere
  Zelle C findet. Dann gilt Stetigkeit: die Spur von F auf der Entität ist die Spur von C.
- **Spur ganz auf einmal:** für eine hängende Fläche werden alle (p+1)² Moden von F, die auf ihr
  nicht verschwinden (4 Ecken, 4 Kanten, Flächeninneres; nach der Basis sind das die Moden mit
  Index 0 bzw. 1 in der Normalenrichtung), aus den Moden von C ausgedrückt:
  `M = V_F⁻¹ · N_C(Punkte)` mit (p+1)² Tensor-Chebyshev-Lobatto-Punkten auf der Fläche, V_F die
  2D-Modalvandermonde von F, N_C die Basis von C an denselben Punkten in C's Referenzkoordinaten
  (der Spurraum ist beidseits der Tensorraum vom Grad p, die Abbildung exakt). Kanten ebenso
  eindimensional (p+1 Punkte), Ecken als Auswertung der Basis von C am Punkt.
- **Vorrang:** Flächen vor Kanten vor Ecken – ein Mode, den eine hängende Fläche schon bindet,
  wird von einer Kante nicht noch einmal definiert (beide Definitionen stimmen überein, weil die
  beiden groben Nachbarn die gemeinsame Kante teilen). Danach die **Zellaggregation** nur noch für
  Moden, die noch frei sind: so bleibt die Stetigkeit über hängende Flächen auch bei schlecht
  geschnittenen feinen Zellen erhalten, und lineare Felder bleiben exakt (beide Vorschriften
  reproduzieren sie). Ketten (Meister selbst gebunden) werden durch Einsetzen aufgelöst.
- **Selbstbezüge gibt es nicht mehr (28.09.2026).** Im verfeinerten Patch-Test (`test_zwaenge`,
  dünne Wand) traten 53 Selbstbezüge mit Koeffizient 1 und Rest bis 2,45 auf; die Diagnose
  zeigte zwei Ursachen. Erstens bekamen 21 schlecht geschnittene grobe Zellen eine *feinere*
  Wurzel, weil alle wohlgestellten Nachbarn feiner waren; deren Moden hingen ihrerseits an der
  groben Zelle. Zweitens wurde ein Eckmode, den eine grobe und eine feine schlechte Zelle
  teilen, über die Wurzel der feinen Zelle gebunden, deren hängende Ecken wiederum an der groben
  Zelle hingen (Mode 582 → 6605 → 582). Regeln seither: eine Wurzel ist nie feiner als ihre
  Zelle (auch im zweiten Durchgang über die Wurzeln der Nachbarn nicht); der Eigentümer eines
  geteilten Modes ist die gröbste schlechte Zelle; findet eine Zelle so keine Wurzel, obwohl sie
  feinere wohlgestellte Nachbarn hat, meldet sie `zu_teilen`, `FcmProblem` teilt sie
  (`Verfeinerung.zellen`) und baut Gitter, Quadratur und Aggregation neu (bis zu vier Runden,
  Protokoll `wurzel_teilungen`). Damit laufen alle Zwangsketten monoton zu gröberen Ebenen –
  hängende Moden zeigen auf gröbere Zellen, aggregierte auf Wurzeln gleicher oder gröberer
  Ebene, Wurzelmoden sind nie aggregiert – und können nicht zurückkehren; ein Selbstbezug ist
  darum ein Fehler, den `Zwaenge` mit Ausnahme meldet. Gemessen: in allen drei verfeinerten
  Patch-Konfigurationen 0 Zyklen bei Kettenlänge 2, u und σ unverändert < 10⁻⁶; die Teilung
  war in keinem Fall nötig (die Wurzeln der Nachbarn reichten), ihr Mechanismus ist in
  `test_oktree` (`Verfeinerung.zellen`) geprüft.
- Ergebnis wie bisher eine Zwangsmatrix C (n_dof × n_frei); Löser, Lasten und Auswertung bleiben
  unverändert.

### 4b.3 STL-Eingang (`geometry/stl.py`)

- Lesen von binärem und ASCII-STL (numpy), Dreiecke mit Flächennormalen, Hüllquader.
- **Vorzeichen über die verallgemeinerte Windungszahl** (Jacobson u. a. 2013): w(P) = Σ Raumwinkel
  der Dreiecke / 4π, innen für w > ½ – robust gegen kleine Lücken (Vorgabe Abschnitt 3).
  Betrag als Abstand zum nächsten Dreieck (Punkt–Dreieck exakt). Beides zunächst blockweise über
  alle Dreiecke (numpy, n·m); für Netze über ~10⁴ Dreiecke kommt der schnelle Windungszahl-Baum
  (Barill u. a. 2018) mit Teilprojekt 5 – hier steht die Korrektheit vorn, die Kosten stehen im
  Protokoll.
- **Lokal eben, drei Lagen:** ein STL ist stückweise eben. Für eine Teilbox liefern die
  Facetten, die ihre Umkugel berühren, die lokalen Ebenen (koplanare zusammengefasst), und
  `lokale_lage` sagt, wie der Werkstoff daraus entsteht: **konvex** (alle Ecken der
  berührenden Facetten auf der Werkstoffseite aller Ebenen: Werkstoff = Schnitt der Halbräume,
  wie bei den Grundformen), **konkav** (alle Ecken auf der Leerseite: Bohrungswand,
  einspringende Kante – der Leerraum ist der Schnitt der gespiegelten Halbräume, der Werkstoff
  ihre Vereinigung, in `csg._form_teile` als Kugel minus Leerraum mit `_subtrahieren`), oder
  **gemischt** (Deckel trifft Bohrungswand, Sattel). Gemischt gilt je Ebene ihr Typ: vom
  Schnitt-Typ, wenn alle Ecken der berührenden Facetten auf ihrer Werkstoffseite liegen, sonst
  vom Vereinigungs-Typ; der Werkstoff ist der Schnitt der Schnitt-Typ-Halbräume mit der
  Vereinigung der übrigen (`csg._form_teile`), geprüft an den Proben der Teilbox gegen das
  Vorzeichen des Formabstands (`_pruefe_teile`). Scheitert die Prüfung, zerlegt `csg._bsp_teile`
  den Würfel um die Teilbox per binärer Raumteilung an den lokalen Ebenen (höchstens sechs) in
  konvexe Zellen, die ein Zeuge (Zellschwerpunkt im einbeschriebenen Würfel, per Windungszahl)
  klassifiziert; erst danach gibt `lokale_stuecke` None zurück, die Teilbox wird weiter geteilt
  und zuletzt per Punkttest integriert (Zähler `blaetter_punkttest`). Gemessen am Viertelring
  (h 10, p 3, belegte Maschine): ohne konkave Lage 6573 Punkttest-Blätter, 10,5 Mio. Randpunkte,
  509 s; mit konkaver Lage, gemischt per Raumteilung 1010 s (29 895 Aufrufe, weil jedes 20 mm
  hohe Wandfacetten-Polygon beide Deckel berührt); mit der Schnitt/Vereinigungs-Regel 43,7 s,
  368 050 Randpunkte, 245 Blätter, kein Punkttest.
  `flaechenfaktor` = 1, `kruemmungsradius` = ∞, `dreiecke()` = die Facetten selbst, Gradient =
  Richtung zum nächsten Punkt der Hülle, auf der Hülle die Facettennormale (Vorzeichen aus der
  Windungszahl). Im CSG-Baum ist das STL eine Grundform (`{"typ": "stl", "pfad": …}` oder
  `"dreiecke"` direkt), also auch schneidbar mit Halbräumen (Schnittebenen) und Löchern.
- **Suchbaum:** nächste Punkte über eine BVH (`geometry/dreiecksbaum.py`: Median-Teilung der
  Schwerpunkte, Boxabstand schneidet Teilbäume ab, numba-Kern mit Stapel je Punkt, seriell
  unter 256 Punkten wegen 0,2 ms Threadstart); ohne numba ein k-d-Baum über Facettenschwerpunkte
  mit exakter Kugelschranke (`stl._DreieckIndex`, Facetten mit R > 1 % der Diagonale für den
  Index geviertelt). Beide liefern dieselben Punkte wie die volle Suche (Prüfung
  `test_suchbaum`). Windungszahl als numba-Kern (Summationsreihenfolge einzig ein Unterschied,
  < 10⁻¹¹), −0,0 → +0,0 im Zähler, damit Punkte genau in einer Facettenebene beidseits gleich
  zählen. Der schnelle Windungszahl-Baum (Barill 2018) bleibt für Teilprojekt 5.
- **Orientierung und Defekt:** eine einzeln verkehrt gewickelte Facette ist mit der Windungszahl
  an ihrer eigenen Probe nicht zu erkennen (ihr eigener Raumwinkel ±½ überdeckt den Rest;
  Gutachten 27.09.), dreht aber Innen/Außen in ihrer Umgebung um. Darum wickelt
  `_konsistent_orientieren` die Facetten über gemeinsame Kanten einheitlich (Nachbarn
  durchlaufen die Kante entgegengesetzt; Breitensuche je Zusammenhangskomponente, Kanten mit
  mehr als zwei Facetten tragen nicht und werden gezählt), richtet jede Komponente über ihr
  Vorzeichenvolumen nach außen und Komponenten ungerader Verschachtelungstiefe (Hohlräume) nach
  innen; `umgedreht` zählt die gewendeten Facetten. Als Sicherung bleibt der |w|-Vergleich
  beidseits einer Stichprobe (mit falsch orientierten Facetten ist w innen −1, das Vorzeichen
  allein taugt nicht). `defekt` = größte Abweichung von w von 0/1 an dieser Stichprobe: 0 bei
  geschlossener Hülle; bei einer Lücke von 1/12 der Oberfläche 0,097. Die Vertragsschicht lehnt
  `defekt` > ¼ ab (Innen/Außen nicht mehr eindeutig) und warnt ab 10⁻³ (Flächenlasten auf der
  Lücke fehlen). Prüfungen: Würfel mit einer verkehrten Facette (umgedreht 1, innen unter ihr
  richtig), Hohlwürfel 30/10 (Hohlraumschale nach innen, Wand innen, Hohlraum außen, Defekt 0).
- **Zweite Sicht (Gutachten 27.09.) eingearbeitet:** Randpolygone genau in einer Zellfläche
  kamen nach Rundung um ein ulp in keiner Zelle an (`dreieck_an_box_clippen` clippt jetzt mit
  Toleranz 10⁻¹²·h, die Werkstoffseite entscheidet); die Prüfung der gemischten STL-Zerlegung
  war für Flächenpolygone leer (alle Proben auf der Fläche) – jetzt kommen Proben knapp
  beidseits dazu; Selbstbezug mit Koeffizient 1 und Rest ≠ 0 bricht ab statt still eine
  Bedingung zu streichen; abgeschnittene Werkstoffläufe zählen nicht als dünne Wand; ein Loch,
  das die ganze Kugel füllt, löscht alle Stücke; `Dreiecksbaum` mit 0 Facetten. Nicht geändert:
  koplanare antiparallele Facetten (innere Doppelfläche) werden zu einer Ebene mit der zuerst
  gesehenen Normale zusammengefasst – im Volumenpfad fängt das die Probenprüfung, im
  Flächenpfad der Zeugentest.
- Innen/Außen-Prüfung: Würfel-STL mit einer fehlenden Facette (Lücke): Windungszahl innen 11/12,
  außen 1/12 (Summe 1), klassifiziert weiter richtig; ein Strahltest durch die Lücke nicht.

### 4b.4 Geometriekern schneller

Gemessen dominiert die Flächenquadratur den Aufbau (Profil: 99 von 106 s). Umgesetzt in
Teilprojekt 2 (jeweils gegen die Suiten geprüft, Ergebnisse unverändert): Blätter-in-Box statt
Dreieck×Wurzelzelle-Schleife (`gitter.blaetter_in_box`), Abstände je Grundform an den Proben
einer Teilbox nur einmal (`lokale_stuecke`), STL-Kern mit BVH und numba-Windungszahl
(Abschnitt 4b.3: Viertelring von 509 s auf 43,7 s). Zweite Runde am 28.09.2026 nach dem
Profil des CSG-Lamé-Aufbaus (50,6 s unter Profiler und Last; 320 000 kleine `abstand`-Aufrufe
mit 15 s, 96 640 einzelne `np.cross` mit 4,3 s, vier Zeugenaufrufe je Polygonstück): in
`lokale_stuecke` ein Abstandsaufruf je Grundform für Mitte und Proben zusammen und der
Gesamtabstand aus denselben Werten über den Baum (`_abstand` mit `vorab`); die Zeugen aller
Stücke eines Polygons in einem Aufruf je Funktion; die acht Kinder einer Teilbox in einem
Abstandsaufruf; Zylinderachse und Radialrichtung einmal je Form statt je Abfrage; Flächenvektor
eines Polygons mit einem `np.cross` statt einem je Fächerdreieck; `_box_abstand` ohne
`linalg.norm`. Ergebnisse unverändert (104 Prüfungen von Geometrie, Quadratur, Patch-Test und
STL identisch grün). Gemessen ohne Profiler bei 42 % Grundlast der Maschine: Lamé CSG h = 10,
p = 3 Aufbau **21,4 s** (vorher 41,9 s), Lamé STL 18,0 s (vorher 43,7 s). Der Rest liegt in
der Vierteilung der Randpolygone an fremden gekrümmten Formen (35 033 Polygonaufrufe aus 2757
Facetten); sie nur für die Teilstücke zu wiederholen, die die gekrümmte Form wirklich berühren,
wäre der nächste Schritt, ändert aber die Punktmenge und gehört zu einer Messung mit den
Abnahmen. Die Modennummerierung über gepackte Schlüssel ist gestrichen: sie taucht im Profil
nicht auf.

### 4b.5 Prüfungen

| Nr. | Suite | Prüfung | Kriterium |
|---|---|---|---|
| U1 | `test_oktree` | Verfeinerung an Schnittzellen/Bereich/dünner Wand, 2:1 über 26 Nachbarn, Punktsuche über Ebenen, Ecken ebenenfrei geteilt, Blätter in Box | Strukturaussagen exakt |
| U2 | `test_zwaenge` | Spurabbildung reproduziert Polynome vom Grad p exakt; hängende Fläche/Kante/Ecke gefunden; Patch-Test auf verfeinertem Gitter (eine Ebene an einer Ecke, dünne Wand) | u, σ < 10⁻⁶ |
| U3 | `test_kirsch` (erweitert) | Loch lokal verfeinert (Bereich r + h, Ebene +2): K_tg gegen Referenz, Schnittlagen-Streuung, Freiheitsgrade gegen gleichmäßiges h = r/4 | Streuung < 1 % bei < 40 % der Freiheitsgrade |
| U4 | `test_stl` | Lesen, Windungszahl an Würfel mit Lücke, Abstand, lokale Ebenen; Lamé aus einem tessellierten Viertelzylinder (Facette 1 mm) gegen CSG | σ-Abweichung STL–CSG < 0,2 % |
| U5 | Kernsuite, `lint-imports`, mypy, `tests.contracts`, `run_all` | wie TP 1 | grün |

## 4c. Teilprojekt 3 im Einzelnen (Stufe 2a, begonnen 28.09.2026)

Plan: `docs/plaene/2026-09-28-tp3-matrixfrei.md`. Ziel ist v = K·u ohne globale Matrix mit
vorkonditioniertem CG, zuerst auf der CPU (numba), dann als CuPy-Kern; gemessen wird alles gegen
die assemblierte Matrix aus Teilprojekt 1.

### 4c.1 Zelldaten und Operator (`fcm/operator.py`)
- **Structure of Arrays:** INSIDE-Zellen je Ebene mit Freiheitsgradtabelle (nz, 3m) und einer
  Referenz-Zellmatrix K_ref je p und Werkstoff (K ∝ h, also K_e = h_l/h₀ · K_ref); CUT-Zellen mit
  gespeicherter Zellmatrix (Vorgabe 8.1 „optional, konfigurierbar“). Die Alternative, je
  Schnittzelle den Quadratursatz zu behalten und K_e u je Anwendung neu zu integrieren, kostet
  bei Tiefe 2 Hunderte Punkte je Zelle und ist erst nötig, wenn die Matrizen nicht ins Budget
  passen (Kirsch h 10 p 3: 1722 Schnittzellen × 295 KB = 0,5 GB; p 4: 1,9 GB) – die Wahl fällt
  nach der Speicherabschätzung.
- **Einsammeln ohne Wettlauf:** Vorgabe 8.1 nennt Atomics oder Graphfärbung. Hier stattdessen
  Gather: der Zellkern schreibt sein Ergebnis in einen Puffer (nz, 3m), und eine vorab gebaute
  Inzidenz „Freiheitsgrad → (Zelle, lokaler Index)“ (CSR) summiert je Freiheitsgrad parallel.
  Keine Atomics, keine Färbung, auf CPU und GPU gleich; der Puffer ist klein (Kirsch h 10 p 3:
  0,4 Mio. Zahlen).
- **Zwänge und Ränder:** hängende Freiheitsgrade und Aggregation bleiben die Zwangsmatrix C aus
  `Zwaenge`; der freie Operator ist A = Cᵀ (K + K_rand) C mit der dünnbesetzten Nitsche-Matrix
  K_rand (Randanteil, klein). Die drei Mittelwertzwänge je Schnittebene (Projektion `schnitt`)
  werden nicht mehr als Sattelpunkt geführt, sondern per projiziertem CG (Nebenbedingung B x = b
  mit 3 Zeilen je Ebene, P = I − Bᵀ(BBᵀ)⁻¹B); A bleibt symmetrisch positiv definit.
- **Summenfaktorisierung** für INSIDE-Zellen (O(p⁴) statt O(p⁶)) kommt als eigene Aufgabe gegen
  die dichte Zellmatrix gemessen; bei p ≤ 4 sind beide Wege nahe beieinander, entschieden wird
  nach Messung.

### 4c.2 PCG (`linalg/pcg.py`)
- FP64, relative Residuumsschranke `FcmSettings.tolerance` (10⁻⁸), zusätzlich Energienorm
  (Vorgabe 8.2), Abbruch über `ProgressCallback`. Jacobi mit der exakten Diagonale von A aus
  den Zellmatrizen (C_eᵀ K_e C_e je Zelle). Mehrere Lastfälle nacheinander; Block-CG später.
- **Gemessen (28.09.2026):** die Jacobi-vorkonditionierte Matrix D^-½ A D^-½ hat Kondition
  1,45·10⁶ (Patch h 20 p 2, 2469 freie Freiheitsgrade) und 5,0·10⁷ (Lamé h 20 p 3, 2316), A
  selbst 1,9·10⁷ bzw. 3,8·10⁹; die Diagonale spannt 3,7·10² bzw. 3,3·10⁴ (Nitsche-Strafterm
  β = 10·E·p²/h auf den Randmoden). PCG braucht 5 045 bzw. 20 373 Iterationen bis 10⁻¹⁰ und
  trifft die direkte Lösung dann auf 7·10⁻⁶ bzw. 2·10⁻⁷; das Kragarmsegment mit projiziertem CG
  548 Iterationen. Das ist der Ausgangspunkt für das Mehrgitter in Teilprojekt 4, kein Mangel
  dieser Stufe: die kleinsten Eigenvektoren verteilen sich über wenige Moden schwach gestützter
  Schnittzellen und Moden hoher Ordnung, genau das Ziel von p-Mehrgitter und Glätter (Vorgabe
  8.3, Richtwert unter 100 Iterationen). Bis dahin bleibt der Direktlöser der Standard der
  Vertragsschicht; der matrixfreie PCG ist als Löser wählbar und geprüft.

### 4c.3 Backends
- CPU: `numba.njit(parallel=True)` für die Zellkerne, numpy-Rückfall ohne numba (langsamer,
  gleiche Zahlen). GPU: `cupy.RawKernel` je Zelle, C und K_rand als `cupyx.scipy.sparse`, PCG mit
  `xp = cupy`; nur lokal prüfbar, CI überspringt. Genauigkeit durchgängig FP64 (gemischt erst in
  Teilprojekt 4 mit der Abnahme „FP64-Referenz auf 10⁻⁶“).
- Vertragsschicht: der Direktlöser bleibt Standard, bis das Mehrgitter (Teilprojekt 4) die
  Iterationszahlen senkt; `FcmProblem(loeser="pcg")` ist geprüft (Protokoll mit Iterationen,
  Residuum, Operator-Speicher). `backend='gpu'` wird in der Vertragsschicht mit Teilprojekt 4
  freigeschaltet, wenn PCG plus Mehrgitter auf der GPU den Direktlöser schlägt.
- **Gemessen (28.09.2026, RTX 3070, FP64):** GPU-Operator = Matrix auf 10⁻¹⁵; Kirsch h 10 p 3
  verfeinert (229 608 Freiheitsgrade) 3,1 ms je Anwendung gegen 18,8 ms CPU (652 MB GPU-Speicher);
  kleine Modelle 0,05–0,63 ms gegen 0,17–0,22 ms; PCG auf der GPU identisch zur CPU (5·10⁻¹²), bei
  2 316 freien Freiheitsgraden 6,8 s gegen 0,1 s – die Startkosten je Iteration zählen, solange
  Jacobi Tausende Iterationen braucht.

### 4c.4 Prüfungen

| Nr. | Suite | Prüfung | Kriterium |
|---|---|---|---|
| V1 | `test_operator` | Inzidenz und Freiheitsgradtabelle wie `zell_dofs`; Zellmatrizen über die Inzidenz summiert = assemblierte Matrix | < 10⁻¹² relativ |
| V2 | `test_operator` | A x gegen (Cᵀ K C) x auf Kirsch verfeinert, Lamé, Patch dünne Wand, 20 Zufallsvektoren | < 10⁻¹² relativ |
| V3 | `test_operator` | Summenfaktorisierung = dichte Zellmatrix; Zeitvergleich p 2…4 | < 10⁻¹³; Messung |
| V4 | `test_pcg` | PCG gegen Direktlöser (Patch, Kragarm mit `schnitt`, Lamé, Kirsch) | 10⁻⁸ relativ; Iterationen protokolliert |
| V5 | `test_vertrag_fcm` | `solve` mit PCG gleich Direktlöser am Vertragsbeispiel | 10⁻⁶ relativ |
| V6 | `test_operator_gpu` (lokal) | GPU gegen CPU, Operator und Lösung | 10⁻¹² / 10⁻⁸ |
| V7 | Kernsuite, `lint-imports`, mypy, `tests.contracts`, `run_all` | wie bisher | grün |
