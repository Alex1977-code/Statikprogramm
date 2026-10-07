# O21: Zellaggregation bei lokaler Teilung – Umsetzungsplan

> **Für ausführende Agenten:** Pflicht-Skill: superpowers:executing-plans (in dieser Sitzung inline), Aufgabe für Aufgabe. Schritte mit Kästchen (`- [ ]`).

**Ziel:** Lokales Teilen soll den wahren Fehler nicht mehr erhöhen; danach Regel 5 aus Phase 1 erneut prüfen. Auftrag des Anwenders vom 06.10.2026 („O21 vor Phase 2“).

**Befund aus Phase 1** (Plan `2026-10-06-tp6a-phase1-schaetzer.md`, Ergebnis): Lamé h 20 p 2, ein Dörfler-Schritt mit 4 geteilten Zellen. Mit Aggregation steigt ‖e‖_E von 2,049 auf 2,184,
ohne Aggregation fällt es von 1,610 auf 1,263. Der Fehleranteil e² der ungeteilten Zellen steigt von 2,390 auf 3,303. 52 von 81 Zellen sind aggregiert, 42 davon mit der Wurzel
außerhalb der Elternzelle.

**Vermuteter Mechanismus (aus dem Code, noch nicht gemessen).** `Zellaggregation._wurzeln_zuordnen` wählt als Wurzel nie eine feinere Zelle (sonst Zwangszyklen, test_zwaenge
27.09.2026). Wird eine Wurzelzelle R geteilt, verlieren die ungeteilten Zellen, deren Wurzel R war, ihre Wurzel: sie binden sich an einen anderen, gröberen oder gleich groben
wohlgestellten Nachbarn, erben über eine Kette, bleiben ohne Wurzel bei α oder werden selbst geteilt (`zu_teilen`). Das Polynom von R über das alte Aggregat ist danach im neuen
Raum nicht mehr darstellbar.

**Kur K1 (Kandidat).** Ganze Aggregate teilen: eine markierte Zelle zieht ihre Wurzel und alle Zellen mit derselben Wurzel nach sich, eine markierte Wurzel alle an ihr hängenden
Zellen. Neu ist nur `schaetzer.aggregate_ergaenzen(problem, zellen)`, aufgerufen vor `verfeinerung_nach`. `Zellaggregation` bleibt unverändert, darum bleibt jede Rechnung ohne
adaptive Teilung Bit für Bit gleich. K1 garantiert die Schachtelung nicht: ein schlecht gestelltes Kind kann sich an einen Nachbarn außerhalb des alten Aggregats binden. Ob es reicht,
entscheidet die Messung.

---

## Regeln, vor der Messung festgelegt (06.10.2026)

**Teil A, Mechanismus.** Für denselben Schritt (Lamé h 20 p 2, Dörfler 0,5, ohne K1) wird jede ungeteilte Zelle (gleiche Ebene und Indizes vor und nach dem Schritt) einer Klasse
zugeordnet: Wurzel gleich, Wurzel gewechselt, Wurzel verloren (danach ohne Wurzel), Wurzel neu (vorher wohlgestellt oder ohne Wurzel). Zellen, die nicht markiert waren und
trotzdem geteilt wurden (Wurzelteilungen der Aggregation), werden getrennt gezählt. Der Mechanismus gilt als **belegt**, wenn (i) mindestens eine markierte Zelle Wurzel ungeteilter
Zellen ist und (ii) die Klassen „gewechselt“ und „verloren“ zusammen mindestens 80 % der positiven Zunahme von e² in den ungeteilten Zellen tragen. Sonst wird der Befund berichtet,
und der Anwender entscheidet, bevor K1 gebaut wird.

**Teil B, Kur.** (B1) Mit K1 fällt ‖e‖_E an Lamé h 20 p 2 und an Kirsch (Basis 20, p 2, Referenz p 4 auf dem jeweiligen Gitter) in jedem der ersten sechs Dörfler-Zyklen
(jeder Zyklus ≤ dem vorherigen). (B2) Regel 5 erneut, mit denselben Vergleichszahlen wie in Phase 1: Lamé ‖e‖_E ≤ 0,1215 mit weniger als 28 215 freien Freiheitsgraden, Kirsch
‖e‖_E ≤ 0,4363 mit weniger als 10 677. Gerechnet wird an beiden Modellen so viele Zyklen, bis die freien Freiheitsgrade die des Vergleichsglieds erreichen, höchstens 15 Zyklen;
erfüllt, wenn ein Zustand mit weniger Freiheitsgraden den Vergleichsfehler erreicht. Der Anwender nannte die offene Zyklenzahl für Kirsch. Für Lamé gilt sie ebenfalls: drei Zyklen ab
765 Freiheitsgraden können den Fehler des Glieds mit 28 215 auch bei geschachtelten Räumen nicht erreichen (der Fehler müsste auf ein Siebzehntel fallen, Dörfler 0,5 teilt je
Zyklus nur wenige Zellen). Diese Lesart wird dem Anwender mit dem Ergebnis genannt. (B3) Ohne adaptive Teilung ändert sich keine Zahl: Kernsuite und `test_schaetzer` grün, die
übrigen Suiten rufen den neuen Weg nicht auf. (B4) Eine Prüfung, die ohne K1 fehlschlägt: ein Dörfler-Schritt an Lamé h 20 p 2 erhöht ‖e‖_E nicht; dieselbe Prüfung rechnet zum
Vergleich ohne K1 und verlangt dort die Zunahme, damit sie nicht leer ist.

Verfehlt K1 die Regel B1, wird das mit dem Befund berichtet, und der Anwender entscheidet mit Empfehlung (Kandidat K2: die Wurzelwahl ändern, etwa feinere Wurzeln innerhalb der
früheren Elternzelle zulassen, mit Zyklusschutz; das ändert alle Rechnungen mit Aggregation und braucht einen eigenen Plan).

---

### Aufgabe 1: Mechanismus messen (Teil A)

**Dateien:** Scratchpad `o21_mechanismus.py` (nicht im Paket)

- [ ] **Schritt 1: Messprogramm**

```python
"""O21 Teil A: Klassen der ungeteilten Zellen beim Doerfler-Schritt Lame h 20 p 2 (Regeln im Plan 2026-10-06-o21-aggregation-lokale-teilung.md)."""
import json
import numpy as np

from volumen3d.fcm.problem import FcmProblem, Werkstoff
from volumen3d.fcm.schaetzer import doerfler, energiefehler, schaetzen, verfeinerung_nach
from volumen3d.tests import test_lame as L
from volumen3d.tests.test_schaetzer import _lame_sigma


def problem(v):
    pr = FcmProblem(L._geometrie(), h=20.0, p=2, werkstoff=Werkstoff(L.E, L.NU), verfeinerung=v)
    for n in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
        pr.verschiebungsrand(n, n, projektion="normal")
    pr.druck("innen", L.PI)
    return pr


def schluessel(G, c):
    return (int(G.ebene[c]), int(G.ijk[c, 0]), int(G.ijk[c, 1]), int(G.ijk[c, 2]))


pr0 = problem(None)
U0 = pr0.loesen({})[:, 0]
mark = doerfler(schaetzen(pr0, U0).zelle ** 2, 0.5)
pr1 = problem(verfeinerung_nach(pr0.gitter, pr0.verfeinerung, mark))
U1 = pr1.loesen({})[:, 0]
e2_0, _ = energiefehler(pr0, U0, _lame_sigma)
e2_1, _ = energiefehler(pr1, U1, _lame_sigma)
G0, G1, w0, w1 = pr0.gitter, pr1.gitter, pr0.aggregation.wurzel, pr1.aggregation.wurzel
k0 = {schluessel(G0, c): c for c in range(len(G0.ijk))}
marksch = {schluessel(G0, c) for c in mark}
klassen = {"gleich": [], "gewechselt": [], "verloren": [], "neu": [], "ohne": []}
for c1 in range(len(G1.ijk)):
    c0 = k0.get(schluessel(G1, c1))
    if c0 is None:
        continue
    r0 = schluessel(G0, w0[c0]) if w0[c0] >= 0 else None
    r1 = schluessel(G1, w1[c1]) if w1[c1] >= 0 else None
    k = "ohne" if r0 is None and r1 is None else "gleich" if r0 == r1 else "verloren" if r1 is None else "neu" if r0 is None else "gewechselt"
    klassen[k].append(float(e2_1[c1] - e2_0[c0]))
zunahme = sum(max(d, 0.0) for v in klassen.values() for d in v)
abh_markiert = int(sum(1 for c in range(len(G0.ijk)) if w0[c] >= 0 and schluessel(G0, w0[c]) in marksch and schluessel(G0, c) not in marksch))
neu_geteilt = [c1 for c1 in range(len(G1.ijk)) if schluessel(G1, c1) not in k0
               and not any(schluessel(G1, c1)[0] == s[0] + 1 and all(schluessel(G1, c1)[1 + i] // 2 == s[1 + i] for i in range(3)) for s in marksch)]
print("A " + json.dumps({
    "markiert": int(len(mark)), "markierte_wurzeln_mit_abhaengigen": abh_markiert,
    "klassen": {k: {"zellen": len(v), "summe_de2": round(sum(v), 4), "positive_de2": round(sum(max(d, 0.0) for d in v), 4)} for k, v in klassen.items()},
    "anteil_gewechselt_verloren": round((sum(max(d, 0.0) for d in klassen["gewechselt"] + klassen["verloren"])) / zunahme, 4) if zunahme > 0 else None,
    "nicht_markiert_geteilt": len(neu_geteilt), "e2_nicht_markiert_geteilt": round(float(e2_1[neu_geteilt].sum()), 4)}))
```

- [ ] **Schritt 2: laufen lassen** aus dem festen Arbeitsbaum auf 1f9fb6b (Code wie 9fc6966), 8 Threads; Ausgabe nach `o21_a.log`.
- [ ] **Schritt 3: urteilen** nach Regel A (zweite Auswertung: die Anteile von Hand aus den Klassensummen nachrechnen). Ist der Mechanismus nicht belegt: anhalten, berichten.

---

### Aufgabe 2: Kur K1 – ganze Aggregate teilen

**Dateien:** ändern `packages/volumen3d/volumen3d/fcm/schaetzer.py`; Prüfungen in `packages/volumen3d/volumen3d/tests/test_schaetzer.py`

- [ ] **Schritt 1: Prüfungen schreiben**

```python
def test_aggregate_ergaenzen():
    """Eine markierte aggregierte Zelle zieht ihre Wurzel und alle Zellen derselben Wurzel nach sich; eine markierte Wurzel alle an ihr haengenden Zellen; ohne
    Aggregation bleibt die Menge, wie sie ist."""
    from volumen3d.fcm.schaetzer import aggregate_ergaenzen
    from volumen3d.tests import test_lame as L
    pr, _ = L._rechnen(2, 20.0)
    w = pr.aggregation.wurzel
    c = int(np.flatnonzero(w >= 0)[0])
    r = int(w[c])
    gruppe = set(np.flatnonzero(w == r).tolist()) | {r}
    a = set(aggregate_ergaenzen(pr, [c]).tolist())
    b = set(aggregate_ergaenzen(pr, [r]).tolist())
    frei = int(np.flatnonzero((w < 0) & ~np.isin(np.arange(len(w)), w))[0])      # wohlgestellt und keine Wurzel
    check(f"aggregate_ergaenzen: Zelle {c} mit Wurzel {r} -> Aggregat aus {len(gruppe)} Zellen; Wurzel allein ebenso; freie Zelle {frei} bleibt allein",
          a == gruppe and b == gruppe and list(aggregate_ergaenzen(pr, [frei])) == [frei])


def test_teilen_ohne_fehlerzunahme():
    """O21, Regel B4: ein Doerfler-Schritt an Lame h 20 p 2 erhoeht den wahren Fehler nicht, wenn ganze Aggregate geteilt werden. Zum Vergleich ohne die Kur: dort
    steigt er (Phase 1: 2,049 -> 2,184), sonst waere die Pruefung leer."""
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.fcm.schaetzer import aggregate_ergaenzen, doerfler, energiefehler, schaetzen, verfeinerung_nach
    from volumen3d.tests import test_lame as L
    pr0, aus0 = L._rechnen(2, 20.0)
    e0 = energiefehler(pr0, aus0.U, _lame_sigma)[1]
    mark = doerfler(schaetzen(pr0, aus0.U).zelle ** 2, 0.5)
    werte = {}
    for name, zellen in (("mit Kur", aggregate_ergaenzen(pr0, mark)), ("ohne Kur", mark)):
        pr = FcmProblem(L._geometrie(), h=20.0, p=2, werkstoff=Werkstoff(L.E, L.NU), verfeinerung=verfeinerung_nach(pr0.gitter, pr0.verfeinerung, zellen))
        for s in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
            pr.verschiebungsrand(s, s, projektion="normal")
        pr.druck("innen", L.PI)
        werte[name] = (energiefehler(pr, pr.loesen({})[:, 0], _lame_sigma)[1], len(zellen))
    check(f"Lame h 20 p 2, ein Doerfler-Schritt: ||e||_E {e0:.4f} -> mit Kur {werte['mit Kur'][0]:.4f} ({werte['mit Kur'][1]} Zellen geteilt), "
          f"ohne Kur {werte['ohne Kur'][0]:.4f} ({werte['ohne Kur'][1]} Zellen)", werte["mit Kur"][0] <= e0 and werte["ohne Kur"][0] > e0)
```

Beide in die `lauf`-Liste von `test_schaetzer` eintragen; `test_aggregate_ergaenzen` auch in die Kernsuite (wenige Sekunden), `test_teilen_ohne_fehlerzunahme` nur in die eigene Suite.

- [ ] **Schritt 2: fehlschlagen sehen** – erwartet `ImportError: cannot import name 'aggregate_ergaenzen'`.

- [ ] **Schritt 3: umsetzen** (in `schaetzer.py` vor `verfeinerung_nach`, `__all__` erweitern)

```python
def aggregate_ergaenzen(problem, zellen) -> np.ndarray:
    """Markierte Zellen zu ganzen Aggregaten ergaenzen (O21): zu jeder markierten Zelle ihre Wurzel (oder sie selbst, wenn sie keine hat) und alle Zellen mit
    dieser Wurzel. Die Zellaggregation waehlt nie eine feinere Wurzel; wird eine Wurzel allein geteilt, verlieren die ungeteilten Zellen an ihr die Wurzel, und
    das Polynom des alten Aggregats ist im neuen Raum nicht mehr darstellbar (Lame h 20 p 2: ||e||_E 2,049 -> 2,184 bei vier geteilten Zellen, Plan O21)."""
    zellen = np.asarray(zellen, int).ravel()
    ag = getattr(problem, "aggregation", None)
    if ag is None or len(zellen) == 0:
        return np.unique(zellen)
    w = np.asarray(ag.wurzel)
    kopf = np.where(w[zellen] >= 0, w[zellen], zellen)
    return np.unique(np.concatenate([zellen, kopf, np.flatnonzero(np.isin(w, kopf))]))
```

- [ ] **Schritt 4: grün sehen** – `python -m volumen3d.tests.test_schaetzer`, erwartet 16/16.
- [ ] **Schritt 5: Kernsuite** (`test_aggregate_ergaenzen` eintragen), erwartet 391/391; Commit.

---

### Aufgabe 3: Messung Teil B

**Dateien:** Scratchpad `o21_messung.py`

- [ ] **Schritt 1: Messprogramm** – wie `p1_messung.adaptiv`, mit `aggregate_ergaenzen` vor `verfeinerung_nach`, an Lamé und Kirsch, Zyklen bis die freien Freiheitsgrade 28 215
  bzw. 10 677 erreichen, höchstens 15; je Zyklus eine Zeile `B {"modell", "zyklus", "fhg", "zellen", "eta", "e", "geteilt"}`.
- [ ] **Schritt 2: laufen lassen** aus einem festen Arbeitsbaum auf dem Commit von Aufgabe 2, 8 Threads, nacheinander.
- [ ] **Schritt 3: urteilen** nach B1 und B2 mit zwei unabhängig geschriebenen Auswertungen; Ergebnis in diesen Plan.

### Aufgabe 4: Dokumentation

- [ ] Theorie 11.22 Nachtrag O21 (Mechanismus, Kur, Zahlen, Regel 5 neu), Entwurf 4f.2, Volumenmodul; Commit und Push auf `feature/volumen3d`; Pull Request nur auf Anweisung.

---

## Ergebnis O21

**Teil A (07.10.2026, fester Arbeitsbaum 9fc6966, 8 Threads, `o21_mechanismus.py` wörtlich aus diesem Plan): Mechanismus nicht belegt.** Markiert waren 4 Zellen; 3 ungeteilte Zellen
hatten eine markierte Wurzel, Bedingung (i) ist also erfüllt. Die ungeteilten Zellen verteilen sich so:

| Klasse | Zellen | Summe Δe² | positive Δe² |
|---|---|---|---|
| Wurzel gleich | 34 | +0,193 | 0,230 |
| Wurzel gewechselt | 3 | +0,247 | 0,247 |
| Wurzel verloren | 0 | 0 | 0 |
| Wurzel neu | 0 | 0 | 0 |
| ohne Wurzel vorher und nachher | 15 | +0,473 | 0,813 |

Gewechselte und verlorene Wurzeln tragen 0,247 / 1,291 = 19 % der positiven Zunahme (Regel: mindestens 80 %; von Hand aus den Klassensummen nachgerechnet). Nicht markierte Zellen
wurden nicht geteilt. Die Klasse „ohne Wurzel“ besteht ganz aus wohlgestellten Zellen (15, keine schlecht gestellte bei α; `zellen_ohne_wurzel` vorher und nachher 0, `o21_ohne.py`):
63 % der Zunahme liegen in Zellen mit freien Polynomen. Ihr Fehler steigt nicht wegen ihrer eigenen Wurzel, sondern weil die Lösung insgesamt schlechter wird; die Einschränkung des
Raums sitzt woanders. Naheliegend, aber nicht gemessen: in den geteilten Zellen selbst, wenn sich schlecht gestellte Kinder an Wurzeln außerhalb ihrer Elternzelle binden und das Polynom
der Elternzelle dort nicht mehr darstellbar ist. Nach der Regel wird K1 nicht gebaut, bevor der Anwender entscheidet.

**Empfehlung.** Zuerst eine Schachtelungsprobe (A2) mit vorab festgelegter Regel: die alte Lösung u_h,0 im neuen Raum bestmöglich darstellen (L²-Ausgleich über die Werkstoffpunkte, im neuen
Raum mit allen Zwängen) und den Rest je Zelle messen. Bei geschachtelten Räumen ist er null bis auf Rundung; wo er es nicht ist, liegt die Verletzung. Danach die Kur dort ansetzen:
K1 (ganze Aggregate teilen), wenn der Rest an Zellen mit gewechselter Wurzel sitzt, K2 (schlecht gestellte Kinder bevorzugt an Geschwister in derselben Elternzelle binden), wenn er an
geteilten Zellen mit Wurzel außerhalb der Elternzelle sitzt. K2 ändert die Wurzelwahl in allen verfeinerten Gittern und damit Zahlen in mehreren Suiten.


**Kurversuch und Teil B (07.10.2026).** Auf die Ansage des Anwenders („allerletzte Chance, los“) wurden die Kuren direkt am Ziel geprüft statt weiter die Ursache: sechs
Dörfler-Zyklen an Lamé h 20 p 2, der wahre Fehler muss in jedem fallen (`o21_kurprobe.py`). K1 (ganze Aggregate) erfüllt das, K2 (Kinder an Geschwister) allein nicht (der Fehler steigt
wie ohne Kur: 2,049 / 2,184 / 2,888 / 3,116, dann 1,196 / 1,351 / 0,610), K1 und K2 zusammen sind nicht besser als K1 (0,177 gegen 0,179 nach sechs Zyklen). Gebaut ist K1
(`schaetzer.aggregate_ergaenzen`, 1221915); die Aggregation selbst ist unverändert, kein Modul außer den Prüfungen ruft den neuen Weg auf, die Kernsuite läuft mit 391/391. Messung aus dem
festen Arbeitsbaum 1221915 (`o21_messung.py`, 8 Threads), zwei unabhängige Auswertungen mit gleichen Urteilen:

| Zyklus | Lamé: freie FHG | Lamé: ‖e‖_E | Kirsch: freie FHG | Kirsch: ‖e‖_E |
|---|---|---|---|---|
| 0 | 765 | 2,049 | 7 713 | 4,886 |
| 1 | 1 701 | 0,994 | 7 821 | 2,549 |
| 2 | 2 229 | 0,715 | 8 319 | 1,126 |
| 3 | 5 397 | 0,534 | 8 961 | 0,669 |
| 4 | 9 399 | 0,293 | 10 149 | 0,477 |
| 5 | 15 345 | 0,204 | 12 879 | 0,293 |
| 6 | 31 485 | 0,179 | 15 837 | 0,224 |
| Vergleichsglied | 28 215 (gleichmäßig h 5) | 0,1215 | 10 677 (Ziel 5 am Loch) | 0,4363 |

**B1 (Fehler fällt in jedem der sechs Zyklen): erfüllt** an Lamé und Kirsch. **B2 (Regel 5 erneut): verfehlt** an beiden. Lamé: der beste Zustand unter 28 215 Freiheitsgraden ist
Zyklus 5 mit 15 345 und 0,204, das gleichmäßige Gitter h 5 erreicht 0,1215; adaptiv und gleichmäßig liegen bei gleicher Größe etwa gleich (gleichmäßig zwischen h 10 und h 5 auf 15 345
Freiheitsgrade interpoliert etwa 0,20). Kirsch: Zyklus 4 mit 10 149 Freiheitsgraden und 0,477 gegen das von Hand am Loch verfeinerte Glied mit 10 677 und 0,436; auf 10 677 interpoliert
liegt die adaptive Folge bei etwa 0,43. Die Adaptivität findet also selbst, was die Verfeinerung von Hand am Loch leistet, schlägt sie aber nicht, und am Lamé-Zylinder, dessen Fehler über
den ganzen Querschnitt verteilt ist, schlägt sie das gleichmäßige Gitter nicht. Ob Regel 5 so stehen bleibt, entscheidet der Anwender.

## Modell je Schritt

| Schritt | Modell | Denkstufe | Stand |
|---|---|---|---|
| Aufgabe 1: Mechanismus messen | Opus 5.5 | hoch | gemessen: nicht belegt (19 % statt 80 %), Entscheidung beim Anwender |
| Aufgabe 2: Kur K1 mit Prüfungen | Opus 5.5 | hoch | fertig (1221915), Kern 391 |
| Aufgabe 3: Messung B1, B2 | Opus 5.5 | hoch | B1 erfüllt, B2 verfehlt |
| Aufgabe 4: Dokumentation | Sonnet 5.5 | niedrig | fertig |
