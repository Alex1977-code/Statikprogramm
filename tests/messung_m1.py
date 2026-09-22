"""
Messung M1 (Auftrag an die Element-Sitzung, 22.09.2026): was kostet tet10 in
ausgewaehlten Koerpern des Drehlagers - **ohne zu rechnen**.

Gemessen wird am Muster der Steifigkeitsmatrix der freien Freiheitsgrade:
Unbekannte, nnz der Matrix und die symbolische Analyse von PARDISO (Phase 11,
mtype 11 wie im Programm): iparm(18) = nnz im Faktor, iparm(19) = MFlops der
Faktorisierung. Keine Faktorisierung, keine Elementmatrizen.

Das Muster entsteht ueber die Inzidenz Element-Knoten: A = C^T C (Knoten, die
ein Element teilen), aufgeblaeht auf drei Verschiebungen je Knoten (kron mit
einer 3x3-Einsmatrix). Gebundene Mittelknoten (Uebergang tet4/tet10,
assemble.mittelknoten_bindungen) tragen keine eigenen FHG; ihre Kopplung geht
auf die Ecken ihrer Kante. Frei sind die Translationen aller Knoten mit
Volumenelement, ohne die Lager (Kontakt nicht gerechnet: der Vergleich gilt
fuer die Grundsteifigkeit).

Varianten:
    heute                     das Netz, wie es ist
    tet10 <Bereich>           die Koerper (Element.group) eines Volumenbereichs
                              mit Nachweis quadratisch (gerade Kanten), Rest wie heute
    tet10 Nachweiskoerper     alle Koerper mit Nachweis zusammen
    tet10 alle                jeder tet4 quadratisch (obere Schranke)

Kein Test (steht nicht in run_all). Aufruf (Maschine vorher ansagen):

    python -m tests.messung_m1 <modell.json> [--ohne-alle] [--bereiche]
"""
from __future__ import annotations

import sys
import time

import numpy as np
from scipy import sparse


def muster(model):
    """(A_frei CSR mit Einsen auf dem FHG-Muster, Zahl der freien FHG)."""
    from statik3d import assemble as asm
    bind = asm.mittelknoten_bindungen(model)
    ersatz = {m: (a, b) for m, a, b in bind}
    zeilen, spalten = [], []
    k = 0
    for i, e in enumerate(model.elements):
        if e.typ not in asm.SOLID_TYPES:
            continue
        kn = set()
        for n in e.nodes:
            n = int(n)
            if n in ersatz:
                kn.update(ersatz[n])
            else:
                kn.add(n)
        zeilen.extend([k] * len(kn))
        spalten.extend(kn)
        k += 1
    C = sparse.csr_matrix((np.ones(len(zeilen)), (np.asarray(zeilen), np.asarray(spalten))),
                          shape=(k, model.nn))
    A = (C.T @ C).tocsr()
    A.data[:] = 1.0
    benutzt = np.flatnonzero(np.asarray(A.getnnz(axis=1)) > 0)
    K = sparse.kron(A[benutzt][:, benutzt], np.ones((3, 3)), format="csr")
    fhg = (3 * benutzt[:, None] + np.arange(3)[None, :]).ravel()
    fest = set()
    for sp_ in model.supports:
        for d in sp_.dofs:
            if int(d) < 3:
                fest.add(3 * int(sp_.node) + int(d))
    frei = np.array([p for p, d in enumerate(fhg) if int(d) not in fest], np.int64)
    return K[frei][:, frei].tocsr(), len(frei)


#: Obergrenze des Faktorspeichers fuer die numerische Faktorisierung (Bytes);
#: darueber wird nur die Analyse gemeldet
FAKTOR_GRENZE = 60e9


def symbolisch(A, numerisch=True):
    """(nnz im Faktor, MFlops, Sekunden Analyse, Sekunden Faktorisierung) -
    PARDISO Phase 11 (mtype 11 wie im Programm), dann Phase 22 mit den Threads
    aus MKL_NUM_THREADS. Die Matrix traegt Einsen auf dem Muster und 10 auf
    der Diagonale: die Zeit der Faktorisierung haengt am Muster, nicht an den
    Werten."""
    import pypardiso
    s = pypardiso.PyPardisoSolver(mtype=11)
    s.set_iparm(18, -1)
    s.set_phase(11)
    A = (sparse.csr_matrix(A) + sparse.diags(np.full(A.shape[0], 10.0))).tocsr()
    b = np.zeros((A.shape[0], 1))
    t0 = time.perf_counter()
    s._call_pardiso(A, b)
    t = time.perf_counter() - t0
    # iparm ist 32 Bit breit: ab 2^31 kommt die Zahl negativ zurueck (gemessen
    # 23.09.2026 am Drehlager, tet10 ueberall: -1.183.324.240). Bis 2^32 ist
    # sie eindeutig und wird zurueckgerechnet.
    nnz_l, mflops = int(s.get_iparm(18)), int(s.get_iparm(19))
    nnz_l = nnz_l + 2 ** 32 if nnz_l < 0 else nnz_l
    mflops = mflops + 2 ** 32 if mflops < 0 else mflops
    t_f = float("nan")
    if numerisch and nnz_l * 8 * 1.5 < FAKTOR_GRENZE:
        s.set_phase(22)
        t0 = time.perf_counter()
        s._call_pardiso(A, b)
        t_f = time.perf_counter() - t0
    s.free_memory(everything=True)
    return nnz_l, mflops, t, t_f


def zeile(name, model):
    t0 = time.perf_counter()
    A, n = muster(model)
    t_m = time.perf_counter() - t0
    nnz_l, mflops, t_s, t_f = symbolisch(A)
    print(f"{name:34s} FHG {n:9d}  nnz(K) {A.nnz:12d}  nnz(L) {nnz_l:13d}  MFlops {mflops:13d}  "
          f"Faktorisierung {t_f:7.2f} s  (Muster {t_m:.1f} s, Analyse {t_s:.1f} s)", flush=True)
    return {"name": name, "fhg": n, "nnz_K": int(A.nnz), "nnz_L": nnz_l, "mflops": mflops,
            "t_faktor": t_f}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pfad = argv[0]
    from statik3d.model import Model
    from statik3d import elementwahl as ew

    def laden():
        t0 = time.perf_counter()
        m = Model.load(pfad)
        return m, time.perf_counter() - t0
    m, t = laden()
    print(f"{pfad}: {m.nn} Knoten, {len(m.elements)} Elemente, geladen in {t:.1f} s", flush=True)
    zeile("heute", m)
    bereiche = []
    for name, vb in (getattr(m, "volumenbereiche", {}) or {}).items():
        if getattr(vb, "design", True):
            bereiche.append((name, {str(m.elements[int(i)].group) for i in vb.elemente}))
    alle_nachweis = set().union(*[g for _n, g in bereiche]) if bereiche else set()
    print(f"Volumenbereiche mit Nachweis: {len(bereiche)}, Koerper darin: {len(alle_nachweis)}",
          flush=True)
    if "--bereiche" in argv:
        for name, gr in bereiche:
            m, _t = laden()
            n_neu = ew.tet4_zu_tet10(m, gr)
            zeile(f"tet10 {name[:18]} (+{n_neu} Kn.)", m)
    if alle_nachweis:
        m, _t = laden()
        n_neu = ew.tet4_zu_tet10(m, alle_nachweis)
        zeile(f"tet10 Nachweiskoerper (+{n_neu} Kn.)", m)
    if "--ohne-alle" not in argv:
        m, _t = laden()
        n_neu = ew.tet4_zu_tet10(m, None)
        zeile(f"tet10 alle (+{n_neu} Kn.)", m)


if __name__ == "__main__":
    main()
