"""
Loeser: lineare Statik (viele Lastfaelle mit einer Faktorisierung),
Kombinationen (Superposition oder nichtlinear bei Kontakt), Umhuellende,
Eigenschwingungen, lineares Knicken, Kontakt-Iteration, Nachlaufrechnung.

Vorzeichen Schnittgroessen (Staebe, DIN 1080): am positiven Schnittufer wirken
positive Schnittgroessen in Richtung der positiven lokalen Achsen.
    N > 0 Zug, My > 0 Zug an der +z-Seite (Oberseite bei horizontalem Stab).

Ergebnisobjekte (Results) enthalten die *linear ueberlagerbaren* Rohgroessen
(Verschiebungen, Lagerkraefte, lokale Stabendkraefte, Schnittkraefte je
Schale, Spannungen je Volumenelement). Abgeleitete Groessen (Vergleichs-
spannung, Ausnutzung, Schnittgroessen an Zwischenstellen) werden bei Bedarf
aus den Rohgroessen berechnet.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu, eigsh

from .model import Model, NDOF, Combination, LoadCase, Member, GRUNDSTELLUNG
from . import assemble as asm
from .elements import beam3d as bm
from .elements import shell as sh
from .elements import solid as sl
from . import parallel


# ==========================================================================
# Linearer Gleichungsloeser (Faktorisierung wiederverwendbar)
# ==========================================================================
def mkl_threads() -> int:
    """Threads fuer den Mehrkern-Loeser: alle Kerne bis auf einen.

    Der eine bleibt der Oberflaeche - sonst ruckelt das Fenster waehrend der
    Faktorisierung. Ein selbst gesetztes MKL_NUM_THREADS/OMP_NUM_THREADS hat
    Vorrang; wer die Zahl von Hand vorgibt, meint es so.

    Muss **vor** dem ersten Laden von mkl_rt laufen: MKL liest die Umgebung
    beim Initialisieren, spaeteres Setzen bleibt wirkungslos.
    """
    import os
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        wert = os.environ.get(name, "").strip()
        if wert.isdigit() and int(wert) > 0:
            return int(wert)
    n = max(1, (os.cpu_count() or 2) - 1)
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        os.environ.setdefault(name, str(n))
    return n


_MKL_LIB = None


def _mkl_lib():
    """Die MKL-Laufzeit (mkl_rt) als ctypes-Handle - ueber pypardiso, das sie
    ohnehin laedt; None ohne pypardiso oder MKL."""
    global _MKL_LIB
    if _MKL_LIB is None:
        try:
            _find_mkl()
            import pypardiso
            _MKL_LIB = pypardiso.PyPardisoSolver().libmkl or False
        except Exception:                                  # noqa: BLE001
            _MKL_LIB = False
    return _MKL_LIB or None


def _mkl_threads_setzen(lib, n: int) -> int:
    """MKL zur Laufzeit auf n Threads stellen; Rueckgabe die wirksame Zahl.

    Die Umgebung (MKL_NUM_THREADS) liest MKL nur beim ersten Laden; danach
    gilt MKL_Set_Num_Threads - so laesst sich die Threadzahl in den
    Einstellungen aendern, ohne das Programm neu zu starten. Es muss die
    **C-Schnittstelle** sein (MKL_Set_Num_Threads, Wert): die kleingeschriebene
    mkl_set_num_threads ist die Fortran-Fassung und erwartet einen Zeiger -
    mit dem Wert 2 gerufen las sie Adresse 2 ("access violation", 13.09.2026).
    MKL kappt selbst auf die physischen Kerne: 31 angefordert ergibt auf
    16 Kernen / 32 Threads MKL_Get_Max_Threads() = 16.
    """
    import ctypes
    lib = getattr(lib, "libmkl", lib)
    if lib is None:
        return int(n)
    try:
        setzen = lib.MKL_Set_Num_Threads
        setzen.argtypes = [ctypes.c_int]
        setzen.restype = None
        setzen(int(n))
        lesen = lib.MKL_Get_Max_Threads
        lesen.argtypes = []
        lesen.restype = ctypes.c_int
        return int(lesen())
    except (AttributeError, OSError):
        return int(n)


def threads_automatisch(backend: str) -> int:
    """Die Vorgabe des Loesers ohne Einstellung: PARDISO alle Kerne bis auf
    einen, MUMPS hoechstens acht (mumps.threads_vorgabe - mehr machten es
    langsamer), sonst 1."""
    if backend == "mumps":
        try:
            import mumps
            return int(mumps.threads_vorgabe())
        except Exception:                                  # noqa: BLE001
            return 1
    if backend == "pardiso":
        lib = _mkl_lib()
        return _mkl_threads_setzen(lib, mkl_threads()) if lib is not None else mkl_threads()
    if backend == "ama":
        return max(1, parallel.cpu_count() - 1)        # wie PARDISO: ein Kern bleibt der Oberflaeche
    return 1


def threads_vorgabe(backend: str) -> int:
    """Wie viele Threads der Loeser nimmt: settings().solver_threads, wenn
    gesetzt (> 0), sonst die Vorgabe des Loesers (threads_automatisch)."""
    n = int(getattr(parallel.settings(), "solver_threads", 0) or 0)
    return n if n > 0 else threads_automatisch(backend)


def _find_mkl():
    """MKL-Laufzeitbibliothek fuer pypardiso finden (pip install mkl legt sie
    ausserhalb des Suchpfads ab; im PyInstaller-Bundle liegt sie neben der exe
    entpackt in sys._MEIPASS)."""
    import os
    import glob
    import sys
    mkl_threads()
    if os.environ.get("PYPARDISO_MKL_RT"):
        return
    basen = [sys.prefix, os.path.join(sys.prefix, "Library", "bin"),
             os.path.join(sys.prefix, "lib"), "/usr/local/lib", "/usr/lib"]
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        # Im Bundle liegen die DLLs beieinander; Windows findet die
        # Abhaengigkeiten von mkl_rt nur, wenn das Verzeichnis im Suchpfad ist.
        basen[:0] = [mei, os.path.join(mei, "Library", "bin")]
        if hasattr(os, "add_dll_directory") and os.path.isdir(mei):
            try:
                os.add_dll_directory(mei)
            except OSError:
                pass
    pats = []
    for base in basen:
        pats += [os.path.join(base, "libmkl_rt.so*"), os.path.join(base, "mkl_rt*.dll"),
                 os.path.join(base, "libmkl_rt*.dylib")]
    try:
        import site
        for sp_ in site.getsitepackages():
            pats += [os.path.join(sp_, "..", "..", "libmkl_rt.so*"),
                     os.path.join(sp_, "..", "..", "..", "Library", "bin", "mkl_rt*.dll")]
    except Exception:
        pass
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            os.environ["PYPARDISO_MKL_RT"] = os.path.abspath(hits[-1])
            return

def _melde(progress, text: str, anteil: float = None) -> None:
    """Fortschritt melden - Text und, wenn bekannt, der Anteil (0…1).

    Empfaenger, die nur Text kennen (Protokoll, Kommandozeile, aeltere
    Aufrufer), bekommen weiterhin nur Text; die Oberflaeche nimmt den Anteil
    und macht daraus einen Balken statt eines endlos wandernden Streifens.
    """
    if progress is None:
        return
    if anteil is None:
        progress(text)
        return
    try:
        progress(text, float(anteil))
    except TypeError:
        progress(text)


#: Die Loeser zur Auswahl (Berechnung -> Einstellungen): Schluessel ->
#: (Name, Python-Paket, Lizenz, Art). Lizenzrechtlich sauber heisst: in der
#: gepackten exe stecken nur MKL (Intel Simplified Software License, frei
#: weitergebbar), SuperLU (BSD, in scipy), PyAMG (MIT) und MUMPS (CeCILL-C,
#: LGPL-artig: die Bibliothek bleibt unveraendert und ein eigenes Modul, der
#: Lizenztext liegt in mumps/LIZENZ bei; Paket "mumps" aus packaging/, eigener
#: Windows-Bau, 13.09.2026). CHOLMOD (LGPL, das Supernodal-Modul GPL) und
#: UMFPACK (GPL) kommen aus der eigenen Python-Umgebung des Anwenders, wenn
#: er sie installiert - sie werden nicht mitgeliefert.
LOESER = {
    "pardiso": ("MKL PARDISO", "pypardiso", "Intel Simplified Software License", "direkt, mehrkernig"),
    "cholmod": ("CHOLMOD", "scikit-sparse", "LGPL / Supernodal GPL - nicht in der exe", "direkt (Cholesky)"),
    "umfpack": ("UMFPACK", "scikit-umfpack", "GPL - nicht in der exe", "direkt (LU)"),
    "mumps": ("MUMPS", "mumps", "CeCILL-C (Lizenztext liegt bei)", "direkt, mehrkernig"),
    "ama": ("ama", "ama", "eigener Kern (Rust, keine Fremdlizenz)", "direkt, mehrkernig (LDL^T, Superknoten)"),
    "pyamg": ("PyAMG", "pyamg", "MIT", "iterativ (algebraisches Mehrgitter + CG)"),
    "superlu": ("SuperLU", "scipy", "BSD", "direkt, einkernig"),
}
NAMEN = {"pardiso": "MKL PARDISO", "cholmod": "CHOLMOD", "superlu": "SuperLU",
         "umfpack": "UMFPACK", "mumps": "MUMPS", "ama": "ama", "pyamg": "PyAMG", "none": "-"}
#: Welches Python-Modul ein Loeser braucht - an einer Stelle, damit Auswahl,
#: Meldung und Rechnung dasselbe pruefen
LOESER_MODUL = {"pardiso": "pypardiso", "cholmod": "sksparse.cholmod",
                "umfpack": "scikits.umfpack", "mumps": "mumps", "ama": "ama.kern", "pyamg": "pyamg",
                "superlu": "scipy.sparse.linalg"}
#: Loeser, die mehrere Threads nutzen (die uebrigen rechnen einkernig)
MEHRKERNIG = ("pardiso", "mumps", "ama")


def loeser_da(key: str) -> bool:
    """Laesst sich dieser Loeser laden? (ohne zu faktorisieren)"""
    import importlib
    from . import werkzeuge
    werkzeuge.aktivieren()                 # nachgeladene Pakete (MUMPS) sichtbar machen
    modul = LOESER_MODUL.get(key)
    if not modul:
        return False
    try:
        if key == "pardiso":
            _find_mkl()
        importlib.import_module(modul)
        return True
    except Exception:                                      # noqa: BLE001
        return False


#: Woher ein fehlender Loeser kommt: (kurz fuer die Auswahlliste, ganzer Weg
#: fuer den Hinweistext). Die Liste schrieb bis dahin nur "nicht installiert";
#: warum und was zu tun waere, stand nirgends (19.09.2026, Anwender: "es gibt
#: gleichungsloeser die mir angezeigt werden, die ich aber nicht waehlen kann
#: und auch nicht installieren"). Drei Faelle stecken dahinter: nachladbar
#: (MUMPS), aus Lizenzgruenden ausgeschlossen (CHOLMOD, UMFPACK) und
#: mitgeliefert - fehlt so einer, ist der Bau schuld.
LOESER_WOHER = {
    "pardiso": ("pip install pypardiso mkl",
                "MKL PARDISO liegt der exe bei. Meldet es sich hier nicht, fehlen die "
                "MKL-Bibliotheken. Eigene Python-Umgebung: pip install pypardiso mkl"),
    "cholmod": ("GPL - nur mit eigenem Python",
                "CHOLMOD steht unter LGPL, sein schneller Supernodal-Teil unter GPL, und "
                "darf darum nicht mitgeliefert werden - auch nicht zum Nachladen. Wer das "
                "Programm aus dem Quelltext startet: pip install scikit-sparse (braucht "
                "SuiteSparse)"),
    "umfpack": ("GPL - nur mit eigenem Python",
                "UMFPACK steht unter GPL und darf darum nicht mitgeliefert werden - auch "
                "nicht zum Nachladen. Wer das Programm aus dem Quelltext startet: "
                "pip install scikit-umfpack (braucht SuiteSparse)"),
    "mumps": ("Extras → Vernetzer installieren…",
              "MUMPS (CeCILL-C) kommt nicht mit der exe, laesst sich aber nachladen: "
              "Extras → Programm → „Vernetzer installieren…“ → MUMPS. Danach steht es "
              "sofort in dieser Liste, ohne Neustart"),
    "ama": ("gehoert in die exe - bitte melden",
            "ama ist der eigene Rechenkern (Rust, keine Fremdlizenz) und liegt der exe "
            "bei. Fehlt er hier, ist der Bau fehlerhaft - bitte melden. Aus dem "
            "Quelltext: pip install packaging/ama-0.1.0-cp311-cp311-win_amd64.whl"),
    "pyamg": ("pip install pyamg",
              "PyAMG (MIT) liegt der exe bei. Eigene Python-Umgebung: pip install pyamg"),
    "superlu": ("scipy fehlt",
                "SuperLU kommt mit scipy und kann nicht fehlen - ohne scipy laeuft das "
                "Programm gar nicht. Meldet es sich hier nicht, ist die Installation "
                "beschaedigt"),
}


def loeser_woher(key: str) -> tuple:
    """(kurzer Grund, ganzer Weg), warum dieser Loeser fehlt."""
    return LOESER_WOHER.get(str(key), ("nicht installiert", ""))


def loeser_liste() -> list:
    """[(Schluessel, Name, verfuegbar, Lizenz, Art)] fuer die Auswahl - ohne
    zu faktorisieren; ``verfuegbar`` heisst: das Paket laesst sich laden."""
    aus = []
    for key, (name, _paket, lizenz, art) in LOESER.items():
        aus.append((key, name, loeser_da(key), lizenz, art))
    return aus


def loeser_beschreibung(key: str) -> str:
    """Name und Kernzahl eines Loesers, wie die Kopfzeile ihn nennt."""
    name = NAMEN.get(key, key)
    if key in MEHRKERNIG:
        return f"{name}, {threads_vorgabe(key)} Threads"
    return f"{name}, einkernig"


def loeser_verfuegbar(backend: str = "") -> str:
    """Womit die naechste Rechnung loesen wird - ohne zu faktorisieren.

    Fuer die Meldung beim Start einer Rechnung. Genannt wird der
    **eingestellte** Loeser (Berechnung -> Einstellungen), nicht der
    erstbeste vorhandene: wer MUMPS gewaehlt hatte, las hier bis zum
    14.09.2026 "MKL PARDISO, 16 Threads", waehrend MUMPS mit acht Threads
    rechnete - die Ergebniszeile sagte es richtig, die Kopfzeile nicht.

    "Automatisch" nimmt PARDISO, sonst CHOLMOD, sonst SuperLU - dieselbe
    Reihenfolge wie :class:`LinearSolver`. Ein eingestellter Loeser, der
    fehlt, wird als solcher gemeldet; die Rechnung braecht damit ab, und das
    gehoert vor die Rechnung, nicht mittendrin.

    Frueher stand in dieser Zeile, wie viele Kerne der **Prozesspool fuers
    Vernetzen** hat; ueber das Loesen sagte das nichts.
    """
    be = str(backend or getattr(parallel.settings(), "solver_backend", "") or "auto").strip()
    if be and be != "auto":
        if be not in LOESER:
            return f"{be} - unbekannter Gleichungslöser (möglich: {', '.join(LOESER)})"
        if not loeser_da(be):
            return (f"{NAMEN.get(be, be)} - eingestellt, aber nicht installiert; die Rechnung "
                    "bricht damit ab (Berechnung → Einstellungen)")
        return loeser_beschreibung(be)
    for key in ("pardiso", "cholmod"):
        if loeser_da(key):
            return loeser_beschreibung(key) + " (automatisch)"
    return "SuperLU, einkernig (automatisch, kein MKL/CHOLMOD im Programm)"


#: Ein GiB - der Taskmanager rechnet so, und die Zahlen sollen zu dem
#: passen, was der Anwender dort sieht
_GIB = 1024 ** 3


def speicherlage() -> dict:
    """Was der eigene Prozess haelt und was der Rechner frei hat, in **GiB**.

    Ueber psutil, sonst ueber die Windows-API; was nicht zu ermitteln ist,
    bleibt None. Gebraucht, um einen Speicherfehler einzuordnen: 669 MiB
    scheiterten an einem Rechner mit 128 GB (19.09.2026), und ohne Zahlen
    liess sich nicht sagen, woran.
    """
    aus = {"prozess": None, "belegt": None, "frei": None, "gesamt": None, "commit_frei": None}
    try:
        import psutil                                   # noqa: PLC0415
        mi = psutil.Process().memory_info()
        aus["prozess"] = mi.rss / _GIB
        aus["belegt"] = getattr(mi, "vms", 0) / _GIB or None
        vm = psutil.virtual_memory()
        aus["frei"], aus["gesamt"] = vm.available / _GIB, vm.total / _GIB
        return aus
    except Exception:                                   # noqa: BLE001
        pass
    if os.name == "nt":
        try:
            import ctypes                               # noqa: PLC0415

            class _MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = _MEM()
            st.dwLength = ctypes.sizeof(_MEM)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                aus["frei"] = st.ullAvailPhys / _GIB
                aus["gesamt"] = st.ullTotalPhys / _GIB
                aus["commit_frei"] = st.ullAvailPageFile / _GIB

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

            pmc = _PMC()
            pmc.cb = ctypes.sizeof(_PMC)
            # Seit Windows 7 liegt die Funktion in kernel32 (K32…); psapi.dll
            # gibt es weiter, ist aber nicht in jeder Umgebung geladen
            # Der Prozess-Handle ist ein Zeiger: ohne restype schneidet ctypes
            # ihn auf 32 Bit, und die Abfrage schlaegt still fehl
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            griff = k32.GetCurrentProcess()
            for hol in (getattr(k32, "K32GetProcessMemoryInfo", None),
                        getattr(ctypes.WinDLL("psapi.dll"), "GetProcessMemoryInfo", None)):
                if hol is None:
                    continue
                hol.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
                hol.restype = ctypes.c_int
                if hol(griff, ctypes.byref(pmc), pmc.cb):
                    aus["prozess"] = pmc.WorkingSetSize / _GIB
                    # Der belegte (committete) Speicher zaehlt fuer einen
                    # Speicherfehler, nicht der Arbeitssatz: numpy reserviert
                    # beim Anlegen, eingelagert wird erst beim Schreiben
                    aus["belegt"] = pmc.PagefileUsage / _GIB
                    break
        except Exception:                               # noqa: BLE001
            pass
    return aus


def speichertext(was: str = "") -> str:
    """Eine Zeile zur Speicherlage - fuer Protokoll und Fehlermeldung."""
    m = speicherlage()
    teile = []
    if m["prozess"] is not None:
        teile.append(f"Statik3D hält {m['prozess']:.1f} GB"
                     + (f" (belegt {m['belegt']:.1f} GB)" if m.get("belegt") else ""))
    if m["frei"] is not None and m["gesamt"] is not None:
        teile.append(f"{m['frei']:.1f} von {m['gesamt']:.1f} GB frei")
    if m["commit_frei"] is not None:
        teile.append(f"Auslagerung frei {m['commit_frei']:.1f} GB")
    return ((was + ": ") if was and teile else "") + ", ".join(teile)


def ist_symmetrisch(K, tol: float = None) -> bool:
    """Ist die Matrix symmetrisch? Blockweise geprueft, ohne die Differenz.

    ``K - K.T`` sieht harmlos aus, aber scipy legt dafuer erst ein Ergebnis
    in der Groesse **beider** Strukturen an und kuerzt danach: am Drehlager
    (948 000 Freiheitsgrade, 43,8 Mio Eintraege) waren das 87,7 Mio Eintraege
    und 669 MiB, die nicht mehr passten - die Rechnung brach mit einem
    Speicherfehler ab (18.09.2026). Zeilenweise in Bloecken gemessen an einer
    Matrix mit 19,3 Mio Eintraegen: 63 MB statt 697 MB Spitze, 0,56 s statt
    0,13 s. Die Zeit faellt neben der Faktorisierung nicht ins Gewicht.
    """
    Kc = K.tocsr()
    if tol is None:
        tol = 1e-12 * (float(abs(Kc).max()) if Kc.nnz else 1.0)
    if Kc.shape[0] != Kc.shape[1]:
        return False
    n = Kc.shape[0]
    # So viele Zeilen, dass ein Block rund 1 Mio Eintraege hat
    je_zeile = max(1.0, Kc.nnz / max(1, n))
    zeilen = int(max(1000, min(n, 1_000_000 // je_zeile)))
    for a in range(0, n, zeilen):
        b = min(n, a + zeilen)
        d = Kc[a:b, :] - Kc[:, a:b].T.tocsr()
        if d.nnz and float(abs(d).max()) > tol:
            return False
    return True


#: Schon gemeldete Hinweise - eine Faktorisierung laeuft in der
#: Kontakt-Iteration Dutzende Male, die Meldung soll einmal kommen.
_GEMELDET: set = set()


def _log_einmal(text: str) -> None:
    """Denselben Hinweis nur einmal je Programmlauf schreiben."""
    if text in _GEMELDET:
        return
    _GEMELDET.add(text)
    import warnings
    warnings.warn(text, RuntimeWarning, stacklevel=2)


#: Groesste Zeilenzahl und groesste Zahl von Eintraegen, die die
#: 32-Bit-Schnittstelle von MKL PARDISO fassen kann. Der Prozess selbst ist
#: durchgehend 64-bittig (Zeiger 64 Bit, numpy.intp 64 Bit, gemessen
#: 20.09.2026); pypardiso reicht die Matrix aber ueber die LP64-Fassung
#: weiter und wandelt dabei um:
#:
#:     ia = A.indptr.astype(np.int32) + 1
#:     ja = A.indices.astype(np.int32) + 1
#:
#: ``astype`` prueft nicht. Ueber der Grenze liefe die Umwandlung still ueber,
#: und PARDISO bekaeme vertauschte Indizes - **falsche Zahlen statt einer
#: Fehlermeldung**. Zum Vergleich: das Drehlager hat 476.214 Zeilen und 17,8
#: Mio. Eintraege, also Faktor 120 Luft; die Grenze greift erst bei rund 30
#: Mio. Freiheitsgraden.
INT32_MAX = 2 ** 31 - 1


def _pardiso_nnz_faktor(ps) -> int:
    """Nichtnullen der Faktorisierung aus iparm(18) - 0, wenn nichts gemeldet wird.

    Gemessen 20.09.2026 an einer Tridiagonalmatrix: n = 200 gibt 964, n = 400
    gibt 1960 - linear, wie es fuer ein Band sein muss. ``get_iparms()`` zaehlt
    von 1; iparm(17) steht direkt daneben und meint den Speicher in KB (28 bei
    n = 400), nicht die Eintraege. Die beiden sind leicht zu verwechseln.
    """
    try:
        return int(ps.get_iparms()[18])
    except Exception:
        return 0


class LinearSolver:
    """Faktorisiert K einmal; solve() fuer beliebig viele rechte Seiten.
    Backends: pypardiso (MKL, mehrere Threads), scikit-sparse CHOLMOD, SuperLU.

    ``threads`` sagt, mit wie vielen Threads tatsaechlich gerechnet wurde.
    SuperLU ist streng einkernig und meldet darum immer 1 - das ist keine
    Einstellungssache, sondern eine Eigenschaft des Loesers.
    """

    def __init__(self, K: sparse.spmatrix, backend: str = None):
        # Kennzahlen der Faktorisierung. Die adaptive Vernetzung fragt danach,
        # um zu sagen, was eine Netzrunde an Loeserzeit gespart hat
        # (Anforderung der Vernetzersitzung 2.2, 20.09.2026): die Elementzahl
        # allein sagt es nicht, weil die Faktorisierung ueberlinear waechst.
        self.zeit_faktorisierung = 0.0
        self.nnz_matrix = int(getattr(K, "nnz", 0) or 0)
        self.nnz_faktor = 0
        # perf_counter, nicht time(): eine Faktorisierung dauert am kleinen
        # System Millisekunden, und die Uhr von time.time() steht unter Windows
        # in Stufen von 15,6 ms - gemessen 20.09.2026: ein Probelauf meldete
        # damit 0,000 s fuer eine Faktorisierung, die es wirklich gab.
        t_fak = time.perf_counter()
        try:
            self._aufbauen(K, backend)
        except MemoryError as ex:
            # Ein nackter Speicherfehler sagt nur, was nicht ging. Die Meldung
            # nennt jetzt, was der Prozess haelt und was der Rechner frei hat -
            # ohne diese Zahlen liess sich nicht sagen, woran es lag
            # (19.09.2026: 669 MiB scheiterten an einem Rechner mit 128 GB)
            lage = speichertext()
            nnz = int(getattr(K, "nnz", 0) or 0)
            raise RuntimeError(
                f"Der Speicher reichte für die Faktorisierung nicht: {ex}. "
                f"System mit {self.n if hasattr(self, 'n') else K.shape[0]} Freiheitsgraden, "
                f"{nnz / 1e6:.1f} Mio. Einträgen"
                + (f". {lage}" if lage else "")
                + ". Ein größeres Modell braucht mehr Arbeitsspeicher oder eine größere "
                  "Auslagerungsdatei; ein anderer Gleichungslöser (Berechnung → Einstellungen) "
                  "kann sparsamer sein.") from ex
        self.zeit_faktorisierung = time.perf_counter() - t_fak

    def _passt_in_int32(self, K: sparse.spmatrix, verlangt: bool) -> bool:
        """Passt die Matrix in die 32-Bit-Schnittstelle von PARDISO?

        ``verlangt`` heisst: der Anwender hat PARDISO ausdruecklich gewaehlt -
        dann ist ein stilles Ausweichen falsch, er bekommt eine Meldung.
        Bei "automatisch" wird auf den naechsten Loeser ausgewichen; MUMPS,
        ama und SuperLU indizieren mit 64 Bit.
        """
        nnz = int(getattr(K, "nnz", 0) or 0)
        if self.n <= INT32_MAX and nnz <= INT32_MAX:
            return True
        text = (f"Das Gleichungssystem ist zu groß für MKL PARDISO: {self.n} Zeilen und "
                f"{nnz / 1e6:.0f} Mio. Einträge; die Schnittstelle fasst {INT32_MAX} "
                f"(32-Bit-Indizes). MUMPS, ama und SuperLU rechnen mit 64 Bit - "
                f"Berechnung \u2192 Einstellungen \u2192 Gleichungslöser.")
        if verlangt:
            raise RuntimeError(text)
        _log_einmal(text + " Es wird auf einen anderen Löser ausgewichen.")
        return False

    def _aufbauen(self, K: sparse.spmatrix, backend: str = None):
        self.n = K.shape[0]
        self.backend = "none"
        self.threads = 1
        be = backend or parallel.settings().solver_backend
        self._solve = None
        self._K = None
        self._ps = None
        self._faktor = None          # nur ama: haelt die Faktorisierung (freigeben() loest ihn)
        self._nachweis = None        # nur ama: was die letzte Loesung erreicht hat
        self._vorgabe = None         # nur ama: wonach faktorisiert wurde (fuer den Nachweis)
        self.nachiterationen = 0
        self.residuum = 0.0
        if self.n == 0:
            self._solve = lambda b: np.zeros_like(b)
            return
        K = K.tocsc()
        self._K = K.tocsr()
        if be in ("auto", "pardiso") and self._passt_in_int32(K, be == "pardiso"):
            try:
                _find_mkl()
                import pypardiso
                ps = pypardiso.PyPardisoSolver()
                Kcsr = K.tocsr()
                # Threadzahl aus den Einstellungen (0 = alle Kerne bis auf einen)
                self.threads = _mkl_threads_setzen(ps, threads_vorgabe("pardiso"))
                ps.factorize(Kcsr)
                self.nnz_faktor = _pardiso_nnz_faktor(ps)
                self._ps = ps
                self._solve = lambda b: ps.solve(Kcsr, b)
                self.backend = "pardiso"
            except Exception:
                if be == "pardiso":
                    raise
        if self._solve is None and be in ("auto", "cholmod"):
            try:
                from sksparse.cholmod import cholesky
                f = cholesky(K)
                self._solve = lambda b: f(b)
                self.backend = "cholmod"
            except Exception:
                if be == "cholmod":
                    raise
        if self._solve is None and be == "umfpack":
            # GPL - nur aus der eigenen Python-Umgebung des Anwenders
            from scikits.umfpack import splu as _umf_splu
            lu = _umf_splu(K)
            self._solve = lu.solve
            self.backend = "umfpack"
        if self._solve is None and be == "mumps":
            # Nachgeladenes MUMPS (statik3d.werkzeuge) in den Suchpfad - auch
            # in Arbeitsprozessen, die vernetzer_extern nie importieren
            from . import werkzeuge
            werkzeuge.aktivieren()
            try:
                import mumps
            except ImportError as ex:
                raise RuntimeError("MUMPS ist nicht installiert - Extras → Vernetzer installieren… lädt es "
                                   "nach (oder beim Programmstart, Kästchen im selben Dialog)") from ex
            mumps.set_threads(threads_vorgabe("mumps"))
            self._solve = self._mumps(K)
            self.backend = "mumps"
            self.threads = mumps.threads()
        if self._solve is None and be == "ama":
            # Eigener Kern (Paket ama, Rust): multifrontale LDL^T mit Superknoten; das
            # untere Dreieck geht hinein, K muss symmetrisch sein (wie MUMPS SYM=2)
            try:
                # ama.genauigkeit hier mit: ein aelteres Wheel hat nur ama.kern, und dann soll
                # dieselbe Meldung kommen statt eines nackten ImportError weiter unten
                from ama import genauigkeit as ama_gen
                from ama import kern as ama_kern
            except ImportError as ex:
                raise RuntimeError("ama ist nicht installiert oder zu alt - pip install <ama-Wheel> "
                                   "in diese Python-Umgebung (Gleichungsloeser-Projekt, "
                                   "maturin build)") from ex
            Kc = K.tocsr()
            skala = float(abs(Kc).max()) if Kc.nnz else 1.0
            if not ist_symmetrisch(Kc, 1e-12 * skala):
                raise RuntimeError("ama braucht eine symmetrische Matrix - fuer unsymmetrische "
                                   "Systeme MKL PARDISO, MUMPS oder SuperLU waehlen")
            # statische Pivotisierung wie MKL PARDISO: ein zu kleines Pivot wird gehoben
            # statt abzubrechen, die Nachiteration unten holt die Genauigkeit zurueck.
            # Ohne sie brach ama an Modellen ab, die PARDISO rechnet (Kontaktfedern,
            # rangdefekte Steifigkeit: cbg.json 6 Pivots, gemessen 18.09.2026)
            # Dieselbe Einstellung, die solve() unten prueft, geht als Vorgabe in ama: der
            # Kern iteriert bis zu dieser Schranke nach und legt in faktor.nachweis ab, was
            # er erreicht hat. Sonst haette dieselbe Sache zwei Bedienelemente.
            #
            # rueckfall="lockern": der Kern meldet die verfehlte Schranke, statt sie selbst
            # zu verfolgen. Sein Rueckfall "genauer" faktorisiert die ganze Matrix ein
            # zweites Mal - und weil self._solve das loese dieses Faktors ist, taete er das
            # bei jedem Nachiterationsschritt von solve() erneut. Ein einziger solve()-Aufruf
            # kostete so 2 Faktorisierungen statt 1 (gemessen 18.09.2026); am Drehlager
            # (1 028 724 FHG) sind das je 7 GB, stumm und mehrfach. Wer eine zu grosse
            # Abweichung meldet, ist und bleibt die Pruefung in solve() darunter.
            #
            # Eine billige Verschachtelung bleibt: jeder Korrekturschritt von solve() ruft
            # wieder loese und damit die ganze Nachiterationsschleife des Kerns auf, also
            # bis zu (n_max + 1)^2 = 16 innere Loesungen statt n_max = 3 (bei der
            # Vorgabe 3). Das sind Vorwaerts-/Rueckwaertseinsetzen auf dem vorhandenen
            # Faktor - Bruchteile einer Faktorisierung, und nur wenn die Schranke ueberhaupt
            # verfehlt wird. Darum bleibt es so; teuer war allein das zweite Faktorisieren.
            grenze, n_max = self.genauigkeit()
            vorgabe = ama_gen.aufloesen(residuum=grenze, nachiterationen=n_max,
                                        rueckfall="lockern")
            faktor = ama_kern.faktorisiere(Kc, threads=threads_vorgabe("ama"), stoerung_rel=1e-13,
                                           vorgabe=vorgabe)
            self._solve = faktor.loese
            self.backend = "ama"
            self.threads = int(faktor.threads)
            self.gestoert = int(faktor.gestoert)
            self._faktor = faktor
            self._vorgabe = vorgabe
        if self._solve is None and be == "pyamg":
            self._solve = self._pyamg(K)
            self.backend = "pyamg"
        if self._solve is None:
            if be not in ("auto", "superlu", "pardiso", "cholmod"):
                raise RuntimeError(f"Gleichungslöser '{be}' unbekannt - möglich: "
                                   + ", ".join(LOESER))
            lu = splu(K, permc_spec="MMD_AT_PLUS_A")
            self._solve = lu.solve
            self.backend = "superlu"

    @staticmethod
    def _mumps(K):
        """MUMPS (CeCILL-C, Paket ``mumps``): einmal faktorisieren, dann je
        rechte Seite.

        Symmetrische Matrizen gehen als unteres Dreieck mit SYM=2 hinein
        (LDL^T mit Pivotisierung): am Wuerfel mit 34 914 FHG 249 statt
        534 MB Faktoren und 2,5e10 statt 4,8e10 Flop (METIS-Umordnung,
        13.09.2026). Ob K symmetrisch ist,
        wird an der Matrix gemessen, nicht angenommen - Reibkontakt oder
        Federn koennten es brechen, und dann rechnet SYM=0 mit der vollen
        Matrix richtig weiter.

        Fehler -8/-9 heissen: die Arbeitsspeicher-Schaetzung der Analyse
        reichte wegen der Pivotisierung nicht. Dann wird ICNTL(14) (Zuschlag
        in Prozent, Vorgabe 20) angehoben und nur die Faktorisierung
        wiederholt, wie es das MUMPS-Handbuch vorsieht.
        """
        from mumps import DMumpsContext, MUMPSError
        Kc = K.tocsr()
        skala = float(abs(Kc).max()) if Kc.nnz else 1.0
        sym = 2 if ist_symmetrisch(Kc, 1e-12 * skala) else 0
        coo = sparse.tril(Kc, format="coo") if sym else Kc.tocoo()
        ctx = DMumpsContext(sym=sym, par=1)
        ctx.set_silent()
        ctx.set_shape(coo.shape[0])
        ctx.set_centralized_assembled(coo.row + 1, coo.col + 1, coo.data)
        ctx.run(job=1)                       # Analyse (Umordnung, Schaetzung)
        zuschlaege = (20, 50, 100, 200)
        for zuschlag in zuschlaege:
            ctx.set_icntl(14, zuschlag)
            try:
                ctx.run(job=2)               # Faktorisierung
                break
            except MUMPSError as ex:
                if ex.infog1 not in (-8, -9) or zuschlag == zuschlaege[-1]:
                    raise
        # Was die Faktorisierung wirklich braucht: INFOG(16) je Prozess,
        # INFOG(17) insgesamt (MB), INFOG(29) Eintraege in den Faktoren. Ohne
        # diese Zahlen liess sich ein Speicherfehler nicht einordnen
        # (19.09.2026: "wieso sind 1,6gb ein problem, hier ist doch genug
        # speicher vorhanden" - der Rechner hat 128 GB)
        try:
            LinearSolver.mumps_speicher = {
                "je_prozess_mb": int(ctx.id.infog[15]), "gesamt_mb": int(ctx.id.infog[16]),
                "faktor_eintraege": int(ctx.id.infog[28]), "sym": int(sym)}
        except Exception:                               # noqa: BLE001
            LinearSolver.mumps_speicher = {}

        def loesen(b):
            # MUMPS loest in place und erwartet mehrere rechte Seiten
            # spaltenweise hintereinander (Fortran-Reihenfolge)
            x = np.array(b, dtype=float, order="F", copy=True)
            ctx.set_rhs(x)
            ctx.run(job=3)
            return x
        loesen.freigeben = ctx.destroy       # fuer LinearSolver.freigeben()
        return loesen

    @staticmethod
    def _pyamg(K):
        """PyAMG (MIT): algebraisches Mehrgitter als Vorkonditionierer fuer CG -
        iterativ, speicherarm, je rechte Seite neu zu iterieren."""
        import pyamg
        ml = pyamg.smoothed_aggregation_solver(K.tocsr(), max_coarse=500)

        def loesen(b):
            b = np.asarray(b, float)
            if b.ndim == 2:
                return np.column_stack([loesen(b[:, j]) for j in range(b.shape[1])])
            x = ml.solve(b, tol=1e-10, accel="cg", maxiter=2000)
            return np.asarray(x, float)
        return loesen

    def freigeben(self) -> None:
        """Den Speicher der Faktorisierung zurueckgeben.

        MKL haelt die Faktorisierung ausserhalb von Python; pypardiso gibt sie
        nur auf ausdruecklichen Aufruf frei, nie beim Einsammeln des Objekts.
        Am Drehlager (1 028 724 FHG, 7 GB je Faktorisierung) wuchs der Prozess
        in der Kontakt-Iteration mit jedem Schritt um diese 7 GB, bis Pardiso
        nach 33 Schritten bei 113 GB mit Fehler -2 aufgab und SuperLU im
        Rueckfall am Speicher scheiterte (11.09.2026).
        """
        ps, self._ps = self._ps, None
        loesen, self._solve = self._solve, None
        # ama haelt die Faktorisierung auf der Rust-Seite; self._faktor wuerde sie ueber das
        # Freigeben hinaus am Leben halten. self._nachweis bleibt - er ist eine Handvoll
        # Zahlen, und beschreibung() soll auch danach noch sagen koennen, was erreicht wurde.
        self._faktor = None
        if ps is not None:
            try:
                ps.free_memory(everything=True)
            except Exception:                   # noqa: BLE001 - beim Aufraeumen nie sperren
                pass
        # MUMPS haelt die Faktorisierung ebenfalls ausserhalb von Python
        # (JOB=-2 gibt sie frei); der Loeser bringt dafuer freigeben() mit
        frei = getattr(loesen, "freigeben", None)
        if frei is not None:
            try:
                frei()
            except Exception:                   # noqa: BLE001
                pass

    def __del__(self):
        try:
            self.freigeben()
        except Exception:                       # noqa: BLE001
            pass

    def beschreibung(self) -> str:
        """Wie in Protokoll und Statuszeile: Loeser, Threads, Genauigkeit.

        Nennt auch Freiheitsgrade ohne Halt, wenn der Loeser sie meldet: dort ist die Loesung
        nicht eindeutig (ein unbelastetes, ungelagertes Teil kann sich frei bewegen), und
        verschiedene Loeser liefern verschiedene, gleich richtige Antworten. Am Modell
        modell.json waren es 14 Pivots und 759 Freiheitsgrade; die Verformung unterschied sich
        dort um 7 % von max|u|, die Energie des Unterschieds aber nur um 1e-22 - und ueber 30
        Kontakt-Iterationen wurde daraus ein anderer Endzustand (18.09.2026)."""
        grenze, n_max = self.genauigkeit()
        frei = getattr(self, "gestoert", 0)
        # Was ama bei der letzten Loesung erreicht hat - gemessen, nicht zugesagt. Vor dem
        # ersten Loesen und bei allen anderen Loesern gibt es keinen Nachweis, dann bleibt
        # der Zusatz leer. Der Wert kommt aus solve() und nicht aus dem Faktor: dort wird er
        # festgehalten, ehe die Nachiteration ihn ueberschreiben kann (siehe solve()).
        nach = self._nachweis
        zusatz = "" if nach is None else f"; erreicht {nach.erreicht:.1e} (Ziel {nach.ziel:.0e})"
        return NAMEN.get(self.backend, self.backend) + (
            f", {self.threads} Threads" if self.threads > 1 else ", einkernig") + (
            f", Genauigkeit {grenze:g}" + (f" mit bis zu {n_max} Nachiterationen" if n_max else "")) + (
            f"; {frei} Freiheitsgrade ohne Halt (Ergebnis dort nicht eindeutig - Lagerung pruefen)"
            if frei else "") + zusatz

    def solve(self, b: np.ndarray, check: bool = True) -> np.ndarray:
        if self._solve is None:
            raise RuntimeError("Loeser ist freigegeben - erneut faktorisieren")
        b = np.asarray(b, float)
        x = self._solve(b)
        # Der Nachweis von ama gehoert zu genau dieser Loesung. Die Nachiteration unten ruft
        # self._solve fuer die Korrektur b - K x auf, und deren Residuum bezieht sich auf
        # ||b - K x|| statt auf ||b||; der Nachweis im Faktor beschreibt danach die Korrektur
        # und widerspricht dem Residuum, das solve() meldet (gemessen 18.09.2026: Meldung
        # 1,1e-16, Beschreibung 1,3e-16). Darum hier festhalten, ehe das geschehen kann.
        # Je Aufruf erneuert, nicht nur beim ersten: beschreibung() und self.residuum sollen
        # dieselbe, zuletzt gerechnete Loesung beschreiben - sonst nennt die Statuszeile nach
        # einer Reihe von Lastfaellen die Zahlen des ersten.
        if self._faktor is not None:
            self._nachweis = self._faktor.nachweis
        if not np.all(np.isfinite(x)):
            raise RuntimeError("Singulaeres System - Lagerung oder Vernetzung pruefen "
                               "(kinematische Kette / freie Knoten).")
        if check and self._K is not None and b.ndim == 1:
            nb = np.linalg.norm(b)
            if nb > 0:
                r = np.linalg.norm(self._K @ x - b) / nb
                # Nachiteration (16.09.2026): Straffedern (1e4-fach die groesste
                # Hauptdiagonale, Kopplungen und Kontakt) kosten die
                # Faktorisierung Stellen - am Drehlager brach LF1 mit Residuum
                # 1,3e-6 als "singulaer" ab, obwohl derselbe Aufbau kurz zuvor
                # konvergiert war. Ein Schritt x += K^-1 (b - K x) mit der
                # vorhandenen Faktorisierung holt die Stellen zurueck; ein
                # wirklich singulaeres System bleibt darueber (Test
                # tests/test_nachiteration.py).
                grenze, n_max = self.genauigkeit()
                schritte = 0
                while r > grenze and schritte < n_max:
                    dx = self._solve(b - self._K @ x)
                    if not np.all(np.isfinite(dx)):
                        break
                    x2 = x + dx
                    r2 = np.linalg.norm(self._K @ x2 - b) / nb
                    schritte += 1
                    if not r2 < r:
                        break
                    x, r = x2, r2
                self.nachiterationen = schritte
                self.residuum = float(r)
                if self._nachweis is not None and self._vorgabe is not None:
                    # Jetzt ist das Residuum der fertigen Loesung bekannt - es gilt, nicht
                    # das des ersten Loesens. Sonst nennt beschreibung() eine andere Zahl als
                    # die Meldung darunter. Die Schritte beider Stellen zaehlen zusammen;
                    # bewertet wird gegen die Vorgabe, mit der ama faktorisiert hat (die kann
                    # aelter sein als `grenze`, wenn die Einstellung sich seither geaendert
                    # hat - dann sagt die Beschreibung beide Zahlen).
                    #
                    # Der Rueckfall gehoert zum ersten Loesen: ama vermerkt ihn, wenn es die
                    # Schranke verfehlt. Holt die Schleife hier die Loesung doch darunter,
                    # ist er ueberholt und faellt weg - sonst meldete der Nachweis zugleich
                    # "gehalten" und einen gezogenen Rueckfall, und zwar jedes Mal, wenn die
                    # Schleife einen Schritt tut und damit Erfolg hat.
                    from ama import genauigkeit as ama_gen
                    rueck = (None if float(r) <= self._vorgabe.residuum
                             else self._nachweis.rueckfall)
                    self._nachweis = ama_gen.bewerte(
                        self._vorgabe, residuum=float(r), rechenart=self._nachweis.rechenart,
                        nachiterationen=self._nachweis.nachiterationen + schritte,
                        rueckfall=rueck)
                if r > grenze:
                    raise RuntimeError(
                        f"Gleichungssystem numerisch singulaer (Residuum {r:.1e}, Schranke {grenze:g}"
                        + (f", nach {schritte} Nachiterationen" if schritte else "") + ") - "
                        "Lagerung, freie Bauteile oder Kontaktdefinition pruefen; die Schranke steht "
                        "unter Berechnung → Einstellungen → Genauigkeit des Gleichungslösers.")
        return x

    @staticmethod
    def genauigkeit() -> tuple:
        """(Residuum-Schranke, hoechstens so viele Nachiterationen) aus den
        Einstellungen - Vorgabe 1e-6 und 3."""
        s = parallel.settings()
        try:
            grenze = float(getattr(s, "solver_residuum", 1e-6) or 1e-6)
        except (TypeError, ValueError):
            grenze = 1e-6
        try:
            n_max = max(0, int(getattr(s, "solver_nachiterationen", 3)))
        except (TypeError, ValueError):
            n_max = 3
        return grenze, n_max


# ==========================================================================
# Ergebnisse
# ==========================================================================
@dataclass
class Results:
    name: str = ""
    kind: str = "case"                      # case | combination | modal | buckling
    u: np.ndarray = None                    # (nn, 6) Verschiebungen/Verdrehungen
    reactions: np.ndarray = None            # (nn, 6) Auflagerreaktionen
    beam_end: dict = field(default_factory=dict)    # elem -> lokale Stabendkraefte (12,)
    beam_q: dict = field(default_factory=dict)      # elem -> Abschnittslasten (n,8): a, b, q1, q2
    shell_res: dict = field(default_factory=dict)   # elem -> [nx ny nxy mx my mxy]
    solid_res: dict = field(default_factory=dict)   # elem -> Spannungen (6,)
    feder_res: dict = field(default_factory=dict)   # elem -> lokale Federkraefte (6,)
    grenzschicht_res: dict = field(default_factory=dict)  # elem -> (sn, st1, st2)
    bimomente: dict = field(default_factory=dict)   # elem -> (B Anfang, B Ende) [Nm^2]
    woelb: dict = field(default_factory=dict)       # Knoten -> Verwoelbung [1/m]
    contact: list = field(default_factory=list)
    #: Sicherung des Kontaktzustands am Ende der Iteration - der Warmstart
    #: fuer den naechsten Lastfall derselben Situation (solve_cases)
    kontaktzustand: object = None
    contact_forces: np.ndarray = None       # (nn, 3)
    modes: np.ndarray = None                # (nmodes, nn, 6)
    freqs: np.ndarray = None                # [Hz]
    buckling_factors: np.ndarray = None
    buckling_modes: np.ndarray = None
    singular: list = field(default_factory=list)   # freie Bewegungen (singular.py)
    info: dict = field(default_factory=dict)
    model: Model = None
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- Kompatible abgeleitete Groessen ------------------------------------
    @property
    def umag(self) -> np.ndarray:
        return np.linalg.norm(self.u[:, :3], axis=1)

    @property
    def beam_forces(self) -> dict:
        """elem -> dict(L, N, Vy, Vz, Mt, My, Mz (Werte an Anfang/Ende), sig_max, util)."""
        if "beam_forces" not in self._cache:
            self._cache["beam_forces"] = {i: beam_end_forces(self.model, i, fl)
                                          for i, fl in self.beam_end.items()}
        return self._cache["beam_forces"]

    @property
    def shell_stress(self) -> dict:
        if "shell_stress" not in self._cache:
            self._cache["shell_stress"] = {i: shell_derived(self.model, i, r)
                                           for i, r in self.shell_res.items()}
        return self._cache["shell_stress"]

    @property
    def solid_stress(self) -> dict:
        if "solid_stress" not in self._cache:
            self._cache["solid_stress"] = {
                i: {"s": s, "vM": sl.von_mises(s), "principal": sl.principal(s)}
                for i, s in self.solid_res.items()}
        return self._cache["solid_stress"]

    @property
    def node_vm(self) -> np.ndarray:
        """Gemittelte Vergleichsspannung (Volumen/Schalen) bzw. Randspannung (Staebe) je Knoten.

        Vektorisiert (spannungen.knotenmittel, von Mises aus den Tensoren in
        einem Zug): am Drehlager (1,8 Mio. Tetraeder) brauchte die Schleife
        ueber solid_stress - je Element eigvalsh und von Mises in Python -
        etwa 50 s je Ergebnis, der Bericht mit drei Ergebnissen 154 s allein
        in der Uebersicht (12.09.2026); jetzt Sekunden.
        """
        if "node_vm" not in self._cache:
            from . import spannungen as spn
            m = self.model
            kn, w = [], []
            for i, d in self.beam_forces.items():
                nodes = m.elements[i].nodes
                kn.extend(int(n) for n in nodes)
                w.extend([float(d["sig_max"])] * len(nodes))
            for i, d in self.shell_stress.items():
                nodes = m.elements[i].nodes
                kn.extend(int(n) for n in nodes)
                w.extend([float(d["vM"])] * len(nodes))
            if self.solid_res:
                ids = list(self.solid_res)
                S = np.array([self.solid_res[i] for i in ids], float).reshape(-1, 6)
                vm = spn.volumen_werte(S, "sv")
                laengen = np.fromiter((len(m.elements[i].nodes) for i in ids), int, count=len(ids))
                import itertools
                kn_s = np.fromiter(itertools.chain.from_iterable(m.elements[i].nodes for i in ids), int,
                                   count=int(laengen.sum()))
                w_s = np.repeat(vm, laengen)
                knoten = np.concatenate([np.asarray(kn, int), kn_s]) if kn else kn_s
                werte = np.concatenate([np.asarray(w, float), w_s]) if w else w_s
            else:
                knoten, werte = np.asarray(kn, int), np.asarray(w, float)
            self._cache["node_vm"] = spn.knotenmittel(m.nn, knoten, werte)
        return self._cache["node_vm"]

    def stations(self, n: int = None) -> dict:
        """Schnittgroessen aller Stabelemente an n Stellen: elem -> dict(x, N, Vy, ...)."""
        n = n or self.model.design.stations
        key = ("stations", n)
        if key not in self._cache:
            self._cache[key] = {i: beam_station_forces(self.model, self, i, n)
                                for i in self.beam_end}
        return self._cache[key]

    def member_forces(self, member: Member, n: int = None) -> dict:
        return member_forces(self.model, self, member, n)

    def max_utilisation(self) -> Optional[float]:
        vals = [d["util"] for d in self.beam_forces.values() if d["util"] is not None]
        return max(vals) if vals else None

    # ---- Superposition ------------------------------------------------------
    @staticmethod
    def combine(model: Model, parts: list, name: str = "", kind: str = "combination") -> "Results":
        """Lineare Ueberlagerung: parts = [(Results, Faktor), ...]."""
        nn = model.nn
        out = Results(name=name, kind=kind, model=model)
        out.u = np.zeros((nn, NDOF))
        out.reactions = np.zeros((nn, NDOF))
        for r, f in parts:
            if not f:
                continue
            out.u += f * r.u
            out.reactions += f * r.reactions
            for i, v in r.beam_end.items():
                out.beam_end[i] = out.beam_end.get(i, 0.0) + f * v
            for i, v in r.beam_q.items():
                out.beam_q[i] = asm.abschnitte_zusammen(out.beam_q.get(i),
                                                        asm.skaliere_abschnitte(v, f))
            for i, v in r.shell_res.items():
                out.shell_res[i] = out.shell_res.get(i, 0.0) + f * v
            for i, v in r.solid_res.items():
                out.solid_res[i] = out.solid_res.get(i, 0.0) + f * v
        out.info = {"ndof": model.ndof, "superposition": True,
                    "factors": {r.name: f for r, f in parts}}
        return out

    def scaled(self, f: float, name: str = "") -> "Results":
        return Results.combine(self.model, [(self, f)], name or self.name, self.kind)

    # ---- Ausgabe --------------------------------------------------------------
    def summary(self) -> str:
        s = []
        if self.info.get("abbruch"):
            s.append("ABBRUCH                 : " + str(self.info["abbruch"]))
            s.append(f"Gezeigt wird die Verformung der letzten Kontakt-Iteration "
                     f"({self.info.get('abbruch_iteration', '?')}) - kein Gleichgewicht, keine Auflagerkräfte")
        if self.name:
            s.append(f"Ergebnis                : {self.name} ({self.kind})")
        s += [f"Freiheitsgrade gesamt   : {self.info.get('ndof', '?')}",
              f"davon aktiv             : {self.info.get('nfree', '?')}",
              f"Rechenzeit              : {self.info.get('time', 0):.3f} s"]
        if self.info.get("solver"):
            s.append(f"Gleichungsloeser        : {self.info['solver']}")
        if self.u is not None and self.u.size:
            i = int(np.argmax(self.umag))
            s.append(f"max. Verschiebung       : {self.umag[i]*1000:.4f} mm (Knoten {i})")
        try:
            nv = self.node_vm
            if nv is not None and nv.size and np.any(np.isfinite(nv)):
                s.append(f"max. Vergleichsspannung : {np.nanmax(nv)/1e6:.2f} MPa")
        except Exception:
            pass
        if self.reactions is not None and self.reactions.size:
            R = self.reactions[:, :3].sum(axis=0)
            s.append(f"Summe Auflagerkraefte   : [{R[0]:.1f}, {R[1]:.1f}, {R[2]:.1f}] N")
        if self.contact:
            from . import contact as ct
            s.append(ct.summary(self.contact))
            if self.info.get("contact_iterations"):
                # Wie viele der Runden teuer waren, steht nicht in der Zahl der
                # Runden: neu faktorisiert wird nur bei geaenderter Signatur
                # (19.09.2026). Und mit Plastizitaet sind es viele Laeufe.
                n_l = int(self.info.get("contact_laeufe", 1) or 1)
                n_f = self.info.get("contact_factorisations")
                s.append(f"Kontakt-Iterationen     : {self.info['contact_iterations']}"
                         + (f" in {n_l} Läufen" if n_l > 1 else "")
                         + (f", davon {int(n_f)} mit neuer Faktorisierung"
                            if n_f is not None else "")
                         + ("" if self.info.get("contact_converged", True)
                            else "  (NICHT konvergiert)"))
        if self.freqs is not None:
            s.append("Eigenfrequenzen [Hz]    : "
                     + ", ".join(f"{f:.3f}" for f in self.freqs[:10]))
            starr = int(self.info.get("starrkoerper", 0) or 0)
            if starr:
                s.append(f"Starrkoerperformen      : {starr} (f < {STARR_HZ:g} Hz) - Bauteile nicht "
                         "gehalten oder Kontakt offen")
            if self.info.get("kontakt"):
                s.append(f"Kontakt                 : {self.info['kontakt']}, "
                         f"{self.info.get('kontakt_aktiv', 0)} Bedingungen aktiv")
            if self.info.get("loeser"):
                s.append(f"Loeser                  : {NAMEN.get(self.info['loeser'], self.info['loeser'])}")
        pz = self.info.get("plastizitaet")
        if pz:
            s.append(f"Plastizität             : {pz.get('fliessend', 0)} Elemente fließen, "
                     f"ε_p,eq max {float(pz.get('eps_p_max', 0.0)) * 100:.3f} %, "
                     f"{pz.get('iterationen', 0)} Schritte in {pz.get('laststufen', 1)} Laststufen"
                     # Was die Zeit traegt, ist nicht die Zahl der Schritte, sondern
                     # die der Faktorisierungen: am Drehlager 3,2 s gegen 0,31 s je
                     # Rueckwaertseinsetzen (20.09.2026)
                     + (f", davon {pz['faktorisierungen']} mit neuer Faktorisierung "
                        "(konsistente Tangente)" if pz.get("faktorisierungen") else "")
                     + ("" if pz.get("konvergiert", True) else " - NICHT KONVERGIERT"))
        if self.buckling_factors is not None:
            s.append("Knicklastfaktoren       : "
                     + ", ".join(f"{f:.3f}" for f in self.buckling_factors[:10]))
        return "\n".join(s)


# ==========================================================================
# Abgeleitete Stabgroessen
# ==========================================================================
def beam_end_forces(model: Model, i: int, fl: np.ndarray) -> dict:
    e = model.elements[i]
    sec = model.sections[e.sec]
    mat = model.materials[e.mat]
    L = model.element_length(i)
    N = (-fl[0], fl[6])
    Vy = (-fl[1], fl[7])
    Vz = (-fl[2], fl[8])
    Mt = (-fl[3], fl[9])
    My = (-fl[4], fl[10])
    Mz = (-fl[5], fl[11])
    sig = max(abs(N[0]), abs(N[1])) / sec.A
    if sec.zmax > 0:
        sig += max(abs(My[0]), abs(My[1])) * sec.zmax / max(sec.Iy, 1e-20)
    if sec.ymax > 0:
        sig += max(abs(Mz[0]), abs(Mz[1])) * sec.ymax / max(sec.Iz, 1e-20)
    fy = mat.yield_strength(sec.t_max) if mat.fy else None
    return {"L": L, "N": N, "Vy": Vy, "Vz": Vz, "Mt": Mt, "My": My, "Mz": Mz,
            "sig_max": sig, "util": sig / fy if fy else None}


def beam_station_forces(model: Model, res: Results, i: int, n: int = 9) -> dict:
    """Schnittgroessen entlang eines Stabelements an n Stellen (x von 0 bis L).

    Gleichgewicht am Teilstab: Stabendkraefte am Anfang plus die Resultierende
    der Abschnittslasten ueber [0, x] und ihr Moment um x. Bei einer
    abschnittsweisen Last knickt der Querkraftverlauf an den Abschnittsenden;
    liegt ein Abschnittsende zwischen zwei Stellen, steht es nicht im Feld -
    die Stellen sind gleichmaessig verteilt, n hoch genug waehlen.
    """
    fl = res.beam_end[i]
    L = model.element_length(i)
    q = res.beam_q.get(i)
    x = np.linspace(0.0, L, n)
    # Lastresultierende ueber [0,x] und deren Moment um die Stelle x
    Q, Mq = asm.lastresultierende(q, x)                            # (n,3)
    N = -fl[0] - Q[:, 0]
    Vy = -fl[1] - Q[:, 1]
    Vz = -fl[2] - Q[:, 2]
    Mt = np.full(n, -fl[3])
    My = -fl[4] - fl[2] * x - Mq[:, 2]
    Mz = -fl[5] + fl[1] * x + Mq[:, 1]
    return {"x": x, "L": L, "N": N, "Vy": Vy, "Vz": Vz, "Mt": Mt, "My": My, "Mz": Mz}


def member_forces(model: Model, res: Results, member: Member, n: int = None) -> dict:
    """Schnittgroessen entlang eines Stabes (Kette von Elementen), x ab Stabanfang."""
    n = n or model.design.stations
    out = {k: [] for k in ("x", "N", "Vy", "Vz", "Mt", "My", "Mz")}
    out["elem"] = []
    x0 = 0.0
    for i in member.elements:
        st = beam_station_forces(model, res, i, n)
        for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"):
            out[k].append(st[k])
        out["x"].append(st["x"] + x0)
        out["elem"].append(np.full(n, i))
        x0 += st["L"]
    for k in out:
        out[k] = np.concatenate(out[k]) if out[k] else np.zeros(0)
    out["L"] = x0
    return out


def shell_derived(model: Model, i: int, r: np.ndarray) -> dict:
    e = model.elements[i]
    t = model.shells[e.sec].t
    n_forces = r[:3]
    m_forces = r[3:]
    sig_mem = n_forces / t
    sig_bend = 6.0 * m_forces / t ** 2
    sig_top = sig_mem + sig_bend
    sig_bot = sig_mem - sig_bend

    def vm(s):
        sx, sy, sxy = s
        return float(np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3 * sxy ** 2))

    X = model.nodes[e.nodes]
    T3, _, _ = sh.shell_frame(X[0], X[1], X[2])
    return {"n": n_forces, "m": m_forces, "sig_top": sig_top, "sig_bot": sig_bot,
            "vM_top": vm(sig_top), "vM_bot": vm(sig_bot),
            "vM": max(vm(sig_top), vm(sig_bot)), "T3": T3}


# ==========================================================================
# Statisches System
# ==========================================================================
class StaticSystem:
    """Assemblierte und faktorisierte Steifigkeit fuer beliebig viele Lastfaelle."""

    def __init__(self, model: Model, workers: int = None, progress=None,
                 aktiv=None, situation: str = ""):
        t0 = time.time()
        self.model = model
        #: Situation: Maske der wirksamen Elemente (None = alle) und ihr Name
        self.aktiv = None if aktiv is None else np.asarray(aktiv, bool)
        basis = model.grundmaske() if hasattr(model, "grundmaske") else None
        if basis is not None:
            # abgeschaltete Staebe (Member.aus) wirken in keiner Situation
            self.aktiv = basis if self.aktiv is None else (self.aktiv & basis)
        self.situation = situation
        self.K = asm.stiffness(model, workers, self.aktiv)
        self.fixed, self.vals = asm.constrained_dofs(model, self.K)
        self.fi = np.where(~self.fixed)[0]
        self.si = np.where(self.fixed)[0]
        self.Kff = self.K[self.fi][:, self.fi].tocsc()
        self.Kfs = self.K[self.fi][:, self.si].tocsc() if np.any(self.vals[self.si]) else None
        if progress:
            _melde(progress, f"Gleichungssystem aufgestellt ({len(self.fi)} aktive FHG)", 0.20)
        self._solver = None
        self.backend = "-"
        #: Freie Bewegungen und ihre Hilfsfesselung - erst nach einem sonst
        #: unloesbaren System belegt (:meth:`hilfsfesselung`)
        self.singular: list = []
        #: "" (noch nicht gesucht) | "grob" (nur die Vorpruefung, ohne Befund)
        #: | "voll" (wirklich gesucht)
        self._gesucht = ""
        #: Die Hilfsfesselung als Lagrange-Rand: (m, n_frei)-Matrix der
        #: festgehaltenen Bewegungen, None solange keine noetig war.
        self._Vf = None
        self._V = None
        self._progress = progress
        #: Summe der Faktorisierungszeiten aller Loeser dieses Systems, und
        #: die Groessen der zuletzt faktorisierten Matrix - fuer Results.info.
        self.zeit_faktorisierung = 0.0
        self.nnz_matrix = 0
        self.nnz_faktor = 0
        self.t_assemble = time.time() - t0
        if not model.has_contact:
            _ = self.solver          # sofort faktorisieren (bei Kontakt erst mit Kc)

    @property
    def solver(self) -> LinearSolver:
        """Faktorisierung der Grundsteifigkeit (bei Bedarf)."""
        if self._solver is None:
            t0 = time.time()
            try:
                self._solver = LinearSolver(self.gerandet(self.Kff))
                self._loeser_merken(self._solver)
            except (RuntimeError, ValueError) as ex:
                # "Factor is exactly singular" sagt niemandem, was fehlt
                from .diagnose import singulaer_text
                raise RuntimeError(singulaer_text(self.model, ex, self)) from None
            self.backend = self._solver.backend
            self.t_assemble += time.time() - t0
            if self._progress:
                _melde(self._progress,
                       f"Faktorisiert ({self._solver.beschreibung()}, "
                       f"{time.time() - t0:.2f} s)", 0.32)
        return self._solver

    def _loeser_merken(self, ls: LinearSolver):
        """Zeit und Groessen einer Faktorisierung mitschreiben.

        Die Zeit wird summiert (ein Lastfall am Drehlager faktorisiert 28 mal,
        gemessen 19.09.2026), die Nichtnullen sind die der letzten Matrix -
        sie aendern sich zwischen den Kontaktschritten nur um die Fugenzeilen.
        """
        self.zeit_faktorisierung += getattr(ls, "zeit_faktorisierung", 0.0)
        self.nnz_matrix = getattr(ls, "nnz_matrix", 0) or self.nnz_matrix
        self.nnz_faktor = getattr(ls, "nnz_faktor", 0) or self.nnz_faktor

    def gerandet(self, Kff):
        """Kff mit dem Lagrange-Rand der Hilfsfesselung.

        Aus K wird

            [ K    V^T ]   [ u ]   [ F ]
            [ V     0  ] * [ l ] = [ 0 ]

        Die Zusatzzeilen erzwingen ``V u = 0`` - der Starrkoerperanteil der
        freien Bewegungen ist damit exakt null statt nur klein. Die Haltekraft
        ist ``V^T l`` und verteilt sich damit ueber das Teil **wie die
        Bewegung selbst**; das ist die Traegheitsentlastung, und genau darum
        geht durch den Mittelschnitt eines frei schwebenden Stabes die halbe
        Last und nicht die ganze. Ein einzelner gesperrter Freiheitsgrad
        taete das nicht - er leitete alles in einen Punkt.

        Der Rand kostet zwei Eintraege je Nichtnull von V. Die fruehere
        Straffeder ``K + k*V^T V`` kostete deren Quadrat: am Drehlagermodell
        826 GB (siehe :func:`singular.stabilisieren`).
        """
        if self._Vf is None or self._Vf.shape[0] == 0:
            return Kff
        m = self._Vf.shape[0]
        return sparse.bmat([[Kff, self._Vf.T],
                            [self._Vf, sparse.csr_matrix((m, m))]], format="csc")

    @property
    def _rand(self) -> int:
        """Zahl der Randzeilen der Hilfsfesselung (0 = keine)."""
        return 0 if self._Vf is None else int(self._Vf.shape[0])

    def freie_bewegungen(self, erzwingen: bool = False) -> list:
        """Bewegungen, die das Modell nicht haelt - gesucht, nicht gefesselt.

        Die Suche laeuft hoechstens einmal je System. Nach einer geglueckten
        Rechnung soll sie nichts kosten: dann laeuft sie nur, wenn ueberhaupt
        ein Teiltragwerk **ohne jedes** feste Lager dasteht - zwei
        Topologielaeufe, die die Modellpruefung ohnehin macht.

        ``erzwingen`` hebt diese Vorpruefung auf. Nach einem Abbruch muss das
        sein: ein Bauteil kann ein Lager haben und trotzdem beweglich sein -
        eine Platte, die nur senkrecht gehalten ist, verschiebt sich in ihrer
        Ebene. Die grobe Vorpruefung saehe sie als gehalten an.
        """
        if self._gesucht == "voll" or (self._gesucht and not erzwingen):
            return self.singular
        from .diagnose import gehaltene_knoten, teiltragwerke
        from . import singular as sg
        try:
            if not erzwingen:
                fest, _kontakt = gehaltene_knoten(self.model)
                if all(set(g) & fest for g in teiltragwerke(self.model)):
                    self._gesucht = "grob"
                    return []
            self.singular = sg.restfreiheiten(self.model)
        except Exception:                 # noqa: BLE001 - eine Diagnose darf nie sperren
            self.singular = []
        self._gesucht = "voll"
        return self.singular

    def hilfsfesselung(self) -> bool:
        """Die freien Bewegungen mit je einer Zeile festhalten - als Rand.

        Statt abzubrechen wird weitergerechnet: jede Bewegung, die das Modell
        nicht haelt, bekommt eine Zeile ``v^T u = 0``. Weil K·v = 0 ist,
        bleiben Spannungen und Dehnungen davon unberuehrt - nur der
        Starrkoerperanteil der Verschiebung faellt weg, und der ist ohnehin
        willkuerlich (:meth:`ohne_starrkoerper` nimmt ihn zusaetzlich heraus,
        falls doch etwas uebrig bleibt).

        Hier stand bis zuletzt eine Straffeder ``K + k*V^T V``. Das aeussere
        Produkt hat so viele Eintraege wie die Zeile Nichtnullen im Quadrat;
        am Drehlagermodell waren das 6,9e10 - rund 826 GB, und der Rechner
        stand still. Der Rand leistet dasselbe exakt und kostet zwei Eintraege
        je Nichtnull (:meth:`gerandet`).

        Rueckgabe True, wenn eine Fesselung eingebaut wurde.
        """
        if self._Vf is not None:
            return False
        from . import singular as sg
        try:
            V, sing = sg.hilfsfesselung(self.model,
                                        self.freie_bewegungen(erzwingen=True),
                                        frei=self.fi)
        except Exception:                 # noqa: BLE001 - das darf nie sperren
            return False
        if not sing or V.shape[0] == 0:
            return False
        self.singular, self._V = sing, V
        self._Vf = sparse.csr_matrix(V[:, self.fi])
        for x in sing:
            x.gefesselt = True
        self._solver = None
        return True

    def ohne_starrkoerper(self, u: np.ndarray) -> np.ndarray:
        """Den willkuerlichen Starrkoerperanteil der Hilfsfesselung abziehen."""
        if self._V is None:
            return u
        from . import singular as sg
        return sg.bereinigen(self._V, u)

    def kontakt_loeser_freigeben(self) -> None:
        """Die behaltene Faktorisierung mit Kontaktsteifigkeit zurueckgeben."""
        ls = getattr(self, "_kontakt_loeser", None)
        self._kontakt_loeser = None
        self._kontakt_signatur = None
        if ls is not None:
            ls.freigeben()

    def solve(self, F: np.ndarray, K_extra: sparse.spmatrix = None,
              F_extra: np.ndarray = None, us: np.ndarray = None,
              signatur=None) -> np.ndarray:
        """Loesen fuer Lastvektor F; optional zusaetzliche Steifigkeit (Kontakt)
        und vorgegebene Verschiebungen ``us`` des Lastfalls (Zwangsverformungen,
        wirksam nur an gesperrten FHG): K_ff u_f = F_f - K_fs u_s.

        ``signatur`` kennzeichnet K_extra (ContactSystem.signatur): mit
        derselben Signatur wie beim vorigen Aufruf bleibt die Faktorisierung
        und es wird nur rueckwaerts eingesetzt. Die Kontakt-Iteration am
        Drehlager brauchte 42 Schritte zu je 10 bis 13 s Faktorisierung, davon
        viele mit unveraenderter Matrix (Setzrunden der Reibkraft, Nachfuehren
        der Gleitrichtungen). Ohne Signatur wird wie bisher faktorisiert und
        gleich wieder freigegeben."""
        u = self.vals.copy()
        if us is not None:
            u[self.si] += us[self.si]
        rhs = F[self.fi]
        if F_extra is not None:
            rhs = rhs + F_extra[self.fi]
        vorgabe = np.any(u[self.si])
        try:
            if K_extra is None:
                if vorgabe:
                    if self.Kfs is None:
                        self.Kfs = self.K[self.fi][:, self.si].tocsc()
                    rhs = rhs - self.Kfs @ u[self.si]
                u[self.fi] = self._geloest(self.solver, rhs)
            else:
                Kt = (self.K + K_extra)
                Ktff = Kt[self.fi][:, self.fi].tocsc()
                if vorgabe:
                    Ktfs = Kt[self.fi][:, self.si]
                    rhs = rhs - Ktfs @ u[self.si]
                schluessel = None if signatur is None else (signatur, self._rand, id(self._Vf))
                ls = getattr(self, "_kontakt_loeser", None)
                neu = schluessel is None or ls is None \
                    or schluessel != getattr(self, "_kontakt_signatur", None)
                if neu:
                    self.kontakt_loeser_freigeben()
                    ls = LinearSolver(self.gerandet(Ktff))
                    self._loeser_merken(ls)
                    self.faktorisierungen = getattr(self, "faktorisierungen", 0) + 1
                self.backend = ls.backend
                try:
                    u[self.fi] = self._geloest(ls, rhs)
                finally:
                    if schluessel is None:
                        # ohne Signatur gilt die Faktorisierung nur fuer diesen
                        # Schritt - sofort zurueckgeben (LinearSolver.freigeben)
                        ls.freigeben()
                    elif neu:
                        self._kontakt_loeser, self._kontakt_signatur = ls, schluessel
        except (RuntimeError, ValueError) as ex:
            # Singulaer (Faktorisierung oder Residuum): sagen, was dem Modell fehlt
            if "Teiltragwerk" in str(ex) or "ohne Netz" in str(ex):
                raise
            from .diagnose import singulaer_text
            raise RuntimeError(singulaer_text(self.model, ex, self)) from None
        return u

    def _geloest(self, ls: "LinearSolver", rhs: np.ndarray) -> np.ndarray:
        """Loesen mit dem Lagrange-Rand: rechte Seite auffuellen, Rand abschneiden.

        Die Randzeilen fordern ``V u = 0``; ihre rechte Seite ist null. Die
        Multiplikatoren am Ende der Loesung sind die Haltekraefte und gehen
        den Aufrufer nichts an.
        """
        m = self._rand
        if not m:
            return ls.solve(rhs)
        x = ls.solve(np.concatenate([rhs, np.zeros(m)]))
        return np.asarray(x, float).ravel()[:len(rhs)]

    def reactions(self, u: np.ndarray, F: np.ndarray, K_extra=None) -> np.ndarray:
        K = self.K if K_extra is None else (self.K + K_extra)
        R = np.zeros(self.model.ndof)
        R[self.si] = (K @ u)[self.si] - F[self.si]
        # Federlager (Knoten-, Linien- und Flaechenlager): Federkraft als Reaktion
        from . import supports as sup
        lin, _ = sup.split(sup.expand(self.model))
        for e in lin:
            if e.typ == "spring" and e.stiffness:
                R[e.index] += -e.stiffness * u[e.index]
        return R


# ==========================================================================
# Lasten eines Lastfalls / einer Kombination
# ==========================================================================
def case_loads(model: Model, factors: dict, aktiv=None) -> tuple:
    """(F, feq, q, temp) fuer eine Linearkombination von Lastfaellen.
    feq: elem -> lokale aequivalente Knotenlasten (unkondensiert),
    q: elem -> lokale Streckenlast (2,3), temp: elem -> dT.
    ``aktiv``: abgeschaltete Elemente einer Situation tragen keine Last."""
    F = np.zeros(model.ndof)
    feq: dict = {}
    q: dict = {}
    temp: dict = {}
    for name, f in factors.items():
        if not f:
            continue
        lc = model.case(name)
        F += f * asm.load_vector(model, lc, aktiv)
        for i, v in asm.element_equivalent_loads(model, lc, aktiv).items():
            feq[i] = feq.get(i, 0.0) + f * v
        for i, v in asm.element_distributed_loads(model, lc, aktiv).items():
            q[i] = asm.abschnitte_zusammen(q.get(i), asm.skaliere_abschnitte(v, f))
        for tl in lc.temp_loads:
            temp[tl.elem] = temp.get(tl.elem, 0.0) + f * tl.dT
        # Anfangsspannungen der Vorspannung in Volumen - fuer die Spannungs-
        # rueckrechnung (sigma = D eps - sigma0); unter dem Schluessel "sigma0",
        # damit die Elementnummern von temp unberuehrt bleiben
        for v in getattr(lc, "vorspannungen", None) or []:
            if getattr(v, "art", "stab") == "koerper" and v.kraft:
                sig = temp.setdefault("sigma0", {})
                for i, s0 in asm.solid_prestress(model, v).items():
                    sig[i] = sig.get(i, 0.0) + f * s0
    return F, feq, q, temp


def case_uebermass(model: Model, factors: dict) -> dict:
    """{Name der Fuge: Gesamtueberdeckung [m]} einer Linearkombination.

    Das Uebermass wird wie jede andere Last mit dem Faktor der Kombination
    vervielfacht. Geometrisch ist ein Uebermass zwar keine Last, sondern ein
    Mass - aber es steht in einem Lastfall, und ein Lastfall geht mit seinem
    Beiwert in die Kombination ein. Wer das nicht will, legt das Uebermass in
    einen staendigen Lastfall mit gamma = 1,0.
    """
    aus: dict = {}
    for name, f in (factors or {}).items():
        if not f or name not in model.load_cases:
            continue
        for u in (getattr(model.case(name), "uebermasse", None) or []):
            ziel = str(u.ziel)
            aus[ziel] = aus.get(ziel, 0.0) + float(f) * float(u.ueberdeckung)
    return {k: v for k, v in aus.items() if v}


def case_prescribed(model: Model, factors: dict, warn=None):
    """Vorgegebene Verschiebungen (Zwangsverformungen) einer Linearkombination
    von Lastfaellen als Vektor ueber alle FHG - oder None, wenn es keine gibt.
    ``warn(text)`` meldet vorgegebene FHG ohne Lager (dort unwirksam)."""
    us = np.zeros(model.ndof)
    gibt = False
    for name, f in factors.items():
        if not f:
            continue
        lc = model.case(name)
        if not lc.zwangsverformungen:
            continue
        gibt = True
        for zv in lc.zwangsverformungen:
            for d in zv.dofs:
                us[NDOF * int(zv.node) + int(d)] += f * float(zv.u[d])
        if warn is not None:
            ohne = model.zwang_ohne_lager(name)
            if ohne:
                namen = ("ux", "uy", "uz", "phix", "phiy", "phiz")
                warn(f"Zwangsverformung im Lastfall {name} ohne Lager - unwirksam: "
                     + ", ".join(f"Knoten {n} {namen[d]}" for n, d in ohne[:8])
                     + (" ..." if len(ohne) > 8 else ""))
    return us if gibt else None


# ==========================================================================
# Nachlaufrechnung
# ==========================================================================
def _post_chunk(model: Model, idx: list[int], extra: dict) -> list:
    u = extra["u"]
    feq = extra["feq"]
    temp = extra["temp"]
    out = []
    for i in idx:
        e = model.elements[i]
        mat = model.materials[e.mat]
        X = model.nodes[e.nodes]
        d = asm.element_dofs(e, model)
        ue = u[d]
        if e.typ in asm.LINE_TYPES:
            f0 = feq.get(i, np.zeros(12))
            if model.stab_woelbt(e):
                # 14 FHG: Stabendkraefte und die Bimomente an beiden Enden
                kl, T3, L = asm.beam_woelb_local(model, e)
                ul = asm.transform14(T3) @ ue
                A = asm.beam_versatz(e)
                if A is not None:
                    A14 = np.eye(14)
                    A14[:12, :12] = A
                    ul = A14 @ ul
                f14 = np.zeros(14)
                f14[:12] = f0
                fl = kl @ ul - f14
                out.append((i, "beam", fl[:12]))
                out.append((i, "bimoment", (-float(fl[12]), float(fl[13]))))
                continue
            kl, T3, T, L = asm.beam_local(model, e)
            ul = T @ ue
            A = asm.beam_versatz(e)
            if A is not None:
                ul = A @ ul                     # Verschiebung des Stabendes hinter dem Versatz
            kl_s, f_s, rec = kl, f0, None
            if getattr(e, "hinge_springs", None):
                kl_s, f_s, rec = asm.hinge_springs(kl, f0, e.hinge_springs)
            if e.hinges:
                _, _, cond = asm.condense(kl_s, f_s, e.hinges)
                c, r, Kcc_inv, Kcr = cond
                ul = ul.copy()
                ul[c] = Kcc_inv @ (f_s[c] - Kcr @ ul[r])
            if rec is not None:
                ul = asm.hinge_local_disp(rec, ul)      # Stabende hinter der Feder
            fl = kl @ ul - f0
            out.append((i, "beam", fl))
        elif e.typ in asm.SHELL_TYPES:
            prop = model.shells[e.sec]
            t = prop.t
            if asm.schalen_formulierung(e, prop) != "dkt":
                from .elements import shell_rm
                lam = asm.laminat_von(model, prop)
                st = shell_rm.stress_schale(e.typ, X, mat.E, mat.nu, t, ue, laminat=lam)
                acc = np.concatenate([np.asarray(st["n"], float), np.asarray(st["m"], float)])
                if i in temp:
                    A_ = lam.A if lam is not None else sh._material_matrices(mat.E, mat.nu, t)[0]
                    acc[:3] -= A_ @ (mat.alpha * temp[i] * np.array([1.0, 1.0, 0.0]))
                out.append((i, "shell", acc))
                continue
            tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
            acc = np.zeros(6)
            # Beim Viereck haben die beiden Dreiecke verschiedene lokale
            # Systeme (x laeuft einmal an der Kante, einmal an der Diagonale).
            # Vor dem Mitteln werden beide in das Elementsystem gedreht -
            # sonst werden Groessen aus zwei Systemen addiert.
            T3e, _xy, _A = sh.shell_frame(X[0], X[1], X[2])
            for tri in tris:
                idx6 = []
                for n in tri:
                    idx6.extend(range(6 * n, 6 * n + 6))
                st = sh.shell3_stress(X[tri[0]], X[tri[1]], X[tri[2]],
                                      mat.E, mat.nu, t, ue[idx6])
                n_v, m_v = st["n"], st["m"]
                if tri != (0, 1, 2):
                    T3t, _xy2, _A2 = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
                    phi = sh.frame_winkel(T3t, T3e)
                    n_v = sh.dreh_tensor(n_v, -phi)
                    m_v = sh.dreh_tensor(m_v, -phi)
                acc[:3] += n_v
                acc[3:] += m_v
            acc /= len(tris)
            if i in temp:
                Dm = sh._material_matrices(mat.E, mat.nu, t)[0]
                acc[:3] -= Dm @ (mat.alpha * temp[i] * np.array([1.0, 1.0, 0.0]))
            out.append((i, "shell", acc))
        elif e.typ in asm.SOLID_TYPES:
            ev = extra.get("ev_dilatation") if isinstance(extra, dict) else None
            if ev and i in ev:
                # tet4 mit knotengemittelter Dilatation: die Steifigkeit
                # rechnet mit der ueber den Knotenverband gemittelten
                # Volumendehnung, die Spannung muss dieselbe nehmen, sonst
                # passen Kraefte und Spannungen nicht zusammen. Der
                # deviatorische Anteil bleibt elementlokal, der volumetrische
                # wird ersetzt: sigma = D_dev eps + K ev_gemittelt m. Der
                # tet4 hat konstante Spannung - ein Punkt genuegt.
                kap = sl.kompressionsmodul(mat.E, mat.nu)
                dN_, _V_ = sl.tet4_shape_grad(X)
                eps_ = sl._B_from_grad(dN_) @ ue
                werte = [sl.D_deviatorisch(mat.E, mat.nu) @ eps_
                         + kap * float(ev[i]) * sl.VOIGT_M]
            else:
                # **Alle** Auswertepunkte, nicht nur die Mitte. Beim tet4 ist
                # das derselbe eine Punkt; beim Sechsflaechner ist die Mitte
                # unter Biegung der schlechteste Ort, den man waehlen kann -
                # gemessen am Kragtraeger 20.09.2026: Mitte 11,15 N/mm2,
                # Eckpunkt 15,51, Balken M/W 15,0. Die Mitte zeigte damit
                # 71,9 % des Randwerts, und der Anwender sah zu wenig.
                werte = [np.asarray(x, float) for x in
                         sl.stress_points(e.typ, X, mat.E, mat.nu, ue)]
            abzug = None
            if i in temp:
                abzug = sl.D_matrix(mat.E, mat.nu) @ (
                    mat.alpha * temp[i] * np.array([1.0, 1.0, 1.0, 0, 0, 0]))
            sig0 = temp.get("sigma0") if isinstance(temp, dict) else None
            if sig0 and i in sig0:
                # Vorspannung: sigma = D eps - sigma0. sigma0 ist das Mittel
                # ueber die Gausspunkte (plastizitaet.sigma0_je_element) und
                # damit je Element konstant - es verschiebt alle
                # Auswertepunkte um denselben Betrag.
                s0 = np.asarray(sig0[i], float)
                abzug = s0 if abzug is None else abzug + s0
            if abzug is not None:
                werte = [w - abzug for w in werte]
            if sig0 and i in sig0 and len(werte) > 1:
                # Fliessende Elemente: nur die Mitte. Die Plastizitaet wird an
                # den **Gausspunkten** erzwungen, die Auswertepunkte (Ecken)
                # liegen ausserhalb, und die abgezogene Vorspannung D eps_p
                # ist das Mittel ueber die Gausspunkte. An einer Ecke waechst
                # eps ueber dieses Mittel hinaus, eps_p bleibt zurueck - die
                # gemeldete Spannung schiesst ueber die Fliessflaeche hinaus.
                # Gemessen am Reibblock (20.09.2026): Eckwert 2,93 MPa gegen
                # die verfestigte Fliessgrenze 1,42 - und damit ueber dem
                # elastischen Spitzenwert 2,30, was es nicht geben kann.
                # In der Mitte ist das Elementmittel die richtige Berichtigung.
                werte = werte[:1]
            s_ = werte[0] if len(werte) == 1 else max(werte, key=sl.von_mises)
            out.append((i, "solid", s_))
        elif e.typ in asm.PLANE_TYPES:
            from .elements import ebene
            t = model.shells[e.sec].t if e.sec and e.sec in model.shells else 1.0
            zustand = getattr(e, "zustand", "spannung")
            s_ = np.asarray(ebene.stress_ebene(e.typ, X, mat.E, mat.nu, t, zustand, ue), float)
            if i in temp:
                # Waermedehnung ohne Spannung: sigma = D (eps - eps_T)
                if zustand == "spannung":
                    k = mat.E * mat.alpha * temp[i] / (1.0 - mat.nu)
                    s_[0] -= k
                    s_[1] -= k
                else:
                    k = mat.E * mat.alpha * temp[i] / (1.0 - 2.0 * mat.nu)
                    s_[:3] -= k
            out.append((i, "solid", s_))
        elif e.typ == "feder":
            from .elements import verbindung as vb
            fp = model.federn[e.sec]
            T3 = vb.feder_achsen(X[0], X[1], fp.achse, e.roll)
            out.append((i, "feder", np.asarray(vb.feder_kraefte(fp.k, T3, ue), float)))
        elif e.typ in asm.GRENZSCHICHT_TYPES:
            from .elements import verbindung as vb
            gp = model.grenzschichten[e.sec]
            k = len(e.nodes) // 2
            out.append((i, "grenzschicht",
                        np.asarray(vb.grenzschicht_spannung(X[:k], X[k:], gp.kn, gp.kt, ue), float)))
    return out


def postprocess(model: Model, u: np.ndarray, res: Results, feq: dict = None,
                q: dict = None, temp: dict = None, workers: int = None, aktiv=None):
    """Rohgroessen je Element aus dem Verschiebungsvektor u (ndof,).
    Abgeschaltete Elemente (``aktiv`` False) bekommen Nullen: sie wirken nicht."""
    feq = feq if feq is not None else {}
    q = q if q is not None else {}
    temp = temp if temp is not None else {}
    idx = asm.aktive_indizes(model, aktiv)
    ev = (asm.knotendilatation_je_element(model, u, aktiv)
          if getattr(model, "knotendilatation", False) else None)
    items = parallel.map_elements(_post_chunk, model, idx, workers=workers,
                                  extra={"u": u, "feq": feq, "temp": temp,
                                         "ev_dilatation": ev})
    if aktiv is not None:
        inaktiv = [i for i in range(len(model.elements)) if not aktiv[i]]
        res.info["inaktiv"] = inaktiv
        for i in inaktiv:
            e = model.elements[i]
            if e.typ in asm.LINE_TYPES:
                res.beam_end[i] = np.zeros(12)
            elif e.typ in asm.SHELL_TYPES:
                res.shell_res[i] = np.zeros(6)
            elif e.typ == "feder":
                res.feder_res[i] = np.zeros(6)
            elif e.typ in asm.GRENZSCHICHT_TYPES:
                res.grenzschicht_res[i] = np.zeros(3)
            else:
                res.solid_res[i] = np.zeros(6)
    for i, kind, val in items:
        if kind == "beam":
            res.beam_end[i] = val
            if i in q:
                res.beam_q[i] = np.asarray(q[i], float)
        elif kind == "bimoment":
            res.bimomente[i] = val
        elif kind == "shell":
            res.shell_res[i] = val
        elif kind == "feder":
            res.feder_res[i] = val
        elif kind == "grenzschicht":
            res.grenzschicht_res[i] = val
        else:
            res.solid_res[i] = val
    res._cache.clear()


# ==========================================================================
# Lineare Statik
# ==========================================================================
def grundlasten(model: Model, factors: dict) -> list:
    """Die Grundlasten, die in dieser direkt geloesten Rechnung noch fehlen."""
    return [n for n, lc in model.load_cases.items()
            if getattr(lc, "grundlast", False) and not factors.get(n)]


def _plastisch(model) -> bool:
    """Fliessen eingeschaltet (Model.plastizitaet.an)?"""
    pz = getattr(model, "plastizitaet", None)
    return bool(pz is not None and getattr(pz, "an", False))


def _nichtlinear(model) -> bool:
    """Kombinationen direkt rechnen statt ueberlagern: bei Kontakt - und bei
    Fliessen, denn plastische Dehnungen ueberlagern sich nicht (17.09.2026)."""
    return bool(model.has_contact or _plastisch(model))


def _kontakt_info_sammeln(res, cinfo: dict) -> dict:
    """Die Kennzahlen des Kontakts aufaddieren statt ueberschreiben.

    Mit Plastizitaet loest derselbe Lastfall viele Male - am Drehlager 18
    Schritte in drei Laststufen. ``res.info.update(cinfo)`` liess davon nur
    die Zahlen des **letzten** Laufes stehen: die Zusammenfassung meldete
    "Kontakt-Iterationen: 2" fuer eine Rechnung von 2289 s, und die
    Kontaktmeldungen der frueheren Schritte (etwa "Nachpruefung der Reibung
    nach 40 Zustandswechseln abgebrochen") fielen ganz weg (19.09.2026).
    "Nicht konvergiert" klebt: ein einziger gekappter Lauf zaehlt.
    """
    for k in ("contact_iterations", "contact_factorisations"):
        if k in cinfo:
            cinfo[k] = int(res.info.get(k, 0) or 0) + int(cinfo[k] or 0)
    cinfo["contact_laeufe"] = int(res.info.get("contact_laeufe", 0) or 0) + 1
    cinfo["contact_converged"] = bool(res.info.get("contact_converged", True)) \
        and bool(cinfo.get("contact_converged", True))
    alt_log = list(res.info.get("contact_log", []) or [])
    neu_log = [z for z in (cinfo.get("contact_log") or []) if z not in alt_log]
    cinfo["contact_log"] = alt_log + neu_log
    return cinfo


def _plastizitaet_rechnen(model, res, F, rechnen, aktiv, temp, progress, start):
    """Fliessen der Volumen (plastizitaet.iteration) um den linearen
    Loesungsweg eines Lastfalls: jede Loesung ist derselbe Lastfall mit der
    Zusatzlast F_p, mit Kontakt warm gestartet vom letzten Zustand.
    Rueckgabe (u, R, aktiv, temp); temp["sigma0"] traegt D eps_p, damit der
    Spannungsnachlauf sigma = D eps - D eps_p rechnet."""
    from . import plastizitaet as pl
    halter = {"start": start, "R": None, "aktiv": aktiv}

    def loesen(Fg, dK=None):
        u_, R_, a_ = rechnen(Fg, halter["start"], dK)
        halter["R"], halter["aktiv"] = R_, a_
        if getattr(res, "kontaktzustand", None) is not None:
            halter["start"] = res.kontaktzustand
        return u_

    log: list = []
    u, zustand, F_p, info = pl.iteration(model, F, loesen, model.plastizitaet, aktiv, log=log,
                                         progress=lambda t: _melde(progress, t),
                                         loesen_tangente=loesen)
    if not isinstance(temp, dict):
        temp = {}
    sig0 = temp.setdefault("sigma0", {})
    for i, s0 in pl.sigma0_je_element(model, zustand).items():
        sig0[i] = np.asarray(sig0.get(i, 0.0), float) + s0
    for z in log:
        _melde(progress, z)
    res.info["plastizitaet"] = {k: v for k, v in info.items() if k != "verlauf"}
    res.info["plastizitaet"]["log"] = list(log)
    # eps_p_eq steht je Gausspunkt; gemeldet wird der groesste Wert des
    # Elements - ein Element gilt als fliessend, sobald ein Punkt fliesst.
    res.info["plastisch"] = {int(i): float(np.max(v)) for i, v in zustand.eps_p_eq.items()
                             if float(np.max(v)) > 0}
    return u, halter["R"], halter["aktiv"], temp


def _solve_loads(model: Model, system: StaticSystem, factors: dict, name: str,
                 kind: str, workers=None, progress=None, start=None,
                 einfrieren=None, fenster=None, probelauf: bool = False) -> Results:
    t0 = time.time()
    aktiv = getattr(system, "aktiv", None)
    # Grundlasten (LoadCase.grundlast) wirken in jeder direkt geloesten
    # Rechnung mit - dort gibt es keine Ueberlagerung, in die man sie spaeter
    # legen koennte. Linear bleibt der Lastfall, was er ist.
    grund = grundlasten(model, factors) if (_nichtlinear(model) or model.hat_ausfallstaebe()) else []
    if grund:
        factors = dict(factors)
        for n in grund:
            factors[n] = 1.0
        _melde(progress, f"{name}: Grundlast wirkt mit - " + ", ".join(grund))
    F, feq, q, temp = case_loads(model, factors, aktiv)
    us = case_prescribed(model, factors, warn=progress)
    ueber = case_uebermass(model, factors)
    res = Results(name=name, kind=kind, model=model)
    if getattr(system, "situation", ""):
        res.info["situation"] = system.situation
    if grund:
        res.info["grundlast"] = list(grund)
    def _rechnen(F_ges=None, start_=None, K_zusatz=None):
        """Der Loesungsweg des Lastfalls - wiederholbar. F_ges ersetzt die
        Last (Plastizitaet: F + F_p), start_ den Warmstart des Kontakts,
        K_zusatz die Steifigkeitsaenderung der konsistenten Tangente
        (plastizitaet._newton) - damit wird neu faktorisiert."""
        Fg = F if F_ges is None else F_ges
        st = start if start_ is None else start_
        if model.hat_ausfallstaebe():
            u_, R_, aktiv_, ausfall, alog, kontakt = solve_with_ausfall(
                model, system, Fg, us=us, progress=progress, uebermass=ueber,
                K_zusatz=K_zusatz, probelauf=probelauf)
            res.info["ausfall"] = ausfall
            res.info["ausfall_log"] = alog
            if kontakt is not None:
                res.contact, res.contact_forces, cinfo = kontakt
                res.info.update(_kontakt_info_sammeln(res, cinfo))
            return u_, R_, aktiv_
        if model.has_contact:
            u_, R_, res.contact, res.contact_forces, cinfo = solve_with_contact(
                model, system, Fg, progress=progress, us=us, uebermass=ueber,
                start=None if probelauf else st, einfrieren=einfrieren,
                fenster=fenster, K_zusatz=K_zusatz, probelauf=probelauf)
            res.kontaktzustand = cinfo.pop("contact_state", None)
            res.info.update(_kontakt_info_sammeln(res, cinfo))
            return u_, R_, aktiv
        u_ = system.solve(Fg, K_extra=K_zusatz, us=us)
        return u_, system.reactions(u_, Fg, K_zusatz), aktiv

    hilfs = False
    try:
        u, R, aktiv_eff = _rechnen()
        system.freie_bewegungen()      # nur suchen - geloest ist geloest
    except RuntimeError as ex:
        # Statt abzubrechen: die freien Bewegungen benennen, festhalten und
        # weiterrechnen. Der Nutzer sieht dann die Verformung und daneben,
        # welche Last in der Bewegung ins Nichts geht - und entscheidet selbst.
        if not system.hilfsfesselung():
            _teilergebnis_anhaengen(model, system, res, ex, F, feq, q, temp, workers, aktiv)
            raise
        n_sg = len(system.singular)
        _melde(progress, f"{n_sg} freie Bewegung{'' if n_sg == 1 else 'en'} gefunden - "
               "wird mit Hilfsfesselung gerechnet")
        try:
            u, R, aktiv_eff = _rechnen()
        except RuntimeError as ex2:
            # Auch mit Hilfsfesselung kein Gleichgewicht: die Verformung der
            # letzten Iteration bleibt als Ergebnis "Abbruch" erhalten
            _teilergebnis_anhaengen(model, system, res, ex2, F, feq, q, temp, workers, aktiv)
            raise
        hilfs = True
    if _plastisch(model) and not probelauf:
        # Der Probelauf laesst die Plastizitaet aus: sie kostet je Schritt eine
        # volle Kontaktiteration, und der Fehlerschaetzer misst den Sprung der
        # Spannung zwischen Nachbarelementen - dafuer genuegt die elastische.
        try:
            u, R, aktiv_eff, temp = _plastizitaet_rechnen(model, res, F, _rechnen, aktiv, temp, progress, start)
        except RuntimeError as ex3:
            _teilergebnis_anhaengen(model, system, res, ex3, F, feq, q, temp, workers, aktiv)
            raise
    if hilfs:
        u = system.ohne_starrkoerper(u)
    if system.singular:
        from . import singular as _sg
        # Nach Schwere geordnet: oben steht, was die Rechnung zunichte macht,
        # nicht das erstbeste Teil nach Knotennummer.
        res.singular = _sg.wichtigste(_sg.auswerten(model, system.singular, F),
                                      hoechstens=len(system.singular))
        for x in res.singular:
            x.kegel = None            # ausgewertet - die Kegelmatrix kann weg
        res.info["singularitaeten"] = [singularitaet_info(x)
                                       for x in _sg.wichtigste(res.singular)]
    verschiebungen_eintragen(model, res, u, R)
    res.info.update({"ndof": model.ndof, "nfree": len(system.fi),
                     "solver": system.backend, "factors": dict(factors),
                     "nnz_matrix": int(getattr(system, "nnz_matrix", 0)),
                     "nnz_faktor": int(getattr(system, "nnz_faktor", 0)),
                     "zeit_faktorisierung": float(getattr(system, "zeit_faktorisierung", 0.0))})
    if probelauf:
        res.info["probelauf"] = True
    postprocess(model, u, res, feq, q, temp, workers, aktiv_eff)
    res.info["time"] = time.time() - t0 + system.t_assemble
    return res


def singularitaet_info(s) -> dict:
    """Eine freie Bewegung als einfaches Woerterbuch - fuer Bericht und Web.

    ``Results.singular`` haelt die Objekte fuer die Oberflaeche (sie braucht
    Richtung und Knoten, um den Pfeil zu zeichnen); hier steht dasselbe in
    Text und Zahlen, damit es auch durch ``to_dict`` und ueber die Farm kommt.
    """
    return {"art": s.art, "koerper": list(s.koerper), "text": s.text,
            "ursache": s.ursache, "befund": s.befund(), "kraft": float(s.kraft),
            "moment": float(s.moment), "gefesselt": bool(s.gefesselt),
            "knoten": len(s.knoten)}


def verschiebungen_eintragen(model: Model, res: Results, u: np.ndarray, R: np.ndarray) -> None:
    """u und R (ndof,) in die Ergebnisfelder (nn, 6) schreiben; die Woelb-FHG
    hinter den Knotenfreiheitsgraden landen in res.woelb."""
    n6 = model.nn * NDOF
    res.u = np.asarray(u[:n6], float).reshape(-1, NDOF)
    res.reactions = np.asarray(R[:n6], float).reshape(-1, NDOF)
    if len(u) > n6:
        res.woelb = {int(n): float(u[k]) for n, k in model.woelb_index().items()}


def _normalkraft(model: Model, e, u: np.ndarray) -> float:
    """Normalkraft (Zug positiv) eines Zug-/Druckstabs, Seils oder der
    Laengskraft einer Feder aus dem Verschiebungsvektor."""
    d = asm.element_dofs(e, model)[:12]
    X = model.nodes[e.nodes]
    if e.typ == "feder":
        from .elements import verbindung as vb
        fp = model.federn[e.sec]
        T3 = vb.feder_achsen(X[0], X[1], fp.achse, e.roll)
        return float(vb.feder_kraefte(fp.k, T3, u[d])[0])
    kl, T3, T, L = asm.beam_local(model, e)
    ul = T @ u[d]
    mat = model.materials[e.mat]
    sec = model.sections[e.sec]
    return float(mat.E * sec.A / L * (ul[6] - ul[0]))


def solve_with_ausfall(model: Model, system: StaticSystem, F: np.ndarray, us=None,
                       progress=None, max_iter: int = 50, uebermass: dict = None,
                       K_zusatz: sparse.spmatrix = None, probelauf: bool = False):
    """Aktivmengen-Iteration fuer Staebe, die nur Zug oder nur Druck aufnehmen
    (Fachwerkstab/Feder mit ``nur``, Seile).

    Gerechnet wird mit allen Staeben; wer die falsche Kraft traegt, wird
    herausgenommen (seine Steifigkeit wird als K_extra wieder abgezogen -
    das System muss nicht neu aufgestellt werden), und es wird neu geloest,
    bis sich die Menge nicht mehr aendert. Herausgenommene Staebe duerfen
    wieder hinein, wenn sie im naechsten Schritt die richtige Kraft
    truegen. Kontakt laeuft innen weiter mit.

    ``K_zusatz`` kommt in jedem Schritt dazu (die konsistente Tangente der
    Plastizitaet, plastizitaet._newton).

    Rueckgabe (u, R, aktiv, ausgefallen, log, kontakt) - kontakt = None oder
    (contact, contact_forces, info) aus der Kontaktiteration.
    """
    if probelauf:
        max_iter = 1            # siehe solve_with_contact: ein Schritt genuegt
    ne = len(model.elements)
    kand = [i for i, e in enumerate(model.elements)
            if (getattr(e, "nur", "") or e.typ == "seil")
            and (system.aktiv is None or system.aktiv[i])]
    Ke = {}
    for i in kand:
        e = model.elements[i]
        Ke[i] = (asm.element_dofs(e, model), np.asarray(asm.element_matrix(model, e), float))
    aus: set = set()
    log: list[str] = []
    n = model.ndof
    u = R = None
    kontakt = None
    for it in range(1, max_iter + 1):
        K_aus = K_zusatz
        if aus:
            rows, cols, vals = [], [], []
            for i in aus:
                d, K_e = Ke[i]
                r, c = np.meshgrid(d, d, indexing="ij")
                rows.append(r.ravel())
                cols.append(c.ravel())
                vals.append(-K_e.ravel())
            K_aus = sparse.coo_matrix(
                (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                shape=(n, n)).tocsr()
            if K_zusatz is not None:
                K_aus = (K_aus + K_zusatz).tocsr()
        if model.has_contact:
            u, R, cons, cf, cinfo = solve_with_contact(model, system, F, progress=progress,
                                                       uebermass=uebermass,
                                                       us=us, K_zusatz=K_aus,
                                                       probelauf=probelauf)
            kontakt = (cons, cf, cinfo)
        else:
            u = system.solve(F, K_extra=K_aus, us=us)
            R = system.reactions(u, F, K_aus)
        kraefte = {i: _normalkraft(model, model.elements[i], u) for i in kand}
        gross = max([abs(v) for v in kraefte.values()] + [1.0])
        tol = 1e-9 * gross
        neu = set()
        for i, N in kraefte.items():
            art = getattr(model.elements[i], "nur", "") or "zug"
            if (art == "zug" and N < -tol) or (art == "druck" and N > tol):
                neu.add(i)
        if progress:
            progress(f"Ausfall-Iteration {it}: {len(neu)} von {len(kand)} Stäben ausgefallen")
        if neu == aus:
            break
        aus = neu
    else:
        log.append(f"Ausfall-Iteration nach {max_iter} Schritten nicht konvergiert")
    if aus:
        log.append(f"{len(aus)} Stäbe tragen nicht (nur Zug/Druck): "
                   + ", ".join(str(i) for i in sorted(aus)[:12])
                   + (" …" if len(aus) > 12 else ""))
    aktiv = np.ones(ne, dtype=bool) if system.aktiv is None else np.asarray(system.aktiv, bool).copy()
    for i in aus:
        aktiv[i] = False
    return u, R, aktiv, sorted(int(i) for i in aus), log, kontakt


# ==========================================================================
# Situationen: je Situation ein eigenes System
# ==========================================================================
def situationssystem(model: Model, name: str = "", workers: int = None,
                     progress=None) -> tuple:
    """(Modell, StaticSystem) der Situation: Stellung angewandt, abgeschaltete
    Elemente weggelassen. Fuer die Grundstellung ist das Modell das Original."""
    from .situationen import situationsmodell
    m_s, aktiv, log = situationsmodell(model, name)
    if progress:
        for z in log:
            progress(z.strip())
    system = StaticSystem(m_s, workers, progress, aktiv=aktiv, situation=name or GRUNDSTELLUNG)
    return m_s, system


def systeme_je_situation(model: Model, namen=None, workers: int = None, progress=None,
                         systeme: dict = None) -> dict:
    """{Situation: (Modell, System)} fuer die Situationen der genannten
    Lastfaelle (alle, wenn keine genannt). ``systeme`` wird ergaenzt."""
    systeme = systeme if systeme is not None else {}
    for sit in model.lastfaelle_je_situation(namen):
        if sit not in systeme:
            systeme[sit] = situationssystem(model, sit, workers, progress)
    return systeme


def solve_static(model: Model, progress=None, case: str = None,
                 workers: int = None, system: StaticSystem = None,
                 probelauf: bool = False) -> Results:
    """Ein Lastfall (der aktive oder ``case``) - im stehenden Prozesspool
    (parallel.arbeiter); Einzelheiten in _solve_static_innen.

    ``probelauf=True`` rechnet **einen** Kontaktschritt aus dem Anfangszustand
    der Fugen und laesst die Plastizitaet aus. Das ist der Lauf fuer die
    adaptive Vernetzung (``adaptiv.adaptiv_vernetzen``): sie braucht den
    Spannungssprung zwischen Nachbarelementen als Netzmass, und der ist schon
    im ersten Schritt da. Ein voller Lastfall am Drehlager kostet 235 s mit 48
    Kontaktschritten (gemessen 19.09.2026); der Probelauf spart den Faktor der
    Iterationszahl. Das Ergebnis ist **kein Nachweis**: ``Results.info`` traegt
    ``probelauf: True``, und ``contact_converged`` steht auf falsch.
    """
    with parallel.arbeiter(model, workers):
        return _solve_static_innen(model, progress, case, workers, system, probelauf)


def _solve_static_innen(model: Model, progress=None, case: str = None,
                        workers: int = None, system: StaticSystem = None,
                        probelauf: bool = False) -> Results:
    """Ein Lastfall (default: aktiver Lastfall; case='all': alle Lastfaelle mit
    Faktor 1 ueberlagert)."""
    system = system or StaticSystem(model, workers, progress)
    if case == "all":
        factors = {k: 1.0 for k in model.load_cases}
        name = "alle Lastfaelle"
    else:
        lc = model.case(case)
        factors = {lc.name: 1.0}
        name = lc.name
    res = _solve_loads(model, system, factors, name, "case", workers, progress,
                       probelauf=probelauf)
    _melde(progress, "System gelöst", 1.0)
    return res


def _mit_referenzen_zuerst(names: list, referenzen: dict) -> list:
    """Jeder Referenzzustand unmittelbar vor den Zustaenden, die ihn
    einfrieren, danach die uebrigen Lastfaelle. Nur so bleibt die
    Faktorisierung seines Kontaktzustands im Speicher (StaticSystem behaelt
    eine): ein Lastfall dazwischen ersetzt sie, und der eingefrorene Zustand
    faktorisiert neu (gemessen am Block mit Reibung: 1 statt 0)."""
    folge = []
    for n in names:
        if n in referenzen.values() and n not in folge:
            folge.append(n)
            folge.extend(z for z in names if referenzen.get(z) == n and z not in folge)
    folge.extend(n for n in names if n not in folge)
    return folge


def solve_cases(model: Model, *args, **kwargs):
    """Mehrere Lastfaelle - im stehenden Prozesspool (parallel.arbeiter);
    Einzelheiten in _solve_cases_innen."""
    with parallel.arbeiter(model, kwargs.get("workers")):
        return _solve_cases_innen(model, *args, **kwargs)


def _solve_cases_innen(model: Model, cases: list = None, workers: int = None,
                       progress=None, system: StaticSystem = None, systeme: dict = None,
                referenzen: dict = None) -> dict:
    """Alle (oder ausgewaehlte) Lastfaelle loesen - je Situation mit ihrem
    System (eine Faktorisierung je Situation). Ein uebergebenes ``system``
    gilt fuer alle genannten Lastfaelle.

    ``referenzen`` {Zustand: Referenzzustand}: der Zustand wird mit dem
    eingefrorenen Kontaktzustand seiner Referenz linear geloest (Zustaende
    einer Ermuedungslast, siehe ermuedungsreferenzen)."""
    names = cases if cases is not None else list(model.load_cases)
    referenzen = dict(referenzen or {})
    if referenzen:
        names = _mit_referenzen_zuerst(list(names), referenzen)
    out = {}

    def _einfrieren(name):
        ref = referenzen.get(name)
        if ref and ref in out and out[ref].kontaktzustand is not None:
            return ref, out[ref].kontaktzustand
        return None, None
    # Warmstart: jeder Lastfall beginnt beim Kontaktzustand des vorigen
    # Lastfalls desselben Systems (Situation)
    # Mehrere Lastfaelle gleichzeitig? Nur ohne uebergebenes System (dann gilt
    # es fuer alle genannten Faelle) und ohne eingefrorene Zustaende (die
    # brauchen ihren Referenzzustand aus demselben Lauf).
    if system is None and not referenzen and len(names) > 1:
        k = ketten_zahl(len(names))
        if k > 1:
            fertig = _cases_in_ketten(model, names, k, progress)
            if fertig:
                return fertig
    # Jeder fertige Lastfall bleibt bestehen, auch wenn der naechste abbricht:
    # ``out`` haengt an der Ausnahme (siehe _teil_merken)
    try:
        if system is not None:
            start = None
            for k, name in enumerate(names):
                ref, einf = _einfrieren(name)
                n_ = max(1, len(names))
                out[name] = _solve_loads(model, system, {name: 1.0}, name, "case", workers,
                                         progress=progress, start=start, einfrieren=einf,
                                         fenster=(0.35 + 0.25 * k / n_, 0.35 + 0.25 * (k + 1) / n_))
                if einf is not None:
                    out[name].info["contact_frozen_from"] = ref
                start = out[name].kontaktzustand or start
                _melde(progress, f"Lastfall {name} ({k + 1}/{len(names)})",
                       0.35 + 0.25 * (k + 1) / n_)
            return out
        systeme = systeme_je_situation(model, names, workers, progress, systeme)
        k = 0
        for sit, sit_names in model.lastfaelle_je_situation(names).items():
            m_s, sys_s = systeme[sit]
            start = getattr(sys_s, "kontaktzustand", None)
            for name in _mit_referenzen_zuerst(list(sit_names), referenzen):
                ref, einf = _einfrieren(name)
                n_ = max(1, len(names))
                out[name] = _solve_loads(m_s, sys_s, {name: 1.0}, name, "case", workers,
                                         progress=progress, start=start, einfrieren=einf,
                                         fenster=(0.35 + 0.25 * k / n_, 0.35 + 0.25 * (k + 1) / n_))
                if einf is not None:
                    out[name].info["contact_frozen_from"] = ref
                start = out[name].kontaktzustand or start
                sys_s.kontaktzustand = start
                k += 1
                _melde(progress, f"Lastfall {name} ({k}/{len(names)})"
                       + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
                       0.35 + 0.25 * k / max(1, len(names)))
    except BaseException as ex:
        raise _teil_merken(ex, "teil_cases", out)
    return out


def ketten_zahl(n_faelle: int) -> int:
    """Wie viele Lastfaelle gleichzeitig laufen sollen.

    0 heisst "automatisch": so viele, wie der freie Speicher traegt, hoechstens
    aber so viele, wie Kerne da sind. Gemessen am Drehlager (20.09.2026)
    braucht eine Kette mit sechs Arbeitern rund 9,5 GB; davon bleibt ein
    Viertel als Reserve.
    """
    st = parallel.settings()
    k = getattr(st, "ketten", 1)
    k = 1 if k is None else int(k)     # 0 heisst automatisch, nicht "eine Kette"
    if k > 0:
        return max(1, min(k, n_faelle))
    frei = float(speicherlage().get("frei", 0.0) or 0.0)
    je_kette = 9.5                      # GB, gemessen: 6 Arbeiter + Matrix + Faktorisierung
    nach_speicher = int(max(1.0, 0.75 * frei / je_kette))
    return max(1, min(nach_speicher, st.workers, n_faelle))


def _ketten_teilen(model: Model, names: list, k: int) -> list:
    """Die Lastfaelle auf k Ketten verteilen - Situation fuer Situation
    zusammenhaengend, damit der Warmstart innerhalb der Kette greift (jede
    Situation hat ihr eigenes System)."""
    folge = [n for sit_names in model.lastfaelle_je_situation(names).values()
             for n in sit_names]
    k = max(1, min(int(k), len(folge)))
    gr = (len(folge) + k - 1) // k
    return [folge[i:i + gr] for i in range(0, len(folge), gr) if folge[i:i + gr]]


def _cases_in_ketten(model: Model, names: list, k: int, progress=None) -> dict:
    """Mehrere Lastfaelle gleichzeitig: je Kette ein Prozess, in sich warm.

    Gemessen am Drehlager (20.09.2026): ein warmer Lastfall braucht 235 s,
    davon 87 s Faktorisierung; der Rechner hatte dabei im Mittel 12 von 32
    Kernen belegt. Der Speicher ist die Grenze, nicht die Kernzahl - eine
    Kette mit vollem Pool belegt 36 GB, davon 32,7 GB die Arbeiter.
    """
    import pickle
    import tempfile
    from .parallel import Job, run_jobs
    bloecke = _ketten_teilen(model, names, k)
    if len(bloecke) <= 1:
        return {}
    st = parallel.settings()
    je = int(getattr(st, "ketten_arbeiter", 0) or 0) or max(2, st.workers // len(bloecke))
    threads = st.solver_threads or max(1, (parallel.cpu_count() - 1) // len(bloecke))
    _melde(progress, f"{len(names)} Lastfälle in {len(bloecke)} Ketten "
                     f"({je} Arbeiter und {threads} Löser-Threads je Kette)")
    pfad = None
    if st.backend != "farm":
        fd, pfad = tempfile.mkstemp(prefix="statik3d_kette_", suffix=".pkl")
        os.close(fd)
        with open(pfad, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    try:
        d = model.to_dict() if pfad is None else None
        jobs = [Job("solve_kette",
                    {"pfad": pfad or "", "model": d, "cases": b,
                     "arbeiter": je, "loeser_threads": threads},
                    label=f"{b[0]}…{b[-1]}")
                for b in bloecke]
        fertig = run_jobs(jobs, workers=len(bloecke),
                          progress=(lambda a, b_: _melde(progress, f"Kette {a}/{b_} fertig"))
                          if progress else None)
    finally:
        if pfad:
            try:
                os.remove(pfad)
            except OSError:
                pass
    out: dict = {}
    for job, r in zip(jobs, fertig):
        if not r.ok:
            raise RuntimeError(f"Kette {job.label}: {r.error}")
        for n, res in (r.result or {}).items():
            res.model = model
            out[n] = res
    return {n: out[n] for n in names if n in out}


def _kombination_pruefen(model: Model, combo: Combination) -> str:
    """Die Situation der Kombination; ihre Lastfaelle muessen dazu gehoeren."""
    sit = combo.situation or GRUNDSTELLUNG
    fremd = [k for k in combo.lastfaelle() if k in model.load_cases
             and (model.load_cases[k].situation or GRUNDSTELLUNG) != sit]
    if fremd:
        raise ValueError(f"Kombination '{combo.name}' (Situation {sit}) enthält Lastfall "
                         f"{', '.join(fremd)} aus einer anderen Situation")
    return sit


def solve_combination(model: Model, combo: Combination, case_results: dict = None,
                      system: StaticSystem = None, workers: int = None,
                      progress=None, systeme: dict = None, start=None) -> Results:
    """Eine Kombination: Superposition (linear) oder direkte Loesung (Kontakt) -
    in der Situation der Kombination."""
    sit = _kombination_pruefen(model, combo)
    if not _nichtlinear(model) and case_results is not None \
            and all(k in case_results for k, f in combo.factors.items() if f):
        teile = [(case_results[k], f) for k, f in combo.factors.items() if f]
        basis = next((r.model for r, _f in teile if getattr(r, "model", None) is not None), model)
        res = Results.combine(basis, teile, combo.name)
        res.info["typ"] = combo.typ
        if sit != GRUNDSTELLUNG:
            res.info["situation"] = sit
        if teile and "inaktiv" in teile[0][0].info:
            res.info["inaktiv"] = list(teile[0][0].info["inaktiv"])
        return res
    if system is None:
        if systeme is not None and sit in systeme:
            model, system = systeme[sit]
        elif sit != GRUNDSTELLUNG or model.situation(sit).deaktiviert:
            model, system = situationssystem(model, sit, workers, progress)
        else:
            system = StaticSystem(model, workers, progress)
    if start is None:
        start = getattr(system, "kontaktzustand", None)
    res = _solve_loads(model, system, combo.factors, combo.name, "combination", workers,
                       progress, start=start)
    if res.kontaktzustand is not None:
        system.kontaktzustand = res.kontaktzustand
    res.info["typ"] = combo.typ
    return res


def umhuellende_der_kombination(model: Model, combo: Combination, case_results: dict,
                                systeme: dict = None, workers: int = None,
                                progress=None) -> tuple:
    """Die Umhuellende einer Kombination mit Alternativen - Rueckgabe
    (Envelope, Zahl der zusaetzlich geloesten Alternativen).

    Eine Alternative aus genau einem Lastfall mit Faktor 1 **ist** dessen
    Lastfallergebnis: es wird wiederverwendet, nichts neu geloest. Am
    Drehlager sind das alle 720 Eintraege der 52 Ergebniskombinationen. Jede
    andere Alternative wird als voruebergehende Kombination gerechnet
    (Ueberlagerung; im Kontaktmodell direkte Loesung) und nach dem Einfalten
    verworfen - der Speicher haengt nicht von der Zahl der Alternativen ab.
    """
    from dataclasses import replace
    sit = _kombination_pruefen(model, combo)
    env = Envelope(model, {}, combo.name)
    geloest = 0
    for k, alt in enumerate(combo.alternativen, 1):
        teile = {a: f for a, f in alt.items() if f}
        if not teile:
            continue
        lc = next(iter(teile))
        if len(teile) == 1 and abs(teile[lc] - 1.0) < 1e-12 and case_results \
                and lc in case_results:
            env.aufnehmen(lc, case_results[lc])
        else:
            name = f"{combo.name} [{k}]"
            zwischen = replace(combo, name=name, factors=teile, alternativen=[])
            res = solve_combination(model, zwischen, case_results, workers=workers,
                                    systeme=systeme)
            env.aufnehmen(name, res)
            geloest += 1
        _melde(progress, f"Umhüllende {combo.name}: {k}/{len(combo.alternativen)}"
               + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
               0.60 + 0.30 * k / max(1, len(combo.alternativen)))
    return env, geloest


def _teil_merken(ex, name: str, wert: dict):
    """Das bisher Gerechnete an die Ausnahme haengen, die gerade nach oben
    laeuft - das erste Ergebnis gewinnt.

    Ein Abbruch faellt als Ausnahme aus dem Fortschrittsaufruf heraus
    (gui.worker.Abgebrochen) und raeumt dabei jeden Aufrufrahmen ab. Ohne
    diesen Anhang waere alles verloren, was bis dahin gerechnet war: der
    Anwender startete am 19.09.2026 versehentlich alle Lastfaelle und
    Kombinationen, brach nach dem ersten Lastfall ab - und stand wieder ohne
    Ergebnis da, obwohl der Lastfall fertig gerechnet war.
    """
    try:
        if getattr(ex, name, None) is None and wert:
            setattr(ex, name, dict(wert))
    except Exception:              # noqa: BLE001 - das Retten darf nie selbst scheitern
        pass
    return ex


def solve_combinations(model: Model, combos: list = None, case_results: dict = None,
                       system: StaticSystem = None, workers: int = None,
                       progress=None, use_jobs: bool = None, systeme: dict = None) -> dict:
    """Alle Kombinationen. Bei Kontakt (nichtlinear) werden die Kombinationen
    als Auftraege parallel bzw. auf der Farm gerechnet."""
    names = combos if combos is not None else list(model.combinations)
    # Kombinationen mit Alternativen sind Umhuellende - die bildet solve_all
    # (umhuellende_der_kombination), nicht ein einzelnes Ergebnis.
    names = [n for n in names if not model.combinations[n].ist_umhuellende]
    out = {}
    if not names:
        return out
    if not _nichtlinear(model):
        if case_results is None:
            case_results = solve_cases(model, workers=workers, progress=progress,
                                       system=system, systeme=systeme)
        try:
            for k, n in enumerate(names):
                out[n] = solve_combination(model, model.combinations[n], case_results,
                                           systeme=systeme)
                # Auch der lineare Weg meldet sich: er ueberlagert nur, aber
                # bei 422 Kombinationen stand der Balken sonst minutenlang
                # still, und ein Abbruch hatte hier keinen Haltepunkt
                # (19.09.2026)
                _melde(progress, f"Kombination {n} ({k + 1}/{len(names)})",
                       0.60 + 0.30 * (k + 1) / max(1, len(names)))
        except BaseException as ex:
            raise _teil_merken(ex, "teil_combinations", out)
        return out
    # nichtlinear: Auftraege
    st = parallel.settings()
    if use_jobs is None:
        use_jobs = (st.backend == "farm") or (st.workers > 1 and len(names) > 1)
    if use_jobs:
        from .parallel import Job, run_jobs
        jobs = [Job("solve_combination", {"model": model.to_dict(), "combination": n},
                    label=n) for n in names]
        results = run_jobs(jobs, workers=workers,
                           progress=(lambda a, b: progress(f"Kombination {a}/{b}"))
                           if progress else None)
        for n, r in zip(names, results):
            if not r.ok:
                raise RuntimeError(f"Kombination {n}: {r.error}")
            res = r.result
            res.model = model
            out[n] = res
        return out
    try:
        for k, n in enumerate(names):
            out[n] = solve_combination(model, model.combinations[n], None, system, workers,
                                       systeme=systeme)
            if progress:
                _melde(progress, f"Kombination {n} ({k + 1}/{len(names)})",
                       0.60 + 0.30 * (k + 1) / max(1, len(names)))
    except BaseException as ex:
        raise _teil_merken(ex, "teil_combinations", out)
    return out


# ==========================================================================
# Kontakt-Iteration
# ==========================================================================
class KontaktAbbruch(RuntimeError):
    """Die Kontakt-Iteration fand kein Gleichgewicht - mit dem, was bis dahin
    vorlag: der Verschiebung der letzten geloesten Iteration (``u``), ihrer
    Nummer, dem Kontaktzustand dieses Schritts und den Teilen, deren
    Bedingungen zuletzt alle offen waren (16.09.2026: "die Verformung der
    letzten Iteration anzeigen, damit der Anwender pruefen kann, woran der
    Abbruch lag - und Zeiger auf die Teile, die ihn verursacht haben").
    ``teilergebnis`` haengt _solve_loads an: das Results-Objekt dazu."""

    def __init__(self, text: str, u=None, iteration: int = 0, kontakt=None, abgehoben=None, log=None):
        super().__init__(text)
        self.log = list(log or [])
        self.u = u
        self.iteration = int(iteration)
        self.kontakt = list(kontakt or [])
        self.abgehoben = list(abgehoben or [])
        self.teilergebnis = None


def _teile_bedingungen(model, cs) -> list:
    """[(Name, Knotenmenge, Bedingungen)] je Teil mit Kontakt. Teile sind die
    Volumenkoerper; was keinem gehoert, zaehlt nach zusammenhaengenden
    Teiltragwerken. Eine Bedingung gehoert zum Teil ihres Slave-Knotens
    **und** zu dem ihrer Master-Knoten - ein Stift, auf den nur die Bohrung
    drueckt, hat sonst keine einzige (17.09.2026)."""
    from .diagnose import teiltragwerke
    if not cs.cons:
        return []
    ne = len(model.elements)
    teile, belegt = [], set()
    for name, k in (getattr(model, "koerper", None) or {}).items():
        kn = {int(n) for e in (k.elemente or []) if 0 <= int(e) < ne
              for n in model.elements[int(e)].nodes}
        if kn:
            teile.append((name, kn))
            belegt |= kn
    try:
        for i, grp in enumerate(teiltragwerke(model), 1):
            kn = {int(n) for n in grp} - belegt
            if kn:
                teile.append((f"Teil {i}", kn))
    except Exception:                 # noqa: BLE001 - eine Diagnose darf nie sperren
        pass
    teil_von: dict = {}
    for j, (_name, kn) in enumerate(teile):
        for n in kn:
            teil_von.setdefault(n, j)
    cons_je: list = [[] for _ in teile]
    for c in cs.cons:
        js = set()
        j = teil_von.get(int(c.node))
        if j is not None:
            js.add(j)
        if c.master:
            for n in c.master[0]:
                j = teil_von.get(int(n))
                if j is not None:
                    js.add(j)
        for j in js:
            cons_je[j].append(c)
    return [(name, kn, cons) for (name, kn), cons in zip(teile, cons_je) if cons]


def _teile_mit_kontakt(model, cs) -> list:
    """[(Name, Knotenmenge, Zahl der Bedingungen, davon aktiv, Fugen)] je Teil
    mit Kontaktbedingungen (siehe :func:`_teile_bedingungen`)."""
    out = []
    for name, kn, cons in _teile_bedingungen(model, cs):
        aktiv = sum(1 for c in cons if c.active)
        fugen = sorted({(c.label or "").split(":")[0] for c in cons if c.label})
        out.append((name, kn, len(cons), aktiv, fugen))
    return out


#: So viele Bedingungen behaelt ein Teil mindestens geschlossen, wenn die
#: Kontakt-Iteration es sonst frei liesse (drei Punkte, mit Haften oder
#: Reibung ein Halt in allen sechs Freiheitsgraden)
HALT_MINDESTENS = 3

#: Ab welchem Verhaeltnis (kleinster zu groesstem Singulaerwert der
#: Tangentialzeilen auf den sechs Starrkoerperbewegungen) der Schub ein Teil
#: traegt. Gemessen am Drehlager (19.09.2026): die Stifte in ihren Bohrungen
#: liegen bei 0,536 bis 0,707, eine ebene Fuge bei 0 - dazwischen liegen
#: Groessenordnungen, die Schwelle liegt weit von beiden Seiten entfernt.
SCHUB_GRENZE = 1e-3


def _schub_traegt(model, knoten, bindend) -> float:
    """Wie fest die Schubbindung allein die sechs Starrkoerperbewegungen des
    Teils haelt: Verhaeltnis kleinster zu groesstem Singulaerwert der
    Tangentialzeilen. 0 heisst, sie haelt es nicht.

    Die Frage laesst sich nicht an der Art der Bedingung entscheiden, sondern
    nur an der Geometrie der Fuge: eine ebene Fuge mit Reibung haelt quer zu
    ihrer Ebene nichts (der hochgezogene Block, tests/test_kontakthalt), eine
    Bohrung fasst den Stift dagegen rundum. Gerechnet wird darum, nicht
    geraten."""
    X = np.asarray(getattr(model, "nodes", ()), float)
    kn = np.array(sorted(int(n) for n in knoten if int(n) < len(X)), dtype=np.int64)
    if len(kn) == 0 or not bindend:
        return 0.0
    o = X[kn].mean(axis=0)
    L = float(np.abs(X[kn] - o).max()) or 1.0
    idx = {int(n): i for i, n in enumerate(kn)}
    P = np.zeros((len(kn), NDOF, 6))
    r = X[kn] - o
    for k in range(3):
        e = np.zeros(3)
        e[k] = 1.0
        P[:, k, k] = 1.0
        P[:, 0:3, 3 + k] = np.cross(np.tile(e, (len(r), 1)), r) / L
        if NDOF > 3:
            P[:, 3 + k, 3 + k] = 1.0 / L
    A = np.zeros((2 * len(bindend), 6))
    for i, c in enumerate(bindend):
        ct = np.asarray(c.ct, float).reshape(2, -1)
        for j, dd in enumerate(np.asarray(c.dofs, dtype=np.int64)):
            z = idx.get(int(dd) // NDOF)
            if z is None:
                continue
            p = P[z, int(dd) % NDOF]
            A[2 * i] += ct[0, j] * p
            A[2 * i + 1] += ct[1, j] * p
    s = np.linalg.svd(A, compute_uv=False)
    s6 = np.zeros(6)
    s6[:len(s)] = s
    return float(s6.min() / s6.max()) if s6.max() > 0.0 else 0.0


def _freie_teile_halten(model, cs, log: list = None, mindestens: int = HALT_MINDESTENS,
                        stufe: int = 1) -> bool:
    """Teile, die in der Kontakt-Iteration (fast) alle Bedingungen verloren
    haben, an ihren am wenigsten offenen Bedingungen halten.

    Am Drehlager (17.09.2026, Protokoll 07:56) pendelte die Zahl der aktiven
    Bedingungen 18 Schritte lang um 13 000, bis in Schritt 27 Passstifte
    keine geschlossene Bedingung mehr hatten: das Gleichungssystem war
    wirklich singulaer (Residuum 1,1e-3), die Verformung des Schritts davor
    dagegen unauffaellig. Ein Stift in einer Bohrung beruehrt sie immer
    irgendwo - dass alle seine Bedingungen offen sind, ist die Linearisierung
    des Schritts, nicht die Physik.

    **Wie gehalten wird, entscheidet die Form der Fuge** (19.09.2026). Traegt
    die Schubbindung das Teil allein - :func:`_schub_traegt` ueber
    ``SCHUB_GRENZE`` -, dann wird tangential gehalten: ``schub_halt`` auf
    *allen* bindenden Bedingungen, keine davon geschlossen. So entsteht keine
    Normalkraft und damit kein Zug. Am Drehlager halten die Normalrichtungen
    der zehn gemeldeten Stifte allein 2,2e-13 bis 3,6e-13 ihrer
    Starrkoerperbewegungen - also nichts -, der Schub aller Bedingungen
    dagegen 0,536 bis 0,707; der Schub aus nur drei Bedingungen kommt auf
    2,3e-18, hielte sie also ebenfalls nicht. Darum alle.

    Traegt der Schub nicht - eine ebene Fuge haelt quer zu ihrer Ebene nichts,
    auch mit Reibung -, bleiben je Teil ``mindestens`` Bedingungen
    geschlossen, und zwar die mit dem kleinsten Spalt; sie zaehlen als Wechsel
    (nach acht Wechseln friert die Bedingung ohnehin geschlossen ein), und das
    Protokoll nennt jedes gehaltene Teil.

    Reicht das nicht (der nach oben gezogene Block haelt mit fuenf Punkten
    auf einer Kante und kippt trotzdem), nimmt ``stufe`` 2 jedes Teil mit
    mehrheitlich offenen Bedingungen und haelt es bis zur Haelfte - die
    Haelfte mit dem kleinsten Spalt, also die Seite, auf die es sich
    zubewegt.

    Rueckgabe True, wenn etwas gehalten wurde - der Aufrufer loest dann
    denselben Schritt noch einmal.
    """
    gehalten, geschoben = [], []
    for name, _kn, cons in _teile_bedingungen(model, cs):
        soll = min(int(mindestens), len(cons)) if stufe == 1 else (len(cons) + 1) // 2
        aktiv = [c for c in cons if c.active]
        if len(aktiv) >= soll:
            continue
        bindend = [c for c in cons if c.ct is not None and (c.haften or float(c.mu) > 0.0)]
        if bindend and _schub_traegt(model, _kn, bindend) > SCHUB_GRENZE:
            # Der Halt eines Stiftes ist seine Schubbindung, nicht der Druck:
            # am Drehlager halten die Normalrichtungen allein 2,2e-13 bis
            # 3,6e-13 der Starrkoerperbewegungen, der Schub *aller* Bedingungen
            # 0,536 bis 0,707 - der Schub aus dreien dagegen 2,3e-18, also gar
            # nichts (19.09.2026, V70 und V96). Darum alle, und darum
            # tangential: eine geschlossene Normalbedingung braechte den
            # Lastanteil -kn*g0*cn mit, und der zieht.
            neu = [c for c in bindend if not c.schub_halt]
            for c in neu:
                c.schub_halt = True
            if neu:
                geschoben.append((name, len(cons), len(bindend)))
            continue
        offen = sorted((c for c in cons if not c.active), key=lambda c: float(c.g))
        nimm = offen[:soll - len(aktiv)]
        for c in nimm:
            c.active = True
            c.gehalten = True
            c.toggles += 1
            c.Fn = 0.0
            if c.toggles > 8:
                c.frozen = True
        if nimm:
            gehalten.append((name, len(cons), len(aktiv), len(nimm), max(float(c.g) for c in nimm)))
    if log is not None:
        if geschoben:
            log.append("Schubhalt für Teile ohne geschlossene Bedingung: "
                       + "; ".join(f"{n}: {b} von {z} Bedingungen tragen Schub"
                                   for n, z, b in geschoben[:8])
                       + (" …" if len(geschoben) > 8 else ""))
        if gehalten:
            log.append(("Halt für Teile ohne geschlossene Bedingung: " if stufe == 1
                        else "Halt für Teile mit mehrheitlich offenen Bedingungen: ")
                       + "; ".join(f"{n}: {a} von {z} zu, {h} mit dem kleinsten Spalt (bis {g * 1e3:.3f} mm) "
                                   "gehalten" for n, z, a, h, g in gehalten[:8])
                       + (" …" if len(gehalten) > 8 else ""))
    return bool(gehalten or geschoben)


#: Ab welchem Anteil seiner eigenen Druckkraft ein Teil, das an gehaltenen
#: Punkten zieht, als abhebend gilt (19.09.2026). Darunter ist der Zug der
#: Rest der Aktivmengen-Iteration: am Drehlager 20 kN gegen 15 232 kN
#: Vorspannung, also 0,13 %.
ZUG_ANTEIL = 0.05


def _gehaltene_unter_zug(model, cs) -> list:
    """Teile, deren gehaltene Bedingungen am Ende Zug tragen: [(Name,
    Knotenmenge, Zahl der gehaltenen Bedingungen, Zugkraft [N], Bedingungen)].

    Der Halt ist fuer den Schritt gedacht, nicht fuer das Ergebnis: haengt ein
    Teil zum Schluss an gehaltenen Punkten und zieht daran, hebt es wirklich
    ab - ein Block, der nach oben gezogen wird, hat kein Gleichgewicht ohne
    Zugfuge. Die Zugkraft ist kn * g je gehaltener, offen stehender Bedingung
    (die Feder der Straffeder-Formulierung, nicht die auf null gekappte Fn).

    **Gemessen wird am Teil selbst**, nicht an der groessten Knotenlast: ein
    Bauteil, das ueber seine Fugen Meganewton an Druck abtraegt, hebt nicht
    ab, weil an ein paar gehaltenen Punkten einige Kilonewton ziehen - das
    ist der Rest der Aktivmengen-Iteration. Am Drehlager (19.09.2026) brach
    die Rechnung deswegen ab: gemeldet waren 0,7 bis 20 kN Zug, waehrend
    allein die Schraubenvorspannung 15 232 kN betrug (16 Zugstaebe mit je
    952 kN aus dT = -445,6 K) und die groesste Kontaktkraft bei 217,6 kN lag.
    Die alte Schranke - ein Tausendstel der groessten Knotenlast - traf damit
    schon bei 1 kN zu. Jetzt gilt ein Teil als abhebend, wenn der Zug
    ``ZUG_ANTEIL`` seiner eigenen Druckkraft ueberschreitet; ein Teil ohne
    Druck (der hochgezogene Block) faellt weiter darunter."""
    out = []
    grenze = 1e-3 * float(getattr(cs, "f_ref", 1.0) or 1.0)
    for name, kn, cons in _teile_bedingungen(model, cs):
        geh = [c for c in cons if getattr(c, "gehalten", False) and c.active]
        if not geh:
            continue
        zug = sum(max(0.0, float(c.kn) * float(c.g)) for c in geh)
        # Was dasselbe Teil an Druck abtraegt (Fn ist die Normalkraft nach der
        # letzten Iteration, Druck positiv)
        druck = sum(max(0.0, float(getattr(c, "Fn", 0.0) or 0.0))
                    for c in cons if c.active and not getattr(c, "gehalten", False))
        if zug > max(grenze, ZUG_ANTEIL * druck):
            out.append((name, kn, len(geh), zug, cons))
    return out


def _kontakt_abbruch(it: int, ex, cs, model, u, zug: list = None, log: list = None) -> KontaktAbbruch:
    """Die Ausnahme zum singulaeren Schritt ``it`` - mit der Loesung des
    Schritts davor und den Teilen, die in diesem Schritt keine geschlossene
    Bedingung mehr hatten."""
    text = _contact_singular(it, ex, cs, model)
    if u is None:
        return KontaktAbbruch(text, iteration=0, log=log)
    abgehoben = []
    try:
        n6 = model.nn * NDOF
        U = np.asarray(u[:n6], float).reshape(-1, NDOF)[:, :3]
        teile = []
        for name, kn, n, aktiv, fugen in _teile_mit_kontakt(model, cs):
            idx = np.fromiter(kn, int, len(kn))
            teile.append((name, idx, n, aktiv, fugen, U[idx].mean(axis=0),
                          float(np.linalg.norm(U[idx], axis=1).mean())))
        betraege = np.array([x[6] for x in teile], float)
        for k, (name, idx, n, aktiv, fugen, mittel, betrag) in enumerate(teile):
            # Ein Teil ist frei, wenn keine seiner Bedingungen mehr haelt - oder
            # wenn die Mehrheit offen ist und es sich um ein Vielfaches dessen
            # bewegt, was die uebrigen Teile tun (der Block, der auf drei
            # Knoten kippt, statt glatt abzuheben). Mass ist das 90. Perzentil
            # der uebrigen, nicht der Median: am Drehlager (17.09.2026) bewegte
            # sich die ganze Lagerbock-Baugruppe (V15, V31, V33, V34, V35) um
            # 0,9 mm gegen 0,07 mm Median - die normale Verformung unter der
            # Last, kein Abheben; gegen ihresgleichen faellt keines auf.
            rest = np.delete(betraege, k)
            mass = float(np.percentile(rest, 90)) if len(rest) else 0.0
            los = aktiv == 0 or (aktiv < n / 2 and betrag > 1e-9 and betrag >= 5.0 * mass)
            if los:
                abgehoben.append({"name": name, "knoten": idx, "n": n, "aktiv": aktiv, "fugen": fugen,
                                  "u": mittel, "betrag": betrag, "mass": mass})
        # Teile, die an gehaltenen Punkten ziehen: sie heben wirklich ab
        genannt = {a["name"] for a in abgehoben}
        for name, kn, n_geh, kraft, cons in (zug or []):
            if name in genannt:
                continue
            idx = np.fromiter(kn, int, len(kn))
            abgehoben.append({"name": name, "knoten": idx, "n": len(cons),
                              "aktiv": sum(1 for c in cons if c.active),
                              "fugen": sorted({(c.label or "").split(":")[0] for c in cons if c.label}),
                              "u": U[idx].mean(axis=0), "betrag": float(np.linalg.norm(U[idx], axis=1).mean()),
                              "mass": 0.0, "gehalten": int(n_geh), "zug": float(kraft)})
    except Exception:                 # noqa: BLE001 - die Diagnose darf den Abbruch nicht verschlucken
        abgehoben = []
    try:
        kontakt = cs.results()
    except Exception:                 # noqa: BLE001
        kontakt = []
    return KontaktAbbruch(text, u=np.array(u, float), iteration=it - 1, kontakt=kontakt, log=log,
                          abgehoben=abgehoben)


def _teilergebnis_anhaengen(model, system, res, ex, F, feq=None, q=None, temp=None,
                            workers=None, aktiv=None) -> None:
    """Nach einem Abbruch der Kontakt-Iteration: die Verschiebung der letzten
    geloesten Iteration als Ergebnis an die Ausnahme haengen - samt den
    Teilen, deren Kontaktbedingungen zuletzt alle offen waren, als freie
    Bewegungen mit Pfeil. Die Oberflaeche zeigt es mit dem Zusatz "Abbruch":
    man sieht, was sich wohin bewegt, statt nur eine Meldung zu lesen.
    Auflagerkraefte gibt es nicht (kein Gleichgewicht); Element- und
    Spannungsergebnisse werden zur letzten Verschiebung nachgerechnet."""
    u = getattr(ex, "u", None)
    if u is None or getattr(ex, "teilergebnis", None) is not None:
        return
    from . import singular as _sg
    try:
        u = system.ohne_starrkoerper(np.asarray(u, float))
        verschiebungen_eintragen(model, res, u, np.zeros_like(u))
        res.contact = list(getattr(ex, "kontakt", None) or [])
        res.info.update({"abbruch": str(ex).splitlines()[0], "abbruch_iteration": int(ex.iteration),
                         "contact_iterations": int(ex.iteration), "contact_converged": False,
                         "contact_log": list(getattr(ex, "log", None) or []),
                         "ndof": model.ndof, "nfree": len(system.fi), "solver": system.backend})
        sing = list(_sg.auswerten(model, list(system.singular or []), F))
        n6 = model.nn * NDOF
        K = np.asarray(F, float).ravel()[:n6].reshape(-1, NDOF)[:, :3] if F is not None else None
        for teil in getattr(ex, "abgehoben", None) or []:
            kn = np.asarray(teil["knoten"], int)
            if not len(kn):
                continue
            mitte, L = _sg._mitte_und_laenge(model.nodes[kn])
            v = np.asarray(teil["u"], float)
            nv = float(np.linalg.norm(v))
            richtung = v / nv if nv > 0 else np.zeros(3)
            kraft = abs(float(K[kn].sum(axis=0) @ richtung)) if K is not None and nv > 0 else 0.0
            fug = ", ".join(teil["fugen"][:3]) + (" …" if len(teil["fugen"]) > 3 else "")
            wohin = (f" - Verschiebung längs ({richtung[0]:.2f}, {richtung[1]:.2f}, {richtung[2]:.2f})"
                     if nv > 0 else "")
            n_akt = int(teil.get("aktiv", 0))     # nicht "aktiv": das ist der Lastvektor fuer postprocess
            if teil.get("zug"):
                wort = "hebt ab"
                lage = (f"hängt nach Kontakt-Iteration {ex.iteration} an {teil.get('gehalten', 0)} gehaltenen "
                        f"Punkten unter {teil['zug'] / 1e3:.1f} kN Zug - ohne Zugfuge kein Gleichgewicht")
            elif n_akt == 0:
                wort = "hebt ab"
                lage = (f"in Kontakt-Iteration {ex.iteration + 1} war keine seiner {teil['n']} "
                        f"Kontaktbedingungen mehr geschlossen")
            else:
                wort = "verliert den Halt"
                lage = (f"in Kontakt-Iteration {ex.iteration + 1} hielten nur noch {n_akt} von {teil['n']} "
                        f"Kontaktbedingungen, und es bewegte sich um {teil.get('betrag', 0.0) * 1e3:.3g} mm "
                        f"(die übrigen Teile bis {teil.get('mass', 0.0) * 1e3:.3g} mm)")
            sing.append(_sg.Singularitaet(
                art="hebt ab", knoten=[int(i) for i in kn], koerper=[teil["name"]],
                t=richtung, omega=np.zeros(3), bezug=mitte, mitte=mitte, laenge=L,
                fugen=list(teil["fugen"]), kraft=kraft,
                text=f"{teil['name']} {wort}: {lage}{wohin}",
                ursache=(f"Das Teil hängt nur an Fugen ohne Zug ({fug}); öffnen sie alle, hält "
                         "es nichts mehr. Die Verformung der letzten Iteration zeigt, wohin es geht - "
                         "Abhilfe: Verbund oder Vorspannung an der Fuge, ein Lager, oder die Last "
                         "in die Fuge drücken lassen.")))
        res.singular = _sg.wichtigste(sing, hoechstens=max(1, len(sing)))
        for x in res.singular:
            x.kegel = None
        res.info["singularitaeten"] = [singularitaet_info(x) for x in _sg.wichtigste(res.singular)]
        if feq is not None:
            try:
                postprocess(model, u, res, feq, q, temp, workers, aktiv)
            except Exception as ex3:      # noqa: BLE001 - Spannungen sind Zugabe, die Verformung zaehlt
                res.info["abbruch_nachlauf"] = str(ex3)
    except Exception as ex2:              # noqa: BLE001 - das Teilergebnis darf den Abbruch nicht verschlucken
        res.info["abbruch_teilergebnis_fehler"] = str(ex2)
    ex.teilergebnis = res


def _contact_singular(it: int, ex, cs, model=None) -> str:
    """Meldung zu einem singulaeren Schritt der Kontakt-Iteration.

    Der Hinweis richtet sich nach der Zahl der **offenen** Bedingungen. Sind
    null offen, ist jede Fuge geschlossen - dann kann nichts abheben, und die
    Bewegung liegt in der Fugenebene. Frueher stand hier in beiden Faellen
    derselbe Satz „vermutlich hebt ein Bauteil ab", auch bei null offenen
    Bedingungen; das widerspricht sich selbst.
    """
    n_zu = sum(1 for c in cs.cons if c.active)
    n_open = len(cs.cons) - n_zu
    if n_open:
        hinweis = (f"{n_open} von {len(cs.cons)} Kontaktbedingungen sind offen - "
                   "ein Bauteil hebt ab oder rutscht ohne Halt.")
    elif cs.cons:
        hinweis = (f"alle {len(cs.cons)} Kontaktbedingungen sind geschlossen - "
                   "abheben kann hier nichts. Die Bewegung liegt damit **in** "
                   "der Fugenebene: das Bauteil gleitet, oder die Fuge haelt "
                   "quer zu sich nichts.")
    else:
        hinweis = "es gibt keine Kontaktbedingungen - die Ursache liegt nicht am Kontakt."
    text = f"Kontakt-Iteration {it}: {ex}\nHinweis: {hinweis}"
    if model is not None and "Teiltragwerk" not in str(ex) and "ohne Netz" not in str(ex):
        from .diagnose import meldungen
        befund = [z for z in meldungen(model) if not z.startswith("Hinweis")]
        if befund:
            text += "\n" + "\n".join(befund)
    return text


def _kontaktsystem(system: StaticSystem, model: Model, uebermass, log: list):
    """Das Kontaktsystem des Modells - einmal gebaut, dann wiederverwendet.

    Der geometrische Teil haengt weder an der Last noch am Verformungszustand:
    welcher Slave-Knoten auf welche Master-Facette faellt, die Normalen, die
    Flaechenquadriken, die Suchbaeume. Gebaut wurde er trotzdem bei jedem
    Aufruf neu - mit Plastizitaet also einmal je Schritt.

    Gemessen am Drehlager (LF3 warm, 12 Kontaktfugen, 18 Plastizitaets-
    schritte, cProfile 20.09.2026): **276 Aufrufe** von contact._build_pair,
    172 s von 542 s - ein Drittel des Lastfalls fuer 23-mal dasselbe
    Ergebnis. 276 / 12 Fugen = 23 Aufbauten. Darin allein 2,5 Mio. Aufrufe
    von numpy.cross zu 96 s.

    Gehalten wird es am ``StaticSystem``: das gehoert zur Situation und lebt
    genau so lange wie das Netz, aus dem es aufgebaut ist. Der Schluessel ist
    das Uebermass, denn das geht in ``g0`` jeder Bedingung ein (Vorspannung
    je Fuge, kann sich von Lastfall zu Lastfall aendern). Den Zustand setzt
    ``initialize()`` bei jedem Aufruf zurueck; die Meldungen des Aufbaus
    werden wiederholt, damit im Protokoll jedes Lastfalls dasselbe steht wie
    zuvor.
    """
    from .contact import ContactSystem
    schluessel = tuple(sorted((str(k), float(v)) for k, v in (uebermass or {}).items() if v))
    cs = getattr(system, "_kontaktsystem", None)
    if cs is not None and getattr(system, "_kontaktsystem_schluessel", None) == schluessel \
            and cs.model is model:
        cs.log = log
        log.extend(getattr(cs, "_baulog", ()))
        return cs
    cs = ContactSystem(model, system.K, log, uebermass)
    cs._baulog = list(log)
    system._kontaktsystem = cs
    system._kontaktsystem_schluessel = schluessel
    return cs


def solve_with_contact(model: Model, system: StaticSystem, F: np.ndarray,
                       max_iter: int = 120, progress=None, us: np.ndarray = None,
                       K_zusatz: sparse.spmatrix = None, uebermass: dict = None,
                       start=None, versuch: int = 0, einfrieren=None, fenster=None,
                       probelauf: bool = False):
    """Kontakt-Iteration; ``K_zusatz`` (z. B. die abgezogene Steifigkeit
    ausgefallener Zugstaebe) kommt in jedem Schritt zur Kontaktsteifigkeit.

    ``einfrieren`` ist die Sicherung eines konvergierten Kontaktzustands, der
    **nicht** mehr veraendert wird: Kontaktsteifigkeit und -kraefte dieses
    Zustands, eine lineare Loesung, keine Iteration. Das ist der Weg fuer die
    Zustaende einer Ermuedungslast (kleine Aenderungen um einen Betriebszustand;
    am Drehlager eine Rueckwaertseinsetzung statt 32 bis 43 Kontaktschritten je
    Zustand). ``start`` ist die Sicherung eines konvergierten Kontaktzustands
    (Results.kontaktzustand des vorigen Lastfalls): die Iteration beginnt
    dort statt bei der Geometrie. Zustaende einer Ermuedungskombination
    unterscheiden sich wenig - der Warmstart braucht wenige Schritte statt
    der 42 am Drehlager. Jeder Schritt loest mit der Signatur des Zustands,
    damit eine unveraenderte Matrix nicht neu faktorisiert wird.

    ``uebermass`` ist das Uebermass des Lastfalls je Fuge (siehe
    :func:`case_uebermass`): ein negativer Anfangsspalt, aus dem die
    Kontaktrechnung die Pressspannung und ueber den Reibbeiwert die
    Schubtragfaehigkeit macht.
    """
    if probelauf:
        # Ein Schritt, Fugen im Anfangszustand. Fuer die Netzsteuerung ist der
        # Spannungssprung ein Netzmass, kein Nachweis - die 48 Kontaktschritte
        # eines warmen Lastfalls am Drehlager (235 s, gemessen 19.09.2026) sind
        # dafuer verschwendet.
        max_iter = 1
    log: list[str] = []
    cs = _kontaktsystem(system, model, uebermass, log)
    cs.set_force_scale(float(np.abs(F).max()) if F.size else 1.0)
    cs.initialize()
    # ContactSystem.signatur() kennt nur den Kontakt. Mit einem K_zusatz, das
    # sich zwischen zwei Aufrufen aendert - die konsistente Tangente der
    # Plastizitaet tut das in jedem Newton-Schritt, die abgezogene Steifigkeit
    # ausgefallener Zugstaebe in jedem Ausfallschritt - bliebe bei gleicher
    # Aktivmenge die **alte** Faktorisierung stehen und loeste mit der falschen
    # Matrix. Darum der Inhalt von K_zusatz im Schluessel (20.09.2026).
    kz_kenn = None if K_zusatz is None else (
        tuple(K_zusatz.shape), int(K_zusatz.nnz),
        hash(np.ascontiguousarray(K_zusatz.tocsr().data).tobytes()))

    def signatur():
        s = cs.signatur()
        return s if kz_kenn is None else s + (kz_kenn,)

    f0 = getattr(system, "faktorisierungen", 0)
    if einfrieren is not None and cs.cons and cs.zustand_setzen(einfrieren):
        Kc, Fc = cs.matrices(model.ndof)
        if K_zusatz is not None:
            Kc = Kc + K_zusatz
        u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
        cs._update_states(u)                 # nur zur Auswertung: g, Fn, Ft je Bedingung
        R = system.reactions(u, F + Fc, Kc)
        Rsup = cs.support_reactions(model.nn)
        n6 = model.nn * NDOF
        Rk = R[:n6].reshape(-1, NDOF)
        Rk[:, :3] += Rsup
        R[:n6] = Rk.ravel()
        log.append("Kontaktzustand eingefroren: Kontaktsteifigkeit und -kräfte des "
                   "Referenzzustands, lineare Lösung ohne Iteration")
        log.extend(cs.warnings())
        return u, R, cs.results(), cs.nodal_forces(model.nn), {
            "contact_iterations": 1, "contact_converged": True, "contact_log": log,
            "contact_warm": False, "contact_frozen": True,
            "contact_factorisations": getattr(system, "faktorisierungen", 0) - f0,
            "contact_state": None}
    warm = bool(start) and cs.zustand_setzen(start)
    if warm:
        log.append("Warmstart aus dem Kontaktzustand des vorigen Lastfalls")
    converged = False
    it = 0
    Kc = Fc = None

    def matrizen():
        Kc_, Fc_ = cs.matrices(model.ndof)
        if K_zusatz is not None:
            Kc_ = (Kc_ + K_zusatz) if Kc_ is not None else K_zusatz
        return Kc_, Fc_

    if not cs.cons:
        u = system.solve(F, K_extra=K_zusatz, us=us)
        R = system.reactions(u, F, K_zusatz)
        return u, R, [], np.zeros((model.nn, 3)), {"contact_iterations": 0,
                                                   "contact_converged": True,
                                                   "contact_log": log,
                                                   "contact_state": None}
    u = None
    forced = False
    for it in range(1, max_iter + 1):
        Kc, Fc = matrizen()
        u_vor = u                  # fuer die Protokollzeile: was bewegt die Runde?
        f_vor = getattr(system, "faktorisierungen", 0)
        try:
            u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
        except RuntimeError as ex:
            if it == 1 and warm and versuch < 3:
                # Warmstart: eine im vorigen Lastfall offene Bedingung (Lager
                # mit Ausfall, Schlupf) laesst dieses System im ersten Schritt
                # ohne Halt - der kalte Start beginnt mit geschlossenen
                # Bedingungen und hat das Problem nicht (12.09.2026, test_web:
                # Lager mit Reibung, Ausfall bei Zug und Schlupf 2 mm)
                log.append("Warmstart verworfen: im ersten Schritt kein Gleichgewicht - "
                           "Neustart von der Geometrie")
                u2, R2, cons2, cf2, cinfo2 = solve_with_contact(
                    model, system, F, max_iter, progress, us, K_zusatz, uebermass,
                    start=None, versuch=versuch + 1, fenster=fenster,
                    probelauf=probelauf)
                cinfo2["contact_log"] = log + list(cinfo2.get("contact_log", []))
                cinfo2["contact_warm"] = False
                cinfo2["contact_factorisations"] = getattr(system, "faktorisierungen", 0) - f0
                return u2, R2, cons2, cf2, cinfo2
            if it == 1 and not forced and cs.stabilise():
                # Im ersten Schritt haelt keine Bedingung - etwa eine Schraube,
                # die erst nach dem Durchfahren des Lochspiels traegt. Ein
                # Hilfsschritt mit allen Bedingungen als reine Federn zeigt,
                # wohin sich das Bauteil bewegen will; danach bleiben nur die
                # Bedingungen geschlossen, auf die es sich zubewegt.
                forced = True
                log.append("Hilfsschritt: Bewegungsrichtung bestimmt, weil im ersten "
                           "Schritt keine Kontaktbedingung haelt")
                Kc, Fc = matrizen()
                try:
                    u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
                except RuntimeError as ex2:
                    raise _kontakt_abbruch(it, ex2, cs, model, u, log=log) from None
                cs.select_by_direction(u)
                Kc, Fc = matrizen()
                try:
                    u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
                except RuntimeError as ex3:
                    raise _kontakt_abbruch(it, ex3, cs, model, u, log=log) from None
            else:
                # Ein Teil hat (fast) alle Bedingungen verloren - an den am
                # wenigsten offenen gehalten und denselben Schritt noch einmal
                # geloest; reicht das nicht, bis zur Haelfte halten
                geloest = False
                for stufe in (1, 2):
                    if not _freie_teile_halten(model, cs, log, stufe=stufe):
                        continue
                    Kc, Fc = matrizen()
                    try:
                        u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
                        geloest = True
                        break
                    except RuntimeError as ex4:
                        ex = ex4
                if not geloest:
                    raise _kontakt_abbruch(it, ex, cs, model, u, log=log) from None
        changed = cs.update(u)
        if cs.schub_halt_loesen():
            # Der Schubhalt hat den Schritt getragen; jetzt liegt das Teil
            # wieder an, und die gewoehnliche Haftbindung uebernimmt. Der
            # naechste Schritt rechnet ohne ihn.
            changed = True
        if progress:
            # Anteil im Fenster des Lastfalls: 1 - 0,85^it waechst mit jedem
            # Schritt und naehert sich der Fensterkante - ein wachsender Balken
            # statt eines wandernden Streifens (Wunsch 12.09.2026); wie viele
            # Schritte es werden, weiss vorher niemand (Drehlager 32 bis 43)
            anteil = None
            if fenster is not None:
                von, bis = float(fenster[0]), float(fenster[1])
                anteil = von + (bis - von) * (1.0 - 0.85 ** it)
            # Die blosse Zahl "aktiv" beantwortet die Frage nicht, ob eine
            # Runde noch etwas ausrichtet: sie zaehlt offen gegen geschlossen
            # und bleibt beim Wechsel haften -> gleiten unveraendert - und das
            # ist genau die Arbeit von Phase 2 (19.09.2026, Anwender: "ist das
            # wirklich relevant obwohl sich die anzahl so gering aendert").
            # Darum dazu, wie weit sich u noch bewegt und ob die Matrix neu
            # faktorisiert wurde: neu wird sie nur bei geaenderter Signatur
            # (Aktivmenge, Haften/Gleiten, Fliessen) - Gleitrichtungen und
            # Reibkraefte stehen allein in Fc. Am Drehlager kostet eine
            # Faktorisierung 4,23 s bei 476 214 Zeilen, das Rueckwaerts-
            # einsetzen einen Bruchteil davon; daran liegt es, dass die
            # Runden gegen Ende rasen ("die iterationen werden immer
            # schneller").
            zusatz = ""
            if u_vor is not None and u is not None:
                bez = float(np.abs(u).max())
                d = float(np.abs(u - u_vor).max())
                zusatz = (f", Δu {d / bez:.1e}" if bez > 0 else f", Δu {d:.1e} m")
            zusatz += (", Matrix neu" if getattr(system, "faktorisierungen", 0) > f_vor
                       else ", Matrix bleibt")
            _melde(progress, f"Kontakt-Iteration {it}: {cs.n_active} aktiv{zusatz}", anteil)
        if not changed:
            converged = True
            break
    if converged and u is not None:
        schub = cs.schub_unter_last(u)
        if schub:
            # Der Schubhalt hat den Schritt getragen, nicht das Ergebnis: das
            # Teil haengt am Schluss an einer Bindung, deren Bedingungen alle
            # offen sind - dann gibt es dort kein Gleichgewicht.
            text = ("kein belastbares Ergebnis - " + "; ".join(
                f"{fuge} hängt am Schubhalt ({n} Bedingungen, {k / 1e3:.1f} kN Schub), "
                "obwohl dort keine Bedingung geschlossen ist" for fuge, n, k in schub[:6])
                + (" …" if len(schub) > 6 else "")
                + ". Abhilfe: Verbund oder Vorspannung an der Fuge, ein Lager, oder die "
                  "Last in die Fuge drücken lassen.")
            log.append(text)
            raise _kontakt_abbruch(it, RuntimeError(text), cs, model, u, log=log) from None
        zug = _gehaltene_unter_zug(model, cs)
        if zug:
            # Der Halt hat den Schritt gerettet, nicht das Ergebnis: das Teil
            # zieht an den gehaltenen Punkten - es hebt ab, kein Gleichgewicht
            text = ("kein statisches Gleichgewicht - " + "; ".join(
                f"{name} hebt ab und hängt an {n_geh} gehaltenen Kontaktpunkten unter {kraft / 1e3:.1f} kN Zug"
                for name, _kn, n_geh, kraft, _c in zug[:6]) + (" …" if len(zug) > 6 else "")
                + ". Abhilfe: Verbund oder Vorspannung an der Fuge, ein Lager, oder die Last in die Fuge drücken lassen.")
            log.append(text)
            raise _kontakt_abbruch(it, RuntimeError(text), cs, model, u, zug=zug, log=log) from None
    if warm and converged and u is not None:
        n_v = cs.warmstart_verstoesse(u)
        if n_v:
            # Gleitende Knoten bewegen sich gegen ihre festgehaltene Richtung.
            # Wenige: auf Haften zuruecksetzen und weiter (die Iteration findet
            # die Richtung neu, die Matrix bleibt meist). Viele oder wiederholt:
            # der Zustand passt nicht zu diesem Lastfall - von der Geometrie neu.
            wenige = n_v <= max(2, cs.n_slip // 10) and versuch < 2
            if wenige:
                cs.warmstart_verstoesse(u, zuruecksetzen=True)
                log.append(f"Warmstart: {n_v} gleitende Knoten bewegten sich gegen ihre "
                           "Richtung - auf Haften zurueckgesetzt, Iteration fortgesetzt")
                neu_start = cs.zustand()
            else:
                log.append(f"Warmstart verworfen: {n_v} gleitende Knoten bewegen sich gegen "
                           "ihre Richtung - Neustart von der Geometrie")
                neu_start = None
            u2, R2, cons2, cf2, cinfo2 = solve_with_contact(
                model, system, F, max_iter, progress, us, K_zusatz, uebermass,
                start=neu_start, versuch=versuch + 1, fenster=fenster,
                probelauf=probelauf)
            cinfo2["contact_log"] = log + list(cinfo2.get("contact_log", []))
            cinfo2["contact_warm"] = bool(neu_start) and cinfo2.get("contact_warm", False)
            cinfo2["contact_iterations"] = it + cinfo2.get("contact_iterations", 0)
            cinfo2["contact_factorisations"] = getattr(system, "faktorisierungen", 0) - f0
            return u2, R2, cons2, cf2, cinfo2
    R = system.reactions(u, F + (Fc if Fc is not None else 0.0), Kc)
    # Einseitige Lager als Auflagerreaktionen ausweisen
    Rsup = cs.support_reactions(model.nn)
    n6 = model.nn * NDOF
    Rk = R[:n6].reshape(-1, NDOF)
    Rk[:, :3] += Rsup
    R[:n6] = Rk.ravel()
    if not converged:
        # Auch in den Fortschrittsstrom: das Protokoll und die Rechenliste
        # zeigen es damit waehrend des Laufs. Bisher stand es allein in
        # res.info["contact_log"] - also erst hinterher im Bericht, und bei
        # 422 Lastfaellen merkt man dort erst am Ende, dass einer haengt.
        text = ("Probelauf: ein Kontaktschritt gerechnet, nicht auskonvergiert - "
                "das Ergebnis ist ein Netzmaß, kein Nachweis"
                if probelauf else
                f"Kontakt-Iteration nach {max_iter} Schritten nicht konvergiert")
        log.append(text)
        _melde(progress, text)
    log.extend(cs.warnings())
    return u, R, cs.results(), cs.nodal_forces(model.nn), {
        "contact_iterations": it, "contact_converged": converged, "contact_log": log,
        "contact_warm": warm,
        "contact_factorisations": getattr(system, "faktorisierungen", 0) - f0,
        "contact_state": cs.zustand()}


# ==========================================================================
# Umhuellende
# ==========================================================================
class Envelope:
    """Extremwerte ueber mehrere Ergebnisse (Kombinationen) mit Herkunft.

    Gebildet wird **inkrementell**: :meth:`aufnehmen` faltet ein Ergebnis in
    das laufende Minimum und Maximum ein, :meth:`aufnehmen_umhuellende` eine
    ganze Umhuellende. Der Speicherbedarf haengt damit nicht von der Zahl der
    Ergebnisse ab - das Stapeln aller Ergebnisse (``np.stack``) hielte sie
    gleichzeitig im Speicher; eine RFEM-Ergebniskombination am Drehlager hat
    128 Alternativen, die Ermuedungskombinationen zusammen ueber 3500.

    Die Herkunft (``*_src``) ist der Index in ``names``. Bei Gleichstand
    gewinnt das **erste** Ergebnis - so wie ``argmin``/``argmax`` beim
    Stapeln; darum ist das laufende Verfahren bitgleich mit dem gestapelten
    (test_umhuellende). Ein Ergebnis, dem ein Stabelement fehlt, zaehlt dort
    mit Null - auch das wie beim Stapeln.

    ``Envelope(model, results, name)`` bleibt der Aufruf fuer alle, die schon
    ein Woerterbuch von Ergebnissen haben.
    """

    KOMPONENTEN = ("N", "Vy", "Vz", "Mt", "My", "Mz")

    def __init__(self, model: Model, results: dict = None, name: str = "Umhuellende",
                 n_stations: int = None):
        self.model = model
        self.name = name
        self.names: list = []
        self.n_stations = n_stations or model.design.stations
        nn = model.nn
        self.u_min = np.zeros((nn, NDOF))
        self.u_max = np.zeros((nn, NDOF))
        self.u_min_src = np.zeros((nn, NDOF), int)
        self.u_max_src = np.zeros((nn, NDOF), int)
        self.r_min = np.zeros((nn, NDOF))
        self.r_max = np.zeros((nn, NDOF))
        self.r_min_src = np.zeros((nn, NDOF), int)
        self.r_max_src = np.zeros((nn, NDOF), int)
        self.beam: dict = {}
        self.node_vm_max = np.zeros(nn)
        self.node_vm_src = np.zeros(nn, int)
        self.util: dict = {}
        for k, r in (results or {}).items():
            self.aufnehmen(k, r)

    # ---- Einfalten ------------------------------------------------------
    @staticmethod
    def _falten(mn, mx, imn, imx, wert, j):
        """Laufendes Min/Max eines Feldes mit Herkunft; Gleichstand bleibt beim
        aelteren Ergebnis (strenges < und >)."""
        kl = wert < mn
        gr = wert > mx
        return (np.where(kl, wert, mn), np.where(gr, wert, mx),
                np.where(kl, j, imn), np.where(gr, j, imx))

    def _stab_neu(self, x, j: int) -> dict:
        """Ein Stabelement, das erst im Ergebnis j auftaucht: die Ergebnisse
        davor zaehlen mit Null (Herkunft 0, das erste), wie beim Stapeln."""
        n = self.n_stations
        d: dict = {"x": x}
        null = np.zeros(n)
        for k in self.KOMPONENTEN:
            if j == 0:
                d[k] = None                      # wird gleich mit dem ersten Wert belegt
            else:
                d[k] = (null.copy(), null.copy(), np.zeros(n, int), np.zeros(n, int))
        return d

    def aufnehmen(self, name: str, r) -> None:
        """Ein Ergebnis einfalten: Verschiebungen, Auflagerkraefte,
        Stabschnittgroessen je Station, Vergleichsspannung, Ausnutzung."""
        j = len(self.names)
        self.names.append(name)
        n = self.n_stations
        u = np.asarray(r.u, float)
        R = np.asarray(r.reactions, float)
        vm = np.nan_to_num(np.asarray(r.node_vm, float))
        if j == 0:
            self.u_min, self.u_max = u.copy(), u.copy()
            self.r_min, self.r_max = R.copy(), R.copy()
            self.node_vm_max = vm.copy()
        else:
            self.u_min, self.u_max, self.u_min_src, self.u_max_src = self._falten(
                self.u_min, self.u_max, self.u_min_src, self.u_max_src, u, j)
            self.r_min, self.r_max, self.r_min_src, self.r_max_src = self._falten(
                self.r_min, self.r_max, self.r_min_src, self.r_max_src, R, j)
            gr = vm > self.node_vm_max
            self.node_vm_max = np.where(gr, vm, self.node_vm_max)
            self.node_vm_src = np.where(gr, j, self.node_vm_src)
        # Staebe: alle Elemente, die dieses oder ein frueheres Ergebnis kennt
        st = r.stations(n) if r.beam_end else {}
        null = np.zeros(n)
        for i in sorted(set(st) | set(self.beam)):
            p = st.get(i)
            d = self.beam.get(i)
            if d is None:
                d = self._stab_neu(p["x"] if p is not None else None, j)
                self.beam[i] = d
            if d["x"] is None and p is not None:
                d["x"] = p["x"]
            for k in self.KOMPONENTEN:
                wert = np.asarray(p[k], float) if p is not None else null
                if d[k] is None:
                    d[k] = (wert.copy(), wert.copy(), np.zeros(n, int), np.zeros(n, int))
                else:
                    d[k] = self._falten(*d[k], wert, j)
        # Ausnutzung (elastisch) je Stab: das Maximum ueber alle Ergebnisse
        bf = r.beam_forces if r.beam_end else {}
        for i in set(bf) | set(self.util):
            v = bf[i]["util"] if i in bf else None
            vorher = self.util.get(i)
            werte = [x for x in (vorher, v) if x is not None]
            self.util[i] = max(werte) if werte else None

    def aufnehmen_umhuellende(self, env: "Envelope") -> None:
        """Eine Umhuellende einfalten - die Herkunft zeigt danach auf deren
        Ergebnisse (ihre Namen werden angehaengt), nicht auf die Umhuellende."""
        if not env.names:
            return
        versatz = len(self.names)
        self.names.extend(env.names)
        n = self.n_stations
        if versatz == 0:
            self.u_min, self.u_max = env.u_min.copy(), env.u_max.copy()
            self.u_min_src, self.u_max_src = env.u_min_src.copy(), env.u_max_src.copy()
            self.r_min, self.r_max = env.r_min.copy(), env.r_max.copy()
            self.r_min_src, self.r_max_src = env.r_min_src.copy(), env.r_max_src.copy()
            self.node_vm_max, self.node_vm_src = env.node_vm_max.copy(), env.node_vm_src.copy()
            self.beam = {i: {k: (tuple(np.array(x) for x in v) if k != "x" else v)
                             for k, v in d.items()} for i, d in env.beam.items()}
            self.util = dict(env.util)
            return
        self.u_min, self.u_max, self.u_min_src, self.u_max_src = self._falten_umhuellende(
            (self.u_min, self.u_max, self.u_min_src, self.u_max_src),
            (env.u_min, env.u_max, env.u_min_src, env.u_max_src), versatz)
        self.r_min, self.r_max, self.r_min_src, self.r_max_src = self._falten_umhuellende(
            (self.r_min, self.r_max, self.r_min_src, self.r_max_src),
            (env.r_min, env.r_max, env.r_min_src, env.r_max_src), versatz)
        gr = env.node_vm_max > self.node_vm_max
        self.node_vm_max = np.where(gr, env.node_vm_max, self.node_vm_max)
        self.node_vm_src = np.where(gr, env.node_vm_src + versatz, self.node_vm_src)
        null = np.zeros(n)
        for i in sorted(set(env.beam) | set(self.beam)):
            d = self.beam.get(i)
            e = env.beam.get(i)
            if d is None:
                # Element nur in der eingefalteten Umhuellende: die eigenen
                # Ergebnisse davor zaehlen mit Null, Herkunft 0
                d = {"x": None}
                for k in self.KOMPONENTEN:
                    d[k] = (null.copy(), null.copy(), np.zeros(n, int), np.zeros(n, int))
                self.beam[i] = d
            if e is None:
                # Element nur hier: die Ergebnisse der Umhuellende zaehlen mit
                # Null, Herkunft = ihr erstes Ergebnis
                e = {"x": None}
                for k in self.KOMPONENTEN:
                    e[k] = (null, null, np.full(n, 0, int), np.full(n, 0, int))
            if d["x"] is None and e.get("x") is not None:
                d["x"] = e["x"]
            for k in self.KOMPONENTEN:
                d[k] = self._falten_umhuellende(d[k], e[k], versatz)
        for i in set(env.util) | set(self.util):
            werte = [x for x in (self.util.get(i), env.util.get(i)) if x is not None]
            self.util[i] = max(werte) if werte else None

    @staticmethod
    def _falten_umhuellende(eigen, fremd, versatz: int):
        mn, mx, imn, imx = eigen
        fmn, fmx, fimn, fimx = fremd
        kl = fmn < mn
        gr = fmx > mx
        return (np.where(kl, fmn, mn), np.where(gr, fmx, mx),
                np.where(kl, np.asarray(fimn) + versatz, imn),
                np.where(gr, np.asarray(fimx) + versatz, imx))

    # ---- Auswertung ------------------------------------------------------
    @property
    def umag_max(self) -> np.ndarray:
        return np.maximum(np.linalg.norm(self.u_max[:, :3], axis=1),
                          np.linalg.norm(self.u_min[:, :3], axis=1))

    def extreme_table(self) -> list[list]:
        """Zeilen: Element, Groesse, min, Kombination, max, Kombination."""
        rows = []
        for i, d in self.beam.items():
            for k in self.KOMPONENTEN:
                mn, mx, imn, imx = d[k]
                j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
                rows.append([i, k, float(mn[j1]), self.names[imn[j1]],
                             float(mx[j2]), self.names[imx[j2]]])
        return rows

    def summary(self) -> str:
        s = [f"{self.name}: {len(self.names)} Ergebnisse"]
        if self.u_max.size and self.names:
            um = self.umag_max
            i = int(np.argmax(um))
            s.append(f"max. Verschiebung       : {um[i]*1000:.3f} mm (Knoten {i})")
        if self.beam:
            for k in ("N", "My", "Mz"):
                mn = min(float(d[k][0].min()) for d in self.beam.values())
                mx = max(float(d[k][1].max()) for d in self.beam.values())
                unit = "kN" if k == "N" else "kNm"
                s.append(f"{k:2s} min/max              : {mn/1e3:.2f} / {mx/1e3:.2f} {unit}")
        if np.any(self.node_vm_max):
            s.append(f"max. Vergleichsspannung : {np.nanmax(self.node_vm_max)/1e6:.2f} MPa")
        return "\n".join(s)


# ==========================================================================
# Gesamtanalyse
# ==========================================================================
@dataclass
class Analysis:
    model: Model
    cases: dict = field(default_factory=dict)
    combinations: dict = field(default_factory=dict)
    envelopes: dict = field(default_factory=dict)
    design: object = None
    fatigue: object = None
    joints: object = None
    gzg: object = None
    beulen: object = None
    lasteinleitung: object = None
    volumen: object = None
    theorie2: object = None
    info: dict = field(default_factory=dict)
    #: je Situation das System und das Modell, mit dem gerechnet wurde
    #: (Grundstellung: das Modell selbst; Stellung: gedrehte Kopie)
    systeme: dict = field(default_factory=dict)
    modelle: dict = field(default_factory=dict)
    theorie3: object = None
    schwingung: object = None

    def all_results(self) -> dict:
        d = dict(self.cases)
        d.update(self.combinations)
        return d

    def envelope(self, typ: str = "ULS") -> Optional[Envelope]:
        return self.envelopes.get(typ)

    def summary(self) -> str:
        s = [f"Lastfaelle: {len(self.cases)}   Kombinationen: {len(self.combinations)}   "
             f"Rechenzeit: {self.info.get('time', 0):.2f} s ({self.info.get('parallel', '')})"]
        for k, env in self.envelopes.items():
            s.append(env.summary())
        if self.theorie2 is not None and getattr(self.theorie2, "kombinationen", None):
            s.append(self.theorie2.summary())
        if self.theorie3 is not None and getattr(self.theorie3, "kombinationen", None):
            s.append(self.theorie3.summary())
        if self.design is not None:
            s.append(self.design.summary())
        if self.fatigue is not None:
            s.append(self.fatigue.summary())
        if self.joints is not None:
            s.append(self.joints.summary())
        if self.gzg is not None:
            s.append(self.gzg.summary())
        if self.beulen is not None:
            s.append(self.beulen.summary())
        if self.lasteinleitung is not None:
            s.append(self.lasteinleitung.summary())
        if self.volumen is not None:
            s.append(self.volumen.summary())
        if self.theorie2 is not None and self.theorie2.kombinationen:
            s.append(self.theorie2.summary())
        return "\n".join(s)


def _lastfaelle_hoeherer_ordnung(model: Model, an, systeme: dict, progress=None):
    """Lastfaelle mit theorie II oder III: das lineare Ergebnis ersetzen."""
    from .theorie2 import solve_theorie2, Th2Results
    from .theorie3 import solve_theorie3, Th3Results
    ds = model.design
    for name, lc in model.load_cases.items():
        th = model.theorie_von(lc)
        if th not in ("II", "III") or name not in an.cases:
            continue
        m_s, sys_s = systeme[lc.situation or GRUNDSTELLUNG]
        try:
            if th == "II":
                res, info = solve_theorie2(m_s, {name: 1.0}, name, sys_s,
                                           imperfektionen=bool(getattr(ds, "imperfektionen", True)),
                                           elastisch=not getattr(ds, "th2_plastisch", False),
                                           richtung=getattr(ds, "th2_richtung", None),
                                           alle_vorkruemmungen=bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
                                           progress=progress)
                if an.theorie2 is None:
                    an.theorie2 = Th2Results(settings={"modus": "je Lastfall/Kombination"})
                an.theorie2.kombinationen[name] = info
            else:
                res, info = solve_theorie3(m_s, {name: 1.0}, name,
                                           schritte=int(getattr(ds, "th3_schritte", 10) or 10),
                                           aktiv=getattr(sys_s, "aktiv", None), progress=progress)
                if an.theorie3 is None:
                    an.theorie3 = Th3Results(settings={"schritte": int(getattr(ds, "th3_schritte", 10) or 10)})
                an.theorie3.kombinationen[name] = info
        except ValueError as ex:
            an.info.setdefault("warnungen", []).append(f"Lastfall {name}: {ex}")
            continue
        if not info.fehler:
            res.kind = "case"
            if lc.situation:
                res.info["situation"] = lc.situation
            an.cases[name] = res


def ermuedungsreferenzen(model: Model) -> dict:
    """{Zustand: Referenzzustand} fuer die Zustaende der Ermuedungslasten eines
    Kontaktmodells (DesignSettings.ermuedung_kontakt_einfrieren).

    Der erste Zustand jeder Ermuedungslast wird nichtlinear geloest, die
    weiteren mit seinem eingefrorenen Kontaktzustand linear. Ein Zustand, der
    schon eingefroren ist, gibt seine Referenz weiter; ein Zustand, der selbst
    Referenz ist, bleibt nichtlinear. Am Drehlager: 50 Ermuedungslasten mit 2
    bis 82 Zustaenden, 164 Zustaende - statt 164 x 18 min etwa 47 x 18 min
    und 117 Rueckwaertseinsetzungen.
    """
    if not model.has_contact or not getattr(model.design, "ermuedung_kontakt_einfrieren", True):
        return {}
    ref: dict = {}
    refs: set = set()
    for fl in model.fatigue_loads.values():
        zust = [z for z in (fl.folge or []) if z in model.load_cases]
        if not zust:
            zust = [z for z in (fl.case_max, fl.case_min) if z and z in model.load_cases]
        if len(zust) < 2:
            continue
        erster = ref.get(zust[0], zust[0])
        refs.add(erster)
        for z in zust[1:]:
            if z not in ref and z not in refs and z != erster:
                ref[z] = erster
    return {z: r for z, r in ref.items() if z not in refs}


def solve_all(model: Model, workers: int = None, progress=None, combinations: bool = True,
              envelopes: bool = True, design: bool = False, fatigue: bool = False) -> Analysis:
    """Alle Lastfaelle, alle Kombinationen, Umhuellende, optional Nachweise -
    mit einem stehenden Prozesspool fuer alle Elementschleifen der Rechnung
    (parallel.arbeiter)."""
    with parallel.arbeiter(model, workers):
        return _solve_all_innen(model, workers, progress, combinations, envelopes, design, fatigue)


def _teilanalyse(ex, an: Analysis, model: Model, systeme: dict, t0: float) -> None:
    """Nach einem Abbruch: was gerechnet ist, an die Ausnahme haengen.

    Die Oberflaeche zeigt es als ganz gewoehnliches Ergebnis - nur mit dem
    Vermerk, dass der Lauf nicht vollstaendig ist (``info["abgebrochen"]``).
    Keine Umhuellenden und keine Nachweise: beide gaeben ueber einen halben
    Satz Lastfaelle ein falsches Bild, und eine Umhuellende ueber drei von
    422 Kombinationen sieht aus wie eine ueber alle.
    """
    if getattr(ex, "teilanalyse", None) is not None:
        return
    if not an.cases:
        an.cases = dict(getattr(ex, "teil_cases", None) or {})
    if not an.combinations:
        an.combinations = dict(getattr(ex, "teil_combinations", None) or {})
    if not an.cases and not an.combinations:
        return                      # nichts fertig - nichts zu retten
    if not an.systeme and systeme:
        an.systeme = {k: v[1] for k, v in systeme.items()}
        an.modelle = {k: v[0] for k, v in systeme.items()}
    an.envelopes = {}
    an.info["abgebrochen"] = True
    an.info["gerechnet"] = {"lastfaelle": len(an.cases), "kombinationen": len(an.combinations)}
    an.info["offen"] = {"lastfaelle": max(0, len(model.load_cases) - len(an.cases)),
                        "kombinationen": max(0, len(model.combinations) - len(an.combinations))}
    an.info.setdefault("time", time.time() - t0)
    an.info.setdefault("parallel", parallel.describe())
    an.info.setdefault("ndof", model.ndof)
    try:
        ex.teilanalyse = an
    except Exception:                # noqa: BLE001 - das Retten darf nie selbst scheitern
        pass


def _solve_all_innen(model: Model, workers: int = None, progress=None, combinations: bool = True,
                     envelopes: bool = True, design: bool = False, fatigue: bool = False) -> Analysis:
    """Alle Lastfaelle, alle Kombinationen, Umhuellende, optional Nachweise.

    Bricht der Anwender mitten im Lauf ab, bleibt das Gerechnete erhalten:
    die Ausnahme traegt es als ``teilanalyse`` nach oben (19.09.2026, "es
    waere gut wenn gerechnete ergebnisse erhalten blieben").
    """
    t0 = time.time()
    an = Analysis(model)
    systeme: dict = {}
    try:
        return _solve_all_rumpf(model, an, systeme, workers, progress, combinations,
                                envelopes, design, fatigue, t0)
    except BaseException as ex:
        _teilanalyse(ex, an, model, systeme, t0)
        raise


def _solve_all_rumpf(model: Model, an: Analysis, systeme: dict, workers, progress, combinations,
                     envelopes, design, fatigue, t0) -> Analysis:
    """Der eigentliche Lauf - ``an`` und ``systeme`` fuellen sich unterwegs,
    damit ein Abbruch sie nicht mitnimmt (:func:`_teilanalyse`)."""
    if model.joints:
        # Das Momenten-Rotations-Verhalten der Anschluesse gehoert in die
        # Rechnung, nicht erst in den Nachweis: nachgiebige Anschluesse sitzen
        # als Drehfeder am Stabende (EN 1993-1-8, 5.1.2).
        from .joints.anschluss import federn_setzen
        an.info["anschlussfedern"] = federn_setzen(model)
    # Je Situation ein System: die Grundstellung (unbewegt, alles aktiv) und
    # jede Situation, in der ein Lastfall steht
    referenzen = ermuedungsreferenzen(model)
    if referenzen:
        an.info["kontakt_eingefroren"] = dict(referenzen)
        _melde(progress, f"Ermüdungszustände: {len(referenzen)} Zustände werden mit dem "
                         "eingefrorenen Kontaktzustand des ersten Zustands ihrer Ermüdungslast "
                         "linear gelöst (Nachweise → Konfiguration)")
    an.cases = solve_cases(model, workers=workers, progress=progress, systeme=systeme,
                           referenzen=referenzen)
    if GRUNDSTELLUNG not in systeme:
        systeme[GRUNDSTELLUNG] = (model, StaticSystem(model, workers, progress))
    an.systeme = {k: v[1] for k, v in systeme.items()}
    an.modelle = {k: v[0] for k, v in systeme.items()}
    system = an.systeme[GRUNDSTELLUNG]
    if combinations and model.combinations:
        an.combinations = solve_combinations(model, case_results=an.cases, system=None,
                                             workers=workers, progress=progress,
                                             systeme=systeme)
        # Kombinationen mit Alternativen: je eine Umhuellende, keine Ergebnisse
        # in an.combinations. Sie stehen hinter den Art-Umhuellenden (unten).
        umhuellende_ek: dict = {}
        for n, c in model.combinations.items():
            if c.ist_umhuellende:
                env, geloest = umhuellende_der_kombination(model, c, an.cases, systeme,
                                                           workers, progress)
                umhuellende_ek[n] = env
                an.info.setdefault("umhuellende", {})[n] = {
                    "alternativen": len(c.alternativen), "geloest": geloest}
        an.info["_umhuellende_ek"] = umhuellende_ek
    # Theorie je Lastfall: II. oder III. Ordnung ersetzt das lineare Ergebnis
    _lastfaelle_hoeherer_ordnung(model, an, systeme, progress)
    th2 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "II"]
    if th2 and an.combinations:
        # Gleichgewicht am verformten System: die Kombinationen werden
        # ersetzt, denn nach Theorie II. Ordnung gilt keine Superposition
        # mehr (EN 1993-1-1, 5.2). Danach erst die Umhuellenden bilden.
        # Ausdruecklich auf "II" gestellte Kombinationen werden immer
        # gerechnet, die uebrigen nach der Einstellung (auto: alpha_cr).
        from .theorie2 import check_theorie2
        erzwungen = {n for n in th2 if (model.combinations[n].theorie or "").upper() == "II"}
        t2 = check_theorie2(model, an, combos=th2, system=system, progress=progress,
                            systeme=systeme, erzwungen=erzwungen)
        if an.theorie2 is None:
            an.theorie2 = t2
        else:                       # Lastfaelle nach II. Ordnung stehen schon darin
            an.theorie2.kombinationen.update(t2.kombinationen)
            an.theorie2.settings.update(t2.settings)
    th3 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "III"]
    if th3 and an.combinations:
        from .theorie3 import check_theorie3
        t3 = check_theorie3(model, an, combos=th3, progress=progress, systeme=systeme)
        if an.theorie3 is None:
            an.theorie3 = t3
        else:
            an.theorie3.kombinationen.update(t3.kombinationen)
            an.theorie3.settings.update(t3.settings)
    umhuellende_ek = an.info.pop("_umhuellende_ek", {}) or {}
    if envelopes:
        groups: dict[str, dict] = {}
        for n, r in an.combinations.items():
            typ = model.combinations[n].typ
            key = "ULS" if typ in ("ULS", "EQU", "ACC", "USER") else typ
            groups.setdefault(key, {})[n] = r
        for key, rs in groups.items():
            an.envelopes[key] = Envelope(model, rs, f"Umhuellende {key}")
        # Die Umhuellende einer Ergebniskombination gehoert in die Umhuellende
        # ihrer Art: so sehen die Nachweise (GZT, GZG, Ermuedung) auch die
        # Alternativen - wie in RFEM.
        for n, env in umhuellende_ek.items():
            typ = model.combinations[n].typ
            key = "ULS" if typ in ("ULS", "EQU", "ACC", "USER") else typ
            if key not in an.envelopes:
                an.envelopes[key] = Envelope(model, {}, f"Umhuellende {key}")
            an.envelopes[key].aufnehmen_umhuellende(env)
        if not an.combinations and not umhuellende_ek:
            an.envelopes["CASES"] = Envelope(model, an.cases, "Umhuellende Lastfaelle")
    for n, env in umhuellende_ek.items():
        an.envelopes[n] = env
    _melde(progress, "Umhüllende gebildet", 0.92)
    if design and model.members:
        from .ec3.design import check_members
        _melde(progress, "Nachweise EC3", 0.94)
        an.design = check_members(model, an, progress=progress)
    if fatigue and model.fatigue_loads:
        from .ec3.fatigue import check_fatigue
        an.fatigue = check_fatigue(model, an, progress=progress)
    if design and model.joints:
        # Anschluesse gehoeren zu den Nachweisen: sie laufen mit, sobald
        # Nachweise verlangt sind (DIN EN 1993-1-8 / -1-9).
        from .joints.anschluss import check_joints
        an.joints = check_joints(model, an, progress=progress, ermuedung=bool(fatigue))
    if design and model.verformungsgrenzen:
        from .gzg import check_verformung
        an.gzg = check_verformung(model, an, progress=progress)
    if design and model.beulfelder:
        from .ec3.beulen import check_beulen
        an.beulen = check_beulen(model, an, progress=progress)
    if design and model.lasteinleitungen:
        from .ec3.beulen import check_lasteinleitungen
        an.lasteinleitung = check_lasteinleitungen(model, an, progress=progress)
    if design and model.volumenbereiche:
        from .ec3.volumen import check_volumen
        an.volumen = check_volumen(model, an, progress=progress)
    an.info.update({"time": time.time() - t0, "parallel": parallel.describe(),
                    "solver": system.backend, "ndof": model.ndof,
                    "nfree": len(system.fi)})
    _melde(progress, f"Berechnung fertig ({time.time() - t0:.1f} s)", 1.0)
    return an


# ==========================================================================
# Modalanalyse
# ==========================================================================
#: Eigenfrequenz, unter der eine Form als Starrkoerperform gilt [Hz]
STARR_HZ = 1e-2


def solve_modal(model: Model, nmodes: int = 8, progress=None, workers: int = None,
                aktiv=None, zusatzmasse=None, kontakt=None) -> Results:
    """Eigenfrequenzen und Eigenformen. ``aktiv``: Elementmaske einer Situation;
    ``zusatzmasse``: zusaetzliche Massenmatrix (ndof x ndof), z. B. die
    hydrodynamische Masse eines Verschlusses (schwingung.zusatzmassen).

    ``kontakt``: der Kontaktzustand einer gerechneten statischen Loesung
    (``Results.kontaktzustand``) - dann schwingt das System um diesen
    Zustand (geschlossene Paare uebertragen, offene nicht). Ohne ihn gelten
    alle Kontaktpaare als **geschlossen und haftend** (verklebt). Vorher
    fehlte der Kontakt ganz: die Koerper schwangen frei - am Block mit
    Reibung kamen sechs Starrkoerperformen mit 0 Hz heraus, und ein Modell,
    dessen Koerper nur ueber Kontakt gehalten sind, lief auf eine singulaere
    Matrix (12.09.2026: „nach der Berechnung keine Ergebnisse").

    Geloest wird mit Shift-Invert um einen **leicht negativen** Shift: K - sigma M
    ist dann auch bei freien Koerpern regulaer, und Starrkoerperformen kommen
    als Eigenwerte nahe null heraus (``info["starrkoerper"]``, in der
    Zusammenfassung benannt) statt als Fehler. Die Faktorisierung uebernimmt
    :class:`LinearSolver` (MKL PARDISO, wenn vorhanden) statt SuperLU.
    """
    from scipy.sparse.linalg import LinearOperator
    t0 = time.time()
    with parallel.arbeiter(model, workers):
        K = asm.stiffness(model, workers, aktiv)
        M = asm.mass(model, workers, aktiv)
    if zusatzmasse is not None:
        M = (M + zusatzmasse).tocsr()
    kontakt_text, n_kontakt = "", 0
    if getattr(model, "contact_pairs", None):
        from . import contact as ct
        cs = ct.ContactSystem(model, K.tocsr(), log=[])
        if kontakt and cs.zustand_setzen(kontakt):
            kontakt_text = "Zustand der statischen Loesung"
        else:
            for c in cs.cons:
                c.active, c.slip, c.yielding, c.frozen = True, False, False, False
            kontakt_text = "alle Paare geschlossen und haftend (verklebt)"
        Kc, _Fc = cs.matrices(model.ndof)
        n_kontakt = int(cs.n_active)
        if Kc is not None and getattr(Kc, "nnz", 0):
            K = (K + Kc).tocsr()
        if progress:
            _melde(progress, f"Kontakt: {kontakt_text}", 0.3)
    fixed, vals = asm.constrained_dofs(model, K)
    md = np.asarray(M.diagonal()).ravel()
    fixed = fixed | (md <= 0)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Mff = M[fi][:, fi].tocsc()
    if progress:
        _melde(progress, "Eigenwertproblem wird gelöst", 0.45)

    k = min(nmodes, Kff.shape[0] - 2)
    kd = np.abs(np.asarray(Kff.diagonal()).ravel())
    mdf = np.asarray(Mff.diagonal()).ravel()
    sigma = -1e-6 * float(kd.mean() / max(float(mdf.mean()), 1e-300))
    A = (Kff - sigma * Mff).tocsc()
    loeser = LinearSolver(A)
    try:
        op = LinearOperator(A.shape, dtype=float,
                            matvec=lambda x: loeser.solve(np.asarray(x, float).ravel(), check=False))
        vals_, vecs = eigsh(Kff, k=k, M=Mff, sigma=sigma, which="LM", OPinv=op)
    finally:
        loeser.freigeben()
    order = np.argsort(vals_)
    vals_ = np.maximum(vals_[order], 0.0)
    vecs = vecs[:, order]

    freqs = np.sqrt(vals_) / (2 * np.pi)
    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = Results(name="Modalanalyse", kind="modal", model=model)
    res.u = np.zeros((model.nn, NDOF))
    res.reactions = np.zeros((model.nn, NDOF))
    res.freqs = freqs
    res.modes = modes[:, :model.nn * NDOF].reshape(k, model.nn, NDOF)
    res.info = {"ndof": model.ndof, "nfree": len(fi), "time": time.time() - t0,
                "zusatzmasse": zusatzmasse is not None,
                "starrkoerper": int(np.sum(freqs < STARR_HZ)),
                "kontakt": kontakt_text, "kontakt_aktiv": n_kontakt,
                "loeser": loeser.backend}
    return res


# ==========================================================================
# Lineares Knicken
# ==========================================================================
def solve_buckling(model: Model, nmodes: int = 5, progress=None, case: str = None,
                   combination: str = None, workers: int = None) -> Results:
    """Lineares Verzweigungsproblem: (K + lambda*Kg) v = 0 (Stabtragwerke).
    Grundzustand: Lastfall (default aktiver) oder Kombination."""
    t0 = time.time()
    system = StaticSystem(model, workers, progress)
    if combination:
        static = solve_combination(model, model.combinations[combination], None, system, workers)
    else:
        static = solve_static(model, progress, case, workers, system)
    u = static.u.ravel()
    K = system.K
    Kg = asm.geometric_stiffness(model, u)
    fi = system.fi
    Kff = system.Kff
    Kgff = Kg[fi][:, fi].tocsc()
    if abs(Kgff).max() == 0:
        raise RuntimeError("Keine Normalkraefte vorhanden - Knicknachweis nicht moeglich")
    if progress:
        _melde(progress, "Verzweigungsproblem wird gelöst", 0.45)

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = eigsh(Kff, k=k, M=-Kgff, sigma=0.0, which="LM")
    order = np.argsort(np.abs(vals_))
    vals_ = vals_[order]
    vecs = vecs[:, order]

    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = static
    res.kind = "buckling"
    res.buckling_factors = vals_
    res.buckling_modes = modes[:, :model.nn * NDOF].reshape(k, model.nn, NDOF)
    res.info["time"] = time.time() - t0
    return res
