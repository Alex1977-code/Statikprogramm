"""
Die Gegenseite einer Fuge ist die ganze Gegenflaeche, und auf einer gekruemmten
Fuge bleibt der Masterpunkt beim Knoten (06.11.2026).

Befund am Drehlager (Mittel, Fuge „Achse (Typ 3)“): die Liste der Gegenfacetten
war das Bild „naechste Gegenfacette je Slave-Schwerpunkt“ (fugen.py). Ist die
Gegenseite feiner als die Kontaktseite, fehlt der groesste Teil: 1 333 von 9 027
Dreiecken, an V16 13,2 % der Flaeche, 486 Knoten galten faelschlich als „neben der
Gegenflaeche“ - 177 statt 663 Bedingungen, rund 174 statt 30 kN je Punkt. Davon
unabhaengig stufte mortar.gewichte eine zu 99,98 % ueberdeckte Slave-Facette auf
einer gekruemmten Fuge als „teilweise“ ein (die Projektion der gekruemmten
Randkante in die Facettenebene laesst einen Streifen frei) und nahm Standard-
Formfunktionen: der Masterpunkt der Randknoten wanderte um L/3 = 23 mm, die
Kontaktkraefte trugen 34,7 kNm, die keinem Teil das Gleichgewicht halten.

P1 (zwei Wuerfel, Gegenseite feiner als die Kontaktseite): Liste, Bedingungen und
- gerechnet - Kraft, Weg und Gleichgewicht gegen die Handrechnung.
P2 (Mantel eines Halbzylinders, Slave-Band ueber die ganze Breite, Master anders
geteilt): Hebel, Einstufung, Stichprobe ueber den Parameterraum; eben bleibt alles.

Jeder Abschnitt nimmt die Kur am Schalter zurueck (fugen.GEGENSEITE_VOLL,
mortar.KRUEMMUNG_BEACHTEN) und belegt, dass die Pruefung dann fehlschlaegt.

Aufruf:  python -m tests.test_master_voll
"""
import contextlib
import copy
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from statik3d import ergebnisse as erg, fugen, mortar as mo, rechenverfahren as rv, solver  # noqa: E402
from statik3d.contact import ContactSystem, master_facets  # noqa: E402
from statik3d.model import DofBehaviour, Material, Model  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    from tests import pruefmatrix as pm  # noqa: E402
    from tests import test_fugen as tf  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:88s} {detail}")
    return bool(ok)


@contextlib.contextmanager
def ohne_kur(fuge=False, mortar=False):
    """Die Kur am Schalter zuruecknehmen (nur fuer die Ruecknahmeprobe)."""
    a, b = fugen.GEGENSEITE_VOLL, mo.KRUEMMUNG_BEACHTEN
    fugen.GEGENSEITE_VOLL = not fuge and a
    mo.KRUEMMUNG_BEACHTEN = not mortar and b
    try:
        yield
    finally:
        fugen.GEGENSEITE_VOLL, mo.KRUEMMUNG_BEACHTEN = a, b


# --------------------------------------------------------------------------
# P1: zwei Wuerfel, die Gegenseite feiner als die Kontaktseite
# --------------------------------------------------------------------------
def _p1(h_unten, h_oben):
    """Oben Slave, unten Master, jeder Wuerfel mit eigenen Flaechen und Linien. Nicht
    zwei_bloecke mit h_oben: dort liefert der freie Vernetzer mit fremden Randlinien
    ueberlappende Elemente (0,1/0,4: Rauminhalt 2,0052 statt 2 m³), und schon die
    homogene Loesung ist keine mehr. Rueckgabe (Modell, Protokoll)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    tf._kasten(m, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, "Unten", h=h_unten)
    tf._kasten(m, 0.0, 1.0, 0.0, 1.0, 1.0, 2.0, "Oben", h=h_oben)
    kb = m.add_kontaktbedingung("Fuge", flaechennamen=["Oben_B"], gegenflaechen=["Unten_D"],
                                koerpernamen=["Oben"],
                                behaviour={2: DofBehaviour("free", failure="zug")})
    log = []
    fugen.kontaktfuge_ausfuehren(m, kb, log)
    return m, log


def _flaeche(m, facetten) -> float:
    if not len(facetten):
        return 0.0
    P = np.asarray(m.nodes, float)[np.asarray([list(f)[:3] for f in facetten], int)]
    return float(0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1).sum())


def _bedingungen(m):
    log = []
    st = ContactSystem(m, sparse.identity(m.ndof, format="csr"), log)
    return st, sum(c.kind == "surface" for c in st.cons), log


#: (Kante unten, Kante oben, Bezeichnung): zwei Netzpaare; „8 Teilungen“ wie P2
P1_NETZE = ((0.1, 0.4, "Kontaktseite h 0,4"), (0.05, 0.125, "Kontaktseite 8 Teilungen, h 0,125"))


def test_p1_liste_und_bedingungen():
    for h_u, h_o, text in P1_NETZE:
        m, _log = _p1(h_u, h_o)
        cp = m.contact_pairs[-1]
        A_voll = _flaeche(m, [x[1] for x in fugen._dreiecke_der_fuge(m, [m.flaechen["Unten_D"]])])
        _st, n, log = _bedingungen(m)
        check(f"P1 {text}: die Master-Facetten decken die ganze Gegenfläche",
              abs(_flaeche(m, master_facets(m, cp)) - A_voll) < 1e-9,
              f"{_flaeche(m, master_facets(m, cp)):.4f} von {A_voll:.4f} m²")
        check(f"P1 {text}: jeder Slave-Knoten hat eine Bedingung",
              n == len(cp.slave_nodes), f"{n} von {len(cp.slave_nodes)}")
        check(f"P1 {text}: niemand meldet „neben der Gegenfläche“",
              not any("neben der Gegenfläche" in z for z in log), (log[-1] if log else "")[:150])
        with ohne_kur(fuge=True):
            m2, _l = _p1(h_u, h_o)
            cp2 = m2.contact_pairs[-1]
            A2 = _flaeche(m2, master_facets(m2, cp2))
            _s2, n2, _l2 = _bedingungen(m2)
        check(f"P1 {text}: Rücknahme - ohne die Kur fehlt Fläche, Knoten tragen nicht",
              A2 < 0.6 * A_voll and n2 < 0.6 * len(cp2.slave_nodes),
              f"{A2:.3f} m², {n2} von {len(cp2.slave_nodes)} Bedingungen")


def test_p1_umgekehrt_unveraendert():
    """Gegenseite grober als die Kontaktseite: die Liste war schon vollstaendig,
    die Kur setzt nichts dazu."""
    m, _log = _p1(0.4, 0.1)
    cp = m.contact_pairs[-1]
    roh = [tuple(int(x) for x in f) for f in cp.master_faces]
    check("P1 umgekehrt: dieselben Facetten in derselben Reihenfolge",
          master_facets(m, cp) == roh, f"{len(roh)} Facetten")


def test_nur_die_genannte_flaeche():
    """Die Kur schwaecht die Fuge nicht ab und weitet sie nicht aus: Unterteil mit
    zweigeteilter Oberseite (D1, D2), fein vernetzt, genannt ist nur D1; das grobe
    Oberteil liegt auf beiden. Ueber D2 traegt nichts, dort stimmt die Meldung."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.netz.ziellaenge = 0.1
    tf._zweigeteilt(m, "Unten", 0.1)
    tf._kasten(m, 0.0, 2.0, 0.0, 1.0, 1.0, 2.0, "Oben", h=0.4)
    kb = m.add_kontaktbedingung("Fuge", flaechennamen=["Oben_B"], gegenflaechen=["Unten_D1"],
                                koerpernamen=["Oben"], behaviour={2: DofBehaviour("free", failure="zug")})
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    cp = m.contact_pairs[-1]

    def facetten(fn):
        return {frozenset(int(x) for x in t[1]) for t in fugen._dreiecke_der_fuge(m, [m.flaechen[fn]])}
    d1, d2 = facetten("Unten_D1"), facetten("Unten_D2")
    alle = {frozenset(f) for f in master_facets(m, cp)}
    check("Nur D1 genannt: die Master-Facetten sind ganz D1", alle == d1,
          f"{len(alle & d1)} von {len(d1)} auf D1, {len(alle & d2)} auf D2")
    st, _n, log = _bedingungen(m)
    bed = {int(c.node) for c in st.cons if c.kind == "surface"}
    x = {int(s): float(m.nodes[int(s)][0]) for s in cp.slave_nodes}
    ueber_d1 = [s for s, xs in x.items() if xs <= 1.0 + 1e-9]
    ueber_d2 = [s for s, xs in x.items() if xs > 1.0 + 1e-9]
    check("… über D1 trägt jeder Knoten", ueber_d1 and all(s in bed for s in ueber_d1),
          f"{sum(s in bed for s in ueber_d1)} von {len(ueber_d1)}")
    check("… über D2 keiner, und die Meldung nennt genau diese",
          not any(s in bed for s in ueber_d2)
          and (not ueber_d2 or any(f"{len(ueber_d2)} liegen neben der Gegenfläche" in z for z in log)),
          f"{sum(s in bed for s in ueber_d2)} von {len(ueber_d2)}")


def test_p1_gerechnet():
    """Druck durch die Fuge: uniaxial, sigma_zz = -p ueberall, u_oben = -p L / E,
    Auflager und Summe der Normalkraefte p A, Gleichgewicht der Momente."""
    p, L, E = 100e6, 2.0, pm.E_ST
    for h_u, h_o, text in P1_NETZE:
        m, _log = _p1(h_u, h_o)
        P = np.asarray(m.nodes, float)
        V = sum(abs(np.linalg.det(P[e.nodes[1:4]] - P[e.nodes[0]])) / 6 for e in m.elements)
        check(f"P1 gerechnet {text}: das Netz ist heil (Rauminhalt 2 m³)", abs(V - 2.0) < 1e-9, f"{V:.6f} m³")
        unten, oben = pm.FugeDruck.lagerung(None, m, p)
        res = solver.solve_all(m, design=False).cases["LF1"]
        u = pm.u3(res, m)
        uo = float(u[oben, 2].mean())
        R = float(res.reactions[unten, 2].sum())
        Fn = sum(float(c.get("Fn", 0.0)) for c in (res.contact or []) if "node" in c)
        dsv = abs(pm.elementfehler(res, p))
        gg = res.info.get("gleichgewicht_global") or {}
        check(f"P1 gerechnet {text}: σ_v = p in jedem Element", dsv < 1.0, f"{dsv:.3f} N/mm² daneben")
        check(f"P1 gerechnet {text}: u_oben = -p L/E", abs(uo / (-p * L / E) - 1) < 0.01,
              f"{uo * 1e3:.4f} mm, Hand {-p * L / E * 1e3:.4f} mm")
        check(f"P1 gerechnet {text}: Auflager = p A", abs(R / p - 1) < 0.01, f"{R / 1e6:.3f} MN")
        check(f"P1 gerechnet {text}: ΣFn der Fuge = p A", abs(Fn / p - 1) < 0.01, f"{Fn / 1e6:.3f} MN")
        check(f"P1 gerechnet {text}: Gleichgewicht ΣF und ΣM", bool(gg.get("ok")),
              f"rel_F {gg.get('rel_F', 0):.1e}, rel_M {gg.get('rel_M', 0):.1e}")
        with ohne_kur(fuge=True):
            m2, _l = _p1(h_u, h_o)
            pm.FugeDruck.lagerung(None, m2, p)
            res2 = solver.solve_all(m2, design=False).cases["LF1"]
            d2 = abs(pm.elementfehler(res2, p))
        check(f"P1 gerechnet {text}: Rücknahme - ohne die Kur ist σ_v weit daneben", d2 > 10.0,
              f"{d2:.1f} N/mm² daneben")


def test_gespeichertes_modell():
    """Ein gespeichertes Modell bekommt die Kur ohne Zutun: die Datei bleibt, wie sie
    ist (Liste und Kennung), der Lauf sieht die ganze Flaeche, gleich ob vor oder nach
    dem Laden."""
    m, _log = _p1(0.1, 0.4)
    d = tempfile.mkdtemp(prefix="master_voll_")
    pfad = os.path.join(d, "alt.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    cp2 = m2.contact_pairs[-1]
    roh = copy.deepcopy(cp2.master_faces)
    k0 = erg.kennung(m2)
    A = _flaeche(m2, master_facets(m2, cp2))
    _st, n, _log2 = _bedingungen(m2)
    check("Gespeichertes Modell: geladen deckt die Gegenseite die ganze Fläche", abs(A - 1.0) < 1e-9, f"{A:.4f} m²")
    check("… und jeder Slave-Knoten hat eine Bedingung", n == len(cp2.slave_nodes), f"{n} von {len(cp2.slave_nodes)}")
    check("… die Liste im Modell bleibt, wie sie in der Datei steht", cp2.master_faces == roh, f"{len(roh)} Facetten")
    check("… die Kennung des Modells ändert sich nicht (Modell gilt nicht als geändert)",
          erg.kennung(m2) == k0)
    m3 = copy.deepcopy(m2)
    check("… eine Kopie des Modells (Arbeitsprozess) rechnet mit derselben Seite",
          master_facets(m3, m3.contact_pairs[-1]) == master_facets(m2, cp2))


def test_handgemachtes_paar_unveraendert():
    """Ein Paar ohne Kontaktbedingung nennt seine Facetten selbst: unveraendert."""
    from statik3d.model import ContactPair
    m = Model()
    m.add_material(Material.steel("S235"))
    g = {(i, j): int(m.add_node(0.1 * i, 0.1 * j, 0.0)) for i in range(4) for j in range(4)}
    master = [[g[i, j], g[i + 1, j], g[i + 1, j + 1]] for i in range(3) for j in range(3)][:2]
    cp = ContactPair("Hand", slave_nodes=[int(m.add_node(0.05, 0.05, 0.0))], master_faces=master, search_radius=0.05)
    m.contact_pairs.append(cp)
    check("Paar ohne Kontaktbedingung: genau seine Facetten",
          master_facets(m, cp) == [tuple(f) for f in master], f"{len(master)} Facetten")


# --------------------------------------------------------------------------
# P2: Mantel eines Halbzylinders, Slave-Band ueber die ganze Breite
# --------------------------------------------------------------------------
def _p2_netz(r, L, nw_s, nw_m, ny_m, eben=False, y_m=(0.0, 1.0)):
    """Slave: ein Band ueber die ganze Breite L, die Randreihen um eine halbe Teilung
    gegeneinander versetzt (schraege Facetten wie V30 an V29). Master: nw_m x ny_m,
    im Umfang etwas weiter als der Slave, damit nur die beiden y-Raender zaehlen.
    ``y_m``: axialer Bereich des Masters als Anteil von L."""
    ds = np.pi / nw_s
    ps = [(i * ds, 0.0) for i in range(nw_s + 1)] + [((i + 0.5) * ds, L) for i in range(nw_s)]
    ts = []
    for i in range(nw_s):
        ts.append((i, i + 1, nw_s + 1 + i))
        if i + 1 < nw_s:
            ts.append((i + 1, nw_s + 2 + i, nw_s + 1 + i))
    th = np.linspace(-0.025 * np.pi, 1.025 * np.pi, nw_m + 1)
    ys = L * np.linspace(y_m[0], y_m[1], ny_m + 1)
    pm_ = [(t, y) for t in th for y in ys]
    k = lambda i, j: i * (ny_m + 1) + j  # noqa: E731
    tm = []
    for i in range(nw_m):
        for j in range(ny_m):
            tm += [(k(i, j), k(i + 1, j), k(i + 1, j + 1)), (k(i, j), k(i + 1, j + 1), k(i, j + 1))]

    def d3(P):
        P = np.array(P, float)
        if eben:
            return np.column_stack([P[:, 0] * r, P[:, 1], np.zeros(len(P))])
        return np.column_stack([r * np.cos(P[:, 0]), P[:, 1], r * np.sin(P[:, 0])])

    Xs, Xm = d3(ps), d3(pm_)
    X = np.vstack([Xs, Xm])
    n = len(Xs)
    return X, [tuple(int(x) for x in t) for t in ts], [tuple(int(x) + n for x in t) for t in tm]


def _p2_auswerten(X, Ts, Tm, radius, r, eben=False):
    """Fuer die Knoten fern vom Umfangsrand: (Hebel max, axial max, Zahl rand, Zahl
    Knoten, groesste Abweichung der Gewichtssumme von 1, Ueberdeckung min)."""
    g = mo.gewichte(X, Ts, Tm, radius)
    h, a, rd, su, ue = [], [], 0, [], []
    for s, e in g.items():
        if e.D <= 0:
            continue
        w = (X[s, 0] / r) if eben else np.arctan2(X[s, 2], X[s, 0])
        if w < 0.15 * np.pi or w > 0.85 * np.pi:
            continue
        xm = sum(v / e.D * X[int(k)] for k, v in e.M.items())
        h.append(float(np.linalg.norm(X[s] - xm)))
        a.append(abs(float(X[s, 1] - xm[1])))
        rd += bool(e.rand)
        su.append(abs(sum(e.M.values()) / e.D - 1.0))
        ue.append(e.D / e.D_ganz)
    return max(h), max(a), rd, len(h), max(su), min(ue)


def test_p2_hebel():
    r, L = 0.298, 0.069
    for nw_s, nw_m in ((8, 13), (24, 37)):
        X, Ts, Tm = _p2_netz(r, L, nw_s, nw_m, 3)
        h, a, rd, n, su, ue = _p2_auswerten(X, Ts, Tm, 0.03, r)
        check(f"P2 Zylinder {nw_s} Teilungen: keine Facette als teilweise überdeckt eingestuft", rd == 0, f"rand {rd} von {n}")
        check(f"P2 Zylinder {nw_s} Teilungen: der Masterpunkt bleibt axial beim Knoten", a < 0.05 * L / 3,
              f"axial {a * 1e3:.3f} mm, L/3 = {L / 3 * 1e3:.1f} mm")
        check(f"P2 Zylinder {nw_s} Teilungen: die Gewichte summieren sich zu 1 (contact._mortar_einsetzen)",
              su <= 1e-9, f"{su:.1e}")
        with ohne_kur(mortar=True):
            _h, a0, rd0, n0, _su, _ue = _p2_auswerten(X, Ts, Tm, 0.03, r)
        check(f"P2 Zylinder {nw_s} Teilungen: Rücknahme - ohne die Kur wandert er um L/3",
              rd0 == n0 and a0 > 0.9 * L / 3, f"axial {a0 * 1e3:.2f} mm, rand {rd0} von {n0}")


def test_p2_eben_unveraendert():
    """Bei ebenen Flaechen aendert die Schranke nichts - bitgleich, auch am Rand der
    Ueberdeckung (das Gitter aus mortar.py)."""
    for nw_s, nw_m in ((8, 13), (24, 37)):
        X, Ts, Tm = _p2_netz(0.298, 0.069, nw_s, nw_m, 3, eben=True)
        a = mo.gewichte(X, Ts, Tm, 0.03)
        with ohne_kur(mortar=True):
            b = mo.gewichte(X, Ts, Tm, 0.03)
        gleich = all(a[j].D == b[j].D and a[j].M == b[j].M and a[j].rand == b[j].rand for j in a)
        check(f"P2 eben {nw_s} Teilungen: Gewichte bitgleich mit und ohne Schranke", gleich and set(a) == set(b))
        h, ax, rd, n, _su, _ue = _p2_auswerten(X, Ts, Tm, 0.03, 0.298, eben=True)
        check(f"P2 eben {nw_s} Teilungen: Hebel null, nichts teilweise", h < 1e-9 and rd == 0, f"{h:.1e} m, rand {rd} von {n}")
    # Gitter 3 x 3 auf [0, 1,2]^2 ueber 2 x 2 auf [0,1, 1,1]^2: echter Rand, eben
    g = lambda n, a, b: [(a + (b - a) * i / n, a + (b - a) * j / n, 0.0) for i in range(n + 1) for j in range(n + 1)]  # noqa: E731

    def tri(n, o):
        k = lambda i, j: o + i * (n + 1) + j  # noqa: E731
        return [t for i in range(n) for j in range(n)
                for t in ((k(i, j), k(i + 1, j), k(i + 1, j + 1)), (k(i, j), k(i + 1, j + 1), k(i, j + 1)))]
    X = np.array(g(3, 0.0, 1.2) + g(2, 0.1, 1.1), float)
    Ts, Tm = tri(3, 0), tri(2, 16)
    a = mo.gewichte(X, Ts, Tm, 0.1)
    with ohne_kur(mortar=True):
        b = mo.gewichte(X, Ts, Tm, 0.1)
    check("Ebener Rand der Überdeckung: bitgleich, weiter als Rand eingestuft",
          all(a[j].D == b[j].D and a[j].M == b[j].M and a[j].rand == b[j].rand for j in a)
          and any(e.rand for e in a.values()))


def test_p2_echter_rand_bleibt():
    """Die Schranke darf einen echten Rand nicht verschlucken: ueberdeckt der Master
    auf dem Zylinder nur drei Viertel der Breite, bleibt die Facette teilweise."""
    r, L = 0.298, 0.069
    for nw_s, nw_m in ((8, 13), (24, 37)):
        X, Ts, Tm = _p2_netz(r, L, nw_s, nw_m, 3, y_m=(0.0, 0.75))
        _h, _a, rd, n, su, ue = _p2_auswerten(X, Ts, Tm, 0.03, r)
        check(f"P2 Zylinder {nw_s} Teilungen, Master auf 3/4 der Breite: alle teilweise", rd == n and ue < 0.9,
              f"rand {rd} von {n}, Überdeckung bis {ue:.3f}")
        check(f"… {nw_s} Teilungen: die Gewichte summieren sich trotzdem zu 1", su <= 1e-9, f"{su:.1e}")


def test_p2_stichprobe():
    """Stichprobe ueber Radius, Teilungen, Masterreihen: keine Facette, die in Wahrheit
    ganz ueberdeckt ist, faellt unter die Schranke (CLAUDE.md: robust statt Glueckssache).
    Von 6 Teilungen am Halbkreis an, also Facetten bis 30 Grad (contact.KNICK: was
    staerker abknickt, ist eine Kante und keine gekruemmte Flaeche). Bei 4 Teilungen
    (45 Grad) fehlen bis 15 % der Facette; das bleibt ein Rand der Ueberdeckung."""
    schlecht, gesehen, hebel, kleinst = [], 0, 0.0, 1.0
    for r in (0.05, 0.298, 1.0):
        for L in (0.2 * r, 0.5 * r):
            for nw_s in (6, 8, 12, 24, 48):
                for f_m in (1.3, 1.62, 2.7):
                    for ny_m in (1, 3, 7):
                        nw_m = max(3, int(round(nw_s * f_m)))
                        X, Ts, Tm = _p2_netz(r, L, nw_s, nw_m, ny_m)
                        _h, a, rd, n, su, ue = _p2_auswerten(X, Ts, Tm, 0.1 * r + L, r)
                        gesehen += 1
                        hebel = max(hebel, a / L)
                        kleinst = min(kleinst, ue)
                        if rd or su > 1e-9:
                            schlecht.append((r, L, nw_s, nw_m, ny_m, rd, n, su))
    check(f"P2 Stichprobe {gesehen} Netze: alles ganz überdeckt, Gewichte summieren zu 1", not schlecht,
          f"{len(schlecht)} daneben, z. B. {schlecht[:3]}")
    check("… der axiale Hebel bleibt klein gegen L/3", hebel < 0.05, f"höchstens {hebel:.4f} L, ohne Kur 0,33 L")


# --------------------------------------------------------------------------
# Verfahrenstabelle: betroffen, nicht ungueltig
# --------------------------------------------------------------------------
def test_verfahren_betroffen():
    mk = rv.merkmal("gegenseite")
    check("Verfahrenstabelle: Fehlerkorrektur eingetragen", mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR,
          str(mk.titel if mk else ""))
    check("… der Stand ist der höchste der Tabelle",
          mk is not None and rv.VERFAHRENSSTAND == mk.wechsel[-1].stand == max(
              w.stand for x in rv.MERKMALE for w in x.wechsel), f"Stand {rv.VERFAHRENSSTAND}")
    m, _log = _p1(0.5, 0.25)
    pm.FugeDruck.lagerung(None, m, 1e6)
    check("… das Modell mit Fuge und Kontaktpaar hat das Merkmal", bool(mk and mk.betrifft(m)), mk.modellmerkmal if mk else "")
    ohne = tf.zwei_bloecke("gemeinsam", h=0.5)
    check("… ein Modell ohne Fuge nicht", not bool(mk and mk.betrifft(ohne)))
    an = solver.solve_all(m, design=False)
    d = tempfile.mkdtemp(prefix="master_voll_")
    p = os.path.join(d, "alt.ergebnisse")
    erg.schreiben(p, m, an)
    a2 = erg.lesen(p, m)
    check("Neu gerechnet: gültig, kein Status", not str(a2.info.get("verfahren_betroffen") or ""),
          str(a2.info.get("verfahren_betroffen") or ""))

    def stand4(inhalt):
        v = inhalt["verfahren"]
        v["stand"] = 4
        v["merkmale"].pop("gegenseite", None)
    with open(p, "rb") as fh:
        inhalt = erg._Leser(fh, m).load()
    stand4(inhalt)
    with open(p, "wb") as fh:
        erg._Schreiber(fh, m).dump(inhalt)
    a3 = erg.lesen(p, m)
    st = str(a3.info.get("verfahren_betroffen") or "")
    check("Ergebnis von Stand 4: Status „möglicherweise betroffen – neu rechnen“", st.startswith(rv.BETROFFEN), st[:140])
    check("… und nicht ungültig: der Lastfall bleibt geladen", "LF1" in a3.cases)


def main():
    tests = [test_p1_liste_und_bedingungen, test_p1_umgekehrt_unveraendert, test_nur_die_genannte_flaeche,
             test_p1_gerechnet,
             test_gespeichertes_modell, test_handgemachtes_paar_unveraendert,
             test_p2_hebel, test_p2_eben_unveraendert, test_p2_echter_rand_bleibt, test_p2_stichprobe,
             test_verfahren_betroffen]
    for t in tests:
        print(f"\n--- {t.__name__}")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
