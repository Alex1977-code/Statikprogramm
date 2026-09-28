"""V1/V2 (Teilprojekt 3): Zelldaten im SoA-Layout und matrixfreier Operator gegen die assemblierte
Matrix aus Teilprojekt 1.

Aufruf: python -m volumen3d.tests.test_operator   (~2 min)
"""
from __future__ import annotations

import sys
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf


def _kirsch(p=2, h=20.0, verfeinert=False):
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.tests.test_kirsch import D, T, _platte
    v = Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, h / 4),)) if verfeinert else None
    return _platte(p, h, verfeinerung=v)


def _lame(p=2, h=20.0):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.tests.test_lame import E, NU, _geometrie
    return FcmProblem(_geometrie(), h=h, p=p, werkstoff=Werkstoff(E, NU))


def test_zelldaten():
    from volumen3d.fcm.elastizitaet import assemblieren
    from volumen3d.fcm.operator import Zelldaten
    for name, pr in (("Kirsch h 20 p 2", _kirsch()), ("Lame h 20 p 2", _lame()), ("Kirsch h 20 p 2 verfeinert", _kirsch(verfeinert=True))):
        t = time.perf_counter()
        z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        t_z = time.perf_counter() - t
        g = pr.gitter
        dofs_ok = all(np.array_equal(z.dofs[c], g.zell_dofs(c)) for c in range(0, len(g.ijk), max(1, len(g.ijk) // 50)))
        # Inzidenz: jeder Eintrag (Zelle, lokal) zeigt auf den Freiheitsgrad, unter dem er steht
        d = np.repeat(np.arange(g.n_dof), np.diff(z.inz_zeiger))
        inz_ok = np.array_equal(z.dofs[z.inz_zelle, z.inz_lokal], d) and z.inz_zeiger[-1] == z.dofs.size
        check(f"{name}: Freiheitsgradtabelle wie zell_dofs, Inzidenz vollstaendig und richtig ({len(g.ijk)} Zellen, "
              f"{len(z.innen)} innen, {len(z.cut)} geschnitten, {t_z:.1f} s)", dofs_ok and inz_ok, str(z.statistik))
        K = assemblieren(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        K2 = z.matrix()
        diff = abs(K - K2).max() / abs(K).max()
        check(f"{name}: Zellmatrizen ueber die Inzidenz summiert = assemblierte Matrix (< 1e-12)", diff < 1e-12, f"{diff:.1e}")


def test_operator():
    from volumen3d.fcm.elastizitaet import assemblieren
    from volumen3d.fcm.operator import Operator, Zelldaten
    rng = np.random.default_rng(5)
    for name, pr in (("Kirsch h 20 p 2 verfeinert", _kirsch(verfeinert=True)), ("Lame h 20 p 3", _lame(p=3))):
        g = pr.gitter
        z = Zelldaten(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        K = assemblieren(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        op = Operator(z)
        X = rng.standard_normal((g.n_dof, 20))
        op.anwenden(X[:, 0])                                   # numba uebersetzen
        t = time.perf_counter()
        V = np.stack([op.anwenden(X[:, k]) for k in range(20)], axis=1)
        t_op = (time.perf_counter() - t) / 20
        R = K @ X
        fehler = np.abs(V - R).max() / np.abs(R).max()
        check(f"{name}: Operator K u gegen Matrix, 20 Zufallsvektoren (< 1e-12); {t_op * 1e3:.1f} ms je Anwendung, {g.n_dof} Freiheitsgrade, numba {op.numba}",
              fehler < 1e-12, f"{fehler:.1e}")
        # freier Operator mit Zwangsmatrix und Nitsche-Rand wie in FcmProblem.aufbauen
        pr.aufbauen()
        C = pr.zwaenge.C
        A_ref = C.T @ (K + pr.K_rand) @ C
        Y = rng.standard_normal((C.shape[1], 5))
        op_frei = Operator(z, C=C, K_rand=pr.K_rand)
        W = np.stack([op_frei.frei_anwenden(Y[:, k]) for k in range(5)], axis=1)
        Rf = A_ref @ Y
        fehler = np.abs(W - Rf).max() / np.abs(Rf).max()
        check(f"{name}: freier Operator C^T (K + K_rand) C gegen Matrix (< 1e-12)", fehler < 1e-12, f"{fehler:.1e}")


def test_kern():
    """Kurzfassung fuer die Kernsuite."""
    from volumen3d.fcm.elastizitaet import assemblieren
    from volumen3d.fcm.operator import Operator, Zelldaten
    pr = _lame(p=2, h=25.0)
    z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    K = assemblieren(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    op = Operator(z)
    x = np.random.default_rng(1).standard_normal(pr.gitter.n_dof)
    fehler = np.abs(op.anwenden(x) - K @ x).max() / np.abs(K @ x).max()
    check("Kernsuite: matrixfreier Operator = Matrix (Lame h 25 p 2, < 1e-12)", fehler < 1e-12, f"{fehler:.1e}")


if __name__ == "__main__":
    sys.exit(lauf([test_zelldaten, test_operator]))
