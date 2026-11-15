"""
Hinweis Biegedrillknicken, Runde k8 (Agent „bdk“), vom Anwender am
15.11.2026 freigegeben („2 ja“).

Die geometrische Steifigkeit K_G der Balken (Theorie II. Ordnung, alpha_cr,
Knicken) enthaelt nur die Normalkraft (elements/beam3d.kg_local_beam), nicht
das Momentenglied M·∫v'φ' dx. Das Biegedrillknicken fehlt dort, auch mit dem
siebten Freiheitsgrad (Woelbkrafttorsion: K_G wirkt nur auf die 12 Stabend-
FHG). Theorie III. Ordnung (korotational) enthaelt es. Kein Wert wird
geaendert; ein Stab mit Druck und Biegung, dessen Biegedrillknicken nicht
anderweitig erfasst ist, bekommt einen Hinweis - eine Zeile je Rechnung.

Anderweitig erfasst bzw. nicht maßgebend:

* Stab vom Typ I mit Nachweis nach EC3 und Haken „Biegedrillknicken“: der
  Ersatzstabnachweis 6.3.2/6.3.3 fuehrt chi_LT auch mit Schnittgroessen nach
  Theorie II. Ordnung (ec3/design.py check_member, ec3/stability.py);
* Hohlprofile (RHS, CHS) und Querschnitte ohne starke Achse (I_y = I_z):
  EN 1993-1-1 6.3.2.1(2) und 6.3.1.4(1);
* der gekoppelte Verzweigungsfaktor des Stabs (gabelgelagerter Stab,
  doppeltsymmetrisch, C1 = 1) liegt bei 25 oder hoeher - dann gilt
  N/N_cr <= 0,04 und M/M_cr <= 0,04, EN 1993-1-1 6.3.1.2(4) und 6.3.2.2(4) -
  oder weniger als 2 % unter dem ohne Momentenglied.

Zwei Wege fuer die Formel des gekoppelten Faktors: Kragstuetze HEA 200, 4 m,
P = 100 kN mit e = 0,3 m, Knick- und Kipplaenge 8 m: 1,98261 aus der
Formel, 1,9826059 aus der DGL (Schiessverfahren) und 1,9826093 aus einem
Energie-FE-Modell mit Richardson (D/ag_k8_starr1/weg_a_ode.py,
weg_b_energie.py).

Aufruf:  python -m tests.test_bdk_hinweis_k8
"""
import contextlib
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

KENNUNG = "enthalten kein Biegedrillknicken"
SCHLUSS = "Biegedrillknicken mit χ_LT nachweisen oder Theorie III. Ordnung rechnen."
TH2 = "Theorie II. Ordnung und α_cr enthalten kein Biegedrillknicken (Momentenglied der geometrischen Steifigkeit fehlt): "
KNICK = "Die Knickfaktoren enthalten kein Biegedrillknicken (Momentenglied der geometrischen Steifigkeit fehlt): "


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def _q():
    from statik3d.model import Section
    return Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05)


def _stuetzen(sec=None, N=200e3, M=40e3, theorie="II", anzahl=1, kombi=False, woelb=False):
    """``anzahl`` Kragstuetzen 4 m lotrecht in 4 Elementen, unten eingespannt,
    oben Druck N und Moment M um die starke Achse (exzentrische Last)."""
    from statik3d.model import Model, Material
    m = Model("K")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    sec = sec or _q()
    m.add_section(sec)
    m.design.imperfektionen = False
    for s in range(anzahl):
        ids = [m.add_node(3.0 * s, 0, 4.0 * j / 4) for j in range(5)]
        els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", sec.name) for j in range(4)]
        if woelb:
            for e in els:
                m.stab_woelb_setzen(e, True)
        m.add_member(f"S{s + 1}", els)
        m.fix(ids[0], "all")
        m.load_node(ids[-1], Fz=-N, My=M)
    if kombi:
        m.add_combination("K1", {m.active_case: 1.0}, "ULS")
        m.design.theorie2 = "auto"
    else:
        m.load_cases[m.active_case].theorie = theorie
    return m


def _ipe(lt=True, design=True):
    """Beispiel A aus (1): IPE 300, 6 m, Gabellager, N = 200 kN, M = 60 kNm."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("A")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-200e3)
    m.load_node(ids[0], My=60e3)
    m.load_node(ids[-1], My=-60e3)
    mem = m.add_member("T1", list(range(6)))
    mem.lt_check = lt
    mem.design = design
    m.design.imperfektionen = False
    m.load_cases[m.active_case].theorie = "II"
    return m


def _rechnen(m):
    from statik3d import solver
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, design=False, progress=lambda t, *a: zeilen.append(str(t)))
    return an, zeilen


def _h(zeilen):
    return [z for z in zeilen if KENNUNG in z]


def _infos(an):
    out = []
    for th in (an.theorie2, an.theorie3):
        out += list((getattr(th, "kombinationen", None) or {}).values())
    return out


def _kein(an, z):
    return (not _h(z) and not an.info.get("bdk_hinweis") and KENNUNG not in an.summary()
            and not any(KENNUNG in h for i in _infos(an) for h in i.hinweise))


# --------------------------------------------------------------------------
def test_formel():
    from statik3d import bdk_hinweis as bh
    # HEA 200 (Schneider): A 53,8 cm², Iy 3692, Iz 1336 cm⁴, It 20,98 cm⁴, ohne Iw
    E, G = 210e9, 210e9 / 2.6
    A, Iy, Iz, It, L, P, e = 53.8e-4, 3692e-8, 1336e-8, 20.98e-8, 8.0, 100e3, 0.3
    i0 = (Iy + Iz) / A
    Ncr_z = math.pi ** 2 * E * Iz / L ** 2
    Ncr_T = G * It / i0
    Mcr = math.sqrt(Ncr_z * Ncr_T * i0)
    lc, l0 = bh.verzweigungsfaktoren(P / Ncr_z, P / Ncr_T, P * e / Mcr)
    check("Formel: gekoppelter Faktor Kragstütze HEA 200, e = 0,3 m, 8 m: 1,98261 wie DGL 1,9826059 "
          "und Energie-FE 1,9826093", abs(lc - 1.98261) < 0.0005, f"{lc:.6f}")
    check("Formel: ohne Momentenglied 4,3266 (Euler schwach 432,66 kN)", abs(l0 - 4.32659) < 0.0005,
          f"{l0:.6f}")
    lc0, l00 = bh.verzweigungsfaktoren(0.5, 0.1, 0.0)
    check("Formel: ohne Moment gleich dem kleineren Einzelfaktor (2)", abs(lc0 - 2.0) < 1e-12
          and abs(l00 - 2.0) < 1e-12, f"{lc0} {l00}")


def test_theorie2():
    m = _stuetzen()
    an, z = _rechnen(m)
    soll = TH2 + "1 Stab mit Druck und Biegung: S1. " + SCHLUSS
    check("Th. II, Kragstütze Querschnitt Q (offen, nicht EC3-I): Hinweis im Protokoll",
          any(soll in x and x.startswith("Hinweis") for x in z), " | ".join(_h(z))[:240])
    check("Th. II: Hinweis in an.info und in der Zusammenfassung",
          an.info.get("bdk_hinweis") == [soll] and soll in an.summary(), str(an.info.get("bdk_hinweis"))[:200])
    info = _infos(an)[0] if _infos(an) else None
    check("Th. II: Hinweis beim Lastfall im Theoriekapitel (Th2Info.hinweise)",
          info is not None and soll in info.hinweise, str(info and info.hinweise)[:200])
    check("Th. II: Meldung ohne wissenschaftliche Schreibweise",
          not any("e+" in x or "e-0" in x for x in _h(z)), "")
    # fuenf Stuetzen: eine Zeile, Zahl und die ersten drei Namen
    m = _stuetzen(anzahl=5)
    an, z = _rechnen(m)
    soll5 = TH2 + "5 Stäbe mit Druck und Biegung, z. B. S1, S2, S3. " + SCHLUSS
    check("Th. II, fünf Stützen: genau eine Zeile im Protokoll mit Zahl 5 und S1, S2, S3",
          len(_h(z)) == 1 and soll5 in _h(z)[0] and an.info.get("bdk_hinweis") == [soll5],
          " | ".join(_h(z))[:240])


def test_mehrere_kombinationen():
    m = _stuetzen()
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {m.active_case: 1.35}, "ULS", theorie="II")
    m.load_cases[m.active_case].theorie = ""
    an, z = _rechnen(m)
    check("zwei Kombinationen nach Th. II: eine Zeile je Rechnung im Protokoll und in an.info",
          len(_h(z)) == 1 and len(an.info.get("bdk_hinweis") or []) == 1, " | ".join(_h(z))[:240])


def test_alpha_cr():
    # alpha_cr (auto) ueber 10: nur alpha_cr bestimmt
    m = _stuetzen(N=50e3, M=60e3, kombi=True)
    an, z = _rechnen(m)
    info = an.theorie2.kombinationen.get("K1") if an.theorie2 else None
    check("α_cr (auto, α_cr ≥ 10): nicht nach Th. II gerechnet",
          info is not None and not info.gerechnet and info.alpha_cr >= 10.0, f"{info and info.alpha_cr}")
    check("α_cr: Hinweis im Protokoll und im Theoriekapitel",
          len(_h(z)) == 1 and info is not None and any(KENNUNG in h for h in info.hinweise),
          " | ".join(_h(z))[:200])


def test_grundzustand_zwei_wege():
    """α_cr „auto“ bewertet aus u, Stablasten und Abschnittslasten, Theorie
    II. Ordnung aus dem Ergebnis nach Theorie I. Ordnung - gleiche
    Schnittgroessen, gleiche Staebe (mit Streckenlast quer: Feldmoment)."""
    from types import SimpleNamespace
    from statik3d import solver, bdk_hinweis as bh, assemble as asm
    m = _stuetzen(anzahl=3)
    for e in range(0, len(m.elements), 4):
        m.load_beam(e, qx=2e3)
    f = {m.active_case: 1.0}
    F, feq, q, _t = solver.case_loads(m, f, None)
    u = solver.StaticSystem(m).solve(F)
    with contextlib.redirect_stdout(io.StringIO()):
        res = solver.solve_static(m)
    d = 0.0
    for i in range(len(m.elements)):
        fl = asm.stab_endkraefte_linear(m, m.elements[i], u, feq.get(i))[0]
        ns = SimpleNamespace(beam_end={i: fl}, beam_q={i: q[i]} if i in q else {})
        a, b = solver.beam_station_forces(m, ns, i, 9), solver.beam_station_forces(m, res, i, 9)
        d = max(d, max(float(np.abs(a[k] - b[k]).max()) for k in ("N", "My", "Mz")))
    s1, s2 = bh.bdk_staebe(m, None, u=u, feq=feq, q=q), bh.bdk_staebe(m, None, res=res)
    check("Grundzustand aus u und aus dem Ergebnis: Schnittgrößen gleich, Stäbe gleich (S1, S2, S3)",
          d <= 1e-6 and s1 == s2 == ["S1", "S2", "S3"], f"Abweichung {d}, {s1} / {s2}")


def test_knicken():
    from statik3d import solver
    m = _stuetzen()
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_buckling(m, 2, lambda t, *a: zeilen.append(str(t)), case=m.active_case)
    soll = KNICK + "1 Stab mit Druck und Biegung: S1. " + SCHLUSS
    check("Knicken: Hinweis im Protokoll, in res.info und in der Zusammenfassung",
          any(soll in x for x in _h(zeilen)) and r.info.get("bdk_hinweis") == [soll] and soll in r.summary(),
          " | ".join(_h(zeilen))[:240])
    m = _stuetzen(M=0.0)
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_buckling(m, 2, lambda t, *a: zeilen.append(str(t)), case=m.active_case)
    check("Knicken, reiner Druckstab: kein Hinweis", not _h(zeilen) and not r.info.get("bdk_hinweis"),
          " | ".join(_h(zeilen))[:200])


def test_ersatzstab():
    an, z = _rechnen(_ipe())
    check("IPE 300 mit EC3-Nachweis und Biegedrillknicken (χ_LT im Ersatzstab): kein Hinweis",
          _kein(an, z), " | ".join(_h(z))[:200])
    an, z = _rechnen(_ipe(lt=False))
    check("IPE 300, Biegedrillknicken am Stab ausgeschaltet: Hinweis nennt T1",
          any("1 Stab mit Druck und Biegung: T1." in x for x in _h(z)), " | ".join(_h(z))[:200])
    an, z = _rechnen(_ipe(design=False))
    check("IPE 300 ohne Nachweis nach EC3: Hinweis nennt T1",
          any("1 Stab mit Druck und Biegung: T1." in x for x in _h(z)), " | ".join(_h(z))[:200])


def test_woelb():
    """Woelbkrafttorsion (7. FHG) erfasst das Biegedrillknicken nicht: K_G
    ohne Normalkraft ist null, auch unter Biegung."""
    from statik3d import solver, assemble as asm
    sec = _q()
    sec.Iw = 1e-7
    m = _stuetzen(sec=sec, N=0.0, M=40e3, woelb=True)
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_static(m)
    u = np.zeros(m.ndof)
    u[:m.nn * 6] = np.asarray(r.u, float).ravel()[:m.nn * 6]
    kg = asm.geometric_stiffness(m, u)
    check("Wölbkrafttorsion: K_G unter reiner Biegung (N = 0) ist null – kein Momentenglied",
          m.ndof > m.nn * 6 and float(abs(kg).max()) == 0.0, f"ndof {m.ndof}, max {float(abs(kg).max())}")
    m = _stuetzen(sec=sec, woelb=True)
    an, z = _rechnen(m)
    check("Wölbkrafttorsion am Stab: Hinweis bleibt (Th. II mit 7. FHG)",
          len(_h(z)) == 1 and "S1" in _h(z)[0], " | ".join(_h(z))[:200])


def test_schutz():
    from statik3d.model import Model, Material, Section
    from statik3d.profiles import make_section
    # Fachwerk: Dreieck aus Fachwerkstaeben, Last am First
    m = Model("F")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("R", A=1e-3, Iy=1e-6, Iz=1e-6, It=1e-6, zmax=0.05, ymax=0.05))
    a, b, c = m.add_node(0, 0, 0), m.add_node(4, 0, 0), m.add_node(2, 0, 2)
    for k, (p, q) in enumerate(((a, c), (c, b), (a, b))):
        m.add_member(f"F{k + 1}", [m.add_element("truss", [p, q], "ST", "R")])
    m.fix(a, [0, 1, 2]); m.fix(b, [1, 2]); m.fix(c, [1])
    m.load_node(c, Fz=-100e3, Fx=10e3)
    m.load_cases[m.active_case].theorie = "II"
    an, z = _rechnen(m)
    check("Schutz: Fachwerk (nur Fachwerkstäbe): kein Hinweis", _kein(an, z), " | ".join(_h(z))[:200])
    an, z = _rechnen(_stuetzen(M=0.0))
    check("Schutz: reiner Druckstab ohne Moment: kein Hinweis", _kein(an, z), " | ".join(_h(z))[:200])
    for p in ("RHS 200x100x8", "CHS 168.3x5"):
        an, z = _rechnen(_stuetzen(sec=make_section(p)))
        check(f"Schutz: Hohlprofil {p} (6.3.2.1(2)): kein Hinweis", _kein(an, z), " | ".join(_h(z))[:200])
    # Querschnitt ohne starke Achse
    an, z = _rechnen(_stuetzen(sec=Section("QQ", A=1e-2, Iy=4e-5, Iz=4e-5, It=1e-5, zmax=0.1, ymax=0.1)))
    check("Schutz: Querschnitt ohne starke Achse (I_y = I_z): kein Hinweis", _kein(an, z), " | ".join(_h(z))[:200])
    # kleine Last: gekoppelter Faktor ueber 25
    an, z = _rechnen(_stuetzen(N=20e3, M=5e3))
    check("Schutz: Druck und Biegung klein (gekoppelter Faktor über 25): kein Hinweis", _kein(an, z),
          " | ".join(_h(z))[:200])
    # Theorie I. Ordnung: keine Rechnung mit K_G
    an, z = _rechnen(_stuetzen(theorie="I"))
    check("Schutz: Theorie I. Ordnung: kein Hinweis", _kein(an, z), " | ".join(_h(z))[:200])


def test_theorie3():
    an, z = _rechnen(_stuetzen(theorie="III"))
    info = an.theorie3.kombinationen[list(an.theorie3.kombinationen)[0]] if an.theorie3 else None
    check("Th. III (korotational, enthält das Biegedrillknicken): kein Hinweis",
          info is not None and info.gerechnet and _kein(an, z), " | ".join(_h(z))[:200])


def main():
    for t in (test_formel, test_theorie2, test_mehrere_kombinationen, test_alpha_cr,
              test_grundzustand_zwei_wege, test_knicken,
              test_ersatzstab, test_woelb, test_schutz, test_theorie3):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
