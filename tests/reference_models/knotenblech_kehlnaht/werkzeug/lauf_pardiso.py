# -*- coding: utf-8 -*-
"""Das Laufskript der Knotenblech-Referenz mit fest eingestelltem PARDISO (02.10.2026).

knotenblech_lauf.py aus dem festen Arbeitsbaum laeuft unveraendert; vorher wird
nur solver_backend = "pardiso" gesetzt. Mit "auto" wiche der Loeser bei einem
Speicherfehler von PARDISO auf einen anderen Direktloeser aus, der noch mehr
Speicher braucht. Mit "pardiso" bricht der Lauf dann ab. Danach stehen Speicher
und Laufzeit in <ausgabeordner>/speicher.json.

Aufruf: python lauf_pardiso.py <baum> <netz.inp> <ausgabeordner> <eichung|referenz>
"""
import json
import os
import sys
import time

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)
import speicher  # noqa: E402


def main():
    baum, netz, aus, modus = sys.argv[1:5]
    sys.path.insert(0, baum)
    from statik3d import parallel
    parallel.configure(solver_backend="pardiso")
    sys.path.insert(0, os.path.join(baum, "tests", "reference_models", "knotenblech_kehlnaht", "werkzeug"))
    import knotenblech_lauf as kl
    vorher = speicher.system()
    t0 = time.perf_counter()
    kl.main()
    out = {"modus": modus, "solver_backend": parallel.settings().solver_backend,
           "zeit_gesamt_s": round(time.perf_counter() - t0, 1),
           "system_vorher": vorher, "prozess": speicher.prozess(), "system_nachher": speicher.system()}
    with open(os.path.join(aus, "speicher.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
