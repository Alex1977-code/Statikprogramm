#!/usr/bin/env python3
"""Startet die Statik3D-Oberflaeche (Doppelklick, python run_gui.py oder Statik3D.exe).

    --version      Versionsnummer ausgeben
    --selbsttest   Pakete laden, Beispiel rechnen, statik3d_selbsttest.txt schreiben (Build-Pruefung)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _selftest() -> int:
    """Alle Pakete laden, ein Beispiel rechnen, Ergebnis (oder Fehler) in
    statik3d_selbsttest.txt schreiben. Rueckgabe 0 = in Ordnung."""
    import traceback
    out = os.path.join(os.getcwd(), "statik3d_selbsttest.txt")
    lines, code = [], 0
    try:
        import numpy, scipy  # noqa: E401
        lines.append(f"numpy {numpy.__version__}, scipy {scipy.__version__}")
        import PySide6
        lines.append(f"PySide6 {PySide6.__version__}")
        import pyvista
        lines.append(f"pyvista {pyvista.__version__}")
        import pyvistaqt  # noqa: F401
        from statik3d import solver, examples_lib, update
        from statik3d.web import server  # noqa: F401
        lines.append(update.describe())
        r = solver.solve_static(examples_lib.frame_example())
        lines.append(f"Beispiel Rahmen: umax = {r.umag.max() * 1000:.3f} mm")
        lines.append("OK")
    except BaseException:      # noqa: BLE001 - alles in die Datei, nie ein Meldungsfenster
        lines.append(traceback.format_exc())
        code = 1
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        print("\n".join(lines))
    except Exception:          # noqa: BLE001 - ohne Konsole
        pass
    return code


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
