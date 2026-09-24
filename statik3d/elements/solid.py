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


#: Volumetrischer Anteil des hex8 (Auftrag A1 an die Element-Sitzung, 22.09.2026):
#: "p1" projiziert die Volumendehnung je Element auf {1, xi, eta, zeta} (B-bar
#: mit linearem Druckansatz, im Rahmen von Simo/Rifai 1990), "voll" ist der
#: Wilson-Taylor-hex8, wie er bis dahin rechnete (punktweise an 2x2x2).
#:
#: Warum nicht die **mittlere** Dilatation (ein Wert je Element): zusammen mit
#: den Wilson-Moden ist sie instabil. Das Feld u = k (xz, yz, (z^2-x^2-y^2)/2)
#: hat die Dehnung k z I - rein volumetrisch, Deviator null - und mit dem
#: Elementmittel null auch keine Volumenenergie; es ist darstellbar (die
#: Quadrate x^2, y^2, z^2 liefern die Moden) und setzt sich als Schachbrett
#: ueber das Netz fort. Gemessen 22.09.2026: 9 statt 6 Nullmoden am
#: regelmaessigen Element, der Kragarm 4x1x1 biegt sich 44-fach durch. Der
#: lineare Ansatz behaelt genau diesen linearen Anteil: 6 Nullmoden am
#: regelmaessigen und am verzerrten Element, Patch-Test auf 1e-15.
#:
#: Was er bringt (Kragarm 1,0 x 0,1 x 0,2 m, sigma_v an Oberkante x = L/2 auf
#: 355 N/mm2 skaliert, 22.09.2026, gemittelter Tensor der Elemente am Punkt):
#:
#:     Netz        nu = 0,3 voll / p1     nu = 0,499 voll / p1
#:     4x1x2        -7,7  /  -9,6          -51,1  / -25,7   N/mm2
#:     8x2x4        +0,73 /  +0,77          -4,2  /  -1,6
#:     16x4x8       +0,23 /  +0,22          +0,07 /  +0,07
#:
#: und in sigma_xx allein (dort sieht man den Druck, den sigma_v ausblendet)
#: bei nu = 0,499: voll -509 / -51 / -2,6, p1 +4,1 / +1,6 / +0,2 N/mm2 - der
#: punktweise hex8 zeigte am groebsten Netz das falsche Vorzeichen. Bei
#: nu = 0,3 aendert sich die Biegung ab 8x2x4 um hoechstens 0,04 N/mm2.
HEX8_VOLUMEN = "p1"


#: Punktregeln ueber t (die dritte Richtung des hex8, im Sweep die Lagen-
#: richtung): Gauss-Legendre oder Gauss-Lobatto mit n Punkten. Lobatto legt
#: die aeussersten Punkte **auf** die Oberflaeche.
_LOBATTO = {
    3: (np.array([-1.0, 0.0, 1.0]), np.array([1.0, 4.0, 1.0]) / 3.0),
    4: (np.array([-1.0, -1.0 / np.sqrt(5.0), 1.0 / np.sqrt(5.0), 1.0]),
        np.array([1.0, 5.0, 5.0, 1.0]) / 6.0),
    5: (np.array([-1.0, -np.sqrt(3.0 / 7.0), 0.0, np.sqrt(3.0 / 7.0), 1.0]),
        np.array([9.0, 49.0, 64.0, 49.0, 9.0]) / 90.0),
}


def hex8_regel(n_t=2, art="gauss"):
    """(GP (P,3), W (P,)) des hex8: 2x2 Gauss in r und s, ``n_t`` Punkte in t
    (``art`` "gauss" oder "lobatto"). n_t = 2 Gauss ist die Vorgaberegel."""
    if art == "lobatto":
        tt, wt = _LOBATTO[int(n_t)]
    else:
        tt, wt = np.polynomial.legendre.leggauss(int(n_t))
    GP = np.array([[a, b, c] for a in (-_G, _G) for b in (-_G, _G) for c in tt])
    W = np.array([wc for _a in (-_G, _G) for _b in (-_G, _G) for wc in wt])
    return GP, W


def _hex8_operator(X, punkte=None, idx=None, knoten=None, incompatible=True, volumen=None,
                   regel=None):
    """Der Dehnungsoperator eines Stapels hex8 (X (n,8,3)).

    Ohne ``punkte`` an den Integrationspunkten (Vorgabe 2x2x2 Gauss, sonst
    ``regel`` = (GP, W) aus :func:`hex8_regel`; w = W |det J|), mit
    ``punkte`` an den natuerlichen Punkten (Q,3) - mit den inneren Moden und
    der Projektion der Volumendehnung **desselben** Elements (die kommen
    immer aus den Integrationspunkten). ``volumen``: "p1" oder "voll"
    (Vorgabe HEX8_VOLUMEN)."""
    X = np.asarray(X, float)
    n = X.shape[0]
    volumen = HEX8_VOLUMEN if volumen is None else volumen
    GP, W = (_HEX_GP, _HEX_W) if regel is None else regel
    kn = np.arange(8)[None, :].repeat(n, 0) if knoten is None else np.asarray(knoten)
    ix = np.arange(n) if idx is None else np.asarray(idx, dtype=np.int64)
    g, det, Ba = _iso_an_punkten("hex8", X, GP, idx, moden=incompatible)
    w = np.asarray(W, float)[:, None] * det
    vol_q = vol_c = vol_ca = None
    if volumen == "p1":
        vol_q = np.column_stack([np.ones(len(GP)), GP])                      # (P,4)
        Mq = np.einsum("pn,pa,pb->nab", w, vol_q, vol_q)                     # (n,4,4)
        mB = g.reshape(len(GP), n, 24)                                       # m^T B = g flach
        vol_c = np.linalg.solve(Mq, np.einsum("pn,pa,pnj->naj", w, vol_q, mB))
        if Ba is not None:
            mBa = Ba[:, :, :3, :].sum(axis=2)                                # (P,n,9)
            vol_ca = np.linalg.solve(Mq, np.einsum("pn,pa,pnj->naj", w, vol_q, mBa))
    elif volumen != "voll":
        raise ValueError(f"hex8: unbekannter Volumenansatz '{volumen}'")
    if punkte is not None:
        pts = np.asarray(punkte, float).reshape(-1, 3)
        g, det, Ba = _iso_an_punkten("hex8", X, pts, idx, pruefen=False, moden=incompatible)
        w = np.zeros_like(det)
        xi = pts
        if vol_q is not None:
            vol_q = np.column_stack([np.ones(len(pts)), pts])
    else:
        xi = np.asarray(GP, float)
    if Ba is not None and vol_ca is not None:
        # Moden mit derselben Projektion: Deviator punktweise, Volumen linear
        mBa = Ba[:, :, :3, :].sum(axis=2)
        proj = np.einsum("pa,naj->pnj", vol_q, vol_ca)
        Ba = Ba.copy()
        Ba[:, :, :3, :] += ((proj - mBa) / 3.0)[:, :, None, :]
    return Dehnungsoperator("hex8", ix, kn, w, g=g, Ba=Ba, xi=xi, vol_q=vol_q, vol_c=vol_c)


def hex8_matrizen_stapel(X, E, nu, incompatible=True, ohne_kuu=False, regel=None):
    """(Kuu, Kua, Kaa, V) eines **Stapels** Sechsflaechner gleichen Werkstoffs.

    X ist (n,8,3). Seit dem 22.09.2026 aus dem Dehnungsoperator
    (:func:`_hex8_operator`) - derselben Kinematik, die Spannung und
    Plastizitaet lesen. Der Stapel war der Grund fuer den Umbau vom
    21.09.2026: einzeln kostete die Schleife 720,5 µs je Element (verzerrter
    Wuerfel), dreissigmal so viel wie ein ``tet4`` mit 24,2 µs. Nachgemessen
    23.09.2026 (tests/messung_elementzeiten.py, ruhige Maschine, Einkern):
    einzeln 880 µs - ``k_hex8`` ist seit dem Umbau ein Stapel der Laenge 1 und
    traegt dessen Aufwand, rechnet aber nur noch im Rueckfall (Fehlermeldung,
    Diagnose) -, im Stapel 58,3 µs, ``tet4`` 18,0 µs.
    """
    op = _hex8_operator(X, incompatible=incompatible, regel=regel)
    Kuu, Kua, Kaa = matrizen_aus_operator(op, D_matrix(E, nu), ohne_kuu=ohne_kuu)
    return Kuu, Kua, Kaa, op.w.sum(axis=0)


def hex8_matrices(X, E, nu, incompatible=True, ohne_kuu=False):
    """Rueckgabe (Kuu, Kua, Kaa, V) eines Elements; bei incompatible=False
    sind Kua/Kaa None, bei ``ohne_kuu`` ist Kuu None. Derselbe Operator wie
    :func:`hex8_matrizen_stapel`, mit einem Element."""
    Kuu, Kua, Kaa, V = hex8_matrizen_stapel(np.asarray(X, float)[None], E, nu,
                                            incompatible, ohne_kuu)
    return (None if Kuu is None else Kuu[0], None if Kua is None else Kua[0],
            None if Kaa is None else Kaa[0], float(V[0]))


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


def hex8_alpha_stapel(X, E, nu, ue):
    """Die inneren Freiheitsgrade alpha (n,9) eines **Stapels** Sechsflaechner:
    alpha = -Kaa^-1 Kua^T u, aus dem Dehnungsoperator."""
    return moden_aus_operator(_hex8_operator(X), D_matrix(E, nu), ue)


def spannungen_hex8_stapel(X, E, nu, U, punkte=None):
    """Spannungen (n, p, 6) an p Punkten fuer einen **Stapel** Sechsflaechner.

    X ist (n,8,3), U ist (n,24). Ohne ``punkte`` sind es die neun
    :data:`AUSWERTEPUNKTE` (Mitte und acht Ecken). Einzeln kostete das am
    21.09.2026 1120,6 µs je Element, einundsechzigmal so viel wie eine
    tet4-Spannung; der Stapel ist der Grund, warum es ihn gibt. Nachgemessen
    23.09.2026: ``stress_points`` einzeln 2 296 µs (seit dem Umbau ueber den
    Operator, nur noch Rueckfall), dieser Stapel 71,8 µs.
    """
    X = np.asarray(X, float)
    U = np.asarray(U, float).reshape(len(X), 24)
    pts = AUSWERTEPUNKTE["hex8"] if punkte is None else punkte
    D = D_matrix(E, nu)
    alpha = hex8_alpha_stapel(X, E, nu, U)
    aw = _hex8_operator(X, punkte=pts)
    aus = np.empty((len(X), aw.P, 6))
    for q in range(aw.P):
        aus[:, q, :] = dehnung_mit_moden(aw, q, U, alpha) @ D.T
    return aus


def k_hex8_stapel(X, E, nu, incompatible=True, regel=None):
    """Kondensierte Steifigkeiten (n,24,24) und Volumen (n) eines Stapels."""
    op = _hex8_operator(X, incompatible=incompatible, regel=regel)
    return steifigkeit_aus_operator(op, D_matrix(E, nu)), op.w.sum(axis=0)


def k_hex8(X, E, nu, incompatible=True, regel=None):
    K, V = k_hex8_stapel(np.asarray(X, float)[None], E, nu, incompatible, regel)
    return K[0], float(V[0])


def stress_hex8(X, E, nu, ue, r=0.0, s=0.0, t=0.0, incompatible=True):
    X = np.asarray(X, float)[None]
    ue = np.asarray(ue, float).reshape(1, 24)
    D = D_matrix(E, nu)
    alpha = moden_aus_operator(_hex8_operator(X), D, ue) if incompatible else None
    aw = _hex8_operator(X, punkte=[(r, s, t)], incompatible=incompatible)
    return (dehnung_mit_moden(aw, 0, ue, alpha) @ D.T)[0]


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


#: Innere Moden des Keils (Auftrag A6, 22.09.2026): die drei Kantenblasen
#: L_a L_b des Dreiecks und (1 - t^2), je fuer drei Verschiebungen - zwoelf
#: innere Freiheitsgrade, im Element kondensiert wie beim hex8. Ohne sie
#: rechnete der Keil rein isoparametrisch (_k_iso) und war im Kragarm
#: 56,4 % gegen 95,9 % des hex8 am selben Gitter.
#:
#: Die Blasen geben dem Dreieck den quadratischen Anteil in der Ebene (die
#: Querverschiebung einer Biegung waechst mit x^2), (1 - t^2) die Querdehnung
#: ueber die Dicke. Ihr Gradient wird um den Mittelwert ueber das Element
#: vermindert und mit det J0 / det J J0^-1 abgebildet (wie Taylor beim hex8):
#: dann ist das Integral der Modendehnung null, und der Patch-Test haelt fuer
#: jede Form. Gemessen 22.09.2026: 6 Nullmoden (regelmaessig und verzerrt,
#: nu 0,3 und 0,499), Patch-Test 1e-15; Kragarm-Nachweisstelle (Soll 355
#: N/mm2, sigma_v) 90 / 405 / 2295 FHG: -50,0 / -15,2 / -4,1 statt -150 /
#: -57 / -18; der hex8 am selben Gitter +0,8 bei 405 FHG. Die Soll-Vorgabe
#: "hoechstens so viele FHG wie der hex8" erreicht der Keil damit **nicht**.
#: Auch nur (1 - t^2) (drei Moden) wurde gemessen und schadet eher (sigma_xx -129 /
#: -44 / -12); nur die Blasen (neun) enden in sigma_xx bei +2,4 statt gegen null.
PENT6_MODEN = True
#: Mittelwert der natuerlichen Modengradienten ueber den Keil: die Gradienten
#: sind in r, s linear und in t linear (die Blasen haengen nicht an t), der
#: Mittelwert ist also ihr Wert im Schwerpunkt (1/3, 1/3, 0).


def _pent6_moden_grad(r, s, t):
    """Natuerliche Gradienten (4,3) der vier skalaren Keilmoden."""
    L = (1.0 - r - s, r, s)
    dL = ((-1.0, -1.0), (1.0, 0.0), (0.0, 1.0))
    aus = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        aus.append([L[a] * dL[b][0] + L[b] * dL[a][0], L[a] * dL[b][1] + L[b] * dL[a][1], 0.0])
    aus.append([0.0, 0.0, -2.0 * t])
    return np.array(aus, float)


_PENT6_DM_MITTEL = _pent6_moden_grad(1.0 / 3.0, 1.0 / 3.0, 0.0)


def pent6_regel(n_t=2, art="gauss"):
    """(GP, W) des Keils: drei Dreieckspunkte, ``n_t`` Punkte in t (Gauss oder
    Gauss-Lobatto, wie hex8_regel)."""
    if art == "lobatto":
        tt, wt = _LOBATTO[int(n_t)]
    else:
        tt, wt = np.polynomial.legendre.leggauss(int(n_t))
    GP = np.array([[a, b, c] for a, b in _TRI3_GP for c in tt])
    W = np.array([w * wc for w in _TRI3_W for wc in wt])
    return GP, W


def _pent6_operator(X, punkte=None, idx=None, knoten=None, moden=None, regel=None):
    """Der Dehnungsoperator eines Stapels pent6 (X (n,6,3)) - mit den inneren
    Moden (PENT6_MODEN), an den Integrationspunkten (Vorgabe 3 x 2) oder an
    ``punkte``."""
    X = np.asarray(X, float)
    n = X.shape[0]
    moden = PENT6_MODEN if moden is None else moden
    GP, W = (_PENT6_GP, _PENT6_W) if regel is None else regel
    kn = np.arange(6)[None, :].repeat(n, 0) if knoten is None else np.asarray(knoten)
    ix = np.arange(n) if idx is None else np.asarray(idx, dtype=np.int64)
    if punkte is None:
        pts = np.asarray(GP, float)
        g, det, _Ba = _iso_an_punkten("pent6", X, pts, idx)
        w = np.asarray(W, float)[:, None] * det
    else:
        pts = np.asarray(punkte, float).reshape(-1, 3)
        g, det, _Ba = _iso_an_punkten("pent6", X, pts, idx, pruefen=False)
        w = np.zeros_like(det)
    Ba = None
    if moden:
        _N0, dN0 = pent6_N_dN(1.0 / 3.0, 1.0 / 3.0, 0.0)
        J0 = np.einsum("ki,nkj->nij", dN0, X)
        detJ0 = np.linalg.det(J0)
        Ba = np.empty((len(pts), n, 6, 12))
        for q, (r, s_, t) in enumerate(pts):
            _N, dNr = pent6_N_dN(r, s_, t)
            J = np.einsum("ki,nkj->nij", dNr, X)
            detJ = np.linalg.det(J)
            dM = _pent6_moden_grad(r, s_, t) - _PENT6_DM_MITTEL
            gm = (detJ0 / detJ)[:, None, None] * np.linalg.solve(
                J0, np.broadcast_to(dM.T, (n, 3, 4))).transpose(0, 2, 1)
            Ba[q] = _b_stapel(gm)
    return Dehnungsoperator("pent6", ix, kn, w, g=g, Ba=Ba, xi=pts)


def k_pent6(X, E, nu, regel=None):
    """Steifigkeit (18x18) und Volumen des Pent6 - ueber den Dehnungsoperator,
    mit den inneren Moden (PENT6_MODEN)."""
    op = _pent6_operator(np.asarray(X, float)[None], regel=regel)
    return steifigkeit_aus_operator(op, D_matrix(E, nu))[0], float(op.w.sum())


def k_pent15(X, E, nu):
    """Steifigkeit (45x45) und Volumen des Pent15 (6 Dreieckspunkte x 3 Gauss)."""
    return _k_iso(pent15_N_dN, _PENT15_GP, _PENT15_W, X, E, nu, "Pent15")


def stress_pent6(X, E, nu, ue, r=1.0 / 3.0, s=1.0 / 3.0, t=0.0):
    return stress_points("pent6", X, E, nu, ue, punkte=[(r, s, t)])[0]


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
# Seiten als Flaechen fuer Kontakt und Lasten (auch gekruemmt, tri6/quad8)
# --------------------------------------------------------------------------
_R7A, _R7B = (6.0 - np.sqrt(15.0)) / 21.0, (6.0 + np.sqrt(15.0)) / 21.0
_R7WA, _R7WB = (155.0 - np.sqrt(15.0)) / 1200.0, (155.0 + np.sqrt(15.0)) / 1200.0
#: Dreiecksregel nach Radon, 7 Punkte, exakt bis Grad 5 (Gewichte auf Flaeche 1/2)
_TRI7_GP = np.array([[1.0 / 3.0, 1.0 / 3.0],
                     [_R7A, _R7A], [1.0 - 2.0 * _R7A, _R7A], [_R7A, 1.0 - 2.0 * _R7A],
                     [_R7B, _R7B], [1.0 - 2.0 * _R7B, _R7B], [_R7B, 1.0 - 2.0 * _R7B]])
_TRI7_W = 0.5 * np.array([9.0 / 40.0] + [_R7WA] * 3 + [_R7WB] * 3)
#: Viereck 4x4 Gauss, exakt bis Grad 7 je Richtung
_G4P, _G4W = np.polynomial.legendre.leggauss(4)
_QUAD16_GP = np.array([[a, b] for a in _G4P for b in _G4P])
_QUAD16_W = np.array([wa * wb for wa in _G4W for wb in _G4W])
#: Knotenzahl der Seite -> Regel fuer die Flaechenintegration
_SEITEN_REGEL = {3: (_TRI7_GP, _TRI7_W), 6: (_TRI7_GP, _TRI7_W),
                 4: (_QUAD16_GP, _QUAD16_W), 8: (_QUAD16_GP, _QUAD16_W)}


def seiten_integration_stapel(P, innen=None, regel=None) -> dict:
    """Integrationsdaten eines **Stapels** Seiten gleicher Knotenzahl.

    P ist (n,k,3) mit k = 3, 4, 6 oder 8 (Ecken zuerst, dann Kantenmitten wie
    in FLAECHEN), ``innen`` (n,3) ein Punkt im Element hinter der Seite
    (der gegenueberliegende Knoten, wie Model._seitennormale ihn nimmt). Die
    Normalen zeigen dann von ihm weg - nach aussen. Ohne ``innen`` folgen sie
    der Rechtsschraube der Ecken.

    Rueckgabe:
        "punkte"   (n,m,3) Integrationspunkte im globalen System
        "dA"       (n,m)   Gewichte mal Flaechen-Jacobideterminante
        "normale"  (n,m,3) Einheitsnormalen an den Punkten
        "N"        (m,k)   Ansatzwerte (fuer alle Seiten gleich)
        "xi"       (m,2)   Seitenkoordinaten der Punkte
        "knotenflaechen" (n,k)  Integral N_i dA - die konsistenten Knoten-
                   anteile eines gleichmaessigen Drucks. Beim ebenen tri6 sind
                   sie an den Ecken **null** und an jeder Kantenmitte A/3
                   (Integral L(2L-1) = 0, Integral 4 L_i L_j = A/3), beim tri3
                   A/3 je Ecke.

    Die Regel (Vorgabe: Dreieck 7 Punkte Grad 5, Viereck 4x4) integriert
    N_i dA auf ebenen Seiten exakt; auf gekruemmten ist dA keine Polynom-
    funktion mehr und die Regel eine Naeherung.
    """
    P = np.asarray(P, float)
    if P.ndim == 2:
        P = P[None]
    n, k = P.shape[0], P.shape[1]
    GP, W = regel if regel is not None else _SEITEN_REGEL[k]
    m = len(GP)
    N = np.empty((m, k))
    dN = np.empty((m, k, 2))
    for q, (a, b) in enumerate(GP):
        N[q], dN[q] = seite_N_dN(k, a, b)
    punkte = np.einsum("mk,nkj->nmj", N, P)
    t1 = np.einsum("mk,nkj->nmj", dN[:, :, 0], P)
    t2 = np.einsum("mk,nkj->nmj", dN[:, :, 1], P)
    nA = np.cross(t1, t2)                                  # Normale mal dA/(da db)
    betrag = np.linalg.norm(nA, axis=2)
    if np.any(betrag <= 0.0):
        s, q = np.argwhere(betrag <= 0.0)[0]
        raise ValueError(f"Seite {int(s)} im Stapel ist an Punkt {int(q)} entartet "
                         "(Flaechen-Jacobideterminante null)")
    normale = nA / betrag[:, :, None]
    if innen is not None:
        innen = np.asarray(innen, float).reshape(n, 3)
        ecken = 4 if k in (4, 8) else 3
        mitte = P[:, :ecken, :].mean(axis=1)
        # Je Seite **ein** Vorzeichen, am Punkt, der der Seitenmitte am
        # naechsten liegt - eine gekruemmte Seite soll kein Normalenfeld
        # bekommen, das auf ihr die Richtung wechselt.
        q0 = int(np.argmin(np.linalg.norm(np.asarray(GP) - np.asarray(GP).mean(axis=0), axis=1)))
        vz = np.sign(np.einsum("nj,nj->n", normale[:, q0, :], mitte - innen))
        vz[vz == 0.0] = 1.0
        normale = normale * vz[:, None, None]
    dA = betrag * np.asarray(W)[None, :]
    return {"punkte": punkte, "dA": dA, "normale": normale, "N": N,
            "xi": np.asarray(GP, float).copy(),
            "knotenflaechen": np.einsum("nm,mk->nk", dA, N)}


def punkt_und_normale(P, a, b, innen=None):
    """Punkt und Einheitsnormale einer Seite (k,3) an den Seitenkoordinaten
    (a, b) - fuer die Projektion eines Gegenknotens auf eine gekruemmte
    Seite. Mit ``innen`` wie bei :func:`seiten_integration_stapel` nach aussen
    gerichtet; die Richtung wird an der Seitenmitte bestimmt, nicht am
    Punkt, damit sie auf der ganzen Seite dieselbe ist."""
    P = np.asarray(P, float)
    k = P.shape[0]
    N, dN = seite_N_dN(k, a, b)
    x = N @ P
    nv = np.cross(dN[:, 0] @ P, dN[:, 1] @ P)
    betrag = float(np.linalg.norm(nv))
    if betrag <= 0.0:
        raise ValueError("Seite ist an diesem Punkt entartet")
    nv = nv / betrag
    if innen is not None:
        a0, b0 = (1.0 / 3.0, 1.0 / 3.0) if k in (3, 6) else (0.0, 0.0)
        N0, dN0 = seite_N_dN(k, a0, b0)
        n0 = np.cross(dN0[:, 0] @ P, dN0[:, 1] @ P)
        if float(n0 @ (N0 @ P - np.asarray(innen, float))) < 0.0:
            nv = -nv
    return x, nv


# --------------------------------------------------------------------------
def solid_volume(typ, X) -> float:
    X = np.asarray(X, float)
    if typ in ("tetp2", "tetp3", "tetp4"):
        # gerade gerechnet: gekruemmte Kanten kennt nur das Modell
        # (tetp.kantenmitten); fuer Volumenbilanzen genuegt die Sehne
        return tet4_shape_grad(X[:4])[1]
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


#: Eckpunkte in natuerlichen Koordinaten, an denen det J zusaetzlich zu den
#: Gausspunkten geprueft wird. Bei der Pyramide nur die Grundflaeche: an der
#: Spitze ist die Abbildung kollabiert und det J dort immer null.
_JACOBI_ECKEN = {
    "tet4": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
    # beim gekruemmten tet10 (Mittelknoten auf der wahren Geometrie, B7)
    # faellt det J zuerst an den Kanten - darum auch die Kantenmitten
    "tet10": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
              (0.5, 0, 0), (0.5, 0.5, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0, 0.5), (0, 0.5, 0.5)],
    "hex8": [tuple(p) for p in _HEX_SIGNS],
    "hex20": [tuple(p) for p in _HEX_SIGNS],
    "pent6": [(0, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1), (1, 0, 1), (0, 1, 1)],
    "pent15": [(0, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1), (1, 0, 1), (0, 1, 1)],
    "pyr5": [tuple(p) + (-1.0,) for p in _PYR_SIGNS],
}


def jacobi_volumen_stapel(typ, X) -> dict:
    """Vorzeichenbehaftetes Volumen und det J eines **Stapels** Elemente.

    X ist (n,k,3). Rueckgabe {"V": (n,), "det_min": (n,), "det_max": (n,)}:
    V = Summe w det J ueber die Gausspunkte **mit** Vorzeichen (solid_volume
    nimmt den Betrag), det_min/det_max ueber Gausspunkte und Ecken
    (_JACOBI_ECKEN). Ein umgestuelptes Element hat det_min < 0.

    Was diese Pruefung **nicht** faengt (gemessen 22.09.2026 von der
    Statik3D-Sitzung, festgehalten in tests/test_elemente_volumen.py): ein
    hex8 mit verdrehtem Deckel (4,5,6,7 -> 5,6,7,4) ist fuer sich ein
    gueltiges Element - det J ueberall positiv, Volumen 2/3 statt 1. Ihn
    faengt nur die Bilanz am Koerper (Summe der Elementvolumina gegen das
    Randvolumen), nicht das Element.
    """
    fn, GP, W = _ISO[typ]
    X = np.asarray(X, float)
    n = X.shape[0]
    V = np.zeros(n)
    det_min = np.full(n, np.inf)
    det_max = np.full(n, -np.inf)
    for (r, s, t), w in zip(GP, W):
        _N, dNr = fn(r, s, t)
        det = np.linalg.det(np.einsum("ki,nkj->nij", dNr, X))
        V += float(w) * det
        det_min = np.minimum(det_min, det)
        det_max = np.maximum(det_max, det)
    for (r, s, t) in _JACOBI_ECKEN[typ]:
        _N, dNr = fn(float(r), float(s), float(t))
        det = np.linalg.det(np.einsum("ki,nkj->nij", dNr, X))
        det_min = np.minimum(det_min, det)
        det_max = np.maximum(det_max, det)
    return {"V": V, "det_min": det_min, "det_max": det_max}


def jacobi_pruefung(model, elemente=None) -> list:
    """[(Element, Typ, kleinstes det J)] aller Volumenelemente, deren Jacobi-
    Determinante an einem Integrationspunkt, einer Ecke oder (tet10) einer
    Kantenmitte nicht positiv ist - fuer die Netzabnahme (B7: gekruemmte
    Elemente muessen **laut** auffallen, mit Nummer, bevor gerechnet wird).
    Stapelweise je Typ (jacobi_volumen_stapel)."""
    idx = range(len(model.elements)) if elemente is None else elemente
    je_typ: dict = {}
    for i in idx:
        typ = model.elements[int(i)].typ
        if typ in _ISO:
            je_typ.setdefault(typ, []).append(int(i))
    schlecht = []
    p_el = [int(i) for i in idx if model.elements[int(i)].typ in ("tetp2", "tetp3", "tetp4")]
    if p_el:
        # Tetraeder mit Ordnung p: gekruemmt ueber die Kantenmitten des Modells
        from . import tetp as _tp
        schlecht.extend(_tp.jacobi_pruefung(model, p_el))
    for typ, liste in je_typ.items():
        k = _KNOTENZAHL[typ]
        for a0 in range(0, len(liste), 50_000):
            teil = liste[a0:a0 + 50_000]
            X = np.asarray(model.nodes, float)[np.asarray([model.elements[i].nodes[:k] for i in teil])]
            d = jacobi_volumen_stapel(typ, X)
            for a in np.flatnonzero(d["det_min"] <= 0.0):
                schlecht.append((teil[int(a)], typ, float(d["det_min"][a])))
    return schlecht


def jacobi_volumen(typ, X) -> dict:
    """:func:`jacobi_volumen_stapel` fuer ein Element: {"V", "det_min", "det_max"}."""
    d = jacobi_volumen_stapel(typ, np.asarray(X, float)[None, :, :])
    return {k: float(v[0]) for k, v in d.items()}


# --------------------------------------------------------------------------
# Entartete Elemente: zusammenfallende Knoten (23.09.2026)
# --------------------------------------------------------------------------
#: Gegenueberliegende Seiten des hex8 (Index in FLAECHEN["hex8"]) und die
#: Zuordnung ihrer Knoten ueber die verbindenden Kanten.
_HEX8_GEGENSEITEN = ((0, 1, {0: 4, 1: 5, 2: 6, 3: 7}),
                     (2, 4, {0: 3, 1: 2, 5: 6, 4: 7}),
                     (3, 5, {1: 0, 2: 3, 6: 7, 5: 4}))


def _kreis_ohne_doppelte(folge, kn):
    """Lokale Indizes einer Seite in Umlaufrichtung, aufeinanderfolgend gleiche
    Knoten (auch ueber das Ende hinweg) nur einmal."""
    aus = []
    for a in folge:
        if not aus or kn[a] != kn[aus[-1]]:
            aus.append(a)
    while len(aus) > 1 and kn[aus[0]] == kn[aus[-1]]:
        aus.pop()
    return aus


#: Kanten der quadratischen Typen in der Reihenfolge ihrer Kantenmitten
#: (hex20: Mitten 8..19; pent15: 6..14; tet10: 4..9) - siehe hex20_N_dN,
#: FLAECHEN["pent15"] und FLAECHEN["tet10"]
_KANTEN_QUADRATISCH = {
    "hex20": ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)),
    "pent15": ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)),
    "tet10": ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)),
}
#: quadratischer Typ -> (linearer Typ der Ecken, Eckenzahl); linear umgewandelt
#: -> quadratisches Ziel (eine Pyramide hat kein quadratisches Gegenstueck)
_QUADRATISCH_ENTARTUNG = {"hex20": ("hex8", 8), "pent15": ("pent6", 6)}
_QUADRATISCH_ZIEL = {"pent6": "pent15", "tet4": "tet10"}


def _entartung_quadratisch(typ, kn, X, grenze_volumen) -> tuple:
    """entartung_aufloesen fuer hex20 und pent15 (VQ203, 23.09.2026): die
    Ecken wie beim linearen Typ einordnen, dann jede Kante des Ziels (pent15,
    tet10) auf ihre Kantenmitte abbilden. Streng: die Mitte einer
    zusammengefallenen Kante muss derselbe Knoten wie ihre Ecke sein, und
    Kanten, die auf dieselbe Zielkante fallen, muessen dieselbe Mitte haben -
    sonst bliebe ein Knoten ohne Element (singulaer) oder die Kante haette
    zwei Mitten. Gemessen am Kragarm: der entartete hex20 direkt gerechnet
    -213 / -96 N/mm2 bei (4,1,2) / (8,2,4), als pent15 -4,7 / -0,02."""
    lin, ne = _QUADRATISCH_ENTARTUNG[typ]
    ecken = kn[:ne]
    try:
        V0 = abs(jacobi_volumen(typ, X)["V"])
    except Exception:                        # noqa: BLE001
        V0 = float("inf")
    if len(set(ecken)) <= 3 or V0 <= grenze_volumen:
        return "null", typ, kn, "zwei Knoten des Elements sind derselbe, kein Volumen"
    art, lin_typ, lin_kn, grund = entartung_aufloesen(lin, ecken, X[:ne], grenze_volumen)
    if art == "gut":
        return "fehler", typ, kn, ("zusammenfallende Kantenmitten bei getrennten Ecken "
                                   f"(Volumen {V0:.3g} m³)")
    if art != "umwandeln" or lin_typ not in _QUADRATISCH_ZIEL:
        return "fehler", typ, kn, (f"zusammenfallende Knoten, keine quadratische Umwandlung "
                                   f"({grund or lin_typ}; Volumen {V0:.3g} m³)")
    ziel = _QUADRATISCH_ZIEL[lin_typ]
    # Kante (Ecke, Ecke) -> Mitten, aus den Kanten des entarteten Elements
    mitte: dict = {}
    for k, (a, b) in enumerate(_KANTEN_QUADRATISCH[typ]):
        m = kn[ne + k]
        if kn[a] == kn[b]:
            if m != kn[a]:
                return "fehler", typ, kn, ("die Mitte einer zusammengefallenen Kante ist ein "
                                           f"eigener Knoten ({m + 1}) - er hinge an keinem Element")
            continue
        mitte.setdefault(frozenset((kn[a], kn[b])), set()).add(m)
    neu = list(lin_kn)
    for a, b in _KANTEN_QUADRATISCH[ziel]:
        ms = mitte.get(frozenset((lin_kn[a], lin_kn[b])), set())
        if len(ms) != 1:
            return "fehler", typ, kn, (f"die Kante {lin_kn[a] + 1}–{lin_kn[b] + 1} des {ziel} hat "
                                       f"{'keine' if not ms else 'mehrere'} Kantenmitte(n)")
        neu.append(next(iter(ms)))
    if set(neu) != set(kn):
        return "fehler", typ, kn, "nach der Umwandlung bliebe ein Knoten ohne Element"
    lage = {k: X[i] for i, k in enumerate(kn)}
    d = jacobi_volumen(ziel, np.array([lage[k] for k in neu]))
    if d["V"] <= 0.0 or d["det_min"] < -1e-12 * max(abs(d["det_max"]), 1e-300) \
            or abs(d["V"] - V0) > 1e-6 * V0:
        return "fehler", typ, kn, (f"zusammenfallende Knoten, die Umwandlung in {ziel} trifft das "
                                   f"Volumen nicht ({d['V']:.3g} statt {V0:.3g} m³)")
    return "umwandeln", ziel, neu, f"{typ} mit zusammenfallenden Knoten ist ein {ziel}"


def entartung_aufloesen(typ, knoten, X, grenze_volumen: float = 1e-15) -> tuple:
    """Ein Volumenelement mit zusammenfallenden Knoten einordnen:
    (art, neuer_typ, neue_knoten, grund) mit art

    * "gut"       - keine doppelten Knoten;
    * "umwandeln" - es ist eindeutig ein Element niedrigerer Art: hex8 mit
      einer Seite auf einen Punkt -> pyr5; hex8 mit zwei gegenueberliegenden
      Seiten zu Dreiecken, deren Spitzen einander ueber Kanten gegenueber
      liegen -> pent6; pent6 mit einer zusammengezogenen Laengskante -> pyr5;
      vier verschiedene Knoten -> tet4 (auch aus pent6 und pyr5). Die neue
      Knotenfolge ist so ausgerichtet, dass das Volumen positiv ist;
    * "null"      - kein Volumen (hoechstens drei verschiedene Knoten, oder
      das Volumen liegt unter ``grenze_volumen``): Weglassen ist exakt;
    * "fehler"    - Volumen > 0, aber keine eindeutige Umwandlung (etwa ein
      hex8 mit nur einer zusammengezogenen Kante, oder ein quadratisches
      Element).

    Warum: bis zum 23.09.2026 galt jedes Element mit doppeltem Knoten als
    "ohne Ausdehnung" und fiel aus der Rechnung. Ein zum Keil entarteter
    Sechsflaechner hat aber Volumen - am Kragarm aus solchen Keilen (128
    Elemente, 408 FHG) lief die Rechnung mit 0,0 mm Durchbiegung durch, nur
    mit einer WARNUNG (tests/test_entartung.py)."""
    kn = [int(k) for k in knoten]
    X = np.asarray(X, float)
    einzeln = list(dict.fromkeys(kn))
    if len(einzeln) == len(kn):
        return "gut", typ, kn, ""
    if typ in _QUADRATISCH_ENTARTUNG:
        return _entartung_quadratisch(typ, kn, X, grenze_volumen)
    try:
        V0 = abs(jacobi_volumen(typ, X)["V"])
    except Exception:                        # noqa: BLE001 - dann aus den Ecken
        V0 = float("inf")
    if len(einzeln) <= 3 or V0 <= grenze_volumen:
        return "null", typ, kn, "zwei Knoten des Elements sind derselbe, kein Volumen"
    lage = {k: X[i] for i, k in enumerate(kn)}
    kandidaten = []
    if typ in ("hex8", "pent6", "pyr5") and len(einzeln) == 4:
        kandidaten.append(("tet4", einzeln))
    elif typ == "hex8" and len(einzeln) == 5:
        for f, g, _m in _HEX8_GEGENSEITEN:
            for a, b in ((f, g), (g, f)):
                spitze = {kn[i] for i in FLAECHEN["hex8"][a]}
                basis = [kn[i] for i in FLAECHEN["hex8"][b]]
                if len(spitze) == 1 and len(set(basis)) == 4:
                    kandidaten.append(("pyr5", basis + [spitze.pop()]))
    elif typ == "hex8" and len(einzeln) == 6:
        for f, g, m in _HEX8_GEGENSEITEN:
            tf = _kreis_ohne_doppelte(FLAECHEN["hex8"][f], kn)
            if len(tf) != 3:
                continue
            unten = [kn[a] for a in tf]
            oben = [kn[m[a]] for a in tf]
            # die Gegenseite muss an denselben Kanten zusammengezogen sein
            if len(set(oben)) == 3 and len(set(unten + oben)) == 6 \
                    and len(_kreis_ohne_doppelte(FLAECHEN["hex8"][g], kn)) == 3:
                kandidaten.append(("pent6", unten + oben))
    elif typ == "pent6" and len(einzeln) == 5:
        for i in range(3):
            if kn[i] == kn[i + 3]:
                for q in FLAECHEN["pent6"][2:]:
                    if i not in q and i + 3 not in q:
                        kandidaten.append(("pyr5", [kn[a] for a in q] + [kn[i]]))
    # eindeutig heisst: genau eine Deutung (dieselbe Knotenmenge zaehlt einmal)
    deutungen = {(t, frozenset(k)): (t, k) for t, k in kandidaten}
    if len(deutungen) != 1:
        grund = ("zusammenfallende Knoten, aber keine eindeutige Umwandlung"
                 if not deutungen else "zusammenfallende Knoten, mehrdeutig")
        return "fehler", typ, kn, f"{grund} (Volumen {V0:.3g} m³)"
    neu_typ, neu = next(iter(deutungen.values()))
    neu = list(neu)
    for _versuch in range(2):
        d = jacobi_volumen(neu_typ, np.array([lage[k] for k in neu]))
        if d["V"] > 0.0:
            break
        # Umlaufsinn drehen: die Folge spiegeln
        if neu_typ == "tet4":
            neu = [neu[0], neu[2], neu[1], neu[3]]
        elif neu_typ == "pyr5":
            neu = [neu[0], neu[3], neu[2], neu[1], neu[4]]
        else:
            neu = [neu[0], neu[2], neu[1], neu[3], neu[5], neu[4]]
    if d["V"] <= 0.0 or d["det_min"] < -1e-12 * max(abs(d["det_max"]), 1e-300) \
            or abs(d["V"] - V0) > 1e-9 * max(V0, 1e-300) + 1e-6 * V0:
        return "fehler", typ, kn, (f"zusammenfallende Knoten, die Umwandlung in {neu_typ} "
                                   f"trifft das Volumen nicht ({d['V']:.3g} statt {V0:.3g} m³)")
    return "umwandeln", neu_typ, neu, f"{typ} mit zusammenfallenden Knoten ist ein {neu_typ}"


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

#: Natuerliche Koordinaten der Eckknoten je Typ, in Knotenreihenfolge
ECKEN_NATUERLICH = {
    "tet4": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
    "tet10": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
    "hex8": [tuple(p) for p in _HEX_SIGNS],
    "hex20": [tuple(p) for p in _HEX_SIGNS],
    "pent6": [(0.0, 0.0, -1.0), (1.0, 0.0, -1.0), (0.0, 1.0, -1.0),
              (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)],
    "pent15": [(0.0, 0.0, -1.0), (1.0, 0.0, -1.0), (0.0, 1.0, -1.0),
               (0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0)],
    "pyr5": [(-1.0, -1.0, -1.0), (1.0, -1.0, -1.0), (1.0, 1.0, -1.0), (-1.0, 1.0, -1.0),
             (0.0, 0.0, 1.0)],
}


def ecken_der_auswertepunkte(typ) -> list:
    """Fuer jeden Eckknoten des Typs (Knotenreihenfolge) die Nummer des
    Auswertepunkts in AUSWERTEPUNKTE[typ], der auf ihm liegt - oder 0 (die
    Mitte), wenn keiner es tut (tet4: ein Punkt fuer alle vier Ecken).

    Die Reihenfolge der Auswertepunkte ist **nicht** immer die der Knoten:
    beim hex8 laufen sie r-s-t geschachtelt (-1,-1,-1), (-1,-1,+1), ..., die
    Knoten gegen den Uhrzeiger unten, dann oben."""
    pts = [tuple(float(x) for x in p) for p in AUSWERTEPUNKTE[typ]]
    aus = []
    for e in ECKEN_NATUERLICH[typ]:
        e = tuple(float(x) for x in e)
        aus.append(pts.index(e) if e in pts else 0)
    return aus


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
    if typ == "pent6":
        X3 = X[None]
        ue3 = np.asarray(ue, float).reshape(1, 18)
        D = D_matrix(E, nu)
        op = _pent6_operator(X3)
        al = moden_aus_operator(op, D, ue3) if op.Ba is not None else None
        aw = _pent6_operator(X3, punkte=pts)
        return [(dehnung_mit_moden(aw, q, ue3, al) @ D.T)[0] for q in range(aw.P)]
    if typ in ("hex20", "pent15", "pyr5"):
        fn = _ISO[typ][0]
        return [_stress_iso(fn, X, E, nu, ue, *p) for p in pts]
    if typ != "hex8":
        return []
    # Hex8: ueber den Dehnungsoperator (dieselbe Kinematik wie die
    # Steifigkeit). ``alpha`` kann von aussen kommen - dann faellt die
    # Kondensation weg.
    X3 = X[None]
    ue3 = np.asarray(ue, float).reshape(1, 24)
    D = D_matrix(E, nu)
    if alpha is None:
        alpha3 = moden_aus_operator(_hex8_operator(X3), D, ue3)
    else:
        alpha3 = np.asarray(alpha, float).reshape(1, 9)
    aw = _hex8_operator(X3, punkte=pts)
    return [(dehnung_mit_moden(aw, q, ue3, alpha3) @ D.T)[0] for q in range(aw.P)]


# --------------------------------------------------------------------------
# Dehnungsoperator: eine Kinematik fuer Steifigkeit, Spannung, Plastizitaet
# --------------------------------------------------------------------------
# Bis zum 22.09.2026 stellte jeder Leser seine Verzerrungsmatrix selbst auf:
# die Steifigkeit in k_<typ> bzw. k_hex8_stapel, die Spannung in
# stress_points, die Plastizitaet in plastizitaet._stapel und
# _schritt_schleife (aus _ISO, je Gausspunkt). Solange alle dasselbe
# isoparametrische B rechnen, ist das nur doppelt; sobald ein Element eine
# andere Kinematik hat (B-bar, geglaettete Dehnung, mehr Punkte ueber die
# Dicke), rechnen Steifigkeit und Fliessen still mit zwei verschiedenen.
# Darum liefert das Element **einen** Operator je Integrationspunkt, und alle
# lesen ihn (Auftrag an die Element-Sitzung, 22.09.2026, Pflicht 1).
from dataclasses import dataclass as _dataclass                    # noqa: E402

#: Globale Freiheitsgrade je Knoten (res.u ist (nn, 6), auch bei Volumen)
_NDOF_GLOBAL = 6


@_dataclass
class Dehnungsoperator:
    """Verzerrungen eines Stapels gleichartiger Elemente an P Punkten.

    ``knoten`` (n,k): die Knoten, an denen die Punkte haengen. k darf groesser
    sein als die Knotenzahl des Elements (ein geglaetteter Punkt haengt auch
    an Nachbarknoten); leere Plaetze tragen einen Elementknoten mit
    Nullgradient. ``w`` (P,n): Gewicht je Punkt (w |det J| bzw.
    Volumenanteil), die Summe ueber P ist das Elementvolumen - bei einem
    reinen Auswerteoperator (auswerteoperator) ohne Bedeutung.

    Genau eines von ``g`` (P,n,k,3) - Gradienten, B = B_from_grad(g) - und
    ``B`` (P,n,6,3k) - allgemeines B, etwa mit B-bar - ist gesetzt. ``Ba``
    (P,n,6,na): innere Moden, im Element kondensiert (hex8), sonst None.
    ``xi`` (P,3): natuerliche Koordinaten der Punkte, None bei Punkten ohne
    solche (geglaettete Gebiete).
    """
    typ: str
    idx: np.ndarray
    knoten: np.ndarray
    w: np.ndarray
    g: np.ndarray = None
    B: np.ndarray = None
    Ba: np.ndarray = None
    xi: np.ndarray = None
    #: Projektion der Volumendehnung (hex8 "p1"): theta = vol_q[p] . (vol_c u)
    #: mit vol_q (P,4) = (1, xi, eta, zeta) am Punkt und vol_c (n,4,3k) je
    #: Element. Der Deviator bleibt punktweise. None: keine Projektion.
    vol_q: np.ndarray = None
    vol_c: np.ndarray = None
    #: Globale FHG je Element und Ansatzfunktion (n, 3k), Spalte 3a + c fuer
    #: Funktion a, Komponente c. Gesetzt fuer Ansaetze, deren Freiheitsgrade
    #: nicht an Knoten haengen (hierarchische Kanten-/Flaechen-/Innenfunktionen,
    #: die wie die Woelb-FHG hinter den Knoten-FHG liegen); dann darf
    #: ``knoten`` None sein. None: 6 * knoten + 0..2.
    fhg: np.ndarray = None

    @property
    def n(self) -> int:
        return int(self.w.shape[1])

    @property
    def k(self) -> int:
        if self.knoten is not None:
            return int(self.knoten.shape[1])
        return int(self.fhg.shape[1]) // 3

    @property
    def P(self) -> int:
        return int(self.w.shape[0])

    @property
    def na(self) -> int:
        return 0 if self.Ba is None else int(self.Ba.shape[3])

    def dofs(self) -> np.ndarray:
        """Globale FHG (n, 3k): ``fhg``, wenn gesetzt, sonst drei
        Verschiebungen je Knoten."""
        if self.fhg is not None:
            return np.asarray(self.fhg, dtype=np.int64)
        return (_NDOF_GLOBAL * self.knoten[:, :, None]
                + np.arange(3)[None, None, :]).reshape(self.n, 3 * self.k)

    def b(self, p: int) -> np.ndarray:
        """Verzerrungsmatrix (n, 6, 3k) am Punkt p."""
        B = self.B[p] if self.B is not None else _b_stapel(self.g[p])
        if self.vol_c is None:
            return B
        # B-bar: die Volumenzeile m^T B durch ihre Projektion ersetzen
        mB = B[:, :3, :].sum(axis=1)                                   # (n,3k)
        proj = np.einsum("a,naj->nj", self.vol_q[p], self.vol_c)
        B = B.copy()
        B[:, :3, :] += ((proj - mB) / 3.0)[:, None, :]
        return B

    @property
    def nur_gradienten(self) -> bool:
        """True, wenn B = B_from_grad(g) gilt (kein allgemeines B, keine Projektion)."""
        return self.B is None and self.vol_c is None

    def dehnung(self, p: int, ue) -> np.ndarray:
        """Voigt-Dehnung (n,6) am Punkt p zu den Elementverschiebungen ue (n,3k)
        - ohne die inneren Moden (die addiert :func:`dehnung_mit_moden`)."""
        ue = np.asarray(ue, float).reshape(self.n, 3 * self.k)
        return (self.b(p) @ ue[:, :, None])[:, :, 0]

    def teil(self, auswahl) -> "Dehnungsoperator":
        """Derselbe Operator fuer eine Teilmenge der Elemente (Maske oder Positionen)."""
        a = np.asarray(auswahl)
        return Dehnungsoperator(
            self.typ, self.idx[a], None if self.knoten is None else self.knoten[a],
            self.w[:, a],
            None if self.g is None else self.g[:, a],
            None if self.B is None else self.B[:, a],
            None if self.Ba is None else self.Ba[:, a], self.xi,
            self.vol_q, None if self.vol_c is None else self.vol_c[a],
            None if self.fhg is None else self.fhg[a])


def _iso_an_punkten(typ, X, punkte, idx=None, pruefen=True, moden=True):
    """Gradienten g (Q,n,k,3), det J (Q,n) und - beim hex8 - die Modenmatrix
    Ba (Q,n,6,9) eines Stapels X (n,k,3) an den natuerlichen Punkten (Q,3).

    ``pruefen``: det J <= 0 wirft ValueError mit der Elementnummer (idx)."""
    fn = _ISO[typ][0]
    X = np.asarray(X, float)
    n, k = X.shape[0], X.shape[1]
    Q = len(punkte)
    g = np.empty((Q, n, k, 3))
    det = np.empty((Q, n))
    Ba = None
    if typ == "hex8" and moden:
        Ba = np.empty((Q, n, 6, 9))
        _N0, dN0 = hex8_N_dN(0.0, 0.0, 0.0)
        J0 = np.einsum("ki,nkj->nij", dN0, X)
        detJ0 = np.linalg.det(J0)
    for q, (r, s_, t) in enumerate(punkte):
        _N, dNr = fn(float(r), float(s_), float(t))
        J = np.einsum("ki,nkj->nij", dNr, X)
        d = np.linalg.det(J)
        if pruefen and np.any(d <= 0.0):
            a = int(np.argmin(d))
            nr = int(idx[a]) + 1 if idx is not None else a
            raise ValueError(f"Element {nr} ({typ}): negative Jacobi-Determinante am Punkt "
                             f"{q} (det J = {d[a]:.3e}) - das Element ist umgestuelpt "
                             "oder entartet")
        g[q] = np.linalg.solve(J, np.broadcast_to(dNr.T, (n, 3, k))).transpose(0, 2, 1)
        det[q] = d
        if Ba is not None:
            dM = np.array([[-2.0 * r, 0.0, 0.0], [0.0, -2.0 * s_, 0.0], [0.0, 0.0, -2.0 * t]])
            gm = (detJ0 / d)[:, None, None] * np.linalg.solve(
                J0, np.broadcast_to(dM.T, (n, 3, 3))).transpose(0, 2, 1)
            Ba[q] = _b_stapel(gm)
    return g, det, Ba


def _elementknoten(model, typ, idx):
    k = _KNOTENZAHL[typ]
    kn = np.asarray([model.elements[int(i)].nodes[:k] for i in idx], dtype=np.int64)
    return kn.reshape(len(idx), k)


def _binde_mittelknoten(model, typ, kn, g):
    """Gebundene Mittelknoten (Uebergang an ein lineares Element, B5): ihr
    Gradient geht je zur Haelfte auf die beiden Ecken ihrer Kante, und sie
    selbst tragen nichts mehr - das ist u_m = (u_a + u_b)/2, exakt, in jeder
    Rechnung, die den Operator liest (Steifigkeit, Spannung, Plastizitaet).
    g (P,n,k,3) wird geaendert."""
    from .. import assemble as asm
    bind = {m: (a, b) for m, a, b in asm.mittelknoten_bindungen(model)}
    if not bind:
        return g
    for e_pos in range(kn.shape[0]):
        zeile = [int(x) for x in kn[e_pos]]
        for l, knoten in enumerate(zeile):
            ab = bind.get(knoten)
            if ab is None or ab[0] not in zeile or ab[1] not in zeile:
                continue
            la, lb = zeile.index(ab[0]), zeile.index(ab[1])
            g[:, e_pos, la, :] += 0.5 * g[:, e_pos, l, :]
            g[:, e_pos, lb, :] += 0.5 * g[:, e_pos, l, :]
            g[:, e_pos, l, :] = 0.0
    return g


def _mittelknoten_zusatz(model, idx, aktiv=None):
    """Zusatzschluessel des Zwischenspeichers: die Bindungen haengen an den
    Nachbarn (ein linearer Nachbar genuegt), nicht an den eigenen Knoten."""
    from .. import assemble as asm
    return hash(tuple(asm.mittelknoten_bindungen(model)))


def _operator_iso(model, typ, idx, aktiv=None) -> list:
    """Bauer der isoparametrischen Typen: die Gaussregel aus _ISO."""
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, typ, idx)
    _fn, GP, W = _ISO[typ]
    g, det, Ba = _iso_an_punkten(typ, np.asarray(model.nodes, float)[kn], GP, idx)
    if typ in _QUADRATISCH:
        g = _binde_mittelknoten(model, typ, kn, g)
    w = np.asarray(W, float)[:, None] * det
    return [Dehnungsoperator(typ, idx, kn, w, g=g, Ba=Ba, xi=np.asarray(GP, float))]


def _auswertung_iso(model, typ, idx, punkte) -> list:
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, typ, idx)
    g, det, Ba = _iso_an_punkten(typ, np.asarray(model.nodes, float)[kn], punkte, idx,
                                 pruefen=False)
    if typ in _QUADRATISCH:
        g = _binde_mittelknoten(model, typ, kn, g)
    return [Dehnungsoperator(typ, idx, kn, np.zeros_like(det), g=g, Ba=Ba,
                             xi=np.asarray(punkte, float))]


#: Typen mit Kantenmitten - die, deren Mittelknoten an ein lineares Element gebunden werden
_QUADRATISCH = ("tet10", "hex20", "pent15")


def hex8_regel_fuer(model):
    """Die Punktregel des hex8 in diesem Modell: mit Fliessen und
    ``plastizitaet.dicke_punkte`` >= 3 Gauss-Lobatto in t (A2, siehe
    plastizitaet.Plastizitaet), sonst None (2x2x2 Gauss). Eine Stelle, damit
    Steifigkeit, Spannung und Plastizitaet dieselbe Regel nehmen."""
    pz = getattr(model, "plastizitaet", None)
    if pz is None or not getattr(pz, "an", False):
        return None
    n = int(getattr(pz, "dicke_punkte", 2) or 2)
    if n < 3:
        return None
    return hex8_regel(min(n, max(_LOBATTO)), "lobatto")


def pent6_regel_fuer(model):
    """Wie hex8_regel_fuer: mit Fliessen Lobatto in t (die Sweep-Richtung)."""
    r = hex8_regel_fuer(model)
    if r is None:
        return None
    n = int(getattr(model.plastizitaet, "dicke_punkte", 2) or 2)
    return pent6_regel(min(n, max(_LOBATTO)), "lobatto")


def _operator_pent6(model, typ, idx, aktiv=None) -> list:
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, "pent6", idx)
    return [_pent6_operator(np.asarray(model.nodes, float)[kn], idx=idx, knoten=kn,
                            regel=pent6_regel_fuer(model))]


def _auswertung_pent6(model, typ, idx, punkte) -> list:
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, "pent6", idx)
    op = _pent6_operator(np.asarray(model.nodes, float)[kn], punkte=punkte, idx=idx, knoten=kn,
                         regel=pent6_regel_fuer(model))
    return [op]


def _operator_hex8(model, typ, idx, aktiv=None) -> list:
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, "hex8", idx)
    return [_hex8_operator(np.asarray(model.nodes, float)[kn], idx=idx, knoten=kn,
                           regel=hex8_regel_fuer(model))]


def _auswertung_hex8(model, typ, idx, punkte) -> list:
    idx = np.asarray(idx, dtype=np.int64)
    kn = _elementknoten(model, "hex8", idx)
    return [_hex8_operator(np.asarray(model.nodes, float)[kn], punkte=punkte, idx=idx, knoten=kn,
                           regel=hex8_regel_fuer(model))]


#: Bauer je Typ: f(model, typ, idx, aktiv) -> list[Dehnungsoperator]. Ein Typ
#: mit eigener Kinematik traegt sich hier ein (auch aus einer anderen Datei).
#: Die Auswertung (AUSWERTER) muss dieselbe Gruppierung liefern.
OPERATOREN: dict = {typ: _operator_iso for typ in _ISO}
OPERATOREN["hex8"] = _operator_hex8
OPERATOREN["pent6"] = _operator_pent6
#: Bauer der Auswertung an beliebigen Punkten: f(model, typ, idx, punkte) -> list
AUSWERTER: dict = {typ: _auswertung_iso for typ in _ISO}
AUSWERTER["hex8"] = _auswertung_hex8
AUSWERTER["pent6"] = _auswertung_pent6


#: Je Typ optional f(model, idx, aktiv) -> hashbar: was den Operator ausser
#: Elementen, Knoten, Koordinaten und Maske bestimmt (etwa die Zuordnung von
#: FHG ohne Knoten, die an Nachbarn oder Kontaktflaechen haengt). Geht in den
#: Schluessel des Zwischenspeichers.
ZUSATZSCHLUESSEL: dict = {}


def _fingerabdruck(model, typ, idx, aktiv) -> tuple:
    """Schluessel des Zwischenspeichers: Typ, Elemente, Maske und die
    Koordinaten der beteiligten Knoten. Bis zum 22.09.2026 hing der Speicher
    der Plastizitaet an (Typ, Zahl, erstes und letztes Element) - ein
    verschobener Knoten oder eine andere Elementfolge gleicher Laenge haette
    den alten Stapel still weiterbenutzt."""
    import itertools
    idx = np.ascontiguousarray(np.asarray(idx, dtype=np.int64))
    kn = np.fromiter(itertools.chain.from_iterable(model.elements[int(i)].nodes for i in idx),
                     dtype=np.int64)
    X = np.ascontiguousarray(np.asarray(model.nodes, float)[np.unique(kn)])
    m = None if aktiv is None else np.ascontiguousarray(np.asarray(aktiv, bool))
    zusatz = ZUSATZSCHLUESSEL.get(typ)
    return (typ, len(idx), hash(idx.tobytes()), hash(kn.tobytes()), hash(X.tobytes()),
            None if m is None else hash(m.tobytes()),
            None if zusatz is None else zusatz(model, idx, aktiv))


def dehnungsoperator(model, typ, idx, aktiv=None, merken=False) -> list:
    """Der Dehnungsoperator eines Elementtyps fuer die Elemente ``idx`` -
    eine Liste, je Gruppe gleicher Punkt- und Knotenzahl ein Eintrag.

    ``merken=True`` legt ihn am Modell ab (je Typ einer) und gibt ihn beim
    naechsten Aufruf mit demselben Fingerabdruck wieder her - die Plastizitaet
    fragt je Schritt, das Netz aendert sich dabei nicht."""
    bauer = OPERATOREN.get(typ)
    if bauer is None:
        raise ValueError(f"Fuer den Elementtyp '{typ}' gibt es keinen Dehnungsoperator")
    if not merken:
        return bauer(model, typ, idx, aktiv)
    schluessel = _fingerabdruck(model, typ, idx, aktiv)
    speicher = getattr(model, "_dehnungsoperatoren", None)
    if speicher is None:
        speicher = {}
        try:
            model._dehnungsoperatoren = speicher
        except AttributeError:          # Modell ohne freie Attribute: nicht merken
            return bauer(model, typ, idx, aktiv)
    alt = speicher.get(typ)
    if alt is not None and alt[0] == schluessel:
        return alt[1]
    ops = bauer(model, typ, idx, aktiv)
    speicher[typ] = (schluessel, ops)
    return ops


def auswerteoperator(model, typ, idx, punkte=None) -> list:
    """Dieselbe Kinematik an anderen Punkten (natuerliche Koordinaten (Q,3));
    ohne ``punkte`` an den AUSWERTEPUNKTEN des Typs. Die Gewichte sind hier
    ohne Bedeutung (null)."""
    bauer = AUSWERTER.get(typ)
    if bauer is None:
        raise ValueError(f"Fuer den Elementtyp '{typ}' gibt es keine Auswertung an Punkten")
    pts = AUSWERTEPUNKTE[typ] if punkte is None else punkte
    return bauer(model, typ, idx, np.asarray(pts, float).reshape(-1, 3))


def D_stapel(E, nu, n) -> np.ndarray:
    """Werkstoffmatrix je Element (n,6,6) aus Skalaren oder Feldern (n,) -
    dieselben Zahlen wie :func:`D_matrix`."""
    E = np.broadcast_to(np.asarray(E, float), (n,))
    nu = np.broadcast_to(np.asarray(nu, float), (n,))
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    D = np.zeros((n, 6, 6))
    D[:, :3, :3] = lam[:, None, None]
    for a in range(3):
        D[:, a, a] = lam + 2 * mu
        D[:, 3 + a, 3 + a] = mu
    return D


def matrizen_aus_operator(op: Dehnungsoperator, D, ohne_kuu=False) -> tuple:
    """(Kuu, Kua, Kaa) eines Operators; D ist (6,6) oder (n,6,6).
    Kua/Kaa sind None ohne innere Moden, Kuu None bei ``ohne_kuu``."""
    D = np.asarray(D, float)
    n, nz, na = op.n, 3 * op.k, op.na
    Kuu = None if ohne_kuu else np.zeros((n, nz, nz))
    Kua = np.zeros((n, nz, na)) if na else None
    Kaa = np.zeros((n, na, na)) if na else None
    for p in range(op.P):
        B = op.b(p)
        wd = op.w[p][:, None, None]
        # matmul statt einsum: die Stapel-Matrixmultiplikation geht ueber
        # BLAS (gemessen 21.09.2026: 258,8 -> 85,4 µs je hex8; am 23.09.2026
        # kostet k_hex8_stapel samt Operator 58,3 µs, der tet10-Stapel 21,3)
        Bt = B.transpose(0, 2, 1)
        if not ohne_kuu:
            Kuu += wd * (Bt @ (D @ B))
        if na:
            DBa = D @ op.Ba[p]
            Kua += wd * (Bt @ DBa)
            Kaa += wd * (op.Ba[p].transpose(0, 2, 1) @ DBa)
    return Kuu, Kua, Kaa


def steifigkeit_aus_operator(op: Dehnungsoperator, D) -> np.ndarray:
    """Elementsteifigkeiten (n,3k,3k), die inneren Moden kondensiert."""
    Kuu, Kua, Kaa = matrizen_aus_operator(op, D)
    if Kua is None:
        return Kuu
    return Kuu - Kua @ np.linalg.solve(Kaa, Kua.transpose(0, 2, 1))


def moden_aus_operator(op: Dehnungsoperator, D, ue) -> np.ndarray:
    """Innere Freiheitsgrade alpha (n,na) = -Kaa^-1 Kua^T u (elastisch)."""
    _Kuu, Kua, Kaa = matrizen_aus_operator(op, D, ohne_kuu=True)
    ue = np.asarray(ue, float).reshape(op.n, 3 * op.k)
    rechts = -np.einsum("nji,nj->ni", Kua, ue)
    return np.linalg.solve(Kaa, rechts[..., None])[..., 0]


def spannungen_stapel(model, typ, idx, E, nu, U, punkte=None) -> tuple:
    """Elastische Spannungen eines Stapels gleichen Typs und Werkstoffs.

    U (n,3k) sind die Elementverschiebungen in der Knotenfolge des Operators.
    Rueckgabe (S, M): S (n,Q,6) an den Auswertepunkten (ohne ``punkte`` die
    AUSWERTEPUNKTE des Typs), M (n,6) das Gewichtsmittel ueber die
    Integrationspunkte - das Elementmittel Integral sigma dV / V, das der
    Fehlerschaetzer liest (netzfehler.MITTELFELD). Beide aus **einem**
    Operator: dieselben inneren Moden, dieselbe Kinematik wie die Steifigkeit.
    """
    idx = list(idx)
    D = D_matrix(E, nu)
    U = np.asarray(U, float).reshape(len(idx), -1)
    S_alle, M_alle = [], []
    pos = 0
    ausw = auswerteoperator(model, typ, idx, punkte)
    for op, aw in zip(dehnungsoperator(model, typ, idx), ausw):
        Ue = U[pos:pos + op.n]
        pos += op.n
        alpha = moden_aus_operator(op, D, Ue) if op.Ba is not None else None
        S = np.empty((op.n, aw.P, 6))
        for q in range(aw.P):
            S[:, q, :] = dehnung_mit_moden(aw, q, Ue, alpha) @ D.T
        M = np.zeros((op.n, 6))
        for p in range(op.P):
            M += op.w[p][:, None] * (dehnung_mit_moden(op, p, Ue, alpha) @ D.T)
        M /= op.w.sum(axis=0)[:, None]
        S_alle.append(S)
        M_alle.append(M)
    return np.concatenate(S_alle), np.concatenate(M_alle)


def dehnung_mit_moden(op: Dehnungsoperator, p: int, ue, alpha=None) -> np.ndarray:
    """Voigt-Dehnung (n,6) am Punkt p, mit den inneren Moden, wenn es welche gibt."""
    eps = op.dehnung(p, ue)
    if op.Ba is not None and alpha is not None:
        eps = eps + (op.Ba[p] @ np.asarray(alpha, float)[:, :, None])[:, :, 0]
    return eps


for _t in _QUADRATISCH:
    ZUSATZSCHLUESSEL[_t] = _mittelknoten_zusatz


# --------------------------------------------------------------------------
# Tetraeder mit Ordnung p (elements/tetp.py, zweite Element-Sitzung)
# --------------------------------------------------------------------------
# Vier Eckknoten, Seiten wie der tet4 (Kontakt, Fugen, Lasten sehen nur
# Ecken); Auswertung an Mitte und Ecken wie der tet10. Steifigkeit,
# Spannung und Plastizitaet lesen den Operator aus elements/tetp.py - der
# kennt die Zusatz-FHG hinter den Knoten-FHG (Dehnungsoperator.fhg).
def _tetp_registrieren():
    """Idempotent und von beiden Seiten aufrufbar: solid ruft es am Ende
    seines Imports, tetp am Ende des seinen. Ist tetp noch nicht fertig
    geladen, holt tetp die Anmeldung selbst nach."""
    try:
        from . import tetp as _tp
        typen = _tp.TYPEN
        operatoren, auswerter, zusatz = _tp.operatoren, _tp.auswerter, _tp.zusatzschluessel
        punkte = _tp.AUSWERTEPUNKTE
    except (ImportError, AttributeError):
        return
    for _t in typen:
        FLAECHEN[_t] = list(FLAECHEN["tet4"])
        FLAECHEN_ECKEN[_t] = list(FLAECHEN_ECKEN["tet4"])
        AUSWERTEPUNKTE[_t] = list(punkte)
        ECKEN_NATUERLICH[_t] = list(ECKEN_NATUERLICH["tet4"])
        _KNOTENZAHL[_t] = 4
        OPERATOREN[_t] = operatoren
        AUSWERTER[_t] = auswerter
        ZUSATZSCHLUESSEL[_t] = zusatz


_tetp_registrieren()
