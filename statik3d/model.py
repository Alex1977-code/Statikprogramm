"""
Datenmodell fuer Statik3D.

Einheiten (konsistent, SI):
    Laenge   m
    Kraft    N
    Spannung Pa (N/m^2)
    Dichte   kg/m^3
    Temperatur K bzw. Kelvin-Differenz

Freiheitsgrade pro Knoten (immer 6, ungenutzte werden automatisch gesperrt):
    0 ux, 1 uy, 2 uz, 3 rx, 4 ry, 5 rz

Aufbau des Modells
------------------
* Knoten, Elemente, Materialien, Querschnitte, Schalendicken   (Geometrie)
* Lager (starr, Feder, vorgegebene Verschiebung)
* Lastfaelle (LoadCase) mit Einwirkungskategorie (G, Q, W, S, T, A, ...)
  - jeder Lastfall traegt eigene Knoten-, Stab-, Flaechen-, Temperaturlasten
    und ein eigenes Eigengewicht
* Kombinationen (Combination): Lastfall -> Faktor, Typ (GZT, GZG, ...)
* Ermuedungslasten (FatigueLoad): Lastwechsel zwischen zwei Lastfaellen
* Staebe (Member): Ketten von Stabelementen fuer Nachweise nach EC3
  (Knicklaengen, Biegedrillknicken, Kerbfall)
* Kontakt: einseitige Lager, Knoten-Knoten-Spaltelemente,
  Knoten-Flaeche-Kontaktpaare (Penalty, Reibung)

Kompatibilitaet: Die alte Ein-Lastfall-API (model.load_node, model.nodal_loads,
model.gravity ...) arbeitet auf dem *aktiven* Lastfall weiter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from typing import Optional

import numpy as np

DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]
DOF_ALIASES = {"ux": 0, "uy": 1, "uz": 2, "rx": 3, "ry": 4, "rz": 5,
               "phix": 3, "phiy": 4, "phiz": 5, "mx": 3, "my": 4, "mz": 5,
               "d0": 0, "d1": 1, "d2": 2, "d3": 3, "d4": 4, "d5": 5,
               "x": 0, "y": 1, "z": 2}


def dof_index(key) -> int:
    """FHG-Index 0..5 aus Name ('uz', 'phiy', 'd2') oder Zahl."""
    if isinstance(key, (int, np.integer)):
        i = int(key)
    else:
        k = str(key).strip().lower().replace("_", "").replace("-", "")
        if k not in DOF_ALIASES:
            raise KeyError(f"Freiheitsgrad '{key}' unbekannt ({sorted(set(DOF_ALIASES))})")
        i = DOF_ALIASES[k]
    if not 0 <= i <= 5:
        raise KeyError(f"Freiheitsgrad {key} liegt nicht zwischen 0 und 5")
    return i
NDOF = 6
FORMAT_VERSION = 6

# Einwirkungskategorien (DIN EN 1990/NA Tabelle A.1.1) -> (psi0, psi1, psi2)
ACTION_CATEGORIES = {
    "G":    ("Staendige Einwirkung", (1.0, 1.0, 1.0)),
    "P":    ("Vorspannung", (1.0, 1.0, 1.0)),
    "Q_A":  ("Nutzlast Kat. A Wohn-/Aufenthaltsraeume", (0.7, 0.5, 0.3)),
    "Q_B":  ("Nutzlast Kat. B Bueros", (0.7, 0.5, 0.3)),
    "Q_C":  ("Nutzlast Kat. C Versammlungsraeume", (0.7, 0.7, 0.6)),
    "Q_D":  ("Nutzlast Kat. D Verkaufsraeume", (0.7, 0.7, 0.6)),
    "Q_E":  ("Nutzlast Kat. E Lagerraeume", (1.0, 0.9, 0.8)),
    "Q_F":  ("Verkehrslast Kat. F Fahrzeuge <= 30 kN", (0.7, 0.7, 0.6)),
    "Q_G":  ("Verkehrslast Kat. G Fahrzeuge 30-160 kN", (0.7, 0.5, 0.3)),
    "Q_H":  ("Nutzlast Kat. H Daecher", (0.0, 0.0, 0.0)),
    "Q_K":  ("Kranlasten (DIN EN 1991-3)", (1.0, 0.9, 0.8)),
    "Q":    ("Veraenderliche Einwirkung, allgemein", (0.8, 0.7, 0.5)),
    "S":    ("Schnee (Orte bis NN + 1000 m)", (0.5, 0.2, 0.0)),
    "S_H":  ("Schnee (Orte ueber NN + 1000 m)", (0.7, 0.5, 0.2)),
    "W":    ("Wind", (0.6, 0.2, 0.0)),
    "T":    ("Temperatur (nicht Brand)", (0.6, 0.5, 0.0)),
    "H":    ("Wasserdruck / hydrostatisch (DIN 19704)", (1.0, 1.0, 1.0)),
    "SET":  ("Baugrundsetzungen", (1.0, 1.0, 1.0)),
    "A":    ("Aussergewoehnliche Einwirkung", (1.0, 1.0, 1.0)),
    "FAT":  ("Ermuedungslast (nur fuer Ermuedungsnachweis)", (0.0, 0.0, 0.0)),
    # --- Stahlwasserbau und bewegliche Bruecken (DIN 19704, ZTV-ING) ---
    # Die psi-Werte sind Voreinstellungen und gegen die geltende Fassung zu
    # bestaetigen; siehe statik3d.bridges.din19704.Regelwerk.
    "G_A":    ("Eigengewicht Ausruestung und Antrieb (DIN 19704)", (1.0, 1.0, 1.0)),
    "W_S":    ("Wasserdruck staendig, Stauziel (DIN 19704)", (1.0, 1.0, 1.0)),
    "W_V":    ("Wasserdruck veraenderlich, Betriebswasserstaende (DIN 19704)", (0.8, 0.7, 0.5)),
    "Q_BEW":  ("Betriebslast beim Bewegen (DIN 19704)", (0.8, 0.7, 0.5)),
    "A_M":    ("Antriebsmoment, planmaessig (DIN 19704)", (1.0, 0.9, 0.8)),
    "A_MG":   ("Antriebsmoment, Grenzmoment der Rutschkupplung (DIN 19704)", (1.0, 0.9, 0.8)),
    "WIND_B": ("Wind waehrend der Bewegung (ZTV-ING)", (0.6, 0.2, 0.0)),
    "EIS":    ("Eisdruck, Eislast (DIN 19704)", (0.6, 0.5, 0.0)),
    "SCHWALL": ("Schwall und Sunk, Wellendruck (DIN 19704)", (0.6, 0.5, 0.0)),
    "ANPRALL": ("Anprall durch Schiff oder Treibgut", (1.0, 1.0, 1.0)),
    "KLEMM":  ("Verklemmen eines Antriebsstrangs (ZTV-ING)", (1.0, 1.0, 1.0)),
    "MONT":   ("Montage- und Revisionszustand", (1.0, 1.0, 1.0)),
    "ERD":    ("Erdbeben (DIN EN 1998)", (1.0, 1.0, 1.0)),
}


# --------------------------------------------------------------------------
# Material / Querschnitt
# --------------------------------------------------------------------------
STEEL_GRADES = {
    # Name: (fy [Pa] t<=40mm, fu [Pa] t<=40mm, fy 40<t<=80, fu 40<t<=80)  EN 10025-2
    "S235": (235e6, 360e6, 215e6, 360e6),
    "S275": (275e6, 430e6, 255e6, 410e6),
    "S355": (355e6, 490e6, 335e6, 470e6),
    "S420": (420e6, 520e6, 390e6, 520e6),
    "S460": (460e6, 540e6, 430e6, 540e6),
}


@dataclass
class Material:
    name: str
    E: float = 210e9          # Elastizitaetsmodul [Pa]
    nu: float = 0.3           # Querdehnzahl [-]
    rho: float = 7850.0       # Dichte [kg/m^3]
    alpha: float = 1.2e-5     # Waermeausdehnung [1/K]
    fy: Optional[float] = None  # Streckgrenze [Pa]
    fu: Optional[float] = None  # Zugfestigkeit [Pa]
    grade: str = ""           # Stahlsorte (S235, S355, ...) fuer Nachweise

    @property
    def G(self) -> float:
        return self.E / (2.0 * (1.0 + self.nu))

    @staticmethod
    def steel(grade: str = "S355", name: str = None) -> "Material":
        """Baustahl nach EN 10025-2 (t <= 40 mm)."""
        g = grade.upper().replace(" ", "")
        if g not in STEEL_GRADES:
            raise KeyError(f"Stahlsorte '{grade}' unbekannt: {list(STEEL_GRADES)}")
        fy, fu, _, _ = STEEL_GRADES[g]
        return Material(name or g, 210e9, 0.3, 7850.0, 1.2e-5, fy, fu, g)

    def yield_strength(self, t: float = 0.0) -> float:
        """Streckgrenze in Abhaengigkeit der Erzeugnisdicke t [m] (EN 1993-1-1 Tab. 3.1)."""
        if self.grade in STEEL_GRADES and t > 0.040:
            return STEEL_GRADES[self.grade][2]
        return self.fy or 0.0

    def ultimate_strength(self, t: float = 0.0) -> float:
        if self.grade in STEEL_GRADES and t > 0.040:
            return STEEL_GRADES[self.grade][3]
        return self.fu or (1.3 * self.fy if self.fy else 0.0)


@dataclass
class Section:
    """Stabquerschnitt. Lokale Achsen: x = Stabachse, y/z = Hauptachsen.
    y = starke Achse (Iy), Steg liegt in lokaler z-Richtung (I-Profile).

    Geometriefelder (h, b, tw, tf, r) werden fuer die Querschnittsklassifizierung
    und die Nachweise nach EC3 benoetigt. Bei typ='free' sind nur die
    Steifigkeitswerte bekannt; Nachweise erfolgen dann elastisch.
    """
    name: str
    A: float = 1e-2           # Flaeche [m^2]
    Iy: float = 1e-5          # Traegheitsmoment um lokale y (Biegung in x-z) [m^4]
    Iz: float = 1e-5          # Traegheitsmoment um lokale z (Biegung in x-y) [m^4]
    It: float = 1e-5          # Torsionstraegheitsmoment [m^4]
    Asy: float = 0.0          # Schubflaeche in y (0 = Schubstarr / Bernoulli)
    Asz: float = 0.0          # Schubflaeche in z
    # Randabstaende fuer Spannungsnachweis [m]
    zmax: float = 0.0
    ymax: float = 0.0
    # ---- Geometrie / Bemessung ----
    typ: str = "free"         # I, RHS, CHS, rect, circle, free
    h: float = 0.0            # Hoehe (CHS: Aussendurchmesser) [m]
    b: float = 0.0            # Breite [m]
    tw: float = 0.0           # Stegdicke (RHS/CHS: Wanddicke) [m]
    tf: float = 0.0           # Flanschdicke [m]
    r: float = 0.0            # Ausrundungsradius (RHS: innerer Eckradius) [m]
    Iw: float = 0.0           # Woelbwiderstand [m^6]
    Wel_y: float = 0.0        # elastische Widerstandsmomente [m^3]
    Wel_z: float = 0.0
    Wpl_y: float = 0.0        # plastische Widerstandsmomente [m^3]
    Wpl_z: float = 0.0
    fabrication: str = "rolled"   # rolled | welded | cold_formed
    # Unsymmetrische Profile (U, L) und zusammengesetzte Querschnitte
    yc: float = 0.0               # Schwerpunktlage in y ab Bezugskante [m]
    zc: float = 0.0               # Schwerpunktlage in z ab Bezugskante [m]
    alpha: float = 0.0            # Drehung der Hauptachsen gegen die Schenkel [rad]
    Iy_geo: float = 0.0           # Traegheitsmomente in Schenkel-/Bezugsrichtung
    Iz_geo: float = 0.0
    Iyz_geo: float = 0.0
    parts: list = field(default_factory=list)   # zusammengesetzt: Teilquerschnitte

    def __post_init__(self):
        if self.Wel_y <= 0 and self.zmax > 0:
            self.Wel_y = self.Iy / self.zmax
        if self.Wel_z <= 0 and self.ymax > 0:
            self.Wel_z = self.Iz / self.ymax
        if self.Wpl_y <= 0 and self.Wel_y > 0:
            self.Wpl_y = self.Wel_y          # konservativ (elastisch)
        if self.Wpl_z <= 0 and self.Wel_z > 0:
            self.Wpl_z = self.Wel_z

    # ---- Standardformen -------------------------------------------------
    @staticmethod
    def rectangle(name: str, b: float, h: float) -> "Section":
        a = min(b, h)
        c = max(b, h)
        beta = 1.0 / 3.0 - 0.21 * (a / c) * (1 - (a / c) ** 4 / 12.0)
        return Section(
            name=name, A=b * h,
            Iy=b * h ** 3 / 12.0, Iz=h * b ** 3 / 12.0,
            It=beta * c * a ** 3,
            Asy=5.0 / 6.0 * b * h, Asz=5.0 / 6.0 * b * h,
            zmax=h / 2.0, ymax=b / 2.0,
            typ="rect", h=h, b=b,
            Wpl_y=b * h ** 2 / 4.0, Wpl_z=h * b ** 2 / 4.0,
        )

    @staticmethod
    def circle(name: str, d: float) -> "Section":
        A = np.pi * d ** 2 / 4.0
        I = np.pi * d ** 4 / 64.0
        return Section(name, A=A, Iy=I, Iz=I, It=2 * I,
                       Asy=0.9 * A, Asz=0.9 * A, zmax=d / 2, ymax=d / 2,
                       typ="circle", h=d, b=d,
                       Wpl_y=d ** 3 / 6.0, Wpl_z=d ** 3 / 6.0)

    @staticmethod
    def pipe(name: str, d: float, t: float, fabrication: str = "rolled") -> "Section":
        """Kreishohlprofil (CHS) mit Aussendurchmesser d und Wanddicke t."""
        di = d - 2 * t
        A = np.pi * (d ** 2 - di ** 2) / 4.0
        I = np.pi * (d ** 4 - di ** 4) / 64.0
        return Section(name, A=A, Iy=I, Iz=I, It=2 * I,
                       Asy=2 * A / np.pi, Asz=2 * A / np.pi, zmax=d / 2, ymax=d / 2,
                       typ="CHS", h=d, b=d, tw=t, tf=t,
                       Wpl_y=(d ** 3 - di ** 3) / 6.0, Wpl_z=(d ** 3 - di ** 3) / 6.0,
                       fabrication=fabrication)

    chs = pipe

    @staticmethod
    def i_profile(name: str, h: float, b: float, tw: float, tf: float,
                  r: float = 0.0, fabrication: str = "rolled") -> "Section":
        """Doppel-T (I/H) mit Gesamthoehe h, Flanschbreite b, Ausrundung r.
        Formeln fuer gewalzte Profile mit Ausrundungen (Herstellerkataloge)."""
        hw = h - 2 * tf
        A = 2 * b * tf + hw * tw + (4 - np.pi) * r ** 2
        Iy = ((b * h ** 3 - (b - tw) * hw ** 3) / 12.0
              + 0.03 * r ** 4 + 0.2146 * r ** 2 * (hw - 0.4468 * r) ** 2)
        Iz = ((2 * tf * b ** 3 + hw * tw ** 3) / 12.0
              + 0.03 * r ** 4 + 0.2146 * r ** 2 * (tw + 0.4468 * r) ** 2)
        It = (2 * b * tf ** 3 + hw * tw ** 3) / 3.0
        if r > 0:
            D = ((tf + r) ** 2 + tw * (r + tw / 4.0)) / (2 * r + tf)
            al = (-0.042 + 0.2204 * tw / tf + 0.1355 * r / tf
                  - 0.0865 * tw * r / tf ** 2 - 0.0725 * tw ** 2 / tf ** 2)
            It += 2 * al * D ** 4 - 0.42 * tf ** 4
        Iw = tf * b ** 3 * (h - tf) ** 2 / 24.0
        Wpl_y = (tw * h ** 2 / 4.0 + (b - tw) * (h - tf) * tf
                 + (4 - np.pi) / 2.0 * r ** 2 * hw + (3 * np.pi - 10) / 3.0 * r ** 3)
        Wpl_z = (tf * b ** 2 / 2.0 + hw * tw ** 2 / 4.0
                 + (4 - np.pi) / 2.0 * r ** 2 * tw + (10 - 3 * np.pi) / 3.0 * r ** 3)
        Avz = A - 2 * b * tf + (tw + 2 * r) * tf          # EN 1993-1-1 6.2.6(3)
        Avy = A - hw * tw
        return Section(name, A=A, Iy=Iy, Iz=Iz, It=It,
                       Asy=Avy, Asz=max(Avz, hw * tw),
                       zmax=h / 2, ymax=b / 2,
                       typ="I", h=h, b=b, tw=tw, tf=tf, r=r, Iw=Iw,
                       Wpl_y=Wpl_y, Wpl_z=Wpl_z, fabrication=fabrication)

    @staticmethod
    def channel(name: str, h: float, b: float, tw: float, tf: float,
                r: float = 0.0, taper: float = 0.0,
                fabrication: str = "rolled") -> "Section":
        """U-Profil (Rinne). h Gesamthoehe, b Flanschbreite, tw Stegdicke,
        tf Flanschdicke (bei geneigten Flanschen in Flanschmitte gemessen),
        taper = Neigung der Flanschinnenseite (UPN: 0.08, UPE: 0).
        Die lokale y-Achse ist die starke Achse (Biegung in x-z), z liegt in der
        Stegebene. yc ist der Schwerpunktabstand von der Stegaussenkante,
        ymax der groessere Randabstand."""
        hw = h - 2 * tf
        A_w = h * tw
        A_f = 2 * (b - tw) * tf
        Ar = (1 - np.pi / 4) * r ** 2                 # Ausrundung je Steg-/Flanschecke
        yr = tw + 0.2234 * r
        A = A_w + A_f + 2 * Ar
        # Flansche als Streifen: erfasst auch geneigte Innenseiten (UPN)
        n = 400
        x = np.linspace(tw, b, n + 1)
        xm = 0.5 * (x[1:] + x[:-1])
        dx = (b - tw) / n
        t_str = tf + taper * ((tw + b) / 2 - xm)      # Dicke an der Stelle xm
        zm = (h - t_str) / 2                          # Schwerpunktlage des Streifens
        A_str = t_str * dx
        S_f = 2 * float(np.sum(A_str * xm))
        ey = (A_w * tw / 2 + S_f + 2 * Ar * yr) / A
        Iy = (tw * hw ** 3 / 12.0                      # Steg
              + 2 * float(np.sum(A_str * (t_str ** 2 / 12.0 + zm ** 2)))
              + 2 * Ar * (hw / 2 - 0.2234 * r) ** 2)
        Iy += tw * (h ** 3 - hw ** 3) / 12.0           # Steg ueber die volle Hoehe
        Iz = (tw ** 3 * h / 12.0 + A_w * (tw / 2 - ey) ** 2
              + 2 * float(np.sum(A_str * (dx ** 2 / 12.0 + (xm - ey) ** 2)))
              + 2 * Ar * (yr - ey) ** 2)
        It = (h * tw ** 3 + 2 * b * tf ** 3) / 3.0
        hm = h - tf                      # Abstand der Flanschmitten
        Iw = (tf * b ** 3 * hm ** 2 / 12.0
              * (3 * tf * b + 2 * hm * tw) / (6 * tf * b + hm * tw))
        ymax = max(ey, b - ey)
        Wpl_y = tw * h ** 2 / 4.0 + (b - tw) * tf * (h - tf)
        Wpl_z = (A / 2.0) * 0.35 * b     # Naeherung (unsymmetrisch)
        return Section(name, A=A, Iy=Iy, Iz=Iz, It=It,
                       Asy=A_f, Asz=hw * tw, zmax=h / 2, ymax=ymax,
                       typ="U", h=h, b=b, tw=tw, tf=tf, r=r, Iw=Iw,
                       Wel_y=Iy / (h / 2), Wel_z=Iz / ymax,
                       Wpl_y=Wpl_y, Wpl_z=Wpl_z, fabrication=fabrication, yc=ey)

    @staticmethod
    def angle(name: str, h: float, b: float, t: float, r: float = 0.0,
              fabrication: str = "rolled") -> "Section":
        """Winkelprofil L (gleich- oder ungleichschenklig). h langer Schenkel,
        b kurzer Schenkel, t Dicke.

        Winkel haben geneigte Hauptachsen. Iy/Iz sind die **Hauptträgheitsmomente**
        (Iy = groesseres), 'alpha' ist der Winkel der Hauptachsen gegen die
        Schenkel [rad]: der Stab muss mit roll = alpha eingebaut werden, damit
        die lokalen Achsen den Hauptachsen entsprechen. Iy_geo/Iz_geo/Iyz_geo
        sind die Werte in Schenkelrichtung (Katalogwerte)."""
        A1, A2 = h * t, (b - t) * t          # senkrechter und waagerechter Schenkel
        A = A1 + A2 + (1 - np.pi / 4) * r ** 2
        z1, y1 = h / 2, t / 2
        z2, y2 = t / 2, t + (b - t) / 2
        zc = (A1 * z1 + A2 * z2) / (A1 + A2)
        yc = (A1 * y1 + A2 * y2) / (A1 + A2)
        Iy_g = (t * h ** 3 / 12.0 + A1 * (z1 - zc) ** 2
                + (b - t) * t ** 3 / 12.0 + A2 * (z2 - zc) ** 2)
        Iz_g = (h * t ** 3 / 12.0 + A1 * (y1 - yc) ** 2
                + t * (b - t) ** 3 / 12.0 + A2 * (y2 - yc) ** 2)
        Iyz = A1 * (y1 - yc) * (z1 - zc) + A2 * (y2 - yc) * (z2 - zc)
        m = (Iy_g + Iz_g) / 2.0
        d = np.hypot((Iy_g - Iz_g) / 2.0, Iyz)
        I1, I2 = m + d, m - d
        alpha = 0.5 * np.arctan2(2 * Iyz, Iy_g - Iz_g) if abs(Iyz) > 1e-18 else 0.0
        It = (h + b - t) * t ** 3 / 3.0
        Iw = (h + b) * t ** 5 / 36.0        # Woelbwiderstand sehr klein
        zmax = max(zc, h - zc)
        ymax = max(yc, b - yc)
        return Section(name, A=A, Iy=I1, Iz=I2, It=It,
                       Asy=b * t, Asz=h * t, zmax=zmax, ymax=ymax,
                       typ="L", h=h, b=b, tw=t, tf=t, r=r, Iw=Iw,
                       Wel_y=I1 / zmax, Wel_z=I2 / ymax,
                       Wpl_y=t * (h ** 2 + b ** 2 - t ** 2) / 4.0,
                       Wpl_z=t * (h ** 2 + b ** 2 - t ** 2) / 4.0,
                       fabrication=fabrication, yc=yc, zc=zc, alpha=float(alpha),
                       Iy_geo=Iy_g, Iz_geo=Iz_g, Iyz_geo=Iyz)

    @staticmethod
    def rhs(name: str, h: float, b: float, t: float, r_out: float = None,
            r_in: float = None, fabrication: str = "rolled") -> "Section":
        """Rechteck-/Quadrathohlprofil. Warmgefertigt (EN 10210): r_out=1.5t, r_in=1.0t."""
        ro = 1.5 * t if r_out is None else r_out
        ri = 1.0 * t if r_in is None else r_in
        hi, bi = h - 2 * t, b - 2 * t

        def rrect(bb, hh, rr):
            # Flaeche, Ix, Iy und halbe statische Momente eines abgerundeten Rechtecks
            Af = 0.2146 * rr ** 2
            cf = 0.2234 * rr
            A_ = bb * hh - 4 * Af
            Ix = bb * hh ** 3 / 12 - 4 * Af * (hh / 2 - cf) ** 2 - 0.03 * rr ** 4
            Iy_ = hh * bb ** 3 / 12 - 4 * Af * (bb / 2 - cf) ** 2 - 0.03 * rr ** 4
            Qx = bb * hh ** 2 / 8 - 2 * Af * (hh / 2 - cf)
            Qy = hh * bb ** 2 / 8 - 2 * Af * (bb / 2 - cf)
            return A_, Ix, Iy_, Qx, Qy

        Ao, Iyo, Izo, Qyo, Qzo = rrect(b, h, ro)
        Ai, Iyi, Izi, Qyi, Qzi = rrect(bi, hi, ri)
        A = Ao - Ai
        Iy = Iyo - Iyi
        Iz = Izo - Izi
        Wpl_y = 2 * (Qyo - Qyi)
        Wpl_z = 2 * (Qzo - Qzi)
        Rc = (ro + ri) / 2.0
        hm, bm = h - t, b - t
        Ap = hm * bm - Rc ** 2 * (4 - np.pi)
        p = 2 * (hm + bm) - 2 * Rc * (4 - np.pi)
        It = t ** 3 * p / 3.0 + 4 * Ap ** 2 * t / p        # EN 10210-2 Anhang
        return Section(name, A=A, Iy=Iy, Iz=Iz, It=It,
                       Asy=A * b / (b + h), Asz=A * h / (b + h),
                       zmax=h / 2, ymax=b / 2,
                       typ="RHS", h=h, b=b, tw=t, tf=t, r=ri,
                       Wpl_y=Wpl_y, Wpl_z=Wpl_z, fabrication=fabrication)

    @staticmethod
    def from_profile(designation: str, name: str = None) -> "Section":
        """Profil aus der Datenbank (z.B. 'HEA 200', 'IPE 300', 'SHS 100x5')."""
        from .profiles import make_section
        return make_section(designation, name)

    # ---- Hilfen -----------------------------------------------------------
    @property
    def hw(self) -> float:
        """Steghoehe zwischen den Flanschen."""
        return self.h - 2 * self.tf if self.typ == "I" else self.h - 2 * self.tw

    @property
    def t_max(self) -> float:
        return max(self.tf, self.tw)

    def describe(self) -> str:
        if self.typ == "I":
            return (f"I-Profil h={self.h*1e3:.0f} b={self.b*1e3:.0f} "
                    f"tw={self.tw*1e3:.1f} tf={self.tf*1e3:.1f} mm")
        if self.typ == "RHS":
            return f"Hohlprofil {self.h*1e3:.0f}x{self.b*1e3:.0f}x{self.tw*1e3:.1f} mm"
        if self.typ == "CHS":
            return f"Rohr {self.h*1e3:.1f}x{self.tw*1e3:.1f} mm"
        if self.typ == "rect":
            return f"Rechteck {self.b*1e3:.0f}x{self.h*1e3:.0f} mm"
        if self.typ == "circle":
            return f"Kreis d={self.h*1e3:.0f} mm"
        return f"A={self.A:.4g} m² Iy={self.Iy:.4g} m⁴"


@dataclass
class ShellProp:
    """Eigenschaften eines Flaechenelements."""
    name: str
    t: float = 0.01           # Dicke [m]


# --------------------------------------------------------------------------
# Elemente
# --------------------------------------------------------------------------
@dataclass
class Element:
    """
    typ:  'beam'   2 Knoten,  Balken/Stab 3D (12 FHG)
          'truss'  2 Knoten,  Fachwerkstab (nur Normalkraft)
          'shell3' 3 Knoten,  ebenes Schalenelement (CST + DKT)
          'shell4' 4 Knoten,  in 2 shell3 zerlegt
          'tet4'   4 Knoten,  linearer Tetraeder
          'tet10' 10 Knoten,  quadratischer Tetraeder
          'hex8'   8 Knoten,  Trilinearer Hexaeder
    """
    typ: str
    nodes: list[int]
    mat: str
    sec: Optional[str] = None       # Section-Name (beam/truss) oder ShellProp (shell)
    roll: float = 0.0               # Verdrehung der lokalen Achsen [rad], nur Stab
    group: str = "default"
    hinges: list[int] = field(default_factory=list)  # Momentengelenke: lokale FHG 3..5 / 9..11
    hinge_springs: list = field(default_factory=list)  # [(lokaler FHG 0..11, Steifigkeit)]
    line: str = ""                  # zugehoerige Linie (RFEM-Import)


FAILURE_MODES = {
    "": "immer wirksam",
    "zug": "faellt bei Zug aus (nimmt nur Druck)",
    "druck": "faellt bei Druck aus (nimmt nur Zug)",
}


@dataclass
class DofBehaviour:
    """Wirkung eines einzelnen Lager-Freiheitsgrads (Nichtlinearitaet wie in RFEM).

    Vorzeichen: Das Lager wirkt entlang der positiven Achse seines FHG. Mit der
    Knotenverschiebung u in diesem FHG ist die Lagerkraft auf den Knoten
    F = -k*u. Bewegt sich der Knoten in das Lager hinein (u < 0), ist F > 0:
    das Lager **drueckt** (Druck im Lager). Zieht der Knoten am Lager (u > 0),
    ist F < 0: **Zug** im Lager.

    typ:        'rigid' (starr) | 'spring' (Feder) | 'free' (frei)
    stiffness:  Federsteifigkeit; Knotenlager [N/m] bzw. [Nm/rad],
                Linienlager [N/m je m], Flaechenlager [N/m je m^2] (Bettung)
    failure:    '' | 'zug' (Ausfall bei Zug) | 'druck' (Ausfall bei Druck)
    slip:       Schlupf [m] bzw. [rad]: freier Weg, bevor das Lager wirkt
    mu:         Reibbeiwert; die Kraft in diesem FHG ist auf mu * |F| des
                Bezugs-FHG begrenzt (nur Verschiebungs-FHG)
    mu_ref:     FHG-Index der Bezugskraft (meist 2 = uz); None = automatisch
                der FHG mit Ausfall in derselben Lagerdefinition
    limit:      Grenzkraft [N] bzw. [Nm]; 0 = unbegrenzt (plastisches Fliessen)
    """
    typ: str = "rigid"
    stiffness: float = 0.0
    failure: str = ""
    slip: float = 0.0
    mu: float = 0.0
    mu_ref: Optional[int] = None
    limit: float = 0.0

    def __post_init__(self):
        if self.typ not in ("rigid", "spring", "free"):
            raise ValueError(f"Lagerart '{self.typ}' unbekannt (rigid | spring | free)")
        if self.failure not in FAILURE_MODES:
            raise ValueError(f"Ausfallart '{self.failure}' unbekannt ({list(FAILURE_MODES)})")

    @property
    def nonlinear(self) -> bool:
        return bool(self.failure) or self.mu > 0 or self.slip > 0 or self.limit > 0

    @property
    def acts(self) -> bool:
        return self.typ != "free"

    def describe(self) -> str:
        if self.typ == "free":
            return "frei"
        t = "starr" if self.typ == "rigid" else f"Feder {self.stiffness:g}"
        if self.failure:
            t += f", Ausfall bei {self.failure.capitalize()}"
        if self.slip:
            t += f", Schlupf {self.slip * 1000:g} mm"
        if self.mu:
            t += f", Reibung mu = {self.mu:g}"
        if self.limit:
            t += f", Grenzkraft {self.limit / 1e3:g} kN"
        return t


@dataclass
class Support:
    node: int
    dofs: list[int]                 # gesperrte FHG-Indizes 0..5
    values: Optional[list[float]] = None   # vorgegebene Verschiebungen (default 0)
    stiffness: Optional[list[float]] = None  # optional Federsteifigkeiten statt starr
    # Nichtlinearitaet je FHG: {FHG-Index: DofBehaviour}; nicht genannte FHG
    # verhalten sich wie bisher (starr bzw. Feder aus 'stiffness')
    behaviour: dict = field(default_factory=dict)
    name: str = ""
    #: Groesse des Lagersymbols in der Ansicht, 1.0 = Grundgroesse. Reine
    #: Darstellung, ohne Einfluss auf die Rechnung - sie wird mitgespeichert,
    #: damit ein eingestelltes Symbol beim naechsten Oeffnen wieder stimmt.
    groesse: float = 1.0

    def dof_behaviour(self, dof: int) -> DofBehaviour:
        """Wirkung eines FHG; setzt 'dofs'/'stiffness' in DofBehaviour um."""
        b = self.behaviour.get(dof) or self.behaviour.get(str(dof))
        if b is not None:
            return b if isinstance(b, DofBehaviour) else _dc(DofBehaviour, b)
        if dof not in self.dofs:
            return DofBehaviour("free")
        if self.stiffness:
            k = self.stiffness[self.dofs.index(dof)]
            if k:
                return DofBehaviour("spring", float(k))
        return DofBehaviour("rigid")

    def set_behaviour(self, dof: int, **kw) -> DofBehaviour:
        b = DofBehaviour(**kw)
        self.behaviour[int(dof)] = b
        if int(dof) not in self.dofs and b.acts:
            self.dofs.append(int(dof))
        return b

    @property
    def nonlinear(self) -> bool:
        return any(self.dof_behaviour(d).nonlinear for d in range(NDOF))


@dataclass
class LineSupport:
    """Lager entlang eines Linienzugs (RFEM: Linienlager).

    nodes: Knoten des Linienzugs in Reihenfolge (oder line = Name einer Linie).
    Die Steifigkeiten in 'behaviour' sind auf die Laenge bezogen
    ([N/m je m] bzw. [Nm/rad je m]) und werden ueber die Einflusslaenge des
    Knotens (halbe Nachbarabschnitte) auf Knotenfedern umgerechnet.
    Ausfall, Schlupf und Reibung gelten je Knoten.
    """
    name: str = ""
    nodes: list[int] = field(default_factory=list)
    line: str = ""
    behaviour: dict = field(default_factory=dict)     # {FHG: DofBehaviour}
    axis: str = "global"                              # global (weitere Systeme spaeter)

    def dof_behaviour(self, dof: int) -> DofBehaviour:
        b = self.behaviour.get(dof) or self.behaviour.get(str(dof))
        if b is None:
            return DofBehaviour("free")
        return b if isinstance(b, DofBehaviour) else _dc(DofBehaviour, b)


@dataclass
class SurfaceSupport:
    """Flaechenlager / Bettung (RFEM: Flaechenlager).

    elements: Schalen- oder Volumenelemente, deren Flaeche gebettet ist;
    bei Volumen wird die angegebene Flaechennummer 'face' verwendet
    (face = -1: alle Aussenflaechen). Die Steifigkeiten in 'behaviour' sind auf
    die Flaeche bezogen ([N/m je m^2] = Bettungsmodul [N/m^3]) und werden ueber
    die Einflussflaeche der Knoten verteilt.
    """
    name: str = ""
    elements: list[int] = field(default_factory=list)
    nodes: list[int] = field(default_factory=list)    # alternativ direkt Knoten + Flaechen
    areas: list[float] = field(default_factory=list)  # Einflussflaechen zu 'nodes' [m^2]
    face: int = -1
    behaviour: dict = field(default_factory=dict)     # {FHG: DofBehaviour}

    def dof_behaviour(self, dof: int) -> DofBehaviour:
        b = self.behaviour.get(dof) or self.behaviour.get(str(dof))
        if b is None:
            return DofBehaviour("free")
        return b if isinstance(b, DofBehaviour) else _dc(DofBehaviour, b)


@dataclass
class Line:
    """Linie zwischen Knoten (RFEM: Linien; Staebe verweisen darauf).

    Eine Linie ist reine Geometrie. 'typ' nennt die Art (polyline, arc,
    circle, ellipse, spline, parabola); 'geometrie' haelt die Angaben, die
    ueber die Stuetzknoten hinausgehen - Mittelpunkt und Radius eines Kreises,
    Grad und Gewichte eines Splines. Die Punktfolge liefert punkte().
    """
    name: str
    nodes: list[int] = field(default_factory=list)
    typ: str = "polyline"
    comment: str = ""
    geometrie: dict = field(default_factory=dict)

    def kurve(self, model=None):
        """Die Kurve dieser Linie (statik3d.geometry.Kurve)."""
        from . import geometry as geo
        kw = dict(self.geometrie)
        if model is not None and self.nodes:
            kw.setdefault("punkte", [model.nodes[int(i)] for i in self.nodes])
            kw.setdefault("steuerpunkte", kw["punkte"])
        return geo.kurve(self.typ, **kw)

    def punkte(self, model=None, n: int = None) -> np.ndarray:
        """Stuetzpunkte der Linie; n = Anzahl der Abschnitte."""
        from . import geometry as geo
        return self.kurve(model).punkte(int(n or self.geometrie.get("teilung")
                                            or geo.TEILUNG))

    def laenge(self, model=None) -> float:
        return float(self.kurve(model).laenge())


HINGE_DOF_NAMES = ["ux", "uy", "uz", "phix", "phiy", "phiz"]


@dataclass
class MemberHinge:
    """Stabendgelenk (RFEM: Stabendgelenke). Je lokalem FHG 0..5:
    'fixed' (biegesteif), 'free' (gelenkig) oder 'spring' mit Federsteifigkeit.
    'end' 0 = Stabanfang, 1 = Stabende. Lokale FHG: 0 ux, 1 uy, 2 uz,
    3 Torsion, 4 My, 5 Mz."""
    name: str = ""
    end: int = 0
    typ: list[str] = field(default_factory=lambda: ["fixed"] * 6)
    stiffness: list[float] = field(default_factory=lambda: [0.0] * 6)

    def released(self) -> list[int]:
        """Lokale Element-FHG (0..11), die gelenkig sind (fuer die Kondensation)."""
        return [d + 6 * self.end for d, t in enumerate(self.typ) if t == "free"]

    def springs(self) -> list[tuple[int, float]]:
        return [(d + 6 * self.end, float(k)) for d, (t, k) in enumerate(zip(self.typ, self.stiffness))
                if t == "spring" and k > 0]

    def describe(self) -> str:
        parts = []
        for d, t in enumerate(self.typ):
            if t == "free":
                parts.append(HINGE_DOF_NAMES[d])
            elif t == "spring" and self.stiffness[d] > 0:
                parts.append(f"{HINGE_DOF_NAMES[d]}={self.stiffness[d]:g}")
        return ("Anfang" if self.end == 0 else "Ende") + ": " + (", ".join(parts) or "biegesteif")


# --------------------------------------------------------------------------
# Lasten
# --------------------------------------------------------------------------
@dataclass
class NodalLoad:
    node: int
    F: list[float] = field(default_factory=lambda: [0.0] * 6)  # Fx Fy Fz Mx My Mz


@dataclass
class BeamLoad:
    """Streckenlast auf Stabelement (linear veraenderlich q1 -> q2 moeglich).
    system: 'global' (auf wahre Laenge bezogen) oder 'local'.
    """
    elem: int
    q: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # qx qy qz [N/m] am Anfang
    system: str = "global"
    q2: Optional[list[float]] = None   # Wert am Stabende (None = gleich q)


@dataclass
class FaceLoad:
    """Flaechenlast (Druck) auf Schalen- oder Volumen-Oberflaeche.
    Bei Schalen: p wirkt in lokale z-Richtung (+ = in Normalenrichtung).
    Bei Volumen: face = lokale Flaechennummer, p in Normalenrichtung (+ = Druck nach innen).
    Optional: direction = globaler Richtungsvektor (dann wirkt p*A in dieser Richtung).
    """
    elem: int
    p: float = 0.0
    face: int = 0
    direction: Optional[list[float]] = None


@dataclass
class TempLoad:
    """Gleichmaessige Temperaturaenderung dT [K] eines Elements
    (Stab, Schale oder Volumen). Optional dT_z = Temperaturdifferenz ueber die
    Hoehe (oben - unten) fuer Stabbiegung um y."""
    elem: int
    dT: float = 0.0
    dT_z: float = 0.0


@dataclass
class LoadCase:
    """Ein Lastfall mit eigener Lastzusammenstellung."""
    name: str
    category: str = "G"
    description: str = ""
    psi: Optional[list[float]] = None      # (psi0, psi1, psi2); None -> aus Kategorie
    exclusive_group: str = ""              # Lastfaelle derselben Gruppe wirken nie gemeinsam
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    beam_loads: list[BeamLoad] = field(default_factory=list)
    face_loads: list[FaceLoad] = field(default_factory=list)
    temp_loads: list[TempLoad] = field(default_factory=list)
    gravity: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    gamma_sup: Optional[float] = None      # Teilsicherheitsbeiwert (None -> aus Kategorie)
    gamma_inf: Optional[float] = None

    @property
    def psi_factors(self) -> tuple[float, float, float]:
        if self.psi is not None:
            return tuple(self.psi)
        return ACTION_CATEGORIES.get(self.category, ACTION_CATEGORIES["Q"])[1]

    @property
    def is_permanent(self) -> bool:
        return self.category in ("G", "P", "SET")

    @property
    def is_variable(self) -> bool:
        return self.category.startswith("Q") or self.category in ("S", "S_H", "W", "T", "H")

    @property
    def is_accidental(self) -> bool:
        return self.category == "A"

    @property
    def n_loads(self) -> int:
        return (len(self.nodal_loads) + len(self.beam_loads) + len(self.face_loads)
                + len(self.temp_loads) + (1 if np.any(self.gravity) else 0))

    def to_dict(self) -> dict:
        return {
            "name": self.name, "category": self.category,
            "description": self.description, "psi": self.psi,
            "exclusive_group": self.exclusive_group,
            "nodal_loads": [asdict(l) for l in self.nodal_loads],
            "beam_loads": [asdict(l) for l in self.beam_loads],
            "face_loads": [asdict(l) for l in self.face_loads],
            "temp_loads": [asdict(l) for l in self.temp_loads],
            "gravity": list(map(float, self.gravity)),
            "gamma_sup": self.gamma_sup, "gamma_inf": self.gamma_inf,
        }

    @staticmethod
    def from_dict(d: dict) -> "LoadCase":
        lc = LoadCase(d["name"], d.get("category", "G"), d.get("description", ""),
                      d.get("psi"), d.get("exclusive_group", ""))
        lc.nodal_loads = [NodalLoad(**l) for l in d.get("nodal_loads", [])]
        lc.beam_loads = [BeamLoad(**l) for l in d.get("beam_loads", [])]
        lc.face_loads = [FaceLoad(**l) for l in d.get("face_loads", [])]
        lc.temp_loads = [TempLoad(**l) for l in d.get("temp_loads", [])]
        lc.gravity = list(d.get("gravity", [0, 0, 0]))
        lc.gamma_sup = d.get("gamma_sup")
        lc.gamma_inf = d.get("gamma_inf")
        return lc


@dataclass
class Combination:
    """Lastfallkombination: Lastfallname -> Faktor.
    typ: ULS (GZT, STR/GEO), EQU, ACC (aussergewoehnlich), SLS_CH (charakteristisch),
         SLS_FR (haeufig), SLS_QP (quasi-staendig), USER
    """
    name: str
    factors: dict[str, float] = field(default_factory=dict)
    typ: str = "ULS"
    description: str = ""
    leading: str = ""       # Leiteinwirkung (Information)

    @property
    def is_uls(self) -> bool:
        return self.typ in ("ULS", "EQU", "ACC", "USER")

    @property
    def is_sls(self) -> bool:
        return self.typ.startswith("SLS")

    def formula(self) -> str:
        return " + ".join(f"{f:g}·{k}" for k, f in self.factors.items() if f)


@dataclass
class FatigueLoad:
    """Ermuedungsbeanspruchung: Lastwechsel zwischen den Lastfaellen case_max und
    case_min (None = Nullzustand) mit cycles Lastspielen ueber die Lebensdauer.
    Die Spannungsschwingbreite folgt aus der Differenz der beiden Zustaende."""
    name: str
    case_max: str
    case_min: Optional[str] = None
    cycles: float = 2e6
    factor: float = 1.0        # zusaetzlicher Faktor (z.B. dynamischer Beiwert)


# --------------------------------------------------------------------------
# Staebe (Member) fuer Nachweise
# --------------------------------------------------------------------------
@dataclass
class Member:
    """Physischer Stab = Kette von Stabelementen (in Reihenfolge entlang der Achse).
    Parameter fuer die Stabilitaetsnachweise nach EN 1993-1-1 6.3 und den
    Ermuedungsnachweis nach EN 1993-1-9."""
    name: str
    elements: list[int] = field(default_factory=list)
    design: bool = True
    beta_y: float = 1.0                # Knicklaengenbeiwert um y (Lcr,y = beta_y * L)
    beta_z: float = 1.0                # Knicklaengenbeiwert um z
    Lcr_y: Optional[float] = None      # explizite Knicklaenge [m] (ueberschreibt beta)
    Lcr_z: Optional[float] = None
    L_LT: Optional[float] = None       # Abstand seitlicher Halterungen [m] (None = Stablaenge)
    k_z: float = 1.0                   # Randbedingungsbeiwerte fuer Mcr
    k_w: float = 1.0
    C1: Optional[float] = None         # Momentenbeiwert (None = automatisch)
    load_position: str = "shear_centre"  # top | shear_centre | bottom (Lastangriff fuer Mcr)
    lt_check: bool = True              # Biegedrillknicken nachweisen
    sway_y: bool = False               # verschieblich um y (Cmy = 0.9)
    sway_z: bool = False               # verschieblich um z (Cmz = 0.9)
    a_steifen: float = 0.0             # Abstand der Quersteifen [m] (0 = nur an den Auflagern)
    starre_endsteife: bool = False     # starre Endquersteife (EN 1993-1-5, Tab. 5.1)
    detail_category: Optional[float] = None       # Kerbfall Delta-sigma_c [Pa], z.B. 71e6
    detail_category_shear: Optional[float] = None  # Kerbfall Schub Delta-tau_c [Pa]
    fatigue_points: str = "flanges"    # Spannungspunkte fuer Ermuedung
    consequence: str = "low"           # low | high (Schadensfolge, gamma_Mf)
    assessment: str = "damage_tolerant"  # damage_tolerant | safe_life


@dataclass
class Volumenbereich:
    """
    Ein Bereich aus Volumenelementen fuer den Spannungsnachweis.

    Volumen bekommen keine Querschnittsnachweise - es gibt keinen
    Querschnitt.  Nachgewiesen wird der **Spannungszustand** nach
    DIN EN 1993-1-1, 6.2.1(5): die Vergleichsspannung nach von Mises gegen
    f_y/gamma_M0.  Zusaetzlich werden die Hauptspannungen, die
    Mehrachsigkeit und - bei dreiachsigem Zug - der Hinweis auf die
    Zaehigkeitsanforderungen nach DIN EN 1993-1-10 ausgewiesen.

    elemente:   die Volumenelemente des Bereichs (tet4, tet10, hex8)
    ausrundung: Kerbradius [m] am Nachweisort, 0 = unbekannt. Wird er
                angegeben, prueft das Programm, ob die Vernetzung dort fein
                genug ist, und sagt es, wenn nicht.
    singular:   Der Bereich enthaelt eine bekannte Spannungssingularitaet
                (einspringende Ecke, Einzellast, Punktlager). Dann wird die
                Spitzenspannung nicht als Nachweis gefuehrt, sondern nur
                berichtet - alles andere waere sinnlos, weil sie mit der
                Netzfeinheit waechst.
    """
    name: str
    elemente: list = field(default_factory=list)
    design: bool = True
    ausrundung: float = 0.0
    singular: bool = False
    beschreibung: str = ""

    def bezug(self) -> str:
        n = len(self.elemente)
        return f"{n} Volumenelement{'e' if n != 1 else ''}"


@dataclass
class Joint:
    """Ein Anschluss an einem Stabende (DIN EN 1993-1-8).

    Der Anschluss gehoert zum Modell: er wird mitgespeichert, steht im
    Modellbaum und in der Tabelle, und er wird bei jeder Berechnung mit
    nachgewiesen. Die Geometrie liegt als Feldwerte der Vorlage vor
    (``statik3d.joints.templates``), damit sie ohne die Vorlagenklasse
    gespeichert und gelesen werden kann.

    typ:        Schluessel aus joints.templates.TYPES
                ("kopfplatte", "lasche", "diagonale")
    elem, end:  Stabelement und sein Ende (0 = Anfang, 1 = Ende)
    geometrie:  Blechdicken, Schraubenbild, Nahtdicken - die Felder der Vorlage
    schraube:   size, grade, hole, category, mu
    kraefte:    von Hand gesetzte Schnittgroessen [N, Nm]. Leer heisst: die
                Schnittgroessen kommen aus der Rechnung, ueber alle
                GZT-Kombinationen, und die ungünstigste ist massgebend.
    ermuedung:  Namen der Ermuedungslasten (leer = alle vorhandenen)
    """
    name: str
    typ: str = "kopfplatte"
    elem: int = 0
    end: int = 1
    geometrie: dict = field(default_factory=dict)
    schraube: dict = field(default_factory=dict)
    kraefte: dict = field(default_factory=dict)
    ermuedung: list = field(default_factory=list)
    design: bool = True
    beschreibung: str = ""
    # -- Momenten-Rotations-Verhalten (EN 1993-1-8, Kap. 5 und 6.3) ------
    #: "automatisch" = nach der Klassifizierung (starr, Drehfeder, Gelenk),
    #: "starr" | "gelenkig" | "feder" = fest vorgegeben
    modellierung: str = "automatisch"
    #: Angaben der Stuetze fuer k_1 bis k_4: h, b, tw, tf, r, fy, versteift
    stuetze: dict = field(default_factory=dict)
    #: "ausgesteift" (k_b = 8) oder "nicht ausgesteift" (k_b = 25) nach 5.2.2.5
    rahmen: str = "ausgesteift"
    #: von Hand gesetzte Drehfedersteifigkeit [Nm/rad] (0 = aus der Rechnung)
    S_j: float = 0.0

    def ort(self) -> str:
        return f"Element {self.elem + 1}, Ende {'A' if self.end == 0 else 'E'}"


@dataclass
class Beulsteife:
    """Eine Steife eines Beulfeldes (DIN EN 1993-1-5, Anhang A und Abschnitt 9).

    art:    "laengs" oder "quer"
    lage:   Abstand vom gedrueckten Rand [m] (laengs) beziehungsweise Abstand
            zur naechsten Quersteife [m] (quer)
    A_sl:   Flaeche der Steife allein [m^2]
    I_sl:   Traegheitsmoment der Steife mit mitwirkendem Blech [m^4]
    A_sl_1: Flaeche mit mitwirkendem Blech [m^2] (0 = je 15 eps t, Bild 4.4)
    I_T, I_p: Torsions- und polares Traegheitsmoment fuer 9.2.1
    """
    art: str = "laengs"
    lage: float = 0.0
    A_sl: float = 0.0
    I_sl: float = 0.0
    A_sl_1: float = 0.0
    I_T: float = 0.0
    I_p: float = 0.0
    name: str = ""


@dataclass
class Beulfeld:
    """Ein Blechfeld fuer den Beulnachweis.

    art: "eben"     ebenes Blechfeld nach DIN EN 1993-1-5, Abschnitt 10
         "zylinder" Kreiszylinderschale nach DIN EN 1993-1-6, Abschnitt 8.5

    elemente: die Schalenelemente, die das Feld bilden. Abmessungen und Dicke
    werden daraus gewonnen; a, b und t ueberschreiben sie, wenn gesetzt.

    rand: "beidseitig" (Feld an beiden Laengsraendern gestuetzt, z. B. ein
    Stegblech zwischen den Flanschen) oder "einseitig" (ein Rand frei).

    Fuer den Zylinder: r (Radius) und l (Beullaenge); 0 = aus der Geometrie.
    qualitaet ist die Herstelltoleranzklasse A, B oder C (Tab. 8.4),
    randbedingung eine der Kennungen "BC1-BC1", "BC1-BC2", "BC2-BC2".
    """
    name: str
    elemente: list = field(default_factory=list)
    art: str = "eben"
    a: float = 0.0                 # Laenge des Feldes [m] (0 = aus der Geometrie)
    b: float = 0.0                 # Breite quer zur Hauptdruckspannung [m]
    t: float = 0.0                 # Blechdicke [m] (0 = aus der Schalendicke)
    rand: str = "beidseitig"
    starre_endsteife: bool = False
    steifen: list = field(default_factory=list)   # Beulsteife
    # -- Zylinder (EN 1993-1-6) -----------------------------------------
    r: float = 0.0                 # Radius [m]
    l: float = 0.0                 # Beullaenge [m]
    qualitaet: str = "B"           # Herstelltoleranzklasse A | B | C
    randbedingung: str = "BC1-BC1"
    beschreibung: str = ""

    def bezug(self) -> str:
        n = len(self.elemente)
        s = f"{n} Element{'e' if n != 1 else ''}"
        if self.steifen:
            nl = sum(1 for x in self.steifen if _steifenart(x) == "laengs")
            nq = len(self.steifen) - nl
            teile = []
            if nl:
                teile.append(f"{nl} Längssteife{'n' if nl != 1 else ''}")
            if nq:
                teile.append(f"{nq} Quersteife{'n' if nq != 1 else ''}")
            s += ", " + " und ".join(teile)
        return s


def _steifenart(x) -> str:
    return x.get("art", "laengs") if isinstance(x, dict) else getattr(x, "art", "laengs")


@dataclass
class Lasteinleitung:
    """Nachweis der Lasteinleitung nach DIN EN 1993-1-5, Abschnitt 6.

    knoten: der Knoten, an dem die Kraft eingeleitet wird.
    quelle: "last" (Knotenlast der Kombination) oder "auflager" (Auflagerkraft)
    typ:    "a", "b" oder "c" nach Bild 6.1
    s_s:    Lasteinleitungslaenge [m]
    a:      Abstand der Quersteifen [m] (0 = keine)
    c:      Abstand vom Traegerende [m] (nur Typ c)
    stab:   Name des Stabes, dessen Querschnitt die Stegabmessungen liefert
    """
    name: str
    knoten: int = 0
    stab: str = ""
    quelle: str = "last"
    typ: str = "a"
    s_s: float = 0.0
    a: float = 0.0
    c: float = 0.0
    richtung: int = 2              # Freiheitsgrad der Kraft (2 = z)
    beschreibung: str = ""

    def bezug(self) -> str:
        return f"Knoten {self.knoten}" + (f", Stab {self.stab}" if self.stab else "")


@dataclass
class Berichtseintrag:
    """Ein aus der Ansicht in den Bericht uebernommenes Ergebnis.

    Der Nutzer stellt in der Ansicht ein, was er zeigen will - Lastfall oder
    Kombination, Faerbung, Schnittgroessenverlauf, Ueberhoehung - und
    uebernimmt das Bild mit einem Befehl. Der Eintrag haelt sowohl das **Bild**
    (PNG, Base64) als auch die **Einstellung**, aus der es entstanden ist;
    so steht im Bericht nicht nur eine Grafik, sondern auch, was sie zeigt.

    quelle: "case:LF1", "combo:GZT7", "env:GZT" oder "modal:1"
    """
    name: str = ""
    quelle: str = ""
    feld: str = ""                 # Faerbung
    verlauf: str = ""              # Schnittgroessenverlauf
    ueberhoehung: float = 0.0
    bild: str = ""                 # PNG als Base64, ohne Praefix
    beschriftung: str = ""
    bemerkung: str = ""

    def bezug(self) -> str:
        teile = [self.quelle_text()]
        if self.feld:
            teile.append(self.feld)
        if self.verlauf and self.verlauf != "kein Verlauf":
            teile.append(self.verlauf)
        return " · ".join(t for t in teile if t)

    def quelle_text(self) -> str:
        art, _, wert = (self.quelle or "").partition(":")
        return {"case": f"Lastfall {wert}", "combo": f"Kombination {wert}",
                "env": f"Umhüllende {wert}", "modal": f"Eigenform {wert}",
                "buckling": f"Knickfigur {wert}"}.get(art, self.quelle or "-")


@dataclass
class Flaeche:
    """Flaeche als Modellobjekt (RFEM: Flaechen) - berandet von Linien.

    Die Kette ist dieselbe wie in RFEM: aus Knoten werden Linien, aus Linien
    Flaechen, aus Flaechen Volumenkoerper. Die Flaeche selbst ist Geometrie;
    erst das **Vernetzen** macht daraus Schalenelemente, deren Nummern in
    ``elemente`` stehen. Wird die Flaeche geaendert oder neu vernetzt, sind es
    andere Elemente - der Zusammenhang bleibt ueber dieses Feld erhalten.

    linien:   Namen der Randlinien, in beliebiger Reihenfolge; der Rand wird
              ueber die gemeinsamen Endknoten zusammengesetzt.
    teilung:  Elementzahl in den beiden Randrichtungen beim Vernetzen.
    """
    name: str
    linien: list[str] = field(default_factory=list)
    typ: str = "eben"
    dicke: str = ""                  # Name der ShellProp
    material: str = ""
    teilung: list[int] = field(default_factory=lambda: [4, 4])
    elemente: list[int] = field(default_factory=list)
    kommentar: str = ""

    def bezug(self) -> str:
        t = f"{len(self.linien)} Linien"
        if self.dicke:
            t += f", {self.dicke}"
        return t + (f", {len(self.elemente)} Elemente" if self.elemente
                    else ", nicht vernetzt")

    def randknoten(self, model) -> list[int]:
        """Die Randknoten im Umlauf - oder [], wenn der Rand nicht schliesst."""
        return _rand_aus_linien(model, self.linien)


@dataclass
class Volumenkoerper:
    """Volumenkoerper als Modellobjekt (RFEM: Volumen) - berandet von Flaechen.

    Wie bei der Flaeche ist der Koerper Geometrie; ``elemente`` haelt die
    Volumenelemente, die beim Vernetzen daraus entstanden sind.
    """
    name: str
    flaechen: list[str] = field(default_factory=list)
    material: str = ""
    teilung: list[int] = field(default_factory=lambda: [4, 4, 4])
    elemente: list[int] = field(default_factory=list)
    kommentar: str = ""

    def bezug(self) -> str:
        t = f"{len(self.flaechen)} Flächen"
        if self.material:
            t += f", {self.material}"
        return t + (f", {len(self.elemente)} Elemente" if self.elemente
                    else ", nicht vernetzt")


def _rand_aus_linien(model, linien: list[str]) -> list[int]:
    """Randpolygon aus Linienzuegen zusammensetzen.

    Die Linien duerfen in beliebiger Reihenfolge und Richtung stehen; sie
    werden ueber ihre gemeinsamen Endknoten aneinandergehaengt. Schliesst der
    Umlauf nicht, kommt eine leere Liste zurueck - lieber keine Flaeche als
    eine falsche.
    """
    stuecke = []
    for name in linien:
        ln = model.lines.get(name)
        if ln is None or len(ln.nodes) < 2:
            return []
        stuecke.append([int(n) for n in ln.nodes])
    if not stuecke:
        return []
    kette = list(stuecke.pop(0))
    while stuecke:
        for i, st in enumerate(stuecke):
            if st[0] == kette[-1]:
                kette += st[1:]
            elif st[-1] == kette[-1]:
                kette += st[-2::-1]
            elif st[-1] == kette[0]:
                kette = st[:-1] + kette
            elif st[0] == kette[0]:
                kette = st[:0:-1] + kette
            else:
                continue
            stuecke.pop(i)
            break
        else:
            return []                      # ein Stueck haengt nirgends an
    # Der Umlauf muss sich schliessen. Ein offener Zug waere keine Berandung -
    # er wuerde eine Flaeche vortaeuschen, deren Rand nirgends endet.
    if len(kette) < 4 or kette[0] != kette[-1]:
        return []
    kette.pop()
    return kette if len(kette) >= 3 else []


@dataclass
class Flaechenfreigabe:
    """Flaechenfreigabe (RFEM: Flaechenfreigaben).

    Eine Flaechenfreigabe trennt die genannten Flaechen von den Objekten, an
    denen sie haengen, und verbindet beide ueber Federn je Freiheitsgrad -
    typisch eine **Kontaktfuge**: in der Ebene starr, senkrecht dazu frei mit
    Ausfall bei Zug.

    Das Programm **liest und speichert** die Freigabe vollstaendig, fuehrt die
    Trennung aber **nicht** aus: dafuer muessten die beteiligten Flaechen
    vernetzt und die Knoten an der Fuge verdoppelt werden. ``ausgefuehrt``
    haelt fest, ob das geschehen ist. Solange es False ist, rechnet das Modell
    an dieser Stelle durchverbunden - also zu steif. Das ist eine
    Modellangabe, keine Zierde: sie steht im Modellbaum, in der Tabelle und im
    Bericht, damit die Luecke sichtbar bleibt.

    flaechen/volumen: Nummern der freigegebenen Objekte in der Quelldatei
    behaviour:        {FHG: DofBehaviour} des Freigabetyps
    """
    name: str = ""
    flaechen: list[int] = field(default_factory=list)
    volumen: list[int] = field(default_factory=list)
    ziele: int = 0                       # Zahl der Objekte, an denen sie haengt
    ort: str = "Anfang"
    typ: str = ""                        # Name/Nummer des Freigabetyps
    behaviour: dict = field(default_factory=dict)     # {FHG: DofBehaviour}
    aus: bool = False                    # in der Quelldatei deaktiviert
    ausgefuehrt: bool = False            # Trennung im Netz umgesetzt?
    beschreibung: str = ""

    def dof_behaviour(self, dof: int) -> DofBehaviour:
        b = self.behaviour.get(dof) or self.behaviour.get(str(dof))
        if b is None:
            return DofBehaviour("free")
        return b if isinstance(b, DofBehaviour) else _dc(DofBehaviour, b)

    def bezug(self) -> str:
        teile = [f"{len(self.flaechen)} Flächen"]
        if self.volumen:
            teile.append(f"{len(self.volumen)} Volumen")
        if self.ziele:
            teile.append(f"an {self.ziele} Objekten")
        return ", ".join(teile)

    def describe(self) -> str:
        namen = ["ux", "uy", "uz", "phix", "phiy", "phiz"]
        teile = []
        for d in range(6):
            b = self.dof_behaviour(d)
            wert = b.describe() if b.acts else "frei"
            if b.failure and "Ausfall" not in wert:
                wert += f" (Ausfall bei {b.failure.capitalize()})"
            if b.mu:
                wert += f", Reibung mu = {b.mu:g}"
            teile.append(f"{namen[d]}={wert}")
        return ", ".join(teile)


#: Verformungsgroessen einer Grenze
VERFORMUNGSGROESSEN = {
    "ux": "Verschiebung in x", "uy": "Verschiebung in y", "uz": "Verschiebung in z",
    "u": "Betrag der Verschiebung",
    "phix": "Verdrehung um x", "phiy": "Verdrehung um y", "phiz": "Verdrehung um z",
}


@dataclass
class Verformungsgrenze:
    """Ein Verformungsnachweis im Grenzzustand der Gebrauchstauglichkeit.

    art:
        "stab"       Durchbiegung eines Stabes, bezogen auf die **Sehne**
                     zwischen seinen Enden (die uebliche Durchbiegung w)
        "knoten"     Verschiebung oder Verdrehung eines Knotens gegenueber
                     der Ausgangslage (z. B. Kragarmspitze)
        "punktpaar"  Verschiebung zweier Knoten **gegeneinander** - fuer
                     Dichtungen, Fuehrungen, Fugen und Anschlaege

    grenzart:
        "L/x"        Grenze = L / wert; L ist die Stablaenge beziehungsweise
                     der Abstand der beiden Knoten
        "absolut"    Grenze = wert [m] beziehungsweise [rad]

    situation: "SLS_CH" (charakteristisch), "SLS_FR" (haeufig),
               "SLS_QP" (quasi-staendig) oder "" fuer alle GZG-Kombinationen.
    ueberhoehung: Vorkruemmung w_c [m]; sie wird von der Durchbiegung
               abgezogen (EN 1993-1-1, A.1.4.2: w = w_max - w_c).
    """
    name: str
    art: str = "stab"
    stab: str = ""
    knoten: list = field(default_factory=list)
    groesse: str = "uz"
    grenzart: str = "L/x"
    wert: float = 300.0
    situation: str = "SLS_CH"
    ueberhoehung: float = 0.0
    beschreibung: str = ""

    def grenztext(self) -> str:
        if self.grenzart == "L/x":
            return f"L/{self.wert:g}"
        if self.groesse.startswith("phi"):
            return f"{self.wert * 1e3:g} mrad"
        return f"{self.wert * 1e3:g} mm"

    def bezug(self) -> str:
        if self.art == "stab":
            return f"Stab {self.stab}"
        if self.art == "punktpaar" and len(self.knoten) >= 2:
            return f"Knoten {self.knoten[0]} gegen {self.knoten[1]}"
        return f"Knoten {self.knoten[0]}" if self.knoten else "-"


@dataclass
class DesignSettings:
    """Globale Einstellungen der Nachweise (DIN EN 1993-1-1/NA)."""
    gamma_M0: float = 1.0
    gamma_M1: float = 1.1
    gamma_M2: float = 1.25
    gamma_Ff: float = 1.0
    interaction_method: str = "B"      # Anhang A (Methode 1) oder B (Methode 2)
    lt_method: str = "general"         # general (6.3.2.2) | rolled (6.3.2.3)
    national_annex: str = "DE"
    combination_rule: str = "6.10"     # 6.10 | 6.10ab
    xi: float = 0.85
    gamma_G_sup: float = 1.35
    gamma_G_inf: float = 1.0
    gamma_Q: float = 1.5
    gamma_Q_fav: float = 0.0
    stations: int = 9                  # Nachweisstellen je Element
    # --- Theorie II. Ordnung und Imperfektionen (EN 1993-1-1, 5.2 und 5.3)
    theorie2: str = "aus"              # aus | auto (nach 5.2.1(3)) | ein
    imperfektionen: bool = True        # Ersatzimperfektionen nach 5.3.2 ansetzen
    th2_plastisch: bool = False        # plastische Berechnung -> Grenze alpha_cr = 15
    th2_richtung: Optional[list] = None  # Richtung der Schiefstellung [x, y]
                                       # (None = aus der Kombination bestimmt)
    th2_alle_vorkruemmungen: bool = False  # 5.3.2(6) uebergehen und alle ansetzen


# --------------------------------------------------------------------------
# Kontakt
# --------------------------------------------------------------------------
@dataclass
class ContactSupport:
    """Einseitiges Lager (nur Druck), z.B. Auflagerung auf Beton oder Boden.
    direction: Richtung, in die das Lager stuetzt (Einheitsvektor). Der Knoten
    darf sich frei in +direction bewegen; Bewegung in -direction ueber den Spalt
    hinaus wird durch die Kontaktsteifigkeit gehalten.
    stiffness = 0 -> automatische (quasi-starre) Penalty-Steifigkeit,
    stiffness > 0 -> elastische Bettung [N/m] (nur Druck)."""
    node: int
    direction: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    gap: float = 0.0
    stiffness: float = 0.0
    mu: float = 0.0
    group: str = "default"


@dataclass
class GapElement:
    """Knoten-Knoten-Kontakt (Spaltelement) zwischen node_a und node_b.
    direction: Richtung von a nach b (None -> aus Geometrie). Kontakt wird aktiv,
    wenn sich b relativ zu a um mehr als 'gap' auf a zubewegt.
    mu: Reibungsbeiwert (Coulomb) fuer die tangentiale Kopplung."""
    node_a: int
    node_b: int
    direction: Optional[list[float]] = None
    gap: float = 0.0
    stiffness: float = 0.0
    mu: float = 0.0
    group: str = "default"


@dataclass
class ContactPair:
    """Knoten-Flaeche-Kontakt: slave_nodes gegen die Oberflaeche von master_elements
    (Schalenelemente oder Volumenelemente, deren Aussenflaechen benutzt werden)
    oder explizit gegebene Facetten master_faces (Knotenlisten mit 3 oder 4 Knoten).
    Die Facettennormale zeigt vom Master weg zum Slave (bei Bedarf flip_normal).
    stiffness = 0 -> automatische Penalty-Steifigkeit; mu = Reibungsbeiwert."""
    name: str
    slave_nodes: list[int] = field(default_factory=list)
    master_elements: list[int] = field(default_factory=list)
    master_faces: list[list[int]] = field(default_factory=list)
    stiffness: float = 0.0
    mu: float = 0.0
    gap: float = 0.0
    search_radius: Optional[float] = None
    flip_normal: bool = False


# --------------------------------------------------------------------------
# Gesamtmodell
# --------------------------------------------------------------------------
class Model:
    def __init__(self, name: str = "Modell"):
        self.name = name
        self.nodes: np.ndarray = np.zeros((0, 3))
        self.elements: list[Element] = []
        self.materials: dict[str, Material] = {}
        self.sections: dict[str, Section] = {}
        self.shells: dict[str, ShellProp] = {}
        self.supports: list[Support] = []
        self.line_supports: list[LineSupport] = []
        self.surface_supports: list[SurfaceSupport] = []
        self.lines: dict[str, Line] = {}
        self.hinges: dict[str, MemberHinge] = {}
        # Lastfaelle / Kombinationen
        self.load_cases: dict[str, LoadCase] = {}
        self.combinations: dict[str, Combination] = {}
        self.fatigue_loads: dict[str, FatigueLoad] = {}
        self.active_case: str = ""
        self.add_load_case("LF1", "G", "Eigengewicht / staendige Lasten")
        # Nachweise
        self.members: dict[str, Member] = {}
        self.joints: dict[str, Joint] = {}
        self.verformungsgrenzen: dict[str, Verformungsgrenze] = {}
        self.beulfelder: dict[str, Beulfeld] = {}
        self.volumenbereiche: dict[str, Volumenbereich] = {}
        self.lasteinleitungen: dict[str, Lasteinleitung] = {}
        self.flaechenfreigaben: dict[str, Flaechenfreigabe] = {}
        self.flaechen: dict[str, Flaeche] = {}
        self.koerper: dict[str, Volumenkoerper] = {}
        #: Aus der Ansicht in den Bericht uebernommene Ergebnisse, in der
        #: Reihenfolge, in der sie im Bericht stehen sollen.
        self.bericht: list[Berichtseintrag] = []
        self.design = DesignSettings()
        # Kontakt
        self.contact_supports: list[ContactSupport] = []
        self.gap_elements: list[GapElement] = []
        self.contact_pairs: list[ContactPair] = []
        # Metadaten (Bericht)
        self.meta: dict[str, str] = {"projekt": "", "bauteil": "", "bearbeiter": "",
                                     "auftraggeber": "", "position": ""}

    # ---------------- Lastfaelle ----------------
    def add_load_case(self, name: str, category: str = "Q", description: str = "",
                      activate: bool = True, **kw) -> LoadCase:
        if category not in ACTION_CATEGORIES:
            raise KeyError(f"Einwirkungskategorie '{category}' unbekannt")
        lc = LoadCase(name, category, description, **kw)
        self.load_cases[name] = lc
        if activate or not self.active_case:
            self.active_case = name
        return lc

    def remove_load_case(self, name: str):
        self.load_cases.pop(name, None)
        for c in self.combinations.values():
            c.factors.pop(name, None)
        if self.active_case == name:
            self.active_case = next(iter(self.load_cases), "")
        if not self.load_cases:
            self.add_load_case("LF1", "G")

    def case(self, name: str = None) -> LoadCase:
        """Lastfall (default: aktiver Lastfall)."""
        if name is None:
            name = self.active_case
        if name not in self.load_cases:
            raise KeyError(f"Lastfall '{name}' existiert nicht")
        return self.load_cases[name]

    def add_combination(self, name: str, factors: dict, typ: str = "ULS",
                        description: str = "", leading: str = "") -> Combination:
        c = Combination(name, dict(factors), typ, description, leading)
        self.combinations[name] = c
        return c

    def add_fatigue_load(self, name: str, case_max: str, case_min: str = None,
                         cycles: float = 2e6, factor: float = 1.0) -> FatigueLoad:
        f = FatigueLoad(name, case_max, case_min, cycles, factor)
        self.fatigue_loads[name] = f
        return f

    # Kompatible Ein-Lastfall-API -> aktiver Lastfall
    @property
    def nodal_loads(self) -> list[NodalLoad]:
        return self.case().nodal_loads

    @property
    def beam_loads(self) -> list[BeamLoad]:
        return self.case().beam_loads

    @property
    def face_loads(self) -> list[FaceLoad]:
        return self.case().face_loads

    @property
    def temp_loads(self) -> list[TempLoad]:
        return self.case().temp_loads

    @property
    def gravity(self) -> np.ndarray:
        lc = self.case()
        if not isinstance(lc.gravity, np.ndarray):
            lc.gravity = np.asarray(lc.gravity, dtype=float)
        return lc.gravity

    @gravity.setter
    def gravity(self, g):
        self.case().gravity = np.asarray(g, dtype=float)

    # ---------------- Aufbau ----------------
    def add_node(self, x: float, y: float, z: float) -> int:
        self.nodes = np.vstack([self.nodes, [x, y, z]])
        return len(self.nodes) - 1

    def add_nodes(self, coords) -> np.ndarray:
        coords = np.asarray(coords, dtype=float).reshape(-1, 3)
        i0 = len(self.nodes)
        self.nodes = np.vstack([self.nodes, coords])
        return np.arange(i0, len(self.nodes))

    def add_material(self, m: Material) -> Material:
        self.materials[m.name] = m
        return m

    def add_section(self, s: Section) -> Section:
        self.sections[s.name] = s
        return s

    def add_shell_prop(self, s: ShellProp) -> ShellProp:
        self.shells[s.name] = s
        return s

    def add_element(self, typ: str, nodes, mat: str, sec: str = None,
                    roll: float = 0.0, group: str = "default", hinges=None) -> int:
        self.elements.append(Element(typ, [int(n) for n in nodes], mat, sec, roll, group,
                                     list(hinges) if hinges else []))
        return len(self.elements) - 1

    def add_elements(self, typ: str, conn, mat: str, sec: str = None,
                     group: str = "default") -> list[int]:
        ids = []
        for row in np.asarray(conn):
            ids.append(self.add_element(typ, row, mat, sec, group=group))
        return ids

    def add_member(self, name: str, elements, **kw) -> Member:
        m = Member(name, [int(e) for e in elements], **kw)
        self.members[name] = m
        return m

    def add_verformungsgrenze(self, name: str, art: str = "stab", **kw) -> Verformungsgrenze:
        """Einen Verformungsnachweis (GZG) in das Modell aufnehmen."""
        if art not in ("stab", "knoten", "punktpaar"):
            raise ValueError(f"Art „{art}“ unbekannt: stab | knoten | punktpaar")
        g = kw.get("groesse", "uz")
        if g not in VERFORMUNGSGROESSEN:
            raise KeyError(f"Verformungsgröße „{g}“ unbekannt: "
                           f"{sorted(VERFORMUNGSGROESSEN)}")
        v = Verformungsgrenze(name, art, **kw)
        if art == "stab" and v.stab and v.stab not in self.members:
            raise KeyError(f"Stab „{v.stab}“ gibt es nicht")
        if art in ("knoten", "punktpaar"):
            noetig = 2 if art == "punktpaar" else 1
            if len(v.knoten) < noetig:
                raise ValueError(f"„{art}“ braucht {noetig} Knoten")
        self.verformungsgrenzen[name] = v
        return v

    def add_beulfeld(self, name: str, elemente, **kw) -> Beulfeld:
        """Ein Blechfeld fuer den Beulnachweis aufnehmen."""
        els = [int(e) for e in elemente]
        if not els:
            raise ValueError("Ein Beulfeld braucht Schalenelemente")
        for e in els:
            if not 0 <= e < len(self.elements):
                raise IndexError(f"Element {e} gibt es nicht")
            if not self.elements[e].typ.startswith("shell"):
                raise ValueError(f"Element {e + 1} ist kein Flächenelement")
        b = Beulfeld(name, els, **kw)
        self.beulfelder[name] = b
        return b

    def add_volumenbereich(self, name: str, elemente, **kw) -> Volumenbereich:
        """Einen Volumenbereich fuer den Spannungsnachweis aufnehmen."""
        els = [int(e) for e in elemente]
        if not els:
            raise ValueError("Ein Volumenbereich braucht Volumenelemente")
        for e in els:
            if not 0 <= e < len(self.elements):
                raise IndexError(f"Element {e} gibt es nicht")
            if self.elements[e].typ not in ("tet4", "tet10", "hex8"):
                raise ValueError(f"Element {e + 1} ist kein Volumenelement")
        v = Volumenbereich(name, els, **kw)
        self.volumenbereiche[name] = v
        return v

    def add_lasteinleitung(self, name: str, knoten: int, **kw) -> Lasteinleitung:
        """Einen Lasteinleitungsnachweis (EN 1993-1-5, Abschnitt 6) aufnehmen."""
        n = int(knoten)
        if not 0 <= n < self.nn:
            raise IndexError(f"Knoten {n} gibt es nicht")
        le = Lasteinleitung(name, n, **kw)
        if le.typ not in ("a", "b", "c"):
            raise ValueError("Lasteinleitungstyp muss a, b oder c sein (Bild 6.1)")
        if le.stab and le.stab not in self.members:
            raise KeyError(f"Stab „{le.stab}“ gibt es nicht")
        self.lasteinleitungen[name] = le
        return le

    def add_flaeche(self, name: str, linien, **kw) -> Flaeche:
        """Eine Flaeche aus Randlinien anlegen (noch ohne Netz)."""
        namen = [str(x) for x in linien]
        fehlt = [x for x in namen if x not in self.lines]
        if fehlt:
            raise KeyError(f"Linie(n) gibt es nicht: {', '.join(fehlt)}")
        f = Flaeche(name, namen, **kw)
        if not f.randknoten(self):
            raise ValueError("Die Linien bilden keinen geschlossenen Rand.")
        self.flaechen[name] = f
        return f

    def add_koerper(self, name: str, flaechen, **kw) -> Volumenkoerper:
        """Einen Volumenkoerper aus Randflaechen anlegen (noch ohne Netz)."""
        namen = [str(x) for x in flaechen]
        fehlt = [x for x in namen if x not in self.flaechen]
        if fehlt:
            raise KeyError(f"Flaeche(n) gibt es nicht: {', '.join(fehlt)}")
        if len(namen) < 4:
            raise ValueError("Ein Volumenkörper braucht mindestens vier Randflächen.")
        k = Volumenkoerper(name, namen, **kw)
        self.koerper[name] = k
        return k

    def add_flaechenfreigabe(self, name: str, **kw) -> Flaechenfreigabe:
        """Eine Flaechenfreigabe aufnehmen (aus RFEM gelesen oder von Hand).

        Die Trennung im Netz fuehrt das Programm nicht aus; ``ausgefuehrt``
        bleibt darum False, bis das jemand tut.
        """
        fr = Flaechenfreigabe(name, **kw)
        self.flaechenfreigaben[name] = fr
        return fr

    def add_joint(self, name: str, typ: str, elem: int, end: int = 1, **kw) -> Joint:
        """Anschluss an einem Stabende in das Modell aufnehmen."""
        e = int(elem)
        if not 0 <= e < len(self.elements):
            raise IndexError(f"Element {e} gibt es nicht")
        if self.elements[e].typ not in ("beam", "truss"):
            raise ValueError(f"Element {e + 1} ist kein Stab")
        j = Joint(name, typ, e, int(end), **kw)
        self.joints[name] = j
        return j

    def fix(self, node: int, dofs="all", values=None, stiffness=None):
        if dofs == "all":
            dofs = [0, 1, 2, 3, 4, 5]
        elif dofs == "pinned":
            dofs = [0, 1, 2]
        self.supports.append(Support(int(node), list(dofs),
                                     list(values) if values is not None else None,
                                     list(stiffness) if stiffness is not None else None))

    def support(self, node: int, dofs="all", name: str = "", **behaviour) -> Support:
        """Lager mit Nichtlinearitaet je FHG.

            m.support(3, "pinned", uz=dict(failure="zug", slip=0.002),
                      ux=dict(mu=0.3, mu_ref=2), uy=dict(mu=0.3, mu_ref=2))

        Schluesselwoerter: ux, uy, uz, phix, phiy, phiz (oder d0..d5) mit
        einem dict der DofBehaviour-Felder.
        """
        if dofs == "all":
            dofs = [0, 1, 2, 3, 4, 5]
        elif dofs == "pinned":
            dofs = [0, 1, 2]
        elif dofs == "free":
            dofs = []
        s = Support(int(node), [int(d) for d in dofs], name=name)
        for key, val in behaviour.items():
            d = dof_index(key)
            s.set_behaviour(d, **(val if isinstance(val, dict) else asdict(val)))
        self.supports.append(s)
        return s

    def add_line_support(self, nodes, name: str = "", **behaviour) -> LineSupport:
        """Linienlager: Steifigkeiten je Laenge ([N/m je m]).

            m.add_line_support(kante, uz=dict(typ="spring", stiffness=5e7, failure="zug"))
        """
        ls = LineSupport(name or f"LL{len(self.line_supports) + 1}", [int(n) for n in nodes])
        for key, val in behaviour.items():
            ls.behaviour[dof_index(key)] = DofBehaviour(**(val if isinstance(val, dict) else asdict(val)))
        self.line_supports.append(ls)
        return ls

    def add_surface_support(self, elements=(), name: str = "", nodes=(), areas=(),
                            face: int = -1, **behaviour) -> SurfaceSupport:
        """Flaechenlager / Bettung: Steifigkeiten je Flaeche ([N/m je m^2] = [N/m^3])."""
        ss = SurfaceSupport(name or f"FL{len(self.surface_supports) + 1}",
                            [int(e) for e in elements], [int(n) for n in nodes],
                            [float(a) for a in areas], int(face))
        for key, val in behaviour.items():
            ss.behaviour[dof_index(key)] = DofBehaviour(**(val if isinstance(val, dict) else asdict(val)))
        self.surface_supports.append(ss)
        return ss

    def add_line(self, name: str, nodes=(), typ: str = "polyline",
                 **geometrie) -> Line:
        """Linie anlegen.

            m.add_line("L1", [0, 1])                       # Polylinie
            m.add_line("B1", [0, 1, 2], "arc")             # Bogen durch drei Knoten
            m.add_line("K1", typ="circle", mitte=(0,0,0), radius=2.0)
        """
        ln = Line(name, [int(n) for n in nodes], typ, geometrie=dict(geometrie))
        self.lines[name] = ln
        return ln

    def line_to_beams(self, name: str, mat: str, sec: str, n: int = None,
                      typ: str = "beam", group: str = "") -> list[int]:
        """Eine Linie in Stabelemente teilen. Rueckgabe: Elementnummern.

        Die Punkte der Linie werden zu Knoten; vorhandene Stuetzknoten werden
        wiederverwendet, wenn sie auf der Linie liegen.
        """
        ln = self.lines[name]
        P = ln.punkte(self, n)
        idx = []
        for p in P:
            if self.nn:
                d = np.linalg.norm(self.nodes - np.asarray(p, float), axis=1)
                i = int(np.argmin(d))
                if float(d[i]) < 1e-9:
                    idx.append(i)
                    continue
            idx.append(self.add_node(float(p[0]), float(p[1]), float(p[2])))
        return [self.add_element(typ, [idx[k], idx[k + 1]], mat, sec,
                                 group=group or name)
                for k in range(len(idx) - 1)]

    def add_hinge(self, name: str, end: int = 0, **dofs) -> MemberHinge:
        """Gelenkdefinition: ux/uy/uz/phix/phiy/phiz = 'free' oder Federsteifigkeit.

            m.add_hinge("G1", end=1, phiy="free", phiz=1.5e6)
        """
        h = MemberHinge(name, int(end))
        for key, val in dofs.items():
            d = dof_index(key)
            if isinstance(val, str):
                h.typ[d] = val
            else:
                h.typ[d] = "spring"
                h.stiffness[d] = float(val)
        self.hinges[name] = h
        return h

    def apply_hinge(self, elem: int, hinge, end: int = None):
        """Gelenkdefinition auf ein Stabelement legen."""
        h = self.hinges[hinge] if isinstance(hinge, str) else hinge
        if end is not None:
            h = MemberHinge(h.name, int(end), list(h.typ), list(h.stiffness))
        e = self.elements[int(elem)]
        e.hinges = sorted(set(e.hinges) | set(h.released()))
        springs = {d: k for d, k in e.hinge_springs}
        springs.update(dict(h.springs()))
        e.hinge_springs = sorted(springs.items())
        return h

    def load_node(self, node: int, Fx=0.0, Fy=0.0, Fz=0.0, Mx=0.0, My=0.0, Mz=0.0,
                  case: str = None):
        self.case(case).nodal_loads.append(NodalLoad(int(node), [Fx, Fy, Fz, Mx, My, Mz]))

    def load_beam(self, elem: int, qx=0.0, qy=0.0, qz=0.0, system="global",
                  case: str = None, q2=None):
        self.case(case).beam_loads.append(
            BeamLoad(int(elem), [qx, qy, qz], system, list(q2) if q2 is not None else None))

    def load_face(self, elem: int, p: float, face: int = 0, case: str = None,
                  direction=None):
        self.case(case).face_loads.append(
            FaceLoad(int(elem), p, face, list(direction) if direction is not None else None))

    def load_temp(self, elem: int, dT: float, dT_z: float = 0.0, case: str = None):
        self.case(case).temp_loads.append(TempLoad(int(elem), dT, dT_z))

    def set_gravity(self, gz: float = -9.81, case: str = None):
        self.case(case).gravity = np.array([0.0, 0.0, gz])

    # ---------------- Kontakt ----------------
    def add_contact_support(self, node: int, direction=(0, 0, 1), gap=0.0,
                            stiffness=0.0, mu=0.0, group="default") -> ContactSupport:
        c = ContactSupport(int(node), [float(x) for x in direction], gap, stiffness, mu, group)
        self.contact_supports.append(c)
        return c

    def add_gap_element(self, node_a: int, node_b: int, direction=None, gap=0.0,
                        stiffness=0.0, mu=0.0, group="default") -> GapElement:
        g = GapElement(int(node_a), int(node_b),
                       [float(x) for x in direction] if direction is not None else None,
                       gap, stiffness, mu, group)
        self.gap_elements.append(g)
        return g

    def add_contact_pair(self, name: str, slave_nodes, master_elements=(),
                         master_faces=(), stiffness=0.0, mu=0.0, gap=0.0,
                         search_radius=None, flip_normal=False) -> ContactPair:
        c = ContactPair(name, [int(n) for n in slave_nodes],
                        [int(e) for e in master_elements],
                        [[int(n) for n in f] for f in master_faces],
                        stiffness, mu, gap, search_radius, flip_normal)
        self.contact_pairs.append(c)
        return c

    @property
    def has_contact(self) -> bool:
        """True, wenn eine nichtlineare Iteration noetig ist: Kontaktdefinitionen
        oder Lager mit Ausfall, Schlupf, Reibung bzw. Grenzkraft."""
        if self.contact_supports or self.gap_elements or self.contact_pairs:
            return True
        if any(s.nonlinear for s in self.supports):
            return True
        for grp in (self.line_supports, self.surface_supports):
            for x in grp:
                if any(x.dof_behaviour(d).nonlinear for d in range(NDOF)):
                    return True
        return False

    # ---------------- Hilfen ----------------
    @property
    def nn(self) -> int:
        return len(self.nodes)

    @property
    def ndof(self) -> int:
        return self.nn * NDOF

    def element_nodes(self, e: Element) -> np.ndarray:
        return self.nodes[e.nodes]

    def element_length(self, i: int) -> float:
        e = self.elements[i]
        return float(np.linalg.norm(self.nodes[e.nodes[1]] - self.nodes[e.nodes[0]]))

    def member_length(self, m: Member) -> float:
        return sum(self.element_length(i) for i in m.elements)

    def bbox(self):
        if self.nn == 0:
            return np.zeros(3), np.ones(3)
        return self.nodes.min(axis=0), self.nodes.max(axis=0)

    def characteristic_size(self) -> float:
        lo, hi = self.bbox()
        d = float(np.linalg.norm(hi - lo))
        return d if d > 0 else 1.0

    def beam_elements(self) -> list[int]:
        return [i for i, e in enumerate(self.elements) if e.typ in ("beam", "truss")]

    def auto_members(self, prefix: str = "S", angle_tol: float = 1e-3,
                     replace: bool = False) -> list[Member]:
        """Kollineare Stabelemente gleichen Querschnitts zu Staeben verketten
        (fuer importierte Netze ohne Stabinformation)."""
        if replace:
            self.members.clear()
        assigned = set()
        for m in self.members.values():
            assigned.update(m.elements)
        beams = [i for i in self.beam_elements() if i not in assigned]
        if not beams:
            return []
        # Knoten -> Elemente
        n2e: dict[int, list[int]] = {}
        for i in beams:
            for n in self.elements[i].nodes:
                n2e.setdefault(n, []).append(i)

        def direction(i):
            e = self.elements[i]
            d = self.nodes[e.nodes[1]] - self.nodes[e.nodes[0]]
            return d / (np.linalg.norm(d) or 1.0)

        def can_join(i, j, node):
            ei, ej = self.elements[i], self.elements[j]
            if ei.sec != ej.sec or ei.mat != ej.mat or ei.typ != ej.typ:
                return False
            if len(n2e[node]) != 2:
                return False
            if abs(abs(float(np.dot(direction(i), direction(j)))) - 1.0) > angle_tol:
                return False
            return True

        used = set()
        members = []
        k = len(self.members)
        for start in beams:
            if start in used:
                continue
            chain = [start]
            used.add(start)
            # nach vorne
            for forward in (True, False):
                cur = start
                while True:
                    e = self.elements[cur]
                    node = e.nodes[1] if forward else e.nodes[0]
                    nxt = [j for j in n2e[node] if j != cur and j not in used]
                    if len(nxt) != 1 or not can_join(cur, nxt[0], node):
                        break
                    nx = nxt[0]
                    # Orientierung sicherstellen: naechstes Element muss am Knoten beginnen
                    en = self.elements[nx]
                    if forward and en.nodes[0] != node:
                        en.nodes = [en.nodes[1], en.nodes[0]]
                    if not forward and en.nodes[1] != node:
                        en.nodes = [en.nodes[1], en.nodes[0]]
                    used.add(nx)
                    if forward:
                        chain.append(nx)
                    else:
                        chain.insert(0, nx)
                    cur = nx
            k += 1
            members.append(self.add_member(f"{prefix}{k}", chain))
        return members

    def check(self) -> list[str]:
        """Einfache Modellpruefung. Gibt Liste von Warnungen/Fehlern zurueck."""
        msgs = []
        if self.nn == 0:
            msgs.append("FEHLER: keine Knoten definiert")
        if not self.elements:
            msgs.append("FEHLER: keine Elemente definiert")
        if not self.supports and not self.contact_supports:
            msgs.append("FEHLER: keine Lagerung definiert (System kinematisch)")
        used = np.zeros(self.nn, dtype=bool)
        for i, e in enumerate(self.elements):
            if e.mat not in self.materials:
                msgs.append(f"FEHLER: Element {i}: Material '{e.mat}' unbekannt")
            if e.typ in ("beam", "truss") and e.sec not in self.sections:
                msgs.append(f"FEHLER: Element {i}: Querschnitt '{e.sec}' unbekannt")
            if e.typ in ("shell3", "shell4") and e.sec not in self.shells:
                msgs.append(f"FEHLER: Element {i}: Schalendicke '{e.sec}' unbekannt")
            for n in e.nodes:
                if n < 0 or n >= self.nn:
                    msgs.append(f"FEHLER: Element {i}: Knoten {n} existiert nicht")
                else:
                    used[n] = True
        free = np.where(~used)[0]
        if len(free):
            msgs.append(f"WARNUNG: {len(free)} Knoten ohne Elementanschluss")
        for c in self.combinations.values():
            for k in c.factors:
                if k not in self.load_cases:
                    msgs.append(f"FEHLER: Kombination '{c.name}': Lastfall '{k}' unbekannt")
        for f in self.fatigue_loads.values():
            for k in (f.case_max, f.case_min):
                if k and k not in self.load_cases:
                    msgs.append(f"FEHLER: Ermuedungslast '{f.name}': Lastfall '{k}' unbekannt")
        for m in self.members.values():
            for i in m.elements:
                if i < 0 or i >= len(self.elements):
                    msgs.append(f"FEHLER: Stab '{m.name}': Element {i} existiert nicht")
                elif self.elements[i].typ not in ("beam", "truss"):
                    msgs.append(f"FEHLER: Stab '{m.name}': Element {i} ist kein Stabelement")
        n_loads = sum(lc.n_loads for lc in self.load_cases.values())
        if n_loads == 0:
            msgs.append("WARNUNG: keine Lasten definiert")
        for lc in self.load_cases.values():
            for l in lc.nodal_loads:
                if l.node >= self.nn:
                    msgs.append(f"FEHLER: Lastfall '{lc.name}': Knoten {l.node} existiert nicht")
            for l in lc.beam_loads:
                if l.elem >= len(self.elements):
                    msgs.append(f"FEHLER: Lastfall '{lc.name}': Element {l.elem} existiert nicht")
        for cp in self.contact_pairs:
            if not cp.master_elements and not cp.master_faces:
                msgs.append(f"FEHLER: Kontaktpaar '{cp.name}' ohne Master-Flaeche")
            if not cp.slave_nodes:
                msgs.append(f"FEHLER: Kontaktpaar '{cp.name}' ohne Slave-Knoten")
        return msgs

    # ---------------- Speichern / Laden ----------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION,
            "name": self.name,
            "meta": dict(self.meta),
            "nodes": self.nodes.tolist(),
            "elements": [asdict(e) for e in self.elements],
            "materials": {k: asdict(v) for k, v in self.materials.items()},
            "sections": {k: asdict(v) for k, v in self.sections.items()},
            "shells": {k: asdict(v) for k, v in self.shells.items()},
            "supports": [_support_dict(s) for s in self.supports],
            "line_supports": [_beh_dict(asdict(x)) for x in self.line_supports],
            "surface_supports": [_beh_dict(asdict(x)) for x in self.surface_supports],
            "lines": [asdict(x) for x in self.lines.values()],
            "hinges": [asdict(x) for x in self.hinges.values()],
            "load_cases": [lc.to_dict() for lc in self.load_cases.values()],
            "active_case": self.active_case,
            "combinations": [asdict(c) for c in self.combinations.values()],
            "fatigue_loads": [asdict(f) for f in self.fatigue_loads.values()],
            "members": [asdict(m) for m in self.members.values()],
            "joints": [asdict(j) for j in self.joints.values()],
            "verformungsgrenzen": [asdict(v) for v in self.verformungsgrenzen.values()],
            "beulfelder": [asdict(x) for x in self.beulfelder.values()],
            "volumenbereiche": [asdict(x) for x in self.volumenbereiche.values()],
            "lasteinleitungen": [asdict(x) for x in self.lasteinleitungen.values()],
            "flaechenfreigaben": [_beh_dict(asdict(x))
                                  for x in self.flaechenfreigaben.values()],
            "flaechen": [asdict(x) for x in self.flaechen.values()],
            "koerper": [asdict(x) for x in self.koerper.values()],
            "bericht": [asdict(x) for x in self.bericht],
            "design": asdict(self.design),
            "contact_supports": [asdict(c) for c in self.contact_supports],
            "gap_elements": [asdict(g) for g in self.gap_elements],
            "contact_pairs": [asdict(c) for c in self.contact_pairs],
        }

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1)

    @staticmethod
    def from_dict(d: dict) -> "Model":
        m = Model(d.get("name", "Modell"))
        m.meta.update(d.get("meta", {}))
        m.nodes = np.asarray(d["nodes"], dtype=float).reshape(-1, 3)
        m.elements = [_dc(Element, e) for e in d["elements"]]
        m.materials = {k: _dc(Material, v) for k, v in d["materials"].items()}
        m.sections = {k: _dc(Section, v) for k, v in d["sections"].items()}
        m.shells = {k: _dc(ShellProp, v) for k, v in d.get("shells", {}).items()}
        m.supports = [_support_from(sd) for sd in d["supports"]]
        m.line_supports = [_beh_from(LineSupport, x) for x in d.get("line_supports", [])]
        m.surface_supports = [_beh_from(SurfaceSupport, x) for x in d.get("surface_supports", [])]
        m.lines = {x["name"]: _dc(Line, x) for x in d.get("lines", [])}
        m.hinges = {x["name"]: _dc(MemberHinge, x) for x in d.get("hinges", [])}
        if "load_cases" in d:
            m.load_cases = {}
            for lcd in d["load_cases"]:
                lc = LoadCase.from_dict(lcd)
                m.load_cases[lc.name] = lc
            if not m.load_cases:
                m.add_load_case("LF1", "G")
            m.active_case = d.get("active_case") or next(iter(m.load_cases))
        else:   # Format 1: ein Lastfall
            lc = m.case()
            lc.nodal_loads = [_dc(NodalLoad, l) for l in d.get("nodal_loads", [])]
            lc.beam_loads = [_dc(BeamLoad, l) for l in d.get("beam_loads", [])]
            lc.face_loads = [_dc(FaceLoad, l) for l in d.get("face_loads", [])]
            lc.gravity = list(d.get("gravity", [0, 0, 0]))
        m.combinations = {c["name"]: _dc(Combination, c) for c in d.get("combinations", [])}
        m.fatigue_loads = {f["name"]: _dc(FatigueLoad, f) for f in d.get("fatigue_loads", [])}
        m.members = {mm["name"]: _dc(Member, mm) for mm in d.get("members", [])}
        m.joints = {j["name"]: _dc(Joint, j) for j in d.get("joints", [])}
        m.verformungsgrenzen = {v["name"]: _dc(Verformungsgrenze, v)
                                for v in d.get("verformungsgrenzen", [])}
        m.beulfelder = {x["name"]: _dc(Beulfeld, x) for x in d.get("beulfelder", [])}
        m.volumenbereiche = {x["name"]: _dc(Volumenbereich, x)
                             for x in d.get("volumenbereiche", [])}
        for bf in m.beulfelder.values():
            bf.steifen = [_dc(Beulsteife, x) if isinstance(x, dict) else x
                          for x in (bf.steifen or [])]
        m.lasteinleitungen = {x["name"]: _dc(Lasteinleitung, x)
                              for x in d.get("lasteinleitungen", [])}
        m.flaechenfreigaben = {x["name"]: _beh_from(Flaechenfreigabe, x)
                               for x in d.get("flaechenfreigaben", [])}
        m.flaechen = {x["name"]: _dc(Flaeche, x) for x in d.get("flaechen", [])}
        m.koerper = {x["name"]: _dc(Volumenkoerper, x) for x in d.get("koerper", [])}
        m.bericht = [_dc(Berichtseintrag, x) for x in d.get("bericht", [])]
        if "design" in d:
            m.design = _dc(DesignSettings, d["design"])
        m.contact_supports = [_dc(ContactSupport, c) for c in d.get("contact_supports", [])]
        m.gap_elements = [_dc(GapElement, g) for g in d.get("gap_elements", [])]
        m.contact_pairs = [_dc(ContactPair, c) for c in d.get("contact_pairs", [])]
        return m

    @staticmethod
    def load(path: str) -> "Model":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return Model.from_dict(d)

    def copy(self) -> "Model":
        return Model.from_dict(json.loads(json.dumps(self.to_dict())))


def _beh_dict(d: dict) -> dict:
    """Verhaltens-Woerterbuch {FHG: DofBehaviour} JSON-tauglich machen."""
    b = d.get("behaviour") or {}
    d = dict(d)
    d["behaviour"] = {str(k): (asdict(v) if hasattr(v, "typ") else dict(v)) for k, v in b.items()}
    return d


def _beh_from(cls, d: dict):
    obj = _dc(cls, {k: v for k, v in d.items() if k != "behaviour"})
    obj.behaviour = {int(k): _dc(DofBehaviour, v) for k, v in (d.get("behaviour") or {}).items()}
    return obj


def _support_dict(s: Support) -> dict:
    return _beh_dict(asdict(s))


def _support_from(d: dict) -> Support:
    return _beh_from(Support, d)


def _dc(cls, d: dict):
    """Dataclass aus dict, unbekannte Schluessel ignorieren (Vorwaertskompatibilitaet)."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})
