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


def test_jeder_loeser_sagt_woher_er_kommt():
    """Ein grauer Eintrag ohne Grund ist eine Sackgasse: der Anwender sah am
    19.09.2026 Loeser, die er „nicht waehlen kann und auch nicht
    installieren“. Jeder Loeser muss darum sagen, warum er fehlt und was zu
    tun ist — und die drei Faelle muessen unterscheidbar bleiben:
    nachladbar (MUMPS), aus Lizenzgruenden ausgeschlossen (CHOLMOD, UMFPACK),
    mitgeliefert (dann ist der Bau schuld)."""
    from statik3d import solver
    keys = list(solver.LOESER)
    fehlt = [k for k in keys if k not in solver.LOESER_WOHER]
    check("jeder bekannte Loeser hat eine Herkunftsangabe", not fehlt, str(fehlt))
    zuviel = [k for k in solver.LOESER_WOHER if k not in solver.LOESER]
    check("und keine Angabe zeigt auf einen Loeser, den es nicht gibt", not zuviel, str(zuviel))
    for k in keys:
        kurz, weg = solver.loeser_woher(k)
        check(f"{k}: kurzer Grund passt in einen Listeneintrag",
              0 < len(kurz) <= 40, f"{len(kurz)} Zeichen: {kurz}")
        # SuperLU ist der einzige, der keinen Weg braucht: er kommt mit scipy
        # und kann gar nicht fehlen - dann muss der Hinweis genau das sagen
        check(f"{k}: der Hinweis nennt einen Weg oder sagt, warum es keinen gibt",
              len(weg) >= 60 and ("pip install" in weg or "Vernetzer installieren" in weg
                                  or "kann nicht fehlen" in weg), weg[:90])
    # Die Lizenzloeser duerfen nicht als nachladbar erscheinen - sie sind es
    # nicht, und ein Verweis auf den Werkzeugdialog ginge ins Leere
    for k in ("cholmod", "umfpack"):
        kurz, weg = solver.loeser_woher(k)
        check(f"{k}: sagt, dass die Lizenz im Weg steht, und verweist nicht auf das Nachladen",
              "GPL" in kurz and "Vernetzer installieren" not in weg, f"{kurz} / {weg[:60]}")
    kurz_m, weg_m = solver.loeser_woher("mumps")
    check("MUMPS: nennt den Weg zum Nachladen, den es wirklich gibt",
          "Vernetzer installieren" in kurz_m and "Vernetzer installieren" in weg_m,
          f"{kurz_m} / {weg_m[:80]}")
    from statik3d import werkzeuge as wz
    check("und dieser Weg fuehrt zu einem Werkzeug, das das Programm kennt",
          "mumps" in wz.WERKZEUGE, str(list(wz.WERKZEUGE)))
    # Unbekannter Schluessel: kein Absturz, sondern der alte Text
    check("ein unbekannter Loeser faellt auf „nicht installiert“ zurueck",
          solver.loeser_woher("gibtsnicht") == ("nicht installiert", ""),
          str(solver.loeser_woher("gibtsnicht")))


def test_ama_liegt_der_exe_bei():
    """ama ist der eigene Rechenkern und gehoert in die exe - er stand aber
    weder in der Bauvorschrift noch im Arbeitsablauf, und darum zeigte die
    Auswahl ihn dort grau (19.09.2026). Er kommt von keinem Paketserver: das
    Rad liegt im Baum, wie das von MUMPS."""
    import io
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = io.open(os.path.join(wurzel, "packaging", "Statik3D.spec"), encoding="utf-8").read()
    check("die Bauvorschrift sammelt ama samt Rechenkern",
          'collect_submodules("ama")' in spec, "collect_submodules(\"ama\") fehlt")
    check("und nennt ihn bei den Zusatzpaketen", '"ama"' in spec.split("for optional in")[1][:120],
          spec.split("for optional in")[1][:120])
    raeder = [d for d in os.listdir(os.path.join(wurzel, "packaging")) if d.startswith("ama-")]
    check("das Rad liegt im Baum (kein Paketserver kennt ama)", len(raeder) == 1, str(raeder))
    ablauf = io.open(os.path.join(wurzel, ".github", "workflows", "windows-exe.yml"),
                     encoding="utf-8").read()
    check("und der Bau spielt genau dieses Rad ein",
          f"pip install packaging/{raeder[0]}" in ablauf,
          f"pip install packaging/{raeder[0]}")
    # Die exe wuerde ama sonst schweigend auslassen: MUMPS steht in excludes,
    # ama stand nirgends - beides sieht im Bauprotokoll gleich aus
    check("MUMPS bleibt dagegen bewusst draussen", "mumps" in spec and "excludes" in spec)


def test_pardiso_grenze_der_32_bit_indizes():
    """Der Prozess ist durchgehend 64-bittig - die Schnittstelle zu MKL
    PARDISO aber nicht: pypardiso reicht die Matrix ueber die LP64-Fassung
    weiter (``ia = A.indptr.astype(np.int32) + 1``), und ``astype`` prueft
    nicht. Ueber 2^31-1 liefe die Umwandlung still ueber und PARDISO bekaeme
    vertauschte Indizes - falsche Zahlen statt einer Fehlermeldung
    (20.09.2026). Darum wird vorher geprueft."""
    import warnings
    from statik3d import solver as slv
    check("die Grenze ist 2^31 - 1", slv.INT32_MAX == 2 ** 31 - 1, str(slv.INT32_MAX))

    class Zugross:
        nnz = 2 ** 31

    def probe(n, nnz, verlangt):
        ls = slv.LinearSolver.__new__(slv.LinearSolver)
        ls.n = n
        Z = type("K", (), {"nnz": nnz})
        return ls._passt_in_int32(Z(), verlangt)

    check("ein gewoehnliches System passt", probe(476214, 17_800_000, True))
    slv._GEMELDET.clear()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        passt = probe(2 ** 31, 3, False)
        gemeldet = [str(x.message) for x in w]
    check("zu viele Zeilen werden erkannt", passt is False)
    check("und gemeldet, mit Zahl, Grenze und den 64-Bit-Alternativen",
          gemeldet and "PARDISO" in gemeldet[0] and "MUMPS" in gemeldet[0]
          and str(slv.INT32_MAX) in gemeldet[0], (gemeldet or [""])[0][:90])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        probe(2 ** 31, 3, False)
        check("derselbe Hinweis kommt nur einmal je Programmlauf - eine "
              "Faktorisierung laeuft Dutzende Male", not w, str(len(w)))
    check("zu viele Eintraege werden ebenso erkannt", probe(10, 2 ** 31, False) is False)
    try:
        probe(2 ** 31, 3, True)
        check("bei ausdruecklich gewaehltem PARDISO wird nicht still ausgewichen", False)
    except RuntimeError as ex:
        check("bei ausdruecklich gewaehltem PARDISO gibt es eine Ausnahme statt eines "
              "stillen Ausweichens", "PARDISO" in str(ex), str(ex)[:70])
    # Die Grenze steht nicht im Weg: das Drehlager ist Faktor 120 davon entfernt
    check("das groesste gerechnete Modell hat reichlich Luft",
          17_800_000 * 120 < slv.INT32_MAX, f"{slv.INT32_MAX / 17.8e6:.0f}-fach")


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
            # Geprueft wird die **Schranke**, nicht der Wert. Wie stark MKL
            # kappt, ist seine Sache und haengt vom Rechner ab: hier auf die
            # 16 physischen Kerne von 32, auf einem anderen Rechner auf 8 bei
            # 24 physischen (Vernetzersitzung, 20.09.2026). Die fruehere
            # Gleichheit n_p == min(Kerne-1, physische) war darum eine
            # Behauptung ueber MKL, die nur auf einer Maschine stimmte - und
            # sie riss den Gesamtlauf auf der anderen. Was das Programm
            # zusichert, ist: nie mehr als angefordert, nie mehr als
            # physisch da, und gemeldet wird, was MKL wirklich nimmt.
            check("PARDISO automatisch: hoechstens Kerne - 1 und hoechstens die physischen Kerne",
                  (1 <= n_p <= min(max(1, os.cpu_count() - 1), _mu.physische_kerne()))
                  or not da.get("pardiso"),
                  f"{n_p} Threads bei {os.cpu_count()} Kernen, davon {_mu.physische_kerne()} physisch")
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
    # Gezaehlt wird, indem `Symbolik.faktorisiere` ersetzt wird - also ueber die Paketgrenze
    # hinweg in amas Interna. Von aussen ist nicht zu sehen, wie oft faktorisiert wurde: der
    # Faktor meldet Threads und gestoerte Pivots, aber nicht, dass er sich selbst noch einmal
    # aufgebaut hat. Der Test haengt damit an zwei Dingen, die ama aendern kann: am Namen
    # `Symbolik.faktorisiere` und daran, dass jede Faktorisierung durch ihn laeuft (die
    # Modulfunktion `ama.kern.faktorisiere` und der Rueckfall tun das heute beide). Wenn ama
    # umgebaut wird und dieser Test still durchlaeuft, ist zuerst hier nachzusehen - und
    # besser waere ein Zaehler, den ama selbst fuehrt.
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


def test_kein_rueckfall_im_nachweis_wenn_die_schranke_gehalten_wird():
    """Der Nachweis darf nicht zugleich „gehalten" und einen gezogenen Rueckfall melden.

    Das passiert, sobald ama die Schranke verfehlt (und darum „lockern" vermerkt) und
    Statik3Ds eigene Nachiteration die Loesung danach doch darunter holt: ``erreicht`` und
    ``gehalten`` stammen dann vom Endergebnis, ``rueckfall`` noch vom ersten Loesen. Das ist
    kein Sonderfall — es tritt ein, sooft die Schleife in ``solve`` einen Schritt macht und
    damit Erfolg hat.

    Der Aufbau: ein Sattelpunktsystem (Nullblock auf der Diagonale, wie bei Kontakt mit
    Lagrange-Multiplikatoren) ist nach dem ersten Loesen messbar ungenauer als nach einer
    Nachiteration. Die Schranke wird zwischen die beiden gemessenen Residuen gelegt, nicht
    geraten: ihr Abstand haengt an der Rechnerei und faellt von Maschine zu Maschine anders
    aus. Ohne Abstand gibt es den Fall hier nicht, dann wird uebersprungen.
    """
    try:
        import ama.kern  # noqa: F401
    except ImportError:
        print("    ama: nicht installiert, uebersprungen")
        return
    n, m = 200, 20
    A = sparse.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                     [-1, 0, 1]).tocsr()
    B = sparse.random(m, n, density=0.3, random_state=5, format="csr")
    K = sparse.bmat([[A, B.T], [B, sparse.csr_matrix((m, m))]], format="csc")
    b = np.ones(n + m)
    s = parallel.settings()
    alt = (s.solver_residuum, s.solver_nachiterationen)

    def residuum_mit(schritte):
        """Das Residuum, das mit so vielen Nachiterationen erreicht wird."""
        parallel.configure(solver_residuum=1e-30, solver_nachiterationen=schritte)
        ls = LinearSolver(K, backend="ama")
        try:
            ls.solve(b)                        # 1e-30 ist unerreichbar: Meldung erwartet
        except RuntimeError:
            pass
        return ls.residuum

    try:
        roh, fein = residuum_mit(0), residuum_mit(4)
        if not fein < roh:
            print(f"    kein Abstand zwischen roher ({roh:.1e}) und nachiterierter ({fein:.1e}) "
                  "Loesung - uebersprungen")
            return
        schranke = (roh * fein) ** 0.5
        # ama bekommt die Schranke ohne Nachiterationen und verfehlt sie; erst danach darf
        # solve() nachiterieren. Die Vorgabe ist im Faktor eingefroren, solve() liest neu.
        parallel.configure(solver_residuum=schranke, solver_nachiterationen=0)
        ls = LinearSolver(K, backend="ama")
        parallel.configure(solver_residuum=schranke, solver_nachiterationen=4)
        ls.solve(b)
        nach = ls._nachweis
        check("der Aufbau trifft den strittigen Fall: die Schleife rettet die Loesung",
              nach.gehalten and ls.nachiterationen >= 1,
              f"{ls.nachiterationen} Schritte, gehalten={nach.gehalten}")
        check("gehaltene Schranke und gezogener Rueckfall schliessen sich aus",
              not (nach.gehalten and nach.rueckfall),
              f"gehalten={nach.gehalten}, rueckfall={nach.rueckfall}")
    finally:
        parallel.configure(solver_residuum=alt[0], solver_nachiterationen=alt[1])


def test_speicherfehler_nennt_zahlen():
    """Ein Speicherfehler sagt, wie groß das System ist und was der Rechner
    hat - ohne das ließ sich nicht sagen, woran es lag (19.09.2026: 669 MiB
    scheiterten an einem Rechner mit 128 GB)."""
    import scipy.sparse as sparse
    from statik3d import solver as slv
    lage = slv.speichertext("jetzt")
    check("die Speicherlage nennt freien und gesamten Speicher",
          "GB frei" in lage and "jetzt" in lage, lage[:90])
    m = slv.speicherlage()
    check("… als Zahlen, in GiB wie im Taskmanager",
          m["gesamt"] is None or 0.5 < m["gesamt"] < 10000,
          str({k: (round(v, 1) if isinstance(v, float) else v) for k, v in m.items()}))
    # Der Weg durch die Fehlerbehandlung: ein erzwungener MemoryError wird
    # zu einer Meldung mit Größe und Lage
    echt = slv.LinearSolver._aufbauen

    def kippt(self, K, backend=None):
        self.n = K.shape[0]
        raise MemoryError("Unable to allocate 669. MiB")

    slv.LinearSolver._aufbauen = kippt
    try:
        slv.LinearSolver(sparse.eye(7, format="csr"))
        check("ein Speicherfehler wird erklärt", False, "keine Ausnahme")
    except RuntimeError as ex:
        t = str(ex)
        check("ein Speicherfehler wird erklärt: Freiheitsgrade, Einträge, Speicherlage, Rat",
              "7 Freiheitsgraden" in t and "Mio. Einträgen" in t and "Auslagerungsdatei" in t, t[:130])
    except MemoryError:
        check("ein Speicherfehler wird erklärt", False, "nackter MemoryError")
    finally:
        slv.LinearSolver._aufbauen = echt


def test_symmetriepruefung():
    """Die Prüfung, ob eine Matrix symmetrisch ist (MUMPS SYM=2, ama), läuft
    blockweise: ``K - K.T`` legt in scipy erst ein Ergebnis in der Größe
    beider Strukturen an. Am Drehlager (43,8 Mio Einträge) waren das 87,7 Mio
    und 669 MiB, die nicht mehr passten (18.09.2026)."""
    import numpy as np
    import scipy.sparse as sparse
    from statik3d.solver import ist_symmetrisch
    n = 400
    rng = np.random.default_rng(3)
    z = np.repeat(np.arange(n), 8)
    sp = np.clip(z + rng.integers(-5, 5, z.size), 0, n - 1)
    A = sparse.coo_matrix((rng.random(z.size), (z, sp)), shape=(n, n)).tocsr()
    K = (A + A.T).tocsr()
    check("eine symmetrische Matrix wird erkannt", ist_symmetrisch(K))
    K2 = K.tolil()
    K2[3, 7] = float(K2[3, 7]) + 1.0          # eine einzige Stelle verstimmen
    check("eine unsymmetrische Matrix auch (eine Stelle genügt)", not ist_symmetrisch(K2.tocsr()))
    K3 = K.tolil()
    K3[n - 1, 0] = 1e-30                       # weit außerhalb der Bandbreite, winzig
    check("ein Wert unter der Schranke gilt noch als symmetrisch",
          ist_symmetrisch(K3.tocsr(), 1e-12 * float(abs(K).max())))
    check("eine nicht quadratische Matrix ist nicht symmetrisch",
          not ist_symmetrisch(sparse.csr_matrix((3, 4))))
    # dasselbe Ergebnis wie der frühere Weg, an einer Stichprobe
    for i in range(5):
        r = np.random.default_rng(10 + i)
        B = sparse.random(120, 120, density=0.05, random_state=r).tocsr()
        M = (B + B.T).tocsr() if i % 2 else B
        alt_ = float(abs(M - M.T).max()) <= 1e-12 * (float(abs(M).max()) or 1.0) if M.nnz else True
        check(f"Stichprobe {i + 1}: gleiches Ergebnis wie K − K.T",
              ist_symmetrisch(M, 1e-12 * (float(abs(M).max()) or 1.0)) == alt_)


def test_die_matrix_wird_einmal_umgewandelt():
    """Der LinearSolver wandelt die Matrix einmal nach CSR um, nicht zweimal.

    ``__init__`` machte bis zum 21.09.2026 ``K = K.tocsc()``,
    ``self._K = K.tocsr()`` und danach fuer PARDISO noch einmal
    ``K.tocsr()`` auf derselben Matrix. Bei Drehlagergroesse (475.935
    Zeilen, 17,6 Mio. Nichtnullen) kostet eine Umwandlung **0,280 s**;
    bei 145 Faktorisierungen je Lastfall sind das 40,6 s, ueber 422
    Lastfaelle 4,75 Stunden. Beide lesen nur, eine genuegt.

    Gezaehlt wird die Umwandlung selbst - eine Zeitmessung waere hier das
    falsche Mass: sie haengt an der Maschine, die Zahl der Aufrufe nicht.
    """
    from scipy import sparse as _sp
    from statik3d.solver import LinearSolver

    n = 200
    rng = np.random.default_rng(11)
    A = _sp.random(n, n, density=0.02, random_state=1, format="csr")
    K = (A + A.T + _sp.eye(n) * (n * 1.0)).tocsr()          # symmetrisch, definit

    echt = _sp.csc_matrix.tocsr
    zahl = {"n": 0}

    def zaehlend(self, *a, **k):
        zahl["n"] += 1
        return echt(self, *a, **k)

    _sp.csc_matrix.tocsr = zaehlend
    try:
        ls = LinearSolver(K, backend="pardiso")
    finally:
        _sp.csc_matrix.tocsr = echt

    check("die Matrix wird genau einmal nach CSR umgewandelt", zahl["n"] == 1,
          f"{zahl['n']} Umwandlungen" + (" - zweimal ist der alte Stand"
                                         if zahl["n"] > 1 else ""))
    b = rng.normal(size=n)
    x = ls.solve(b)
    check("und sie loest damit richtig",
          float(np.abs(K @ x - b).max()) < 1e-8 * float(np.abs(b).max()),
          f"Restfehler {float(np.abs(K @ x - b).max()):.2e}")
    ls.freigeben()


def test_die_tangente_wird_nur_gebaut_wenn_sie_gelesen_wird():
    """Bleibt die Faktorisierung stehen, wird Kt gar nicht erst gebaut.

    ``StaticSystem.solve`` baute bis zum 21.09.2026 in **jedem** Schritt
    ``Kt = self.K + K_extra`` und ``Ktff = Kt[fi][:, fi].tocsc()``. Ktff
    wird aber nur unter ``if neu:`` gelesen, Kt sonst nur bei einer
    Verformungsvorgabe. Bei Drehlagergroesse kosten Addition und Zuschnitt
    zusammen 0,577 s; am Drehlager nutzen 5 von 150 Kontaktschritten die
    Faktorisierung wieder, das sind 2,88 s je Lastfall und 0,34 Stunden
    ueber 422 Lastfaelle.

    Gezaehlt wird die Matrixaddition. Der zweite Aufruf mit **derselben**
    Signatur muss ohne auskommen - er loest nur rueckwaerts ein.
    """
    from scipy import sparse as _sp
    from statik3d import solver as _s

    m, _L, _A = _zugstab()
    system = _s.StaticSystem(m)
    F = _s.case_loads(m, {m.case().name: 1.0}, None)[0]
    # Eine kleine Zusatzsteifigkeit, wie sie der Kontakt beisteuert
    Kc = _sp.csr_matrix((np.array([1.0e3]), (np.array([6]), np.array([6]))),
                        shape=(m.ndof, m.ndof))

    echt = _sp.csr_matrix.__add__
    zahl = {"n": 0}

    def zaehlend(self, other):
        zahl["n"] += 1
        return echt(self, other)

    _sp.csr_matrix.__add__ = zaehlend
    try:
        sig = ("probe", 1)
        u1 = system.solve(F, K_extra=Kc, signatur=sig)
        erste = zahl["n"]
        u2 = system.solve(F, K_extra=Kc, signatur=sig)
        zweite = zahl["n"] - erste
    finally:
        _sp.csr_matrix.__add__ = echt
        system.kontakt_loeser_freigeben()

    check("der erste Schritt baut die Tangente", erste >= 1,
          f"{erste} Additionen")
    check("der zweite mit gleicher Signatur baut sie nicht noch einmal",
          zweite == 0, f"{zweite} Additionen"
          + (" - der alte Stand baute auch hier" if zweite else ""))
    check("und er faktorisiert auch nicht neu",
          getattr(system, "faktorisierungen", 0) == 1,
          f"{getattr(system, 'faktorisierungen', 0)} Faktorisierungen")
    check("beide Loesungen sind dieselbe",
          float(np.abs(np.asarray(u1) - np.asarray(u2)).max()) == 0.0,
          "bitgleich")


def test_die_symmetriesonde_hat_keine_luecke():
    """Ein Muster, das eine ungestimmte Sonde sicher verschluckt.

    ``ist_symmetrisch`` sondiert seit dem 22.09.2026 mit ``K r`` gegen
    ``K^T r`` statt die Struktur zu durchlaufen (5,206 -> 0,419 s an einer
    Ersatzmatrix mit 35,2 Mio. Eintraegen; das Zeitfenster am Drehlager,
    162,9 s im kalten LF1, umfasste auch triu, sort_indices und die
    Diagonalpruefung). ``r`` darf dafuer **nicht** aus plus/minus eins
    bestehen.

    ``D = K - K^T`` ist antisymmetrisch. Vier Stellen loeschen sich in
    **allen** betroffenen Zeilen zugleich aus:

        D[k,i] = a    D[k,j] = -a    D[i,l] = a    D[j,l] = -a

        (D r)_k = a (r_i - r_j)      (D r)_i = a (r_l - r_k)
        (D r)_j = a (r_k - r_l)      (D r)_l = a (r_j - r_i)

    Alle vier sind null, sobald r_i = r_j und r_k = r_l. Weil die Sonden
    fest gesaet sind, lassen sich solche Paare **suchen** - genau das tut
    diese Pruefung. Mit plus/minus eins meldet ``ist_symmetrisch`` dann
    "symmetrisch", obwohl die Abweichung sechs Zehnerpotenzen ueber der
    Schranke liegt; verstimmt faellt sie auf.

    Zwei einfachere Pruefkoerper treffen die Luecke **nicht**, und das ist
    der Grund, warum sie hier so umstaendlich gebaut ist: zwei
    Unsymmetrien in einer Zeile werden von den Gegeneintraegen in den
    Partnerzeilen verraten, und ein zufaelliges Vierermuster braucht
    r_i = r_j und r_k = r_l in allen vier Sonden - das traf in 300
    Versuchen kein einziges Mal.
    """
    print("")
    print("--- Die Symmetriesonde und ihre Luecke ---")
    from scipy import sparse as _sp
    from statik3d.solver import ist_symmetrisch

    n, proben, saat = 40, 4, 20260922      # wie in ist_symmetrisch
    rng = np.random.default_rng(saat)
    R = [rng.choice((-1.0, 1.0), size=n) for _ in range(proben)]

    def gleichpaar(ausser=()):
        for p in range(n):
            for q in range(p + 1, n):
                if p in ausser or q in ausser:
                    continue
                if all(r[p] == r[q] for r in R):
                    return p, q
        return None

    ij = gleichpaar()
    kl = gleichpaar(ausser=set(ij or ()))
    check("Indexpaare mit gleichem Vorzeichen in allen Sonden gefunden",
          ij is not None and kl is not None, f"{ij} und {kl}")
    if not ij or not kl:
        return
    i, j = ij
    k, l = kl

    A = _sp.random(n, n, density=0.3, random_state=7, format="csr")
    K = (A + A.T).tocsr()
    gross = float(abs(K).max())
    check("der Prüfkörper ist symmetrisch", ist_symmetrisch(K), f"max |K| {gross:.3e}")

    a = 1.0e-6 * gross
    M = K.tolil()
    for p, q, v in ((k, i, a), (k, j, -a), (i, l, a), (j, l, -a)):
        M[p, q] = M[p, q] + v
        M[q, p] = M[q, p] - v
    M = M.tocsr()
    d = float(abs(M - M.T).max())
    schranke = 1e-12 * gross
    check("das Muster macht die Matrix wirklich unsymmetrisch",
          d > 1e5 * schranke, f"{d:.3e} gegen Schranke {schranke:.3e}")
    check("und die verstimmte Sonde merkt es", not ist_symmetrisch(M),
          "erkannt" if not ist_symmetrisch(M)
          else "VERSCHLUCKT - die Sonde ist ungestimmt")

    # Die Empfindlichkeit darf unter der Verstimmung nicht gelitten haben
    M2 = K.tolil()
    M2[1, 2] = M2[1, 2] + 1.0e-11 * gross
    check("eine einzelne Stoerung von 1e-11 faellt weiter auf",
          not ist_symmetrisch(M2.tocsr()), "erkannt")
    M3 = K.tolil()
    M3[1, 2] = M3[1, 2] + 1.0e-14 * gross
    check("eine unter der Schranke gilt weiter als symmetrisch",
          ist_symmetrisch(M3.tocsr()), "nicht angeschlagen")


def test_pardiso_faellt_nicht_still_aus():
    """Scheitert PARDISO bei "automatisch", steht der Grund da.

    Bis zum 22.09.2026 wurde bei der Wahl "automatisch" jede Ausnahme von
    PARDISO verworfen (``except Exception: if be == "pardiso": raise``),
    und es ging ohne eine Zeile ueber CHOLMOD nach SuperLU. Am Drehlager
    scheitert SuperLU dann selbst - gemessen von der Loesersitzung:
    "Can't expand MemType 0: jcol 412895", SystemError -, und warum PARDISO
    nicht gerechnet hatte, war nicht mehr festzustellen.

    Zweite Falle, die die Kur nicht einbauen darf: ein RuntimeError beim
    Aufbau wird als singulaere Matrix gedeutet ("Lagerung pruefen"). Scheitern
    beide Loeser aus einem anderen Grund, ist das die falsche Diagnose - darum
    eine eigene Ausnahmeart.
    """
    import pypardiso
    from scipy import sparse as _sp
    from statik3d import solver as S

    n = 12
    K = _sp.diags([np.full(n - 1, -1.0), np.full(n, 4.0), np.full(n - 1, -1.0)],
                  [-1, 0, 1], format="csc")
    b = np.ones(n)
    echt_fak = pypardiso.PyPardisoSolver.factorize
    echt_splu = S.splu

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        ls = S.LinearSolver(K, backend="auto")
        check("PARDISO faellt aus, es wird ausgewichen", ls.backend == "superlu",
              ls.backend)
        check("und der Grund steht am Loeser",
              "PARDISO" in ls.ausweichgrund and "verweigert" in ls.ausweichgrund,
              ls.ausweichgrund)
        check("die Beschreibung im Fortschritt nennt ihn",
              "ausgewichen" in ls.beschreibung(), ls.beschreibung()[:90])
        x = ls.solve(b)
        close("die Loesung stimmt trotzdem",
              float(np.abs(K @ x - b).max()), 0.0, 1e-12)

        # beide scheitern, nicht an Singularitaet
        def speicher(*a, **kw):
            raise SystemError("Can't expand MemType 0: jcol 412895")

        S.splu = speicher
        try:
            S.LinearSolver(K, backend="auto")
            check("scheitern beide, bricht es mit beiden Gruenden ab", False,
                  "lief durch")
        except S.LoeserAusfall as ex:
            check("scheitern beide, bricht es mit beiden Gruenden ab",
                  "PARDISO" in str(ex) and "MemType" in str(ex), str(ex)[:100])
        except Exception as ex:          # noqa: BLE001
            check("scheitern beide, bricht es mit beiden Gruenden ab", False,
                  f"{type(ex).__name__}: {ex}"[:100])
        check("und nicht als RuntimeError - der hiesse 'Lagerung pruefen'",
              not issubclass(S.LoeserAusfall, RuntimeError))

        # singulaer bleibt singulaer - nur mit Zusatz
        def singulaer(*a, **kw):
            raise RuntimeError("Factor is exactly singular")

        S.splu = singulaer
        try:
            S.LinearSolver(K, backend="auto")
            check("eine singulaere Matrix bleibt ein RuntimeError", False, "lief durch")
        except S.LoeserAusfall as ex:
            check("eine singulaere Matrix bleibt ein RuntimeError", False,
                  f"LoeserAusfall: {ex}"[:90])
        except RuntimeError as ex:
            check("eine singulaere Matrix bleibt ein RuntimeError",
                  "singular" in str(ex) and "PARDISO" in str(ex), str(ex)[:100])
    finally:
        pypardiso.PyPardisoSolver.factorize = echt_fak
        S.splu = echt_splu

    # Die 32-Bit-Grenze ist ebenso ein Ausweichgrund: scheitert danach
    # SuperLU, muss sie in der Meldung stehen - sonst kaeme die rohe Ausnahme.
    echt_passt = S.LinearSolver._passt_in_int32
    S.LinearSolver._passt_in_int32 = lambda self, K, verlangt: False
    S.splu = speicher
    try:
        S.LinearSolver(K, backend="auto")
        check("auch die 32-Bit-Grenze steht im Abbruch", False, "lief durch")
    except S.LoeserAusfall as ex:
        check("auch die 32-Bit-Grenze steht im Abbruch", "32-Bit" in str(ex), str(ex)[:100])
    except Exception as ex:              # noqa: BLE001
        check("auch die 32-Bit-Grenze steht im Abbruch", False,
              f"{type(ex).__name__}: {ex}"[:100])
    finally:
        S.LinearSolver._passt_in_int32 = echt_passt
        S.splu = echt_splu

    # Ein installiertes, aber scheiterndes CHOLMOD ist ein Grund; ein fehlendes
    # (der Regelfall) nicht.
    import sys as _sys
    import types as _types
    falsch = _types.ModuleType("sksparse.cholmod")

    def _chol(A):
        raise ValueError("Probe: nicht positiv definit")

    falsch.cholesky = _chol
    alt_mod = {k: _sys.modules.get(k) for k in ("sksparse", "sksparse.cholmod")}
    _sys.modules["sksparse"] = _types.ModuleType("sksparse")
    _sys.modules["sksparse.cholmod"] = falsch
    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        ls3 = S.LinearSolver(K, backend="auto")
        check("ein scheiterndes CHOLMOD steht mit im Grund",
              "PARDISO" in ls3.ausweichgrund and "CHOLMOD" in ls3.ausweichgrund,
              ls3.ausweichgrund[:100])
    finally:
        pypardiso.PyPardisoSolver.factorize = echt_fak
        for k, v in alt_mod.items():
            if v is None:
                _sys.modules.pop(k, None)
            else:
                _sys.modules[k] = v

    # Gegenprobe: ohne Ausfall kein Grund und keine Zusatzangabe
    ls2 = S.LinearSolver(K, backend="auto")
    check("ohne Ausfall bleibt der Grund leer", ls2.ausweichgrund == "",
          repr(ls2.ausweichgrund))


def test_ausweichen_erreicht_den_fortschritt_auch_im_kontakt():
    """Der Ausweichgrund steht im Fortschritt - auch bei den
    Faktorisierungen der Kontaktschritte.

    Die Zeile "Faktorisiert (...)" gibt es nur fuer die Grundfaktorisierung.
    Ein Kontaktmodell faktorisiert aber in jedem Schritt neu (am Drehlager
    145-mal je Lastfall), und dort meldete das Ausweichen nichts - es ging
    nur ueber warnings.warn, und das erreicht das Protokollfenster nicht.
    """
    import pypardiso
    from statik3d import solver as S
    from statik3d.examples_lib import block_friction_example
    m = block_friction_example()
    zeilen = []
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        S.solve_static(m, progress=lambda *a: zeilen.append(" ".join(str(x) for x in a)))
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
    check("der Fortschritt nennt das Ausweichen",
          any("ausgewichen" in z for z in zeilen),
          next((z for z in zeilen if "ausgewichen" in z), "keine Zeile")[:100])
    check("und zwar einmal je System, nicht je Faktorisierung",
          sum(1 for z in zeilen if "Gleichungslöser ausgewichen" in z) <= 1,
          str(sum(1 for z in zeilen if "Gleichungslöser ausgewichen" in z)))


def _k2_modell():
    """Kragarm aus sechs Staeben, zwei Lastfaelle und eine ueberlagerte
    Kombination - klein genug, dass jeder Loeser ihn in Millisekunden rechnet."""
    from statik3d import mesher
    m = Model("k2")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S235", "R", (0, 0, 0), (2.0, 0, 0), 6)
    m.fix(ids[0], "all")
    m.add_load_case("LF1", "G")
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fz=-1.0e4, case="LF1")
    m.load_node(ids[-1], Fy=2.0e3, case="LF2")
    m.add_combination("K1", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    return m


def test_ausweichgrund_erreicht_ergebnis_bericht_und_modalanalyse():
    """Der Ausweichgrund gehoert ans Ergebnis, nicht nur in den Fortschritt.

    Befund K2 (22.09.2026): ``_log_einmal`` meldet ueber warnings.warn - das
    erreicht weder das Protokollfenster noch die exe. Die Fortschrittszeile
    aus 54b6f9a gibt es nur, wenn ein Fortschritt mitlaeuft. Rechenketten,
    Pool und Farm rechnen ohne (jobs._job_solve_kette ruft solve_cases ohne
    progress): gemessen mit PARDISO im Prozess zum Scheitern gebracht stand in
    ``res.info`` nur "superlu", der Bericht nannte das Ausweichen nicht, und
    solve_modal meldete es weder im Fortschritt noch am Ergebnis.
    """
    import re
    import pypardiso
    from statik3d import solver as S
    from statik3d.report.html import Report
    alt_backend = parallel.settings().solver_backend
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        # 1. Ohne Fortschritt - so rechnen Ketten, Pool und Farm
        r = S.solve_static(_k2_modell(), case="LF1")
        grund = str(r.info.get("ausweichgrund", ""))
        check("ohne Fortschritt traegt das Ergebnis den Grund",
              "PARDISO" in grund and "verweigert" in grund, repr(grund)[:90])
        check("und die Zusammenfassung des Ergebnisses nennt ihn",
              "ausgewichen" in r.summary() and "verweigert" in r.summary(),
              next((z for z in r.summary().splitlines() if "ausgewichen" in z),
                   "keine Zeile")[:90])

        # 2. Alles mit Bericht: gleiche Gruende werden zu einer Zeile
        m = _k2_modell()
        an = S.solve_all(m)
        traeger = sorted(n for n, x in an.all_results().items()
                         if "verweigert" in str(x.info.get("ausweichgrund", "")))
        check("jedes Ergebnis traegt ihn, auch die ueberlagerte Kombination",
              traeger == ["K1", "LF1", "LF2"], str(traeger))
        html = Report(m, an).html()
        punkte = [p for p in re.findall(r"<li>(.*?)</li>", html, re.S) if "ausgewichen" in p]
        check("der Bericht nennt ihn unter den Hinweisen - eine Zeile fuer drei Ergebnisse",
              len(punkte) == 1 and "verweigert" in punkte[0] and "3 Ergebnis" in punkte[0],
              f"{len(punkte)} Zeilen: " + (punkte[0][:90] if punkte else ""))
        check("der Grund steht einmal im Bericht, nicht je Ergebnis",
              html.count("Probe: PARDISO verweigert") == 1,
              f"{html.count('Probe: PARDISO verweigert')} mal")
        zf = an.summary()
        check("die Zusammenfassung der Oberflaeche nennt ihn einmal",
              zf.count("verweigert") == 1, f"{zf.count('verweigert')} mal")

        # 3. Modalanalyse: Fortschritt und Ergebnis
        zeilen = []
        rm = S.solve_modal(_k2_modell(), nmodes=3,
                           progress=lambda *a: zeilen.append(" ".join(str(x) for x in a)))
        n_z = sum(1 for z in zeilen if "ausgewichen" in z)
        check("die Modalanalyse meldet ihn im Fortschritt, einmal", n_z == 1, f"{n_z} Zeilen")
        check("und traegt ihn am Ergebnis",
              "verweigert" in str(rm.info.get("ausweichgrund", "")),
              repr(rm.info.get("ausweichgrund"))[:90])

        # 4. Theorie II. Ordnung ersetzt die lineare Kombination - ihr
        #    Ergebnis muss den Grund selbst tragen
        from statik3d.theorie2 import solve_theorie2
        r2, _i2 = solve_theorie2(_k2_modell(), {"LF1": 1.35, "LF2": 1.5}, "K1")
        check("das Ergebnis nach Theorie II. Ordnung traegt ihn",
              "verweigert" in str(r2.info.get("ausweichgrund", "")),
              repr(r2.info.get("ausweichgrund"))[:90])
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        parallel.configure(solver_backend=alt_backend)

    # Gegenprobe: ohne Ausfall steht nichts da
    m0 = _k2_modell()
    an0 = S.solve_all(m0)
    check("ohne Ausfall traegt kein Ergebnis einen Grund",
          not any("ausweichgrund" in x.info for x in an0.all_results().values()),
          str([n for n, x in an0.all_results().items() if "ausweichgrund" in x.info]))
    check("und der Bericht nennt kein Ausweichen",
          "ausgewichen" not in Report(m0, an0).html())


def _zwei_wuerfel():
    """Zwei hex8-Wuerfel mit nur einem gemeinsamen Knoten (wie
    tests/test_singular.py): B dreht fast ohne Steifigkeit um den Knoten,
    SuperLU faktorisiert, das Residuum reisst die Schranke."""
    m = Model("zwei")
    m.add_material(Material.steel("S235"))
    A = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    B = np.array([[2, 1, 0], [2, 2, 0], [1, 2, 0],
                  [1, 1, 1], [2, 1, 1], [2, 2, 1], [1, 2, 1.]])
    m.add_nodes(np.vstack([A, B]))
    m.add_element("hex8", [0, 1, 2, 3, 4, 5, 6, 7], "S235", group="A")
    m.add_element("hex8", [2, 8, 9, 10, 11, 12, 13, 14], "S235", group="B")
    for k in range(4):
        m.fix(k, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.load_node(13, Fz=-1000.0)
    return m


def test_singulaer_nach_ausweichen_nennt_den_grund():
    """Reisst die Loesung eines ausgewichenen Loesers die Residuumsschranke,
    gehoert der Grund des Ausweichens in die Meldung - so, wie ihn das
    Scheitern der SuperLU-Faktorisierung schon anhaengt ("(vorher: ...)").
    Bis zum 23.09.2026 fehlte er in "Gleichungssystem numerisch singulaer
    (Residuum ...)" (Nebenbefund 2). Ein Skript ohne Fortschritt sah ihn nur
    als RuntimeWarning von _log_einmal auf der Konsole, einmal je
    Programmlauf - gemessen 24.09.2026 am Stand ec6448c mit diesem Aufbau;
    in der Meldung, mit der die Rechnung abbricht, stand er nicht."""
    try:
        import pypardiso
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - Ausweichen in der Singularitaetsmeldung uebersprungen", True)
        return
    from statik3d import solver as S
    alt_backend = parallel.settings().solver_backend
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        try:
            S.solve_static(_zwei_wuerfel(), case="LF1", workers=1)
            check("ausgewichen und singulaer: die Meldung nennt den Grund", False, "lief durch")
        except RuntimeError as ex:
            kopf = str(ex).splitlines()[0]
            check("ausgewichen und singulaer: die Meldung nennt den Grund",
                  "numerisch singulaer" in kopf and "ausgewichen" in kopf
                  and "Probe: PARDISO verweigert" in kopf, kopf[:240])
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
    # Gegenprobe: rechnet PARDISO selbst, steht kein Ausweichen darin
    try:
        try:
            S.solve_static(_zwei_wuerfel(), case="LF1", workers=1)
            check("ohne Ausweichen: singulaer, aber ohne Zusatz", False, "lief durch")
        except RuntimeError as ex:
            kopf = str(ex).splitlines()[0]
            check("ohne Ausweichen: singulaer, aber ohne Zusatz",
                  "numerisch singulaer" in kopf and "ausgewichen" not in kopf, kopf[:240])
    finally:
        parallel.configure(solver_backend=alt_backend)


def test_ausweichloeser_und_buendelung_je_art():
    """Die Hinweiszeile nennt den Loeser, auf den ausgewichen wurde, und
    buendelt Gruende derselben Art auch innerhalb eines Ergebnisses.

    Gegenpruefung von 4a8c464 (23.09.2026):
    1. "gerechnet mit ..." kam aus info["solver"], dem Loeser der **letzten**
       Faktorisierung. Scheiterte PARDISO nur beim ersten von sieben
       Versuchen, hiess es "gerechnet mit MKL PARDISO" - neben einem Grund,
       der sagt, dass PARDISO nicht rechnete.
    2. Ein Kontaktlastfall, dessen Nichtnullen sich zwischen den Schritten
       aendern, trug zwei 32-Bit-Gruende mit "; " verbunden; die Buendelung
       machte daraus eine eigene Zeile neben der seiner Nachbarn.
    """
    import re
    import warnings
    import pypardiso
    from statik3d import solver as S
    from statik3d.examples_lib import block_friction_example
    from statik3d.report.html import Report
    alt_backend = parallel.settings().solver_backend
    alt_grenze = S.INT32_MAX
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize
    versuche = {"n": 0}

    def einmal_aus(self, A):
        versuche["n"] += 1
        if versuche["n"] == 1:
            raise RuntimeError("Probe: PARDISO nur beim ersten Mal aus")
        return echt(self, A)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # 1. PARDISO faellt nur in der ersten Faktorisierung aus
            m = block_friction_example()
            pypardiso.PyPardisoSolver.factorize = einmal_aus
            try:
                an = S.solve_all(m, combinations=False)
            finally:
                pypardiso.PyPardisoSolver.factorize = echt
            r = an.all_results()["LF1"]
            check("Vorbedingung: nur teilweise ausgefallen, zuletzt rechnete PARDISO",
                  versuche["n"] > 1 and r.info.get("solver") == "pardiso",
                  f"{versuche['n']} Versuche, solver={r.info.get('solver')!r}")
            check("das Ergebnis nennt SuperLU als Ausweichloeser",
                  [lo for _g, lo in (r.info.get("ausweichen") or [])] == ["superlu"],
                  repr(r.info.get("ausweichen"))[:120])
            zeilen = [z for z in an.summary().splitlines() if "ausgewichen" in z]
            check("die Zusammenfassung nennt SuperLU, nicht PARDISO als den Loeser, der rechnete",
                  len(zeilen) == 1 and "stattdessen rechnete SuperLU" in zeilen[0]
                  and "MKL PARDISO" not in zeilen[0],
                  (zeilen[0] if zeilen else "keine Zeile")[60:200])
            zr = [z for z in r.summary().splitlines() if "ausgewichen" in z]
            check("ebenso die Zusammenfassung des Ergebnisses",
                  len(zr) == 1 and "SuperLU" in zr[0], (zr[0] if zr else "keine Zeile")[:160])
            html = Report(m, an).html()
            li = [p for p in re.findall(r"<li>(.*?)</li>", html, re.S) if "ausgewichen" in p]
            check("der Bericht nennt SuperLU, nicht PARDISO",
                  len(li) == 1 and "stattdessen rechnete SuperLU" in li[0]
                  and "MKL PARDISO" not in li[0], (li[0] if li else "keine Zeile")[60:200])
            i = html.find("Gleichungslöser</")
            anhang = re.sub(r"<[^>]+>", " ", html[i:i + 400]) if i >= 0 else ""
            check("der Anhang nennt den Ausweichloeser",
                  "ausgewichen auf SuperLU" in anhang, " ".join(anhang.split())[:140])

            # 2. Ausweichen ueber die 32-Bit-Grenze (auf 50 gesenkt) an einem
            #    kippenden Block: die Kante hebt ab, die Nichtnullen aendern sich
            S.INT32_MAX = 50
            m2 = block_friction_example()
            top = [k for k in range(len(m2.nodes)) if abs(m2.nodes[k][2] - 0.4) < 1e-9]
            m2.add_load_case("LF2", "Q", "Kippen")
            for n in top:
                m2.load_node(n, Fz=-20000.0 / len(top), Fx=15000.0 / len(top), case="LF2")
            m2.add_combination("K1", {"LF1": 1.0, "LF2": 1.0}, "ULS")
            an2 = S.solve_all(m2)
            erg = an2.all_results()
            texte = {n: str(x.info.get("ausweichgrund") or "") for n, x in erg.items()}
            check("Vorbedingung: die Gruende tragen verschiedene Eintragszahlen",
                  len(set(texte.values())) > 1 and all(texte.values()),
                  str({n: re.findall(r"\d+ Einträge", t) for n, t in texte.items()}))
            check("jedes Ergebnis traegt je Art einen Grund, nicht einen je Eintragszahl",
                  all(t.count("PARDISO:") == 1 for t in texte.values()),
                  str({n: t.count("PARDISO:") for n, t in texte.items()}))
            zs = S.ausweichen_gebuendelt(erg.items())
            check("eine Zeile fuer alle drei Ergebnisse",
                  len(zs) == 1 and "3 Ergebnissen" in zs[0],
                  f"{len(zs)} Zeilen: " + " | ".join(z[:70] for z in zs))
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        S.INT32_MAX = alt_grenze
        parallel.configure(solver_backend=alt_backend)


def test_ketten_rechnen_mit_den_einstellungen_des_hauptprozesses():
    """Unter spawn beginnt jeder Kettenprozess mit den Vorgaben.

    Bis zum 22.09.2026 rechnete eine Kette darum mit solver_backend "auto"
    statt dem gespeicherten "pardiso" und mit der Vorgabegenauigkeit - und
    wich still aus, wo der Hauptprozess abgebrochen haette.
    """
    from statik3d import jobs, parallel, solver as S
    from statik3d.model import Material, Model, Section
    st = parallel.settings()
    alt = {k: getattr(st, k) for k in S.KETTEN_EINSTELLUNGEN}
    try:
        for k, v in alt.items():
            parallel.configure(**{k: getattr(parallel.Settings(), k)})
        check("mit Vorgaben geht nichts mit (aeltere Arbeiter bleiben brauchbar)",
              S.kettenauftrag_einstellungen(st) == {},
              str(S.kettenauftrag_einstellungen(st)))
        parallel.configure(solver_backend="pardiso", solver_residuum=1e-9)
        ein = S.kettenauftrag_einstellungen(st)
        check("abweichende Einstellungen gehen mit",
              ein == {"solver_backend": "pardiso", "solver_residuum": 1e-9}, str(ein))

        # Der Auftrag wendet sie an - und uebergeht, was er nicht kennt
        parallel.configure(solver_backend="auto", solver_residuum=1e-6)
        m = Model("kette")
        m.add_material(Material.steel("S235"))
        m.add_section(Section.rectangle("R", 0.1, 0.2))
        a, b = m.add_node(0, 0, 0), m.add_node(2, 0, 0)
        m.add_element("beam", [a, b], "S235", "R")
        m.fix(a, "all")
        m.load_node(b, Fz=-1000.0)
        jobs._job_solve_kette(model=m.to_dict(), cases=[m.active_case or "LF1"],
                              einstellungen={"solver_backend": "superlu",
                                             "gibt_es_nicht": 1})
        check("der Kettenauftrag rechnet mit der Einstellung des Hauptprozesses",
              parallel.settings().solver_backend == "superlu",
              parallel.settings().solver_backend)
    finally:
        parallel.configure(**alt)


def test_ketten_teilen_sich_die_threads():
    """Die eingestellte Threadzahl ist das Budget des Rechners, nicht einer
    Kette.

    Bis zum 22.09.2026 bekam jede Rechenkette die volle Einstellung. Beim
    Anwender stehen 31 in einstellungen.json - sechs Ketten forderten damit je
    31 Loeser-Threads; MKL kappt nur innerhalb eines Prozesses auf die 16
    physischen Kerne, also bis zu 96 auf 16 Kernen. Ohne Einstellung wurde
    schon immer geteilt.
    """
    from statik3d import solver as S, parallel as P
    check("31 eingestellt, sechs Ketten: je 5", S.threads_je_kette(31, 6) == 5,
          str(S.threads_je_kette(31, 6)))
    check("nie weniger als einer", S.threads_je_kette(4, 8) == 1,
          str(S.threads_je_kette(4, 8)))
    check("ohne Einstellung wie bisher: Kerne minus eins, geteilt",
          S.threads_je_kette(0, 3) == max(1, (P.cpu_count() - 1) // 3),
          str(S.threads_je_kette(0, 3)))
    check("die Probe ist scharf: die alte Regel gaebe 31",
          (31 or 0) == 31 and S.threads_je_kette(31, 6) != 31)


def test_abbruchmeldung_nennt_ihren_lauf():
    """Welcher Kontaktlauf hat aufgegeben - und war es der letzte?

    Mit Plastizitaet rechnet derselbe Lastfall viele Kontaktlaeufe (am
    Drehlager zwoelf). Die Meldung "Nachpruefung der Reibung ... abgebrochen"
    nannte keinen Lauf, und gleichlautende Zeilen wurden zu einer
    zusammengefasst: eine Zeile konnte fuer 1 bis 12 gekappte Laeufe stehen,
    und ob der letzte dabei war - aus dem u und sigma stammen -, war nicht
    festzustellen (Nachpruefung der Loesersitzung, 22.09.2026).
    """
    from statik3d.solver import _kontakt_info_sammeln

    class Erg:
        def __init__(self):
            self.info = {}

    text = ("Kontakt: Nachprüfung der Reibung nach 40 Zustandswechseln "
            "abgebrochen - das Ergebnis ist nicht auskonvergiert")

    def lauf(ok):
        return {"contact_iterations": 5, "contact_converged": ok,
                "contact_abbruch": "" if ok else text,
                "contact_log": [] if ok else [text]}

    r = Erg()
    for ok in (True, False, False, True):
        r.info.update(_kontakt_info_sammeln(r, lauf(ok)))
    log = r.info["contact_log"]
    check("jeder gekappte Lauf steht einzeln da",
          sum(1 for z in log if "abgebrochen" in z) == 2, str(log)[:120])
    check("mit seiner Nummer",
          any("(Kontaktlauf 2)" in z for z in log)
          and any("(Kontaktlauf 3)" in z for z in log), str(log)[:120])
    check("der Lastfall gilt als nicht konvergiert",
          r.info["contact_converged"] is False)
    check("und es steht da, dass der letzte Lauf konvergiert ist",
          r.info["contact_letzter_lauf_konvergiert"] is True)
    check("zwei von vier Laeufen gekappt",
          r.info["contact_laeufe_nicht_konvergiert"] == 2
          and r.info["contact_laeufe"] == 4,
          f"{r.info['contact_laeufe_nicht_konvergiert']} von {r.info['contact_laeufe']}")

    r2 = Erg()
    for ok in (True, True, False):
        r2.info.update(_kontakt_info_sammeln(r2, lauf(ok)))
    check("war der letzte gekappt, steht das ebenso da",
          r2.info["contact_letzter_lauf_konvergiert"] is False)


def _laplace_2d(n: int) -> sparse.csr_matrix:
    """5-Punkt-Laplace mit Dirichlet-Rand auf n x n: regulaer, positiv definit."""
    e = np.ones(n)
    T = sparse.diags([-e[:-1], 2.0 * e, -e[:-1]], [-1, 0, 1])
    I_ = sparse.identity(n)
    return (sparse.kron(T, I_) + sparse.kron(I_, T)).tocsr()


def test_pardiso_zaehlt_gestoerte_pivots():
    """iparm(14) ist die Zahl der Pivots, die MKL angehoben hat - gezeigt an
    einer kleinen Matrix, nicht aus der Doku uebernommen.

    Der Dirichlet-Laplace ist regulaer: 0. Ein entkoppelter Block [[1, 1],
    [1, 1]] hat nach einem Eliminationsschritt den Pivot 1 - 1*1/1 = 0, exakt;
    MKL hebt ihn an (iparm(10) = 13, also auf rund 1e-13 der Matrixnorm)
    statt abzubrechen: 1. Drei solche Bloecke: 3. Gemessen 22.09.2026 mit dem
    mkl_rt.3.dll der Programmumgebung, ein Thread: 0 / 1 / 3.
    """
    try:
        import pypardiso                                        # noqa: F401
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - gestoerte Pivots uebersprungen", True)
        return
    from statik3d import solver as S
    L = _laplace_2d(6)
    B = sparse.csr_matrix(np.array([[1.0, 1.0], [1.0, 1.0]]))
    ls0 = LinearSolver(L, backend="pardiso")
    ls1 = LinearSolver(sparse.block_diag([L, B]).tocsr(), backend="pardiso")
    ls3 = LinearSolver(sparse.block_diag([L, B, B, B]).tocsr(), backend="pardiso")
    check("regulaere Matrix: kein Pivot angehoben", ls0.gestoerte_pivots == 0,
          repr(ls0.gestoerte_pivots))
    check("ein Block mit Pivot 0: einer angehoben", ls1.gestoerte_pivots == 1,
          repr(ls1.gestoerte_pivots))
    check("drei Bloecke: drei angehoben", ls3.gestoerte_pivots == 3,
          repr(ls3.gestoerte_pivots))
    check("der Loeser nennt seinen Matrixtyp (unsymmetrisch, 11)", ls0.mtype == 11,
          repr(ls0.mtype))
    kz = ls1.pardiso_kennzahlen
    check("die Kennzahlen tragen iparm(18) als nnz, wie nnz_faktor",
          kz.get("nnz") == ls1.nnz_faktor and ls1.nnz_faktor > 0,
          f"{kz.get('nnz')} / {ls1.nnz_faktor}")
    check("die Eingabefelder stehen da, wie MKL sie zurueckgibt",
          set(kz.get("eingabe", {})) == {str(i) for i in S.PARDISO_EINGABEFELDER}
          and kz["eingabe"]["10"] == 13, str(kz.get("eingabe")))
    check("der Speicher ist als 'laut Doku' gekennzeichnet",
          set(kz.get("speicher_kb", {})) == {"15", "16", "17"}
          and "laut" in kz.get("speicher_einheit", ""), str(kz.get("speicher_kb")))
    lu = LinearSolver(L, backend="superlu")
    check("SuperLU meldet keine Zahl - None, nicht 0", lu.gestoerte_pivots is None
          and lu.mtype is None, f"{lu.gestoerte_pivots!r} / {lu.mtype!r}")


def test_residuum_gehoert_zur_loesung():
    """``LinearSolver.residuum`` beschreibt die Loesung, die solve() gerade
    gerechnet hat. Ohne Pruefung (check=False) gibt es keins: nan, nicht die
    Zahl der vorigen Loesung - die schriebe der Loeser-Nachweis sonst dem
    Lastfall zu. Das Buch zaehlt nan nicht als gemessen (Gegenpruefung
    22.09.2026: die Aenderung stand ohne Test da)."""
    from statik3d.solver import _LoeserBuch
    L = _laplace_2d(6)
    b = np.arange(1.0, L.shape[0] + 1.0)
    ls = LinearSolver(L, backend="superlu")
    ls.solve(b)
    r1 = ls.residuum
    check("mit Pruefung: ein gemessenes Residuum", np.isfinite(r1) and r1 < 1e-10, repr(r1))
    ls.solve(b, check=False)
    check("ohne Pruefung: nan, nicht das der vorigen Loesung", np.isnan(ls.residuum),
          repr(ls.residuum))
    buch = _LoeserBuch(0.0)
    buch.loesung(ls)
    check("das Buch zaehlt eine Loesung ohne Residuum nicht als gemessen",
          buch.residuum_gemessen == 0 and buch.residuum_max is None,
          f"{buch.residuum_gemessen} / {buch.residuum_max!r}")
    ls.solve(b)
    buch.loesung(ls)
    check("wohl aber die naechste gepruefte",
          buch.residuum_gemessen == 1 and buch.residuum_max == ls.residuum,
          f"{buch.residuum_gemessen} / {buch.residuum_max!r}")


def _block_zwei_lastfaelle():
    """Der Block mit Reibung und ein zweiter Lastfall mit umgekehrter
    Horizontallast - beide rechnen Kontakt und faktorisieren."""
    from statik3d.examples_lib import block_friction_example
    m = block_friction_example()
    erster = m.active_case
    oben = [nl.node for nl in m.case(erster).nodal_loads]
    m.add_load_case("LF2", "Q")
    for n in oben:
        m.load_node(n, Fz=-90000.0 / len(oben), Fx=-15000.0 / len(oben), case="LF2")
    return m, erster


def test_loeser_nachweis_je_lastfall():
    """Der Loeser-Nachweis gilt dem Lastfall, nicht dem Rechensystem.

    ``zeit_faktorisierung`` summiert ueber das System (so dokumentiert,
    Theoriehandbuch 1.3); in einer Kette waechst der Wert von Lastfall zu
    Lastfall. Die Nachpruefung der Loesersitzung (22.09.2026) musste die
    Faktorisierungszeit je Lastfall deshalb aus Differenzen rechnen
    (1190,1 - 734,8 = 455,3 s). Der Nachweis traegt sie jetzt selbst - und
    zaehlt dort, wo geloest wird: welcher Loeser, wie oft, mit welchen Threads,
    und das groesste Residuum.
    """
    from statik3d.solver import StaticSystem, loeser_da, solve_cases
    m, erster = _block_zwei_lastfaelle()
    alt = parallel.settings().solver_backend
    try:
        parallel.configure(solver_backend="auto")
        system = StaticSystem(m)
        out = solve_cases(m, [erster, "LF2"], system=system)
    finally:
        parallel.configure(solver_backend=alt)
    n1 = out[erster].info.get("loeser_nachweis")
    n2 = out["LF2"].info.get("loeser_nachweis")
    if not check("jeder Lastfall traegt einen Loeser-Nachweis",
                 isinstance(n1, dict) and isinstance(n2, dict), repr(n2)[:80]):
        return
    z1 = out[erster].info["zeit_faktorisierung"]
    z2 = out["LF2"].info["zeit_faktorisierung"]
    check("'zeit_faktorisierung' bleibt die Summe des Systems (wie dokumentiert)",
          z2 > z1 > 0.0, f"{z1:.4f} / {z2:.4f} s")
    close("der zweite Lastfall hat nur seine eigene Faktorisierungszeit",
          n2["zeit_faktorisierung_lastfall"], z2 - z1, 1e-12, "s")
    check("und die ist kleiner als die Summe",
          0.0 < n2["zeit_faktorisierung_lastfall"] < z2,
          f"{n2['zeit_faktorisierung_lastfall']:.4f} von {z2:.4f} s")
    for name, n in ((erster, n1), ("LF2", n2)):
        info = out[name].info
        check(f"{name}: Faktorisierungen des Lastfalls = die der Kontaktschritte",
              n["faktorisierungen"] == info.get("contact_factorisations"),
              f"{n['faktorisierungen']} / {info.get('contact_factorisations')}")
        check(f"{name}: je Kontaktschritt eine Loesung, gezaehlt beim Loesen",
              sum(n["loesungen"].values()) == info.get("contact_iterations"),
              f"{n['loesungen']} / {info.get('contact_iterations')}")
    if loeser_da("pardiso"):
        check("PARDISO hat geloest, mit mtype 11 und seinen Threads",
              set(n2["loesungen"]) == {"pardiso"} and set(n2["mtype"]) == {"11"}
              and n2["threads"], f"{n2['loesungen']} {n2['mtype']} {n2['threads']}")
        check("gestoerte Pivots gezaehlt (Summe und Hoechstwert)",
              n2["gestoerte_pivots_summe"] == 0 and n2["gestoerte_pivots_max"] == 0,
              f"{n2['gestoerte_pivots_summe']} / {n2['gestoerte_pivots_max']}")
    schranke = LinearSolver.genauigkeit()[0]
    for name, n in ((erster, n1), ("LF2", n2)):
        r = n.get("residuum_linear_max")
        check(f"{name}: 0 < groesstes Residuum <= Schranke {schranke:g}",
              r is not None and 0.0 < r <= schranke, repr(r))
    check("kein Ausweichen, keine Gruende", not n1["ausweichgruende"]
          and not n2["ausweichgruende"], str(n2["ausweichgruende"]))


def test_loeser_nachweis_nennt_das_ausweichen():
    """Weicht PARDISO aus, steht es im Nachweis des Lastfalls - mit Grund.

    Gezaehlt wird beim Loesen, nicht beim Faktorisieren: ein lineares Modell
    faktorisiert beim Aufstellen des Systems, also **vor** dem Lastfall. Ein
    Nachweis, der nur Faktorisierungen zaehlte, bliebe hier leer (Einwand der
    Gegenprobe zum Entwurf, 22.09.2026).

    Zwei Threads fuer PARDISO sind eingestellt, damit die Threadzahl des
    Ersatzes etwas zeigt: PARDISO setzt sie vor ps.factorize, und bis zur
    Gegenpruefung (22.09.2026) blieb sie nach dem Ausweichen stehen - der
    Nachweis nannte "1x SuperLU (2 Threads)".
    """
    import pypardiso
    from statik3d.solver import solve_static
    m, _L, _A = _zugstab()
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    alt = parallel.settings().solver_backend
    alt_t = parallel.settings().solver_threads
    try:
        parallel.configure(solver_backend="auto", solver_threads=2)
        res = solve_static(m)
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        parallel.configure(solver_backend=alt, solver_threads=alt_t)
    n = res.info.get("loeser_nachweis") or {}
    check("SuperLU hat geloest, einmal", n.get("loesungen") == {"superlu": 1},
          str(n.get("loesungen")))
    check("mit einem Thread, nicht mit den zwei von PARDISO",
          n.get("threads") == {"1": 1}, str(n.get("threads")))
    check("und ohne PARDISO-Matrixtyp", n.get("mtype") == {}, str(n.get("mtype")))
    gruende = n.get("ausweichgruende") or {}
    check("der Grund steht im Nachweis, mit der Zahl der Loesungen",
          any("PARDISO" in g and "verweigert" in g for g in gruende)
          and sum(gruende.values()) == 1, str(gruende)[:100])
    check("die Faktorisierung lag vor dem Lastfall: 0 im Lastfall",
          n.get("faktorisierungen") == 0 and n.get("zeit_faktorisierung_lastfall") == 0.0,
          f"{n.get('faktorisierungen')} / {n.get('zeit_faktorisierung_lastfall')}")
    check("SuperLU meldet keine gestoerten Pivots - keine Zahl statt 0",
          n.get("gestoerte_pivots_max") is None, repr(n.get("gestoerte_pivots_max")))
    z = res.summary()
    check("die Zusammenfassung nennt das Ausweichen",
          "Ausgewichen" in z and "verweigert" in z,
          next((x for x in z.splitlines() if "Ausgewichen" in x), "keine Zeile")[:100])
    zeile = next((x for x in z.splitlines() if x.startswith("Lösungen")), "keine Zeile")
    check("die Zeile Lösungen sagt: SuperLU einkernig", "1× SuperLU (einkernig)" in zeile,
          zeile[:100])


def test_zusammenfassung_nennt_gestoerte_pivots():
    """Gestoerte Pivots stehen in der Zusammenfassung, wenn es welche gab -
    sonst keine Zeile (am Block mit Reibung sind es 0, eine echte Rechnung mit
    angehobenen Pivots gibt es im kleinen Test nicht)."""
    from statik3d.solver import Results
    nachweis = {"loesungen": {"pardiso": 12}, "loesungen_gescheitert": 0,
                "ausweichgruende": {}, "threads": {"16": 12}, "mtype": {"11": 12},
                "faktorisierungen": 11, "faktorisierungen_mit_gestoerten_pivots": 2,
                "gestoerte_pivots_summe": 3, "gestoerte_pivots_max": 2,
                "zeit_faktorisierung_lastfall": 1.25, "residuum_linear_max": 3.1e-13,
                "residuum_gemessen": 12, "mkl_cbwr": None}
    r = Results(name="LF1")
    r.info = {"loeser_nachweis": nachweis}
    z = r.summary()
    # Die Zeilen selbst pruefen, nicht die ganze Zusammenfassung: "3" oder
    # "12" stehen dort auch ohne diese Zeilen (etwa in "3.1e-13").
    loes = next((x for x in z.splitlines() if x.startswith("Lösungen")), "keine Zeile")
    piv = next((x for x in z.splitlines() if x.startswith("Gestörte Pivots")), "keine Zeile")
    check("die Zusammenfassung nennt Loeser, Loesungen und Faktorisierungen",
          "12× MKL PARDISO (16 Threads, mtype 11)" in loes
          and "11 Faktorisierungen in 1.250 s" in loes and "höchstens 3.1e-13" in loes,
          loes[:110])
    check("und die gestoerten Pivots: Summe, Faktorisierungen, Hoechstwert",
          "3 in 2 von 11 Faktorisierungen" in piv and "höchstens 2 " in piv, piv[:110])
    ohne = dict(nachweis, gestoerte_pivots_summe=0, gestoerte_pivots_max=0,
                faktorisierungen_mit_gestoerten_pivots=0)
    r.info = {"loeser_nachweis": ohne}
    check("ohne gestoerte Pivots keine Zeile dazu", "Gestörte Pivots" not in r.summary())


_CBWR_PROBE = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
from tests.test_loeser import _zugstab
from statik3d import parallel
from statik3d.solver import solve_static
parallel.configure(solver_backend="auto")
m, _L, _A = _zugstab()
a = solve_static(m).info["loeser_nachweis"]
os.environ["MKL_CBWR"] = "COMPATIBLE"      # nach dem Laden: MKL liest das nicht mehr
b = solve_static(m).info["loeser_nachweis"]
print("ERGEBNIS " + json.dumps({"a": a.get("mkl_cbwr"), "b": b.get("mkl_cbwr"),
                                 "loeser": a.get("loesungen")}))
"""


def test_loeser_nachweis_haelt_mkl_cbwr_fest():
    """MKL_CBWR steht im Nachweis - so, wie es beim ersten Laden von MKL galt.

    MKL liest die Variable nur beim Laden; ein spaeteres Setzen wirkt nicht.
    Gemessen 22.09.2026 (mkl_rt.3.dll, MKL_CBWR_Get(MKL_CBWR_BRANCH = 1)):
    ohne Variable 1 (BRANCH_OFF), mit AUTO 2, mit COMPATIBLE 3. Darum ein
    eigener Prozess: im Testprozess ist MKL laengst geladen.
    """
    import json
    import subprocess
    try:
        import pypardiso                                        # noqa: F401
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - MKL_CBWR uebersprungen", True)
        return
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, MKL_CBWR="AUTO", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
               PYTHONUTF8="1")
    p = subprocess.run([sys.executable, "-c", _CBWR_PROBE], cwd=wurzel, env=env,
                       capture_output=True, text=True, timeout=300)
    zeile = next((z for z in p.stdout.splitlines() if z.startswith("ERGEBNIS ")), "")
    if not check("der Probeprozess laeuft durch", p.returncode == 0 and zeile,
                 (p.stderr or p.stdout)[-160:]):
        return
    d = json.loads(zeile[len("ERGEBNIS "):])
    a, b = d.get("a") or {}, d.get("b") or {}
    check("PARDISO hat im Probeprozess geloest", d.get("loeser") == {"pardiso": 1},
          str(d.get("loeser")))
    check("die Umgebung beim Laden steht im Nachweis", a.get("umgebung") == "AUTO", str(a))
    check("und was MKL selbst meldet: AUTO (Code 2)",
          a.get("code") == 2 and a.get("zweig") == "AUTO", str(a))
    check("spaeteres Setzen aendert den festgehaltenen Wert nicht",
          b.get("umgebung") == "AUTO" and b.get("code") == 2, str(b))


_CBWR_VORGABE = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
vorher = os.environ.get("MKL_CBWR")
from tests.test_loeser import _zugstab
from statik3d import parallel
from statik3d.solver import solve_static
parallel.configure(solver_backend="auto")
m, _L, _A = _zugstab()
n = solve_static(m).info["loeser_nachweis"]
print("ERGEBNIS " + json.dumps({"vorher": vorher, "cbwr": n.get("mkl_cbwr"),
                                 "loeser": n.get("loesungen")}))
"""

_CBWR_KETTEN = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
if __name__ == "__main__":
    from statik3d import parallel, solver
    from statik3d.examples_lib import hall_frame_example
    parallel.configure(solver_backend="auto", ketten=2)
    m = hall_frame_example()
    namen = list(m.load_cases)
    gerufen = {"n": 0}
    echt = solver._cases_in_ketten
    def merken(*a, **kw):
        gerufen["n"] += 1
        return echt(*a, **kw)
    solver._cases_in_ketten = merken
    erg = solver.solve_cases(m, cases=namen)
    print("ERGEBNIS " + json.dumps({"ketten": gerufen["n"], "cbwr": {
        k: (r.info.get("loeser_nachweis") or {}).get("mkl_cbwr") for k, r in erg.items()}}))
"""


def _probe(code: str, env: dict):
    """Einen Probeprozess rechnen lassen; Rueckgabe (dict oder None, Text)."""
    import json
    import subprocess
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = subprocess.run([sys.executable, "-c", code], cwd=wurzel, env=env,
                       capture_output=True, text=True, timeout=600)
    zeile = next((z for z in p.stdout.splitlines() if z.startswith("ERGEBNIS ")), "")
    if p.returncode != 0 or not zeile:
        return None, (p.stderr or p.stdout)[-200:]
    return json.loads(zeile[len("ERGEBNIS "):]), ""


def test_mkl_cbwr_auto_ist_vorgabe():
    """MKL_CBWR=AUTO ist seit dem 23.09.2026 die Vorgabe (Entscheidung des
    Anwenders): bitgleich wiederholbar, am Drehlager LF1 gemessen rund +11 %
    Zeit. Ohne Variable rechnet MKL darum mit AUTO (MKL_CBWR_Get: Code 2);
    ein vom Anwender gesetzter Wert hat Vorrang (COMPATIBLE: Code 3). Eigene
    Prozesse, denn MKL liest die Variable nur beim ersten Laden - und der
    Testprozess hat sie beim Import des Pakets selbst schon gesetzt."""
    try:
        import pypardiso                                        # noqa: F401
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - MKL_CBWR-Vorgabe uebersprungen", True)
        return
    basis = {k: v for k, v in os.environ.items() if k != "MKL_CBWR"}
    basis.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONUTF8="1")
    d, fehler = _probe(_CBWR_VORGABE, basis)
    if not check("Probeprozess ohne MKL_CBWR laeuft durch", d is not None, fehler):
        return
    cb = d.get("cbwr") or {}
    check("vor dem Import war MKL_CBWR nicht gesetzt", d.get("vorher") is None, str(d.get("vorher")))
    check("PARDISO hat geloest", d.get("loeser") == {"pardiso": 1}, str(d.get("loeser")))
    check("ohne Variable rechnet MKL mit AUTO (Umgebung AUTO, Code 2)",
          cb.get("umgebung") == "AUTO" and cb.get("code") == 2 and cb.get("zweig") == "AUTO", str(cb))
    d2, fehler2 = _probe(_CBWR_VORGABE, dict(basis, MKL_CBWR="COMPATIBLE"))
    if not check("Probeprozess mit MKL_CBWR=COMPATIBLE laeuft durch", d2 is not None, fehler2):
        return
    cb2 = d2.get("cbwr") or {}
    check("ein gesetzter Wert hat Vorrang (COMPATIBLE, Code 3)",
          cb2.get("umgebung") == "COMPATIBLE" and cb2.get("code") == 3, str(cb2))


def test_mkl_cbwr_in_kettenprozessen():
    """Die Kettenprozesse (spawn) laden MKL selbst - auch dort muss AUTO
    gelten, ohne dass der Anwender etwas setzt. Geprueft am Loeser-Nachweis
    jedes Lastfalls, den die Ketten zurueckgeben."""
    try:
        import pypardiso                                        # noqa: F401
    except Exception:                                           # noqa: BLE001
        check("Pardiso fehlt - MKL_CBWR in Ketten uebersprungen", True)
        return
    basis = {k: v for k, v in os.environ.items() if k != "MKL_CBWR"}
    basis.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONUTF8="1")
    d, fehler = _probe(_CBWR_KETTEN, basis)
    if not check("Probeprozess mit zwei Ketten laeuft durch", d is not None, fehler):
        return
    check("es wurde wirklich in Ketten gerechnet", d.get("ketten") == 1, str(d.get("ketten")))
    cb = d.get("cbwr") or {}
    check("jeder Lastfall aus den Kettenprozessen rechnete mit AUTO (Code 2)",
          bool(cb) and all((v or {}).get("code") == 2 for v in cb.values()),
          ", ".join(f"{k}: {(v or {}).get('code')}" for k, v in cb.items()))


def main():
    for f in (test_pardiso_faellt_nicht_still_aus, test_ketten_teilen_sich_die_threads,
              test_pardiso_zaehlt_gestoerte_pivots, test_residuum_gehoert_zur_loesung,
              test_loeser_nachweis_je_lastfall,
              test_loeser_nachweis_nennt_das_ausweichen,
              test_zusammenfassung_nennt_gestoerte_pivots,
              test_loeser_nachweis_haelt_mkl_cbwr_fest,
              test_mkl_cbwr_auto_ist_vorgabe, test_mkl_cbwr_in_kettenprozessen,
              test_abbruchmeldung_nennt_ihren_lauf,
              test_ausweichen_erreicht_den_fortschritt_auch_im_kontakt,
              test_ausweichgrund_erreicht_ergebnis_bericht_und_modalanalyse,
              test_singulaer_nach_ausweichen_nennt_den_grund,
              test_ausweichloeser_und_buendelung_je_art,
              test_ketten_rechnen_mit_den_einstellungen_des_hauptprozesses,
              test_speicherfehler_nennt_zahlen, test_symmetriepruefung, test_loeser_treffen_die_geschlossene_loesung,
              test_jeder_loeser_sagt_woher_er_kommt, test_ama_liegt_der_exe_bei,
              test_pardiso_grenze_der_32_bit_indizes,
              test_superlu_nennt_sich_einkernig,
              test_pardiso_nimmt_alle_kerne_bis_auf_einen,
              test_meldung_trennt_pool_und_loeser, test_kopfzeile_nennt_den_eingestellten_loeser,
              test_superlu_ordnet_symmetrisch, test_pardiso_gibt_speicher_frei,
              test_mumps_sagt_was_es_tut_und_gibt_speicher_frei,
              test_threadzahl_aus_den_einstellungen,
              test_ama_faktorisiert_symmetrisch_und_nennt_threads,
              test_ama_nimmt_die_genauigkeitseinstellung,
              test_ama_faktorisiert_kein_zweites_mal_im_stillen,
              test_die_beschreibung_nennt_die_loesung_nicht_die_korrektur,
              test_kein_rueckfall_im_nachweis_wenn_die_schranke_gehalten_wird,
              test_die_matrix_wird_einmal_umgewandelt,
              test_die_tangente_wird_nur_gebaut_wenn_sie_gelesen_wird,
              test_die_symmetriesonde_hat_keine_luecke):
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
