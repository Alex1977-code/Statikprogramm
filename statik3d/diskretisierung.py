"""Das FE-Netz von Statik3D hinter der Vertragsabstraktion ``Discretization``.

Vertrag Abschnitt 4 und 10.2 (``docs/Schnittstellenvertrag_Statik3D_FCM.md``):
Das Hauptprogramm legt seine Netzlogik hinter ``Discretization`` mit
``kind = FE_MESH``; ein FCM-Octree des Volumenmoduls sieht fuer die
Oberflaeche gleich aus. ``FeNetzDiskretisierung`` ist ein Adapter, der das
bestehende Modell (Knoten in m, Elemente je Typ) im Vertragsformat
ausgibt - in mm, wie der Vertrag es verlangt (Abschnitt 2).

Die Rechenwege des Programms greifen weiter direkt auf ``model.nodes`` und
``model.elements`` zu; die Umstellung "Stellen, die direkt auf Knoten-/
Elementlisten zugreifen, ueber das Protokoll fuehren" (10.2) beginnt hier
an der Oberflaeche zum Volumenmodul, nicht in den Elementroutinen.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from statik3d_contracts.discretization import DiscretizationKind

#: Meter -> Millimeter (Statik3D rechnet in SI, der Vertrag in mm)
MM = 1000.0

#: Seiten der Volumenelemente ueber ihre Eckknoten (Indizes in element.nodes);
#: quadratische Typen nutzen dieselben Ecken (die ersten Knoten)
_ECKEN = {"tet4": 4, "tet10": 4, "tetp2": 4, "tetp3": 4, "tetp4": 4,
          "hex8": 8, "hex20": 8, "pent6": 6, "pent15": 6, "pyr5": 5}
_SEITEN = {
    4: [(0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)],
    8: [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    6: [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)],
    5: [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
}
_SCHALEN = {"shell3": 3, "shell4": 4, "tri3": 3, "quad4": 4, "tri6": 3, "quad8": 4, "quad9": 4}
_STAEBE = {"beam", "truss", "beam7"}


class FeNetzDiskretisierung:
    """Erfuellt ``statik3d_contracts.discretization.Discretization`` fuer ein Modell."""
    kind: DiscretizationKind = DiscretizationKind.FE_MESH

    def __init__(self, model: Any, subsystem_id: str = "global") -> None:
        self.model = model
        self.subsystem_id = str(subsystem_id)

    # -- Protokoll -----------------------------------------------------------
    def dof_count(self) -> int:
        return int(self.model.ndof)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        X = np.asarray(self.model.nodes, float).reshape(-1, 3)
        if not len(X):
            return np.zeros(3), np.zeros(3)
        return X.min(axis=0) * MM, X.max(axis=0) * MM

    def summary(self) -> dict[str, float | int | str]:
        typen: dict[str, int] = {}
        for e in self.model.elements:
            typen[str(e.typ)] = typen.get(str(e.typ), 0) + 1
        aus: dict[str, float | int | str] = {"kind": self.kind.value, "subsystem": self.subsystem_id,
                                              "nodes": int(len(self.model.nodes)),
                                              "elements": int(len(self.model.elements)),
                                              "dofs": self.dof_count(), "length_unit": "mm"}
        for t, n in sorted(typen.items()):
            aus[t] = n
        return aus

    def preview_geometry(self) -> dict[str, np.ndarray]:
        """Knoten in mm, die freien Seiten der Volumen und die Schalen als
        Dreiecke, die Staebe als Strecken."""
        X = np.asarray(self.model.nodes, float).reshape(-1, 3) * MM
        dreiecke: list[tuple[int, int, int]] = []
        strecken: list[tuple[int, int]] = []
        seiten_zaehler: dict[tuple[int, ...], tuple[int, ...]] = {}
        seiten_anzahl: dict[tuple[int, ...], int] = {}
        for e in self.model.elements:
            typ = str(e.typ)
            kn = [int(k) for k in e.nodes]
            if typ in _ECKEN:
                for s in _SEITEN[_ECKEN[typ]]:
                    seite = tuple(kn[i] for i in s)
                    key = tuple(sorted(seite))
                    seiten_anzahl[key] = seiten_anzahl.get(key, 0) + 1
                    seiten_zaehler.setdefault(key, seite)
            elif typ in _SCHALEN:
                n = _SCHALEN[typ]
                if n == 3:
                    dreiecke.append((kn[0], kn[1], kn[2]))
                else:
                    dreiecke.append((kn[0], kn[1], kn[2]))
                    dreiecke.append((kn[0], kn[2], kn[3]))
            elif typ in _STAEBE:
                strecken.append((kn[0], kn[-1] if len(kn) > 1 else kn[0]))
        # freie Seiten der Volumen: nur einmal vorhanden = Oberflaeche
        for key, seite in seiten_zaehler.items():
            if seiten_anzahl[key] != 1:
                continue
            if len(seite) == 3:
                dreiecke.append((seite[0], seite[1], seite[2]))
            else:
                dreiecke.append((seite[0], seite[1], seite[2]))
                dreiecke.append((seite[0], seite[2], seite[3]))
        return {"vertices": X,
                "triangles": np.asarray(dreiecke, int).reshape(-1, 3),
                "lines": np.asarray(strecken, int).reshape(-1, 2)}


def aus_modell(model: Any, subsystem_id: str = "global") -> FeNetzDiskretisierung:
    """Die Diskretisierung des Modells im Vertragsformat."""
    return FeNetzDiskretisierung(model, subsystem_id)


__all__ = ["FeNetzDiskretisierung", "aus_modell", "MM"]
