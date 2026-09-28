"""V4 (Teilprojekt 3): PCG mit Jacobi auf dem matrixfreien Operator gegen den Direktloeser -
Patch-Test (voll), Kragarmsegment mit Schnittebenen ('schnitt', projizierter CG mit
Multiplikatoren), Lame (normal), Kirsch verfeinert (normal + Traktion).

Aufruf: python -m volumen3d.tests.test_pcg   (~3 min)
"""
from __future__ import annotations

import sys
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf


def _pcg_loesen(pr, vorgaben, tol=1e-10, max_iter=40000):
    """Loest dasselbe reduzierte System wie FcmProblem.loesen, aber matrixfrei mit PCG."""
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.linalg.pcg import jacobi_diagonale, pcg
    if pr.K is None:
        pr.aufbauen()
    n = pr.gitter.n_dof
    C = pr.zwaenge.C
    z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    op = Operator(z, C=C, K_rand=pr.K_rand)
    t = time.perf_counter()
    diag = jacobi_diagonale(z, C, pr.K_rand)
    t_diag = time.perf_counter() - t
    F = pr.rechte_seite(vorgaben)
    b = np.asarray(C.T @ F[:n]).ravel()
    B = d = None
    if pr.n_zwaenge:
        B = np.asarray(pr._B @ C)
        d = F[n:]
    t = time.perf_counter()
    erg = pcg(op.frei_anwenden, b, 1.0 / diag, tol=tol, B=B, d=d, max_iter=max_iter)
    t_pcg = time.perf_counter() - t
    U = np.asarray(C @ erg.x).ravel()
    return U, erg, t_diag, t_pcg


# Ausgangslage vor dem Mehrgitter (28.09.2026): die Jacobi-vorkonditionierte Matrix hat Kondition
# 1,45e6 (Patch h 20 p 2) bzw. 5,0e7 (Lame h 20 p 3) - hierarchische Moden hoher Ordnung, Nitsche-
# Strafterm (Diagonale max/min 3e4) und Schnittzellen. PCG braucht 5 045 bzw. 20 373 Iterationen bis
# 1e-10 und trifft die direkte Loesung dann auf 7e-6 bzw. 2e-7 (Kondition von A selbst 2e7 / 4e9).
# Kriterium hier: konvergiert und < 1e-4 relativ; die Iterationszahlen sind der Massstab fuer TP 4.
def _vergleich(name, pr, vorgaben, tol=1e-10, grenze=1e-4):
    U_ref = pr.loesen(vorgaben)[:, 0]
    lam_ref = pr.multiplikatoren[:, 0] if pr.n_zwaenge else np.zeros(0)
    U, erg, t_diag, t_pcg = _pcg_loesen(pr, vorgaben, tol)
    fehler = np.abs(U - U_ref).max() / max(np.abs(U_ref).max(), 1e-300)
    # Spannungen sind von freien Starrkoerperanteilen unabhaengig (Kirsch: u_z ist nicht gehalten,
    # Direktloeser und CG waehlen verschiedene z-Verschiebungen; das Residuum ist bei beiden ~1e-10)
    P = np.concatenate([pr.quadratur.zelle(c)[0][pr.quadratur.zelle(c)[2]][:3] for c in range(0, len(pr.gitter.ijk), max(1, len(pr.gitter.ijk) // 100))])
    s_ref = pr.auswertung(U_ref).spannung(P)
    s = pr.auswertung(U).spannung(P)
    fehler_s = np.abs(s - s_ref).max() / max(np.abs(s_ref).max(), 1e-300)
    lam_ok = True
    lam_txt = ""
    if pr.n_zwaenge:
        lam_ok = np.allclose(erg.multiplikatoren, lam_ref, rtol=1e-6, atol=1e-6 * max(np.abs(lam_ref).max(), 1.0))
        lam_txt = f", Multiplikatoren {np.round(erg.multiplikatoren, 3).tolist()} gegen {np.round(lam_ref, 3).tolist()}"
    check(f"{name}: PCG (Jacobi, tol {tol:g}) trifft den Direktloeser in den Spannungen auf {grenze:g}; {erg.iterationen} Iterationen, "
          f"Residuum {erg.residuum_rel:.1e}, Energie {erg.energie_rel:.1e}, {pr.gitter.n_dof} FHG ({C_n(pr)} frei), "
          f"Diagonale {t_diag:.1f} s, PCG {t_pcg:.1f} s{lam_txt}",
          erg.konvergiert and fehler_s < grenze and lam_ok, f"max |dsigma|/|sigma| {fehler_s:.1e}, max |dU|/|U| {fehler:.1e} (Starrkoerperanteil moeglich)")
    return erg


def C_n(pr):
    return pr.zwaenge.C.shape[1]


def test_pcg():
    from volumen3d.tests.test_kragarm import _segment
    from volumen3d.tests.test_operator import _kirsch, _lame
    from volumen3d.tests.test_patch import _problem as patch_problem, u_exakt

    def u_lin(P):                                          # lineare Kinematik fuer die Schnittebenen
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([1e-3 * P[:, 0], -0.3e-3 * P[:, 1], -0.3e-3 * P[:, 2]], axis=1)

    _vergleich("Patch-Test h 20 p 2 (Dirichlet voll, Aggregation)", patch_problem(2, 1e-8), {"alles": u_exakt})
    _vergleich("Kragarmsegment p 2 h 50 ('schnitt': projizierter CG)", _segment(400.0, 600.0, 2, 50.0), {"links": u_lin, "rechts": u_lin})
    _vergleich("Lame h 20 p 3 (Normalprojektion, Druck)", _lame_mit_druck(_lame(p=3)), {})
    _vergleich("Kirsch h 20 p 2 verfeinert (haengende Freiheitsgrade, Traktion)", _kirsch(verfeinert=True), {})


def test_problem_pcg():
    """FcmProblem(loeser='pcg') rechnet denselben Lastfall wie der Direktloeser (Protokoll mit Iterationen)."""
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.tests.test_kragarm import _segment
    from volumen3d.tests.test_lame import E, NU, _geometrie

    def u_lin(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([1e-3 * P[:, 0], -0.3e-3 * P[:, 1], -0.3e-3 * P[:, 2]], axis=1)

    ergebnisse = []
    for loeser in ("direkt", "pcg"):
        pr = _lame_mit_druck(FcmProblem(_geometrie(), h=25.0, p=2, werkstoff=Werkstoff(E, NU), loeser=loeser, toleranz=1e-10))
        U = pr.loesen({})[:, 0]
        P = np.array([[60.0, 30.0, 10.0], [80.0, 20.0, 5.0], [55.0, 55.0, 15.0]])
        ergebnisse.append((pr, pr.auswertung(U).spannung(P)))
    (pr_d, s_d), (pr_p, s_p) = ergebnisse
    check(f"FcmProblem loeser='pcg' (Lame h 25 p 2): Spannungen wie 'direkt' auf 1e-6; Protokoll {pr_p.protokoll['loeser']}, "
          f"Iterationen {pr_p.protokoll['iterationen']}, Residuum {pr_p.protokoll['residuum']:.1e}, Operator {pr_p.protokoll['operator']}",
          np.abs(s_p - s_d).max() / np.abs(s_d).max() < 1e-6 and pr_p.protokoll["residuum"] < 1e-8 and pr_p.protokoll["iterationen"][0] > 0,
          f"{np.abs(s_p - s_d).max() / np.abs(s_d).max():.1e}")
    pr = _segment(400.0, 600.0, 2, 50.0)
    pr_p = _segment(400.0, 600.0, 2, 50.0)
    pr_p.loeser, pr_p.toleranz = "pcg", 1e-10
    U_d = pr.loesen({"links": u_lin, "rechts": u_lin})[:, 0]
    U_p = pr_p.loesen({"links": u_lin, "rechts": u_lin})[:, 0]
    check("FcmProblem loeser='pcg' mit Schnittebenen ('schnitt'): Verschiebungen und Multiplikatoren wie 'direkt'",
          np.abs(U_p - U_d).max() / np.abs(U_d).max() < 1e-6 and np.allclose(pr_p.multiplikatoren, pr.multiplikatoren, atol=1e-6),
          f"{np.abs(U_p - U_d).max() / np.abs(U_d).max():.1e}, Iterationen {pr_p.protokoll['iterationen']}")


def _lame_mit_druck(pr):
    from volumen3d.tests.test_lame import PI
    for n in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
        pr.verschiebungsrand(n, n, projektion="normal")
    pr.druck("innen", PI)
    return pr


def test_pcg_nan():
    """Ein Vorkonditionierer mit NaN bricht sofort mit Meldung ab, statt bis max_iter zu laufen (Vergleiche mit
    NaN sind falsch; Gutachten 28.09.2026: singulaerer GPU-Block -> 1000 V-Zyklen, dann 'Residuum nan')."""
    from volumen3d.linalg.pcg import pcg
    A = np.diag(np.arange(1.0, 11.0))
    aufrufe = [0]

    def vork(r):
        aufrufe[0] += 1
        return np.full_like(r, np.nan) if aufrufe[0] > 2 else r.copy()

    try:
        pcg(lambda x: A @ x, np.ones(10), vork, tol=1e-12, max_iter=500)
        meldung = ""
    except ValueError as ex:
        meldung = str(ex)
    check("NaN im Vorkonditionierer: ValueError nach wenigen Schritten", "NaN" in meldung and aufrufe[0] <= 4,
          f"{meldung!r} nach {aufrufe[0]} Anwendungen")


if __name__ == "__main__":
    sys.exit(lauf([test_pcg, test_problem_pcg, test_pcg_nan]))
