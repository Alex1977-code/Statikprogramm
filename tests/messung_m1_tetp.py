"""
Messung M1 fuer den Tetraeder mit Ordnung p (``elements/tetp.py``) am
Drehlager - **ohne zu rechnen**. Dieselben Spalten und dieselbe symbolische
Analyse wie ``tests/messung_m1.py`` (erste Element-Sitzung, tet10), damit die
Zeilen nebeneinander stehen koennen: Unbekannte, nnz der Matrix, PARDISO
Phase 11 (mtype 11) mit iparm(18) = nnz im Faktor und iparm(19) = MFlops.

Muster: Inzidenz Element-Funktion statt Element-Knoten. Die Eckfunktionen
sind die Knoten; jede Kanten-, Flaechen- und Innenfunktion der Anreicherung
ist eine eigene Funktion mit drei Verschiebungen (tetp.Anreicherung: FHG
start + 3 r + c). Inaktive Funktionen (Maske der Mindestregel und der
Pflichtseiten) fehlen. A = C^T C, aufgeblaeht mit einer 3x3-Einsmatrix.
Frei sind die Translationen wie in messung_m1 (Knoten mit Volumenelement ohne
Knotenlager) und alle Zusatz-FHG ohne die, die ein starres Lager mitsperrt
(tetp.gesperrte_fhg). Kontakt nicht gerechnet: der Vergleich gilt fuer die
Grundsteifigkeit, wie bei messung_m1.

Varianten:
    heute                         das Netz, wie es ist (messung_m1.zeile)
    tetp p = 2 ueberall           jeder tet4 wird tetp2 - im Muster dasselbe
                                  wie tet10 ueberall, nur ohne Mittelknoten
    tetp p = 4 in 1 Lage          p = 4 in den Elementen mit einer Ecke auf
                                  einer gekruemmten Flaeche, sonst p = 2
    ... sonst tet4                dieselbe Lage, der Rest bleibt tet4 (die
                                  billigste Form; im Labor verschmutzte ein
                                  tet4-Rest die Nachweisstellen)
    ... Nachweiskoerper           dieselben nur in den Koerpern mit Nachweis
                                  (Volumenbereiche mit design), Rest tet4
    --koerper                     jeder Koerper ab 1 % der Elemente einzeln als
                                  tetp2 und tetp3, Rest tet4, mit dem Aufwand
                                  gegen heute (Liste je Koerper)
    --alle                        auch p = 2 ueberall und p = 4 in der Lage
                                  mit p = 2 im Rest (am Drehlager 2,66 Mio.
                                  FHG und mehr - Muster allein ~8 min)

Gekruemmt heisst: eine Modellflaeche, deren Randseiten nicht in einer Ebene
liegen (Winkel einer Seitennormale zur mittleren Normale > 0,5 Grad) -
gemessen am Netz, nicht am Flaechentyp (Model.Flaeche.typ warnt selbst, dass
ein Ebenheitstest an Eckknoten kippen kann). Lage 1 wie im Labor
(gemischt_zyl): Elemente mit einer Ecke auf der Flaeche. Kontakt- und
Fugenseiten bleiben auch dort linear (Pflichtseiten); das Muster zaehlt, was
die Rechnung heute haette.

Kein Test (steht nicht in run_all). Aufruf (Maschine vorher ansagen):

    python -m tests.messung_m1_tetp <modell.json> [--koerper | --alle]
"""
from __future__ import annotations

import sys
import time

import numpy as np
from scipy import sparse

from tests.messung_m1 import muster, zeile

#: Grenzwinkel fuer "gekruemmt" in Grad
GRENZWINKEL = 0.5
#: Obergrenze fuer nnz(K) der freien Matrix, bis zu der Muster und Analyse
#: gebaut werden - die Maschine teilen sich mehrere Sitzungen. Der
#: Spitzenspeicher jeder Zeile wird mit ausgegeben (spitze_gb).
GRENZE_NNZ = 6e8


def spitze_gb() -> float:
    """Spitzenspeicher (PeakWorkingSetSize) dieses Prozesses in GB; nur Windows, sonst nan."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return float("nan")
        return pmc.PeakWorkingSetSize / 2 ** 30
    except Exception:            # noqa: BLE001 - kein Windows
        return float("nan")


def muster_tetp(model, zeiten=None):
    """(A_frei CSR mit Einsen auf dem FHG-Muster oder None oberhalb GRENZE_NNZ,
    Zahl der freien FHG, nnz(A_frei), Kontrolle). ``zeiten`` sammelt die
    Sekunden je Schritt."""
    from statik3d import assemble as asm
    from statik3d.elements import tetp as tp
    zeiten = {} if zeiten is None else zeiten
    uhr = [time.perf_counter()]

    def stopp(name):
        jetzt = time.perf_counter()
        zeiten[name] = zeiten.get(name, 0.0) + jetzt - uhr[0]
        uhr[0] = jetzt
    an = tp.anreicherung(model, streng=True)
    stopp("Anreicherung")
    nn = int(model.nn)
    nfun = nn + int(an.anzahl) // 3
    try:
        bind = asm.mittelknoten_bindungen(model)
    except Exception:            # noqa: BLE001 - ohne quadratische Nachbarn keine Bindung
        bind = []
    ersatz = {m: (a, b) for m, a, b in bind}
    zeilen, spalten = [], []
    k = 0
    for e in model.elements:
        if e.typ not in asm.SOLID_TYPES or tp.ist_tetp(e.typ):
            continue
        kn = set()
        for n in e.nodes:
            n = int(n)
            kn.update(ersatz.get(n, (n,)))
        zeilen.extend([k] * len(kn))
        spalten.extend(kn)
        k += 1
    stopp("uebrige Elemente")
    z_all, s_all = [np.asarray(zeilen, np.int64)], [np.asarray(spalten, np.int64)]
    for _P, els, fhg, maske in tp._laeufe(model, an.idx):
        d0 = fhg[:, 0::3]
        fid = np.where(d0 >= an.basis, nn + (d0 - an.basis) // 3, d0 // 6)
        zz = np.repeat(np.arange(k, k + len(els)), d0.shape[1]).reshape(d0.shape)
        z_all.append(zz[maske])
        s_all.append(fid[maske])
        k += len(els)
    stopp("tetp-FHG (_laeufe)")
    z, s = np.concatenate(z_all), np.concatenate(s_all)
    C = sparse.csr_matrix((np.ones(len(z)), (z, s)), shape=(k, nfun))
    A = (C.T @ C).tocsr()
    A.data[:] = 1.0
    benutzt = np.flatnonzero(np.asarray(A.getnnz(axis=1)) > 0)
    kontrolle = (int((benutzt >= nn).sum()), int(an.anzahl) // 3)
    A = A[benutzt][:, benutzt].tocsr()
    stopp("C^T C")
    # FHG-Nummer je Zeile von K: Knoten 3 n + c wie messung_m1, Zusatz basis + 3 r + c
    fhg = np.where(benutzt[:, None] < nn, 3 * benutzt[:, None],
                   an.basis + 3 * (benutzt[:, None] - nn)) + np.arange(3)[None, :]
    fest = set()
    for sp_ in model.supports:
        for d in sp_.dofs:
            if int(d) < 3:
                fest.add(3 * int(sp_.node) + int(d))
    fest.update(int(d) for d in tp.gesperrte_fhg(model))
    frei_je = ~np.isin(fhg, np.fromiter(fest, np.int64, len(fest)))        # (nb, 3)
    stopp("Lager (gesperrte_fhg)")
    # nnz der freien Matrix exakt ohne sie zu bauen: w^T A w, w = freie Komponenten je Funktion
    w = frei_je.sum(axis=1).astype(float)
    nnz_frei = int(round(float(w @ (A @ w))))
    n_frei = int(frei_je.sum())
    if nnz_frei > GRENZE_NNZ:
        return None, n_frei, nnz_frei, kontrolle
    K = sparse.kron(A, np.ones((3, 3)), format="csr")
    frei = np.flatnonzero(frei_je.ravel())
    K = K[frei][:, frei].tocsr()
    stopp("kron und frei")
    return K, n_frei, nnz_frei, kontrolle


def symbolisch_voll(A):
    """Wie messung_m1.symbolisch, dazu iparm(17) = Speicher fuer die
    Faktorisierung in KB. (nnz im Faktor, MFlops, Sekunden, KB)"""
    import pypardiso
    s = pypardiso.PyPardisoSolver(mtype=11)
    s.set_iparm(18, -1)
    s.set_phase(11)
    A = sparse.csr_matrix(A) + sparse.diags(np.full(A.shape[0], 10.0))
    t0 = time.perf_counter()
    s._call_pardiso(A.tocsr(), np.zeros((A.shape[0], 1)))
    t = time.perf_counter() - t0
    nnz_l, mflops, kb = int(s.get_iparm(18)), int(s.get_iparm(19)), int(s.get_iparm(17))
    s.free_memory(everything=True)
    return nnz_l, mflops, t, kb


def nnz_berichtigt(roh: int, kb: int):
    """iparm(18) ist int32 und kann mehrfach ueberlaufen. Die Zahl der
    Ueberlaeufe folgt aus dem Faktorspeicher iparm(17): nnz ~ KB * 1024 / 8
    (die Faktorwerte als double). Rueckgabe (nnz, Ueberlaeufe, KB*128/nnz)."""
    rest = roh % 2 ** 32
    schaetz = kb * 1024 / 8
    k = max(0, int(round((schaetz - rest) / 2 ** 32)))
    nnz = rest + k * 2 ** 32
    return nnz, k, schaetz / max(nnz, 1)


def zeile_tetp(name, model):
    zeiten = {}
    t0 = time.perf_counter()
    A, n, nnz_k, (zusatz, soll) = muster_tetp(model, zeiten)
    t_m = time.perf_counter() - t0
    if zusatz != soll:
        raise RuntimeError(f"Muster: {zusatz} Zusatzfunktionen benutzt, Anreicherung hat {soll}")
    if A is not None and A.nnz != nnz_k:
        raise RuntimeError(f"nnz: gebaut {A.nnz}, gezaehlt {nnz_k}")
    teile = ", ".join(f"{k} {v:.1f} s" for k, v in zeiten.items())
    if A is None:
        print(f"{name:34s} FHG {n:9d}  nnz(K) {nnz_k:12d}  keine Analyse: nnz(K) > {GRENZE_NNZ:.0e} "
              f"(Speicher)  (Muster {t_m:.1f} s: {teile})", flush=True)
        return {"name": name, "fhg": n, "nnz_K": nnz_k, "nnz_L": None, "mflops": None}
    roh, mflops, t_s, kb = symbolisch_voll(A)
    del A
    nnz_l, k, verh = nnz_berichtigt(roh, kb)
    # iparm(18) ist int32: ueber 2^31 laeuft die Zahl ueber, auch mehrfach
    ueber = f" [iparm(17) {kb} KB, KB*128/nnz {verh:.3f}" + (f", {k}x 2^32 ergaenzt]" if k else "]")
    print(f"{name:34s} FHG {n:9d}  nnz(K) {nnz_k:12d}  nnz(L) {nnz_l:13d}  MFlops {mflops:13d}  "
          f"(Muster {t_m:.1f} s: {teile}; Analyse {t_s:.1f} s; Spitze bisher {spitze_gb():.1f} GB){ueber}",
          flush=True)
    return {"name": name, "fhg": n, "nnz_K": nnz_k, "nnz_L": nnz_l, "mflops": mflops}


def gekruemmte_knoten(model):
    """(Knotenmenge auf gekruemmten Modellflaechen, Zahl gekruemmt, Zahl eben)."""
    from statik3d import assemble as asm
    X = np.asarray(model.nodes, float)
    ne = len(model.elements)
    knoten, n_kr, n_eb = set(), 0, 0
    for f in (getattr(model, "flaechen", None) or {}).values():
        tri = []
        for e, seite in (f.randseiten or []):
            e, seite = int(e), int(seite)
            if not 0 <= e < ne:
                continue
            el = model.elements[e]
            seiten = asm.SOLID_FACES.get(el.typ)
            if not seiten or seite >= len(seiten):
                continue
            tri.append([int(el.nodes[j]) for j in seiten[seite]])
        if not tri:
            continue
        ecken = np.array([t[:3] for t in tri], dtype=np.int64)
        n = np.cross(X[ecken[:, 1]] - X[ecken[:, 0]], X[ecken[:, 2]] - X[ecken[:, 0]])
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-300)[:, None]
        # Vorzeichen einheitlich zur ersten Normale (die Umlaufrichtung der Seiten ist beliebig)
        n *= np.where(n @ n[0] < 0, -1.0, 1.0)[:, None]
        mitte = n.sum(axis=0)
        mitte /= max(np.linalg.norm(mitte), 1e-300)
        winkel = np.degrees(np.arccos(np.clip(n @ mitte, -1, 1))).max()
        if winkel > GRENZWINKEL:
            n_kr += 1
            knoten.update(int(x) for t in tri for x in t)
        else:
            n_eb += 1
    return knoten, n_kr, n_eb


def setze(model, ordnung_je):
    """Elementtypen setzen: {Element: Typ}; alle anderen bleiben, wie sie sind."""
    for i, typ in ordnung_je.items():
        model.elements[i].typ = typ
    model._tetp_version = getattr(model, "_tetp_version", 0) + 1


def je_koerper(m, heute, tet4, anteil_min=0.01, ordnungen=("tetp2", "tetp3")):
    """Jeden Koerper (Model.koerper) ab ``anteil_min`` der Elemente einzeln
    als tetp, der Rest bleibt tet4 - absteigend nach Elementzahl. Dazu der
    Aufwand gegenueber heute. p = 3 nur, solange p = 2 unter GRENZE_NNZ blieb."""
    ist_tet4 = np.zeros(len(m.elements), bool)
    ist_tet4[tet4] = True
    koerper = []
    for name, vk in (getattr(m, "koerper", None) or {}).items():
        els = [int(i) for i in (vk.elemente or []) if 0 <= int(i) < len(m.elements) and ist_tet4[int(i)]]
        if len(els) >= anteil_min * len(tet4):
            koerper.append((len(els), name, els))
    koerper.sort(reverse=True)
    summe = sum(n for n, _name, _els in koerper)
    print(f"Koerper ab {anteil_min:.0%} der tet4: {len(koerper)}, zusammen {summe} von {len(tet4)} "
          f"({summe / len(tet4):.1%})", flush=True)
    for n, name, els in koerper:
        for typ in ordnungen:
            setze(m, {i: typ for i in els})
            try:
                z = zeile_tetp(f"{name} ({n}, {n / len(tet4):.1%}) {typ}", m)
            finally:
                setze(m, {i: "tet4" for i in els})
            if z["mflops"] is not None:
                def q(k):
                    return z[k] / max(heute[k], 1)
                print(f"    gegen heute: FHG {q('fhg'):.2f}x, nnz(L) {q('nnz_L'):.2f}x, "
                      f"MFlops {q('mflops'):.2f}x", flush=True)
            else:
                break


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pfad = argv[0]
    from statik3d.model import Model
    t0 = time.perf_counter()
    m = Model.load(pfad)
    print(f"{pfad}: {m.nn} Knoten, {len(m.elements)} Elemente, geladen in "
          f"{time.perf_counter() - t0:.1f} s", flush=True)
    typen = {}
    for e in m.elements:
        typen[e.typ] = typen.get(e.typ, 0) + 1
    print("Elementtypen:", ", ".join(f"{t} {n}" for t, n in sorted(typen.items())), flush=True)
    heute = zeile("heute", m)
    # Eichung der Ueberlaufkorrektur am Netz von heute (kein Ueberlauf)
    roh, _mf, _t, kb = symbolisch_voll(muster(m)[0])
    print(f"Eichung heute: iparm(18) {roh}, iparm(17) {kb} KB, KB*128/nnz {kb * 128 / roh:.3f}", flush=True)
    tet4 = [i for i, e in enumerate(m.elements) if e.typ == "tet4"]
    if "--koerper" in argv:
        je_koerper(m, heute, tet4)
        return
    kr, n_kr, n_eb = gekruemmte_knoten(m)
    lage = {i for i in tet4 if any(int(n) in kr for n in m.elements[i].nodes[:4])}
    print(f"gekruemmte Flaechen {n_kr} (eben {n_eb}), Knoten darauf {len(kr)}, "
          f"Lage 1: {len(lage)} von {len(tet4)} tet4", flush=True)

    def variante(name, menge, lage_p4):
        setze(m, {i: ("tetp4" if i in lage_p4 else "tetp2") for i in menge})
        try:
            zeile_tetp(name, m)
        finally:
            setze(m, {i: "tet4" for i in menge})

    gruppen = set()
    for _name, vb in (getattr(m, "volumenbereiche", {}) or {}).items():
        if getattr(vb, "design", True):
            gruppen |= {str(m.elements[int(i)].group) for i in vb.elemente}
    nw = [i for i in tet4 if str(m.elements[i].group) in gruppen]
    lage_nw = [i for i in nw if i in lage]
    print(f"Nachweiskoerper {len(gruppen)}, tet4 darin {len(nw)}, davon in Lage 1 {len(lage_nw)}",
          flush=True)
    # zuerst die kleinen Varianten; die grossen laufen ueber GRENZE_NNZ nur als Zaehlung
    if nw:
        variante("p=2 Nachweiskoerper", nw, set())
        variante("p=4 Lage NW, sonst tet4", lage_nw, lage)
        variante("p=4 Lage NW, uebrige NW p=2", nw, lage)
    variante("p=4 Lage ueberall, sonst tet4", sorted(lage), lage)
    if "--alle" in argv:
        variante("p=2 ueberall", tet4, set())
        variante("p=4 Lage ueberall, sonst p=2", tet4, lage)


if __name__ == "__main__":
    main()
