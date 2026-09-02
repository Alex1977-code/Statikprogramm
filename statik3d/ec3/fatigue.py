"""
Ermuedungsnachweis nach DIN EN 1993-1-9 (Nennspannungskonzept).

Woehlerlinien (Bild 7.1):
    Normalspannung: m = 3 bis N_D = 5e6 (Delta_sigma_D = 0.737 Delta_sigma_C),
                    m = 5 bis N_L = 1e8 (Delta_sigma_L = 0.549 Delta_sigma_D),
                    darunter keine Schaedigung.
    Schubspannung:  m = 5 bis N_L = 1e8 (Delta_tau_L = 0.457 Delta_tau_C).
Schadensakkumulation nach Palmgren-Miner: D = sum(n_i / N_Ri) <= 1.
Teilsicherheitsbeiwerte gamma_Mf nach Tabelle 3.1, gamma_Ff = 1.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..model import Model, Member

# Kerbfallklassen [MPa] (Tabellen 8.1 - 8.10, Auswahl)
DETAIL_CATEGORIES = [160, 140, 125, 112, 100, 90, 80, 71, 63, 56, 50, 45, 40, 36]
DETAIL_CATEGORIES_SHEAR = [100, 80]

GAMMA_MF = {("damage_tolerant", "low"): 1.00, ("damage_tolerant", "high"): 1.15,
            ("safe_life", "low"): 1.15, ("safe_life", "high"): 1.35}

DETAIL_EXAMPLES = {
    160: "Grundwerkstoff gewalzt, Oberflaeche geschliffen (Tab. 8.1, 1)",
    140: "Grundwerkstoff gewalzt, Walzhaut, scharfe Kanten entfernt (Tab. 8.1, 2)",
    125: "Laengsnaht durchgeschweisst, geprueft (Tab. 8.2); Brennschnitt maschinell (8.1, 3)",
    112: "Laengsnaht Kehl-/Stumpfnaht automatisch (Tab. 8.2, 3); Stumpfstoss bearbeitet (8.3, 1)",
    100: "Stumpfstoss quer, geprueft, Schweissnahtueberhoehung <= 10 % (Tab. 8.3, 3)",
    90: "Stumpfstoss quer ohne Bearbeitung (Tab. 8.3, 5); Laengssteife <= 50 mm",
    80: "Quersteife/Rippe angeschweisst, l <= 50 mm (Tab. 8.4, 7); Laengssteife 50-80 mm",
    71: "Quersteife > 50 mm, Laengssteife 80-100 mm (Tab. 8.4); Schraubenverbindung gleitfest",
    63: "Laengssteife > 100 mm (Tab. 8.4, 6); Deckblech Ende (8.5)",
    56: "Deckblech-Ende t <= 20 mm (Tab. 8.5, 1); Konsolanschluss",
    50: "Kehlnahtanschluss quer (Tab. 8.5); Schraube mit Zug (Tab. 8.1, 14: 50 fuer Schrauben)",
    45: "Deckblech Ende t > 20 mm; Halbrundnaht am Flanschrand (Tab. 8.5)",
    40: "Kehlnahtanschluss ohne Bearbeitung, dick (Tab. 8.5, 3)",
    36: "Kehlnaht auf Zug/Schub (Tab. 8.5, 8); Schraubengewinde unter Zug",
}


def sn_life(delta_sigma: float, category: float, gamma_Mf: float = 1.0,
            shear: bool = False) -> float:
    """Ertragbare Lastspielzahl N_R fuer eine Schwingbreite [Pa] und Kerbfall [Pa]."""
    dc = category / gamma_Mf
    if delta_sigma <= 0:
        return np.inf
    if shear:
        dL = (2.0 / 100.0) ** 0.2 * dc
        if delta_sigma < dL:
            return np.inf
        return 2e6 * (dc / delta_sigma) ** 5
    dD = (2.0 / 5.0) ** (1.0 / 3.0) * dc
    dL = (5.0 / 100.0) ** 0.2 * dD
    if delta_sigma >= dD:
        return 2e6 * (dc / delta_sigma) ** 3
    if delta_sigma >= dL:
        return 5e6 * (dD / delta_sigma) ** 5
    return np.inf


def damage(ranges: list[tuple[float, float]], category: float, gamma_Mf: float = 1.0,
           shear: bool = False) -> float:
    """Palmgren-Miner: ranges = [(Delta_sigma_i [Pa], n_i), ...]."""
    D = 0.0
    for ds, n in ranges:
        N = sn_life(ds, category, gamma_Mf, shear)
        if np.isfinite(N) and N > 0:
            D += n / N
    return D


def equivalent_range(ranges: list[tuple[float, float]], m: float = 3.0, N_ref: float = 2e6) -> float:
    """Schadensaequivalente Einstufen-Schwingbreite bei N_ref (Steigung m)."""
    s = sum(n * ds ** m for ds, n in ranges)
    return float((s / N_ref) ** (1.0 / m)) if s > 0 else 0.0


# --------------------------------------------------------------------------
@dataclass
class FatigueMember:
    member: str
    category: float
    category_shear: float
    gamma_Mf: float
    ranges: list = field(default_factory=list)       # (Delta_sigma, n, name, x)
    ranges_shear: list = field(default_factory=list)
    D: float = 0.0
    D_shear: float = 0.0
    dsig_max: float = 0.0
    dtau_max: float = 0.0
    dsig_E2: float = 0.0
    util: float = 0.0
    util_E2: float = 0.0
    governing: str = ""
    x_governing: float = 0.0
    warnings: list = field(default_factory=list)


@dataclass
class FatigueResults:
    members: dict = field(default_factory=dict)
    gamma_Ff: float = 1.0

    def summary(self) -> str:
        if not self.members:
            return "Ermuedung: keine Staebe mit Kerbfall"
        worst = max(self.members.values(), key=lambda m: m.util)
        return (f"Ermuedung: {len(self.members)} Staebe, max. Schaedigung D = {worst.util:.3f} "
                f"({worst.member}, Kerbfall {worst.category/1e6:.0f})")

    def table(self) -> list[list]:
        rows = [["Stab", "Kerbfall", "gamma_Mf", "max Delta-sigma [MPa]", "Delta-sigma_E,2 [MPa]",
                 "D (Miner)", "D Schub", "Ausnutzung", "massgebend"]]
        for m in self.members.values():
            rows.append([m.member, f"{m.category/1e6:.0f}", f"{m.gamma_Mf:.2f}",
                         f"{m.dsig_max/1e6:.1f}", f"{m.dsig_E2/1e6:.1f}", f"{m.D:.3f}",
                         f"{m.D_shear:.3f}", f"{m.util:.3f}", m.governing])
        return rows

    def util_by_element(self, model: Model) -> dict:
        out = {}
        for m in self.members.values():
            for e in model.members[m.member].elements:
                out[e] = max(out.get(e, 0.0), m.util)
        return out


def _stress_points(model: Model, res, member: Member, n: int):
    """Normalspannungen an den 4 Eckpunkten und Schubspannung entlang des Stabes."""
    mf = res.member_forces(member, n)
    e0 = model.elements[member.elements[0]]
    sec = model.sections[e0.sec]
    Wy = sec.Wel_y if sec.Wel_y > 0 else 1e-30
    Wz = sec.Wel_z if sec.Wel_z > 0 else 1e-30
    N, My, Mz = mf["N"], mf["My"], mf["Mz"]
    sig = np.stack([N / sec.A + sy * My / Wy + sz * Mz / Wz
                    for sy in (1, -1) for sz in (1, -1)])          # (4, nstat)
    Avz = sec.Asz if sec.Asz > 0 else sec.A
    Avy = sec.Asy if sec.Asy > 0 else sec.A
    tau = np.maximum(np.abs(mf["Vz"]) / Avz, np.abs(mf["Vy"]) / Avy)
    return mf["x"], sig, tau


def check_fatigue(model: Model, analysis, progress=None, n: int = None) -> FatigueResults:
    """Ermuedungsnachweis aller Staebe mit Kerbfall fuer alle Ermuedungslasten."""
    ds = model.design
    n = n or ds.stations
    out = FatigueResults(gamma_Ff=ds.gamma_Ff)
    all_res = analysis.all_results() if hasattr(analysis, "all_results") else analysis
    for mname, member in model.members.items():
        if not member.design or member.detail_category is None:
            continue
        gMf = GAMMA_MF.get((member.assessment, member.consequence), 1.15)
        cat_s = member.detail_category_shear or 100e6
        fm = FatigueMember(mname, member.detail_category, cat_s, gMf)
        for fl in model.fatigue_loads.values():
            if fl.case_max not in all_res:
                fm.warnings.append(f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_max}' fehlt")
                continue
            x, s_max, t_max = _stress_points(model, all_res[fl.case_max], member, n)
            if fl.case_min and fl.case_min in all_res:
                _, s_min, t_min = _stress_points(model, all_res[fl.case_min], member, n)
            else:
                s_min = np.zeros_like(s_max)
                t_min = np.zeros_like(t_max)
            dsig = np.abs(s_max - s_min).max(axis=0) * fl.factor * ds.gamma_Ff   # je Station
            dtau = np.abs(t_max - t_min) * fl.factor * ds.gamma_Ff
            j = int(np.argmax(dsig))
            fm.ranges.append((float(dsig[j]), fl.cycles, fl.name, float(x[j])))
            k = int(np.argmax(dtau))
            fm.ranges_shear.append((float(dtau[k]), fl.cycles, fl.name, float(x[k])))
        if not fm.ranges:
            continue
        fm.D = damage([(r[0], r[1]) for r in fm.ranges], fm.category, gMf)
        fm.D_shear = damage([(r[0], r[1]) for r in fm.ranges_shear], cat_s, gMf, shear=True)
        fm.dsig_max = max(r[0] for r in fm.ranges)
        fm.dtau_max = max(r[0] for r in fm.ranges_shear)
        fm.dsig_E2 = equivalent_range([(r[0], r[1]) for r in fm.ranges])
        fm.util_E2 = fm.dsig_E2 / (fm.category / gMf)
        # Kombination Normal- und Schubspannung (Gl. 8.3): D_sig + D_tau <= 1 sinngemaess
        fm.util = fm.D + fm.D_shear
        gov = max(fm.ranges, key=lambda r: r[0])
        fm.governing = f"{gov[2]} (Delta-sigma = {gov[0]/1e6:.1f} MPa bei x = {gov[3]:.2f} m)"
        fm.x_governing = gov[3]
        out.members[mname] = fm
        if progress:
            progress(f"Ermuedung {mname}: D = {fm.util:.3f}")
    return out
