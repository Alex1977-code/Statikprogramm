"""
Zylindrische Flaechenachsen in der Maske der Flaeche (14.10.2026).

Lasten in lokal x/y auf gewoelbten RFEM-Flaechen setzt der Import nicht an,
er haengt sie an die Flaeche (Geometrielast.lokal). Sie wirken erst, wenn der
Anwender an der Flaeche zylindrische Achsen waehlt: x axial in Richtung +x,
y gleichsinnig um den Umfang, z nach aussen. Die Wahl gilt fuer alle Flaechen
derselben Bohrung.

* die Maske einer gewoelbten Flaeche fuehrt „Lokale Achsen“ und „+x (axial)“,
  eine ebene nicht;
* „Übernehmen“ mit „zylindrisch“ und +Y setzt beide Halbmaentel, und die
  Lasten liegen danach als Elementlasten auf ihren Schalen: axial p A_ges in
  +Y-Richtung (p = -1000 -> -1000 A_ges), keine Restkraft quer.

Aufruf:  python -m tests.test_zylinderachsen
"""
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_zylinder_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._ungespeichert_fragen = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w)
    _FENSTER.update(w=w, app=app)
    return w, app


def _halbzylinder_modell(tmp):
    """Halbzylinderpaar R = 0,3 m, L = 1 m um global Y aus einer rf6 mit Lasten
    in lokal x (-1000 N/m^2) auf beiden, dazu je 24 Schalen als Pruefnetz."""
    from tests.test_rfem6 import build_db, _rf6_aus_db
    from statik3d.importers import rfem6_db as R6
    R0, L0 = 0.3, 1.0
    db = os.path.join(tmp, "model.db")
    build_db(db,
             nodes=[(R0, 0, 0), (R0, L0, 0), (-R0, L0, 0), (-R0, 0, 0),
                    (R0, L0, 0), (R0, 0, 0), (-R0, 0, 0), (-R0, L0, 0),
                    (5, 0, 0), (6, 0, 0), (6, 1, 0), (5, 1, 0)],
             lines=[[1, 2], ([2, 3], (0.0, L0, R0)), [3, 4], ([4, 1], (0.0, 0.0, R0)),
                    [5, 6], ([6, 7], (0.0, 0.0, -R0)), [7, 8], ([8, 5], (0.0, L0, -R0)),
                    [9, 10], [10, 11], [11, 12], [12, 9]],
             members=[], supports=[],
             surfaces=[[1, 2, 3, 4], [5, 6, 7, 8], ([9, 10, 11, 12], 0.0)],
             boundary_lines={1: [1, 2, 3, 4], 2: [5, 6, 7, 8], 3: [9, 10, 11, 12]},
             load_cases=[("LF1", 12, 0.0)],
             surface_loads=[(1, [1, 2], -1000.0, 0)])
    m = R6.read_rf6(_rf6_aus_db(db, os.path.join(tmp, "zyl.rf6")), log=[])
    N = 24
    for fname, seite in (("F1", 1.0), ("F2", -1.0)):
        f = m.flaechen[fname]
        ids = {}
        for i in range(N + 1):
            phi = math.pi * i / N
            for j, y in enumerate((0.0, L0)):
                ids[(i, j)] = m.add_node(R0 * math.cos(phi), y, seite * R0 * math.sin(phi))
        for i in range(N):
            kn = [ids[(i, 0)], ids[(i + 1, 0)], ids[(i + 1, 1)], ids[(i, 1)]]
            f.elemente.append(m.add_element("shell4", kn, "S355", None))
    return m


def test_maske_zylinderachsen():
    w, app = _fenster()
    tmp = tempfile.mkdtemp()
    try:
        m = _halbzylinder_modell(tmp)
        w.model = m
        w.analysis = None
        w.results = None
        w.refresh_all()
        app.processEvents()
        w._objektmaske("geoflaeche", "F1")
        app.processEvents()
        maske = w.maskenrand.maske
        werte = maske.werte() if maske is not None else {}
        check("Maske der gewoelbten Flaeche F1 fuehrt „Lokale Achsen“ und „+x (axial)“",
              "lokale_achsen" in werte and "achse_plus_x" in werte, str(sorted(werte)))
        check("  Vorgabe: keine Achsen (Lasten wirken nicht)",
              str(werte.get("lokale_achsen", "")).startswith("keine"), str(werte.get("lokale_achsen")))
        w._objektmaske("geoflaeche", "F3")
        app.processEvents()
        werte3 = w.maskenrand.maske.werte() if w.maskenrand.maske is not None else {}
        check("Maske der ebenen Flaeche F3 fuehrt sie nicht", "lokale_achsen" not in werte3,
              str(sorted(werte3)))
        w._objektmaske("geoflaeche", "F1")
        app.processEvents()
        werte = dict(w.maskenrand.maske.werte())
        werte["lokale_achsen"] = "zylindrisch (x axial, y um den Umfang, z nach außen)"
        werte["achse_plus_x"] = "+Y"
        werte["vernetzen"] = False
        w._objekt_uebernehmen("geoflaeche", "F1", werte, False)
        app.processEvents()
        m = w.model
        check("Übernehmen setzt F1 und F2 (dieselbe Bohrung) auf zylindrisch, +x = +Y",
              all(m.flaechen[n].lokale_achsen == "zylinder"
                  and list(m.flaechen[n].achse_plus_x) == [0.0, 1.0, 0.0] for n in ("F1", "F2")),
              str([(m.flaechen[n].lokale_achsen, m.flaechen[n].achse_plus_x) for n in ("F1", "F2")]))
        F, A = np.zeros(3), 0.0
        for fl in m.load_cases["LF1"].face_loads:
            X = np.asarray(m.nodes[list(m.elements[fl.elem].nodes)], float)
            a = 0.5 * float(np.linalg.norm(np.cross(X[2] - X[0], X[3] - X[1])))
            F += fl.p * a * np.asarray(fl.direction, float)
            A += a
        check("  danach 48 Elementlasten, Summe -1000 A_ges in Y, quer 0",
              len(m.load_cases["LF1"].face_loads) == 48 and abs(F[1] + 1000.0 * A) < 1e-6
              and abs(F[0]) < 1e-6 and abs(F[2]) < 1e-6, f"{len(m.load_cases['LF1'].face_loads)} {F.round(4)}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_maske_zylinderachsen,):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
