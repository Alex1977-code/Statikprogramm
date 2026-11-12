"""
Temperaturunterschied ΔT_z (oben − unten) auf Schalen (Befund A4 der
Pruefagenten, 09.11.2026). Bis dahin trug die Schale nur den gleichmaessigen
Anteil ΔT; ΔT_z wurde still verworfen (Kragstreifen 0 mm statt 12 mm).

Erwartung: ΔT_z erzeugt die Anfangskruemmung κ = α ΔT_z / t in beiden
Richtungen. „Oben“ ist die Seite der Elementnormalen (lokal +z).

1. Platte 1,0 × 0,2 m, t = 10 mm, statisch bestimmt an drei Ecken gelagert,
   ΔT_z = 20 K: die Platte kruemmt sich frei zur Kugelkappe
   w(x, y) = κ/2 · (x − x² + 0,2 y − y²), Mitte w = κ/2 · 0,26 = 3,120 mm nach
   oben, und bleibt momentenfrei. Exakt fuer jedes Netz, weil die Elemente
   konstante Kruemmung genau abbilden.
2. Kragstreifen, an x = 0 eingespannt, ν = 0: Spitze genau κ L² / 2 = 12,0 mm
   nach unten (Stabformel). Mit ν = 0,3 sperrt die Einspannung die
   Querkruemmung, ueber ν waechst dort die Laengskruemmung bis κ (1 + ν):
   12,59 mm (shell4) bzw. 12,53 mm (shell8), nicht Teil der Pruefung.
3. Gleichmaessiges ΔT bleibt wie bisher (Reaktion E α ΔT A zwischen Waenden).
Fuer beide Schalenformulierungen (DKT-Dreieck/-Viereck und Reissner-Mindlin
quadratisch).

Aufruf:  python -m tests.test_schale_temperatur_gradient
"""
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


def _platte(ordnung, dT=0.0, dT_z=20.0, teilung=(10, 2)):
    from statik3d import mesher
    from statik3d.model import Model, Material, ShellProp
    m = Model("Platte")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    for p in [(0, 0, 0), (1, 0, 0), (1, 0.2, 0), (0, 0.2, 0)]:
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j}", [j, (j + 1) % 4])
    f = m.add_flaeche("P", [f"L{j}" for j in range(4)], material="S235", dicke="t10")
    f.teilung = list(teilung)
    m.netz.ordnung = ordnung
    m.add_load_case("LF1", "Q")
    m.add_geometrielast("P", art="flaeche", lastart="temperatur", dT=dT, dT_z=dT_z, case="LF1")
    mesher.modell_vernetzen(m, log=[], workers=1)
    return m


def _knoten(m, x, y):
    d = np.hypot(m.nodes[:, 0] - x, m.nodes[:, 1] - y) + np.abs(m.nodes[:, 2])
    return int(np.argmin(d))


def _rechnen(m):
    from statik3d import solver
    return solver.solve_all(m, workers=1, combinations=False)


def test_freie_platte():
    for o in (1, 2):
        m = _platte(o)
        typen = sorted({e.typ for e in m.elements})
        a = m.materials["S235"].alpha
        kappa = a * 20.0 / 0.010
        # Normale der Elemente: oben = +z global?
        for n in range(m.nn):
            m.fix(n, [5])                       # Drillfreiheitsgrad: in der ebenen Platte ohne Wirkung
        m.fix(_knoten(m, 0, 0), [0, 1, 2])
        m.fix(_knoten(m, 1, 0), [1, 2])
        m.fix(_knoten(m, 0, 0.2), [2])
        res = _rechnen(m)
        U = np.asarray(res.cases["LF1"].u)
        X = m.nodes
        w_soll = kappa / 2.0 * (X[:, 0] - X[:, 0] ** 2 + 0.2 * X[:, 1] - X[:, 1] ** 2)
        # Vorzeichen der Elementnormalen (oben) bestimmt die Richtung
        e0 = m.elements[0]
        P = m.nodes[e0.nodes[:3]]
        nz = np.sign(np.cross(P[1] - P[0], P[2] - P[0])[2])
        w_soll = nz * w_soll
        fehler = np.abs(U[:, 2] - w_soll).max()
        mitte = _knoten(m, 0.5, 0.1)
        check(f"{typen}: freie Platte ΔT_z = 20 K, Kugelkappe, Mitte {nz * kappa / 2 * 0.26 * 1e3:+.3f} mm",
              fehler < 0.005 * abs(w_soll).max(),
              f"Mitte {U[mitte, 2] * 1e3:+.4f} mm, größte Abweichung {fehler * 1e6:.3f} µm")
        # momentenfrei: Schnittmomente gegen D κ (Moment bei voller Einspannung)
        D = m.materials["S235"].E * 0.010 ** 3 / (12 * (1 - m.materials["S235"].nu))
        mmax = 0.0
        for acc in res.cases["LF1"].shell_res.values():
            mmax = max(mmax, float(np.abs(np.asarray(acc, float)[3:5]).max()))
        check(f"{typen}: freie Platte momentenfrei (|m| < 0,1 % von D κ = {D * kappa:.1f} Nm/m)",
              mmax < 1e-3 * D * kappa, f"größtes |m| {mmax:.4f} Nm/m")


def test_kragstreifen():
    """Mit ν = 0 sind Laengs- und Querkruemmung entkoppelt: die Einspannung
    sperrt die Querkruemmung, beruehrt die Laengskruemmung aber nicht - die
    Spitze senkt sich genau um κ L²/2 (Stabformel). Oben warm: nach unten."""
    for o in (1, 2):
        m = _platte(o)
        m.materials["S235"].nu = 0.0
        typen = sorted({e.typ for e in m.elements})
        e0 = m.elements[0]
        P = m.nodes[e0.nodes[:3]]
        nz = np.sign(np.cross(P[1] - P[0], P[2] - P[0])[2])
        for n in np.where(np.abs(m.nodes[:, 0]) < 1e-9)[0]:
            m.fix(int(n), "all")
        res = _rechnen(m)
        U = np.asarray(res.cases["LF1"].u)
        spitze = np.where(np.abs(m.nodes[:, 0] - 1.0) < 1e-9)[0]
        w = float(U[spitze, 2].mean())
        a = m.materials["S235"].alpha
        soll = -nz * a * 20.0 / 0.010 / 2.0
        check(f"{typen}: Kragstreifen ν = 0, ΔT_z = 20 K oben warm: w_Spitze = κ L²/2 = {soll * 1e3:+.3f} mm",
              abs(w - soll) < 0.002 * abs(soll), f"w = {w * 1e3:+.4f} mm")


def test_gleichmaessig_unveraendert():
    for o in (1, 2):
        m = _platte(o, dT=30.0, dT_z=0.0)
        typen = sorted({e.typ for e in m.elements})
        links = np.where(np.abs(m.nodes[:, 0]) < 1e-9)[0]
        rechts = np.where(np.abs(m.nodes[:, 0] - 1.0) < 1e-9)[0]
        for n in links:
            m.fix(int(n), [0, 2, 3, 4, 5])
        for n in rechts:
            m.fix(int(n), [0, 2])
        m.fix(_knoten(m, 0, 0), [1])
        res = _rechnen(m)
        R = np.asarray(res.cases["LF1"].reactions)
        mat = m.materials["S235"]
        soll = mat.E * mat.alpha * 30.0 * 0.2 * 0.010
        check(f"{typen}: gleichmäßig ΔT = 30 K zwischen Wänden, |Rx| = E α ΔT A = {soll / 1e3:.2f} kN",
              abs(abs(R[links, 0].sum()) - soll) < 1e-3 * soll, f"{abs(R[links, 0].sum()) / 1e3:.3f} kN")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("temperatur_schale_dTz")
    ja = _platte(1)
    nein = _platte(1, dT=30.0, dT_z=0.0)
    check("Verfahrenstabelle: „temperatur_schale_dTz“ Fehlerkorrektur Stand 10, nur mit ΔT_z auf Schale",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 10
          and rv.VERFAHRENSSTAND >= 10 and mk.betrifft(ja) and not mk.betrifft(nein))


def main():
    for t in (test_freie_platte, test_kragstreifen, test_gleichmaessig_unveraendert, test_verfahrenstabelle):
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
