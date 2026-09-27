"""Paketgeruest: Import, Vertragsversion, Entry Points fcm und hybrid, Importregeln.

Aufruf: python -m tests.volumen3d.test_paket
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.volumen3d._pruef import check, lauf  # noqa: E402


def test_import():
    import statik3d_contracts as V
    import volumen3d
    check("volumen3d importierbar, nennt passende Vertragsversion",
          V.vertragsversion_passt(volumen3d.CONTRACT_VERSION), volumen3d.CONTRACT_VERSION)


def test_entry_points():
    from importlib import metadata
    eps = {ep.name: ep.value for ep in metadata.entry_points(group="statik3d.solid_solvers")}
    check("Entry Point fcm -> volumen3d.api:FcmSolver", eps.get("fcm") == "volumen3d.api:FcmSolver", str(eps))
    eps2 = {ep.name: ep.value for ep in metadata.entry_points(group="statik3d.assembly_solvers")}
    check("Entry Point hybrid -> volumen3d.api:HybridAssemblySolver",
          eps2.get("hybrid") == "volumen3d.api:HybridAssemblySolver", str(eps2))


def test_importregeln():
    """Vertrag Abschnitt 1: volumen3d importiert niemals statik3d, keine Qt-/VTK-Bibliothek."""
    import ast
    import volumen3d
    wurzel = os.path.dirname(os.path.abspath(volumen3d.__file__))
    verstoesse = []
    for ordner, _, dateien in os.walk(wurzel):
        for name in dateien:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(ordner, name), encoding="utf-8") as f:
                baum = ast.parse(f.read(), filename=name)
            for kn in ast.walk(baum):
                if isinstance(kn, ast.Import):
                    mods = [a.name for a in kn.names]
                elif isinstance(kn, ast.ImportFrom) and not kn.level:
                    mods = [kn.module or ""]
                else:
                    continue
                for m in mods:
                    if m.split(".")[0] in ("statik3d", "PySide6", "pyvista", "vtk"):
                        verstoesse.append(f"{name}: {m}")
    check("volumen3d importiert weder statik3d noch Qt/VTK", not verstoesse, "; ".join(verstoesse))


if __name__ == "__main__":
    sys.exit(lauf([test_import, test_entry_points, test_importregeln]))
