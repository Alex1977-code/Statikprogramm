"""Diskretisierungs-Abstraktion (Vertrag Abschnitt 4).

Ersetzt im Hauptprogramm die Annahme "Netz = Knoten + Elemente": ein
FE-Netz (Staebe, Schalen, klassische Volumenelemente) und ein FCM-Octree
sehen fuer die Oberflaeche gleich aus.
"""
from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np


class DiscretizationKind(str, Enum):
    FE_MESH = "fe_mesh"          # Staebe, Schalen, klassische Volumenelemente
    FCM_OCTREE = "fcm_octree"    # Finite-Cell-Methode


@runtime_checkable
class Discretization(Protocol):
    kind: DiscretizationKind
    subsystem_id: str            # Globalmodell, Stellung oder Detailmodell

    def dof_count(self) -> int: ...
    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]: ...
    def summary(self) -> dict[str, float | int | str]: ...
    def preview_geometry(self) -> dict[str, np.ndarray]:
        """Darstellungsdaten fuer die UI, z. B. {'vertices': (n,3), 'triangles': (m,3), 'cell_boxes': (k,6)}."""
        ...


__all__ = ["DiscretizationKind", "Discretization"]
