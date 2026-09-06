"""
Ebene Kontinuumselemente (Scheiben): tri3, quad4, tri6, quad8.

Zustaende (``zustand``):
  "spannung"  ebener Spannungszustand, Dicke t
  "dehnung"   ebener Dehnungszustand, t = Tiefe der Scheibe (Vorgabe 1.0)
  "rotation"  rotationssymmetrisch: die Elementebene ist die globale
              x-z-Ebene, r = x >= 0, Drehachse = globale z-Achse,
              Integration ueber 2*pi*r; die Dicke t wird ignoriert

Typen und Knotenreihenfolge (gegen den Uhrzeigersinn):
  "ebene3"  tri3   Ecken 0, 1, 2
  "ebene4"  quad4  Ecken 0..3
  "ebene6"  tri6   Ecken 0, 1, 2; 3 = Mitte 0-1, 4 = Mitte 1-2, 5 = Mitte 2-0
  "ebene8"  quad8  Ecken 0..3; 4..7 = Mitten der Kanten 0-1, 1-2, 2-3, 3-0

Freiheitsgrade: je Knoten die drei globalen Verschiebungen (ux, uy, uz).
Die Steifigkeit wirkt nur in der Elementebene; die Zeilen und Spalten der
Richtung senkrecht zur Ebene bleiben 0 (der Loeser sperrt steifigkeitslose
FHG selbst).

Dehnungsreihenfolge lokal: [exx, eyy, gxy] bzw. bei rotation
[err, ezz, grz, ett].  Spannungsausgabe in Voigt-Anordnung (lokal):
[sx, sy, sz, txy, 0, 0] mit sz = 0 (spannung) bzw. sz = nu*(sx+sy)
(dehnung); bei rotation [s_r, s_z, s_theta, t_rz, 0, 0].

Integration:
  tri3   3-Punkt-Regel (Grad 2; bei spannung/dehnung identisch mit CST,
         bei rotation fuer den Rang noetig)
  quad4  2x2 Gauss; bei spannung/dehnung mit inkompatiblen Moden
         (Wilson/Taylor, statisch kondensiert), bei rotation ohne
  tri6   6-Punkt-Regel (Grad 4)
  quad8  3x3 Gauss
"""
from __future__ import annotations

import numpy as np

ZUSTAENDE = ("spannung", "dehnung", "rotation")

_KNOTEN = {"ebene3": 3, "ebene4": 4, "ebene6": 6, "ebene8": 8}
_ECKEN = {"ebene3": 3, "ebene4": 4, "ebene6": 3, "ebene8": 4}
_QUADRATISCH = ("ebene6", "ebene8")

#: Kanten je Typ: (Anfangsecke, Endecke[, Mittelknoten]) in Umlaufrichtung
_KANTEN = {
    "ebene3": [(0, 1), (1, 2), (2, 0)],
    "ebene4": [(0, 1), (1, 2), (2, 3), (3, 0)],
    "ebene6": [(0, 1, 3), (1, 2, 4), (2, 0, 5)],
    "ebene8": [(0, 1, 4), (1, 2, 5), (2, 3, 6), (3, 0, 7)],
}

#: Elementmitte in natuerlichen Koordinaten
_MITTE = {"ebene3": (1 / 3, 1 / 3), "ebene4": (0.0, 0.0),
          "ebene6": (1 / 3, 1 / 3), "ebene8": (0.0, 0.0)}

#: Auswertepunkte je Elementtyp: Mitte zuerst, dann die Ecken
AUSWERTEPUNKTE_EBENE = {
    "ebene3": [(1 / 3, 1 / 3), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
    "ebene4": [(0.0, 0.0), (-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
    "ebene6": [(1 / 3, 1 / 3), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0)],
    "ebene8": [(0.0, 0.0), (-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)],
}


# --------------------------------------------------------------------------
# Typ, Zustand, Formfunktionen, Integrationsregeln
# --------------------------------------------------------------------------
def _pruefe_typ(typ: str) -> None:
    if typ not in _KNOTEN:
        raise ValueError(f"unbekannter Scheibentyp {typ!r}")


def _pruefe_zustand(zustand: str) -> None:
    if zustand not in ZUSTAENDE:
        raise ValueError(f"unbekannter Zustand {zustand!r} "
                         f"(erlaubt: {', '.join(ZUSTAENDE)})")


def knotenzahl_ebene(typ: str) -> int:
    _pruefe_typ(typ)
    return _KNOTEN[typ]


_Q4_VORZ = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], dtype=float)
_Q8_NAT = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1],
                    [0, -1], [1, 0], [0, 1], [-1, 0]], dtype=float)
_TRI_dL = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]])


def N_dN_ebene(typ: str, xi: float, eta: float):
    """Formfunktionen N (n,) und Ableitungen dN (n,2) nach (xi, eta).

    Dreiecke: Flaechenkoordinaten L1 = 1-xi-eta, L2 = xi, L3 = eta.
    Vierecke: xi, eta in [-1, 1]."""
    _pruefe_typ(typ)
    if typ == "ebene3":
        N = np.array([1.0 - xi - eta, xi, eta])
        return N, _TRI_dL.copy()
    if typ == "ebene6":
        L = np.array([1.0 - xi - eta, xi, eta])
        N = np.empty(6)
        dN = np.empty((6, 2))
        for i in range(3):
            N[i] = L[i] * (2.0 * L[i] - 1.0)
            dN[i] = (4.0 * L[i] - 1.0) * _TRI_dL[i]
        for k, (a, b) in enumerate(((0, 1), (1, 2), (2, 0))):
            N[3 + k] = 4.0 * L[a] * L[b]
            dN[3 + k] = 4.0 * (L[a] * _TRI_dL[b] + L[b] * _TRI_dL[a])
        return N, dN
    if typ == "ebene4":
        sg = _Q4_VORZ
        N = 0.25 * (1.0 + sg[:, 0] * xi) * (1.0 + sg[:, 1] * eta)
        dN = np.column_stack([0.25 * sg[:, 0] * (1.0 + sg[:, 1] * eta),
                              0.25 * (1.0 + sg[:, 0] * xi) * sg[:, 1]])
        return N, dN
    # quad8 (Serendipity)
    N = np.empty(8)
    dN = np.empty((8, 2))
    for i in range(4):
        a, b = _Q8_NAT[i]
        N[i] = 0.25 * (1.0 + a * xi) * (1.0 + b * eta) * (a * xi + b * eta - 1.0)
        dN[i, 0] = 0.25 * a * (1.0 + b * eta) * (2.0 * a * xi + b * eta)
        dN[i, 1] = 0.25 * b * (1.0 + a * xi) * (a * xi + 2.0 * b * eta)
    for i in (4, 6):
        b = _Q8_NAT[i, 1]
        N[i] = 0.5 * (1.0 - xi * xi) * (1.0 + b * eta)
        dN[i, 0] = -xi * (1.0 + b * eta)
        dN[i, 1] = 0.5 * b * (1.0 - xi * xi)
    for i in (5, 7):
        a = _Q8_NAT[i, 0]
        N[i] = 0.5 * (1.0 + a * xi) * (1.0 - eta * eta)
        dN[i, 0] = 0.5 * a * (1.0 - eta * eta)
        dN[i, 1] = -eta * (1.0 + a * xi)
    return N, dN


# Dreieck, 3 Punkte (Grad 2), Gewichte auf Referenzflaeche 1/2
_TRI3_GP = np.array([[1 / 6, 1 / 6], [2 / 3, 1 / 6], [1 / 6, 2 / 3]])
_TRI3_W = np.full(3, 1 / 6)

# Dreieck, 6 Punkte (Grad 4, Dunavant)
_DA, _DB = 0.445948490915965, 0.091576213509771
_TRI6_GP = np.array([[_DA, _DA], [1 - 2 * _DA, _DA], [_DA, 1 - 2 * _DA],
                     [_DB, _DB], [1 - 2 * _DB, _DB], [_DB, 1 - 2 * _DB]])
_TRI6_W = 0.5 * np.array([0.223381589678011] * 3 + [0.109951743655322] * 3)

# Viereck 2x2 und 3x3
_G2 = 1.0 / np.sqrt(3.0)
_Q4_GP = np.array([[a, b] for a in (-_G2, _G2) for b in (-_G2, _G2)])
_Q4_W = np.ones(4)
_G3 = np.sqrt(0.6)
_P3 = (-_G3, 0.0, _G3)
_W3 = (5 / 9, 8 / 9, 5 / 9)
_Q8_GP = np.array([[a, b] for a in _P3 for b in _P3])
_Q8_W = np.array([wa * wb for wa in _W3 for wb in _W3])

# Linie (Kantenlasten), 3 Punkte
_L_GP = np.array(_P3)
_L_W = np.array(_W3)


def gauss_ebene(typ: str):
    """Integrationsregel: Punkte GP (m,2) in natuerlichen Koordinaten und
    Gewichte W (m,).  Die Gewichte enthalten bereits die Referenzflaeche
    (Dreieck 1/2, Viereck 4)."""
    _pruefe_typ(typ)
    if typ == "ebene3":
        return _TRI3_GP.copy(), _TRI3_W.copy()
    if typ == "ebene6":
        return _TRI6_GP.copy(), _TRI6_W.copy()
    if typ == "ebene4":
        return _Q4_GP.copy(), _Q4_W.copy()
    return _Q8_GP.copy(), _Q8_W.copy()


# --------------------------------------------------------------------------
# Lokales System
# --------------------------------------------------------------------------
_T3_ROTATION = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])


def ebene_frame(P, zustand: str):
    """Lokales Elementsystem.

    Rueckgabe: T3 (3,3) mit den Zeilen ex, ey, ez und die lokalen
    Knotenkoordinaten xy (n,2).

    spannung/dehnung: Ausgleichsebene der Knoten; ex entlang der Kante 0-1
    (in die Ebene projiziert), ez die Normale (Orientierung nach dem
    Umlaufsinn der Ecken), Ursprung im Knoten 0.
    rotation: T3 = [[1,0,0],[0,0,1],[0,1,0]] (lokal x = global x = r,
    lokal y = global z = axial), xy = (x, z).  Fehler, wenn ein Knoten
    y != 0 hat oder x < 0 liegt (Toleranz 1e-9 mal Elementgroesse)."""
    _pruefe_zustand(zustand)
    P = np.asarray(P, float)
    if P.ndim != 2 or P.shape[1] != 3:
        raise ValueError("P muss die Form (n,3) haben")
    n = P.shape[0]
    groesse = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if groesse <= 0.0:
        raise ValueError("entartetes Scheibenelement (alle Knoten gleich)")

    if zustand == "rotation":
        tol = 1e-9 * groesse
        if np.max(np.abs(P[:, 1])) > tol:
            raise ValueError("rotationssymmetrisches Element: alle Knoten "
                             "muessen in der x-z-Ebene liegen (y = 0)")
        if np.min(P[:, 0]) < -tol:
            raise ValueError("rotationssymmetrisches Element: r = x muss "
                             ">= 0 sein")
        xy = np.column_stack([np.maximum(P[:, 0], 0.0), P[:, 2]])
        return _T3_ROTATION.copy(), xy

    ne = {3: 3, 4: 4, 6: 3, 8: 4}.get(n)
    if ne is None:
        raise ValueError(f"Scheibenelement mit {n} Knoten nicht bekannt")
    # Orientierung: Newell-Normale der Ecken (Umlaufsinn)
    ecken = P[:ne]
    nrm = np.zeros(3)
    for i in range(ne):
        nrm += np.cross(ecken[i], ecken[(i + 1) % ne])
    # Ausgleichsebene: Richtung des kleinsten Singulaerwerts
    Q = P - P.mean(axis=0)
    _, S, Vt = np.linalg.svd(Q, full_matrices=False)
    if S[1] <= 1e-12 * S[0] or np.linalg.norm(nrm) <= 1e-24 * groesse ** 2:
        raise ValueError("entartetes Scheibenelement (Flaeche 0)")
    ez = Vt[2]
    if ez @ nrm < 0.0:
        ez = -ez
    ex = P[1] - P[0]
    ex = ex - (ex @ ez) * ez
    lx = np.linalg.norm(ex)
    if lx <= 1e-12 * groesse:
        raise ValueError("entartetes Scheibenelement (Kante 0-1 hat Laenge 0)")
    ex = ex / lx
    ey = np.cross(ez, ex)
    T3 = np.vstack([ex, ey, ez])
    R = P - P[0]
    xy = np.column_stack([R @ ex, R @ ey])
    return T3, xy


def _Tm(T3: np.ndarray, n: int) -> np.ndarray:
    """Abbildung globale Verschiebungen (3n) -> lokale Ebenenverschiebungen
    (2n): u_lokal = Tm @ u_global."""
    Tm = np.zeros((2 * n, 3 * n))
    for i in range(n):
        Tm[2 * i, 3 * i:3 * i + 3] = T3[0]
        Tm[2 * i + 1, 3 * i:3 * i + 3] = T3[1]
    return Tm


# --------------------------------------------------------------------------
# Werkstoff
# --------------------------------------------------------------------------
def D_ebene(E: float, nu: float, zustand: str) -> np.ndarray:
    """Werkstoffmatrix: (3,3) fuer spannung/dehnung ([exx, eyy, gxy]),
    (4,4) fuer rotation ([err, ezz, grz, ett])."""
    _pruefe_zustand(zustand)
    if zustand == "spannung":
        f = E / (1.0 - nu ** 2)
        return f * np.array([[1.0, nu, 0.0],
                             [nu, 1.0, 0.0],
                             [0.0, 0.0, 0.5 * (1.0 - nu)]])
    f = E / ((1.0 + nu) * (1.0 - 2.0 * nu))
    if zustand == "dehnung":
        return f * np.array([[1.0 - nu, nu, 0.0],
                             [nu, 1.0 - nu, 0.0],
                             [0.0, 0.0, 0.5 * (1.0 - 2.0 * nu)]])
    return f * np.array([[1.0 - nu, nu, 0.0, nu],
                         [nu, 1.0 - nu, 0.0, nu],
                         [0.0, 0.0, 0.5 * (1.0 - 2.0 * nu), 0.0],
                         [nu, nu, 0.0, 1.0 - nu]])


def _eps_thermisch(nu: float, alpha: float, dT: float, zustand: str) -> np.ndarray:
    """Waermedehnung in der Reihenfolge der Werkstoffmatrix.  Beim ebenen
    Dehnungszustand ist die behinderte Dehnung in z enthalten: (1+nu)."""
    if zustand == "spannung":
        return alpha * dT * np.array([1.0, 1.0, 0.0])
    if zustand == "dehnung":
        return alpha * dT * (1.0 + nu) * np.array([1.0, 1.0, 0.0])
    return alpha * dT * np.array([1.0, 1.0, 0.0, 1.0])


def _voigt(s: np.ndarray, nu: float, zustand: str) -> np.ndarray:
    """Lokale Spannungen in Voigt-Anordnung (6,)."""
    out = np.zeros(6)
    if zustand == "rotation":
        out[0], out[1], out[2], out[3] = s[0], s[1], s[3], s[2]
        return out
    out[0], out[1], out[3] = s[0], s[1], s[2]
    if zustand == "dehnung":
        out[2] = nu * (s[0] + s[1])
    return out


# --------------------------------------------------------------------------
# Kinematik
# --------------------------------------------------------------------------
def _B_eben(dN: np.ndarray) -> np.ndarray:
    """dN: (n,2) Ableitungen nach x,y -> B (3, 2n) fuer [exx, eyy, gxy]."""
    n = dN.shape[0]
    B = np.zeros((3, 2 * n))
    B[0, 0::2] = dN[:, 0]
    B[1, 1::2] = dN[:, 1]
    B[2, 0::2] = dN[:, 1]
    B[2, 1::2] = dN[:, 0]
    return B


def _B_rot(N: np.ndarray, dN: np.ndarray, r: float, r_tol: float) -> np.ndarray:
    """B (4, 2n) fuer [err, ezz, grz, ett]; auf der Drehachse (r -> 0) wird
    die Umfangsdehnung durch die Radialdehnung ersetzt (Grenzwert)."""
    n = dN.shape[0]
    B = np.zeros((4, 2 * n))
    B[0, 0::2] = dN[:, 0]
    B[1, 1::2] = dN[:, 1]
    B[2, 0::2] = dN[:, 1]
    B[2, 1::2] = dN[:, 0]
    if r > r_tol:
        B[3, 0::2] = N / r
    else:
        B[3, 0::2] = dN[:, 0]
    return B


class _Element:
    """Hilfsobjekt: lokales System und Auswertung an einem Punkt."""

    def __init__(self, typ, P, zustand, t=1.0):
        _pruefe_typ(typ)
        _pruefe_zustand(zustand)
        self.typ = typ
        self.zustand = zustand
        self.rot = zustand == "rotation"
        self.n = _KNOTEN[typ]
        P = np.asarray(P, float)
        if P.shape != (self.n, 3):
            raise ValueError(f"{typ}: erwarte Knoten (n,3) mit n = {self.n}, "
                             f"erhalten {P.shape}")
        self.T3, self.xy = ebene_frame(P, zustand)
        self.Tm = _Tm(self.T3, self.n)
        self.t = 1.0 if self.rot else float(t)
        self.r_tol = 1e-12 * float(np.linalg.norm(self.xy.max(axis=0)
                                                  - self.xy.min(axis=0)))
        self.inkompatibel = (typ == "ebene4" and not self.rot)
        if self.inkompatibel:
            _, dN0 = N_dN_ebene(typ, 0.0, 0.0)
            self.J0 = dN0.T @ self.xy
            self.detJ0 = float(np.linalg.det(self.J0))

    def punkt(self, xi, eta):
        """Rueckgabe (N, dN_xy, detJ, r, B).  r = 0 bei spannung/dehnung."""
        N, dNn = N_dN_ebene(self.typ, xi, eta)
        J = dNn.T @ self.xy
        detJ = float(np.linalg.det(J))
        if detJ <= 0.0:
            raise ValueError(f"{self.typ} mit nicht positiver "
                             f"Jacobi-Determinante (Knotenreihenfolge?)")
        dN = np.linalg.solve(J, dNn.T).T
        if self.rot:
            r = float(N @ self.xy[:, 0])
            B = _B_rot(N, dN, r, self.r_tol)
        else:
            r = 0.0
            B = _B_eben(dN)
        return N, dN, detJ, r, B

    def dV(self, w, detJ, r):
        """Volumenanteil eines Integrationspunkts."""
        if self.rot:
            return w * detJ * 2.0 * np.pi * r
        return w * detJ * self.t

    def Ba(self, xi, eta, detJ):
        """B-Matrix (3,4) der inkompatiblen Moden (1-xi^2, 1-eta^2) mit
        Taylor-Korrektur, damit der Patch-Test erfuellt bleibt."""
        dM = np.array([[-2.0 * xi, 0.0], [0.0, -2.0 * eta]])
        g = (self.detJ0 / detJ) * np.linalg.solve(self.J0, dM.T).T
        return _B_eben(g)


def _matrizen_lokal(el: _Element, D: np.ndarray):
    """Lokale Matrizen (Kuu (2n,2n), Kua (2n,4), Kaa (4,4)); ohne
    inkompatible Moden sind Kua/Kaa None."""
    n = el.n
    Kuu = np.zeros((2 * n, 2 * n))
    Kua = np.zeros((2 * n, 4)) if el.inkompatibel else None
    Kaa = np.zeros((4, 4)) if el.inkompatibel else None
    GP, W = gauss_ebene(el.typ)
    for (xi, eta), w in zip(GP, W):
        _, _, detJ, r, B = el.punkt(xi, eta)
        dV = el.dV(w, detJ, r)
        Kuu += dV * (B.T @ D @ B)
        if el.inkompatibel:
            Ba = el.Ba(xi, eta, detJ)
            Kua += dV * (B.T @ D @ Ba)
            Kaa += dV * (Ba.T @ D @ Ba)
    return Kuu, Kua, Kaa


# --------------------------------------------------------------------------
# Steifigkeit, Spannungen
# --------------------------------------------------------------------------
def k_ebene(typ: str, P, E: float, nu: float, t: float, zustand: str) -> np.ndarray:
    """Globale Steifigkeitsmatrix (3n,3n); FHG je Knoten ux, uy, uz."""
    el = _Element(typ, P, zustand, t)
    D = D_ebene(E, nu, zustand)
    Kuu, Kua, Kaa = _matrizen_lokal(el, D)
    if Kua is not None:
        Kuu = Kuu - Kua @ np.linalg.solve(Kaa, Kua.T)
    return el.Tm.T @ Kuu @ el.Tm


def stress_points_ebene(typ: str, P, E: float, nu: float, t: float,
                        zustand: str, ue, punkte=None) -> list:
    """Spannungen an mehreren Punkten (Vorgabe: Mitte, dann die Ecken).

    ue: globale Elementverschiebungen (3n,).  Rueckgabe: Liste von
    Spannungsvektoren (6,) in Voigt-Anordnung im lokalen System,
    [sx, sy, sz, txy, 0, 0] bzw. rotation [s_r, s_z, s_theta, t_rz, 0, 0].
    Beim quad4 (spannung/dehnung) werden die inkompatiblen Moden mit
    ausgewertet."""
    el = _Element(typ, P, zustand, t)
    D = D_ebene(E, nu, zustand)
    ue = np.asarray(ue, float).reshape(3 * el.n)
    ul = el.Tm @ ue
    pts = punkte if punkte is not None else AUSWERTEPUNKTE_EBENE[typ]
    alpha = None
    if el.inkompatibel:
        _, Kua, Kaa = _matrizen_lokal(el, D)
        alpha = -np.linalg.solve(Kaa, Kua.T @ ul)
    out = []
    for xi, eta in pts:
        _, _, detJ, _, B = el.punkt(xi, eta)
        eps = B @ ul
        if alpha is not None:
            eps = eps + el.Ba(xi, eta, detJ) @ alpha
        out.append(_voigt(D @ eps, nu, zustand))
    return out


def stress_ebene(typ: str, P, E: float, nu: float, t: float, zustand: str,
                 ue) -> np.ndarray:
    """Spannungen in der Elementmitte (6,), Voigt-Anordnung lokal."""
    return stress_points_ebene(typ, P, E, nu, t, zustand, ue,
                               punkte=[_MITTE[typ]])[0]


# --------------------------------------------------------------------------
# Flaeche, Masse, Lasten
# --------------------------------------------------------------------------
def _integrale(el: _Element):
    """Rueckgabe (V, int N_i dV, int N_i^2 dV) mit t bzw. 2*pi*r."""
    GP, W = gauss_ebene(el.typ)
    V = 0.0
    s1 = np.zeros(el.n)
    s2 = np.zeros(el.n)
    for (xi, eta), w in zip(GP, W):
        N, _, detJ, r, _ = el.punkt(xi, eta)
        dV = el.dV(w, detJ, r)
        V += dV
        s1 += dV * N
        s2 += dV * N * N
    return V, s1, s2


def flaeche_ebene(typ: str, P, zustand: str) -> float:
    """Flaeche des Elements; bei rotation das Volumen 2*pi * int r dA."""
    el = _Element(typ, P, zustand, 1.0)
    return _integrale(el)[0]


def masse_ebene(typ: str, P, rho: float, t: float, zustand: str) -> np.ndarray:
    """Diagonale (lumped) Massenmatrix (3n,), je Knoten fuer ux, uy, uz.

    Lineare Typen: Zeilensummen; quadratische Typen: HRZ-Lumping (alle
    Eintraege > 0).  Summe je Richtung = rho * V mit V = t*A bzw. bei
    rotation 2*pi * int r dA."""
    el = _Element(typ, P, zustand, t)
    V, s1, s2 = _integrale(el)
    if typ in _QUADRATISCH:
        m = rho * V * s2 / s2.sum()
    else:
        m = rho * s1
    return np.repeat(m, 3)


def _kante_N(m: int, s: float):
    """Formfunktionen einer Kante mit m Knoten (Anfang, Ende[, Mitte])
    ueber s in [-1, 1] und deren Ableitungen."""
    if m == 2:
        return (np.array([0.5 * (1.0 - s), 0.5 * (1.0 + s)]),
                np.array([-0.5, 0.5]))
    return (np.array([0.5 * s * (s - 1.0), 0.5 * s * (s + 1.0), 1.0 - s * s]),
            np.array([s - 0.5, s + 0.5, -2.0 * s]))


def kantenlast_ebene(typ: str, P, kante: int, p: float, zustand: str,
                     richtung=None) -> np.ndarray:
    """Konsistente Knotenlasten (3n,) einer gleichmaessigen Linienlast p.

    spannung/dehnung: p [N/m] je Laenge der Kante (die Dicke ist bereits
    enthalten); rotation: p [N/m^2] auf der Rotationsflaeche der Kante
    (Integration ueber 2*pi*r).  kante = Index der Kante (0: Knoten 0-1,
    1: 1-2, ...).  Ohne richtung wirkt p als Druck senkrecht zur Kante nach
    innen, mit richtung (Einheitsvektor, global) in diese Richtung."""
    el = _Element(typ, P, zustand, 1.0)
    kanten = _KANTEN[typ]
    if not 0 <= kante < len(kanten):
        raise ValueError(f"{typ}: Kante {kante} gibt es nicht "
                         f"(0..{len(kanten) - 1})")
    kn = kanten[kante]
    xk = el.xy[list(kn)]
    f2 = np.zeros(2 * el.n)
    fs = np.zeros(el.n)
    for s, w in zip(_L_GP, _L_W):
        Ns, dNs = _kante_N(len(kn), s)
        tang = dNs @ xk
        ds = float(np.linalg.norm(tang))
        faktor = w * ds * p
        if el.rot:
            faktor *= 2.0 * np.pi * float(Ns @ xk[:, 0])
        if richtung is None:
            n_innen = np.array([-tang[1], tang[0]]) / ds
            for a, i in enumerate(kn):
                f2[2 * i:2 * i + 2] += faktor * Ns[a] * n_innen
        else:
            for a, i in enumerate(kn):
                fs[i] += faktor * Ns[a]
    if richtung is None:
        return el.Tm.T @ f2
    d = np.asarray(richtung, float).reshape(3)
    ld = np.linalg.norm(d)
    if ld <= 0.0:
        raise ValueError("richtung darf nicht der Nullvektor sein")
    d = d / ld
    f = np.zeros(3 * el.n)
    for i in range(el.n):
        f[3 * i:3 * i + 3] = fs[i] * d
    return f


def temperatur_ebene(typ: str, P, E: float, nu: float, t: float,
                     alpha: float, dT: float, zustand: str) -> np.ndarray:
    """Aequivalente Knotenlasten (3n,) einer gleichmaessigen Erwaermung dT:
    f = int B^T D eps_T dV.  Die inkompatiblen Moden liefern wegen der
    Taylor-Korrektur keinen Beitrag."""
    el = _Element(typ, P, zustand, t)
    D = D_ebene(E, nu, zustand)
    sT = D @ _eps_thermisch(nu, alpha, dT, zustand)
    GP, W = gauss_ebene(typ)
    f2 = np.zeros(2 * el.n)
    for (xi, eta), w in zip(GP, W):
        _, _, detJ, r, B = el.punkt(xi, eta)
        f2 += el.dV(w, detJ, r) * (B.T @ sT)
    return el.Tm.T @ f2
