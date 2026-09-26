"""Mehrkoerpermodelle, Kontakt und Plastizitaet (Vertrag Abschnitt 6a, ab 1.1).

Rein additiv zu ``detail.py``. Grundregel: keine Superposition - Ergebnisse
entstehen nur entlang eines ``LoadPath``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .coupling import CutPlane
from .detail import FcmSettings, GeometrySource, RefinementRegion, WeldLine
from .discretization import DiscretizationKind
from .model import ResultKey

# ---------- Materialmodelle ----------


class HardeningType(str, Enum):
    NONE = "none"                  # ideal-plastisch
    ISOTROPIC = "isotropic"
    KINEMATIC = "kinematic"        # linear kinematisch (Prager)
    COMBINED = "combined"


@dataclass(frozen=True)
class ElastoPlasticJ2:
    """Von-Mises-Plastizitaet, kleine Dehnungen in Stufe A."""
    material_id: str               # verweist auf Material (E, nu, fy)
    hardening: HardeningType = HardeningType.ISOTROPIC
    # Fliesskurve: Stuetzpunkte (plastische Vergleichsdehnung [-], Fliessspannung [N/mm2]),
    # erster Punkt muss (0.0, fy) sein; ein Punkt = ideal-plastisch
    flow_curve: tuple[tuple[float, float], ...] = ()
    strain_limit: float | None = 0.05   # Grenzdehnung fuer Nachweis, z. B. 5 % nach EC3-1-5 Anhang C


@dataclass(frozen=True)
class LinearElasticModel:
    material_id: str


MaterialModel = LinearElasticModel | ElastoPlasticJ2

# ---------- Koerper ----------


@dataclass(frozen=True)
class FeHexSettings:
    """Klassische Vernetzung fuer Koerper mit einfacher Geometrie (Bolzen, Buchse, Ring)."""
    order: int = 2                     # 2 = Hex20/Hex27
    element_size_mm: float = 5.0
    mesher: str = "revolve"            # "revolve" (strukturiert, Rotationskoerper) | "gmsh"
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
    exact_surface: str | None = None             # z. B. "cylinder" - exakte Normalen fuer Kontakt

# ---------- Flaechen, Kontakt, feste Verbindungen ----------


@dataclass(frozen=True)
class SurfaceSelector:
    """Auswahl einer Koerperoberflaeche. Genau eine Variante belegen."""
    body_id: str
    named_surface: str | None = None       # benannte Flaeche aus CAD/CSG, z. B. "bohrung"
    box: tuple[np.ndarray, np.ndarray] | None = None   # (min, max) Auswahlbox
    cylinder: tuple[np.ndarray, np.ndarray, float] | None = None  # (Achspunkt, Achsrichtung, Radius +- Toleranz)


class ContactFormulation(str, Enum):
    PENALTY = "penalty"
    AUGMENTED_LAGRANGE = "augmented_lagrange"   # Standard
    MORTAR = "mortar"                           # Segment-zu-Segment, spaeter dual


class FrictionModel(str, Enum):
    FRICTIONLESS = "frictionless"
    COULOMB = "coulomb"
    STICK = "stick"                             # haftend, aber abhebend moeglich


@dataclass(frozen=True)
class ContactPair:
    id: str
    master: SurfaceSelector                     # i. d. R. steifere / groeber diskretisierte Seite
    slave: SurfaceSelector
    friction: FrictionModel = FrictionModel.FRICTIONLESS
    mu: float = 0.0
    initial_clearance_mm: float | None = None   # None = aus Geometrie; Wert ueberschreibt (Lagerspiel)
    formulation: ContactFormulation = ContactFormulation.AUGMENTED_LAGRANGE
    penalty_factor: float | None = None         # None = automatisch aus Steifigkeit


@dataclass(frozen=True)
class Tie:
    """Feste Verbindung zweier Flaechen (Schweissnaht vereinfacht, Presssitz ohne Schlupf, FE-FCM-Kopplung)."""
    id: str
    a: SurfaceSelector
    b: SurfaceSelector


@dataclass(frozen=True)
class Support:
    """Lagerung direkt am Koerper (wenn nicht ueber Globalmodell-Kopplung)."""
    id: str
    surface: SurfaceSelector
    fixed_dofs: tuple[bool, bool, bool] = (True, True, True)


@dataclass(frozen=True)
class SurfaceLoad:
    id: str
    surface: SurfaceSelector
    load_case_id: str
    pressure: float | None = None               # N/mm2, positiv = auf Flaeche drueckend
    traction: np.ndarray | None = None          # (3,) N/mm2, global
    resultant: tuple[np.ndarray, np.ndarray] | None = None  # (Kraft N, Moment N*mm), ueber Flaeche verteilt

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
    """Geordnete Folge von Zustaenden, z. B. Eigengewicht -> Wasserdruck -> Stellung 1 -> Stellung 2 -> ...
    Plastische Verformungen und Kontaktzustaende werden von Zustand zu Zustand mitgenommen."""
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
    stabilization: str = "auto"                  # "auto" | "springs" | "viscous" | "none" - fuer anfangs freie Koerper im Spiel
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
    points: np.ndarray            # (n,3) Auswertepunkte auf der Slave-Flaeche
    pressure: np.ndarray          # (n,) N/mm2
    gap: np.ndarray               # (n,) mm, negativ = Durchdringung (sollte ~ 0 sein)
    slip: np.ndarray              # (n,3) mm, akkumuliert
    status: np.ndarray            # (n,) int: 0 offen, 1 haftend, 2 gleitend
    resultant_force: np.ndarray   # (3,) N


@dataclass
class BodyResult:
    body_id: str
    surface_points: np.ndarray    # (n,3)
    surface_triangles: np.ndarray  # (m,3)
    displacement: np.ndarray      # (n,3) mm
    stress: np.ndarray            # (n,6) Voigt, N/mm2
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
    reaction_forces: dict[str, np.ndarray] = field(default_factory=dict)  # Support-ID -> (3,)


@dataclass
class AssemblyResult:
    assembly_id: str
    path_id: str
    steps: list[StepResult]                        # nur Ausgabeschritte, nicht jede Iteration
    checkpoints: list[str] = field(default_factory=list)
    max_plastic_strain: dict[str, float] = field(default_factory=dict)   # Koerper-ID -> max
    max_contact_pressure: dict[str, float] = field(default_factory=dict)  # Paar-ID -> max
    coupling_check: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    protocol: dict[str, Any] = field(default_factory=dict)


__all__ = ["HardeningType", "ElastoPlasticJ2", "LinearElasticModel", "MaterialModel", "FeHexSettings",
           "Body", "SurfaceSelector", "ContactFormulation", "FrictionModel", "ContactPair", "Tie",
           "Support", "SurfaceLoad", "LoadState", "LoadPath", "NonlinearSettings", "AssemblyModelSpec",
           "ContactResult", "BodyResult", "StepResult", "AssemblyResult"]
