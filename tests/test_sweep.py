"""
Sweep (statik3d.sweep): Grundflaeche mal Weg - Hexaeder und Keile statt Tetraeder.

Geprueft wird

  * die Erkennung: Platte mit Bohrungen ja, Pyramide nein, Quader bleibt beim
    abgebildeten Pfad, ``netz.sweep = False`` schaltet ab;
  * das Netz: nur hex8 und pent6, alle positiv orientiert, Rauminhalt exakt,
    Hexaederanteil und Elemente je Knoten, Guete, Abnahme;
  * die Randseiten: Lasten auf Grund, Deckel und Wand kommen als Auflagerkraft an;
  * die Vertraeglichkeit mit einem Tetraeder-Nachbarn an einer Wand: der Nachbar
    bekommt das Wandnetz vorgegeben, beide teilen die Knoten;
  * die Lagenvorgabe: Mantellinien, die Nachbarn mit verschiedener Teilung
    gehoeren, sperren den Sweep nicht mehr (Drehlager V18/V11, 21.09.2026);
  * die Lagenzahl bei Fliessen (LAGEN_MIN_PLASTISCH, Messung der Loeser-Sitzung);
  * Speichern und Laden;
  * die Probe, um die es geht: Kragplatte unter Endlast, tet4 gegen gesweepte
    hex8, gegen die Balkenloesung.

Aufruf: python -m tests.test_sweep
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from statik3d.model import Model, DofBehaviour, Material             # noqa: E402
from statik3d import mesher, sweep, diagnose, netzguete, solver       # noqa: E402
from statik3d import mesher3d                                        # noqa: E402
from statik3d.elements.solid import solid_volume, hex8_N_dN, pent6_N_dN  # noqa: E402
from test_netzfeld import platte_mit_bohrungen, zug_und_lager          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return bool(ok)


def _typen(m):
    aus = {}
    for e in m.elements:
        aus[e.typ] = aus.get(e.typ, 0) + 1
    return aus


def _negativ(m) -> int:
    """Elemente mit negativer Jacobi-Determinante in der Mitte."""
    n = 0
    for e in m.elements:
        X = m.nodes[e.nodes]
        if e.typ == "hex8":
            _, dN = hex8_N_dN(0.0, 0.0, 0.0)
        elif e.typ == "pent6":
            _, dN = pent6_N_dN(1.0 / 3.0, 1.0 / 3.0, 0.0)
        else:
            continue
        if np.linalg.det(dN.T @ X) <= 0:
            n += 1
    return n


def test_erkennung():
    m, k = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1), (0.15, 0.1, 0.02)))
    erk = sweep.erkennen(m, k)
    check("Platte mit zwei Bohrungen wird erkannt", erk is not None)
    if erk:
        check("Grund und Deckel sind Boden und Deckel", {erk["grund"].name, erk["deckel"].name} == {"Boden", "Deckel"},
              f"{erk['grund'].name} -> {erk['deckel'].name}")
        check("der Weg ist die Dicke", np.allclose(np.abs(erk["t"]), [0, 0, 0.2]), str(np.round(erk["t"], 3)))
        check("acht Waende (vier aussen, zwei je Bohrung), acht Mantellinien",
              len(erk["waende"]) == 8 and len(erk["mantel"]) == 8)
    check("sweepbar() sagt ja", sweep.sweepbar(m, k))
    m.netz.sweep = False
    check("netz.sweep = False schaltet ab", not sweep.sweepbar(m, k))
    # Pyramide: fuenf Flaechen, keine zwei deckungsgleichen
    p = Model()
    from statik3d.model import Material
    p.add_material(Material.steel("S235"))
    kn = [p.add_node(*x) for x in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1))]
    for i in range(4):
        p.add_line(f"G{i}", [kn[i], kn[(i + 1) % 4]])
        p.add_line(f"S{i}", [kn[i], kn[4]])
    p.add_flaeche("Boden", [f"G{i}" for i in range(4)], material="S235")
    for i in range(4):
        p.add_flaeche(f"D{i}", [f"G{i}", f"S{(i + 1) % 4}", f"S{i}"], material="S235")
    kp = p.add_koerper("P", ["Boden"] + [f"D{i}" for i in range(4)], material="S235")
    check("eine Pyramide ist nicht sweepbar", sweep.erkennen(p, kp) is None)


def test_netz_platte():
    m, k = platte_mit_bohrungen(bohrungen=((0.5, 0.3, 0.1), (0.15, 0.1, 0.02)))
    zug_und_lager(m)
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    log = []
    erg = mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("nur Hexaeder und Keile", set(typen) <= {"hex8", "pent6"}, str(typen))
    check("das Protokoll nennt den Sweep", any("gesweept" in z for z in log))
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = (1.0 * 0.6 - np.pi * 0.1 ** 2 - np.pi * 0.02 ** 2) * 0.2
    # Die Bohrungen sind Vielecke (eingeschrieben), darum etwas mehr Rauminhalt
    check("Rauminhalt: Grundflaeche mal Hoehe, Bohrungen als Vielecke",
          V_soll <= V <= V_soll * 1.01, f"{V:.6f} m^3 (Kreise: {V_soll:.6f})")
    z = sweep.hexaederanteil(m, [k])
    check("Hexaederanteil ueber 75 %", z["anteil_hexaeder"] > 0.75, f"{z['anteil_hexaeder'] * 100:.1f} %")
    check("unter einem Element je Knoten (Tetraeder: vier)", z["elemente_je_knoten"] < 1.2,
          f"{z['elemente_je_knoten']:.2f}")
    q = netzguete.guete(m)
    check("Formguete ueber 0,15 (Keile werden auf den regelmaessigen Keil normiert)",
          float(np.nanmin(q)) > 0.15, f"min {np.nanmin(q):.3f}, Mittel {np.nanmean(q):.3f}")
    bef = diagnose.abnahme(m)
    check("die Abnahme hat nichts zu bemaengeln", not bef, str([b.pruefung for b in bef])[:100])
    # Die Zeile des Koerpers, nicht die modellweite Vorgabe („Sweep: Lagen für …")
    zeile = [z for z in log if "gesweept - Grundfläche" in z]
    check("Lagen: mehr als eine, Mantellinien gleich geteilt", bool(zeile)
          and int(zeile[0].split(" Lagen")[0].split(", ")[-1]) >= 2)
    # Randseiten: Zug an M2 (Wand) kommt als Auflagerkraft an der Einspannung an
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 100e6 * 0.6 * 0.2
    check("Wandlast: Summe der Auflagerkraefte = p * A", abs(float(res.reactions[:, 0].sum()) - F) < 1e-3 * F,
          f"{res.reactions[:, 0].sum() / 1e3:.1f} kN gegen {F / 1e3:.1f} kN")
    # Deckellast
    m.case("LF1").geometrielasten = []
    m.add_geometrielast("Deckel", 2e6, "flaeche", case="LF1")
    m.lasten_verteilen()
    res2 = solver.solve_static(m, case="LF1", workers=1)
    A = 1.0 * 0.6 - 24 * 0.1 ** 2 * np.sin(2 * np.pi / 24) * 0 - 0  # Kreise als Vielecke, Anteil klein
    Fz = 2e6 * (1.0 * 0.6 - np.pi * 0.1 ** 2 - np.pi * 0.02 ** 2)
    check("Deckellast: Summe der Auflagerkraefte = p * A (auf 1 %)",
          abs(float(res2.reactions[:, 2].sum()) + Fz * np.sign(res2.reactions[:, 2].sum() or 1) * 0) > 0
          and abs(abs(float(res2.reactions[:, 2].sum())) - Fz) < 0.01 * Fz,
          f"{abs(res2.reactions[:, 2].sum()) / 1e3:.1f} kN gegen {Fz / 1e3:.1f} kN")
    # Speichern und Laden
    m2 = Model.from_dict(m.to_dict())
    check("Hexaeder und Keile ueberleben Speichern und Laden", _typen(m2) == typen)


def test_quader_bleibt_abgebildet():
    m, k = platte_mit_bohrungen(0.4, 0.2, 0.2, bohrungen=())
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    check("ein Quader (sechs Vierecke, acht Knoten) bleibt beim abgebildeten Netz",
          any("Hexaeder (" in z and " x " in z for z in log), str([z for z in log if "Hexaeder" in z][:1]))


def _platte_mit_pyramide():
    """Gesweepte Platte, an ihrer Wand M2 haengt eine Pyramide (fuenf Flaechen,
    nicht sweepbar, kein Quader) - sie muss das Wandnetz der Platte uebernehmen."""
    m, k = platte_mit_bohrungen(0.4, 0.3, 0.1, bohrungen=((0.2, 0.15, 0.03),))
    ecken = [int(n) for n in m.flaechen["M2"].randknoten(m)]
    spitze = m.add_node(0.4 + 0.3, 0.15, 0.05)
    for i, e in enumerate(ecken):
        m.add_line(f"SP{i}", [e, spitze])
    lin = list(m.flaechen["M2"].linien)

    def linie_zwischen(a, b):
        for name in lin:
            ln = m.lines[name]
            if {int(ln.nodes[0]), int(ln.nodes[-1])} == {a, b}:
                return name
        raise KeyError((a, b))
    fl = []
    for i in range(4):
        a, b = ecken[i], ecken[(i + 1) % 4]
        m.add_flaeche(f"PY{i}", [linie_zwischen(a, b), f"SP{(i + 1) % 4}", f"SP{i}"], material="S235")
        fl.append(f"PY{i}")
    k2 = m.add_koerper("V2", fl + ["M2"], material="S235")
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("Deckel", 1e6, "flaeche", case="LF1")
    ss = m.add_surface_support(name="Einspannung")
    ss.flaechen = ["M4"]
    for d in (0, 1, 2):
        ss.behaviour[d] = DofBehaviour("rigid")
    m.netz.ziellaenge = 0.05
    m.netz.dichte = "eigene"
    m.active_case = "LF1"
    return m, k, k2


def test_nachbar_mit_tetraedern():
    m, k, k2 = _platte_mit_pyramide()
    check("die Platte ist sweepbar, die Pyramide nicht", sweep.sweepbar(m, k) and not sweep.sweepbar(m, k2))
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    t1 = {m.elements[e].typ for e in k.elemente}
    t2 = {m.elements[e].typ for e in k2.elemente}
    check("Platte aus hex8/pent6, Pyramide aus tet4", t1 <= {"hex8", "pent6"} and t2 == {"tet4"} and k2.elemente,
          f"{t1} / {t2}, {len(k2.elemente)} Tetraeder")
    check("die Wand M2 steht als vorgegebenes Flaechennetz bereit",
          "M2" in (getattr(m, "flaechennetze", None) or {}))
    bef = diagnose.abnahme(m)
    check("Abnahme: gemeinsame Flaeche verbunden, keine losen Knoten, Guete, Randtreue",
          not bef, str([(b.pruefung, b.text[:60]) for b in bef])[:160])
    # Dieselben Knoten auf M2: jeder Knoten der Pyramide auf x = 0,4 ist ein Knoten der Platte
    kn1 = {int(x) for e in k.elemente for x in m.elements[e].nodes}
    kn2 = {int(x) for e in k2.elemente for x in m.elements[e].nodes}
    auf_wand = [n for n in kn2 if abs(m.nodes[n][0] - 0.4) < 1e-9]
    check("alle Wandknoten der Pyramide gehoeren auch der Platte",
          auf_wand and all(n in kn1 for n in auf_wand), f"{len(auf_wand)} Wandknoten")
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * (0.4 * 0.3 - np.pi * 0.03 ** 2)
    check("die Last geht durch beide Koerper in die Einspannung",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 0.01 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")


def test_nachbar_mit_verschiedener_teilung():
    """Drehlager V18/V11 (Zaehlung der Loeser-Sitzung, 21.09.2026): erkannt,
    aber null Elemente - „die Mantellinien gehören zweiten Körpern mit
    verschiedener Teilung". Nachgestellt: die Wand M2 der Platte gehoert einer
    Pyramide; an der Mantellinie AV1 (Ecke x = 0,4, y = 0) sitzt eine Kugel des
    Groessenfelds, die sie feiner teilt als AV2. Ohne die modellweite
    Lagenvorgabe (sweep.lagenvorgabe) fiel die Platte an die Tetraeder."""
    m, k, k2 = _platte_mit_pyramide()
    m.netz.verfeinerungen = [{"art": "kugel", "mitte": [0.4, 0.0, 0.05], "radius": 0.03, "h": 0.02}]
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    vorgabe = getattr(m, "linienvorgabe", None) or {}
    mantel = ("AV0", "AV1", "AV2", "AV3")
    check("die Lagen sind fuer alle vier Mantellinien vorab festgelegt, und zwar gleich",
          all(s in vorgabe for s in mantel) and len({vorgabe[s] for s in mantel if s in vorgabe}) == 1,
          str(vorgabe))
    check("die Kugel an AV1 gibt die Lagen vor: mehr als die zwei aus Weg und Kantenlaenge",
          vorgabe.get("AV1", 0) >= 3, f"{vorgabe.get('AV1')} Lagen")
    check("das Protokoll nennt die Vorgabe", any(z.startswith("Sweep: Lagen für") for z in log))
    check("kein Sweep faellt an 'verschiedener Teilung'", not any("verschiedener Teilung" in z for z in log))
    t1 = {m.elements[e].typ for e in k.elemente}
    t2 = {m.elements[e].typ for e in k2.elemente}
    check("die Platte ist gesweept (hex8/pent6), die Pyramide aus tet4",
          k.elemente and t1 <= {"hex8", "pent6"} and t2 == {"tet4"}, f"{t1} / {t2}")
    zeile = [z for z in log if "gesweept - Grundfläche" in z]
    L = int(zeile[0].split(" Lagen")[0].split(", ")[-1]) if zeile else 0
    check("die Lagen des Netzes sind die der Vorgabe", L == vorgabe.get("AV1", -1), f"{L} Lagen")
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    bef = diagnose.abnahme(m)
    check("Abnahme: gemeinsame Flaeche verbunden, keine losen Knoten, Guete, Randtreue",
          not bef, str([(b.pruefung, b.text[:60]) for b in bef])[:160])
    kn1 = {int(x) for e in k.elemente for x in m.elements[e].nodes}
    kn2 = {int(x) for e in k2.elemente for x in m.elements[e].nodes}
    auf_wand = [n for n in kn2 if abs(m.nodes[n][0] - 0.4) < 1e-9]
    check("alle Wandknoten der Pyramide gehoeren auch der Platte",
          auf_wand and all(n in kn1 for n in auf_wand), f"{len(auf_wand)} Wandknoten")
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * (0.4 * 0.3 - np.pi * 0.03 ** 2)
    check("die Last geht durch beide Koerper in die Einspannung",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 0.01 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")


def test_lagen_bei_fliessen():
    """LAGEN_MIN_PLASTISCH: mit Fliessen wenigstens vier Lagen. Messung der
    Loeser-Sitzung (21.09.2026, Kragtraeger unter 1,20 M_el): mit einer und
    zwei Lagen fliesst kein Element, ab drei wird gefunden, was da ist;
    elastisch bleibt es bei LAGEN_MIN."""
    def netz(fliessen):
        m, k = platte_mit_bohrungen(0.4, 0.3, 0.05, bohrungen=((0.2, 0.15, 0.03),))
        m.netz.ziellaenge = 0.05
        m.netz.dichte = "eigene"
        m.plastizitaet.an = fliessen
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
        zeile = [z for z in log if "gesweept - Grundfläche" in z]
        L = int(zeile[0].split(" Lagen")[0].split(", ")[-1]) if zeile else 0
        return m, k, L, log
    m_e, k_e, L_e, log_e = netz(False)
    m_p, k_p, L_p, log_p = netz(True)
    check("elastisch: LAGEN_MIN Lagen (Weg 50 mm bei h = 50 mm)", L_e == sweep.LAGEN_MIN, f"{L_e} Lagen")
    check("mit Fliessen: LAGEN_MIN_PLASTISCH Lagen", L_p == sweep.LAGEN_MIN_PLASTISCH, f"{L_p} Lagen")
    check("das Grundflaechennetz bleibt, nur die Lagen werden mehr",
          L_e and L_p and len(k_p.elemente) * L_e == len(k_e.elemente) * L_p,
          f"{len(k_e.elemente)} -> {len(k_p.elemente)} Elemente")
    check("das Protokoll nennt den Grund",
          any("wegen Fließen" in z for z in log_p) and not any("wegen Fließen" in z for z in log_e))
    check("lagen_min(model) folgt dem Schalter",
          sweep.lagen_min(m_e) == sweep.LAGEN_MIN and sweep.lagen_min(m_p) == sweep.LAGEN_MIN_PLASTISCH)


def quader(a=2.0, b=1.0, c=1.0, name="V1", material="S235", teilung=(4, 2, 2)):
    """Ein Quader aus sechs Vierecken mit acht Eckknoten - der abgebildete
    Pfad (mesher._hex_netz). Boden z = 0, Deckel z = c, Wand X1 bei x = a."""
    m = Model()
    m.add_material(Material.steel(material))
    E = [(0, 0), (a, 0), (a, b), (0, b)]
    ku = [m.add_node(x, y, 0.0) for x, y in E]
    ko = [m.add_node(x, y, c) for x, y in E]
    for i in range(4):
        j = (i + 1) % 4
        m.add_line(f"QU{i}", [ku[i], ku[j]])
        m.add_line(f"QO{i}", [ko[i], ko[j]])
        m.add_line(f"QV{i}", [ku[i], ko[i]])
    m.add_flaeche("QBoden", [f"QU{i}" for i in range(4)], material=material)
    m.add_flaeche("QDeckel", [f"QO{i}" for i in range(4)], material=material)
    namen = ["Y0", "X1", "Y1", "X0"]
    for i in range(4):
        j = (i + 1) % 4
        m.add_flaeche(namen[i], [f"QU{i}", f"QV{j}", f"QO{i}", f"QV{i}"], material=material)
    k = m.add_koerper(name, ["QBoden", "QDeckel"] + namen, material=material, teilung=list(teilung))
    return m, k


def test_quader_randseiten_und_nachbar():
    """Der abgebildete Quaderpfad setzte bis zum 21.09.2026 keine Randseiten
    (Flaechenlast: Auflagerkraft 0 kN) und teilte keine Knoten mit Nachbarn
    (Abnahme: doppelte Knoten). Jetzt: Randseiten wie beim Sweep, Knoten ueber
    dieselben Schluessel, vorgegebene Flaechennetze - und die Linienvorgabe,
    wenn ein Nachbar eine Kante feiner braucht."""
    m, k = quader()
    # Pyramide an der Wand X1 (x = 2): fuenf Flaechen, nicht sweepbar -> Tetraeder
    ecken = [int(n) for n in m.flaechen["X1"].randknoten(m)]
    spitze = m.add_node(2.0 + 0.8, 0.5, 0.5)
    for i, e in enumerate(ecken):
        m.add_line(f"SP{i}", [e, spitze])
    lin = list(m.flaechen["X1"].linien)

    def linie_zwischen(a, b):
        for name in lin:
            ln = m.lines[name]
            if {int(ln.nodes[0]), int(ln.nodes[-1])} == {a, b}:
                return name
        raise KeyError((a, b))
    fl = []
    for i in range(4):
        a, b = ecken[i], ecken[(i + 1) % 4]
        m.add_flaeche(f"PY{i}", [linie_zwischen(a, b), f"SP{(i + 1) % 4}", f"SP{i}"], material="S235")
        fl.append(f"PY{i}")
    k2 = m.add_koerper("V2", fl + ["X1"], material="S235")
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast("QDeckel", 1e6, "flaeche", case="LF1")
    ss = m.add_surface_support(name="Einspannung")
    ss.flaechen = ["QBoden"]
    for d in (0, 1, 2):
        ss.behaviour[d] = DofBehaviour("rigid")
    m.netz.ziellaenge = 0.25
    m.netz.dichte = "eigene"
    # Eine Kugel des Groessenfelds an der Kante QV1 (x = 2, y = 0): die Pyramide
    # teilt sie feiner als der Quader mit teilung 2 - die Vorgabe muss folgen
    m.netz.verfeinerungen = [{"art": "kugel", "mitte": [2.0, 0.0, 0.5], "radius": 0.3, "h": 0.1}]
    m.active_case = "LF1"
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    t1 = {m.elements[e].typ for e in k.elemente}
    t2 = {m.elements[e].typ for e in k2.elemente}
    check("Quader aus hex8 (abgebildet), Pyramide aus tet4", t1 == {"hex8"} and t2 == {"tet4"}, f"{t1} / {t2}")
    vorgabe = getattr(m, "linienvorgabe", None) or {}
    check("die z-Kanten des Quaders tragen die Vorgabe der Kugel (mehr als teilung 2)",
          all(f"QV{i}" in vorgabe for i in range(4)) and vorgabe.get("QV1", 0) > 2, str(vorgabe))
    # Die Wand X1 gehoert der Pyramide: ihre y- und z-Kanten tragen deren Karte,
    # die x-Kanten bleiben bei der eigenen Teilung 4
    ny, nz = vorgabe.get("QU1", 2), vorgabe.get("QV1", 2)
    check("die Elementzahl folgt der Vorgabe: 4 x ny x nz", len(k.elemente) == 4 * ny * nz,
          f"{len(k.elemente)} Elemente, ny = {ny}, nz = {nz}")
    hex_x1 = [x for x in m.flaechen["X1"].randseiten if m.elements[int(x[0])].typ == "hex8"]
    check("Randseiten: Deckel und Boden 4 x ny Hexaederseiten, Wand X1 ny x nz (dazu die der Pyramide)",
          len(m.flaechen["QDeckel"].randseiten) == 4 * ny and len(m.flaechen["QBoden"].randseiten) == 4 * ny
          and len(hex_x1) == ny * nz,
          f"{len(m.flaechen['QDeckel'].randseiten)} / {len(m.flaechen['QBoden'].randseiten)} / {len(hex_x1)}")
    check("die sechs Flaechen stehen als vorgegebene Flaechennetze bereit",
          all(x in (getattr(m, "flaechennetze", None) or {}) for x in ("QBoden", "QDeckel", "X1", "X0", "Y0", "Y1")))
    bef = diagnose.abnahme(m)
    check("Abnahme: gemeinsame Flaeche verbunden, keine doppelten Knoten, Guete, Randtreue",
          not bef, str([(b.pruefung, b.text[:60]) for b in bef])[:160])
    kn1 = {int(x) for e in k.elemente for x in m.elements[e].nodes}
    kn2 = {int(x) for e in k2.elemente for x in m.elements[e].nodes}
    auf_wand = [n for n in kn2 if abs(m.nodes[n][0] - 2.0) < 1e-9]
    check("alle Wandknoten der Pyramide sind Knoten des Quaders",
          auf_wand and all(n in kn1 for n in auf_wand), f"{len(auf_wand)} Wandknoten")
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * 2.0 * 1.0
    check("die Deckellast kommt als Auflagerkraft an (vorher 0 kN)",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 1e-3 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.1f} kN gegen {F / 1e3:.1f} kN")
    # Speichern und Laden
    m2 = Model.from_dict(m.to_dict())
    check("das Netz ueberlebt Speichern und Laden", _typen(m2) == _typen(m))


def _kreis(m, tag, cx, cy, z, r):
    """Ein Kreis aus zwei Halbboegen zwischen zwei Knoten - wie aus RFEM.
    Rueckgabe (Knoten p, Knoten q, Linie 1, Linie 2)."""
    p = m.add_node(cx - r, cy, z)
    q = m.add_node(cx + r, cy, z)
    l1, l2 = f"{tag}1", f"{tag}2"
    m.add_line(l1, [p, q], "arc", punkte=[(cx - r, cy, z), (cx, cy + r, z), (cx + r, cy, z)])
    m.add_line(l2, [q, p], "arc", punkte=[(cx + r, cy, z), (cx, cy - r, z), (cx - r, cy, z)])
    return p, q, l1, l2


def _zylinder(m, tag, cx, cy, z0, z1, r, material="S235"):
    """Mantel eines Zylinders (zwei Halbmantel-Flaechen) zwischen den Kreisen
    bei z0 und z1. Rueckgabe (Kreis unten, Kreis oben, Mantelflaechen)."""
    pu, qu, u1, u2 = _kreis(m, f"{tag}U", cx, cy, z0, r)
    po, qo, o1, o2 = _kreis(m, f"{tag}O", cx, cy, z1, r)
    m.add_line(f"{tag}V1", [pu, po])
    m.add_line(f"{tag}V2", [qu, qo])
    m.add_flaeche(f"{tag}Mantel1", [u1, f"{tag}V2", o1, f"{tag}V1"], material=material)
    m.add_flaeche(f"{tag}Mantel2", [u2, f"{tag}V1", o2, f"{tag}V2"], material=material)
    return (u1, u2), (o1, o2), [f"{tag}Mantel1", f"{tag}Mantel2"]


def _lager_und_last(m, lager, last, p):
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.add_geometrielast(last, p, "flaeche", case="LF1")
    ss = m.add_surface_support(name="Einspannung")
    ss.flaechen = [lager]
    for d in (0, 1, 2):
        ss.behaviour[d] = DofBehaviour("rigid")
    m.active_case = "LF1"


def _flaechenmass(m, name) -> float:
    """Flaecheninhalt einer Randflaeche aus ihren Randseiten (Dreiecke, Vierecke)."""
    from statik3d.assemble import SOLID_FACES
    A = 0.0
    for e, s in m.flaechen[name].randseiten:
        el = m.elements[int(e)]
        X = m.nodes[[int(el.nodes[i]) for i in SOLID_FACES[el.typ][int(s)]]]
        A += 0.5 * float(np.linalg.norm(sum(np.cross(X[i] - X[0], X[i + 1] - X[0]) for i in range(1, len(X) - 1))))
    return A


def _doppelte_knoten(m, kn) -> int:
    """Knoten unter den genannten, die an derselben Stelle liegen wie ein anderer."""
    from scipy.spatial import cKDTree
    kn = sorted(kn)
    if len(kn) < 2:
        return 0
    X = m.nodes[kn]
    paare = cKDTree(X).query_pairs(1e-9)
    return len(paare)


def test_zylinder_wird_gesweept():
    """Ein Zylinder hat vier Flaechen (zwei Kreise, zwei Halbmantel) - bis zum
    21.09.2026 verlangte die Erkennung fuenf, und jeder Bolzen fiel an die
    Tetraeder (48 von 108 Drehlager-Koerpern haben vier Flaechen)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    unten, oben, mantel = _zylinder(m, "Z", 0.0, 0.0, 0.0, 0.3, 0.05)
    m.add_flaeche("ZBoden", list(unten), material="S235")
    m.add_flaeche("ZDeckel", list(oben), material="S235")
    k = m.add_koerper("Bolzen", ["ZBoden", "ZDeckel"] + mantel, material="S235")
    _lager_und_last(m, "ZBoden", "ZDeckel", 1e6)
    m.netz.ziellaenge = 0.03
    m.netz.dichte = "eigene"
    check("der Zylinder ist sweepbar (vier Flaechen)", sweep.sweepbar(m, k))
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("nur Hexaeder und Keile", set(typen) <= {"hex8", "pent6"} and typen, str(typen))
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = np.pi * 0.05 ** 2 * 0.3
    check("Rauminhalt: Kreis als Vieleck, innerhalb 2 % unter pi r^2 h", 0.98 * V_soll <= V <= V_soll,
          f"{V:.6f} m^3 gegen {V_soll:.6f}")
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([b.pruefung for b in bef])[:100])
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * _flaechenmass(m, "ZDeckel")
    check("die Deckellast kommt als Auflagerkraft an",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 1e-3 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")


def _platte_mit_nabe(a=0.4, b=0.3, t=0.1, r=0.06, hoehe=0.08):
    """Platte a x b x t, auf dem Deckel eine zylindrische Nabe (Radius r, Hoehe
    hoehe): der Deckel traegt den Fussabdruck als Oeffnung, die Nabe besteht aus
    zwei Mantelflaechen und einer Kreisscheibe. Nicht als Ganzes Grundflaeche
    mal Weg - erst nach dem Schnitt am Fussabdruck."""
    m = Model()
    m.add_material(Material.steel("S235"))
    E = [(0, 0), (a, 0), (a, b), (0, b)]
    ku = [m.add_node(x, y, 0.0) for x, y in E]
    ko = [m.add_node(x, y, t) for x, y in E]
    for i in range(4):
        j = (i + 1) % 4
        m.add_line(f"AU{i}", [ku[i], ku[j]])
        m.add_line(f"AO{i}", [ko[i], ko[j]])
        m.add_line(f"AV{i}", [ku[i], ko[i]])
    namen = []
    for i in range(4):
        j = (i + 1) % 4
        m.add_flaeche(f"M{i + 1}", [f"AU{i}", f"AV{j}", f"AO{i}", f"AV{i}"], material="S235")
        namen.append(f"M{i + 1}")
    unten, oben, mantel = _zylinder(m, "N", a / 2, b / 2, t, t + hoehe, r)
    m.add_flaeche("Boden", [f"AU{i}" for i in range(4)], material="S235")
    m.add_flaeche("Deckel", [f"AO{i}" for i in range(4)], material="S235", oeffnungen=[list(unten)])
    m.add_flaeche("NDeckel", list(oben), material="S235")
    k = m.add_koerper("V1", namen + ["Boden", "Deckel", "NDeckel"] + mantel, material="S235")
    _lager_und_last(m, "Boden", "NDeckel", 1e6)
    m.netz.ziellaenge = 0.03
    m.netz.dichte = "eigene"
    return m, k


def test_platte_mit_nabe_zerlegt():
    """Zerlegen an Fussabdruecken: Platte mit Nabe -> zwei gesweepte Bloecke,
    knotenkonform an der Schnittflaeche, alles Hexaeder und Keile."""
    m, k = _platte_mit_nabe()
    check("als Ganzes nicht sweepbar", sweep.erkennen(m, k) is None)
    bl, schnitte = sweep.zerlegen(m, k)
    check("das Zerlegen findet zwei sweepbare Bloecke an einem Schnitt",
          bl is not None and len(bl) == 2 and all(e is not None for _n, e in bl) and len(schnitte) == 1,
          f"{None if bl is None else [(len(n), e is not None) for n, e in bl]}, {len(schnitte)} Schnitt(e)")
    sweep.schnitte_entfernen(m, schnitte)
    check("die Schnittflaeche ist danach wieder aus dem Modell", not any(x.startswith("V1§") for x in m.flaechen))
    check("sweepbar() sagt ja - der Koerper laeuft im Hauptprozess vor den freien", sweep.sweepbar(m, k))
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("nur Hexaeder und Keile, kein Tetraeder", set(typen) <= {"hex8", "pent6"} and typen, str(typen))
    check("das Protokoll nennt das Zerlegen", any("zerlegt" in z for z in log))
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = 0.4 * 0.3 * 0.1 + np.pi * 0.06 ** 2 * 0.08
    check("Rauminhalt Platte + Nabe (Kreis als Vieleck)", 0.995 * V_soll <= V <= V_soll,
          f"{V:.6f} m^3 gegen {V_soll:.6f}")
    # Knotenkonform an der Schnittflaeche: kein Knoten doppelt in der Ebene z = t
    ebene = [n for n in range(m.nn) if abs(m.nodes[n][2] - 0.1) < 1e-9]
    check("keine doppelten Knoten in der Schnittebene", _doppelte_knoten(m, ebene) == 0, f"{len(ebene)} Knoten")
    check("keine Schnittflaeche bleibt im Modell", not any(x.startswith("V1§") for x in m.flaechen))
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([(b.pruefung, b.text[:50]) for b in bef])[:160])
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * _flaechenmass(m, "NDeckel")
    check("die Last auf der Nabe geht durch die Schnittflaeche in die Platte und ins Lager",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 1e-3 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")
    m2 = Model.from_dict(m.to_dict())
    check("das Netz ueberlebt Speichern und Laden", _typen(m2) == typen)


def test_abgesetzte_welle_zerlegt():
    """Abgesetzte Welle: dicker Absatz r1 und duenner r2 hintereinander; die
    Schulter (Kreisring) traegt den Fussabdruck des duennen Teils als Oeffnung."""
    m = Model()
    m.add_material(Material.steel("S235"))
    r1, r2, l1, l2 = 0.05, 0.03, 0.2, 0.15
    unten1, oben1, mantel1 = _zylinder(m, "D", 0.0, 0.0, 0.0, l1, r1)
    unten2, oben2, mantel2 = _zylinder(m, "K", 0.0, 0.0, l1, l1 + l2, r2)
    m.add_flaeche("Ende1", list(unten1), material="S235")
    m.add_flaeche("Schulter", list(oben1), material="S235", oeffnungen=[list(unten2)])
    m.add_flaeche("Ende2", list(oben2), material="S235")
    k = m.add_koerper("Welle", ["Ende1", "Schulter", "Ende2"] + mantel1 + mantel2, material="S235")
    _lager_und_last(m, "Ende1", "Ende2", 1e6)
    m.netz.ziellaenge = 0.025
    m.netz.dichte = "eigene"
    check("als Ganzes nicht sweepbar (sieben Flaechen, zwei Radien)", sweep.erkennen(m, k) is None)
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("nur Hexaeder und Keile", set(typen) <= {"hex8", "pent6"} and typen, str(typen))
    check("das Protokoll nennt zwei gesweepte Bloecke",
          any("2 gesweept, 0 frei" in z for z in log), str([z for z in log if "Blöcke" in z])[:200])
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = np.pi * (r1 ** 2 * l1 + r2 ** 2 * l2)
    check("Rauminhalt beider Absaetze (Kreise als Vielecke)", 0.98 * V_soll <= V <= V_soll,
          f"{V:.6f} m^3 gegen {V_soll:.6f}")
    ebene = [n for n in range(m.nn) if abs(m.nodes[n][2] - l1) < 1e-9]
    check("keine doppelten Knoten in der Schulterebene", _doppelte_knoten(m, ebene) == 0, f"{len(ebene)} Knoten")
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([(b.pruefung, b.text[:50]) for b in bef])[:160])
    res = solver.solve_static(m, case="LF1", workers=1)
    F = 1e6 * _flaechenmass(m, "Ende2")
    check("die Last am duennen Ende kommt durch die Schulter im Lager an",
          abs(abs(float(res.reactions[:, 2].sum())) - F) < 1e-3 * F,
          f"{abs(res.reactions[:, 2].sum()) / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")


def test_pyramiden_als_uebergang():
    """netz.pyramiden: wo der Tetraeder-Nachbar an die Vierecke der gesweepten
    Wand stoesst, bekommt jedes Viereck eine Pyramide (pyr5) mit Spitze im
    Inneren; die Tetraeder folgen dahinter. Ohne den Schalter bleibt es beim
    geteilten Viereck - beides knotenkonform."""
    zahlen = {}
    for pyr in (False, True):
        m, k, k2 = _platte_mit_pyramide()
        m.netz.pyramiden = pyr
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
        typen = _typen(m)
        V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
        q = netzguete.guete(m)
        bef = diagnose.abnahme(m)
        res = solver.solve_static(m, case="LF1", workers=1)
        zahlen[pyr] = {"typen": typen, "V": V, "q": float(np.nanmin(q)), "bef": bef,
                       "R": abs(float(res.reactions[:, 2].sum())),
                       "u": float(np.abs(res.u[:, :3]).max()), "log": log, "m": m, "k2": k2}
    aus, an = zahlen[False], zahlen[True]
    check("ohne Schalter keine Pyramide", not aus["typen"].get("pyr5"), str(aus["typen"]))
    check("mit Schalter Pyramiden am Uebergang, Rest Tetraeder",
          an["typen"].get("pyr5", 0) > 0 and an["typen"].get("tet4", 0) > 0
          and an["typen"].get("tet4", 0) < aus["typen"].get("tet4", 0),
          f"{aus['typen']} -> {an['typen']}")
    check("das Protokoll nennt die Nachbarflaeche",
          any("Pyramiden (pyr5) als Übergang" in z and "M2" in z for z in an["log"]))
    check("die Bilanz zaehlt sie", any("Pyramiden 12" in z or "Pyramiden " in z and "Hexaeder" in z
                                       for z in an["log"]))
    check("der Rauminhalt bleibt derselbe", abs(an["V"] - aus["V"]) < 1e-9 * aus["V"],
          f"{aus['V']:.6f} -> {an['V']:.6f} m^3")
    check("die Verschiebung aendert sich um weniger als ein Prozent",
          abs(an["u"] - aus["u"]) < 0.01 * aus["u"], f"{aus['u'] * 1e3:.4f} -> {an['u'] * 1e3:.4f} mm")
    F = 1e6 * (0.4 * 0.3 - np.pi * 0.03 ** 2)
    check("die Last kommt weiter an", abs(an["R"] - F) < 0.01 * F, f"{an['R'] / 1e3:.2f} kN gegen {F / 1e3:.2f} kN")
    check("Abnahme ohne Befund, Formguete ueber 0,1", not an["bef"] and an["q"] > 0.1,
          f"Güte min {an['q']:.3f}, {[b.pruefung for b in an['bef']]}")
    # Knotenkonform: die Pyramidengrundflaechen liegen auf der Wand M2, ihre
    # Knoten sind die der Platte
    m2 = an["m"]
    kn_platte = {int(x) for e in m2.koerper["V1"].elemente for x in m2.elements[e].nodes}
    grund = [e for e in an["k2"].elemente if m2.elements[e].typ == "pyr5"]
    check("jede Pyramide steht mit ihren vier Grundknoten auf der Platte",
          grund and all(all(int(x) in kn_platte for x in m2.elements[e].nodes[:4]) for e in grund),
          f"{len(grund)} Pyramiden")
    check("und ihre Spitze gehoert nur dem Nachbarn",
          all(int(m2.elements[e].nodes[4]) not in kn_platte for e in grund))
    check("die Randseiten der Wand nennen die Pyramiden",
          sum(1 for e, _s in m2.flaechen["M2"].randseiten if m2.elements[int(e)].typ == "pyr5") == len(grund),
          f"{len(m2.flaechen['M2'].randseiten)} Randseiten")


def test_zerlegen_sagt_warum_nicht():
    """Am Drehlager stand keine einzige Zeile über das Zerlegen im Protokoll
    (Lauf der Löser-Sitzung, 21.09.2026) - damit ließ sich nicht sagen, woran
    es lag. Jetzt sagt es der Körper selbst, einmal und mit Zahlen."""
    m, k, k2 = _platte_mit_pyramide()
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    zeile = [z for z in log if "nicht zerlegt" in z]
    check("der nicht sweepbare Nachbar sagt, warum kein Schnitt ansetzt",
          zeile and "Öffnung" in zeile[0], str(zeile[:1])[:160])
    check("und nennt dabei seine Randflächen", zeile and "5 Randflächen" in zeile[0], str(zeile[:1])[:160])
    # Ein Körper mit Öffnung, aber ohne Aufsatz darauf: andere Begründung
    m2, k3 = platte_mit_bohrungen(0.4, 0.3, 0.1, bohrungen=((0.2, 0.15, 0.03),))
    grund = sweep.zerlegen_warum_nicht(m2, k3)
    check("eine Platte mit Bohrung nennt die Öffnung ohne Aufsatz",
          "kein Aufsatz" in grund, grund[:120])
    check("die gesweepte Platte mit Nabe findet dagegen einen Fußabdruck",
          "Fußabdruck" in sweep.zerlegen_warum_nicht(*_platte_mit_nabe()),
          sweep.zerlegen_warum_nicht(*_platte_mit_nabe())[:120])


def platte_mit_stufe(a=0.2, b=0.1, t=0.035, d=0.00045, h=0.05):
    """Gesweepte Platte, deren Umriss eine **winzige Stufe** hat: zwei
    Randknoten d auseinander bei der Kantenlänge h.

    Das ist der Drehlager-Fall (V35, Element 11313, Güte 0,025): eine Kante
    von 0,456 mm gegen 17,23 mm der übrigen. Nicht die Stufe selbst macht den
    Schaden - sie ist **eine** Kante -, sondern die Regel „eine Linie darf
    nicht neben einer viel feineren stehenbleiben"
    (mesher3d._linien_wachsen_lassen): sie teilt die 50-mm-Nachbarlinien in
    3,1-mm-Strecken, und gegen ein 50-mm-Inneres ist jedes Dreieck dazwischen
    ein Splitter. Der Sweep zieht jeden davon über alle Lagen zum Keil aus.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    E = [(0, 0), (a, 0), (a, b * 0.5), (a - d * 0.8, b * 0.5 + d * 0.6), (a, b), (0, b)]
    ku = [m.add_node(x, y, 0.0) for x, y in E]
    ko = [m.add_node(x, y, t) for x, y in E]
    n = len(E)
    for i in range(n):
        j = (i + 1) % n
        m.add_line(f"SU{i}", [ku[i], ku[j]])
        m.add_line(f"SO{i}", [ko[i], ko[j]])
        m.add_line(f"SV{i}", [ku[i], ko[i]])
    namen = []
    for i in range(n):
        j = (i + 1) % n
        m.add_flaeche(f"SM{i}", [f"SU{i}", f"SV{j}", f"SO{i}", f"SV{i}"], material="S235")
        namen.append(f"SM{i}")
    m.add_flaeche("SBoden", [f"SU{i}" for i in range(n)], material="S235")
    m.add_flaeche("SDeckel", [f"SO{i}" for i in range(n)], material="S235")
    k = m.add_koerper("V1", namen + ["SBoden", "SDeckel"], material="S235")
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    return m, k


def test_keile_am_feinen_rand():
    """Der Auftrag „entartete Keile" (Statik3D-Sitzung, 21.09.2026): am
    Drehlager waren 992 von 9 368 Keilen unter der Güte 0,10 (10,6 %) und
    **kein einziger** von 31 108 Hexaedern.

    Die Ursache ist nicht die Paarung, sondern ein Band feiner Randstrecken
    gegen ein grobes Flächeninneres; der Sweep zieht jedes Splitterdreieck
    über alle Lagen aus. Das Randfeld (mesher3d.RANDFELD) lässt das Innennetz
    dem feinen Rand folgen - dieselbe Regel, die das Tetraedernetz längst hat.
    """
    zahlen = {}
    for randfeld in (False, True):
        alt = mesher3d.RANDFELD
        mesher3d.RANDFELD = randfeld
        try:
            for sweep_an in (True, False):
                m, k = platte_mit_stufe()
                m.netz.sweep = sweep_an
                mesher.modell_vernetzen(m, [], workers=1)
                q = netzguete.guete(m)
                q = q[np.isfinite(q)]
                zahlen[(randfeld, sweep_an)] = (len(q), float(q.min()), int((q < 0.1).sum()),
                                                dict(_typen(m)))
        finally:
            mesher3d.RANDFELD = alt
    aus_s, an_s = zahlen[(False, True)], zahlen[(True, True)]
    aus_t, an_t = zahlen[(False, False)], zahlen[(True, False)]
    check("ohne Randfeld entarten die Keile (der Drehlager-Befund, nachgestellt)",
          aus_s[2] > 20 and aus_s[1] < 0.1 and an_s[3].get("hex8", 0) > 0,
          f"{aus_s[2]} Elemente unter 0,10, Güte min {aus_s[1]:.4f}, {aus_s[3]}")
    check("mit Randfeld ist keiner mehr unter 0,10", an_s[2] == 0,
          f"{aus_s[2]} → {an_s[2]} Elemente unter 0,10")
    check("und die schlechteste Güte steigt deutlich", an_s[1] > 2.0 * aus_s[1],
          f"{aus_s[1]:.4f} → {an_s[1]:.4f}")
    check("der Preis sind weniger als doppelt so viele Elemente",
          an_s[0] < 2.0 * aus_s[0], f"{aus_s[0]} → {an_s[0]} Elemente")
    check("dasselbe im Tetraederweg - die Hülle erbt die Splitter sonst ebenso",
          aus_t[2] > 0 and an_t[2] == 0 and an_t[1] > 2.0 * aus_t[1],
          f"{aus_t[2]} → {an_t[2]} unter 0,10, Güte {aus_t[1]:.4f} → {an_t[1]:.4f}")
    check("der Tetraederweg war nie die bessere Wahl: gleiche Güte, ein Vielfaches an Elementen",
          abs(aus_t[1] - aus_s[1]) < 0.01 and aus_t[0] > 10 * aus_s[0],
          f"tet4 {aus_t[0]} Elemente/Güte {aus_t[1]:.4f} gegen Sweep {aus_s[0]}/{aus_s[1]:.4f}")
    # Wo kein feiner Rand ist, kostet die Regel fast nichts
    ohne = {}
    for randfeld in (False, True):
        alt = mesher3d.RANDFELD
        mesher3d.RANDFELD = randfeld
        try:
            m, k = platte_mit_bohrungen(1.0, 0.6, 0.2, bohrungen=((0.5, 0.3, 0.1),))
            m.netz.ziellaenge = 0.05
            m.netz.dichte = "eigene"
            mesher.modell_vernetzen(m, [], workers=1)
            q = netzguete.guete(m)
            q = q[np.isfinite(q)]
            ohne[randfeld] = (len(q), float(q.min()))
        finally:
            mesher3d.RANDFELD = alt
    check("an einer gewöhnlichen Platte ändert sich fast nichts",
          ohne[True][0] < 1.15 * ohne[False][0] and ohne[True][1] >= 0.9 * ohne[False][1],
          f"{ohne[False][0]} → {ohne[True][0]} Elemente, Güte {ohne[False][1]:.3f} → {ohne[True][1]:.3f}")


def test_kragplatte_tet4_gegen_hex8():
    """Das Erfolgsmass des Auftrags an der Kragplatte 1 x 0,2 x 0,05 m mit
    Endlast 10 kN, gegen Bernoulli + Schub. Eine kleine Bohrung am freien
    Ende macht die Platte zum Sweep-Fall (ein Quader bliebe abgebildet)."""
    E_, nu_ = 210e9, 0.3
    L_, b_, t_, F = 1.0, 0.2, 0.05, 10e3
    G_ = E_ / (2 * (1 + nu_))
    I_ = b_ * t_ ** 3 / 12
    w_balken = F * L_ ** 3 / (3 * E_ * I_) + F * L_ / (5.0 / 6.0 * G_ * b_ * t_)

    def rechnen(sweep_an, h):
        m, k = platte_mit_bohrungen(L_, b_, t_, bohrungen=((0.95, 0.1, 0.01),))
        m.add_load_case("LF1")
        m.case("LF1").gravity = [0.0, 0.0, 0.0]
        m.add_geometrielast("M2", F / (b_ * t_), "flaeche", richtung=[0.0, 0.0, -1.0], case="LF1")
        ss = m.add_surface_support(name="Einspannung")
        ss.flaechen = ["M4"]
        for d in (0, 1, 2):
            ss.behaviour[d] = DofBehaviour("rigid")
        m.netz.ziellaenge = h
        m.netz.dichte = "eigene"
        m.netz.sweep = sweep_an
        m.active_case = "LF1"
        mesher.modell_vernetzen(m, [], workers=1)
        res = solver.solve_static(m, case="LF1", workers=1)
        return float(np.abs(res.u[:, 2]).max()), _typen(m), int(m.nn)
    w_tet, typ_tet, nn_tet = rechnen(False, 0.025)
    w_hex, typ_hex, nn_hex = rechnen(True, 0.025)
    print(f"    Balken: {w_balken * 1e3:.3f} mm | tet4: {w_tet * 1e3:.3f} mm = {w_tet / w_balken * 100:.1f} % "
          f"({typ_tet}, {nn_tet} Knoten) | Sweep: {w_hex * 1e3:.3f} mm = {w_hex / w_balken * 100:.1f} % "
          f"({typ_hex}, {nn_hex} Knoten)")
    check("der lineare Tetraeder ist zu steif (unter 80 % der Balkenloesung)", w_tet < 0.8 * w_balken,
          f"{w_tet / w_balken * 100:.1f} %")
    check("die gesweepte Platte trifft die Balkenloesung auf 10 %", abs(w_hex / w_balken - 1.0) < 0.10,
          f"{w_hex / w_balken * 100:.1f} %")
    check("und braucht dafuer weniger Knoten", nn_hex < nn_tet, f"{nn_hex} gegen {nn_tet}")


def main():
    for t in (test_erkennung, test_netz_platte, test_quader_bleibt_abgebildet, test_nachbar_mit_tetraedern,
              test_nachbar_mit_verschiedener_teilung, test_lagen_bei_fliessen,
              test_quader_randseiten_und_nachbar, test_zylinder_wird_gesweept,
              test_platte_mit_nabe_zerlegt, test_abgesetzte_welle_zerlegt,
              test_pyramiden_als_uebergang, test_zerlegen_sagt_warum_nicht,
              test_keile_am_feinen_rand, test_kragplatte_tet4_gegen_hex8):
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
