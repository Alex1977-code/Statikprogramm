"""Kopplung Globalmodell -> Detail (Vertrag Abschnitt 5).

Das Hauptprogramm implementiert ``GlobalFieldProvider``, das Volumenmodul
nutzt ihn. Zusage des Hauptprogramms: ``displacement_at`` ist vektorisiert
(keine Python-Schleife je Punkt) und fuer 10^5 Punkte in unter 1 s aufrufbar.
"""
from __future__ import annotations

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
    moment: np.ndarray    # (3,) N*mm


@runtime_checkable
class GlobalFieldProvider(Protocol):
    def available_keys(self) -> list[ResultKey]: ...

    def displacement_at(
        self, points: np.ndarray, key: ResultKey
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Verschiebung u (n,3) in mm und Rotation (n,3) in rad an beliebigen Punkten.
        Fuer Punkte im Querschnittsbereich eines Stabs liefert der Provider die
        Querschnittskinematik (Starrkoerper + Rotation, optional Verwoelbung),
        fuer Schalen die lineare Verteilung ueber die Dicke.
        Punkte ohne Zuordnung: NaN, der Aufrufer muss das pruefen.
        """
        ...

    def section_forces(self, plane: CutPlane, key: ResultKey) -> SectionForces:
        """Schnittgroessen des Globalmodells am Schnitt, fuer die Plausibilitaetskontrolle."""
        ...


__all__ = ["CutPlane", "SectionForces", "GlobalFieldProvider"]
