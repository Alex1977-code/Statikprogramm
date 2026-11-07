"""„Frei drehbar“ streng auslegen (Vorgabe des Anwenders vom 16.10.2026, Punkt 3).

Woertlich: „‚Frei drehbar‘ streng auslegen: ja. Warnung, wenn die Drehung nur
numerisch gehalten wird (weiche Feder, Pivot-Regularisierung). Information nur
bei echter Zwangsbedingung ohne Last am Freiheitsgrad. Kraft bzw. Moment in
numerischen Haltungen in die Gleichgewichtskontrolle aufnehmen.“

„Echte Zwangsbedingung“ heisst: Der Freiheitsgrad ist durch die Bedingung
bestimmt, mit endlicher, nicht verschwindender Steifigkeit aus der Kopplung,
nicht nur durch einen angehobenen Pivot. Am Drehlager-Entwurf mit Lochrand
hielt die Drehung des Ankerkopfs K157 eine wirksame Steifigkeit von 0,4 bis
66 Nm/rad bei 3,2e13 Nm/rad auf der Hauptdiagonale (357 gestoerte Pivots,
scratchpad fix_exetest_arbeit/a6b.out): die Unterlegbleche schwimmen, die
starre Scheibe bindet den Kopf an ein Blech, das sich selbst frei dreht.

Pruefkoerper: das Blech aus tests/test_scheibe_kreisring (60 x 60 x 20 mm,
Bohrung 20, Schraube Rund 20 senkrecht darunter, unten fest), hier nur
senkrecht und an einem Knoten waagrecht gelagert - es dreht sich frei um eine
senkrechte Achse wie die Unterlegbleche am Drehlager. Last: 50 kN auf den
Schraubenkopf.

* Lochrand (starre Scheibe RBE2 mit Drehanteil): der Kopf ist nur numerisch
  gehalten - WARNUNG mit Grund und wirksamer Steifigkeit, keine Information.
* Kreisring (RBE3 ohne Momentenzeilen am Fachwerkstab): die Drehung des Kopfs
  haengt an nichts und ist automatisch gesperrt - keine Meldung am Kopf.
* Blech voll gelagert (Lochrand): keine gestoerten Pivots, keine Meldung.
* Moment um die freie Achse am Kopf: die Gleichgewichtskontrolle nennt es als
  numerisch gehalten (ein grosses Moment bricht schon der Gleichungsloeser als
  singulaer ab); eine Last an automatisch gehaltenen FHG zaehlt mit, ab 1 % der
  Lasten ist das Ergebnis nicht gueltig.
* Die Stufung selbst: Information nur ohne numerische Haltung.

Aufruf:  python -m tests.test_frei_drehbar_streng
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import singular as sg, solver                      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {str(detail)[:240]}")
    return bool(ok)


def blech(ring: bool, frei: bool = True, Mz: float = 0.0):
    from tests import test_scheibe_kreisring as T
    m = T.blech(h=0.006, ordnung=1, ring=ring, plast=False)
    kopf = int(m._mitte)
    fuss = next(int(e.nodes[1]) for e in m.elements if e.typ == "truss")
    lc = m.load_cases["LF1"]
    lc.vorspannungen = []
    m.load_node(kopf, Fz=-50e3, Mz=Mz, case="LF1")
    if frei:
        unten = sorted(i for i in range(m.nn) if abs(m.nodes[i][2]) < 1e-9 and i != fuss)
        m.supports = [s for s in m.supports if int(s.node) == fuss]
        for i in unten:
            m.fix(i, [2])
        m.fix(unten[0], [0, 1])
    return m, kopf


def teile(r):
    return list((r.info or {}).get("freie_teile") or [])


def am_kopf(r, kopf):
    return [e for e in teile(r) if kopf in (e.get("knoten") or [])]


# --------------------------------------------------------------------------
def test_stufung():
    print("\n--- 1. Stufung: Information nur ohne numerische Haltung ---")
    from tests.test_freie_teile import STAB_KNOTEN, stab_mit_freiem_knoten
    from statik3d.model import Kopplung
    m = stab_mit_freiem_knoten()
    n2 = int(m.add_node(1.0, 0.0, 0.0))
    m.kopplungen.append(Kopplung(STAB_KNOTEN, n2, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [float("inf")] * 3,
                                 gruppe="starr F37"))
    z_achse = np.array([[0.0], [0.0], [1.0]])
    keine = np.zeros((3, 0))
    lasten = sg.last_je_knoten(m, [STAB_KNOTEN])
    zw, fe = sg.zwang_je_knoten(m, [STAB_KNOTEN])
    s, halt = sg.stufe_freier_knoten(m, STAB_KNOTEN, keine, z_achse, lasten, zw, fe,
                                     numerisch={"k_eff": 0.36, "k_diag": 3.2e13})
    check("Zwangsbedingung, keine Last, aber nur numerisch gehalten: WARNUNG mit Grund",
          s == "WARNUNG" and "numerisch" in halt and "Pivot" in halt, f"{s}: {halt}")
    check("… der Grund nennt die wirksame Steifigkeit", "0,36" in halt, halt)
    s, halt = sg.stufe_freier_knoten(m, STAB_KNOTEN, keine, z_achse, lasten, zw, fe, numerisch=False)
    check("Zwangsbedingung bestimmt den Freiheitsgrad (gemessen), keine Last: INFORMATION",
          s == "INFORMATION" and "starr F37" in halt, f"{s}: {halt}")
    s, halt = sg.stufe_freier_knoten(m, STAB_KNOTEN, keine, z_achse, lasten, zw, fe, numerisch="unbekannt")
    check("nicht gemessen: im Zweifel WARNUNG (streng)", s == "WARNUNG" and "Pivot" in halt, f"{s}: {halt}")


def test_lochrand_schwimmend():
    print("\n--- 2. Lochrand, Blech dreht sich frei: Warnung am Kopf ---")
    m, kopf = blech(ring=False)
    r = solver.solve_static(m, workers=1)
    such = (r.info or {}).get("freie_teile_suche") or {}
    check("gestörte Pivots (das Blech dreht sich frei)", int(such.get("gestoerte_pivots", 0) or 0) > 0, str(such)[:200])
    e = am_kopf(r, kopf)
    check("Eintrag am Schraubenkopf", bool(e), str([x.get("text", "")[:120] for x in teile(r)])[:240])
    if e:
        e = e[0]
        check("… Stufe WARNUNG, keine Information", e.get("stufe") == "WARNUNG", e.get("stufe"))
        t = e.get("text", "")
        check("… der Text sagt „nur numerisch gehalten“ und nennt die wirksame Steifigkeit",
              "nur numerisch gehalten" in t and "wirksame Steifigkeit" in t, t[t.find("(nur"):][:240])
        check("… die Drehung um z ist genannt", "um z" in e.get("bewegung", ""), e.get("bewegung"))
    zl = [z for z in r.summary().splitlines() if f"K{kopf}" in z]
    check("Zusammenfassung: WARNUNG-Zeile am Kopf", any(z.startswith("WARNUNG") for z in zl), str(zl)[:200])


def test_kreisring_schwimmend():
    print("\n--- 3. Kreisring, Blech dreht sich frei: keine Meldung am Kopf ---")
    m, kopf = blech(ring=True)
    r = solver.solve_static(m, workers=1)
    check("kein Eintrag am Schraubenkopf", not am_kopf(r, kopf), str([x.get("text", "")[:120] for x in teile(r)])[:240])


def test_gehalten():
    print("\n--- 4. Blech voll gelagert: keine Meldung ---")
    for ring in (False, True):
        m, kopf = blech(ring=ring, frei=False)
        r = solver.solve_static(m, workers=1)
        check(f"{'Kreisring' if ring else 'Lochrand'}, voll gelagert: keine frei beweglichen Teile",
              not teile(r), str([x.get("text", "")[:100] for x in teile(r)])[:200])
        g = r.info.get("gleichgewicht_global") or {}
        check("… keine numerische Haltung in der Gleichgewichtskontrolle",
              float((g.get("numerisch") or {}).get("norm", 0.0)) == 0.0, str(g.get("numerisch"))[:160])


def test_gleichgewicht():
    print("\n--- 5. Moment um die freie Achse: in der Gleichgewichtskontrolle ---")
    # Ein Moment um die freie Achse bricht schon der Gleichungsloeser als „singulär“
    # ab (seine Residuumschranke 1e-6 der Last sieht dasselbe, gemessen bis 0,01 Nm
    # bei 50 kN). Die Projektion selbst an einem Eintrag, wie pivotbefund ihn schreibt:
    from tests import test_scheibe_kreisring as T
    m, kopf = blech(ring=False)
    F = np.zeros(m.ndof)
    F[6 * kopf + 2], F[6 * kopf + 5] = -50e3, 30.0
    eintrag = {"stufe": "WARNUNG", "modus": [{"art": "knoten", "knoten": kopf, "Vt": [[0.7071, -0.7071, 0.0]],
                                             "Vr": [[0.0, 0.0, 1.0]]}]}
    r_num, n = sg.numerische_haltung(m, F, [eintrag])
    check("Projektion: 30 Nm um die freie Achse z, die senkrechte Kraft fällt nicht auf die freie Bewegung",
          r_num is not None and abs(r_num[6 * kopf + 5] - 30.0) < 1e-9 and abs(r_num[6 * kopf + 2]) < 1e-9,
          "" if r_num is None else str(r_num[6 * kopf:6 * kopf + 6]))
    r_num, n = sg.numerische_haltung(m, F, [dict(eintrag, stufe="INFORMATION", modus=[])])
    check("eine Information (echte Zwangsbedingung) hält nichts numerisch", r_num is None, "")
    m, kopf = blech(ring=False)
    r = solver.solve_static(m, workers=1)
    g = r.info.get("gleichgewicht_global") or {}
    check("Lochrand schwimmend ohne Last an der freien Bewegung: keine numerische Haltung ausgewiesen",
          not g.get("numerisch"), str(g.get("numerisch"))[:160])
    # Last an automatisch gehaltenen FHG (tests/test_auto_gehalten: Kette aus zwei
    # Fachwerkstaeben, 1 kN quer): sie zaehlt mit
    from tests.test_auto_gehalten import kette
    r = solver.solve_static(kette(), case="LF1")
    g = r.info.get("gleichgewicht_global") or {}
    nm = g.get("numerisch") or {}
    Fz = float((nm.get("F") or [0, 0, 0])[2])
    check("Kette, 1 kN quer am automatisch gehaltenen FHG: 1 kN nur numerisch gehalten, verletzt",
          abs(Fz + 1e3) <= 1e-6 and nm.get("verletzt") is True, str(nm)[:200])
    z = next((x for x in r.summary().splitlines() if x.startswith("Gleichgewicht global")), "")
    check("… die Zeile sagt NICHT GÜLTIG und nennt die numerische Haltung",
          "NICHT GÜLTIG" in z and "numerisch gehalten" in z, z[:240])


def main():
    for f in (test_stufung, test_lochrand_schwimmend, test_kreisring_schwimmend, test_gehalten,
              test_gleichgewicht):
        try:
            f()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
