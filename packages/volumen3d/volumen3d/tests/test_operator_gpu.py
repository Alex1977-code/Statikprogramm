"""V6 (Teilprojekt 3): GPU-Operator (CuPy) gegen CPU-Operator und assemblierte Matrix, PCG auf der
GPU gegen CPU. Nur lokal mit GPU; ohne CuPy/GPU werden die Pruefungen als uebersprungen gemeldet.

Aufruf: python -m volumen3d.tests.test_operator_gpu   (~3 min)
"""
from __future__ import annotations

import sys
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf


def test_operator_gpu():
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - GPU-Pruefungen uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.elastizitaet import assemblieren
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.fcm.operator_gpu import OperatorGpu
    from volumen3d.tests.test_operator import _kirsch, _lame
    rng = np.random.default_rng(11)
    for name, pr in (("Kirsch h 20 p 2 verfeinert", _kirsch(verfeinert=True)), ("Lame h 20 p 3", _lame(p=3))):
        g = pr.gitter
        z = Zelldaten(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        K = assemblieren(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        pr.aufbauen()
        cpu = Operator(z, C=pr.zwaenge.C, K_rand=pr.K_rand)
        gpu = OperatorGpu(z, C=pr.zwaenge.C, K_rand=pr.K_rand)
        X = rng.standard_normal((g.n_dof, 10))
        V_gpu = np.stack([gpu.anwenden_np(X[:, k]) for k in range(10)], axis=1)
        R = K @ X
        f1 = np.abs(V_gpu - R).max() / np.abs(R).max()
        Y = rng.standard_normal((pr.zwaenge.C.shape[1], 5))
        W_gpu = np.stack([gpu.frei_anwenden_np(Y[:, k]) for k in range(5)], axis=1)
        W_cpu = np.stack([cpu.frei_anwenden(Y[:, k]) for k in range(5)], axis=1)
        f2 = np.abs(W_gpu - W_cpu).max() / np.abs(W_cpu).max()
        d_x = cupy.asarray(X[:, 0])
        gpu.anwenden(d_x)
        cupy.cuda.Stream.null.synchronize()
        t = time.perf_counter()
        for _ in range(20):
            gpu.anwenden(d_x)
        cupy.cuda.Stream.null.synchronize()
        t_gpu = (time.perf_counter() - t) / 20
        t = time.perf_counter()
        for _ in range(20):
            cpu.anwenden(X[:, 0])
        t_cpu = (time.perf_counter() - t) / 20
        check(f"{name}: GPU-Operator = Matrix (< 1e-12) und freier Operator = CPU (< 1e-12); {t_gpu * 1e3:.2f} ms GPU gegen "
              f"{t_cpu * 1e3:.2f} ms CPU je Anwendung, {g.n_dof} FHG, GPU-Speicher {gpu.speicher_mb} MB",
              f1 < 1e-12 and f2 < 1e-12, f"Matrix {f1:.1e}, CPU {f2:.1e}")


def test_pcg_gpu():
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - PCG-GPU uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.fcm.operator_gpu import OperatorGpu
    from volumen3d.linalg.pcg import jacobi_diagonale, pcg
    from volumen3d.tests.test_operator import _lame
    from volumen3d.tests.test_pcg import _lame_mit_druck
    pr = _lame_mit_druck(_lame(p=2, h=25.0))
    pr.aufbauen()
    n = pr.gitter.n_dof
    C = pr.zwaenge.C
    z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    diag = jacobi_diagonale(z, C, pr.K_rand)
    F = pr.rechte_seite({})
    b = np.asarray(C.T @ F[:n]).ravel()
    cpu = Operator(z, C=C, K_rand=pr.K_rand)
    gpu = OperatorGpu(z, C=C, K_rand=pr.K_rand)
    t = time.perf_counter()
    e_cpu = pcg(cpu.frei_anwenden, b, 1.0 / diag, tol=1e-10)
    t_cpu = time.perf_counter() - t
    t = time.perf_counter()
    e_gpu = pcg(gpu.frei_anwenden, cupy.asarray(b), cupy.asarray(1.0 / diag), tol=1e-10)
    cupy.cuda.Stream.null.synchronize()
    t_gpu = time.perf_counter() - t
    x_gpu = cupy.asnumpy(e_gpu.x)
    f = np.abs(x_gpu - e_cpu.x).max() / np.abs(e_cpu.x).max()
    check(f"PCG auf der GPU (Lame h 25 p 2): Loesung wie CPU (< 1e-8), {e_gpu.iterationen} gegen {e_cpu.iterationen} Iterationen, "
          f"{t_gpu:.1f} s GPU gegen {t_cpu:.1f} s CPU", e_gpu.konvergiert and f < 1e-8, f"{f:.1e}")


def test_gross_gpu():
    """Kirsch h 10 p 3 verfeinert: Operator-Zeit GPU gegen CPU bei 229 608 Freiheitsgraden (Messung)."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - grosse Messung uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.fcm.operator_gpu import OperatorGpu
    from volumen3d.tests.test_operator import _kirsch
    pr = _kirsch(p=3, h=10.0, verfeinert=True)
    z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    cpu, gpu = Operator(z), OperatorGpu(z)
    x = np.random.default_rng(2).standard_normal(pr.gitter.n_dof)
    d_x = cupy.asarray(x)
    v_cpu = cpu.anwenden(x)
    v_gpu = gpu.anwenden_np(x)
    f = np.abs(v_gpu - v_cpu).max() / np.abs(v_cpu).max()
    cupy.cuda.Stream.null.synchronize()
    t = time.perf_counter()
    for _ in range(20):
        gpu.anwenden(d_x)
    cupy.cuda.Stream.null.synchronize()
    t_gpu = (time.perf_counter() - t) / 20
    t = time.perf_counter()
    for _ in range(10):
        cpu.anwenden(x)
    t_cpu = (time.perf_counter() - t) / 10
    check(f"Kirsch h 10 p 3 verfeinert ({pr.gitter.n_dof} FHG): GPU = CPU (< 1e-12); {t_gpu * 1e3:.1f} ms GPU gegen {t_cpu * 1e3:.1f} ms CPU, "
          f"GPU-Speicher {gpu.speicher_mb} MB", f < 1e-12, f"{f:.1e}")


if __name__ == "__main__":
    sys.exit(lauf([test_operator_gpu, test_pcg_gpu, test_gross_gpu]))
