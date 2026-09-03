"""
Export von Statikmodellen in fremde Formate.

    .json    Statik3D-Modell (verlustfrei)
    .dxf     AutoCAD DXF: Knoten, Staebe, Schalen, Lager
    .ifc     IFC 4 Statikmodell (Structural Analysis View)
    .xlsx    SAF - Structural Analysis Format (RFEM 6, SCIA, Allplan, ...)
    .csv     Tabellen im RFEM-Aufbau (ein Blatt je Datei, Ordner)
    .sdnf    Steel Detailing Neutral Format (HiCAD, Tekla, SDS/2)
    .nc1     DSTV-NC, je Stab eine Datei (Ordner oder ZIP)
    .inp     Abaqus / CalculiX
    .bdf     Nastran Bulk Data
    .stl     Oberflaechennetz (Dreiecke)
    .vtu     VTK-Unstructured-Grid fuer ParaView, mit Verformung und Spannung
    .sza     HiCAD-Archiv (Behaelter) - siehe Einschraenkung in hicad.py

    from statik3d.exporters import export_model, FORMATS
    export_model(m, "modell.sdnf")
    print(FORMATS)
"""
from __future__ import annotations

import os

from ..model import Model

#: Endung -> (Beschreibung, Modul, Funktion)
FORMATS: dict[str, tuple] = {
    ".json": ("Statik3D-Modell (verlustfrei)", None, None),
    ".dxf": ("AutoCAD DXF - Staebe als Linien, Schalen als 3DFACE", "dxf", "write_dxf"),
    ".ifc": ("IFC 4 Statikmodell (Structural Analysis View)", "ifc", "write_ifc"),
    ".xlsx": ("SAF - Structural Analysis Format", "saf", "write_saf"),
    ".csv": ("Tabellen im RFEM-Aufbau (Ordner)", "tables", "write_tables"),
    ".sdnf": ("SDNF - Steel Detailing Neutral Format", "sdnf", "write_sdnf"),
    ".nc1": ("DSTV-NC - je Stab eine Datei (Ordner oder ZIP)", "dstv", "write_dstv"),
    ".inp": ("Abaqus / CalculiX", "abaqus", "write_inp"),
    ".bdf": ("Nastran Bulk Data", "nastran", "write_bdf"),
    ".stl": ("STL-Oberflaechennetz", "stl", "write_stl"),
    ".vtu": ("VTK fuer ParaView (mit Verformung und Spannung)", "vtk", "write_vtu"),
    ".sza": ("HiCAD-Archiv (Behaelter)", "hicad", "write_sza"),
}


def formats() -> list[tuple[str, str]]:
    """[(Endung, Beschreibung)] aller Ausgabeformate."""
    return [(e, v[0]) for e, v in FORMATS.items()]


def file_filter() -> str:
    """Filterzeichenkette fuer Qt-Speicherdialoge."""
    parts = [f"{d} (*{e})" for e, d in formats()]
    parts.append("Alle Dateien (*)")
    return ";;".join(parts)


def export_model(model: Model, path: str, results=None, log: list = None, **options) -> str:
    """Modell in das an der Endung erkannte Format schreiben. Rueckgabe: Pfad."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in FORMATS:
        raise ValueError(f"Endung '{ext or '(keine)'}' wird nicht unterstuetzt. "
                         "Moeglich: " + ", ".join(sorted(FORMATS)))
    if ext == ".json":
        model.save(path)
        return path
    _desc, modname, func = FORMATS[ext]
    mod = __import__(f"statik3d.exporters.{modname}", fromlist=[func])
    return getattr(mod, func)(model, path, results=results, log=log, **options)
