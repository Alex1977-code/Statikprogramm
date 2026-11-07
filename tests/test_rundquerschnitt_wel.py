"""W_el der Rundquerschnitte im frischen RFEM-Import (06.11.2026).

Die rf6-Datei fuehrt fuer einen Rundstahl A, A_y, A_z, I_y, I_z, I_t (und W_pl),
aber kein W_el. Der Import setzte die Kennwerte nach ``Section.__post_init__``,
darum blieb W_el = 0 (Drehlager: Rund 16/20/40). Davon haengen die Randspannung
aus Normalkraft und Biegung (Ermuedung, Querschnittsklasse 3, Schalenbeulen)
ab: dort steht dann 1e-30 im Nenner. Jetzt: W_el = pi d^3 / 32.

Aufruf:  python -m tests.test_rundquerschnitt_wel
"""
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.importers import rfem6_db as R6                      # noqa: E402
from tests.test_rfem6 import INF, make_rf6                          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def test_wel():
    print("\n--- W_el = pi d^3 / 32 am Rundstahl aus dem Import ---")
    tmp = tempfile.mkdtemp()
    try:
        f = make_rf6(os.path.join(tmp, "rund.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                     members=[(1, None, None)],
                     supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1])])
        m = R6.read_rf6(f, log=[])
        sec = list(m.sections.values())[0]
        d = 0.040
        soll = math.pi * d ** 3 / 32.0
        check("Rund 40: W_el,y = pi d^3/32 (6,283 cm3)", abs(sec.Wel_y - soll) < 1e-9 * soll, sec.Wel_y)
        check("… und W_el,z ebenso", abs(sec.Wel_z - soll) < 1e-9 * soll, sec.Wel_z)
        check("… gleich I/z_max", abs(sec.Wel_y - sec.Iy / sec.zmax) < 1e-12, "")
        check("W_pl bleibt wie die Datei es fuehrt (hier nicht eingetragen: nicht erfunden)",
              sec.Wpl_y == 0.0 or abs(sec.Wpl_y - d ** 3 / 6) < 1e-12, sec.Wpl_y)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    try:
        test_wel()
    except Exception as ex:                      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
