"""
Fehlerliste F11 (Paket P7, 06.10.2026): Linienlasten und Linienlager auf
quadratischen Kanten.

Eine Linie im Netz ist eine Kette von Elementkanten. Auf einer quadratischen
Kante (Ecke, Kantenmitte, Ecke: tet10, hex20, shell6, shell8, ...) gehoert zu
einer Linienlast q(s) an jeden Knoten das Integral int N_i q ds mit den
quadratischen Formfunktionen der Kante - bei gleichmaessiger Last L/6, 2L/3,
L/6. Bis zum 06.10.2026 wurde die Kette als Folge linearer Teilstuecke
behandelt (L/4, L/2, L/4); die Summe stimmte, die Verteilung nicht. Federnde
Linienlager bekamen ihre Steifigkeit auf dieselbe Weise.

Geprueft wird gegen

* eine unabhaengige Integration (scipy.integrate.quad mit den
  Lagrange-Polynomen der Kante in x) Knoten fuer Knoten - gleichmaessig,
  Trapez, Teilstrecke und eine Stichprobe ueber Abschnitt und Lastwerte;
* die Momente der Last: Resultierende und statisches Moment fuer lineare und
  quadratische Kanten, dazu das zweite Moment int q x^2 dx, das nur die
  quadratische Kante exakt wiedergibt;
* den Vergleich lineare Kante gegen quadratische Kante: die Last der
  Kantenmitte je zur Haelfte auf ihre Ecken gelegt (die Bindung
  u_m = (u_a + u_b)/2) ergibt genau die Knotenlasten des linearen Netzes;
* einen Patch-Test: ein Scheibenstreifen aus shell8/shell6 unter einer
  Linienlast in seiner Ebene hat exakt gleichmaessige Spannung, die Kante
  verschiebt sich ueberall gleich - mit konsistenten Lasten, nicht mit dem
  Hebelgesetz. Ebenso mit einem federnden Linienlager statt der Sperrung.

    python -m tests.test_fehler_p7
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from scipy import integrate, optimize  # noqa: E402

from statik3d.model import Model, Material, ShellProp  # noqa: E402
from statik3d import mesher, solver, supports  # noqa: E402
from tests import pruefmatrix as pmx  # noqa: E402

RESULTS = []


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:<70s} {info}")
    return bool(ok)


# --------------------------------------------------------------------------
# Koerper mit einer Kante: Quader 1 x 0,25 x 0,25 m, h = 0,25 m
# --------------------------------------------------------------------------
H = 0.25


def koerper(typ):
    """Quader aus ``typ`` (hex8, hex20, tet10) und der Name der Linie entlang
    x bei y = 0, z = 0,25 (Oberkante, 1 m lang)."""
    familie = "tet" if typ.startswith("tet") else "hex"
    ordnung = 2 if typ in ("hex20", "tet10") else 1
    m = pmx.geo_modell(ordnung, H)
    g = pmx.Geo(m)
    k = g.quader("K", (0, 0, 0), (1.0, 0.25, 0.25))
    pmx.vernetzen(m, [k], familie, H, ordnung, [])
    a = g.knoten((0, 0, 0.25))
    b = g.knoten((1.0, 0, 0.25))
    return m, g.li[(min(a, b), max(a, b))]


def knotenlasten(m, ll):
    """{x: F (3,)} der Knotenlasten einer Linienlast auf der Linie entlang x."""
    out = {}
    for nl in m._linienlast_legen(ll):
        x = round(float(m.nodes[nl.node, 0]), 9)
        out[x] = out.get(x, np.zeros(3)) + np.asarray(nl.F[:3], float)
    return out


def q_von(q1, q2, von, bis):
    q1, q2 = np.asarray(q1, float), np.asarray(q2, float)

    def q(x):
        if x < von or x > bis:
            return np.zeros(3)
        t = (x - von) / (bis - von)
        return (1 - t) * q1 + t * q2
    return q


def referenz(xs, quadratisch, q, von, bis):
    """Unabhaengig: int N_i(x) q(x) dx je Knoten mit den Lagrange-Polynomen
    der geraden Kante in x (quad, adaptiv). xs: Knotenlagen, sortiert."""
    xs = list(xs)
    F = {x: np.zeros(3) for x in xs}
    schritt = 2 if quadratisch else 1
    for i in range(0, len(xs) - 1, schritt):
        kn = xs[i:i + schritt + 1]
        lo, hi = max(von, kn[0]), min(bis, kn[-1])
        if hi <= lo:
            continue
        for j, xj in enumerate(kn):
            andere = [x for k, x in enumerate(kn) if k != j]

            def N(x, xj=xj, andere=andere):
                return float(np.prod([(x - a) / (xj - a) for a in andere]))
            for c in range(3):
                F[xj][c] += integrate.quad(lambda x: N(x) * q(x)[c], lo, hi,
                                           epsabs=1e-12, epsrel=1e-12)[0]
    return F


def momente(F):
    x = np.array(sorted(F))
    f = np.array([F[k] for k in sorted(F)])
    return f.sum(axis=0), (f * x[:, None]).sum(axis=0), (f * x[:, None] ** 2).sum(axis=0)


def momente_soll(q, von, bis):
    return tuple(np.array([integrate.quad(lambda x: q(x)[c] * x ** p, von, bis,
                                          epsabs=1e-12, epsrel=1e-12)[0] for c in range(3)])
                 for p in (0, 1, 2))


def abw(a, b, skala):
    return float(np.max(np.abs(np.asarray(a) - np.asarray(b)))) / max(skala, 1e-300)


# --------------------------------------------------------------------------
def test_gleichlast_auf_quadratischer_kante():
    """q = 1000 N/m auf 1 m, Kanten 0,25 m: Kantenmitte 2qL/3 = 166,7 N,
    innere Ecke 2 qL/6 = 83,3 N, Endecke qL/6 = 41,7 N - der Befund F11
    (vorher 125 N an Mitte und Ecke, 62,5 N am Ende). hex8 bleibt bei 125/250 N."""
    q = 1000.0
    for typ in ("hex20", "tet10"):
        m, name = koerper(typ)
        typen = {e.typ for e in m.elements}
        ll = m.add_linienlast(name, [0.0, 0.0, -q], art="linie")
        F = knotenlasten(m, ll)
        xs = sorted(F)
        gitter = np.allclose(xs, np.arange(9) * H / 2)
        soll = {x: -q * H * ((1 / 6 if x in (0.0, 1.0) else 1 / 3) if i % 2 == 0 else 2 / 3)
                for i, x in enumerate(xs)}
        fehler = max(abs(F[x][2] - soll[x]) for x in xs) if gitter else float("inf")
        werte = ", ".join(f"{F[x][2]:.1f}" for x in xs)
        check(f"{typ}: Gleichlast L/6, 2L/3, L/6 je Kante ({typen})",
              gitter and fehler < 1e-9 * q, f"Fz = [{werte}] N")
    m, name = koerper("hex8")
    F = knotenlasten(m, m.add_linienlast(name, [0.0, 0.0, -q], art="linie"))
    xs = sorted(F)
    soll = [-q * H / 2] + [-q * H] * 3 + [-q * H / 2]
    check("hex8: Gleichlast wie bisher L/2 je Kante",
          len(xs) == 5 and max(abs(F[x][2] - s) for x, s in zip(xs, soll)) < 1e-9 * q,
          "Fz = [" + ", ".join(f"{F[x][2]:.1f}" for x in xs) + "] N")


def faelle():
    """(Bezeichnung, q1, q2, von, bis): gleichmaessig, Trapez, Teilstrecke
    mit Schnitten innerhalb der Kanten und Vorzeichenwechsel, dazu eine
    Stichprobe."""
    out = [("gleichmaessig", [0, 0, -1e3], [0, 0, -1e3], 0.0, 1.0),
           ("Trapez 0 -> q", [0, 0, 0], [0, 0, -2e3], 0.0, 1.0),
           ("Teilstrecke 0,1..0,8, Trapez mit Vorzeichenwechsel", [300, 0, -2e3], [-100, 50, 500],
            0.1, 0.8),
           ("Teilstrecke innerhalb einer Kante 0,30..0,45", [0, 0, -1e3], [0, 0, -4e3], 0.30, 0.45)]
    rng = np.random.default_rng(611)
    for k in range(10):
        von, bis = sorted(rng.uniform(0.0, 1.0, 2))
        if bis - von < 0.02:
            bis = min(1.0, von + 0.02)
        out.append((f"Stichprobe {k + 1}", rng.uniform(-5e3, 5e3, 3), rng.uniform(-5e3, 5e3, 3),
                    float(von), float(bis)))
    return out


def test_trapez_und_teilstrecke():
    """Knoten fuer Knoten gegen die unabhaengige Integration; Resultierende
    und Momente; lineare gegen quadratische Kante."""
    netze = {typ: koerper(typ) for typ in ("hex8", "hex20", "tet10")}
    for bez, q1, q2, von, bis in faelle():
        q = q_von(q1, q2, von, bis)
        skala = max(np.abs(q1).max(), np.abs(q2).max()) * (bis - von)
        soll0, soll1, soll2 = momente_soll(q, von, bis)
        je_typ = {}
        for typ, (m, name) in netze.items():
            m.case().linienlasten.clear()
            ll = m.add_linienlast(name, list(q1), art="linie", q2=list(q2), von=von, bis=bis)
            F = knotenlasten(m, ll)
            xs = sorted(set(F) | {round(float(x), 9) for x in
                                  m.nodes[[n for n, _s in m.knoten_auf_linie(name)], 0]})
            F = {x: F.get(x, np.zeros(3)) for x in xs}
            je_typ[typ] = F
            quadratisch = typ != "hex8"
            ref = referenz(xs, quadratisch, q, von, bis)
            d = max(abw(F[x], ref[x], skala) for x in xs)
            r0, r1, r2 = momente(F)
            d0, d1, d2 = abw(r0, soll0, skala), abw(r1, soll1, skala), abw(r2, soll2, skala)
            ok = d < 1e-8 and d0 < 1e-10 and d1 < 1e-10 and (d2 < 1e-10 or not quadratisch)
            check(f"{typ} {bez}: Knotenlasten = int N_i q ds, Momente",
                  ok, f"Knoten {d:.1e}, Summe {d0:.1e}, Moment {d1:.1e}, x² {d2:.1e}")
        # lineare gegen quadratische Kante: Mitte je zur Haelfte auf die Ecken
        lin = je_typ["hex8"]
        for typ in ("hex20", "tet10"):
            F = je_typ[typ]
            xs = sorted(F)
            gebunden = {x: F[x].copy() for x in xs[::2]}
            for i in range(1, len(xs), 2):
                gebunden[xs[i - 1]] += 0.5 * F[xs[i]]
                gebunden[xs[i + 1]] += 0.5 * F[xs[i]]
            gleich = sorted(gebunden) == sorted(lin) and \
                max(abw(gebunden[x], lin[x], skala) for x in lin) < 1e-9
            check(f"{typ} {bez}: Mitte auf die Ecken gebunden = hex8", gleich,
                  f"{max(abw(gebunden[x], lin.get(x, np.zeros(3)), skala) for x in gebunden):.1e}")


def test_kantenintegral_ausser_mitte():
    """Eine Kantenmitte ausser der Mitte (gekruemmte Linie, Bogenlage s):
    s(xi) = sum N_i(xi) s_i, Lage auf der Kante durch Nullstellensuche -
    unabhaengig von der geschlossenen Umkehrung im Programm."""
    from statik3d.linienverteilung import kantenintegral
    s = [0.0, 0.43, 1.0]

    def N(xi):
        return np.array([0.5 * xi * (xi - 1), 1 - xi * xi, 0.5 * xi * (xi + 1)])

    def s_von(xi):
        return float(N(xi) @ s)

    def ds(xi):
        return (s[2] - s[0]) / 2 + xi * (s[0] - 2 * s[1] + s[2])

    q = q_von([0, 0, 1e3], [0, 0, -3e3], 0.2, 0.9)
    lo, hi = 0.2, 0.9
    a = optimize.brentq(lambda x: s_von(x) - lo, -1, 1, xtol=1e-15)
    b = optimize.brentq(lambda x: s_von(x) - hi, -1, 1, xtol=1e-15)
    ref = np.array([[integrate.quad(lambda x: N(x)[i] * q(s_von(x))[2] * ds(x), a, b,
                                    epsabs=1e-12, epsrel=1e-12)[0]] for i in range(3)])
    ist = kantenintegral(s, lo, hi, lambda x: q(x)[2:3])
    check("Kantenintegral mit Mitte bei 0,43 L: Trapez auf Teilstrecke",
          abw(ist, ref, 3e3) < 1e-10, f"{np.ravel(ist).round(3)} gegen {np.ravel(ref).round(3)}")
    w = kantenintegral(s, 0.0, 1.0)
    wref = [integrate.quad(lambda x: N(x)[i] * ds(x), -1, 1)[0] for i in range(3)]
    check("Kantenintegral mit Mitte bei 0,43 L: Einflusslaengen", abw(w, wref, 1.0) < 1e-12,
          f"{np.round(w, 4)} gegen {np.round(wref, 4)}")
    w = kantenintegral([0.0, 0.5, 1.0], 0.0, 1.0)
    check("Kantenintegral mittig: L/6, 2L/3, L/6", abw(w, [1 / 6, 2 / 3, 1 / 6], 1.0) < 1e-14,
          str(np.round(w, 6)))


def test_kantentypen():
    """Jeder Elementtyp mit Kantenmitten (VTK tri6, quad8, tet10, hex20,
    wedge15) ist in der Kantentabelle; die Kanten der Volumen stimmen mit
    der Kantenreihenfolge der Elemente ueberein."""
    from statik3d import elemente as EL
    from statik3d.elements import solid as sl
    from statik3d.linienverteilung import kanten_mit_mitte
    km = kanten_mit_mitte()
    mit_mitte = [t for t, a in EL.ELEMENTE.items() if a.vtk in (EL.VTK_TRI6, EL.VTK_QUAD8,
                                                                EL.VTK_TET10, EL.VTK_HEX20,
                                                                EL.VTK_WEDGE15)]
    check("alle Typen mit Kantenmitten in der Tabelle", set(mit_mitte) == set(km),
          f"{sorted(km)}")
    gleich = all(sorted((frozenset((a, b)), m) for a, b, m in km[t])
                 == sorted((frozenset(k), 1 + max(max(x) for x in sl._KANTEN_QUADRATISCH[t]) + i)
                           for i, k in enumerate(sl._KANTEN_QUADRATISCH[t]))
                 for t in ("tet10", "hex20", "pent15"))
    check("Volumenkanten wie solid._KANTEN_QUADRATISCH", gleich)


# --------------------------------------------------------------------------
# Patch-Test: Scheibenstreifen in seiner Ebene gezogen
# --------------------------------------------------------------------------
LX, LY, T, E, NU, Q = 2.0, 1.0, 0.02, 210e9, 0.3, 4.0e5


def streifen(ordnung, dreiecke=False, feder=None):
    """Streifen LX x LY aus Schalen (4 x 2), an L2 (x = LX) mit Q [N/m] in +x
    gezogen. Gehalten an L4 (x = 0) starr in x - oder mit einem federnden
    Linienlager in x (``feder`` [N/m je m]) -, in y an der Ecke (0, 0), aus der
    Ebene und in den Verdrehungen ueberall (Membranzustand)."""
    m = Model("Streifen")
    m.add_material(Material("S", E=E, nu=NU))
    m.add_shell_prop(ShellProp("t", T))
    m.add_nodes([[0, 0, 0], [LX, 0, 0], [LX, LY, 0], [0, LY, 0]])
    for i in range(4):
        m.add_line(f"L{i + 1}", [i, (i + 1) % 4], "polyline")
    f = m.add_flaeche("F", ["L1", "L2", "L3", "L4"], material="S", dicke="t", teilung=[4, 2])
    mesher.mesh_flaeche(m, f, dreiecke=dreiecke, ordnung=ordnung)
    for n in range(m.nn):
        m.fix(n, [2, 3, 4, 5])
    links = [n for n, _s in m.knoten_auf_linie("L4")]
    if feder is None:
        for n in links:
            m.fix(n, [0])
    else:
        ls = m.add_line_support([3, 0], name="Feder", ux=dict(typ="spring", stiffness=feder))
        ls.linien = ["L4"]
    m.fix(0, [1])
    m.add_linienlast("L2", [Q, 0.0, 0.0], art="linie")
    m.lasten_verteilen()
    return m, links, [n for n, _s in m.knoten_auf_linie("L2")]


def test_patch_streifen():
    """Gleichmaessige Spannung sigma = Q/T: u_x an der gezogenen Kante
    ueberall Q LX/(E T), auch an den Kantenmitten. Mit dem Hebelgesetz bekam
    die Kantenmitte zu wenig Last und blieb zurueck."""
    soll = Q * LX / (E * T)
    for typ, ordnung, dreiecke in (("shell8", 2, False), ("shell6", 2, True), ("shell4", 1, False)):
        m, _links, rechts = streifen(ordnung, dreiecke)
        typen = {e.typ for e in m.elements}
        r = solver.solve_static(m)
        ux = r.u[rechts, 0]
        d = float(np.max(np.abs(ux - soll))) / soll
        check(f"{typ}: Streifen gezogen, u_x an der Kante gleich ({typen})", d < 1e-8,
              f"u_x {ux.min() * 1e6:.4f} .. {ux.max() * 1e6:.4f} µm, Soll {soll * 1e6:.4f} µm, "
              f"Abw {d:.1e}")


def test_linienlager_quadratisch():
    """Einflusslaengen auf der quadratischen Kante L/6, 2L/3, L/6 (Summe L);
    Patch-Test mit federndem Linienlager: u_x = Q/k an jedem Knoten der
    gelagerten Kante."""
    for typ in ("hex20", "tet10"):
        m, name = koerper(typ)
        ls = m.add_line_support([0, 1], name="Kante", uz=dict(typ="spring", stiffness=1e8))
        ls.linien = [name]
        supports.lager_auf_netz(m)
        w = supports.tributary_lengths(m, ls.nodes)
        xs = [float(m.nodes[n, 0]) for n in ls.nodes]
        soll = [H * ((1 / 6 if x in (0.0, 1.0) else 1 / 3) if i % 2 == 0 else 2 / 3)
                for i, x in enumerate(xs)]
        ist = [w[n] for n in ls.nodes]
        check(f"{typ}: Linienlager-Einflusslaengen L/6, 2L/3, L/6, Summe L",
              len(ist) == 9 and abw(ist, soll, H) < 1e-12 and abs(sum(ist) - 1.0) < 1e-12,
              "[" + ", ".join(f"{x:.4f}" for x in ist) + "] m")
    m, name = koerper("hex8")
    ls = m.add_line_support([0, 1], name="Kante", uz=dict(typ="spring", stiffness=1e8))
    ls.linien = [name]
    supports.lager_auf_netz(m)
    w = supports.tributary_lengths(m, ls.nodes)
    ist = [w[n] for n in ls.nodes]
    check("hex8: Linienlager-Einflusslaengen wie bisher L/2 je Kante",
          abw(ist, [H / 2, H, H, H, H / 2], H) < 1e-15, str(np.round(ist, 4)))
    k = 2.0e9
    soll = Q / k
    for typ, ordnung, dreiecke in (("shell8", 2, False), ("shell6", 2, True), ("shell4", 1, False)):
        m, links, rechts = streifen(ordnung, dreiecke, feder=k)
        r = solver.solve_static(m)
        ux = r.u[links, 0]
        d = float(np.max(np.abs(ux - soll))) / soll
        ux_r = r.u[rechts, 0]
        d_r = float(np.max(np.abs(ux_r - soll - Q * LX / (E * T)))) / soll
        check(f"{typ}: federndes Linienlager, u_x = Q/k an jedem Knoten", d < 1e-8 and d_r < 1e-8,
              f"u_x {ux.min() * 1e6:.4f} .. {ux.max() * 1e6:.4f} µm, Soll {soll * 1e6:.4f} µm, "
              f"Abw {d:.1e} / {d_r:.1e}")


def main():
    for t in (test_gleichlast_auf_quadratischer_kante, test_trapez_und_teilstrecke,
              test_kantenintegral_ausser_mitte, test_kantentypen, test_patch_streifen,
              test_linienlager_quadratisch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
