"""
Theorie III. Ordnung (grosse Verformungen, korotational) und die Theoriewahl
je Lastfall und Kombination.

Geschlossene Loesungen: Kragarm unter Endmoment rollt sich zum Kreisbogen,
Elastica-Kragarm unter Querlast (Mattiasson 1981), Seil aus zwei
Fachwerkstaeben, Vergleich II./III. Ordnung am Druckstab mit Querlast.
Aufruf:  python -m tests.test_theorie3
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Section, Combination  # noqa: E402
from statik3d import solver  # noqa: E402
from statik3d.theorie3 import solve_theorie3, rot_exp, rot_log  # noqa: E402

RESULTS = []
E = 210e9


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6f} ana={want:.6f} Abw={err * 100:.3f}% {unit}")


def kragarm(ne: int = 10, L: float = 2.0):
    """Ebener Kragarm in der x-z-Ebene, schubstarr, ohne Imperfektionen."""
    m = Model("Kragarm")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.05, 0.05)
    sec.Asy = sec.Asz = 0.0
    m.add_section(sec)
    for i in range(ne + 1):
        m.add_node(i * L / ne, 0, 0)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S", "R")
    m.fix(0, "all")
    for i in range(1, ne + 1):
        m.fix(i, [1, 3, 5])
    m.design.imperfektionen = False
    return m, sec


def test_drehungen():
    for th in ([0.1, -0.2, 0.3], [3.0, 0.5, -0.4], [1e-9, 0, 0], [0, 0, math.pi - 1e-4]):
        check(f"exp/log Drehvektor {np.round(th, 3).tolist()}",
              np.allclose(rot_log(rot_exp(th)), th, atol=1e-8))
    R = rot_exp([0.3, 0.2, 0.1])
    check("Drehmatrix orthonormal", np.allclose(R @ R.T, np.eye(3)) and abs(np.linalg.det(R) - 1) < 1e-12)


def test_kreisbogen():
    """Endmoment M = (π/2)·EI/L: der Kragarm wird zum Viertelkreis."""
    ne, L = 10, 2.0
    m, sec = kragarm(ne, L)
    EI = E * sec.Iy
    M = (math.pi / 2) * EI / L
    m.load_node(ne, My=M)
    res, info = solve_theorie3(m, {"LF1": 1.0}, "M", schritte=10)
    check("konvergiert", info.gerechnet and not info.fehler, info.text())
    r = 2 * L / math.pi                                    # Radius EI/M
    close("Viertelkreis: x der Spitze = 2L/π", L + res.u[ne, 0], r, 2e-3, "m")
    close("Viertelkreis: Durchbiegung der Spitze = 2L/π", abs(res.u[ne, 2]), r, 2e-3, "m")
    close("Viertelkreis: Drehung der Spitze = 90°", info.drehung_max, math.pi / 2, 1e-6, "rad")
    # Moment konstant ueber die Laenge, keine Normalkraft, keine Querkraft
    My = [abs(res.beam_end[i][4]) for i in range(ne)]
    close("Moment konstant = M", max(My), M, 2e-3, "Nm")
    check("keine Normal- und Querkraft im reinen Biegefall",
          max(abs(res.beam_end[i][0]) for i in range(ne)) < 1e-6 * M / L
          and max(abs(res.beam_end[i][2]) for i in range(ne)) < 1e-6 * M / L)
    check("Auflagermoment = M, Auflagerkraft null",
          abs(abs(res.reactions[0, 4]) - M) < 1e-6 * M and abs(res.reactions[0, 2]) < 1e-6 * M / L)


def test_elastica():
    """Querlast P·L²/EI = 1 (Mattiasson 1981): w/L = 0,30172, u/L = 0,05643, θ = 0,46135."""
    ne, L = 12, 2.0
    m, sec = kragarm(ne, L)
    EI = E * sec.Iy
    P = EI / L ** 2
    m.load_node(ne, Fz=-P)
    res, info = solve_theorie3(m, {"LF1": 1.0}, "P", schritte=10)
    close("Elastica: Durchbiegung w/L", -res.u[ne, 2] / L, 0.30172, 3e-3)
    close("Elastica: Verkuerzung u/L", -res.u[ne, 0] / L, 0.05643, 5e-3)
    close("Elastica: Enddrehung", abs(res.u[ne, 4]), 0.46135, 3e-3, "rad")
    # linear waere w = PL³/3EI = L/3: die grosse Verformung ist kleiner
    close("Bezug Theorie I: u_max_I = L/3", info.u_max_I, L / 3, 1e-9, "m")
    check("Zuwachs negativ (Versteifung durch die Verformung)", info.zuwachs < -0.05)
    # Ergebnis nennt die Theorie
    check("Ergebnis nennt Theorie III", res.info.get("theorie") == "III. Ordnung")


def test_seil():
    """Zwei Fachwerkstaebe, fast gestreckt, Querlast in der Mitte - exakt."""
    m = Model("Seil")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.01, 0.01)
    m.add_section(sec)
    L0, w0 = 1.0, 0.02
    m.add_node(0, 0, 0)
    m.add_node(L0, 0, -w0)
    m.add_node(2 * L0, 0, 0)
    m.add_element("truss", [0, 1], "S", "R")
    m.add_element("truss", [1, 2], "S", "R")
    m.fix(0, "all")
    m.fix(2, "all")
    m.fix(1, [1, 3, 4, 5])
    m.design.imperfektionen = False
    EA = E * sec.A
    w = 0.1
    Li, Lw = math.hypot(L0, w0), math.hypot(L0, w)
    N = EA * (Lw - Li) / Li
    F = 2 * N * w / Lw
    m.load_node(1, Fz=-F)
    res, info = solve_theorie3(m, {"LF1": 1.0}, "Seil", schritte=10)
    close("Seil: Durchhang", -res.u[1, 2], w - w0, 1e-7, "m")
    close("Seil: Normalkraft", res.beam_end[0][6], N, 1e-7, "N")
    close("Seil: Auflagerkraft = F/2", abs(res.reactions[0, 2]), F / 2, 1e-7, "N")


def test_druckstab_II_gegen_III():
    """Gelenkig gelagerter Druckstab mit Querlast, P = 0,5 P_cr: II. und III.
    Ordnung stimmen bei maessiger Verformung ueberein (Vergroesserung ≈ 2)."""
    ne, L = 12, 4.0
    m = Model("Druckstab")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.05, 0.05)
    sec.Asy = sec.Asz = 0.0
    m.add_section(sec)
    for i in range(ne + 1):
        m.add_node(i * L / ne, 0, 0)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S", "R")
    m.fix(0, [0, 1, 2, 3, 5])
    m.fix(ne, [1, 2, 3, 5])
    for i in range(1, ne):
        m.fix(i, [1, 3, 5])
    m.design.imperfektionen = False
    EI = E * sec.Iy
    Pcr = math.pi ** 2 * EI / L ** 2
    P = 0.5 * Pcr
    q = 50.0
    m.load_node(ne, Fx=-P)
    for i in range(ne):
        m.load_beam(i, qz=-q)
    from statik3d.theorie2 import solve_theorie2
    r2, i2 = solve_theorie2(m, {"LF1": 1.0}, "II", imperfektionen=False)
    r3, i3 = solve_theorie3(m, {"LF1": 1.0}, "III", schritte=10)
    w1 = 5 * q * L ** 4 / (384 * EI)
    close("Theorie I: w = 5qL⁴/384EI", i3.u_max_I, w1, 1e-6, "m")
    w2, w3 = abs(r2.u[ne // 2, 2]), abs(r3.u[ne // 2, 2])
    close("Theorie II: Vergroesserung ≈ 1/(1 − P/P_cr) = 2", w2 / w1, 2.0, 0.02)
    close("Theorie III = Theorie II bei maessiger Verformung", w3, w2, 1e-2, "m")


def test_theoriewahl():
    """theorie je Lastfall / Kombination in solve_all."""
    ne, L = 10, 2.0
    m, sec = kragarm(ne, L)
    EI = E * sec.Iy
    M = (math.pi / 2) * EI / L
    m.add_load_case("LF1", "G")
    m.load_node(ne, My=M, case="LF1")
    m.add_load_case("LF2", "G")
    m.load_node(ne, Fz=-1000.0, case="LF2")
    m.load_cases["LF1"].theorie = "III"
    m.combinations["K1"] = Combination("K1", {"LF2": 1.5}, "ULS", theorie="II")
    m.combinations["K2"] = Combination("K2", {"LF2": 1.0}, "ULS", theorie="I")
    m.combinations["K3"] = Combination("K3", {"LF1": 1.0}, "ULS", theorie="III")
    m.design.theorie2 = "aus"
    check("theorie_von: Lastfall III, Kombinationen II / I / III, Vorgabe I",
          m.theorie_von(m.load_cases["LF1"]) == "III" and m.theorie_von(m.load_cases["LF2"]) == "I"
          and [m.theorie_von(m.combinations[k]) for k in ("K1", "K2", "K3")] == ["II", "I", "III"])
    m.design.theorie2 = "ein"
    check("Einstellung 'ein' gilt nur fuer Kombinationen ohne eigene Wahl",
          m.theorie_von(Combination("x", {"LF2": 1.0}, "ULS")) == "II"
          and m.theorie_von(m.combinations["K2"]) == "I" and m.theorie_von(m.load_cases["LF2"]) == "I")
    m.design.theorie2 = "aus"
    an = solver.solve_all(m)
    r = an.cases["LF1"]
    check("Lastfall nach Theorie III. Ordnung gerechnet (Viertelkreis)",
          r.info.get("theorie") == "III. Ordnung" and abs(abs(r.u[ne, 2]) - 2 * L / math.pi) < 5e-3
          and an.theorie3 is not None and "LF1" in an.theorie3.kombinationen)
    check("Kombination II erzwungen trotz Einstellung 'aus'",
          an.theorie2 is not None and "K1" in an.theorie2.kombinationen
          and an.theorie2.kombinationen["K1"].gerechnet
          and an.combinations["K1"].info.get("theorie") == "II. Ordnung")
    check("Kombination I bleibt Superposition",
          an.combinations["K2"].info.get("superposition") is True)
    check("Kombination III gerechnet",
          "K3" in an.theorie3.kombinationen and an.combinations["K3"].info.get("theorie") == "III. Ordnung")
    close("Kombination III = Lastfall III", abs(an.combinations["K3"].u[ne, 2]), abs(r.u[ne, 2]), 1e-9)
    # Speichern
    import json
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Theorie ueberlebt Speichern", m2.load_cases["LF1"].theorie == "III"
          and m2.combinations["K1"].theorie == "II" and m2.design.th3_schritte == 10)
    # Grenzen: Flaechen -> Fehler mit Hinweis
    from statik3d import mesher
    mp = Model("Platte")
    mp.add_material(Material("S"))
    from statik3d.model import ShellProp
    mp.add_shell_prop(ShellProp("t", 0.01))
    mesher.plate_mesh(mp, "S", "t", 1.0, 1.0, 2, 2) if hasattr(mesher, "plate_mesh") else None
    if mp.elements:
        mp.fix(0, "all")
        mp.load_node(mp.nn - 1, Fz=-1.0)
        try:
            solve_theorie3(mp, {mp.active_case: 1.0}, "x")
            check("Flaechen: Theorie III wird abgewiesen", False)
        except ValueError as ex:
            check("Flaechen: Theorie III wird abgewiesen", "Stabtragwerke" in str(ex))


def main():
    for t in (test_drehungen, test_kreisbogen, test_elastica, test_seil,
              test_druckstab_II_gegen_III, test_theoriewahl):
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
