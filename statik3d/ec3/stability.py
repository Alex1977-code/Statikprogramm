"""
Stabilitaetsnachweise nach DIN EN 1993-1-1, 6.3:
    6.3.1  Biegeknicken (und Drillknicken doppeltsymmetrischer I-Profile)
    6.3.2  Biegedrillknicken (allgemeiner Fall 6.3.2.2 / gewalzte Profile 6.3.2.3)
    6.3.3  Biegung und Druck: Interaktion nach Anhang B (Methode 2)

Alle Groessen SI (N, m, Pa). Druckkraft N_Ed > 0.
"""
from __future__ import annotations

import numpy as np

from ..model import Section
from .section_class import ClassResult

BUCKLING_ALPHA = {"a0": 0.13, "a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}


# --------------------------------------------------------------------------
def buckling_curve(sec: Section, fy: float, axis: str) -> str:
    """Knicklinie nach Tabelle 6.2 (axis 'y' oder 'z')."""
    s460 = fy >= 455e6
    if sec.typ == "I":
        hb = sec.h / sec.b if sec.b > 0 else 2.0
        tf = sec.tf
        if sec.fabrication == "welded":
            if tf <= 0.040:
                return "b" if axis == "y" else "c"
            return "c" if axis == "y" else "d"
        if hb > 1.2:
            if tf <= 0.040:
                return "a0" if s460 else ("a" if axis == "y" else "b")
            if tf <= 0.100:
                return "a" if s460 else ("b" if axis == "y" else "c")
            return "c" if s460 else "d"
        if tf <= 0.100:
            return "a" if s460 else ("b" if axis == "y" else "c")
        return "c" if s460 else "d"
    if sec.typ in ("RHS", "CHS"):
        if sec.fabrication == "cold_formed":
            return "c"
        return "a0" if s460 else "a"
    if sec.typ in ("rect", "circle"):
        return "c"
    return "c"


def chi(lam: float, alpha: float) -> float:
    """Abminderungsfaktor Gl. 6.49."""
    if lam <= 0.2:
        return 1.0
    phi = 0.5 * (1 + alpha * (lam - 0.2) + lam ** 2)
    return float(min(1.0 / (phi + np.sqrt(max(phi ** 2 - lam ** 2, 0.0))), 1.0))


def flexural_buckling(sec: Section, E: float, G: float, fy: float, cls: ClassResult,
                      Lcr_y: float, Lcr_z: float, gamma_M1: float) -> dict:
    """Biegeknicken um y und z, Drillknicken (I-Profile). Rueckgabe dict."""
    A = sec.A if cls.cls < 4 else cls.A_eff
    out = {"A": A}
    for ax, I, L in (("y", sec.Iy, Lcr_y), ("z", sec.Iz, Lcr_z)):
        Ncr = np.pi ** 2 * E * I / L ** 2 if L > 0 else np.inf
        lam = np.sqrt(A * fy / Ncr) if Ncr > 0 and np.isfinite(Ncr) else 0.0
        curve = buckling_curve(sec, fy, ax)
        x = chi(lam, BUCKLING_ALPHA[curve])
        out.update({f"N_cr_{ax}": Ncr, f"lam_{ax}": lam, f"chi_{ax}": x, f"curve_{ax}": curve,
                    f"N_b_{ax}_Rd": x * A * fy / gamma_M1, f"Lcr_{ax}": L})
    # Drillknicken (doppeltsymmetrisch): i0^2 = (Iy+Iz)/A
    if sec.typ == "I" and sec.Iw > 0 and Lcr_z > 0:
        i0sq = (sec.Iy + sec.Iz) / sec.A
        NcrT = (G * sec.It + np.pi ** 2 * E * sec.Iw / Lcr_z ** 2) / i0sq
        lamT = np.sqrt(A * fy / NcrT)
        curve = buckling_curve(sec, fy, "z")
        xT = chi(lamT, BUCKLING_ALPHA[curve])
        out.update({"N_cr_T": NcrT, "lam_T": lamT, "chi_T": xT,
                    "N_b_T_Rd": xT * A * fy / gamma_M1})
    else:
        out.update({"N_cr_T": np.inf, "lam_T": 0.0, "chi_T": 1.0, "N_b_T_Rd": np.inf})
    out["N_b_Rd"] = min(out["N_b_y_Rd"], out["N_b_z_Rd"], out["N_b_T_Rd"])
    out["chi_min"] = min(out["chi_y"], out["chi_z"], out["chi_T"])
    return out


# --------------------------------------------------------------------------
def Mcr(sec: Section, E: float, G: float, L: float, k: float = 1.0, kw: float = 1.0,
        C1: float = 1.0, C2: float = 0.0, zg: float = 0.0) -> float:
    """Ideales Biegedrillknickmoment doppeltsymmetrischer Querschnitte
    (Standardformel, z.B. NCCI SN003 / Anhang F ENV 1993-1-1)."""
    if L <= 0 or sec.Iz <= 0:
        return np.inf
    kL = k * L
    term = ((k / kw) ** 2 * sec.Iw / sec.Iz + kL ** 2 * G * sec.It / (np.pi ** 2 * E * sec.Iz)
            + (C2 * zg) ** 2)
    return float(C1 * np.pi ** 2 * E * sec.Iz / kL ** 2 * (np.sqrt(max(term, 0.0)) - C2 * zg))


def moment_shape(M: np.ndarray) -> dict:
    """Kennwerte einer Momentenverteilung: Endmomente, psi, Feldmoment,
    Querlast vorhanden (nicht-lineare Verteilung)?"""
    M = np.asarray(M, float)
    if M.size < 2:
        return {"psi": 1.0, "linear": True, "Mmax": float(abs(M).max()) if M.size else 0.0,
                "Mh": 0.0, "Ms": 0.0, "alpha_s": 0.0, "alpha_h": 0.0}
    M1, M2 = M[0], M[-1]
    Mmax = float(np.abs(M).max())
    lin = np.linspace(M1, M2, M.size)
    dev = float(np.abs(M - lin).max())
    linear = dev <= 0.02 * max(Mmax, 1e-9)
    big, small = (M1, M2) if abs(M1) >= abs(M2) else (M2, M1)
    psi = float(small / big) if abs(big) > 1e-12 else 1.0
    Mh = float(big)
    inner = M[1:-1] if M.size > 2 else M
    Ms = float(inner[np.argmax(np.abs(inner))]) if inner.size else 0.0
    return {"psi": psi, "linear": linear, "Mmax": Mmax, "Mh": Mh, "Ms": Ms,
            "alpha_s": Ms / Mh if abs(Mh) > 1e-12 else np.inf,
            "alpha_h": Mh / Ms if abs(Ms) > 1e-12 else np.inf}


def C1_factor(M: np.ndarray) -> tuple[float, str]:
    """Momentenbeiwert C1 fuer Mcr: linearer Verlauf -> 1.77 - 1.04 psi + 0.27 psi^2 <= 2.6,
    sonst Kirby/Nethercot aus den Viertelspunktmomenten."""
    sh = moment_shape(M)
    if sh["Mmax"] <= 0:
        return 1.0, "M = 0"
    if sh["linear"]:
        psi = sh["psi"]
        C1 = min(1.77 - 1.04 * psi + 0.27 * psi ** 2, 2.6)
        return float(C1), f"linear, psi = {psi:.2f}"
    M = np.asarray(M, float)
    n = M.size
    MA = abs(M[int(round(0.25 * (n - 1)))])
    MB = abs(M[int(round(0.5 * (n - 1)))])
    MC = abs(M[int(round(0.75 * (n - 1)))])
    C1 = min(12.5 * sh["Mmax"] / (2.5 * sh["Mmax"] + 3 * MA + 4 * MB + 3 * MC), 2.5)
    return float(C1), "Querlast (Viertelspunkte)"


def Cm_factor(M: np.ndarray, sway: bool = False) -> tuple[float, str]:
    """Aequivalenter Momentenbeiwert Cm nach Tabelle B.3 (Gleichlast-Spalten)."""
    if sway:
        return 0.9, "verschieblich"
    sh = moment_shape(M)
    if sh["Mmax"] <= 0:
        return 1.0, "M = 0"
    psi = sh["psi"]
    if sh["linear"]:
        return float(max(0.6 + 0.4 * psi, 0.4)), f"linear, psi = {psi:.2f}"
    Mh, Ms = sh["Mh"], sh["Ms"]
    if abs(Mh) >= abs(Ms):
        a_s = Ms / Mh if abs(Mh) > 0 else 0.0
        if a_s >= 0:
            Cm = 0.2 + 0.8 * a_s
        elif psi >= 0:
            Cm = 0.1 - 0.8 * a_s
        else:
            Cm = 0.1 * (1 - psi) - 0.8 * a_s
        return float(max(Cm, 0.4)), f"Querlast, alpha_s = {a_s:.2f}"
    a_h = Mh / Ms if abs(Ms) > 0 else 0.0
    if a_h >= 0 or psi >= 0:
        Cm = 0.95 + 0.05 * a_h
    else:
        Cm = 0.95 + 0.05 * a_h * (1 + 2 * psi)
    return float(max(Cm, 0.4)), f"Querlast, alpha_h = {a_h:.2f}"


def lt_curve(sec: Section, method: str) -> tuple[str, float, float, float]:
    """(Knicklinie, alpha_LT, lambda_LT,0, beta) fuer Biegedrillknicken."""
    hb = sec.h / sec.b if sec.b > 0 else 2.0
    welded = sec.fabrication == "welded"
    if method == "rolled" and sec.typ == "I":
        if welded:
            c = "c" if hb <= 2 else "d"
        else:
            c = "b" if hb <= 2 else "c"
        return c, BUCKLING_ALPHA[c], 0.4, 0.75
    if sec.typ == "I":
        if welded:
            c = "c" if hb <= 2 else "d"
        else:
            c = "a" if hb <= 2 else "b"
    else:
        c = "d"
    return c, BUCKLING_ALPHA[c], 0.2, 1.0


def lateral_torsional(sec: Section, fy: float, cls: ClassResult, Mcr_val: float,
                      method: str, gamma_M1: float, C1: float = 1.0) -> dict:
    """chi_LT und M_b,Rd nach 6.3.2.2 bzw. 6.3.2.3 (mit f-Korrektur)."""
    if cls.cls in (1, 2):
        Wy = sec.Wpl_y
    elif cls.cls == 3:
        Wy = sec.Wel_y
    else:
        Wy = cls.Weff_y
    out = {"Wy": Wy, "M_cr": Mcr_val}
    if not np.isfinite(Mcr_val) or Mcr_val <= 0:
        out.update({"lam_LT": 0.0, "chi_LT": 1.0, "M_b_Rd": Wy * fy / gamma_M1,
                    "curve": "-", "f": 1.0, "method": method})
        return out
    lam = float(np.sqrt(Wy * fy / Mcr_val))
    curve, alpha, lam0, beta = lt_curve(sec, method)
    if lam <= lam0:
        x = 1.0
    else:
        phi = 0.5 * (1 + alpha * (lam - lam0) + beta * lam ** 2)
        x = 1.0 / (phi + np.sqrt(max(phi ** 2 - beta * lam ** 2, 0.0)))
        x = min(x, 1.0)
        if method == "rolled":
            x = min(x, 1.0 / lam ** 2)
    f = 1.0
    if method == "rolled" and sec.typ == "I":
        kc = 1.0 / np.sqrt(max(C1, 1.0))
        f = min(1.0 - 0.5 * (1 - kc) * (1 - 2.0 * (lam - 0.8) ** 2), 1.0)
        f = max(f, 0.5)
        x = min(x / f, 1.0)
    out.update({"lam_LT": lam, "chi_LT": float(x), "M_b_Rd": float(x) * Wy * fy / gamma_M1,
                "curve": curve, "f": f, "method": method, "lam_LT_0": lam0})
    return out


# --------------------------------------------------------------------------
def interaction_factors(sec: Section, cls: ClassResult, lam_y: float, lam_z: float,
                        n_y: float, n_z: float, Cmy: float, Cmz: float, CmLT: float,
                        susceptible: bool) -> dict:
    """Interaktionsbeiwerte k_ij nach Anhang B (Tabellen B.1 / B.2)."""
    plastic = cls.cls in (1, 2)
    if plastic:
        kyy = min(Cmy * (1 + (lam_y - 0.2) * n_y), Cmy * (1 + 0.8 * n_y))
        if sec.typ == "I":
            kzz = min(Cmz * (1 + (2 * lam_z - 0.6) * n_z), Cmz * (1 + 1.4 * n_z))
        else:
            kzz = min(Cmz * (1 + (lam_z - 0.2) * n_z), Cmz * (1 + 0.8 * n_z))
        kyz = 0.6 * kzz
        if not susceptible:
            kzy = 0.6 * kyy
        else:
            d = max(CmLT - 0.25, 0.05)
            if lam_z < 0.4:
                kzy = min(0.6 + lam_z, 1 - 0.1 * lam_z * n_z / d)
            else:
                kzy = max(1 - 0.1 * lam_z * n_z / d, 1 - 0.1 * n_z / d)
    else:
        kyy = min(Cmy * (1 + 0.6 * lam_y * n_y), Cmy * (1 + 0.6 * n_y))
        kzz = min(Cmz * (1 + 0.6 * lam_z * n_z), Cmz * (1 + 0.6 * n_z))
        kyz = kzz
        if not susceptible:
            kzy = 0.8 * kyy
        else:
            d = max(CmLT - 0.25, 0.05)
            kzy = max(1 - 0.05 * lam_z * n_z / d, 1 - 0.05 * n_z / d)
    return {"kyy": kyy, "kyz": kyz, "kzy": kzy, "kzz": kzz}


def member_stability(sec: Section, E: float, G: float, fy: float, cls: ClassResult,
                     N_Ed: float, My_Ed: float, Mz_Ed: float, My_dist: np.ndarray,
                     Mz_dist: np.ndarray, Lcr_y: float, Lcr_z: float, L_LT: float,
                     k_z: float = 1.0, k_w: float = 1.0, C1: float = None,
                     zg: float = 0.0, lt_check: bool = True, lt_method: str = "general",
                     sway_y: bool = False, sway_z: bool = False,
                     gamma_M1: float = 1.1) -> dict:
    """Vollstaendiger Stabilitaetsnachweis eines Stabes (Druck > 0, Momente Betraege).
    Rueckgabe: dict mit 'checks' {name: (util, text)}, 'util', 'details'."""
    checks: dict[str, tuple[float, str]] = {}
    fb = flexural_buckling(sec, E, G, fy, cls, Lcr_y, Lcr_z, gamma_M1)
    A = fb["A"]
    if cls.cls in (1, 2):
        Wy, Wz = sec.Wpl_y, sec.Wpl_z
    elif cls.cls == 3:
        Wy, Wz = sec.Wel_y, sec.Wel_z
    else:
        Wy, Wz = cls.Weff_y, cls.Weff_z
    NRk = A * fy
    MyRk = Wy * fy
    MzRk = Wz * fy
    details = dict(fb)

    # ---- 6.3.1 Biegeknicken ----
    if N_Ed > 0:
        for ax in ("y", "z"):
            if fb[f"lam_{ax}"] > 0.2 and N_Ed / fb[f"N_cr_{ax}"] > 0.04:
                checks[f"Knicken {ax} (6.3.1)"] = (
                    N_Ed / fb[f"N_b_{ax}_Rd"],
                    f"N_Ed/N_b,{ax},Rd = {N_Ed/1e3:.1f}/{fb[f'N_b_{ax}_Rd']/1e3:.1f} kN; "
                    f"Lcr = {fb[f'Lcr_{ax}']:.2f} m, lambda = {fb[f'lam_{ax}']:.3f}, "
                    f"Linie {fb[f'curve_{ax}']}, chi = {fb[f'chi_{ax}']:.3f}")
        if np.isfinite(fb["N_cr_T"]) and fb["lam_T"] > 0.2 and N_Ed / fb["N_cr_T"] > 0.04:
            checks["Drillknicken (6.3.1.4)"] = (
                N_Ed / fb["N_b_T_Rd"],
                f"N_Ed/N_b,T,Rd = {N_Ed/1e3:.1f}/{fb['N_b_T_Rd']/1e3:.1f} kN; "
                f"lambda_T = {fb['lam_T']:.3f}, chi_T = {fb['chi_T']:.3f}")

    # ---- 6.3.2 Biegedrillknicken ----
    susceptible = sec.typ == "I" and lt_check
    chiLT = 1.0
    lt = None
    if susceptible and My_Ed > 0:
        if C1 is None:
            C1v, c1txt = C1_factor(My_dist)
        else:
            C1v, c1txt = C1, "vorgegeben"
        C2 = 0.5 if zg != 0 else 0.0
        Mcr_v = Mcr(sec, E, G, L_LT, k_z, k_w, C1v, C2, zg)
        lt = lateral_torsional(sec, fy, cls, Mcr_v, lt_method, gamma_M1, C1v)
        chiLT = lt["chi_LT"]
        details.update({"M_cr": Mcr_v, "C1": C1v, "C1_text": c1txt, "lam_LT": lt["lam_LT"],
                        "chi_LT": chiLT, "curve_LT": lt["curve"], "f_LT": lt["f"],
                        "L_LT": L_LT})
        lam0 = lt.get("lam_LT_0", 0.2)
        if lt["lam_LT"] > lam0 and My_Ed / Mcr_v > lam0 ** 2:
            checks["Biegedrillknicken (6.3.2)"] = (
                My_Ed / lt["M_b_Rd"],
                f"M_Ed/M_b,Rd = {My_Ed/1e3:.1f}/{lt['M_b_Rd']/1e3:.1f} kNm; "
                f"M_cr = {Mcr_v/1e3:.1f} kNm (C1 = {C1v:.2f}, L_LT = {L_LT:.2f} m), "
                f"lambda_LT = {lt['lam_LT']:.3f}, Linie {lt['curve']}, chi_LT = {chiLT:.3f}")
    else:
        details.update({"chi_LT": 1.0, "M_cr": np.inf, "lam_LT": 0.0})

    # ---- 6.3.3 Interaktion ----
    if N_Ed > 0 and (My_Ed > 0 or Mz_Ed > 0):
        Cmy, cmy_t = Cm_factor(My_dist, sway_y)
        Cmz, cmz_t = Cm_factor(Mz_dist, sway_z)
        CmLT = Cmy
        n_y = N_Ed / (fb["chi_y"] * NRk / gamma_M1)
        n_z = N_Ed / (fb["chi_z"] * NRk / gamma_M1)
        kf = interaction_factors(sec, cls, fb["lam_y"], fb["lam_z"], n_y, n_z,
                                 Cmy, Cmz, CmLT, susceptible)
        MyRd = chiLT * MyRk / gamma_M1
        MzRd = MzRk / gamma_M1
        # Klasse 4: Zusatzmomente aus der Verschiebung der Schwerachse,
        # Gl. (6.61) und (6.62) mit (M_Ed + dM_Ed)
        dMy = N_Ed * abs(cls.eN_y) if cls.cls == 4 else 0.0
        dMz = N_Ed * abs(cls.eN_z) if cls.cls == 4 else 0.0
        My_i, Mz_i = My_Ed + dMy, Mz_Ed + dMz
        zusatz = (f"; ΔM_y,Ed = {dMy/1e3:.1f} kNm, ΔM_z,Ed = {dMz/1e3:.1f} kNm "
                  f"aus e_N (Klasse 4)" if (dMy or dMz) else "")
        u61 = n_y + kf["kyy"] * My_i / MyRd + kf["kyz"] * Mz_i / MzRd
        u62 = n_z + kf["kzy"] * My_i / MyRd + kf["kzz"] * Mz_i / MzRd
        checks["Interaktion Gl. 6.61"] = (
            u61, f"{n_y:.3f} + {kf['kyy']:.3f}·{My_i/MyRd:.3f} + {kf['kyz']:.3f}·{Mz_i/MzRd:.3f}"
                 f" (Cmy = {Cmy:.2f} {cmy_t}){zusatz}")
        checks["Interaktion Gl. 6.62"] = (
            u62, f"{n_z:.3f} + {kf['kzy']:.3f}·{My_i/MyRd:.3f} + {kf['kzz']:.3f}·{Mz_i/MzRd:.3f}"
                 f" (Cmz = {Cmz:.2f} {cmz_t})")
        details.update(kf)
        details.update({"Cmy": Cmy, "Cmz": Cmz, "n_y": n_y, "n_z": n_z})
    util = max((v[0] for v in checks.values()), default=0.0)
    gov = max(checks, key=lambda k: checks[k][0]) if checks else ""
    return {"checks": checks, "util": util, "governing": gov, "details": details,
            "N_Ed": N_Ed, "My_Ed": My_Ed, "Mz_Ed": Mz_Ed}
