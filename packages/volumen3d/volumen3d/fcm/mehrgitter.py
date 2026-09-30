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


def _zell_bloecke(C: sp.csr_matrix, dofs: np.ndarray) -> dict[int, list[np.ndarray]]:
    """Je Zelle die beruehrten freien Koordinaten (Spalten der Zeilen von C zu den Zellfreiheits-
    graden), nach Blockgroesse gruppiert."""
    Cz = C.tocsr()[dofs.ravel()]
    n3 = dofs.shape[1]
    gruppen: dict[int, list[np.ndarray]] = {}
    for c in range(dofs.shape[0]):
        a, b = Cz.indptr[c * n3], Cz.indptr[(c + 1) * n3]
        if a == b:
            continue
        S = np.unique(Cz.indices[a:b])
        gruppen.setdefault(len(S), []).append(S)
    return gruppen


class ZellSchwarz:
    """Additiver Schwarz-Glaetter ueber Zellbloecke (Vorgabe 8.3, Gegenmassnahme 2).

    Warum: mit Jacobi bleiben Moden schwach gestuetzter Schnittzellen (Werkstoffanteil der
    beteiligten Zellen ~0, auf dem Nitsche-Rand) bei lambda ~ 1e-5 von D^-1 A liegen - weder der
    Glaetter noch das Grobgitter p = 1 (nur Eckmoden) erreichen sie (Patch h 20 p 2: 210 von 2469
    Eigenwerten des V-Zyklus-vorkonditionierten Operators unter 0,01, 1327 CG-Iterationen). Je
    Zelle wird der Block A[S,S] der freien Koordinaten, die die Zelle beruehrt, exakt geloest.
    Bloecke gleicher Groesse liegen gestapelt. ``geraet='cpu'``: numba-Auszug aus der CSR-Matrix,
    eigene Cholesky-Inversion, Anwenden mit einsum + bincount. ``geraet='gpu'``: Auszug auf der CPU in
    Teilstapeln, Inversion mit cuBLAS bzw. cuSOLVER, die Inversen liegen symmetrisch gepackt auf der GPU
    (fcm/bloecke_gpu.py, halber Speicher in FP64; Theorie 11.10)."""

    def __init__(self, C: sp.csr_matrix, dofs: np.ndarray, A: sp.csr_matrix, geraet: str = "cpu") -> None:
        A = A.tocsr()
        A.sort_indices()
        gruppen = _zell_bloecke(C, dofs)
        self.n = int(C.shape[1])
        self.geraet = geraet
        self.gruppen: list = []
        self.bloecke = None
        if geraet == "gpu":
            import cupy
            from .bloecke_gpu import GepackteBloecke, dreieck, gepackte_laenge
            reihen = sorted(gruppen.items())
            groessen = np.concatenate([np.full(len(liste), s, np.int64) for s, liste in reihen]) if reihen else np.zeros(0, np.int64)
            laengen = gepackte_laenge(groessen)
            start_x = np.concatenate([[0], np.cumsum(laengen)[:-1]]).astype(np.int64) if len(laengen) else np.zeros(0, np.int64)
            X = cupy.empty(int(laengen.sum()), dtype=cupy.float64)
            indizes = (A.indptr.astype(np.int64), A.indices.astype(np.int64))
            index, pos = [], 0
            for s, liste in reihen:
                I = np.ascontiguousarray(np.array(liste, dtype=np.int64))
                index.append(I.ravel())
                k = int(I.shape[0])
                il, jl = (cupy.asarray(f) for f in dreieck(s))
                # Teilstapel von hoechstens _TEILSTAPEL_BYTES: die gestapelte Inversion legt Kopien und
                # Arbeitsfelder an - ueber ganze Groessengruppen hielt der Speicherpool danach das Doppelte der
                # Bloecke (Kirsch h 9 p 3: 5,9 GB, davon 2,9 GB belegt), und bei h 8 lief die 8-GB-Karte ueber
                # (Auslagern, 1,5 s statt 0,13 s je Iteration, 28.09.2026). Ausgezogen wird auf der CPU: die feine
                # Matrix auf der GPU waere bei 1e6 Freiheitsgraden 3,4 bis 4,2 GB nur fuer den Auszug; der Weg
                # ueber die CPU kostet am Block h 14 p 3 0,64 statt 0,48 s (29.09.2026, A3 Plan TP 5)
                schritt = max(1, int(_TEILSTAPEL_BYTES // (8 * s * s)))
                for a in range(0, k, schritt):
                    b = min(k, a + schritt)
                    B = cupy.asarray(_teilmatrizen(A, I[a:b], indizes))
                    if s > _EINZELN_AB:
                        Xa = cupy.stack([cupy.linalg.inv(B[i]) for i in range(b - a)])
                    else:
                        Xa = cupy.linalg.inv(B)
                    del B
                    # cupy wirft bei singulaeren Bloecken nicht, sondern liefert inf/NaN (errstate 'ignore'); ohne
                    # Pruefung lief der PCG dann 1000 V-Zyklen und meldete 'Residuum nan' (Gutachten 28.09.2026)
                    if not bool(cupy.isfinite(Xa).all()):
                        raise ValueError(f"Schwarz-Glaetter (GPU): Zellbloecke der Groesse {s} nicht invertierbar")
                    # symmetrisiert und gepackt in einem Schritt: unteres Dreieck von (X + X^T) / 2
                    P = Xa[:, il, jl]
                    P += Xa[:, jl, il]
                    P *= 0.5
                    del Xa
                    X[pos:pos + P.size] = P.ravel()
                    pos += int(P.size)
                    del P
                # Je Groessengruppe andere Feldgroessen: der Pool haelt die freien Stuecke der letzten Gruppe fest.
                # Freigegeben wird nur, wenn der Speicher der Karte knapp wird - die Freigabe kostet Zeit (Kirsch
                # h 8 p 3, 33 Gruppen: Einrichten 7,3 statt 6,2 s) und senkt den Hoechststand von 3311 auf
                # 2689 MB (Block h 14: 2295 auf 2094 MB; 29.09.2026). Unter Windows meldet die Karte keinen
                # Mangel, sie lagert aus - darum vorher pruefen statt auf den Fehler zu warten.
                del il, jl
                _gpu_spitze_merken()
                if cupy.cuda.runtime.memGetInfo()[0] < _FREI_RESERVE_BYTES:
                    cupy.get_default_memory_pool().free_all_blocks()
            self.bloecke = GepackteBloecke(self.n, groessen, np.concatenate(index) if index else np.zeros(0, np.int64), X, start_x)
            self.groessen = groessen
            self.speicher_mb = round(int(X.nbytes) / 1e6, 1)
        else:
            indizes = (A.indptr.astype(np.int64), A.indices.astype(np.int64))
            for s, liste in sorted(gruppen.items()):
                I = np.ascontiguousarray(np.array(liste, dtype=np.int64))
                B = _teilmatrizen(A, I, indizes)
                if s > _EINZELN_AB:
                    # LAPACK aus dem Hauptfaden (mehrfaedig je Block); aus numba-Faeden zerstoerte es Speicher
                    X = np.linalg.inv(B)
                    if not np.all(np.isfinite(X)):
                        raise ValueError(f"Schwarz-Glaetter: Zellbloecke der Groesse {s} nicht invertierbar")
                    self.gruppen.append((I, 0.5 * (X + np.swapaxes(X, 1, 2))))
                else:
                    self.gruppen.append((I, _inv_stapel(B)))
            self.speicher_mb = round(sum(Bi.nbytes for _, Bi in self.gruppen) / 1e6, 1)

    def anwenden(self, r):
        if self.bloecke is not None:
            return self.bloecke.anwenden(r)
        z = np.zeros(self.n)
        for I, Binv in self.gruppen:
            beitrag = np.einsum("kab,kb->ka", Binv, r[I])
            z += np.bincount(I.ravel(), weights=beitrag.ravel(), minlength=self.n)
        return z


# Hoechststand des GPU-Speicherpools waehrend des Einrichtens. Der Pool gibt von selbst nichts zurueck, sein
# Gesamtstand vor jeder Freigabe ist darum der Hoechststand seit der letzten.
_GPU_SPITZE = [0]


def _gpu_spitze_merken() -> int:
    import cupy
    _GPU_SPITZE[0] = max(_GPU_SPITZE[0], int(cupy.get_default_memory_pool().total_bytes()))
    return _GPU_SPITZE[0]


# Unter diesem freien Speicher der Karte gibt der Glaetteraufbau den Pool nach jeder Groessengruppe frei
_FREI_RESERVE_BYTES = 2048e6

# Groesse der Teilstapel beim Auszug und der Inversion der Glaetterbloecke auf der GPU
_TEILSTAPEL_BYTES = 256e6

# Ab dieser Blockgroesse wird einzeln invertiert statt gestapelt. Die gestapelte Inversion (cuBLAS
# getrfBatched) ist fuer viele kleine Bloecke gebaut und waechst fuer grosse wie s^4 und schlechter:
# gemessen (RTX 3070, 29.09.2026) s 256, 20 Bloecke: gestapelt 0,014 s, einzeln 0,026 s; s 400, 4 Bloecke:
# 0,043 gegen 0,016 s; s 1350: 1,47 gegen 0,038 s; s 2463: 8,57 gegen 0,17 s. Am Block h 14 p 3 (Schwelle
# 0,4) kostete so ein einzelner Block 8,6 s von 19 s Glaetter-Einrichtung (A1, Plan TP 5). Auf der CPU gilt
# dasselbe fuer die numba-Cholesky je Block (ein Faden je Block): grosse Bloecke gehen an LAPACK im Hauptfaden.
_EINZELN_AB = 320

# Schwelle fuer den Singulaerwert eines Nullvektors nach zwei Schritten inverser Iteration und Zahl der
# Zufallsproben (siehe grob_nullkandidaten)
_NULL_SCHWELLE = 0.1
_NULL_PROBEN = 16


def grob_nullkandidaten(loesen, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Kandidaten fuer den Nullraum des Grobgitters: zwei Schritte inverser Iteration mit der verschobenen
    Zerlegung, loesen(R) = (A1 + delta I)^-1 A1 R, auf Zufallsproben X mit Eintraegen ~ N(0, 1).

    X - loesen(X) = delta (A1 + delta I)^-1 X: ein Nullvektor n bleibt mit Faktor 1 stehen, ein Modus mit
    Eigenwert lambda schrumpft um delta / (lambda + delta) je Schritt. Nach zwei Schritten ist R2 ~ N (N^T X),
    die Singulaerwerte der k Nullvektoren sind die der Gaussmatrix N^T X (k x m Proben), alle anderen Moden
    um (delta/lambda)^2 gedaempft. Mit m = 16 Proben liegt der kleinste dieser Singulaerwerte fuer k <= 6
    (ganz ungelagerter Koerper) im Mittel bei sqrt(16) - sqrt(k) >= 1,5, weit ueber der Schwelle 0,1; mit
    den frueheren 6 Proben war er fuer k = 6 mit rund 20 % Wahrscheinlichkeit darunter (Edelman,
    Gutachten 28.09.2026). Gemessen Kirsch p 3, h 10 bis 14, Versatz 0 und 0,6 (k = 1): Nullvektor 2,4 bis
    3,8, zweitgroesster Wert 5e-6 bis 4e-4 (28.09.2026). Mit Mittelwertzwaengen loest ``loesen`` den
    Sattelpunkt; ein Nullvektor, den die Zwaenge sperren (B n != 0), faellt dabei heraus (die Loesung trifft
    ihn exakt), nur freie Bewegungen im Kern von B bleiben stehen.

    Die fruehere Schwelle auf das Residuum einer einzelnen Probe (> 1e-3) hing am Zufall und an der Groesse:
    der Nullanteil eines Zufallsvektors ist |n^T x| / ||x|| ~ 1 / sqrt(N1); bei Kirsch h 12 und h 14 lag er bei
    9,8e-4 und 8,5e-4, der Nullraum blieb unerkannt, und der PCG divergierte nach 1,6e-8 wieder (Abbruch mit
    p^T A p < 0 bzw. 113 statt 51 Iterationen). Rueckgabe: Kandidaten (orthonormale Spalten), Singulaerwerte."""
    R1 = X - loesen(X)
    R2 = R1 - loesen(R1)
    U_s, s_w, _ = np.linalg.svd(R2, full_matrices=False)
    return U_s[:, s_w > _NULL_SCHWELLE], s_w


class Ebene:
    """Eine p-Ebene: Gitter (bzw. Kopie mit eigener Nummerierung), Zwangsmatrix C, assemblierte freie
    Matrix A = C^T (K + K_rand) C, Diagonale, Injektion P zur feineren Ebene, Freiheitsgradtabelle
    der Zellen (fuer die Glaetterbloecke) und der Operator: auf der feinsten Ebene matrixfrei, auf den
    groben Ebenen das Produkt mit A (die groben Matrizen sind Teilmatrizen der feinen, s. PMehrgitter)."""

    def __init__(self, p: int, gitter, C: sp.csr_matrix, moden_frei: np.ndarray, A: sp.csr_matrix,
                 operator=None) -> None:
        self.p = p
        self.gitter = gitter
        self.C = C.tocsr()
        self.moden_frei = np.asarray(moden_frei, int)            # Modennummer je freier Koordinate
        self.A_matrix = A.tocsr()
        self.n_frei = int(self.C.shape[1])
        self.diag = np.asarray(self.A_matrix.diagonal(), float)
        n3 = 3 * int(gitter.zell_moden.shape[1])
        self.dofs = np.ascontiguousarray((3 * gitter.zell_moden[:, :, None] + np.arange(3)).reshape(-1, n3), dtype=np.int64)
        self.operator = operator                                  # matrixfrei (feinste Ebene) oder None
        self.lambda_max = 0.0
        self.P: sp.csr_matrix | None = None            # Injektion freie Koordinaten dieser Ebene -> feinere Ebene
        self.B: np.ndarray | None = None               # Mittelwertzwaenge auf dieser Ebene
        self.direkt: Direktloeser | None = None
        self.vork = None
        self.schwarz: ZellSchwarz | None = None
        self.A_geraet = None                                      # Operator auf dem Rechengeraet
        self.P_geraet = None
        self.PT_geraet = None

    def A(self, x):
        if self.A_geraet is not None:
            return self.A_geraet(x)
        if self.operator is not None:
            return self.operator.frei_anwenden(x)
        return self.A_matrix @ x


class PMehrgitter:
    """V-Zyklus ueber die Polynomgrade p, p-1, ..., 1; ``anwenden(r)`` ist die Vorkonditionierung.
    Glaetter: 'schwarz' (Zellbloecke, Standard) oder 'jacobi', jeweils mit Chebyshev-Beschleunigung.
    ``geraet='gpu'``: Glaetterbloecke, Operatoren, lambda_max und V-Zyklus auf der GPU (``anwenden``
    nimmt und liefert cupy-Felder); nur das Grobgitter p = 1 bleibt auf der CPU.

    Standard Grad 5 auf [lambda_max/16, lambda_max]: am schwierigsten Fall (Kirsch h 10 p 3, Versatz
    0,6, GPU) gemessen Grad 3/alpha 8: 129 Iterationen 14,6 s, Grad 5/alpha 8: 92 / 16,7 s, Grad
    5/alpha 16: 86 / 15,0 s, Grad 8/alpha 30: 58 / 16,4 s (28.09.2026). Die Zeit haengt kaum am Grad,
    die Iterationszahl schon; Grad 5/alpha 16 haelt die Vorgabe (unter 100) ohne Zeitverlust."""

    def __init__(self, problem, glaetter_grad: int = 5, alpha: float = 16.0, potenz_schritte: int = 15,
                 glaetter: str = "schwarz", lambda_sicherheit: float = 1.1, grob_verschiebung: float = 1e-10,
                 geraet: str = "cpu") -> None:
        try:
            self._einrichten(problem, glaetter_grad, alpha, potenz_schritte, glaetter, lambda_sicherheit,
                             grob_verschiebung, geraet)
        finally:
            if geraet == "gpu":
                # zwischengespeicherte Bloecke freigeben - hier sind die lokalen Felder des Einrichtens schon
                # aufgeloest, und auch nach einem Fehler (Speichermangel) bleibt der Pool nicht gefuellt;
                # sonst sammelten sich mehrere Details eines Prozesses im Pool, bis die Karte auslagerte
                # (Messreihe 28.09.2026: 1,5 statt 0,13 s je Iteration)
                import cupy
                cupy.get_default_memory_pool().free_all_blocks()
        if geraet == "gpu":
            import cupy
            self.statistik["gpu_belegt_mb"] = round(cupy.get_default_memory_pool().used_bytes() / 1e6, 1)

    def _einrichten(self, problem, glaetter_grad: int, alpha: float, potenz_schritte: int, glaetter: str,
                    lambda_sicherheit: float, grob_verschiebung: float, geraet: str) -> None:
        t0 = time.perf_counter()
        zeiten: dict[str, float] = {}
        _GPU_SPITZE[0] = 0
        pr = problem
        if pr.K is None:
            pr.aufbauen()
        g = pr.gitter
        p = int(g.p)
        self.glaetter_grad = int(glaetter_grad)
        self.alpha = float(alpha)
        self.geraet = geraet
        if geraet == "gpu":
            import cupy
            self.xp = cupy
        else:
            self.xp = np
        zd_fein = getattr(pr, "_zelldaten", None) or Zelldaten(g, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        # feinste Ebene mit den Zwaengen und der reduzierten Matrix des Problems (dieselben freien
        # Koordinaten wie pr.loesen); beim Direktloeser mit Schnittebenen ist _K_red der Sattelpunkt
        C0 = pr.zwaenge.C
        A0 = getattr(pr, "_K_red", None)
        if A0 is None or A0.shape[0] != C0.shape[1]:
            K = zd_fein.matrix()
            if pr.K_rand is not None:
                K = K + pr.K_rand
            A0 = (C0.T @ K @ C0).tocsr()
        op_fein = Operator(zd_fein, C=C0, K_rand=pr.K_rand)
        self.ebenen: list[Ebene] = [Ebene(p, g, C0, pr.zwaenge.moden_frei, A0, operator=op_fein)]
        self.zelldaten_fein = zd_fein
        self.K_rand = pr.K_rand
        fein = self.ebenen[0]
        t = time.perf_counter()
        for pk in range(p - 1, 0, -1):
            g_k = copy.copy(g)
            g_k.moden_nummerieren(pk)                      # weist neue Felder zu, das Original bleibt
            sub = _teilraum_indizes(fein.p, pk)
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
            auswahl = (3 * spalten_f[:, None] + np.arange(3)).ravel()        # feine freie Koordinaten
            P_frei = sp.csr_matrix((np.ones(len(auswahl)), (auswahl, np.arange(len(auswahl)))), shape=(fein.n_frei, len(auswahl)))
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
            # Galerkin exakt, weil geschachtelt: A_grob = P~^T A_fein P~, und P~ waehlt nur Koordinaten aus -
            # die grobe Matrix ist eine Teilmatrix der feinen (keine neue Assemblierung, test_mehrgitter
            # vergleicht mit C_k^T K_k C_k aus den Teilbloecken der Zellmatrizen)
            A_k = fein.A_matrix[auswahl][:, auswahl].tocsr()
            eb = Ebene(pk, g_k, C_k, moden_frei_k, A_k)
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
        # Rechengeraet: Operatoren und Injektionen
        t = time.perf_counter()
        if geraet == "gpu":
            import cupyx.scipy.sparse as cusp
            from .operator_gpu import OperatorGpu
            op_gpu = OperatorGpu(zd_fein, C=C0, K_rand=pr.K_rand)
            self.ebenen[0].A_geraet = op_gpu.frei_anwenden
            self.operator_gpu = op_gpu
            for eb in self.ebenen[1:]:
                if eb is not self.ebenen[-1]:
                    A_g = cusp.csr_matrix(eb.A_matrix)
                    eb.A_geraet = (lambda x, M=A_g: M @ x)
                eb.P_geraet = cusp.csr_matrix(eb.P)
                eb.PT_geraet = cusp.csr_matrix(eb.P.T.tocsr())
        else:
            for eb in self.ebenen[1:]:
                eb.P_geraet = eb.P
                eb.PT_geraet = eb.P.T.tocsr()
        zeiten["geraet"] = time.perf_counter() - t
        # Grobgitter p = 1 direkt (CPU), mit den Mittelwertzwaengen als Sattelpunkt
        t = time.perf_counter()
        grob = self.ebenen[-1]
        A1 = grob.A_matrix
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
        # Singularitaet erkennen (grob_nullkandidaten): fuer Zufallsproben X liefert die Loesung von
        # A1s Y = A1 X den Nullraumanteil nicht zurueck; zwei Schritte inverser Iteration trennen ihn ab.
        # grob_residuum (Probe einer Spalte) bleibt nur als Kennzahl im Protokoll, entscheidet nichts mehr.
        N1 = A1.shape[0]
        X = np.random.default_rng(1).standard_normal((N1, _NULL_PROBEN))

        def grob_loesen(R):
            rhs = A1 @ R
            if self.n_zwaenge:
                rhs = np.concatenate([rhs, grob.B @ R], axis=0)
            return grob.direkt.loesen(rhs)[:N1]

        self.grob_residuum = float(np.linalg.norm(X[:, 0] - grob_loesen(X[:, :1])[:, 0]) / np.linalg.norm(X[:, 0]))
        # auch mit Schnittebenen: der Vertragsweg hat immer welche, und ein Koerper, den keine Ebene
        # beruehrt (zweites Blech, STL mit zwei Schalen), bliebe sonst ohne Projektion und ohne Warnung
        # (Gutachten 28.09.2026); der Sattelpunkt filtert die von B gesperrten Bewegungen
        kandidaten = grob_nullkandidaten(grob_loesen, X)[0]
        zeiten["grobgitter"] = time.perf_counter() - t
        # Nullraum auf die feinste Ebene injizieren und dort am Operator bestaetigen. Ohne ihn blaehte der
        # Vorkonditionierer den Nullraumanteil auf (r_0/delta), der ueber Rundung ins Residuum
        # zurueckwirkte: Kirsch h 10 p 3 (u_z frei) erreichte 1e-8 und sprang wieder auf 1e-6, 147 bis 243
        # Iterationen je nach Einstellung und Summationsreihenfolge (28.09.2026). Nur bestaetigte echte
        # Nullvektoren werden herausprojiziert - ein fast singulaerer, aber echter Modus darf nicht fehlen.
        self.nullraum = None
        self._nullraum_cpu: np.ndarray | None = None
        n_kandidaten = int(kandidaten.shape[1])
        if n_kandidaten:
            for eb in reversed(self.ebenen[1:]):
                kandidaten = eb.P @ kandidaten
            fein = self.ebenen[0]
            Q, _ = np.linalg.qr(kandidaten)
            x_ref = np.random.default_rng(2).standard_normal(fein.n_frei)
            bezug = np.linalg.norm(fein.A_matrix @ x_ref) / np.linalg.norm(x_ref)
            echt = [j for j in range(Q.shape[1]) if np.linalg.norm(fein.A_matrix @ Q[:, j]) < 1e-6 * bezug]
            if fein.B is not None and echt:
                # frei nur im Kern der Mittelwertzwaenge: dann vertauschen die Projektionen des CG (auf den
                # Kern von B) und des V-Zyklus (weg vom Nullraum)
                b_norm = float(np.linalg.norm(fein.B))
                echt = [j for j in echt if np.linalg.norm(fein.B @ Q[:, j]) < 1e-8 * b_norm]
            if echt:
                self._nullraum_cpu = np.ascontiguousarray(Q[:, echt])
                self.nullraum = self.xp.asarray(self._nullraum_cpu)
        # Glaetter je Ebene: Schwarz-Zellbloecke aus der assemblierten Matrix der Ebene, sonst Jacobi
        t = time.perf_counter()
        self.glaetter = glaetter
        speicher = 0.0
        for eb in self.ebenen[:-1]:
            if glaetter == "schwarz":
                eb.schwarz = ZellSchwarz(eb.C, eb.dofs, eb.A_matrix, geraet=geraet)
                speicher += eb.schwarz.speicher_mb
                eb.vork = eb.schwarz.anwenden
            else:
                d = self.xp.asarray(eb.diag)
                eb.vork = (lambda r, d=d: r / d)
        zeiten["glaetter"] = time.perf_counter() - t
        # lambda_max von M^-1 A je Ebene (Potenzmethode), 10 % Sicherheit
        t = time.perf_counter()
        rng = np.random.default_rng(0)
        for eb in self.ebenen[:-1]:
            v = self.xp.asarray(rng.standard_normal(eb.n_frei))
            v /= float(self.xp.linalg.norm(v))
            lam = 0.0
            for _ in range(potenz_schritte):
                w = eb.vork(eb.A(v))
                lam = float(self.xp.linalg.norm(w))
                v = w / lam
            eb.lambda_max = float(lambda_sicherheit) * lam
        zeiten["lambda_max"] = time.perf_counter() - t
        warnungen = []
        k_null = 0 if self._nullraum_cpu is None else int(self._nullraum_cpu.shape[1])
        if k_null:
            warnungen.append(f"Operator singulaer: {k_null} freie Starrkoerperbewegung(en) ohne Lagerung (am feinen Operator "
                             f"bestaetigt); der Vorkonditionierer projiziert sie heraus, die Verschiebungen sind nur bis auf "
                             f"diese Bewegung bestimmt, die Spannungen nicht betroffen")
        elif n_kandidaten:
            warnungen.append(f"Grobgitter nahezu singulaer ({n_kandidaten} Kandidat(en) fuer freie Bewegungen), am feinen "
                             f"Operator nicht bestaetigt; Verschiebung {self.grob_delta:.1e}")
        self.statistik = {"ebenen": [int(e.p) for e in self.ebenen], "frei_je_ebene": [int(e.n_frei) for e in self.ebenen],
                          "lambda_max": [round(e.lambda_max, 4) for e in self.ebenen[:-1]], "glaetter": glaetter,
                          "glaetter_grad": self.glaetter_grad, "alpha": self.alpha, "geraet": geraet,
                          "grobgitter": grob.direkt.name, "grobgitter_nnz": int(A1s.nnz), "grobgitter_probe": self.grob_residuum,
                          "grobgitter_delta": self.grob_delta, "nullraum_dim": k_null,
                          "speicher_glaetter_mb": round(speicher, 1), "warnungen": warnungen,
                          "zeiten_s": {k: round(v, 2) for k, v in zeiten.items()},
                          "t_einrichten_s": round(time.perf_counter() - t0, 3)}
        if geraet == "gpu":
            # Spitze = was der Pool waehrend des Einrichtens hoechstens hielt
            self.statistik["gpu_spitze_mb"] = round(_gpu_spitze_merken() / 1e6, 1)

    # -- Glaetter ------------------------------------------------------------------------
    def _chebyshev(self, eb: Ebene, b: np.ndarray, x: np.ndarray) -> np.ndarray:
        """Chebyshev vom Grad k auf [lambda_max/alpha, lambda_max] mit dem Glaetter M (Saad, Alg. 12.1)."""
        lmax = eb.lambda_max
        lmin = lmax / self.alpha
        d = 0.5 * (lmax + lmin)
        c = 0.5 * (lmax - lmin)
        r = b - eb.A(x)
        alpha = 0.0
        p = self.xp.zeros_like(x)
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
    def _zyklus(self, k: int, b):
        eb = self.ebenen[k]
        if eb.direkt is not None:
            # Grobgitter auf der CPU (klein); auf der GPU eine Uebertragung hin und zurueck
            b_cpu = b.get() if self.geraet == "gpu" else b
            if self.n_zwaenge:
                y = eb.direkt.loesen(np.concatenate([b_cpu, np.zeros(self.n_zwaenge)]))[:len(b_cpu)]
            else:
                y = eb.direkt.loesen(b_cpu)
            return self.xp.asarray(y)
        x = self._chebyshev(eb, b, self.xp.zeros_like(b))
        r = b - eb.A(x)
        grob = self.ebenen[k + 1]
        xc = self._zyklus(k + 1, grob.PT_geraet @ r)
        x = x + grob.P_geraet @ xc
        return self._chebyshev(eb, b, x)

    def anwenden(self, r):
        r = self.xp.asarray(r, dtype=float)
        N = self.nullraum
        if N is None:
            return self._zyklus(0, r)
        # symmetrisch projiziert: z = Pi M Pi r mit Pi = I - N N^T (N orthonormal)
        r = r - N @ (N.T @ r)
        z = self._zyklus(0, r)
        return z - N @ (N.T @ z)


__all__ = ["PMehrgitter", "Ebene", "ZellSchwarz", "grob_nullkandidaten"]
