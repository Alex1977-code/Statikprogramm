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
    beim Initialisieren, spaeteres Setzen bleibt wirkungslos. Setzt auch die
    Vorgabe MKL_CBWR=AUTO (siehe statik3d/__init__.py) - fuer den Fall, dass
    solver ohne das Paket geladen wurde; ein gesetzter Wert hat Vorrang.
    """
    import os
    os.environ.setdefault("MKL_CBWR", "AUTO")
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
            if _MKL_LIB:
                _mkl_cbwr_festhalten(_MKL_LIB)
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


#: MKL_CBWR, wie es galt, als Statik3D MKL zum ersten Mal geladen hat - None,
#: solange das nicht geschehen ist (siehe _mkl_cbwr_festhalten).
_MKL_CBWR = None

#: Argument von MKL_CBWR_Get fuer den eingestellten Zweig und die Namen der
#: Zweige, aus mkl_cbwr.h. Der Header liegt der Programmumgebung nicht bei;
#: gelesen aus der Kopie in Intels Repository intel/mklnn (src/mkl_cat.h,
#: Abschnitt "MKL CBWR stuff"), die Signatur ``int mkl_cbwr_get(int option)``
#: aus IntelPython/mkl-service (mkl/_mkl_service.pxd). Gemessen 22.09.2026 am
#: mkl_rt.3.dll der Programmumgebung: ohne Variable 1, mit MKL_CBWR=AUTO 2,
#: mit MKL_CBWR=COMPATIBLE 3 - wie die Tabelle.
MKL_CBWR_BRANCH = 1
MKL_CBWR_ZWEIGE = {0: "OFF", 1: "BRANCH_OFF", 2: "AUTO", 3: "COMPATIBLE", 4: "SSE2",
                   5: "SSE3", 6: "SSSE3", 7: "SSE4_1", 8: "SSE4_2", 9: "AVX", 10: "AVX2",
                   11: "AVX512_MIC", 12: "AVX512"}


def _mkl_cbwr_festhalten(lib) -> None:
    """MKL_CBWR festhalten, einmal je Prozess, beim ersten Laden von MKL.

    MKL liest die Variable nur beim Laden; wer sie danach setzt, aendert
    nichts mehr (gemessen 22.09.2026: gesetzt nach dem Laden, meldet MKL
    weiter den alten Zweig). Darum zaehlt der Wert von diesem Zeitpunkt und
    nicht der beim Faktorisieren. Daneben steht, was MKL selbst meldet
    (MKL_CBWR_Get) - aber nur, wenn das geladene mkl_rt die Funktion hat;
    sonst "unbekannt", nicht geraten.

    Ein eigener Prototyp statt ``lib.MKL_CBWR_Get``: argtypes am geteilten
    CDLL-Objekt gelten fuer alle, die es benutzen.
    """
    global _MKL_CBWR
    if _MKL_CBWR is not None:
        return
    import ctypes
    code, zweig = "unbekannt", "unbekannt"
    lib = getattr(lib, "libmkl", lib)
    if lib is not None:
        try:
            lesen = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int)(("MKL_CBWR_Get", lib))
            code = int(lesen(MKL_CBWR_BRANCH))
            zweig = MKL_CBWR_ZWEIGE.get(code, f"unbekannt ({code})")
        except Exception:                                  # noqa: BLE001
            code, zweig = "unbekannt", "unbekannt"
    _MKL_CBWR = {"umgebung": os.environ.get("MKL_CBWR"), "code": code, "zweig": zweig}


def mkl_cbwr() -> Optional[dict]:
    """{umgebung, code, zweig} vom ersten Laden von MKL - None, solange
    Statik3D MKL nicht geladen hat. ``umgebung`` ist None ohne Variable."""
    return None if _MKL_CBWR is None else dict(_MKL_CBWR)


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


def ist_symmetrisch(K, tol: float = None, proben: int = 4) -> bool:
    """Ist die Matrix symmetrisch? Sondiert, nicht durchlaufen.

    Ist K symmetrisch, dann ist ``K r = K^T r`` fuer **jedes** r. Mit r aus
    plus/minus eins zeigt sich eine Unsymmetrie der Groesse eps an einer
    Stelle als genau eps in ``(K - K^T) r`` - die Sonde ist damit so
    empfindlich wie ein Durchlauf, der dieselbe Schranke je Eintrag anlegt,
    und ``K.T`` ist bei CSR eine CSC-Ansicht derselben Felder, kostet also
    nichts.

    **Warum das nicht immer so war.** Bis zum 22.09.2026 lief hier ein
    blockweiser Durchlauf ueber ``K[a:b, :] - K[:, a:b].T``, und der
    Docstring behauptete, die Zeit falle "neben der Faktorisierung nicht ins
    Gewicht". Die Loesersitzung hat am Drehlager ein Zeitfenster von **1,12 s
    je Aufruf, 162,9 s im kalten LF1** gemessen - bei 145 Faktorisierungen,
    deren Symmetrie sich zwischen zwei Kontaktschritten nicht aendert. Das
    Fenster umfasste neben der Pruefung auch triu, sort_indices und die
    Diagonalpruefung; welcher Teil auf die Pruefung entfaellt, ist nicht
    gemessen. Ueber 422 Lastfaelle hochgerechnet mit den gemessenen
    Faktorisierungszahlen (145 kalt, im Mittel 91 warm) sind es rund 12 h fuer
    das ganze Fenster (eine fruehere Fassung schrieb 19 h fuer die Pruefung
    allein; Nachpruefung der Loesersitzung vom 22.09.2026). Die Sonde unten
    ist an einer Ersatzmatrix mit 475.935 Zeilen und 35,2 Mio. Eintraegen
    gemessen - doppelt so vielen wie am Drehlager (17,68 Mio.):

        Durchlauf   5,206 s
        Sonde       0,419 s        Faktor 12,4

    ``K - K.T`` als Ganzes bleibt verboten: scipy legt dafuer erst ein
    Ergebnis in der Groesse **beider** Strukturen an und kuerzt danach - am
    Drehlager waren das 87,7 Mio Eintraege und 669 MiB, die nicht mehr
    passten (18.09.2026).

    Zwei Fallen, beide beim Bauen hineingetappt und darum benannt:

    * Die Schranke ist **genau** ``tol``, ohne Zuschlag. Mit ``sqrt(n)``
      skaliert lag sie bei 3,7e-9 und verschluckte eine Stoerung von 5,4e-11,
      die der Durchlauf fand. Eine zu grosszuegige Sonde ist schlimmer als
      keine.
    * ``K.T.tocsr()`` baut die Transponierte wirklich auf: 1,33 s statt
      0,42 s. Die CSC-Ansicht ``K.T`` genuegt.

    Der Rauschabstand traegt auch bei Drehlagerskala: bei max |K| = 1,9e17
    (die Strafsteifigkeit ist 1e4 mal die Diagonale) stehen die beiden
    Produkte bitgleich, waehrend die Schranke bei 1,9e5 liegt; eine Stoerung
    von zehnfacher Schranke faellt auf.

    **Die dritte Falle, und die gefaehrlichste: r darf nicht aus plus/minus
    eins bestehen.** ``D = K - K^T`` ist antisymmetrisch, und vier Stellen
    loeschen sich in **allen** betroffenen Zeilen zugleich aus:

        D[k,i] = a    D[k,j] = -a    D[i,l] = a    D[j,l] = -a

        (D r)_k = a (r_i - r_j)      (D r)_i = a (r_l - r_k)
        (D r)_j = a (r_k - r_l)      (D r)_l = a (r_j - r_i)

    Alle vier sind null, sobald r_i = r_j und r_k = r_l - bei plus/minus
    eins eine gewoehnliche Bedingung. Weil die Sonden fest gesaet sind,
    lassen sich solche Indexpaare sogar **suchen**; genau das tut
    ``tests/test_loeser.py::test_die_symmetriesonde_hat_keine_luecke``.
    Ungestimmt meldet die Sonde dort "symmetrisch", obwohl die Abweichung
    3,84e-06 betraegt und die Schranke bei 1,92e-12 liegt - sechs
    Zehnerpotenzen daneben. Verstimmt faellt sie auf.

    Die Kur ist, r paarweise verschieden zu **verstimmen**: eine
    Ausloeschung verlangte dann d_i = d_j, und die d sind paarweise
    verschieden. Die Empfindlichkeit bleibt, weil |r| zwischen 1,000016 und
    1,001 liegt: eine Stoerung von 5,40e-11 zeigt sich als 5,40e-11.

    **Wie haeufig die Luecke ohne Absicht auftritt, ist dabei offen.** Die
    Loesersitzung hat 50,4 / 25,0 / 12,7 / 5,9 % (bei ein bis vier Sonden)
    gemessen, aber an einer **einzelnen Zeile**; in einer wirklichen Matrix
    verraten die antisymmetrischen Gegeneintraege die Abweichung meist in
    den Partnerzeilen. An 300 zufaelligen Vierermustern fiel mit plus/minus
    eins kein einziges durch. Die Verstimmung bleibt trotzdem drin: sie
    kostet ein ``arange`` und schliesst eine Klasse, die sich sonst nur
    durch Glueck nicht zeigt.
    """
    Kc = K.tocsr()
    if Kc.shape[0] != Kc.shape[1]:
        return False
    if tol is None:
        tol = 1e-12 * (float(abs(Kc).max()) if Kc.nnz else 1.0)
    n = Kc.shape[0]
    if n == 0 or Kc.nnz == 0:
        return True
    KT = Kc.T                      # CSC-Ansicht derselben Felder
    rng = np.random.default_rng(20260922)   # fest: dieselbe Matrix, dasselbe Urteil
    stimmung = 1.0 + 1.0e-3 * np.arange(1, n + 1, dtype=float) / n
    for _ in range(max(1, int(proben))):
        r = rng.choice((-1.0, 1.0), size=n) * stimmung
        if float(np.abs(Kc @ r - KT @ r).max()) > tol:
            return False
    return True


#: Schon gemeldete Hinweise - eine Faktorisierung laeuft in der
#: Kontakt-Iteration Dutzende Male, die Meldung soll einmal kommen.
_GEMELDET: set = set()


class LoeserAusfall(Exception):
    """Kein Gleichungsloeser konnte faktorisieren.

    **Bewusst keine RuntimeError**: ein RuntimeError beim Aufbau wird vom
    Aufrufer als singulaere Matrix gedeutet und mit „Lagerung pruefen"
    beantwortet (StaticSystem, diagnose.singulaer_text). Scheitern PARDISO
    und der Ausweichweg aus einem anderen Grund - Speicher, 32-Bit-Ueberlauf
    in SuperLU -, waere das eine falsche Diagnose.
    """


#: Einstellungen, die das Ergebnis oder den Rechenweg einer Kette bestimmen
#: und darum aus dem Hauptprozess mitgehen (siehe _cases_in_ketten).
KETTEN_EINSTELLUNGEN = ("solver_backend", "solver_residuum", "solver_nachiterationen",
                        "min_elements", "chunk_elements", "mumps_nachladen")


def kettenauftrag_einstellungen(st) -> dict:
    """Die Einstellungen, die eine Kette braucht - nur die, die von der
    Vorgabe abweichen."""
    vorgabe = parallel.Settings()
    return {k: getattr(st, k) for k in KETTEN_EINSTELLUNGEN
            if hasattr(st, k) and getattr(st, k) != getattr(vorgabe, k)}


def threads_je_kette(eingestellt: int, ketten: int) -> int:
    """Loeser-Threads je Rechenkette.

    Die eingestellte Threadzahl (``solver_threads``, 0 = alle Kerne bis auf
    einen) ist das **Budget des Rechners**, nicht das einer Kette. Bis zum
    22.09.2026 bekam jede Kette die volle Einstellung: beim Anwender stehen
    31 Threads in einstellungen.json, sechs Ketten forderten damit je 31 -
    MKL kappt nur innerhalb eines Prozesses auf die 16 physischen Kerne, also
    bis zu 96 Threads auf 16 Kernen (Nachpruefung der Loesersitzung). Ohne
    Einstellung wurde schon immer geteilt; jetzt auch mit.
    """
    budget = int(eingestellt or 0) or (parallel.cpu_count() - 1)
    return max(1, budget // max(1, int(ketten)))


def _log_einmal(text: str) -> None:
    """Denselben Hinweis nur einmal je Programmlauf schreiben - fuer die
    Konsole.

    warnings.warn erreicht weder das Protokollfenster der Oberflaeche noch
    die exe (dort werden Python-Warnungen nicht angezeigt). Der Anwender
    erfaehrt ein Ausweichen darum ueber das Ergebnis: ``res.info
    ["ausweichgrund"]`` (:func:`ausweich_info`), das Zusammenfassung und
    Bericht lesen (:func:`ausweichen_gebuendelt`), und ueber den Fortschritt
    (StaticSystem._loeser_merken, solve_modal)."""
    if text in _GEMELDET:
        return
    _GEMELDET.add(text)
    import warnings
    warnings.warn(text, RuntimeWarning, stacklevel=2)


def ausweichgruende_zaehlen(system) -> dict:
    """Stand der Loesungen mit ausgewichenem Loeser:
    (Grund, Ausweichloeser) -> Zahl.

    Vor einer Rechnung genommen, sagt :func:`ausweich_info` danach, welche
    Gruende genau diese Rechnung betrafen (StaticSystem._geloest zaehlt)."""
    return dict(getattr(system, "_ausweich_genutzt", None) or {})


def _ausweich_art(grund: str) -> str:
    """Art eines Ausweichgrunds: der Text ohne seine Zahlen.

    Der 32-Bit-Grund nennt Zeilen und Eintraege, und die aendern sich bei
    Kontakt von Schritt zu Schritt (inaktive Fugenbedingungen fallen heraus):
    am kippenden Block mit Reibung trug ein Lastfall "375 Zeilen, 19153
    Eintraege" und "376 Zeilen, 19903 Eintraege" (gemessen 23.09.2026 mit auf
    50 gesenkter Grenze). Das ist ein Grund, nicht zwei."""
    import re
    return re.sub(r"\d+", "#", grund)


def _ausweich_eintraege(paare) -> dict:
    """``res.info``-Eintraege aus (Grund, Ausweichloeser)-Paaren - je Art und
    Ausweichloeser ein Paar, der erste Text bleibt.

    ``ausweichen`` haelt die Paare fuer Zusammenfassung und Bericht,
    ``ausweichgrund`` den lesbaren Text, je Art einmal. Leer ohne Paare."""
    vereint: dict = {}
    for g, lo in paare:
        if g:
            vereint.setdefault((_ausweich_art(g), lo or ""), (g, lo or ""))
    if not vereint:
        return {}
    texte: dict = {}
    for g, _lo in vereint.values():
        texte.setdefault(_ausweich_art(g), g)
    return {"ausweichgrund": "; ".join(texte.values()), "ausweichen": list(vereint.values())}


def ausweich_paare(info: dict) -> list:
    """(Grund, Ausweichloeser)-Paare eines Ergebnisses; der Loeser ist leer,
    wenn nur der Text ``ausweichgrund`` vorliegt."""
    info = info or {}
    paare = info.get("ausweichen")
    if paare:
        return [(str(g), str(lo or "")) for g, lo in paare]
    grund = str(info.get("ausweichgrund") or "")
    return [(grund, "")] if grund else []


def ausweich_info(system, vorher: dict) -> dict:
    """``{"ausweichgrund": ..., "ausweichen": [...]}`` fuer ``Results.info`` -
    leer, wenn seit ``vorher`` keine Loesung mit einem ausgewichenen Loeser
    lief.

    Gezaehlt wird je **Loesung**, nicht je System. Die Grundfaktorisierung
    eines linearen Systems dient allen Lastfaellen - jeder, der mit ihr
    rechnet, traegt den Grund. Ein Kontaktmodell faktorisiert dagegen in jedem
    Schritt neu (am Drehlager 145-mal je Lastfall): scheitert PARDISO erst im
    dritten Lastfall, betrifft das die beiden davor nicht, und eine Marke am
    System hinge sie ihnen trotzdem an.

    Der Ausweichloeser kommt aus der Loesung selbst, nicht aus
    ``system.backend``: das ist der Loeser der **letzten** Faktorisierung.
    Scheitert PARDISO nur beim ersten von sieben Faktorisierungsversuchen
    eines Lastfalls, steht dort wieder "pardiso" (gemessen 23.09.2026 am Block
    mit Reibung, Probe des Gegenpruefers am Stand 4a8c464), und die
    Hinweiszeile nannte bis dahin PARDISO als den Loeser, der stattdessen
    rechnete."""
    jetzt = getattr(system, "_ausweich_genutzt", None) or {}
    vorher = vorher or {}
    return _ausweich_eintraege([k for k, n in jetzt.items() if n > vorher.get(k, 0)])


def ausweich_arten(ergebnisse) -> list:
    """Ausweichen ueber alle Ergebnisse, je Art des Grunds ein Eintrag
    ``{"grund", "namen", "loeser"}`` - Grundlage fuer
    :func:`ausweichen_gebuendelt` und den Anhang des Berichts.

    ``ergebnisse``: (Name, Results)-Paare. ``loeser`` sind die Loeser, auf die
    ausgewichen wurde. Zahlen im Grund zaehlen nicht zur Art
    (:func:`_ausweich_art`) - auch nicht, wenn ein Ergebnis mehrere Faelle
    derselben Art traegt."""
    arten: dict = {}
    for name, r in ergebnisse:
        info = getattr(r, "info", None) or {}
        for g, lo in ausweich_paare(info):
            e = arten.setdefault(_ausweich_art(g), {"grund": g, "namen": [], "loeser": []})
            # Die Paare eines Ergebnisses folgen aufeinander - derselbe Name
            # kaeme nur doppelt, wenn eine Art mit zwei Loesern auftrat
            if not e["namen"] or e["namen"][-1] != str(name):
                e["namen"].append(str(name))
            if lo and lo not in e["loeser"]:
                e["loeser"].append(lo)
    return list(arten.values())


def ausweichloeser_text(loeser) -> str:
    """Lesbare Namen der Loeser, auf die ausgewichen wurde."""
    return ", ".join(NAMEN.get(k, k) + (f" ({LOESER[k][3]})" if k in LOESER else "")
                     for k in loeser)


def ausweichen_gebuendelt(ergebnisse) -> list:
    """Je Art von Ausweichgrund **eine** Zeile ueber alle Ergebnisse - fuer
    die Hinweise des Berichts und die Zusammenfassung der Oberflaeche.

    ``ergebnisse``: (Name, Results)-Paare. Ohne Buendelung stuende derselbe
    Grund einmal je Ergebnis da, am Drehlager 422-mal. Die Zeile nennt den
    Loeser, auf den ausgewichen wurde (aus ``ausweichen``), nicht den der
    letzten Faktorisierung.
    """
    zeilen = []
    for e in ausweich_arten(ergebnisse):
        n = len(e["namen"])
        mit = ausweichloeser_text(e["loeser"])
        zeilen.append(
            f"Gleichungslöser ausgewichen bei {n} Ergebnis{'' if n == 1 else 'sen'} "
            f"({', '.join(e['namen'][:3])}{' …' if n > 3 else ''}): {e['grund']}"
            + (f" – stattdessen rechnete {mit}" if mit else "")
            + ". Den Grund beheben oder unter Berechnung → Einstellungen → "
              "Gleichungslöser einen Löser wählen; ein ausdrücklich gewählter Löser "
              "bricht ab, statt auszuweichen.")
    return zeilen


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


#: Die iparm-Eingabefelder, die nach der Faktorisierung mitgeschrieben werden,
#: so wie MKL sie zurueckgibt. pypardiso uebergibt ein Nullfeld (iparm(1) = 0,
#: MKL nimmt seine Vorgaben); danach steht darin, womit gerechnet wurde.
#: Gemessen 22.09.2026 am Dirichlet-Laplace mit 36 Zeilen, ein Thread:
#: 1: 1, 2: 3, 8: 2, 10: 13, 11: 1, 13: 1, 21: 0, 24: 0, 25: 0. Die
#: Ausgabefelder (7, 14-20, 22, 23, 30) gehoeren nicht dazu.
PARDISO_EINGABEFELDER = (1, 2, 8, 10, 11, 13, 21, 24, 25)


def _pardiso_kennzahlen(ps) -> dict:
    """Was MKL PARDISO bei der Faktorisierung getan hat, aus iparm - direkt
    nach ``ps.factorize`` zu lesen, vor jedem solve (der schreibt iparm neu).

    * ``gestoert`` = iparm(14): Zahl der angehobenen Pivots. Gemessen
      22.09.2026: Dirichlet-Laplace 0; mit einem entkoppelten Block
      [[1, 1], [1, 1]] (Pivot nach einem Eliminationsschritt exakt 0) 1; mit
      drei solchen Bloecken 3 (tests/test_loeser.py).
    * ``nnz`` = iparm(18): Nichtnullen des Faktors. Gemessen 20.09.2026 an
      einer Tridiagonalmatrix: n = 200 gibt 964, n = 400 gibt 1960 - linear,
      wie es fuer ein Band sein muss.
    * ``speicher_kb`` = iparm(15), (16), (17): Spitze der Analyse, dauerhaft
      aus der Analyse, Zahlenphase - in KB **laut MKL-Dokumentation**, nicht
      nachgemessen. iparm(17) steht direkt neben iparm(18) und ist leicht mit
      den Eintraegen zu verwechseln (28 bei der Tridiagonalmatrix n = 400).
    * ``eingabe``: die Felder PARDISO_EINGABEFELDER.

    ``get_iparms()`` zaehlt von 1. Leer, wenn iparm nicht lesbar ist.
    """
    try:
        ip = ps.get_iparms()
    except Exception:                                      # noqa: BLE001
        return {}

    def feld(i):
        try:
            return int(ip[i])
        except Exception:                                  # noqa: BLE001
            return None

    return {"gestoert": feld(14), "nnz": feld(18),
            "speicher_kb": {str(i): feld(i) for i in (15, 16, 17)},
            "speicher_einheit": "KB laut MKL-Dokumentation, nicht nachgemessen",
            "eingabe": {str(i): feld(i) for i in PARDISO_EINGABEFELDER}}


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
        #: Nur PARDISO: Matrixtyp (pypardiso rechnet mit 11, reell unsymmetrisch),
        #: angehobene Pivots (iparm(14)) und alle Kennzahlen aus
        #: _pardiso_kennzahlen. None bei den anderen Loesern - sie melden keine
        #: Zahl, und 0 hiesse "keiner angehoben".
        self.mtype = None
        self.gestoerte_pivots = None
        self.pardiso_kennzahlen = {}
        #: Warum der gewaehlte Loeser nicht rechnete, wenn auf einen anderen
        #: ausgewichen wurde - leer, wenn nicht. Steht in beschreibung() und
        #: damit im Fortschrittsstrom und im Protokoll.
        self.ausweichgrund = ""
        if self.n == 0:
            self._solve = lambda b: np.zeros_like(b)
            return
        K = K.tocsc()
        self._K = K.tocsr()
        passt = be in ("auto", "pardiso") and self._passt_in_int32(K, be == "pardiso")
        if be == "auto" and not passt:
            # Die 32-Bit-Grenze ist ebenso ein Ausweichgrund wie eine Ausnahme -
            # scheitert danach SuperLU, muss er in der Meldung stehen.
            self.ausweichgrund = (f"PARDISO: Gleichungssystem zu groß für die "
                                  f"32-Bit-Indizes ({self.n} Zeilen, "
                                  f"{int(getattr(K, 'nnz', 0) or 0)} Einträge)")
        if passt:
            try:
                _find_mkl()
                import pypardiso
                ps = pypardiso.PyPardisoSolver()
                _mkl_cbwr_festhalten(ps)         # nur beim ersten Mal
                # self._K ist bereits K.tocsr() (siehe oben). Ein zweites
                # tocsr() auf derselben Matrix kostete bei Drehlagergroesse
                # 0,280 s (475.935 Zeilen, 17,6 Mio. Nichtnullen, gemessen
                # 21.09.2026) - bei 145 Faktorisierungen je Lastfall 40,6 s,
                # ueber 422 Lastfaelle 4,75 Stunden. Beide lesen nur.
                Kcsr = self._K
                # Threadzahl aus den Einstellungen (0 = alle Kerne bis auf einen)
                self.threads = _mkl_threads_setzen(ps, threads_vorgabe("pardiso"))
                ps.factorize(Kcsr)
                # Direkt nach der Faktorisierung: solve schreibt iparm neu
                kz = _pardiso_kennzahlen(ps)
                self.pardiso_kennzahlen = kz
                self.nnz_faktor = int(kz.get("nnz") or 0)
                self.gestoerte_pivots = kz.get("gestoert")
                # pypardiso 0.4.7 fuehrt den Typ als ps.mtype. Fehlte das Feld,
                # liefe ein AttributeError in das except unten, und nur das
                # Mitschreiben liesse den Loeser ausweichen.
                mt = getattr(ps, "mtype", None)
                self.mtype = None if mt is None else int(mt)
                self._ps = ps
                self._solve = lambda b: ps.solve(Kcsr, b)
                self.backend = "pardiso"
            except Exception as ex:
                if be == "pardiso":
                    raise
                # Was PARDISO vor dem Scheitern eingetragen hat, gehoert nicht
                # dem Ersatz. Die Threadzahl setzt _mkl_threads_setzen schon vor
                # ps.factorize; ohne diese Zeilen nannten beschreibung() und der
                # Loeser-Nachweis SuperLU mit den Threads von PARDISO (gemessen
                # 22.09.2026 mit solver_threads = 2 und werfendem factorize:
                # Nachweis threads {"2": 1}, Zeile "1x SuperLU (2 Threads)").
                # SuperLU rechnet einkernig (test_superlu_nennt_sich_einkernig).
                self.threads = 1
                self.mtype = None
                self.gestoerte_pivots = None
                self.pardiso_kennzahlen = {}
                self.nnz_faktor = 0
                # **Nicht still verwerfen.** Bis zum 22.09.2026 fiel hier jede
                # PARDISO-Ausnahme ohne eine Zeile weg, und es ging ueber
                # CHOLMOD (meist nicht installiert) nach SuperLU. Am Drehlager
                # scheitert SuperLU dann selbst ("Can't expand MemType 0",
                # SystemError, gemessen von der Loesersitzung) - und der
                # eigentliche Grund, warum PARDISO nicht rechnete, war weg.
                self.ausweichgrund = f"PARDISO: {type(ex).__name__}: {str(ex)[:160]}"
                _log_einmal(f"PARDISO rechnete nicht ({self.ausweichgrund}) - "
                            "es wird auf einen anderen Löser ausgewichen.")
        if self._solve is None and be in ("auto", "cholmod"):
            try:
                from sksparse.cholmod import cholesky
                f = cholesky(K)
                self._solve = lambda b: f(b)
                self.backend = "cholmod"
            except ImportError:
                # CHOLMOD nicht installiert - der Regelfall, kein Ausweichgrund
                if be == "cholmod":
                    raise
            except Exception as ex:
                if be == "cholmod":
                    raise
                self.ausweichgrund = ((self.ausweichgrund + "; ") if self.ausweichgrund
                                      else "") + f"CHOLMOD: {type(ex).__name__}: {str(ex)[:120]}"
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
            # self._K ist schon CSR; _mumps wandelte die CSC sonst ein zweites
            # Mal um (bei Drehlagergroesse 0,280 s je Faktorisierung, gemessen
            # 21.09.2026 an einer Ersatzmatrix). tocsr() auf CSR kostet nichts.
            self._solve = self._mumps(self._K)
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
            Kc = self._K             # schon CSR - keine zweite Umwandlung
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
            try:
                lu = splu(K, permc_spec="MMD_AT_PLUS_A")
            except (RuntimeError, ValueError) as ex:
                # SuperLU meldet eine singulaere Matrix als RuntimeError - die
                # Deutung "Lagerung pruefen" des Aufrufers bleibt richtig; der
                # Grund des Ausweichens wird nur angehaengt.
                if self.ausweichgrund:
                    raise type(ex)(f"{ex} (vorher: {self.ausweichgrund})") from ex
                raise
            except Exception as ex:
                if not self.ausweichgrund:
                    raise
                raise LoeserAusfall(
                    f"Kein Gleichungslöser konnte die Matrix zerlegen: "
                    f"{self.ausweichgrund}; danach SuperLU: {type(ex).__name__}: "
                    f"{str(ex)[:160]}. SuperLU rechnet mit 32-Bit-Arbeitsfeldern "
                    "und reicht für große Modelle nicht - Berechnung → "
                    "Einstellungen → Gleichungslöser: MUMPS oder ama.") from ex
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
            f" (ausgewichen - {self.ausweichgrund})" if self.ausweichgrund else "") + (
            f", {self.threads} Threads" if self.threads > 1 else ", einkernig") + (
            f", Genauigkeit {grenze:g}" + (f" mit bis zu {n_max} Nachiterationen" if n_max else "")) + (
            f"; {frei} Freiheitsgrade ohne Halt (Ergebnis dort nicht eindeutig - Lagerung pruefen)"
            if frei else "") + zusatz

    def solve(self, b: np.ndarray, check: bool = True) -> np.ndarray:
        if self._solve is None:
            raise RuntimeError("Loeser ist freigegeben - erneut faktorisieren")
        b = np.asarray(b, float)
        # Das Residuum gehoert zu **dieser** Loesung. Ohne Pruefung (check=False,
        # mehrere rechte Seiten, b = 0) gibt es keins - dann nan statt der Zahl
        # der vorigen Loesung, die StaticSystem sonst diesem Lastfall
        # zuschriebe. Gelesen wird es nur vom Loeser-Nachweis (_LoeserBuch) und
        # von Tests; am Rechenweg haengt es nicht.
        self.residuum = float("nan")
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
                    # Der Grund des Ausweichens gehoert dazu, wie beim Scheitern
                    # der SuperLU-Faktorisierung ("(vorher: ...)"). Bis zum
                    # 23.09.2026 fehlte er in dieser Meldung (Nebenbefund 2).
                    # Ein Skript ohne Fortschritt sah ihn nur als RuntimeWarning
                    # von _log_einmal auf der Konsole (einmal je Programmlauf)
                    # - gemessen 24.09.2026 am Stand ec6448c mit den zwei
                    # Wuerfeln aus test_loeser, PARDISO zum Scheitern gebracht.
                    # Ins Protokollfenster kommt eine Warnung nicht (statik3d
                    # faengt warnings nirgends ab), und die exe hat keine
                    # Konsole (console=False in packaging/Statik3D.spec).
                    raise RuntimeError(
                        f"Gleichungssystem numerisch singulaer (Residuum {r:.1e}, Schranke {grenze:g}"
                        + (f", nach {schritte} Nachiterationen" if schritte else "") + ")"
                        + (f" (Löser ausgewichen - {self.ausweichgrund})" if self.ausweichgrund
                           else "") + " - "
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
    #: elem -> Elementmittel Integral sigma dV / V (6,) - linear in u, daher in
    #: Kombinationen exakt ueberlagerbar; das liest der Fehlerschaetzer
    #: (netzfehler.MITTELFELD). Seit 22.09.2026.
    solid_mittel: dict = field(default_factory=dict)
    #: Geglaettete Eckspannung je Knoten, Koerper und Werkstoff (siehe
    #: randspannung_knoten) - daraus liest der Nachweis (solid_rand). Seit 22.09.2026.
    solid_knoten: dict = field(default_factory=dict)
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
    def solid_rand(self) -> dict:
        """{Element: (Spannung (6,), Eckknoten)} - die geglaettete Spannung an der
        massgebenden Ecke des Elements (groesstes sigma_v unter seinen Eckknoten,
        gemittelt je Knoten, Koerper und Werkstoff; siehe randspannung_knoten).
        Leer, wenn der Loeser keine Knotenwerte gefuehrt hat."""
        if "solid_rand" not in self._cache:
            sk = self.solid_knoten or {}
            aus = {}
            frei: set = set()
            if sk and "spannung" in sk:
                m = self.model
                ng = max(1, len(sk["gruppen"]))
                pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]) * ng
                                                        + np.asarray(sk["gruppe"]))}
                grp = {g: j for j, g in enumerate(sk["gruppen"])}
                S = np.asarray(sk["spannung"], float)
                from . import spannungen as spn
                sv = spn.volumen_werte(S, "sv") if len(S) else np.zeros(0)
                for i in self.solid_res:
                    e = m.elements[i]
                    if e.typ not in sl.ECKEN_NATUERLICH:
                        continue
                    g = grp.get((str(getattr(e, "group", "")), str(e.mat)))
                    if g is None:
                        continue
                    nk = len(sl.ECKEN_NATUERLICH[e.typ])
                    js = [pos.get(int(n) * ng + g) for n in e.nodes[:nk]]
                    js = [j for j in js if j is not None]
                    if not js:
                        continue
                    j = max(js, key=lambda jj: sv[jj])
                    aus[i] = (S[j], int(sk["knoten"][j]))
                    if "frei" in sk and bool(sk["frei"][j]):
                        frei.add(i)
            self._cache["solid_rand"] = aus
            self._cache["solid_rand_frei"] = frei
        return self._cache["solid_rand"]

    @property
    def solid_rand_frei(self) -> set:
        """Elemente, deren Randspannung (solid_rand) an einem freien Knoten auf
        sigma n = 0 gezogen ist (rand_projizieren) - fuer die Beschriftung im
        Nachweis."""
        self.solid_rand
        return self._cache.get("solid_rand_frei", set())

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
            for i, v in (getattr(r, "solid_mittel", None) or {}).items():
                out.solid_mittel[i] = out.solid_mittel.get(i, 0.0) + f * v
            sk = getattr(r, "solid_knoten", None) or {}
            if sk:
                if not out.solid_knoten:
                    out.solid_knoten = {"knoten": sk["knoten"], "gruppe": sk["gruppe"],
                                        "gruppen": list(sk["gruppen"]),
                                        "spannung": f * np.asarray(sk["spannung"], float)}
                    if "frei" in sk:
                        out.solid_knoten["frei"] = np.asarray(sk["frei"], bool).copy()
                elif (len(sk["knoten"]) == len(out.solid_knoten["knoten"])
                      and np.array_equal(sk["knoten"], out.solid_knoten["knoten"])
                      and np.array_equal(sk["gruppe"], out.solid_knoten["gruppe"])):
                    out.solid_knoten["spannung"] = (out.solid_knoten["spannung"]
                                                    + f * np.asarray(sk["spannung"], float))
                    # Die freien Knoten haengen an den Lasten des Lastfalls
                    # (rand_projizieren): jeder Anteil ist fuer sich die beste
                    # Schaetzung, die Summe bleibt linear. "sigma n = 0" heisst
                    # ein Knoten der Summe nur, wenn er es in jedem Anteil war.
                    if "frei" in out.solid_knoten:
                        out.solid_knoten["frei"] = (out.solid_knoten["frei"]
                                                    & np.asarray(sk.get("frei", np.zeros(len(sk["knoten"]), bool)), bool))
                else:
                    # verschiedene Schluessel (andere Situation): nicht
                    # ueberlagerbar - lieber keine Randspannung als eine falsche
                    out.solid_knoten = {"verworfen": True}
        out.info = {"ndof": model.ndof, "superposition": True,
                    "factors": {r.name: f for r, f in parts}}
        # Eine Ueberlagerung besteht aus Loesungen - ist dort ausgewichen
        # worden, gilt das auch fuer sie (sonst nennte die Zusammenfassung
        # einer Kombination es nicht, obwohl jeder ihrer Lastfaelle es traegt).
        out.info.update(_ausweich_eintraege(
            [p for r, f in parts if f for p in ausweich_paare(r.info or {})]))
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
        # Die Situation gehoert in den Text, den Oberflaeche (Protokoll und
        # Zusammenfassung), Kommandozeile und Webserver zeigen: am Stand
        # b118805 stand sie nur in info['situation'], und die Zusammenfassung
        # eines Lastfalls mit abgebautem Lager sah aus wie eine der
        # Grundstellung (Gegenpruefung 24.09.2026, Balken der Pruefung
        # test_situationen: kein Wort zur Situation 'offen').
        sit = self.info.get("situation")
        if sit and sit != GRUNDSTELLUNG:
            s.append(f"Situation               : {sit}")
        s += [f"Freiheitsgrade gesamt   : {self.info.get('ndof', '?')}",
              f"davon aktiv             : {self.info.get('nfree', '?')}",
              f"Rechenzeit              : {self.info.get('time', 0):.3f} s"]
        if self.info.get("solver"):
            s.append(f"Gleichungsloeser        : {self.info['solver']}")
        # "Gleichungsloeser" darueber ist der Loeser der letzten
        # Faktorisierung - der Ausweichloeser steht darum hier dabei
        for g, lo in ausweich_paare(self.info):
            s.append(f"Löser ausgewichen       : {g}"
                     + (f" – stattdessen rechnete {ausweichloeser_text([lo])}" if lo else ""))
        if self.info.get("loeser_nachweis"):
            s.extend(loeser_nachweis_zeilen(self.info["loeser_nachweis"]))
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
class _LoeserBuch:
    """Was die Loesungen **eines Lastfalls** benutzt haben - der Loeser-Nachweis.

    Gezaehlt wird dort, wo geloest wird (StaticSystem._geloest), nicht nur
    beim Faktorisieren: ein Lastfall kann eine Faktorisierung benutzen, die
    vor ihm entstand. Ein lineares Modell faktorisiert beim Aufstellen des
    Systems, und die behaltene Kontaktfaktorisierung
    (StaticSystem._kontakt_loeser) ueberlebt den Wechsel des Lastfalls -
    eingefrorene Zustaende sind darauf gebaut. Ein Nachweis, der nur
    Faktorisierungen zaehlte, bliebe dort leer (Einwand der Gegenprobe zum
    Entwurf, 22.09.2026). Die Faktorisierungen des Lastfalls zaehlen getrennt.

    Nur Zaehlen und Lesen: kein Wert hier geht in eine Rechnung zurueck.
    """

    def __init__(self, zeit_vorher: float):
        self.zeit_vorher = float(zeit_vorher)
        self.loesungen: dict = {}            # Loeser -> Zahl der Loesungen
        self.threads: dict = {}              # wirksame Threads -> Zahl der Loesungen
        self.mtype: dict = {}                # PARDISO-Matrixtyp -> Zahl der Loesungen
        self.ausweichgruende: dict = {}      # Grund -> Zahl der Loesungen
        self.gescheitert = 0
        self.faktorisierungen = 0
        self.faktorisierungen_gestoert = 0
        self.gestoert_summe = None           # None: keine Faktorisierung meldete eine Zahl
        self.gestoert_max = None
        self.residuum_max = None
        self.residuum_gemessen = 0
        self.pardiso_eingabe = None

    @staticmethod
    def _zaehlen(d: dict, schluessel: str) -> None:
        d[schluessel] = d.get(schluessel, 0) + 1

    def _gestoert(self, ls):
        g = getattr(ls, "gestoerte_pivots", None)
        if g is not None:
            self.gestoert_max = max(int(g), self.gestoert_max or 0)
        return g

    def faktorisierung(self, ls) -> None:
        self.faktorisierungen += 1
        g = self._gestoert(ls)
        if g is not None:
            self.gestoert_summe = (self.gestoert_summe or 0) + int(g)
            self.faktorisierungen_gestoert += 1 if int(g) > 0 else 0

    def loesung(self, ls) -> None:
        self._zaehlen(self.loesungen, str(getattr(ls, "backend", "?")))
        self._zaehlen(self.threads, str(int(getattr(ls, "threads", 1) or 1)))
        mt = getattr(ls, "mtype", None)
        if mt is not None:
            self._zaehlen(self.mtype, str(int(mt)))
        grund = getattr(ls, "ausweichgrund", "")
        if grund:
            self._zaehlen(self.ausweichgruende, str(grund))
        self._gestoert(ls)
        r = getattr(ls, "residuum", None)
        if r is not None and np.isfinite(r):
            self.residuum_gemessen += 1
            self.residuum_max = float(r) if self.residuum_max is None else max(self.residuum_max, float(r))
        kz = getattr(ls, "pardiso_kennzahlen", None)
        if kz:
            self.pardiso_eingabe = dict(kz.get("eingabe") or {})

    def als_dict(self, zeit_jetzt: float) -> dict:
        return {"loesungen": dict(self.loesungen), "loesungen_gescheitert": self.gescheitert,
                "ausweichgruende": dict(self.ausweichgruende),
                "threads": dict(self.threads), "mtype": dict(self.mtype),
                "faktorisierungen": self.faktorisierungen,
                "faktorisierungen_mit_gestoerten_pivots": self.faktorisierungen_gestoert,
                "gestoerte_pivots_summe": self.gestoert_summe,
                "gestoerte_pivots_max": self.gestoert_max,
                # Differenz der Systemsumme: das System rechnet viele Lastfaelle
                "zeit_faktorisierung_lastfall": float(zeit_jetzt) - self.zeit_vorher,
                "residuum_linear_max": self.residuum_max,
                "residuum_gemessen": self.residuum_gemessen,
                "pardiso_eingabe": self.pardiso_eingabe,
                "mkl_cbwr": mkl_cbwr()}


def loeser_nachweis_zeilen(nw: dict) -> list:
    """Die Zeilen der Zusammenfassung zum Loeser-Nachweis eines Lastfalls:
    wer wie oft geloest hat, Ausweichen mit Grund, gestoerte Pivots - die
    beiden letzten nur, wenn es sie gab."""
    z = []
    loes = nw.get("loesungen") or {}
    if loes:
        thr = sorted(int(t) for t in (nw.get("threads") or {}))
        wie = ("einkernig" if thr == [1] else "/".join(str(t) for t in thr) + " Threads") if thr else ""
        mt = sorted(nw.get("mtype") or {})
        if mt:
            wie += (", " if wie else "") + "mtype " + "/".join(mt)
        text = ", ".join(f"{n}× {NAMEN.get(b, b)}" for b, n in loes.items())
        text += f" ({wie})" if wie else ""
        text += (f"; {int(nw.get('faktorisierungen', 0) or 0)} Faktorisierungen in "
                 f"{float(nw.get('zeit_faktorisierung_lastfall', 0.0) or 0.0):.3f} s")
        r = nw.get("residuum_linear_max")
        if r is not None:
            text += f"; Residuum höchstens {float(r):.1e}"
        z.append(f"Lösungen                : {text}")
    if nw.get("loesungen_gescheitert"):
        z.append(f"Gescheiterte Lösungen   : {int(nw['loesungen_gescheitert'])}")
    for grund, n in (nw.get("ausweichgruende") or {}).items():
        z.append(f"Ausgewichen             : {grund} ({n} Lösung{'' if n == 1 else 'en'})")
    summe, hoechst = nw.get("gestoerte_pivots_summe"), nw.get("gestoerte_pivots_max")
    if summe or hoechst:
        z.append(f"Gestörte Pivots         : {int(summe or 0)} in "
                 f"{int(nw.get('faktorisierungen_mit_gestoerten_pivots', 0) or 0)} von "
                 f"{int(nw.get('faktorisierungen', 0) or 0)} Faktorisierungen dieses Lastfalls, "
                 f"höchstens {int(hoechst or 0)} je benutzter Faktorisierung")
    return z


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
        #: Loesungen mit ausgewichenem Loeser, (Grund, Ausweichloeser) -> Zahl
        #: (_geloest zaehlt, ausweich_info liest je Ergebnis)
        self._ausweich_genutzt: dict = {}
        #: Loeser-Nachweis des laufenden Lastfalls (nachweis_beginnen) - None
        #: ausserhalb eines Lastfalls
        self._nachweis_buch = None
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
        # Ist ein Loeser ausgewichen, gehoert das in den Fortschritt - und zwar
        # auch bei den Faktorisierungen der Kontaktschritte, nicht nur bei der
        # Grundfaktorisierung, deren Zeile "Faktorisiert (...)" ihn schon
        # nennt. Einmal je System, nicht je Faktorisierung.
        grund = getattr(ls, "ausweichgrund", "")
        if grund and not getattr(self, "ausweichgrund", ""):
            self.ausweichgrund = grund
            fortschritt = getattr(self, "_progress", None)
            if fortschritt:
                _melde(fortschritt, f"Gleichungslöser ausgewichen - {grund}")
        buch = getattr(self, "_nachweis_buch", None)
        if buch is not None:
            buch.faktorisierung(ls)

    def nachweis_beginnen(self) -> None:
        """Den Loeser-Nachweis eines Lastfalls neu beginnen (_solve_loads).

        Ein Buch, das ein abgebrochener Lastfall offen liess, wird ersetzt -
        seine Zahlen gehoeren nicht zum naechsten."""
        self._nachweis_buch = _LoeserBuch(self.zeit_faktorisierung)

    def nachweis_abschliessen(self) -> Optional[dict]:
        """Den Loeser-Nachweis des Lastfalls als Woerterbuch; None, wenn keiner
        begonnen wurde. Danach zaehlt nichts mehr hinein."""
        buch, self._nachweis_buch = getattr(self, "_nachweis_buch", None), None
        return None if buch is None else buch.als_dict(self.zeit_faktorisierung)

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
                # Erst entscheiden, ob neu faktorisiert wird - dann bauen.
                # Kt und Ktff wurden bis zum 21.09.2026 in **jedem** Schritt
                # gebaut, obwohl Ktff nur unter `if neu:` gelesen wird und Kt
                # sonst nur bei Vorgabe. Am Drehlager waren das bei 150
                # Kontaktschritten je Lastfall 150 Matrixadditionen und 150
                # Zuschnitte ueber 17,6 Mio. Nichtnullen umsonst. Weder
                # `schluessel` noch `ls` noch `neu` haengen an Kt - die
                # Reihenfolge laesst sich also umstellen, ohne dass sich
                # sonst etwas aendert.
                schluessel = None if signatur is None else (signatur, self._rand, id(self._Vf))
                ls = getattr(self, "_kontakt_loeser", None)
                neu = schluessel is None or ls is None \
                    or schluessel != getattr(self, "_kontakt_signatur", None)
                Kt = (self.K + K_extra) if (neu or vorgabe) else None
                if vorgabe:
                    Ktfs = Kt[self.fi][:, self.si]
                    rhs = rhs - Ktfs @ u[self.si]
                if neu:
                    Ktff = Kt[self.fi][:, self.fi].tocsc()
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

        Hier zaehlt auch der Loeser-Nachweis des Lastfalls (_LoeserBuch): jede
        Loesung mit dem Loeser, der sie gerechnet hat.
        """
        # Jede Loesung mit einem ausgewichenen Loeser zaehlen - daraus liest
        # _solve_loads, ob **dieses** Ergebnis betroffen ist (ausweich_info).
        # Vor dem Loesen: auch ein Abbruch danach rechnete mit dem Ausweichloeser.
        # Mit dem Loeser dieser Loesung: self.backend ist nur der der letzten.
        grund = getattr(ls, "ausweichgrund", "")
        if grund:
            genutzt = self.__dict__.setdefault("_ausweich_genutzt", {})
            schluessel = (grund, str(getattr(ls, "backend", "") or ""))
            genutzt[schluessel] = genutzt.get(schluessel, 0) + 1
        m = self._rand
        buch = getattr(self, "_nachweis_buch", None)
        try:
            if not m:
                x = ls.solve(rhs)
            else:
                x = ls.solve(np.concatenate([rhs, np.zeros(m)]))
                x = np.asarray(x, float).ravel()[:len(rhs)]
        except BaseException:
            if buch is not None:
                buch.gescheitert += 1
            raise
        if buch is not None:
            buch.loesung(ls)
        return x

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
def zusatz_kenn(K_zusatz):
    """Kennung einer Zusatzmatrix fuer den Faktorisierungsschluessel.

    Sie muss **alles** erfassen, was die Matrix ausmacht: Form, Zahl der
    Nichtnullen, Werte **und Belegung**. Bis zum 21.09.2026 fehlte die
    Belegung - zwei Matrizen mit gleicher Form, gleicher Nichtnullzahl und
    bitgleichen Werten an **anderen** Stellen waren ununterscheidbar, und die
    alte Faktorisierung blieb stehen. Greifbar wird das bei baugleichen
    Staeben in ``solve_with_ausfall``: dieselben 144 Eintraege, andere Indizes.
    Am Drehlager nicht zu erwarten (die plastische Tangente aendert in jedem
    Newton-Schritt die Werte), an einem Fachwerk aus nur-Zug-Staeben sehr wohl.
    Gefunden von der Loesersitzung am Quelltext.

    Kosten: ein Hash ueber zwei weitere Felder je Aufruf.
    """
    if K_zusatz is None:
        return None
    K = K_zusatz.tocsr()
    return (tuple(K.shape), int(K.nnz),
            hash(np.ascontiguousarray(K.data).tobytes()),
            hash(np.ascontiguousarray(K.indices).tobytes()),
            hash(np.ascontiguousarray(K.indptr).tobytes()))


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
    # Sechsflaechner stapelweise: einzeln kostet stress_points 1375,5 µs je
    # Element - einundsiebzigmal so viel wie eine tet4-Spannung mit 18,2 µs
    # (21.09.2026). Zwei Drittel davon sind die acht Gausspunkte fuer die
    # inneren Freiheitsgrade, der Rest die neun Auswertepunkte; im Stapel
    # sind es 58,1 µs, Ergebnis identisch bis 2,5e-16. Am Drehlagernetz der
    # Vernetzersitzung waeren das 42,8 s -> 1,81 s je Nachlauf. Nachgemessen
    # 23.09.2026 (tests/messung_elementzeiten.py): einzeln 2 296 µs, im Stapel
    # 71,8 µs - beides seit dem 22.09.2026 mit Elementmittel und ueber den
    # Dehnungsoperator; der Einzelweg rechnet nur noch im Rueckfall.
    #
    # Seit dem 22.09.2026 fuer jeden Typ mit Dehnungsoperator (asm.STAPEL_TYPEN)
    # und aus **demselben** Operator wie Steifigkeit und Plastizitaet
    # (sl.spannungen_stapel). Dabei faellt das Elementmittel Integral
    # sigma dV / V mit ab: ``solid_mittel``, das der Fehlerschaetzer liest
    # (netzfehler.MITTELFELD) - bis dahin fuehrte der Loeser es nicht, und der
    # Schaetzer bekam fuer den elastischen hex8 das Eckmaximum.
    hex_vor: dict = {}
    mittel_vor: dict = {}
    je_werkstoff: dict = {}
    for i in idx:
        e = model.elements[i]
        if e.typ in asm.STAPEL_TYPEN:
            je_werkstoff.setdefault((e.typ, e.mat), []).append(i)
    for (typ, mat_name), liste in je_werkstoff.items():
        mat = model.materials[mat_name]
        for a0 in range(0, len(liste), asm.HEX8_STAPEL):
            teil = liste[a0:a0 + asm.HEX8_STAPEL]
            try:
                Us = np.asarray([u[asm.element_dofs(model.elements[j], model)] for j in teil], float)
                S, M = sl.spannungen_stapel(model, typ, teil, mat.E, mat.nu, Us)
                for j, sp, mm in zip(teil, S, M):
                    hex_vor[j] = sp
                    mittel_vor[j] = mm
            except Exception:         # noqa: BLE001 - dann rechnet die Schleife einzeln
                hex_vor = {k: v for k, v in hex_vor.items() if k not in teil}
                mittel_vor = {k: v for k, v in mittel_vor.items() if k not in teil}
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
            elif i in hex_vor:
                werte = [np.asarray(x, float) for x in hex_vor[i]]
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
            punkte = temp.get("plast_punkte") if isinstance(temp, dict) else None
            ecken_nr = sl.ecken_der_auswertepunkte(e.typ) if e.typ in sl.ECKEN_NATUERLICH else None
            if punkte and i in punkte:
                # Fliessende Elemente: die Spannung an den **Integrations-
                # punkten** (plastizitaet.punktspannungen), nicht an Mitte und
                # Ecken. Nur dort ist eps_p bekannt; an einer Ecke waechst eps
                # ueber die Punkte hinaus, eps_p bleibt zurueck, und die
                # gemeldete Spannung schoss ueber die Fliessflaeche (gemessen
                # 20.09.2026 am Reibblock: 2,93 MPa gegen die verfestigte
                # Grenze 1,42). Bis zum 22.09.2026 stand hier deshalb die
                # Mitte mit dem Mittel von D eps_p - beim Sechsflaechner unter
                # Biegung der schlechteste Ort (dort ist die Spannung null).
                # Jeder Punktwert liegt auf oder in der Fliessflaeche; massgebend
                # ist der groesste, und die Ecke nimmt den naechsten Punkt.
                xi_p, sig_p = punkte[i]
                rest = None
                if i in temp:
                    rest = sl.D_matrix(mat.E, mat.nu) @ (
                        mat.alpha * temp[i] * np.array([1.0, 1.0, 1.0, 0, 0, 0]))
                vor = (temp.get("sigma0_ohne_plastisch") or {}).get(i)
                if vor is not None:
                    rest = np.asarray(vor, float) if rest is None else rest + np.asarray(vor, float)
                werte_p = [np.asarray(x, float) - (0.0 if rest is None else rest) for x in sig_p]
                s_ = max(werte_p, key=sl.von_mises)
                if ecken_nr is not None and xi_p is not None:
                    en = np.asarray(sl.ECKEN_NATUERLICH[e.typ], float)
                    naechst = np.argmin(np.linalg.norm(en[:, None, :] - np.asarray(xi_p)[None], axis=2),
                                        axis=1)
                    ecken = np.array([werte_p[k] for k in naechst])
                else:
                    ecken = None
            else:
                if sig0 and i in sig0 and len(werte) > 1:
                    # Plastischer Zustand ohne Punktspannungen (etwa ein Typ ohne
                    # Dehnungsoperator): die Mitte, wie bis zum 22.09.2026
                    werte = werte[:1]
                s_ = werte[0] if len(werte) == 1 else max(werte, key=sl.von_mises)
                ecken = None
                if ecken_nr is not None:
                    ecken = np.array([werte[k] if k < len(werte) else werte[0] for k in ecken_nr])
            out.append((i, "solid", s_))
            if ecken is not None:
                out.append((i, "solid_ecken", ecken))
            # Elementmittel: beim Typ mit einem Punkt (tet4) ist es dieser
            # Punkt, sonst das Gewichtsmittel ueber die Integrationspunkte aus
            # dem Stapel - mit demselben Abzug (Temperatur, D eps_p).
            if i in mittel_vor:
                mm = np.asarray(mittel_vor[i], float)
                out.append((i, "solid_mittel", mm - abzug if abzug is not None else mm))
            elif len(werte) == 1 and e.typ not in asm.STAPEL_TYPEN:
                out.append((i, "solid_mittel", s_))
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


def randspannung_knoten(model: Model, ecken: dict) -> dict:
    """Die geglaettete Spannung an den Eckknoten der Volumenelemente: je
    Knoten, Koerper (Element.group) und Werkstoff das Mittel der Elementwerte
    an diesem Knoten.

    ``ecken`` ist {Element: (Ecken, 6)} in Knotenreihenfolge (solver.
    _post_chunk: elastisch das Elementfeld an der Ecke, fliessend der
    naechste Integrationspunkt). Rueckgabe {"knoten": (m,), "gruppe": (m,),
    "spannung": (m,6), "gruppen": [(Koerper, Werkstoff), ...]} - leer, wenn
    es keine Volumen gibt. Linear in u, also in Kombinationen exakt
    ueberlagerbar.

    Warum gemittelt wird, und warum je Koerper und Werkstoff (Auftrag A4/B6
    an die Element-Sitzung, 22.09.2026): Ein Element mit linearem Ansatz
    zeigt an seinen Ecken den Momentenverlauf versetzt - die Ecke zur
    Einspannung zu hoch, die andere zu niedrig. Am Kragarm-Pruefkoerper
    (Oberkante bei L/2, Soll 355 N/mm2) lag das bisherige Elementmaximum beim
    hex8 um +173 / +65 / +31 N/mm2 daneben (90 / 405 / 2295 FHG), beim tet10
    um +157 / +85 / +43; der Knotenmittelwert um -9,6 / +0,8 / +0,2 bzw.
    +14,2 / +4,0 (405 / 2295 FHG). Ueber eine Koerper- oder Werkstoffgrenze
    hinweg waere das Mittel falsch: die Spannung springt dort wirklich.
    """
    if not ecken:
        return {}
    knoten_l, gruppe_l, werte_l = [], [], []
    gruppen: dict = {}
    for i, S in ecken.items():
        e = model.elements[i]
        k = sl.knotenzahl(e.typ) if e.typ in sl.ECKEN_NATUERLICH else len(S)
        nk = len(sl.ECKEN_NATUERLICH.get(e.typ, S))
        g = gruppen.setdefault((str(getattr(e, "group", "")), str(e.mat)), len(gruppen))
        knoten_l.append(np.asarray(e.nodes[:nk], np.int64))
        gruppe_l.append(np.full(nk, g, np.int64))
        werte_l.append(np.asarray(S, float).reshape(nk, 6))
        del k
    kn = np.concatenate(knoten_l)
    gr = np.concatenate(gruppe_l)
    W = np.concatenate(werte_l)
    schluessel = kn * max(1, len(gruppen)) + gr
    einmalig, inv = np.unique(schluessel, return_inverse=True)
    summe = np.zeros((len(einmalig), 6))
    np.add.at(summe, inv, W)
    zahl = np.bincount(inv, minlength=len(einmalig)).astype(float)
    return {"knoten": einmalig // max(1, len(gruppen)), "gruppe": einmalig % max(1, len(gruppen)),
            "spannung": summe / zahl[:, None],
            "gruppen": [k for k, _v in sorted(gruppen.items(), key=lambda kv: kv[1])]}


# --------------------------------------------------------------------------
# Randspannung an freien Oberflaechen (Auftrag B6, 23.09.2026)
# --------------------------------------------------------------------------
#: Die Wege der Randspannung (Model.randspannung): "frei" (Vorgabe) projiziert
#: die geglaettete Knotenspannung an freien Oberflaechen auf sigma n = 0,
#: "gemittelt" laesst das Knotenmittel wie bis zum 23.09.2026.
RANDSPANNUNG_WEGE = ("frei", "gemittelt")
#: Normalen eines Knotens, die weniger als diesen Winkel [Grad] auseinander
#: liegen, gehoeren zu einer glatten Flaeche und werden gemittelt; mehr ist
#: eine Kante. 30 Grad liegen ueber der Facettierung eines Bogens (BOGENWINKEL
#: 18 Grad) und unter jeder gewollten Kante.
KANTENWINKEL = 30.0


def _nicht_freie_knoten(model: Model, faelle=None) -> np.ndarray:
    """Knoten, an denen sigma n **nicht** bekannt ist (bool, nn) - streng:

    * Lager aller Art, Kontaktlager, Spaltelemente, Kontaktpaare (Slave-Knoten,
      Master-Facetten, alle Knoten der Master-Elemente), Kopplungen,
      Starrkoerper, getrennte Fugenknoten, Lasteinleitungen, Punktmassen,
      Daempfer;
    * jede Last der wirkenden Lastfaelle ``faelle`` (None: aller): Knotenlasten,
      Zwangsverformungen und alle Knoten einer belasteten Seite. Eigengewicht,
      Temperatur und Vorspannung wirken im Volumen und lassen sigma n = 0 an
      der freien Oberflaeche stehen.

    Die Knoten der Nicht-Volumenelemente und die Grenzen zwischen Koerpern
    kommen aus _randnormalen bzw. aus der Knotentabelle (rand_projizieren).
    """
    nn = model.nn
    aus = np.zeros(nn, bool)

    def setze(knoten):
        k = np.asarray([int(x) for x in knoten if x is not None], np.int64)
        k = k[(k >= 0) & (k < nn)]
        if k.size:
            aus[k] = True
    for sp in model.supports:
        setze([sp.node])
    for grp in (model.line_supports, model.surface_supports):
        for x in grp:
            setze(x.nodes or [])
    for cs in getattr(model, "contact_supports", None) or []:
        setze([cs.node])
    for gp in getattr(model, "gap_elements", None) or []:
        setze([gp.node_a, gp.node_b])
    for cp in getattr(model, "contact_pairs", None) or []:
        setze(cp.slave_nodes or [])
        for f in cp.master_faces or []:
            setze(f or [])
        for i in cp.master_elements or []:
            if 0 <= int(i) < len(model.elements):
                setze(model.elements[int(i)].nodes)
    for kp in getattr(model, "kopplungen", None) or []:
        setze([kp.node_a, kp.node_b])
    for sk in getattr(model, "starrkoerper", None) or []:
        setze([sk.master] + list(sk.slaves or []))
    for paare in (getattr(model, "getrennte_knoten", None) or {}).values():
        setze([n for p in paare for n in p])
    for x in (getattr(model, "lasteinleitungen", None) or {}).values():
        setze([x.knoten])
    for pm in getattr(model, "punktmassen", None) or []:
        setze([pm.node])
    for dp in getattr(model, "daempfer", None) or []:
        setze([dp.node_a] + ([dp.node_b] if int(dp.node_b) >= 0 else []))
    namen = list(model.load_cases) if faelle is None else [f for f in faelle if f in model.load_cases]
    for name in namen:
        lc = model.load_cases[name]
        setze([l.node for l in lc.nodal_loads])
        setze([z.node for z in lc.zwangsverformungen])
        for fl in lc.face_loads:
            if not 0 <= int(fl.elem) < len(model.elements):
                continue
            e = model.elements[int(fl.elem)]
            seiten = sl.FLAECHEN.get(e.typ)
            if seiten is None or not 0 <= int(fl.face) < len(seiten):
                setze(e.nodes)
            else:
                setze([e.nodes[a] for a in seiten[int(fl.face)]])
    return aus


def _randnormalen(model: Model, aktiv=None) -> dict:
    """Die Randseiten der wirksamen Volumenelemente (Seiten, die genau einmal
    vorkommen) mit den aeusseren Normalen an ihren Ecken: {"knoten": (m,),
    "normale": (m,3), "flaeche": (m,), "element": (m,), "seite_knoten": (m,4)}
    - eine Zeile je (Randseite, Ecke), dazu "nicht_volumen" (bool, nn): die
    Knoten wirksamer Nicht-Volumenelemente (Stab, Schale, Feder, Spalt), an
    denen ein anderes Element Kraft einleitet. Die Normale kommt aus der
    Geometrie der Seite **an der Ecke** (tet10/hex20: aus der gekruemmten
    Seite), nach aussen ueber den Elementschwerpunkt.

    Vektorisiert je (Typ, Seite); rand_projizieren merkt sich das Ergebnis je
    Rechnung am StaticSystem - das Netz aendert sich nicht, ohne dass das
    System neu entsteht, und der Nachlauf laeuft je Lastfall."""
    X = np.asarray(model.nodes, float)
    nn = model.nn
    nicht_volumen = np.zeros(nn, bool)
    je_typ: dict = {}
    for i, e in enumerate(model.elements):
        if aktiv is not None and not aktiv[i]:
            continue
        if e.typ in sl.ECKEN_NATUERLICH:
            je_typ.setdefault(e.typ, []).append(i)
        else:
            k = np.asarray(e.nodes, np.int64)
            nicht_volumen[k[(k >= 0) & (k < nn)]] = True
    schl, herkunft = [], []          # herkunft: (typ, seite, Elementfeld, Knotenfeld)
    for typ, idx in je_typ.items():
        idx = np.asarray(idx, np.int64)
        conn = np.asarray([model.elements[i].nodes for i in idx], np.int64)
        for s, f in enumerate(sl.FLAECHEN_ECKEN[typ]):
            ecken = np.sort(conn[:, list(f)], axis=1)
            if ecken.shape[1] < 4:
                ecken = np.hstack([np.full((len(idx), 4 - ecken.shape[1]), -1, np.int64), ecken])
            schl.append(ecken)
            herkunft.append((typ, s, idx, conn))
    leer = {"knoten": np.zeros(0, np.int64), "normale": np.zeros((0, 3)), "flaeche": np.zeros(0),
            "element": np.zeros(0, np.int64), "seite_knoten": np.zeros((0, 4), np.int64),
            "nicht_volumen": nicht_volumen}
    if not schl:
        return leer
    # Zeilen als ein Void-Wert vergleichen: np.unique(axis=0) sortiert
    # zeilenweise und war hier der groesste Posten
    K = np.ascontiguousarray(np.vstack(schl))
    _u, inv, zahl = np.unique(K.view(np.dtype((np.void, K.dtype.itemsize * K.shape[1]))).ravel(),
                              return_inverse=True, return_counts=True)
    einmal = zahl[inv.ravel()] == 1
    kn_l, nv_l, fl_l, el_l, sk_l = [], [], [], [], []
    a0 = 0
    for (typ, s, idx, conn), ecken in zip(herkunft, schl):
        sel = einmal[a0:a0 + len(idx)]
        a0 += len(idx)
        if not sel.any():
            continue
        seite = list(sl.FLAECHEN[typ][s])
        k = len(seite)
        cb = conn[sel]
        P = X[cb[:, seite]]                                    # (m, k, 3)
        nk = len(sl.ECKEN_NATUERLICH[typ])
        mitte = X[cb[:, :nk]].mean(axis=1)                     # (m, 3)
        GP, W = sl._SEITEN_GAUSS[k]
        A = np.zeros(len(cb))
        for (a, b), w in zip(GP, W):
            _N, dN = sl.seite_N_dN(k, a, b)
            t1 = np.einsum("mkd,k->md", P, dN[:, 0])
            t2 = np.einsum("mkd,k->md", P, dN[:, 1])
            A += w * np.linalg.norm(np.cross(t1, t2), axis=1)
        eckzahl = 3 if k in (3, 6) else 4
        for c in range(eckzahl):
            a, b = ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))[c] if eckzahl == 3 else sl._QUAD_SIGNS[c]
            N, dN = sl.seite_N_dN(k, a, b)
            t1 = np.einsum("mkd,k->md", P, dN[:, 0])
            t2 = np.einsum("mkd,k->md", P, dN[:, 1])
            n = np.cross(t1, t2)
            ln = np.linalg.norm(n, axis=1)
            gut = ln > 0.0
            n = n[gut] / ln[gut, None]
            lage = np.einsum("mkd,k->md", P[gut], N) - mitte[gut]
            n[np.einsum("md,md->m", n, lage) < 0.0] *= -1.0
            kn_l.append(cb[gut][:, seite[c]])
            nv_l.append(n)
            fl_l.append(A[gut])
            el_l.append(idx[sel][gut])
            sk_l.append(ecken[sel][gut])
    return {"knoten": np.concatenate(kn_l), "normale": np.vstack(nv_l), "flaeche": np.concatenate(fl_l),
            "element": np.concatenate(el_l), "seite_knoten": np.vstack(sk_l),
            "nicht_volumen": nicht_volumen}


def _projektor_frei(normalen: list) -> np.ndarray:
    """Die lineare Abbildung P (6,6) auf Voigt-Spannungen, die sigma auf
    sigma n_i = 0 fuer alle Normalen n_i zieht, mit der kleinsten Aenderung im
    Frobenius-Mass (Schubanteile zaehlen doppelt). Eine Normale ergibt
    sigma' = sigma - n (x) r - r (x) n + (n . r) n (x) n mit r = sigma n; zwei
    oder drei (Kante, Ecke) werden **gleichzeitig** erfuellt, nicht
    nacheinander."""
    C = []
    for n in normalen:
        x, y, z = n
        # (sigma n) in Voigt xx, yy, zz, xy, yz, xz
        C.append([x, 0, 0, y, 0, z])
        C.append([0, y, 0, x, z, 0])
        C.append([0, 0, z, 0, y, x])
    C = np.asarray(C, float)
    Wi = np.diag([1.0, 1.0, 1.0, 0.5, 0.5, 0.5])
    M = C @ Wi @ C.T
    return np.eye(6) - Wi @ C.T @ np.linalg.pinv(M, rcond=1e-10) @ C


def _projiziere_glatt(S: np.ndarray, n: np.ndarray) -> np.ndarray:
    """sigma' = sigma - n (x) r - r (x) n + (n . r) n (x) n, r = sigma n, fuer
    einen Stapel Voigt-Spannungen S (m,6) und Normalen n (m,3)."""
    T = np.empty((len(S), 3, 3))
    T[:, 0, 0], T[:, 1, 1], T[:, 2, 2] = S[:, 0], S[:, 1], S[:, 2]
    T[:, 0, 1] = T[:, 1, 0] = S[:, 3]
    T[:, 1, 2] = T[:, 2, 1] = S[:, 4]
    T[:, 0, 2] = T[:, 2, 0] = S[:, 5]
    r = np.einsum("mij,mj->mi", T, n)
    nr = np.einsum("mi,mi->m", n, r)
    T = (T - np.einsum("mi,mj->mij", n, r) - np.einsum("mi,mj->mij", r, n)
         + nr[:, None, None] * np.einsum("mi,mj->mij", n, n))
    return np.column_stack([T[:, 0, 0], T[:, 1, 1], T[:, 2, 2], T[:, 0, 1], T[:, 1, 2], T[:, 0, 2]])


def rand_projizieren(model: Model, sk: dict, aktiv=None, faelle=None, merker: dict = None,
                     fliessend=None) -> dict:
    """Die geglaettete Knotenspannung ``sk`` (randspannung_knoten) an freien
    Oberflaechen auf sigma n = 0 ziehen; setzt sk["frei"] (bool je Zeile).
    ``faelle``: die wirkenden Lastfaelle (deren Lasten sperren Knoten), None =
    alle. ``merker``: ein dict, in dem die Randseiten fuer diese Rechnung
    liegen bleiben (postprocess gibt das des StaticSystem). ``fliessend``:
    Elemente mit plastischem Zustand - ihre Knoten bleiben, wie sie sind: dort
    begrenzt die Fliessflaeche die Spannung, und die Projektion aendert den
    Deviator. Am Balken mit einer hex8-Lage unter 1,20 M_el schob sie die
    Randfaser auf 251,6 N/mm2, ueber die verfestigte Fliessgrenze 236,3
    (tests/test_volumen.py, test_randspannung_fliessend, 23.09.2026).

    Warum (gemessen 23.09.2026, tests/test_randspannung.py): das Knotenmittel
    am Rand mischt die Spannung der Randelemente mit der ihres Inneren, auch
    in den Komponenten, die der Rand kennt. Am Kirsch-Loch (Zug, freier
    Lochrand, halbe Dicke bei 90 Grad) lag der hex8 bei 4 455 FHG 14,7 N/mm2
    daneben, auf sigma n = 0 gezogen 1,1; der tet10 bei 29 835 FHG 5,8 statt
    4,2, der tet4 bei 16 575 FHG 24 statt 15. Unter Biegung an der ebenen
    freien Seite (Kragarm) aendert es fast nichts: dort sind die
    Randkomponenten schon fast null.

    Projiziert wird nur ein Knoten, der in genau einem Koerper liegt, selbst
    frei ist und dessen Randseiten alle frei sind (eine Seite mit einem nicht
    freien Knoten ist nicht frei; _nicht_freie_knoten, _randnormalen). Glatte
    Flaeche (alle Normalen innerhalb KANTENWINKEL um ihr Mittel): eine
    Normale, flaechengewichtet gemittelt. Kante oder Ecke: die Normalen
    buendeln und alle gleichzeitig erfuellen, aber nur, wenn sie **konvex**
    ist - an einer einspringenden Kante ist die Spannung singulaer, und die
    Projektion wuerde den Kerbgrund schoenen. Linear in der Spannung: fuer
    feste freie Knoten in Kombinationen exakt ueberlagerbar.
    """
    if not sk or "spannung" not in sk or not len(sk["knoten"]):
        return sk
    knoten = np.asarray(sk["knoten"], np.int64)
    frei = np.zeros(len(knoten), bool)
    sk["frei"] = frei
    merker = {} if merker is None else merker
    # je wirksamer Elementmenge (Ausfallstaebe schalten je Lastfall ab)
    schluessel = None if aktiv is None else hash(np.asarray(aktiv, bool).tobytes())
    alt = merker.get("randnormalen")
    if alt is not None and alt[0] == schluessel:
        rn = alt[1]
    else:
        rn = _randnormalen(model, aktiv)
        merker["randnormalen"] = (schluessel, rn)
    if not len(rn["knoten"]):
        return sk
    nicht = _nicht_freie_knoten(model, faelle) | rn["nicht_volumen"]
    for i in (fliessend or ()):
        if 0 <= int(i) < len(model.elements):
            k = np.asarray(model.elements[int(i)].nodes, np.int64)
            nicht[k[(k >= 0) & (k < model.nn)]] = True
    # Grenze zweier Koerper oder Werkstoffe: der Knoten steht mehrfach in der Tabelle
    u_kn, zahl = np.unique(knoten, return_counts=True)
    nicht[u_kn[zahl > 1]] = True
    # Eine Seite mit einem nicht freien Knoten ist nicht frei - alle ihre Knoten fallen raus
    sk4 = rn["seite_knoten"]
    schlecht_seite = np.any(np.where(sk4 >= 0, nicht[np.maximum(sk4, 0)], False), axis=1)
    gesperrt = nicht.copy()
    gesperrt[rn["knoten"][schlecht_seite]] = True
    zeilen = np.flatnonzero(~gesperrt[rn["knoten"]])
    if not len(zeilen):
        return sk
    kn = rn["knoten"][zeilen]
    nv = rn["normale"][zeilen] * rn["flaeche"][zeilen, None]
    einz, inv = np.unique(kn, return_inverse=True)
    inv = inv.ravel()
    mittel = np.zeros((len(einz), 3))
    np.add.at(mittel, inv, nv)
    ln = np.linalg.norm(mittel, axis=1)
    ok = ln > 0.0
    mittel[ok] /= ln[ok, None]
    cos_zeile = np.einsum("md,md->m", rn["normale"][zeilen], mittel[inv])
    cos_min = np.ones(len(einz))
    np.minimum.at(cos_min, inv, cos_zeile)
    glatt = ok & (cos_min >= np.cos(np.radians(KANTENWINKEL)))
    S = np.asarray(sk["spannung"], float).copy()
    j = np.searchsorted(knoten, einz)
    da = (j < len(knoten))
    da[da] = knoten[j[da]] == einz[da]
    g = glatt & da
    if g.any():
        S[j[g]] = _projiziere_glatt(S[j[g]], mittel[g])
        frei[j[g]] = True
    # Kanten und Ecken einzeln: buendeln, Konvexitaet pruefen, gleichzeitig projizieren
    X = np.asarray(model.nodes, float)
    cos_kante = np.cos(np.radians(KANTENWINKEL))
    for q in np.flatnonzero(~glatt & da & ok):
        n = int(einz[q])
        zs = zeilen[inv == q]
        buendel: list = []
        for z in zs[np.argsort(-rn["flaeche"][zs])]:
            v = rn["normale"][z] * rn["flaeche"][z]
            for b in buendel:
                if np.dot(b / np.linalg.norm(b), rn["normale"][z]) >= cos_kante:
                    b += v
                    break
            else:
                buendel.append(v.copy())
        normalen = [b / np.linalg.norm(b) for b in buendel]
        els = {int(i) for i in rn["element"][zs]}
        mitten = [X[list(model.elements[i].nodes)].mean(axis=0) - X[n] for i in els]
        if any(np.dot(c, m) > 0.0 for c in normalen for m in mitten):
            continue                    # einspringend: nicht anfassen
        S[j[q]] = _projektor_frei(normalen) @ S[j[q]]
        frei[j[q]] = True
    sk["spannung"] = S
    return sk


def postprocess(model: Model, u: np.ndarray, res: Results, feq: dict = None,
                q: dict = None, temp: dict = None, workers: int = None, aktiv=None,
                system=None):
    """Rohgroessen je Element aus dem Verschiebungsvektor u (ndof,).
    Abgeschaltete Elemente (``aktiv`` False) bekommen Nullen: sie wirken nicht."""
    feq = feq if feq is not None else {}
    q = q if q is not None else {}
    temp = temp if temp is not None else {}
    idx = asm.aktive_indizes(model, aktiv)
    ev = (asm.knotendilatation_je_element(model, u, aktiv)
          if getattr(model, "knotendilatation", False) else None)
    ecken: dict = {}
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
                res.solid_mittel[i] = np.zeros(6)
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
        elif kind == "solid_mittel":
            res.solid_mittel[i] = val
        elif kind == "solid_ecken":
            ecken[i] = val
        else:
            res.solid_res[i] = val
    res.solid_knoten = randspannung_knoten(model, ecken)
    weg = str(getattr(model, "randspannung", "frei") or "frei")
    if weg == "frei" and res.solid_knoten:
        faktoren = res.info.get("factors")
        faelle = [n for n, f in faktoren.items() if f] if isinstance(faktoren, dict) else None
        merker = None
        if system is not None:
            merker = getattr(system, "_randspannung_merker", None)
            if merker is None:
                merker = {}
                try:
                    system._randspannung_merker = merker
                except AttributeError:
                    merker = None
        fliessend = list((temp.get("plast_punkte") or {}).keys()) if isinstance(temp, dict) else None
        rand_projizieren(model, res.solid_knoten, aktiv, faelle, merker, fliessend)
        res.info["randspannung"] = (f"geglättet, an freien Oberflächen σ·n = 0 "
                                    f"({int(np.sum(res.solid_knoten.get('frei', [])))} Knoten)")
    elif res.solid_knoten:
        res.info["randspannung"] = "geglättet (Knotenmittel)"
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


def _nichtlinear(model, ausfall: bool = None) -> bool:
    """Kombinationen direkt rechnen statt ueberlagern: bei Kontakt, bei
    Fliessen (plastische Dehnungen ueberlagern sich nicht, 17.09.2026) - und
    bei **Ausfallstaeben und Seilen**.

    Der dritte Fall fehlte bis zum 22.09.2026, obwohl das Modell ihn seit
    jeher kennt (``Model.hat_ausfallstaebe``) und der Loeser ihn an zwei
    anderen Stellen abfragt. Ein Zug- oder Druckstab, ein Seil oder eine
    ausfallende Feder aendert seine Aktivmenge mit der Last: jeder Lastfall
    wurde mit einer **anderen** Menge tragender Staebe gerechnet, und die
    Summe solcher Ergebnisse steht in keinem Gleichgewicht eines wirklichen
    Zustands. Schnittgroessen, Verformungen und Auflagerkraefte jeder
    Kombination waren damit falsch - ohne jede Meldung.

    ``ausfall`` nimmt die Antwort entgegen, wenn sie schon bekannt ist:
    ``hat_ausfallstaebe`` laeuft ueber alle Elemente (4,5 ms bei 67.500,
    gemessen 22.09.2026), und diese Funktion wird je Kombination gerufen. Bei
    Kontakt oder Fliessen faellt der Durchlauf ohnehin weg, weil ``or``
    kurzschliesst - teuer waere nur das lineare Modell, und genau dort gibt
    ``solve_combinations`` die Antwort einmal mit.
    """
    if model.has_contact or _plastisch(model):
        return True
    return bool(model.hat_ausfallstaebe() if ausfall is None else ausfall)


def _laufbuch_eintrag(nr: int, cinfo: dict, art: str = "", start_von_lauf=None) -> dict:
    """Ein Eintrag des Laufbuchs (``res.info['laeufe']``) aus dem ``cinfo``
    **eines** Kontaktlaufs - vor jeder Summierung gebaut.

    ``start_von_lauf``: Nummer des Laufs desselben Lastfalls, dessen
    Kontaktzustand der Start war; 0 = der Start, der dem Lastfall angeboten
    wurde (res.info['start_angeboten_von']); None = ohne Start (kalt).
    Ob der Start angenommen wurde, sagt ``warm``."""
    lauf = dict(cinfo.get("contact_lauf") or {})
    konvergiert = bool(cinfo.get("contact_converged", True))
    grund = lauf.get("grund")
    if grund is None:
        # Ein cinfo ohne Laufangaben (Einheitstest, aelterer Stand): der
        # Grund ist unbekannt, aber leer darf er nur bei Konvergenz sein
        grund = "" if konvergiert else "unbekannt"
    return {"nr": int(nr), "art": str(art or ""),
            "schritte": int(cinfo.get("contact_iterations", 0) or 0),
            "faktorisierungen": int(cinfo.get("contact_factorisations", 0) or 0),
            "konvergiert": konvergiert, "grund": str(grund),
            "warm": bool(cinfo.get("contact_warm", False)),
            "neustart": bool(lauf.get("neustart", False)),
            "start_von_lauf": start_von_lauf,
            "zyklen": lauf.get("zyklen"), "phase": lauf.get("phase"),
            "n_aktiv": lauf.get("n_aktiv"), "n_gleitet": lauf.get("n_gleitet"),
            "runden": list(lauf.get("runden") or []),
            "endzustand_kennung": lauf.get("endzustand_kennung"),
            "u_max": lauf.get("u_max")}


def _kontakt_info_sammeln(res, cinfo: dict, art: str = "", start_von_lauf=None) -> dict:
    """Die Kennzahlen des Kontakts aufaddieren statt ueberschreiben.

    Mit Plastizitaet loest derselbe Lastfall viele Male - am Drehlager 18
    Schritte in drei Laststufen. ``res.info.update(cinfo)`` liess davon nur
    die Zahlen des **letzten** Laufes stehen: die Zusammenfassung meldete
    "Kontakt-Iterationen: 2" fuer eine Rechnung von 2289 s, und die
    Kontaktmeldungen der frueheren Schritte (etwa "Nachpruefung der Reibung
    nach 40 Zustandswechseln abgebrochen") fielen ganz weg (19.09.2026).
    "Nicht konvergiert" klebt: ein einziger gekappter Lauf zaehlt.

    **Laufbuch** (22.09.2026): jeder Kontaktlauf bekommt einen eigenen
    Eintrag in ``res.info['laeufe']`` (siehe :func:`_laufbuch_eintrag`),
    gebaut **vor** der Summierung und nie zusammengefasst. Die Summen oben
    sagen nicht, welcher der zwoelf Laeufe am Drehlager gedeckelt war und ob
    der letzte - aus dem u und sigma stammen - dabei ist. Die Kennzahlen
    ``contact_laeufe``, ``contact_letzter_lauf_konvergiert`` und
    ``contact_laeufe_nicht_konvergiert`` werden aus dem Laufbuch abgeleitet.
    ``art`` und ``start_von_lauf`` gibt ``_solve_loads`` mit.
    """
    alte = list(res.info.get("laeufe") or [])
    eintrag = _laufbuch_eintrag(len(alte) + 1, cinfo, art, start_von_lauf)
    cinfo.pop("contact_lauf", None)     # steht jetzt im Eintrag, nicht als Einzelwert
    for k in ("contact_iterations", "contact_factorisations"):
        if k in cinfo:
            cinfo[k] = int(res.info.get(k, 0) or 0) + int(cinfo[k] or 0)
    laeufe = alte + [eintrag]
    cinfo["laeufe"] = laeufe
    lauf = eintrag["nr"]
    cinfo["contact_laeufe"] = len(laeufe)
    dieser = eintrag["konvergiert"]
    cinfo["contact_converged"] = bool(res.info.get("contact_converged", True)) and dieser
    # **Welcher Lauf, und war es der letzte?** Die Meldung "Nachpruefung der
    # Reibung ... abgebrochen" nannte keinen Lauf und wurde unten mit den
    # gleichlautenden der anderen Laeufe zu EINER Zeile zusammengefasst. Eine
    # Zeile konnte fuer 1 bis 12 gekappte Laeufe stehen, und ob der letzte
    # dabei war - aus dem u und sigma stammen -, liess sich hinterher nicht
    # mehr sagen (am Drehlager genau so geschehen; Nachpruefung der
    # Loesersitzung vom 22.09.2026). Die Abbruchzeile traegt jetzt ihren
    # Lauf und wird nicht zusammengefasst.
    cinfo["contact_letzter_lauf_konvergiert"] = laeufe[-1]["konvergiert"]
    cinfo["contact_laeufe_nicht_konvergiert"] = sum(1 for e in laeufe if not e["konvergiert"])
    abbruch = cinfo.get("contact_abbruch")
    eigene = [f"{z} (Kontaktlauf {lauf})" if abbruch and z == abbruch else z
              for z in (cinfo.get("contact_log") or [])]
    alt_log = list(res.info.get("contact_log", []) or [])
    neu_log = [z for z in eigene if z not in alt_log]
    cinfo["contact_log"] = alt_log + neu_log
    return cinfo


def _fliessarten(info: dict, einst) -> list:
    """Die Art jedes Loeseraufrufs von ``plastizitaet.iteration`` als Liste
    (Art, Laststufe, Schritt) - nachgezeichnet aus ``info['verlauf']``, ohne
    die Signatur von iteration zu aendern (sie wird aus Tests mit einem
    einfachen ``loesen`` gerufen).

    Newton (``_newton``): je Laststufe ein Aufruf zu Beginn ("Laststufe"),
    dann je Schritt, der die Toleranz noch verfehlt, einer ("Newton"); zum
    Schluss einer ("Abschluss"). Anfangsdehnung: je Schritt ein Aufruf, der
    erste einer Laststufe heisst "Laststufe", die weiteren "Fliessschritt".
    Ohne Volumenelemente ruft iteration einmal: "Abschluss"."""
    verlauf = list(info.get("verlauf") or [])
    if not verlauf:
        return [("Abschluss", None, None)]
    stufen = int(info.get("laststufen", 1) or 1)
    tol = float(einst.toleranz)
    newton = info.get("verfahren") == "tangente"
    arten = []
    for k in range(1, stufen + 1):
        schritte = [v for v in verlauf if v[0] == k]
        if newton:
            arten.append(("Laststufe", k, 0))
            # iteration bricht beim ersten diff <= tol ab, ohne zu loesen;
            # "not <=" wie dort, damit auch ein NaN genauso zaehlt
            arten.extend(("Newton", k, int(it)) for (_k, it, diff, _n) in schritte
                         if not (diff <= tol))
        else:
            arten.extend(("Laststufe" if it == 1 else "Fliessschritt", k, int(it))
                         for (_k, it, _d, _n) in schritte)
    arten.append(("Abschluss", None, None))
    return arten


def _fliessarten_eintragen(res, info: dict, einst, aufrufe: list) -> None:
    """Die vorlaeufige Art "Fliessen" der Laufbuch-Eintraege durch die
    nachgezeichnete ersetzen. Passt die Zahl der Aufrufe nicht - oder traegt
    ein Aufruf eine Tangente, wo keiner eine haben kann -, bleibt es bei
    "Fliessen": eine falsche Zuordnung waere schlimmer als eine grobe."""
    try:
        arten = _fliessarten(info, einst)
    except Exception:                  # noqa: BLE001 - Buchfuehrung darf nie die Rechnung kosten
        return
    if len(arten) != len(aufrufe):
        return
    if any(tang and art != "Newton" for (_i, tang), (art, _k, _s) in zip(aufrufe, arten)):
        return
    laeufe = res.info.get("laeufe") or []
    for (i, tang), (art, k, s) in zip(aufrufe, arten):
        if i is not None and 0 <= i < len(laeufe):
            laeufe[i].update({"art": art, "stufe": k, "schritt": s, "tangente": bool(tang)})


def _plastizitaet_rechnen(model, res, F, rechnen, aktiv, temp, progress, start):
    """Fliessen der Volumen (plastizitaet.iteration) um den linearen
    Loesungsweg eines Lastfalls: jede Loesung ist derselbe Lastfall mit der
    Zusatzlast F_p, mit Kontakt warm gestartet vom letzten Zustand.
    Rueckgabe (u, R, aktiv, temp); temp["sigma0"] traegt D eps_p, damit der
    Spannungsnachlauf sigma = D eps - D eps_p rechnet."""
    from . import plastizitaet as pl
    halter = {"start": start, "R": None, "aktiv": aktiv}
    aufrufe: list = []      # je Loeseraufruf (Index im Laufbuch oder None, mit Tangente)

    def loesen(Fg, dK=None):
        vor = len(res.info.get("laeufe") or [])
        u_, R_, a_ = rechnen(Fg, halter["start"], dK)
        nach = len(res.info.get("laeufe") or [])
        aufrufe.append((vor if nach == vor + 1 else None, dK is not None))
        halter["R"], halter["aktiv"] = R_, a_
        if getattr(res, "kontaktzustand", None) is not None:
            halter["start"] = res.kontaktzustand
        return u_

    log: list = []
    u, zustand, F_p, info = pl.iteration(model, F, loesen, model.plastizitaet, aktiv, log=log,
                                         progress=lambda t: _melde(progress, t),
                                         loesen_tangente=loesen)
    _fliessarten_eintragen(res, info, model.plastizitaet, aufrufe)
    if not isinstance(temp, dict):
        temp = {}
    sig0 = temp.setdefault("sigma0", {})
    # Was vor dem Fliessen in sigma0 stand, ist Vorspannung - die Spannungen
    # an den Integrationspunkten (unten) rechnen eps_p selbst ab und brauchen
    # nur diesen Rest
    temp["sigma0_ohne_plastisch"] = {i: np.array(v, float, copy=True) for i, v in sig0.items()}
    for i, s0 in pl.sigma0_je_element(model, zustand).items():
        sig0[i] = np.asarray(sig0.get(i, 0.0), float) + s0
    temp["plast_punkte"] = pl.punktspannungen(model, u, zustand)
    for z in log:
        _melde(progress, z)
    res.info["plastizitaet"] = {k: v for k, v in info.items() if k != "verlauf"}
    res.info["plastizitaet"]["log"] = list(log)
    # eps_p_eq steht je Gausspunkt; gemeldet wird der groesste Wert des
    # Elements - ein Element gilt als fliessend, sobald ein Punkt fliesst.
    res.info["plastisch"] = {int(i): float(np.max(v)) for i, v in zustand.eps_p_eq.items()
                             if float(np.max(v)) > 0}
    return u, halter["R"], halter["aktiv"], temp


def _startherkunft_eintragen(res, start, start_von, ausfallweg: bool) -> None:
    """Woher der Warmstart des Lastfalls kam - **angeboten** und **genutzt**
    getrennt (22.09.2026).

    Angeboten ist nicht genutzt: ``zustand_setzen`` lehnt eine Sicherung ab,
    die nicht zu den Bedingungen passt, ``solve_with_contact`` verwirft einen
    Warmstart ohne Halt oder mit vielen Knoten gegen ihre Gleitrichtung und
    rechnet von der Geometrie, und ein eingefrorener Zustand rechnet mit
    seiner Referenz statt mit dem Start. Der Ausfallweg reicht den Start gar
    nicht weiter (``solve_with_ausfall`` ruft ``solve_with_contact`` ohne
    ``start``) - dort gilt immer: nichts angeboten. Eine einzige Angabe
    "Start von" behauptete in all diesen Faellen einen Warmstart, den es nie
    gab (Gegenprobe der Loesersitzung).

    ``start_genutzt`` ist wahr, wenn ein Kontaktlauf, der den angebotenen
    Start bekam (``start_von_lauf == 0`` im Laufbuch), warm endete."""
    if ausfallweg:
        res.info["start_angeboten_von"] = None
        res.info["start_genutzt"] = False
        res.info["start_vermerk"] = "Ausfallweg ohne Warmstart"
        return
    res.info["start_angeboten_von"] = (str(start_von) if start_von else "unbekannt") \
        if start is not None else None
    res.info["start_genutzt"] = any(bool(e.get("warm")) for e in (res.info.get("laeufe") or [])
                                    if e.get("start_von_lauf") == 0)


def _solve_loads(model: Model, system: StaticSystem, factors: dict, name: str,
                 kind: str, workers=None, progress=None, start=None,
                 einfrieren=None, fenster=None, probelauf: bool = False,
                 start_von: str = None) -> Results:
    """Einen Lastfall (oder eine direkt geloeste Kombination) rechnen.

    ``start_von`` nennt nur, woher ``start`` stammt ("Lastfall LF1",
    "Kombination K1", "System <Situation>") - es steht als
    ``res.info['start_angeboten_von']`` im Ergebnis und aendert nichts an
    der Rechnung."""
    t0 = time.time()
    # Loeser-Nachweis je Lastfall: das System wird ueber Lastfaelle und
    # Kombinationen geteilt, seine Summen (zeit_faktorisierung) wachsen mit.
    if hasattr(system, "nachweis_beginnen"):
        system.nachweis_beginnen()
    aktiv = getattr(system, "aktiv", None)
    # Wie oft vorher mit einem ausgewichenen Loeser geloest wurde - am Ende
    # steht in res.info, ob dieses Ergebnis betroffen ist. Ketten, Pool und
    # Farm rechnen ohne Fortschritt; dort ist das Ergebnis der einzige Weg,
    # auf dem der Grund den Anwender erreicht (Befund K2, 22.09.2026).
    ausweich_vorher = ausweichgruende_zaehlen(system)
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
    # Laufbuch: die Art des naechsten Kontaktlaufs und die Zustaende, die die
    # Laeufe hinterlassen haben - daran erkennt der naechste, von welchem
    # Lauf sein Start stammt (Vergleich mit ``is``, keine Kopie). Reine
    # Buchfuehrung, nichts davon geht in die Rechnung.
    lauf_art = {"art": "Vorlauf" if _plastisch(model) else "Lastfall"}
    zustaende: list = []        # [(Nr. des Laufs, Kontaktzustand danach)]

    def _start_von_lauf(st_eff):
        if st_eff is None:
            return None
        if st_eff is start:
            return 0
        for nr, z in reversed(zustaende):
            if z is st_eff:
                return nr
        return -1               # Herkunft unbekannt (von aussen hineingereicht)

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
                # solve_with_ausfall reicht keinen Start weiter: kalt
                res.info.update(_kontakt_info_sammeln(res, cinfo, lauf_art["art"], None))
            return u_, R_, aktiv_
        if model.has_contact:
            # Derselbe Ausdruck wie unten im Aufruf, nur fuer das Laufbuch
            st_eff = None if (probelauf and start_ is None) else st
            von_lauf = _start_von_lauf(st_eff)
            u_, R_, res.contact, res.contact_forces, cinfo = solve_with_contact(
                model, system, Fg, progress=progress, us=us, uebermass=ueber,
                # Der Probelauf verwirft den Warmstart des **vorigen
                # Lastfalls** (start), damit jede Netzrunde dieselbe Lage
                # misst. Der Zustand **innerhalb** desselben Lastfalls
                # (start_, den die Plastizitaetsschleife je Fliessschritt
                # durchreicht) muss bleiben - sonst faengt jeder Fliessschritt
                # den Kontakt wieder bei der Geometrie an. Bis zum 21.09.2026
                # warf diese Zeile beides weg; gemessen am Drehlager
                # (Loeser-Sitzung): 8,97 % andere Vergleichsspannung und ein um
                # 2,1 % steiferes Ergebnis (0,2657 statt 0,2715 mm) - Kontakte,
                # die sich nicht setzen konnten, machen steifer. Die Rangfolge
                # blieb dieselbe (100 von 100 Spitzenelementen), das Netzmass
                # war also brauchbar, aber der Lauf war nicht der, der er sein
                # sollte.
                start=None if (probelauf and start_ is None) else st,
                einfrieren=einfrieren,
                fenster=fenster, K_zusatz=K_zusatz, probelauf=probelauf)
            res.kontaktzustand = cinfo.pop("contact_state", None)
            res.info.update(_kontakt_info_sammeln(res, cinfo, lauf_art["art"], von_lauf))
            zustaende.append((len(res.info["laeufe"]), res.kontaktzustand))
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
            _teilergebnis_anhaengen(model, system, res, ex, F, feq, q, temp, workers, aktiv,
                                    art=lauf_art["art"])
            res.info.update(ausweich_info(system, ausweich_vorher))
            raise
        n_sg = len(system.singular)
        _melde(progress, f"{n_sg} freie Bewegung{'' if n_sg == 1 else 'en'} gefunden - "
               "wird mit Hilfsfesselung gerechnet")
        try:
            u, R, aktiv_eff = _rechnen()
        except RuntimeError as ex2:
            # Auch mit Hilfsfesselung kein Gleichgewicht: die Verformung der
            # letzten Iteration bleibt als Ergebnis "Abbruch" erhalten
            _teilergebnis_anhaengen(model, system, res, ex2, F, feq, q, temp, workers, aktiv,
                                    art=lauf_art["art"])
            res.info.update(ausweich_info(system, ausweich_vorher))
            raise
        hilfs = True
    if _plastisch(model) and "contact_laeufe" in res.info:
        # Die Kontaktlaeufe bis hier sind der elastische Vorlauf. Sein Zustand
        # geht nicht weiter - der erste plastische Lauf startet bei ``start``,
        # nicht bei res.kontaktzustand (_plastizitaet_rechnen) -, und sein u
        # wird ueberschrieben. Ein gedeckelter Vorlauf aendert das Ergebnis
        # darum nicht: am Block mit Reibung max |du| = 0 gegen den Lauf ohne
        # Deckel (tests/test_rechenliste, 22.09.2026). Damit die Kennzeichnung
        # (rechenliste.zustand_aus_info) ihn herausrechnen kann, stehen seine
        # Zahlen hier eigens; contact_converged klebt weiter ueber alle Laeufe.
        res.info["contact_vorlauf_laeufe"] = int(res.info.get("contact_laeufe", 0) or 0)
        res.info["contact_vorlauf_nicht_konvergiert"] = int(
            res.info.get("contact_laeufe_nicht_konvergiert", 0) or 0)
    if _plastisch(model):
        # Vorlaeufig: welcher Aufruf der Fliess-Iteration welche Art hat,
        # steht erst nach ihrem Ende fest (_fliessarten_eintragen)
        lauf_art["art"] = "Fliessen"
        # Der Probelauf rechnet das Fliessen **mit** - nur der Kontakt bleibt
        # bei einem Schritt. Die erste Fassung (357d61d) liess die Plastizitaet
        # aus, weil fuer den Spannungssprung die elastische Spannung zu genuegen
        # schien. Am Drehlager gemessen (Loeser-Sitzung, 21.09.2026) ist das
        # falsch: elastisch trifft der Probelauf nur 54 von 100
        # Spitzenelementen (L2-Abweichung 52,2 %), plastisch 100 von 100
        # (2,3 %). Er verfeinerte also an den falschen Stellen. Der Preis ist
        # klein - 199 statt 124 s gegen 633 s fuer den vollen Lauf: bei 645.934
        # Elementen ist das Aufstellen der Matrix der Brocken, nicht die Zahl
        # der Schritte.
        try:
            u, R, aktiv_eff, temp = _plastizitaet_rechnen(model, res, F, _rechnen, aktiv, temp, progress, start)
        except RuntimeError as ex3:
            _teilergebnis_anhaengen(model, system, res, ex3, F, feq, q, temp, workers, aktiv,
                                    art=lauf_art["art"])
            res.info.update(ausweich_info(system, ausweich_vorher))
            raise
    if model.has_contact:
        _startherkunft_eintragen(res, start, start_von, model.hat_ausfallstaebe())
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
                     "zeit_faktorisierung": float(getattr(system, "zeit_faktorisierung", 0.0)),
                     **ausweich_info(system, ausweich_vorher)})
    nachweis = system.nachweis_abschliessen() if hasattr(system, "nachweis_abschliessen") else None
    if nachweis is not None:
        res.info["loeser_nachweis"] = nachweis
    if probelauf:
        res.info["probelauf"] = True
    postprocess(model, u, res, feq, q, temp, workers, aktiv_eff, system=system)
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
    # gebundene Mittelknoten (Uebergang linear/quadratisch) haben keine
    # eigene Steifigkeit; ihre Verschiebung folgt aus der Kante
    u = asm.mittelknoten_nachfuehren(model, u)
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

    ``probelauf=True`` begrenzt den **Kontakt** auf einen Schritt aus dem
    Anfangszustand der Fugen; das Fliessen wird mitgerechnet. Das ist der Lauf
    fuer die adaptive Vernetzung (``adaptiv.adaptiv_vernetzen``): sie braucht
    den Spannungssprung zwischen Nachbarelementen als Netzmass.

    **Der Gewinn ist Faktor 3, nicht Faktor 48.** Am Drehlager LF1 kalt
    gemessen (Loeser-Sitzung, 21.09.2026): voller Lauf 633,4 s, Probelauf
    198,8 s. Ein **einziger** Kontaktschritt kostet dort schon 123,8 s, weil
    bei 645.934 Elementen das Aufstellen der Matrix der Brocken ist und nicht
    die Zahl der Schritte.

    **Warum das Fliessen mit muss**: ohne es (so war es in 357d61d gebaut)
    verfeinert die Schleife an den falschen Stellen - elastisch stimmen nur
    54 von 100 Spitzenelementen mit dem vollen Lauf ueberein, die
    L2-Abweichung der Vergleichsspannung liegt bei 52,2 %; mit Fliessen sind
    es 100 von 100 und 2,3 %. Die 75 s Unterschied bringen die ganze
    Genauigkeit.

    **Das Ergebnis ist ein Netzmass, kein Rechenergebnis.** ``Results.info``
    traegt ``probelauf: True``, ``contact_converged`` steht auf falsch - und
    vor allem: ``res.contact_forces`` liegt um **Faktor 834** daneben
    (9,276e8 N gegen 1,112e6 N am Drehlager, 21.09.2026), damit auch
    Fugenkraefte, Pressungen, Bolzennachweise und die Auflagerkraefte
    einseitiger Lager. Verschiebung (0,04 %) und Spannung (2,3 %) stimmen;
    warum die Kontaktkraefte es nicht tun, ist nicht geklaert. Wer aus einem
    Probelauf etwas anderes als ein Netzmass liest, liest falsch.
    """
    with parallel.arbeiter(model, workers):
        return _solve_static_innen(model, progress, case, workers, system, probelauf)


def _solve_static_innen(model: Model, progress=None, case: str = None,
                        workers: int = None, system: StaticSystem = None,
                        probelauf: bool = False) -> Results:
    """Ein Lastfall (default: aktiver Lastfall; case='all': alle Lastfaelle mit
    Faktor 1 ueberlagert).

    Ohne uebergebenes ``system`` rechnet der Lastfall in **seiner Situation**
    (Stellung, abgeschaltete Elemente) - wie in solve_cases. Bis zum
    23.09.2026 baute diese Funktion StaticSystem(model) ohne Situation und
    rechnete jeden Lastfall still in der Grundstellung: „Nur aktiver
    Lastfall“, ``--analyse lastfall`` und der Webserver lieferten fuer einen
    Lastfall mit abgebautem Lager das Ergebnis mit Lager (Befund B123,
    Winkelrahmen: uz in Kragarmmitte -0,2470 statt -3,5971 mm wie
    solve_cases). Ein uebergebenes System gilt, wie es ist."""
    if case == "all":
        factors = {k: 1.0 for k in model.load_cases}
        name = "alle Lastfaelle"
    else:
        lc = model.case(case)
        factors = {lc.name: 1.0}
        name = lc.name
    if system is None:
        sit = _situation_der_faelle(model, list(factors))
        if sit != GRUNDSTELLUNG:
            model, system = situationssystem(model, sit, workers, progress)
        else:
            system = StaticSystem(model, workers, progress)
    res = _solve_loads(model, system, factors, name, "case", workers, progress,
                       probelauf=probelauf)
    sit = getattr(system, "situation", "") or GRUNDSTELLUNG
    _melde(progress, "System gelöst" + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
           1.0)
    return res


def _situation_der_faelle(model: Model, namen: list) -> str:
    """Die eine Situation der genannten Lastfaelle.

    Stehen sie in verschiedenen Situationen, gibt es kein gemeinsames System
    (andere Lager, andere wirksame Elemente) - ihre Summe laesst sich nicht
    in einer Rechnung bilden, und stillschweigend eine der Situationen zu
    nehmen, hiesse die anderen Lastfaelle falsch zu rechnen."""
    je = model.lastfaelle_je_situation(namen)
    if len(je) > 1:
        raise ValueError("Die Lastfälle stehen in verschiedenen Situationen ("
                         + "; ".join(f"{s}: {', '.join(n)}" for s, n in je.items())
                         + ") - in einer Rechnung lassen sie sich nicht überlagern, "
                           "jede Situation hat ihr eigenes System")
    return next(iter(je), GRUNDSTELLUNG)


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


def _referenzgruppen(folge: list, referenzen: dict) -> list:
    """Die Lastfaelle in **unteilbare** Gruppen: eine Referenz und alle
    Zustaende, die ihren Kontaktzustand einfrieren, gehoeren zusammen.

    Warum unteilbar: :func:`_solve_cases_innen` findet den eingefrorenen
    Zustand nur, wenn seine Referenz **in demselben Lauf** schon gerechnet
    wurde (``_einfrieren`` dort). Liegt sie in einer anderen Kette, gibt es
    still ``(None, None)`` und der Zustand rechnet voll nichtlinear - kein
    falsches Ergebnis, aber der ganze Gewinn ist weg, und niemand sieht es.
    Darum wird an Gruppengrenzen geschnitten und nicht an festen Bloecken.

    Zusammengefasst wird ueber Zusammenhangskomponenten und nicht ueber ein
    einfaches "Referenz plus ihre Zustaende": waere ein Zustand selbst
    Referenz eines dritten, zerfiele die Kette sonst.
    :func:`ermuedungsreferenzen` baut solche Ketten heute nicht (ein Zustand,
    der selbst Referenz ist, bleibt nichtlinear), aber die Gruppenbildung darf
    davon nicht abhaengen.

    Die Reihenfolge bleibt erhalten: innerhalb einer Gruppe die von ``folge``,
    die Gruppen in der Reihenfolge ihres ersten Auftretens. So bleiben
    Situationen zusammenhaengend und der Warmstart greift weiter.
    """
    eltern = {n: n for n in folge}

    def wurzel(a):
        while eltern[a] != a:
            eltern[a] = eltern[eltern[a]]
            a = eltern[a]
        return a

    for zustand, ref in (referenzen or {}).items():
        if zustand in eltern and ref in eltern:
            ra, rb = wurzel(zustand), wurzel(ref)
            if ra != rb:
                eltern[ra] = rb
    gruppen: dict = {}
    for n in folge:
        gruppen.setdefault(wurzel(n), []).append(n)
    gesehen, aus = set(), []
    for n in folge:
        w = wurzel(n)
        if w not in gesehen:
            gesehen.add(w)
            aus.append(gruppen[w])
    return aus


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
    # Mehrere Lastfaelle gleichzeitig? Nur ohne uebergebenes System - das gilt
    # fuer alle genannten Faelle und laesst sich nicht auf Prozesse verteilen.
    #
    # Eingefrorene Zustaende sperrten die Ketten bis zum 22.09.2026 ganz, weil
    # sie ihren Referenzzustand aus demselben Lauf brauchen. Am Drehlager
    # liefert ermuedungsreferenzen 161 eingefrorene Zustaende (Protokoll vom
    # 19.09.2026; eine fruehere Fassung dieses Kommentars schrieb 117), also
    # war referenzen nie leer, und die Sperre haette immer gegriffen - sobald
    # die Ketten ueberhaupt eingeschaltet sind; die Vorgabe ist ketten = 1.
    # Jetzt schneidet _ketten_teilen an Gruppengrenzen, und Referenz und
    # Zustand landen in derselben Kette. Am Drehlager sind es nur drei
    # Gruppen (LF401: 79, LF601: 81, LF402: 1), die Aufteilung ist dort grob.
    if system is None and len(names) > 1:
        k = ketten_zahl(len(names))
        if k > 1:
            fertig = _cases_in_ketten(model, names, k, progress, referenzen)
            if fertig:
                return fertig
    # Jeder fertige Lastfall bleibt bestehen, auch wenn der naechste abbricht:
    # ``out`` haengt an der Ausnahme (siehe _teil_merken)
    try:
        if system is not None:
            start = None
            start_von = None        # woher ``start`` stammt - nur fuers Ergebnis
            for k, name in enumerate(names):
                ref, einf = _einfrieren(name)
                n_ = max(1, len(names))
                out[name] = _solve_loads(model, system, {name: 1.0}, name, "case", workers,
                                         progress=progress, start=start, einfrieren=einf,
                                         fenster=(0.35 + 0.25 * k / n_, 0.35 + 0.25 * (k + 1) / n_),
                                         start_von=start_von)
                if einf is not None:
                    out[name].info["contact_frozen_from"] = ref
                if out[name].kontaktzustand:
                    start_von = f"Lastfall {name}"
                start = out[name].kontaktzustand or start
                _melde(progress, f"Lastfall {name} ({k + 1}/{len(names)})",
                       0.35 + 0.25 * (k + 1) / n_)
            return out
        systeme = systeme_je_situation(model, names, workers, progress, systeme)
        k = 0
        for sit, sit_names in model.lastfaelle_je_situation(names).items():
            m_s, sys_s = systeme[sit]
            start = getattr(sys_s, "kontaktzustand", None)
            # Der Zustand am System kann aus einem frueheren Aufruf stammen
            # (Lastfall oder Kombination); kennt es seine Herkunft nicht, heisst
            # sie nach dem System
            start_von = (getattr(sys_s, "kontaktzustand_von", None) or f"System {sit}") \
                if start is not None else None
            for name in _mit_referenzen_zuerst(list(sit_names), referenzen):
                ref, einf = _einfrieren(name)
                n_ = max(1, len(names))
                out[name] = _solve_loads(m_s, sys_s, {name: 1.0}, name, "case", workers,
                                         progress=progress, start=start, einfrieren=einf,
                                         fenster=(0.35 + 0.25 * k / n_, 0.35 + 0.25 * (k + 1) / n_),
                                         start_von=start_von)
                if einf is not None:
                    out[name].info["contact_frozen_from"] = ref
                if out[name].kontaktzustand:
                    start_von = f"Lastfall {name}"
                start = out[name].kontaktzustand or start
                sys_s.kontaktzustand = start
                sys_s.kontaktzustand_von = start_von
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


def _ketten_teilen(model: Model, names: list, k: int, referenzen: dict = None) -> list:
    """Die Lastfaelle auf k Ketten verteilen - Situation fuer Situation
    zusammenhaengend, damit der Warmstart innerhalb der Kette greift (jede
    Situation hat ihr eigenes System), und **nie zwischen einer Referenz und
    ihren eingefrorenen Zustaenden** (siehe :func:`_referenzgruppen`).

    Geschnitten wird darum an Gruppengrenzen statt an festen Bloecken. Eine
    Gruppe, die groesser ist als die Zielgroesse, bekommt ihre eigene Kette;
    die Ketten werden dadurch ungleich lang. Das ist die richtige Seite zum
    Irren: ungleiche Ketten kosten Wartezeit, eine verlorene Referenz kostet
    einen vollen nichtlinearen Lastfall - und zwar still.
    """
    # Die Referenzordnung gilt **je Situation**, nicht ueber alle Lastfaelle:
    # sonst zieht sie Faelle aus einer Situation vor und zerreisst damit die
    # Ordnung, die der Docstring zusichert. Jede Situation, die eine Kette
    # beruehrt, kostet dort ein eigenes System und eine eigene Faktorisierung
    # (87 s von 235 s je Lastfall am Drehlager) - und ketten_zahl rechnet mit
    # 9,5 GB je Kette fuer **eine** Matrix.
    folge = []
    for sit_names in model.lastfaelle_je_situation(names).values():
        teil = list(sit_names)
        if referenzen:
            teil = _mit_referenzen_zuerst(teil, referenzen)
        folge.extend(teil)
    k = max(1, min(int(k), len(folge)))
    gr = (len(folge) + k - 1) // k
    gruppen = _referenzgruppen(folge, referenzen) if referenzen else [[n] for n in folge]
    ketten, aktuell = [], []
    for g in gruppen:
        # Eine neue Kette nur, solange danach noch eine uebrigbleibt: sonst
        # entstuenden **mehr** Ketten als angefordert. _cases_in_ketten
        # startet so viele Prozesse, wie es Bloecke gibt, und eine Kette am
        # Drehlager belegt 9,5 GB - aus k=3 wuerden sonst 4 Prozesse und
        # 38 GB. Gemessen an vier Ermuedungslasten zu je drei Zustaenden:
        # k=3 gab vier Ketten (22.09.2026).
        if aktuell and len(aktuell) + len(g) > gr and len(ketten) < k - 1:
            ketten.append(aktuell)
            aktuell = []
        aktuell.extend(g)
    if aktuell:
        ketten.append(aktuell)
    return ketten


def _cases_in_ketten(model: Model, names: list, k: int, progress=None,
                     referenzen: dict = None) -> dict:
    """Mehrere Lastfaelle gleichzeitig: je Kette ein Prozess, in sich warm.

    Gemessen am Drehlager (20.09.2026): ein warmer Lastfall braucht 235 s,
    davon 87 s Faktorisierung. Die Kernlast (Loesersitzung, 22.09.2026, 31
    Prozesse): im Mittel rund 12,5 von 32 **logischen** Prozessoren belegt -
    der Rechner hat aber nur 16 physische Kerne, und die Last kommt in
    Schueben: etwa 60 % der Zeit sind alle physischen Kerne besetzt, etwa ein
    Drittel der Zeit weniger als acht. Im Mittel stehen geschaetzt 4 bis 5
    physische Kerne still, nicht 20; ein Gewinn durch Ketten ist am Drehlager
    nicht gemessen. Der Speicher ist die Grenze - eine Kette mit vollem Pool
    belegt 36 GB, davon 32,7 GB die Arbeiter.
    """
    import pickle
    import tempfile
    from .parallel import Job, run_jobs
    bloecke = _ketten_teilen(model, names, k, referenzen)
    if len(bloecke) <= 1:
        return {}
    st = parallel.settings()
    je = int(getattr(st, "ketten_arbeiter", 0) or 0) or max(2, st.workers // len(bloecke))
    threads = threads_je_kette(st.solver_threads, len(bloecke))
    _melde(progress, f"{len(names)} Lastfälle in {len(bloecke)} Ketten "
                     f"({je} Arbeiter und {threads} Löser-Threads je Kette)")
    pfad = None
    # vor dem Pickeln bzw. to_dict umwandeln (parallel.vor_dem_pickeln): jede
    # Kette rechnete sonst die Umwandlung noch einmal selbst
    parallel.vor_dem_pickeln(model)
    if st.backend != "farm":
        fd, pfad = tempfile.mkstemp(prefix="statik3d_kette_", suffix=".pkl")
        os.close(fd)
        with open(pfad, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
    try:
        d = model.to_dict() if pfad is None else None
        # Je Kette nur die Referenzen, deren **beide** Enden in ihr liegen. Eine
        # Referenz, die anderswo liegt, waere im Auftrag wertlos und
        # verdeckte, dass der Zustand voll gerechnet hat.
        def _teilreferenzen(b):
            drin = set(b)
            return {z: r for z, r in (referenzen or {}).items()
                    if z in drin and r in drin}

        def _auftrag(b):
            a = {"pfad": pfad or "", "model": d, "cases": b,
                 "arbeiter": je, "loeser_threads": threads}
            # ``referenzen`` nur mitgeben, wenn es welche gibt: ein Arbeiter
            # aelteren Stands (Rechnerfarm, danebenliegende Statik3D.exe)
            # kennt den Schluessel nicht und faellt mit TypeError aus. Ohne
            # Ermuedungsreferenzen - also in fast jedem Modell - aendert sich
            # damit nichts an seinem Auftrag.
            # Die Einstellungen des Loesers muessen mit: unter spawn beginnt
            # jeder Kettenprozess mit den Vorgaben. Bis zum 22.09.2026 rechnete
            # eine Kette darum mit solver_backend "auto" statt dem
            # gespeicherten "pardiso" und mit der Vorgabegenauigkeit - und wich
            # still aus, wo der Hauptprozess abgebrochen haette (gefunden von der
            # Loesersitzung). Nur die, die von der Vorgabe abweichen: ein
            # Arbeiter aelteren Stands kennt den Schluessel nicht.
            ein = kettenauftrag_einstellungen(st)
            if ein:
                a["einstellungen"] = ein
            tr = _teilreferenzen(b)
            if tr:
                a["referenzen"] = tr
            return a

        jobs = [Job("solve_kette", _auftrag(b), label=f"{b[0]}…{b[-1]}")
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
    fehler = []
    for i_kette, (job, r) in enumerate(zip(jobs, fertig)):
        if not r.ok:
            fehler.append(f"Kette {job.label}: {r.error}")
            continue
        for n, res in (r.result or {}).items():
            res.model = model
            # Laufbuch: in welcher Kette (Nummer, Zahl der Ketten) der
            # Lastfall lief. Der erste jeder Kette startet kalt - ohne diese
            # Angabe liesse sich ein "start_angeboten_von: None" mitten in der
            # Reihe nicht von einem Fehler unterscheiden. Reine Buchfuehrung.
            info = getattr(res, "info", None)
            if isinstance(info, dict):
                info["kette"] = (i_kette + 1, len(bloecke))
            out[n] = res
    gerettet = {n: out[n] for n in names if n in out}
    # **Was hier bewusst NICHT steht.** Eine erste Fassung zog die
    # Lastfallmarken nach ("Lastfall X (k/n)"), damit die Rechenliste ihre
    # Posten abschliesst - in der Kette laeuft solve_cases ohne progress, also
    # entsteht dort keine solche Zeile, und alle Zeilen bleiben bis zum Ende
    # des Laufs offen. Eine Gegenlesung hat die Fassung am 22.09.2026 in drei
    # Punkten widerlegt, und alle drei waren schlimmer als das Uebel:
    #
    #   * Die Schleife stand **vor** der Rettung und in keinem try. Ein
    #     Abbruch faellt als Ausnahme aus dem Fortschrittsaufruf heraus
    #     (gui.worker.Abgebrochen) - und nahm damit genau das mit, was die
    #     Rettung gerade sichern sollte. Vor der Aenderung war diese Lage
    #     harmlos, weil nach run_jobs gar kein Fortschritt mehr gemeldet wurde.
    #   * Der Anteil i/n sprengte das Fenster der Lastfaelle (0,35 bis 0,60,
    #     siehe die Aufrufe weiter oben): der Balken sprang auf 100 % und fiel
    #     mit der ersten Kombination auf 60 % zurueck.
    #   * Die Marken kommen ohnehin erst, wenn **alle** Ketten zurueck sind
    #     (run_jobs wartet). Die Rechenliste misst die Dauer von Marke zu
    #     Marke - ein Lastfall haette 4:12:00 behauptet und 421 je 0:00.
    #
    # Was bleibt, ist die Einschraenkung: auf dem Kettenweg schliessen die
    # Zeilen der Rechenliste erst am Ende, und der Abbruch greift zwischen
    # den Ketten. Das ist der Preis der Ketten und steht so im
    # Theoriehandbuch - eine falsche Anzeige waere schlechter als eine
    # ausbleibende.
    if fehler:
        # Was fertig ist, bleibt - genau wie im seriellen Weg. Ohne diesen
        # Anhang kostete ein einziger Fehlschlag (divergierender Lastfall,
        # Speicher, abgestuerzter Arbeiter) die Rechenzeit **aller** fertigen
        # Ketten; am Drehlager sind das viele Stunden.
        raise _teil_merken(RuntimeError("; ".join(fehler)), "teil_cases", gerettet)
    return gerettet


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
                      progress=None, systeme: dict = None, start=None,
                      nichtlinear: bool = None) -> Results:
    """Eine Kombination: Superposition (linear) oder direkte Loesung (Kontakt) -
    in der Situation der Kombination.

    ``nichtlinear`` nimmt die Antwort von :func:`_nichtlinear` entgegen, wenn
    der Aufrufer sie schon kennt - siehe dort, warum das lohnt."""
    sit = _kombination_pruefen(model, combo)
    nl = _nichtlinear(model) if nichtlinear is None else bool(nichtlinear)
    if not nl and case_results is not None \
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
        start_von = (getattr(system, "kontaktzustand_von", None) or f"System {sit}") \
            if start is not None else None
    else:
        start_von = "Aufrufer"      # von aussen hineingereicht, Herkunft unbekannt
    res = _solve_loads(model, system, combo.factors, combo.name, "combination", workers,
                       progress, start=start, start_von=start_von)
    if res.kontaktzustand is not None:
        system.kontaktzustand = res.kontaktzustand
        system.kontaktzustand_von = f"Kombination {combo.name}"
    res.info["typ"] = combo.typ
    return res


def alternativen_der_kombination(combo: Combination) -> list:
    """[(Name, {Lastfall: Faktor})] je Alternative einer Ergebniskombination.

    Der Name ist "EK [k]" mit k ab 1 in der Reihenfolge der Alternativen -
    derselbe in der Herkunft der Umhuellenden, in den Nachweisen und in den
    Tabellen der Theorie II./III. Ordnung. Eine Alternative ohne Faktor
    ungleich null entfaellt, behaelt aber ihre Nummer nicht fuer eine andere.
    """
    aus = []
    for k, alt in enumerate(combo.alternativen, 1):
        teile = {a: f for a, f in alt.items() if f}
        if teile:
            aus.append((f"{combo.name} [{k}]", teile))
    return aus


def faktoren_der_alternative(model: Model, name: str):
    """{Lastfall: Faktor} der Alternative "EK [k]" - None, wenn keine
    Ergebniskombination eine Alternative dieses Namens hat."""
    for c in (getattr(model, "combinations", None) or {}).values():
        if c.ist_umhuellende and name.startswith(f"{c.name} ["):
            for n, teile in alternativen_der_kombination(c):
                if n == name:
                    return dict(teile)
    return None


def _lastfall_alternative(teile: dict):
    """Der Lastfall, wenn die Alternative genau dieser Lastfall mit Faktor 1
    ist - sonst None. Dann **ist** die Alternative das Lastfallergebnis."""
    if len(teile) != 1:
        return None
    lc, f = next(iter(teile.items()))
    return lc if abs(f - 1.0) < 1e-12 else None


def umhuellende_der_kombination(model: Model, combo: Combination, case_results: dict,
                                systeme: dict = None, workers: int = None,
                                progress=None, ablage: dict = None) -> tuple:
    """Die Umhuellende einer Kombination mit Alternativen - Rueckgabe
    (Envelope, Zahl der zusaetzlich geloesten Alternativen).

    Eine Alternative aus genau einem Lastfall mit Faktor 1 **ist** dessen
    Lastfallergebnis: es wird wiederverwendet, nichts neu geloest. Am
    Drehlager sind das alle 720 Eintraege der 52 Ergebniskombinationen. Jede
    andere Alternative wird als voruebergehende Kombination gerechnet
    (Ueberlagerung; im Kontaktmodell direkte Loesung) und nach dem Einfalten
    verworfen - im linearen Modell haengt der Speicher nicht von der Zahl
    der Alternativen ab; die Nachweise ueberlagern sie bei Bedarf neu
    (:func:`ergebnisse_der_alternativen`).

    ``case_results`` muessen die **linearen** Lastfallergebnisse sein, auch
    wenn ein Lastfall auf theorie "II"/"III" steht: eine Alternative ist
    entweder die Ueberlagerung linearer Lastfaelle (sie gilt nach I.
    Ordnung) oder als Ganzes nach II./III. Ordnung gerechnet (dann liegt sie
    in ``ablage``) - nie ein Gemisch (solve_all, ``lineare_cases``).

    ``ablage`` (``Analysis.alternativen``) nimmt die Ergebnisse auf, die sich
    spaeter **nicht** aus den Lastfaellen wiedergewinnen lassen, und liefert
    die schon gerechneten: Alternativen nach Theorie II./III. Ordnung (legt
    theorie2/theorie3 ab), direkte Loesungen im Kontaktmodell und
    Alternativen aus Lastfaellen, deren lineares Ergebnis danach durch II./III.
    Ordnung ersetzt wird. Ohne sie sahen die Nachweise die Alternativen gar
    nicht (22.09.2026: nur-oder-Modell 0,170 statt 0,370 Ausnutzung).
    """
    from dataclasses import replace
    sit = _kombination_pruefen(model, combo)
    env = Envelope(model, {}, combo.name)
    geloest = 0
    nl = None
    # Lastfaelle, deren Ergebnis _lastfaelle_hoeherer_ordnung in an.cases
    # ersetzt (hat): eine Alternative mit ihnen laesst sich spaeter nicht
    # mehr aus an.cases ueberlagern und wird darum abgelegt
    wechselt = {k for k, lc in model.load_cases.items()
                if model.theorie_von(lc) in ("II", "III")}
    liste = alternativen_der_kombination(combo)
    for k, (name, teile) in enumerate(liste, 1):
        lc = _lastfall_alternative(teile)
        if ablage is not None and name in ablage:
            env.aufnehmen(name, ablage[name])
            geloest += 1
        elif lc is not None and case_results and lc in case_results:
            env.aufnehmen(lc, case_results[lc])
            if ablage is not None and lc in wechselt:
                ablage[name] = case_results[lc]
        else:
            zwischen = replace(combo, name=name, factors=teile, alternativen=[])
            res = solve_combination(model, zwischen, case_results, workers=workers,
                                    systeme=systeme)
            env.aufnehmen(name, res)
            geloest += 1
            if ablage is not None:
                if nl is None:
                    nl = _nichtlinear(model)
                if nl or (wechselt & set(teile)):
                    ablage[name] = res
        _melde(progress, f"Umhüllende {combo.name}: {k}/{len(liste)}"
               + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
               0.60 + 0.30 * k / max(1, len(liste)))
    return env, geloest


def ergebnisse_der_alternativen(model: Model, analysis, combo: Combination) -> tuple:
    """Die Ergebnisse der Alternativen einer Ergebniskombination fuer die
    Nachweise - Rueckgabe ({"EK [k]": Results}, [Warnungen]).

    Ein Nachweis braucht **zusammengehoerige** Schnittgroessen; die
    Umhuellende mischt Minimum und Maximum verschiedener Alternativen und
    taugt dafuer nicht. Darum sieht jeder Nachweis jede Alternative wie eine
    eigene Kombination, in derselben Reihenfolge wie die Umhuellende:

    * abgelegt (``analysis.alternativen``): nach Theorie II./III. Ordnung
      gerechnet, im Kontaktmodell direkt geloest, oder linear ueberlagert
      aus einem Lastfall, dessen lineares Ergebnis danach durch II./III.
      Ordnung ersetzt wurde - so, wie die Umhuellende sie gefaltet hat;
    * ein Lastfall mit Faktor 1: das Lastfallergebnis;
    * sonst im linearen Modell die Ueberlagerung der Lastfaelle.

    Was so nicht zu haben ist, wird als Warnung benannt und nicht still
    durch etwas anderes ersetzt - etwa nach ``solve_all(combinations=False)``
    oder aus einer Ergebnisdatei von vor dem 22.09.2026:

    * das Kontaktmodell ohne abgelegtes Ergebnis;
    * jede Alternative, die nach der **Theorie der EK** nach II./III.
      Ordnung zu rechnen ist und nicht abgelegt wurde. Ueberlagert kaeme dort
      still das lineare Ergebnis heraus: am Druckkragarm EK1 [2] 3,321 statt
      9,705 mm, an der Halle (theorie2 "ein", alle GZT-Kombinationen als eine
      EK) Riegel 0,9654 statt 0,9734 - ohne Warnung, waehrend die
      gewoehnlichen Kombinationen derselben Rechnung als "nicht
      nachgewiesen" gemeldet wurden (Gegenpruefung 23.09.2026);
    * sonst jede Alternative mit einem **Lastfall** auf Theorie II./III.
      Ordnung, die nicht abgelegt wurde. Nach II./III. Ordnung zu rechnen ist
      sie nicht - ihr Ergebnis ist die lineare Ueberlagerung
      (umhuellende_der_kombination, ``wechselt``) -, aber
      _lastfaelle_hoeherer_ordnung hat das lineare Ergebnis des Lastfalls in
      ``analysis.cases`` ersetzt, und daraus laesst sie sich nicht mehr
      bilden.
    """
    from dataclasses import replace
    aus: dict = {}
    warn: list = []
    abgelegt = getattr(analysis, "alternativen", None) or {}
    cases = getattr(analysis, "cases", None) or {}
    nl = None
    theorie = model.theorie_von(combo)
    # Lastfaelle, deren Ergebnis II./III. Ordnung ist oder war: ihr lineares
    # Ergebnis steht nicht mehr in analysis.cases, die (zulaessige) lineare
    # Ueberlagerung einer Alternative mit ihnen laesst sich daraus nicht mehr
    # bilden - darum legt die volle Rechnung jede solche Alternative ab
    # (umhuellende_der_kombination, ``wechselt``)
    hoeher = {k for k, lf in model.load_cases.items()
              if model.theorie_von(lf) in ("II", "III")}
    for name, teile in alternativen_der_kombination(combo):
        lc = _lastfall_alternative(teile)
        if name in abgelegt:
            aus[name] = abgelegt[name]
            continue
        grund = None
        if theorie in ("II", "III") and not _bei_theorie_I_geblieben(analysis, theorie, name):
            grund = (f"sie ist nach Theorie {theorie}. Ordnung zu rechnen, ihr Ergebnis "
                     "liegt nicht vor (Überlagerung wäre linear)")
        elif hoeher & set(teile):
            # Bis zum 23.09.2026 hiess es hier "ihr Ergebnis liegt nicht vor
            # (Überlagerung nicht zulässig)" - gesucht ist aber gerade die
            # zulaessige lineare Ueberlagerung (Nebenbefund 5)
            grund = (f"Lastfall {', '.join(sorted(hoeher & set(teile)))} wird nach Theorie "
                     "II./III. Ordnung gerechnet, ihre lineare Überlagerung lässt sich "
                     "nach dem Ersetzen nicht mehr aus den Lastfallergebnissen bilden")
        if grund is not None:
            warn.append(f"Kombination {name} (Alternative der Ergebniskombination "
                        f"{combo.name}) nicht nachgewiesen: {grund} – „Alle Lastfälle + "
                        "Kombinationen“ neu rechnen")
            continue
        if lc is not None and lc in cases:
            aus[name] = cases[lc]
            continue
        fehlt = [a for a in teile if a not in cases]
        if nl is None:
            nl = _nichtlinear(model)
        if not nl and not fehlt:
            zwischen = replace(combo, name=name, factors=teile, alternativen=[])
            try:
                aus[name] = solve_combination(model, zwischen, cases, nichtlinear=False)
            except ValueError as ex:
                warn.append(f"Kombination {name} (Alternative der Ergebniskombination "
                            f"{combo.name}) nicht nachgewiesen: {ex}")
            continue
        grund = (f"Lastfall {', '.join(fehlt)} nicht gerechnet" if fehlt else
                 "ihr direkt gelöstes Ergebnis liegt nicht vor (nichtlineares Modell, "
                 "Überlagerung nicht zulässig)")
        warn.append(f"Kombination {name} (Alternative der Ergebniskombination {combo.name}) "
                    f"nicht nachgewiesen: {grund} – „Alle Lastfälle + Kombinationen“ "
                    "neu rechnen")
    return aus, warn


def _bei_theorie_I_geblieben(analysis, theorie: str, name: str) -> bool:
    """Ob die Rechnung nach Theorie II. bzw. III. Ordnung die Alternative
    ``name`` gesehen hat und bei ihrem linearen Ergebnis geblieben ist -
    dann darf ergebnisse_der_alternativen es ueberlagern.

    Das trifft zu bei alpha_cr >= Grenze nach 5.2.1(3) (theorie2 "auto")
    und bei einem Fehler der Rechnung, den das Theoriekapitel nennt ("nicht
    geführt"); beides behandelt check_theorie2/check_theorie3 bei einer
    gewoehnlichen Kombination genauso - deren lineares Ergebnis bleibt
    stehen. Keine Zeile fuer die Alternative heisst: nicht nach dieser
    Theorie gerechnet, das lineare Ergebnis waere geraten.
    """
    t = getattr(analysis, "theorie2" if theorie == "II" else "theorie3", None)
    info = (getattr(t, "kombinationen", None) or {}).get(name)
    return info is not None and not getattr(info, "gerechnet", False)


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
    nl = _nichtlinear(model)
    if not nl:
        if case_results is None:
            case_results = solve_cases(model, workers=workers, progress=progress,
                                       system=system, systeme=systeme)
        try:
            for k, n in enumerate(names):
                out[n] = solve_combination(model, model.combinations[n], case_results,
                                           systeme=systeme, nichtlinear=nl)
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
                            workers=None, aktiv=None, art: str = "") -> None:
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
        # Auch die Laufzaehlung: ohne diese Zeilen blieben
        # contact_letzter_lauf_konvergiert und contact_laeufe_nicht_konvergiert
        # auf dem Stand des VORIGEN, konvergierten Laufs, und ein abgebrochener
        # Lastfall meldete "letzter Lauf konvergiert" (gefunden von der
        # Loesersitzung am Quelltext, 22.09.2026).
        #
        # Das Laufbuch bekommt fuer den abgebrochenen Lauf einen eigenen
        # Eintrag (grund 'abbruch'); die Zaehlung wird daraus abgeleitet wie
        # in _kontakt_info_sammeln. Zustandsangaben gibt es nicht - die
        # Iteration hat kein Ende erreicht.
        _alte = list(res.info.get("laeufe") or [])
        _eintrag = _laufbuch_eintrag(len(_alte) + 1, {
            "contact_iterations": int(ex.iteration), "contact_converged": False,
            "contact_lauf": {"grund": "abbruch"}}, art, None)
        _eintrag["faktorisierungen"] = None      # nicht bekannt: der Lauf gab kein cinfo zurueck
        _laeufe_liste = _alte + [_eintrag]
        _laeufe = len(_laeufe_liste)
        _nicht = sum(1 for e in _laeufe_liste if not e["konvergiert"])
        res.info.update({"abbruch": str(ex).splitlines()[0], "abbruch_iteration": int(ex.iteration),
                         "laeufe": _laeufe_liste,
                         "contact_laeufe": _laeufe, "contact_letzter_lauf_konvergiert": False,
                         "contact_laeufe_nicht_konvergiert": _nicht,
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
                postprocess(model, u, res, feq, q, temp, workers, aktiv, system=system)
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


def _kontaktlauf_angaben(cs, u, model: Model, grund: str) -> dict:
    """Was das Laufbuch ueber einen Kontaktlauf festhaelt (``cinfo['contact_lauf']``,
    in _kontakt_info_sammeln zum Eintrag gemacht): Grund des Endes, Zustand am
    Ende und die Runden (contact.RUNDEN_FELDER).

    ``u_max`` ist die groesste Verschiebung eines Knotens [m], nur ueber die
    drei Verschiebungen - u haengt Drehungen und Woelb-Freiheitsgrade an, und
    ein Maximum ueber m und rad zusammen waere keine Groesse. Dasselbe Mass
    wie "max|u|" der Drehlager-Messungen (Knotenbetrag)."""
    u_max = None
    if u is not None:
        n6 = model.nn * NDOF
        v = np.asarray(u, float)[:n6].reshape(-1, NDOF)[:, :3]
        u_max = float(np.linalg.norm(v, axis=1).max()) if len(v) else 0.0
    return {"grund": grund, "zyklen": int(cs.cycles), "phase": int(cs.phase),
            "n_aktiv": int(cs.n_active), "n_gleitet": int(cs.n_slip),
            "runden": list(getattr(cs, "runden", None) or []),
            "endzustand_kennung": cs.endzustand_kennung(), "u_max": u_max}


def _neustart_vermerken(cinfo2: dict, runden_vorher: list) -> None:
    """Ein Neustart gehoert zu **demselben** Kontaktlauf: die Runden vor dem
    Neustart kommen vor die des Neustarts, damit je Schritt eine Runde im
    Laufbuch steht (Schritte werden dort ebenso zusammengezaehlt)."""
    lauf = cinfo2.setdefault("contact_lauf", {})
    lauf["neustart"] = True
    lauf["runden"] = list(runden_vorher) + list(lauf.get("runden") or [])


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
    kz_kenn = zusatz_kenn(K_zusatz)

    def signatur():
        s = cs.signatur()
        return s if kz_kenn is None else s + (kz_kenn,)

    f0 = getattr(system, "faktorisierungen", 0)
    eingefroren_verworfen = None     # Verstoesse, wenn der eingefrorene Zustand nicht passte
    if einfrieren is not None and cs.cons and cs.zustand_setzen(einfrieren):
        Kc, Fc = cs.matrices(model.ndof)
        if K_zusatz is not None:
            Kc = Kc + K_zusatz
        u = system.solve(F, Kc, Fc, us=us, signatur=signatur())
        # Vor _update_states (das setzt Zustaende um): passt der eingefrorene
        # Zustand zu dieser Last? Bis zum 22.09.2026 hiess der Lauf immer
        # "konvergiert", auch wenn eine geschlossene Bedingung Zug trug (FE4).
        # Gemessen am Block mit Reibung, Referenz H1: 1,0 H1 passt (0,00 %
        # gegen die nichtlineare Loesung), 1,1 H1 vier Knoten ueber dem
        # Reibkegel (7,0 %), 0,5 H1 Durchdringung und Gleiten gegen die
        # Richtung (18,8 %), -1,0 H1 Zug an sechs geschlossenen (70,0 %).
        verst = cs.zustand_verstoesse(u)
        passt = not (verst["zug"] or verst["durchdringung"] or verst["kegel"] or verst["gegen"])
        if passt:
            cs._update_states(u)             # nur zur Auswertung: g, Fn, Ft je Bedingung
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
                "contact_state": None,
                # konvergiert: der Zustand erfuellt alle Bedingungen unter dieser
                # Last; der Grund sagt, dass dieser Lauf nicht iteriert hat
                "contact_lauf": _kontaktlauf_angaben(cs, u, model, "eingefroren")}
        # Passt nicht: nichtlinear nachrechnen, vom eingefrorenen Zustand aus
        teile = []
        if verst["zug"]:
            teile.append(f"{verst['zug']} geschlossene Bedingungen unter Zug "
                         f"(größter {verst['zug_max'] / 1e3:.3g} kN)")
        if verst["durchdringung"]:
            teile.append(f"{verst['durchdringung']} offene durchdrungen "
                         f"(größte {verst['durchdringung_max'] * 1e3:.3g} mm)")
        if verst["kegel"]:
            teile.append(f"{verst['kegel']} haftende über dem Reibkegel "
                         f"(bis {verst['kegel_max']:.3g}-fach)")
        if verst["gegen"]:
            teile.append(f"{verst['gegen']} gleitende gegen ihre Gleitrichtung")
        zeile = ("Kontaktzustand eingefroren, passt aber nicht zu dieser Last: "
                 + ", ".join(teile) + " - wird nichtlinear nachgerechnet, Start: der eingefrorene Zustand")
        log.append(zeile)
        _melde(progress, zeile)
        eingefroren_verworfen = verst
        start = einfrieren
    warm = bool(start) and cs.zustand_setzen(start)
    if warm:
        log.append("Warmstart aus dem Kontaktzustand des vorigen Lastfalls")
    converged = False
    deckel = False          # die Reibungsnachpruefung hat aufgegeben
    from .contact import MAX_CYCLES as _MAX_CYCLES
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
                                                   "contact_state": None,
                                                   "contact_lauf": _kontaktlauf_angaben(
                                                       cs, u, model, "")}
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
                runden_vorher = list(getattr(cs, "runden", None) or [])
                u2, R2, cons2, cf2, cinfo2 = solve_with_contact(
                    model, system, F, max_iter, progress, us, K_zusatz, uebermass,
                    start=None, versuch=versuch + 1, fenster=fenster,
                    probelauf=probelauf)
                cinfo2["contact_log"] = log + list(cinfo2.get("contact_log", []))
                cinfo2["contact_warm"] = False
                cinfo2["contact_factorisations"] = getattr(system, "faktorisierungen", 0) - f0
                _neustart_vermerken(cinfo2, runden_vorher)
                if eingefroren_verworfen is not None:     # der Neustart kennt ihn nicht
                    cinfo2["contact_frozen_verworfen"] = eingefroren_verworfen
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
            weiter = ("Kontakt: nach dem Deckel der Reibungsnachprüfung wurde ein "
                      "Schubhalt gelöst - die Iteration läuft weiter")
            if getattr(cs, "am_deckel", False) and weiter not in log:
                # Die Abbruchzeile des Kontaktsystems steht schon im
                # Protokoll; ohne diese Zeile laese man dort "abgebrochen"
                # neben einem Lauf, der danach noch zu Ende kommen kann.
                log.append(weiter)
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
            # ContactSystem.update() gibt False zurueck, wenn es fertig ist -
            # **und** wenn es aufgibt: nach MAX_CYCLES Zustandswechseln bricht
            # die Nachpruefung der Reibung ab (contact.py) und meldet das nur
            # ins contact_log. Der Loeser las beides als Konvergenz und setzte
            # contact_converged auf wahr. Eine Zahl aus einem gedeckelten Lauf
            # sah damit aus wie eine auskonvergierte - und genau gegen solche
            # Zahlen pruefen wir 'aendert das Ergebnis nicht'. Gefunden von der
            # Loesersitzung am Quelltext (21.09.2026).
            # Entschieden wird an der Runde, in der die Schleife wirklich
            # endet (cs.am_deckel), nicht an cs.cycles: der Zaehler bleibt
            # nach dem Deckel stehen, und eine spaetere Runde ohne Wechsel
            # meldete sonst ebenfalls den Deckel (22.09.2026).
            # Fehlt der Merker (ein Kontaktsystem, dessen update() ihn nicht
            # setzt), gilt die alte, vorsichtige Probe: ein fehlender Merker
            # darf nicht "konvergiert" heissen (Gegenpruefung, 22.09.2026).
            deckel = bool(getattr(cs, "am_deckel",
                                  cs.phase == 2 and cs.cycles >= _MAX_CYCLES))
            converged = not deckel
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
            runden_vorher = list(getattr(cs, "runden", None) or [])
            u2, R2, cons2, cf2, cinfo2 = solve_with_contact(
                model, system, F, max_iter, progress, us, K_zusatz, uebermass,
                start=neu_start, versuch=versuch + 1, fenster=fenster,
                probelauf=probelauf)
            cinfo2["contact_log"] = log + list(cinfo2.get("contact_log", []))
            cinfo2["contact_warm"] = bool(neu_start) and cinfo2.get("contact_warm", False)
            cinfo2["contact_iterations"] = it + cinfo2.get("contact_iterations", 0)
            cinfo2["contact_factorisations"] = getattr(system, "faktorisierungen", 0) - f0
            _neustart_vermerken(cinfo2, runden_vorher)
            if eingefroren_verworfen is not None:         # der Neustart kennt ihn nicht
                cinfo2["contact_frozen_verworfen"] = eingefroren_verworfen
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
                (f"Kontakt: Nachprüfung der Reibung nach {_MAX_CYCLES} Zustandswechseln "
                 "abgebrochen - das Ergebnis ist nicht auskonvergiert"
                 if deckel else
                 f"Kontakt-Iteration nach {max_iter} Schritten nicht konvergiert"))
        log.append(text)
        _melde(progress, text)
    log.extend(cs.warnings())
    # Derselbe Entscheid wie der Meldetext oben, als Wort fuers Laufbuch
    grund = ("" if converged else "probelauf" if probelauf
             else "deckel" if deckel else "max_iter")
    return u, R, cs.results(), cs.nodal_forces(model.nn), {
        "contact_abbruch": (text if not converged else ""),
        "contact_iterations": it, "contact_converged": converged, "contact_log": log,
        "contact_warm": warm,
        "contact_factorisations": getattr(system, "faktorisierungen", 0) - f0,
        "contact_state": cs.zustand(),
        "contact_frozen_verworfen": eingefroren_verworfen,
        "contact_lauf": _kontaktlauf_angaben(cs, u, model, grund)}


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
    #: Ergebnisse von Alternativen einer Ergebniskombination ("EK [k]"), die
    #: sich nicht aus den Lastfaellen wiedergewinnen lassen: Theorie II./III.
    #: Ordnung, Kontaktmodell (umhuellende_der_kombination). Die Nachweise
    #: lesen sie ueber ergebnisse_der_alternativen.
    alternativen: dict = field(default_factory=dict)

    def all_results(self) -> dict:
        d = dict(self.cases)
        d.update(self.combinations)
        return d

    def envelope(self, typ: str = "ULS") -> Optional[Envelope]:
        return self.envelopes.get(typ)

    def summary(self) -> str:
        s = [f"Lastfaelle: {len(self.cases)}   Kombinationen: {len(self.combinations)}   "
             f"Rechenzeit: {self.info.get('time', 0):.2f} s ({self.info.get('parallel', '')})"]
        # Ausweichen des Gleichungsloesers: eine Zeile je Grund ueber alle
        # Ergebnisse - auch aus Ketten, Pool und Farm, die ohne Fortschritt rechnen
        s += ausweichen_gebuendelt(self.all_results().items())
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
        # Die Zeile der Theorie II. Ordnung steht oben hinter den Umhuellenden.
        # Bis zum 23.09.2026 wurde sie hier ein zweites Mal angehaengt, und
        # Protokoll und Zusammenfassung zeigten sie doppelt (Befund B125).
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
            # **Nicht nur nach an.info["warnungen"]**: dieser Schluessel wird im
            # ganzen Programm einmal geschrieben und nirgends gelesen - weder
            # von Analysis.summary noch vom Bericht noch von der Oberflaeche.
            # Der Lastfall behielt damit still sein LINEARES Ergebnis unter
            # demselben Namen, waehrend die Lastfalltabelle des Berichts
            # weiterhin "II" bzw. "III" ausweist (report/html.py druckt
            # model.theorie_von, also die Einstellung, nicht das Gerechnete).
            # Zusatzmomente aus der Verformung und die Vorkruemmungen fehlten
            # vollstaendig, und alle darauf aufbauenden Nachweise rechneten mit
            # zu kleinen Momenten - unkonservativ und ohne jeden Hinweis
            # (gefunden 22.09.2026).
            #
            # Der Kombinationszweig macht es seit jeher richtig
            # (theorie3.py: Th3Info(name=n, fehler=str(ex))); hier fehlte es.
            # Mit einem Eintrag in kombinationen steht der Fehler in der
            # Spalte "Hinweis" des Theoriekapitels, und res.info["theorie"]
            # sagt, was wirklich gerechnet wurde.
            an.info.setdefault("warnungen", []).append(f"Lastfall {name}: {ex}")
            if th == "II":
                from .theorie2 import Th2Info
                if an.theorie2 is None:
                    an.theorie2 = Th2Results(settings={"modus": "je Lastfall/Kombination"})
                an.theorie2.kombinationen[name] = Th2Info(kombination=name, fehler=str(ex))
            else:
                from .theorie3 import Th3Info
                if an.theorie3 is None:
                    an.theorie3 = Th3Results(
                        settings={"schritte": int(getattr(ds, "th3_schritte", 10) or 10)})
                an.theorie3.kombinationen[name] = Th3Info(name=name, fehler=str(ex))
            _lineares_ergebnis_markieren(an, name, th, str(ex))
            continue
        if not info.fehler:
            res.kind = "case"
            if lc.situation:
                res.info["situation"] = lc.situation
            an.cases[name] = res
        else:
            # Singulaeres System (theorie2.py) oder keine Konvergenz
            # (theorie3.py): das nichtlineare Ergebnis wird zu Recht NICHT
            # uebernommen, der Fehler steht ueber kombinationen[name] schon im
            # Theoriekapitel. Das stehenbleibende lineare Ergebnis blieb aber
            # unmarkiert, und die Lastfalltabelle wies weiter "II"/"III" aus,
            # obwohl nach Theorie I. Ordnung gerechnet war (gemessen 22.09.2026
            # mit erzwungenem info.fehler, tests/test_theorie3.py). Darum
            # dieselbe Markierung wie im ValueError-Zweig.
            an.info.setdefault("warnungen", []).append(f"Lastfall {name}: {info.fehler}")
            _lineares_ergebnis_markieren(an, name, th, str(info.fehler))


def _lineares_ergebnis_markieren(an, name: str, th: str, grund: str) -> None:
    """Ein Lastfall, dessen Rechnung nach Theorie ``th`` scheiterte, behaelt
    sein lineares Ergebnis - es ist ja gerechnet -, sagt aber ab jetzt selbst,
    nach welcher Theorie (report/html.py, ``_theorie_spalte``)."""
    alt_res = an.cases.get(name)
    if alt_res is None:
        return
    alt_res.info["theorie"] = "I"
    alt_res.info["theorie_gewuenscht"] = th
    alt_res.info["theorie_fehler"] = grund


def ermuedungsreferenzen(model: Model) -> dict:
    """{Zustand: Referenzzustand} fuer die Zustaende der Ermuedungslasten eines
    Kontaktmodells (DesignSettings.ermuedung_kontakt_einfrieren).

    Der erste Zustand jeder Ermuedungslast wird nichtlinear geloest, die
    weiteren mit seinem eingefrorenen Kontaktzustand linear. Ein Zustand, der
    schon eingefroren ist, gibt seine Referenz weiter; ein Zustand, der selbst
    Referenz ist, bleibt nichtlinear. Am Drehlager: 50 Ermuedungslasten, 164
    Zustaende; weil spaetere Lasten den schon eingefrorenen ersten Zustand
    weiterreichen, bleiben drei Referenzen (LF401, LF601, LF402) nichtlinear
    und 161 Zustaende werden linear geloest (Programmprotokoll vom
    19.09.2026). Eine fruehere Fassung schrieb "47 x 18 min und 117
    Rueckwaertseinsetzungen" - das war falsch.
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
    ek_rechnen = bool(combinations and model.combinations)
    umhuellende_ek: dict = {}

    def _ek_umhuellende(namen, lineare_cases: dict) -> None:
        for n in namen:
            c = model.combinations[n]
            env, geloest = umhuellende_der_kombination(model, c, lineare_cases, systeme,
                                                       workers, progress,
                                                       ablage=an.alternativen)
            umhuellende_ek[n] = env
            an.info.setdefault("umhuellende", {})[n] = {
                "alternativen": len(c.alternativen), "geloest": geloest}

    # Ergebniskombinationen, deren Theorie II. oder III. Ordnung ist: ihre
    # Alternativen rechnen check_theorie2/check_theorie3 unten am verformten
    # System, erst danach wird gefaltet. Vorher gingen sie hier linear in die
    # Umhuellende, und check_theorie2 legte fuer die EK selbst (factors leer)
    # ein Nullergebnis in an.combinations (Befund FE12, 22.09.2026).
    ek_hoeher = [n for n, c in model.combinations.items()
                 if c.ist_umhuellende and model.theorie_von(c) in ("II", "III")]
    if combinations and model.combinations:
        an.combinations = solve_combinations(model, case_results=an.cases, system=None,
                                             workers=workers, progress=progress,
                                             systeme=systeme)
        # Kombinationen mit Alternativen: je eine Umhuellende, keine Ergebnisse
        # in an.combinations. Sie stehen hinter den Art-Umhuellenden (unten).
        _ek_umhuellende([n for n, c in model.combinations.items()
                         if c.ist_umhuellende and n not in ek_hoeher], an.cases)
    # Die linearen Lastfallergebnisse, bevor _lastfaelle_hoeherer_ordnung die
    # mit theorie "II"/"III" ersetzt. Im Erfolgsfall setzt es je Lastfall ein
    # neues Objekt ein (an.cases[name] = res), die flache Kopie behaelt das
    # lineare. Scheitert die Rechnung (ValueError oder info.fehler), bleibt
    # das lineare Objekt in an.cases stehen, und _lineares_ergebnis_markieren
    # setzt an **demselben** Objekt die info-Marken theorie "I" und
    # theorie_gewuenscht - lineare_cases sieht sie mit. Das ist harmlos: das
    # Ergebnis ist ja linear, nur die Marken sind geteilt. Aus diesen
    # linearen Ergebnissen - wie oben jede gewoehnliche Kombination -
    # ueberlagert die Umhuellende einer EK nach II./III. Ordnung jede
    # Alternative, die bei I. Ordnung bleibt (theorie2 "auto" mit alpha_cr
    # >= Grenze, Fehler der Rechnung). Eine Zwischenfassung dieser Aenderung
    # (Zweig fix/ek, nicht ausgeliefert) faltete dort an.cases nach dem
    # Ersetzen: 1,35·G linear + 1,5·W nach II. Ordnung, ein Gemisch, weder
    # I. noch II. Ordnung, abgelegt und nachgewiesen (Gegenpruefung
    # 23.09.2026, W mit theorie "II", auto: Rahmen Stielkopf 102,4519 statt
    # 102,1415 mm wie K2; Druckkragarm des Tests EK1 [2] 3,374407 statt
    # 3,320749 mm). Der Stand bis 22.09.2026 (54b6f9a) hatte das Gemisch
    # nicht: er faltete die Umhuellende vor _lastfaelle_hoeherer_ordnung
    # linear, legte aber keine Alternative ab und wies keine nach
    # (Druckkragarm: Umhuellende 3,320749 mm, die Nachweise sahen nur K2 und
    # K3; nachgemessen 23.09.2026).
    lineare_cases = dict(an.cases) if (ek_rechnen and ek_hoeher) else None
    # Theorie je Lastfall: II. oder III. Ordnung ersetzt das lineare Ergebnis
    _lastfaelle_hoeherer_ordnung(model, an, systeme, progress)
    # Eine Ergebniskombination kommt nur mit ihren Alternativen hinein
    # (Ergebnisse nach an.alternativen) und nur, wenn Kombinationen gerechnet
    # werden; eine gewoehnliche, wenn es Kombinationsergebnisse gibt.
    th2 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "II"
           and (ek_rechnen if c.ist_umhuellende else bool(an.combinations))]
    if th2:
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
    th3 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "III"
           and (ek_rechnen if c.ist_umhuellende else bool(an.combinations))]
    if th3:
        from .theorie3 import check_theorie3
        t3 = check_theorie3(model, an, combos=th3, progress=progress, systeme=systeme)
        if an.theorie3 is None:
            an.theorie3 = t3
        else:
            an.theorie3.kombinationen.update(t3.kombinationen)
            an.theorie3.settings.update(t3.settings)
    if ek_rechnen and ek_hoeher:
        # Nach II./III. Ordnung Gerechnetes kommt aus an.alternativen, alles
        # andere aus den linearen Lastfaellen - nie aus einem Gemisch
        _ek_umhuellende(ek_hoeher, lineare_cases)
        lineare_cases = None        # die ersetzten linearen Ergebnisse freigeben
        # in der Reihenfolge des Modells, wie vorher
        umhuellende_ek = {n: umhuellende_ek[n] for n in model.combinations
                          if n in umhuellende_ek}
    if envelopes:
        groups: dict[str, dict] = {}
        for n, r in an.combinations.items():
            typ = model.combinations[n].typ
            key = "ULS" if typ in ("ULS", "EQU", "ACC", "USER") else typ
            groups.setdefault(key, {})[n] = r
        for key, rs in groups.items():
            an.envelopes[key] = Envelope(model, rs, f"Umhuellende {key}")
        # Die Umhuellende einer Ergebniskombination gehoert in die Umhuellende
        # ihrer Art - wie in RFEM. Die Nachweise lesen die Umhuellenden
        # **nicht** (sie brauchen zusammengehoerige Schnittgroessen); sie
        # sehen die Alternativen einzeln ueber ergebnisse_der_alternativen.
        # Hier stand bis zum 22.09.2026, die Nachweise saehen so die
        # Alternativen - das traf nie zu (Befund FE11).
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
    # Die Modalanalyse faktorisiert selbst, ohne StaticSystem - das Ausweichen
    # meldete hier bis zum 22.09.2026 nur warnings.warn (Befund K2).
    if loeser.ausweichgrund:
        _melde(progress, f"Gleichungslöser ausgewichen - {loeser.ausweichgrund}")
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
    res.info.update(_ausweich_eintraege([(loeser.ausweichgrund, loeser.backend)]))
    return res


# ==========================================================================
# Lineares Knicken
# ==========================================================================
def _verzweigung(system: StaticSystem, Kgff, k: int) -> tuple:
    """(lambda, Eigenvektoren) von K v = lambda (-K_g) v - die ``k``
    betragskleinsten lambda, aufsteigend nach Betrag.

    Geloest wird mit K als Metrik: (-K_g) v = mu K v, lambda = 1/mu, die
    betragsgroessten mu. Bis zum 23.09.2026 stand hier
    eigsh(K, M=-K_g, sigma=0): ARPACK verlangt im Shift-Invert-Modus ein
    positiv (semi)definites M. Mit Zug und Druck im Grundzustand ist -K_g
    indefinit, und die Faktoren wechselten von Lauf zu Lauf - gemessen
    23.09.2026 am Zweigelenkrahmen unter Wind (tests/test_knicklaengen.py):
    in sechs Laeufen erste Faktoren zwischen 1,00 und 4,77 statt 77,3287
    (dichter Bezug).
    In diesem Modus (ohne sigma) verlangt ARPACK ein positiv definites M.
    K ist das bei gehaltenem System, und seine Faktorisierung liegt aus dem
    Grundzustand schon vor. Mit einer freien Bewegung ist K nur
    semidefinit: an der Stuetze mit freier Torsion aus
    tests/test_knicklaengen.py::test_knicken_mit_freier_torsion (PARDISO,
    kein Rand) hat Kff den kleinsten Eigenwert 7,7e-8 gegen 1,6e4 den
    naechsten und 1,24e10 den groessten. Die Wirkung ist dort gemessen:
    die Eulerlast wird auf 0,039 % getroffen (24.09.2026); eine allgemeine
    Zusage fuer freie Bewegungen ist das nicht.
    Der Startvektor ist fest (Zufallszahlen mit
    festem Keim, nicht Einsen: ein symmetrischer Vektor kann auf
    antimetrische Formen senkrecht stehen). Bitgleich wird es damit nicht
    ganz: am Rahmen ist 77,3287 ein siebenfacher Eigenwert, und seine
    zweite und dritte Kopie streuen von Lauf zu Lauf in der 14. Stelle; die
    erste war in allen Laeufen bitgleich (gemessen 23.09.2026)."""
    from scipy.sparse.linalg import LinearOperator
    ls = system.solver
    n = Kgff.shape[0]
    rand = system._rand

    def k_inv(x):
        x = np.asarray(x, float).ravel()
        if rand:                    # Lagrange-Rand der Hilfsfesselung (gerandet)
            y = ls.solve(np.concatenate([x, np.zeros(rand)]), check=False)
            return np.asarray(y, float).ravel()[:n]
        return ls.solve(x, check=False)

    op = LinearOperator((n, n), dtype=float, matvec=k_inv)
    v0 = np.random.default_rng(0).standard_normal(n)
    mu, vecs = eigsh(-Kgff, k=k, M=system.Kff, Minv=op, which="LM", v0=v0)
    lam = np.full(len(mu), np.inf)
    np.divide(1.0, mu, out=lam, where=mu != 0.0)
    order = np.argsort(np.abs(lam), kind="stable")
    return lam[order], vecs[:, order]


def solve_buckling(model: Model, nmodes: int = 5, progress=None, case: str = None,
                   combination: str = None, workers: int = None) -> Results:
    """Lineares Verzweigungsproblem: (K + lambda*Kg) v = 0 (Stabtragwerke).
    Grundzustand: Lastfall (default aktiver) oder Kombination.

    Gerechnet wird in der **Situation** des Grundzustands: Steifigkeit,
    Grundzustand und geometrische Steifigkeit (nur wirksame Elemente) aus
    ihrem System. Bis zum 23.09.2026 kam alles aus der Grundstellung - ein
    Lastfall mit abgebautem Lager knickte mit Lager.

    Die Faktoren sind die ``nmodes`` betragskleinsten, beiderlei Vorzeichens
    (negativ: Knicken bei umgekehrter Last), aufsteigend nach Betrag - siehe
    :func:`_verzweigung`, warum mit K als Metrik geloest wird."""
    t0 = time.time()
    if combination:
        sit = _kombination_pruefen(model, model.combinations[combination])
    else:
        sit = _situation_der_faelle(model, [model.case(case).name])
    if sit != GRUNDSTELLUNG:
        model, system = situationssystem(model, sit, workers, progress)
    else:
        system = StaticSystem(model, workers, progress)
    if combination:
        static = solve_combination(model, model.combinations[combination], None, system, workers)
    else:
        static = solve_static(model, progress, case, workers, system)
    u = static.u.ravel()
    Kg = asm.geometric_stiffness(model, u, system.aktiv)
    fi = system.fi
    Kff = system.Kff
    Kgff = Kg[fi][:, fi].tocsc()
    if abs(Kgff).max() == 0:
        raise RuntimeError("Keine Normalkraefte vorhanden - Knicknachweis nicht moeglich")
    if progress:
        _melde(progress, "Verzweigungsproblem wird gelöst", 0.45)

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = _verzweigung(system, Kgff, k)

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
