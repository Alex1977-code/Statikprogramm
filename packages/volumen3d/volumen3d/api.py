"""Oeffentliche Einstiegspunkte des Volumenmoduls (Vertrag Abschnitt 7 und 7a).

Ausbau in Aufgabe 13 des Plans; hier zunaechst nur die Klassenkoepfe, damit die
Entry Points aufloesen.
"""
from __future__ import annotations

from statik3d_contracts import CONTRACT_VERSION


class FcmSolver:
    name: str = "fcm"
    contract_version: str = CONTRACT_VERSION


class HybridAssemblySolver:
    name: str = "hybrid"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset()
