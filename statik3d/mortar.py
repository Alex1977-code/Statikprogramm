"""Mortar-Gewichte fuer Kontaktpaare mit ungleichen Netzen (28.09.2026).

Die Knoten-gegen-Flaeche-Kopplung (contact._build_pair) projiziert jeden
Slave-Knoten auf ein Master-Dreieck (Vierecke geteilt) und verteilt seine
Kraft mit den Dreiecksgewichten. Bei ungleichen Netzen kommt ein
gleichmaessiger Druck damit nicht gleichmaessig an: Pruefmatrix K6 (zwei
Wuerfel, oben 3 x 3, unten 2 x 2 geteilt, p = 100 N/mm2) - an den unteren
Knoten 846 und 661 statt 625 cm2 Einflussflaeche an den Ecken, 2255 statt
2500 in der Mitte, unsymmetrisch laengs der Dreiecksdiagonalen; sigma_v
+74 N/mm2 mit hex8, -13,6 mit tet4.

Hier die duale Mortar-Kopplung (Wohlmuth 2000): je Slave-Knoten j

    w_ji = M_ji / D_j,   D_j = int N_j dA,   M_ji = int Phi_j N_i^m dA

ueber die Slave-Oberflaeche, Phi_j die dualen Formfunktionen der
Slave-Facetten (int_e Phi_j N_k = delta_jk int_e N_j je Facette e), N_i^m die
Formfunktionen der Master-Facetten an der Projektion. Die Bedingung des
Knotens bleibt eine Zeile n . (u_j - sum_i w_ji u_i) + g0 = 0. Warum das
genuegt: fuer einen gleichmaessigen Druck p ist die Kraft am Slave-Knoten
p D_j, und am Master-Knoten kommt sum_j p D_j w_ji = p int N_i^m an - genau
seine Einflussflaeche. Bei deckungsgleichen Netzen ist w_ji = delta_ji: die
Kopplung Knoten auf Knoten bleibt, wie sie war.

Am Rand der Ueberdeckung (30.09.2026): liegt eine Slave-Facette nur zum Teil
auf der Master-Flaeche, sind die dualen Integrale ueber den ueberdeckten Teil
wertlos - Phi_j ist abseits seines Knotens negativ, und ueber ein Teilstueck
integriert kippt die Summe. Gemessen am Gitter 3 x 3 auf [0, 1,2]^2 ueber
2 x 2 auf [0,1, 1,1]^2: auf den ueberdeckten Teil normiert (w = M_ji / sum_i
M_ji) bekaemen alle 16 Knoten negative Gewichte, an den Ecken -0,96 und
+2,56, und sum_i M_ji / D_j laege fuer die inneren Knoten bei 1,34, obwohl
ihr Einflussbereich nicht ganz ueberdeckt ist. Darum wird **je Facette**
entschieden (VOLL_TOL): eine ganz ueberdeckte Facette traegt die dualen
Integrale wie bisher, eine teilweise ueberdeckte die Standard-Formfunktionen
auf ihren Schnittstuecken (int_{e cap gamma} N_j N_i^m, int_{e cap gamma}
N_j - nichtnegativ), eine gar nicht ueberdeckte nichts. Beide Anteile bilden
auf jedem Stueck die Eins nach (sum_j Phi_j = sum_j N_j = 1), darum kommt ein
gleichmaessiger Druck p mit der konsistenten Knotenlast p D_j auch am Rand
genau als p int_gamma N_i^m am Master-Knoten an; bei voller Ueberdeckung
sind es die bisherigen dualen Gewichte. Eine mehr als einmal ueberdeckte
Facette (zwei Master-Lagen) gilt als fehlerhaft: ihre Knoten behalten die
Projektion.

Nur Geometrie und Integration, kein Zustand; contact.py setzt die Gewichte
ein. Facetten: Dreiecke (3 Knoten) und Vierecke (4 Knoten, bilinear).
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

#: Eine Slave-Facette gilt als ganz ueberdeckt, wenn die Summe ihrer
#: Schnittstuecke mit den Master-Facetten bis auf diesen Anteil ihrer Flaeche
#: reicht; darueber hinaus ist sie mehrfach ueberdeckt. Deckungsgleiche und
#: ineinander aufgehende Netze (K6) treffen die Flaeche auf 1e-15.
VOLL_TOL = 1e-6


class Gewicht(NamedTuple):
    """Mortar-Integrale eines Slave-Knotens: ``D`` der Nenner (int N_j ueber
    die ganz ueberdeckten Facetten plus int_{e cap gamma} N_j ueber die
    teilweise ueberdeckten), ``M`` je Master-Knoten der Zaehler, ``D_ganz``
    int N_j ueber alle Facetten (Ueberdeckung = D / D_ganz), ``rand``: eine
    Facette des Knotens liegt nur teilweise oder gar nicht auf dem Master,
    ``doppelt``: eine Facette ist mehr als einmal ueberdeckt."""
    D: float
    M: dict
    D_ganz: float
    rand: bool
    doppelt: bool

#: Dunavant, Grad 5, 7 Punkte: (a, b) baryzentrisch und Gewicht (Summe 1)
_DUN5 = np.array([
    [1 / 3, 1 / 3, 0.225],
    [0.059715871789770, 0.470142064105115, 0.132394152788506],
    [0.470142064105115, 0.059715871789770, 0.132394152788506],
    [0.470142064105115, 0.470142064105115, 0.132394152788506],
    [0.797426985353087, 0.101286507323456, 0.125939180544827],
    [0.101286507323456, 0.797426985353087, 0.125939180544827],
    [0.101286507323456, 0.101286507323456, 0.125939180544827],
])
#: 3 x 3 Gauss auf [-1, 1]^2
_G3 = np.array([-np.sqrt(0.6), 0.0, np.sqrt(0.6)])
_W3 = np.array([5 / 9, 8 / 9, 5 / 9])


def _flaeche2(poly: np.ndarray) -> float:
    """Vorzeichenbehaftete Flaeche eines ebenen Polygons (n, 2)."""
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _ccw(poly: np.ndarray) -> np.ndarray:
    return poly if _flaeche2(poly) >= 0 else poly[::-1]


def schneiden(subjekt: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Sutherland-Hodgman: ``subjekt`` (n, 2) geschnitten mit dem konvexen,
    gegen den Uhrzeigersinn umlaufenden ``clip`` (m, 2). Rueckgabe das
    Schnittpolygon (k, 2), leer wenn nichts ueberlappt."""
    aus = [np.asarray(p, float) for p in subjekt]
    m = len(clip)
    for i in range(m):
        if not aus:
            break
        a, b = clip[i], clip[(i + 1) % m]
        kante = b - a

        def innen(p):
            return kante[0] * (p[1] - a[1]) - kante[1] * (p[0] - a[0]) >= -1e-14 * (1.0 + np.dot(kante, kante))

        ein = aus
        aus = []
        for k in range(len(ein)):
            p, q = ein[k], ein[(k + 1) % len(ein)]
            pi, qi = innen(p), innen(q)
            if pi:
                aus.append(p)
            if pi != qi:
                d = q - p
                nenner = kante[0] * d[1] - kante[1] * d[0]
                if abs(nenner) > 0:
                    t = (kante[0] * (a[1] - p[1]) - kante[1] * (a[0] - p[0])) / nenner
                    aus.append(p + t * d)
    return np.array(aus, float) if len(aus) >= 3 else np.zeros((0, 2))


def _flaeche_py(poly) -> float:
    """Wie _flaeche2, fuer eine kleine Liste von (x, y) - ohne numpy (am
    Drehlager zehntausendfach je Paar; np.roll kostete die Haelfte der Zeit)."""
    s = 0.0
    n = len(poly)
    for k in range(n):
        x0, y0 = poly[k]
        x1, y1 = poly[(k + 1) % n]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def _schneiden_py(subjekt, clip):
    """Sutherland-Hodgman wie :func:`schneiden`, auf Listen von (x, y)."""
    aus = list(subjekt)
    m = len(clip)
    for i in range(m):
        if not aus:
            return []
        ax, ay = clip[i]
        bx, by = clip[(i + 1) % m]
        kx, ky = bx - ax, by - ay
        eps = -1e-14 * (1.0 + kx * kx + ky * ky)
        ein = aus
        aus = []
        n = len(ein)
        for k in range(n):
            px, py = ein[k]
            qx, qy = ein[(k + 1) % n]
            sp = kx * (py - ay) - ky * (px - ax)
            sq = kx * (qy - ay) - ky * (qx - ax)
            pi, qi = sp >= eps, sq >= eps
            if pi:
                aus.append((px, py))
            if pi != qi:
                dx, dy = qx - px, qy - py
                nenner = kx * dy - ky * dx
                if nenner != 0.0:
                    tt = (kx * (ay - py) - ky * (ax - px)) / nenner
                    aus.append((px + tt * dx, py + tt * dy))
    return aus if len(aus) >= 3 else []


def formfunktionen(poly: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Formfunktionen der ebenen Facette ``poly`` (3 oder 4 Ecken, 2D) an den
    Punkten ``x`` (k, 2): Dreieck baryzentrisch, Viereck bilinear (inverse
    Abbildung mit Newton). Rueckgabe (k, 3|4)."""
    x = np.atleast_2d(np.asarray(x, float))
    if len(poly) == 3:
        A, B, C = poly
        T = np.array([[B[0] - A[0], C[0] - A[0]], [B[1] - A[1], C[1] - A[1]]])
        lc = np.linalg.solve(T, (x - A).T).T          # (k, 2): Gewichte von B, C
        return np.column_stack([1.0 - lc[:, 0] - lc[:, 1], lc[:, 0], lc[:, 1]])
    P = poly
    xi = np.zeros((len(x), 2))
    for _ in range(25):
        r, s = xi[:, 0], xi[:, 1]
        N = 0.25 * np.column_stack([(1 - r) * (1 - s), (1 + r) * (1 - s), (1 + r) * (1 + s), (1 - r) * (1 + s)])
        dr = 0.25 * np.column_stack([-(1 - s), (1 - s), (1 + s), -(1 + s)])
        ds = 0.25 * np.column_stack([-(1 - r), -(1 + r), (1 + r), (1 - r)])
        F = N @ P - x
        J = np.stack([np.column_stack([dr @ P[:, 0], ds @ P[:, 0]]),
                      np.column_stack([dr @ P[:, 1], ds @ P[:, 1]])], axis=1)   # (k, 2, 2)
        dxi = np.linalg.solve(J, F[:, :, None])[:, :, 0]
        xi = xi - dxi
        if float(np.abs(dxi).max()) < 1e-13:
            break
    r, s = xi[:, 0], xi[:, 1]
    return 0.25 * np.column_stack([(1 - r) * (1 - s), (1 + r) * (1 - s), (1 + r) * (1 + s), (1 - r) * (1 + s)])


def facetten_integrale(poly: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(D_e, M_e) der ebenen Facette: D_e = int N, M_e = int N N^T."""
    if len(poly) == 3:
        a = abs(_flaeche2(poly))
        return np.full(3, a / 3.0), a / 12.0 * (np.ones((3, 3)) + np.eye(3))
    D = np.zeros(4)
    M = np.zeros((4, 4))
    for i, r in enumerate(_G3):
        for k, s in enumerate(_G3):
            N = 0.25 * np.array([(1 - r) * (1 - s), (1 + r) * (1 - s), (1 + r) * (1 + s), (1 - r) * (1 + s)])
            dr = 0.25 * np.array([-(1 - s), (1 - s), (1 + s), -(1 + s)])
            ds = 0.25 * np.array([-(1 - r), -(1 + r), (1 + r), (1 - r)])
            J = np.array([dr @ poly, ds @ poly])
            w = _W3[i] * _W3[k] * abs(float(np.linalg.det(J)))
            D += w * N
            M += w * np.outer(N, N)
    return D, M


def _ebene(P3: np.ndarray):
    """Mittelpunkt, Normale und zwei Achsen der (naeherungsweise) ebenen Facette."""
    c = P3.mean(axis=0)
    if len(P3) == 3:
        n = np.cross(P3[1] - P3[0], P3[2] - P3[0])
    else:
        n = np.cross(P3[2] - P3[0], P3[3] - P3[1])
    ln = float(np.linalg.norm(n))
    if ln <= 0:
        return None
    n = n / ln
    e1 = P3[1] - P3[0]
    e1 = e1 - (e1 @ n) * n
    e1 = e1 / float(np.linalg.norm(e1))
    e2 = np.cross(n, e1)
    return c, n, e1, e2


def _ebenen(Ps: list) -> tuple:
    """Mittelpunkte und Einheitsnormalen vieler Facetten auf einmal (Dreiecke:
    Kreuzprodukt zweier Kanten, Vierecke: der Diagonalen); entartete: 0."""
    if not Ps:
        return np.zeros((0, 3)), np.zeros((0, 3))
    C = np.array([P.mean(axis=0) for P in Ps])
    a = np.array([P[2] - P[0] if len(P) == 4 else P[1] - P[0] for P in Ps])
    b = np.array([P[3] - P[1] if len(P) == 4 else P[2] - P[0] for P in Ps])
    N = np.cross(a, b)
    ln = np.linalg.norm(N, axis=1)
    N = np.where(ln[:, None] > 0, N / np.where(ln > 0, ln, 1.0)[:, None], 0.0)
    return C, N


def gewichte(knoten: np.ndarray, slave_facetten: list, master_facetten: list,
             suchradius: float, slave_innen: dict = None, master_innen: dict = None) -> dict:
    """Duale Mortar-Gewichte je Slave-Knoten.

    ``knoten`` (nn, 3) Koordinaten; Facetten als Tupel von Knotennummern (3
    oder 4). ``slave_innen``/``master_innen``: je Facette (sortiertes
    Knotentupel) ein Punkt im Inneren ihres Koerpers (Elementschwerpunkt) -
    dann zaehlen nur Master-Facetten, die der Slave-Facette zugewandt sind
    (Aussennormalen entgegengesetzt). Ohne sie haette eine duenne
    Master-Platte zwei Seiten im Suchradius, und die Ueberdeckung waere 2.
    Rueckgabe {slave_knoten: Gewicht}; die Gewichte sind M_ji / D_j, ihre
    Summe ist 1, wenn keine Facette des Knotens mehrfach ueberdeckt ist."""
    from scipy.spatial import cKDTree
    if not slave_facetten or not master_facetten:
        return {}
    mf = [tuple(int(x) for x in f) for f in master_facetten if len(f) in (3, 4)]
    MP = [knoten[list(f)] for f in mf]
    MC, MN = _ebenen(MP)
    MR = np.array([float(np.sqrt(((P - P.mean(axis=0)) ** 2).sum(1).max())) for P in MP])
    # Aussennormalen der Master-Facetten (0, wenn kein Innenpunkt bekannt)
    MA = np.zeros_like(MN)
    if master_innen:
        for k, f in enumerate(mf):
            q = master_innen.get(tuple(sorted(f)))
            if q is not None:
                MA[k] = MN[k] if float(MN[k] @ (MC[k] - q)) >= 0 else -MN[k]
    baum = cKDTree(MC)
    rmax = float(MR.max()) if len(MR) else 0.0
    sf = [tuple(int(x) for x in f) for f in slave_facetten if len(f) in (3, 4)]
    SP = [knoten[list(f)] for f in sf]
    SC, SN = _ebenen(SP)
    SR = np.array([float(np.sqrt(((P - c_) ** 2).sum(1).max())) for P, c_ in zip(SP, SC)])
    # alle Baumabfragen auf einmal (je Facette ihr eigener Radius)
    alle_kand = baum.query_ball_point(SC, SR + rmax + suchradius) if len(sf) else []
    D: dict = {}
    M: dict = {}
    D_ganz: dict = {}
    rand: set = set()
    doppelt: set = set()
    for si, f in enumerate(sf):
        n = SN[si]
        if not np.any(n):
            continue
        c = SC[si]
        P3 = SP[si]
        e1 = P3[1] - P3[0]
        e1 = e1 - (e1 @ n) * n
        e1 = e1 / float(np.linalg.norm(e1))
        e2 = np.array([n[1] * e1[2] - n[2] * e1[1], n[2] * e1[0] - n[0] * e1[2], n[0] * e1[1] - n[1] * e1[0]])
        n_aussen = None
        if slave_innen:
            q = slave_innen.get(tuple(sorted(f)))
            if q is not None:
                n_aussen = n if float(n @ (c - q)) >= 0 else -n
        P2 = np.column_stack([(P3 - c) @ e1, (P3 - c) @ e2])
        if _flaeche2(P2) < 0:                     # gegen den Uhrzeigersinn umlaufen
            ordnung = list(range(len(f)))[::-1]
            f = tuple(f[i] for i in ordnung)
            P3, P2 = P3[ordnung], P2[ordnung]
        De, Me = facetten_integrale(P2)
        Ae = np.diag(De) @ np.linalg.inv(Me)      # duale Formfunktionen Phi = Ae N
        for j, dj in zip(f, De):
            D_ganz[j] = D_ganz.get(j, 0.0) + float(dj)
        re = float(SR[si])
        kand = np.asarray(alle_kand[si], dtype=int)
        if not kand.size:
            rand.update(f)                        # nichts gegenueber: unueberdeckt
            continue
        # gebuendelt vorfiltern: gegenueber (Normalen hoechstens 60 Grad
        # auseinander), im Suchradius laengs der Normalen, und in der Ebene
        # nahe genug, dass sich die Umkreise ueberlappen
        dC = MC[kand] - c
        laengs = dC @ n
        quer = np.linalg.norm(dC - laengs[:, None] * n, axis=1)
        ok = ((np.abs(MN[kand] @ n) >= 0.5) & (np.abs(laengs) <= suchradius + MR[kand])
              & (quer <= re + MR[kand]))
        if n_aussen is not None:
            # zugewandt: Aussennormalen entgegengesetzt; Facetten ohne bekannte
            # Aussenseite (Schalen) bleiben
            gegen = MA[kand] @ n_aussen
            ok &= (gegen <= -0.5) | (np.abs(MA[kand]).sum(1) == 0)
        P2l = [(float(x), float(y)) for x, y in P2]
        sx = [q[0] for q in P2l]
        sy = [q[1] for q in P2l]
        sxmin, sxmax, symin, symax = min(sx), max(sx), min(sy), max(sy)
        a_e = abs(_flaeche_py(P2l))
        E = np.column_stack([e1, e2])
        pts, wts, stuecke = [], [], []          # stuecke: (Q2c, Master-Knoten, von, bis)
        a_ueb = 0.0                             # ueberdeckte Flaeche, exakt aus den Polygonen
        for fi in kand[ok]:
            Q2 = (MP[fi] - c) @ E
            ql = [(float(x), float(y)) for x, y in Q2]
            qx = [q[0] for q in ql]
            qy = [q[1] for q in ql]
            if min(qx) > sxmax or max(qx) < sxmin or min(qy) > symax or max(qy) < symin:
                continue                               # Umrissboxen getrennt
            aq = _flaeche_py(ql)
            if aq == 0.0:
                continue
            q_ord = list(range(len(mf[fi])))
            if aq < 0:
                q_ord = q_ord[::-1]
                ql = ql[::-1]
            poly = _schneiden_py(P2l, ql)
            if len(poly) < 3 or abs(_flaeche_py(poly)) <= 1e-14 * a_e:
                continue
            a_ueb += abs(_flaeche_py(poly))
            von = len(pts)
            ax, ay = poly[0]
            for k in range(1, len(poly) - 1):
                bx, by = poly[k]
                cx, cy = poly[k + 1]
                ak = 0.5 * abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay))
                for l1, l2, w in _DUN5:
                    pts.append((ax + l1 * (bx - ax) + l2 * (cx - ax), ay + l1 * (by - ay) + l2 * (cy - ay)))
                    wts.append(w * ak)
            stuecke.append((np.array(ql), [mf[fi][i] for i in q_ord], von, len(pts)))
        if a_ueb > (1.0 + VOLL_TOL) * a_e:
            doppelt.update(f)                     # zwei Master-Lagen: kein Gewicht
            continue
        voll = abs(a_ueb - a_e) <= VOLL_TOL * a_e
        if not voll:
            rand.update(f)
        if not stuecke:
            continue
        pts_a = np.array(pts)
        wts_a = np.array(wts)
        Ns = formfunktionen(P2, pts_a)                  # (k, ns), einmal je Slave-Facette
        if voll:
            Phi = Ns @ Ae.T                             # dual: int_e Phi_j N_k = delta_jk int_e N_j
            for j, dj in zip(f, De):
                D[j] = D.get(j, 0.0) + float(dj)
        else:
            # teilweise ueberdeckt: Standard-Formfunktionen auf den Stuecken -
            # nichtnegativ, und sum_i M_ji = int_{e cap gamma} N_j genau
            Phi = Ns
            for a_, j in enumerate(f):
                D[j] = D.get(j, 0.0) + float(Ns[:, a_] @ wts_a)
        for Q2c, mknoten, von, bis in stuecke:
            Nm = formfunktionen(Q2c, pts_a[von:bis])
            I = (Phi[von:bis] * wts_a[von:bis, None]).T @ Nm
            for a_, j in enumerate(f):
                zeile = M.setdefault(j, {})
                for b_, i in enumerate(mknoten):
                    zeile[i] = zeile.get(i, 0.0) + float(I[a_, b_])
    return {j: Gewicht(D.get(j, 0.0), M.get(j, {}), D_ganz[j], j in rand, j in doppelt)
            for j in D_ganz}
