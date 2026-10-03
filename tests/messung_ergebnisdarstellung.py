"""
Messung zu Paket 6b (25.09.2026): verlaengern Max/Min-Marken, verformte
Knotenlage und die Linien des Verlaufs das Neuzeichnen merklich?

Pruefkoerper: Quader 5 x 2 x 1 m aus 50 x 40 x 20 Zellen zu je fuenf
Tetraedern (200 000 tet4, 43 911 Knoten), einseitig eingespannt, Endlast;
daneben ein Rahmen aus 16 Stabelementen fuer den Verlauf. Gemessen wird
``redraw`` mit gezeigtem Ergebnis (Faerbung u gesamt, mit und ohne Verlauf
My), je Fall der Median aus sieben Laeufen nach einem Aufwaermlauf.

Der Aufruf nutzt nur, was es vor und nach Paket 6b gibt (cb_field,
cb_diagram, redraw) - dieselbe Datei misst beide Staende.

Aufruf:  python -m tests.messung_ergebnisdarstellung
"""
import os
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_messung6b_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import mesher, solver  # noqa: E402
from statik3d.model import Model, Material, Section  # noqa: E402


def pruefkoerper() -> Model:
    m = Model("Pruefkoerper 200 000 tet4")
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    m.add_section(Section.i_profile("HEA 200", 0.190, 0.200, 0.0065, 0.010))
    ids = mesher.grid_box(m, "S355", 5.0, 2.0, 1.0, 50, 40, 20, typ="tet4")
    for j in range(ids.shape[1]):
        for k in range(ids.shape[2]):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    ende = ids[-1, :, -1].ravel()
    for n in ende:
        m.load_node(int(n), Fz=-500000.0 / len(ende))
    # Rahmen daneben (y = 4 m) fuer den Schnittgroessenverlauf
    links = mesher.line_of_beams(m, "S355", "HEA 200", (0, 4, 0), (0, 4, 4), 4)
    rechts = mesher.line_of_beams(m, "S355", "HEA 200", (6, 4, 0), (6, 4, 4), 4)
    oben = mesher.line_of_beams(m, "S355", "HEA 200", (0, 4, 4), (6, 4, 4), 8)
    mesher.merge_nodes(m)
    for n in mesher.select_nodes(m, ymin=4 - 1e-6, zmax=1e-6):
        m.fix(int(n), "all")
    for i in oben:
        m.load_beam(int(i), qz=-15000.0)
    return m, (links, rechts, oben)


def main():
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    t0 = time.perf_counter()
    m, _ = pruefkoerper()
    print(f"Modell: {len(m.elements)} Elemente, {m.nn} Knoten ({time.perf_counter() - t0:.1f} s)")
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.error = lambda *a, **k: None
    w.model = m
    w.refresh_all()
    app.processEvents()
    t0 = time.perf_counter()
    an = solver.solve_all(m, design=False)
    print(f"gerechnet in {time.perf_counter() - t0:.1f} s")
    w._solve_done("all", an)
    app.processEvents()
    aus = {}
    for name, feld, verlauf in (("u gesamt, kein Verlauf", "|u| Verschiebung", "kein Verlauf"),
                                ("u gesamt, Verlauf My", "|u| Verschiebung", "My"),
                                ("uz, kein Verlauf", "uz", "kein Verlauf")):
        w.cb_field.setCurrentText(feld)
        w.cb_diagram.setCurrentText(verlauf)
        app.processEvents()
        w.redraw()                                   # Aufwaermen
        zeiten = []
        for _ in range(7):
            t = time.perf_counter()
            w.redraw()
            zeiten.append(time.perf_counter() - t)
        aus[name] = statistics.median(zeiten)
        print(f"redraw {name:28s} Median {aus[name]:.3f} s  (min {min(zeiten):.3f}, max {max(zeiten):.3f})")
    akt = sorted(k for k in w.plotter.renderer.actors if k.startswith(("marke", "verlauf", "diagram")))
    print("Darsteller:", akt)
    # die Suche der Extremstellen allein, an 2 Mio. Werten (Drehlager-Groesse)
    try:
        from statik3d.gui import viewport as vp
        werte = np.random.default_rng(1).normal(size=2_000_000)
        maske = np.ones(len(werte), bool)
        t = time.perf_counter()
        for _ in range(10):
            vp.extremstellen(werte, maske)
        print(f"extremstellen an 2 000 000 Werten: {(time.perf_counter() - t) / 10 * 1000:.1f} ms")
    except AttributeError:
        print("extremstellen: gibt es in diesem Stand nicht")
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
