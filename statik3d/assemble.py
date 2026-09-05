"""Assemblierung von Steifigkeits-, Massen- und Lastvektoren.

Neu gegenueber Version 1:
* Momentengelenke an Stabenden (statische Kondensation)
* Lastvektor je Lastfall (Knoten-, Strecken- (auch trapezfoermig), Flaechen-,
  Temperaturlasten, Eigengewicht)
* parallele Elementschleifen ueber statik3d.parallel
"""
from __future__ import annotations

import numpy as np
from scipy import sparse

from .model import Model, NDOF, LoadCase
from .elements import beam3d as bm
from .elements import shell as sh
from .elements import solid as sl

SOLID_TYPES = ("tet4", "tet10", "hex8")
SHELL_TYPES = ("shell3", "shell4")
LINE_TYPES = ("beam", "truss")


# --------------------------------------------------------------------------
def element_dofs(e) -> np.ndarray:
    """Globale FHG-Nummern eines Elements."""
    if e.typ in SOLID_TYPES:
        d = []
        for n in e.nodes:
            d.extend([NDOF * n, NDOF * n + 1, NDOF * n + 2])
        return np.array(d, dtype=int)
    d = []
    for n in e.nodes:
        d.extend(range(NDOF * n, NDOF * n + NDOF))
    return np.array(d, dtype=int)


def beam_local(model: Model, e):
    """Lokale Steifigkeitsmatrix (12x12), T3, T (12x12), L eines Stabelements."""
    mat = model.materials[e.mat]
    sec = model.sections[e.sec]
    X = model.nodes[e.nodes]
    T3, L = bm.local_axes(X[0], X[1], e.roll)
    T = bm.transform_matrix(T3)
    if e.typ == "truss":
        kl = bm.k_local_truss(mat.E, sec.A, L)
    else:
        kl = bm.k_local_beam(mat.E, mat.G, sec.A, sec.Iy, sec.Iz, sec.It,
                             L, sec.Asy, sec.Asz)
    return kl, T3, T, L


def hinge_springs(kl: np.ndarray, fl: np.ndarray, springs) -> tuple:
    """Federgelenke: zwischen Stabende und Knoten liegt je FHG eine Feder.

    Fuer jeden Federgelenk-FHG d wird ein innerer FHG eingefuehrt, den das
    Element belegt; die Feder k verbindet ihn mit dem aeusseren FHG d. Der
    innere FHG wird anschliessend statisch kondensiert - das Ergebnis ist die
    exakte Reihenschaltung Stab + Feder (k -> unendlich: biegesteif,
    k -> 0: Gelenk).
    Rueckgabe: (kl, fl) mit denselben 12 aeusseren FHG.
    """
    springs = [(int(d), float(k)) for d, k in (springs or []) if k and k > 0]
    if not springs:
        return kl, fl, None
    n = 12 + len(springs)
    B = np.zeros((12, n))
    for i in range(12):
        B[i, i] = 1.0
    K = np.zeros((n, n))
    f = np.zeros(n)
    for j, (d, k) in enumerate(springs):
        B[d, d] = 0.0
        B[d, 12 + j] = 1.0          # das Element haengt am inneren FHG
    K[:, :] = B.T @ kl @ B
    f[:] = B.T @ fl
    for j, (d, k) in enumerate(springs):
        e = np.zeros(n)
        e[d] = 1.0
        e[12 + j] = -1.0
        K += k * np.outer(e, e)     # Feder zwischen aeusserem und innerem FHG
    inner = np.arange(12, n)
    outer = np.arange(12)
    Kii = K[np.ix_(inner, inner)]
    Kio = K[np.ix_(inner, outer)]
    try:
        Kii_inv = np.linalg.inv(Kii)
    except np.linalg.LinAlgError:
        Kii_inv = np.linalg.pinv(Kii)
    kl2 = K[np.ix_(outer, outer)] - Kio.T @ Kii_inv @ Kio
    fl2 = f[outer] - Kio.T @ Kii_inv @ f[inner]
    return kl2, fl2, (B, Kii_inv, Kio, f[inner])


def hinge_local_disp(rec, ul: np.ndarray) -> np.ndarray:
    """Stabend-Verschiebungen des Elements aus den Knotenverschiebungen ul,
    wenn Federgelenke vorliegen (Rueckrechnung der inneren FHG)."""
    B, Kii_inv, Kio, f_inner = rec
    wi = Kii_inv @ (f_inner - Kio @ ul)
    return B @ np.concatenate([ul, wi])


def condense(kl: np.ndarray, fl: np.ndarray, released: list[int]):
    """Statische Kondensation freigegebener (Gelenk-)FHG.
    Rueckgabe: kondensierte Matrix (12x12, Zeilen/Spalten der Gelenke = 0),
    kondensierter Lastvektor und Daten zur Rueckrechnung (Kcc^-1, Kcr, fc)."""
    if not released:
        return kl, fl, None
    c = np.array(sorted(set(released)), dtype=int)
    r = np.array([i for i in range(12) if i not in set(c)], dtype=int)
    Kcc = kl[np.ix_(c, c)]
    Kcr = kl[np.ix_(c, r)]
    try:
        Kcc_inv = np.linalg.inv(Kcc)
    except np.linalg.LinAlgError:
        Kcc_inv = np.linalg.pinv(Kcc)
    K = np.zeros_like(kl)
    K[np.ix_(r, r)] = kl[np.ix_(r, r)] - Kcr.T @ Kcc_inv @ Kcr
    f = np.zeros_like(fl)
    f[r] = fl[r] - Kcr.T @ Kcc_inv @ fl[c]
    return K, f, (c, r, Kcc_inv, Kcr)


def element_matrix(model: Model, e):
    """Elementsteifigkeitsmatrix im globalen System."""
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]

    if e.typ in LINE_TYPES:
        kl, T3, T, L = beam_local(model, e)
        if getattr(e, "hinge_springs", None):
            kl, _, _ = hinge_springs(kl, np.zeros(12), e.hinge_springs)
        if e.hinges:
            kl, _, _ = condense(kl, np.zeros(12), e.hinges)
        return T.T @ kl @ T

    if e.typ == "shell3":
        t = model.shells[e.sec].t
        K, _, _, _ = sh.k_shell3(X[0], X[1], X[2], mat.E, mat.nu, t)
        return K

    if e.typ == "shell4":
        t = model.shells[e.sec].t
        return sh.k_shell4(X[0], X[1], X[2], X[3], mat.E, mat.nu, t)

    if e.typ == "tet4":
        return sl.k_tet4(X, mat.E, mat.nu)[0]
    if e.typ == "tet10":
        return sl.k_tet10(X, mat.E, mat.nu)[0]
    if e.typ == "hex8":
        return sl.k_hex8(X, mat.E, mat.nu)[0]

    raise ValueError(f"unbekannter Elementtyp '{e.typ}'")


def element_mass(model: Model, e):
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]
    if e.typ in LINE_TYPES:
        sec = model.sections[e.sec]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        ml = bm.m_local_beam(mat.rho, sec.A, L, sec.Iy + sec.Iz)
        return T.T @ ml @ T
    if e.typ == "shell3":
        return sh.shell3_mass(X[0], X[1], X[2], mat.rho, model.shells[e.sec].t)
    if e.typ == "shell4":
        M = np.zeros((24, 24))
        for tri, f in [((0, 1, 2), 0.5), ((0, 2, 3), 0.5),
                       ((0, 1, 3), 0.5), ((1, 2, 3), 0.5)]:
            Me = sh.shell3_mass(X[tri[0]], X[tri[1]], X[tri[2]],
                                mat.rho, model.shells[e.sec].t)
            idx = []
            for n in tri:
                idx.extend(range(6 * n, 6 * n + 6))
            idx = np.array(idx)
            M[np.ix_(idx, idx)] += f * Me
        return M
    if e.typ in SOLID_TYPES:
        return np.diag(sl.lumped_mass(e.typ, X, mat.rho))
    raise ValueError(e.typ)


# --------------------------------------------------------------------------
# Elementschleifen (seriell oder parallel)
# --------------------------------------------------------------------------
def _matrix_chunk(model: Model, idx: list[int]) -> list[tuple]:
    out = []
    for i in idx:
        e = model.elements[i]
        out.append((element_dofs(e), np.asarray(element_matrix(model, e), float)))
    return out


def _mass_chunk(model: Model, idx: list[int]) -> list[tuple]:
    out = []
    for i in idx:
        e = model.elements[i]
        out.append((element_dofs(e), np.asarray(element_mass(model, e), float)))
    return out


def _assemble_triplets(model: Model, chunk_func, workers=None) -> sparse.csr_matrix:
    from . import parallel
    n = model.ndof
    ne = len(model.elements)
    if ne == 0:
        return sparse.csr_matrix((n, n))
    pairs = parallel.map_elements(chunk_func, model, list(range(ne)), workers=workers)
    rows, cols, vals = [], [], []
    for d, ke in pairs:
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(ke.ravel())
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()


def stiffness(model: Model, workers=None) -> sparse.csr_matrix:
    K = _assemble_triplets(model, _matrix_chunk, workers)
    # Federlager
    from . import supports as sup
    lin, _ = sup.split(sup.expand(model))
    springs = [(e.index, e.stiffness) for e in lin if e.typ == "spring" and e.stiffness]
    if springs:
        idx = np.array([i for i, _ in springs])
        val = np.array([k for _, k in springs])
        K = (K + sparse.coo_matrix((val, (idx, idx)), shape=K.shape)).tocsr()
    Kk = kopplungen(model, K)
    return (K + Kk).tocsr() if Kk is not None else K


def _trans_dofs(node: int) -> list[int]:
    """Die drei Verschiebungs-FHG eines Knotens."""
    return [NDOF * node, NDOF * node + 1, NDOF * node + 2]


def kopplungen(model: Model, K: sparse.spmatrix = None) -> sparse.spmatrix:
    """Steifigkeit der Knotenkopplungen (Kontaktfugen, starr oder federnd).

    Fuer jede Richtung n mit der Steifigkeit k gilt zwischen den Knoten a und b

        K += k * c c^T   mit c = [-n, n]

    - eine Feder, die den Abstand der beiden Knoten in Richtung n haelt.
    Starre Kopplungen (``inf``) werden als Straffeder gesetzt: 1e4-mal die
    groesste vorhandene Hauptdiagonale. Das ist das uebliche Strafverfahren;
    groesser gewaehlt wuerde die Matrix schlecht konditioniert, kleiner
    liesse die Fuge nach.
    """
    kopp = getattr(model, "kopplungen", None)
    if not kopp:
        return None
    n = model.ndof
    if K is None:
        K = _assemble_triplets(model, _matrix_chunk, None)
    diag = np.abs(np.asarray(K.diagonal()).ravel())
    gross = float(diag[diag > 0].max()) if np.any(diag > 0) else 1.0
    starr = 1e4 * gross
    rows, cols, vals = [], [], []
    for kp in kopp:
        d = np.array(_trans_dofs(int(kp.node_a)) + _trans_dofs(int(kp.node_b)), int)
        for richtung, wert in kp.paare():
            k = starr if not np.isfinite(wert) else float(wert)
            if k <= 0:
                continue
            c = np.concatenate([-richtung, richtung])
            ke = k * np.outer(c, c)
            r, cc = np.meshgrid(d, d, indexing="ij")
            rows.append(r.ravel())
            cols.append(cc.ravel())
            vals.append(ke.ravel())
    if not rows:
        return None
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n))


def mass(model: Model, workers=None) -> sparse.csr_matrix:
    return _assemble_triplets(model, _mass_chunk, workers)


def geometric_stiffness(model: Model, u: np.ndarray) -> sparse.csr_matrix:
    """Geometrische Steifigkeit aus vorhandenem Verformungszustand (nur Staebe)."""
    n = model.ndof
    rows, cols, vals = [], [], []
    for e in model.elements:
        if e.typ not in LINE_TYPES:
            continue
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        d = element_dofs(e)
        ul = T @ u[d]
        N = mat.E * sec.A / L * (ul[6] - ul[0])      # Zug positiv
        kg = bm.kg_local_beam(N, L, sec.A, sec.Iy + sec.Iz)
        kg = T.T @ kg @ T
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(kg.ravel())
    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()


# --------------------------------------------------------------------------
# Lasten
# --------------------------------------------------------------------------
def trapezoid_fixed_end_forces(q1, q2, L) -> np.ndarray:
    """Aequivalente Knotenlasten fuer linear veraenderliche Streckenlast
    q1 (Anfang) -> q2 (Ende) im lokalen System (Bernoulli)."""
    q1 = np.asarray(q1, float)
    q2 = np.asarray(q2, float)
    f = np.zeros(12)
    # axial
    f[0] += L * (2 * q1[0] + q2[0]) / 6.0
    f[6] += L * (q1[0] + 2 * q2[0]) / 6.0
    # qy -> Biegung x-y (uy, rz)
    f[1] += L * (7 * q1[1] + 3 * q2[1]) / 20.0
    f[7] += L * (3 * q1[1] + 7 * q2[1]) / 20.0
    f[5] += L ** 2 * (3 * q1[1] + 2 * q2[1]) / 60.0
    f[11] += -L ** 2 * (2 * q1[1] + 3 * q2[1]) / 60.0
    # qz -> Biegung x-z (uz, ry)
    f[2] += L * (7 * q1[2] + 3 * q2[2]) / 20.0
    f[8] += L * (3 * q1[2] + 7 * q2[2]) / 20.0
    f[4] += -L ** 2 * (3 * q1[2] + 2 * q2[2]) / 60.0
    f[10] += L ** 2 * (2 * q1[2] + 3 * q2[2]) / 60.0
    return f


def partial_trapezoid_fixed_end_forces(q1, q2, a, b, L) -> np.ndarray:
    """Aequivalente Knotenlasten einer Trapezlast auf dem **Abschnitt** [a, b]
    eines Stabes (lokal, Bernoulli): q1 bei x = a, q2 bei x = b.

    f = Integral von a bis b ueber N(x)^T q(x) dx mit den Ansatzfunktionen des
    Stabes (linear fuer die Laengskraft, Hermite-Polynome fuer die Biegung).
    Der Integrand ist hoechstens vom Grad 4; vier Gauss-Punkte sind exakt.
    Fuer a = 0, b = L ergibt sich dasselbe wie trapezoid_fixed_end_forces;
    fuer b -> a die Einzellast q (b - a) an der Stelle a.
    """
    q1 = np.asarray(q1, float)
    q2 = np.asarray(q2, float)
    a = max(0.0, float(a))
    b = L if b is None else min(float(b), L)
    f = np.zeros(12)
    if b <= a or L <= 0:
        return f
    xg, wg = np.polynomial.legendre.leggauss(4)
    for xi_g, w in zip(xg, wg):
        x = 0.5 * (a + b) + 0.5 * (b - a) * xi_g
        dw = 0.5 * (b - a) * w
        t = (x - a) / (b - a)
        q = (1.0 - t) * q1 + t * q2
        xi = x / L
        n1, n7 = 1.0 - xi, xi
        h1 = 1.0 - 3.0 * xi ** 2 + 2.0 * xi ** 3
        h2 = L * (xi - 2.0 * xi ** 2 + xi ** 3)
        h3 = 3.0 * xi ** 2 - 2.0 * xi ** 3
        h4 = L * (-xi ** 2 + xi ** 3)
        f[0] += dw * n1 * q[0]
        f[6] += dw * n7 * q[0]
        f[1] += dw * h1 * q[1]
        f[5] += dw * h2 * q[1]
        f[7] += dw * h3 * q[1]
        f[11] += dw * h4 * q[1]
        f[2] += dw * h1 * q[2]
        f[4] += -dw * h2 * q[2]
        f[8] += dw * h3 * q[2]
        f[10] += -dw * h4 * q[2]
    return f


def beam_load_local(model: Model, e, bl) -> tuple[np.ndarray, np.ndarray]:
    """Lokale Streckenlast (q1, q2) eines BeamLoad."""
    X = model.nodes[e.nodes]
    T3, L = bm.local_axes(X[0], X[1], e.roll)
    q1 = np.asarray(bl.q, float)
    q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1.copy()
    if bl.system == "global":
        q1 = T3 @ q1
        q2 = T3 @ q2
    return q1, q2


def element_equivalent_loads(model: Model, case: LoadCase) -> dict[int, np.ndarray]:
    """Lokale aequivalente Knotenlasten je Stabelement (Streckenlasten,
    Eigengewicht, Temperatur) - ohne Gelenkkondensation. Wird fuer die
    Schnittgroessenrueckrechnung gebraucht."""
    out: dict[int, np.ndarray] = {}
    g = np.asarray(case.gravity, float)
    for bl in case.beam_loads:
        e = model.elements[bl.elem]
        if e.typ not in LINE_TYPES:
            continue
        q1, q2 = beam_load_local(model, e, bl)
        L = model.element_length(bl.elem)
        if getattr(bl, "teilweise", False):
            f = partial_trapezoid_fixed_end_forces(q1, q2, bl.a, bl.b, L)
        else:
            f = trapezoid_fixed_end_forces(q1, q2, L)
        out[bl.elem] = out.get(bl.elem, np.zeros(12)) + f
    if np.any(g):
        for i, e in enumerate(model.elements):
            if e.typ in LINE_TYPES:
                mat = model.materials[e.mat]
                sec = model.sections[e.sec]
                X = model.nodes[e.nodes]
                T3, L = bm.local_axes(X[0], X[1], e.roll)
                q = T3 @ (mat.rho * sec.A * g)
                out[i] = out.get(i, np.zeros(12)) + bm.fixed_end_forces(q, L)
    for tl in case.temp_loads:
        e = model.elements[tl.elem]
        if e.typ not in LINE_TYPES:
            continue
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        f = np.zeros(12)
        Fn = mat.E * sec.A * mat.alpha * tl.dT
        f[0] -= Fn
        f[6] += Fn
        if tl.dT_z and sec.h > 0 and e.typ == "beam":
            Mt_ = mat.E * sec.Iy * mat.alpha * tl.dT_z / sec.h
            f[4] -= Mt_
            f[10] += Mt_
        out[tl.elem] = out.get(tl.elem, np.zeros(12)) + f
    return out


def element_distributed_loads(model: Model, case: LoadCase) -> dict[int, np.ndarray]:
    """Lokale Streckenlasten je Stabelement als **Abschnitte**, inkl.
    Eigengewicht: Feld (n, 8) mit Zeilen [a, b, q1x, q1y, q1z, q2x, q2y, q2z] -
    q1 bei x = a, q2 bei x = b. Fuer die Schnittgroessen an Zwischenstellen.
    Eine Last ueber die ganze Laenge ist ein Abschnitt [0, L]."""
    out: dict[int, np.ndarray] = {}
    g = np.asarray(case.gravity, float)

    def anhaengen(i, zeile):
        z = np.asarray(zeile, float).reshape(1, 8)
        out[i] = np.vstack([out[i], z]) if i in out else z
    for bl in case.beam_loads:
        e = model.elements[bl.elem]
        if e.typ not in LINE_TYPES:
            continue
        q1, q2 = beam_load_local(model, e, bl)
        L = model.element_length(bl.elem)
        a = max(0.0, float(getattr(bl, "a", 0.0) or 0.0))
        b = L if getattr(bl, "b", None) is None else min(float(bl.b), L)
        if b <= a:
            continue
        anhaengen(bl.elem, [a, b, *q1, *q2])
    if np.any(g):
        for i, e in enumerate(model.elements):
            if e.typ in LINE_TYPES:
                mat = model.materials[e.mat]
                sec = model.sections[e.sec]
                X = model.nodes[e.nodes]
                T3, L = bm.local_axes(X[0], X[1], e.roll)
                q = T3 @ (mat.rho * sec.A * g)
                anhaengen(i, [0.0, L, *q, *q])
    return out


def skaliere_abschnitte(q: np.ndarray, f: float) -> np.ndarray:
    """Abschnittslasten (n, 8) mit einem Faktor versehen (a, b bleiben)."""
    q = np.asarray(q, float).reshape(-1, 8).copy()
    q[:, 2:] *= f
    return q


def abschnitte_zusammen(alt, neu) -> np.ndarray:
    """Zwei Abschnittslisten aneinanderhaengen (None = leer)."""
    if alt is None:
        return np.asarray(neu, float).reshape(-1, 8)
    return np.vstack([np.asarray(alt, float).reshape(-1, 8),
                      np.asarray(neu, float).reshape(-1, 8)])


def lastresultierende(abschnitte, x: np.ndarray):
    """Resultierende Q(x) der Abschnittslasten ueber [0, x] und ihr Moment
    Mq(x) um die Stelle x (je Komponente) - fuer das Gleichgewicht am
    Teilstab. Rueckgabe (Q, Mq) mit Form (len(x), 3)."""
    x = np.asarray(x, float)
    Q = np.zeros((len(x), 3))
    Mq = np.zeros((len(x), 3))
    if abschnitte is None:
        return Q, Mq
    for zeile in np.asarray(abschnitte, float).reshape(-1, 8):
        a, b = float(zeile[0]), float(zeile[1])
        q1, q2 = zeile[2:5], zeile[5:8]
        if b <= a:
            continue
        s = np.clip(x, a, b) - a
        k = (q2 - q1) / (b - a)
        sN = s[:, None]
        R = q1 * sN + k * sN ** 2 / 2.0
        Q += R
        Mq += (x - a)[:, None] * R - (q1 * sN ** 2 / 2.0 + k * sN ** 3 / 3.0)
    return Q, Mq


def shell_thermal_loads(model: Model, e, dT: float) -> np.ndarray:
    """Aequivalente Knotenlasten einer gleichmaessigen Temperaturaenderung
    eines Schalenelements (Membrananteil), global."""
    mat = model.materials[e.mat]
    t = model.shells[e.sec].t
    X = model.nodes[e.nodes]
    tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
    nn = len(e.nodes)
    f = np.zeros(6 * nn)
    eps0 = mat.alpha * dT * np.array([1.0, 1.0, 0.0])
    Dm = sh._material_matrices(mat.E, mat.nu, t)[0]
    for tri in tris:
        T3, xy, A = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
        Bm, _ = sh.cst_b(xy)
        fm = A * (Bm.T @ (Dm @ eps0))           # [u1 v1 u2 v2 u3 v3] lokal
        for k, n in enumerate(tri):
            fl = np.array([fm[2 * k], fm[2 * k + 1], 0.0])
            f[6 * n:6 * n + 3] += T3.T @ fl
    return f


def solid_thermal_loads(model: Model, e, dT: float) -> np.ndarray:
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]
    D = sl.D_matrix(mat.E, mat.nu)
    eps0 = mat.alpha * dT * np.array([1.0, 1.0, 1.0, 0, 0, 0])
    s0 = D @ eps0
    if e.typ == "tet4":
        _, B, V = sl.k_tet4(X, mat.E, mat.nu)
        return V * (B.T @ s0)
    if e.typ == "tet10":
        f = np.zeros(30)
        for (r, s, t), w in zip(sl._TET_GP, sl._TET_W):
            _, dNr = sl.tet10_N_dN(r, s, t)
            J = dNr.T @ X
            dN = np.linalg.solve(J, dNr.T).T
            B = sl._B_from_grad(dN)
            f += w * np.linalg.det(J) * (B.T @ s0)
        return f
    f = np.zeros(24)
    for (r, s, t), w in zip(sl._HEX_GP, sl._HEX_W):
        _, dNr = sl.hex8_N_dN(r, s, t)
        J = dNr.T @ X
        dN = np.linalg.solve(J, dNr.T).T
        B = sl._B_from_grad(dN)
        f += w * np.linalg.det(J) * (B.T @ s0)
    return f


def load_vector(model: Model, case: LoadCase = None) -> np.ndarray:
    """Globaler Lastvektor eines Lastfalls (default: aktiver Lastfall)."""
    if case is None:
        case = model.case()
    elif isinstance(case, str):
        case = model.case(case)
    F = np.zeros(model.ndof)

    for l in case.nodal_loads:
        F[NDOF * l.node: NDOF * l.node + 6] += np.asarray(l.F, float)

    # Stablasten (Strecken-, Eigengewicht, Temperatur) mit Gelenkkondensation
    for i, fl in element_equivalent_loads(model, case).items():
        e = model.elements[i]
        kl, T3, T, L = beam_local(model, e)
        if getattr(e, "hinge_springs", None):
            kl, fl, _ = hinge_springs(kl, fl, e.hinge_springs)
        if e.hinges:
            _, fl, _ = condense(kl, fl, e.hinges)
        F[element_dofs(e)] += T.T @ fl

    for l in case.face_loads:
        e = model.elements[l.elem]
        X = model.nodes[e.nodes]
        if e.typ in SHELL_TYPES:
            tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
            f = np.zeros(6 * len(e.nodes))
            for tri in tris:
                if l.direction is not None:
                    _, _, A = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
                    d = np.asarray(l.direction, float)
                    d = d / (np.linalg.norm(d) or 1.0)
                    fn = l.p * A / 3.0 * d
                    for n in tri:
                        f[6 * n:6 * n + 3] += fn
                else:
                    ft = sh.shell3_pressure(X[tri[0]], X[tri[1]], X[tri[2]], l.p)
                    for k, n in enumerate(tri):
                        f[6 * n:6 * n + 6] += ft[6 * k:6 * k + 6]
            F[element_dofs(e)] += f
        elif e.typ in SOLID_TYPES:
            F[element_dofs(e)] += solid_face_pressure(model, e, l.p, l.face, l.direction)

    for tl in case.temp_loads:
        e = model.elements[tl.elem]
        if e.typ in SHELL_TYPES:
            F[element_dofs(e)] += shell_thermal_loads(model, e, tl.dT)
        elif e.typ in SOLID_TYPES:
            F[element_dofs(e)] += solid_thermal_loads(model, e, tl.dT)

    # Eigengewicht Schalen und Volumen (Staebe: siehe oben)
    g = np.asarray(case.gravity, float)
    if np.any(g):
        for e in model.elements:
            mat = model.materials[e.mat]
            X = model.nodes[e.nodes]
            if e.typ in SHELL_TYPES:
                t = model.shells[e.sec].t
                tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
                for tri in tris:
                    _, _, A = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
                    fn = mat.rho * t * A / 3.0 * g
                    for n in tri:
                        F[NDOF * e.nodes[n]: NDOF * e.nodes[n] + 3] += fn
            elif e.typ in SOLID_TYPES:
                m = sl.lumped_mass(e.typ, X, mat.rho)[0::3]
                for k, n in enumerate(e.nodes):
                    F[NDOF * n: NDOF * n + 3] += m[k] * g
    return F


SOLID_FACES = {
    "tet4": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
    "tet10": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
    "hex8": [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
}


def solid_face_pressure(model: Model, e, p: float, face: int, direction=None) -> np.ndarray:
    """Druck p auf Flaeche 'face' eines Volumenelements (positiv = nach innen).
    Rueckgabe: Lastvektor (3 * Knotenzahl)."""
    X = model.nodes[e.nodes]
    faces = SOLID_FACES[e.typ]
    f = np.zeros(3 * len(e.nodes))
    if face < 0 or face >= len(faces):
        return f
    fn = faces[face]
    P = X[list(fn)]
    if len(fn) == 3:
        tris = [(0, 1, 2)]
    else:
        tris = [(0, 1, 2), (0, 2, 3)]
    centroid = X.mean(axis=0)
    for tri in tris:
        a, b, c = P[tri[0]], P[tri[1]], P[tri[2]]
        nvec = np.cross(b - a, c - a)
        A = 0.5 * np.linalg.norm(nvec)
        if A <= 0:
            continue
        n = nvec / (2 * A)
        if np.dot(n, centroid - (a + b + c) / 3.0) < 0:
            n = -n                     # nach innen zeigend
        if direction is not None:
            d = np.asarray(direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
            fvec = p * A / 3.0 * d
        else:
            fvec = p * A / 3.0 * n
        for k in tri:
            node_local = fn[k]
            f[3 * node_local:3 * node_local + 3] += fvec
    return f


# --------------------------------------------------------------------------
def constrained_dofs(model: Model, K: sparse.csr_matrix):
    """Gesperrte FHG: Lager + FHG ohne Steifigkeit (z.B. Rotation an Volumenknoten).
    Rueckgabe (fixed_idx, prescribed_values)."""
    n = model.ndof
    fixed = np.zeros(n, dtype=bool)
    vals = np.zeros(n)

    diag = np.abs(K.diagonal())
    ref = diag.max() if diag.size and diag.max() > 0 else 1.0
    weak = diag < ref * 1e-12
    if model.has_contact:
        # FHG, die ihre Steifigkeit erst aus dem Kontakt bekommen (Schraube mit
        # Lochspiel, Reibflaeche), duerfen nicht vorab gesperrt werden.
        from . import contact as _ct
        held = _ct.contact_dofs(model, K)
        if held:
            weak[np.fromiter(held, dtype=int, count=len(held))] = False
    fixed |= weak

    from . import supports as sup
    lin, _ = sup.split(sup.expand(model))
    for e in lin:
        if e.typ == "rigid":
            fixed[e.index] = True
            vals[e.index] = e.value
    return fixed, vals
