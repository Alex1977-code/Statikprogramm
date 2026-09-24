"""Oberflaeche von Statik3D.

Das Hauptfenster (gui.main) wird erst geladen, wenn es gebraucht wird. Bis
zum 23.09.2026 stand hier ``from .main import main, MainWindow``: dann lud
jedes ``from statik3d.gui import tabellen`` (oder viewport, start,
rechenliste ...) gui.main samt pyvista, pyvistaqt und VTK mit, auch in den
Pruefungen ohne Fenster (Befund B147; tests/test_gzg.py prueft das).

``statik3d.gui.MainWindow`` bleibt erreichbar (PEP 562, laedt gui.main beim
ersten Zugriff). ``statik3d.gui.main`` ist das Modul - wie nach jedem
``import statik3d.gui.main``; die Startfunktion ist ``statik3d.gui.main.main``
(so rufen sie run_gui.py, ``python -m statik3d.gui`` und pyproject.toml).
"""
import importlib


def __getattr__(name):
    if name == "main":
        return importlib.import_module(".main", __name__)
    if name == "MainWindow":
        return importlib.import_module(".main", __name__).MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
