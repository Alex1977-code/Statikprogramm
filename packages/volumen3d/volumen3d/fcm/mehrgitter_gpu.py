"""p-Mehrgitter auf der GPU (Teilprojekt 4 Aufgabe 5, Vorgabe 9).

Spiegelt ein auf der CPU eingerichtetes ``PMehrgitter`` (Ebenen, Zwaenge, Glaetterbloecke,
lambda_max) auf die GPU: Operator je Ebene als ``OperatorGpu``, Schwarz-Bloecke gestapelt je Groesse
(batched matmul, Scatter-Add), Injektion als cupyx-CSR, Chebyshev in cupy. Das Grobgitter p = 1
bleibt auf der CPU (klein; eine Hin- und Rueckuebertragung je V-Zyklus).

Genauigkeit (Vorgabe 9): Operator und aeussere CG-Iteration in FP64; die Glaetterbloecke wahlweise
in FP32 (``fp32=True``) - sie sind der groesste Speicher- und Bandbreitenposten (Kirsch h 10 p 3:
900 MB in FP64), und ein Glaetter muss nur naeherungsweise wirken. Warum die GPU: auf der CPU liest
jeder V-Zyklus die Blockinversen zwoelfmal aus dem Hauptspeicher (Theorie 11.10).
"""
from __future__ import annotations

import time

import numpy as np

from .operator_gpu import OperatorGpu, verfuegbar

try:
    import cupy
    import cupyx
    import cupyx.scipy.sparse as cusp
    _CUPY = True
except ImportError:                                            # pragma: no cover - ohne GPU
    cupy = None
    _CUPY = False


class _EbeneGpu:
    def __init__(self, eb, fp32: bool) -> None:
        self.p = eb.p
        self.n_frei = eb.n_frei
        self.op = OperatorGpu(eb.zelldaten, C=eb.C, K_rand=eb.K_rand)
        self.lambda_max = float(eb.lambda_max)
        dtyp = cupy.float32 if fp32 else cupy.float64
        self.fp32 = fp32
        self.gruppen = []
        if eb.schwarz is not None:
            for I, Binv in eb.schwarz.gruppen:
                self.gruppen.append((cupy.asarray(I), cupy.asarray(I.ravel()), cupy.asarray(Binv, dtype=dtyp)))
        self.diag = cupy.asarray(eb.diag)

    def A(self, x):
        return self.op.frei_anwenden(x)

    def vork(self, r):
        if not self.gruppen:
            return r / self.diag
        z = cupy.zeros(self.n_frei, dtype=cupy.float64)
        for I, I_flach, Binv in self.gruppen:
            rI = r[I]
            if self.fp32:
                rI = rI.astype(cupy.float32)
            beitrag = cupy.matmul(Binv, rI[:, :, None])[:, :, 0]
            cupyx.scatter_add(z, I_flach, beitrag.ravel().astype(cupy.float64))
        return z


class PMehrgitterGpu:
    """V-Zyklus auf der GPU aus einem eingerichteten CPU-``PMehrgitter``; ``anwenden(r)`` nimmt und
    liefert cupy-Felder (FP64)."""

    def __init__(self, mg, fp32: bool = False) -> None:
        if not verfuegbar():
            raise RuntimeError("keine GPU/CuPy verfuegbar")
        t0 = time.perf_counter()
        self.mg = mg
        self.glaetter_grad = mg.glaetter_grad
        self.alpha = mg.alpha
        self.n_zwaenge = mg.n_zwaenge
        self.ebenen = [_EbeneGpu(eb, fp32) for eb in mg.ebenen[:-1]]
        self.grob = mg.ebenen[-1]                           # Direktloeser auf der CPU
        # Injektionen Ebene k+1 -> Ebene k (einschliesslich der zum Grobgitter), einmal hochgeladen
        self.injektion = [(cusp.csr_matrix(mg.ebenen[k + 1].P), cusp.csr_matrix(mg.ebenen[k + 1].P.T.tocsr()))
                          for k in range(len(mg.ebenen) - 1)]
        self.nullraum = cupy.asarray(mg.nullraum) if mg.nullraum is not None else None
        self.fp32 = fp32
        cupy.cuda.Stream.null.synchronize()
        frei, gesamt = cupy.cuda.Device().mem_info
        self.statistik = {"fp32_glaetter": fp32, "t_hochladen_s": round(time.perf_counter() - t0, 2),
                          "gpu_speicher_belegt_mb": round(cupy.get_default_memory_pool().used_bytes() / 1e6, 1),
                          "gpu_frei_mb": round(frei / 1e6, 1), "gpu_gesamt_mb": round(gesamt / 1e6, 1)}

    def _chebyshev(self, eb: _EbeneGpu, b, x):
        lmax = eb.lambda_max
        lmin = lmax / self.alpha
        d = 0.5 * (lmax + lmin)
        c = 0.5 * (lmax - lmin)
        r = b - eb.A(x)
        alpha = 0.0
        p = cupy.zeros_like(x)
        for i in range(self.glaetter_grad):
            z = eb.vork(r)
            if i == 0:
                p = z.copy()
                alpha = 1.0 / d
            else:
                beta = 0.5 * (c * alpha) ** 2 if i == 1 else (0.5 * c * alpha) ** 2
                alpha = 1.0 / (d - beta / alpha)
                p = z + beta * p
            x = x + alpha * p
            if i < self.glaetter_grad - 1:
                r = r - alpha * eb.A(p)
        return x

    def _grob(self, b):
        b_cpu = cupy.asnumpy(b)
        if self.n_zwaenge:
            y = self.grob.direkt.loesen(np.concatenate([b_cpu, np.zeros(self.n_zwaenge)]))[:len(b_cpu)]
        else:
            y = self.grob.direkt.loesen(b_cpu)
        return cupy.asarray(y)

    def _zyklus(self, k: int, b):
        if k == len(self.ebenen):
            return self._grob(b)
        eb = self.ebenen[k]
        x = self._chebyshev(eb, b, cupy.zeros_like(b))
        r = b - eb.A(x)
        P, PT = self.injektion[k]                            # Ebene k+1 -> Ebene k
        xc = self._zyklus(k + 1, PT @ r)
        x = x + P @ xc
        return self._chebyshev(eb, b, x)

    def anwenden(self, r):
        r = cupy.asarray(r, dtype=cupy.float64)
        if self.nullraum is None:
            return self._zyklus(0, r)
        N = self.nullraum                                     # symmetrisch projiziert wie auf der CPU
        r = r - N @ (N.T @ r)
        z = self._zyklus(0, r)
        return z - N @ (N.T @ z)


__all__ = ["PMehrgitterGpu"]
