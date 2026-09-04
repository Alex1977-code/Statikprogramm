"""
Freier 3D-Vernetzer: Pruefung an geschlossen rechenbaren Koerpern.

Ein Netz laesst sich nicht "ungefaehr" pruefen. Darum wird hier alles gegen
Werte gehalten, die in einer Zeile nachzurechnen sind:

* **Volumen** - die Summe der Tetraedervolumen gegen das Volumen der Huelle
  aus dem Gaussschen Satz und gegen die Formel des Koerpers.
* **Dichtheit** - jede Kante der Huelle in genau zwei Dreiecken.
* **Punkt im Koerper** - die schnelle Strahlenzaehlung gegen die
  verallgemeinerte Windungszahl, zwei voellig verschiedene Wege.
* **Rechnung** - ein Zugstab: die volumengewichtete Mittelspannung muss nach
  dem Gleichgewichtssatz genau N/A sein, die Verlaengerung N L /(E A).
* **Einspringende Ecke** - der L-Koerper, an dem eine Delaunay-Zerlegung ohne
  Randnachfuehrung den Innenwinkel zuschuettet.
* **Bohrung** - eine Platte mit Loch: das Loch muss ausgespart bleiben.
* **Zylinder und Buchse** - krumme Randflaechen ueber ihre Kontrollpunkte.
* **Gemeinsame Flaeche** - zwei Koerper mit derselben Randflaeche muessen
  dort dieselben Knoten bekommen, sonst zerfaellt das Modell.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                   # noqa: E402
from statik3d import mesher3d as M3                           # noqa: E402
from statik3d.model import Model, Material                    # noqa: E402
from statik3d.elements import solid as SO                     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:58s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {abw:.4f} %")


# --------------------------------------------------------------------------
# Baukasten: Prisma ueber einem ebenen Umriss (mit Loechern), Zylinder, Buchse
# --------------------------------------------------------------------------
def neues_modell() -> Model:
    m = Model()
    m.add_material(Material.steel("S235"))
    return m


class Bauer:
    """Legt Linien und Flaechen an und zaehlt die Namen selbst durch."""

    def __init__(self, model: Model):
        self.m = model
        self.i = 0

    def linie(self, a, b, typ="polyline", **kw):
        self.i += 1
        name = f"L{self.i}"
        self.m.add_line(name, [a, b], typ, **kw)
        return name


def prisma(m: Model, ringe, hoehe: float, name: str = "V1"):
    """Prisma ueber einem ebenen Umriss; ringe[0] aussen, ringe[1:] Loecher."""
    b = Bauer(m)
    unten_r, oben_r, senkr = [], [], []
    for R in ringe:
        R = np.asarray(R, float)
        i0 = m.nn
        m.add_nodes(np.vstack([np.column_stack([R, np.zeros(len(R))]),
                               np.column_stack([R, np.full(len(R), hoehe)])]))
        n = len(R)
        unten_r.append([b.linie(i0 + i, i0 + (i + 1) % n) for i in range(n)])
        oben_r.append([b.linie(i0 + n + i, i0 + n + (i + 1) % n) for i in range(n)])
        senkr.append([b.linie(i0 + i, i0 + n + i) for i in range(n)])
    flaechen = []
    for k, R in enumerate(ringe):
        n = len(R)
        for i in range(n):
            nm = f"M{len(flaechen) + 1}"
            m.add_flaeche(nm, [unten_r[k][i], senkr[k][(i + 1) % n],
                               oben_r[k][i], senkr[k][i]], material="S235")
            flaechen.append(nm)
    m.add_flaeche("Boden", unten_r[0], material="S235", oeffnungen=unten_r[1:])
    m.add_flaeche("Deckel", oben_r[0], material="S235", oeffnungen=oben_r[1:])
    flaechen += ["Boden", "Deckel"]
    return m.add_koerper(name, flaechen, material="S235")


def kreis_punkte(r, n, mx=0.0, my=0.0, umgekehrt=False):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if umgekehrt:
        t = -t
    return np.column_stack([mx + r * np.cos(t), my + r * np.sin(t)])


def buchse(m: Model, ra: float, ri: float, hoehe: float, name: str = "V1"):
    """Zylinder oder Buchse - Kreise aus zwei Halbboegen wie in RFEM."""
    flaechen = []
    ringe = []
    for tag, r in (("A", ra), ("I", ri)):
        if r <= 0:
            continue
        satz = []
        for z, marke in ((0.0, "U"), (hoehe, "O")):
            a = m.add_node(-r, 0, z)
            b = m.add_node(r, 0, z)
            l1, l2 = f"{tag}{marke}1", f"{tag}{marke}2"
            m.add_line(l1, [a, b], "arc", punkte=[(-r, 0, z), (0, r, z), (r, 0, z)])
            m.add_line(l2, [b, a], "arc", punkte=[(r, 0, z), (0, -r, z), (-r, 0, z)])
            satz.append((a, b, l1, l2))
        (au, bu, u1, u2), (ao, bo, o1, o2) = satz
        v1, v2 = f"{tag}V1", f"{tag}V2"
        m.add_line(v1, [au, ao])
        m.add_line(v2, [bu, bo])
        m.add_flaeche(f"Mantel{tag}1", [u1, v2, o1, v1], material="S235")
        m.add_flaeche(f"Mantel{tag}2", [u2, v1, o2, v2], material="S235")
        flaechen += [f"Mantel{tag}1", f"Mantel{tag}2"]
        ringe.append(([u1, u2], [o1, o2]))
    loch_u = [ringe[1][0]] if len(ringe) > 1 else []
    loch_o = [ringe[1][1]] if len(ringe) > 1 else []
    m.add_flaeche("Boden", ringe[0][0], material="S235", oeffnungen=loch_u)
    m.add_flaeche("Deckel", ringe[0][1], material="S235", oeffnungen=loch_o)
    flaechen += ["Boden", "Deckel"]
    return m.add_koerper(name, flaechen, material="S235")


def _umfangsabschnitte(m: Model, koerper, h: float, linie: str) -> int:
    """Wieviele Abschnitte der Vernetzer dieser Linie gibt."""
    flaechen = [m.flaechen[x] for x in koerper.flaechen]
    return int(M3.Linienteilung(m, flaechen, h).n.get(linie, 1))


def netzvolumen(m: Model, els) -> float:
    return float(sum(abs(SO.solid_volume(m.elements[i].typ,
                                         m.nodes[[int(x) for x in m.elements[i].nodes]]))
                     for i in els))


# --------------------------------------------------------------------------
# 1) Die beiden Punkt-im-Koerper-Wege muessen dasselbe sagen
# --------------------------------------------------------------------------
def test_punkt_im_koerper():
    m = neues_modell()
    L = [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)]
    k = prisma(m, [L], 1.0)
    P, T, bericht = M3.randschale(m, k, 0.5)
    check("Randhülle ist dicht (jede Kante in zwei Dreiecken)",
          bericht["offen"] == 0, f"{bericht['offen']} offene Kanten")
    check("Randhülle ist ein Stück", bericht["teile"] == 1, str(bericht["teile"]))
    close("Hüllvolumen (Gaußscher Satz)", bericht["volumen"], 5.0, 1e-9, " m^3")

    rng = np.random.default_rng(7)
    Q = rng.uniform([-0.5, -0.5, -0.5], [3.5, 3.5, 1.5], size=(2000, 3))
    strahl = M3.innen(Q, P, T)
    windung = M3.windungszahl(Q, P, T) > 0.5
    check("Strahlenzählung und Windungszahl stimmen überein",
          bool(np.array_equal(strahl, windung)),
          f"{int((strahl != windung).sum())} Abweichungen von {len(Q)}")

    # Der L-Umriss ist von Hand nachzurechnen
    drin = ((Q[:, 2] > 0) & (Q[:, 2] < 1)
            & (((Q[:, 0] > 0) & (Q[:, 0] < 3) & (Q[:, 1] > 0) & (Q[:, 1] < 1))
               | ((Q[:, 0] > 0) & (Q[:, 0] < 1) & (Q[:, 1] > 0) & (Q[:, 1] < 3))))
    check("und beide treffen den L-Umriss", bool(np.array_equal(strahl, drin)),
          f"{int((strahl != drin).sum())} Abweichungen")


# --------------------------------------------------------------------------
# 2) Quader: Volumen exakt, Güte brauchbar, Netzrand auf der Hülle
# --------------------------------------------------------------------------
def test_quader():
    zahl = {}
    for h in (0.25, 0.125):
        m = neues_modell()
        k = prisma(m, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
        m.netz.ziellaenge = h
        log = []
        els = M3.mesh_koerper_frei(m, k, log=log)
        zahl[h] = len(els)
        check(f"Quader h={h}: vernetzt", bool(els), f"{len(els)} Tetraeder")
        check(f"Quader h={h}: nur Tetraeder",
              all(m.elements[i].typ == "tet4" for i in els))
        close(f"Quader h={h}: Netzvolumen", netzvolumen(m, els), 1.0, 1e-9, " m^3")
        q = M3.guete(m.nodes, np.array([[int(x) for x in m.elements[i].nodes]
                                        for i in els]))
        check(f"Quader h={h}: kein entartetes Element", float(q.min()) > 0.02,
              f"Güte min {q.min():.3f}, Mittel {q.mean():.3f}")
        check(f"Quader h={h}: im Mittel gut geformt", float(q.mean()) > 0.7,
              f"Mittel {q.mean():.3f}")
        # Die mittlere Kantenlaenge muss zur Vorgabe passen
        TET = np.array([[int(x) for x in m.elements[i].nodes] for i in els])
        L = np.mean([np.linalg.norm(m.nodes[TET[:, a]] - m.nodes[TET[:, b]], axis=1).mean()
                     for a, b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))])
        check(f"Quader h={h}: mittlere Kantenlänge nahe der Vorgabe",
              0.6 * h <= L <= 1.2 * h, f"{L * 1e3:.1f} mm statt {h * 1e3:.0f} mm")
    check("halbe Kantenlänge gibt rund achtmal so viele Elemente",
          4 * zahl[0.25] < zahl[0.125] < 16 * zahl[0.25],
          f"{zahl[0.25]} -> {zahl[0.125]}")

    # Eine zu grobe Vorgabe wird auf die Bauteilgroesse heruntergesetzt
    m = neues_modell()
    k = prisma(m, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
    m.netz.ziellaenge = 2.0
    log = []
    els = M3.mesh_koerper_frei(m, k, log=log)
    check("zu grobe Vorgabe wird verkleinert und gemeldet",
          bool(els) and any("zu grob" in z for z in log), log[0] if log else "-")


# --------------------------------------------------------------------------
# 3) Einspringende Ecke: der L-Koerper darf nicht zugeschuettet werden
# --------------------------------------------------------------------------
def test_einspringende_ecke():
    m = neues_modell()
    L = [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)]
    k = prisma(m, [L], 1.0)
    m.netz.ziellaenge = 0.25
    log = []
    els = M3.mesh_koerper_frei(m, k, log=log)
    V = netzvolumen(m, els)
    close("L-Körper: Netzvolumen (5 m^2 x 1 m)", V, 5.0, 5e-3, " m^3")
    # Kein Element darf in der Kerbe liegen (x > 1 und y > 1)
    schwer = np.array([m.nodes[[int(x) for x in m.elements[i].nodes]].mean(axis=0)
                       for i in els])
    kerbe = int(np.count_nonzero((schwer[:, 0] > 1.02) & (schwer[:, 1] > 1.02)))
    check("kein Element in der einspringenden Ecke", kerbe == 0, f"{kerbe} Elemente")
    check("Protokoll nennt Volumen, Güte und Randtreue",
          any("Randtreue" in z for z in log), log[-1] if log else "-")


# --------------------------------------------------------------------------
# 4) Platte mit Bohrung: das Loch bleibt ausgespart
# --------------------------------------------------------------------------
def test_platte_mit_bohrung():
    r, t = 0.4, 0.4
    m = neues_modell()
    k = prisma(m, [[(0, 0), (2, 0), (2, 2), (0, 2)],
                   kreis_punkte(r, 48, 1.0, 1.0, umgekehrt=True)], t)
    m.netz.ziellaenge = 0.15
    els = M3.mesh_koerper_frei(m, k, log=[])
    # Das 48-Eck der Bohrung ist eingeschrieben, seine Flaeche also
    # A = 48/2 * r^2 * sin(2 pi / 48)
    A_loch = 24 * r * r * np.sin(2 * np.pi / 48)
    soll = (4.0 - A_loch) * t
    close("Platte mit Bohrung: Netzvolumen", netzvolumen(m, els), soll, 1e-6, " m^3")
    schwer = np.array([m.nodes[[int(x) for x in m.elements[i].nodes]].mean(axis=0)
                       for i in els])
    im_loch = int(np.count_nonzero(
        np.linalg.norm(schwer[:, :2] - np.array([1.0, 1.0]), axis=1) < 0.95 * r))
    check("kein Element in der Bohrung", im_loch == 0, f"{im_loch} Elemente")


# --------------------------------------------------------------------------
# 5) Zylinder und Buchse: krumme Randflaechen ueber ihre Kontrollpunkte
# --------------------------------------------------------------------------
def test_zylinder_und_buchse():
    m = neues_modell()
    k = buchse(m, 0.5, 0.0, 1.0)
    m.netz.ziellaenge = 0.1
    els = M3.mesh_koerper_frei(m, k, log=[])
    P, T, bericht = M3.randschale(m, k, 0.1)
    check("Zylinder: Hülle dicht", bericht["offen"] == 0, str(bericht["offen"]))
    close("Zylinder: Netzvolumen gleich Hüllvolumen",
          netzvolumen(m, els), bericht["volumen"], 1e-6, " m^3")
    # Das einbeschriebene n-Eck: A = n/2 r^2 sin(2 pi / n). n ist die Zahl der
    # Umfangsabschnitte, die der Vernetzer der Linie wirklich gegeben hat.
    n = 2 * _umfangsabschnitte(m, k, 0.1, "AU1")
    soll = 0.5 * n * 0.25 * np.sin(2 * np.pi / n) * 1.0
    close("Zylinder: Volumen des einbeschriebenen Vielecks",
          bericht["volumen"], soll, 1e-6, " m^3")
    check("Zylinder: mindestens zwölf Umfangsabschnitte", n >= 12, f"{n}")

    m = neues_modell()
    k = buchse(m, 0.5, 0.3, 1.0)
    m.netz.ziellaenge = 0.1
    els = M3.mesh_koerper_frei(m, k, log=[])
    P, T, bericht = M3.randschale(m, k, 0.1)
    check("Buchse: Hülle dicht", bericht["offen"] == 0, str(bericht["offen"]))
    close("Buchse: Netzvolumen gleich Hüllvolumen",
          netzvolumen(m, els), bericht["volumen"], 1e-6, " m^3")
    close("Buchse: Volumen nahe pi (ra^2 - ri^2) h",
          bericht["volumen"], np.pi * (0.25 - 0.09), 4e-3, " m^3")
    schwer = np.array([m.nodes[[int(x) for x in m.elements[i].nodes]].mean(axis=0)
                       for i in els])
    innen = int(np.count_nonzero(np.linalg.norm(schwer[:, :2], axis=1) < 0.28))
    check("Buchse: kein Element in der Bohrung", innen == 0, f"{innen} Elemente")


# --------------------------------------------------------------------------
# 6) Zu grobe Vorgabe wird fuer kleine Bauteile selbst verfeinert
# --------------------------------------------------------------------------
def test_kleines_bauteil():
    m = neues_modell()
    k = buchse(m, 0.010, 0.0, 0.025)          # Bolzen d = 20 mm, l = 25 mm
    m.netz.ziellaenge = 0.05                   # 50 mm - groesser als das Teil
    log = []
    els = M3.mesh_koerper_frei(m, k, log=log)
    check("Bolzen wird trotz zu grober Vorgabe vernetzt", bool(els),
          f"{len(els)} Tetraeder")
    check("und das Protokoll sagt, dass die Kantenlänge verkleinert wurde",
          any("zu grob" in z for z in log), log[0] if log else "-")
    V = netzvolumen(m, els)
    n = 2 * _umfangsabschnitte(m, k, 0.025 / 4, "AU1")
    soll = 0.5 * n * 1e-4 * np.sin(2 * np.pi / n) * 0.025
    close("Bolzen: Volumen des einbeschriebenen Vielecks", V, soll, 1e-11, " m^3")
    check("und das liegt knapp unter dem Kreiszylinder",
          0.94 * np.pi * 1e-4 * 0.025 <= V < np.pi * 1e-4 * 0.025,
          f"{V:.6e} m^3 von {np.pi * 1e-4 * 0.025:.6e} m^3")


# --------------------------------------------------------------------------
# 7) Zwei Koerper mit gemeinsamer Randflaeche haengen zusammen
# --------------------------------------------------------------------------
def test_gemeinsame_flaeche():
    m = neues_modell()
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.]])
    m.add_nodes(P)
    b = Bauer(m)
    E = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [b.linie(i, i + 4) for i in range(4)]
    V12 = [b.linie(i + 4, i + 8) for i in range(4)]
    for j, nm in enumerate(("F0", "Fm", "F2")):
        m.add_flaeche(nm, E[j], material="S235")
    unten, oben = [], []
    for i in range(4):
        m.add_flaeche(f"A{i}", [E[0][i], V01[(i + 1) % 4], E[1][i], V01[i]],
                      material="S235")
        m.add_flaeche(f"B{i}", [E[1][i], V12[(i + 1) % 4], E[2][i], V12[i]],
                      material="S235")
        unten.append(f"A{i}")
        oben.append(f"B{i}")
    k1 = m.add_koerper("V1", ["F0", "Fm"] + unten, material="S235")
    k2 = m.add_koerper("V2", ["Fm", "F2"] + oben, material="S235")
    m.netz.ziellaenge = 0.25
    cache: dict = {}
    e1 = M3.mesh_koerper_frei(m, k1, log=[], cache=cache)
    e2 = M3.mesh_koerper_frei(m, k2, log=[], cache=cache)
    close("beide Körper zusammen", netzvolumen(m, e1 + e2), 2.0, 1e-9, " m^3")

    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    zeilen, spalten = [], []
    for i in e1 + e2:
        nd = [int(x) for x in m.elements[i].nodes]
        for a in nd:
            zeilen.append(a)
            spalten.append(nd[0])
    A = coo_matrix((np.ones(len(zeilen)), (zeilen, spalten)), shape=(m.nn, m.nn))
    _, marke = connected_components(A, directed=False)
    benutzt = sorted({int(x) for i in e1 + e2 for x in m.elements[i].nodes})
    check("die gemeinsame Fläche verbindet beide Netze",
          len(set(marke[benutzt])) == 1, f"{len(set(marke[benutzt]))} Teile")

    # Ohne gemeinsames Woerterbuch stehen beide fuer sich
    m2 = neues_modell()
    m2.add_nodes(P)
    b2 = Bauer(m2)
    E = [[b2.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [b2.linie(i, i + 4) for i in range(4)]
    V12 = [b2.linie(i + 4, i + 8) for i in range(4)]
    for j, nm in enumerate(("F0", "Fm", "F2")):
        m2.add_flaeche(nm, E[j], material="S235")
    for i in range(4):
        m2.add_flaeche(f"A{i}", [E[0][i], V01[(i + 1) % 4], E[1][i], V01[i]],
                       material="S235")
        m2.add_flaeche(f"B{i}", [E[1][i], V12[(i + 1) % 4], E[2][i], V12[i]],
                       material="S235")
    kk1 = m2.add_koerper("V1", ["F0", "Fm"] + unten, material="S235")
    kk2 = m2.add_koerper("V2", ["Fm", "F2"] + oben, material="S235")
    m2.netz.ziellaenge = 0.25
    f1 = M3.mesh_koerper_frei(m2, kk1, log=[])
    f2 = M3.mesh_koerper_frei(m2, kk2, log=[])
    gemeinsam = ({int(x) for i in f1 for x in m2.elements[i].nodes}
                 & {int(x) for i in f2 for x in m2.elements[i].nodes})
    check("ohne Wörterbuch teilen sie sich nur die Eckknoten der Linien",
          0 < len(gemeinsam) < 8, f"{len(gemeinsam)} gemeinsame Knoten")


# --------------------------------------------------------------------------
# 8) Rechnung: Zugstab
# --------------------------------------------------------------------------
def test_zugstab():
    E, a, L, N = 210e9, 0.2, 2.0, 1.0e6
    A = a * a
    m = neues_modell()
    k = prisma(m, [[(0, 0), (a, 0), (a, a), (0, a)]], L)
    m.netz.ziellaenge = 0.1
    els = M3.mesh_koerper_frei(m, k, log=[])
    im_netz = sorted({int(x) for i in els for x in m.elements[i].nodes})
    # Symmetriebedingungen: sie sind mit der genauen Loesung vertraeglich,
    # denn u_x ~ x und u_y ~ y verschwinden dort von selbst.
    for i in im_netz:
        dofs = []
        if abs(m.nodes[i][2]) < 1e-9:
            dofs.append(2)
        if abs(m.nodes[i][0]) < 1e-9:
            dofs.append(0)
        if abs(m.nodes[i][1]) < 1e-9:
            dofs.append(1)
        if dofs:
            m.support(i, dofs)
    oben = [i for i in im_netz if abs(m.nodes[i][2] - L) < 1e-9]
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for i in oben:
        m.load_node(i, Fz=N / len(oben), case="LF1")
    r = solver.solve_static(m, case="LF1")

    close("Summe der Auflagerkräfte", float(r.reactions[:, 2].sum()), -N, 1e-3, " N")
    V = np.array([abs(SO.solid_volume("tet4",
                                      m.nodes[[int(x) for x in m.elements[i].nodes]]))
                  for i in els])
    sig = np.array([r.solid_res[i][2] for i in els])
    # Gleichgewichtssatz: Integral sigma_zz dV = Summe z_i F_zi = N * L,
    # also ist die volumengewichtete Mittelspannung genau N/A - unabhaengig
    # vom Netz. Das ist die schaerfste Probe, die es hier gibt.
    close("volumengewichtete Mittelspannung = N/A",
          float((sig * V).sum() / V.sum()), N / A, 1e3, " Pa")
    uz = r.u.reshape(-1, 6)[oben, 2].mean()
    close("Verlängerung N L /(E A)", float(uz), N * L / (E * A),
          0.03 * N * L / (E * A), " m")
    check("Verlängerung liegt auf der sicheren Seite (Netz eher weicher)",
          uz >= N * L / (E * A) * 0.98, f"{uz * 1e6:.2f} µm")


# --------------------------------------------------------------------------
# 9) Undichte Huelle wird nicht vernetzt
# --------------------------------------------------------------------------
def test_undichte_huelle():
    m = neues_modell()
    k = prisma(m, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
    k.flaechen = [x for x in k.flaechen if x != "Deckel"]     # eine Wand fehlt
    m.netz.ziellaenge = 0.5
    log = []
    els = M3.mesh_koerper_frei(m, k, log=log)
    check("offener Körper wird nicht vernetzt", not els, f"{len(els)} Elemente")
    check("und der Grund steht im Protokoll",
          any("nicht dicht" in z for z in log), log[0] if log else "-")


# --------------------------------------------------------------------------
# 10) Quadratische Tetraeder (tet10) und Splitterglaettung
# --------------------------------------------------------------------------
def test_quadratische_tetraeder():
    """Der lineare Tetraeder hat eine konstante Dehnung: unter Biegung ist er
    viel zu steif. Der quadratische gibt dieselbe Aufgabe mit demselben Netz
    richtig wieder - das ist der ganze Grund fuer ihn."""
    E, nu = 210e9, 0.3
    b = hq = 0.2
    L, F = 2.0, 1.0e5
    I = b * hq ** 3 / 12
    G = E / (2 * (1 + nu))
    As = 5.0 / 6.0 * b * hq
    w_soll = F * L ** 3 / (3 * E * I) + F * L / (G * As)     # Biegung + Schub
    ergebnis = {}
    for ordnung in (1, 2):
        m = neues_modell()
        k = prisma(m, [[(0, 0), (b, 0), (b, hq), (0, hq)]], L)
        m.netz.ziellaenge = 0.1
        m.netz.ordnung = ordnung
        els = M3.mesh_koerper_frei(m, k, log=[])
        typen = {m.elements[i].typ for i in els}
        check(f"Ordnung {ordnung}: Elementtyp",
              typen == ({"tet10"} if ordnung == 2 else {"tet4"}), str(typen))
        close(f"Ordnung {ordnung}: Volumen", netzvolumen(m, els), b * hq * L,
              1e-9, " m^3")
        im = sorted({int(x) for i in els for x in m.elements[i].nodes})
        for i in im:
            if abs(m.nodes[i][2]) < 1e-9:
                m.support(i, [0, 1, 2])
        oben = [i for i in im if abs(m.nodes[i][2] - L) < 1e-9]
        lc = m.add_load_case("LF1")
        lc.gravity = [0.0, 0.0, 0.0]
        for i in oben:
            m.load_node(i, Fx=F / len(oben), case="LF1")
        r = solver.solve_static(m, case="LF1")
        ergebnis[ordnung] = float(r.u.reshape(-1, 6)[oben, 0].mean())
        close(f"Ordnung {ordnung}: Summe der Auflagerkräfte",
              -float(r.reactions[:, 0].sum()), F, 1e-3, " N")
    check("der lineare Tetraeder ist unter Biegung deutlich zu steif",
          ergebnis[1] < 0.85 * w_soll,
          f"{ergebnis[1] / w_soll * 100:.1f} % der Balkenlösung")
    check("der quadratische trifft dieselbe Aufgabe auf 3 % genau",
          abs(ergebnis[2] - w_soll) < 0.03 * w_soll,
          f"{ergebnis[2] / w_soll * 100:.1f} % der Balkenlösung "
          f"({ergebnis[2] * 1e3:.3f} mm von {w_soll * 1e3:.3f} mm)")

    # Seitenmittenknoten muessen geteilt werden - sonst faellt das Netz auseinander
    m = neues_modell()
    k = prisma(m, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
    m.netz.ziellaenge = 0.5
    m.netz.ordnung = 2
    els = M3.mesh_koerper_frei(m, k, log=[])
    seiten = {}
    for i in els:
        nd = [int(x) for x in m.elements[i].nodes]
        for a2, b2 in M3.TET10_KANTEN:
            seiten.setdefault((min(nd[a2], nd[b2]), max(nd[a2], nd[b2])), set()).add(
                nd[4 + M3.TET10_KANTEN.index((a2, b2))])
    check("jede Kante hat genau einen Seitenmittenknoten",
          all(len(v) == 1 for v in seiten.values()),
          f"{sum(1 for v in seiten.values() if len(v) != 1)} Kanten mit mehreren")


def test_splitter_glaetten():
    """Splitter sind fast flache Tetraeder. Das Kugel-Kanten-Kriterium erfasst
    sie nicht - dafuer werden die freien Knoten so verschoben, dass die
    schlechteste Guete steigt. Die Randknoten bleiben, wo sie sind: das
    Volumen darf sich dabei nicht aendern."""
    r, t = 0.4, 0.4
    ohne = mit = None
    for splitter in (0.0, 0.1):
        m = neues_modell()
        k = prisma(m, [[(0, 0), (2, 0), (2, 2), (0, 2)],
                       kreis_punkte(r, 48, 1.0, 1.0, umgekehrt=True)], t)
        m.netz.ziellaenge = 0.15
        m.netz.splitter = splitter
        els = M3.mesh_koerper_frei(m, k, log=[])
        TET = np.array([[int(x) for x in m.elements[i].nodes] for i in els])
        q = M3.guete(m.nodes, TET)
        werte = (float(q.min()), int((q < 0.1).sum()), netzvolumen(m, els), len(els))
        if splitter:
            mit = werte
        else:
            ohne = werte
    check("ohne Glättung gibt es Splitter", ohne[1] > 0,
          f"{ohne[1]} Elemente unter 0.1, schlechtestes {ohne[0]:.4f}")
    check("mit Glättung ist die schlechteste Güte deutlich besser",
          mit[0] > 5 * ohne[0], f"{ohne[0]:.4f} -> {mit[0]:.4f}")
    check("und kein Splitter bleibt übrig", mit[1] == 0, f"{mit[1]} Elemente")
    close("das Volumen bleibt dabei unverändert", mit[2], ohne[2], 1e-9, " m^3")
    check("und die Elementzahl auch", mit[3] == ohne[3], f"{ohne[3]} -> {mit[3]}")


# --------------------------------------------------------------------------
# 11) Lasten, die an der Geometrie haengen, wirken nach dem Vernetzen
# --------------------------------------------------------------------------
def test_geometrielast():
    """RFEM haengt seine Flaechenlasten an die Flaeche. Beim Import gibt es die
    Elemente noch nicht - die Last muss darum am Objekt bleiben und beim
    Vernetzen auf die Elemente kommen. Die Probe ist das Gleichgewicht:
    die Summe der Auflagerkraefte muss p mal Flaeche sein."""
    a, hoehe, p = 1.0, 0.5, -2.0e5          # 200 kN/m^2 nach unten
    m = neues_modell()
    k = prisma(m, [[(0, 0), (a, 0), (a, a), (0, a)]], hoehe)
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("Deckel", p, "flaeche", richtung=[0.0, 0.0, 1.0], case="LF1")
    check("die Last haengt am Objekt", len(m.case("LF1").geometrielasten) == 1)
    check("vor dem Vernetzen wirkt sie nicht",
          m.lasten_verteilen() == 0 and not m.case("LF1").face_loads)

    m.netz.ziellaenge = 0.25
    els = M3.mesh_koerper_frei(m, k, log=[])
    n = m.lasten_verteilen()
    check("nach dem Vernetzen liegt sie auf den Elementen", n > 0,
          f"{n} Elementlasten")
    check("die Randseiten der Fläche sind gemerkt",
          len(m.flaechen["Deckel"].randseiten) == n,
          f"{len(m.flaechen['Deckel'].randseiten)} Seiten")

    im = sorted({int(x) for i in els for x in m.elements[i].nodes})
    for i in im:
        if abs(m.nodes[i][2]) < 1e-9:
            m.support(i, [0, 1, 2])
    r = solver.solve_static(m, case="LF1")
    close("Summe der Auflagerkräfte = p · A", float(r.reactions[:, 2].sum()),
          -p * a * a, 1.0, " N")

    # Wiederholtes Verteilen darf die Last nicht verdoppeln
    n2 = m.lasten_verteilen()
    check("nochmaliges Verteilen verdoppelt die Last nicht",
          n2 == n and len(m.case("LF1").face_loads) == n,
          f"{len(m.case('LF1').face_loads)} Elementlasten")
    # und sie ueberlebt Speichern und Laden
    from statik3d.model import Model as _M
    m2 = _M.from_dict(m.to_dict())
    check("die Geometrielast überlebt Speichern und Laden",
          len(m2.case("LF1").geometrielasten) == 1
          and len(m2.case("LF1").face_loads) == 0,
          f"{len(m2.case('LF1').geometrielasten)} Geometrielasten, "
          f"{len(m2.case('LF1').face_loads)} Elementlasten")
    check("und wird nach dem Laden wieder verteilt",
          m2.lasten_verteilen() == n, f"{n} Elementlasten")


def main():
    for t in (test_punkt_im_koerper, test_quader, test_einspringende_ecke,
              test_platte_mit_bohrung, test_zylinder_und_buchse,
              test_kleines_bauteil, test_gemeinsame_flaeche, test_zugstab,
              test_undichte_huelle, test_quadratische_tetraeder,
              test_splitter_glaetten, test_geometrielast):
        print(f"\n--- {t.__name__} ---")
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
