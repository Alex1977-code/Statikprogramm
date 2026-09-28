"""p-Mehrgitter als Vorkonditionierer (Teilprojekt 4, Vorgabe 8.3, Entwurf 4d).

Die hierarchische Basis ist geschachtelt: der Raum vom Grad p-1 besteht aus den Moden, deren drei
1D-Indizes <= p-1 sind. Der Uebergang zwischen den Graden ist darum eine Injektion (Auswahl von
Moden), der Galerkin-Grobgitteroperator der Teilblock der Zellmatrizen (keine neue Integration),
und die Zwaenge sind geschachtelt: ein Meister vom Grad d traegt nur zu Sklaven vom Grad <= d bei
(Spur und Fortsetzung eines Polynoms vom Grad d haben Grad d). Deshalb werden die groben Zwaenge
nicht neu gebaut, sondern aus den feinen abgeleitet: C_grob = P3^T C_fein P~ mit P~ = Auswahl der
freien feinen Koordinaten, deren Mode im groben Raum liegt. Die Schachtelung wird beim Aufbau
geprueft (C_fein P~ hat auf Moden ausserhalb des groben Raums keine Eintraege); damit gilt
A_grob = P~^T A_fein P~ exakt (test_mehrgitter vergleicht zusaetzlich mit unabhaengig gebauten
groben Zwaengen).

Glaetter: additiver Schwarz ueber Zellbloecke (Vorgabe 8.3, Gegenmassnahme 2) mit Chebyshev-
Beschleunigung (Saad, Alg. 12.1) auf dem Spektrum [lambda_max/alpha, lambda_max] von M^-1 A,
lambda_max per Potenzmethode; Jacobi als Alternative. Grobgitter p = 1: Direktloeser, die
Mittelwertzwaenge der Schnittebenen als Sattelpunkt. Der V-Zyklus ist symmetrisch (Vor- und
Nachglaetter mit demselben Fehlerpolynom) und damit als Vorkonditionierer im CG zulaessig.
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

try:
    import numba
    _NUMBA = True
except ImportError:                                            # pragma: no cover - CI ohne numba
    numba = None
    _NUMBA = False


def _teilraum_indizes(p_fein: int, p_grob: int) -> np.ndarray:
    """Feiner lokaler Modenindex je grobem lokalen Mode (gleiche Indizes a, b, c)."""
    abc_f = modenklassen(p_fein)["abc"]
    abc_g = modenklassen(p_grob)["abc"]
    lage = {tuple(int(x) for x in k): i for i, k in enumerate(abc_f)}
    return np.array([lage[tuple(int(x) for x in k)] for k in abc_g], int)


def _kron3(M: sp.spmatrix) -> sp.csr_matrix:
    return sp.kron(M, sp.eye(3, format="csr"), format="csr")


if _NUMBA:
    @numba.njit(parallel=True, cache=True)
    def _teilmatrizen_nb(indptr, indices, data, S, s):          # pragma: no cover - numba
        """A[S_k, S_k] fuer k Bloecke gleicher Groesse s (S (k, s) sortiert) aus CSR, parallel ueber
        die Bloecke (jeder Block schreibt nur in seinen eigenen Speicher)."""
        k = S.shape[0]
        B = np.zeros((k, s, s))
        for b in numba.prange(k):
            for a in range(s):
                zeile = S[b, a]
                for idx in range(indptr[zeile], indptr[zeile + 1]):
                    col = indices[idx]
                    lo, hi = 0, s
                    while lo < hi:                                # binaere Suche in S[b]
                        mid = (lo + hi) // 2
                        if S[b, mid] < col:
                            lo = mid + 1
                        else:
                            hi = mid
                    if lo < s and S[b, lo] == col:
                        B[b, a, lo] = data[idx]
        return B


    @numba.njit(cache=True)
    def _chol_inv(A, aus):                                      # pragma: no cover - numba
        """Inverse einer symmetrisch positiv definiten Matrix ueber Cholesky, ohne LAPACK:
        A = L L^T, W = L^-1, A^-1 = W^T W (exakt symmetrisch). Gibt False bei Pivot <= 0 zurueck."""
        s = A.shape[0]
        L = np.zeros((s, s))
        for j in range(s):
            summe = A[j, j]
            for k in range(j):
                summe -= L[j, k] * L[j, k]
            if summe <= 0.0:
                return False
            L[j, j] = np.sqrt(summe)
            for i in range(j + 1, s):
                t = A[i, j]
                for k in range(j):
                    t -= L[i, k] * L[j, k]
                L[i, j] = t / L[j, j]
        W = np.zeros((s, s))                                     # W = L^-1 (untere Dreiecksmatrix)
        for j in range(s):
            W[j, j] = 1.0 / L[j, j]
            for i in range(j + 1, s):
                t = 0.0
                for k in range(j, i):
                    t -= L[i, k] * W[k, j]
                W[i, j] = t / L[i, i]
        for i in range(s):                                       # A^-1 = W^T W
            for j in range(i, s):
                t = 0.0
                for k in range(j, s):
                    t += W[k, i] * W[k, j]
                aus[i, j] = t
                aus[j, i] = t
        return True

    @numba.njit(parallel=True, cache=True)
    def _inv_stapel_nb(B):                                      # pragma: no cover - numba
        """Inversen eines Stapels (k, s, s) parallel ueber die Bloecke. Keine LAPACK-Aufrufe aus den
        Threads: OpenBLAS ist fuer mehr als 24 gleichzeitige Aufrufer nicht gebaut und ueberschrieb
        dabei Speicher (28.09.2026: Indexfeld zerstoert, 'NUM_THREADS exceeded'). Nicht positiv
        definite Bloecke (sollte nicht vorkommen) werden mit 1e-12 der Spur verschoben."""
        aus = np.empty_like(B)
        ok = np.ones(B.shape[0], np.bool_)
        for k in numba.prange(B.shape[0]):
            if not _chol_inv(B[k], aus[k]):
                s = B.shape[1]
                spur = 0.0
                for i in range(s):
                    spur += B[k, i, i]
                C = B[k].copy()
                for i in range(s):
                    C[i, i] += 1e-12 * spur
                ok[k] = _chol_inv(C, aus[k])
        return aus, ok


def _teilmatrizen(A: sp.csr_matrix, S: np.ndarray, indizes: tuple | None = None) -> np.ndarray:
    """``indizes``: (indptr, indices) schon als int64 - einmal umgewandelt statt je Blockgruppe
    (Kirsch h 10 p 3: 57 Gruppen, 3,0 s nur fuer astype, 28.09.2026)."""
    if _NUMBA:
        ip, ix = indizes if indizes is not None else (A.indptr.astype(np.int64), A.indices.astype(np.int64))
        return _teilmatrizen_nb(ip, ix, A.data, S.astype(np.int64), S.shape[1])
    return np.stack([A[s_][:, s_].toarray() for s_ in S])


def _inv_stapel(B: np.ndarray) -> np.ndarray:
    """Blockinversen, symmetrisiert: die LU-Inverse eines symmetrischen Blocks ist nur bis auf
    Kondition x Rundung symmetrisch, und der V-Zyklus war dadurch um 1e-9 unsymmetrisch (28.09.2026).
    Mit numba parallel ueber die Bloecke - die Inversion war 90 von 147 s Einrichtzeit am Kirsch-
    Modell h 10 p 3 (4732 Bloecke, einzeln und einfaedig)."""
    if _NUMBA:
        X, ok = _inv_stapel_nb(np.ascontiguousarray(B))
        if not ok.all():
            raise ValueError(f"Schwarz-Glaetter: {int((~ok).sum())} Zellbloecke nicht positiv definit")
        return X
    X = np.linalg.inv(B)
    return 0.5 * (X + np.swapaxes(X, 1, 2))


class ZellSchwarz:
    """Additiver Schwarz-Glaetter ueber Zellbloecke (Vorgabe 8.3, Gegenmassnahme 2).

    Warum: mit Jacobi bleiben Moden schwach gestuetzter Schnittzellen (Werkstoffanteil der
    beteiligten Zellen ~0, auf dem Nitsche-Rand) bei lambda ~ 1e-5 von D^-1 A liegen - weder der
    Glaetter noch das Grobgitter p = 1 (nur Eckmoden) erreichen sie (Patch h 20 p 2: 210 von 2469
    Eigenwerten des V-Zyklus-vorkonditionierten Operators unter 0,01, 1327 CG-Iterationen). Je
    Zelle wird der Block A[S,S] der freien Koordinaten, die die Zelle beruehrt, exakt geloest.
    Bloecke gleicher Groesse liegen gestapelt (Einrichten: numba-Auszug aus der CSR-Matrix und
    eine gestapelte Inversion je Groesse; Anwenden: einsum + bincount statt Schleife ueber Zellen -
    Kirsch h 20 p 3: Einrichten 49 s -> siehe Theorie 11.10, Anwenden 19 -> 13 ms)."""

    def __init__(self, ebene: "Ebene", A: sp.csr_matrix) -> None:
        z = ebene.zelldaten
        C = ebene.C.tocsr()
        A = A.tocsr()
        A.sort_indices()
        gruppen: dict[int, list[np.ndarray]] = {}
        # beruehrte freie Koordinaten je Zelle: Spalten der Zeilen von C zu den Zellfreiheitsgraden
        Cz = C[z.dofs.ravel()]
        n3 = z.dofs.shape[1]
        for c in range(len(z.gitter.ijk)):
            a, b = Cz.indptr[c * n3], Cz.indptr[(c + 1) * n3]
            if a == b:
                continue
            S = np.unique(Cz.indices[a:b])
            gruppen.setdefault(len(S), []).append(S)
        self.gruppen: list[tuple[np.ndarray, np.ndarray]] = []
        indizes = (A.indptr.astype(np.int64), A.indices.astype(np.int64))
        for s, liste in sorted(gruppen.items()):
            I = np.ascontiguousarray(np.array(liste, dtype=np.int64))
            B = _teilmatrizen(A, I, indizes)
            self.gruppen.append((I, _inv_stapel(B)))
        self.n = int(C.shape[1])
        self.speicher_mb = round(sum(Bi.nbytes for _, Bi in self.gruppen) / 1e6, 1)

    def anwenden(self, r: np.ndarray) -> np.ndarray:
        z = np.zeros(self.n)
        for I, Binv in self.gruppen:
            beitrag = np.einsum("kab,kb->ka", Binv, r[I])
            z += np.bincount(I.ravel(), weights=beitrag.ravel(), minlength=self.n)
        return z


class Ebene:
    """Eine p-Ebene: Gitter (bzw. Kopie mit eigener Nummerierung), Zwangsmatrix, Zelldaten,
    Operator, Jacobi-Diagonale."""

    def __init__(self, p: int, gitter, C: sp.csr_matrix, moden_frei: np.ndarray, zelldaten: Zelldaten,
                 K_rand: sp.spmatrix | None, diag: np.ndarray | None = None) -> None:
        self.p = p
        self.gitter = gitter
        self.C = C.tocsr()
        self.moden_frei = np.asarray(moden_frei, int)            # Modennummer je freier Koordinate
        self.zelldaten = zelldaten
        self.K_rand = K_rand
        self.operator = Operator(zelldaten, C=self.C, K_rand=K_rand)
        self.n_frei = int(self.C.shape[1])
        self.diag = diag if diag is not None else jacobi_diagonale(zelldaten, self.C, K_rand)
        self.lambda_max = 0.0
        self.P: sp.csr_matrix | None = None            # Injektion freie Koordinaten dieser Ebene -> feinere Ebene
        self.B: np.ndarray | None = None               # Mittelwertzwaenge auf dieser Ebene
        self.direkt: Direktloeser | None = None
        self.vork = None
        self.schwarz: ZellSchwarz | None = None

    def A(self, x: np.ndarray) -> np.ndarray:
        return self.operator.frei_anwenden(x)

    def matrix(self) -> sp.csr_matrix:
        """Assemblierte freie Matrix C^T (K + K_rand) C (fuer Glaetterbloecke und Grobgitter)."""
        K = self.zelldaten.matrix()
        if self.K_rand is not None:
            K = K + self.K_rand
        return (self.C.T @ K @ self.C).tocsr()


class PMehrgitter:
    """V-Zyklus ueber die Polynomgrade p, p-1, ..., 1; ``anwenden(r)`` ist die Vorkonditionierung.
    Glaetter: 'schwarz' (Zellbloecke, Standard) oder 'jacobi', jeweils mit Chebyshev-Beschleunigung.

    Standard Grad 5 auf [lambda_max/16, lambda_max]: am schwierigsten Fall (Kirsch h 10 p 3, Versatz
    0,6, GPU) gemessen Grad 3/alpha 8: 129 Iterationen 14,6 s, Grad 5/alpha 8: 92 / 16,7 s, Grad
    5/alpha 16: 86 / 15,0 s, Grad 8/alpha 30: 58 / 16,4 s (28.09.2026). Die Zeit haengt kaum am Grad,
    die Iterationszahl schon; Grad 5/alpha 16 haelt die Vorgabe (unter 100) ohne Zeitverlust."""

    def __init__(self, problem, glaetter_grad: int = 5, alpha: float = 16.0, potenz_schritte: int = 15,
                 glaetter: str = "schwarz", lambda_sicherheit: float = 1.1, grob_verschiebung: float = 1e-10) -> None:
        t0 = time.perf_counter()
        zeiten: dict[str, float] = {}
        pr = problem
        if pr.K is None:
            pr.aufbauen()
        g = pr.gitter
        p = int(g.p)
        self.glaetter_grad = int(glaetter_grad)
        self.alpha = float(alpha)
        zd_fein = getattr(pr, "_zelldaten", None) or Zelldaten(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        # feinste Ebene mit den Zwaengen des Problems selbst: dieselben freien Koordinaten wie pr.loesen
        self.ebenen: list[Ebene] = [Ebene(p, g, pr.zwaenge.C, pr.zwaenge.moden_frei, zd_fein, pr.K_rand,
                                          getattr(pr, "_diagonale", None))]
        fein = self.ebenen[0]
        t = time.perf_counter()
        for pk in range(p - 1, 0, -1):
            g_k = copy.copy(g)
            g_k.moden_nummerieren(pk)                      # weist neue Felder zu, das Original bleibt
            sub = _teilraum_indizes(fein.p, pk)
            zd_k = Zelldaten.teilraum(fein.zelldaten, g_k, sub)
            # Injektion der Moden: je Zelle grober lokaler Mode j <-> feiner lokaler Mode sub[j]
            paare = np.unique(np.stack([fein.gitter.zell_moden[:, sub].ravel(), g_k.zell_moden.ravel()], axis=1), axis=0)
            grob_von_fein = np.full(fein.gitter.n_moden, -1, int)
            grob_von_fein[paare[:, 0]] = paare[:, 1]
            P_moden = sp.csr_matrix((np.ones(len(paare)), (paare[:, 0], paare[:, 1])), shape=(fein.gitter.n_moden, g_k.n_moden))
            P3 = _kron3(P_moden)
            # freie grobe Koordinaten = freie feine, deren Mode im groben Raum liegt (Schachtelung)
            maske = grob_von_fein[fein.moden_frei] >= 0
            spalten_f = np.flatnonzero(maske)
            moden_frei_k = grob_von_fein[fein.moden_frei[spalten_f]]
            zeilen = (3 * spalten_f[:, None] + np.arange(3)).ravel()
            spalten = np.arange(3 * len(spalten_f))
            P_frei = sp.csr_matrix((np.ones(len(zeilen)), (zeilen, spalten)), shape=(fein.n_frei, 3 * len(spalten_f)))
            CP = (fein.C @ P_frei).tocsr()
            # Schachtelung pruefen: Zeilen von C_fein P~ ausserhalb des groben Raums muessen verschwinden
            ausserhalb = np.ones(fein.gitter.n_moden, bool)
            ausserhalb[paare[:, 0]] = False
            rest = CP[np.flatnonzero(np.repeat(ausserhalb, 3))]
            if rest.nnz and float(np.abs(rest.data).max()) > 1e-10 * max(float(np.abs(CP.data).max()), 1.0):
                raise ValueError(f"p-Mehrgitter: Zwaenge nicht geschachtelt (Grad {fein.p} -> {pk}): "
                                 f"Eintrag {float(np.abs(rest.data).max()):.2e} auf Moden ausserhalb des groben Raums")
            C_k = (P3.T @ CP).tocsr()
            C_k.eliminate_zeros()
            K_rand_k = (P3.T @ fein.K_rand @ P3).tocsr() if fein.K_rand is not None and fein.K_rand.nnz else None
            eb = Ebene(pk, g_k, C_k, moden_frei_k, zd_k, K_rand_k)
            eb.P = P_frei
            self.ebenen.append(eb)
            fein = eb
        zeiten["ebenen"] = time.perf_counter() - t
        # Mittelwertzwaenge der Schnittebenen (B x = 0 im projizierten CG): auf jede Ebene injiziert; ohne sie
        # waere A auf dem Grobgitter singulaer (Starrkoerperbewegungen in der Ebene), und der Direktloeser
        # lieferte Zahlen um 1e12 (Kragarmsegment 'schnitt': 2000 Iterationen ohne Konvergenz, 28.09.2026)
        B = np.asarray(pr._B @ pr.zwaenge.C) if getattr(pr, "n_zwaenge", 0) else None
        for eb in self.ebenen:
            if B is not None and eb.P is not None:
                B = np.asarray(B @ eb.P)
            eb.B = B
        # Grobgitter p = 1 direkt, mit den Mittelwertzwaengen als Sattelpunkt
        t = time.perf_counter()
        grob = self.ebenen[-1]
        A1 = grob.matrix()
        # Kleine Verschiebung delta = 1e-10 max diag: ein singulaeres Grobgitter (Kirsch-Modell: u_z frei,
        # keine Schnittebene) faktorisierte Pardiso mit still gestoerten Pivots, die Korrektur bekam
        # Nullraumanteile der Groesse 1/Pivot, und der PCG stagnierte je nach Schnittlage (Versatz 0,2:
        # 500 Iterationen ohne Konvergenz, 28.09.2026). Mit delta bleibt der Nullraumanteil r_0/delta,
        # und r_0 ist fuer konsistente Systeme Rundung; fuer die uebrigen Moden (lambda >> delta) aendert
        # sich die Korrektur nicht messbar.
        self.grob_delta = float(grob_verschiebung) * float(np.abs(A1.diagonal()).max())
        A1s = (A1 + self.grob_delta * sp.eye(A1.shape[0], format="csr")).tocsr()
        self.n_zwaenge = 0 if grob.B is None else int(grob.B.shape[0])
        if self.n_zwaenge:
            B1 = sp.csr_matrix(grob.B)
            A1s = sp.bmat([[A1s, B1.T], [B1, sp.csr_matrix((self.n_zwaenge, self.n_zwaenge))]], format="csr")
        grob.direkt = Direktloeser(A1s)
        # Singularitaet erkennen: fuer Zufallsproben X liefert die Loesung von A1s Y = A1 X den
        # Nullraumanteil nicht zurueck (A1 X_0 = 0); X - Y ist ein Schritt inverser Iteration auf den
        # Nullraum, ein zweiter Schritt drueckt die uebrigen Moden auf (delta/lambda)^2.
        N1 = A1.shape[0]
        X = np.random.default_rng(1).standard_normal((N1, 6))

        def grob_loesen(R):
            rhs = A1 @ R
            if self.n_zwaenge:
                rhs = np.concatenate([rhs, grob.B @ R], axis=0)
            return grob.direkt.loesen(rhs)[:N1]

        R1 = X - grob_loesen(X)
        self.grob_residuum = float(np.linalg.norm(R1[:, 0]) / np.linalg.norm(X[:, 0]))
        R2 = R1 - grob_loesen(R1)
        A1 = A1s
        zeiten["grobgitter"] = time.perf_counter() - t
        # Nullraum auf die feinste Ebene injizieren und dort am Operator bestaetigen. Ohne ihn blaehte der
        # Vorkonditionierer den Nullraumanteil auf (r_0/delta), der ueber Rundung ins Residuum
        # zurueckwirkte: Kirsch h 10 p 3 (u_z frei) erreichte 1e-8 und sprang wieder auf 1e-6, 147 bis 243
        # Iterationen je nach Einstellung und Summationsreihenfolge (28.09.2026). Nur bestaetigte echte
        # Nullvektoren werden herausprojiziert - ein fast singulaerer, aber echter Modus darf nicht fehlen.
        self.nullraum: np.ndarray | None = None
        if not self.n_zwaenge and self.grob_residuum > 1e-3:
            U_s, s_w, _ = np.linalg.svd(R2, full_matrices=False)
            kandidaten = U_s[:, s_w > 1e-2 * s_w.max()] if s_w.max() > 1e-3 else U_s[:, :0]
            for eb in reversed(self.ebenen[1:]):
                kandidaten = eb.P @ kandidaten
            fein = self.ebenen[0]
            if kandidaten.shape[1]:
                Q, _ = np.linalg.qr(kandidaten)
                x_ref = np.random.default_rng(2).standard_normal(fein.n_frei)
                bezug = np.linalg.norm(fein.A(x_ref)) / np.linalg.norm(x_ref)
                echt = [j for j in range(Q.shape[1]) if np.linalg.norm(fein.A(Q[:, j])) < 1e-6 * bezug]
                if echt:
                    self.nullraum = Q[:, echt]
        # Glaetter je Ebene: Schwarz-Zellbloecke aus der (nur hierfuer) assemblierten Matrix, sonst Jacobi
        t = time.perf_counter()
        self.glaetter = glaetter
        speicher = 0.0
        for k, eb in enumerate(self.ebenen[:-1]):
            if glaetter == "schwarz":
                # feinste Ebene: die reduzierte Matrix des Problems ist schon da (C^T (K + K_rand) C); beim
                # Direktloeser mit Schnittebenen ist sie der Sattelpunkt (andere Groesse) und wird neu gebildet
                A_eb = getattr(pr, "_K_red", None) if k == 0 else None
                if A_eb is None or A_eb.shape[0] != eb.n_frei:
                    A_eb = eb.matrix()
                eb.schwarz = ZellSchwarz(eb, A_eb)
                speicher += eb.schwarz.speicher_mb
                eb.vork = eb.schwarz.anwenden
            else:
                eb.vork = lambda r, d=eb.diag: r / d
        zeiten["glaetter"] = time.perf_counter() - t
        # lambda_max von M^-1 A je Ebene (Potenzmethode), 10 % Sicherheit
        t = time.perf_counter()
        rng = np.random.default_rng(0)
        for eb in self.ebenen[:-1]:
            v = rng.standard_normal(eb.n_frei)
            v /= np.linalg.norm(v)
            lam = 0.0
            for _ in range(potenz_schritte):
                w = eb.vork(eb.A(v))
                lam = float(np.linalg.norm(w))
                v = w / lam
            eb.lambda_max = float(lambda_sicherheit) * lam
        zeiten["lambda_max"] = time.perf_counter() - t
        warnungen = []
        k_null = 0 if self.nullraum is None else int(self.nullraum.shape[1])
        if k_null:
            warnungen.append(f"Operator singulaer: {k_null} freie Starrkoerperbewegung(en) ohne Lagerung (am feinen Operator "
                             f"bestaetigt); der Vorkonditionierer projiziert sie heraus, die Verschiebungen sind nur bis auf "
                             f"diese Bewegung bestimmt, die Spannungen nicht betroffen")
        elif self.grob_residuum > 1e-3:
            warnungen.append(f"Grobgitter nahezu singulaer (Probe weicht um {self.grob_residuum:.1e} ab), am feinen Operator "
                             f"nicht bestaetigt; Verschiebung {self.grob_delta:.1e}")
        self.statistik = {"ebenen": [int(e.p) for e in self.ebenen], "frei_je_ebene": [int(e.n_frei) for e in self.ebenen],
                          "lambda_max": [round(e.lambda_max, 4) for e in self.ebenen[:-1]], "glaetter": glaetter,
                          "glaetter_grad": self.glaetter_grad, "alpha": self.alpha, "grobgitter": grob.direkt.name,
                          "grobgitter_nnz": int(A1.nnz), "grobgitter_probe": self.grob_residuum, "grobgitter_delta": self.grob_delta,
                          "nullraum_dim": k_null,
                          "speicher_glaetter_mb": round(speicher, 1), "warnungen": warnungen,
                          "zeiten_s": {k: round(v, 2) for k, v in zeiten.items()},
                          "t_einrichten_s": round(time.perf_counter() - t0, 3)}

    # -- Glaetter ------------------------------------------------------------------------
    def _chebyshev(self, eb: Ebene, b: np.ndarray, x: np.ndarray) -> np.ndarray:
        """Chebyshev vom Grad k auf [lambda_max/alpha, lambda_max] mit dem Glaetter M (Saad, Alg. 12.1)."""
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
            if i < self.glaetter_grad - 1:
                r = r - alpha * eb.A(p)                    # letztes Residuum wird nicht gebraucht
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
        r = np.asarray(r, float)
        N = self.nullraum
        if N is None:
            return self._zyklus(0, r)
        # symmetrisch projiziert: z = Pi M Pi r mit Pi = I - N N^T (N orthonormal)
        r = r - N @ (N.T @ r)
        z = self._zyklus(0, r)
        return z - N @ (N.T @ z)


__all__ = ["PMehrgitter", "Ebene", "ZellSchwarz"]
