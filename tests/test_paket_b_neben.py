"""
Zwei Nebenbefunde aus dem Oberflaechenpaket B (08.11.2026, Freigabe des Anwenders
„1 2 3 ja dann 4“):

1. Projizierte Flaechenlasten (Schnee, Wind) auf **Schalen** erzeugten keine Last:
   der Windschatten fragte die Aussennormale einer Volumenseite, die es bei
   Schalen nicht gibt. Jetzt wirkt p A |n.d| in Richtung d, unabhaengig vom
   Umlauf der Randlinien; eine Schale parallel zur Lastrichtung bekommt nichts.
2. ``Model.um_x_drehen`` (Einlesen einer Datei mit Z nach unten) drehte eigene
   Koordinatensysteme und Lasten mit globalem Bezug nicht mit. Jetzt bleibt
   jede Last im Bauteil, wo sie war: der Lastvektor ist danach Knoten fuer
   Knoten der gedrehte alte.

Aufruf:  python -m tests.test_paket_b_neben
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _platte(m, name, punkte, umlauf=(0, 1, 2, 3)):
    b = m.nn
    for p in punkte:
        m.add_node(*p)
    linien = []
    for j in range(4):
        m.add_line(f"{name}L{j}", [b + umlauf[j], b + umlauf[(j + 1) % 4]])
        linien.append(f"{name}L{j}")
    m.add_flaeche(name, linien, material="S235", dicke="D10")


def _modell():
    from statik3d.model import Model, Material, ShellProp
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01, "S235"))
    m.add_load_case("LF1", "Q")
    return m


def _kraefte(m, fall="LF1"):
    """Knotenkraefte (n x 3) des Lastfalls nach dem Verteilen."""
    from statik3d import solver
    m.lasten_verteilen()
    F = np.asarray(solver.case_loads(m, {fall: 1.0}, None)[0], float)
    return F.reshape(m.nn, -1)[:, :3]


def test_projiziert_schale():
    from statik3d import mesher
    h = math.tan(math.radians(30.0))
    dach = [(0, 0, 0), (2, 0, 0), (2, 1, h), (0, 1, h)]
    for umlauf, text in (((0, 1, 2, 3), "Umlauf gegen den Uhrzeiger"), ((0, 3, 2, 1), "Umlauf im Uhrzeiger")):
        m = _modell()
        _platte(m, "D", dach, umlauf)
        m.add_geometrielast("D", 5000.0, richtung=[0, 0, -1], projiziert=True, case="LF1")
        mesher.modell_vernetzen(m, log=[])
        F = _kraefte(m).sum(axis=0)
        # Schnee 5 kN/m² auf der Grundrissflaeche 2 m x 1 m: 10 kN nach unten
        check(f"Schnee projiziert auf Dachschale 30°, {text}: ΣF = (0; 0; −10,000) kN",
              np.allclose(F / 1000.0, [0.0, 0.0, -10.0], atol=1e-6), f"ΣF = {np.round(F / 1000.0, 6)} kN")
        mw = _modell()
        _platte(mw, "D", dach, umlauf)
        mw.add_geometrielast("D", 5000.0, richtung=[0, 0, -1], projiziert=False, case="LF1")
        mesher.modell_vernetzen(mw, log=[])
        Fw = _kraefte(mw).sum(axis=0)
        check(f"Gegenrechnung wahre Fläche, {text}: projiziert/wahr = cos 30° = 0,8660",
              abs(F[2] / Fw[2] - math.cos(math.radians(30.0))) < 1e-9, f"{F[2] / Fw[2]:.6f}")
    # senkrechte Wand: Schnee trifft nichts, Wind von vorn die volle Ansicht
    m = _modell()
    _platte(m, "W", [(0, 0, 0), (2, 0, 0), (2, 0, 1), (0, 0, 1)])
    m.add_geometrielast("W", 5000.0, richtung=[0, 0, -1], projiziert=True, case="LF1")
    m.add_geometrielast("W", 800.0, richtung=[0, 1, 0], projiziert=True, case="LF1")
    mesher.modell_vernetzen(m, log=[])
    F = _kraefte(m).sum(axis=0)
    check("senkrechte Wandschale: Schnee 0, Wind 0,8 kN/m² × 2 m² = 1,600 kN in +y",
          np.allclose(F / 1000.0, [0.0, 1.6, 0.0], atol=1e-6), f"ΣF = {np.round(F / 1000.0, 6)} kN")
    # Verfahrenstabelle: Fehlerkorrektur, betrifft nur projizierte Lasten an Schalen
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("projiziert_schale")
    m2 = _modell()
    _platte(m2, "W", [(0, 0, 0), (2, 0, 0), (2, 0, 1), (0, 0, 1)])
    m2.add_geometrielast("W", 800.0, richtung=[0, 1, 0], projiziert=False, case="LF1")
    check("Verfahrenstabelle: „projiziert_schale“ Fehlerkorrektur Stand 7, betrifft nur projizierte Schalenlast",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 7
          and rv.VERFAHRENSSTAND == 7 and mk.betrifft(m) and not mk.betrifft(m2))


def test_um_x_drehen():
    from statik3d import mesher
    from statik3d.lastbezug import achsen_aus_winkeln, winkel_aus_achsen
    # Umkehrung der Winkel, auch am Rand (Nick ±90°)
    gut = True
    for w in ((30, 20, 10), (-150, 45, 170), (10, 90, 0), (25, -90, 0), (0, 0, 180)):
        A = achsen_aus_winkeln(w)
        gut &= bool(np.allclose(achsen_aus_winkeln(winkel_aus_achsen(A)), A, atol=1e-12))
    check("winkel_aus_achsen kehrt achsen_aus_winkeln um (fünf Fälle, Nick ±90°)", gut)
    m = _modell()
    _platte(m, "P", [(0, 0, 0), (2, 0, 0), (2, 1, 0.3), (0, 1, 0.3)])
    m.add_node(0.0, 2.0, 0.0)
    m.add_node(3.0, 2.5, 0.5)
    m.add_line("G", [m.nn - 2, m.nn - 1])
    m.add_koordinatensystem("KW", art="winkel", ursprung=[1.0, 2.0, 3.0], winkel=[30.0, 20.0, 10.0])
    m.add_koordinatensystem("KP", art="punkte", ursprung=[0.5, -1.0, 2.0], punkt_x=[1.5, -0.5, 2.0],
                            punkt_xy=[0.5, 0.0, 3.0])
    m.add_geometrielast("P", -5000.0, case="LF1", bezug="global", achse="z")
    m.add_geometrielast("P", 3000.0, case="LF1", bezug="global", achse="y")
    m.add_geometrielast("P", -2000.0, case="LF1", bezug="ks", achse="x", ks="KW")
    m.add_geometrielast("P", 1500.0, case="LF1", bezug="ks", achse="z", ks="KP")
    m.add_geometrielast("P", -1000.0, case="LF1", bezug="lokal", achse="z")
    m.add_geometrielast("P", 700.0, case="LF1", richtung=[0.3, -0.4, 0.5])
    m.add_linienlast("G", [100.0, -200.0, 300.0], art="linie", case="LF1", ks="KW")
    m.add_linienlast("G", [0.0, 50.0, -400.0], art="linie", case="LF1")
    mesher.modell_vernetzen(m, log=[])
    F0 = _kraefte(m)
    A_kw, A_kp = m.koordinatensysteme["KW"].achsen(), m.koordinatensysteme["KP"].achsen()
    m.um_x_drehen()
    F1 = _kraefte(m)
    Q = np.array([1.0, -1.0, -1.0])
    check("um_x_drehen: Lastvektor Knoten für Knoten der gedrehte alte (global, ks, lokal, Richtung, Linie)",
          np.allclose(F1, F0 * Q, atol=1e-6 * np.abs(F0).max()),
          f"größte Abweichung {np.abs(F1 - F0 * Q).max():.3g} N von {np.abs(F0).max():.4g} N")
    check("um_x_drehen: Koordinatensystem aus Winkeln - Achsen gedreht",
          np.allclose(m.koordinatensysteme["KW"].achsen(), A_kw * Q, atol=1e-12))
    check("um_x_drehen: Koordinatensystem aus Punkten - Achsen und Ursprung gedreht",
          np.allclose(m.koordinatensysteme["KP"].achsen(), A_kp * Q, atol=1e-12)
          and np.allclose(m.koordinatensysteme["KP"].ursprung, [0.5, 1.0, -2.0]))


def main():
    for t in (test_projiziert_schale, test_um_x_drehen):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
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
    sys.exit(main())
