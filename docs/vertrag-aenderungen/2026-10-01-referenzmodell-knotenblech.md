# Vorschlag: Referenzmodell „Knotenblech mit Kehlnaht“ (Vertrag Abschnitt 8, Ablage nach E3)

**Anlass:** Plan TP 5 des Volumenmoduls, Schritt C1 (Abnahme: Hot-Spot-Spannung gegen Tet10 unter 3 %, Vorgabe 13).
Entscheidungen des Anwenders vom 29.09.2026: E2 – die Referenz ist die Tet10-Rechnung des Hauptprogramms
`statik3d/`, im Protokoll so benannt; E3 – Ablage der Referenzmodelle in `tests/reference_models/` (für Session B nur
lesbar) als eigener Pull Request der Hauptsitzung.

**Vorgeschlagene Änderung:** keine Änderung an Typen oder Protokollen (Versionsstufe **Patch**, nur Daten): neues
Verzeichnis `tests/reference_models/knotenblech_kehlnaht/` mit

| Datei | Inhalt | Quelle |
|---|---|---|
| `knotenblech_kehlnaht.json` | Eingabedaten (Geometrie, Werkstoff, Last, Nahtlinien, Referenzpunkte, Formel, Toleranz) | Session B, `volumen3d/tests/test_knotenblech.py` (`MODELL`), liegt fertig in `Desktop/Statik3D/REFERENZ-KNOTENBLECH-2026-10-01/` |
| `knotenblech.step` | Körper zwischen den Schnittebenen (x 0…200), aus gmsh/OpenCASCADE, Volumen 181 936 mm³ exakt | Session B |
| `erwartung_tet10.json` | Erwartungswerte der Referenz: σ_xx an den 36 Referenzpunkten, σ_hs je Nahtpunkt, Reaktionskraft, Netzangaben, Programmstand | **Hauptsitzung** (Tet10-Rechnung) |

Das Volumenmodul liest die Erwartungswerte nur (Abnahmetest `test_knotenblech.test_knotenblech_konvergenz`); bis sie
vorliegen, stehen die Werte in `REFERENZ` des Tests als „vorläufig“.

## Modell (identisch mit `MODELL` im Test; alle Maße mm, N, N/mm²)

```json
{
 "name": "Knotenblech mit Kehlnaht (Laengsrippe, IIW Typ a)",
 "werkstoff": {"E": 210000.0, "nu": 0.3},
 "grundblech": {"min": [-5.0, 0.0, -10.0], "max": [205.0, 80.0, 0.0], "hinweis": "Schnittebenen x 0 und x 200 stutzen auf 200 mm; das Polster ist nicht Teil des Details"},
 "knotenblech": {"min": [70.0, 36.0, 0.0], "max": [130.0, 44.0, 40.0]},
 "kehlnaht": {"schenkel": 6.0, "quader_min": [64.0, 30.0, 0.0], "quader_max": [136.0, 50.0, 6.0],
              "halbraeume_innen": [{"punkt": [136, 0, 0], "normale": [1, 0, 1]}, {"punkt": [64, 0, 0], "normale": [-1, 0, 1]},
                                   {"punkt": [0, 50, 0], "normale": [0, 1, 1]}, {"punkt": [0, 30, 0], "normale": [0, -1, 1]}],
              "hinweis": "Pyramidenstumpf (Prismatoid) mit 45-Grad-Flanken, Ecken auf Gehrung; Volumen 5 616 = 6/6 (72*20 + 4*66*14 + 60*8)"},
 "schnittebenen": [{"punkt": [0.0, 40.0, -5.0], "normale": [-1, 0, 0]}, {"punkt": [200.0, 40.0, -5.0], "normale": [1, 0, 0]}],
 "last": {"sigma_n": 100.0, "u": "(eps x, -nu eps (y - 40), -nu eps (z + 5)), eps = sigma_n / E", "schnittkraft_N": 80000.0,
          "kopplung_volumenmodul": "Normalkomponente punktweise (Nitsche), Tangentialkomponenten als Mittelwerte"},
 "nahtlinien": {"stirn_rechts": "(136, y, 0)", "stirn_links": "(64, y, 0)", "y": [32, 34, 36, 38, 40, 42, 44, 46, 48], "blechdicke": 10.0},
 "hot_spot": {"verfahren": "IIW Typ a, 0,4 t und 1,0 t senkrecht zur Naht auf der Blechoberseite z = 0",
              "punkte_rechts": {"0.4t": "(140, y, 0)", "1.0t": "(146, y, 0)"}, "punkte_links": {"0.4t": "(60, y, 0)", "1.0t": "(54, y, 0)"},
              "formel": "sigma_hs = 5/3 sigma_xx(0,4 t) - 2/3 sigma_xx(1,0 t)"},
 "toleranz": {"sigma_hs_gegen_referenz": 0.03, "symmetrie_rechts_links": 0.01}
}
```

## Bitte an die Hauptsitzung (Tet10-Referenz)

1. Körper aus `knotenblech.step` oder dem beigelegten gmsh-Netz `knotenblech_tet10_1mm.inp` (C3D10, 247 636 Elemente,
   363 048 Knoten; 1 mm in 12 mm Umkreis der Nahtübergänge, 2,5 mm im Blech, 5 mm fern; Knotenmengen `stirn_x0`,
   `stirn_x200`; Einheit mm → beim Import `unit_scale = 1e-3`). Ein eigenes Netz des Hauptprogramms ist ebenso recht,
   wenn die Kantenlänge am Übergang höchstens t/10 = 1 mm beträgt.
2. Randbedingungen wie der Vertragsweg: u_x = ε·x auf den Stirnflächen x 0 (u_x = 0) und x 200 (u_x = 200 ε = 0,095238 mm),
   ε = 100/210 000; Querbewegung frei; Starrkörper statisch bestimmt sperren (z. B. u_y = u_z = 0 bei (0, 40, −5),
   u_z = 0 bei (0, 80, −5)). Die Querdehnung −νε(y − 40), −νε(z + 5) des Geberfelds geht im Volumenmodul nur als
   Mittelwert ein und ist dort null – darum freie Querbewegung.
3. Auswertung: σ_xx an den 36 Referenzpunkten (Knotenwerte oder an die Punkte interpoliert – bitte sagen, was), σ_hs je
   Nahtpunkt nach der Formel, Reaktionskraft in x an x 200, Knoten- und Elementzahl, Kantenlänge am Übergang,
   Programmstand (Commit). Liegt die Abweichung zum Volumenmodul über 3 %, bitte zusätzlich mit 0,5 mm am Übergang
   (Netzkonvergenz der Referenz), bevor eine Seite das Verfahren hinterfragt.
4. Ablage als `erwartung_tet10.json` neben den beiden anderen Dateien, eigener Pull Request auf `main` (E3).

**Auswirkung auf das Hauptprogramm:** keine Code-Änderung; nur Daten im Repository und eine Tet10-Rechnung.

**Stand:** Vorschlag gestellt 01.10.2026 (Session B). Die FCM-Seite (vier Zyklen h 5, h 2,5, p 3, p 4) steht in Theorie 11.18.
