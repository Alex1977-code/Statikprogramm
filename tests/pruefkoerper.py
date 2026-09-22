"""
Pruefkoerper fuer die Elementmessungen: Netze, Lasten, Sollwerte, Auswertung.

Kein Testlauf fuer sich (steht nicht in tests.run_all) - die Suiten und die
Messskripte (tests/messung_*.py) bauen ihre Koerper hier, damit alle mit
denselben Netzen und derselben Auswertung rechnen.

Das Mass des Auftrags vom 22.09.2026 ist die **Vergleichsspannung an einer
glatten Nachweisstelle**, auf 1 N/mm2 gegen die Referenz. Weil die Rechnung
linear ist, haengt ein absoluter Fehler an der Lasthoehe; darum wird jede
Messung auf ``SIGMA_BEZUG`` = 355 N/mm2 an der Nachweisstelle skaliert.
1 N/mm2 heisst dann 1/355 = 0,28 % relativ.

Netze
-----
Alle Quadernetze stehen auf **demselben Knotengitter** (nx+1)(ny+1)(nz+1),
damit gleiche Gitter gleiche Freiheitsgrade haben:

* ``hex8``  ein Sechsflaechner je Zelle
* ``tet4``  sechs Tetraeder je Zelle um die Raumdiagonale 0-7 (Kuhn). Diese
  Zerlegung ist bei gleicher Orientierung in jeder Zelle **konform**. Die
  Fuenferzerlegung aus ``mesher.grid_box`` ist es nicht (gemessen 22.09.2026:
  am 4x1x1-Quader gehoeren 48 Dreiecke nur einem Element, 36 waeren Rand) -
  darum baut dieses Modul seine Tetraeder selbst.
* ``tet10`` dieselben Kuhn-Tetraeder mit Kantenmitten (mehr Knoten!)
* ``pent6`` zwei Keile je Zelle, Dreiecke in der x-y-Ebene, Achse z
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                        # noqa: E402
from statik3d.elements import solid as sl                          # noqa: E402
from statik3d.model import Material, Model                         # noqa: E402

#: Bezugsspannung an der Nachweisstelle [Pa]: auf sie wird die Last skaliert
SIGMA_BEZUG = 355e6
#: Das Genauigkeitsziel des Anwenders (22.09.2026): 1 N/mm2
ZIEL = 1e6

E_ST, NU_ST = 210e9, 0.3

#: Kuhn-Zerlegung einer Zelle; Eckindex x = i + 2 j + 4 k
KUHN = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]
#: Zelle -> hex8-Knotenreihenfolge (unten 0-1-2-3 gegen den Uhrzeiger, oben 4-7)
HEX_AUS_ZELLE = [0, 1, 3, 2, 4, 5, 7, 6]
#: Kanten des tet10 in solid.tet10_N_dN-Reihenfolge
TET10_KANTEN = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]


# --------------------------------------------------------------------------
# Netze
# --------------------------------------------------------------------------
def quader(typ, nx, ny, nz, L, B, H, E=E_ST, nu=NU_ST, fy=None, knotendilatation=False,
           verzerrung=0.0, keim=3, form=None):
    """Quader [0,L] x [0,B] x [0,H] als Netz des Typs ``typ``.

    ``verzerrung`` verschiebt die **inneren** Gitterknoten zufaellig um
    diesen Bruchteil der kleinsten Zellweite (Randknoten bleiben, damit
    Lager und Last dieselben Stellen treffen). ``form(i, j, k, p) -> p``
    bildet die Gitterpunkte ab (Trapez, Parallelogramm, Verdrehung).
    Rueckgabe (Modell, ids) mit ids[(i, j, k)] = Knotennummer.
    """
    m = Model(f"{typ}_{nx}x{ny}x{nz}")
    m.add_material(Material("S", E=E, nu=nu, rho=7850.0, fy=fy))
    m.knotendilatation = bool(knotendilatation)
    rng = np.random.default_rng(keim)
    h = min(L / nx, B / ny, H / nz)
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                p = np.array([L * i / nx, B * j / ny, H * k / nz])
                if form is not None:
                    p = np.asarray(form(i, j, k, p), float)
                if verzerrung and 0 < i < nx and 0 < j < ny and 0 < k < nz:
                    p = p + rng.uniform(-1, 1, 3) * verzerrung * h
                ids[(i, j, k)] = m.add_node(*p)
    mitten = {}

    def mitte(a, b):
        key = (min(a, b), max(a, b))
        if key not in mitten:
            mitten[key] = m.add_node(*(0.5 * (m.nodes[a] + m.nodes[b])))
        return mitten[key]

    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                z = [ids[(i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1))] for x in range(8)]
                if typ == "hex8":
                    m.add_element("hex8", [z[x] for x in HEX_AUS_ZELLE], "S")
                elif typ in ("tet4", "tet10"):
                    for tet in KUHN:
                        kn = [z[x] for x in tet]
                        if _tet_volumen(m.nodes[kn]) < 0:
                            kn[1], kn[2] = kn[2], kn[1]
                        if typ == "tet10":
                            kn = kn + [mitte(kn[a], kn[b]) for a, b in TET10_KANTEN]
                        m.add_element(typ, kn, "S")
                elif typ == "pent6":
                    c = [z[x] for x in HEX_AUS_ZELLE]
                    m.add_element("pent6", [c[0], c[1], c[2], c[4], c[5], c[6]], "S")
                    m.add_element("pent6", [c[0], c[2], c[3], c[4], c[6], c[7]], "S")
                else:
                    raise ValueError(typ)
    return m, ids


def _tet_volumen(X):
    X = np.asarray(X, float)
    return float(np.linalg.det(np.array([X[1] - X[0], X[2] - X[0], X[3] - X[0]]))) / 6.0


def einfache_flaechen(model):
    """Zahl der Eckseiten, die zu genau einem Element gehoeren - bei einem
    konformen Quadernetz sind das genau die Randseiten."""
    from collections import Counter
    c = Counter()
    for e in model.elements:
        for f in sl.FLAECHEN_ECKEN[e.typ]:
            c[tuple(sorted(int(e.nodes[a]) for a in f))] += 1
    return sum(1 for v in c.values() if v == 1)


# --------------------------------------------------------------------------
# Lasten und Lager
# --------------------------------------------------------------------------
def randseiten(model, bedingung):
    """[(Element, Seitenknoten)] der Seiten, deren Knoten alle ``bedingung(x)``
    erfuellen (x: (k,3))."""
    aus = []
    for i, e in enumerate(model.elements):
        for f in sl.FLAECHEN[e.typ]:
            kn = [int(e.nodes[a]) for a in f]
            if bedingung(model.nodes[kn]):
                aus.append((i, kn))
    return aus


def schubkraft_auf_seiten(model, seiten, F, richtung):
    """Gleichmaessige Schubspannung mit der Resultierenden F in ``richtung``
    auf die Seiten verteilen - konsistent je Seitentyp (tri3, quad4, tri6):
    solid.flaechenlast_knoten mit p = 1 in ``richtung`` gibt die Knotenanteile
    einer Einheitsspannung, die Summe ist die Seitenflaeche."""
    anteile: dict = {}
    for _i, kn in seiten:
        fk = sl.flaechenlast_knoten(model.nodes[kn], 1.0, richtung)
        for a, n in enumerate(kn):
            anteile[n] = anteile.get(n, 0.0) + float(np.linalg.norm(fk[a]))
    A = sum(anteile.values())
    d = np.asarray(richtung, float) / np.linalg.norm(richtung)
    for n, w in anteile.items():
        f = F * w / A * d
        model.load_node(int(n), Fx=f[0], Fy=f[1], Fz=f[2])
    return A


def spannung_auf_seiten(model, seiten, t_von_x):
    """Konsistente Knotenkraefte einer ortsabhaengigen Randspannung
    t(x) (Vektor [N/m2]) auf die Seiten: f_a = Integral N_a t dA, mit der
    Gaussregel der Seite (solid._SEITEN_GAUSS). Fuer ein Endmoment ist t
    eine lineare Normalspannung M z / I."""
    kraefte: dict = {}
    for _i, kn in seiten:
        P = model.nodes[kn]
        k = len(kn)
        GP, W = sl._SEITEN_GAUSS[k]
        for (a, b), w in zip(GP, W):
            N, dN = sl.seite_N_dN(k, a, b)
            x = N @ P
            dA = float(np.linalg.norm(np.cross(dN[:, 0] @ P, dN[:, 1] @ P)))
            t = np.asarray(t_von_x(x), float)
            for j, n in enumerate(kn):
                kraefte[n] = kraefte.get(n, np.zeros(3)) + w * N[j] * dA * t
    for n, f in kraefte.items():
        model.load_node(int(n), Fx=f[0], Fy=f[1], Fz=f[2])
    return kraefte


def einspannen(model, bedingung):
    X = np.asarray(model.nodes, float)
    fest = [n for n in range(model.nn) if bedingung(X[n:n + 1])]
    for n in fest:
        model.fix(int(n), [0, 1, 2])
    return fest


# --------------------------------------------------------------------------
# Kragarm mit Endquerkraft
# --------------------------------------------------------------------------
class Kragarm:
    """Kragarm [0,L] x [0,B] x [0,H], bei x = 0 eingespannt, bei x = L eine
    Querkraft in -z als gleichmaessige Schubspannung auf der Stirnseite.

    Nachweisstelle: Oberkante, Mitte der Breite, x = L/2. Dort gilt nach
    Saint-Venant (Biegung mit Querkraft) exakt sigma_xx = M z / I mit
    M = F (L - x), und tau_xz = 0 (freie Oberflaeche), tau_xy = 0
    (Symmetrie der Breite): sigma_v = sigma_xx. Die Stoerungen der Enden
    (Einspannung mit Querdehnung, Lasteinleitung) klingen nach 2,5 Hoehen
    ab. Die Last wird so gewaehlt, dass dort SIGMA_BEZUG steht.
    """

    def __init__(self, L=1.0, B=0.1, H=0.2, sigma=SIGMA_BEZUG):
        self.L, self.B, self.H = L, B, H
        self.I = B * H ** 3 / 12.0
        self.x_nw = 0.5 * L
        self.F = sigma * self.I / ((L - self.x_nw) * 0.5 * H)
        self.sigma = sigma

    def punkt(self):
        return np.array([self.x_nw, 0.5 * self.B, self.H])

    def sigma_soll(self):
        return self.sigma

    def w_balken(self, E=E_ST, nu=NU_ST):
        """Endverschiebung nach Timoshenko (k = 5/6) - nur Anhalt; die
        3D-Loesung liegt wegen Einspannung und Querdehnung etwas darunter."""
        G = E / (2 * (1 + nu))
        return self.F * self.L ** 3 / (3 * E * self.I) + self.F * self.L / (5 / 6 * G * self.B * self.H)

    def modell(self, typ, nx, ny, nz, **kw):
        m, ids = quader(typ, nx, ny, nz, self.L, self.B, self.H, **kw)
        tol = 1e-9 * self.L
        einspannen(m, lambda X: bool(np.all(np.abs(X[:, 0]) < tol)))
        seiten = randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - self.L) < tol)))
        schubkraft_auf_seiten(m, seiten, self.F, (0.0, 0.0, -1.0))
        return m, ids


# --------------------------------------------------------------------------
# Hohlkugel unter Innendruck (Lame, exakt)
# --------------------------------------------------------------------------
class Hohlkugel:
    """Achtel einer Hohlkugel a <= r <= b unter Innendruck p, Symmetrie an
    x = 0, y = 0, z = 0. Geschlossene Loesung (Lame):

        sigma_rr = p a^3/(b^3 - a^3) (1 - b^3/r^3)
        sigma_tt = p a^3/(b^3 - a^3) (1 + b^3/(2 r^3))
        sigma_v  = 3/2 p a^3 b^3 / ((b^3 - a^3) r^3)

    Nachweisstelle ist die Innenflaeche (dort ist sigma_v am groessten, und
    sie ist glatt). p wird so gewaehlt, dass dort SIGMA_BEZUG steht.

    Netz: die Kugelflaeche des Achtels in drei Vierecksfelder geteilt (je
    eine Koordinate ist die groesste, "gewuerfelte Kugel"), winkeltreu
    geteilt, n_t Teile je Feldkante, n_r Lagen radial. Sechsflaechner oder
    Kuhn-Tetraeder; beim tet10 liegen die Kantenmitten der Kugelflaechen
    **auf** der Kugel (gekruemmte Elemente).
    """

    def __init__(self, a=0.1, b=0.2, sigma=SIGMA_BEZUG):
        self.a, self.b = a, b
        self.c = a ** 3 / (b ** 3 - a ** 3)
        self.p = sigma / (1.5 * self.c * b ** 3 / a ** 3)
        self.sigma = sigma

    def sv(self, r):
        return 1.5 * self.p * self.c * self.b ** 3 / r ** 3

    def modell(self, typ, n_t, n_r, E=E_ST, nu=NU_ST, stufung=1.0):
        a, b = self.a, self.b
        m = Model(f"Hohlkugel_{typ}_{n_t}x{n_r}")
        m.add_material(Material("S", E=E, nu=nu, rho=0.0))
        knoten: dict = {}

        def knoten_bei(p):
            key = tuple(np.round(p, 10))
            if key not in knoten:
                knoten[key] = m.add_node(*p)
            return knoten[key]

        def richtung(feld, i, j):
            u = np.tan(0.25 * np.pi * i / n_t)
            v = np.tan(0.25 * np.pi * j / n_t)
            d = {0: (1.0, u, v), 1: (v, 1.0, u), 2: (u, v, 1.0)}[feld]
            d = np.array(d)
            return d / np.linalg.norm(d)
        mitten = {}

        def mitte(p, q):
            key = (min(p, q), max(p, q))
            if key not in mitten:
                X = 0.5 * (m.nodes[p] + m.nodes[q])
                ra, rb = np.linalg.norm(m.nodes[p]), np.linalg.norm(m.nodes[q])
                # Kante auf einer Kugelflaeche: Mitte auf die Kugel
                if abs(ra - rb) < 1e-12 * b:
                    X = X / np.linalg.norm(X) * ra
                mitten[key] = m.add_node(*X)
            return mitten[key]

        for feld in range(3):
            for k in range(n_r):
                for j in range(n_t):
                    for i in range(n_t):
                        z = []
                        for x in range(8):
                            ii, jj, kk = i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1)
                            r = a + (b - a) * (kk / n_r) ** stufung
                            z.append(knoten_bei(r * richtung(feld, ii, jj)))
                        if typ == "hex8":
                            kn = [z[x] for x in HEX_AUS_ZELLE]
                            from statik3d.elements import solid as _sl
                            if _sl.jacobi_volumen("hex8", m.nodes[kn])["V"] < 0:
                                kn = kn[4:] + kn[:4]
                            m.add_element("hex8", kn, "S")
                            continue
                        for tet in KUHN:
                            kn = [z[x] for x in tet]
                            if _tet_volumen(m.nodes[kn]) < 0:
                                kn[1], kn[2] = kn[2], kn[1]
                            if typ == "tet10":
                                kn = kn + [mitte(kn[p], kn[q]) for p, q in TET10_KANTEN]
                            m.add_element(typ, kn, "S")
        X = np.asarray(m.nodes, float)
        tol = 1e-9 * b
        for n in range(m.nn):
            dofs = [d for d in range(3) if abs(X[n, d]) < tol]
            if dofs:
                m.fix(int(n), dofs)
        innen = randseiten(m, lambda P: bool(np.all(np.abs(np.linalg.norm(P, axis=1) - a) < 1e-9 * b)))
        spannung_auf_seiten(m, innen, lambda x: self.p * x / np.linalg.norm(x))
        return m

    def nachweisknoten(self, m):
        """Knoten der Innenflaeche (r = a) - Eckknoten der Elemente."""
        X = np.asarray(m.nodes, float)
        r = np.linalg.norm(X, axis=1)
        from statik3d.elements import solid as _sl
        ecken = {int(n) for e in m.elements for n in e.nodes[:len(_sl.ECKEN_NATUERLICH[e.typ])]}
        return [n for n in range(m.nn) if abs(r[n] - self.a) < 1e-9 * self.b and n in ecken]


class Hohlzylinder:
    """Viertel eines dickwandigen Rohres a <= r <= b unter Innendruck p,
    ebener Dehnungszustand (u_z = 0 an beiden Stirnen), Symmetrie an x = 0
    und y = 0 - der Pruefkoerper von MacNeal/Harder (1985) fuer nahezu
    inkompressiblen Werkstoff. Geschlossene Loesung (Lame, ebene Dehnung):

        u_r      = (1 + nu)/E ((1 - 2 nu) A r + B / r)
        sigma_rr = A - B/r^2,  sigma_tt = A + B/r^2,  sigma_zz = 2 nu A
        A = p a^2/(b^2 - a^2),  B = p a^2 b^2/(b^2 - a^2)

    Netz: polar, n_t Teile ueber 90 Grad, n_r radial, eine Lage der Hoehe h."""

    def __init__(self, a=0.1, b=0.2, h=0.02, p=100e6):
        self.a, self.b, self.h, self.p = a, b, h, p
        self.A = p * a * a / (b * b - a * a)
        self.B = p * a * a * b * b / (b * b - a * a)

    def u_r(self, r, E=E_ST, nu=NU_ST):
        return (1 + nu) / E * ((1 - 2 * nu) * self.A * r + self.B / r)

    def sv_innen(self, nu=NU_ST):
        a = self.a
        s = np.array([self.A - self.B / a ** 2, self.A + self.B / a ** 2, 2 * nu * self.A])
        return float(np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[2] - s[0]) ** 2)))

    def modell(self, typ, n_t, n_r, E=E_ST, nu=NU_ST, fy=None):
        a, b, h = self.a, self.b, self.h

        def form(i, j, k, p):
            r = a + (b - a) * i / n_r
            t = 0.5 * np.pi * j / n_t
            return np.array([r * np.cos(t), r * np.sin(t), h * k])
        m, ids = quader(typ, n_r, n_t, 1, 1.0, 1.0, h, E=E, nu=nu, fy=fy, form=form)
        if typ == "tet10":
            # Kantenmitten auf den Kreisbogen (die Knoten der Mitte lagen auf der Sehne)
            for e in m.elements:
                for (p_, q_), mm in zip(TET10_KANTEN, e.nodes[4:]):
                    P, Q = m.nodes[e.nodes[p_]], m.nodes[e.nodes[q_]]
                    rp, rq = np.hypot(P[0], P[1]), np.hypot(Q[0], Q[1])
                    if abs(rp - rq) < 1e-12 * b:
                        M = 0.5 * (P + Q)
                        f = rp / np.hypot(M[0], M[1])
                        m.nodes[mm] = np.array([M[0] * f, M[1] * f, M[2]])
        X = np.asarray(m.nodes, float)
        tol = 1e-9 * b
        for n in range(m.nn):
            dofs = [d for d in (0, 1) if abs(X[n, d]) < tol]
            if abs(X[n, 2]) < tol or abs(X[n, 2] - h) < tol:
                dofs.append(2)
            if dofs:
                m.fix(int(n), dofs)
        innen = randseiten(m, lambda P: bool(np.all(np.abs(np.hypot(P[:, 0], P[:, 1]) - a) < 1e-9 * b)))
        spannung_auf_seiten(m, innen, lambda x: self.p * np.array([x[0], x[1], 0.0])
                            / np.hypot(x[0], x[1]))
        return m


# --------------------------------------------------------------------------
# Loesen und Auswerten
# --------------------------------------------------------------------------
def loese(model):
    """Einen Lastfall rechnen; Rueckgabe (Results, Sekunden)."""
    t0 = time.perf_counter()
    r = solver.solve_all(model)
    t = time.perf_counter() - t0
    return next(iter(r.cases.values())), t


def verschiebungen(res, model):
    """(nn, 3) - res.u fuehrt **sechs** FHG je Knoten, auch bei Volumen."""
    u = np.asarray(res.u, float).reshape(model.nn, -1)
    assert u.shape[1] == 6, u.shape
    return u[:, :3]


def lokale_koordinaten(typ, X, P, iter_max=30):
    """Natuerliche Koordinaten des Punktes P im Element (Newton auf der
    isoparametrischen Abbildung). Rueckgabe (xi (3,), innen?)."""
    X = np.asarray(X, float)
    P = np.asarray(P, float)
    if typ in ("tet4", "tet10"):
        xi = np.array([0.25, 0.25, 0.25])
    elif typ in ("pent6", "pent15"):
        xi = np.array([1 / 3, 1 / 3, 0.0])
    else:
        xi = np.zeros(3)
    for _ in range(iter_max):
        N, dN = sl.N_dN(typ, *xi)
        r = N @ X - P
        J = dN.T @ X                       # (3,3): Zeile = d/dxi_a, Spalte = x
        d = np.linalg.solve(J.T, r)
        xi = xi - d
        if np.linalg.norm(d) < 1e-13:
            break
    return xi, _innen(typ, xi)


def _innen(typ, xi, tol=1e-9):
    r, s, t = xi
    if typ in ("tet4", "tet10"):
        return min(r, s, t, 1 - r - s - t) >= -tol
    if typ in ("pent6", "pent15"):
        return min(r, s, 1 - r - s) >= -tol and abs(t) <= 1 + tol
    return max(abs(r), abs(s), abs(t)) <= 1 + tol


def punktspannung(model, res, P, tol=1e-9):
    """Spannung am Punkt P aus den Elementfeldern.

    Jedes Element, das P enthaelt (auf einem Knoten oder einer Seite sind es
    mehrere), wertet **sein** Spannungsfeld an P aus - der tet4 hat eine
    konstante Spannung, hex8, tet10 und pent6 ein Feld (solid.stress_points
    an den natuerlichen Koordinaten von P). Rueckgabe:

        mittel      Mittel der Tensoren (das, was eine Knotenglaettung an P zeigt)
        sv_mittel   sigma_v davon
        sv_min/max  Spanne der sigma_v der einzelnen Elemente an P
        sv_nachweis groesstes sigma_v aus res.solid_res dieser Elemente -
                    das, was der Nachweis (ec3.volumen) je Element liest
    """
    u = np.asarray(res.u, float).reshape(model.nn, -1)[:, :3]
    P = np.asarray(P, float)
    werte, nachweis = [], []
    ev = None
    for i, e in enumerate(model.elements):
        X = np.asarray(model.nodes[e.nodes], float)
        lo, hi = X.min(axis=0) - tol, X.max(axis=0) + tol
        if np.any(P < lo) or np.any(P > hi):
            continue
        typ = e.typ
        k = sl.knotenzahl(typ)
        xi, innen = lokale_koordinaten(typ, X[:k] if typ != "tet10" else X, P)
        if not innen:
            continue
        mat = model.materials[e.mat]
        ue = u[e.nodes].ravel()
        if typ == "tet4" and getattr(model, "knotendilatation", False):
            if ev is None:
                from statik3d import assemble as asm
                ev = asm.knotendilatation_je_element(model, np.asarray(res.u, float).ravel())
            dN, _V = sl.tet4_shape_grad(X)
            eps = sl._B_from_grad(dN) @ ue
            s = sl.D_deviatorisch(mat.E, mat.nu) @ eps + sl.kompressionsmodul(mat.E, mat.nu) * ev[i] * sl.VOIGT_M
        else:
            s = np.asarray(sl.stress_points(typ, X, mat.E, mat.nu, ue, punkte=[tuple(xi)])[0], float)
        werte.append(s)
        if i in res.solid_res:
            nachweis.append(sl.von_mises(np.asarray(res.solid_res[i], float)))
    if not werte:
        raise ValueError(f"kein Element enthaelt den Punkt {P}")
    S = np.array(werte)
    svs = [sl.von_mises(s) for s in S]
    mittel = S.mean(axis=0)
    return {"mittel": mittel, "sv_mittel": sl.von_mises(mittel), "sv_min": min(svs),
            "sv_max": max(svs), "sv_nachweis": max(nachweis) if nachweis else float("nan"),
            "elemente": len(werte)}


def fhg(model):
    """Freiheitsgrade, die tragen: drei je Knoten eines Volumennetzes."""
    return 3 * model.nn
