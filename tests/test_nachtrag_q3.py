"""
Nachtrag zur Fehlerliste, Paket Q3: N01 - Trapez-, Teilstrecken- und kurze
Einzellasten auf Staeben mit Schubverformung (07.10.2026).

Ein Stab mit Schubflaechen rechnet seine Steifigkeit mit Schubverformung
(Timoshenko, phi = 12 EI/(G A_s L^2)). Die Ersatzknotenlasten einer Stablast
kamen bis zum 07.10.2026 aber aus den kubischen Hermite-Ansaetzen des
schubstarren Stabes (Bernoulli). Fuer eine gleichmaessige Last ueber das ganze
Element ist das dasselbe (qL/2 und qL^2/12 haengen nicht von phi ab), fuer
jede andere Verteilung nicht: ein Zwischenknoten aenderte die Verschiebung
(beim Teilen eines HEB 200 gemessen bis 2,0e-3 relativ, tests/test_stab_teilen),
und ein einzelnes Element wich von der Loesung mit Schubverformung ab (Kragarm
4 m aus einem Element, kurze Last 10 kN bei 1,3 m: HEB 200 5,9e-3, Rechteck
200 x 600 mm 9,2e-3 an der Spitze).

Geprueft wird gegen Referenzen ohne Programmcode: die Volleinspannkraefte aus
dem Kraftgroessenverfahren am Kragarm, die Durchbiegungen nach dem Arbeitssatz
(Biegung plus Schub, w = int M m/EI + int V v/(G A_s)), beides mit
Gauss-Integration je Teilstrecke. Dazu ein Element gegen 40 Elemente an den
gemeinsamen Knoten. Fuer Staebe ohne Schubflaechen, Fachwerkstaebe und
Gleichlasten ueber das ganze Element bleibt die Rechnung bitgleich.

Aufruf:  python -m tests.test_nachtrag_q3
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np

RESULTS = []
E, NU = 210e9, 0.3
G = E / (2.0 * (1.0 + NU))
L = 4.0
#: Gauss-Legendre mit 10 Punkten je Teilstrecke: exakt bis Grad 19, die
#: Integranden sind stueckweise Polynome hoechstens fuenften Grades
XG, WG = np.polynomial.legendre.leggauss(10)

#: Lasten (q1 bei a, q2 bei b, a, b) [N/m, m] auf einem 4-m-Stab
LASTEN = {
    "Gleichlast ganz": [(-10e3, -10e3, 0.0, L)],
    "Trapez ganz": [(-2e3, -12e3, 0.0, L)],
    "Dreieck ganz": [(0.0, -12e3, 0.0, L)],
    "Teilstrecke gleich 1,0-2,5 m": [(-8e3, -8e3, 1.0, 2.5)],
    "Teilstrecke trapez 0,5-3,2 m": [(-3e3, -15e3, 0.5, 3.2)],
    "Einzellast 10 kN bei 1,3 m (2 mm breit)": [(-5e6, -5e6, 1.299, 1.301)],
}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# ---------------------------------------------------------------------------
# Referenz ohne Programmcode
# ---------------------------------------------------------------------------
def _int(f, a, b, punkte=()):
    """Integral von f ueber [a, b], an den Knickstellen zerlegt."""
    knoten = sorted({float(a), float(b), *[float(p) for p in punkte if a < p < b]})
    s = 0.0
    for u, v in zip(knoten[:-1], knoten[1:]):
        x = 0.5 * (u + v) + 0.5 * (v - u) * XG
        s += 0.5 * (v - u) * sum(w * f(t) for w, t in zip(WG, x))
    return s


class _Last:
    """p(x) aus Abschnitten (q1, q2, a, b), Richtung beliebig (Vorzeichen in p)."""

    def __init__(self, lasten):
        self.lasten = list(lasten)
        self.knicke = sorted({x for *_q, a, b in self.lasten for x in (a, b)})

    def __call__(self, x):
        s = 0.0
        for q1, q2, a, b in self.lasten:
            if a <= x <= b:
                s += q1 + (q2 - q1) * (x - a) / (b - a)
        return s

    def M(self, x):
        """Moment der Last rechts von x um x (Kragarm, frei bei L)."""
        return _int(lambda s: self(s) * (s - x), x, L, self.knicke)

    def V(self, x):
        return _int(self, x, L, self.knicke)


def _kragarm(p: _Last, EI, GAs, xi):
    """Kragarm (eingespannt bei 0): Durchbiegung bei xi und Querschnitts-
    verdrehung bei L unter p, Arbeitssatz mit Einheitslast bzw. -moment."""
    k = p.knicke + [xi]
    w = _int(lambda x: p.M(x) * (xi - x), 0.0, xi, k) / EI
    if GAs:
        w += _int(p.V, 0.0, xi, k) / GAs
    th = _int(p.M, 0.0, L, p.knicke) / EI
    return w, th


def _nachgiebigkeit(EI, GAs):
    """Spitze des Kragarms unter Einheitskraft und Einheitsmoment."""
    return np.array([[L ** 3 / (3 * EI) + (L / GAs if GAs else 0.0), L ** 2 / (2 * EI)],
                     [L ** 2 / (2 * EI), L / EI]])


def volleinspannung(lasten, EI, GAs):
    """Ersatzknotenlasten [F1, M1, F2, M2] des beidseitig eingespannten
    Stabes (= minus Einspannkraefte), Ebene mit Drehung = Neigung der
    Biegelinie: Kraftgroessenverfahren am Kragarm, Ueberzaehlige am Ende L."""
    p = _Last(lasten)
    w_L, th_L = _kragarm(p, EI, GAs, L)
    R2, M2 = np.linalg.solve(_nachgiebigkeit(EI, GAs), [-w_L, -th_L])
    P = _int(p, 0.0, L, p.knicke)
    Px = _int(lambda x: p(x) * x, 0.0, L, p.knicke)
    R1 = -P - R2
    M1 = -M2 - R2 * L - Px
    return -np.array([R1, M1, R2, M2])


def durchbiegung(lager, lasten, EI, GAs, xs):
    """Durchbiegung an den Stellen xs in Lastrichtung, Biegung plus Schub.

    'krag'        eingespannt bei 0, frei bei L;
    'einfeld'     gelenkig bei 0 und L;
    'gestuetzt'   eingespannt bei 0, gelenkig gestuetzt bei L.
    Rueckgabe (w(xs), Zusatz): Zusatz ist beim Kragarm die Verdrehung bei L,
    beim Einfeldtraeger die Verdrehung bei 0, beim gestuetzten Traeger die
    Auflagerkraft bei L (in Lastrichtung positiv)."""
    p = _Last(lasten)
    if lager == "einfeld":
        R_L = -_int(lambda s: p(s) * s, 0.0, L, p.knicke) / L
        def M(x):
            return p.M(x) + R_L * (L - x)
        def V(x):
            return p.V(x) + R_L
        w = []
        for xi in xs:
            if xi <= 0.0 or xi >= L:
                w.append(0.0)
                continue
            k = p.knicke + [xi]
            mb = lambda x, xi=xi: -xi / L * (L - x) + ((xi - x) if x < xi else 0.0)
            vb = lambda x, xi=xi: -xi / L + (1.0 if x < xi else 0.0)
            wi = _int(lambda x: M(x) * mb(x), 0.0, L, k) / EI
            if GAs:
                wi += _int(lambda x: V(x) * vb(x), 0.0, L, k) / GAs
            w.append(wi)
        # Verdrehung bei 0 (Sinn der Neigung dw/dx) mit Einheitsmoment am
        # Lager 0: Auflager bei L -1/L, also m = -(1 - x/L), v = -1/L
        th0 = _int(lambda x: M(x) * -(1.0 - x / L), 0.0, L, p.knicke) / EI
        if GAs:
            th0 += _int(lambda x: V(x) * (-1.0 / L), 0.0, L, p.knicke) / GAs
        return np.array(w), th0
    w = np.array([_kragarm(p, EI, GAs, xi)[0] for xi in xs])
    if lager == "krag":
        return w, _kragarm(p, EI, GAs, L)[1]
    # gestuetzt: Ueberzaehlige R bei L aus w(L) = 0
    w_L = _kragarm(p, EI, GAs, L)[0]
    R = -w_L / _nachgiebigkeit(EI, GAs)[0, 0]
    w1 = np.array([_int(lambda x: (L - x) * (xi - x), 0.0, xi, [xi]) / EI + (xi / GAs if GAs else 0.0)
                   for xi in xs])
    return w + R * w1, R


# ---------------------------------------------------------------------------
# Programm
# ---------------------------------------------------------------------------
def _querschnitte():
    from statik3d.model import Section
    rechteck = Section.rectangle("R 200x600", 0.2, 0.6)
    heb = Section.from_profile("HEB 200")
    # schubweich: phi um 1 bei 4 m (Iy, Iz mit A_s so, dass phi_z 0,4 und phi_y 1,5)
    weich = Section("weich", A=0.02, Iy=3.0e-4, Iz=8.0e-5, It=1e-6,
                    Asy=12 * E * 8.0e-5 / (G * 0.4 * L ** 2),
                    Asz=12 * E * 3.0e-4 / (G * 1.5 * L ** 2))
    return [rechteck, heb, weich]


def _modell(sec, n, lasten, ebene, lager, typ="beam"):
    """Stab entlang x aus n gleichen Elementen; die Abschnitte werden je
    Element zerlegt (ganzes Element: Trapezformel, sonst Abschnitt)."""
    from statik3d.model import Model, Material
    m = Model("N01")
    m.add_material(Material("S", E, NU, 7850.0, fy=235e6))
    m.add_section(sec)
    for k in range(n + 1):
        m.add_node(L * k / n, 0.0, 0.0)
    if lager == "einfeld":
        m.fix(0, [0, 1, 2, 3])
        m.fix(n, [1, 2])
    elif lager == "gestuetzt":
        m.fix(0, "all")
        m.fix(n, [1, 2])
    else:
        m.fix(0, "all")
    for k in range(n):
        m.add_element(typ, [k, k + 1], "S", sec.name)
    h = L / n
    for q1, q2, a, b in lasten:
        for k in range(n):
            x0, x1 = k * h, (k + 1) * h
            u, v = max(a, x0), min(b, x1)
            if v <= u:
                continue
            qu = q1 + (q2 - q1) * (u - a) / (b - a)
            qv = q1 + (q2 - q1) * (v - a) / (b - a)
            aa = 0.0 if u - x0 < 1e-12 else u - x0
            bb = None if x1 - v < 1e-12 else v - x0
            q2v = [0.0, 0.0, qv] if ebene == "xz" else [0.0, qv, 0.0]
            if ebene == "xz":
                m.load_beam(k, qz=qu, q2=q2v, system="local", a=aa, b=bb)
            else:
                m.load_beam(k, qy=qu, q2=q2v, system="local", a=aa, b=bb)
    return m


def _steifen(sec, ebene):
    """(EI, G A_s, phi) der Ebene: x-z biegt um y (Iy, A_sz), x-y um z (Iz, A_sy)."""
    I, As = (sec.Iy, sec.Asz) if ebene == "xz" else (sec.Iz, sec.Asy)
    return E * I, G * As, (12 * E * I / (G * As * L ** 2) if As > 0 else 0.0)


def _rechnen(m):
    from statik3d import solver
    r = solver.solve_static(m)
    return np.asarray(r.u, float).reshape(-1, 6), np.asarray(r.reactions, float).reshape(-1, 6)


# ---------------------------------------------------------------------------
# 1. Ersatzknotenlasten eines Elements gegen das Kraftgroessenverfahren
# ---------------------------------------------------------------------------
def test_volleinspannkraefte():
    from statik3d import assemble as asm
    for sec in _querschnitte():
        for ebene in ("xy", "xz"):
            EI, GAs, phi = _steifen(sec, ebene)
            schlecht = []
            for name, lasten in LASTEN.items():
                m = _modell(sec, 1, lasten, ebene, "krag")
                f = asm.element_equivalent_loads(m, m.case())[0]
                # x-z: die Drehung um y ist minus die Neigung von w
                ist = (np.array([f[1], f[5], f[7], f[11]]) if ebene == "xy"
                       else np.array([f[2], -f[4], f[8], -f[10]]))
                soll = volleinspannung(lasten, EI, GAs)
                s = np.array([1.0, 1.0 / L, 1.0, 1.0 / L])           # Momente auf Kraefte bezogen
                d = float(np.max(np.abs((ist - soll) * s)) / np.max(np.abs(soll * s)))
                schlecht.append((d, name))
            d, name = max(schlecht)
            check(f"Ersatzknotenlasten {sec.name}, Ebene {ebene} (phi {phi:.3f}) = Kraftgrößenverfahren",
                  d < 1e-10, f"größte Abweichung {d:.1e} ({name})")


# ---------------------------------------------------------------------------
# 2. Verschiebungen: ein Element gegen Referenz und gegen 40 Elemente
# ---------------------------------------------------------------------------
def test_ein_element_gegen_referenz_und_fein():
    n_fein = 40
    xs = np.linspace(0.0, L, n_fein + 1)
    for sec in _querschnitte():
        for ebene in ("xy", "xz"):
            EI, GAs, phi = _steifen(sec, ebene)
            k_w = 1 if ebene == "xy" else 2                 # uy bzw. uz
            k_r = 5 if ebene == "xy" else 4                 # rz bzw. ry
            vz = 1.0 if ebene == "xy" else -1.0             # Drehung = vz * Neigung
            for lager in ("krag", "einfeld", "gestuetzt"):
                d_ref1 = d_ref_fein = d_fein = 0.0
                wo = ["", "", ""]
                for name, lasten in LASTEN.items():
                    w_ref, zus = durchbiegung(lager, lasten, EI, GAs, xs)
                    s = float(np.max(np.abs(w_ref)))
                    U1, R1 = _rechnen(_modell(sec, 1, lasten, ebene, lager))
                    UF, RF = _rechnen(_modell(sec, n_fein, lasten, ebene, lager))
                    if lager == "krag":
                        # Spitze: Durchbiegung und Verdrehung
                        a1 = max(abs(U1[1, k_w] - w_ref[-1]) / s,
                                 abs(U1[1, k_r] - vz * zus) / abs(zus))
                        af = max(abs(UF[-1, k_w] - U1[1, k_w]) / s,
                                 abs(UF[-1, k_r] - U1[1, k_r]) / abs(zus))
                    elif lager == "einfeld":
                        a1 = abs(U1[0, k_r] - vz * zus) / abs(zus)
                        af = abs(UF[0, k_r] - U1[0, k_r]) / abs(zus)
                    else:
                        # Auflagerkraft bei L (Reaktion = Kraft des Lagers auf den Stab)
                        a1 = abs(R1[1, k_w] - zus) / abs(zus)
                        af = max(abs(RF[-1, k_w] - R1[1, k_w]) / abs(zus),
                                 float(np.max(np.abs(RF[0] - R1[0]))) / float(np.max(np.abs(RF[0]))))
                    ar = float(np.max(np.abs(UF[:, k_w] - w_ref))) / s
                    for i, (wert, alt) in enumerate(((a1, d_ref1), (ar, d_ref_fein), (af, d_fein))):
                        if wert > alt:
                            wo[i] = name
                    d_ref1, d_ref_fein, d_fein = max(d_ref1, a1), max(d_ref_fein, ar), max(d_fein, af)
                check(f"{sec.name}, {ebene}, {lager}: 1 Element = Referenz (Biegung + Schub)",
                      d_ref1 < 1e-9, f"{d_ref1:.1e} ({wo[0]}), phi {phi:.3f}")
                check(f"{sec.name}, {ebene}, {lager}: 40 Elemente = Referenz an allen Knoten",
                      d_ref_fein < 1e-9, f"{d_ref_fein:.1e} ({wo[1]})")
                check(f"{sec.name}, {ebene}, {lager}: 1 Element = 40 Elemente am gemeinsamen Knoten",
                      d_fein < 1e-9, f"{d_fein:.1e} ({wo[2]})")


# ---------------------------------------------------------------------------
# 3. Bernoulli, Fachwerk und Gleichlast bleiben bitgleich
# ---------------------------------------------------------------------------
def _trapez_bis_0710(q1, q2, L_):
    """assemble.trapezoid_fixed_end_forces am Stand 3f7b670 (wortgleich)."""
    q1 = np.asarray(q1, float)
    q2 = np.asarray(q2, float)
    f = np.zeros(12)
    f[0] += L_ * (2 * q1[0] + q2[0]) / 6.0
    f[6] += L_ * (q1[0] + 2 * q2[0]) / 6.0
    f[1] += L_ * (7 * q1[1] + 3 * q2[1]) / 20.0
    f[7] += L_ * (3 * q1[1] + 7 * q2[1]) / 20.0
    f[5] += L_ ** 2 * (3 * q1[1] + 2 * q2[1]) / 60.0
    f[11] += -L_ ** 2 * (2 * q1[1] + 3 * q2[1]) / 60.0
    f[2] += L_ * (7 * q1[2] + 3 * q2[2]) / 20.0
    f[8] += L_ * (3 * q1[2] + 7 * q2[2]) / 20.0
    f[4] += -L_ ** 2 * (3 * q1[2] + 2 * q2[2]) / 60.0
    f[10] += L_ ** 2 * (2 * q1[2] + 3 * q2[2]) / 60.0
    return f


def _abschnitt_bis_0710(q1, q2, a, b, L_):
    """assemble.partial_trapezoid_fixed_end_forces am Stand 3f7b670 (wortgleich)."""
    q1 = np.asarray(q1, float)
    q2 = np.asarray(q2, float)
    a = max(0.0, float(a))
    b = L_ if b is None else min(float(b), L_)
    f = np.zeros(12)
    if b <= a or L_ <= 0:
        return f
    xg, wg = np.polynomial.legendre.leggauss(4)
    for xi_g, w in zip(xg, wg):
        x = 0.5 * (a + b) + 0.5 * (b - a) * xi_g
        dw = 0.5 * (b - a) * w
        t = (x - a) / (b - a)
        q = (1.0 - t) * q1 + t * q2
        xi = x / L_
        n1, n7 = 1.0 - xi, xi
        h1 = 1.0 - 3.0 * xi ** 2 + 2.0 * xi ** 3
        h2 = L_ * (xi - 2.0 * xi ** 2 + xi ** 3)
        h3 = 3.0 * xi ** 2 - 2.0 * xi ** 3
        h4 = L_ * (-xi ** 2 + xi ** 3)
        f[0] += dw * n1 * q[0]
        f[6] += dw * n7 * q[0]
        f[1] += dw * h1 * q[1]
        f[5] += dw * h2 * q[1]
        f[7] += dw * h3 * q[1]
        f[11] += dw * h4 * q[1]
        f[2] += dw * h1 * q[2]
        f[4] += -dw * h2 * q[2]
        f[8] += dw * h3 * q[2]
        f[10] += -dw * h4 * q[2]
    return f


def test_bitgleich():
    from statik3d import assemble as asm
    from statik3d.model import Model, Material, Section
    rng = np.random.default_rng(7)
    faelle = []
    for _k in range(40):
        q1 = rng.uniform(-5e3, 5e3, 3)
        q2 = rng.uniform(-5e3, 5e3, 3)
        a, b = sorted(rng.uniform(0.0, L, 2))
        faelle.append((q1, q2, a, b))

    def lasten_von(typ, sec, gleich=False):
        m = Model("bit")
        m.add_material(Material("S", E, NU, 7850.0, fy=235e6))
        m.add_section(sec)
        # schraeg, damit globale Lasten alle drei lokalen Richtungen treffen
        m.add_node(0.0, 0.0, 0.0)
        m.add_node(3.1, 1.7, 1.2)
        m.add_element(typ, [0, 1], "S", sec.name, roll=0.3)
        Le = m.element_length(0)
        soll = []
        for q1, q2, a, b in faelle:
            m.load_beam(0, *q1, system="global", q2=None if gleich else q2)
            ql1, ql2 = asm.beam_load_local(m, m.elements[0], m.case().beam_loads[-1])
            soll.append(_trapez_bis_0710(ql1, ql2, Le))
            if not gleich:
                m.load_beam(0, *q1, system="local", q2=q2, a=a * Le / L, b=b * Le / L)
                bl = m.case().beam_loads[-1]
                soll.append(_abschnitt_bis_0710(np.asarray(bl.q, float), np.asarray(bl.q2, float),
                                                bl.a, bl.b, Le))
        ist = []
        lc = m.case()
        alle = list(lc.beam_loads)
        for bl in alle:
            lc.beam_loads = [bl]
            ist.append(asm.element_equivalent_loads(m, lc)[0])
        lc.beam_loads = alle
        return np.array(ist), np.array(soll)

    ohne = Section("ohne Schub", A=0.02, Iy=3e-4, Iz=8e-5, It=1e-6)
    mit = Section("mit Schub", A=0.02, Iy=3e-4, Iz=8e-5, It=1e-6, Asy=0.004, Asz=0.006)
    ist, soll = lasten_von("beam", ohne)
    check("Stab ohne Schubflächen: Ersatzknotenlasten bitgleich zu den Formeln bis 07.10.2026",
          np.array_equal(ist, soll), f"{len(ist)} Lasten, max |Δ| {np.abs(ist - soll).max():.1e}")
    ist, soll = lasten_von("truss", mit)
    check("Fachwerkstab mit Schubflächen-Querschnitt: bitgleich",
          np.array_equal(ist, soll), f"{len(ist)} Lasten, max |Δ| {np.abs(ist - soll).max():.1e}")
    ist, soll = lasten_von("beam", mit, gleich=True)
    check("Stab mit Schubflächen, Gleichlast über das ganze Element: bitgleich",
          np.array_equal(ist, soll), f"{len(ist)} Lasten, max |Δ| {np.abs(ist - soll).max():.1e}")
    ist, soll = lasten_von("beam", mit)
    d = float(np.abs(ist - soll).max())
    check("… mit Trapez- und Abschnittslasten ändern sich die Ersatzknotenlasten (Gegenprobe)",
          d > 0.0, f"max |Δ| {d:.3e} N bzw. Nm")
    # Summe der Kraefte und Moment um den Anfang bleiben: die Korrektur ist ein
    # Gleichgewichtssystem (Auflagersumme unveraendert)
    Le = float(np.linalg.norm([3.1, 1.7, 1.2]))
    df = ist - soll
    kraft = np.abs(df[:, [1, 2]] + df[:, [7, 8]]).max()
    moment = max(np.abs(df[:, 5] + df[:, 11] + df[:, 7] * Le).max(),
                 np.abs(df[:, 4] + df[:, 10] - df[:, 8] * Le).max())
    check("… die Änderung ist im Gleichgewicht (Summe Kräfte und Momente 0)",
          kraft < 1e-9 and moment < 1e-9, f"Kräfte {kraft:.1e} N, Momente {moment:.1e} Nm")


# ---------------------------------------------------------------------------
# 4. Theorie II. und III. Ordnung nehmen dieselben Ersatzknotenlasten
# ---------------------------------------------------------------------------
def test_theorie_hoeherer_ordnung():
    """Bei verschwindender Normalkraft rechnen Theorie II und III wie
    Theorie I: am Kragarm aus einem Element mit Trapezlast (ohne Normalkraft)
    muss die Spitze dann die Referenz mit Schubverformung treffen."""
    from statik3d import theorie2, theorie3
    from statik3d.model import Section
    sec = Section.rectangle("R 200x600", 0.2, 0.6)
    lasten = LASTEN["Teilstrecke trapez 0,5-3,2 m"]
    EI, GAs, _phi = _steifen(sec, "xz")
    w_ref, _ = durchbiegung("krag", lasten, EI, GAs, [L])
    m = _modell(sec, 1, lasten, "xz", "krag")
    lf = next(iter(m.load_cases))
    r2, _i2 = theorie2.solve_theorie2(m, {lf: 1.0}, "T2", imperfektionen=False)
    u2 = np.asarray(r2.u, float).reshape(-1, 6)[1, 2]
    r3, _i3 = theorie3.solve_theorie3(m, {lf: 1.0}, "T3", imperfektionen=False, schritte=2)
    u3 = np.asarray(r3.u, float).reshape(-1, 6)[1, 2]
    d2 = abs(u2 - w_ref[0]) / abs(w_ref[0])
    d3 = abs(u3 - w_ref[0]) / abs(w_ref[0])
    check("Theorie II, ein Element, Teil-Trapezlast: Spitze = Referenz mit Schub",
          d2 < 1e-9, f"{d2:.1e}")
    # Theorie III rechnet geometrisch nichtlinear: die Spitze wandert um
    # 0,27 mm von 4 m; die Laengsverkuerzung bleibt von zweiter Ordnung
    check("Theorie III, ein Element, Teil-Trapezlast: Spitze = Referenz mit Schub (1e-6)",
          d3 < 1e-6, f"{d3:.1e}")


# ---------------------------------------------------------------------------
# 5. Handbuch
# ---------------------------------------------------------------------------
def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("* Streckenlasten auf Stäben, global oder lokal", "Theoriehandbuch.md")
    check("Theoriehandbuch: Ansätze mit Schubverformung, Stand bis 07.10.2026",
          "Schubverformung" in a and "φ/(1+φ)" in a and "Bis zum 07.10.2026" in a
          and "Bernoulli" in a, a[:120])
    b = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Benutzerhandbuch (Teilen): gilt seit 07.10.2026 auch mit Schubflächen",
          "Seit dem 07.10.2026 gilt das auch für Stäbe mit Schubflächen" in b
          and "Bis zum 07.10.2026" in b and "2·10⁻³" in b, b[-200:])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_volleinspannkraefte, test_ein_element_gegen_referenz_und_fein,
              test_bitgleich, test_theorie_hoeherer_ordnung, test_handbuch):
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
    sys.stdout.flush()
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
