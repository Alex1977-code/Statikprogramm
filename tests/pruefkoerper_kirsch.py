"""
Pruefkoerper Kirsch (freier Lochrand unter Zug) fuer die Randspannung (B6).

Halbring a <= r <= b, 0 <= theta <= pi, ebene Dehnung (u_z = 0 an beiden
Stirnen, n_z Lagen), Symmetrie an y = 0, aussen die exakte Kirsch-Spannung als
Randlast, das Loch frei. Die Kirsch-Loesung (Zug S in x) ist in der Ebene
exakt, sigma_zz = nu (sigma_xx + sigma_yy):

    sigma_rr = S/2 (1 - a2/r2) + S/2 (1 - 4 a2/r2 + 3 a4/r4) cos 2t
    sigma_tt = S/2 (1 + a2/r2) - S/2 (1 + 3 a4/r4) cos 2t
    sigma_rt = -S/2 (1 + 2 a2/r2 - 3 a4/r4) sin 2t

S ist so gewaehlt, dass sigma_v am Lochrand bei 90 Grad 355 N/mm2 ist. Der
Knoten dort liegt nicht auf der Symmetrieebene, und mit n_z >= 4 Lagen gibt
es Lochknoten, deren Randseiten keinen gelagerten Knoten beruehren.
"""
from __future__ import annotations

import numpy as np

from statik3d.elements import solid as sl
from tests import pruefkoerper as pk

A, B, H = 0.1, 0.4, 0.02


def kirsch(x, S, nu=pk.NU_ST):
    r = np.hypot(x[0], x[1])
    th = np.arctan2(x[1], x[0])
    q2, q4 = (A / r) ** 2, (A / r) ** 4
    c2, s2 = np.cos(2 * th), np.sin(2 * th)
    srr = S / 2 * (1 - q2) + S / 2 * (1 - 4 * q2 + 3 * q4) * c2
    stt = S / 2 * (1 + q2) - S / 2 * (1 + 3 * q4) * c2
    srt = -S / 2 * (1 + 2 * q2 - 3 * q4) * s2
    c, s = np.cos(th), np.sin(th)
    sxx = srr * c * c + stt * s * s - 2 * srt * s * c
    syy = srr * s * s + stt * c * c + 2 * srt * s * c
    sxy = (srr - stt) * s * c + srt * (c * c - s * s)
    return np.array([sxx, syy, nu * (sxx + syy), sxy, 0.0, 0.0])


S_BEZUG = 355e6 / sl.von_mises(kirsch(np.array([0.0, A, 0.0]), 1.0))


def modell(typ, n_t, n_r, n_z=4, q=1.5):
    """n_t Teile ueber 180 Grad, n_r radial (gestuft (i/n)^q zum Loch hin)."""
    def form(i, j, k, p):
        r = A + (B - A) * (i / n_r) ** q
        t = np.pi * j / n_t
        return np.array([r * np.cos(t), r * np.sin(t), H * k / n_z])
    m, _ids = pk.quader(typ, n_r, n_t, n_z, 1.0, 1.0, H, form=form)
    if typ == "tet10":
        # Kantenmitten auf den Kreisbogen
        for e in m.elements:
            for (p_, q_), mm in zip(pk.TET10_KANTEN, e.nodes[4:]):
                P, Q = m.nodes[e.nodes[p_]], m.nodes[e.nodes[q_]]
                rp, rq = np.hypot(P[0], P[1]), np.hypot(Q[0], Q[1])
                if abs(rp - rq) < 1e-12 * B:
                    M = 0.5 * (P + Q)
                    f = rp / np.hypot(M[0], M[1])
                    m.nodes[mm] = np.array([M[0] * f, M[1] * f, M[2]])
    X = np.asarray(m.nodes, float)
    tol = 1e-9 * B
    fest_x = None
    for n in range(m.nn):
        dofs = []
        if abs(X[n, 1]) < tol:
            dofs.append(1)
        if abs(X[n, 2]) < tol or abs(X[n, 2] - H) < tol:
            dofs.append(2)
        if dofs:
            m.fix(int(n), dofs)
        if fest_x is None and abs(np.hypot(X[n, 0], X[n, 1]) - B) < tol and abs(X[n, 1]) < tol \
                and abs(X[n, 2]) < tol:
            fest_x = n
    m.fix(int(fest_x), [0, 1, 2])
    aussen = pk.randseiten(m, lambda P: bool(np.all(np.abs(np.hypot(P[:, 0], P[:, 1]) - B) < 1e-9 * B)))

    def t(x):
        s = kirsch(x, S_BEZUG)
        T = np.array([[s[0], s[3], 0], [s[3], s[1], 0], [0, 0, s[2]]])
        return T @ (np.array([x[0], x[1], 0.0]) / np.hypot(x[0], x[1]))
    pk.spannung_auf_seiten(m, aussen, t)
    return m


def lochknoten(m):
    """Eckknoten am Lochrand, deren z nicht auf einer Stirn liegt."""
    X = np.asarray(m.nodes, float)
    ecken = {int(k) for e in m.elements for k in e.nodes[:len(sl.ECKEN_NATUERLICH[e.typ])]}
    return [n for n in range(m.nn) if abs(np.hypot(X[n, 0], X[n, 1]) - A) < 1e-9 * B
            and n in ecken and 1e-9 < X[n, 2] < H - 1e-9]


def abweichung(m, res):
    """(groesste |Abweichung| am Lochrand, Abweichung bei 90 Grad in halber
    Dicke) von sigma_v in N/mm2, aus res.solid_knoten."""
    sk = res.solid_knoten
    pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
    S = np.asarray(sk["spannung"])
    X = np.asarray(m.nodes, float)
    werte, spitze = [], None
    for n in lochknoten(m):
        d = (sl.von_mises(S[pos[n]]) - sl.von_mises(kirsch(X[n], S_BEZUG))) / 1e6
        werte.append(d)
        if abs(X[n, 0]) < 1e-9 and abs(X[n, 2] - H / 2) < 1e-9:
            spitze = d
    return float(np.max(np.abs(werte))), spitze
