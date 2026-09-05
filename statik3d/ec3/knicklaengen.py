"""
Knicklängenbeiwerte aus der Knickfigur (Eigenform).

Das lineare Verzweigungsproblem (K + α·K_g) v = 0 liefert den Verzweigungs-
lastfaktor α_cr und die Knickfigur v. Für jeden Stab folgt daraus die
ideale Knicklast N_cr = α_cr · |N_Ed| und die Knicklänge

    L_cr = π · √(E·I / N_cr),   β = L_cr / L.

Die **Eigenform** sagt zweierlei, was die Zahl α_cr allein nicht sagt:

* **um welche Achse** der Stab ausknickt - aus der modalen Biegeenergie des
  Stabes um seine lokale y- und z-Achse (½ vᵀ k v je Element, getrennt nach
  den Biegefreiheitsgraden); die Knicklänge gilt für diese Achse, für die
  andere sagt diese Knickfigur nichts;
* **ob der Stab überhaupt beteiligt ist** - sein Anteil an der modalen
  Formänderungsenergie. Ein Stab, der in der Knickfigur gerade bleibt, hat
  nach α_cr·|N_Ed| eine viel zu große Knicklänge (die Formel setzt voraus,
  dass er es ist, der ausknickt); der Wert ist dann nur eine Obergrenze und
  wird so gekennzeichnet. Für solche Stäbe gehört eine höhere Knickfigur
  ausgewertet, in der sie sich verformen.

Das ist das übliche Verfahren der Stabwerksprogramme (RSBUCK, SOFiSTiK):
Knicklängen aus dem Eigenwert, achsenweise über die Eigenform zugeordnet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..model import Model, Member
from .. import assemble as asm
from ..elements import beam3d as bm

#: Biegefreiheitsgrade eines Stabelements: um y (Verschiebung z, Drehung y)
#: und um z (Verschiebung y, Drehung z) an beiden Enden
DOFS_UM_Y = [2, 4, 8, 10]
DOFS_UM_Z = [1, 5, 7, 11]


@dataclass
class Knicklaenge:
    """Das Ergebnis für einen Stab."""
    stab: str
    L: float                          # Stablänge [m]
    N_Ed: float                       # maßgebende Normalkraft (negativ = Druck) [N]
    alpha_cr: float
    N_cr: float = 0.0                 # α_cr · |N_Ed| [N]
    achse: str = ""                   # "y" oder "z": Biegeachse der Knickfigur
    Lcr_y: Optional[float] = None
    beta_y: Optional[float] = None
    Lcr_z: Optional[float] = None
    beta_z: Optional[float] = None
    beteiligung: float = 0.0          # Anteil an der modalen Formänderungsenergie
    beteiligt: bool = False
    hinweis: str = ""

    def zeile(self) -> list:
        f = lambda v, k=1.0, d=3: "–" if v is None else f"{v * k:.{d}f}"  # noqa: E731
        return [self.stab, f"{self.L:.3f}", f"{self.N_Ed / 1e3:.2f}", f"{self.alpha_cr:.3f}",
                f"{self.N_cr / 1e3:.2f}" if self.N_cr else "–", self.achse or "–",
                f(self.Lcr_y), f(self.beta_y), f(self.Lcr_z), f(self.beta_z),
                f"{self.beteiligung * 100:.1f} %", self.hinweis]


@dataclass
class KnicklaengenErgebnis:
    alpha_cr: float
    modus: int                        # Nummer der Knickfigur (0 = erste)
    grundzustand: str                 # Lastfall oder Kombination des Grundzustands
    staebe: dict = field(default_factory=dict)
    min_beteiligung: float = 0.05
    log: list = field(default_factory=list)

    KOPF = ["Stab", "L [m]", "N_Ed [kN]", "α_cr", "N_cr [kN]", "Achse",
            "L_cr,y [m]", "β_y", "L_cr,z [m]", "β_z", "Beteiligung", "Hinweis"]

    def tabelle(self) -> list:
        return [list(self.KOPF)] + [k.zeile() for k in self.staebe.values()]

    def summary(self) -> str:
        n = sum(1 for k in self.staebe.values() if k.beteiligt)
        return (f"Knicklängen aus Knickfigur {self.modus + 1} (α_cr = {self.alpha_cr:.3f}, "
                f"Grundzustand {self.grundzustand}): {n} von {len(self.staebe)} Stäben beteiligt")


def _modale_biegeenergie(model: Model, v: np.ndarray, i: int) -> tuple[float, float]:
    """(E_um_y, E_um_z): Formänderungsenergie ½ vᵀ k v des Elements i in der
    Eigenform v, getrennt nach Biegung um die lokale y- und z-Achse."""
    e = model.elements[i]
    kl, T3, T, L = asm.beam_local(model, e)
    ul = T @ v[asm.element_dofs(e)]
    ey = 0.5 * float(ul[DOFS_UM_Y] @ kl[np.ix_(DOFS_UM_Y, DOFS_UM_Y)] @ ul[DOFS_UM_Y])
    ez = 0.5 * float(ul[DOFS_UM_Z] @ kl[np.ix_(DOFS_UM_Z, DOFS_UM_Z)] @ ul[DOFS_UM_Z])
    return ey, ez


def _druckkraft(model: Model, res, member: Member) -> float:
    """Die maßgebende (größte) Druckkraft entlang des Stabes, negativ."""
    from ..solver import member_forces
    st = member_forces(model, res, member)
    N = np.asarray(st["N"], float)
    return float(N.min()) if len(N) else 0.0


def knicklaengen_aus_eigenform(model: Model, res, modus: int = 0,
                               min_beteiligung: float = 0.05,
                               staebe=None) -> KnicklaengenErgebnis:
    """Knicklängenbeiwerte aller Stäbe aus der Knickfigur ``modus`` des
    Verzweigungsergebnisses ``res`` (``solver.solve_buckling``).

    ``res`` trägt den Grundzustand (Normalkräfte) und die Knickfiguren mit
    ihren Faktoren. Stäbe unter Zug bekommen keine Knicklänge."""
    figuren = getattr(res, "buckling_modes", None)
    faktoren = getattr(res, "buckling_factors", None)
    if figuren is None or faktoren is None or len(figuren) == 0:
        raise ValueError("Kein Verzweigungsergebnis: zuerst „Knicken“ rechnen")
    if not 0 <= modus < len(figuren):
        raise ValueError(f"Knickfigur {modus + 1} gibt es nicht ({len(figuren)} gerechnet)")
    alpha = float(faktoren[modus])
    v = np.asarray(figuren[modus], float).ravel()
    out = KnicklaengenErgebnis(alpha, modus, getattr(res, "name", "") or "", {},
                               min_beteiligung)
    if alpha <= 0:
        out.log.append(f"α_cr = {alpha:.3f} ≤ 0: die Knickfigur gehört zu einer Entlastung")
    # Energie je Element (alle Stabelemente), daraus die Beteiligung der Staebe
    energie: dict[int, tuple[float, float]] = {}
    for i, e in enumerate(model.elements):
        if e.typ in asm.LINE_TYPES:
            energie[i] = _modale_biegeenergie(model, v, i)
    gesamt = sum(a + b for a, b in energie.values()) or 1.0
    namen = list(staebe) if staebe else list(model.members)
    for name in namen:
        mem = model.members.get(name)
        if mem is None or not mem.elements:
            continue
        L = sum(model.element_length(int(i)) for i in mem.elements)
        N_Ed = _druckkraft(model, res, mem)
        ey = sum(energie.get(int(i), (0.0, 0.0))[0] for i in mem.elements)
        ez = sum(energie.get(int(i), (0.0, 0.0))[1] for i in mem.elements)
        anteil = (ey + ez) / gesamt
        k = Knicklaenge(name, L, N_Ed, alpha, beteiligung=anteil,
                        beteiligt=anteil >= min_beteiligung)
        if N_Ed >= -1e-9 * max(1.0, abs(N_Ed)):
            k.hinweis = "keine Druckkraft - kein Knicken"
            out.staebe[name] = k
            continue
        if alpha <= 0:
            k.hinweis = "α_cr ≤ 0"
            out.staebe[name] = k
            continue
        k.N_cr = alpha * abs(N_Ed)
        e0 = model.elements[int(mem.elements[0])]
        sec = model.sections[e0.sec]
        mat = model.materials[e0.mat]
        # Biegeachse aus der Eigenform: wo die Biegeenergie liegt
        um_y = ey >= ez
        k.achse = "y" if um_y else "z"
        if um_y:
            k.Lcr_y = math.pi * math.sqrt(mat.E * sec.Iy / k.N_cr)
            k.beta_y = k.Lcr_y / L
        else:
            k.Lcr_z = math.pi * math.sqrt(mat.E * sec.Iz / k.N_cr)
            k.beta_z = k.Lcr_z / L
        if not k.beteiligt:
            k.hinweis = (f"nur {anteil * 100:.1f} % der Knickfigur - Wert ist eine Obergrenze; "
                         "höhere Knickfigur auswerten")
        out.staebe[name] = k
    return out


def knicklaengen_uebernehmen(model: Model, erg: KnicklaengenErgebnis,
                             nur_beteiligte: bool = True) -> list[str]:
    """Die gefundenen β in die Stäbe schreiben (für die Stabilitätsnachweise).
    Rückgabe: die geänderten Stäbe."""
    geaendert = []
    for name, k in erg.staebe.items():
        mem = model.members.get(name)
        if mem is None or (nur_beteiligte and not k.beteiligt):
            continue
        if k.beta_y is not None:
            mem.beta_y = float(k.beta_y)
            mem.Lcr_y = None
            geaendert.append(name)
        if k.beta_z is not None:
            mem.beta_z = float(k.beta_z)
            mem.Lcr_z = None
            if name not in geaendert:
                geaendert.append(name)
    return geaendert
