"""
Laminat mit Kopplung (B ≠ 0) unter gleichmaessiger Temperatur (Nebenbefund 14,
09.11.2026). Die Last trug m0 = B α ΔT schon (shell_rm.temperatur_schale), die
Rueckrechnung der Momente zog nur A α ΔT bei den Normalkraeften ab - die frei
gedehnte Platte zeigte das Moment B α ΔT und daraus eine Randspannung.

Aufbau: 5 mm E = 210 000 N/mm² unten, 5 mm E = 70 000 N/mm² oben, ν = 0,3,
α = 1,2e-5 1/K (das Programm fuehrt eine Waermedehnzahl je Element, nicht je
Lage), ΔT = 50 K, also ε0 = α ΔT = 6e-4.

1. Frei gelagert: jede Lage dehnt sich um ε0, die Platte bleibt eben und
   spannungsfrei: n = 0, m = 0, w = 0, u_x(L) = α ΔT L = 0,600 mm.
   (Mit gleicher Waermedehnzahl in beiden Lagen gibt es keine Kruemmung; die
   Bimetall-Kruemmung braeuchte α je Lage, das Programm hat sie nicht.)
2. Voll gehalten (alle Freiheitsgrade aller Knoten fest): ε = κ = 0,
   n = −N_T, m = −M_T. Zwei Wege fuer die Soll-Zahl:
   a) klassische Laminattheorie: N_T = Σ Q̄ α ΔT (z_k − z_{k−1}),
      M_T = ½ Σ Q̄ α ΔT (z_k² − z_{k−1}²) mit Q̄11 + Q̄12 = E/(1 − ν):
      N_T = (300 000 + 100 000) N/mm² · 5 mm · 6e-4 = 1 200 N/mm,
      M_T = ½ (300 000 · (0 − 25) + 100 000 · (25 − 0)) · 6e-4 = −1 500 N.
   b) Spannung je Lage σ_k = −E_k α ΔT/(1 − ν): unten −180, oben −60 N/mm²;
      n = (−180 − 60) · 5 = −1 200 N/mm,
      m = Σ σ_k t_k z_k = (−180)(5)(−2,5) + (−60)(5)(+2,5) = +1 500 N.
3. Symmetrischer Aufbau (B = 0) und homogene Schale bleiben, wie sie waren.

Aufruf:  python -m tests.test_laminat_temperatur
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

UNSYM = [{"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 0.0},
         {"t": 0.005, "E": 70e9, "nu": 0.3, "winkel": 0.0}]
SYM = [{"t": 0.0025, "E": 70e9, "nu": 0.3, "winkel": 0.0},
       {"t": 0.005, "E": 210e9, "nu": 0.3, "winkel": 0.0},
       {"t": 0.0025, "E": 70e9, "nu": 0.3, "winkel": 0.0}]
DT = 50.0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _platte(ordnung, lagen):
    from statik3d import mesher
    from statik3d.model import Model, Material, ShellProp
    m = Model("Laminat")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("lam", 0.010, lagen=[dict(lage) for lage in lagen]))
    for p in [(0, 0, 0), (1, 0, 0), (1, 0.2, 0), (0, 0.2, 0)]:
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j}", [j, (j + 1) % 4])
    f = m.add_flaeche("P", [f"L{j}" for j in range(4)], material="S235", dicke="lam")
    f.teilung = [10, 2]
    m.netz.ordnung = ordnung
    m.add_load_case("LF1", "Q")
    m.add_geometrielast("P", art="flaeche", lastart="temperatur", dT=DT, case="LF1")
    mesher.modell_vernetzen(m, log=[], workers=1)
    return m


def _knoten(m, x, y):
    d = np.hypot(m.nodes[:, 0] - x, m.nodes[:, 1] - y) + np.abs(m.nodes[:, 2])
    return int(np.argmin(d))


def _frei(m):
    for n in range(m.nn):
        m.fix(n, [5])
    m.fix(_knoten(m, 0, 0), [0, 1, 2])
    m.fix(_knoten(m, 1, 0), [1, 2])
    m.fix(_knoten(m, 0, 0.2), [2])


def _rechnen(m):
    from statik3d import solver
    r = solver.solve_all(m, workers=1, combinations=False).cases["LF1"]
    acc = np.array([np.asarray(v, float) for v in r.shell_res.values()])
    return r, acc


def test_frei_unsymmetrisch():
    for o in (1, 2):
        m = _platte(o, UNSYM)
        typen = sorted({e.typ for e in m.elements})
        _frei(m)
        r, acc = _rechnen(m)
        U = np.asarray(r.u)
        a = m.materials["S235"].alpha
        check(f"{typen}: frei, Zweischichter: u_x(L) = α ΔT L = {a * DT * 1e3:.3f} mm, eben",
              abs(U[_knoten(m, 1, 0), 0] - a * DT) < 1e-6 * a * DT and np.abs(U[:, 2]).max() < 1e-9,
              f"u_x {U[_knoten(m, 1, 0), 0] * 1e3:.6f} mm, |w| {np.abs(U[:, 2]).max() * 1e3:.6f} mm")
        check(f"{typen}: frei, Zweischichter: normalkraftfrei (|n| < 0,1 % von N_T = 1 200 N/mm)",
              np.abs(acc[:, :3]).max() < 1e-3 * 1.2e6, f"größtes |n| {np.abs(acc[:, :3]).max() / 1e3:.4f} N/mm")
        check(f"{typen}: frei, Zweischichter: momentenfrei (|m| < 0,1 % von |M_T| = 1 500 N)",
              np.abs(acc[:, 3:]).max() < 1e-3 * 1500.0, f"größtes |m| {np.abs(acc[:, 3:]).max():.3f} Nm/m")
        vm = max(float(s["vM"]) for s in r.shell_stress.values())
        check(f"{typen}: frei, Zweischichter: Randspannung 0 (< 0,1 N/mm²)",
              vm < 0.1e6, f"größte Vergleichsspannung {vm / 1e6:.3f} N/mm²")


def test_gehalten_unsymmetrisch():
    for o in (1, 2):
        m = _platte(o, UNSYM)
        typen = sorted({e.typ for e in m.elements})
        for n in range(m.nn):
            m.fix(n, "all")
        r, acc = _rechnen(m)
        n_soll, m_soll = -1.2e6, +1500.0
        check(f"{typen}: voll gehalten: n_x = n_y = −N_T = −1 200 N/mm",
              np.abs(acc[:, :2] - n_soll).max() < 1e-6 * abs(n_soll) and np.abs(acc[:, 2]).max() < 1.0,
              f"n_x {acc[0, 0] / 1e3:.3f}, n_y {acc[0, 1] / 1e3:.3f} N/mm")
        check(f"{typen}: voll gehalten: m_x = m_y = −M_T = +1 500 N",
              np.abs(acc[:, 3:5] - m_soll).max() < 1e-6 * abs(m_soll) and np.abs(acc[:, 5]).max() < 1e-3,
              f"m_x {acc[0, 3]:.3f}, m_y {acc[0, 4]:.3f} Nm/m")


def test_symmetrisch_und_homogen_unveraendert():
    for name, lagen in (("symmetrischer Dreischichter", SYM), ("homogen", [])):
        m = _platte(2, lagen)
        typen = sorted({e.typ for e in m.elements})
        for n in range(m.nn):
            m.fix(n, "all")
        r, acc = _rechnen(m)
        mat = m.materials["S235"]
        # homogen: E t/(1−ν) α ΔT; Dreischichter: (2·2,5·100 000 + 5·300 000) N/mm · 6e-4 = 1 200 N/mm
        n_soll = -(mat.E * 0.010 / (1 - mat.nu) * mat.alpha * DT if not lagen else 1.2e6)
        check(f"{typen}: {name}, voll gehalten: n = {n_soll / 1e3:.1f} N/mm, m = 0 (wie bisher)",
              np.abs(acc[:, :2] - n_soll).max() < 1e-6 * abs(n_soll) and np.abs(acc[:, 3:]).max() < 1e-3,
              f"n_x {acc[0, 0] / 1e3:.3f} N/mm, größtes |m| {np.abs(acc[:, 3:]).max():.6f} Nm/m")


def main():
    for t in (test_frei_unsymmetrisch, test_gehalten_unsymmetrisch, test_symmetrisch_und_homogen_unveraendert):
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
