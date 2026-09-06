"""
Verifikation der ebenen Kontinuumselemente (statik3d.elements.ebene)
gegen geschlossene Loesungen.

Typen: tri3 ("ebene3"), quad4 ("ebene4"), tri6 ("ebene6"), quad8 ("ebene8")
Zustaende: ebener Spannungszustand, ebener Dehnungszustand, rotationssymmetrisch

Geprueft wird:
  * Patch-Tests (verzerrte Netze mit inneren Knoten, lineares Verschiebungs-
    feld am Rand) fuer alle Typen und Zustaende, Spannungen an allen
    Auswertepunkten exakt
  * Starrkoerpermoden (3 in der Ebene, 1 bei Rotationssymmetrie) und
    steifigkeitslose Normalenrichtung
  * Kragscheibe gegen die Balkenloesung mit Schub (Timoshenko, 5/6)
  * ebener Dehnungszustand unter einachsigem Zug
  * dickwandiger Zylinder unter Innendruck (Lame) und rotierender Ring
  * Lastkonsistenz der Kantenlasten, Massen, Flaechen, Waermedehnung

Die Verbaende werden hier im Test assembliert (dichte Matrizen, 3 FHG je
Knoten); Lager durch Streichen von Zeilen/Spalten, die Richtung senkrecht
zur Ebene wird ebenfalls gestrichen.

Aufruf:  python3 tests/test_elemente_ebene.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.elements import ebene as EB                         # noqa: E402

RESULTS = []


def check(name, ok, info=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {info}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, rel <= tol,
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.4f} %")


# --------------------------------------------------------------------------
# Hilfsmittel: Rahmen, Netze, Assemblierung, Loesung
# --------------------------------------------------------------------------
def rotationsmatrix(achse, winkel):
    """Zeilen e1, e2, e3 eines um 'achse' gedrehten Systems (Rodrigues)."""
    k = np.asarray(achse, float)
    k = k / np.linalg.norm(k)
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    R = np.eye(3) + math.sin(winkel) * Kx + (1 - math.cos(winkel)) * Kx @ Kx
    return R.T.copy()          # Zeilen = gedrehte Basisvektoren


RAHMEN_SCHRAEG = rotationsmatrix((1.0, 2.0, 3.0), 0.7)
RAHMEN_ROT = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])
VERSATZ = np.array([0.5, -0.3, 0.8])

KANTEN = {
    "ebene3": [(0, 1), (1, 2), (2, 0)],
    "ebene4": [(0, 1), (1, 2), (2, 3), (3, 0)],
    "ebene6": [(0, 1, 3), (1, 2, 4), (2, 0, 5)],
    "ebene8": [(0, 1, 4), (1, 2, 5), (2, 3, 6), (3, 0, 7)],
}
ECKEN = {"ebene3": 3, "ebene4": 4, "ebene6": 3, "ebene8": 4}
TYPEN = ("ebene3", "ebene4", "ebene6", "ebene8")
ZUSTAENDE = ("spannung", "dehnung", "rotation")


def rahmen(zustand):
    return RAHMEN_ROT if zustand == "rotation" else RAHMEN_SCHRAEG


def knoten3d(xy, zustand, r0=1.0):
    """Ebene Koordinaten -> Raum.  spannung/dehnung: schraege Ebene;
    rotation: x-z-Ebene mit r = x + r0."""
    xy = np.asarray(xy, float)
    if zustand == "rotation":
        return np.column_stack([xy[:, 0] + r0, np.zeros(len(xy)), xy[:, 1]])
    return VERSATZ + xy @ RAHMEN_SCHRAEG[:2]


def mittelknoten(xy, elemente):
    """Erzeugt die Seitenmittelknoten (gemeinsam fuer Nachbarelemente)."""
    xy = [tuple(p) for p in np.asarray(xy, float)]
    merk = {}
    aus = []
    for el in elemente:
        ne = len(el)
        neu = list(el)
        for k in range(ne):
            a, b = el[k], el[(k + 1) % ne]
            key = (min(a, b), max(a, b))
            if key not in merk:
                merk[key] = len(xy)
                xy.append(tuple(0.5 * (np.array(xy[a]) + np.array(xy[b]))))
            neu.append(merk[key])
        aus.append(neu)
    return np.array(xy), aus


def netz_rechteck(typ, Lx, Ly, nx, ny, x0=0.0, y0=0.0):
    """Strukturiertes Netz eines Rechtecks; Dreiecke durch Teilen der
    Vierecke mit wechselnder Diagonale."""
    xy = [(x0 + i * Lx / nx, y0 + j * Ly / ny)
          for j in range(ny + 1) for i in range(nx + 1)]

    def nid(i, j):
        return j * (nx + 1) + i

    elemente = []
    for j in range(ny):
        for i in range(nx):
            q = [nid(i, j), nid(i + 1, j), nid(i + 1, j + 1), nid(i, j + 1)]
            if typ in ("ebene4", "ebene8"):
                elemente.append(q)
            elif (i + j) % 2 == 0:
                elemente += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
            else:
                elemente += [[q[0], q[1], q[3]], [q[1], q[2], q[3]]]
    xy = np.array(xy, float)
    if typ in ("ebene6", "ebene8"):
        xy, elemente = mittelknoten(xy, elemente)
    return xy, elemente


def patch_netz(typ):
    """Verzerrtes Patch (5 Vierecke bzw. 10 Dreiecke) mit inneren Knoten.
    Rueckgabe xy, Elemente, Randknoten."""
    xy = np.array([[0.0, 0.0], [2.4, 0.0], [2.4, 1.2], [0.0, 1.2],
                   [0.4, 0.2], [1.8, 0.3], [1.6, 0.8], [0.8, 0.8]])
    quads = [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7], [4, 5, 6, 7]]
    if typ in ("ebene3", "ebene6"):
        elemente = []
        for q in quads:
            elemente += [[q[0], q[1], q[2]], [q[0], q[2], q[3]]]
    else:
        elemente = quads
    if typ in ("ebene6", "ebene8"):
        xy, elemente = mittelknoten(xy, elemente)
    rand = [k for k, (x, y) in enumerate(xy)
            if min(abs(x), abs(x - 2.4), abs(y), abs(y - 1.2)) < 1e-12]
    return xy, elemente, rand


def element_verzerrt(typ, gekruemmt=False):
    """Ein einzelnes, verzerrtes Element (lokale Koordinaten)."""
    if typ in ("ebene3", "ebene6"):
        ecken = np.array([[0.0, 0.0], [2.0, 0.3], [0.5, 1.5]])
    else:
        ecken = np.array([[0.0, 0.0], [2.0, 0.2], [2.3, 1.6], [-0.2, 1.4]])
    if typ in ("ebene3", "ebene4"):
        return ecken
    xy, el = mittelknoten(ecken, [list(range(len(ecken)))])
    if gekruemmt:
        ne = len(ecken)
        for k in range(ne):
            a, b = ecken[k], ecken[(k + 1) % ne]
            t = b - a
            xy[ne + k] += 0.05 * np.array([-t[1], t[0]])
    return xy[el[0]]


def dofs(el):
    return np.array([3 * i + k for i in el for k in range(3)])


def assemblieren(typ, X, elemente, E, nu, t, zustand):
    N = len(X)
    K = np.zeros((3 * N, 3 * N))
    for el in elemente:
        idx = dofs(el)
        K[np.ix_(idx, idx)] += EB.k_ebene(typ, X[el], E, nu, t, zustand)
    return K


def loesen(K, f, Q3, gesperrt, u_vor=None):
    """Loest K u = f.  Q3: Zeilen e1, e2, e3 des Netzsystems; die Richtung
    e3 (senkrecht zur Ebene) wird bei allen Knoten gestrichen.  gesperrt:
    Paare (Knoten, lokale Richtung 0/1); u_vor: vorgegebene globale
    Verschiebungen (3N,) fuer gesperrte FHG."""
    N = K.shape[0] // 3
    Q = np.kron(np.eye(N), Q3)
    Kt = Q @ K @ Q.T
    ft = Q @ f
    ut = np.zeros(3 * N) if u_vor is None else Q @ u_vor
    g = np.zeros(3 * N, bool)
    g[2::3] = True
    for k, d in gesperrt:
        g[3 * k + d] = True
    fr = ~g
    ut[fr] = np.linalg.solve(Kt[np.ix_(fr, fr)], ft[fr] - Kt[np.ix_(fr, g)] @ ut[g])
    return Q.T @ ut


def kanten_auf(xy, elemente, typ, bedingung):
    """(Elementindex, Kantenindex) aller Kanten, deren Knoten 'bedingung'
    erfuellen."""
    aus = []
    for e, el in enumerate(elemente):
        for k, kn in enumerate(KANTEN[typ]):
            if all(bedingung(*xy[el[i]]) for i in kn):
                aus.append((e, k))
    return aus


def Tm_matrix(T3, n):
    Tm = np.zeros((2 * n, 3 * n))
    for i in range(n):
        Tm[2 * i, 3 * i:3 * i + 3] = T3[0]
        Tm[2 * i + 1, 3 * i:3 * i + 3] = T3[1]
    return Tm


def voigt_exakt(D, eps, nu, zustand):
    s = D @ eps
    out = np.zeros(6)
    if zustand == "rotation":
        out[:4] = [s[0], s[1], s[3], s[2]]
    else:
        out[0], out[1], out[3] = s[0], s[1], s[2]
        if zustand == "dehnung":
            out[2] = nu * (s[0] + s[1])
    return out


# --------------------------------------------------------------------------
# Patch-Tests
# --------------------------------------------------------------------------
def t_patch(typ, zustand):
    E, nu, t = 210e9, 0.3, 0.05
    xy, elemente, rand = patch_netz(typ)
    X = knoten3d(xy, zustand)
    N = len(X)
    Q3 = rahmen(zustand)
    D = EB.D_ebene(E, nu, zustand)

    if zustand == "rotation":
        a, b = 1.0e-3, -0.5e-3
        u_ex = np.zeros((N, 3))
        u_ex[:, 0] = a * X[:, 0]
        u_ex[:, 2] = b * X[:, 2]
        s_ex = voigt_exakt(D, np.array([a, b, 0.0, a]), nu, zustand)
    else:
        G2 = np.array([[1.0e-3, 0.4e-3], [-0.6e-3, 0.5e-3]])
        c2 = np.array([0.2e-3, -0.1e-3])
        u_ex = (xy @ G2.T + c2) @ Q3[:2]
        G3 = Q3[:2].T @ G2 @ Q3[:2]

    K = assemblieren(typ, X, elemente, E, nu, t, zustand)
    gesperrt = [(k, d) for k in rand for d in (0, 1)]
    u = loesen(K, np.zeros(3 * N), Q3, gesperrt, u_ex.reshape(-1))
    du = np.abs(u - u_ex.reshape(-1)).max() / np.abs(u_ex).max()
    check(f"Patch {typ} {zustand}: Verschiebung innere Knoten", du <= 1e-8,
          f"max. Abw. {du:.2e}")

    fehler = 0.0
    for el in elemente:
        Xe = X[el]
        if zustand != "rotation":
            T3, _ = EB.ebene_frame(Xe, zustand)
            Gl = T3 @ G3 @ T3.T
            eps = np.array([Gl[0, 0], Gl[1, 1], Gl[0, 1] + Gl[1, 0]])
            s_ex = voigt_exakt(D, eps, nu, zustand)
        sp = EB.stress_points_ebene(typ, Xe, E, nu, t, zustand, u[dofs(el)])
        for s in sp:
            fehler = max(fehler, np.abs(s - s_ex).max() / np.abs(s_ex).max())
    check(f"Patch {typ} {zustand}: Spannungen an allen Auswertepunkten",
          fehler <= 1e-8, f"max. rel. Abw. {fehler:.2e}")


# --------------------------------------------------------------------------
# Starrkoerpermoden
# --------------------------------------------------------------------------
def t_starrkoerper(typ, zustand):
    E, nu, t = 210e9, 0.3, 0.02
    X = knoten3d(element_verzerrt(typ, gekruemmt=True), zustand)
    n = EB.knotenzahl_ebene(typ)
    K = EB.k_ebene(typ, X, E, nu, t, zustand)
    T3, _ = EB.ebene_frame(X, zustand)
    Tm = Tm_matrix(T3, n)
    K2 = Tm @ K @ Tm.T
    ev = np.linalg.eigvalsh(K2)
    nz = int(np.sum(ev < 1e-9 * ev.max()))
    soll = 1 if zustand == "rotation" else 3
    check(f"Starrkoerper {typ} {zustand}: {soll} Nulleigenwert(e) in der Ebene",
          nz == soll, f"{nz} gefunden, kleinster positiver "
          f"{ev[soll] / ev.max():.2e} (rel.)")
    Tn = np.zeros((n, 3 * n))
    for i in range(n):
        Tn[i, 3 * i:3 * i + 3] = T3[2]
    normal = np.abs(Tn @ K).max() / np.abs(K).max()
    sym = np.abs(K - K.T).max() / np.abs(K).max()
    check(f"Starrkoerper {typ} {zustand}: Normalenrichtung steifigkeitslos, symmetrisch",
          normal <= 1e-12 and sym <= 1e-12, f"normal {normal:.1e}, sym {sym:.1e}")


# --------------------------------------------------------------------------
# Kragscheibe
# --------------------------------------------------------------------------
KRAG = dict(L=10.0, h=1.0, t=0.1, E=210e9, nu=0.3, F=1000.0)


def schublast_parabel(xy, elemente, typ, L, h, t, F):
    """Konsistente Knotenkraefte der parabolischen Schubverteilung am Ende."""
    N = len(xy)
    fs = np.zeros(N)
    gp = (-math.sqrt(0.6), 0.0, math.sqrt(0.6))
    gw = (5 / 9, 8 / 9, 5 / 9)
    for e, k in kanten_auf(xy, elemente, typ, lambda x, y: abs(x - L) < 1e-9):
        kn = [elemente[e][i] for i in KANTEN[typ][k]]
        yk = xy[kn, 1]
        for s, w in zip(gp, gw):
            if len(kn) == 2:
                Ns = np.array([0.5 * (1 - s), 0.5 * (1 + s)])
                dNs = np.array([-0.5, 0.5])
            else:
                Ns = np.array([0.5 * s * (s - 1), 0.5 * s * (s + 1), 1 - s * s])
                dNs = np.array([s - 0.5, s + 0.5, -2 * s])
            y = Ns @ yk
            tau = 1.5 * F / (h * t) * (1.0 - (2.0 * y / h) ** 2)
            fs[kn] += w * Ns * tau * t * abs(dNs @ yk)
    return fs


def kragscheibe(typ, nx, ny):
    """Kragscheibe in einer schraegen Ebene.  Einspannung: u_x = 0 auf dem
    ganzen Rand x = 0, u_y = 0 nur im Mittelknoten (laesst die
    Querkontraktion frei, wie bei der Balkenloesung); gibt es keinen
    Mittelknoten (ny ungerade bei linearen Typen), wird voll eingespannt."""
    L, h, t, E, nu, F = (KRAG[k] for k in ("L", "h", "t", "E", "nu", "F"))
    xy, elemente = netz_rechteck(typ, L, h, nx, ny, y0=-h / 2)
    X = knoten3d(xy, "spannung")
    N = len(X)
    K = assemblieren(typ, X, elemente, E, nu, t, "spannung")
    fs = schublast_parabel(xy, elemente, typ, L, h, t, F)
    f = np.zeros(3 * N)
    for k in range(N):
        f[3 * k:3 * k + 3] = fs[k] * RAHMEN_SCHRAEG[1]
    rand = [k for k in range(N) if abs(xy[k, 0]) < 1e-12]
    mitte = [k for k in rand if abs(xy[k, 1]) < 1e-12]
    if mitte:
        gesperrt = [(k, 0) for k in rand] + [(k, 1) for k in mitte]
    else:
        gesperrt = [(k, d) for k in rand for d in (0, 1)]
    u = loesen(K, f, RAHMEN_SCHRAEG, gesperrt)
    ende = [k for k in range(N) if abs(xy[k, 0] - L) < 1e-9]
    w = float(np.mean([u[3 * k:3 * k + 3] @ RAHMEN_SCHRAEG[1] for k in ende]))
    return w, fs.sum()


def krag_analytisch():
    L, h, t, E, nu, F = (KRAG[k] for k in ("L", "h", "t", "E", "nu", "F"))
    I = t * h ** 3 / 12.0
    A = t * h
    G = E / (2.0 * (1.0 + nu))
    return F * L ** 3 / (3.0 * E * I) + F * L / (5.0 / 6.0 * G * A)


def t_kragscheibe(typ, nx, ny, tol):
    w, Fsum = kragscheibe(typ, nx, ny)
    close(f"Kragscheibe {typ} {nx}x{ny}: Endlast = F", Fsum, KRAG["F"], 1e-12)
    close(f"Kragscheibe {typ} {nx}x{ny}: Enddurchbiegung (Timoshenko)",
          w, krag_analytisch(), tol, " m")


def t_kragscheibe_tri3_konvergenz():
    w_ana = krag_analytisch()
    fehler = []
    netze = ((8, 2), (16, 4), (32, 8), (64, 16))
    for nx, ny in netze:
        w, _ = kragscheibe("ebene3", nx, ny)
        fehler.append(abs(w - w_ana) / w_ana)
    mono = all(fehler[i + 1] < fehler[i] for i in range(len(fehler) - 1))
    check("Kragscheibe tri3: Fehler faellt monoton mit der Verfeinerung",
          mono, "  ".join(f"{nx}x{ny}: {100 * e:.1f}%"
                          for (nx, ny), e in zip(netze, fehler)))
    check("Kragscheibe tri3 64x16: Fehler < 5 %", fehler[-1] < 0.05,
          f"{100 * fehler[-1]:.2f} %")


# --------------------------------------------------------------------------
# Ebener Dehnungszustand, einachsiger Zug
# --------------------------------------------------------------------------
def t_dehnung_zug(typ):
    E, nu, t, sigma = 210e9, 0.3, 1.0, 50e6
    Lx, Ly = 2.0, 1.0
    xy, elemente = netz_rechteck(typ, Lx, Ly, 2, 2)
    X = knoten3d(xy, "dehnung")
    N = len(X)
    K = assemblieren(typ, X, elemente, E, nu, t, "dehnung")
    f = np.zeros(3 * N)
    for e, k in kanten_auf(xy, elemente, typ, lambda x, y: abs(x - Lx) < 1e-9):
        f[dofs(elemente[e])] += EB.kantenlast_ebene(
            typ, X[elemente[e]], k, sigma * t, "dehnung", richtung=RAHMEN_SCHRAEG[0])
    gesperrt = ([(k, 0) for k in range(N) if abs(xy[k, 0]) < 1e-12]
                + [(k, 1) for k in range(N) if abs(xy[k, 1]) < 1e-12])
    u = loesen(K, f, RAHMEN_SCHRAEG, gesperrt)
    ende = [k for k in range(N) if abs(xy[k, 0] - Lx) < 1e-9]
    eps_x = np.array([u[3 * k:3 * k + 3] @ RAHMEN_SCHRAEG[0] for k in ende]) / Lx
    eps_ana = (1.0 - nu ** 2) * sigma / E
    close(f"Ebener Dehnungszustand {typ}: eps_x = (1-nu^2) sigma/E",
          float(eps_x.mean()), eps_ana, 1e-8)
    check(f"Ebener Dehnungszustand {typ}: eps_x an allen Endknoten gleich",
          np.abs(eps_x - eps_ana).max() <= 1e-8 * eps_ana)
    # exakter Verzerrungszustand im Netzsystem, je Element ins lokale
    # System gedreht (bei Dreiecken liegt ex auf der Diagonale)
    eps_y = -nu * (1.0 + nu) * sigma / E
    G3 = eps_ana * np.outer(RAHMEN_SCHRAEG[0], RAHMEN_SCHRAEG[0]) \
        + eps_y * np.outer(RAHMEN_SCHRAEG[1], RAHMEN_SCHRAEG[1])
    D = EB.D_ebene(E, nu, "dehnung")
    fehler = 0.0
    for el in elemente:
        T3, _ = EB.ebene_frame(X[el], "dehnung")
        Gl = T3 @ G3 @ T3.T
        s_ex = voigt_exakt(D, np.array([Gl[0, 0], Gl[1, 1], Gl[0, 1] + Gl[1, 0]]),
                           nu, "dehnung")
        if abs(s_ex[2] - nu * sigma) > 1e-9 * sigma:
            raise RuntimeError("Testfehler: sigma_z muss nu*sigma sein")
        for s in EB.stress_points_ebene(typ, X[el], E, nu, t, "dehnung", u[dofs(el)]):
            fehler = max(fehler, np.abs(s - s_ex).max() / sigma)
    check(f"Ebener Dehnungszustand {typ}: sigma_x = sigma, sigma_z = nu sigma",
          fehler <= 1e-8, f"max. rel. Abw. {fehler:.2e}")


# --------------------------------------------------------------------------
# Rotationssymmetrie: Lame, rotierender Ring
# --------------------------------------------------------------------------
def t_lame(typ, nr, tol_u, tol_s):
    ri, ra, H, p, E, nu = 1.0, 2.0, 0.1, 10e6, 210e9, 0.3
    xy, elemente = netz_rechteck(typ, ra - ri, H, nr, 1, x0=ri)
    X = knoten3d(xy, "rotation", r0=0.0)
    N = len(X)
    K = assemblieren(typ, X, elemente, E, nu, 1.0, "rotation")
    f = np.zeros(3 * N)
    for e, k in kanten_auf(xy, elemente, typ, lambda x, y: abs(x - ri) < 1e-12):
        f[dofs(elemente[e])] += EB.kantenlast_ebene(typ, X[elemente[e]], k, p, "rotation")
    gesperrt = [(k, 1) for k in range(N)
                if abs(xy[k, 1]) < 1e-12 or abs(xy[k, 1] - H) < 1e-12]
    u = loesen(K, f, RAHMEN_ROT, gesperrt)

    A = p * ri ** 2 / (ra ** 2 - ri ** 2)
    B = p * ri ** 2 * ra ** 2 / (ra ** 2 - ri ** 2)

    def u_r(r):
        return (1.0 + nu) / E * ((1.0 - 2.0 * nu) * A * r + B / r)

    def s_r(r):
        return A - B / r ** 2

    def s_t(r):
        return A + B / r ** 2

    name = f"Lame {typ} 1x{nr}"
    innen = [k for k in range(N) if abs(xy[k, 0] - ri) < 1e-12]
    aussen = [k for k in range(N) if abs(xy[k, 0] - ra) < 1e-12]
    close(f"{name}: u_r(r_i)", float(np.mean(u[3 * np.array(innen)])), u_r(ri), tol_u, " m")
    close(f"{name}: u_r(r_a)", float(np.mean(u[3 * np.array(aussen)])), u_r(ra), tol_u, " m")
    close(f"{name}: Summe Innendruck = p 2 pi r_i H",
          float(f[0::3].sum()), p * 2 * math.pi * ri * H, 1e-12)

    # Spannungen des innersten Elements an den optimalen Spannungspunkten
    # (lineare Typen: Mitte, quadratische Typen: reduzierte Gauss-Punkte)
    # gegen Lame am jeweiligen Radius
    e0 = [e for e, el in enumerate(elemente)
          if any(abs(xy[k, 0] - ri) < 1e-12 for k in el[:ECKEN[typ]])]
    pts = {"ebene3": [(1 / 3, 1 / 3)], "ebene4": [(0.0, 0.0)],
           "ebene6": [tuple(q) for q in EB.gauss_ebene("ebene3")[0]],
           "ebene8": [tuple(q) for q in EB.gauss_ebene("ebene4")[0]]}[typ]
    err_s = 0.0
    for e in e0:
        el = elemente[e]
        sp = EB.stress_points_ebene(typ, X[el], E, nu, 1.0, "rotation",
                                    u[dofs(el)], punkte=pts)
        for (xi, eta), s in zip(pts, sp):
            Nn, _ = EB.N_dN_ebene(typ, xi, eta)
            r = float(Nn @ xy[el, 0])
            err_s = max(err_s, abs(s[0] - s_r(r)) / p, abs(s[2] - s_t(r)) / s_t(ri),
                        abs(s[1] - nu * (s_r(r) + s_t(r))) / s_t(ri))
    check(f"{name}: sigma_r, sigma_theta, sigma_z an den Spannungspunkten gegen Lame",
          err_s <= tol_s, f"max. Abw. {100 * err_s:.3f} % (bezogen auf p bzw. sigma_theta(r_i))")

    # Eckwerte am Innenrand (Ableitungen direkt am Rand)
    st_i, sr_i = [], []
    for e in e0:
        el = elemente[e]
        sp = EB.stress_points_ebene(typ, X[el], E, nu, 1.0, "rotation", u[dofs(el)])
        for (xi, eta), s in zip(EB.AUSWERTEPUNKTE_EBENE[typ][1:], sp[1:]):
            Nn, _ = EB.N_dN_ebene(typ, xi, eta)
            if abs(Nn @ xy[el, 0] - ri) < 1e-9:
                st_i.append(s[2])
                sr_i.append(s[0])
    return (float(np.mean(sr_i)), float(np.mean(st_i)), s_t(ri), name)


def t_lame_alle():
    """Dickwandiger Zylinder r_i = 1, r_a = 2 unter Innendruck.

    Verschiebungen und Spannungen an den optimalen Spannungspunkten werden
    mit den engen Toleranzen geprueft (quad4 1x10: 2 %, quad8 1x5: 0,5 %).
    Die Eckwerte direkt am Innenrand sind durch die Interpolationsordnung
    begrenzt: u_r ~ 1/r, das Element liefert am Rand die Sekante statt der
    Tangente (quad4 1x10: sigma_r um rund 20 % zu klein, quad8 1x5 rund
    4 %).  Diese Werte werden deshalb nur mit gestaffelten Toleranzen
    (Vorzeichen und Groessenordnung) geprueft."""
    p = 10e6
    for typ, nr, tol_u, tol_s, tol_eck in (("ebene4", 10, 2e-2, 2e-2, 0.25),
                                           ("ebene8", 5, 5e-3, 5e-3, 0.05),
                                           ("ebene3", 10, 3e-2, 3e-2, 0.25),
                                           ("ebene6", 5, 1e-2, 1e-2, 0.05)):
        sr, st, st_ana, name = t_lame(typ, nr, tol_u, tol_s)
        close(f"{name}: sigma_theta(r_i) am Eckpunkt (Toleranz {100 * tol_eck:.0f} %)",
              st, st_ana, tol_eck, " Pa")
        close(f"{name}: sigma_r(r_i) = -p am Eckpunkt (Toleranz {100 * tol_eck:.0f} %)",
              sr, -p, tol_eck, " Pa")


def t_rotierender_ring(typ):
    R, b, H, rho, omega, E, nu = 10.0, 0.2, 0.2, 7850.0, 100.0, 210e9, 0.3
    xy, elemente = netz_rechteck(typ, b, H, 2, 2, x0=R - b / 2)
    X = knoten3d(xy, "rotation", r0=0.0)
    N = len(X)
    K = assemblieren(typ, X, elemente, E, nu, 1.0, "rotation")
    f = np.zeros(3 * N)
    GP, W = EB.gauss_ebene(typ)
    for el in elemente:
        xe = xy[el]
        for (xi, eta), w in zip(GP, W):
            Nn, dNn = EB.N_dN_ebene(typ, xi, eta)
            detJ = np.linalg.det(dNn.T @ xe)
            r = Nn @ xe[:, 0]
            f[3 * np.array(el)] += w * detJ * 2 * math.pi * r * Nn * rho * omega ** 2 * r
    u = loesen(K, f, RAHMEN_ROT, [(0, 1)])
    ur = float(np.mean(u[0::3]))
    close(f"Rotierender Ring {typ}: u_r = rho w^2 R^3/E", ur,
          rho * omega ** 2 * R ** 3 / E, 2e-3, " m")
    st = [EB.stress_ebene(typ, X[el], E, nu, 1.0, "rotation", u[dofs(el)]) for el in elemente]
    close(f"Rotierender Ring {typ}: sigma_theta = rho w^2 R^2",
          float(np.mean([s[2] for s in st])), rho * omega ** 2 * R ** 2, 2e-3, " Pa")
    rest = max(abs(s[0]) + abs(s[1]) + abs(s[3]) for s in st) / (rho * omega ** 2 * R ** 2)
    check(f"Rotierender Ring {typ}: sigma_r, sigma_z, tau_rz vernachlaessigbar",
          rest <= 1e-2, f"{100 * rest:.3f} % von sigma_theta")


# --------------------------------------------------------------------------
# Lastkonsistenz, Massen, Flaechen, Temperatur
# --------------------------------------------------------------------------
def polygon_flaeche_schwerpunkt(ecken):
    x, y = ecken[:, 0], ecken[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    kreuz = x * yn - xn * y
    A = 0.5 * kreuz.sum()
    cx = (x + xn) @ kreuz / (6.0 * A)
    cy = (y + yn) @ kreuz / (6.0 * A)
    return A, cx, cy


def t_lastkonsistenz(typ, zustand):
    p = 1234.5
    xy = element_verzerrt(typ)
    X = knoten3d(xy, zustand)
    T3, xyl = EB.ebene_frame(X, zustand)
    n = EB.knotenzahl_ebene(typ)
    err_druck, err_richt = 0.0, 0.0
    d = np.array([0.3, -0.4, 0.5]) if zustand != "rotation" else np.array([0.6, 0.0, 0.8])
    d = d / np.linalg.norm(d)
    for kante, kn in enumerate(KANTEN[typ]):
        a, b = kn[0], kn[1]
        Lk = np.linalg.norm(X[b] - X[a])
        tl = xyl[b] - xyl[a]
        n_in = np.array([-tl[1], tl[0]]) / np.linalg.norm(tl)
        n_glob = n_in[0] * T3[0] + n_in[1] * T3[1]
        faktor = p * Lk
        if zustand == "rotation":
            faktor *= 2 * math.pi * 0.5 * (X[a, 0] + X[b, 0])
        f = EB.kantenlast_ebene(typ, X, kante, p, zustand)
        F = f.reshape(n, 3).sum(axis=0)
        err_druck = max(err_druck, np.linalg.norm(F - faktor * n_glob) / faktor)
        f = EB.kantenlast_ebene(typ, X, kante, p, zustand, richtung=d)
        F = f.reshape(n, 3).sum(axis=0)
        err_richt = max(err_richt, np.linalg.norm(F - faktor * d) / faktor)
        # Kantenlast nur auf den Kantenknoten
        andere = [i for i in range(n) if i not in kn]
        if andere:
            err_richt = max(err_richt, np.abs(f.reshape(n, 3)[andere]).max() / faktor)
    check(f"Kantenlast {typ} {zustand}: Druck, Summe = p*L*n (innen)",
          err_druck <= 1e-12, f"max. rel. Abw. {err_druck:.1e}")
    check(f"Kantenlast {typ} {zustand}: Richtung, Summe = p*L*d",
          err_richt <= 1e-12, f"max. rel. Abw. {err_richt:.1e}")


def t_masse_flaeche(typ, zustand):
    rho, t = 7850.0, 0.03
    xy = element_verzerrt(typ)
    X = knoten3d(xy, zustand)
    ne = ECKEN[typ]
    A, cx, cy = polygon_flaeche_schwerpunkt(xy[:ne])
    if zustand == "rotation":
        V_ana = 2 * math.pi * (cx + 1.0) * A         # Pappus, r0 = 1
        F_ana = V_ana
    else:
        V_ana = A * t
        F_ana = A
    Fl = EB.flaeche_ebene(typ, X, zustand)
    close(f"Flaeche {typ} {zustand}: flaeche_ebene", Fl, F_ana, 1e-12)
    m = EB.masse_ebene(typ, X, rho, t, zustand)
    check(f"Masse {typ} {zustand}: alle Eintraege > 0, Summe je Richtung = rho V",
          m.min() > 0 and all(abs(m[k::3].sum() - rho * V_ana) <= 1e-12 * rho * V_ana
                              for k in range(3)),
          f"min {m.min():.4g}, Summe {m[0::3].sum():.6g} / {rho * V_ana:.6g}")


def t_temperatur(typ, zustand):
    E, nu, t, alpha, dT = 210e9, 0.3, 0.02, 1.2e-5, 40.0
    Lx, Ly = 2.0, 1.0
    xy, elemente = netz_rechteck(typ, Lx, Ly, 2, 2)
    X = knoten3d(xy, zustand)
    N = len(X)
    Q3 = rahmen(zustand)
    K = assemblieren(typ, X, elemente, E, nu, t, zustand)
    f = np.zeros(3 * N)
    for el in elemente:
        f[dofs(el)] += EB.temperatur_ebene(typ, X[el], E, nu, t, alpha, dT, zustand)
    gesperrt = [(k, 1) for k in range(N) if abs(xy[k, 1]) < 1e-12]
    if zustand != "rotation":
        gesperrt += [(k, 0) for k in range(N) if abs(xy[k, 0]) < 1e-12]
    u = loesen(K, f, Q3, gesperrt)
    faktor = {"spannung": 1.0, "dehnung": 1.0 + nu, "rotation": 1.0}[zustand]
    err = 0.0
    for k in range(N):
        ul = Q3[:2] @ u[3 * k:3 * k + 3]
        if zustand == "rotation":
            soll = np.array([alpha * dT * X[k, 0], alpha * dT * xy[k, 1]])
        else:
            soll = faktor * alpha * dT * xy[k]
        err = max(err, np.abs(ul - soll).max() / (alpha * dT * Lx * faktor))
    check(f"Temperatur {typ} {zustand}: freie Waermedehnung "
          f"({'(1+nu) ' if zustand == 'dehnung' else ''}alpha dT)",
          err <= 1e-8, f"max. rel. Abw. {err:.2e}")


def t_rahmen_fehler():
    P = np.array([[1.0, 0, 0], [2.0, 0, 0], [2.0, 0, 1.0], [1.0, 0, 1.0]])
    T3, xy = EB.ebene_frame(P, "rotation")
    ok = np.allclose(T3, RAHMEN_ROT) and np.allclose(xy, P[:, [0, 2]])
    check("Rahmen rotation: T3 und (r, z)", ok)
    try:
        EB.ebene_frame(P + np.array([0, 1e-3, 0]), "rotation")
        ok = False
    except ValueError:
        ok = True
    check("Rahmen rotation: Fehler bei y != 0", ok)
    try:
        EB.ebene_frame(P - np.array([1.5, 0, 0]), "rotation")
        ok = False
    except ValueError:
        ok = True
    check("Rahmen rotation: Fehler bei r < 0", ok)
    q = element_verzerrt("ebene8")
    T3, xy = EB.ebene_frame(knoten3d(q, "spannung"), "spannung")
    # lokal: Ursprung Knoten 0, ex entlang Kante 0-1 -> Netzkoordinaten gedreht
    e1 = (q[1] - q[0]) / np.linalg.norm(q[1] - q[0])
    e2 = np.array([-e1[1], e1[0]])
    soll = np.column_stack([(q - q[0]) @ e1, (q - q[0]) @ e2])
    ok = (np.allclose(T3 @ T3.T, np.eye(3)) and np.allclose(np.cross(T3[0], T3[1]), T3[2])
          and np.allclose(T3[2], RAHMEN_SCHRAEG[2]) and np.allclose(xy, soll)
          and np.allclose(T3[0], e1 @ RAHMEN_SCHRAEG[:2]))
    check("Rahmen spannung: Orthonormalsystem, Normale, ex auf Kante 0-1, lokale Koordinaten", ok)


# --------------------------------------------------------------------------
def main():
    print("=" * 100)
    print("Verifikation ebene Kontinuumselemente (tri3, quad4, tri6, quad8)")
    print("=" * 100)
    print("\n-- Rahmen ------------------------------------------------------------")
    t_rahmen_fehler()
    print("\n-- Patch-Tests ---------------------------------------------------------")
    for zustand in ZUSTAENDE:
        for typ in TYPEN:
            t_patch(typ, zustand)
    print("\n-- Starrkoerpermoden ---------------------------------------------------")
    for zustand in ZUSTAENDE:
        for typ in TYPEN:
            t_starrkoerper(typ, zustand)
    print("\n-- Kragscheibe ---------------------------------------------------------")
    t_kragscheibe("ebene4", 8, 1, 3e-2)
    t_kragscheibe("ebene8", 4, 1, 1e-2)
    t_kragscheibe("ebene6", 8, 1, 2e-2)
    t_kragscheibe_tri3_konvergenz()
    print("\n-- Ebener Dehnungszustand ----------------------------------------------")
    for typ in TYPEN:
        t_dehnung_zug(typ)
    print("\n-- Rotationssymmetrie --------------------------------------------------")
    t_lame_alle()
    t_rotierender_ring("ebene8")
    t_rotierender_ring("ebene4")
    print("\n-- Lasten, Massen, Flaechen, Temperatur --------------------------------")
    for zustand in ZUSTAENDE:
        for typ in TYPEN:
            t_lastkonsistenz(typ, zustand)
            t_masse_flaeche(typ, zustand)
            t_temperatur(typ, zustand)

    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 100)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    print("=" * 100)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
