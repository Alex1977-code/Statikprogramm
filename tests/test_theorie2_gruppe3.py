"""
Theorie II. Ordnung, Gruppe 3 der Befundliste (Befunde A7 bis A10 der
Pruefagenten, 09.11.2026). Jede Zahl gegen eine geschlossene Loesung und
einen zweiten Rechenweg.

A7  Geometrische Steifigkeit an Stabendgelenken: Kragstiel h = 5 m mit
    Pendelstuetze als Balken mit Gelenken (1 Element), Last P = 0,5 kst h:
    alpha_cr = kst h / P = 2,000 und u = H / (kst - P/h) (vorher 1,667 und
    +25 %); zweiter Weg: dieselbe Pendelstuetze als Fachwerkstab. Gezogener
    Gelenkstab T = 0,5 kst h: u = H / (kst + T/h); mit Druck im Stiel alpha_cr
    wie mit Fachwerkstab (vorher +37 %).
A8  Schnittgroessen: Einfeldtraeger 6 m, q = 5 kN/m, Druck 0,6 N_cr in einem
    Element: max My = q/k² (1/cos(kL/2) - 1) (Timoshenko), vorher -35 %;
    zweiter Weg 48 Elemente. Kragarm 5 m, Druck 0,6 N_cr, ein Element:
    Stabendmoment = Lagermoment (vorher +7,9 %), Vz(0) = Rz.
A9  alpha_cr mit einem Element je Knickhalbwelle: Hinweis „Stabteilung zu
    grob“ in der Theorie-II-Sammlung und der Zusammenfassung; mit vier
    Elementen keiner. Ein Balken aus einem Element, beidseits gelenkig, steht
    im Einzelknicken mit pi² E I / (L² N).
A10 Federgelenk mit k = 0 wirkt als Gelenk (Einfeldtraeger: Lagermoment 0
    statt 4,69 kNm); eine aeltere Datei bekommt es beim Oeffnen mit
    Ladehinweis.
Dazu: Verfahrenstabelle Stand 15-17; die Stabend-Verschiebungen fuer das
Feld (beam_th2) ueberstehen die Ergebnisdatei.

Aufruf:  python -m tests.test_theorie2_gruppe3
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
I = 1e-4
EI = E * I


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _modell():
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1.0, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    return m


def _kette(m, p1, p2, n, typ="beam"):
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    ids = []
    for k in range(n + 1):
        p = p1 + (p2 - p1) * k / n
        if m.nn:
            d = np.linalg.norm(m.nodes - p, axis=1)
            j = int(np.argmin(d))
            if d[j] < 1e-9:
                ids.append(j)
                continue
        ids.append(m.add_node(*p))
    els = [m.add_element(typ, [ids[k], ids[k + 1]], "ST", "Q") for k in range(n)]
    return ids, els


def _th2(m):
    from statik3d import solver
    m.load_cases["LF1"].theorie = "II"
    m.design.imperfektionen = False
    an = solver.solve_all(m, workers=1, design=False)
    return an, an.cases["LF1"]


H_, h = 1e3, 5.0
KST = 3 * EI / h ** 3


def _stiel_mit_pendel(pendel, P=0.0, T=0.0):
    m = _modell()
    ids, _ = _kette(m, (0, 0, 0), (0, 0, h), 8)
    pa, pe = _kette(m, (3, 0, 0), (3, 0, h), 1, typ=("truss" if pendel == "truss" else "beam"))
    m.add_element("truss", [ids[-1], pa[-1]], "ST", "Q")
    if pendel == "beam":
        m.add_hinge("GA", end=0, phiy="free", phiz="free")
        m.add_hinge("GE", end=1, phiy="free", phiz="free")
        m.apply_hinge(pe[0], "GA")
        m.apply_hinge(pe[-1], "GE")
        m.fix(pa[0], [5])
        m.fix(pa[-1], [5])
    m.fix(ids[0], "all")
    m.fix(pa[0], [0, 1, 2])
    m.fix(pa[-1], [1])
    m.fix(ids[-1], [1])
    m.load_node(pa[-1], Fz=-P + T)
    m.load_node(ids[-1], Fx=H_)
    return m, ids


def test_a7():
    P = 0.5 * KST * h
    m, ids = _stiel_mit_pendel("beam", P=P)
    _an, r = _th2(m)
    u, a = r.u[ids[-1], 0], r.info.get("alpha_cr")
    m2, ids2 = _stiel_mit_pendel("truss", P=P)
    _an2, r2 = _th2(m2)
    check("A7 Pendelstütze als Balken mit Gelenken: α_cr = kst h/P = 2,000 (wie Fachwerkstab)",
          abs(a - 2.0) < 1e-3 and abs(a - r2.info.get("alpha_cr")) < 1e-6, f"{a:.4f} / {r2.info.get('alpha_cr'):.4f}")
    soll = H_ / (KST - P / h)
    check("… u Kopf = H/(kst − P/h)", abs(u / soll - 1) < 1e-3 and abs(u - r2.u[ids2[-1], 0]) < 1e-9,
          f"{u * 1e3:.4f} mm, Hand {soll * 1e3:.4f} mm")
    T = 0.5 * KST * h
    m, ids = _stiel_mit_pendel("beam", T=T)
    _an, r = _th2(m)
    soll = H_ / (KST + T / h)
    check("A7 gezogener Gelenkstab: u Kopf = H/(kst + T/h)", abs(r.u[ids[-1], 0] / soll - 1) < 1e-3,
          f"{r.u[ids[-1], 0] * 1e3:.4f} mm, Hand {soll * 1e3:.4f} mm")


def test_a8():
    Ls, q = 6.0, 5e3
    Ncr = math.pi ** 2 * EI / Ls ** 2
    P = 0.6 * Ncr
    k = math.sqrt(P / EI)
    Mex = q / k ** 2 * (1 / math.cos(k * Ls / 2) - 1)
    werte = {}
    for n in (1, 48):
        m = _modell()
        ids, els = _kette(m, (0, 0, 0), (Ls, 0, 0), n)
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2])
        m.load_node(ids[-1], Fx=-P)
        for e in els:
            m.load_beam(e, qz=-q)
        _an, r = _th2(m)
        werte[n] = max(float(np.max(np.abs(r.stations(41)[e]["My"]))) for e in els)
    check("A8 Einfeldträger 0,6 N_cr, ein Element: max My = q/k² (1/cos(kL/2) − 1) auf 0,5 %",
          abs(werte[1] / Mex - 1) < 5e-3, f"{werte[1] / 1e3:.3f} kNm, Hand {Mex / 1e3:.3f} kNm")
    check("… zweiter Weg 48 Elemente auf 0,1 %", abs(werte[48] / Mex - 1) < 1e-3, f"{werte[48] / 1e3:.3f} kNm")
    L = 5.0
    P = 0.6 * math.pi ** 2 * EI / (4 * L ** 2)
    m = _modell()
    ids, els = _kette(m, (0, 0, 0), (L, 0, 0), 1)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fx=-P, Fz=-2e3)
    _an, r = _th2(m)
    Mr = abs(r.reactions[ids[0], 4])
    Mb = abs(r.beam_forces[els[0]]["My"][0])
    Vz = abs(r.beam_forces[els[0]]["Vz"][0])
    k = math.sqrt(P / EI)
    M0 = 2e3 * math.tan(k * L) / k
    check("A8 Kragarm 0,6 N_cr, ein Element: Stabendmoment = Lagermoment, Vz(0) = Rz = 2 kN",
          abs(Mb - Mr) < 1e-6 * Mr and abs(Vz - 2e3) < 1e-6 * 2e3,
          f"Stab {Mb / 1e3:.4f}, Lager {Mr / 1e3:.4f}, Hand {M0 / 1e3:.4f} kNm; Vz {Vz:.1f} N")


def test_a9():
    from statik3d import theorie2 as T2
    L, P = 6.0, 100e3
    for n in (1, 4, "geteilt"):
        m = _modell()
        m.sections["Q"].Iz = 2 * I
        # ohne interne Stabteilung (seit 12.11.2026 Vorgabe 10) - nur so
        # bleibt ein Element je Stab und der Hinweis hat etwas zu melden
        if n != "geteilt":
            m.netz.stabteilung = 1
        ids, els = _kette(m, (0, 0, 0), (L, 0, 0), 1 if n == "geteilt" else n)
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2])
        m.load_node(ids[-1], Fx=-P)
        for e in els:
            m.load_beam(e, qz=-1e3)
        an, _r = _th2(m)
        hin = [h_ for i in an.theorie2.kombinationen.values() for h_ in i.hinweise]
        grob = any(h_.startswith("α_cr: Stabteilung zu grob") for h_ in hin)
        if n == 1:
            check("A9 Euler-Fall 2 in einem Element: Hinweis „Stabteilung zu grob“ (Sammlung und Zusammenfassung)",
                  grob and "Stabteilung zu grob" in an.theorie2.summary(), str(hin)[:120])
        elif n == 4:
            check("… in vier Elementen: kein Hinweis", not grob, str(hin)[:120])
        else:
            ac = [i.alpha_cr for i in an.theorie2.kombinationen.values()]
            soll = math.pi ** 2 * EI / (L ** 2 * P)
            check("… ein Element mit interner Stabteilung (12.11.2026): kein Hinweis, α_cr = π² E I/(L² N) "
                  "auf 0,1 %", not grob and len(ac) == 1 and abs(ac[0] / soll - 1) < 1e-3,
                  f"{ac} / {soll:.4f}; {str(hin)[:80]}")
    # Balken aus einem Element, beidseits gelenkig: Einzelknicken pi² E I / (L² N)
    m = _modell()
    ids, els = _kette(m, (0, 0, 0), (L, 0, 0), 1)
    m.add_hinge("GA", end=0, phiy="free", phiz="free")
    m.add_hinge("GE", end=1, phiy="free", phiz="free")
    m.apply_hinge(els[0], "GA")
    m.apply_hinge(els[0], "GE")
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.fix(ids[-1], [1, 2, 3, 4, 5])
    m.load_node(ids[-1], Fx=-P)
    from statik3d import solver
    system = solver.StaticSystem(m)
    F, _feq, _q, _t = solver.case_loads(m, {"LF1": 1.0}, None)
    u = system.solve(F)
    ein = T2.einzelstab_knicken(m, u)
    soll = math.pi ** 2 * EI / (L ** 2 * P)
    check("A9/A7 Gelenkbalken aus einem Element: Einzelknicken α = π² E I/(L² N)",
          len(ein) == 1 and abs(ein[0]["alpha_cr"] / soll - 1) < 1e-9, f"{ein[0]['alpha_cr'] if ein else None} / {soll:.4f}")


def test_a10():
    from statik3d import solver
    from statik3d.model import Model
    L, F = 5.0, 5e3

    def bauen():
        m = _modell()
        ids, els = _kette(m, (0, 0, 0), (L, 0, 0), 2)
        m.fix(ids[0], [0, 1, 2, 3, 4, 5])
        m.fix(ids[-1], [1, 2])
        m.add_hinge("G0", end=0, phiy=0.0)
        m.apply_hinge(els[0], "G0")
        m.load_node(ids[1], Fz=-F)
        return m, ids, els
    m, ids, els = bauen()
    r = solver.solve_static(m)
    check("A10 Federgelenk k = 0 wirkt als Gelenk: Lagermoment 0 (vorher F L/4·… = 4,69 kNm)",
          abs(r.reactions[ids[0], 4]) < 1e-6 and 4 in m.elements[els[0]].hinges,
          f"{r.reactions[ids[0], 4]:.6f} Nm")
    # aeltere Datei: das Element ohne den Gelenk-FHG (so trug apply_hinge bis 09.11.2026 ein)
    d = m.to_dict()
    # eine Datei von vor dem 09.11.2026 hat die Kennung nicht (seit 11.11.2026 schreibt
    # to_dict sie, und from_dict zieht dann nichts nach - Befund 34)
    d.pop("federgelenk_null", None)
    for ed in d["elements"]:
        ed["hinges"] = []
    m2 = Model.from_dict(d)
    hinweis = [h_ for h_ in m2._ladehinweise if "Federsteifigkeit 0" in h_]
    check("… ältere Datei: beim Öffnen als Gelenk eingetragen, mit Ladehinweis",
          4 in m2.elements[els[0]].hinges and len(hinweis) == 1, str(hinweis))


def test_verfahren_und_datei():
    from statik3d import rechenverfahren as rv
    namen = {"theorie2_gelenke": 15, "theorie2_schnittgroessen": 16, "gelenk_feder_null": 17}
    ok = all(rv.merkmal(n) is not None and rv.merkmal(n).wechsel[-1].stand == s
             and rv.merkmal(n).wechsel[-1].art == rv.FEHLERKORREKTUR for n, s in namen.items())
    m, _ids = _stiel_mit_pendel("beam", P=1e3)
    m_t, _ = _stiel_mit_pendel("truss", P=1e3)
    check("Verfahrenstabelle: A7/A8/A10 Fehlerkorrektur Stand 15/16/17, Gelenkmerkmal nur mit Gelenk",
          ok and rv.VERFAHRENSSTAND >= 17 and rv.merkmal("theorie2_gelenke").betrifft(m)
          and not rv.merkmal("theorie2_gelenke").betrifft(m_t))
    from statik3d import ergebnisse
    Ls = 6.0
    m = _modell()
    ids, els = _kette(m, (0, 0, 0), (Ls, 0, 0), 1)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2])
    m.load_node(ids[-1], Fx=-0.5 * math.pi ** 2 * EI / Ls ** 2)
    m.load_beam(els[0], qz=-5e3)
    _an, r = _th2(m)
    vorher = r.stations(21)[els[0]]["My"].copy()
    r2 = ergebnisse._entpacken_results(ergebnisse._packen_results(r), m)
    nachher = r2.stations(21)[els[0]]["My"]
    check("Ergebnisdatei: die Feldmomente nach Theorie II. Ordnung bleiben nach dem Laden gleich",
          els[0] in r2.beam_th2 and np.allclose(vorher, nachher, rtol=0, atol=1e-9),
          f"max {np.abs(nachher).max() / 1e3:.3f} kNm")


def main():
    for t in (test_a7, test_a8, test_a9, test_a10, test_verfahren_und_datei):
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
