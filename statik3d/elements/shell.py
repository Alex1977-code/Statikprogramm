"""
Ebenes Schalenelement (3-Knoten) = CST-Scheibe + DKT-Plattenelement.

Pro Knoten 6 FHG: ux uy uz rx ry rz
Der Drill-FHG (Drehung um die Flaechennormale) wird mit einer kleinen
kuenstlichen Steifigkeit stabilisiert (Standardvorgehen bei flachen Schalen).

Literatur: Batoz/Bathe/Ho (1980), Discrete Kirchhoff Triangle (DKT).
"""
from __future__ import annotations

import numpy as np

DRILL_FACTOR = 1e-4      # kuenstliche Drillsteifigkeit, relativ zu E*t*A


# --------------------------------------------------------------------------
def shell_frame(p1, p2, p3):
    """Lokales Elementsystem. Rueckgabe: T3 (3x3), lokale xy-Koordinaten, Flaeche."""
    p1, p2, p3 = map(lambda p: np.asarray(p, float), (p1, p2, p3))
    v12 = p2 - p1
    v13 = p3 - p1
    n = np.cross(v12, v13)
    An2 = np.linalg.norm(n)
    if An2 <= 0:
        raise ValueError("entartetes Schalenelement (Flaeche 0)")
    ez = n / An2
    ex = v12 / np.linalg.norm(v12)
    ey = np.cross(ez, ex)
    T3 = np.vstack([ex, ey, ez])
    xy = np.array([
        [0.0, 0.0],
        [np.dot(v12, ex), np.dot(v12, ey)],
        [np.dot(v13, ex), np.dot(v13, ey)],
    ])
    A = 0.5 * An2
    return T3, xy, A


def _material_matrices(E, nu, t):
    f = E / (1.0 - nu ** 2)
    D0 = np.array([[1.0, nu, 0.0],
                   [nu, 1.0, 0.0],
                   [0.0, 0.0, 0.5 * (1.0 - nu)]])
    Dm = f * t * D0                       # Scheibe (Kraefte je Laenge)
    Db = f * t ** 3 / 12.0 * D0           # Platte (Momente je Laenge)
    return Dm, Db, D0 * f


# --------------------------------------------------------------------------
def cst_b(xy) -> tuple[np.ndarray, float]:
    """B-Matrix (3x6) der Konstant-Dehnungs-Scheibe."""
    (x1, y1), (x2, y2), (x3, y3) = xy
    A = 0.5 * ((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1))
    b1, b2, b3 = y2 - y3, y3 - y1, y1 - y2
    c1, c2, c3 = x3 - x2, x1 - x3, x2 - x1
    B = np.array([[b1, 0, b2, 0, b3, 0],
                  [0, c1, 0, c2, 0, c3],
                  [c1, b1, c2, b2, c3, b3]]) / (2.0 * A)
    return B, A


# --------------------------------------------------------------------------
def _dkt_constants(xy):
    (x1, y1), (x2, y2), (x3, y3) = xy
    x23, y23 = x2 - x3, y2 - y3
    x31, y31 = x3 - x1, y3 - y1
    x12, y12 = x1 - x2, y1 - y2
    l23 = x23 ** 2 + y23 ** 2
    l31 = x31 ** 2 + y31 ** 2
    l12 = x12 ** 2 + y12 ** 2
    P = {4: -6 * x23 / l23, 5: -6 * x31 / l31, 6: -6 * x12 / l12}
    t = {4: -6 * y23 / l23, 5: -6 * y31 / l31, 6: -6 * y12 / l12}
    q = {4: 3 * x23 * y23 / l23, 5: 3 * x31 * y31 / l31, 6: 3 * x12 * y12 / l12}
    r = {4: 3 * y23 ** 2 / l23, 5: 3 * y31 ** 2 / l31, 6: 3 * y12 ** 2 / l12}
    return P, t, q, r, (x23, y23, x31, y31, x12, y12)


def dkt_b(xy, xi, eta) -> np.ndarray:
    """Kruemmungs-B-Matrix (3x9) des DKT-Elements.
    FHG-Reihenfolge: [w1 tx1 ty1 w2 tx2 ty2 w3 tx3 ty3]."""
    P, t, q, r, (x23, y23, x31, y31, x12, y12) = _dkt_constants(xy)
    A = 0.5 * (x31 * y12 - x12 * y31)

    P4, P5, P6 = P[4], P[5], P[6]
    t4, t5, t6 = t[4], t[5], t[6]
    q4, q5, q6 = q[4], q[5], q[6]
    r4, r5, r6 = r[4], r[5], r[6]

    Hx_xi = np.array([
        P6 * (1 - 2 * xi) + (P5 - P6) * eta,
        q6 * (1 - 2 * xi) - (q5 + q6) * eta,
        -4 + 6 * (xi + eta) + r6 * (1 - 2 * xi) - eta * (r5 + r6),
        -P6 * (1 - 2 * xi) + eta * (P4 + P6),
        q6 * (1 - 2 * xi) - eta * (q6 - q4),
        -2 + 6 * xi + r6 * (1 - 2 * xi) + eta * (r4 - r6),
        -eta * (P5 + P4),
        eta * (q4 - q5),
        -eta * (r5 - r4),
    ])
    Hy_xi = np.array([
        t6 * (1 - 2 * xi) + (t5 - t6) * eta,
        1 + r6 * (1 - 2 * xi) - (r5 + r6) * eta,
        -q6 * (1 - 2 * xi) + eta * (q5 + q6),
        -t6 * (1 - 2 * xi) + eta * (t4 + t6),
        -1 + r6 * (1 - 2 * xi) + eta * (r4 - r6),
        -q6 * (1 - 2 * xi) - eta * (q4 - q6),
        -eta * (t5 + t4),
        eta * (r4 - r5),
        -eta * (q4 - q5),
    ])
    Hx_eta = np.array([
        -P5 * (1 - 2 * eta) - (P6 - P5) * xi,
        q5 * (1 - 2 * eta) - (q5 + q6) * xi,
        -4 + 6 * (xi + eta) + r5 * (1 - 2 * eta) - xi * (r5 + r6),
        xi * (P4 + P6),
        xi * (q4 - q6),
        -xi * (r6 - r4),
        P5 * (1 - 2 * eta) - xi * (P4 + P5),
        q5 * (1 - 2 * eta) + xi * (q4 - q5),
        -2 + 6 * eta + r5 * (1 - 2 * eta) + xi * (r4 - r5),
    ])
    Hy_eta = np.array([
        -t5 * (1 - 2 * eta) - (t6 - t5) * xi,
        1 + r5 * (1 - 2 * eta) - (r5 + r6) * xi,
        -q5 * (1 - 2 * eta) + xi * (q5 + q6),
        xi * (t4 + t6),
        xi * (r4 - r6),
        -xi * (q4 - q6),
        t5 * (1 - 2 * eta) - xi * (t4 + t5),
        -1 + r5 * (1 - 2 * eta) + xi * (r4 - r5),
        -q5 * (1 - 2 * eta) - xi * (q4 - q5),
    ])

    B = np.zeros((3, 9))
    B[0, :] = (y31 * Hx_xi + y12 * Hx_eta) / (2 * A)
    B[1, :] = (-x31 * Hy_xi - x12 * Hy_eta) / (2 * A)
    B[2, :] = (-x31 * Hx_xi - x12 * Hx_eta + y31 * Hy_xi + y12 * Hy_eta) / (2 * A)
    return B


_TRI_GP = [(1 / 6, 1 / 6), (2 / 3, 1 / 6), (1 / 6, 2 / 3)]
_TRI_W = [1 / 3, 1 / 3, 1 / 3]


# --------------------------------------------------------------------------
def k_shell3_local(xy, A, E, nu, t) -> np.ndarray:
    """Lokale 18x18 Steifigkeitsmatrix (FHG: je Knoten ux uy uz rx ry rz)."""
    Dm, Db, _ = _material_matrices(E, nu, t)

    # --- Scheibe -----------------------------------------------------------
    Bm, _A = cst_b(xy)
    Km = A * (Bm.T @ Dm @ Bm)      # 6x6, DOF [u1 v1 u2 v2 u3 v3]

    # --- Platte ------------------------------------------------------------
    Kb = np.zeros((9, 9))
    for (xi, eta), w in zip(_TRI_GP, _TRI_W):
        B = dkt_b(xy, xi, eta)
        Kb += w * A * (B.T @ Db @ B)   # 9x9, DOF [w1 tx1 ty1 ...]

    # --- Einbau in 18x18 ---------------------------------------------------
    K = np.zeros((18, 18))
    mem_map = [0, 1, 6, 7, 12, 13]           # ux, uy je Knoten
    bend_map = [2, 3, 4, 8, 9, 10, 14, 15, 16]  # uz, rx, ry je Knoten
    for i in range(6):
        for j in range(6):
            K[mem_map[i], mem_map[j]] += Km[i, j]
    for i in range(9):
        for j in range(9):
            K[bend_map[i], bend_map[j]] += Kb[i, j]

    # --- Drill-Stabilisierung ---------------------------------------------
    kd = DRILL_FACTOR * E * t * A
    drill = [5, 11, 17]
    pat = np.array([[1.0, -0.5, -0.5], [-0.5, 1.0, -0.5], [-0.5, -0.5, 1.0]])
    for i in range(3):
        for j in range(3):
            K[drill[i], drill[j]] += kd * pat[i, j]
    return K


def T_shell(T3: np.ndarray, nnod: int = 3) -> np.ndarray:
    T = np.zeros((6 * nnod, 6 * nnod))
    for i in range(2 * nnod):
        T[3 * i:3 * i + 3, 3 * i:3 * i + 3] = T3
    return T


def k_shell3(p1, p2, p3, E, nu, t):
    """Globale 18x18 Steifigkeitsmatrix + Hilfsdaten fuer Postprocessing."""
    T3, xy, A = shell_frame(p1, p2, p3)
    Kl = k_shell3_local(xy, A, E, nu, t)
    T = T_shell(T3, 3)
    return T.T @ Kl @ T, T3, xy, A


def k_shell4(p1, p2, p3, p4, E, nu, t):
    """Viereck: Mittelung ueber beide Diagonalen-Aufteilungen (24x24)."""
    K = np.zeros((24, 24))
    combos = [((0, 1, 2), (0, 2, 3)), ((0, 1, 3), (1, 2, 3))]
    pts = [np.asarray(p, float) for p in (p1, p2, p3, p4)]
    for combo in combos:
        for tri in combo:
            Ke, _, _, _ = k_shell3(pts[tri[0]], pts[tri[1]], pts[tri[2]], E, nu, t)
            idx = []
            for n in tri:
                idx.extend(range(6 * n, 6 * n + 6))
            idx = np.array(idx)
            K[np.ix_(idx, idx)] += 0.5 * Ke
    return K


# --------------------------------------------------------------------------
def shell3_pressure(p1, p2, p3, p) -> np.ndarray:
    """Aequivalente Knotenkraefte fuer Flaechenlast p in Normalenrichtung.
    Rueckgabe: 18er Vektor in globalen Koordinaten."""
    T3, xy, A = shell_frame(p1, p2, p3)
    n = T3[2]
    f = np.zeros(18)
    Fn = p * A / 3.0
    for i in range(3):
        f[6 * i:6 * i + 3] = Fn * n
    return f


def shell3_mass(p1, p2, p3, rho, t) -> np.ndarray:
    """Konzentrierte (lumped) Massenmatrix, 18x18 diagonal."""
    _, _, A = shell_frame(p1, p2, p3)
    m = rho * t * A / 3.0
    d = np.zeros(18)
    rot = m * (A / 3.0) * 1e-3   # kleine Rotationstraegheit zur Regularisierung
    for i in range(3):
        d[6 * i:6 * i + 3] = m
        d[6 * i + 3:6 * i + 6] = rot
    return np.diag(d)


# --------------------------------------------------------------------------
def shell3_stress(p1, p2, p3, E, nu, t, u_glob18):
    """Schnittgroessen und Spannungen.
    Rueckgabe dict mit n (Nx,Ny,Nxy [N/m]), m (Mx,My,Mxy [Nm/m]),
    sig_top/sig_bot (3 Komponenten [Pa]) und vM_top/vM_bot."""
    T3, xy, A = shell_frame(p1, p2, p3)
    T = T_shell(T3, 3)
    ul = T @ u_glob18

    mem_map = [0, 1, 6, 7, 12, 13]
    bend_map = [2, 3, 4, 8, 9, 10, 14, 15, 16]
    Dm, Db, _ = _material_matrices(E, nu, t)

    Bm, _ = cst_b(xy)
    eps = Bm @ ul[mem_map]
    n_forces = Dm @ eps

    # Kruemmung im Schwerpunkt
    B = dkt_b(xy, 1 / 3, 1 / 3)
    kappa = B @ ul[bend_map]
    m_forces = Db @ kappa

    sig_mem = n_forces / t
    sig_bend = 6.0 * m_forces / t ** 2
    sig_top = sig_mem + sig_bend
    sig_bot = sig_mem - sig_bend

    def vm(s):
        sx, sy, sxy = s
        return float(np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3 * sxy ** 2))

    return {
        "n": n_forces, "m": m_forces,
        "sig_top": sig_top, "sig_bot": sig_bot,
        "vM_top": vm(sig_top), "vM_bot": vm(sig_bot),
        "vM": max(vm(sig_top), vm(sig_bot)),
        "T3": T3,
    }
