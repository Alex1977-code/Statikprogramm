"""
Export der Statikmodelle in fremde Formate - und, wo Statik3D das Format auch
liest, der Rueckweg: exportieren, wieder einlesen, vergleichen.

Aufruf:  python -m tests.test_exporters
"""
import math
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver  # noqa: E402
from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402
from statik3d.exporters import export_model, formats, file_filter, FORMATS  # noqa: E402
from statik3d.importers import import_file  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:56s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, err <= tol * max(1.0, abs(want)),
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.3f} %")


def _rahmen() -> Model:
    """Zweistieliger Rahmen mit Blech, Lager, Knoten- und Stablast."""
    m = Model("Rahmen")
    m.add_material(Material.steel("S355"))
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 400"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_shell_prop(ShellProp("t12", 0.012))
    n = [m.add_node(*p) for p in ((0, 0, 0), (0, 0, 5), (8, 0, 5), (8, 0, 0),
                                  (0, 3, 5), (8, 3, 5))]
    m.add_element("beam", [n[0], n[1]], "S355", "HEB 300")
    m.add_element("beam", [n[1], n[2]], "S355", "IPE 400")
    m.add_element("beam", [n[2], n[3]], "S355", "HEB 300")
    m.add_element("shell4", [n[1], n[2], n[5], n[4]], "S235", "t12")
    m.fix(n[0], "all")
    m.fix(n[3], "pinned")
    m.load_node(n[1], Fx=25e3, Fz=-40e3, case="LF1")
    m.load_beam(1, qz=-12e3)
    m.add_load_case("LF2", "Q", "Verkehr", activate=False)
    m.load_node(n[2], Fz=-60e3, case="LF2")
    m.add_combination("K1", {"LF1": 1.35, "LF2": 1.5})
    m.auto_members()
    m.meta["projekt"] = "Pruefrahmen"
    return m


# --------------------------------------------------------------------------
# 1) Alle Formate schreiben
# --------------------------------------------------------------------------
def test_alle_formate():
    m = _rahmen()
    tmp = tempfile.mkdtemp()
    try:
        check("dreizehn Ausgabeformate", len(FORMATS) == 13, str(len(FORMATS)))
        ff = file_filter()
        check("Dateidialog nennt alle Endungen",
              all(f"*{e}" in ff for e in FORMATS), ff[:60])
        for ext, _b in formats():
            p = os.path.join(tmp, "modell" + ext)
            log = []
            out = export_model(m, p, log=log)
            gross = (os.path.getsize(out) if os.path.isfile(out)
                     else sum(os.path.getsize(os.path.join(r, f))
                              for r, _d, fs in os.walk(out) for f in fs))
            check(f"{ext} geschrieben", gross > 100, f"{gross} Byte")
        try:
            export_model(m, os.path.join(tmp, "x.unbekannt"))
            check("unbekannte Endung wird abgewiesen", False)
        except ValueError as ex:
            check("unbekannte Endung wird abgewiesen", "unterstuetzt" in str(ex),
                  str(ex)[:50])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 2) Rueckweg: exportieren und wieder einlesen
# --------------------------------------------------------------------------
def test_rueckweg():
    m = _rahmen()
    tmp = tempfile.mkdtemp()
    try:
        # JSON: verlustfrei
        p = os.path.join(tmp, "m.json")
        export_model(m, p)
        m2 = Model.load(p)
        check("JSON: Knoten gleich", m2.nn == m.nn, f"{m2.nn}")
        check("JSON: Elemente gleich", len(m2.elements) == len(m.elements))
        check("JSON: Lastfaelle gleich", sorted(m2.load_cases) == sorted(m.load_cases))
        check("JSON: Lager gleich", len(m2.supports) == len(m.supports))

        # SAF
        p = os.path.join(tmp, "m.xlsx")
        export_model(m, p)
        log = []
        m3 = import_file(p, log=log)
        check("SAF: als SAF erkannt", any("SAF" in x for x in log), log[0][:50])
        check("SAF: Knoten wieder da", m3.nn == m.nn, f"{m3.nn} / {m.nn}")
        check("SAF: Staebe wieder da",
              len([e for e in m3.elements if e.typ == "beam"]) == 3,
              str(len([e for e in m3.elements if e.typ == "beam"])))
        check("SAF: Querschnitte wieder da",
              "IPE 400" in m3.sections and "HEB 300" in m3.sections,
              str(sorted(m3.sections)))
        close("SAF: Flaeche IPE 400", m3.sections["IPE 400"].A,
              m.sections["IPE 400"].A, 1e-9, " m^2")
        check("SAF: Lager wieder da", len(m3.supports) >= 2, str(len(m3.supports)))
        check("SAF: Lastfaelle wieder da",
              len(m3.load_cases) >= 2, str(sorted(m3.load_cases)))

        # SDNF
        p = os.path.join(tmp, "m.sdnf")
        export_model(m, p)
        m4 = import_file(p)
        beams = [e for e in m4.elements if e.typ == "beam"]
        check("SDNF: drei Staebe", len(beams) == 3, str(len(beams)))
        check("SDNF: Profile erhalten",
              "IPE 400" in m4.sections and "HEB 300" in m4.sections,
              str(sorted(m4.sections)))
        laengen = sorted(round(m4.element_length(i), 4) for i, e in enumerate(m4.elements)
                         if e.typ == "beam")
        check("SDNF: Laengen erhalten", laengen == [5.0, 5.0, 8.0], str(laengen))

        # DSTV-NC
        p = os.path.join(tmp, "teile.zip")
        export_model(m, p)
        m5 = import_file(p)
        check("DSTV: drei Teile", len([e for e in m5.elements if e.typ == "beam"]) == 3,
              str(len(m5.elements)))
        close("DSTV: Gesamtlaenge erhalten",
              sum(m5.element_length(i) for i in range(len(m5.elements))),
              5.0 + 8.0 + 5.0, 1e-6, " m")

        # DXF
        p = os.path.join(tmp, "m.dxf")
        export_model(m, p)
        m6 = import_file(p)
        check("DXF: Linien wieder da", len(m6.elements) >= 3, str(len(m6.elements)))

        # Abaqus
        p = os.path.join(tmp, "m.inp")
        export_model(m, p)
        m7 = import_file(p)
        check("Abaqus: Knoten wieder da", m7.nn == m.nn, f"{m7.nn}")
        check("Abaqus: Elemente wieder da", len(m7.elements) == len(m.elements),
              str(len(m7.elements)))
        check("Abaqus: Lager wieder da", len(m7.supports) >= 2, str(len(m7.supports)))

        # Nastran
        p = os.path.join(tmp, "m.bdf")
        export_model(m, p)
        m8 = import_file(p)
        check("Nastran: Knoten wieder da", m8.nn == m.nn, f"{m8.nn}")
        check("Nastran: Elemente wieder da", len(m8.elements) >= 3,
              str(len(m8.elements)))

        # IFC
        p = os.path.join(tmp, "m.ifc")
        export_model(m, p)
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        check("IFC: Kopf mit StructuralAnalysisView",
              "StructuralAnalysisView" in txt and "FILE_SCHEMA(('IFC4'))" in txt)
        check("IFC: Bauteile und Knoten enthalten",
              "IFCSTRUCTURALCURVEMEMBER" in txt and "IFCSTRUCTURALPOINTCONNECTION" in txt)
        check("IFC: Lager und Lasten enthalten",
              "IFCBOUNDARYNODECONDITION" in txt and "IFCSTRUCTURALLOADSINGLEFORCE" in txt)
        m9 = import_file(p)
        check("IFC: wieder einlesbar", m9.nn > 0, f"{m9.nn} Knoten")

        # HiCAD-Archiv
        p = os.path.join(tmp, "m.sza")
        export_model(m, p)
        from statik3d.importers.hicad_sza import (archive_entries, part_tables,
                                                  table_sections, is_hicad_archive)
        check("HiCAD-Archiv: Kennung stimmt", is_hicad_archive(p))
        ents = archive_entries(p, data=True)
        check("HiCAD-Archiv: sechs Teile", len(ents) == 6, str(len(ents)))
        check("HiCAD-Archiv: alle Teile entpackbar",
              all(e.get("data") for e in ents),
              str([e["kurz"] for e in ents if not e.get("data")]))
        namen = [e["kurz"] for e in ents]
        check("HiCAD-Archiv: SDNF enthalten", "STATIK3D.sdnf" in namen, str(namen))
        tabs = part_tables(p)
        secs = table_sections(tabs["STATIK3D_PROFILE.IPT"])
        close("HiCAD-Archiv: Profilwerte erhalten", secs["IPE 400"].A,
              m.sections["IPE 400"].A, 1e-3, " m^2")
        close("HiCAD-Archiv: I_y erhalten", secs["IPE 400"].Iy,
              m.sections["IPE 400"].Iy, 1e-3, " m^4")
        m10 = import_file(p)
        check("HiCAD-Archiv: wieder einlesbar (Profile, Werkstoffe)",
              "IPE 400" in m10.sections, str(sorted(m10.sections)))

        # Tabellen
        p = os.path.join(tmp, "tabellen")
        out = export_model(m, p + ".csv")
        check("Tabellen: zehn Blätter", len(os.listdir(out)) == 10,
              str(len(os.listdir(out))))
        m11 = import_file(out)
        check("Tabellen: Knoten wieder da", m11.nn == m.nn, f"{m11.nn}")
        check("Tabellen: Staebe wieder da",
              len([e for e in m11.elements if e.typ == "beam"]) == 3,
              str(len(m11.elements)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 3) Ergebnisse mitschreiben (VTK) und Geometrie (STL)
# --------------------------------------------------------------------------
def test_ergebnisse():
    m = _rahmen()
    r = solver.solve_static(m, case="LF1")
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "m.vtu")
        export_model(m, p, results=r)
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        check("VTK: Verformung mitgeschrieben", 'Name="Verformung"' in txt)
        check("VTK: Auflagerkraefte mitgeschrieben", 'Name="Auflagerkraft"' in txt)
        check("VTK: Normalkraft je Element", 'Name="Normalkraft"' in txt)
        check("VTK: Zellarten gesetzt", 'Name="types"' in txt)
        n_pts = txt.count("Points")
        check("VTK: Punktblock vorhanden", n_pts >= 2, str(n_pts))
        # Zahlenprobe: groesste Verformung steht in der Datei
        umax = float(np.abs(np.asarray(r.u).reshape(-1, 6)[:, :3]).max())
        check("VTK: Verformungswert plausibel", umax > 0, f"u_max = {umax * 1e3:.3f} mm")

        p = os.path.join(tmp, "m.stl")
        export_model(m, p)
        with open(p, "rb") as f:
            kopf = f.read(80)
            import struct
            n = struct.unpack("<I", f.read(4))[0]
        check("STL: binaer mit Dreieckszahl", n == 2, f"{n} Dreiecke")
        check("STL: Kopf nennt Statik3D", kopf.startswith(b"Statik3D"))
        p2 = os.path.join(tmp, "m_ascii.stl")
        from statik3d.exporters.stl import write_stl
        write_stl(m, p2, binary=False)
        with open(p2, encoding="ascii") as f:
            t = f.read()
        check("STL: ASCII mit solid/endsolid",
              t.startswith("solid") and t.rstrip().endswith("endsolid Rahmen"))
        check("STL: zwei facet normal", t.count("facet normal") == 2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# 4) Anbindung: Kommandozeile und Web-API
# --------------------------------------------------------------------------
def test_anbindung():
    import json
    import threading
    import urllib.error
    import urllib.request
    from statik3d.cli import main as cli_main
    from statik3d.web.server import make_server

    tmp = tempfile.mkdtemp()
    try:
        m = _rahmen()
        quelle = os.path.join(tmp, "modell.json")
        m.save(quelle)
        ziel = os.path.join(tmp, "aus.sdnf")
        rc = cli_main([quelle, "--export", ziel, "--still"])
        check("Kommandozeile: --export schreibt", rc == 0 and os.path.exists(ziel),
              f"rc = {rc}")
        z2 = os.path.join(tmp, "aus.dxf")
        z3 = os.path.join(tmp, "aus.stl")
        rc = cli_main([quelle, "--export", z2, "--export", z3, "--still"])
        check("Kommandozeile: mehrere Ziele",
              os.path.exists(z2) and os.path.exists(z3), f"rc = {rc}")
        rc = cli_main(["--formate"])
        check("Kommandozeile: --formate listet auf", rc == 0)

        srv = make_server("127.0.0.1", 0, model=m)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"

        def op(d):
            req = urllib.request.Request(url + "/api/op", json.dumps(d).encode(),
                                         {"Content-Type": "application/json"})
            try:
                return json.loads(urllib.request.urlopen(req, timeout=20).read())
            except urllib.error.HTTPError as e:
                return {"error": json.loads(e.read()).get("error", "")}

        try:
            a = op({"op": "export", "path": "aus/modell.sdnf"})
            check("Web-API: export schreibt SDNF", "SDNF" in a.get("message", ""),
                  a.get("message", a.get("error", ""))[:60])
            b = op({"op": "export", "path": "aus/modell.dxf"})
            check("Web-API: export schreibt DXF", "DXF" in b.get("message", ""),
                  b.get("message", b.get("error", ""))[:60])
            c = op({"op": "export", "path": "x.foo"})
            check("Web-API: unbekannte Endung wird abgewiesen",
                  "Ausgabeformat" in c.get("error", ""), c.get("error", "")[:60])
            d = op({"op": "export"})
            check("Web-API: fehlender Name wird abgewiesen",
                  "Dateiname" in d.get("error", ""), d.get("error", "")[:60])
        finally:
            srv.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for t in (test_alle_formate, test_rueckweg, test_ergebnisse, test_anbindung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
