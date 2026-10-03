"""Matrixfreier Operator auf der GPU (CuPy, Teilprojekt 3 Aufgabe 6, Vorgabe 9).

Dieselben Zelldaten wie auf der CPU (fcm/operator.py). Die Zellmatrizen liegen gepackt auf der GPU (nur das
untere Dreieck, fcm/bloecke_gpu.py): bei p 3 148 statt 295 KB je Schnittzelle, in FP64 und damit dieselbe
Rechnung; alle INSIDE-Zellen teilen sich die Referenzmatrix mit der Skala h_l/h_0. Das Einsammeln je
Freiheitsgrad laeuft ueber die Inzidenz. Zwangsmatrix C und Nitsche-Matrix K_rand als cupyx-CSR.
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

# Groesse der Teilstapel beim Packen und Hochladen der Zellmatrizen
_TEILSTAPEL_BYTES = 256e6

_PROBE: bool | None = None


def verfuegbar() -> bool:
    """GPU nutzbar: Geraet da und eine Kleinrechnung samt RawModule-Kompilat laeuft. Nur die Geraetezahl
    reichte nicht - ohne NVRTC (gepackte exe) brach jedes grosse Modell unter 'auto' mit CompileException ab,
    statt auf die CPU zurueckzufallen (Gutachten 28.09.2026). Das Ergebnis wird je Prozess gemerkt."""
    global _PROBE
    if _PROBE is not None:
        return _PROBE
    if not _CUPY:
        _PROBE = False
        return False
    try:
        if int(cupy.cuda.runtime.getDeviceCount()) <= 0:
            _PROBE = False
            return False
        a = cupy.arange(4, dtype=cupy.float64)
        kern = cupy.RawModule(code='extern "C" __global__ void probe(double* a) { a[threadIdx.x] *= 2.0; }').get_function("probe")
        kern((1,), (4,), (a,))
        _PROBE = abs(float((a * 1.0).sum()) - 12.0) < 1e-12
    except Exception:                                          # pragma: no cover - Treiber-, NVRTC-, cuBLAS-Fehler
        _PROBE = False
    return _PROBE


class OperatorGpu:
    """v = K u auf der GPU; mit C und K_rand auch A x = C^T (K + K_rand) C x. Ein- und Ausgaben
    sind cupy-Felder (``anwenden``/``frei_anwenden``) oder numpy (``*_np``)."""

    def __init__(self, zelldaten, C=None, K_rand=None) -> None:
        if not verfuegbar():
            raise RuntimeError("keine GPU/CuPy verfuegbar")
        from .bloecke_gpu import GepackteBloecke, dreieck
        z = zelldaten
        self.z = z
        self.n = int(z.gitter.n_dof)
        self.n3 = 3 * z.m
        self.nz = len(z.gitter.ijk)
        il, jl = dreieck(self.n3)
        je = len(il)
        # Matrixspeicher: Referenzmatrix, danach die Schnittzellen; in Teilstapeln gepackt und hochgeladen, damit
        # der Hauptspeicher keine zweite Kopie aller Zellmatrizen haelt
        X = cupy.empty(je * (1 + len(z.cut)), dtype=cupy.float64)
        X[:je] = cupy.asarray(np.ascontiguousarray(z.K_ref[il, jl]))
        schritt = max(1, int(_TEILSTAPEL_BYTES // (8 * je)))
        for a0 in range(0, len(z.cut), schritt):
            a1 = min(len(z.cut), a0 + schritt)
            X[je * (1 + a0):je * (1 + a1)] = cupy.asarray(np.ascontiguousarray(z.K_cut[a0:a1][:, il, jl])).ravel()
        zellen = np.concatenate([z.innen, z.cut]).astype(np.int64)
        start_x = np.concatenate([np.zeros(len(z.innen), np.int64), je * (1 + np.arange(len(z.cut), dtype=np.int64))])
        skala = np.concatenate([z.skala_innen, np.ones(len(z.cut))])
        self.bloecke = GepackteBloecke(self.n, np.full(len(zellen), self.n3), z.dofs[zellen].ravel(), X, start_x, skala)
        self.C = cusp.csr_matrix(C.tocsr()) if C is not None else None
        self.CT = cusp.csr_matrix(C.T.tocsr()) if C is not None else None
        self.K_rand = cusp.csr_matrix(K_rand.tocsr()) if K_rand is not None and K_rand.nnz else None
        duenn = sum(int(M.data.nbytes + M.indices.nbytes + M.indptr.nbytes) for M in (self.C, self.CT, self.K_rand) if M is not None)
        self.speicher_mb = round(self.bloecke.speicher_mb + duenn / 1e6, 1)

    def anwenden(self, u):
        return self.bloecke.anwenden(u)

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
