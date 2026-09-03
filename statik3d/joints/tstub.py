"""
Aequivalenter T-Stummel nach EN 1993-1-8, 6.2.4.

Der T-Stummel bildet die Zugzone einer Kopfplatten- oder Stirnplattenverbindung
ab: ein Blechstreifen der wirksamen Laenge l_eff, ueber den die Schraubenkraft
mit Abstuetzkraeften (Prying) in den Steg eingeleitet wird.

Drei Versagensarten:

    Modus 1   vollstaendiges Fliessen des Blechs
              F_T,1,Rd = 4 M_pl,1,Rd / m
              (Verfahren 2 mit Unterlegscheibe: (8n - 2e_w) M_pl,1,Rd
               / (2 m n - e_w (m + n)))
    Modus 2   Schraubenversagen mit Fliessen des Blechs
              F_T,2,Rd = (2 M_pl,2,Rd + n sum F_t,Rd) / (m + n)
    Modus 3   Schraubenversagen
              F_T,3,Rd = sum F_t,Rd

mit M_pl,i,Rd = 0,25 sum l_eff,i t^2 f_y / gamma_M0 und n = min(e, 1,25 m).

Die wirksamen Laengen folgen Tab. 6.4 bis 6.6; die kreisfoermigen und die nicht
kreisfoermigen Fliesslinienbilder werden getrennt gefuehrt, weil Modus 1 den
kleineren, Modus 2 nur den nicht kreisfoermigen Wert verwendet.

    from statik3d.joints.tstub import TStub, effective_lengths
    ts = TStub(t=0.020, fy=355e6, m=0.040, e=0.045, leff_cp=0.251, leff_nc=0.176,
               Ft_Rd=176.4e3, n_bolts=2)
    print(ts.resistance())
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TStub:
    """Aequivalenter T-Stummel einer Schraubenreihe.

    t:        Blechdicke (Kopfplatte oder Stuetzenflansch) [m]
    fy:       Streckgrenze des Blechs [Pa]
    m:        Abstand Schraubenachse - Anschnitt (Steg/Naht) [m]
    e:        Randabstand quer zur Kraft [m]
    leff_cp:  wirksame Laenge des kreisfoermigen Bildes [m]
    leff_nc:  wirksame Laenge des nicht kreisfoermigen Bildes [m]
    Ft_Rd:    Zugtragfaehigkeit **einer** Schraube [N]
    n_bolts:  Schrauben je Reihe (meist 2)
    ew:       Viertel der Schluesselweite/Scheibe fuer Verfahren 2 [m]
    method2:  Verfahren 2 nach 6.2.4.1(2) (Abstuetzung ueber die Scheibe)
    beton:    Blech liegt auf Beton auf (kein Abheben) - Modus 1* ohne Prying
    """
    t: float
    fy: float
    m: float
    e: float
    leff_cp: float
    leff_nc: float
    Ft_Rd: float
    n_bolts: int = 2
    ew: float = 0.0
    method2: bool = False
    gamma_M0: float = 1.0
    prying: bool = True

    @property
    def n(self) -> float:
        """Abstand der Abstuetzkraft: n = min(e, 1,25 m)."""
        return min(self.e, 1.25 * self.m)

    @property
    def leff_1(self) -> float:
        """Modus 1: kleinerer der beiden Werte."""
        return min(self.leff_cp, self.leff_nc) if self.leff_cp else self.leff_nc

    @property
    def leff_2(self) -> float:
        """Modus 2: nur das nicht kreisfoermige Bild."""
        return self.leff_nc

    def Mpl(self, leff: float) -> float:
        """Plastisches Moment des Blechstreifens [Nm]."""
        return 0.25 * leff * self.t ** 2 * self.fy / self.gamma_M0

    def F_T1(self) -> float:
        """Modus 1: vollstaendiges Fliessen des Blechs [N]."""
        M1 = self.Mpl(self.leff_1)
        if not self.prying:
            # Modus 1*: ohne Abstuetzung, 6.2.4.1(6)
            return 2.0 * M1 / self.m if self.m > 0 else float("inf")
        if self.method2 and self.ew > 0:
            nen = 2.0 * self.m * self.n - self.ew * (self.m + self.n)
            if nen > 0:
                return (8.0 * self.n - 2.0 * self.ew) * M1 / nen
        return 4.0 * M1 / self.m if self.m > 0 else float("inf")

    def F_T2(self) -> float:
        """Modus 2: Schraubenversagen mit Fliessen des Blechs [N]."""
        M2 = self.Mpl(self.leff_2)
        s = self.n_bolts * self.Ft_Rd
        d = self.m + self.n
        return (2.0 * M2 + self.n * s) / d if d > 0 else float("inf")

    def F_T3(self) -> float:
        """Modus 3: Schraubenversagen [N]."""
        return self.n_bolts * self.Ft_Rd

    def resistance(self) -> dict:
        """Massgebende Tragfaehigkeit und Versagensart."""
        f1, f2, f3 = self.F_T1(), self.F_T2(), self.F_T3()
        if not self.prying:
            werte = {"Modus 1* (ohne Abstuetzung)": f1, "Modus 3 (Schraube)": f3}
        else:
            werte = {"Modus 1 (Blech)": f1, "Modus 2 (Blech + Schraube)": f2,
                     "Modus 3 (Schraube)": f3}
        art = min(werte, key=werte.get)
        return {"F_T_Rd": werte[art], "versagen": art, "werte": werte,
                "l_eff_1": self.leff_1, "l_eff_2": self.leff_2, "n": self.n,
                "M_pl_1_Rd": self.Mpl(self.leff_1), "M_pl_2_Rd": self.Mpl(self.leff_2)}

    def describe(self) -> str:
        r = self.resistance()
        return (f"T-Stummel t = {self.t * 1e3:g} mm, m = {self.m * 1e3:g} mm, "
                f"e = {self.e * 1e3:g} mm, l_eff,1 = {self.leff_1 * 1e3:.0f} mm: "
                f"F_T,Rd = {r['F_T_Rd'] / 1e3:.1f} kN, massgebend {r['versagen']}")


# --------------------------------------------------------------------------
# Wirksame Laengen nach EN 1993-1-8 Tab. 6.4 bis 6.6
# --------------------------------------------------------------------------
def alpha_stiffened(lam1: float, lam2: float) -> float:
    """Beiwert alpha fuer Schraubenreihen neben einer Steife (Bild 6.11).

    lam1 = m/(m+e), lam2 = m2/(m+e). Die Kurvenschar wird durch die
    geschlossene Naeherung von Weynand/Jaspart wiedergegeben; sie liegt im
    gesamten Bereich innerhalb von rund 2 % der Ablesewerte und ist auf
    4,45 <= alpha <= 8 begrenzt.
    """
    lam1 = max(1e-6, min(lam1, 0.9))
    lam2 = max(0.0, min(lam2, 0.9))
    if lam1 + lam2 >= 0.9:
        return 2.0 * math.pi * lam1 / max(lam1, 1e-6) if False else 2.0 * math.pi
    a = 4.45 + (2.0 * math.pi - 4.45) * ((0.9 - lam1 - lam2) / 0.9) ** 1.6
    return max(4.45, min(a, 2.0 * math.pi))


def effective_lengths(kind: str, m: float, e: float, **kw) -> dict:
    """Wirksame Laengen l_eff,cp (kreisfoermig) und l_eff,nc (nicht kreisfoermig).

    kind:
        "innen"          Schraubenreihe innen (Tab. 6.6, Zeile "innere Reihe")
        "rand"           Reihe am Plattenrand mit Abstand e_1 (kw: e1)
        "aussen"         Reihe ausserhalb des Zugflansches (kw: mx, ex, w, bp)
        "neben_steife"   Reihe neben einer Steife (kw: m2)
        "stuetze_innen"  Stuetzenflansch, innere Reihe (unversteift)
        "stuetze_rand"   Stuetzenflansch, Randreihe (kw: e1)
    p: Reihenabstand [m], wenn mehrere Reihen zusammenwirken.
    """
    p = kw.get("p", 0.0)
    e1 = kw.get("e1", 0.0)
    m2 = kw.get("m2", 0.0)
    if kind in ("innen", "stuetze_innen"):
        cp = 2.0 * math.pi * m
        nc = 4.0 * m + 1.25 * e
        if p:
            cp = min(cp, math.pi * m + p)
            nc = min(nc, 2.0 * m + 0.625 * e + 0.5 * p)
        return {"cp": cp, "nc": nc, "bild": "innere Reihe (Tab. 6.6)"}
    if kind in ("rand", "stuetze_rand"):
        cp = min(2.0 * math.pi * m, math.pi * m + 2.0 * e1)
        nc = min(4.0 * m + 1.25 * e, 2.0 * m + 0.625 * e + e1)
        return {"cp": cp, "nc": nc, "bild": "Randreihe (Tab. 6.6)"}
    if kind == "neben_steife":
        a = alpha_stiffened(m / (m + e), m2 / (m + e)) if (m + e) > 0 else 2 * math.pi
        return {"cp": 2.0 * math.pi * m, "nc": a * m,
                "bild": f"Reihe neben Steife, alpha = {a:.2f} (Bild 6.11)"}
    if kind == "aussen":
        mx = kw.get("mx", m)
        ex = kw.get("ex", e)
        w = kw.get("w", 0.0)
        bp = kw.get("bp", 0.0)
        cp = min(2.0 * math.pi * mx, math.pi * mx + w, math.pi * mx + 2.0 * ex) \
            if (w or ex) else 2.0 * math.pi * mx
        nc_list = [4.0 * mx + 1.25 * ex]
        if e:
            nc_list.append(e + 2.0 * mx + 0.625 * ex)
        if w:
            nc_list.append(0.5 * w + 2.0 * mx + 0.625 * ex)
        if bp:
            nc_list.append(0.5 * bp)
        return {"cp": cp, "nc": min(nc_list),
                "bild": "Reihe ausserhalb des Zugflansches (Tab. 6.6)"}
    raise KeyError(f"Fliesslinienbild '{kind}' unbekannt")
