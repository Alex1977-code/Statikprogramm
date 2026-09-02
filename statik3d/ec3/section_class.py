"""
Querschnittsklassifizierung nach DIN EN 1993-1-1, 5.5 (Tabelle 5.2) und
wirksame Querschnitte der Klasse 4 nach DIN EN 1993-1-5, 4.4.

Vorzeichen: Druck positiv (N_c = -N), Momente als Betraege.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..model import Section


def epsilon(fy: float) -> float:
    return float(np.sqrt(235e6 / fy))


@dataclass
class ClassResult:
    cls: int = 1
    flange: int = 1
    web: int = 1
    details: dict = field(default_factory=dict)
    A_eff: float = 0.0          # wirksame Flaeche (nur Klasse 4, sonst = A)
    Weff_y: float = 0.0
    Weff_z: float = 0.0
    eN_y: float = 0.0           # Verschiebung der Schwerachse (Klasse 4, reine Druckkraft)
    warnings: list = field(default_factory=list)

    def text(self) -> str:
        return f"Klasse {self.cls} (Flansch {self.flange}, Steg {self.web})"


# --------------------------------------------------------------------------
def _internal_class(ct: float, eps: float, alpha: float, psi: float) -> int:
    """Innenliegendes druckbeanspruchtes Teil (Tab. 5.2 Blatt 1)."""
    if alpha <= 0:
        return 1                     # kein Druck
    # Klasse 1
    lim1 = 396 * eps / (13 * alpha - 1) if alpha > 0.5 else 36 * eps / alpha
    if ct <= lim1:
        return 1
    lim2 = 456 * eps / (13 * alpha - 1) if alpha > 0.5 else 41.5 * eps / alpha
    if ct <= lim2:
        return 2
    if psi > -1:
        lim3 = 42 * eps / (0.67 + 0.33 * psi)
    else:
        lim3 = 62 * eps * (1 - psi) * np.sqrt(-psi)
    return 3 if ct <= lim3 else 4


def _outstand_class(ct: float, eps: float) -> int:
    """Einseitig gestuetztes Teil unter Druck (Tab. 5.2 Blatt 2)."""
    if ct <= 9 * eps:
        return 1
    if ct <= 10 * eps:
        return 2
    if ct <= 14 * eps:
        return 3
    return 4


def _web_state(sec: Section, fy: float, Nc: float, My: float, c: float, t: float):
    """(alpha, psi) fuer den Steg eines doppeltsymmetrischen Profils unter
    Druckkraft Nc (>0) und Moment My (Betrag)."""
    if Nc <= 0 and My <= 0:
        return 0.0, 1.0
    # plastisch: Druckzonenanteil
    if My <= 0:
        alpha = 1.0
    else:
        alpha = 0.5 + Nc / (2 * c * t * fy)
        alpha = float(min(max(alpha, 0.0), 1.0))
        if Nc <= 0:
            alpha = 0.5
    # elastisch: Spannungsverhaeltnis
    A = sec.A
    W = sec.Wel_y if sec.Wel_y > 0 else 1e-30
    s_top = Nc / A + My / W            # Druck positiv
    s_bot = Nc / A - My / W
    if s_top <= 0 and s_bot <= 0:
        return 0.0, 1.0
    smax = max(s_top, s_bot)
    smin = min(s_top, s_bot)
    psi = smin / smax if smax > 0 else 1.0
    return alpha, float(max(psi, -1.0))


# --------------------------------------------------------------------------
def classify(sec: Section, fy: float, N: float = 0.0, My: float = 0.0,
             Mz: float = 0.0) -> ClassResult:
    """Querschnittsklasse fuer die Schnittgroessen N (Zug > 0), My, Mz."""
    eps = epsilon(fy)
    Nc = max(-N, 0.0)
    My = abs(My)
    Mz = abs(Mz)
    res = ClassResult(A_eff=sec.A, Weff_y=sec.Wel_y, Weff_z=sec.Wel_z)
    res.details["eps"] = eps

    if sec.typ == "I":
        cf = (sec.b - sec.tw - 2 * sec.r) / 2.0
        ctf = cf / sec.tf
        # Flansch: Druck bei N_c oder Biegung um y (Druckflansch), Biegung um z
        flange_comp = Nc > 0 or My > 0 or Mz > 0
        res.flange = _outstand_class(ctf, eps) if flange_comp else 1
        cw = sec.h - 2 * sec.tf - 2 * sec.r
        ctw = cw / sec.tw
        alpha, psi = _web_state(sec, fy, Nc, My, cw, sec.tw)
        res.web = _internal_class(ctw, eps, alpha, psi)
        res.details.update({"c/t Flansch": ctf, "c/t Steg": ctw, "alpha": alpha, "psi": psi})
        res.cls = max(res.flange, res.web)
        if res.cls == 4:
            _effective_I(sec, fy, eps, Nc, My, alpha, psi, res)
    elif sec.typ == "RHS":
        cf = sec.b - 2 * sec.tw - 2 * sec.r
        cw = sec.h - 2 * sec.tw - 2 * sec.r
        ctf = cf / sec.tw
        ctw = cw / sec.tw
        # Gurte (innenliegend) unter Druck: reine Druck-Grenzen (alpha=1, psi=1) bei Nc/My
        res.flange = _internal_class(ctf, eps, 1.0, 1.0) if (Nc > 0 or My > 0) else 1
        alpha, psi = _web_state(sec, fy, Nc, My, cw, sec.tw)
        res.web = _internal_class(ctw, eps, alpha, psi)
        if Mz > 0:      # Biegung um z: Gurte werden zu 'Stegen'
            res.flange = max(res.flange, _internal_class(ctf, eps, 0.5, -1.0))
        res.details.update({"c/t Gurt": ctf, "c/t Steg": ctw, "alpha": alpha, "psi": psi})
        res.cls = max(res.flange, res.web)
        if res.cls == 4:
            _effective_RHS(sec, fy, eps, Nc, My, res)
    elif sec.typ == "CHS":
        dt = sec.h / sec.tw
        if dt <= 50 * eps ** 2:
            res.cls = 1
        elif dt <= 70 * eps ** 2:
            res.cls = 2
        elif dt <= 90 * eps ** 2:
            res.cls = 3
        else:
            res.cls = 4
            res.warnings.append("CHS Klasse 4: Beulnachweis nach EN 1993-1-6 erforderlich "
                                "(hier elastisch mit Bruttoquerschnitt)")
        res.flange = res.web = res.cls
        res.details["d/t"] = dt
    elif sec.typ in ("rect", "circle"):
        res.cls = res.flange = res.web = 1
    else:
        res.cls = res.flange = res.web = 3
        res.warnings.append("Querschnittsgeometrie unbekannt - elastischer Nachweis (Klasse 3)")
    return res


# --------------------------------------------------------------------------
# Wirksame Querschnitte (EN 1993-1-5, 4.4)
# --------------------------------------------------------------------------
def _rho_internal(bt: float, eps: float, psi: float) -> float:
    if psi == 1:
        k = 4.0
    elif psi > 0:
        k = 8.2 / (1.05 + psi)
    elif psi == 0:
        k = 7.81
    elif psi > -1:
        k = 7.81 - 6.29 * psi + 9.78 * psi ** 2
    else:
        k = 23.9
    lam = bt / (28.4 * eps * np.sqrt(k))
    if lam <= 0.5 + np.sqrt(max(0.085 - 0.055 * psi, 0)):
        return 1.0
    return float(min((lam - 0.055 * (3 + psi)) / lam ** 2, 1.0))


def _rho_outstand(bt: float, eps: float, k: float = 0.43) -> float:
    lam = bt / (28.4 * eps * np.sqrt(k))
    if lam <= 0.748:
        return 1.0
    return float(min((lam - 0.188) / lam ** 2, 1.0))


def _rect_props(rects):
    """rects: Liste (y0, y1, z0, z1). Rueckgabe A, zs, Iy, Iz um den Schwerpunkt."""
    A = sum((y1 - y0) * (z1 - z0) for y0, y1, z0, z1 in rects)
    zs = sum((y1 - y0) * (z1 - z0) * 0.5 * (z0 + z1) for y0, y1, z0, z1 in rects) / A
    ys = sum((y1 - y0) * (z1 - z0) * 0.5 * (y0 + y1) for y0, y1, z0, z1 in rects) / A
    Iy = sum((y1 - y0) * (z1 - z0) ** 3 / 12 + (y1 - y0) * (z1 - z0) * (0.5 * (z0 + z1) - zs) ** 2
             for y0, y1, z0, z1 in rects)
    Iz = sum((z1 - z0) * (y1 - y0) ** 3 / 12 + (y1 - y0) * (z1 - z0) * (0.5 * (y0 + y1) - ys) ** 2
             for y0, y1, z0, z1 in rects)
    return A, ys, zs, Iy, Iz


def _effective_I(sec: Section, fy, eps, Nc, My, alpha, psi, res: ClassResult):
    """Wirksamer Querschnitt eines doppeltsymmetrischen I-Profils (ohne Ausrundungen)."""
    h, b, tw, tf = sec.h, sec.b, sec.tw, sec.tf
    cf = (b - tw) / 2.0            # Flanschueberstand (konservativ ohne r)
    hw = h - 2 * tf
    # --- reiner Druck: A_eff ---
    rho_f = _rho_outstand(cf / tf, eps)
    rho_w = _rho_internal(hw / tw, eps, 1.0)
    A_eff_c = 2 * (tw + 2 * rho_f * cf) * tf + rho_w * hw * tw
    # --- Biegung um y: Druckflansch + Steg (psi = -1 bzw. aus Bruttoquerschnitt) ---
    zt = h / 2.0
    top = (-(tw / 2 + rho_f * cf), tw / 2 + rho_f * cf, zt - tf, zt)      # Druckflansch (oben)
    bot = (-b / 2, b / 2, -zt, -zt + tf)
    rects = [top, bot, (-tw / 2, tw / 2, -zt + tf, zt - tf)]
    A1, _, zs1, _, _ = _rect_props(rects)
    # Spannungsverhaeltnis im Steg (Schwerachse verschoben)
    z_top_w = zt - tf - zs1
    z_bot_w = -zt + tf - zs1
    psi_w = z_bot_w / z_top_w if z_top_w > 0 else -1.0
    psi_w = max(psi_w, -1.0)
    rho = _rho_internal(hw / tw, eps, psi_w)
    bc = hw / (1 - psi_w) if psi_w < 1 else hw        # Druckzone
    beff = rho * bc
    be1 = 0.4 * beff
    be2 = 0.6 * beff
    # Steg: wirksam be1 am Druckflansch, be2 am Ende der Druckzone, Zugzone voll
    z_c_end = zt - tf - bc                              # Ende der Druckzone
    web_rects = [(-tw / 2, tw / 2, zt - tf - be1, zt - tf),
                 (-tw / 2, tw / 2, z_c_end, z_c_end + be2),
                 (-tw / 2, tw / 2, -zt + tf, z_c_end)]
    web_rects = [r for r in web_rects if r[3] > r[2]]
    A2, _, zs2, Iy2, _ = _rect_props([top, bot] + web_rects)
    Weff_y = Iy2 / max(zt - zs2, zt + zs2)
    # --- Biegung um z: Flansche als einseitig gestuetzte Teile, Steg neutral ---
    rho_fz = _rho_outstand(cf / tf, eps)
    bz = tw / 2 + rho_fz * cf
    Iz_eff = 2 * tf * (2 * bz) ** 3 / 12 + hw * tw ** 3 / 12
    Weff_z = Iz_eff / bz
    res.A_eff = A_eff_c
    res.Weff_y = min(Weff_y, sec.Wel_y) if sec.Wel_y > 0 else Weff_y
    res.Weff_z = min(Weff_z, sec.Wel_z) if sec.Wel_z > 0 else Weff_z
    res.eN_y = 0.0
    res.details.update({"rho_f": rho_f, "rho_w": rho_w, "A_eff": A_eff_c, "Weff_y": res.Weff_y})


def _effective_RHS(sec: Section, fy, eps, Nc, My, res: ClassResult):
    h, b, t = sec.h, sec.b, sec.tw
    cf = b - 2 * t
    cw = h - 2 * t
    rho_f = _rho_internal(cf / t, eps, 1.0)
    rho_w = _rho_internal(cw / t, eps, 1.0)
    res.A_eff = sec.A - 2 * (1 - rho_f) * cf * t - 2 * (1 - rho_w) * cw * t
    # Biegung um y: Druckgurt reduziert, Stege mit psi=-1
    rho_wb = _rho_internal(cw / t, eps, -1.0)
    top = (-b / 2, -b / 2 + t, h / 2 - t, h / 2)
    rects = [(-b / 2, b / 2, -h / 2, -h / 2 + t),                       # Zuggurt
             (-rho_f * cf / 2, rho_f * cf / 2, h / 2 - t, h / 2),       # Druckgurt (wirksam)
             (-b / 2, -b / 2 + t, h / 2 - t, h / 2), (b / 2 - t, b / 2, h / 2 - t, h / 2)]
    bc = cw / 2.0
    beff = rho_wb * bc
    for y0 in (-b / 2, b / 2 - t):
        rects.append((y0, y0 + t, -h / 2 + t, 0.0))                        # Zugzone
        rects.append((y0, y0 + t, h / 2 - t - 0.4 * beff, h / 2 - t))     # be1
        rects.append((y0, y0 + t, 0.0, 0.6 * beff))                        # be2
    A2, _, zs2, Iy2, _ = _rect_props(rects)
    res.Weff_y = min(Iy2 / max(h / 2 - zs2, h / 2 + zs2), sec.Wel_y)
    res.Weff_z = sec.Wel_z * res.A_eff / sec.A
    res.details.update({"rho_f": rho_f, "rho_w": rho_w, "A_eff": res.A_eff})
