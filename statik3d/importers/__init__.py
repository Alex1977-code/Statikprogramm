"""
Import fremder Dateiformate in ein Statik3D-Modell.

    from statik3d.importers import import_file
    log = []
    model = import_file("rahmen.dxf", log=log, unit_scale=1e-3)
    print("\\n".join(log))

Unterstuetzt (siehe SUPPORTED): Statik3D-JSON, DXF, IFC (Statikmodell), SAF-xlsx,
RFEM/RSTAB-Tabellenexport (xlsx / CSV-Ordner), Abaqus/CalculiX .inp, Nastran .bdf,
CAD (STEP/IGES/BREP/STL ueber gmsh). Fuer proprietaere Binaerformate (.rf5, .rf6,
.rfem, .rstab, .fem, .ifm) wird der Exportweg erklaert (explain_format).

Alle Importer haben die Signatur  import_xxx(path, model=None, log=None, **options)
und liefern ein Modell in SI-Einheiten (m, N, Pa). 'log' ist eine Liste, an die
deutschsprachige Meldungen und Warnungen angehaengt werden.
"""
from __future__ import annotations

import os

from ..model import Model
from .. import mesher
from . import _common as C

SUPPORTED: dict[str, str] = {
    ".json": "Statik3D-Modell (JSON)",
    ".rf5": "RFEM 5-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rf6": "RFEM 6-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rs5": "RSTAB-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rs6": "RSTAB-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rs8": "RSTAB 8-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rs9": "RSTAB 9-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rfem": "RFEM-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".rstab": "RSTAB-Projektdatei - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".dxf": "AutoCAD DXF - Linien/Polylinien als Staebe, 3DFACE als Schalen",
    ".ifc": "IFC 2x3 / IFC4 - Statikmodell (Structural Analysis View) oder Bauteilachsen",
    ".xlsx": "SAF (Structural Analysis Format) oder RFEM/RSTAB-Tabellenexport (Excel)",
    ".csv": "RFEM/RSTAB-Tabellenexport (CSV, eine Tabelle je Datei bzw. Ordner)",
    ".inp": "Abaqus / CalculiX Eingabedatei",
    ".bdf": "Nastran Bulk Data",
    ".nas": "Nastran Bulk Data",
    ".dat": "Nastran Bulk Data",
    ".step": "STEP-Geometrie (Vernetzung mit gmsh)",
    ".stp": "STEP-Geometrie (Vernetzung mit gmsh)",
    ".iges": "IGES-Geometrie (Vernetzung mit gmsh)",
    ".igs": "IGES-Geometrie (Vernetzung mit gmsh)",
    ".brep": "BREP-Geometrie (Vernetzung mit gmsh)",
    ".stl": "STL-Oberflaechennetz (Vernetzung mit gmsh)",
    ".sdnf": "SDNF - Steel Detailing Neutral Format (HiCAD, Tekla, SDS/2, Advance Steel)",
    ".sdn": "SDNF - Steel Detailing Neutral Format",
    ".nc": "DSTV-NC - Stahlbauteil fuer die NC-Steuerung",
    ".nc1": "DSTV-NC - Stahlbauteil fuer die NC-Steuerung (HiCAD, Tekla, bocad)",
    ".nc2": "DSTV-NC - Stahlbauteil fuer die NC-Steuerung",
    ".dstv": "DSTV-NC - Stahlbauteil fuer die NC-Steuerung",
    ".zip": "ZIP-Behaelter - Inhalt wird bestimmt (DSTV-NC-Teile, SDNF, IFC)",
    ".sza": "HiCAD-Szene - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".kra": "HiCAD-Konstruktion - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".fga": "HiCAD-Figur - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".fig": "HiCAD-Figur - Behaelter wird untersucht und gelesen, soweit zugaenglich",
    ".vaa": "HiCAD-Variante - Behaelter wird untersucht und gelesen, soweit zugaenglich",
}

_SDNF = (".sdnf", ".sdn")
_DSTV = (".nc", ".nc1", ".nc2", ".dstv")
_HICAD = (".sza", ".kra", ".fga", ".fig", ".vaa")

_CAD = (".step", ".stp", ".iges", ".igs", ".brep", ".stl")
_NO_MEMBER_INFO = (".dxf", ".inp", ".bdf", ".nas", ".dat")

PROPRIETARY: dict[str, str] = {
    ".rf5": ("RFEM 5-Projektdatei (.rf5) ist ein proprietaeres Binaerformat und kann nicht "
             "direkt gelesen werden. Bitte in RFEM exportieren: "
             "Datei → Exportieren → IFC (Statikmodell / Structural Analysis View), "
             "oder Datei → Exportieren → Tabellen nach Excel/CSV "
             "(Knoten, Linien, Staebe, Querschnitte, Knotenlager, Lastfaelle, Lasten)."),
    ".rf6": ("RFEM 6-Projektdatei (.rf6) ist ein proprietaeres Binaerformat und kann nicht "
             "direkt gelesen werden. Bitte in RFEM 6 exportieren: "
             "Datei → Exportieren → IFC (Statikmodell / Structural Analysis View), "
             "Datei → Exportieren → SAF (.xlsx) oder Tabellen nach Excel/CSV."),
    ".rfem": ("RFEM-Projektdatei (.rfem) ist ein proprietaeres Binaerformat. Bitte in RFEM "
              "exportieren: Datei → Exportieren → IFC (Statikmodell / Structural Analysis "
              "View), SAF (.xlsx) oder Tabellen nach Excel/CSV."),
    ".rstab": ("RSTAB-Projektdatei (.rstab) ist ein proprietaeres Binaerformat. Bitte in RSTAB "
               "exportieren: Datei → Exportieren → IFC (Statikmodell / Structural Analysis "
               "View), SAF (.xlsx) oder Tabellen nach Excel/CSV."),
    ".fem": ("InfoCAD-Projektdatei (.fem) ist ein proprietaeres Format und kann nicht direkt "
             "gelesen werden. Bitte in InfoCAD exportieren: IFC-Statikmodell "
             "(Datei → Export → IFC, Statikmodell) oder DXF (Datei → Export → DXF)."),
    ".ifm": ("InfoCAD-Modelldatei (.ifm) ist ein proprietaeres Format und kann nicht direkt "
             "gelesen werden. Bitte in InfoCAD exportieren: IFC-Statikmodell "
             "(Datei → Export → IFC, Statikmodell) oder DXF (Datei → Export → DXF)."),
}


_NATIVE = (".rf3", ".rf4", ".rf5", ".rf6", ".rfem",
           ".rs5", ".rs6", ".rs7", ".rs8", ".rs9", ".rstab")


def explain_format(path: str) -> str:
    """Erklaerung zum Dateiformat (Unterstuetzung bzw. Exportweg) als deutscher Text."""
    if os.path.isdir(path):
        return ("Ordner: wird als RFEM/RSTAB-Tabellenexport (CSV-Dateien je Tabelle) "
                "gelesen.")
    ext = os.path.splitext(path)[1].lower()
    if ext in PROPRIETARY:
        return PROPRIETARY[ext]
    if ext in SUPPORTED:
        desc = SUPPORTED[ext]
        if ext in _CAD:
            desc += (" - benoetigt das Python-Paket 'gmsh' (pip install gmsh)"
                     if not mesher.HAVE_GMSH else " - gmsh vorhanden")
        return f"{ext}: {desc}"
    if ext in (".xls",):
        return ("Altes Excel-Binaerformat (.xls) wird nicht gelesen - bitte in Excel als "
                ".xlsx speichern.")
    return (f"Dateiendung '{ext or '(keine)'}' wird nicht unterstuetzt. Unterstuetzt: "
            + ", ".join(sorted(SUPPORTED)))


def file_filter() -> str:
    """Filterzeichenkette fuer Qt-Dateidialoge (QFileDialog.getOpenFileName)."""
    all_ext = " ".join(f"*{e}" for e in SUPPORTED)
    parts = [f"Alle unterstuetzten Formate ({all_ext})",
             "Statik3D-Modell (*.json)",
             "DXF-Zeichnung (*.dxf)",
             "IFC-Modell (*.ifc)",
             "SAF / RFEM-Tabellen Excel (*.xlsx)",
             "RFEM-Tabellen CSV (*.csv)",
             "Abaqus / CalculiX (*.inp)",
             "Nastran Bulk Data (*.bdf *.nas *.dat)",
             "RFEM / RSTAB Projektdatei (*.rf5 *.rf6 *.rs5 *.rs6 *.rs8 *.rs9 *.rfem *.rstab)",
             "SDNF Stahlbaumodell (*.sdnf *.sdn)",
             "DSTV-NC Stahlbauteile (*.nc *.nc1 *.nc2 *.dstv)",
             "HiCAD Szene / Bauteil (*.sza *.kra *.fga *.fig *.vaa)",
             "ZIP mit DSTV-NC, SDNF oder IFC (*.zip)",
             "CAD-Geometrie (*.step *.stp *.iges *.igs *.brep *.stl)",
             "Alle Dateien (*)"]
    return ";;".join(parts)


def _detect(path: str) -> str:
    if os.path.isdir(path):
        names = os.listdir(path)
        if any(os.path.splitext(n)[1].lower() in _DSTV for n in names):
            return "dstv"                   # Ordner mit DSTV-NC-Teilen
        return "rfem"                       # Ordner mit RFEM-Tabellen (CSV)
    ext = os.path.splitext(path)[1].lower()
    if ext in _NATIVE:
        return "native"                     # Behaelter wird untersucht (rfem_native)
    if ext in _SDNF:
        return "sdnf"
    if ext in _DSTV:
        return "dstv"
    if ext in _HICAD:
        return "hicad"
    if ext == ".zip":
        return _detect_zip(path)
    if ext in PROPRIETARY:
        raise ImportError(PROPRIETARY[ext])
    if ext == ".json":
        return "json"
    if ext == ".dxf":
        return "dxf"
    if ext == ".ifc":
        return "ifc"
    if ext in (".xlsx", ".xlsm"):
        return "xlsx"
    if ext == ".csv":
        return "rfem"
    if ext in _NATIVE:
        return "native"
    if ext == ".inp":
        return "inp"
    if ext in (".bdf", ".nas", ".dat"):
        return "bdf"
    if ext in _CAD:
        return "cad"
    raise ImportError(explain_format(path))


def _detect_zip(path: str) -> str:
    """Inhalt eines ZIP-Behaelters bestimmen: DSTV-NC-Teile, SDNF oder IFC."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            namen = z.namelist()
    except zipfile.BadZipFile as ex:
        raise ImportError(f"{os.path.basename(path)} ist keine lesbare ZIP-Datei "
                          f"({ex}).") from None
    ext = {os.path.splitext(n)[1].lower() for n in namen}
    if ext & set(_DSTV):
        return "dstv"
    if ext & set(_SDNF):
        return "sdnf_zip"
    if ".ifc" in ext:
        return "ifc_zip"
    raise ImportError(
        f"{os.path.basename(path)}: im ZIP-Behaelter ist kein lesbares Modell. "
        "Enthalten sind u. a.: " + ", ".join(sorted(namen)[:8])
        + ". Erwartet werden DSTV-NC-Teile (*.nc1), SDNF (*.sdnf) oder IFC (*.ifc).")


def _from_zip_member(path: str, endungen, kind: str, model, log, **options) -> Model:
    """Ein Modell aus dem ersten passenden Eintrag eines ZIP-Behaelters lesen."""
    import shutil
    import tempfile
    import zipfile
    tmp = tempfile.mkdtemp(prefix="statik3d_zip_")
    try:
        with zipfile.ZipFile(path) as z:
            treffer = [n for n in z.namelist()
                       if os.path.splitext(n)[1].lower() in endungen]
            out = os.path.join(tmp, os.path.basename(treffer[0]))
            with z.open(treffer[0]) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
        C.say(log, f"Im ZIP-Behaelter gefunden: {treffer[0]}")
        if kind == "sdnf":
            from .sdnf import import_sdnf
            return import_sdnf(out, model, log, **options)
        from .ifc import import_ifc
        return import_ifc(out, model, log, **options)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def import_file(path: str, model: Model = None, log: list = None, **options) -> Model:
    """Datei anhand der Endung erkennen und in ein Modell importieren.

    model: bestehendes Modell, an das die Geometrie angehaengt wird (Knoten werden
           mit Toleranz zusammengefuehrt); None -> neues Modell mit dem Dateinamen.
    log:   Liste fuer Meldungen/Warnungen (deutsch).
    options: unit_scale, tol und formatspezifische Optionen (siehe Module).
    """
    path = os.fspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Datei '{path}' nicht gefunden")
    kind = _detect(path)
    fresh = model is None
    # Z-Achse der Datei zeigt nach unten (RFEM-Vorgabe): nach dem Lesen um x
    # drehen - nur bei einem frischen Modell, ein angehaengtes Modell wuerde
    # sonst mitgedreht.
    z_drehen = bool(options.pop("z_drehen", False)) and fresh
    stem = os.path.splitext(os.path.basename(os.path.normpath(path)))[0]
    tol = float(options.get("tol", C.DEFAULT_TOL))

    if kind == "json":
        loaded = Model.load(path)
        if fresh:
            model = loaded
        else:
            model = _append_model(model, loaded, tol)
            C.say(log, f"JSON-Modell '{loaded.name}' angehaengt")
        model.meta["quelle"] = path
        C.say(log, f"Statik3D-Modell geladen: {model.nn} Knoten, {len(model.elements)} Elemente")
        return model

    if model is None:
        model = Model(stem)
    n_nodes0, n_elems0 = model.nn, len(model.elements)

    if kind == "cad":
        if not mesher.HAVE_GMSH:
            raise RuntimeError(f"CAD-Import von '{os.path.basename(path)}' benoetigt das "
                               f"Python-Paket 'gmsh' (pip install gmsh).")
        mat = options.get("mat") or C.ensure_material(model, options.get("material"), log)
        dim = int(options.get("dim", 3))
        shell_prop = options.get("shell_prop")
        if dim == 2:
            shell_prop = C.ensure_shell_prop(model, shell_prop, options.get("thickness"), log)
        n = mesher.mesh_cad(model, path, mat, size=float(options.get("size", 0.0)),
                            order=int(options.get("order", 2)), dim=dim,
                            shell_prop=shell_prop, size_min=float(options.get("size_min", 0.0)))
        C.say(log, f"CAD-Import ({os.path.basename(path)}): {n} Elemente mit gmsh vernetzt")
    elif kind == "dxf":
        from .dxf import import_dxf
        import_dxf(path, model, log, **options)
    elif kind == "ifc":
        from .ifc import import_ifc
        import_ifc(path, model, log, **options)
    elif kind == "inp":
        from .abaqus import import_inp
        import_inp(path, model, log, **options)
    elif kind == "bdf":
        from .nastran import import_bdf
        import_bdf(path, model, log, **options)
    elif kind == "xlsx":
        from .xlsx_reader import read_xlsx
        from .saf import import_saf, is_saf
        from .rfem_tables import import_rfem_tables
        tables = read_xlsx(path)
        if is_saf(tables):
            C.say(log, "Excel-Datei als SAF (Structural Analysis Format) erkannt")
            import_saf(path, model, log, tables=tables, **options)
        else:
            C.say(log, "Excel-Datei als RFEM/RSTAB-Tabellenexport gelesen")
            import_rfem_tables(path, model, log, tables=tables, **options)
    elif kind == "rfem":
        from .rfem_tables import import_rfem_tables
        import_rfem_tables(path, model, log, **options)
    elif kind == "native":
        from .rfem_native import import_rfem_native
        import_rfem_native(path, model, log, **options)
    elif kind == "sdnf":
        from .sdnf import import_sdnf
        import_sdnf(path, model, log, **options)
    elif kind == "dstv":
        from .dstv import import_dstv
        import_dstv(path, model, log, **options)
    elif kind == "hicad":
        from .hicad import import_hicad
        import_hicad(path, model, log, **options)
    elif kind == "sdnf_zip":
        _from_zip_member(path, set(_SDNF), "sdnf", model, log, **options)
    elif kind == "ifc_zip":
        _from_zip_member(path, {".ifc"}, "ifc", model, log, **options)

    # Nachbereitung
    if z_drehen:
        n_gedreht = model.um_x_drehen()
        C.say(log, f"Modell um die x-Achse gedreht ({n_gedreht} Knoten): die Z-Achse der "
                   "Datei zeigte nach unten, hier zeigt z nach oben (y gespiegelt).")
    n_merged = C.merge_duplicate_nodes(model, tol) if model.nn > n_nodes0 else 0
    if n_merged:
        kb = getattr(model, "kontaktbedingungen", None) or {}
        C.say(log, f"{n_merged} doppelte Knoten zusammengefuehrt"
                   + (f" - die Flaechen der {len(kb)} Kontaktbedingungen werden beim "
                      "Vernetzen wieder getrennt" if kb else ""))
    ext = os.path.splitext(path)[1].lower()
    if ext in _NO_MEMBER_INFO or kind == "cad":
        members = model.auto_members()
        if members:
            C.say(log, f"{len(members)} Staebe aus kollinearen Stabelementen gebildet")
    if fresh and C.drop_empty_default_case(model):
        pass
    if model.active_case not in model.load_cases and model.load_cases:
        model.active_case = next(iter(model.load_cases))
    model.meta["quelle"] = path
    if not model.meta.get("bauteil"):
        model.meta["bauteil"] = stem
    n_new = len(model.elements) - n_elems0
    C.say(log, f"Import abgeschlossen: {n_new} neue Elemente, {model.nn} Knoten gesamt, "
               f"{len(model.supports)} Lager, {len(model.load_cases)} Lastfaelle")
    return model


def _append_model(target: Model, src: Model, tol: float) -> Model:
    """Geladenes JSON-Modell an ein bestehendes Modell anhaengen."""
    base = target.nn
    for m in src.materials.values():
        target.materials.setdefault(m.name, m)
    for s in src.sections.values():
        target.sections.setdefault(s.name, s)
    for s in src.shells.values():
        target.shells.setdefault(s.name, s)
    if src.nn:
        target.add_nodes(src.nodes)
    e_base = len(target.elements)
    for e in src.elements:
        target.add_element(e.typ, [n + base for n in e.nodes], e.mat, e.sec, e.roll, e.group,
                           e.hinges)
    for s in src.supports:
        target.fix(s.node + base, s.dofs, s.values, s.stiffness)
    for name, lc in src.load_cases.items():
        tgt = C.get_or_add_case(target, name, lc.category, lc.description)
        for l in lc.nodal_loads:
            target.load_node(l.node + base, *l.F, case=name)
        for l in lc.beam_loads:
            target.load_beam(l.elem + e_base, *l.q, system=l.system, case=name, q2=l.q2)
        for l in lc.face_loads:
            target.load_face(l.elem + e_base, l.p, l.face, case=name, direction=l.direction)
        for l in lc.temp_loads:
            target.load_temp(l.elem + e_base, l.dT, l.dT_z, case=name)
        if any(lc.gravity):
            tgt.gravity = list(lc.gravity)
    for m in src.members.values():
        target.add_member(C.unique_name(target.members, m.name),
                          [i + e_base for i in m.elements])
    C.merge_duplicate_nodes(target, tol)
    return target


__all__ = ["SUPPORTED", "PROPRIETARY", "import_file", "explain_format", "file_filter"]
