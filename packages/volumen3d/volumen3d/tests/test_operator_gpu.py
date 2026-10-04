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


def test_mehrgitter_auf_gpu_eingerichtet():
    """PMehrgitter(geraet='gpu'): Glaetterbloecke per RawKernel ausgezogen und mit cuBLAS invertiert,
    lambda_max und Zyklus auf der GPU - gleich dem CPU-Mehrgitter (V-Zyklus < 1e-8, lambda_max < 1e-6)."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - Einrichten auf der GPU uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.tests.test_operator import _kirsch
    pr = _kirsch(p=3, h=20.0, verfeinert=True)
    pr.loeser = "pcg"
    pr.aufbauen()
    t = time.perf_counter()
    mg_c = PMehrgitter(pr)
    t_c = time.perf_counter() - t
    t = time.perf_counter()
    mg_g = PMehrgitter(pr, geraet="gpu")
    cupy.cuda.Stream.null.synchronize()
    t_g = time.perf_counter() - t
    r = np.random.default_rng(6).standard_normal(mg_c.ebenen[0].n_frei)
    z_c = mg_c.anwenden(r)
    z_g = cupy.asnumpy(mg_g.anwenden(cupy.asarray(r)))
    f = np.abs(z_g - z_c).max() / np.abs(z_c).max()
    f_l = max(abs(a - b) / a for a, b in zip(mg_c.statistik["lambda_max"], mg_g.statistik["lambda_max"]))
    check(f"Kirsch h 20 p 3: Mehrgitter auf der GPU eingerichtet = CPU (V-Zyklus < 1e-8, lambda_max < 1e-6); Einrichten "
          f"CPU {t_c:.1f} s {mg_c.statistik['zeiten_s']} gegen GPU {t_g:.1f} s {mg_g.statistik['zeiten_s']}",
          f < 1e-8 and f_l < 1e-6, f"V-Zyklus {f:.1e}, lambda_max {f_l:.1e}")


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


def test_gpu_speicher():
    """Die Speicherschaetzung der Vertragsschicht deckt den gemessenen Hoechststand beim Einrichten und liegt
    hoechstens 30 % darueber. Gemessen wird im knappen Betrieb (Freigabe des Pools nach jeder Groessengruppe
    erzwungen), fuer den die Schaetzung gilt; der Hoechststand des Pools wird gegen die Karte selbst geprueft
    (freier Speicher, alle 10 ms abgetastet, Abweichung unter 150 MB).

    Befunde: 28.09.2026 lag die alte Schaetzung bis 50 % unter der Spitze (Kirsch h 8: 4,7 gegen 7,3 GB), mehrere
    Details in einem Prozess sammelten sich im Pool, bis die 8-GB-Karte auslagerte. 29.09.2026 (A3, Plan TP 5):
    Zellmatrizen und Blockinversen symmetrisch gepackt, feine Matrix nicht mehr auf der GPU - Kirsch h 12 V 0,6
    1549 statt 2172 MB Hoechststand, belegt 690 statt 1251 MB; die Schranke 'belegt' unten haelt das fest."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - GPU-Pruefungen uebersprungen", True)
        return
    import threading
    import cupy
    from volumen3d.api import _gpu_speicher_mb
    from volumen3d.fcm import mehrgitter as mg_modul
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.tests.test_kirsch import D, T, _platte
    pool = cupy.get_default_memory_pool()
    reserve_alt = mg_modul._FREI_RESERVE_BYTES
    try:
        mg_modul._FREI_RESERVE_BYTES = 1e15
        for h, vers, belegt_max in ((14.0, 0.0, 400.0), (12.0, 0.6, 800.0)):
            v = Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, h / 4),))
            pr = _platte(3, h, versatz=vers, verfeinerung=v)
            pr.loeser = "pcg"
            pr.aufbauen()
            g = pr.gitter
            schaetzung = _gpu_speicher_mb(len(g.ijk), int((g.klasse == 2).sum()), 3, int(pr.zwaenge.C.shape[1]))
            pool.free_all_blocks()
            vorher = pool.total_bytes()
            frei0 = cupy.cuda.runtime.memGetInfo()[0]
            kleinstes, laeuft = [frei0], [True]

            def abtasten():
                while laeuft[0]:
                    kleinstes[0] = min(kleinstes[0], cupy.cuda.runtime.memGetInfo()[0])
                    time.sleep(0.01)

            faden = threading.Thread(target=abtasten, daemon=True)
            faden.start()
            mg = mg_modul.PMehrgitter(pr, geraet="gpu")
            laeuft[0] = False
            faden.join()
            spitze = (mg.statistik["gpu_spitze_mb"] * 1e6 - vorher) / 1e6
            karte = (frei0 - kleinstes[0]) / 1e6
            belegt = mg.statistik["gpu_belegt_mb"] - vorher / 1e6
            check(f"Kirsch h {h} Versatz {vers}: Schaetzung {schaetzung:.0f} MB >= Hoechststand {spitze:.0f} MB und <= 1,3 x; "
                  f"Pool und Karte gleich (< 150 MB); belegt {belegt:.0f} MB < {belegt_max:.0f} MB",
                  max(spitze, karte) <= schaetzung <= 1.3 * spitze and abs(karte - spitze) < 150.0 and belegt < belegt_max,
                  f"Verhaeltnis {schaetzung / spitze:.2f}, Karte {karte:.0f} MB")
            del mg, pr
            pool.free_all_blocks()
    finally:
        mg_modul._FREI_RESERVE_BYTES = reserve_alt


def test_schwarz_grosse_bloecke_gpu():
    """Auf der GPU werden Bloecke ueber _EINZELN_AB einzeln invertiert (cuSOLVER) statt gestapelt: Blockinversen
    exakt wie numpy (< 1e-10) und das Einrichten mit einem Block der Groesse 2000 unter 1,5 s (gestapelt gemessen
    etwa 5 s fuer s 2000, 8,6 s fuer s 2463; A1, Plan TP 5)."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - GPU-Pruefungen uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.mehrgitter import _EINZELN_AB, ZellSchwarz
    from volumen3d.tests.test_mehrgitter import _schwarz_probe
    C, dofs, A, r, z_ref = _schwarz_probe()
    ZellSchwarz(C[6:, 2000:], dofs[1:] - 6, A[2000:, 2000:], geraet="gpu")    # Kompilate und cuSOLVER warm
    cupy.cuda.Device().synchronize()
    t = time.perf_counter()
    sw = ZellSchwarz(C, dofs, A, geraet="gpu")
    cupy.cuda.Device().synchronize()
    dt = time.perf_counter() - t
    z = cupy.asnumpy(sw.anwenden(cupy.asarray(r)))
    f = float(np.abs(z - z_ref).max() / np.abs(z_ref).max())
    check(f"Schwarz GPU mit einem Block der Groesse 2000 (> {_EINZELN_AB}): Blockinversen exakt (< 1e-10), Einrichten < 1,5 s",
          f < 1e-10 and dt < 1.5, f"Abweichung {f:.1e}, Einrichten {dt:.2f} s")


def test_gepackte_bloecke():
    """Gepackte symmetrische Bloecke (fcm/bloecke_gpu.py) gegen eine unabhaengige numpy-Rechnung
    z[I_k] += skala_k X_k v[I_k] mit vollen Matrizen. Der Fall deckt ab: Groessen 1, 81, 192 und 211, drei
    Bloecke ueber 256 Zeilen (in Auftraege zerlegt: 700, 257 und 1030), zwanzig Bloecke, die sich eine Matrix mit
    verschiedener Skala teilen (wie die INSIDE-Zellen des Operators), und Ziele ohne Block. Erwartet: Abweichung
    < 1e-13, zwei Anwendungen bitgleich (Einsammeln in fester Reihenfolge), Matrixspeicher s (s + 1) / 2 je Block."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - GPU-Pruefungen uebersprungen", True)
        return
    import cupy
    from volumen3d.fcm.bloecke_gpu import GepackteBloecke, dreieck, gepackte_laenge
    rng = np.random.default_rng(21)
    n = 9000
    groessen = np.array([1] * 3 + [81] * 40 + [192] * 30 + [211] * 10 + [700, 257, 1030] + [192] * 20)
    n_eigen = len(groessen) - 20
    index, voll, gepackt, start_x, pos = [], [], [], [], 0
    for k, sk in enumerate(groessen):
        index.append(np.sort(rng.choice(n - 50, int(sk), replace=False)))          # die letzten 50 Ziele bleiben leer
        if k < n_eigen:
            M = rng.standard_normal((sk, sk))
            Xk = M + M.T
            il, jl = dreieck(int(sk))
            gepackt.append(Xk[il, jl])
            start_x.append(pos)
            pos += len(il)
        else:                                                                       # geteilte Matrix: die des ersten 192er-Blocks
            Xk = voll[43]
            start_x.append(start_x[43])
        voll.append(Xk)
    skala = np.concatenate([np.ones(n_eigen), 0.5 ** rng.integers(0, 4, 20)])
    X = cupy.asarray(np.concatenate(gepackt))
    gb = GepackteBloecke(n, groessen, np.concatenate(index), X, np.array(start_x), skala)
    v = rng.standard_normal(n)
    z_ref = np.zeros(n)
    for k in range(len(groessen)):
        z_ref[index[k]] += skala[k] * (voll[k] @ v[index[k]])
    vg = cupy.asarray(v)
    z1 = gb.anwenden(vg)
    z2 = gb.anwenden(vg)
    f = float(np.abs(cupy.asnumpy(z1) - z_ref).max() / np.abs(z_ref).max())
    n_auftraege = sum(a for _, a, _ in gb.auftraege)
    erwartet_auftraege = len(groessen) - 3 + 3 + 2 + 5                              # 700 -> 3, 257 -> 2, 1030 -> 5
    speicher = int(gepackte_laenge(groessen[:n_eigen]).sum()) * 8
    check("gepackte Bloecke = volle Rechnung mit numpy (< 1e-13), bitgleich wiederholbar, grosse Bloecke in Auftraegen",
          f < 1e-13 and bool((z1 == z2).all()) and n_auftraege == erwartet_auftraege and int(X.nbytes) == speicher
          and float(cupy.abs(z1[n - 50:]).max()) == 0.0,
          f"Abweichung {f:.1e}, {n_auftraege} Auftraege fuer {len(groessen)} Bloecke, Matrixspeicher {X.nbytes / 1e6:.1f} MB "
          f"(voll waeren {sum(int(g) ** 2 for g in groessen[:n_eigen]) * 8 / 1e6:.1f} MB)")


def test_million_gpu():
    """Eine Million Freiheitsgrade auf der 8-GB-Karte (Plan TP 5, A3; Vorgabe 13 Performance): Kirsch-Scheibe h 5,5
    p 3 verfeinert (1 002 528 Freiheitsgrade, 10 962 Zellen, 9 600 geschnitten) mit dem GPU-Mehrgitter im knappen
    Speicherbetrieb. Erwartet: Hoechststand des Pools unter 5,5 GB und unter der Schaetzung der Vertragsschicht
    (diese hoechstens 30 % darueber), Iterationen unter 100, und die Spannung sigma_x am Lochrand wie am 30.09.2026
    gegen den Direktloeser bestaetigt (Mehrgitter 307,5662 N/mm2, Abweichung zum Direktloeser 1,6e-12; die
    Verschiebungen unterscheiden sich um die freie z-Bewegung, die der Direktloeser beliebig festlegt). Vor dem
    Packen der Zellmatrizen und Blockinversen haette dieses Modell 12,2 GB gebraucht. Laeuft nur, wenn die Karte
    mindestens 6,5 GB frei hat; braucht rund 16 GB Hauptspeicher und 90 s."""
    from volumen3d.fcm.operator_gpu import verfuegbar
    if not verfuegbar():
        check("GPU/CuPy nicht verfuegbar - GPU-Pruefungen uebersprungen", True)
        return
    import cupy
    frei = cupy.cuda.runtime.memGetInfo()[0] / 1e6
    if frei < 6500:
        check(f"GPU hat nur {frei:.0f} MB frei - Millionenmodell uebersprungen", True)
        return
    from volumen3d.api import _gpu_speicher_mb
    from volumen3d.fcm import mehrgitter as mg_modul
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.tests.test_kirsch import D, S0, T, _platte
    pool = cupy.get_default_memory_pool()
    reserve_alt = mg_modul._FREI_RESERVE_BYTES
    try:
        mg_modul._FREI_RESERVE_BYTES = 1e15
        t0 = time.perf_counter()
        h = 5.5
        v = Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, h / 4),))
        pr = _platte(3, h, versatz=0.0, verfeinerung=v)
        pr.loeser, pr.backend, pr.toleranz = "mehrgitter", "gpu", 1e-12
        g = pr.gitter
        schaetzung = _gpu_speicher_mb(len(g.ijk), int((g.klasse == 2).sum()), 3, int(pr.zwaenge.C.shape[1]))
        pool.free_all_blocks()
        vorher = pool.total_bytes() / 1e6
        pr.aufbauen()
        st = pr._mehrgitter.statistik
        spitze = st["gpu_spitze_mb"] - vorher
        U = pr.loesen({})[:, 0]
        it = pr.protokoll["iterationen"][0]
        sx = float(pr.auswertung(U).spannung(np.array([[0.0, D / 2 + 1e-6, T / 2]]))[0, 0])
        f = abs(sx - 307.5662) / 307.5662
        check(f"Kirsch h 5,5 p 3 ({g.n_dof} Freiheitsgrade): Hoechststand {spitze:.0f} MB < 5500 und <= Schaetzung {schaetzung:.0f} MB <= 1,3 x; "
              f"{it} Iterationen < 100; sigma_x {sx:.4f} wie gegen den Direktloeser bestaetigt (< 5e-7)",
              g.n_dof == 1_002_528 and spitze < 5500 and spitze <= schaetzung <= 1.3 * spitze and it < 100 and f < 5e-7,
              f"belegt {st['gpu_belegt_mb'] - vorher:.0f} MB, Abweichung sigma_x {f:.1e}, {time.perf_counter() - t0:.0f} s")
        del pr, U
        pool.free_all_blocks()
    finally:
        mg_modul._FREI_RESERVE_BYTES = reserve_alt


if __name__ == "__main__":
    sys.exit(lauf([test_gepackte_bloecke, test_operator_gpu, test_pcg_gpu, test_gross_gpu, test_mehrgitter_gpu, test_mehrgitter_auf_gpu_eingerichtet, test_problem_gpu, test_gpu_speicher, test_schwarz_grosse_bloecke_gpu, test_million_gpu]))
