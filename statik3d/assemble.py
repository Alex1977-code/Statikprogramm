"""Assemblierung von Steifigkeits-, Massen- und Lastvektoren."""
from __future__ import annotations

import numpy as np
from scipy import sparse

from .model import Model, NDOF
from .elements import beam3d as bm
from .elements import shell as sh
from .elements import solid as sl

SOLID_TYPES = ("tet4", "tet10", "hex8")
SHELL_TYPES = ("shell3", "shell4")
LINE_TYPES = ("beam", "truss")


# --------------------------------------------------------------------------
def element_dofs(e) -> np.ndarray:
    """Globale FHG-Nummern eines Elements."""
    if e.typ in SOLID_TYPES:
        d = []
        for n in e.nodes:
            d.extend([NDOF * n, NDOF * n + 1, NDOF * n + 2])
        return np.array(d, dtype=int)
    d = []
    for n in e.nodes:
        d.extend(range(NDOF * n, NDOF * n + NDOF))
    return np.array(d, dtype=int)


def element_matrix(model: Model, e):
    """Elementsteifigkeitsmatrix im globalen System."""
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]

    if e.typ in LINE_TYPES:
        sec = model.sections[e.sec]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        if e.typ == "truss":
            kl = bm.k_local_truss(mat.E, sec.A, L)
        else:
            kl = bm.k_local_beam(mat.E, mat.G, sec.A, sec.Iy, sec.Iz, sec.It,
                                 L, sec.Asy, sec.Asz)
        return T.T @ kl @ T

    if e.typ == "shell3":
        t = model.shells[e.sec].t
        K, _, _, _ = sh.k_shell3(X[0], X[1], X[2], mat.E, mat.nu, t)
        return K

    if e.typ == "shell4":
        t = model.shells[e.sec].t
        return sh.k_shell4(X[0], X[1], X[2], X[3], mat.E, mat.nu, t)

    if e.typ == "tet4":
        return sl.k_tet4(X, mat.E, mat.nu)[0]
    if e.typ == "tet10":
        return sl.k_tet10(X, mat.E, mat.nu)[0]
    if e.typ == "hex8":
        return sl.k_hex8(X, mat.E, mat.nu)[0]

    raise ValueError(f"unbekannter Elementtyp '{e.typ}'")


def element_mass(model: Model, e):
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]
    if e.typ in LINE_TYPES:
        sec = model.sections[e.sec]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        ml = bm.m_local_beam(mat.rho, sec.A, L, sec.Iy + sec.Iz)
        return T.T @ ml @ T
    if e.typ == "shell3":
        return sh.shell3_mass(X[0], X[1], X[2], mat.rho, model.shells[e.sec].t)
    if e.typ == "shell4":
        M = np.zeros((24, 24))
        for tri, f in [((0, 1, 2), 0.5), ((0, 2, 3), 0.5),
                       ((0, 1, 3), 0.5), ((1, 2, 3), 0.5)]:
            Me = sh.shell3_mass(X[tri[0]], X[tri[1]], X[tri[2]],
                                mat.rho, model.shells[e.sec].t)
            idx = []
            for n in tri:
                idx.extend(range(6 * n, 6 * n + 6))
            idx = np.array(idx)
            M[np.ix_(idx, idx)] += f * Me
        return M
    if e.typ in SOLID_TYPES:
        return np.diag(sl.lumped_mass(e.typ, X, mat.rho))
    raise ValueError(e.typ)


# --------------------------------------------------------------------------
def stiffness(model: Model) -> sparse.csr_matrix:
    n = model.ndof
    rows, cols, vals = [], [], []
    for e in model.elements:
        ke = element_matrix(model, e)
        d = element_dofs(e)
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(np.asarray(ke).ravel())
    if not rows:
        return sparse.csr_matrix((n, n))
    K = sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()
    # Federlager
    for s in model.supports:
        if s.stiffness:
            for k_, dof in zip(s.stiffness, s.dofs):
                if k_:
                    i = NDOF * s.node + dof
                    K[i, i] += k_
    return K


def mass(model: Model) -> sparse.csr_matrix:
    n = model.ndof
    rows, cols, vals = [], [], []
    for e in model.elements:
        me = element_mass(model, e)
        d = element_dofs(e)
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(np.asarray(me).ravel())
    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()


def geometric_stiffness(model: Model, u: np.ndarray) -> sparse.csr_matrix:
    """Geometrische Steifigkeit aus vorhandenem Verformungszustand (nur Staebe)."""
    n = model.ndof
    rows, cols, vals = [], [], []
    for e in model.elements:
        if e.typ not in LINE_TYPES:
            continue
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        d = element_dofs(e)
        ul = T @ u[d]
        N = mat.E * sec.A / L * (ul[6] - ul[0])      # Zug positiv
        kg = bm.kg_local_beam(N, L, sec.A, sec.Iy + sec.Iz)
        kg = T.T @ kg @ T
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(kg.ravel())
    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()


# --------------------------------------------------------------------------
def load_vector(model: Model) -> np.ndarray:
    F = np.zeros(model.ndof)

    for l in model.nodal_loads:
        F[NDOF * l.node: NDOF * l.node + 6] += np.asarray(l.F, float)

    for l in model.beam_loads:
        e = model.elements[l.elem]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        q = np.asarray(l.q, float)
        q_local = T3 @ q if l.system == "global" else q
        fl = bm.fixed_end_forces(q_local, L)
        T = bm.transform_matrix(T3)
        F[element_dofs(e)] += T.T @ fl

    for l in model.face_loads:
        e = model.elements[l.elem]
        X = model.nodes[e.nodes]
        if e.typ == "shell3":
            F[element_dofs(e)] += sh.shell3_pressure(X[0], X[1], X[2], l.p)
        elif e.typ == "shell4":
            f = np.zeros(24)
            for tri in [(0, 1, 2), (0, 2, 3)]:
                ft = sh.shell3_pressure(X[tri[0]], X[tri[1]], X[tri[2]], l.p)
                for k, n in enumerate(tri):
                    f[6 * n:6 * n + 6] += ft[6 * k:6 * k + 6]
            F[element_dofs(e)] += f

    # Eigengewicht
    g = np.asarray(model.gravity, float)
    if np.any(g):
        for e in model.elements:
            mat = model.materials[e.mat]
            X = model.nodes[e.nodes]
            if e.typ in LINE_TYPES:
                sec = model.sections[e.sec]
                T3, L = bm.local_axes(X[0], X[1], e.roll)
                q = mat.rho * sec.A * g
                fl = bm.fixed_end_forces(T3 @ q, L)
                F[element_dofs(e)] += bm.transform_matrix(T3).T @ fl
            elif e.typ in SHELL_TYPES:
                t = model.shells[e.sec].t
                tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
                for tri in tris:
                    _, _, A = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
                    fn = mat.rho * t * A / 3.0 * g
                    for n in tri:
                        F[NDOF * e.nodes[n]: NDOF * e.nodes[n] + 3] += fn
            elif e.typ in SOLID_TYPES:
                m = sl.lumped_mass(e.typ, X, mat.rho)[0::3]
                for k, n in enumerate(e.nodes):
                    F[NDOF * n: NDOF * n + 3] += m[k] * g
    return F


# --------------------------------------------------------------------------
def constrained_dofs(model: Model, K: sparse.csr_matrix):
    """Gesperrte FHG: Lager + FHG ohne Steifigkeit (z.B. Rotation an Volumenknoten).
    Rueckgabe (fixed_idx, prescribed_values)."""
    n = model.ndof
    fixed = np.zeros(n, dtype=bool)
    vals = np.zeros(n)

    diag = np.abs(K.diagonal())
    ref = diag.max() if diag.size and diag.max() > 0 else 1.0
    fixed |= diag < ref * 1e-12

    for s in model.supports:
        if s.stiffness:
            continue           # Federlager -> nicht sperren
        for k, dof in enumerate(s.dofs):
            i = NDOF * s.node + dof
            fixed[i] = True
            vals[i] = s.values[k] if s.values else 0.0
    return fixed, vals
