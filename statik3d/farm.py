"""
Rechnerfarm: Auftraege (Jobs) auf mehrere Rechner im Netz verteilen.

Architektur (Standardbibliothek, multiprocessing.managers):

    Server  - haelt Auftrags- und Ergebniswarteschlange, Statusliste
    Worker  - laeuft auf jedem Rechner der Farm, holt Auftraege, rechnet mit
              n Prozessen und liefert Ergebnisse zurueck
    Client  - (GUI/CLI) schickt Auftraege und sammelt Ergebnisse

Start:
    python -m statik3d.farm server --port 5555 --key geheim
    python -m statik3d.farm worker --host 192.168.1.10 --port 5555 --key geheim --cores 8
    python -m statik3d.farm status --host 192.168.1.10 --port 5555 --key geheim

Fuer den Anwender ohne Kommandozeile (13.09.2026, "die Rechnerfarm muss
benutzerfreundlicher funktionieren"): der Arbeitsplatz schaltet die Farm in
Berechnung -> Einstellungen ein und **kuendigt sich per UDP-Rundruf an**
(start_ankuendigung, Port 5556); ein Helfer startet ``Statik3D.exe
--rechenhilfe`` oder Extras -> Als Rechenhilfe arbeiten..., drueckt
"Arbeitsplatz suchen" (server_suchen) und "Verbinden" - ohne IP zu tippen.
Der Schluessel muss auf beiden Seiten gleich sein.

Auf allen Rechnern muss dieselbe statik3d-Version laufen; jeder Worker
meldet Version und Stand (Commit), der Status zeigt Abweichungen. Die
Verbindung ist mit dem Schluessel (authkey, HMAC) gesichert; die Farm sollte
nur im vertrauenswuerdigen Netz betrieben werden.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import platform
import queue
import socket
import sys
import threading
import time
from multiprocessing.managers import BaseManager

from . import __version__
from .parallel import Job, JobResult, execute_job

#: UDP-Port, auf dem sich ein Farm-Server ankuendigt und Helfer lauschen
ANKUENDIGUNGS_PORT = 5556
ANKUENDIGUNG = b"STATIK3D-FARM "


def build_sha() -> str:
    """Der Stand (Commit) dieser Installation, kurz - fuer den Abgleich der Rechner."""
    try:
        from .update import build_info
        return str(build_info().get("sha", ""))[:7]
    except Exception:                                      # noqa: BLE001
        return ""


def eigene_adressen() -> list:
    """IPv4-Adressen dieses Rechners (ohne 127.x) - die Adresse, unter der
    Helfer den Arbeitsplatz erreichen, zuerst die des Standardwegs ins Netz."""
    adressen = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))            # kein Verkehr - nur die Wegewahl
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            adressen.append(ip)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in adressen:
                adressen.append(ip)
    except OSError:
        pass
    return adressen


def start_ankuendigung(port: int, name: str = "", takt: float = 2.0, ziel_port: int = None,
                       zusatz_ziele=()) -> threading.Event:
    """Den Farm-Server per UDP-Rundruf ankuendigen (alle ``takt`` Sekunden),
    damit Helfer ihn finden, ohne eine IP zu tippen. Rueckgabe: das
    Stopp-Ereignis (set() beendet die Ankuendigung)."""
    stop = threading.Event()
    ziel_port = int(ziel_port or ANKUENDIGUNGS_PORT)
    text = json.dumps({"statik3d": "farm", "port": int(port), "name": name or platform.node(),
                       "version": __version__, "stand": build_sha()}).encode("utf-8")

    def lauf():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not stop.is_set():
            for ziel in ("<broadcast>", *zusatz_ziele):
                try:
                    s.sendto(ANKUENDIGUNG + text, (ziel, ziel_port))
                except OSError:
                    pass
            stop.wait(takt)
        s.close()

    threading.Thread(target=lauf, daemon=True, name="farm-ankuendigung").start()
    return stop


def server_suchen(sekunden: float = 3.0, port: int = None) -> list:
    """Auf Ankuendigungen lauschen. Rueckgabe: [{host, port, name, version,
    stand}] ohne Doppelte, in der Reihenfolge des Eintreffens."""
    port = int(port or ANKUENDIGUNGS_PORT)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", port))
    except OSError as ex:
        s.close()
        raise ConnectionError(f"Auf Port {port} (UDP) lässt sich nicht lauschen: {ex}") from ex
    s.settimeout(0.5)
    gefunden: dict = {}
    t0 = time.time()
    while time.time() - t0 < sekunden:
        try:
            data, (host, _p) = s.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        if not data.startswith(ANKUENDIGUNG):
            continue
        try:
            d = json.loads(data[len(ANKUENDIGUNG):].decode("utf-8"))
        except ValueError:
            continue
        if d.get("statik3d") != "farm":
            continue
        schluessel = (host, int(d.get("port", 5555)))
        gefunden[schluessel] = {"host": host, "port": schluessel[1], "name": str(d.get("name", "")),
                                "version": str(d.get("version", "")), "stand": str(d.get("stand", ""))}
    s.close()
    return list(gefunden.values())


class _ServerManager(BaseManager):
    """Manager-Klasse der Serverseite (registriert das Zustandsobjekt mit callable)."""


class _ClientManager(BaseManager):
    """Manager-Klasse fuer Worker und Clients (nur Proxy-Zugriff)."""


_ClientManager.register("state")


# --------------------------------------------------------------------------
# Server
# --------------------------------------------------------------------------
class _State:
    def __init__(self):
        self.jobs: queue.Queue = queue.Queue()
        self.results: queue.Queue = queue.Queue()
        self.workers: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.stats = {"submitted": 0, "done": 0, "failed": 0, "started": time.time()}

    # --- Client-Seite ---
    def submit(self, job):
        with self.lock:
            self.stats["submitted"] += 1
        self.jobs.put(job)

    def get_result(self, timeout=1.0):
        try:
            return self.results.get(timeout=timeout)
        except queue.Empty:
            return None

    # --- Worker-Seite ---
    def fetch(self, worker: str, timeout=2.0):
        with self.lock:
            w = self.workers.setdefault(worker, {"jobs": 0, "since": time.time()})
            w["seen"] = time.time()
        try:
            return self.jobs.get(timeout=timeout)
        except queue.Empty:
            return None

    def deliver(self, worker: str, result):
        with self.lock:
            self.workers.setdefault(worker, {"jobs": 0, "since": time.time()})["jobs"] += 1
            self.workers[worker]["seen"] = time.time()
            self.stats["done" if result.ok else "failed"] += 1
        self.results.put(result)

    def register(self, worker: str, info: dict):
        with self.lock:
            d = self.workers.setdefault(worker, {"jobs": 0, "since": time.time()})
            d.update(info)
            d["seen"] = time.time()

    def status(self) -> dict:
        with self.lock:
            now = time.time()
            ws = {k: dict(v, alive=(now - v.get("seen", 0)) < 30) for k, v in self.workers.items()}
            return {"workers": ws, "queued": self.jobs.qsize(), "stats": dict(self.stats)}


_state = None


def _get_state():
    return _state


def serve(host: str = "0.0.0.0", port: int = 5555, key: str = "statik3d", quiet=False):
    """Farm-Server starten (blockiert)."""
    global _state
    _state = _State()
    _ServerManager.register("state", callable=_get_state)
    mgr = _ServerManager(address=(host, port), authkey=key.encode())
    srv = mgr.get_server()
    if not quiet:
        print(f"Statik3D Rechnerfarm-Server auf {host}:{port}  (Strg+C beendet)")
    srv.serve_forever()


def start_server_thread(host="127.0.0.1", port=5555, key="statik3d"):
    """Server im Hintergrund-Thread (fuer Tests / GUI 'lokale Farm')."""
    global _state
    _state = _State()
    _ServerManager.register("state", callable=_get_state)
    mgr = _ServerManager(address=(host, port), authkey=key.encode())
    srv = mgr.get_server()
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return th


# --------------------------------------------------------------------------
def _connect(host, port, key, timeout=10.0):
    mgr = _ClientManager(address=(host, port), authkey=key.encode())
    t0 = time.time()
    while True:
        try:
            mgr.connect()
            return mgr.state()
        except (ConnectionRefusedError, OSError) as ex:
            if time.time() - t0 > timeout:
                raise ConnectionError(f"Farm-Server {host}:{port} nicht erreichbar: {ex}")
            time.sleep(0.5)


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------
def _worker_loop(host, port, key, name, stop_event=None):
    state = _connect(host, port, key)
    try:
        state.register(name, {"host": platform.node(), "python": platform.python_version(),
                              "version": __version__, "stand": build_sha()})
    except (EOFError, ConnectionError, OSError):
        return                          # Server schon weg (etwa beim Beenden des Programms)
    while stop_event is None or not stop_event.is_set():
        try:
            job = state.fetch(name, 2.0)
        except (EOFError, ConnectionError, OSError):
            time.sleep(2.0)
            try:
                state = _connect(host, port, key, timeout=30)
            except ConnectionError:
                continue
            continue
        if job is None:
            continue
        res = execute_job(job)
        res.worker = name
        try:
            state.deliver(name, res)
        except (EOFError, ConnectionError, OSError):
            pass


def run_worker(host="127.0.0.1", port=5555, key="statik3d", cores: int = None,
               name: str = None, quiet=False):
    """Worker mit 'cores' Prozessen starten (blockiert)."""
    cores = cores or (mp.cpu_count() or 1)
    base = name or platform.node()
    if not quiet:
        print(f"Statik3D Farm-Worker '{base}' mit {cores} Prozessen -> {host}:{port}")
    procs = []
    ctx = mp.get_context("spawn") if platform.system() != "Linux" else mp.get_context("fork")
    for i in range(cores):
        p = ctx.Process(target=_worker_loop, args=(host, port, key, f"{base}#{i+1}"),
                        daemon=True)
        p.start()
        procs.append(p)
    try:
        while any(p.is_alive() for p in procs):
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    for p in procs:
        p.terminate()


def start_worker_prozesse(host="127.0.0.1", port=5555, key="statik3d", n: int = None, name: str = None) -> tuple:
    """Worker als eigene Prozesse, ohne zu blockieren (Rechenhilfe-Fenster).
    Rueckgabe (stoppen, prozesse): ``stoppen()`` beendet sie."""
    n = int(n or (mp.cpu_count() or 1))
    base = name or platform.node()
    ctx = mp.get_context("spawn") if platform.system() != "Linux" else mp.get_context("fork")
    procs = []
    for i in range(n):
        p = ctx.Process(target=_worker_loop, args=(host, port, key, f"{base}#{i + 1}"), daemon=True)
        p.start()
        procs.append(p)

    def stoppen():
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=5.0)

    return stoppen, procs


def start_worker_threads(host="127.0.0.1", port=5555, key="statik3d", n=2, name="local"):
    """Worker als Threads im aktuellen Prozess (Tests, GUI 'lokale Farm')."""
    stop = threading.Event()
    ths = []
    for i in range(n):
        th = threading.Thread(target=_worker_loop, args=(host, port, key, f"{name}#{i+1}", stop),
                              daemon=True)
        th.start()
        ths.append(th)
    return stop, ths


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class FarmClient:
    def __init__(self, host="127.0.0.1", port=5555, key="statik3d"):
        self.host, self.port, self.key = host, port, key
        self.state = _connect(host, port, key)

    def status(self) -> dict:
        return self.state.status()

    def describe(self) -> str:
        st = self.status()
        alive = [k for k, v in st["workers"].items() if v.get("alive")]
        eigen = build_sha()
        fremd = sorted({v.get("host", k) for k, v in st["workers"].items()
                        if v.get("alive") and eigen and v.get("stand") and v.get("stand") != eigen})
        return (f"Farm {self.host}:{self.port}: {len(alive)} Worker aktiv, "
                f"{st['queued']} Auftraege wartend, {st['stats']['done']} erledigt"
                + (f" - ACHTUNG, anderer Programmstand auf {', '.join(fremd)}" if fremd else ""))

    def wait_for_workers(self, seconds: float = 10.0) -> int:
        """Auf mindestens einen aktiven Worker warten; Rueckgabe: Anzahl."""
        t0 = time.time()
        while True:
            st = self.status()
            n = sum(1 for v in st["workers"].values() if v.get("alive"))
            if n or time.time() - t0 > seconds:
                return n
            time.sleep(0.25)

    def run(self, jobs: list[Job], progress=None, timeout: float = 3600.0,
            wait_workers: float = 10.0) -> list[JobResult]:
        for i, j in enumerate(jobs):
            j.id = i
        if not self.wait_for_workers(wait_workers):
            raise RuntimeError("Kein Farm-Worker aktiv - bitte Worker starten "
                               "(python -m statik3d.farm worker ...)")
        for j in jobs:
            self.state.submit(j)
        results: dict[int, JobResult] = {}
        t0 = time.time()
        while len(results) < len(jobs):
            r = self.state.get_result(1.0)
            if r is not None:
                results[r.id] = r
                if progress:
                    progress(len(results), len(jobs))
            elif time.time() - t0 > timeout:
                raise TimeoutError(f"Farm: nur {len(results)} von {len(jobs)} Ergebnissen "
                                   f"nach {timeout:.0f} s")
        return [results[j.id] for j in jobs]


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Statik3D Rechnerfarm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("server", "worker", "status"):
        p = sub.add_parser(name)
        p.add_argument("--host", default="0.0.0.0" if name == "server" else "127.0.0.1")
        p.add_argument("--port", type=int, default=5555)
        p.add_argument("--key", default="statik3d")
        if name == "worker":
            p.add_argument("--cores", type=int, default=None)
            p.add_argument("--name", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "server":
        serve(a.host, a.port, a.key)
    elif a.cmd == "worker":
        run_worker(a.host, a.port, a.key, a.cores, a.name)
    else:
        c = FarmClient(a.host, a.port, a.key)
        st = c.status()
        print(c.describe())
        for k, v in st["workers"].items():
            print(f"  {k:24s} {'aktiv' if v.get('alive') else 'inaktiv':8s} "
                  f"Auftraege: {v.get('jobs', 0)}  Rechner: {v.get('host', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
