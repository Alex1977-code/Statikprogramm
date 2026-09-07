# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Rezept:  pyinstaller --noconfirm packaging/Statik3D.spec   (Windows)
import os
import sys

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


# --------------------------------------------------------------------------
# Intel MKL: der Mehrkern-Gleichungsloeser
# --------------------------------------------------------------------------
# Ohne MKL faellt LinearSolver auf SuperLU zurueck, und SuperLU ist streng
# einkernig - am Drehlagermodell hiess das 97 % eines Kerns bei 32 vorhandenen.
# Gemessen an einem Wuerfel mit 34.914 FHG: SuperLU 12,25 s und +0,49 GB,
# PARDISO mit vier Threads 1,38 s und +0,39 GB. Also 8,9-mal schneller bei
# 20 % weniger Speicher, gleiche Loesung.
#
# Welche Bibliotheken PARDISO wirklich laedt, wurde aus /proc/self/maps
# abgelesen (nicht geraten): rt, core, intel_lp64, intel_thread, der zur CPU
# passende Rechenkern und sein vml-Gegenstueck, dazu libiomp5 und tbbmalloc.
# Mitgenommen werden alle Rechenkerne (def/avx2/avx512/avx10/mc3), damit die
# exe auf jeder Maschine den schnellsten nimmt. Ausgelassen wird nur, was
# sicher nicht gebraucht wird: die Cluster-Teile (scalapack, blacs, cdft) und
# die TBB-Variante der Threadschicht - gerechnet wird mit intel_thread.
def _mkl_dlls():
    import glob
    fund = []
    orte = [os.path.join(sys.prefix, "Library", "bin"), os.path.join(sys.prefix, "lib"),
            os.path.join(sys.prefix, "bin"), "/usr/local/lib"]
    raus = ("scalapack", "blacs", "cdft", "tbb_thread")
    for ort in orte:
        for muster in ("mkl_*.dll", "libmkl_*.so*", "libiomp5*", "libomp*",
                       "tbbmalloc*", "libtbbmalloc*"):
            for datei in glob.glob(os.path.join(ort, muster)):
                name = os.path.basename(datei).lower()
                if any(x in name for x in raus):
                    continue
                fund.append((datei, "."))
    return fund


mkl_binaries = []
try:
    __import__("pypardiso")
    mkl_binaries = _mkl_dlls()
except ImportError:
    pass
if mkl_binaries:
    mb = sum(os.path.getsize(f) for f, _ in mkl_binaries) / 1e6
    print(f"[Statik3D] MKL fuer PARDISO: {len(mkl_binaries)} Dateien, {mb:.0f} MB")
else:
    print("[Statik3D] WARNUNG: kein MKL gefunden - der Loeser bleibt einkernig (SuperLU)")

a = Analysis(
    [os.path.join(root, "run_gui.py")],
    pathex=[root],
    binaries=mkl_binaries,
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
