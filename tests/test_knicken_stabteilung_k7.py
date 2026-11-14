"""
Behebung vom 14.11.2026, Runde k7 (Agent „knick“), vom Anwender freigegeben
(„ja, beide einverstanden“): das Knicken (solver.solve_buckling, K + λ K_G)
rechnet am intern geteilten Modell wie Theorie II. Ordnung und α_cr „auto“
(statik3d.stabteilung: jeder Stab mindestens netz.stabteilung Teile, nur wo
|N_I| >= 1e-3 N_E des Elements). Bis dahin knickte ein Stab aus einem
Element mit seiner kubischen Biegelinie: Saeule 5 m mit Last in Stabrichtung
auf dem unteren Meter 16,80 statt 5,81 (α_cr „auto“) bzw. 5,61 (DGL), eine
beidseits eingespannte Stuetze aus einem Element gar nicht („Keine
Normalkräfte vorhanden“).

Eigenformen und Ergebnis gehen auf die Knoten und Elemente des Modells
zurueck (stabteilung.zurueck); die Zwischenknoten stehen nicht als
Modellknoten im Ergebnis, ihre Eigenform liegt in res.buckling_modes_teile
(fuer die modale Energie der Knicklaengen).

Sollwerte und zwei Wege:
* Euler π² EI / (β L)² geschlossen (β = 0,6992 aus tan kL = kL) gegen das
  Programm an einer Stuetze aus einem Element; Abweichung unter 0,5 %.
* Zweistielrahmen aus je einem Element gegen dasselbe Modell, von Hand in
  zehn Elemente je Stab geteilt (Faktoren, Eigenform an den Modellknoten,
  Knicklaengen).
* Saeule mit Last in Stabrichtung gegen die finite-Differenzen-Loesung der
  DGL (wie D/ag_k6_theorie/referenz.py; Gegenprobe Ritz mit Sinusreihe in
  D/ag_k7_knick/sollwerte.py: gleichmaessig 2,59962 / 2,59959).
* Knicken gegen α_cr „auto“ (check_theorie2) fuer dasselbe Modell, auch am
  Zugband-Kurzstab ohne Sollkraft (Pruefagent Runde k5: 4369,9 gegen 3289,6).

Aufruf:  python -m tests.test_knicken_stabteilung_k7
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


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


E = 210e9
IZ = 1e-4                    # schwache Achse
IY = 2e-4
L = 5.0
P = 1e6                      # Last am Kopf [N]


def _stuetze(fuss, kopf, n=1, teilung=10, stab=True):
    """Stuetze 5 m in n Elementen, Last P am Kopf."""
    from statik3d.model import Model, Material, Section
    m = Model("S")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=IY, Iz=IZ, It=2e-4, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    ids = [m.add_node(0, 0, L * j / n) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    if stab:
        m.add_member("S1", els)
    m.fix(ids[0], fuss)
    if kopf:
        m.fix(ids[-1], kopf)
    m.load_node(ids[-1], Fz=-P)
    m.netz.stabteilung = teilung
    return m


def _knick(m, nmodes=3, **kw):
    from statik3d import solver
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_buckling(m, nmodes, **kw)
    f = np.asarray(r.buckling_factors, float)
    return float(f[f > 0].min()), r


def _beta_eg():
    lo, hi = 4.0, 4.6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if math.tan(mid) - mid > 0:
            hi = mid
        else:
            lo = mid
    return math.pi / lo


EULER = (("gelenkig-gelenkig", [0, 1, 2, 5], [0, 1], 1.0),
         ("Kragstütze", "all", [], 2.0),
         ("beidseits eingespannt", "all", [0, 1, 3, 4, 5], 0.5),
         ("eingespannt-gelenkig", "all", [0, 1], None))


def test_euler():
    for text, fuss, kopf, beta in EULER:
        beta = beta or _beta_eg()
        soll = math.pi ** 2 * E * IZ / (beta * L) ** 2 / P
        try:
            lam, r = _knick(_stuetze(fuss, kopf))
        except Exception as ex:          # noqa: BLE001
            check(f"Euler {text}, ein Element: λ = π²EI/(βL)²/P = {soll:.4f} (0,5 %)", False, f"Ausnahme: {ex}")
            continue
        check(f"Euler {text}, ein Element: λ = π²EI/(βL)²/P = {soll:.4f} (0,5 %)",
              abs(lam / soll - 1) < 5e-3, f"{lam:.4f} ({(lam / soll - 1) * 100:+.3f} %)")
        bm = np.asarray(r.buckling_modes)
        check(f"Euler {text}: Eigenform an den 2 Modellknoten, Teilung im Ergebnis vermerkt",
              bm.ndim == 3 and bm.shape[1:] == (2, 6) and r.info.get("stabteilung") == {0: 10}
              and len(r.u) == 2,
              f"Form {bm.shape}, stabteilung {r.info.get('stabteilung')}")


def test_knicklaengen():
    from statik3d.ec3.knicklaengen import knicklaengen_aus_eigenform
    for text, fuss, kopf, beta in (EULER[0], EULER[2]):
        try:
            _lam, r = _knick(_stuetze(fuss, kopf))
            k = knicklaengen_aus_eigenform(_stuetze(fuss, kopf), r).staebe["S1"]
        except Exception as ex:          # noqa: BLE001
            check(f"Knicklänge {text}, ein Element: β_z = {beta:g} (0,3 %), beteiligt", False, f"Ausnahme: {ex}")
            continue
        check(f"Knicklänge {text}, ein Element: β_z = {beta:g} (0,3 %), beteiligt",
              k.achse == "z" and k.beta_z is not None and abs(k.beta_z / beta - 1) < 3e-3
              and k.beteiligt and k.beteiligung > 0.99,
              f"Achse {k.achse} β_z {k.beta_z} Beteiligung {k.beteiligung:.3f}")


# --------------------------------------------------------------------------
# Zweistielrahmen: ein Element je Stab gegen von Hand zehn
# --------------------------------------------------------------------------
H_R, B_R = 4.0, 6.0


def _rahmen(n):
    """Stiele 4 m, Riegel 6 m, Fuesse eingespannt; Kopflasten 1000 kN lotrecht
    und 20 kN waagerecht links (Riegel mit Normalkraft). Die Eckknoten sind
    0..3 (Fuss links, Kopf links, Kopf rechts, Fuss rechts), Zwischenknoten
    danach."""
    from statik3d.model import Model, Material, Section
    m = Model("R")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=IY, Iz=IZ, It=2e-4, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    ecken = [m.add_node(*p) for p in ((0, 0, 0), (0, 0, H_R), (B_R, 0, H_R), (B_R, 0, 0))]

    def stab(name, a, b):
        X0, X1 = np.asarray(m.nodes[a], float), np.asarray(m.nodes[b], float)
        ids = [a] + [m.add_node(*(X0 + (X1 - X0) * k / n)) for k in range(1, n)] + [b]
        m.add_member(name, [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(n)])

    stab("SL", ecken[0], ecken[1])
    stab("RI", ecken[1], ecken[2])
    stab("SR", ecken[3], ecken[2])
    m.fix(ecken[0], "all")
    m.fix(ecken[3], "all")
    m.load_node(ecken[1], Fz=-1000e3, Fx=20e3)
    m.load_node(ecken[2], Fz=-1000e3)
    return m


def test_rahmen():
    from statik3d.ec3.knicklaengen import knicklaengen_aus_eigenform
    try:
        _l1, r1 = _knick(_rahmen(1), 3)
        _l2, r2 = _knick(_rahmen(10), 3)
    except Exception as ex:          # noqa: BLE001
        check("Rahmen: Faktoren wie von Hand in zehn Elemente je Stab geteilt (1e-8)", False, f"Ausnahme: {ex}")
        return
    f1, f2 = np.asarray(r1.buckling_factors, float), np.asarray(r2.buckling_factors, float)
    check("Rahmen: Faktoren wie von Hand in zehn Elemente je Stab geteilt (1e-8)",
          np.allclose(f1, f2, rtol=1e-8, atol=0), f"{np.round(f1, 5)} / {np.round(f2, 5)}")
    v1 = np.asarray(r1.buckling_modes[0], float)
    v2 = np.asarray(r2.buckling_modes[0], float)[:4]
    s = 1.0 if float(np.sum(v1 * v2)) >= 0 else -1.0
    check("Rahmen: Eigenform 1 an den vier Eckknoten wie von Hand geteilt (1e-6)",
          v1.shape == (4, 6) and np.allclose(v1, s * v2, atol=1e-6),
          f"max Abweichung {np.abs(v1 - s * v2).max():.2e}")
    k1 = knicklaengen_aus_eigenform(_rahmen(1), r1)
    k2 = knicklaengen_aus_eigenform(_rahmen(10), r2)
    gleich = all(abs(k1.staebe[n].beteiligung - k2.staebe[n].beteiligung) < 1e-6
                 and k1.staebe[n].achse == k2.staebe[n].achse
                 and ((k1.staebe[n].beta_z is None) == (k2.staebe[n].beta_z is None))
                 and (k1.staebe[n].beta_z is None or abs(k1.staebe[n].beta_z / k2.staebe[n].beta_z - 1) < 1e-8)
                 for n in ("SL", "SR", "RI"))
    check("Rahmen: Knicklängen und Beteiligung je Stab wie von Hand geteilt", gleich,
          "; ".join(f"{n} {k1.staebe[n].achse} β {k1.staebe[n].beta_z}/{k2.staebe[n].beta_z} "
                    f"{k1.staebe[n].beteiligung:.4f}/{k2.staebe[n].beteiligung:.4f}" for n in ("SL", "SR", "RI")))


# --------------------------------------------------------------------------
# Saeule mit Last in Stabrichtung gegen die DGL
# --------------------------------------------------------------------------
def _qfun(art, x):
    return np.full_like(x, 1.2e6) if art == "gleich" else np.where(x <= 1.0, 6e6, 0.0)


def _fd(art, n=600):
    """Kleinster Verzweigungsfaktor der DGL (EI w'')'' + (P w')' = 0,
    gelenkig/gelenkig, P(x) Druck aus der Last in Stabrichtung (oben frei)."""
    from scipy import linalg, sparse
    xf = np.linspace(0, L, 200001)
    qf = _qfun(art, xf)
    cum = np.concatenate([[0], np.cumsum(0.5 * (qf[1:] + qf[:-1]) * np.diff(xf))])
    Pd = lambda x: np.interp(x, xf, cum[-1] - cum)          # noqa: E731
    h = L / n
    x = np.linspace(0, L, n + 1)
    k = n - 1
    D2 = sparse.diags([np.ones(k - 1), -2 * np.ones(k), np.ones(k - 1)], [-1, 0, 1]) / h ** 2
    pp, pm = Pd(x[1:-1] + h / 2), Pd(x[1:-1] - h / 2)
    G = sparse.diags([pm[1:], -(pp + pm), pp[:-1]], [-1, 0, 1]).toarray() / h ** 2
    mu = linalg.eigvals(np.linalg.solve((E * IZ * (D2 @ D2)).toarray(), -G))
    mu = np.real(mu[np.abs(np.imag(mu)) < 1e-9])
    return 1.0 / mu.max()


def _saeule(art, teilung=10, n=1):
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=IY, Iz=IZ, It=2e-4, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    ids = [m.add_node(0, 0, L * j / n) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    m.add_member("S1", els)
    m.fix(ids[0], [0, 1, 2, 5])
    m.fix(ids[-1], [0, 1])
    for j, e in enumerate(els):
        z0, z1 = L * j / n, L * (j + 1) / n
        if art == "gleich":
            m.load_beam(e, qz=-1.2e6)
        elif z0 < 1.0:
            m.load_beam(e, qz=-6e6, a=0.0, b=min(1.0, z1) - z0)
    m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m


def test_laengslast():
    from statik3d import theorie2
    for art, teilung, tol in (("gleich", 10, 5e-3), ("teil_unten", 40, 5e-3)):
        soll = _fd(art)
        try:
            lam, _r = _knick(_saeule(art, teilung), case=None)
        except Exception as ex:          # noqa: BLE001
            check(f"Längslast {art}, ein Element, Stabteilung {teilung}: λ wie DGL {soll:.4f} "
                  f"({tol * 100:g} %)", False, f"Ausnahme: {ex}")
            continue
        check(f"Längslast {art}, ein Element, Stabteilung {teilung}: λ wie DGL {soll:.4f} ({tol * 100:g} %)",
              abs(lam / soll - 1) < tol, f"{lam:.4f} ({(lam / soll - 1) * 100:+.3f} %)")
    # Teillast unten mit der Vorgabe 10: wie α_cr „auto“ (beide am geteilten Modell)
    lam, _r = _knick(_saeule("teil_unten"), case=None)
    with contextlib.redirect_stdout(io.StringIO()):
        a = theorie2.check_theorie2(_saeule("teil_unten"), None, ["K1"]).kombinationen["K1"].alpha_cr
    check("Längslast Teillast unten, ein Element, Vorgabe 10: Knicken = α_cr „auto“ (1e-9), "
          "nicht mehr 16,80", abs(lam / a - 1) < 1e-9 and lam < 6.0, f"Knicken {lam:.4f}, auto {a:.4f}")
    lam10, _r = _knick(_saeule("teil_unten", 10, 10), case=None)
    check("Längslast Teillast unten: ein Element intern geteilt = zehn Elemente von Hand (1e-9)",
          abs(lam / lam10 - 1) < 1e-9, f"{lam:.6f} / {lam10:.6f}")


def test_hinweis_zaehlt_teilung():
    """Der Hinweis „Last in Stabrichtung“ zaehlt beim Knicken die gerechneten
    Elemente nach der internen Teilung (wie Theorie II. Ordnung)."""
    for teilung, soll in ((10, None), (2, "in 2 Elemente geteilt"), (1, "in 1 Element geteilt")):
        zeilen = []
        from statik3d import solver
        with contextlib.redirect_stdout(io.StringIO()):
            r = solver.solve_buckling(_saeule("teil_unten", teilung), 2, lambda t, *a: zeilen.append(str(t)))
        h = [z for z in zeilen if "trägt Last in Stabrichtung" in z]
        if soll is None:
            check("Hinweis Längslast, ein Element mit Stabteilung 10 (gerechnet in 10): kein Hinweis",
                  not h and not r.info.get("laengslast_teilung"), " | ".join(h)[:200])
        else:
            check(f"Hinweis Längslast, ein Element mit Stabteilung {teilung}: „{soll}“",
                  any(soll in z for z in h) and r.info.get("laengslast_teilung"), " | ".join(h)[:200])


# --------------------------------------------------------------------------
# Zugband-Kurzstab ohne Sollkraft: Knicken = α_cr „auto“ (Pruefagent Runde k5)
# --------------------------------------------------------------------------
def _zugband(band_teile=1, soll=False, arm=0.3):
    """Wie tests/test_versatz_achsen_lotrecht._zugband("kurzstab"), das Band
    wahlweise von Hand geteilt."""
    from statik3d.model import Model, Material, Section
    m = Model("Zugband")
    m.add_material(Material("S355", E=E, nu=0.3, rho=0.0, fy=355e6))
    q = Section.rectangle("Q", 0.2, 0.2)
    q.Asy = q.Asz = 0.0
    m.add_section(q)
    m.add_section(Section.circle("D", 0.03))
    m.add_section(Section("STARR", A=10.0, Iy=1.0, Iz=1.0, It=1.0, zmax=0.1, ymax=0.1))
    kn = [m.add_node(0.0, 0.0, 3.0 * k / 16) for k in range(17)]
    c = m.add_node(2.0, 0.0, 0.0)
    m.fix(kn[0], "all")
    m.fix(c, "all")
    for k in range(16):
        m.add_element("beam", [kn[k], kn[k + 1]], "S355", "Q")
    kopf = np.array([0.0, 0.0, 3.0])
    t = kopf - np.array([2.0, 0.0, 0.0])
    t /= np.linalg.norm(t)
    p = m.add_node(*(kopf - arm * t))
    X0, X1 = np.array([2.0, 0.0, 0.0]), kopf - arm * t
    ids = [c] + [m.add_node(*(X0 + (X1 - X0) * k / band_teile)) for k in range(1, band_teile)] + [p]
    band = [m.add_element("beam", [ids[k], ids[k + 1]], "S355", "D") for k in range(band_teile)]
    m.add_element("beam", [p, kn[-1]], "S355", "STARR")
    m.add_member("Band", band)
    m.add_load_case("V").gravity = [0, 0, 0]
    m.add_vorspannung("Band", 70e3, case="V", sollkraft=soll)
    m.design.imperfektionen = False
    m.add_combination("K1", {"V": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m


def test_zugband():
    from statik3d import theorie2
    for arm in (0.3, -0.3):
        lam, _r = _knick(_zugband(arm=arm), 150, combination="K1")
        with contextlib.redirect_stdout(io.StringIO()):
            a = theorie2.check_theorie2(_zugband(arm=arm), None, ["K1"]).kombinationen["K1"].alpha_cr
        lam10, _r = _knick(_zugband(10, arm=arm), 150, combination="K1")
        check(f"Zugband-Kurzstab ohne Sollkraft, Arm {arm:+.1f}: Knicken = α_cr „auto“ (1e-6) = Band von "
              "Hand in 10 Teilen (1e-8)", abs(lam / a - 1) < 1e-6 and abs(lam / lam10 - 1) < 1e-8,
              f"Knicken {lam:.4f}, auto {a:.4f}, von Hand {lam10:.4f}")
    # mit Sollkraft 70 kN: das verriegelte Band traegt 70 kN Zug und wird geteilt -
    # auch bei α_cr „auto“ (stabteilung.kraefte_theorie1 mit Spannschritt und
    # Verriegelung); bis dahin dort N = 0, Band ungeteilt: 801,6 statt 603,4
    for arm in (0.3, -0.3):
        lam, _r = _knick(_zugband(soll=True, arm=arm), 150, combination="K1")
        with contextlib.redirect_stdout(io.StringIO()):
            a = theorie2.check_theorie2(_zugband(soll=True, arm=arm), None, ["K1"]).kombinationen["K1"].alpha_cr
        lam10, _r = _knick(_zugband(10, soll=True, arm=arm), 150, combination="K1")
        check(f"Zugband-Kurzstab mit Sollkraft, Arm {arm:+.1f}: Knicken = α_cr „auto“ (1e-6) = Band von "
              "Hand in 10 Teilen (1e-8)", abs(lam / a - 1) < 1e-6 and abs(lam / lam10 - 1) < 1e-8,
              f"Knicken {lam:.4f}, auto {a:.4f}, von Hand {lam10:.4f}")


# --------------------------------------------------------------------------
# Unveraendert: schon fein geteilt, unter der Relevanzgrenze
# --------------------------------------------------------------------------
def test_unveraendert():
    _lam, r = _knick(_stuetze([0, 1, 2, 5], [0, 1], n=10))
    check("Stütze schon in 10 Elementen: keine interne Teilung, Eigenform an 11 Knoten",
          "stabteilung" not in r.info and np.asarray(r.buckling_modes).shape[1] == 11,
          f"{r.info.get('stabteilung')} {np.asarray(r.buckling_modes).shape}")
    # Riegel ohne Normalkraft (unter der Relevanzgrenze) bleibt ein Element
    from statik3d.model import Model, Material, Section
    m = Model("R0")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=IY, Iz=IZ, It=2e-4, zmax=0.1, ymax=0.05))
    a = [m.add_node(0, 0, H_R * k / 10) for k in range(11)]
    b = [m.add_node(B_R, 0, H_R * k / 10) for k in range(11)]
    m.add_member("SL", [m.add_element("beam", [a[k], a[k + 1]], "ST", "Q") for k in range(10)])
    m.add_member("SR", [m.add_element("beam", [b[k], b[k + 1]], "ST", "Q") for k in range(10)])
    m.add_member("RI", [m.add_element("beam", [a[-1], b[-1]], "ST", "Q")])
    m.fix(a[0], "all")
    m.fix(b[0], "all")
    m.load_node(a[-1], Fz=-1000e3)
    m.load_node(b[-1], Fz=-1000e3)
    _lam, r = _knick(m)
    check("Rahmen mit geteilten Stielen, Riegel ohne Normalkraft: keine interne Teilung",
          "stabteilung" not in r.info, str(r.info.get("stabteilung")))


def test_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("knicken_stabteilung")
    check("Merkmal knicken_stabteilung: Stand 61, Fehlerkorrektur, VERFAHRENSSTAND >= 61",
          mk is not None and mk.wechsel[-1].stand == 61 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 61, f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    check("Merkmal betrifft: Stütze aus einem Element ja, aus zehn nein",
          mk.betrifft(_stuetze("all", [], n=1)) and not mk.betrifft(_stuetze("all", [], n=10)))
    from statik3d import solver

    class _An:
        def __init__(self, ergebnisse):
            self.cases, self.combinations = ergebnisse, {}

        def all_results(self):
            return dict(self.cases)

    m = _stuetze("all", [], n=1)
    r = solver.Results(name="LF1", kind="buckling", model=m)
    s_ = solver.Results(name="LF1", kind="case", model=m)
    check("Merkmal im Ergebnis: Knickergebnis ja, statisches Ergebnis nein",
          bool(mk.im_ergebnis(m, _An({"LF1": r}))) and not mk.im_ergebnis(m, _An({"LF1": s_}))
          and bool(mk.im_ergebnis(m, r)),
          f"{mk.im_ergebnis(m, _An({'LF1': r}))!r} / {mk.im_ergebnis(m, _An({'LF1': s_}))!r}")


def main():
    for t in (test_euler, test_knicklaengen, test_rahmen, test_laengslast, test_hinweis_zaehlt_teilung,
              test_zugband, test_unveraendert, test_merkmal):
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
