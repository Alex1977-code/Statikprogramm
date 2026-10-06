"""Residuenbasierter Fehlerschaetzer je Zelle (Teilprojekt 6a, Phase 1; Vorgabe 8.4; Plan 2026-10-06-tp6a-phase1-schaetzer.md).

eta_K^2 = (1/E) [ (h/p)^2 ||f + div sigma_h||^2_{K cap Omega} + 1/2 sum_F (h_F/p) ||[sigma_h n]||^2_{F cap Omega} + (h/p) ||t - sigma_h n||^2_{Gamma_N cap K} ]
          + E (p^2/h) ||P (u_h - g)||^2_{Gamma_D cap K}

Einheit N mm (Energie). Die Flaechen zwischen Zellen werden mit Tensor-Gauss je Unterquadrat (2^tiefe x 2^tiefe) und Punkttest integriert (erste Ordnung in der
Geometrie, Entwurf 6a Abschnitt 3). Freie Oberflaeche sind alle Oberflaechenpunkte ausser denen eines Verschiebungsrands (Zuordnung ueber die Koordinaten:
die Raender sind Auswahlen der Oberflaechenquadratur); ihre Soll-Traktion kommt aus den aufgezeichneten Flaechenlasten, sonst null.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .basis import basis_3d, basis_3d_hesse, gauss_1d
from .elastizitaet import b_matrizen, d_matrix, lame
from .rand import _zellweise, nn_matrizen

ANTEILE = ("residuum", "sprung", "neumann", "dirichlet")


def flaechen_paare(gitter) -> np.ndarray:
    """(k,4): Zelle c, Nachbar n, Achse, Seite (+1/-1) je Flaeche zwischen zwei aktiven Zellen. Jede Flaeche einmal: von der feineren Zelle aus, bei gleicher
    Ebene von der mit dem kleineren Index. Nachbar ueber einen Probepunkt knapp jenseits der Flaechenmitte (an einer feineren Nachbarflaeche liegt er auf einer
    Kante der feinen Zellen; welche gefunden wird, ist gleich, sie ist feiner und wird uebersprungen)."""
    nz = len(gitter.ijk)
    lo, hi = gitter.zellbox(np.arange(nz))
    m = 0.5 * (lo + hi)
    hl = 0.5 * (hi - lo)[:, 0]
    c = np.arange(nz)
    teile = []
    for achse in range(3):
        for seite in (-1, 1):
            P = m.copy()
            P[:, achse] += seite * hl * (1.0 + 1e-6)
            nb = gitter.zelle_finden(P)
            ok = (nb >= 0) & (nb != c)
            nbs = np.where(ok, nb, 0)
            ok &= gitter.ebene[nbs] <= gitter.ebene[c]
            ok &= ~((gitter.ebene[nbs] == gitter.ebene[c]) & (nbs < c))
            k = int(ok.sum())
            teile.append(np.stack([c[ok], nb[ok], np.full(k, achse), np.full(k, seite)], axis=1))
    return np.concatenate(teile).astype(int) if teile else np.zeros((0, 4), int)


def flaechen_punkte(gitter, c: int, achse: int, seite: int, n_gauss: int, tiefe: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Werkstoffpunkte (q,3) und Gewichte (q,) auf der Flaeche (achse, seite) der Zelle c: 2^tiefe x 2^tiefe Unterquadrate mit n_gauss x n_gauss Gauss-Punkten,
    Punkttest gegen die Geometrie."""
    lo, hi = gitter.zellbox(int(c))
    a, b = [d for d in range(3) if d != achse]
    k = 2 ** int(tiefe)
    x, w = gauss_1d(int(n_gauss))
    t = ((np.arange(k)[:, None] + 0.5 * (x[None, :] + 1.0)) / k).ravel()
    wt = np.tile(w, k) / (2.0 * k)
    A, B = np.meshgrid(t, t, indexing="ij")
    WA, WB = np.meshgrid(wt, wt, indexing="ij")
    P = np.empty((A.size, 3))
    P[:, achse] = hi[achse] if seite > 0 else lo[achse]
    P[:, a] = lo[a] + A.ravel() * (hi[a] - lo[a])
    P[:, b] = lo[b] + B.ravel() * (hi[b] - lo[b])
    W = (WA * WB).ravel() * (hi[a] - lo[a]) * (hi[b] - lo[b])
    innen = np.asarray(gitter.geometrie.innen(P), bool)
    return P[innen], W[innen]


@dataclass
class Schaetzung:
    """eta^2 je Anteil (ANTEILE) und Zelle, Einheit N mm."""
    eta2: dict

    @property
    def zelle(self) -> np.ndarray:
        return np.sqrt(sum(self.eta2[k] for k in ANTEILE))

    @property
    def gesamt(self) -> float:
        return float(np.sqrt(sum(float(self.eta2[k].sum()) for k in ANTEILE)))


def _koeff(problem, U, c: int) -> np.ndarray:
    """Modenkoeffizienten (m,3) der Zelle c."""
    return U[problem.gitter.zell_dofs(c)].reshape(-1, 3)


def _spannung(problem, D, c: int, xi, Uc) -> np.ndarray:
    g = problem.gitter
    _, dN = basis_3d(g.p, xi)
    eps = np.einsum("qsd,d->qs", b_matrizen(dN * (2.0 / float(g.h_zelle(c)))), Uc.ravel())
    return eps @ D.T


def _traktion(s, n) -> np.ndarray:
    return np.einsum("qab,qb->qa", nn_matrizen(n), s)


def _residuum(problem, U, f, lam, mu, eta2) -> None:
    g, q = problem.gitter, problem.quadratur
    E, p = problem.werkstoff.E, g.p
    for c in range(len(g.ijk)):
        P, W, I = q.zelle(c)
        if len(P) == 0 or not I.any():
            continue
        Pm, Wm = P[I], W[I]
        h = float(g.h_zelle(c))
        H = basis_3d_hesse(p, g.lokal(Pm, np.full(len(Pm), c))) * (2.0 / h) ** 2
        d2u = np.einsum("qkij,ka->qaij", H, _koeff(problem, U, c))
        # div sigma = mu Laplace u + (lambda + mu) grad div u bei festem Werkstoff
        r = mu * np.einsum("qajj->qa", d2u) + (lam + mu) * np.einsum("qbab->qa", d2u) + f(Pm)
        eta2["residuum"][c] += (h / p) ** 2 / E * float((Wm * (r * r).sum(axis=1)).sum())


def _spruenge(problem, U, D, eta2, tiefe: int) -> None:
    g = problem.gitter
    E, p = problem.werkstoff.E, g.p
    for c, k, achse, seite in flaechen_paare(g):
        P, W = flaechen_punkte(g, c, achse, seite, p + 1, tiefe)
        if len(P) == 0:
            continue
        n = np.zeros((len(P), 3))
        n[:, achse] = seite
        s_c = _spannung(problem, D, c, g.lokal(P, np.full(len(P), c)), _koeff(problem, U, c))
        s_k = _spannung(problem, D, k, g.lokal(P, np.full(len(P), k)), _koeff(problem, U, k))
        j = _traktion(s_c - s_k, n)
        beitrag = 0.5 * (float(g.h_zelle(c)) / p) / E * float((W * (j * j).sum(axis=1)).sum())
        eta2["sprung"][c] += beitrag
        eta2["sprung"][k] += beitrag


def _randwerte(problem, U, D, fq):
    """u_h (q,3) und Traktion sigma_h n (q,3) an den Punkten einer Flaechenquadratur."""
    u = np.zeros((len(fq.punkte), 3))
    t = np.zeros((len(fq.punkte), 3))
    for c, idx, N, G in _zellweise(problem.gitter, fq):
        Uc = _koeff(problem, U, c)
        u[idx] = N @ Uc
        s = np.einsum("qsd,d->qs", b_matrizen(G), Uc.ravel()) @ D.T
        t[idx] = _traktion(s, fq.normalen[idx])
    return u, t


def _rand(problem, U, D, vorgaben, eta2) -> None:
    g = problem.gitter
    E, p = problem.werkstoff.E, g.p
    fq = problem.oberflaeche
    index = {fq.punkte[i].tobytes(): i for i in range(len(fq.punkte))}
    t_soll = np.zeros((len(fq.punkte), 3))
    for fql, T in problem.flaechenlasten:
        for i, P in enumerate(fql.punkte):
            j = index.get(P.tobytes())
            if j is not None:
                t_soll[j] += T[i]
    frei = np.ones(len(fq.punkte), bool)
    for r in problem.raender.values():
        for P in r.quadratur.punkte:
            j = index.get(P.tobytes())
            if j is not None:
                frei[j] = False
    hk = g.h_zelle(fq.zelle)
    # freie und belastete Oberflaeche: t - sigma_h n
    if frei.any():
        fr = fq.auswahl(frei)
        _, t = _randwerte(problem, U, D, fr)
        res = t_soll[frei] - t
        np.add.at(eta2["neumann"], fr.zelle, (hk[frei] / p) / E * fr.gewichte * (res * res).sum(axis=1))
    # Verschiebungsraender: Nitsche-Rest, bei 'normal' und 'schnitt' zusaetzlich der tangentiale Traktionsrest. An einer Schnittebene sind die drei
    # In-Ebene-Starrkoerpermoden (Querkraft, Torsion) als Mittelwertzwaenge gehalten: ihr Anteil an der Tangentialtraktion ist Reaktion und kein Fehler,
    # er wird durch L2-Projektion auf die Moden abgezogen
    for name, r in problem.raender.items():
        rq = r.quadratur
        gv = (vorgaben or {}).get(name, 0.0)
        G = np.asarray(gv(rq.punkte) if callable(gv) else np.broadcast_to(np.asarray(gv, float), (len(rq.punkte), 3)), float)
        u, t = _randwerte(problem, U, D, rq)
        h_r = g.h_zelle(rq.zelle)
        n = rq.normalen
        d = u - G
        if r.projektion != "voll":
            d = n * (d * n).sum(axis=1, keepdims=True)
            tt = t - n * (t * n).sum(axis=1, keepdims=True)
            if r.projektion == "schnitt":
                M = r.moden                                                          # (q,3,3) [Punkt, Mode, Komponente]
                gram = np.einsum("q,qka,qla->kl", rq.gewichte, M, M)
                koeff = np.linalg.solve(gram, np.einsum("q,qka,qa->k", rq.gewichte, M, tt))
                tt = tt - np.einsum("k,qka->qa", koeff, M)
            np.add.at(eta2["neumann"], rq.zelle, (h_r / p) / E * rq.gewichte * (tt * tt).sum(axis=1))
        np.add.at(eta2["dirichlet"], rq.zelle, E * p ** 2 / h_r * rq.gewichte * (d * d).sum(axis=1))


def schaetzen(problem, U, vorgaben=None, volumenlast=None, tiefe: int = 2) -> Schaetzung:
    """Residuenbasierter Schaetzer je Zelle fuer die Loesung U (n_dof,). vorgaben wie FcmProblem.loesen (Randname -> g); volumenlast f(P) -> (q,3) in N/mm3
    zusaetzlich zu den mit FcmProblem.volumenlast gesetzten konstanten Lasten; tiefe: Unterteilung der Zellflaechen."""
    U = np.asarray(U, float).ravel()
    nz = len(problem.gitter.ijk)
    eta2 = {k: np.zeros(nz) for k in ANTEILE}
    E, nu = problem.werkstoff.E, problem.werkstoff.nu
    D = d_matrix(E, nu)
    lam, mu = lame(E, nu)
    b = np.sum(problem.volumenlasten, axis=0) if problem.volumenlasten else np.zeros(3)

    def f(P):
        aus = np.broadcast_to(b, (len(P), 3)).copy()
        return aus + (np.asarray(volumenlast(P), float).reshape(-1, 3) if volumenlast is not None else 0.0)
    _residuum(problem, U, f, lam, mu, eta2)
    _spruenge(problem, U, D, eta2, tiefe)
    _rand(problem, U, D, vorgaben, eta2)
    return Schaetzung(eta2)


def energiefehler(problem, U, sigma_ref) -> tuple[np.ndarray, float]:
    """(e^2 je Zelle (nz,), ||e||_E) mit ||e||_E^2 = int (sigma_h - sigma_ref) . D^-1 (sigma_h - sigma_ref) dV ueber die Werkstoffpunkte der Zellquadratur;
    sigma_ref: P (q,3) -> (q,6) Voigt. Mit U = 0 die Energienorm des Referenzfelds."""
    g, q = problem.gitter, problem.quadratur
    D = d_matrix(problem.werkstoff.E, problem.werkstoff.nu)
    C = np.linalg.inv(D)
    U = np.asarray(U, float).ravel()
    e2 = np.zeros(len(g.ijk))
    for c in range(len(g.ijk)):
        P, W, I = q.zelle(c)
        if len(P) == 0 or not I.any():
            continue
        Pm, Wm = P[I], W[I]
        s = _spannung(problem, D, c, g.lokal(Pm, np.full(len(Pm), c)), _koeff(problem, U, c)) - np.asarray(sigma_ref(Pm), float).reshape(-1, 6)
        e2[c] = float((Wm * np.einsum("qi,ij,qj->q", s, C, s)).sum())
    return e2, float(np.sqrt(e2.sum()))
