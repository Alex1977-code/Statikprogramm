"""
Schwingungsnachweis eines Verschlusses: strömungsinduzierte Schwingungen
aus den Ergebnissen des Wasserdruck-Generierers.

Grundlagen (Naudascher/Rockwell, Flow-Induced Vibrations; Kolkman; DIN 19704-1
Abschnitt Schwingungen; BAW-Merkblatt):

* **Eigenfrequenzen in Luft und im Wasser.** Das mitschwingende Wasser wirkt
  als hydrodynamische Zusatzmasse. Für eine senkrechte, starre Wand vor einem
  Wasserkörper der Tiefe H gilt nach Westergaard die Massenverteilung

      m''(y) = 7/8 · ρ · √(H·y)      (y = Tiefe unter dem Wasserspiegel)

  je Flächeneinheit, in Summe 7/12·ρ·H² je Breite. Sie wird an den benetzten
  Schalenelementen in Richtung ihrer Normalen als Knotenmasse angesetzt
  (m·n·nᵀ), auf beiden Wasserseiten getrennt. Damit sinkt jede Eigenfrequenz
  von f_Luft auf f_Wasser = f_Luft·√(m/(m + m_h)) (modal).
* **Wirbelablösung** an Unterkante bzw. Dichtung: f_s = St·v/d mit der
  Strouhal-Zahl St (≈ 0,2 für stumpfe Kanten), der Strömungsgeschwindigkeit
  v (Ausflussstrahl bzw. Überfallgeschwindigkeit aus dem Wasserdruck) und der
  Kantenbreite d in Strömungsrichtung. Liegt f_s im Band ±band um eine
  Eigenfrequenz, droht Resonanz (Lock-in).
* **Reduzierte Geschwindigkeit** V_r = v/(f·d). Für V_r ≤ V_r,grenz (≈ 1) ist
  die Anregung quasistatisch und instabilitäts- oder bewegungsinduzierte
  Schwingungen sind nicht zu erwarten; darüber sind sie möglich und müssen
  konstruktiv (steife, scharfkantige Unterkante, Dichtung stromauf) oder
  durch eine genauere Untersuchung ausgeschlossen werden.
* **Dynamische Antwort** auf die Druckschwankung Δp = c_p'·ρ·v²/2 (Lastfall
  des Generierers): Vergrößerungsfunktion V = 1/√((1−r²)² + (2ζr)²) mit
  r = f_s/f₁ und dem Dämpfungsgrad ζ; Spannungsschwingbreite Δσ = 2·V·σ_amp;
  Lastspiele N = f_s·Betriebsdauer; Ermüdung nach EN 1993-1-9 (Kerbfall,
  Palmgren-Miner D = N/N_R ≤ 1).

Alle Formeln sind geschlossene Näherungen der Literatur; Kompressibilität
des Wassers, Kavitation und die Rückwirkung der Schwingung auf die Strömung
(selbsterregte Schwingungen) sind nicht enthalten - dafür steht der Hinweis
über V_r.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import sparse

from .wasserdruck import Wasserdruck, kennwerte as wd_kennwerte, geometrie as wd_geometrie

NDOF = 6
SHELL_TYPES = ("shell3", "shell4")


# ==========================================================================
# Eingabe
# ==========================================================================
@dataclass
class Schwingungsnachweis:
    """Die Angaben zum Nachweis eines Verschlusses."""
    name: str
    wasserdruck: str = ""              # Name des Wasserdruck-Generierers
    n_moden: int = 6
    zeta: float = 0.02                 # Dämpfungsgrad (Lehr)
    strouhal: float = 0.2              # Strouhal-Zahl der Kante
    d_kante: Optional[float] = None    # Kantenbreite in Strömungsrichtung [m]; None = Blechdicke
    vr_grenz: float = 1.0              # Grenze der reduzierten Geschwindigkeit
    band: float = 0.2                  # Resonanzband ±band um f_s
    hydromasse: bool = True            # hydrodynamische Masse nach Westergaard
    betriebsstunden: float = 0.0       # Stunden je Jahr mit Durch-/Überströmung
    jahre: float = 50.0                # Nutzungsdauer
    kerbfall: float = 71.0             # Δσ_C [MPa]
    gamma_Mf: float = 1.15
    gamma_Ff: float = 1.0
    kommentar: str = ""


# ==========================================================================
# Ergebnis
# ==========================================================================
@dataclass
class Mode:
    nr: int
    f_luft: float
    f_wasser: float
    mu: float = 0.0                    # modales Massenverhältnis m_h/m
    V_r: float = 0.0
    verhaeltnis: float = 0.0           # f_s / f
    dlf: float = 1.0
    beurteilung: str = ""
    kritisch: bool = False
    hinweis: bool = False

    def zeile(self) -> list:
        f = lambda v, d=2: "–" if v is None else f"{v:.{d}f}"    # noqa: E731
        return [str(self.nr), f(self.f_luft), f(self.f_wasser), f(self.mu),
                f(self.V_r) if self.V_r else "–", f(self.verhaeltnis) if self.verhaeltnis else "–",
                f(self.dlf) if self.verhaeltnis else "–", self.beurteilung]


@dataclass
class SchwingungsErgebnis:
    name: str
    wasserdruck: str
    moden: list = field(default_factory=list)
    m_struktur: float = 0.0            # Masse der benetzten Haut [kg]
    m_hydro: float = 0.0               # hydrodynamische Masse gesamt [kg]
    m_hydro_theorie: float = 0.0       # 7/12·ρ·H²·b (Oberwasser) [kg]
    v: float = 0.0                     # maßgebende Strömungsgeschwindigkeit [m/s]
    d: float = 0.0                     # Kantenbreite [m]
    f_s: float = 0.0                   # Strouhal-Frequenz [Hz]
    f_grenz: float = 0.0               # Frequenz mit V_r = V_r,grenz [Hz]
    zeta: float = 0.02
    strouhal: float = 0.2
    vr_grenz: float = 1.0
    band: float = 0.2
    kennwerte: dict = field(default_factory=dict)
    dyn: dict = field(default_factory=dict)
    status: str = ""
    log: list = field(default_factory=list)
    res_luft: object = None
    res_wasser: object = None

    KOPF = ["Mode", "f_Luft [Hz]", "f_Wasser [Hz]", "m_h/m", "V_r", "f_s/f", "V", "Beurteilung"]

    def tabelle(self) -> list:
        return [list(self.KOPF)] + [mo.zeile() for mo in self.moden]

    def summary(self) -> str:
        if not self.moden:
            return f"Schwingung {self.name}: keine Eigenform"
        f1 = self.moden[0].f_wasser
        t = f"Schwingung {self.name}: f₁ = {f1:.2f} Hz im Wasser"
        if self.f_s > 0:
            t += f", f_s = {self.f_s:.2f} Hz, V_r,1 = {self.moden[0].V_r:.2f}"
        if self.dyn.get("D") is not None:
            t += f", D = {self.dyn['D']:.3f}"
        return t + f" - {self.status}"


# ==========================================================================
# Geschlossene Formeln
# ==========================================================================
def westergaard(H: float, y: float, rho: float = 1000.0) -> float:
    """Hydrodynamische Masse je Fläche [kg/m²] in der Tiefe y unter dem
    Wasserspiegel bei der Wassertiefe H (Westergaard 1933)."""
    if H <= 0 or y <= 0:
        return 0.0
    return 7.0 / 8.0 * rho * math.sqrt(H * min(y, H))


def westergaard_gesamt(H: float, rho: float = 1000.0) -> float:
    """∫₀ᴴ m''(y) dy = 7/12·ρ·H² je Breite [kg/m]."""
    return 7.0 / 12.0 * rho * max(H, 0.0) ** 2 if H > 0 else 0.0


def strouhal_frequenz(St: float, v: float, d: float) -> float:
    return St * v / d if (v > 0 and d > 0) else 0.0


def reduzierte_geschwindigkeit(v: float, f: float, d: float) -> float:
    return v / (f * d) if (f > 0 and d > 0) else 0.0


def vergroesserung(r: float, zeta: float) -> float:
    """Vergrößerungsfunktion des gedämpften Einmassenschwingers, r = f_err/f_n."""
    return 1.0 / math.sqrt((1.0 - r * r) ** 2 + (2.0 * zeta * r) ** 2)


def frequenz_im_wasser(f_luft: float, mu: float) -> float:
    """f_Wasser = f_Luft·√(1/(1 + m_h/m)) bei modal gleichmäßiger Zusatzmasse."""
    return f_luft / math.sqrt(1.0 + mu)


# ==========================================================================
# Hydrodynamische Zusatzmasse auf dem Netz
# ==========================================================================
def _integrationspunkte(X: np.ndarray):
    """(Punkte, Flächengewichte, Normale, Fläche) eines Schalenelements:
    Dreieck mit den Seitenmitten, Viereck mit 2×2 Gauß-Punkten."""
    X = np.asarray(X, float)
    if len(X) == 3:
        n = np.cross(X[1] - X[0], X[2] - X[0])
        A = 0.5 * float(np.linalg.norm(n))
        pts = [(X[0] + X[1]) / 2, (X[1] + X[2]) / 2, (X[2] + X[0]) / 2]
        w = [A / 3.0] * 3
    else:
        n = np.cross(X[2] - X[0], X[3] - X[1])
        A = 0.5 * float(np.linalg.norm(n))
        g = 1.0 / math.sqrt(3.0)
        pts, w = [], []
        for xi in (-g, g):
            for eta in (-g, g):
                N = [(1 - xi) * (1 - eta) / 4, (1 + xi) * (1 - eta) / 4,
                     (1 + xi) * (1 + eta) / 4, (1 - xi) * (1 + eta) / 4]
                pts.append(sum(Ni * Xi for Ni, Xi in zip(N, X[:4])))
                w.append(A / 4.0)
    nn = float(np.linalg.norm(n))
    return pts, w, (n / nn if nn > 0 else np.array([1.0, 0.0, 0.0])), A


def zusatzmassen(model, wd: Wasserdruck, kw: dict = None) -> tuple:
    """Hydrodynamische Zusatzmasse der benetzten Flächen als Matrix (ndof×ndof)
    und Kennzahlen. Je Wasserseite (Ober-, Unterwasser) die Westergaard-
    Verteilung in Richtung der Elementnormalen, gleichmäßig auf die Knoten."""
    g = wd_geometrie(wd, model)
    z_uk = g["z_uk"]
    seiten = [(float(wd.h_ow), float(wd.h_ow) - z_uk)]
    if wd.h_uw is not None:
        seiten.append((float(wd.h_uw), float(wd.h_uw) - z_uk))
    n_all = model.ndof
    rows, cols, vals = [], [], []
    m_ges = 0.0
    m_str = 0.0
    A_ges = 0.0
    elemente = []
    for name in wd.flaechen:
        f = model.flaechen.get(name)
        if f is None:
            continue
        for ei in f.elemente or []:
            ei = int(ei)
            if 0 <= ei < len(model.elements) and model.elements[ei].typ in SHELL_TYPES:
                elemente.append(ei)
    for ei in elemente:
        e = model.elements[ei]
        X = model.nodes[[int(i) for i in e.nodes]]
        pts, w, n, A = _integrationspunkte(X)
        m_e = 0.0
        for P, wi in zip(pts, w):
            for h_w, H in seiten:
                m_e += wi * westergaard(H, h_w - float(P[2]), wd.rho)
        if m_e <= 0:
            continue
        m_ges += m_e
        A_ges += A
        try:
            m_str += model.materials[e.mat].rho * model.shells[e.sec].t * A
        except (KeyError, AttributeError):
            pass
        block = m_e / len(e.nodes) * np.outer(n, n)
        for k in e.nodes:
            d0 = NDOF * int(k)
            for a in range(3):
                for b in range(3):
                    if block[a, b] != 0.0:
                        rows.append(d0 + a)
                        cols.append(d0 + b)
                        vals.append(block[a, b])
    M = sparse.coo_matrix((np.array(vals, float), (np.array(rows, int), np.array(cols, int))),
                          shape=(n_all, n_all)).tocsr() if vals else sparse.csr_matrix((n_all, n_all))
    info = {"m_hydro": m_ges, "m_struktur": m_str, "A": A_ges,
            "m_hydro_theorie": westergaard_gesamt(seiten[0][1], wd.rho) * g["breite"]
            + (westergaard_gesamt(seiten[1][1], wd.rho) * g["breite"] if len(seiten) > 1 else 0.0),
            "H_ow": seiten[0][1], "H_uw": seiten[1][1] if len(seiten) > 1 else None,
            "elemente": len(elemente)}
    return M, info


def modale_massen(res, M_s, M_add) -> list:
    """Je Eigenform φ: (φᵀ·M_s·φ, φᵀ·M_h·φ)."""
    out = []
    if res is None or getattr(res, "modes", None) is None:
        return out
    for phi in res.modes:
        v = np.asarray(phi, float).ravel()
        ms = float(v @ (M_s @ v))
        ma = float(v @ (M_add @ v)) if M_add is not None else 0.0
        out.append((ms, ma))
    return out


# ==========================================================================
# Nachweis
# ==========================================================================
def _kantenbreite(model, wd: Wasserdruck, sn: Schwingungsnachweis) -> float:
    if sn.d_kante:
        return float(sn.d_kante)
    for name in wd.flaechen:
        f = model.flaechen.get(name)
        if f is not None and f.dicke in model.shells:
            return float(model.shells[f.dicke].t)
    return 0.01


def _spannungsamplitude(res) -> float:
    """Größte Vergleichs- bzw. Randspannung eines Ergebnisses [Pa]."""
    s = 0.0
    try:
        for d in res.shell_stress.values():
            s = max(s, float(d["vM"]))
    except Exception:            # noqa: BLE001
        pass
    try:
        for d in res.beam_forces.values():
            s = max(s, abs(float(d.get("sig_max", 0.0))))
    except Exception:            # noqa: BLE001
        pass
    try:
        for d in res.solid_stress.values():
            s = max(s, float(np.max(d["vM"])))
    except Exception:            # noqa: BLE001
        pass
    return s


def beurteilen(mo: Mode, sn: Schwingungsnachweis, f_s: float) -> None:
    """Resonanzband und reduzierte Geschwindigkeit je Mode."""
    if f_s <= 0:
        mo.beurteilung = "keine Anregung (v = 0)"
        return
    if abs(mo.verhaeltnis - 1.0) <= sn.band:
        mo.kritisch = True
        mo.beurteilung = f"Resonanz: f_s im Band ±{sn.band * 100:.0f} % um f"
    elif mo.V_r > sn.vr_grenz:
        mo.hinweis = True
        mo.beurteilung = (f"V_r > {sn.vr_grenz:g}: instabilitäts-/bewegungsinduzierte Anregung "
                          "möglich")
    else:
        mo.beurteilung = f"V_r ≤ {sn.vr_grenz:g}: quasistatisch, unkritisch"


def nachweis(model, sn: Schwingungsnachweis, analysis=None, progress=None,
             workers: int = None) -> SchwingungsErgebnis:
    """Der Nachweis: Eigenfrequenzen trocken und nass, Anregung, Antwort."""
    from . import solver
    from . import assemble as asm
    wd = model.wasserdruecke.get(sn.wasserdruck) if getattr(model, "wasserdruecke", None) else None
    if wd is None:
        raise ValueError(f"Wasserdruck „{sn.wasserdruck}“ gibt es nicht - zuerst den Generierer anlegen")
    if not wd.flaechen:
        raise ValueError(f"Wasserdruck „{wd.name}“ hat keine benetzten Flächen")
    kw = wd_kennwerte(wd, model)
    erg = SchwingungsErgebnis(sn.name, wd.name, zeta=float(sn.zeta), strouhal=float(sn.strouhal),
                              vr_grenz=float(sn.vr_grenz), band=float(sn.band), kennwerte=kw)
    # Situation des Generierers
    aktiv = None
    m_s = model
    if wd.situation:
        from .situationen import situationsmodell
        m_s, aktiv, log = situationsmodell(model, wd.situation)
        erg.log += list(log or [])
    if progress:
        progress("Hydrodynamische Masse")
    M_add, info = (zusatzmassen(m_s, wd, kw) if sn.hydromasse else (None, {}))
    erg.m_hydro = float(info.get("m_hydro", 0.0))
    erg.m_struktur = float(info.get("m_struktur", 0.0))
    erg.m_hydro_theorie = float(info.get("m_hydro_theorie", 0.0))
    n = max(1, int(sn.n_moden))
    if progress:
        progress("Eigenfrequenzen in Luft")
    res_l = solver.solve_modal(m_s, n, progress=None, workers=workers, aktiv=aktiv)
    if M_add is not None and erg.m_hydro > 0:
        if progress:
            progress("Eigenfrequenzen im Wasser")
        res_w = solver.solve_modal(m_s, n, progress=None, workers=workers, aktiv=aktiv,
                                   zusatzmasse=M_add)
        res_w.name = f"Eigenschwingungen im Wasser ({wd.name})"
    else:
        res_w = res_l
    erg.res_luft, erg.res_wasser = res_l, res_w
    M_s = asm.mass(m_s, workers, aktiv)
    mm = modale_massen(res_w, M_s, M_add)
    # Anregung
    erg.v = float(kw.get("v_max", 0.0))
    erg.d = _kantenbreite(m_s, wd, sn)
    erg.f_s = strouhal_frequenz(sn.strouhal, erg.v, erg.d)
    erg.f_grenz = erg.v / (sn.vr_grenz * erg.d) if (erg.v > 0 and erg.d > 0 and sn.vr_grenz > 0) else 0.0
    k = min(len(res_l.freqs), len(res_w.freqs))
    for i in range(k):
        f_l, f_w = float(res_l.freqs[i]), float(res_w.freqs[i])
        ms, ma = mm[i] if i < len(mm) else (1.0, 0.0)
        mo = Mode(i + 1, f_l, f_w, mu=(ma / ms if ms > 0 else 0.0))
        if f_w > 0 and erg.v > 0:
            mo.V_r = reduzierte_geschwindigkeit(erg.v, f_w, erg.d)
            mo.verhaeltnis = erg.f_s / f_w
            mo.dlf = vergroesserung(mo.verhaeltnis, sn.zeta)
        beurteilen(mo, sn, erg.f_s)
        erg.moden.append(mo)
    # Dynamische Antwort auf die Druckschwankung
    dyn = {}
    if wd.lastfall_dyn and kw.get("dp_dyn", 0.0) > 0 and wd.lastfall_dyn in model.load_cases:
        res_d = None
        if analysis is not None:
            res_d = (getattr(analysis, "cases", {}) or {}).get(wd.lastfall_dyn)
        if res_d is None:
            if progress:
                progress(f"Lastfall {wd.lastfall_dyn} (Druckschwankung)")
            try:
                res_d = solver.solve_cases(model, [wd.lastfall_dyn], workers)[wd.lastfall_dyn]
            except Exception as ex:        # noqa: BLE001
                erg.log.append(f"Druckschwankung nicht gerechnet: {ex}")
        if res_d is not None and erg.moden:
            s_amp = _spannungsamplitude(res_d)
            f1 = erg.moden[0].f_wasser
            r = erg.f_s / f1 if (f1 > 0 and erg.f_s > 0) else 0.0
            V = vergroesserung(r, sn.zeta) if r > 0 else 1.0
            dyn = {"lastfall": wd.lastfall_dyn, "dp": float(kw["dp_dyn"]), "sigma_amp": s_amp,
                   "r": r, "V": V, "sigma_dyn": s_amp * V, "delta_sigma": 2.0 * s_amp * V,
                   "u_amp": float(np.max(res_d.umag)) if getattr(res_d, "u", None) is not None else 0.0}
            dyn["u_dyn"] = dyn["u_amp"] * V
            if sn.betriebsstunden > 0 and erg.f_s > 0:
                from .ec3.fatigue import sn_life
                N = erg.f_s * 3600.0 * float(sn.betriebsstunden) * float(sn.jahre)
                ds_Ed = float(sn.gamma_Ff) * dyn["delta_sigma"]
                N_R = sn_life(ds_Ed, float(sn.kerbfall) * 1e6, float(sn.gamma_Mf))
                D = N / N_R if np.isfinite(N_R) and N_R > 0 else 0.0
                dyn.update({"N": N, "delta_sigma_Ed": ds_Ed, "N_R": N_R, "D": D,
                            "kerbfall": float(sn.kerbfall), "gamma_Mf": float(sn.gamma_Mf),
                            "gamma_Ff": float(sn.gamma_Ff)})
    erg.dyn = dyn
    # Status
    if erg.v <= 0:
        erg.status = "erfüllt (keine Durchströmung, keine Anregung)"
    elif any(mo.kritisch for mo in erg.moden) or (dyn.get("D") is not None and dyn["D"] > 1.0):
        erg.status = "nicht erfüllt"
    elif any(mo.hinweis for mo in erg.moden):
        erg.status = "erfüllt mit Hinweis (V_r über der Grenze)"
    else:
        erg.status = "erfüllt"
    erg.log += erlaeuterung(erg, sn)
    return erg


# ==========================================================================
# Erläuterung und Skizze
# ==========================================================================
def erlaeuterung(erg: SchwingungsErgebnis, sn: Schwingungsnachweis = None) -> list:
    kw = erg.kennwerte
    z = []
    if erg.m_hydro > 0:
        z.append(f"Hydrodynamische Masse nach Westergaard m'' = 7/8·ρ·√(H·y): {erg.m_hydro:.0f} kg auf "
                 f"den benetzten Flächen (Theorie 7/12·ρ·H²·b = {erg.m_hydro_theorie:.0f} kg), "
                 f"Haut {erg.m_struktur:.0f} kg - Verhältnis {erg.m_hydro / max(erg.m_struktur, 1e-9):.2f}; "
                 "sie wirkt in Richtung der Flächennormalen.")
    else:
        z.append("Ohne hydrodynamische Masse gerechnet (Eigenfrequenzen wie in Luft).")
    if erg.moden:
        m1 = erg.moden[0]
        z.append(f"Grundfrequenz f₁ = {m1.f_luft:.2f} Hz in Luft, {m1.f_wasser:.2f} Hz im Wasser "
                 f"(modales Massenverhältnis m_h/m = {m1.mu:.2f}, Abminderung 1/√(1 + m_h/m) = "
                 f"{1 / math.sqrt(1 + m1.mu):.3f}).")
    if erg.v > 0:
        quelle = []
        if kw.get("v_a", 0) > 0:
            quelle.append(f"Ausflussstrahl v_a = {kw['v_a']:.2f} m/s")
        if kw.get("v_c", 0) > 0:
            quelle.append(f"Überfall v_c = {kw['v_c']:.2f} m/s")
        z.append(f"Strömungsgeschwindigkeit v = {erg.v:.2f} m/s ({', '.join(quelle) or 'aus dem Wasserdruck'}); "
                 f"Kantenbreite d = {erg.d * 1e3:.0f} mm; Wirbelablösung f_s = St·v/d = "
                 f"{erg.strouhal:g}·{erg.v:.2f}/{erg.d:.3f} = {erg.f_s:.2f} Hz.")
        z.append(f"Reduzierte Geschwindigkeit V_r = v/(f·d): unkritisch für V_r ≤ {erg.vr_grenz:g}, "
                 f"also für Eigenfrequenzen f ≥ {erg.f_grenz:.2f} Hz; Resonanz mit der Wirbelablösung "
                 f"im Band ±{erg.band * 100:.0f} % um f_s "
                 f"({erg.f_s * (1 - erg.band):.2f} … {erg.f_s * (1 + erg.band):.2f} Hz).")
        krit = [mo.nr for mo in erg.moden if mo.kritisch]
        hinw = [mo.nr for mo in erg.moden if mo.hinweis]
        if krit:
            z.append("Resonanzgefahr bei Mode " + ", ".join(map(str, krit))
                     + ": Eigenfrequenz verschieben (Steifigkeit, Masse), Kante ändern (d, St) oder "
                       "Dämpfung erhöhen.")
        if hinw:
            z.append("V_r über der Grenze bei Mode " + ", ".join(map(str, hinw))
                     + ": bewegungs- oder instabilitätsinduzierte Schwingungen (Kolkman, Naudascher) "
                       "sind nicht auszuschließen - scharfkantige, steife Unterkante, Dichtung "
                       "stromauf, kein Unterdruck hinter der Kante; sonst Modellversuch/Messung.")
    else:
        z.append("Keine Durch- oder Überströmung im gewählten Wasserdruck (v = 0): keine "
                 "strömungsinduzierte Anregung; die Eigenfrequenzen dienen der Einordnung.")
    d = erg.dyn
    if d:
        z.append(f"Druckschwankung Δp = {d['dp'] / 1e3:.3f} kN/m² (Lastfall {d['lastfall']}): statische "
                 f"Amplitude σ_amp = {d['sigma_amp'] / 1e6:.1f} N/mm², Vergrößerung V = "
                 f"{d['V']:.2f} bei r = f_s/f₁ = {d['r']:.2f} und ζ = {erg.zeta:g}: "
                 f"σ_dyn = {d['sigma_dyn'] / 1e6:.1f} N/mm², Δσ = {d['delta_sigma'] / 1e6:.1f} N/mm², "
                 f"Verformungsamplitude {d['u_dyn'] * 1e3:.2f} mm.")
        if "N" in d:
            z.append(f"Ermüdung: N = f_s·t = {d['N']:.3g} Lastspiele, Δσ_Ed = γ_Ff·Δσ = "
                     f"{d['delta_sigma_Ed'] / 1e6:.1f} N/mm², Kerbfall {d['kerbfall']:g} "
                     f"(γ_Mf = {d['gamma_Mf']:g}): N_R = "
                     + ("∞" if not np.isfinite(d["N_R"]) else f"{d['N_R']:.3g}")
                     + f", D = N/N_R = {d['D']:.3f} " + ("≤ 1 erfüllt" if d["D"] <= 1 else "> 1 nicht erfüllt") + ".")
        else:
            z.append("Ermüdung nicht bewertet: keine Betriebsdauer (Stunden je Jahr) angegeben.")
    z.append(f"Ergebnis: {erg.status}.")
    return z


def skizze_svg(erg: SchwingungsErgebnis, breite: int = 620, hoehe: int = 300) -> str:
    """Links das Frequenzbild (Eigenfrequenzen trocken/nass, Wirbelablösung,
    Grenze V_r), rechts die hydrodynamische Masse über die Höhe."""
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{breite}" height="{hoehe}" '
         f'viewBox="0 0 {breite} {hoehe}" font-family="sans-serif" font-size="11">',
         f'<rect width="{breite}" height="{hoehe}" fill="#fff"/>']
    x0, y0, W, H = 40, hoehe - 50, 330, hoehe - 100
    fs = [mo.f_luft for mo in erg.moden] + [mo.f_wasser for mo in erg.moden]
    if erg.f_s > 0:
        fs += [erg.f_s * (1 - erg.band), erg.f_s * (1 + erg.band)]
    if erg.f_grenz > 0:
        fs.append(erg.f_grenz)
    fs = [f for f in fs if f > 0] or [1.0]
    lo, hi = math.log10(min(fs) / 2.0), math.log10(max(fs) * 2.0)
    if hi - lo < 1.0:
        mid = (hi + lo) / 2
        lo, hi = mid - 0.5, mid + 0.5

    def X(f):
        return x0 + (math.log10(f) - lo) / (hi - lo) * W

    if erg.f_grenz > 0:
        xg = min(max(X(erg.f_grenz), x0), x0 + W)
        s.append(f'<rect x="{xg:.1f}" y="{y0 - H}" width="{x0 + W - xg:.1f}" height="{H}" fill="#e6f4ea"/>')
        s.append(f'<line x1="{xg:.1f}" y1="{y0 - H}" x2="{xg:.1f}" y2="{y0}" stroke="#2e7d32" stroke-dasharray="4 3"/>')
        s.append(f'<text x="{xg + 3:.1f}" y="{y0 - H + 12}" fill="#2e7d32" font-size="10">V_r ≤ {erg.vr_grenz:g}</text>')
    if erg.f_s > 0:
        xa, xb = X(erg.f_s * (1 - erg.band)), X(erg.f_s * (1 + erg.band))
        s.append(f'<rect x="{xa:.1f}" y="{y0 - H}" width="{xb - xa:.1f}" height="{H}" fill="#c62828" opacity="0.18"/>')
        s.append(f'<line x1="{X(erg.f_s):.1f}" y1="{y0 - H}" x2="{X(erg.f_s):.1f}" y2="{y0}" stroke="#c62828" stroke-width="1.5"/>')
        s.append(f'<text x="{X(erg.f_s):.1f}" y="{y0 - H - 4}" fill="#c62828" text-anchor="middle" font-size="10">f_s = {erg.f_s:.2f} Hz</text>')
    s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0 + W}" y2="{y0}" stroke="#666"/>')
    dec = range(int(math.floor(lo)), int(math.ceil(hi)) + 1)
    for e in dec:
        for k in (1, 2, 5):
            f = k * 10.0 ** e
            if lo <= math.log10(f) <= hi:
                s.append(f'<line x1="{X(f):.1f}" y1="{y0}" x2="{X(f):.1f}" y2="{y0 + 4}" stroke="#666"/>')
                s.append(f'<text x="{X(f):.1f}" y="{y0 + 15}" text-anchor="middle" font-size="9">{f:g}</text>')
    s.append(f'<text x="{x0 + W}" y="{y0 + 30}" text-anchor="end">f [Hz], logarithmisch</text>')
    for mo in erg.moden:
        xl, xw = X(mo.f_luft), X(mo.f_wasser)
        s.append(f'<line x1="{xl:.1f}" y1="{y0 - H * 0.45}" x2="{xl:.1f}" y2="{y0}" stroke="#9aa5b1" stroke-dasharray="3 2"/>')
        farbe = "#c62828" if mo.kritisch else ("#e5701c" if mo.hinweis else "#1467c6")
        s.append(f'<line x1="{xw:.1f}" y1="{y0 - H * 0.7}" x2="{xw:.1f}" y2="{y0}" stroke="{farbe}" stroke-width="2"/>')
        s.append(f'<text x="{xw:.1f}" y="{y0 - H * 0.7 - 3}" text-anchor="middle" fill="{farbe}" font-size="10">{mo.nr}</text>')
    s.append(f'<text x="{x0}" y="18">Frequenzbild: Eigenfrequenzen im Wasser (farbig) und in Luft (grau)</text>')
    # Rechts: Westergaard-Verteilung
    gx, gy, GW, GH = 420, 50, 160, hoehe - 100
    kw = erg.kennwerte
    H_w = max(float(kw.get("h_ow", 0.0)) - float(kw.get("z_uk", 0.0)), 0.0)
    hg = max(float(kw.get("z_ok", 1.0)) - float(kw.get("z_uk", 0.0)), 1e-6)
    sc = GH / max(hg, H_w, 1e-6)
    yb = gy + GH
    s.append(f'<rect x="{gx + GW - 14}" y="{yb - hg * sc:.1f}" width="14" height="{hg * sc:.1f}" fill="#d9dee3" stroke="#1d2731"/>')
    if H_w > 0:
        s.append(f'<line x1="{gx}" y1="{yb - H_w * sc:.1f}" x2="{gx + GW - 14}" y2="{yb - H_w * sc:.1f}" stroke="#1467c6"/>')
        pts = []
        for k in range(41):
            y = H_w * k / 40.0
            m = westergaard(H_w, y, float(kw.get("rho", 1000.0)))
            m_max = westergaard(H_w, H_w, float(kw.get("rho", 1000.0))) or 1.0
            pts.append(f"{gx + GW - 14 - m / m_max * (GW - 30):.1f},{yb - (H_w - y) * sc:.1f}")
        s.append(f'<polygon points="{gx + GW - 14},{yb - H_w * sc:.1f} ' + " ".join(pts)
                 + f' {gx + GW - 14},{yb}" fill="#1467c6" opacity="0.25" stroke="#1467c6"/>')
        s.append(f'<text x="{gx}" y="{yb - H_w * sc - 4:.1f}" fill="#1467c6" font-size="10">OW, H = {H_w:.2f} m</text>')
    s.append(f'<line x1="{gx - 10}" y1="{yb}" x2="{gx + GW + 10}" y2="{yb}" stroke="#666"/>')
    s.append(f'<text x="{gx}" y="18">Hydrodynamische Masse</text>')
    s.append(f'<text x="{gx}" y="{yb + 16}" font-size="10">m\'\' = 7/8·ρ·√(H·y) (Westergaard)</text>')
    s.append(f'<text x="{gx}" y="{yb + 30}" font-size="10">Σ = 7/12·ρ·H² je m Breite</text>')
    s.append('</svg>')
    return "\n".join(s)
