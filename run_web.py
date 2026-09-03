#!/usr/bin/env python3
"""Startet den Statik3D-Web-Server fuer Handy/Tablet/Browser.

    python run_web.py                          # http://<PC-Adresse>:8080/
    python run_web.py --schluessel geheim --beispiel hall
    python run_web.py --modell halle.json --port 8000
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _start():
    from statik3d.web.__main__ import main
    sys.exit(main())


if __name__ == "__main__":       # wichtig fuer multiprocessing (Windows: spawn)
    _start()
