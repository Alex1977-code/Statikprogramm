"""
Messung M1 (Auftrag an die Element-Sitzung, 22.09.2026): was kostet tet10 in
ausgewaehlten Koerpern des Drehlagers - **ohne zu rechnen**.

Gemessen wird am Muster der Steifigkeitsmatrix der freien Freiheitsgrade:
Unbekannte, nnz der Matrix und die symbolische Analyse von PARDISO (Phase 11,
mtype 11 wie im Programm): iparm(18) = nnz im Faktor, iparm(19) = MFlops der
Faktorisierung. Keine Faktorisierung, keine Elementmatrizen - das Muster
entsteht aus den FHG-Listen der Elemente (Einsen).

Varianten:
    heute        das Netz, wie es ist (tet4)
    tet10 alle   jeder tet4 mit Kantenmitten (gerade Kanten) - die obere Schranke
    tet10 <K>    nur die Koerper K (Element.group) quadratisch, der Rest tet4;
                 an der Grenze die Mittelknotenbindung (assemble.mittelknoten_bindungen),
                 gebundene Mittelknoten tragen keine eigenen FHG

Kein Test (steht nicht in run_all). Aufruf (Maschine vorher ansagen):

    python -m tests.messung_m1 <modell.json> [Koerper ...]

Ohne Koerper: heute, tet10 alle, und je Volumenbereich mit Nachweis dessen
Koerper.
"""
from __future__ import annotations

import sys
import time

import numpy as np
from scipy import sparse


def muster(model, frei_maske=None):
    """CSR-Muster (Einsen) der Translations-FHG aller Volumenelemente.
    Rueckgabe (A, fhg-Liste der Zeilen)."""
    from statik3d import assemble as asm
    bind = {m: (a, b) for m, a, b in asm.mittelknoten_bindungen(model)}
    zeilen, spalten = [], []
    for e in model.elements:
        if e.typ not in asm.SOLID_TYPES:
            continue
        kn = [int(n) for n in e.nodes]
        # gebundene Mittelknoten: ihre Kopplung geht auf die Ecken
        kn = [n for n in kn if n not in bind]
        d = np.array([6 * n + r for n in kn for r in range(3)], np.int64)
        r, c = np.meshgrid(d, d, indexing="ij")
        zeilen.append(r.ravel())
        spalten.append(c.ravel())
    z = np.concatenate(zeilen)
    s = np.concatenate(spalten)
    n = 6 * model.nn
    A = sparse.coo_matrix((np.ones(len(z)), (z, s)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    benutzt = np.flatnonzero(np.asarray(A.getnnz(axis=1)) > 0)
    fest = set()
    for sp_ in model.supports:
        for d in sp_.dofs:
            if int(d) < 3:
                fest.add(6 * int(sp_.node) + int(d))
    frei = np.array([d for d in benutzt if d not in fest], np.int64)
    return A[frei][:, frei].tocsr(), frei


def symbolisch(A):
    """(nnz im Faktor, MFlops, Sekunden) der PARDISO-Analyse (Phase 11)."""
    import pypardiso
    s = pypardiso.PyPardisoSolver(mtype=11)
    s.set_iparm(18, -1)
    s.set_phase(11)
    A = sparse.csr_matrix(A)
    # Diagonale dominant belegen, damit die Analyse eine regulaere Matrix sieht
    A = A + sparse.diags(np.full(A.shape[0], 10.0))
    t0 = time.perf_counter()
    s._call_pardiso(A, np.zeros((A.shape[0], 1)))
    t = time.perf_counter() - t0
    nnz_l, mflops = int(s.get_iparm(18)), int(s.get_iparm(19))
    s.free_memory(everything=True)
    return nnz_l, mflops, t


def quadratisch_machen(model, koerper=None):
    """tet4 der Koerper (alle, wenn None) zu tet10 mit Kantenmitten auf geraden
    Kanten - gemeinsame Kanten bekommen denselben Mittelknoten."""
    kanten = [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]
    mitten: dict = {}
    neu = []
    X = np.asarray(model.nodes, float)
    zahl = model.nn
    for e in model.elements:
        if e.typ != "tet4" or (koerper is not None and e.group not in koerper):
            continue
        kn = [int(n) for n in e.nodes]
        for a, b in kanten:
            key = (min(kn[a], kn[b]), max(kn[a], kn[b]))
            if key not in mitten:
                mitten[key] = zahl
                neu.append(0.5 * (X[kn[a]] + X[kn[b]]))
                zahl += 1
        e.nodes = kn + [mitten[(min(kn[a], kn[b]), max(kn[a], kn[b]))] for a, b in kanten]
        e.typ = "tet10"
    if neu:
        model.nodes = np.vstack([X, np.asarray(neu)])
    return len(neu)


def zeile(name, model):
    t0 = time.perf_counter()
    A, frei = muster(model)
    t_m = time.perf_counter() - t0
    nnz_l, mflops, t_s = symbolisch(A)
    print(f"{name:28s} FHG {len(frei):9d}  nnz(K) {A.nnz:12d}  nnz(L) {nnz_l:13d}  "
          f"MFlops {mflops:13d}  (Muster {t_m:.1f} s, Analyse {t_s:.1f} s)", flush=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pfad = argv[0]
    wahl = argv[1:]
    from statik3d.model import Model
    t0 = time.perf_counter()
    m = Model.load(pfad)
    print(f"{pfad}: {m.nn} Knoten, {len(m.elements)} Elemente, geladen in "
          f"{time.perf_counter() - t0:.1f} s", flush=True)
    zeile("heute", m)
    import copy
    if not wahl:
        bereiche = []
        for name, vb in (getattr(m, "volumenbereiche", {}) or {}).items():
            if getattr(vb, "design", True):
                gr = {m.elements[int(i)].group for i in vb.elemente}
                bereiche.append((name, gr))
        for name, gr in bereiche:
            m2 = copy.deepcopy(m)
            n_neu = quadratisch_machen(m2, gr)
            zeile(f"tet10 {name} (+{n_neu} Kn.)", m2)
        m2 = copy.deepcopy(m)
        n_neu = quadratisch_machen(m2, None)
        zeile(f"tet10 alle (+{n_neu} Kn.)", m2)
    else:
        m2 = copy.deepcopy(m)
        n_neu = quadratisch_machen(m2, set(wahl))
        zeile(f"tet10 {','.join(wahl)[:20]} (+{n_neu} Kn.)", m2)


if __name__ == "__main__":
    main()
