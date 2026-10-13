"""
Gewichtslose Werkstoffe (rho = 0): Import, Maske, Eigengewicht, Schwingung.

Klarstellung des Anwenders vom 13.10.2026: „Nullmaterial ist tatsächlich vom
user mit 0 wichte angegeben, das ist kein fehler, es handelt sich um ein
hilfsmaterial für hilfselemente“. Der Import soll rho = 0 wie definiert
uebernehmen; ein Modell mit teilweise gewichtslosen Koerpern muss rechnen.

Bis zum 13.10.2026 machte der RFEM-6-Import aus rho = 0 (und Wichte 0) still
7850 kg/m3 (rfem6_db._material: ``rho = rho or 7850.0``; _material_props
verwarf jede 0) - am Drehlager traegt der Werkstoff „Nullmaterial“ seitdem
das Gewicht von Stahl. Die Werkstoffmaske tat dasselbe beim Uebernehmen
(``float(w.get("rho", 7850.0) or 7850.0)``). Und die Modalanalyse sperrte jeden
Freiheitsgrad ohne Masse (``fixed | (md <= 0)``): die Knoten eines
gewichtslosen Koerpers standen dort fest wie ein Lager.

Geprueft: der Import (rho = 0 und Wichte 0 -> 0, mit Hinweis; Wichte allein ->
gamma/g; nichts angegeben -> 7850 wie bisher; 7850 bleibt), die Maske
(„0“ bleibt 0), das Eigengewicht (der gewichtslose Koerper bringt keine Last,
der andere seine), die Schwingung eines Kragarms mit gewichtsloser Spitze
(gegen dieselbe Spitze mit 1e-6 der Dichte) aus Volumen und aus Staeben.

Aufruf:  python -m tests.test_gewichtslos
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_gewichtslos_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402
from statik3d.model import Material, Model, Section  # noqa: E402

RESULTS = []
HINWEIS = "ist gewichtslos – Hilfsmaterial? Körper daraus können vom Volumennachweis ausgenommen werden."


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def _rf6(pfad, rho="7850", gamma=None):
    """Wuerfel als Volumen (tests.test_rfem6) mit Werkstoff 1; ``rho``/
    ``gamma``: Zahl, oder None = der Eintrag fehlt."""
    from tests import test_rfem6 as T6
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "model.db")
    T6.build_db(db, nodes=T6.WUERFEL_KNOTEN, lines=[], members=[], supports=[],
                surfaces=T6.WUERFEL_FLAECHEN, solids=[[1, 2, 3, 4, 5, 6]])
    con = sqlite3.connect(db)
    if rho is None:
        rid = con.execute("SELECT id FROM MaterialPropertyDouble WHERE propertyKey='rho'").fetchone()[0]
        con.execute("DELETE FROM MaterialPropertyDouble WHERE id=?", (rid,))
    else:
        con.execute("UPDATE MaterialPropertyDouble SET valueSI=? WHERE propertyKey='rho'", (float(rho),))
    if gamma is not None:
        con.execute("INSERT INTO MaterialPropertyDouble VALUES (900,1,'gamma',?)", (float(gamma),))
        con.execute("INSERT INTO MaterialProperties_propertiesMap_keys VALUES (1,90,'gamma')")
        con.execute("INSERT INTO MaterialProperties_propertiesMap_values VALUES (1,90,900,'MaterialPropertyDouble')")
    con.commit()
    con.close()
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("mesh.xml", T6.MESH_XML)
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
        z.writestr("general_data.xml", "<?xml version='1.0'?><property key='generalData'/>")
    shutil.rmtree(tmp, ignore_errors=True)
    return pfad


def test_import():
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        faelle = [("ρ = 0 und Wichte 0 (Nullmaterial in RFEM)", 0.0, 0.0, 0.0, True),
                  ("ρ = 0, Wichte fehlt", 0.0, None, 0.0, True),
                  ("ρ = 7850", 7850.0, None, 7850.0, False),
                  ("ρ fehlt, Wichte 78,5 kN/m³", None, 78500.0, 78500.0 / 9.81, False),
                  ("ρ und Wichte fehlen: 7850 wie bisher", None, None, 7850.0, False)]
        for i, (titel, rho, gamma, soll, hinweis) in enumerate(faelle):
            log = []
            m = R6.read_rf6(_rf6(os.path.join(tmp, f"m{i}.rf6"), rho, gamma), log=log)
            mt = [m.materials[e.mat] for e in m.elements][0]
            zeilen = [z for z in log if HINWEIS in z]
            check(f"Import {titel}: ρ = {soll:.1f} kg/m³" + (", mit Hinweis" if hinweis else ", kein Hinweis"),
                  abs(mt.rho - soll) <= 1e-9 * max(soll, 1.0) and bool(zeilen) == hinweis
                  and (not hinweis or f"Werkstoff ‚{mt.name}‘ {HINWEIS}" in zeilen[0]),
                  f"ρ {mt.rho!r}, {zeilen[:1]}")
            if hinweis:
                check("… der Schalter „vom Volumennachweis ausnehmen“ bleibt aus (setzt nur der Anwender)",
                      mt.nachweis_ausnehmen is False and not any(getattr(k, "nachweis_ausnehmen", False)
                                                                for k in m.koerper.values()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
# Werkstoffmaske
# --------------------------------------------------------------------------
def test_maske():
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    w.new_model()
    app.processEvents()
    name = next(iter(w.model.materials))
    for text, soll in (("0", 0.0), ("7850", 7850.0), ("", 7850.0)):
        mk = w._objektmaske("werkstoff", name) or w.maskenrand.maske
        mk._felder["rho"].setText(text)
        mk.anwenden()
        app.processEvents()
        check(f"Werkstoffmaske: Dichte „{text}“ + Übernehmen → {soll:.0f} kg/m³",
              w.model.materials[name].rho == soll, str(w.model.materials[name].rho))


# --------------------------------------------------------------------------
# Eigengewicht
# --------------------------------------------------------------------------
def test_eigengewicht():
    from statik3d.mesher import grid_box
    m = Model("Eigengewicht")
    m.add_material(Material("Stahl", 210e9, 0.3, 7850.0, fy=355e6))
    m.add_material(Material("Null", 210e9, 0.3, 0.0, fy=355e6))
    a = grid_box(m, "Stahl", 1.0, 1.0, 1.0, 2, 2, 2, origin=(0.0, 0.0, 0.0))
    b = grid_box(m, "Null", 1.0, 1.0, 1.0, 2, 2, 2, origin=(3.0, 0.0, 0.0))
    for ids in (a, b):
        for n in ids[:, :, 0].ravel():
            m.fix(int(n), "all")
    lf = list(m.load_cases)[0]
    m.load_cases[lf].gravity = [0.0, 0.0, -9.81]
    r = solver.solve_all(m).cases[lf]
    Ra = float(sum(r.reactions[int(n), 2] for n in a[:, :, 0].ravel()))
    Rb = float(sum(r.reactions[int(n), 2] for n in b[:, :, 0].ravel()))
    check("Eigengewicht: Stahlwürfel 1 m³ trägt 7850 · 9,81 = 77 008,5 N ab",
          abs(Ra - 7850.0 * 9.81) <= 1e-6 * 7850.0 * 9.81, f"R_z {Ra:.3f} N")
    check("… der gewichtslose Würfel bringt keine Last, die Rechnung läuft",
          abs(Rb) < 1e-6 and np.all(np.isfinite(r.u)), f"R_z {Rb:.6f} N")


# --------------------------------------------------------------------------
# Schwingung
# --------------------------------------------------------------------------
def _kragarm_volumen(rho_spitze):
    from statik3d.mesher import grid_box
    m = Model("Kragarm Volumen")
    m.add_material(Material("Stahl", 210e9, 0.3, 7850.0))
    m.add_material(Material("Spitze", 210e9, 0.3, rho_spitze))
    ids = grid_box(m, "Stahl", 1.2, 0.1, 0.1, 12, 1, 1)
    for e in m.elements:
        if float(np.asarray(m.nodes)[e.nodes, 0].mean()) > 1.0:
            e.mat = "Spitze"
    for n in ids[0].ravel():
        m.fix(int(n), "all")
    return m


def _kragarm_stab(rho_spitze):
    m = Model("Kragarm Stab")
    m.add_material(Material("Stahl", 210e9, 0.3, 7850.0))
    m.add_material(Material("Spitze", 210e9, 0.3, rho_spitze))
    m.add_section(Section.circle("R40", 0.04))
    kn = [m.add_node(0.1 * i, 0.0, 0.0) for i in range(13)]
    for i in range(12):
        m.add_element("beam", [kn[i], kn[i + 1]], "Stahl" if i < 10 else "Spitze", "R40")
    m.fix(kn[0], "all")
    return m


def test_schwingung():
    for titel, bau in (("Volumen (hex8)", _kragarm_volumen), ("Stäbe", _kragarm_stab)):
        f0 = solver.solve_modal(bau(0.0), nmodes=4).freqs
        f1 = solver.solve_modal(bau(7850.0 * 1e-6), nmodes=4).freqs
        rel = float(np.max(np.abs(f0[:3] - f1[:3]) / f1[:3]))
        check(f"Schwingung, Kragarm aus {titel} mit gewichtsloser Spitze: rechnet, Frequenzen wie mit "
              f"1e-6 der Dichte", np.all(np.isfinite(f0)) and rel < 1e-4,
              f"f1..3 ρ=0: {np.round(f0[:3], 3).tolist()} Hz, ρ=1e-6·7850: {np.round(f1[:3], 3).tolist()} Hz, "
              f"Abweichung {rel * 100:.4f} %")


def main():
    for t in (test_import, test_maske, test_eigengewicht, test_schwingung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
