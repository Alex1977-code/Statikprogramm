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
    # Schranke 1e-5 des Rauminhalts statt 1e-6 m^3: Kappen an der Bohrungswand
    # (Splitter aus vier Huellknoten) werden entfernt, das Huellviereck ist
    # danach ueber die andere Diagonale geteilt und dem Netz fehlt der
    # Rauminhalt der Kappen - hier 2 Kappen, 5,8e-6 von 1,40 m^3 (20.09.2026,
    # mesher3d._kappen_entfernen). Das ist der Preis fuer ein Netz ohne Splitter.
    close("Platte mit Bohrung: Netzvolumen", netzvolumen(m, els), soll, 1e-5 * soll, " m^3")
    schwer = np.array([m.nodes[[int(x) for x in m.elements[i].nodes]].mean(axis=0)
                       for i in els])
    im_loch = int(np.count_nonzero(
        np.linalg.norm(schwer[:, :2] - np.array([1.0, 1.0]), axis=1) < 0.95 * r))
    check("kein Element in der Bohrung", im_loch == 0, f"{im_loch} Elemente")


def test_duenne_platte_randseiten():
    """Duenne Platte (Dicke ein Drittel der Kantenlaenge), frei vernetzt: die
    Randseiten der Deckflaeche sind genau die Facetten in ihrer Ebene - keine
    Seitenwand haengt an ihr. Vorher bekam die Deckflaeche die Seitenfacetten
    dazu (naechste Huellflaeche innerhalb eines Viertels der Kantenlaenge):
    36 % zu viel Flaeche fuer Flaechenlast, Kontaktfuge und Flaechenlager."""
    from statik3d.fugen import _dreiecke_der_fuge
    lx, ly, t = 1.0, 0.6, 0.04
    m = neues_modell()
    k = prisma(m, [[(0, 0), (lx, 0), (lx, ly), (0, ly)]], t)
    m.netz.ziellaenge = 0.12
    els = M3.mesh_koerper_frei(m, k, log=[])
    check("duenne Platte: frei vernetzt", len(els) > 0, f"{len(els)} Tetraeder")

    def flaeche(fac):
        return sum(0.5 * float(np.linalg.norm(np.cross(m.nodes[nd[1]] - m.nodes[nd[0]],
                                                       m.nodes[nd[2]] - m.nodes[nd[0]])))
                   for _e, nd, _n in fac)

    for name, z in (("Boden", 0.0), ("Deckel", t)):
        fac = _dreiecke_der_fuge(m, [m.flaechen[name]])
        close(f"{name}: Summe der Randseiten = Flaecheninhalt", flaeche(fac), lx * ly,
              0.01 * lx * ly, " m^2")
        neben = sum(1 for _e, nd, _n in fac if np.abs(m.nodes[nd][:, 2] - z).max() > 1e-9)
        check(f"{name}: keine Randseite neben der Ebene", neben == 0, f"{neben} von {len(fac)}")
    seiten = sum(flaeche(_dreiecke_der_fuge(m, [m.flaechen[f"M{i}"]])) for i in range(1, 5))
    close("Seitenwaende: Summe = Umfang x Dicke", seiten, 2 * (lx + ly) * t, 1e-9, " m^2")


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
    Volumen darf sich dabei nicht aendern.

    Flache Tetraeder (Volumen unter FLACH * h^3) bleiben bis nach der
    Glaettung im Netz - sonst staende an ihrer Stelle ein Schlitz, dessen
    Knoten festzuhalten waeren, und ein Splitter daneben mit den uebrigen
    Knoten auf der Huelle bliebe, wie er ist (10.09.2026: Guete 0,0058 blieb
    0,0058, weil alle vier Knoten festlagen). Repariert die Glaettung einen
    flachen Tetraeder, ist er danach ein Element: die Elementzahl waechst um
    genau die reparierten, und die Volumensumme um das, was ihnen vorher
    fehlte - je unter FLACH * h^3."""
    r, t = 0.4, 0.4
    ohne = mit = None
    flache = {}
    for splitter in (0.0, 0.1):
        m = neues_modell()
        k = prisma(m, [[(0, 0), (2, 0), (2, 2), (0, 2)],
                       kreis_punkte(r, 48, 1.0, 1.0, umgekehrt=True)], t)
        m.netz.ziellaenge = 0.15
        m.netz.splitter = splitter
        # Hier wird die Wirkung der Glaettung fuer sich gemessen, und dazu
        # muessen beide Laeufe dasselbe Netz bekommen. Das selbsttaetige
        # Nachvernetzen reagiert aber auf die Guete - also genau auf das, was
        # die Glaettung veraendert: ohne Glaettung reisst das Guetekriterium,
        # es wird verfeinert, und verglichen wuerden zwei verschiedene Netze.
        m.netz.nachvernetzen = False
        log = []
        els = M3.mesh_koerper_frei(m, k, log=log)
        TET = np.array([[int(x) for x in m.elements[i].nodes] for i in els])
        q = M3.guete(m.nodes, TET)
        werte = (float(q.min()), int((q < 0.1).sum()), netzvolumen(m, els), len(els))
        zeile = next((z for z in log if "flache Tetraeder aussortiert" in z), "0")
        flache[splitter] = int(zeile.split()[0])
        if splitter:
            mit = werte
        else:
            ohne = werte
    check("ohne Glättung gibt es Splitter", ohne[1] > 0,
          f"{ohne[1]} Elemente unter 0.1, schlechtestes {ohne[0]:.4f}")
    check("mit Glättung ist die schlechteste Güte deutlich besser",
          mit[0] > 5 * ohne[0], f"{ohne[0]:.4f} -> {mit[0]:.4f}")
    check("und kein Splitter bleibt übrig", mit[1] == 0, f"{mit[1]} Elemente")
    # Seit 20.09.2026 tut der Splitterweg mehr als glaetten: Kappen (Splitter
    # aus vier Huellknoten) bekommen einen Punkt knapp innerhalb der Huelle
    # (mesher3d._kappenpunkte) - das gibt zusaetzliche Tetraeder -, und was
    # davon auf einer gewoelbten Wand stehenbleibt, wird entfernt
    # (_kappen_entfernen) - das nimmt dem Netz den Rauminhalt der Kappen.
    # Die Elementzahl waechst darum um mindestens die reparierten flachen
    # Tetraeder, und der Rauminhalt aendert sich hoechstens um das, was den
    # flachen fehlte, plus den Kappen (gemessen: 5,8e-6 von 1,40 m^3).
    check("die Elementzahl wächst mindestens um die reparierten flachen Tetraeder",
          mit[3] - ohne[3] >= flache[0.0] - flache[0.1] and flache[0.0] > 0,
          f"{ohne[3]} -> {mit[3]}; flach aussortiert {flache[0.0]} -> {flache[0.1]}")
    schranke = (flache[0.0] + flache[0.1]) * M3.FLACH * 0.15 ** 3 + 1e-5 * ohne[2]
    check("und das Volumen nur um das, was den flachen fehlte, und um die entfernten Kappen",
          abs(mit[2] - ohne[2]) <= schranke,
          f"{mit[2] - ohne[2]:.3e} m^3, Schranke {schranke:.3e} m^3")


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
    # Bis zum 21.09.2026 stand hier ``face_loads == 0``: die Elementlasten
    # kommen nicht in die Datei (richtig), und die naechste Zeile verteilte
    # von Hand. Der Name der Pruefung sagte aber "ueberlebt Speichern und
    # Laden", und das tat sie nicht - niemand verteilte von selbst, und der
    # Anwender rechnete ohne seine Flaechenlast (Theoriehandbuch 7.3).
    # ``Model.from_dict`` verteilt jetzt beim Laden; die Datei selbst ist
    # unveraendert und traegt die abgeleiteten Lasten weiterhin nicht.
    check("die Geometrielast überlebt Speichern und Laden",
          len(m2.case("LF1").geometrielasten) == 1
          and len(m2.case("LF1").face_loads) == n
          and len(m.to_dict()["load_cases"][0]["face_loads"]) == 0,
          f"{len(m2.case('LF1').geometrielasten)} Geometrielasten, "
          f"{len(m2.case('LF1').face_loads)} Elementlasten, "
          f"in der Datei {len(m.to_dict()['load_cases'][0]['face_loads'])}")
    check("und ein weiteres Verteilen verdoppelt sie nicht",
          m2.lasten_verteilen() == n and len(m2.case("LF1").face_loads) == n,
          f"{n} Elementlasten")


# --------------------------------------------------------------------------
# 13) Fortschritt und Abbruch: der Rueckruf laeuft mit, False haelt an
# --------------------------------------------------------------------------
def test_fortschritt_und_abbruch():
    m = neues_modell()
    k = prisma(m, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
    m.netz.ziellaenge = 0.125
    rufe = []
    els = M3.mesh_koerper_frei(m, k, log=[], fortschritt=lambda a, t: rufe.append((a, t)) or True)
    anteile = [a for a, _ in rufe if a is not None]
    check("der Rückruf kommt während der Vernetzung oft", bool(els) and len(rufe) >= 10,
          f"{len(rufe)} Rückrufe")
    rueckwaerts = sum(1 for a, b in zip(anteile, anteile[1:]) if b < a - 1e-9)
    check("die Anteile laufen von 0 bis nahe 1 und kaum je zurück",
          anteile and anteile[0] <= 0.05 and max(anteile) >= 0.9 and rueckwaerts <= 2,
          f"{anteile[0]:.2f} … {max(anteile):.2f}, {rueckwaerts} Rückschritte")
    check("die Texte nennen die Schritte",
          any("Randhülle" in t for _, t in rufe) and any("Tetraedern" in t for _, t in rufe),
          str([t for _, t in rufe[:4]]))
    # Abbruch: nach ein paar Rueckrufen False - der Koerper bleibt ohne Netz,
    # das Modell unveraendert, das Protokoll sagt es
    m2 = neues_modell()
    k2 = prisma(m2, [[(0, 0), (1, 0), (1, 1), (0, 1)]], 1.0)
    m2.netz.ziellaenge = 0.125
    nn, ne = m2.nn, len(m2.elements)
    zaehler = [0]

    def stop(_a, _t):
        zaehler[0] += 1
        return zaehler[0] < 5
    log = []
    els2 = M3.mesh_koerper_frei(m2, k2, log=log, fortschritt=stop)
    check("Abbrechen lässt den Körper ohne Netz und das Modell unverändert",
          not els2 and m2.nn == nn and len(m2.elements) == ne and not k2.elemente,
          f"{len(els2)} Elemente, {m2.nn - nn} neue Knoten")
    check("und das Protokoll nennt den Abbruch", any("abgebrochen" in z for z in log),
          log[-1] if log else "-")


# --------------------------------------------------------------------------
# 14) Mehrere Koerper parallel: dasselbe Netz wie seriell, verbunden
# --------------------------------------------------------------------------
def _zwei_koerper():
    """Zwei sechseckige Prismen uebereinander mit gemeinsamer Trennflaeche -
    keine Sechsflaechner, also Arbeit fuer den freien Vernetzer."""
    m = neues_modell()
    m.netz.sweep = False                     # sonst sweepbar (statik3d.sweep, 20.09.2026)
    n = 6
    w = np.arange(n) * 2 * np.pi / n
    ring = np.column_stack([np.cos(w), np.sin(w)])
    P = np.vstack([np.column_stack([ring, np.full(n, z)]) for z in (0.0, 1.0, 2.0)])
    m.add_nodes(P)
    b = Bauer(m)
    E = [[b.linie(o + i, o + (i + 1) % n) for i in range(n)] for o in (0, n, 2 * n)]
    V01 = [b.linie(i, i + n) for i in range(n)]
    V12 = [b.linie(i + n, i + 2 * n) for i in range(n)]
    for j, nm in enumerate(("F0", "Fm", "F2")):
        m.add_flaeche(nm, E[j], material="S235")
    unten, oben = [], []
    for i in range(n):
        m.add_flaeche(f"A{i}", [E[0][i], V01[(i + 1) % n], E[1][i], V01[i]], material="S235")
        m.add_flaeche(f"B{i}", [E[1][i], V12[(i + 1) % n], E[2][i], V12[i]], material="S235")
        unten.append(f"A{i}")
        oben.append(f"B{i}")
    k1 = m.add_koerper("V1", ["F0", "Fm"] + unten, material="S235")
    k2 = m.add_koerper("V2", ["Fm", "F2"] + oben, material="S235")
    m.netz.ziellaenge = 0.3
    return m, k1, k2


def _teile(m, els) -> int:
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    zeilen, spalten = [], []
    for i in els:
        nd = [int(x) for x in m.elements[i].nodes]
        for a in nd:
            zeilen.append(a)
            spalten.append(nd[0])
    A = coo_matrix((np.ones(len(zeilen)), (zeilen, spalten)), shape=(m.nn, m.nn))
    _, marke = connected_components(A, directed=False)
    benutzt = sorted({int(x) for i in els for x in m.elements[i].nodes})
    return len(set(marke[benutzt]))


def test_parallel_vernetzen():
    from statik3d import mesher
    ms, s1, s2 = _zwei_koerper()
    rufe_s = []
    erg_s = mesher.koerper_vernetzen(ms, [s1, s2], log=[], workers=1,
                                     fortschritt=lambda a, t: rufe_s.append((a, t)) or True)
    check("seriell: beide Körper vernetzt", erg_s["fertig"] == 2 and erg_s["elemente"] > 0,
          str(erg_s))
    check("seriell: der Rückruf zählt die Volumenarbeit von 0 bis 1 durch",
          rufe_s and rufe_s[0][0] <= 0.5 and max(a for a, _ in rufe_s) >= 0.9, str(rufe_s[-1]))
    mp_, p1, p2 = _zwei_koerper()
    rufe_p = []
    log_p = []
    erg_p = mesher.koerper_vernetzen(mp_, [p1, p2], log=log_p, workers=2,
                                     fortschritt=lambda a, t: rufe_p.append((a, t)) or True)
    check("parallel: zwei Arbeitsprozesse, beide Körper vernetzt",
          erg_p["prozesse"] == 2 and erg_p["fertig"] == 2, str(erg_p))
    check("parallel gibt genau dasselbe Netz wie seriell",
          erg_p["elemente"] == erg_s["elemente"] and mp_.nn == ms.nn,
          f"{erg_p['elemente']} gegen {erg_s['elemente']} Elemente, {mp_.nn} gegen {ms.nn} Knoten")
    check("und die gemeinsame Fläche verbindet beide Netze",
          _teile(mp_, p1.elemente + p2.elemente) == 1)
    close("Netzvolumen beider Körper", netzvolumen(mp_, p1.elemente + p2.elemente),
          2 * 6 * 0.5 * np.sin(np.pi / 3), 1e-9, " m^3")
    check("das Protokoll nennt beide Körper", sum(1 for z in log_p if z.startswith("Volumen V")) >= 2,
          str(log_p[:2]))
    # Abbrechen: der erste Rueckruf sagt False - nichts wird eingebaut, die
    # Prozesse werden beendet
    ma, a1, a2 = _zwei_koerper()
    erg_a = mesher.koerper_vernetzen(ma, [a1, a2], log=[], workers=2, fortschritt=lambda a, t: False)
    check("Abbrechen beendet die Arbeitsprozesse und baut nichts ein",
          erg_a["abgebrochen"] and erg_a["elemente"] == 0 and not ma.elements, str(erg_a))


def altes_rundungsgitter(P, T, tol):
    """Das Vernaehen, wie es bis zum 09.09.2026 war - nur fuer die Gegenprobe.

    Verschmolzen wird ueber ein Rundungsgitter ``round(P / tol)``. Genau das
    trennt zwei Kopien desselben Punktes, wenn die Zellgrenze zufaellig
    zwischen ihnen liegt.
    """
    key = np.round(P / max(tol, 1e-15)).astype(np.int64)
    _, erste, invers = np.unique(key, axis=0, return_index=True, return_inverse=True)
    invers = np.asarray(invers).reshape(-1)
    ordnung = np.argsort(erste)
    neu = np.zeros(len(erste), dtype=int)
    neu[ordnung] = np.arange(len(erste))
    index = neu[invers]
    Pn = np.zeros((len(erste), 3))
    Pn[index] = P
    Tn = index[T] if len(T) else T
    gut = np.ones(len(Tn), bool)
    if len(Tn):
        gut = ((Tn[:, 0] != Tn[:, 1]) & (Tn[:, 1] != Tn[:, 2]) & (Tn[:, 0] != Tn[:, 2]))
        Tn = Tn[gut]
    return Pn, Tn, index, gut


def test_huelle_ohne_rundungsgitter():
    """Die Randhuelle darf nicht an der Arithmetik der Toleranz haengen.

    Jede Randflaeche hebt ihre Randpunkte ueber die **eigene** Ebenenbasis aus
    2D zurueck. Die beiden Kopien desselben Linienpunkts sind danach nur noch
    auf Maschinengenauigkeit gleich - Groessenordnung 1e-16 m. Ein
    Rundungsgitter ``round(P / tol)`` legt sie nur dann zusammen, wenn keine
    Zellgrenze dazwischen liegt; ob eine dazwischenliegt, ist reine
    Arithmetik: die Koordinaten eines CAD-Modells sind Vielfache von 0,25 mm,
    ``tol`` ist h/10000, und bei manchem h faellt ``x / tol`` genau auf eine
    halbe Ganzzahl. Dann rundet die eine Kopie auf, die andere ab - zwei
    Knoten statt einem, vier Kanten in nur einem Dreieck, Huelle offen.

    Gebaut ist genau dieser Fall: Ecke bei x = -421,25 mm, h = 50/1,5^2 mm,
    also tol = 2,2222 um und x/tol = -189562,5. Das sind die Zahlen aus der
    Bestandsaufnahme vom 09.09.
    """
    h = 0.05 / 1.5 / 1.5
    tol = max(h * 1e-4, 1e-9)
    check("die Ecke liegt genau auf einer Zellgrenze des Rundungsgitters",
          abs(abs(-0.42125 / tol) % 1.0 - 0.5) < 1e-6,
          f"x/tol = {-0.42125 / tol:.4f}")

    m = neues_modell()
    k = prisma(m, [[(-0.42125, -0.38), (0.1, -0.38), (0.1, 0.2), (-0.42125, 0.2)]], 0.3)
    P, T, bericht = M3.randschale(m, k, h, [], None, None, None)
    check("die Hülle ist dicht", bericht["offen"] == 0,
          f"{bericht['offen']} offene Kanten, {len(T)} Dreiecke")
    check("sie ist ein Stück", bericht.get("teile") == 1, str(bericht.get("teile")))
    check("und umschließt das Rauminhalt des Quaders",
          abs(bericht["volumen"] - 0.52125 * 0.58 * 0.3) < 1e-9,
          f"{bericht['volumen']:.6f} m^3")

    # Gegenprobe: mit dem alten Weg reisst dieselbe Huelle auf. Ohne diese
    # Zeile pruefte der Test nichts - er liefe auch mit dem Fehler gruen.
    fuegen, naehen = M3.huelle_fuegen, M3.vernaehen
    M3.vernaehen = altes_rundungsgitter
    M3.huelle_fuegen = lambda Pt, Tt, kn: (
        np.vstack(Pt),
        np.vstack([Tx + sum(len(x) for x in Pt[:i]) for i, Tx in enumerate(Tt)]),
        [])
    try:
        _, _, alt = M3.randschale(m, k, h, [], None, None, None)
    finally:
        M3.huelle_fuegen, M3.vernaehen = fuegen, naehen
    check("mit dem Rundungsgitter wäre sie aufgerissen - der Test greift",
          alt["offen"] > 0, f"{alt['offen']} offene Kanten")

    # Der Einheitstest zum Vernaehen selbst: zwei Punkte 5e-16 m auseinander,
    # auf beiden Seiten der Zellgrenze - in jeder der vier Lagen ein Punkt.
    T0 = np.zeros((0, 3), int)
    getrennt = 0
    for kk in (-189562, -189563):
        x = (kk - 0.5) * tol
        for d in (+5e-16, -5e-16):
            Pn = M3.vernaehen(np.array([[x, 0.0, 0.0], [x + d, 0.0, 0.0]]), T0, tol)[0]
            getrennt += int(len(Pn) != 1)
    check("vernaehen legt zwei Punkte im Abstand 5e-16 m immer zusammen",
          getrennt == 0, f"{getrennt} von 4 blieben getrennt")
    zwei = M3.vernaehen(np.array([[0.0, 0.0, 0.0], [10 * tol, 0.0, 0.0]]), T0, tol)[0]
    check("echte Nachbarn bleiben getrennt", len(zwei) == 2, f"{len(zwei)} Punkte")

    # Die offenen Kanten werden benannt, nicht nur gezaehlt
    zeilen = M3.offene_kanten_text(M3._offene_kanten(
        np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1.0, 0]]),
        np.array([[0, 1, 2]]), ["F1"]))
    check("eine offene Kante wird mit Fläche und Koordinaten genannt",
          len(zeilen) == 3 and "F1" in zeilen[0] and "0.0000" in zeilen[0],
          zeilen[0] if zeilen else "keine Zeile")


def test_groessenfeld_an_der_bohrung():
    """Am Bohrungsrand darf die Kante nicht in einem Schritt aufs Feld springen.

    Gemessen an einer 20-mm-Bohrung in einer 900-mm-Platte bei 50 mm
    Zielkantenlaenge: der Bohrungsrand war mit 20 Segmenten geteilt (Sehne
    3,1 mm), und **in der ersten Elementlage** stand schon die volle
    Zielkantenlaenge. Im Kranz zwischen r und 2r lag **kein einziger** Knoten,
    das Kantenverhaeltnis der Dreiecke am Loch betrug im Median 17 und die
    Formguete lag bei 0,06 - 73 % der Dreiecke unter 0,3.

    Fuer eine Kerbspannung ist das zu wenig: der Spannungsabfall geschieht
    ueber etwa r/2, und den bildet eine einzige Elementlage nicht ab. Gefordert
    sind darum mindestens zwei Knotenringe im Kranz r … 2r, ein
    Kantenverhaeltnis im Median unter 2 und hoechstens 5 % der Dreiecke unter
    der Guete 0,3.
    """
    r, R, t, h = 0.010, 0.45, 0.05, 0.05
    m = neues_modell()
    k = prisma(m, [[(-R, -R), (R, -R), (R, R), (-R, R)],
                   [tuple(x) for x in kreis_punkte(r, 24, umgekehrt=True)]], t)
    teilung = M3.Linienteilung(m, [m.flaechen[n] for n in k.flaechen], h)

    def messen(P, T):
        d = np.linalg.norm(P[:, :2], axis=1)
        nah = np.where(d <= 2 * r)[0]
        maske = np.isin(T, nah).any(axis=1)
        X = P[T[maske]]
        L = np.linalg.norm(X[:, [1, 2, 0]] - X, axis=2)
        A = 0.5 * np.linalg.norm(np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]), axis=1)
        q = 4 * np.sqrt(3) * A / np.maximum((L ** 2).sum(1), 1e-30)
        v = L.max(1) / np.maximum(L.min(1), 1e-12)
        return (int(((d > 1.05 * r) & (d <= 2 * r)).sum()),
                float(np.median(v)), float(v.max()),
                float(q.min()), float((q < 0.3).mean()))

    P, T, meldung, _grob, _kenn = M3.flaechennetz(m, m.flaechen["Deckel"], teilung)
    check("Deckel mit Bohrung vernetzt", not meldung and len(T) > 0,
          meldung or f"{len(T)} Dreiecke")
    n_kranz, v_med, v_max, q_min, q_schlecht = messen(P, T)
    check("mindestens zwei Knotenringe im Kranz r … 2r", n_kranz >= 2 * 20,
          f"{n_kranz} Knoten")
    check("Kantenverhältnis am Loch im Median unter 2", v_med < 2.0, f"{v_med:.2f}")
    check("und im Größtwert unter 4", v_max < 4.0, f"{v_max:.2f}")
    check("höchstens 5 % der Dreiecke unter der Güte 0,3", q_schlecht <= 0.05,
          f"{q_schlecht * 100:.1f} %")
    check("die schlechteste Güte über 0,1", q_min > 0.1, f"{q_min:.3f}")

    # Gegenprobe ohne Kraenze - sonst pruefte der Test nichts
    echt = M3._kraenze
    M3._kraenze = lambda ringe, hh, wachstum=0.0: np.zeros((0, 2))
    try:
        P0, T0, *_ = M3.flaechennetz(m, m.flaechen["Deckel"], teilung)
    finally:
        M3._kraenze = echt
    n0, v0, _vm0, q0, s0 = messen(P0, T0)
    # Gegenprobe ohne Kraenze. Bis zum **Randfeld** (mesher3d.RANDFELD,
    # 21.09.2026) lag dann **kein einziger** Knoten im Kranz r … 2r, das
    # Kantenverhaeltnis war 17 und die Haelfte der Dreiecke unter der Guete
    # 0,3. Seither setzt das Innennetz auch ohne Kraenze Punkte dorthin (37
    # statt 72, Verhaeltnis 1,3, keins unter 0,3) - die Form allein tragen
    # also inzwischen beide. Die Kraenze bleiben fuer die **Aufloesung** am
    # Loch: zwei Knotenringe in r … 2r, die der Kerbspannung, nicht der Guete
    # wegen da sind (oben geprueft).
    check("ohne Kränze ist der Kranz merklich dünner besetzt - der Test greift",
          n0 < 0.75 * n_kranz,
          f"{n0} statt {n_kranz} Knoten, Kantenverhältnis {v0:.1f} statt {v_med:.1f}, "
          f"{s0 * 100:.0f} statt {q_schlecht * 100:.0f} % unter 0,3, Güte {q0:.3f}")
    check("und der Preis dafür sind weniger als doppelt so viele Punkte",
          len(P) < 2.0 * len(P0), f"{len(P0)} -> {len(P)} Punkte")

    # Der Vollkreis bekommt 20 Abschnitte (Kruemmungswinkel 18 Grad)
    m2 = neues_modell()
    m2.add_nodes(np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]))
    m2.add_line("B", [0, 1, 2], "arc")          # Halbkreis durch drei Knoten
    check("ein Halbkreis bekommt zehn Abschnitte (Krümmungswinkel 18 Grad)",
          M3._bogenabschnitte(m2, "B") == 10, str(M3._bogenabschnitte(m2, "B")))


def test_mantellinie_der_bohrung():
    """Eine Linie darf nicht neben einer viel feineren stehenbleiben.

    Die Mantellinie einer Bohrung ist der Fall: der Bohrungsrand wird nach der
    Kruemmung geteilt (r = 10 mm, 24 Sehnen von 2,6 mm), die Mantellinie aber
    nach ihrer Laenge - 35 mm bei 50 mm Zielkantenlaenge sind **ein**
    Abschnitt, ein Sprung von 13:1. Die Wachstumsregel
    (:func:`mesher3d._linien_wachsen_lassen`) macht daraus 10 Abschnitte; eine
    900-mm-Aussenlinie bleibt dabei bei der Zielkantenlaenge - die Regel
    begrenzt sich selbst.

    Was es bringt, steht am fertigen Netz: der Anteil der Tetraeder unter der
    Guete 0,3 an der Bohrungswand faellt von 6,8 % auf 1,0 % (Abnahmegrenze
    der Anweisung: 5 %).
    """
    r, R, t, h = 0.010, 0.45, 0.035, 0.05

    def modell(intelligent):
        m = neues_modell()
        m.netz.ziellaenge = h
        m.netz.intelligent = intelligent
        k = prisma(m, [[(-R, -R), (R, -R), (R, R), (-R, R)],
                       [tuple(x) for x in kreis_punkte(r, 24, umgekehrt=True)]], t)
        return m, k

    def linien(m):
        mantel, aussen = [], []
        for name, ln in m.lines.items():
            if len(ln.nodes) != 2:
                continue
            a, b = m.nodes[ln.nodes[0]], m.nodes[ln.nodes[1]]
            if abs(np.linalg.norm(a[:2]) - r) < 1e-9 and abs(a[2] - b[2]) > 1e-9:
                mantel.append(name)
            elif np.linalg.norm(a[:2] - b[:2]) > 0.5:
                aussen.append(name)
        return mantel, aussen

    m, k = modell(True)
    hf, hl = M3.kantenlaengen_karte(m, h=h)
    teil = M3.Linienteilung(m, [m.flaechen[n] for n in k.flaechen], h, hl, hf)
    mantel, aussen = linien(m)
    n_mantel = min(teil.n.get(x, 1) for x in mantel)
    check("die Mantellinie bekommt mehrere Abschnitte", n_mantel >= 8,
          f"{n_mantel} Abschnitte über {t * 1e3:.0f} mm")
    check("ihr Segment liegt nahe an der Sehne des Bohrungsrandes",
          t / n_mantel < 2.0 * (2 * r * np.sin(np.pi / 24)),
          f"{t / n_mantel * 1e3:.1f} mm gegen Sehne "
          f"{2 * r * np.sin(np.pi / 24) * 1e3:.1f} mm")
    n_aussen = min(teil.n.get(x, 1) for x in aussen)
    check("die 900-mm-Außenlinie bleibt bei der Zielkantenlänge - die Regel "
          "begrenzt sich selbst", abs(0.9 / n_aussen - h) < 0.2 * h,
          f"{0.9 / n_aussen * 1e3:.0f} mm statt {h * 1e3:.0f} mm")

    # Gegenprobe ohne die Regel
    m0, k0 = modell(False)
    hf0, hl0 = M3.kantenlaengen_karte(m0, h=h)
    teil0 = M3.Linienteilung(m0, [m0.flaechen[n] for n in k0.flaechen], h, hl0, hf0)
    mantel0, _ = linien(m0)
    check("ohne „intelligent“ steht ein Abschnitt über der ganzen Bohrtiefe - "
          "der Test greift",
          min(teil0.n.get(x, 1) for x in mantel0) == 1,
          f"{min(teil0.n.get(x, 1) for x in mantel0)} Abschnitt(e)")

    # Und am fertigen Netz: die Tetraeder an der Bohrungswand
    def wandguete(mm, kk):
        els = M3.mesh_koerper_frei(mm, kk, log=[])
        TET = np.array([[int(x) for x in mm.elements[i].nodes] for i in els])
        schwer = mm.nodes[TET].mean(axis=1)
        nah = np.abs(np.linalg.norm(schwer[:, :2], axis=1) - r) < 0.5 * r
        q = M3.guete(mm.nodes, TET)
        return len(els), float((q[nah] < 0.3).mean()), float(np.median(q[nah]))

    n1, schlecht1, med1 = wandguete(m, k)
    n0, schlecht0, med0 = wandguete(m0, k0)
    check("an der Bohrungswand liegen höchstens 5 % der Tetraeder unter der Güte 0,3",
          schlecht1 <= 0.05, f"{schlecht1 * 100:.1f} % (ohne die Regel {schlecht0 * 100:.1f} %)")
    check("und die Formgüte dort ist besser als ohne die Regel", med1 > med0,
          f"Median {med1:.3f} gegen {med0:.3f}")
    check("der Preis bleibt im Rahmen (höchstens dreimal so viele Elemente)",
          n1 < 3 * n0, f"{n0} -> {n1} Tetraeder")


def test_randstrecke_wird_nicht_verdraengt():
    """Ein Innenpunkt darf keine Randstrecke aus der Zerlegung verdraengen.

    Der Fall entstand, als gemeinsame Linien nicht mehr allein nachgeteilt
    werden: die Linie bleibt grob, das Innengitter wird feiner - und bei einer
    achsparallelen Flaeche fiel die Gitterreihe j = 0 auf ``lo[1]``, also
    **genau auf die Randlinie**. Der alte Filter mass den Abstand zum
    naechsten Rand**punkt**; mitten zwischen zwei 50,5 mm auseinander
    liegenden Ringpunkten sind das 25 mm, und die Schranke 0,65 h = 21,7 mm
    war damit erfuellt - obwohl der Punkt 0,000 mm von der Strecke entfernt
    lag. Die Delaunay-Zerlegung nahm ihn, die Randstrecke war keine Kante
    mehr, die Huelle klaffte auf, und der Koerper endete ohne Netz, obwohl
    der erste Anlauf ein gueltiges hatte (am Drehlagermodell V34, V31, V110,
    V109, V108).
    """
    from scipy.spatial import Delaunay
    h, L, B, n = 0.05 / 1.5, 0.960, 0.035, 19
    ring = np.array([(L * i / n, 0.0) for i in range(n)] + [(L, B)]
                    + [(L - L * i / n, B) for i in range(1, n)] + [(0.0, B)], float)
    strecke = L / n

    # 1) Das Mass selbst: der Punkt mitten auf der Strecke
    mitte = np.array([[0.5 * strecke, 0.0]])
    zum_punkt = float(np.linalg.norm(ring - mitte, axis=1).min())
    zur_strecke = float(M3.randstreckenabstand(mitte, [ring])[0])
    check("zum nächsten Randpunkt ist der Punkt weit genug weg (altes Maß)",
          zum_punkt > M3.RANDABSTAND * h,
          f"{zum_punkt * 1e3:.1f} mm > {M3.RANDABSTAND * h * 1e3:.1f} mm")
    check("zur Randstrecke ist er es nicht (neues Maß)",
          zur_strecke < 1e-12, f"{zur_strecke * 1e3:.3f} mm")

    # 2) Die Folge: nimmt man ihn, fehlt die Randstrecke im Netz
    P0 = np.vstack([ring, mitte])
    T0 = Delaunay(P0).simplices
    kanten0 = set()
    for i, j in ((0, 1), (1, 2), (2, 0)):
        for x, y in zip(T0[:, i], T0[:, j]):
            kanten0.add((min(int(x), int(y)), max(int(x), int(y))))
    check("ein Punkt auf der Strecke verdrängt sie aus der Zerlegung - "
          "das ist der Mechanismus", (0, 1) not in kanten0)

    # 3) Das Netz: keine Randstrecke fehlt, an keiner der beiden Flaechen
    for nm, ringe, hh in (("Streifen 960 x 35 mm, Langseite fest", [ring], h),
                          ("Platte 1 x 1 m", [np.array([(0., 0.), (1., 0.),
                                                        (1., 1.), (0., 1.)])], 0.1)):
        P2, T, fehlt = M3._dreiecke_2d(ringe, hh)
        nr = len(ringe[0])
        kanten = set()
        for i, j in ((0, 1), (1, 2), (2, 0)):
            for x, y in zip(T[:, i], T[:, j]):
                kanten.add((min(int(x), int(y)), max(int(x), int(y))))
        fehlend = [k for k in ((min(i, (i + 1) % nr), max(i, (i + 1) % nr))
                               for i in range(nr)) if k not in kanten]
        check(f"{nm}: _fehlende_randstrecken meldet nichts", len(fehlt) == 0,
              f"{len(fehlt)} Strecken")
        check(f"{nm}: jede Randstrecke ist eine Kante", not fehlend,
              f"{len(fehlend)} fehlen")

    # 4) Und die Regel raeumt das Innere nicht leer - sie misst zur Strecke,
    #    nicht an ihrer Laenge. Ein Quadrat mit vier 1-m-Strecken haette sonst
    #    650 mm Sperrzone und bliebe leer.
    q = np.array([(0., 0.), (1., 0.), (1., 1.), (0., 1.)], float)
    Pb, _Tb, _fb = M3._dreiecke_2d([q], 0.1)
    check("die 1-x-1-m-Platte behält ihr Innengitter", len(Pb) - 4 > 40,
          f"{len(Pb) - 4} Innenpunkte")


def test_groessenfeld_an_der_festgelegten_linie():
    """Neben einer festgelegten Randlinie richtet sich die Weite nach ihr.

    Gehoert eine Randlinie einem zweiten Koerper, darf sie nicht allein
    nachgeteilt werden - sie bleibt grob, waehrend der eigene Koerper feiner
    vernetzt. Ein Dreieck mit 200 mm Grundseite und 25 mm hohen Nachbarn ist
    aber ein Splitter, ganz gleich wie brav das Innengitter liegt. Gemessen am
    Rechteck 1000 x 500 mm mit festgelegter Langseite, h = 25 mm::

        Strecke/h      1      2      3      4      6      8
        ohne Feld  0.837  0.725  0.480  0.480  0.221  0.153
        mit Feld   0.837  0.725  0.659  0.643  0.443  0.322

    Bis zum Doppelten traegt das gleichmaessige Gitter - dort ist das Feld
    ein **Nullschritt**, und zwar ohne Schwelle: die zulaessige Weite ist die
    Streckenlaenge geteilt durch VERHAELTNIS_FEST, und das ist bei L = 2 h
    gerade h. Erst darueber greift es.
    """
    def guete2d(P, T):
        a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        A = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                         - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
        L2 = (np.sum((b - a) ** 2, 1) + np.sum((c - b) ** 2, 1)
              + np.sum((a - c) ** 2, 1))
        return 4.0 * np.sqrt(3.0) * A / np.maximum(L2, 1e-300)

    def teilen(a, b, s):
        a, b = np.asarray(a, float), np.asarray(b, float)
        k = max(int(round(float(np.linalg.norm(b - a)) / s)), 1)
        return [tuple(a + (b - a) * i / k) for i in range(k)]

    L, B, h = 1.0, 0.5, 0.025
    mass = {}
    for f in (1, 2, 3, 8):
        kopf = teilen((0, 0), (L, 0), f * h)
        ring = np.array(kopf + teilen((L, 0), (L, B), h)
                        + teilen((L, B), (0, B), h) + teilen((0, B), (0, 0), h), float)
        marke = np.zeros(len(ring), bool)
        marke[:len(kopf)] = True            # nur die Langseite ist festgelegt
        for name, fest in (("ohne", None), ("mit", [marke])):
            P2, T, fehlt = M3._dreiecke_2d([ring], h, fest)
            q = guete2d(P2, T)
            mass[(f, name)] = (float(q.min()), len(T), len(fehlt),
                               int((q < 0.2).sum()))
    for f in (1, 2):
        check(f"Verhältnis {f}: das Größenfeld ändert nichts",
              mass[(f, "ohne")] == mass[(f, "mit")],
              f"{mass[(f, 'ohne')][1]} Dreiecke, Güte {mass[(f, 'ohne')][0]:.3f}")
    # Hier greift das **Randfeld** (mesher3d.RANDFELD) nicht: die Randstrecken
    # sind h oder groeber, und es schaltet sich erst unter RANDFELD_SCHWELLE
    # ein. Die festgelegte grobe Strecke bleibt also allein zustaendig.
    for f in (3, 8):
        a, b = mass[(f, "ohne")], mass[(f, "mit")]
        check(f"Verhältnis {f}: die schlechteste Güte steigt deutlich",
              b[0] > 1.3 * a[0], f"{a[0]:.3f} -> {b[0]:.3f}")
    check("bei Verhältnis 8 bleibt kein Splitter übrig",
          mass[(8, "ohne")][3] > 0 and mass[(8, "mit")][3] == 0,
          f"{mass[(8, 'ohne')][3]} -> {mass[(8, 'mit')][3]} Dreiecke unter 0.2")
    check("und keine Randstrecke geht dabei verloren",
          all(v[2] == 0 for v in mass.values()))


def test_randstrecken_sind_keine_glueckssache():
    """Dichtheit darf nicht vom Zufall abhaengen - 600 Flaechen zur Probe.

    Eine freie Delaunay-Zerlegung kennt keine Randbedingung: sie *kann* eine
    Randstrecke ueberspringen, und ob sie es tut, haengt an der Lage der
    Innenpunkte - also an der Phase des Gitters, an der Drehung der Flaeche,
    an Rundung. Ein Netz, dessen Dichtheit vom Zufall abhaengt, ist kein Netz;
    genau daran endeten am Drehlagermodell fuenf Koerper ohne Netz, obwohl ihr
    erster Anlauf ein gueltiges hatte.

    :func:`_dreiecke_2d` erzwingt die Randstrecken darum, statt zu hoffen:
    fehlt eine, fliegen die Innenpunkte in ihrer Umkreisscheibe heraus und es
    wird neu zerlegt. Jede Runde entfernt mindestens einen Punkt, also endet
    das Verfahren - und es fasst nie einen Randpunkt an.

    Geprueft wird das nicht an einem Beispiel, sondern an einer Stichprobe
    ueber den Raum, in dem es schiefging: Groesse, Teilung, Zielkantenlaenge,
    Drehung und Lage zufaellig, dazu drei Bauformen - der Streifen mit einer
    grob festgelegten Langseite (der gemessene Fall), die L-Form mit
    einspringender Ecke und die Platte mit ein bis drei Bohrungen.
    """
    rng = np.random.default_rng(11)
    zahl: dict = {}
    offen: dict = {}
    entartet = 0
    for versuch in range(600):
        art = ["Streifen", "L-Form", "Bohrungen"][versuch % 3]
        h = float(rng.uniform(0.01, 0.4))
        phi = float(rng.uniform(0, 2 * np.pi))
        v = rng.uniform(-2, 2, 2)
        R = np.array([[np.cos(phi), -np.sin(phi)], [np.sin(phi), np.cos(phi)]])
        ungueltig = False
        if art == "Streifen":
            n = int(rng.integers(3, 25))
            L, B = float(rng.uniform(0.1, 1.5)), float(rng.uniform(0.02, 1.0))
            ringe = [np.array([(L * i / n, 0.0) for i in range(n)] + [(L, B)]
                              + [(L - L * i / n, B) for i in range(1, n)]
                              + [(0.0, B)], float)]
        elif art == "L-Form":
            a, b = float(rng.uniform(0.3, 1.2)), float(rng.uniform(0.3, 1.2))
            ringe = [np.array([(0, 0), (a, 0), (a, b / 2), (a / 2, b / 2),
                               (a / 2, b), (0, b)], float)]
        else:
            sq = float(rng.uniform(0.4, 1.2))
            ringe = [np.array([(0, 0), (sq, 0), (sq, sq), (0, sq)], float)]
            kreise = []
            for _k in range(int(rng.integers(1, 4))):
                r = float(rng.uniform(0.02, 0.12))
                m = rng.uniform(0.2 * sq, 0.8 * sq, 2)
                nn = int(rng.integers(8, 30))
                w = np.linspace(0, 2 * np.pi, nn, endpoint=False)[::-1]
                ringe.append(np.column_stack([m[0] + r * np.cos(w), m[1] + r * np.sin(w)]))
                kreise.append((m, r))
            # Ueberlappende oder ueberstehende Bohrungen sind keine gueltige
            # Flaeche - sie gehoeren nicht in die Statistik.
            for i, (m1, r1) in enumerate(kreise):
                if (m1 - r1 < 0).any() or (m1 + r1 > sq).any():
                    ungueltig = True
                for (m2, r2) in kreise[i + 1:]:
                    if float(np.linalg.norm(m1 - m2)) < r1 + r2 + 1e-9:
                        ungueltig = True
        if ungueltig:
            entartet += 1
            continue
        ringe = [Rg @ R.T + v for Rg in ringe]
        _P2, _T, fehlt = M3._dreiecke_2d(ringe, h)
        zahl[art] = zahl.get(art, 0) + 1
        if fehlt:
            offen[art] = offen.get(art, 0) + 1
    for art in sorted(zahl):
        check(f"{art}: keine Fläche mit fehlender Randstrecke", offen.get(art, 0) == 0,
              f"{offen.get(art, 0)} von {zahl[art]}")
    check("die Stichprobe ist gross genug", sum(zahl.values()) > 400,
          f"{sum(zahl.values())} gültige Flächen, {entartet} entartete übergangen")


def _kantenzaehlung(T: np.ndarray) -> np.ndarray:
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    E.sort(axis=1)
    return np.unique(E, axis=0, return_counts=True)[1]


def _dreiecksguete(P: np.ndarray, T: np.ndarray) -> np.ndarray:
    p0, p1, p2 = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    fl = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    l2 = ((p1 - p0) ** 2).sum(1) + ((p2 - p1) ** 2).sum(1) + ((p0 - p2) ** 2).sum(1)
    return 4 * np.sqrt(3) * fl / np.maximum(l2, 1e-30)


def test_huelle_verfeinern_haelt_form():
    """Die Nachverfeinerung der Huelle halbiert die laengste Kante (Rivara)
    statt im Schwerpunkt zu teilen. Nachgestellt an der Platte mit Bohrung:
    drei Runden um die Bohrung, wie tetraedern_treu sie faehrt. Gemessen am
    Drehlager (V15) machte das Teilen im Schwerpunkt aus einer Huelle ohne
    Splitter in zwei Runden 2 391 Splitter (Guete min 0,165 -> 0,018)."""
    r = 0.4
    m = neues_modell()
    k = prisma(m, [[(0, 0), (2, 0), (2, 2), (0, 2)],
                   kreis_punkte(r, 48, 1.0, 1.0, umgekehrt=True)], 0.4)
    P, T, bericht = M3.randschale(m, k, 0.15)
    quelle = list(bericht["quelle"])
    kennung = list(bericht["kennung"])
    check("Huelle der Platte geschlossen", bool((_kantenzaehlung(T) == 2).all()), f"{len(T)} Dreiecke")
    q0 = float(_dreiecksguete(P, T).min())
    V0 = M3.huellvolumen(P, T)
    n0 = len(P)
    # Boden gehoert (angenommen) auch einem Nachbarn: geschuetzt. Die Linien
    # des Deckels gelten als gemeinsam: ihre Punkte sind gesperrt.
    deckel = m.flaechen["Deckel"]
    linien = set(deckel.linien or [])
    for loch in (deckel.oeffnungen or []):
        linien.update(loch)
    gesperrt = np.zeros(n0, bool)
    for i, kn in enumerate(kennung[:n0]):
        if isinstance(kn, tuple) and (kn[0] == "K" or (kn[0] == "L" and kn[1] in linien)):
            gesperrt[i] = True
    E0 = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    E0.sort(axis=1)
    ringkanten = {tuple(e) for e in E0 if gesperrt[e[0]] and gesperrt[e[1]]}
    check("Sperre greift: Deckelring und Eckknoten gesperrt", 0 < int(gesperrt.sum()) < n0 and len(ringkanten) >= 48,
          f"{int(gesperrt.sum())} Punkte, {len(ringkanten)} Ringkanten")

    def runden(teilen, P, T, quelle, g, n=3):
        for _ in range(n):
            schutz = {i for i, q in enumerate(quelle) if q == "Boden"}
            schwer = P[T].mean(axis=1)
            nah = np.flatnonzero(np.linalg.norm(schwer[:, :2] - np.array([1.0, 1.0]), axis=1) < 2.0 * r)
            welche = [int(i) for i in nah if int(i) not in schutz]
            if teilen is M3.huelle_verfeinern:
                P, T, quelle = teilen(P, T, welche, quelle, schutz=schutz, gesperrt=g)
            else:
                P, T, quelle = teilen(P, T, welche, quelle)
            g = np.concatenate([g, np.zeros(len(P) - len(g), bool)])
        return P, T, quelle

    P1, T1, q1 = runden(M3.huelle_verfeinern, P, T, quelle, gesperrt)
    g1 = float(_dreiecksguete(P1, T1).min())
    check("drei Runden Halbieren: Huelle bleibt geschlossen", bool((_kantenzaehlung(T1) == 2).all()), f"{len(T1)} Dreiecke")
    check("… und feiner (mehr Dreiecke, neue Punkte)", len(T1) > 1.5 * len(T) and len(P1) > n0, f"{len(T)} -> {len(T1)}")
    # Rivaras Schranke gilt dem kleinsten Winkel (mindestens die Haelfte).
    # Wo die laengste Kante gesperrt ist (Boden geschuetzt, Deckelring
    # gesperrt), bleibt nur die Teilung im Schwerpunkt; gemessen an dieser
    # Platte: Guete min 0,555 -> 0,128 - im Schwerpunkt ueberall geteilt
    # (alter Weg): 0,029, also Splitter.
    print(f"    Guete min {q0:.3f} -> {g1:.3f}")
    close("… das Huellvolumen bleibt (Punkte liegen auf der Huelle, Umlaufsinn bleibt)", M3.huellvolumen(P1, T1), V0, 1e-9, " m^3")
    check("… kein Splitter (Guete < 0,1)", int((_dreiecksguete(P1, T1) < 0.1).sum()) == 0, f"{int((_dreiecksguete(P1, T1) < 0.1).sum())}")
    neu = P1[n0:]
    check("geschuetzter Boden: kein neuer Punkt auf z = 0", bool((np.abs(neu[:, 2]) > 1e-9).all()) if len(neu) else False, f"{len(neu)} neue Punkte")
    check("… Bodendreiecke unveraendert", sum(1 for q in q1 if q == "Boden") == sum(1 for q in quelle if q == "Boden"))
    E1 = np.vstack([T1[:, [0, 1]], T1[:, [1, 2]], T1[:, [2, 0]]])
    E1.sort(axis=1)
    E1 = {tuple(e) for e in E1}
    check("gesperrte Linien: jede Ringkante des Deckels ist noch da", all(e in E1 for e in ringkanten), f"{sum(e in E1 for e in ringkanten)} von {len(ringkanten)}")
    # Zum Vergleich der alte Weg: dieselben drei Runden im Schwerpunkt
    P2, T2, _ = runden(M3._huelle_schwerpunkt_teilen, P, T, quelle, gesperrt)
    g2 = float(_dreiecksguete(P2, T2).min())
    check("Teilen im Schwerpunkt fiele durch (Guete unter 0,1)", g2 < 0.1, f"{q0:.3f} -> {g2:.3f}")


def test_gitterindex_zelle():
    """Die Zelle des Gitterindex folgt der typischen Dreiecksgroesse, nicht dem
    groessten Dreieck. Eine ebene Aussenflaeche mit einem 85-mm-Dreieck machte
    am Drehlager (V31, 21 716 Dreiecke, Median 5 mm) 22 Zellen mit 1148
    Kandidaten je Zelle: innen() brauchte 4,49 s fuer 60 000 Punkte, mit
    2 x Median 0,19 s - bei gleichem Ergebnis."""
    m = neues_modell()
    k = prisma(m, [[(0, 0), (2, 0), (2, 2), (0, 2)],
                   kreis_punkte(0.2, 48, 1.0, 1.0, umgekehrt=True)], 0.4)
    m.netz.ziellaenge = 0.15
    P, T, _b = M3.randschale(m, k, 0.15, [], None)
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    kanten = np.concatenate([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                             np.linalg.norm(a - c, axis=1)])
    med = float(np.median(kanten))
    idx = M3.Gitterindex(P, T)
    close("die Zelle ist das Doppelte der Median-Kantenlaenge", idx.zelle, 2 * med, 1e-12, " m")
    check("und damit kleiner als das groesste Dreieck",
          idx.zelle < float(np.max(idx.hi - idx.lo)),
          f"Zelle {idx.zelle * 1e3:.1f} mm, groesstes Dreieck {float(np.max(idx.hi - idx.lo)) * 1e3:.1f} mm")
    close("mit Zielkantenlaenge h ist die Zelle hoechstens 0,5 h",
          M3.Gitterindex(P, T, h=0.01).zelle, 0.005, 1e-12, " m")
    close("und bleibt bei grossem h das Doppelte des Medians",
          M3.Gitterindex(P, T, h=10.0).zelle, 2 * med, 1e-12, " m")
    rng = np.random.default_rng(3)
    q = P.min(axis=0) + rng.random((5000, 3)) * (P.max(axis=0) - P.min(axis=0))
    grob = M3.Gitterindex(P, T, zelle=float(np.max(idx.hi - idx.lo)))
    fein, alt = M3.innen(q, P, T, idx), M3.innen(q, P, T, grob)
    check("innen() liefert mit feiner und grober Zelle dasselbe",
          np.array_equal(fein, alt), f"{int(fein.sum())} / {int(alt.sum())} Punkte innen")


def test_enge_huellkanten_werden_benannt():
    """Die Diagnose der engen Hüllkanten: sie sind die Quelle der Splitter, die
    kein Volumenschritt mehr los wird (Drehlager, 21.09.2026: bei allen 189
    Splittern war die kürzeste Kante eine Hüllkante von 0,13 bis 1,36 mm bei
    h = 50 mm). Geprüft wird, dass sie gezählt und **nach Herkunft** benannt
    werden - Linie, zwei Linien oder Innennetz."""
    from statik3d.mesher3d import _enge_huellkanten, MINDESTWEITE_TEILER
    h = 0.05
    weite = h / MINDESTWEITE_TEILER
    # Vier Punkte: zwei davon 0,4 mm auseinander (auf derselben Linie L1),
    # einer auf L2, einer ohne Kennung (Innennetz)
    P = np.array([[0.0, 0.0, 0.0], [0.0004, 0.0, 0.0], [0.05, 0.0, 0.0], [0.02, 0.03, 0.0]])
    T = np.array([[0, 1, 3], [1, 2, 3]], int)
    kenn = [("L", "L1", 1), ("L", "L1", 2), ("L", "L2", 1), None]
    aus = _enge_huellkanten(P, T, kenn, ["F1", "F1"], h)
    check("die enge Kante wird gefunden", aus["anzahl"] == 1, str(aus["anzahl"]))
    check("mit ihrer Länge und der Mindestweite",
          abs(aus["kuerzeste"] - 0.0004) < 1e-12 and abs(aus["weite"] - weite) < 1e-12,
          f"{aus['kuerzeste'] * 1e3:.3f} mm, Weite {aus['weite'] * 1e3:.2f} mm")
    check("und nach Herkunft benannt: dieselbe Linie",
          aus["je_art"] == {"auf der Linie L1": 1}, str(aus["je_art"]))
    # Dieselben Punkte, aber der zweite gehört einer anderen Linie
    kenn2 = [("L", "L1", 1), ("L", "L3", 0), ("L", "L2", 1), None]
    aus2 = _enge_huellkanten(P, T, kenn2, ["F1", "F1"], h)
    check("zwei eng zusammenlaufende Linien werden als solche genannt",
          list(aus2["je_art"]) == ["zwischen den Linien L1 und L3"], str(aus2["je_art"]))
    # Ein Innennetzpunkt nah am Rand
    P3 = np.array([[0.0, 0.0, 0.0], [0.05, 0.0, 0.0], [0.02, 0.03, 0.0], [0.0003, 0.0, 0.0]])
    T3 = np.array([[0, 1, 2], [0, 2, 3]], int)
    aus3 = _enge_huellkanten(P3, T3, [("L", "L1", 1), ("L", "L1", 2), None, None], ["F1", "F1"], h)
    check("ein Punkt des Innennetzes am Rand wird als solcher genannt",
          aus3["anzahl"] == 1 and "Innennetz" in list(aus3["je_art"])[0], str(aus3["je_art"]))
    check("ohne enge Kante meldet die Diagnose nichts",
          _enge_huellkanten(np.array([[0.0, 0, 0], [0.05, 0, 0], [0.02, 0.03, 0]]),
                            np.array([[0, 1, 2]], int), [None] * 3, ["F1"], h)["anzahl"] == 0)
    # Am Prüfkörper: eine Bohrung r = 2 mm bei h = 50 mm erzeugt sie, und das
    # Protokoll nennt sie mit Zahl, Mindestweite und Herkunft
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_netzfeld import platte_mit_bohrungen
    from statik3d import mesher
    m, k = platte_mit_bohrungen(0.4, 0.3, 0.1, bohrungen=((0.2, 0.15, 0.002),))
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    m.netz.sweep = False
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    zeile = [z for z in log if "Mindestweite" in z]
    check("das Protokoll warnt vor den engen Hüllkanten der winzigen Bohrung",
          zeile and "Hüllkanten unter der Mindestweite" in zeile[0], str(zeile[:1])[:150])


def test_abnahme_warnstufe_splitter():
    """Die zweite Stufe der Abnahme: Splitter (Formguete unter 0,10) werden je
    Koerper als WARNUNG mit Zahl und Elementnummern genannt, ohne die
    Rechnung anzuhalten; unter 0,05 bleibt es ein FEHLER (Anforderungen 3.4,
    21.09.2026)."""
    from statik3d import diagnose
    from statik3d.netzguete import guete as _guete
    m = Model()
    m.add_material(Material.steel("S235"))
    # Ein guter Tetraeder und ein flacher (vierter Knoten nahe der Grundebene)
    n0 = m.add_node(0.0, 0.0, 0.0)
    n1 = m.add_node(1.0, 0.0, 0.0)
    n2 = m.add_node(0.0, 1.0, 0.0)
    n3 = m.add_node(0.0, 0.0, 1.0)
    n4 = m.add_node(1.0, 1.0, 0.0)
    n5 = m.add_node(0.7, 0.7, 0.013)     # q = 12 (z/2)^(2/3) / 5,34 = 0,079
    e_gut = m.add_element("tet4", [n0, n1, n2, n3], "S235", group="V1")
    e_flach = m.add_element("tet4", [n1, n4, n2, n5], "S235", group="V1")
    m.add_line("L1", [n0, n1]); m.add_line("L2", [n1, n2]); m.add_line("L3", [n2, n0])
    m.add_flaeche("F1", ["L1", "L2", "L3"], material="S235")
    m.add_flaeche("F2", ["L1", "L2", "L3"], material="S235")
    m.add_flaeche("F3", ["L1", "L2", "L3"], material="S235")
    m.add_flaeche("F4", ["L1", "L2", "L3"], material="S235")
    k = m.add_koerper("V1", ["F1", "F2", "F3", "F4"], material="S235")
    k.elemente = [e_gut, e_flach]
    k.randtreue = 1.0
    q = _guete(m)
    check("der flache Tetraeder liegt zwischen 0,05 und 0,10", 0.05 <= float(q[e_flach]) < 0.10, f"{q[e_flach]:.3f}")
    fehler = [b for b in diagnose.abnahme(m) if b.pruefung in ("Elementgüte", "Splitter")]
    check("ohne warnungen=True kein Befund zur Guete (kein Element unter 0,05)", not fehler, str([b.pruefung for b in fehler]))
    alle = diagnose.abnahme(m, warnungen=True)
    # Die vier Randflaechen dieses Koerpers sind dieselbe (Huelle nicht
    # dicht): seit dem 23.09.2026 steht dafuer auch die WARNUNG
    # „Volumenbilanz nicht geprüft" da (B038) - sie gehoert nicht zu den
    # Splittern, um die es hier geht
    warn = [b for b in alle if b.stufe == "WARNUNG" and b.pruefung != "Volumenbilanz nicht geprüft"]
    check("mit warnungen=True eine WARNUNG 'Splitter' mit Zahl, Koerper und Elementnummer",
          len(warn) == 1 and warn[0].pruefung == "Splitter" and warn[0].objekt == "V1"
          and warn[0].element == e_flach and "1 von 2 Elementen" in warn[0].text, str([b.text for b in warn])[:160])
    check("die Warnung haelt nichts an: kein FEHLER darunter", not any(b.stufe == "FEHLER" and b.pruefung == "Splitter" for b in alle))
    # Unter 0,05 bleibt es ein FEHLER - und die Warnung nennt ihn mit
    m.nodes[n5] = [0.7, 0.7, 0.0045]   # q = 0,039
    q = _guete(m)
    check("noch flacher: unter 0,05", float(q[e_flach]) < 0.05, f"{q[e_flach]:.3f}")
    alle = diagnose.abnahme(m, warnungen=True)
    check("FEHLER Elementgüte und WARNUNG Splitter nebeneinander",
          any(b.stufe == "FEHLER" and b.pruefung == "Elementgüte" for b in alle)
          and any(b.stufe == "WARNUNG" and b.pruefung == "Splitter" for b in alle),
          str([(b.stufe, b.pruefung) for b in alle]))


def test_luecke_im_netzrand_geschlossen():
    """Befund der Statik3D-Sitzung vom 23.09.2026: der freie Vernetzer liess an
    5 von 9 L-, T- und U-Prismen einen Tetraeder an der Oberflaeche weg
    (0,003 bis 0,113 % des Koerpers), am Wuerfel mit angehobener Deckelecke
    einen ganz eingeschlossenen. Drei Ursachen, drei Kuren:

    * ``innen()`` zaehlte einen Strahl doppelt, der genau die gemeinsame Kante
      zweier Huelldreiecke trifft - jetzt entscheidet die Kante wie fuer einen
      um (eps, eps^2) verschobenen Punkt (Simulation of Simplicity);
    * ein Gitterpunkt stand mitten in einer Facette 0,85 mm vor der Huelle -
      der flache Tetraeder dazwischen ist nie Delaunay; Startpunkte halten
      jetzt RANDABSTAND_FLAECHE * h zur Huelle;
    * ``tetraedern_treu`` nahm 0,01 % Fehlbetrag und 99,9 % Randtreue hin -
      jetzt gilt der Rauminhalt (TREU_VOLUMEN), und nur echte Dellen
      (``echte_dellen``, nicht der Diagonaltausch eines Huellvierecks) treiben
      die Nachfuehrung.
    Abnahme wie im Auftrag: Summe der Elementvolumina gleich Huellvolumen an
    allen neun Prismen und am Wuerfel, keine Abnahme-Befunde."""
    import contextlib
    import io as _io
    from statik3d import mesher, diagnose as dg
    from test_diagnose import _extrudiert, _wuerfel_angehoben
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]
    T = [(0, 0), (2, 0), (2, 0.4), (1.2, 0.4), (1.2, 1.5), (0.8, 1.5), (0.8, 0.4), (0, 0.4)]
    U = [(0, 0), (2, 0), (2, 1.5), (1.4, 1.5), (1.4, 0.5), (0.6, 0.5), (0.6, 1.5), (0, 1.5)]

    def flaeche(P):
        x = np.array([q[0] for q in P])
        y = np.array([q[1] for q in P])
        return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    befunde = ("Lücke im Netzrand", "Seiten im Inneren", "Volumenbilanz", "Netzrand neben der Hülle")
    for name, P, z1 in (("L", L, 0.4), ("T", T, 0.3), ("U", U, 0.4)):
        for h in (0.25, 0.2, 0.1):
            m = Model(name)
            m.add_material(Material.steel("S235"))
            k = _extrudiert(m, P, 0.0, z1)
            with contextlib.redirect_stdout(_io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1, hs={"K": h})
            V = netzvolumen(m, k.elemente)
            soll = flaeche(P) * z1
            bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in befunde]
            check(f"{name}-Prisma h = {h}: Rauminhalt gleich der Huelle, kein Befund",
                  abs(V - soll) < 1e-9 * soll and not bef,
                  f"{len(k.elemente)} tet4, {(soll - V) / soll * 100:+.5f} %, "
                  + "; ".join(f"{b.stufe} {b.pruefung}" for b in bef))
    with contextlib.redirect_stdout(_io.StringIO()):
        m, k, els = _wuerfel_angehoben(0.5, 0.1)
    bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in befunde]
    check("Wuerfel mit angehobener Deckelecke, h = 0,1: kein eingeschlossener Tetraeder fehlt",
          not bef, f"{len(els)} tet4; " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    # Ruecknahmeprobe: alle drei Kuren zurueck - dann sind die Fehlbetraege
    # der Statik3D-Sitzung wieder da (0,079 % am L-Prisma, 0,113 % am
    # T-Prisma; die Elementzahl war 821 bzw. 663 und ist seit der Regel fuer
    # die Kappenpunkte 809 bzw. 677 - gemessen 23.09.2026 abends). Jede Kur
    # allein laesst sich nicht zuruecknehmen: die anderen beiden aendern die
    # Punktmenge, und der Gleichstand an der Kante tritt dann nicht ein
    # (gemessen 23.09.2026 - "nur Kante zurueck" 634 Tetraeder, 0,0000 %).
    # Das Kantenkippen (huelle_kippen) aendert an dieser Luecke nichts - sie
    # kommt aus der Gitterphase, nicht aus dem Gleichstand an der Kugel
    # (mit und ohne KIPP_RUNDEN dieselben Zahlen).
    alt = (M3._seite_mit_ausweichung, M3.RANDABSTAND_FLAECHE, M3.TREU_VOLUMEN, M3.TREU_RUNDEN)
    M3._seite_mit_ausweichung = lambda l, gx, gy: l >= 0
    M3.RANDABSTAND_FLAECHE = 0.0
    M3.TREU_VOLUMEN, M3.TREU_RUNDEN = 1e-4, 3
    try:
        zurueck = {}
        for name, P, z1, h in (("L", L, 0.4, 0.25), ("T", T, 0.3, 0.2)):
            m = Model(name)
            m.add_material(Material.steel("S235"))
            k = _extrudiert(m, P, 0.0, z1)
            with contextlib.redirect_stdout(_io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1, hs={"K": h})
            soll = flaeche(P) * z1
            zurueck[name] = (len(k.elemente), (soll - netzvolumen(m, k.elemente)) / soll * 100)
    finally:
        (M3._seite_mit_ausweichung, M3.RANDABSTAND_FLAECHE, M3.TREU_VOLUMEN,
         M3.TREU_RUNDEN) = alt
    check("Ruecknahmeprobe: ohne die drei Kuren fehlen am L-Prisma wieder 0,079 %",
          abs(zurueck["L"][1] - 0.0788) < 0.001,
          f"{zurueck['L'][0]} tet4, {zurueck['L'][1]:+.4f} %")
    check("  und am T-Prisma 0,113 % an der einspringenden Kante",
          abs(zurueck["T"][1] - 0.1128) < 0.001,
          f"{zurueck['T'][0]} tet4, {zurueck['T'][1]:+.4f} %")


def test_huelle_kippen():
    """Zweiter Auftrag der Statik3D-Sitzung (23.09.2026): die Luecke an der
    rechtwinklig einspringenden Kante. Fuenf Huellpunkte liegen dort auf
    einer Kugel (Thales), Qhull waehlt drei Tetraeder um die Kante quer
    durch die Kerbe, das Huelldreieck fehlt. ``huelle_kippen`` nimmt die
    andere Antwort (zwei Tetraeder mit dem Dreieck als Seite), ohne einen
    Punkt zu setzen. Gemessen 23.09.2026: Stichprobe 3 Prismen x 23
    Ziellaengen 11 -> 2 von 69 mit Fehlbetrag, die Stichprobe der
    Statik3D-Sitzung 1 -> 0 von 69."""
    import contextlib
    import io as _io
    from statik3d import mesher
    from statik3d.elements.solid import solid_volume
    # 1) der reine Fall: Dreieck a-b-c in z = 0, Kante u-w durchstoesst es,
    #    drei Tetraeder um u-w
    Pn = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0.3, 0.3, 1.0], [0.3, 0.3, -1.0],
                   [3, 3, 3]], float)
    a, b, c, u, w = 0, 1, 2, 3, 4
    TET = np.array([[u, w, a, b], [u, w, b, c], [u, w, c, a], [a, b, 5, u]], int)
    T = np.array([[a, b, c]], int)
    TET2, n = M3.huelle_kippen(Pn, TET, Pn[:3], T)
    seiten = {tuple(sorted(x)) for t in TET2.tolist() for x in
              ((t[0], t[1], t[2]), (t[0], t[1], t[3]), (t[0], t[2], t[3]), (t[1], t[2], t[3]))}
    check("eine Kante mit drei Tetraedern, die das Huelldreieck durchstoesst, wird gekippt",
          n == 1 and len(TET2) == 3 and (a, b, c) in seiten, f"{n} gekippt, {len(TET2)} Tetraeder")
    V = sum(abs(np.linalg.det(Pn[t][1:] - Pn[t][0])) / 6 for t in TET2.tolist())
    V0 = sum(abs(np.linalg.det(Pn[t][1:] - Pn[t][0])) / 6 for t in TET.tolist())
    close("  und der Rauminhalt bleibt derselbe", V, V0, 1e-12)
    # 2) vier Tetraeder um die Kante: kein 3-2-Kippen moeglich, nichts geschieht
    Pn4 = np.vstack([Pn, [[-0.5, -0.5, 0.0]]])
    d = 6
    TET4 = np.array([[u, w, a, b], [u, w, b, c], [u, w, c, d], [u, w, d, a]], int)
    TET4b, n4 = M3.huelle_kippen(Pn4, TET4, Pn4[:3], T)
    check("eine Kante mit vier Tetraedern bleibt stehen (kein 3-2-Kippen)", n4 == 0 and len(TET4b) == 4,
          f"{n4} gekippt")
    # 2b) drei Tetraeder an a, b, c und ein vierter um dieselbe Kante, der
    #     keine der drei Ecken traegt: der Ring hat vier, nichts wird gekippt
    Pn5 = np.vstack([Pn, [[-0.5, -0.5, 0.0], [-0.6, -0.4, 0.3]]])
    TET5 = np.array([[u, w, a, b], [u, w, b, c], [u, w, c, a], [u, w, 6, 7]], int)
    TET5b, n5 = M3.huelle_kippen(Pn5, TET5, Pn5[:3], T)
    check("  auch wenn der vierte Tetraeder keine Ecke des Dreiecks traegt", n5 == 0 and len(TET5b) == 4,
          f"{n5} gekippt")
    # 3) am Prisma der Statik3D-Sitzung: T-Prisma (test_diagnose._extrudiert),
    #    h = 0,09 - der Fall fuer test_diagnose: ohne Kippen 0,0003 %
    #    Fehlbetrag nach acht Durchgaengen (10 751 Tetraeder), mit Kippen
    #    exakt im ersten (7 864; gemessen 23.09.2026)
    from test_diagnose import _extrudiert
    T = [(0, 0), (2, 0), (2, 0.4), (1.2, 0.4), (1.2, 1.5), (0.8, 1.5), (0.8, 0.4), (0, 0.4)]

    def lauf():
        m = Model("T")
        m.add_material(Material.steel("S235"))
        k = _extrudiert(m, T, 0.0, 0.3)
        log = []
        with contextlib.redirect_stdout(_io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1, hs={"K": 0.09})
        V = sum(solid_volume(m.elements[i].typ, m.nodes[m.elements[i].nodes]) for i in k.elemente)
        soll = (2 * 0.4 + 0.4 * 1.1) * 0.3
        return len(k.elemente), (soll - V) / soll * 100, log
    n_mit, fehl_mit, log_mit = lauf()
    check("T-Prisma h = 0,09: Rauminhalt exakt im ersten Durchgang, eine Kante gekippt",
          abs(fehl_mit) < 1e-9 and any("gekippt" in z for z in log_mit)
          and not any("Lücke" in z for z in log_mit),
          f"{n_mit} tet4, {fehl_mit:+.5f} %, " + "; ".join(z.strip()[:70] for z in log_mit if "gekippt" in z))
    alt = M3.KIPP_RUNDEN
    M3.KIPP_RUNDEN = 0
    try:
        n_ohne, fehl_ohne, log_ohne = lauf()
    finally:
        M3.KIPP_RUNDEN = alt
    check("  Ruecknahmeprobe: ohne Kippen bleibt die Luecke (gemessen 0,0003 %) und wird gemeldet",
          fehl_ohne > 1e-5 and any("Lücke im Netzrand" in z for z in log_ohne),
          f"{n_ohne} tet4, {fehl_ohne:+.5f} %")


def test_kappenpunkte_halten_abstand():
    """Zweiter Auftrag (23.09.2026), Aufgabe 2: an der Bohrung der Buchse
    r 50/100, h = 20 mm behielten 4 tet10 gerade Kanten, dazu eine Luecke
    von 0,0023 %. Ursache: der Punkt, der eine Kappe **im ebenen Deckel**
    aufloesen sollte (vier Punkte am Bohrungsrand und im Deckel), ging um
    die halbe Kappenkante - bis 36 mm - senkrecht in den Koerper und landete
    0,08 bis 2 mm neben der Bohrungswand. Jetzt hoechstens KAPPEN_WEG
    Sollgroessen weit und mit KAPPEN_RANDABSTAND zur ganzen Huelle."""
    import contextlib
    import io as _io
    from statik3d import mesher

    def lauf():
        m = neues_modell()
        k = buchse(m, 0.1, 0.05, 0.1)
        k.ordnung = 2
        m.netz.sweep = False
        m.netz.ziellaenge = 0.02
        m.netz.dichte = "eigene"
        log = []
        with contextlib.redirect_stdout(_io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1)
        rueck = [z for z in log if "behalten gerade Kanten" in z]
        luecke = [z for z in log if "Lücke im Netzrand" in z]
        return len(k.elemente), rueck, luecke
    alt = (M3.KRUMM_ANLAEUFE, M3.KAPPEN_RANDABSTAND, M3.KAPPEN_WEG)
    M3.KRUMM_ANLAEUFE = 0                   # ohne oertliche Nachhilfe: die Regel allein
    try:
        n_neu, rueck_neu, luecke_neu = lauf()
        M3.KAPPEN_RANDABSTAND, M3.KAPPEN_WEG = 0.0, float("inf")
        n_alt, rueck_alt, luecke_alt = lauf()
    finally:
        M3.KRUMM_ANLAEUFE, M3.KAPPEN_RANDABSTAND, M3.KAPPEN_WEG = alt
    check("Buchse r 50/100, h = 20 mm, tet10: keine gerade Kante, keine Luecke - ohne oertliche Verfeinerung",
          not rueck_neu and not luecke_neu, f"{n_neu} tet10; " + "; ".join(z.strip()[:80] for z in rueck_neu + luecke_neu))
    check("  Ruecknahmeprobe: mit der alten Kappenregel kommen die geraden Kanten und die Luecke wieder",
          rueck_alt and luecke_alt, f"{n_alt} tet10; " + "; ".join(z.strip()[:90] for z in rueck_alt + luecke_alt))


def test_krumme_kanten_oertlich_feiner():
    """Zweiter Auftrag (23.09.2026), Aufgabe 2: wo eine gekruemmte tet10-Kante
    die Jacobi-Determinante umklappen liesse, wird **oertlich feiner**
    vernetzt - die betroffene Flaeche und ihre nicht gemeinsamen Linien um
    VERFEINERN_FAKTOR, der Koerper behaelt seine Kantenlaenge -, bis die
    Kante gueltig ist (koerper_vorbereiten, krumme_kanten_pruefen). Fall mit
    groben Boegen: Buchse r 50/100 bei 36 Grad je Abschnitt und h = 35 mm,
    5 ungueltige tet10 (gemessen 23.09.2026)."""
    import contextlib
    import io as _io
    from statik3d import mesher
    from statik3d.elements.solid import jacobi_volumen

    def lauf():
        m = neues_modell()
        k = buchse(m, 0.1, 0.05, 0.1)
        k.ordnung = 2
        m.netz.sweep = False
        m.netz.ziellaenge = 0.035
        m.netz.dichte = "eigene"
        m.netz.bogenwinkel = 36.0
        log = []
        with contextlib.redirect_stdout(_io.StringIO()):
            mesher.modell_vernetzen(m, log, workers=1)
        det = [jacobi_volumen("tet10", m.nodes[m.elements[i].nodes]) for i in k.elemente]
        return (len(k.elemente), [z for z in log if "behalten gerade Kanten" in z],
                [z for z in log if "örtlich feiner" in z], min(d["det_min"] / d["det_max"] for d in det))
    n_mit, rueck_mit, oertlich, det_mit = lauf()
    check("Buchse 36 Grad, h = 35 mm: die Mantelflaechen werden oertlich feiner, keine gerade Kante bleibt",
          not rueck_mit and oertlich and det_mit > 0,
          f"{n_mit} tet10, kleinste bezogene Determinante {det_mit:.3f}; " + "; ".join(z.strip()[:150] for z in oertlich))
    alt = M3.KRUMM_ANLAEUFE
    M3.KRUMM_ANLAEUFE = 0
    try:
        n_ohne, rueck_ohne, _o, _d = lauf()
    finally:
        M3.KRUMM_ANLAEUFE = alt
    check("  Ruecknahmeprobe: ohne die oertlichen Anlaeufe behalten 5 tet10 gerade Kanten (872 Elemente)",
          rueck_ohne and n_ohne < n_mit, f"{n_ohne} tet10; " + "; ".join(z.strip()[:110] for z in rueck_ohne))


def test_bogenwinkel_je_koerper():
    """Zweiter Auftrag (23.09.2026), Aufgabe 3 (V3): der Bogenwinkel je
    Abschnitt ist einstellbar - am Modell (``Netzeinstellungen.bogenwinkel``)
    und je Koerper (``Volumenkoerper.bogenwinkel``), Vorgabe wie bisher 18
    Grad; an einer Linie zweier Koerper gilt der kleinere Winkel."""
    import contextlib
    import io as _io
    from statik3d import mesher

    def kreisknoten(m):
        X = np.asarray(m.nodes, float)
        return int(np.count_nonzero((np.abs(np.hypot(X[:, 0], X[:, 1]) - 0.1) < 1e-9) & (np.abs(X[:, 2]) < 1e-9)))

    def lauf(modell_winkel=None, koerper_winkel=None):
        # Zylinder r = 100, Hoehe 300 mm, h = 80 mm: die Laengenregel gaebe dem
        # Halbkreis 4 Abschnitte, die Kruemmung bestimmt (5 bei 36, 10 bei 18 Grad)
        m = neues_modell()
        k = buchse(m, 0.1, 0.0, 0.3)
        m.netz.sweep = False
        m.netz.ziellaenge = 0.08
        m.netz.dichte = "eigene"
        if modell_winkel:
            m.netz.bogenwinkel = modell_winkel
        if koerper_winkel:
            k.bogenwinkel = koerper_winkel
        with contextlib.redirect_stdout(_io.StringIO()):
            mesher.modell_vernetzen(m, [], workers=1)
        return kreisknoten(m), len(m.elements)
    n18, e18 = lauf()
    n36m, e36m = lauf(modell_winkel=36.0)
    n36k, e36k = lauf(koerper_winkel=36.0)
    n12k, e12k = lauf(modell_winkel=36.0, koerper_winkel=12.0)
    check("Vorgabe 18 Grad: 20 Knoten auf dem Grundkreis", n18 == 20, f"{n18} Knoten, {e18} Elemente")
    check("Netzeinstellung 36 Grad: 10 Knoten", n36m == 10 and e36m < e18, f"{n36m} Knoten, {e36m} Elemente")
    check("Vorgabe am Koerper 36 Grad: 10 Knoten", n36k == 10, f"{n36k} Knoten, {e36k} Elemente")
    check("der Koerper darf feiner sein als das Modell (12 gegen 36 Grad): 30 Knoten", n12k == 30,
          f"{n12k} Knoten, {e12k} Elemente")
    m = neues_modell()
    k1 = buchse(m, 0.1, 0.0, 0.3, "V1")
    k1.bogenwinkel = 36.0
    je = M3.bogenwinkel_je_linie(m)
    check("bogenwinkel_je_linie nennt jede Linie des Koerpers mit seinem Winkel",
          set(je) == {ln for f in k1.flaechen for ln in m.flaechen[f].linien} and set(je.values()) == {36.0},
          f"{len(je)} Linien")
    k1.bogenwinkel = None
    check("  und nichts, wenn kein Koerper einen Winkel vorgibt", M3.bogenwinkel_je_linie(m) == {}, "")
    check("  die Vorgabe des Modells bleibt 18 Grad", M3.bogenwinkel_vorgabe(m) == 18.0, f"{M3.bogenwinkel_vorgabe(m)}")
    # Zwei Koerper an einer Linie (gestapelte Zylinder, Mittelkreis gemeinsam):
    # der zweite ohne eigene Vorgabe zaehlt mit der des Modells - die kleinere gilt
    m2 = neues_modell()
    kA, kB = gestapelte_zylinder(m2, 0.1, 0.1, 0.1)
    kA.bogenwinkel = 36.0
    je = M3.bogenwinkel_je_linie(m2)
    check("Koerper A 36 Grad, Koerper B ohne Vorgabe: der gemeinsame Kreis bleibt bei 18, der eigene Grundkreis bekommt 36",
          je.get("KM1") == 18.0 and je.get("KU1") == 36.0 and "KO1" not in je, str(je))
    kB.bogenwinkel = 12.0
    je = M3.bogenwinkel_je_linie(m2)
    check("  beide mit Vorgabe (36 und 12): der gemeinsame Kreis bekommt 12",
          je.get("KM1") == 12.0 and je.get("KU1") == 36.0 and je.get("KO1") == 12.0, str(je))
    m2.netz.sweep = False
    m2.netz.ziellaenge = 0.08
    m2.netz.dichte = "eigene"
    with contextlib.redirect_stdout(_io.StringIO()):
        mesher.modell_vernetzen(m2, [], workers=1)
    X = np.asarray(m2.nodes, float)
    r = np.hypot(X[:, 0], X[:, 1])
    def kreis(z):
        return int(np.count_nonzero((np.abs(r - 0.1) < 1e-9) & (np.abs(X[:, 2] - z) < 1e-9)))
    # Der Mantel ist eine abgebildete Vierseitflaeche: Grund- und Mittelkreis
    # sind gegenueberliegende Seiten und bekommen dieselbe Teilung - die
    # feinere (12 Grad = 30 Knoten) zieht den Grundkreis mit (Linienteilung)
    check("  vernetzt: Mittel- und Deckkreis 30 Knoten (12 Grad), der Grundkreis ueber den Mantel gebunden auch 30",
          kreis(0.0) == 30 and kreis(0.1) == 30 and kreis(0.2) == 30,
          f"{kreis(0.0)} / {kreis(0.1)} / {kreis(0.2)} Knoten")


def gestapelte_zylinder(m: Model, r: float, h1: float, h2: float):
    """Zwei Zylinder uebereinander (Koerper A unten, B oben), die sich die
    Mittelkreisflaeche teilen; Linien KU*, KM*, KO* (Kreise), SA*, SB*
    (Mantellinien). Rueckgabe (A, B)."""
    satz = []
    for z, marke in ((0.0, "U"), (h1, "M"), (h1 + h2, "O")):
        a = m.add_node(-r, 0, z)
        b = m.add_node(r, 0, z)
        m.add_line(f"K{marke}1", [a, b], "arc", punkte=[(-r, 0, z), (0, r, z), (r, 0, z)])
        m.add_line(f"K{marke}2", [b, a], "arc", punkte=[(r, 0, z), (0, -r, z), (-r, 0, z)])
        satz.append((a, b))
    (au, bu), (am, bm), (ao, bo) = satz
    m.add_line("SA1", [au, am])
    m.add_line("SA2", [bu, bm])
    m.add_line("SB1", [am, ao])
    m.add_line("SB2", [bm, bo])
    m.add_flaeche("Grund", ["KU1", "KU2"], material="S235")
    m.add_flaeche("Mitte", ["KM1", "KM2"], material="S235")
    m.add_flaeche("Deckel", ["KO1", "KO2"], material="S235")
    m.add_flaeche("MantelA1", ["KU1", "SA2", "KM1", "SA1"], material="S235")
    m.add_flaeche("MantelA2", ["KU2", "SA1", "KM2", "SA2"], material="S235")
    m.add_flaeche("MantelB1", ["KM1", "SB2", "KO1", "SB1"], material="S235")
    m.add_flaeche("MantelB2", ["KM2", "SB1", "KO2", "SB2"], material="S235")
    kA = m.add_koerper("A", ["Grund", "Mitte", "MantelA1", "MantelA2"], material="S235")
    kB = m.add_koerper("B", ["Mitte", "Deckel", "MantelB1", "MantelB2"], material="S235")
    return kA, kB


def test_flache_tetraeder_nach_eigener_groesse():
    """Nachtrag der Statik3D-Sitzung (24.09.2026, B101): flache Tetraeder
    wurden an FLACH * h^3 mit dem h des **Koerpers** aussortiert; an einer
    feinen Bohrung (Sehnen 2-7 mm bei h = 50 mm) fielen so Tetraeder mit
    1,7-11 % Dicke heraus, die Abnahme meldete einen Riss. Jetzt zaehlt die
    eigene laengste Kante (flache_tetraeder)."""
    import contextlib
    import io as _io
    from statik3d import mesher, diagnose as dg
    L = 3e-3
    ecke = np.array([[0, 0, 0], [L, 0, 0], [0.5 * L, 0.866 * L, 0]], float)
    def tet(dicke):
        return np.vstack([ecke, [0.5 * L, 0.289 * L, dicke * L]])
    Pn = np.vstack([tet(0.02), tet(1e-7) + 1.0])
    TET = np.array([[0, 1, 2, 3], [4, 5, 6, 7]], int)
    V = np.abs(M3.tetraedervolumen(Pn, TET))
    flach = M3.flache_tetraeder(V, Pn, TET)
    alt = V <= M3.FLACH * 0.05 ** 3
    check("ein 3-mm-Tetraeder mit 2 % Dicke bleibt, einer mit 1e-7 Dicke fliegt",
          flach.tolist() == [False, True], f"{flach.tolist()}, V = {V}")
    check("  Ruecknahmeprobe: mit h = 50 mm des Koerpers flog auch der gesunde",
          alt.tolist() == [True, True], f"{alt.tolist()}, Grenze {M3.FLACH * 0.05 ** 3:.3g} m³")
    # Der Pruefkoerper der Statik3D-Sitzung: Platte R 450, t 35, Bohrung r 10 mm, h 50 mm
    m = neues_modell()
    k = buchse(m, 0.45, 0.01, 0.035)
    m.netz.sweep = False
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    log = []
    with contextlib.redirect_stdout(_io.StringIO()):
        mesher.modell_vernetzen(m, log, workers=1)
    bef = [b for b in dg.abnahme(m, warnungen=True)
           if b.pruefung in ("Riss im Netz", "Lücke im Netzrand", "Seiten im Inneren", "Volumenbilanz")]
    check("Platte R 450 / Bohrung r 10 / t 35 mm, h = 50 mm: kein Riss, keine Luecke",
          not bef and not any("flache Tetraeder" in z for z in log),
          f"{len(k.elemente)} tet4; " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.3g}" for b in bef))


def kegelstumpf(m: Model, ru: float, ro: float, hoehe: float, name: str = "V1"):
    """Kegelstumpf: Grundkreis ru, Deckkreis ro, zwei Mantelflaechen aus je
    zwei Boegen verschiedener Halbmesser und zwei Mantellinien."""
    satz = []
    for z, r, marke in ((0.0, ru, "U"), (hoehe, ro, "O")):
        a = m.add_node(-r, 0, z)
        b = m.add_node(r, 0, z)
        l1, l2 = f"K{marke}1", f"K{marke}2"
        m.add_line(l1, [a, b], "arc", punkte=[(-r, 0, z), (0, r, z), (r, 0, z)])
        m.add_line(l2, [b, a], "arc", punkte=[(r, 0, z), (0, -r, z), (-r, 0, z)])
        satz.append((a, b, l1, l2))
    (au, bu, u1, u2), (ao, bo, o1, o2) = satz
    m.add_line("KV1", [au, ao])
    m.add_line("KV2", [bu, bo])
    m.add_flaeche("Mantel1", [u1, "KV2", o1, "KV1"], material="S235")
    m.add_flaeche("Mantel2", [u2, "KV1", o2, "KV2"], material="S235")
    m.add_flaeche("Boden", [u1, u2], material="S235")
    m.add_flaeche("Deckel", [o1, o2], material="S235")
    return m.add_koerper(name, ["Mantel1", "Mantel2", "Boden", "Deckel"], material="S235")


def verdrehter_block(m: Model, dz: float = 0.1, name: str = "V1"):
    """Einheitswuerfel, dessen Deckel an einer Ecke um dz angehoben ist: der
    Deckel ist ein windschiefes Viereck aus vier Geraden, z = 1 + dz x y."""
    P = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1 + dz), (0, 1, 1)]
    n = [m.add_node(*p) for p in P]
    kanten: dict = {}

    def linie(a, b):
        key = (min(a, b), max(a, b))
        if key not in kanten:
            kanten[key] = f"L{len(kanten)}"
            m.add_line(kanten[key], [n[a], n[b]])
        return kanten[key]
    fl = []
    for nm, q in (("Boden", (0, 1, 2, 3)), ("Deckel", (4, 5, 6, 7)), ("S0", (0, 1, 5, 4)),
                  ("S1", (1, 2, 6, 5)), ("S2", (2, 3, 7, 6)), ("S3", (3, 0, 4, 7))):
        m.add_flaeche(nm, [linie(q[i], q[(i + 1) % 4]) for i in range(4)], material="S235")
        fl.append(nm)
    return m.add_koerper(name, fl, material="S235")


def _randkantenmitten(m: Model, k) -> tuple:
    """(Randkanten des tet4-Netzrands als Knotenpaare, {Knotenpaar: Mittenknoten})"""
    E4 = np.array([[int(x) for x in m.elements[i].nodes[:4]] for i in k.elemente])
    mid = {}
    for i in k.elemente:
        kn = [int(x) for x in m.elements[i].nodes]
        for (a, b), mm in zip(M3.TET10_KANTEN, kn[4:]):
            mid[(min(kn[a], kn[b]), max(kn[a], kn[b]))] = mm
    kanten = set()
    for f in M3.freie_seiten(E4).tolist():
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            kanten.add((min(a, b), max(a, b)))
    return kanten, mid


def test_projektor_kegel_und_windschief():
    """Zweiter Auftrag (23.09.2026), Aufgabe 2: ``flaechenprojektoren`` kannte
    den Zylinder; das Drehlager hat daneben 8 Kegelflaechen (Fasen,
    Senkungen) und 8 windschiefe Vierecke aus Geraden (gezaehlt 23.09.2026),
    keine Kugel, keinen Torus. Beide Arten werden abgebildet: die
    tet10-Seitenmitten der Randkanten liegen auf Kegel bzw. bilinearer
    Flaeche."""
    import contextlib
    import io as _io
    from statik3d import mesher

    def kegel(ohne):
        m = neues_modell()
        ru, ro, H = 0.1, 0.06, 0.1
        k = kegelstumpf(m, ru, ro, H)
        k.ordnung = 2
        m.netz.sweep = False
        m.netz.ziellaenge = 0.03
        m.netz.dichte = "eigene"
        alt = M3._kegelpassung
        if ohne:
            M3._kegelpassung = lambda *a, **kw: None
        try:
            with contextlib.redirect_stdout(_io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1)
        finally:
            M3._kegelpassung = alt
        X = np.asarray(m.nodes, float)
        r, z = np.hypot(X[:, 0], X[:, 1]), X[:, 2]
        rz = ru + (ro - ru) * z / H
        auf = np.abs(r - rz) < 1e-7
        kanten, mid = _randkantenmitten(m, k)
        d = [abs(r[mid[key]] - rz[mid[key]]) for key in kanten if auf[key[0]] and auf[key[1]] and key in mid]
        return len(d), max(d)
    n, d_mit = kegel(False)
    _n, d_ohne = kegel(True)
    check("Kegelstumpf r 100 -> 60 mm, tet10: jede Randkantenmitte des Mantels liegt auf dem Kegel",
          n > 100 and d_mit < 1e-9, f"{n} Mantelkanten, groesster Abstand {d_mit * 1e3:.4f} mm")
    check("  Ruecknahmeprobe: ohne Kegelpassung liegt sie auf der Sehne (Sehnenpfeil 1,23 mm)",
          d_ohne > 1e-3, f"{d_ohne * 1e3:.4f} mm")
    from statik3d.sweep import _schleifenpunkte
    m = neues_modell()
    kegelstumpf(m, 0.1, 0.06, 0.1)
    f = m.flaechen["Mantel1"]
    kg = M3._kegelpassung(m, f, _schleifenpunkte(m, list(f.linien)))
    check("  die Kegelpassung nennt Achse z und Steigung -0,4",
          kg is not None and abs(abs(float(kg[1][2])) - 1.0) < 1e-12 and abs(abs(float(kg[3])) - 0.4) < 1e-9,
          str(kg))

    def wind(ohne):
        m = neues_modell()
        k = verdrehter_block(m, 0.1)
        k.ordnung = 2
        m.netz.sweep = False
        m.netz.ziellaenge = 0.3
        m.netz.dichte = "eigene"
        alt = M3._windschief_projektor
        if ohne:
            M3._windschief_projektor = lambda *a, **kw: None
        try:
            with contextlib.redirect_stdout(_io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1)
        finally:
            M3._windschief_projektor = alt
        X = np.asarray(m.nodes, float)
        soll = 1 + 0.1 * X[:, 0] * X[:, 1]
        auf = np.abs(X[:, 2] - soll) < 1e-7
        kanten, mid = _randkantenmitten(m, k)
        d = [abs(X[mid[key], 2] - soll[mid[key]]) for key in kanten
             if auf[key[0]] and auf[key[1]] and key in mid and X[key[0], 2] > 0.5 and X[key[1], 2] > 0.5]
        return len(d), max(d), len(k.elemente)
    n, d_mit, e_mit = wind(False)
    _n, d_ohne, e_ohne = wind(True)
    check("windschiefer Deckel z = 1 + 0,1 x y, tet10: jede Randkantenmitte liegt auf der bilinearen Flaeche",
          n > 20 and d_mit < 1e-9, f"{n} Deckelkanten, groesster Abstand {d_mit * 1e3:.4f} mm, {e_mit} tet10")
    check("  Ruecknahmeprobe: ohne den Projektor liegt die Mitte der Diagonale daneben",
          d_ohne > 1e-3, f"{d_ohne * 1e3:.4f} mm, {e_ohne} tet10")
    m = neues_modell()
    kegelstumpf(m, 0.1, 0.06, 0.1)
    arten = M3.projektorarten(m)
    check("projektorarten zaehlt den Kegelstumpf: 2 Kegel, 2 eben",
          arten == {"Zylinder": 0, "Kegel": 2, "Kugel": 0, "windschief": 0, "eben/ohne": 2}, str(arten))


def hohlkugel_achtel(m: Model, a: float, b: float, name: str = "V1"):
    """Achtel der Hohlkugel a <= r <= b (tests/pruefkoerper.Hohlkugel als
    Geometrie): zwei Kugelflaechen aus je drei Grosskreisboegen, drei ebene
    Viertelringe in den Symmetrieebenen."""
    s2 = 1 / np.sqrt(2)
    ia = [m.add_node(a, 0, 0), m.add_node(0, a, 0), m.add_node(0, 0, a)]
    ib = [m.add_node(b, 0, 0), m.add_node(0, b, 0), m.add_node(0, 0, b)]

    def bogen(nm, kn, r, ij):
        P = {0: (r, 0, 0), 1: (0, r, 0), 2: (0, 0, r)}
        mitte = {(0, 1): (r * s2, r * s2, 0), (1, 2): (0, r * s2, r * s2), (0, 2): (r * s2, 0, r * s2)}
        i, j = ij
        m.add_line(nm, [kn[i], kn[j]], "arc", punkte=[P[i], mitte[(min(i, j), max(i, j))], P[j]])
    for tag, kn, r in (("I", ia, a), ("A", ib, b)):
        bogen(f"{tag}xy", kn, r, (0, 1))
        bogen(f"{tag}yz", kn, r, (1, 2))
        bogen(f"{tag}zx", kn, r, (2, 0))
    m.add_line("Rx", [ia[0], ib[0]])
    m.add_line("Ry", [ia[1], ib[1]])
    m.add_line("Rz", [ia[2], ib[2]])
    m.add_flaeche("innen", ["Ixy", "Iyz", "Izx"], material="S235")
    m.add_flaeche("aussen", ["Axy", "Ayz", "Azx"], material="S235")
    m.add_flaeche("Ez", ["Ixy", "Ry", "Axy", "Rx"], material="S235")
    m.add_flaeche("Ex", ["Iyz", "Rz", "Ayz", "Ry"], material="S235")
    m.add_flaeche("Ey", ["Izx", "Rx", "Azx", "Rz"], material="S235")
    return m.add_koerper(name, ["innen", "aussen", "Ez", "Ex", "Ey"], material="S235")


def test_kugelflaeche():
    """Zweiter Auftrag (23.09.2026), Aufgabe 4 (V5) braucht die Lame-Hohlkugel
    mit dem freien Vernetzer: eine Kugelflaeche aus drei Grosskreisboegen
    geht weder als Coons-Fleck noch als Abwicklung; das harmonische Heben
    legte ihre inneren Punkte unter die Kugel. Jetzt: Kugelpassung, die
    Flaechenpunkte auf der Kugel, der Projektor fuer Verfeinerung und
    tet10-Seitenmitten."""
    import contextlib
    import io as _io
    from statik3d import mesher

    def lauf(ohne):
        m = neues_modell()
        k = hohlkugel_achtel(m, 0.1, 0.2)
        k.ordnung = 2
        m.netz.sweep = False
        m.netz.ziellaenge = 0.03
        m.netz.dichte = "eigene"
        alt = M3._kugelpassung
        if ohne:
            M3._kugelpassung = lambda *a, **kw: None
        try:
            with contextlib.redirect_stdout(_io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1)
        finally:
            M3._kugelpassung = alt
        X = np.asarray(m.nodes, float)
        r = np.linalg.norm(X, axis=1)
        E4 = np.array([[int(x) for x in m.elements[i].nodes[:4]] for i in k.elemente])
        rand = np.unique(M3.freie_seiten(E4))
        ebene = (np.abs(X[:, 0]) < 1e-9) | (np.abs(X[:, 1]) < 1e-9) | (np.abs(X[:, 2]) < 1e-9)
        kugel = rand[~ebene[rand]]
        d_knoten = float(np.minimum(np.abs(r[kugel] - 0.1), np.abs(r[kugel] - 0.2)).max())
        kanten, mid = _randkantenmitten(m, k)
        d_mitten = [abs(r[mid[key]] - R) for key in kanten for R in (0.1, 0.2)
                    if abs(r[key[0]] - R) < 1e-7 and abs(r[key[1]] - R) < 1e-7
                    and not (ebene[key[0]] and ebene[key[1]]) and key in mid]
        return len(kugel), d_knoten, len(d_mitten), max(d_mitten, default=0.0), len(k.elemente)
    n_k, d_k, n_m, d_m, n_el = lauf(False)
    check("Achtel der Hohlkugel a = 100, b = 200 mm, tet10: alle Huellknoten der Kugelflaechen auf den Kugeln",
          n_k > 30 and d_k < 1e-9, f"{n_k} Knoten, groesster Abstand {d_k * 1e3:.4f} mm, {n_el} tet10")
    check("  und alle Seitenmitten der Randkanten", n_m > 100 and d_m < 1e-9,
          f"{n_m} Kanten, groesster Abstand {d_m * 1e3:.4f} mm")
    _n, d_k0, _m, d_m0, _e = lauf(True)
    check("  Ruecknahmeprobe: ohne Kugelpassung liegen Flaechenpunkte unter der Kugel (harmonisch gehoben)",
          d_k0 > 1e-4, f"Huellknoten bis {d_k0 * 1e3:.3f} mm daneben, Seitenmitten bis {d_m0 * 1e3:.3f} mm")
    m = neues_modell()
    hohlkugel_achtel(m, 0.1, 0.2)
    arten = M3.projektorarten(m)
    check("  projektorarten zaehlt 2 Kugeln, 3 ebene", arten.get("Kugel") == 2 and arten.get("eben/ohne") == 3, str(arten))
    # Mit Groessenfeld teilt die Linienteilung die Boegen ungleich - die
    # Punkte muessen trotzdem genau auf dem Kreis liegen (vorher bis 7e-8 m
    # daneben, und die Kugelpassung nahm den mittleren Radius)
    m = neues_modell()
    k = hohlkugel_achtel(m, 0.1, 0.2)
    m.netz.sweep = False
    m.netz.ziellaenge = 0.03
    m.netz.dichte = "eigene"
    m.netz.feldpunkte = [[0.1, 0.0, 0.0, 0.01, 0.03], [0.0, 0.07, 0.07, 0.012, 0.03]]
    with contextlib.redirect_stdout(_io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1)
    X = np.asarray(m.nodes, float)
    r = np.linalg.norm(X, axis=1)
    E4 = np.array([[int(x) for x in m.elements[i].nodes[:4]] for i in k.elemente])
    rand = np.unique(M3.freie_seiten(E4))
    ebene = (np.abs(X[:, 0]) < 1e-9) | (np.abs(X[:, 1]) < 1e-9) | (np.abs(X[:, 2]) < 1e-9)
    innen = rand[(r[rand] < 0.15) & ~ebene[rand]]
    check("  mit Groessenfeld (ungleiche Bogenteilung) liegen die Knoten der Innenflaeche genau auf r = a",
          len(innen) > 20 and float(np.abs(r[innen] - 0.1).max()) < 1e-12,
          f"{len(innen)} Knoten, groesster Abstand {np.abs(r[innen] - 0.1).max():.2e} m, {len(k.elemente)} Elemente")


def test_innen_zaehlt_die_kante_einmal():
    """Ein Strahl genau durch die gemeinsame Kante zweier Huelldreiecke wird
    von genau einem gezaehlt - wie fuer einen um (eps, eps^2) verschobenen
    Punkt. Am Wuerfel: der Punkt unter der Deckeldiagonale ist innen, der
    darueber aussen; ebenso ueber einer Ecke."""
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    T = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                  [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
    q = np.array([[0.5, 0.5, 0.5], [0.5, 0.5, 1.5],       # unter / ueber der Deckeldiagonale
                  [0.25, 0.25, 0.5], [0.75, 0.75, 0.5],   # auf der Diagonale, innen
                  [1.0, 1.0, 0.5], [1.0, 1.0, 1.5],       # senkrecht ueber der Ecke (1,1)
                  [0.0, 0.0, 0.5]])                        # ueber der Ecke (0,0)
    drin = M3.innen(q, P, T)
    check("Punkte unter der Deckeldiagonale sind innen, darueber aussen",
          list(drin[:4]) == [True, False, True, True], str(drin[:4].tolist()))
    # Genau unter einer Deckelecke liegt der Punkt zugleich auf der Seitenwand
    # (x = 1 oder y = 1): ein Randpunkt, fuer den beide Antworten vertretbar
    # sind. Entscheidend ist, dass die Regel **eine** gibt und fuer alle
    # Dreiecke dieselbe: der um (+eps, +eps^2) verschobene Punkt liegt an der
    # Ecke (1, 1) draussen und an der Ecke (0, 0) drinnen.
    check("ueber einer Deckelecke entscheidet dieselbe Verschiebung - (1,1) aussen, (0,0) innen",
          not drin[4] and not drin[5] and drin[6], str(drin[4:].tolist()))
    # Gegenprobe der alten Regel: beide Dreiecke zaehlen - der Punkt unter der
    # Diagonale gilt als aussen
    alt = M3._seite_mit_ausweichung
    M3._seite_mit_ausweichung = lambda l, gx, gy: l >= 0
    try:
        alt_drin = M3.innen(q[:1], P, T)
    finally:
        M3._seite_mit_ausweichung = alt
    check("mit der alten Regel l >= 0 galt derselbe Punkt als aussen", not alt_drin[0])


def test_randtreue_nicht_messbar_meldet_null():
    """Auftrag der Statik3D-Sitzung (22.09.2026), Nummer 1: misslingt die
    Messung der Randtreue, stand 1,0 im Bericht - die Zusage, der Netzrand
    liege genau auf der Huelle. Aus 83,3 % wurden so 100,0 %, der zweite
    Anlauf unterblieb. Jetzt 0,0 (im ganzen Programm: nicht gemessen) und der
    Grund im Bericht."""
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    T = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    TET = np.array([[0, 1, 2, 3]])
    alt = M3.randtreue

    def kaputt(*a, **kw):
        raise ValueError("Probe: Randtreue nicht messbar")
    M3.randtreue = kaputt
    try:
        tb = M3._netzbericht(P, TET, P, T)
    finally:
        M3.randtreue = alt
    check("Randtreue 0,0 statt 1,0, und der Grund steht im Bericht",
          tb["randtreue"] == 0.0 and tb["randabweichung"] == 0.0
          and "ValueError" in tb.get("randtreue_fehler", ""),
          f"randtreue {tb['randtreue']}, Fehler {tb.get('randtreue_fehler')}")
    tb2 = M3._netzbericht(P, TET, P, T)
    check("messbar bleibt sie 1,0 ohne Fehlereintrag",
          tb2["randtreue"] == 1.0 and "randtreue_fehler" not in tb2, str(tb2.get("randtreue")))


def _zwei_koerper_ungleich():
    """Wie _zwei_koerper, aber die beiden Prismen bekommen **verschiedene**
    Kantenlaengen - erst dann wird der obere vor dem unteren fertig, und die
    Einbaufolge entscheidet ueber die Knotennummern."""
    m, k1, k2 = _zwei_koerper()
    return m, k1, k2, {"V1": 0.22, "V2": 0.45}


def test_nummern_haengen_nicht_am_prozess():
    """Auftrag der Statik3D-Sitzung (22.09.2026), Nummer 2: eingebaut wurde in
    der Folge des Fertigwerdens; am Drehlager behielten 18 von 3 731 Knoten
    ihre Nummer zwischen zwei Laeufen. Jetzt folgt der Einbau der festen
    Reihe der Koerper. Geprueft mit zwei verschieden grossen Koerpern und
    Knoten fuer Knoten - nicht nur an der Stueckzahl, die stimmte auch vorher."""
    from statik3d import mesher
    ms, s1, s2, hs = _zwei_koerper_ungleich()
    erg_s = mesher.koerper_vernetzen(ms, [s1, s2], hs=hs, log=[], workers=1)
    mp_, p1, p2, hs = _zwei_koerper_ungleich()
    erg_p = mesher.koerper_vernetzen(mp_, [p1, p2], hs=hs, log=[], workers=2)
    check("zwei verschieden feine Koerper, seriell und auf zwei Prozessen vernetzt",
          erg_s["fertig"] == 2 and erg_p["fertig"] == 2 and erg_p.get("prozesse") == 2
          and len(s1.elemente) != len(s2.elemente), f"{erg_s} / {erg_p}")
    check("gleich viele Knoten und Elemente", ms.nn == mp_.nn and len(ms.elements) == len(mp_.elements),
          f"{ms.nn}/{mp_.nn} Knoten, {len(ms.elements)}/{len(mp_.elements)} Elemente")
    gleich = ms.nn == mp_.nn and bool(np.allclose(ms.nodes, mp_.nodes, atol=1e-12))
    check("und jeder Knoten hat in beiden Laeufen dieselbe Nummer (Koordinaten Knoten fuer Knoten)",
          gleich, f"{int((np.linalg.norm(ms.nodes - mp_.nodes, axis=1) < 1e-12).sum()) if ms.nn == mp_.nn else 0} von {ms.nn} gleich")
    check("und jedes Element dieselben Knoten",
          all(list(a.nodes) == list(b.nodes) and a.typ == b.typ for a, b in zip(ms.elements, mp_.elements)))


def test_ordnung_je_koerper():
    """Anweisung V1 (Loeser-Sitzung, 22.09.2026): ``Volumenkoerper.ordnung``
    = 2 gibt tet10 in diesem Koerper, tet4 im Rest; an der gemeinsamen Flaeche
    stimmen die Eckknoten ueberein. Umlauf: speichern, laden, dieselbe
    Elementliste."""
    from statik3d import mesher
    m, k1, k2 = _zwei_koerper()
    k2.ordnung = 2
    erg = mesher.koerper_vernetzen(m, [k1, k2], log=[], workers=1)
    typ1 = {m.elements[i].typ for i in k1.elemente}
    typ2 = {m.elements[i].typ for i in k2.elemente}
    check("V1 (ohne Vorgabe) tet4, V2 (Ordnung 2) tet10",
          typ1 == {"tet4"} and typ2 == {"tet10"} and erg["fertig"] == 2, f"{typ1} / {typ2}")
    # Die Eckknoten der gemeinsamen Flaeche Fm (z = 1) gehoeren beiden
    ecken1 = {int(x) for i in k1.elemente for x in m.elements[i].nodes if abs(m.nodes[int(x)][2] - 1.0) < 1e-9}
    ecken2 = {int(x) for i in k2.elemente for x in m.elements[i].nodes[:4] if abs(m.nodes[int(x)][2] - 1.0) < 1e-9}
    check("die Eckknoten in der gemeinsamen Flaeche sind dieselben", ecken1 == ecken2 and len(ecken1) > 3,
          f"{len(ecken1)} gegen {len(ecken2)}, gemeinsam {len(ecken1 & ecken2)}")
    m2 = Model.from_dict(m.to_dict())
    check("Umlauf: nach Speichern und Laden dieselbe Elementliste und Ordnung am Koerper",
          [(e.typ, list(e.nodes)) for e in m2.elements] == [(e.typ, list(e.nodes)) for e in m.elements]
          and m2.koerper["V2"].ordnung == 2 and m2.koerper["V1"].ordnung is None)
    # Ein Quader mit Ordnung 2 geht nicht in den abgebildeten Hexaederpfad
    from test_sweep import quader as _quader
    mq, kq = _quader()
    kq.ordnung = 2
    mesher.modell_vernetzen(mq, [], workers=1)
    check("ein Quader mit Ordnung 2 wird frei mit tet10 vernetzt statt abgebildet",
          {mq.elements[i].typ for i in kq.elemente} == {"tet10"},
          str({mq.elements[i].typ for i in kq.elemente}))


def test_seitenmitten_auf_der_zylinderflaeche():
    """Anweisung V2 mit Nachtrag (Loeser- und Element-Sitzung, 22./23.09.2026):
    bei tet10 gehoeren alle Randknoten und Kantenmitten auf die wahre Flaeche,
    nicht auf die Sehne - eine einzige gerade Bohrungskante liess das Element
    hoechster Ordnung 23 N/mm^2 danebenliegen. Hohlzylinder r = 50/100 mm,
    h = 35 mm wie in der Messung der Element-Sitzung."""
    import contextlib
    import io as _io
    from statik3d import mesher
    from statik3d.elements.solid import jacobi_volumen
    m = neues_modell()
    k = buchse(m, 0.1, 0.05, 0.1)
    k.ordnung = 2
    m.netz.sweep = False
    m.netz.ziellaenge = 0.035
    m.netz.dichte = "eigene"
    log = []
    with contextlib.redirect_stdout(_io.StringIO()):
        mesher.modell_vernetzen(m, log, workers=1)
    els = list(k.elemente)
    check("der Hohlzylinder wird mit tet10 vernetzt", els and {m.elements[i].typ for i in els} == {"tet10"},
          str({m.elements[i].typ for i in els}))
    E4 = np.array([[int(x) for x in m.elements[i].nodes[:4]] for i in els])
    mitte = {}
    for i in els:
        kn = [int(x) for x in m.elements[i].nodes]
        for (a, b), mid in zip(M3.TET10_KANTEN, kn[4:]):
            mitte[(min(kn[a], kn[b]), max(kn[a], kn[b]))] = mid
    abst = {0.1: [0.0], 0.05: [0.0]}
    zahl = {0.1: 0, 0.05: 0}
    for f in M3.freie_seiten(E4).tolist():
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            ra, rb = np.hypot(*m.nodes[a][:2]), np.hypot(*m.nodes[b][:2])
            for R in (0.1, 0.05):
                if abs(ra - R) < 1e-6 and abs(rb - R) < 1e-6:
                    zahl[R] += 1
                    abst[R].append(abs(np.hypot(*m.nodes[mitte[(min(a, b), max(a, b))]][:2]) - R))
    check("jede Seitenmitte einer Randkante liegt auf dem Aussenzylinder (vorher auf der Sehne, 1,23 mm daneben)",
          zahl[0.1] > 100 and max(abst[0.1]) < 1e-9, f"{zahl[0.1]} Kanten, groesster Abstand {max(abst[0.1]) * 1e3:.4f} mm")
    check("und auf der Bohrung (vorher 0,62 mm daneben)",
          zahl[0.05] > 100 and max(abst[0.05]) < 1e-9, f"{zahl[0.05]} Kanten, groesster Abstand {max(abst[0.05]) * 1e3:.4f} mm")
    det = [jacobi_volumen("tet10", m.nodes[m.elements[i].nodes]) for i in els]
    check("die Jacobi-Determinante bleibt an allen Integrationspunkten positiv",
          all(d["det_min"] > 0 for d in det),
          f"kleinstes Verhaeltnis {min(d['det_min'] / d['det_max'] for d in det):.3f}")
    zeile = next((z for z in log if "Seitenmitten auf die gekrümmte Fläche" in z), "")
    check("das Protokoll nennt die Zahl und den groessten Weg (der Sehnenpfeil r (1 - cos 9 Grad) = 1,231 mm)",
          "Seitenmitten" in zeile and "1.231 mm" in zeile, zeile.strip()[:140])
    check("kein Rueckfall auf gerade Kanten", not any("gerade Kanten" in z for z in log),
          str([z.strip()[:100] for z in log if "gerade Kanten" in z]))
    # Die Huelle selbst: ein neuer Huellpunkt aus der Verfeinerung liegt auf dem Zylinder
    P = np.array([[0.1, 0.0, 0.0], [0.1 * np.cos(0.3), 0.1 * np.sin(0.3), 0.0],
                  [0.1, 0.0, 0.05], [0.1 * np.cos(0.3), 0.1 * np.sin(0.3), 0.05]])
    T = np.array([[0, 1, 2], [1, 3, 2]])
    proj = {"M": M3._zylinder_projektor((np.zeros(3), np.array([0.0, 0.0, 1.0]), 0.1))}
    P2, T2, _q = M3.huelle_verfeinern(P, T, [0], ["M", "M"], projektor=proj)
    r_neu = np.hypot(*P2[len(P):].T[:2]) if len(P2) > len(P) else np.zeros(0)
    check("ein neuer Huellpunkt der Verfeinerung liegt auf dem Zylinder, nicht auf der Sehne",
          len(P2) > len(P) and np.allclose(r_neu, 0.1, atol=1e-12),
          f"{len(P2) - len(P)} neue Punkte, r = {np.round(r_neu, 6).tolist()}")
    P3, _T3, _q3 = M3.huelle_verfeinern(P, T, [0], ["M", "M"])
    check("ohne Projektor bleibt er auf der Sehne (Ruecknahmeprobe)",
          len(P3) > len(P) and abs(np.hypot(*P3[len(P)][:2]) - 0.1) > 1e-4,
          f"r = {np.hypot(*P3[len(P)][:2]):.6f}")


def main():
    for t in (test_punkt_im_koerper, test_quader, test_huelle_ohne_rundungsgitter,
              test_abnahme_warnstufe_splitter, test_enge_huellkanten_werden_benannt,
              test_randstrecke_wird_nicht_verdraengt,
              test_groessenfeld_an_der_festgelegten_linie,
              test_randstrecken_sind_keine_glueckssache,
              test_groessenfeld_an_der_bohrung, test_mantellinie_der_bohrung,
              test_einspringende_ecke,
              test_platte_mit_bohrung, test_duenne_platte_randseiten,
              test_zylinder_und_buchse,
              test_kleines_bauteil, test_gemeinsame_flaeche, test_zugstab,
              test_undichte_huelle, test_quadratische_tetraeder,
              test_splitter_glaetten, test_huelle_verfeinern_haelt_form,
              test_gitterindex_zelle, test_geometrielast,
              test_fortschritt_und_abbruch, test_parallel_vernetzen,
              test_luecke_im_netzrand_geschlossen, test_innen_zaehlt_die_kante_einmal,
              test_randtreue_nicht_messbar_meldet_null, test_nummern_haengen_nicht_am_prozess,
              test_ordnung_je_koerper, test_seitenmitten_auf_der_zylinderflaeche,
              test_huelle_kippen, test_kappenpunkte_halten_abstand, test_krumme_kanten_oertlich_feiner,
              test_projektor_kegel_und_windschief, test_kugelflaeche, test_bogenwinkel_je_koerper,
              test_flache_tetraeder_nach_eigener_groesse):
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
