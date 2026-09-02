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
from dataclasses import dataclass, field
from typing import Callable, Optional


# --------------------------------------------------------------------------
@dataclass
class Settings:
    workers: int = max(1, (os.cpu_count() or 2))
    backend: str = "local"            # local | farm
    farm_host: str = "127.0.0.1"
    farm_port: int = 5555
    farm_key: str = "statik3d"
    min_elements: int = 1500          # ab dieser Elementzahl lohnt der Prozess-Pool
    chunk_elements: int = 400
    solver_backend: str = "auto"      # auto | pardiso | cholmod | superlu
    farm_timeout: float = 3600.0


_settings = Settings()


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
    ctx = _context()
    try:
        with ProcessPoolExecutor(max_workers=min(w, len(chunks)), mp_context=ctx,
                                 initializer=_init_model_worker, initargs=(model, extra)) as ex:
            parts = list(ex.map(_run_chunk, [func] * len(chunks), chunks))
    except Exception as ex:   # z.B. kein fork/spawn moeglich -> seriell
        sys.stderr.write(f"[parallel] Pool nicht verfuegbar ({ex}), rechne seriell\n")
        return serial()
    out = []
    for p in parts:
        out.extend(p)
    return out


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
    except Exception as ex:
        sys.stderr.write(f"[parallel] Pool nicht verfuegbar ({ex}), rechne seriell\n")
        return [execute_job(j) for j in jobs]
    return [results[j.id] for j in jobs]


def describe() -> str:
    s = _settings
    if s.backend == "farm":
        return f"Rechnerfarm {s.farm_host}:{s.farm_port}"
    return f"lokal, {s.workers} von {cpu_count()} Kernen"
