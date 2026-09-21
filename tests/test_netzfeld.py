"""
Groessenfeld (statik3d.netzfeld): eine Groesse, die alle Wege des
Vernetzers lesen - Linienteilung, Flaechennetz, Tetraedern, gmsh, MMG3D.

Geprueft wird

  * das Feld selbst: Auswertung exakt gegen alle Quellen (Stichprobe ueber
    den Parameterraum), Ausduennung innerhalb der Toleranz, pickle-fest;
  * die Bedeutung der Flaechen: Last, Lager, Kontakt, Nachbar machen
    bedeutend, alles andere ist Nebenflaeche;
  * der grobe Bogenwinkel an Nebenflaechen (8 statt 20 Abschnitte je Kreis)
    und dass er die Huelle kleiner macht;
  * die Linienteilung nach dem Feld (Zahl und Verteilung der Punkte);
  * das gradierte Flaechennetz und das Tetraedern nach dem Feld;
  * gmsh (Rueckruf) und MMG3D (Metrik) mit Feld, wenn installiert;
  * ein ganzer Koerper mit Kugelverfeinerung durch die Abnahme;
  * das Aufraeumen der Netzknoten und die kopflose Vernetzungsfolge;
  * Speichern und Laden der neuen Netzeinstellungen.

Aufruf: python -m tests.test_netzfeld
"""
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, DofBehaviour, Netzeinstellungen    # noqa: E402
from statik3d import mesher, mesher3d as M3, netzfeld, diagnose, vernetzer_extern as vx  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return bool(ok)


# --------------------------------------------------------------------------
# Testkoerper: Platte mit Bohrungen aus Boegen, wie RFEM sie liefert
# --------------------------------------------------------------------------
def platte_mit_bohrungen(a=1.0, b=0.6, t=0.2, bohrungen=((0.5, 0.3, 0.1),), name="V1",
                         material="S235"):
    """Quaderplatte a x b x t mit zylindrischen Bohrungen (cx, cy, r). Jeder
    Kreis besteht aus zwei Halbboegen zwischen zwei Knoten - so kommt er aus
    RFEM, und nur so greift die Kruemmungsteilung (ein Polygon hat keine)."""
    m = Model()
    m.add_material(Material.steel(material))
    E = [(0, 0), (a, 0), (a, b), (0, b)]
    ku = [m.add_node(x, y, 0.0) for x, y in E]
    ko = [m.add_node(x, y, t) for x, y in E]
    for i in range(4):
        j = (i + 1) % 4
        m.add_line(f"AU{i}", [ku[i], ku[j]])
        m.add_line(f"AO{i}", [ko[i], ko[j]])
    for i in range(4):
        m.add_line(f"AV{i}", [ku[i], ko[i]])
    flaechen = []
    for i in range(4):
        j = (i + 1) % 4
        m.add_flaeche(f"M{i + 1}", [f"AU{i}", f"AV{j}", f"AO{i}", f"AV{i}"], material=material)
        flaechen.append(f"M{i + 1}")
    loch_u, loch_o = [], []
    for k, (cx, cy, r) in enumerate(bohrungen):
        tag = f"B{k + 1}"
        satz = []
        for z, marke in ((0.0, "U"), (t, "O")):
            p = m.add_node(cx - r, cy, z)
            q = m.add_node(cx + r, cy, z)
            l1, l2 = f"{tag}{marke}1", f"{tag}{marke}2"
            m.add_line(l1, [p, q], "arc", punkte=[(cx - r, cy, z), (cx, cy + r, z), (cx + r, cy, z)])
            m.add_line(l2, [q, p], "arc", punkte=[(cx + r, cy, z), (cx, cy - r, z), (cx - r, cy, z)])
            satz.append((p, q, l1, l2))
        (pu, qu, u1, u2), (po, qo, o1, o2) = satz
        m.add_line(f"{tag}V1", [pu, po])
        m.add_line(f"{tag}V2", [qu, qo])
        m.add_flaeche(f"{tag}Mantel1", [u1, f"{tag}V2", o1, f"{tag}V1"], material=material)
        m.add_flaeche(f"{tag}Mantel2", [u2, f"{tag}V1", o2, f"{tag}V2"], material=material)
        flaechen += [f"{tag}Mantel1", f"{tag}Mantel2"]
        loch_u.append([u1, u2])
        loch_o.append([o1, o2])
    m.add_flaeche("Boden", [f"AU{i}" for i in range(4)], material=material, oeffnungen=loch_u)
    m.add_flaeche("Deckel", [f"AO{i}" for i in range(4)], material=material, oeffnungen=loch_o)
    flaechen += ["Boden", "Deckel"]
    k = m.add_koerper(name, flaechen, material=material)
    return m, k


def zug_und_lager(m, p=-100e6, case="LF1"):
    """Zug in x an der Flaeche x = a (M2); Einspannung als Flaechenlager an
    M4, das ueber supports.lager_auf_netz dem Netz folgt."""
    m.add_load_case(case)
    m.case(case).gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("M2", p, "flaeche", richtung=[1.0, 0.0, 0.0], case=case)
    m.active_case = case
    ss = m.add_surface_support(name="Einspannung")
    ss.flaechen = ["M4"]
    for d in (0, 1, 2):
        ss.behaviour[d] = DofBehaviour("rigid")
    return m


def _kanten(m, els):
    """Mittlere Kantenlaenge und Schwerpunkt je Element."""
    K = np.array([[int(x) for x in m.elements[i].nodes[:4]] for i in els], int)
    X = m.nodes[K]
    L = np.mean([np.linalg.norm(X[:, a] - X[:, b], axis=1)
                 for a, b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))], axis=0)
    return L, X.mean(axis=1)


# --------------------------------------------------------------------------
# 1) Das Feld selbst
# --------------------------------------------------------------------------
def test_feld_auswertung_exakt():
    """Stichprobe ueber den Parameterraum: Dichte der Quellen, Reichweiten,
    Spanne der Kantenlaengen. Die schnelle Auswertung muss der ueber alle
    Quellen gleichen - die Lipschitz-Schranke macht sie exakt."""
    rng = np.random.default_rng(7)
    schlimmste = 0.0
    for n, rmax, (h0, h1) in ((300, 0.0, (0.003, 0.07)), (5000, 0.02, (0.003, 0.07)),
                              (50000, 0.005, (0.002, 0.05)), (2000, 0.05, (0.01, 0.08))):
        f = netzfeld.Groessenfeld(0.08)
        X = rng.uniform(0, 1, (n, 3))
        h = rng.uniform(h0, h1, n)
        r = rng.uniform(0, rmax, n) if rmax else np.zeros(n)
        f.punkte(X, h, r)
        f.abschliessen()
        Q = rng.uniform(-0.1, 1.1, (400, 3))
        a, b = f(Q), f.genau(Q)
        schlimmste = max(schlimmste, float(np.max(np.abs(a - b) / b)))
    check("schnelle Auswertung = Auswertung ueber alle Quellen (4 Stichproben)",
          schlimmste < 1e-9, f"groesste Abweichung {schlimmste:.2e}")


def test_feld_ausduennung():
    """Die Ausduennung darf das Feld nur innerhalb UEBERDECKUNG aendern - und
    nur nach oben (weniger Quellen = groeberes Minimum), nie nach unten."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(3)
    n = 20000
    X = rng.uniform(0, 1, (n, 3))
    h = rng.uniform(0.003, 0.07, n)
    r = rng.uniform(0, 0.01, n)
    f = netzfeld.Groessenfeld(0.08)
    f.punkte(X, h, r)
    m = f.abschliessen()
    g = netzfeld.Groessenfeld(0.08)
    g.X, g.h, g.r = X, h, r
    g._baum = cKDTree(X)
    Q = rng.uniform(0, 1, (500, 3))
    a, c = f(Q), g.genau(Q)
    rel = (a - c) / c
    check("Ausduennen laesst deutlich weniger Quellen stehen", m < 0.5 * n, f"{m} von {n}")
    check("und veraendert das Feld hoechstens um UEBERDECKUNG nach oben",
          float(rel.max()) <= netzfeld.UEBERDECKUNG + 1e-9 and float(rel.min()) >= -1e-9,
          f"{rel.min() * 100:+.2f} … {rel.max() * 100:+.2f} %")
    check("ohne Quellen ist das Feld ueberall h_max",
          np.allclose(netzfeld.Groessenfeld(0.05)(Q), 0.05))
    k = netzfeld.Groessenfeld(0.05)
    k.kugel([0.5, 0.5, 0.5], 0.1, 0.01)
    innen = k(np.array([[0.5, 0.5, 0.55], [0.5, 0.5, 0.5]]))
    aussen = k(np.array([[0.5, 0.5, 0.5 + 0.1 + 0.1]]))
    check("Kugel: innen die Kantenlaenge der Kugel", np.allclose(innen, 0.01), str(innen))
    check("aussen waechst sie mit WACHSTUM je Meter",
          abs(aussen[0] - (0.01 + netzfeld.WACHSTUM * 0.1)) < 1e-12, f"{aussen[0]:.4f}")
    p = pickle.loads(pickle.dumps(f))
    check("das Feld ueberlebt pickle (Weg in die Arbeitsprozesse)", np.allclose(p(Q), a))
    rueckruf = f.gmsh_rueckruf(0.08)
    check("der gmsh-Rueckruf nimmt das Minimum aus gmsh-Groesse und Feld",
          abs(rueckruf(3, 1, 0.5, 0.5, 0.5, 1e9) - a[0] * 0 - f(np.array([[0.5, 0.5, 0.5]]))[0]) < 1e-12
          and rueckruf(3, 1, 0.5, 0.5, 0.5, 1e-4) == 1e-4)


# --------------------------------------------------------------------------
# 2) Bedeutung der Flaechen und der grobe Bogenwinkel
# --------------------------------------------------------------------------
def test_bedeutung_und_bogenwinkel():
    m, k = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1), (0.15, 0.1, 0.02)))
    b = netzfeld.bedeutung(m)
    check("ohne Last, Lager, Kontakt ist jede Flaeche Nebenflaeche",
          not b["flaechen"] and len(b["neben_flaechen"]) == len(k.flaechen),
          f"{len(b['neben_flaechen'])} Nebenflaechen")
    zug_und_lager(m)
    m.add_kontaktbedingung("Bolzen", flaechennamen=["B1Mantel1", "B1Mantel2"])
    b = netzfeld.bedeutung(m)
    check("Last macht bedeutend", b["flaechen"].get("M2", "").startswith("Last"), str(b["flaechen"].get("M2")))
    check("Flaechenlager macht bedeutend", "Flächenlager" in b["flaechen"].get("M4", ""), str(b["flaechen"].get("M4")))
    check("Kontakt macht die Bohrungswand bedeutend", "Kontakt" in b["flaechen"].get("B1Mantel1", ""))
    check("die kleine Bohrung bleibt Nebenflaeche",
          "B2Mantel1" in b["neben_flaechen"] and "B2U1" in b["neben_linien"])
    check("die Linien bedeutender Flaechen sind bedeutend", "B1U1" in b["linien"])
    # Bogenwinkel: 18 Grad -> 10 Abschnitte je Halbkreis; 45 Grad -> 4
    check("Halbkreis mit 18 Grad: 10 Abschnitte", M3._bogenabschnitte(m, "B2U1") == 10,
          str(M3._bogenabschnitte(m, "B2U1")))
    check("Halbkreis mit 45 Grad: 4 Abschnitte", M3._bogenabschnitte(m, "B2U1", 45.0) == 4)
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    m.netz.nebenflaechen_grob = True
    feld = netzfeld.aufbauen(m)
    check("nebenflaechen_grob: das Feld kennt die groben Linien",
          feld is not None and "B2U1" in feld.grobe_linien and "B1U1" not in feld.grobe_linien,
          f"{len(feld.grobe_linien) if feld else 0} grobe Linien")
    m.groessenfeld = feld
    flaechen = [m.flaechen[x] for x in k.flaechen]
    teilung = M3.Linienteilung(m, flaechen, 0.05)
    check("die kleine Bohrung bekommt 4 Abschnitte je Halbkreis", teilung.n["B2U1"] == 4, str(teilung.n["B2U1"]))
    check("die Bolzenbohrung behaelt 10", teilung.n["B1U1"] == 10, str(teilung.n["B1U1"]))
    m.netz.nebenflaechen_grob = False
    m.groessenfeld = netzfeld.aufbauen(m)
    check("Vorgabe aus: alles wie bisher (10 Abschnitte)",
          M3.Linienteilung(m, flaechen, 0.05).n["B2U1"] == 10)


def test_grober_bogenwinkel_macht_die_huelle_kleiner():
    """Die Huelle ist der Hebel (3,4 Tetraeder je Randdreieck am Drehlager):
    vier unbelastete Durchgangsbohrungen mit 8 statt 20 Abschnitten."""
    bohr = ((0.5, 0.3, 0.1), (0.15, 0.1, 0.02), (0.85, 0.1, 0.02), (0.15, 0.5, 0.02), (0.85, 0.5, 0.02))
    zahlen = {}
    for grob in (False, True):
        m, k = platte_mit_bohrungen(bohrungen=bohr)
        zug_und_lager(m)
        m.netz.ziellaenge = 0.05
        m.netz.dichte = "eigene"
        m.netz.nebenflaechen_grob = grob
        m.groessenfeld = netzfeld.aufbauen(m)
        P, T, ber = M3.randschale(m, k, 0.05, [])
        check(f"Huelle dicht (nebenflaechen_grob={grob})", ber["offen"] == 0 and ber["volumen"] > 0)
        zahlen[grob] = len(T)
    check("die Huelle wird mit groben Nebenflaechen kleiner",
          zahlen[True] < zahlen[False], f"{zahlen[False]} -> {zahlen[True]} Randdreiecke")


# --------------------------------------------------------------------------
# 3) Linien und Flaechen folgen dem Feld
# --------------------------------------------------------------------------
def test_linienteilung_nach_feld():
    m, k = platte_mit_bohrungen(bohrungen=())
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    m.netz.verfeinerungen = [{"art": "kugel", "mitte": [0.5, 0.0, 0.0], "radius": 0.05, "h": 0.01}]
    m.groessenfeld = netzfeld.aufbauen(m)
    flaechen = [m.flaechen[x] for x in k.flaechen]
    ohne = M3.Linienteilung(m, flaechen, 0.05, feld=netzfeld.Groessenfeld(0.05))
    mit = M3.Linienteilung(m, flaechen, 0.05)
    check("ohne Feld: 1 m / 50 mm = 20 Abschnitte", ohne.n["AU0"] == 20, str(ohne.n["AU0"]))
    check("mit Kugel 10 mm auf der Linie: mehr Abschnitte", mit.n["AU0"] > 20, str(mit.n["AU0"]))
    P = mit.punkte("AU0")
    L = np.linalg.norm(np.diff(P, axis=0), axis=1)
    x = 0.5 * (P[1:, 0] + P[:-1, 0])
    nah, fern = L[np.abs(x - 0.5) < 0.04], L[np.abs(x - 0.5) > 0.3]
    check("die Punkte liegen dicht an der Kugel", nah.mean() < 0.015, f"{nah.mean() * 1e3:.1f} mm")
    check("und weit davon entfernt gleichmaessig bei h", 0.035 < fern.mean() <= 0.05 + 1e-9,
          f"{fern.mean() * 1e3:.1f} mm")
    check("Anfang und Ende liegen genau auf den Knoten",
          np.allclose(P[0], m.nodes[m.lines['AU0'].nodes[0]]) and np.allclose(P[-1], m.nodes[m.lines['AU0'].nodes[1]]))
    check("die Linie AU2 (y = 0,6) bleibt unberuehrt", mit.n["AU2"] == 20, str(mit.n["AU2"]))
    # Zwei Koerper an einer gemeinsamen Linie muessen dieselben Punkte
    # bekommen: dieselbe Kantenlaenge, andere Flaechenmenge, gleiches Ergebnis
    P2 = M3.Linienteilung(m, flaechen[:2], 0.05).punkte("AU0")
    check("dieselbe Linie aus einer anderen Teilung: dieselbe Punktzahl und Lage",
          len(P2) == len(P) and np.allclose(P2, P))


def test_flaechennetz_gradiert():
    # Der Rand ist in h geteilt, wie ihn die Linienteilung liefert - ein Rand
    # aus vier Eckpunkten allein gaebe an jeder Ecke einen Faecher aus Splittern
    s = np.linspace(0.0, 1.0, 11)[:-1]
    ring = [np.vstack([np.column_stack([s, np.zeros(10)]), np.column_stack([np.ones(10), s]),
                       np.column_stack([1.0 - s, np.ones(10)]), np.column_stack([np.zeros(10), 1.0 - s])])]
    P0, T0, fehlt0 = M3._dreiecke_2d(ring, 0.1)
    feld2 = lambda K: 0.02 + netzfeld.WACHSTUM * np.linalg.norm(np.atleast_2d(K) - [0.5, 0.5], axis=1)  # noqa: E731
    P1, T1, fehlt1 = M3._dreiecke_2d(ring, 0.1, None, feld2)
    check("ohne Feld: keine Randstrecke fehlt", not fehlt0)
    check("mit Feld: keine Randstrecke fehlt", not fehlt1)
    d0 = np.linalg.norm(P0 - [0.5, 0.5], axis=1)
    d1 = np.linalg.norm(P1 - [0.5, 0.5], axis=1)
    check("mit Feld liegen viele Punkte um die Mitte", (d1 < 0.1).sum() > 4 * max(1, (d0 < 0.1).sum()),
          f"{(d1 < 0.1).sum()} gegen {(d0 < 0.1).sum()}")
    check("am Rand bleibt es bei der Zielweite", abs((d1 > 0.45).sum() - (d0 > 0.45).sum()) <= 0.5 * (d0 > 0.45).sum() + 4,
          f"{(d1 > 0.45).sum()} gegen {(d0 > 0.45).sum()}")
    A = 0.5 * np.abs((P1[T1[:, 1], 0] - P1[T1[:, 0], 0]) * (P1[T1[:, 2], 1] - P1[T1[:, 0], 1])
                     - (P1[T1[:, 2], 0] - P1[T1[:, 0], 0]) * (P1[T1[:, 1], 1] - P1[T1[:, 0], 1]))
    check("die Dreiecke fuellen das Quadrat", abs(A.sum() - 1.0) < 1e-9, f"{A.sum():.6f}")
    L2 = sum(np.sum((P1[T1[:, a]] - P1[T1[:, b]]) ** 2, axis=1) for a, b in ((0, 1), (1, 2), (2, 0)))
    q = 4 * np.sqrt(3) * A / L2
    check("Dreiecksguete bleibt brauchbar (min > 0,3)", q.min() > 0.3, f"min {q.min():.3f}")


def test_tetraedern_nach_feld():
    m, k = platte_mit_bohrungen(bohrungen=())
    P, T, ber = M3.randschale(m, k, 0.1, [])
    feld = netzfeld.Groessenfeld(0.1)
    feld.kugel([0.5, 0.3, 0.1], 0.03, 0.015)
    Pn0, TET0, b0 = M3.tetraedern(P, T, 0.1)
    Pn1, TET1, b1 = M3.tetraedern(P, T, 0.1, feld=feld)
    check("Volumen stimmt mit und ohne Feld",
          abs(b0["volumen"] - ber["volumen"]) < 1e-3 * ber["volumen"] and abs(b1["volumen"] - ber["volumen"]) < 1e-3 * ber["volumen"])

    def kante(Pn, TET):
        X = Pn[TET]
        return np.mean([np.linalg.norm(X[:, a] - X[:, b], axis=1)
                        for a, b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))], axis=0), X.mean(axis=1)
    L1, C1 = kante(Pn1, TET1)
    L0, C0 = kante(Pn0, TET0)
    nah1 = L1[np.linalg.norm(C1 - [0.5, 0.3, 0.1], axis=1) < 0.03]
    nah0 = L0[np.linalg.norm(C0 - [0.5, 0.3, 0.1], axis=1) < 0.03]
    fern1 = L1[np.linalg.norm(C1 - [0.1, 0.1, 0.1], axis=1) < 0.05]
    check("im Kugelbereich: Kanten nahe 15 mm statt 100 mm", nah1.mean() < 0.03 and nah0.mean() > 0.05,
          f"{nah1.mean() * 1e3:.1f} mm statt {nah0.mean() * 1e3:.1f} mm")
    check("fern der Kugel bleibt es grob", fern1.mean() > 0.05, f"{fern1.mean() * 1e3:.1f} mm")
    check("und die Guete bleibt (min > 0,05)", b1["guete"] > 0.05, f"{b1['guete']:.3f}")


def test_gmsh_und_mmg_mit_feld():
    da = vx.verfuegbar()
    m, k = platte_mit_bohrungen(bohrungen=())
    P, T, ber = M3.randschale(m, k, 0.1, [])
    feld = netzfeld.Groessenfeld(0.1)
    feld.kugel([0.5, 0.3, 0.1], 0.03, 0.01)
    Z = np.array([0.5, 0.3, 0.1])

    def nah_fern(Pn, TET):
        X = Pn[TET]
        L = np.mean([np.linalg.norm(X[:, a] - X[:, b], axis=1)
                     for a, b in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))], axis=0)
        C = X.mean(axis=1)
        return L[np.linalg.norm(C - Z, axis=1) < 0.03].mean(), L[np.linalg.norm(C - [0.1, 0.1, 0.1], axis=1) < 0.06].mean()
    if da["gmsh"][1]:
        Pn0, TET0 = vx.gmsh_tetraedern(P, T, 0.1)
        nah0, _fern0 = nah_fern(Pn0, TET0)
        Pn, TET = vx.gmsh_tetraedern(P, T, 0.1, feld=feld)
        nah, fern = nah_fern(Pn, TET)
        check("gmsh mit Feld: Huellpunkte erhalten", np.allclose(Pn[:len(P)], P))
        # gmsh folgt dem Rueckruf nur teilweise und je Prozesszustand
        # verschieden tief (14,5 oder 38,5 mm bei Ziel 10 mm, 20.09.2026 -
        # bei identischen Antworten des Rueckrufs); verlaesslich ist erst die
        # Metrik von MMG3D. Geprueft wird darum nur: feiner als ohne Feld.
        # Ohne Feld gibt es in 30 mm um die Kugelmitte kein einziges Element
        # (Kanten um 150 mm) - der Vergleich geht darum gegen die Huelle h.
        check("gmsh mit Feld: in der Kugel deutlich feiner als die Huelle, im Feld grob",
              nah < 0.5 * 0.1 and fern > 0.05,
              f"{nah * 1e3:.1f} mm (ohne Feld {nah0 * 1e3:.1f} mm) / fern {fern * 1e3:.1f} mm")
        if da["mmg3d"][1]:
            log = []
            Pn2, TET2 = vx.mmg3d_nachbessern(Pn0, TET0, T, 0.1, feld=feld, log=log)
            nah2, fern2 = nah_fern(Pn2, TET2)
            V = M3.tetraedervolumen(Pn2, TET2)
            check("MMG3D mit Metrik: fein in der Kugel, grob im Feld", nah2 < 0.03 and fern2 > 0.05,
                  f"{nah2 * 1e3:.1f} / {fern2 * 1e3:.1f} mm")
            check("MMG3D mit Metrik: Volumen und Huelle unveraendert",
                  abs(V.sum() - ber["volumen"]) < 1e-6 * ber["volumen"] and np.allclose(Pn2[:len(P)], P))
            check("MMG3D mit Metrik: das Protokoll sagt es", any("Größenfeld" in z for z in log), str(log[-1:])[:90])
        else:
            print("    MMG3D nicht installiert - Metrikweg uebersprungen")
    else:
        print("    gmsh nicht installiert - Rueckrufweg uebersprungen")


# --------------------------------------------------------------------------
# 4) Ein ganzer Koerper durch die Abnahme; Netzknoten; die Folge ohne Oberflaeche
# --------------------------------------------------------------------------
def test_koerper_mit_kugel_durch_die_abnahme():
    m, k = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1),))
    zug_und_lager(m)
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    m.netz.max_elemente = 1_000_000
    # Geprueft wird der freie Vernetzer (Tetraeder); die Platte ist sweepbar
    m.netz.sweep = False
    m.netz.verfeinerungen = [{"art": "kugel", "mitte": [0.6, 0.3, 0.1], "radius": 0.03, "h": 0.006}]
    log = []
    erg = mesher.modell_vernetzen(m, log, workers=1)
    els = list(k.elemente)
    check("der Koerper ist vernetzt", erg["elemente"] > 0 and len(els) == erg["elemente"], f"{erg['elemente']} Elemente")
    check("das Protokoll nennt das Feld", any("Größenfeld" in z for z in log) and any("wirkt hier" in z for z in log))
    L, C = _kanten(m, els)
    d = np.linalg.norm(C - [0.6, 0.3, 0.1], axis=1)
    check("in der Kugel: Kanten um 6 mm", L[d < 0.03].mean() < 0.012, f"{L[d < 0.03].mean() * 1e3:.1f} mm")
    check("weit weg: grob", L[d > 0.3].mean() > 0.02, f"{L[d > 0.3].mean() * 1e3:.1f} mm")
    bef = diagnose.abnahme(m)
    check("die Abnahme vor dem Rechnen hat nichts zu bemaengeln", not bef, str([b.pruefung for b in bef])[:120])
    check("das Flaechenlager folgt dem Netz", len(m.surface_supports[0].nodes) > 20, f"{len(m.surface_supports[0].nodes)} Knoten")
    check("die Last liegt auf den Randseiten", len(m.case("LF1").face_loads) > 10, f"{len(m.case('LF1').face_loads)}")
    return m, k


def test_netzknoten_und_wiederholtes_vernetzen():
    m, k = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1),))
    zug_und_lager(m)
    m.netz.ziellaenge = 0.1
    m.netz.dichte = "eigene"
    m.netz.sweep = False                     # der Tetraederweg ist der Gegenstand
    n_geo = m.nn
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    e1 = len(m.elements)
    # Ein Knotenlager an einem Geometrieknoten, eine Knotenlast an einem
    # freien Knoten und die Eckknoten einer Flaeche (RFEM nennt sie) muessen
    # ueberleben - am richtigen Ort
    geo = int(m.lines["AU0"].nodes[0])
    xk = m.nodes[geo].copy()
    m.support(geo, [0, 1, 2], name="Probe")
    frei = m.add_node(2.0, 2.0, 2.0)
    m.load_node(frei, Fz=-1.0, case="LF1")
    m.flaechen["M2"].ecken = [int(x) for x in m.flaechen["M2"].randknoten(m)]
    ecken_xyz = m.nodes[m.flaechen["M2"].ecken].copy()
    m.elemente_loeschen(list(range(len(m.elements))))
    for f in m.flaechen.values():
        f.elemente = []
    k.elemente = []
    weg = m.netzknoten_loeschen()
    check("netzknoten_loeschen entfernt genau die Knoten des alten Netzes",
          weg > 0 and m.nn == n_geo + 1, f"{weg} entfernt, {m.nn} statt {n_geo} + 1 Knoten")
    check("das Knotenlager sitzt noch am selben Ort", np.allclose(m.nodes[m.supports[-1].node], xk))
    last = [l for l in m.case("LF1").nodal_loads if not getattr(l, "_geo", False)]
    check("die Knotenlast auch (ihr freier Knoten blieb)",
          bool(last) and np.allclose(m.nodes[last[0].node], [2.0, 2.0, 2.0]))
    check("die Eckknoten der Flaeche zeigen auf dieselben Orte",
          np.allclose(m.nodes[m.flaechen["M2"].ecken], ecken_xyz))
    check("das Flaechenlager hat seine alten Netzknoten abgegeben (nur die vier Eckknoten bleiben)",
          len(m.surface_supports[0].nodes) <= 4
          and all(0 <= int(n) < m.nn for n in m.surface_supports[0].nodes),
          f"{len(m.surface_supports[0].nodes)} Knoten")
    check("alle Linien zeigen auf gueltige Knoten",
          all(0 <= int(n) < m.nn for ln in m.lines.values() for n in ln.nodes))
    # Zweites Vernetzen ueber die Folge selbst: sie raeumt auf
    m2, k2 = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1),))
    zug_und_lager(m2)
    m2.netz.ziellaenge = 0.1
    m2.netz.dichte = "eigene"
    m2.netz.sweep = False
    mesher.modell_vernetzen(m2, [], workers=1)
    log = []
    mesher.modell_vernetzen(m2, log, workers=1)
    bef = [b for b in diagnose.abnahme(m2) if b.pruefung == "Knoten ohne Element"]
    check("nach dem zweiten Vernetzen: keine Knoten ohne Element", not bef,
          bef[0].text[:90] if bef else "")
    check("und gleich viele Elemente wie beim ersten Mal", len(m2.elements) == e1, f"{len(m2.elements)} / {e1}")
    check("das Protokoll nennt die entfernten Knoten", any("Knoten des alten Netzes entfernt" in z for z in log))
    check("die Folge misst ihre Schritte", any("Vernetzt:" in z and "davon" in z for z in log))
    check("das Flaechenlager folgt dem neuen Netz", len(m2.surface_supports[0].nodes) > 4)


def test_netzeinstellungen_speichern():
    n = Netzeinstellungen()
    check("Vorgaben: keine Verfeinerung, kein Feld, Nebenflaechen wie bisher",
          n.verfeinerungen == [] and n.feldpunkte == [] and n.koerper_h == {} and n.nebenflaechen_grob is False)
    m = Model()
    m.netz.verfeinerungen = [{"art": "kugel", "mitte": [1, 2, 3], "radius": 0.1, "h": 0.01}]
    m.netz.feldpunkte = [[0.1, 0.2, 0.3, 0.004, 0.002]]
    m.netz.koerper_h = {"V1": 0.08}
    m.netz.nebenflaechen_grob = True
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("Verfeinerungen, Feldpunkte, Koerperkantenlaengen und Schalter ueberleben Speichern und Laden",
          m2.netz.verfeinerungen == m.netz.verfeinerungen and m2.netz.feldpunkte == m.netz.feldpunkte
          and m2.netz.koerper_h == {"V1": 0.08} and m2.netz.nebenflaechen_grob is True)
    d["netz"] = {kk: v for kk, v in d["netz"].items()
                 if kk not in ("verfeinerungen", "feldpunkte", "koerper_h", "nebenflaechen_grob")}
    m3 = Model.from_dict(d)
    check("eine alte Datei ohne die Felder laedt mit Vorgaben",
          m3.netz.verfeinerungen == [] and m3.netz.nebenflaechen_grob is False)
    # koerper_h in der Netzdichte
    m, k = platte_mit_bohrungen(bohrungen=())
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    from statik3d import netzdichte as nd
    h0 = nd.elementlaenge(m, m.netz, k)["h"]
    m.netz.koerper_h = {"V1": 0.08}
    e = nd.elementlaenge(m, m.netz, k)
    check("die eigene Kantenlaenge je Koerper geht vor der Ziellaenge",
          abs(h0 - 0.05) < 1e-12 and abs(e["h"] - 0.08) < 1e-12 and "eigene Kantenlänge" in e["grund"],
          f"{h0 * 1e3:.0f} -> {e['h'] * 1e3:.0f} mm ({e['grund']})")


def main():
    for t in (test_feld_auswertung_exakt, test_feld_ausduennung, test_bedeutung_und_bogenwinkel,
              test_grober_bogenwinkel_macht_die_huelle_kleiner, test_linienteilung_nach_feld,
              test_flaechennetz_gradiert, test_tetraedern_nach_feld, test_gmsh_und_mmg_mit_feld,
              test_koerper_mit_kugel_durch_die_abnahme, test_netzknoten_und_wiederholtes_vernetzen,
              test_netzeinstellungen_speichern):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:100])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
