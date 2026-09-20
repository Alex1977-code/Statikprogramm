"""
Parallele Ausfuehrung: mehrere Prozessorkerne lokal und/oder Rechnerfarm.

Einstellungen (global, z.B. aus der GUI):

    from statik3d import parallel
    parallel.configure(workers=8)                       # lokale Kerne
    parallel.configure(backend="farm", farm_host="192.168.1.10",
                       farm_port=5555, farm_key="geheim")

Zwei Ebenen:
1. map_elements(func, model, indices)  - Elementschleifen (Assemblierung,
   Nachlauf) werden in Bloecke zerlegt und auf einen Prozess-Pool verteilt.
   Das Modell wird je Arbeitsprozess einmal uebertragen.
2. run_jobs(jobs)  - grobkoernige Auftraege (Kombinationen mit Kontakt,
   Nachweise, Parameterstudien) lokal im Pool oder auf der Rechnerfarm.

Auftraege sind ueber die Registry JOB_KINDS definiert (siehe statik3d.jobs).
"""
from __future__ import annotations

import multiprocessing as mp
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from typing import Callable, Optional


# --------------------------------------------------------------------------
@dataclass
class Settings:
    #: Arbeitsprozesse fuer Elementschleifen, Auftraege und die Vernetzung:
    #: alle Kerne bis auf einen - der bleibt der Oberflaeche, damit sich das
    #: Programm waehrend einer Rechnung noch bedienen laesst.
    workers: int = max(1, (os.cpu_count() or 2) - 1)
    backend: str = "local"            # local | farm
    farm_host: str = "127.0.0.1"
    farm_port: int = 5555
    farm_key: str = "statik3d"
    min_elements: int = 1500          # ab dieser Elementzahl lohnt der Prozess-Pool
    chunk_elements: int = 400
    solver_backend: str = "auto"      # auto | pardiso | cholmod | superlu
    farm_timeout: float = 3600.0
    #: Threads des Gleichungsloesers (MKL PARDISO, MUMPS): 0 = automatisch
    #: (PARDISO alle Kerne bis auf einen, MUMPS hoechstens acht, siehe
    #: mumps.threads_vorgabe); sonst genau diese Zahl - "dann kann ich das an
    #: meinem Modell pruefen" (13.09.2026)
    solver_threads: int = 0
    #: MUMPS beim Programmstart nachladen, wenn es fehlt (statik3d.werkzeuge)
    mumps_nachladen: bool = True
    #: Genauigkeit des Gleichungsloesers (17.09.2026, "Einstellmoeglichkeit zur
    #: Genauigkeit"): bis zu diesem relativen Residuum |K u - b| / |b| gilt
    #: eine Loesung; darueber wird mit der vorhandenen Faktorisierung
    #: nachiteriert (hoechstens solver_nachiterationen Schritte), und erst
    #: dann gilt das System als singulaer. Vorgabe 1e-6 und 3 Schritte.
    solver_residuum: float = 1e-6
    solver_nachiterationen: int = 3
    #: Rechenketten: so viele Lastfaelle laufen gleichzeitig, jede Kette in
    #: einem eigenen Prozess und in sich warm gestartet (1 = nacheinander wie
    #: bisher, 0 = automatisch nach freiem Speicher). Gemessen am Drehlager
    #: (20.09.2026): eine Kette mit vollem Pool braucht 36 GB, davon 32,7 GB
    #: die 31 Arbeiter (1,05 GB je Arbeiter, jeder haelt das Modell) und nur
    #: 3,2 GB Matrix und Faktorisierung. Der Pool ist also die Grenze, nicht
    #: der Loeser - darum bekommt jede Kette einen kleinen eigenen Pool.
    ketten: int = 1
    #: Arbeiter je Kette (0 = workers // ketten, mindestens 2). Die
    #: Elementschleifen sind nur noch ein kleiner Teil der Zeit (Nachlauf
    #: 2-3 s, Plastizitaet 8 s von 235 s je warmem Lastfall), grosse Pools je
    #: Kette lohnen darum nicht.
    ketten_arbeiter: int = 0


_settings = Settings()

#: Was ueber den Programmstart hinaus gilt (Benutzerdaten/Statik3D/einstellungen.json)
GESPEICHERT = ("solver_backend", "solver_threads", "mumps_nachladen",
               "solver_residuum", "solver_nachiterationen", "ketten", "ketten_arbeiter")


def einstellungsdatei() -> str:
    """STATIK3D_EINSTELLUNGEN, sonst Benutzerdaten/Statik3D/einstellungen.json."""
    p = os.environ.get("STATIK3D_EINSTELLUNGEN")
    if p:
        return p
    from . import werkzeuge
    return os.path.join(werkzeuge.datenordner(), "einstellungen.json")


def einstellungen_laden() -> dict:
    """Gespeicherte Einstellungen in settings() uebernehmen; Rueckgabe, was in
    der Datei stand (leer, wenn es keine gibt oder sie unlesbar ist)."""
    import json
    try:
        with open(einstellungsdatei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    for k in GESPEICHERT:
        if k in d:
            try:
                setattr(_settings, k, type(getattr(_settings, k))(d[k]))
            except (TypeError, ValueError):
                pass
    return d


def einstellungen_speichern() -> str:
    """Die gespeicherten Einstellungen schreiben; Rueckgabe der Dateipfad."""
    import json
    p = einstellungsdatei()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({k: getattr(_settings, k) for k in GESPEICHERT}, f, ensure_ascii=False, indent=1)
    return p


def configure(**kw) -> Settings:
    for k, v in kw.items():
        if not hasattr(_settings, k):
            raise KeyError(f"unbekannte Einstellung '{k}'")
        setattr(_settings, k, v)
    return _settings


def settings() -> Settings:
    return _settings


def cpu_count() -> int:
    return os.cpu_count() or 1


def _context():
    if platform.system() == "Linux":
        return mp.get_context("fork")
    return mp.get_context("spawn")


# --------------------------------------------------------------------------
# Elementschleifen
# --------------------------------------------------------------------------
_WORKER_MODEL = None
_WORKER_EXTRA = None


def _melden(text: str) -> None:
    """Hinweis ausgeben, ohne sich auf ``sys.stderr`` zu verlassen.

    Die gepackte exe laeuft ohne Konsole; dort ist ``sys.stderr`` None. Ein
    ``write`` darauf brach die ganze Rechnung mit einem nichtssagenden
    ``AttributeError: 'NoneType' object has no attribute 'write'`` ab - und
    verdeckte damit den Fehler, den es eigentlich melden sollte.
    """
    strom = getattr(sys, "stderr", None)
    if strom is None:
        return
    try:
        strom.write(text)
    except Exception:               # noqa: BLE001 - ein Hinweis darf nie stoeren
        pass


def _init_model_worker(model, extra=None):
    global _WORKER_MODEL, _WORKER_EXTRA
    _WORKER_MODEL = model
    _WORKER_EXTRA = extra
    try:
        import statik3d.jobs  # noqa: F401  (registriert Auftragsarten)
    except Exception:
        pass


def _run_chunk(func: Callable, idx: list[int]):
    if _WORKER_EXTRA is None:
        return func(_WORKER_MODEL, idx)
    return func(_WORKER_MODEL, idx, _WORKER_EXTRA)


# --------------------------------------------------------------------------
# Stehender Pool je Rechnung: das Modell einmal je Arbeiter aus einer Datei
# --------------------------------------------------------------------------
_AKTIV = None            # der Arbeiter-Block, der gerade offen ist
_WORKER_EXTRA_PFAD = None


def _init_worker_datei(pfad: str) -> None:
    """Der Arbeitsprozess liest das Modell **einmal** aus der Datei."""
    global _WORKER_MODEL, _WORKER_EXTRA, _WORKER_EXTRA_PFAD
    import pickle
    with open(pfad, "rb") as f:
        _WORKER_MODEL = pickle.load(f)
    _WORKER_EXTRA, _WORKER_EXTRA_PFAD = None, None
    try:
        import statik3d.jobs  # noqa: F401  (registriert Auftragsarten)
    except Exception:
        pass


def _run_chunk_datei(func: Callable, idx: list[int], extra_pfad):
    """Ein Block im stehenden Pool; das Zusatzpaket (Verschiebungen) kommt je
    Aufruf einmal je Arbeiter aus seiner Datei."""
    global _WORKER_EXTRA, _WORKER_EXTRA_PFAD
    if extra_pfad is None:
        return func(_WORKER_MODEL, idx)
    if extra_pfad != _WORKER_EXTRA_PFAD:
        import pickle
        with open(extra_pfad, "rb") as f:
            _WORKER_EXTRA = pickle.load(f)
        _WORKER_EXTRA_PFAD = extra_pfad
    return func(_WORKER_MODEL, idx, _WORKER_EXTRA)


class Arbeiter:
    """Ein Prozesspool, der eine ganze Rechnung lang steht.

    Bis 13.09.2026 startete jede Elementschleife (Assemblierung, Nachlauf je
    Lastfall) einen neuen Pool und gab jedem Arbeiter das Modell als
    Startargument mit - gepickelt im Hauptprozess, **je Arbeiter**. Am
    Drehlager (1 812 423 Elemente, 275 MB gepickelt, 6,3 s) kostete das den
    Nachlauf eines einzigen Lastfalls 244 s, bei 422 Lastfaellen den
    Loewenanteil der Rechenzeit. Jetzt: das Modell einmal in eine Datei
    (wie beim Vernetzen), jeder Arbeiter liest sie beim Start, und der Pool
    bleibt bis zum Ende des Blocks stehen; das Zusatzpaket eines Aufrufs
    (der Verschiebungsvektor) geht ebenso ueber eine Datei, einmal je
    Arbeiter statt je Block.

    Verschachtelte Bloecke fuer dasselbe Modell nutzen denselben Pool. Ein
    Modell darf sich im Block nicht aendern - er gehoert zu **einer**
    Rechnung (solve_all, solve_static, solve_cases, solve_modal).
    """

    def __init__(self, model, workers: int = None):
        self.model = model
        self.w = _settings.workers if workers is None else int(workers)
        self.pool = None
        self.pfad = None
        self.tiefe = 0
        self.vorher = None
        self.aufrufe = 0
        self.geteilt = None      # der Block, den ein verschachtelter Aufruf mitbenutzt

    def __enter__(self):
        global _AKTIV
        if _AKTIV is not None and _AKTIV.model is self.model:
            # Verschachtelt: denselben Pool mitbenutzen. Python ruft __exit__
            # auf **diesem** Objekt, darum merkt es sich den Eigentuemer.
            self.geteilt = _AKTIV
            _AKTIV.tiefe += 1
            return _AKTIV
        self.vorher = _AKTIV
        self.tiefe = 1
        n = len(getattr(self.model, "elements", []) or [])
        if self.w > 1 and n >= _settings.min_elements:
            self._starten()
        _AKTIV = self
        return self

    def _starten(self) -> None:
        import pickle
        import tempfile
        fd, pfad = tempfile.mkstemp(prefix="statik3d_pool_", suffix=".pkl")
        os.close(fd)
        try:
            with open(pfad, "wb") as f:
                pickle.dump(self.model, f, protocol=pickle.HIGHEST_PROTOCOL)
            self.pool = ProcessPoolExecutor(max_workers=self.w, mp_context=_context(),
                                            initializer=_init_worker_datei, initargs=(pfad,))
            self.pfad = pfad
        except Exception as fehler:      # noqa: BLE001 - dann eben wie bisher je Aufruf
            _melden(f"[parallel] Stehender Pool nicht moeglich ({fehler})\n")
            self.pool = None
            try:
                os.remove(pfad)
            except OSError:
                pass

    def map(self, func: Callable, chunks: list, extra) -> list:
        """Die Bloecke ueber den stehenden Pool; extra einmal je Arbeiter."""
        import pickle
        import tempfile
        extra_pfad = None
        if extra is not None:
            fd, extra_pfad = tempfile.mkstemp(prefix="statik3d_extra_", suffix=".pkl")
            os.close(fd)
            with open(extra_pfad, "wb") as f:
                pickle.dump(extra, f, protocol=pickle.HIGHEST_PROTOCOL)
        try:
            parts = list(self.pool.map(_run_chunk_datei, [func] * len(chunks), chunks,
                                       [extra_pfad] * len(chunks)))
        finally:
            if extra_pfad:
                try:
                    os.remove(extra_pfad)
                except OSError:
                    pass
        self.aufrufe += 1
        out = []
        for part in parts:
            out.extend(part)
        return out

    def verwerfen(self) -> None:
        """Der Pool ist ausgefallen: schliessen, die Aufrufe laufen wie bisher."""
        pool, self.pool = self.pool, None
        if pool is not None:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except Exception:               # noqa: BLE001
                pass

    def __exit__(self, *_a):
        global _AKTIV
        if self.geteilt is not None:
            self.geteilt.tiefe -= 1
            self.geteilt = None
            return False
        self.tiefe -= 1
        if self.tiefe > 0:
            return False
        pool, self.pool = self.pool, None
        if pool is not None:
            try:
                pool.shutdown(wait=True)
            except Exception:               # noqa: BLE001
                pass
        if self.pfad:
            try:
                os.remove(self.pfad)
            except OSError:
                pass
        _AKTIV = self.vorher
        return False


def arbeiter(model, workers: int = None) -> "Arbeiter":
    """``with parallel.arbeiter(model):`` - ein stehender Pool fuer alle
    Elementschleifen dieser Rechnung (siehe :class:`Arbeiter`)."""
    return Arbeiter(model, workers)


def map_elements(func: Callable, model, indices: list[int], workers: int = None,
                 min_elements: int = None, extra=None) -> list:
    """func(model, [elementindizes]) bzw. func(model, idx, extra) -> Liste;
    Ergebnisse aller Bloecke werden in Elementreihenfolge aneinandergehaengt.
    'extra' (z.B. Verschiebungsvektor) wird je Arbeitsprozess einmal uebertragen."""
    n = len(indices)
    w = _settings.workers if workers is None else int(workers)
    mn = _settings.min_elements if min_elements is None else min_elements

    def serial():
        return func(model, list(indices)) if extra is None else func(model, list(indices), extra)

    if w <= 1 or n < mn or n == 0:
        return serial()
    chunk = max(_settings.chunk_elements, n // (4 * w) + 1)
    chunks = [list(indices[i:i + chunk]) for i in range(0, n, chunk)]
    akt = _AKTIV
    if akt is not None and akt.model is model and akt.pool is not None:
        try:
            return akt.map(func, chunks, extra)
        except (BrokenProcessPool, OSError, EOFError) as fehler:
            _melden(f"[parallel] Stehender Pool ausgefallen ({fehler}), rechne seriell\n")
            akt.verwerfen()
            return serial()
    # Ohne offenen Block: ein Pool nur fuer diesen Aufruf - aber ebenfalls
    # ueber die Modelldatei. Das Modell als Startargument je Arbeiter zu
    # pickeln machte den Pool am Drehlager langsamer als die serielle
    # Rechnung (244 s gegen 60 s, 13.09.2026).
    try:
        with Arbeiter(model, min(w, len(chunks))) as einmal:
            if einmal.pool is None:
                return serial()
            try:
                return einmal.map(func, chunks, extra)
            except (BrokenProcessPool, OSError, EOFError) as fehler:
                # Der Pool selbst ist ausgefallen (Speicher, abgestuerzter
                # Prozess) - das laesst sich seriell nachholen. Ein Fehler
                # *aus* func dagegen ist ein echter Befund am Modell und muss
                # unveraendert nach oben.
                _melden(f"[parallel] Arbeitsprozess ausgefallen ({fehler}), rechne seriell\n")
                einmal.verwerfen()
                return serial()
    except (BrokenProcessPool, OSError, EOFError) as fehler:
        _melden(f"[parallel] Pool nicht verfuegbar ({fehler}), rechne seriell\n")
        return serial()


# --------------------------------------------------------------------------
# Auftraege
# --------------------------------------------------------------------------
JOB_KINDS: dict[str, Callable] = {}


def register_job(kind: str):
    def deco(fn):
        JOB_KINDS[kind] = fn
        return fn
    return deco


@dataclass
class Job:
    kind: str
    payload: dict
    id: int = 0
    label: str = ""


@dataclass
class JobResult:
    id: int
    ok: bool
    result: object = None
    error: str = ""
    worker: str = ""
    seconds: float = 0.0


def execute_job(job: Job) -> JobResult:
    """Einen Auftrag im aktuellen Prozess ausfuehren."""
    import statik3d.jobs  # noqa: F401
    t0 = time.time()
    try:
        fn = JOB_KINDS[job.kind]
    except KeyError:
        return JobResult(job.id, False, None, f"unbekannte Auftragsart '{job.kind}'",
                         platform.node(), 0.0)
    try:
        res = fn(**job.payload)
        return JobResult(job.id, True, res, "", platform.node(), time.time() - t0)
    except Exception as ex:   # Fehler als Ergebnis zurueckgeben
        import traceback
        return JobResult(job.id, False, None,
                         f"{ex}\n{traceback.format_exc()}", platform.node(), time.time() - t0)


def run_jobs(jobs: list[Job], workers: int = None, backend: str = None,
             progress: Callable = None) -> list[JobResult]:
    """Auftraege ausfuehren: seriell, im lokalen Prozess-Pool oder auf der Farm.
    Rueckgabe in der Reihenfolge der Auftraege."""
    for i, j in enumerate(jobs):
        j.id = i
    if not jobs:
        return []
    be = backend or _settings.backend
    if be == "farm":
        from .farm import FarmClient
        client = FarmClient(_settings.farm_host, _settings.farm_port, _settings.farm_key)
        return client.run(jobs, progress=progress, timeout=_settings.farm_timeout)

    w = _settings.workers if workers is None else int(workers)
    if w <= 1 or len(jobs) == 1:
        out = []
        for j in jobs:
            out.append(execute_job(j))
            if progress:
                progress(len(out), len(jobs))
        return out
    ctx = _context()
    results: dict[int, JobResult] = {}
    try:
        with ProcessPoolExecutor(max_workers=min(w, len(jobs)), mp_context=ctx,
                                 initializer=_init_model_worker, initargs=(None,)) as ex:
            for r in ex.map(execute_job, jobs):
                results[r.id] = r
                if progress:
                    progress(len(results), len(jobs))
    except (BrokenProcessPool, OSError, EOFError) as fehler:
        _melden(f"[parallel] Pool nicht verfuegbar ({fehler}), rechne seriell\n")
        return [execute_job(j) for j in jobs]
    return [results[j.id] for j in jobs]


def describe() -> str:
    """Der **Prozesspool** - Elementschleifen, Auftraege, Vernetzen.

    Ausdruecklich nicht der Gleichungsloeser: der faktorisiert in einem
    Prozess und benutzt eigene Threads. Frueher stand hier nur „lokal,
    31 von 32 Kernen“, und das las sich, als rechne auch der Loeser so.
    Was der Loeser kann, sagt solver.loeser_verfuegbar().
    """
    s = _settings
    if s.backend == "farm":
        return f"Rechnerfarm {s.farm_host}:{s.farm_port}"
    return f"lokal, {s.workers} von {cpu_count()} Kernen"
