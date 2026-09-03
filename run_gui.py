#!/usr/bin/env python3
"""Startet die Statik3D-Oberflaeche (Doppelklick, python run_gui.py oder Statik3D.exe).

    --version      Versionsnummer ausgeben
    --selbsttest   Pakete laden, Beispiel rechnen, statik3d_selbsttest.txt schreiben (Build-Pruefung)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _selftest() -> int:
    import numpy, scipy  # noqa: F401
    import PySide6, pyvista, pyvistaqt  # noqa: F401
    from statik3d import solver, examples_lib, update
    from statik3d.web import server  # noqa: F401
    r = solver.solve_static(examples_lib.frame_example())
    text = f"{update.describe()}\nBeispiel Rahmen: umax = {r.umag.max() * 1000:.3f} mm\n"
    with open("statik3d_selbsttest.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0


def _start():
    if "--version" in sys.argv:
        from statik3d import __version__
        print(__version__)
        sys.exit(0)
    if "--selbsttest" in sys.argv:
        sys.exit(_selftest())
    try:
        from statik3d.gui.main import main
    except ImportError as ex:
        print("Fehlende Abhaengigkeit:", ex)
        print("Bitte installieren:  pip install -r requirements.txt")
        sys.exit(1)
    main()


if __name__ == "__main__":       # wichtig fuer multiprocessing (Windows: spawn / exe)
    import multiprocessing
    multiprocessing.freeze_support()
    _start()
