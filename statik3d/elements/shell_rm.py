"""
Reissner-Mindlin-Schalenelemente (schubweich) auf ebenen Facetten.

Elementtypen (Knotenreihenfolge jeweils gegen den Uhrzeigersinn):
  shell3  Dreieck 0,1,2                        Membran CST, Platte MITC3
  shell4  Viereck 0..3                         Membran bilinear mit inkompatiblen
                                               Moden, Platte MITC4
  shell6  Dreieck 0,1,2 Ecken; 3,4,5 Mitten    quadratisch, Verdrehungen mit
          der Kanten 0-1, 1-2, 2-0             Bubble, Querschub 3-Punkt (selektiv)
  shell8  Viereck 0..3 Ecken; 4..7 Mitten      Serendipity, Verdrehungen Lagrange
          der Kanten 0-1, 1-2, 2-3, 3-0        (Heterosis), Querschub 2x2 (selektiv)

Die Verdrehungsfelder von shell6 und shell8 werden hierarchisch um eine
Bubble-Funktion erweitert (2 innere Verdrehungs-FHG, statisch kondensiert).
Das beseitigt das Rest-Locking der selektiv reduziert integrierten Elemente
auf groben Netzen weitgehend; die Knoten-FHG bleiben unveraendert (6n x 6n).
MITC3 ist lockingfrei, auf groben Netzen aber (wie das CST bei Scheiben)
merklich zu steif; die Konvergenz ist quadratisch.

Pro Knoten 6 FHG (ux uy uz rx ry rz, global). Der Drill-FHG (Drehung um die
Flaechennormale) erhaelt eine kleine kuenstliche Steifigkeit (DRILL_FACTOR aus
shell.py), die an die Scheibendrehung 0.5*(v,x - u,y) gekoppelt ist, so dass
genau die sechs Starrkoerpermoden energiefrei bleiben.

Lokales System: Ausgleichsebene durch den Schwerpunkt der Eckknoten, Normale
aus dem Kreuzprodukt der Diagonalen (Viereck) bzw. der Kanten (Dreieck),
lokale x-Achse entlang der Kante 0-1 (auf die Ebene projiziert). Die Knoten
werden auf die Ebene projiziert, die Verwoelbung wird gemessen.

Kinematik (lokal): u = u0 + z*ry, v = v0 - z*rx, w = w0
  Membrandehnung  eps   = [u,x    v,y    u,y + v,x]
  Kruemmung       kappa = [ry,x   -rx,y  ry,y - rx,x]
  Querschub       gamma = [w,x + ry   w,y - rx]
Schnittgroessen: n = A eps + B kappa, m = B eps + D kappa, q = Ds gamma mit
A, B, D, Ds aus der klassischen Laminattheorie (isotrop als Sonderfall).
Vorzeichen wie in shell.py: sig_oben = n/t + 6 m/t^2 (isotrop).

Literatur: Dvorkin/Bathe (1984) MITC4; Lee/Bathe (2004) MITC3;
Hughes/Cohen (1978) Heterosis-Element;
Taylor/Beresford/Wilson (1976) inkompatible Moden; Hughes (1987) selektiv
reduzierte Integration; Reddy (2004) Laminattheorie.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .shell import DRILL_FACTOR, T_shell

SCHUBKORREKTUR = 5.0 / 6.0

_NKNOTEN = {"shell3": 3, "shell4": 4, "shell6": 6, "shell8": 8}
_ECKEN = {"shell3": 3, "shell4": 4, "shell6": 3, "shell8": 4}
_TYP_NACH_N = {3: "shell3", 4: "shell4", 6: "shell6", 8: "shell8"}


# ==========================================================================
# Laminat (klassische Laminattheorie)
# ==========================================================================
@dataclass
class Laminat:
    """Steifigkeiten eines Schichtaufbaus.

    A Scheibe, B Kopplung, D Platte (je 3x3, Reihenfolge xx yy xy),
    Ds Querschub (2x2, Reihenfolge xz yz, Schubkorrektur enthalten),
    t Gesamtdicke, lagen Eingabeliste (von unten nach oben),
    q_lagen je Lage (Qbar 3x3, Qsbar 2x2, z_unten, z_oben) im Elementsystem.
    """
    A: np.ndarray
    B: np.ndarray
    D: np.ndarray
    Ds: np.ndarray
    t: float
    lagen: list
    q_lagen: list = field(default_factory=list)

    def flaechenmasse(self, rho: float | None = None) -> float:
        """Masse je Flaeche: Summe rho_i t_i (rho aus der Lage, sonst rho)."""
        m = 0.0
        for lage in self.lagen:
            r = lage.get("rho", rho)
            if r is None:
                raise ValueError("Dichte fehlt (rho in der Lage oder als Argument)")
            m += float(r) * float(lage["t"])
        return m


def _lagen_steifigkeit(lage: dict):
    """Q (3x3) und Qs (2x2) einer Lage in ihren Materialachsen (1, 2)."""
    if "E1" in lage:
        E1, E2 = float(lage["E1"]), float(lage["E2"])
        nu12, G12 = float(lage["nu12"]), float(lage["G12"])
        G13 = float(lage.get("G13", G12))
        G23 = float(lage.get("G23", G12))
        nu21 = nu12 * E2 / E1
        f = 1.0 / (1.0 - nu12 * nu21)
        Q = np.array([[E1 * f, nu12 * E2 * f, 0.0],
                      [nu12 * E2 * f, E2 * f, 0.0],
                      [0.0, 0.0, G12]])
        Qs = np.diag([G13, G23])
    else:
        E, nu = float(lage["E"]), float(lage["nu"])
        f = E / (1.0 - nu ** 2)
        G = E / (2.0 * (1.0 + nu))
        Q = f * np.array([[1.0, nu, 0.0],
                          [nu, 1.0, 0.0],
                          [0.0, 0.0, 0.5 * (1.0 - nu)]])
        Qs = G * np.eye(2)
    return Q, Qs


def _lage_drehen(Q: np.ndarray, Qs: np.ndarray, winkel: float):
    """Lagensteifigkeit ins Elementsystem drehen. winkel: Faserachse 1 gegen
    die lokale x-Achse (Bogenmass). Dehnungstransformation (x,y) -> (1,2)
    mit technischen Gleitungen; Qbar = Te^T Q Te (Energieinvarianz)."""
    c, s = np.cos(winkel), np.sin(winkel)
    Te = np.array([[c * c, s * s, c * s],
                   [s * s, c * c, -c * s],
                   [-2 * c * s, 2 * c * s, c * c - s * s]])
    R = np.array([[c, s], [-s, c]])
    return Te.T @ Q @ Te, R.T @ Qs @ R


def abd_matrizen(lagen) -> Laminat:
    """A-, B-, D- und Ds-Matrix eines Schichtaufbaus.

    lagen: Liste von dicts, von unten (z = -t/2) nach oben:
      isotrop   {t, E, nu, winkel}
      orthotrop {t, E1, E2, nu12, G12, G13, G23, winkel}
    optional rho je Lage (fuer die Massenmatrix). winkel im Bogenmass zur
    lokalen x-Achse. Bezugsflaeche ist die Mittelflaeche des Gesamtaufbaus,
    Querschub mit Schubkorrektur 5/6.
    """
    lagen = [dict(lage) for lage in lagen]
    if not lagen:
        raise ValueError("Laminat ohne Lagen")
    t = sum(float(lage["t"]) for lage in lagen)
    A = np.zeros((3, 3))
    B = np.zeros((3, 3))
    D = np.zeros((3, 3))
    Ds = np.zeros((2, 2))
    q_lagen = []
    z = -0.5 * t
    for lage in lagen:
        z0, z1 = z, z + float(lage["t"])
        Q, Qs = _lagen_steifigkeit(lage)
        Qb, Qsb = _lage_drehen(Q, Qs, float(lage.get("winkel", 0.0)))
        A += Qb * (z1 - z0)
        B += Qb * (z1 ** 2 - z0 ** 2) / 2.0
        D += Qb * (z1 ** 3 - z0 ** 3) / 3.0
        Ds += SCHUBKORREKTUR * Qsb * (z1 - z0)
        q_lagen.append((Qb, Qsb, z0, z1))
        z = z1
    return Laminat(A, B, D, Ds, t, lagen, q_lagen)


def isotrop_laminat(E: float, nu: float, t: float) -> Laminat:
    """Einlagiges isotropes Laminat: A = E t/(1-nu^2) D0, B = 0,
    D = E t^3/(12 (1-nu^2)) D0, Ds = 5/6 G t I."""
    return abd_matrizen([{"t": float(t), "E": float(E), "nu": float(nu),
                          "winkel": 0.0}])


def _laminat(E, nu, t, laminat) -> Laminat:
    if laminat is not None:
        return laminat
    return isotrop_laminat(E, nu, t)


# ==========================================================================
# Geometrie und Formfunktionen
# ==========================================================================
def schalen_frame(P):
    """Lokales Elementsystem eines ebenen Schalenelements (3, 4, 6, 8 Knoten).

    Rueckgabe: T3 (3x3, Zeilen ex ey ez), xy (n,2) lokale Knotenkoordinaten
    (Ursprung im Schwerpunkt der Eckknoten, auf die Ausgleichsebene
    projiziert), A Flaeche, verwoelbung (groesster Knotenabstand zur Ebene).
    """
    P = np.asarray(P, float).reshape(-1, 3)
    typ = _TYP_NACH_N.get(P.shape[0])
    if typ is None:
        raise ValueError(f"Schalenelement mit {P.shape[0]} Knoten unbekannt")
    ecken = P[:_ECKEN[typ]]
    c = ecken.mean(axis=0)
    if len(ecken) == 4:
        nv = np.cross(ecken[2] - ecken[0], ecken[3] - ecken[1])
    else:
        nv = np.cross(ecken[1] - ecken[0], ecken[2] - ecken[0])
    ln = np.linalg.norm(nv)
    if ln <= 0.0:
        raise ValueError("entartetes Schalenelement (Flaeche 0)")
    ez = nv / ln
    v01 = ecken[1] - ecken[0]
    ex = v01 - (v01 @ ez) * ez
    lx = np.linalg.norm(ex)
    if lx <= 0.0:
        raise ValueError("entartetes Schalenelement (Kante 0-1 ohne Laenge)")
    ex = ex / lx
    ey = np.cross(ez, ex)
    T3 = np.vstack([ex, ey, ez])
    d = P - c
    xy = np.column_stack([d @ ex, d @ ey])
    verwoelbung = float(np.max(np.abs(d @ ez)))
    A = 0.0
    for r, s, w in _regeln(typ)[0]:
        _, dN = formfunktionen(typ, r, s)
        A += w * _jacobi(xy, dN)[1]
    return T3, xy, A, verwoelbung


def formfunktionen(typ: str, r: float, s: float):
    """Formfunktionen N (n,) und natuerliche Ableitungen dN (n,2) an (r,s).
    Dreiecke: Flaechenkoordinaten mit Ecken (0,0), (1,0), (0,1);
    Vierecke: (xi, eta) in [-1,1]^2."""
    if typ == "shell3":
        N = np.array([1.0 - r - s, r, s])
        dN = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]])
    elif typ == "shell6":
        L1, L2, L3 = 1.0 - r - s, r, s
        N = np.array([L1 * (2 * L1 - 1), L2 * (2 * L2 - 1), L3 * (2 * L3 - 1),
                      4 * L1 * L2, 4 * L2 * L3, 4 * L3 * L1])
        dN = np.array([[1 - 4 * L1, 1 - 4 * L1],
                       [4 * L2 - 1, 0.0],
                       [0.0, 4 * L3 - 1],
                       [4 * (L1 - L2), -4 * L2],
                       [4 * L3, 4 * L2],
                       [-4 * L3, 4 * (L1 - L3)]])
    elif typ == "shell4":
        xi_i = np.array([-1.0, 1.0, 1.0, -1.0])
        et_i = np.array([-1.0, -1.0, 1.0, 1.0])
        N = 0.25 * (1 + xi_i * r) * (1 + et_i * s)
        dN = np.column_stack([0.25 * xi_i * (1 + et_i * s),
                              0.25 * et_i * (1 + xi_i * r)])
    elif typ == "shell8":
        xi_i = np.array([-1.0, 1.0, 1.0, -1.0])
        et_i = np.array([-1.0, -1.0, 1.0, 1.0])
        N = np.zeros(8)
        dN = np.zeros((8, 2))
        N[:4] = 0.25 * (1 + xi_i * r) * (1 + et_i * s) * (xi_i * r + et_i * s - 1)
        dN[:4, 0] = 0.25 * xi_i * (1 + et_i * s) * (2 * xi_i * r + et_i * s)
        dN[:4, 1] = 0.25 * et_i * (1 + xi_i * r) * (xi_i * r + 2 * et_i * s)
        N[4] = 0.5 * (1 - r * r) * (1 - s)
        dN[4] = [-r * (1 - s), -0.5 * (1 - r * r)]
        N[5] = 0.5 * (1 + r) * (1 - s * s)
        dN[5] = [0.5 * (1 - s * s), -s * (1 + r)]
        N[6] = 0.5 * (1 - r * r) * (1 + s)
        dN[6] = [-r * (1 + s), 0.5 * (1 - r * r)]
        N[7] = 0.5 * (1 - r) * (1 - s * s)
        dN[7] = [-0.5 * (1 - s * s), -s * (1 - r)]
    else:
        raise ValueError(f"unbekannter Schalentyp '{typ}'")
    return N, dN


def _jacobi(xy: np.ndarray, dN: np.ndarray):
    """Jacobi-Matrix J = [[x,r y,r], [x,s y,s]], Determinante und
    kartesische Ableitungen dNxy (n,2)."""
    J = dN.T @ xy
    detJ = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
    if detJ <= 0.0:
        raise ValueError("Schalenelement: Jacobi-Determinante <= 0 "
                         "(Knotenreihenfolge gegen den Uhrzeigersinn?)")
    Jinv = np.array([[J[1, 1], -J[0, 1]], [-J[1, 0], J[0, 0]]]) / detJ
    return J, detJ, dN @ Jinv.T


def _mitte(typ: str):
    return (1.0 / 3.0, 1.0 / 3.0) if typ in ("shell3", "shell6") else (0.0, 0.0)


# --- Integrationsregeln ----------------------------------------------------
_G2 = 1.0 / np.sqrt(3.0)
_G3 = np.sqrt(0.6)
_QUAD2 = [(a, b, 1.0) for a in (-_G2, _G2) for b in (-_G2, _G2)]
_QUAD3 = [(a, b, wa * wb)
          for a, wa in ((-_G3, 5 / 9), (0.0, 8 / 9), (_G3, 5 / 9))
          for b, wb in ((-_G3, 5 / 9), (0.0, 8 / 9), (_G3, 5 / 9))]
_TRI3 = [(1 / 6, 1 / 6, 1 / 6), (2 / 3, 1 / 6, 1 / 6), (1 / 6, 2 / 3, 1 / 6)]
_TRI3K = [(0.5, 0.0, 1 / 6), (0.5, 0.5, 1 / 6), (0.0, 0.5, 1 / 6)]   # Kantenmitten, Grad 2
_TA, _TWA = 0.470142064105115, 0.132394152788506
_TB, _TWB = 0.101286507323456, 0.125939180544827
_TRI7 = [(1 / 3, 1 / 3, 0.1125),
         (_TA, _TA, _TWA / 2), (1 - 2 * _TA, _TA, _TWA / 2), (_TA, 1 - 2 * _TA, _TWA / 2),
         (_TB, _TB, _TWB / 2), (1 - 2 * _TB, _TB, _TWB / 2), (_TB, 1 - 2 * _TB, _TWB / 2)]


def _regeln(typ: str):
    """(Regel Membran/Biegung, Regel Querschub) je Elementtyp."""
    if typ == "shell3":
        return _TRI3, _TRI3          # MITC3: Querschub linear -> 3-Punkt exakt
    if typ == "shell4":
        return _QUAD2, _QUAD2        # MITC4: 2x2 fuer alle Anteile
    if typ == "shell6":
        return _TRI7, _TRI3K         # 7-Punkt (Grad 5), Querschub 3-Punkt (Kantenmitten)
    if typ == "shell8":
        return _QUAD3, _QUAD2        # 3x3, Querschub 2x2 (selektiv reduziert)
    raise ValueError(f"unbekannter Schalentyp '{typ}'")


# ==========================================================================
# B-Matrizen (lokale FHG je Knoten: u v w rx ry rz; danach innere FHG)
# ==========================================================================
_BUBBLE = {"shell3": False, "shell4": False, "shell6": True, "shell8": True}


def _bubble(typ: str, r: float, s: float):
    """Hierarchische Bubble-Funktion der Verdrehungen: Wert und natuerliche
    Ableitungen (2,). Dreieck kubisch 27 r s (1-r-s), Viereck (1-xi^2)(1-eta^2)
    (ergaenzt den Serendipity-Ansatz zum Lagrange-Ansatz, Heterosis)."""
    if typ in ("shell3", "shell6"):
        f = 27.0 * r * s * (1.0 - r - s)
        df = np.array([27.0 * s * (1.0 - 2.0 * r - s), 27.0 * r * (1.0 - r - 2.0 * s)])
    else:
        f = (1.0 - r * r) * (1.0 - s * s)
        df = np.array([-2.0 * r * (1.0 - s * s), -2.0 * s * (1.0 - r * r)])
    return f, df


def _anzahl_innere(typ: str):
    """(Bubble-Verdrehungen, inkompatible Membranmoden)."""
    return (2 if _BUBBLE[typ] else 0), (4 if typ == "shell4" else 0)


def _b_membran(dNxy: np.ndarray, nt: int) -> np.ndarray:
    B = np.zeros((3, nt))
    B[0, 0:6 * len(dNxy):6] = dNxy[:, 0]
    B[1, 1:6 * len(dNxy):6] = dNxy[:, 1]
    B[2, 0:6 * len(dNxy):6] = dNxy[:, 1]
    B[2, 1:6 * len(dNxy):6] = dNxy[:, 0]
    return B


def _b_biegung(dNxy: np.ndarray, nt: int, dfb=None) -> np.ndarray:
    n = len(dNxy)
    B = np.zeros((3, nt))
    B[0, 4:6 * n:6] = dNxy[:, 0]      # kappa_x  = ry,x
    B[1, 3:6 * n:6] = -dNxy[:, 1]     # kappa_y  = -rx,y
    B[2, 4:6 * n:6] = dNxy[:, 1]      # kappa_xy = ry,y - rx,x
    B[2, 3:6 * n:6] = -dNxy[:, 0]
    if dfb is not None:               # Bubble-Verdrehungen rx_b, ry_b
        B[0, 6 * n + 1] = dfb[0]
        B[1, 6 * n] = -dfb[1]
        B[2, 6 * n + 1] = dfb[1]
        B[2, 6 * n] = -dfb[0]
    return B


def _b_inkompatibel(r: float, s: float, J0inv: np.ndarray, faktor: float) -> np.ndarray:
    """Membran-B-Matrix (3x4) der inkompatiblen Moden 1-xi^2, 1-eta^2 des
    Vierecks (Reihenfolge: u-P1, u-P2, v-P1, v-P2). Ableitungen mit der
    Jacobi-Matrix der Elementmitte und dem Faktor detJ0/detJ (Taylor-
    Korrektur), damit das Integral der Moden verschwindet (Patch-Test)."""
    dP = np.array([[-2.0 * r, 0.0], [0.0, -2.0 * s]])     # Zeilen P1, P2
    dPxy = (dP @ J0inv.T) * faktor
    B = np.zeros((3, 4))
    B[0, 0], B[0, 1] = dPxy[0, 0], dPxy[1, 0]
    B[1, 2], B[1, 3] = dPxy[0, 1], dPxy[1, 1]
    B[2, 0], B[2, 1] = dPxy[0, 1], dPxy[1, 1]
    B[2, 2], B[2, 3] = dPxy[0, 0], dPxy[1, 0]
    return B


def _kovariante_schubzeile(typ: str, xy: np.ndarray, r: float, s: float,
                           richtung: int, nt: int) -> np.ndarray:
    """Zeile (nt,) der kovarianten Querschubgleitung e_rt (richtung 0) bzw.
    e_st (richtung 1) am natuerlichen Punkt (r, s) aus dem Verschiebungsansatz:
    e = w,r + x,r ry - y,r rx (einschliesslich Bubble-Verdrehungen)."""
    N, dN = formfunktionen(typ, r, s)
    n = len(N)
    J = dN.T @ xy
    z = np.zeros(nt)
    z[2:6 * n:6] = dN[:, richtung]
    z[3:6 * n:6] = -J[richtung, 1] * N
    z[4:6 * n:6] = J[richtung, 0] * N
    if _BUBBLE[typ]:
        fb, _ = _bubble(typ, r, s)
        z[6 * n] = -J[richtung, 1] * fb
        z[6 * n + 1] = J[richtung, 0] * fb
    return z


def _mitc_vorbereiten(typ: str, xy: np.ndarray, nt: int):
    """Kopplungspunkte der MITC-Elemente (angenommene Querschubgleitungen)."""
    zeile = lambda r, s, d: _kovariante_schubzeile(typ, xy, r, s, d, nt)  # noqa: E731
    if typ == "shell4":
        # Bathe/Dvorkin: e_xi an den Kantenmitten eta = -1 (A) und +1 (C),
        # e_eta an xi = -1 (D) und +1 (B)
        return {"A": zeile(0.0, -1.0, 0), "C": zeile(0.0, 1.0, 0),
                "D": zeile(-1.0, 0.0, 1), "B": zeile(1.0, 0.0, 1)}
    if typ == "shell3":
        # Lee/Bathe: e_rt = e_rt(1) + c s, e_st = e_st(2) - c r mit den
        # Kopplungspunkten (1) = (1/2, 0), (2) = (0, 1/2), (3) = (1/2, 1/2);
        # c aus der Bedingung fuer die Gleitung laengs der Kante 1-2 in (3)
        r1, s2 = zeile(0.5, 0.0, 0), zeile(0.0, 0.5, 1)
        r3, s3 = zeile(0.5, 0.5, 0), zeile(0.5, 0.5, 1)
        return {"r1": r1, "s2": s2, "c": r3 - s3 - r1 + s2}
    return None


def _b_schub(typ: str, r: float, s: float, N, dNxy, J, kopplung, nt: int) -> np.ndarray:
    """Querschub-B-Matrix (2 x nt): MITC-Interpolation fuer shell3/shell4,
    sonst verschiebungsbasiert (mit Bubble-Verdrehungen)."""
    if typ == "shell4":
        e_r = 0.5 * (1 - s) * kopplung["A"] + 0.5 * (1 + s) * kopplung["C"]
        e_s = 0.5 * (1 - r) * kopplung["D"] + 0.5 * (1 + r) * kopplung["B"]
        return np.linalg.solve(J, np.vstack([e_r, e_s]))
    if typ == "shell3":
        e_r = kopplung["r1"] + kopplung["c"] * s
        e_s = kopplung["s2"] - kopplung["c"] * r
        return np.linalg.solve(J, np.vstack([e_r, e_s]))
    n = len(N)
    B = np.zeros((2, nt))
    B[0, 2:6 * n:6] = dNxy[:, 0]      # gamma_xz = w,x + ry
    B[0, 4:6 * n:6] = N
    B[1, 2:6 * n:6] = dNxy[:, 1]      # gamma_yz = w,y - rx
    B[1, 3:6 * n:6] = -N
    if _BUBBLE[typ]:
        fb, _ = _bubble(typ, r, s)
        B[0, 6 * n + 1] = fb
        B[1, 6 * n] = -fb
    return B


# ==========================================================================
# Steifigkeitsmatrizen
# ==========================================================================
def _k_drill(typ: str, xy: np.ndarray, lam: Laminat, A: float, nt: int) -> np.ndarray:
    """Kuenstliche Drillsteifigkeit: kd * Summe_i (rz_i - omega)^2 mit der
    Scheibendrehung omega = 0.5 (v,x - u,y) in der Elementmitte. Die
    Starrkoerperdrehung um die Normale (rz = omega) bleibt energiefrei."""
    n = _NKNOTEN[typ]
    _, dN = formfunktionen(typ, *_mitte(typ))
    _, _, dNxy = _jacobi(xy, dN)
    b = np.zeros(nt)
    b[0:6 * n:6] = -0.5 * dNxy[:, 1]
    b[1:6 * n:6] = 0.5 * dNxy[:, 0]
    kd = DRILL_FACTOR * lam.A[0, 0] * A
    K = np.zeros((nt, nt))
    for i in range(n):
        g = -b
        g[6 * i + 5] += 1.0
        K += kd * np.outer(g, g)
    return K


def _k_lokal_voll(typ: str, xy: np.ndarray, lam: Laminat) -> np.ndarray:
    """Lokale Steifigkeitsmatrix einschliesslich der inneren FHG
    (nt = 6n + Bubble-Verdrehungen + inkompatible Moden) mit vereinheitlichter
    B-Matrix [Membran; Kruemmung; Querschub] und Werkstoffmatrix
    [[A,B,0],[B,D,0],[0,0,Ds]]."""
    n = _NKNOTEN[typ]
    nd = 6 * n
    nb, ni = _anzahl_innere(typ)
    nt = nd + nb + ni
    Cmb = np.block([[lam.A, lam.B], [lam.B, lam.D]])
    regel_mb, regel_s = _regeln(typ)
    kopplung = _mitc_vorbereiten(typ, xy, nt)
    K = np.zeros((nt, nt))
    if ni:
        _, dN0 = formfunktionen(typ, 0.0, 0.0)
        J0, detJ0, _ = _jacobi(xy, dN0)
        J0inv = np.linalg.inv(J0)
    A = 0.0
    for r, s, w in regel_mb:
        N, dN = formfunktionen(typ, r, s)
        J, detJ, dNxy = _jacobi(xy, dN)
        dfb = None
        if nb:
            _, dfb_nat = _bubble(typ, r, s)
            dfb = np.linalg.solve(J, dfb_nat)
        Bmb = np.vstack([_b_membran(dNxy, nt), _b_biegung(dNxy, nt, dfb)])
        if ni:
            Bmb[:3, nd + nb:] = _b_inkompatibel(r, s, J0inv, detJ0 / detJ)
        K += (w * detJ) * (Bmb.T @ Cmb @ Bmb)
        A += w * detJ
    for r, s, w in regel_s:
        N, dN = formfunktionen(typ, r, s)
        J, detJ, dNxy = _jacobi(xy, dN)
        Bs = _b_schub(typ, r, s, N, dNxy, J, kopplung, nt)
        K += (w * detJ) * (Bs.T @ lam.Ds @ Bs)
    K += _k_drill(typ, xy, lam, A, nt)
    return K


def k_schale_lokal(typ: str, xy: np.ndarray, lam: Laminat) -> np.ndarray:
    """Lokale Steifigkeitsmatrix (6n x 6n); innere FHG (Bubble-Verdrehungen,
    inkompatible Moden) statisch kondensiert."""
    nd = 6 * _NKNOTEN[typ]
    K = _k_lokal_voll(typ, xy, lam)
    if K.shape[0] == nd:
        return K
    Krc = K[:nd, nd:]
    Kcc = K[nd:, nd:]
    return K[:nd, :nd] - Krc @ np.linalg.solve(Kcc, Krc.T)


def _k_global(typ: str, P, E, nu, t, laminat) -> np.ndarray:
    P = np.asarray(P, float).reshape(-1, 3)
    if P.shape[0] != _NKNOTEN[typ]:
        raise ValueError(f"{typ}: {_NKNOTEN[typ]} Knoten erwartet, {P.shape[0]} erhalten")
    lam = _laminat(E, nu, t, laminat)
    T3, xy, _, _ = schalen_frame(P)
    T = T_shell(T3, _NKNOTEN[typ])
    return T.T @ k_schale_lokal(typ, xy, lam) @ T


def k_shell4_mitc(P, E, nu, t, laminat=None) -> np.ndarray:
    """Viereck (24x24, global): Membran bilinear mit inkompatiblen Moden
    (2x2 Gauss, Taylor-Korrektur, statisch kondensiert), Platte MITC4
    (Querschub an den Kantenmitten interpoliert), Biegung 2x2."""
    return _k_global("shell4", P, E, nu, t, laminat)


def k_shell3_mitc(P, E, nu, t, laminat=None) -> np.ndarray:
    """Dreieck (18x18, global): Membran CST, Platte MITC3 (Lee/Bathe 2004),
    3-Punkt-Integration."""
    return _k_global("shell3", P, E, nu, t, laminat)


def k_shell6(P, E, nu, t, laminat=None) -> np.ndarray:
    """Quadratisches Dreieck (36x36, global): Membran und Biegung 7-Punkt,
    Querschub 3-Punkt an den Kantenmitten (selektiv reduziert), Verdrehungen
    mit kubischer Bubble (innere FHG kondensiert)."""
    return _k_global("shell6", P, E, nu, t, laminat)


def k_shell8(P, E, nu, t, laminat=None) -> np.ndarray:
    """Serendipity-Viereck (48x48, global): Membran und Biegung 3x3,
    Querschub 2x2 (selektiv reduziert); Verdrehungen mit Lagrange-Ansatz
    (Heterosis, innerer Knoten kondensiert)."""
    return _k_global("shell8", P, E, nu, t, laminat)


def k_schale(typ: str, P, E, nu, t, laminat=None) -> np.ndarray:
    """Globale Steifigkeitsmatrix (6n x 6n) je Elementtyp:
    shell3 -> MITC3, shell4 -> MITC4, shell6, shell8."""
    if typ not in _NKNOTEN:
        raise ValueError(f"unbekannter Schalentyp '{typ}'")
    return _k_global(typ, P, E, nu, t, laminat)


# ==========================================================================
# Verzerrungen, Schnittgroessen, Spannungen
# ==========================================================================
def verzerrungen_schale(typ: str, P, E, nu, t, u_glob, laminat=None) -> dict:
    """Membrandehnungen eps, Kruemmungen kappa und Querschubgleitungen gamma
    in der Elementmitte (lokal), dazu T3. Die inneren FHG werden aus den
    Knotenverschiebungen zurueckgerechnet."""
    P = np.asarray(P, float).reshape(-1, 3)
    n = _NKNOTEN[typ]
    nd = 6 * n
    lam = _laminat(E, nu, t, laminat)
    T3, xy, _, _ = schalen_frame(P)
    ul = T_shell(T3, n) @ np.asarray(u_glob, float).reshape(nd)
    K = _k_lokal_voll(typ, xy, lam)
    nt = K.shape[0]
    u = np.zeros(nt)
    u[:nd] = ul
    if nt > nd:
        u[nd:] = -np.linalg.solve(K[nd:, nd:], K[nd:, :nd] @ ul)
    r, s = _mitte(typ)
    N, dN = formfunktionen(typ, r, s)
    J, _, dNxy = _jacobi(xy, dN)
    nb, ni = _anzahl_innere(typ)
    dfb = None
    if nb:
        _, dfb_nat = _bubble(typ, r, s)
        dfb = np.linalg.solve(J, dfb_nat)
    Bm = _b_membran(dNxy, nt)
    if ni:      # inkompatible Moden: Ableitungen in der Mitte gleich 0
        Bm[:, nd + nb:] = 0.0
    kopplung = _mitc_vorbereiten(typ, xy, nt)
    return {"eps": Bm @ u,
            "kappa": _b_biegung(dNxy, nt, dfb) @ u,
            "gamma": _b_schub(typ, r, s, N, dNxy, J, kopplung, nt) @ u,
            "T3": T3}


def _von_mises(sig) -> float:
    sx, sy, sxy = sig
    return float(np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3 * sxy ** 2))


def stress_schale(typ: str, P, E, nu, t, u_glob, laminat=None) -> dict:
    """Schnittgroessen und Spannungen in der Elementmitte.
    Rueckgabe dict mit n (Nx,Ny,Nxy), m (Mx,My,Mxy), q (Qx,Qy), sig_top/
    sig_bot (3 Komponenten, bei Laminaten aus der obersten/untersten Lage mit
    deren Steifigkeit), vM_top, vM_bot, vM, T3."""
    lam = _laminat(E, nu, t, laminat)
    v = verzerrungen_schale(typ, P, E, nu, t, u_glob, lam)
    eps, kappa, gamma = v["eps"], v["kappa"], v["gamma"]
    n_f = lam.A @ eps + lam.B @ kappa
    m_f = lam.B @ eps + lam.D @ kappa
    q_f = lam.Ds @ gamma
    h = 0.5 * lam.t
    Q_unten = lam.q_lagen[0][0]
    Q_oben = lam.q_lagen[-1][0]
    sig_top = Q_oben @ (eps + h * kappa)
    sig_bot = Q_unten @ (eps - h * kappa)
    vt, vb = _von_mises(sig_top), _von_mises(sig_bot)
    return {
        "n": n_f, "m": m_f, "q": q_f,
        "sig_top": sig_top, "sig_bot": sig_bot,
        "vM_top": vt, "vM_bot": vb, "vM": max(vt, vb),
        "T3": v["T3"],
    }


# ==========================================================================
# Masse und Lasten
# ==========================================================================
def masse_schale(typ: str, P, rho, t, laminat=None) -> np.ndarray:
    """Konzentrierte Massenmatrix (6n x 6n, diagonal). Knotenanteile nach
    dem Diagonalskalierungsverfahren (HRZ), kleine Rotationstraegheit wie
    shell3_mass. Laminat: Flaechenmasse Summe rho_i t_i (rho je Lage,
    sonst rho)."""
    P = np.asarray(P, float).reshape(-1, 3)
    n = _NKNOTEN[typ]
    _, xy, A, _ = schalen_frame(P)
    mA = float(rho) * float(t) if laminat is None else laminat.flaechenmasse(rho)
    anteil = np.zeros(n)
    for r, s, w in _regeln(typ)[0]:
        N, dN = formfunktionen(typ, r, s)
        anteil += w * _jacobi(xy, dN)[1] * N ** 2
    m = mA * A * anteil / anteil.sum()
    d = np.zeros(6 * n)
    for i in range(n):
        d[6 * i:6 * i + 3] = m[i]
        d[6 * i + 3:6 * i + 6] = m[i] * (A / n) * 1e-3
    return np.diag(d)


def flaechenlast_schale(typ: str, P, p) -> np.ndarray:
    """Konsistente Knotenkraefte (6n, global) einer Flaechenlast p in
    Richtung der Elementnormalen; Momente 0. (shell8: Ecken -pA/12,
    Kantenmitten +pA/3; shell6: Ecken 0, Kantenmitten pA/3.)"""
    P = np.asarray(P, float).reshape(-1, 3)
    n = _NKNOTEN[typ]
    T3, xy, _, _ = schalen_frame(P)
    fn = np.zeros(n)
    for r, s, w in _regeln(typ)[0]:
        N, dN = formfunktionen(typ, r, s)
        fn += w * _jacobi(xy, dN)[1] * N
    f = np.zeros(6 * n)
    for i in range(n):
        f[6 * i:6 * i + 3] = float(p) * fn[i] * T3[2]
    return f


def temperatur_schale(typ: str, P, E, nu, t, alpha, dT, laminat=None) -> np.ndarray:
    """Aequivalente Knotenlasten (6n, global) einer gleichmaessigen
    Temperaturaenderung dT: Membrananteil n0 = A alpha dT [1 1 0]; bei
    Laminaten mit Kopplung zusaetzlich m0 = B alpha dT [1 1 0]."""
    P = np.asarray(P, float).reshape(-1, 3)
    n = _NKNOTEN[typ]
    lam = _laminat(E, nu, t, laminat)
    eps0 = float(alpha) * float(dT) * np.array([1.0, 1.0, 0.0])
    n0 = lam.A @ eps0
    m0 = lam.B @ eps0
    T3, xy, _, _ = schalen_frame(P)
    f = np.zeros(6 * n)
    for r, s, w in _regeln(typ)[0]:
        _, dN = formfunktionen(typ, r, s)
        _, detJ, dNxy = _jacobi(xy, dN)
        f += (w * detJ) * (_b_membran(dNxy, 6 * n).T @ n0
                           + _b_biegung(dNxy, 6 * n).T @ m0)
    return T_shell(T3, n).T @ f
