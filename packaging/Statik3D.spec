# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Rezept:  pyinstaller --noconfirm packaging/Statik3D.spec   (Windows)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(root, "statik3d", "web", "static"), os.path.join("statik3d", "web", "static")),
    (os.path.join(root, "docs"), "docs"),
    (os.path.join(root, "README.md"), "."),
]
datas += collect_data_files("pyvista")
datas += collect_data_files("pyvistaqt")

hiddenimports = ["pyvistaqt", "zstandard", "statik3d.web.server", "statik3d.update", "statik3d.farm",
                 "statik3d.jobs", "statik3d.importers", "statik3d.report", "statik3d.ec3",
                 "scipy.sparse.csgraph._validation", "scipy.special._cdflib",
                 "vtkmodules.all", "vtkmodules.util.data_model", "vtkmodules.util.execution_model"]
hiddenimports += collect_submodules("statik3d")
hiddenimports += collect_submodules("vtkmodules")
for optional in ("pypardiso", "reportlab", "svglib", "qrcode"):
    try:
        __import__(optional)
        hiddenimports.append(optional)
    except ImportError:
        pass

a = Analysis(
    [os.path.join(root, "run_gui.py")],
    pathex=[root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "jupyter", "pytest", "PyQt5", "PyQt6", "matplotlib.tests"],   # matplotlib: von pyvista benoetigt
    noarchive=False,
)
pyz = PYZ(a.pure)
# Startbild schon beim Auspacken der exe (Tcl/Tk des Build-Python; tkinter
# selbst bleibt ausgeschlossen, die Splash-Stufe bringt ihre Bibliotheken
# selbst mit). run_gui.py schliesst es, sobald Qt das Startbild uebernimmt.
#
# Kein text_font: PyInstaller setzt den Namen unmaskiert in das Tcl-Skript
# („font create myFont -family Segoe UI“) - ein Leerzeichen im Namen bricht
# das Skript ab, bevor Bild und Rahmenlosigkeit gesetzt sind, und es bleibt
# ein leeres Fenster mit dem Titel „tk“ stehen. Die Vorgabeschrift ist auf
# Windows ohnehin Segoe UI.
splash = Splash(
    os.path.join(SPECPATH, "splash.png"),
    binaries=a.binaries,
    datas=a.datas,
    text_pos=(24, 268),
    text_size=10,
    text_color="#dfe8f2",
    text_default="Statik3D wird gestartet …",
    minify_script=True,
    always_on_top=False,
)
exe = EXE(
    pyz,
    a.scripts,
    splash,
    splash.binaries,
    a.binaries,
    a.datas,
    [],
    name="Statik3D",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join(SPECPATH, "statik3d.ico"),
    version=None,
)
