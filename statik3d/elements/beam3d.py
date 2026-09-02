"""
Raeumliches Balkenelement (12 FHG) und Fachwerkstab.

Lokales System:   x = Stabachse (Knoten 1 -> Knoten 2)
                  y, z = Querschnittshauptachsen
FHG-Reihenfolge:  [u1x u1y u1z r1x r1y r1z  u2x u2y u2z r2x r2y r2z]

Schubverformung nach Timoshenko wird beruecksichtigt, wenn Asy/Asz > 0.
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------
def local_axes(p1, p2, roll: float = 0.0):
    """Richtungskosinusmatrix T3 (3x3): Zeilen = lokale x,y,z in globalen Koord."""
    dx = np.asarray(p2, float) - np.asarray(p1, float)
    L = np.linalg.norm(dx)
    if L <= 0:
        raise ValueError("Stab mit Laenge 0")
    ex = dx / L
    # Referenzrichtung: global z, ausser der Stab ist (fast) vertikal
    if abs(ex[2]) > 0.9999:
        ref = np.array([1.0, 0.0, 0.0])
    else:
        ref = np.array([0.0, 0.0, 1.0])
    ey = np.cross(ref, ex)
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    if roll:
        c, s = np.cos(roll), np.sin(roll)
        ey2 = c * ey + s * ez
        ez2 = -s * ey + c * ez
        ey, ez = ey2, ez2
    return np.vstack([ex, ey, ez]), L


def transform_matrix(T3: np.ndarray) -> np.ndarray:
    """12x12 Blockdiagonale aus 3x3 Richtungskosinus."""
    T = np.zeros((12, 12))
    for i in range(4):
        T[3 * i:3 * i + 3, 3 * i:3 * i + 3] = T3
    return T


# --------------------------------------------------------------------------
def k_local_beam(E, G, A, Iy, Iz, It, L, Asy=0.0, Asz=0.0) -> np.ndarray:
    """Lokale Steifigkeitsmatrix 12x12."""
    k = np.zeros((12, 12))

    # Schubparameter
    phy = 12.0 * E * Iy / (G * Asz * L ** 2) if Asz > 0 else 0.0   # Biegung x-z
    phz = 12.0 * E * Iz / (G * Asy * L ** 2) if Asy > 0 else 0.0   # Biegung x-y

    # Normalkraft
    ea = E * A / L
    k[0, 0] = k[6, 6] = ea
    k[0, 6] = k[6, 0] = -ea

    # Torsion
    gj = G * It / L
    k[3, 3] = k[9, 9] = gj
    k[3, 9] = k[9, 3] = -gj

    # Biegung in x-y-Ebene (uy, rz) -> Iz
    f = E * Iz / (L ** 3 * (1.0 + phz))
    a = 12.0 * f
    b = 6.0 * f * L
    c = (4.0 + phz) * f * L ** 2
    d = (2.0 - phz) * f * L ** 2
    k[1, 1] = k[7, 7] = a
    k[1, 7] = k[7, 1] = -a
    k[1, 5] = k[5, 1] = b
    k[1, 11] = k[11, 1] = b
    k[5, 7] = k[7, 5] = -b
    k[7, 11] = k[11, 7] = -b
    k[5, 5] = k[11, 11] = c
    k[5, 11] = k[11, 5] = d

    # Biegung in x-z-Ebene (uz, ry) -> Iy
    f = E * Iy / (L ** 3 * (1.0 + phy))
    a = 12.0 * f
    b = 6.0 * f * L
    c = (4.0 + phy) * f * L ** 2
    d = (2.0 - phy) * f * L ** 2
    k[2, 2] = k[8, 8] = a
    k[2, 8] = k[8, 2] = -a
    k[2, 4] = k[4, 2] = -b
    k[2, 10] = k[10, 2] = -b
    k[4, 8] = k[8, 4] = b
    k[8, 10] = k[10, 8] = b
    k[4, 4] = k[10, 10] = c
    k[4, 10] = k[10, 4] = d

    return k


def kg_local_beam(N: float, L: float, A: float = 0.0, Ip: float = 0.0) -> np.ndarray:
    """Geometrische Steifigkeitsmatrix (Theorie II. Ordnung / Knicken).
    N > 0 = Zug. Konsistente Formulierung nach Przemieniecki."""
    kg = np.zeros((12, 12))
    if L <= 0:
        return kg
    f = N / L
    # Biegung x-y (uy, rz)
    for (i, j, v) in [(1, 1, 6 / 5), (1, 7, -6 / 5), (7, 7, 6 / 5),
                      (1, 5, L / 10), (1, 11, L / 10),
                      (5, 7, -L / 10), (7, 11, -L / 10),
                      (5, 5, 2 * L ** 2 / 15), (11, 11, 2 * L ** 2 / 15),
                      (5, 11, -L ** 2 / 30)]:
        kg[i, j] += f * v
        if i != j:
            kg[j, i] += f * v
    # Biegung x-z (uz, ry)
    for (i, j, v) in [(2, 2, 6 / 5), (2, 8, -6 / 5), (8, 8, 6 / 5),
                      (2, 4, -L / 10), (2, 10, -L / 10),
                      (4, 8, L / 10), (8, 10, L / 10),
                      (4, 4, 2 * L ** 2 / 15), (10, 10, 2 * L ** 2 / 15),
                      (4, 10, -L ** 2 / 30)]:
        kg[i, j] += f * v
        if i != j:
            kg[j, i] += f * v
    # Torsionsanteil (polares Traegheitsmoment)
    if A > 0 and Ip > 0:
        t = N * Ip / (A * L)
        kg[3, 3] += t
        kg[9, 9] += t
        kg[3, 9] -= t
        kg[9, 3] -= t
    return kg


def m_local_beam(rho, A, L, Ix_polar=0.0) -> np.ndarray:
    """Konsistente Massenmatrix 12x12 (ohne Schubeinfluss)."""
    m = np.zeros((12, 12))
    c = rho * A * L
    # axial
    m[0, 0] = m[6, 6] = c / 3.0
    m[0, 6] = m[6, 0] = c / 6.0
    # torsion
    if Ix_polar > 0:
        j = rho * Ix_polar * L
        m[3, 3] = m[9, 9] = j / 3.0
        m[3, 9] = m[9, 3] = j / 6.0
    # Biegung x-y
    v = c / 420.0
    tab = [(1, 1, 156), (1, 5, 22 * L), (1, 7, 54), (1, 11, -13 * L),
           (5, 5, 4 * L ** 2), (5, 7, 13 * L), (5, 11, -3 * L ** 2),
           (7, 7, 156), (7, 11, -22 * L), (11, 11, 4 * L ** 2)]
    for i, j_, val in tab:
        m[i, j_] += v * val
        if i != j_:
            m[j_, i] += v * val
    # Biegung x-z (Vorzeichen der Rotationskopplung dreht sich)
    tab = [(2, 2, 156), (2, 4, -22 * L), (2, 8, 54), (2, 10, 13 * L),
           (4, 4, 4 * L ** 2), (4, 8, -13 * L), (4, 10, -3 * L ** 2),
           (8, 8, 156), (8, 10, 22 * L), (10, 10, 4 * L ** 2)]
    for i, j_, val in tab:
        m[i, j_] += v * val
        if i != j_:
            m[j_, i] += v * val
    return m


def k_local_truss(E, A, L) -> np.ndarray:
    """Fachwerkstab: nur Normalkraft, Rotations-FHG bleiben leer."""
    k = np.zeros((12, 12))
    ea = E * A / L
    k[0, 0] = k[6, 6] = ea
    k[0, 6] = k[6, 0] = -ea
    return k


def fixed_end_forces(q_local, L, Asy=0.0, Asz=0.0) -> np.ndarray:
    """Volleinspannschnittgroessen fuer Gleichstreckenlast im lokalen System.
    Rueckgabe: Vektor der aequivalenten Knotenlasten (= -Volleinspannkraefte)."""
    qx, qy, qz = q_local
    f = np.zeros(12)
    # axial
    f[0] += qx * L / 2.0
    f[6] += qx * L / 2.0
    # qy -> Biegung x-y
    f[1] += qy * L / 2.0
    f[7] += qy * L / 2.0
    f[5] += qy * L ** 2 / 12.0
    f[11] += -qy * L ** 2 / 12.0
    # qz -> Biegung x-z
    f[2] += qz * L / 2.0
    f[8] += qz * L / 2.0
    f[4] += -qz * L ** 2 / 12.0
    f[10] += qz * L ** 2 / 12.0
    return f
