# Schnittstellenvertrag Statik3D ↔ Volumenmodul `volumen3d`

> **Verbindlich für beide Entwicklungsstränge.** Das Hauptprogramm (Statik3D) und das Volumenmodul (`volumen3d`, FCM und FE-Hexaeder, Kontakt, Plastizität) dürfen sich ausschließlich über die hier definierten Typen und Protokolle kennen. Änderungen an diesem Vertrag erfolgen nur per eigenem Pull Request mit Versionserhöhung (Abschnitt 9).

**Vertragsversion:** 2.0.0 (Änderungen siehe Abschnitt 9)
**Sprache:** Python ≥ 3.11, Typisierung mit `dataclasses` und `typing.Protocol`, numerische Felder als `numpy.ndarray`.

---

## 1. Repository-Struktur (Monorepo auf GitHub)

```
statik3d/                      # Repository-Wurzel
├── packages/
│   ├── statik3d_contracts/    # NUR dieser Vertrag als Code – keine Logik
│   │   └── statik3d_contracts/
│   │       ├── __init__.py
│   │       ├── units.py
│   │       ├── model.py
│   │       ├── discretization.py
│   │       ├── coupling.py
│   │       ├── detail.py
│   │       ├── nonlinear.py   # ab 1.1: Mehrkörper, Kontakt, Plastizität
│   │       ├── solver.py
│   │       └── testing.py     # Stubs
│   ├── statik3d/              # Hauptprogramm (UI, Globalmodell, Stab-/Schalenlöser)
│   └── volumen3d/             # Volumenmodul (ohne UI-Abhängigkeit)
│       └── volumen3d/
│           ├── api.py         # einzige öffentliche Einstiegspunkte (Entry Points)
│           ├── geometry/      # Geometriekern, SDF, BVH, Punktwolken
│           ├── fcm/           # Octree, Schnittzellen-Integration, FCM-Ansätze
│           ├── hex/           # FE-Hexaeder für einfache Körper, strukturierter Rotationsvernetzer
│           ├── material/      # linear elastisch, J2-Plastizität (Return Mapping)
│           ├── contact/       # Kontaktsuche, Kontaktformulierungen, Tie
│           ├── nonlinear/     # Newton-Treiber, Schrittsteuerung, Checkpoints
│           ├── linalg/        # Sparse-Direktlöser, PCG, Mehrgitter, GPU-Kernels
│           └── postprocess/   # Spannungsrückgewinnung, Hot-Spot, Kontaktauswertung
├── tests/
│   ├── contracts/             # Prüft, dass beide Seiten den Vertrag erfüllen
│   └── reference_models/      # Gemeinsame Referenzmodelle (Abschnitt 8)
└── .github/workflows/ci.yml   # Tests für alle drei Pakete bei jedem PR
```

**Abhängigkeitsregeln (per CI geprüft, z. B. mit `import-linter`):**
- `statik3d_contracts` importiert nur Standardbibliothek und `numpy`.
- `volumen3d` importiert `statik3d_contracts`, **niemals** `statik3d`.
- `statik3d` importiert `statik3d_contracts` und `volumen3d` nur über die Registrierung in Abschnitt 7, nie interne Module von `volumen3d`.

**Arbeitsteilung paralleler Sessions:**
- Session A arbeitet ausschließlich in `packages/statik3d/`.
- Session B arbeitet ausschließlich in `packages/volumen3d/`.
- `packages/statik3d_contracts/` und `tests/reference_models/` werden von keiner Session eigenmächtig geändert.
- Jede Session auf eigenem Branch (`feature/3d-solver`, `feature/volumen3d`), Zusammenführung per Pull Request mit grüner CI.

---

## 2. Einheiten und Konventionen (`units.py`)

| Größe | Einheit |
|---|---|
| Länge | mm |
| Kraft | N |
| Spannung, E-Modul | N/mm² (= MPa) |
| Moment | N·mm |
| Dichte | kg/mm³ (intern), Anzeige in kg/m³ |
| Winkel, Rotation | rad |
| Temperatur | °C |

- **Globales Koordinatensystem:** rechtshändig, **Z nach oben**. Höhen im Modell sind relativ; der Bezug zum Höhensystem (NHN) wird als `height_datum_offset_mm` am Modell geführt und nur für Wasserdruck und Anzeige verwendet.
- **Vorzeichen:** Zugspannung positiv.
- **Spannungstensor in Voigt-Notation, Reihenfolge verbindlich:** `[σxx, σyy, σzz, τxy, τyz, τxz]`.
- **Punktlisten:** `ndarray` der Form `(n, 3)`, `dtype=float64`.
- **IDs:** nichtleere Strings, eindeutig je Typ, unveränderlich nach Anlage.

```python
# units.py
from typing import Final

LENGTH: Final = "mm"
FORCE: Final = "N"
STRESS: Final = "N/mm2"
VOIGT_ORDER: Final = ("xx", "yy", "zz", "xy", "yz", "xz")
```

---

## 3. Modellbezogene Typen (`model.py`)

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Material:
    id: str
    name: str
    E: float                 # N/mm²
    nu: float
    rho: float = 0.0         # kg/mm³
    fy: float | None = None  # N/mm², für Auslastung

@dataclass(frozen=True)
class ResultKey:
    """Adressiert einen Ergebniszustand des Globalmodells."""
    load_case_id: str
    stellung_id: str | None = None      # None = Grundstellung / keine Stellungen
    combination_id: str | None = None   # gesetzt, wenn Kombination statt Lastfall

@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    contract_version: str
    height_datum_offset_mm: float = 0.0
    materials: tuple[Material, ...] = field(default_factory=tuple)
```

---

## 4. Diskretisierungs-Abstraktion (`discretization.py`)

Ersetzt im Hauptprogramm die Annahme „Netz = Knoten + Elemente“.

```python
from enum import Enum
from typing import Protocol, runtime_checkable
import numpy as np

class DiscretizationKind(str, Enum):
    FE_MESH = "fe_mesh"          # Stäbe, Schalen, klassische Volumenelemente
    FCM_OCTREE = "fcm_octree"    # Finite-Cell-Methode

@runtime_checkable
class Discretization(Protocol):
    kind: DiscretizationKind
    subsystem_id: str            # Globalmodell, Stellung oder Detailmodell

    def dof_count(self) -> int: ...
    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]: ...
    def summary(self) -> dict[str, float | int | str]: ...
    def preview_geometry(self) -> dict[str, np.ndarray]:
        """Darstellungsdaten für die UI, z. B. {'vertices': (n,3), 'triangles': (m,3), 'cell_boxes': (k,6)}."""
        ...
```

---

## 5. Kopplung Globalmodell → Detail (`coupling.py`)

Das **Hauptprogramm implementiert** diesen Provider, das **FCM-Modul nutzt** ihn.

```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
import numpy as np
from .model import ResultKey

@dataclass(frozen=True)
class CutPlane:
    origin: np.ndarray    # (3,)
    normal: np.ndarray    # (3,), Einheitsvektor, zeigt aus dem Detail heraus

@dataclass(frozen=True)
class SectionForces:
    """Resultierende am Schnitt, bezogen auf CutPlane.origin, globale Achsen."""
    force: np.ndarray     # (3,) N
    moment: np.ndarray    # (3,) N·mm

@runtime_checkable
class GlobalFieldProvider(Protocol):
    def available_keys(self) -> list[ResultKey]: ...

    def displacement_at(
        self, points: np.ndarray, key: ResultKey
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Verschiebung u (n,3) in mm und Rotation (n,3) in rad an beliebigen Punkten.
        Für Punkte im Querschnittsbereich eines Stabs liefert der Provider die
        Querschnittskinematik (Starrkörper + Rotation, optional Verwölbung),
        für Schalen die lineare Verteilung über die Dicke.
        Punkte ohne Zuordnung: NaN, der Aufrufer muss das prüfen.
        """
        ...

    def section_forces(self, plane: CutPlane, key: ResultKey) -> SectionForces:
        """Schnittgrößen des Globalmodells am Schnitt, für die Plausibilitätskontrolle."""
        ...
```

**Zusage des Hauptprogramms:** `displacement_at` ist vektorisiert (keine Python-Schleife je Punkt) und für 10⁵ Punkte in unter 1 s aufrufbar.

---

## 6. Detailmodell und Ergebnis (`detail.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from .model import ResultKey
from .coupling import CutPlane

class GeometrySourceType(str, Enum):
    STL = "stl"
    STEP = "step"
    POINT_CLOUD = "point_cloud"    # z. B. .e57, .las, .ply
    VOXEL = "voxel"
    CSG = "csg"                    # parametrischer Aufbau
    FROM_GLOBAL = "from_global"    # aus Globalmodell ausgeschnitten

@dataclass(frozen=True)
class GeometrySource:
    type: GeometrySourceType
    path: str | None = None
    params: dict = field(default_factory=dict)

@dataclass(frozen=True)
class RefinementRegion:
    center: np.ndarray       # (3,)
    radius_mm: float
    target_cell_size_mm: float
    p: int | None = None

@dataclass(frozen=True)
class WeldLine:
    id: str
    points: np.ndarray       # (n,3) Nahtübergang als Polylinie
    plate_thickness_mm: float
    method: str = "hot_spot"  # "hot_spot" | "effective_notch"

@dataclass(frozen=True)
class FcmSettings:
    base_cell_size_mm: float
    p: int = 3
    alpha: float = 1e-8
    tolerance: float = 1e-8
    adaptive_cycles: int = 0
    backend: str = "auto"     # "auto" | "cpu" | "gpu"
    coupling: str = "displacement"  # "displacement" | "forces"

@dataclass(frozen=True)
class DetailModelSpec:
    id: str
    name: str
    geometry: GeometrySource
    material_id: str
    cut_planes: tuple[CutPlane, ...]
    settings: FcmSettings
    refinement: tuple[RefinementRegion, ...] = ()
    weld_lines: tuple[WeldLine, ...] = ()

@dataclass
class HotSpotResult:
    weld_line_id: str
    position: np.ndarray     # (3,)
    stress: float            # N/mm², maßgebende Komponente
    method: str

@dataclass
class DetailResult:
    detail_id: str
    key: ResultKey
    surface_points: np.ndarray      # (n,3)
    surface_triangles: np.ndarray   # (m,3) int
    displacement: np.ndarray        # (n,3) mm
    stress: np.ndarray              # (n,6) Voigt, N/mm²
    von_mises: np.ndarray           # (n,)
    hot_spots: list[HotSpotResult] = field(default_factory=list)
    convergence: list[dict] = field(default_factory=list)  # je Zyklus: dofs, iterations, hotspot_max ...
    coupling_check: dict = field(default_factory=dict)     # Abweichung Schnittgrößen
    warnings: list[str] = field(default_factory=list)
    protocol: dict = field(default_factory=dict)           # alle Einstellungen, für Prüffähigkeit
```

---

## 6a. Mehrkörpermodelle, Kontakt und Plastizität (`nonlinear.py`, ab Version 1.1)

Rein additiv: Alle bestehenden Typen bleiben unverändert gültig. Ein linearer Einkörper-Detailnachweis nutzt weiterhin `DetailModelSpec`, ein nichtlineares Mehrkörpermodell (z. B. Drehlager) nutzt `AssemblyModelSpec`.

**Grundregel Nichtlinearität:** Es gilt **keine Superposition**. Ergebnisse entstehen nur entlang eines definierten Lastpfads (`LoadPath`). Lastfälle werden nicht einzeln gelöst und überlagert; jede Kombination bzw. Stellungsfolge ist ein eigener Lauf.

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from .model import ResultKey
from .coupling import CutPlane
from .detail import GeometrySource, RefinementRegion, WeldLine, FcmSettings
from .discretization import DiscretizationKind

# ---------- Materialmodelle ----------

class HardeningType(str, Enum):
    NONE = "none"                  # ideal-plastisch
    ISOTROPIC = "isotropic"
    KINEMATIC = "kinematic"        # linear kinematisch (Prager)
    COMBINED = "combined"

@dataclass(frozen=True)
class ElastoPlasticJ2:
    """Von-Mises-Plastizität, kleine Dehnungen in Stufe A."""
    material_id: str               # verweist auf Material (E, nu, fy)
    hardening: HardeningType = HardeningType.ISOTROPIC
    # Fließkurve: Stützpunkte (plastische Vergleichsdehnung [-], Fließspannung [N/mm²]),
    # erster Punkt muss (0.0, fy) sein; ein Punkt = ideal-plastisch
    flow_curve: tuple[tuple[float, float], ...] = ()
    strain_limit: float | None = 0.05   # Grenzdehnung für Nachweis, z. B. 5 % nach EC3-1-5 Anhang C

@dataclass(frozen=True)
class LinearElasticModel:
    material_id: str

MaterialModel = LinearElasticModel | ElastoPlasticJ2

# ---------- Körper ----------

@dataclass(frozen=True)
class FeHexSettings:
    """Klassische Vernetzung für Körper mit einfacher Geometrie (Bolzen, Buchse, Ring)."""
    order: int = 2                     # 2 = Hex20/Hex27
    element_size_mm: float = 5.0
    mesher: str = "revolve"            # "revolve" (strukturiert, Rotationskörper) | "gmsh"
    refinement: tuple[RefinementRegion, ...] = ()

@dataclass(frozen=True)
class Body:
    id: str
    name: str
    geometry: GeometrySource
    material: MaterialModel
    discretization: DiscretizationKind          # FE_MESH oder FCM_OCTREE
    fe_settings: FeHexSettings | None = None     # Pflicht bei FE_MESH
    fcm_settings: FcmSettings | None = None      # Pflicht bei FCM_OCTREE
    exact_surface: str | None = None             # z. B. "cylinder" – exakte Normalen für Kontakt

# ---------- Flächen, Kontakt, feste Verbindungen ----------

@dataclass(frozen=True)
class SurfaceSelector:
    """Auswahl einer Körperoberfläche. Genau eine Variante belegen."""
    body_id: str
    named_surface: str | None = None       # benannte Fläche aus CAD/CSG, z. B. "bohrung"
    box: tuple[np.ndarray, np.ndarray] | None = None   # (min, max) Auswahlbox
    cylinder: tuple[np.ndarray, np.ndarray, float] | None = None  # (Achspunkt, Achsrichtung, Radius ± Toleranz)

class ContactFormulation(str, Enum):
    PENALTY = "penalty"
    AUGMENTED_LAGRANGE = "augmented_lagrange"   # Standard
    MORTAR = "mortar"                           # Segment-zu-Segment, später dual

class FrictionModel(str, Enum):
    FRICTIONLESS = "frictionless"
    COULOMB = "coulomb"
    STICK = "stick"                             # haftend, aber abhebend möglich

@dataclass(frozen=True)
class ContactPair:
    id: str
    master: SurfaceSelector                     # i. d. R. steifere / gröber diskretisierte Seite
    slave: SurfaceSelector
    friction: FrictionModel = FrictionModel.FRICTIONLESS
    mu: float = 0.0
    initial_clearance_mm: float | None = None   # None = aus Geometrie; Wert überschreibt (Lagerspiel)
    formulation: ContactFormulation = ContactFormulation.AUGMENTED_LAGRANGE
    penalty_factor: float | None = None         # None = automatisch aus Steifigkeit

@dataclass(frozen=True)
class Tie:
    """Feste Verbindung zweier Flächen (Schweißnaht vereinfacht, Presssitz ohne Schlupf, FE–FCM-Kopplung)."""
    id: str
    a: SurfaceSelector
    b: SurfaceSelector

@dataclass(frozen=True)
class Support:
    """Lagerung direkt am Körper (wenn nicht über Globalmodell-Kopplung)."""
    id: str
    surface: SurfaceSelector
    fixed_dofs: tuple[bool, bool, bool] = (True, True, True)

@dataclass(frozen=True)
class SurfaceLoad:
    id: str
    surface: SurfaceSelector
    load_case_id: str
    pressure: float | None = None               # N/mm², positiv = auf Fläche drückend
    traction: np.ndarray | None = None          # (3,) N/mm², global
    resultant: tuple[np.ndarray, np.ndarray] | None = None  # (Kraft N, Moment N·mm), über Fläche verteilt

# ---------- Lastpfad ----------

@dataclass(frozen=True)
class LoadState:
    """Ein Zielzustand im Lastpfad. Faktor skaliert Globalmodell-Kopplung und direkte Lasten."""
    key: ResultKey
    factor: float = 1.0
    increments: int = 10                         # Startwert, adaptive Schrittsteuerung darf anpassen
    label: str = ""

@dataclass(frozen=True)
class LoadPath:
    """Geordnete Folge von Zuständen, z. B. Eigengewicht → Wasserdruck → Stellung 1 → Stellung 2 → …
    Plastische Verformungen und Kontaktzustände werden von Zustand zu Zustand mitgenommen."""
    id: str
    states: tuple[LoadState, ...]
    start_from_checkpoint: str | None = None     # ID eines gespeicherten Zustands (Verzweigung)
    save_checkpoints: bool = True

@dataclass(frozen=True)
class NonlinearSettings:
    max_newton_iterations: int = 30
    tol_residual: float = 1e-6                   # relativ
    tol_displacement: float = 1e-6
    tol_energy: float = 1e-10
    line_search: bool = True
    adaptive_stepping: bool = True               # Schrittweitenhalbierung bei Divergenz
    min_increment_factor: float = 1e-4
    stabilization: str = "auto"                  # "auto" | "springs" | "viscous" | "none" – für anfangs freie Körper im Spiel
    linear_solver: str = "auto"                  # "auto" | "direct" | "pcg_mg"
    backend: str = "auto"                        # "auto" | "cpu" | "gpu"

# ---------- Gesamtmodell ----------

@dataclass(frozen=True)
class AssemblyModelSpec:
    id: str
    name: str
    bodies: tuple[Body, ...]
    contacts: tuple[ContactPair, ...] = ()
    ties: tuple[Tie, ...] = ()
    supports: tuple[Support, ...] = ()
    loads: tuple[SurfaceLoad, ...] = ()
    cut_planes: tuple[CutPlane, ...] = ()        # Kopplung an Globalmodell (optional)
    weld_lines: tuple[WeldLine, ...] = ()
    load_paths: tuple[LoadPath, ...] = ()
    settings: NonlinearSettings = field(default_factory=NonlinearSettings)

# ---------- Ergebnisse ----------

@dataclass
class ContactResult:
    pair_id: str
    points: np.ndarray            # (n,3) Auswertepunkte auf der Slave-Fläche
    pressure: np.ndarray          # (n,) N/mm²
    gap: np.ndarray               # (n,) mm, negativ = Durchdringung (sollte ≈ 0 sein)
    slip: np.ndarray              # (n,3) mm, akkumuliert
    status: np.ndarray            # (n,) int: 0 offen, 1 haftend, 2 gleitend
    resultant_force: np.ndarray   # (3,) N

@dataclass
class BodyResult:
    body_id: str
    surface_points: np.ndarray    # (n,3)
    surface_triangles: np.ndarray # (m,3)
    displacement: np.ndarray      # (n,3) mm
    stress: np.ndarray            # (n,6) Voigt, N/mm²
    von_mises: np.ndarray         # (n,)
    plastic_strain_eq: np.ndarray | None = None   # (n,) plastische Vergleichsdehnung [-]

@dataclass
class StepResult:
    path_id: str
    state_index: int
    load_factor: float            # innerhalb des Zustands, 0..1
    converged: bool
    newton_iterations: int
    bodies: list[BodyResult] = field(default_factory=list)
    contacts: list[ContactResult] = field(default_factory=list)
    reaction_forces: dict[str, np.ndarray] = field(default_factory=dict)  # Support-ID → (3,)

@dataclass
class AssemblyResult:
    assembly_id: str
    path_id: str
    steps: list[StepResult]                        # nur Ausgabeschritte, nicht jede Iteration
    checkpoints: list[str] = field(default_factory=list)
    max_plastic_strain: dict[str, float] = field(default_factory=dict)   # Körper-ID → max
    max_contact_pressure: dict[str, float] = field(default_factory=dict) # Paar-ID → max
    coupling_check: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    protocol: dict = field(default_factory=dict)
```

**Verbindliche Regeln zu 6a:**
- `Body.fe_settings` ist genau dann gesetzt, wenn `discretization == FE_MESH`; `fcm_settings` genau dann, wenn `FCM_OCTREE`. Verstöße → `SolverError` in `prepare`.
- Kontakt und `Tie` werden **unabhängig von der Diskretisierungsart** über Oberflächen-Quadraturpunkte formuliert. FE–FE, FE–FCM und FCM–FCM müssen über denselben Code laufen.
- Plastische Körper mit FCM verwenden für geschnittene Zellen die rekursive Unterteilung, **kein Moment Fitting**.
- Ergebniszustände sind nur als `StepResult` entlang eines `LoadPath` gültig; ein `AssemblyResult` darf nie mit einem anderen überlagert werden. Die UI muss das kenntlich machen (keine Superpositionsfunktion für diese Ergebnisse anbieten).

---

## 7. Löser-Protokoll und Registrierung (`solver.py`)

```python
from typing import Callable, Protocol, runtime_checkable
from .detail import DetailModelSpec, DetailResult
from .discretization import Discretization
from .coupling import GlobalFieldProvider
from .model import Material, ResultKey

ProgressCallback = Callable[[str, float], None]   # (Meldung, Anteil 0..1)

class SolverCancelled(Exception): ...
class SolverError(Exception): ...

@runtime_checkable
class SolidDetailSolver(Protocol):
    name: str
    contract_version: str

    def estimate(self, spec: DetailModelSpec) -> dict:
        """Schnell: erwartete DOF, Speicherbedarf (MB), Backend. Ohne Rechnung."""
        ...

    def prepare(
        self, spec: DetailModelSpec, material: Material,
        progress: ProgressCallback | None = None,
    ) -> Discretization:
        """Geometrie laden, Octree bauen, Schnittzellen integrieren. Wiederverwendbar für alle Keys."""
        ...

    def solve(
        self, disc: Discretization, provider: GlobalFieldProvider,
        keys: list[ResultKey],
        progress: ProgressCallback | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> list[DetailResult]:
        """Löst alle Keys mit derselben Diskretisierung (nur rechte Seiten ändern sich)."""
        ...

# Registrierung ohne direkte Imports: Python Entry Points
# In packages/volumen3d/pyproject.toml:
# [project.entry-points."statik3d.solid_solvers"]
# fcm = "volumen3d.api:FcmSolver"
```

Das Hauptprogramm lädt Löser über `importlib.metadata.entry_points(group="statik3d.solid_solvers")`. Dadurch kennt `statik3d` keine internen Module von `volumen3d`.

### 7a. Nichtlinearer Mehrkörperlöser (ab Version 1.1)

Eigenes, zusätzliches Protokoll; `SolidDetailSolver` bleibt unverändert.

```python
from typing import Callable, Protocol, runtime_checkable
from .nonlinear import AssemblyModelSpec, AssemblyResult, LoadPath, StepResult
from .coupling import GlobalFieldProvider
from .model import Material

@runtime_checkable
class AssemblySolver(Protocol):
    name: str
    contract_version: str
    capabilities: frozenset[str]
    # mögliche Einträge: "fe_hex", "fcm", "j2_plasticity", "contact_frictionless",
    # "contact_coulomb", "tie", "gpu", "checkpoints"

    def estimate(self, spec: AssemblyModelSpec) -> dict: ...

    def prepare(
        self, spec: AssemblyModelSpec, materials: dict[str, Material],
        progress: ProgressCallback | None = None,
    ) -> object:
        """Diskretisiert alle Körper, sucht Kontaktflächen, liefert ein Handle."""
        ...

    def solve_path(
        self, handle: object, path: LoadPath,
        provider: GlobalFieldProvider | None = None,
        progress: ProgressCallback | None = None,
        cancel: Callable[[], bool] | None = None,
        on_step: Callable[[StepResult], None] | None = None,   # Live-Anzeige je Laststufe
    ) -> AssemblyResult: ...

# Entry-Point-Gruppe: "statik3d.assembly_solvers"
# volumen3d/pyproject.toml:
# [project.entry-points."statik3d.assembly_solvers"]
# hybrid = "volumen3d.api:HybridAssemblySolver"
```

Die UI prüft `capabilities`, bevor sie Optionen anbietet (z. B. Reibung nur, wenn `"contact_coulomb"` vorhanden ist). Fehlende Fähigkeiten werden ausgegraut, nicht versteckt.

---

## 8. Stub und Referenzmodelle

**Stub (liegt in `statik3d_contracts/testing.py`):** `StubSolidSolver` erfüllt `SolidDetailSolver`, erzeugt eine Würfel-Oberfläche und liefert konstante Spannungen. Damit kann die UI-Einbindung (Modellbaum, Ribbons, Ergebnistabellen) fertig werden, bevor der echte Löser existiert.

**`StubGlobalFieldProvider`:** liefert ein analytisches Feld (z. B. Kragarm unter Endlast nach Balkentheorie). Damit kann das FCM-Modul die Kopplung testen, bevor der 3D-Stablöser fertig ist.

**Gemeinsame Referenzmodelle (`tests/reference_models/`):**

| Modell | Nutzen |
|---|---|
| Kragarm-Rechteckquerschnitt, Endlast | Kopplung Stab → Volumen, Schnittgrößenkontrolle |
| Scheibe mit Loch unter Zug | Spannungsgenauigkeit, Kerbe |
| Dickwandiger Zylinder unter Innendruck | Rotationssymmetrie, Druckrandbedingung |
| Knotenblech mit Kehlnaht | Hot-Spot-Auswertung, Praxisbezug |
| Kontakt-Patch-Test (zwei Blöcke, ebene Kontaktfläche, nicht passende Diskretisierungen) | Kontaktdruck exakt konstant übertragen, FE–FE, FE–FCM, FCM–FCM |
| Hertz: Zylinder auf Ebene / zwei Zylinder | Kontaktdruck, Kontaktbreite |
| Bolzen in Bohrung mit Spiel | Konformer Zylinderkontakt, Druckverteilung, Stabilisierung anfangs freier Körper |
| Elastoplastische Lochscheibe (monoton und zyklisch) | Return Mapping, Verfestigung, Pfadabhängigkeit |
| Hybrid-Gleichheitstest | Derselbe Körper einmal als FE, einmal als FCM → gleiche Ergebnisse innerhalb Toleranz |
| Drehlager-Vergleichsmodell | Gesamtmodell gegen Ansys/RFEM: Kontaktdruck, plastische Dehnung, Reaktionen |

Zusätzlicher Stub: `StubAssemblySolver` erzeugt zwei Zylinderkörper und liefert einen synthetischen Lastpfad mit Kontaktdruck nach Hertz und steigender plastischer Dehnung, damit die UI (Laststufen-Regler, Kontaktergebnisse, Kraft-Weg-Diagramm) vorab gebaut werden kann.

Jedes Referenzmodell enthält Eingabedaten, Erwartungswerte und Toleranzen als JSON/YAML, unabhängig von beiden Implementierungen.

---

## 9. Änderungs- und Versionsregeln

- Semantische Versionierung von `CONTRACT_VERSION`:
  - **Patch:** Doku, Kommentare
  - **Minor:** neue optionale Felder/Methoden (abwärtskompatibel)
  - **Major:** Umbenennen, Entfernen, geänderte Bedeutung
- Beide Pakete prüfen beim Start die Vertragsversion (Major muss übereinstimmen).
- Änderungen am Vertrag nur per separatem Pull Request, **vor** der Nutzung in einem der Pakete.
- CI-Pflichttests für jeden PR:
  1. `isinstance(obj, Protocol)`-Prüfungen für alle Implementierungen
  2. Import-Regeln (Abschnitt 1)
  3. Referenzmodelle gegen Stub und – sobald vorhanden – echte Implementierungen
  4. Typprüfung mit `mypy --strict` für `statik3d_contracts`

**Änderungsprotokoll:**
- **2.0.0** – Paket `fcm_solid` in `volumen3d` umbenannt (enthält inzwischen FCM, FE-Hexaeder, Kontakt und Plastizität). Umbenennung vor der ersten Implementierung, daher ohne Migrationsaufwand.
- **1.1.0** – Neu: `nonlinear.py` (Materialmodelle, Körper, Kontakt, Tie, Lastpfad, Mehrkörperergebnisse), Protokoll `AssemblySolver` mit Entry-Point-Gruppe `statik3d.assembly_solvers`, Stub `StubAssemblySolver`, neue Referenzmodelle. Keine Änderung bestehender Typen.
- **1.0.0** – Erstfassung.

---

## 10. Umstellung im Hauptprogramm (einmalig, vor Parallelstart)

1. `statik3d_contracts` anlegen und als lokale Abhängigkeit einbinden (`pip install -e packages/statik3d_contracts`).
2. Bestehende Netzlogik hinter `Discretization` mit `kind = FE_MESH` legen; Stellen, die direkt auf Knoten-/Elementlisten zugreifen, über das Protokoll führen.
3. Ergebnisschicht um punktweise Abfrage erweitern (`GlobalFieldProvider` implementieren, zunächst für Stäbe).
4. Modellbaum um Knoten „Detailmodelle (Volumen)“ erweitern, gespeist aus `DetailModelSpec`.
5. Löser-Registrierung über Entry Points einbauen und mit `StubSolidSolver` testen.

Danach können beide Stränge unabhängig weiterlaufen.
