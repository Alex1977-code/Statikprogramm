"""Direktloeser fuer die CPU-Referenz und spaeter das Grobgitter: pypardiso, sonst SuperLU.

Mehrere rechte Seiten in einem Lauf (Vertrag: ``solve`` fuer alle Keys mit einer
Diskretisierung - nur die rechten Seiten aendern sich).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


class Direktloeser:
    def __init__(self, K: sp.spmatrix) -> None:
        self.n = K.shape[0]
        self._K = sp.csr_matrix(K)
        self.name = "superlu"
        self._lu = None
        try:
            import pypardiso  # noqa: F401
            self.name = "pardiso"
        except ImportError:
            self._lu = spla.splu(self._K.tocsc(), permc_spec="COLAMD")

    def loesen(self, F: np.ndarray) -> np.ndarray:
        """U (n, k) fuer F (n,) oder (n, k)."""
        F = np.asarray(F, float)
        einspaltig = F.ndim == 1
        F = F.reshape(self.n, -1)
        if self.name == "pardiso":
            import pypardiso
            U = np.asarray(pypardiso.spsolve(self._K, np.ascontiguousarray(F))).reshape(self.n, -1)
        else:
            U = self._lu.solve(F)
        return U[:, 0] if einspaltig else U


__all__ = ["Direktloeser"]
