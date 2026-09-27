"""Zellsteifigkeit auf zwei unabhaengigen Wegen (Gradientenmomente gegen explizites B^T D B),
Symmetrie, Starrkoerperkern der assemblierten Matrix.

Aufruf: python -m tests.volumen3d.test_elastizitaet
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from tests.volumen3d._pruef import check, lauf  # noqa: E402


def _B(dN):
    """dN (m,3) global -> B (6,3m), Voigt xx,yy,zz,xy,yz,xz mit technischen Gleitungen."""
    m = len(dN)
    B = np.zeros((6, 3 * m))
    B[0, 0::3] = dN[:, 0]
    B[1, 1::3] = dN[:, 1]
    B[2, 2::3] = dN[:, 2]
    B[3, 0::3] = dN[:, 1]
    B[3, 1::3] = dN[:, 0]
    B[4, 1::3] = dN[:, 2]
    B[4, 2::3] = dN[:, 1]
    B[5, 0::3] = dN[:, 2]
    B[5, 2::3] = dN[:, 0]
    return B


def test_zellsteifigkeit():
    from volumen3d.fcm.basis import basis_3d, gauss_3d
    from volumen3d.fcm.elastizitaet import d_matrix, zellsteifigkeit
    E, nu, h, p = 210000.0, 0.3, 7.0, 3
    D = d_matrix(E, nu)
    check("D symmetrisch, D[0,0] = E(1-nu)/((1+nu)(1-2nu)), D[3,3] = G",
          np.allclose(D, D.T) and abs(D[0, 0] - E * (1 - nu) / ((1 + nu) * (1 - 2 * nu))) < 1e-6 and abs(D[3, 3] - E / (2 * (1 + nu))) < 1e-9)
    X, W = gauss_3d(p + 1)
    _, dN = basis_3d(p, X)
    G = dN * (2.0 / h)
    w = W * (h / 2) ** 3
    K1 = zellsteifigkeit(G, w, E, nu)
    K2 = sum(w[q] * _B(G[q]).T @ D @ _B(G[q]) for q in range(len(w)))
    check("Gradientenmomente = explizites B^T D B", np.allclose(K1, K2, rtol=1e-12, atol=1e-9 * abs(K2).max()), f"max Abw. {abs(K1 - K2).max():.1e}")
    ew = np.linalg.eigvalsh(K1)
    check("symmetrisch, positiv semidefinit mit genau 6 Nullmoden (Starrkoerper)",
          np.allclose(K1, K1.T) and ew.min() > -1e-9 * ew.max() and int((ew < 1e-9 * ew.max()).sum()) == 6, f"kleinste 7: {ew[:7] / ew.max()}")


def test_starrkoerper():
    from volumen3d.fcm.basis import modenklassen
    from volumen3d.fcm.elastizitaet import assemblieren
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 25.0}})
    G = Gitter(g, h=10.0)
    G.moden_nummerieren(2)
    K = assemblieren(G, Zellquadratur(G, 2, tiefe=2), 210000.0, 0.3)
    check("K quadratisch (n_dof) und symmetrisch", K.shape == (G.n_dof, G.n_dof) and abs(K - K.T).max() < 1e-8 * abs(K).max(), f"n_dof {G.n_dof}, nnz {K.nnz}")
    # Starrkoerperbewegungen als Modenkoeffizienten: Ecken tragen die Werte, hoehere Moden 0
    kl = modenklassen(2)
    U = np.zeros((G.n_dof, 6))
    for c in range(len(G.ijk)):
        lo, hi = G.zellbox(c)
        for m in np.flatnonzero(kl["klasse"] == 0):
            x = np.where(kl["abc"][m] == 0, lo, hi)
            mode = G.zell_moden[c, m]
            for d in range(3):
                U[3 * mode + d, d] = 1.0
            U[3 * mode + 1, 3] = -x[2]; U[3 * mode + 2, 3] = x[1]        # Drehung um x
            U[3 * mode + 0, 4] = x[2];  U[3 * mode + 2, 4] = -x[0]       # um y
            U[3 * mode + 0, 5] = -x[1]; U[3 * mode + 1, 5] = x[0]        # um z
    r = np.abs(K @ U).max() / (abs(K).max() * np.abs(U).max())
    check("sechs Starrkoerpermoden im Kern von K", r < 1e-10, f"{r:.1e}")
    # und eine lineare Dehnung ist kein Nullmode
    Ue = np.zeros(G.n_dof)
    for c in range(len(G.ijk)):
        lo, hi = G.zellbox(c)
        for m in np.flatnonzero(kl["klasse"] == 0):
            x = np.where(kl["abc"][m] == 0, lo, hi)
            Ue[3 * G.zell_moden[c, m]] = 1e-3 * x[0]
    check("Dehnung eps_xx = 1e-3 hat positive Energie", Ue @ (K @ Ue) > 0)


if __name__ == "__main__":
    sys.exit(lauf([test_zellsteifigkeit, test_starrkoerper]))
