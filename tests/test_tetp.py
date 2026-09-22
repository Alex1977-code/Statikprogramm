"""
Pruefungen des Tetraeders mit Ordnung p (statik3d.elements.tetp).

  * Integrationsregeln: exakt fuer alle Monome bis zu ihrem Grad
  * Ansatz vollstaendig: L2-Projektion eines Polynoms vom Grad p ist exakt
  * Starrkoerpermoden, Symmetrie: genau sechs Nulleigenwerte je Element
  * Patch-Test am verzerrten Verband, auch mit gemischter Ordnung, linearen
    Pflichtseiten und gekruemmten Elementen
  * Stapel gegen Einzelweg (1e-15)
  * Masse, Volumenlast, Seitenlast: Summen gegen Volumen bzw. Flaeche
  * Kragarm (konformes Kuhn-Gitter): sigma_v an der Oberkante auf 1 N/mm2

Die Verbaende werden hier selbst mit duennen Matrizen assembliert.

Aufruf:  python -m tests.test_tetp
"""
import os
import sys
from math import factorial

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.elements import tetp as tp                         # noqa: E402

RESULTS = []
E_ST, NU_ST = 210e9, 0.3


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Netze: Kuhn-Zerlegung (konform), wahlweise mit verschobenen inneren Knoten
# --------------------------------------------------------------------------
KUHN = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]


def _vol(Xe):
    return np.linalg.det(np.array([Xe[1] - Xe[0], Xe[2] - Xe[0], Xe[3] - Xe[0]])) / 6.0


def kuhn(nx, ny, nz, L=1.0, B=1.0, H=1.0, verzerrung=0.0, keim=3, mischen=True):
    rng = np.random.default_rng(keim)
    idx = {}
    X = []
    h = min(L / nx, B / ny, H / nz)
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                p = np.array([L * i / nx, B * j / ny, H * k / nz])
                if verzerrung and 0 < i < nx and 0 < j < ny and 0 < k < nz:
                    p = p + rng.uniform(-1, 1, 3) * verzerrung * h
                idx[(i, j, k)] = len(X)
                X.append(p)
    X = np.array(X)
    T = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                z = [idx[(i + (c & 1), j + ((c >> 1) & 1), k + ((c >> 2) & 1))] for c in range(8)]
                for tet in KUHN:
                    kn = [z[c] for c in tet]
                    if _vol(X[kn]) < 0:
                        kn[1], kn[2] = kn[2], kn[1]
                    T.append(kn)
    T = np.array(T)
    if mischen:
        # zufaellige globale Nummern, damit alle Orientierungen vorkommen
        perm = rng.permutation(len(X))
        Xp = np.empty_like(X)
        Xp[perm] = X
        X, T = Xp, perm[T]
    return X, T


class Verband:
    """Kleiner Verband aus tetp-Elementen: Nummern, Steifigkeit, Loesen."""

    def __init__(self, X, T, ordnung, linear_flaechen=(), G=None):
        self.X, self.T = np.asarray(X, float), np.asarray(T)
        self.ordnung = np.broadcast_to(np.asarray(ordnung), (len(T),)).copy()
        nn = len(X)
        self.an = tp.Anreicherung(T, self.ordnung, 6 * nn, linear_flaechen=linear_flaechen)
        self.ndof = 6 * nn + self.an.anzahl
        self.G = tp.geometrie(self.X[self.T]) if G is None else G
        self.gruppen = {}
        P_e = self.an.gruppe(np.arange(len(T)))
        for P in np.unique(P_e):
            pos = np.nonzero(P_e == P)[0]
            fhg, maske = self.an.fhg_und_maske(pos, int(P))
            self.gruppen[int(P)] = (pos, fhg, maske)

    def steifigkeit(self, E=E_ST, nu=NU_ST, krumm=None):
        r, c, v = [], [], []
        for P, (pos, fhg, maske) in self.gruppen.items():
            K, _V = tp.steifigkeit_stapel(self.G[pos], self.T[pos], P, E, nu, maske, krumm=krumm)
            r.append(np.repeat(fhg, fhg.shape[1], axis=1).ravel())
            c.append(np.tile(fhg, (1, fhg.shape[1])).ravel())
            v.append(K.ravel())
        return sparse.coo_matrix((np.concatenate(v), (np.concatenate(r), np.concatenate(c))),
                                 shape=(self.ndof, self.ndof)).tocsr()

    def loese(self, K, f, fest, u0=None):
        u = np.zeros(self.ndof) if u0 is None else u0.copy()
        diag = np.abs(K.diagonal())
        tot = np.nonzero(diag == 0)[0]                  # Drehungen und unbenutzte Plaetze
        fest = np.union1d(fest, tot)
        frei = np.setdiff1d(np.arange(self.ndof), fest)
        rhs = f[frei] - K[frei][:, fest] @ u[fest]
        u[frei] = spsolve(K[frei][:, frei].tocsc(), rhs)
        return u

    def spannung_ecke(self, u, E=E_ST, nu=NU_ST):
        """{Knoten: Liste der Spannungen der Elemente an diesem Knoten}."""
        aus = {}
        for P, (pos, fhg, maske) in self.gruppen.items():
            S = tp.spannungen_stapel(self.G[pos], self.T[pos], P, E, nu, u[fhg], tp.AUSWERTEPUNKTE[1:], maske)
            for a, e in enumerate(pos):
                for i in range(4):
                    aus.setdefault(int(self.T[e, i]), []).append(S[a, i])
        return aus

    def fest_auf(self, bedingung):
        """FHG (Ecken und Anreicherung) aller Entitaeten, die ganz die Bedingung
        erfuellen - fuer vorgegebene Randwerte. Kanten und Flaechen zusaetzlich
        an ihrer Mitte geprueft."""
        auf = np.array([bool(bedingung(x)) for x in self.X])
        d = [6 * np.nonzero(auf)[0][:, None] + np.arange(3)]
        an = self.an
        for k, (a, b) in enumerate(an.kanten):
            n = tp.je_entitaet(int(an.p_kante[k]), "k")
            if n and auf[a] and auf[b] and bedingung(0.5 * (self.X[a] + self.X[b])):
                d.append((an.start_kante[k] + np.arange(3 * n))[None, :])
        for f, fl in enumerate(an.flaechen):
            n = tp.je_entitaet(int(an.p_flaeche[f]), "f")
            if n and all(auf[fl]) and bedingung(self.X[fl].mean(axis=0)):
                d.append((an.start_flaeche[f] + np.arange(3 * n))[None, :])
        return np.unique(np.concatenate([x.ravel() for x in d]))


# --------------------------------------------------------------------------
def test_regeln():
    for grad, (L, W) in tp.REGELN.items():
        fehler = 0.0
        for g in range(grad + 1):
            for a in range(g + 1):
                for b in range(g + 1 - a):
                    for c in range(g + 1 - a - b):
                        d = g - a - b - c
                        num = W @ (L[:, 0] ** a * L[:, 1] ** b * L[:, 2] ** c * L[:, 3] ** d)
                        ex = 6.0 * factorial(a) * factorial(b) * factorial(c) * factorial(d) / factorial(g + 3)
                        fehler = max(fehler, abs(num - ex) / ex)
        check(f"Regel Grad {grad} ({len(W)} Punkte) exakt, Gewichte positiv",
              fehler < 1e-13 and np.all(W > 0) and np.all(L >= 0),
              f"rel. Fehler {fehler:.1e}")
    L, W = tp.regel_konisch(4)
    check("konische Regel n = 4: 64 Punkte, Summe 1", len(W) == 64 and abs(W.sum() - 1) < 1e-14)


def test_vollstaendig():
    X, T = kuhn(2, 2, 2, verzerrung=0.2)
    rng = np.random.default_rng(1)
    for P in (2, 3, 4):
        v = Verband(X, T, P)
        exps = [(i, j, k) for i in range(P + 1) for j in range(P + 1) for k in range(P + 1) if i + j + k <= P]
        coef = rng.normal(size=len(exps))

        def fpol(Q):
            return sum(c * Q[:, 0] ** i * Q[:, 1] ** j * Q[:, 2] ** k for c, (i, j, k) in zip(coef, exps))
        L, W = tp.regel(2 * P)
        F, _dF = tp.basis_ref(L, P)
        r, c, m, rhs = [], [], [], np.zeros(v.ndof)
        pos, fhg, maske = v.gruppen[P]
        C = tp.orientierung(T[pos], P)
        for a, e in enumerate(pos):
            Fg = F @ C[a]
            nr = fhg[a, 0::3]
            _dummy, detJ = tp.jacobi(v.G[e][None], L)
            w = W * detJ[0] / 6
            Q = L @ X[T[e]]
            Me = Fg.T @ (Fg * w[:, None])
            rr, cc = np.meshgrid(nr, nr, indexing="ij")
            r.append(rr.ravel()); c.append(cc.ravel()); m.append(Me.ravel())
            np.add.at(rhs, nr, Fg.T @ (w * fpol(Q)))
        M = sparse.coo_matrix((np.concatenate(m), (np.concatenate(r), np.concatenate(c))),
                              shape=(v.ndof, v.ndof)).tocsr()
        benutzt = np.nonzero(np.abs(M.diagonal()) > 0)[0]
        a_ = np.zeros(v.ndof)
        a_[benutzt] = spsolve(M[benutzt][:, benutzt].tocsc(), rhs[benutzt])
        fehler = 0.0
        for a, e in enumerate(pos):
            Fg = F @ C[a]
            fehler = max(fehler, np.abs(Fg @ a_[fhg[a, 0::3]] - fpol(L @ X[T[e]])).max())
        check(f"p = {P}: Polynom vom Grad {P} exakt dargestellt", fehler < 1e-10, f"{fehler:.1e}")


def test_starrkoerper():
    rng = np.random.default_rng(7)
    X = np.array([[0, 0, 0], [1.1, 0.1, 0], [0.2, 0.9, 0.1], [0.1, 0.3, 1.2]]) + rng.normal(size=(4, 3)) * 0.05
    for P in (2, 3, 4):
        K, V = tp.steifigkeit_stapel(X[None], np.array([[5, 2, 9, 1]]), P, E_ST, NU_ST)
        K = K[0]
        ew = np.linalg.eigvalsh(0.5 * (K + K.T))
        null = int(np.sum(np.abs(ew) < 1e-9 * np.abs(ew).max()))
        sym = np.abs(K - K.T).max() / np.abs(K).max()
        check(f"p = {P}: sechs Starrkoerpermoden, symmetrisch", null == 6 and sym < 1e-14 and ew.min() > -1e-9 * ew.max(),
              f"Nullmoden {null}, Asymmetrie {sym:.1e}, V {V[0]:.4f}")


def _patch(v, K, A, E=E_ST, nu=NU_ST):
    rand = v.fest_auf(lambda x: min(x.min(), 1 - x.max()) < 1e-9)
    u0 = np.zeros(v.ndof)
    for c in range(3):
        u0[6 * np.arange(len(v.X)) + c] = v.X @ A[c]
    # Auf gekruemmten Kanten ist u = A x entlang der Kante quadratisch in der
    # Kantenkoordinate: die Amplitude der Kantenfunktion L_a L_b (am
    # Mittelpunkt 1/4) ist 4 A (x_mitte - (x_a + x_b)/2); gerade Kanten: 0.
    mitte = {}
    for e, t in enumerate(v.T):
        for m, (a, b) in enumerate(tp.TET10_KANTEN):
            mitte[(min(t[a], t[b]), max(t[a], t[b]))] = v.G[e, 4 + m]
    an = v.an
    for k, (a, b) in enumerate(an.kanten):
        if an.p_kante[k] >= 2:
            d = mitte[(int(a), int(b))] - 0.5 * (v.X[a] + v.X[b])
            u0[an.start_kante[k]:an.start_kante[k] + 3] = 4.0 * (A @ d)
    u = v.loese(K, np.zeros(v.ndof), rand, u0)
    eps = np.array([A[0, 0], A[1, 1], A[2, 2], A[0, 1] + A[1, 0], A[1, 2] + A[2, 1], A[0, 2] + A[2, 0]])
    soll = tp.D_matrix(E, nu) @ eps
    S = v.spannung_ecke(u)
    fehler = max(np.abs(np.array(s) - soll).max() for s in S.values()) / np.abs(soll).max()
    amp = np.abs(u[6 * len(v.X):]).max() if v.an.anzahl else 0.0
    return fehler, amp


def test_patch():
    rng = np.random.default_rng(11)
    A = rng.normal(size=(3, 3)) * 1e-3
    X, T = kuhn(3, 3, 3, verzerrung=0.25)
    for P in (2, 3, 4):
        v = Verband(X, T, P)
        f, amp = _patch(v, v.steifigkeit(), A)
        check(f"Patch-Test p = {P}, verzerrt", f < 1e-10, f"rel. Spannungsfehler {f:.1e}, Anreicherung {amp:.1e}")
    # gemischte Ordnung und eine Pflichtflaeche (linear) mitten im Verband
    ordn = rng.integers(1, 5, size=len(T))
    ordn[ordn == 1] = 2
    innen = [tuple(sorted(T[0][[0, 1, 2]]))]
    v = Verband(X, T, ordn, linear_flaechen=innen)
    f, amp = _patch(v, v.steifigkeit(), A)
    check("Patch-Test gemischte Ordnung 2..4 mit linearer Pflichtseite", f < 1e-10,
          f"rel. Spannungsfehler {f:.1e}; Kanten p: {np.bincount(v.an.p_kante)}")
    # gekruemmte Elemente: innere Kantenmitten auf einer glatten Abbildung
    Xg, Tg = kuhn(3, 3, 3, verzerrung=0.0)
    abb = lambda Q: Q + 0.04 * np.column_stack([np.sin(3 * Q[:, 1]) * np.sin(np.pi * Q[:, 0]),
                                                 np.sin(2 * Q[:, 2]) * np.sin(np.pi * Q[:, 1]),
                                                 np.sin(3 * Q[:, 0]) * np.sin(np.pi * Q[:, 2])])
    Xa = abb(Xg)
    G = []
    for t in Tg:
        M = np.array([0.5 * (Xg[t[a]] + Xg[t[b]]) for a, b in tp.TET10_KANTEN])
        G.append(np.vstack([Xa[t], abb(M)]))
    G = np.array(G)
    for P in (2, 3):
        v = Verband(Xa, Tg, P, G=G)
        f, amp = _patch(v, v.steifigkeit(krumm=True), A)
        check(f"Patch-Test p = {P}, gekruemmte Elemente", f < 1e-9, f"rel. Spannungsfehler {f:.1e}")


def test_stapel_einzeln():
    X, T = kuhn(2, 2, 1, verzerrung=0.0)
    for P in (2, 3, 4):
        Ks, _V = tp.steifigkeit_stapel(X[T], T, P, E_ST, NU_ST)
        einzeln = np.array([tp.steifigkeit_stapel(X[T[e]][None], T[e][None], P, E_ST, NU_ST)[0][0]
                            for e in range(len(T))])
        d = np.abs(Ks - einzeln).max() / np.abs(Ks).max()
        check(f"p = {P}: Stapel gegen Einzelweg", d <= 1e-15, f"{d:.1e}")


def test_summen():
    X, T = kuhn(2, 1, 1, L=1.0, B=0.5, H=0.4, verzerrung=0.0)
    V_soll = 0.2
    for P in (2, 3, 4):
        pos = np.arange(len(T))
        M = tp.masse_stapel(X[T], T, P, 7850.0)
        # Starre Verschiebung in x: nur Ecken tragen 1
        nf = tp.funktionszahl(P)
        e = np.zeros(3 * nf)
        e[0:12:3] = 1.0
        m = sum(e @ Mi @ e for Mi in M)
        f = tp.volumenlast_stapel(X[T], T, P, np.array([0.0, 0.0, -7850.0 * 9.81]))
        Fz = f[:, 2:12:3].sum()
        s0 = np.array([1e6, -2e6, 3e5, 4e5, 0.0, -1e5])
        fa = tp.anfangsspannung_stapel(X[T], T, P, s0)
        check(f"p = {P}: Masse = rho V, Volumenlast = rho g V",
              abs(m / (7850.0 * V_soll) - 1) < 1e-13 and abs(Fz / (-7850.0 * 9.81 * V_soll) - 1) < 1e-13,
              f"m {m:.6f} kg, Fz {Fz:.4f} N")
        # Anfangsspannung: die Ecklasten eines Elements heben sich auf (Gleichgewicht)
        check(f"p = {P}: Anfangsspannung im Gleichgewicht",
              np.abs(fa[:, 0:12].reshape(-1, 4, 3).sum(axis=1)).max() < 1e-6 * np.abs(s0).max())
    # Seitenlast: gerade Seite -> p A n; gekruemmte -> Resultierende des Bogens
    Xe = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    for P in (2, 3):
        f = tp.seitenlast(Xe, np.array([0, 1, 2, 3]), P, 0, 1000.0)
        F = f.reshape(-1, 3)[:4].sum(axis=0)
        check(f"p = {P}: Seitendruck 1 kN/m2 auf 0,5 m2 nach innen", np.allclose(F, [0, 0, 500.0], atol=1e-9),
              f"F = {F}")


def test_kragarm():
    """Kragarm 1,0 x 0,1 x 0,2 m, Endquerkraft als Schubspannung, sigma_v an
    der Oberkante x = L/2, Mitte der Breite: Saint-Venant 355 N/mm2. Gemessen
    22.09.2026 im Labor: p = 3 auf 5 x 1 x 1 Kuhn-Zellen (30 Tetraeder, 720
    freie FHG) liegt jedes Element dort hoechstens 0,18 N/mm2 daneben."""
    L, B, H = 1.0, 0.1, 0.2
    I = B * H ** 3 / 12
    F = 355e6 * I / (0.5 * L * 0.5 * H)
    X, T = kuhn(5, 1, 1, L, B, H, mischen=False)
    v = Verband(X, T, 3)
    K = v.steifigkeit()
    f = np.zeros(v.ndof)
    for e, t in enumerate(T):
        for s, ecken in enumerate(tp.SEITEN):
            if all(abs(X[t[list(ecken)], 0] - L) < 1e-9):
                pos, fhg, maske = v.gruppen[3]
                a = int(np.nonzero(pos == e)[0][0])
                fe = tp.seitenlast(X[t], t, 3, s, F / (B * H), richtung=(0, 0, -1), maske=maske[a])
                np.add.at(f, fhg[a], fe)
    fest = v.fest_auf(lambda x: abs(x[0]) < 1e-9)
    u = v.loese(K, f, fest)
    P_nw = np.array([0.5 * L, 0.5 * B, H])
    pos, fhg, maske = v.gruppen[3]
    sv = []
    for a, e in enumerate(pos):
        Xe = X[T[e]]
        M = np.ones((4, 4))
        M[:, 1:] = Xe
        Lb = np.linalg.solve(M.T, np.concatenate([[1.0], P_nw]))
        if Lb.min() < -1e-9:
            continue
        S = tp.spannungen_stapel(Xe[None], T[e][None], 3, E_ST, NU_ST, u[fhg[a]][None], [tuple(Lb[1:])], maske[a][None])
        s = S[0, 0]
        sv.append(np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[2] - s[0]) ** 2)
                          + 3 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)) / 1e6)
    abw = max(abs(x - 355.0) for x in sv)
    check("Kragarm p = 3, 30 Tetraeder: sigma_v an der Oberkante auf 1 N/mm2", abw <= 1.0 and len(sv) >= 1,
          f"{len(sv)} Elemente, groesste Abweichung {abw:.3f} N/mm2 bei {v.ndof} Plaetzen")


def test_umgeklappt():
    X = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
    G = tp.geometrie(X[None]).copy()
    # Mitte der Kante 0-1 zwischen Viertelpunkt und Ecke: an allen 14
    # Integrationspunkten ist det J positiv (>= 0,245), an der Ecke 0 -0,200
    G[0, 4] = [0.2, 0.0, 0.0]
    try:
        tp.steifigkeit_stapel(G, np.array([[0, 1, 2, 3]]), 2, E_ST, NU_ST, elemente=[41])
        check("umgeklapptes Element wirft ValueError mit Nummer", False, "kein Fehler")
    except ValueError as ex:
        check("umgeklapptes Element wirft ValueError mit Nummer", "Element 42" in str(ex), str(ex)[:60])


# --------------------------------------------------------------------------
# Am Modell: Uebergaenge, Kontakt, Fugen, Lager
# --------------------------------------------------------------------------
def _modell(nx=2, ny=2, nz=2, typ_von=None):
    from statik3d.model import Element, Material, Model
    X, T = kuhn(nx, ny, nz, mischen=False)
    m = Model("tetp")
    m.add_material(Material("S", E=E_ST, nu=NU_ST))
    for x in X:
        m.add_node(*x)
    for i, t in enumerate(T):
        typ = typ_von(X[t].mean(axis=0)) if typ_von else "tetp3"
        m.elements.append(Element(typ, [int(v) for v in t], "S"))
    return m


def _kanten_am_rand(an, kn):
    """Kanten mit beiden Ecken in kn."""
    s = set(int(v) for v in kn)
    return [k for k, (a, b) in enumerate(an.kanten) if int(a) in s and int(b) in s]


def test_modell_uebergang_kontakt():
    # links tet4, rechts tetp3: die gemeinsame Ebene x = 0,5 bleibt linear
    m = _modell(typ_von=lambda c: "tet4" if c[0] < 0.5 else "tetp3")
    an = tp.anreicherung(m)
    X = np.asarray(m.nodes)
    mitte = np.nonzero(np.abs(X[:, 0] - 0.5) < 1e-12)[0]
    ks = _kanten_am_rand(an, mitte)
    fl = [f for f, tri in enumerate(an.flaechen) if all(abs(X[tri, 0] - 0.5) < 1e-12)]
    innen_k = [k for k in range(len(an.kanten)) if min(X[an.kanten[k], 0]) > 0.5 + 1e-9]
    check("Uebergang tet4/tetp: Kanten und Seiten der Grenze linear",
          len(ks) > 0 and all(an.p_kante[k] == 1 for k in ks) and all(an.p_flaeche[f] == 1 for f in fl)
          and all(an.p_kante[k] == 3 for k in innen_k),
          f"{len(ks)} Kanten, {len(fl)} Seiten an der Grenze; innen p = 3 auf {len(innen_k)} Kanten")
    # Kontaktpaar auf der Oberseite z = 1: dort linear
    from statik3d.model import ContactPair
    m = _modell()
    oben = [i for i in range(m.nn) if abs(m.nodes[i][2] - 1.0) < 1e-12]
    m.contact_pairs.append(ContactPair("K", slave_nodes=oben, master_faces=[[0, 1, 2]]))
    an = tp.anreicherung(m)
    fl = [f for f, tri in enumerate(an.flaechen) if all(np.abs(np.asarray(m.nodes)[tri, 2] - 1.0) < 1e-12)]
    ks = _kanten_am_rand(an, oben)
    check("Kontaktseite bleibt linear (keine Zusatz-FHG, die der Kontakt nicht kennt)",
          len(fl) == 8 and all(an.p_flaeche[f] == 1 for f in fl) and all(an.p_kante[k] == 1 for k in ks),
          f"{len(fl)} Seiten, {len(ks)} Kanten")


def test_modell_fuge_getrennt():
    """Eine Fuge wird erst nach dem Vernetzen getrennt (fugen.py verdoppelt
    die Ecken). Die Zusatz-FHG haengen an Eckpaaren und -tripeln und trennen
    sich damit mit; beide Koerper teilen danach keinen einzigen FHG."""
    m = _modell()
    X = np.asarray(m.nodes, float)
    mitte = [i for i in range(m.nn) if abs(X[i, 0] - 0.5) < 1e-12]
    neu = {}
    for e in m.elements:
        if X[e.nodes].mean(axis=0)[0] > 0.5:
            for a, v in enumerate(e.nodes):
                if v in mitte:
                    if v not in neu:
                        neu[v] = m.add_node(*m.nodes[v])
                    e.nodes[a] = neu[v]
    from statik3d.model import Kopplung
    for a, b in neu.items():
        m.kopplungen.append(Kopplung(a, b, [[1.0, 0, 0]], [float("inf")]))
    tp.anreicherung(m)
    links, rechts = set(), set()
    Xn = np.asarray(m.nodes, float)
    for P, mat, els, fhg, maske in tp.gruppen(m, list(range(len(m.elements)))):
        for a, i in enumerate(els):
            ziel = rechts if Xn[m.elements[i].nodes].mean(axis=0)[0] > 0.5 else links
            ziel.update(int(d) for d, mk in zip(fhg[a], np.repeat(maske[a], 3)) if mk)
    gemeinsam = links & rechts
    check("getrennte Fuge: kein gemeinsamer FHG beider Koerper", len(gemeinsam) == 0,
          f"{len(links)} / {len(rechts)} FHG, gemeinsam {len(gemeinsam)}")


def test_modell_pflichtpruefung_laut():
    from statik3d.model import ContactPair
    m = _modell()
    oben = [i for i in range(m.nn) if abs(m.nodes[i][2] - 1.0) < 1e-12]
    m.contact_pairs.append(ContactPair("K", slave_nodes=oben, master_faces=[[0, 1, 2]]))
    kn = np.array([e.nodes[:4] for e in m.elements])
    falsch = tp.Anreicherung(kn, np.full(len(kn), 3), tp.basis_fhg(m))     # ohne Pflichtseiten
    try:
        tp.pruefe_pflichtseiten(m, falsch)
        check("Zusatzansatz auf einer Kontaktseite bricht laut ab", False, "kein Fehler")
    except ValueError as ex:
        check("Zusatzansatz auf einer Kontaktseite bricht laut ab", "Kontakt" in str(ex), str(ex)[:70])


def test_modell_lager():
    """Symmetrieebene z = 0 (nur uz gelagert): die Zusatz-FHG der Seiten dort
    sind in z gesperrt, in x und y frei; eine Feder macht die Seite linear."""
    m = _modell()
    unten = [i for i in range(m.nn) if abs(m.nodes[i][2]) < 1e-12]
    for n in unten:
        m.fix(n, [2])
    an = tp.anreicherung(m)
    fest = tp.gesperrte_fhg(m)
    kompon = set(int((d - an.basis) % 3) for d in fest)
    fl = [f for f, tri in enumerate(an.flaechen) if all(np.abs(np.asarray(m.nodes)[tri, 2]) < 1e-12)]
    soll = sum(tp.je_entitaet(int(an.p_flaeche[f]), "f") for f in fl)
    ks = _kanten_am_rand(an, unten)
    soll += sum(tp.je_entitaet(int(an.p_kante[k]), "k") for k in ks)
    check("Symmetrieebene: Zusatz-FHG nur in der gelagerten Richtung gesperrt",
          kompon == {2} and len(fest) == soll, f"{len(fest)} gesperrt, erwartet {soll}")
    m2 = _modell()
    for n in [i for i in range(m2.nn) if abs(m2.nodes[i][2]) < 1e-12]:
        m2.fix(n, [2], stiffness=[1e9])
    an2 = tp.anreicherung(m2)
    fl2 = [f for f, tri in enumerate(an2.flaechen) if all(np.abs(np.asarray(m2.nodes)[tri, 2]) < 1e-12)]
    check("federndes Flaechenlager: Seite bleibt linear", all(an2.p_flaeche[f] == 1 for f in fl2),
          f"{len(fl2)} Seiten")


def test_modell_steifigkeit():
    """tetp.matrizen und tetp.spannungen am Modell: Patch-Test mit gemischter Ordnung."""
    m = _modell(typ_von=lambda c: "tetp2" if c[2] < 0.5 else "tetp4")
    an = tp.anreicherung(m)
    mats = tp.matrizen(m, list(range(len(m.elements))))
    ndof = 6 * m.nn + an.anzahl
    r, c, v = [], [], []
    for i, (d, K) in mats.items():
        r.append(np.repeat(d, len(d)))
        c.append(np.tile(d, len(d)))
        v.append(K.ravel())
    K = sparse.coo_matrix((np.concatenate(v), (np.concatenate(r), np.concatenate(c))), shape=(ndof, ndof)).tocsr()
    rng = np.random.default_rng(3)
    A = rng.normal(size=(3, 3)) * 1e-3
    X = np.asarray(m.nodes, float)
    rand = [i for i in range(m.nn) if min(X[i].min(), 1 - X[i].max()) < 1e-9]
    fest = (6 * np.array(rand)[:, None] + np.arange(3)).ravel()
    auf = np.zeros(m.nn, bool)
    auf[rand] = True
    rs = tp._randseiten(an)
    for f, tri in enumerate(an.flaechen):
        n = tp.je_entitaet(int(an.p_flaeche[f]), "f")
        if n and rs[f] and auf[tri].all():
            fest = np.concatenate([fest, an.start_flaeche[f] + np.arange(3 * n)])
    for k in range(len(an.kanten)):
        n = tp.je_entitaet(int(an.p_kante[k]), "k")
        if n and auf[an.kanten[k]].all() and tp._kante_auf_randseite(an, k, auf):
            fest = np.concatenate([fest, an.start_kante[k] + np.arange(3 * n)])
    u = np.zeros(ndof)
    for cc in range(3):
        u[6 * np.arange(m.nn) + cc] = X @ A[cc]
    tot = np.nonzero(np.abs(K.diagonal()) == 0)[0]
    fest = np.union1d(fest, tot)
    frei = np.setdiff1d(np.arange(ndof), fest)
    u[frei] = spsolve(K[frei][:, frei].tocsc(), -K[frei][:, fest] @ u[fest])
    S = tp.spannungen(m, list(range(len(m.elements))), u)
    eps = np.array([A[0, 0], A[1, 1], A[2, 2], A[0, 1] + A[1, 0], A[1, 2] + A[2, 1], A[0, 2] + A[2, 0]])
    soll = tp.D_matrix(E_ST, NU_ST) @ eps
    fehler = max(np.abs(Si - soll).max() for Si in S.values()) / np.abs(soll).max()
    check("Modell mit p = 2 und p = 4 gemischt: Patch-Test", fehler < 1e-10,
          f"rel. Spannungsfehler {fehler:.1e}, {an.anzahl} Zusatz-FHG")


def test_importreihenfolge():
    """tetp vor solid und solid vor tetp importiert, je in einem frischen
    Prozess: beide Male sind die tetp-Typen bei solid angemeldet."""
    import subprocess
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for reihe in ("from statik3d.elements import tetp\nfrom statik3d.elements import solid as sl",
                  "from statik3d.elements import solid as sl\nfrom statik3d.elements import tetp"):
        code = reihe + "\nprint(all(t in sl.OPERATOREN and t in sl.FLAECHEN for t in tetp.TYPEN))"
        r = subprocess.run([sys.executable, "-c", code], cwd=wurzel, capture_output=True, text=True)
        erste = reihe.split("\n")[0].split()[-1]
        check(f"Import zuerst {erste}: tetp bei solid angemeldet", r.stdout.strip() == "True",
              (r.stdout.strip() or r.stderr.strip()[-80:]))


def test_modell_tet10_nachbar_laut():
    m = _modell(typ_von=lambda c: "tetp3")
    # ein Element wird tet10 (Mittenknoten dazu): Grenze zu tetp nicht konform
    e = m.elements[0]
    kn = list(e.nodes[:4])
    mitten = []
    for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
        mitten.append(m.add_node(*(0.5 * (np.asarray(m.nodes[kn[a]]) + np.asarray(m.nodes[kn[b]])))))
    e.typ = "tet10"
    e.nodes = kn + mitten
    try:
        tp.anreicherung(m, streng=True)
        check("tet10 neben tetp: laut abgewiesen", False, "kein Fehler")
    except ValueError as ex:
        check("tet10 neben tetp: laut abgewiesen", "Mittenknoten" in str(ex), str(ex)[:70])


def test_modell_jacobi_gekruemmt():
    from statik3d.elements import solid as sl
    m = _modell()
    t = m.elements[0].nodes[:4]
    a, b = t[0], t[1]
    Xa, Xb = np.asarray(m.nodes[a], float), np.asarray(m.nodes[b], float)
    # Kantenmitte zwischen Viertelpunkt und Ecke a: das Element klappt an a um
    m.tetp_kantenmitten = {(min(a, b), max(a, b)): Xa + 0.2 * (Xb - Xa)}
    schlecht = sl.jacobi_pruefung(m)
    check("gekruemmter tetp in der Netzabnahme (solid.jacobi_pruefung) mit Nummer",
          len(schlecht) >= 1 and all(s[1] == "tetp3" for s in schlecht) and schlecht[0][2] < 0,
          f"{len(schlecht)} Elemente, z. B. {schlecht[0] if schlecht else None}")


def main():
    test_regeln()
    test_vollstaendig()
    test_starrkoerper()
    test_patch()
    test_stapel_einzeln()
    test_summen()
    test_kragarm()
    test_umgeklappt()
    test_modell_uebergang_kontakt()
    test_modell_fuge_getrennt()
    test_modell_pflichtpruefung_laut()
    test_modell_lager()
    test_modell_steifigkeit()
    test_importreihenfolge()
    test_modell_tet10_nachbar_laut()
    test_modell_jacobi_gekruemmt()
    n_fail = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} bestanden")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
