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
    hex8, gegen die Balkenloesung;
  * die Betriebsart "sauber" (dritter Auftrag, 24.09.2026): das Feld
    ``sweep = "aus" | "sauber" | "immer"`` (True/False alter Dateien gehen
    weiter), Trapez- gegen Winkelfehler, die Pruefung vor dem Einbau, der
    Kegelstumpf faellt an die Tetraeder und das Protokoll sagt warum, der
    Uebergang zum abgebildeten Nachbarn ueber richtig ausgerichtete Pyramiden.

Aufruf: python -m tests.test_sweep
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from statik3d.model import Model, DofBehaviour, Material, Volumenkoerper   # noqa: E402
from statik3d import mesher, sweep, diagnose, netzguete, solver       # noqa: E402
from statik3d import mesher3d                                        # noqa: E402
from statik3d.elements.solid import solid_volume, hex8_N_dN, pent6_N_dN  # noqa: E402
from test_netzfeld import platte_mit_bohrungen as _platte_roh, zug_und_lager  # noqa: E402


def platte_mit_bohrungen(*a, **kw):
    """Wie in test_netzfeld, aber mit eingeschaltetem Sweep.

    Die Vorgabe `Netzeinstellungen.sweep` ist seit dem 21.09.2026 **aus** -
    am Drehlager entstanden 992 entartete Keile und LF1 rechnete um Faktor
    4,5 daneben. Diese Suite hat den Sweep zum Gegenstand und schaltet ihn
    darum selbst ein; wer den Tetraederweg prueft, laesst ihn aus.
    """
    m, koerper = _platte_roh(*a, **kw)
    m.netz.sweep = True
    return m, koerper

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
    p.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
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
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
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
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
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
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
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
    bl, werk = sweep.zerlegen(m, k)
    schnitte = list(werk.flaechen)
    check("das Zerlegen findet zwei sweepbare Bloecke an einem Schnitt",
          bl is not None and len(bl) == 2 and all(e is not None for _n, e in bl) and len(schnitte) == 1,
          f"{None if bl is None else [(len(n), e is not None) for n, e in bl]}, {len(schnitte)} Schnitt(e)")
    sweep.schnitte_entfernen(m, werk)
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
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
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
    # Die Tetraederzahl mit Pyramiden liegt nicht zwingend unter der ohne:
    # das freie Netz des Nachbarn faellt anders aus, sobald die Randseiten
    # Vierecke bleiben (gemessen 24.09.2026: 332 -> 346 tet4 bei 12 pyr5)
    check("mit Schalter Pyramiden am Uebergang, Rest Tetraeder",
          an["typen"].get("pyr5", 0) > 0 and an["typen"].get("tet4", 0) > 0,
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
    # Seit 23.09.2026 halten die Startpunkte des freien Vernetzers Abstand zur
    # Huelle (mesher3d.RANDABSTAND_FLAECHE): der Tetraederweg hat ohne Randfeld
    # nur noch 7 statt 13 Splitter und Guete 0,086 statt 0,052 - das Randfeld
    # hebt sie auf 0,131 (gemessen; vorher 0,052 -> 0,131, also Faktor 2,5,
    # jetzt 1,5). Die Aussage bleibt: kein Splitter mehr, und die Guete steigt.
    check("dasselbe im Tetraederweg - die Hülle erbt die Splitter sonst ebenso",
          aus_t[2] > 0 and an_t[2] == 0 and an_t[1] > 1.3 * aus_t[1],
          f"{aus_t[2]} → {an_t[2]} unter 0,10, Güte {aus_t[1]:.4f} → {an_t[1]:.4f}")
    check("der Tetraederweg war nie die bessere Wahl: ein Vielfaches an Elementen bei gleicher Groessenordnung der Güte",
          aus_t[1] < 2.0 * aus_s[1] and aus_t[0] > 10 * aus_s[0],
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


def _kegelstumpf(r1=0.05, r2=0.03, l=0.2, h=0.03):
    """Kegelstumpf aus zwei Kreisen und zwei Halbmantelflächen - ein
    **verjüngter Zug**: der Deckel ist die skalierte Kopie des Grundes."""
    m = Model()
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
    m.add_material(Material.steel("S235"))
    u = _kreis(m, "CU", 0.0, 0.0, 0.0, r1)
    o = _kreis(m, "CO", 0.0, 0.0, l, r2)
    m.add_line("CV1", [u[0], o[0]])
    m.add_line("CV2", [u[1], o[1]])
    m.add_flaeche("CM1", [u[2], "CV2", o[2], "CV1"], material="S235")
    m.add_flaeche("CM2", [u[3], "CV1", o[3], "CV2"], material="S235")
    m.add_flaeche("CBoden", [u[2], u[3]], material="S235")
    m.add_flaeche("CDeckel", [o[2], o[3]], material="S235")
    k = m.add_koerper("Kegel", ["CBoden", "CDeckel", "CM1", "CM2"], material="S235")
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    return m, k


def test_verjuengter_zug():
    """Stufe 2 des Nachtrags vom 22.09.2026: die Erkennung verlangte eine
    **reine Verschiebung**; ein Kegelstumpf, eine konische Rippe, eine Nabe mit
    Anzug fielen darum an die Tetraeder. Jetzt genügt eine Ähnlichkeit - der
    Deckel ist die skalierte, verschobene Kopie des Grundes, und die Lagen
    führen den Maßstab linear mit."""
    for r1, r2, name in ((0.05, 0.03, "verjüngt"), (0.05, 0.05, "zylindrisch"),
                         (0.03, 0.06, "geweitet")):
        m, k = _kegelstumpf(r1, r2)
        check(f"{name} (r {r1 * 1e3:.0f} → {r2 * 1e3:.0f} mm): sweepbar", sweep.sweepbar(m, k))
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
        typen = _typen(m)
        check(f"{name}: nur Hexaeder und Keile", set(typen) <= {"hex8", "pent6"} and typen, str(typen))
        check(f"{name}: kein Element ist umgestülpt", _negativ(m) == 0)
        V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
        V_soll = np.pi * 0.2 / 3.0 * (r1 ** 2 + r2 ** 2 + r1 * r2)
        check(f"{name}: Rauminhalt ist der des Kegelstumpfs (Kreise als Vielecke)",
              0.97 * V_soll <= V <= V_soll, f"{V * 1e6:.0f} von {V_soll * 1e6:.0f} cm³ ({V / V_soll * 100:.1f} %)")
        bef = diagnose.abnahme(m)
        check(f"{name}: Abnahme ohne Befund", not bef, str([b.pruefung for b in bef])[:100])
    # Die Abbildung selbst: Verschiebung ist der Sonderfall k = 1
    m, k = _kegelstumpf(0.05, 0.03)
    erk = sweep.erkennen(m, k)
    art, c, k_ab, t = sweep.abbildung_von(erk)
    check("die Abbildung ist eine Ähnlichkeit und nennt den Maßstab",
          art == "v" and abs(k_ab - 0.6) < 0.02, f"{art}, k = {k_ab:.4f} (Soll 0,600)")
    check("und die Verschiebung längs der Achse", abs(float(t[2]) - 0.2) < 1e-9 and
          abs(float(np.linalg.norm(t[:2]))) < 1e-9, f"t = {np.round(t, 4)}")
    P = np.array([[0.05, 0.0, 0.0], [0.0, 0.05, 0.0]])
    check("die halbe Lage liegt auf halbem Maßstab",
          np.allclose(sweep._abbilden(P, ("v", c, k_ab, t), 0.5),
                      c + (P - c) * (1 + (k_ab - 1) * 0.5) + t * 0.5),
          "linear in s")
    m2, k2 = platte_mit_bohrungen(0.4, 0.3, 0.1, bohrungen=((0.2, 0.15, 0.03),))
    erk2 = sweep.erkennen(m2, k2)
    check("eine Platte bleibt eine reine Verschiebung (k = 1)",
          abs(sweep.massstab_von(sweep.abbildung_von(erk2)) - 1.0) < 1e-9,
          f"k = {sweep.massstab_von(sweep.abbildung_von(erk2)):.6f}")


def _ringsegment(r1=0.10, r2=0.15, hoehe=0.05, winkel=np.pi / 2, h=0.02):
    """Ringsegment: ein Rechteckprofil, um die z-Achse gedreht - ein
    **Drehkörper** (Rohrbogen, Ringsegment). Die Mantellinien sind Bögen."""
    m = Model()
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
    m.add_material(Material.steel("S235"))

    def dreh(p, w):
        return (p[0] * np.cos(w) - p[1] * np.sin(w), p[0] * np.sin(w) + p[1] * np.cos(w), p[2])
    prof = [(r1, 0.0, 0.0), (r2, 0.0, 0.0), (r2, 0.0, hoehe), (r1, 0.0, hoehe)]
    A = [m.add_node(*p) for p in prof]
    B = [m.add_node(*dreh(p, winkel)) for p in prof]
    for i in range(4):
        j = (i + 1) % 4
        m.add_line(f"GA{i}", [A[i], A[j]])
        m.add_line(f"GB{i}", [B[i], B[j]])
        m.add_line(f"MA{i}", [A[i], B[i]], "arc",
                   punkte=[prof[i], dreh(prof[i], winkel / 2.0), dreh(prof[i], winkel)])
    m.add_flaeche("KA", [f"GA{i}" for i in range(4)], material="S235")
    m.add_flaeche("KB", [f"GB{i}" for i in range(4)], material="S235")
    namen = []
    for i in range(4):
        m.add_flaeche(f"W{i}", [f"GA{i}", f"MA{(i + 1) % 4}", f"GB{i}", f"MA{i}"], material="S235")
        namen.append(f"W{i}")
    k = m.add_koerper("Bogen", ["KA", "KB"] + namen, material="S235")
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    return m, k


def test_drehkoerper():
    """Stufe 2 des Nachtrags vom 22.09.2026, zweiter Fall: der **Drehkörper**.
    Grund und Deckel sind eben, aber nicht parallel - sie stehen um denselben
    Winkel gegeneinander wie der Körper. Beide Kappenebenen enthalten die
    Achse, daraus folgt sie; die Lagen werden um den Anteil des Winkels
    gedreht und liegen damit auf dem Bogen, nicht auf der Sehne."""
    for grad in (90, 45):
        m, k = _ringsegment(winkel=np.radians(grad))
        erk = sweep.erkennen(m, k)
        check(f"{grad}°: als Drehkörper erkannt", erk is not None and sweep.abbildung_von(erk)[0] == "d",
              "-" if erk is None else str(sweep.abbildung_von(erk)[0]))
        if erk is None:
            continue
        _tag, a, d, phi = sweep.abbildung_von(erk)
        check(f"{grad}°: die Achse ist die z-Achse", abs(abs(float(d[2])) - 1.0) < 1e-9
              and float(np.linalg.norm(a[:2])) < 1e-9, f"d = {np.round(d, 3)}, a = {np.round(a, 4)}")
        check(f"{grad}°: der Winkel stimmt", abs(abs(np.degrees(phi)) - grad) < 0.5,
              f"{np.degrees(phi):.2f}°")
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
        typen = _typen(m)
        check(f"{grad}°: nur Hexaeder und Keile", set(typen) <= {"hex8", "pent6"} and typen, str(typen))
        check(f"{grad}°: kein Element ist umgestülpt", _negativ(m) == 0)
        V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
        V_soll = np.radians(grad) / 2.0 * (0.15 ** 2 - 0.10 ** 2) * 0.05
        check(f"{grad}°: Rauminhalt nach Guldin (Grundfläche mal Weg des Schwerpunkts)",
              0.98 * V_soll <= V <= V_soll, f"{V * 1e6:.1f} von {V_soll * 1e6:.1f} cm³ ({V / V_soll * 100:.1f} %)")
        q = netzguete.guete(m)
        q = q[np.isfinite(q)]
        check(f"{grad}°: Formgüte über 0,3", float(q.min()) > 0.3, f"min {q.min():.3f}")
        bef = diagnose.abnahme(m)
        check(f"{grad}°: Abnahme ohne Befund", not bef, str([b.pruefung for b in bef])[:100])
    # Die Lagen liegen auf dem Bogen, nicht auf der Sehne
    m, k = _ringsegment(winkel=np.pi / 2)
    abb = sweep.abbildung_von(sweep.erkennen(m, k))
    P = np.array([[0.125, 0.0, 0.0]])
    halb = sweep._abbilden(P, abb, 0.5)[0]
    check("die halbe Lage liegt auf dem Bogen (r bleibt 125 mm)",
          abs(float(np.linalg.norm(halb[:2])) - 0.125) < 1e-9,
          f"r = {np.linalg.norm(halb[:2]) * 1e3:.4f} mm, Punkt {np.round(halb, 4)}")
    check("und auf halbem Winkel", abs(np.degrees(np.arctan2(halb[1], halb[0])) - 45.0) < 1e-9,
          f"{np.degrees(np.arctan2(halb[1], halb[0])):.4f}°")


def test_krummer_quader_nicht_abgebildet():
    """Ein Sechsflächner mit acht Ecken, aber **krummen** Kanten darf nicht in
    den abgebildeten Quaderpfad: die trilineare Abbildung schneidet jede
    Rundung ab. Der 90°-Rohrbogen kam so auf 63,7 % seines Rauminhalts - ohne
    eine Meldung, weil Hülle und Güte tadellos aussehen (22.09.2026)."""
    m, k = _ringsegment(winkel=np.pi / 2)
    ringe = [m.flaechen[x].randknoten(m) for x in k.flaechen]
    knoten = {n for r in ringe for n in r}
    check("er sieht aus wie ein Quader: sechs Vierecke, acht Ecken",
          len(k.flaechen) == 6 and len(knoten) == 8 and all(len(r) == 4 for r in ringe),
          f"{len(k.flaechen)} Flächen, {len(knoten)} Ecken")
    from statik3d.importers.rfem6_db import _hex_order
    order = _hex_order(ringe)
    check("und die Quader-Knotenfolge ließe sich sogar bilden", bool(order))
    check("aber seine Kanten sind krumm - der Quaderpfad greift nicht",
          not mesher._gerade_kanten(m, k, order))
    log = []
    els = mesher.mesh_koerper(m, k, log=log, h=0.02)
    typen = {m.elements[e].typ for e in els}
    check("darum wird er gesweept statt abgebildet", typen <= {"hex8", "pent6"} and typen,
          str(sorted(typen)))
    check("und das Protokoll sagt, warum", any("krumme Kanten" in z for z in log),
          str([z[:110] for z in log if "krumme" in z])[:140])
    V = sum(solid_volume(m.elements[e].typ, m.nodes[m.elements[e].nodes]) for e in els)
    V_soll = np.pi / 4.0 * (0.15 ** 2 - 0.10 ** 2) * 0.05
    check("der Rauminhalt stimmt jetzt (vorher 63,7 %)", V / V_soll > 0.98,
          f"{V * 1e6:.1f} von {V_soll * 1e6:.1f} cm³ ({V / V_soll * 100:.1f} %)")
    # Ein gerader Quader bleibt abgebildet
    m2, k2 = quader()
    ringe2 = [m2.flaechen[x].randknoten(m2) for x in k2.flaechen]
    order2 = _hex_order(ringe2)
    check("ein gerader Quader behält den abgebildeten Pfad",
          bool(order2) and mesher._gerade_kanten(m2, k2, order2))


def _platte_mit_randrippe(a=0.2, b=0.1, t=0.02, x0=0.05, by=0.02, hr=0.06, h=0.025):
    """Platte a x b x t, darauf eine Rippe von x0 bis an den **Rand** x = a.

    Der Fussabdruck der Rippe beruehrt den Aussenrand der Deckflaeche - sie
    haengt also nicht ueber einer Oeffnung, und genau das schliesst
    ``_fussabdruecke`` aus. Nur der Ebenenschnitt trennt sie.
    """
    m = Model()
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
    m.add_material(Material.steel("S235"))
    y1, y2 = (b - by) / 2.0, (b + by) / 2.0
    N, L = {}, {}

    def kn(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in N:
            N[key] = m.add_node(x, y, z)
        return N[key]

    def li(p_, q_):
        key = (p_, q_) if p_ < q_ else (q_, p_)
        if key not in L:
            L[key] = f"L{len(L) + 1}"
            m.add_line(L[key], [key[0], key[1]])
        return L[key]

    def fl(name, punkte):
        ks = [kn(*pp) for pp in punkte]
        m.add_flaeche(name, [li(ks[i], ks[(i + 1) % len(ks)]) for i in range(len(ks))],
                      material="S235")
        return name
    namen = [
        fl("Boden", [(0, 0, 0), (a, 0, 0), (a, b, 0), (0, b, 0)]),
        fl("X0", [(0, 0, 0), (0, b, 0), (0, b, t), (0, 0, t)]),
        fl("Y0", [(0, 0, 0), (a, 0, 0), (a, 0, t), (0, 0, t)]),
        fl("Y1", [(0, b, 0), (a, b, 0), (a, b, t), (0, b, t)]),
        # x = a: Platte plus Rippenstirn - T-foermig, die Ebene z = t teilt sie
        fl("XA", [(a, 0, 0), (a, b, 0), (a, b, t), (a, y2, t), (a, y2, t + hr),
                  (a, y1, t + hr), (a, y1, t), (a, 0, t)]),
        # Deckflaeche der Platte, am Rand x = a eingekerbt
        fl("Deckel", [(0, 0, t), (a, 0, t), (a, y1, t), (x0, y1, t), (x0, y2, t),
                      (a, y2, t), (a, b, t), (0, b, t)]),
        fl("RY1", [(x0, y1, t), (a, y1, t), (a, y1, t + hr), (x0, y1, t + hr)]),
        fl("RY2", [(x0, y2, t), (a, y2, t), (a, y2, t + hr), (x0, y2, t + hr)]),
        fl("RX0", [(x0, y1, t), (x0, y2, t), (x0, y2, t + hr), (x0, y1, t + hr)]),
        fl("RDeckel", [(x0, y1, t + hr), (a, y1, t + hr), (a, y2, t + hr), (x0, y2, t + hr)]),
    ]
    k = m.add_koerper("V1", namen, material="S235")
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    return m, k


def test_rippe_am_rand_ueber_ebene_zerlegt():
    """Zerlegen an einer **Ebene**: die Rippe laeuft bis an den Rand, ihr
    Fussabdruck ist keine Oeffnung. Geschnitten wird an der Ebene der
    Deckflaeche; beide Bloecke werden gesweept (22.09.2026)."""
    m, k = _platte_mit_randrippe()
    check("als Ganzes nicht sweepbar", sweep.erkennen(m, k) is None)
    check("kein Fussabdruck: keine Randflaeche hat eine Oeffnung",
          not any(m.flaechen[x].oeffnungen for x in k.flaechen))
    ebenen = sweep.schnittebenen(m, k, 1e-7)
    check("vier Randflaechen-Ebenen trennen den Koerper", len(ebenen) == 4, f"{len(ebenen)}")
    bl, werk = sweep.zerlegen(m, k)
    check("der Ebenenschnitt findet zwei Bloecke, **beide** sweepbar",
          bl is not None and len(bl) == 2 and all(e is not None for _n, e in bl),
          f"{None if bl is None else [(len(n), e is not None) for n, e in bl]}")
    sweep.schnitte_entfernen(m, werk)
    check("die Hilfsgeometrie ist danach wieder aus dem Modell",
          not any("§" in x for x in m.flaechen) and not any("§" in x for x in m.lines)
          and m.nn == 16, f"{m.nn} Knoten")
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("nur Hexaeder und Keile, kein Tetraeder", set(typen) <= {"hex8", "pent6"} and typen,
          str(typen))
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = 0.2 * 0.1 * 0.02 + 0.15 * 0.02 * 0.06
    check("Rauminhalt Platte + Rippe", abs(V / V_soll - 1.0) < 1e-6,
          f"{V * 1e6:.1f} von {V_soll * 1e6:.1f} cm³ ({V / V_soll * 100:.2f} %)")
    ebene = [n for n in range(m.nn) if abs(m.nodes[n][2] - 0.02) < 1e-9]
    check("knotenkonform in der Schnittebene", _doppelte_knoten(m, ebene) == 0,
          f"{len(ebene)} Knoten in der Ebene")
    check("das Protokoll nennt den Ebenenschnitt",
          any("an einer Ebene" in z for z in log), str([z[:90] for z in log if "Ebene" in z])[:120])
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([(b.pruefung, b.text[:40]) for b in bef])[:160])
    # Die Last muss durch beide Bloecke ins Lager: die Stirnflaeche XA ist
    # geschnitten (Rippe oben, Platte unten, deren Wand noch dreigeteilt), der
    # Boden ist durch das Angleichen ersetzt, der Deckel liegt in der Ebene.
    for flaeche, A in (("XA", 0.1 * 0.02 + 0.02 * 0.06), ("Boden", 0.2 * 0.1),
                       ("Deckel", 0.2 * 0.1 - 0.15 * 0.02)):
        mm, _kk = _platte_mit_randrippe()
        mm.add_load_case("LF1")
        mm.case("LF1").gravity = [0.0, 0.0, 0.0]
        mm.add_geometrielast(flaeche, 1e6, "flaeche", richtung=[0.0, 0.0, -1.0], case="LF1")
        ss = mm.add_surface_support(name="E")
        ss.flaechen = ["X0"]
        for d in (0, 1, 2):
            ss.behaviour[d] = DofBehaviour("rigid")
        mm.active_case = "LF1"
        mesher.modell_vernetzen(mm, [], workers=1)
        r = solver.solve_static(mm, case="LF1", workers=1)
        R = abs(float(r.reactions[:, 2].sum()))
        check(f"die Last auf {flaeche} kommt ganz im Lager an",
              abs(R - 1e6 * A) < 1e-6 * 1e6 * A, f"{R / 1e3:.3f} kN gegen {1e6 * A / 1e3:.3f} kN")
    # Das Erfolgsmass: dieselbe Last, weniger Knoten, groessere Verschiebung
    def rechnen(sweep_an, hh):
        mm, _kk = _platte_mit_randrippe(h=hh)
        mm.add_load_case("LF1")
        mm.case("LF1").gravity = [0.0, 0.0, 0.0]
        mm.add_geometrielast("XA", 10e3 / (0.1 * 0.02), "flaeche",
                             richtung=[0.0, 0.0, -1.0], case="LF1")
        ss = mm.add_surface_support(name="E")
        ss.flaechen = ["X0"]
        for d in (0, 1, 2):
            ss.behaviour[d] = DofBehaviour("rigid")
        mm.netz.sweep = sweep_an
        mm.active_case = "LF1"
        mesher.modell_vernetzen(mm, [], workers=1)
        r = solver.solve_static(mm, case="LF1", workers=1)
        return float(np.abs(r.u[:, 2]).max()), int(mm.nn), len(mm.elements)
    w_tet, nn_tet, ne_tet = rechnen(False, 0.025)
    w_hex, nn_hex, ne_hex = rechnen(True, 0.025)
    print(f"    tet4: {w_tet * 1e3:.4f} mm ({ne_tet} Elemente, {nn_tet} Knoten) | "
          f"zerlegt+gesweept: {w_hex * 1e3:.4f} mm ({ne_hex} Elemente, {nn_hex} Knoten)")
    # Zum Vergleich gemessen (22.09.2026): der Tetraeder braucht h = 6 mm,
    # 39 891 Elemente und 7 459 Knoten fuer 1,9674 mm - der gesweepte Block
    # steht mit 124 Elementen und 239 Knoten bei 2,0161 mm schon darueber.
    # Der tet4-Wert hing an den Splittern des groben Netzes: mit 0,5811 mm war
    # er dreimal zu steif; seit die Kappenpunkte Abstand zur Huelle halten
    # (mesher3d.KAPPEN_RANDABSTAND, 23.09.2026) sind es 1,1397 mm - immer noch
    # 1,8-mal zu steif gegen 2,0254 mm.
    check("der lineare Tetraeder ist hier deutlich zu steif (gemessen 1,8-mal)", w_hex > 1.5 * w_tet,
          f"{w_hex * 1e3:.4f} mm gegen {w_tet * 1e3:.4f} mm")
    # (tet4 685 Elemente am 22.09., 471 seit den Kippungen und Kappenregeln
    # vom 24.09.2026 - der freie Vernetzer braucht weniger, die Schranke ist
    # darum ein Drittel statt ein Viertel)
    check("und das mit weniger Elementen (hoechstens ein Drittel)", ne_hex < 0.35 * ne_tet, f"{ne_hex} gegen {ne_tet}")


def _quader_mit_geteilter_kante(a=0.3, b=0.2, t=0.1, h=0.05):
    """Ein Quader, dessen Deckel eine Kante in **zwei** Linien fuehrt - so
    kommt er aus einem Modell, in dem dort ein Nachbar anstoesst."""
    m = Model()
    m.netz.sweep = True          # Vorgabe seit 21.09.2026 aus - hier ist der Sweep der Gegenstand
    m.add_material(Material.steel("S235"))
    N, L = {}, {}

    def kn(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in N:
            N[key] = m.add_node(x, y, z)
        return N[key]

    def li(p_, q_):
        key = (p_, q_) if p_ < q_ else (q_, p_)
        if key not in L:
            L[key] = f"L{len(L) + 1}"
            m.add_line(L[key], [key[0], key[1]])
        return L[key]

    def fl(name, punkte):
        ks = [kn(*pp) for pp in punkte]
        m.add_flaeche(name, [li(ks[i], ks[(i + 1) % len(ks)]) for i in range(len(ks))],
                      material="S235")
        return name
    namen = [
        fl("U", [(0, 0, 0), (a, 0, 0), (a, b, 0), (0, b, 0)]),
        fl("O", [(0, 0, t), (a, 0, t), (a, b, t), (a / 2, b, t), (0, b, t)]),
        fl("X0", [(0, 0, 0), (0, b, 0), (0, b, t), (0, 0, t)]),
        fl("XA", [(a, 0, 0), (a, 0, t), (a, b, t), (a, b, 0)]),
        fl("Y0", [(0, 0, 0), (0, 0, t), (a, 0, t), (a, 0, 0)]),
        fl("YB", [(0, b, 0), (a, b, 0), (a, b, t), (a / 2, b, t), (0, b, t)]),
    ]
    k = m.add_koerper("V1", namen, material="S235")
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    return m, k


def test_kappen_verschieden_geteilt():
    """Grund und Deckel duerfen ihren Rand **verschieden** in Linien teilen.

    Erst wird die Figur gemessen, nicht die Ecken (Flaechenschwerpunkt und
    Abstand zur Kurve), dann werden die Linien angeglichen: die fehlende Ecke
    wird auf die andere Schleife abgebildet, deren Linie dort geteilt und die
    Wand dazwischen mit (22.09.2026)."""
    P = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    Q = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0],
                  [0.5, 1.0, 0.0], [0.0, 1.0, 0.0]])       # eine Ecke mehr, dieselbe Figur
    check("der Mittelwert der Ecken wandert mit einer zusaetzlichen Ecke",
          float(np.linalg.norm(P.mean(axis=0) - Q.mean(axis=0))) > 0.04,
          f"{np.linalg.norm(P.mean(axis=0) - Q.mean(axis=0)):.4f} m")
    check("der Flaechenschwerpunkt bleibt, wo er ist",
          float(np.linalg.norm(sweep._umringmitte(P) - sweep._umringmitte(Q))) < 1e-12)
    eins = ("v", np.zeros(3), 1.0, np.zeros(3))
    check("und die Umringe gelten als deckungsgleich", sweep._deckungsgleich_abb(P, Q, eins, 1e-9))
    m, k = _quader_mit_geteilter_kante()
    check("so erkannt wird der Quader trotzdem nicht - die Wand hat fuenf Linien",
          sweep.erkennen(m, k) is None
          and "nicht aus vier Linien" in sweep.erkennen_warum_nicht(m, k),
          sweep.erkennen_warum_nicht(m, k)[:110])
    werk = sweep.Schnittwerk(m)
    namen = sweep.kappenlinien_angleichen(m, list(k.flaechen), werk, 1e-9)
    check("das Angleichen liefert eine Flaechenliste mit einer Wand mehr",
          namen is not None and len(namen) == 7, "-" if namen is None else str(len(namen)))
    pseudo = Volumenkoerper("V1", list(namen or []), material="S235", teilung=[4, 4, 4])
    check("und dann ist er sweepbar", sweep.erkennen(m, pseudo) is not None)
    werk.zuruecknehmen()
    check("zuruecknehmen laesst nichts stehen",
          not any("§" in x for x in m.flaechen) and not any("§" in x for x in m.lines)
          and m.nn == 9, f"{m.nn} Knoten")
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("vernetzt gibt das Hexaeder und Keile, keinen Tetraeder",
          set(typen) <= {"hex8", "pent6"} and typen, str(typen))
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    check("Rauminhalt stimmt", abs(V / (0.3 * 0.2 * 0.1) - 1.0) < 1e-9,
          f"{V * 1e3:.4f} von {0.3 * 0.2 * 0.1 * 1e3:.4f} dm³")
    check("kein Element ist umgestuelpt", _negativ(m) == 0)
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([b.pruefung for b in bef])[:120])


def _nachbar_darunter(m, a=0.3, b=0.2, t=0.1):
    """Ein zweiter Quader unter dem ersten - er **teilt sich die Grundflaeche**
    ``U`` mit ihm. Ihre Linien gehoeren damit auch ihm."""
    def kn(x, y, z):
        for i in range(m.nn):
            if abs(m.nodes[i][0] - x) < 1e-12 and abs(m.nodes[i][1] - y) < 1e-12 \
                    and abs(m.nodes[i][2] - z) < 1e-12:
                return i
        return m.add_node(x, y, z)

    def li(p_, q_):
        for name, ln in m.lines.items():
            if len(ln.nodes) == 2 and {int(ln.nodes[0]), int(ln.nodes[1])} == {p_, q_}:
                return name
        name = f"NL{len(m.lines) + 1}"
        m.add_line(name, [p_, q_])
        return name

    def fl(name, punkte):
        ks = [kn(*pp) for pp in punkte]
        m.add_flaeche(name, [li(ks[i], ks[(i + 1) % len(ks)]) for i in range(len(ks))],
                      material="S235")
        return name
    namen = ["U",
             fl("NU", [(0, 0, -t), (a, 0, -t), (a, b, -t), (0, b, -t)]),
             fl("NX0", [(0, 0, -t), (0, b, -t), (0, b, 0), (0, 0, 0)]),
             fl("NXA", [(a, 0, -t), (a, 0, 0), (a, b, 0), (a, b, -t)]),
             fl("NY0", [(0, 0, -t), (0, 0, 0), (a, 0, 0), (a, 0, -t)]),
             fl("NYB", [(0, b, -t), (a, b, -t), (a, b, 0), (0, b, 0)])]
    return m.add_koerper("V2", namen, material="S235")


def test_angleichen_schont_den_nachbarn():
    """Eine Linie, die ein **zweiter Koerper** fuehrt, wird nicht geteilt -
    sein Netz kennt die Stuecke nicht, und die Fuge risse auf. Der Weg wird
    dann anderswo gesucht (22.09.2026)."""
    m, k = _quader_mit_geteilter_kante()
    werk = sweep.Schnittwerk(m)
    allein = sweep.kappenlinien_angleichen(m, list(k.flaechen), werk, 1e-9)
    check("allein geht das Angleichen ueber die Grundflaeche U",
          allein is not None and "U" not in allein, str(allein))
    werk.zuruecknehmen()
    m, k = _quader_mit_geteilter_kante()
    k2 = _nachbar_darunter(m)
    fremd = sweep._fremde_flaechen(m, k)
    check("die Grundflaeche gehoert jetzt auch dem Nachbarn", "U" in fremd, str(sorted(fremd)))
    werk = sweep.Schnittwerk(m)
    mit = sweep.kappenlinien_angleichen(m, list(k.flaechen), werk, 1e-9, fremd)
    check("mit Nachbar bleibt U unangetastet - angeglichen wird quer dazu",
          mit is not None and "U" in mit, str(mit))
    werk.zuruecknehmen()
    check("beide Koerper sind sweepbar", sweep.sweepbar(m, k) and sweep.sweepbar(m, k2))
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("und das Netz ist reiner Hexaeder", set(typen) == {"hex8"}, str(typen))
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    check("Rauminhalt beider Quader", abs(V / (2 * 0.3 * 0.2 * 0.1) - 1.0) < 1e-9,
          f"{V * 1e3:.4f} dm³")
    fuge = [n for n in range(m.nn) if abs(m.nodes[n][2]) < 1e-12]
    check("knotenkonform in der Fuge", _doppelte_knoten(m, fuge) == 0, f"{len(fuge)} Knoten")
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([b.pruefung for b in bef])[:120])


def _gestapelter_zylinder(r=0.02, h1=0.03, h2=0.05, hh=0.01):
    """Zylinder, dessen Mantel an z = h1 in **zwei Ringe** geteilt ist - wie
    V61 am Drehlager: an der Zwischenkreislinie liegt ein Nachbar an, eine
    Flaeche gibt es dort nicht. Die Kappen passen, aber je Randlinie stehen
    zwei Waende uebereinander (23 der 40 nicht sweepbaren Drehlagerkoerper,
    23.09.2026)."""
    m = Model()
    m.add_material(Material.steel("S235"))

    def kreis(z, tag):
        a = m.add_node(-r, 0, z)
        b = m.add_node(r, 0, z)
        m.add_line(f"{tag}1", [a, b], "arc", punkte=[(-r, 0, z), (0, r, z), (r, 0, z)])
        m.add_line(f"{tag}2", [b, a], "arc", punkte=[(r, 0, z), (0, -r, z), (-r, 0, z)])
        return a, b
    au, bu = kreis(0.0, "U")
    am, bm = kreis(h1, "M")
    ao, bo = kreis(h1 + h2, "O")
    m.add_line("S1", [au, am])
    m.add_line("S2", [bu, bm])
    m.add_line("S3", [am, ao])
    m.add_line("S4", [bm, bo])
    m.add_flaeche("KU", ["U1", "U2"], material="S235")
    m.add_flaeche("KO", ["O1", "O2"], material="S235")
    m.add_flaeche("W1", ["U1", "S2", "M1", "S1"], material="S235")
    m.add_flaeche("W2", ["U2", "S1", "M2", "S2"], material="S235")
    m.add_flaeche("W3", ["M1", "S4", "O1", "S3"], material="S235")
    m.add_flaeche("W4", ["M2", "S3", "O2", "S4"], material="S235")
    k = m.add_koerper("Z", ["KU", "KO", "W1", "W2", "W3", "W4"], material="S235")
    m.netz.ziellaenge = hh
    m.netz.dichte = "eigene"
    m.netz.sweep = True
    return m, k


def test_zerlegen_an_vorhandener_schleife():
    """Der gestapelte Zylinder: als Ganzes nicht sweepbar (zwei Waende je
    Randlinie), aber an der Zwischenkreislinie teilbar - die Schnittflaeche
    besteht aus vorhandenen Linien, keine Flaeche wird geschnitten."""
    import time
    m, k = _gestapelter_zylinder()
    check("als Ganzes nicht sweepbar - zwei Waende je Randlinie",
          sweep.erkennen(m, k) is None and "4 Wandflächen zu 2 Randlinien" in sweep.erkennen_warum_nicht(m, k),
          sweep.erkennen_warum_nicht(m, k)[:100])
    t0 = time.time()
    bl, werk = sweep.zerlegen(m, k)
    dt = time.time() - t0
    check("an der vorhandenen Schleife in zwei sweepbare Bloecke zerlegt, in unter einer Sekunde",
          bl is not None and len(bl) == 2 and all(e is not None for _n, e in bl) and dt < 1.0
          and getattr(werk, "art", "") == "an einer vorhandenen Schleife",
          f"{None if bl is None else [(len(n), e is not None) for n, e in bl]}, {dt:.2f} s, {getattr(werk, 'art', '')}")
    check("eine Schnittflaeche aus den beiden Boegen der Zwischenkreislinie",
          len(werk.flaechen) == 1 and sorted(m.flaechen[werk.flaechen[0]].linien) == ["M1", "M2"]
          and not werk.linien and m.nn == 6, str([m.flaechen[x].linien for x in werk.flaechen]))
    sweep.schnitte_entfernen(m, werk)
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("vernetzt: nur Hexaeder", set(typen) == {"hex8"} and typen, str(typen))
    V = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    V_soll = np.pi * 0.02 ** 2 * 0.08
    check("Rauminhalt (Kreis als Vieleck)", 0.98 * V_soll <= V <= V_soll, f"{V / V_soll * 100:.1f} %")
    check("die Zwischenkreislinie ist eine Lagengrenze - knotenkonform, keine doppelten Knoten",
          _doppelte_knoten(m, [n for n in range(m.nn) if abs(m.nodes[n][2] - 0.03) < 1e-9]) == 0)
    check("das Protokoll nennt die Schleife", any("vorhandenen Schleife" in z for z in log),
          str([z[:90] for z in log if "zerlegt" in z])[:120])
    check("Abnahme ohne Befund", not diagnose.abnahme(m))


def test_zerlegen_namen_und_budget():
    """Zwei Fehler vom Drehlager (23.09.2026): der Fussabdruck hiess nach der
    Zahl der Schnitte und bekam nach einem verworfenen Versuch denselben
    Namen wieder (KeyError 'V30§2'); und die Fussabdrucksuche probierte an
    V30 255 s lang durch. Jetzt zaehlt Schnittwerk.marke durch, und ein
    Budget begrenzt Zeit und Versuche."""
    m, k = _platte_mit_nabe()
    werk = sweep.Schnittwerk(m)
    namen = [werk.marke(k) for _ in range(3)]
    werk.zurueck_bis(werk.stand())
    check("die Marke vergibt keinen Namen zweimal, auch nach dem Zuruecknehmen nicht",
          len(set(namen)) == 3 and werk.marke(k) not in namen, str(namen + [werk.marke(k)]))
    alt = (sweep.ZERLEGEN_ZEIT_S, sweep.ZERLEGEN_VERSUCHE)
    sweep.ZERLEGEN_ZEIT_S, sweep.ZERLEGEN_VERSUCHE = 1e9, 0
    try:
        m2, k2 = _platte_mit_nabe()
        bl, werk2 = sweep.zerlegen(m2, k2)
        sweep.schnitte_entfernen(m2, werk2)
        grund = sweep.zerlegen_warum_nicht(m2, k2)
    finally:
        sweep.ZERLEGEN_ZEIT_S, sweep.ZERLEGEN_VERSUCHE = alt
    check("ohne Budget wird nichts zerlegt, und das Protokoll nennt den Abbruch",
          bl is None and "abgebrochen" in grund, f"{bl} | {grund[:120]}")
    m3, k3 = _platte_mit_nabe()
    bl3, werk3 = sweep.zerlegen(m3, k3)
    sweep.schnitte_entfernen(m3, werk3)
    check("mit Budget wird die Platte mit Nabe wie zuvor zerlegt", bl3 is not None and len(bl3) == 2)
    check("zerlegbar() merkt sich die Antwort am Modell",
          sweep.zerlegbar(m3, k3) and (k3.name, tuple(k3.flaechen), m3.nn) in getattr(m3, "_zerlegbar_cache", {}))


def test_umpaaren_spart_keile():
    """Ein Keil ist kein halber Sechsflächner: der hex8 trägt Biegung über
    inkompatible Moden, der pent6 nicht (Statik3D-Sitzung, 22.09.2026: am
    identischen Gitter 95,9 % gegen 56,4 % der Balkenlösung). Jedes Dreieck
    ohne Partner kostet also.

    Die gierige Paarung lässt Dreiecke stehen, deren Nachbarn schon vergeben
    sind - und zwar **nicht** wegen der Gütegrenze: sie von 0,3 auf 10⁻⁶ zu
    senken ändert keine einzige Zahl. Erst das Umpaaren (erweiternder Weg der
    Länge drei) holt sie."""
    from statik3d.sweep import _viereckguete

    def nur_gierig(P2, T, guete_min=sweep.VIERECK_GUETE_MIN):
        """Die Paarung ohne den zweiten Schritt - der Stand vor dem 22.09.2026."""
        T = np.asarray(T, int)
        kante = {}
        for k, (a, b, c) in enumerate(T):
            for x, y in ((a, b), (b, c), (c, a)):
                kante.setdefault((min(x, y), max(x, y)), []).append(k)
        kand = []
        for (x, y), ks in kante.items():
            if len(ks) != 2:
                continue
            k1, k2 = ks
            t1 = [int(v) for v in T[k1]]
            t2 = [int(v) for v in T[k2]]
            s1 = [v for v in t1 if v not in (x, y)][0]
            s2 = [v for v in t2 if v not in (x, y)][0]
            i1 = t1.index(s1)
            i, j = t1[(i1 + 1) % 3], t1[(i1 + 2) % 3]
            kand.append((k1, k2, (s1, i, s2, j)))
        if not kand:
            return 0, len(T)
        q = _viereckguete(P2[np.array([v for _, _, v in kand], int)])
        benutzt = np.zeros(len(T), bool)
        n = 0
        for r in np.argsort(-q, kind="stable"):
            if q[r] < guete_min:
                break
            k1, k2, _v = kand[r]
            if benutzt[k1] or benutzt[k2]:
                continue
            benutzt[k1] = benutzt[k2] = True
            n += 1
        return n, int((~benutzt).sum())

    # Das Grundflächennetz der Kragplatte, wie der Sweep es sieht
    m, k = platte_mit_bohrungen(1.0, 0.2, 0.05, bohrungen=((0.95, 0.1, 0.01),))
    m.netz.ziellaenge = 0.025
    m.netz.dichte = "eigene"
    erk = sweep.erkennen(m, k)
    h = mesher3d._kantenlaenge(m, k, 0.025)
    hf, hl = mesher3d.kantenlaengen_karte(m, h=h)
    gem = mesher3d.gemeinsame_randflaechen(m)
    teilung = mesher3d.Linienteilung(m, [m.flaechen[x] for x in k.flaechen], h, hl, hf, gem)
    P, T, meldung, grob, _kenn = mesher3d.flaechennetz(m, erk["grund"], teilung)
    P = np.asarray(P, float)
    T = np.asarray(T, int)
    c, e1, e2, n, _abw = mesher3d.ausgleichsebene(P)
    P2 = np.stack([(P - c) @ e1, (P - c) @ e2], axis=1)
    a_, b_, d_ = P2[T[:, 0]], P2[T[:, 1]], P2[T[:, 2]]
    fl = (b_[:, 0] - a_[:, 0]) * (d_[:, 1] - a_[:, 1]) - (d_[:, 0] - a_[:, 0]) * (b_[:, 1] - a_[:, 1])
    T = np.where((fl < 0)[:, None], T[:, [0, 2, 1]], T)
    n_gierig, rest_gierig = nur_gierig(P2, T)
    V, D = sweep.paaren(P2, T)
    check("das Umpaaren lässt weniger Dreiecke übrig als die reine Gier",
          len(D) < rest_gierig, f"{rest_gierig} → {len(D)} Dreiecke von {len(T)}")
    check("und es entstehen entsprechend mehr Vierecke",
          len(V) > n_gierig and 2 * len(V) + len(D) == len(T),
          f"{n_gierig} → {len(V)} Vierecke, Buchführung {2 * len(V) + len(D)} = {len(T)}")
    check("kein Viereck ist umgestülpt", len(V) == 0 or float(_viereckguete(P2[V]).min()) > 0,
          f"kleinste Vierecksgüte {float(_viereckguete(P2[V]).min()):.3f}" if len(V) else "-")
    # Die Guetegrenze ist nicht der Engpass: sie von 0,3 auf 10^-6 zu senken
    # holt auf 882 Dreiecken noch vier Paare und aendert am fertigen Netz
    # keine Zahl (Keilanteil und Verschiebung unten sind fuer beide gleich,
    # 22.09.2026). Darum bleibt sie, wo sie ist - ein schlechtes Viereck waere
    # ein schlechter Sechsflaechner.
    ohne_grenze = len(sweep.paaren(P2, T, 1e-6)[1])
    check("die Gütegrenze ist nicht der Engpass - ohne sie bleibt es fast gleich",
          abs(ohne_grenze - len(D)) <= 0.2 * len(D),
          f"{len(D)} mit Grenze 0,3 gegen {ohne_grenze} ohne")
    # Und am fertigen Netz: weniger Keile, bessere Verschiebung
    zahlen = {}
    for h_ in (0.05, 0.025):
        m2, k2 = platte_mit_bohrungen(1.0, 0.2, 0.05, bohrungen=((0.95, 0.1, 0.01),))
        m2.add_load_case("LF1")
        m2.case("LF1").gravity = [0.0, 0.0, 0.0]
        m2.add_geometrielast("M2", 10e3 / (0.2 * 0.05), "flaeche", richtung=[0.0, 0.0, -1.0], case="LF1")
        ss = m2.add_surface_support(name="Einspannung")
        ss.flaechen = ["M4"]
        for d in (0, 1, 2):
            ss.behaviour[d] = DofBehaviour("rigid")
        m2.netz.ziellaenge = h_
        m2.netz.dichte = "eigene"
        m2.active_case = "LF1"
        mesher.modell_vernetzen(m2, [], workers=1)
        res = solver.solve_static(m2, case="LF1", workers=1)
        typ = _typen(m2)
        zahlen[h_] = (typ.get("pent6", 0) / max(1, sum(typ.values())),
                      float(np.abs(res.u[:, 2]).max()), typ)
    w_balken = 10e3 * 1.0 ** 3 / (3 * 210e9 * 0.2 * 0.05 ** 3 / 12)         + 10e3 * 1.0 / (5.0 / 6.0 * 210e9 / 2.6 * 0.2 * 0.05)
    check("Keilanteil bei h = 25 mm unter 10 % (vor dem Umpaaren 13,5 %)",
          zahlen[0.025][0] < 0.10, f"{zahlen[0.025][0] * 100:.1f} % {zahlen[0.025][2]}")
    check("und die Endverschiebung über 97 % der Balkenlösung (vorher 97,1 %)",
          zahlen[0.025][1] / w_balken > 0.97, f"{zahlen[0.025][1] / w_balken * 100:.1f} %")
    check("auch am groben Netz: Keilanteil unter 15 %, über 95 % (vorher 19,1 % und 93,8 %)",
          zahlen[0.05][0] < 0.15 and zahlen[0.05][1] / w_balken > 0.95,
          f"{zahlen[0.05][0] * 100:.1f} %, {zahlen[0.05][1] / w_balken * 100:.1f} %")


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


def test_vorgabe_aus():
    """Die Vorgabe `Netzeinstellungen.sweep` ist **aus** (21.09.2026).

    Der Sweep liefert das bessere Element - an der Kragplatte 97,6 % der
    Balkenloesung gegen 68,4 % beim Tetraeder (test_kragplatte_tet4_gegen_hex8).
    Am Drehlager erzeugte er aber 992 entartete Keile (10,6 % aller pent6,
    schlechteste Formguete 0,025; von 31.108 Hexaedern keiner unter 0,10), und
    LF1 rechnete darauf max |u| 1,2335 statt 0,2716 mm - Faktor 4,5. Die Keile
    erben die Splitterdreiecke der Flaechenvernetzung: die Paarung zu Vierecken
    verlangt Guete >= 0,3, ein Splitterdreieck erfuellt das nie und bleibt als
    Keil uebrig.

    Darum wird von Hand eingeschaltet (Netz -> Netzeinstellungen), bis die
    Flaechenteilung eine Mindestweite kennt. Geprueft wird nicht nur das Feld,
    sondern das Verhalten: derselbe Koerper einmal ohne und einmal mit Haken.
    """
    from statik3d.model import Netzeinstellungen
    check("die Vorgabe ist aus", Netzeinstellungen().sweep is False,
          "sweep = %r" % Netzeinstellungen().sweep)

    def netz(an):
        # Mit Bohrung: ein Quader ohne Bohrung ginge den abgebildeten Pfad
        # (mesher._hex_netz, sechs Vierecke und acht Eckknoten) und gaebe auch
        # ohne Sweep Hexaeder - er wuerde die Frage nicht beantworten.
        m, k = _platte_roh(0.4, 0.2, 0.2, bohrungen=((0.2, 0.1, 0.03),))
        m.netz.sweep = bool(an)
        m.netz.ziellaenge = 0.1
        m.netz.dichte = "eigene"
        mesher.modell_vernetzen(m, [], workers=1)
        return _typen(m)

    aus, an = netz(False), netz(True)
    check("ohne Haken: nur Tetraeder", set(aus) == {"tet4"}, str(aus))
    check("mit Haken: Hexaeder und Keile", set(an) <= {"hex8", "pent6"} and "hex8" in an,
          str(an))


def test_betriebsart_sauber():
    """Dritter Auftrag (24.09.2026), Aufgabe 4: ``Netzeinstellungen.sweep``
    kennt "aus", "sauber" und "immer"; True/False alter Dateien heissen
    "immer"/"aus". In der Betriebsart "sauber" wird ein Koerper nur gesweept,
    wenn jedes hex8 und pent6 hoechstens TRAPEZ_GRENZE Trapezfehler und eine
    positive Jacobi-Determinante hat - sonst Tetraeder, mit Grund im
    Protokoll. Das Mass ist der **Trapezfehler** (Winkel zwischen
    gegenueberliegenden Kanten einer Viereckseite), nicht der Eckwinkel:
    am Kragarm kostet Parallelogrammverzerrung bis 30 Grad nichts,
    Trapezverzerrung ab 2,5 Grad mehr als 1 N/mm2 (tests/messung_winkelfehler.py)."""
    def art(wert):
        m = Model()
        m.netz.sweep = wert
        return sweep.betriebsart(m)
    check("True heisst immer, False aus (alte Dateien)", art(True) == "immer" and art(False) == "aus",
          f"{art(True)}, {art(False)}")
    check("die drei Woerter, auch mit Grossbuchstaben und Leerzeichen",
          art("aus") == "aus" and art("sauber") == "sauber" and art("immer") == "immer" and art(" Sauber ") == "sauber")
    check("ein unbekanntes Wort gilt als immer", art("hexaeder") == "immer", art("hexaeder"))
    check("die Vorgabe ist aus", sweep.betriebsart(Model()) == "aus", sweep.betriebsart(Model()))
    check("die Grenzen: Trapez 5 Grad = 2 x Winkelfehler 2,5 Grad (gemessen 24.09.2026)",
          abs(sweep.WINKELFEHLER_GRENZE - 2.5) < 1e-12 and abs(sweep.TRAPEZ_GRENZE - 5.0) < 1e-12,
          f"{sweep.WINKELFEHLER_GRENZE}, {sweep.TRAPEZ_GRENZE}")
    # Trapez- gegen Winkelfehler am Einheitswuerfel, Deckel um 10 Grad verzerrt
    X0 = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                   [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
    t = float(np.tan(np.radians(10.0)))
    Xp = X0.copy()
    Xp[4:, 0] += t                                   # Parallelogramm: Deckel verschoben
    Xt = X0.copy()
    Xt[4:, 0] = 0.5 + (Xt[4:, 0] - 0.5) * (1.0 - 2.0 * t)   # Trapez: Deckel schmaler
    wf_p, tf_p = sweep.winkelfehler(Xp, "hex8"), sweep.trapezfehler(Xp, "hex8")
    wf_t, tf_t = sweep.winkelfehler(Xt, "hex8"), sweep.trapezfehler(Xt, "hex8")
    check("Parallelogramm: Winkelfehler 10 Grad, Trapezfehler 0", abs(wf_p - 10.0) < 0.5 and tf_p < 1e-6,
          f"Winkel {wf_p:.2f}, Trapez {tf_p:.2e}")
    check("Trapez: Winkelfehler 10 Grad, Trapezfehler 20 Grad", abs(wf_t - 10.0) < 0.5 and abs(tf_t - 20.0) < 0.5,
          f"Winkel {wf_t:.2f}, Trapez {tf_t:.2f}")
    check("ein regelmaessiger Wuerfel hat beides 0",
          sweep.winkelfehler(X0, "hex8") < 1e-9 and sweep.trapezfehler(X0, "hex8") < 1e-9)
    # Die Pruefung vor dem Einbau an einem Lagenstapel (ein Viereck, eine Lage)
    vierecke, dreiecke = np.array([[0, 1, 2, 3]]), np.zeros((0, 3), int)
    ok0, _g0, tf0, wf0 = sweep.sauber_pruefen(np.stack([X0[:4], X0[4:]]), vierecke, dreiecke)
    okp, _gp, tfp, wfp = sweep.sauber_pruefen(np.stack([X0[:4], Xp[4:]]), vierecke, dreiecke)
    okt, gt, tft, wft = sweep.sauber_pruefen(np.stack([X0[:4], Xt[4:]]), vierecke, dreiecke)
    oki, gi, _tfi, _wfi = sweep.sauber_pruefen(np.stack([X0[4:], X0[:4]]), vierecke, dreiecke)
    check("regelmaessig: sauber", ok0 and tf0 < 1e-9 and wf0 < 1e-9)
    check("Parallelogramm 10 Grad: sauber (Trapezfehler 0, Winkelfehler 10)", okp and tfp < 1e-6 and abs(wfp - 10) < 0.5,
          f"Trapez {tfp:.2e}, Winkel {wfp:.2f}")
    check("Trapez 10 Grad: nicht sauber, der Grund nennt den Trapezfehler",
          not okt and "Trapezfehler" in gt and abs(tft - 20) < 0.5, gt)
    check("umgestuelpt (Deckel unter dem Boden): nicht sauber, der Grund nennt die Jacobi-Determinante",
          not oki and "Jacobi" in gi, gi)
    # Das Verhalten: Kegelstumpf und Zylinder (gepflasterte Kreisscheibe) gegen
    # den Quader mit geteilter Deckelkante (abgebildetes Vierecknetz als Grund)
    aus = {}
    for r2, wert in ((0.03, "sauber"), (0.05, "sauber"), (0.03, True), (0.03, "aus")):
        m, k = _kegelstumpf(0.05, r2)
        m.netz.sweep = wert
        log = []
        mesher.modell_vernetzen(m, log, workers=1)
        aus[(r2, wert)] = (_typen(m), log)
    typen, log = aus[(0.03, "sauber")]
    check("Kegelstumpf, sauber: der Sweep lehnt ab, Tetraeder", set(typen) == {"tet4"}, str(typen))
    check("  und das Protokoll sagt warum (Trapezfehler ueber der Grenze)",
          any("nicht gesweept (Betriebsart „sauber“)" in z and "Trapezfehler" in z and "Pyramiden" in z for z in log),
          "; ".join(z.strip()[:150] for z in log if "sauber" in z)[:200])
    # Auch der Zylinder: seine Kreisscheibe ist aus gepaarten Dreiecken
    # gepflastert, die Vierecke haben bis 72 Grad Winkel- und rund 70 Grad
    # Trapezfehler (gemessen 24.09.2026) - kein sauberer Hexaeder
    typen, log = aus[(0.05, "sauber")]
    check("Zylinder, sauber: die gepflasterte Kreisscheibe ist kein sauberer Hexaeder - Tetraeder",
          set(typen) == {"tet4"} and any("nicht gesweept (Betriebsart „sauber“)" in z and "Trapezfehler" in z for z in log),
          str(typen) + "; " + "; ".join(z.strip()[60:150] for z in log if "sauber" in z)[:150])
    # Und der Befund, der die Betriebsart heute bestimmt: auch ein
    # **Rechteck** als Grund wird aus gepaarten Dreiecken gepflastert
    # (sweep._grundnetz), nicht als abgebildetes Vierecknetz - der Block des
    # Quaders mit geteilter Deckelkante (Kappen X0 -> XA, 100 x 200 mm bei
    # h = 50 mm) kam auf 30 Grad Trapezfehler (gemessen 24.09.2026; ein
    # 100 x 50 mm-Grund auf 5,9 Grad). Ein abgebildetes Grundnetz fuer
    # vierseitige Grundflaechen ist der Weg, die Betriebsart mit Hexaedern
    # zu fuellen - er gehoert zum Plan des hex8-Vernetzers. In "sauber" wird
    # nicht zerlegt: der Koerper ist als Ganzes nicht sweepbar (zwei Waende
    # nicht aus vier Linien) und geht mit Grund im Protokoll an die Tetraeder.
    m, k = _quader_mit_geteilter_kante()
    m.netz.sweep = "sauber"
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    typen = _typen(m)
    check("Quader mit geteilter Deckelkante, sauber: nicht als Ganzes sweepbar, kein Zerlegen - Tetraeder mit Grund",
          set(typen) == {"tet4"} and any("nicht gesweept - " in z and "wird nicht zerlegt" in z for z in log),
          str(typen) + "; " + "; ".join(z.strip()[:150] for z in log if "nicht gesweept" in z)[:200])
    check("  die Ablehnung steht genau einmal im Protokoll",
          sum(1 for z in log if "nicht gesweept" in z) == 1, f"{sum(1 for z in log if 'nicht gesweept' in z)} Zeilen")
    m, k = _quader_mit_geteilter_kante()
    m.netz.sweep = True
    mesher.modell_vernetzen(m, [], workers=1)
    check("  mit True wird derselbe Koerper gesweept (Hexaeder und Keile, wie bisher)",
          set(_typen(m)) <= {"hex8", "pent6"} and "hex8" in _typen(m), str(_typen(m)))
    typen, _log = aus[(0.03, True)]
    check("Kegelstumpf mit True (alte Datei): weiter gesweept wie bisher", set(typen) <= {"hex8", "pent6"} and typen,
          str(typen))
    typen, _log = aus[(0.03, "aus")]
    check("Kegelstumpf mit \"aus\": Tetraeder", set(typen) == {"tet4"}, str(typen))


def test_pyramiden_ausrichtung_am_abgebildeten_nachbarn():
    """Dritter Auftrag (24.09.2026), Aufgabe 4: in der Betriebsart "sauber"
    geht der Uebergang zum Tetraeder-Nachbarn immer ueber Pyramiden (pyr5),
    auch ohne ``netz.pyramiden``. An der Fuge zu einem **abgebildeten**
    Quader kamen alle 32 Pyramiden umgestuelpt in den Loeser (det J = -9,8e-7
    an jedem Punkt; solid_volume nimmt den Betrag und sah nichts) - jetzt
    richtet das Vorzeichen der Jacobi-Determinante die Grundflaeche aus.
    Pruefkoerper: der zweiteilige Kragarm aus tests/messung_uebergang_pyramiden."""
    import pruefkoerper as pk
    from messung_uebergang_pyramiden import geometrie
    from statik3d.elements.solid import jacobi_volumen
    kr = pk.Kragarm()
    h = 0.05
    m = Model("uebergang")
    m.add_material(Material("S", E=pk.E_ST, nu=pk.NU_ST, rho=0.0))
    kA, kB = geometrie(m, kr, h_teilung=h)
    m.netz.sweep = "sauber"
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    check("netz.pyramiden ist aus - die Pyramiden kommen aus der Betriebsart", not getattr(m.netz, "pyramiden", False))
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    tA = {m.elements[e].typ for e in kA.elemente}
    tB = {m.elements[e].typ for e in kB.elemente}
    check("A ist das abgebildete hex8-Gitter, B Tetraeder mit Pyramiden", tA == {"hex8"} and tB == {"tet4", "pyr5"},
          f"{tA} / {tB}")
    pyr = [m.elements[e] for e in kB.elemente if m.elements[e].typ == "pyr5"]
    n_soll = int(round(kr.B / h)) * int(round(kr.H / h))
    check(f"je Viereck der Fuge eine Pyramide ({n_soll})", len(pyr) == n_soll, f"{len(pyr)} Pyramiden")
    dets = [jacobi_volumen("pyr5", m.nodes[e.nodes]) for e in pyr]
    check("jede Pyramide hat positives Volumen und det J > 0 an allen Punkten (vorher alle umgestuelpt)",
          dets and all(d["V"] > 0 and d["det_min"] > 0 for d in dets),
          f"det_min {min(d['det_min'] for d in dets):.3e}, V min {min(d['V'] for d in dets):.3e} m^3" if dets else "keine")
    V_hex = sum(solid_volume("hex8", m.nodes[m.elements[e].nodes]) for e in kA.elemente)
    V_B = sum(solid_volume(m.elements[e].typ, m.nodes[m.elements[e].nodes]) for e in kB.elemente)
    V_soll_A = kr.L / 2 * kr.B * kr.H
    # B: Quader plus der bilineare Deckel mit einer um 20 mm angehobenen Ecke (mittlere Hoehe dz / 4)
    V_soll_B = kr.L / 2 * kr.B * kr.H + (kr.L / 4) * kr.B * 0.02 / 4
    check("Rauminhalt A exakt, B innerhalb 1 %", abs(V_hex - V_soll_A) < 1e-9 * V_soll_A and abs(V_B - V_soll_B) < 0.01 * V_soll_B,
          f"A {V_hex * 1e6:.1f} cm3 (Soll {V_soll_A * 1e6:.1f}), B {V_B * 1e6:.1f} cm3 (Soll {V_soll_B * 1e6:.1f})")
    bef = diagnose.abnahme(m)
    check("Abnahme ohne Befund", not bef, str([(b.pruefung, b.text[:60]) for b in bef])[:200])


def main():
    for t in (test_vorgabe_aus, test_erkennung, test_netz_platte, test_quader_bleibt_abgebildet, test_nachbar_mit_tetraedern,
              test_nachbar_mit_verschiedener_teilung, test_lagen_bei_fliessen,
              test_quader_randseiten_und_nachbar, test_zylinder_wird_gesweept,
              test_platte_mit_nabe_zerlegt, test_abgesetzte_welle_zerlegt,
              test_pyramiden_als_uebergang, test_zerlegen_sagt_warum_nicht,
              test_keile_am_feinen_rand, test_verjuengter_zug, test_drehkoerper,
              test_krummer_quader_nicht_abgebildet, test_umpaaren_spart_keile,
              test_rippe_am_rand_ueber_ebene_zerlegt, test_kappen_verschieden_geteilt,
              test_angleichen_schont_den_nachbarn, test_zerlegen_an_vorhandener_schleife,
              test_zerlegen_namen_und_budget,
              test_kragplatte_tet4_gegen_hex8, test_betriebsart_sauber,
              test_pyramiden_ausrichtung_am_abgebildeten_nachbarn):
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
