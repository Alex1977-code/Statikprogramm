"""
Schrauben nach EN 1993-1-8 und EN 1090-2.

Enthalten sind die Abmessungen (M8 bis M36), die Festigkeitsklassen, die
Lochspiele nach EN 1090-2 Tab. 11 einschliesslich Passschrauben und Langloch,
die Vorspannkraft F_p,C und alle Tragfaehigkeiten nach EN 1993-1-8 Tab. 3.4:
Abscheren, Lochleibung, Zug, Durchstanzen, Gleitfestigkeit, Interaktion,
Blockversagen und die Abminderung langer Anschluesse.

Vorzeichen und Einheiten durchgehend SI: Kraefte in N, Laengen in m,
Spannungen in Pa.

    from statik3d.joints.bolts import Bolt, BoltGeometry
    b = Bolt("M20", "10.9", preloaded=True, mu=0.5)
    print(b.Fv_Rd() / 1e3, "kN je Scherfuge")
    print(b.Fs_Rd() / 1e3, "kN Gleitfestigkeit")
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

#: Abmessungen: Bezeichnung -> (d [mm], A_s Spannungsquerschnitt [mm^2],
#: d_m Mittelwert Schluesselweite/Kopfdurchmesser [mm], Steigung P [mm])
SIZES = {
    "M8":  (8.0,   36.6, 13.5, 1.25),
    "M10": (10.0,  58.0, 16.8, 1.50),
    "M12": (12.0,  84.3, 19.6, 1.75),
    "M14": (14.0, 115.0, 22.5, 2.00),
    "M16": (16.0, 157.0, 24.6, 2.00),
    "M18": (18.0, 192.0, 27.7, 2.50),
    "M20": (20.0, 245.0, 31.4, 2.50),
    "M22": (22.0, 303.0, 33.3, 2.50),
    "M24": (24.0, 353.0, 38.0, 3.00),
    "M27": (27.0, 459.0, 42.8, 3.00),
    "M30": (30.0, 561.0, 46.6, 3.50),
    "M33": (33.0, 694.0, 51.1, 3.50),
    "M36": (36.0, 817.0, 55.9, 4.00),
}

#: Festigkeitsklassen EN 1993-1-8 Tab. 3.1: Klasse -> (f_yb, f_ub) [N/mm^2]
GRADES = {
    "4.6":  (240.0, 400.0),
    "4.8":  (320.0, 400.0),
    "5.6":  (300.0, 500.0),
    "5.8":  (400.0, 500.0),
    "6.8":  (480.0, 600.0),
    "8.8":  (640.0, 800.0),
    "10.9": (900.0, 1000.0),
}

#: Klassen, bei denen alpha_v = 0,5 gilt, wenn das Gewinde in der Scherfuge liegt
ALPHA_V_050 = ("4.8", "5.8", "6.8", "10.9")

#: nur diese Klassen duerfen vorgespannt werden (EN 1993-1-8, 3.1.2)
PRELOAD_GRADES = ("8.8", "10.9")

#: Lochspiel EN 1090-2 Tab. 11: Lochart -> Funktion d [mm] -> Spiel [mm]
def _normal_clearance(d: float) -> float:
    if d <= 14.0:
        return 1.0
    if d <= 24.0:
        return 2.0
    return 3.0


HOLE_TYPES = {
    "normal":      ("Normales Rundloch", _normal_clearance, 1.0),
    "pass":        ("Passschraube", lambda d: 0.3, 1.0),
    "uebergross":  ("Uebergrosses Loch", lambda d: 3.0 if d <= 14 else (4.0 if d <= 22 else 6.0), 0.85),
    "langloch_kurz": ("Kurzes Langloch", _normal_clearance, 0.85),
    "langloch_lang": ("Langes Langloch", _normal_clearance, 0.70),
}

#: Beiwert k_s der Gleitfestigkeit quer zum Langloch (EN 1993-1-8 Tab. 3.6)
KS_PERPENDICULAR = {"langloch_kurz": 0.76, "langloch_lang": 0.63}

#: Reibbeiwerte nach EN 1090-2 Tab. 18 (Klasse der Reibflaeche)
FRICTION_CLASSES = {"A": 0.50, "B": 0.40, "C": 0.30, "D": 0.20}

#: Anschlusskategorien EN 1993-1-8, 3.4
CATEGORIES = {
    "A": "Scher-/Lochleibungsverbindung (SL), nicht vorgespannt",
    "B": "Gleitfeste Verbindung im Gebrauchszustand (GV)",
    "C": "Gleitfeste Verbindung im Grenzzustand der Tragfaehigkeit (GVP)",
    "D": "Zugverbindung, nicht vorgespannt",
    "E": "Zugverbindung, vorgespannt",
}


@dataclass
class BoltGeometry:
    """Lage der Schraube im Anschluss (Rand- und Lochabstaende) [m].

    e1: Randabstand in Kraftrichtung, e2: quer dazu,
    p1: Lochabstand in Kraftrichtung, p2: quer dazu.
    """
    e1: float = 0.0
    e2: float = 0.0
    p1: float = 0.0
    p2: float = 0.0
    inner_1: bool = False       # innen liegend in Kraftrichtung
    inner_2: bool = False       # innen liegend quer zur Kraft


@dataclass
class Bolt:
    """Eine Schraube mit allen Angaben fuer die Nachweise.

    size:      "M12" ... "M36"
    grade:     "4.6" ... "10.9"
    hole:      Lochart, siehe HOLE_TYPES ("pass" = Passschraube)
    preloaded: planmaessig vorgespannt (nur 8.8 und 10.9)
    mu:        Reibbeiwert der Reibflaeche (Klasse A..D oder Zahl)
    shear_planes: Anzahl der Scherfugen
    threads_in_shear: Gewinde liegt in der Scherfuge
    countersunk: Senkschraube (k_2 = 0,63 statt 0,9)
    category:  Anschlusskategorie A..E
    """
    size: str = "M20"
    grade: str = "10.9"
    hole: str = "normal"
    preloaded: bool = False
    mu: float = 0.5
    shear_planes: int = 1
    threads_in_shear: bool = True
    countersunk: bool = False
    category: str = "A"
    gamma_M2: float = 1.25
    gamma_M3: float = 1.25
    gamma_M0: float = 1.00
    gamma_M7: float = 1.10

    def __post_init__(self):
        if self.size not in SIZES:
            raise KeyError(f"Schraubengroesse '{self.size}' unbekannt: {list(SIZES)}")
        if self.grade not in GRADES:
            raise KeyError(f"Festigkeitsklasse '{self.grade}' unbekannt: {list(GRADES)}")
        if self.hole not in HOLE_TYPES:
            raise KeyError(f"Lochart '{self.hole}' unbekannt: {list(HOLE_TYPES)}")
        if self.category not in CATEGORIES:
            raise KeyError(f"Kategorie '{self.category}' unbekannt: {list(CATEGORIES)}")
        if isinstance(self.mu, str):
            self.mu = FRICTION_CLASSES[self.mu.upper()]
        if self.category in ("B", "C", "E"):
            self.preloaded = True
        if self.preloaded and self.grade not in PRELOAD_GRADES:
            raise ValueError(f"Nur die Klassen {PRELOAD_GRADES} duerfen vorgespannt "
                             f"werden, nicht {self.grade} (EN 1993-1-8, 3.1.2).")

    # ---- Abmessungen ---------------------------------------------------
    @property
    def d(self) -> float:
        """Schaftdurchmesser [m]."""
        return SIZES[self.size][0] * 1e-3

    @property
    def As(self) -> float:
        """Spannungsquerschnitt [m^2]."""
        return SIZES[self.size][1] * 1e-6

    @property
    def A(self) -> float:
        """Schaftquerschnitt [m^2]."""
        return math.pi * self.d ** 2 / 4.0

    @property
    def dm(self) -> float:
        """Mittelwert aus Schluesselweite und Kopfdurchmesser [m]."""
        return SIZES[self.size][2] * 1e-3

    @property
    def clearance(self) -> float:
        """Lochspiel [m] - der Weg, den die Schraube frei zurueckliegt."""
        return HOLE_TYPES[self.hole][1](SIZES[self.size][0]) * 1e-3

    @property
    def d0(self) -> float:
        """Lochdurchmesser [m]."""
        return self.d + self.clearance

    @property
    def fyb(self) -> float:
        return GRADES[self.grade][0] * 1e6

    @property
    def fub(self) -> float:
        return GRADES[self.grade][1] * 1e6

    @property
    def ks(self) -> float:
        """Beiwert k_s der Gleitfestigkeit (EN 1993-1-8 Tab. 3.6)."""
        return HOLE_TYPES[self.hole][2]

    @property
    def alpha_v(self) -> float:
        """Beiwert der Abschertragfaehigkeit."""
        if not self.threads_in_shear:
            return 0.6
        return 0.5 if self.grade in ALPHA_V_050 else 0.6

    @property
    def A_shear(self) -> float:
        """Massgebender Querschnitt in der Scherfuge [m^2]."""
        return self.As if self.threads_in_shear else self.A

    @property
    def Fp_C(self) -> float:
        """Planmaessige Vorspannkraft F_p,C = 0,7 f_ub A_s [N] (EN 1993-1-8, 3.6.1)."""
        return 0.7 * self.fub * self.As if self.preloaded else 0.0

    # ---- Tragfaehigkeiten ----------------------------------------------
    def Fv_Rd(self, planes: int = None) -> float:
        """Abschertragfaehigkeit [N] (Tab. 3.4)."""
        n = self.shear_planes if planes is None else planes
        return n * self.alpha_v * self.fub * self.A_shear / self.gamma_M2

    def Ft_Rd(self) -> float:
        """Zugtragfaehigkeit [N] (Tab. 3.4). Senkschraube: k_2 = 0,63."""
        k2 = 0.63 if self.countersunk else 0.9
        return k2 * self.fub * self.As / self.gamma_M2

    def Bp_Rd(self, tp: float, fu: float) -> float:
        """Durchstanzen des Blechs [N]: 0,6 pi d_m t_p f_u / gamma_M2."""
        return 0.6 * math.pi * self.dm * tp * fu / self.gamma_M2

    def alpha_b(self, geo: BoltGeometry, fu: float, direction: int = 1) -> float:
        """Beiwert alpha_b der Lochleibung in Kraftrichtung."""
        if direction == 1:
            e, p, inner = geo.e1, geo.p1, geo.inner_1
        else:
            e, p, inner = geo.e2, geo.p2, geo.inner_2
        ad = (p / (3.0 * self.d0) - 0.25) if inner else (e / (3.0 * self.d0) if e else 0.0)
        return max(0.0, min(ad, self.fub / fu, 1.0))

    def k1(self, geo: BoltGeometry, direction: int = 1) -> float:
        """Beiwert k_1 der Lochleibung quer zur Kraftrichtung."""
        if direction == 1:
            e, p, inner = geo.e2, geo.p2, geo.inner_2
        else:
            e, p, inner = geo.e1, geo.p1, geo.inner_1
        val = (1.4 * p / self.d0 - 1.7) if inner else (2.8 * e / self.d0 - 1.7 if e else 2.5)
        return max(0.0, min(val, 2.5))

    def Fb_Rd(self, t: float, fu: float, geo: BoltGeometry, direction: int = 1) -> float:
        """Lochleibungstragfaehigkeit [N]: k_1 alpha_b f_u d t / gamma_M2."""
        return (self.k1(geo, direction) * self.alpha_b(geo, fu, direction)
                * fu * self.d * t / self.gamma_M2)

    def Fs_Rd(self, Ft_Ed: float = 0.0, sls: bool = False,
              perpendicular_slot: bool = False, n: int = None) -> float:
        """Gleitfestigkeit [N] (EN 1993-1-8, 3.9).

        F_s,Rd = k_s n mu (F_p,C - 0,8 F_t,Ed) / gamma_M3.
        Eine gleichzeitige Zugkraft F_t,Ed mindert die Klemmkraft.
        sls=True rechnet mit gamma_M3,ser = 1,10 (Kategorie B).
        """
        if not self.preloaded:
            return 0.0
        n = self.shear_planes if n is None else n
        ks = KS_PERPENDICULAR.get(self.hole, self.ks) if perpendicular_slot else self.ks
        g = 1.10 if sls else self.gamma_M3
        return max(0.0, ks * n * self.mu * (self.Fp_C - 0.8 * Ft_Ed) / g)

    def interaction(self, Fv_Ed: float, Ft_Ed: float) -> float:
        """Ausnutzung Abscheren mit Zug (Tab. 3.4):
        F_v,Ed/F_v,Rd + F_t,Ed/(1,4 F_t,Rd) <= 1."""
        a = Fv_Ed / self.Fv_Rd() if self.Fv_Rd() else 0.0
        b = Ft_Ed / (1.4 * self.Ft_Rd()) if self.Ft_Rd() else 0.0
        return a + b

    def describe(self) -> str:
        t = f"{self.size} {self.grade}"
        t += f", {HOLE_TYPES[self.hole][0]} d_0 = {self.d0 * 1e3:g} mm"
        t += f", Spiel {self.clearance * 1e3:g} mm"
        if self.preloaded:
            t += f", vorgespannt F_p,C = {self.Fp_C / 1e3:.1f} kN, mu = {self.mu:g}"
        t += f", Kategorie {self.category}"
        return t


def beta_Lf(Lj: float, d: float) -> float:
    """Abminderung langer Anschluesse (EN 1993-1-8, 3.8).

    L_j: Abstand der aeusseren Schrauben in Kraftrichtung [m].
    Fuer L_j > 15 d gilt beta_Lf = 1 - (L_j - 15 d)/(200 d), begrenzt auf
    0,75 <= beta_Lf <= 1,0.
    """
    if Lj <= 15.0 * d:
        return 1.0
    return max(0.75, min(1.0, 1.0 - (Lj - 15.0 * d) / (200.0 * d)))


def block_tearing(Ant: float, Anv: float, fu: float, fy: float,
                  concentric: bool = True, gamma_M2: float = 1.25,
                  gamma_M0: float = 1.0) -> float:
    """Blockversagen (EN 1993-1-8, 3.10.2) [N].

    mittige Beanspruchung:  V_eff,1,Rd = f_u A_nt/gamma_M2 + f_y A_nv/(sqrt(3) gamma_M0)
    aussermittig:           V_eff,2,Rd = 0,5 f_u A_nt/gamma_M2 + f_y A_nv/(sqrt(3) gamma_M0)
    A_nt: Nettoflaeche auf Zug, A_nv: Nettoflaeche auf Schub [m^2].
    """
    k = 1.0 if concentric else 0.5
    return k * fu * Ant / gamma_M2 + fy * Anv / (math.sqrt(3.0) * gamma_M0)


def min_spacing(d0: float) -> dict:
    """Mindestabstaende nach EN 1993-1-8 Tab. 3.3 [m]."""
    return {"e1": 1.2 * d0, "e2": 1.2 * d0, "p1": 2.2 * d0, "p2": 2.4 * d0}


def max_spacing(t: float, exposed: bool = False) -> dict:
    """Groesstabstaende nach EN 1993-1-8 Tab. 3.3 [m]. t = duennstes Blech."""
    if exposed:
        return {"e1": 4.0 * t + 0.040, "e2": 4.0 * t + 0.040,
                "p1": min(14.0 * t, 0.200), "p2": min(14.0 * t, 0.200)}
    return {"e1": float("inf"), "e2": float("inf"),
            "p1": min(14.0 * t, 0.200), "p2": min(14.0 * t, 0.200)}


def check_spacing(geo: BoltGeometry, d0: float, t: float, exposed: bool = False) -> list[str]:
    """Rand- und Lochabstaende pruefen. Rueckgabe: Liste der Verstoesse."""
    out = []
    lo = min_spacing(d0)
    hi = max_spacing(t, exposed)
    for key in ("e1", "e2", "p1", "p2"):
        val = getattr(geo, key)
        if val <= 0:
            continue
        if val < lo[key] - 1e-12:
            out.append(f"{key} = {val * 1e3:.1f} mm < {lo[key] * 1e3:.1f} mm "
                       f"(Mindestabstand nach EN 1993-1-8 Tab. 3.3)")
        if val > hi[key] + 1e-12:
            out.append(f"{key} = {val * 1e3:.1f} mm > {hi[key] * 1e3:.1f} mm "
                       f"(Groesstabstand nach EN 1993-1-8 Tab. 3.3)")
    return out
