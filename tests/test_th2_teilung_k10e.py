"""
Mindestteilung nach Theorie II. Ordnung, alpha_cr und Knicken (Runde k10e,
Nr. 29 der Fehlerliste, Verfahrensstand 76).

Befund: Seit Stand 74 teilt Theorie II. Ordnung gedrückte Stäbe mit
Ersatzimperfektionen intern mindestens in 10 Teile. Ohne Ersatzimperfektion
und mit der Stabteilung 1 der Netzeinstellungen rechnete ein Stab aus einem
Element weiter in diesem Element: IPE 300, 6 m, 300 kN Druck, Endmomente
6 kNm (als Knotenmomente oder als Versatz y 0,02 m) 54,2074 statt
54,2940 kNm (1,08 N/mm²); Versatz y 0,1 m, Federgelenk 2000 kNm/rad an
Gabellagern, qy 5 kN/m 107,4283 statt 107,2971 kNm; beidseits eingespannt
15,00 statt 16,66 kNm; in zwei Elementen 52,33 kNm; unter 600 kN Zug ein
unsinnig großes Feldmoment; alpha_cr und Knicken 21,7 % zu hoch,
beidseits eingespannt „Keine Normalkräfte“ statt des Knickfaktors.

Seither teilen Theorie II. Ordnung, alpha_cr („ein“ und „auto“) und
Knicken jeden Stab, an dem die Normalkraft zählt (Druck oder Zug),
mindestens in 10 Teile (stabteilung.th2_mindest), seriell und über
Arbeitsprozesse, mit den Teilergebnissen je Stab für den EC3-Nachweis.

Bezüge: geschlossene Lösungen der Biegelinie mit Längskraft (Timoshenko,
k² = N / (EI (1 ∓ N/(G A_s)))) und eine eigene ebene Rahmenrechnung mit
120 Elementen (Gegenprüfung k10d Runde 4, frame2d.py): 54,2940, 107,2971,
16,6569 und 7,9195 kNm.

Aufruf:  python -m tests.test_th2_teilung_k10e
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

E = 210e9
G = E / 2.6
L = 6.0
#: Grenze des Fehlerbegriffs ist 1 N/mm²; geprüft wird mit der Hälfte
GRENZE = 0.5e6


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _ipe():
    from statik3d.profiles import make_section
    return make_section("IPE 300")


def stab(e0=0.0, e1=0.0, n_el=1, teilung=1, N=200e3, qy=0.0, feder=None, lager="gabel",
         theorie="II", knotenmomente=0.0, imp=False):
    """IPE 300, S235, 6 m, Achse x, Gabellager (oder beidseits eingespannt),
    Druck N (negativ: Zug) am Ende, Versatz y e0/e1 an den Stabenden,
    Federgelenke um z an beiden Enden, Endmomente Mz ±M als Knotenmomente."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("K10e")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (L, 0, 0), n_el)
    ne = len(m.elements)
    for k, e in enumerate(m.elements):
        a = e0 + (e1 - e0) * k / ne
        b = e0 + (e1 - e0) * (k + 1) / ne
        if a or b:
            e.exzentrizitaet = [[0.0, a, 0.0], [0.0, b, 0.0]]
    if feder:
        m.elements[0].hinge_springs = [(5, feder)]
        m.elements[-1].hinge_springs = sorted(set(m.elements[-1].hinge_springs or []) | {(11, feder)})
    if lager == "einsp":
        m.fix(ids[0], [0, 1, 2, 3, 4, 5])
        m.fix(ids[-1], [1, 2, 3, 4, 5])
    else:
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N)
    if knotenmomente:
        m.load_node(ids[0], Mz=knotenmomente)
        m.load_node(ids[-1], Mz=-knotenmomente)
    if qy:
        for e in range(ne):
            m.load_beam(e, qy=qy, system="global")
    mem = m.add_member("T1", list(range(ne)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m, ids


def rechnen(m, workers=1):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=workers, design=False)
    r = an.combinations["K1"]
    mf = solver.member_forces(m, r, m.members["T1"], n=241)
    return an, r, mf


def mz_max(mf):
    return float(np.abs(mf["Mz"]).max())


def _wz():
    return float(_ipe().Wel_z)


def _k(N):
    """k der Biegelinie um z mit Schubverformung, N > 0 Druck, < 0 Zug."""
    s = _ipe()
    EI, GA = E * s.Iz, G * s.Asy
    return math.sqrt(abs(N) / (EI * (1.0 - N / GA))), GA


# --------------------------------------------------------------------------
# Druck: Endmomente, Versatz, zwei Elemente, Federgelenk, Einspannung
# --------------------------------------------------------------------------
def test_druck_endmomente():
    """300 kN Druck, Endmomente 6 kNm: M = M_0 / cos(kL/2) (Weg 1), Rahmen-
    rechnung 54,2940 kNm (Weg 2)."""
    k, _GA = _k(300e3)
    hand = 6e3 / math.cos(k * L / 2)
    check("Bezug Endmomente: geschlossen 54,2939 kNm wie die Rahmenrechnung 54,2940 kNm",
          abs(hand - 54294.0) < 1.0, f"{hand / 1e3:.4f} kNm")
    W = _wz()
    for tag, kw in (("Knotenmomente, ein Element", dict(knotenmomente=300e3 * 0.02)),
                    ("Versatz y 0,02 m, ein Element", dict(e0=0.02, e1=0.02)),
                    ("Knotenmomente, zwei Elemente", dict(knotenmomente=300e3 * 0.02, n_el=2)),
                    ("Versatz y 0,02 m, zwei Elemente", dict(e0=0.02, e1=0.02, n_el=2))):
        m, _ids = stab(N=300e3, **kw)
        _an, r, mf = rechnen(m)
        M = mz_max(mf)
        check(f"300 kN, Stabteilung 1, {tag}: Mz {hand / 1e3:.4f} kNm (unter 0,5 N/mm²)",
              abs(M - hand) / W <= GRENZE, f"{M / 1e3:.4f} kNm, {abs(M - hand) / W / 1e6:.3f} N/mm²")
        check(f"300 kN, Stabteilung 1, {tag}: intern mindestens 10 Teile je Stab",
              sum((r.info.get("stabteilung") or {}).values()) >= 10, str(r.info.get("stabteilung")))


def test_feder_versatz_q():
    """Versatz y 0,1 m, Federgelenke 2000 kNm/rad an Gabellagern, qy 5 kN/m,
    200 kN: Rahmenrechnung 107,2971 kNm (Weg 1), Programm mit 10 Elementen im
    Modell (Weg 2)."""
    W = _wz()
    BEZUG = 107297.1
    m, _ids = stab(0.1, 0.1, n_el=10, teilung=10, qy=5e3, feder=2e6)
    _an, _r, mf = rechnen(m)
    zehn = mz_max(mf)
    check("Federgelenk + Versatz + qy: zehn Elemente im Modell wie die Rahmenrechnung 107,2971 kNm",
          abs(zehn - BEZUG) / W <= GRENZE, f"{zehn / 1e3:.4f} kNm")
    m, _ids = stab(0.1, 0.1, n_el=1, teilung=1, qy=5e3, feder=2e6)
    _an, _r, mf = rechnen(m)
    M = mz_max(mf)
    check("Federgelenk + Versatz + qy, ein Element, Stabteilung 1: 107,2971 kNm (unter 0,5 N/mm²)",
          abs(M - BEZUG) / W <= GRENZE, f"{M / 1e3:.4f} kNm, {abs(M - BEZUG) / W / 1e6:.3f} N/mm²")


def test_einspannung():
    """Beidseits eingespannt, qy 5 kN/m, 200 kN: M_Rand = q'/k² (1 - u cot u),
    u = kL/2, q' = q/(1 - N/(G A_s)) (Weg 1), Rahmenrechnung 16,6569 kNm (Weg 2)."""
    W = _wz()
    k, GA = _k(200e3)
    u = k * L / 2
    hand = 5e3 / (1 - 200e3 / GA) / k ** 2 * (1 - u / math.tan(u))
    check("Bezug Einspannung: geschlossen wie die Rahmenrechnung 16,6569 kNm",
          abs(hand - 16656.9) < 1.0, f"{hand / 1e3:.4f} kNm")
    for n_el in (1, 2):
        m, _ids = stab(qy=5e3, lager="einsp", n_el=n_el)
        _an, _r, mf = rechnen(m)
        M = mz_max(mf)
        check(f"beidseits eingespannt, qy 5 kN/m, {n_el} Element(e), Stabteilung 1: Rand {hand / 1e3:.4f} kNm",
              abs(M - hand) / W <= GRENZE, f"{M / 1e3:.4f} kNm, {abs(M - hand) / W / 1e6:.3f} N/mm²")


# --------------------------------------------------------------------------
# Zug: nichts darf falsch werden
# --------------------------------------------------------------------------
def test_zug():
    """600 kN Zug, qy 5 kN/m, Gabellager: M = q'/k² (1 - 1/cosh(kL/2)),
    q' = q/(1 + N/(G A_s)) (Weg 1), Rahmenrechnung 7,9195 kNm (Weg 2).
    300 kN Zug mit Versatz y 0,02 m: Endmoment 6 kNm ist das größte."""
    W = _wz()
    k, GA = _k(-600e3)
    hand = 5e3 / (1 + 600e3 / GA) / k ** 2 * (1 - 1 / math.cosh(k * L / 2))
    check("Bezug Zug: geschlossen wie die Rahmenrechnung 7,9195 kNm", abs(hand - 7919.5) < 1.0,
          f"{hand / 1e3:.4f} kNm")
    for n_el in (1, 2):
        m, _ids = stab(N=-600e3, qy=5e3, n_el=n_el)
        _an, _r, mf = rechnen(m)
        M = mz_max(mf)
        check(f"600 kN Zug, qy 5 kN/m, {n_el} Element(e), Stabteilung 1: Mz {hand / 1e3:.4f} kNm",
              math.isfinite(M) and abs(M - hand) / W <= GRENZE, f"{M / 1e3:.4f} kNm")
    m, _ids = stab(0.02, 0.02, N=-300e3)
    _an, _r, mf = rechnen(m)
    M = mz_max(mf)
    check("300 kN Zug, Versatz y 0,02 m, ein Element, Stabteilung 1: Mz 6,0000 kNm am Rand",
          abs(M - 6e3) / W <= GRENZE, f"{M / 1e3:.4f} kNm")


def test_fachwerk():
    """Ein Fachwerkstab teilt sich nicht (keine Biegung): Dreieck aus zwei
    Balken und einem gedrückten Fachwerkstab, Stabteilung 1 und 10 gleich,
    die Normalkraft im Fachwerkstab aus dem Gleichgewicht."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import solver
    werte = {}
    for t in (1, 10):
        m = Model("FW")
        m.add_material(Material.steel("S235"))
        m.add_section(make_section("IPE 300"))
        shs = make_section("SHS 100x5")
        m.add_section(shs)
        a, b, c = m.add_node(0, 0, 0), m.add_node(4, 0, 0), m.add_node(2, 0, 3)
        e0 = m.add_element("beam", [a, c], "S235", "IPE 300")
        e1 = m.add_element("beam", [b, c], "S235", "IPE 300")
        e2 = m.add_element("truss", [a, b], "S235", shs.name)
        m.add_member("B1", [e0])
        m.add_member("B2", [e1])
        m.add_member("F1", [e2])
        m.fix(a, [0, 1, 2, 3, 4])
        m.fix(b, [1, 2, 3, 4])
        m.fix(c, [1, 3, 5])
        # Last nach aussen am Fuss b: der Fachwerkstab a-b wird gedrueckt
        m.load_node(b, Fx=-50e3)
        m.load_node(c, Fz=-100e3)
        m.design.imperfektionen = False
        m.netz.stabteilung = t
        m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="II")
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.combinations["K1"]
        werte[t] = (float(np.asarray(r.beam_end[e2], float)[0]), r.info.get("stabteilung") or {})
    n1, teile1 = werte[1]
    n10, _t10 = werte[10]
    check("Fachwerkstab gedrückt, Stabteilung 1: nicht geteilt, Balken geteilt",
          e2 not in teile1 and teile1.get(e0, 1) >= 10 and teile1.get(e1, 1) >= 10, str(teile1))
    check("Fachwerkstab gedrückt: Normalkraft bei Stabteilung 1 und 10 gleich (1 N)",
          abs(n1 - n10) <= 1.0, f"{n1:.2f} / {n10:.2f} N")


# --------------------------------------------------------------------------
# alpha_cr und Knicken
# --------------------------------------------------------------------------
def test_alpha_cr_knicken():
    """Gabellager, 200 kN: alpha_cr = N_E/(1 + N_E/(G A_s))/N (Weg 1),
    Programm mit Stabteilung 10 (Weg 2). Beidseits eingespannt: die kleinste
    Verzweigung ist das Drillknicken ohne Wölbkrafttorsion,
    G I_t A/(I_y + I_z)/N = 4,8312 (Weg 1), Stabteilung 10 (Weg 2)."""
    from statik3d import solver
    s = _ipe()
    NE = math.pi ** 2 * E * s.Iz / L ** 2
    hand = NE / (1 + NE / (G * s.Asy)) / 200e3
    drill = G * s.It * s.A / (s.Iy + s.Iz) / 200e3

    def werte(n_el, t, lager):
        m, _ids = stab(n_el=n_el, teilung=t, qy=1e3, lager=lager)
        an, _r, _mf = rechnen(m)
        ein = an.theorie2.kombinationen["K1"].alpha_cr
        m, _ids = stab(n_el=n_el, teilung=t, qy=1e3, lager=lager, theorie="")
        m.design.theorie2 = "auto"
        an = _still(solver.solve_all, m, workers=1, design=False)
        auto = an.theorie2.kombinationen["K1"].alpha_cr
        m, _ids = stab(n_el=n_el, teilung=t, qy=1e3, lager=lager)
        try:
            r = _still(solver.solve_buckling, m, nmodes=1, combination="K1", workers=1)
            kn = min(x for x in r.buckling_factors if x > 0)
        except Exception as ex:          # noqa: BLE001
            kn = f"{type(ex).__name__}: {ex}"
        return ein, auto, kn
    z_g = werte(1, 10, "gabel")
    check("Bezug Gabellager: Stabteilung 10 wie geschlossen (0,1 %)",
          all(abs(v / hand - 1) < 1e-3 for v in z_g), f"{z_g} / {hand:.4f}")
    for n_el in (1, 2):
        ein, auto, kn = werte(n_el, 1, "gabel")
        for tag, v in (("Theorie II ein", ein), ("auto", auto), ("Knicken", kn)):
            check(f"Gabellager, {n_el} Element(e), Stabteilung 1: alpha_cr {tag} = {hand:.4f} (0,1 %)",
                  isinstance(v, float) and abs(v / hand - 1) < 1e-3, f"{v}")
    z_e = werte(1, 10, "einsp")
    check("Bezug eingespannt: Stabteilung 10 wie Drillknicken geschlossen 4,8312 (0,1 %)",
          all(isinstance(v, float) and abs(v / drill - 1) < 1e-3 for v in z_e), f"{z_e} / {drill:.4f}")
    ein, auto, kn = werte(1, 1, "einsp")
    for tag, v in (("Theorie II ein", ein), ("auto", auto), ("Knicken", kn)):
        check(f"beidseits eingespannt, ein Element, Stabteilung 1: {tag} = {drill:.4f} (keine Abweisung)",
              isinstance(v, float) and abs(v / drill - 1) < 1e-3, f"{v}")


# --------------------------------------------------------------------------
# Arbeitsprozesse und EC3-Nachweis mit den Teilergebnissen
# --------------------------------------------------------------------------
def test_arbeitsprozesse():
    """Rechnung mit zwei Arbeitern wie seriell; EC3-Nachweis über
    Arbeitsprozesse wie seriell, mit den Teilergebnissen (beam_teile) und
    Mz_Ed nach der geschlossenen Lösung."""
    from statik3d.ec3.design import check_members
    W = _wz()
    k, _GA = _k(300e3)
    hand = 6e3 / math.cos(k * L / 2)
    m, _ids = stab(N=300e3, knotenmomente=6e3)
    an1, r1, mf1 = rechnen(m, workers=1)
    m2, _ids = stab(N=300e3, knotenmomente=6e3)
    an2, r2, mf2 = rechnen(m2, workers=2)
    check("Stabteilung 1: Rechnung mit zwei Arbeitern bitgleich mit seriell (Mz im Feld, Verschiebungen)",
          np.array_equal(np.asarray(mf1["Mz"]), np.asarray(mf2["Mz"]))
          and np.array_equal(np.asarray(r1.u), np.asarray(r2.u)),
          f"{mz_max(mf1) / 1e3:.6f} / {mz_max(mf2) / 1e3:.6f} kNm")
    check("Stabteilung 1: Teilergebnisse je Stab im Ergebnis (beam_teile, 10 Teile)",
          len((getattr(r1, "beam_teile", None) or {}).get(0, {}).get("end", [])) == 10
          and len((getattr(r2, "beam_teile", None) or {}).get(0, {}).get("end", [])) == 10,
          str({i: len(t.get("end", [])) for i, t in (getattr(r1, "beam_teile", None) or {}).items()}))
    a = _still(check_members, m, an1, use_jobs=False)
    b = _still(check_members, m, an1, use_jobs=True, workers=2)
    sa, sb = a.members["T1"].stability[0], b.members["T1"].stability[0]
    check("EC3 über Arbeitsprozesse: Ausnutzung und Mz_Ed bitgleich mit seriell",
          a.util_max == b.util_max and sa.get("Mz_Ed") == sb.get("Mz_Ed"),
          f"{a.util_max:.6f} / {b.util_max:.6f}; {sa.get('Mz_Ed')} / {sb.get('Mz_Ed')}")
    check(f"EC3 über Arbeitsprozesse: Mz_Ed = {hand / 1e3:.4f} kNm (unter 0,5 N/mm²)",
          abs(abs(float(sb.get("Mz_Ed", 0.0))) - hand) / W <= GRENZE, f"{sb.get('Mz_Ed')}")


# --------------------------------------------------------------------------
# Hinweis Last in Stabrichtung: gezählt wird, was gerechnet wird
# --------------------------------------------------------------------------
def test_laengslast_hinweis():
    """Stütze mit Eigengewicht (Last in Stabrichtung), ein Element,
    Stabteilung 1, Theorie II: intern in 10 Teilen - kein Hinweis „in
    1 Element geteilt“ mehr."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver
    m = Model("S")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=7850.0, fy=355e6))
    m.add_section(Section("Q", A=0.1, Iy=1e-4, Iz=1e-4, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    a, b = m.add_node(0, 0, 0), m.add_node(0, 0, 5.0)
    e = m.add_element("beam", [a, b], "ST", "Q")
    m.add_member("S1", [e])
    m.fix(a, [0, 1, 2, 5])
    m.fix(b, [0, 1])
    m.load_beam(e, qx=2e3)
    m.set_gravity(-9.81)
    m.load_cases[m.active_case].theorie = "II"
    m.netz.stabteilung = 1
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, design=False, progress=lambda t, *x: zeilen.append(str(t)))
    h = [z for z in zeilen if "trägt Last in Stabrichtung" in z]
    r = an.cases[m.active_case]
    check("Stütze mit Eigengewicht, Stabteilung 1, Theorie II: intern 10 Teile, kein Hinweis „1 Element“",
          not h and (r.info.get("stabteilung") or {}).get(0) == 10, f"{h[:1]} {r.info.get('stabteilung')}")


# --------------------------------------------------------------------------
# Vorgabe unverändert, Merkmal
# --------------------------------------------------------------------------
def test_vorgabe():
    from statik3d.stabteilung import th2_mindest
    m, _ids = stab(teilung=10)
    check("Stabteilung 10: keine zusätzliche Mindestteilung (th2_mindest leer)",
          th2_mindest(m, {0: -200e3}) == {}, "")
    m, _ids = stab(teilung=1)
    check("Stabteilung 1: gedrückter und gezogener Stab mindestens 10 Teile, ohne Normalkraft nicht",
          th2_mindest(m, {0: -200e3}) == {0: 10} and th2_mindest(m, {0: 200e3}) == {0: 10}
          and th2_mindest(m, {0: 0.0}) == {}, "")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("th2_mindestteilung")
    # Bis zur Zusammenfuehrung k10e (16.11.2026) stand hier VERFAHRENSSTAND == 76;
    # gemeint ist wie in tests/test_gleitweg.py: Stand >= 76 und der hoechste der Tabelle
    check("Merkmal th2_mindestteilung: Stand 76, Fehlerkorrektur, 16.11.2026, VERFAHRENSSTAND >= 76 "
          "(höchster Stand der Tabelle)",
          mk is not None and mk.wechsel[-1].stand == 76 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].datum == "16.11.2026" and rv.VERFAHRENSSTAND >= 76
          and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m1, _ids = stab(teilung=1)
    m10, _ids = stab(teilung=10)
    check("Merkmal betrifft Stabteilung 1, nicht Stabteilung 10",
          mk.betrifft(m1) and not mk.betrifft(m10), "")
    an, _r, _mf = rechnen(m1)
    check("Merkmal im Ergebnis: Theorie II. Ordnung genannt", bool(mk.im_ergebnis(m1, an)),
          mk.im_ergebnis(m1, an))


def main():
    for t in (test_druck_endmomente, test_feder_versatz_q, test_einspannung, test_zug, test_fachwerk,
              test_alpha_cr_knicken, test_arbeitsprozesse, test_laengslast_hinweis, test_vorgabe,
              test_merkmal):
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
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
