"""Modellbezogene Typen (Vertrag Abschnitt 3)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Material:
    id: str
    name: str
    E: float                 # N/mm2
    nu: float
    rho: float = 0.0         # kg/mm3
    fy: float | None = None  # N/mm2, fuer Auslastung


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


__all__ = ["Material", "ResultKey", "ModelInfo"]
