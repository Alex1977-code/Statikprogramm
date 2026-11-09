"""
Anschlussnachweis ohne f_u bzw. f_y im Werkstoff (Befund A23 der
Pruefagenten, 09.11.2026). Festlegung des Anwenders: f_u kommt aus dem
Werkstoff; fehlt es, gibt es eine Meldung und keinen Vorgabewert. Bis dahin
rechnete der Anschluss still mit 1,3 f_y (Werkstoff mit f_y, ohne f_u) bzw.
mit S355-Werten f_y = 355, f_u = 510 N/mm² (Werkstoff ganz ohne Festigkeiten):
die Lasche ging von η = 1,048 auf 1,573.

Erwartung (IPE 300, Kragarm 4 m, Lasche und Kopfplatte am Einspannende):
  * f_y 235, f_u 360 angegeben: Nachweis wie bisher (Lasche η = 1,0484)
  * nur Sorte S235: f_y, f_u aus der Sortentabelle, Nachweis gleich
  * f_y 235 ohne f_u: kein Nachweis, Fehler nennt f_u und den Werkstoff
  * ohne f_y und f_u und ohne Sorte: kein Nachweis, Fehler nennt f_y und f_u

Aufruf:  python -m tests.test_anschluss_festigkeit
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _nachweis(fy, fu, grade, art):
    from statik3d.model import Model, Material, Section
    from statik3d import mesher, solver
    from statik3d.joints import anschluss, templates
    m = Model("A")
    m.add_material(Material("X", E=210e9, nu=0.3, rho=7850, fy=fy, fu=fu, grade=grade))
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    ids = mesher.line_of_beams(m, "X", "IPE300", (0, 0, 0), (4, 0, 0), n=4)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-20000.0)
    an = solver.solve_all(m, workers=1, combinations=False)
    # Die Geometrie kommt aus dem Vorschlag mit vollstaendigem Werkstoff (235/360): seit dem
    # 09.11.2026 gibt es ohne f_y oder f_u auch keinen Vorschlag mehr (Nebenbefund 15,
    # tests.test_nachweis_ohne_fu). Nachgewiesen wird mit dem Werkstoff des Falls.
    fall = m.materials["X"]
    m.materials["X"] = Material("X", E=210e9, nu=0.3, rho=7850, fy=235e6, fu=360e6)
    t = templates.propose(art, m, 0, end=0, N=0.0, Vz=20000.0, My=80000.0)
    m.materials["X"] = fall
    j = anschluss.als_joint(t, name=f"J_{art}")
    m.joints[j.name] = j
    c = anschluss.check_joint(m, j, dict(an.cases), analysis=an)
    c.modell = m
    return c


def _eta(c):
    return getattr(c, "util", getattr(c, "eta", None))


def test_festigkeiten():
    for art, eta_soll in (("lasche", 1.0484135), ("kopfplatte", 0.7932072)):
        c = _nachweis(235e6, 360e6, "", art)
        check(f"{art}: f_y 235, f_u 360 angegeben: η = {eta_soll:.4f} wie bisher",
              not c.fehler and abs(float(_eta(c)) - eta_soll) < 1e-6, f"η = {_eta(c)}, Fehler {c.fehler!r}")
        c = _nachweis(None, None, "S235", art)
        check(f"{art}: nur Sorte S235: Werte aus der Tabelle, η = {eta_soll:.4f}",
              not c.fehler and abs(float(_eta(c)) - eta_soll) < 1e-6, f"η = {_eta(c)}, Fehler {c.fehler!r}")
        c = _nachweis(235e6, None, "", art)
        check(f"{art}: f_y ohne f_u: kein Nachweis, Fehler nennt f_u und Werkstoff „X“",
              bool(c.fehler) and "f_u" in c.fehler and "X" in c.fehler, f"Fehler {c.fehler!r}")
        c = _nachweis(None, None, "", art)
        check(f"{art}: ohne f_y, f_u und Sorte: kein Nachweis, Fehler nennt f_y und f_u",
              bool(c.fehler) and "f_y" in c.fehler and "f_u" in c.fehler, f"Fehler {c.fehler!r}")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("anschluss_festigkeit")
    ja = _nachweis(235e6, None, "", "lasche").modell
    nein = _nachweis(235e6, 360e6, "", "lasche").modell
    check("Verfahrenstabelle: „anschluss_festigkeit“ Fehlerkorrektur Stand 13, nur Anschluss ohne f_u",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 13
          and rv.VERFAHRENSSTAND >= 13 and mk.betrifft(ja) and not mk.betrifft(nein))


def main():
    for t in (test_festigkeiten, test_verfahrenstabelle):
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
