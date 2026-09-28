"""p-Mehrgitter als Vorkonditionierer (Teilprojekt 4, Vorgabe 8.3, Entwurf 4d).

Die hierarchische Basis ist geschachtelt: der Raum vom Grad p-1 besteht aus den Moden, deren drei
1D-Indizes <= p-1 sind. Der Uebergang zwischen den Graden ist darum eine Injektion (Auswahl von
Moden), der Galerkin-Grobgitteroperator der Teilblock der Zellmatrizen (keine neue Integration),
und die Zwaenge sind geschachtelt: ein Meister vom Grad d traegt nur zu Sklaven vom Grad <= d bei
(Spur und Fortsetzung eines Polynoms vom Grad d haben Grad d). Also C_fein P~ = P C_grob, und die
freien groben Moden sind eine Teilmenge der freien feinen Moden; P~ ist die Injektion zwischen
den freien Koordinaten und A_grob = P~^T A_fein P~ gilt exakt (test_mehrgitter prueft es).

Glaetter: Chebyshev-Jacobi (Adams, Brezina, Hu, Tuminaro 2003) auf dem Spektrum
[lambda_max/alpha, lambda_max] von D^-1 A, lambda_max je Ebene per Potenzmethode. Grobgitter
p = 1: Direktloeser auf der assemblierten Matrix. Der V-Zyklus ist symmetrisch (gleicher Glaetter
vor und nach dem Grobgitter) und damit als Vorkonditionierer im CG zulaessig.
"""
from __future__ import annotations

import copy
import time

import numpy as np
import scipy.sparse as sp

from ..linalg.direkt import Direktloeser
from ..linalg.pcg import jacobi_diagonale
from .basis import modenklassen
from .operator import Operator, Zelldaten
from .zwaenge import Zwaenge


def _teilraum_indizes(p_fein: int, p_grob: int) -> np.ndarray:
    """Feiner lokaler Modenindex je grobem lokalen Mode (gleiche Indizes a, b, c)."""
    abc_f = modenklassen(p_fein)["abc"]
    abc_g = modenklassen(p_grob)["abc"]
    lage = {tuple(int(x) for x in k): i for i, k in enumerate(abc_f)}
    return np.array([lage[tuple(int(x) for x in k)] for k in abc_g], int)


class Ebene:
    """Eine p-Ebene: Gitterkopie mit eigener Nummerierung, Zwaenge, Zelldaten, Operator, Jacobi."""

    def __init__(self, p: int, gitter, aggregation, zelldaten: Zelldaten, K_rand: sp.spmatrix | None) -> None:
        self.p = p
        self.gitter = gitter
        self.zwaenge = Zwaenge(gitter, aggregation)
        self.C = self.zwaenge.C
        self.zelldaten = zelldaten
        self.K_rand = K_rand
        self.operator = Operator(zelldaten, C=self.C, K_rand=K_rand)
        self.n_frei = int(self.C.shape[1])
        self.diag = jacobi_diagonale(zelldaten, self.C, K_rand)
        self.lambda_max = 0.0
        self.P: sp.csr_matrix | None = None            # Injektion freie Koordinaten dieser Ebene -> feinere Ebene
        self.B: np.ndarray | None = None               # Mittelwertzwaenge auf dieser Ebene
        self.direkt: Direktloeser | None = None
        self.vork = None

    def A(self, x: np.ndarray) -> np.ndarray:
        return self.operator.frei_anwenden(x)


class ZellSchwarz:
    """Additiver Schwarz-Glaetter ueber Zellbloecke (Vorgabe 8.3, Gegenmassnahme 2).

    Warum: mit Jacobi bleiben Moden schwach gestuetzter Schnittzellen (Werkstoffanteil der
    beteiligten Zellen ~0, auf dem Nitsche-Rand) bei lambda ~ 1e-5 von D^-1 A liegen - weder der
    Glaetter noch das Grobgitter p = 1 (nur Eckmoden) erreichen sie (Patch h 20 p 2: 210 von 2469
    Eigenwerten des V-Zyklus-vorkonditionierten Operators unter 0,01, 1327 CG-Iterationen). Je
    Zelle wird der Block A[S,S] der freien Koordinaten, die die Zelle beruehrt, exakt geloest;
    diese lokalen Cluster verschwinden damit aus dem Spektrum. Die Ueberlappung regelt nicht eine
    Daempfung, sondern die Chebyshev-Beschleunigung um den Glaetter herum."""

    def __init__(self, ebene: "Ebene", A: sp.csr_matrix) -> None:
        z = ebene.zelldaten
        C = ebene.C
        A = A.tocsr()
        self.bloecke: list[tuple[np.ndarray, np.ndarray]] = []
        for c in range(len(z.gitter.ijk)):
            Ce = C[z.dofs[c]]
            if Ce.nnz == 0:
                continue
            S = np.unique(Ce.indices)
            B = A[S][:, S].toarray()
            self.bloecke.append((S, np.linalg.inv(B)))
        self.n = int(C.shape[1])
        self.speicher_mb = round(sum(Bi.nbytes for _, Bi in self.bloecke) / 1e6, 1)

    def anwenden(self, r: np.ndarray) -> np.ndarray:
        z = np.zeros(self.n)
        for S, Bi in self.bloecke:
            z[S] += Bi @ r[S]
        return z


class PMehrgitter:
    """V-Zyklus ueber die Polynomgrade p, p-1, ..., 1; ``anwenden(r)`` ist die Vorkonditionierung.
    Glaetter: 'schwarz' (Zellbloecke, Standard) oder 'jacobi', jeweils mit Chebyshev-Beschleunigung."""

    def __init__(self, problem, glaetter_grad: int = 3, alpha: float = 8.0, potenz_schritte: int = 15,
                 glaetter: str = "schwarz") -> None:
        t0 = time.perf_counter()
        pr = problem
        if pr.K is None:
            pr.aufbauen()
        g = pr.gitter
        p = int(g.p)
        self.glaetter_grad = int(glaetter_grad)
        self.alpha = float(alpha)
        zd_fein = getattr(pr, "_zelldaten", None) or Zelldaten(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        self.ebenen: list[Ebene] = [Ebene(p, g, pr.aggregation, zd_fein, pr.K_rand)]
        # dieselben freien Koordinaten wie das Problem: die feinste Ebene nutzt pr.zwaenge (gleiche Nummerierung)
        fein = self.ebenen[0]
        for pk in range(p - 1, 0, -1):
            g_k = copy.copy(g)
            g_k.moden_nummerieren(pk)
            ag_k = None
            if pr.aggregation is not None:
                ag_k = copy.copy(pr.aggregation)
                ag_k.gitter = g_k
            sub = _teilraum_indizes(fein.p, pk)
            zd_k = Zelldaten.teilraum(fein.zelldaten, g_k, sub)
            # Injektion der Moden: je Zelle grober lokaler Mode j <-> feiner lokaler Mode sub[j]
            paare = np.unique(np.stack([fein.gitter.zell_moden[:, sub].ravel(), g_k.zell_moden.ravel()], axis=1), axis=0)
            P_moden = sp.csr_matrix((np.ones(len(paare)), (paare[:, 0], paare[:, 1])), shape=(fein.gitter.n_moden, g_k.n_moden))
            P3 = sp.kron(P_moden, sp.eye(3, format="csr"), format="csr")
            K_rand_k = (P3.T @ fein.K_rand @ P3).tocsr() if fein.K_rand is not None and fein.K_rand.nnz else None
            eb = Ebene(pk, g_k, ag_k, zd_k, K_rand_k)
            # Injektion der freien Koordinaten: grobe freie Mode -> feine freie Mode (muss frei sein)
            frei_g = eb.zwaenge.moden_frei
            frei_f_von_g = np.asarray(P_moden[:, frei_g].argmax(axis=0)).ravel()      # feine Modennummer je grober freier Mode
            spalte_f = fein.zwaenge.spalte_von_mode[frei_f_von_g]
            gebunden_f = set(fein.zwaenge.roh)
            fehl = [int(m) for m in frei_f_von_g if int(m) in gebunden_f]
            if fehl:
                raise ValueError(f"p-Mehrgitter: {len(fehl)} grobe freie Moden sind fein gebunden (Zwaenge nicht geschachtelt), z. B. Mode {fehl[0]}")
            zeilen = (3 * spalte_f[:, None] + np.arange(3)).ravel()
            spalten = (3 * np.arange(len(frei_g))[:, None] + np.arange(3)).ravel()
            eb.P = sp.csr_matrix((np.ones(len(zeilen)), (zeilen, spalten)), shape=(fein.n_frei, eb.n_frei))
            self.ebenen.append(eb)
            fein = eb
        # Mittelwertzwaenge der Schnittebenen (B x = 0 im projizierten CG): auf jede Ebene injiziert; ohne sie
        # waere A auf dem Grobgitter singulaer (Starrkoerperbewegungen in der Ebene), und der Direktloeser
        # lieferte Zahlen um 1e12 (Kragarmsegment 'schnitt': 2000 Iterationen ohne Konvergenz, 28.09.2026)
        B = np.asarray(pr._B @ pr.zwaenge.C) if getattr(pr, "n_zwaenge", 0) else None
        for eb in self.ebenen:
            eb.B = B
            if B is not None and eb.P is not None:
                B = np.asarray(B @ eb.P)
                eb.B = B
        # Grobgitter p = 1 direkt, mit den Mittelwertzwaengen als Sattelpunkt
        grob = self.ebenen[-1]
        A1 = (grob.C.T @ (grob.zelldaten.matrix() + (grob.K_rand if grob.K_rand is not None else 0)) @ grob.C).tocsr()
        self.n_zwaenge = 0 if grob.B is None else int(grob.B.shape[0])
        if self.n_zwaenge:
            B1 = sp.csr_matrix(grob.B)
            A1 = sp.bmat([[A1, B1.T], [B1, sp.csr_matrix((self.n_zwaenge, self.n_zwaenge))]], format="csr")
        grob.direkt = Direktloeser(A1)
        # Glaetter je Ebene: Schwarz-Zellbloecke aus der (nur hierfuer) assemblierten Matrix, sonst Jacobi
        self.glaetter = glaetter
        speicher = 0.0
        for eb in self.ebenen[:-1]:
            if glaetter == "schwarz":
                A_eb = (eb.C.T @ (eb.zelldaten.matrix() + (eb.K_rand if eb.K_rand is not None else 0)) @ eb.C).tocsr()
                eb.schwarz = ZellSchwarz(eb, A_eb)
                speicher += eb.schwarz.speicher_mb
                eb.vork = eb.schwarz.anwenden
            else:
                eb.vork = lambda r, d=eb.diag: r / d
        # lambda_max von M^-1 A je Ebene (Potenzmethode), 10 % Sicherheit
        rng = np.random.default_rng(0)
        for eb in self.ebenen[:-1]:
            v = rng.standard_normal(eb.n_frei)
            v /= np.linalg.norm(v)
            lam = 0.0
            for _ in range(potenz_schritte):
                w = eb.vork(eb.A(v))
                lam = float(np.linalg.norm(w))
                v = w / lam
            eb.lambda_max = 1.1 * lam
        self.statistik = {"ebenen": [int(e.p) for e in self.ebenen], "frei_je_ebene": [int(e.n_frei) for e in self.ebenen],
                          "lambda_max": [round(e.lambda_max, 4) for e in self.ebenen[:-1]], "glaetter": glaetter,
                          "glaetter_grad": self.glaetter_grad, "alpha": self.alpha, "grobgitter": grob.direkt.name,
                          "grobgitter_nnz": int(A1.nnz), "speicher_glaetter_mb": round(speicher, 1),
                          "t_einrichten_s": round(time.perf_counter() - t0, 3)}

    # -- Glaetter ------------------------------------------------------------------------
    def _chebyshev(self, eb: Ebene, b: np.ndarray, x: np.ndarray) -> np.ndarray:
        """Chebyshev-Jacobi vom Grad k auf [lambda_max/alpha, lambda_max] (Adams u. a. 2003)."""
        lmax = eb.lambda_max
        lmin = lmax / self.alpha
        d = 0.5 * (lmax + lmin)
        c = 0.5 * (lmax - lmin)
        r = b - eb.A(x)
        alpha = 0.0
        p = np.zeros_like(x)
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
            r = r - alpha * eb.A(p)
        return x

    # -- Zyklus --------------------------------------------------------------------------
    def _zyklus(self, k: int, b: np.ndarray) -> np.ndarray:
        eb = self.ebenen[k]
        if eb.direkt is not None:
            if self.n_zwaenge:
                return eb.direkt.loesen(np.concatenate([b, np.zeros(self.n_zwaenge)]))[:len(b)]
            return eb.direkt.loesen(b)
        x = self._chebyshev(eb, b, np.zeros_like(b))
        r = b - eb.A(x)
        grob = self.ebenen[k + 1]
        rc = grob.P.T @ r
        xc = self._zyklus(k + 1, rc)
        x = x + grob.P @ xc
        return self._chebyshev(eb, b, x)

    def anwenden(self, r: np.ndarray) -> np.ndarray:
        return self._zyklus(0, np.asarray(r, float))


__all__ = ["PMehrgitter", "Ebene"]
