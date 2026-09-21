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

from statik3d.model import Model, DofBehaviour                       # noqa: E402
from statik3d import mesher, sweep, diagnose, netzguete, solver       # noqa: E402
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
              test_kragplatte_tet4_gegen_hex8):
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
