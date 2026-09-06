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
from . import elemente as EL

#: Elementfamilien - siehe statik3d.elemente (dort steht das Verzeichnis)
SOLID_TYPES = EL.VOLUMEN_TYPEN
SHELL_TYPES = EL.SCHALEN_TYPEN
LINE_TYPES = EL.STAB_TYPEN                  # beam, truss, seil
PLANE_TYPES = EL.EBENE_TYPEN                # ebene3 .. ebene8
GRENZSCHICHT_TYPES = ("grenzschicht6", "grenzschicht8")
TRANSLATION_TYPES = EL.VERSCHIEBUNGS_TYPEN  # nur ux, uy, uz je Knoten


# --------------------------------------------------------------------------
def element_dofs(e, model: Model = None) -> np.ndarray:
    """Globale FHG-Nummern eines Elements.

    Volumen-, ebene und Grenzschichtelemente belegen nur die drei
    Verschiebungen je Knoten; alle anderen sechs. Ein Stab mit
    Woelbkrafttorsion haengt hinter den 12 Stab-FHG die zwei Woelb-FHG
    seiner Knoten an (sie stehen im Modell hinter den 6·nn Knoten-FHG) -
    dafuer braucht die Funktion das Modell.
    """
    if e.typ in TRANSLATION_TYPES:
        d = []
        for n in e.nodes:
            d.extend([NDOF * n, NDOF * n + 1, NDOF * n + 2])
        return np.array(d, dtype=int)
    d = []
    for n in e.nodes:
        d.extend(range(NDOF * n, NDOF * n + NDOF))
    if model is not None and model.stab_woelbt(e):
        wi = model.woelb_index()
        d.extend(wi[int(n)] for n in e.nodes)
    return np.array(d, dtype=int)


def beam_local(model: Model, e):
    """Lokale Steifigkeitsmatrix (12x12), T3, T (12x12), L eines Stabelements.

    Fachwerkstab und Seil: nur die Laengssteifigkeit (das Seil ist nach
    Theorie I. Ordnung ein Zugstab; Ausfall bei Druck ueber die
    Aktivmengen-Iteration, die Kettenlinie rechnet Theorie III. Ordnung).
    """
    mat = model.materials[e.mat]
    sec = model.sections[e.sec]
    X = model.nodes[e.nodes]
    T3, L = bm.local_axes(X[0], X[1], e.roll)
    T = bm.transform_matrix(T3)
    if e.typ in ("truss", "seil"):
        kl = bm.k_local_truss(mat.E, sec.A, L)
    else:
        kl = bm.k_local_beam(mat.E, mat.G, sec.A, sec.Iy, sec.Iz, sec.It,
                             L, sec.Asy, sec.Asz)
    return kl, T3, T, L


def beam_versatz(e):
    """Starre Versaetze der Stabenden (Exzentrizitaet) als 12x12-Matrix A
    in lokalen Achsen: u_stab = A u_knoten. None ohne Versatz."""
    ex = getattr(e, "exzentrizitaet", None)
    if not ex:
        return None
    r1 = np.zeros(3)
    r2 = np.zeros(3)
    try:
        if len(ex) >= 1 and ex[0] is not None:
            r1[:len(ex[0])] = np.asarray(ex[0], float)[:3]
        if len(ex) >= 2 and ex[1] is not None:
            r2[:len(ex[1])] = np.asarray(ex[1], float)[:3]
    except (TypeError, ValueError):
        return None
    if not (np.any(r1) or np.any(r2)):
        return None
    return bm.versatz_matrix(r1, r2)


def beam_woelb_local(model: Model, e):
    """Lokale 14x14-Steifigkeit eines Stabes mit Woelbkrafttorsion
    (12 Stab-FHG + Verwoelbung an beiden Enden), dazu T3, L."""
    mat = model.materials[e.mat]
    sec = model.sections[e.sec]
    X = model.nodes[e.nodes]
    T3, L = bm.local_axes(X[0], X[1], e.roll)
    kl = bm.k_local_beam14(mat.E, mat.G, sec.A, sec.Iy, sec.Iz, sec.It,
                           float(getattr(sec, "Iw", 0.0) or 0.0), L, sec.Asy, sec.Asz)
    return kl, T3, L


def transform14(T3: np.ndarray) -> np.ndarray:
    """Transformation der 14 FHG: 12 wie beim Stab, die Verwoelbungen sind
    skalar und bleiben, wie sie sind."""
    T = np.eye(14)
    T[:12, :12] = bm.transform_matrix(T3)
    return T


def laminat_von(model: Model, prop):
    """Laminat (A, B, D, Ds) einer geschichteten Schaleneigenschaft - None,
    wenn die Schale homogen ist. Eine Lage darf statt E/nu einen
    Werkstoffnamen ('material') nennen."""
    lagen = getattr(prop, "lagen", None) or []
    if not lagen:
        return None
    from .elements import shell_rm
    voll = []
    for l in lagen:
        l = dict(l)
        mname = l.pop("material", None) or l.pop("werkstoff", None)
        if mname and mname in model.materials:
            mat = model.materials[mname]
            l.setdefault("E", mat.E)
            l.setdefault("nu", mat.nu)
            l.setdefault("rho", mat.rho)
        voll.append(l)
    return shell_rm.abd_matrizen(voll)


def schalen_formulierung(e, prop) -> str:
    """'dkt' (Dreieck CST+DKT bzw. Viereck in DKT-Dreiecke zerlegt) oder
    'rm' (Reissner-Mindlin: MITC3, MITC4, shell6, shell8)."""
    f = (getattr(prop, "formulierung", "") or "").lower()
    if getattr(prop, "lagen", None):
        return "rm"
    if e.typ == "shell3":
        return "rm" if f == "mindlin" else "dkt"
    if e.typ == "shell4":
        return "dkt" if f == "dkt" else "rm"
    return "rm"


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
        if model.stab_woelbt(e):
            kl, T3, L = beam_woelb_local(model, e)
            A = beam_versatz(e)
            if A is not None:
                A14 = np.eye(14)
                A14[:12, :12] = A
                kl = A14.T @ kl @ A14
            T = transform14(T3)
            return T.T @ kl @ T
        kl, T3, T, L = beam_local(model, e)
        if getattr(e, "hinge_springs", None):
            kl, _, _ = hinge_springs(kl, np.zeros(12), e.hinge_springs)
        if e.hinges:
            kl, _, _ = condense(kl, np.zeros(12), e.hinges)
        A = beam_versatz(e)
        if A is not None:
            kl = A.T @ kl @ A
        return T.T @ kl @ T

    if e.typ in SHELL_TYPES:
        prop = model.shells[e.sec]
        if schalen_formulierung(e, prop) == "dkt":
            t = prop.t
            if e.typ == "shell3":
                K, _, _, _ = sh.k_shell3(X[0], X[1], X[2], mat.E, mat.nu, t)
                return K
            return sh.k_shell4(X[0], X[1], X[2], X[3], mat.E, mat.nu, t)
        from .elements import shell_rm
        return shell_rm.k_schale(e.typ, X, mat.E, mat.nu, prop.t, laminat=laminat_von(model, prop))

    if e.typ in SOLID_TYPES:
        return getattr(sl, "k_" + e.typ)(X, mat.E, mat.nu)[0]

    if e.typ in PLANE_TYPES:
        from .elements import ebene
        t = model.shells[e.sec].t if e.sec and e.sec in model.shells else 1.0
        return ebene.k_ebene(e.typ, X, mat.E, mat.nu, t, getattr(e, "zustand", "spannung"))

    if e.typ == "feder":
        from .elements import verbindung as vb
        fp = model.federn[e.sec]
        T3 = vb.feder_achsen(X[0], X[1], fp.achse, e.roll)
        return vb.k_feder(fp.k, T3)

    if e.typ in GRENZSCHICHT_TYPES:
        from .elements import verbindung as vb
        gp = model.grenzschichten[e.sec]
        k = len(e.nodes) // 2
        return vb.k_grenzschicht(X[:k], X[k:], gp.kn, gp.kt)

    raise ValueError(f"unbekannter Elementtyp '{e.typ}'")


def element_mass(model: Model, e):
    """Elementmassenmatrix im globalen System (Staebe konsistent, Schalen und
    Volumen konzentriert; Feder und Grenzschicht masselos)."""
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]
    if e.typ in LINE_TYPES:
        sec = model.sections[e.sec]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        if model.stab_woelbt(e):
            ml = bm.m_local_beam14(mat.rho, sec.A, L, sec.Iy + sec.Iz,
                                   float(getattr(sec, "Iw", 0.0) or 0.0))
            A = beam_versatz(e)
            if A is not None:
                A14 = np.eye(14)
                A14[:12, :12] = A
                ml = A14.T @ ml @ A14
            T = transform14(T3)
            return T.T @ ml @ T
        T = bm.transform_matrix(T3)
        ml = bm.m_local_beam(mat.rho, sec.A, L, sec.Iy + sec.Iz)
        A = beam_versatz(e)
        if A is not None:
            ml = A.T @ ml @ A
        return T.T @ ml @ T
    if e.typ in SHELL_TYPES:
        prop = model.shells[e.sec]
        if schalen_formulierung(e, prop) == "dkt":
            if e.typ == "shell3":
                return sh.shell3_mass(X[0], X[1], X[2], mat.rho, prop.t)
            M = np.zeros((24, 24))
            for tri, f in [((0, 1, 2), 0.5), ((0, 2, 3), 0.5),
                           ((0, 1, 3), 0.5), ((1, 2, 3), 0.5)]:
                Me = sh.shell3_mass(X[tri[0]], X[tri[1]], X[tri[2]], mat.rho, prop.t)
                idx = []
                for n in tri:
                    idx.extend(range(6 * n, 6 * n + 6))
                idx = np.array(idx)
                M[np.ix_(idx, idx)] += f * Me
            return M
        from .elements import shell_rm
        return shell_rm.masse_schale(e.typ, X, mat.rho, prop.t, laminat=laminat_von(model, prop))
    if e.typ in SOLID_TYPES:
        return np.diag(sl.lumped_mass(e.typ, X, mat.rho))
    if e.typ in PLANE_TYPES:
        from .elements import ebene
        t = model.shells[e.sec].t if e.sec and e.sec in model.shells else 1.0
        return np.diag(ebene.masse_ebene(e.typ, X, mat.rho, t, getattr(e, "zustand", "spannung")))
    if e.typ == "feder":
        return np.zeros((12, 12))
    if e.typ in GRENZSCHICHT_TYPES:
        n = 3 * len(e.nodes)
        return np.zeros((n, n))
    raise ValueError(e.typ)


def element_masse_knoten(model: Model, e) -> np.ndarray:
    """Konzentrierte Masse je Knoten eines Elements [kg] (Eigengewicht):
    die Verschiebungs-Diagonale der Massenmatrix, je Knoten gemittelt."""
    M = element_mass(model, e)
    d = np.diag(M)
    nk = len(e.nodes)
    fhg = 3 if e.typ in TRANSLATION_TYPES else 6
    out = np.zeros(nk)
    for k in range(nk):
        out[k] = float(d[fhg * k:fhg * k + 3].mean())
    return out


# --------------------------------------------------------------------------
# Elementschleifen (seriell oder parallel)
# --------------------------------------------------------------------------
def elementfehler(model: Model, i: int, ex: Exception) -> ValueError:
    """Aus einem Fehler tief in der Elementformulierung eine Meldung machen,
    mit der man das Element auch findet.

    Bisher kam aus einer halben Million Elementen nur „entartetes Tet4“
    zurueck - ohne Nummer, ohne Knoten, ohne Koerper. Wer das Netz reparieren
    soll, braucht beides.
    """
    try:
        e = model.elements[i]
        kn = ", ".join(str(int(k) + 1) for k in e.nodes)
        wo = f" im Volumen/Objekt '{e.group}'" if getattr(e, "group", "") else ""
        return ValueError(f"Element {i + 1} ({e.typ}{wo}, Knoten {kn}): {ex}")
    except Exception:      # noqa: BLE001 - die Meldung darf nie selbst scheitern
        return ValueError(f"Element {i + 1}: {ex}")


def _matrix_chunk(model: Model, idx: list[int]) -> list[tuple]:
    out = []
    for i in idx:
        e = model.elements[i]
        try:
            ke = np.asarray(element_matrix(model, e), float)
        except Exception as ex:      # noqa: BLE001
            raise elementfehler(model, i, ex) from ex
        out.append((element_dofs(e, model), ke))
    return out


def _mass_chunk(model: Model, idx: list[int]) -> list[tuple]:
    out = []
    for i in idx:
        e = model.elements[i]
        try:
            me = np.asarray(element_mass(model, e), float)
        except Exception as ex:      # noqa: BLE001
            raise elementfehler(model, i, ex) from ex
        out.append((element_dofs(e, model), me))
    return out


def aktive_indizes(model: Model, aktiv=None) -> list[int]:
    """Die Elemente, die wirken: alle oder die der Aktivmaske (Situation)."""
    ne = len(model.elements)
    if aktiv is None:
        return list(range(ne))
    return [i for i in range(ne) if aktiv[i]]


def _assemble_triplets(model: Model, chunk_func, workers=None, idx=None) -> sparse.csr_matrix:
    from . import parallel
    n = model.ndof
    idx = list(range(len(model.elements))) if idx is None else list(idx)
    if not idx:
        return sparse.csr_matrix((n, n))
    pairs = parallel.map_elements(chunk_func, model, idx, workers=workers)
    rows, cols, vals = [], [], []
    for d, ke in pairs:
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(ke.ravel())
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(n, n)).tocsr()


def stiffness(model: Model, workers=None, aktiv=None) -> sparse.csr_matrix:
    """Gesamtsteifigkeit; ``aktiv`` (Maske je Element) laesst abgeschaltete
    Elemente einer Situation weg."""
    K = _assemble_triplets(model, _matrix_chunk, workers, aktive_indizes(model, aktiv))
    # Federlager
    from . import supports as sup
    lin, _ = sup.split(sup.expand(model))
    springs = [(e.index, e.stiffness) for e in lin if e.typ == "spring" and e.stiffness]
    if springs:
        idx = np.array([i for i, _ in springs])
        val = np.array([k for _, k in springs])
        K = (K + sparse.coo_matrix((val, (idx, idx)), shape=K.shape)).tocsr()
    Kk = kopplungen(model, K, aktiv=aktiv)
    if Kk is not None:
        K = (K + Kk).tocsr()
    Ks = starrkoerper(model, K)
    return (K + Ks).tocsr() if Ks is not None else K


def starrkoerper(model: Model, K: sparse.spmatrix = None) -> sparse.spmatrix:
    """Steifigkeit der starren Koerper (RBE2) und Verteilkopplungen (RBE3)
    im Strafverfahren: K += k Gᵀ G mit den Zwangsbedingungszeilen G aus
    verbindung.starrkoerper_matrix und k = 1e4-mal die groesste
    Hauptdiagonale (wie bei den Kopplungen)."""
    sk_liste = getattr(model, "starrkoerper", None) or []
    if not sk_liste:
        return None
    from .elements import verbindung as vb
    n = model.ndof
    if K is None:
        K = _assemble_triplets(model, _matrix_chunk, None)
    diag = np.abs(np.asarray(K.diagonal()).ravel())
    gross = float(diag[diag > 0].max()) if np.any(diag > 0) else 1.0
    k = 1e4 * gross
    rows, cols, vals = [], [], []
    for sk in sk_liste:
        slaves = [int(x) for x in sk.slaves if 0 <= int(x) < model.nn and int(x) != int(sk.master)]
        if not slaves or not 0 <= int(sk.master) < model.nn:
            continue
        gew = list(sk.gewichte or [])
        gew = gew if len(gew) == len(slaves) else None
        G = vb.starrkoerper_matrix(model.nodes[int(sk.master)], model.nodes[slaves], sk.art, gew)
        d = np.array(list(range(NDOF * int(sk.master), NDOF * int(sk.master) + NDOF))
                     + [x for sl_ in slaves for x in range(NDOF * sl_, NDOF * sl_ + NDOF)], int)
        Ke = vb.starrkoerper_steifigkeit(G, k)
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(Ke.ravel())
    if not rows:
        return None
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))


def _trans_dofs(node: int) -> list[int]:
    """Die drei Verschiebungs-FHG eines Knotens."""
    return [NDOF * node, NDOF * node + 1, NDOF * node + 2]


def kopplungen(model: Model, K: sparse.spmatrix = None, aktiv=None) -> sparse.spmatrix:
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
    kn_aktiv = None
    if aktiv is not None:
        from .situationen import aktive_knoten
        kn_aktiv = aktive_knoten(model, aktiv)
    for kp in kopp:
        if kn_aktiv is not None and not (kn_aktiv[int(kp.node_a)] and kn_aktiv[int(kp.node_b)]):
            continue                      # Fuge an einem Knoten ohne wirksames Element
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


def mass(model: Model, workers=None, aktiv=None) -> sparse.csr_matrix:
    """Gesamtmasse (konzentriert) samt Punktmassen; ``aktiv`` laesst
    abgeschaltete Elemente weg."""
    M = _assemble_triplets(model, _mass_chunk, workers, aktive_indizes(model, aktiv))
    Mp = punktmassen(model)
    return (M + Mp).tocsr() if Mp is not None else M


def punktmassen(model: Model) -> sparse.spmatrix:
    """Diagonale Massenmatrix der Punktmassen (Masse auf ux, uy, uz;
    Drehtraegheiten auf rx, ry, rz)."""
    pm = getattr(model, "punktmassen", None) or []
    if not pm:
        return None
    n = model.ndof
    idx, val = [], []
    for p in pm:
        node = int(p.node)
        if not 0 <= node < model.nn:
            continue
        for d in range(3):
            idx.append(NDOF * node + d)
            val.append(float(p.masse))
        J = list(p.traegheit or [0.0, 0.0, 0.0]) + [0.0, 0.0, 0.0]
        for d in range(3):
            idx.append(NDOF * node + 3 + d)
            val.append(float(J[d]))
    if not idx:
        return None
    return sparse.coo_matrix((np.array(val), (np.array(idx), np.array(idx))), shape=(n, n))


def daempfung(model: Model) -> sparse.csr_matrix:
    """Daempfungsmatrix der diskreten Daempfer (viskos, wie Federn mit c
    statt k; node_b = -1: gegen den Boden)."""
    n = model.ndof
    dl = getattr(model, "daempfer", None) or []
    if not dl:
        return sparse.csr_matrix((n, n))
    from .elements import verbindung as vb
    rows, cols, vals = [], [], []
    for dp in dl:
        a, b = int(dp.node_a), int(dp.node_b)
        if not 0 <= a < model.nn:
            continue
        Pa = model.nodes[a]
        Pb = model.nodes[b] if 0 <= b < model.nn else Pa
        T3 = vb.feder_achsen(Pa, Pb, dp.achse)
        C = vb.k_feder(dp.c, T3)
        if 0 <= b < model.nn:
            d = np.array(list(range(NDOF * a, NDOF * a + NDOF)) + list(range(NDOF * b, NDOF * b + NDOF)), int)
            Ce = C
        else:
            d = np.array(list(range(NDOF * a, NDOF * a + NDOF)), int)
            Ce = C[:6, :6]
        r, c = np.meshgrid(d, d, indexing="ij")
        rows.append(r.ravel())
        cols.append(c.ravel())
        vals.append(Ce.ravel())
    if not rows:
        return sparse.csr_matrix((n, n))
    return sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)).tocsr()


def geometric_stiffness(model: Model, u: np.ndarray, aktiv=None) -> sparse.csr_matrix:
    """Geometrische Steifigkeit aus vorhandenem Verformungszustand (nur Staebe);
    abgeschaltete Elemente (``aktiv`` False) bleiben weg."""
    n = model.ndof
    rows, cols, vals = [], [], []
    for i, e in enumerate(model.elements):
        if e.typ not in LINE_TYPES or not _wirkt(aktiv, i):
            continue
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        X = model.nodes[e.nodes]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        T = bm.transform_matrix(T3)
        d = element_dofs(e, model)[:12]
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


def _wirkt(aktiv, i: int) -> bool:
    return aktiv is None or bool(aktiv[int(i)])


def element_equivalent_loads(model: Model, case: LoadCase, aktiv=None) -> dict[int, np.ndarray]:
    """Lokale aequivalente Knotenlasten je Stabelement (Streckenlasten,
    Eigengewicht, Temperatur) - ohne Gelenkkondensation. Wird fuer die
    Schnittgroessenrueckrechnung gebraucht. ``aktiv``: abgeschaltete
    Elemente einer Situation tragen keine Last."""
    out: dict[int, np.ndarray] = {}
    g = np.asarray(case.gravity, float)
    for bl in case.beam_loads:
        e = model.elements[bl.elem]
        if e.typ not in LINE_TYPES or not _wirkt(aktiv, bl.elem):
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
            if e.typ in LINE_TYPES and _wirkt(aktiv, i):
                mat = model.materials[e.mat]
                sec = model.sections[e.sec]
                X = model.nodes[e.nodes]
                T3, L = bm.local_axes(X[0], X[1], e.roll)
                q = T3 @ (mat.rho * sec.A * g)
                out[i] = out.get(i, np.zeros(12)) + bm.fixed_end_forces(q, L)
    for tl in case.temp_loads:
        e = model.elements[tl.elem]
        if e.typ not in LINE_TYPES or not _wirkt(aktiv, tl.elem):
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
    # Vorspannung in Staeben: der Stab will sich um F/(EA) verkuerzen - wie
    # eine Abkuehlung ziehen die aequivalenten Knotenlasten die Enden zusammen
    for v in getattr(case, "vorspannungen", None) or []:
        if getattr(v, "art", "stab") != "stab" or not v.kraft:
            continue
        mem = model.members.get(v.ziel)
        for i in (mem.elements if mem else []):
            i = int(i)
            if (not 0 <= i < len(model.elements) or model.elements[i].typ not in LINE_TYPES
                    or not _wirkt(aktiv, i)):
                continue
            f = np.zeros(12)
            f[0] += float(v.kraft)
            f[6] -= float(v.kraft)
            out[i] = out.get(i, np.zeros(12)) + f
    return out


def element_distributed_loads(model: Model, case: LoadCase, aktiv=None) -> dict[int, np.ndarray]:
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
        if e.typ not in LINE_TYPES or not _wirkt(aktiv, bl.elem):
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
            if e.typ in LINE_TYPES and _wirkt(aktiv, i):
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
    prop = model.shells[e.sec]
    X = model.nodes[e.nodes]
    if schalen_formulierung(e, prop) != "dkt":
        from .elements import shell_rm
        return shell_rm.temperatur_schale(e.typ, X, mat.E, mat.nu, prop.t, mat.alpha, dT,
                                          laminat=laminat_von(model, prop))
    t = prop.t
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
    """Aequivalente Knotenlasten einer gleichmaessigen Temperaturaenderung
    eines Volumenelements: die Anfangsspannung D eps0."""
    mat = model.materials[e.mat]
    D = sl.D_matrix(mat.E, mat.nu)
    eps0 = mat.alpha * dT * np.array([1.0, 1.0, 1.0, 0, 0, 0])
    return solid_initial_stress_loads(model, e, D @ eps0)


def ebene_thermal_loads(model: Model, e, dT: float) -> np.ndarray:
    """Temperaturlasten eines ebenen Elements."""
    from .elements import ebene
    mat = model.materials[e.mat]
    X = model.nodes[e.nodes]
    t = model.shells[e.sec].t if e.sec and e.sec in model.shells else 1.0
    return ebene.temperatur_ebene(e.typ, X, mat.E, mat.nu, t, mat.alpha, dT,
                                  getattr(e, "zustand", "spannung"))


def solid_initial_stress_loads(model: Model, e, s0) -> np.ndarray:
    """Aequivalente Knotenlasten einer Anfangsspannung s0 (Voigt: xx, yy, zz,
    xy, yz, xz) im Volumenelement: f = ∫ Bᵀ s0 dV - Temperatur, Vorspannung."""
    X = model.nodes[e.nodes]
    s0 = np.asarray(s0, float)
    if e.typ in SOLID_TYPES:
        return sl.anfangsspannungs_lasten(e.typ, X, s0)
    return np.zeros(3 * len(e.nodes))


def solid_prestress(model: Model, v) -> dict:
    """{Element: Anfangsspannung (Voigt)} einer Vorspannung in einem
    Volumenkoerper: einachsig -F/A laengs der Achse, in allen Elementen."""
    elems, a, A_q = model.vorspannung_koerper(v)
    if not elems or A_q <= 0 or not v.kraft:
        return {}
    s = -float(v.kraft) / A_q
    s0 = s * np.array([a[0] * a[0], a[1] * a[1], a[2] * a[2], a[0] * a[1], a[1] * a[2], a[0] * a[2]])
    return {i: s0 for i in elems if model.elements[i].typ in SOLID_TYPES}


def load_vector(model: Model, case: LoadCase = None, aktiv=None) -> np.ndarray:
    """Globaler Lastvektor eines Lastfalls (default: aktiver Lastfall).
    ``aktiv``: abgeschaltete Elemente einer Situation tragen keine Last;
    Knotenlasten an Knoten ohne wirksames Element entfallen."""
    if case is None:
        case = model.case()
    elif isinstance(case, str):
        case = model.case(case)
    F = np.zeros(model.ndof)
    kn_aktiv = None
    if aktiv is not None:
        from .situationen import aktive_knoten
        kn_aktiv = aktive_knoten(model, aktiv)

    for l in case.nodal_loads:
        if kn_aktiv is not None and not kn_aktiv[int(l.node)]:
            continue
        F[NDOF * l.node: NDOF * l.node + 6] += np.asarray(l.F, float)

    # Stablasten (Strecken-, Eigengewicht, Temperatur) mit Gelenkkondensation;
    # bei Exzentrizitaet auf die Knoten umgerechnet (f_knoten = Aᵀ f_stab)
    for i, fl in element_equivalent_loads(model, case, aktiv).items():
        e = model.elements[i]
        kl, T3, T, L = beam_local(model, e)
        if getattr(e, "hinge_springs", None):
            kl, fl, _ = hinge_springs(kl, fl, e.hinge_springs)
        if e.hinges:
            _, fl, _ = condense(kl, fl, e.hinges)
        A = beam_versatz(e)
        if A is not None:
            fl = A.T @ fl
        F[element_dofs(e, model)[:12]] += T.T @ fl

    for l in case.face_loads:
        if not _wirkt(aktiv, l.elem):
            continue
        e = model.elements[l.elem]
        X = model.nodes[e.nodes]
        if e.typ in SHELL_TYPES:
            F[element_dofs(e)] += shell_face_load(model, e, l.p, l.direction)
        elif e.typ in SOLID_TYPES:
            F[element_dofs(e)] += solid_face_pressure(model, e, l.p, l.face, l.direction)
        elif e.typ in PLANE_TYPES:
            from .elements import ebene
            F[element_dofs(e)] += ebene.kantenlast_ebene(
                e.typ, X, int(l.face), l.p, getattr(e, "zustand", "spannung"),
                None if l.direction is None else np.asarray(l.direction, float))

    for tl in case.temp_loads:
        if not _wirkt(aktiv, tl.elem):
            continue
        e = model.elements[tl.elem]
        if e.typ in SHELL_TYPES:
            F[element_dofs(e)] += shell_thermal_loads(model, e, tl.dT)
        elif e.typ in SOLID_TYPES:
            F[element_dofs(e)] += solid_thermal_loads(model, e, tl.dT)
        elif e.typ in PLANE_TYPES:
            F[element_dofs(e)] += ebene_thermal_loads(model, e, tl.dT)
    # Vorspannung in Volumenkoerpern (Schrauben): einachsige Anfangsspannung
    # -F/A laengs der Achse in allen Elementen des Koerpers
    for v in getattr(case, "vorspannungen", None) or []:
        if getattr(v, "art", "stab") != "koerper":
            continue
        for i, s0 in solid_prestress(model, v).items():
            if _wirkt(aktiv, i):
                F[element_dofs(model.elements[i])] += solid_initial_stress_loads(model, model.elements[i], s0)

    # Eigengewicht Schalen, Volumen und ebene Elemente (Staebe: siehe oben)
    # ueber die konzentrierten Knotenmassen; dazu die Punktmassen
    g = np.asarray(case.gravity, float)
    if np.any(g):
        for i, e in enumerate(model.elements):
            if not _wirkt(aktiv, i) or e.typ in LINE_TYPES or e.typ == "feder" \
                    or e.typ in GRENZSCHICHT_TYPES:
                continue
            m = element_masse_knoten(model, e)
            for k, n in enumerate(e.nodes):
                F[NDOF * n: NDOF * n + 3] += m[k] * g
        for p in (getattr(model, "punktmassen", None) or []):
            n = int(p.node)
            if 0 <= n < model.nn and (kn_aktiv is None or kn_aktiv[n]):
                F[NDOF * n: NDOF * n + 3] += float(p.masse) * g
    return F


def shell_face_load(model: Model, e, p: float, direction=None) -> np.ndarray:
    """Konsistente Knotenlasten einer Flaechenlast p auf einem Schalenelement,
    global; ohne Richtung in Normalenrichtung des Elements."""
    prop = model.shells[e.sec]
    X = model.nodes[e.nodes]
    if schalen_formulierung(e, prop) != "dkt":
        from .elements import shell_rm
        f = shell_rm.flaechenlast_schale(e.typ, X, p)
        if direction is not None:
            # Knotengewichte der Normallast auf die gegebene Richtung umlenken
            T3, _xy, _A, _v = shell_rm.schalen_frame(X)
            n = T3[2]
            d = np.asarray(direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
            g = np.zeros_like(f)
            for k in range(len(e.nodes)):
                w = float(f[6 * k:6 * k + 3] @ n)
                g[6 * k:6 * k + 3] = w * d
            return g
        return f
    tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
    f = np.zeros(6 * len(e.nodes))
    for tri in tris:
        if direction is not None:
            _, _, A = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
            d = np.asarray(direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
            fn = p * A / 3.0 * d
            for n in tri:
                f[6 * n:6 * n + 3] += fn
        else:
            ft = sh.shell3_pressure(X[tri[0]], X[tri[1]], X[tri[2]], p)
            for k, n in enumerate(tri):
                f[6 * n:6 * n + 6] += ft[6 * k:6 * k + 6]
    return f


#: Seiten der Volumenelemente (nur die Eckknoten, Rechtsschraube nach aussen) -
#: gefuehrt in elements.solid (FLAECHEN_ECKEN); FLAECHEN dort hat auch die
#: Kantenmitten der quadratischen Typen.
SOLID_FACES = getattr(sl, "FLAECHEN_ECKEN", {
    "tet4": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
    "tet10": [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)],
    "hex8": [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
})


def solid_face_pressure(model: Model, e, p: float, face: int, direction=None) -> np.ndarray:
    """Druck p auf Seite 'face' eines Volumenelements (positiv = nach innen),
    konsistent auf alle Knoten der Seite verteilt (bei quadratischen Seiten
    auch auf die Kantenmitten). Rueckgabe: Lastvektor (3 * Knotenzahl)."""
    X = model.nodes[e.nodes]
    faces = sl.FLAECHEN[e.typ]
    f = np.zeros(3 * len(e.nodes))
    if face < 0 or face >= len(faces):
        return f
    fn = list(faces[face])
    P = X[fn]
    ecken = P[:4] if len(fn) in (4, 8) else P[:3]
    nvec = np.cross(ecken[1] - ecken[0], ecken[2] - ecken[0])
    if len(ecken) == 4:
        nvec = nvec + np.cross(ecken[2] - ecken[0], ecken[3] - ecken[0])
    ln = float(np.linalg.norm(nvec))
    if ln <= 0:
        return f
    n = nvec / ln
    if np.dot(n, X.mean(axis=0) - ecken.mean(axis=0)) < 0:
        n = -n                                  # nach innen zeigend
    if direction is not None:
        d = np.asarray(direction, float)
        d = d / (np.linalg.norm(d) or 1.0)
    else:
        d = n
    fk = sl.flaechenlast_knoten(P, p, d)        # (k, 3)
    for k, node_local in enumerate(fn):
        f[3 * node_local:3 * node_local + 3] += fk[k]
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
    # Woelbeinspannung: die Verwoelbung ist am Knoten behindert
    wi = model.woelb_index() if model.ndof > model.nn * NDOF else {}
    if wi:
        for s_ in model.supports:
            if getattr(s_, "woelb", False) and int(s_.node) in wi:
                fixed[wi[int(s_.node)]] = True
    return fixed, vals
