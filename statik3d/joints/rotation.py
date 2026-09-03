"""
Momenten-Rotations-Verhalten der Anschluesse (DIN EN 1993-1-8, Kap. 5 und 6.3).

Ein Anschluss ist weder starr noch gelenkig, sondern etwas dazwischen. Dieses
Modul beschreibt sein Verhalten mit drei Groessen und traegt sie in die
Berechnung:

**Anfangssteifigkeit S_j,ini** nach dem Komponentenverfahren (6.3.1):

    S_j,ini = E z_eq^2 / SUM_i (1 / k_i)

Jede Komponente bekommt einen Steifigkeitsbeiwert k_i nach Tab. 6.11. Bei
mehreren Schraubenreihen werden sie nach 6.3.3.1 zu einer wirksamen Feder
zusammengefasst::

    k_eff,r = 1 / SUM_i (1 / k_i,r)
    z_eq    = SUM_r k_eff,r h_r^2 / SUM_r k_eff,r h_r
    k_eq    = SUM_r k_eff,r h_r / z_eq

**Momententragfaehigkeit M_j,Rd** nach 6.2.7: Summe der Zugkraefte der
Schraubenreihen mal ihrem Hebelarm zum Druckpunkt, begrenzt durch die
Druckzone; ueberschuessige Zugkraft wird von der untersten Reihe her
abgebaut.

**Rotationskapazitaet** nach 6.4: ein geschraubter Anschluss hat genuegend
Rotationsvermoegen, wenn seine Tragfaehigkeit vom Biegen des Blechs bestimmt
wird **und** das Blech duenn genug ist, damit sich die Fliessgelenke bilden::

    t <= 0,36 d sqrt(f_ub / f_y)                                  (6.4.2(2))

**Klassifizierung** nach 5.2.2.5 (Steifigkeit) und 5.2.3 (Tragfaehigkeit):

    starr        S_j,ini >= k_b E I_b / L_b     (k_b = 8 ausgesteift, 25 sonst)
    gelenkig     S_j,ini <= 0,5 E I_b / L_b
    nachgiebig   dazwischen

**In der Rechnung** wird nach 5.1.2(4) vereinfacht mit S_j = S_j,ini / eta
gerechnet (eta nach Tab. 5.2: 2 fuer geschraubte Stirnplatten). Das ist die
Steifigkeit, die als Drehfeder an das Stabende gelegt wird; sie gilt fuer
jedes M_j,Ed, so dass die Rechnung in einem Durchgang stimmt.

Was fehlt, wird gesagt: ohne Angaben zur Stuetze entfallen die Komponenten
der Stuetzenseite (k_1 bis k_4). S_j,ini ist dann eine **obere Schranke** -
der wirkliche Anschluss ist weicher. Das steht in den Hinweisen jedes
Ergebnisses.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

E_STAHL = 210e9

#: Steifigkeitsverhaeltnis eta nach Tab. 5.2 je Anschlussart
ETA = {"kopfplatte": 2.0, "geschweisst": 2.0, "winkel": 2.0, "fussplatte": 3.0}

#: Beiwert k_b der Steifigkeitsklassifizierung (5.2.2.5)
KB = {"ausgesteift": 8.0, "nicht ausgesteift": 25.0}

#: Klassen
KLASSEN = ("starr", "nachgiebig", "gelenkig")


@dataclass
class Komponente:
    """Eine Grundkomponente mit ihrem Steifigkeitsbeiwert k_i [m]."""
    kennung: str
    k: float
    text: str = ""

    @property
    def unendlich(self) -> bool:
        return not math.isfinite(self.k) or self.k <= 0


@dataclass
class Reihe:
    """Eine Schraubenreihe der Zugzone."""
    h: float                       # Hebelarm zum Druckpunkt [m]
    komponenten: list = field(default_factory=list)
    F_Rd: float = 0.0              # Zugtragfaehigkeit der Reihe [N]
    versagen: str = ""

    @property
    def k_eff(self) -> float:
        """k_eff,r = 1 / SUM (1/k_i) - unendliche Komponenten zaehlen nicht mit."""
        s = sum(1.0 / k.k for k in self.komponenten if not k.unendlich)
        return 1.0 / s if s > 0 else float("inf")


@dataclass
class Gelenkkennwerte:
    """Momenten-Rotations-Verhalten eines Anschlusses."""
    art: str = "kopfplatte"
    S_j_ini: float = 0.0           # Anfangssteifigkeit [Nm/rad]
    eta: float = 2.0
    z_eq: float = 0.0              # Hebelarm der Ersatzfeder [m]
    k_eq: float = 0.0
    M_j_Rd: float = 0.0            # Momententragfaehigkeit [Nm]
    reihen: list = field(default_factory=list)
    komponenten: list = field(default_factory=list)   # (Kennung, k, Text)
    klasse: str = ""               # starr | nachgiebig | gelenkig
    klasse_grund: str = ""
    tragklasse: str = ""           # voll | teil | gelenkig
    grenze_starr: float = 0.0
    grenze_gelenkig: float = 0.0
    rotation_ok: bool = False
    rotation_grund: str = ""
    phi_Cd: float = 0.0            # Verdrehung bei M_j,Rd mit S_j [rad]
    hinweise: list = field(default_factory=list)
    vollstaendig: bool = False     # Stuetzenseite mitgerechnet?

    @property
    def S_j(self) -> float:
        """Steifigkeit fuer die Rechnung, 5.1.2(4): S_j,ini / eta."""
        return self.S_j_ini / self.eta if self.eta else self.S_j_ini

    def beschreibung(self) -> str:
        if self.klasse == "starr":
            return (f"starr (S_j,ini = {self.S_j_ini / 1e6:.1f} MNm/rad "
                    f">= {self.grenze_starr / 1e6:.1f})")
        if self.klasse == "gelenkig":
            return (f"gelenkig (S_j,ini = {self.S_j_ini / 1e6:.1f} MNm/rad "
                    f"<= {self.grenze_gelenkig / 1e6:.1f})")
        return (f"nachgiebig (S_j,ini = {self.S_j_ini / 1e6:.1f} MNm/rad, "
                f"Rechenwert S_j = {self.S_j / 1e6:.1f} MNm/rad)")


# --------------------------------------------------------------------------
# Steifigkeitsbeiwerte nach Tab. 6.11
# --------------------------------------------------------------------------
def k5_stirnplatte(l_eff: float, t_p: float, m: float) -> Komponente:
    """Stirnplatte auf Biegung: k_5 = 0,9 l_eff t_p^3 / m^3."""
    k = 0.9 * l_eff * t_p ** 3 / m ** 3 if m > 0 else float("inf")
    return Komponente("k_5", k, f"Stirnplatte auf Biegung, l_eff = {l_eff * 1e3:.0f} mm, "
                                f"t_p = {t_p * 1e3:.0f} mm, m = {m * 1e3:.0f} mm")


def k10_schrauben(As: float, L_b: float, n_bolts: int = 2) -> Komponente:
    """Schrauben auf Zug: k_10 = 1,6 A_s / L_b (je Reihe mit zwei Schrauben)."""
    k = 1.6 * As / L_b if L_b > 0 else float("inf")
    if n_bolts != 2:
        k *= n_bolts / 2.0
    return Komponente("k_10", k, f"Schrauben auf Zug, A_s = {As * 1e6:.0f} mm², "
                                 f"L_b = {L_b * 1e3:.0f} mm")


def k4_stuetzenflansch(l_eff: float, t_fc: float, m: float) -> Komponente:
    """Stuetzenflansch auf Biegung: k_4 = 0,9 l_eff t_fc^3 / m^3."""
    k = 0.9 * l_eff * t_fc ** 3 / m ** 3 if m > 0 else float("inf")
    return Komponente("k_4", k, f"Stützenflansch auf Biegung, l_eff = {l_eff * 1e3:.0f} mm, "
                                f"t_fc = {t_fc * 1e3:.0f} mm")


def k3_stuetzensteg_zug(b_eff: float, t_wc: float, d_c: float) -> Komponente:
    """Stuetzensteg auf Zug: k_3 = 0,7 b_eff,t,wc t_wc / d_c."""
    k = 0.7 * b_eff * t_wc / d_c if d_c > 0 else float("inf")
    return Komponente("k_3", k, f"Stützensteg auf Zug, b_eff = {b_eff * 1e3:.0f} mm")


def k2_stuetzensteg_druck(b_eff: float, t_wc: float, d_c: float) -> Komponente:
    """Stuetzensteg auf Druck: k_2 = 0,7 b_eff,c,wc t_wc / d_c."""
    k = 0.7 * b_eff * t_wc / d_c if d_c > 0 else float("inf")
    return Komponente("k_2", k, f"Stützensteg auf Druck, b_eff = {b_eff * 1e3:.0f} mm")


def schubflaeche_I(h: float, b: float, tw: float, tf: float, r: float = 0.0,
                   A: float = 0.0, eta: float = 1.2) -> float:
    """Schubflaeche A_v eines gewalzten I-Profils (EN 1993-1-1, 6.2.6(3)).

        A_v = A - 2 b t_f + (t_w + 2 r) t_f   >=  eta h_w t_w

    Ohne bekannte Flaeche A wird sie aus den Abmessungen gebildet.
    """
    if A <= 0:
        A = 2.0 * b * tf + max(h - 2.0 * tf, 0.0) * tw + (4.0 - math.pi) * r ** 2
    av = A - 2.0 * b * tf + (tw + 2.0 * r) * tf
    return max(av, eta * max(h - 2.0 * tf, 0.0) * tw)


def k1_schubfeld(A_vc: float, beta: float, z: float) -> Komponente:
    """Stuetzensteg als Schubfeld: k_1 = 0,38 A_vc / (beta z)."""
    k = 0.38 * A_vc / (beta * z) if beta * z > 0 else float("inf")
    return Komponente("k_1", k, f"Stützensteg als Schubfeld, A_vc = {A_vc * 1e4:.1f} cm², "
                                f"beta = {beta:g}")


# --------------------------------------------------------------------------
# Zusammenfassen mehrerer Reihen (6.3.3.1)
# --------------------------------------------------------------------------
def ersatzfeder(reihen: list) -> tuple:
    """(z_eq, k_eq) der Zugzone aus den wirksamen Federn der Reihen."""
    zaehler = sum(r.k_eff * r.h ** 2 for r in reihen if math.isfinite(r.k_eff))
    nenner = sum(r.k_eff * r.h for r in reihen if math.isfinite(r.k_eff))
    if nenner <= 0:
        return 0.0, float("inf")
    z_eq = zaehler / nenner
    k_eq = nenner / z_eq
    return z_eq, k_eq


def steifigkeit(reihen: list, weitere: list = None, E: float = E_STAHL) -> tuple:
    """S_j,ini aus den Reihen der Zugzone und den Komponenten der Druckzone.

    weitere: Komponenten, die in Reihe zur Ersatzfeder liegen (k_1, k_2).
    Rueckgabe: (S_j,ini, z_eq, k_eq, alle Komponenten).
    """
    if len(reihen) == 1:
        z = reihen[0].h
        k_eq = reihen[0].k_eff
    else:
        z, k_eq = ersatzfeder(reihen)
    if z <= 0:
        return 0.0, 0.0, 0.0, list(weitere or [])
    summe = 0.0 if not math.isfinite(k_eq) else 1.0 / k_eq
    for k in (weitere or []):
        if not k.unendlich:
            summe += 1.0 / k.k
    if summe <= 0:
        return float("inf"), z, k_eq, list(weitere or [])
    return E * z ** 2 / summe, z, k_eq, list(weitere or [])


# --------------------------------------------------------------------------
# Momententragfaehigkeit (6.2.7)
# --------------------------------------------------------------------------
def momententragfaehigkeit(reihen: list, F_c_Rd: float) -> tuple:
    """M_j,Rd aus den Reihenkraeften, begrenzt durch die Druckzone.

    Uebersteigt die Summe der Zugkraefte die Tragfaehigkeit der Druckzone,
    werden die Kraefte von der **untersten** Reihe her abgebaut (6.2.7.2(6)).
    Rueckgabe: (M_j,Rd, [(h, F, versagen), ...]).
    """
    sortiert = sorted(reihen, key=lambda r: -r.h)      # oben zuerst
    uebrig = float(F_c_Rd)
    anteile = []
    for r in sortiert:
        F = min(r.F_Rd, max(uebrig, 0.0))
        uebrig -= F
        anteile.append((r.h, F, r.versagen))
    M = sum(h * F for h, F, _ in anteile)
    return M, anteile


# --------------------------------------------------------------------------
# Klassifizierung (5.2.2.5 und 5.2.3)
# --------------------------------------------------------------------------
def klassifizieren(S_j_ini: float, E: float, I_b: float, L_b: float,
                   rahmen: str = "ausgesteift") -> tuple:
    """(Klasse, Begruendung, Grenze starr, Grenze gelenkig) nach 5.2.2.5."""
    if I_b <= 0 or L_b <= 0:
        return "", "Trägheitsmoment oder Stablänge unbekannt", 0.0, 0.0
    kb = KB.get(rahmen, 8.0)
    grenze_starr = kb * E * I_b / L_b
    grenze_gelenkig = 0.5 * E * I_b / L_b
    if S_j_ini >= grenze_starr:
        return ("starr", f"S_j,ini ≥ {kb:g} E I_b / L_b ({rahmen})",
                grenze_starr, grenze_gelenkig)
    if S_j_ini <= grenze_gelenkig:
        return ("gelenkig", "S_j,ini ≤ 0,5 E I_b / L_b", grenze_starr, grenze_gelenkig)
    return ("nachgiebig", f"zwischen 0,5 und {kb:g} E I_b / L_b",
            grenze_starr, grenze_gelenkig)


def tragfaehigkeitsklasse(M_j_Rd: float, M_pl_Rd: float) -> str:
    """5.2.3: volltragfaehig, teiltragfaehig oder gelenkig."""
    if M_pl_Rd <= 0:
        return ""
    if M_j_Rd >= M_pl_Rd:
        return "volltragfähig"
    if M_j_Rd <= 0.25 * M_pl_Rd:
        return "gelenkig"
    return "teiltragfähig"


# --------------------------------------------------------------------------
# Rotationskapazitaet (6.4)
# --------------------------------------------------------------------------
def rotationskapazitaet(versagen: str, t: float, d: float, fub: float,
                        fy: float) -> tuple:
    """(genügt?, Begruendung) nach 6.4.2(2).

    Ein geschraubter Anschluss hat genuegend Rotationsvermoegen, wenn seine
    Tragfaehigkeit vom **Biegen** des Blechs bestimmt wird und das Blech die
    Dickengrenze einhaelt: t <= 0,36 d sqrt(f_ub / f_y).
    """
    grenze = 0.36 * d * math.sqrt(fub / fy) if fy > 0 else 0.0
    biegt = ("Modus 1" in versagen or "Modus 2" in versagen
             or "Blech" in versagen or "T-Stummel" in versagen)
    if not biegt:
        return (False, f"maßgebend ist „{versagen}“ - das Versagen ist nicht duktil; "
                       "für plastische Berechnung ist das Rotationsvermögen "
                       "nachzuweisen (6.4.2)")
    if t <= grenze + 1e-12:
        return (True, f"Blechbiegen maßgebend und t = {t * 1e3:.1f} mm ≤ "
                      f"0,36 d √(f_ub/f_y) = {grenze * 1e3:.1f} mm (6.4.2(2))")
    return (False, f"Blechbiegen maßgebend, aber t = {t * 1e3:.1f} mm > "
                   f"0,36 d √(f_ub/f_y) = {grenze * 1e3:.1f} mm - das Blech ist zu dick, "
                   "die Fließgelenke bilden sich nicht aus (6.4.2(2))")


def klemmlaenge(t_platte: float, t_gegen: float, bolt) -> float:
    """L_b fuer k_10: Klemmlaenge plus je die Haelfte von Kopf und Mutter.

    Kopf- und Mutterhoehe werden mit 0,7 d beziehungsweise 0,8 d angesetzt
    (uebliche Abmessungen nach EN ISO 4014/4032), Scheiben mit 4 mm.
    """
    return t_platte + t_gegen + 0.004 + 0.5 * (0.7 * bolt.d + 0.8 * bolt.d)
