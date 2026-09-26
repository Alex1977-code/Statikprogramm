"""Stubs des Vertrags (Abschnitt 8) - Attrappen ohne Rechenlogik.

* ``StubSolidSolver`` erfuellt ``SolidDetailSolver``: eine Wuerfel-Oberflaeche
  als Diskretisierung, konstante Spannungen als Ergebnis. Damit kann die
  Oberflaeche des Hauptprogramms (Modellbaum, Ribbons, Ergebnistabellen)
  fertig werden, bevor der echte Loeser existiert.
* ``StubGlobalFieldProvider`` liefert ein analytisches Feld: Kragarm unter
  Endlast nach der Balkentheorie. Damit kann das Volumenmodul die Kopplung
  testen, bevor der 3D-Stabloeser fertig ist.
* ``StubAssemblySolver`` erzeugt zwei Zylinderkoerper und einen synthetischen
  Lastpfad mit Kontaktdruck nach Hertz und steigender plastischer Dehnung
  fuer Laststufen-Regler, Kontaktergebnisse und Kraft-Weg-Diagramm der UI.

Alle Zahlen sind Attrappen; die Formeln (Balken, Hertz) stimmen, damit die
Kopplungs- und Anzeigeprobe etwas Sinnvolles zeigt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from . import CONTRACT_VERSION
from .coupling import CutPlane, GlobalFieldProvider, SectionForces
from .detail import DetailModelSpec, DetailResult
from .discretization import DiscretizationKind
from .model import Material, ResultKey
from .nonlinear import (AssemblyModelSpec, AssemblyResult, BodyResult, ContactResult, LoadPath,
                        StepResult)
from .solver import ProgressCallback, SolverCancelled, SolverError


def von_mises(stress: np.ndarray) -> np.ndarray:
    """Vergleichsspannung aus (n,6) Voigt [xx, yy, zz, xy, yz, xz]."""
    s = np.asarray(stress, float).reshape(-1, 6)
    sx, sy, sz, txy, tyz, txz = s.T
    sv: np.ndarray = np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                             + 3.0 * (txy ** 2 + tyz ** 2 + txz ** 2))
    return sv


# ---------------------------------------------------------------------------
# Wuerfel-Diskretisierung und StubSolidSolver
# ---------------------------------------------------------------------------
def wuerfel_oberflaeche(mitte: np.ndarray, kante_mm: float) -> tuple[np.ndarray, np.ndarray]:
    """Acht Ecken und zwoelf Dreiecke eines achsparallelen Wuerfels, nach aussen orientiert."""
    h = 0.5 * float(kante_mm)
    c = np.asarray(mitte, float).reshape(3)
    P = c + h * np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                          [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], float)
    T = np.array([[0, 2, 1], [0, 3, 2],      # unten (z-)
                  [4, 5, 6], [4, 6, 7],      # oben (z+)
                  [0, 1, 5], [0, 5, 4],      # y-
                  [2, 3, 7], [2, 7, 6],      # y+
                  [1, 2, 6], [1, 6, 5],      # x+
                  [3, 0, 4], [3, 4, 7]],     # x-
                 int)
    return P, T


@dataclass
class StubDiscretization:
    """Erfuellt ``Discretization``: ein Wuerfel als ein Octree mit acht Zellen."""
    subsystem_id: str
    kante_mm: float
    p: int
    kind: DiscretizationKind = DiscretizationKind.FCM_OCTREE

    def dof_count(self) -> int:
        # acht Zellen, hierarchischer Ansatz Grad p, drei Verschiebungen je Funktion
        return int(8 * 3 * (self.p + 1) ** 3)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        h = 0.5 * self.kante_mm
        return np.array([-h, -h, -h]), np.array([h, h, h])

    def summary(self) -> dict[str, float | int | str]:
        return {"kind": self.kind.value, "cells": 8, "cut_cells": 0, "p": self.p,
                "dofs": self.dof_count(), "edge_mm": self.kante_mm}

    def preview_geometry(self) -> dict[str, np.ndarray]:
        P, T = wuerfel_oberflaeche(np.zeros(3), self.kante_mm)
        h = 0.5 * self.kante_mm
        boxes = []
        for sx in (-1, 0):
            for sy in (-1, 0):
                for sz in (-1, 0):
                    lo = np.array([sx, sy, sz], float) * h
                    boxes.append(np.concatenate([lo, lo + h]))
        return {"vertices": P, "triangles": T, "cell_boxes": np.asarray(boxes, float)}


class StubSolidSolver:
    """Erfuellt ``SolidDetailSolver`` (Vertrag Abschnitt 7) ohne zu rechnen."""
    name: str = "stub"
    contract_version: str = CONTRACT_VERSION
    #: konstante Spannung des Ergebnisses, Voigt, N/mm2
    SPANNUNG = np.array([100.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    KANTE_MM = 100.0

    def estimate(self, spec: DetailModelSpec) -> dict[str, Any]:
        p = int(spec.settings.p)
        zellen = max(1, int(round((self.KANTE_MM / max(spec.settings.base_cell_size_mm, 1e-9)) ** 3)))
        dofs = 3 * (p + 1) ** 3 * zellen
        return {"dofs": dofs, "cells": zellen, "memory_mb": round(dofs * 8 * 30 / 1e6, 1),
                "backend": "cpu" if spec.settings.backend == "auto" else spec.settings.backend,
                "solver": self.name}

    def prepare(self, spec: DetailModelSpec, material: Material,
                progress: ProgressCallback | None = None) -> StubDiscretization:
        if spec.settings.base_cell_size_mm <= 0:
            raise SolverError("base_cell_size_mm muss positiv sein")
        if progress is not None:
            progress("Stub: Wuerfel angelegt", 1.0)
        return StubDiscretization(subsystem_id=spec.id, kante_mm=self.KANTE_MM, p=int(spec.settings.p))

    def solve(self, disc: Any, provider: GlobalFieldProvider, keys: list[ResultKey],
              progress: ProgressCallback | None = None,
              cancel: Callable[[], bool] | None = None) -> list[DetailResult]:
        geo = disc.preview_geometry()
        P = np.asarray(geo["vertices"], float)
        T = np.asarray(geo["triangles"], int)
        aus: list[DetailResult] = []
        for i, key in enumerate(keys):
            if cancel is not None and cancel():
                raise SolverCancelled("abgebrochen")
            u, _rot = provider.displacement_at(P, key)
            u = np.where(np.isfinite(u), u, 0.0)
            stress = np.tile(self.SPANNUNG, (len(P), 1))
            aus.append(DetailResult(
                detail_id=str(disc.subsystem_id), key=key, surface_points=P, surface_triangles=T,
                displacement=np.asarray(u, float), stress=stress, von_mises=von_mises(stress),
                convergence=[{"cycle": 0, "dofs": disc.dof_count(), "iterations": 1, "hotspot_max": 100.0}],
                coupling_check={"force_deviation": 0.0, "moment_deviation": 0.0},
                warnings=["Stub: konstante Spannung 100 N/mm2, keine Rechnung"],
                protocol={"solver": self.name, "contract_version": self.contract_version,
                          "p": disc.p, "edge_mm": disc.kante_mm}))
            if progress is not None:
                progress(f"Stub: {key.load_case_id}", (i + 1) / max(1, len(keys)))
        return aus


# ---------------------------------------------------------------------------
# Analytisches Feld: Kragarm unter Endlast
# ---------------------------------------------------------------------------
class StubGlobalFieldProvider:
    """Erfuellt ``GlobalFieldProvider``: Kragarm laengs x, Laenge L, Rechteck
    b x h, E, Endlast F in -z am freien Ende (x = L), eingespannt bei x = 0.

    Balkentheorie (Bernoulli): w(x) = -F x^2 (3L - x) / (6 E I), Neigung
    w'(x) = -F x (2L - x) / (2 E I), I = b h^3 / 12. Punkte im Querschnitt
    bekommen die Querschnittskinematik u_x = -z w'(x), u_z = w(x); die
    Rotation um y ist -w'(x). Punkte ausserhalb 0 <= x <= L: NaN.
    Vektorisiert, 10^5 Punkte deutlich unter 1 s.
    """
    def __init__(self, L_mm: float = 1000.0, b_mm: float = 100.0, h_mm: float = 200.0,
                 E: float = 210_000.0, F_N: float = 10_000.0) -> None:
        self.L, self.b, self.h, self.E, self.F = float(L_mm), float(b_mm), float(h_mm), float(E), float(F_N)
        self.I = self.b * self.h ** 3 / 12.0
        self.key = ResultKey("LF1")

    def available_keys(self) -> list[ResultKey]:
        return [self.key]

    def displacement_at(self, points: np.ndarray, key: ResultKey) -> tuple[np.ndarray, np.ndarray]:
        P = np.asarray(points, float).reshape(-1, 3)
        x, z = P[:, 0], P[:, 2]
        innen = (x >= -1e-9) & (x <= self.L + 1e-9)
        EI = self.E * self.I
        w = -self.F * x ** 2 * (3.0 * self.L - x) / (6.0 * EI)
        dw = -self.F * x * (2.0 * self.L - x) / (2.0 * EI)
        u = np.column_stack([-z * dw, np.zeros_like(x), w])
        rot = np.column_stack([np.zeros_like(x), -dw, np.zeros_like(x)])
        u[~innen] = np.nan
        rot[~innen] = np.nan
        return u, rot

    def section_forces(self, plane: CutPlane, key: ResultKey) -> SectionForces:
        x = float(np.asarray(plane.origin, float)[0])
        # Schnittgroessen am Schnitt x: Querkraft F, Moment F (L - x) um y
        return SectionForces(force=np.array([0.0, 0.0, -self.F]),
                             moment=np.array([0.0, self.F * (self.L - x), 0.0]))


# ---------------------------------------------------------------------------
# Baugruppen-Stub: zwei Zylinder, Hertz, wachsende plastische Dehnung
# ---------------------------------------------------------------------------
def zylinder_oberflaeche(achse_z0: float, laenge: float, radius: float, mitte_xy: tuple[float, float],
                         n_phi: int = 24, n_z: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Mantel eines Zylinders laengs z als Punkte (n,3) und Dreiecke (m,3)."""
    phi = np.linspace(0.0, 2.0 * np.pi, n_phi, endpoint=False)
    zz = np.linspace(achse_z0, achse_z0 + laenge, n_z)
    P = np.array([[mitte_xy[0] + radius * np.cos(p), mitte_xy[1] + radius * np.sin(p), z]
                  for z in zz for p in phi], float)
    T = []
    for k in range(n_z - 1):
        for i in range(n_phi):
            a, b = k * n_phi + i, k * n_phi + (i + 1) % n_phi
            c, d = a + n_phi, b + n_phi
            T.append([a, b, c])
            T.append([b, d, c])
    return P, np.asarray(T, int)


def hertz_zylinder_ebene(F_je_laenge: float, R_mm: float, E: float, nu: float) -> tuple[float, float]:
    """Hertz, Zylinder auf Ebene, gleiche Werkstoffe: (p0 [N/mm2], halbe Breite b [mm])."""
    E_stern = E / (2.0 * (1.0 - nu ** 2))
    b = np.sqrt(4.0 * F_je_laenge * R_mm / (np.pi * E_stern))
    p0 = np.sqrt(F_je_laenge * E_stern / (np.pi * R_mm))
    return float(p0), float(b)


class StubAssemblySolver:
    """Erfuellt ``AssemblySolver`` (Vertrag Abschnitt 7a) ohne zu rechnen."""
    name: str = "stub"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset({"fe_hex", "contact_frictionless", "j2_plasticity", "checkpoints"})
    R_MM = 25.0
    LAENGE_MM = 100.0
    F_JE_LAENGE = 1000.0       # N/mm am Ende des Lastpfads
    E, NU = 210_000.0, 0.3
    SCHRITTE_JE_ZUSTAND = 5

    def estimate(self, spec: AssemblyModelSpec) -> dict[str, Any]:
        n = max(1, len(spec.bodies))
        return {"dofs": 3 * 2000 * n, "bodies": n, "contacts": len(spec.contacts),
                "memory_mb": round(3 * 2000 * n * 8 * 30 / 1e6, 1), "backend": "cpu", "solver": self.name}

    def prepare(self, spec: AssemblyModelSpec, materials: dict[str, Material],
                progress: ProgressCallback | None = None) -> object:
        for b in spec.bodies:
            if b.discretization == DiscretizationKind.FE_MESH and b.fe_settings is None:
                raise SolverError(f"Koerper {b.id}: fe_settings fehlt bei FE_MESH")
            if b.discretization == DiscretizationKind.FCM_OCTREE and b.fcm_settings is None:
                raise SolverError(f"Koerper {b.id}: fcm_settings fehlt bei FCM_OCTREE")
        koerper = {}
        ids = [b.id for b in spec.bodies] or ["bolzen", "buchse"]
        for i, bid in enumerate(ids[:2]):
            koerper[bid] = zylinder_oberflaeche(0.0, self.LAENGE_MM, self.R_MM * (1 + i), (0.0, 0.0))
        if progress is not None:
            progress("Stub: zwei Zylinder", 1.0)
        return {"spec": spec, "koerper": koerper, "paare": [c.id for c in spec.contacts] or ["bolzen/buchse"]}

    def solve_path(self, handle: object, path: LoadPath, provider: GlobalFieldProvider | None = None,
                   progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None,
                   on_step: Callable[[StepResult], None] | None = None) -> AssemblyResult:
        h: dict[str, Any] = handle if isinstance(handle, dict) else {}
        koerper: dict[str, tuple[np.ndarray, np.ndarray]] = h.get("koerper") or {
            "bolzen": zylinder_oberflaeche(0.0, self.LAENGE_MM, self.R_MM, (0.0, 0.0))}
        paare: list[str] = h.get("paare") or ["bolzen/buchse"]
        spec = h.get("spec")
        steps: list[StepResult] = []
        n_zust = max(1, len(path.states))
        gesamt = n_zust * self.SCHRITTE_JE_ZUSTAND
        zaehler = 0
        max_eps: dict[str, float] = {}
        max_p: dict[str, float] = {}
        for si, zustand in enumerate(path.states or ()):
            for k in range(1, self.SCHRITTE_JE_ZUSTAND + 1):
                if cancel is not None and cancel():
                    raise SolverCancelled("abgebrochen")
                zaehler += 1
                faktor = k / self.SCHRITTE_JE_ZUSTAND
                lam = (si + faktor) / n_zust * float(zustand.factor)     # 0..factor ueber den Pfad
                F_len = self.F_JE_LAENGE * lam
                p0, b = hertz_zylinder_ebene(max(F_len, 1e-12), self.R_MM, self.E, self.NU)
                bodies = []
                for bid, (P, T) in koerper.items():
                    u = np.zeros_like(P)
                    u[:, 2] = -0.01 * lam                     # mm, Starrkoerper nach unten
                    stress = np.zeros((len(P), 6))
                    stress[:, 2] = -p0 * lam                  # Druck laengs z als Attrappe
                    eps_p = np.full(len(P), 0.02 * lam ** 2)  # plastische Dehnung waechst mit der Last
                    max_eps[bid] = max(max_eps.get(bid, 0.0), float(eps_p.max()))
                    bodies.append(BodyResult(body_id=bid, surface_points=P, surface_triangles=T,
                                             displacement=u, stress=stress, von_mises=von_mises(stress),
                                             plastic_strain_eq=eps_p))
                contacts = []
                for pid in paare:
                    xq = np.linspace(-b, b, 21) if b > 0 else np.zeros(21)
                    pts = np.column_stack([xq, np.zeros_like(xq), np.full_like(xq, 0.5 * self.LAENGE_MM)])
                    druck = p0 * np.sqrt(np.clip(1.0 - (xq / b) ** 2, 0.0, 1.0)) if b > 0 else np.zeros(21)
                    max_p[pid] = max(max_p.get(pid, 0.0), float(druck.max()))
                    contacts.append(ContactResult(pair_id=pid, points=pts, pressure=druck, gap=np.zeros(21),
                                                  slip=np.zeros((21, 3)), status=np.ones(21, int),
                                                  resultant_force=np.array([0.0, 0.0, -F_len * self.LAENGE_MM])))
                step = StepResult(path_id=path.id, state_index=si, load_factor=faktor, converged=True,
                                  newton_iterations=3, bodies=bodies, contacts=contacts,
                                  reaction_forces={"lager": np.array([0.0, 0.0, F_len * self.LAENGE_MM])})
                steps.append(step)
                if on_step is not None:
                    on_step(step)
                if progress is not None:
                    progress(f"Stub: Zustand {si + 1}/{n_zust}, Schritt {k}", zaehler / gesamt)
        return AssemblyResult(
            assembly_id=str(getattr(spec, "id", "stub")), path_id=path.id, steps=steps,
            checkpoints=[f"{path.id}:{i}" for i in range(n_zust)] if path.save_checkpoints else [],
            max_plastic_strain=max_eps, max_contact_pressure=max_p,
            coupling_check={"force_deviation": 0.0},
            warnings=["Stub: synthetischer Lastpfad, Hertz-Druck und Attrappen-Dehnung"],
            protocol={"solver": self.name, "contract_version": self.contract_version,
                      "hertz": {"R_mm": self.R_MM, "F_je_laenge_N_mm": self.F_JE_LAENGE, "E": self.E, "nu": self.NU}})


__all__ = ["von_mises", "wuerfel_oberflaeche", "StubDiscretization", "StubSolidSolver",
           "StubGlobalFieldProvider", "zylinder_oberflaeche", "hertz_zylinder_ebene", "StubAssemblySolver"]
