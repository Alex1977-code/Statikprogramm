"""
Element-Bausteine gegen geschlossene Loesungen:
Stabexzentrizitaet, Woelbkrafttorsion (7. FHG), Feder, Seil (elastische
Kettenlinie), starre Koerper RBE2/RBE3 und Grenzschichtelemente.

Die Verbaende werden hier im Test selbst mit dichten numpy-Matrizen
assembliert.  Aufruf:  python3 tests/test_elemente_stab.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.elements import beam3d as bm          # noqa: E402
from statik3d.elements import verbindung as vb      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def close(name, got, want, rtol, unit=""):
    """Relative Abweichung (absolut, wenn want = 0)."""
    got = float(got)
    want = float(want)
    err = abs(got - want) / abs(want) if want else abs(got)
    return check(name, err <= rtol,
                 f"num={got: .6e}{unit} ana={want: .6e}{unit} Abw={err * 100:.4f} %")


def null_moden(K, n_soll, name):
    """Zahl der (relativ) verschwindenden Eigenwerte einer symm. Matrix."""
    ev = np.linalg.eigvalsh(0.5 * (K + K.T))
    ref = abs(ev).max()
    n0 = int(np.sum(abs(ev) < 1e-9 * ref))
    return check(name, n0 == n_soll, f"{n0} Nullmoden (erwartet {n_soll})")


# ==========================================================================
# A1  Stabexzentrizitaet
# ==========================================================================
def t_versatz():
    print("\n-- Stabexzentrizitaet ------------------------------------------")
    E, G = 210e9, 80.77e9
    A, Iy, Iz, It, L = 1e-2, 1e-5, 2e-5, 1.5e-5, 3.0
    e = 0.1                                       # Versatz in lokaler z-Richtung
    N = 1000.0
    Ks = bm.k_local_beam(E, G, A, Iy, Iz, It, L)
    Am = bm.versatz_matrix([0.0, 0.0, e], [0.0, 0.0, e])
    Kk = Am.T @ Ks @ Am

    # reiner Normalkraftzustand: die Stabendkraefte erzeugen am Knoten N*e
    fs = np.zeros(12)
    fs[0], fs[6] = -N, N
    fk = Am.T @ fs
    close("Versatz: Knotenmoment My aus N (Knoten 2)", fk[10], N * e, 1e-12)
    close("Versatz: Knotenmoment My aus N (Knoten 1)", fk[4], -N * e, 1e-12)
    check("Versatz: uebrige Knotenkraefte unveraendert",
          np.allclose(np.delete(fk, [4, 10]), np.delete(fs, [4, 10])))

    # Starrkoerpertransformation: 6 Nullmoden bleiben erhalten, A invertierbar
    null_moden(Ks, 6, "Versatz: Stabmatrix hat 6 Nullmoden")
    null_moden(Kk, 6, "Versatz: A^T K A behaelt 6 Nullmoden")
    check("Versatz: A invertierbar (det = 1)", abs(np.linalg.det(Am) - 1) < 1e-12)
    check("Versatz: A^T K A symmetrisch", np.allclose(Kk, Kk.T))

    # Kragarm: Knoten 1 fest, Kraft N am Knoten 2 (auf der Knotenlinie).
    # Der versetzte Stab erhaelt N und das konstante Moment N*e; die
    # Einspannung liefert nur -N (kein Moment, Last liegt auf der Knotenlinie).
    F = np.zeros(12)
    F[6] = N
    frei = np.arange(6, 12)
    u = np.zeros(12)
    u[frei] = np.linalg.solve(Kk[np.ix_(frei, frei)], F[frei])
    fst = Ks @ (Am @ u)                            # Stabendkraefte
    react = (Am.T @ fst)[:6]                       # Auflagerreaktion am Knoten 1
    close("Versatz: Stabendmoment |My| = N*e", abs(fst[10]), N * e, 1e-9)
    close("Versatz: Stabnormalkraft", fst[6], N, 1e-9)
    close("Versatz: Reaktion Fx = -N", react[0], -N, 1e-9)
    check("Versatz: Reaktionsmoment am Knoten = 0",
          abs(react[4]) < 1e-9 * N * e, f"My={react[4]:.3e}")
    # Handrechnung: die Last auf der Knotenlinie erzeugt am versetzten Stab
    # (Achse bei +e) das Moment My = -N e, konstant: ry2 = My L/(E Iy);
    # der Knoten 2 verschiebt sich um N L/(EA) - ry2 e (u_knoten = u_ende - theta x r)
    close("Versatz: Verdrehung ry2 = -N e L/(E Iy)", u[10], -N * e * L / (E * Iy), 1e-9)
    close("Versatz: Verschiebung u2x = N L/(EA) - ry2 e",
          u[6], N * L / (E * A) + (N * e * L / (E * Iy)) * e, 1e-9)


# ==========================================================================
# A2-4  Woelbkrafttorsion
# ==========================================================================
def _torsion_system(E, G, A, Iy, Iz, It, Iw, L, ne, T, woelbeinspannung=False,
                    woelbtrennung=False):
    """Gabelgelagerter Traeger, Torsionsmoment T in Feldmitte, ne Elemente
    mit 14 FHG (7 je Knoten: ux uy uz rx ry rz omega). Rueckgabe (u, h, K_e).
    woelbtrennung: omega am Lastknoten fuer beide Seiten getrennt (Knick in
    theta zulaessig, noetig fuer die reine St.-Venant-Torsion Iw = 0)."""
    nn = ne + 1
    h = L / ne
    ndof = 7 * nn + (1 if woelbtrennung else 0)
    K = np.zeros((ndof, ndof))
    Ke = bm.k_local_beam14(E, G, A, Iy, Iz, It, Iw, h)
    # Element-FHG: Knoten a: 7a..7a+5, omega 7a+6; Knoten b analog
    for el in range(ne):
        a, b = el, el + 1
        d = [7 * a + i for i in range(6)] + [7 * b + i for i in range(6)] + [7 * a + 6, 7 * b + 6]
        if woelbtrennung and a == ne // 2:
            d[12] = 7 * nn                        # eigenes omega rechts vom Lastknoten
        K[np.ix_(d, d)] += Ke
    fest = [0, 1, 2, 3, 7 * ne + 1, 7 * ne + 2, 7 * ne + 3]
    if woelbeinspannung:
        fest += [6, 7 * ne + 6]
    F = np.zeros(ndof)
    F[7 * (ne // 2) + 3] = T
    frei = np.setdiff1d(np.arange(ndof), fest)
    u = np.zeros(ndof)
    u[frei] = np.linalg.solve(K[np.ix_(frei, frei)], F[frei])
    return u, h, Ke


def _element_u14(u, el):
    a, b = el, el + 1
    d = [7 * a + i for i in range(6)] + [7 * b + i for i in range(6)] + [7 * a + 6, 7 * b + 6]
    return u[d]


def t_woelbkrafttorsion():
    print("\n-- Woelbkrafttorsion -------------------------------------------")
    E, G = 210e9, 80.77e9
    It, Iw, L = 2.01e-7, 1.26e-7, 6.0
    A, Iy, Iz = 5.38e-3, 8.36e-5, 6.04e-6
    T = 10e3
    ne = 40                                       # 20 je Haelfte
    lam = math.sqrt(G * It / (E * Iw))
    a = lam * L / 2

    # Matrizen: Struktur und Symmetrie
    Kt4 = bm.k_local_torsion_woelb(E, G, It, Iw, 0.3)
    K14 = bm.k_local_beam14(E, G, A, Iy, Iz, It, Iw, 0.3)
    K12 = bm.k_local_beam(E, G, A, Iy, Iz, It, 0.3)
    ix = np.ix_(bm.IDX_TORSION14, bm.IDX_TORSION14)
    check("Torsion: 4x4 symmetrisch, positiv semidefinit",
          np.allclose(Kt4, Kt4.T) and np.linalg.eigvalsh(Kt4).min() > -1e-9 * abs(Kt4).max())
    null_moden(Kt4, 1, "Torsion: 4x4 hat genau 1 Nullmode (Starrdrehung)")
    check("Torsion: 14x14 enthaelt 4x4 auf [3,12,9,13]", np.allclose(K14[ix], Kt4))
    K12z = K12.copy()
    K12z[np.ix_([3, 9], [3, 9])] = 0
    K14z = K14[:12, :12].copy()
    K14z[np.ix_([3, 9], [3, 9])] = 0
    check("Torsion: 14x14 sonst wie k_local_beam", np.allclose(K12z, K14z))
    null_moden(K14, 6, "Torsion: 14x14 hat 6 Nullmoden")

    # geschlossene Loesung der gemischten Torsion (Gabellager, T in Feldmitte):
    #   theta' = T/(2 G It) (1 - cosh(lam x)/cosh(a)),  a = lam L/2
    #   theta(L/2) = T/(2 G It lam) (a - tanh a),  B = -E Iw theta'' -> B(L/2) = T/(2 lam) tanh a
    u, h, Ke = _torsion_system(E, G, A, Iy, Iz, It, Iw, L, ne, T)
    th_ana = T / (2 * G * It * lam) * (a - math.tanh(a))
    B_ana = T / (2 * lam) * math.tanh(a)
    th_fe = u[7 * (ne // 2) + 3]
    close("Woelbtorsion: theta(L/2) gegen geschlossene Loesung", th_fe, th_ana, 5e-3)
    el = ne // 2 - 1
    v = bm.torsion_verlauf(E, G, It, Iw, h, _element_u14(u, el), h)
    close("Woelbtorsion: B(L/2) gegen geschlossene Loesung", v["B"], B_ana, 5e-3)
    # theta(x) an einem Zwischenpunkt
    x0 = 1.3
    th_x = T / (2 * G * It) * (x0 - math.sinh(lam * x0) / (lam * math.cosh(a)))
    el0 = int(x0 // h)
    v0 = bm.torsion_verlauf(E, G, It, Iw, h, _element_u14(u, el0), x0 - el0 * h)
    close("Woelbtorsion: theta(1.3 m) gegen geschlossene Loesung", v0["theta"], th_x, 5e-3)
    close("Woelbtorsion: B(0) = 0 (Gabellager)", abs(bm.torsion_verlauf(
        E, G, It, Iw, h, _element_u14(u, 0), 0.0)["B"]) / B_ana, 0.0, 1e-3)

    # Gleichgewicht: Elementendkraefte K u tragen ueberall T/2
    ok = True
    worst = 0.0
    for el_ in range(ne // 2):
        fe = Ke @ _element_u14(u, el_)
        worst = max(worst, abs(fe[9] - T / 2), abs(fe[3] + T / 2))
    close("Woelbtorsion: Mt aus Elementendkraeften = T/2 (max. Abw.)",
          worst / (T / 2), 0.0, 1e-6)
    # Mt_p + Mt_s aus der Hermite-Interpolation: theta''' ist je Element
    # konstant, der Verlauf also nur in der Elementmitte O(h^2) genau, an den
    # Elementenden O(h). Beides wird mit zwei Netzen (h, h/2) belegt.
    def mt_abweichung(u_, h_, ne_):
        ok_ = True
        w_mitte = w_ende = 0.0
        for el_ in range(ne_ // 2):
            vv = bm.torsion_verlauf(E, G, It, Iw, h_, _element_u14(u_, el_),
                                    np.array([0.0, h_ / 2, h_]))
            ok_ &= np.allclose(vv["Mt"], vv["Mt_p"] + vv["Mt_s"], rtol=1e-12, atol=1e-9)
            w_mitte = max(w_mitte, abs(vv["Mt"][1] - T / 2))
            w_ende = max(w_ende, abs(vv["Mt"][[0, 2]] - T / 2).max())
        return ok_, w_mitte / (T / 2), w_ende / (T / 2)

    ok, w_mitte, w_ende = mt_abweichung(u, h, ne)
    check("Woelbtorsion: torsion_verlauf Mt = Mt_p + Mt_s", ok)
    close("Woelbtorsion: Mt_p + Mt_s = T/2 in Elementmitten (max. Abw.)", w_mitte, 0.0, 1e-3)
    u2, h2, _K = _torsion_system(E, G, A, Iy, Iz, It, Iw, L, 2 * ne, T)
    _ok, w_mitte2, w_ende2 = mt_abweichung(u2, h2, 2 * ne)
    check("Woelbtorsion: Mt-Abweichung Elementmitte O(h^2), Elementende O(h)",
          0.2 <= w_mitte2 / w_mitte <= 0.3 and 0.45 <= w_ende2 / w_ende <= 0.55,
          f"Mitte {w_mitte:.2e} -> {w_mitte2:.2e}, Ende {w_ende:.2e} -> {w_ende2:.2e}")
    # Feldmitte: Mt_p = G It theta' = 0 (Symmetrie), alles laeuft ueber Mt_s
    check("Woelbtorsion: Mt_p(L/2) = 0 (Symmetrie)", abs(v["Mt_p"]) < 1e-9 * T,
          f"Mt_p={v['Mt_p']:.3e}")

    # Grenzfall Iw -> 0: St. Venant, theta = T L/(4 G It). Ohne Woelbsteifigkeit
    # ist theta' am Lastknoten unstetig, omega wird dort getrennt.
    u0, _h, _K = _torsion_system(E, G, A, Iy, Iz, It, 0.0, L, ne, T, woelbtrennung=True)
    close("St. Venant (Iw = 0, omega getrennt): theta(L/2) = T L/(4 G It)",
          u0[7 * (ne // 2) + 3], T * L / (4 * G * It), 1e-9)
    # kleines Iw (1 %): geschlossene Loesung geht gegen St. Venant (Abzug 1/a)
    Iw_k = 1e-2 * Iw
    lam_k = math.sqrt(G * It / (E * Iw_k))
    a_k = lam_k * L / 2
    uk, _h, _K = _torsion_system(E, G, A, Iy, Iz, It, Iw_k, L, ne, T)
    close("Iw klein (1 %): theta(L/2) gegen geschlossene Loesung",
          uk[7 * (ne // 2) + 3], T / (2 * G * It * lam_k) * (a_k - math.tanh(a_k)), 1e-3)
    close("Iw klein (1 %): theta(L/2) nahe St. Venant (Abzug 1/a)",
          uk[7 * (ne // 2) + 3], T * L / (4 * G * It) * (1 - 1 / a_k), 1e-3)
    # Woelbeinspannung beidseits: theta(L/2) = T/(2 G It lam) (a - 2 tanh(a/2)) < frei
    ue, _h, _K = _torsion_system(E, G, A, Iy, Iz, It, Iw, L, ne, T, woelbeinspannung=True)
    th_e = ue[7 * (ne // 2) + 3]
    th_e_ana = T / (2 * G * It * lam) * (a - 2 * math.tanh(a / 2))
    check("Woelbeinspannung verringert theta", th_e < th_fe,
          f"{th_e:.6e} < {th_fe:.6e}")
    close("Woelbeinspannung: theta(L/2) gegen geschlossene Loesung", th_e, th_e_ana, 5e-3)

    # Massenmatrix: Starrdrehung -> rho Ip L; lineare Verdrillung -> rho Ip L/3 + rho Iw/L
    rho, Ip = 7850.0, Iy + Iz
    Lm = 2.0
    M = bm.m_local_beam14(rho, A, Lm, Ip, Iw)
    check("Masse 14x14 symmetrisch, positiv semidefinit",
          np.allclose(M, M.T) and np.linalg.eigvalsh(M).min() > -1e-12 * abs(M).max())
    M0 = bm.m_local_beam14(rho, A, Lm, Ip, 0.0)
    check("Masse 14x14 ohne Iw = m_local_beam",
          np.allclose(M0[:12, :12], bm.m_local_beam(rho, A, Lm, Ip)) and not M0[12:].any())
    ixm = np.ix_(bm.IDX_TORSION14, bm.IDX_TORSION14)
    Mw = np.zeros((14, 14))
    Mw[ixm] = rho * Iw / (30 * Lm) * np.array([[36, 3 * Lm, -36, 3 * Lm], [3 * Lm, 4 * Lm ** 2, -3 * Lm, -Lm ** 2],
                                                 [-36, -3 * Lm, 36, -3 * Lm], [3 * Lm, -Lm ** 2, -3 * Lm, 4 * Lm ** 2]])
    check("Masse 14x14: Woelbtraegheit rho Iw int N'^T N' auf [3,12,9,13]", np.allclose(M - M0, Mw))
    d = np.zeros(14)
    d[3] = d[9] = 1.0
    close("Masse: Starrdrehung -> rho Ip L", d @ M @ d, rho * Ip * Lm, 1e-12)
    d = np.zeros(14)
    d[9] = 1.0
    d[12] = d[13] = 1.0 / Lm
    close("Masse: lineare Verdrillung -> rho Ip L/3 + rho Iw/L",
          d @ M @ d, rho * Ip * Lm / 3 + rho * Iw / Lm, 1e-12)


# ==========================================================================
# B5  Feder
# ==========================================================================
def t_feder():
    print("\n-- Feder ---------------------------------------------------------")
    k6 = np.array([1e3, 2e3, 3e3, 4e2, 5e2, 6e2])
    P1 = np.array([0.0, 0.0, 0.0])
    P2 = np.array([1.0, 0.0, 0.0])
    T3 = vb.feder_achsen(P1, P2)
    check("Feder: Achsen entlang x = Einheitsmatrix", np.allclose(T3, np.eye(3)))
    K = vb.k_feder(k6, T3)
    du = np.array([0.01, -0.02, 0.03, 0.004, -0.005, 0.006])
    u = np.concatenate([np.zeros(6), du])
    f = K @ u
    check("Feder: Kraefte am Knoten 2 = k*Delta", np.allclose(f[6:], k6 * du))
    check("Feder: Kraefte am Knoten 1 = -k*Delta", np.allclose(f[:6], -k6 * du))
    check("Feder: feder_kraefte = k*Delta (Zug positiv)",
          np.allclose(vb.feder_kraefte(k6, T3, u), k6 * du))
    # Zug: Knoten 2 entfernt sich -> positive Federkraft
    uz = np.zeros(12)
    uz[6] = 0.01
    close("Feder: Zugkraft bei Dehnung positiv", vb.feder_kraefte(k6, T3, uz)[0], 10.0, 1e-12)
    # gemeinsame Bewegung beider Knoten: kraftlos
    null_moden(K, 6, "Feder: 6 Nullmoden (gemeinsame Bewegung)")
    ug = np.concatenate([du, du])
    check("Feder: gemeinsame Verschiebung/Verdrehung gibt 0",
          np.allclose(K @ ug, 0, atol=1e-12 * abs(K).max()))

    # gedrehte Achse
    P2b = np.array([1.0, 2.0, 2.0])
    T3b = vb.feder_achsen(P1, P2b, roll=0.3)
    ex = (P2b - P1) / np.linalg.norm(P2b - P1)
    check("Feder: gedrehte Achse orthonormal, ex = Sehne",
          np.allclose(T3b @ T3b.T, np.eye(3)) and np.allclose(T3b[0], ex)
          and abs(np.linalg.det(T3b) - 1) < 1e-12)
    Kb = vb.k_feder(k6, T3b)
    check("Feder: gedreht symmetrisch, 6 Nullmoden",
          np.allclose(Kb, Kb.T) and np.linalg.eigvalsh(Kb).min() > -1e-9 * abs(Kb).max()
          and int(np.sum(abs(np.linalg.eigvalsh(Kb)) < 1e-9 * abs(Kb).max())) == 6)
    # Dehnung entlang ex -> Kraft kx*Delta entlang ex (global)
    ub = np.zeros(12)
    ub[6:9] = 0.01 * ex
    fb = Kb @ ub
    check("Feder: Dehnung entlang gedrehter Achse -> kx*Delta*ex",
          np.allclose(fb[6:9], k6[0] * 0.01 * ex) and np.allclose(fb[:6], -fb[6:]))
    close("Feder: feder_kraefte gedreht, Zug", vb.feder_kraefte(k6, T3b, ub)[0], 10.0, 1e-12)
    # Rueckrechnung: K_global = T^T K_lokal T
    Tm = bm.transform_matrix(T3b)
    check("Feder: T K_global T^T = K_lokal",
          np.allclose(Tm @ Kb @ Tm.T, vb.k_feder(k6, np.eye(3))))
    # isotrope Feder haengt nicht von der Achsenwahl ab
    kiso = np.array([5.0, 5.0, 5.0, 2.0, 2.0, 2.0])
    check("Feder: isotrope Steifigkeit unabhaengig von der Achse",
          np.allclose(vb.k_feder(kiso, T3b), vb.k_feder(kiso, np.eye(3))))
    # zusammenfallende Knoten: Achse aus Vorgabe, Starrdrehung kraftlos
    T3c = vb.feder_achsen(P1, P1, achse=[0, 0, 1])
    check("Feder: zusammenfallende Knoten, ex = Vorgabe", np.allclose(T3c[0], [0, 0, 1]))
    Kc = vb.k_feder(k6, T3c)
    th = np.array([0.1, -0.2, 0.3])
    ur = np.concatenate([np.zeros(3), th, np.zeros(3), th])
    check("Feder: Starrdrehung bei zusammenfallenden Knoten kraftlos",
          np.allclose(Kc @ ur, 0, atol=1e-12 * abs(Kc).max()))


# ==========================================================================
# B6  Seil
# ==========================================================================
def _sehnenabstand(pts, P1, P2):
    e = (P2 - P1) / np.linalg.norm(P2 - P1)
    d = pts - P1
    return np.linalg.norm(d - np.outer(d @ e, e), axis=1)


def t_seil():
    print("\n-- Seil (elastische Kettenlinie) ---------------------------------")
    P1 = np.array([0.0, 0.0, 0.0])
    P2 = np.array([100.0, 0.0, 0.0])
    q = 10.0
    w = np.array([0.0, 0.0, -q])
    EA = 1e8
    f_soll = 5.0
    L0 = vb.seil_laenge_aus_durchhang(P1, P2, EA, w, f_soll)
    fi, Kt, info = vb.seil_kettenlinie(P1, P2, L0, EA, w)
    H = info["H"]
    close("Seil: H gegen Parabel w L^2/(8 f)", H, q * 100.0 ** 2 / (8 * f_soll), 1e-2)
    close("Seil: Durchhang aus info = f", info["Durchhang"], f_soll, 1e-8)
    # exakte (dehnstarre) Kettenlinie: f = H/q (cosh(q l/(2H)) - 1)
    close("Seil: Durchhang gegen cosh-Beziehung", H / q * (math.cosh(q * 100 / (2 * H)) - 1),
          f_soll, 3e-3)
    close("Seil: Tmax = H cosh(q l/(2H))", info["Tmax"], H * math.cosh(q * 100 / (2 * H)), 1e-3)
    close("Seil: Tmax = sqrt(H^2 + (q L0/2)^2) exakt", info["Tmax"],
          math.hypot(H, q * L0 / 2), 1e-10)
    close("Seil: Tmin = H (Tiefpunkt im Feld)", info["Tmin"], H, 1e-12)
    close("Seil: L0 aus Horizontalzug (Rueckrechnung)",
          vb.seil_laenge_aus_horizontalzug(P1, P2, EA, w, H), L0, 1e-9)
    # Vorzeichen: die Knoten muessen das Seil halten -> Summe f_int = -w L0
    check("Seil: Summe f_int = -w L0 (Knoten tragen das Gewicht)",
          np.allclose(fi[:3] + fi[3:], -w * L0, rtol=1e-10, atol=1e-9))
    check("Seil: f_int1 = -(H, V1), f_int2 = +(H, V2), Seil zieht die Knoten zusammen",
          fi[0] < 0 and fi[3] > 0 and abs(fi[0] + H) < 1e-9 * H and abs(fi[3] - H) < 1e-9 * H
          and fi[2] > 0 and fi[5] > 0)
    close("Seil: Vertikalkomponenten symmetrisch (V2 = -V1 = q L0/2)",
          info["V2"], q * L0 / 2, 1e-10)
    # gedehnte Laenge gegen Polygonzug der Seilform
    pts = vb.seil_form(P1, P2, L0, EA, w, 2001)
    Lpoly = float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
    close("Seil: gedehnte Laenge L gegen Seilform", info["L"], Lpoly, 1e-6)
    check("Seil: L > L0 (Zug dehnt)", info["L"] > L0)
    close("Seil: seil_form Sehnenabstand in der Mitte = f",
          _sehnenabstand(pts, P1, P2).max(), f_soll, 1e-2)
    check("Seil: seil_form beginnt/endet in P1/P2",
          np.allclose(pts[0], P1, atol=1e-9) and np.allclose(pts[-1], P2, atol=1e-9))
    # Form gegen die Kettenlinie z = H/q (cosh(q (x - l/2)/H) - cosh(q l/(2H)))
    xs = pts[:, 0]
    z_kette = H / q * (np.cosh(q * (xs - 50) / H) - math.cosh(q * 50 / H))
    close("Seil: seil_form liegt auf der Kettenlinie (max. Abw.)",
          abs(pts[:, 2] - z_kette).max() / f_soll, 0.0, 3e-3)

    # Tangente gegen zentrale Differenzen
    def fd_tangente(P1_, P2_, L0_, w_, eps):
        Kfd = np.zeros((6, 6))
        for j in range(6):
            dv = np.zeros(6)
            dv[j] = eps
            fp = vb.seil_kettenlinie(P1_ + dv[:3], P2_ + dv[3:], L0_, EA, w_)[0]
            fm = vb.seil_kettenlinie(P1_ - dv[:3], P2_ - dv[3:], L0_, EA, w_)[0]
            Kfd[:, j] = (fp - fm) / (2 * eps)
        return Kfd

    Kfd = fd_tangente(P1, P2, L0, w, 2e-4)
    close("Seil: Kt gegen zentrale Differenzen (horizontal)",
          np.linalg.norm(Kt - Kfd) / np.linalg.norm(Kt), 0.0, 1e-5)
    check("Seil: Kt symmetrisch, Form [[Kc,-Kc],[-Kc,Kc]]",
          np.allclose(Kt, Kt.T) and np.allclose(Kt[:3, :3], Kt[3:, 3:])
          and np.allclose(Kt[:3, 3:], -Kt[:3, :3]))
    close("Seil: Steifigkeit quer zur Ebene = H/l", Kt[1, 1], H / 100.0, 1e-10)
    check("Seil: Kc positiv definit", np.linalg.eigvalsh(Kt[:3, :3]).min() > 0)

    # geneigte Spannweite
    P2g = np.array([80.0, 10.0, 30.0])
    c = float(np.linalg.norm(P2g - P1))
    L0g = 1.05 * c
    fg, Kg, ig = vb.seil_kettenlinie(P1, P2g, L0g, EA, w)
    check("Seil geneigt: Loesung ohne Fehler, H > 0", ig["H"] > 0 and np.all(np.isfinite(fg)))
    check("Seil geneigt: Summe f_int = -w L0",
          np.allclose(fg[:3] + fg[3:], -w * L0g, rtol=1e-10, atol=1e-9))
    Kfdg = fd_tangente(P1, P2g, L0g, w, 2e-4)
    close("Seil geneigt: Kt gegen zentrale Differenzen",
          np.linalg.norm(Kg - Kfdg) / np.linalg.norm(Kg), 0.0, 1e-5)
    # Momentengleichgewicht um P1: Knotenkraefte gegen verteiltes Gewicht
    ptsg = vb.seil_form(P1, P2g, L0g, EA, w, 4001)
    sw = np.ones(4001)
    sw[0] = sw[-1] = 0.5
    schwer = (sw @ ptsg) / sw.sum()               # Schwerpunkt (gleichmaessig in s)
    M_knoten = np.cross(P2g - P1, -fg[3:])        # Kraft auf Knoten 2 = -f_int2
    M_gewicht = np.cross(schwer - P1, w * L0g)
    close("Seil geneigt: Momentengleichgewicht um P1",
          np.linalg.norm(M_knoten - M_gewicht) / np.linalg.norm(M_gewicht), 0.0, 1e-5)
    sag_g = _sehnenabstand(ptsg, P1, P2g).max()
    close("Seil geneigt: Durchhang aus info = Sehnenabstand der Form", ig["Durchhang"], sag_g, 1e-6)
    L0g2 = vb.seil_laenge_aus_durchhang(P1, P2g, EA, w, sag_g)
    close("Seil geneigt: L0 aus Durchhang (Rueckrechnung)", L0g2, L0g, 1e-8)
    close("Seil geneigt: L0 aus Horizontalzug (Rueckrechnung)",
          vb.seil_laenge_aus_horizontalzug(P1, P2g, EA, w, ig["H"]), L0g, 1e-8)

    # straffes Seil: Grenzuebergang zum Zugstab
    L0s = 99.99
    ws = np.array([0.0, 0.0, -1e-3])
    fs, Ks, is_ = vb.seil_kettenlinie(P1, P2, L0s, EA, ws)
    Tst = EA * (100.0 - L0s) / L0s
    e = np.array([1.0, 0.0, 0.0])
    Kstab = EA / L0s * np.outer(e, e) + Tst / 100.0 * (np.eye(3) - np.outer(e, e))
    close("Seil straff: Kc gegen Zugstab EA/L0 (+ T/L quer)",
          np.linalg.norm(Ks[:3, :3] - Kstab) / np.linalg.norm(Kstab), 0.0, 1e-3)
    close("Seil straff: Zugkraft EA (c - L0)/L0", is_["Tmax"], Tst, 1e-3)

    # senkrecht haengend: straff und mit Schlaufe
    Po = np.array([0.0, 0.0, 10.0])
    Pu = np.array([0.0, 0.0, 0.0])
    fv, Kv, iv = vb.seil_kettenlinie(Po, Pu, 9.99, EA, w)
    Tv = EA * 0.01 / 9.99
    check("Seil senkrecht straff: ohne Fehler, Zug ~ EA dL/L0 +- Gewicht",
          np.all(np.isfinite(fv)) and abs(iv["Tmax"] - iv["Tmin"] - q * 9.99) < 1e-6
          and abs(iv["Tmax"] - (Tv + q * 9.99 / 2)) / Tv < 1e-3)
    check("Seil senkrecht straff: oberer Knoten haelt Zug + Gewicht",
          fv[2] > 0 and fv[5] < 0 and abs(fv[2] + fv[5] - q * 9.99) < 1e-6)
    close("Seil senkrecht straff: Kt axial = EA/L0", Kv[2, 2], EA / 9.99, 1e-12)
    check("Seil senkrecht straff: Kt seitlich > 0, symmetrisch",
          Kv[0, 0] > 0 and abs(Kv[0, 0] - Kv[1, 1]) < 1e-9 * Kv[0, 0] and np.allclose(Kv, Kv.T))
    fl, Kl, il = vb.seil_kettenlinie(Po, Pu, 12.0, EA, w)
    check("Seil senkrecht Schlaufe: ohne Fehler, Knoten tragen 11 m bzw. 1 m",
          np.all(np.isfinite(fl)) and abs(fl[2] - 110.0) < 1e-2 and abs(fl[5] - 10.0) < 1e-2)
    # fast senkrecht (allgemeiner Loeser mit kleinem H) ohne Fehler
    fn, Kn, inn = vb.seil_kettenlinie(Po, np.array([1e-4, 0.0, 0.0]), 12.0, EA, w)
    check("Seil fast senkrecht: allgemeiner Loeser konvergiert",
          np.all(np.isfinite(fn)) and inn["H"] > 0 and abs(fn[2] - 110.0) < 1e-2)

    # ohne Streckenlast: gerader Zugstab bzw. kraftlos
    f0, K0, i0 = vb.seil_kettenlinie(P1, P2, 99.9, EA, np.zeros(3))
    close("Seil w = 0, gedehnt: Zugstab EA/L0", K0[0, 0], EA / 99.9, 1e-12)
    close("Seil w = 0, gedehnt: N = EA (c - L0)/L0", f0[3], EA * 0.1 / 99.9, 1e-12)
    f1, K1, i1 = vb.seil_kettenlinie(P1, P2, 100.5, EA, np.zeros(3))
    check("Seil w = 0, schlaff: kraftlos (f = 0, Kt = 0)",
          i1["schlaff"] and np.all(f1 == 0) and np.all(K1 == 0))
    f2, K2, i2 = vb.seil_kettenlinie(P1, P2, 100.5, EA, np.zeros(3), k_min=1e-6)
    close("Seil w = 0, schlaff: Stabilisierung k_min EA/L0", K2[0, 0], 1e-6 * EA / 100.5, 1e-12)


# ==========================================================================
# B7  Starre Koerper
# ==========================================================================
def _feder_system(n_slave, ks, kr):
    """Diagonale Federn an allen Slaves (6 FHG je Slave), Master frei."""
    ndof = 6 * (n_slave + 1)
    K = np.zeros((ndof, ndof))
    for i in range(n_slave):
        c = 6 * (i + 1)
        K[c:c + 3, c:c + 3] = ks * np.eye(3)
        K[c + 3:c + 6, c + 3:c + 6] = kr * np.eye(3)
    return K


def t_starrkoerper():
    print("\n-- Starre Koerper RBE2 / RBE3 ----------------------------------")
    a = 0.5
    P_m = np.array([0.0, 0.0, 0.0])
    P_s = np.array([[a, a, 0.0], [-a, a, 0.0], [-a, -a, 0.0], [a, -a, 0.0]])
    ks, kr, kp = 1e4, 1e3, 1e12
    n = len(P_s)

    # ---- RBE2 -----------------------------------------------------------
    G = vb.starrkoerper_matrix(P_m, P_s, "RBE2")
    check("RBE2: G hat 6 Zeilen je Slave", G.shape == (6 * n, 6 * (n + 1)))
    # Starrkoerperbewegung erfuellt G u = 0 exakt
    um, thm = np.array([0.1, -0.2, 0.3]), np.array([0.01, 0.02, -0.03])
    u = np.concatenate([um, thm] + [np.concatenate([um + np.cross(thm, P - P_m), thm]) for P in P_s])
    check("RBE2: Starrkoerperbewegung erfuellt G u = 0", np.allclose(G @ u, 0, atol=1e-14))
    K = _feder_system(n, ks, kr) + vb.starrkoerper_steifigkeit(G, kp)
    check("RBE2: Strafmatrix symmetrisch", np.allclose(K, K.T))
    Fx, Fz, Mx = 200.0, 1000.0, 500.0
    F = np.zeros(6 * (n + 1))
    F[0], F[2], F[3] = Fx, Fz, Mx
    u = np.linalg.solve(K, F)
    # Handrechnung: starre Platte auf 4 Federn
    close("RBE2: Master u_x = Fx/(4 ks)", u[0], Fx / (4 * ks), 1e-6)
    close("RBE2: Master u_z = Fz/(4 ks)", u[2], Fz / (4 * ks), 1e-6)
    close("RBE2: Master theta_x = Mx/(4 kr + ks sum y^2)", u[3], Mx / (4 * kr + ks * 4 * a * a), 1e-6)
    ok = True
    for i, P in enumerate(P_s):
        c = 6 * (i + 1)
        us_soll = u[:3] + np.cross(u[3:6], P - P_m)
        ok &= np.allclose(u[c:c + 3], us_soll, rtol=1e-6, atol=1e-6 * abs(us_soll).max())
        ok &= np.allclose(u[c + 3:c + 6], u[3:6], rtol=1e-6, atol=1e-6 * abs(u[3:6]).max())
    check("RBE2: Slaves folgen starr (u_s = u_m + theta_m x r, theta_s = theta_m)", ok)
    close("RBE2: Slave 1 u_z = u_mz + theta_x * y", u[6 + 2], u[2] + u[3] * a, 1e-6)
    # Gleichgewicht: Federkraefte = aeussere Lasten
    fs = np.array([ks * u[6 * (i + 1) + 2] for i in range(n)])
    close("RBE2: Summe Federkraefte z = Fz", fs.sum(), Fz, 1e-6)
    close("RBE2: Momentengleichgewicht um x", float(np.sum(fs * P_s[:, 1])) + kr * 4 * u[3], Mx, 1e-6)

    # ---- RBE3 -----------------------------------------------------------
    G3 = vb.starrkoerper_matrix(P_m, P_s, "RBE3")
    check("RBE3: G hat 6 Zeilen", G3.shape == (6, 6 * (n + 1)))
    u = np.concatenate([um, thm] + [np.concatenate([um + np.cross(thm, P - P_m), np.zeros(3)]) for P in P_s])
    check("RBE3: Starrkoerperbewegung erfuellt G u = 0", np.allclose(G3 @ u, 0, atol=1e-14))
    K3 = _feder_system(n, ks, kr) + vb.starrkoerper_steifigkeit(G3, kp)
    F = np.zeros(6 * (n + 1))
    F[2] = Fz
    u = np.linalg.solve(K3, F)
    f_sl = np.array([ks * u[6 * (i + 1):6 * (i + 1) + 3] for i in range(n)])
    check("RBE3: Einzellast gleich auf 4 Slaves verteilt (F/4)",
          np.allclose(f_sl[:, 2], Fz / 4, rtol=1e-6) and np.allclose(f_sl[:, :2], 0, atol=1e-6 * Fz))
    close("RBE3: Summe Slave-Kraefte = F", f_sl[:, 2].sum(), Fz, 1e-6)
    M_sl = np.sum(np.cross(P_s - P_m, f_sl), axis=0)
    close("RBE3: Momentengleichgewicht (Sum r x f = 0)", np.linalg.norm(M_sl) / (Fz * a), 0.0, 1e-6)
    # Last mit Moment am Master
    F[3] = Mx
    u = np.linalg.solve(K3, F)
    f_sl = np.array([ks * u[6 * (i + 1):6 * (i + 1) + 3] for i in range(n)])
    M_sl = np.sum(np.cross(P_s - P_m, f_sl), axis=0)
    close("RBE3 mit Moment: Summe Kraefte = F", f_sl[:, 2].sum(), Fz, 1e-6)
    close("RBE3 mit Moment: Sum r x f = M", M_sl[0], Mx, 1e-6)
    close("RBE3 mit Moment: Slave 1 f_z = F/4 + M/(4 a)", f_sl[0, 2], Fz / 4 + Mx / (4 * a), 1e-6)
    # ungleiche Gewichte, Master im gewichteten Schwerpunkt -> proportional
    wg = np.array([1.0, 2.0, 3.0, 4.0])
    P_m2 = (wg[:, None] * P_s).sum(axis=0) / wg.sum()
    G3w = vb.starrkoerper_matrix(P_m2, P_s, "RBE3", gewichte=wg)
    K3w = _feder_system(n, ks, kr) + vb.starrkoerper_steifigkeit(G3w, kp)
    F = np.zeros(6 * (n + 1))
    F[0], F[2] = Fx, Fz
    u = np.linalg.solve(K3w, F)
    f_sl = np.array([ks * u[6 * (i + 1):6 * (i + 1) + 3] for i in range(n)])
    check("RBE3 Gewichte: Kraefte proportional w_i/W (x und z)",
          np.allclose(f_sl[:, 2], Fz * wg / wg.sum(), rtol=1e-6)
          and np.allclose(f_sl[:, 0], Fx * wg / wg.sum(), rtol=1e-6))
    close("RBE3 Gewichte: Summe = F", f_sl[:, 2].sum(), Fz, 1e-6)
    M_sl = np.sum(np.cross(P_s - P_m2, f_sl), axis=0)
    close("RBE3 Gewichte: Momentengleichgewicht um Master", np.linalg.norm(M_sl) / (Fz * a), 0.0, 1e-6)


# ==========================================================================
# B8  Grenzschicht
# ==========================================================================
def _rot(axis, ang):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    S = bm._skew(axis)
    return np.eye(3) + math.sin(ang) * S + (1 - math.cos(ang)) * S @ S


def t_grenzschicht():
    print("\n-- Grenzschicht ------------------------------------------------")
    kn, kt = 5e6, 2e6
    delta = 1e-3
    # zwei Vierecke 1x1 nebeneinander, 6 Knoten je Seite
    Pn = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [0, 1, 0], [1, 1, 0], [2, 1, 0]], float)
    elems = [[0, 1, 4, 3], [1, 2, 5, 4]]
    nk = len(Pn)
    ndof = 6 * nk                                  # unten 0..5, oben 6..11, je 3 FHG
    K = np.zeros((ndof, ndof))
    for el in elems:
        Ke = vb.k_grenzschicht(Pn[el], Pn[el], kn, kt)
        d = [3 * i + j for i in el for j in range(3)] + [3 * (nk + i) + j for i in el for j in range(3)]
        K[np.ix_(d, d)] += Ke
    Ke1 = vb.k_grenzschicht(Pn[elems[0]], Pn[elems[0]], kn, kt)
    check("Grenzschicht: Elementmatrix 24x24 symmetrisch, PSD",
          Ke1.shape == (24, 24) and np.allclose(Ke1, Ke1.T)
          and np.linalg.eigvalsh(Ke1).min() > -1e-9 * abs(Ke1).max())
    sv = np.linalg.svd(Ke1, compute_uv=False)
    check("Grenzschicht: Rang 12 = 3 k (nur Relativverschiebung)",
          int(np.sum(sv > 1e-9 * sv[0])) == 12, f"Rang {int(np.sum(sv > 1e-9 * sv[0]))}")
    # gleichmaessige Normaloeffnung: Summe Kraft oben = kn delta A
    u = np.zeros(ndof)
    u[3 * nk + 2::3] = delta
    f = K @ u
    close("Grenzschicht: Normaloeffnung, Summe F_z oben = kn delta A", f[3 * nk + 2::3].sum(),
          kn * delta * 2.0, 1e-12)
    close("Grenzschicht: Gegenkraft unten", f[2:3 * nk:3].sum(), -kn * delta * 2.0, 1e-12)
    check("Grenzschicht: keine Tangentialkraft bei Normaloeffnung",
          np.allclose(f[0::3], 0, atol=1e-9 * kn * delta) and np.allclose(f[1::3], 0, atol=1e-9 * kn * delta))
    # Verteilung: Innenknoten (zwei Elemente) doppelt
    close("Grenzschicht: Eckknoten erhaelt kn delta A/4", f[3 * (nk + 0) + 2], kn * delta / 4, 1e-12)
    close("Grenzschicht: Mittelknoten erhaelt 2 kn delta A/4", f[3 * (nk + 1) + 2], 2 * kn * delta / 4, 1e-12)
    # tangential
    u = np.zeros(ndof)
    u[3 * nk::3] = delta
    f = K @ u
    close("Grenzschicht: Tangentialverschiebung, Summe F_x = kt delta A", f[3 * nk::3].sum(),
          kt * delta * 2.0, 1e-12)
    check("Grenzschicht: keine Normalkraft bei Tangentialverschiebung",
          np.allclose(f[2::3], 0, atol=1e-9 * kt * delta))
    # gemeinsame Starrkoerperbewegung beider Seiten kraftlos
    Pall = np.vstack([Pn, Pn])
    ok = True
    for mode in range(6):
        u = np.zeros(ndof)
        for i, P in enumerate(Pall):
            if mode < 3:
                u[3 * i + mode] = 1.0
            else:
                th = np.zeros(3)
                th[mode - 3] = 1.0
                u[3 * i:3 * i + 3] = np.cross(th, P - np.array([0.3, -0.7, 2.0]))
        ok &= np.linalg.norm(K @ u) < 1e-9 * abs(K).max() * np.linalg.norm(u)
    check("Grenzschicht: 6 Starrkoerpermoden beider Seiten kraftlos", ok)
    # Spannung in der Mitte
    ue = np.zeros(24)
    ue[12 + 2::3] = delta                          # obere Knoten in +z
    sn, st1, st2 = vb.grenzschicht_spannung(Pn[elems[0]], Pn[elems[0]], kn, kt, ue)
    close("Grenzschicht: sigma_n = kn delta (Zug positiv)", sn, kn * delta, 1e-12)
    check("Grenzschicht: keine Schubspannung bei Oeffnung", abs(st1) < 1e-9 * kn * delta and abs(st2) < 1e-9 * kn * delta)
    ue = np.zeros(24)
    ue[12 + 1::3] = delta                          # obere Knoten in +y -> t2
    sn, st1, st2 = vb.grenzschicht_spannung(Pn[elems[0]], Pn[elems[0]], kn, kt, ue)
    close("Grenzschicht: tau_2 = kt delta (Verschiebung in y)", st2, kt * delta, 1e-12)
    check("Grenzschicht: sigma_n = tau_1 = 0 bei Schub in y", abs(sn) < 1e-9 * kt * delta and abs(st1) < 1e-9 * kt * delta)
    ue = np.zeros(24)
    ue[2:12:3] = delta                             # untere Knoten in +z -> Druck
    sn, _s1, _s2 = vb.grenzschicht_spannung(Pn[elems[0]], Pn[elems[0]], kn, kt, ue)
    close("Grenzschicht: Druck negativ", sn, -kn * delta, 1e-12)

    # gedrehte Flaeche: Oeffnung entlang der Normalen
    Q = _rot([1, 2, 3], 0.7)
    Pq = (Q @ Pn[elems[0]].T).T + np.array([1.0, -2.0, 0.5])
    nq = Q @ np.array([0.0, 0.0, 1.0])
    Kq = vb.k_grenzschicht(Pq, Pq, kn, kt)
    ue = np.zeros(24)
    for i in range(4):
        ue[12 + 3 * i:12 + 3 * i + 3] = delta * nq
    fq = Kq @ ue
    Fo = fq[12:].reshape(4, 3).sum(axis=0)
    close("Grenzschicht gedreht: |Summe F oben| = kn delta A", np.linalg.norm(Fo), kn * delta, 1e-12)
    close("Grenzschicht gedreht: Kraft entlang der Normalen", float(Fo @ nq) / np.linalg.norm(Fo), 1.0, 1e-12)
    sn, st1, st2 = vb.grenzschicht_spannung(Pq, Pq, kn, kt, ue)
    close("Grenzschicht gedreht: sigma_n = kn delta", sn, kn * delta, 1e-12)
    check("Grenzschicht gedreht: Elementmatrix = Q K Q^T",
          np.allclose(Kq, np.kron(np.eye(8), Q) @ Ke1 @ np.kron(np.eye(8), Q).T))

    # Dreieck (3 Knoten je Seite)
    Pt = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    Kd = vb.k_grenzschicht(Pt, Pt, kn, kt)
    check("Grenzschicht Dreieck: 18x18 symmetrisch, Rang 9",
          Kd.shape == (18, 18) and np.allclose(Kd, Kd.T)
          and int(np.sum(np.linalg.svd(Kd, compute_uv=False) > 1e-9 * abs(Kd).max())) == 9)
    ue = np.zeros(18)
    ue[9 + 2::3] = delta
    fd = Kd @ ue
    close("Grenzschicht Dreieck: Summe F_z oben = kn delta A (A = 1/2)", fd[9 + 2::3].sum(),
          kn * delta * 0.5, 1e-12)
    close("Grenzschicht Dreieck: jeder Knoten A/3", fd[9 + 2], kn * delta / 6, 1e-12)
    ue = np.zeros(18)
    ue[9::3] = delta
    fd = Kd @ ue
    close("Grenzschicht Dreieck: Summe F_x = kt delta A", fd[9::3].sum(), kt * delta * 0.5, 1e-12)
    ue = np.zeros(18)
    ue[9 + 2::3] = delta
    sn, st1, st2 = vb.grenzschicht_spannung(Pt, Pt, kn, kt, ue)
    close("Grenzschicht Dreieck: sigma_n = kn delta", sn, kn * delta, 1e-12)


# ==========================================================================
def main():
    print("=" * 92)
    print("STATIK3D - Element-Bausteine (Versatz, Woelbtorsion, Feder, Seil, RBE, Grenzschicht)")
    print("=" * 92)
    t_versatz()
    t_woelbkrafttorsion()
    t_feder()
    t_seil()
    t_starrkoerper()
    t_grenzschicht()
    print("\n" + "=" * 92)
    nok = sum(1 for r in RESULTS if r[1])
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    print("=" * 92)
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
