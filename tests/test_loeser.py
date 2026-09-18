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
    for backend in ("superlu", "pardiso", "cholmod", "umfpack", "mumps", "ama", "pyamg"):
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


def test_loeser_liste():
    """Die Auswahl nennt jeden Loeser mit Lizenz und ob er da ist; PyAMG (MIT)
    und SuperLU (BSD) duerfen in die exe, GPL-Loeser nicht."""
    liste = solver.loeser_liste()
    keys = [k for k, *_ in liste]
    check("alle sieben Loeser in der Liste", keys == ["pardiso", "cholmod", "umfpack", "mumps", "ama", "pyamg", "superlu"],
          str(keys))
    check("SuperLU ist immer da", dict((k, da) for k, _n, da, *_r in liste)["superlu"])
    lizenz = {k: liz for k, _n, _da, liz, _a in liste}
    check("GPL-Loeser sind als nicht mitgeliefert gekennzeichnet",
          "GPL" in lizenz["umfpack"] and "nicht in der exe" in lizenz["cholmod"] and lizenz["pyamg"] == "MIT",
          str(lizenz))
    try:
        import pyamg  # noqa: F401
        m = _stab()
        alt = parallel.settings().solver_backend
        parallel.configure(solver_backend="pyamg")
        try:
            r = solve_static(m)
        finally:
            parallel.configure(solver_backend=alt)
        soll = _soll(m)
        close("PyAMG (iterativ) trifft N·L/(E·A)", r.u[-1, 0], soll, 1e-6 * soll, "m")
    except ImportError:
        print("    pyamg: nicht vorhanden, uebersprungen")
    try:
        ls = LinearSolver(sparse.eye(3, format="csc"), backend="gibtsnicht")
        check("unbekannter Loeser wird abgewiesen", False, ls.backend)
    except RuntimeError as ex:
        check("unbekannter Loeser wird abgewiesen, die Meldung nennt die Auswahl",
              "unbekannt" in str(ex) and "pyamg" in str(ex), str(ex)[:80])


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


def test_kopfzeile_nennt_den_eingestellten_loeser():
    """Die Zeile beim Start der Rechnung muss den Loeser nennen, der dann auch
    rechnet - fuer **jeden** eingestellten, nicht den erstbesten vorhandenen.

    Gemessen wird gegen den Loeser selbst: fuer jeden installierten Loeser
    wird eingestellt, ein kleines System faktorisiert und verglichen, was
    ``LinearSolver`` als Backend und Threadzahl meldet. Bis 14.09.2026 stand
    dort mit eingestelltem MUMPS "MKL PARDISO, 16 Threads", waehrend MUMPS mit
    acht Threads rechnete.
    """
    from statik3d.solver import NAMEN, loeser_da, loeser_liste, loeser_verfuegbar, threads_vorgabe
    K = _laplace_3d(8)
    alt_b = parallel.settings().solver_backend
    alt_t = parallel.settings().solver_threads
    try:
        parallel.configure(solver_threads=0)
        for key, name, da, _lz, _art in loeser_liste():
            if not da or key == "umfpack":          # umfpack: GPL, selten vorhanden
                print(f"     {key} nicht installiert - uebersprungen")
                continue
            parallel.configure(solver_backend=key)
            zeile = loeser_verfuegbar()
            ls = LinearSolver(K)
            ok = NAMEN[ls.backend] in zeile and ls.backend == key
            if key in ("pardiso", "mumps"):
                ok = ok and f"{ls.threads} Threads" in zeile
            check(f"eingestellt {key}: die Kopfzeile nennt ihn und seine Kernzahl",
                  ok, f"„{zeile}“ gegen {ls.beschreibung()}")
        parallel.configure(solver_backend="auto")
        zeile = loeser_verfuegbar()
        ls = LinearSolver(K)
        check("automatisch: die Kopfzeile nennt, was die Reihenfolge ergibt, und sagt „automatisch“",
              NAMEN[ls.backend] in zeile and "automatisch" in zeile,
              f"„{zeile}“ gegen {ls.beschreibung()}")
        parallel.configure(solver_backend="mumps", solver_threads=3)
        check("die eingestellte Threadzahl steht in der Zeile",
              loeser_verfuegbar() == "MUMPS, 3 Threads" or not loeser_da("mumps"),
              loeser_verfuegbar())
        parallel.configure(solver_backend="pardiso", solver_threads=0)
        check("PARDISO nennt seine automatische Threadzahl",
              loeser_verfuegbar() == f"MKL PARDISO, {threads_vorgabe('pardiso')} Threads"
              or not loeser_da("pardiso"), loeser_verfuegbar())
        parallel.configure(solver_backend="superlu")
        check("SuperLU nennt sich einkernig, ohne Threadzahl",
              loeser_verfuegbar() == "SuperLU, einkernig", loeser_verfuegbar())
        parallel.configure(solver_backend="gibtesnicht")
        check("ein unbekannter Löser wird als solcher gemeldet",
              "unbekannter Gleichungslöser" in loeser_verfuegbar(), loeser_verfuegbar())
    finally:
        parallel.configure(solver_backend=alt_b, solver_threads=alt_t)


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


def test_mumps_sagt_was_es_tut_und_gibt_speicher_frei():
    """MUMPS (CeCILL-C) kommt unter Windows als Paket ``mumps`` aus packaging/
    mit in die exe - eigener Bau mit gfortran, OpenMP, OpenBLAS und METIS
    (docs/MUMPS_Windows_Bauanleitung.md). Geprueft wird, was ohne die
    Anbindung falsch waere: die Threadzahl kommt von der Laufzeit und nicht
    aus der Umgebung; symmetrische Matrizen laufen als unteres Dreieck
    (SYM=2), unsymmetrische als volle Matrix - beide richtig; freigeben()
    gibt die Faktorisierung zurueck (MUMPS haelt sie wie MKL ausserhalb von
    Python); 25 Faktorisierungen ohne Bezug wachsen nicht."""
    from statik3d import werkzeuge
    werkzeuge.aktivieren()
    try:
        import mumps
    except ImportError:
        # Nicht in der Umgebung: unter Windows das Rad aus packaging/ offline
        # in einen Wegwerf-Werkzeugordner (so kommt es auch in die exe-Umgebung)
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rad = os.path.join(here, "packaging", werkzeuge.WERKZEUGE["mumps"].rad)
        if not sys.platform.startswith("win") or not os.path.isfile(rad):
            check("Paket mumps: kein Windows oder kein Rad in packaging/ - uebersprungen", True)
            return
        import tempfile
        os.environ["STATIK3D_WERKZEUGE"] = tempfile.mkdtemp(prefix="statik3d_loeser_mumps_")
        os.environ["STATIK3D_WERKZEUG_QUELLE"] = os.path.join(here, "packaging")
        werkzeuge.installieren("mumps")
        import mumps
        check("MUMPS aus packaging/ nachgeladen", mumps.__file__.startswith(os.environ["STATIK3D_WERKZEUGE"]))
    K = _laplace_3d(30)                                     # 27 000 FHG, symmetrisch
    n = K.shape[0]
    b = np.arange(1.0, n + 1.0)
    ls = LinearSolver(K, backend="mumps")
    check("MUMPS meldet sich als MUMPS", ls.backend == "mumps", ls.beschreibung())
    check("die Threadzahl kommt von der Laufzeit (mumps.threads())",
          ls.threads == mumps.threads() >= 1, f"{ls.beschreibung()} / {mumps.beschreibung()}")
    x = ls.solve(b)
    close("MUMPS loest das symmetrische 27 000-FHG-System",
          float(np.abs(K @ x - b).max() / np.abs(b).max()), 0.0, 1e-10)
    X = ls.solve(np.column_stack([b, 2.0 * b]))
    check("zwei rechte Seiten auf einmal, spaltenweise",
          X.shape == (n, 2) and np.allclose(X[:, 0], x) and np.allclose(X[:, 1], 2.0 * x))
    vor = _arbeitsspeicher_mb()
    ls.freigeben()
    nach = _arbeitsspeicher_mb()
    einzeln = max(vor - nach, 1.0)
    check("freigeben() gibt den Speicher der Faktorisierung zurueck (mindestens 10 MB)",
          vor - nach > 10.0, f"{vor - nach:.0f} MB")
    try:
        ls.solve(b)
        check("nach dem Freigeben loest MUMPS nicht mehr stillschweigend", False)
    except RuntimeError:
        check("nach dem Freigeben loest MUMPS nicht mehr stillschweigend", True)
    # Unsymmetrisch: ein Eintrag oberhalb der Diagonale anders als sein
    # Spiegelbild - dann darf nicht das untere Dreieck allein hinein
    Ku = K.tolil()
    Ku[0, 1] = 3.0 * Ku[0, 1]
    Ku = Ku.tocsc()
    xu = LinearSolver(Ku, backend="mumps").solve(b)
    close("unsymmetrische Matrix: volle Matrix, richtig geloest",
          float(np.abs(Ku @ xu - b).max() / np.abs(b).max()), 0.0, 1e-10)
    check("und die Loesung unterscheidet sich von der symmetrischen",
          not np.allclose(xu, x, rtol=1e-6), f"max |dx| = {np.abs(xu - x).max():.3g}")
    start = _arbeitsspeicher_mb()
    for _ in range(25):
        LinearSolver(K, backend="mumps").solve(b)           # wie eine Kontakt-Iteration
    ende = _arbeitsspeicher_mb()
    check("25 Faktorisierungen ohne Bezug: Wachstum unter 3 Faktorisierungen",
          ende - start < 3.0 * einzeln + 50.0,
          f"Wachstum {ende - start:.0f} MB bei {einzeln:.0f} MB je Faktorisierung")


def test_threadzahl_aus_den_einstellungen():
    """Berechnung -> Einstellungen -> Threads des Gleichungsloesers: 0 heisst
    automatisch (PARDISO alle Kerne bis auf einen, MUMPS hoechstens acht),
    sonst genau diese Zahl - fuer beide Loeser, zur Laufzeit umschaltbar
    ohne Neustart ("dann kann ich das an meinem Modell pruefen", 13.09.2026)."""
    from statik3d.solver import threads_automatisch, threads_vorgabe, loeser_liste
    K = _laplace_3d(12)
    b = np.ones(K.shape[0])
    da = {k: ok for k, _n, ok, *_r in loeser_liste()}
    alt = parallel.settings().solver_threads
    try:
        parallel.configure(solver_threads=0)
        n_p = threads_automatisch("pardiso")
        check("automatisch: PARDISO alle Kerne bis auf einen (von MKL auf die physischen Kerne gekappt), MUMPS hoechstens acht",
              threads_vorgabe("pardiso") == n_p and 1 <= n_p <= max(1, os.cpu_count() - 1)
              and 1 <= threads_automatisch("mumps") <= 8,
              f"pardiso {n_p}, mumps {threads_automatisch('mumps')}")
        try:
            import mumps as _mu
            check("PARDISO automatisch = min(Kerne - 1, physische Kerne) - so kappt MKL (16 auf 16/32)",
                  n_p == min(max(1, os.cpu_count() - 1), _mu.physische_kerne()) or not da.get("pardiso"),
                  f"{n_p} bei {_mu.physische_kerne()} physischen Kernen")
        except ImportError:
            pass
        parallel.configure(solver_threads=2)
        check("Einstellung 2: die Vorgabe beider Loeser ist 2",
              threads_vorgabe("pardiso") == 2 and threads_vorgabe("mumps") == 2)
        for key in ("pardiso", "mumps"):
            if not da.get(key):
                print(f"     {key} nicht installiert - uebersprungen")
                continue
            ls = LinearSolver(K, backend=key)
            x = ls.solve(b)
            check(f"{key} rechnet mit 2 Threads und richtig",
                  ls.threads == 2 and float(np.abs(K @ x - b).max()) < 1e-8, ls.beschreibung())
            parallel.configure(solver_threads=0)
            ls0 = LinearSolver(K, backend=key)
            check(f"{key} zurueck auf automatisch: {threads_automatisch(key)} Threads, ohne Neustart",
                  ls0.threads == threads_automatisch(key), ls0.beschreibung())
            parallel.configure(solver_threads=2)
    finally:
        parallel.configure(solver_threads=alt)


def test_ama_faktorisiert_symmetrisch_und_nennt_threads():
    """ama (eigener Kern): loest das Testsystem exakt, meldet seine Threads und lehnt
    unsymmetrische Matrizen mit einer Meldung ab, die die Alternativen nennt."""
    try:
        import ama.kern  # noqa: F401
    except ImportError:
        print("    ama: nicht installiert, uebersprungen")
        return
    n = 400
    K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsc()
    ls = LinearSolver(K, backend="ama")
    check("ama meldet sich als ama", ls.backend == "ama", ls.beschreibung())
    check("ama meldet mindestens einen Thread", ls.threads >= 1, str(ls.threads))
    x = ls.solve(np.ones(n))
    close("ama loest das Testsystem", float(np.linalg.norm(K @ x - 1.0)), 0.0, 1e-12)
    X = ls.solve(np.ones((n, 3)))
    close("ama loest mehrere rechte Seiten", float(np.abs(K @ X - 1.0).max()), 0.0, 1e-12)
    Ku = K.tolil()
    Ku[0, 1] = -0.5                                        # unsymmetrisch
    try:
        LinearSolver(Ku.tocsc(), backend="ama")
        check("ama weist unsymmetrische Matrizen ab", False)
    except RuntimeError as ex:
        check("ama weist unsymmetrische Matrizen ab und nennt Alternativen",
              "symmetrisch" in str(ex) and "PARDISO" in str(ex), str(ex)[:80])


def test_ama_nimmt_die_genauigkeitseinstellung():
    """Die Einstellung 'Genauigkeit des Gleichungsloesers' muss bei ama ankommen: der Faktor
    iteriert bis zu dieser Schranke nach und nennt sie in der Beschreibung.

    Geprueft wird das am Nachweis von ama ("Ziel ... erreicht ..."), nicht an der Schranke
    allein: die stand schon vorher in der Beschreibung, aus der Einstellung gelesen. Erst der
    Nachweis belegt, dass ama die Vorgabe wirklich bekommen und gemessen hat.
    """
    try:
        import ama.kern  # noqa: F401
    except ImportError:
        print("    ama: nicht installiert, uebersprungen")
        return
    n = 300
    K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsc()
    alt = parallel.settings().solver_residuum if hasattr(parallel.settings(), "solver_residuum") else 1e-6
    parallel.configure(solver_residuum=1e-4)
    try:
        ls = LinearSolver(K, backend="ama")
        x = ls.solve(np.ones(n))
        close("ama loest mit gelockerter Schranke", float(np.linalg.norm(K @ x - 1.0)), 0.0, 1e-4 * n)
        check("die Beschreibung nennt die Stufe, die ama gemessen hat",
              "Ziel 1e-04" in ls.beschreibung() or "Ziel 0.0001" in ls.beschreibung(),
              ls.beschreibung())
    finally:
        parallel.configure(solver_residuum=alt)


def test_ama_faktorisiert_kein_zweites_mal_im_stillen():
    """Erreicht ama die Schranke nicht, darf es nicht von sich aus neu faktorisieren.

    Der Rueckfall „genauer" des Kerns faktorisiert die ganze Matrix ein zweites Mal. Da
    ``LinearSolver._solve`` das ``loese`` des Faktors ist, geschieht das bei jedem
    Nachiterationsschritt von ``solve`` erneut — am Drehlager (1 028 724 FHG) sieben Gigabyte
    je Faktorisierung, stumm und mehrfach. Gemessen wurden 2 Faktorisierungen fuer einen
    einzigen ``solve``-Aufruf (18.09.2026). Wer meldet, dass das Residuum zu gross ist, ist
    und bleibt Statik3Ds eigene Pruefung in ``solve``.
    """
    try:
        from ama import kern as ama_kern
    except ImportError:
        print("    ama: nicht installiert, uebersprungen")
        return
    n = 300
    K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsc()
    alt = parallel.settings().solver_residuum
    zaehler = [0]
    echt = ama_kern.Symbolik.faktorisiere

    def zaehlend(self, *args, **kw):
        zaehler[0] += 1
        return echt(self, *args, **kw)

    parallel.configure(solver_residuum=1e-20)          # unerreichbar, auch mit Nachiteration
    ama_kern.Symbolik.faktorisiere = zaehlend
    try:
        ls = LinearSolver(K, backend="ama")
        check("der Aufbau faktorisiert genau einmal", zaehler[0] == 1, f"{zaehler[0]}x")
        zaehler[0] = 0
        try:
            ls.solve(np.ones(n))
            check("die unerreichbare Schranke wird gemeldet", False, "kein Fehler")
        except RuntimeError as ex:
            check("die unerreichbare Schranke wird gemeldet, nicht heimlich verfolgt",
                  "Residuum" in str(ex) and "Schranke" in str(ex), str(ex)[:70])
        check("Loesen faktorisiert kein zweites Mal", zaehler[0] == 0,
              f"{zaehler[0]} zusaetzliche Faktorisierungen")
    finally:
        ama_kern.Symbolik.faktorisiere = echt
        parallel.configure(solver_residuum=alt)


def test_die_beschreibung_nennt_die_loesung_nicht_die_korrektur():
    """Nach mehreren Loesungen muss die Beschreibung die Zahl nennen, die ``solve`` gemessen hat.

    ``LinearSolver._solve`` ist das ``loese`` des ama-Faktors, und jeder Aufruf ueberschreibt
    dessen ``nachweis``. Die Nachiteration in ``solve`` ruft es fuer die Korrektur ``b - K x``
    auf, deren Residuum sich auf eine ganz andere Bezugsgroesse bezieht. Danach beschrieb die
    Beschreibung die Korrektur statt der Loesung und widersprach der eigenen Fehlermeldung
    (gemessen 18.09.2026: Meldung 1,1e-16, Beschreibung 1,3e-16).

    Die Einstellung wird hier erst nach dem Faktorisieren verschaerft — so laeuft die
    Nachiteration von ``solve`` sicher an, ohne dass der Test auf eine numerische Randlage
    angewiesen waere. Im Programm tritt genau das auf, wenn die Genauigkeit sich aendert,
    waehrend eine Faktorisierung behalten wird (``StaticSystem._kontakt_loeser``).
    """
    try:
        import ama.kern  # noqa: F401
    except ImportError:
        print("    ama: nicht installiert, uebersprungen")
        return
    n = 300
    K = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsc()
    alt = parallel.settings().solver_residuum
    try:
        ls = LinearSolver(K, backend="ama")
        ls.solve(np.ones(n))
        check("die Beschreibung nennt das Residuum der ersten Loesung",
              f"erreicht {ls.residuum:.1e}" in ls.beschreibung(),
              f"{ls.residuum:.1e} / {ls.beschreibung()}")
        parallel.configure(solver_residuum=1e-20)      # Nachiteration von solve laeuft an
        try:
            ls.solve(np.arange(1.0, n + 1.0))
        except RuntimeError:
            pass                                       # erwartet: Schranke unerreichbar
        check("die Beschreibung nennt die Loesung, nicht die letzte Korrektur",
              f"erreicht {ls.residuum:.1e}" in ls.beschreibung(),
              f"{ls.residuum:.1e} / {ls.beschreibung()}")
        gemeldet = ls.beschreibung()
        ls.freigeben()
        check("freigeben() gibt den ama-Faktor zurueck", ls._faktor is None, repr(ls._faktor))
        check("der Nachweis ueberlebt das Freigeben", ls.beschreibung() == gemeldet,
              ls.beschreibung())
    finally:
        parallel.configure(solver_residuum=alt)


def main():
    for f in (test_loeser_treffen_die_geschlossene_loesung,
              test_superlu_nennt_sich_einkernig,
              test_pardiso_nimmt_alle_kerne_bis_auf_einen,
              test_meldung_trennt_pool_und_loeser, test_kopfzeile_nennt_den_eingestellten_loeser,
              test_superlu_ordnet_symmetrisch, test_pardiso_gibt_speicher_frei,
              test_mumps_sagt_was_es_tut_und_gibt_speicher_frei,
              test_threadzahl_aus_den_einstellungen,
              test_ama_faktorisiert_symmetrisch_und_nennt_threads,
              test_ama_nimmt_die_genauigkeitseinstellung,
              test_ama_faktorisiert_kein_zweites_mal_im_stillen,
              test_die_beschreibung_nennt_die_loesung_nicht_die_korrektur):
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
