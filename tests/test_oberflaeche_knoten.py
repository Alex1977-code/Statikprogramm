"""
Oberflaeche der Volumen: welcher Modellknoten zu welchem Punkt (14.10.2026).

Die Ansicht zeichnet Volumen als ihre Oberflaeche (MainWindow._gitter,
extract_surface) und holt Verschiebungen und Knotenwerte ueber die
Nummer des Modellknotens je Punkt. Diese Nummer stand bis zum 14.10.2026 im
Feld ``vtkOriginalPointIds`` der Oberflaeche. Mit VTK 9.7 sind das bei
quadratischen Elementen (tet10) **nicht** die Modellknoten, sondern die
Nummern der Oberflaeche selbst (0, 1, 2 …): am Drehlager lag der Punkt bis
3,52 m neben dem Knoten, dessen Wert er bekam. Farbe und verformte Figur
eines tet10-Netzes waren damit falsch zugeordnet - gefunden an der Platte
V21, deren Ecken magenta waren, obwohl ausserhalb der Zone dort nichts ueber
der Skala liegt. Bei hex8 und tet4 stimmte das Feld.

Jetzt traegt das Gitter die Knotennummer als Punktfeld durch extract_surface
(viewport.oberflaeche), die Zuordnung stimmt fuer jeden Typ.

Aufruf:  python -m tests.test_oberflaeche_knoten
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_oberflaeche_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402
from tests import pruefkoerper as pk  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def test_zuordnung():
    from statik3d.gui import viewport as vp
    for typ in ("tet10", "tet4", "hex8", "pent6"):
        m, _ids = pk.quader(typ, 3, 2, 2, 0.3, 0.2, 0.2)
        g = vp.to_grid(m)
        f, kn = vp.oberflaeche(g)
        X = np.asarray(m.nodes, float)
        d = float(np.linalg.norm(np.asarray(f.points) - X[kn], axis=1).max())
        check(f"{typ}: jeder Punkt der Oberfläche liegt auf seinem Modellknoten",
              len(kn) == f.n_points and d < 1e-6 and "elem" in f.cell_data, f"größter Abstand {d:.2e} m")


def test_ansicht():
    """Farbe und verformte Figur eines tet10-Kragarms: der Wert je Punkt ist
    der seines Knotens, die Verschiebung ebenso."""
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    m, ids = pk.quader("tet10", 6, 2, 2, 0.6, 0.2, 0.2)
    for (i, _j, _k), n in ids.items():
        if i == 0:
            m.fix(int(n), "all")
    m.load_node(int(ids[(6, 1, 2)]), Fz=-50e3)
    an = solver.solve_all(m)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case":
            w.cb_result.setCurrentIndex(k)
            break
    app.processEvents()
    feld = next((w.cb_field.itemText(k) for k in range(w.cb_field.count())
                 if w.cb_field.itemText(k).startswith("|u|")), None)
    if feld:
        w.cb_field.setCurrentIndex(w.cb_field.findText(feld))
    r = w.current_result()
    u = np.asarray(r.u, float)[:, :3]
    soll = np.linalg.norm(u, axis=1) * 1000.0
    X = np.asarray(m.nodes, float)
    from scipy.spatial import cKDTree
    for art, s in (("aus", 0.0), ("fest", 100.0)):
        w.ueberhoehung_setzen(art, s)
        app.processEvents()
        akt = w.plotter.actors.get("result_netz")
        ds = akt.mapper.dataset if akt is not None else None
        if ds is None:
            check(f"tet10-Kragarm, Überhöhung {s:g}: Darsteller da", False)
            continue
        P = np.asarray(ds.points, float)
        d, k = cKDTree(X + s * u).query(P, k=1)
        werte = np.asarray(ds.point_data[ds.active_scalars_name], float)
        check(f"tet10-Kragarm, Überhöhung {s:g}: jeder Punkt liegt (verformt) auf einem Knoten und trägt dessen Wert",
              float(d.max()) < 1e-6 and np.allclose(werte, soll[k], rtol=1e-9, atol=1e-9),
              f"größter Abstand {float(d.max()):.2e} m, größter Wertfehler {float(np.max(np.abs(werte - soll[k]))):.3g} mm")
    w.close()


def main():
    for t in (test_zuordnung, test_ansicht):
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
