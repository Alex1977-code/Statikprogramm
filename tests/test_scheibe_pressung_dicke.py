"""Pressungsangabe der Scheibe: f_y dickenabhaengig (Auftrag 06.11.2026).

Die „mittlere Pressung ... = x f_y“ der Scheibentabelle bezog f_y bisher auf den
Nennwert (355 N/mm²). An der 60-mm-Ankerplatte S355 gilt nach EN 1993-1-1
Tab. 3.1 aber f_y = 335 N/mm². Jetzt wird f_y ueber ``Material.yield_strength``
mit der Dicke des Koerpers unter der Scheibe genommen (kleinste Abmessung
seines umschliessenden Quaders, wie im Volumennachweis); ist die Dicke nicht
bestimmbar, gilt der Werkstoffwert, und der Text sagt es.

Geprueft: 60-mm-Platte S355 -> 335; 20-mm-Platte -> 355; Ring 51/72 mm mit
944,4 kN -> 466 N/mm² = 1,39 f_y; ohne bestimmbare Dicke Werkstoffwert samt Hinweis.

Aufruf:  python -m tests.test_scheibe_pressung_dicke
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import scheibeneinleitung as SCH                           # noqa: E402
from tests import test_scheibe_kreisring as K                            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:200]}")
    return ok


def platte(t: float):
    alt = K.T_
    K.T_ = t
    try:
        return K.blech(h=0.012, ordnung=1, ring=True)
    finally:
        K.T_ = alt


def test_dicke():
    print("\n--- 1. f_y nach Erzeugnisdicke ---")
    z60 = SCH.scheiben(platte(0.06))[0]
    check("60 mm S355: f_y = 335 N/mm² (Tab. 3.1, über 40 mm)", abs(z60["fy"] - 335e6) < 1.0, z60["fy"])
    check("… die Dicke steht in der Zeile (60 mm)", abs(z60.get("dicke", 0.0) - 0.06) < 1e-6, z60.get("dicke"))
    z20 = SCH.scheiben(platte(0.02))[0]
    check("20 mm S355: f_y = 355 N/mm²", abs(z20["fy"] - 355e6) < 1.0, z20["fy"])
    # Ring 51/72, 944,4 kN
    z = dict(z60)
    z.update(einleitung=SCH.RING, d_innen=0.051, d_aussen=0.072, F=944.4e3)
    SCH.pressung_setzen(z)
    check("Ring Ø 51/72 mit 944,4 kN: 466 N/mm² = 1,39 f_y",
          abs(z["pressung"] / 1e6 - 465.5) < 0.5 and abs(z["verhaeltnis"] - 1.39) < 0.005, SCH.pressung_text(z))
    check("… der Text nennt f_y = 335 und die Dicke 60 mm",
          "335" in SCH.pressung_text(z) and "60" in SCH.pressung_text(z), SCH.pressung_text(z))


def test_ohne_dicke():
    print("\n--- 2. Dicke nicht bestimmbar: Werkstoffwert, der Text sagt es ---")
    z = dict(SCH.scheiben(platte(0.06))[0])
    z.update(einleitung=SCH.RING, d_innen=0.051, d_aussen=0.072, F=944.4e3, dicke=None, fy=355e6)
    SCH.pressung_setzen(z)
    t = SCH.pressung_text(z)
    check("ohne Dicke: f_y = 355 des Werkstoffs mit Hinweis „Dicke nicht bestimmbar“",
          "1,31 f_y" in t and "Dicke nicht bestimmbar" in t, t)


def main():
    for t in (test_dicke, test_ohne_dicke):
        try:
            t()
        except Exception as ex:                      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
