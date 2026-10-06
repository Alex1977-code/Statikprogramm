# Teilprojekt 6a, Phase 1: residuenbasierter Fehlerschätzer, h-adaptiv – Umsetzungsplan

> **Für ausführende Agenten:** Pflicht-Skill: superpowers:subagent-driven-development (empfohlen) oder superpowers:executing-plans, Aufgabe für Aufgabe.
> Schritte mit Kästchen (`- [ ]`) zum Abhaken.

**Ziel:** Ein residuenbasierter Fehlerschätzer je Zelle bei einheitlichem p (`fcm/schaetzer.py`), mit Dörfler-Markierung und lokaler Teilung, dessen
Wirksamkeit an Lamé, Kragarm und Kirsch nach vorab festgelegten Regeln gemessen ist.

**Aufbau:** Der Schätzer summiert je Zelle vier Anteile: Zellresiduum f + div σ_h (zweite Ableitungen der Legendre-Basis), Traktionssprünge über die
Zellflächen im Werkstoff (Tensor-Gauß mit Punkttest), Traktionsrest auf der freien und belasteten Oberfläche, Nitsche-Rest auf Verschiebungsrändern.
Das Problem zeichnet dafür seine Flächen- und Volumenlasten auf. Die Verfeinerung nutzt die erzwungenen Teilungen von `Verfeinerung.zellen`.
Grundlage: Entwurf `2026-10-04-tp6a-fehlerschaetzer-hp.md`, Abschnitt 3 (vom Anwender am 04.10.2026 freigegeben, Freigabe dieses Plans folgt mit dem Entwurf).

**Technik:** Python, numpy; Prüfsuiten im Stil von `volumen3d/tests/_pruef.py` (`check`, `lauf`); Aufruf aus `statik3d-volumen3d`:
`.venv/Scripts/python.exe -m volumen3d.tests.<suite>`.

---

## Dateien

| Datei | Aufgabe |
|---|---|
| `packages/volumen3d/volumen3d/fcm/basis.py` | ändern: `legendre_1d_d2`, `basis_3d_hesse` (zweite Ableitungen) |
| `packages/volumen3d/volumen3d/fcm/problem.py` | ändern: `flaechenlasten`, `volumenlasten` aufzeichnen |
| `packages/volumen3d/volumen3d/fcm/schaetzer.py` | neu: `Schaetzung`, `schaetzen`, `flaechen_paare`, `flaechen_punkte`, `energiefehler`, `doerfler`, `verfeinerung_nach` |
| `packages/volumen3d/volumen3d/tests/test_schaetzer.py` | neu: Suite des Schätzers |
| `packages/volumen3d/volumen3d/tests/test_kern.py` | ändern: schnelle Prüfungen eintragen |
| Scratchpad `p1_messung.py` | Messung nach den Regeln (nicht im Paket) |
| `docs/Theoriehandbuch.md` (11.22), `packages/volumen3d/docs/Entwurf.md` (4f), `docs/Volumenmodul.md`, dieser Plan (Ergebnis) | Dokumentation |

---

## Regeln Phase 1, vor der Messung festgelegt (06.10.2026)

**Frage.** Ist der residuenbasierte Schätzer mit Punkttest-Flächen an FCM-Modellen zuverlässig (Effektivitätsindex konstant), trifft er die Zellen mit dem
größten Fehler, und spart h-adaptive Verfeinerung Freiheitsgrade?

**Wahrer Fehler.** ‖e‖_E² = ∫_Ω (σ_h − σ_ref) · D⁻¹ (σ_h − σ_ref) dV über die Werkstoffpunkte der Zellquadratur (`energiefehler`). σ_ref ist bei Lamé die exakte
Lösung; bei Kirsch und Kragarm die Lösung desselben Gitters mit p + 2 (Referenz auf demselben Gitter: ihr Fehler fällt wie h^(p+2) gegen h^p). Ob die Referenz
genügt, zeigt der Vergleich mit p + 1 als Referenz: weicht der Effektivitätsindex mit p + 1 um mehr als 20 % von dem mit p + 2 ab, wird das berichtet und die Regel
an diesem Modell nicht gewertet.

**Folgen.** M1 Lamé (exakt): p 2 und p 3, gleichmäßig h 20, 10, 5. M2 Kirsch (`test_kirsch._platte`, Versatz 0): p 2, Basiszelle 20 mit Verfeinerung am Loch
(`Verfeinerung(bereiche=((Mitte des Lochs auf halber Dicke, D/2 + 10, Ziel),))`) mit Ziel 20 (keine), 10, 5; Referenz p 4 auf demselben Gitter. M3 Kragarm (Quader
L 1000 × B 100 × H 200, links voll eingespannt, rechts Querkraft F 10 000 N als Traktion F/(B·H) in z): p 2, gleichmäßig h 50, 25, 12,5, solange die Referenz p 4 unter
10⁶ Freiheitsgraden bleibt, sonst bis 25.

**Regeln.** (1) Der Effektivitätsindex θ = η / ‖e‖_E schwankt je Modell und p über die Folge höchstens um den Faktor 3 (max θ / min θ ≤ 3). (2) η fällt mit
derselben Rate wie ‖e‖_E: die Steigungen von log η und log ‖e‖_E über log h zwischen erstem und letztem Glied unterscheiden sich um höchstens 0,3. (3) Felder im
Ansatzraum (Patch-Körper: lineares Feld p 2, quadratisches p 2, kubisches p 3) ergeben η / ‖u‖_E < 10⁻⁸ bei p 2 und < 10⁻⁷ bei p 3. Der Entwurf nannte 10⁻⁸ für
alle p; bei p 3 gibt die Zwangsmatrix Polynome aber nur auf etwa 10⁻⁹ wieder (Theorie 11.21, H4), und `test_patch_hoeherer_ordnung` prüft aus diesem Grund die
Spannung bei p 3 gegen 10⁻⁷ (eine Prüfung gleicher Art fiel am 03.10. in der CI mit 1,7·10⁻⁸ gegen 10⁻⁸ durch). Die Schranken sind darum dieselben wie dort,
festgelegt vor jeder Messung des Schätzers. (4) Von den 10 % Zellen mit größtem η liegen mindestens die
Hälfte unter den 20 % Zellen mit größtem wahrem Fehler (Lamé h 10 p 2, Kirsch Ziel 5). (5) h-adaptiv (Dörfler θ = 0,5) ab dem gröbsten Glied erreicht nach drei
Zyklen den wahren Fehler des feinsten gleichmäßigen Glieds (Lamé p 2: h 5) bzw. des feinsten Glieds der Folge (Kirsch: Ziel 5) mit weniger Freiheitsgraden.
(6) Flächenquadratur: η mit Unterteilung tiefe 2 und tiefe 4 unterscheidet sich am feinsten Glied von Lamé und Kirsch um höchstens 10 %; sonst werden die
Flächen eben-exakt integriert (Entwurf 6a, Risiken). Berichtet wird zusätzlich die Zeit von `schaetzen` gegen die Zeit von Aufbau und Lösung.
Wird eine Regel verfehlt, entscheidet der Anwender mit Empfehlung.

---

### Aufgabe 1: zweite Ableitungen der Basis

**Dateien:** ändern `packages/volumen3d/volumen3d/fcm/basis.py`; neu `packages/volumen3d/volumen3d/tests/test_schaetzer.py`

- [ ] **Schritt 1: Prüfung schreiben** (`test_schaetzer.py` neu anlegen)

```python
"""Teilprojekt 6a Phase 1: residuenbasierter Fehlerschaetzer (fcm/schaetzer.py), Plan 2026-10-06-tp6a-phase1-schaetzer.md.

Aufruf: python -m volumen3d.tests.test_schaetzer
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def test_hesse():
    """Hesse-Matrizen der Basis gegen den zentralen Differenzenquotienten der Gradienten; 1D geschlossen: N_j'' = sqrt((2j-1)/2) P'_{j-1}."""
    from volumen3d.fcm.basis import basis_3d, basis_3d_hesse, legendre_1d_d2
    rng = np.random.default_rng(3)
    xi = rng.uniform(-0.9, 0.9, (40, 3))
    for p in (1, 2, 3, 4):
        H = basis_3d_hesse(p, xi)
        d = 1e-5
        fd = np.empty_like(H)
        for b in range(3):
            e = np.zeros(3)
            e[b] = d
            _, dp = basis_3d(p, xi + e)
            _, dm = basis_3d(p, xi - e)
            fd[:, :, :, b] = (dp - dm) / (2 * d)
        rel = float(np.abs(H - fd).max() / max(float(np.abs(H).max()), 1.0))
        check(f"p {p}: Hesse-Matrizen gegen Differenzenquotient der Gradienten ({rel:.1e} < 1e-7), symmetrisch",
              rel < 1e-7 and np.allclose(H, H.transpose(0, 1, 3, 2)))
    x = rng.uniform(-1, 1, 20)
    d2 = legendre_1d_d2(4, x)
    check("1D geschlossen: N_0'' = N_1'' = 0, N_2'' = sqrt(3/2), N_3'' = sqrt(5/2) 3x, N_4'' = sqrt(7/2) (15x^2 - 3)/2",
          not d2[:, :2].any() and np.allclose(d2[:, 2], np.sqrt(1.5)) and np.allclose(d2[:, 3], np.sqrt(2.5) * 3 * x)
          and np.allclose(d2[:, 4], np.sqrt(3.5) * (15 * x ** 2 - 3) / 2))


if __name__ == "__main__":
    sys.exit(lauf([test_hesse]))
```

- [ ] **Schritt 2: fehlschlagen sehen**

Aufruf: `.venv/Scripts/python.exe -m volumen3d.tests.test_schaetzer`
Erwartet: `FEHLER test_hesse laeuft ohne Ausnahme` mit `ImportError: cannot import name 'basis_3d_hesse'`.

- [ ] **Schritt 3: umsetzen** (in `basis.py` vor `gauss_1d` einfügen und `__all__` erweitern)

```python
def legendre_1d_d2(p: int, xi: np.ndarray) -> np.ndarray:
    """Zweite Ableitungen d2N/dxi2 (n,p+1) der 1D-Basis: 0 fuer die linearen Moden, fuer j >= 2 phi_j'' = sqrt((2j-1)/2) P'_{j-1}
    mit P'_k = sum_{i = k-1, k-3, ...} (2i+1) P_i (Fehlerschaetzer: Zellresiduum div sigma, Teilprojekt 6a)."""
    xi = np.asarray(xi, float).ravel()
    d2 = np.zeros((len(xi), p + 1))
    if p >= 2:
        P = L.legvander(xi, p)
        for j in range(2, p + 1):
            k = j - 1
            dPk = np.zeros(len(xi))
            for i in range(k - 1, -1, -2):
                dPk += (2 * i + 1) * P[:, i]
            d2[:, j] = np.sqrt((2 * j - 1) / 2.0) * dPk
    return d2


def basis_3d_hesse(p: int, xi: np.ndarray) -> np.ndarray:
    """Hesse-Matrizen d2N/dxi_a dxi_b (n,m,3,3) in Referenzkoordinaten, Modenordnung wie basis_3d."""
    xi = np.asarray(xi, float).reshape(-1, 3)
    Na, da = legendre_1d(p, xi[:, 0])
    Nb, db = legendre_1d(p, xi[:, 1])
    Nc, dc = legendre_1d(p, xi[:, 2])
    ea, eb, ec = legendre_1d_d2(p, xi[:, 0]), legendre_1d_d2(p, xi[:, 1]), legendre_1d_d2(p, xi[:, 2])
    abc = _indizes(p)
    A, B, C = abc[:, 0], abc[:, 1], abc[:, 2]
    H = np.empty((len(xi), len(abc), 3, 3))
    H[:, :, 0, 0] = ea[:, A] * Nb[:, B] * Nc[:, C]
    H[:, :, 1, 1] = Na[:, A] * eb[:, B] * Nc[:, C]
    H[:, :, 2, 2] = Na[:, A] * Nb[:, B] * ec[:, C]
    H[:, :, 0, 1] = H[:, :, 1, 0] = da[:, A] * db[:, B] * Nc[:, C]
    H[:, :, 0, 2] = H[:, :, 2, 0] = da[:, A] * Nb[:, B] * dc[:, C]
    H[:, :, 1, 2] = H[:, :, 2, 1] = Na[:, A] * db[:, B] * dc[:, C]
    return H
```

`__all__` in `basis.py`: `["legendre_1d", "legendre_1d_d2", "anzahl_moden", "modenklassen", "basis_3d", "basis_3d_hesse", "gauss_1d", "gauss_3d"]`.

- [ ] **Schritt 4: grün sehen** – gleicher Aufruf, erwartet `Ergebnis: 5/5 Pruefungen bestanden`.

- [ ] **Schritt 5: Commit**

```bash
git add packages/volumen3d/volumen3d/fcm/basis.py packages/volumen3d/volumen3d/tests/test_schaetzer.py
git commit -m "volumen3d: 6a Phase 1 - zweite Ableitungen der Legendre-Basis (legendre_1d_d2, basis_3d_hesse)"
```

---

### Aufgabe 2: Lasten aufzeichnen

**Dateien:** ändern `packages/volumen3d/volumen3d/fcm/problem.py`; Prüfung in `test_schaetzer.py`

- [ ] **Schritt 1: Prüfung schreiben** (in `test_schaetzer.py` ergänzen, in die `lauf`-Liste eintragen)

```python
def _wuerfel(p=1, h=50.0):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    return FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(210000.0, 0.3))


def test_lasten_aufgezeichnet():
    """Der Schaetzer braucht die Soll-Traktion je Oberflaechenpunkt und die Volumenlast; das Problem zeichnet sie neben dem Lastvektor auf."""
    pr = _wuerfel()
    pr.druck("q", 5.0)
    pr.volumenlast([0.0, 0.0, -7.85e-5])
    fq, T = pr.flaechenlasten[-1]
    check("druck: aufgezeichnete Traktion = -p n an allen Punkten, Volumenlast aufgezeichnet",
          len(pr.flaechenlasten) == 1 and np.allclose(T, -5.0 * fq.normalen) and len(fq.punkte) == len(pr.oberflaeche.punkte)
          and len(pr.volumenlasten) == 1 and np.allclose(pr.volumenlasten[0], [0.0, 0.0, -7.85e-5]))
```

- [ ] **Schritt 2: fehlschlagen sehen** – erwartet `AttributeError: 'FcmProblem' object has no attribute 'flaechenlasten'`.

- [ ] **Schritt 3: umsetzen** (in `FcmProblem.__init__` nach `self.lasten: list[np.ndarray] = []`)

```python
        # fuer den Fehlerschaetzer (Teilprojekt 6a): Soll-Traktion je Oberflaechenpunkt und konstante Volumenlasten neben dem Lastvektor
        self.flaechenlasten: list[tuple[Flaechenquadratur, np.ndarray]] = []
        self.volumenlasten: list[np.ndarray] = []
```

in `traktion`, die letzte Zeile ersetzen durch

```python
        T = np.asarray(T, float).copy()
        self.lasten.append(rand.flaechenlast(self.gitter, fq, T))
        self.flaechenlasten.append((fq, T))
```

in `volumenlast` ergänzen

```python
    def volumenlast(self, b) -> None:
        self.lasten.append(rand.volumenlast(self.gitter, self.quadratur, np.asarray(b, float)))
        self.volumenlasten.append(np.asarray(b, float).reshape(3).copy())
```

- [ ] **Schritt 4: grün sehen** – erwartet `Ergebnis: 6/6 Pruefungen bestanden`.

- [ ] **Schritt 5: Commit** – `git commit -m "volumen3d: 6a Phase 1 - FcmProblem zeichnet Flaechen- und Volumenlasten fuer den Fehlerschaetzer auf"`

---

### Aufgabe 3: Zellflächen zwischen aktiven Zellen und ihre Werkstoffpunkte

**Dateien:** neu `packages/volumen3d/volumen3d/fcm/schaetzer.py`; Prüfungen in `test_schaetzer.py`

- [ ] **Schritt 1: Prüfungen schreiben**

```python
def test_flaechen_paare():
    """Jede Flaeche zwischen zwei aktiven Zellen genau einmal, von der feineren Zelle aus; unabhaengige Gegenprobe ueber die Zellboxen (alle Paare mit
    gemeinsamer Flaeche positiven Inhalts)."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.schaetzer import flaechen_paare
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    pr = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3), verfeinerung=Verfeinerung(bereiche=((np.zeros(3), 30.0, 12.5),)))
    G = pr.gitter
    paare = flaechen_paare(G)
    lo, hi = G.zellbox(np.arange(len(G.ijk)))
    tol = 1e-9 * G.h
    brute = set()
    for c in range(len(G.ijk)):
        for k in range(c + 1, len(G.ijk)):
            for a in range(3):
                b, d = [x for x in range(3) if x != a]
                beruehrt = abs(hi[c, a] - lo[k, a]) < tol or abs(hi[k, a] - lo[c, a]) < tol
                ueber = all(min(hi[c, x], hi[k, x]) - max(lo[c, x], lo[k, x]) > tol for x in (b, d))
                if beruehrt and ueber:
                    brute.add((c, k))
    gefunden = {(min(c, k), max(c, k)) for c, k, _, _ in paare}
    feiner = all(G.ebene[c] >= G.ebene[k] for c, k, _, _ in paare)
    check(f"flaechen_paare: {len(paare)} Paare, gleich der Gegenprobe ueber die Boxen ({len(brute)}), keine doppelt, immer von der feineren Zelle aus",
          gefunden == brute and len(paare) == len(gefunden) and feiner and len(set(G.ebene)) > 1)


def test_flaechen_punkte():
    """Werkstoffanteil einer Zellflaeche: ganz im Werkstoff exakt die Flaeche; schraeg geschnitten auf erste Ordnung gegen das exakt geclippte Polygon."""
    from volumen3d.fcm.schaetzer import flaechen_paare, flaechen_punkte
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.polyeder import polygon_clippen
    pkt, nrm = np.array([50.0, 50.0, 50.0]), np.array([1.0, 0.5, 0.0])
    g = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"},
                                                         {"typ": "halbraum", "punkt": list(pkt), "normale": list(nrm), "name": "s"}]}})
    G = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3)).gitter
    voll = schraeg = 0
    fehler = 0.0
    for c, k, achse, seite in flaechen_paare(G):
        lo, hi = G.zellbox(int(c))
        a, b = [d for d in range(3) if d != achse]
        flaeche = (hi[a] - lo[a]) * (hi[b] - lo[b])
        ebene = hi[achse] if seite > 0 else lo[achse]
        ecken = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        Q = np.empty((4, 3))
        Q[:, achse] = ebene
        Q[:, a] = lo[a] + ecken[:, 0] * (hi[a] - lo[a])
        Q[:, b] = lo[b] + ecken[:, 1] * (hi[b] - lo[b])
        # exakter Werkstoffanteil: Flaeche gegen den Halbraum und die sechs Quaderseiten clippen (polygon_clippen behaelt (x - p).n <= 0)
        R, _ = polygon_clippen(Q, pkt, nrm / np.linalg.norm(nrm), 1e-12)
        for x0, n0 in ((np.array([0.0, 0, 0]), np.array([-1.0, 0, 0])), (np.array([100.0, 0, 0]), np.array([1.0, 0, 0])),
                       (np.array([0.0, 0, 0]), np.array([0, -1.0, 0])), (np.array([0, 100.0, 0]), np.array([0, 1.0, 0])),
                       (np.array([0, 0, 0.0]), np.array([0, 0, -1.0])), (np.array([0, 0, 100.0]), np.array([0, 0, 1.0]))):
            if len(R) >= 3:
                R, _ = polygon_clippen(R, x0, n0, 1e-12)
        exakt = 0.5 * float(np.linalg.norm(np.cross(R[1:-1] - R[0], R[2:] - R[0]).sum(axis=0))) if len(R) >= 3 else 0.0
        P, W = flaechen_punkte(G, c, achse, seite, 2, tiefe=2)
        if abs(exakt - flaeche) < 1e-9 * flaeche:
            voll += 1
            fehler_voll = abs(float(W.sum()) - flaeche) / flaeche
            fehler = max(fehler, fehler_voll)
        elif exakt > 0:
            # erste Ordnung: eine Gerade schneidet hoechstens 2 * 2^tiefe der 2^tiefe x 2^tiefe Unterquadrate, jedes irrt hoechstens um seine Flaeche
            schraeg += 1
            if abs(float(W.sum()) - exakt) > 2.0 * flaeche / 2 ** 2:
                fehler = max(fehler, 1.0)
    check(f"flaechen_punkte: {voll} Flaechen ganz im Werkstoff exakt ({fehler:.1e} < 1e-12), {schraeg} geschnittene innerhalb der Schranke erster Ordnung",
          voll > 0 and schraeg > 0 and fehler < 1e-12)
```

- [ ] **Schritt 2: fehlschlagen sehen** – erwartet `ModuleNotFoundError: No module named 'volumen3d.fcm.schaetzer'`.

- [ ] **Schritt 3: umsetzen** (`schaetzer.py` neu, erster Teil)

```python
"""Residuenbasierter Fehlerschaetzer je Zelle (Teilprojekt 6a, Phase 1; Vorgabe 8.4; Plan 2026-10-06-tp6a-phase1-schaetzer.md).

eta_K^2 = (1/E) [ (h/p)^2 ||f + div sigma_h||^2_{K cap Omega} + 1/2 sum_F (h_F/p) ||[sigma_h n]||^2_{F cap Omega} + (h/p) ||t - sigma_h n||^2_{Gamma_N cap K} ]
          + E (p^2/h) ||P (u_h - g)||^2_{Gamma_D cap K}

Einheit N mm (Energie). Die Flaechen zwischen Zellen werden mit Tensor-Gauss je Unterquadrat (2^tiefe x 2^tiefe) und Punkttest integriert (erste Ordnung in der
Geometrie, Entwurf 6a Abschnitt 3). Freie Oberflaeche sind alle Oberflaechenpunkte ausser denen eines Verschiebungsrands (Zuordnung ueber die Koordinaten:
die Raender sind Auswahlen der Oberflaechenquadratur); ihre Soll-Traktion kommt aus den aufgezeichneten Flaechenlasten, sonst null.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np

from .basis import basis_3d, basis_3d_hesse, gauss_1d
from .elastizitaet import b_matrizen, d_matrix, lame
from .rand import _zellweise, nn_matrizen

ANTEILE = ("residuum", "sprung", "neumann", "dirichlet")


def flaechen_paare(gitter) -> np.ndarray:
    """(k,4): Zelle c, Nachbar n, Achse, Seite (+1/-1) je Flaeche zwischen zwei aktiven Zellen. Jede Flaeche einmal: von der feineren Zelle aus, bei gleicher
    Ebene von der mit dem kleineren Index. Nachbar ueber einen Probepunkt knapp jenseits der Flaechenmitte (an einer feineren Nachbarflaeche liegt er auf einer
    Kante der feinen Zellen; welche gefunden wird, ist gleich, sie ist feiner und wird uebersprungen)."""
    nz = len(gitter.ijk)
    lo, hi = gitter.zellbox(np.arange(nz))
    m = 0.5 * (lo + hi)
    hl = 0.5 * (hi - lo)[:, 0]
    c = np.arange(nz)
    teile = []
    for achse in range(3):
        for seite in (-1, 1):
            P = m.copy()
            P[:, achse] += seite * hl * (1.0 + 1e-6)
            nb = gitter.zelle_finden(P)
            ok = (nb >= 0) & (nb != c)
            nbs = np.where(ok, nb, 0)
            ok &= gitter.ebene[nbs] <= gitter.ebene[c]
            ok &= ~((gitter.ebene[nbs] == gitter.ebene[c]) & (nbs < c))
            k = int(ok.sum())
            teile.append(np.stack([c[ok], nb[ok], np.full(k, achse), np.full(k, seite)], axis=1))
    return np.concatenate(teile).astype(int) if teile else np.zeros((0, 4), int)


def flaechen_punkte(gitter, c: int, achse: int, seite: int, n_gauss: int, tiefe: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Werkstoffpunkte (q,3) und Gewichte (q,) auf der Flaeche (achse, seite) der Zelle c: 2^tiefe x 2^tiefe Unterquadrate mit n_gauss x n_gauss Gauss-Punkten,
    Punkttest gegen die Geometrie."""
    lo, hi = gitter.zellbox(int(c))
    a, b = [d for d in range(3) if d != achse]
    k = 2 ** int(tiefe)
    x, w = gauss_1d(int(n_gauss))
    t = ((np.arange(k)[:, None] + 0.5 * (x[None, :] + 1.0)) / k).ravel()
    wt = np.tile(w, k) / (2.0 * k)
    A, B = np.meshgrid(t, t, indexing="ij")
    WA, WB = np.meshgrid(wt, wt, indexing="ij")
    P = np.empty((A.size, 3))
    P[:, achse] = hi[achse] if seite > 0 else lo[achse]
    P[:, a] = lo[a] + A.ravel() * (hi[a] - lo[a])
    P[:, b] = lo[b] + B.ravel() * (hi[b] - lo[b])
    W = (WA * WB).ravel() * (hi[a] - lo[a]) * (hi[b] - lo[b])
    innen = np.asarray(gitter.geometrie.innen(P), bool)
    return P[innen], W[innen]
```

- [ ] **Schritt 4: grün sehen** – erwartet `Ergebnis: 8/8 Pruefungen bestanden`.

- [ ] **Schritt 5: Commit** – `git commit -m "volumen3d: 6a Phase 1 - Zellflaechen zwischen aktiven Zellen und ihre Werkstoffpunkte (flaechen_paare, flaechen_punkte)"`

---

### Aufgabe 4: Schätzer, wahrer Energiefehler

**Dateien:** ändern `schaetzer.py`; Prüfungen in `test_schaetzer.py`

- [ ] **Schritt 1: Prüfungen schreiben**

```python
def _energie(pr, sig):
    from volumen3d.fcm.schaetzer import energiefehler
    return energiefehler(pr, np.zeros(pr.gitter.n_dof), sig)[1]


def test_konsistenz():
    """Felder im Ansatzraum ergeben eta auf Rundungsniveau (Regel 3): Zellresiduum, Spruenge und Randreste verschwinden fuer die exakte Loesung. Schranken wie
    test_patch_hoeherer_ordnung: 1e-8 bei p 2, 1e-7 bei p 3 (die Zwangsmatrix gibt Polynome bei p 3 nur auf rund 1e-9 wieder, Theorie 11.21 H4)."""
    from volumen3d.fcm.schaetzer import schaetzen
    from volumen3d.tests import test_patch as T
    pr = T._problem(2, 1e-8)
    s0 = T.sigma_exakt()
    U = pr.loesen({"alles": T.u_exakt})[:, 0]
    eta = schaetzen(pr, U, {"alles": T.u_exakt}).gesamt
    ref = _energie(pr, lambda P: np.broadcast_to(s0, (len(P), 6)))
    check(f"Patch-Koerper p 2, lineares Feld: eta / ||u||_E = {eta / ref:.1e} (< 1e-8)", eta / ref < 1e-8)
    for p, k in ((2, 2), (3, 3)):
        u, sig, f, _ = T._polynomfeld(k)
        _, _, pr = T._polynomfehler(p, k)
        U = pr.loesen({"alles": u}, zusatzlasten=[T._lastvektor(pr, f)])[:, 0]
        eta = schaetzen(pr, U, {"alles": u}, volumenlast=f).gesamt
        ref = _energie(pr, sig)
        schranke = 1e-8 if p == 2 else 1e-7
        check(f"Patch-Koerper p {p}, Feld vom Grad {k} mit Volumenlast: eta / ||u||_E = {eta / ref:.1e} (< {schranke:.0e})", eta / ref < schranke)


def _lame_sigma(P):
    from volumen3d.tests import test_lame as L
    P = np.asarray(P, float).reshape(-1, 3)
    r = np.hypot(P[:, 0], P[:, 1])
    c, s = P[:, 0] / r, P[:, 1] / r
    sr, sphi = L._lame(r)
    o = np.zeros(len(P))
    return np.stack([sr * c * c + sphi * s * s, sr * s * s + sphi * c * c, L.NU * (sr + sphi), (sr - sphi) * s * c, o, o], axis=1)


def test_lame():
    """Lame p 2, h 20 und h 10: eta faellt, Effektivitaetsindex gegen die exakte Loesung in [0,1; 10] und zwischen beiden Gittern um hoechstens den Faktor 3."""
    from volumen3d.fcm.schaetzer import energiefehler, schaetzen
    from volumen3d.tests import test_lame as L
    werte = []
    for h in (20.0, 10.0):
        pr, aus = L._rechnen(2, h)
        eta = schaetzen(pr, aus.U).gesamt
        e = energiefehler(pr, aus.U, _lame_sigma)[1]
        werte.append((h, eta, e, eta / e))
    (_, eta1, e1, t1), (_, eta2, e2, t2) = werte
    check(f"Lame p 2: eta {eta1:.3e} -> {eta2:.3e}, ||e||_E {e1:.3e} -> {e2:.3e}, Effektivitaet {t1:.2f} / {t2:.2f}",
          eta2 < eta1 and e2 < e1 and all(0.1 < t < 10.0 for t in (t1, t2)) and max(t1, t2) / min(t1, t2) < 3.0)
```

- [ ] **Schritt 2: fehlschlagen sehen** – erwartet `ImportError: cannot import name 'schaetzen'`.

- [ ] **Schritt 3: umsetzen** (in `schaetzer.py` anfügen)

```python
@dataclass
class Schaetzung:
    """eta^2 je Anteil (ANTEILE) und Zelle, Einheit N mm."""
    eta2: dict

    @property
    def zelle(self) -> np.ndarray:
        return np.sqrt(sum(self.eta2[k] for k in ANTEILE))

    @property
    def gesamt(self) -> float:
        return float(np.sqrt(sum(float(self.eta2[k].sum()) for k in ANTEILE)))


def _koeff(problem, U, c: int) -> np.ndarray:
    """Modenkoeffizienten (m,3) der Zelle c."""
    return U[problem.gitter.zell_dofs(c)].reshape(-1, 3)


def _spannung(problem, D, c: int, xi, Uc) -> np.ndarray:
    g = problem.gitter
    _, dN = basis_3d(g.p, xi)
    eps = np.einsum("qsd,d->qs", b_matrizen(dN * (2.0 / float(g.h_zelle(c)))), Uc.ravel())
    return eps @ D.T


def _traktion(s, n) -> np.ndarray:
    return np.einsum("qab,qb->qa", nn_matrizen(n), s)


def _residuum(problem, U, f, lam, mu, eta2) -> None:
    g, q = problem.gitter, problem.quadratur
    E, p = problem.werkstoff.E, g.p
    for c in range(len(g.ijk)):
        P, W, I = q.zelle(c)
        if len(P) == 0 or not I.any():
            continue
        Pm, Wm = P[I], W[I]
        h = float(g.h_zelle(c))
        H = basis_3d_hesse(p, g.lokal(Pm, np.full(len(Pm), c))) * (2.0 / h) ** 2
        d2u = np.einsum("qkij,ka->qaij", H, _koeff(problem, U, c))
        r = mu * np.einsum("qajj->qa", d2u) + (lam + mu) * np.einsum("qbab->qa", d2u) + f(Pm)
        eta2["residuum"][c] += (h / p) ** 2 / E * float((Wm * (r * r).sum(axis=1)).sum())


def _spruenge(problem, U, D, eta2, tiefe: int) -> None:
    g = problem.gitter
    E, p = problem.werkstoff.E, g.p
    for c, k, achse, seite in flaechen_paare(g):
        P, W = flaechen_punkte(g, c, achse, seite, p + 1, tiefe)
        if len(P) == 0:
            continue
        n = np.zeros((len(P), 3))
        n[:, achse] = seite
        s_c = _spannung(problem, D, c, g.lokal(P, np.full(len(P), c)), _koeff(problem, U, c))
        s_k = _spannung(problem, D, k, g.lokal(P, np.full(len(P), k)), _koeff(problem, U, k))
        j = _traktion(s_c - s_k, n)
        beitrag = 0.5 * (float(g.h_zelle(c)) / p) / E * float((W * (j * j).sum(axis=1)).sum())
        eta2["sprung"][c] += beitrag
        eta2["sprung"][k] += beitrag


def _randwerte(problem, U, D, fq):
    """u_h (q,3) und Traktion sigma_h n (q,3) an den Punkten einer Flaechenquadratur."""
    u = np.zeros((len(fq.punkte), 3))
    t = np.zeros((len(fq.punkte), 3))
    for c, idx, N, G in _zellweise(problem.gitter, fq):
        Uc = _koeff(problem, U, c)
        u[idx] = N @ Uc
        s = np.einsum("qsd,d->qs", b_matrizen(G), Uc.ravel()) @ D.T
        t[idx] = _traktion(s, fq.normalen[idx])
    return u, t


def _rand(problem, U, D, vorgaben, eta2) -> None:
    g = problem.gitter
    E, p = problem.werkstoff.E, g.p
    fq = problem.oberflaeche
    index = {fq.punkte[i].tobytes(): i for i in range(len(fq.punkte))}
    t_soll = np.zeros((len(fq.punkte), 3))
    for fql, T in problem.flaechenlasten:
        for i, P in enumerate(fql.punkte):
            j = index.get(P.tobytes())
            if j is not None:
                t_soll[j] += T[i]
    frei = np.ones(len(fq.punkte), bool)
    for r in problem.raender.values():
        for P in r.quadratur.punkte:
            j = index.get(P.tobytes())
            if j is not None:
                frei[j] = False
    hk = g.h_zelle(fq.zelle)
    # freie und belastete Oberflaeche: t - sigma_h n
    if frei.any():
        fr = fq.auswahl(frei)
        _, t = _randwerte(problem, U, D, fr)
        res = t_soll[frei] - t
        np.add.at(eta2["neumann"], fr.zelle, (hk[frei] / p) / E * fr.gewichte * (res * res).sum(axis=1))
    # Verschiebungsraender: Nitsche-Rest, bei 'normal' und 'schnitt' zusaetzlich der tangentiale Traktionsrest. An einer Schnittebene sind die drei
    # In-Ebene-Starrkoerpermoden (Querkraft, Torsion) als Mittelwertzwaenge gehalten: ihr Anteil an der Tangentialtraktion ist Reaktion und kein Fehler,
    # er wird durch L2-Projektion auf die Moden abgezogen
    for name, r in problem.raender.items():
        rq = r.quadratur
        gv = (vorgaben or {}).get(name, 0.0)
        G = np.asarray(gv(rq.punkte) if callable(gv) else np.broadcast_to(np.asarray(gv, float), (len(rq.punkte), 3)), float)
        u, t = _randwerte(problem, U, D, rq)
        h_r = g.h_zelle(rq.zelle)
        n = rq.normalen
        d = u - G
        if r.projektion != "voll":
            d = n * (d * n).sum(axis=1, keepdims=True)
            tt = t - n * (t * n).sum(axis=1, keepdims=True)
            if r.projektion == "schnitt":
                M = r.moden                                                          # (q,3,3) [Punkt, Mode, Komponente]
                gram = np.einsum("q,qka,qla->kl", rq.gewichte, M, M)
                koeff = np.linalg.solve(gram, np.einsum("q,qka,qa->k", rq.gewichte, M, tt))
                tt = tt - np.einsum("k,qka->qa", koeff, M)
            np.add.at(eta2["neumann"], rq.zelle, (h_r / p) / E * rq.gewichte * (tt * tt).sum(axis=1))
        np.add.at(eta2["dirichlet"], rq.zelle, E * p ** 2 / h_r * rq.gewichte * (d * d).sum(axis=1))


def schaetzen(problem, U, vorgaben=None, volumenlast=None, tiefe: int = 2) -> Schaetzung:
    """Residuenbasierter Schaetzer je Zelle fuer die Loesung U (n_dof,). vorgaben wie FcmProblem.loesen (Randname -> g); volumenlast f(P) -> (q,3) in N/mm3
    zusaetzlich zu den mit FcmProblem.volumenlast gesetzten konstanten Lasten; tiefe: Unterteilung der Zellflaechen."""
    U = np.asarray(U, float).ravel()
    nz = len(problem.gitter.ijk)
    eta2 = {k: np.zeros(nz) for k in ANTEILE}
    E, nu = problem.werkstoff.E, problem.werkstoff.nu
    D = d_matrix(E, nu)
    lam, mu = lame(E, nu)
    b = np.sum(problem.volumenlasten, axis=0) if problem.volumenlasten else np.zeros(3)

    def f(P):
        aus = np.broadcast_to(b, (len(P), 3)).copy()
        return aus + (np.asarray(volumenlast(P), float).reshape(-1, 3) if volumenlast is not None else 0.0)
    _residuum(problem, U, f, lam, mu, eta2)
    _spruenge(problem, U, D, eta2, tiefe)
    _rand(problem, U, D, vorgaben, eta2)
    return Schaetzung(eta2)


def energiefehler(problem, U, sigma_ref) -> tuple[np.ndarray, float]:
    """(e^2 je Zelle (nz,), ||e||_E) mit ||e||_E^2 = int (sigma_h - sigma_ref) . D^-1 (sigma_h - sigma_ref) dV ueber die Werkstoffpunkte der Zellquadratur;
    sigma_ref: P (q,3) -> (q,6) Voigt. Mit U = 0 die Energienorm des Referenzfelds."""
    g, q = problem.gitter, problem.quadratur
    D = d_matrix(problem.werkstoff.E, problem.werkstoff.nu)
    C = np.linalg.inv(D)
    U = np.asarray(U, float).ravel()
    e2 = np.zeros(len(g.ijk))
    for c in range(len(g.ijk)):
        P, W, I = q.zelle(c)
        if len(P) == 0 or not I.any():
            continue
        Pm, Wm = P[I], W[I]
        s = _spannung(problem, D, c, g.lokal(Pm, np.full(len(Pm), c)), _koeff(problem, U, c)) - np.asarray(sigma_ref(Pm), float).reshape(-1, 6)
        e2[c] = float((Wm * np.einsum("qi,ij,qj->q", s, C, s)).sum())
    return e2, float(np.sqrt(e2.sum()))
```

- [ ] **Schritt 4: grün sehen** – erwartet `Ergebnis: 12/12 Pruefungen bestanden` (die Lamé-Prüfung braucht einige zehn Sekunden).

- [ ] **Schritt 5: Commit** – `git commit -m "volumen3d: 6a Phase 1 - residuenbasierter Schaetzer je Zelle und wahrer Energiefehler (schaetzen, energiefehler)"`

---

### Aufgabe 5: Markieren und lokal teilen

**Dateien:** ändern `schaetzer.py`; Prüfungen in `test_schaetzer.py`

- [ ] **Schritt 1: Prüfungen schreiben**

```python
def test_doerfler():
    """Doerfler: kleinste Menge der groessten Indikatoren, deren Summe mindestens theta der Gesamtsumme traegt."""
    from volumen3d.fcm.schaetzer import doerfler
    check("Doerfler theta 0,5 auf [1, 4, 2, 3]: Zellen 1 und 3 (4 + 3 >= 5); theta 1: alle; leer bei Summe 0",
          list(doerfler(np.array([1.0, 4.0, 2.0, 3.0]), 0.5)) == [1, 3] and list(doerfler(np.array([1.0, 4.0, 2.0, 3.0]), 1.0)) == [0, 1, 2, 3]
          and len(doerfler(np.zeros(3), 0.5)) == 0)


def test_verfeinerung_nach():
    """Die markierte Zelle wird geteilt: im neuen Gitter liegen in ihrer Box acht Blaetter der naechsten Ebene. Eine Zelle ganz im Werkstoff, damit kein Kind
    als OUTSIDE wegfaellt."""
    from volumen3d.fcm.gitter import INSIDE
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.fcm.schaetzer import verfeinerung_nach
    pr = _wuerfel(p=1, h=50.0)
    c = int(np.flatnonzero((pr.gitter.ebene == 0) & (pr.gitter.klasse == INSIDE))[0])
    lo, hi = pr.gitter.zellbox(c)
    v = verfeinerung_nach(pr.gitter, pr.verfeinerung, [c])
    G2 = FcmProblem(pr.geometrie, h=50.0, p=1, werkstoff=Werkstoff(210000.0, 0.3), verfeinerung=v).gitter
    m = 0.5 * (G2.zellbox(np.arange(len(G2.ijk)))[0] + G2.zellbox(np.arange(len(G2.ijk)))[1])
    drin = np.flatnonzero(((m > lo) & (m < hi)).all(axis=1))
    check(f"verfeinerung_nach: Zelle {c} geteilt, {len(drin)} Blaetter der Ebene 1 in ihrer Box", len(drin) == 8 and (G2.ebene[drin] == 1).all())
```

- [ ] **Schritt 2: fehlschlagen sehen** – erwartet `ImportError: cannot import name 'doerfler'`.

- [ ] **Schritt 3: umsetzen** (in `schaetzer.py` anfügen und `__all__` setzen)

```python
def doerfler(eta2_zelle, theta: float = 0.5) -> np.ndarray:
    """Indizes (aufsteigend) der kleinsten Menge von Zellen mit den groessten eta^2, deren Summe mindestens theta der Gesamtsumme ist."""
    eta2 = np.asarray(eta2_zelle, float).ravel()
    summe = float(eta2.sum())
    if summe <= 0.0:
        return np.zeros(0, int)
    ordnung = np.argsort(eta2)[::-1]
    k = int(np.searchsorted(np.cumsum(eta2[ordnung]), theta * summe * (1.0 - 1e-12))) + 1
    return np.sort(ordnung[:k])


def verfeinerung_nach(gitter, verfeinerung, zellen):
    """Verfeinerung mit den genannten Zellen als erzwungene Teilungen (ebene, i, j, k) zusaetzlich zu den bisherigen."""
    neu = tuple((int(gitter.ebene[c]), int(gitter.ijk[c, 0]), int(gitter.ijk[c, 1]), int(gitter.ijk[c, 2])) for c in zellen)
    return dataclasses.replace(verfeinerung, zellen=tuple(verfeinerung.zellen) + neu)


__all__ = ["ANTEILE", "Schaetzung", "schaetzen", "energiefehler", "flaechen_paare", "flaechen_punkte", "doerfler", "verfeinerung_nach"]
```

- [ ] **Schritt 4: grün sehen** – erwartet `Ergebnis: 14/14 Pruefungen bestanden`.

- [ ] **Schritt 5: Kernsuite** – in `test_kern.py` den Import um `test_schaetzer` erweitern und `test_schaetzer.test_hesse, test_schaetzer.test_lasten_aufgezeichnet,
  test_schaetzer.test_flaechen_paare, test_schaetzer.test_flaechen_punkte, test_schaetzer.test_konsistenz, test_schaetzer.test_doerfler,
  test_schaetzer.test_verfeinerung_nach` in `TESTS` aufnehmen (die Lamé-Prüfung bleibt nur in der eigenen Suite). Aufruf
  `.venv/Scripts/python.exe -m volumen3d.tests.test_kern`, erwartet alle Prüfungen grün.

- [ ] **Schritt 6: Commit** – `git commit -m "volumen3d: 6a Phase 1 - Doerfler-Markierung und lokale Teilung (doerfler, verfeinerung_nach), Kernsuite"`

---

### Aufgabe 6: Messung nach den Regeln

**Dateien:** Scratchpad `p1_messung.py` (nicht im Paket); Ergebnis in diesem Plan

- [ ] **Schritt 1: Messprogramm schreiben** (Scratchpad; ein Modell je Aufruf, Ausgabe je Glied eine Zeile JSON mit Präfix `P1`)

```python
"""6a Phase 1: Messung nach den Regeln im Plan 2026-10-06-tp6a-phase1-schaetzer.md. Aufruf: python p1_messung.py <lame|kirsch|kragarm|adaptiv|tiefe>"""
import json
import sys
import time

import numpy as np

from volumen3d.fcm.gitter import Verfeinerung
from volumen3d.fcm.problem import FcmProblem, Werkstoff
from volumen3d.fcm.schaetzer import doerfler, energiefehler, schaetzen, verfeinerung_nach
from volumen3d.geometry.csg import aus_params
from volumen3d.tests import test_kirsch as K, test_lame as L
from volumen3d.tests.test_schaetzer import _lame_sigma

E, NU = 210000.0, 0.3


def zeile(**kw):
    print("P1 " + json.dumps(kw), flush=True)


def glied(modell, pr, U, vorgaben, sigma_ref, t_bau, extra=None):
    t0 = time.perf_counter()
    s = schaetzen(pr, U, vorgaben)
    t_s = time.perf_counter() - t0
    e2, e = energiefehler(pr, U, sigma_ref)
    eta_z = s.zelle
    top_eta = set(np.argsort(eta_z)[::-1][:max(1, len(eta_z) // 10)])
    top_e = set(np.argsort(e2)[::-1][:max(1, len(e2) // 5)])
    zeile(modell=modell, h=pr.gitter.h, p=pr.p, fhg=int(3 * pr.zwaenge.statistik["moden_frei"]), eta=s.gesamt, e=e, theta=s.gesamt / e,
          anteile={k: float(np.sqrt(v.sum())) for k, v in s.eta2.items()}, treffer=len(top_eta & top_e) / len(top_eta),
          t_schaetzen=round(t_s, 2), t_bau_loesen=round(t_bau, 2), **(extra or {}))


def lame():
    for p in (2, 3):
        for h in (20.0, 10.0, 5.0):
            t0 = time.perf_counter()
            pr, aus = L._rechnen(p, h)
            glied("Lame", pr, aus.U, {}, _lame_sigma, time.perf_counter() - t0)


def kirsch_problem(p, ziel):
    v = Verfeinerung(bereiche=((np.array([0.0, 0.0, K.T / 2]), K.D / 2 + 10.0, ziel),)) if ziel < 20.0 else None
    return K._platte(p, 20.0, versatz=0.0, verfeinerung=v)


def kirsch():
    for ziel in (20.0, 10.0, 5.0):
        t0 = time.perf_counter()
        pr = kirsch_problem(2, ziel)
        U = pr.loesen({})[:, 0]
        t_bau = time.perf_counter() - t0
        refs = {}
        for pref in (3, 4):
            prr = K._platte(pref, 20.0, versatz=0.0, verfeinerung=pr.verfeinerung)
            Ur = prr.loesen({})[:, 0]
            refs[pref] = (prr, Ur)
        theta3 = schaetzen(pr, U).gesamt / energiefehler(pr, U, lambda P: refs[3][0].auswertung(refs[3][1]).spannung(P))[1]
        glied("Kirsch", pr, U, {}, lambda P: refs[4][0].auswertung(refs[4][1]).spannung(P), t_bau, {"ziel": ziel, "theta_ref_p3": theta3})


def kragarm_problem(p, h):
    g = aus_params({"csg": {"typ": "quader", "min": [0, -50, -100], "max": [1000, 50, 100], "name": "balken"}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), polster=0.13)
    fq = pr.oberflaeche
    links = pr.oberflaeche.auswahl(np.abs(fq.punkte[:, 0]) < 1e-6)
    rechts = pr.oberflaeche.auswahl(np.abs(fq.punkte[:, 0] - 1000.0) < 1e-6)
    pr.verschiebungsrand("links", None, projektion="voll", quadratur=links)
    pr.traktion(None, np.array([0.0, 0.0, 10000.0 / (100.0 * 200.0)]), quadratur=rechts)
    return pr


def kragarm():
    for h in (50.0, 25.0, 12.5):
        t0 = time.perf_counter()
        pr = kragarm_problem(2, h)
        U = pr.loesen({})[:, 0]
        t_bau = time.perf_counter() - t0
        prr = kragarm_problem(4, h)
        if prr.gitter.n_dof > 1_000_000:
            zeile(modell="Kragarm", h=h, uebersprungen=f"Referenz p 4 mit {prr.gitter.n_dof} Freiheitsgraden")
            break
        Ur = prr.loesen({})[:, 0]
        pr3 = kragarm_problem(3, h)
        U3 = pr3.loesen({})[:, 0]
        theta3 = schaetzen(pr, U).gesamt / energiefehler(pr, U, lambda P: pr3.auswertung(U3).spannung(P))[1]
        glied("Kragarm", pr, U, {}, lambda P: prr.auswertung(Ur).spannung(P), t_bau, {"theta_ref_p3": theta3})


def adaptiv():
    # Lame p 2 ab h 20, drei Zyklen Doerfler 0,5
    pr, aus = L._rechnen(2, 20.0)
    for zyklus in range(4):
        s = schaetzen(pr, aus.U)
        zeile(modell="Lame adaptiv", zyklus=zyklus, fhg=int(3 * pr.zwaenge.statistik["moden_frei"]), eta=s.gesamt,
              e=energiefehler(pr, aus.U, _lame_sigma)[1])
        if zyklus == 3:
            break
        v = verfeinerung_nach(pr.gitter, pr.verfeinerung, doerfler(s.zelle ** 2, 0.5))
        pr = FcmProblem(L._geometrie(), h=20.0, p=2, werkstoff=Werkstoff(L.E, L.NU), verfeinerung=v)
        for n in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
            pr.verschiebungsrand(n, n, projektion="normal")
        pr.druck("innen", L.PI)
        aus = pr.auswertung(pr.loesen({})[:, 0])
    # Kirsch p 2 ab Basis 20 ohne Verfeinerung, drei Zyklen; Referenz p 4 auf dem jeweiligen Gitter
    pr = kirsch_problem(2, 20.0)
    for zyklus in range(4):
        U = pr.loesen({})[:, 0]
        prr = K._platte(4, 20.0, versatz=0.0, verfeinerung=pr.verfeinerung)
        Ur = prr.loesen({})[:, 0]
        s = schaetzen(pr, U)
        zeile(modell="Kirsch adaptiv", zyklus=zyklus, fhg=int(3 * pr.zwaenge.statistik["moden_frei"]), eta=s.gesamt,
              e=energiefehler(pr, U, lambda P: prr.auswertung(Ur).spannung(P))[1])
        if zyklus == 3:
            break
        v = verfeinerung_nach(pr.gitter, pr.verfeinerung, doerfler(s.zelle ** 2, 0.5))
        pr = K._platte(2, 20.0, versatz=0.0, verfeinerung=v)


def tiefe():
    pr, aus = L._rechnen(2, 5.0)
    zeile(modell="Lame h 5 p 2", tiefe2=schaetzen(pr, aus.U, tiefe=2).gesamt, tiefe4=schaetzen(pr, aus.U, tiefe=4).gesamt)
    pr = kirsch_problem(2, 5.0)
    U = pr.loesen({})[:, 0]
    zeile(modell="Kirsch Ziel 5 p 2", tiefe2=schaetzen(pr, U, tiefe=2).gesamt, tiefe4=schaetzen(pr, U, tiefe=4).gesamt)


if __name__ == "__main__":
    {"lame": lame, "kirsch": kirsch, "kragarm": kragarm, "adaptiv": adaptiv, "tiefe": tiefe}[sys.argv[1]]()
```

- [ ] **Schritt 2: Messung laufen lassen** – aus einem festen Arbeitsbaum auf dem Commit von Aufgabe 5 (`git worktree add --detach <scratchpad>/p1_fest <commit>`),
  nacheinander, schwere Läufe der Hauptsitzung vorher ankündigen: `lame`, `kirsch`, `kragarm`, `adaptiv`, `tiefe`; Ausgaben nach `p1_<teil>.log`.

- [ ] **Schritt 3: auswerten** – je Regel (1) bis (6) das Urteil aus den Zeilen `P1` (Effektivität max/min, Steigungen log η und log e über log h, Treffer,
  adaptiv gegen gleichmäßig, tiefe 2 gegen 4) mit einem zweiten, unabhängig geschriebenen Auswerteskript gegenprüfen (Übereinstimmung der Urteile).

- [ ] **Schritt 4: Ergebnis eintragen** – Abschnitt „Ergebnis Phase 1“ unten in diesem Plan; verfehlte Regel mit Empfehlung an den Anwender.

---

### Aufgabe 7: Dokumentation und Abschluss

- [ ] **Schritt 1:** `docs/Theoriehandbuch.md` neuer Abschnitt 11.22 „Teilprojekt 6a: residuenbasierter Fehlerschätzer“: Formel, Anteile, Flächenquadratur, Rand-
  terme je Projektionsart, Markierung, Messwerte der Regeln (1) bis (6) aus dem Ergebnisabschnitt.
- [ ] **Schritt 2:** `packages/volumen3d/docs/Entwurf.md` neuer Abschnitt 4f (Teilprojekt 6, Zerlegung, Phase 1), `docs/Volumenmodul.md` (Stand), Kernsuite-Zahl.
- [ ] **Schritt 3:** `mypy --strict` für `api.py` und `lint-imports`; Kernsuite grün; alle Paketsuiten aus einem festen Arbeitsbaum (der Schätzer ändert keine
  Rechnung: die Zahlen der übrigen Suiten müssen Bit für Bit gleich bleiben, geprüft mit dem Prüfzeilenvergleich).
- [ ] **Schritt 4:** Commit und Push auf `feature/volumen3d`; Pull Request nur auf Anweisung, Merge nur auf Freigabe.

---

## Ergebnis Phase 1

Gemessen am 06.10.2026 aus einem festen Arbeitsbaum auf 9fc6966, nacheinander, mit 8 Threads (auf Bitte der Hauptsitzung, die nebenher Prüfungen ohne
Zeitmessung rechnete). Ausgewertet von zwei unabhängig geschriebenen Skripten (`p1_auswertung_a.py`, `p1_auswertung_b.py` im Scratchpad); beide kommen zu
denselben Urteilen. Die Lesart der Regeln stand vor dem ersten Ergebnis im Kopf der Auswertung A: Weicht bei Kirsch oder Kragarm an einem Glied der
Effektivitätsindex mit Referenz p + 1 um mehr als 20 % von dem mit Referenz p + 2 ab, werden die Regeln 1, 2 und 4 an diesem Modell nicht gewertet; Regel 5 gilt
für den Stand nach Zyklus 3.

| Folge | h bzw. Ziel | freie FHG | η | ‖e‖_E | θ = η/‖e‖_E | Treffer | Zeit Schätzer / Aufbau und Lösen (s) |
|---|---|---|---|---|---|---|---|
| Lamé p 2 | 20 / 10 / 5 | 765 / 4 395 / 28 215 | 9,230 / 2,026 / 0,519 | 2,049 / 0,467 / 0,121 | 4,50 / 4,34 / 4,27 | 1,00 / 1,00 / 1,00 | 0,2 / 9,9; 0,8 / 20,7; 4,1 / 45,8 |
| Lamé p 3 | 20 / 10 / 5 | 2 100 / 13 188 / 89 310 | 1,489 / 0,505 / 0,276 | 0,327 / 0,101 / 0,048 | 4,56 / 5,02 / 5,74 | 1,00 / 1,00 / 0,92 | 1,1 / 12,9; 4,1 / 31,7; 17,6 / 82,1 |
| Kirsch p 2 | 20 / 10 / 5 | 7 713 / 8 037 / 10 677 | 18,30 / 5,725 / 1,580 | 4,886 / 1,486 / 0,436 | 3,74 / 3,85 / 3,62 | 1,00 / 0,92 / 1,00 | 0,4 / 2,0; 0,5 / 1,9; 1,1 / 3,3 |
| Kragarm p 2 | 50 / 25 | 5 535 / 37 179 | 7,445 / 4,506 | 1,420 / 0,851 | 5,24 / 5,30 | 1,00 / 1,00 | 0,8 / 1,1; 5,2 / 3,6 |

Bei Lamé ist das Zellresiduum der größte Anteil von η (p 2 auf h 5: Residuum 0,506, Sprünge 0,078, Neumann 0,085, Dirichlet 0,021); bei p 3 wächst der
Nitsche-Rest mit der Verfeinerung (0,216 / 0,329 / 0,235) und mit ihm θ. Die Kragarm-Folge endet nach der Regel bei h 25, weil die Referenz p 4 bei h 12,5
2 489 175 Freiheitsgrade hätte (h 25: 384 615). Die Rate des Kragarms ist mit 0,72 bis 0,74 niedrig, weil die voll eingespannte Stirnfläche an ihren Kanten singulär ist; η folgt ihr.

**Regel 1 (θ konstant bis Faktor 3): erfüllt.** max θ / min θ ist 1,05 (Lamé p 2), 1,26 (Lamé p 3) und 1,01 (Kragarm). Kirsch ist nach der Referenzprüfung nicht gewertet: auf dem
gröbsten Glied (Ziel 20) weicht θ mit Referenz p 3 um 50 % von θ mit Referenz p 4 ab (5,63 gegen 3,74), auf den feineren um 4 % und 1 %. Die Lochplatte ist mit 20-mm-Zellen
um ein Loch mit 20 mm Radius auf demselben Gitter auch mit p 4 noch nicht auskonvergiert. Ungewertet liegt die Spanne bei 1,06.

**Regel 2 (gleiche Rate, Differenz der Steigungen ≤ 0,3): erfüllt.** Steigungen von η und ‖e‖_E über h: Lamé p 2 2,08 und 2,04 (Differenz 0,04), Lamé p 3 1,22 und 1,38 (0,17),
Kragarm 0,72 und 0,74 (0,02); Kirsch ungewertet 1,77 und 1,74.

**Regel 3 (Felder im Ansatzraum): erfüllt.** η / ‖u‖_E am Patch-Körper in drei Läufen von `test_konsistenz` (Schätzer seit 01e3ec6 unverändert): lineares Feld p 2 6,7·10⁻¹² bis 1,0·10⁻¹¹, quadratisches p 2
3,5·10⁻¹² bis 4,1·10⁻¹² (Schranke 10⁻⁸), kubisches p 3 1,8·10⁻¹⁰ bis 2,1·10⁻¹⁰ (Schranke 10⁻⁷).

**Regel 4 (die 10 % Zellen mit größtem η liegen zu mindestens der Hälfte unter den 20 % mit größtem wahrem Fehler): erfüllt** an Lamé h 10 p 2 mit 1,00. Kirsch Ziel 5 ist ungewertet (1,00).

**Regel 5 (h-adaptiv erreicht nach drei Zyklen den Fehler des feinsten Glieds mit weniger Freiheitsgraden): verfehlt, an beiden Modellen.**

| Zyklus | Lamé: freie FHG | Lamé: ‖e‖_E | Kirsch: freie FHG | Kirsch: ‖e‖_E |
|---|---|---|---|---|
| 0 | 765 | 2,049 | 7 713 | 4,886 |
| 1 | 1 065 | 2,184 | 7 713 | 3,940 |
| 2 | 1 674 | 2,888 | 7 821 | 2,549 |
| 3 | 2 388 | 3,116 | 8 085 | 1,347 |
| Vergleich (feinstes Glied) | 28 215 | 0,121 | 10 677 | 0,436 |

Kirsch: Der Fehler fällt in drei Zyklen auf ein Viertel. Bei gleicher Größe ist das adaptive Gitter besser als das feste (Zyklus 3 mit 8 085 Freiheitsgraden 1,35 gegen Ziel 10 mit
8 037 und 1,49). Für den Fehler des feinsten Glieds reichen drei Dörfler-Zyklen mit θ 0,5 aber nicht; die Regel war mit drei Zyklen zu knapp gesetzt. Dass Zyklus 1 dieselbe Zahl freier
Freiheitsgrade hat wie Zyklus 0 (7 713, 7 Zellen mehr), liegt daran, dass die geteilten Zellen aggregiert werden.

Lamé: Der wahre Fehler **steigt** mit jedem Zyklus, obwohl nur geteilt wird; bei geschachtelten Ansatzräumen ist das in der Energienorm ausgeschlossen. Der Diagnoselauf
(`p1_diag_lame.py`, Kriterium vor dem Lauf festgelegt: Die Vermutung „die Zellaggregation macht die Räume ungeschachtelt“ gilt als gestützt, wenn derselbe Schritt ohne Aggregation den Fehler
senkt und mit Aggregation hebt) ergibt für den Schritt von Zyklus 0 zu Zyklus 1 (4 Zellen markiert):

| | ‖e‖_E vorher → nachher | e² der geteilten Zellen | e² der übrigen Zellen | freie FHG |
|---|---|---|---|---|
| mit Aggregation (0,4) | 2,049 → 2,184 | 1,809 → 1,467 | 2,390 → 3,303 | 765 → 1 065 |
| ohne Aggregation (α 10⁻⁸) | 1,610 → 1,263 | 1,191 → 0,246 | 1,400 → 1,350 | 2 055 → 2 574 |

Die Vermutung ist damit gestützt. In den geteilten Zellen fällt der Fehler auch mit Aggregation; er steigt in den **ungeteilten** Zellen, und das nur mit Aggregation. Im verfeinerten
Gitter sind 52 von 81 Zellen aggregiert, und bei 42 davon liegt die Wurzel außerhalb der eigenen Elternzelle. Das Lamé-Modell mit h 20 ist dafür ein harter Fall: die Dicke (20 mm) ist
gleich der Basiszelle, fast jede Zelle ist an den Ebenen z = 0 und z = 20 geschnitten. Wahrscheinlicher Mechanismus (nicht gemessen): Die Teilung schafft neue, feinere wohlgestellte
Zellen, an die aggregierte Zellen der Umgebung neu gebunden werden. Deren Fortsetzung reicht dann über eine größere Entfernung, gemessen an der Wurzelgröße, und das Polynom der
früheren, gröberen Wurzel ist nicht mehr darstellbar. Ohne Aggregation gibt es das nicht (dort steht das α-Verfahren mit seinen bekannten Nachteilen, Theorie 11.4).

**Regel 6 (Flächenquadratur tiefe 2 gegen 4 ≤ 10 %): erfüllt.** Lamé h 5 p 2 +0,01 %, Kirsch Ziel 5 p 2 +0,05 %. Der Punkttest erster Ordnung genügt; eine eben-exakte
Flächenintegration ist nicht nötig.

**Zeit (berichtet, keine Regel).** Der Schätzer braucht bei Lamé 2 bis 21 % der Zeit für Aufbau und Lösen, bei Kirsch 18 bis 32 %, am Kragarm mit h 25 aber 143 % (5,2 gegen 3,6 s).
Er läuft in Python-Schleifen je Zelle und je Fläche; am kompakten Quader mit vielen ganz inneren Zellen ist das langsamer als der Direktlöser.

**Neu auf der Liste (nicht bearbeitet).** *O21 Verschachtelung bei lokaler Teilung unter Zellaggregation:* Die Teilung einzelner Zellen kann den Fehler in ungeteilten aggregierten Zellen
erhöhen (Lamé h 20: +38 % in e² der übrigen Zellen), weil sich Wurzeln umhängen. Ein hp-Treiber (Phase 3) setzt voraus, dass Verfeinern den Fehler nicht erhöht. *O22 Schätzer
vektorisieren:* Flächen und Zellen in Blöcken statt einzeln. *O23 Lasten je Lastfall:* Die Schnittstelle übergibt Flächenlasten je Lastfall als fertige Lastvektoren (`api`, `zusatzlasten`);
schätzt man dort, fehlt dem Schätzer die Soll-Traktion. Das wird wichtig, wenn der Schätzer an die Schnittstelle kommt.

**Empfehlung an den Anwender.** Der Schätzer erfüllt alle Regeln über sich selbst (1, 2, 3, 4, 6). Regel 5 verfehlt er nicht, weil er falsch markiert: An Kirsch wirkt die
Adaptivität, an Lamé verhindert die Aggregation, dass Verfeinern den Fehler senkt. Empfehlung: Phase 1 mit Regel 5 als „verfehlt“ abschließen und dokumentieren, O21 als
nächsten Punkt vor Phase 2 messen und beheben (eigene Regeln vorab, etwa „Wurzeln ungeteilter Zellen bleiben bei lokaler Teilung erhalten“ oder „Wurzel nur innerhalb der
Elternzelle“) und Regel 5 danach mit denselben Zahlen erneut prüfen, an Kirsch mit so vielen Zyklen, bis die Größe des feinsten Glieds erreicht ist. Phase 2 baut auf den
Aggregationsregeln auf (aggregierte Zellen erben p der Wurzel), deshalb O21 davor.

## Modell je Schritt

| Schritt | Modell | Denkstufe | Stand |
|---|---|---|---|
| Aufgaben 1 bis 5: Basis, Lasten, Flächen, Schätzer, Markierung | Opus 5.5 | hoch | fertig (9fc6966) |
| Aufgabe 6: Messung nach den Regeln | Opus 5.5 | hoch | gemessen; Regel 5 verfehlt, Entscheidung beim Anwender |
| Aufgabe 7: Dokumentation, Suiten, Push | Sonnet 5.5 | niedrig | offen |
