"""
Theorie II. Ordnung und Ersatzimperfektionen nach DIN EN 1993-1-1, 5.2 und 5.3.

Drei Dinge stecken hier drin:

1. **alpha_cr** je Kombination aus dem linearen Verzweigungsproblem
   (K + lambda K_g) v = 0 mit dem Spannungszustand der Kombination als
   Grundzustand.  Nach 5.2.1(3) darf nach Theorie I. Ordnung gerechnet
   werden, solange

        alpha_cr = F_cr / F_Ed >= 10   (elastische Berechnung)
        alpha_cr >= 15                 (plastische Berechnung)

2. **Ersatzimperfektionen** nach 5.3.2.  Statt die Geometrie zu verziehen
   werden nach 5.3.2(7) aequivalente Lasten angesetzt - das ist gleichwertig
   und laesst das Netz unberuehrt:

        Schiefstellung  phi = phi_0 alpha_h alpha_m       (5.3.2(3)a)
                        H_Ed = phi N_Ed  je Stiel, als Kraeftepaar
        Vorkruemmung    e_0 nach Tab. 5.1 je Knicklinie
                        q = 8 N_Ed e_0 / L^2 quer zum Stab,
                        dazu die Endquerkraefte 4 N_Ed e_0 / L

   phi_0 = 1/200; alpha_h = 2/sqrt(h) mit 2/3 <= alpha_h <= 1,0;
   alpha_m = sqrt(0,5 (1 + 1/m)).  h ist die Bauwerkshoehe, m die Zahl der
   Stiele einer Reihe, die mindestens 50 % der mittleren Stielnormalkraft
   tragen (5.3.2(3)) - deshalb wird m je Kombination aus den Normalkraeften
   bestimmt, nicht geraten.

3. **Gleichgewicht am verformten System**: (K + K_g(N)) u = F, iterativ, weil
   K_g von den Normalkraeften abhaengt und diese von u.  Die Normalkraefte
   und die Ersatzlasten werden in jedem Schritt neu gebildet.

Wichtig und im Bericht gesagt: nach Theorie II. Ordnung gilt die
**Superposition nicht mehr**.  Jede Kombination wird einzeln gerechnet;
Ergebnisse duerfen nicht mehr aus Lastfallergebnissen ueberlagert werden.

Nicht enthalten: Theorie III. Ordnung (grosse Verformungen), Fliessgelenke,
die Imperfektionsform aus der Knickeigenform nach 5.3.2(11) (dafuer wird die
Eigenform zwar berechnet, aber nur als alpha_cr ausgewertet), und
Imperfektionen fuer Aussteifungsverbaende nach 5.3.3.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from . import assemble as asm
from .elements import beam3d as bm
from .model import Model

NDOF = 6

#: Vorkruemmung e_0/L nach Tabelle 5.1, je Knicklinie
E0_ELASTISCH = {"a0": 1 / 350, "a": 1 / 300, "b": 1 / 250, "c": 1 / 200, "d": 1 / 150}
E0_PLASTISCH = {"a0": 1 / 300, "a": 1 / 250, "b": 1 / 200, "c": 1 / 150, "d": 1 / 100}

PHI_0 = 1.0 / 200.0

#: Ab welchem Winkel zur Lotrechten ein Stab noch als Stiel gilt [Grad]
STIEL_WINKEL = 30.0


# ==========================================================================
# Ersatzimperfektionen (5.3.2)
# ==========================================================================
def alpha_h(h: float) -> float:
    """Abminderung nach der Bauwerkshoehe, 5.3.2(3)a: 2/sqrt(h), 2/3 <= a_h <= 1."""
    if h <= 0:
        return 1.0
    return float(min(max(2.0 / math.sqrt(h), 2.0 / 3.0), 1.0))


def alpha_m(m: int) -> float:
    """Abminderung nach der Stielzahl, 5.3.2(3)a: sqrt(0,5 (1 + 1/m))."""
    m = max(int(m), 1)
    return float(math.sqrt(0.5 * (1.0 + 1.0 / m)))


def schiefstellung(h: float, m: int, phi_0: float = PHI_0) -> dict:
    """Schiefstellung phi = phi_0 alpha_h alpha_m mit allen Zwischenwerten."""
    ah, am = alpha_h(h), alpha_m(m)
    return {"phi_0": phi_0, "h": float(h), "m": int(m), "alpha_h": ah,
            "alpha_m": am, "phi": float(phi_0 * ah * am)}


def e0_durch_L(kurve: str, elastisch: bool = True) -> float:
    """Vorkruemmung e_0/L nach Tabelle 5.1."""
    tab = E0_ELASTISCH if elastisch else E0_PLASTISCH
    return tab.get(kurve, tab["c"])


# --------------------------------------------------------------------------
def _elementachse(model: Model, e):
    X = model.nodes[e.nodes]
    v = np.asarray(X[1], float) - np.asarray(X[0], float)
    L = float(np.linalg.norm(v))
    return (v / L if L > 0 else v), L


def stiele(model: Model) -> dict:
    """
    Stiele des Tragwerks: Staebe, deren Achse hoechstens ``STIEL_WINKEL`` von
    der Lotrechten abweicht.  Rueckgabe {Stabname: (Elementliste, Laenge)}.
    """
    grenze = math.cos(math.radians(STIEL_WINKEL))
    out = {}
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        e = model.elements[mem.elements[0]]
        if e.typ not in ("beam", "truss"):
            continue
        v, _ = _elementachse(model, e)
        if abs(v[2]) >= grenze:
            L = model.member_length(mem)
            out[name] = (list(mem.elements), L)
    return out


def bauwerkshoehe(model: Model) -> float:
    """Hoehe des Tragwerks aus der Bounding-Box (z-Richtung)."""
    lo, hi = model.bbox()
    return float(hi[2] - lo[2])


def _member_N(model: Model, mem, res) -> float:
    """Mittlere Normalkraft eines Stabes [N], Druck negativ (wie im Ergebnis)."""
    try:
        mf = res.member_forces(mem, 3)
    except Exception:
        return 0.0
    return float(np.mean(mf["N"]))


def stielkraefte(model: Model, res) -> dict:
    """Normalkraft je Stiel; nur Druck zaehlt (Zugstiele bekommen keine
    Ersatzlast aus der Schiefstellung)."""
    out = {}
    for name, (_els, _L) in stiele(model).items():
        N = _member_N(model, model.members[name], res)
        if N < 0:
            out[name] = -N            # Druck positiv
    return out


def massgebende_stiele(kraefte: dict) -> list:
    """
    Stiele, die mindestens 50 % der mittleren Stielnormalkraft tragen
    (5.3.2(3)): nur sie zaehlen fuer m.
    """
    if not kraefte:
        return []
    mittel = sum(kraefte.values()) / len(kraefte)
    return [k for k, v in kraefte.items() if v >= 0.5 * mittel]


def imperfektionsrichtung(model: Model, res, vorgabe=None) -> np.ndarray:
    """
    Richtung der Schiefstellung in der Grundrissebene, 5.3.2(4).

    Die Schiefstellung wirkt in der **massgebenden waagerechten Richtung**,
    nicht gleichzeitig in beiden.  Massgebend ist die Richtung, in die sich
    das Tragwerk ohnehin verschiebt: gemittelt ueber die gedrueckten Stiele
    wird die waagerechte Verschiebung des Kopfes gegen den Fuss gebildet.  So
    wirkt die Ersatzlast immer unguenstig.  Verschiebt sich nichts (reine
    Vertikallast am symmetrischen System), wird die globale x-Richtung
    genommen; ``vorgabe`` ueberschreibt die Wahl.
    """
    if vorgabe is not None:
        v = np.asarray(vorgabe, float).ravel()[:2]
        n = float(np.linalg.norm(v))
        if n > 0:
            return np.array([v[0] / n, v[1] / n, 0.0])
    u = getattr(res, "u", None)
    if u is not None:
        u = np.asarray(u, float)
        v = np.zeros(2)
        for name, (els, _L) in stiele(model).items():
            ea, eb = model.elements[els[0]], model.elements[els[-1]]
            na, nb = int(ea.nodes[0]), int(eb.nodes[-1])
            if model.nodes[na][2] > model.nodes[nb][2]:
                na, nb = nb, na
            if nb < u.shape[0] and na < u.shape[0]:
                v += u[nb, :2] - u[na, :2]
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            return np.array([v[0] / n, v[1] / n, 0.0])
        # keine Stiele: groesste waagerechte Verschiebung ueberhaupt
        if u.ndim == 2 and u.shape[0]:
            k = int(np.argmax(np.abs(u[:, 0]) + np.abs(u[:, 1])))
            w = u[k, :2]
            n = float(np.linalg.norm(w))
            if n > 1e-12:
                return np.array([w[0] / n, w[1] / n, 0.0])
    return np.array([1.0, 0.0, 0.0])


def ersatzlasten_schiefstellung(model: Model, res, richtung=None) -> tuple:
    """
    Aequivalente Horizontalkraefte aus der Schiefstellung, 5.3.2(7).

    Je Stiel wird H = phi N_Ed am Kopf in Richtung der Schiefstellung
    angesetzt und am Fuss abgezogen - das ergibt genau das Kraeftepaar aus
    Bild 5.3 und laesst die Summe der Auflagerkraefte unberuehrt.

    Rueckgabe (F, info) mit F als Lastvektor ueber alle FHG.
    """
    F = np.zeros(model.ndof)
    kraefte = stielkraefte(model, res)
    if not kraefte:
        return F, {"phi": 0.0, "je_stiel": [], "H_gesamt": 0.0,
                   "hinweis": "keine gedrückten Stiele gefunden - "
                              "keine Schiefstellung angesetzt"}
    m = len(massgebende_stiele(kraefte))
    h = bauwerkshoehe(model)
    sk = schiefstellung(h, m)
    phi = sk["phi"]
    d = imperfektionsrichtung(model, res, richtung)
    je_stiel = []
    for name, N in kraefte.items():
        mem = model.members[name]
        ea = model.elements[mem.elements[0]]
        eb = model.elements[mem.elements[-1]]
        n_unten, n_oben = int(ea.nodes[0]), int(eb.nodes[-1])
        if model.nodes[n_unten][2] > model.nodes[n_oben][2]:
            n_unten, n_oben = n_oben, n_unten
        H = phi * N
        F[n_oben * NDOF:n_oben * NDOF + 3] += H * d
        F[n_unten * NDOF:n_unten * NDOF + 3] -= H * d
        je_stiel.append({"stab": name, "N_Ed": N, "H_Ed": H,
                         "knoten_oben": n_oben, "knoten_unten": n_unten})
    sk["je_stiel"] = je_stiel
    sk["richtung"] = [float(x) for x in d]
    sk["H_gesamt"] = float(sum(x["H_Ed"] for x in je_stiel))
    return F, sk


def _knicklinie(model: Model, mem) -> tuple:
    """(Knicklinie, Section, f_y) fuer die schwache Achse."""
    from .ec3.stability import buckling_curve
    e = model.elements[mem.elements[0]]
    sec = model.sections.get(e.sec)
    mat = model.materials.get(e.mat)
    if sec is None or mat is None:
        return "c", sec, 235e6
    fy = mat.yield_strength(sec.t_max) or 235e6
    return buckling_curve(sec, fy, "z"), sec, fy


def vorkruemmung_noetig(model: Model, mem, Nc: float) -> dict:
    """
    Kriterium 5.3.2(6): die Vorkruemmung eines Einzelstabes ist nur
    anzusetzen, wenn der Stab biegesteif angeschlossen und schlank genug ist:

        lambda_quer > 0,5 sqrt(A f_y / N_Ed)

    lambda_quer wird um die schwache Achse mit der Knicklaenge L_cr,z des
    Stabes gebildet.
    """
    kurve, sec, fy = _knicklinie(model, mem)
    if sec is None or Nc <= 0:
        return {"noetig": False, "grund": "keine Druckkraft"}
    e = model.elements[mem.elements[0]]
    mat = model.materials.get(e.mat)
    L = model.member_length(mem)
    Lcr = mem.Lcr_z if mem.Lcr_z else mem.beta_z * L
    if Lcr <= 0 or sec.Iz <= 0 or mat is None:
        return {"noetig": True, "grund": "Knicklänge unbekannt - "
                                         "auf der sicheren Seite angesetzt"}
    Ncr = math.pi ** 2 * mat.E * sec.Iz / Lcr ** 2
    lam = math.sqrt(sec.A * fy / Ncr) if Ncr > 0 else 0.0
    grenze = 0.5 * math.sqrt(sec.A * fy / Nc)
    return {"noetig": lam > grenze, "lambda": lam, "grenze": grenze,
            "kurve": kurve, "L_cr": Lcr,
            "grund": (f"λ̄ = {lam:.3f} > 0,5 √(A f_y/N_Ed) = {grenze:.3f}"
                      if lam > grenze else
                      f"λ̄ = {lam:.3f} ≤ 0,5 √(A f_y/N_Ed) = {grenze:.3f} → "
                      "nach 5.3.2(6) nicht erforderlich")}


def ersatzlasten_vorkruemmung(model: Model, res, elastisch: bool = True,
                              alle: bool = False) -> tuple:
    """
    Aequivalente Querlasten aus der Vorkruemmung, 5.3.2(7), Bild 5.4:

        q = 8 N_Ed e_0 / L^2   ueber die Stablaenge, quer zur Stabachse
        V = 4 N_Ed e_0 / L     an beiden Enden entgegengesetzt

    Angesetzt wird in der lokalen **y**-Richtung des Stabes: e_0 stammt aus
    der Knicklinie fuer die schwache Achse z, und Knicken um z bedeutet
    Ausweichen in y.  Nur gedrueckte Staebe bekommen eine Vorkruemmung, und
    nur die nach 5.3.2(6) schlanken (``alle=True`` setzt sie fuer alle an).
    """
    F = np.zeros(model.ndof)
    je_stab, uebersprungen = [], []
    for name, mem in model.members.items():
        if not mem.elements:
            continue
        if model.elements[mem.elements[0]].typ not in ("beam", "truss"):
            continue
        N = _member_N(model, mem, res)
        if N >= 0:                              # Zug: keine Vorkruemmung
            continue
        Nc = -N
        L = model.member_length(mem)
        if L <= 0:
            continue
        krit = vorkruemmung_noetig(model, mem, Nc)
        if not alle and not krit["noetig"]:
            uebersprungen.append({"stab": name, "grund": krit["grund"]})
            continue
        kurve, _sec, _fy = _knicklinie(model, mem)
        e0 = e0_durch_L(kurve, elastisch) * L
        q = 8.0 * Nc * e0 / L ** 2
        for ie in mem.elements:
            el = model.elements[ie]
            T3, Le = bm.local_axes(model.nodes[el.nodes[0]],
                                   model.nodes[el.nodes[1]], el.roll)
            ny = T3[1]                            # lokale y-Achse global
            fk = 0.5 * q * Le
            for nd in (int(el.nodes[0]), int(el.nodes[1])):
                F[nd * NDOF:nd * NDOF + 3] += fk * ny
        ea = model.elements[mem.elements[0]]
        T3a, _ = bm.local_axes(model.nodes[ea.nodes[0]], model.nodes[ea.nodes[1]],
                               ea.roll)
        na = int(ea.nodes[0])
        nb = int(model.elements[mem.elements[-1]].nodes[-1])
        V = 4.0 * Nc * e0 / L
        F[na * NDOF:na * NDOF + 3] -= V * T3a[1]
        F[nb * NDOF:nb * NDOF + 3] -= V * T3a[1]
        je_stab.append({"stab": name, "L": L, "kurve": kurve, "e0_L": e0 / L,
                        "e_0": e0, "N_Ed": Nc, "q": q, "V": V,
                        "lambda": krit.get("lambda", 0.0),
                        "grenze": krit.get("grenze", 0.0)})
    return F, {"je_stab": je_stab, "uebersprungen": uebersprungen,
               "elastisch": elastisch, "anzahl": len(je_stab)}


# ==========================================================================
# alpha_cr (5.2.1)
# ==========================================================================
def alpha_cr(model: Model, system, u: np.ndarray, nmodes: int = 1) -> dict:
    """
    Kleinster Verzweigungslastfaktor zum Verformungszustand ``u``.

    Rueckgabe {"alpha_cr": ..., "modus": Eigenvektor, "fehler": ""}.
    """
    from scipy.sparse.linalg import eigsh
    Kg = asm.geometric_stiffness(model, u)
    fi = system.fi
    Kgff = Kg[fi][:, fi].tocsc()
    if Kgff.shape[0] < 3 or abs(Kgff).max() == 0:
        return {"alpha_cr": math.inf, "fehler": "keine Normalkräfte - "
                                                "kein Verzweigungsproblem"}
    try:
        k = max(1, min(nmodes, Kgff.shape[0] - 2))
        vals, vecs = eigsh(system.Kff, k=k, M=-Kgff, sigma=0.0, which="LM")
    except Exception as exc:                       # pragma: no cover
        return {"alpha_cr": math.inf, "fehler": f"Eigenwertlöser: {exc}"}
    pos = [v for v in np.atleast_1d(vals) if v > 1e-9]
    if not pos:
        return {"alpha_cr": math.inf,
                "fehler": "kein positiver Verzweigungslastfaktor"}
    j = int(np.argmin(np.abs(vals - min(pos))))
    modus = np.zeros(model.ndof)
    modus[fi] = vecs[:, j]
    mx = float(np.abs(modus).max())
    if mx > 0:
        modus /= mx
    return {"alpha_cr": float(min(pos)), "modus": modus, "fehler": ""}


def erforderlich(a_cr: float, plastisch: bool = False) -> dict:
    """Kriterium 5.2.1(3): Theorie II. Ordnung noetig?"""
    grenze = 15.0 if plastisch else 10.0
    return {"alpha_cr": a_cr, "grenze": grenze, "noetig": a_cr < grenze,
            "text": (f"α_cr = {a_cr:.2f} < {grenze:.0f} → Theorie II. Ordnung "
                     "erforderlich (5.2.1(3))" if a_cr < grenze else
                     f"α_cr = {a_cr:.2f} ≥ {grenze:.0f} → Theorie I. Ordnung "
                     "ausreichend (5.2.1(3))")}


# ==========================================================================
# Gleichgewicht am verformten System
# ==========================================================================
@dataclass
class Th2Info:
    """Was bei einer Kombination nach Theorie II. Ordnung passiert ist."""
    kombination: str = ""
    alpha_cr: float = math.inf
    grenze: float = 10.0
    gerechnet: bool = False
    iterationen: int = 0
    konvergenz: float = 0.0
    schiefstellung: dict = field(default_factory=dict)
    vorkruemmung: dict = field(default_factory=dict)
    u_max_I: float = 0.0
    u_max_II: float = 0.0
    zuwachs: float = 0.0
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def text(self) -> str:
        if self.fehler:
            return f"nicht geführt: {self.fehler}"
        if not self.gerechnet:
            return erforderlich(self.alpha_cr, self.grenze > 10.0)["text"]
        return (f"Theorie II. Ordnung, {self.iterationen} Iterationen, "
                f"Verformungszuwachs {self.zuwachs * 100:+.1f} %")


def solve_theorie2(model: Model, factors: dict, name: str, system=None,
                   imperfektionen: bool = True, elastisch: bool = True,
                   max_iter: int = 30, tol: float = 1e-6,
                   richtung=None, alle_vorkruemmungen: bool = False,
                   progress=None):
    """
    Eine Kombination am verformten System rechnen.

    Vorgehen:
      1. Loesung nach Theorie I. Ordnung (Grundzustand)
      2. alpha_cr dazu bestimmen
      3. iterativ: Normalkraefte -> K_g und Ersatzlasten -> neue Loesung,
         bis sich die Verformungen nicht mehr aendern

    Rueckgabe (Results, Th2Info).
    """
    from .solver import StaticSystem, case_loads, postprocess, Results
    t0 = time.time()
    system = system or StaticSystem(model)
    F, feq, q, temp = case_loads(model, factors)

    # --- Theorie I. Ordnung als Ausgangspunkt
    u1 = system.solve(F)
    res1 = Results(name=name, kind="combination", model=model)
    res1.u = u1.reshape(-1, NDOF)
    res1.reactions = system.reactions(u1, F).reshape(-1, NDOF)
    postprocess(model, u1, res1, feq, q, temp)

    info = Th2Info(kombination=name, u_max_I=float(np.abs(u1).max()))
    ac = alpha_cr(model, system, u1)
    info.alpha_cr = ac["alpha_cr"]
    if ac.get("fehler"):
        info.hinweise.append(ac["fehler"])

    u = u1.copy()
    res = res1
    Fges = F.copy()
    for it in range(1, max_iter + 1):
        Fimp = np.zeros(model.ndof)
        if imperfektionen:
            Fs, s_info = ersatzlasten_schiefstellung(model, res, richtung)
            Fv, v_info = ersatzlasten_vorkruemmung(model, res, elastisch,
                                                   alle=alle_vorkruemmungen)
            Fimp = Fs + Fv
            info.schiefstellung, info.vorkruemmung = s_info, v_info
        Fges = F + Fimp
        Kg = asm.geometric_stiffness(model, u)
        try:
            u_neu = system.solve(Fges, K_extra=Kg)
        except Exception as exc:
            info.fehler = f"Gleichungssystem singulär (α_cr ≈ 1?): {exc}"
            break
        d = float(np.abs(u_neu - u).max())
        bezug = max(float(np.abs(u_neu).max()), 1e-12)
        u = u_neu
        res = Results(name=name, kind="combination", model=model)
        res.u = u.reshape(-1, NDOF)
        res.reactions = system.reactions(u, Fges, K_extra=Kg).reshape(-1, NDOF)
        postprocess(model, u, res, feq, q, temp)
        info.iterationen = it
        info.konvergenz = d / bezug
        if d / bezug < tol:
            break
    else:
        info.hinweise.append(
            f"Die Iteration ist nach {max_iter} Schritten nicht konvergiert "
            f"(letzte Änderung {info.konvergenz * 100:.3f} %). Das Tragwerk ist "
            "sehr verformungsweich - α_cr prüfen.")

    info.gerechnet = not info.fehler
    info.u_max_II = float(np.abs(u).max())
    if info.u_max_I > 0:
        info.zuwachs = info.u_max_II / info.u_max_I - 1.0
    res.info.update({"typ": model.combinations[name].typ if name in model.combinations else "",
                     "theorie": "II. Ordnung", "alpha_cr": info.alpha_cr,
                     "iterationen": info.iterationen, "time": time.time() - t0,
                     "factors": dict(factors), "solver": system.backend,
                     "ndof": model.ndof, "nfree": len(system.fi)})
    if progress:
        progress(f"{name}: Theorie II. Ordnung, {info.iterationen} Iterationen")
    return res, info


# ==========================================================================
# Ergebnisse ueber alle Kombinationen
# ==========================================================================
@dataclass
class Th2Results:
    """Sammlung der Theorie-II-Informationen aller Kombinationen."""
    kombinationen: dict = field(default_factory=dict)     # name -> Th2Info
    settings: dict = field(default_factory=dict)

    @property
    def alpha_cr_min(self) -> float:
        w = [i.alpha_cr for i in self.kombinationen.values()
             if math.isfinite(i.alpha_cr)]
        return min(w) if w else math.inf

    @property
    def zuwachs_max(self) -> float:
        return max((i.zuwachs for i in self.kombinationen.values()), default=0.0)

    def summary(self) -> str:
        if not self.kombinationen:
            return "Theorie II. Ordnung: nicht gerechnet"
        n2 = sum(1 for i in self.kombinationen.values() if i.gerechnet)
        a = self.alpha_cr_min
        s = (f"Theorie II. Ordnung: {n2} von {len(self.kombinationen)} Kombinationen "
             f"am verformten System")
        if math.isfinite(a):
            s += f", min. α_cr = {a:.2f}"
        if n2:
            s += f", max. Verformungszuwachs {self.zuwachs_max * 100:+.1f} %"
        fehler = [n for n, i in self.kombinationen.items() if i.fehler]
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Kombination", "α_cr", "Grenze", "Verfahren", "Iterationen",
                 "u_I [mm]", "u_II [mm]", "Zuwachs"]]
        for n, i in self.kombinationen.items():
            rows.append([n, f"{i.alpha_cr:.2f}" if math.isfinite(i.alpha_cr) else "∞",
                         f"{i.grenze:.0f}",
                         "II. Ordnung" if i.gerechnet else "I. Ordnung",
                         str(i.iterationen) if i.gerechnet else "-",
                         f"{i.u_max_I * 1e3:.2f}",
                         f"{i.u_max_II * 1e3:.2f}" if i.gerechnet else "-",
                         f"{i.zuwachs * 100:+.1f} %" if i.gerechnet else "-"])
        return rows


def check_theorie2(model: Model, analysis, combos: list = None, system=None,
                   progress=None) -> Th2Results:
    """
    Alle GZT-Kombinationen nach Theorie II. Ordnung rechnen und die
    Ergebnisse der Berechnung **ersetzen**.

    ``model.design.theorie2``:
        "aus"   nichts tun
        "auto"  je Kombination alpha_cr bestimmen und nur rechnen, wenn
                alpha_cr unter der Grenze nach 5.2.1(3) liegt
        "ein"   immer am verformten System rechnen
    """
    from .solver import StaticSystem
    ds = model.design
    modus = getattr(ds, "theorie2", "aus")
    out = Th2Results(settings={
        "modus": modus,
        "imperfektionen": bool(getattr(ds, "imperfektionen", True)),
        "plastisch": bool(getattr(ds, "th2_plastisch", False)),
        "grenze": 15.0 if getattr(ds, "th2_plastisch", False) else 10.0,
        "richtung": getattr(ds, "th2_richtung", None),
        "alle_vorkruemmungen": bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
        "Norm": "DIN EN 1993-1-1, 5.2 und 5.3"})
    if modus == "aus":
        return out
    names = combos if combos is not None else [
        n for n, c in model.combinations.items() if c.is_uls]
    if not names:
        return out
    system = system or StaticSystem(model, progress=progress)
    grenze = out.settings["grenze"]
    for k, n in enumerate(names):
        combo = model.combinations[n]
        if modus == "auto":
            # Grundzustand und alpha_cr zuerst
            from .solver import case_loads
            F, _feq, _q, _temp = case_loads(model, combo.factors)
            u1 = system.solve(F)
            ac = alpha_cr(model, system, u1)
            info = Th2Info(kombination=n, alpha_cr=ac["alpha_cr"], grenze=grenze,
                           u_max_I=float(np.abs(u1).max()))
            if ac.get("fehler"):
                info.hinweise.append(ac["fehler"])
            if ac["alpha_cr"] >= grenze:
                out.kombinationen[n] = info
                if progress:
                    progress(f"{n}: α_cr = {ac['alpha_cr']:.1f} ≥ {grenze:.0f} "
                             f"({k + 1}/{len(names)})")
                continue
        res, info = solve_theorie2(
            model, combo.factors, n, system,
            imperfektionen=out.settings["imperfektionen"],
            elastisch=not out.settings["plastisch"],
            richtung=out.settings["richtung"],
            alle_vorkruemmungen=out.settings["alle_vorkruemmungen"])
        info.grenze = grenze
        out.kombinationen[n] = info
        if not info.fehler and analysis is not None:
            analysis.combinations[n] = res
        if progress:
            progress(f"{n}: Theorie II. Ordnung ({k + 1}/{len(names)})")
    return out
