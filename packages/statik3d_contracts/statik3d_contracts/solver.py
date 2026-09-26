"""Loeser-Protokolle und Registrierung (Vertrag Abschnitt 7 und 7a).

Registrierung ohne direkte Imports ueber Python Entry Points:

* Gruppe ``statik3d.solid_solvers``  - ``SolidDetailSolver`` (Abschnitt 7),
  in ``packages/volumen3d/pyproject.toml``: ``fcm = "volumen3d.api:FcmSolver"``
* Gruppe ``statik3d.assembly_solvers`` - ``AssemblySolver`` (Abschnitt 7a),
  ``hybrid = "volumen3d.api:HybridAssemblySolver"``

Das Hauptprogramm laedt Loeser ueber
``importlib.metadata.entry_points(group=...)`` und kennt so keine internen
Module von ``volumen3d``.
"""
from __future__ import annotations

from typing import Any, Callable, Final, Protocol, runtime_checkable

from .coupling import GlobalFieldProvider
from .detail import DetailModelSpec, DetailResult
from .discretization import Discretization
from .model import Material, ResultKey
from .nonlinear import AssemblyModelSpec, AssemblyResult, LoadPath, StepResult

ProgressCallback = Callable[[str, float], None]   # (Meldung, Anteil 0..1)

#: Entry-Point-Gruppen (Abschnitt 7 und 7a)
ENTRY_POINT_SOLID: Final = "statik3d.solid_solvers"
ENTRY_POINT_ASSEMBLY: Final = "statik3d.assembly_solvers"

#: moegliche Eintraege in ``AssemblySolver.capabilities``
CAPABILITIES: Final = frozenset({"fe_hex", "fcm", "j2_plasticity", "contact_frictionless",
                                 "contact_coulomb", "tie", "gpu", "checkpoints"})


class SolverCancelled(Exception): ...


class SolverError(Exception): ...


@runtime_checkable
class SolidDetailSolver(Protocol):
    name: str
    contract_version: str

    def estimate(self, spec: DetailModelSpec) -> dict[str, Any]:
        """Schnell: erwartete DOF, Speicherbedarf (MB), Backend. Ohne Rechnung."""
        ...

    def prepare(
        self, spec: DetailModelSpec, material: Material,
        progress: ProgressCallback | None = None,
    ) -> Discretization:
        """Geometrie laden, Octree bauen, Schnittzellen integrieren. Wiederverwendbar fuer alle Keys."""
        ...

    def solve(
        self, disc: Discretization, provider: GlobalFieldProvider,
        keys: list[ResultKey],
        progress: ProgressCallback | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> list[DetailResult]:
        """Loest alle Keys mit derselben Diskretisierung (nur rechte Seiten aendern sich)."""
        ...


@runtime_checkable
class AssemblySolver(Protocol):
    name: str
    contract_version: str
    capabilities: frozenset[str]
    # moegliche Eintraege: "fe_hex", "fcm", "j2_plasticity", "contact_frictionless",
    # "contact_coulomb", "tie", "gpu", "checkpoints"

    def estimate(self, spec: AssemblyModelSpec) -> dict[str, Any]: ...

    def prepare(
        self, spec: AssemblyModelSpec, materials: dict[str, Material],
        progress: ProgressCallback | None = None,
    ) -> object:
        """Diskretisiert alle Koerper, sucht Kontaktflaechen, liefert ein Handle."""
        ...

    def solve_path(
        self, handle: object, path: LoadPath,
        provider: GlobalFieldProvider | None = None,
        progress: ProgressCallback | None = None,
        cancel: Callable[[], bool] | None = None,
        on_step: Callable[[StepResult], None] | None = None,   # Live-Anzeige je Laststufe
    ) -> AssemblyResult: ...


__all__ = ["ProgressCallback", "ENTRY_POINT_SOLID", "ENTRY_POINT_ASSEMBLY", "CAPABILITIES",
           "SolverCancelled", "SolverError", "SolidDetailSolver", "AssemblySolver"]
