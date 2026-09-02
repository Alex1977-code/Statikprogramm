"""Loeser: lineare Statik, Eigenschwingungen, lineares Beulen/Knicken."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve, eigsh

from .model import Model, NDOF
from . import assemble as asm
from .elements import beam3d as bm
from .elements import shell as sh
from .elements import solid as sl


# --------------------------------------------------------------------------
@dataclass
class Results:
    u: np.ndarray = None                    # (nn, 6) Verschiebungen/Verdrehungen
    reactions: np.ndarray = None            # (nn, 6) Auflagerreaktionen
    beam_forces: dict = field(default_factory=dict)   # elem -> dict
    shell_stress: dict = field(default_factory=dict)
    solid_stress: dict = field(default_factory=dict)
    node_vm: np.ndarray = None              # gemittelte Vergleichsspannung je Knoten
    modes: np.ndarray = None                # (nmodes, nn, 6)
    freqs: np.ndarray = None                # [Hz]
    buckling_factors: np.ndarray = None
    buckling_modes: np.ndarray = None
    info: dict = field(default_factory=dict)

    @property
    def umag(self) -> np.ndarray:
        return np.linalg.norm(self.u[:, :3], axis=1)

    def summary(self) -> str:
        s = [f"Freiheitsgrade gesamt : {self.info.get('ndof', '?')}",
             f"davon aktiv           : {self.info.get('nfree', '?')}",
             f"Rechenzeit            : {self.info.get('time', 0):.3f} s"]
        if self.u is not None:
            i = int(np.argmax(self.umag))
            s.append(f"max. Verschiebung     : {self.umag[i]*1000:.4f} mm (Knoten {i})")
        if self.node_vm is not None and self.node_vm.size:
            s.append(f"max. Vergleichsspg.   : {np.nanmax(self.node_vm)/1e6:.2f} MPa")
        if self.reactions is not None:
            s.append("Summe Auflagerkraefte : "
                     f"[{self.reactions[:,0].sum():.1f}, "
                     f"{self.reactions[:,1].sum():.1f}, "
                     f"{self.reactions[:,2].sum():.1f}] N")
        if self.freqs is not None:
            s.append("Eigenfrequenzen [Hz]  : "
                     + ", ".join(f"{f:.3f}" for f in self.freqs[:10]))
        if self.buckling_factors is not None:
            s.append("Knicklastfaktoren     : "
                     + ", ".join(f"{f:.3f}" for f in self.buckling_factors[:10]))
        return "\n".join(s)


# --------------------------------------------------------------------------
def _partition(K, F, fixed, vals):
    free = ~fixed
    fi = np.where(free)[0]
    si = np.where(fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    rhs = F[fi]
    if np.any(vals[si]):
        Kfs = K[fi][:, si]
        rhs = rhs - Kfs @ vals[si]
    return fi, si, Kff, rhs


def solve_static(model: Model, progress=None) -> Results:
    t0 = time.time()
    K = asm.stiffness(model)
    F = asm.load_vector(model)
    fixed, vals = asm.constrained_dofs(model, K)
    if progress:
        progress("Gleichungssystem aufgestellt")

    fi, si, Kff, rhs = _partition(K, F, fixed, vals)

    u = vals.copy()
    if Kff.shape[0] > 0:
        try:
            u[fi] = spsolve(Kff, rhs)
        except Exception as ex:
            raise RuntimeError(f"Loesen fehlgeschlagen: {ex}")
    if not np.all(np.isfinite(u)):
        raise RuntimeError("Singulaeres System - Lagerung oder Vernetzung pruefen "
                           "(kinematische Kette / freie Knoten).")
    if progress:
        progress("System geloest")

    R = np.zeros(model.ndof)
    R[si] = (K @ u)[si] - F[si]

    res = Results()
    res.u = u.reshape(-1, NDOF)
    res.reactions = R.reshape(-1, NDOF)
    res.info = {"ndof": model.ndof, "nfree": len(fi), "time": time.time() - t0}
    postprocess(model, u, res)
    res.info["time"] = time.time() - t0
    return res


# --------------------------------------------------------------------------
def postprocess(model: Model, u: np.ndarray, res: Results):
    nn = model.nn
    acc = np.zeros(nn)
    cnt = np.zeros(nn)

    for i, e in enumerate(model.elements):
        mat = model.materials[e.mat]
        X = model.nodes[e.nodes]
        d = asm.element_dofs(e)
        ue = u[d]

        if e.typ in asm.LINE_TYPES:
            sec = model.sections[e.sec]
            T3, L = bm.local_axes(X[0], X[1], e.roll)
            T = bm.transform_matrix(T3)
            if e.typ == "truss":
                kl = bm.k_local_truss(mat.E, sec.A, L)
            else:
                kl = bm.k_local_beam(mat.E, mat.G, sec.A, sec.Iy, sec.Iz,
                                     sec.It, L, sec.Asy, sec.Asz)
            fl = kl @ (T @ ue)
            # Streckenlastanteil zuruecknehmen
            for bl in model.beam_loads:
                if bl.elem == i:
                    q = np.asarray(bl.q, float)
                    ql = T3 @ q if bl.system == "global" else q
                    fl -= bm.fixed_end_forces(ql, L)
            N1 = -fl[0]
            sig = abs(N1) / sec.A
            if sec.zmax > 0:
                sig += max(abs(fl[4]), abs(fl[10])) * sec.zmax / max(sec.Iy, 1e-20)
            if sec.ymax > 0:
                sig += max(abs(fl[5]), abs(fl[11])) * sec.ymax / max(sec.Iz, 1e-20)
            res.beam_forces[i] = {
                "L": L,
                "N": (-fl[0], fl[6]),
                "Vy": (fl[1], -fl[7]),
                "Vz": (fl[2], -fl[8]),
                "Mt": (-fl[3], fl[9]),
                "My": (-fl[4], fl[10]),
                "Mz": (-fl[5], fl[11]),
                "sig_max": sig,
                "util": sig / mat.fy if mat.fy else None,
            }
            for n in e.nodes:
                acc[n] += sig
                cnt[n] += 1

        elif e.typ in asm.SHELL_TYPES:
            t = model.shells[e.sec].t
            tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
            vms = []
            for tri in tris:
                idx = []
                for n in tri:
                    idx.extend(range(6 * n, 6 * n + 6))
                st = sh.shell3_stress(X[tri[0]], X[tri[1]], X[tri[2]],
                                      mat.E, mat.nu, t, ue[idx])
                vms.append(st)
            res.shell_stress[i] = vms[0] if len(vms) == 1 else {
                "n": np.mean([v["n"] for v in vms], axis=0),
                "m": np.mean([v["m"] for v in vms], axis=0),
                "sig_top": np.mean([v["sig_top"] for v in vms], axis=0),
                "sig_bot": np.mean([v["sig_bot"] for v in vms], axis=0),
                "vM": max(v["vM"] for v in vms),
                "vM_top": max(v["vM_top"] for v in vms),
                "vM_bot": max(v["vM_bot"] for v in vms),
                "T3": vms[0]["T3"],
            }
            v = res.shell_stress[i]["vM"]
            for n in e.nodes:
                acc[n] += v
                cnt[n] += 1

        elif e.typ in asm.SOLID_TYPES:
            if e.typ == "tet4":
                s = sl.stress_tet4(X, mat.E, mat.nu, ue)
            elif e.typ == "tet10":
                s = sl.stress_tet10(X, mat.E, mat.nu, ue)
            else:
                s = sl.stress_hex8(X, mat.E, mat.nu, ue)
            v = sl.von_mises(s)
            res.solid_stress[i] = {"s": s, "vM": v,
                                   "principal": sl.principal(s)}
            for n in e.nodes:
                acc[n] += v
                cnt[n] += 1

    with np.errstate(invalid="ignore", divide="ignore"):
        res.node_vm = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)


# --------------------------------------------------------------------------
def solve_modal(model: Model, nmodes: int = 8, progress=None) -> Results:
    t0 = time.time()
    K = asm.stiffness(model)
    M = asm.mass(model)
    fixed, vals = asm.constrained_dofs(model, K)
    # Knoten ohne Masse ebenfalls sperren
    md = np.asarray(M.diagonal()).ravel()
    fixed = fixed | (md <= 0)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Mff = M[fi][:, fi].tocsc()
    if progress:
        progress("Eigenwertproblem wird geloest")

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = eigsh(Kff, k=k, M=Mff, sigma=0.0, which="LM")
    order = np.argsort(vals_)
    vals_ = np.maximum(vals_[order], 0.0)
    vecs = vecs[:, order]

    freqs = np.sqrt(vals_) / (2 * np.pi)
    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = Results()
    res.u = np.zeros((model.nn, NDOF))
    res.freqs = freqs
    res.modes = modes.reshape(k, model.nn, NDOF)
    res.info = {"ndof": model.ndof, "nfree": len(fi), "time": time.time() - t0}
    return res


# --------------------------------------------------------------------------
def solve_buckling(model: Model, nmodes: int = 5, progress=None) -> Results:
    """Lineares Verzweigungsproblem: (K + lambda*Kg) v = 0 (Stabtragwerke)."""
    t0 = time.time()
    static = solve_static(model)
    u = static.u.ravel()
    K = asm.stiffness(model)
    Kg = asm.geometric_stiffness(model, u)
    fixed, _ = asm.constrained_dofs(model, K)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Kgff = Kg[fi][:, fi].tocsc()
    if abs(Kgff).max() == 0:
        raise RuntimeError("Keine Normalkraefte vorhanden - Knicknachweis nicht moeglich")
    if progress:
        progress("Verzweigungsproblem wird geloest")

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = eigsh(Kff, k=k, M=-Kgff, sigma=0.0, which="LM")
    order = np.argsort(np.abs(vals_))
    vals_ = vals_[order]
    vecs = vecs[:, order]

    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = static
    res.buckling_factors = vals_
    res.buckling_modes = modes.reshape(k, model.nn, NDOF)
    res.info["time"] = time.time() - t0
    return res
