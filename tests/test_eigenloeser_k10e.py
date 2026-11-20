"""
Runde k10e (16.11.2026), Fehlerliste Nr. 26: Schwingung, Knicken und alpha_cr
ohne rohen ARPACK-Abbruch.

Befund: Die Schwingungsberechnung brach mit „ARPACK error -9999“ oder
„ARPACK error -1“ ab (Sonde angriff1.py der k10c-Gegenpruefung, Ring-
Gegenpruefungen k10_ring_k10c_pruef3 und k10_ring_n2), auch bei rechenbaren
Modellen; das Knicken gab den ARPACK-Fehler roh weiter, und alpha_cr wurde
bei einem Abbruch „unendlich“ - check_theorie2 („auto“) nahm die Kombination
dann als „Theorie I. Ordnung ausreichend“.

Ursache der Abbrueche bei rechenbaren Modellen (in der Quelle belegt):
solve_modal verschiebt um sigma = -0,000001 mal mittlere Hauptdiagonale von
K durch mittlere von M. Das richtet sich nach den steifsten Freiheitsgraden,
nicht nach den gesuchten Eigenwerten: am Kragarm aus 1000 masselosen Staeben
mit 21 Punktmassen sigma = -47 400 000 000 gegen lambda_1 = 18 000. Die
Eigenwerte 1/(lambda - sigma) des Shift-Invert-Operators liegen dann fast
gleich, ARPACK baut keine Arnoldi-Zerlegung („error -9999“). Mit tausendfach
kleinerem sigma rechnet ARPACK dieselben Frequenzen.

Behebung: zweiter Loesungsweg nach jedem ARPACK-Abbruch - Modalanalyse mit
stufenweise kleinerer Verschiebung, dann dicht kondensiert; Knicken und
alpha_cr dicht ueber dem Traeger von K_g (sonst ARPACK mit mehr Lanczos-
Vektoren). Gemeldete Paare, deren Rayleigh-Quotient vom Eigenwert abweicht,
gelten als Abbruch. Erst wenn auch der zweite Weg nichts liefert, kommt ein
Klartext; singulaere Systeme behalten die Meldung der Statik.

Pruefkoerper und Sollwerte (je zwei Wege):
* Kragarm L = 3 m aus 1000 masselosen Staeben (E = 210 GPa, I = 8e-5 m^4,
  A = 0,01 m^2), 21 Punktmassen je 10 kg auf der aeusseren Haelfte.
  Weg 1: Nachgiebigkeit aus der Biegelinie x_i^2 (3 x_j - x_i) / (6 E I) und
  der Laengsdehnung min(x_i, x_j) / (E A), dicht geloest (Hand). Weg 2: das
  Programm selbst mit kleinem Modell (21 Staebe, dieselben Massen und Orte -
  die Knoten der Massen sind dieselben), das ARPACK ohne zweiten Weg rechnet.
* Knicken/alpha_cr: Kragstuetze 3 m aus 20 Staeben, 100 kN Druck; Hand
  pi^2 E I / (4 L^2) / 100 kN = 46,058154 und dasselbe Modell ohne
  erzwungenen Abbruch.

Aufruf:  python -m tests.test_eigenloeser_k10e
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

E, I, A, L = 210e9, 8e-5, 1e-2, 3.0
MASSE = 10.0
EULER = math.pi ** 2 * E * I / (4 * L ** 2) / 1e5


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


NE, NM = 1000, 21


def massenorte(ne=NE, nm=NM):
    """x der Punktmassen: Knoten ne, ne - d, ne - 2 d, ... (d = ne // (2 nm))."""
    return np.array([(ne - j * (ne // (2 * nm))) * L / ne for j in range(nm)])


def kragarm_massen(ne=NE, nm=NM, situation=False, grob=False):
    """Masseloser Kragarm aus ``ne`` gleich langen Staeben, ``nm`` Punktmassen.
    ``grob``: Knoten nur am Lager und an den Massen (21 Staebe, dieselben
    Orte) - Weg 2, kubische Balken geben die Nachgiebigkeit an den Knoten
    exakt. ``situation``: ein zusaetzlicher Stab von der Spitze zu einem
    festen Knoten, in der Situation „s“ abgeschaltet."""
    from statik3d.model import Model, Material, Section, Situation
    m = Model("eigen_k10e")
    m.add_material(Material("O", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    xm = massenorte(ne, nm)
    xs = np.concatenate([[0.0], np.sort(xm)]) if grob else np.arange(ne + 1) * L / ne
    kn = [m.add_node(float(x), 0, 0) for x in xs]
    for i in range(len(kn) - 1):
        m.add_element("beam", [kn[i], kn[i + 1]], "O", "Q")
    m.fix(kn[0], "all")
    for x in xm:
        m.add_punktmasse(kn[int(np.argmin(np.abs(xs - x)))], MASSE)
    ne = len(kn) - 1
    aktiv = None
    if situation:
        f = m.add_node(L, 1.0, 0)
        m.fix(f, "all")
        m.add_element("beam", [kn[-1], f], "O", "Q")
        m.situationen["s"] = Situation("s", "", [ne])
        aktiv = m.aktive_elemente("s")
    return m, aktiv


def hand_frequenzen(ne=NE, nm=NM):
    """Weg 1: Nachgiebigkeit aus Biegelinie und Laengsdehnung, dicht."""
    import scipy.linalg as sl
    x = massenorte(ne, nm)
    a, b = np.minimum.outer(x, x), np.maximum.outer(x, x)
    Fq = a * a * (3 * b - a) / (6 * E * I)
    Fl = a / (E * A)
    f = []
    for F in (Fq, Fq, Fl):
        mu = sl.eigvalsh(F * MASSE)
        f += list(np.sqrt(1.0 / mu[mu > 0]) / (2 * np.pi))
    return np.sort(np.asarray(f))


def test_kragarm_punktmassen():
    """Rechenbares Modell, an dem ARPACK um das alte sigma abbrach."""
    from statik3d import solver
    hand = hand_frequenzen()
    for sit in (False, True):
        titel = "in einer Situation" if sit else "ohne Situation"
        m, aktiv = kragarm_massen(situation=sit)
        try:
            r = still(solver.solve_modal, m, 6, workers=1, aktiv=aktiv)
        except Exception as ex:          # noqa: BLE001
            check(f"Kragarm 1000 Stäbe, 21 Punktmassen, {titel}: rechnet", False,
                  f"{type(ex).__name__}: {str(ex)[:200]}")
            continue
        f = np.asarray(r.freqs, float)
        check(f"Kragarm 1000 Stäbe, 21 Punktmassen, {titel}: rechnet, 6 Eigenformen", len(f) == 6,
              np.round(f, 5))
        # 0,0001 relativ: die Kondition des feinen Netzes (Hauptdiagonale ueber
        # 7 Zehnerpotenzen) laesst gemessen 0,00003 relativ zur Hand
        check(f"Kragarm, {titel}: f₁..f₆ gleich Hand (Biegelinie, dicht), relativ 0,0001",
              len(f) == 6 and np.allclose(f, hand[:6], rtol=1e-4),
              f"ist {np.round(f, 5)} soll {np.round(hand[:6], 5)}")
        hw = str(r.info.get("eigenloeser_hinweis", ""))
        check(f"Kragarm, {titel}: Hinweis „zweiter Lösungsweg“ im Ergebnis", "zweiten Lösungsweg" in hw, hw[:200])


def test_kragarm_grob_gleich():
    """Weg 2: derselbe Arm mit Knoten nur am Lager und an den Massen (21
    Staebe) rechnet ARPACK ohne zweiten Weg - gleiche Frequenzen wie die Hand
    und wie das feine Netz."""
    from statik3d import solver
    m, _a = kragarm_massen(grob=True)
    r = still(solver.solve_modal, m, 6, workers=1)
    f = np.asarray(r.freqs, float)
    hand = hand_frequenzen()
    check("Gegenprobe 21 Stäbe, Massen an denselben Orten: ARPACK ohne zweiten Weg, gleich Hand (relativ 0,000001)",
          r.info.get("eigenloeser") == "ARPACK" and np.allclose(f, hand[:6], rtol=1e-6),
          f"{r.info.get('eigenloeser')} ist {np.round(f, 5)} soll {np.round(hand[:6], 5)}")
    m2, _a = kragarm_massen()
    try:
        r2 = still(solver.solve_modal, m2, 6, workers=1)
        f2 = np.asarray(r2.freqs, float)
    except Exception as ex:              # noqa: BLE001
        f2 = np.zeros(0)
        check("Gegenprobe: feines Netz rechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
        return
    check("Gegenprobe: feines Netz (1000 Stäbe) gleich grobem (21 Stäbe), relativ 0,0001",
          len(f2) == 6 and np.allclose(f2, f, rtol=1e-4), f"fein {np.round(f2, 5)} grob {np.round(f, 5)}")


def _bricht(*a, **kw):
    from scipy.sparse.linalg import ArpackError
    raise ArpackError(-9999)


@contextlib.contextmanager
def arpack_gebrochen():
    """Jeder ARPACK-Aufruf bricht ab (solver.eigsh und scipy.sparse.linalg.eigsh)."""
    import scipy.sparse.linalg as spl
    from statik3d import solver
    alt_s, alt_l = solver.eigsh, spl.eigsh
    solver.eigsh = spl.eigsh = _bricht
    try:
        yield
    finally:
        solver.eigsh, spl.eigsh = alt_s, alt_l


def stahl_kragarm(ne=30, rho=7850.0, situation=False):
    from statik3d.model import Model, Material, Section, Situation
    m = Model("eigen_k10e_st")
    m.add_material(Material("ST", E=E, nu=0.3, rho=rho, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    kn = [m.add_node(i * L / ne, 0, 0) for i in range(ne + 1)]
    for i in range(ne):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(kn[-1], Fx=-1e5, case="LF1")
    if situation:
        f = m.add_node(L, 1.0, 0)
        m.fix(f, "all")
        m.add_element("beam", [kn[-1], f], "ST", "Q")
        m.situationen["s"] = Situation("s", "", [ne])
        m.load_cases["LF1"].situation = "s"
    return m


def test_modal_zweiter_weg_erzwungen():
    """ARPACK bricht immer ab: der dichte zweite Weg liefert dieselben
    Frequenzen wie ARPACK ohne Abbruch."""
    from statik3d import solver
    m = stahl_kragarm()
    ref = np.asarray(still(solver.solve_modal, m, 6, workers=1).freqs, float)
    with arpack_gebrochen():
        try:
            r = still(solver.solve_modal, m, 6, workers=1)
            f, txt = np.asarray(r.freqs, float), str(r.info.get("eigenloeser", ""))
        except Exception as ex:          # noqa: BLE001
            f, txt = np.zeros(0), f"{type(ex).__name__}: {str(ex)[:200]}"
    check("Modal, ARPACK bricht immer ab: dichter zweiter Weg gleich ARPACK (relativ 0,000001)",
          len(f) == 6 and np.allclose(f, ref, rtol=1e-6), f"{txt[:80]} ist {np.round(f, 4)} soll {np.round(ref, 4)}")


def test_knicken_zweiter_weg():
    """Knicken mit abbrechendem ARPACK: Faktoren wie ohne Abbruch und wie Hand,
    ohne und in einer Situation."""
    from statik3d import solver
    for sit in (False, True):
        titel = "in einer Situation" if sit else "ohne Situation"
        m = stahl_kragarm(ne=20, rho=0.0, situation=sit)
        ref = np.asarray(still(solver.solve_buckling, m, nmodes=4, case="LF1", workers=1).buckling_factors)
        with arpack_gebrochen():
            try:
                r = still(solver.solve_buckling, m, nmodes=4, case="LF1", workers=1)
                f, txt = np.asarray(r.buckling_factors, float), ""
            except Exception as ex:      # noqa: BLE001
                f, txt = np.zeros(0), f"{type(ex).__name__}: {str(ex)[:200]}"
        check(f"Knicken, ARPACK bricht ab, {titel}: Faktoren wie ohne Abbruch (relativ 0,000001)",
              len(f) == 4 and np.allclose(f, ref, rtol=1e-6), txt or f"ist {np.round(f, 5)} soll {np.round(ref, 5)}")
        check(f"Knicken, ARPACK bricht ab, {titel}: α₁ gleich π²EI/(4L²)/N (relativ 0,00001)",
              len(f) and abs(f[0] / EULER - 1) < 1e-5, txt or f"ist {f[0]:.6f} soll {EULER:.6f}")


def test_alpha_cr_zweiter_weg():
    """alpha_cr mit abbrechendem ARPACK: der zweite Weg rechnet; rechnet auch er
    nicht, heisst es nicht „unendlich“ ohne Kennzeichen."""
    from statik3d import solver, theorie2
    m = stahl_kragarm(ne=20, rho=0.0)
    sy = still(solver.StaticSystem, m, 1)
    u = sy.solve(solver.case_loads(m, {"LF1": 1.0}, None)[0])
    ref = theorie2.alpha_cr(m, sy, u)["alpha_cr"]
    with arpack_gebrochen():
        ac = still(theorie2.alpha_cr, m, sy, u)
    check("alpha_cr, ARPACK bricht ab: zweiter Weg gleich ohne Abbruch und gleich Hand (relativ 0,00001)",
          abs(ac["alpha_cr"] / ref - 1) < 1e-6 and abs(ac["alpha_cr"] / EULER - 1) < 1e-5 and not ac.get("fehler"),
          f"ist {ac['alpha_cr']} soll {ref} / {EULER:.6f} {ac.get('fehler', '')[:120]}")
    alt = getattr(solver, "KNICK_DICHT_MAX", None)
    with arpack_gebrochen():
        if alt is not None:
            solver.KNICK_DICHT_MAX = 0
        try:
            ac2 = still(theorie2.alpha_cr, m, sy, u)
        finally:
            if alt is not None:
                solver.KNICK_DICHT_MAX = alt
    check("alpha_cr, auch der zweite Weg ohne Ergebnis: Kennzeichen eigen_fehler und Klartext „α_cr nicht "
          "bestimmbar“", bool(ac2.get("eigen_fehler")) and str(ac2.get("fehler", "")).startswith("α_cr nicht bestimmbar")
          and "ARPACK error" not in str(ac2.get("fehler", "")).split("(")[0],
          str(ac2.get("fehler", ""))[:200])


def test_check_theorie2_nicht_ausreichend():
    """check_theorie2 „auto“: ohne bestimmbares alpha_cr rechnet die Kombination
    nach Theorie II. Ordnung, statt „Theorie I. Ordnung ausreichend“ zu sagen."""
    from statik3d import solver, theorie2
    m = stahl_kragarm(ne=20, rho=0.0)
    m.add_combination("LK1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"          # alpha_cr (Hand 46,06) liegt ueber der Grenze 10
    alt = getattr(solver, "KNICK_DICHT_MAX", None)
    try:
        with arpack_gebrochen():
            if alt is not None:
                solver.KNICK_DICHT_MAX = 0
            out = still(theorie2.check_theorie2, m, None)
    except Exception as ex:              # noqa: BLE001
        check("check_theorie2 „auto“ ohne alpha_cr: rechnet", False, f"{type(ex).__name__}: {str(ex)[:200]}")
        return
    finally:
        if alt is not None:
            solver.KNICK_DICHT_MAX = alt
    info = (getattr(out, "kombinationen", {}) or {}).get("LK1")
    hw = " | ".join(getattr(info, "hinweise", []) or [])
    check("check_theorie2 „auto“ ohne alpha_cr: Kombination nach Theorie II. Ordnung gerechnet, Hinweis „α_cr "
          "nicht bestimmbar“", info is not None and bool(getattr(info, "gerechnet", False))
          and "α_cr nicht bestimmbar" in hw, f"gerechnet {getattr(info, 'gerechnet', None)} {hw[:160]}")


def test_singulaer_situation():
    """Singulaeres Modell in einer Situation (Sonde angriff1, Fall 1): die
    Schwingung rechnet mit Hinweis auf die freien Knoten ohne Masse, das
    Knicken meldet den Klartext der Statik - kein ARPACK-Text."""
    from statik3d import solver
    from tests import test_singulaer_meldung_k10 as T
    m = T.fall1("situation")
    m.materials["ST"].rho = 7850.0
    try:
        r = still(solver.solve_modal, m, 3, workers=1, aktiv=m.aktive_elemente("s"))
        ok = len(r.freqs) == 3 and "Frei beweglich ohne Masse" in str(r.info.get("frei_hinweis", ""))
        txt = f"{np.round(r.freqs, 4)} {str(r.info.get('frei_hinweis', ''))[:100]}"
    except Exception as ex:              # noqa: BLE001
        ok, txt = False, f"{type(ex).__name__}: {str(ex)[:200]}"
    check("Fall 1 in der Situation: Schwingung rechnet, Hinweis „Frei beweglich ohne Masse“", ok, txt)
    m = T.fall1("situation")
    try:
        still(solver.solve_buckling, m, case="LF1", workers=1)
        ok, txt = False, "keine Meldung"
    except RuntimeError as ex:
        txt = str(ex)
        ok = txt.startswith("Gleichungssystem singulär") and "ARPACK" not in txt
    except Exception as ex:              # noqa: BLE001
        ok, txt = False, f"{type(ex).__name__}: {str(ex)[:200]}"
    check("Fall 1 in der Situation: Knicken meldet „Gleichungssystem singulär“ der Statik", ok, txt[:200])


def _kreisring(Rr, rho=0.0):
    """Kragarm 3 m aus 10 Staeben, an der Spitze 32 Speichen auf einen Ring
    vom Radius Rr, RBE3 der Ringknoten auf P (Bolzen 0,5 m); Last an P
    (wie p3.py der Ring-Gegenpruefung k10c)."""
    from statik3d.model import Model, Material, Section
    m = Model("ring_k10e")
    m.add_material(Material("ST", E=E, nu=0.3, rho=rho, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    kn = [m.add_node(i * 0.3, 0, 0) for i in range(11)]
    for i in range(10):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    b = kn[-1]
    rk = []
    for i in range(32):
        t = 2 * np.pi * i / 32 + 0.13
        k = m.add_node(L, Rr * np.cos(t), Rr * np.sin(t))
        m.add_element("beam", [b, k], "ST", "Q")
        rk.append(k)
    p = m.add_node(L + 0.5, 0.0, 0.0)
    m.add_element("beam", [b, p], "ST", "Q")
    m.add_starrkoerper(p, rk, "RBE3", None, name="Ring")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(p, case="LF1", Fx=-1e5, Fz=-1e3, Mx=500.0)
    return m


def test_kreisring_kurze_speichen():
    """Befund Nr. 25 (sehr kurze, steife Speichen) wird gesondert behoben; hier
    nur: kein roher ARPACK-Abbruch und kein still falsches Ergebnis - entweder
    innerhalb 1 % der Referenz (MPC-Elimination der Gegenpruefung k10c, p3.py)
    oder Klartext."""
    from statik3d import solver
    m = _kreisring(0.005, rho=7850.0)
    try:
        r = still(solver.solve_modal, m, 6, workers=1)
        f1 = float(r.freqs[0])
        ok = abs(f1 / 19.9842 - 1) < 0.01
        txt = f"f₁ {f1:.4f} Hz soll 19,9842; {str(r.info.get('eigenloeser_hinweis', ''))[:120]}"
    except RuntimeError as ex:
        txt = str(ex)
        ok = txt.startswith("Eigenschwingungen nicht berechenbar") and "ARPACK error" not in txt
    check("Kreisring, Speichen 5 mm, Schwingung: f₁ innerhalb 1 % der Referenz oder Klartext ohne ARPACK-Fehler",
          ok, txt[:220])
    m = _kreisring(0.002)
    try:
        r = still(solver.solve_buckling, m, nmodes=4, case="LF1", workers=1)
        a = np.asarray(r.buckling_factors, float)
        pos = a[np.isfinite(a) & (a > 0)]
        ok = bool(pos.size) and abs(pos.min() / 46.0602 - 1) < 0.01
        txt = f"Faktoren {np.round(a, 4)} soll 46,0602"
    except RuntimeError as ex:
        txt = str(ex)
        ok = txt.startswith("Verzweigungslastfaktoren nicht berechenbar") and "ARPACK error" not in txt.split("(")[0]
    check("Kreisring, Speichen 2 mm, Knicken: kleinster positiver Faktor innerhalb 1 % der Referenz oder Klartext",
          ok, txt[:220])


def test_merkmal():
    """Merkmal eigenpaare_geprueft: Stand 78, Fehlerkorrektur; betrifft den
    frei definierten RBE3 mit Knicken, nicht den Stab ohne RBE3."""
    from statik3d import rechenverfahren as rv, solver
    mk = rv.merkmal("eigenpaare_geprueft")
    check("Merkmal eigenpaare_geprueft: Stand 78, Fehlerkorrektur, VERFAHRENSSTAND >= 78 = höchster Stand",
          mk is not None and mk.wechsel[-1].stand == 78 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 78 and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m_ring, m_stab = _kreisring(0.02), stahl_kragarm(ne=20, rho=0.0)
    check("betrifft: Kragarm mit Kreisring-RBE3 ja, Stab ohne RBE3 nein",
          [mk.betrifft(m_ring), mk.betrifft(m_stab)] == [True, False])
    br = still(solver.solve_buckling, m_ring, nmodes=2, case="LF1", workers=1)
    br.name = "Knicken LF1"
    an = still(solver.solve_all, m_ring, workers=1, design=False)
    t_knick, t_statik = mk.im_ergebnis(m_ring, br), mk.im_ergebnis(m_ring, an)
    check("im Ergebnis: Knicken genannt, reine Statik nicht", "Knicken" in t_knick and t_statik == "",
          f"{t_knick!r} / {t_statik!r}")


def main():
    test_kragarm_punktmassen()
    test_kragarm_grob_gleich()
    test_modal_zweiter_weg_erzwungen()
    test_knicken_zweiter_weg()
    test_alpha_cr_zweiter_weg()
    test_check_theorie2_nicht_ausreichend()
    test_singulaer_situation()
    test_kreisring_kurze_speichen()
    test_merkmal()
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} bestanden")
    if n_ok != len(RESULTS):
        print("FEHLGESCHLAGEN:", [n for n, ok in RESULTS if not ok])
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
