"""B6: exakte Integration tessellierter Huellen ueber den Divergenzsatz (geometry/huelle.py, Theorie 11.16).

Pruefung (1) des Plans TP 5: Stammfunktionen der 1D-Basis gegen Gauss (1e-14); Volumen und alle Tensor-Momente bis Grad 6
fuer Wuerfel, gedrehten Wuerfel, gedrehtes L-Prisma und Huelle gleich Zellbox gegen die exakte Zerlegung in Tetraeder (1e-12);
dazu die Boolesche Auswertung des CSG-Baums (Huelle als Loch, im Schnitt, in der Vereinigung) und die Zellquadratur.
Pruefung (4) in der Suitenfassung: der Windungszahl-Baum (geometry/windung.py, Barill 2018) an einer Kugelschale mit 25 088 Facetten
gegen die exakte Summe (gleiche Innen/Aussen-Entscheidung, |dw| < 1e-3, schneller); die Planmessung mit 107 636 Dreiecken und
100 000 Punkten steht in Theorie 11.16.

Aufruf: python -m volumen3d.tests.test_huelle   (~20 s)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

Q_MAX = 6                                                        # Momente bis Grad 6 (q = 2p fuer p 3)


def _wuerfel(lo, hi):
    """Zwoelf nach aussen gewickelte Dreiecke des Quaders [lo, hi]."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    V = np.array([[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]], [lo[0], hi[1], lo[2]],
                  [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
    seiten = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    D = []
    for s in seiten:
        a, b, c, d = V[list(s)]
        D += [[a, b, c], [a, c, d]]
    return np.asarray(D)


def _drehung(rz, rx):
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    return Rx @ Rz


def _momente_gauss_box(b_lo, b_hi, lo, hi, q):
    """Exakte Momente der Basis der Zelle [lo, hi] ueber den achsparallelen Quader [b_lo, b_hi] (Tensor-Gauss)."""
    from volumen3d.fcm.basis import gauss_3d, legendre_1d
    X, W = gauss_3d(q + 1)
    sb = 0.5 * (b_hi - b_lo)
    P = b_lo + sb * (X + 1)
    xi = (P - lo) / (0.5 * (hi - lo)) - 1
    Na, _ = legendre_1d(q, xi[:, 0])
    Nb, _ = legendre_1d(q, xi[:, 1])
    Nc, _ = legendre_1d(q, xi[:, 2])
    return np.einsum("p,pa,pb,pc->abc", W * np.prod(sb), Na, Nb, Nc)


def _momente_konvex(D_konvex, lo, hi, q):
    """Zweiter, unabhaengiger Weg: Zellbox an den Ebenen aller Facetten eines konvexen Koerpers clippen, Zerlegung in
    Tetraeder, konische Produktregel (polyeder.tet_regel, exakt bis Gesamtgrad 2n - 1; der Integrand hat Grad 3q)."""
    from volumen3d.fcm.basis import legendre_1d
    from volumen3d.geometry.polyeder import box_flaechen, clippen, polyeder_quadratur
    fl = box_flaechen(lo, hi)
    gesehen: list[tuple[np.ndarray, np.ndarray]] = []
    for a, b, c in D_konvex:
        n = np.cross(b - a, c - a)
        n /= np.linalg.norm(n)
        if any(abs(n @ m) > 1 - 1e-12 and abs((a - p) @ n) < 1e-12 for p, m in gesehen):
            continue
        gesehen.append((a, n))
        fl = clippen(fl, a, n, 1e-12)
        if not fl:
            return np.zeros((q + 1, q + 1, q + 1))
    n_tet = (3 * q + 2) // 2 + 1
    P, W = polyeder_quadratur(fl, n_tet)
    if len(P) == 0:
        return np.zeros((q + 1, q + 1, q + 1))
    xi = (P - lo) / (0.5 * (hi - lo)) - 1
    Na, _ = legendre_1d(q, xi[:, 0])
    Nb, _ = legendre_1d(q, xi[:, 1])
    Nc, _ = legendre_1d(q, xi[:, 2])
    return np.einsum("p,pa,pb,pc->abc", W, Na, Nb, Nc)


def test_stammfunktionen():
    """S_a(xi) = int_{-1}^{xi} N_a gegen Gauss-Legendre auf [-1, xi] (n = 12 Punkte, exakt fuer Grad <= 23)."""
    from volumen3d.fcm.basis import gauss_1d, legendre_1d
    from volumen3d.geometry.huelle import legendre_1d_stamm
    q = 10
    xis = np.linspace(-1.0, 1.0, 17)
    S = legendre_1d_stamm(q, xis)
    t, w = gauss_1d(12)
    soll = np.empty_like(S)
    for i, xi in enumerate(xis):
        h = 0.5 * (xi + 1.0)
        N, _ = legendre_1d(q, -1.0 + h * (t + 1.0))
        soll[i] = h * (w @ N)
    check("Stammfunktionen der 1D-Basis bis Grad 10 an 17 Stellen gegen Gauss auf 1e-14", np.abs(S - soll).max() < 1e-14,
          f"max {np.abs(S - soll).max():.1e}")
    voll = legendre_1d_stamm(q, np.array([1.0]))[0]
    # N_2 = (P_2 - P_0)/sqrt 6 integriert zu -2/sqrt 6 (P_0 ist nicht orthogonal zur Konstanten), N_j fuer j >= 3 zu 0
    check("volles Intervall: int N_0 = int N_1 = 1, int N_2 = -2/sqrt 6, Moden ab 3 integrieren zu 0 (Orthogonalitaet)",
          abs(voll[0] - 1) < 1e-15 and abs(voll[1] - 1) < 1e-15 and abs(voll[2] + 2 / np.sqrt(6.0)) < 1e-15
          and np.abs(voll[3:]).max() < 1e-15, str(np.round(voll, 15)))
    check("Startwert: S_a(-1) = 0", np.abs(legendre_1d_stamm(q, np.array([-1.0]))).max() < 1e-15)


def test_polyeder_momente():
    """Wuerfel, gedrehter Wuerfel, gedrehtes L-Prisma in Zellen verschiedener Lage: alle Momente bis Grad 6 auf 1e-12."""
    from volumen3d.geometry.huelle import huellenmomente, huellenvolumen
    q = Q_MAX
    lo, hi = np.array([1.0, 2.0, 3.0]), np.array([3.0, 4.0, 5.0])
    box_vol = float(np.prod(hi - lo))
    schlimmste = 0.0
    faelle = []
    # achsparalleler Wuerfel: Huelle gleich Zelle, Zelle ganz innen, Teilbox (Kante und Ecke in der Zelle), Huelle ganz in der Zelle,
    # Huelle beruehrt die Zelle bei x_hi von aussen (Volumen null), Huellenflaeche faellt mit einer Zellflaeche zusammen
    for name, b_lo, b_hi in (("Huelle gleich Zellbox", lo, hi),
                             ("Zelle ganz im Werkstoff", lo - 1, hi + 2),
                             ("Teilbox, Ecke in der Zelle", lo + [0.7, -0.3, 0.4], hi + [5.0, -0.6, 7.0]),
                             ("Huelle ganz in der Zelle", lo + 0.3, hi - 0.5),
                             ("beruehrt x_hi von aussen", [3.0, 2.5, 3.5], [4.0, 3.5, 4.5]),
                             ("Flaeche auf x = x_lo der Zelle", [1.0, 1.0, 1.0], [2.2, 10.0, 10.0])):
        b_lo, b_hi = np.asarray(b_lo, float), np.asarray(b_hi, float)
        D = _wuerfel(b_lo, b_hi)
        soll = _momente_gauss_box(np.maximum(b_lo, lo), np.minimum(b_hi, hi), lo, hi, q) if (np.minimum(b_hi, hi) > np.maximum(b_lo, lo)).all() else np.zeros((q + 1,) * 3)
        mu = huellenmomente(D, lo, hi, q)
        f = np.abs(mu - soll).max() / box_vol
        schlimmste = max(schlimmste, f)
        faelle.append(f"{name}: {f:.1e}")
    check("achsparalleler Wuerfel in sechs Lagen zur Zelle: Momente bis Grad 6 gegen Tensor-Gauss (relativ zum Zellvolumen) < 1e-12",
          schlimmste < 1e-12, "; ".join(faelle))
    # gedrehter Wuerfel: Referenz ueber Clippen der Zellbox an den Facettenebenen und Tetraeder-Zerlegung
    R = _drehung(0.52, 0.35)
    schlimmste = 0.0
    faelle = []
    for name, c_lo, c_hi, t in (("Ecke in der Zelle", [-1.3, -1.1, -0.9], [1.2, 1.4, 1.0], [2.0, 3.0, 4.0]),
                                ("Kante durch die Zelle", [-3.0, -0.6, -3.0], [3.0, 0.6, 3.0], [2.0, 4.1, 4.0]),
                                ("Zelle ganz innen", [-9.0, -9.0, -9.0], [9.0, 9.0, 9.0], [2.0, 3.0, 4.0]),
                                ("Wuerfel ganz in der Zelle", [-0.4, -0.4, -0.4], [0.4, 0.4, 0.4], [2.0, 3.0, 4.0])):
        D = _wuerfel(c_lo, c_hi) @ R.T + np.asarray(t)
        soll = _momente_konvex(D, lo, hi, q)
        mu = huellenmomente(D, lo, hi, q)
        f = np.abs(mu - soll).max() / box_vol
        schlimmste = max(schlimmste, f)
        faelle.append(f"{name}: {f:.1e}, V {huellenvolumen(D, lo, hi):.9f} / {soll[0:2, 0:2, 0:2].sum():.9f}")
    check("gedrehter Wuerfel in vier Lagen: Momente bis Grad 6 gegen Tetraeder-Zerlegung < 1e-12", schlimmste < 1e-12, "; ".join(faelle))
    # gedrehtes L-Prisma (nicht konvex, einspringende Kante): Referenz als Summe der beiden Teilquader (disjunkt)
    from volumen3d.tests.test_stl import _prisma
    L = _prisma([(0, 0), (4, 0), (4, 1), (2, 1), (2, 2), (0, 2)], 3.0)
    A = _wuerfel([0, 0, 0], [4, 1, 3])
    B = _wuerfel([0, 1, 0], [2, 2, 3])
    schlimmste = 0.0
    faelle = []
    for name, t, Rl in (("einspringende Kante in der Zelle", [0.3, 1.6, 1.5], R),
                        ("achsparallel, Kante in der Zelle", [0.0, 1.5, 2.0], np.eye(3)),
                        ("Zelle im langen Schenkel", [1.5, 0.9, 1.2], R)):
        DL = (L - 1.0) @ Rl.T + np.asarray(t)
        soll = _momente_konvex((A - 1.0) @ Rl.T + t, lo, hi, q) + _momente_konvex((B - 1.0) @ Rl.T + t, lo, hi, q)
        mu = huellenmomente(DL, lo, hi, q)
        f = np.abs(mu - soll).max() / box_vol
        schlimmste = max(schlimmste, f)
        faelle.append(f"{name}: {f:.1e}, V {huellenvolumen(DL, lo, hi):.9f}")
    check("L-Prisma (einspringende Kante) in drei Lagen: Momente bis Grad 6 gegen Summe der Teilquader < 1e-12", schlimmste < 1e-12,
          "; ".join(faelle))
    # Quaderzelle (Seitenverhaeltnis 1:2:3) mit gedrehtem Wuerfel
    lo2, hi2 = np.array([0.0, 0.0, 0.0]), np.array([1.0, 2.0, 3.0])
    D = _wuerfel([-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]) @ R.T + np.array([0.8, 1.2, 1.9])
    soll = _momente_konvex(D, lo2, hi2, q)
    mu = huellenmomente(D, lo2, hi2, q)
    f = np.abs(mu - soll).max() / 6.0
    check("Quaderzelle 1:2:3 mit gedrehtem Wuerfel: Momente < 1e-12", f < 1e-12, f"{f:.1e}")
    # Vorzeichen: eine nach innen gewickelte Huelle gibt die negativen Momente (Vertrauen in die Orientierung, keine Betraege)
    D_i = _wuerfel(lo + 0.5, hi + 2.0)[:, [0, 2, 1], :]
    check("nach innen gewickelte Huelle liefert das negative Volumen (kein Betrag)", abs(huellenvolumen(D_i, lo, hi) + 1.5 ** 3) < 1e-12,
          f"{huellenvolumen(D_i, lo, hi):.9f}")


def test_baum_und_zellquadratur():
    """Boolesche Auswertung des CSG-Baums ueber {leer, voll, Huelle, Komplement} und die Zellquadratur mit Huelle als Loch."""
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    D = _wuerfel([10.0, 10.0, 10.0], [20.0, 20.0, 20.0])
    loch = {"typ": "stl", "dreiecke": D.tolist(), "name": "loch"}
    quader = {"typ": "quader", "min": [0, 0, 0], "max": [30, 30, 30], "name": "block"}
    g_diff = aus_params({"csg": {"typ": "differenz", "teile": [quader, loch]}})
    g_schnitt = aus_params({"csg": {"typ": "schnitt", "teile": [quader, loch]}})
    g_ver = aus_params({"csg": {"typ": "vereinigung", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [30, 30, 12]}, loch]}})
    m_kante = np.array([10.0, 10.0, 15.0])                      # Kugel um eine Lochkante, tief im Block
    r = 2.0
    e1 = g_diff.huellenzelle(m_kante, r)
    e2 = g_schnitt.huellenzelle(m_kante, r)
    e3 = g_diff.huellenzelle(np.array([10.0, 10.0, 1.0]), r)      # Blockrand aktiv, Loch nicht: keine Huellenzelle
    e4 = g_diff.huellenzelle(np.array([10.0, 10.0, 28.0]), 3.0)   # Loch aktiv, Blockrand aktiv: beide -> None
    e5 = g_ver.huellenzelle(m_kante, r)                           # Platte bis z 12 enthaelt die Kugel um z 15 nicht: Huelle allein
    e6 = g_ver.huellenzelle(np.array([10.0, 10.0, 11.0]), r)      # Platte voll in der Kugel um z 11 -> voll, keine Huellenzelle
    check("Differenz Block minus Loch: Kugel an der Lochkante ist Komplement der Huelle (-1); Schnitt: Huelle (+1)",
          e1 is not None and e1[1] == -1 and e2 is not None and e2[1] == +1, f"{e1 and e1[1]}, {e2 and e2[1]}")
    check("keine Huellenzelle, wenn der Blockrand allein (None) oder zusaetzlich (None) aktiv ist", e3 is None and e4 is None)
    check("Vereinigung Platte + Huelle: ueber der Platte Huelle (+1); in der Platte voll (None, Zelle wird als innen behandelt)",
          e5 is not None and e5[1] == +1 and e6 is None, f"{e5 and e5[1]}, {e6}")
    G = Gitter(g_diff, h=10.0)
    Q = Zellquadratur(G, p=2, alpha=0.0)
    v = Q.volumen()
    check("Zellquadratur Block 30^3 minus Loch 10^3 (Lochflaechen auf Zellgrenzen): Volumen 26 000 exakt (< 1e-10)",
          abs(v / 26000.0 - 1) < 1e-10, f"{v:.6f}, {Q.statistik}")
    # Loch versetzt, tief in einem groesseren Block (80^3, h 10: die Blockflaechen sind in den inneren 6^3 Zellen nicht aktiv):
    # Lochkanten und -ecken liegen in Zellen; jede nur vom Loch geschnittene Zelle ist Komplementzelle ohne Blaetter -
    # der Block allein braucht genauso viele ebene Blaetter wie Block mit Loch
    gross = {"typ": "quader", "min": [0, 0, 0], "max": [80, 80, 80], "name": "block"}
    D2 = _wuerfel([32.0, 33.0, 34.0], [43.0, 42.0, 41.0])
    g2 = aus_params({"csg": {"typ": "differenz", "teile": [gross, {"typ": "stl", "dreiecke": D2.tolist()}]}})
    G2 = Gitter(g2, h=10.0)
    Q2 = Zellquadratur(G2, p=2, alpha=0.0)
    v2 = Q2.volumen()
    G0 = Gitter(aus_params({"csg": gross}), h=10.0)
    Q0 = Zellquadratur(G0, p=2, alpha=0.0)
    Q0.volumen()
    n_loch = int((G2.klasse == 2).sum()) - int((G0.klasse == 2).sum())
    check("versetztes Loch 11x9x7 im Block 80^3: Volumen 512 000 - 693 exakt, die vom Loch geschnittenen Zellen sind Huellenzellen, "
          "ebene Blaetter wie ohne Loch",
          abs(v2 / (512000.0 - 693.0) - 1) < 1e-10 and Q2.statistik["huellenzellen"] == n_loch > 0
          and Q2.statistik["blaetter_eben"] == Q0.statistik["blaetter_eben"] and Q2.statistik["blaetter_punkttest"] == 0,
          f"{v2:.6f}, {n_loch} Lochzellen, {Q2.statistik['huellenzellen']} Huellenzellen, Blaetter {Q2.statistik['blaetter_eben']} / {Q0.statistik['blaetter_eben']}")
    # Schnittebene durch die Huelle: Zellen mit Huelle und Ebene gehen den alten Weg, das Volumen bleibt exakt
    g3 = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "stl", "dreiecke": _wuerfel([1.0, 1.0, 1.0], [31.0, 31.0, 31.0]).tolist()},
                                                          {"typ": "halbraum", "punkt": [16.0, 0.0, 0.0], "normale": [1.0, 0.0, 0.0]}]}})
    G3 = Gitter(g3, h=10.0)
    Q3 = Zellquadratur(G3, p=2, alpha=0.0)
    v3 = Q3.volumen()
    check("Huelle ∩ Halbraum (Ebene x = 16 durch die Huelle): Volumen 15*30*30 exakt, Huellenzellen und ebene Blaetter nebeneinander",
          abs(v3 / 13500.0 - 1) < 1e-10 and Q3.statistik["huellenzellen"] > 0 and Q3.statistik["blaetter_eben"] > 0
          and Q3.statistik["blaetter_punkttest"] == 0, f"{v3:.6f}, {Q3.statistik}")


def _kugelschale(r, n_phi, n_theta, mitte=(0.0, 0.0, 0.0)):
    """Wasserdichte Laengen-Breiten-Tessellierung der Kugel (2 n_phi (n_theta - 1) Dreiecke, nach aussen gewickelt)."""
    th = np.linspace(0.0, np.pi, n_theta + 1)
    ph = np.linspace(0.0, 2 * np.pi, n_phi, endpoint=False)
    TH, PH = np.meshgrid(th[1:-1], ph, indexing="ij")
    ring = np.stack([np.sin(TH) * np.cos(PH), np.sin(TH) * np.sin(PH), np.cos(TH)], axis=2)      # (n_theta-1, n_phi, 3)
    nord, sued = np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, -1.0])
    D = []
    j1 = (np.arange(n_phi) + 1) % n_phi
    D.append(np.stack([np.broadcast_to(nord, (n_phi, 3)), ring[0], ring[0][j1]], axis=1))
    for i in range(n_theta - 2):
        a, b, c, d = ring[i], ring[i][j1], ring[i + 1], ring[i + 1][j1]
        D.append(np.stack([a, c, d], axis=1))
        D.append(np.stack([a, d, b], axis=1))
    D.append(np.stack([ring[-1], np.broadcast_to(sued, (n_phi, 3)), ring[-1][j1]], axis=1))
    return r * np.concatenate(D) + np.asarray(mitte)


def test_windungsbaum():
    """Windungszahl-Baum gegen die exakte Summe: Kugelschale r 50 mit 25 088 Facetten (ueber der Vorgabe 20 000), 20 000 Punkte
    (zwei Drittel im Huellquader mit Rand, ein Drittel bis 0,5 mm beidseits der Flaeche); dazu die Einbindung in Stl.innen."""
    from volumen3d.geometry.dreiecksbaum import _NUMBA
    if not _NUMBA:
        check("Windungsbaum uebersprungen: numba fehlt (ohne numba keine BVH, exakte Summe wie bisher)", True)
        return
    import time
    from volumen3d.geometry.dreiecksbaum import Dreiecksbaum
    from volumen3d.geometry.stl import Stl, windungszahl
    from volumen3d.geometry.windung import BETA_STANDARD, WINDUNG_BAUM_AB, Windungsbaum
    D = _kugelschale(50.0, 112, 113, mitte=(10.0, -20.0, 30.0))
    check("Kugelschale: 25 088 Facetten, eingeschlossenes Volumen auf 0,1 % bei 4/3 pi r^3",
          len(D) == 25088 and abs(np.einsum("ij,ij->i", D[:, 0], np.cross(D[:, 1], D[:, 2])).sum() / 6.0 / (4 / 3 * np.pi * 50.0 ** 3) - 1) < 1e-3)
    rng = np.random.default_rng(7)
    P1 = np.array([10.0, -20.0, 30.0]) - 60.0 + 120.0 * rng.random((13000, 3))
    idx = rng.integers(0, len(D), 7000)
    n = np.cross(D[idx, 1] - D[idx, 0], D[idx, 2] - D[idx, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    P2 = D[idx].mean(axis=1) + (rng.random(7000) - 0.5)[:, None] * n
    P = np.concatenate([P1, P2])
    baum = Dreiecksbaum(D)
    wb = Windungsbaum(baum)
    windungszahl(P[:300], D)
    wb.windungszahl(P[:300])                                   # numba-Uebersetzung nicht mitmessen
    t = time.perf_counter(); w_ex = windungszahl(P, D); t_ex = time.perf_counter() - t
    t = time.perf_counter(); w_b = wb.windungszahl(P); t_b = time.perf_counter() - t
    d = np.abs(w_b - w_ex)
    gleich = int(((w_b > 0.5) == (w_ex > 0.5)).sum())
    check(f"Baum (beta {BETA_STANDARD:g}) gegen exakt an 20 000 Punkten: innen/aussen gleich {gleich}/20000, |dw| max {d.max():.1e} (< 1e-3), "
          f"{t_ex / t_b:.0f}-mal schneller ({t_ex:.2f} s gegen {t_b:.3f} s; > 3)",
          gleich == 20000 and d.max() < 1e-3 and t_ex > 3 * t_b)
    # ohne Momente (nur Blaetter exakt, beta unendlich) muss der Baum die exakte Summe liefern: Blattrechnung und Baumdurchlauf stimmen
    wb_exakt = Windungsbaum(baum, beta=np.inf)
    check("beta unendlich: Baum = exakte Summe auf 1e-12 (Blattrechnung und Durchlauf)", np.abs(wb_exakt.windungszahl(P[:2000]) - w_ex[:2000]).max() < 1e-12)
    # Einbindung: Stl.innen baut den Baum ab WINDUNG_BAUM_AB Facetten, darunter nicht; die Entscheidung ist dieselbe
    s_gross = Stl.aus_dreiecken(D)
    innen_gross = s_gross.innen(P)
    s_klein = Stl.aus_dreiecken(_kugelschale(50.0, 40, 41, mitte=(10.0, -20.0, 30.0)))
    s_klein.innen(P[:10])
    check(f"Stl.innen: Baum ab {WINDUNG_BAUM_AB} Facetten gebaut (25 088: ja, 3 200: nein), Entscheidung wie exakt",
          s_gross._windung is not None and s_klein._windung is None and bool((innen_gross == (w_ex > 0.5)).all()))


def test_flaeche_hinter_schnittebene():
    """Befund aus B7 (Plan TP 5, 01.10.2026): Facetten einer Huelle, die kleiner sind als der Abstand zu einer Schnittebene, lagen
    in Zellen, in denen die Ebene fuer das Facettenpolygon nicht aktiv war - die Zerlegung ``ohne=form`` hielt sie fuer ganz
    innen und behielt sie, obwohl sie hinter der Ebene liegen (Oberflaechenpunkte und Flaechenlasten ausserhalb des Details;
    vorher fing das der Gesamtabstand ab, den B6 fuer Huellenfacetten entfernt hatte). Tessellierte Kugel r 50 (3 200 Facetten, mittlere
    Kante 8 mm) um den Ursprung, Halbraum x <= 20: Oberflaeche = Summe der an der Ebene geclippten Facetten + Kappenflaeche (konvexe
    Huelle der Schnittpunkte, unabhaengig davon mit scipy), keine Punkte mit x > 20."""
    from scipy.spatial import ConvexHull
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur, polygon_flaeche
    from volumen3d.geometry.polyeder import polygon_clippen
    D = _kugelschale(50.0, 40, 41)
    x_e = 20.0
    ex = np.array([1.0, 0.0, 0.0])
    # unabhaengige Referenz: Facetten an x = x_e geclippt (Werkstoffseite x <= x_e) und die Kappe als konvexe Huelle der Schnittpunkte
    flaeche, punkte = 0.0, []
    for t in D:
        Q, _ = polygon_clippen(t, np.array([x_e, 0.0, 0.0]), ex, 1e-12)               # Normale zeigt auf die entfernte Seite
        if len(Q) >= 3:
            flaeche += polygon_flaeche(Q)
            punkte += [q[1:] for q in Q if abs(q[0] - x_e) < 1e-9]
    kappe = ConvexHull(np.array(punkte)).volume                  # 2D-Huelle: "volume" ist die Flaeche
    soll = flaeche + kappe
    g = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "stl", "dreiecke": D.tolist(), "name": "kugel"},
                                                         {"typ": "halbraum", "punkt": [x_e, 0.0, 0.0], "normale": [1.0, 0.0, 0.0], "name": "ebene"}]}})
    G = Gitter(g, h=10.0)
    fq = Flaechenquadratur.aus_geometrie(g, G, ordnung=3)
    ist = float(fq.gewichte.sum())
    dahinter = int((fq.punkte[:, 0] > x_e + 1e-6).sum())
    check(f"Kugel-Huelle mit Halbraum x <= 20: Oberflaeche {ist:.4f} gegen unabhaengig {soll:.4f} (relativ {abs(ist / soll - 1):.1e} < 1e-9), "
          f"Punkte hinter der Ebene {dahinter} (0)", abs(ist / soll - 1) < 1e-9 and dahinter == 0, f"{fq.statistik}")


TESTS = [test_stammfunktionen, test_polyeder_momente, test_baum_und_zellquadratur, test_windungsbaum, test_flaeche_hinter_schnittebene]

if __name__ == "__main__":
    sys.exit(lauf(TESTS))
