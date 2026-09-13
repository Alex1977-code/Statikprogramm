"""Rechnerfarm fuer den Anwender: Ankuendigung per UDP und Suche, eigene
Adressen, Worker als Prozesse ohne Blockieren, Stand (Commit) je Worker im
Status. Alles auf dem eigenen Rechner (Loopback) mit freien Ports.
"""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import farm                                      # noqa: E402
from statik3d.parallel import Job                              # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")


def freier_port(art=socket.SOCK_STREAM) -> int:
    s = socket.socket(socket.AF_INET, art)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_ankuendigung_und_suche():
    port_udp = freier_port(socket.SOCK_DGRAM)
    stop = farm.start_ankuendigung(5599, name="Arbeitsplatz-Probe", takt=0.3, ziel_port=port_udp,
                                   zusatz_ziele=("127.0.0.1",))
    try:
        gefunden = farm.server_suchen(1.5, port=port_udp)
        # Auf dem eigenen Rechner kommt der Rundruf zweimal an: ueber die
        # Netzadresse (Broadcast) und ueber 127.0.0.1 (zusatz_ziele) - je Absender ein Eintrag
        check("die Ankuendigung wird gefunden - Name, Port, Version und Stand kommen mit",
              len(gefunden) >= 1 and all(d["port"] == 5599 and d["name"] == "Arbeitsplatz-Probe"
                                         and d["version"] and "stand" in d for d in gefunden), str(gefunden))
        check("darunter der Absender Loopback (Zusatzziel 127.0.0.1)", any(d["host"] == "127.0.0.1" for d in gefunden))
    finally:
        stop.set()
    time.sleep(0.5)
    check("nach dem Stopp kommt nichts mehr", farm.server_suchen(0.8, port=port_udp) == [])
    adressen = farm.eigene_adressen()
    check("eigene Adressen: IPv4 ohne 127.x (auf einem Rechner ohne Netz leer)",
          all(a.count(".") == 3 and not a.startswith("127.") for a in adressen), str(adressen))


def test_worker_prozesse_und_stand():
    port = freier_port()
    farm.start_server_thread("127.0.0.1", port, "probe")
    stoppen, procs = farm.start_worker_prozesse("127.0.0.1", port, "probe", n=1, name="hilfe")
    try:
        client = farm.FarmClient("127.0.0.1", port, "probe")
        n = client.wait_for_workers(60.0)
        check("ein Worker-Prozess meldet sich an (Start der exe/Python im Spawn)", n == 1, f"{n} aktiv")
        st = client.status()
        w = st["workers"].get("hilfe#1", {})
        check("der Worker nennt Version und Stand (Commit) des Programms",
              w.get("version") == farm.__version__ and "stand" in w, str({k: w.get(k) for k in ('version', 'stand', 'host')}))
        res = client.run([Job("ping", {"x": 1})], timeout=60)
        check("ein Auftrag laeuft ueber den Prozess", res[0].ok and res[0].worker == "hilfe#1", str(res[0])[:80])
        check("describe() nennt keinen fremden Stand, solange alle gleich sind",
              "anderer Programmstand" not in client.describe(), client.describe())
        # Ein fremder Stand faellt im Status auf
        client.state.register("fremd#1", {"host": "anderer-rechner", "version": farm.__version__, "stand": "0000000"})
        text = client.describe()
        check("ein Worker mit anderem Stand wird in describe() genannt",
              ("anderer Programmstand" in text and "anderer-rechner" in text) or not farm.build_sha(), text)
    finally:
        stoppen()
    check("stoppen() beendet den Prozess", not any(p.is_alive() for p in procs))


def main():
    for t in (test_ankuendigung_und_suche, test_worker_prozesse_und_stand):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
