"""
Querschnittsnachweise nach DIN EN 1993-1-1, 6.2.

Eingangsgroessen: N (Zug > 0), Vy, Vz, Mt, My, Mz [SI], Section, fy, gamma_M0.
Ergebnis: dict mit Widerstaenden, Ausnutzungen je Nachweis und dem
massgebenden Nachweis.
"""
from __future__ import annotations

import numpy as np

from ..model import Section
from .section_class import classify, ClassResult, epsilon


def section_resistance(sec: Section, fy: float, cls: ClassResult, gamma_M0: float = 1.0) -> dict:
    """Bemessungswerte der Querschnittstragfaehigkeit."""
    g = gamma_M0
    if cls.cls in (1, 2):
        Wy, Wz = sec.Wpl_y, sec.Wpl_z
    elif cls.cls == 3:
        Wy, Wz = sec.Wel_y, sec.Wel_z
    else:
        Wy, Wz = cls.Weff_y, cls.Weff_z
    A = sec.A if cls.cls < 4 else cls.A_eff
    Avz = sec.Asz if sec.Asz > 0 else sec.A
    Avy = sec.Asy if sec.Asy > 0 else sec.A
    if sec.typ == "CHS":
        Avz = Avy = 2 * sec.A / np.pi
    elif sec.typ == "RHS":
        Avz = sec.A * sec.h / (sec.b + sec.h)
        Avy = sec.A * sec.b / (sec.b + sec.h)
    return {
        "N_t_Rd": sec.A * fy / g, "N_c_Rd": A * fy / g,
        "M_y_Rd": Wy * fy / g, "M_z_Rd": Wz * fy / g,
        "V_y_Rd": Avy * fy / (np.sqrt(3) * g), "V_z_Rd": Avz * fy / (np.sqrt(3) * g),
        "Wy": Wy, "Wz": Wz, "A": A, "Avy": Avy, "Avz": Avz,
    }


def _torsion_stress(sec: Section, Mt: float) -> float:
    """St.-Venant-Schubspannung [Pa] aus Torsionsmoment (Woelbkrafttorsion vernachlaessigt)."""
    if Mt == 0 or sec.It <= 0:
        return 0.0
    if sec.typ == "RHS":
        Am = (sec.b - sec.tw) * (sec.h - sec.tw)
        return abs(Mt) / (2 * Am * sec.tw)
    if sec.typ == "CHS":
        Am = np.pi * (sec.h - sec.tw) ** 2 / 4
        return abs(Mt) / (2 * Am * sec.tw)
    tmax = sec.t_max if sec.t_max > 0 else (sec.h / 2 if sec.h > 0 else 0.01)
    return abs(Mt) * tmax / sec.It


def section_check(sec: Section, fy: float, N: float, Vy: float, Vz: float, Mt: float,
                  My: float, Mz: float, gamma_M0: float = 1.0, cls: ClassResult = None,
                  gamma_M1: float = 1.1, a_steifen: float = 0.0,
                  starre_endsteife: bool = False) -> dict:
    """Alle Querschnittsnachweise an einer Stelle. Rueckgabe:
    {"class": ClassResult, "res": Widerstaende, "checks": {name: (util, text)},
     "util": max, "governing": name}"""
    cls = cls or classify(sec, fy, N, My, Mz)
    R = section_resistance(sec, fy, cls, gamma_M0)
    g = gamma_M0
    checks: dict[str, tuple[float, str]] = {}
    Nc = max(-N, 0.0)
    Nt = max(N, 0.0)
    aMy, aMz = abs(My), abs(Mz)
    aVy, aVz = abs(Vy), abs(Vz)

    # 6.2.3 / 6.2.4 Normalkraft
    if Nt > 0:
        checks["N_t (6.2.3)"] = (Nt / R["N_t_Rd"], f"N_Ed/N_t,Rd = {Nt/1e3:.1f}/{R['N_t_Rd']/1e3:.1f} kN")
    if Nc > 0:
        checks["N_c (6.2.4)"] = (Nc / R["N_c_Rd"], f"N_Ed/N_c,Rd = {Nc/1e3:.1f}/{R['N_c_Rd']/1e3:.1f} kN")

    # 6.2.6 Querkraft (+ 6.2.7 Torsion)
    tau_t = _torsion_stress(sec, Mt)
    fvd = fy / (np.sqrt(3) * g)
    red_T = 1.0
    if tau_t > 0:
        if sec.typ in ("RHS", "CHS"):
            red_T = max(1.0 - tau_t / fvd, 0.0)
        else:
            red_T = float(np.sqrt(max(1.0 - tau_t / (1.25 * fvd), 0.0)))
        checks["tau_t (6.2.7)"] = (tau_t / fvd, f"tau_t,Ed/(fy/(sqrt3 gM0)) = {tau_t/1e6:.1f}/{fvd/1e6:.1f} MPa")
    VyRd = R["V_y_Rd"] * red_T
    VzRd = R["V_z_Rd"] * red_T
    # Schoepft die Torsion die Schubtragfaehigkeit schon allein aus (red_T = 0),
    # bliebe V_Rd = 0 und die Ausnutzung unendlich. Dann wird stattdessen die
    # Summe der Schubspannungen aus Torsion und Querkraft nachgewiesen - ein
    # endlicher, nachvollziehbarer Wert, der ueber 1 liegt.
    if aVz > 0:
        if VzRd > 0:
            checks["V_z (6.2.6)"] = (aVz / VzRd,
                                     f"V_z,Ed/V_pl,z,Rd = {aVz/1e3:.1f}/{VzRd/1e3:.1f} kN")
        else:
            tau = tau_t + (aVz / R["Avz"] if R["Avz"] > 0 else 0.0)
            checks["V_z + tau_t (6.2.6/6.2.7)"] = (
                tau / fvd, f"Torsion schoepft die Schubtragfaehigkeit allein aus: "
                f"(tau_t + tau_V)/f_vd = {tau/1e6:.1f}/{fvd/1e6:.1f} MPa")
    if aVy > 0:
        if VyRd > 0:
            checks["V_y (6.2.6)"] = (aVy / VyRd,
                                     f"V_y,Ed/V_pl,y,Rd = {aVy/1e3:.1f}/{VyRd/1e3:.1f} kN")
        else:
            tau = tau_t + (aVy / R["Avy"] if R["Avy"] > 0 else 0.0)
            checks["V_y + tau_t (6.2.6/6.2.7)"] = (
                tau / fvd, f"Torsion schoepft die Schubtragfaehigkeit allein aus: "
                f"(tau_t + tau_V)/f_vd = {tau/1e6:.1f}/{fvd/1e6:.1f} MPa")
    if sec.typ == "I" and sec.tw > 0 and sec.h > 2 * sec.tf:
        # Schubbeulen des Stegblechs: der Nachweis wird gefuehrt, nicht nur
        # angekuendigt (DIN EN 1993-1-5, Abschnitt 5).
        from .beulen import schubbeulen, schubbeulen_noetig
        hw = sec.h - 2 * sec.tf
        noetig, _grenze, text = schubbeulen_noetig(hw, sec.tw, fy, a_steifen)
        if noetig:
            b = schubbeulen(hw, sec.tw, fy, a_steifen, gamma_M1, starre_endsteife)
            V_b = b.get("V_b_Rd", 0.0)
            if V_b > 0:
                checks["Schubbeulen V_b,Rd (EN 1993-1-5, 5.2)"] = (
                    aVz / V_b,
                    f"h_w/t_w = {hw / sec.tw:.1f} > {text}; λ̄_w = {b['lambda_w']:.3f}, "
                    f"χ_w = {b['chi_w']:.3f}, V_b,Rd = {V_b / 1e3:.0f} kN "
                    f"(ohne Flanschanteil)")
                if aVz > 0.5 * V_b and abs(My) > 0:
                    # Interaktion M-V nach 7.1: eta_3 = V_Ed / V_bw,Rd
                    eta3 = aVz / max(b.get("V_bw_Rd", V_b), 1e-9)
                    MfRd = (sec.b * sec.tf * (sec.h - sec.tf) * fy / gamma_M0
                            if sec.b > 0 and sec.tf > 0 else 0.0)
                    MplRd = R["M_y_Rd"]
                    if MplRd > 0 and abs(My) > MfRd:
                        eta1 = abs(My) / MplRd
                        w = eta1 + (1.0 - MfRd / MplRd) * (2.0 * eta3 - 1.0) ** 2
                        checks["Biegung + Schubbeulen (EN 1993-1-5, 7.1)"] = (
                            w, f"η_1 + (1 − M_f,Rd/M_pl,Rd)(2 η_3 − 1)² mit "
                               f"η_1 = {eta1:.3f}, η_3 = {eta3:.3f}, "
                               f"M_f,Rd = {MfRd / 1e3:.0f} kNm")

    # 6.2.8 Biegung + Querkraft: Abminderung
    rho_y = (2 * aVz / VzRd - 1) ** 2 if VzRd > 0 and aVz > 0.5 * VzRd else 0.0
    rho_z = (2 * aVy / VyRd - 1) ** 2 if VyRd > 0 and aVy > 0.5 * VyRd else 0.0
    MyRd = R["M_y_Rd"]
    MzRd = R["M_z_Rd"]
    if rho_y > 0:
        if sec.typ == "I" and cls.cls <= 2:
            Aw = (sec.h - 2 * sec.tf) * sec.tw
            MyRd = min((sec.Wpl_y - rho_y * Aw ** 2 / (4 * sec.tw)) * fy / g, MyRd)
        else:
            MyRd *= (1 - rho_y)
    if rho_z > 0:
        MzRd *= (1 - rho_z)

    # 6.2.5 Biegung
    if aMy > 0:
        checks["M_y (6.2.5)"] = (aMy / MyRd, f"M_y,Ed/M_c,y,Rd = {aMy/1e3:.1f}/{MyRd/1e3:.1f} kNm"
                                 + (f" (V-Abminderung rho={rho_y:.2f})" if rho_y else ""))
    if aMz > 0:
        checks["M_z (6.2.5)"] = (aMz / MzRd, f"M_z,Ed/M_c,z,Rd = {aMz/1e3:.1f}/{MzRd/1e3:.1f} kNm")

    # 6.2.9 Biegung + Normalkraft
    Nabs = max(Nc, Nt)
    if Nabs > 0 and (aMy > 0 or aMz > 0):
        if cls.cls <= 2:
            Npl = sec.A * fy / g
            n = Nabs / Npl
            if sec.typ == "I":
                a = min((sec.A - 2 * sec.b * sec.tf) / sec.A, 0.5)
                hw = sec.h - 2 * sec.tf
                small = Nabs <= 0.25 * Npl and Nabs <= 0.5 * hw * sec.tw * fy / g
                MNy = MyRd if small else min(MyRd * (1 - n) / (1 - 0.5 * a), MyRd)
                if n <= a:
                    MNz = MzRd
                else:
                    MNz = MzRd * (1 - ((n - a) / (1 - a)) ** 2)
                al, be = 2.0, max(5 * n, 1.0)
            elif sec.typ == "RHS":
                aw = min((sec.A - 2 * sec.b * sec.tw) / sec.A, 0.5)
                af = min((sec.A - 2 * sec.h * sec.tw) / sec.A, 0.5)
                MNy = min(MyRd * (1 - n) / (1 - 0.5 * aw), MyRd)
                MNz = min(MzRd * (1 - n) / (1 - 0.5 * af), MzRd)
                al = be = min(1.66 / (1 - 1.13 * n ** 2), 6.0) if n < 0.94 else 6.0
            elif sec.typ == "CHS":
                MNy = MNz = MyRd * (1 - n ** 1.7)
                al = be = 2.0
            else:
                MNy = MyRd * (1 - n)
                MNz = MzRd * (1 - n)
                al = be = 1.0
            MNy = max(MNy, 1e-30)
            MNz = max(MNz, 1e-30)
            if aMy > 0 and aMz > 0:
                u = (aMy / MNy) ** al + (aMz / MNz) ** be
                checks["M+N biaxial (6.2.9.1)"] = (
                    u, f"(My/M_N,y)^{al:.2f} + (Mz/M_N,z)^{be:.2f} = {u:.3f}, n = {n:.3f}")
            elif aMy > 0:
                checks["M_y+N (6.2.9.1)"] = (aMy / MNy, f"M_y,Ed/M_N,y,Rd = {aMy/1e3:.1f}/{MNy/1e3:.1f} kNm (n={n:.3f})")
            else:
                checks["M_z+N (6.2.9.1)"] = (aMz / MNz, f"M_z,Ed/M_N,z,Rd = {aMz/1e3:.1f}/{MNz/1e3:.1f} kNm (n={n:.3f})")
        else:
            # elastisch (Klasse 3) bzw. wirksam (Klasse 4): lineare Interaktion
            NRd = R["N_c_Rd"] if Nc > 0 else R["N_t_Rd"]
            u = Nabs / NRd + aMy / MyRd + aMz / MzRd
            checks["N+M elastisch (6.2.9.2/3)"] = (
                u, f"N/N_Rd + My/M_y,Rd + Mz/M_z,Rd = {Nabs/NRd:.3f} + {aMy/MyRd:.3f} + {aMz/MzRd:.3f}")

    # 6.2.1(5) Vergleichsspannung (elastisch, informativ fuer Klasse 3/4, massgebend bei Torsion)
    if cls.cls >= 3 or tau_t > 0:
        sig = Nabs / R["A"] + aMy / max(R["Wy"], 1e-30) + aMz / max(R["Wz"], 1e-30)
        tau = max(aVz / R["Avz"] if R["Avz"] else 0.0, aVy / R["Avy"] if R["Avy"] else 0.0) + tau_t
        u = (sig / (fy / g)) ** 2 + 3 * (tau / (fy / g)) ** 2
        checks["sigma_v (6.2.1(5))"] = (u, f"(sig/fyd)^2 + 3 (tau/fyd)^2 = {u:.3f}; "
                                            f"sig = {sig/1e6:.1f} MPa, tau = {tau/1e6:.1f} MPa")

    util = max((v[0] for v in checks.values()), default=0.0)
    gov = max(checks, key=lambda k: checks[k][0]) if checks else ""
    return {"class": cls, "res": R, "checks": checks, "util": util, "governing": gov,
            "M_y_Rd": MyRd, "M_z_Rd": MzRd}
