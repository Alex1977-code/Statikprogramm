"""
Querschnittsklassifizierung nach DIN EN 1993-1-1, 5.5 (Tabelle 5.2) und
wirksame Querschnitte der Klasse 4 nach DIN EN 1993-1-5, 4.4.

Vorzeichen: Druck positiv (N_c = -N), Momente als Betraege.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    eN_y: float = 0.0           # Verschiebung der Schwerachse in z (Klasse 4, reiner Druck)
    eN_z: float = 0.0           # Verschiebung der Schwerachse in y
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
            # Fuer das Kreisrohr gibt es keine wirksamen Breiten nach
            # EN 1993-1-5, 4.4; der Nachweis laeuft spannungsbasiert nach
            # EN 1993-1-6, 8.5 (siehe section_check). Die Querschnittswerte
            # bleiben deshalb die des Bruttoquerschnitts.
            res.details["schalenbeulen"] = True
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
def k_sigma_internal(psi: float) -> float:
    """Beulwert eines beidseitig gestuetzten Teils, EN 1993-1-5 Tab. 4.1."""
    from .beulen import k_sigma
    return k_sigma(psi, "beidseitig")


def k_sigma_outstand(psi: float = 1.0, druck_am_freien_rand: bool = True) -> float:
    """
    Beulwert eines einseitig gestuetzten Teils, EN 1993-1-5 Tab. 4.2.

    ``psi`` ist das Spannungsverhaeltnis ueber die Breite des Teils,
    ``druck_am_freien_rand`` unterscheidet die beiden Blaetter der Tabelle.
    """
    from .beulen import k_sigma
    return k_sigma(psi, "einseitig", druck_am_freien_rand)


def _rho_info(bt: float, eps: float, psi: float, k: float, innen: bool) -> dict:
    """Abminderungsbeiwert rho mit allen Zwischenwerten (EN 1993-1-5, 4.4(2))."""
    lam = bt / (28.4 * eps * np.sqrt(k))
    if innen:
        grenze = 0.5 + np.sqrt(max(0.085 - 0.055 * psi, 0.0))
        rho = 1.0 if lam <= grenze else min((lam - 0.055 * (3 + psi)) / lam ** 2, 1.0)
    else:
        grenze = 0.748
        rho = 1.0 if lam <= grenze else min((lam - 0.188) / lam ** 2, 1.0)
    return {"b_t": float(bt), "psi": float(psi), "k_sigma": float(k),
            "lambda_p": float(lam), "grenze": float(grenze), "rho": float(max(rho, 0.0))}


def _rho_internal(bt: float, eps: float, psi: float) -> float:
    return _rho_info(bt, eps, psi, k_sigma_internal(psi), True)["rho"]


def _rho_outstand(bt: float, eps: float, k: float = 0.43) -> float:
    return _rho_info(bt, eps, 1.0, k, False)["rho"]


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
    """
    Wirksamer Querschnitt eines doppeltsymmetrischen I-Profils (EN 1993-1-5, 4.4).

    Nach EN 1993-1-1, 6.2.9.3 werden drei Querschnitte gebildet:

      A_eff     aus reinem Druck (psi = 1 in allen Teilen)
      W_eff,y   aus reiner Biegung um y
      W_eff,z   aus reiner Biegung um z

    Die Ausrundungen bleiben unberuecksichtigt (der Flanschueberstand wird mit
    (b - t_w)/2 statt (b - t_w - 2r)/2 angesetzt) - das liegt auf der sicheren
    Seite.  Die Schwerachsenverschiebung e_N wird aus dem wirksamen
    Druckquerschnitt berechnet, nicht angenommen.
    """
    h, b, tw, tf = sec.h, sec.b, sec.tw, sec.tf
    cf = (b - tw) / 2.0            # Flanschueberstand (konservativ ohne r)
    hw = h - 2 * tf
    zt = h / 2.0
    d = {}

    # ---------------- reiner Druck: A_eff und e_N ----------------
    i_f = _rho_info(cf / tf, eps, 1.0, k_sigma_outstand(1.0), False)
    i_w = _rho_info(hw / tw, eps, 1.0, k_sigma_internal(1.0), True)
    rho_f, rho_w = i_f["rho"], i_w["rho"]
    # Steg unter Gleichdruck: b_eff = rho h_w, je zur Haelfte an beiden Raendern
    be = rho_w * hw
    druck = [(-(tw / 2 + rho_f * cf), tw / 2 + rho_f * cf, zt - tf, zt),
             (-(tw / 2 + rho_f * cf), tw / 2 + rho_f * cf, -zt, -zt + tf),
             (-tw / 2, tw / 2, zt - tf - be / 2, zt - tf),
             (-tw / 2, tw / 2, -zt + tf, -zt + tf + be / 2)]
    druck = [r for r in druck if r[3] > r[2] and r[1] > r[0]]
    A_eff_c, ys_c, zs_c, _, _ = _rect_props(druck)
    d["druck"] = {"flansch": i_f, "steg": i_w, "b_eff_Steg": float(be),
                  "A_eff": float(A_eff_c)}

    # ---------------- Biegung um y: W_eff,y ----------------
    # psi im Steg nach 4.4(3) aus dem Bruttoquerschnitt: reine Biegung -> -1
    i_wy = _rho_info(hw / tw, eps, -1.0, k_sigma_internal(-1.0), True)
    rho_wy = i_wy["rho"]
    bc = hw / 2.0                                   # Druckzone (psi = -1)
    beff = rho_wy * bc
    be1, be2 = 0.4 * beff, 0.6 * beff
    top = (-(tw / 2 + rho_f * cf), tw / 2 + rho_f * cf, zt - tf, zt)
    bot = (-b / 2, b / 2, -zt, -zt + tf)
    z_c_end = zt - tf - bc                          # Ende der Druckzone (= Schwerachse)
    web = [(-tw / 2, tw / 2, zt - tf - be1, zt - tf),
           (-tw / 2, tw / 2, z_c_end, z_c_end + be2),
           (-tw / 2, tw / 2, -zt + tf, z_c_end)]
    rects = [r for r in ([top, bot] + web) if r[3] > r[2] and r[1] > r[0]]
    _A2, _ys2, zs2, Iy2, _ = _rect_props(rects)
    Weff_y = Iy2 / max(zt - zs2, zt + zs2)
    d["biegung_y"] = {"flansch": i_f, "steg": i_wy, "b_eff": float(beff),
                      "b_e1": float(be1), "b_e2": float(be2),
                      "z_s": float(zs2), "I_eff": float(Iy2), "W_eff": float(Weff_y)}

    # ---------------- Biegung um z: W_eff,z ----------------
    # Jede Flanschhaelfte ist ein einseitig gestuetztes Teil mit der groessten
    # Druckspannung am freien Rand; psi = 0 am Steg (Tab. 4.2).
    i_fz = _rho_info(cf / tf, eps, 0.0, k_sigma_outstand(0.0, True), False)
    bz = tw / 2 + i_fz["rho"] * cf
    Iz_eff = 2 * tf * (2 * bz) ** 3 / 12 + hw * tw ** 3 / 12
    Weff_z = Iz_eff / bz
    d["biegung_z"] = {"flansch": i_fz, "b_eff_halb": float(bz),
                      "I_eff": float(Iz_eff), "W_eff": float(Weff_z)}

    res.A_eff = A_eff_c
    res.Weff_y = min(Weff_y, sec.Wel_y) if sec.Wel_y > 0 else Weff_y
    res.Weff_z = min(Weff_z, sec.Wel_z) if sec.Wel_z > 0 else Weff_z
    # Schwerachsenverschiebung: der wirksame Druckquerschnitt gegen den Brutto-
    # querschnitt (dessen Schwerpunkt hier im Ursprung liegt)
    res.eN_y = float(zs_c)
    res.eN_z = float(ys_c)
    d["e_N"] = {"e_Ny": res.eN_y, "e_Nz": res.eN_z}
    res.details.update({"rho_f": rho_f, "rho_w": rho_w, "A_eff": A_eff_c,
                        "Weff_y": res.Weff_y, "Weff_z": res.Weff_z,
                        "wirksam": d})


def _effective_RHS(sec: Section, fy, eps, Nc, My, res: ClassResult):
    """Wirksamer Querschnitt eines Rechteckhohlprofils (EN 1993-1-5, 4.4)."""
    h, b, t = sec.h, sec.b, sec.tw
    cf = b - 2 * t
    cw = h - 2 * t
    d = {}

    # ---------------- reiner Druck ----------------
    i_f = _rho_info(cf / t, eps, 1.0, k_sigma_internal(1.0), True)
    i_w = _rho_info(cw / t, eps, 1.0, k_sigma_internal(1.0), True)
    rho_f, rho_w = i_f["rho"], i_w["rho"]
    bef, bew = rho_f * cf, rho_w * cw
    druck = []
    for z0, z1 in ((h / 2 - t, h / 2), (-h / 2, -h / 2 + t)):      # Gurte
        druck.append((-b / 2, -b / 2 + t + bef / 2, z0, z1))
        druck.append((b / 2 - t - bef / 2, b / 2, z0, z1))
    for y0, y1 in ((-b / 2, -b / 2 + t), (b / 2 - t, b / 2)):      # Stege
        druck.append((y0, y1, h / 2 - t - bew / 2, h / 2 - t))
        druck.append((y0, y1, -h / 2 + t, -h / 2 + t + bew / 2))
    A_eff_c, ys_c, zs_c, _, _ = _rect_props(druck)
    res.A_eff = A_eff_c
    d["druck"] = {"gurt": i_f, "steg": i_w, "A_eff": float(A_eff_c)}

    # ---------------- Biegung um y ----------------
    i_wb = _rho_info(cw / t, eps, -1.0, k_sigma_internal(-1.0), True)
    rho_wb = i_wb["rho"]
    bc = cw / 2.0
    beff = rho_wb * bc
    rects = [(-b / 2, b / 2, -h / 2, -h / 2 + t),                       # Zuggurt voll
             (-b / 2, -b / 2 + t + bef / 2, h / 2 - t, h / 2),          # Druckgurt wirksam
             (b / 2 - t - bef / 2, b / 2, h / 2 - t, h / 2)]
    for y0 in (-b / 2, b / 2 - t):
        rects.append((y0, y0 + t, -h / 2 + t, 0.0))                        # Zugzone voll
        rects.append((y0, y0 + t, h / 2 - t - 0.4 * beff, h / 2 - t))      # b_e1
        rects.append((y0, y0 + t, 0.0, 0.6 * beff))                        # b_e2
    rects = [r for r in rects if r[3] > r[2] and r[1] > r[0]]
    _A2, _ys2, zs2, Iy2, _ = _rect_props(rects)
    res.Weff_y = min(Iy2 / max(h / 2 - zs2, h / 2 + zs2), sec.Wel_y)
    d["biegung_y"] = {"gurt": i_f, "steg": i_wb, "b_eff": float(beff),
                      "z_s": float(zs2), "I_eff": float(Iy2), "W_eff": float(res.Weff_y)}

    # ---------------- Biegung um z: Rollentausch von Gurt und Steg ----------
    i_fb = _rho_info(cf / t, eps, -1.0, k_sigma_internal(-1.0), True)
    bcz = cf / 2.0
    beffz = i_fb["rho"] * bcz
    rectz = [(-b / 2, -b / 2 + t, -h / 2, h / 2),                          # Zugsteg voll
             (b / 2 - t - bew / 2, b / 2, h / 2 - t, h / 2),
             (b / 2 - t - bew / 2, b / 2, -h / 2, -h / 2 + t)]
    for z0 in (-h / 2, h / 2 - t):
        rectz.append((-b / 2 + t, 0.0, z0, z0 + t))                        # Zugzone voll
        rectz.append((b / 2 - t - 0.4 * beffz, b / 2 - t, z0, z0 + t))     # b_e1
        rectz.append((0.0, 0.6 * beffz, z0, z0 + t))                       # b_e2
    rectz = [r for r in rectz if r[3] > r[2] and r[1] > r[0]]
    _A3, ys3, _zs3, _Iy3, Iz3 = _rect_props(rectz)
    res.Weff_z = min(Iz3 / max(b / 2 - ys3, b / 2 + ys3), sec.Wel_z)
    d["biegung_z"] = {"gurt": i_fb, "b_eff": float(beffz), "y_s": float(ys3),
                      "I_eff": float(Iz3), "W_eff": float(res.Weff_z)}

    res.eN_y = float(zs_c)
    res.eN_z = float(ys_c)
    d["e_N"] = {"e_Ny": res.eN_y, "e_Nz": res.eN_z}
    res.details.update({"rho_f": rho_f, "rho_w": rho_w, "A_eff": res.A_eff,
                        "Weff_y": res.Weff_y, "Weff_z": res.Weff_z, "wirksam": d})
