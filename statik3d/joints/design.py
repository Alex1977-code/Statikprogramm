"""
Nachweise fuer Anschluesse nach EN 1993-1-8 und EN 1993-1-9.

Ausgewertet werden die Schnittgroessen, die die Rechnung liefert - Schrauben-
kraefte aus dem Schaft, Klemmkraefte und Reibkraefte aus der Trennfuge,
Nahtspannungen aus dem Nahtbild -, und daraus die Ausnutzungen:

    Schrauben   Abscheren, Lochleibung, Zug, Durchstanzen, Interaktion,
                Gleitfestigkeit (Kategorie B und C), Blockversagen
    Naehte      Richtungsbezogenes und Vereinfachtes Verfahren
    Bleche      Zug im Nettoquerschnitt, T-Stummel der Zugzone
    Ermuedung   Kerbfaelle nach EN 1993-1-9 Tab. 8.1 fuer Schrauben und Naehte,
                Schadensakkumulation nach Palmgren-Miner

    from statik3d.joints.design import check_bolt, check_weld, JointCheck
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .bolts import Bolt, BoltGeometry, block_tearing, beta_Lf, check_spacing
from .welds import Fillet, beta_w
from ..ec3 import fatigue as fat

#: Kerbfaelle EN 1993-1-9 Tab. 8.1 (Schrauben) und 8.5 (Naehte), Delta-sigma_C
DETAILS = {
    "schraube_zug": (50, 3, "Schraube auf Zug, Spannungsquerschnitt, "
                            "Abstützkräfte berücksichtigen (Tab. 8.1, Kerbfall 50)"),
    "schraube_zug_gewalzt": (50, 3, "Schraube mit gewalztem Gewinde, Kerbfall 50"),
    "schraube_abscheren": (100, 5, "Schraube auf Abscheren, Schaftquerschnitt "
                                   "(Tab. 8.1, Kerbfall 100, m = 5)"),
    "passschraube": (100, 5, "Passschraube auf Abscheren, Kerbfall 100"),
    "niet": (100, 5, "Niet auf Abscheren, Kerbfall 100"),
    "lochleibung": (90, 3, "Lochleibung am Blech mit Loch, Kerbfall 90"),
    "blech_loch": (90, 3, "Blech mit Loch, Nettoquerschnitt, Kerbfall 90"),
    "gvp": (112, 3, "Gleitfeste Verbindung, Bruttoquerschnitt, Kerbfall 112"),
    "stumpfnaht_quer": (90, 3, "Stumpfnaht quer, beidseitig geschweißt, "
                               "Nahtüberhöhung abgearbeitet: 112"),
    "stumpfnaht_laengs": (125, 3, "Stumpfnaht längs, Kerbfall 125"),
    "kehlnaht_quer": (80, 3, "Kehlnaht quer (Stirnkehlnaht), Kerbfall 80"),
    "kehlnaht_laengs": (80, 3, "Kehlnaht längs (Flankenkehlnaht), Kerbfall 80"),
    "kehlnaht_schub": (80, 5, "Kehlnaht auf Schub, Delta-tau, Kerbfall 80, m = 5"),
    "steife": (71, 3, "Aufgeschweißte Steife oder Rippe, Kerbfall 71"),
    "kopfplatte": (71, 3, "Kopfplattenanschluss, Naht am Flansch, Kerbfall 71"),
}


@dataclass
class Check:
    """Ein Einzelnachweis."""
    name: str
    E: float                 # Beanspruchung
    R: float                 # Beanspruchbarkeit
    einheit: str = "kN"
    hinweis: str = ""

    @property
    def eta(self) -> float:
        return abs(self.E) / self.R if self.R else float("inf")

    @property
    def ok(self) -> bool:
        return self.eta <= 1.0 + 1e-9

    #: Umrechnung der Anzeigeeinheit
    FAKTOR = {"kN": 1e-3, "kNm": 1e-3, "N/mm^2": 1e-6, "-": 1.0, "": 1.0}

    def line(self) -> str:
        f = self.FAKTOR.get(self.einheit, 1.0)
        return (f"{'OK ' if self.ok else 'NICHT ERFUELLT'} {self.name:44s} "
                f"{self.E * f:9.1f} / {self.R * f:9.1f} {self.einheit}  eta = {self.eta:.3f}"
                + (f"   {self.hinweis}" if self.hinweis else ""))


def check_bolt(bolt: Bolt, Fv_Ed: float = 0.0, Ft_Ed: float = 0.0,
               geo: BoltGeometry = None, t: float = 0.0, fu: float = 490e6,
               tp: float = 0.0, Lj: float = 0.0, sls_slip: float = None) -> list[Check]:
    """Alle Schraubennachweise einer Einzelschraube.

    Fv_Ed: Abscherkraft [N], Ft_Ed: Zugkraft [N]
    geo:   Rand- und Lochabstaende fuer die Lochleibung
    t:     massgebende Blechdicke der Lochleibung [m], fu deren Zugfestigkeit
    tp:    Blechdicke fuer den Durchstanznachweis [m]
    Lj:    Laenge des Anschlusses fuer die Abminderung langer Anschluesse [m]
    sls_slip: Gebrauchslast fuer den Gleitnachweis der Kategorie B [N]
    """
    out: list[Check] = []
    beta = beta_Lf(Lj, bolt.d) if Lj else 1.0
    if Fv_Ed:
        out.append(Check("Abscheren F_v,Rd", Fv_Ed, beta * bolt.Fv_Rd(),
                         hinweis=("" if beta >= 1.0 else
                                  f"langer Anschluss, beta_Lf = {beta:.3f}")))
        if geo is not None and t > 0:
            out.append(Check("Lochleibung F_b,Rd", Fv_Ed, bolt.Fb_Rd(t, fu, geo),
                             hinweis=f"alpha_b = {bolt.alpha_b(geo, fu):.3f}, "
                                     f"k_1 = {bolt.k1(geo):.2f}"))
    if Ft_Ed:
        out.append(Check("Zug F_t,Rd", Ft_Ed, bolt.Ft_Rd()))
        if tp > 0:
            out.append(Check("Durchstanzen B_p,Rd", Ft_Ed, bolt.Bp_Rd(tp, fu)))
    if Fv_Ed and Ft_Ed:
        eta = bolt.interaction(Fv_Ed, Ft_Ed)
        out.append(Check("Interaktion Abscheren und Zug", eta, 1.0, einheit="-",
                         hinweis="F_v,Ed/F_v,Rd + F_t,Ed/(1,4 F_t,Rd)"))
    if bolt.preloaded and Fv_Ed:
        if bolt.category == "C":
            out.append(Check("Gleitfestigkeit F_s,Rd (GZT)", Fv_Ed,
                             bolt.Fs_Rd(Ft_Ed), hinweis="Kategorie C: kein Gleiten im GZT"))
        elif bolt.category == "B":
            F = sls_slip if sls_slip is not None else Fv_Ed
            out.append(Check("Gleitfestigkeit F_s,Rd,ser (GZG)", F,
                             bolt.Fs_Rd(Ft_Ed, sls=True),
                             hinweis="Kategorie B: kein Gleiten im Gebrauchszustand"))
    return out


def check_weld(weld: Fillet, N_perp: float = 0.0, V_perp: float = 0.0,
               V_par: float = 0.0, method: str = "richtung",
               bezeichnung: str = "Kehlnaht") -> list[Check]:
    """Nahtnachweis nach dem Richtungsbezogenen oder Vereinfachten Verfahren.

    bezeichnung: benennt die Naht im Nachweis ("Kehlnaht am Flansch"). Im
    Bericht stehen sonst mehrere gleichnamige Zeilen, die niemand
    auseinanderhalten kann.
    """
    if method == "vereinfacht":
        F = math.sqrt(N_perp ** 2 + V_perp ** 2 + V_par ** 2)
        return [Check(f"{bezeichnung} (Vereinfachtes Verfahren)", F, weld.Fw_Rd(),
                      hinweis=f"f_vw,d = {weld.fvw_d() / 1e6:.0f} N/mm^2, "
                              f"a = {weld.a * 1e3:g} mm, l = {weld.length * 1e3:.0f} mm")]
    r = weld.utilisation_directional(N_perp, V_perp, V_par)
    return [
        Check(f"{bezeichnung}: Vergleichsspannung", r["vergleichsspannung"],
              r["grenzspannung"], einheit="N/mm^2",
              hinweis=f"beta_w = {beta_w(weld.grade):.2f}, a = {weld.a * 1e3:g} mm, "
                      f"l = {weld.length * 1e3:.0f} mm"),
        Check(f"{bezeichnung}: sigma senkrecht", abs(r["sigma_senkrecht"]),
              0.9 * weld.fu / weld.gamma_M2, einheit="N/mm^2"),
    ]


def check_net_section(A_brutto: float, A_netto: float, fy: float, fu: float,
                      N_Ed: float, gamma_M0: float = 1.0, gamma_M2: float = 1.25,
                      category_C: bool = False) -> list[Check]:
    """Zugstab mit Loechern (EN 1993-1-1, 6.2.3).

    N_pl,Rd = A f_y/gamma_M0, N_u,Rd = 0,9 A_net f_u/gamma_M2.
    Bei gleitfesten Verbindungen der Kategorie C gilt zusaetzlich
    N_net,Rd = A_net f_y/gamma_M0.
    """
    out = [Check("Zug Bruttoquerschnitt N_pl,Rd", N_Ed, A_brutto * fy / gamma_M0),
           Check("Zug Nettoquerschnitt N_u,Rd", N_Ed, 0.9 * A_netto * fu / gamma_M2)]
    if category_C:
        out.append(Check("Zug Nettoquerschnitt N_net,Rd (Kat. C)", N_Ed,
                         A_netto * fy / gamma_M0))
    return out


def check_block_tearing(N_Ed: float, Ant: float, Anv: float, fu: float, fy: float,
                        concentric: bool = True) -> Check:
    R = block_tearing(Ant, Anv, fu, fy, concentric)
    return Check("Blockversagen V_eff,Rd", N_Ed, R,
                 hinweis="mittig" if concentric else "aussermittig")


# --------------------------------------------------------------------------
# Ermuedung
# --------------------------------------------------------------------------
def fatigue_check(detail: str, ranges: list, gamma_Mf: float = 1.15,
                  gamma_Ff: float = 1.0, area: float = 0.0) -> dict:
    """Ermuedungsnachweis eines Anschlussteils nach EN 1993-1-9.

    detail: Schluessel aus DETAILS
    ranges: [(Delta-Kraft [N] oder Delta-Spannung [Pa], Lastwechsel n), ...]
            Mit area > 0 werden Kraefte ueber die Flaeche in Spannungen
            umgerechnet (Schraube: A_s, Naht: a*l).
    Rueckgabe: Kerbfall, Schaedigungssumme, zulaessige Lastwechsel je Stufe.
    """
    if detail not in DETAILS:
        raise KeyError(f"Kerbfall '{detail}' unbekannt: {sorted(DETAILS)}")
    dc, m, text = DETAILS[detail]
    stufen = []
    for val, n in ranges:
        ds = (abs(val) / area) if area > 0 else abs(val)
        ds *= gamma_Ff
        stufen.append((ds, float(n)))
    # m = 5 entspricht der Woehlerlinie mit konstanter Steigung 5 (Schub-
    # kerbfall nach EN 1993-1-9, Bild 7.2) - so wird sie im Ermuedungsmodul
    # gefuehrt; m = 3 ist die uebliche Linie mit Knick bei 5e6 und 1e8.
    D = fat.damage(stufen, dc * 1e6, gamma_Mf, shear=(m == 5))
    N = [fat.sn_life(ds, dc * 1e6, gamma_Mf, shear=(m == 5)) for ds, _n in stufen]
    return {"kerbfall": dc, "steigung": m, "beschreibung": text, "N_R": N,
            "gamma_Mf": gamma_Mf, "stufen": stufen, "schaedigung": D,
            "ok": D <= 1.0 + 1e-9}


@dataclass
class JointCheck:
    """Sammlung aller Nachweise eines Anschlusses."""
    name: str = "Anschluss"
    checks: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    ermuedung: list = field(default_factory=list)

    def add(self, items):
        if isinstance(items, Check):
            self.checks.append(items)
        else:
            self.checks.extend(items)
        return self

    @property
    def eta(self) -> float:
        return max((c.eta for c in self.checks), default=0.0)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks) and all(e.get("ok", True) for e in self.ermuedung)

    @property
    def massgebend(self) -> str:
        if not self.checks:
            return ""
        return max(self.checks, key=lambda c: c.eta).name

    def report(self) -> str:
        lines = [f"Nachweise {self.name}", "=" * 78]
        lines += [c.line() for c in self.checks]
        for e in self.ermuedung:
            lines.append(f"{'OK ' if e['ok'] else 'NICHT ERFUELLT'} Ermuedung "
                         f"{e['beschreibung'][:44]:44s} D = {e['schaedigung']:.3f}")
        lines.append("-" * 78)
        lines.append(f"groesste Ausnutzung eta = {self.eta:.3f}"
                     + (f", massgebend: {self.massgebend}" if self.checks else ""))
        for h in self.hinweise:
            lines.append("Hinweis: " + h)
        return "\n".join(lines)
