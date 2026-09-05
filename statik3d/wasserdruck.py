"""
Lastgenerierer Wasserdruck: statisch und dynamisch, überströmt und unterströmt.

Ein :class:`Wasserdruck` beschreibt je **Situation** einen Verschluss (Schütz,
Klappe, Segment): die benetzten Flächen (Haut), die Dichtungslinie (unten),
die Wasserstände Ober- und Unterwasser und - wenn Wasser über die Oberkante
oder unter der Unterkante hindurch strömt - die Angaben zum Strömungsverhalten.
Daraus entstehen Objektlasten (:class:`~statik3d.model.Geometrielast` mit
``verlauf["art"] == "wasser"``), die beim Vernetzen auf die Elemente gelegt
werden und jedes Neuvernetzen überleben.

**Statisch**: hydrostatischer Druck p = ρ·g·(h − z) auf beiden Seiten, netto
aus Ober- und Unterwasser. Resultierende auf ein senkrechtes Rechteck:
F = ½·ρ·g·h²·b, Angriffspunkt h/3 über der Dichtung.

**Überströmt** (Oberwasser über der Oberkante z_ok): Überfallhöhe
h_ü = h_ow − z_ok, Abfluss je Breite nach Poleni q = ⅔·μ·√(2g)·h_ü^1,5,
kritische Tiefe h_c = ⅔·h_ü auf der Krone, v_c = √(g·h_c). Mit dem Schalter
**Absenkung** wird die Geschwindigkeitshöhe v²/2g auf der Krone vom Druck
abgezogen: an der Oberkante wirkt statt ρ·g·h_ü nur ⅔·ρ·g·h_ü; der Fehlbetrag
klingt nach unten linear über 2·h_ü ab (Näherung nach Naudascher: die
Krümmung der Stromlinien reicht etwa zwei Überfallhöhen unter die Krone).

**Unterströmt** (Öffnung a unter dem Verschluss): wirksame Fallhöhe
Δh = h_ow − max(h_uw, z_uk + μ_a·a), Ausflussgeschwindigkeit v_a = √(2·g·Δh)
(Torricelli), Abfluss je Breite q = μ_a·a·v_a mit dem Kontraktionsbeiwert
μ_a. Mit **Absenkung**: an der Unterkante herrscht der Druck des
Unterwassers (des kontrahierten Strahls) statt des Oberwasserdrucks; der
Fehlbetrag klingt nach oben linear über 2·a ab.

**Dynamisch**: eine Druckschwankung mit der Amplitude Δp = c_p'·ρ·v²/2
(Druckschwankungsbeiwert c_p', v die größte Strömungsgeschwindigkeit) auf der
benetzten Fläche als eigener Lastfall - der Eingang für den
Schwingungsnachweis des Verschlusses.

**Strömungsnumerisch** (Vorgabe, ``verfahren = "numerisch"``): statt der
Näherungsformeln wird die Strömung im lotrechten Schnitt durch den Verschluss
als Potentialströmung auf einem Gitter gelöst (:mod:`statik3d.stroemung`):
Zufluss aus dem Oberwasser, Abfluss über die Krone (Poleni) und/oder unter
dem Verschluss (Torricelli) oder ins Unterwasser, Wasserspiegel als feste
Deckel, der Verschluss aus den benetzten Flächen und Körpern gerastert. Der
Druck folgt aus Bernoulli p = ρ·g·(E − z) − ½·ρ·|v|² und wird je Elementseite
vor der Fläche abgetastet - das ergibt die **resultierende Druckverteilung**
mit der Absenkung an Krone und Unterkante aus der Rechnung statt aus der
Näherung. Wo Oberwasser und Unterwasser liegen, sagt je eine
**Referenzfläche** mit der Angabe, ob ihre Oberseite (+Normale) oder
Unterseite (−Normale) dem Wasser zugewandt ist. Die Dichtungslinie kann in
der Ansicht angeklickt werden. Die Rechnung läuft mit Fortschrittsbalken und
ist abbrechbar (:class:`statik3d.stroemung.Abgebrochen`).

Alle Höhen in m über dem Bezug des Modells (z-Achse nach oben), Drücke in
Pa, Kräfte in N. Bezug: DIN 19704-1 (Stahlwasserbauten), Naudascher,
Hydrodynamic Forces (IAHR 1991).
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

from . import stroemung as st

G = 9.81
VERFAHREN = ("numerisch", "analytisch")
SEITEN = ("Oberseite", "Unterseite")


@dataclass
class Wasserdruck:
    """Ein Wasserdruck-Lastgenerierer für einen Verschluss in einer Situation."""
    name: str
    situation: str = ""                    # "" = Grundstellung
    lastfall: str = ""                     # Lastfall der statischen Last (wird angelegt)
    lastfall_dyn: str = ""                 # Lastfall der Druckschwankung (Amplitude)
    flaechen: list = field(default_factory=list)     # benetzte Flächen (Haut)
    koerper: list = field(default_factory=list)      # benetzte Volumenkörper
    dichtung: list = field(default_factory=list)     # Linien der Dichtungslinie (unten)
    h_ow: float = 0.0                      # Wasserstand Oberwasser [m]
    h_uw: Optional[float] = None           # Wasserstand Unterwasser [m]; None = trocken
    rho: float = 1000.0                    # Dichte [kg/m³]
    richtung: Optional[list] = None        # None = senkrecht zur Fläche, sonst global
    seite: int = 1                         # +1: Druck gegen die Außennormale (in den Körper)
    z_uk: Optional[float] = None           # Unterkante / Dichtung [m]; None = aus Geometrie
    z_ok: Optional[float] = None           # Oberkante [m]; None = aus Geometrie
    breite: Optional[float] = None         # Breite quer zur Strömung [m]; None = aus Geometrie
    ueberstroemt: bool = False
    mu_ue: float = 0.62                    # Überfallbeiwert (Poleni)
    unterstroemt: bool = False
    spalt: float = 0.0                     # Öffnungshöhe a unter dem Verschluss [m]
    mu_a: float = 0.61                     # Kontraktionsbeiwert des Ausflusses
    absenkung: bool = True                 # Absenkung des Wasserspiegels berücksichtigen (analytisch)
    cp_dyn: float = 0.0                    # Druckschwankungsbeiwert c_p'
    kommentar: str = ""
    # -- strömungsnumerische Berechnung --------------------------------------
    verfahren: str = "numerisch"           # "numerisch" (Potentialströmung im Schnitt) | "analytisch"
    lastfall_nr: int = 0                   # Lastfallnummer (0 = nächste freie)
    ow_flaeche: str = ""                   # Referenzfläche des Oberwassers
    ow_seite: str = "Oberseite"            # Oberseite (+Normale) oder Unterseite (−Normale) ist Oberwasser
    uw_flaeche: str = ""                   # Referenzfläche des Unterwassers
    uw_seite: str = "Unterseite"
    z_sohle: Optional[float] = None        # Sohle [m]; None = Dichtung − Öffnung
    gitter: int = 40                       # Zellen über die Verschlusshöhe
    unterdruck: bool = False               # Unterdruck (Sog) ansetzen statt bei 0 zu kappen

    def numerisch(self) -> bool:
        return str(self.verfahren or "").lower().startswith("num")

    def bezug(self) -> str:
        t = f"OW {self.h_ow:g} m"
        t += f", UW {self.h_uw:g} m" if self.h_uw is not None else ", UW trocken"
        if self.ueberstroemt:
            t += ", überströmt"
        if self.unterstroemt:
            t += f", unterströmt a = {self.spalt:g} m"
        if self.situation:
            t += f" [{self.situation}]"
        return t


# ==========================================================================
# Druckverlauf
# ==========================================================================
def _param(wd) -> Wasserdruck:
    if isinstance(wd, Wasserdruck):
        return wd
    felder = {f for f in Wasserdruck.__dataclass_fields__}
    return Wasserdruck(**{k: v for k, v in dict(wd).items() if k in felder})


def geometrie(wd: Wasserdruck, model=None) -> dict:
    """z_uk, z_ok und Breite - aus den Angaben oder aus der Geometrie der Flächen."""
    z_uk, z_ok, b = wd.z_uk, wd.z_ok, wd.breite
    if model is not None and (z_uk is None or z_ok is None or b is None):
        knoten = set()
        for name in wd.flaechen:
            f = model.flaechen.get(name)
            if f is None:
                continue
            for e in f.elemente or []:
                if 0 <= int(e) < len(model.elements):
                    knoten.update(int(n) for n in model.elements[int(e)].nodes)
            try:
                knoten.update(int(n) for n in f.randknoten(model))
            except Exception:                    # noqa: BLE001
                pass
        for name in wd.koerper:
            k = model.koerper.get(name)
            if k is None:
                continue
            for e in k.elemente or []:
                if 0 <= int(e) < len(model.elements):
                    knoten.update(int(n) for n in model.elements[int(e)].nodes)
        if wd.dichtung and z_uk is None:
            zd = []
            for name in wd.dichtung:
                ln = model.lines.get(name)
                if ln is not None:
                    zd += [float(model.nodes[int(n)][2]) for n in ln.nodes if 0 <= int(n) < model.nn]
            if zd:
                z_uk = min(zd)
        if knoten:
            P = model.nodes[sorted(knoten)]
            if z_uk is None:
                z_uk = float(P[:, 2].min())
            if z_ok is None:
                z_ok = float(P[:, 2].max())
            if b is None:
                dx, dy = float(np.ptp(P[:, 0])), float(np.ptp(P[:, 1]))
                if wd.richtung is not None:
                    r = np.asarray(wd.richtung, float)
                    # Breite quer zur Strömung: die Ausdehnung senkrecht zur Richtung
                    b = dy if abs(r[0]) >= abs(r[1]) else dx
                else:
                    b = max(dx, dy)
    return {"z_uk": 0.0 if z_uk is None else float(z_uk),
            "z_ok": 1.0 if z_ok is None else float(z_ok),
            "breite": 1.0 if b is None else float(b)}


def kennwerte(wd: Wasserdruck, model=None, fortschritt=None) -> dict:
    """Strömungskennwerte: Überfall, Ausfluss, Geschwindigkeiten, Druckschwankung.
    Mit Modell und ``verfahren = "numerisch"`` kommen Resultierende,
    Angriffspunkt, Geschwindigkeiten und Druckverlauf aus dem Druckfeld der
    Potentialströmung (Schlüssel ``verfahren``, ``q``, ``p_max``, ``profil``,
    ``gitter``; das Feld selbst unter ``_feld``)."""
    out = _kennwerte_analytisch(wd, model)
    if model is not None and wd.numerisch() and (wd.flaechen or wd.koerper):
        try:
            fr = feld_rechnen(wd, model, fortschritt=fortschritt)
        except st.Abgebrochen:
            raise
        except (ValueError, KeyError, RuntimeError) as ex:
            out["verfahren"] = "analytisch"
            out["numerik_fehler"] = str(ex)
            return out
        out.update(_kennwerte_aus_feld(wd, fr, out))
    else:
        out["verfahren"] = "analytisch"
    return out


def _kennwerte_aus_feld(wd: Wasserdruck, fr: dict, out: dict) -> dict:
    """Was aus dem Druckfeld kommt - ueberschreibt die Naeherungswerte."""
    f = fr["feld"]
    b = out["breite"]
    z_s = fr["z_sohle"]
    # Die groesste Geschwindigkeit bleibt die des Strahls bzw. der Krone
    # (Torricelli, kritischer Abfluss) - die Potentialstroemung kann sie nicht
    # uebertreffen; das Feld liefert seinen eigenen Hoechstwert unter v_feld.
    profil = [(z_s + z, p) for z, p in f["profil"]]
    F = float(f["F_je_m"])
    z_R = z_s + float(f["z_R"])
    sch = fr["schnitt"]
    return {"verfahren": "numerisch", "F_je_m": F, "F": F * b, "z_R": z_R, "hebel": z_R - out["z_uk"],
            "v_feld": max(float(f["v_max"]), 0.0),
            "q": float(f["q"]), "Q": float(f["q"]) * b, "U": float(f["U"]), "p_max": float(f["p_max"]),
            "E_ow": z_s + float(f["E_ow"]), "profil": profil, "z_sohle": z_s,
            "gitter": (sch.nx, sch.nz, sch.h), "n_fluid": int(f["n_fluid"]),
            "richtung_stroemung": list(sch.ex), "hinweise": list(fr.get("hinweise", [])), "_feld": fr}


def _kennwerte_analytisch(wd: Wasserdruck, model=None) -> dict:
    """Die Näherungsformeln (Poleni, Torricelli, Naudascher)."""
    g = geometrie(wd, model)
    z_uk, z_ok = g["z_uk"], g["z_ok"]
    out = dict(g)
    out["h_ow"], out["h_uw"] = float(wd.h_ow), wd.h_uw
    out["rho"] = float(wd.rho)
    v_max = 0.0
    # Überströmen
    h_ue = max(0.0, wd.h_ow - z_ok) if wd.ueberstroemt else 0.0
    out["h_ue"] = h_ue
    if h_ue > 0:
        q = 2.0 / 3.0 * wd.mu_ue * math.sqrt(2 * G) * h_ue ** 1.5        # Poleni [m³/(s·m)]
        h_c = 2.0 / 3.0 * h_ue
        v_c = math.sqrt(G * h_c)                                          # kritisch, Fr = 1
        out.update({"q_ue": q, "Q_ue": q * g["breite"], "h_c": h_c, "v_c": v_c,
                    "Fr_c": 1.0, "dp_ue": wd.rho * G * h_ue / 3.0 if wd.absenkung else 0.0})
        v_max = max(v_max, v_c)
    # Unterströmen
    a = float(wd.spalt) if wd.unterstroemt else 0.0
    out["spalt"] = a
    if a > 0:
        unten = z_uk + wd.mu_a * a
        if wd.h_uw is not None:
            unten = max(unten, float(wd.h_uw))
        dh = max(0.0, wd.h_ow - unten)
        v_a = math.sqrt(2 * G * dh)
        q_a = wd.mu_a * a * v_a
        Fr_a = v_a / math.sqrt(G * wd.mu_a * a) if a > 0 else 0.0
        out.update({"dh_a": dh, "v_a": v_a, "q_a": q_a, "Q_a": q_a * g["breite"], "Fr_a": Fr_a,
                    "h_strahl": wd.mu_a * a})
        v_max = max(v_max, v_a)
    out["v_max"] = v_max
    out["dp_dyn"] = float(wd.cp_dyn) * wd.rho * v_max ** 2 / 2.0 if wd.cp_dyn else 0.0
    # Resultierende je Breite und gesamt (Integration des Nettodrucks)
    z_top = min(z_ok, max(wd.h_ow, wd.h_uw if wd.h_uw is not None else -math.inf))
    if z_top > z_uk:
        zz = np.linspace(z_uk, z_top, 2001)
        pp = np.array([druck(wd, z, g) for z in zz])
        F = float(np.trapezoid(pp, zz))
        M = float(np.trapezoid(pp * (zz - z_uk), zz))
        out["F_je_m"] = F
        out["F"] = F * g["breite"]
        out["z_R"] = z_uk + (M / F if abs(F) > 1e-12 else 0.0)
        out["hebel"] = (M / F if abs(F) > 1e-12 else 0.0)
    else:
        out["F_je_m"] = out["F"] = 0.0
        out["z_R"] = z_uk
        out["hebel"] = 0.0
    return out


def druck(wd, z: float, g: dict = None) -> float:
    """Nettodruck p(z) [Pa] auf den Verschluss, positiv vom Oberwasser her."""
    wd = _param(wd)
    g = g or geometrie(wd)
    z = float(z)
    p_ow = wd.rho * G * (wd.h_ow - z) if z < wd.h_ow else 0.0
    p_uw = wd.rho * G * (wd.h_uw - z) if (wd.h_uw is not None and z < wd.h_uw) else 0.0
    p = p_ow - p_uw
    if not wd.absenkung:
        return p
    z_uk, z_ok = g["z_uk"], g["z_ok"]
    # Überströmen: Geschwindigkeitshöhe auf der Krone, Fehlbetrag über 2 h_ue abklingend
    if wd.ueberstroemt and wd.h_ow > z_ok:
        h_ue = wd.h_ow - z_ok
        defekt = wd.rho * G * h_ue / 3.0
        tiefe = z_ok - z                       # unter der Krone
        if tiefe < 2.0 * h_ue:
            p -= defekt * max(0.0, 1.0 - tiefe / (2.0 * h_ue))
    # Unterströmen: an der Unterkante der Druck des Strahls / Unterwassers
    a = float(wd.spalt) if wd.unterstroemt else 0.0
    if a > 0 and wd.h_ow > z_uk:
        unten = z_uk + wd.mu_a * a
        if wd.h_uw is not None:
            unten = max(unten, float(wd.h_uw))
        p_lip_soll = wd.rho * G * max(0.0, unten - z_uk)          # Druck des Strahls an der Unterkante
        p_lip_ist = wd.rho * G * (wd.h_ow - z_uk) - (wd.rho * G * (wd.h_uw - z_uk)
                                                    if (wd.h_uw is not None and wd.h_uw > z_uk) else 0.0)
        defekt = p_lip_ist - (p_lip_soll - (wd.rho * G * (wd.h_uw - z_uk)
                                            if (wd.h_uw is not None and wd.h_uw > z_uk) else 0.0))
        hoehe = z - z_uk
        if defekt > 0 and hoehe < 2.0 * a:
            p -= defekt * max(0.0, 1.0 - hoehe / (2.0 * a))
    return p


#: Entpackte Druckfelder je Objektlast (Schluessel: id des verlauf-dicts und
#: sein Stempel) - das Entpacken darf nicht je Elementseite anfallen
_FELDER: dict = {}


def _feld_aus_verlauf(verlauf: dict):
    key = (id(verlauf), (verlauf.get("feld") or {}).get("stempel"))
    hit = _FELDER.get(key)
    if hit is None:
        hit = st.feld_entpacken(verlauf["feld"])
        if len(_FELDER) > 12:
            _FELDER.clear()
        _FELDER[key] = hit
    return hit


def druck_aus_verlauf(verlauf: dict, punkt, normale=None, beidseitig: bool = False) -> float:
    """Der Druck an einem Punkt für eine Geometrielast mit verlauf["art"] == "wasser".

    Mit Druckfeld (``verlauf["feld"]``, strömungsnumerisch) wird das Gitter
    vor der Elementseite abgetastet - entlang ``normale``, bei einer dünnen
    Schale (``beidseitig``) netto aus Vorder- und Rückseite; positiv drückt
    gegen die Außennormale. Sonst die Näherungsformel p(z)."""
    wd = _param(verlauf.get("param") or {})
    if verlauf.get("feld"):
        schnitt, p, fluid, _block = _feld_aus_verlauf(verlauf)
        # Nettodruck gegen die Aussennormale der Seite (positiv: drueckt hinein)
        p_n = float(st.wert_am_punkt(p, fluid, schnitt, punkt, normale, beidseitig))
        if verlauf.get("dyn"):
            p_n = math.copysign(float(verlauf.get("dp_dyn", 0.0)), p_n) if p_n != 0.0 else 0.0
        if wd.richtung is not None and normale is not None:
            # Last in einer vorgegebenen Richtung d: die Kraft −p_n·A·n wird
            # als p_d·A·d geschrieben, p_d = −p_n·sign(n·d)
            c = float(np.asarray(normale, float)[:3] @ np.asarray(wd.richtung, float)[:3])
            if abs(c) > 1e-9:
                return -p_n if c > 0 else p_n
        return p_n
    g = verlauf.get("geometrie") or geometrie(wd)
    z = float(np.asarray(punkt, float)[2])
    if verlauf.get("dyn"):
        # Druckschwankung: Amplitude auf der benetzten Fläche
        return float(verlauf.get("dp_dyn", 0.0)) * wd.seite if druck(wd, z, g) > 0 else 0.0
    return druck(wd, z, g) * wd.seite


# ==========================================================================
# Strömungsnumerische Berechnung im Schnitt
# ==========================================================================
def flaechennormale(model, name: str):
    """Mittlere Außennormale einer Fläche - aus den Schalenelementen, sonst
    aus dem Randpolygon (Newell)."""
    f = model.flaechen.get(name)
    if f is None:
        return None
    n = np.zeros(3)
    for e in f.elemente or []:
        if not 0 <= int(e) < len(model.elements):
            continue
        el = model.elements[int(e)]
        if el.typ not in ("shell3", "shell4"):
            continue
        X = model.nodes[[int(k) for k in el.nodes[:3]]]
        n += np.cross(X[1] - X[0], X[2] - X[0])
    if float(np.linalg.norm(n)) <= 1e-12:
        try:
            P = np.asarray(f.randpunkte(model), float)
        except Exception:                    # noqa: BLE001
            P = np.zeros((0, 3))
        for j in range(len(P)):
            a, b = P[j], P[(j + 1) % len(P)]
            n += np.cross(a, b)
    L = float(np.linalg.norm(n))
    return n / L if L > 1e-12 else None


def _seitennormale(model, name: str, seite: str):
    n = flaechennormale(model, name)
    if n is None:
        return None
    return -n if str(seite or "").lower().startswith("unter") else n


def stroemungsrichtung(wd: Wasserdruck, model) -> np.ndarray:
    """Waagerechte Einheitsrichtung der Strömung (vom Oberwasser durch den
    Verschluss): aus der Referenzfläche des Oberwassers, sonst aus der
    Lastrichtung, sonst aus der Normale der ersten benetzten Fläche."""
    ex = None
    if wd.ow_flaeche and wd.ow_flaeche in model.flaechen:
        n = _seitennormale(model, wd.ow_flaeche, wd.ow_seite)
        if n is not None:
            ex = -n
    if ex is None and wd.richtung is not None:
        ex = np.asarray(wd.richtung, float)[:3].copy()
    if ex is None:
        for name in list(wd.flaechen) + [n for k in wd.koerper for n in
                                         (model.koerper[k].flaechen if k in model.koerper else [])]:
            n = flaechennormale(model, name)
            if n is not None:
                ex = -float(wd.seite or 1) * n
                break
    if ex is None:
        ex = np.array([1.0, 0.0, 0.0])
    ex = np.asarray(ex, float)[:3].copy()
    ex[2] = 0.0
    L = float(np.linalg.norm(ex))
    return ex / L if L > 1e-9 else np.array([1.0, 0.0, 0.0])


def schnitt_anlegen(wd: Wasserdruck, model, g: dict, punkte: np.ndarray) -> tuple:
    """Schnittebene und Gitter um den Verschluss: (Schnitt, z_sohle)."""
    ex = stroemungsrichtung(wd, model)
    ez = np.array([0.0, 0.0, 1.0])
    P = np.asarray(punkte, float).reshape(-1, 3)
    xs = P @ ex
    H = max(float(g["z_ok"] - g["z_uk"]), 1e-3)
    a = float(wd.spalt) if wd.unterstroemt else 0.0
    z_sohle = float(wd.z_sohle) if wd.z_sohle is not None else float(g["z_uk"]) - a
    if z_sohle > g["z_uk"] - a + 1e-9:
        z_sohle = float(g["z_uk"]) - a
    h_uw = float(wd.h_uw) if wd.h_uw is not None else -math.inf
    tiefe = max(float(wd.h_ow), float(g["z_ok"]), h_uw) - z_sohle
    n_h = min(400, max(8, int(wd.gitter or 40)))
    h = H / n_h
    vor = max(2.5 * H, 2.0 * tiefe)
    nach = max(1.5 * H, 1.5 * tiefe)
    x0 = float(xs.min()) - vor
    x1 = float(xs.max()) + nach
    z_top = max(float(wd.h_ow), float(g["z_ok"]), h_uw) + max(0.2 * H, 2 * h)
    nx = int(math.ceil((x1 - x0) / h))
    nz = int(math.ceil((z_top - z_sohle) / h))
    if nx * nz > 250000:
        f = math.sqrt(nx * nz / 250000.0)
        h *= f
        nx = int(math.ceil((x1 - x0) / h))
        nz = int(math.ceil((z_top - z_sohle) / h))
    c = P.mean(axis=0)
    ursprung = c + (x0 - float(c @ ex)) * ex + (z_sohle - float(c[2])) * ez
    return st.Schnitt(ursprung, ex, ez, h, nx, nz), z_sohle


_FELD_CACHE: dict = {}


def feld_rechnen(wd: Wasserdruck, model, fortschritt=None) -> dict:
    """Die Potentialströmung um den Verschluss rechnen: Rückgabe
    {"schnitt", "z_sohle", "feld" (siehe stroemung.wasserdruck_feld), "g",
    "hinweise"}. Je Parametersatz und Modellstand einmal (Zwischenspeicher)."""
    g = geometrie(wd, model)
    stand = (id(model), model.nn, len(model.elements), len(model.flaechen),
             json.dumps({k: v for k, v in asdict(wd).items() if k not in ("name", "kommentar")}, sort_keys=True,
                        default=str))
    hit = _FELD_CACHE.get(stand)
    if hit is not None:
        return hit
    tris = st.objekt_dreiecke(model, wd.flaechen, wd.koerper)
    if not tris:
        raise ValueError("Die benetzten Flächen haben keine Geometrie (weder Netz noch Randlinien)")
    punkte = np.concatenate([np.asarray(t, float) for t in tris]).reshape(-1, 3)
    schnitt, z_sohle = schnitt_anlegen(wd, model, g, punkte)
    st._melden(fortschritt, 0.0, f"Wasserdruck {wd.name}: Gitter {schnitt.nx} × {schnitt.nz}")
    ver = st.rastern(schnitt, tris,
                     fortschritt=(lambda a_, t_: fortschritt(0.02 + 0.28 * a_, t_)) if fortschritt else None,
                     text=f"Wasserdruck {wd.name}: Verschluss rastern")
    ver = st.verdicken(ver)
    h_uw = None if wd.h_uw is None else float(wd.h_uw) - z_sohle
    feld = st.wasserdruck_feld(
        schnitt, ver, h_ow=float(wd.h_ow) - z_sohle, h_uw=h_uw, z_uk=float(g["z_uk"]) - z_sohle,
        z_ok=float(g["z_ok"]) - z_sohle, ueberstroemt=bool(wd.ueberstroemt),
        unterstroemt=bool(wd.unterstroemt), spalt=float(wd.spalt), mu_ue=float(wd.mu_ue),
        mu_a=float(wd.mu_a), rho=float(wd.rho), unterdruck=bool(wd.unterdruck),
        fortschritt=(lambda a_, t_: fortschritt(0.3 + 0.6 * a_, t_)) if fortschritt else None)
    hinweise = []
    if wd.uw_flaeche and wd.uw_flaeche in model.flaechen:
        n = _seitennormale(model, wd.uw_flaeche, wd.uw_seite)
        if n is not None and float(n @ np.asarray(schnitt.ex)) < 0:
            hinweise.append(f"Die Unterwasserseite der Fläche {wd.uw_flaeche} zeigt gegen die Strömung - "
                            "Ober- und Unterwasser vertauscht?")
    if feld["q"] > 0 and feld["n_fluid"] < 50:
        hinweise.append("Sehr wenige Fluidzellen - Gitter feiner wählen")
    out = {"schnitt": schnitt, "z_sohle": z_sohle, "feld": feld, "g": g, "hinweise": hinweise}
    if len(_FELD_CACHE) > 6:
        _FELD_CACHE.clear()
    _FELD_CACHE[stand] = out
    return out


def feld_svg_bericht(wd: Wasserdruck, kw: dict, breite: int = 620) -> str:
    """Das Druckfeld des Schnitts als Bild fuer den Bericht (nur numerisch)."""
    fr = kw.get("_feld")
    if not fr:
        return ""
    sch, f, z_s = fr["schnitt"], fr["feld"], fr["z_sohle"]
    L = sch.nx * sch.h
    linien = [((0.0, float(wd.h_ow) - z_s), (L * 0.5, float(wd.h_ow) - z_s), "#1467c6")]
    texte = [((0.5 * sch.h, float(wd.h_ow) - z_s), f"OW {wd.h_ow:g} m", "#1467c6")]
    if wd.h_uw is not None:
        linien.append(((L * 0.6, float(wd.h_uw) - z_s), (L, float(wd.h_uw) - z_s), "#1467c6"))
        texte.append(((L * 0.62, float(wd.h_uw) - z_s), f"UW {wd.h_uw:g} m", "#1467c6"))
    if kw.get("z_R") is not None:
        texte.append(((L * 0.02, float(kw["z_R"]) - z_s), f"F = {kw['F'] / 1e3:.1f} kN, z_R = {kw['z_R']:.2f} m",
                      "#c62828"))
    return st.feld_svg(sch, f["p"], f["fluid"], f["block"], "wasser", breite=breite,
                       titel=f"Wasserdruck {wd.name}: Druckfeld der Potentialströmung [kN/m²]",
                       einheit="kN/m²", faktor=1e-3, linien=linien, texte=texte)


# ==========================================================================
# Lasten erzeugen
# ==========================================================================
def lasten_erzeugen(model, wd: Wasserdruck, fortschritt=None) -> dict:
    """Die Objektlasten des Generierers in seine Lastfälle schreiben (vorher
    seine alten Lasten entfernen), auf das Netz verteilen; Rückgabe: die
    Kennwerte samt Zahl der Elementlasten. Strömungsnumerisch wird zuerst
    das Druckfeld gerechnet (``fortschritt(anteil, text) -> bool``; False
    bricht ab, das Modell bleibt dann unverändert)."""
    from .model import GRUNDSTELLUNG
    if not (wd.flaechen or wd.koerper):
        raise ValueError("Keine benetzte Fläche gewählt")
    fehlt = [n for n in wd.flaechen if n not in model.flaechen] \
        + [n for n in wd.koerper if n not in model.koerper]
    if fehlt:
        raise ValueError("Unbekannt: " + ", ".join(fehlt))
    if wd.situation and wd.situation not in model.situationsnamen():
        raise ValueError(f"Situation '{wd.situation}' unbekannt")
    for name, was in ((wd.ow_flaeche, "Oberwasser"), (wd.uw_flaeche, "Unterwasser")):
        if name and name not in model.flaechen:
            raise ValueError(f"Referenzfläche {was}: {name} unbekannt")
    g = geometrie(wd, model)
    kw = kennwerte(wd, model, fortschritt=fortschritt)
    feld = None
    if kw.get("verfahren") == "numerisch":
        fr = kw["_feld"]
        feld = st.feld_packen(fr["schnitt"], fr["feld"]["p"], fr["feld"]["fluid"], fr["feld"]["block"],
                              nachkomma=1, z_sohle=fr["z_sohle"], stempel=uuid.uuid4().hex)
    if not wd.lastfall:
        wd.lastfall = f"Wasser {wd.name}"
    lastfaelle = [(wd.lastfall, False)]
    if wd.cp_dyn and kw["dp_dyn"] > 0:
        if not wd.lastfall_dyn:
            wd.lastfall_dyn = f"Wasser {wd.name} dyn"
        lastfaelle.append((wd.lastfall_dyn, True))
    # Alte Lasten dieses Generierers entfernen (in allen Lastfaellen)
    for lc in model.load_cases.values():
        lc.geometrielasten = [gl for gl in lc.geometrielasten
                              if not (gl.verlauf.get("art") == "wasser"
                                      and gl.verlauf.get("name") == wd.name)]
    param = asdict(wd)
    n_lasten = 0
    st._melden(fortschritt, 0.92, f"Wasserdruck {wd.name}: Lasten auf das Netz")
    for j, (fall, dyn) in enumerate(lastfaelle):
        if fall not in model.load_cases:
            model.add_load_case(fall, "Q", f"Wasserdruck {wd.name}" + (" (Schwankung)" if dyn else ""),
                                activate=False)
        lc = model.load_cases[fall]
        lc.situation = "" if wd.situation == GRUNDSTELLUNG else wd.situation
        if not getattr(lc, "nummer", 0):
            lc.nummer = (int(wd.lastfall_nr) + j) if int(wd.lastfall_nr or 0) > 0 \
                else model.naechste_lastfallnummer()
        verlauf = {"art": "wasser", "name": wd.name, "param": param, "geometrie": g,
                   "dyn": dyn, "dp_dyn": kw["dp_dyn"]}
        if feld is not None:
            verlauf["feld"] = feld
        for name in wd.flaechen:
            model.add_geometrielast(name, 0.0, art="flaeche", richtung=wd.richtung, case=fall,
                                    verlauf=dict(verlauf))
            n_lasten += 1
        for name in wd.koerper:
            model.add_geometrielast(name, 0.0, art="koerper", richtung=wd.richtung, case=fall,
                                    verlauf=dict(verlauf))
            n_lasten += 1
    model.wasserdruecke[wd.name] = wd
    n_elem = model.lasten_verteilen()
    kw["objektlasten"] = n_lasten
    kw["elementlasten"] = n_elem
    kw["lastfaelle"] = [f for f, _ in lastfaelle]
    kw["lastfall_nr"] = int(getattr(model.load_cases[wd.lastfall], "nummer", 0) or 0)
    kw["kontrolle"] = kontrollsumme(model, wd)
    st._melden(fortschritt, 1.0, f"Wasserdruck {wd.name}: {n_elem} Elementlasten")
    return kw


def kontrollsumme(model, wd: Wasserdruck) -> dict:
    """Summe der erzeugten Elementlasten (Kraftvektor) - zur Probe gegen F."""
    from .elements import shell as sh
    from .assemble import SOLID_FACES
    F = np.zeros(3)
    M = np.zeros(3)
    n = 0
    lc = model.load_cases.get(wd.lastfall)
    if lc is None:
        return {"F": F.tolist(), "n": 0}
    for fl in lc.face_loads:
        if not getattr(fl, "_geo", False):
            continue
        e = model.elements[int(fl.elem)]
        X = model.nodes[[int(k) for k in e.nodes]]
        if e.typ in ("shell3", "shell4"):
            tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
            A = 0.0
            nrm = None
            for t in tris:
                T3, _xy, At = sh.shell_frame(X[t[0]], X[t[1]], X[t[2]])
                A += At
                nrm = T3[2]
            mitte = X.mean(axis=0)
        else:
            seiten = SOLID_FACES.get(e.typ)
            if not seiten:
                continue
            nd = seiten[int(fl.face) % len(seiten)]
            P = X[list(nd)]
            v = np.zeros(3)
            for i in range(1, len(P) - 1):
                v += np.cross(P[i] - P[0], P[i + 1] - P[0])
            A = 0.5 * float(np.linalg.norm(v))
            nrm = model._seitennormale(int(fl.elem), int(fl.face))
            if nrm is None:
                continue
            nrm = -nrm            # p positiv drueckt in den Koerper
            mitte = P.mean(axis=0)
        if fl.direction is not None:
            d = np.asarray(fl.direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
            f = fl.p * A * d
        else:
            f = fl.p * A * nrm
        F += f
        M += np.cross(mitte, f)
        n += 1
    return {"F": F.tolist(), "M": M.tolist(), "n": n, "betrag": float(np.linalg.norm(F))}


# ==========================================================================
# Erläuterung und Skizze
# ==========================================================================
def erlaeuterung(wd: Wasserdruck, kw: dict) -> list:
    """Erläuternde Sätze zum Strömungsverhalten (für Protokoll und Bericht)."""
    z = []
    z.append(f"Hydrostatischer Druck p = ρ·g·(h − z) mit ρ = {wd.rho:g} kg/m³, Oberwasser "
             f"{wd.h_ow:g} m" + (f", Unterwasser {wd.h_uw:g} m (Nettodruck)" if wd.h_uw is not None
                                  else ", Unterwasser trocken")
             + f"; Verschluss von z = {kw['z_uk']:g} m (Dichtung) bis {kw['z_ok']:g} m, Breite "
               f"{kw['breite']:g} m.")
    z.append(f"Resultierende {kw['F'] / 1e3:.1f} kN ({kw['F_je_m'] / 1e3:.2f} kN/m), Angriffspunkt "
             f"{kw['hebel']:.3f} m über der Dichtung (z = {kw['z_R']:.3f} m).")
    if kw.get("h_ue", 0) > 0:
        z.append(f"Überströmt: Überfallhöhe h_ü = {kw['h_ue']:.3f} m, Abfluss nach Poleni "
                 f"q = ⅔·μ·√(2g)·h_ü^1,5 = {kw['q_ue']:.3f} m³/(s·m) mit μ = {wd.mu_ue:g} "
                 f"(Q = {kw['Q_ue']:.2f} m³/s); auf der Krone kritischer Abfluss, h_c = ⅔·h_ü = "
                 f"{kw['h_c']:.3f} m, v_c = √(g·h_c) = {kw['v_c']:.2f} m/s (Fr = 1)."
                 + (f" Absenkung berücksichtigt: an der Oberkante wirkt ρ·g·h_ü − ρ·v_c²/2 = "
                    f"⅔·ρ·g·h_ü, der Fehlbetrag {kw['dp_ue'] / 1e3:.2f} kN/m² klingt über 2·h_ü nach "
                    f"unten ab." if wd.absenkung else " Absenkung nicht berücksichtigt (hydrostatisch bis zur Krone)."))
    if kw.get("spalt", 0) > 0:
        z.append(f"Unterströmt: Öffnung a = {kw['spalt']:g} m, kontrahierter Strahl μ_a·a = "
                 f"{kw['h_strahl']:.3f} m (μ_a = {wd.mu_a:g}), wirksame Fallhöhe Δh = {kw['dh_a']:.3f} m, "
                 f"v_a = √(2·g·Δh) = {kw['v_a']:.2f} m/s (Torricelli), q = μ_a·a·v_a = "
                 f"{kw['q_a']:.3f} m³/(s·m) (Q = {kw['Q_a']:.2f} m³/s), Froude-Zahl des Strahls "
                 f"Fr = {kw['Fr_a']:.2f}."
                 + (" Absenkung berücksichtigt: an der Unterkante herrscht der Druck des Strahls "
                    "bzw. des Unterwassers, der Fehlbetrag klingt über 2·a nach oben ab."
                    if wd.absenkung else " Absenkung nicht berücksichtigt."))
    if kw.get("dp_dyn", 0) > 0:
        z.append(f"Druckschwankung: Δp = c_p'·ρ·v²/2 = {kw['dp_dyn'] / 1e3:.3f} kN/m² mit c_p' = "
                 f"{wd.cp_dyn:g} und v = {kw['v_max']:.2f} m/s als Amplitude auf der benetzten Fläche "
                 f"(Lastfall {wd.lastfall_dyn}) - Eingang für den Schwingungsnachweis.")
    if not (kw.get("h_ue", 0) > 0 or kw.get("spalt", 0) > 0):
        z.append("Kein Überströmen und kein Unterströmen: rein hydrostatische Belastung.")
    if kw.get("verfahren") == "numerisch":
        nx, nz, h = kw.get("gitter", (0, 0, 0.0))
        z.append(f"Strömungsnumerisch: Potentialströmung (reibungsfrei, drehungsfrei) im lotrechten Schnitt "
                 f"durch den Verschluss auf einem Gitter {nx} × {nz} (Zelle {h:.3g} m, {kw.get('n_fluid', 0)} "
                 f"Fluidzellen), Sohle z = {kw.get('z_sohle', 0):g} m, Strömungsrichtung "
                 f"({kw['richtung_stroemung'][0]:+.2f}, {kw['richtung_stroemung'][1]:+.2f}). "
                 f"Wasserspiegel als feste Deckel, Zufluss q = {kw.get('q', 0):.3f} m³/(s·m) "
                 f"(U = {kw.get('U', 0):.2f} m/s), Druck aus Bernoulli p = ρ·g·(E − z) − ½·ρ·v² mit der "
                 f"Energiehöhe E = {kw.get('E_ow', 0):.3f} m; größte Geschwindigkeit {kw['v_max']:.2f} m/s, "
                 f"größter Druck {kw.get('p_max', 0) / 1e3:.1f} kN/m². Die Elementseiten tasten das Feld vor "
                 f"der Fläche ab; die Resultierende {kw['F'] / 1e3:.1f} kN bei z = {kw['z_R']:.3f} m ist die "
                 f"Summe der Zelldrücke auf den Verschluss." + (" Unterdruck (Sog) angesetzt."
                                                               if wd.unterdruck else
                                                               " Unterdruck bei 0 gekappt (belüftet)."))
        for hw in kw.get("hinweise", []):
            z.append("Hinweis: " + hw)
    elif kw.get("numerik_fehler"):
        z.append(f"Strömungsnumerische Berechnung nicht möglich ({kw['numerik_fehler']}) - Näherungsformeln.")
    return z


def skizze_svg(wd: Wasserdruck, kw: dict, breite: int = 560, hoehe: int = 380) -> str:
    """Schnitt durch den Verschluss: Wasserstände, Druckfigur, Über-/Unterströmung,
    Resultierende - als SVG-Text."""
    z_uk, z_ok = kw["z_uk"], kw["z_ok"]
    profil = kw.get("profil") or []

    def pz(z: float) -> float:
        """Druck an der Oberwasserseite: aus dem Feld (numerisch) oder der Formel."""
        if len(profil) >= 2:
            zz = np.array([q[0] for q in profil])
            pp = np.array([q[1] for q in profil])
            o = np.argsort(zz)
            if zz[o][0] - 1e-9 <= z <= zz[o][-1] + 1e-9:
                return float(np.interp(z, zz[o], pp[o]))
            return 0.0
        return druck(wd, z, kw)

    z_lo = min(z_uk - (wd.spalt if wd.unterstroemt else 0.0) - 0.15 * (z_ok - z_uk), z_uk - 0.2)
    z_hi = max(z_ok, wd.h_ow, wd.h_uw if wd.h_uw is not None else z_ok) + 0.25 * max(z_ok - z_uk, 0.5)
    H = max(z_hi - z_lo, 1e-6)
    rand = 40
    sy = (hoehe - 2 * rand) / H
    x_gate = breite * 0.5
    p_max = max(1e-9, max(abs(pz(z)) for z in np.linspace(z_uk, min(z_ok, max(wd.h_ow, z_uk)), 50))
                if wd.h_ow > z_uk else 1e-9)
    sx = (breite * 0.3) / p_max

    def Y(z):
        return hoehe - rand - (z - z_lo) * sy

    def X(p):
        return x_gate - p * sx

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{breite}" height="{hoehe}" '
         f'viewBox="0 0 {breite} {hoehe}" font-family="sans-serif" font-size="11">',
         f'<rect width="{breite}" height="{hoehe}" fill="#fff"/>']
    # Wasser links (Oberwasser) und rechts (Unterwasser)
    if wd.h_ow > z_lo:
        s.append(f'<rect x="{rand}" y="{Y(wd.h_ow):.1f}" width="{x_gate - rand:.1f}" '
                 f'height="{Y(z_lo) - Y(wd.h_ow):.1f}" fill="#cfe3f7" opacity="0.7"/>')
        s.append(f'<line x1="{rand}" y1="{Y(wd.h_ow):.1f}" x2="{x_gate:.1f}" y2="{Y(wd.h_ow):.1f}" '
                 f'stroke="#1467c6" stroke-width="1.5"/>')
        s.append(f'<text x="{rand + 4}" y="{Y(wd.h_ow) - 4:.1f}" fill="#1467c6">OW {wd.h_ow:g} m</text>')
    if wd.h_uw is not None and wd.h_uw > z_lo:
        s.append(f'<rect x="{x_gate:.1f}" y="{Y(wd.h_uw):.1f}" width="{breite - rand - x_gate:.1f}" '
                 f'height="{Y(z_lo) - Y(wd.h_uw):.1f}" fill="#cfe3f7" opacity="0.7"/>')
        s.append(f'<line x1="{x_gate:.1f}" y1="{Y(wd.h_uw):.1f}" x2="{breite - rand}" y2="{Y(wd.h_uw):.1f}" '
                 f'stroke="#1467c6" stroke-width="1.5"/>')
        s.append(f'<text x="{breite - rand - 70}" y="{Y(wd.h_uw) - 4:.1f}" fill="#1467c6">UW {wd.h_uw:g} m</text>')
    # Sohle
    s.append(f'<line x1="{rand}" y1="{Y(z_lo):.1f}" x2="{breite - rand}" y2="{Y(z_lo):.1f}" stroke="#666" stroke-width="2"/>')
    # Druckfigur
    if wd.h_ow > z_uk:
        zz = np.linspace(z_uk, min(z_ok, max(wd.h_ow, wd.h_uw or z_uk)), 60)
        pts = [f"{x_gate:.1f},{Y(zz[0]):.1f}"] + [f"{X(pz(z)):.1f},{Y(z):.1f}" for z in zz] \
            + [f"{x_gate:.1f},{Y(zz[-1]):.1f}"]
        s.append(f'<polygon points="{" ".join(pts)}" fill="#e5701c" opacity="0.35" stroke="#e5701c"/>')
        pw = [pz(z) for z in zz]
        k_max = int(np.argmax(pw))
        s.append(f'<text x="{X(pw[k_max]) + 6:.1f}" y="{Y(zz[k_max]) - 6:.1f}" fill="#7a3a06">'
                 f'p_max = {pw[k_max] / 1e3:.1f} kN/m²</text>')
    # Verschluss
    s.append(f'<rect x="{x_gate - 4:.1f}" y="{Y(z_ok):.1f}" width="8" height="{Y(z_uk) - Y(z_ok):.1f}" fill="#2b2b2b"/>')
    s.append(f'<text x="{x_gate + 8:.1f}" y="{Y(z_ok) + 4:.1f}">OK {z_ok:g} m</text>')
    s.append(f'<text x="{x_gate + 8:.1f}" y="{Y(z_uk) + 4:.1f}">Dichtung {z_uk:g} m</text>')
    # Ueberfall
    if kw.get("h_ue", 0) > 0:
        h_ue = kw["h_ue"]
        s.append(f'<path d="M {x_gate - 60:.1f} {Y(wd.h_ow):.1f} Q {x_gate + 10:.1f} {Y(z_ok + 0.6 * h_ue):.1f} '
                 f'{x_gate + 60:.1f} {Y(z_ok - 1.5 * h_ue):.1f}" fill="none" stroke="#1467c6" stroke-width="2" stroke-dasharray="4 3"/>')
        s.append(f'<text x="{x_gate + 30:.1f}" y="{Y(wd.h_ow) - 18:.1f}" fill="#1467c6">'
                 f'h_ü = {h_ue:.2f} m, q = {kw["q_ue"]:.2f} m³/(s·m)</text>')
        s.append(f'<text x="{x_gate + 30:.1f}" y="{Y(wd.h_ow) - 5:.1f}" fill="#1467c6">'
                 f'v_c = {kw["v_c"]:.2f} m/s (Fr = 1), Absenkung {"ja" if wd.absenkung else "nein"}</text>')
    # Unterstroemung
    if kw.get("spalt", 0) > 0:
        a = kw["spalt"]
        s.append(f'<rect x="{x_gate - 4:.1f}" y="{Y(z_uk):.1f}" width="8" height="{Y(z_uk - a) - Y(z_uk):.1f}" fill="#fff" stroke="#2b2b2b" stroke-dasharray="3 2"/>')
        y1, y2 = Y(z_uk - a / 2), Y(z_uk - a / 2)
        s.append(f'<line x1="{x_gate - 50:.1f}" y1="{y1:.1f}" x2="{x_gate + 50:.1f}" y2="{y2:.1f}" stroke="#1467c6" stroke-width="2" marker-end="url(#pf)"/>')
        s.append(f'<text x="{x_gate + 54:.1f}" y="{Y(z_lo) + 14:.1f}" fill="#1467c6">'
                 f'unterströmt: a = {a:g} m, v_a = {kw["v_a"]:.2f} m/s</text>')
        s.append(f'<text x="{x_gate + 54:.1f}" y="{Y(z_lo) + 27:.1f}" fill="#1467c6">'
                 f'q = {kw["q_a"]:.2f} m³/(s·m), Fr = {kw["Fr_a"]:.2f}</text>')
    # Resultierende
    if kw.get("F", 0):
        yR = Y(kw["z_R"])
        s.append('<defs><marker id="pf" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
                 '<path d="M0,0 L8,4 L0,8 z" fill="#c62828"/></marker></defs>')
        s.append(f'<line x1="{x_gate - 110:.1f}" y1="{yR:.1f}" x2="{x_gate - 10:.1f}" y2="{yR:.1f}" '
                 f'stroke="#c62828" stroke-width="2.5" marker-end="url(#pf)"/>')
        s.append(f'<text x="{x_gate - 112:.1f}" y="{yR - 6:.1f}" text-anchor="end" fill="#c62828">'
                 f'F = {kw["F"] / 1e3:.1f} kN bei z = {kw["z_R"]:.2f} m</text>')
    s.append('</svg>')
    return "\n".join(s)
