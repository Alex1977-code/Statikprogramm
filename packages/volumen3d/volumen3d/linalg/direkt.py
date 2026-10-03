"""Direktloeser fuer die CPU-Referenz und spaeter das Grobgitter: pypardiso, sonst SuperLU.

Mehrere rechte Seiten in einem Lauf (Vertrag: ``solve`` fuer alle Keys mit einer
Diskretisierung - nur die rechten Seiten aendern sich).
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla


# Nachiteration im SuperLU-Weg (Plan TP 5, O20, 03.10.2026): SuperLU mit COLAMD und ohne Schwellenpivotierung loest das schlecht konditionierte System des
# geneigten Plattenstreifens (30 Grad, p 3, 78 von 89 Zellen aggregiert) nur auf 1e-5 (Spannung); PARDISO, das selbst nachiteriert, auf 2,5e-8. Ohne pypardiso
# rechnet die CI. Der PARDISO-Weg bleibt unveraendert.
# Abbruchmass ist das komponentenweise Rueckwaertsfehlermass omega = max_i |r_i| / (|K| |U| + |F|)_i (Oettli-Prager, wie LAPACK xGERFS), nicht das normweise Residuum:
# am Streifen liegt dieses schon vor dem ersten Schritt bei 6e-13 und danach bei 4e-13 (der Boden seiner eigenen Auswertung), waehrend der Spannungsfehler von 1e-5 auf
# 1,6e-8 faellt; omega faellt dabei von 2,6e-7 auf 7e-14 und dann auf 7e-15 (Plan, Berichtigung der Regeln O20).
NACHITERATION_STANDARD = 3
NACHITERATION_TOLERANZ = 1e-14                 # omega, ab dem nicht weiter iteriert wird


class Direktloeser:
    """``nachiteration``: hoechste Zahl der Nachiteration-Schritte im SuperLU-Weg (Vorgabe ``NACHITERATION_STANDARD``, 0 schaltet sie ab). Das Grobgitter des
    Mehrgitters nimmt 0: es ist ein fester, symmetrischer Vorkonditionierer, und seine Nullraumerkennung haengt am Verhalten der einfachen Zerlegung."""

    def __init__(self, K: sp.spmatrix, nachiteration: int | None = None) -> None:
        self.n = K.shape[0]
        self._K = sp.csr_matrix(K)
        self.name = "superlu"
        self._lu = None
        self.nachiteration = NACHITERATION_STANDARD if nachiteration is None else int(nachiteration)
        self._K_abs: sp.csr_matrix | None = None                 # |K| mit denselben Indexfeldern, nur ein zweites Datenfeld (8 Byte je Eintrag)
        self.letzte_nachiteration: dict[str, float] = {"schritte": 0, "omega_vorher": 0.0, "omega_nachher": 0.0}
        try:
            import pypardiso  # noqa: F401
            self.name = "pardiso"
        except ImportError:
            self._lu = spla.splu(self._K.tocsc(), permc_spec="COLAMD")

    def rueckwaertsfehler(self, F: np.ndarray, U: np.ndarray) -> tuple[np.ndarray, float]:
        """(R, omega): Residuum R = F - K U und das komponentenweise Rueckwaertsfehlermass omega = max_i |r_i| / (|K| |U| + |F|)_i ueber alle rechten Seiten;
        Zeilen, in denen Nenner und Zaehler null sind (Zwangszeile ohne Last und ohne Verschiebung), zaehlen nicht."""
        if self._K_abs is None:
            K = self._K
            self._K_abs = sp.csr_matrix((np.abs(K.data), K.indices, K.indptr), shape=K.shape)
        R = F - self._K @ U
        nenner = self._K_abs @ np.abs(U) + np.abs(F)
        mit = nenner > 0.0
        return R, float((np.abs(R)[mit] / nenner[mit]).max()) if mit.any() else 0.0

    def _nachiterieren(self, F: np.ndarray, U: np.ndarray) -> np.ndarray:
        """Hoechstens ``nachiteration`` Schritte U += K^-1 (F - K U), solange omega ueber der Toleranz liegt. Ein Schritt, der omega nicht senkt, wird verworfen;
        senkt er es nicht mindestens auf die Haelfte, ist der Boden erreicht und es wird nicht weiter iteriert."""
        R, w = self.rueckwaertsfehler(F, U)
        vorher, schritte = w, 0
        while schritte < self.nachiteration and w > NACHITERATION_TOLERANZ:
            U_neu = U + self._lu.solve(R)
            R_neu, w_neu = self.rueckwaertsfehler(F, U_neu)
            if not w_neu < w:
                break
            U, R, schritte = U_neu, R_neu, schritte + 1
            boden = w_neu > 0.5 * w
            w = w_neu
            if boden:
                break
        self.letzte_nachiteration = {"schritte": schritte, "omega_vorher": vorher, "omega_nachher": w}
        return U

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
            if self.nachiteration > 0:
                U = self._nachiterieren(F, U)
        return U[:, 0] if einspaltig else U


__all__ = ["Direktloeser"]
