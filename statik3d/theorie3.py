"""
Theorie III. Ordnung: Gleichgewicht am verformten System mit **grossen
Verformungen** (geometrisch nichtlinear) fuer Stabtragwerke.

Korotationale Formulierung (Crisfield): jedes Stabelement bekommt ein
mitgehendes Bezugssystem aus der aktuellen Sehne und der mittleren Drehung
seiner beiden Knoten. Was der Stab in diesem System an Verformung uebrig
behaelt - Laengenaenderung und die kleinen Knotendrehungen relativ zur
Sehne - ist die elastische Verformung; sie ist klein, auch wenn sich das
ganze Element weit bewegt und dreht. Darauf wird die lineare lokale
Steifigkeit (Timoshenko/Bernoulli, Gelenke kondensiert) angewandt:

    f_l = k_l · d_l,   d_l = (0, θ₁ˡ, ΔL, θ₂ˡ),   f_int = Tᵀ f_l.

Knotendrehungen sind endliche Drehungen: je Knoten eine Drehmatrix R, die
mit jedem Iterationsschritt multiplikativ fortgeschrieben wird
(R ← exp(Δθ)·R). Gleichgewicht: f_int(u, R) = λ·F + F_imp; geloest mit
Newton-Raphson in Laststufen λ = 1/n … 1, Tangente T ᵀ (k_l + k_g(N)) T
(korotational mit geometrischer Steifigkeit; der Rest der konsistenten
Tangente fehlt, dafuer ist das Residuum exakt - die Iteration konvergiert
gegen das richtige Gleichgewicht, nur nicht quadratisch).

Lasten sind richtungstreu (konservativ) und werden als Knotenlasten der
Ausgangslage angesetzt; Ersatzimperfektionen nach EC3 5.3.2 (Schiefstellung,
Vorkruemmung) kommen wie bei Theorie II. Ordnung als gleichwertige Lasten
dazu und werden je Laststufe aus den Normalkraeften neu gebildet.

Grenzen: nur Stab- und Fachwerkelemente (keine Schalen, Volumen), kein
Kontakt, keine Zwangsverformungen; kleine Dehnungen (linear-elastisch).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

from . import assemble as asm
from .elements import beam3d as bm
from .model import Model

NDOF = 6


# ==========================================================================
# Endliche Drehungen
# ==========================================================================
def rot_exp(theta) -> np.ndarray:
    """Drehmatrix zum Drehvektor (Rodrigues)."""
    t = np.asarray(theta, float)
    a = float(np.linalg.norm(t))
    K = np.array([[0.0, -t[2], t[1]], [t[2], 0.0, -t[0]], [-t[1], t[0], 0.0]])
    if a < 1e-12:
        return np.eye(3) + K + 0.5 * K @ K
    return np.eye(3) + math.sin(a) / a * K + (1.0 - math.cos(a)) / a ** 2 * K @ K


def rot_log(R) -> np.ndarray:
    """Drehvektor zur Drehmatrix (Umkehrung von rot_exp), auch nahe 0 und π."""
    R = np.asarray(R, float)
    c = (np.trace(R) - 1.0) / 2.0
    c = min(1.0, max(-1.0, c))
    a = math.acos(c)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    s = math.sin(a)
    if a < 1e-6:
        return 0.5 * w                       # kleine Drehung: Schiefsymmetrischer Teil
    if abs(s) > 1e-6 and a < math.pi - 1e-3:
        return a / (2.0 * s) * w
    # nahe π: Achse aus R + I
    M = R + np.eye(3)
    k = int(np.argmax(np.diag(M)))
    axis = M[:, k] / np.linalg.norm(M[:, k])
    if np.dot(axis, w) < 0:
        axis = -axis
    return a * axis


# ==========================================================================
# Ergebnisse
# ==========================================================================
@dataclass
class Th3Info:
    """Was bei einem Lastfall oder einer Kombination nach Theorie III. Ordnung passiert ist."""
    name: str = ""
    gerechnet: bool = False
    schritte: int = 0
    iterationen: int = 0
    konvergenz: float = 0.0
    u_max_I: float = 0.0
    u_max_III: float = 0.0
    zuwachs: float = 0.0
    drehung_max: float = 0.0           # groesste Knotendrehung [rad]
    schiefstellung: dict = field(default_factory=dict)
    vorkruemmung: dict = field(default_factory=dict)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def text(self) -> str:
        if self.fehler:
            return f"{self.name}: {self.fehler}"
        return (f"{self.name}: {self.schritte} Laststufen, {self.iterationen} Iterationen, "
                f"u_max {self.u_max_I * 1e3:.3f} → {self.u_max_III * 1e3:.3f} mm "
                f"({self.zuwachs * 100:+.1f} %), größte Drehung {math.degrees(self.drehung_max):.2f}°")


@dataclass
class Th3Results:
    kombinationen: dict = field(default_factory=dict)      # name -> Th3Info
    settings: dict = field(default_factory=dict)

    @property
    def zuwachs_max(self) -> float:
        return max((i.zuwachs for i in self.kombinationen.values()), default=0.0)

    def summary(self) -> str:
        if not self.kombinationen:
            return "Theorie III. Ordnung: nichts gerechnet"
        n = sum(1 for i in self.kombinationen.values() if i.gerechnet)
        return (f"Theorie III. Ordnung: {n} von {len(self.kombinationen)} gerechnet, "
                f"größter Zuwachs der Verformung {self.zuwachs_max * 100:+.1f} %")


# ==========================================================================
# Element
# ==========================================================================
class _Stab:
    """Ein Stabelement mit Ausgangslage, lokaler Steifigkeit und Lasten."""

    def __init__(self, model: Model, i: int, feq: dict):
        e = model.elements[i]
        self.i = i
        self.nodes = [int(n) for n in e.nodes]
        self.typ = e.typ
        sec = model.sections[e.sec]
        self.A, self.Ip = sec.A, sec.Iy + sec.Iz
        kl, T3, T, L = asm.beam_local(model, e)
        if getattr(e, "hinge_springs", None):
            kl, _f, _rec = asm.hinge_springs(kl, np.zeros(12), e.hinge_springs)
        if e.hinges:
            kl, _f, _c = asm.condense(kl, np.zeros(12), e.hinges)
        self.kl = kl
        self.E0T = T3.T                   # Spalten: Ausgangsachsen ex, ey, ez
        self.L0 = L
        self.f0 = np.asarray(feq.get(i, np.zeros(12)), float)
        self.dofs = asm.element_dofs(e)

    def zustand(self, X: np.ndarray, R: np.ndarray):
        """(f_l, T, k_g, N, L) im mitgehenden System der aktuellen Lage."""
        n1, n2 = self.nodes
        d = X[n2] - X[n1]
        L = float(np.linalg.norm(d))
        e1 = d / L
        Q1 = R[n1] @ self.E0T
        Q2 = R[n2] @ self.E0T
        phi = rot_log(R[n1].T @ R[n2])
        Qm = R[n1] @ rot_exp(0.5 * phi) @ self.E0T
        q2 = Qm[:, 1]
        e2 = q2 - float(q2 @ e1) * e1
        n = float(np.linalg.norm(e2))
        if n < 1e-9:
            q3 = Qm[:, 2]
            e2 = np.cross(q3, e1)
            n = float(np.linalg.norm(e2))
        e2 /= n
        e3 = np.cross(e1, e2)
        E = np.column_stack([e1, e2, e3])
        th1 = rot_log(E.T @ Q1)
        th2 = rot_log(E.T @ Q2)
        dl = np.concatenate([[0.0, 0.0, 0.0], th1, [L - self.L0, 0.0, 0.0], th2])
        fl = self.kl @ dl
        N = float(fl[6])
        if self.typ == "truss":
            kg = np.zeros((12, 12))
            for a, b in ((1, 7), (2, 8)):
                kg[a, a] = kg[b, b] = N / L
                kg[a, b] = kg[b, a] = -N / L
        else:
            kg = bm.kg_local_beam(N, L, self.A, self.Ip)
        T = bm.transform_matrix(E.T)
        return fl, T, kg, N, L


# ==========================================================================
# Loesung
# ==========================================================================
def solve_theorie3(model: Model, factors: dict, name: str, schritte: int = 10,
                   max_iter: int = 30, tol: float = 1e-6, imperfektionen: bool = None,
                   elastisch: bool = True, richtung=None, alle_vorkruemmungen: bool = False,
                   aktiv=None, progress=None):
    """Einen Lastfall oder eine Kombination (``factors``) nach Theorie III.
    Ordnung rechnen. Rueckgabe (Results, Th3Info)."""
    from .solver import case_loads, case_prescribed, Results
    from . import supports as sup
    t0 = time.time()
    info = Th3Info(name=name)
    ds = model.design
    if imperfektionen is None:
        imperfektionen = bool(getattr(ds, "imperfektionen", True))
    ne = len(model.elements)
    wirksam = [i for i in range(ne) if aktiv is None or aktiv[i]]
    fremd = [i for i in wirksam if model.elements[i].typ not in asm.LINE_TYPES]
    if fremd:
        raise ValueError("Theorie III. Ordnung gibt es nur für Stabtragwerke - "
                         f"{len(fremd)} Flächen-/Volumenelemente im Modell")
    if model.has_contact:
        raise ValueError("Theorie III. Ordnung nicht zusammen mit Kontakt")
    us = case_prescribed(model, factors)
    if us is not None and np.any(np.asarray(us) != 0):
        raise ValueError("Theorie III. Ordnung nicht mit Zwangsverformungen")
    F_ref, feq, q, temp = case_loads(model, factors, aktiv)
    nn, ndof = model.nn, model.ndof
    staebe = [_Stab(model, i, feq) for i in wirksam]

    # Lager: starr (u = 0) und Federn
    lin, _ = sup.split(sup.expand(model))
    fixed = np.zeros(ndof, dtype=bool)
    feder_idx, feder_k = [], []
    for e in lin:
        if e.typ == "rigid":
            if e.value:
                raise ValueError("Theorie III. Ordnung nicht mit vorgegebenen Lagerverschiebungen")
            fixed[e.index] = True
        elif e.typ == "spring" and e.stiffness:
            feder_idx.append(int(e.index))
            feder_k.append(float(e.stiffness))
    feder_idx = np.array(feder_idx, int)
    feder_k = np.array(feder_k, float)
    Kk = asm.kopplungen(model, sparse.csr_matrix((ndof, ndof)), aktiv=aktiv)
    Kk = Kk.tocsr() if Kk is not None else None

    X0 = np.asarray(model.nodes, float).copy()
    u = np.zeros((nn, 3))
    R = np.tile(np.eye(3), (nn, 1, 1))

    def gesamtvektor():
        d = np.zeros((nn, NDOF))
        d[:, :3] = u
        for n in range(nn):
            d[n, 3:] = rot_log(R[n])
        return d.ravel()

    def aufbau():
        """Innere Kraefte und Tangente in der aktuellen Lage."""
        X = X0 + u
        f_int = np.zeros(ndof)
        rows, cols, vals = [], [], []
        zust = {}
        for st in staebe:
            fl, T, kg, N, L = st.zustand(X, R)
            zust[st.i] = (fl, N)
            Ke = T.T @ (st.kl + kg) @ T
            d = st.dofs
            f_int[d] += T.T @ fl
            r, c = np.meshgrid(d, d, indexing="ij")
            rows.append(r.ravel())
            cols.append(c.ravel())
            vals.append(Ke.ravel())
        K = sparse.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                              shape=(ndof, ndof)).tocsr()
        dges = gesamtvektor()
        if len(feder_idx):
            f_int[feder_idx] += feder_k * dges[feder_idx]
            K = K + sparse.coo_matrix((feder_k, (feder_idx, feder_idx)), shape=(ndof, ndof)).tocsr()
        if Kk is not None:
            f_int += Kk @ dges
            K = K + Kk
        return f_int, K, zust

    # Freiheitsgrade ohne Steifigkeit (Fachwerkknoten, lose Knoten) festhalten
    _f0, K0, _z = aufbau()
    diag = np.abs(K0.diagonal())
    ref = diag.max() if diag.size and diag.max() > 0 else 1.0
    fixed |= diag < ref * 1e-12
    fi = np.where(~fixed)[0]
    if not len(fi):
        raise ValueError("Kein freier Freiheitsgrad")

    def ergebnis(zust, F_ges, f_int):
        res = Results(name=name, kind="combination", model=model)
        res.u = gesamtvektor().reshape(-1, NDOF).copy()
        Rk = f_int - F_ges
        Rk[fi] = 0.0
        res.reactions = Rk.reshape(-1, NDOF)
        for st in staebe:
            fl, _N = zust[st.i]
            res.beam_end[st.i] = fl - st.f0
            if st.i in q:
                res.beam_q[st.i] = np.asarray(q[st.i], float)
        if aktiv is not None:
            res.info["inaktiv"] = [i for i in range(ne) if not aktiv[i]]
            for i in res.info["inaktiv"]:
                res.beam_end[i] = np.zeros(12)
        return res

    # Theorie I. Ordnung als Bezug (u_max_I)
    try:
        lu0 = splu(K0[fi][:, fi].tocsc())
        u1 = np.zeros(ndof)
        u1[fi] = lu0.solve(F_ref[fi])
        info.u_max_I = float(np.abs(u1[:, ].reshape(-1, NDOF)[:, :3]).max())
    except Exception as ex:                    # noqa: BLE001
        raise ValueError(f"Gleichungssystem singulär: {ex}") from ex

    lastnorm = float(np.linalg.norm(F_ref[fi])) or 1.0
    F_imp = np.zeros(ndof)
    zust = _z
    f_int = _f0
    F_ges = np.zeros(ndof)
    gesamt_it = 0
    for schritt in range(1, schritte + 1):
        lam = schritt / schritte
        konv = math.inf
        for it in range(1, max_iter + 1):
            f_int, K, zust = aufbau()
            if imperfektionen:
                from .theorie2 import ersatzlasten_schiefstellung, ersatzlasten_vorkruemmung
                res_t = ergebnis(zust, np.zeros(ndof), f_int)
                Fs, s_info = ersatzlasten_schiefstellung(model, res_t, richtung)
                Fv, v_info = ersatzlasten_vorkruemmung(model, res_t, elastisch, alle=alle_vorkruemmungen)
                F_imp = Fs + Fv
                info.schiefstellung, info.vorkruemmung = s_info, v_info
            F_ges = lam * F_ref + F_imp
            r = F_ges - f_int
            konv = float(np.linalg.norm(r[fi])) / (lam * lastnorm)
            gesamt_it += 1
            if konv < tol:
                break
            try:
                dd = splu(K[fi][:, fi].tocsc()).solve(r[fi])
            except Exception as ex:            # noqa: BLE001
                info.fehler = f"Laststufe {schritt}: Gleichungssystem singulär ({ex})"
                break
            delta = np.zeros(ndof)
            delta[fi] = dd
            delta = delta.reshape(-1, NDOF)
            u += delta[:, :3]
            for n in range(nn):
                dth = delta[n, 3:]
                if np.any(dth):
                    R[n] = rot_exp(dth) @ R[n]
        else:
            info.hinweise.append(
                f"Laststufe {schritt}: nach {max_iter} Iterationen nicht konvergiert "
                f"(Residuum {konv * 100:.3g} % der Last) - mehr Laststufen wählen")
            info.fehler = info.fehler or "keine Konvergenz"
        info.konvergenz = konv
        if info.fehler:
            break
        if progress:
            progress(f"{name}: Laststufe {schritt}/{schritte} ({it} Iterationen)")
    info.schritte = schritte
    info.iterationen = gesamt_it
    info.gerechnet = not info.fehler
    f_int, K, zust = aufbau()
    res = ergebnis(zust, F_ges, f_int)
    info.u_max_III = float(np.abs(res.u[:, :3]).max())
    info.drehung_max = float(np.linalg.norm(res.u[:, 3:], axis=1).max())
    if info.u_max_I > 0:
        info.zuwachs = info.u_max_III / info.u_max_I - 1.0
    res.info.update({"theorie": "III. Ordnung", "schritte": schritte,
                     "iterationen": gesamt_it, "konvergenz": info.konvergenz,
                     "factors": dict(factors), "time": time.time() - t0,
                     "ndof": ndof, "nfree": len(fi), "solver": "SuperLU"})
    if info.fehler:
        res.info["fehler"] = info.fehler
    return res, info


def check_theorie3(model: Model, analysis, combos: list = None, progress=None,
                   systeme: dict = None, schritte: int = None) -> Th3Results:
    """Alle Kombinationen mit theorie = "III" rechnen und die Ergebnisse der
    Berechnung **ersetzen** (nach Theorie III. Ordnung gilt keine Superposition)."""
    from .model import GRUNDSTELLUNG
    ds = model.design
    out = Th3Results(settings={
        "imperfektionen": bool(getattr(ds, "imperfektionen", True)),
        "plastisch": bool(getattr(ds, "th2_plastisch", False)),
        "schritte": int(schritte or getattr(ds, "th3_schritte", 10) or 10),
        "Norm": "geometrisch nichtlinear, korotational; Imperfektionen DIN EN 1993-1-1, 5.3"})
    names = combos if combos is not None else [
        n for n, c in model.combinations.items() if (getattr(c, "theorie", "") or "").upper() == "III"]
    for k, n in enumerate(names):
        combo = model.combinations[n]
        sit = getattr(combo, "situation", "") or GRUNDSTELLUNG
        m_c, aktiv = model, None
        if systeme and sit in systeme:
            m_c, sys_c = systeme[sit]
            aktiv = getattr(sys_c, "aktiv", None)
        try:
            res, info = solve_theorie3(m_c, combo.factors, n, schritte=out.settings["schritte"],
                                       imperfektionen=out.settings["imperfektionen"],
                                       elastisch=not out.settings["plastisch"],
                                       richtung=getattr(ds, "th2_richtung", None),
                                       alle_vorkruemmungen=bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
                                       aktiv=aktiv, progress=progress)
        except ValueError as ex:
            info = Th3Info(name=n, fehler=str(ex))
            res = None
        out.kombinationen[n] = info
        if res is not None and not info.fehler and analysis is not None:
            res.info["typ"] = combo.typ
            if sit != GRUNDSTELLUNG:
                res.info["situation"] = sit
            analysis.combinations[n] = res
        if progress:
            progress(f"{n}: Theorie III. Ordnung ({k + 1}/{len(names)})")
    return out
