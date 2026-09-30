"""Viele symmetrische Bloecke auf der GPU anwenden, gepackt gespeichert (Plan TP 5, A3; Vorgabe 9).

    z[d] = Summe ueber alle (Block k, lokale Zeile a) mit I_k[a] = d von  skala_k * (X_k v[I_k])[a]

Zwei Nutzer derselben Gestalt: der matrixfreie Operator (X_k = Zellmatrix, I_k = Freiheitsgrade der
Zelle; alle INSIDE-Zellen teilen sich eine Referenzmatrix mit der Skala h_l/h_0) und der Schwarz-Glaetter
(X_k = Inverse des Zellblocks, I_k = freie Koordinaten der Zelle).

Warum gepackt: Zellmatrizen und Blockinversen sind die groessten Posten im GPU-Speicher (p 3: 295 KB je
Schnittzelle und rund 350 KB je Glaetterblock in voller Speicherung); bei 1e6 Freiheitsgraden waeren es mit
der feinen Matrix zusammen 10,8 bis 12,2 GB auf einer Karte mit 8 GB. Gespeichert wird nur das untere Dreieck,
spaltenweise - die Haelfte, in FP64 und damit ohne Aenderung der Rechnung (FP32 im Glaetter divergierte
schon einmal, Theorie 11.10).

Warum zwei Teile im Kern: ein Faden je Zeile, der das Dreieck ueber die Symmetrie ergaenzt, liest die
gespiegelte Haelfte laengs seiner eigenen Spalte - 32 Faeden eines Warps greifen dann auf 32 verschiedene
Speicherzeilen zu, und die Anwendung war 2,8-mal langsamer als die volle Speicherung (4000 Bloecke der Groesse
192: 8,7 gegen 3,1 ms, RTX 3070, 29.09.2026). Darum
  Teil 1: ein Faden je Zeile a, Summe ueber b <= a; fuer festes b lesen die Faeden a >= b aufeinanderfolgende
          Adressen der Spalte b;
  Teil 2: ein Warp je Spalte a, Skalarprodukt laengs der Spalte ueber b > a; die 32 Faeden lesen
          aufeinanderfolgende Adressen, summiert wird ueber den Warp.
Damit 3,3 ms bei halbem Speicher. Grosse Bloecke werden in Auftraege von hoechstens 256 Zeilen zerlegt, sonst
rechnete ein einzelner Kernblock sechs Millionen Eintraege (6 Bloecke der Groesse 2463: 3,2 ms).

Eingesammelt wird ueber die Inzidenz (je Ziel die Liste seiner Pufferplaetze) in fester Reihenfolge; die
Anwendung ist damit bitgleich wiederholbar - das Aufaddieren mit atomaren Additionen war es nicht.
"""
from __future__ import annotations

import numpy as np

try:
    import cupy
    _CUPY = True
except ImportError:                                            # pragma: no cover - ohne GPU
    cupy = None
    _CUPY = False

# Zeilen je Auftrag (= groesste Fadenzahl eines Kernblocks)
_ZEILEN_JE_AUFTRAG = 256

_QUELLE = r"""
extern "C" __global__
void bloecke(const double* __restrict__ vl, const long long* __restrict__ start_i,
             const long long* __restrict__ start_x, const int* __restrict__ groesse,
             const double* __restrict__ skala, const int* __restrict__ auftrag, const int n_auftraege,
             const double* __restrict__ X, double* __restrict__ puffer)
{
    extern __shared__ double aus[];
    const int t = blockIdx.x;
    if (t >= n_auftraege) return;
    const int k = auftrag[3 * t], a0 = auftrag[3 * t + 1], a1 = auftrag[3 * t + 2];
    const int s = groesse[k];
    const double* v = vl + start_i[k];
    const double* Xk = X + start_x[k];
    // Teil 1: untere Haelfte mit Diagonale, Spalte b beginnt bei cb und enthaelt die Zeilen b .. s-1
    for (int a = a0 + threadIdx.x; a < a1; a += blockDim.x) {
        double acc = 0.0;
        long long cb = 0;
        for (int b = 0; b <= a; ++b) { acc += Xk[cb + (a - b)] * v[b]; cb += s - b; }
        aus[a - a0] = acc;
    }
    __syncthreads();
    // Teil 2: gespiegelte Haelfte, X[a][b] = X[b][a] fuer b > a liegt in der Spalte a
    const int warp = threadIdx.x >> 5, lane = threadIdx.x & 31, n_warps = blockDim.x >> 5;
    for (int a = a0 + warp; a < a1; a += n_warps) {
        const double* ca = Xk + ((long long)a * s - (long long)a * (a - 1) / 2) - a;      // ca[b] = X[b][a]
        double acc = 0.0;
        for (int b = a + 1 + lane; b < s; b += 32) acc += ca[b] * v[b];
        for (int off = 16; off > 0; off >>= 1) acc += __shfl_down_sync(0xffffffff, acc, off);
        if (lane == 0) aus[a - a0] += acc;
    }
    __syncthreads();
    const double f = skala[k];
    double* ziel = puffer + start_i[k];
    for (int a = a0 + threadIdx.x; a < a1; a += blockDim.x) ziel[a] = f * aus[a - a0];
}

extern "C" __global__
void sammeln(const double* __restrict__ puffer, const long long* __restrict__ zeiger,
             const int* __restrict__ quelle, const int n, double* __restrict__ z)
{
    const int d = blockIdx.x * blockDim.x + threadIdx.x;
    if (d >= n) return;
    double acc = 0.0;
    for (long long j = zeiger[d]; j < zeiger[d + 1]; ++j) acc += puffer[quelle[j]];
    z[d] = acc;
}
"""

_KERNE: dict = {}


def _kerne():
    if not _KERNE:
        modul = cupy.RawModule(code=_QUELLE)
        _KERNE["bloecke"] = modul.get_function("bloecke")
        _KERNE["sammeln"] = modul.get_function("sammeln")
    return _KERNE["bloecke"], _KERNE["sammeln"]


def dreieck(s: int) -> tuple[np.ndarray, np.ndarray]:
    """Zeilen- und Spaltenindex des unteren Dreiecks (mit Diagonale) in der Speicherfolge: spaltenweise, in
    der Spalte nach Zeilen. X_gepackt = X[il, jl], Laenge s (s + 1) / 2."""
    jl, il = np.triu_indices(int(s))                     # (Spalte <= Zeile), nach Spalte, dann Zeile sortiert
    return il, jl


def gepackte_laenge(groessen) -> np.ndarray:
    g = np.asarray(groessen, np.int64)
    return g * (g + 1) // 2


class GepackteBloecke:
    """``n``: Laenge von Ein- und Ausgabe. ``groessen`` (k,): Blockgroessen. ``index``: flach, je Block seine
    Ziel- und Quellstellen in v (Summe der Groessen). ``X``: cupy-Feld, flach, untere Dreiecke spaltenweise.
    ``start_x`` (k,): Beginn der Matrix je Block in X (mehrere Bloecke duerfen dieselbe Matrix teilen).
    ``skala`` (k,): Faktor je Block, ohne Angabe 1."""

    def __init__(self, n: int, groessen: np.ndarray, index: np.ndarray, X, start_x: np.ndarray,
                 skala: np.ndarray | None = None) -> None:
        groessen = np.asarray(groessen, np.int64)
        index = np.asarray(index).ravel()
        k = len(groessen)
        gesamt = int(groessen.sum())
        if len(index) != gesamt:
            raise ValueError(f"GepackteBloecke: {len(index)} Indizes fuer Bloecke der Gesamtgroesse {gesamt}")
        if gesamt >= 2 ** 31 or n >= 2 ** 31:
            raise ValueError("GepackteBloecke: mehr als 2^31 Pufferplaetze oder Unbekannte")
        if k and (index.min() < 0 or index.max() >= n):
            raise ValueError("GepackteBloecke: Index ausserhalb von 0 .. n-1")
        start_x = np.asarray(start_x, np.int64)
        if k and int((start_x + gepackte_laenge(groessen)).max()) > int(X.size):
            raise ValueError("GepackteBloecke: Matrixspeicher kuerzer als die Bloecke verlangen")
        self.n = int(n)
        self.k = k
        self.gesamt = gesamt
        start_i = np.concatenate([[0], np.cumsum(groessen)]).astype(np.int64)
        # Auftraege: Bloecke in Stuecken von hoechstens _ZEILEN_JE_AUFTRAG Zeilen, nach Fadenzahl gruppiert
        bl, a0 = [], []
        for kk in np.flatnonzero(groessen > _ZEILEN_JE_AUFTRAG):
            anf = np.arange(0, int(groessen[kk]), _ZEILEN_JE_AUFTRAG)
            bl.append(np.full(len(anf), kk))
            a0.append(anf)
        klein = np.flatnonzero((groessen <= _ZEILEN_JE_AUFTRAG) & (groessen > 0))
        bl.append(klein)
        a0.append(np.zeros(len(klein), np.int64))
        bl_f = np.concatenate(bl).astype(np.int64)
        a0_f = np.concatenate(a0).astype(np.int64)
        a1_f = np.minimum(a0_f + _ZEILEN_JE_AUFTRAG, groessen[bl_f])
        faeden = ((a1_f - a0_f + 31) // 32) * 32
        self.auftraege = []
        for f in np.unique(faeden):
            w = np.flatnonzero(faeden == f)
            feld = np.ascontiguousarray(np.stack([bl_f[w], a0_f[w], a1_f[w]], axis=1).astype(np.int32))
            self.auftraege.append((int(f), int(len(w)), cupy.asarray(feld)))
        # Inzidenz: je Ziel seine Pufferplaetze, in fester Reihenfolge
        reihen = np.argsort(index, kind="stable")
        self.d_quelle = cupy.asarray(reihen.astype(np.int32))
        self.d_zeiger = cupy.asarray(np.searchsorted(index[reihen], np.arange(self.n + 1)).astype(np.int64))
        self.d_index = cupy.asarray(index.astype(np.int32))
        self.d_start_i = cupy.asarray(start_i)
        self.d_start_x = cupy.asarray(start_x)
        self.d_groesse = cupy.asarray(groessen.astype(np.int32))
        self.d_skala = cupy.asarray(np.ones(k) if skala is None else np.asarray(skala, float))
        self.d_X = X
        self.d_vl = cupy.zeros(gesamt, dtype=cupy.float64)
        self.d_puffer = cupy.zeros(gesamt, dtype=cupy.float64)
        self._bloecke, self._sammeln = _kerne()
        self.speicher_mb = round((int(X.nbytes) + 2 * 8 * gesamt + 4 * 2 * gesamt + 8 * (self.n + 1)) / 1e6, 1)

    def anwenden(self, v):
        v = cupy.ascontiguousarray(v, dtype=cupy.float64)
        cupy.take(v, self.d_index, out=self.d_vl)
        for faeden, anzahl, feld in self.auftraege:
            self._bloecke((anzahl,), (faeden,),
                          (self.d_vl, self.d_start_i, self.d_start_x, self.d_groesse, self.d_skala, feld,
                           np.int32(anzahl), self.d_X, self.d_puffer), shared_mem=8 * _ZEILEN_JE_AUFTRAG)
        z = cupy.empty(self.n, dtype=cupy.float64)
        self._sammeln(((self.n + 255) // 256,), (256,),
                      (self.d_puffer, self.d_zeiger, self.d_quelle, np.int32(self.n), z))
        return z


__all__ = ["GepackteBloecke", "dreieck", "gepackte_laenge"]
