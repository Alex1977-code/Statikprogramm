"""Programmsymbol statik3d.ico aus der Zeichnung in statik3d/gui/symbole.py.

Dieselbe Zeichnung, die das Fenster und die Taskleiste zeigen, wird hier in
allen Groessen gerendert und als Windows-Symboldatei fuer die exe abgelegt
(PyInstaller: ``icon=`` in Statik3D.spec). Daneben entstehen statik3d.png
(256 px) fuer README und Handbuch und splash.png, das Startbild, das der
Packer schon beim Auspacken der exe zeigt (``Splash`` in Statik3D.spec).

    python packaging/make_icon.py
"""
import io
import os
import sys

if sys.platform.startswith("win"):
    # Die Plattform offscreen hat auf Windows keine Schriftdatenbank: ohne
    # QT_QPA_FONTDIR zeichnet sie jeden Buchstaben als Kaestchen - und genau
    # so saehe dann das Startbild des Packers aus (acht Kaestchen statt
    # „Statik3D"). Mit dem Schriftenordner von Windows findet sie Segoe UI.
    os.environ.setdefault("QT_QPA_FONTDIR",
                          os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(here))

from PySide6 import QtCore, QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from statik3d.gui import symbole as sym  # noqa: E402

sizes = [256, 128, 64, 48, 32, 16]


def png_bytes(groesse: int) -> bytes:
    pm = sym.programmbild(groesse)
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())


out_png = os.path.join(here, "statik3d.png")
with open(out_png, "wb") as f:
    f.write(png_bytes(256))
# Startbild fuer den Packer (PyInstaller zeigt es schon beim Auspacken)
from statik3d import __version__  # noqa: E402
from statik3d.gui import start  # noqa: E402
try:
    from statik3d.update import build_info
    stand = (build_info().get("sha") or "")[:7]
except Exception:  # noqa: BLE001
    stand = ""
out_splash = os.path.join(here, "splash.png")
if start.schrift_vorhanden():
    start.startbild(__version__, stand).save(out_splash, "PNG")
    print(out_splash)
else:
    # Lieber das eingecheckte Bild mit alter Fassungsnummer als eines aus
    # Kaestchen: ohne Schrift wird nicht neu gerendert.
    print(f"WARNUNG: keine Schrift gefunden (Plattform {os.environ.get('QT_QPA_PLATFORM')}, "
          f"QT_QPA_FONTDIR={os.environ.get('QT_QPA_FONTDIR')}) - {out_splash} bleibt, wie es "
          "eingecheckt ist")
out = os.path.join(here, "statik3d.ico")
try:
    from PIL import Image
    frames = [Image.open(io.BytesIO(png_bytes(s))).convert("RGBA") for s in sizes]
    frames[0].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[1:])
except ImportError:
    # Ohne Pillow schreibt Qt ein Symbol mit einer Groesse
    sym.programmbild(256).save(out, "ICO")
print(out)
print(out_png)
