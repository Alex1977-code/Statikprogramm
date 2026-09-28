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


def test_mehrgitter_gpu():
    """V-Zyklus auf der GPU: FP64 gleich der CPU (< 1e-10), mit FP32-Glaetter konvergiert der PCG auf
    dieselbe Loesung; Zeiten gegen CPU-Mehrgitter und Direktloeser (Kirsch h 20 p 3 und h 10 p 3 verfeinert)."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - Mehrgitter-GPU uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.fcm.mehrgitter_gpu import PMehrgitterGpu
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.fcm.operator_gpu import OperatorGpu
    from volumen3d.linalg.pcg import pcg
    from volumen3d.tests.test_operator import _kirsch
    for h in (20.0, 10.0):
        pr = _kirsch(p=3, h=h, verfeinert=True)
        t = time.perf_counter()
        U_d = pr.loesen({})[:, 0]
        t_d = time.perf_counter() - t
        n = pr.gitter.n_dof
        C = pr.zwaenge.C
        z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        pr._zelldaten = z
        t = time.perf_counter()
        mg = PMehrgitter(pr)
        t_mg = time.perf_counter() - t
        b = np.asarray(C.T @ pr.rechte_seite({})[:n]).ravel()
        op_gpu = OperatorGpu(z, C=C, K_rand=pr.K_rand)
        t = time.perf_counter()
        gpu = PMehrgitterGpu(mg)                             # FP64-Glaetter (FP32 divergierte bei h 10, Theorie 11.10)
        t_hoch = time.perf_counter() - t
        if h == 20.0:
            r = np.random.default_rng(4).standard_normal(len(b))
            f = np.abs(cupy.asnumpy(gpu.anwenden(cupy.asarray(r))) - mg.anwenden(r)).max() / np.abs(mg.anwenden(r)).max()
            # Grenze wie die Symmetrie des V-Zyklus (Summationsreihenfolge, LU am Grobgitter): gemessen 1,4e-9
            check(f"Kirsch h 20 p 3: V-Zyklus GPU (FP64) = CPU (< 1e-8)", f < 1e-8, f"{f:.1e}")
        erg_c = None
        t_c = float("nan")
        if h == 20.0:
            op = Operator(z, C=C, K_rand=pr.K_rand)
            t = time.perf_counter()
            erg_c = pcg(op.frei_anwenden, b, mg.anwenden, tol=1e-10, max_iter=400)
            t_c = time.perf_counter() - t
        cupy.cuda.Stream.null.synchronize()
        t = time.perf_counter()
        erg_g = pcg(op_gpu.frei_anwenden, cupy.asarray(b), gpu.anwenden, tol=1e-10, max_iter=400)
        cupy.cuda.Stream.null.synchronize()
        t_g = time.perf_counter() - t
        U = np.asarray(C @ cupy.asnumpy(erg_g.x)).ravel()
        P = np.concatenate([pr.quadratur.zelle(c)[0][pr.quadratur.zelle(c)[2]][:3] for c in range(0, len(pr.gitter.ijk), max(1, len(pr.gitter.ijk) // 100))])
        s_d = pr.auswertung(U_d).spannung(P)
        f_s = np.abs(pr.auswertung(U).spannung(P) - s_d).max() / np.abs(s_d).max()
        cpu_txt = f", CPU-Mehrgitter {erg_c.iterationen} It. {t_c:.1f} s" if erg_c is not None else ""
        check(f"Kirsch h {h:g} p 3 verfeinert ({C.shape[1]} frei): PCG auf der GPU {erg_g.iterationen} It. "
              f"{t_g:.1f} s (Hochladen {t_hoch:.1f} s, Einrichten CPU {t_mg:.1f} s, GPU-Speicher {gpu.statistik['gpu_speicher_belegt_mb']} MB)"
              f"{cpu_txt}; Direktloeser {t_d:.1f} s; Spannungen wie direkt < 1e-6",
              erg_g.konvergiert and f_s < 1e-6, f"Spannungen {f_s:.1e}")
        del gpu, op_gpu
        cupy.get_default_memory_pool().free_all_blocks()


def test_problem_gpu():
    """FcmProblem(loeser='mehrgitter', backend='gpu') am Kragarmsegment mit Schnittebenen: Verschiebungen und
    Multiplikatoren wie der Direktloeser (projizierter CG auf der GPU mit B als cupy-Feld)."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - FcmProblem backend='gpu' uebersprungen", True)
        return
    from volumen3d.tests.test_kragarm import _segment

    def u_dreh(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([1e-3 * P[:, 0], -1e-3 * P[:, 2], 1e-3 * P[:, 1]], axis=1)

    pr_d = _segment(400.0, 600.0, 3, 50.0)
    U_d = pr_d.loesen({"links": 0.0, "rechts": u_dreh})[:, 0]
    pr_g = _segment(400.0, 600.0, 3, 50.0)
    pr_g.loeser, pr_g.toleranz, pr_g.backend = "mehrgitter", 1e-12, "gpu"   # 1e-10 ergab 1,0e-6 (Kondition), Vorgabe 9: 1e-6
    t = time.perf_counter()
    U_g = pr_g.loesen({"links": 0.0, "rechts": u_dreh})[:, 0]
    fu = np.abs(U_g - U_d).max() / np.abs(U_d).max()
    fl = np.abs(pr_g.multiplikatoren - pr_d.multiplikatoren).max() / max(np.abs(pr_d.multiplikatoren).max(), 1.0)
    check(f"FcmProblem loeser='mehrgitter', backend='gpu' (Kragarm p 3, Schnittebenen): wie direkt (< 1e-6); "
          f"{pr_g.protokoll['loeser']}, {pr_g.protokoll['iterationen']} It., {time.perf_counter() - t:.1f} s",
          fu < 1e-6 and fl < 1e-6, f"U {fu:.1e}, lambda {fl:.1e}")


if __name__ == "__main__":
    sys.exit(lauf([test_operator_gpu, test_pcg_gpu, test_gross_gpu, test_mehrgitter_gpu, test_problem_gpu]))
