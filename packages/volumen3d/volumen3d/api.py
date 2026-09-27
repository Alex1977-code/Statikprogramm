"""Oeffentliche Einstiegspunkte des Volumenmoduls (Vertrag Abschnitt 7 und 7a).

``FcmSolver`` (Entry Point ``fcm``): Detailmodell aus CSG-Geometrie
(``GeometrySource.params`` nach docs/Volumenmodul_Entwurf.md 3.7), Schnittebenen als
Halbraeume (Werkstoff gegen die Normale, wie ``CutPlane.normal``), Verschiebungskopplung ueber
den ``GlobalFieldProvider``: Normalkomponente punktweise ueber Nitsche, in der Ebene die drei
Resultierenden als Mittelwertzwaenge (Entwurf 3.6, Projektion ``schnitt``). Ergebnis an der
Oberflaechentriangulierung, Schnittgroessenkontrolle je Ebene, vollstaendiges Protokoll.

``HybridAssemblySolver`` (Entry Point ``hybrid``): bis Teilprojekt 7 ein ehrlicher Platzhalter
ohne Faehigkeiten.
"""
from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
from statik3d_contracts import CONTRACT_VERSION
from statik3d_contracts.coupling import GlobalFieldProvider
from statik3d_contracts.detail import DetailModelSpec, DetailResult, FcmSettings, GeometrySourceType
from statik3d_contracts.discretization import DiscretizationKind
from statik3d_contracts.model import Material, ResultKey
from statik3d_contracts.nonlinear import AssemblyModelSpec, AssemblyResult, LoadPath, StepResult
from statik3d_contracts.solver import ProgressCallback, SolverCancelled, SolverError

from . import __version__
from .fcm.gitter import Gitter
from .fcm.problem import FcmProblem, Werkstoff
from .geometry.csg import Csg, Operation, aus_params
from .geometry.sdf import Halbraum
from .postprocess.auswertung import von_mises

Fortschritt = Callable[[str, float], None]


def _geometrie(spec: DetailModelSpec) -> tuple[Csg, list[str]]:
    """CSG des Details, geschnitten mit den Halbraeumen der Schnittebenen ('schnitt_i')."""
    if spec.geometry.type != GeometrySourceType.CSG:
        raise SolverError(f"Geometriequelle {spec.geometry.type.value!r} kommt mit Teilprojekt 2/5; "
                          f"Teilprojekt 1 rechnet nur CSG")
    try:
        basis = aus_params(spec.geometry.params)
    except (ValueError, KeyError, TypeError) as ex:
        raise SolverError(f"CSG-Geometrie: {ex}") from ex
    namen = [f"schnitt_{i}" for i in range(len(spec.cut_planes))]
    if not spec.cut_planes:
        return basis, namen
    teile = (basis.wurzel,) + tuple(Halbraum(np.asarray(cp.origin, float), np.asarray(cp.normal, float), n)
                                    for cp, n in zip(spec.cut_planes, namen))
    try:
        return Csg(Operation("schnitt", teile)), namen
    except ValueError as ex:
        raise SolverError(str(ex)) from ex


def _einstellungen_pruefen(s: FcmSettings) -> None:
    if not s.base_cell_size_mm > 0:
        raise SolverError("base_cell_size_mm muss positiv sein")
    if not 1 <= int(s.p) <= 4:
        raise SolverError(f"p = {s.p}: Teilprojekt 1 unterstuetzt p = 1 ... 4")
    if s.backend not in ("auto", "cpu"):
        raise SolverError(f"backend {s.backend!r}: GPU kommt mit Teilprojekt 3, hier 'auto' oder 'cpu'")
    if s.coupling != "displacement":
        raise SolverError(f"coupling {s.coupling!r}: Kraftkopplung kommt mit Teilprojekt 5")
    if not 0.0 <= float(s.alpha) < 1.0:
        raise SolverError("alpha muss in [0, 1) liegen")


def _oberflaeche(problem: FcmProblem) -> tuple[np.ndarray, np.ndarray]:
    """Dreiecke der Gesamtoberflaeche fuer Vorschau und Auswertepunkte: Tessellierung der
    Grundformen, nur Dreiecke mit Schwerpunkt auf der Gesamtoberflaeche, nach aussen
    orientiert. An CSG-Schnittkurven nicht wasserdicht (Entwurf 3.9; Marching Cubes in TP 5)."""
    g = problem.geometrie
    V, T, _ = g.dreiecke(0.25 * problem.gitter.h)
    if len(T) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    S = V[T].mean(axis=1)
    T = T[np.abs(g.abstand(S)) <= 0.02 * problem.gitter.h]
    if len(T) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int)
    S = V[T].mean(axis=1)
    n = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
    umdrehen = np.einsum("ij,ij->i", n, g.gradient(S)) < 0
    T[umdrehen] = T[umdrehen][:, [0, 2, 1]]
    benutzt = np.unique(T)
    neu = np.full(len(V), -1)
    neu[benutzt] = np.arange(len(benutzt))
    ecken: np.ndarray = np.array(V[benutzt], dtype=float)
    dreiecke: np.ndarray = np.array(neu[T], dtype=int)
    return ecken, dreiecke


class FcmDiskretisierung:
    """Erfuellt ``Discretization`` (Vertrag Abschnitt 4) und haelt das aufgebaute Problem."""
    kind: DiscretizationKind = DiscretizationKind.FCM_OCTREE

    def __init__(self, spec: DetailModelSpec, problem: FcmProblem, schnittnamen: list[str]) -> None:
        self.subsystem_id = spec.id
        self.spec = spec
        self.problem = problem
        self.schnittnamen = schnittnamen
        self._oberflaeche: tuple[np.ndarray, np.ndarray] | None = None

    def dof_count(self) -> int:
        return int(self.problem.gitter.n_dof)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        lo, hi = self.problem.geometrie.huellquader()
        return np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)

    def summary(self) -> dict[str, float | int | str]:
        g = self.problem.gitter
        ag = self.problem.aggregation
        return {"kind": self.kind.value, "subsystem": self.subsystem_id, "p": int(g.p or 0), "cell_size_mm": g.h,
                "cells": int(len(g.ijk)), "inside_cells": int((g.klasse == 1).sum()), "cut_cells": int((g.klasse == 2).sum()),
                "dofs": self.dof_count(), "dofs_free": int(ag.statistik["moden_frei"] * 3) if ag is not None else self.dof_count(),
                "aggregated_cells": int(ag.statistik["zellen_schlecht"]) if ag is not None else 0,
                "quadrature_points": int(self.problem.quadratur.anzahl_punkte()),
                "surface_points": int(len(self.problem.oberflaeche.punkte)), "length_unit": "mm"}

    def oberflaeche(self) -> tuple[np.ndarray, np.ndarray]:
        if self._oberflaeche is None:
            self._oberflaeche = _oberflaeche(self.problem)
        return self._oberflaeche

    def preview_geometry(self) -> dict[str, np.ndarray]:
        V, T = self.oberflaeche()
        lo, hi = self.problem.gitter.zellbox(np.arange(len(self.problem.gitter.ijk)))
        return {"vertices": V, "triangles": T, "cell_boxes": np.concatenate([lo, hi], axis=1),
                "cell_class": self.problem.gitter.klasse.copy()}


class FcmSolver:
    name: str = "fcm"
    contract_version: str = CONTRACT_VERSION

    def estimate(self, spec: DetailModelSpec) -> dict[str, Any]:
        s = spec.settings
        _einstellungen_pruefen(s)
        g, _ = _geometrie(spec)
        try:
            G = Gitter(g, float(s.base_cell_size_mm), 0.1)
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        G.moden_nummerieren(int(s.p))
        m = (int(s.p) + 1) ** 3
        nnz = len(G.ijk) * (3 * m) ** 2
        return {"dofs": int(G.n_dof), "cells": int(len(G.ijk)), "cut_cells": int((G.klasse == 2).sum()),
                "memory_mb": round(nnz * 16 / 1e6 + G.n_dof * 8 * 40 / 1e6, 1), "backend": "cpu", "solver": self.name,
                "note": "Direktloeser (Teilprojekt 1); Speicher der Faktorisierung kommt hinzu"}

    def prepare(self, spec: DetailModelSpec, material: Material, progress: ProgressCallback | None = None) -> FcmDiskretisierung:
        s = spec.settings
        _einstellungen_pruefen(s)
        melden: Fortschritt = progress or (lambda t, a: None)
        g, namen = _geometrie(spec)
        melden("Gitter, Quadratur und Oberflaeche", 0.05)
        try:
            pr = FcmProblem(g, h=float(s.base_cell_size_mm), p=int(s.p),
                            werkstoff=Werkstoff(float(material.E), float(material.nu), float(material.rho)),
                            alpha=float(s.alpha))
            for n in namen:
                pr.verschiebungsrand(n, n, projektion="schnitt")
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        melden("Steifigkeit assemblieren", 0.3)
        pr.aufbauen(lambda t, a: melden(t, 0.3 + 0.6 * a))
        melden("Diskretisierung bereit", 1.0)
        return FcmDiskretisierung(spec, pr, namen)

    def solve(self, disc: FcmDiskretisierung, provider: GlobalFieldProvider, keys: list[ResultKey],
              progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None) -> list[DetailResult]:
        melden: Fortschritt = progress or (lambda t, a: None)
        abbruch = cancel or (lambda: False)
        if not isinstance(disc, FcmDiskretisierung):
            raise SolverError("solve braucht die Diskretisierung aus FcmSolver.prepare")
        pr = disc.problem
        t0 = time.perf_counter()
        vorgaben: list[dict[str, np.ndarray]] = []
        for k, key in enumerate(keys):
            if abbruch():
                raise SolverCancelled("abgebrochen vor der rechten Seite")
            v: dict[str, np.ndarray] = {}
            for n in disc.schnittnamen:
                P = pr.raender[n].quadratur.punkte
                u, _ = provider.displacement_at(P, key)
                u = np.asarray(u, float).reshape(-1, 3)
                schlecht = ~np.isfinite(u).all(axis=1)
                if schlecht.any():
                    i = int(np.flatnonzero(schlecht)[0])
                    raise SolverError(f"Provider liefert NaN fuer {key} auf Schnittebene {n} an {int(schlecht.sum())} "
                                      f"von {len(P)} Punkten, z. B. {P[i]} (Punkt ohne Zuordnung im Globalmodell?)")
                v[n] = u
            vorgaben.append(v)
            melden(f"Randverschiebungen {key.load_case_id}", 0.2 * (k + 1) / max(len(keys), 1))
        if abbruch():
            raise SolverCancelled("abgebrochen vor dem Loesen")
        try:
            U = pr.loesen(vorgaben)
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        melden("Gleichungssystem geloest", 0.7)
        V, T = disc.oberflaeche()
        # Auswertepunkte minimal in den Werkstoff ruecken, damit die Punktsuche eine aktive Zelle findet
        Pe = V - 1e-7 * pr.gitter.h * pr.geometrie.gradient(V) if len(V) else V
        ergebnisse: list[DetailResult] = []
        for k, key in enumerate(keys):
            if abbruch():
                raise SolverCancelled("abgebrochen bei der Auswertung")
            aus = pr.auswertung(U[:, k])
            if len(Pe):
                s_e, u_e = aus.spannung_und_verschiebung(Pe)
            else:
                s_e, u_e = np.zeros((0, 6)), np.zeros((0, 3))
            ebenen = []
            warn: list[str] = []
            for i, (n, cp) in enumerate(zip(disc.schnittnamen, disc.spec.cut_planes)):
                F, M = aus.schnittgroessen(pr.raender[n].quadratur, cp.origin)
                sf = provider.section_forces(cp, key)
                f_g = np.asarray(sf.force, float).reshape(3)
                m_g = np.asarray(sf.moment, float).reshape(3)
                dF = float(np.linalg.norm(F - f_g)) / max(float(np.linalg.norm(f_g)), 1e-12)
                dM = float(np.linalg.norm(M - m_g)) / max(float(np.linalg.norm(m_g)), 1e-12)
                # Konvention der FCM-Seite: F = int sigma.n dA mit n aus dem Detail heraus, also die Kraft,
                # die der abgeschnittene Teil auf das Detail ausuebt (Vorschlag zur Klarstellung im Vertrag:
                # docs/vertrag-aenderungen/2026-09-27-lasten-und-schnittgroessen.md)
                ebenen.append({"plane": i, "force_fcm": F, "force_global": f_g, "moment_fcm": M, "moment_global": m_g,
                               "deviation_force": dF, "deviation_moment": dM,
                               "convention": "force_fcm = int sigma.n dA, n out of the detail",
                               "multipliers": np.asarray(pr.multiplikatoren[3 * i:3 * i + 3, k], float)})
                if dM > 0.05 or dF > 0.05:
                    warn.append(f"Schnittebene {i}: Abweichung der Schnittgroessen Kraft {dF * 100:.1f} %, Moment {dM * 100:.1f} % "
                                f"> 5 % (Vorgabe 16.7: Schnittebenen weiter auseinander legen, schubweiches Globalmodell oder Kraftkopplung)")
            protokoll: dict[str, Any] = dict(pr.protokoll)
            protokoll.update({"solver": self.name, "contract_version": self.contract_version, "volumen3d": __version__,
                              "key": str(key), "coupling": "displacement (normal pointwise + in-plane resultants)",
                              "geometry": spec_kurz(disc.spec), "t_solve_s": round(time.perf_counter() - t0, 3)})
            ergebnisse.append(DetailResult(detail_id=disc.subsystem_id, key=key, surface_points=V, surface_triangles=T,
                                           displacement=u_e, stress=s_e, von_mises=von_mises(s_e) if len(s_e) else np.zeros(0),
                                           coupling_check={"planes": ebenen}, warnings=warn, protocol=protokoll,
                                           convergence=[{"cycle": 0, "dofs": int(pr.gitter.n_dof), "p": pr.p, "cells": int(len(pr.gitter.ijk))}]))
            melden(f"Ergebnis {key.load_case_id}", 0.7 + 0.3 * (k + 1) / max(len(keys), 1))
        return ergebnisse


def spec_kurz(spec: DetailModelSpec) -> dict[str, Any]:
    return {"id": spec.id, "name": spec.name, "source": spec.geometry.type.value, "cut_planes": len(spec.cut_planes),
            "material_id": spec.material_id, "base_cell_size_mm": spec.settings.base_cell_size_mm, "p": spec.settings.p,
            "alpha": spec.settings.alpha}


class HybridAssemblySolver:
    """Platzhalter bis Teilprojekt 7: registriert, aber ohne Faehigkeiten (die Oberflaeche graut alles aus)."""
    name: str = "hybrid"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset()

    def estimate(self, spec: AssemblyModelSpec) -> dict[str, Any]:
        return {"dofs": 0, "memory_mb": 0.0, "backend": "cpu", "solver": self.name,
                "status": "nicht umgesetzt (Teilprojekt 7 des Volumenmoduls)"}

    def prepare(self, spec: AssemblyModelSpec, materials: dict[str, Material],
                progress: ProgressCallback | None = None) -> object:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls); "
                          "fuer die Oberflaeche steht der Stub des Vertragspakets bereit")

    def solve_path(self, handle: object, path: LoadPath, provider: GlobalFieldProvider | None = None,
                   progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None,
                   on_step: Callable[[StepResult], None] | None = None) -> AssemblyResult:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls)")


__all__ = ["FcmSolver", "FcmDiskretisierung", "HybridAssemblySolver"]
