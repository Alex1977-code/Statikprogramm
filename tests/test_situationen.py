"""
Situationen (Stellung + abgeschaltete Elemente) und Subsysteme.

Jeder Lastfall rechnet in seiner Situation mit einem eigenen System; die
Pruefungen vergleichen mit geschlossenen Loesungen (Kragarm, eingespannt-
gestuetzter Balken, Dehnstab) - nie mit frueheren Ergebnissen.
Aufruf:  python -m tests.test_situationen
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import (Model, Material, Section, Situation, Combination,  # noqa: E402
                            Support, GRUNDSTELLUNG, GESAMTSYSTEM)
from statik3d import solver, mesher, combinations as comb  # noqa: E402
from statik3d.bridges.positions import Stellung  # noqa: E402

RESULTS = []
E, L, F = 210e9, 3.0, 10e3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6e} ana={want:.6e} Abw={err * 100:.4f}% {unit}")


def _balken(n: int = 2, laenge: float = 2 * L) -> tuple:
    """Balken auf der x-Achse, Bernoulli (schubstarr), eingespannt am Anfang."""
    m = Model("Situationen")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.1, 0.2)
    sec.Asy = sec.Asz = 0.0                     # schubstarr: geschlossene Formeln exakt
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (laenge, 0, 0), n)
    m.fix(ids[0], "all")
    return m, ids, sec


def test_abgeschaltete_elemente():
    m, ids, sec = _balken(2)
    n0, n1, n2 = ids
    EI = E * sec.Iy
    m.supports.append(Support(node=n2, dofs=[2], name="Rolle"))
    m.add_load_case("LF1", "G")
    m.load_node(n1, Fz=-F, case="LF1")
    m.add_load_case("LF2", "G")
    m.load_node(n1, Fz=-F, case="LF2")
    m.load_cases["LF2"].situation = "Kragarm"
    m.situationen["Kragarm"] = Situation("Kragarm", "", [1], "zweites Element aus")
    check("Modellpruefung ohne Beanstandung", not m.check(), str(m.check()))
    an = solver.solve_all(m)
    close("Grundstellung: eingespannt-gestuetzt w = 7PL³/96EI", an.cases["LF1"].u[n1, 2],
          -7 * F * L ** 3 / (96 * EI), 1e-9, "m")
    r2 = an.cases["LF2"]
    close("Situation: zweites Element aus -> Kragarm w = PL³/3EI", r2.u[n1, 2],
          -F * L ** 3 / (3 * EI), 1e-9, "m")
    check("abgeschaltetes Element ohne Schnittgroessen", np.allclose(r2.beam_end[1], 0.0)
          and r2.info.get("inaktiv") == [1])
    check("Auflager am abgeschalteten Ende ohne Kraft", abs(r2.reactions[n2, 2]) < 1e-9,
          f"{r2.reactions[n2, 2]:.3e}")
    check("Knoten ohne wirksames Element wird festgehalten", np.allclose(r2.u[n2], 0.0))
    check("Ergebnis nennt seine Situation", r2.info.get("situation") == "Kragarm")
    check("je Situation ein System", set(an.systeme) == {GRUNDSTELLUNG, "Kragarm"}
          and an.systeme["Kragarm"].aktiv is not None and not an.systeme["Kragarm"].aktiv[1])
    # Kombinationen: nur Lastfaelle derselben Situation
    m.combinations["K1"] = Combination("K1", {"LF2": 1.5}, "ULS", situation="Kragarm")
    m.combinations["K2"] = Combination("K2", {"LF1": 1.0, "LF2": 1.0}, "ULS")
    msgs = m.check()
    check("Modellpruefung: gemischte Kombination ist ein FEHLER",
          any("K2" in x and "anderen Situation" in x for x in msgs), str(msgs))
    try:
        solver.solve_combination(m, m.combinations["K2"], an.cases)
        check("Solver weist die gemischte Kombination ab", False)
    except ValueError as ex:
        check("Solver weist die gemischte Kombination ab", "K2" in str(ex))
    del m.combinations["K2"]
    an = solver.solve_all(m)
    close("Kombination in der Situation: 1,5 · w", an.combinations["K1"].u[n1, 2],
          -1.5 * F * L ** 3 / (3 * EI), 1e-9, "m")
    check("Kombination nennt Situation und abgeschaltete Elemente",
          an.combinations["K1"].info.get("situation") == "Kragarm"
          and an.combinations["K1"].info.get("inaktiv") == [1])
    # Eigengewicht: das abgeschaltete Element traegt nicht
    m.materials["S"].rho = 7850.0
    m.add_load_case("EG", "G")
    m.load_cases["EG"].gravity = [0.0, 0.0, -9.81]
    m.load_cases["EG"].situation = "Kragarm"
    an = solver.solve_all(m)
    R = an.cases["EG"].reactions[:, 2].sum()
    close("Eigengewicht nur des wirksamen Elements", R, 7850.0 * sec.A * L * 9.81, 1e-9, "N")
    # Theorie II. Ordnung laeuft je Situation
    m.design.theorie2 = "ein"
    m.add_load_case("N", "G")
    m.load_node(n1, Fx=-1e3, case="N")
    m.load_cases["N"].situation = "Kragarm"
    m.combinations["K3"] = Combination("K3", {"LF2": 1.0, "N": 1.0}, "ULS", situation="Kragarm")
    an = solver.solve_all(m)
    check("Theorie II. Ordnung in der Situation gerechnet",
          "K3" in an.theorie2.kombinationen and an.theorie2.kombinationen["K3"].gerechnet
          and np.allclose(an.combinations["K3"].beam_end[1], 0.0),
          str(an.theorie2.kombinationen.get("K3")))
    m.design.theorie2 = "aus"
    # Alle Elemente aus: FEHLER
    m.situationen["leer"] = Situation("leer", "", [0, 1])
    m.load_cases["N"].situation = "leer"
    check("alle Elemente aus ist ein FEHLER", any("leer" in x for x in m.check()))


def test_stellung():
    m, ids, sec = _balken(2, L)
    EI, EA = E * sec.Iy, E * sec.A
    m.add_load_case("LF1", "G")
    m.load_node(ids[-1], Fz=-F, case="LF1")
    m.add_load_case("LF2", "G")
    m.load_node(ids[-1], Fz=-F, case="LF2")
    m.stellungen.append(Stellung("S90", 90.0, "hochgeklappt", dreh_achse=(0, 1, 0),
                                 dreh_punkt=(0, 0, 0), dreh_winkel=90.0))
    m.situationen["hoch"] = Situation("hoch", "S90", [], "Kragarm senkrecht")
    m.load_cases["LF2"].situation = "hoch"
    an = solver.solve_all(m)
    close("Grundstellung: Kragarm waagerecht w = PL³/3EI", an.cases["LF1"].u[ids[-1], 2],
          -F * L ** 3 / (3 * EI), 1e-9, "m")
    r = an.cases["LF2"]
    close("Stellung 90°: Last laengs, u = PL/EA", r.u[ids[-1], 2], -F * L / EA, 1e-9, "m")
    check("Stellung: Ergebnismodell traegt die gedrehten Knoten",
          np.allclose(r.model.nodes[ids[-1]], [0.0, 0.0, -L], atol=1e-9)
          and np.allclose(m.nodes[ids[-1]], [L, 0.0, 0.0]),
          str(r.model.nodes[ids[-1]]))
    check("Grundstellung rechnet mit dem Modell selbst", an.modelle[GRUNDSTELLUNG] is m
          and an.modelle["hoch"] is not m)
    m.situationen["hoch"].stellung = "gibt es nicht"
    check("unbekannte Stellung ist ein FEHLER", any("gibt es nicht" in x for x in m.check()))


def test_stellung_lage_und_wirkung():
    """Ausgangsstellung, Verschiebung, abgeschaltete Staebe, biegesteife
    Gelenke und Lager je Stellung - gegen geschlossene Loesungen."""
    from statik3d.model import Member
    m, ids, sec = _balken(2, 2 * L)               # Knoten 0, 1, 2 bei x = 0, L, 2L
    EI = E * sec.Iy
    m.members["M1"] = Member("M1", [0])
    m.members["M2"] = Member("M2", [1])
    m.add_load_case("LF1", "G")
    m.load_node(ids[1], Fz=-F, case="LF1")        # Last in Balkenmitte
    m.add_load_case("LF2", "G")
    m.load_node(ids[2], Fz=-F, case="LF2")        # Last am Ende
    # Stellung "kurz": der aeussere Stab M2 wirkt nicht -> Kragarm der Laenge L
    m.stellungen.append(Stellung("kurz", 0.0, "ohne M2", staebe_aus=["M2"]))
    m.situationen["kurz"] = Situation("kurz", "kurz")
    m.load_cases["LF1"].situation = "kurz"
    # Stellung "hoch": 90 Grad um y; "hoch+1": darauf aufsetzend um 1 m in x verschoben
    m.stellungen.append(Stellung("hoch", 90.0, dreh_achse=(0, 1, 0), dreh_punkt=(0, 0, 0),
                                 dreh_winkel=90.0))
    m.stellungen.append(Stellung("hoch+1", 90.0, basis="hoch", verschiebung=(1.0, 0.0, 0.0)))
    m.situationen["oben"] = Situation("oben", "hoch+1")
    m.load_cases["LF2"].situation = "oben"
    an = solver.solve_all(m)
    r1 = an.cases["LF1"]
    close("Stab M2 abgeschaltet: w(L) = FL³/3EI des kurzen Kragarms", r1.u[ids[1], 2],
          -F * L ** 3 / (3 * EI), 1e-9, "m")
    check("abgeschaltetes Element ohne Schnittgroessen, Endknoten festgehalten",
          np.allclose(r1.beam_end[1], 0.0) and abs(r1.u[ids[2], 2]) < 1e-12
          and list(r1.info.get("inaktiv", [])) == [1], str(r1.info.get("inaktiv")))
    check("aktive_elemente kennt die Abschaltung der Stellung",
          list(m.aktive_elemente("kurz")) == [True, False])
    r2 = an.cases["LF2"]
    check("Ausgangsstellung + Verschiebung: Kette aus Drehung und Verschiebung",
          np.allclose(r2.model.nodes[ids[2]], [1.0, 0.0, -2 * L], atol=1e-9)
          and np.allclose(r2.model.nodes[ids[0]], [0.0, 0.0, 0.0], atol=1e-9),
          str(r2.model.nodes[ids[2]]))
    # Gelenk am Ende von Element 0 - in Stellung "steif" wieder biegesteif
    m.add_hinge("G1", end=1, phiy="free")
    m.apply_hinge(0, "G1")
    check("apply_hinge merkt sich das Element", m.hinges["G1"].elemente == [0]
          and m.elements[0].hinges == [10])
    m.stellungen.append(Stellung("steif", 0.0, gelenke_aus=["G1"]))
    m2 = m.copy()
    m.stellungen[-1].anwenden(m2, m)
    check("Stellung macht das Gelenk biegesteif (nur in der Kopie)",
          m2.elements[0].hinges == [] and m.elements[0].hinges == [10])
    m.situationen["steif"] = Situation("steif", "steif")
    m.add_load_case("LF3", "G")
    m.load_node(ids[2], Fz=-F, case="LF3")
    m.load_cases["LF3"].situation = "steif"
    an = solver.solve_all(m, names=["LF3"]) if "names" in solver.solve_all.__code__.co_varnames \
        else solver.solve_all(m)
    close("Gelenk biegesteif: Kragarm 2L, w = F(2L)³/3EI", an.cases["LF3"].u[ids[2], 2],
          -F * (2 * L) ** 3 / (3 * EI), 1e-9, "m")
    # Lager ueber Nummer statt Namen abschalten
    m.fix(ids[2], "all")                          # Lager 1: Einspannung am Ende
    st = Stellung("frei", 0.0, lager_aus=["1"])
    m3 = m.copy()
    st.anwenden(m3, m)
    check("Lager ueber seine Nummer abgeschaltet", len(m3.supports) == 1
          and int(m3.supports[0].node) == ids[0] and len(m.supports) == 2)
    # Elemente loeschen zieht die Gelenk-Elemente nach
    m4 = m.copy()
    m4.elemente_loeschen([1])
    check("Elemente loeschen: Gelenk zeigt weiter auf sein Element",
          m4.hinges["G1"].elemente == [0])
    m4.elemente_loeschen([0])
    check("… und verliert es, wenn es geloescht wird", m4.hinges["G1"].elemente == [])
    d = m.to_dict()
    import json
    m5 = Model.from_dict(json.loads(json.dumps(d)))
    st5 = m5.stellung("hoch+1")
    check("Ausgangsstellung, Verschiebung und Abschaltungen ueberleben Speichern",
          st5.basis == "hoch" and st5.verschiebung == (1.0, 0.0, 0.0)
          and m5.stellung("kurz").staebe_aus == ["M2"] and m5.stellung("steif").gelenke_aus == ["G1"]
          and m5.hinges["G1"].elemente == [0])


def test_speichern():
    m, ids, sec = _balken(2, L)
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].situation = "hoch"
    m.stellungen.append(Stellung("S90", 90.0, "hochgeklappt", dreh_achse=(0, 1, 0),
                                 dreh_winkel=90.0, lager_aus=["Rolle"], antrieb=(1, (0, 5e3, 0))))
    m.situationen["hoch"] = Situation("hoch", "S90", [1], "")
    m.combinations["K1"] = Combination("K1", {"LF1": 1.35}, "ULS", situation="hoch")
    from statik3d.model import Member
    m.members["St1"] = Member("St1", [0, 1])
    sub = m.subsystem_bilden("Teil A", staebe=["St1"], beschreibung="links")
    d = m.to_dict()
    import json
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    check("Situation, Stellung, Subsystem ueberleben Speichern",
          list(m2.situationen) == ["hoch"] and m2.situationen["hoch"].deaktiviert == [1]
          and m2.stellungen[0].name == "S90" and m2.stellungen[0].dreh_achse == (0, 1, 0)
          and m2.stellungen[0].lager_aus == ["Rolle"] and m2.stellungen[0].antrieb == (1, (0, 5e3, 0))
          and m2.load_cases["LF1"].situation == "hoch" and m2.combinations["K1"].situation == "hoch"
          and list(m2.subsysteme) == ["Teil A"] and m2.subsysteme["Teil A"].elemente == sub.elemente)
    m3 = m2.copy()
    check("copy() nimmt alles mit", m3.situationen["hoch"].stellung == "S90"
          and m3.subsysteme["Teil A"].knoten == sub.knoten)


def test_subsystem():
    from statik3d.model import Member, LineSupport
    m = Model("Rahmen")
    m.add_material(Material("S", E=E))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    h, b = 4.0, 6.0
    li = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (0, 0, h), 2)        # linke Stuetze
    re = mesher.line_of_beams(m, "S", "R", (b, 0, 0), (b, 0, h), 2)        # rechte Stuetze
    ri = mesher.line_of_beams(m, "S", "R", (0, 0, h), (b, 0, h), 2)        # Riegel (eigene Knoten)
    mesher.merge_nodes(m, 1e-6)          # Riegel an die Stuetzenkoepfe haengen
    kopf_li = int(np.argmin(np.linalg.norm(m.nodes - [0, 0, h], axis=1)))
    kopf_re = int(np.argmin(np.linalg.norm(m.nodes - [b, 0, h], axis=1)))
    fuss_li = int(np.argmin(np.linalg.norm(m.nodes - [0, 0, 0], axis=1)))
    m.fix(fuss_li, "all")
    m.fix(int(np.argmin(np.linalg.norm(m.nodes - [b, 0, 0], axis=1))), "all")
    stuetze = [i for i, e in enumerate(m.elements) if abs(m.nodes[e.nodes[0]][0]) < 1e-9
               and abs(m.nodes[e.nodes[1]][0]) < 1e-9]
    riegel = [i for i, e in enumerate(m.elements) if abs(m.nodes[e.nodes[0]][2] - h) < 1e-9
              and abs(m.nodes[e.nodes[1]][2] - h) < 1e-9]
    m.members["Stuetze links"] = Member("Stuetze links", stuetze)
    m.members["Riegel"] = Member("Riegel", riegel)
    ges = m.subsystem(GESAMTSYSTEM)
    check("Gesamtsystem ist die ganze Struktur", ges.elemente == list(range(len(m.elements)))
          and ges.knoten == list(range(m.nn)) and m.subsystemnamen() == [GESAMTSYSTEM])
    sub = m.subsystem_bilden("Links", staebe=["Stuetze links"])
    beruehrt = [i for i in riegel if kopf_li in m.elements[i].nodes]
    check("Subsystem aus dem Stab: seine Elemente samt Beruehrungselement",
          set(sub.elemente) == set(stuetze) | set(beruehrt) and sub.beruehrung == beruehrt
          and len(beruehrt) == 1, f"{sub.elemente} / {sub.beruehrung}")
    check("Knoten, Lager und Stab gehoeren dazu",
          fuss_li in sub.knoten and kopf_li in sub.knoten and sub.lager == [0]
          and sub.staebe == ["Stuetze links"] and "Riegel" not in sub.staebe, sub.bezug())
    sub2 = m.subsystem_bilden("Links ohne", staebe=["Stuetze links"], beruehrung=False)
    check("ohne Beruehrung nur der Stab selbst", set(sub2.elemente) == set(stuetze)
          and not sub2.beruehrung)
    check("Beruehrungselement gehoert auch dem Gesamtsystem",
          all(i in m.subsystem(GESAMTSYSTEM).elemente for i in beruehrt))
    try:
        m.subsystem_bilden("leer")
        check("leere Auswahl wird abgewiesen", False)
    except ValueError:
        check("leere Auswahl wird abgewiesen", True)
    # Loeschen eines Elements zieht die Nummern nach
    weg = riegel[-1]
    alt = [i for i in sub.elemente]
    m.elemente_loeschen([weg])
    erwartet = [i if i < weg else i - 1 for i in alt if i != weg]
    check("Elementnummern der Subsysteme ziehen nach dem Loeschen nach",
          m.subsysteme["Links"].elemente == erwartet, f"{m.subsysteme['Links'].elemente}")
    m.situationen["S"] = Situation("S", "", [weg - 1, weg])
    m.elemente_loeschen([weg - 1])
    check("Elementnummern der Situationen ziehen nach", m.situationen["S"].deaktiviert == [],
          str(m.situationen["S"].deaktiviert))


def test_kombinationen_je_situation():
    m, ids, sec = _balken(2, L)
    m.add_load_case("G1", "G")
    m.add_load_case("Q1", "Q")
    m.add_load_case("Q2", "Q")
    m.load_cases["Q2"].situation = "hoch"
    m.situationen["hoch"] = Situation("hoch", "", [1])
    for k in ("G1", "Q1", "Q2"):
        m.load_node(ids[-1], Fz=-F, case=k)
    combos = comb.generate_combinations(m)
    check("Kombinationen werden je Situation gebildet", combos
          and all(not any((m.load_cases[k].situation or GRUNDSTELLUNG) != (c.situation or GRUNDSTELLUNG)
                          for k in c.factors) for c in combos), str([c.factors for c in combos]))
    check("Kombinationen der Situation tragen sie im Namen und im Feld",
          any(c.situation == "hoch" and "[hoch]" in c.description for c in combos)
          and any(not c.situation for c in combos))
    check("Modellpruefung ohne Beanstandung", not m.check(), str(m.check()))
    an = solver.solve_all(m)
    check("alle Kombinationen gerechnet", set(an.combinations) == set(m.combinations))


def _balken_mit_rolle() -> tuple:
    """Balken 2L, eingespannt, Rolle 'Rolle' am Ende; Stellung 'offen' baut
    die Rolle ab. LF1 (Grundstellung) und LF-S (Situation 'offen') tragen
    dieselbe Last in Balkenmitte."""
    m, ids, sec = _balken(2)
    m.supports.append(Support(node=ids[2], dofs=[2], name="Rolle"))
    m.stellungen.append(Stellung("offen", 0.0, "Rolle abgebaut", lager_aus=["Rolle"]))
    m.situationen["offen"] = Situation("offen", "offen")
    for lf in ("LF1", "LF-S"):
        m.add_load_case(lf, "G")
        m.load_node(ids[1], Fz=-F, case=lf)
    m.load_cases["LF-S"].situation = "offen"
    return m, ids, sec


def _situation_in_zusammenfassung(res):
    """Der Wert der Zeile „Situation : …“ in res.summary(), sonst None.

    Die Zusammenfassung ist, was Oberflaeche (Protokoll und Feld
    „Zusammenfassung“), Kommandozeile und Webserver nach der Rechnung
    zeigen; res.info['situation'] zeigen sie nicht."""
    for z in res.summary().splitlines():
        kopf, _, wert = z.partition(":")
        if kopf.strip() == "Situation":
            return wert.strip()
    return None


def test_einzelner_lastfall_in_seiner_situation():
    """„Nur aktiver Lastfall“ (Oberflaeche), ``--analyse lastfall`` (cli) und
    der Webserver rufen solve_static. Das baute sein System bis zum 23.09.2026
    ohne die Situation des Lastfalls und rechnete ihn still in der
    Grundstellung (Befund B123; Winkelrahmen mit abgebauter Stuetze uz in
    Kragarmmitte -0,2470 statt -3,5971 mm wie solve_cases)."""
    m, ids, sec = _balken_mit_rolle()
    n1 = ids[1]
    EI = E * sec.Iy
    check("Modellpruefung ohne Beanstandung", not m.check(), str(m.check()))
    rs = solver.solve_static(m, case="LF-S")
    close("Lastfall in seiner Situation: Rolle abgebaut -> Kragarm w = PL³/3EI",
          rs.u[n1, 2], -F * L ** 3 / (3 * EI), 1e-9, "m")
    rc = solver.solve_cases(m, ["LF-S"])["LF-S"]
    check("bitgleich mit solve_cases (Verschiebungen und Lagerkraefte)",
          np.array_equal(rs.u, rc.u) and np.array_equal(rs.reactions, rc.reactions),
          f"{rs.u[n1, 2]:.9e} gegen {rc.u[n1, 2]:.9e}")
    check("Ergebnis nennt seine Situation", rs.info.get("situation") == "offen",
          str(rs.info.get("situation")))
    # Was der Anwender nach der Rechnung liest, ist die Zusammenfassung. Am
    # Stand b118805 stand die Situation nur in info, das Benutzerhandbuch
    # sagte aber „das Ergebnis nennt die Situation“ (Gegenpruefung 24.09.2026)
    check("die Zusammenfassung nennt die Situation", _situation_in_zusammenfassung(rs) == "offen",
          str(_situation_in_zusammenfassung(rs)))
    # aktiver Lastfall wie in der Oberflaeche: solve_static(model, progress)
    m.active_case = "LF-S"
    zeilen: list = []
    ra = solver.solve_static(m, lambda text, *a: zeilen.append(str(text)))
    check("aktiver Lastfall ebenso in seiner Situation", np.array_equal(ra.u, rc.u),
          f"{ra.u[n1, 2]:.9e} gegen {rc.u[n1, 2]:.9e}")
    # die Zeile, die das Benutzerhandbuch nennt, wortgleich
    check("der Fortschritt hat die Zeile „System gelöst – Situation offen“",
          "System gelöst – Situation offen" in zeilen, str(zeilen[-3:]))
    check("... und die Zusammenfassung des aktiven Lastfalls die Situation",
          _situation_in_zusammenfassung(ra) == "offen", str(_situation_in_zusammenfassung(ra)))
    r1 = solver.solve_static(m, case="LF1")
    close("Lastfall der Grundstellung unveraendert: eingespannt-gestuetzt w = 7PL³/96EI",
          r1.u[n1, 2], -7 * F * L ** 3 / (96 * EI), 1e-9, "m")
    check("Grundstellung: keine Zeile „Situation“ in der Zusammenfassung",
          _situation_in_zusammenfassung(r1) is None, str(_situation_in_zusammenfassung(r1)))
    try:
        solver.solve_static(m, case="all")
        check("alle Lastfaelle ueber zwei Situationen werden abgewiesen", False, "lief durch")
    except ValueError as ex:
        check("alle Lastfaelle ueber zwei Situationen werden abgewiesen",
              GRUNDSTELLUNG in str(ex) and "offen" in str(ex), str(ex))
    del m.load_cases["LF1"]
    m.active_case = "LF-S"
    rl = solver.solve_static(m, case="all")
    check("alle Lastfaelle einer Situation: in dieser Situation",
          np.array_equal(rl.u, rc.u) and rl.info.get("situation") == "offen",
          f"{rl.u[n1, 2]:.9e} {rl.info.get('situation')}")


def test_knicken_in_seiner_situation():
    """solve_buckling baute sein System ebenso ohne Situation: Grundzustand,
    Steifigkeit und geometrische Steifigkeit stammten aus der Grundstellung.
    Gerechnet gegen die Eulerfaelle einer Stuetze laengs x (acht Elemente,
    schubstarr): Kopf seitlich gehalten (eingespannt-gelenkig, (kL)² =
    20,1907) oder in der Situation frei (Kragstuetze, π²/4)."""
    m, ids, sec = _balken(8, L)
    kopf = ids[-1]
    I = min(sec.Iy, sec.Iz)
    P = 1.0e3
    m.supports.append(Support(node=kopf, dofs=[1, 2], name="Kopf"))
    m.stellungen.append(Stellung("frei", 0.0, "Kopf frei", lager_aus=["Kopf"]))
    m.situationen["frei"] = Situation("frei", "frei")
    for lf in ("D", "D-frei"):
        m.add_load_case(lf, "G")
        m.load_node(kopf, Fx=-P, case=lf)
    m.load_cases["D-frei"].situation = "frei"
    m.combinations["K"] = Combination("K", {"D-frei": 1.5}, "ULS", situation="frei")
    check("Modellpruefung ohne Beanstandung", not m.check(), str(m.check()))
    rg = solver.solve_buckling(m, 2, case="D")
    close("Grundstellung: eingespannt-gelenkig N_cr = 20,1907 EI/L²",
          rg.buckling_factors[0] * P, 4.4934094579 ** 2 * E * I / L ** 2, 1e-3, "N")
    check("Grundstellung: keine Zeile „Situation“ in der Zusammenfassung",
          _situation_in_zusammenfassung(rg) is None, str(_situation_in_zusammenfassung(rg)))
    # wie in der Oberflaeche: mit Fortschritt, danach die Zusammenfassung
    zeilen: list = []
    rk = solver.solve_buckling(m, 2, lambda text, *a: zeilen.append(str(text)), case="D-frei")
    close("Lastfall in der Situation: Kragstuetze N_cr = π²EI/(2L)²",
          rk.buckling_factors[0] * P, math.pi ** 2 * E * I / (2 * L) ** 2, 1e-4, "N")
    check("Knickergebnis nennt seine Situation", rk.info.get("situation") == "frei",
          str(rk.info.get("situation")))
    # Das Benutzerhandbuch sagt, wo die Zeile steht: beim Knicken vor
    # „Verzweigungsproblem wird gelöst“, nicht am Schluss
    gl = "System gelöst – Situation frei"
    vz = "Verzweigungsproblem wird gelöst"
    check("Knicken: „System gelöst – Situation frei“ vor „Verzweigungsproblem …“",
          gl in zeilen and vz in zeilen and zeilen.index(gl) < zeilen.index(vz),
          str(zeilen[-3:]))
    check("Knicken: die Zusammenfassung nennt die Situation",
          _situation_in_zusammenfassung(rk) == "frei", str(_situation_in_zusammenfassung(rk)))
    rc = solver.solve_buckling(m, 2, combination="K")
    close("Kombination in der Situation: 1,5 · P gegen π²EI/(2L)²",
          rc.buckling_factors[0] * 1.5 * P, math.pi ** 2 * E * I / (2 * L) ** 2, 1e-4, "N")
    check("Kombination: die Zusammenfassung nennt die Situation",
          _situation_in_zusammenfassung(rc) == "frei", str(_situation_in_zusammenfassung(rc)))
    # Abgeschaltete Elemente: die aeussere Haelfte eines Stabes 2L wirkt in
    # der Situation nicht; ihre Knoten ausser dem ersten haben kein wirksames
    # Element und werden festgehalten. Ginge sie mit ihrer Verformung in die
    # geometrische Steifigkeit ein, bekaeme ihr erstes Element (Laenge L/4)
    # die ganze Verkuerzung der Stuetze als Dehnung: N = +4P = +4000 N, das
    # naechste 0 N. Gemessen 24.09.2026 (system.aktiv bei geometric_stiffness
    # weggelassen, sechs Faktoren): [-59,798; -239,192; 10850,028; 27039,519;
    # ...] statt [959,576; 3838,305; ...] - der betragskleinste wird negativ, und
    # darum faellt die Pruefung unten durch (-5,98e4 statt 9,595e5 N); der
    # kleinste positive steigt von 959,5 auf 10850.
    m2, ids2, sec2 = _balken(8, 2 * L)
    m2.situationen["kurz"] = Situation("kurz", "", [4, 5, 6, 7], "aeussere Haelfte aus")
    m2.add_load_case("D", "G")
    m2.load_node(ids2[4], Fx=-P, case="D")
    m2.load_cases["D"].situation = "kurz"
    r2 = solver.solve_buckling(m2, 2, case="D")
    close("abgeschaltete Haelfte: Kragstuetze der Laenge L, N_cr = π²EI/(2L)²",
          r2.buckling_factors[0] * P, math.pi ** 2 * E * min(sec2.Iy, sec2.Iz) / (2 * L) ** 2,
          1e-4, "N")


def test_abgeschalteter_stab_in_jeder_situation():
    """Member.aus (RFEM deaktiviert) wirkt in der Grundstellung und in jeder
    Situation: kein Beitrag, keine Last, Knoten festgehalten."""
    m, ids, sec = _balken(2)
    n0, n1, n2 = ids
    EI = E * sec.Iy
    # ein loser, ungelagerter Stab daneben - abgeschaltet
    k0 = m.add_node(0.0, 1.0, 0.0)
    k1 = m.add_node(1.0, 1.0, 0.0)
    e_los = m.add_element("beam", [k0, k1], "S", "R")
    m.add_member("los", [e_los], aus=True)
    m.add_load_case("LF1", "G")
    m.load_node(n1, Fz=-F, case="LF1")
    m.load_node(k1, Fz=-F, case="LF1")                # Last auf dem abgeschalteten Stab
    check("grundmaske nennt genau das Element des abgeschalteten Stabs",
          m.grundmaske() is not None and list(np.flatnonzero(~m.grundmaske())) == [e_los])
    check("aktive_elemente() ohne Situation traegt die Grundmaske", not m.aktive_elemente()[e_los])
    check("Modellpruefung ohne Beanstandung", not m.check(), str(m.check()))
    an = solver.solve_all(m)
    r = an.cases["LF1"]
    close("der Kragarm rechnet wie ohne den losen Stab: am Lastpunkt w = PL³/3EI", r.u[n1, 2],
          -F * L ** 3 / (3 * EI), 1e-9, "m")
    check("die Knoten des abgeschalteten Stabs bleiben in Ruhe, seine Last traegt nichts",
          np.allclose(r.u[k0], 0.0) and np.allclose(r.u[k1], 0.0) and r.info.get("inaktiv") == [e_los])


def main():
    for t in (test_abgeschalteter_stab_in_jeder_situation, test_abgeschaltete_elemente, test_stellung, test_stellung_lage_und_wirkung,
              test_speichern, test_subsystem, test_kombinationen_je_situation,
              test_einzelner_lastfall_in_seiner_situation, test_knicken_in_seiner_situation):
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
