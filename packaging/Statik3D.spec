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
for optional in ("pypardiso", "pyamg", "ama", "reportlab", "svglib", "qrcode"):
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
# ama (eigener Rechenkern, Rust, keine Fremdlizenz) gehoert genauso in die exe,
# stand aber nicht in dieser Datei: in der exe erschien er als "nicht
# installiert", und der Anwender konnte ihn weder waehlen noch beschaffen
# (19.09.2026). collect_submodules findet auch die Erweiterung ama.ama_kern
# (ama_kern.cp311-win_amd64.pyd); collect_dynamic_libs("ama") liefert dagegen
# [] - gemessen: die .pyd ist ein Modul, keine lose DLL. Das Rad kommt aus
# einem eigenen Bau (packaging/ama-0.1.0-cp311-cp311-win_amd64.whl, Quelle
# Desktop/Gleichungsloeser) - nach einem Neubau die Datei dort ersetzen und
# den Namen in .github/workflows/windows-exe.yml nachziehen.
try:
    __import__("ama")
    hiddenimports += collect_submodules("ama")
except ImportError:
    pass
# MUMPS (CeCILL-C) kommt **nicht** mit: das Programm laedt das Rad aus
# packaging/ beim Start aus dem Release "werkzeuge" nach (statik3d/werkzeuge.py,
# Anweisung MUMPS_Nachladen_Anweisung.md, 13.09.2026) - die exe bliebe sonst
# 63 MB groesser (434 statt 371 MB), und MUMPS ist eine Wahl neben PARDISO.
# "mumps" steht darum in excludes: sobald es in der Bau-Umgebung installiert
# ist, naehme PyInstaller es ueber "import mumps" in solver.py sonst mit.
# Der Wrapper braucht Standardmodule, die das Programm selbst nicht importiert.
hiddenimports += ["glob", "ctypes", "site"]


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
    excludes=["tkinter", "IPython", "jupyter", "pytest", "PyQt5", "PyQt6", "matplotlib.tests",
              "mumps"],           # MUMPS wird beim Start nachgeladen, nicht mitgeliefert   # matplotlib: von pyvista benoetigt
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
