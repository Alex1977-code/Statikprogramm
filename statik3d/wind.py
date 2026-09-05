"""
Lastgenerierer Wind nach DIN EN 1991-1-4 mit deutschem Nationalen Anhang.

Ein :class:`Wind` beschreibt eine Anströmung: Windzone (oder v_b unmittelbar),
Geländekategorie bzw. Mischprofil des NA, Richtung, die belasteten Flächen
(Wände, Dächer, freistehende Wände, Schilder) und Stäbe (Kraftbeiwerte je
Querschnitt). Daraus entstehen Objektlasten an den Flächen (Verlauf "wind":
Druck aus q_p(z) und dem Außendruckbeiwert der Zone am Punkt) und Linienlasten
auf den Stäben (w = c_f·q_p(z)·b_ref, trapezförmig über die Höhe). Alles
folgt jedem Neuvernetzen.

**Strömung** (4.2 bis 4.5): v_b = c_dir·c_season·v_b,0; Rauigkeit
c_r(z) = k_r·ln(z/z_0) mit k_r = 0,19·(z_0/z_0,II)^0,07 (z ≥ z_min, Tab. 4.1);
mittlere Geschwindigkeit v_m = c_r·c_o·v_b; Turbulenzintensität
I_v = k_I/(c_o·ln(z/z_0)); Böengeschwindigkeitsdruck
q_p = (1 + 7·I_v)·½·ρ·v_m². Alternativ die Mischprofile des NA
(Tab. NA.B.2: Binnenland, Küste, Inseln der Nordsee) auf q_b = ½·ρ·v_b².

**Beiwerte**: Wände (Tab. 7.1) mit den Zonen D (Luv), E (Lee), A/B/C
(Seiten, Bänder e/5 und e ab der Luvkante, e = min(b, 2h)); Flachdach
(Tab. 7.2, scharfkantig) mit F/G/H/I; freistehende Wand (Tab. 7.9, Zonen
A–D ab dem freien Ende) und Anzeigetafel (7.4.3, c_f = 1,8); Stäbe:
Rechteck (Bild 7.23, c_f,0 über d/b), scharfkantige Walzprofile (7.7,
c_f,0 = 2,0), Kreiszylinder (Bild 7.28 bzw. Gl. 7.19 mit der Reynoldszahl
Re = b·v/ν, ν = 15·10⁻⁶ m²/s, Rauigkeit k), Fachwerk (Bild 7.33/7.34 über
den Völligkeitsgrad φ); Abminderung ψ_λ für die Schlankheit (Bild 7.36,
Tab. 7.16). Alle Beiwerte lassen sich je Objekt überschreiben.

Die Kennwerte (v_b, q_b, v_m, I_v, q_p über die Höhe, Re, c_f, Resultierende)
stehen im Protokoll und im Bericht - dort mit dem Höhenprofil und der Skizze
der Zonen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

RHO = 1.25            # Luftdichte [kg/m³]
NU = 15e-6            # kinematische Zähigkeit der Luft [m²/s]

#: Windzonen Deutschland, v_b,0 [m/s] (DIN EN 1991-1-4/NA, Tab. NA.A.1)
WINDZONEN = {1: 22.5, 2: 25.0, 3: 27.5, 4: 30.0}

#: Geländekategorien (EN 1991-1-4, Tab. 4.1): z_0 [m], z_min [m]
GELAENDE = {"0": (0.003, 1.0), "I": (0.01, 1.0), "II": (0.05, 2.0), "III": (0.3, 5.0),
            "IV": (1.0, 10.0)}
Z_MAX = 200.0

#: Mischprofile des NA (Tab. NA.B.2): (z-Grenzen, Faktor, Exponent) auf q_b
MISCHPROFILE = {
    "Binnenland": [(7.0, 1.5, 0.0), (50.0, 1.7, 0.37), (300.0, 2.1, 0.24)],
    "Küste und Inseln der Ostsee": [(4.0, 1.8, 0.0), (50.0, 2.3, 0.27), (300.0, 2.6, 0.19)],
    "Inseln der Nordsee": [(2.0, 1.1, 0.0), (50.0, 1.5, 0.19), (300.0, 1.7, 0.16)],
}

#: Zonen der Wände (Tab. 7.1, c_pe,10) - A, B, C Seitenwände; D Luv; E Lee je h/d
CPE_SEITE = {"A": -1.2, "B": -0.8, "C": -0.5}
#: Flachdach scharfkantig (Tab. 7.2, c_pe,10)
CPE_FLACHDACH = {"F": -1.8, "G": -1.2, "H": -0.7, "I": -0.2}
#: Freistehende Wand ohne Eckabschluss, l/h >= 10 (Tab. 7.9, c_p,net)
CP_FREIE_WAND = {"A": 2.3, "B": 1.4, "C": 1.2, "D": 1.2}
CF_SCHILD = 1.8


@dataclass
class Wind:
    """Ein Wind-Lastgenerierer (eine Anströmrichtung, eine Situation)."""
    name: str
    situation: str = ""
    lastfall: str = ""
    zone: int = 2                         # Windzone 1..4 (v_b,0) oder v_b unmittelbar
    v_b: Optional[float] = None           # Basiswindgeschwindigkeit [m/s]; None = aus Zone
    c_dir: float = 1.0
    c_season: float = 1.0
    profil: str = "II"                    # Geländekategorie 0, I, II, III, IV oder Mischprofil
    c_o: float = 1.0                      # Topographiebeiwert
    richtung: list = field(default_factory=lambda: [1.0, 0.0, 0.0])   # Anströmrichtung (horizontal)
    z_boden: Optional[float] = None       # Geländeoberkante [m]; None = Unterkante der Objekte
    flaechen: list = field(default_factory=list)      # Wände und Dächer eines Gebäudes
    freie_waende: list = field(default_factory=list)  # freistehende Wände (Flächen)
    schilder: list = field(default_factory=list)      # Anzeigetafeln (Flächen)
    staebe: list = field(default_factory=list)        # Stäbe mit Nachweis
    c_pi: float = 0.0                     # Innendruckbeiwert (Gebäude), 0 = ohne
    k_rauigkeit: float = 0.2e-3           # Oberflächenrauigkeit k [m] für Zylinder (Stahl 0,2 mm)
    phi: float = 1.0                      # Völligkeitsgrad (Fachwerk); 1 = Vollwand
    fachwerk: bool = False                # Stäbe als Fachwerk (Bild 7.33/7.34)
    cf_vorgabe: Optional[float] = None    # c_f für alle Stäbe erzwingen
    c_scd: float = 1.0                    # Strukturbeiwert c_s·c_d
    kommentar: str = ""
    # -- numerischer Windkanal (Gitter-Boltzmann im Schnitt) ------------------
    verfahren: str = "norm"               # "norm" (DIN EN 1991-1-4) | "windkanal"
    schnittart: str = "grundriss"         # "grundriss" (waagerechter Schnitt) | "aufriss" (lotrecht in Windrichtung)
    z_schnitt: Optional[float] = None     # Höhe des Grundriss-Schnitts [m]; None = 0,6·h über Gelände
    gitter: int = 24                      # Zellen über die Querabmessung des Hindernisses
    re: float = 150.0                     # Reynolds-Zahl des Modells (Stabilität: τ ≥ 0,52)
    schritte: int = 3000                  # Zeitschritte des Windkanals
    lastfall_nr: int = 0                  # Lastfallnummer (0 = nächste freie)

    def windkanal(self) -> bool:
        return str(self.verfahren or "").lower().startswith("wind")

    def bezug(self) -> str:
        t = f"Zone {self.zone}" if self.v_b is None else f"v_b = {self.v_b:g} m/s"
        t += f", {self.profil}, Richtung ({self.richtung[0]:g}, {self.richtung[1]:g})"
        if self.situation:
            t += f" [{self.situation}]"
        return t


# ==========================================================================
# Strömung
# ==========================================================================
def v_basis(w: Wind) -> float:
    v0 = float(w.v_b) if w.v_b is not None else WINDZONEN.get(int(w.zone), 25.0)
    return w.c_dir * w.c_season * v0


def q_basis(w: Wind) -> float:
    return 0.5 * RHO * v_basis(w) ** 2


def k_r(z0: float) -> float:
    return 0.19 * (z0 / 0.05) ** 0.07


def c_r(z: float, kat: str) -> float:
    z0, zmin = GELAENDE[kat]
    z = min(max(float(z), zmin), Z_MAX)
    return k_r(z0) * math.log(z / z0)


def v_m(z: float, w: Wind) -> float:
    """Mittlere Windgeschwindigkeit in der Höhe z (4.3)."""
    if w.profil in GELAENDE:
        return c_r(z, w.profil) * w.c_o * v_basis(w)
    # Mischprofil: v_m aus q_p zurückgerechnet (Böenanteil wie Kategorie II)
    return math.sqrt(2 * q_p(z, w) / RHO / (1 + 7 * I_v(z, w)))


def I_v(z: float, w: Wind, k_I: float = 1.0) -> float:
    """Turbulenzintensität (4.4)."""
    kat = w.profil if w.profil in GELAENDE else "II"
    z0, zmin = GELAENDE[kat]
    z = min(max(float(z), zmin), Z_MAX)
    return k_I / (w.c_o * math.log(z / z0))


def q_p(z: float, w: Wind) -> float:
    """Böengeschwindigkeitsdruck [Pa] in der Höhe z über Gelände (4.5)."""
    if w.profil in GELAENDE:
        vm = v_m(z, w)
        return (1.0 + 7.0 * I_v(z, w)) * 0.5 * RHO * vm ** 2
    stufen = MISCHPROFILE.get(w.profil)
    if not stufen:
        raise ValueError(f"Profil '{w.profil}' unbekannt: {list(GELAENDE) + list(MISCHPROFILE)}")
    qb = q_basis(w)
    z = max(float(z), 0.0)
    for grenze, faktor, exponent in stufen:
        if z <= grenze:
            return faktor * qb * ((max(z, 1e-9) / 10.0) ** exponent if exponent else 1.0)
    grenze, faktor, exponent = stufen[-1]
    return faktor * qb * (grenze / 10.0) ** exponent


# ==========================================================================
# Beiwerte
# ==========================================================================
def _interp_log(x: float, punkte) -> float:
    xs = [p[0] for p in punkte]
    ys = [p[1] for p in punkte]
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    return float(np.interp(math.log(x), np.log(xs), ys))


def cf0_rechteck(d_b: float) -> float:
    """Bild 7.23: c_f,0 scharfkantiger Rechteckquerschnitt über d/b (d in Windrichtung)."""
    return _interp_log(d_b, [(0.1, 2.0), (0.2, 2.0), (0.7, 2.4), (1.0, 2.1), (2.0, 1.65),
                             (5.0, 1.0), (10.0, 0.9), (50.0, 0.9)])


def psi_r(r_b: float) -> float:
    """Bild 7.24: Abminderung für abgerundete Ecken (r/b)."""
    return float(np.clip(1.0 - 2.5 * r_b, 0.5, 1.0))


def reynolds(b: float, v: float) -> float:
    return b * v / NU


def cf0_zylinder(re: float, k_b: float) -> float:
    """Bild 7.28 / Gl. 7.19: c_f,0 des Kreiszylinders über Re und k/b.
    Unterkritisch (Re < 2·10⁵) 1,2; darüber nach Gl. 7.19, mindestens 0,4."""
    if re < 2e5:
        return 1.2
    c = 1.2 + 0.18 * math.log10(10.0 * max(k_b, 1e-7)) / (1.0 + 0.4 * math.log10(re / 1e6))
    return float(np.clip(c, 0.4, 1.2))


def cf0_fachwerk(phi: float, rund: bool = False, re: float = 0.0) -> float:
    """Bild 7.33 (scharfkantig) / 7.34 (Rundstäbe): c_f,0 ebener Fachwerke über φ."""
    phi = float(np.clip(phi, 0.0, 1.0))
    if not rund:
        return _interp_log(max(phi, 0.01), [(0.01, 1.8), (0.2, 1.7), (0.35, 1.6), (0.5, 1.65),
                                            (0.7, 1.8), (1.0, 2.0)])
    if re < 2e5:
        return _interp_log(max(phi, 0.01), [(0.01, 1.2), (0.3, 1.2), (0.6, 1.4), (1.0, 1.6)])
    return _interp_log(max(phi, 0.01), [(0.01, 0.6), (0.3, 0.6), (0.6, 0.8), (1.0, 1.1)])


def schlankheit(laenge: float, b: float) -> float:
    """Wirksame Schlankheit λ nach Tab. 7.16 (Zeile 1: Stäbe, scharfkantige Profile)."""
    if b <= 0:
        return 70.0
    if laenge >= 50.0:
        return min(1.4 * laenge / b, 70.0)
    if laenge < 15.0:
        return min(2.0 * laenge / b, 70.0)
    f = (laenge - 15.0) / 35.0
    return min((2.0 - 0.6 * f) * laenge / b, 70.0)


def psi_lambda(lam: float, phi: float = 1.0) -> float:
    """Bild 7.36: Abminderungsfaktor für die Schlankheit (Endeffekte)."""
    voll = _interp_log(max(lam, 1.0), [(1.0, 0.60), (10.0, 0.70), (70.0, 0.92), (200.0, 1.0)])
    phi = float(np.clip(phi, 0.1, 1.0))
    # zwischen der Kurve φ = 1 und ψ ≈ 0,98 bei φ = 0,1
    return voll + (0.98 - voll) * (1.0 - phi) / 0.9 if phi < 1.0 else voll


def cpe_luv(h_d: float) -> float:
    """Tab. 7.1, Zone D: +0,7 (h/d ≤ 0,25) bis +0,8 (h/d ≥ 1)."""
    return float(np.interp(h_d, [0.25, 1.0], [0.7, 0.8]))


def cpe_lee(h_d: float) -> float:
    """Tab. 7.1, Zone E: −0,3 (h/d ≤ 0,25), −0,5 (h/d = 1), −0,7 (h/d ≥ 5)."""
    return float(np.interp(h_d, [0.25, 1.0, 5.0], [-0.3, -0.5, -0.7]))


def zone_seite(x: float, e: float) -> str:
    """Seitenwand: A (0 … e/5), B (e/5 … e), C (> e) ab der Luvkante."""
    if x < e / 5.0:
        return "A"
    return "B" if x < e else "C"


def zone_flachdach(x: float, y_rand: float, e: float) -> str:
    """Flachdach (Bild 7.6): F an den Luvecken (bis e/4 vom Seitenrand, e/10 tief),
    G am Luvrand, H bis e/2, I dahinter."""
    if x < e / 10.0:
        return "F" if y_rand < e / 4.0 else "G"
    return "H" if x < e / 2.0 else "I"


def zone_freie_wand(x_ende: float, h: float) -> str:
    """Freistehende Wand (Tab. 7.9): A (0 … 0,3h), B (… 2h), C (… 4h), D (> 4h) ab dem freien Ende."""
    if x_ende < 0.3 * h:
        return "A"
    if x_ende < 2.0 * h:
        return "B"
    return "C" if x_ende < 4.0 * h else "D"


# ==========================================================================
# Geometrie der Objekte
# ==========================================================================
def _richtung(w: Wind) -> np.ndarray:
    d = np.asarray(w.richtung, float)[:3].copy()
    d[2] = 0.0
    n = float(np.linalg.norm(d))
    if n <= 0:
        raise ValueError("Anströmrichtung ist null (horizontal angeben)")
    return d / n


def _flaechenknoten(model, name: str) -> set:
    f = model.flaechen.get(name)
    kn = set()
    if f is None:
        return kn
    for e in f.elemente or []:
        if 0 <= int(e) < len(model.elements):
            kn.update(int(n) for n in model.elements[int(e)].nodes)
    try:
        kn.update(int(n) for n in f.randknoten(model))
    except Exception:                    # noqa: BLE001
        pass
    return kn


def _flaechennormale(model, name: str):
    """Mittlere Aussennormale der Elemente einer Fläche (Knotenreihenfolge)."""
    from .elements import shell as sh
    f = model.flaechen.get(name)
    if f is None:
        return None
    n = np.zeros(3)
    for e in f.elemente or []:
        el = model.elements[int(e)]
        if el.typ not in ("shell3", "shell4"):
            continue
        X = model.nodes[[int(k) for k in el.nodes]]
        T3, _xy, A = sh.shell_frame(X[0], X[1], X[2])
        n += T3[2] * A
    L = float(np.linalg.norm(n))
    return n / L if L > 0 else None


def gebaeude(w: Wind, model) -> dict:
    """Abmessungen des Gebäudes aus den Flächen: Höhe h, Breite b (quer),
    Tiefe d (längs), Geländeoberkante z_0, Luvkante x_0."""
    d = _richtung(w)
    quer = np.array([-d[1], d[0], 0.0])
    kn = set()
    for name in list(w.flaechen) + list(w.freie_waende) + list(w.schilder):
        kn |= _flaechenknoten(model, name)
    for name in w.staebe:
        mem = model.members.get(name)
        if mem is not None:
            for e in mem.elements:
                if 0 <= int(e) < len(model.elements):
                    kn.update(int(n) for n in model.elements[int(e)].nodes)
    if not kn:
        raise ValueError("Keine Flächen oder Stäbe gewählt")
    P = model.nodes[sorted(kn)]
    s = P @ d                       # Koordinate in Windrichtung
    t = P @ quer                    # quer
    z_boden = float(P[:, 2].min()) if w.z_boden is None else float(w.z_boden)
    h = float(P[:, 2].max()) - z_boden
    return {"h": max(h, 1e-6), "b": float(np.ptp(t)) or 1e-6, "d": float(np.ptp(s)) or 1e-6,
            "z_boden": z_boden, "x_luv": float(s.min()), "t_min": float(t.min()),
            "t_max": float(t.max()), "richtung": d.tolist(), "quer": quer.tolist()}


def rollen(w: Wind, model, geo: dict) -> dict:
    """Je Fläche: luv, lee, seite, dach, freie_wand, schild - aus der Normalen."""
    d = np.asarray(geo["richtung"], float)
    out = {}
    for name in w.flaechen:
        n = _flaechennormale(model, name)
        if n is None:
            out[name] = "seite"
            continue
        if abs(n[2]) > 0.7:
            out[name] = "dach"
        else:
            c = float(n @ d)
            out[name] = "luv" if c < -0.5 else ("lee" if c > 0.5 else "seite")
    for name in w.freie_waende:
        out[name] = "freie_wand"
    for name in w.schilder:
        out[name] = "schild"
    return out


# ==========================================================================
# Druck an einem Punkt (Objektlast "wind")
# ==========================================================================
def beiwert_am_punkt(param: dict, geo: dict, rolle: str, punkt) -> tuple:
    """(c_pe oder c_f, Zone) der Rolle am Punkt."""
    d = np.asarray(geo["richtung"], float)
    quer = np.asarray(geo["quer"], float)
    P = np.asarray(punkt, float)
    h, b, t = geo["h"], geo["b"], geo["d"]
    e = min(b, 2.0 * h)
    x = float(P @ d) - geo["x_luv"]                   # Abstand von der Luvkante
    y_rand = min(float(P @ quer) - geo["t_min"], geo["t_max"] - float(P @ quer))
    c_pi = float(param.get("c_pi", 0.0) or 0.0)
    if rolle == "luv":
        return cpe_luv(h / t) - c_pi, "D"
    if rolle == "lee":
        return cpe_lee(h / t) - c_pi, "E"
    if rolle == "seite":
        z = zone_seite(x, e)
        return CPE_SEITE[z] - c_pi, z
    if rolle == "dach":
        z = zone_flachdach(x, y_rand, e)
        return CPE_FLACHDACH[z] - c_pi, z
    if rolle == "freie_wand":
        x_ende = min(float(P @ quer) - geo["t_min"], geo["t_max"] - float(P @ quer))
        z = zone_freie_wand(x_ende, h)
        return CP_FREIE_WAND[z], z
    if rolle == "schild":
        return CF_SCHILD, "Schild"
    return 0.0, "–"


#: Entpackte c_p-Felder je Objektlast (siehe wasserdruck._FELDER)
_FELDER: dict = {}


def _feld_aus_verlauf(verlauf: dict):
    from . import stroemung as st
    key = (id(verlauf), (verlauf.get("feld") or {}).get("stempel"))
    hit = _FELDER.get(key)
    if hit is None:
        hit = st.feld_entpacken(verlauf["feld"])
        if len(_FELDER) > 12:
            _FELDER.clear()
        _FELDER[key] = hit
    return hit


def druck_aus_verlauf(verlauf: dict, punkt, normale=None, beidseitig: bool = False) -> float:
    """p [Pa] für eine Geometrielast mit verlauf["art"] == "wind": positiv drückt
    in den Körper (gegen die Außennormale), negativ ist Sog.

    Mit c_p-Feld des Windkanals (``verlauf["feld"]``) wird der Beiwert vor
    der Elementseite abgetastet (dünne Schale: netto aus beiden Seiten) und
    mit dem Böengeschwindigkeitsdruck q_p(z) der Norm skaliert; sonst die
    Zonenbeiwerte der Norm."""
    from . import stroemung as st
    param = verlauf.get("param") or {}
    geo = verlauf.get("geometrie") or {}
    w = _param(param)
    z = float(np.asarray(punkt, float)[2]) - float(geo.get("z_boden", 0.0))
    if verlauf.get("feld"):
        schnitt, cp, fluid, _block = _feld_aus_verlauf(verlauf)
        c = float(st.wert_am_punkt(cp, fluid, schnitt, punkt, normale, beidseitig)) - float(w.c_pi)
        return w.c_scd * c * q_p(max(z, 0.0), w)
    c, _zone = beiwert_am_punkt(param, geo, verlauf.get("rolle", ""), punkt)
    return w.c_scd * c * q_p(max(z, 0.0), w)


# ==========================================================================
# Numerischer Windkanal (Gitter-Boltzmann im Schnitt)
# ==========================================================================
def _stab_vierecke(model, w: Wind, geo: dict) -> list:
    """Die Stäbe als schmale Vierecke (Achse ± b_ref/2 quer zur Achse in der
    Ebene) - so stehen Stützen und Riegel als Hindernis im Windkanal."""
    tris = []
    for name in w.staebe:
        mem = model.members.get(name)
        if mem is None:
            continue
        try:
            b = stabbeiwert(w, model, name, geo)["b_ref"]
        except Exception:                    # noqa: BLE001
            b = 0.2
        for e in mem.elements or []:
            if not 0 <= int(e) < len(model.elements):
                continue
            el = model.elements[int(e)]
            A, B = model.nodes[int(el.nodes[0])], model.nodes[int(el.nodes[-1])]
            ab = B - A
            L = float(np.linalg.norm(ab))
            if L < 1e-9:
                continue
            t = ab / L
            # zwei Querrichtungen, damit das Viereck in jeder Schnittebene Breite hat
            for q in (np.array([0.0, 0.0, 1.0]), np.array([-t[1], t[0], 0.0])):
                q = q - t * float(q @ t)
                n = float(np.linalg.norm(q))
                if n < 1e-9:
                    continue
                q = q / n * 0.5 * b
                tris.append(np.array([A - q, B - q, B + q]))
                tris.append(np.array([A - q, B + q, A + q]))
    return tris


def windkanal_rechnen(w: Wind, model, geo: dict, fortschritt=None) -> dict:
    """Die Strömung um die Flächen und Stäbe im Schnitt rechnen (Gitter-
    Boltzmann): Rückgabe {"schnitt", "cp", "ux", "uz", "fluid", "block",
    "re", "tau", "schritte", "aufriss", "z_schnitt", "gitter"}."""
    from . import stroemung as st
    d = np.asarray(geo["richtung"], float)
    quer = np.asarray(geo["quer"], float)
    tris = st.objekt_dreiecke(model, list(w.flaechen) + list(w.freie_waende) + list(w.schilder))
    tris += _stab_vierecke(model, w, geo)
    if not tris:
        raise ValueError("Keine Flächen oder Stäbe für den Windkanal")
    P = np.concatenate([np.asarray(t, float) for t in tris]).reshape(-1, 3)
    aufriss = str(w.schnittart or "").lower().startswith("auf")
    z_boden = float(geo["z_boden"])
    c = P.mean(axis=0)
    if aufriss:
        ex, ez = d, np.array([0.0, 0.0, 1.0])
        L = max(float(geo["h"]), 1e-3)
        s0, s1 = float((P @ d).min()), float((P @ d).max())
        z_schnitt = None
        x0, x1 = s0 - 3.0 * L, s1 + 8.0 * L
        z0, z1 = z_boden, z_boden + 4.0 * L
    else:
        ex, ez = d, quer
        L = max(float(geo["b"]), 1e-3)
        s0, s1 = float((P @ d).min()), float((P @ d).max())
        t0, t1 = float((P @ quer).min()), float((P @ quer).max())
        z_schnitt = float(w.z_schnitt) if w.z_schnitt is not None else z_boden + 0.6 * float(geo["h"])
        x0, x1 = s0 - 3.0 * L, s1 + 8.0 * L
        z0, z1 = t0 - 3.0 * L, t1 + 3.0 * L
    n_g = min(120, max(6, int(w.gitter or 24)))
    h = L / n_g
    nx, nz = int(math.ceil((x1 - x0) / h)), int(math.ceil((z1 - z0) / h))
    if nx * nz > 80000:
        f = math.sqrt(nx * nz / 80000.0)
        h *= f
        nx, nz = int(math.ceil((x1 - x0) / h)), int(math.ceil((z1 - z0) / h))
    ursprung = c + (x0 - float(c @ ex)) * ex + (z0 - float(c @ ez)) * ez
    if not aufriss:
        ursprung = ursprung + (z_schnitt - float(ursprung[2])) * np.array([0.0, 0.0, 1.0])
    schnitt = st.Schnitt(ursprung, ex, ez, h, nx, nz)
    st._melden(fortschritt, 0.0, f"Wind {w.name}: Windkanal {nx} × {nz} Zellen")
    block = st.rastern(schnitt, tris,
                       fortschritt=(lambda a_, t_: fortschritt(0.02 + 0.13 * a_, t_)) if fortschritt else None,
                       text=f"Wind {w.name}: Hindernisse rastern")
    block = st.verdicken(block)
    if not block.any():
        raise ValueError("Die Hindernisse liegen nicht im Schnitt - Schnitthöhe prüfen")
    lb = st.gitter_boltzmann(block, u_lb=0.08, re=float(w.re or 150.0), schritte=int(w.schritte or 3000),
                             boden=aufriss,
                             fortschritt=(lambda a_, t_: fortschritt(0.15 + 0.8 * a_, t_)) if fortschritt else None)
    return {"schnitt": schnitt, "cp": lb["cp"], "ux": lb["ux"], "uz": lb["uz"], "fluid": ~lb["block"],
            "block": lb["block"], "re": lb["re"], "tau": lb["tau"], "schritte": lb["schritte"],
            "aufriss": aufriss, "z_schnitt": z_schnitt, "gitter": (nx, nz, h), "L": L}


def _feld_passt(wk: dict, normale, quer) -> bool:
    """Liegt die Fläche mit ihrer Normale in der Schnittebene? Dann kommt ihr
    Druck aus dem Windkanal, sonst aus den Zonen der Norm (Dächer im
    Grundriss, Seitenwände im Aufriss)."""
    if normale is None:
        return False
    n = np.asarray(normale, float)
    if wk["aufriss"]:
        return abs(float(n @ np.asarray(quer, float))) <= 0.7
    return abs(float(n[2])) <= 0.7


def abschirmung(wk: dict, punkt) -> float:
    """(v/v_∞)² an einem Punkt des Windkanals - Verschattung eines Stabes im
    Nachlauf; 1,0 ausserhalb des Feldes."""
    from . import stroemung as st
    v = np.sqrt(wk["ux"] ** 2 + wk["uz"] ** 2)
    v[~wk["fluid"]] = np.nan
    r = st.wert_am_punkt(v, wk["fluid"], wk["schnitt"], punkt, None, False)
    if r <= 0.0:
        return 1.0
    return float(min(1.5, r) ** 2)


def windkanal_svg(w: Wind, kw: dict, breite: int = 620) -> tuple:
    """Bilder des Windkanals fuer den Bericht: (c_p-Feld, Geschwindigkeitsfeld)."""
    from . import stroemung as st
    wk = kw.get("_wk")
    if not wk:
        return "", ""
    sch = wk["schnitt"]
    art = "Aufriss" if wk["aufriss"] else f"Grundriss bei z = {wk['z_schnitt']:.2f} m"
    cp = st.feld_svg(sch, wk["cp"], wk["fluid"], wk["block"], "wind", breite=breite,
                     titel=f"Wind {w.name}: Druckbeiwert c_p im Windkanal ({art})", einheit="c_p", faktor=1.0,
                     grenzen=(-1.5, 1.0))
    v = np.sqrt(wk["ux"] ** 2 + wk["uz"] ** 2)
    v[~wk["fluid"]] = np.nan
    vs = st.feld_svg(sch, v, wk["fluid"], wk["block"], "wasser", breite=breite,
                     titel=f"Wind {w.name}: Geschwindigkeit v/v∞ (Nachlauf, Verschattung)", einheit="v/v∞",
                     faktor=1.0, grenzen=(0.0, 1.3))
    return cp, vs


def _param(p) -> Wind:
    if isinstance(p, Wind):
        return p
    felder = set(Wind.__dataclass_fields__)
    return Wind(**{k: v for k, v in dict(p).items() if k in felder})


# ==========================================================================
# Stäbe
# ==========================================================================
def stabbeiwert(w: Wind, model, name: str, geo: dict) -> dict:
    """c_f, b_ref, Re, ψ_λ und w(z) an beiden Enden eines Stabes."""
    mem = model.members[name]
    els = [int(e) for e in mem.elements if 0 <= int(e) < len(model.elements)]
    if not els:
        raise ValueError(f"Stab {name} ohne Elemente")
    e0 = model.elements[els[0]]
    sec = model.sections[e0.sec]
    d = np.asarray(geo["richtung"], float)
    n1 = model.nodes[int(e0.nodes[0])]
    n2 = model.nodes[int(model.elements[els[-1]].nodes[-1])]
    L = float(sum(model.element_length(e) for e in els))
    achse = n2 - n1
    achse = achse / (np.linalg.norm(achse) or 1.0)
    # Querabmessung gegen den Wind: bei Stab quer zum Wind das größere Maß
    hh, bb = float(sec.h or 0.0), float(sec.b or 0.0)
    b_ref = max(hh, bb) if max(hh, bb) > 0 else 2.0 * math.sqrt(max(sec.A, 1e-9) / math.pi)
    z1 = float(n1[2]) - geo["z_boden"]
    z2 = float(n2[2]) - geo["z_boden"]
    zm = 0.5 * (z1 + z2)
    qm = q_p(max(zm, 0.0), w)
    v = math.sqrt(2.0 * qm / RHO)
    re = reynolds(b_ref, v)
    lam = schlankheit(L, b_ref)
    psi = psi_lambda(lam, w.phi if w.fachwerk else 1.0)
    typ = (sec.typ or "").upper()
    if w.cf_vorgabe:
        cf0, art = float(w.cf_vorgabe), "Vorgabe"
    elif w.fachwerk:
        cf0, art = cf0_fachwerk(w.phi, typ in ("CHS", "CIRCLE"), re), "Fachwerk (Bild 7.33/7.34)"
    elif typ in ("CHS", "CIRCLE"):
        cf0, art = cf0_zylinder(re, w.k_rauigkeit / b_ref), "Kreiszylinder (Gl. 7.19)"
    elif typ in ("RHS", "RECT", "POLY", "COMPOSITE"):
        d_b = (min(hh, bb) / max(hh, bb)) if min(hh, bb) > 0 else 1.0
        cf0, art = cf0_rechteck(d_b) * psi_r(float(sec.r or 0.0) / max(b_ref, 1e-9)), "Rechteck (Bild 7.23)"
    else:
        cf0, art = 2.0, "scharfkantiges Profil (7.7)"
    cf = cf0 * psi
    # Anteil quer zur Stabachse: Wind parallel zum Stab belastet ihn nicht
    sin = math.sqrt(max(0.0, 1.0 - float(achse @ d) ** 2))
    w1 = w.c_scd * cf * q_p(max(z1, 0.0), w) * b_ref * sin
    w2 = w.c_scd * cf * q_p(max(z2, 0.0), w) * b_ref * sin
    return {"stab": name, "typ": typ or "frei", "b_ref": b_ref, "L": L, "lambda": lam, "psi": psi,
            "Re": re, "cf0": cf0, "cf": cf, "art": art, "w1": w1, "w2": w2, "z1": z1, "z2": z2,
            "F": 0.5 * (w1 + w2) * L}


# ==========================================================================
# Lasten erzeugen und Kennwerte
# ==========================================================================
def kennwerte(w: Wind, model=None, geo: dict = None) -> dict:
    """Strömungskennwerte und Höhenprofil."""
    out = {"v_b": v_basis(w), "q_b": q_basis(w), "profil": w.profil, "rho": RHO}
    if geo is None and model is not None:
        try:
            geo = gebaeude(w, model)
        except ValueError:
            geo = None
    h = geo["h"] if geo else 10.0
    hoehen = sorted(set([1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0] + [round(h, 2)]))
    hoehen = [z for z in hoehen if z <= max(h, 10.0) + 1e-9] or [h]
    out["profil_tabelle"] = [(z, v_m(z, w), I_v(z, w), q_p(z, w)) for z in hoehen]
    out["q_p_h"] = q_p(h, w)
    out["v_m_h"] = v_m(h, w)
    out["I_v_h"] = I_v(h, w)
    if geo:
        out.update({k: geo[k] for k in ("h", "b", "d", "z_boden")})
        out["e"] = min(geo["b"], 2.0 * geo["h"])
        out["h_d"] = geo["h"] / geo["d"]
        out["cpe_D"], out["cpe_E"] = cpe_luv(out["h_d"]), cpe_lee(out["h_d"])
    return out


def lasten_erzeugen(model, w: Wind, fortschritt=None) -> dict:
    """Objektlasten an Flächen und Linienlasten auf Stäbe schreiben (alte des
    Generierers entfernen), verteilen; Rückgabe: Kennwerte samt Zahlen. Mit
    ``verfahren = "windkanal"`` läuft zuerst die Strömungsrechnung
    (``fortschritt(anteil, text) -> bool``; False bricht ab, das Modell bleibt
    unverändert)."""
    from .model import GRUNDSTELLUNG, ACTION_CATEGORIES
    from . import stroemung as st
    import uuid
    fehlt = [n for n in list(w.flaechen) + list(w.freie_waende) + list(w.schilder)
             if n not in model.flaechen] + [n for n in w.staebe if n not in model.members]
    if fehlt:
        raise ValueError("Unbekannt: " + ", ".join(fehlt))
    if w.situation and w.situation not in model.situationsnamen():
        raise ValueError(f"Situation '{w.situation}' unbekannt")
    geo = gebaeude(w, model)
    roll = rollen(w, model, geo)
    kw = kennwerte(w, model, geo)
    wk = None
    feld = None
    if w.windkanal():
        wk = windkanal_rechnen(w, model, geo, fortschritt=fortschritt)
        cp = wk["cp"]
        kw["windkanal"] = {"re": wk["re"], "tau": wk["tau"], "schritte": wk["schritte"], "gitter": wk["gitter"],
                           "aufriss": wk["aufriss"], "z_schnitt": wk["z_schnitt"],
                           "cp_min": float(np.nanmin(cp)) if np.isfinite(cp).any() else 0.0,
                           "cp_max": float(np.nanmax(cp)) if np.isfinite(cp).any() else 0.0}
        kw["_wk"] = wk
        feld = st.feld_packen(wk["schnitt"], cp, wk["fluid"], wk["block"], nachkomma=3,
                              aufriss=bool(wk["aufriss"]), stempel=uuid.uuid4().hex)
        st._melden(fortschritt, 0.96, f"Wind {w.name}: Lasten auf das Netz")
    if not w.lastfall:
        w.lastfall = f"Wind {w.name}"
    for lc in model.load_cases.values():
        lc.geometrielasten = [gl for gl in lc.geometrielasten
                              if not (gl.verlauf.get("art") == "wind" and gl.verlauf.get("name") == w.name)]
        lc.linienlasten = [ll for ll in lc.linienlasten if not (ll.kommentar or "").startswith(f"Wind {w.name}:")]
    if w.lastfall not in model.load_cases:
        model.add_load_case(w.lastfall, "W" if "W" in ACTION_CATEGORIES else "Q",
                            f"Wind {w.name}", activate=False)
    lc = model.load_cases[w.lastfall]
    lc.situation = "" if w.situation == GRUNDSTELLUNG else w.situation
    if not getattr(lc, "nummer", 0):
        lc.nummer = int(w.lastfall_nr) if int(w.lastfall_nr or 0) > 0 else model.naechste_lastfallnummer()
    param = asdict(w)
    n_obj = 0
    zonen: dict = {}
    aus_feld: list = []
    for name, rolle in roll.items():
        verlauf = {"art": "wind", "name": w.name, "param": param, "geometrie": geo, "rolle": rolle}
        if feld is not None and _feld_passt(wk, _flaechennormale(model, name), geo["quer"]):
            verlauf["feld"] = feld
            aus_feld.append(name)
        model.add_geometrielast(name, 0.0, art="flaeche", richtung=None, case=w.lastfall, verlauf=verlauf)
        n_obj += 1
        zonen[name] = rolle
    staebe = []
    for name in w.staebe:
        sb = stabbeiwert(w, model, name, geo)
        d = np.asarray(geo["richtung"], float)
        faktor = 1.0
        if wk is not None:
            mem = model.members[name]
            kn = [int(n) for e in mem.elements for n in model.elements[int(e)].nodes
                  if 0 <= int(e) < len(model.elements)]
            if kn:
                faktor = abschirmung(wk, model.nodes[kn].mean(axis=0))
        sb["abschirmung"] = faktor
        ll = model.add_linienlast(name, (sb["w1"] * faktor * d).tolist(), art="stab",
                                  q2=(sb["w2"] * faktor * d).tolist(), system="global", case=w.lastfall)
        ll.kommentar = f"Wind {w.name}: c_f = {sb['cf']:.2f}, b_ref = {sb['b_ref']:.3f} m" \
            + (f", Windkanal (v/v∞)² = {faktor:.2f}" if wk is not None else "")
        staebe.append(sb)
    model.winde[w.name] = w
    n_elem = model.lasten_verteilen()
    kw.update({"rollen": zonen, "staebe": staebe, "objektlasten": n_obj, "elementlasten": n_elem,
               "lastfall": w.lastfall, "lastfall_nr": int(getattr(lc, "nummer", 0) or 0),
               "aus_feld": aus_feld, "verfahren": "windkanal" if wk is not None else "norm"})
    kw["kontrolle"] = kontrollsumme(model, w)
    st._melden(fortschritt, 1.0, f"Wind {w.name}: {n_elem} Elementlasten")
    return kw


def kontrollsumme(model, w: Wind) -> dict:
    """Summe der erzeugten Flächen-Elementlasten (Kraftvektor) und der Stablasten."""
    from .elements import shell as sh
    F = np.zeros(3)
    n = 0
    lc = model.load_cases.get(w.lastfall)
    if lc is None:
        return {"F": F.tolist(), "n": 0, "betrag": 0.0, "F_staebe": 0.0}
    for fl in lc.face_loads:
        if not getattr(fl, "_geo", False):
            continue
        e = model.elements[int(fl.elem)]
        if e.typ not in ("shell3", "shell4"):
            continue
        X = model.nodes[[int(k) for k in e.nodes]]
        tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
        A, nrm = 0.0, None
        for t in tris:
            T3, _xy, At = sh.shell_frame(X[t[0]], X[t[1]], X[t[2]])
            A += At
            nrm = T3[2]
        F += fl.p * A * (-nrm)          # p positiv drueckt gegen die Normale
        n += 1
    F_st = 0.0
    for bl in lc.beam_loads:
        if getattr(bl, "_geo", False):
            L = model.element_length(int(bl.elem))
            q1 = np.asarray(bl.q, float)
            q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
            a = float(getattr(bl, "a", 0.0) or 0.0)
            b = L if getattr(bl, "b", None) is None else float(bl.b)
            F_st += float(np.linalg.norm(0.5 * (q1 + q2))) * (b - a)
    return {"F": F.tolist(), "n": n, "betrag": float(np.linalg.norm(F)), "F_staebe": F_st}


# ==========================================================================
# Erläuterung und Skizze
# ==========================================================================
def erlaeuterung(w: Wind, kw: dict) -> list:
    z = []
    z.append(f"Basiswindgeschwindigkeit v_b = c_dir·c_season·v_b,0 = {kw['v_b']:.1f} m/s "
             + (f"(Windzone {w.zone})" if w.v_b is None else "(Vorgabe)")
             + f", Basisgeschwindigkeitsdruck q_b = ½·ρ·v_b² = {kw['q_b']:.1f} N/m² (ρ = {RHO} kg/m³).")
    if w.profil in GELAENDE:
        z0, zmin = GELAENDE[w.profil]
        z.append(f"Geländekategorie {w.profil} (z_0 = {z0:g} m, z_min = {zmin:g} m): Rauigkeitsbeiwert "
                 f"c_r(z) = k_r·ln(z/z_0) mit k_r = 0,19·(z_0/z_0,II)^0,07 = {k_r(z0):.3f}, "
                 f"v_m = c_r·c_o·v_b, Turbulenzintensität I_v = 1/(c_o·ln(z/z_0)), "
                 f"Böengeschwindigkeitsdruck q_p = (1 + 7·I_v)·½·ρ·v_m² (DIN EN 1991-1-4, 4.3 bis 4.5).")
    else:
        z.append(f"Mischprofil „{w.profil}“ des Nationalen Anhangs (Tab. NA.B.2): q_p(z) stufenweise "
                 f"als Vielfaches von q_b.")
    if "h" in kw:
        z.append(f"Bezugshöhe h = {kw['h']:.2f} m über Gelände (z = {kw['z_boden']:g} m): "
                 f"v_m = {kw['v_m_h']:.1f} m/s, I_v = {kw['I_v_h']:.3f}, q_p = {kw['q_p_h']:.1f} N/m². "
                 f"Gebäude b = {kw['b']:.2f} m quer, d = {kw['d']:.2f} m längs zur Anströmung "
                 f"({w.richtung[0]:g}, {w.richtung[1]:g}); e = min(b, 2h) = {kw['e']:.2f} m, "
                 f"h/d = {kw['h_d']:.2f}: c_pe,D = {kw['cpe_D']:+.2f} (Luv), c_pe,E = {kw['cpe_E']:+.2f} (Lee); "
                 f"Seitenwände A/B/C = −1,2/−0,8/−0,5 in Bändern e/5 und e ab der Luvkante; Flachdach "
                 f"F/G/H/I = −1,8/−1,2/−0,7/−0,2 (Tab. 7.1, 7.2)."
                 + (f" Innendruck c_pi = {w.c_pi:+g} abgezogen." if w.c_pi else ""))
    if kw.get("staebe"):
        for sb in kw["staebe"]:
            z.append(f"Stab {sb['stab']} ({sb['typ']}, b_ref = {sb['b_ref']:.3f} m, L = {sb['L']:.2f} m): "
                     f"{sb['art']} c_f,0 = {sb['cf0']:.2f}, λ = {sb['lambda']:.1f}, ψ_λ = {sb['psi']:.2f}, "
                     f"c_f = {sb['cf']:.2f}, Re = {sb['Re']:.2e}; w = c_f·q_p·b_ref = {sb['w1']:.1f} … "
                     f"{sb['w2']:.1f} N/m (z = {sb['z1']:.1f} … {sb['z2']:.1f} m), F = {sb['F'] / 1e3:.2f} kN.")
    if w.c_scd != 1.0:
        z.append(f"Strukturbeiwert c_s·c_d = {w.c_scd:g}.")
    wk = kw.get("windkanal")
    if wk:
        nx, nz, h = wk["gitter"]
        z.append(f"Numerischer Windkanal: Gitter-Boltzmann-Verfahren (D2Q9, BGK) im "
                 + ("lotrechten Schnitt in Windrichtung (Aufriss, Boden als Wand)" if wk["aufriss"]
                    else f"waagerechten Schnitt bei z = {wk['z_schnitt']:.2f} m (Grundriss)")
                 + f", Gitter {nx} × {nz} (Zelle {h:.3g} m), {wk['schritte']} Zeitschritte, Modell-Reynolds-Zahl "
                   f"Re = {wk['re']:.0f} (τ = {wk['tau']:.3f}); der Druck ist über die letzten 40 % der Schritte "
                   f"gemittelt. Druckbeiwerte c_p = (p − p∞)/(½·ρ·v∞²) von {wk['cp_min']:+.2f} bis "
                   f"{wk['cp_max']:+.2f}; sie ersetzen die Zonenbeiwerte der Norm auf den Flächen, die in der "
                   f"Schnittebene liegen (" + (", ".join(kw.get("aus_feld", [])) or "keine") + "), und werden mit "
                   f"q_p(z) skaliert. Stäbe im Nachlauf tragen (v/v∞)² als Abschirmung. Nachlauf, "
                   f"Wirbelablösung und Verschattung kommen aus der Rechnung; die Reynolds-Zahl ist die des "
                   f"Modells, nicht die des Bauwerks - die Beiwerte sind qualitativ und gegen die Norm zu "
                   f"prüfen.")
    return z


def skizze_svg(w: Wind, kw: dict, breite: int = 620, hoehe: int = 360) -> str:
    """Links das Höhenprofil q_p(z), rechts der Grundriss mit Anströmung und Zonen."""
    h = kw.get("h", 10.0)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{breite}" height="{hoehe}" '
         f'viewBox="0 0 {breite} {hoehe}" font-family="sans-serif" font-size="11">',
         f'<rect width="{breite}" height="{hoehe}" fill="#fff"/>']
    # Hoehenprofil
    x0, y0, W, H = 50, hoehe - 40, 200, hoehe - 80
    zmax = max(h, 10.0) * 1.1
    zz = np.linspace(0.0, zmax, 60)
    qq = np.array([q_p(z, w) for z in zz])
    qmax = float(qq.max()) or 1.0
    s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0 + W}" y2="{y0}" stroke="#666"/>')
    s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0 - H}" stroke="#666"/>')
    pts = " ".join(f"{x0 + q / qmax * W:.1f},{y0 - z / zmax * H:.1f}" for q, z in zip(qq, zz))
    s.append(f'<polyline points="{pts}" fill="none" stroke="#1467c6" stroke-width="2"/>')
    s.append(f'<text x="{x0 + W - 4}" y="{y0 + 14}" text-anchor="end">q_p [N/m²] bis {qmax:.0f}</text>')
    s.append(f'<text x="{x0 - 4}" y="{y0 - H + 4}" text-anchor="end">z</text>')
    yh = y0 - h / zmax * H
    s.append(f'<line x1="{x0}" y1="{yh:.1f}" x2="{x0 + W}" y2="{yh:.1f}" stroke="#e5701c" stroke-dasharray="4 3"/>')
    s.append(f'<text x="{x0 + 4}" y="{yh - 16:.1f}" fill="#e5701c" font-size="10">h = {h:.1f} m: q_p = {kw.get("q_p_h", 0):.0f} N/m²</text>')
    s.append(f'<text x="{x0 + 4}" y="{yh - 4:.1f}" fill="#e5701c" font-size="10">v_m = {kw.get("v_m_h", 0):.1f} m/s, I_v = {kw.get("I_v_h", 0):.2f}</text>')
    s.append(f'<text x="{x0}" y="22">Höhenprofil {w.profil}, v_b = {kw["v_b"]:.1f} m/s</text>')
    # Grundriss
    if "b" in kw:
        gx, gy = 330, 60
        GW, GH = 240, 200
        d_, b_ = kw["d"], kw["b"]
        sc = min(GW / d_, GH / b_) * 0.75
        rx, ry = gx + 60, gy + (GH - b_ * sc) / 2
        e = kw["e"]
        s.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{d_ * sc:.1f}" height="{b_ * sc:.1f}" fill="#eaf2fc" stroke="#1d2731" stroke-width="1.5"/>')
        # Zonen A/B/C entlang der Seiten
        for x_a, x_b, zone, farbe in ((0, e / 5, "A", "#c62828"), (e / 5, e, "B", "#e5701c"), (e, d_, "C", "#b7791f")):
            if x_b <= x_a or x_a >= d_:
                continue
            x_b = min(x_b, d_)
            for yy in (ry - 8, ry + b_ * sc):
                s.append(f'<rect x="{rx + x_a * sc:.1f}" y="{yy:.1f}" width="{(x_b - x_a) * sc:.1f}" height="8" fill="{farbe}" opacity="0.7"/>')
            s.append(f'<text x="{rx + (x_a + x_b) / 2 * sc:.1f}" y="{ry - 12:.1f}" text-anchor="middle" fill="{farbe}">'
                     f'{zone} {CPE_SEITE[zone]:+.1f}</text>')
        s.append(f'<text x="{rx - 6:.1f}" y="{ry + b_ * sc / 2 + 4:.1f}" text-anchor="end" fill="#1467c6">D {kw["cpe_D"]:+.2f}</text>')
        s.append(f'<text x="{rx + d_ * sc + 6:.1f}" y="{ry + b_ * sc / 2 + 4:.1f}" fill="#1467c6">E {kw["cpe_E"]:+.2f}</text>')
        s.append('<defs><marker id="pw" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
                 '<path d="M0,0 L8,4 L0,8 z" fill="#1467c6"/></marker></defs>')
        for k in range(3):
            yy = ry + b_ * sc * (0.25 + 0.25 * k)
            s.append(f'<line x1="{rx - 108:.1f}" y1="{yy:.1f}" x2="{rx - 64:.1f}" y2="{yy:.1f}" stroke="#1467c6" stroke-width="2" marker-end="url(#pw)"/>')
        s.append(f'<text x="{rx - 108:.1f}" y="{ry + b_ * sc * 0.25 - 10:.1f}" fill="#1467c6">Wind</text>')
        s.append(f'<text x="{gx}" y="22">Grundriss: b = {b_:.1f} m, d = {d_:.1f} m, e = {e:.1f} m</text>')
        s.append(f'<text x="{gx}" y="{gy + GH + 40}" font-size="10">Dach: F −1.8 (Luvecken), G −1.2 (Luvrand bis e/10),</text>')
        s.append(f'<text x="{gx}" y="{gy + GH + 54}" font-size="10">H −0.7 (bis e/2), I −0.2 (Rest)</text>')
        s.append(f'<text x="{gx}" y="{gy + GH + 68}" font-size="10">Wände: A/B/C seitlich (Bänder), D Luv, E Lee</text>')
    s.append('</svg>')
    return "\n".join(s)
