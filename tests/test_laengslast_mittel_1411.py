"""
Befund B'6 der Befundliste vom 14.11.2026 (Runde 2, Theorie II. Ordnung):
Stab mit ungleichmaessiger Last in Stabrichtung, in einem Element gerechnet
(Netzeinstellung Stabteilung 1).

B'6a: Am Laengsgelenk nahm die geometrische Steifigkeit (asm.stab_normalkraft)
und der Feldanteil N w (solver._th2_feldanteil) die halbe Gesamtlast
½ (f_l[6] - f_l[0]) als Normalkraft - richtig nur bei gleichmaessiger Last.
Das Mittel der Normalkraft ueber den Stab ist das Integral der Last mal
ihrem Abstand vom Gelenk: Gelenk am Stabende N(x) = int_x^L q ds, Mittel
1/L int_0^L s q ds = f0[6] (konsistente Stabendlast); Gelenk am Stabanfang
-f0[0]. Stuetze 5 m, Teillast oben: -3000 statt -5400 kN, alpha_cr 3,360
statt 1,867, max|My| 4,95 statt 9,14 kNm (DGL 8,08).

B'6b: Der Feldanteil nahm fuer Staebe ohne Gelenk P = f_l[0], die
Stabkraft am Stabanfang - das Ergebnis hing von der Elementrichtung ab
(gleichmaessige Last: 11,556 bzw. 3,125 kNm, Element allein 4,949, DGL
5,0745). Jetzt das Integralmittel wie in K_G.

Zwei Wege je Zahl: die Handformeln (Integralmittel geschlossen, alpha_cr
eines Elements 12 EI/(L² |N|), Moment bei konstanter Normalkraft mit der
sec- bzw. sech-Formel) und die eigene Loesung der DGL
EI w'''' + (P(x) w')' = q mit finiten Differenzen in gemischter Form (w, M)
- gegengeprueft mit einem Ritz-Ansatz (Sinusreihe), beide auf 0,01 %.

Aufruf:  python -m tests.test_laengslast_mittel_1411
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
L = 5.0
QX = 1e3            # quer, N/m
QM = 1.2e6          # in Stabrichtung, N/m
ARTEN = ("gleich", "dreieck_oben", "dreieck_unten", "teil_unten", "teil_oben")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def nahe(name, ist, soll, rel):
    ok = math.isfinite(ist) and abs(ist - soll) <= rel * max(abs(soll), 1e-30)
    return check(name, ok, f"ist {ist:.6g}, soll {soll:.6g} (±{rel * 100:g} %)")


# --------------------------------------------------------------------------
# Lasten in Stabrichtung (z von unten): Streckenlast q(z) nach unten
# --------------------------------------------------------------------------
def _q(art, z):
    if art == "gleich":
        return QM + 0 * z
    if art == "dreieck_oben":
        return 2 * QM * z / L
    if art == "dreieck_unten":
        return 2 * QM * (1 - z / L)
    if art == "teil_unten":
        return np.where(z <= 1.0, 5 * QM, 0.0)
    if art == "teil_oben":
        return np.where(z >= 4.0, 5 * QM, 0.0)
    raise KeyError(art)


def _mittel_hand(art, haengend=False):
    """Integralmittel der Normalkraft (Zug positiv), geschlossen: stehend
    (Laengsgelenk oben) -1/L int z q dz, haengend (Laengsgelenk unten)
    +1/L int (L - z) q dz."""
    s1 = {"gleich": QM * L ** 2 / 2, "dreieck_oben": 2 * QM * L ** 2 / 3, "dreieck_unten": 2 * QM * L ** 2 / 6,
          "teil_unten": 5 * QM * 0.5, "teil_oben": 5 * QM * (25 - 16) / 2}[art]
    Q = QM * L if art.startswith(("gleich", "dreieck")) else 5 * QM
    return (Q * L - s1) / L if haengend else -s1 / L


def _ein_element(Nm):
    """Ein Element mit konstanter Normalkraft Nm (Zug positiv), gelenkig,
    Querlast QX: (alpha_cr, max|M|) - 12 EI/(L² |N|) aus k und k_G des
    Elements, das Moment nach der sec-/sech-Formel (Feldanteil N w exakt)."""
    if Nm < 0:
        k = math.sqrt(-Nm / EI)
        return 12 * EI / (L ** 2 * -Nm), QX / k ** 2 * (1 / math.cos(k * L / 2) - 1)
    k = math.sqrt(Nm / EI)
    return math.inf, QX / k ** 2 * (1 - 1 / math.cosh(k * L / 2))


def _dgl(art, haengend=False, n=2000):
    """DGL EI w'''' + (P w')' = q mit P Druck positiv, gelenkig/gelenkig, in
    gemischter Form: EI w'' = -M, M'' = -q + (P w')' (finite Differenzen,
    w = M = 0 an den Enden). (max|M|, alpha_cr) - alpha_cr nur stehend."""
    from scipy import linalg, sparse
    from scipy.sparse import linalg as spl
    h = L / n
    z = np.linspace(0, L, n + 1)
    zf = np.linspace(0, L, 200001)
    qf = _q(art, zf)
    cum = np.concatenate([[0], np.cumsum(0.5 * (qf[1:] + qf[:-1]) * np.diff(zf))])
    Pf = -cum if haengend else cum[-1] - cum
    m = n - 1
    pp = np.interp(z[1:-1] + h / 2, zf, Pf)
    pm = np.interp(z[1:-1] - h / 2, zf, Pf)
    D2 = sparse.diags([np.ones(m - 1), -2 * np.ones(m), np.ones(m - 1)], [-1, 0, 1]) / h ** 2
    G = sparse.diags([pm[1:], -(pp + pm), pp[:-1]], [-1, 0, 1]) / h ** 2
    A = sparse.bmat([[EI * D2, sparse.identity(m)], [-G, D2]]).tocsc()
    sol = spl.spsolve(A, np.concatenate([np.zeros(m), -np.full(m, QX)]))
    a = None
    if not haengend:
        mu = linalg.eigvals(np.linalg.solve((EI * (D2 @ D2)).toarray(), -G.toarray()))
        a = float(1.0 / np.real(mu[np.abs(np.imag(mu)) < 1e-9]).max())
    return float(np.abs(sol[m:]).max()), a


# --------------------------------------------------------------------------
# Programmmodell: Stuetze 5 m, gelenkig, Querlast QX (global x)
# --------------------------------------------------------------------------
def _stuetze(art, gelenk, umgedreht=False, teilung=1, haengend=False, temperatur=0.0, theorie="II"):
    """``gelenk``: Laengsgelenk oben (stehend, Fuss axial gehalten) bzw. unten
    (``haengend``, Kopf axial gehalten); ohne Gelenk axial am Fuss (stehend)
    bzw. am Kopf (haengend) gehalten - dasselbe System. ``umgedreht``: das
    Element laeuft von oben nach unten."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=0.01, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    m.netz.stabteilung = teilung
    nu = m.add_node(0, 0, 0)
    no = m.add_node(0, 0, L)
    e = m.add_element("beam", [no, nu] if umgedreht else [nu, no], "ST", "Q")
    lager, frei = (no, nu) if haengend else (nu, no)
    m.fix(lager, [0, 1, 2])
    m.fix(nu, [5])
    if gelenk:
        m.fix(frei, [0, 1, 2])
        # Gelenk am freien Knoten: Element-Ende 1, wenn es dort endet
        am_ende = (frei == no) != umgedreht
        m.add_hinge("GE", end=1 if am_ende else 0, ux="free")
        m.apply_hinge(e, "GE")
    else:
        m.fix(frei, [0, 1])
    m.case("LF1")
    m.load_beam(e, qx=QX, case="LF1")
    # Stablast in Stabrichtung, Lage und Verlauf ab dem Elementanfang
    z0, z1 = (L, 0.0) if umgedreht else (0.0, L)
    if art in ("gleich", "dreieck_oben", "dreieck_unten"):
        m.load_beam(e, qz=-float(_q(art, z0)), q2=[0.0, 0.0, -float(_q(art, z1))], case="LF1")
    else:
        unten = art == "teil_unten"
        a, b = ((0.0, 1.0) if unten else (4.0, 5.0)) if not umgedreht else ((4.0, 5.0) if unten else (0.0, 1.0))
        m.load_beam(e, qz=-5 * QM, a=a, b=b, case="LF1")
    if temperatur:
        m.load_temp(e, temperatur, case="LF1")
    m.load_cases["LF1"].theorie = theorie
    return m, e


def _n_kg(m, e):
    from statik3d import solver, theorie2
    sy = solver.StaticSystem(m)
    F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    u = sy.solve(F)
    return theorie2.normalkraefte_kg(m, u, n_anfang=solver.anfangsnormalkraefte(m, {"LF1": 1.0}),
                                     feq=feq)[e]


def _rechne(m, e):
    from statik3d import solver
    r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
    st = solver.beam_station_forces(m, r, e, 81)
    return float(r.info.get("alpha_cr") or math.inf), float(np.abs(st["My"]).max()), r


# --------------------------------------------------------------------------
def test_integralmittel_kg():
    """B'6a: die Normalkraft des Elements mit Laengsgelenk in K_G ist das
    Integralmittel - wie derselbe Stab ohne Gelenk (E A Δl/L), Gelenk am
    Stabende und am Stabanfang."""
    for art in ARTEN:
        soll = _mittel_hand(art)
        zf = np.linspace(0, L, 200001)
        num = -np.trapezoid(np.cumsum(np.r_[0.0, 0.5 * (_q(art, zf)[1:] + _q(art, zf)[:-1]) * np.diff(zf)])[-1]
                            - np.cumsum(np.r_[0.0, 0.5 * (_q(art, zf)[1:] + _q(art, zf)[:-1]) * np.diff(zf)]),
                            zf) / L
        nahe(f"Handformel = Integral numerisch ({art})", num, soll, 1e-4)
        ohne = _n_kg(*_stuetze(art, False))
        nahe(f"N in K_G ohne Gelenk = Integralmittel {soll / 1e3:.0f} kN ({art})", ohne, soll, 1e-9)
        for umg in (False, True):
            n = _n_kg(*_stuetze(art, True, umg))
            nahe(f"N in K_G Längsgelenk am Stab{'anfang' if umg else 'ende'} = {soll / 1e3:.0f} kN ({art})",
                 n, soll, 1e-9)


def test_integralmittel_haengend():
    """Laengsgelenk unten, Kopf axial gehalten: die Last haengt, Zug
    +1/L int (L - z) q dz (Dreieck oben 2000, Teillast oben 600 kN statt
    ½ Q = 3000 kN)."""
    for art in ("dreieck_oben", "teil_oben", "teil_unten"):
        soll = _mittel_hand(art, haengend=True)
        nahe(f"hängend: N in K_G ohne Gelenk = {soll / 1e3:.0f} kN ({art})",
             _n_kg(*_stuetze(art, False, haengend=True)), soll, 1e-9)
        for umg in (False, True):
            nahe(f"hängend: N in K_G Längsgelenk am Stab{'ende' if umg else 'anfang'} = {soll / 1e3:.0f} kN ({art})",
                 _n_kg(*_stuetze(art, True, umg, haengend=True)), soll, 1e-9)


def test_temperatur_am_gelenk():
    """Die Anfangsdehnung zaehlt am Laengsgelenk nicht (das Ende ist in
    Stabrichtung frei): Dreieck oben mit dT = 30 K wie ohne."""
    soll = _mittel_hand("dreieck_oben")
    for umg in (False, True):
        m, e = _stuetze("dreieck_oben", True, umg, temperatur=30.0)
        nahe(f"Längsgelenk mit dT 30 K am Stab{'anfang' if umg else 'ende'}: N in K_G = {soll / 1e3:.0f} kN",
             _n_kg(m, e), soll, 1e-9)
        a, My, _r = _rechne(m, e)
        a0, My0, _r0 = _rechne(*_stuetze("dreieck_oben", True, umg))
        nahe(f"Längsgelenk mit dT 30 K am Stab{'anfang' if umg else 'ende'}: alpha_cr wie ohne dT", a, a0, 1e-9)
        nahe(f"Längsgelenk mit dT 30 K am Stab{'anfang' if umg else 'ende'}: max|My| wie ohne dT", My, My0, 1e-9)
    # ohne Laengslast bleibt das Gelenk mit Temperatur ohne Normalkraft
    from statik3d.model import Model  # noqa: F401
    m, e = _stuetze("gleich", True, temperatur=30.0)
    m.load_cases["LF1"].beam_loads = [bl for bl in m.load_cases["LF1"].beam_loads if not bl.q[2]]
    check("Längsgelenk nur mit dT und Querlast: N in K_G = 0", abs(_n_kg(m, e)) < 1e-6, f"{_n_kg(m, e):.3g} N")


def test_ein_element():
    """Netzeinstellung Stabteilung 1: alpha_cr und max|My| mit dem
    Integralmittel, gleich fuer beide Elementrichtungen und mit/ohne
    Laengsgelenk (B'6a und B'6b)."""
    for art in ARTEN:
        a_h, M_h = _ein_element(_mittel_hand(art))
        werte = {}
        for gel in (True, False):
            for umg in (False, True):
                a, My, r = _rechne(*_stuetze(art, gel, umg))
                werte[(gel, umg)] = (a, My)
                txt = f"{'Längsgelenk' if gel else 'ohne Gelenk'}, {'oben→unten' if umg else 'unten→oben'}"
                check(f"ein Element ungeteilt ({art}, {txt})", not r.info.get("stabteilung"),
                      f"{r.info.get('stabteilung')}")
                nahe(f"1 El. alpha_cr = 12 EI/(L² |N_m|) = {a_h:.4f} ({art}, {txt})", a, a_h, 1e-6)
                nahe(f"1 El. max|My| = sec-Formel mit N_m {M_h / 1e3:.4f} kNm ({art}, {txt})", My, M_h, 1e-3)
        ref = werte[(False, False)][1]
        for k, (a, My) in werte.items():
            nahe(f"1 El. max|My| unabhängig von Gelenk und Richtung ({art}, {k})", My, ref, 1e-6)


def test_ein_element_haengend():
    for art in ("dreieck_oben", "teil_oben"):
        _a, M_h = _ein_element(_mittel_hand(art, haengend=True))
        for gel in (True, False):
            for umg in (False, True):
                _a2, My, _r = _rechne(*_stuetze(art, gel, umg, haengend=True))
                nahe(f"hängend 1 El. max|My| = sech-Formel {M_h / 1e3:.4f} kNm ({art}, "
                     f"{'Längsgelenk' if gel else 'ohne Gelenk'}, {'oben→unten' if umg else 'unten→oben'})",
                     My, M_h, 1e-3)


def test_vorgabe_teilung_dgl():
    """Vorgabe Stabteilung 10: gegen die DGL, und die Teilstuecke nehmen im
    Feldanteil ihr Mittel - unabhaengig von der Elementrichtung (bis dahin
    5,0753 gegen 5,0727 kNm)."""
    for art in ARTEN:
        M_d, a_d = _dgl(art)
        print(f"   DGL {art}: max|M| {M_d / 1e3:.4f} kNm, alpha_cr {a_d:.4f}")
        werte = {}
        for gel in (True, False):
            for umg in (False, True):
                a, My, r = _rechne(*_stuetze(art, gel, umg, teilung=10))
                werte[(gel, umg)] = My
                txt = f"{'Längsgelenk' if gel else 'ohne Gelenk'}, {'oben→unten' if umg else 'unten→oben'}"
                nahe(f"Teilung 10: max|My| = DGL ({art}, {txt})", My, M_d, 0.005)
                # Teillast unten: alpha_cr konvergiert mit h² (20 El. 5,662, 40 El. 5,626)
                nahe(f"Teilung 10: alpha_cr = DGL ({art}, {txt})", a, a_d, 0.04 if art == "teil_unten" else 0.01)
        for gel in (True, False):
            nahe(f"Teilung 10: max|My| unabhängig von der Elementrichtung ({art}, "
                 f"{'Längsgelenk' if gel else 'ohne Gelenk'})", werte[(gel, True)], werte[(gel, False)], 2e-5)


def test_ohne_laengslast_unveraendert():
    """Staebe ohne Last in Stabrichtung rechnen wie vor der Behebung
    (Werte vom Stand 542ba156)."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver
    soll = {(1, False): 4948.441355184238, (1, True): 4948.441355184238,
            (10, False): 4949.153822995438, (10, True): 4949.153822995496}
    for (n_teil, umg), wert in soll.items():
        m = Model("T")
        m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
        m.add_section(Section("Q", A=0.01, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
        m.design.imperfektionen = False
        n0, n1 = m.add_node(0, 0, 0), m.add_node(0, 0, L)
        e = m.add_element("beam", [n1, n0] if umg else [n0, n1], "ST", "Q")
        m.fix(n0, [0, 1, 2, 5])
        m.fix(n1, [0, 1])
        m.case("LF1")
        m.load_node(n1, Fz=-3e6, case="LF1")
        m.load_beam(e, qx=QX, case="LF1")
        m.load_cases["LF1"].theorie = "II"
        m.netz.stabteilung = n_teil
        r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
        My = float(np.abs(solver.beam_station_forces(m, r, e, 81)["My"]).max())
        nahe(f"Knotenlast statt Stablast: max|My| wie vorher (Teilung {n_teil}, "
             f"{'oben→unten' if umg else 'unten→oben'})", My, wert, 1e-12)
    for umg in (False, True):
        m, e = _stuetze("gleich", True, umg, temperatur=30.0)
        m.load_cases["LF1"].beam_loads = [bl for bl in m.load_cases["LF1"].beam_loads if not bl.q[2]]
        a, My, _r = _rechne(m, e)
        nahe(f"Längsgelenk ohne Längslast mit dT: q L²/8 = 3,125 kNm ({'oben→unten' if umg else 'unten→oben'})",
             My, QX * L ** 2 / 8, 1e-12)
        check(f"Längsgelenk ohne Längslast mit dT: kein alpha_cr ({'oben→unten' if umg else 'unten→oben'})",
              not math.isfinite(a), f"{a}")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("th2_laengslast_mittel")
    check("Merkmal th2_laengslast_mittel vorhanden", mk is not None)
    if mk is None:
        return
    w = mk.wechsel[-1]
    check("… Stand 58, Fehlerkorrektur", w.stand == 58 and w.art == rv.FEHLERKORREKTUR, f"{w.stand} {w.art}")
    check("… VERFAHRENSSTAND ≥ 58", rv.VERFAHRENSSTAND >= 58, f"{rv.VERFAHRENSSTAND}")
    m1, _e = _stuetze("dreieck_oben", False)                 # Stabteilung 1, Laengslast
    m10, _e = _stuetze("dreieck_oben", False, teilung=10)    # Vorgabe, ohne Gelenk
    mg10, _e = _stuetze("dreieck_oben", True, teilung=10)    # Laengsgelenk: Knicken teilt nicht
    mq, e = _stuetze("gleich", False)
    mq.load_cases["LF1"].beam_loads = [bl for bl in mq.load_cases["LF1"].beam_loads if not bl.q[2]]
    check("… betroffen: Längslast bei Stabteilung 1 ja", mk.betrifft(m1))
    check("… betroffen: Längslast bei Vorgabe ohne Längsgelenk nein", not mk.betrifft(m10))
    check("… betroffen: Längsgelenk mit Längslast auch bei Vorgabe ja", mk.betrifft(mg10))
    check("… betroffen: ohne Längslast nein", not mk.betrifft(mq))


def main():
    for t in (test_integralmittel_kg, test_integralmittel_haengend, test_temperatur_am_gelenk, test_ein_element,
              test_ein_element_haengend, test_vorgabe_teilung_dgl, test_ohne_laengslast_unveraendert,
              test_verfahrenstabelle):
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
