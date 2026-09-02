#!/usr/bin/env python3
"""Startet die Statik3D-Oberflaeche (Doppelklick oder: python run_gui.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from statik3d.gui.main import main
except ImportError as ex:
    print("Fehlende Abhaengigkeit:", ex)
    print("Bitte installieren:  pip install -r requirements.txt")
    sys.exit(1)

main()
