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
