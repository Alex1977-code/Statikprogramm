# Für die Statik3D-Sitzung: wo die 46 Kontaktschritte eines warmen Lastfalls herkommen

Übergabe aus der Gleichungslöser-Sitzung, 20.09.2026.
Zweig `claude/statikprogramm-analog-ansys-bzfhij`, Stand `020a1a3`.

## Die Lage

Für 422 Lastfälle am Drehlager zählt allein der **warme** Lastfall — einer ist kalt, 421 sind warm.
Gemessen auf freier Maschine (20.09.2026, drehlager.json, PARDISO, Ryzen 9 5950X):

| Lastfall | Zeit | Kontaktschritte | Plastizitätsschritte |
|---|---|---|---|
| LF1 (kalt) | 821,1 s | **109** | 19 |
| LF3 (warm) | 400,5 s | **52** | 19 |
| LF5 (warm) | 343,4 s | **46** | 19 |

max|u| = 0,2680 mm in allen dreien, unverändert gegenüber allen früheren Läufen.

**Der semiglatte Newton (`34c2f51`, `020a1a3`) hat den kalten Fall von 698 auf 109 Schritte
gebracht — Faktor 6,4 — und den warmen von 56 auf 52, also gar nicht.** Das ist folgerichtig: warm
startet die Iteration im nahezu richtigen Zustand, es sind kaum Reibwechsel nötig, und die Regel
„ein Wechsel je Runde" war dort nie der Engpass.

## Die offene Frage

**46 Kontaktschritte bei 19 Plastizitätsschritten sind 2,4 Schritte je Plastizitätsschritt.**
Wenn der Kontaktzustand zwischen zwei Plastizitätsschritten unverändert bleibt — und das sollte er
weitgehend, die Plastizität ändert nur die rechte Seite —, müsste ein Plastizitätsschritt mit
**einem** Kontaktschritt auskommen, und dieser eine müsste die Faktorisierung des vorigen
wiederverwenden (`StaticSystem.solve(..., signatur=cs.signatur())`).

Gemessen kostet ein Schritt 343,4 s / 46 = **7,5 s**. Eine Faktorisierung der Drehlager-Matrix
kostet 4,23 s (PARDISO, 476.214 Zeilen, gemessen 19.09.2026). Dazwischen liegt der Aufbau von
`Kt = K + Kc` und das Herausschneiden von `Ktff` — eine dünn besetzte Addition über 17,8 Mio.
Einträge. **Die 7,5 s beweisen also nicht, dass die Faktorisierung verworfen wird**; das war eine
zu schnelle Schlussfolgerung der Löser-Sitzung und ist hiermit zurückgenommen.

**Was wirklich zu messen ist:**

1. **`cinfo["contact_factorisations"]` je Plastizitätsschritt.** Es steht schon im Info-Wörterbuch
   (`solve_with_contact` zählt `system.faktorisierungen`). Wird es je Schritt protokolliert, steht
   sofort da, ob wiederverwendet wird oder nicht.
2. **Wie viel von den 7,5 s ist Faktorisierung, wie viel der Aufbau von `Kt`?** `matrizen()` und
   die Zeile `Ktff = Kt[self.fi][:, self.fi].tocsc()` in `StaticSystem.solve` einzeln messen.
   Am Drehlager ist `self.fi` 476.214 lang und `K` hat 17,8 Mio. Einträge — das Herausschneiden
   mit zwei Indexlisten ist in scipy nicht billig und läuft in **jedem** Kontaktschritt.
3. **Warum 2,4 statt 1 Schritt je Plastizitätsschritt?** Wechselt wirklich etwas am Kontakt, oder
   läuft eine Setzrunde der Reibung (`dF_slip > 1e-4 * f_ref`, `SETTLE_ROUNDS = 8`)? Die Setzrunden
   ändern die Matrix **nicht** — dort müsste die Faktorisierung stehen bleiben.

## Was schon geprüft und ausgeschlossen ist

* **Die Phase geht nicht verloren.** `ContactSystem.zustand()` nimmt `phase` mit, `zustand_setzen`
  stellt sie wieder her, und der Docstring hält ausdrücklich fest: „Es geht in der Phase der
  Sicherung weiter (2 nach einer konvergierten Rechnung): der erste Schritt löst mit derselben
  Matrix wie der letzte des vorigen."
* **Die Signatur ist nicht zu fein.** Sie ist `(phase, aktiv, gleiten, fliessen,
  full_slip_groups)` — genau die Größen, von denen `Kc` abhängt. Eine gröbere Signatur würde
  falsch rechnen, nicht schneller.

## Warum es sich lohnt

Bleibt es bei 46 Schritten à 7,5 s, kosten 422 Lastfälle **421 × 343 s = 40 Stunden = 1,7 Tage**.
Käme ein Plastizitätsschritt mit einem Kontaktschritt aus und würde dieser die Faktorisierung
wiederverwenden, wären es 19 Schritte à ~1 s statt 46 à 7,5 s — also **rund 20 s je Lastfall** und
**2,3 Stunden** für alle 422.

Das ist der größte verbliebene Hebel am Drehlager, und er liegt ganz in Statik3D.

## Konventionen

Deutsch, im Quelltext ohne Umlaute; jede Zahl gemessen und mit Datum; je Verhaltensänderung ein
Test, der ohne sie fehlschlägt, und ein Absatz im Handbuch; vor jedem Commit
`python -m tests.run_all`. Unter Windows in einer Pipe nach UTF-8 umstellen
(`PYTHONUTF8=1`) — ein „ε" hat in dieser Sitzung einen 70-Minuten-Lauf nach dem Rechnen zerrissen.

## Stand des Zweigs

`020a1a3` Reibung Phase 2: der Gleitanteil sucht seine Schrittweite selbst
`34c2f51` Reibung Phase 2: ein Anteil der haftenden Knoten je Runde statt genau einer
`6ad3aae`…`4b21cf9` Schubhalt (behebt den Drehlager-Abbruch)

Alle auf `ALLE TESTS BESTANDEN` geprüft. Die exe vom 19.09., 18:20 kennt den semiglatten Newton
**nicht** — sie ist aus `main` bei `8d7b7b5` gebaut, beide Newton-Commits kamen danach.
