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

Alle Höhen in m über dem Bezug des Modells (z-Achse nach oben), Drücke in
Pa, Kräfte in N. Bezug: DIN 19704-1 (Stahlwasserbauten), Naudascher,
Hydrodynamic Forces (IAHR 1991).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

G = 9.81


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
    absenkung: bool = True                 # Absenkung des Wasserspiegels berücksichtigen
    cp_dyn: float = 0.0                    # Druckschwankungsbeiwert c_p'
    kommentar: str = ""

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


def kennwerte(wd: Wasserdruck, model=None) -> dict:
    """Strömungskennwerte: Überfall, Ausfluss, Geschwindigkeiten, Druckschwankung."""
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


def druck_aus_verlauf(verlauf: dict, punkt) -> float:
    """Der Druck an einem Punkt für eine Geometrielast mit verlauf["art"] == "wasser"."""
    wd = _param(verlauf.get("param") or {})
    g = verlauf.get("geometrie") or geometrie(wd)
    z = float(np.asarray(punkt, float)[2])
    if verlauf.get("dyn"):
        # Druckschwankung: Amplitude auf der benetzten Fläche
        return float(verlauf.get("dp_dyn", 0.0)) * wd.seite if druck(wd, z, g) > 0 else 0.0
    return druck(wd, z, g) * wd.seite


# ==========================================================================
# Lasten erzeugen
# ==========================================================================
def lasten_erzeugen(model, wd: Wasserdruck) -> dict:
    """Die Objektlasten des Generierers in seine Lastfälle schreiben (vorher
    seine alten Lasten entfernen), auf das Netz verteilen; Rückgabe: die
    Kennwerte samt Zahl der Elementlasten."""
    from .model import GRUNDSTELLUNG
    if not (wd.flaechen or wd.koerper):
        raise ValueError("Keine benetzte Fläche gewählt")
    fehlt = [n for n in wd.flaechen if n not in model.flaechen] \
        + [n for n in wd.koerper if n not in model.koerper]
    if fehlt:
        raise ValueError("Unbekannt: " + ", ".join(fehlt))
    if wd.situation and wd.situation not in model.situationsnamen():
        raise ValueError(f"Situation '{wd.situation}' unbekannt")
    g = geometrie(wd, model)
    kw = kennwerte(wd, model)
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
    for fall, dyn in lastfaelle:
        if fall not in model.load_cases:
            model.add_load_case(fall, "Q", f"Wasserdruck {wd.name}" + (" (Schwankung)" if dyn else ""),
                                activate=False)
        lc = model.load_cases[fall]
        lc.situation = "" if wd.situation == GRUNDSTELLUNG else wd.situation
        verlauf = {"art": "wasser", "name": wd.name, "param": param, "geometrie": g,
                   "dyn": dyn, "dp_dyn": kw["dp_dyn"]}
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
    kw["kontrolle"] = kontrollsumme(model, wd)
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
    return z


def skizze_svg(wd: Wasserdruck, kw: dict, breite: int = 560, hoehe: int = 380) -> str:
    """Schnitt durch den Verschluss: Wasserstände, Druckfigur, Über-/Unterströmung,
    Resultierende - als SVG-Text."""
    z_uk, z_ok = kw["z_uk"], kw["z_ok"]
    z_lo = min(z_uk - (wd.spalt if wd.unterstroemt else 0.0) - 0.15 * (z_ok - z_uk), z_uk - 0.2)
    z_hi = max(z_ok, wd.h_ow, wd.h_uw if wd.h_uw is not None else z_ok) + 0.25 * max(z_ok - z_uk, 0.5)
    H = max(z_hi - z_lo, 1e-6)
    rand = 40
    sy = (hoehe - 2 * rand) / H
    x_gate = breite * 0.5
    p_max = max(1e-9, max(abs(druck(wd, z, kw)) for z in np.linspace(z_uk, min(z_ok, max(wd.h_ow, z_uk)), 50))
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
        pts = [f"{x_gate:.1f},{Y(zz[0]):.1f}"] + [f"{X(druck(wd, z, kw)):.1f},{Y(z):.1f}" for z in zz] \
            + [f"{x_gate:.1f},{Y(zz[-1]):.1f}"]
        s.append(f'<polygon points="{" ".join(pts)}" fill="#e5701c" opacity="0.35" stroke="#e5701c"/>')
        pw = [druck(wd, z, kw) for z in zz]
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
