"""
Schweissnaehte nach EN 1993-1-8, Abschnitt 4.

Enthalten sind Kehlnaht und Stumpfnaht, das Richtungsbezogene Verfahren
(4.5.3.2) und das Vereinfachte Verfahren (4.5.3.3), die Korrelationsbeiwerte
beta_w, die Grenzwerte fuer die Nahtdicke und die Umrechnung von Schnittgroessen
einer Nahtgruppe in Spannungen.

Einheiten SI: Kraefte N, Momente Nm, Laengen m, Spannungen Pa.

    from statik3d.joints.welds import Fillet, weld_group_stress
    n = Fillet(a=0.005, length=0.300, fu=490e6, grade="S355")
    print(n.Fw_Rd() / 1e3, "kN Tragfaehigkeit (vereinfacht)")
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Korrelationsbeiwert beta_w nach EN 1993-1-8 Tab. 4.1
BETA_W = {"S235": 0.80, "S275": 0.85, "S355": 0.90,
          "S420": 1.00, "S460": 1.00, "S500": 1.00}

#: Mindestnahtdicke: a >= 3 mm (EN 1993-1-8, 4.5.1) und a >= sqrt(t_max) - 0,5
MIN_THROAT = 0.003


def beta_w(grade: str) -> float:
    g = (grade or "S355").upper().replace(" ", "")
    for k, v in BETA_W.items():
        if g.startswith(k):
            return v
    return 1.0


def fvw_d(fu: float, grade: str, gamma_M2: float = 1.25) -> float:
    """Schubfestigkeit der Kehlnaht f_vw,d = (f_u/sqrt(3))/(beta_w gamma_M2) [Pa]."""
    return (fu / math.sqrt(3.0)) / (beta_w(grade) * gamma_M2)


def min_throat(t_max: float) -> float:
    """Kleinste Nahtdicke [m]: a >= 3 mm und a >= sqrt(t_max [mm]) - 0,5, in mm."""
    return max(MIN_THROAT, (math.sqrt(t_max * 1e3) - 0.5) * 1e-3)


def max_throat(t_min: float) -> float:
    """Groesste sinnvolle Nahtdicke [m]: a <= 0,7 t_min."""
    return 0.7 * t_min


@dataclass
class Fillet:
    """Kehlnaht.

    a:      rechnerische Nahtdicke [m]
    length: wirksame Laenge [m]
    fu:     Zugfestigkeit des schwaecheren Grundwerkstoffs [Pa]
    grade:  Stahlsorte des Grundwerkstoffs (fuer beta_w)
    double: beidseitige Naht (doppelte Flaeche)
    """
    a: float
    length: float
    fu: float = 490e6
    grade: str = "S355"
    double: bool = False
    gamma_M2: float = 1.25

    @property
    def area(self) -> float:
        """Rechnerische Nahtflaeche [m^2]."""
        return self.a * self.length * (2.0 if self.double else 1.0)

    def fvw_d(self) -> float:
        return fvw_d(self.fu, self.grade, self.gamma_M2)

    def Fw_Rd(self) -> float:
        """Tragfaehigkeit je Naht [N] nach dem Vereinfachten Verfahren."""
        return self.fvw_d() * self.area

    def utilisation_simple(self, F: float) -> float:
        """Ausnutzung nach dem Vereinfachten Verfahren (4.5.3.3).

        Die Resultierende F [N] darf in beliebiger Richtung wirken.
        """
        R = self.Fw_Rd()
        return abs(F) / R if R else float("inf")

    def utilisation_directional(self, N_perp: float, V_perp: float, V_par: float) -> dict:
        """Richtungsbezogenes Verfahren (4.5.3.2).

        N_perp: Kraft senkrecht zur Nahtachse, senkrecht zur Nahtflaeche [N]
        V_perp: Kraft senkrecht zur Nahtachse, in der Nahtflaeche [N]
        V_par:  Kraft laengs der Nahtachse [N]

        Die Kraefte werden auf die Nahtflaeche bezogen und nach Gl. (4.1) in
        die Wurzelbedingung eingesetzt; zusaetzlich gilt sigma_senkrecht <=
        0,9 f_u/gamma_M2.
        """
        A = self.area
        if A <= 0:
            raise ValueError("Nahtflaeche ist null.")
        # Zerlegung in die Nahtebene: die Kraft senkrecht zur Naht verteilt
        # sich nach EN 1993-1-8 Bild 4.5 zu gleichen Teilen auf sigma_senkr.
        # und tau_senkr. (Winkel 45 Grad der Kehlnahtflanke).
        s = (N_perp / A) / math.sqrt(2.0)
        t_perp = (N_perp / A) / math.sqrt(2.0) + (V_perp / A) / math.sqrt(2.0)
        t_par = V_par / A
        vergleich = math.sqrt(s ** 2 + 3.0 * (t_perp ** 2 + t_par ** 2))
        grenz = self.fu / (beta_w(self.grade) * self.gamma_M2)
        grenz_s = 0.9 * self.fu / self.gamma_M2
        return {
            "sigma_senkrecht": s, "tau_senkrecht": t_perp, "tau_laengs": t_par,
            "vergleichsspannung": vergleich, "grenzspannung": grenz,
            "eta_vergleich": vergleich / grenz if grenz else float("inf"),
            "eta_sigma": abs(s) / grenz_s if grenz_s else float("inf"),
            "eta": max(vergleich / grenz if grenz else 0.0,
                       abs(s) / grenz_s if grenz_s else 0.0),
        }

    def check_throat(self, t_min: float, t_max: float) -> list[str]:
        out = []
        if self.a < min_throat(t_max) - 1e-12:
            out.append(f"a = {self.a * 1e3:.1f} mm < {min_throat(t_max) * 1e3:.1f} mm "
                       "(kleinste Nahtdicke nach EN 1993-1-8, 4.5.1)")
        if self.a > max_throat(t_min) + 1e-12:
            out.append(f"a = {self.a * 1e3:.1f} mm > 0,7 t = {max_throat(t_min) * 1e3:.1f} mm")
        if self.length < max(6.0 * self.a, 0.030) - 1e-12:
            out.append(f"Nahtlaenge {self.length * 1e3:.0f} mm < "
                       f"max(6a, 30 mm) = {max(6 * self.a, 0.030) * 1e3:.0f} mm "
                       "(EN 1993-1-8, 4.5.1)")
        return out

    def describe(self) -> str:
        return (f"Kehlnaht a = {self.a * 1e3:g} mm, l = {self.length * 1e3:g} mm"
                + (" (beidseitig)" if self.double else "")
                + f", {self.grade}, f_vw,d = {self.fvw_d() / 1e6:.1f} N/mm^2")


@dataclass
class Butt:
    """Stumpfnaht.

    Bei durchgeschweisster Naht mit passendem Zusatzwerkstoff ist die
    Tragfaehigkeit die des schwaecheren Grundwerkstoffs (EN 1993-1-8, 4.7.1);
    nachgewiesen wird dann der Grundwerkstoff. Bei nicht durchgeschweisster
    Naht gilt die Kehlnahtregel mit der wirksamen Nahtdicke.
    """
    thickness: float
    length: float
    fy: float = 355e6
    fu: float = 490e6
    grade: str = "S355"
    full_penetration: bool = True
    gamma_M0: float = 1.0
    gamma_M2: float = 1.25

    @property
    def area(self) -> float:
        return self.thickness * self.length

    def N_Rd(self) -> float:
        """Zugtragfaehigkeit [N]."""
        if self.full_penetration:
            return self.fy * self.area / self.gamma_M0
        return fvw_d(self.fu, self.grade, self.gamma_M2) * self.area

    def describe(self) -> str:
        art = "durchgeschweisst" if self.full_penetration else "nicht durchgeschweisst"
        return (f"Stumpfnaht t = {self.thickness * 1e3:g} mm, l = {self.length * 1e3:g} mm, "
                f"{art}, N_Rd = {self.N_Rd() / 1e3:.0f} kN")


# --------------------------------------------------------------------------
# Nahtgruppen: Schnittgroessen -> Spannungen im Nahtbild
# --------------------------------------------------------------------------
@dataclass
class WeldSegment:
    """Ein gerades Nahtstueck im Nahtbild (Koordinaten in der Anschlussebene).

    p1, p2: Endpunkte [m] in der y-z-Ebene des Anschlusses
    a:      Nahtdicke [m]
    double: beidseitig
    """
    p1: tuple
    p2: tuple
    a: float
    double: bool = False

    @property
    def length(self) -> float:
        return math.dist(self.p1, self.p2)

    @property
    def area(self) -> float:
        return self.a * self.length * (2.0 if self.double else 1.0)

    @property
    def mid(self) -> tuple:
        return (0.5 * (self.p1[0] + self.p2[0]), 0.5 * (self.p1[1] + self.p2[1]))

    @property
    def direction(self) -> tuple:
        L = self.length
        if L <= 0:
            return (1.0, 0.0)
        return ((self.p2[0] - self.p1[0]) / L, (self.p2[1] - self.p1[1]) / L)


def weld_group_properties(segments: list[WeldSegment]) -> dict:
    """Schwerpunkt und Flaechenmomente des Nahtbildes (Nahtflaeche als Linie).

    Rueckgabe: A [m^2], yc, zc [m], Iy, Iz, Ip [m^4] um den Schwerpunkt.
    """
    A = sum(s.area for s in segments)
    if A <= 0:
        raise ValueError("Nahtbild ohne Flaeche.")
    yc = sum(s.area * s.mid[0] for s in segments) / A
    zc = sum(s.area * s.mid[1] for s in segments) / A
    Iy = Iz = 0.0
    for s in segments:
        L = s.length
        if L <= 0:
            continue
        dy, dz = s.direction
        t = s.area / L                      # wirksame Dicke des Streifens
        # Eigenanteil des geraden Streifens plus Steiner
        Iy += t * L ** 3 * dz ** 2 / 12.0 + s.area * (s.mid[1] - zc) ** 2
        Iz += t * L ** 3 * dy ** 2 / 12.0 + s.area * (s.mid[0] - yc) ** 2
    return {"A": A, "yc": yc, "zc": zc, "Iy": Iy, "Iz": Iz, "Ip": Iy + Iz}


def weld_group_stress(segments: list[WeldSegment], N: float = 0.0, Vy: float = 0.0,
                      Vz: float = 0.0, Mt: float = 0.0, My: float = 0.0,
                      Mz: float = 0.0) -> dict:
    """Spannungen im Nahtbild aus den Schnittgroessen des Anschlusses.

    N wirkt senkrecht zur Anschlussebene (Zug/Druck), Vy und Vz in der Ebene,
    Mt um die Anschlussachse, My und Mz um die Achsen der Anschlussebene.
    Rueckgabe je Naht: sigma_senkrecht, tau (in der Ebene) und die
    Vergleichsspannung nach Gl. (4.1) mit der massgebenden Naht.
    """
    p = weld_group_properties(segments)
    A, yc, zc, Iy, Iz, Ip = p["A"], p["yc"], p["zc"], p["Iy"], p["Iz"], p["Ip"]
    out = []
    worst = 0.0
    for s in segments:
        y = s.mid[0] - yc
        z = s.mid[1] - zc
        sigma = N / A + (My * z / Iy if Iy else 0.0) - (Mz * y / Iz if Iz else 0.0)
        tau_y = Vy / A - (Mt * z / Ip if Ip else 0.0)
        tau_z = Vz / A + (Mt * y / Ip if Ip else 0.0)
        tau = math.hypot(tau_y, tau_z)
        # Zerlegung wie bei der Kehlnaht: sigma und tau_senkr. je 1/sqrt(2)
        s_perp = sigma / math.sqrt(2.0)
        t_perp = sigma / math.sqrt(2.0)
        vergleich = math.sqrt(s_perp ** 2 + 3.0 * (t_perp ** 2 + tau ** 2))
        worst = max(worst, vergleich)
        out.append({"naht": s, "sigma": sigma, "tau": tau,
                    "vergleichsspannung": vergleich})
    return {"eigenschaften": p, "nahtspannungen": out, "max_vergleich": worst}
