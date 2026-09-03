"""python -m statik3d.web [--port 8080] [--host 0.0.0.0] [--schluessel geheim]
                          [--modell datei.json | --beispiel hall] [--kerne 4] [--laut]"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    from .. import parallel
    from ..examples_lib import EXAMPLES, build_example
    from ..model import Model
    from .server import serve

    ap = argparse.ArgumentParser(description="Statik3D - Bedienung im Browser / auf dem Handy")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0",
                    help="0.0.0.0 = im ganzen Netz erreichbar, 127.0.0.1 = nur dieser Rechner")
    ap.add_argument("--schluessel", default=None,
                    help="Zugangsschlüssel (im Browser einmalig eingeben); empfohlen im Netz")
    ap.add_argument("--modell", help="Modelldatei (.json) oder Importdatei beim Start laden")
    ap.add_argument("--beispiel", choices=list(EXAMPLES), help="eingebautes Beispiel laden")
    ap.add_argument("--kerne", type=int, default=None, help="Anzahl lokaler Prozesse")
    ap.add_argument("--laut", action="store_true", help="jede Anfrage protokollieren")
    a = ap.parse_args(argv)

    if a.kerne:
        parallel.configure(workers=a.kerne)
    model = None
    if a.beispiel:
        model = build_example(a.beispiel)
    elif a.modell:
        if a.modell.lower().endswith(".json"):
            model = Model.load(a.modell)
        else:
            from ..importers import import_file
            msgs: list[str] = []
            model = import_file(a.modell, log=msgs)
            for s in msgs:
                print("  " + s)
    return serve(a.host, a.port, a.schluessel, model, quiet=not a.laut)


if __name__ == "__main__":       # wichtig fuer multiprocessing (Windows: spawn)
    sys.exit(main())
