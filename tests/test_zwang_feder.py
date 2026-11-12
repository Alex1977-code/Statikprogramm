"""
Zwangsverformung an Lagern, die kein starres lineares Knotenlager sind
(Befund A11 der Pruefagenten, 09.11.2026). Bis dahin wirkte sie nur an starren
gesperrten FHG; an einer Feder, einem freien FHG oder einem Lager mit Ausfall
blieb sie still ohne Wirkung (Kragarm: 0 mm, 0 kN, keine Meldung).

Jetzt:
* Feder: die Vorgabe verschiebt den **Fusspunkt** der Feder. Federkraft
  k (u − d), Reaktion −k (u − d).
* freier FHG und Lager mit Ausfall: unwirksam - aber gemeldet
  („Zwangsverformung … unwirksam“), nicht still.
* starres Linienlager: wirkt wie bisher, die falsche Meldung „ohne Lager“
  entfaellt (Befund C1).

Kragarm L = 6 m, EI = 21 000 kNm², d = 10 mm nach unten am freien Ende.
Kragarmsteifigkeit k_b = 3 EI / L³ = 291,667 kN/m.
  * Feder k = 1000 kN/m: u = −k d / (k + k_b) = −7,7419 mm,
    Federreaktion −k (u + d) = −2,2581 kN, Einspannung Rz = +2,2581 kN.
  * Gegenprobe ueber einen anderen Rechenweg: statt der Feder eine
    Pendelstuetze mit EA/l = k, deren Fusspunkt starr gelagert und um d
    abgesenkt ist - dieselbe Verschiebung und Einspannkraft.

Aufruf:  python -m tests.test_zwang_feder
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E, I, L, D = 210e9, 1e-4, 6.0, 0.01
KB = 3 * E * I / L ** 3
K = 1.0e6


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _kragarm():
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    m = Model("Z")
    m.add_material(Material("S", E=E, nu=0.3))
    m.add_section(Section("R", A=1e-2, Iy=I, Iz=I, It=1e-4))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (L, 0, 0), 12)
    m.fix(ids[0], "all")
    return m, ids


def _rechnen(m):
    from statik3d import solver
    return solver.solve_static(m, workers=1)


def test_feder():
    u_soll = -K * D / (K + KB)
    m, ids = _kragarm()
    m.fix(ids[-1], [2], stiffness=[K])
    m.add_zwangsverformung(ids[-1], [2], [-D])
    r = _rechnen(m)
    u = float(r.u[ids[-1], 2])
    R_feder = float(r.reactions[ids[-1], 2])
    R_ein = float(r.reactions[ids[0], 2])
    check(f"Feder k = 1000 kN/m, Fußpunkt −10 mm: u = {u_soll * 1e3:.4f} mm",
          abs(u - u_soll) < 1e-6 * D, f"u = {u * 1e3:.4f} mm")
    check(f"Federreaktion −k (u − d) = {-K * (u_soll + D) / 1e3:.4f} kN, Einspannung = Gegenwert",
          abs(R_feder + K * (u_soll + D)) < 1e-3 and abs(R_ein + R_feder) < 1e-3,
          f"Feder {R_feder / 1e3:.4f} kN, Einspannung {R_ein / 1e3:.4f} kN")
    check("Feder mit Vorgabe: keine Meldung „unwirksam“", not r.info.get("zwang_ohne_lager"),
          str(r.info.get("zwang_ohne_lager")))

    # Gegenprobe: Pendelstuetze EA/l = K, Fuss starr, um d abgesenkt
    from statik3d.model import Section
    from statik3d import mesher
    m2, ids2 = _kragarm()
    l = 2.0
    m2.add_section(Section("P", A=K * l / E, Iy=1e-8, Iz=1e-8, It=1e-8))
    fuss = m2.add_node(L, 0.0, -l)
    n0 = len(m2.elements)
    m2.add_element("truss", [ids2[-1], fuss], "S", "P")
    m2.fix(fuss, "all")
    m2.add_zwangsverformung(fuss, [2], [-D])
    r2 = _rechnen(m2)
    u2 = float(r2.u[ids2[-1], 2])
    check("Gegenprobe Pendelstütze mit starrem, abgesenktem Fuß: gleiche Verschiebung und Einspannkraft",
          abs(u2 - u) < 1e-6 * D and abs(float(r2.reactions[ids2[0], 2]) - R_ein) < 1e-3,
          f"u = {u2 * 1e3:.4f} mm, Einspannung {float(r2.reactions[ids2[0], 2]) / 1e3:.4f} kN (Element {n0})")


def test_starr_unveraendert():
    m, ids = _kragarm()
    m.fix(ids[-1], [2])
    m.add_zwangsverformung(ids[-1], [2], [-D])
    r = _rechnen(m)
    check(f"starres Knotenlager: Rz Einspannung = 3 EI d / L³ = {KB * D / 1e3:.4f} kN (wie bisher)",
          abs(abs(float(r.reactions[ids[0], 2])) - KB * D) < 1e-3 and abs(r.u[ids[-1], 2] + D) < 1e-12)


def test_unwirksam_gemeldet():
    m, ids = _kragarm()
    m.support(ids[-1], [2], uz=dict(typ="free"))
    m.add_zwangsverformung(ids[-1], [2], [-D])
    r = _rechnen(m)
    w = " ".join(r.info.get("zwang_ohne_lager") or [])
    check("freier FHG mit Vorgabe: unwirksam und gemeldet", "unwirksam" in w and "Knoten 12 uz" in w, w)
    m, ids = _kragarm()
    m.support(ids[-1], [2], uz=dict(typ="rigid", failure="zug"))
    m.add_zwangsverformung(ids[-1], [2], [+D])
    r = _rechnen(m)
    w = " ".join(r.info.get("zwang_ohne_lager") or [])
    check("Lager mit Ausfall und Vorgabe: unwirksam und gemeldet", "unwirksam" in w and "Ausfall" in w, w)


def test_linienlager_ohne_falsche_meldung():
    m, ids = _kragarm()
    m.add_line_support(ids[-2:], uz=dict(typ="rigid"))
    m.add_zwangsverformung(ids[-1], [2], [-D])
    m.add_zwangsverformung(ids[-2], [2], [-D])
    r = _rechnen(m)
    check("starres Linienlager mit Vorgabe: wirkt (−10 mm), keine Meldung „ohne Lager“ (C1)",
          abs(r.u[ids[-1], 2] + D) < 1e-12 and not r.info.get("zwang_ohne_lager"),
          str(r.info.get("zwang_ohne_lager")))


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("zwang_feder")
    ja, ids = _kragarm()
    ja.fix(ids[-1], [2], stiffness=[K])
    ja.add_zwangsverformung(ids[-1], [2], [-D])
    nein, ids = _kragarm()
    nein.fix(ids[-1], [2])
    nein.add_zwangsverformung(ids[-1], [2], [-D])
    check("Verfahrenstabelle: „zwang_feder“ Fehlerkorrektur Stand 12, nur Zwang an einer Feder",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 12
          and rv.VERFAHRENSSTAND >= 12 and mk.betrifft(ja) and not mk.betrifft(nein))


def main():
    for t in (test_feder, test_starr_unveraendert, test_unwirksam_gemeldet, test_linienlager_ohne_falsche_meldung,
              test_verfahrenstabelle):
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
