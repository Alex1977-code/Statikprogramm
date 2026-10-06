"""Residuenbasierter Fehlerschaetzer je Zelle (Teilprojekt 6a, Phase 1; Vorgabe 8.4; Plan 2026-10-06-tp6a-phase1-schaetzer.md).

eta_K^2 = (1/E) [ (h/p)^2 ||f + div sigma_h||^2_{K cap Omega} + 1/2 sum_F (h_F/p) ||[sigma_h n]||^2_{F cap Omega} + (h/p) ||t - sigma_h n||^2_{Gamma_N cap K} ]
          + E (p^2/h) ||P (u_h - g)||^2_{Gamma_D cap K}

Einheit N mm (Energie). Die Flaechen zwischen Zellen werden mit Tensor-Gauss je Unterquadrat (2^tiefe x 2^tiefe) und Punkttest integriert (erste Ordnung in der
Geometrie, Entwurf 6a Abschnitt 3). Freie Oberflaeche sind alle Oberflaechenpunkte ausser denen eines Verschiebungsrands (Zuordnung ueber die Koordinaten:
die Raender sind Auswahlen der Oberflaechenquadratur); ihre Soll-Traktion kommt aus den aufgezeichneten Flaechenlasten, sonst null.
"""
from __future__ import annotations

import numpy as np

from .basis import gauss_1d


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
