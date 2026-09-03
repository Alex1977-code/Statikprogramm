"""
Schalenbeulen nach DIN EN 1993-1-6 (Kreiszylinderschalen).

Ein gekruemmtes Blech beult anders als ein ebenes: die Kruemmung erhoeht die
Beullast stark, aber die Schale ist zugleich sehr empfindlich gegen
Vorverformungen. Die Norm traegt dem mit dem **spannungsbasierten Nachweis**
nach Abschnitt 8.5 Rechnung.

Ablauf je Spannungsrichtung (Meridian x, Umfang theta, Schub x-theta):

    1. kritische Beulspannung sigma_Rcr nach Anhang D.1 (Laengenbereich ueber
       omega = l / sqrt(r t))
    2. Beulparameter alpha (elastischer Imperfektionsbeiwert), beta, eta und
       lambda_0 - alpha haengt an der **Herstelltoleranzklasse** A, B oder C
    3. Schlankheit lambda = sqrt(f_yk / sigma_Rcr) und

           lambda <= lambda_0            chi = 1
           lambda_0 < lambda < lambda_p  chi = 1 - beta ((lambda-lambda_0)
                                                        /(lambda_p-lambda_0))^eta
           lambda >= lambda_p            chi = alpha / lambda^2

       mit lambda_p = sqrt(alpha / (1 - beta))
    4. sigma_Rd = chi f_yk / gamma_M1

Die Interaktion folgt 8.5.3(3)::

    (sx/sxRd)^kx - ki (sx sth)/(sxRd sthRd) + (sth/sthRd)^kth + (tau/tauRd)^ktau <= 1

Zug beult nicht: nur Druckspannungen gehen ein.

**Grenzen**: nur Kreiszylinder mit konstanter Wanddicke; Kegel, Kugeln und
ringversteifte Schalen sind nicht enthalten, ebenso wenig die numerischen
Verfahren (LA, GNA, GMNIA) nach Abschnitt 8.6 und 8.7.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

E_STAHL = 210e9
NU = 0.3

#: Herstelltoleranzklassen nach Tab. 8.4 / D.2: Klasse -> (Q, Beschreibung)
QUALITAET = {
    "A": (40.0, "Klasse A – ausgezeichnet"),
    "B": (25.0, "Klasse B – hoch"),
    "C": (16.0, "Klasse C – normal"),
}

#: Imperfektionsbeiwerte alpha fuer Umfangsdruck und Schub (Tab. D.5 / D.6)
ALPHA_THETA = {"A": 0.75, "B": 0.65, "C": 0.50}
ALPHA_TAU = {"A": 0.75, "B": 0.65, "C": 0.50}

#: Randbedingungsbeiwert C_xb (D.1.2.1(6))
C_XB = {"BC1-BC1": 6.0, "BC1-BC2": 3.0, "BC2-BC2": 1.0}


def omega(l: float, r: float, t: float) -> float:
    """Laengenparameter omega = l / sqrt(r t)."""
    return l / math.sqrt(r * t) if r > 0 and t > 0 else 0.0


def laengenbereich(l: float, r: float, t: float) -> str:
    """"kurz", "mittel" oder "lang" nach D.1.2.1."""
    w = omega(l, r, t)
    if w <= 1.7:
        return "kurz"
    if w <= 0.5 * r / t:
        return "mittel"
    return "lang"


# --------------------------------------------------------------------------
# Kritische Beulspannungen (Anhang D.1)
# --------------------------------------------------------------------------
def sigma_x_Rcr(l: float, r: float, t: float, rand: str = "BC1-BC1",
                E: float = E_STAHL) -> dict:
    """Meridionale (axiale) Beulspannung nach D.1.2.1."""
    if r <= 0 or t <= 0:
        return {"sigma_Rcr": float("inf"), "fehler": "Abmessungen fehlen"}
    w = omega(l, r, t)
    bereich = laengenbereich(l, r, t)
    if bereich == "kurz":
        Cx = 1.36 - 1.83 / w + 2.07 / w ** 2 if w > 0 else 1.0
    elif bereich == "mittel":
        Cx = 1.0
    else:
        Cxb = C_XB.get(rand, 6.0)
        Cx = max(1.0 + 0.2 / Cxb * (1.0 - 2.0 * w * t / r), 0.6)
    return {"sigma_Rcr": 0.605 * E * Cx * t / r, "C_x": Cx, "omega": w,
            "bereich": bereich}


def sigma_theta_Rcr(l: float, r: float, t: float, rand: str = "BC1-BC1",
                    E: float = E_STAHL) -> dict:
    """Umfangs-Beulspannung nach D.1.3.1 (BC1/BC2: C_theta = 1,0)."""
    if r <= 0 or t <= 0:
        return {"sigma_Rcr": float("inf"), "fehler": "Abmessungen fehlen"}
    w = omega(l, r, t)
    bereich = laengenbereich(l, r, t)
    Ct = 1.0
    if bereich == "kurz":
        Cts = 1.5 + 10.0 / w ** 2 - 5.0 / w ** 3 if w > 0 else 1.5
        s = 0.92 * E * Cts / (w * r / t) if w > 0 else float("inf")
    elif bereich == "mittel":
        s = 0.92 * E * Ct / (w * r / t) if w > 0 else float("inf")
    else:
        Ctl = Ct + 0.275 + 2.03 * (Ct * w * t / r) ** 4 if r > 0 else Ct
        s = 0.92 * E * Ctl / (w * r / t) if w > 0 else float("inf")
    return {"sigma_Rcr": s, "C_theta": Ct, "omega": w, "bereich": bereich}


def tau_Rcr(l: float, r: float, t: float, E: float = E_STAHL) -> dict:
    """Schub-Beulspannung nach D.1.4.1."""
    if r <= 0 or t <= 0:
        return {"tau_Rcr": float("inf"), "fehler": "Abmessungen fehlen"}
    w = omega(l, r, t)
    bereich = laengenbereich(l, r, t)
    if bereich == "kurz":
        Ct = math.sqrt(1.0 + 42.0 / w ** 3) if w > 0 else 1.0
    elif bereich == "mittel":
        Ct = 1.0
    else:
        Ct = (1.0 / 3.0) * math.sqrt(w * t / r) if r > 0 else 1.0
    return {"tau_Rcr": 0.75 * E * Ct * math.sqrt(1.0 / w) * t / r if w > 0
            else float("inf"), "C_tau": Ct, "omega": w, "bereich": bereich}


# --------------------------------------------------------------------------
# Beulparameter und Abminderung (8.5.2)
# --------------------------------------------------------------------------
def alpha_x(r: float, t: float, klasse: str = "B") -> dict:
    """Elastischer Imperfektionsbeiwert fuer Meridiandruck, D.1.2.2.

        Delta_wk = (1/Q) sqrt(r/t) t,   alpha_x = 0,62 / (1 + 1,91 (Delta_wk/t)^1,44)
    """
    Q = QUALITAET.get(klasse, QUALITAET["B"])[0]
    if r <= 0 or t <= 0:
        return {"alpha": 0.62, "Q": Q}
    dw = (1.0 / Q) * math.sqrt(r / t) * t
    a = 0.62 / (1.0 + 1.91 * (dw / t) ** 1.44)
    return {"alpha": a, "Q": Q, "Delta_wk": dw, "Delta_wk_t": dw / t}


def chi_schale(lam: float, alpha: float, beta: float = 0.6, eta: float = 1.0,
               lam_0: float = 0.2) -> dict:
    """Abminderungsbeiwert chi nach 8.5.2(3)."""
    lam_p = math.sqrt(alpha / (1.0 - beta)) if beta < 1.0 else float("inf")
    if lam <= lam_0:
        chi, zweig = 1.0, "λ̄ ≤ λ̄_0 (kein Beulen)"
    elif lam < lam_p:
        chi = 1.0 - beta * ((lam - lam_0) / (lam_p - lam_0)) ** eta
        zweig = "λ̄_0 < λ̄ < λ̄_p (elastisch-plastisch)"
    else:
        chi = alpha / lam ** 2
        zweig = "λ̄ ≥ λ̄_p (elastisch)"
    return {"chi": chi, "lambda_p": lam_p, "zweig": zweig, "lambda": lam,
            "alpha": alpha, "beta": beta, "eta": eta, "lambda_0": lam_0}


@dataclass
class Zylinderbeulen:
    """Ergebnis eines Schalenbeulnachweises."""
    r: float = 0.0
    t: float = 0.0
    l: float = 0.0
    fy: float = 0.0
    klasse: str = "B"
    sigma_x: float = 0.0
    sigma_theta: float = 0.0
    tau: float = 0.0
    werte: dict = field(default_factory=dict)
    util: float = 0.0
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


def zylinder(r: float, t: float, l: float, fy: float, sigma_x: float = 0.0,
             sigma_theta: float = 0.0, tau: float = 0.0, klasse: str = "B",
             rand: str = "BC1-BC1", gamma_M1: float = 1.1,
             E: float = E_STAHL) -> Zylinderbeulen:
    """Beulnachweis einer Kreiszylinderschale nach Abschnitt 8.5.

    sigma_x, sigma_theta: **Druck** positiv [Pa]; tau: Schubspannung [Pa].
    """
    z = Zylinderbeulen(r=r, t=t, l=l, fy=fy, klasse=klasse,
                       sigma_x=max(sigma_x, 0.0),
                       sigma_theta=max(sigma_theta, 0.0), tau=abs(tau))
    if r <= 0 or t <= 0 or l <= 0 or fy <= 0:
        z.fehler = "Abmessungen oder Streckgrenze fehlen"
        return z
    w = omega(l, r, t)
    if laengenbereich(l, r, t) == "lang":
        z.hinweise.append(
            "Langer Zylinder (ω > 0,5 r/t): neben dem Schalenbeulen ist das "
            "Knicken der Schale als Stab nach EN 1993-1-1 zu prüfen "
            "(EN 1993-1-6, D.1.2.1(7)).")
    if r / t < 20:
        z.hinweise.append(
            f"r/t = {r / t:.0f} < 20: die Schale ist dickwandig, der "
            "spannungsbasierte Beulnachweis nach 8.5 ist dann nicht maßgebend.")

    crx = sigma_x_Rcr(l, r, t, rand, E)
    crt = sigma_theta_Rcr(l, r, t, rand, E)
    crs = tau_Rcr(l, r, t, E)
    ax = alpha_x(r, t, klasse)
    at = ALPHA_THETA.get(klasse, 0.65)
    au = ALPHA_TAU.get(klasse, 0.65)

    def teil(sig, s_cr, alpha, lam_0):
        lam = math.sqrt(fy / s_cr) if s_cr > 0 and math.isfinite(s_cr) else 0.0
        d = chi_schale(lam, alpha, 0.6, 1.0, lam_0)
        d["sigma_Rcr"] = s_cr
        d["sigma_Rd"] = d["chi"] * fy / gamma_M1
        d["eta"] = sig / d["sigma_Rd"] if d["sigma_Rd"] > 0 else 0.0
        return d

    dx = teil(z.sigma_x, crx["sigma_Rcr"], ax["alpha"], 0.2)
    dt = teil(z.sigma_theta, crt["sigma_Rcr"], at, 0.4)
    ds = teil(z.tau * math.sqrt(3.0), crs["tau_Rcr"] * math.sqrt(3.0), au, 0.4)
    ds["tau_Rd"] = ds["sigma_Rd"] / math.sqrt(3.0)
    ds["eta"] = z.tau / ds["tau_Rd"] if ds["tau_Rd"] > 0 else 0.0

    # Interaktion 8.5.3(3)
    kx = 1.25 + 0.75 * dx["chi"]
    kt = 1.25 + 0.75 * dt["chi"]
    ku = 1.75 + 0.25 * ds["chi"]
    ki = (dx["chi"] * dt["chi"]) ** 2
    ex, et, eu = dx["eta"], dt["eta"], ds["eta"]
    wert = ex ** kx - ki * ex * et + et ** kt + eu ** ku
    z.util = wert
    z.werte = {"omega": w, "bereich": crx.get("bereich", ""),
               "r_t": r / t, "meridian": dx, "umfang": dt, "schub": ds,
               "C_x": crx.get("C_x"), "C_theta": crt.get("C_theta"),
               "C_tau": crs.get("C_tau"),
               "alpha_x": ax, "alpha_theta": at, "alpha_tau": au,
               "k_x": kx, "k_theta": kt, "k_tau": ku, "k_i": ki,
               "interaktion": wert, "gamma_M1": gamma_M1,
               "qualitaet": QUALITAET.get(klasse, QUALITAET["B"])[1]}
    if wert <= 0:
        z.hinweise.append("keine Druck- oder Schubbeanspruchung - kein Beulen")
    return z
