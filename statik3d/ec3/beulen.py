"""
Plattenbeulen nach DIN EN 1993-1-5.

Ein duennes Blech unter Druck oder Schub versagt nicht durch Fliessen, sondern
durch Ausbeulen. Dieses Modul enthaelt die Grundlagen dafuer:

**Beulwerte** k_sigma nach Tab. 4.1 (beidseitig gestuetzte Bleche) und Tab. 4.2
(einseitig gestuetzte Bleche), k_tau nach A.3.

**Bezugsspannung** sigma_E = pi^2 E t^2 / (12 (1 - nu^2) b^2), im Stahlbau
gelaeufig als 190000 (t/b)^2 N/mm^2.

**Abminderungsbeiwert** rho nach 4.4(2) beziehungsweise chi_w nach Tab. 5.1
fuer Schub.

**Schubbeulen** nach Abschnitt 5: V_b,Rd = chi_w f_yw h_w t_w / (sqrt(3) g_M1),
begrenzt auf eta f_yw h_w t_w / (sqrt(3) g_M1). Der Flanschanteil V_bf,Rd wird
nicht angesetzt - er liegt auf der sicheren Seite.

**Methode der reduzierten Spannungen** nach Abschnitt 10 fuer ein Beulfeld
unter einem beliebigen Spannungszustand (sigma_x, sigma_z, tau)::

    1/alpha_ult,k^2 = (sx/fy)^2 + (sz/fy)^2 - (sx/fy)(sz/fy) + 3 (tau/fy)^2
    1/alpha_cr      = ... Gl. (10.6) aus den drei Einzelbeulwerten
    lambda_p        = sqrt(alpha_ult,k / alpha_cr)
    Nachweis        Gl. (10.5) mit rho_x, rho_z und chi_w

Alle Formeln sind gegen die Zahlenwerte der Norm geprueft (tests/test_beulen.py).

Grenzen: Laengs- und Quersteifen sind **nicht** enthalten (k_sigma und k_tau
gelten fuer das unversteifte Blechfeld); ebenso wenig das Schalenbeulen nach
EN 1993-1-6 und die Lasteinleitung nach Abschnitt 6.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

E_STAHL = 210e9
NU = 0.3

#: Schubbeul-Beiwert eta (bis S460 nach DIN EN 1993-1-5/NA)
ETA_SCHUB = 1.2


def epsilon(fy: float) -> float:
    """eps = sqrt(235 / f_y) mit f_y in Pa."""
    return math.sqrt(235e6 / fy) if fy > 0 else 1.0


def sigma_E(t: float, b: float, E: float = E_STAHL, nu: float = NU) -> float:
    """Bezugsspannung des Beulens [Pa]: pi^2 E t^2 / (12 (1-nu^2) b^2)."""
    if b <= 0:
        return float("inf")
    return math.pi ** 2 * E * t ** 2 / (12.0 * (1.0 - nu ** 2) * b ** 2)


# --------------------------------------------------------------------------
# Beulwerte
# --------------------------------------------------------------------------
def k_sigma(psi: float, rand: str = "beidseitig", druck_am_rand: bool = True) -> float:
    """Beulwert k_sigma fuer Laengsspannungen.

    psi:  Spannungsverhaeltnis sigma_2 / sigma_1 (Druck positiv gerechnet,
          psi = 1 gleichmaessiger Druck, psi = -1 reine Biegung)
    rand: "beidseitig" (Tab. 4.1, z. B. Steg) oder "einseitig" (Tab. 4.2,
          z. B. Flanschhaelfte)
    druck_am_rand: nur bei "einseitig" - liegt die groessere Druckspannung am
          freien Rand (Tab. 4.2 oben) oder am gestuetzten (unten)?
    """
    p = float(psi)
    if rand == "beidseitig":
        if p >= 1.0:
            return 4.0
        if p > 0.0:
            return 8.2 / (1.05 + p)
        if p == 0.0:
            return 7.81
        if p > -1.0:
            return 7.81 - 6.29 * p + 9.78 * p ** 2
        if p >= -3.0:
            return 5.98 * (1.0 - p) ** 2
        return 5.98 * 16.0
    # einseitig gestuetzt (Tab. 4.2)
    if druck_am_rand:
        if p >= 1.0:
            return 0.43
        if p >= 0.0:
            return 0.578 / (p + 0.34)
        return 1.7 - 5.0 * p + 17.1 * p ** 2
    if p >= 1.0:
        return 0.43
    if p >= 0.0:
        return 0.57 - 0.21 * p + 0.07 * p ** 2
    return 0.57 - 0.21 * p + 0.07 * p ** 2


def k_tau(alpha: float, steifen: int = 0) -> float:
    """Schubbeulwert k_tau nach A.3(1) fuer das unversteifte Blechfeld.

    alpha = a / h_w (Seitenverhaeltnis). Laengssteifen sind nicht enthalten;
    ``steifen`` wird nur gemeldet, nicht gerechnet.
    """
    a = float(alpha)
    if a <= 0:
        return 5.34
    return 5.34 + 4.00 / a ** 2 if a >= 1.0 else 4.00 + 5.34 / a ** 2


# --------------------------------------------------------------------------
# Abminderungsbeiwerte
# --------------------------------------------------------------------------
def rho_platte(lam_p: float, psi: float = 1.0, rand: str = "beidseitig") -> float:
    """Abminderungsbeiwert rho nach 4.4(2)."""
    if lam_p <= 0:
        return 1.0
    if rand == "beidseitig":
        grenze = 0.5 + math.sqrt(max(0.085 - 0.055 * psi, 0.0))
        if lam_p <= grenze:
            return 1.0
        return min(1.0, (lam_p - 0.055 * (3.0 + psi)) / lam_p ** 2)
    if lam_p <= 0.748:
        return 1.0
    return min(1.0, (lam_p - 0.188) / lam_p ** 2)


def chi_w(lam_w: float, starre_endsteife: bool = False,
          eta: float = ETA_SCHUB) -> float:
    """Abminderungsbeiwert chi_w des Stegblechs, Tab. 5.1."""
    if lam_w < 0.83 / eta:
        return eta
    if lam_w < 1.08:
        return 0.83 / lam_w
    return 1.37 / (0.7 + lam_w) if starre_endsteife else 0.83 / lam_w


# --------------------------------------------------------------------------
# Schubbeulen eines Stegblechs (Abschnitt 5)
# --------------------------------------------------------------------------
def schubbeulen_noetig(hw: float, tw: float, fy: float, a: float = 0.0,
                       eta: float = ETA_SCHUB) -> tuple:
    """Ist der Schubbeulnachweis zu fuehren? (ja/nein, Grenze, Text) - 5.1(2)."""
    eps = epsilon(fy)
    if tw <= 0:
        return False, 0.0, "keine Stegdicke"
    if a > 0:
        kt = k_tau(a / hw) if hw > 0 else 5.34
        grenze = 31.0 * eps * math.sqrt(kt) / eta
        text = f"31 ε √k_τ/η = {grenze:.1f} (Quersteifen im Abstand a = {a:.2f} m)"
    else:
        grenze = 72.0 * eps / eta
        text = f"72 ε/η = {grenze:.1f} (nur Endquersteifen)"
    return (hw / tw > grenze), grenze, text


def schubbeulen(hw: float, tw: float, fy: float, a: float = 0.0,
                gamma_M1: float = 1.1, starre_endsteife: bool = False,
                eta: float = ETA_SCHUB) -> dict:
    """Schubbeultragfaehigkeit V_b,Rd eines Stegblechs nach Abschnitt 5.

    a: Abstand der Quersteifen [m]; 0 = nur Steifen an den Auflagern.
    Der Flanschanteil V_bf,Rd wird nicht angesetzt (sichere Seite).
    """
    eps = epsilon(fy)
    if hw <= 0 or tw <= 0:
        return {"V_b_Rd": 0.0, "fehler": "Stegabmessungen unbekannt"}
    if a > 0:
        kt = k_tau(a / hw)
        lam = hw / (37.4 * tw * eps * math.sqrt(kt))
        grund = f"λ̄_w = h_w/(37,4 t_w ε √k_τ), k_τ = {kt:.2f} (5.3(3))"
    else:
        kt = k_tau(0.0)
        lam = hw / (86.4 * tw * eps)
        grund = "λ̄_w = h_w/(86,4 t_w ε), nur Endquersteifen (5.3(3))"
    chi = chi_w(lam, starre_endsteife, eta)
    V_bw = chi * fy * hw * tw / (math.sqrt(3.0) * gamma_M1)
    V_max = eta * fy * hw * tw / (math.sqrt(3.0) * gamma_M1)
    return {"V_b_Rd": min(V_bw, V_max), "V_bw_Rd": V_bw, "V_max": V_max,
            "chi_w": chi, "lambda_w": lam, "k_tau": kt, "eta": eta,
            "grund": grund,
            "tau_cr": kt * sigma_E(tw, hw),
            "begrenzt": V_bw > V_max}


# --------------------------------------------------------------------------
# Methode der reduzierten Spannungen (Abschnitt 10)
# --------------------------------------------------------------------------
def alpha_ult_k(sx: float, sz: float, tau: float, fy: float) -> float:
    """Kleinster Faktor, der die Fliessgrenze erreicht - Gl. (10.3)."""
    if fy <= 0:
        return float("inf")
    q = ((sx / fy) ** 2 + (sz / fy) ** 2 - (sx / fy) * (sz / fy)
         + 3.0 * (tau / fy) ** 2)
    return float("inf") if q <= 0 else 1.0 / math.sqrt(q)


def alpha_cr_gesamt(a_crx: float, a_crz: float, a_crt: float,
                    psi_x: float = 1.0, psi_z: float = 1.0) -> float:
    """Kleinster Faktor, der das Beulen einleitet - Gl. (10.6)."""
    ix = 1.0 / a_crx if a_crx and math.isfinite(a_crx) else 0.0
    iz = 1.0 / a_crz if a_crz and math.isfinite(a_crz) else 0.0
    it = 1.0 / a_crt if a_crt and math.isfinite(a_crt) else 0.0
    if ix <= 0 and iz <= 0 and it <= 0:
        return float("inf")
    A = (1.0 + psi_x) / 4.0 * ix + (1.0 + psi_z) / 4.0 * iz
    B = (A ** 2 + (1.0 - psi_x) / 2.0 * ix ** 2
         + (1.0 - psi_z) / 2.0 * iz ** 2 + it ** 2)
    s = A + math.sqrt(max(B, 0.0))
    return float("inf") if s <= 0 else 1.0 / s


def beulfeld(a: float, b: float, t: float, fy: float, sx: float = 0.0,
             sz: float = 0.0, tau: float = 0.0, psi_x: float = 1.0,
             psi_z: float = 1.0, rand: str = "beidseitig",
             gamma_M1: float = 1.1, starre_endsteife: bool = False,
             eta: float = ETA_SCHUB, E: float = E_STAHL) -> dict:
    """Nachweis eines Beulfeldes nach Abschnitt 10 (reduzierte Spannungen).

    a, b: Laenge und Breite des Feldes [m] (b quer zur Hauptdruckspannung),
    t: Blechdicke [m], fy: Streckgrenze [Pa].
    sx, sz: Druckspannungen [Pa] (Druck **positiv**), tau: Schubspannung [Pa].
    psi_x, psi_z: Spannungsverhaeltnisse der jeweiligen Richtung.

    Rueckgabe: alle Zwischenwerte und die beiden Ausnutzungen -
    ``eta_interaktion`` nach Gl. (10.5) und ``eta_rho_min`` nach der
    Vereinfachung 10.5(2).
    """
    out = {"a": a, "b": b, "t": t, "fy": fy, "sigma_x": sx, "sigma_z": sz,
           "tau": tau, "hinweise": []}
    if b <= 0 or t <= 0 or fy <= 0:
        out["fehler"] = "Abmessungen oder Streckgrenze fehlen"
        return out
    sE = sigma_E(t, b, E)
    alpha = a / b if b > 0 else 1.0
    ksx = k_sigma(psi_x, rand)
    ksz = k_sigma(psi_z, rand)
    kt = k_tau(alpha)
    out.update({"sigma_E": sE, "alpha": alpha, "k_sigma_x": ksx,
                "k_sigma_z": ksz, "k_tau": kt,
                "sigma_cr_x": ksx * sE, "sigma_cr_z": ksz * sE,
                "tau_cr": kt * sE})
    inf = float("inf")
    a_crx = (ksx * sE / sx) if sx > 0 else inf
    a_crz = (ksz * sE / sz) if sz > 0 else inf
    a_crt = (kt * sE / abs(tau)) if abs(tau) > 0 else inf
    a_cr = alpha_cr_gesamt(a_crx, a_crz, a_crt, psi_x, psi_z)
    a_ult = alpha_ult_k(sx, sz, tau, fy)
    out.update({"alpha_cr_x": a_crx, "alpha_cr_z": a_crz, "alpha_cr_tau": a_crt,
                "alpha_cr": a_cr, "alpha_ult_k": a_ult})
    if not math.isfinite(a_cr) or not math.isfinite(a_ult):
        out["lambda_p"] = 0.0
        out["rho_x"] = out["rho_z"] = out["chi_w"] = 1.0
        out["eta_interaktion"] = out["eta_rho_min"] = 0.0
        out["hinweise"].append("keine Beulbeanspruchung im Feld")
        return out
    lam = math.sqrt(a_ult / a_cr)
    rx = rho_platte(lam, psi_x, rand) if sx > 0 else 1.0
    rz = rho_platte(lam, psi_z, rand) if sz > 0 else 1.0
    cw = chi_w(lam, starre_endsteife, eta) if abs(tau) > 0 else 1.0
    fyd = fy / gamma_M1
    out.update({"lambda_p": lam, "rho_x": rx, "rho_z": rz, "chi_w": cw,
                "f_yd": fyd})
    # Gl. (10.5)
    tx = sx / (rx * fyd) if rx > 0 else inf
    tz = sz / (rz * fyd) if rz > 0 else inf
    tt = abs(tau) / (cw * fyd) if cw > 0 else inf
    q = tx ** 2 + tz ** 2 - tx * tz + 3.0 * tt ** 2
    out["eta_interaktion"] = math.sqrt(max(q, 0.0))
    # Vereinfachung 10.5(2): ein einziger Abminderungsbeiwert
    rho_min = min(rx if sx > 0 else 1.0, rz if sz > 0 else 1.0,
                  cw if abs(tau) > 0 else 1.0)
    out["rho_min"] = rho_min
    out["eta_rho_min"] = (1.0 / (rho_min * a_ult / gamma_M1)
                          if rho_min * a_ult > 0 else inf)
    if lam <= 0.5:
        out["hinweise"].append(
            f"λ̄_p = {lam:.3f} ≤ 0,5: das Feld beult nicht, maßgebend ist die "
            "Querschnittstragfähigkeit")
    return out


# --------------------------------------------------------------------------
# Beulfelder eines Modells
# --------------------------------------------------------------------------
def _rahmen(model, elemente) -> tuple:
    """(Ursprung, u, v, n) des Feldes: u laengs, v quer, n Normale.

    u zeigt in die laengere Ausdehnung des Feldes - das ist die Richtung a,
    quer dazu liegt b. Die Elemente muessen in einer Ebene liegen.
    """
    import numpy as np
    P = np.vstack([model.nodes[model.elements[int(e)].nodes] for e in elemente])
    mitte = P.mean(axis=0)
    Q = P - mitte
    # Normale aus der kleinsten Hauptrichtung der Punktwolke
    _u, _s, vt = np.linalg.svd(Q, full_matrices=False)
    n = vt[2]
    eben = float(np.max(np.abs(Q @ n)))
    e1, e2 = vt[0], vt[1]
    L1 = float(np.ptp(Q @ e1))
    L2 = float(np.ptp(Q @ e2))
    if L2 > L1:
        e1, e2, L1, L2 = e2, e1, L2, L1
    return mitte, e1, e2, n, L1, L2, eben


def _dreh(sig: tuple, phi: float) -> tuple:
    """Ebenen-Spannungstensor um phi drehen: (sx, sy, txy) -> (su, sv, tuv)."""
    c, s2 = math.cos(2.0 * phi), math.sin(2.0 * phi)
    sx, sy, txy = sig
    mitte = 0.5 * (sx + sy)
    halb = 0.5 * (sx - sy)
    su = mitte + halb * c + txy * s2
    sv = mitte - halb * c - txy * s2
    tuv = -halb * s2 + txy * c
    return su, sv, tuv


def feldspannungen(model, res, elemente, u, v) -> dict:
    """Membranspannungen des Feldes in den Feldachsen u und v [Pa].

    Druck wird **positiv** zurueckgegeben (so rechnet EN 1993-1-5).
    """
    import numpy as np
    from ..elements import shell as sh
    su_l, sv_l, t_l = [], [], []
    for i in elemente:
        i = int(i)
        d = res.shell_stress.get(i)
        if d is None:
            continue
        e = model.elements[i]
        t = model.shells[e.sec].t
        n = d["n"]
        sig = (float(n[0]) / t, float(n[1]) / t, float(n[2]) / t)
        X = model.nodes[e.nodes]
        T3, _a, _b = sh.shell_frame(X[0], X[1], X[2])
        ex = np.asarray(T3[0], float)
        phi = math.atan2(float(ex @ v), float(ex @ u))
        a, b, c = _dreh(sig, -phi)
        su_l.append(a)
        sv_l.append(b)
        t_l.append(c)
    if not su_l:
        return {}
    su = np.asarray(su_l)
    sv = np.asarray(sv_l)
    tt = np.asarray(t_l)
    return {"sigma_u_max": float(-su.min()), "sigma_u_min": float(-su.max()),
            "sigma_v_max": float(-sv.min()), "sigma_v_min": float(-sv.max()),
            "tau": float(np.abs(tt).max()), "n": len(su_l)}


def _psi(smax: float, smin: float) -> float:
    """Spannungsverhaeltnis psi = sigma_2/sigma_1 mit Druck positiv."""
    if smax <= 0:
        return 1.0
    return max(min(smin / smax, 1.0), -4.0)


def check_beulfeld(model, bf, res, fy: float = 0.0, gamma_M1: float = 1.1) -> dict:
    """Ein Beulfeld gegen ein Ergebnis nachweisen (Abschnitt 10)."""
    out = {"name": bf.name, "hinweise": []}
    if not bf.elemente:
        out["fehler"] = "keine Elemente"
        return out
    try:
        _mitte, u, v, _n, L1, L2, eben = _rahmen(model, bf.elemente)
    except Exception as ex:            # noqa: BLE001
        out["fehler"] = f"Geometrie nicht auswertbar: {ex}"
        return out
    a = bf.a or L1
    b = bf.b or L2
    e0 = model.elements[int(bf.elemente[0])]
    t = bf.t or model.shells[e0.sec].t
    if not fy:
        mat = model.materials.get(e0.mat)
        fy = (mat.yield_strength(t) if mat is not None else 0.0) or 235e6
    if eben > 0.02 * max(L1, L2, 1e-6):
        out["hinweise"].append(
            f"Die Elemente liegen nicht in einer Ebene (Abweichung {eben * 1e3:.0f} mm). "
            "Der Nachweis gilt für ebene Blechfelder; für gekrümmte Bleche ist "
            "EN 1993-1-6 maßgebend.")
    sp = feldspannungen(model, res, bf.elemente, u, v)
    if not sp:
        out["fehler"] = "keine Flächenergebnisse für dieses Feld"
        return out
    r = beulfeld(a=a, b=b, t=t, fy=fy,
                 sx=max(sp["sigma_u_max"], 0.0), sz=max(sp["sigma_v_max"], 0.0),
                 tau=sp["tau"],
                 psi_x=_psi(sp["sigma_u_max"], sp["sigma_u_min"]),
                 psi_z=_psi(sp["sigma_v_max"], sp["sigma_v_min"]),
                 rand=bf.rand, gamma_M1=gamma_M1,
                 starre_endsteife=bf.starre_endsteife)
    r["hinweise"] = out["hinweise"] + r.get("hinweise", [])
    r["name"] = bf.name
    r["spannungen"] = sp
    r["psi_x"] = _psi(sp["sigma_u_max"], sp["sigma_u_min"])
    r["psi_z"] = _psi(sp["sigma_v_max"], sp["sigma_v_min"])
    return r


@dataclass
class BeulCheck:
    """Nachweis eines Beulfeldes, gefuehrt ueber alle GZT-Kombinationen."""
    name: str
    a: float = 0.0
    b: float = 0.0
    t: float = 0.0
    fy: float = 0.0
    util: float = 0.0
    kombination: str = ""
    werte: dict = field(default_factory=dict)      # Zwischenwerte der massgebenden
    je_kombination: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class BeulResults:
    felder: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.felder.values()), default=0.0)

    def summary(self) -> str:
        if not self.felder:
            return "Beulnachweise: keine Beulfelder festgelegt"
        schlecht = [c.name for c in self.felder.values() if c.util > 1.0]
        fehler = [c.name for c in self.felder.values() if c.fehler]
        worst = max(self.felder.values(), key=lambda c: c.util)
        s = (f"Beulen (EN 1993-1-5): {len(self.felder)} Felder, "
             f"{len(self.kombinationen)} Kombinationen, max. Ausnutzung "
             f"{worst.util:.3f} ({worst.name}"
             + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif not fehler:
            s += " - alle erfüllt"
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Beulfeld", "a [m]", "b [m]", "t [mm]", "σ_x [MPa]", "σ_z [MPa]",
                 "τ [MPa]", "λ̄_p", "ρ_x", "χ_w", "Ausnutzung", "Kombination",
                 "Status"]]
        for c in self.felder.values():
            w = c.werte
            rows.append([c.name, f"{c.a:.2f}", f"{c.b:.2f}", f"{c.t * 1e3:.0f}",
                         f"{w.get('sigma_x', 0) / 1e6:.1f}",
                         f"{w.get('sigma_z', 0) / 1e6:.1f}",
                         f"{w.get('tau', 0) / 1e6:.1f}",
                         f"{w.get('lambda_p', 0):.3f}", f"{w.get('rho_x', 1):.3f}",
                         f"{w.get('chi_w', 1):.3f}", f"{c.util:.3f}",
                         c.kombination, c.status()])
        return rows


def check_beulen(model, analysis, combos: list = None, progress=None) -> BeulResults:
    """Alle Beulfelder des Modells ueber alle GZT-Kombinationen nachweisen."""
    from .design import _uls_results
    ergebnisse = _uls_results(model, analysis, combos)
    ds = model.design
    out = BeulResults(kombinationen=list(ergebnisse), settings={
        "gamma_M1": ds.gamma_M1, "eta": ETA_SCHUB,
        "Norm": "DIN EN 1993-1-5, Abschnitt 10 (Methode der reduzierten Spannungen)"})
    for i, (name, bf) in enumerate(model.beulfelder.items()):
        c = BeulCheck(name)
        for kname, res in ergebnisse.items():
            r = check_beulfeld(model, bf, res, gamma_M1=ds.gamma_M1)
            if r.get("fehler"):
                c.fehler = r["fehler"]
                break
            eta = float(r.get("eta_interaktion", 0.0))
            c.je_kombination.append({"kombination": kname, "eta": eta,
                                     "sigma_x": r.get("sigma_x", 0.0),
                                     "sigma_z": r.get("sigma_z", 0.0),
                                     "tau": r.get("tau", 0.0),
                                     "lambda_p": r.get("lambda_p", 0.0)})
            if eta >= c.util:
                c.util, c.kombination, c.werte = eta, kname, r
                c.a, c.b, c.t, c.fy = r["a"], r["b"], r["t"], r["fy"]
                c.hinweise = list(r.get("hinweise", []))
        if not c.je_kombination and not c.fehler:
            c.fehler = "keine Ergebnisse"
        out.felder[name] = c
        if progress:
            progress(f"Beulfeld {name} ({i + 1}/{len(model.beulfelder)})")
    return out
