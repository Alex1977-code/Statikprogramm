"""
Verbindungs- und Sonderelemente.

* Zweiknotenfeder mit sechs lokalen Steifigkeiten
* Seil als elastische Kettenlinie (Peyrot/Goulois 1979, Jayaraman/Knudson 1981)
* Starre Koerper RBE2 / RBE3 als Zwangsbedingungen (Strafverfahren)
* Grenzschichtelement ohne Dicke (Interface) mit 3 oder 4 Knoten je Seite

Alle Bausteine liefern dichte numpy-Matrizen im globalen System. Die
FHG-Reihenfolge je Knoten ist wie in beam3d [ux uy uz rx ry rz].
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from . import beam3d as bm


# ==========================================================================
# Feder
# ==========================================================================
def feder_achsen(P1, P2, achse=None, roll: float = 0.0) -> np.ndarray:
    """Richtungskosinusmatrix T3 (3x3, Zeilen ex, ey, ez) einer Zweiknotenfeder.

    ex zeigt von P1 nach P2. Fallen die Knoten zusammen, wird ex = ``achse``
    (Vorgabe global x). ey und ez werden wie in ``beam3d.local_axes`` gebildet
    (Referenz global z, bei vertikaler Achse global x), ``roll`` dreht um ex.
    """
    P1 = np.asarray(P1, float)
    P2 = np.asarray(P2, float)
    L = float(np.linalg.norm(P2 - P1))
    ref = max(1.0, float(np.linalg.norm(P1)), float(np.linalg.norm(P2)))
    if L > 1e-9 * ref:
        return bm.local_axes(P1, P2, roll)[0]
    ex = np.array([1.0, 0.0, 0.0]) if achse is None else np.asarray(achse, float)
    n = float(np.linalg.norm(ex))
    if n <= 0:
        raise ValueError("Federachse mit Laenge 0")
    return bm.local_axes(np.zeros(3), ex / n, roll)[0]


def k_feder(k6, T3) -> np.ndarray:
    """Globale Steifigkeitsmatrix (12x12) einer Zweiknotenfeder.

    k6 = [kx, ky, kz, krx, kry, krz] lokale Steifigkeiten entlang der Achsen T3
    (Zeilen ex, ey, ez). Lokal K = [[k, -k], [-k, k]] mit k = diag(k6),
    transformiert wie ein Stab: K = T^T K_l T.
    """
    k6 = np.asarray(k6, float)
    if k6.shape != (6,):
        raise ValueError("k6 braucht 6 Steifigkeiten [kx ky kz krx kry krz]")
    kd = np.diag(k6)
    Kl = np.zeros((12, 12))
    Kl[:6, :6] = kd
    Kl[6:, 6:] = kd
    Kl[:6, 6:] = -kd
    Kl[6:, :6] = -kd
    T = bm.transform_matrix(np.asarray(T3, float))
    return T.T @ Kl @ T


def feder_kraefte(k6, T3, u12) -> np.ndarray:
    """Lokale Federkraefte/-momente (6,) aus den globalen Knotenverschiebungen
    u12 (12,). Positiv = Zug bzw. Dehnung der Feder (Knoten 2 bewegt sich in
    Richtung +ex von Knoten 1 weg; Momente analog aus theta2 - theta1)."""
    k6 = np.asarray(k6, float)
    T3 = np.asarray(T3, float)
    u12 = np.asarray(u12, float)
    du = u12[6:] - u12[:6]
    dl = np.concatenate([T3 @ du[:3], T3 @ du[3:]])
    return k6 * dl


# ==========================================================================
# Seil als elastische Kettenlinie
# ==========================================================================
# Formulierung (Irvine; Peyrot/Goulois 1979; Jayaraman/Knudson 1981):
# s = ungedehnte Bogenlaenge 0..L0, q = |w| Gewicht je ungedehnter Laenge,
# e_up = -w/q. Der Seilzug im Schnitt s (Kraft des Teils s..L0 auf 0..s) ist
#     T(s) = (H, V0 + q s)          in der Ebene (e_x, e_up)
# mit dem konstanten Horizontalzug H > 0. Aus dx/ds = (1 + T/EA) H/T folgt
#     x(s) = H s/EA + (H/q) [asinh((V0 + q s)/H) - asinh(V0/H)]
#     z(s) = (V0 s + q s^2/2)/EA + [T(s) - T(0)]/q
# Die Unbekannten H, V0 folgen aus x(L0) = l, z(L0) = h (Newton).
#
# Vorzeichen der Rueckgabe: f_int sind die Kraefte, die die Knoten auf das Seil
# ausueben (f_int = -[F_auf_Knoten1, F_auf_Knoten2]):
#     f_int1 = -T(0) = -(H e_x + V0 e_up),   f_int2 = +T(L0)
# Summe f_int = -w L0 (die Knoten tragen das Seilgewicht). Kt = d f_int/d[u1, u2].


def _seil_ebene(P1, P2, w):
    """Ebene aus Sehne und Last. Rueckgabe (e_x, e_up, e_y, l, h, c, q)."""
    P1 = np.asarray(P1, float)
    P2 = np.asarray(P2, float)
    w = np.asarray(w, float)
    d = P2 - P1
    c = float(np.linalg.norm(d))
    q = float(np.linalg.norm(w))
    if q <= 0:
        return None, None, None, 0.0, 0.0, c, 0.0
    e_up = -w / q
    h = float(d @ e_up)
    dh = d - h * e_up
    l = float(np.linalg.norm(dh))
    if l > 1e-9 * max(c, 1e-300):
        e_x = dh / l
    else:
        l = 0.0
        ref = np.array([1.0, 0.0, 0.0]) if abs(e_up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e_x = np.cross(e_up, ref)
        e_x /= np.linalg.norm(e_x)
    e_y = np.cross(e_up, e_x)
    return e_x, e_up, e_y, l, h, c, q


def _asinh_diff(a: float, b: float, d: float, H: float) -> float:
    """asinh(a/H) - asinh(b/H) ohne Ausloeschung; d = a - b exakt bekannt."""
    u, v = a / H, b / H
    if a * b > 0:
        su = math.sqrt(1.0 + u * u)
        sv = math.sqrt(1.0 + v * v)
        return math.asinh((d / H) * (u + v) / (u * sv + v * su))
    return math.asinh(u) - math.asinh(v)


def _hyp_diff(a: float, b: float, d: float, H: float) -> float:
    """sqrt(H^2 + a^2) - sqrt(H^2 + b^2) ohne Ausloeschung; d = a - b."""
    Ta = math.hypot(H, a)
    Tb = math.hypot(H, b)
    if Ta + Tb <= 0:
        return 0.0
    return d * (a + b) / (Ta + Tb)


_GAUSS = np.polynomial.legendre.leggauss(6)


def _int_V2_T3(H: float, a: float, b: float, d: float) -> float:
    """int_b^a V^2 / (H^2 + V^2)^(3/2) dV  (= [asinh(V/H) - V/T]_b^a)."""
    if d <= 1e-2 * max(H, abs(a), abs(b)):
        xg, wg = _GAUSS
        V = b + (xg + 1.0) / 2.0 * d
        return float(np.sum(wg * V ** 2 / (H * H + V * V) ** 1.5) * d / 2.0)
    return _asinh_diff(a, b, d, H) - a / math.hypot(H, a) + b / math.hypot(H, b)


def _int_T(H: float, a: float, b: float, d: float) -> float:
    """int_b^a sqrt(H^2 + V^2) dV  (= 1/2 [V T + H^2 asinh(V/H)]_b^a)."""
    if H <= 0:
        return 0.5 * (a * abs(a) - b * abs(b))
    if d <= 1e-2 * max(H, abs(a), abs(b)):
        xg, wg = _GAUSS
        V = b + (xg + 1.0) / 2.0 * d
        return float(np.sum(wg * np.hypot(H, V)) * d / 2.0)
    Ta = math.hypot(H, a)
    Tb = math.hypot(H, b)
    return 0.5 * (a * Ta - b * Tb + H * H * _asinh_diff(a, b, d, H))


def _seil_xz(H: float, V0: float, q: float, EA: float, s: float):
    """Lage (x, z) des Seilpunkts mit ungedehnter Bogenlaenge s."""
    a = V0 + q * s
    b = V0
    d = q * s
    z = (V0 * s + 0.5 * q * s * s) / EA + _hyp_diff(a, b, d, H) / q
    if H <= 0:
        return 0.0, z
    x = H * s / EA + H / q * _asinh_diff(a, b, d, H)
    return x, z


def _seil_jacobi(H: float, V0: float, q: float, EA: float, L0: float) -> np.ndarray:
    """d(x, z)(L0) / d(H, V0), symmetrisch."""
    a = V0 + q * L0
    b = V0
    d = q * L0
    Ta = math.hypot(H, a)
    Tb = math.hypot(H, b)
    Jxx = L0 / EA + _int_V2_T3(H, a, b, d) / q
    # H/q (1/Ta - 1/Tb) = H/q (Tb - Ta)/(Ta Tb)
    Jxz = -H / q * _hyp_diff(a, b, d, H) / (Ta * Tb)
    # a/Ta - b/Tb ohne Ausloeschung
    if a * b > 0:
        sab = H * H * d * (a + b) / ((a * Tb + b * Ta) * Ta * Tb)
    else:
        sab = a / Ta - b / Tb
    Jzz = L0 / EA + sab / q
    return np.array([[Jxx, Jxz], [Jxz, Jzz]])


def _seil_newton(l: float, h: float, L0: float, EA: float, q: float):
    """H, V0 aus x(L0) = l, z(L0) = h. Rueckgabe (H, V0, iterationen)."""
    c = math.hypot(l, h)
    tol = 1e-11 * max(c, L0)
    # Startwerte: straffes Seil -> Zugstab; sonst Parabel
    if L0 < c:
        T0 = EA * (c - L0) / L0
        H = max(T0 * l / c, 0.05 * q * l, 1e-6 * q * L0)
        V0 = T0 * h / c - 0.5 * q * L0
    else:
        f = c * math.sqrt(3.0 * (L0 / c - 1.0) / 8.0)
        f = max(f, 1e-6 * c)
        H = max(q * L0 * l / (8.0 * f), 1e-6 * q * L0)
        V0 = H * h / l - 0.5 * q * L0

    def resid(H_, V_):
        x, z = _seil_xz(H_, V_, q, EA, L0)
        return np.array([x - l, z - h])

    r = resid(H, V0)
    nr = float(np.linalg.norm(r))
    ok = nr <= tol
    it = 0
    while not ok and it < 100:
        it += 1
        J = _seil_jacobi(H, V0, q, EA, L0)
        try:
            dHV = np.linalg.solve(J, -r)
        except np.linalg.LinAlgError:
            break
        alpha = 1.0
        akzeptiert = False
        while alpha > 1e-8:
            Hn = H + alpha * dHV[0]
            Vn = V0 + alpha * dHV[1]
            if Hn > 0:
                rn = resid(Hn, Vn)
                nrn = float(np.linalg.norm(rn))
                if nrn < nr or nrn <= tol:
                    H, V0, r, nr = Hn, Vn, rn, nrn
                    akzeptiert = True
                    break
            alpha *= 0.5
        if not akzeptiert:
            break
        ok = nr <= tol
    if ok:
        return H, V0, it

    # Rueckfall: geschachtelte Intervallhalbierung (monoton in V0 und H)
    Vlim = q * L0 + 2.0 * EA * (abs(h) + L0) / L0 + 1.0

    def v0_von_h(H_):
        return brentq(lambda V_: _seil_xz(H_, V_, q, EA, L0)[1] - h, -Vlim, Vlim,
                      xtol=1e-14 * Vlim, rtol=1e-15, maxiter=500)

    def gx(H_):
        return _seil_xz(H_, v0_von_h(H_), q, EA, L0)[0] - l

    Hmax = 2.0 * EA * (l + L0) / L0 + q * (l + L0) + 1.0
    Hmin = 1e-300
    H = brentq(gx, Hmin, Hmax, xtol=1e-16 * Hmax, rtol=1e-15, maxiter=1000)
    V0 = v0_von_h(H)
    return H, V0, it + 1000


def _seil_vertikal(h: float, L0: float, EA: float, q: float):
    """Senkrecht haengendes Seil (l = 0, H = 0): V0 aus z(L0) = h.
    z ist stueckweise linear und streng monoton in V0."""
    k = q * L0 * L0 / (2.0 * EA)
    V0 = (h - L0 - k) * EA / L0                     # Seil straff, Zug nach oben
    if V0 >= 0:
        return V0
    V0 = (h + L0 - k) * EA / L0                     # Seil straff, Zug nach unten
    if V0 <= -q * L0:
        return V0
    return (h - L0 - k) / (L0 / EA + 2.0 / q)       # Schlaufe, Tiefpunkt im Seil


def seil_kettenlinie(P1, P2, L0: float, EA: float, w, k_min: float = 0.0):
    """Seilelement als elastische Kettenlinie.

    P1, P2 (3,) Endpunkte in der aktuellen Lage, L0 ungedehnte Laenge,
    EA Dehnsteifigkeit, w (3,) Streckenlast [N/m] je ungedehnter Laenge
    (z. B. Eigengewicht [0, 0, -q]).

    Rueckgabe (f_int (6,), Kt (6,6), info):
      f_int = innere Knotenkraefte im Sinne der Newton-Iteration, d. h. die
              Kraefte, die die Knoten aufbringen muessen, um das Seil in dieser
              Lage zu halten: f_int = -[F_auf_Knoten1, F_auf_Knoten2];
              Summe f_int = -w L0.
      Kt    = d f_int / d[u1, u2], symmetrisch, Form [[Kc, -Kc], [-Kc, Kc]].
      info  = dict(H, Tmax, Tmin, Durchhang, L, V1, V2, schlaff, iterationen)
              H = Horizontalzug, Durchhang = groesster Abstand von der Sehne,
              L = gedehnte Laenge, V1/V2 = Vertikalkomponenten des Seilzugs an
              den Enden (positiv in Richtung -w).

    Sonderfaelle: w = 0 -> gerader Zugstab (bei L < L0 kraftlos, f_int = 0 und
    Kt = k_min EA/L0 in Sehnenrichtung als optionale Stabilisierung, Vorgabe 0);
    Sehne parallel zu w -> senkrecht haengend (H = 0, Loesung geschlossen);
    straffes Seil -> Kt geht in den Zugstab EA/L0 ueber.
    """
    P1 = np.asarray(P1, float)
    P2 = np.asarray(P2, float)
    w = np.asarray(w, float)
    e_x, e_up, e_y, l, h, c, q = _seil_ebene(P1, P2, w)
    f_int = np.zeros(6)
    Kt = np.zeros((6, 6))
    info = {"H": 0.0, "Tmax": 0.0, "Tmin": 0.0, "Durchhang": 0.0, "L": c,
            "V1": 0.0, "V2": 0.0, "schlaff": False, "iterationen": 0}

    def _zusammen(Kc):
        Kt[:3, :3] = Kc
        Kt[3:, 3:] = Kc
        Kt[:3, 3:] = -Kc
        Kt[3:, :3] = -Kc

    # ---- ohne Streckenlast: gerades Seil ------------------------------
    if q <= 0:
        if c <= 0:
            return f_int, Kt, info
        e = (P2 - P1) / c
        if c <= L0:                                  # schlaff, kraftlos
            info["schlaff"] = True
            _zusammen(k_min * EA / L0 * np.outer(e, e))
            return f_int, Kt, info
        T = EA * (c - L0) / L0
        f_int[:3] = -T * e
        f_int[3:] = T * e
        Kc = EA / L0 * np.outer(e, e) + T / c * (np.eye(3) - np.outer(e, e))
        _zusammen(Kc)
        info.update(H=0.0, Tmax=T, Tmin=T, L=c)
        return f_int, Kt, info

    # ---- senkrecht haengend --------------------------------------------
    if l <= 0:
        V0 = _seil_vertikal(h, L0, EA, q)
        V2 = V0 + q * L0
        f_int[:3] = -V0 * e_up
        f_int[3:] = V2 * e_up
        sa, sb = math.copysign(1.0, V2), math.copysign(1.0, V0)
        k_ax = 1.0 / (L0 / EA + (sa - sb) / q)
        if V0 * V2 > 0:
            k_lat = 1.0 / (L0 / EA + abs(math.log(abs(V2) / abs(V0))) / q)
        else:
            k_lat = 0.0                              # Schlaufe: seitlich kraftlos
        Pn = np.outer(e_up, e_up)
        _zusammen(k_ax * Pn + k_lat * (np.eye(3) - Pn))
        L = L0 + _int_T(0.0, V2, V0, q * L0) / (EA * q)
        info.update(H=0.0, Tmax=max(abs(V0), abs(V2)),
                    Tmin=0.0 if V0 * V2 <= 0 else min(abs(V0), abs(V2)),
                    Durchhang=0.0, L=L, V1=V0, V2=V2)
        return f_int, Kt, info

    # ---- allgemeiner Fall ----------------------------------------------
    H, V0, it = _seil_newton(l, h, L0, EA, q)
    V2 = V0 + q * L0
    f_int[:3] = -(H * e_x + V0 * e_up)
    f_int[3:] = H * e_x + V2 * e_up
    J = _seil_jacobi(H, V0, q, EA, L0)
    Kf = np.linalg.inv(J)
    R = np.vstack([e_x, e_up])
    Kc = R.T @ Kf @ R + H / l * np.outer(e_y, e_y)
    Kc = 0.5 * (Kc + Kc.T)
    _zusammen(Kc)

    T1 = math.hypot(H, V0)
    T2 = math.hypot(H, V2)
    Tmin = H if V0 < 0 < V2 else min(T1, T2)
    # Durchhang: Tangente parallel zur Sehne bei V = H h/l
    s_star = min(max((H * h / l - V0) / q, 0.0), L0)
    xs, zs = _seil_xz(H, V0, q, EA, s_star)
    f_sag = abs(xs * h - zs * l) / c
    L = L0 + _int_T(H, V2, V0, q * L0) / (EA * q)
    info.update(H=H, Tmax=max(T1, T2), Tmin=Tmin, Durchhang=f_sag, L=L,
                V1=V0, V2=V2, iterationen=it)
    return f_int, Kt, info


def seil_form(P1, P2, L0: float, EA: float, w, n: int = 20) -> np.ndarray:
    """n Punkte (n,3) entlang des Seils (gleichmaessig in der ungedehnten
    Bogenlaenge), zum Zeichnen."""
    P1 = np.asarray(P1, float)
    P2 = np.asarray(P2, float)
    n = max(int(n), 2)
    e_x, e_up, e_y, l, h, c, q = _seil_ebene(P1, P2, w)
    t = np.linspace(0.0, 1.0, n)
    if q <= 0:
        return P1[None, :] + t[:, None] * (P2 - P1)[None, :]
    _f, _K, info = seil_kettenlinie(P1, P2, L0, EA, w)
    H, V0 = info["H"], info["V1"]
    pts = np.empty((n, 3))
    for i, ti in enumerate(t):
        x, z = _seil_xz(H, V0, q, EA, ti * L0)
        pts[i] = P1 + x * e_x + z * e_up
    return pts


def seil_laenge_aus_horizontalzug(P1, P2, EA: float, w, H: float) -> float:
    """Ungedehnte Laenge L0, bei der sich der Horizontalzug H einstellt."""
    e_x, e_up, e_y, l, h, c, q = _seil_ebene(P1, P2, w)
    if H <= 0:
        raise ValueError("Horizontalzug muss positiv sein")
    if q <= 0:                                        # gerader Zugstab
        if l <= 0:
            raise ValueError("Ohne Streckenlast und ohne Horizontalanteil nicht bestimmbar")
        T = H * c / l
        return c / (1.0 + T / EA)
    if l <= 0:
        raise ValueError("Senkrecht haengendes Seil hat keinen Horizontalzug")
    # dehnstarre Kettenlinie als Obergrenze (Dehnung vergroessert den Durchhang)
    Lc = math.hypot(h, 2.0 * H / q * math.sinh(q * l / (2.0 * H)))

    def g(L0):
        return seil_kettenlinie(P1, P2, L0, EA, w)[2]["H"] - H

    hi = Lc
    if g(hi) > 0:
        hi = Lc * 1.001
        while g(hi) > 0:
            hi *= 1.01
    lo = Lc * (1.0 - 2.0 * math.hypot(H, q * Lc) / EA) - 1e-9 * Lc
    lo = min(lo, hi * (1 - 1e-9))
    while g(lo) < 0:
        lo *= 0.9
        if lo < 1e-6 * c:
            raise ValueError("Kein L0 zum Horizontalzug gefunden")
    return float(brentq(g, lo, hi, xtol=1e-14 * c, rtol=1e-15, maxiter=500))


def seil_laenge_aus_durchhang(P1, P2, EA: float, w, f: float) -> float:
    """Ungedehnte Laenge L0 zum Durchhang f (groesster Abstand von der Sehne)."""
    e_x, e_up, e_y, l, h, c, q = _seil_ebene(P1, P2, w)
    if q <= 0 or l <= 0:
        raise ValueError("Durchhang nur mit Streckenlast und Horizontalanteil definiert")
    if f <= 0:
        raise ValueError("Durchhang muss positiv sein")

    def g(L0):
        return seil_kettenlinie(P1, P2, L0, EA, w)[2]["Durchhang"] - f

    hi = math.hypot(c, f) + f            # laenger als jede Kurve mit Abstand f
    lo = c
    while g(lo) > 0:
        lo *= 0.9
        if lo < 1e-6 * c:
            raise ValueError("Kein L0 zum Durchhang gefunden")
    return float(brentq(g, lo, hi, xtol=1e-14 * c, rtol=1e-15, maxiter=500))


# ==========================================================================
# Starre Koerper RBE2 / RBE3
# ==========================================================================
def starrkoerper_matrix(P_m, P_s, art: str = "RBE2", gewichte=None) -> np.ndarray:
    """Zwangsbedingungen G fuer einen starren Koerper, G u = 0 mit
    u = [u_m (6), u_s1 (6), u_s2 (6), ...] (Master zuerst, dann Slaves).

    art "RBE2": je Slave 6 Zeilen
        u_s - u_m - theta_m x r_s = 0,   theta_s - theta_m = 0,   r_s = P_s - P_m
    art "RBE3": 6 Zeilen, gewichtete kleinste Quadrate der Starrkoerperbewegung
        sum w_i (u_i - u_m - theta_m x r_i) = 0
        sum w_i r_i x (u_i - u_m - theta_m x r_i) = 0
      (nur Verschiebungen der Slaves; der Master folgt den Slaves).
    gewichte (n,) nur fuer RBE3, Vorgabe 1.
    """
    P_m = np.asarray(P_m, float)
    P_s = np.atleast_2d(np.asarray(P_s, float))
    n = P_s.shape[0]
    art = art.upper()
    I3 = np.eye(3)
    if art == "RBE2":
        G = np.zeros((6 * n, 6 * (n + 1)))
        for i in range(n):
            r = P_s[i] - P_m
            z = 6 * i
            cs = 6 * (i + 1)
            # -theta_m x r = +[r]x theta_m
            G[z:z + 3, 0:3] = -I3
            G[z:z + 3, 3:6] = bm._skew(r)
            G[z:z + 3, cs:cs + 3] = I3
            G[z + 3:z + 6, 3:6] = -I3
            G[z + 3:z + 6, cs + 3:cs + 6] = I3
        return G
    if art == "RBE3":
        wgt = np.ones(n) if gewichte is None else np.asarray(gewichte, float)
        if wgt.shape != (n,):
            raise ValueError("gewichte braucht einen Wert je Slave")
        G = np.zeros((6, 6 * (n + 1)))
        W = float(wgt.sum())
        Sr = np.zeros((3, 3))          # sum w_i [r_i]x
        Srr = np.zeros((3, 3))         # sum w_i [r_i]x [r_i]x
        for i in range(n):
            r = P_s[i] - P_m
            S = bm._skew(r)
            cs = 6 * (i + 1)
            G[0:3, cs:cs + 3] = wgt[i] * I3
            G[3:6, cs:cs + 3] = wgt[i] * S
            Sr += wgt[i] * S
            Srr += wgt[i] * S @ S
        G[0:3, 0:3] = -W * I3
        G[0:3, 3:6] = Sr
        G[3:6, 0:3] = -Sr
        G[3:6, 3:6] = Srr
        return G
    raise ValueError(f"Unbekannte Starrkoerperart {art!r} (RBE2 oder RBE3)")


def starrkoerper_steifigkeit(G, k: float) -> np.ndarray:
    """Strafsteifigkeit k G^T G zur Assemblierung auf die FHG [u_m, u_s1, ...]."""
    G = np.asarray(G, float)
    return k * (G.T @ G)


# ==========================================================================
# Grenzschichtelement (Interface ohne Dicke)
# ==========================================================================
def _grenzschicht_ansatz(k: int, xi: float, eta: float):
    """Ansatzfunktionen N (k,) und Ableitungen dN (k,2) fuer Dreieck (k = 3,
    Flaechenkoordinaten) oder Viereck (k = 4, bilinear auf [-1, 1]^2)."""
    if k == 3:
        N = np.array([1.0 - xi - eta, xi, eta])
        dN = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]])
    elif k == 4:
        N = 0.25 * np.array([(1 - xi) * (1 - eta), (1 + xi) * (1 - eta),
                             (1 + xi) * (1 + eta), (1 - xi) * (1 + eta)])
        dN = 0.25 * np.array([[-(1 - eta), -(1 - xi)], [(1 - eta), -(1 + xi)],
                              [(1 + eta), (1 + xi)], [-(1 + eta), (1 - xi)]])
    else:
        raise ValueError("Grenzschicht braucht 3 oder 4 Knoten je Seite")
    return N, dN


def _grenzschicht_gauss(k: int):
    if k == 3:
        return [(1 / 6, 1 / 6, 1 / 6), (2 / 3, 1 / 6, 1 / 6), (1 / 6, 2 / 3, 1 / 6)]
    g = 1.0 / math.sqrt(3.0)
    return [(-g, -g, 1.0), (g, -g, 1.0), (g, g, 1.0), (-g, g, 1.0)]


def _grenzschicht_lokal(Pm, dN):
    """Tangenten, Normale und Flaechenmass der Mittelflaeche am Punkt."""
    g1 = dN[:, 0] @ Pm
    g2 = dN[:, 1] @ Pm
    nv = np.cross(g1, g2)
    dA = float(np.linalg.norm(nv))
    if dA <= 0:
        raise ValueError("Entartete Grenzschichtflaeche")
    n = nv / dA
    t1 = g1 / np.linalg.norm(g1)
    t2 = np.cross(n, t1)
    return t1, t2, n, dA


def k_grenzschicht(P_u, P_o, kn: float, kt: float) -> np.ndarray:
    """Steifigkeitsmatrix (6k x 6k) eines Grenzschichtelements ohne Dicke mit
    k = 3 oder 4 Knoten je Seite. FHG nur Verschiebungen (3 je Knoten),
    Reihenfolge [unten 0..k-1, oben 0..k-1].

    Relativverschiebung Delta = N (u_o - u_u); K = int B^T (R^T C R) B dA mit
    B = [-N, +N], C = diag(kt, kt, kn) im Flaechensystem (t1, t2, n), n =
    Normale der Mittelflaeche (Rechtsschraube der unteren Knotenreihenfolge).
    Integration 2x2 Gauss (Viereck) bzw. 3-Punkt (Dreieck).
    """
    P_u = np.atleast_2d(np.asarray(P_u, float))
    P_o = np.atleast_2d(np.asarray(P_o, float))
    k = P_u.shape[0]
    if P_o.shape != P_u.shape:
        raise ValueError("Untere und obere Seite brauchen gleich viele Knoten")
    Pm = 0.5 * (P_u + P_o)
    K = np.zeros((6 * k, 6 * k))
    for xi, eta, wgt in _grenzschicht_gauss(k):
        N, dN = _grenzschicht_ansatz(k, xi, eta)
        t1, t2, n, dA = _grenzschicht_lokal(Pm, dN)
        D = kt * (np.outer(t1, t1) + np.outer(t2, t2)) + kn * np.outer(n, n)
        B = np.zeros((3, 6 * k))
        for a in range(k):
            B[:, 3 * a:3 * a + 3] = -N[a] * np.eye(3)
            B[:, 3 * (k + a):3 * (k + a) + 3] = N[a] * np.eye(3)
        K += wgt * dA * (B.T @ D @ B)
    return K


def grenzschicht_spannung(P_u, P_o, kn: float, kt: float, ue):
    """Spannungen (sn, st1, st2) in der Elementmitte aus den Knotenverschiebungen
    ue (6k,) [unten 0..k-1, oben 0..k-1]. Zug (Oeffnung in Richtung n) positiv;
    t1 = Richtung der ersten Elementkante (dP/dxi), t2 = n x t1."""
    P_u = np.atleast_2d(np.asarray(P_u, float))
    P_o = np.atleast_2d(np.asarray(P_o, float))
    ue = np.asarray(ue, float).reshape(-1)
    k = P_u.shape[0]
    if ue.shape != (6 * k,):
        raise ValueError("ue braucht 3 Verschiebungen je Knoten (6k Werte)")
    Pm = 0.5 * (P_u + P_o)
    xi, eta = (1 / 3, 1 / 3) if k == 3 else (0.0, 0.0)
    N, dN = _grenzschicht_ansatz(k, xi, eta)
    t1, t2, n, _dA = _grenzschicht_lokal(Pm, dN)
    uu = ue[:3 * k].reshape(k, 3)
    uo = ue[3 * k:].reshape(k, 3)
    delta = N @ (uo - uu)
    return float(kn * (n @ delta)), float(kt * (t1 @ delta)), float(kt * (t2 @ delta))
