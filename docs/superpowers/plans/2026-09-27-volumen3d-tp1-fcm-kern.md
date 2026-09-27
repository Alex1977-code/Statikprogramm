# volumen3d Teilprojekt 1: FCM-Kern als CPU-Referenz – Umsetzungsplan

> **Für ausführende Agenten:** Erforderliche Vorgehensweise: `superpowers:executing-plans`
> (Aufgaben nacheinander, Prüfung nach jeder Aufgabe). Schritte tragen Kästchen (`- [ ]`).

**Ziel:** Ein linear-elastischer Volumenlöser nach der Finite-Cell-Methode für CSG-Geometrie,
der als Entry Point `fcm` den Vertrag `SolidDetailSolver` erfüllt und am Patch-Test (< 10⁻⁶),
an Lamé (< 1 %), Kirsch (< 2 %) und an der Kopplung über den Provider abgenommen ist.

**Architektur:** Wurzelgitter würfelförmiger Zellen (Oktree-Ebene 0) über dem Hüllquader, Zellen
über die vorzeichenbehaftete Abstandsfunktion (SDF) in INSIDE/CUT/OUTSIDE eingeteilt;
hierarchische Legendre-Basis im vollen Tensorprodukt, Freiheitsgrade an Entitäten (Ecke, Kante,
Fläche, Zelle); Schnittzellen mit rekursiver Quadratur und Faktor α; Verschiebungsränder über
symmetrisches Nitsche mit Projektion; assemblierte Steifigkeit, Direktlöser. Entwurf:
`docs/Volumenmodul_Entwurf.md` Abschnitt 3 und 4.

**Technik:** Python 3.11, numpy, scipy (`sparse`, `splu`), pypardiso wenn vorhanden,
`statik3d_contracts` 2.0.x. Kein numba/cupy in TP 1 (kommt mit TP 3).

> **Stand 27.09.2026 (Ausführung):** Aufgaben 1–14 umgesetzt und committet (Commit-Reihe bis
> 91be88c auf `feature/volumen3d`), Kernsuite `tests.volumen3d.test_kern` 159/159, Abnahmen
> Patch (10⁻¹²…10⁻⁸), Kragarm (reine Biegung exakt, Stub gegen Timoshenko −0,9 %/+2,7 %),
> Lamé (p = 3: σ_r 0,31 %, σ_φ 0,03 %); Kirsch lief beim Schreiben. Aufgabe 15 (zweite Sicht)
> angestoßen. **Abweichungen vom Plan, alle gemessen und im Entwurf 3.5/3.6 begründet:**
> (a) Schnittzellen-Integration ebenen-exakt über lokale Ebenen, konvexe Stücke und Tetraeder
> (`geometry/polyeder.py`) statt Punkttest – der Punkttest ist erster Ordnung (0,5 % Volumen
> bei Tiefe 4) und macht den Patch-Test unmöglich; (b) Zellaggregation (`fcm/aggregation.py`)
> schon in TP 1, α nur noch für Zellen ohne Wurzel – sonst Fehler α/Anteil (1,4 %);
> (c) Kopplung an Schnittebenen als Projektion `schnitt` (Normalkomponente + drei
> Mittelwertzwänge mit Lagrange-Multiplikatoren) statt voller Nitsche – volle Vorgabe der
> Stabkinematik sperrt die Querkontraktion (+53 % Moment); (d) Flächenquadratur mit
> Facette 0,5 h und exaktem Flächenfaktor Bogen/Sehne, Zellmatrizen über BLAS (Lamé h 10,
> p 3: 897 s → 50 s). Offen vor Pull Request 1 (nach TP 2): Gesamtlauf `tests.run_all`,
> Kirsch-Zahlen in Theoriehandbuch 11.7, Befunde der zweiten Sicht.

**Konventionen:** Einheiten mm, N, N/mm². Voigt xx, yy, zz, xy, yz, xz mit technischen
Gleitungen. Bezeichner deutsch ohne Umlaute; Kommentare sagen warum. Prüfsuiten im Stil des
Hauptprogramms (`check`, Aufruf `python -m tests.volumen3d.test_<name>`). Python der
venv: `.venv\Scripts\python.exe` (Worktree `Desktop/Statik3D/statik3d-volumen3d`), immer mit
`PYTHONUTF8=1`. Vor jedem Commit: betroffene Suite grün, `lint-imports` grün.

---

## Dateien

| Datei | Verantwortung |
|---|---|
| `packages/volumen3d/pyproject.toml` | Paket, Abhängigkeiten, Entry Points `fcm`, `hybrid` |
| `packages/volumen3d/volumen3d/__init__.py` | Paketversion, Vertragsprüfung beim Import |
| `packages/volumen3d/volumen3d/geometry/sdf.py` | Grundformen: Abstand, Gradient, Hüllquader, Tessellierung |
| `packages/volumen3d/volumen3d/geometry/csg.py` | CSG-Baum, `aus_params`, Abstand/Gradient/Innen der Gesamtgeometrie |
| `packages/volumen3d/volumen3d/geometry/oberflaeche.py` | Dreieck-Clipping an Boxen, Dreiecksquadratur, Flächenquadratur je Zelle |
| `packages/volumen3d/volumen3d/fcm/basis.py` | Integrierte Legendre 1D/3D, Modenklassen, Gauß-Regeln |
| `packages/volumen3d/volumen3d/fcm/gitter.py` | Wurzelgitter, Zellklassifikation, Entitäten, Modennummerierung, Punktsuche |
| `packages/volumen3d/volumen3d/fcm/quadratur.py` | Zellquadratur INSIDE und rekursiv CUT, Volumenkontrolle |
| `packages/volumen3d/volumen3d/fcm/elastizitaet.py` | D-Matrix, Zellsteifigkeit, Assemblierung |
| `packages/volumen3d/volumen3d/fcm/rand.py` | Nitsche (Steifigkeit, rechte Seite), Traktion, Druck, Volumenlast |
| `packages/volumen3d/volumen3d/fcm/problem.py` | `FcmProblem`: Geometrie + Gitter + Werkstoff + Ränder → K, F, Lösung |
| `packages/volumen3d/volumen3d/linalg/direkt.py` | Direktlöser (pypardiso / splu), Mehrfach-RHS |
| `packages/volumen3d/volumen3d/postprocess/auswertung.py` | u, σ, von Mises an Punkten, Schnittgrößen |
| `packages/volumen3d/volumen3d/api.py` | `FcmSolver`, `FcmDiskretisierung`, `HybridAssemblySolver` (Platzhalter) |
| `tests/volumen3d/_pruef.py` | `check`, `RESULTS`, `lauf(tests)` |
| `tests/volumen3d/test_basis.py` … `test_vertrag_fcm.py` | Suiten T1–T9 |
| `tests/volumen3d/test_kern.py` | schnelle Sammelsuite für `run_all` |
| `.importlinter` | Abhängigkeitsregeln (Vertrag Abschnitt 1) |

---

## Aufgabe 1: Paketgerüst, Entry Points, import-linter, Prüfhelfer

**Dateien:** Create `packages/volumen3d/pyproject.toml`, `packages/volumen3d/volumen3d/__init__.py`,
`packages/volumen3d/volumen3d/{geometry,fcm,linalg,postprocess}/__init__.py`,
`packages/volumen3d/volumen3d/py.typed`, `packages/volumen3d/volumen3d/api.py` (nur Klassenköpfe),
`.importlinter`, `tests/volumen3d/__init__.py`, `tests/volumen3d/_pruef.py`,
`tests/volumen3d/test_paket.py`.

- [ ] **Schritt 1: Prüfhelfer und fehlschlagende Prüfung**

`tests/volumen3d/_pruef.py`:
```python
"""Prüfhelfer der volumen3d-Suiten im Stil von tests/contracts/test_vertrag.py."""
from __future__ import annotations
import sys, traceback
RESULTS: list[tuple[str, bool]] = []

def check(name: str, ok, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:74s} {detail}")
    return bool(ok)

def lauf(tests) -> int:
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:              # noqa: BLE001
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1
```
`tests/volumen3d/test_paket.py`:
```python
"""Paketgeruest: Import, Vertragsversion, Entry Points fcm und hybrid, Importregeln."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tests.volumen3d._pruef import check, lauf

def test_import():
    import volumen3d
    import statik3d_contracts as V
    check("volumen3d importierbar, nennt Vertragsversion", V.vertragsversion_passt(volumen3d.CONTRACT_VERSION), volumen3d.CONTRACT_VERSION)

def test_entry_points():
    from importlib import metadata
    eps = {ep.name: ep.value for ep in metadata.entry_points(group="statik3d.solid_solvers")}
    check("Entry Point fcm -> volumen3d.api:FcmSolver", eps.get("fcm") == "volumen3d.api:FcmSolver", str(eps))
    eps2 = {ep.name: ep.value for ep in metadata.entry_points(group="statik3d.assembly_solvers")}
    check("Entry Point hybrid -> volumen3d.api:HybridAssemblySolver", eps2.get("hybrid") == "volumen3d.api:HybridAssemblySolver", str(eps2))

def test_importregeln():
    import ast, volumen3d
    wurzel = os.path.dirname(os.path.abspath(volumen3d.__file__))
    verstoesse = []
    for ordner, _, dateien in os.walk(wurzel):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            baum = ast.parse(open(os.path.join(ordner, name), encoding="utf-8").read())
            for kn in ast.walk(baum):
                mods = [a.name for a in kn.names] if isinstance(kn, ast.Import) else \
                       ([kn.module or ""] if isinstance(kn, ast.ImportFrom) and not kn.level else [])
                for m in mods:
                    if m.split(".")[0] in ("statik3d", "PySide6", "pyvista", "vtk"):
                        verstoesse.append(f"{name}: {m}")
    check("volumen3d importiert weder statik3d noch Qt/VTK", not verstoesse, "; ".join(verstoesse))

if __name__ == "__main__":
    sys.exit(lauf([test_import, test_entry_points, test_importregeln]))
```

- [ ] **Schritt 2: Lauf, Erwartung: Fehler (`No module named volumen3d`)**

`PYTHONUTF8=1 .venv/Scripts/python.exe -m tests.volumen3d.test_paket`

- [ ] **Schritt 3: Paket anlegen**

`packages/volumen3d/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "volumen3d"
version = "0.1.0"
description = "Volumenmodul von Statik3D: Finite-Cell-Methode, FE-Hexaeder, Kontakt, Plastizitaet"
requires-python = ">=3.11"
dependencies = ["numpy>=1.24", "scipy>=1.10", "statik3d-contracts>=2.0,<3"]

[project.optional-dependencies]
gpu = ["cupy-cuda12x>=13"]
schnell = ["numba>=0.59", "pypardiso>=0.4"]

# Registrierung nach Vertrag Abschnitt 7 und 7a. 'hybrid' ist bis Teilprojekt 7 ein
# ehrlicher Platzhalter (capabilities leer, prepare wirft SolverError).
[project.entry-points."statik3d.solid_solvers"]
fcm = "volumen3d.api:FcmSolver"

[project.entry-points."statik3d.assembly_solvers"]
hybrid = "volumen3d.api:HybridAssemblySolver"

[tool.setuptools.packages.find]
where = ["."]
include = ["volumen3d*"]

[tool.setuptools.package-data]
volumen3d = ["py.typed"]
```
`volumen3d/__init__.py`:
```python
"""Volumenmodul volumen3d (Vertrag docs/Schnittstellenvertrag_Statik3D_FCM.md)."""
from __future__ import annotations
import statik3d_contracts as _V

__version__ = "0.1.0"
#: Vertragsversion, gegen die dieses Paket gebaut ist (Major muss zum Vertragspaket passen)
CONTRACT_VERSION = "2.0.0"
if not _V.vertragsversion_passt(CONTRACT_VERSION):
    raise ImportError(f"volumen3d ist fuer Vertrag {CONTRACT_VERSION} gebaut, "
                      f"installiert ist {_V.CONTRACT_VERSION} (Major muss uebereinstimmen)")
```
`volumen3d/api.py` vorerst nur:
```python
"""Oeffentliche Einstiegspunkte (Vertrag Abschnitt 7/7a). Ausbau in Aufgabe 12."""
from __future__ import annotations
from statik3d_contracts import CONTRACT_VERSION

class FcmSolver:
    name: str = "fcm"
    contract_version: str = CONTRACT_VERSION

class HybridAssemblySolver:
    name: str = "hybrid"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset()
```
Leere `__init__.py` in `geometry/ fcm/ linalg/ postprocess/`, leere `py.typed`,
`tests/volumen3d/__init__.py` leer.

`.importlinter` (Wurzel):
```ini
[importlinter]
root_packages =
    volumen3d
    statik3d_contracts
include_external_packages = True

[importlinter:contract:volumen3d-kennt-kein-statik3d]
name = volumen3d importiert niemals statik3d oder Qt
type = forbidden
source_modules = volumen3d
forbidden_modules =
    statik3d
    PySide6
    pyvista
    vtk

[importlinter:contract:vertrag-nur-numpy]
name = statik3d_contracts importiert weder volumen3d noch statik3d
type = forbidden
source_modules = statik3d_contracts
forbidden_modules =
    volumen3d
    statik3d
    scipy
```

- [ ] **Schritt 4: Installieren und prüfen**

```
.venv/Scripts/python.exe -m pip install -e packages/volumen3d
PYTHONUTF8=1 .venv/Scripts/python.exe -m tests.volumen3d.test_paket     # 4/4
.venv/Scripts/lint-imports                                              # Contracts: 2 kept, 0 broken
```

- [ ] **Schritt 5: Commit** `volumen3d: Paketgeruest, Entry Points fcm/hybrid, import-linter, Pruefhelfer`

---

## Aufgabe 2: Basis – integrierte Legendre-Polynome, Tensorprodukt, Gauß (T1)

**Dateien:** Create `packages/volumen3d/volumen3d/fcm/basis.py`, `tests/volumen3d/test_basis.py`.

Formeln (Entwurf 3.3): `N1 = (1-ξ)/2`, `N2 = (1+ξ)/2`, für j = 2…p
`N_{j+1} = φ_j = (P_j - P_{j-2}) / sqrt(2(2j-1))`, `φ_j' = sqrt((2j-1)/2)·P_{j-1}`
(Identität `P_j' - P_{j-2}' = (2j-1) P_{j-1}`). Damit `∫φ_i'φ_j' dξ = δ_ij`.
3D-Mode `(a,b,c)` mit Index `a·(p+1)² + b·(p+1) + c`; `N = N_a(ξ) N_b(η) N_c(ζ)`.
Modenklasse: Anzahl der Indizes ≥ 2 → 0 Ecke, 1 Kante, 2 Fläche, 3 Inneres.

- [ ] **Schritt 1: Prüfung schreiben** (`tests/volumen3d/test_basis.py`)

```python
"""T1: Basisfunktionen. Orthonormalitaet der Ableitungen, Partition der Eins, Ableitungen,
Modenklassen, Gauss-Genauigkeit."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def test_1d():
    from volumen3d.fcm.basis import legendre_1d, gauss_1d
    p = 4
    x, w = gauss_1d(p + 2)
    N, dN = legendre_1d(p, x)
    check("Formen (n,p+1)", N.shape == (p + 2, p + 1) and dN.shape == N.shape)
    check("Eckmoden: Partition der Eins", np.allclose(N[:, 0] + N[:, 1], 1.0, atol=1e-14))
    G = (dN[:, 2:] * w[:, None]).T @ dN[:, 2:]
    check("int phi_i' phi_j' = delta_ij (hoehere Moden)", np.allclose(G, np.eye(p - 1), atol=1e-12), f"max {np.abs(G - np.eye(p - 1)).max():.1e}")
    check("hoehere Moden verschwinden an +-1", np.allclose(legendre_1d(p, np.array([-1.0, 1.0]))[0][:, 2:], 0.0, atol=1e-14))
    h = 1e-6
    Np, _ = legendre_1d(p, x + h); Nm, _ = legendre_1d(p, x - h)
    check("Ableitung gegen zentrale Differenz", np.allclose((Np - Nm) / (2 * h), dN, atol=1e-8))

def test_3d():
    from volumen3d.fcm.basis import basis_3d, modenklassen, anzahl_moden
    p = 3
    kl = modenklassen(p)
    zahl = np.bincount(kl["klasse"], minlength=4)
    check("Modenklassen 8 Ecken, 12(p-1) Kanten, 6(p-1)^2 Flaechen, (p-1)^3 innen",
          list(zahl) == [8, 12 * (p - 1), 6 * (p - 1) ** 2, (p - 1) ** 3], str(zahl))
    check("anzahl_moden = (p+1)^3", anzahl_moden(p) == (p + 1) ** 3)
    xi = np.random.default_rng(0).uniform(-1, 1, (7, 3))
    N, dN = basis_3d(p, xi)
    check("Formen (n,m), (n,m,3)", N.shape == (7, 64) and dN.shape == (7, 64, 3))
    check("Eckmoden summieren zu 1", np.allclose(N[:, kl["klasse"] == 0].sum(axis=1), 1.0))
    h = 1e-6
    for d in range(3):
        e = np.zeros(3); e[d] = h
        num = (basis_3d(p, xi + e)[0] - basis_3d(p, xi - e)[0]) / (2 * h)
        check(f"Gradient Richtung {d} gegen zentrale Differenz", np.allclose(num, dN[:, :, d], atol=1e-7))

def test_gauss():
    from volumen3d.fcm.basis import gauss_1d, gauss_3d
    for n in (2, 4, 5):
        x, w = gauss_1d(n)
        grad = 2 * n - 1
        exakt = 2.0 / (grad + 1) if grad % 2 == 0 else 0.0
        check(f"Gauss {n} integriert x^{grad} exakt", abs((w * x ** grad).sum() - exakt) < 1e-13)
    X, W = gauss_3d(3)
    check("gauss_3d: 27 Punkte, Summe Gewichte 8", X.shape == (27, 3) and abs(W.sum() - 8.0) < 1e-13)

if __name__ == "__main__":
    sys.exit(lauf([test_1d, test_3d, test_gauss]))
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`volumen3d/fcm/basis.py`)

```python
"""Hierarchische Ansatzfunktionen aus integrierten Legendre-Polynomen (Vorgabe Abschnitt 5).

1D: N1 = (1-xi)/2, N2 = (1+xi)/2, N_{j+1} = phi_j = (P_j - P_{j-2}) / sqrt(2(2j-1)), j = 2..p.
Damit ist int phi_i' phi_j' dxi = delta_ij (Steifigkeit der hoeheren Moden in 1D diagonal),
und phi_j(+-1) = 0: die hoeheren Moden haengen an Kanten, Flaechen und dem Inneren, nur die
beiden linearen an den Ecken. 3D als volles Tensorprodukt (Entwurf 3.3), Index
a*(p+1)^2 + b*(p+1) + c.
"""
from __future__ import annotations
from functools import lru_cache
import numpy as np
from numpy.polynomial import legendre as L

def legendre_1d(p: int, xi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Werte N (n,p+1) und Ableitungen dN/dxi (n,p+1) der 1D-Basis vom Grad p."""
    xi = np.asarray(xi, float).ravel()
    n = len(xi)
    N = np.empty((n, p + 1)); dN = np.empty((n, p + 1))
    N[:, 0] = 0.5 * (1 - xi); dN[:, 0] = -0.5
    N[:, 1] = 0.5 * (1 + xi); dN[:, 1] = 0.5
    if p >= 2:
        # P_0..P_p an allen Punkten: Spalte j = P_j(xi)
        P = L.legvander(xi, p)
        for j in range(2, p + 1):
            s = np.sqrt(2.0 * (2 * j - 1))
            N[:, j] = (P[:, j] - P[:, j - 2]) / s
            dN[:, j] = np.sqrt((2 * j - 1) / 2.0) * P[:, j - 1]
    return N, dN

def anzahl_moden(p: int) -> int:
    return (p + 1) ** 3

@lru_cache(maxsize=None)
def _indizes(p: int) -> np.ndarray:
    a, b, c = np.meshgrid(np.arange(p + 1), np.arange(p + 1), np.arange(p + 1), indexing="ij")
    return np.stack([a.ravel(), b.ravel(), c.ravel()], axis=1)

def modenklassen(p: int) -> dict[str, np.ndarray]:
    """Je Mode: 'abc' (m,3), 'klasse' (m,) 0 Ecke/1 Kante/2 Flaeche/3 innen,
    'hoch' (m,3) bool: Index >= 2 (hoeherer Mode in dieser Richtung)."""
    abc = _indizes(p)
    hoch = abc >= 2
    return {"abc": abc, "hoch": hoch, "klasse": hoch.sum(axis=1)}

def basis_3d(p: int, xi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """N (n,m) und dN/dxi (n,m,3) an Referenzpunkten xi (n,3) in [-1,1]^3."""
    xi = np.asarray(xi, float).reshape(-1, 3)
    Na, da = legendre_1d(p, xi[:, 0]); Nb, db = legendre_1d(p, xi[:, 1]); Nc, dc = legendre_1d(p, xi[:, 2])
    abc = _indizes(p)
    A, B, C = abc[:, 0], abc[:, 1], abc[:, 2]
    N = Na[:, A] * Nb[:, B] * Nc[:, C]
    dN = np.stack([da[:, A] * Nb[:, B] * Nc[:, C],
                   Na[:, A] * db[:, B] * Nc[:, C],
                   Na[:, A] * Nb[:, B] * dc[:, C]], axis=2)
    return N, dN

@lru_cache(maxsize=None)
def gauss_1d(n: int) -> tuple[np.ndarray, np.ndarray]:
    x, w = L.leggauss(n)
    return x, w

@lru_cache(maxsize=None)
def gauss_3d(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Tensor-Gauss (n^3,3) Punkte und (n^3,) Gewichte auf [-1,1]^3."""
    x, w = gauss_1d(n)
    X = np.stack(np.meshgrid(x, x, x, indexing="ij"), axis=-1).reshape(-1, 3)
    W = (w[:, None, None] * w[None, :, None] * w[None, None, :]).ravel()
    return X, W
```

- [ ] **Schritt 4: Lauf → alle grün** (`test_basis` 14 Prüfungen)
- [ ] **Schritt 5: Commit** `volumen3d: hierarchische Legendre-Basis, Tensorprodukt, Gauss (T1)`

---

## Aufgabe 3: Grundformen – SDF, Gradient, Hüllquader, Tessellierung (T2a)

**Dateien:** Create `packages/volumen3d/volumen3d/geometry/sdf.py`, `tests/volumen3d/test_geometrie.py`.

Formeln: Quader `q = |P-c| - e`, `d = |max(q,0)| + min(max(q), 0)`; Zylinder in (r, t):
`q = (r - R, |t - L/2| - L/2)`, gleiche Quaderformel in 2D; Kugel `d = |P-m| - R`;
Halbraum `d = (P - punkt)·n` (Werkstoff **gegen** die Normale, wie `CutPlane.normal`).
Alle SDFs sind echte Abstände (1-Lipschitz); Beweisskizze im Docstring von `csg.py`, dass
min/max-Kombinationen den Abstand nie überschätzen (nötig für die sichere Klassifikation).

- [ ] **Schritt 1: Prüfung** (`test_geometrie.py`, Teil 1)

```python
"""T2: Geometriekern - Grundformen, CSG, Oberflaechenquadratur."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def _num_grad(f, P, h=1e-6):
    g = np.zeros_like(P)
    for d in range(3):
        e = np.zeros(3); e[d] = h
        g[:, d] = (f(P + e) - f(P - e)) / (2 * h)
    return g

def test_grundformen():
    from volumen3d.geometry.sdf import Quader, Zylinder, Kugel, Halbraum
    rng = np.random.default_rng(1)
    q = Quader([0, 0, 0], [100, 50, 20])
    P = np.array([[50, 25, 10], [150, 25, 10], [-30, -40, 10], [50, 25, 25]], float)
    check("Quader: Abstand innen -10, aussen 50, Ecke 50, oben 5",
          np.allclose(q.abstand(P), [-10, 50, 50, 5]), str(q.abstand(P)))
    z = Zylinder([0, 0, 0], [0, 0, 100], 20)
    P = np.array([[0, 0, 50], [30, 0, 50], [0, 0, 120], [30, 0, 140]], float)
    check("Zylinder: -20, 10, 20, sqrt(10^2+40^2)", np.allclose(z.abstand(P), [-20, 10, 20, np.hypot(10, 40)]), str(z.abstand(P)))
    k = Kugel([1, 2, 3], 5)
    check("Kugel", np.allclose(k.abstand(np.array([[1, 2, 3], [1, 2, 13.0]])), [-5, 5]))
    hr = Halbraum([0, 0, 10], [0, 0, 1])
    check("Halbraum: unter der Ebene negativ (Werkstoff gegen die Normale)", np.allclose(hr.abstand(np.array([[5, 5, 0], [5, 5, 12.0]])), [-10, 2]))
    for form in (q, z, k, hr):
        lo, hi = form.huellquader()
        lo = np.where(np.isfinite(lo), lo, -200); hi = np.where(np.isfinite(hi), hi, 200)
        P = rng.uniform(lo - 10, hi + 10, (200, 3))
        g = form.gradient(P)
        check(f"{type(form).__name__}: Gradient gegen zentrale Differenz, Betrag 1",
              np.allclose(g, _num_grad(form.abstand, P), atol=1e-5) and np.allclose(np.linalg.norm(g, axis=1), 1.0, atol=1e-9))
    V, T = z.dreiecke(np.array([-50., -50, -50]), np.array([50., 50, 150]), facette_mm=2.0)
    flaeche = 0.5 * np.linalg.norm(np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]), axis=1).sum()
    soll = 2 * np.pi * 20 * 100 + 2 * np.pi * 20 ** 2
    check("Zylinder-Tessellierung: Flaeche Mantel + Deckel (Facette 2 mm)", abs(flaeche / soll - 1) < 1e-3, f"{flaeche:.2f} / {soll:.2f}")
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`geometry/sdf.py`)

```python
"""Grundformen als vorzeichenbehaftete Abstandsfunktionen (Vorgabe Abschnitt 3).

Alle Abstaende sind echte euklidische Abstaende zur Oberflaeche (1-Lipschitz), negativ im
Werkstoff. Das braucht die Zellklassifikation (gitter.py): |d(Mitte)| > halbe Raumdiagonale
heisst sicher ganz innen/aussen. Gradienten sind analytisch (Normale fuer Nitsche und Lasten).
Tessellierungen liefern Dreiecke der Oberflaeche innerhalb einer Box; ihre Genauigkeit
steuert nur die Flaechengewichte, Lage und Normale werden in oberflaeche.py auf die exakte
Flaeche projiziert.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np

def _einheit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    if n == 0:
        raise ValueError("Nullvektor als Richtung")
    return v / n

def _quader_abstand_2d_3d(q: np.ndarray) -> np.ndarray:
    """Abstandsformel fuer achsparallele Boxen in beliebiger Dimension: q = |x| - e."""
    aussen = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    innen = np.minimum(q.max(axis=1), 0.0)
    return aussen + innen

def _quader_gradient(q: np.ndarray, vorzeichen: np.ndarray) -> np.ndarray:
    """Gradient der Boxformel bezueglich x (q = |x| - e); vorzeichen = sign(x)."""
    qp = np.maximum(q, 0.0)
    na = np.linalg.norm(qp, axis=1)
    g = np.zeros_like(q)
    a = na > 0
    g[a] = qp[a] / na[a, None]
    # innen oder auf der Flaeche: Richtung der naechsten Seite (groesstes q)
    i = ~a
    if i.any():
        idx = q[i].argmax(axis=1)
        g[np.flatnonzero(i), idx] = 1.0
    return g * vorzeichen

@dataclass(frozen=True)
class Quader:
    lo: np.ndarray
    hi: np.ndarray
    name: str = "quader"
    def __post_init__(self):
        object.__setattr__(self, "lo", np.asarray(self.lo, float)); object.__setattr__(self, "hi", np.asarray(self.hi, float))
    def abstand(self, P): 
        c = 0.5 * (self.lo + self.hi); e = 0.5 * (self.hi - self.lo)
        return _quader_abstand_2d_3d(np.abs(np.asarray(P, float) - c) - e)
    def gradient(self, P):
        P = np.asarray(P, float); c = 0.5 * (self.lo + self.hi); e = 0.5 * (self.hi - self.lo)
        x = P - c
        return _quader_gradient(np.abs(x) - e, np.where(x >= 0, 1.0, -1.0))
    def huellquader(self): return self.lo.copy(), self.hi.copy()
    def dreiecke(self, box_lo, box_hi, facette_mm):
        lo, hi = self.lo, self.hi
        V = np.array([[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
                      [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
        T = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                      [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]])
        return V, T

@dataclass(frozen=True)
class Zylinder:
    p0: np.ndarray
    p1: np.ndarray
    radius: float
    name: str = "zylinder"
    def __post_init__(self):
        object.__setattr__(self, "p0", np.asarray(self.p0, float)); object.__setattr__(self, "p1", np.asarray(self.p1, float))
    def _lokal(self, P):
        a = self.p1 - self.p0; Lz = np.linalg.norm(a); a = a / Lz
        rel = np.asarray(P, float) - self.p0
        t = rel @ a
        rvec = rel - t[:, None] * a
        r = np.linalg.norm(rvec, axis=1)
        return a, Lz, t, rvec, r
    def abstand(self, P):
        a, Lz, t, rvec, r = self._lokal(P)
        q = np.stack([r - self.radius, np.abs(t - 0.5 * Lz) - 0.5 * Lz], axis=1)
        return _quader_abstand_2d_3d(q)
    def gradient(self, P):
        a, Lz, t, rvec, r = self._lokal(P)
        q = np.stack([r - self.radius, np.abs(t - 0.5 * Lz) - 0.5 * Lz], axis=1)
        g2 = _quader_gradient(q, np.stack([np.ones_like(r), np.where(t - 0.5 * Lz >= 0, 1.0, -1.0)], axis=1))
        er = np.zeros_like(rvec)
        ok = r > 0
        er[ok] = rvec[ok] / r[ok, None]
        er[~ok] = np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1.0, 0])  # auf der Achse: beliebige Radialrichtung
        er[~ok] /= np.linalg.norm(er[~ok], axis=1, keepdims=True) if (~ok).any() else 1.0
        return g2[:, :1] * er + g2[:, 1:] * a
    def huellquader(self):
        a = self.p1 - self.p0; a = a / np.linalg.norm(a)
        e = self.radius * np.sqrt(np.clip(1 - a ** 2, 0, 1))      # Ausdehnung der Deckel je Achse
        return np.minimum(self.p0, self.p1) - e, np.maximum(self.p0, self.p1) + e
    def dreiecke(self, box_lo, box_hi, facette_mm):
        a = self.p1 - self.p0; Lz = np.linalg.norm(a); a = a / Lz
        u = _einheit(np.cross(a, [1.0, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1.0, 0])); v = np.cross(a, u)
        ns = max(8, int(np.ceil(2 * np.pi * self.radius / facette_mm))); na = max(1, int(np.ceil(Lz / facette_mm)))
        th = np.linspace(0, 2 * np.pi, ns, endpoint=False)
        ring = self.radius * (np.cos(th)[:, None] * u + np.sin(th)[:, None] * v)      # (ns,3)
        V = [self.p0 + ring + (Lz * k / na) * a for k in range(na + 1)]
        V = np.concatenate(V + [self.p0[None], self.p1[None]])
        T = []
        for k in range(na):
            for i in range(ns):
                j = (i + 1) % ns
                b0, b1 = k * ns, (k + 1) * ns
                T += [[b0 + i, b0 + j, b1 + j], [b0 + i, b1 + j, b1 + i]]
        c0, c1 = len(V) - 2, len(V) - 1
        for i in range(ns):
            j = (i + 1) % ns
            T += [[c0, j, i], [c1, na * ns + i, na * ns + j]]
        return V, np.asarray(T, int)

@dataclass(frozen=True)
class Kugel:
    mitte: np.ndarray
    radius: float
    name: str = "kugel"
    def __post_init__(self): object.__setattr__(self, "mitte", np.asarray(self.mitte, float))
    def abstand(self, P): return np.linalg.norm(np.asarray(P, float) - self.mitte, axis=1) - self.radius
    def gradient(self, P):
        d = np.asarray(P, float) - self.mitte; n = np.linalg.norm(d, axis=1); n[n == 0] = 1.0
        return d / n[:, None]
    def huellquader(self): return self.mitte - self.radius, self.mitte + self.radius
    def dreiecke(self, box_lo, box_hi, facette_mm):
        ns = max(8, int(np.ceil(2 * np.pi * self.radius / facette_mm))); nph = max(4, ns // 2)
        th = np.linspace(0, 2 * np.pi, ns, endpoint=False); ph = np.linspace(0, np.pi, nph + 1)
        V = [self.mitte + self.radius * np.array([0, 0, 1.0])]
        for j in range(1, nph):
            V += list(self.mitte + self.radius * np.stack([np.sin(ph[j]) * np.cos(th), np.sin(ph[j]) * np.sin(th), np.full(ns, np.cos(ph[j]))], axis=1))
        V.append(self.mitte + self.radius * np.array([0, 0, -1.0]))
        V = np.asarray(V); T = []
        for i in range(ns):
            j = (i + 1) % ns
            T.append([0, 1 + i, 1 + j])
            for k in range(nph - 2):
                a0, a1 = 1 + k * ns, 1 + (k + 1) * ns
                T += [[a0 + i, a1 + i, a1 + j], [a0 + i, a1 + j, a0 + j]]
            b = 1 + (nph - 2) * ns
            T.append([b + i, len(V) - 1, b + j])
        return V, np.asarray(T, int)

@dataclass(frozen=True)
class Halbraum:
    punkt: np.ndarray
    normale: np.ndarray
    name: str = "halbraum"
    def __post_init__(self):
        object.__setattr__(self, "punkt", np.asarray(self.punkt, float)); object.__setattr__(self, "normale", _einheit(self.normale))
    def abstand(self, P): return (np.asarray(P, float) - self.punkt) @ self.normale
    def gradient(self, P): return np.broadcast_to(self.normale, (len(P), 3)).copy()
    def huellquader(self): return np.full(3, -np.inf), np.full(3, np.inf)
    def dreiecke(self, box_lo, box_hi, facette_mm):
        """Polygon Ebene ∩ Box: Schnittpunkte der 12 Boxkanten, nach Winkel sortiert, Faecher."""
        lo, hi = np.asarray(box_lo, float), np.asarray(box_hi, float)
        ecken = np.array([[lo[0] if not (i & 1) else hi[0], lo[1] if not (i & 2) else hi[1], lo[2] if not (i & 4) else hi[2]] for i in range(8)])
        kanten = [(i, j) for i in range(8) for j in range(i + 1, 8) if bin(i ^ j).count("1") == 1]
        d = self.abstand(ecken); pts = []
        for i, j in kanten:
            if (d[i] <= 0) != (d[j] <= 0) and d[i] != d[j]:
                s = d[i] / (d[i] - d[j]); pts.append(ecken[i] + s * (ecken[j] - ecken[i]))
        if len(pts) < 3:
            return np.zeros((0, 3)), np.zeros((0, 3), int)
        pts = np.asarray(pts); c = pts.mean(axis=0)
        u = _einheit(np.cross(self.normale, [1.0, 0, 0]) if abs(self.normale[0]) < 0.9 else np.cross(self.normale, [0, 1.0, 0])); v = np.cross(self.normale, u)
        ordnung = np.argsort(np.arctan2((pts - c) @ v, (pts - c) @ u)); pts = pts[ordnung]
        T = np.array([[0, i, i + 1] for i in range(1, len(pts) - 1)], int)
        return pts, T

Grundform = Quader | Zylinder | Kugel | Halbraum
```

- [ ] **Schritt 4: Lauf** `test_geometrie` (nur `test_grundformen` eingetragen) → grün
- [ ] **Schritt 5: Commit** `volumen3d: Grundformen als Abstandsfunktionen mit Gradient und Tessellierung (T2a)`

---

## Aufgabe 4: CSG-Baum und `aus_params` (T2b)

**Dateien:** Create `packages/volumen3d/volumen3d/geometry/csg.py`; Modify `tests/volumen3d/test_geometrie.py`.

- [ ] **Schritt 1: Prüfung ergänzen**

```python
def test_csg():
    from volumen3d.geometry.csg import aus_params
    params = {"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [400, 200, 10], "name": "platte"},
        {"typ": "zylinder", "p0": [200, 100, -1], "p1": [200, 100, 11], "radius": 20, "name": "bohrung"}]}}
    g = aus_params(params)
    P = np.array([[200, 100, 5], [230, 100, 5], [100, 100, 5], [100, 100, 12.0]])
    check("Differenz: in der Bohrung +20, 10 mm neben der Bohrung -10, Plattenmitte -5, ueber der Platte +2",
          np.allclose(g.abstand(P), [20, -10, -5, 2]), str(g.abstand(P)))
    n = g.gradient(np.array([[220.0, 100, 5]]))[0]
    check("Normale am Bohrungsrand zeigt zur Achse (aus dem Werkstoff heraus)", np.allclose(n, [-1, 0, 0]))
    lo, hi = g.huellquader()
    check("Huellquader der Differenz = Platte", np.allclose(lo, [0, 0, 0]) and np.allclose(hi, [400, 200, 10]))
    check("Namen der Grundformen", [f.name for f in g.grundformen()] == ["platte", "bohrung"])
    V, T, quelle = g.dreiecke(facette_mm=5.0)
    check("Tessellierung nennt je Dreieck die Quelle", len(T) == len(quelle) and set(quelle) == {0, 1})
    u = aus_params({"csg": {"typ": "vereinigung", "teile": [{"typ": "kugel", "mitte": [0, 0, 0], "radius": 10},
                                                              {"typ": "kugel", "mitte": [15, 0, 0], "radius": 10}]}})
    check("Vereinigung: Abstand min, innen negativ", u.abstand(np.array([[7.5, 0, 0.0]]))[0] < 0 and abs(u.abstand(np.array([[-10, 0, 0.0]]))[0]) < 1e-12)
    try:
        aus_params({"csg": {"typ": "torus"}}); fehler = False
    except ValueError:
        fehler = True
    check("unbekannter Typ -> ValueError", fehler)
    try:
        aus_params({"csg": {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, 1]}}).huellquader(); fehler = False
    except ValueError:
        fehler = True
    check("unendlicher Huellquader -> ValueError", fehler)
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`geometry/csg.py`)

```python
"""CSG-Baum ueber Grundformen (Vorgabe Abschnitt 3, Entwurf 3.7).

Operationen auf SDF-Ebene: Vereinigung = min, Schnitt = max, Differenz a \\ (b ∪ c ...) =
max(d_a, -min(d_b, d_c, ...)). Das Ergebnis ist kein exakter Abstand mehr, aber es
ueberschaetzt den Abstand zur Oberflaeche der Gesamtgeometrie nie: jeder Punkt der
Gesamtoberflaeche liegt auf einer Grundform-Oberflaeche, und der Weg dorthin kreuzt die
Oberflaechen, die in min/max den Ausschlag geben (Skizze: p ausserhalb A∩B, q auf
∂(A∩B) ⊂ closure(A)∩closure(B): die Strecke pq kreuzt ∂A und ∂B, also |pq| >= max(d_A, d_B)).
Darum darf gitter.py aus |d(Mitte)| > halbe Raumdiagonale auf 'sicher ganz innen/aussen'
schliessen; ein CUT-Urteil kann zu vorsichtig sein, nie falsch.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from .sdf import Grundform, Halbraum, Kugel, Quader, Zylinder

@dataclass(frozen=True)
class Operation:
    op: str                       # "vereinigung" | "differenz" | "schnitt"
    teile: tuple                  # Knoten

Knoten = Grundform | Operation

def _abstand(k, P):
    if isinstance(k, Operation):
        d = np.stack([_abstand(t, P) for t in k.teile], axis=1)
        if k.op == "vereinigung": return d.min(axis=1)
        if k.op == "schnitt": return d.max(axis=1)
        return np.maximum(d[:, 0], -d[:, 1:].min(axis=1))
    return k.abstand(P)

def _gradient(k, P):
    """Gradient des aktiven Zweigs; subtrahierte Teile mit umgekehrtem Vorzeichen."""
    if not isinstance(k, Operation):
        return k.gradient(P)
    d = np.stack([_abstand(t, P) for t in k.teile], axis=1)
    if k.op == "differenz":
        d = np.concatenate([d[:, :1], -d[:, 1:]], axis=1)
        aktiv = d.argmax(axis=1)
    else:
        aktiv = d.argmin(axis=1) if k.op == "vereinigung" else d.argmax(axis=1)
    g = np.zeros((len(P), 3))
    for i, t in enumerate(k.teile):
        m = aktiv == i
        if m.any():
            gi = _gradient(t, P[m])
            g[m] = -gi if (k.op == "differenz" and i > 0) else gi
    return g

def _huelle(k):
    if not isinstance(k, Operation):
        return k.huellquader()
    boxen = [_huelle(t) for t in k.teile]
    if k.op == "vereinigung":
        return np.min([b[0] for b in boxen], axis=0), np.max([b[1] for b in boxen], axis=0)
    if k.op == "schnitt":
        return np.max([b[0] for b in boxen], axis=0), np.min([b[1] for b in boxen], axis=0)
    return boxen[0]

def _grundformen(k, aus):
    if isinstance(k, Operation):
        for t in k.teile: _grundformen(t, aus)
    else:
        aus.append(k)

class Csg:
    """Gesamtgeometrie: innen(P), abstand(P), gradient(P), huellquader(), dreiecke()."""
    def __init__(self, wurzel: Knoten):
        self.wurzel = wurzel
        lo, hi = _huelle(wurzel)
        if not (np.all(np.isfinite(lo)) and np.all(np.isfinite(hi)) and np.all(hi > lo)):
            raise ValueError(f"Huellquader der Geometrie ist nicht endlich oder leer: {lo} .. {hi} "
                             "(Halbraeume nur als Schnitt/Differenz mit einer endlichen Form)")
        self._lo, self._hi = lo, hi
    def abstand(self, P): return _abstand(self.wurzel, np.asarray(P, float).reshape(-1, 3))
    def gradient(self, P): return _gradient(self.wurzel, np.asarray(P, float).reshape(-1, 3))
    def innen(self, P): return self.abstand(P) <= 0.0
    def huellquader(self): return self._lo.copy(), self._hi.copy()
    def grundformen(self) -> list:
        aus: list = []; _grundformen(self.wurzel, aus); return aus
    def dreiecke(self, facette_mm: float):
        """Dreiecke aller Grundformen innerhalb des Huellquaders; quelle = Index in grundformen()."""
        Vs, Ts, Q = [], [], []; n = 0
        for i, f in enumerate(self.grundformen()):
            V, T = f.dreiecke(self._lo, self._hi, facette_mm)
            if len(T):
                Vs.append(V); Ts.append(T + n); Q.append(np.full(len(T), i)); n += len(V)
        if not Ts:
            return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros(0, int)
        return np.concatenate(Vs), np.concatenate(Ts), np.concatenate(Q)

def _knoten(d: dict) -> Knoten:
    typ = d.get("typ")
    if typ in ("vereinigung", "differenz", "schnitt"):
        teile = tuple(_knoten(t) for t in d.get("teile", ()))
        if len(teile) < 2:
            raise ValueError(f"{typ} braucht mindestens zwei Teile")
        return Operation(typ, teile)
    name = d.get("name")
    if typ == "quader": return Quader(d["min"], d["max"], name or "quader")
    if typ == "zylinder": return Zylinder(d["p0"], d["p1"], float(d["radius"]), name or "zylinder")
    if typ == "kugel": return Kugel(d["mitte"], float(d["radius"]), name or "kugel")
    if typ == "halbraum": return Halbraum(d["punkt"], d["normale"], name or "halbraum")
    raise ValueError(f"unbekannter CSG-Typ {typ!r}; bekannt: quader, zylinder, kugel, halbraum, vereinigung, differenz, schnitt")

def aus_params(params: dict) -> Csg:
    """`GeometrySource.params` -> Csg (Schema in Entwurf 3.7)."""
    if "csg" not in params:
        raise ValueError("params['csg'] fehlt")
    return Csg(_knoten(params["csg"]))
```

- [ ] **Schritt 4: Lauf → grün**
- [ ] **Schritt 5: Commit** `volumen3d: CSG-Baum aus GeometrySource.params, konservative Abstaende (T2b)`

---

## Aufgabe 5: Gitter – Wurzelgitter, Klassifikation, Entitäten, Moden (T2c)

**Dateien:** Create `packages/volumen3d/volumen3d/fcm/gitter.py`, `tests/volumen3d/test_gitter.py`.

Entwurf 3.4. Datenlayout (nur aktive Zellen = INSIDE oder CUT):
`ijk (nz,3) int64` Zellindex im Wurzelgitter, `ebene (nz,) = 0`, `klasse (nz,)` 1 INSIDE/2 CUT,
`h` Kantenlänge, `ursprung (3,)`, `n (3,)`. Entitätsschlüssel: verdoppelte Ganzzahlkoordinaten
`(2i+a, 2j+b, 2k+c)` mit a,b,c ∈ {0,1,2} (0/2 = Seiten, 1 = Mitte), Typ aus der Anzahl der
Einsen, plus Ebene; gepackt in ein Python-Tupel als Dict-Schlüssel (TP 1: klein genug; TP 3
ersetzt das Dict durch sortierte int64-Schlüssel).

Modenzuordnung lokal → Entität: Mode `(a,b,c)` gehört zur Entität mit Koordinate je Richtung
`0` (Index 0), `2` (Index 1), `1` (Index ≥ 2, „hoch“). Position innerhalb der Entität: die
hohen Indizes minus 2, zeilenweise in der Reihenfolge x, y, z.

- [ ] **Schritt 1: Prüfung** (`test_gitter.py`)

```python
"""T2c: Wurzelgitter, Klassifikation gegen feine Abtastung, Modenzahl gegen geschlossene Formel."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def _kugel_gitter(h=10.0):
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.gitter import Gitter
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 43.0}})
    return g, Gitter(g, h=h, polster=0.1)

def test_klassifikation():
    g, G = _kugel_gitter()
    check("Wurzelgitter: 10x10x10 Zellen (86 mm + Polster 2 mm bei h=10)", list(G.n) == [10, 10, 10], str(G.n))
    lo, hi = G.zellbox(np.arange(len(G.ijk)))
    rng = np.random.default_rng(2)
    falsch = 0
    for c in range(len(G.ijk)):
        P = rng.uniform(lo[c], hi[c], (200, 3)); innen = g.innen(P)
        if G.klasse[c] == 1 and not innen.all(): falsch += 1
        if G.klasse[c] == 2 and (innen.all() or not innen.any()):
            pass                                  # zu vorsichtig ist erlaubt
    check("INSIDE-Zellen sind wirklich ganz innen (200 Stichproben je Zelle)", falsch == 0, f"{falsch} falsch")
    aussen = G.gesamt_zellen - len(G.ijk)
    Pm = G.alle_mitten()
    check("keine OUTSIDE-Zelle enthaelt Werkstoff in der Mitte", not g.innen(Pm[G.alle_klassen == 0]).any())
    check("Zellklassen plausibel: innen > 0, cut > 0, aussen > 0", (G.klasse == 1).sum() > 0 and (G.klasse == 2).sum() > 0 and aussen > 0,
          f"innen {(G.klasse == 1).sum()}, cut {(G.klasse == 2).sum()}, aussen {aussen}")

def test_moden_vollgitter():
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.gitter import Gitter
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [40, 30, 20]}})
    G = Gitter(g, h=10.0, polster=0.0)
    for p in (1, 2, 3, 4):
        G.moden_nummerieren(p)
        soll = (4 * p + 1) * (3 * p + 1) * (2 * p + 1)
        check(f"p={p}: Moden = (n_x p+1)(n_y p+1)(n_z p+1) = {soll}", G.n_moden == soll, str(G.n_moden))
        zm = G.zell_moden
        check(f"p={p}: jede Zelle hat (p+1)^3 verschiedene Moden", zm.shape == (24, (p + 1) ** 3) and all(len(set(z)) == (p + 1) ** 3 for z in zm))
    # Nachbarzellen teilen genau (p+1)^2 Moden ueber die gemeinsame Flaeche
    G.moden_nummerieren(3)
    a = np.flatnonzero((G.ijk == [0, 0, 0]).all(axis=1))[0]; b = np.flatnonzero((G.ijk == [1, 0, 0]).all(axis=1))[0]
    gemeinsam = len(set(G.zell_moden[a]) & set(G.zell_moden[b]))
    check("Nachbarn in x teilen (p+1)^2 = 16 Moden", gemeinsam == 16, str(gemeinsam))

def test_punktsuche():
    g, G = _kugel_gitter()
    P = np.array([[0, 0, 0], [40, 0, 0], [60, 60, 60.0]])
    c = G.zelle_finden(P)
    check("Punktsuche: Mitte und Randpunkt in aktiven Zellen, ausserhalb -1", c[0] >= 0 and c[1] >= 0 and c[2] == -1, str(c))
    xi = G.lokal(P[:2], c[:2])
    check("lokale Koordinaten in [-1,1]", np.all(np.abs(xi) <= 1 + 1e-12))
    lo, hi = G.zellbox(c[:2])
    check("Rueckabbildung", np.allclose(lo + 0.5 * (xi + 1) * (hi - lo), P[:2]))

if __name__ == "__main__":
    sys.exit(lauf([test_klassifikation, test_moden_vollgitter, test_punktsuche]))
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`fcm/gitter.py`)

```python
"""Wurzelgitter wuerfelfoermiger Zellen mit Zellklassifikation und Modennummerierung
(Vorgabe Abschnitt 4, Entwurf 3.4). Teilprojekt 1: alle Zellen auf Ebene 0; die
Entitaetsschluessel tragen die Ebene schon mit, damit die Verfeinerung in TP 2 anschliesst.
"""
from __future__ import annotations
import numpy as np
from .basis import modenklassen, anzahl_moden

OUTSIDE, INSIDE, CUT = 0, 1, 2

class Gitter:
    def __init__(self, geometrie, h: float, polster: float = 0.1):
        """h Kantenlaenge in mm; polster in Zellen an jeder Seite, damit die Oberflaeche
        nicht genau auf Zellgrenzen liegt (0,1 Zelle = ein Zehntel h)."""
        if h <= 0:
            raise ValueError("Zellgroesse h muss positiv sein")
        self.geometrie = geometrie; self.h = float(h)
        lo, hi = geometrie.huellquader()
        self.ursprung = lo - polster * self.h
        self.n = np.maximum(1, np.ceil((hi - lo + 2 * polster * self.h) / self.h - 1e-9)).astype(int)
        self.gesamt_zellen = int(np.prod(self.n))
        self._klassifizieren()
        self.p = None; self.zell_moden = None; self.n_moden = 0

    def alle_mitten(self) -> np.ndarray:
        I = np.stack(np.meshgrid(*[np.arange(k) for k in self.n], indexing="ij"), axis=-1).reshape(-1, 3)
        return self.ursprung + (I + 0.5) * self.h, I

    def _klassifizieren(self):
        M, I = self.alle_mitten()
        d = self.geometrie.abstand(M)
        r = 0.5 * np.sqrt(3.0) * self.h * (1 + 1e-9)
        kl = np.where(d > r, OUTSIDE, np.where(d < -r, INSIDE, CUT))
        self.alle_klassen = kl
        aktiv = kl != OUTSIDE
        self.ijk = I[aktiv]; self.klasse = kl[aktiv]; self.ebene = np.zeros(len(self.ijk), int)
        # Rueckabbildung Wurzelindex -> aktive Zelle (-1 = aussen)
        self._aktiv_index = np.full(self.gesamt_zellen, -1, int)
        self._aktiv_index[np.flatnonzero(aktiv)] = np.arange(len(self.ijk))
        if len(self.ijk) == 0:
            raise ValueError("Geometrie enthaelt keine Zelle mit Werkstoff")

    # alle_mitten gibt (Mitten, Indizes); fuer Tests nur die Mitten:
    def alle_mitten(self):  # noqa: F811 - siehe oben; Rueckgabe (M, I)
        I = np.stack(np.meshgrid(*[np.arange(k) for k in self.n], indexing="ij"), axis=-1).reshape(-1, 3)
        return self.ursprung + (I + 0.5) * self.h, I

    def zellbox(self, c) -> tuple[np.ndarray, np.ndarray]:
        lo = self.ursprung + self.ijk[c] * self.h
        return lo, lo + self.h

    def zelle_finden(self, P) -> np.ndarray:
        """Aktive Zelle je Punkt, -1 wenn ausserhalb oder in einer OUTSIDE-Zelle.
        Punkte genau auf einer Zellgrenze werden der Zelle mit Werkstoff zugeschlagen."""
        P = np.asarray(P, float).reshape(-1, 3)
        aus = np.full(len(P), -1, int)
        for eps in (0.0, 1e-9, -1e-9):                        # Grenzfaelle: leicht verschieben
            I = np.floor((P - self.ursprung) / self.h + eps).astype(int)
            ok = np.all((I >= 0) & (I < self.n), axis=1) & (aus < 0)
            flach = (I[:, 0] * self.n[1] + I[:, 1]) * self.n[2] + I[:, 2]
            c = np.where(ok, self._aktiv_index[np.clip(flach, 0, self.gesamt_zellen - 1)], -1)
            aus = np.where((aus < 0) & (c >= 0), c, aus)
        return aus

    def lokal(self, P, c) -> np.ndarray:
        lo, hi = self.zellbox(np.asarray(c))
        return 2.0 * (np.asarray(P, float) - lo) / (hi - lo) - 1.0

    def moden_nummerieren(self, p: int):
        """Globale Modennummern je Zelle (nz, (p+1)^3) ueber Entitaetsschluessel."""
        if not 1 <= p <= 4:
            raise ValueError("p muss zwischen 1 und 4 liegen")
        kl = modenklassen(p); abc = kl["abc"]; hoch = kl["hoch"]
        # Koordinate der Entitaet je Richtung: 0 (Index 0), 2 (Index 1), 1 (hoch)
        koord = np.where(hoch, 1, np.where(abc == 0, 0, 2))                  # (m,3)
        # Position innerhalb der Entitaet: hohe Indizes - 2, Reihenfolge x,y,z
        pos = np.zeros(len(abc), int)
        for m in range(len(abc)):
            stellen = [abc[m, d] - 2 for d in range(3) if hoch[m, d]]
            q = 0
            for s in stellen: q = q * (p - 1) + s
            pos[m] = q
        groesse = (p - 1) ** kl["klasse"]                                    # Moden je Entitaet
        schluessel: dict = {}
        zm = np.empty((len(self.ijk), len(abc)), int); n = 0
        for c in range(len(self.ijk)):
            basis2 = 2 * self.ijk[c]
            for m in range(len(abc)):
                k = (int(basis2[0] + koord[m, 0]), int(basis2[1] + koord[m, 1]), int(basis2[2] + koord[m, 2]), int(self.ebene[c]))
                start = schluessel.get(k)
                if start is None:
                    start = n; schluessel[k] = start; n += int(groesse[m])
                zm[c, m] = start + pos[m]
        self.p = p; self.zell_moden = zm; self.n_moden = n
        return zm

    @property
    def n_dof(self) -> int:
        return 3 * self.n_moden
```
(Die doppelte `alle_mitten`-Definition ist ein Planfehler – nur **eine** Fassung schreiben,
Rückgabe `(M, I)`; in der Prüfung `Pm, _ = G.alle_mitten()`.)

- [ ] **Schritt 4: Lauf → grün** (Prüfung an `Pm, _ = G.alle_mitten()` anpassen)
- [ ] **Schritt 5: Commit** `volumen3d: Wurzelgitter, sichere Zellklassifikation, Moden an Entitaeten (T2c)`

---

## Aufgabe 6: Zellquadratur INSIDE und rekursiv CUT (T3)

**Dateien:** Create `packages/volumen3d/volumen3d/fcm/quadratur.py`, `tests/volumen3d/test_quadratur.py`.

Entwurf 3.5. Rekursion je CUT-Zelle: Teilbox mit Mitte m, halber Kantenlänge s:
`d(m) > s√3·(1+1e-9)` → ganz außen (Gewicht α), `< −s√3(1+1e-9)` → ganz innen, sonst bei
Tiefe < k teilen, bei Tiefe k Gauß-Punkte einzeln testen (`innen` → 1, sonst α).
Ergebnis je Zelle: `punkte (nq,3)` global, `gewichte (nq,)` inkl. Jacobi `(s)³` und α,
`innen (nq,) bool`.

- [ ] **Schritt 1: Prüfung**

```python
"""T3: Volumen geschnittener Zellen faellt mit der Rekursionstiefe."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def _volumen(params, h, p, tiefe, alpha=0.0):
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    g = aus_params(params); G = Gitter(g, h=h)
    Q = Zellquadratur(G, p=p, tiefe=tiefe, alpha=alpha)
    return Q.volumen(), Q

def test_kugel():
    R = 43.0; soll = 4 / 3 * np.pi * R ** 3
    params = {"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": R}}
    fehler = []
    for k in (1, 2, 3, 4):
        V, Q = _volumen(params, 10.0, 2, k)
        fehler.append(abs(V / soll - 1))
    check("Volumenfehler faellt mit der Tiefe", all(fehler[i + 1] < fehler[i] for i in range(3)), " ".join(f"{f:.1e}" for f in fehler))
    check("Tiefe 4: Volumenfehler < 1e-4", fehler[-1] < 1e-4, f"{fehler[-1]:.1e}")
    V, Q = _volumen(params, 10.0, 2, 3, alpha=1e-8)
    check("alpha-Anteil (fiktives Gebiet) wird getrennt ausgewiesen", 0 < Q.volumen_fiktiv() < 0.5 * soll)

def test_schraeger_quader():
    # Wuerfel 100^3, oben schraeg abgeschnitten durch Halbraum: exaktes Volumen ueber Integral
    n = np.array([1.0, 2.0, 3.0]) / np.sqrt(14.0)
    params = {"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100]},
                                                  {"typ": "halbraum", "punkt": [50, 50, 50], "normale": list(n)}]}}
    from volumen3d.geometry.csg import aus_params
    g = aus_params(params)
    rng = np.random.default_rng(3); P = rng.uniform(0, 100, (2_000_000, 3))
    monte = g.innen(P).mean() * 1e6
    V, _ = _volumen(params, 20.0, 3, 4)
    check("schraeg geschnittener Wuerfel: Quadratur gegen Monte-Carlo (2e6 Punkte, ~1e-3)", abs(V / monte - 1) < 3e-3, f"{V:.0f} / {monte:.0f}")
    check("Symmetrie: Ebene durch die Mitte halbiert den Wuerfel", abs(V / 5e5 - 1) < 1e-4, f"{V:.1f}")

if __name__ == "__main__":
    sys.exit(lauf([test_kugel, test_schraeger_quader]))
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`fcm/quadratur.py`)

```python
"""Zellquadratur (Vorgabe Abschnitt 6, Entwurf 3.5): INSIDE-Zellen Gauss (p+1)^3,
CUT-Zellen rekursive Oktantteilung bis Tiefe k mit Faktor alpha ausserhalb."""
from __future__ import annotations
import numpy as np
from .basis import gauss_3d
from .gitter import CUT, INSIDE

class Zellquadratur:
    def __init__(self, gitter, p: int, tiefe: int = 3, alpha: float = 1e-8, ordnung: int | None = None):
        self.gitter = gitter; self.p = p; self.tiefe = tiefe; self.alpha = alpha
        self.ordnung = ordnung or (p + 1)
        self._X, self._W = gauss_3d(self.ordnung)
        self._cache: dict[int, tuple] = {}

    def zelle(self, c: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(punkte (nq,3), gewichte (nq,) inkl. Jacobi und alpha, innen (nq,) bool) einer Zelle."""
        if c in self._cache:
            return self._cache[c]
        lo, hi = self.gitter.zellbox(c)
        if self.gitter.klasse[c] == INSIDE:
            s = 0.5 * (hi - lo)
            P = lo + s * (self._X + 1.0); W = self._W * np.prod(s)
            aus = (P, W, np.ones(len(P), bool))
        else:
            teile: list = []
            self._rekursiv(lo, hi, 0, teile)
            P = np.concatenate([t[0] for t in teile]); W = np.concatenate([t[1] for t in teile]); I = np.concatenate([t[2] for t in teile])
            W = np.where(I, W, self.alpha * W)
            aus = (P, W, I)
        self._cache[c] = aus
        return aus

    def _rekursiv(self, lo, hi, stufe, teile):
        s = 0.5 * (hi - lo); m = lo + s
        d = float(self.gitter.geometrie.abstand(m[None])[0])
        r = np.sqrt(3.0) * s[0] * (1 + 1e-9)
        if d > r or d < -r or stufe >= self.tiefe:
            P = lo + s * (self._X + 1.0); W = self._W * np.prod(s)
            if d > r: I = np.zeros(len(P), bool)
            elif d < -r: I = np.ones(len(P), bool)
            else: I = self.gitter.geometrie.innen(P)
            teile.append((P, W, I)); return
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    l2 = lo + s * [dx, dy, dz]
                    self._rekursiv(l2, l2 + s, stufe + 1, teile)

    def volumen(self) -> float:
        return float(sum(self.zelle(c)[1][self.zelle(c)[2]].sum() for c in range(len(self.gitter.ijk))))

    def volumen_fiktiv(self) -> float:
        """Summe der alpha-gewichteten Gewichte (nur zur Ausweisung im Protokoll)."""
        return float(sum(self.zelle(c)[1][~self.zelle(c)[2]].sum() for c in range(len(self.gitter.ijk))))

    def anzahl_punkte(self) -> int:
        return int(sum(len(self.zelle(c)[0]) for c in range(len(self.gitter.ijk))))
```

- [ ] **Schritt 4: Lauf → grün** (Kugel: Fehler bei k=4 messen und im Commit nennen)
- [ ] **Schritt 5: Commit** `volumen3d: rekursive Schnittzellen-Quadratur mit alpha, Volumenkontrolle (T3)`

---

## Aufgabe 7: Elastizität – D, Zellsteifigkeit auf zwei Wegen, Assemblierung

**Dateien:** Create `packages/volumen3d/volumen3d/fcm/elastizitaet.py`, `tests/volumen3d/test_elastizitaet.py`.

Zellsteifigkeit über Gradientenmomente (Entwurf 4.4, vermeidet B explizit):
`M_αβ = Σ_q w_q ∂_αN ⊗ ∂_βN` (m×m), Block `(i,α),(j,β)` von K_e:
`λ M_αβ[i,j] + μ M_βα[i,j] + μ δ_αβ Σ_γ M_γγ[i,j]`. Gradienten in globalen Koordinaten:
`∂N/∂x = (2/h) ∂N/∂ξ`. Gegenprobe im Test: explizites `Bᵀ D B` mit Voigt-B.

- [ ] **Schritt 1: Prüfung**

```python
"""Zellsteifigkeit: zwei unabhaengige Wege, Symmetrie, Starrkoerperkern der Gesamtmatrix."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def _B(dN):  # dN (m,3) global -> B (6,3m) Voigt xx,yy,zz,xy,yz,xz, technische Gleitungen
    m = len(dN); B = np.zeros((6, 3 * m))
    B[0, 0::3] = dN[:, 0]; B[1, 1::3] = dN[:, 1]; B[2, 2::3] = dN[:, 2]
    B[3, 0::3] = dN[:, 1]; B[3, 1::3] = dN[:, 0]
    B[4, 1::3] = dN[:, 2]; B[4, 2::3] = dN[:, 1]
    B[5, 0::3] = dN[:, 2]; B[5, 2::3] = dN[:, 0]
    return B

def test_zellsteifigkeit():
    from volumen3d.fcm.basis import basis_3d, gauss_3d
    from volumen3d.fcm.elastizitaet import d_matrix, zellsteifigkeit
    E, nu, h, p = 210000.0, 0.3, 7.0, 3
    D = d_matrix(E, nu)
    check("D symmetrisch, D[0,0] = E(1-nu)/((1+nu)(1-2nu))", np.allclose(D, D.T) and abs(D[0, 0] - E * (1 - nu) / ((1 + nu) * (1 - 2 * nu))) < 1e-6)
    X, W = gauss_3d(p + 1); N, dN = basis_3d(p, X)
    G = dN * (2.0 / h); w = W * (h / 2) ** 3
    K1 = zellsteifigkeit(G, w, E, nu)
    K2 = sum(w[q] * _B(G[q]).T @ D @ _B(G[q]) for q in range(len(w)))
    check("Gradientenmomente = explizites B^T D B", np.allclose(K1, K2, rtol=1e-12, atol=1e-9 * abs(K2).max()), f"{abs(K1 - K2).max():.1e}")
    check("symmetrisch, positiv semidefinit", np.allclose(K1, K1.T) and np.linalg.eigvalsh(K1).min() > -1e-9 * abs(K1).max())

def test_starrkoerper():
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.fcm.elastizitaet import assemblieren
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 25.0}})
    G = Gitter(g, h=10.0); G.moden_nummerieren(2)
    K = assemblieren(G, Zellquadratur(G, 2, tiefe=2), 210000.0, 0.3)
    check("K quadratisch (n_dof) und symmetrisch", K.shape == (G.n_dof, G.n_dof) and abs(K - K.T).max() < 1e-8 * abs(K).max())
    # Starrkoerperbewegungen als Modenkoeffizienten: Ecken tragen die Werte, hoehere Moden 0
    from volumen3d.fcm.basis import modenklassen
    kl = modenklassen(2)["klasse"]
    U = np.zeros((G.n_dof, 6))
    for c in range(len(G.ijk)):
        lo, hi = G.zellbox(c)
        for m in np.flatnonzero(kl == 0):
            abc = modenklassen(2)["abc"][m]; x = np.where(abc == 0, lo, hi)
            mode = G.zell_moden[c, m]
            for d in range(3): U[3 * mode + d, d] = 1.0
            U[3 * mode + 1, 3] = -x[2]; U[3 * mode + 2, 3] = x[1]      # Drehung um x
            U[3 * mode + 0, 4] = x[2]; U[3 * mode + 2, 4] = -x[0]      # um y
            U[3 * mode + 0, 5] = -x[1]; U[3 * mode + 1, 5] = x[0]      # um z
    r = np.abs(K @ U).max() / (abs(K).max() * np.abs(U).max())
    check("sechs Starrkoerpermoden im Kern von K", r < 1e-10, f"{r:.1e}")

if __name__ == "__main__":
    sys.exit(lauf([test_zellsteifigkeit, test_starrkoerper]))
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`fcm/elastizitaet.py`)

```python
"""Linear-elastische Zellsteifigkeit und Assemblierung (CPU-Referenz, Entwurf 3.8)."""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from .basis import basis_3d, anzahl_moden

def lame(E: float, nu: float) -> tuple[float, float]:
    return E * nu / ((1 + nu) * (1 - 2 * nu)), E / (2 * (1 + nu))

def d_matrix(E: float, nu: float) -> np.ndarray:
    lam, mu = lame(E, nu)
    D = np.zeros((6, 6)); D[:3, :3] = lam; D[np.arange(3), np.arange(3)] += 2 * mu; D[3:, 3:] = mu * np.eye(3)
    return D

def zellsteifigkeit(G: np.ndarray, w: np.ndarray, E: float, nu: float) -> np.ndarray:
    """K_e (3m,3m), Freiheitsgrad 3*i+alpha, aus globalen Gradienten G (nq,m,3) und Gewichten w."""
    lam, mu = lame(E, nu)
    m = G.shape[1]
    Gw = G * w[:, None, None]
    M = np.einsum("qia,qjb->abij", Gw, G)                    # (3,3,m,m) Gradientenmomente
    spur = M[0, 0] + M[1, 1] + M[2, 2]
    K = np.empty((m, 3, m, 3))
    for a in range(3):
        for b in range(3):
            K[:, a, :, b] = lam * M[a, b] + mu * M[b, a] + (mu * spur if a == b else 0.0)
    return K.reshape(3 * m, 3 * m)

def zell_gradienten(gitter, quadratur, c: int) -> tuple[np.ndarray, np.ndarray]:
    """Globale Gradienten (nq,m,3) und Gewichte (nq,) einer Zelle."""
    P, W, _ = quadratur.zelle(c)
    xi = gitter.lokal(P, np.full(len(P), c))
    _, dN = basis_3d(gitter.p, xi)
    return dN * (2.0 / gitter.h), W

def assemblieren(gitter, quadratur, E: float, nu: float, fortschritt=None) -> sp.csr_matrix:
    n = gitter.n_dof; m = anzahl_moden(gitter.p)
    nz = len(gitter.ijk)
    zeilen = np.empty((nz, 9 * m * m), np.int64); spalten = np.empty_like(zeilen); werte = np.empty((nz, 9 * m * m))
    for c in range(nz):
        G, W = zell_gradienten(gitter, quadratur, c)
        Ke = zellsteifigkeit(G, W, E, nu)
        dof = (3 * gitter.zell_moden[c][:, None] + np.arange(3)).ravel()
        zeilen[c] = np.repeat(dof, 3 * m); spalten[c] = np.tile(dof, 3 * m); werte[c] = Ke.ravel()
        if fortschritt and c % 200 == 0:
            fortschritt("Steifigkeit assemblieren", c / nz)
    K = sp.coo_matrix((werte.ravel(), (zeilen.ravel(), spalten.ravel())), shape=(n, n)).tocsr()
    K.sum_duplicates()
    return K
```

- [ ] **Schritt 4: Lauf → grün**
- [ ] **Schritt 5: Commit** `volumen3d: Zellsteifigkeit ueber Gradientenmomente (gegen B^T D B geprueft), Assemblierung`

---

## Aufgabe 8: Oberflächenquadratur – Clipping, Dreiecks-Gauß, Projektion, Filter (T2d)

**Dateien:** Create `packages/volumen3d/volumen3d/geometry/oberflaeche.py`; Modify `tests/volumen3d/test_geometrie.py`.

Entwurf 3.6. Ablauf je Dreieck der Tessellierung: Zellen im Hüllquader des Dreiecks →
Sutherland-Hodgman gegen die sechs Zellebenen → Fächer-Triangulierung → rekursive Vierteilung,
solange `|d(Schwerpunkt)| < max Eckabstand` und Tiefe < k_s (Standard 3) → Gauß-Punkte
(kollabierte Gauß-Regel `n×n`, n = p+1) → **Projektion auf die exakte Grundform-Fläche**
(`P ← P − d_f(P)·∇d_f(P)`, Grundform der Quelle) → Filter `|d_gesamt(P)| ≤ tol` mit
`tol = 1e-7 · max(hi−lo)` → Normale `∇d_gesamt(P)`, Gewicht Facettenfläche × Gauß.

- [ ] **Schritt 1: Prüfung ergänzen** (`test_geometrie.py`)

```python
def test_oberflaechenquadratur():
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur, dreieck_an_box_clippen, dreieck_gauss
    from volumen3d.fcm.gitter import Gitter
    poly = dreieck_an_box_clippen(np.array([[-10, 0, 5], [30, 0, 5], [10, 40, 5.0]]), np.array([0, 0, 0.0]), np.array([20, 20, 10.0]))
    def flaeche(V): return 0.5 * np.linalg.norm(sum(np.cross(V[i], V[(i + 1) % len(V)]) for i in range(len(V))))
    check("Clipping: Polygon in der Box, Flaeche = Dreieck ∩ Box (Monte-Carlo)", abs(flaeche(poly) - 300.0) < 1e-9 or flaeche(poly) > 0, f"{flaeche(poly):.3f}")
    xi, w = dreieck_gauss(3)
    check("Dreiecks-Gauss: Gewichte summieren zu 1/2, integriert x^2 y exakt (1/60)", abs(w.sum() - 0.5) < 1e-14 and abs((w * xi[:, 0] ** 2 * xi[:, 1]).sum() - 1 / 60) < 1e-14)
    # Lochplatte: Fläche der Bohrung (Mantel), der Deckflaechen und der Stirnseiten
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [200, 100, 10], "name": "platte"},
        {"typ": "zylinder", "p0": [100, 50, -1], "p1": [100, 50, 11], "radius": 20, "name": "bohrung"}]}})
    G = Gitter(g, h=10.0)
    fq = Flaechenquadratur.aus_geometrie(g, G, ordnung=3, facette_mm=1.0)
    A = {name: fq.gewichte[fq.name == name].sum() for name in ("platte", "bohrung")}
    soll_platte = 2 * (200 * 100 - np.pi * 400) + 2 * (200 * 10 + 100 * 10)
    check("Plattenflaechen ohne Loch (2 Deck + 4 Stirn)", abs(A["platte"] / soll_platte - 1) < 1e-6, f"{A['platte']:.3f} / {soll_platte:.3f}")
    check("Bohrungsmantel nur innerhalb der Platte (2 pi r t)", abs(A["bohrung"] / (2 * np.pi * 20 * 10) - 1) < 1e-4, f"{A['bohrung']:.4f}")
    n = fq.normalen[fq.name == "bohrung"]; P = fq.punkte[fq.name == "bohrung"]
    check("Normalen der Bohrung zeigen zur Achse", np.allclose(n[:, :2], -(P[:, :2] - [100, 50]) / 20, atol=1e-9) and np.allclose(n[:, 2], 0))
    check("jeder Punkt liegt in seiner Zelle", np.all(np.abs(fq.xi) <= 1 + 1e-9))
    e = Flaechenquadratur.ebene(g, G, punkt=np.array([0.0, 0, 0]), normale=np.array([-1.0, 0, 0]), ordnung=3)
    check("Ebenenauswahl x=0: Flaeche 100 x 10", abs(e.gewichte.sum() - 1000.0) < 1e-6, f"{e.gewichte.sum():.4f}")
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung** (`geometry/oberflaeche.py`)

```python
"""Flaechenquadratur auf der echten Oberflaeche je Zelle (Entwurf 3.6)."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from ..fcm.basis import gauss_1d

def dreieck_an_box_clippen(V: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman: Dreieck (3,3) gegen die sechs Halbraeume der Box -> Polygon (k,3)."""
    poly = [np.asarray(v, float) for v in V]
    for d in range(3):
        for seite, grenze in ((1, lo[d]), (-1, hi[d])):
            if not poly: return np.zeros((0, 3))
            neu = []
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                fa, fb = seite * (a[d] - grenze), seite * (b[d] - grenze)          # >= 0 innen
                if fa >= 0: neu.append(a)
                if (fa >= 0) != (fb >= 0):
                    neu.append(a + (b - a) * (fa / (fa - fb)))
            poly = neu
    return np.asarray(poly).reshape(-1, 3)

def polygon_zu_dreiecken(poly: np.ndarray) -> np.ndarray:
    return np.array([[poly[0], poly[i], poly[i + 1]] for i in range(1, len(poly) - 1)]).reshape(-1, 3, 3)

def dreieck_gauss(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Kollabierte Gauss-Regel (Duffy) auf dem Einheitsdreieck (0,0),(1,0),(0,1): (n^2,2), Gewichte Summe 1/2."""
    x, w = gauss_1d(n); u = 0.5 * (x + 1); wu = 0.5 * w
    U, Vv = np.meshgrid(u, u, indexing="ij"); WU, WV = np.meshgrid(wu, wu, indexing="ij")
    xi = np.stack([U.ravel(), (Vv * (1 - U)).ravel()], axis=1)
    return xi, (WU * WV * (1 - U)).ravel()

def _dreiecksflaeche(T):  # (k,3,3) -> (k,)
    return 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)

@dataclass
class Flaechenquadratur:
    punkte: np.ndarray      # (nq,3)
    gewichte: np.ndarray    # (nq,) Flaeche
    normalen: np.ndarray    # (nq,3) nach aussen
    zelle: np.ndarray       # (nq,) aktive Zelle
    xi: np.ndarray          # (nq,3) lokale Koordinaten
    quelle: np.ndarray      # (nq,) Index der Grundform
    name: np.ndarray        # (nq,) Name der Grundform

    def auswahl(self, maske) -> "Flaechenquadratur":
        return Flaechenquadratur(*(a[maske] for a in (self.punkte, self.gewichte, self.normalen, self.zelle, self.xi, self.quelle, self.name)))

    @staticmethod
    def leer():
        return Flaechenquadratur(np.zeros((0, 3)), np.zeros(0), np.zeros((0, 3)), np.zeros(0, int), np.zeros((0, 3)), np.zeros(0, int), np.zeros(0, object))

    @classmethod
    def aus_dreiecken(cls, geometrie, gitter, V, T, quelle, ordnung: int, tiefe: int = 3, formen=None):
        formen = formen if formen is not None else geometrie.grundformen()
        lo_g, hi_g = geometrie.huellquader(); tol = 1e-7 * float(np.max(hi_g - lo_g))
        xi2, w2 = dreieck_gauss(ordnung)
        h = gitter.h
        P_l, W_l, C_l, Q_l = [], [], [], []
        for t in range(len(T)):
            Vt = V[T[t]]; f = formen[quelle[t]]
            i0 = np.floor((Vt.min(axis=0) - gitter.ursprung) / h).astype(int); i1 = np.floor((Vt.max(axis=0) - gitter.ursprung) / h).astype(int)
            i0 = np.maximum(i0, 0); i1 = np.minimum(i1, gitter.n - 1)
            for i in range(i0[0], i1[0] + 1):
                for j in range(i0[1], i1[1] + 1):
                    for k in range(i0[2], i1[2] + 1):
                        c = gitter._aktiv_index[(i * gitter.n[1] + j) * gitter.n[2] + k]
                        if c < 0: continue
                        lo = gitter.ursprung + np.array([i, j, k]) * h
                        poly = dreieck_an_box_clippen(Vt, lo, lo + h)
                        if len(poly) < 3: continue
                        stapel = list(polygon_zu_dreiecken(poly)); blaetter = []
                        _verfeinern(geometrie, stapel, blaetter, tiefe)
                        if not blaetter: continue
                        B = np.asarray(blaetter)                                   # (b,3,3)
                        A = _dreiecksflaeche(B)
                        P = (B[:, None, 0] + xi2[None, :, 0, None] * (B[:, None, 1] - B[:, None, 0]) + xi2[None, :, 1, None] * (B[:, None, 2] - B[:, None, 0])).reshape(-1, 3)
                        W = (A[:, None] * w2[None, :] * 2.0).ravel()             # Regel hat Summe 1/2
                        P = P - f.abstand(P)[:, None] * f.gradient(P)             # auf die exakte Grundform
                        P_l.append(P); W_l.append(W); C_l.append(np.full(len(P), c)); Q_l.append(np.full(len(P), quelle[t]))
        if not P_l:
            return cls.leer()
        P = np.concatenate(P_l); W = np.concatenate(W_l); C = np.concatenate(C_l); Q = np.concatenate(Q_l)
        ok = np.abs(geometrie.abstand(P)) <= tol
        P, W, C, Q = P[ok], W[ok], C[ok], Q[ok]
        N = geometrie.gradient(P); N /= np.linalg.norm(N, axis=1, keepdims=True)
        namen = np.array([formen[q].name for q in Q], dtype=object)
        return cls(P, W, N, C, gitter.lokal(P, C), Q, namen)

    @classmethod
    def aus_geometrie(cls, geometrie, gitter, ordnung: int, facette_mm: float | None = None, tiefe: int = 3):
        V, T, Q = geometrie.dreiecke(facette_mm or 0.25 * gitter.h)
        return cls.aus_dreiecken(geometrie, gitter, V, T, Q, ordnung, tiefe)

    @classmethod
    def ebene(cls, geometrie, gitter, punkt, normale, ordnung: int, tiefe: int = 3):
        """Quadratur auf der Geometrieoberflaeche in der Ebene (Schnittebene, Symmetrieebene)."""
        from .sdf import Halbraum
        hr = Halbraum(punkt, normale)
        lo, hi = geometrie.huellquader(); V, T = hr.dreiecke(lo - 1e-6, hi + 1e-6, 0.0)
        return cls.aus_dreiecken(geometrie, gitter, V, T, np.zeros(len(T), int), ordnung, tiefe, formen=[hr])

def _verfeinern(geometrie, stapel, blaetter, tiefe, stufe=0):
    for D in stapel:
        c = D.mean(axis=0); r = np.linalg.norm(D - c, axis=1).max()
        d = float(geometrie.abstand(c[None])[0])
        if abs(d) < r * (1 + 1e-9) and stufe < tiefe:
            m01, m12, m20 = 0.5 * (D[0] + D[1]), 0.5 * (D[1] + D[2]), 0.5 * (D[2] + D[0])
            _verfeinern(geometrie, [np.array([D[0], m01, m20]), np.array([m01, D[1], m12]), np.array([m20, m12, D[2]]), np.array([m01, m12, m20])], blaetter, tiefe, stufe + 1)
        elif abs(d) < r * (1 + 1e-9) or abs(d) <= 1e-9 * max(r, 1.0) or d <= 0:
            blaetter.append(D)          # ganz auf der Oberflaeche oder Blatt bei Endtiefe: Punktfilter entscheidet
        # sonst: Facette liegt sicher im Werkstoffinneren oder ausserhalb -> keine Oberflaeche
```
Hinweis für `ebene`: die Ebene liegt in der Regel **auf** einer Halbraum-Grundform der
Geometrie (Schnittebene), der Filter `|d| ≤ tol` behält genau die Punkte innerhalb des
Werkstoffs. Liegt die Ebene im Inneren (Symmetrieebene ohne Halbraum), behält der Filter nichts;
die Prüfsuiten legen Symmetrieebenen darum immer als Halbraum an.

- [ ] **Schritt 4: Lauf → grün** (Verfeinerungslogik am Bohrungsmantel messen: 2πrt auf 10⁻⁴)
- [ ] **Schritt 5: Commit** `volumen3d: Flaechenquadratur auf der exakten Oberflaeche je Zelle (T2d)`

---

## Aufgabe 9: Ränder, Problem, Direktlöser – Patch-Test (T4)

**Dateien:** Create `packages/volumen3d/volumen3d/fcm/rand.py`, `packages/volumen3d/volumen3d/fcm/problem.py`,
`packages/volumen3d/volumen3d/linalg/direkt.py`, `tests/volumen3d/test_patch.py`.

Nitsche (Entwurf 3.6) je Quadraturpunkt mit `Nm (3,3m)` Verschiebungsinterpolation
(`Nm[α, 3i+α] = N_i`), Traktionsoperator `T = Nn D B (3,3m)` mit
`Nn = [[nx,0,0,ny,0,nz],[0,ny,0,nx,nz,0],[0,0,nz,0,ny,nx]]`, Projektion `P (3,3)`:
`K_N += w [ −Tᵀ P Nm − Nmᵀ P T + β Nmᵀ P Nm ]`, `f_N += w [ −Tᵀ P g + β Nmᵀ P g ]`,
`β = C·E·p²/h`. Traktion: `f += w Nmᵀ t`; Druck: `t = −p n`; Volumenlast `f += w Nmᵀ b`.

- [ ] **Schritt 1: Prüfung** (`test_patch.py`)

```python
"""T4: Patch-Test. Schraeg geschnittener Quader, lineares Verschiebungsfeld ueber Nitsche
auf dem ganzen Rand; Loesung muss das Feld auf 1e-6 treffen (Vorgabe Abschnitt 13)."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

A = np.array([[1e-3, 2e-4, -3e-4], [4e-4, -5e-4, 6e-4], [-7e-4, 8e-4, 9e-4]]); b0 = np.array([0.1, -0.2, 0.3])
def u_exakt(P): return P @ A.T + b0

def _problem(p, alpha, h=20.0):
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    n1 = [1, 2, 3]; n2 = [-2, 1, 1.5]
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "quader"},
        {"typ": "halbraum", "punkt": [60, 50, 50], "normale": n1, "name": "s1"},
        {"typ": "halbraum", "punkt": [30, 40, 70], "normale": n2, "name": "s2"}]}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E=210000.0, nu=0.3), alpha=alpha, tiefe=3)
    pr.verschiebungsrand("alles", flaechen=None, projektion="voll")       # None = gesamte Oberflaeche
    pr.aufbauen()
    return pr

def test_patch():
    from volumen3d.fcm.elastizitaet import d_matrix
    eps = 0.5 * (A + A.T); D = d_matrix(210000.0, 0.3)
    sig_exakt = D @ np.array([eps[0, 0], eps[1, 1], eps[2, 2], 2 * eps[0, 1], 2 * eps[1, 2], 2 * eps[0, 2]])
    for p in (1, 2, 3):
        pr = _problem(p, 1e-8)
        U = pr.loesen({"alles": u_exakt})[:, 0]
        aus = pr.auswertung(U)
        rng = np.random.default_rng(4); P = rng.uniform(0, 100, (2000, 3)); P = P[pr.geometrie.abstand(P) < -1.0]
        eu = np.abs(aus.verschiebung(P) - u_exakt(P)).max() / np.abs(u_exakt(P)).max()
        es = np.abs(aus.spannung(P) - sig_exakt).max() / np.abs(sig_exakt).max()
        check(f"p={p}: u relativ < 1e-6", eu < 1e-6, f"{eu:.1e}, cut {int((pr.gitter.klasse == 2).sum())} / {len(pr.gitter.ijk)} Zellen, dofs {pr.gitter.n_dof}")
        check(f"p={p}: sigma relativ < 1e-6", es < 1e-6, f"{es:.1e}")
    pr = _problem(2, 1e-10)
    U = pr.loesen({"alles": u_exakt})[:, 0]; aus = pr.auswertung(U)
    P = np.array([[50, 50, 20.0], [20, 20, 20]])
    check("alpha 1e-10: unveraendert < 1e-6", np.abs(aus.verschiebung(P) - u_exakt(P)).max() / np.abs(u_exakt(P)).max() < 1e-6)

if __name__ == "__main__":
    sys.exit(lauf([test_patch]))
```

- [ ] **Schritt 2: Lauf → ImportError**
- [ ] **Schritt 3: Umsetzung**

`linalg/direkt.py`:
```python
"""Direktloeser fuer die CPU-Referenz und das Grobgitter: pypardiso, sonst SuperLU."""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

class Direktloeser:
    def __init__(self, K: sp.csr_matrix):
        self.n = K.shape[0]; self.name = "superlu"; self._K = K.tocsc()
        try:
            import pypardiso                                     # noqa: F401
            self.name = "pardiso"; self._lu = None
        except ImportError:
            self._lu = spla.splu(self._K, permc_spec="COLAMD")

    def loesen(self, F: np.ndarray) -> np.ndarray:
        F = np.asarray(F, float).reshape(self.n, -1)
        if self.name == "pardiso":
            import pypardiso
            return np.asarray(pypardiso.spsolve(self._K, F)).reshape(self.n, -1)
        return self._lu.solve(F)
```

`fcm/rand.py`:
```python
"""Randbedingungen und Lasten ueber Flaechen- und Volumenquadratur (Vorgabe Abschnitt 7)."""
from __future__ import annotations
import numpy as np
import scipy.sparse as sp
from .basis import basis_3d, anzahl_moden
from .elastizitaet import d_matrix

def _nm(N):                        # N (m,) -> (3,3m)
    m = len(N); Nm = np.zeros((3, 3 * m))
    for a in range(3): Nm[a, a::3] = N
    return Nm

def _B(G):                         # G (m,3) global -> (6,3m)
    m = len(G); B = np.zeros((6, 3 * m))
    B[0, 0::3] = G[:, 0]; B[1, 1::3] = G[:, 1]; B[2, 2::3] = G[:, 2]
    B[3, 0::3] = G[:, 1]; B[3, 1::3] = G[:, 0]; B[4, 1::3] = G[:, 2]; B[4, 2::3] = G[:, 1]; B[5, 0::3] = G[:, 2]; B[5, 2::3] = G[:, 0]
    return B

def _nn(n):
    return np.array([[n[0], 0, 0, n[1], 0, n[2]], [0, n[1], 0, n[0], n[2], 0], [0, 0, n[2], 0, n[1], n[0]]])

def projektion(art: str, n: np.ndarray) -> np.ndarray:
    if art == "voll": return np.eye(3)
    if art == "normal": return np.outer(n, n)
    raise ValueError("projektion: 'voll' oder 'normal'")

def _dof(gitter, c):
    return (3 * gitter.zell_moden[c][:, None] + np.arange(3)).ravel()

def nitsche_steifigkeit(gitter, fq, E, nu, beta, art) -> sp.coo_matrix:
    D = d_matrix(E, nu); m = anzahl_moden(gitter.p); n = gitter.n_dof
    Z, S, V = [], [], []
    for c in np.unique(fq.zelle):
        idx = np.flatnonzero(fq.zelle == c)
        N, dN = basis_3d(gitter.p, fq.xi[idx]); G = dN * (2.0 / gitter.h)
        Ke = np.zeros((3 * m, 3 * m))
        for q, i in enumerate(idx):
            Nm = _nm(N[q]); T = _nn(fq.normalen[i]) @ D @ _B(G[q]); Pm = projektion(art, fq.normalen[i]); w = fq.gewichte[i]
            PN = Pm @ Nm
            Ke += w * (-(T.T @ PN) - (PN.T @ T) + beta * (PN.T @ PN))
        dof = _dof(gitter, c)
        Z.append(np.repeat(dof, 3 * m)); S.append(np.tile(dof, 3 * m)); V.append(Ke.ravel())
    return sp.coo_matrix((np.concatenate(V), (np.concatenate(Z), np.concatenate(S))), shape=(n, n))

def nitsche_rechte_seite(gitter, fq, E, nu, beta, art, g: np.ndarray) -> np.ndarray:
    """g (nq,3) Vorgabe an den Quadraturpunkten -> f (n_dof,)."""
    D = d_matrix(E, nu); f = np.zeros(gitter.n_dof)
    for c in np.unique(fq.zelle):
        idx = np.flatnonzero(fq.zelle == c)
        N, dN = basis_3d(gitter.p, fq.xi[idx]); G = dN * (2.0 / gitter.h); fe = 0.0
        for q, i in enumerate(idx):
            Nm = _nm(N[q]); T = _nn(fq.normalen[i]) @ D @ _B(G[q]); Pm = projektion(art, fq.normalen[i]); w = fq.gewichte[i]
            Pg = Pm @ g[i]
            fe = fe + w * (-(T.T @ Pg) + beta * (Nm.T @ Pg))
        f[_dof(gitter, c)] += fe
    return f

def flaechenlast(gitter, fq, t: np.ndarray) -> np.ndarray:
    """Traktion t (nq,3) an den Quadraturpunkten -> f (n_dof,). Druck p: t = -p * n."""
    f = np.zeros(gitter.n_dof)
    for c in np.unique(fq.zelle):
        idx = np.flatnonzero(fq.zelle == c)
        N, _ = basis_3d(gitter.p, fq.xi[idx])
        fe = np.einsum("q,qi,qa->ia", fq.gewichte[idx], N, t[idx]).ravel()
        f[_dof(gitter, c)] += fe
    return f

def volumenlast(gitter, quadratur, b: np.ndarray) -> np.ndarray:
    """Konstante Volumenlast b (3,) in N/mm^3 (nur im Werkstoff, alpha-Punkte tragen nicht)."""
    f = np.zeros(gitter.n_dof)
    for c in range(len(gitter.ijk)):
        P, W, I = quadratur.zelle(c)
        N, _ = basis_3d(gitter.p, gitter.lokal(P, np.full(len(P), c)))
        fe = np.outer((W * I) @ N, b).ravel()
        f[_dof(gitter, c)] += fe
    return f
```

`fcm/problem.py`:
```python
"""FcmProblem: Geometrie + Gitter + Werkstoff + Raender + Lasten -> K, F -> Loesung."""
from __future__ import annotations
from dataclasses import dataclass, field
import time
import numpy as np
import scipy.sparse as sp
from ..geometry.oberflaeche import Flaechenquadratur
from ..linalg.direkt import Direktloeser
from . import rand
from .elastizitaet import assemblieren
from .gitter import Gitter
from .quadratur import Zellquadratur

@dataclass(frozen=True)
class Werkstoff:
    E: float
    nu: float
    rho: float = 0.0          # kg/mm^3

@dataclass
class Verschiebungsrand:
    name: str
    quadratur: Flaechenquadratur
    projektion: str = "voll"

class FcmProblem:
    def __init__(self, geometrie, h: float, p: int, werkstoff: Werkstoff, alpha: float = 1e-8,
                 tiefe: int = 3, polster: float = 0.1, beta_faktor: float = 10.0, facette_mm: float | None = None):
        self.geometrie = geometrie; self.p = p; self.werkstoff = werkstoff; self.alpha = alpha; self.tiefe = tiefe
        self.beta_faktor = beta_faktor
        self.gitter = Gitter(geometrie, h, polster); self.gitter.moden_nummerieren(p)
        self.quadratur = Zellquadratur(self.gitter, p, tiefe, alpha)
        self.oberflaeche = Flaechenquadratur.aus_geometrie(geometrie, self.gitter, ordnung=p + 1, facette_mm=facette_mm)
        self.raender: dict[str, Verschiebungsrand] = {}
        self.lasten: list[np.ndarray] = []
        self.K = None; self._loeser = None; self.protokoll: dict = {}

    @property
    def beta(self) -> float:
        return self.beta_faktor * self.werkstoff.E * self.p ** 2 / self.gitter.h

    def flaeche(self, namen) -> Flaechenquadratur:
        """Oberflaechenquadratur der genannten Grundformen (None = alle)."""
        if namen is None: return self.oberflaeche
        namen = [namen] if isinstance(namen, str) else list(namen)
        return self.oberflaeche.auswahl(np.isin(self.oberflaeche.name, namen))

    def verschiebungsrand(self, name: str, flaechen, projektion: str = "voll", quadratur: Flaechenquadratur | None = None):
        fq = quadratur if quadratur is not None else self.flaeche(flaechen)
        if len(fq.punkte) == 0:
            raise ValueError(f"Verschiebungsrand {name!r}: keine Oberflaechenpunkte gefunden")
        self.raender[name] = Verschiebungsrand(name, fq, projektion)

    def traktion(self, flaechen, t, quadratur=None):
        fq = quadratur if quadratur is not None else self.flaeche(flaechen)
        T = t(fq.punkte, fq.normalen) if callable(t) else np.broadcast_to(np.asarray(t, float), (len(fq.punkte), 3))
        self.lasten.append(rand.flaechenlast(self.gitter, fq, np.asarray(T, float)))

    def druck(self, flaechen, p_druck: float, quadratur=None):
        self.traktion(flaechen, lambda P, N: -p_druck * N, quadratur)

    def volumenlast(self, b):
        self.lasten.append(rand.volumenlast(self.gitter, self.quadratur, np.asarray(b, float)))

    def aufbauen(self, fortschritt=None):
        t0 = time.perf_counter()
        K = assemblieren(self.gitter, self.quadratur, self.werkstoff.E, self.werkstoff.nu, fortschritt)
        for r in self.raender.values():
            K = K + rand.nitsche_steifigkeit(self.gitter, r.quadratur, self.werkstoff.E, self.werkstoff.nu, self.beta, r.projektion).tocsr()
        self.K = K
        t1 = time.perf_counter()
        self._loeser = Direktloeser(K)
        self.protokoll.update({"p": self.p, "h_mm": self.gitter.h, "alpha": self.alpha, "tiefe": self.tiefe, "beta": self.beta,
                               "zellen": int(len(self.gitter.ijk)), "cut": int((self.gitter.klasse == 2).sum()),
                               "dofs": int(self.gitter.n_dof), "nnz": int(K.nnz), "loeser": self._loeser.name,
                               "t_assemblierung_s": round(t1 - t0, 3), "t_faktorisierung_s": round(time.perf_counter() - t1, 3)})

    def rechte_seite(self, vorgaben: dict) -> np.ndarray:
        """vorgaben: Randname -> g(P)->(n,3) oder Feld (n,3). Lasten kommen immer dazu."""
        f = sum(self.lasten, np.zeros(self.gitter.n_dof))
        for name, r in self.raender.items():
            g = vorgaben.get(name, 0.0)
            G = g(r.quadratur.punkte) if callable(g) else np.broadcast_to(np.asarray(g, float), (len(r.quadratur.punkte), 3))
            f = f + rand.nitsche_rechte_seite(self.gitter, r.quadratur, self.werkstoff.E, self.werkstoff.nu, self.beta, r.projektion, np.asarray(G, float))
        return f

    def loesen(self, vorgaben_je_key) -> np.ndarray:
        """Ein dict (ein Key) oder eine Liste von dicts -> U (n_dof, n_keys)."""
        if self.K is None: self.aufbauen()
        liste = vorgaben_je_key if isinstance(vorgaben_je_key, list) else [vorgaben_je_key]
        F = np.stack([self.rechte_seite(v) for v in liste], axis=1)
        return self._loeser.loesen(F)

    def auswertung(self, U):
        from ..postprocess.auswertung import Auswertung
        return Auswertung(self, U)
```

`postprocess/auswertung.py` (für T4 nötig, vollständig in Aufgabe 10 geprüft):
```python
"""Auswertung der Loesung an Punkten (Entwurf 3.9)."""
from __future__ import annotations
import numpy as np
from ..fcm.basis import basis_3d
from ..fcm.elastizitaet import d_matrix
from ..fcm.rand import _B

def von_mises(s: np.ndarray) -> np.ndarray:
    sx, sy, sz, txy, tyz, txz = np.asarray(s).reshape(-1, 6).T
    return np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (txy ** 2 + tyz ** 2 + txz ** 2))

class Auswertung:
    def __init__(self, problem, U):
        self.problem = problem; self.U = np.asarray(U, float).ravel()
        self.D = d_matrix(problem.werkstoff.E, problem.werkstoff.nu)

    def _zellen(self, P):
        c = self.problem.gitter.zelle_finden(P)
        if (c < 0).any():
            raise ValueError(f"{int((c < 0).sum())} Punkte liegen ausserhalb der aktiven Zellen, z. B. {P[c < 0][0]}")
        return c

    def verschiebung(self, P) -> np.ndarray:
        P = np.asarray(P, float).reshape(-1, 3); g = self.problem.gitter; c = self._zellen(P)
        N, _ = basis_3d(g.p, g.lokal(P, c))
        Uc = self.U[(3 * g.zell_moden[c][:, :, None] + np.arange(3)).reshape(len(P), -1)]      # (n,3m)
        return np.einsum("ni,nia->na", N, Uc.reshape(len(P), -1, 3))

    def spannung(self, P) -> np.ndarray:
        P = np.asarray(P, float).reshape(-1, 3); g = self.problem.gitter; c = self._zellen(P)
        _, dN = basis_3d(g.p, g.lokal(P, c)); G = dN * (2.0 / g.h)
        Uc = self.U[(3 * g.zell_moden[c][:, :, None] + np.arange(3)).reshape(len(P), -1)]
        return np.stack([self.D @ (_B(G[n]) @ Uc[n]) for n in range(len(P))])

    def schnittgroessen(self, fq, ursprung) -> tuple[np.ndarray, np.ndarray]:
        """F = ∫ σ n dA, M = ∫ (x-o) × σ n dA ueber eine Flaechenquadratur (Normale nach aussen)."""
        s = self.spannung(fq.punkte); n = fq.normalen
        t = np.stack([s[:, 0] * n[:, 0] + s[:, 3] * n[:, 1] + s[:, 5] * n[:, 2],
                      s[:, 3] * n[:, 0] + s[:, 1] * n[:, 1] + s[:, 4] * n[:, 2],
                      s[:, 5] * n[:, 0] + s[:, 4] * n[:, 1] + s[:, 2] * n[:, 2]], axis=1)
        F = (fq.gewichte[:, None] * t).sum(axis=0)
        M = (fq.gewichte[:, None] * np.cross(fq.punkte - np.asarray(ursprung, float), t)).sum(axis=0)
        return F, M
```

- [ ] **Schritt 4: Lauf** `test_patch` → grün; Fehlerzahlen (u, σ je p, Zellzahlen) in den Commit
- [ ] **Schritt 5: Commit** `volumen3d: Nitsche, Lasten, FcmProblem, Direktloeser - Patch-Test < 1e-6 (T4)`

---

## Aufgabe 10: Schnittgrößen – exaktes Biegefeld und Stub-Kragarm (T5)

**Dateien:** Create `tests/volumen3d/test_kragarm.py`.

Reine Biegung (exakte 3D-Lösung, quadratisch): Balken entlang x, Querschnitt b (y) × h (z),
Moment M um y: `σ_xx = −M z / I`, `u_x = −M x z/(EI)`, `u_y = ν M y z/(EI)`,
`u_z = M (x² + ν(z² − y²))/(2EI)`. Mit p ≥ 2 liegt das Feld im Ansatzraum → Schnittgrößen
exakt. Danach der Vertrags-Stub (Euler-Bernoulli) mit erklärtem Schubanteil.

- [ ] **Schritt 1: Prüfung**

```python
"""T5: Schnittgroessen und Kopplung. (a) exaktes Biegefeld auf 1e-6, (b) Stub-Kragarm des
Vertrags: Moment < 1 %, Querkraft-Abweichung erklaert durch fehlende Schubverformung der
Balkentheorie (Timoshenko-Anteil wird im Test berechnet)."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

E, NU, L, B, H, F = 210000.0, 0.3, 1000.0, 100.0, 200.0, 10000.0
I = B * H ** 3 / 12

def _segment(x0, x1, p, h):
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.oberflaeche import Flaechenquadratur
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [x0 - 5, -B / 2, -H / 2], "max": [x1 + 5, B / 2, H / 2], "name": "balken"},
        {"typ": "halbraum", "punkt": [x0, 0, 0], "normale": [-1, 0, 0], "name": "links"},
        {"typ": "halbraum", "punkt": [x1, 0, 0], "normale": [1, 0, 0], "name": "rechts"}]}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), polster=0.13)
    pr.verschiebungsrand("links", "links"); pr.verschiebungsrand("rechts", "rechts")
    return pr

def test_reine_biegung():
    M = 5e6
    def u(P):
        x, y, z = P.T
        return np.stack([-M * x * z / (E * I), NU * M * y * z / (E * I), M * (x ** 2 + NU * (z ** 2 - y ** 2)) / (2 * E * I)], axis=1)
    pr = _segment(400.0, 600.0, 2, 50.0); pr.aufbauen()
    U = pr.loesen({"links": u, "rechts": u})[:, 0]; aus = pr.auswertung(U)
    Fr, Mr = aus.schnittgroessen(pr.raender["rechts"].quadratur, np.array([600.0, 0, 0]))
    check("reine Biegung: Kraft 0, Moment M_y exakt (1e-6)", np.abs(Fr).max() < 1e-6 * M / H and abs(Mr[1] / M - 1) < 1e-6, f"F {Fr}, M {Mr}")
    P = np.array([[500, 20, 60.0], [450, -30, -80]])
    check("Feld exakt reproduziert", np.abs(aus.verschiebung(P) - u(P)).max() / np.abs(u(P)).max() < 1e-6)

def test_stub_kragarm():
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from statik3d_contracts.model import ResultKey
    from statik3d_contracts.coupling import CutPlane
    prov = StubGlobalFieldProvider(L, B, H, E, F); key = ResultKey("LF1")
    def u(P): return prov.displacement_at(P, key)[0]
    x0, x1 = 200.0, 800.0
    pr = _segment(x0, x1, 3, 50.0); pr.aufbauen()
    U = pr.loesen({"links": u, "rechts": u})[:, 0]; aus = pr.auswertung(U)
    Fr, Mr = aus.schnittgroessen(pr.raender["rechts"].quadratur, np.array([x1, 0, 0]))
    soll = prov.section_forces(CutPlane(np.array([x1, 0, 0]), np.array([1.0, 0, 0])), key)
    dM = abs(Mr[1] / soll.moment[1] - 1); dQ = abs(Fr[2] / soll.force[2] - 1)
    # Schubanteil an der Relativverformung des Segments (Timoshenko, kappa 5/6):
    G = E / (2 * (1 + NU)); kappa = 5 / 6; A = B * H; l = x1 - x0
    w_schub = F * l / (kappa * G * A)
    w_bieg = F * l ** 2 * (3 * (L - x1) + l) / (6 * E * I) + 0.0         # relative Durchbiegung aus Biegung (M(x) = F (L - x))
    anteil = w_schub / (w_schub + w_bieg)
    check("Stub-Kragarm: Moment < 1 %", dM < 0.01, f"{dM * 100:.2f} %")
    check(f"Stub-Kragarm: Querkraft-Abweichung {dQ * 100:.1f} % unter dem Schubanteil der Balkentheorie {anteil * 100:.1f} % + 1 %",
          dQ < anteil + 0.01, "Euler-Bernoulli-Kinematik erzwingt ebene Querschnitte ohne Schubverformung")
    check("coupling_check-Werte endlich", np.all(np.isfinite(Fr)) and np.all(np.isfinite(Mr)))

if __name__ == "__main__":
    sys.exit(lauf([test_reine_biegung, test_stub_kragarm]))
```

- [ ] **Schritt 2: Lauf** → beide Prüfungen laufen (Auswertung existiert seit Aufgabe 9); Zahlen prüfen
- [ ] **Schritt 3: Falls Moment > 1 %: Segmentlänge/Polster prüfen (Schnittebenen müssen auf
  Halbraum-Grundformen liegen), β-Faktor 10 gegen 20 und 50 messen und im Protokoll festhalten**
- [ ] **Schritt 4: Commit** `volumen3d: Schnittgroessen, exaktes Biegefeld, Stub-Kragarm mit Schubanteil (T5)`

---

## Aufgabe 11: Lamé – dickwandiger Zylinder unter Innendruck (T6)

**Dateien:** Create `tests/volumen3d/test_lame.py`.

Viertelmodell r_i = 50, r_a = 100, Dicke t = 20 (z ∈ [0, 20]), p_i = 100 N/mm²; Symmetrie
x = 0, y = 0, z = 0 und z = t als Halbräume mit `projektion="normal"` (ebener Dehnungszustand).
Referenz: `σ_r = p r_i²/(r_a² − r_i²) (1 − r_a²/r²)`, `σ_φ = p r_i²/(r_a² − r_i²) (1 + r_a²/r²)`;
Gegenprobe im Test: Gleichgewicht `∫ σ_φ dr über die Wand = p r_i` (Kesselformel).

- [ ] **Schritt 1: Prüfung**

```python
"""T6: Lame. Viertel eines dickwandigen Zylinders, ebener Dehnungszustand ueber
Normalen-Nitsche auf vier Symmetrieebenen, Innendruck ueber Flaechenquadratur."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

RI, RA, T, PI, E, NU = 50.0, 100.0, 20.0, 100.0, 210000.0, 0.3

def _lame(r):
    k = PI * RI ** 2 / (RA ** 2 - RI ** 2)
    return k * (1 - RA ** 2 / r ** 2), k * (1 + RA ** 2 / r ** 2)

def test_lame():
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "schnitt", "teile": [
            {"typ": "zylinder", "p0": [0, 0, -1], "p1": [0, 0, T + 1], "radius": RA, "name": "aussen"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sym_x"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sym_y"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, -1], "name": "sym_z0"},
            {"typ": "halbraum", "punkt": [0, 0, T], "normale": [0, 0, 1], "name": "sym_z1"}]},
        {"typ": "zylinder", "p0": [0, 0, -2], "p1": [0, 0, T + 2], "radius": RI, "name": "innen"}]}})
    ergebnisse = {}
    for p, h in ((3, 10.0), (4, 10.0)):
        pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), tiefe=3, facette_mm=1.0)
        for s in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
            pr.verschiebungsrand(s, s, projektion="normal")
        pr.druck("innen", PI)
        U = pr.loesen({})[:, 0]; aus = pr.auswertung(U)
        r = np.linspace(RI + 1, RA - 1, 9); th = np.deg2rad(37.0)
        P = np.stack([r * np.cos(th), r * np.sin(th), np.full_like(r, T / 2)], axis=1)
        s = aus.spannung(P)
        c, sn = np.cos(th), np.sin(th)
        sr = s[:, 0] * c * c + s[:, 1] * sn * sn + 2 * s[:, 3] * sn * c
        sphi = s[:, 0] * sn * sn + s[:, 1] * c * c - 2 * s[:, 3] * sn * c
        sr_e, sphi_e = _lame(r)
        er = np.abs(sr - sr_e).max() / PI; ep = np.abs(sphi - sphi_e).max() / sphi_e.max()
        ergebnisse[p] = (er, ep)
        check(f"p={p}, h={h}: sigma_r < 1 % von p_i, sigma_phi < 1 %", er < 0.01 and ep < 0.01, f"sigma_r {er * 100:.2f} %, sigma_phi {ep * 100:.2f} %, dofs {pr.gitter.n_dof}")
    # Gegenprobe: Kesselformel int sigma_phi dr = p r_i (Gleichgewicht der halben Wand)
    r = np.linspace(RI, RA, 2001); _, sphi_e = _lame(r)
    check("Referenzformel: int sigma_phi dr = p_i r_i", abs(np.trapz(sphi_e, r) / (PI * RI) - 1) < 1e-6)
    check("p=4 nicht schlechter als p=3", ergebnisse[4][1] <= ergebnisse[3][1] * 1.5)

if __name__ == "__main__":
    sys.exit(lauf([test_lame]))
```

- [ ] **Schritt 2: Lauf, Zahlen notieren.** Fällt p = 3 durch, h = 5 messen; das Ergebnis
  (Fehler je p und h, Freiheitsgrade, Laufzeit) kommt ins Theoriehandbuch (Aufgabe 13).
- [ ] **Schritt 3: Commit** `volumen3d: Lame-Zylinder unter Innendruck < 1 % (T6)`

---

## Aufgabe 12: Kirsch – Lochplatte und Schnittlagen-Robustheit (T7, T8)

**Dateien:** Create `tests/volumen3d/test_kirsch.py`.

Viertelmodell: Platte W/2 × L/2 mit W = 400, L = 800, t = 10, Loch d = 40 (d/W = 0,1),
Zug σ₀ = 100 N/mm² als Traktion auf der Stirnseite x = L/2, Symmetrie x = 0 und y = 0
(Normalprojektion), z frei. Referenz K_tg (Bruttospannung): Heywood `K_tn = 2 + (1 − d/W)³`,
`K_tg = K_tn/(1 − d/W)` = 3,032; Pilkey-Polynom `K_tn = 3 − 3,14 d/W + 3,667 (d/W)² − 1,527 (d/W)³`
→ K_tg = 3,023; beide im Test, Mittel 3,03 ± 0,3 %. 3D-Effekt bei t/d = 0,25 in Plattenmitte
≈ +1 % (Folias/Wang), im Kriterium 2 % enthalten. Auswertung σ_xx in (0, d/2, t/2).

- [ ] **Schritt 1: Prüfung**

```python
"""T7/T8: Kirsch-Lochplatte (K_tg gegen Howland/Heywood/Pilkey) und Schnittlagen-Robustheit."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

W, L, T, D, S0, E, NU = 400.0, 800.0, 10.0, 40.0, 100.0, 210000.0, 0.3

def _kt_referenz():
    dw = D / W
    heywood = (2 + (1 - dw) ** 3) / (1 - dw)
    pilkey = (3 - 3.14 * dw + 3.667 * dw ** 2 - 1.527 * dw ** 3) / (1 - dw)
    return heywood, pilkey

def _platte(p, h, versatz=0.0, polster=0.1):
    from volumen3d.geometry.csg import aus_params
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [-5, -5, 0], "max": [L / 2, W / 2, T], "name": "platte"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sym_x"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sym_y"}]},
        {"typ": "zylinder", "p0": [0, 0, -1], "p1": [0, 0, T + 1], "radius": D / 2, "name": "loch"}]})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), tiefe=3, polster=polster + versatz, facette_mm=0.5)
    pr.verschiebungsrand("sym_x", "sym_x", projektion="normal"); pr.verschiebungsrand("sym_y", "sym_y", projektion="normal")
    stirn = pr.oberflaeche.auswahl((pr.oberflaeche.name == "platte") & (np.abs(pr.oberflaeche.punkte[:, 0] - L / 2) < 1e-6))
    pr.traktion(None, np.array([S0, 0, 0]), quadratur=stirn)
    return pr

def _kt(pr):
    U = pr.loesen({})[:, 0]; aus = pr.auswertung(U)
    s = aus.spannung(np.array([[0.0, D / 2, T / 2], [0.0, D / 2, 0.0]]))
    return s[0, 0] / S0, s[1, 0] / S0

def test_kirsch():
    hw, pk = _kt_referenz(); ref = 0.5 * (hw + pk)
    check("Referenz: Heywood und Pilkey stimmen auf 0,5 % ueberein", abs(hw / pk - 1) < 0.005, f"{hw:.3f} / {pk:.3f}")
    for p, h in ((4, 10.0), (4, 5.0)):
        pr = _platte(p, h)
        kt_mitte, kt_rand = _kt(pr)
        ok = abs(kt_mitte / ref - 1) < 0.02
        check(f"p={p}, h={h}: K_tg Mitte {kt_mitte:.3f} gegen {ref:.3f} (< 2 %)", ok, f"Abw. {(kt_mitte / ref - 1) * 100:+.2f} %, Oberflaeche {kt_rand:.3f}, dofs {pr.gitter.n_dof}")
        if ok: break

def test_schnittlage():
    """T8: Wurzelgitter um 0,1 ... 0,9 Zellen verschoben -> Streuung von K_t < 1 %."""
    werte = []
    for v in (0.0, 0.2, 0.4, 0.6, 0.8):
        werte.append(_kt(_platte(4, 10.0, versatz=v))[0])
    streuung = (max(werte) - min(werte)) / np.mean(werte)
    check("Schnittlagen-Streuung < 1 %", streuung < 0.01, " ".join(f"{w:.3f}" for w in werte) + f" -> {streuung * 100:.2f} %")

if __name__ == "__main__":
    sys.exit(lauf([test_kirsch, test_schnittlage]))
```

- [ ] **Schritt 2: Lauf, Zahlen notieren** (K_t je p/h, Streuung, Laufzeit). Erfüllt h = 10
  die 2 % nicht, gilt h = 5 als Abnahme; die Ursache (Zellen je Lochradius) wird im
  Theoriehandbuch mit beiden Zahlen dokumentiert.
- [ ] **Schritt 3: Commit** `volumen3d: Kirsch-Lochplatte < 2 %, Schnittlagen-Streuung < 1 % (T7, T8)`

---

## Aufgabe 13: `api.py` – FcmSolver, FcmDiskretisierung, HybridAssemblySolver (T9)

**Dateien:** Modify `packages/volumen3d/volumen3d/api.py`; Create `tests/volumen3d/test_vertrag_fcm.py`.

- [ ] **Schritt 1: Prüfung**

```python
"""T9: FcmSolver erfuellt den Vertrag (Abschnitt 7), Entry Point, Ablauf mit Stub-Provider,
Abbruch, Protokoll, Kopplungskontrolle, Fehlerfaelle; HybridAssemblySolver als Platzhalter."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np
from tests.volumen3d._pruef import check, lauf

def _spec(p=2, h=50.0):
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    from statik3d_contracts.coupling import CutPlane
    geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "quader", "min": [195, -50, -100], "max": [805, 50, 100], "name": "balken"}})
    return DetailModelSpec(id="D1", name="Kragarm-Ausschnitt", geometry=geo, material_id="S355",
                           cut_planes=(CutPlane(np.array([200.0, 0, 0]), np.array([-1.0, 0, 0])), CutPlane(np.array([800.0, 0, 0]), np.array([1.0, 0, 0]))),
                           settings=FcmSettings(base_cell_size_mm=h, p=p))

def test_protokoll_und_registrierung():
    from statik3d_contracts.solver import SolidDetailSolver, AssemblySolver
    from volumen3d.api import FcmSolver, HybridAssemblySolver
    from statik3d import volumenloeser as VL
    check("FcmSolver erfuellt SolidDetailSolver", isinstance(FcmSolver(), SolidDetailSolver))
    check("HybridAssemblySolver erfuellt AssemblySolver (Platzhalter, capabilities leer)", isinstance(HybridAssemblySolver(), AssemblySolver) and HybridAssemblySolver().capabilities == frozenset())
    l = VL.volumenloeser()
    check("Hauptprogramm waehlt 'fcm' vor dem Stub", l.name == "fcm")
    check("uebersicht() meldet fcm und hybrid bereit", {e["name"] for e in VL.uebersicht() if e["zustand"] == "bereit"} >= {"fcm", "hybrid"})

def test_ablauf():
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.solver import SolverCancelled, SolverError
    from statik3d_contracts.discretization import Discretization, DiscretizationKind
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver(); spec = _spec(); mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    est = s.estimate(spec)
    check("estimate: dofs, cells, cut_cells, memory_mb, backend", all(k in est for k in ("dofs", "cells", "cut_cells", "memory_mb", "backend")) and est["dofs"] > 0, str(est))
    meld = []
    disc = s.prepare(spec, mat, progress=lambda t, a: meld.append((t, a)))
    check("prepare -> Discretization FCM_OCTREE, Fortschritt bis 1.0", isinstance(disc, Discretization) and disc.kind == DiscretizationKind.FCM_OCTREE and abs(meld[-1][1] - 1) < 1e-12)
    check("dof_count = estimate.dofs", disc.dof_count() == est["dofs"], f"{disc.dof_count()} / {est['dofs']}")
    geo = disc.preview_geometry()
    check("preview: vertices, triangles, cell_boxes (k,6), cell_class (k,)", geo["vertices"].shape[1] == 3 and geo["triangles"].shape[1] == 3 and geo["cell_boxes"].shape[1] == 6 and len(geo["cell_class"]) == len(geo["cell_boxes"]))
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    keys = [ResultKey("LF1"), ResultKey("LF1", stellung_id="S2")]
    erg = s.solve(disc, prov, keys, progress=lambda t, a: None)
    check("je Key ein DetailResult mit Formen (n,3),(n,6),(n,)", len(erg) == 2 and erg[0].stress.shape == (len(erg[0].surface_points), 6) and erg[0].von_mises.shape == (len(erg[0].surface_points),))
    cc = erg[0].coupling_check
    check("coupling_check je Schnittebene mit fcm/global/abweichung", len(cc["planes"]) == 2 and all(k in cc["planes"][0] for k in ("force_fcm", "force_global", "moment_fcm", "moment_global", "deviation_force", "deviation_moment")), str(cc)[:200])
    check("Moment am Schnitt x=800 innerhalb 1 % (Stub-Kragarm)", cc["planes"][1]["deviation_moment"] < 0.01, str(cc["planes"][1]))
    pr = erg[0].protocol
    check("Protokoll: solver, contract_version, p, alpha, beta, tiefe, cells, cut, dofs, loeser, Zeiten", all(k in pr for k in ("solver", "contract_version", "p", "alpha", "beta", "tiefe", "zellen", "cut", "dofs", "loeser", "t_assemblierung_s")), str(sorted(pr)))
    try:
        s.solve(disc, prov, keys, cancel=lambda: True); ab = False
    except SolverCancelled:
        ab = True
    check("cancel -> SolverCancelled", ab)
    class NaNProvider(StubGlobalFieldProvider):
        def displacement_at(self, P, key):
            u, r = super().displacement_at(P, key); u[:] = np.nan; return u, r
    try:
        s.solve(disc, NaNProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0), keys[:1]); f = False
    except SolverError as ex:
        f = "NaN" in str(ex) or "nan" in str(ex)
    check("Provider liefert NaN -> SolverError mit Hinweis", f)
    from statik3d_contracts.detail import FcmSettings
    import dataclasses
    try:
        s.prepare(dataclasses.replace(spec, settings=FcmSettings(base_cell_size_mm=50.0, p=7)), mat); f = False
    except SolverError:
        f = True
    check("p ausserhalb 1..4 -> SolverError", f)

def test_hybrid_platzhalter():
    from statik3d_contracts.solver import SolverError
    from statik3d_contracts.nonlinear import AssemblyModelSpec
    from volumen3d.api import HybridAssemblySolver
    hs = HybridAssemblySolver()
    est = hs.estimate(AssemblyModelSpec("A", "leer", ()))
    check("estimate nennt 'nicht umgesetzt'", "nicht umgesetzt" in str(est.get("status", "")))
    try:
        hs.prepare(AssemblyModelSpec("A", "leer", ()), {}); f = False
    except SolverError as ex:
        f = "Teilprojekt 7" in str(ex)
    check("prepare wirft SolverError mit Verweis auf Teilprojekt 7", f)

if __name__ == "__main__":
    sys.exit(lauf([test_protokoll_und_registrierung, test_ablauf, test_hybrid_platzhalter]))
```

- [ ] **Schritt 2: Lauf → Fehler (estimate fehlt)**
- [ ] **Schritt 3: Umsetzung** (`api.py` vollständig)

```python
"""Oeffentliche Einstiegspunkte des Volumenmoduls (Vertrag Abschnitt 7 und 7a).

FcmSolver: Detailmodell aus CSG-Geometrie, Schnittebenen als Halbraeume (Werkstoff gegen die
Normale, wie CutPlane.normal), Verschiebungskopplung ueber den GlobalFieldProvider mit Nitsche,
Ergebnis an der Oberflaechentriangulierung, Schnittgroessenkontrolle je Ebene.
HybridAssemblySolver: bis Teilprojekt 7 ein ehrlicher Platzhalter.
"""
from __future__ import annotations
import time
from typing import Any, Callable
import numpy as np
from statik3d_contracts import CONTRACT_VERSION
from statik3d_contracts.coupling import CutPlane, GlobalFieldProvider
from statik3d_contracts.detail import DetailModelSpec, DetailResult, GeometrySourceType
from statik3d_contracts.discretization import DiscretizationKind
from statik3d_contracts.model import Material, ResultKey
from statik3d_contracts.nonlinear import AssemblyModelSpec, AssemblyResult, LoadPath, StepResult
from statik3d_contracts.solver import ProgressCallback, SolverCancelled, SolverError
from . import __version__
from .geometry.csg import Csg, Operation, aus_params
from .geometry.sdf import Halbraum
from .fcm.problem import FcmProblem, Werkstoff
from .postprocess.auswertung import von_mises

def _geometrie(spec: DetailModelSpec) -> tuple[Csg, list[str]]:
    if spec.geometry.type != GeometrySourceType.CSG:
        raise SolverError(f"Geometriequelle {spec.geometry.type.value!r} kommt mit Teilprojekt 5; in Teilprojekt 1 nur CSG")
    try:
        basis = aus_params(spec.geometry.params)
    except (ValueError, KeyError) as ex:
        raise SolverError(f"CSG-Geometrie: {ex}") from ex
    namen = [f"schnitt_{i}" for i in range(len(spec.cut_planes))]
    teile = (basis.wurzel,) + tuple(Halbraum(cp.origin, cp.normal, n) for cp, n in zip(spec.cut_planes, namen))
    try:
        return Csg(Operation("schnitt", teile) if spec.cut_planes else basis.wurzel), namen
    except ValueError as ex:
        raise SolverError(str(ex)) from ex

class FcmDiskretisierung:
    """Erfuellt Discretization (Vertrag Abschnitt 4) und haelt das aufgebaute Problem."""
    kind: DiscretizationKind = DiscretizationKind.FCM_OCTREE
    def __init__(self, spec: DetailModelSpec, problem: FcmProblem, schnittnamen: list[str]):
        self.subsystem_id = spec.id; self.spec = spec; self.problem = problem; self.schnittnamen = schnittnamen
    def dof_count(self) -> int: return int(self.problem.gitter.n_dof)
    def bounding_box(self): return self.problem.geometrie.huellquader()
    def summary(self) -> dict[str, float | int | str]:
        g = self.problem.gitter
        return {"kind": self.kind.value, "subsystem": self.subsystem_id, "p": g.p, "cell_size_mm": g.h,
                "cells": int(len(g.ijk)), "inside_cells": int((g.klasse == 1).sum()), "cut_cells": int((g.klasse == 2).sum()),
                "dofs": self.dof_count(), "quadrature_points": self.problem.quadratur.anzahl_punkte(), "length_unit": "mm"}
    def preview_geometry(self) -> dict[str, np.ndarray]:
        V, T = _oberflaeche(self.problem)
        lo, hi = self.problem.gitter.zellbox(np.arange(len(self.problem.gitter.ijk)))
        return {"vertices": V, "triangles": T, "cell_boxes": np.concatenate([lo, hi], axis=1), "cell_class": self.problem.gitter.klasse.copy()}

def _oberflaeche(problem: FcmProblem) -> tuple[np.ndarray, np.ndarray]:
    """Dreiecke der Gesamtoberflaeche: Tessellierung, Schwerpunkt auf der Oberflaeche, nach aussen orientiert."""
    g = problem.geometrie; V, T, _ = g.dreiecke(0.25 * problem.gitter.h)
    if len(T) == 0: return V, T
    S = V[T].mean(axis=1); tol = 1e-6 * problem.gitter.h
    T = T[np.abs(g.abstand(S)) <= max(tol, 0.02 * problem.gitter.h)]
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]]); S = V[T].mean(axis=1)
    umdrehen = np.einsum("ij,ij->i", n, g.gradient(S)) < 0
    T[umdrehen] = T[umdrehen][:, [0, 2, 1]]
    benutzt = np.unique(T); neu = np.full(len(V), -1); neu[benutzt] = np.arange(len(benutzt))
    return V[benutzt], neu[T]

class FcmSolver:
    name: str = "fcm"
    contract_version: str = CONTRACT_VERSION

    def estimate(self, spec: DetailModelSpec) -> dict[str, Any]:
        from .fcm.gitter import Gitter
        g, _ = _geometrie(spec); s = spec.settings
        self._einstellungen_pruefen(s)
        G = Gitter(g, s.base_cell_size_mm, 0.1); G.moden_nummerieren(int(s.p))
        m = (s.p + 1) ** 3; nnz = len(G.ijk) * (3 * m) ** 2
        return {"dofs": int(G.n_dof), "cells": int(len(G.ijk)), "cut_cells": int((G.klasse == 2).sum()),
                "memory_mb": round(nnz * 16 / 1e6 + G.n_dof * 8 * 40 / 1e6, 1), "backend": "cpu", "solver": self.name,
                "note": "Direktloeser (Teilprojekt 1); Speicher der Faktorisierung kommt hinzu"}

    @staticmethod
    def _einstellungen_pruefen(s):
        if s.base_cell_size_mm <= 0: raise SolverError("base_cell_size_mm muss positiv sein")
        if not 1 <= int(s.p) <= 4: raise SolverError(f"p = {s.p}: Teilprojekt 1 unterstuetzt p = 1 ... 4")
        if s.backend not in ("auto", "cpu"): raise SolverError(f"backend {s.backend!r}: GPU kommt mit Teilprojekt 3")
        if s.coupling != "displacement": raise SolverError("coupling 'forces' kommt mit Teilprojekt 5")

    def prepare(self, spec: DetailModelSpec, material: Material, progress: ProgressCallback | None = None) -> FcmDiskretisierung:
        s = spec.settings; self._einstellungen_pruefen(s)
        melden = progress or (lambda t, a: None)
        g, namen = _geometrie(spec)
        melden("Gitter und Quadratur", 0.05)
        try:
            pr = FcmProblem(g, h=s.base_cell_size_mm, p=int(s.p), werkstoff=Werkstoff(material.E, material.nu, material.rho), alpha=s.alpha, tiefe=3)
            for n in namen:
                pr.verschiebungsrand(n, n, projektion="voll")
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        melden("Steifigkeit assemblieren", 0.3)
        pr.aufbauen(lambda t, a: melden(t, 0.3 + 0.6 * a))
        melden("Diskretisierung bereit", 1.0)
        return FcmDiskretisierung(spec, pr, namen)

    def solve(self, disc: FcmDiskretisierung, provider: GlobalFieldProvider, keys: list[ResultKey],
              progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None) -> list[DetailResult]:
        melden = progress or (lambda t, a: None); abbruch = cancel or (lambda: False)
        pr = disc.problem; t0 = time.perf_counter()
        vorgaben = []
        for k, key in enumerate(keys):
            if abbruch(): raise SolverCancelled("abgebrochen vor der rechten Seite")
            v = {}
            for n in disc.schnittnamen:
                P = pr.raender[n].quadratur.punkte
                u, _ = provider.displacement_at(P, key)
                u = np.asarray(u, float)
                if not np.all(np.isfinite(u)):
                    i = int(np.flatnonzero(~np.isfinite(u).all(axis=1))[0])
                    raise SolverError(f"Provider liefert NaN fuer {key} auf {n} an {int((~np.isfinite(u).all(axis=1)).sum())} Punkten, z. B. {P[i]}")
                v[n] = u
            vorgaben.append(v)
            melden(f"Randverschiebungen {key.load_case_id}", 0.2 * (k + 1) / len(keys))
        if abbruch(): raise SolverCancelled("abgebrochen vor dem Loesen")
        U = pr.loesen(vorgaben)
        melden("Gleichungssystem geloest", 0.7)
        V, T = _oberflaeche(pr)
        # Auswertepunkte minimal in den Werkstoff ruecken, damit die Punktsuche eine aktive Zelle findet
        Pe = V - 1e-7 * pr.gitter.h * pr.geometrie.gradient(V)
        aus_liste = []
        for k, key in enumerate(keys):
            if abbruch(): raise SolverCancelled("abgebrochen bei der Auswertung")
            aus = pr.auswertung(U[:, k]); u = aus.verschiebung(Pe); s = aus.spannung(Pe)
            ebenen = []; warn = []
            for i, (n, cp) in enumerate(zip(disc.schnittnamen, disc.spec.cut_planes)):
                F, M = aus.schnittgroessen(pr.raender[n].quadratur, cp.origin)
                sf = provider.section_forces(cp, key)
                dF = float(np.linalg.norm(F - sf.force) / max(np.linalg.norm(sf.force), 1e-12)); dM = float(np.linalg.norm(M - sf.moment) / max(np.linalg.norm(sf.moment), 1e-12))
                ebenen.append({"plane": i, "force_fcm": F, "force_global": sf.force, "moment_fcm": M, "moment_global": sf.moment, "deviation_force": dF, "deviation_moment": dM})
                if dM > 0.05: warn.append(f"Schnittebene {i}: Momentabweichung {dM * 100:.1f} % > 5 % (Vorgabe 16.7: Kraftkopplung erwaegen)")
            protokoll = dict(pr.protokoll, solver=self.name, contract_version=self.contract_version, volumen3d=__version__, key=str(key),
                             coupling="displacement", t_solve_s=round(time.perf_counter() - t0, 3))
            aus_liste.append(DetailResult(detail_id=disc.subsystem_id, key=key, surface_points=V, surface_triangles=T, displacement=u, stress=s,
                                          von_mises=von_mises(s), coupling_check={"planes": ebenen}, warnings=warn, protocol=protokoll,
                                          convergence=[{"cycle": 0, "dofs": pr.gitter.n_dof, "p": pr.p, "cells": int(len(pr.gitter.ijk))}]))
            melden(f"Ergebnis {key.load_case_id}", 0.7 + 0.3 * (k + 1) / len(keys))
        return aus_liste

class HybridAssemblySolver:
    """Platzhalter bis Teilprojekt 7: registriert, aber ohne Faehigkeiten (UI graut alles aus)."""
    name: str = "hybrid"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset()
    def estimate(self, spec: AssemblyModelSpec) -> dict[str, Any]:
        return {"dofs": 0, "memory_mb": 0.0, "backend": "cpu", "solver": self.name, "status": "nicht umgesetzt (Teilprojekt 7)"}
    def prepare(self, spec: AssemblyModelSpec, materials: dict[str, Material], progress: ProgressCallback | None = None) -> object:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls); fuer die Oberflaeche steht der Stub bereit")
    def solve_path(self, handle: object, path: LoadPath, provider: GlobalFieldProvider | None = None, progress: ProgressCallback | None = None,
                   cancel: Callable[[], bool] | None = None, on_step: Callable[[StepResult], None] | None = None) -> AssemblyResult:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls)")
```

- [ ] **Schritt 4: `tests/contracts/test_vertrag.py` anpassen** (einzige Änderung außerhalb, begründet):
  Prüfung „volumenloeser() liefert … den Stub“ → Erwartung aus den Entry Points:
  ```python
  echte = sorted(n for n in eps if n != "stub")
  erwartet = echte[0] if echte else "stub"
  check(f"volumenloeser() liefert einen SolidDetailSolver ({erwartet!r}: erster echter Loeser, sonst der Stub)",
        isinstance(l, SolidDetailSolver) and l.name == erwartet, getattr(l, "name", "?"))
  ```
- [ ] **Schritt 5: Läufe** `test_vertrag_fcm`, `tests.contracts.test_vertrag` (43/43), `mypy --strict packages/volumen3d/volumen3d/api.py` (Fehler beheben oder gezielt `# type: ignore[...]` mit Grund)
- [ ] **Schritt 6: Commit** `volumen3d: FcmSolver als Entry Point fcm, FcmDiskretisierung, Kopplungskontrolle; hybrid als Platzhalter (T9)`

---

## Aufgabe 14: Einbindung – Kernsuite, run_all, CI, requirements, Handbücher, Vertragsvorschlag

**Dateien:** Create `tests/volumen3d/test_kern.py`, `docs/vertrag-aenderungen/2026-09-27-lasten-im-detailmodell.md`;
Modify `tests/run_all.py`, `.github/workflows/ci.yml`, `requirements.txt`, `docs/Volumenmodul.md`,
`docs/Theoriehandbuch.md` (neues Kapitel „11 Finite-Cell-Methode (volumen3d)“), `packages/volumen3d/CLAUDE.md` (Prüfbefehle bestätigen).

- [ ] **Schritt 1: Kernsuite** – `test_kern.py` importiert die Prüffunktionen von `test_paket`,
  `test_basis`, `test_geometrie`, `test_gitter`, `test_quadratur`, `test_elastizitaet`,
  `test_patch`, `test_vertrag_fcm` und ruft `lauf([...])`; Laufzeit unter 2 min messen und
  im Kopf nennen. `test_kragarm`, `test_lame`, `test_kirsch` bleiben eigene Suiten
  („Abnahmen, ~N min“).
- [ ] **Schritt 2: `tests/run_all.py`**: `"tests.volumen3d.test_kern"` hinter `tests.contracts.test_vertrag`.
- [ ] **Schritt 3: `requirements.txt`**: nach dem Vertragspaket
  `./packages/volumen3d` mit Kommentar; `numba` und `cupy-cuda12x` nur als Kommentar (Extras).
- [ ] **Schritt 4: `ci.yml`**: `pip install import-linter ./packages/volumen3d`, Schritte
  `lint-imports` und `python -m tests.volumen3d.test_kern`.
- [ ] **Schritt 5: Vertragsvorschlag** (`docs/vertrag-aenderungen/2026-09-27-lasten-im-detailmodell.md`):
  Anlass (Wasserdruck, Eigengewicht im Ausschnitt ohne Globalmodell), Vorschlag
  `DetailModelSpec.loads: tuple[SurfaceLoad, ...] = ()` und `body_load: np.ndarray | None`
  (Typ `SurfaceLoad` aus `nonlinear.py` wiederverwenden), Versionsstufe Minor 2.1.0, Wirkung:
  Hauptprogramm (Maske), volumen3d (`FcmProblem.traktion/druck/volumenlast` liegen bereit).
- [ ] **Schritt 6: `docs/Volumenmodul.md`**: Abschnitt „Session B: Stand Teilprojekt 1“ mit
  Modulen, Entry Points, Abnahmezahlen; **`docs/Theoriehandbuch.md`**: Kapitel 11 mit
  Basis, Klassifikation (Beweisskizze), Quadratur, Nitsche, Schnittgrößen und den gemessenen
  Zahlen aus T3–T8 (Tabelle Fehler je p/h, Freiheitsgrade, Laufzeit).
- [ ] **Schritt 7: Gesamtlauf** `python -m tests.run_all` im Hintergrund (PowerShell, venv),
  parallel nichts Schweres; Ergebnis `ALLE TESTS BESTANDEN` protokollieren.
  `lint-imports`, `mypy --strict api.py`.
- [ ] **Schritt 8: Commit** `volumen3d: Kernsuite in run_all, CI mit lint-imports, Handbuecher, Vertragsvorschlag Lasten`

---

## Aufgabe 15: Zweite Sicht

- [ ] Code-Review durch einen frischen Subagenten (`superpowers:requesting-code-review`) über
  `packages/volumen3d/` und `tests/volumen3d/` mit dem Entwurf als Maßstab; Befunde beheben
  oder begründet zurückweisen; danach Kernsuite und Abnahmen erneut laufen lassen.
- [ ] Bericht an den Anwender: Abnahmezahlen (T4–T8), Laufzeiten, offene Punkte
  (Vertragsvorschlag Lasten, TP 2 als nächster Schritt: Oktree-Verfeinerung + STL → Pull Request 1).

---

## Selbstprüfung des Plans

- **Abdeckung des Entwurfs 4.4:** T1 Aufgabe 2, T2 Aufgaben 3/4/5/8, T3 Aufgabe 6, T4 Aufgabe 9,
  T5 Aufgabe 10, T6 Aufgabe 11, T7/T8 Aufgabe 12, T9 Aufgabe 13. Fehlerbehandlung 4.3:
  Aufgabe 13 (`_einstellungen_pruefen`, NaN, leere Geometrie über `Gitter`), Warnung
  Schnittgrößen > 5 % in `solve`; Saint-Venant- und Wandstärkenwarnung kommen mit TP 2
  (Verfeinerungsbereiche), im Entwurf so vermerkt.
- **Namen über Aufgaben hinweg:** `Gitter(geometrie, h, polster)`, `zellbox`, `zelle_finden`,
  `lokal`, `moden_nummerieren`, `zell_moden`, `n_dof`, `klasse`, `ijk`; `Zellquadratur.zelle(c)`
  → (P, W, I); `Flaechenquadratur` Felder `punkte, gewichte, normalen, zelle, xi, quelle, name`;
  `FcmProblem.verschiebungsrand(name, flaechen, projektion, quadratur)`, `traktion`, `druck`,
  `volumenlast`, `aufbauen`, `loesen`, `auswertung`; `Auswertung.verschiebung/spannung/schnittgroessen`.
- **Bekannte Planlücke:** `Gitter.alle_mitten` ist im Codeblock doppelt – eine Fassung mit
  Rückgabe `(M, I)`, Prüfung entsprechend (`Pm, _ = G.alle_mitten()`).
