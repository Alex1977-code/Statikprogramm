"""
Volumenelemente: Tet4, Tet10, Hex8, Hex20, Pent6, Pent15, Pyr5.

Nur Translations-FHG (3 pro Knoten). Die Rotations-FHG solcher Knoten
werden im Loeser automatisch gesperrt.

Dehnungsreihenfolge: [exx, eyy, ezz, gxy, gyz, gzx]
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------
#: Werkstoffmatrizen, einmal je (E, nu) gebaut. Sie haengt an nichts
#: anderem, wurde aber je Element neu erzeugt: am Drehlager 1 940 118 Aufrufe
#: und 3,55 s je Plastizitaetsschritt (cProfile 19.09.2026). Die Matrizen
#: liegen schreibgeschuetzt, damit ein versehentliches D[i, j] = ... auffaellt
#: statt still alle Elemente desselben Werkstoffs zu verderben.
_D_CACHE: dict = {}


def D_matrix(E: float, nu: float) -> np.ndarray:
    schluessel = (float(E), float(nu))
    D = _D_CACHE.get(schluessel)
    if D is not None:
        return D
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[0, 0] = D[1, 1] = D[2, 2] = lam + 2 * mu
    D[3, 3] = D[4, 4] = D[5, 5] = mu
    D.flags.writeable = False
    if len(_D_CACHE) < 256:            # ein Modell hat eine Handvoll Werkstoffe
        _D_CACHE[schluessel] = D
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
        raise ValueError("Tetraeder ohne Volumen - die vier Knoten fallen "
                         "zusammen oder liegen in einer Ebene "
                         f"(V = {V:.3e} m^3). Das Netz an dieser Stelle neu "
                         "erzeugen (Netz -> Vernetzen)")
    Minv = np.linalg.inv(M)
    dN = Minv[1:, :].T          # (4,3)
    return dN, abs(V)


#: Voigt-Vektor der Einheitsdehnung: m^T eps = eps_xx + eps_yy + eps_zz
VOIGT_M = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])


def kompressionsmodul(E: float, nu: float) -> float:
    """K = E / (3 (1 - 2 nu)) - der volumetrische Anteil von D."""
    return float(E) / (3.0 * (1.0 - 2.0 * float(nu)))


def D_deviatorisch(E: float, nu: float) -> np.ndarray:
    """D ohne seinen volumetrischen Anteil: D - K m m^T.

    Zusammen mit K m m^T ergibt das wieder genau D - die Aufspaltung ist
    exakt und macht fuer sich genommen keinen Unterschied. Erst wenn der
    volumetrische Anteil ueber einen Elementverband gemittelt wird
    (assemble.knotendilatation), aendert sich etwas.
    """
    return D_matrix(E, nu) - kompressionsmodul(E, nu) * np.outer(VOIGT_M, VOIGT_M)


def tet4_grad_stapel(X):
    """Formfunktionsableitungen und Volumen eines **Stapels** Tetraeder.

    X: (n,4,3). Rueckgabe dN (n,4,3) und V (n,). Dieselbe Rechnung wie
    tet4_shape_grad, nur ueber alle Elemente auf einmal: eine Schleife mit
    35 bis 39 µs je Element kostete am Drehlager 25 s je Aufstellen der
    Steifigkeit (646.706 tet4, gemessen 20.09.2026) - und das in jeder
    Kontakt- und Plastizitaetsrunde.
    """
    X = np.asarray(X, float)
    M = np.ones((X.shape[0], 4, 4))
    M[:, :, 1:] = X
    V = np.linalg.det(M) / 6.0
    inv = np.linalg.inv(M)              # dN = letzte drei Spalten von M^-1
    return np.ascontiguousarray(inv[:, 1:, :].transpose(0, 2, 1)), V


def b_tet4(X):
    """Die Zeile m^T B des Tetraeders (12,) und sein Volumen.

    m^T B u = Spur der Dehnung = Volumendehnung. Beim linearen Tetraeder ist
    sie ueber das Element konstant, darum ist sie **eine** Zeile und nicht
    ein Feld ueber Gausspunkte - und darum bringt elementlokales B-bar hier
    auch nichts: es gibt nichts zu mitteln.
    """
    dN, V = tet4_shape_grad(np.asarray(X, float))
    return dN.ravel(), V


def k_tet4_deviatorisch(X, E, nu):
    """Der Tetraeder **ohne** seinen volumetrischen Anteil.

    Der volumetrische kommt in assemble.knotendilatation dazu, dort ueber den
    Elementverband jedes Knotens gemittelt. Der lineare Tetraeder versteift
    sonst (Theoriehandbuch 6a: Kragtraeger 69,5 % der Balkenloesung), und im
    Fliessbereich ist es am schlimmsten, weil von-Mises-Fliessen volumentreu
    ist - nu geht praktisch gegen 0,5.
    """
    dN, V = tet4_shape_grad(np.asarray(X, float))
    B = _B_from_grad(dN)
    return V * (B.T @ D_deviatorisch(E, nu) @ B), B, V


def k_tet4(X, E, nu):
    dN, V = tet4_shape_grad(np.asarray(X, float))
    B = _B_from_grad(dN)
    D = D_matrix(E, nu)
    return V * (B.T @ D @ B), B, V


def stress_tet4(X, E, nu, ue):
    """Spannung im Tetraeder: sigma = D B u_e.

    Dafuer braucht es **B**, nicht die Steifigkeitsmatrix. Bis zum 19.09.2026
    holte diese Funktion B aus k_tet4 und warf dessen 12x12-Produkt
    V*(B^T D B) weg - gemessen am Drehlager (646 706 Tetraeder) kostete das
    24,9 s von 39,4 s je Plastizitaetsschritt (cProfile, Uebergabe der
    Loeser-Sitzung).
    """
    dN, _V = tet4_shape_grad(np.asarray(X, float))
    return D_matrix(E, nu) @ (_B_from_grad(dN) @ ue)


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


def hex8_matrices(X, E, nu, incompatible=True, ohne_kuu=False):
    """Rueckgabe (Kuu, Kua, Kaa, V). Bei incompatible=False ist Kua/Kaa None.

    ``ohne_kuu=True`` laesst Kuu weg und gibt None zurueck. Wer nur die
    inneren Freiheitsgrade braucht - die Spannungsauswertung loest
    alpha = -Kaa^-1 Kua^T u -, zahlt sonst die 24x24-Summe ueber acht
    Gausspunkte umsonst: gemessen 21.09.2026 kostete stress_points am hex8
    1332 µs je Element gegen 18 µs beim tet4, und der groesste Posten darin
    war das Kuu, das niemand liest."""
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
        if not ohne_kuu:
            Kuu += w * detJ * (B.T @ D @ B)
        V += w * detJ
        if incompatible:
            g = _hex8_incompatible_grad(r, s, t, J0, detJ0, J, detJ)
            Ba = _B_from_grad(g)
            Kua += w * detJ * (B.T @ D @ Ba)
            Kaa += w * detJ * (Ba.T @ D @ Ba)
    if ohne_kuu:
        Kuu = None
    if not incompatible:
        return Kuu, None, None, V
    return Kuu, Kua, Kaa, V


def _b_stapel(g):
    """Verzerrungsmatrix B (n,6,3k) aus den Ableitungen g (n,k,3) - dieselbe
    Belegung wie :func:`_B_from_grad`, nur ueber einen Stapel."""
    n, k = g.shape[0], g.shape[1]
    B = np.zeros((n, 6, 3 * k))
    B[:, 0, 0::3] = g[:, :, 0]
    B[:, 1, 1::3] = g[:, :, 1]
    B[:, 2, 2::3] = g[:, :, 2]
    B[:, 3, 0::3] = g[:, :, 1]
    B[:, 3, 1::3] = g[:, :, 0]
    B[:, 4, 1::3] = g[:, :, 2]
    B[:, 4, 2::3] = g[:, :, 1]
    B[:, 5, 0::3] = g[:, :, 2]
    B[:, 5, 2::3] = g[:, :, 0]
    return B


def hex8_matrizen_stapel(X, E, nu, incompatible=True, ohne_kuu=False):
    """(Kuu, Kua, Kaa, V) eines **Stapels** Sechsflaechner gleichen Werkstoffs.

    X ist (n,8,3). Dieselbe Rechnung wie :func:`hex8_matrices`, nur ueber
    alle Elemente auf einmal: die Schleife je Element kostete gemessen
    720,5 µs (21.09.2026, verzerrter Wuerfel) - dreissigmal so viel wie ein
    ``tet4`` mit 24,2 µs. Am Drehlagernetz der Vernetzersitzung waren das
    23,5 s je Aufstellen fuer 31.108 Sechsflaechner gegen 9,5 s fuer 453.331
    Tetraeder: **sieben Prozent der Elemente trugen einundsiebzig Prozent der
    Zeit.** Die acht Gausspunkte bleiben eine Schleife - es sind acht; was
    kostete, war der Aufruf je Element.
    """
    X = np.asarray(X, float)
    n = X.shape[0]
    D = D_matrix(E, nu)
    Kuu = None if ohne_kuu else np.zeros((n, 24, 24))
    Kua = np.zeros((n, 24, 9)) if incompatible else None
    Kaa = np.zeros((n, 9, 9)) if incompatible else None
    V = np.zeros(n)
    _N0, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
    J0 = np.einsum("ki,nkj->nij", dN0, X)
    detJ0 = np.linalg.det(J0)
    for (r, s_, t), w in zip(_HEX_GP, _HEX_W):
        _N, dNr = hex8_N_dN(r, s_, t)
        J = np.einsum("ki,nkj->nij", dNr, X)
        detJ = np.linalg.det(J)
        if np.any(detJ <= 0):
            i = int(np.argmin(detJ))
            raise ValueError(f"Hex8 mit negativer Jacobi-Determinante "
                             f"(Element {i} im Stapel, det = {detJ[i]:.3e})")
        dN = np.linalg.solve(J, np.broadcast_to(dNr.T, (n, 3, 8))).transpose(0, 2, 1)
        B = _b_stapel(dN)
        wd = (float(w) * detJ)[:, None, None]
        # matmul statt einsum: die Stapel-Matrixmultiplikation von numpy geht
        # ueber BLAS, einsum rechnet sie bei diesen kleinen Matrizen selbst.
        # Gemessen 21.09.2026 an 2000 verzerrten Wuerfeln: 258,8 µs je Element
        # mit einsum, 85,4 µs mit matmul.
        Bt = B.transpose(0, 2, 1)
        if not ohne_kuu:
            Kuu += wd * (Bt @ (D @ B))
        V += float(w) * detJ
        if incompatible:
            dM = np.array([[-2.0 * r, 0.0, 0.0], [0.0, -2.0 * s_, 0.0], [0.0, 0.0, -2.0 * t]])
            g = (detJ0 / detJ)[:, None, None] * np.linalg.solve(
                J0, np.broadcast_to(dM.T, (n, 3, 3))).transpose(0, 2, 1)
            Ba = _b_stapel(g)
            DBa = D @ Ba
            Kua += wd * (Bt @ DBa)
            Kaa += wd * (Ba.transpose(0, 2, 1) @ DBa)
    return Kuu, Kua, Kaa, V


def hex8_alpha_stapel(X, E, nu, ue):
    """Die inneren Freiheitsgrade alpha (n,9) eines **Stapels** Sechsflaechner.

    alpha = -Kaa^-1 Kua^T u. Die Spannungsauswertung braucht sie je Element,
    und sie einzeln zu holen kostete 1040 µs - achtundfuenfzigmal so viel wie
    eine tet4-Spannung mit 18,2 µs (21.09.2026). Das Kuu wird dabei gar nicht
    erst gebaut (``ohne_kuu``); den Rest macht der Stapel.
    """
    _Kuu, Kua, Kaa, _V = hex8_matrizen_stapel(X, E, nu, True, ohne_kuu=True)
    ue = np.asarray(ue, float).reshape(len(Kaa), 24)
    rechts = -np.einsum("nji,nj->ni", Kua, ue)
    return np.linalg.solve(Kaa, rechts[..., None])[..., 0]


def spannungen_hex8_stapel(X, E, nu, U, punkte=None):
    """Spannungen (n, p, 6) an p Punkten fuer einen **Stapel** Sechsflaechner.

    X ist (n,8,3), U ist (n,24). Ohne ``punkte`` sind es die neun
    :data:`AUSWERTEPUNKTE` (Mitte und acht Ecken).

    Einzeln kostete ``stress_points`` am hex8 1120,6 µs je Element -
    einundsechzigmal so viel wie eine tet4-Spannung mit 18,2 µs
    (21.09.2026). Zwei Drittel davon waren die acht Gausspunkte fuer die
    inneren Freiheitsgrade, der Rest die neun Auswertepunkte; beides laeuft
    hier ueber den Stapel.
    """
    X = np.asarray(X, float)
    U = np.asarray(U, float).reshape(len(X), 24)
    pts = list(AUSWERTEPUNKTE["hex8"] if punkte is None else punkte)
    n = X.shape[0]
    D = D_matrix(E, nu)
    alpha = hex8_alpha_stapel(X, E, nu, U)
    _N0, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
    J0 = np.einsum("ki,nkj->nij", dN0, X)
    detJ0 = np.linalg.det(J0)
    aus = np.empty((n, len(pts), 6))
    for k, (r, s_, t) in enumerate(pts):
        _N, dNr = hex8_N_dN(r, s_, t)
        J = np.einsum("ki,nkj->nij", dNr, X)
        detJ = np.linalg.det(J)
        dN = np.linalg.solve(J, np.broadcast_to(dNr.T, (n, 3, 8))).transpose(0, 2, 1)
        eps = (_b_stapel(dN) @ U[:, :, None])[:, :, 0]
        dM = np.array([[-2.0 * r, 0.0, 0.0], [0.0, -2.0 * s_, 0.0], [0.0, 0.0, -2.0 * t]])
        g = (detJ0 / detJ)[:, None, None] * np.linalg.solve(
            J0, np.broadcast_to(dM.T, (n, 3, 3))).transpose(0, 2, 1)
        eps = eps + (_b_stapel(g) @ alpha[:, :, None])[:, :, 0]
        aus[:, k, :] = eps @ D.T
    return aus


def k_hex8_stapel(X, E, nu, incompatible=True):
    """Kondensierte Steifigkeiten (n,24,24) und Volumen (n) eines Stapels.

    Identisch zu :func:`k_hex8` je Element - die Pruefung
    ``tests/test_elemente_volumen.py`` haelt das auf 1e-12 fest.
    """
    Kuu, Kua, Kaa, V = hex8_matrizen_stapel(X, E, nu, incompatible)
    if Kua is None:
        return Kuu, V
    K = Kuu - Kua @ np.linalg.solve(Kaa, Kua.transpose(0, 2, 1))
    return K, V


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
        _, Kua, Kaa, _ = hex8_matrices(X, E, nu, True, ohne_kuu=True)
        alpha = -np.linalg.solve(Kaa, Kua.T @ ue)
        _, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
        J0 = dN0.T @ X
        g = _hex8_incompatible_grad(r, s, t, J0, np.linalg.det(J0), J, detJ)
        eps = eps + _B_from_grad(g) @ alpha
    return D_matrix(E, nu) @ eps


# --------------------------------------------------------------------------
# Hex20 (Serendipity-Hexaeder, 20 Knoten)
# --------------------------------------------------------------------------
_G3 = np.sqrt(0.6)
_GP3 = (-_G3, 0.0, _G3)
_GW3 = (5.0 / 9.0, 8.0 / 9.0, 5.0 / 9.0)
_HEX20_GP = np.array([[a, b, c] for a in _GP3 for b in _GP3 for c in _GP3])
_HEX20_W = np.array([wa * wb * wc for wa in _GW3 for wb in _GW3 for wc in _GW3])

#: natuerliche Koordinaten der 20 Knoten: 0..7 Ecken wie Hex8, dann Kantenmitten
_HEX20_XI = np.vstack([_HEX_SIGNS, np.array([
    [0, -1, -1], [1, 0, -1], [0, 1, -1], [-1, 0, -1],    # 8..11:  Kanten 0-1, 1-2, 2-3, 3-0
    [0, -1, 1], [1, 0, 1], [0, 1, 1], [-1, 0, 1],        # 12..15: Kanten 4-5, 5-6, 6-7, 7-4
    [-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0],      # 16..19: Kanten 0-4, 1-5, 2-6, 3-7
], dtype=float)])
_HEX20_MID = _HEX20_XI[8:] != 0      # (12,3): True = Richtung mit Vorzeichen, False = Nullrichtung


def hex20_N_dN(r, s, t):
    """Serendipity-Hexaeder, r, s, t in [-1, 1].  Knotenreihenfolge (VTK/Abaqus):
    0..7 Ecken wie Hex8, 8..11 Kantenmitten unten (Kanten 0-1, 1-2, 2-3, 3-0),
    12..15 oben (4-5, 5-6, 6-7, 7-4), 16..19 senkrecht (0-4, 1-5, 2-6, 3-7).
    Rueckgabe N (20,), dN (20,3) nach r, s, t."""
    xi = _HEX20_XI
    a, b, c = xi[:, 0], xi[:, 1], xi[:, 2]
    fa, fb, fc = 1.0 + a * r, 1.0 + b * s, 1.0 + c * t
    N = np.empty(20)
    dN = np.empty((20, 3))
    # Ecken: 1/8 (1+ar)(1+bs)(1+ct)(ar+bs+ct-2)
    e = slice(0, 8)
    g = a[e] * r + b[e] * s + c[e] * t
    N[e] = 0.125 * fa[e] * fb[e] * fc[e] * (g - 2.0)
    dN[e, 0] = 0.125 * a[e] * fb[e] * fc[e] * (g + a[e] * r - 1.0)
    dN[e, 1] = 0.125 * b[e] * fa[e] * fc[e] * (g + b[e] * s - 1.0)
    dN[e, 2] = 0.125 * c[e] * fa[e] * fb[e] * (g + c[e] * t - 1.0)
    # Kantenmitten: 1/4 (1-r^2)(1+bs)(1+ct) usw. - in der Nullrichtung steht (1-xi^2)
    m = slice(8, 20)
    ma, mb, mc = _HEX20_MID[:, 0], _HEX20_MID[:, 1], _HEX20_MID[:, 2]
    Fa = np.where(ma, fa[m], 1.0 - r * r)
    Fb = np.where(mb, fb[m], 1.0 - s * s)
    Fc = np.where(mc, fc[m], 1.0 - t * t)
    dFa = np.where(ma, a[m], -2.0 * r)
    dFb = np.where(mb, b[m], -2.0 * s)
    dFc = np.where(mc, c[m], -2.0 * t)
    N[m] = 0.25 * Fa * Fb * Fc
    dN[m, 0] = 0.25 * dFa * Fb * Fc
    dN[m, 1] = 0.25 * Fa * dFb * Fc
    dN[m, 2] = 0.25 * Fa * Fb * dFc
    return N, dN


def _k_iso(N_dN, GP, W, X, E, nu, name):
    """Steifigkeit (3n x 3n) und Volumen eines isoparametrischen Volumenelements
    mit voller Gauss-Integration; negative Jacobi-Determinante -> ValueError."""
    X = np.asarray(X, float)
    n = X.shape[0]
    D = D_matrix(E, nu)
    K = np.zeros((3 * n, 3 * n))
    V = 0.0
    for (r, s, t), w in zip(GP, W):
        _, dNr = N_dN(r, s, t)
        J = dNr.T @ X
        detJ = np.linalg.det(J)
        if detJ <= 0:
            raise ValueError(f"{name} mit negativer Jacobi-Determinante")
        dN = np.linalg.solve(J, dNr.T).T
        B = _B_from_grad(dN)
        K += w * detJ * (B.T @ D @ B)
        V += w * detJ
    return K, V


def _stress_iso(N_dN, X, E, nu, ue, r, s, t):
    """Spannung (6,) eines isoparametrischen Elements am Punkt (r, s, t)."""
    X = np.asarray(X, float)
    _, dNr = N_dN(r, s, t)
    J = dNr.T @ X
    dN = np.linalg.solve(J, dNr.T).T
    return D_matrix(E, nu) @ (_B_from_grad(dN) @ np.asarray(ue, float))


def k_hex20(X, E, nu):
    """Steifigkeit (60x60) und Volumen des Hex20 (3x3x3 Gauss-Punkte)."""
    return _k_iso(hex20_N_dN, _HEX20_GP, _HEX20_W, X, E, nu, "Hex20")


def stress_hex20(X, E, nu, ue, r=0.0, s=0.0, t=0.0):
    return _stress_iso(hex20_N_dN, X, E, nu, ue, r, s, t)


# --------------------------------------------------------------------------
# Pent6 / Pent15 (Keile: Dreieck x Strecke)
# --------------------------------------------------------------------------
# Dreiecksregeln in (r, s) mit L1 = 1-r-s, L2 = r, L3 = s (Gewichte auf Flaeche 1/2)
_TRI3_GP = np.array([[1.0 / 6.0, 1.0 / 6.0], [2.0 / 3.0, 1.0 / 6.0], [1.0 / 6.0, 2.0 / 3.0]])
_TRI3_W = np.full(3, 1.0 / 6.0)
_DA, _DB = 0.44594849091596489, 0.09157621350977073          # Dunavant, 6 Punkte, Grad 4
_TRI6_GP = np.array([[_DA, _DA], [1.0 - 2 * _DA, _DA], [_DA, 1.0 - 2 * _DA],
                     [_DB, _DB], [1.0 - 2 * _DB, _DB], [_DB, 1.0 - 2 * _DB]])
_TRI6_W = 0.5 * np.array([0.22338158967801147] * 3 + [0.10995174365532187] * 3)

_PENT6_GP = np.array([[a, b, c] for a, b in _TRI3_GP for c in (-_G, _G)])
_PENT6_W = np.array([w for w in _TRI3_W for _c in (-_G, _G)])
_PENT15_GP = np.array([[a, b, c] for a, b in _TRI6_GP for c in _GP3])
_PENT15_W = np.array([w * wc for w in _TRI6_W for wc in _GW3])

_DL = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]])     # dL_i / d(r, s)
_TRI_KANTEN = ((0, 1), (1, 2), (2, 0))


def pent6_N_dN(r, s, t):
    """Keil mit 6 Knoten: 0,1,2 unteres Dreieck (t = -1), 3,4,5 oberes (t = +1),
    gleicher Umlauf.  L1 = 1-r-s, L2 = r, L3 = s; t in [-1, 1]."""
    L = np.array([1.0 - r - s, r, s])
    tm, tp = 0.5 * (1.0 - t), 0.5 * (1.0 + t)
    N = np.concatenate([L * tm, L * tp])
    dN = np.zeros((6, 3))
    dN[:3, :2] = _DL * tm
    dN[:3, 2] = -0.5 * L
    dN[3:, :2] = _DL * tp
    dN[3:, 2] = 0.5 * L
    return N, dN


def pent15_N_dN(r, s, t):
    """Quadratischer Keil: 0..5 Ecken wie Pent6, 6..8 Kantenmitten unten
    (0-1, 1-2, 2-0), 9..11 oben (3-4, 4-5, 5-3), 12..14 senkrecht (0-3, 1-4, 2-5)."""
    L = np.array([1.0 - r - s, r, s])
    tm, tp, tq = 1.0 - t, 1.0 + t, 1.0 - t * t
    N = np.zeros(15)
    dN = np.zeros((15, 3))
    for i in range(3):
        Li, dLi = L[i], _DL[i]
        q = 0.5 * Li * (2.0 * Li - 1.0)
        dq = 0.5 * (4.0 * Li - 1.0)
        # Ecken unten / oben
        N[i] = q * tm - 0.5 * Li * tq
        dN[i, :2] = (dq * tm - 0.5 * tq) * dLi
        dN[i, 2] = -q + Li * t
        N[3 + i] = q * tp - 0.5 * Li * tq
        dN[3 + i, :2] = (dq * tp - 0.5 * tq) * dLi
        dN[3 + i, 2] = q + Li * t
        # senkrechte Kantenmitten
        N[12 + i] = Li * tq
        dN[12 + i, :2] = tq * dLi
        dN[12 + i, 2] = -2.0 * Li * t
    for k, (a, b) in enumerate(_TRI_KANTEN):
        La, Lb = L[a], L[b]
        dLL = La * _DL[b] + Lb * _DL[a]
        N[6 + k] = 2.0 * La * Lb * tm
        dN[6 + k, :2] = 2.0 * dLL * tm
        dN[6 + k, 2] = -2.0 * La * Lb
        N[9 + k] = 2.0 * La * Lb * tp
        dN[9 + k, :2] = 2.0 * dLL * tp
        dN[9 + k, 2] = 2.0 * La * Lb
    return N, dN


def k_pent6(X, E, nu):
    """Steifigkeit (18x18) und Volumen des Pent6 (3 Dreieckspunkte x 2 Gauss)."""
    return _k_iso(pent6_N_dN, _PENT6_GP, _PENT6_W, X, E, nu, "Pent6")


def k_pent15(X, E, nu):
    """Steifigkeit (45x45) und Volumen des Pent15 (6 Dreieckspunkte x 3 Gauss)."""
    return _k_iso(pent15_N_dN, _PENT15_GP, _PENT15_W, X, E, nu, "Pent15")


def stress_pent6(X, E, nu, ue, r=1.0 / 3.0, s=1.0 / 3.0, t=0.0):
    return _stress_iso(pent6_N_dN, X, E, nu, ue, r, s, t)


def stress_pent15(X, E, nu, ue, r=1.0 / 3.0, s=1.0 / 3.0, t=0.0):
    return _stress_iso(pent15_N_dN, X, E, nu, ue, r, s, t)


# --------------------------------------------------------------------------
# Pyr5 (Pyramide mit Viereckgrundflaeche)
# --------------------------------------------------------------------------
_PYR_SIGNS = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
# kollabierte 2x2x2-Hexaederregel: r = a (1-t)/2, s = b (1-t)/2, Gewicht ((1-t)/2)^2.
# In diesen Koordinaten sind die rationalen Formfunktionen Polynome, darum sind
# Volumen und Patch-Test exakt.
_PYR5_GP = np.array([[a * 0.5 * (1.0 - c), b * 0.5 * (1.0 - c), c]
                     for a in (-_G, _G) for b in (-_G, _G) for c in (-_G, _G)])
_PYR5_W = np.array([(0.5 * (1.0 - c)) ** 2
                    for _a in (-_G, _G) for _b in (-_G, _G) for c in (-_G, _G)])


def pyr5_N_dN(r, s, t):
    """Pyramide mit 5 Knoten (rationale Formfunktionen nach Bedrosian 1992):
    Grundflaeche 0..3 bei t = -1 mit (r, s) = (-1,-1), (1,-1), (1,1), (-1,1),
    Spitze 4 bei (0, 0, 1).  Das Element ist |r|, |s| <= (1-t)/2, t in [-1, 1].
    An der Spitze wird der Grenzwert laengs der Achse r = s = 0 verwendet."""
    a, b = _PYR_SIGNS[:, 0], _PYR_SIGNS[:, 1]
    h = 1.0 - t
    if h > 1e-12:
        qr, qs, qrs, qrs2 = r / h, s / h, r * s / h, r * s / (h * h)
    else:
        qr = qs = qrs = qrs2 = 0.0
    ab = a * b
    N = np.empty(5)
    dN = np.empty((5, 3))
    N[:4] = 0.25 * (0.5 * h + a * r + b * s + 2.0 * ab * qrs)
    N[4] = 0.5 * (1.0 + t)
    dN[:4, 0] = 0.25 * (a + 2.0 * ab * qs)
    dN[:4, 1] = 0.25 * (b + 2.0 * ab * qr)
    dN[:4, 2] = 0.25 * (-0.5 + 2.0 * ab * qrs2)
    dN[4] = (0.0, 0.0, 0.5)
    return N, dN


def k_pyr5(X, E, nu):
    """Steifigkeit (15x15) und Volumen des Pyr5 (kollabierte 2x2x2-Regel)."""
    return _k_iso(pyr5_N_dN, _PYR5_GP, _PYR5_W, X, E, nu, "Pyr5")


def stress_pyr5(X, E, nu, ue, r=0.0, s=0.0, t=-0.5):
    """Spannung der Pyramide; Vorgabe ist der Schwerpunkt (0, 0, -1/2)."""
    return _stress_iso(pyr5_N_dN, X, E, nu, ue, r, s, t)


# --------------------------------------------------------------------------
# Generische Hilfen fuer alle Volumentypen
# --------------------------------------------------------------------------
_TET4_GP = np.array([[0.25, 0.25, 0.25]])
_TET4_W = np.array([1.0 / 6.0])


def tet4_N_dN(r, s, t):
    """Lineares Tetraeder in Volumenkoordinaten L1 = 1-r-s-t, L2 = r, L3 = s, L4 = t."""
    N = np.array([1.0 - r - s - t, r, s, t])
    dN = np.array([[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    return N, dN


#: typ -> (Formfunktionen, Gauss-Punkte, Gauss-Gewichte)
_ISO = {
    "tet4": (tet4_N_dN, _TET4_GP, _TET4_W),
    "tet10": (tet10_N_dN, _TET_GP, _TET_W),
    "hex8": (hex8_N_dN, _HEX_GP, _HEX_W),
    "hex20": (hex20_N_dN, _HEX20_GP, _HEX20_W),
    "pent6": (pent6_N_dN, _PENT6_GP, _PENT6_W),
    "pent15": (pent15_N_dN, _PENT15_GP, _PENT15_W),
    "pyr5": (pyr5_N_dN, _PYR5_GP, _PYR5_W),
}
_KNOTENZAHL = {"tet4": 4, "tet10": 10, "hex8": 8, "hex20": 20,
               "pent6": 6, "pent15": 15, "pyr5": 5}


def knotenzahl(typ) -> int:
    """Zahl der Knoten eines Volumentyps."""
    try:
        return _KNOTENZAHL[typ]
    except KeyError:
        raise ValueError(typ) from None


def N_dN(typ, r, s, t):
    """Formfunktionen N (n,) und Ableitungen dN (n,3) nach r, s, t des Typs."""
    try:
        fn = _ISO[typ][0]
    except KeyError:
        raise ValueError(typ) from None
    return fn(r, s, t)


def gauss(typ):
    """Gauss-Punkte (m,3) und Gewichte (m,) des Typs in Elementkoordinaten."""
    try:
        _, GP, W = _ISO[typ]
    except KeyError:
        raise ValueError(typ) from None
    return GP.copy(), W.copy()


def anfangsspannungs_lasten(typ, X, s0) -> np.ndarray:
    """Aequivalente Knotenlasten f = ∫ Bᵀ s0 dV (3n,) einer Anfangsspannung s0
    (Voigt: xx, yy, zz, xy, yz, zx) - Temperatur, Vorspannung."""
    fn, GP, W = _ISO[typ]
    X = np.asarray(X, float)
    s0 = np.asarray(s0, float)
    f = np.zeros(3 * X.shape[0])
    for (r, s, t), w in zip(GP, W):
        _, dNr = fn(r, s, t)
        J = dNr.T @ X
        dN = np.linalg.solve(J, dNr.T).T
        f += w * abs(np.linalg.det(J)) * (_B_from_grad(dN).T @ s0)
    return f


# --------------------------------------------------------------------------
# Seiten der Volumenelemente
# --------------------------------------------------------------------------
#: Seiten je Typ: Ecken zuerst, dann die Kantenmitten in Kantenreihenfolge
#: (Kante k verbindet Ecke k mit Ecke k+1).  Bei hex20, pent6, pent15 und pyr5
#: laeuft der Umlauf so, dass die Rechtsschraube der Ecken nach aussen zeigt.
#: Bei tet4, tet10 und hex8 gelten die Tupel aus assemble.SOLID_FACES
#: unveraendert (dort zeigt die Rechtsschraube der Seiten 0 und 3 des Tetraeders
#: und der Seite 0 des Hex8 nach innen; die Assemblierung richtet die Normale
#: ueber den Elementschwerpunkt aus).
FLAECHEN = {
    "tet4": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
    "tet10": [(0, 1, 2, 4, 5, 6), (0, 1, 3, 4, 8, 7),
              (1, 2, 3, 5, 9, 8), (0, 2, 3, 6, 9, 7)],
    "hex8": [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    "hex20": [(0, 3, 2, 1, 11, 10, 9, 8), (4, 5, 6, 7, 12, 13, 14, 15),
              (0, 1, 5, 4, 8, 17, 12, 16), (1, 2, 6, 5, 9, 18, 13, 17),
              (2, 3, 7, 6, 10, 19, 14, 18), (3, 0, 4, 7, 11, 16, 15, 19)],
    "pent6": [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)],
    "pent15": [(0, 2, 1, 8, 7, 6), (3, 4, 5, 9, 10, 11), (0, 1, 4, 3, 6, 13, 9, 12),
               (1, 2, 5, 4, 7, 14, 10, 13), (2, 0, 3, 5, 8, 12, 11, 14)],
    "pyr5": [(0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)],
}
#: nur die Ecken der Seiten (bei quadratischen Typen die erste Haelfte der Tupel)
FLAECHEN_ECKEN = {
    typ: [f[:len(f) // 2] if typ in ("tet10", "hex20", "pent15") else f for f in faces]
    for typ, faces in FLAECHEN.items()
}

_QUAD_SIGNS = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
_QUAD8_XI = np.vstack([_QUAD_SIGNS, np.array([[0, -1], [1, 0], [0, 1], [-1, 0]], float)])
_QUAD8_MID = _QUAD8_XI[4:] != 0
_QUAD4_GP = np.array([[a, b] for a in (-_G, _G) for b in (-_G, _G)])
_QUAD4_W = np.ones(4)
_QUAD8_GP = np.array([[a, b] for a in _GP3 for b in _GP3])
_QUAD8_W = np.array([wa * wb for wa in _GW3 for wb in _GW3])
#: Knotenzahl der Seite -> Gauss-Regel (tri3, quad4, tri6, quad8)
_SEITEN_GAUSS = {3: (_TRI3_GP, _TRI3_W), 4: (_QUAD4_GP, _QUAD4_W),
                 6: (_TRI6_GP, _TRI6_W), 8: (_QUAD8_GP, _QUAD8_W)}


def seite_N_dN(k, a, b):
    """2D-Formfunktionen einer Seite mit k Knoten (3: tri3, 4: quad4, 6: tri6,
    8: quad8) an den Seitenkoordinaten (a, b): Ecken zuerst, dann Kantenmitten
    in Kantenreihenfolge.  Dreieck: L1 = 1-a-b, L2 = a, L3 = b; Viereck: a, b
    in [-1, 1].  Rueckgabe N (k,), dN (k,2)."""
    if k in (3, 6):
        L = np.array([1.0 - a - b, a, b])
        if k == 3:
            return L, _DL.copy()
        N = np.empty(6)
        dN = np.empty((6, 2))
        N[:3] = L * (2.0 * L - 1.0)
        dN[:3] = (4.0 * L - 1.0)[:, None] * _DL
        for m, (i, j) in enumerate(_TRI_KANTEN):
            N[3 + m] = 4.0 * L[i] * L[j]
            dN[3 + m] = 4.0 * (L[i] * _DL[j] + L[j] * _DL[i])
        return N, dN
    if k == 4:
        p, q = _QUAD_SIGNS[:, 0], _QUAD_SIGNS[:, 1]
        N = 0.25 * (1.0 + p * a) * (1.0 + q * b)
        dN = np.column_stack([0.25 * p * (1.0 + q * b), 0.25 * (1.0 + p * a) * q])
        return N, dN
    if k == 8:
        p, q = _QUAD8_XI[:, 0], _QUAD8_XI[:, 1]
        fa, fb = 1.0 + p * a, 1.0 + q * b
        N = np.empty(8)
        dN = np.empty((8, 2))
        e = slice(0, 4)
        g = p[e] * a + q[e] * b
        N[e] = 0.25 * fa[e] * fb[e] * (g - 1.0)
        dN[e, 0] = 0.25 * p[e] * fb[e] * (g + p[e] * a)
        dN[e, 1] = 0.25 * q[e] * fa[e] * (g + q[e] * b)
        m = slice(4, 8)
        mp, mq = _QUAD8_MID[:, 0], _QUAD8_MID[:, 1]
        Fa = np.where(mp, fa[m], 1.0 - a * a)
        Fb = np.where(mq, fb[m], 1.0 - b * b)
        dFa = np.where(mp, p[m], -2.0 * a)
        dFb = np.where(mq, q[m], -2.0 * b)
        N[m] = 0.5 * Fa * Fb
        dN[m, 0] = 0.5 * dFa * Fb
        dN[m, 1] = 0.5 * Fa * dFb
        return N, dN
    raise ValueError(f"Seite mit {k} Knoten")


def flaechenlast_knoten(P, p, richtung=None) -> np.ndarray:
    """Konsistente Knotenkraefte (k,3) einer gleichmaessigen Flaechenlast p [N/m²]
    auf einer Seite mit k = 3, 4, 6 oder 8 Punkten P (Ecken zuerst, dann die
    Kantenmitten).  Ohne 'richtung' wirkt p laengs der Seitennormale (Rechts-
    schraube der Ecken), sonst in Richtung des Einheitsvektors 'richtung'.
    Die Summe der Kraefte ist p·A·n bzw. p·A·richtung."""
    P = np.asarray(P, float)
    k = P.shape[0]
    GP, W = _SEITEN_GAUSS[k]
    d = None
    if richtung is not None:
        d = np.asarray(richtung, float)
        d = d / (np.linalg.norm(d) or 1.0)
    f = np.zeros((k, 3))
    for (a, b), w in zip(GP, W):
        N, dN = seite_N_dN(k, a, b)
        nA = np.cross(dN[:, 0] @ P, dN[:, 1] @ P)      # Normale mal dA/(da db)
        fvec = p * nA if d is None else p * np.linalg.norm(nA) * d
        f += w * np.outer(N, fvec)
    return f


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
    if typ in ("hex20", "pent6", "pent15", "pyr5"):
        fn, GP, W = _ISO[typ]
        V = 0.0
        for (r, s, t), w in zip(GP, W):
            _, dNr = fn(r, s, t)
            V += w * abs(np.linalg.det(dNr.T @ X))
        return V
    raise ValueError(typ)


def _hrz_gewichte(typ, X) -> np.ndarray:
    """Massenanteile je Knoten nach Hinton-Rock-Zienkiewicz: m_i ∝ ∫ N_i² dV,
    auf Summe 1 skaliert.  Reine Zeilensummen gaeben bei quadratischen
    Elementen negative Eckmassen."""
    fn, GP, W = _ISO[typ]
    X = np.asarray(X, float)
    w = np.zeros(X.shape[0])
    for (r, s, t), wg in zip(GP, W):
        N, dNr = fn(r, s, t)
        w += wg * abs(np.linalg.det(dNr.T @ X)) * N * N
    return w / w.sum()


def lumped_mass(typ, X, rho) -> np.ndarray:
    """Diagonale Massenmatrix (nur Translation)."""
    n = knotenzahl(typ)
    V = solid_volume(typ, X)
    if typ == "tet10":
        # Ecken leicht, Mittelknoten schwerer (klassische HRZ-naehe Verteilung)
        w = np.array([1 / 32] * 4 + [7 / 48] * 6)
        w = w / w.sum()
    elif typ in ("hex20", "pent6", "pent15", "pyr5"):
        w = _hrz_gewichte(typ, X)
    else:
        w = np.full(n, 1.0 / n)
    m = rho * V * w
    return np.repeat(m, 3)


# --------------------------------------------------------------------------
# Spannungen an mehreren Punkten eines Elements
# --------------------------------------------------------------------------
#: Auswertepunkte je Elementtyp: Mitte und Eckpunkte in Elementkoordinaten
AUSWERTEPUNKTE = {
    "tet4": [(0.25, 0.25, 0.25)],
    "tet10": [(0.25, 0.25, 0.25), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
              (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
    "hex8": [(0.0, 0.0, 0.0)] + [(r, s, t) for r in (-1.0, 1.0)
                                 for s in (-1.0, 1.0) for t in (-1.0, 1.0)],
    "hex20": [(0.0, 0.0, 0.0)] + [tuple(p) for p in _HEX_SIGNS],
    "pent6": [(1.0 / 3.0, 1.0 / 3.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, -1.0),
              (0.0, 1.0, -1.0), (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)],
    "pent15": [(1.0 / 3.0, 1.0 / 3.0, 0.0), (0.0, 0.0, -1.0), (1.0, 0.0, -1.0),
               (0.0, 1.0, -1.0), (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)],
    # Pyramide: Schwerpunkt (Viertel der Hoehe), Grundflaechenecken, Spitze
    "pyr5": [(0.0, 0.0, -0.5), (-1.0, -1.0, -1.0), (1.0, -1.0, -1.0),
             (1.0, 1.0, -1.0), (-1.0, 1.0, -1.0), (0.0, 0.0, 1.0)],
}


def stress_points(typ, X, E, nu, ue, punkte=None, alpha=None) -> list:
    """
    Spannungen an mehreren Punkten eines Volumenelements.

    Die Elementmitte allein reicht fuer einen Nachweis nicht: bei Biegung
    durch den Koerper liegt die Randspannung deutlich hoeher.  An einem
    Kragarm aus Hexaedern (4 Elemente ueber die Hoehe) gibt die Mitte
    43,3 N/mm^2, der Eckpunkt 60,3 N/mm^2 - die Balkenloesung M/W ist
    60,0 N/mm^2.  Darum wird hier ueber Mitte **und** Eckpunkte ausgewertet.

    Rueckgabe: Liste von Spannungsvektoren [sx, sy, sz, txy, tyz, tzx].
    """
    X = np.asarray(X, float)
    pts = punkte if punkte is not None else AUSWERTEPUNKTE.get(typ, [])
    if typ == "tet4":
        return [stress_tet4(X, E, nu, ue)]
    if typ == "tet10":
        return [stress_tet10(X, E, nu, ue, *p) for p in pts]
    if typ in ("hex20", "pent6", "pent15", "pyr5"):
        fn = _ISO[typ][0]
        return [_stress_iso(fn, X, E, nu, ue, *p) for p in pts]
    if typ != "hex8":
        return []
    # Hex8: die inkompatiblen Moden einmal loesen, dann alle Punkte auswerten.
    # ``alpha`` kann von aussen kommen (hex8_alpha_stapel) - dann faellt der
    # teuerste Teil weg, die acht Gausspunkte je Element.
    D = D_matrix(E, nu)
    if alpha is None:
        _K, Kua, Kaa, _ = hex8_matrices(X, E, nu, True, ohne_kuu=True)
        alpha = -np.linalg.solve(Kaa, Kua.T @ ue)
    _, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
    J0 = dN0.T @ X
    detJ0 = np.linalg.det(J0)
    out = []
    for r, s, t in pts:
        _, dNr = hex8_N_dN(r, s, t)
        J = dNr.T @ X
        detJ = np.linalg.det(J)
        dN = np.linalg.solve(J, dNr.T).T
        eps = _B_from_grad(dN) @ ue
        g = _hex8_incompatible_grad(r, s, t, J0, detJ0, J, detJ)
        eps = eps + _B_from_grad(g) @ alpha
        out.append(D @ eps)
    return out
