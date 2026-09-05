"""
Knicklaengenbeiwerte aus der Knickfigur (Eigenform).

Geprueft gegen die Eulerfaelle (β = 1, 2, 0,5, 0,7), gegen die Achse, um die
die Knickfigur biegt, und gegen Rahmen mit bekannter Knicklaenge.
Aufruf:  python -m tests.test_knicklaengen
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Section, Member  # noqa: E402
from statik3d import solver  # noqa: E402
from statik3d.ec3.knicklaengen import (knicklaengen_aus_eigenform,  # noqa: E402
                                       knicklaengen_uebernehmen)

RESULTS = []
E = 210e9


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.5f} ana={want:.5f} Abw={err * 100:.3f}% {unit}")


def _stuetze(L=4.0, ne=12, sec=None, name="St"):
    """Eine Stuetze auf der z-Achse als Stab mit Nachweis."""
    m = Model("Knick")
    m.add_material(Material("S235"))
    sec = sec or Section.rectangle("R", 0.05, 0.10)      # Iy > Iz: schwache Achse z
    m.add_section(sec)
    for i in range(ne + 1):
        m.add_node(0, 0, i * L / ne)
    for i in range(ne):
        m.add_element("beam", [i, i + 1], "S235", sec.name)
    m.members[name] = Member(name, list(range(ne)))
    return m, sec


def _euler(fuss, kopf, beta_soll, text, ne=12, L=4.0):
    m, sec = _stuetze(L, ne)
    m.fix(0, fuss)
    m.fix(ne, kopf)
    m.load_node(ne, Fz=-1000.0)
    r = solver.solve_buckling(m, nmodes=3)
    erg = knicklaengen_aus_eigenform(m, r)
    k = erg.staebe["St"]
    close(f"{text}: β_z = {beta_soll:g}", k.beta_z, beta_soll, 3e-3)
    check(f"{text}: Achse z (schwache Achse), beteiligt, β_y offen",
          k.achse == "z" and k.beta_y is None and k.beteiligt and k.beteiligung > 0.99,
          f"{k.achse} {k.beteiligung:.3f}")
    close(f"{text}: N_cr = α_cr·|N_Ed|", k.N_cr, r.buckling_factors[0] * 1000.0, 1e-9)
    return m, erg


def test_eulerfaelle():
    # Fall 2: beidseits gelenkig (Torsion gehalten), β = 1
    _euler([0, 1, 2, 5], [0, 1, 5], 1.0, "Euler 2 gelenkig-gelenkig")
    # Fall 1: unten eingespannt, oben frei, β = 2
    _euler("all", [], 2.0, "Euler 1 Kragstuetze")
    # Fall 4: beidseits eingespannt (oben vertikal frei), β = 0,5
    _euler("all", [0, 1, 3, 4, 5], 0.5, "Euler 4 eingespannt-eingespannt", ne=16)
    # Fall 3: unten eingespannt, oben gelenkig, β = 0,699
    _euler("all", [0, 1, 5], 0.6992, "Euler 3 eingespannt-gelenkig", ne=16)


def test_achse_und_uebernahme():
    # Kopf in y gehalten -> Knicken um y (in der x-z-Ebene) trotz Iy > Iz
    m, sec = _stuetze(4.0, 12)
    m.fix(0, [0, 1, 2, 3, 5])                     # gelenkig, Drehung um y frei
    m.fix(12, [0, 1, 3, 5])
    # Zwischenhalterung in y auf halber Hoehe: Knicken um z wird steifer
    for i in range(1, 12):
        m.fix(i, [1])                             # y gehalten ueber die ganze Laenge
    m.load_node(12, Fz=-1000.0)
    r = solver.solve_buckling(m, nmodes=3)
    erg = knicklaengen_aus_eigenform(m, r)
    k = erg.staebe["St"]
    check("y ueberall gehalten: Knickfigur biegt um y, β_y = 1", k.achse == "y"
          and k.beta_y is not None and abs(k.beta_y - 1.0) < 3e-3 and k.beta_z is None,
          f"{k.achse} {k.beta_y}")
    m.members["St"].beta_y = 7.0
    m.members["St"].beta_z = 7.0
    geaendert = knicklaengen_uebernehmen(m, erg)
    check("Uebernehmen schreibt nur die bestimmte Achse", geaendert == ["St"]
          and abs(m.members["St"].beta_y - k.beta_y) < 1e-12 and m.members["St"].beta_z == 7.0)
    # Zugstab: keine Knicklaenge
    m2, _ = _stuetze(4.0, 8)
    m2.fix(0, "all")
    m2.load_node(8, Fz=+1000.0)
    m2.load_node(4, Fy=10.0)                       # etwas Biegung, damit K_g nicht null ist
    try:
        r2 = solver.solve_buckling(m2, nmodes=2)
        erg2 = knicklaengen_aus_eigenform(m2, r2)
        k2 = erg2.staebe["St"]
        check("Zugstab bekommt keine Knicklaenge", k2.beta_y is None and k2.beta_z is None
              and "keine Druckkraft" in k2.hinweis, k2.hinweis)
    except RuntimeError as ex:
        check("Zugstab bekommt keine Knicklaenge", True, f"(kein Verzweigungsproblem: {ex})")
    tabelle = erg.tabelle()
    check("Tabelle mit Kopf und einer Zeile je Stab", tabelle[0][0] == "Stab" and len(tabelle) == 2
          and "St" in erg.summary())


def test_rahmen():
    """Zweistieliger Rahmen mit starrem Riegel (EI_R -> gross): eingespannte
    Fuesse -> β = 1 (verschieblich, Kopf drehbehindert); Fussgelenke -> β = 2."""
    for fuss, beta_soll, text in (("all", 1.0, "Rahmen eingespannt, starrer Riegel"),
                                  ([0, 1, 2, 3, 5], 2.0, "Rahmen Fussgelenke, starrer Riegel")):
        m = Model("Rahmen")
        m.add_material(Material("S235"))
        sec = Section.rectangle("R", 0.1, 0.1)
        m.add_section(sec)
        riegel = Section.rectangle("RR", 1.0, 1.0)            # praktisch starr
        m.add_section(riegel)
        h, b, ne = 4.0, 6.0, 10
        li = [m.add_node(0, 0, i * h / ne) for i in range(ne + 1)]
        re = [m.add_node(b, 0, i * h / ne) for i in range(ne + 1)]
        el_li = [m.add_element("beam", [li[i], li[i + 1]], "S235", "R") for i in range(ne)]
        el_re = [m.add_element("beam", [re[i], re[i + 1]], "S235", "R") for i in range(ne)]
        m.add_element("beam", [li[-1], re[-1]], "S235", "RR")
        m.members["links"] = Member("links", el_li)
        m.members["rechts"] = Member("rechts", el_re)
        m.fix(li[0], fuss)
        m.fix(re[0], fuss)
        for n in li + re:                                     # ebener Rahmen in x-z
            m.fix(n, [1, 3, 5])
        m.load_node(li[-1], Fz=-1000.0)
        m.load_node(re[-1], Fz=-1000.0)
        r = solver.solve_buckling(m, nmodes=3)
        erg = knicklaengen_aus_eigenform(m, r)
        for name in ("links", "rechts"):
            k = erg.staebe[name]
            close(f"{text}: β_y {name}", k.beta_y, beta_soll, 1e-2)
            check(f"{text}: {name} beteiligt (≈ 50 %)", k.beteiligt and 0.4 < k.beteiligung < 0.6,
                  f"{k.beteiligung:.3f}")
    # Ein kaum belasteter Stiel bleibt in der ersten Knickfigur gerade
    m = Model("zwei Stiele")
    m.add_material(Material("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.1))
    h, ne = 4.0, 10
    a = [m.add_node(0, 0, i * h / ne) for i in range(ne + 1)]
    c = [m.add_node(5, 0, i * h / ne) for i in range(ne + 1)]
    ea = [m.add_element("beam", [a[i], a[i + 1]], "S235", "R") for i in range(ne)]
    ec = [m.add_element("beam", [c[i], c[i + 1]], "S235", "R") for i in range(ne)]
    m.members["A"] = Member("A", ea)
    m.members["C"] = Member("C", ec)
    for n in (a[0], c[0]):
        m.fix(n, "all")
    for n in a + c:
        m.fix(n, [1, 3, 5])
    m.load_node(a[-1], Fz=-1000.0)
    m.load_node(c[-1], Fz=-10.0)
    r = solver.solve_buckling(m, nmodes=2)
    erg = knicklaengen_aus_eigenform(m, r)
    ka, kc = erg.staebe["A"], erg.staebe["C"]
    close("belasteter Kragstiel: β = 2", ka.beta_y, 2.0, 3e-3)
    check("kaum belasteter Stiel: unbeteiligt, als Obergrenze gekennzeichnet",
          not kc.beteiligt and "Obergrenze" in kc.hinweis and kc.beta_y > 10.0,
          f"{kc.beteiligung:.4f} β={kc.beta_y}")
    geaendert = knicklaengen_uebernehmen(m, erg)
    check("Uebernehmen nur fuer beteiligte Staebe", geaendert == ["A"] and m.members["C"].beta_y == 1.0)


def main():
    for t in (test_eulerfaelle, test_achse_und_uebernahme, test_rahmen):
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
