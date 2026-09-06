"""
Verifikation der Volumenelemente Hex20, Pent6, Pent15 und Pyr5 gegen
geschlossene Loesungen.

Geprueft wird:

  * Formfunktionen: Partition der Eins, Summe der Ableitungen 0, Kronecker-
    Eigenschaft an den Knoten, lineare Vollstaendigkeit (alle sieben Typen)
  * Starrkoerpermoden: genau 6 Null-Eigenwerte verzerrter Elemente
  * Patch-Test: lineares Verschiebungsfeld am Rand, innerer Knoten frei,
    Spannung an allen Auswertepunkten exakt
  * Volumen verzerrter Elemente (Keil = halbes Parallelepiped, Pyramide =
    Sechstel eines Wuerfels, Hex20 mit gekruemmter Deckflaeche)
  * Kragarm-Biegung gegen Bernoulli + Timoshenko
  * Flaechenlasten, Anfangsspannungslasten, Seitenlisten, Massen

Die kleinen Verbaende werden hier selbst mit dichten Matrizen assembliert
(3 FHG je Knoten, Lager durch Streichen der Zeilen und Spalten).

Aufruf:  python3 tests/test_elemente_volumen.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.elements import solid as sl                        # noqa: E402

RESULTS = []
NEU = ("hex20", "pent6", "pent15", "pyr5")
ALLE = ("tet4", "tet10", "hex8") + NEU
E_ST, NU_ST = 210e9, 0.3


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def close(name, num, ana, tol):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    return check(name, err <= tol, f"num={num: .6e} ana={ana: .6e} Abw={err * 100:.4f} %")


# --------------------------------------------------------------------------
# natuerliche Knotenkoordinaten (unabhaengig vom Modul aufgeschrieben)
# --------------------------------------------------------------------------
_HEX_ECKEN = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
              (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_HEX_KANTEN = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
               (0, 4), (1, 5), (2, 6), (3, 7)]
_PENT_ECKEN = [(0, 0, -1), (1, 0, -1), (0, 1, -1), (0, 0, 1), (1, 0, 1), (0, 1, 1)]
_PENT_KANTEN = [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)]
_TET_ECKEN = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
_TET_KANTEN = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]


def _mit_mitten(ecken, kanten):
    X = [np.array(e, float) for e in ecken]
    return np.array(X + [0.5 * (X[a] + X[b]) for a, b in kanten])


KNOTEN_NAT = {
    "tet4": np.array(_TET_ECKEN, float),
    "tet10": _mit_mitten(_TET_ECKEN, _TET_KANTEN),
    "hex8": np.array(_HEX_ECKEN, float),
    "hex20": _mit_mitten(_HEX_ECKEN, _HEX_KANTEN),
    "pent6": np.array(_PENT_ECKEN, float),
    "pent15": _mit_mitten(_PENT_ECKEN, _PENT_KANTEN),
    "pyr5": np.array([(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (0, 0, 1)], float),
}
KANTEN = {"tet10": _TET_KANTEN, "hex20": _HEX_KANTEN, "pent15": _PENT_KANTEN}
V_NAT = {"tet4": 1 / 6, "tet10": 1 / 6, "hex8": 8.0, "hex20": 8.0,
         "pent6": 1.0, "pent15": 1.0, "pyr5": 8 / 3}


def punkt_innen(typ, rng):
    """Zufaelliger Punkt im Inneren des natuerlichen Elements."""
    if typ.startswith("hex"):
        return rng.uniform(-1, 1, 3)
    if typ.startswith("pent"):
        r, s = rng.uniform(0, 1, 2)
        if r + s > 1:
            r, s = 1 - r, 1 - s
        return np.array([r, s, rng.uniform(-1, 1)])
    if typ == "pyr5":
        t = rng.uniform(-1, 1)
        h = 0.5 * (1 - t)
        return np.array([rng.uniform(-h, h), rng.uniform(-h, h), t])
    p = rng.uniform(0, 1, 3)
    while p.sum() > 1:
        p = rng.uniform(0, 1, 3)
    return p


# --------------------------------------------------------------------------
# Elementsteifigkeit, Assemblierung, Loesung
# --------------------------------------------------------------------------
def k_elem(typ, X):
    if typ == "tet4":
        K, _, V = sl.k_tet4(X, E_ST, NU_ST)
        return K, V
    fn = {"tet10": sl.k_tet10, "hex8": sl.k_hex8, "hex20": sl.k_hex20, "pent6": sl.k_pent6,
          "pent15": sl.k_pent15, "pyr5": sl.k_pyr5}[typ]
    return fn(X, E_ST, NU_ST)


def dofs(knoten):
    return np.array([3 * n + j for n in knoten for j in range(3)])


def assemble(nodes, elems, typ):
    n = len(nodes)
    K = np.zeros((3 * n, 3 * n))
    for el in elems:
        Ke, _ = k_elem(typ, nodes[list(el)])
        d = dofs(el)
        K[np.ix_(d, d)] += Ke
    return K


def loese(K, F, vorgabe):
    """vorgabe: {fhg: wert}.  Rueckgabe u (3n,)."""
    n = K.shape[0]
    u = np.zeros(n)
    fest = np.zeros(n, bool)
    for d, val in vorgabe.items():
        fest[d] = True
        u[d] = val
    frei = ~fest
    rhs = F[frei] - K[np.ix_(frei, fest)] @ u[fest]
    u[frei] = np.linalg.solve(K[np.ix_(frei, frei)], rhs)
    return u


# --------------------------------------------------------------------------
# Netze
# --------------------------------------------------------------------------
class Netz:
    """Knotenverwaltung: Eckknoten ueber Schluessel, Kantenmitten ueber Paare."""

    def __init__(self):
        self.X = []
        self.key = {}
        self.mid = {}
        self.elems = []

    def knoten(self, key, x):
        if key not in self.key:
            self.key[key] = len(self.X)
            self.X.append(np.asarray(x, float))
        return self.key[key]

    def mitte(self, a, b):
        k = (min(a, b), max(a, b))
        if k not in self.mid:
            self.mid[k] = len(self.X)
            self.X.append(0.5 * (self.X[a] + self.X[b]))
        return self.mid[k]

    def hex(self, ecken, quadratisch):
        el = list(ecken)
        if quadratisch:
            el += [self.mitte(el[a], el[b]) for a, b in _HEX_KANTEN]
        self.elems.append(el)

    def keil(self, ecken, quadratisch):
        el = list(ecken)
        if quadratisch:
            el += [self.mitte(el[a], el[b]) for a, b in _PENT_KANTEN]
        self.elems.append(el)

    def pyramiden(self, ecken, mitte_key):
        """Zerlegt ein Hexaeder (Ecken wie Hex8) in 6 Pyramiden mit Spitze in der Mitte."""
        c = self.knoten(mitte_key, np.mean([self.X[i] for i in ecken], axis=0))
        e = list(ecken)
        for f in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
            self.elems.append([e[i] for i in f] + [c])   # Rechtsschraube der Basis zur Spitze

    def fertig(self):
        return np.array(self.X), self.elems


def balken(typ, nx, ny, nz, L=2.0, b=0.1, h=0.2):
    """Kragarm-Netz aus Hexaedern, Keilen (Achse z) oder Pyramiden."""
    m = Netz()
    quad = typ in ("hex20", "pent15")

    def kn(i, j, k):
        return m.knoten((i, j, k), (L * i / nx, b * j / ny, h * k / nz))

    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                e = [kn(i, j, k), kn(i + 1, j, k), kn(i + 1, j + 1, k), kn(i, j + 1, k),
                     kn(i, j, k + 1), kn(i + 1, j, k + 1), kn(i + 1, j + 1, k + 1), kn(i, j + 1, k + 1)]
                if typ.startswith("hex"):
                    m.hex(e, quad)
                elif typ.startswith("pent"):
                    m.keil([e[0], e[1], e[2], e[4], e[5], e[6]], quad)
                    m.keil([e[0], e[2], e[3], e[4], e[6], e[7]], quad)
                else:
                    m.pyramiden(e, ("c", i, j, k))
    return m.fertig()


def kragarm(typ, nx, ny, nz, F=1000.0, L=2.0, b=0.1, h=0.2):
    """Durchbiegung am freien Ende: Einspannung bei x = 0, Einzellast F als
    konsistent verteilte Flaechenlast auf der Stirnflaeche x = L.
    Rueckgabe (Mittelwert der Knotenverschiebungen, arbeitskonjugierter Wert)."""
    nodes, elems = balken(typ, nx, ny, nz, L, b, h)
    K = assemble(nodes, elems, typ)
    Fv = np.zeros(3 * len(nodes))
    p = F / (b * h)
    for el in elems:
        for seite in sl.FLAECHEN[typ]:
            kn = [el[i] for i in seite]
            if np.all(np.abs(nodes[kn, 0] - L) < 1e-9):
                Fv[dofs(kn)] += sl.flaechenlast_knoten(nodes[kn], p, richtung=(0, 0, -1)).ravel()
    vorgabe = {d: 0.0 for n in np.where(np.abs(nodes[:, 0]) < 1e-9)[0] for d in dofs([n])}
    u = loese(K, Fv, vorgabe)
    tip = np.where(np.abs(nodes[:, 0] - L) < 1e-9)[0]
    w_mittel = -np.mean(u[3 * tip + 2])
    w_arbeit = -(Fv @ u) / F
    return w_mittel, w_arbeit


def balken_analytisch(F=1000.0, L=2.0, b=0.1, h=0.2, E=E_ST, nu=NU_ST):
    G = E / (2 * (1 + nu))
    I = b * h ** 3 / 12
    return F * L ** 3 / (3 * E * I) + F * L / (5 / 6 * b * h * G)


# --------------------------------------------------------------------------
# Formfunktionen und Gauss-Regeln
# --------------------------------------------------------------------------
def t_formfunktionen():
    rng = np.random.default_rng(7)
    for typ in ALLE:
        XI = KNOTEN_NAT[typ]
        n = sl.knotenzahl(typ)
        e_kron = max(np.abs(sl.N_dN(typ, *XI[i])[0] - np.eye(n)[i]).max() for i in range(n))
        e_pu = e_dn = e_lin = e_fd = 0.0
        for _ in range(25):
            p = punkt_innen(typ, rng)
            N, dN = sl.N_dN(typ, *p)
            e_pu = max(e_pu, abs(N.sum() - 1.0))
            e_dn = max(e_dn, np.abs(dN.sum(axis=0)).max())
            e_lin = max(e_lin, np.abs(N @ XI - p).max())
            for j in range(3):                       # Ableitungen gegen Differenzenquotient
                d = np.zeros(3)
                d[j] = 1e-6
                fd = (sl.N_dN(typ, *(p + d))[0] - sl.N_dN(typ, *(p - d))[0]) / 2e-6
                e_fd = max(e_fd, np.abs(fd - dN[:, j]).max())
        check(f"{typ}: Kronecker an den Knoten", e_kron < 1e-13, f"max {e_kron:.1e}")
        check(f"{typ}: Partition der Eins, Summe dN = 0", e_pu < 1e-13 and e_dn < 1e-13,
              f"{e_pu:.1e} / {e_dn:.1e}")
        check(f"{typ}: lineare Vollstaendigkeit", e_lin < 1e-13, f"max {e_lin:.1e}")
        check(f"{typ}: Ableitungen (Differenzenquotient)", e_fd < 1e-7, f"max {e_fd:.1e}")
        GP, W = sl.gauss(typ)
        close(f"{typ}: Gauss-Gewichte = natuerliches Volumen", W.sum(), V_NAT[typ], 1e-13)
        check(f"{typ}: Gauss-Punkte liegen im Element", all(punkt_im_element(typ, g) for g in GP))


def punkt_im_element(typ, p):
    r, s, t = p
    if typ.startswith("hex"):
        return max(abs(r), abs(s), abs(t)) < 1
    if typ.startswith("pent"):
        return r > 0 and s > 0 and r + s < 1 and abs(t) < 1
    if typ == "pyr5":
        return abs(t) < 1 and max(abs(r), abs(s)) < 0.5 * (1 - t)
    return r > 0 and s > 0 and t > 0 and r + s + t < 1


# --------------------------------------------------------------------------
# verzerrte Einzelelemente
# --------------------------------------------------------------------------
def verzerrt(typ, rng, amp=0.08):
    """Knoten eines verzerrten Elements: natuerliche Koordinaten affin abgebildet,
    Ecken zufaellig verschoben, Kantenmitten in der Mitte der Kanten."""
    A = np.array([[1.0, 0.2, -0.1], [0.1, 0.9, 0.15], [-0.05, 0.1, 1.1]])
    XI = KNOTEN_NAT[typ]
    ne = {"tet4": 4, "tet10": 4, "hex8": 8, "hex20": 8, "pent6": 6, "pent15": 6, "pyr5": 5}[typ]
    X = XI @ A.T
    X[:ne] += rng.uniform(-amp, amp, (ne, 3))
    if typ in KANTEN:
        for k, (a, b) in enumerate(KANTEN[typ]):
            X[ne + k] = 0.5 * (X[a] + X[b])
    return X


def t_starrkoerper(typ):
    rng = np.random.default_rng(3)
    X = verzerrt(typ, rng)
    K, V = k_elem(typ, X)
    lam = np.linalg.eigvalsh(K)
    ref = lam.max()
    null = int(np.sum(np.abs(lam) < 1e-9 * ref))
    rest = lam[np.abs(lam) >= 1e-9 * ref]
    check(f"{typ}: genau 6 Starrkoerpermoden", null == 6 and np.all(rest > 0),
          f"{null} Nulleigenwerte, kleinster Rest {rest.min() / ref:.1e}")
    check(f"{typ}: K symmetrisch", np.abs(K - K.T).max() < 1e-9 * ref)


def t_volumen():
    A = np.array([[1.2, 0.3, -0.2], [0.1, 0.8, 0.25], [-0.15, 0.2, 1.1]])   # Parallelepiped
    detA = abs(np.linalg.det(A))
    # Hex20: Ecken affin, Kantenmitten laengs der Kanten verschoben (bei 40 %)
    X = KNOTEN_NAT["hex20"] @ A.T
    for k, (a, b) in enumerate(_HEX_KANTEN):
        X[8 + k] = 0.6 * X[a] + 0.4 * X[b]
    close("hex20: Volumen, Mittelknoten auf den Kanten verschoben", sl.solid_volume("hex20", X),
          8 * detA, 1e-12)
    close("hex20: Volumen ueber k_hex20", k_elem("hex20", X)[1], 8 * detA, 1e-12)
    # Hex20: Einheitswuerfel mit gewoelbter Deckflaeche: obere Kantenmitten um d angehoben
    d = 0.15
    X = 0.5 * (KNOTEN_NAT["hex20"] + 1.0)
    X[12:16, 2] += d
    close("hex20: Volumen mit gekruemmter Deckflaeche (1 + 4d/3)", sl.solid_volume("hex20", X),
          1 + 4 * d / 3, 1e-12)
    # Keile: halbes Parallelepiped, Pent15 mit verschobenen Kantenmitten
    X6 = KNOTEN_NAT["pent6"] @ A.T
    close("pent6: Volumen = halbes Parallelepiped", sl.solid_volume("pent6", X6), detA, 1e-12)
    X15 = KNOTEN_NAT["pent15"] @ A.T
    for k, (a, b) in enumerate(_PENT_KANTEN):
        X15[6 + k] = 0.55 * X15[a] + 0.45 * X15[b]
    close("pent15: Volumen, Mittelknoten verschoben", sl.solid_volume("pent15", X15), detA, 1e-12)
    close("pent15: Volumen ueber k_pent15", k_elem("pent15", X15)[1], detA, 1e-12)
    # Pyramiden: Wuerfel mit innerem Punkt P in 6 Pyramiden, V_i = A * Abstand / 3
    P = np.array([0.4, 0.55, 0.45])
    m = Netz()
    ecken = [m.knoten(e, 0.5 * (np.array(e, float) + 1)) for e in _HEX_ECKEN]
    m.pyramiden(ecken, "P")
    m.X[-1] = P
    nodes, elems = m.fertig()
    abst = [P[2], 1 - P[2], P[1], 1 - P[0], 1 - P[1], P[0]]
    vs = [sl.solid_volume("pyr5", nodes[el]) for el in elems]
    check("pyr5: Volumen der 6 Pyramiden = Abstand/3", np.allclose(vs, np.array(abst) / 3, rtol=1e-12),
          f"Summe {sum(vs):.12f}")
    Xp = KNOTEN_NAT["pyr5"] @ A.T
    close("pyr5: Volumen affine Pyramide", k_elem("pyr5", Xp)[1], 8 / 3 * detA, 1e-12)


# --------------------------------------------------------------------------
# Patch-Test
# --------------------------------------------------------------------------
_GRAD = np.array([[1.0e-3, 2.0e-4, -3.0e-4], [4.0e-4, -5.0e-4, 6.0e-4], [-2.0e-4, 3.0e-4, 7.0e-4]])
_U0 = np.array([1.0e-4, -2.0e-4, 3.0e-4])


def _feld(x):
    return _U0 + _GRAD @ x


def patch_netz(typ, rng):
    """Kleiner Verband mit inneren Knoten.  Rueckgabe nodes, elems, innere Knoten."""
    m = Netz()
    quad = typ in ("hex20", "pent15")
    if typ == "hex20":
        # 2x2x2 Block, Ecken zufaellig verschoben, innere Kantenmitten gekruemmt
        def kn(i, j, k):
            return m.knoten((i, j, k), np.array([i, j, k]) * 0.5 + rng.uniform(-0.06, 0.06, 3))
        for k in range(2):
            for j in range(2):
                for i in range(2):
                    m.hex([kn(i, j, k), kn(i + 1, j, k), kn(i + 1, j + 1, k), kn(i, j + 1, k),
                           kn(i, j, k + 1), kn(i + 1, j, k + 1), kn(i + 1, j + 1, k + 1),
                           kn(i, j + 1, k + 1)], True)
        c = m.key[(1, 1, 1)]
        innen = [c] + [m.mid[(min(c, m.key[k]), max(c, m.key[k]))]
                       for k in [(0, 1, 1), (2, 1, 1), (1, 0, 1), (1, 2, 1), (1, 1, 0), (1, 1, 2)]]
        for i in innen[1:]:
            m.X[i] += rng.uniform(-0.03, 0.03, 3)         # gekruemmte innere Kanten
    elif typ.startswith("pent"):
        # Quadrat in 4 Dreiecke um einen inneren Punkt, zwei Schichten in z
        xy = [(0, 0), (1, 0), (1, 1), (0, 1), (0.45, 0.55)]
        zs = [0.0, 0.5, 1.0]

        def kn(p, layer):
            x = np.array([xy[p][0], xy[p][1], zs[layer]])
            if layer == 1:
                x += rng.uniform(-0.08, 0.08, 3)
            return m.knoten((p, layer), x)
        for layer in range(2):
            for a in range(4):
                b = (a + 1) % 4
                m.keil([kn(a, layer), kn(b, layer), kn(4, layer),
                        kn(a, layer + 1), kn(b, layer + 1), kn(4, layer + 1)], quad)
        c = m.key[(4, 1)]
        innen = [c]
        if quad:
            for k in [(0, 1), (1, 1), (2, 1), (3, 1), (4, 0), (4, 2)]:
                innen.append(m.mid[(min(c, m.key[k]), max(c, m.key[k]))])
    else:
        ecken = [m.knoten(e, 0.5 * (np.array(e, float) + 1) + rng.uniform(-0.05, 0.05, 3))
                 for e in _HEX_ECKEN]
        m.pyramiden(ecken, "P")
        m.X[-1] = np.array([0.4, 0.55, 0.45])
        innen = [m.key["P"]]
    nodes, elems = m.fertig()
    return nodes, elems, innen


def t_patch(typ):
    rng = np.random.default_rng(11)
    nodes, elems, innen = patch_netz(typ, rng)
    K = assemble(nodes, elems, typ)
    vorgabe = {}
    for n in range(len(nodes)):
        if n not in innen:
            for j in range(3):
                vorgabe[3 * n + j] = _feld(nodes[n])[j]
    u = loese(K, np.zeros(3 * len(nodes)), vorgabe)
    uex = np.array([_feld(x) for x in nodes]).ravel()
    e_u = np.abs(u - uex).max() / np.abs(uex).max()
    check(f"{typ}: Patch-Test, innere Knoten auf dem linearen Feld ({len(elems)} Elemente, "
          f"{len(innen)} innere Knoten)", e_u < 1e-9, f"max {e_u:.1e}")
    g = _GRAD + _GRAD.T              # Voigt: [exx, eyy, ezz, gxy, gyz, gzx], Gleitungen doppelt
    s_ex = sl.D_matrix(E_ST, NU_ST) @ np.array([g[0, 0] / 2, g[1, 1] / 2, g[2, 2] / 2,
                                                 g[0, 1], g[1, 2], g[0, 2]])
    worst = 0.0
    npkt = 0
    for el in elems:
        ue = u[dofs(el)]
        for sig in sl.stress_points(typ, nodes[list(el)], E_ST, NU_ST, ue):
            worst = max(worst, np.abs(sig - s_ex).max() / np.abs(s_ex).max())
            npkt += 1
    check(f"{typ}: Patch-Test, Spannung an allen {npkt} Auswertepunkten exakt", worst < 1e-8,
          f"max {worst:.1e}")
    check(f"{typ}: Auswertepunkte = Mitte + Ecken", len(sl.AUSWERTEPUNKTE[typ]) == npkt // len(elems)
          and sl.AUSWERTEPUNKTE[typ][0] not in [tuple(x) for x in KNOTEN_NAT[typ]])


# --------------------------------------------------------------------------
# Kragarm-Biegung
# --------------------------------------------------------------------------
def t_kragarm_quadratisch(typ, tol_grob, tol_fein):
    """L = 2, h = 0.2, b = 0.1: 1 Element ueber Hoehe und Breite.  Mit 4 Elementen
    ueber die Laenge ist der Verband bei Einzellast (kubische Biegelinie) noch
    zu steif; mit 16 Elementen liegt er dicht an Bernoulli + Timoshenko."""
    ana = balken_analytisch()
    w4, _ = kragarm(typ, 4, 1, 1)
    close(f"{typ}: Kragarm 4x1x1 gegen Bernoulli+Timoshenko", w4, ana, tol_grob)
    w16, _ = kragarm(typ, 16, 1, 1)
    close(f"{typ}: Kragarm 16x1x1 gegen Bernoulli+Timoshenko", w16, ana, tol_fein)
    check(f"{typ}: Kragarm konvergiert von unten", w4 < w16 < ana * 1.001)


def t_kragarm_konvergenz(typ, stufen):
    ana = balken_analytisch()
    ws = []
    for nx, ny, nz in stufen:
        w, _ = kragarm(typ, nx, ny, nz)
        ws.append(w)
        print(f"     {typ} {nx}x{ny}x{nz}: w/w_ana = {w / ana:.4f}")
    fehler = [abs(w - ana) / ana for w in ws]
    check(f"{typ}: Kragarm konvergiert monoton ({len(stufen)} Stufen)",
          all(fehler[i + 1] < fehler[i] for i in range(len(ws) - 1))
          and all(ws[i + 1] > ws[i] for i in range(len(ws) - 1)),
          "Abw. " + ", ".join(f"{f * 100:.1f} %" for f in fehler))
    close(f"{typ}: Kragarm feinste Stufe gegen Bernoulli+Timoshenko", ws[-1], ana, 0.15)


# --------------------------------------------------------------------------
# Flaechenlasten, Anfangsspannungen, Seiten, Massen
# --------------------------------------------------------------------------
def t_flaechenlast():
    rng = np.random.default_rng(5)
    p = 3.7e3
    R = np.linalg.qr(rng.normal(size=(3, 3)))[0]          # zufaellige Drehung
    if np.linalg.det(R) < 0:
        R[:, 0] = -R[:, 0]
    seiten = {
        "tri3": (np.array([[0, 0, 0], [2, 0, 0], [0.5, 1.5, 0]], float), None),
        "quad4": (np.array([[0, 0, 0], [2, 0, 0], [2.2, 1.6, 0], [-0.3, 1.4, 0]], float), None),
    }
    seiten["tri6"] = (_mit_mitten(seiten["tri3"][0], [(0, 1), (1, 2), (2, 0)]), None)
    seiten["quad8"] = (_mit_mitten(seiten["quad4"][0], [(0, 1), (1, 2), (2, 3), (3, 0)]), None)
    for name, (P0, _) in seiten.items():
        P = P0 @ R.T + np.array([1.0, -2.0, 0.5])
        k = len(P)
        ne = 3 if k in (3, 6) else 4
        # Flaeche und Schwerpunkt der ebenen Seite (Polygon der Ecken)
        n = R[:, 2]
        A = 0.0
        S = np.zeros(3)
        for i in range(1, ne - 1):
            a = 0.5 * np.cross(P[i] - P[0], P[i + 1] - P[0]) @ n
            A += a
            S += a * (P[0] + P[i] + P[i + 1]) / 3
        S /= A
        f = sl.flaechenlast_knoten(P, p)
        e_sum = np.abs(f.sum(axis=0) - p * A * n).max() / (p * A)
        M = np.sum(np.cross(P - S, f), axis=0)
        check(f"{name}: Summe der Knotenkraefte = p·A·n", e_sum < 1e-12, f"max {e_sum:.1e}")
        check(f"{name}: Momentengleichgewicht um den Schwerpunkt",
              np.abs(M).max() < 1e-10 * p * A, f"max {np.abs(M).max() / (p * A):.1e}")
        d = np.array([0.3, -0.4, 0.5])
        d /= np.linalg.norm(d)
        fd = sl.flaechenlast_knoten(P, p, richtung=d)
        check(f"{name}: mit Richtung: Summe = p·A·richtung",
              np.abs(fd.sum(axis=0) - p * A * d).max() < 1e-12 * p * A
              and np.allclose(np.linalg.norm(fd, axis=1), np.abs(f @ n), rtol=1e-12))
    # Vergleichswerte der Gleichlast: quad8 Ecken -pA/12, Mitten pA/3; tri6 Ecken 0, Mitten pA/3
    P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]], float)
    P8 = _mit_mitten(P, [(0, 1), (1, 2), (2, 3), (3, 0)])
    f = sl.flaechenlast_knoten(P8, p)[:, 2] / (p * 2.0)
    check("quad8: Gleichlast -> Ecken -pA/12, Mitten pA/3",
          np.allclose(f, [-1 / 12] * 4 + [1 / 3] * 4, atol=1e-13), np.array2string(f, precision=4))
    P6 = _mit_mitten(P[:3], [(0, 1), (1, 2), (2, 0)])
    f = sl.flaechenlast_knoten(P6, p)[:, 2] / (p * 1.0)
    check("tri6: Gleichlast -> Ecken 0, Mitten pA/3",
          np.allclose(f, [0] * 3 + [1 / 3] * 3, atol=1e-13), np.array2string(f, precision=4))
    P3 = P[:3]
    f = sl.flaechenlast_knoten(P3, p)[:, 2] / (p * 1.0)
    check("tri3: Gleichlast -> je pA/3", np.allclose(f, 1 / 3, atol=1e-13))
    f = sl.flaechenlast_knoten(P, p)[:, 2] / (p * 2.0)
    check("quad4: Gleichlast -> je pA/4", np.allclose(f, 1 / 4, atol=1e-13))


def wuerfel_netz(typ):
    """Einheitswuerfel aus Elementen des Typs (Tetraeder: 6 Kuhn-Tetraeder)."""
    m = Netz()
    ecken = [m.knoten(e, 0.5 * (np.array(e, float) + 1)) for e in _HEX_ECKEN]
    quad = typ in ("tet10", "hex20", "pent15")
    if typ.startswith("hex"):
        m.hex(ecken, quad)
    elif typ.startswith("pent"):
        e = ecken
        m.keil([e[0], e[1], e[2], e[4], e[5], e[6]], quad)
        m.keil([e[0], e[2], e[3], e[4], e[6], e[7]], quad)
    elif typ == "pyr5":
        m.pyramiden(ecken, "P")
    else:
        X = np.array(m.X)
        for perm in [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]:
            pts = [np.zeros(3)]
            for ax in perm:
                q = pts[-1].copy()
                q[ax] = 1.0
                pts.append(q)
            el = [int(np.argmin(np.linalg.norm(X - q, axis=1))) for q in pts]
            if np.linalg.det(np.array([X[el[i]] - X[el[0]] for i in (1, 2, 3)])) < 0:
                el[1], el[2] = el[2], el[1]
            if quad:
                el += [m.mitte(el[a], el[b]) for a, b in _TET_KANTEN]
            m.elems.append(el)
    return m.fertig()


def t_anfangsspannung():
    s0 = np.array([1.0, 0, 0, 0, 0, 0])
    for typ in ALLE:
        nodes, elems = wuerfel_netz(typ)
        F = np.zeros((len(nodes), 3))
        for el in elems:
            F[list(el)] += sl.anfangsspannungs_lasten(typ, nodes[list(el)], s0).reshape(-1, 3)
        ok = np.abs(F.sum(axis=0)).max() < 1e-12
        seiten = {"x=0": (0, 0.0, -1.0), "x=1": (0, 1.0, 1.0), "y=0": (1, 0.0, 0.0),
                  "y=1": (1, 1.0, 0.0), "z=0": (2, 0.0, 0.0), "z=1": (2, 1.0, 0.0)}
        info = []
        for name, (ax, wert, soll) in seiten.items():
            auf = np.abs(nodes[:, ax] - wert) < 1e-12
            fx = F[auf].sum(axis=0)
            ok = ok and abs(fx[0] - soll) < 1e-12 and np.abs(fx[1:]).max() < 1e-12
            info.append(f"{name}: {fx[0]:+.3f}")
        check(f"{typ}: Anfangsspannung sx = 1 auf Wuerfel ({len(elems)} El.): Seitensummen +-A, gesamt 0",
              ok, "  ".join(info))
        V = sum(sl.solid_volume(typ, nodes[list(el)]) for el in elems)
        close(f"{typ}: Wuerfelvolumen aus solid_volume", V, 1.0, 1e-12)


def t_flaechen():
    try:
        from statik3d.assemble import SOLID_FACES
    except Exception as ex:                                 # pragma: no cover
        SOLID_FACES = None
        print(f"     (assemble nicht importierbar: {ex})")
    for typ in ALLE:
        XI = KNOTEN_NAT[typ]
        n_ecken = len(XI) - len(KANTEN.get(typ, []))
        mitte = np.array([0.0, 0.0, -0.5]) if typ == "pyr5" else XI[:n_ecken].mean(axis=0)
        faces = sl.FLAECHEN[typ]
        ecken = sl.FLAECHEN_ECKEN[typ]
        ok_mid = ok_aussen = True
        richtung = []
        for f, fe in zip(faces, ecken):
            ne = len(fe)
            ok_mid = ok_mid and tuple(f[:ne]) == tuple(fe)
            for k in range(ne, len(f)):                  # Kantenmitten in Kantenreihenfolge
                a, b = fe[k - ne], fe[(k - ne + 1) % ne]
                ok_mid = ok_mid and np.allclose(XI[f[k]], 0.5 * (XI[a] + XI[b]))
            n = np.cross(XI[fe[1]] - XI[fe[0]], XI[fe[2]] - XI[fe[0]])
            aussen = n @ (XI[list(fe)].mean(axis=0) - mitte) > 0
            richtung.append("aussen" if aussen else "innen")
            ok_aussen = ok_aussen and aussen
        nseiten = 4 if typ.startswith("tet") else 5 if typ in ("pent6", "pent15", "pyr5") else 6
        alle_knoten = set(sum((list(f) for f in faces), []))
        check(f"{typ}: FLAECHEN: {nseiten} Seiten, Ecken zuerst, Kantenmitten passend",
              len(faces) == nseiten and ok_mid and alle_knoten == set(range(sl.knotenzahl(typ))))
        if typ in NEU:
            check(f"{typ}: FLAECHEN: Rechtsschraube der Ecken zeigt nach aussen", ok_aussen,
                  ", ".join(richtung))
        else:
            print(f"     {typ}: Rechtsschraube der Seiten (Bezug assemble.SOLID_FACES): "
                  + ", ".join(richtung))
            if SOLID_FACES is not None:
                check(f"{typ}: FLAECHEN_ECKEN identisch mit assemble.SOLID_FACES",
                      [tuple(f) for f in ecken] == [tuple(f) for f in SOLID_FACES[typ]])
    # Seitenlast ueber FLAECHEN eines verzerrten Elements: Summe = p * Vektorflaeche der Seite
    rng = np.random.default_rng(9)
    for typ in NEU:
        X = verzerrt(typ, rng)
        ok = True
        for f, fe in zip(sl.FLAECHEN[typ], sl.FLAECHEN_ECKEN[typ]):
            P = X[list(f)]
            fs = sl.flaechenlast_knoten(P, 1.0).sum(axis=0)
            An = np.zeros(3)
            for i in range(1, len(fe) - 1):
                An += 0.5 * np.cross(X[fe[i]] - X[fe[0]], X[fe[i + 1]] - X[fe[0]])
            ok = ok and np.allclose(fs, An, rtol=1e-10, atol=1e-14)
        check(f"{typ}: Flaechenlast auf jeder Seite = p * Vektorflaeche", ok)


def t_massen():
    rng = np.random.default_rng(13)
    rho = 7850.0
    for typ in ALLE:
        X = verzerrt(typ, rng)
        m = sl.lumped_mass(typ, X, rho)
        V = sl.solid_volume(typ, X)
        check(f"{typ}: Lumped-Massen positiv, Summe = rho·V",
              np.all(m > 0) and abs(m.sum() / 3 - rho * V) < 1e-9 * rho * V
              and np.allclose(m[0::3], m[1::3]) and np.allclose(m[0::3], m[2::3]),
              f"min {m.min():.4g}, Summe/3 {m.sum() / 3:.6g}, rho V {rho * V:.6g}")


# --------------------------------------------------------------------------
def main():
    print("=" * 100)
    print("STATIK3D - Volumenelemente Hex20, Pent6, Pent15, Pyr5")
    print("=" * 100)
    print("\n-- Formfunktionen und Gauss-Regeln ----------------------------------------------")
    t_formfunktionen()
    print("\n-- Starrkoerpermoden ---------------------------------------------------------------")
    for typ in NEU:
        t_starrkoerper(typ)
    print("\n-- Volumen ---------------------------------------------------------------------------")
    t_volumen()
    print("\n-- Patch-Test ------------------------------------------------------------------------")
    for typ in NEU:
        t_patch(typ)
    print("\n-- Kragarm-Biegung -------------------------------------------------------------------")
    t_kragarm_quadratisch("hex20", 0.05, 0.02)
    t_kragarm_quadratisch("pent15", 0.05, 0.03)
    t_kragarm_konvergenz("pent6", [(10, 1, 1), (20, 2, 2), (40, 4, 4)])
    t_kragarm_konvergenz("pyr5", [(6, 1, 1), (12, 2, 2), (24, 4, 4)])
    print("\n-- Flaechenlasten --------------------------------------------------------------------")
    t_flaechenlast()
    print("\n-- Anfangsspannungen -----------------------------------------------------------------")
    t_anfangsspannung()
    print("\n-- Seiten ----------------------------------------------------------------------------")
    t_flaechen()
    print("\n-- Massen ----------------------------------------------------------------------------")
    t_massen()
    print("\n" + "=" * 100)
    nok = sum(1 for r in RESULTS if r[1])
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    print("=" * 100)
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
