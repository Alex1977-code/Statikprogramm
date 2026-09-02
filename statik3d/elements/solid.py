"""
Volumenelemente: Tet4, Tet10, Hex8.

Nur Translations-FHG (3 pro Knoten). Die Rotations-FHG solcher Knoten
werden im Loeser automatisch gesperrt.

Dehnungsreihenfolge: [exx, eyy, ezz, gxy, gyz, gzx]
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------
def D_matrix(E: float, nu: float) -> np.ndarray:
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[0, 0] = D[1, 1] = D[2, 2] = lam + 2 * mu
    D[3, 3] = D[4, 4] = D[5, 5] = mu
    return D


def von_mises(s: np.ndarray) -> float:
    sx, sy, sz, txy, tyz, tzx = s
    return float(np.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                         + 3.0 * (txy ** 2 + tyz ** 2 + tzx ** 2)))


def principal(s: np.ndarray) -> np.ndarray:
    sx, sy, sz, txy, tyz, tzx = s
    T = np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])
    return np.sort(np.linalg.eigvalsh(T))[::-1]


def _B_from_grad(dN: np.ndarray) -> np.ndarray:
    """dN: (n,3) Ableitungen nach x,y,z -> B (6, 3n)."""
    n = dN.shape[0]
    B = np.zeros((6, 3 * n))
    B[0, 0::3] = dN[:, 0]
    B[1, 1::3] = dN[:, 1]
    B[2, 2::3] = dN[:, 2]
    B[3, 0::3] = dN[:, 1]
    B[3, 1::3] = dN[:, 0]
    B[4, 1::3] = dN[:, 2]
    B[4, 2::3] = dN[:, 1]
    B[5, 0::3] = dN[:, 2]
    B[5, 2::3] = dN[:, 0]
    return B


# --------------------------------------------------------------------------
# Tet4
# --------------------------------------------------------------------------
def tet4_shape_grad(X: np.ndarray):
    """X: (4,3). Rueckgabe dN (4,3) und Volumen."""
    M = np.ones((4, 4))
    M[:, 1:] = X
    detM = np.linalg.det(M)
    V = detM / 6.0
    if abs(V) < 1e-18:
        raise ValueError("entartetes Tet4")
    Minv = np.linalg.inv(M)
    dN = Minv[1:, :].T          # (4,3)
    return dN, abs(V)


def k_tet4(X, E, nu):
    dN, V = tet4_shape_grad(np.asarray(X, float))
    B = _B_from_grad(dN)
    D = D_matrix(E, nu)
    return V * (B.T @ D @ B), B, V


def stress_tet4(X, E, nu, ue):
    _, B, _ = k_tet4(X, E, nu)
    return D_matrix(E, nu) @ (B @ ue)


# --------------------------------------------------------------------------
# Tet10
# --------------------------------------------------------------------------
_TET_GP = np.array([
    [0.5854101966249685, 0.1381966011250105, 0.1381966011250105],
    [0.1381966011250105, 0.5854101966249685, 0.1381966011250105],
    [0.1381966011250105, 0.1381966011250105, 0.5854101966249685],
    [0.1381966011250105, 0.1381966011250105, 0.1381966011250105],
])
_TET_W = np.full(4, 1.0 / 24.0)


def tet10_N_dN(r, s, t):
    """Kanonische Knotenreihenfolge:
    0..3 Ecken, 4=M(0,1) 5=M(1,2) 6=M(0,2) 7=M(0,3) 8=M(1,3) 9=M(2,3)."""
    L1 = 1.0 - r - s - t
    L2, L3, L4 = r, s, t
    N = np.array([
        L1 * (2 * L1 - 1), L2 * (2 * L2 - 1), L3 * (2 * L3 - 1), L4 * (2 * L4 - 1),
        4 * L1 * L2, 4 * L2 * L3, 4 * L1 * L3, 4 * L1 * L4, 4 * L2 * L4, 4 * L3 * L4,
    ])
    dL = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0],
                   [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    L = [L1, L2, L3, L4]
    dN = np.zeros((10, 3))
    for i in range(4):
        dN[i] = (4 * L[i] - 1) * dL[i]
    pairs = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    for k, (a, b) in enumerate(pairs):
        dN[4 + k] = 4 * (L[a] * dL[b] + L[b] * dL[a])
    return N, dN


def k_tet10(X, E, nu):
    X = np.asarray(X, float)
    D = D_matrix(E, nu)
    K = np.zeros((30, 30))
    V = 0.0
    for (r, s, t), w in zip(_TET_GP, _TET_W):
        _, dNr = tet10_N_dN(r, s, t)
        J = dNr.T @ X                     # (3,3)
        detJ = np.linalg.det(J)
        if detJ <= 0:
            raise ValueError("Tet10 mit negativer Jacobi-Determinante")
        dN = np.linalg.solve(J, dNr.T).T
        B = _B_from_grad(dN)
        K += w * detJ * (B.T @ D @ B)
        V += w * detJ
    return K, V


def stress_tet10(X, E, nu, ue, r=0.25, s=0.25, t=0.25):
    X = np.asarray(X, float)
    _, dNr = tet10_N_dN(r, s, t)
    J = dNr.T @ X
    dN = np.linalg.solve(J, dNr.T).T
    B = _B_from_grad(dN)
    return D_matrix(E, nu) @ (B @ ue)


def normalize_tet10(node_ids, coords):
    """Bringt eine beliebige Tet10-Knotenreihenfolge (z.B. aus gmsh) in die
    kanonische Reihenfolge. Mittelknoten werden geometrisch zugeordnet."""
    node_ids = list(node_ids)
    coords = np.asarray(coords, float)
    corners = node_ids[:4]
    cc = coords[:4]
    mids = node_ids[4:]
    mc = coords[4:]
    pairs = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    out = list(corners)
    used = set()
    for a, b in pairs:
        target = 0.5 * (cc[a] + cc[b])
        d = np.linalg.norm(mc - target, axis=1)
        for idx in np.argsort(d):
            if idx not in used:
                used.add(int(idx))
                out.append(mids[int(idx)])
                break
    return out


# --------------------------------------------------------------------------
# Hex8
# --------------------------------------------------------------------------
_G = 1.0 / np.sqrt(3.0)
_HEX_GP = np.array([[a, b, c] for a in (-_G, _G) for b in (-_G, _G) for c in (-_G, _G)])
_HEX_W = np.ones(8)

_HEX_SIGNS = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
], dtype=float)


def hex8_N_dN(r, s, t):
    sg = _HEX_SIGNS
    N = 0.125 * (1 + sg[:, 0] * r) * (1 + sg[:, 1] * s) * (1 + sg[:, 2] * t)
    dN = np.zeros((8, 3))
    dN[:, 0] = 0.125 * sg[:, 0] * (1 + sg[:, 1] * s) * (1 + sg[:, 2] * t)
    dN[:, 1] = 0.125 * (1 + sg[:, 0] * r) * sg[:, 1] * (1 + sg[:, 2] * t)
    dN[:, 2] = 0.125 * (1 + sg[:, 0] * r) * (1 + sg[:, 1] * s) * sg[:, 2]
    return N, dN


def _hex8_incompatible_grad(r, s, t, J0, detJ0, J, detJ):
    """Gradienten der inkompatiblen Wilson-Moden (1-r^2, 1-s^2, 1-t^2),
    mit Taylor-Korrektur damit der Patch-Test erfuellt bleibt."""
    dM = np.array([[-2 * r, 0.0, 0.0],
                   [0.0, -2 * s, 0.0],
                   [0.0, 0.0, -2 * t]])           # (3 Moden, 3 nat. Richtungen)
    g = (detJ0 / detJ) * np.linalg.solve(J0, dM.T).T
    return g                                       # (3,3) nach x,y,z


def hex8_matrices(X, E, nu, incompatible=True):
    """Rueckgabe (Kuu, Kua, Kaa, V). Bei incompatible=False ist Kua/Kaa None."""
    X = np.asarray(X, float)
    D = D_matrix(E, nu)
    Kuu = np.zeros((24, 24))
    Kua = np.zeros((24, 9))
    Kaa = np.zeros((9, 9))
    V = 0.0
    _, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
    J0 = dN0.T @ X
    detJ0 = np.linalg.det(J0)
    for (r, s, t), w in zip(_HEX_GP, _HEX_W):
        _, dNr = hex8_N_dN(r, s, t)
        J = dNr.T @ X
        detJ = np.linalg.det(J)
        if detJ <= 0:
            raise ValueError("Hex8 mit negativer Jacobi-Determinante")
        dN = np.linalg.solve(J, dNr.T).T
        B = _B_from_grad(dN)
        Kuu += w * detJ * (B.T @ D @ B)
        V += w * detJ
        if incompatible:
            g = _hex8_incompatible_grad(r, s, t, J0, detJ0, J, detJ)
            Ba = _B_from_grad(g)
            Kua += w * detJ * (B.T @ D @ Ba)
            Kaa += w * detJ * (Ba.T @ D @ Ba)
    if not incompatible:
        return Kuu, None, None, V
    return Kuu, Kua, Kaa, V


def k_hex8(X, E, nu, incompatible=True):
    Kuu, Kua, Kaa, V = hex8_matrices(X, E, nu, incompatible)
    if Kua is None:
        return Kuu, V
    K = Kuu - Kua @ np.linalg.solve(Kaa, Kua.T)
    return K, V


def stress_hex8(X, E, nu, ue, r=0.0, s=0.0, t=0.0, incompatible=True):
    X = np.asarray(X, float)
    _, dNr = hex8_N_dN(r, s, t)
    J = dNr.T @ X
    detJ = np.linalg.det(J)
    dN = np.linalg.solve(J, dNr.T).T
    B = _B_from_grad(dN)
    eps = B @ ue
    if incompatible:
        _, Kua, Kaa, _ = hex8_matrices(X, E, nu, True)
        alpha = -np.linalg.solve(Kaa, Kua.T @ ue)
        _, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
        J0 = dN0.T @ X
        g = _hex8_incompatible_grad(r, s, t, J0, np.linalg.det(J0), J, detJ)
        eps = eps + _B_from_grad(g) @ alpha
    return D_matrix(E, nu) @ eps


# --------------------------------------------------------------------------
def solid_volume(typ, X) -> float:
    X = np.asarray(X, float)
    if typ == "tet4":
        return tet4_shape_grad(X)[1]
    if typ == "tet10":
        V = 0.0
        for (r, s, t), w in zip(_TET_GP, _TET_W):
            _, dNr = tet10_N_dN(r, s, t)
            V += w * abs(np.linalg.det(dNr.T @ X))
        return V
    if typ == "hex8":
        V = 0.0
        for (r, s, t), w in zip(_HEX_GP, _HEX_W):
            _, dNr = hex8_N_dN(r, s, t)
            V += w * abs(np.linalg.det(dNr.T @ X))
        return V
    raise ValueError(typ)


def lumped_mass(typ, X, rho) -> np.ndarray:
    """Diagonale Massenmatrix (nur Translation)."""
    n = {"tet4": 4, "tet10": 10, "hex8": 8}[typ]
    V = solid_volume(typ, X)
    if typ == "tet10":
        # Ecken leicht, Mittelknoten schwerer (klassische HRZ-naehe Verteilung)
        w = np.array([1 / 32] * 4 + [7 / 48] * 6)
        w = w / w.sum()
    else:
        w = np.full(n, 1.0 / n)
    m = rho * V * w
    return np.repeat(m, 3)
