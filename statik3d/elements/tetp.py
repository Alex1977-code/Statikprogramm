"""
Tetraeder mit Ordnung p je Element (hierarchischer Ansatz, p = 2..4).

Das Element hat vier Eckknoten mit den gewohnten drei Verschiebungen. Die
hoeheren Ansaetze sind **hierarchische** Funktionen an Kanten, Flaechen und im
Inneren; ihre Freiheitsgrade haengen an keinem Knoten, sondern liegen wie die
Woelb-FHG hinter den Knoten-FHG (``Anreicherung``). Fuer Kontakt, Lager,
Fugen und Anzeige bleibt das Netz ein Netz aus Ecken.

Herkunft (nichts davon ist neu): hierarchische Ansaetze der p-Version nach
Szabo/Babuska (Finite Element Analysis, 1991) und Zienkiewicz/Gago/Kelly
(1983); quadratische Geometrie wie beim isoparametrischen tet10; die
Integrationsregeln mit 14 und 24 Punkten sind die bekannten von Walkington
bzw. Keast, hier aus den Momentengleichungen neu bestimmt und im Test gegen
alle Monome geprueft.

Funktionen je Element fuer die Hoechstordnung P, in dieser Reihenfolge:

  Ecken i = 0..3                    L_i
  Kanten k = 0..5, q = 2..P         L_a L_b (L_b - L_a)^(q-2)
  Flaechen f = 0..3, q = 3          L_a L_b L_c
                     q = 4          L_a L_b L_c (L_b - L_a),  L_a L_b L_c (L_c - L_a)
  Inneres, q = 4                    L_1 L_2 L_3 L_4

a < b < c nach **globaler** Knotennummer; darum sehen zwei Nachbarn an ihrer
gemeinsamen Kante bzw. Flaeche dieselbe Funktion. p = 2 ist genau der Raum
des tet10, p = 1 der des tet4.

Warum hierarchisch und nicht der tet10 mit Mittenknoten: Die Ordnung kann
von Element zu Element wechseln, ohne dass eine Kopplung noetig ist - eine
Kante, die ein Nachbar nicht mittraegt (tet4, Kontaktflaeche), bekommt
schlicht keine Kantenfunktion, und die Spur auf der Seite ist dort linear wie
beim tet4. Gemessen im Labor 22.09.2026 (Einkern): Kragarm 1,0 x 0,1 x 0,2 m,
sigma_v an der Oberkante auf 355 N/mm2 - p = 3 auf 30 Tetraedern 720 FHG,
Abweichung aller Elemente an der Stelle <= 0,18 N/mm2; tet10 braucht fuer
+1,0 N/mm2 im Mittel 14.688 FHG. Lame-Hohlzylinder aus dem Statik3D-
Vernetzer mit gekruemmter Bohrung (1.400 Tetraeder): Knotenmittel am
Innenrand p = 2/3/4 -> 14,8/1,85/0,39 N/mm2 bei 6.407/20.754/48.129 FHG.
"""
from __future__ import annotations

import numpy as np

#: Elementtypen und ihre Ordnung
TYPEN = {"tetp2": 2, "tetp3": 3, "tetp4": 4}
P_MAX = 4

#: lokale Kanten und Flaechen der hierarchischen Funktionen (Flaeche i liegt
#: gegenueber Ecke i). Die Seitennummern fuer Lasten sind die des tet4
#: (solid.FLAECHEN["tet4"]), siehe SEITEN.
KANTEN = ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
FLAECHEN = ((1, 2, 3), (0, 2, 3), (0, 1, 3), (0, 1, 2))
#: Seiten wie beim tet4 (Lasten, Kontakt, Fugen): Eckentripel
SEITEN = ((0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3))
#: Knotenfolge der Kantenmitten eines tet10 in Statik3D (solid.tet10_N_dN):
#: 4 = M(0,1), 5 = M(1,2), 6 = M(0,2), 7 = M(0,3), 8 = M(1,3), 9 = M(2,3)
TET10_KANTEN = ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))


def ordnung(typ: str) -> int:
    try:
        return TYPEN[typ]
    except KeyError:
        raise ValueError(f"kein Tetraeder mit Ordnung: {typ}") from None


# --------------------------------------------------------------------------
# Integrationsregeln (Schwerpunktkoordinaten, Gewichte mit Summe 1)
# --------------------------------------------------------------------------
def _bahn_s31(a):
    return [np.roll(np.array([1.0 - 3.0 * a, a, a, a]), k) for k in range(4)]


def _bahn_s22(a):
    b = 0.5 - a
    return [np.array(p) for p in ((a, a, b, b), (a, b, a, b), (a, b, b, a),
                                  (b, a, a, b), (b, a, b, a), (b, b, a, a))]


def _bahn_s211(a, b):
    c = 1.0 - 2.0 * a - b
    pts = []
    for i in range(4):
        for j in range(4):
            if i == j:
                continue
            p = np.full(4, a)
            p[i] = b
            p[j] = c
            pts.append(p)
    return pts


def _regel(bahnen):
    L, W = [], []
    for pts, w in bahnen:
        L.extend(pts)
        W.extend([w] * len(pts))
    return np.array(L), np.array(W)


#: Grad -> (L, W). Grad 2: 4 Punkte; Grad 5: 14 Punkte (Walkington);
#: Grad 6: 24 Punkte (Keast). Alle Gewichte positiv. Die Werte sind aus den
#: Momentengleichungen bestimmt (22.09.2026) und in tests/test_tetp.py gegen
#: alle Monome bis zum Grad geprueft.
REGELN = {
    2: _regel([(_bahn_s31(0.13819660112501053), 0.25)]),
    5: _regel([(_bahn_s31(0.31088591926330067), 0.11268792571801645),
               (_bahn_s31(0.0927352503108913), 0.07349304311636214),
               (_bahn_s22(0.045503704125649), 0.04254602077708094)]),
    6: _regel([(_bahn_s31(0.04067395853461113), 0.010077211055320627),
               (_bahn_s31(0.3223378901422761), 0.05535718154365377),
               (_bahn_s31(0.214602871259158), 0.03992275025816567),
               (_bahn_s211(0.06366100187501848, 0.26967233145831565), 0.04821428571428662)]),
}


def regel_konisch(n: int):
    """Konisches Produkt aus Gauss-Jacobi-Regeln, exakt bis Grad 2n-1."""
    from scipy.special import roots_jacobi
    a, wa = roots_jacobi(n, 2, 0)
    b, wb = roots_jacobi(n, 1, 0)
    c, wc = roots_jacobi(n, 0, 0)
    a, b, c = (a + 1) / 2, (b + 1) / 2, (c + 1) / 2
    A, Bm, Cm = np.meshgrid(a, b, c, indexing="ij")
    WA, WB, WC = np.meshgrid(wa, wb, wc, indexing="ij")
    x = A.ravel()
    y = (Bm * (1 - A)).ravel()
    z = (Cm * (1 - A) * (1 - Bm)).ravel()
    W = (WA * WB * WC).ravel()
    W = W / W.sum()
    return np.column_stack([1 - x - y - z, x, y, z]), W


def regel(grad: int):
    """Die kleinste vorhandene Regel, die Polynome bis ``grad`` exakt integriert."""
    for g in sorted(REGELN):
        if g >= grad:
            return REGELN[g]
    return regel_konisch((grad + 2) // 2)


def steifigkeitsregel(P: int, krumm: bool):
    """Regel fuer B^T D B: Grad 2(P-1) bei geraden Elementen. Bei gekruemmten
    ist der Integrand rational; mindestens Grad P+1 braucht es dort, damit
    der Patch-Test haelt (int grad N dV = int cof(J) grad_xi N ist ein
    Polynom vom Grad P+1)."""
    return regel(max(2 * (P - 1), P + 1) if krumm else max(2 * (P - 1), 1))


# --------------------------------------------------------------------------
# Ansatzfunktionen
# --------------------------------------------------------------------------
def funktionen(P: int) -> list:
    """(Art, lokale Entitaet, Grad q, Nummer in der Entitaet) je Funktion."""
    if not 1 <= P <= P_MAX:
        raise ValueError(f"Ordnung {P} nicht vorgesehen (1..{P_MAX})")
    out = [("e", i, 1, 0) for i in range(4)]
    for k in range(6):
        for q in range(2, P + 1):
            out.append(("k", k, q, q - 2))
    for f in range(4):
        if P >= 3:
            out.append(("f", f, 3, 0))
        if P >= 4:
            out.append(("f", f, 4, 1))
            out.append(("f", f, 4, 2))
    if P >= 4:
        out.append(("i", 0, 4, 0))
    return out


def funktionszahl(P: int) -> int:
    return (P + 1) * (P + 2) * (P + 3) // 6


def je_entitaet(q: int, art: str) -> int:
    """Zahl der Funktionen einer Entitaet der Ordnung q."""
    if art == "k":
        return max(q - 1, 0)
    if art == "f":
        return (q - 1) * (q - 2) // 2 if q >= 3 else 0
    return (q - 1) * (q - 2) * (q - 3) // 6 if q >= 4 else 0


def basis_ref(L, P):
    """Werte (m,nf) und Ableitungen nach L (m,nf,4), lokal orientiert."""
    L = np.asarray(L, float)
    m = L.shape[0]
    F, dF = [], []
    for i in range(4):
        d = np.zeros((m, 4))
        d[:, i] = 1.0
        F.append(L[:, i].copy())
        dF.append(d)
    for (i, j) in KANTEN:
        a, b = L[:, i], L[:, j]
        s = b - a
        for q in range(2, P + 1):
            mm = q - 2
            sm = s ** mm
            sm1 = s ** (mm - 1) if mm >= 1 else np.zeros(m)
            d = np.zeros((m, 4))
            d[:, i] = b * sm - mm * a * b * sm1
            d[:, j] = a * sm + mm * a * b * sm1
            F.append(a * b * sm)
            dF.append(d)
    if P >= 3:
        for (i, j, k) in FLAECHEN:
            bl = L[:, i] * L[:, j] * L[:, k]
            db = np.zeros((m, 4))
            db[:, i] = L[:, j] * L[:, k]
            db[:, j] = L[:, i] * L[:, k]
            db[:, k] = L[:, i] * L[:, j]
            F.append(bl)
            dF.append(db)
            if P >= 4:
                # Blase * (L_x - L_i): mit Blase * L_x waere Blase = sum_x Blase L_x
                # + L1 L2 L3 L4 linear abhaengig von der Innenblase (so im Labor
                # gemessen: Patch-Test p = 4 um 7,7 % daneben)
                for x in (j, k):
                    s = L[:, x] - L[:, i]
                    d = db * s[:, None]
                    d[:, x] += bl
                    d[:, i] -= bl
                    F.append(bl * s)
                    dF.append(d)
    if P >= 4:
        d = np.zeros((m, 4))
        for i in range(4):
            d[:, i] = np.prod(np.delete(L, i, axis=1), axis=1)
        F.append(np.prod(L, axis=1))
        dF.append(d)
    return np.array(F).T, np.stack(dF, axis=1)


def orientierung(g, P):
    """Lokal -> global orientierte Funktionen: F_glob = F_ref @ C, C (n,nf,nf).

    Kantenfunktionen ungerader Potenz wechseln mit der Richtung ihr Vorzeichen;
    die beiden Flaechenfunktionen q = 4 mischen sich mit der Reihenfolge der
    globalen Nummern ihrer Ecken (2x2 je Flaeche)."""
    g = np.asarray(g)
    n = g.shape[0]
    fu = funktionen(P)
    nf = len(fu)
    C = np.zeros((n, nf, nf))
    idx = np.arange(nf)
    C[:, idx, idx] = 1.0
    pos = {(a, e, q, r): c for c, (a, e, q, r) in enumerate(fu)}
    for k, (i, j) in enumerate(KANTEN):
        vz = np.where(g[:, i] < g[:, j], 1.0, -1.0)
        for q in range(3, P + 1, 2):
            c = pos[("k", k, q, q - 2)]
            C[:, c, c] = vz
    if P >= 4:
        vek = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
        for f, (i, j, k) in enumerate(FLAECHEN):
            c1, c2 = pos[("f", f, 4, 1)], pos[("f", f, 4, 2)]
            ordn = np.argsort(g[:, [i, j, k]], axis=1)
            va, vb, vc = vek[ordn[:, 0]], vek[ordn[:, 1]], vek[ordn[:, 2]]
            n1, n2 = vb - va, vc - va
            C[:, c1, c1] = n1[:, 0]
            C[:, c2, c1] = n1[:, 1]
            C[:, c1, c2] = n2[:, 0]
            C[:, c2, c2] = n2[:, 1]
    return C


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------
def geometrie(X):
    """Geometriepunkte (n,10,3) in tet10-Folge. X ist (n,4,3) - gerade, die
    Kantenmitten werden ergaenzt - oder (n,10,3) mit Kantenmitten auf der
    wahren Geometrie."""
    X = np.asarray(X, float)
    if X.shape[1] == 10:
        return X
    if X.shape[1] != 4:
        raise ValueError(f"Geometrie mit {X.shape[1]} Punkten (4 oder 10)")
    M = np.stack([0.5 * (X[:, a] + X[:, b]) for a, b in TET10_KANTEN], axis=1)
    return np.concatenate([X, M], axis=1)


def _geometrie_ableitungen(L):
    """d N_geo / d xi (m,10,3), xi = (L1, L2, L3), L0 = 1 - xi1 - xi2 - xi3."""
    L = np.asarray(L, float)
    m = L.shape[0]
    dN = np.zeros((m, 10, 4))
    for i in range(4):
        dN[:, i, i] = 4 * L[:, i] - 1
    for k, (i, j) in enumerate(TET10_KANTEN):
        dN[:, 4 + k, i] = 4 * L[:, j]
        dN[:, 4 + k, j] = 4 * L[:, i]
    return dN[:, :, 1:] - dN[:, :, [0]]


def geometrie_werte(L):
    """N_geo (m,10) - Lage eines Punktes aus den zehn Geometriepunkten."""
    L = np.asarray(L, float)
    N = np.zeros((L.shape[0], 10))
    for i in range(4):
        N[:, i] = L[:, i] * (2 * L[:, i] - 1)
    for k, (i, j) in enumerate(TET10_KANTEN):
        N[:, 4 + k] = 4 * L[:, i] * L[:, j]
    return N


def jacobi(G, L):
    """J (n,m,3,3) = dx/dxi und det J (n,m) an den Punkten L."""
    J = np.einsum("nka,mkj->nmaj", G, _geometrie_ableitungen(L))
    return J, np.linalg.det(J)


#: Pruefpunkte fuer gekruemmte Elemente: Ecken und Kantenmitten. An den
#: Integrationspunkten allein faellt ein umgeklapptes Element nicht auf -
#: gemessen 23.09.2026 am Einheitstetraeder mit der Mitte der Kante 0-1 bei
#: (0,2; 0; 0), also zwischen Viertelpunkt und Ecke: det J an allen 14
#: Integrationspunkten >= 0,245, an der Ecke 0 aber -0,200.
_PRUEFPUNKTE = np.vstack([np.eye(4)] + [0.5 * (np.eye(4)[a] + np.eye(4)[b]) for a, b in TET10_KANTEN])


def pruefe_jacobi(G, elemente=None, schwelle=0.0):
    """ValueError mit Elementnummer, wenn det J an einer Ecke oder Kantenmitte
    nicht ueber ``schwelle`` mal 6 V (gerades Element) liegt."""
    _J, detJ = jacobi(G, _PRUEFPUNKTE)
    V = np.abs(np.linalg.det(G[:, 1:4] - G[:, [0]])) / 6.0
    schlecht = detJ.min(axis=1) <= schwelle * 6.0 * V
    if np.any(schlecht):
        i = int(np.nonzero(schlecht)[0][0])
        nr = int(elemente[i]) + 1 if elemente is not None else i
        wo = f"Element {nr}" if elemente is not None else f"Element {i} im Stapel"
        raise ValueError(f"Tetraeder mit Ordnung p: {wo} ist umgeklappt oder zu stark "
                         f"gekruemmt (kleinste det J {detJ[i].min():.3e} an Ecke oder "
                         "Kantenmitte) - die Kantenmitte gerade lassen oder neu vernetzen")


def gradienten(G, dF, L, elemente=None):
    """Gradienten (n,m,nf,3) der lokal orientierten Funktionen nach x und dV/w
    = det J / 6 (n,m). Nicht positive det J -> ValueError mit Elementnummer
    (``elemente`` gibt die Nummern im Modell an, sonst die Stelle im Stapel)."""
    J, detJ = jacobi(G, L)
    if np.any(detJ <= 0):
        i = int(np.argmin(detJ.min(axis=1)))
        nr = int(elemente[i]) + 1 if elemente is not None else i
        wo = f"Element {nr}" if elemente is not None else f"Element {i} im Stapel"
        raise ValueError(f"Tetraeder mit Ordnung p: {wo} hat eine nicht positive "
                         f"Jacobi-Determinante (det J = {detJ[i].min():.3e}) - das "
                         "Element ist umgeklappt oder entartet, gekruemmt zu stark")
    Jinv = np.linalg.inv(J)
    dfdxi = dF[:, :, 1:] - dF[:, :, [0]]
    return np.einsum("mfk,nmka->nmfa", dfdxi, Jinv), detJ / 6.0


def _global(Gx, C, maske):
    """Lokale Gradienten (n,m,nf,3) global orientieren und maskieren."""
    Gx = np.einsum("nmfa,nfh->nmha", Gx, C)
    if maske is not None:
        Gx = Gx * np.asarray(maske, float)[:, None, :, None]
    return Gx


# --------------------------------------------------------------------------
# Elementmatrizen und -vektoren, gestapelt
# --------------------------------------------------------------------------
def _stapelgroesse(nf: int) -> int:
    # A (n,nf,nf,3,3) in double: 20 MB je Block
    return max(16, int(20e6 / (8 * 9 * nf * nf)))


def steifigkeit_stapel(X, g, P, E, nu, maske=None, elemente=None, krumm=None):
    """Steifigkeiten (n, 3nf, 3nf) und Volumen (n,) eines Stapels gleicher
    Hoechstordnung P und gleichen Werkstoffs.

    X (n,4,3) oder (n,10,3), g (n,4) globale Eckennummern (Orientierung),
    maske (n,nf) - False fuer Funktionen, deren Entitaet eine kleinere Ordnung
    hat (ihre Zeilen und Spalten bleiben null). Isotrop: K_ab = int lam da db^T
    + mu db da^T + mu (da.db) I."""
    G = geometrie(X)
    n = G.shape[0]
    nf = funktionszahl(P)
    if krumm is None:
        krumm = X.shape[1] == 10
    if krumm:
        pruefe_jacobi(G, elemente)
    L, W = steifigkeitsregel(P, krumm)
    _F, dF = basis_ref(L, P)
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    K = np.empty((n, 3 * nf, 3 * nf))
    V = np.empty(n)
    blk = _stapelgroesse(nf)
    for a in range(0, n, blk):
        s = slice(a, a + blk)
        el = None if elemente is None else np.asarray(elemente)[s]
        Gx, dV = gradienten(G[s], dF, L, el)
        Gx = _global(Gx, orientierung(np.asarray(g)[s], P), None if maske is None else np.asarray(maske)[s])
        wV = W[None, :] * dV
        A = np.einsum("nm,nmai,nmbj->nabij", wV, Gx, Gx)
        tr = np.einsum("nabii->nab", A)
        Kb = lam * A + mu * A.transpose(0, 1, 2, 4, 3) + mu * tr[..., None, None] * np.eye(3)
        K[s] = Kb.transpose(0, 1, 3, 2, 4).reshape(-1, 3 * nf, 3 * nf)
        V[s] = wV.sum(axis=1)
    return K, V


def B_aus_grad(Gx):
    """Gradienten (..., nf, 3) -> Verzerrungsmatrix (..., 6, 3nf), Dehnungsfolge
    [exx, eyy, ezz, gxy, gyz, gzx] wie in elements.solid."""
    sh = Gx.shape[:-2]
    nf = Gx.shape[-2]
    B = np.zeros(sh + (6, 3 * nf))
    B[..., 0, 0::3] = Gx[..., 0]
    B[..., 1, 1::3] = Gx[..., 1]
    B[..., 2, 2::3] = Gx[..., 2]
    B[..., 3, 0::3] = Gx[..., 1]
    B[..., 3, 1::3] = Gx[..., 0]
    B[..., 4, 1::3] = Gx[..., 2]
    B[..., 4, 2::3] = Gx[..., 1]
    B[..., 5, 0::3] = Gx[..., 2]
    B[..., 5, 2::3] = Gx[..., 0]
    return B


def dehnungen_stapel(X, g, P, U, punkte, maske=None, elemente=None):
    """Dehnungen (n,q,6) an den Punkten ``punkte`` (q,3) in natuerlichen
    Koordinaten (r, s, t) mit L0 = 1 - r - s - t. U (n, 3nf) - die
    Elementfreiheitsgrade in Funktionsfolge."""
    G = geometrie(X)
    pk = np.asarray(punkte, float).reshape(-1, 3)
    L = np.column_stack([1 - pk.sum(axis=1), pk])
    _F, dF = basis_ref(L, P)
    Gx, _dV = gradienten(G, dF, L, elemente)
    Gx = _global(Gx, orientierung(g, P), maske)
    U = np.asarray(U, float).reshape(G.shape[0], -1, 3)          # (n,nf,3)
    H = np.einsum("nqfa,nfi->nqia", Gx, U)                        # du_i/dx_a
    eps = np.empty(H.shape[:2] + (6,))
    eps[..., 0] = H[..., 0, 0]
    eps[..., 1] = H[..., 1, 1]
    eps[..., 2] = H[..., 2, 2]
    eps[..., 3] = H[..., 0, 1] + H[..., 1, 0]
    eps[..., 4] = H[..., 1, 2] + H[..., 2, 1]
    eps[..., 5] = H[..., 0, 2] + H[..., 2, 0]
    return eps


def masse_stapel(X, g, P, rho, maske=None, elemente=None):
    """Konsistente Massenmatrizen (n, 3nf, 3nf). Hierarchische Funktionen
    haben keine sinnvolle Zeilensummen-Masse (sie sind am Knoten null)."""
    G = geometrie(X)
    L, W = regel(2 * P + (3 if X.shape[1] == 10 else 0))
    F, dF = basis_ref(L, P)
    C = orientierung(g, P)
    _J, detJ = jacobi(G, L)
    Fg = np.einsum("mf,nfh->nmh", F, C)
    if maske is not None:
        Fg = Fg * np.asarray(maske, float)[:, None, :]
    M = rho * np.einsum("nm,nma,nmb->nab", W[None, :] * detJ / 6.0, Fg, Fg)
    nf = M.shape[1]
    return np.einsum("nab,ij->naibj", M, np.eye(3)).reshape(-1, 3 * nf, 3 * nf)


def volumenlast_stapel(X, g, P, b, maske=None):
    """Konsistente Lasten (n, 3nf) einer gleichmaessigen Volumenkraft b (3,)
    [N/m^3], etwa rho * Erdbeschleunigung."""
    G = geometrie(X)
    L, W = regel(P + (3 if X.shape[1] == 10 else 0))
    F, _dF = basis_ref(L, P)
    Fg = np.einsum("mf,nfh->nmh", F, orientierung(g, P))
    if maske is not None:
        Fg = Fg * np.asarray(maske, float)[:, None, :]
    _J, detJ = jacobi(G, L)
    s = np.einsum("nm,nmf->nf", W[None, :] * detJ / 6.0, Fg)
    return (s[:, :, None] * np.asarray(b, float)[None, None, :]).reshape(len(G), -1)


def anfangsspannung_stapel(X, g, P, s0, maske=None, elemente=None):
    """f = int B^T s0 dV (n, 3nf) einer je Element gleichmaessigen
    Anfangsspannung s0 (n,6) oder (6,) - Temperatur, Vorspannung."""
    G = geometrie(X)
    krumm = X.shape[1] == 10
    L, W = regel(P + 1 if krumm else max(P - 1, 1))
    _F, dF = basis_ref(L, P)
    Gx, dV = gradienten(G, dF, L, elemente)
    Gx = _global(Gx, orientierung(g, P), maske)
    s0 = np.broadcast_to(np.asarray(s0, float), (G.shape[0], 6))
    S = np.empty(s0.shape[:1] + (3, 3))
    S[:, 0, 0], S[:, 1, 1], S[:, 2, 2] = s0[:, 0], s0[:, 1], s0[:, 2]
    S[:, 0, 1] = S[:, 1, 0] = s0[:, 3]
    S[:, 1, 2] = S[:, 2, 1] = s0[:, 4]
    S[:, 0, 2] = S[:, 2, 0] = s0[:, 5]
    f = np.einsum("nm,nmfa,nia->nfi", W[None, :] * dV, Gx, S)
    return f.reshape(len(G), -1)


def seitenlast(X, g, P, seite, p, richtung=None, maske=None):
    """Konsistente Lasten (3nf,) eines Drucks p [N/m^2] auf die Seite
    ``seite`` (tet4-Nummer, SEITEN) eines Elements; positiv = nach innen wie
    assemble.solid_face_pressure. Mit ``richtung`` wirkt p in dieser Richtung
    (Betrag p je Flaecheninhalt). Gekruemmte Seiten werden auf ihrer
    quadratischen Geometrie integriert."""
    if not 0 <= int(seite) < 4:
        raise ValueError(f"tetp: Seite {seite} gibt es nicht (0..3)")
    G = geometrie(np.asarray(X, float)[None])[0]
    ecken = SEITEN[int(seite)]
    gegen = [i for i in range(4) if i not in ecken][0]
    from scipy.special import roots_jacobi
    n = P + 3
    a, wa = roots_jacobi(n, 1, 0)
    c, wc = roots_jacobi(n, 0, 0)
    a, c = (a + 1) / 2, (c + 1) / 2
    AA, CC = np.meshgrid(a, c, indexing="ij")
    u = AA.ravel()
    v = (CC * (1 - AA)).ravel()
    w = np.outer(wa, wc).ravel()
    w = 0.5 * w / w.sum()                       # Referenzdreieck: Flaeche 1/2
    L = np.zeros((len(u), 4))
    L[:, ecken[0]] = 1 - u - v
    L[:, ecken[1]] = u
    L[:, ecken[2]] = v
    F, _dF = basis_ref(L, P)
    Fg = F @ orientierung(np.asarray(g)[None], P)[0]
    if maske is not None:
        Fg = Fg * np.asarray(maske, float)[None, :]
    # Tangenten der Seite aus der quadratischen Geometrie
    dN = np.zeros((len(u), 10, 4))
    for i in range(4):
        dN[:, i, i] = 4 * L[:, i] - 1
    for k, (i, j) in enumerate(TET10_KANTEN):
        dN[:, 4 + k, i] = 4 * L[:, j]
        dN[:, 4 + k, j] = 4 * L[:, i]
    xu = np.einsum("ka,mk->ma", G, dN[:, :, ecken[1]] - dN[:, :, ecken[0]])
    xv = np.einsum("ka,mk->ma", G, dN[:, :, ecken[2]] - dN[:, :, ecken[0]])
    nA = np.cross(xu, xv)                       # Normale * dA/(du dv)
    pkt = geometrie_werte(L) @ G
    innen = np.sign(np.einsum("ma,ma->m", nA, G[gegen][None, :] - pkt))
    nA = nA * np.where(innen == 0, 1.0, innen)[:, None]
    if richtung is not None:
        d = np.asarray(richtung, float)
        d = d / (np.linalg.norm(d) or 1.0)
        t = p * np.linalg.norm(nA, axis=1)[:, None] * d[None, :]
    else:
        t = p * nA
    f = np.einsum("m,mf,mi->fi", w, Fg, t)
    return f.ravel()


# --------------------------------------------------------------------------
# Spannungen
# --------------------------------------------------------------------------
#: Auswertepunkte (natuerliche Koordinaten): Mitte und die vier Ecken, wie tet10
AUSWERTEPUNKTE = [(0.25, 0.25, 0.25), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                  (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]


def D_matrix(E, nu):
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.zeros((6, 6))
    D[:3, :3] = lam
    D[0, 0] = D[1, 1] = D[2, 2] = lam + 2 * mu
    D[3, 3] = D[4, 4] = D[5, 5] = mu
    return D


def spannungen_stapel(X, g, P, E, nu, U, punkte=None, maske=None, elemente=None):
    """Spannungen (n,q,6) an den Punkten (Vorgabe AUSWERTEPUNKTE)."""
    pk = AUSWERTEPUNKTE if punkte is None else punkte
    eps = dehnungen_stapel(X, g, P, U, pk, maske, elemente)
    return eps @ D_matrix(E, nu).T


# --------------------------------------------------------------------------
# Freiheitsgrade: Entitaeten, Ordnungen, Nummern
# --------------------------------------------------------------------------
class Anreicherung:
    """Nummerierung der hierarchischen Freiheitsgrade eines Netzes.

    ``ecken`` (n,4) globale Eckknoten der p-Elemente, ``ordnung`` (n,) ihre
    Ordnung P_e. ``linear_kanten`` / ``linear_flaechen``: Kanten (Eckpaare)
    und Flaechen (Ecktripel), die linear bleiben muessen - Seiten an Kontakt-
    und Fugenflaechen und alles, was ein Element ohne Anreicherung mitbenutzt
    (tet4, hex8 ...). Dort ist die Verschiebung auf der Seite wirklich linear,
    der Uebergang ist konform ohne Kopplung.

    Ordnung einer Kante bzw. Flaeche: die **kleinste** der Elemente daran
    (Mindestregel der p-Version), 1 wenn sie linear bleiben muss. Das Innere
    hat die Ordnung des Elements. Mit der Mindestregel hat jedes Element
    hoechstens seine eigene Ordnung - alle Elemente eines Typs tetpN haben
    also dieselbe Funktionszahl, und die Stapel der Leser (Steifigkeit,
    Spannung, Plastizitaet) bleiben je Typ gleich breit. Mit der Hoechstregel
    haette ein tetp2 neben einem tetp4 35 statt 10 Funktionen, und ein Stapel
    je Typ zerfiele in verschieden breite Teile.

    Die FHG beginnen bei ``basis`` (hinter den Knoten- und Woelb-FHG) und
    liegen je Entitaet zusammen: Funktion r, Komponente c -> start + 3 r + c.
    """

    def __init__(self, ecken, ordnung, basis: int, linear_kanten=(), linear_flaechen=()):
        self.ecken = np.asarray(ecken, dtype=np.int64).reshape(-1, 4)
        self.ordnung = np.asarray(ordnung, dtype=np.int64).ravel()
        self.basis = int(basis)
        n = len(self.ecken)
        lk = {tuple(sorted(map(int, k))) for k in linear_kanten}
        lf = {tuple(sorted(map(int, f))) for f in linear_flaechen}
        for f in list(lf):
            lk.update({(f[0], f[1]), (f[0], f[2]), (f[1], f[2])})
        # Kanten und Flaechen der Elemente (Schluessel sortiert)
        ks = np.sort(self.ecken[:, np.array(KANTEN)], axis=2)           # (n,6,2)
        fs = np.sort(self.ecken[:, np.array(FLAECHEN)], axis=2)         # (n,4,3)
        kschl, self.el_kante = np.unique(ks.reshape(-1, 2), axis=0, return_inverse=True)
        fschl, self.el_flaeche = np.unique(fs.reshape(-1, 3), axis=0, return_inverse=True)
        self.el_kante = self.el_kante.reshape(n, 6)
        self.el_flaeche = self.el_flaeche.reshape(n, 4)
        self.kanten = kschl
        self.flaechen = fschl
        pk = np.full(len(kschl), P_MAX, dtype=np.int64)
        np.minimum.at(pk, self.el_kante.ravel(), np.repeat(self.ordnung, 6))
        pf = np.full(len(fschl), P_MAX, dtype=np.int64)
        np.minimum.at(pf, self.el_flaeche.ravel(), np.repeat(self.ordnung, 4))
        self.kanten_pflicht = np.zeros(len(kschl), bool)
        self.flaechen_pflicht = np.zeros(len(fschl), bool)
        if lk:
            self.kanten_pflicht = np.array([tuple(k) in lk for k in map(tuple, kschl)])
            pk[self.kanten_pflicht] = 1
        if lf:
            self.flaechen_pflicht = np.array([tuple(f) in lf for f in map(tuple, fschl)])
            pf[self.flaechen_pflicht] = 1
        self.p_kante, self.p_flaeche = pk, pf
        self.p_innen = self.ordnung.copy()
        nk = np.array([je_entitaet(int(q), "k") for q in pk], dtype=np.int64)
        nfl = np.array([je_entitaet(int(q), "f") for q in pf], dtype=np.int64)
        ni = np.array([je_entitaet(int(q), "i") for q in self.p_innen], dtype=np.int64)
        start = self.basis
        self.start_kante = start + 3 * np.concatenate([[0], np.cumsum(nk)[:-1]]) if len(nk) else np.zeros(0, np.int64)
        start += 3 * int(nk.sum())
        self.start_flaeche = start + 3 * np.concatenate([[0], np.cumsum(nfl)[:-1]]) if len(nfl) else np.zeros(0, np.int64)
        start += 3 * int(nfl.sum())
        self.start_innen = start + 3 * np.concatenate([[0], np.cumsum(ni)[:-1]]) if len(ni) else np.zeros(0, np.int64)
        start += 3 * int(ni.sum())
        self.anzahl = start - self.basis

    def gruppe(self, pos):
        """Hoechstordnung der Elemente ``pos`` (Stellen in ``ecken``): die
        groesste Ordnung an Kanten, Flaechen und im Inneren."""
        pos = np.asarray(pos, dtype=np.int64)
        return np.maximum.reduce([self.p_kante[self.el_kante[pos]].max(axis=1),
                                  self.p_flaeche[self.el_flaeche[pos]].max(axis=1),
                                  self.p_innen[pos]])

    def fhg_und_maske(self, pos, P):
        """Globale FHG (n, 3nf) in Funktionsfolge fuer Ordnung P und Maske (n,nf).
        Inaktive Funktionen zeigen auf die FHG der ersten Ecke (Gradient null)."""
        pos = np.asarray(pos, dtype=np.int64)
        ek = self.ecken[pos]
        n = len(pos)
        fu = funktionen(P)
        nr = np.zeros((n, len(fu), 3), dtype=np.int64)
        maske = np.ones((n, len(fu)), dtype=bool)
        comp = np.arange(3)
        for c, (art, ent, q, r) in enumerate(fu):
            if art == "e":
                nr[:, c] = 6 * ek[:, ent][:, None] + comp
                continue
            if art == "k":
                kk = self.el_kante[pos, ent]
                aktiv = self.p_kante[kk] >= q
                st = self.start_kante[kk]
            elif art == "f":
                ff = self.el_flaeche[pos, ent]
                aktiv = self.p_flaeche[ff] >= q
                st = self.start_flaeche[ff]
            else:
                aktiv = self.p_innen[pos] >= q
                st = self.start_innen[pos]
            nr[:, c] = np.where(aktiv[:, None], st[:, None] + 3 * r + comp, 6 * ek[:, 0][:, None] + comp)
            maske[:, c] = aktiv
        return nr.reshape(n, -1), maske


# --------------------------------------------------------------------------
# Anbindung an das Modell
# --------------------------------------------------------------------------
#: Knotenzahl im Modell: nur die Ecken
KNOTEN = 4


def ist_tetp(typ) -> bool:
    return typ in TYPEN


def _gebundene_knoten(model) -> set:
    """Knoten, an denen etwas anderes als das eigene Element eine Seite fasst:
    Kontaktpaare (Slave-Knoten, Master-Seiten), Kopplungen (Fugen), Starrkoerper,
    Grenzschichtelemente. Eine Seite, deren Ecken alle hier liegen, bleibt linear
    - dann sieht der Kontakt dort genau, was er beim tet4 sieht (Absprache mit
    der Loeser-Sitzung 22.09.2026: keine Mittenfreiheitsgrade auf Kontaktseiten,
    die der Kontakt nicht kennt)."""
    out: set = set()
    for cp in getattr(model, "contact_pairs", None) or []:
        out.update(int(n) for n in cp.slave_nodes)
        for f in cp.master_faces or []:
            out.update(int(n) for n in f)
        for ei in cp.master_elements or []:
            out.update(int(n) for n in model.elements[int(ei)].nodes)
    for kp in getattr(model, "kopplungen", None) or []:
        out.add(int(kp.node_a))
        out.add(int(kp.node_b))
    for sk in getattr(model, "starrkoerper", None) or []:
        out.update(int(n) for n in sk.slaves)
    for e in model.elements:
        if e.typ in ("grenzschicht6", "grenzschicht8"):
            out.update(int(n) for n in e.nodes)
    # Federnde und nichtlineare Lager wirken je Knoten wie beim tet4 - eine
    # Seite dazwischen darf sich nicht quadratisch verformen, ohne dass eine
    # Feder sie haelt. Starre Lager sperren die Zusatz-FHG (gesperrte_fhg).
    for d in _lager(model):
        if d.typ != "rigid" or d.nonlinear:
            out.add(int(d.node))
    return out


def _lager(model) -> list:
    try:
        from .. import supports as sup
        return [d for d in sup.expand(model) if d.dof < 3 and d.node < model.nn]
    except Exception:            # noqa: BLE001 - ein Modell ohne Lager
        return []


def gesperrte_fhg(model) -> np.ndarray:
    """Zusatz-FHG, die ein starres Lager mitsperrt (Wert 0).

    Sind an allen drei Ecken einer Seite die Richtung c starr gelagert, ist
    die Verschiebung c auf der Seite die lineare Verteilung der Eckwerte -
    die Amplituden der Kanten- und Flaechenfunktionen der Seite in c sind
    null. Je Richtung, damit eine Symmetrieebene (nur die Normale gelagert)
    in der Ebene frei bleibt: dort liegen oft Nachweisstellen."""
    an = anreicherung(model)
    if an is None:
        return np.zeros(0, dtype=np.int64)
    fest = [set() for _ in range(3)]
    for d in _lager(model):
        if d.typ == "rigid" and not d.nonlinear:
            fest[d.dof].add(int(d.node))
    aus = []
    for c in range(3):
        if not fest[c]:
            continue
        auf = np.zeros(int(model.nn), bool)
        auf[list(fest[c])] = True
        rand = _randseiten(an)
        for f, tri in enumerate(an.flaechen):
            if not (rand[f] and auf[tri].all()):
                continue
            q = int(an.p_flaeche[f])
            nf = je_entitaet(q, "f")
            if nf:
                aus.extend(int(an.start_flaeche[f]) + 3 * r + c for r in range(nf))
        for k, (a, b) in enumerate(an.kanten):
            if not (auf[a] and auf[b]):
                continue
            nk = je_entitaet(int(an.p_kante[k]), "k")
            if nk and _kante_auf_randseite(an, k, auf):
                aus.extend(int(an.start_kante[k]) + 3 * r + c for r in range(nk))
    return np.unique(np.array(aus, dtype=np.int64))


def _kante_auf_randseite(an, k, auf) -> bool:
    """Liegt die Kante k (beide Ecken gelagert) auf dem Rand, also auf einer
    Randseite? Dann ist sie Teil einer Lagerflaeche oder -linie, und zwischen
    den Ecken haelt das Lager wie beim tet4. Eine Kante zwischen zwei
    gelagerten Ecken quer durch den Koerper liegt nicht auf dem Rand."""
    rand = _randseiten(an)
    if not hasattr(an, "_kante_flaechen"):
        kf = {}
        for f, tri in enumerate(an.flaechen):
            for a, b in ((tri[0], tri[1]), (tri[0], tri[2]), (tri[1], tri[2])):
                kf.setdefault((int(a), int(b)), []).append(f)
        an._kante_flaechen = kf
    a, b = an.kanten[k]
    for f in an._kante_flaechen.get((int(a), int(b)), []):
        if rand[f]:
            return True
    return False


def _randseiten(an) -> np.ndarray:
    """Seiten, die nur ein p-Element hat (Rand des p-Gebiets)."""
    if not hasattr(an, "_rand"):
        zahl = np.bincount(an.el_flaeche.ravel(), minlength=len(an.flaechen))
        an._rand = zahl == 1
    return an._rand


def pruefe_pflichtseiten(model, an) -> None:
    """Laut statt still: traegt eine Seite an Kontakt, Fuge, Kopplung oder
    einem federnden Lager doch einen Zusatzansatz, bricht die Rechnung ab.
    Der Kontakt kennt nur die Ecken (assemble.SOLID_FACES); eine Kante mit
    p > 1 auf seiner Seite waere dort still falsch - derselbe Fehler, den der
    tet10 mit seinen Mittenknoten an den Fugen hatte (Loeser-Sitzung
    22.09.2026: 52,6 % Zug an einer Fuge ohne Zug)."""
    geb = _gebundene_knoten(model)
    if not geb:
        return
    auf = np.zeros(int(model.nn), bool)
    auf[[n for n in geb if 0 <= n < model.nn]] = True
    f_geb = auf[an.flaechen].all(axis=1)
    schlecht_f = np.nonzero(f_geb & (an.p_flaeche > 1))[0]
    k_geb = np.zeros(len(an.kanten), bool)
    for f in np.nonzero(f_geb)[0]:
        tri = an.flaechen[f]
        for a, b in ((tri[0], tri[1]), (tri[0], tri[2]), (tri[1], tri[2])):
            k_geb[np.nonzero((an.kanten[:, 0] == a) & (an.kanten[:, 1] == b))[0]] = True
    k_geb |= auf[an.kanten].all(axis=1)
    schlecht_k = np.nonzero(k_geb & (an.p_kante > 1))[0]
    if len(schlecht_f) or len(schlecht_k):
        wo = (f"Seite mit den Knoten {[int(x) + 1 for x in an.flaechen[schlecht_f[0]]]}" if len(schlecht_f)
              else f"Kante mit den Knoten {[int(x) + 1 for x in an.kanten[schlecht_k[0]]]}")
        raise ValueError(f"Tetraeder mit Ordnung p: {wo} liegt an Kontakt, Fuge, Kopplung oder "
                         f"federndem Lager, traegt aber einen Zusatzansatz ({len(schlecht_f)} "
                         f"Seiten, {len(schlecht_k)} Kanten). Dort muss sie linear bleiben.")


def pflichtseiten(model, idx_p) -> tuple:
    """(Kanten, Flaechen, fremde Kanten): was linear bleiben muss, und die
    Kanten, die ein Element ohne Anreicherung mitbenutzt (dort ist auch die
    Geometrie gerade, siehe geometrie_modell).

    1. Alles, was ein Volumenelement ohne Anreicherung mitbenutzt (tet4, tet10,
       hex8 ...): dessen Spur auf der gemeinsamen Seite ist linear.
    2. Seiten an Kontakt, Fugen und Kopplungen (siehe _gebundene_knoten).
    """
    from ..elemente import VOLUMEN_TYPEN
    kanten, flaechen = set(), set()
    fremd = set()
    for e in model.elements:
        if e.typ in VOLUMEN_TYPEN and not ist_tetp(e.typ):
            kn = [int(n) for n in e.nodes]
            # alle Eckpaare und -tripel reichen: was keine Kante bzw. Seite
            # eines p-Elements ist, wird nie gefragt
            ecken = kn[:4] if e.typ in ("tet4", "tet10") else kn
            for a in range(len(ecken)):
                for b in range(a + 1, len(ecken)):
                    kanten.add((min(ecken[a], ecken[b]), max(ecken[a], ecken[b])))
                    fremd.add((min(ecken[a], ecken[b]), max(ecken[a], ecken[b])))
            if e.typ in ("tet4", "tet10"):
                for f in SEITEN:
                    flaechen.add(tuple(sorted(ecken[i] for i in f)))
    # Ein quadratisches Element mit Mittenknoten (tet10, hex20, pent15), das
    # eine Kante mit einem p-Element teilt: dort traegt es einen Mittenknoten,
    # den das p-Element nicht kennt - die Grenze waere nicht konform (Hinweis
    # der ersten Element-Sitzung 23.09.2026). Laut abweisen.
    p_kanten = set()
    for i in idx_p:
        kn = [int(n) for n in model.elements[i].nodes[:4]]
        for a, b in KANTEN:
            p_kanten.add((min(kn[a], kn[b]), max(kn[a], kn[b])))
    for j, e in enumerate(model.elements):
        if e.typ in ("tet10", "hex20", "pent15"):
            from . import solid as sl
            for f in sl.FLAECHEN_ECKEN[e.typ]:
                ecken = [int(e.nodes[a]) for a in f]
                for a in range(len(ecken)):
                    k = (min(ecken[a], ecken[a - 1]), max(ecken[a], ecken[a - 1]))
                    if k in p_kanten:
                        raise ValueError(
                            f"Element {j + 1} ({e.typ}) teilt die Kante {k[0] + 1}-{k[1] + 1} mit "
                            "einem Tetraeder mit Ordnung p: der Mittenknoten des quadratischen "
                            "Elements haette dort kein Gegenueber. Beide Koerper als tetp "
                            "rechnen oder die Grenze als Kontakt/Kopplung fuehren.")
    geb = _gebundene_knoten(model)
    if geb:
        for i in idx_p:
            kn = [int(n) for n in model.elements[i].nodes[:4]]
            for f in SEITEN:
                tri = [kn[j] for j in f]
                if all(n in geb for n in tri):
                    flaechen.add(tuple(sorted(tri)))
            # auch eine einzelne Kante zwischen zwei gebundenen Ecken (ein
            # federndes Linienlager, der Rand einer Kontaktflaeche): zwischen
            # den Ecken haelt dort nur, was an den Ecken haelt
            for a, b in KANTEN:
                if kn[a] in geb and kn[b] in geb:
                    kanten.add((min(kn[a], kn[b]), max(kn[a], kn[b])))
    # gemerkt fuer die Geometrie: eine Kante, die ein Element ohne Anreicherung
    # mitbenutzt, ist dort gerade - also auch beim tetp (sonst klafft die
    # Geometrie). Kontakt- und Fugenkanten bleiben gekruemmt: dort liegt kein
    # Nachbar, dessen Geometrie passen muesste, und die Nachweisstellen an
    # Bohrungen brauchen die Kruemmung (Labor 23.09.2026: eine einzige gerade
    # Bohrungskante, und selbst p = 4 lag dort 23 N/mm2 daneben).
    return kanten, flaechen, fremd


def basis_fhg(model) -> int:
    """Erster Platz der Anreicherung: hinter Knoten- und Woelb-FHG."""
    return int(model.nn) * 6 + len(model.woelb_knoten())


def _fingerabdruck(model, idx_p) -> str:
    """Voller Fingerabdruck: Ecken und Ordnung der p-Elemente, die gebundenen
    Knoten und alle Nicht-p-Volumenelemente (ihre Seiten bleiben linear)."""
    import hashlib
    import itertools
    kn = np.array([model.elements[i].nodes[:4] for i in idx_p], dtype=np.int64).reshape(-1, 4)
    ordn = np.array([TYPEN[model.elements[i].typ] for i in idx_p], dtype=np.int64)
    geb = np.array(sorted(_gebundene_knoten(model)), dtype=np.int64)
    andere = [e for e in model.elements if not ist_tetp(e.typ)]
    lang = np.fromiter((len(e.nodes) for e in andere), dtype=np.int64, count=len(andere))
    alle = np.fromiter(itertools.chain.from_iterable(e.nodes for e in andere), dtype=np.int64)
    h = hashlib.sha1()
    for arr in (kn, ordn, geb, np.array(idx_p, dtype=np.int64), lang, alle):
        h.update(np.ascontiguousarray(arr).tobytes())
    h.update("|".join(sorted({e.typ for e in andere})).encode())
    return h.hexdigest()


def _schnellschluessel(model) -> tuple:
    """Billiger Schluessel fuer die haeufigen Fragen (Model.ndof): Groessen
    und ein Zaehler ``_tetp_version``, den erhoehen muss, wer Elementtypen
    oder -knoten an Ort und Stelle aendert. Die Rechnung selbst prueft den
    vollen Fingerabdruck (``anreicherung(model, streng=True)`` in
    assemble.stiffness)."""
    return (int(model.nn), len(model.elements), len(model.woelb_knoten()),
            getattr(model, "_tetp_version", 0),
            len(getattr(model, "contact_pairs", None) or []),
            len(getattr(model, "kopplungen", None) or []),
            len(getattr(model, "starrkoerper", None) or []),
            len(getattr(model, "supports", None) or []),
            len(getattr(model, "line_supports", None) or []),
            len(getattr(model, "surface_supports", None) or []))


def anreicherung(model, streng: bool = False):
    """Die Anreicherung des Modells (zwischengespeichert) - None ohne p-Elemente.

    ``streng``: den vollen Fingerabdruck pruefen (einmal je Rechnung); sonst
    genuegt der billige Schluessel. Am Drehlager (645.934 Elemente) kostet
    der volle Abdruck eine Schleife ueber alle Elemente - Model.ndof wird
    aber in einer Kontaktrechnung hundertfach gefragt."""
    zw = getattr(model, "_tetp_zwischen", None)
    schnell = _schnellschluessel(model)
    if zw is not None and zw[0] == schnell and not streng:
        return zw[2]
    idx_p = [i for i, e in enumerate(model.elements) if ist_tetp(e.typ)]
    if not idx_p:
        try:
            model._tetp_zwischen = (schnell, None, None)
        except Exception:        # noqa: BLE001
            pass
        return None
    fa = _fingerabdruck(model, idx_p)
    if zw is not None and zw[1] == fa and zw[2] is not None:
        try:
            model._tetp_zwischen = (schnell, fa, zw[2])
        except Exception:        # noqa: BLE001
            pass
        return zw[2]
    kn = np.array([model.elements[i].nodes[:4] for i in idx_p], dtype=np.int64)
    ordn = np.array([TYPEN[model.elements[i].typ] for i in idx_p], dtype=np.int64)
    lk, lf, fremd = pflichtseiten(model, idx_p)
    an = Anreicherung(kn, ordn, basis_fhg(model), linear_kanten=lk, linear_flaechen=lf)
    an.gerade_kanten = fremd
    pruefe_pflichtseiten(model, an)
    an.idx = np.array(idx_p, dtype=np.int64)
    an.stelle = {int(i): s for s, i in enumerate(idx_p)}
    an.gruppe_je = an.gruppe(np.arange(len(idx_p)))
    an.fingerabdruck = fa
    try:
        model._tetp_zwischen = (schnell, fa, an)
    except Exception:            # noqa: BLE001 - ein Modell ohne Attribute rechnet trotzdem
        pass
    return an


def index_von(model, e) -> int:
    """Nummer des p-Elements ``e`` (Objekt) im Modell."""
    an = anreicherung(model)
    zuordnung = getattr(an, "_nach_id", None)
    if zuordnung is None:
        zuordnung = an._nach_id = {id(model.elements[int(i)]): int(i) for i in an.idx}
    i = zuordnung.get(id(e))
    if i is None:
        raise ValueError("tetp: Element gehoert nicht zum Modell")
    return i


def anzahl_fhg(model) -> int:
    """Zahl der Zusatz-FHG (fuer Model.ndof)."""
    an = anreicherung(model)
    return 0 if an is None else int(an.anzahl)


def kantenmitten(model) -> dict:
    """{(a, b) mit a < b: Punkt} - Kantenmitten auf der wahren Geometrie, vom
    Vernetzer; fehlt eine Kante, ist sie gerade."""
    return getattr(model, "tetp_kantenmitten", None) or {}


def geometrie_modell(model, idx) -> np.ndarray:
    """Geometriepunkte (n,10,3) der Elemente idx."""
    X = np.asarray(model.nodes, float)
    kn = np.array([model.elements[i].nodes[:4] for i in idx], dtype=np.int64)
    G = geometrie(X[kn])
    km = kantenmitten(model)
    if km:
        an = anreicherung(model)
        gerade = getattr(an, "gerade_kanten", set()) if an is not None else set()
        G = G.copy()
        for a, e in enumerate(kn):
            for m, (i, j) in enumerate(TET10_KANTEN):
                schl = (min(e[i], e[j]), max(e[i], e[j]))
                p = km.get(schl)
                if p is not None and schl not in gerade:
                    G[a, 4 + m] = p
    return G


def _ist_krumm(model, idx) -> bool:
    km = kantenmitten(model)
    if not km:
        return False
    for i in idx:
        kn = model.elements[i].nodes[:4]
        for a, b in TET10_KANTEN:
            if (min(kn[a], kn[b]), max(kn[a], kn[b])) in km:
                return True
    return False


def gruppen(model, idx) -> list:
    """Die p-Elemente idx nach Hoechstordnung und Werkstoff gestapelt:
    Liste (P, Werkstoffname, Elementnummern, fhg (n,3nf), maske (n,nf))."""
    an = anreicherung(model)
    aus = {}
    for i in idx:
        s = an.stelle[int(i)]
        P = int(an.gruppe_je[s])
        aus.setdefault((P, model.elements[i].mat), []).append(int(i))
    liste = []
    for (P, mat), els in sorted(aus.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        pos = [an.stelle[i] for i in els]
        fhg, maske = an.fhg_und_maske(pos, P)
        liste.append((P, mat, np.array(els, dtype=np.int64), fhg, maske))
    return liste


def matrizen(model, idx) -> dict:
    """{Element: (FHG, Steifigkeit)} der p-Elemente in idx - gestapelt."""
    aus = {}
    for P, mat, els, fhg, maske in gruppen(model, idx):
        m = model.materials[mat]
        G = geometrie_modell(model, els)
        g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
        K, _V = steifigkeit_stapel(G, g, P, float(m.E), float(m.nu), maske, elemente=els,
                                   krumm=_ist_krumm(model, els))
        for a, i in enumerate(els):
            aus[int(i)] = (fhg[a], K[a])
    return aus


def element_fhg(model, i) -> np.ndarray:
    """Globale FHG eines p-Elements (3nf,) in Funktionsfolge seiner Gruppe.

    Aus dem Speicher, den _laeufe fuellt: assemble.element_dofs fragt je
    Element, und die Nummern je Element neu zu bilden kostete eine Schleife
    ueber alle Funktionen."""
    an = anreicherung(model)
    speicher = getattr(an, "_fhg", None)
    if speicher is not None and int(i) in speicher:
        return speicher[int(i)]
    for _P, _els, fhg, _mk in _laeufe(model, [int(i)]):
        return fhg[0]
    raise ValueError(i)


def spannungen(model, idx, u, punkte=None) -> dict:
    """{Element: Spannungen (q,6)} an den Punkten (Vorgabe AUSWERTEPUNKTE)."""
    u = np.asarray(u, float).ravel()
    aus = {}
    for P, mat, els, fhg, maske in gruppen(model, idx):
        m = model.materials[mat]
        G = geometrie_modell(model, els)
        g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
        S = spannungen_stapel(G, g, P, float(m.E), float(m.nu), u[fhg], punkte, maske, elemente=els)
        for a, i in enumerate(els):
            aus[int(i)] = S[a]
    return aus


def knotenmittel(model, idx, u, gruppe_von=None) -> dict:
    """{(Knoten, Gruppe): gemittelter Spannungsvektor} ueber die p-Elemente an
    der Ecke.

    Gemessen im Labor (Lame-Hohlzylinder, 22./23.09.2026): die Eckwerte
    einzelner Elemente streuen deutlich mehr als ihr Mittel - p = 4 auf 1.400
    Tetraedern hoechstens 1,22 N/mm2 je Element, im Knotenmittel 0,40 N/mm2.
    Gemittelt wird nur innerhalb eines Werkstoffs (bzw. gruppe_von(e)), denn
    ueber eine Werkstoffgrenze springt die Spannung wirklich."""
    S = spannungen(model, idx, u, AUSWERTEPUNKTE[1:])
    summe, zahl = {}, {}
    for i, Si in S.items():
        e = model.elements[i]
        key_g = gruppe_von(e) if gruppe_von is not None else e.mat
        for a in range(4):
            k = (int(e.nodes[a]), key_g)
            summe[k] = summe.get(k, 0.0) + Si[a]
            zahl[k] = zahl.get(k, 0) + 1
    return {k: summe[k] / zahl[k] for k in summe}


# --------------------------------------------------------------------------
# Lasten, Masse, Dehnungsoperator - je Modellelement
# --------------------------------------------------------------------------
def _laeufe(model, idx) -> list:
    """idx in Laeufe gleicher Hoechstordnung zerlegen, **ohne die Folge zu
    aendern**: die Leser (solid.spannungen_stapel, die Plastizitaet) schneiden
    ihre Elementfelder in der Folge von idx. Rueckgabe [(P, Elemente, fhg, maske)]."""
    an = anreicherung(model)
    aus = []
    lauf, P_lauf = [], None
    for i in idx:
        P = int(an.gruppe_je[an.stelle[int(i)]])
        if lauf and P != P_lauf:
            aus.append((P_lauf, lauf))
            lauf = []
        lauf.append(int(i))
        P_lauf = P
    if lauf:
        aus.append((P_lauf, lauf))
    liste = []
    for P, els in aus:
        fhg, maske = an.fhg_und_maske([an.stelle[i] for i in els], P)
        speicher = getattr(an, "_fhg", None)
        if speicher is None:
            speicher = an._fhg = {}
        for a, i in enumerate(els):
            speicher[int(i)] = fhg[a]
        liste.append((P, np.array(els, dtype=np.int64), fhg, maske))
    return liste


def element_fhg_objekt(model, e) -> np.ndarray:
    """Globale FHG des Modellelements ``e`` (Objekt) - fuer assemble.element_dofs."""
    return element_fhg(model, index_von(model, e))


def seitenlast_modell(model, i, seite, p, richtung=None) -> tuple:
    """(FHG, Lasten) eines Seitendrucks auf das Modellelement i."""
    (P, els, fhg, maske), = _laeufe(model, [int(i)])
    G = geometrie_modell(model, els)[0]
    g = np.array(model.elements[int(i)].nodes[:4], dtype=np.int64)
    return fhg[0], seitenlast(G, g, P, seite, p, richtung, maske[0])


def volumenlasten_modell(model, idx, b) -> dict:
    """{Element: (FHG, Lasten)} einer Volumenkraft je Element: b ist (3,)
    [N/m^3] fuer alle oder ein Aufruf b(element) -> (3,)."""
    aus = {}
    for P, els, fhg, maske in _laeufe(model, idx):
        G = geometrie_modell(model, els)
        g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
        for a, i in enumerate(els):
            bi = b(model.elements[i]) if callable(b) else b
            f = volumenlast_stapel(G[a:a + 1], g[a:a + 1], P, bi, maske[a:a + 1])[0]
            aus[int(i)] = (fhg[a], f)
    return aus


def anfangsspannung_modell(model, i, s0) -> tuple:
    """(FHG, f = int B^T s0 dV) des Modellelements i - Temperatur, Vorspannung."""
    (P, els, fhg, maske), = _laeufe(model, [int(i)])
    G = geometrie_modell(model, els)
    g = np.array([model.elements[int(i)].nodes[:4]], dtype=np.int64)
    return fhg[0], anfangsspannung_stapel(G, g, P, s0, maske, elemente=els)[0]


def massen_modell(model, idx) -> dict:
    """{Element: (FHG, konsistente Masse)}."""
    aus = {}
    for P, els, fhg, maske in _laeufe(model, idx):
        G = geometrie_modell(model, els)
        g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
        for a, i in enumerate(els):
            rho = float(getattr(model.materials[model.elements[i].mat], "rho", 0.0) or 0.0)
            aus[int(i)] = (fhg[a], masse_stapel(G[a:a + 1], g[a:a + 1], P, rho, maske[a:a + 1])[0])
    return aus


def _operator(model, typ, els, fhg, maske, P, L, w_regel):
    from . import solid as sl
    G = geometrie_modell(model, els)
    g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
    _F, dF = basis_ref(L, P)
    Gx, dV = gradienten(G, dF, L, els)
    Gx = _global(Gx, orientierung(g, P), maske)                  # (n,m,nf,3)
    w = (w_regel[None, :] * dV).T if w_regel is not None else np.zeros((L.shape[0], len(els)))
    return sl.Dehnungsoperator(typ, np.asarray(els, dtype=np.int64), None, np.ascontiguousarray(w),
                               g=np.ascontiguousarray(Gx.transpose(1, 0, 2, 3)),
                               xi=np.ascontiguousarray(L[:, 1:]), fhg=fhg)


def operatoren(model, typ, idx, aktiv=None) -> list:
    """Dehnungsoperatoren (solid.Dehnungsoperator) der p-Elemente idx an den
    Integrationspunkten der Steifigkeit - dieselben Gradienten und Gewichte,
    aus denen steifigkeit_stapel rechnet. Je Lauf gleicher Hoechstordnung
    einer, in der Folge von idx."""
    aus = []
    for P, els, fhg, maske in _laeufe(model, idx):
        L, W = steifigkeitsregel(P, _ist_krumm(model, els))
        aus.append(_operator(model, typ, els, fhg, maske, P, L, W))
    return aus


def auswerter(model, typ, idx, punkte) -> list:
    """Dieselbe Kinematik an natuerlichen Punkten (Q,3), gleiche Laeufe wie
    :func:`operatoren`."""
    pk = np.asarray(punkte, float).reshape(-1, 3)
    L = np.column_stack([1.0 - pk.sum(axis=1), pk])
    return [_operator(model, typ, els, fhg, maske, P, L, None)
            for P, els, fhg, maske in _laeufe(model, idx)]


def zusatzschluessel(model, idx, aktiv=None):
    """Fuer solid.ZUSATZSCHLUESSEL: die Zuordnung der Zusatz-FHG haengt an den
    Nachbarn und an Kontakt/Fugen/Lagern, nicht nur an den eigenen Knoten."""
    an = anreicherung(model)
    return None if an is None else (int(an.basis), int(an.anzahl), an.fingerabdruck)


# --------------------------------------------------------------------------
# Fehlerindikator: was bringt die naechste Ordnung? (fuer die Ordnungswahl)
# --------------------------------------------------------------------------
def naechste_ordnung(model, u, idx=None) -> dict:
    """Energie der naechsten Ordnung je p-Element - zum **Ordnen**, nicht als
    Spannungsfehler.

    Hierarchischer Indikator (Zienkiewicz/Gago/Kelly 1983): Die Funktionen
    der Ordnung P+1 kommen zum Element dazu, die bisherigen bleiben auf ihrer
    Loesung u stehen, die Nachbarn halten still:

        K_nn a = -K_no u_o,      eta^2 = a^T K_nn a.

    Gemessen 23.09.2026 am Kragarm (10 x 2 x 2 Kuhn-Zellen, p = 2): Die
    groessten eta liegen an der Einspannung (x = 0,025 ... 0,075 m), wo die
    Singularitaet sitzt - als Rangfolge brauchbar. Die aus a folgende
    **Spannungsaenderung** an den Ecken lag an der Nachweisstelle aber bei
    80 bis 311 N/mm2, wirklich aenderte sich sigma_v beim Uebergang auf p = 3
    um 2,5 bis 18 N/mm2. Das lokale Problem ohne Nachbarn uebertreibt
    punktweise um Faktoren; darum liefert die Funktion **keine** Spannung.
    Ob eine Nachweisstelle auf 1 N/mm2 steht, zeigt der Vergleich zweier
    Loesungen (p und p+1) an der Stelle selbst.

    Seiten, die linear bleiben muessen (Kontakt, Fugen, Nachbarn ohne
    Anreicherung), bekommen auch hier keine neuen Funktionen. Elemente mit
    P = P_MAX werden uebersprungen. Rueckgabe {Element: eta^2 [J]}.
    """
    an = anreicherung(model)
    if an is None:
        return {}
    u = np.asarray(u, float).ravel()
    idx = list(an.idx) if idx is None else [int(i) for i in idx]
    aus = {}
    for P, els, fhg, maske in _laeufe(model, idx):
        if P >= P_MAX:
            continue
        Q = P + 1
        fu_P, fu_Q = funktionen(P), funktionen(Q)
        pos = {f: c for c, f in enumerate(fu_Q)}
        alt = np.array([pos[f] for f in fu_P])
        neu_je_el = []
        for i in els:
            s_ = an.stelle[int(i)]
            n = []
            for c, (art, ent, q, _r) in enumerate(fu_Q):
                if q != Q:
                    continue
                if art == "k" and an.kanten_pflicht[an.el_kante[s_, ent]]:
                    continue
                if art == "f" and an.flaechen_pflicht[an.el_flaeche[s_, ent]]:
                    continue
                n.append(c)
            neu_je_el.append(np.array(n, dtype=np.int64))
        G = geometrie_modell(model, els)
        g = np.array([model.elements[i].nodes[:4] for i in els], dtype=np.int64)
        for mat in {model.elements[i].mat for i in els}:
            sel = [a_ for a_, i in enumerate(els) if model.elements[i].mat == mat]
            m = model.materials[mat]
            K, _V = steifigkeit_stapel(G[sel], g[sel], Q, float(m.E), float(m.nu),
                                       krumm=_ist_krumm(model, els[sel]))
            d_alt = (3 * alt[:, None] + np.arange(3)).ravel()
            for b_, a_ in enumerate(sel):
                n = neu_je_el[a_]
                if len(n) == 0:
                    continue
                d_neu = (3 * n[:, None] + np.arange(3)).ravel()
                uo = u[fhg[a_]] * np.repeat(maske[a_], 3)
                Knn = K[b_][np.ix_(d_neu, d_neu)]
                an_ = np.linalg.solve(Knn, -K[b_][np.ix_(d_neu, d_alt)] @ uo)
                aus[int(els[a_])] = float(an_ @ Knn @ an_)
    return aus


def jacobi_pruefung(model, idx) -> list:
    """[(Element, Typ, kleinstes det J)] der p-Elemente idx, deren quadratische
    Geometrie an einer Ecke, Kantenmitte oder einem Integrationspunkt nicht
    positiv ist (fuer solid.jacobi_pruefung und die Netzabnahme, B7)."""
    idx = [int(i) for i in idx]
    if not idx or not kantenmitten(model):
        return []
    G = geometrie_modell(model, idx)
    L, _W = steifigkeitsregel(P_MAX, True)
    punkte = np.vstack([_PRUEFPUNKTE, L])
    _J, detJ = jacobi(G, punkte)
    m = detJ.min(axis=1)
    return [(idx[a], model.elements[idx[a]].typ, float(m[a])) for a in np.flatnonzero(m <= 0.0)]


# --------------------------------------------------------------------------
# Aus einem tet10-Netz: die Mittenknoten werden Geometrie
# --------------------------------------------------------------------------
def aus_tet10(model, elemente=None, ordnung: int = 3, toleranz: float = 1e-9) -> dict:
    """tet10-Elemente (alle oder ``elemente``) in tetpN umwandeln.

    Die Ecken bleiben die Knoten des Elements. Ein Mittenknoten, der nicht auf
    der Sehnenmitte liegt (der Vernetzer setzt ihn auf die wahre Flaeche,
    Anweisung V2), wird zur Kantenmitte der Geometrie
    (``model.tetp_kantenmitten``); liegt er auf der Sehne, bleibt die Kante
    gerade. Die Mittenknoten selbst tragen danach nichts mehr (ihre FHG haben
    keine Steifigkeit und werden gesperrt).

    Laut statt still: Eine Knotenlast oder ein Lager an einem Mittenknoten,
    das die Ecken der Kante nicht ebenso tragen, bricht ab - die Last ginge
    sonst mit dem Knoten verloren. Lasten gehoeren beim tetp als Flaechenlast
    auf die Seite (sie wirkt dort konsistent auch auf die Zusatz-FHG).

    Rueckgabe {"elemente": Zahl, "gekruemmt": Zahl gekruemmter Kanten,
    "mittenknoten": Menge der frei gewordenen Knoten}.
    """
    if ordnung not in (2, 3, 4):
        raise ValueError(f"Ordnung {ordnung} (2, 3 oder 4)")
    X = np.asarray(model.nodes, float)
    idx = [i for i, e in enumerate(model.elements) if e.typ == "tet10"] if elemente is None \
        else [int(i) for i in elemente]
    mitte_von = {}
    for i in idx:
        e = model.elements[i]
        if e.typ != "tet10":
            raise ValueError(f"Element {i + 1} ist {e.typ}, nicht tet10")
        kn = [int(n) for n in e.nodes]
        for m_, (a, b) in enumerate(TET10_KANTEN):
            mitte_von[kn[4 + m_]] = (min(kn[a], kn[b]), max(kn[a], kn[b]))
    # Lasten und Lager an den Mittenknoten pruefen
    for lc in getattr(model, "load_cases", {}).values() if isinstance(getattr(model, "load_cases", None), dict) \
            else (getattr(model, "load_cases", None) or []):
        for nl in getattr(lc, "nodal_loads", None) or []:
            if int(nl.node) in mitte_von and any(float(x) for x in nl.F):
                raise ValueError(f"Knotenlast am Mittenknoten {int(nl.node) + 1} (Lastfall "
                                 f"'{getattr(lc, 'name', '?')}'): beim Tetraeder mit Ordnung p "
                                 "traegt der Mittenknoten nichts - die Last als Flaechenlast "
                                 "auf die Seite geben")
    lager: dict = {}
    for sp in getattr(model, "supports", None) or []:
        lager.setdefault(int(sp.node), []).append(sp)
    def gesperrt(n):
        """Starr gesperrte Richtungen 0..2 eines Knotens (alle seine Lager)."""
        return {int(d) for sq in lager.get(n, []) if sq.stiffness is None and not sq.behaviour
                for d in sq.dofs if int(d) < 3}

    for m_, (a, b) in mitte_von.items():
        for sp in lager.get(m_, []):
            dofs = {int(d) for d in sp.dofs if int(d) < 3}
            starr = sp.stiffness is None and not sp.behaviour
            # die Richtungen des Mittenknotens muessen an beiden Ecken ebenso
            # starr gehalten sein (eine Ecke auf zwei Symmetrieebenen haelt mehr)
            ok = starr and dofs <= gesperrt(a) and dofs <= gesperrt(b)
            if dofs and not ok:
                raise ValueError(f"Lager am Mittenknoten {m_ + 1}, das die Ecken {a + 1} und "
                                 f"{b + 1} nicht ebenso tragen: beim Tetraeder mit Ordnung p "
                                 "gilt ein Lager ueber die Ecken der Seite")
    km = dict(getattr(model, "tetp_kantenmitten", None) or {})
    gekruemmt = 0
    for i in idx:
        e = model.elements[i]
        kn = [int(n) for n in e.nodes]
        for m_, (a, b) in enumerate(TET10_KANTEN):
            pa, pb, pm = X[kn[a]], X[kn[b]], X[kn[4 + m_]]
            lang = float(np.linalg.norm(pb - pa))
            if np.linalg.norm(pm - 0.5 * (pa + pb)) > toleranz * max(lang, 1e-300):
                schl = (min(kn[a], kn[b]), max(kn[a], kn[b]))
                if schl not in km:
                    gekruemmt += 1
                km[schl] = pm.copy()
        e.nodes = kn[:4]
        e.typ = f"tetp{ordnung}"
    model.tetp_kantenmitten = km
    model._tetp_version = getattr(model, "_tetp_version", 0) + 1
    # Lager an den Mittenknoten sind jetzt ohne Wirkung - weg damit, damit
    # kein Lager an einem Knoten ohne Element steht
    frei = set(mitte_von)
    if frei and getattr(model, "supports", None):
        model.supports = [sp for sp in model.supports if int(sp.node) not in frei]
    return {"elemente": len(idx), "gekruemmt": gekruemmt, "mittenknoten": frei}


# --------------------------------------------------------------------------
# Flaechenschnittstelle fuer einen kuenftigen Kontakt ueber Punkte der Seite
# (Absprache mit der Loeser-Sitzung 23.09.2026; heute bleiben Kontaktseiten
# linear, und diese Funktion wird von keiner Rechnung gerufen)
# --------------------------------------------------------------------------
def seitenfunktionen(P) -> list:
    """Positionen (in funktionen(P)) der Funktionen, die auf Seite ``s``
    (SEITEN-Nummer) nicht verschwinden: je Seite eine Liste."""
    fu = funktionen(P)
    aus = []
    for ecken in SEITEN:
        es = set(ecken)
        pos = []
        for c, (art, ent, _q, _r) in enumerate(fu):
            if art == "e" and ent in es:
                pos.append(c)
            elif art == "k" and set(KANTEN[ent]) <= es:
                pos.append(c)
            elif art == "f" and set(FLAECHEN[ent]) == es:
                pos.append(c)
        aus.append(pos)
    return aus


def flaechenschnittstelle(model, seiten, grad: int = None) -> dict:
    """Integrationspunkte, Flaechengewichte, Aussennormalen und Ansatzwerte
    der Seiten ``seiten`` = [(Element, Seite), ...] von p-Elementen.

    Rueckgabe {"punkte" (n,m,3), "dA" (n,m), "normalen" (n,m,3) nach aussen
    (weg von der Gegenecke, wie Model._seitennormale), "ansatz" (n,m,k),
    "fhg" (n,k,3), "k" (n,) Zahl der wirksamen Funktionen je Seite}. k ist
    die groesste Funktionszahl der Seiten; kuerzere Seiten sind mit Nullen
    (Ansatz) und den FHG ihrer ersten Ecke aufgefuellt. Die Verschiebung am
    Punkt ist u = sum_a ansatz[a] * u[fhg[a]]."""
    seiten = [(int(i), int(s)) for i, s in seiten]
    n = len(seiten)
    daten = []
    for i, s in seiten:
        (P, _els, fhg, maske), = _laeufe(model, [i])
        pos = [c for c in seitenfunktionen(P)[s] if maske[0][c]]
        G = geometrie_modell(model, [i])[0]
        g = np.array(model.elements[i].nodes[:4], dtype=np.int64)
        grad_i = (2 * P + 2) if grad is None else grad
        from scipy.special import roots_jacobi
        nq = max(2, (grad_i + 2) // 2)
        a, wa = roots_jacobi(nq, 1, 0)
        c_, wc = roots_jacobi(nq, 0, 0)
        a, c_ = (a + 1) / 2, (c_ + 1) / 2
        AA, CC = np.meshgrid(a, c_, indexing="ij")
        u_ = AA.ravel()
        v_ = (CC * (1 - AA)).ravel()
        w = np.outer(wa, wc).ravel()
        w = 0.5 * w / w.sum()
        ecken = SEITEN[s]
        L = np.zeros((len(u_), 4))
        L[:, ecken[0]] = 1 - u_ - v_
        L[:, ecken[1]] = u_
        L[:, ecken[2]] = v_
        F, _dF = basis_ref(L, P)
        Fg = F @ orientierung(g[None], P)[0]
        dN = np.zeros((len(u_), 10, 4))
        for e_ in range(4):
            dN[:, e_, e_] = 4 * L[:, e_] - 1
        for kk, (p_, q_) in enumerate(TET10_KANTEN):
            dN[:, 4 + kk, p_] = 4 * L[:, q_]
            dN[:, 4 + kk, q_] = 4 * L[:, p_]
        xu = np.einsum("ka,mk->ma", G, dN[:, :, ecken[1]] - dN[:, :, ecken[0]])
        xv = np.einsum("ka,mk->ma", G, dN[:, :, ecken[2]] - dN[:, :, ecken[0]])
        nA = np.cross(xu, xv)
        pkt = geometrie_werte(L) @ G
        gegen = [e_ for e_ in range(4) if e_ not in ecken][0]
        aussen = np.sign(np.einsum("ma,ma->m", nA, pkt - G[gegen][None, :]))
        nA = nA * np.where(aussen == 0, 1.0, aussen)[:, None]
        betrag = np.linalg.norm(nA, axis=1)
        daten.append((pkt, w * betrag, nA / betrag[:, None], Fg[:, pos],
                      fhg[0].reshape(-1, 3)[pos]))
    m = max(len(d[1]) for d in daten) if daten else 0
    k = max(d[3].shape[1] for d in daten) if daten else 0
    aus = {"punkte": np.zeros((n, m, 3)), "dA": np.zeros((n, m)), "normalen": np.zeros((n, m, 3)),
           "ansatz": np.zeros((n, m, k)), "fhg": np.zeros((n, k, 3), dtype=np.int64),
           "k": np.zeros(n, dtype=np.int64)}
    for r, (pkt, dA, nor, ans, dofs) in enumerate(daten):
        mm, kk = len(dA), ans.shape[1]
        aus["punkte"][r, :mm] = pkt
        aus["dA"][r, :mm] = dA
        aus["normalen"][r, :mm] = nor
        aus["ansatz"][r, :mm, :kk] = ans
        aus["fhg"][r, :kk] = dofs
        aus["fhg"][r, kk:] = dofs[0]
        aus["k"][r] = kk
    return aus


def _anmelden():
    """Am Ende des eigenen Imports: bei solid anmelden (idempotent). Ist solid
    selbst noch im Laden, meldet es tetp am Ende seines Imports an."""
    try:
        from . import solid as _sl
        _sl._tetp_registrieren()
    except (ImportError, AttributeError):
        pass


_anmelden()
