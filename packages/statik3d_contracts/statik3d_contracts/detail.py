"""Detailmodell und Ergebnis (Vertrag Abschnitt 6)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from .coupling import CutPlane
from .model import ResultKey


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
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefinementRegion:
    center: np.ndarray       # (3,)
    radius_mm: float
    target_cell_size_mm: float
    p: int | None = None


@dataclass(frozen=True)
class WeldLine:
    id: str
    points: np.ndarray       # (n,3) Nahtuebergang als Polylinie
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
    stress: float            # N/mm2, massgebende Komponente
    method: str


@dataclass
class DetailResult:
    detail_id: str
    key: ResultKey
    surface_points: np.ndarray      # (n,3)
    surface_triangles: np.ndarray   # (m,3) int
    displacement: np.ndarray        # (n,3) mm
    stress: np.ndarray              # (n,6) Voigt, N/mm2
    von_mises: np.ndarray           # (n,)
    hot_spots: list[HotSpotResult] = field(default_factory=list)
    convergence: list[dict[str, Any]] = field(default_factory=list)  # je Zyklus: dofs, iterations, hotspot_max ...
    coupling_check: dict[str, Any] = field(default_factory=dict)     # Abweichung Schnittgroessen
    warnings: list[str] = field(default_factory=list)
    protocol: dict[str, Any] = field(default_factory=dict)           # alle Einstellungen, fuer Prueffaehigkeit


__all__ = ["GeometrySourceType", "GeometrySource", "RefinementRegion", "WeldLine", "FcmSettings",
           "DetailModelSpec", "HotSpotResult", "DetailResult"]
