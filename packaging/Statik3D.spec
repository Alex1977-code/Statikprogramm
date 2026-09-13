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
# Nachgeladene Werkzeuge (statik3d.werkzeuge): gmsh.py und Netgen kommen aus
# dem Werkzeugordner des Anwenders und brauchen diese Standardmodule, die
# das Programm selbst sonst nicht importiert
hiddenimports += ["platform", "signal", "struct", "ctypes.util", "importlib.metadata", "hashlib"]
hiddenimports += collect_submodules("vtkmodules")
for optional in ("pypardiso", "pyamg", "reportlab", "svglib", "qrcode"):
    try:
        __import__(optional)
        hiddenimports.append(optional)
    except ImportError:
        pass
# PyAMG (MIT) kommt mit in die exe - samt seinem Rechenkern amg_core, den
# PyInstaller sonst nicht sieht. GPL-Loeser (CHOLMOD, UMFPACK) und gmsh
# bleiben draussen (Benutzerhandbuch Kap. 9, Lizenzen).
try:
    __import__("pyamg")
    hiddenimports += collect_submodules("pyamg")
except ImportError:
    pass
# MUMPS (CeCILL-C) kommt ebenfalls mit: Paket "mumps" aus packaging/ (eigener
# Windows-Bau, docs/MUMPS_Windows_Bauanleitung.md). Die DLLs liegen im
# Paketordner _lib und mumps/__init__.py laedt sie von dort
# (os.add_dll_directory) - darum kommen sie als datas an denselben Ort und
# nicht als binaries: PyInstaller wuerde ihre Abhaengigkeiten sonst ein
# zweites Mal in die Wurzel legen. Der Ordner LIZENZ liegt bei, weil die
# CeCILL-C den Lizenztext und die Urheberhinweise neben der Weitergabe
# verlangt (Art. 5.3.1 und 6.4).
try:
    import glob as _glob
    import mumps as _mumps
    _n_dll = 0
    for datei in _glob.glob(os.path.join(_mumps.LIB_DIR, "*")):
        datas.append((datei, os.path.join("mumps", "_lib")))
        _n_dll += datei.lower().endswith(".dll")
    for wurzel, _d, dateien in os.walk(_mumps.LIZENZ_DIR):
        for datei in dateien:
            datas.append((os.path.join(wurzel, datei),
                          os.path.join("mumps", os.path.relpath(wurzel, os.path.dirname(_mumps.LIZENZ_DIR)))))
    hiddenimports.append("mumps")
    print(f"[Statik3D] MUMPS {_mumps.MUMPS_VERSION}: {_n_dll} DLLs aus {_mumps.LIB_DIR}")
except ImportError:
    print("[Statik3D] WARNUNG: kein Paket mumps - der Selbsttest der exe wird rot")


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
