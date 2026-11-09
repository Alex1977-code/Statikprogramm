"""
Kontaktbedingung, die nur Koerper nennt (Befund A17 der Pruefagenten,
09.11.2026). Bis dahin blieb eine Bedingung mit ``koerpernamen`` und
``gegenkoerper``, aber ohne Flaechen, unausgefuehrt; mit einer zweiten
Halterung (Feder am oberen Koerper) lief die ganze Last still durch die Feder.

Jetzt sind die Flaechen der Gegenkoerper die Gegenseite, und die Fuge sind die
Randseiten des geloesten Koerpers, die auf ihnen liegen.

Modell: zwei Quader 0,2 × 0,2 × 0,1 m uebereinander (eigene Knoten, Fuge bei
z = 0,1), unten fest, oben p = 10 N/mm² auf der Oberseite (400 kN).
  * nur Koerper: ausgefuehrt, ein Kontaktpaar ueber die ganze Unterseite (400 cm²)
  * frei: ΣRz = 400 kN
  * mit Feder an der Oberseite: der untere Koerper traegt ueber den Kontakt -
    Gegenprobe ueber einen anderen Eingabeweg: dieselbe Bedingung mit den
    Flaechen OB (geloest) und AD (Gegenseite) genannt - gleiche Lagerkraefte
    unten und oben.
  * die Bedingung bleibt, wie eingegeben (keine Gegenflaechen eingetragen).

Aufruf:  python -m tests.test_kontakt_nur_koerper
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
B, H, P = 0.2, 0.1, 10e6
F = P * B * B


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _quader(m, name, z0, zaehler):
    E = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float) * [B, B, H] + [0, 0, z0]
    b = m.nn
    m.add_nodes(E)

    def linie(a, c):
        zaehler[0] += 1
        m.add_line(f"L{zaehler[0]}", [b + a, b + c])
        return f"L{zaehler[0]}"
    R0 = [linie(i, (i + 1) % 4) for i in range(4)]
    R1 = [linie(4 + i, 4 + (i + 1) % 4) for i in range(4)]
    V = [linie(i, 4 + i) for i in range(4)]
    m.add_flaeche(f"{name}B", R0, material="S235")
    m.add_flaeche(f"{name}D", R1, material="S235")
    for i in range(4):
        m.add_flaeche(f"{name}M{i}", [R0[i], V[(i + 1) % 4], R1[i], V[i]], material="S235")
    m.add_koerper(name, [f"{name}B", f"{name}D"] + [f"{name}M{i}" for i in range(4)], material="S235")


def _modell(art, feder):
    from statik3d.model import Model, Material, DofBehaviour
    from statik3d import mesher
    m = Model()
    m.add_material(Material.steel("S235"))
    z = [0]
    _quader(m, "A", 0.0, z)
    _quader(m, "O", H, z)
    m.netz.ziellaenge = 0.05
    if art == "koerper":
        kb = m.add_kontaktbedingung("K1", koerpernamen=["O"], gegenkoerper=["A"])
    else:
        kb = m.add_kontaktbedingung("K1", koerpernamen=["O"], flaechennamen=["OB"], gegenflaechen=["AD"])
    kb.standard_anwenden("Reibungsbehaftet")
    ss = m.add_surface_support(name="fest", **{d: DofBehaviour("rigid") for d in ("ux", "uy", "uz")})
    ss.flaechen = ["AB"]
    if feder:
        sf = m.add_surface_support(name="Feder", **{d: DofBehaviour("spring", 1e9) for d in ("ux", "uy", "uz")})
        sf.flaechen = ["OD"]
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0, 0, 0]
    m.add_geometrielast("OD", P, "flaeche", case="LF1")
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    return m, kb, log


def _rechnen(m):
    from statik3d import solver
    an = solver.solve_all(m, workers=1, combinations=False)
    r = an.cases["LF1"]
    R = np.asarray(r.reactions)[:, :3]
    unten = np.abs(m.nodes[:, 2]) < 1e-9
    oben = np.abs(m.nodes[:, 2] - 2 * H) < 1e-9
    return float(R[unten, 2].sum()), float(R[oben, 2].sum())


def test_nur_koerper():
    m, kb, log = _modell("koerper", feder=False)
    zeile = next((z for z in log if "Kontaktbedingung K1" in str(z)), "")
    check("nur Körper: ausgeführt, ein Kontaktpaar über die ganze Unterseite (400 von 400 cm²)",
          kb.ausgefuehrt and len(m.contact_pairs) == 1 and "400 von 400 cm²" in zeile, zeile[:120])
    check("die Bedingung bleibt, wie eingegeben (keine Gegenflächen eingetragen)",
          not kb.gegenflaechen and not kb.flaechennamen and kb.gegenkoerper == ["A"])
    unten, oben = _rechnen(m)
    check(f"frei: ΣRz unten = {F / 1e3:.1f} kN", abs(unten - F) < 1e-6 * F, f"{unten / 1e3:.3f} kN")


def test_mit_feder():
    m1, _, _ = _modell("koerper", feder=True)
    u1, o1 = _rechnen(m1)
    m2, kb2, _ = _modell("flaechen", feder=True)
    u2, o2 = _rechnen(m2)
    check("mit Feder oben: Lagerkraft unten + Feder = 400 kN, unten trägt (nicht still 0)",
          abs(u1 + o1 - F) < 1e-6 * F and u1 > 0.5 * F, f"unten {u1 / 1e3:.3f} kN, Feder {o1 / 1e3:.3f} kN")
    check("Gegenprobe Eingabe mit Flächen OB/AD: gleiche Lagerkräfte unten und oben",
          kb2.ausgefuehrt and abs(u1 - u2) < 1e-6 * F and abs(o1 - o2) < 1e-6 * F,
          f"Flächen: unten {u2 / 1e3:.3f} kN, Feder {o2 / 1e3:.3f} kN")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("kontakt_nur_koerper")
    ja, _, _ = _modell("koerper", feder=False)
    nein, _, _ = _modell("flaechen", feder=False)
    check("Verfahrenstabelle: „kontakt_nur_koerper“ Fehlerkorrektur Stand 14, nur Bedingung ohne Flächen",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 14
          and rv.VERFAHRENSSTAND >= 14 and mk.betrifft(ja) and not mk.betrifft(nein))


def main():
    for t in (test_nur_koerper, test_mit_feder, test_verfahrenstabelle):
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
