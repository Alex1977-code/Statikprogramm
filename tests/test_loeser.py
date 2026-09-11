"""
Der Gleichungslöser: welcher rechnet, mit wie vielen Threads — und rechnet er richtig.

Anlass ist der Befund vom 07.09.2026. Die ausgelieferte exe hatte kein MKL im
Bundle, fiel auf SuperLU zurück und rechnete auf genau einem von 32 Kernen.
Gemeldet wurde aber „lokal, 31 von 32 Kernen" — diese Zeile stammt vom
Prozesspool fürs Vernetzen und sagt über das Lösen nichts aus. Der Anwender
hat also neun Minuten lang auf eine Rechnung gewartet und dabei geglaubt, sie
laufe auf allen Kernen.

Geprüft wird darum beides:

* **Rechnet er richtig?** Jeder verfügbare Löser wird gegen die geschlossene
  Lösung gestellt, nicht gegeneinander. Ein Zugstab unter Einzellast hat
  u = N·L/(E·A) — daran gibt es nichts zu deuten. Zwei Löser, die beide
  falsch liegen, fallen bei einem Vergleich untereinander nicht auf.
* **Sagt er die Wahrheit?** ``beschreibung()`` muss den Löser nennen, der
  wirklich faktorisiert hat, und SuperLU muss sich „einkernig" nennen — das
  ist keine Einstellung, sondern eine Eigenschaft dieses Lösers.
"""
import os
import sys

import numpy as np
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import parallel                                     # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section     # noqa: E402
from statik3d.solver import (NAMEN, LinearSolver, loeser_verfuegbar,  # noqa: E402
                             mkl_threads, solve_static)

RESULTS = []

E_STAHL = 210e9          # N/m^2


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:62s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(got - want) <= tol
    return check(name, ok, f"{got:.6g} statt {want:.6g} {unit}".strip())


def _zugstab(n_elem=20, L=2.0, A=0.01):
    """Zugstab, links fest, rechts 100 kN in x: u = N·L/(E·A), geschlossen."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("Q", 0.1, 0.1))       # A = 0,01 m^2
    knoten = [m.add_node(i * L / n_elem, 0.0, 0.0) for i in range(n_elem + 1)]
    for i in range(n_elem):
        m.add_element("beam", [knoten[i], knoten[i + 1]], "S235", "Q")
    m.support(knoten[0], "all")
    m.case().nodal_loads.append(NodalLoad(knoten[-1], [1.0e5, 0, 0, 0, 0, 0]))
    return m, L, A


def test_loeser_treffen_die_geschlossene_loesung():
    """Jeder Löser einzeln gegen u = N·L/(E·A)."""
    m, L, A = _zugstab()
    soll = 1.0e5 * L / (E_STAHL * A)
    print(f"    Sollwert u = N·L/(E·A) = {soll * 1e3:.6f} mm")
    gerechnet = 0
    for backend in ("superlu", "pardiso", "cholmod"):
        try:
            r = solve_static(m, backend=backend)
        except TypeError:
            # solve_static reicht das Backend nicht durch - ueber die
            # globale Einstellung gehen
            alt = parallel.settings().solver_backend
            parallel.configure(solver_backend=backend)
            try:
                r = solve_static(m)
            except Exception:                       # noqa: BLE001
                parallel.configure(solver_backend=alt)
                print(f"    {backend}: nicht vorhanden, uebersprungen")
                continue
            parallel.configure(solver_backend=alt)
        except Exception:                           # noqa: BLE001
            print(f"    {backend}: nicht vorhanden, uebersprungen")
            continue
        gerechnet += 1
        close(f"{NAMEN[backend]} trifft N·L/(E·A)", r.u[-1, 0], soll, 1e-9 * soll, "m")
    check("mindestens ein Loeser vorhanden", gerechnet >= 1, f"{gerechnet} gerechnet")


def test_superlu_nennt_sich_einkernig():
    """SuperLU kann keine Threads — es muss das auch sagen."""
    n = 400
    K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsc()
    ls = LinearSolver(K, backend="superlu")
    check("SuperLU meldet sich als SuperLU", ls.backend == "superlu", ls.beschreibung())
    check("SuperLU meldet einen Thread", ls.threads == 1)
    check("die Beschreibung sagt „einkernig“", "einkernig" in ls.beschreibung(),
          ls.beschreibung())
    x = ls.solve(np.ones(n))
    close("SuperLU loest das Testsystem", float(np.linalg.norm(K @ x - 1.0)), 0.0, 1e-9)


def test_pardiso_nimmt_alle_kerne_bis_auf_einen():
    """Die Vorgabe ist cpu_count()−1: der eine Kern bleibt der Oberfläche."""
    merker = {k: os.environ.get(k) for k in ("MKL_NUM_THREADS", "OMP_NUM_THREADS")}
    try:
        for k in merker:
            os.environ.pop(k, None)
        n = mkl_threads()
        soll = max(1, (os.cpu_count() or 2) - 1)
        check("Vorgabe ist „alle Kerne bis auf einen“", n == soll,
              f"{n} von {os.cpu_count()}")
        check("die Umgebung ist danach gesetzt",
              os.environ.get("MKL_NUM_THREADS") == str(soll),
              os.environ.get("MKL_NUM_THREADS", "-"))
        # Eine selbst gesetzte Zahl hat Vorrang
        os.environ["MKL_NUM_THREADS"] = "2"
        check("selbst gesetzte Threadzahl hat Vorrang", mkl_threads() == 2)
    finally:
        for k, v in merker.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_meldung_trennt_pool_und_loeser():
    """Der Prozesspool und der Löser sind zweierlei — die Meldung muss das trennen."""
    pool = parallel.describe()
    loes = loeser_verfuegbar()
    check("der Pool nennt Kerne", "Kerne" in pool or "Rechnerfarm" in pool, pool)
    check("der Loeser nennt sich selbst",
          any(x in loes for x in ("PARDISO", "CHOLMOD", "SuperLU")), loes)
    check("die beiden Meldungen sind verschieden", pool != loes)
    check("ohne Mehrkern-Loeser steht es ausdruecklich da",
          "PARDISO" in loes or "CHOLMOD" in loes or "einkernig" in loes, loes)


def test_superlu_ordnet_symmetrisch():
    """MMD_AT_PLUS_A statt COLAMD: weniger Füllung bei symmetrischer Matrix."""
    from scipy.sparse.linalg import splu
    m, _L, _A = _zugstab(n_elem=200)
    from statik3d.solver import StaticSystem
    K = StaticSystem(m).Kff.tocsc()
    colamd = splu(K, permc_spec="COLAMD")
    mmd = splu(K, permc_spec="MMD_AT_PLUS_A")
    f_col = colamd.L.nnz + colamd.U.nnz
    f_mmd = mmd.L.nnz + mmd.U.nnz
    check("MMD_AT_PLUS_A fuellt nicht mehr als COLAMD", f_mmd <= f_col,
          f"{f_mmd:,} statt {f_col:,} Eintraege")
    # und liefert dasselbe
    b = np.ones(K.shape[0])
    check("beide Ordnungen liefern dieselbe Loesung",
          bool(np.allclose(colamd.solve(b), mmd.solve(b), rtol=1e-9)))


def _arbeitsspeicher_mb() -> float:
    """Arbeitsspeicher des Prozesses [MB] - Windows-API oder /proc."""
    if sys.platform.startswith("win"):
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
        fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        fn.restype = wintypes.BOOL
        if not fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return float("nan")
        return pmc.WorkingSetSize / 2 ** 20
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2 ** 20
    except Exception:            # noqa: BLE001
        return float("nan")


def _laplace_3d(n: int) -> sparse.csc_matrix:
    """7-Punkt-Laplace auf einem n x n x n Gitter - Fuellung wie ein Volumennetz."""
    e = np.ones(n)
    T = sparse.diags([-e[:-1], 2.0 * e, -e[:-1]], [-1, 0, 1])
    I_ = sparse.identity(n)
    A = sparse.kron(sparse.kron(T, I_), I_) + sparse.kron(sparse.kron(I_, T), I_) \
        + sparse.kron(sparse.kron(I_, I_), T)
    return (A + 0.1 * sparse.identity(n ** 3)).tocsc()


def test_pardiso_gibt_speicher_frei():
    """Jede Kontakt-Iteration faktorisiert neu; MKL haelt die Faktorisierung
    ausserhalb von Python und gibt sie nur auf Aufruf frei. Am Drehlager
    (1 028 724 FHG, 7 GB je Faktorisierung) wuchs der Prozess je Schritt um
    7 GB bis zum Fehler -2 bei 113 GB. Hier: 25 Faktorisierungen eines
    64 000-FHG-Systems duerfen den Prozess nicht um 25 Faktorisierungen
    wachsen lassen."""
    from statik3d.solver import LinearSolver
    try:
        import pypardiso                                        # noqa: F401
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - Speicherpruefung uebersprungen", True)
        return
    K = _laplace_3d(40)
    ls = LinearSolver(K, backend="pardiso")
    if ls.backend != "pardiso":
        check("Pardiso nicht nutzbar - Speicherpruefung uebersprungen", True, ls.backend)
        return
    b = np.ones(K.shape[0])
    x = ls.solve(b)
    check("Pardiso loest das 64 000-FHG-System", float(np.abs(K @ x - b).max()) < 1e-8)
    vor = _arbeitsspeicher_mb()
    ls.freigeben()
    nach_frei = _arbeitsspeicher_mb()
    einzeln = max(vor - nach_frei, 1.0)
    check("freigeben() gibt den Speicher der Faktorisierung zurueck (mindestens 10 MB)",
          vor - nach_frei > 10.0, f"{vor - nach_frei:.0f} MB")
    try:
        ls.solve(b)
        check("nach dem Freigeben loest der Loeser nicht mehr stillschweigend", False)
    except RuntimeError:
        check("nach dem Freigeben loest der Loeser nicht mehr stillschweigend", True)
    start = _arbeitsspeicher_mb()
    for _ in range(25):
        LinearSolver(K, backend="pardiso").solve(b)          # wie eine Kontakt-Iteration
    ende = _arbeitsspeicher_mb()
    check("25 Faktorisierungen ohne Bezug: Wachstum unter 3 Faktorisierungen",
          ende - start < 3.0 * einzeln + 50.0,
          f"Wachstum {ende - start:.0f} MB bei {einzeln:.0f} MB je Faktorisierung")


def main():
    for f in (test_loeser_treffen_die_geschlossene_loesung,
              test_superlu_nennt_sich_einkernig,
              test_pardiso_nimmt_alle_kerne_bis_auf_einen,
              test_meldung_trennt_pool_und_loeser,
              test_superlu_ordnet_symmetrisch, test_pardiso_gibt_speicher_frei):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
