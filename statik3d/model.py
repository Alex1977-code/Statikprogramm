"""
Datenmodell fuer Statik3D.

Einheiten (konsistent, SI):
    Laenge   m
    Kraft    N
    Spannung Pa (N/m^2)
    Dichte   kg/m^3
    Temperatur K bzw. Kelvin-Differenz
    Winkel   rad (Element.roll), Ausnahme: Stellung.angle in Grad (siehe dort)

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
* Stellungen (Stellung): Lagen eines beweglichen Systems (Klapp-, Dreh-,
  Hubbruecke). Jede Stellung bewegt einen Teil des Modells als Starrkoerper
  und traegt eigene Lager und Lastfaelle; die Nachweise laufen ueber die
  Umhuellende aller Stellungen (siehe statik3d.stellungen).

Kompatibilitaet: Die alte Ein-Lastfall-API (model.load_node, model.nodal_loads,
model.gravity ...) arbeitet auf dem *aktiven* Lastfall weiter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from typing import Optional

import numpy as np

DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]
NDOF = 6
FORMAT_VERSION = 3       # 3: Stellungen des Systems (bewegliche Bruecken)

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


@dataclass
class Support:
    node: int
    dofs: list[int]                 # gesperrte FHG-Indizes 0..5
    values: Optional[list[float]] = None   # vorgegebene Verschiebungen (default 0)
    stiffness: Optional[list[float]] = None  # optional Federsteifigkeiten statt starr


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
    detail_category: Optional[float] = None       # Kerbfall Delta-sigma_c [Pa], z.B. 71e6
    detail_category_shear: Optional[float] = None  # Kerbfall Schub Delta-tau_c [Pa]
    fatigue_points: str = "flanges"    # Spannungspunkte fuer Ermuedung
    consequence: str = "low"           # low | high (Schadensfolge, gamma_Mf)
    assessment: str = "damage_tolerant"  # damage_tolerant | safe_life


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
# Stellungen des Systems (bewegliche Bruecken)
# --------------------------------------------------------------------------
MOVEMENT_KINDS = {
    "rotate": "Drehung um eine Achse (Klapp-, Dreh-, Faltbruecke)",
    "translate": "Verschiebung laengs einer Richtung (Hub-, Schiebebruecke)",
    "none": "unveraendert (Ausgangslage)",
}


@dataclass
class Stellung:
    """Eine Stellung des beweglichen Systems.

    Die Stellung beschreibt eine Starrkoerperbewegung des *bewegten Bauteils*
    gegenueber der Ausgangsgeometrie des Modells:

        kind = 'rotate'     Drehung um die Achse (axis_point, axis_dir)
                            um angle [Grad], Rechtsschraube um axis_dir
        kind = 'translate'  Verschiebung um shift [m] in Richtung axis_dir
        kind = 'none'       unveraenderte Geometrie (z.B. Verkehrsstellung)

    Der Winkel steht abweichend von der sonstigen SI-Konvention in **Grad**:
    im Brueckenbau wird die Stellung durchweg in Grad angegeben (0 Grad
    geschlossen, 82 Grad offen), und der Wert erscheint unveraendert in
    Eingabe, Bericht und Zeichnung.

    Das bewegte Bauteil ergibt sich aus den Elementgruppen `moving_groups`
    (alle Knoten der Elemente dieser Gruppen) und zusaetzlich aus den
    ausdruecklich genannten Knoten `moving_nodes`.

    Lagerung: In jeder Stellung ist das System anders gelagert (verriegelt,
    im Drehlager, am Endanschlag). `supports` sind die Lager dieser Stellung.
    Mit `use_model_supports = True` treten sie zu den Lagern des Modells
    hinzu, mit False ersetzen sie diese vollstaendig.

    Lastfaelle: `cases` waehlt die in dieser Stellung wirkenden Lastfaelle
    (leer = alle). Kombinationen, die einen nicht gewaehlten Lastfall mit
    einem Faktor ungleich null enthalten, entfallen in dieser Stellung.
    """
    name: str
    title: str = ""                    # Klartext, z.B. "Verkehrsstellung"
    kind: str = "rotate"
    angle: float = 0.0                 # Drehwinkel [Grad]
    shift: float = 0.0                 # Verschiebung [m]
    axis_point: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    axis_dir: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    moving_groups: list[str] = field(default_factory=list)
    moving_nodes: list[int] = field(default_factory=list)
    supports: list[Support] = field(default_factory=list)
    use_model_supports: bool = True
    contact_supports: list[ContactSupport] = field(default_factory=list)
    cases: list[str] = field(default_factory=list)
    active: bool = True                # in der Umhuellenden beruecksichtigen
    description: str = ""

    @property
    def moves(self) -> bool:
        """Bewegt diese Stellung ueberhaupt etwas gegenueber der Ausgangslage?"""
        if self.kind == "rotate":
            return abs(self.angle) > 1e-12
        if self.kind == "translate":
            return abs(self.shift) > 1e-12
        return False

    @property
    def label(self) -> str:
        return f"{self.name} ({self.title})" if self.title else self.name

    def value_text(self) -> str:
        if self.kind == "rotate":
            return f"{self.angle:g}°"
        if self.kind == "translate":
            return f"{self.shift:g} m"
        return "—"

    def to_dict(self) -> dict:
        return {
            "name": self.name, "title": self.title, "kind": self.kind,
            "angle": float(self.angle), "shift": float(self.shift),
            "axis_point": [float(v) for v in self.axis_point],
            "axis_dir": [float(v) for v in self.axis_dir],
            "moving_groups": list(self.moving_groups),
            "moving_nodes": [int(n) for n in self.moving_nodes],
            "supports": [asdict(s) for s in self.supports],
            "use_model_supports": bool(self.use_model_supports),
            "contact_supports": [asdict(c) for c in self.contact_supports],
            "cases": list(self.cases), "active": bool(self.active),
            "description": self.description,
        }

    @staticmethod
    def from_dict(d: dict) -> "Stellung":
        st = Stellung(
            d["name"], d.get("title", ""), d.get("kind", "rotate"),
            float(d.get("angle", 0.0)), float(d.get("shift", 0.0)),
            list(d.get("axis_point", [0.0, 0.0, 0.0])),
            list(d.get("axis_dir", [0.0, 1.0, 0.0])),
            list(d.get("moving_groups", [])),
            [int(n) for n in d.get("moving_nodes", [])],
        )
        st.supports = [_dc(Support, s) for s in d.get("supports", [])]
        st.use_model_supports = bool(d.get("use_model_supports", True))
        st.contact_supports = [_dc(ContactSupport, c) for c in d.get("contact_supports", [])]
        st.cases = list(d.get("cases", []))
        st.active = bool(d.get("active", True))
        st.description = d.get("description", "")
        return st


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
        # Lastfaelle / Kombinationen
        self.load_cases: dict[str, LoadCase] = {}
        self.combinations: dict[str, Combination] = {}
        self.fatigue_loads: dict[str, FatigueLoad] = {}
        self.active_case: str = ""
        self.add_load_case("LF1", "G", "Eigengewicht / staendige Lasten")
        # Nachweise
        self.members: dict[str, Member] = {}
        self.design = DesignSettings()
        # Kontakt
        self.contact_supports: list[ContactSupport] = []
        self.gap_elements: list[GapElement] = []
        self.contact_pairs: list[ContactPair] = []
        # Stellungen (bewegliche Bruecken)
        self.stellungen: dict[str, Stellung] = {}
        self.active_stellung: str = ""
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

    def fix(self, node: int, dofs="all", values=None, stiffness=None):
        if dofs == "all":
            dofs = [0, 1, 2, 3, 4, 5]
        elif dofs == "pinned":
            dofs = [0, 1, 2]
        self.supports.append(Support(int(node), list(dofs),
                                     list(values) if values is not None else None,
                                     list(stiffness) if stiffness is not None else None))

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
        return bool(self.contact_supports or self.gap_elements or self.contact_pairs)

    # ---------------- Stellungen ----------------
    def add_stellung(self, name: str, title: str = "", kind: str = "rotate",
                     angle: float = 0.0, activate: bool = True, **kw) -> Stellung:
        """Stellung anlegen. angle in Grad, shift in m (siehe Stellung)."""
        if kind not in MOVEMENT_KINDS:
            raise KeyError(f"Bewegungsart '{kind}' unbekannt: {list(MOVEMENT_KINDS)}")
        st = Stellung(name, title, kind, angle, **kw)
        self.stellungen[name] = st
        if activate or not self.active_stellung:
            self.active_stellung = name
        return st

    def remove_stellung(self, name: str):
        self.stellungen.pop(name, None)
        if self.active_stellung == name:
            self.active_stellung = next(iter(self.stellungen), "")

    def stellung(self, name: str = None) -> Stellung:
        """Stellung (default: aktive Stellung)."""
        if name is None:
            name = self.active_stellung
        if name not in self.stellungen:
            raise KeyError(f"Stellung '{name}' existiert nicht")
        return self.stellungen[name]

    @property
    def is_movable(self) -> bool:
        return bool(self.stellungen)

    def active_stellungen(self) -> list[Stellung]:
        """Stellungen, die in die Umhuellende eingehen (in Eingabereihenfolge)."""
        return [s for s in self.stellungen.values() if s.active]

    def element_groups(self) -> list[str]:
        """Vorhandene Elementgruppen (fuer die Wahl des bewegten Bauteils)."""
        seen = {}
        for e in self.elements:
            seen[e.group] = None
        return list(seen)

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
        groups = set(self.element_groups())
        for st in self.stellungen.values():
            if st.kind not in MOVEMENT_KINDS:
                msgs.append(f"FEHLER: Stellung '{st.name}': Bewegungsart '{st.kind}' unbekannt")
            if st.kind in ("rotate", "translate") and not np.any(np.asarray(st.axis_dir, float)):
                msgs.append(f"FEHLER: Stellung '{st.name}': Achsrichtung ist der Nullvektor")
            for n in st.moving_nodes:
                if n < 0 or n >= self.nn:
                    msgs.append(f"FEHLER: Stellung '{st.name}': Knoten {n} existiert nicht")
            for gname in st.moving_groups:
                if gname not in groups:
                    msgs.append(f"WARNUNG: Stellung '{st.name}': Elementgruppe "
                                f"'{gname}' kommt im Modell nicht vor")
            for k in st.cases:
                if k not in self.load_cases:
                    msgs.append(f"FEHLER: Stellung '{st.name}': Lastfall '{k}' unbekannt")
            for s in st.supports:
                if s.node < 0 or s.node >= self.nn:
                    msgs.append(f"FEHLER: Stellung '{st.name}': Lagerknoten {s.node} "
                                f"existiert nicht")
            if st.moves and not st.moving_groups and not st.moving_nodes:
                msgs.append(f"WARNUNG: Stellung '{st.name}': kein bewegtes Bauteil "
                            f"gewaehlt, die Geometrie bleibt unveraendert")
            if not st.use_model_supports and not st.supports and not st.contact_supports:
                msgs.append(f"FEHLER: Stellung '{st.name}': keine Lagerung "
                            f"(Modelllager abgewaehlt und keine eigenen Lager)")
        if self.stellungen and not self.active_stellungen():
            msgs.append("WARNUNG: keine Stellung aktiv - die Umhuellende ueber die "
                        "Stellungen bleibt leer")
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
            "supports": [asdict(s) for s in self.supports],
            "load_cases": [lc.to_dict() for lc in self.load_cases.values()],
            "active_case": self.active_case,
            "combinations": [asdict(c) for c in self.combinations.values()],
            "fatigue_loads": [asdict(f) for f in self.fatigue_loads.values()],
            "members": [asdict(m) for m in self.members.values()],
            "design": asdict(self.design),
            "contact_supports": [asdict(c) for c in self.contact_supports],
            "gap_elements": [asdict(g) for g in self.gap_elements],
            "contact_pairs": [asdict(c) for c in self.contact_pairs],
            "stellungen": [s.to_dict() for s in self.stellungen.values()],
            "active_stellung": self.active_stellung,
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
        m.supports = [_dc(Support, s) for s in d["supports"]]
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
        if "design" in d:
            m.design = _dc(DesignSettings, d["design"])
        m.contact_supports = [_dc(ContactSupport, c) for c in d.get("contact_supports", [])]
        m.gap_elements = [_dc(GapElement, g) for g in d.get("gap_elements", [])]
        m.contact_pairs = [_dc(ContactPair, c) for c in d.get("contact_pairs", [])]
        for sd in d.get("stellungen", []):
            s = Stellung.from_dict(sd)
            m.stellungen[s.name] = s
        m.active_stellung = d.get("active_stellung") or next(iter(m.stellungen), "")
        return m

    @staticmethod
    def load(path: str) -> "Model":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return Model.from_dict(d)

    def copy(self) -> "Model":
        return Model.from_dict(json.loads(json.dumps(self.to_dict())))


def _dc(cls, d: dict):
    """Dataclass aus dict, unbekannte Schluessel ignorieren (Vorwaertskompatibilitaet)."""
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})
