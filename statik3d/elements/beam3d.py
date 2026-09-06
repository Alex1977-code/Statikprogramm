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


# ==========================================================================
# Stabexzentrizitaet (starre Versaetze der Stabenden)
# ==========================================================================
def _skew(r) -> np.ndarray:
    """Schiefsymmetrische Matrix [r]x mit [r]x v = r x v."""
    r = np.asarray(r, float)
    return np.array([[0.0, -r[2], r[1]],
                     [r[2], 0.0, -r[0]],
                     [-r[1], r[0], 0.0]])


def versatz_matrix(r1, r2) -> np.ndarray:
    """Starre Versaetze der Stabenden gegenueber den Knoten, Matrix A (12x12).

    r_i (3,) = Vektor vom Knoten i zum Stabende i in **lokalen** Koordinaten
    des Stabes. Das Stabende bewegt sich starr mit dem Knoten:

        u_ende  = u_knoten + theta_knoten x r_i,   theta_ende = theta_knoten

    also u_stab = A u_knoten. Damit K_knoten = A^T K_stab A, f_knoten = A^T f_stab
    (eine Stabendkraft F erzeugt am Knoten zusaetzlich das Moment r_i x F).
    A ist invertierbar; Starrkoerpermoden bleiben Starrkoerpermoden.
    """
    A = np.eye(12)
    for i, r in enumerate((r1, r2)):
        # theta x r = -[r]x theta
        A[6 * i:6 * i + 3, 6 * i + 3:6 * i + 6] = -_skew(r)
    return A


# ==========================================================================
# Woelbkrafttorsion (7. Freiheitsgrad: Verwoelbung omega = theta_x')
# ==========================================================================
# Lage der Torsions-FHG [theta_x1, omega1, theta_x2, omega2] im 14-FHG-Element
IDX_TORSION14 = (3, 12, 9, 13)


def _hermite_ableitungen(L: float, x):
    """Kubische Hermite-Ansaetze fuer [w1, w1', w2, w2'] und ihre Ableitungen
    nach x an der Stelle x (0..L). Rueckgabe (N, N', N'', N''') je (4,) bzw.
    (4, n) bei Vektor x."""
    xi = np.asarray(x, float) / L
    one = np.ones_like(xi)
    N = np.array([1 - 3 * xi ** 2 + 2 * xi ** 3,
                  L * (xi - 2 * xi ** 2 + xi ** 3),
                  3 * xi ** 2 - 2 * xi ** 3,
                  L * (-xi ** 2 + xi ** 3)])
    dN = np.array([(-6 * xi + 6 * xi ** 2) / L,
                   1 - 4 * xi + 3 * xi ** 2,
                   (6 * xi - 6 * xi ** 2) / L,
                   -2 * xi + 3 * xi ** 2])
    ddN = np.array([(-6 + 12 * xi) / L ** 2,
                    (-4 + 6 * xi) / L,
                    (6 - 12 * xi) / L ** 2,
                    (-2 + 6 * xi) / L])
    dddN = np.array([12 / L ** 3 * one, 6 / L ** 2 * one,
                     -12 / L ** 3 * one, 6 / L ** 2 * one])
    return N, dN, ddN, dddN


def _hermite_steifigkeit_1(L: float) -> np.ndarray:
    """int N'^T N' dx  (mal 30 L) fuer kubische Hermite-Ansaetze."""
    L2 = L * L
    return np.array([[36.0, 3 * L, -36.0, 3 * L],
                     [3 * L, 4 * L2, -3 * L, -L2],
                     [-36.0, -3 * L, 36.0, -3 * L],
                     [3 * L, -L2, -3 * L, 4 * L2]]) / (30.0 * L)


def _hermite_steifigkeit_2(L: float) -> np.ndarray:
    """int N''^T N'' dx  (mal L^3) fuer kubische Hermite-Ansaetze."""
    L2 = L * L
    return np.array([[12.0, 6 * L, -12.0, 6 * L],
                     [6 * L, 4 * L2, -6 * L, 2 * L2],
                     [-12.0, -6 * L, 12.0, -6 * L],
                     [6 * L, 2 * L2, -6 * L, 4 * L2]]) / L ** 3


def k_local_torsion_woelb(E, G, It, Iw, L) -> np.ndarray:
    """Steifigkeit der gemischten Torsion (4x4) fuer die FHG
    [theta_x1, omega1, theta_x2, omega2] mit omega = theta_x' (Verwoelbung).

    theta_x wird kubisch (Hermite) interpoliert; die Formaenderungsenergie ist
    1/2 int (G It theta'^2 + E Iw theta''^2) dx. Fuer Iw = 0 bleibt die
    St.-Venant-Torsion (mit kubischem Ansatz, die lineare Loesung ist exakt).
    """
    return G * It * _hermite_steifigkeit_1(L) + E * Iw * _hermite_steifigkeit_2(L)


def k_local_beam14(E, G, A, Iy, Iz, It, Iw, L, Asy=0.0, Asz=0.0) -> np.ndarray:
    """Lokale Steifigkeitsmatrix 14x14 mit Woelbfreiheitsgrad.

    FHG 0..11 wie ``k_local_beam`` [u1x u1y u1z r1x r1y r1z u2x ... r2z],
    FHG 12 = omega1, 13 = omega2 (Verwoelbung = theta_x'). Die reine
    St.-Venant-Torsion ([3,3], [3,9], [9,9]) ist durch die gemischte Torsion
    aus ``k_local_torsion_woelb`` ersetzt.
    """
    k = np.zeros((14, 14))
    k12 = k_local_beam(E, G, A, Iy, Iz, It, L, Asy, Asz)
    k12[3, 3] = k12[9, 9] = k12[3, 9] = k12[9, 3] = 0.0
    k[:12, :12] = k12
    ix = np.ix_(IDX_TORSION14, IDX_TORSION14)
    k[ix] += k_local_torsion_woelb(E, G, It, Iw, L)
    return k


def m_local_beam14(rho, A, L, Ip, Iw) -> np.ndarray:
    """Konsistente Massenmatrix 14x14: ``m_local_beam`` (mit polarer
    Drehtraegheit rho Ip) plus Woelbtraegheit rho Iw.

    Die Verwoelbung u_x = -omega(s) theta_x' liefert die kinetische Energie
    1/2 rho Iw int (d theta_x'/dt)^2 dx, also die Matrix rho Iw int N'^T N' dx
    der Hermite-Ansaetze auf den FHG [3, 12, 9, 13].
    """
    m = np.zeros((14, 14))
    m[:12, :12] = m_local_beam(rho, A, L, Ip)
    if Iw > 0:
        ix = np.ix_(IDX_TORSION14, IDX_TORSION14)
        m[ix] += rho * Iw * _hermite_steifigkeit_1(L)
    return m


def torsion_verlauf(E, G, It, Iw, L, ul14, x) -> dict:
    """Torsionsgroessen an der Stelle x (0..L, Skalar oder Vektor) aus den
    lokalen Elementverschiebungen ul14 (14,) mittels Hermite-Interpolation
    von theta_x:

        theta  = Verdrehung
        B      = -E Iw theta''   (Woelbbimoment)
        Mt_p   =  G It theta'    (primaeres, St.-Venant-Torsionsmoment)
        Mt_s   = -E Iw theta'''  (sekundaeres Torsionsmoment aus Woelbkrafttorsion)
        Mt     = Mt_p + Mt_s

    Innerhalb eines Elements ist theta' quadratisch, Mt also nur naeherungsweise
    konstant; die Elementendkraefte K u erfuellen das Gleichgewicht exakt.
    """
    ul14 = np.asarray(ul14, float)
    d = ul14[list(IDX_TORSION14)]
    N, dN, ddN, dddN = _hermite_ableitungen(L, x)
    th = d @ N
    th1 = d @ dN
    th2 = d @ ddN
    th3 = d @ dddN
    B = -E * Iw * th2
    Mt_p = G * It * th1
    Mt_s = -E * Iw * th3
    return {"theta": th, "B": B, "Mt_p": Mt_p, "Mt_s": Mt_s, "Mt": Mt_p + Mt_s}
