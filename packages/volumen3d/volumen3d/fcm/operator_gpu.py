"""Matrixfreier Operator auf der GPU (CuPy, Teilprojekt 3 Aufgabe 6, Vorgabe 9).

Dieselben Zelldaten wie auf der CPU (fcm/operator.py): ein Block je Zelle laedt u_e in den
gemeinsamen Speicher, jeder Thread bildet eine Zeile von K_e u_e - gelesen wird K_e spaltenweise
(K_e ist symmetrisch, K[b*n3 + a] fuer feste b ueber die Threads a ist zusammenhaengend), das
Ergebnis geht in den Puffer (Zellen x 3m); das Einsammeln je Freiheitsgrad ueber die Inzidenz ist
der zweite Kern. Zwangsmatrix C und Nitsche-Matrix K_rand als cupyx-CSR. FP64 durchgehend.
"""
from __future__ import annotations

import numpy as np

try:
    import cupy
    import cupyx.scipy.sparse as cusp
    _CUPY = True
except ImportError:                                            # pragma: no cover - ohne GPU
    cupy = None
    cusp = None
    _CUPY = False

_QUELLE = r"""
extern "C" __global__
void zellkern(const double* __restrict__ u, const int* __restrict__ dofs, const int n3,
              const long long* __restrict__ zellen, const double* __restrict__ skala,
              const double* __restrict__ K, const long long K_schritt, const int n_zellen,
              double* __restrict__ puffer)
{
    extern __shared__ double ue[];
    const int i = blockIdx.x;
    if (i >= n_zellen) return;
    const long long c = zellen[i];
    const int* d = dofs + c * n3;
    for (int a = threadIdx.x; a < n3; a += blockDim.x) ue[a] = u[d[a]];
    __syncthreads();
    const double* Ke = K + (long long)i * K_schritt;
    const double s = skala[i];
    for (int a = threadIdx.x; a < n3; a += blockDim.x) {
        double acc = 0.0;
        for (int b = 0; b < n3; ++b) acc += Ke[(long long)b * n3 + a] * ue[b];
        puffer[c * n3 + a] = s * acc;
    }
}

extern "C" __global__
void einsammeln(const double* __restrict__ puffer, const long long* __restrict__ zeiger,
                const long long* __restrict__ zelle, const long long* __restrict__ lokal,
                const int n3, const int n, double* __restrict__ v)
{
    const int d = blockIdx.x * blockDim.x + threadIdx.x;
    if (d >= n) return;
    double acc = 0.0;
    for (long long j = zeiger[d]; j < zeiger[d + 1]; ++j) acc += puffer[zelle[j] * n3 + lokal[j]];
    v[d] = acc;
}
"""


def verfuegbar() -> bool:
    if not _CUPY:
        return False
    try:
        return int(cupy.cuda.runtime.getDeviceCount()) > 0
    except Exception:                                          # pragma: no cover - Treiberfehler
        return False


class OperatorGpu:
    """v = K u auf der GPU; mit C und K_rand auch A x = C^T (K + K_rand) C x. Ein- und Ausgaben
    sind cupy-Felder (``anwenden``/``frei_anwenden``) oder numpy (``*_np``)."""

    def __init__(self, zelldaten, C=None, K_rand=None) -> None:
        if not verfuegbar():
            raise RuntimeError("keine GPU/CuPy verfuegbar")
        z = zelldaten
        self.z = z
        self.n = int(z.gitter.n_dof)
        self.n3 = 3 * z.m
        self.nz = len(z.gitter.ijk)
        self.d_dofs = cupy.asarray(z.dofs, dtype=cupy.int32)
        self.d_innen = cupy.asarray(z.innen, dtype=cupy.int64)
        self.d_skala_innen = cupy.asarray(z.skala_innen, dtype=cupy.float64)
        self.d_K_ref = cupy.asarray(z.K_ref, dtype=cupy.float64)
        self.d_cut = cupy.asarray(z.cut, dtype=cupy.int64)
        self.d_skala_cut = cupy.ones(len(z.cut), dtype=cupy.float64)
        self.d_K_cut = cupy.asarray(z.K_cut, dtype=cupy.float64)
        self.d_zeiger = cupy.asarray(z.inz_zeiger, dtype=cupy.int64)
        self.d_zelle = cupy.asarray(z.inz_zelle, dtype=cupy.int64)
        self.d_lokal = cupy.asarray(z.inz_lokal, dtype=cupy.int64)
        self.d_puffer = cupy.zeros(self.nz * self.n3, dtype=cupy.float64)
        modul = cupy.RawModule(code=_QUELLE)
        self._zellkern = modul.get_function("zellkern")
        self._einsammeln = modul.get_function("einsammeln")
        self._block = int(min(256, max(32, ((self.n3 + 31) // 32) * 32)))
        self._shared = self.n3 * 8
        self.C = cusp.csr_matrix(C.tocsr()) if C is not None else None
        self.CT = cusp.csr_matrix(C.T.tocsr()) if C is not None else None
        self.K_rand = cusp.csr_matrix(K_rand.tocsr()) if K_rand is not None and K_rand.nnz else None
        self.speicher_mb = round(cupy.get_default_memory_pool().used_bytes() / 1e6, 1)

    def anwenden(self, u):
        u = cupy.ascontiguousarray(u, dtype=cupy.float64)
        n3 = np.int32(self.n3)
        if len(self.z.innen):
            self._zellkern((len(self.z.innen),), (self._block,),
                           (u, self.d_dofs, n3, self.d_innen, self.d_skala_innen, self.d_K_ref, np.int64(0),
                            np.int32(len(self.z.innen)), self.d_puffer), shared_mem=self._shared)
        if len(self.z.cut):
            self._zellkern((len(self.z.cut),), (self._block,),
                           (u, self.d_dofs, n3, self.d_cut, self.d_skala_cut, self.d_K_cut, np.int64(self.n3 * self.n3),
                            np.int32(len(self.z.cut)), self.d_puffer), shared_mem=self._shared)
        v = cupy.empty(self.n, dtype=cupy.float64)
        bl = 256
        self._einsammeln(((self.n + bl - 1) // bl,), (bl,),
                         (self.d_puffer, self.d_zeiger, self.d_zelle, self.d_lokal, n3, np.int32(self.n), v))
        return v

    def voll_anwenden(self, u):
        v = self.anwenden(u)
        if self.K_rand is not None:
            v = v + self.K_rand @ u
        return v

    def frei_anwenden(self, x):
        if self.C is None:
            return self.voll_anwenden(x)
        return self.CT @ self.voll_anwenden(self.C @ x)

    def anwenden_np(self, u: np.ndarray) -> np.ndarray:
        return cupy.asnumpy(self.anwenden(cupy.asarray(u)))

    def frei_anwenden_np(self, x: np.ndarray) -> np.ndarray:
        return cupy.asnumpy(self.frei_anwenden(cupy.asarray(x)))


__all__ = ["OperatorGpu", "verfuegbar"]
