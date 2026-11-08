"""
Rueckmeldung des Anwenders zur exe vom 08.11.2026 (Build 4aceca1):

1. „linienlager und flächenlager rechnen nicht es kommt fehlermeldung struktur
   nicht gelagert“: ein Linienlager aus der Maske bekam nur die Endknoten seiner
   Linien; die Netzknoten dazwischen erst beim naechsten Vernetzen. Am schon
   vernetzten Modell hing eine Platte an einer Linie so nur an zwei Knoten.
   Jetzt kommt das Lager mit OK auf das Netz (supports.lager_auf_netz).
2. „wenn neue line dann im rechten menü nicht erst in feld für knoten klicken
   sondern es dürfen gleich knoten angeklickt werden … gilt auch für weitere
   masken“: eine neue Maske beginnt mit der Auswahl per Maus fuer ihr erstes
   Knoten-, Linien- oder Flaechenfeld; eine Maske zum Bearbeiten nicht.

Aufruf:  python -m tests.test_rueckmeldung_0811
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(tempfile.mkdtemp(prefix="statik3d_rm0811_"),
                                                    "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if "w" in _FENSTER:
        return _FENSTER["w"], app
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _platte(w, app, vernetzen=True):
    """Platte 4 m x 3 m, 10 mm S235, Linien L1..L4, Flaeche F1, Eigengewicht in LF1."""
    from statik3d.model import Material, ShellProp
    from statik3d import mesher
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in ((0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)):
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j + 1}", [j, (j + 1) % 4])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0.0, 0.0, -9.81]
    if vernetzen:
        mesher.modell_vernetzen(m, log=[])
    w.refresh_all()
    w.selection = np.array([], dtype=int)
    w.sel_linien, w.sel_flaechen = [], []
    w.maskenrand.schliessen()
    w.fehler_liste.clear()
    _ruhe(app)
    return m


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _durchbiegung(m):
    from statik3d import solver
    res = solver.solve_all(m, workers=1, combinations=False)
    r = res.cases["LF1"]
    U = np.asarray(r.u, float).reshape(m.nn, -1)
    return float(np.abs(U[:, 2]).max())


def test_linienlager_am_netz():
    from statik3d import supports
    w, app = _fenster()
    m = _platte(w, app)
    w.add_line_support()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("linien", "L4")
    for d in range(3, 6):          # eingespannt: auch die Verdrehungen starr
        mk.setzen(f"typ{d}", w.LAGERWIRKUNG["rigid"])
    mk.anwenden()
    _ruhe(app)
    ll = m.line_supports
    kn_maske = list(ll[0].nodes) if ll else []
    # zweiter Weg: dieselbe Linie ueber das Modell, Knoten aus lager_auf_netz
    import copy
    m2 = copy.deepcopy(m)
    m2.line_supports[0].nodes = []
    supports.lager_auf_netz(m2)
    kn_netz = list(m2.line_supports[0].nodes)
    check("Linienlager aus der Maske am vernetzten Modell: alle Netzknoten der Linie L4",
          len(kn_maske) > 2 and kn_maske == kn_netz, f"Maske {len(kn_maske)}, Netz {len(kn_netz)} Knoten")
    w1 = _durchbiegung(m)
    m3 = copy.deepcopy(m)
    m3.line_supports[0].nodes = kn_netz
    w2 = _durchbiegung(m3)
    # Kragplatte 3 m, q = 78,5 kg/m³·9,81·0,01 m: w = q L⁴/(8 D) mit D = E t³/(12(1-ν²))
    q = 7850 * 9.81 * 0.01
    D = 210e9 * 0.01 ** 3 / (12 * (1 - 0.3 ** 2))
    w_hand = q * 4.0 ** 4 / (8 * D)
    check("… Kragplatte eingespannt an L4 rechnet: Durchbiegung gleich auf beiden Wegen, nahe q L⁴/(8 D)",
          abs(w1 - w2) <= 1e-9 * max(w2, 1e-12) and 0.9 * w_hand < w1 < 1.15 * w_hand,
          f"Maske {w1 * 1e3:.2f} mm, Netz {w2 * 1e3:.2f} mm, Hand {w_hand * 1e3:.2f} mm")
    check("… keine Meldung", not w.fehler_liste, str(w.fehler_liste[:2]))


def test_nur_linien_oder_flaechenlager_rechnen():
    """Ein Modell, das nur auf Linien- bzw. Flaechenlagern steht, rechnet ueber
    „Berechnen“ (bis 08.11.2026: „keine Lagerung definiert (System kinematisch)“
    aus Model.check, das nur Knoten- und Kontaktlager zaehlte)."""
    import time
    w, app = _fenster()
    w._fragen = lambda *a, **k: True               # „vor dem Rechnen vernetzen?“ - ja
    for lagerart, ziele, text in (("linien", ["L2", "L4"], "Platte auf zwei Linienlagern"),
                                  ("flaechen", ["F1"], "Platte auf einem Flächenlager")):
        m = _platte(w, app, vernetzen=False)
        for z in ziele:
            (w.add_line_support if lagerart == "linien" else w.add_surface_support)()
            _ruhe(app)
            mk = _maske(w)
            mk.setzen(lagerart, z)
            mk.anwenden()
            _ruhe(app)
        check(f"Model.check: {text} ohne Knotenlager gilt als gelagert",
              not any("keine Lagerung" in x for x in m.check()), str([x for x in m.check() if "FEHLER" in x][:2]))
        w.fehler_liste.clear()
        w.analysis = None
        w.do_solve("all")
        t0 = time.time()
        while w._rechnet() and time.time() - t0 < 120:
            app.processEvents()
            time.sleep(0.02)
        _ruhe(app, 20)
        ana = getattr(w, "analysis", None)
        hat = ana is not None and "LF1" in getattr(ana, "cases", {})
        check(f"„Berechnen“: {text} rechnet, ohne Meldung „keine Lagerung definiert“",
              hat and not any("keine Lagerung" in str(x) for x in w.fehler_liste), str(w.fehler_liste[:2]))
        if hat and lagerart == "linien":
            U = np.asarray(ana.cases["LF1"].u, float).reshape(m.nn, -1)
            # gelenkig gelagerte Platte 4 m Spannweite (Lager an x = 0 und x = 4), in
            # Plattenmitte (2; 1,5): zwischen Plattenstreifen 5 q L⁴/(384 D) und Balken
            # 5 q L⁴/(384 E I) - am freien Rand ist die Platte weicher als beide
            q = 7850 * 9.81 * 0.01
            D = 210e9 * 0.01 ** 3 / (12 * (1 - 0.3 ** 2))
            w_streifen = 5 * q * 4.0 ** 4 / (384 * D)
            X = np.asarray(m.nodes, float)
            mitte = int(np.argmin(np.hypot(X[:, 0] - 2.0, X[:, 1] - 1.5)))
            w_fem = float(abs(U[mitte, 2]))
            check("… Durchbiegung in Plattenmitte zwischen Plattenstreifen und Balken (5 q L⁴/384)",
                  0.99 * w_streifen < w_fem < w_streifen / 0.91,
                  f"FEM {w_fem * 1e3:.1f} mm an ({X[mitte, 0]:.2f}; {X[mitte, 1]:.2f}), Streifen "
                  f"{w_streifen * 1e3:.1f} mm, Balken {w_streifen / 0.91 * 1e3:.1f} mm")


def _klick_knoten(w, app, i):
    alt = w._naechster_am_zeiger
    w._naechster_am_zeiger = lambda punkte, radius=None: (int(i), 0.0)
    try:
        w._maskenobjekt_klick(w.maskenrand.objekt_modus(), None)
    finally:
        w._naechster_am_zeiger = alt
    _ruhe(app)


def test_neue_masken_klicken_gleich():
    w, app = _fenster()
    m = _platte(w, app, vernetzen=False)
    w._baum_neu("linien")
    _ruhe(app)
    mk = _maske(w)
    check("„Neu: Linie“ beginnt mit der Auswahl per Maus im Feld „Knoten“",
          mk is not None and mk.objekt_modus == "knoten" and getattr(mk, "_klick_art", "") == "linie",
          f"{getattr(mk, 'titel', None)}: Modus {getattr(mk, 'objekt_modus', None)!r}")
    if mk is not None:
        _klick_knoten(w, app, 0)
        _klick_knoten(w, app, 2)
        check("… zwei Knoten angeklickt, ohne vorher ins Feld zu klicken: sie stehen im Feld",
              str(mk.werte().get("kn", "")).replace(" ", "") in ("0,2",), repr(mk.werte().get("kn")))
        mk.anwenden()
        _ruhe(app)
        check("… OK legt die Linie K0–K2 an",
              any(list(L.nodes) == [0, 2] for L in m.lines.values()), str([L.nodes for L in m.lines.values()][-1:]))
    for befehl, modus, text in ((w.add_line_support, "linie", "Neu: Linienlager → Linien"),
                                (w.add_surface_support, "flaeche", "Neu: Flächenlager → Flächen"),
                                (w.maske_lager, "knoten", "Lager setzen → Knoten")):
        w.maskenrand.schliessen()
        _ruhe(app)
        befehl()
        _ruhe(app)
        mk = _maske(w)
        check(f"{text}: gleich anklickbar", mk is not None and mk.objekt_modus == modus,
              f"Modus {getattr(mk, 'objekt_modus', None)!r}")
    w.maskenrand.schliessen()
    _ruhe(app)
    w._objektmaske("linie", "L1")
    _ruhe(app)
    mk = _maske(w)
    check("Die Maske einer bestehenden Linie beginnt ohne Auswahl per Maus (Klick wählt weiter)",
          mk is not None and not mk.objekt_modus, f"Modus {getattr(mk, 'objekt_modus', None)!r}")
    w.maskenrand.schliessen()


def main():
    for t in (test_linienlager_am_netz, test_nur_linien_oder_flaechenlager_rechnen, test_neue_masken_klicken_gleich):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    w = _FENSTER.get("w")
    if w is not None:
        w.close()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
