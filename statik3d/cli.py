"""
Kommandozeilen-Betrieb (ohne GUI).

    python -m statik3d.cli modell.json                      # alle Lastfaelle + Kombinationen
    python -m statik3d.cli modell.json --nachweise --ermuedung --bericht bericht.html
    python -m statik3d.cli --beispiel hall --nachweise --bericht halle.html
    python -m statik3d.cli --beispiel frame --analyse knicken
    python -m statik3d.cli --import modell.ifc --speichern modell.json
    python -m statik3d.cli modell.json --kerne 8            # 8 Prozesse
    python -m statik3d.cli modell.json --farm 192.168.1.10:5555 --schluessel geheim
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

from .model import Model
from . import solver, parallel
from .examples_lib import build_example, EXAMPLES


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Statik3D - FEM-Berechnung ohne GUI")
    ap.add_argument("datei", nargs="?", help="Modelldatei (.json) oder Importdatei")
    ap.add_argument("--beispiel", choices=list(EXAMPLES),
                    help="statt einer Datei ein eingebautes Beispiel rechnen")
    ap.add_argument("--import", dest="import_file", help="Fremdformat importieren "
                    "(DXF, IFC, SAF/RFEM-xlsx, INP, BDF, STEP/IGES/STL)")
    ap.add_argument("--einheit", type=float, default=None, help="Laengenskalierung beim Import")
    ap.add_argument("--speichern", help="Modell nach Import/Kombinationsbildung als JSON speichern")
    ap.add_argument("--analyse", default="statik",
                    choices=["statik", "lastfall", "eigenformen", "knicken"],
                    help="statik = alle Lastfaelle + Kombinationen (Standard)")
    ap.add_argument("--lastfall", help="nur diesen Lastfall rechnen (mit --analyse lastfall)")
    ap.add_argument("--kombinationen", action="store_true",
                    help="Kombinationen nach DIN EN 1990 automatisch erzeugen")
    ap.add_argument("--nachweise", action="store_true", help="Nachweise nach EC3 fuehren")
    ap.add_argument("--ermuedung", action="store_true", help="Ermuedungsnachweis (EN 1993-1-9)")
    ap.add_argument("--staebe", action="store_true", help="Staebe automatisch erkennen")
    ap.add_argument("--moden", type=int, default=6)
    ap.add_argument("--kerne", type=int, default=None, help="Anzahl lokaler Prozesse")
    ap.add_argument("--farm", help="Rechnerfarm host:port")
    ap.add_argument("--schluessel", default="statik3d", help="Farm-Schluessel")
    ap.add_argument("--csv", help="Knotenergebnisse als CSV schreiben")
    ap.add_argument("--vtk", help="Netz + Ergebnisse als .vtu schreiben (ParaView)")
    ap.add_argument("--export", action="append", default=[], metavar="DATEI",
                    help="Modell in ein fremdes Format schreiben; das Format folgt aus "
                         "der Endung (.sdnf .nc1 .zip .ifc .xlsx .csv .dxf .stl .vtu "
                         ".inp .bdf .sza .json). Mehrfach verwendbar.")
    ap.add_argument("--formate", action="store_true",
                    help="Ausgabeformate auflisten und beenden")
    ap.add_argument("--bericht", help="Statischen Bericht schreiben (.html / .pdf / .md)")
    ap.add_argument("--still", action="store_true", help="weniger Ausgabe")
    a = ap.parse_args(argv)
    if a.formate:
        from .exporters import formats as _formats
        print("Ausgabeformate (--export DATEI, Format aus der Endung):")
        for ext, beschr in _formats():
            print(f"  {ext:<7s} {beschr}")
        return 0

    log = print if not a.still else (lambda *x: None)
    if a.kerne:
        parallel.configure(workers=a.kerne)
    if a.farm:
        host, _, port = a.farm.partition(":")
        parallel.configure(backend="farm", farm_host=host, farm_port=int(port or 5555),
                           farm_key=a.schluessel)

    # ---- Modell ----
    if a.beispiel:
        m = build_example(a.beispiel)
    elif a.import_file or (a.datei and not a.datei.lower().endswith(".json")):
        from . import importers
        path = a.import_file or a.datei
        msgs: list[str] = []
        opts = {"unit_scale": a.einheit} if a.einheit else {}
        m = importers.import_file(path, log=msgs, **opts)
        for s in msgs:
            log("  " + s)
        log(f"Import: {m.nn} Knoten, {len(m.elements)} Elemente, "
            f"{len(m.load_cases)} Lastfaelle, {len(m.members)} Staebe")
    elif a.datei:
        m = Model.load(a.datei)
    else:
        ap.error("Bitte eine Modelldatei, --import oder --beispiel angeben")

    if a.staebe:
        n = len(m.auto_members())
        log(f"{n} Staebe erkannt")
    if a.kombinationen:
        from .combinations import generate_combinations
        n = len(generate_combinations(m))
        log(f"{n} Kombinationen erzeugt")
    if a.speichern:
        m.save(a.speichern)
        log(f"Modell gespeichert: {a.speichern}")

    problems = [x for x in m.check() if x.startswith("FEHLER")]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    for w in m.check():
        log(w)
    log(f"Parallelisierung: {parallel.describe()}")

    # ---- Berechnung ----
    an = None
    r = None
    if a.analyse == "statik":
        an = solver.solve_all(m, progress=log, design=a.nachweise, fatigue=a.ermuedung)
        print()
        print(an.summary())
        if an.design is not None:
            print()
            for row in an.design.table():
                print(" | ".join(f"{str(c):>12s}" for c in row))
        if an.fatigue is not None:
            print()
            for row in an.fatigue.table():
                print(" | ".join(f"{str(c):>12s}" for c in row))
        first = next(iter(an.combinations.values()), None) or next(iter(an.cases.values()))
        r = first
    elif a.analyse == "lastfall":
        r = solver.solve_static(m, log, case=a.lastfall)
        print(); print(r.summary())
    elif a.analyse == "eigenformen":
        r = solver.solve_modal(m, a.moden, log)
        print(); print(r.summary())
    else:
        r = solver.solve_buckling(m, a.moden, log, case=a.lastfall)
        print(); print(r.summary())

    # ---- Ausgabe ----
    if a.csv and r is not None:
        with open(a.csv, "w", encoding="utf-8") as f:
            f.write("Knoten;x;y;z;ux;uy;uz;rx;ry;rz\n")
            for i in range(m.nn):
                x, y, z = m.nodes[i]
                f.write(f"{i};{x:.6f};{y:.6f};{z:.6f};"
                        + ";".join(f"{v:.6e}" for v in r.u[i]) + "\n")
            if r.beam_forces:
                f.write("\nElement;N1;N2;Vy1;Vy2;Vz1;Vz2;Mt1;My1;My2;Mz1;Mz2;sigma\n")
                for e, d in sorted(r.beam_forces.items()):
                    f.write(f"{e};{d['N'][0]:.3f};{d['N'][1]:.3f};{d['Vy'][0]:.3f};{d['Vy'][1]:.3f};"
                            f"{d['Vz'][0]:.3f};{d['Vz'][1]:.3f};{d['Mt'][0]:.3f};{d['My'][0]:.3f};"
                            f"{d['My'][1]:.3f};{d['Mz'][0]:.3f};{d['Mz'][1]:.3f};{d['sig_max']:.3f}\n")
        log(f"CSV geschrieben: {a.csv}")

    if a.vtk and r is not None:
        from .gui.viewport import to_grid
        g = to_grid(m)
        g.point_data["u"] = r.u[:, :3]
        if r.node_vm is not None:
            g.point_data["vonMises"] = np.nan_to_num(r.node_vm)
        g.save(a.vtk)
        log(f"VTK geschrieben: {a.vtk}")

    for ziel in a.export:
        from .exporters import export_model as _ex
        elog = []
        try:
            out = _ex(m, ziel, results=r, log=elog)
        except Exception as ex:      # noqa: BLE001
            print(f"Export nach '{ziel}' fehlgeschlagen: {ex}", file=sys.stderr)
            continue
        for zeile in elog:
            log(zeile)
        log(f"exportiert: {out}")
    if a.bericht:
        from .report import write_report
        fmt = os.path.splitext(a.bericht)[1].lower().lstrip(".") or "html"
        fmt = {"htm": "html", "markdown": "md"}.get(fmt, fmt)
        write_report(m, an if an is not None else r, a.bericht, fmt=fmt)
        log(f"Bericht geschrieben: {a.bericht}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
