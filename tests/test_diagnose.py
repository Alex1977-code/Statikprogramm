"""
Rechenbarkeit: Teiltragwerke ohne Lager, unvernetzte Geometrie, Kontakt-
gehaltene Teile - Diagnose, Modellpruefung und die Meldung des Solvers.
Aufruf:  python -m tests.test_diagnose
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche, Kopplung, ContactSupport  # noqa: E402
from statik3d import diagnose as dg, solver  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def _fenster(n, gemessen, anteil=0.10):
    """Elementzahl eines frei vernetzten Netzes im Fenster ±anteil um den
    gemessenen Wert. Die Zahl haengt am Vernetzer und ist nicht die Aussage
    der Pruefung (Hinweis der Vernetzer-Sitzung, 24.09.2026: nach jedem
    Vernetzer-Stand rissen sonst Pruefungen, deren Befund gleich blieb).

    Warum ±10 % und nicht ±5 %: schon eine andere Phase des eigenen
    BCC-Gitters (mesher3d.bcc_gitter, Versatz um 0,125 bis 0,875·h
    verschoben) streut die Zahlen um -7,2 bis +0,8 % (Wuerfel 1018 bis 1088
    gegen 1091, L-Prisma h 0,25 592 bis 639 gegen 634, h 0,12 5810 bis 6202
    gegen 6155, T-Prisma 5465 bis 5862 gegen 5886; die Bezugswerte liegen am
    oberen Rand). Mit ±5 % rissen daran vier von sieben Phasen am T-Prisma.
    Echte Aenderungen bleiben draussen: doppelte Dichte (h·0,79) +85 bis
    +120 %, h·1,26 -50 bis -57 %, das L-Netz mit Luecke (821) +29,5 %.
    Gemessen 24.09.2026, zweimal (Gegenpruefung und Nachbesserung)."""
    return abs(n - gemessen) <= anteil * gemessen


def _zwei_teile(lager_b=False):
    """Zwei Kragarme: Teil A (K0-K1) gelagert, Teil B (K2-K3) frei."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    n = [m.add_node(0, 0, 0), m.add_node(2, 0, 0), m.add_node(0, 3, 0), m.add_node(2, 3, 0)]
    m.add_element("beam", [n[0], n[1]], "S235", "IPE 200")
    m.add_element("beam", [n[2], n[3]], "S235", "IPE 200")
    m.fix(n[0], "all")
    if lager_b:
        m.fix(n[2], "all")
    m.case()
    m.load_node(n[1], Fz=-1000.0)
    m.load_node(n[3], Fz=-1000.0)
    return m, n


def _teiltragwerke_langsam(model) -> list:
    """Die Vereinigungs-Suche in Python (Stand bis 12.09.2026) als Vergleich."""
    nn = model.nn
    eltern = list(range(nn))

    def finde(a):
        while eltern[a] != a:
            eltern[a] = eltern[eltern[a]]
            a = eltern[a]
        return a
    belegt = [False] * nn
    for e in model.elements:
        kn = [int(k) for k in e.nodes if 0 <= int(k) < nn]
        for k in kn:
            belegt[k] = True
        for k in kn[1:]:
            ra, rb = finde(kn[0]), finde(k)
            if ra != rb:
                eltern[rb] = ra
    for kp in getattr(model, "kopplungen", []) or []:
        a, b = int(getattr(kp, "node_a", -1)), int(getattr(kp, "node_b", -1))
        if 0 <= a < nn and 0 <= b < nn:
            ra, rb = finde(a), finde(b)
            if ra != rb:
                eltern[rb] = ra
    gruppen = {}
    for k in range(nn):
        if belegt[k]:
            gruppen.setdefault(finde(k), []).append(k)
    return sorted(gruppen.values(), key=lambda g: (-len(g), g[0]))


def test_teiltragwerke():
    m, n = _zwei_teile()
    teile = dg.teiltragwerke(m)
    check("zwei Teiltragwerke, je zwei Knoten", len(teile) == 2 and sorted(len(g) for g in teile) == [2, 2])
    # vektorisiert (csgraph) = Vereinigungs-Suche, auch mit Kopplung und an groesseren Netzen
    from statik3d.examples_lib import build_example
    check("Teiltragwerke vektorisiert = Vereinigungs-Suche (zwei Teile)",
          dg.teiltragwerke(m) == _teiltragwerke_langsam(m))
    m.kopplungen.append(Kopplung(n[1], n[3], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e9, 1e9, 1e9]))
    check("… mit Kopplung ein Teil, gleich", dg.teiltragwerke(m) == _teiltragwerke_langsam(m)
          and len(dg.teiltragwerke(m)) == 1)
    m.kopplungen.clear()
    for name in ("hall", "friction", "contact"):
        mx = build_example(name)
        a, b = dg.teiltragwerke(mx), _teiltragwerke_langsam(mx)
        check(f"… Beispiel {name}: gleiche Teile ({len(a)})", a == b, f"{len(a)} / {len(b)}")
    d = dg.diagnose(m)
    check("Teil B ohne Lager erkannt, nicht rechenbar", len(d["ohne_lager"]) == 1 and sorted(d["ohne_lager"][0]) == [n[2], n[3]]
          and not d["rechenbar"] and d["lose_knoten"] == 0)
    z = dg.meldungen(m, d)
    check("Meldung FEHLER mit Knoten und Teilezahl", any(x.startswith("FEHLER") and "K2" in x and "2 Teile" in x for x in z), str(z))
    check("Modellprüfung nennt das Teiltragwerk als FEHLER", any("Teiltragwerk" in x and x.startswith("FEHLER") for x in m.check()))
    # Kopplung verbindet die Teile
    m.kopplungen.append(Kopplung(n[1], n[3], [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e9, 1e9, 1e9]))
    d = dg.diagnose(m)
    check("Kopplung verbindet: ein Teil, rechenbar", d["teile"] == 1 and d["rechenbar"], str(d["teile"]))
    m.kopplungen.clear()
    # einseitiges Lager haelt Teil B nur ueber Kontakt
    m.contact_supports.append(ContactSupport(n[2], [0, 0, 1.0]))
    d = dg.diagnose(m)
    check("einseitiges Lager: Teil nur durch Kontakt gehalten (Hinweis, kein FEHLER)",
          not d["ohne_lager"] and len(d["nur_kontakt"]) == 1 and d["rechenbar"]
          and not any(x.startswith("FEHLER") for x in m.check()), str(m.check()))
    m.contact_supports.clear()
    # mit Lager an B alles in Ordnung
    m2, _ = _zwei_teile(lager_b=True)
    d2 = dg.diagnose(m2)
    check("beide Teile gelagert: rechenbar, keine Beanstandung", d2["rechenbar"] and not any(
        x.startswith("FEHLER") for x in m2.check()), str(m2.check()))


def test_unvernetzt():
    m, n = _zwei_teile(lager_b=True)
    m.add_shell_prop(ShellProp("t", 0.01))
    m.flaechen["F1"] = Flaeche("F1", dicke="t", material="S235", elemente=[])
    d = dg.diagnose(m)
    check("Fläche ohne Netz erkannt", d["unvernetzte_flaechen"] == ["F1"])
    check("Modellprüfung: WARNUNG „ohne Netz“, kein FEHLER", any("ohne Netz" in x and x.startswith("WARNUNG") for x in m.check())
          and not any(x.startswith("FEHLER") for x in m.check()), str(m.check()))


def test_solver_meldung():
    m, n = _zwei_teile()
    try:
        solver.solve_static(m)
        # SuperLU faktorisiert eine numerisch singulaere Matrix manchmal dennoch;
        # dann liefert die Modellpruefung die Meldung (vor dem Rechnen in der GUI)
        check("Solver oder Modellprüfung nennen das Teiltragwerk ohne Lager",
              any("Teiltragwerk" in x for x in m.check()))
    except RuntimeError as ex:
        check("Solver-Meldung erklärt das singuläre System (Teiltragwerk ohne Lager)",
              "Teiltragwerk" in str(ex) and "singulär" in str(ex), str(ex)[:120])
    text = dg.singulaer_text(m, "Factor is exactly singular")
    check("singulaer_text: Kopf, Ursache und Anweisung",
          text.startswith("Gleichungssystem singulär") and "Factor is exactly singular" in text
          and "Lager setzen" in text, text[:100])
    m2, _ = _zwei_teile(lager_b=True)
    text2 = dg.singulaer_text(m2)
    check("ohne topologischen Befund: Hinweis auf Gelenke/Nullsteifigkeit", "Gelenke" in text2)


def _koerper_ohne_netz(netzgrund: str, flach: bool = False):
    """Ein gelagerter Wuerfel und daneben ein Koerper ohne Elemente."""
    from statik3d.model import OHNE_NETZ
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]]))
    m.add_element("hex8", list(range(8)), "S235", group="A")
    for i in range(4):
        m.fix(i, [0, 1, 2])
    n0 = m.nn
    ecken = ([(5, 0, 0), (6, 0, 0), (5, 1, 0), (6, 1, 0)] if flach
             else [(5, 0, 0), (6, 0, 0), (5, 1, 0), (5, 0, 1)])
    for pkt in ecken:
        m.add_node(*pkt)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]):
        m.add_line(f"L{i}", [n0 + a, n0 + b])
    for nm, ls in [("A1", ["L0", "L1", "L2"]), ("A2", ["L0", "L4", "L3"]),
                   ("A3", ["L1", "L5", "L4"]), ("A4", ["L2", "L3", "L5"])]:
        m.add_flaeche(nm, ls, material="S235")
    k = m.add_koerper("V5", ["A1", "A2", "A3", "A4"], material="S235")
    if netzgrund:
        k.kommentar = f"{OHNE_NETZ} die Randhülle ist nicht dicht (3 offene Kanten)"
        k.netzgrund = netzgrund
    return m


def test_koerper_ohne_netz_haelt_an():
    """Ein tragendes Bauteil ohne Elemente darf nicht stillschweigend fehlen.

    Der Vernetzer haelt sein Scheitern im Kommentar fest. Bisher schloss
    ``koerper_traegt`` bei **jedem** Vermerk „ohne Netz" kurz - auch bei
    diesem. Der Koerper galt damit als Hilfsobjekt, verschwand aus der
    Pruefung, und gerechnet wurde ohne ihn. Am Drehlagermodell war das V5,
    mit echtem Werkstoff und 13 Randflaechen.

    Unterschieden wird jetzt am Grund: nur „kein_volumen" heisst, dass es
    kein Netz geben **kann**.
    """
    m = _koerper_ohne_netz("gescheitert")
    d = dg.diagnose(m)
    check("ein gescheiterter Körper zählt nicht als Hilfsobjekt",
          d["koerper_ohne_volumen"] == [], str(d["koerper_ohne_volumen"]))
    check("er steht als gescheitert da, mit dem Grund des Vernetzers",
          [n for n, _g in d["koerper_gescheitert"]] == ["V5"]
          and "nicht dicht" in d["koerper_gescheitert"][0][1],
          str(d["koerper_gescheitert"]))
    check("und wird nicht ein zweites Mal zum Vernetzen angeboten",
          d["unvernetzte_koerper"] == [], str(d["unvernetzte_koerper"]))
    fehler = [z for z in dg.meldungen(m, d) if z.startswith("FEHLER")]
    check("die Meldung ist ein FEHLER und nennt Bauteil und Grund",
          any("V5" in z and "nicht dicht" in z for z in fehler),
          (fehler[0][:110] if fehler else "keine"))
    check("und sie steht in der Modellprüfung",
          any(z.startswith("FEHLER") and "V5" in z for z in m.check()),
          str([z[:60] for z in m.check() if z.startswith("FEHLER")]))

    # Gegenprobe: das flache Hilfsobjekt bleibt ein Hinweis
    m2 = _koerper_ohne_netz("kein_volumen", flach=True)
    d2 = dg.diagnose(m2)
    check("ein Körper ohne Rauminhalt bleibt Hilfsobjekt",
          d2["koerper_ohne_volumen"] == ["V5"] and d2["koerper_gescheitert"] == [],
          f"{d2['koerper_ohne_volumen']} / {d2['koerper_gescheitert']}")
    check("und erzeugt keinen FEHLER",
          not any("V5" in z for z in dg.meldungen(m2, d2) if z.startswith("FEHLER")))

    # Gegenprobe: noch gar nicht versucht -> vernetzen anbieten, kein FEHLER
    m3 = _koerper_ohne_netz("")
    d3 = dg.diagnose(m3)
    check("ein noch nicht vernetzter Körper wird zum Vernetzen angeboten",
          d3["unvernetzte_koerper"] == ["V5"] and d3["koerper_gescheitert"] == [],
          f"{d3['unvernetzte_koerper']} / {d3['koerper_gescheitert']}")

    # Der Grund muss Speichern und Laden ueberstehen
    import json
    m4 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("netzgrund übersteht Speichern und Laden",
          getattr(m4.koerper["V5"], "netzgrund", "") == "gescheitert",
          repr(getattr(m4.koerper["V5"], "netzgrund", None)))


def test_meldung_nennt_ursache_und_kanten():
    """Die Meldung soll die Ursache nennen, nicht das naechstliegende Mittel.

    Zwei Befunde aus dem Lauf 09.09. 19:43 am Drehlagermodell:

    * „12 Teiltragwerke ohne Lager" war die **Folge** davon, dass V31, V34
      und V108-V110 ohne Netz blieben. Auf dem alten, vollstaendig vernetzten
      Modell gab es die Meldung gar nicht. „Lager setzen" waere darum der
      falsche Rat gewesen - die Koerper ohne Netz gehoeren genannt.
    * Der Fehlertext nannte nur die **Zahl** der offenen Kanten. Das
      Protokoll hatte die Kanten laengst mit Koordinaten und Randflaechen;
      sie gehoeren dorthin, wo der Anwender hinsieht.
    """
    from statik3d.model import OHNE_NETZ
    m = _koerper_ohne_netz("gescheitert")
    kante = ("    Kante 6-624 in 1 Dreieck(en), Flächen F267: "
             "(0.6800 | 0.0200 | -0.0500) - (0.6800 | 0.0467 | -0.0500)")
    m.koerper["V5"].netzkanten = [kante]
    # Ein zweites, ungelagertes Bauteil - es haengt nur ueber V5 am System
    n0 = m.nn
    for pkt in [(9, 0, 0), (10, 0, 0), (10, 1, 0), (9, 1, 0),
                (9, 0, 1), (10, 0, 1), (10, 1, 1), (9, 1, 1.)]:
        m.add_node(*pkt)
    m.add_element("hex8", list(range(n0, n0 + 8)), "S235", group="B")
    d = dg.diagnose(m)
    z = dg.meldungen(m, d)
    lose = [x for x in z if "ohne Lager" in x]
    check("es gibt die Meldung über die losen Teile", len(lose) == 1,
          lose[0][:80] if lose else "keine")
    check("sie nennt den Körper ohne Netz als Ursache",
          "V5" in lose[0] and "Folge" in lose[0], lose[0][-140:] if lose else "-")
    check("und empfiehlt nicht mehr, Lager zu setzen",
          "Lager setzen" not in lose[0])
    check("die offenen Kanten stehen im Fehlertext, mit Koordinaten und Fläche",
          kante in z, f"{len([x for x in z if x.startswith('    Kante')])} Kantenzeilen")

    # Gegenprobe: ohne gescheiterten Koerper bleibt der alte Rat stehen
    m2 = _koerper_ohne_netz("")
    m2.koerper.pop("V5", None)
    n0 = m2.nn
    for pkt in [(9, 0, 0), (10, 0, 0), (10, 1, 0), (9, 1, 0),
                (9, 0, 1), (10, 0, 1), (10, 1, 1), (9, 1, 1.)]:
        m2.add_node(*pkt)
    m2.add_element("hex8", list(range(n0, n0 + 8)), "S235", group="B")
    lose2 = [x for x in dg.meldungen(m2) if "ohne Lager" in x]
    check("ohne unvernetzten Körper heißt es weiter „Lager setzen“",
          len(lose2) == 1 and "Lager setzen" in lose2[0],
          lose2[0][-90:] if lose2 else "keine")
    import json
    m3 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("netzkanten überstehen Speichern und Laden",
          list(getattr(m3.koerper["V5"], "netzkanten", [])) == [kante],
          repr(getattr(m3.koerper["V5"], "netzkanten", None))[:80])
    check("und der Kommentar bleibt der des Vernetzers",
          str(m3.koerper["V5"].kommentar).startswith(OHNE_NETZ))


def _wuerfelpaar():
    """Zwei Hexaeder uebereinander, die sich die Trennflaeche teilen."""
    m = Model()
    m.add_material(Material.steel("S235"))
    U = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    m.add_nodes(np.vstack([U, U[4:] + [0, 0, 1.0]]))
    m.add_element("hex8", list(range(8)), "S235", group="Unten")
    m.add_element("hex8", [4, 5, 6, 7, 8, 9, 10, 11], "S235", group="Oben")
    for k in range(4):
        m.fix(k, "all")
    m.case()
    return m


def test_abnahme():
    """Die Abnahme des Netzes vor dem Rechnen - jede Verletzung mit Namen.

    Ein Bauteil ist vollstaendig angebunden, oder es ist ein Fehler mit Namen.
    Geprueft wird jede der Pruefungen einzeln an einem Fall, dessen Antwort
    von Hand feststeht.
    """
    # 1) Ein Element, das eine ausgefuehrte Fuge ueberbrueckt
    m = _wuerfelpaar()
    check("ein sauberes Netz besteht die Abnahme", not dg.abnahme(m),
          "; ".join(b.text[:60] for b in dg.abnahme(m)))
    # Knoten 4 wurde getrennt (die Nummer 12 ist seine neue Haelfte); das
    # obere Element benutzt beide -> es ueberbrueckt die Trennung
    neu_k = int(m.add_node(*m.nodes[4]))
    m.getrennte_knoten = {"Fuge": [[4, neu_k]]}
    m.elements[1].nodes = [4, 5, 6, 7, 8, 9, 10, neu_k]
    b = [x for x in dg.abnahme(m) if x.pruefung == "Fuge überbrückt"]
    check("ein Element mit beiden Seiten der Fuge wird gefunden",
          len(b) == 1 and b[0].element == 1 and sorted(b[0].knoten) == sorted([4, neu_k]),
          str([(x.element, x.knoten) for x in b]))
    check("und der Text nennt Element, Knoten und Fuge",
          "Element 1" in b[0].text and f"{neu_k}" in b[0].text and "Fuge" in b[0].text,
          b[0].text[:110])
    m.elements[1].nodes = [4, 5, 6, 7, 8, 9, 10, 11]
    check("ohne dieses Element ist die Fuge sauber",
          not [x for x in dg.abnahme(m) if x.pruefung == "Fuge überbrückt"], "")

    # 2) Abdeckung der Kontaktseite
    from statik3d.model import ContactPair
    m2 = _wuerfelpaar()
    m2.contact_pairs.append(ContactPair("Fuge", slave_nodes=[8], master_faces=[[4, 5, 6, 7]],
                                        abdeckung=0.55))
    b2 = [x for x in dg.abnahme(m2) if x.pruefung == "Abdeckung der Kontaktseite"]
    check("eine Fuge mit 55 % Abdeckung reißt die Grenze",
          len(b2) == 1 and abs(b2[0].wert - 0.55) < 1e-12
          and abs(b2[0].grenze - dg.ABNAHME_ABDECKUNG) < 1e-12,
          b2[0].text[:110] if b2 else "kein Befund")
    m2.contact_pairs[-1].abdeckung = 0.99
    check("mit 99 % nicht",
          not [x for x in dg.abnahme(m2) if x.pruefung == "Abdeckung der Kontaktseite"], "")

    # 3) Ein Gegenkoerper, der keine Facette gestellt hat
    m3 = _wuerfelpaar()
    m3.add_kontaktbedingung("Fuge", flaechennamen=[], koerpernamen=["Oben"],
                            gegenkoerper=["Unten"])
    m3.contact_pairs.append(ContactPair("Fuge", slave_nodes=[8], master_faces=[[4, 5, 6, 7]],
                                        abdeckung=1.0, gegenkoerper=[]))
    b3 = [x for x in dg.abnahme(m3) if x.pruefung == "Gegenkörper ohne Facette"]
    check("ein genannter Gegenkörper ohne Facette ist ein Fehler mit Namen",
          len(b3) == 1 and "Unten" in b3[0].text, b3[0].text[:110] if b3 else "kein Befund")
    m3.contact_pairs[-1].gegenkoerper = ["Unten"]
    check("hat er Facetten gestellt, ist es keiner",
          not [x for x in dg.abnahme(m3) if x.pruefung == "Gegenkörper ohne Facette"], "")
    # Er trägt auch, wenn er die **Knotenseite** stellt statt der Facetten: an
    # einer gemeinsamen Fläche steht in koerpernamen/gegenkoerper nicht
    # zwingend dieselbe Rolle wie in den Flächenlisten. Am Drehlager nannte
    # V29–V34 die Flächen von V34 als Kontaktseite, die Facetten kamen von
    # V29 - die Fuge deckte 100 % ab und trug, die Abnahme meldete trotzdem
    # einen Mangel (18.09.2026)
    m5 = _wuerfelpaar()
    m5.add_kontaktbedingung("Fuge", flaechennamen=[], koerpernamen=["Oben"],
                            gegenkoerper=["Unten"])
    slave = [int(n) for n in m5.elements[0].nodes[:2]]
    m5.contact_pairs.append(ContactPair("Fuge", slave_nodes=slave, master_faces=[[4, 5, 6, 7]],
                                        abdeckung=1.0, gegenkoerper=["Oben"]))
    gruppe = str(getattr(m5.elements[0], "group", "") or "")
    m5.kontaktbedingungen["Fuge"].gegenkoerper = [gruppe]
    check("der genannte Gegenkörper stellt die Knoten statt der Facetten: kein Mangel",
          not [x for x in dg.abnahme(m5) if x.pruefung == "Gegenkörper ohne Facette"],
          f"Knoten aus {gruppe}")
    m5.kontaktbedingungen["Fuge"].gegenkoerper = ["gibt es nicht"]
    check("ein Bauteil, das weder Facette noch Knoten stellt, bleibt ein Mangel",
          len([x for x in dg.abnahme(m5) if x.pruefung == "Gegenkörper ohne Facette"]) == 1)

    # 4) Knoten ohne Element und Randtreue
    m4 = _wuerfelpaar()
    lose = int(m4.add_node(5.0, 5.0, 5.0))
    b4 = [x for x in dg.abnahme(m4) if x.pruefung == "Knoten ohne Element"]
    check("ein Knoten ohne Element wird gezählt und genannt",
          len(b4) == 1 and lose in b4[0].knoten and abs(b4[0].wert - 1.0) < 1e-12,
          b4[0].text[:110] if b4 else "kein Befund")
    from statik3d.model import Volumenkoerper
    m5 = _wuerfelpaar()
    m5.koerper["V1"] = Volumenkoerper("V1", elemente=[0], randtreue=0.90)
    b5 = [x for x in dg.abnahme(m5) if x.pruefung == "Randtreue"]
    check("eine Randtreue von 90 % reißt die Grenze 99 %",
          len(b5) == 1 and abs(b5[0].wert - 0.90) < 1e-12
          and abs(b5[0].grenze - dg.ABNAHME_RANDTREUE) < 1e-12,
          b5[0].text[:110] if b5 else "kein Befund")
    m5.koerper["V1"].randtreue = 0.999
    check("eine von 99,9 % nicht",
          not [x for x in dg.abnahme(m5) if x.pruefung == "Randtreue"], "")


def test_abnahme_an_der_echten_fuge():
    """Nach dem Ausfuehren einer echten Fuge ueberbrueckt kein Element sie.

    Das ist die Zusage des Vernetzers und der Fugenausfuehrung zusammen: die
    Randknoten werden verdoppelt **und** alle Elemente der geloesten Seite
    umgehaengt. Bliebe eines mit einem Fuss auf der alten Seite, waere die
    Fuge dort wirkungslos - von aussen sieht man das als „halb vernetzt".
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from test_fugen import zwei_bloecke
    from statik3d.model import DofBehaviour
    from statik3d import fugen
    m = zwei_bloecke("eigene", h=0.25)
    kb = m.add_kontaktbedingung(
        "Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"], koerpernamen=["Oben"],
        behaviour={2: DofBehaviour("free", failure="zug")})
    bericht = fugen.kontaktfuge_ausfuehren(m, kb, [])
    paare = m.getrennte_knoten.get("Fuge", [])
    check("die Fuge hat Randknoten getrennt und es steht am Modell",
          len(paare) == bericht["knoten"] > 0,
          f"{len(paare)} Paare, Bericht {bericht['knoten']}")
    b = [x for x in dg.abnahme(m) if x.pruefung == "Fuge überbrückt"]
    check("und kein einziges Element benutzt beide Seiten", not b,
          "; ".join(x.text[:60] for x in b))


def test_schliesstest_mit_oeffnungsringen():
    """Eine Huelle ist dicht, wenn jede Randlinie zu genau zwei Raendern gehoert.

    **Die Oeffnungsringe zaehlen mit.** Wer sie vergisst, haelt die Haelfte der
    Koerper fuer kaputt: am Drehlagermodell melden 26 der 108 Koerper offene
    Kanten ohne die Innenraender (V33 allein 118) und keiner einzige mit
    ihnen. Hier derselbe Fall in klein: ein Quader mit einem Durchbruch, der
    beide Deckflaechen durchsetzt.
    """
    from statik3d.model import Volumenkoerper, Line
    m = Model()
    m.add_material(Material.steel("S235"))
    # Ein Quader: 6 Flaechen, 12 Kanten. Oben und unten je ein Loch aus vier
    # Linien, dazwischen vier Wandflaechen des Durchbruchs.
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                                (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]):
        m.lines[f"K{i}"] = Line(f"K{i}", [a, b])
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
                                (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]):
        m.lines[f"D{i}"] = Line(f"D{i}", [a, b])       # Linien des Durchbruchs
    aussen = {"unten": ["K0", "K1", "K2", "K3"], "oben": ["K4", "K5", "K6", "K7"],
              "w1": ["K0", "K9", "K4", "K8"], "w2": ["K1", "K10", "K5", "K9"],
              "w3": ["K2", "K11", "K6", "K10"], "w4": ["K3", "K8", "K7", "K11"]}
    for n, ls in aussen.items():
        m.flaechen[n] = Flaeche(n, ls)
    # Der Durchbruch: seine Wand aus vier Flaechen, oben und unten als Loch
    m.flaechen["unten"].oeffnungen = [["D0", "D1", "D2", "D3"]]
    m.flaechen["oben"].oeffnungen = [["D4", "D5", "D6", "D7"]]
    for i, ls in enumerate([["D0", "D9", "D4", "D8"], ["D1", "D10", "D5", "D9"],
                            ["D2", "D11", "D6", "D10"], ["D3", "D8", "D7", "D11"]]):
        m.flaechen[f"d{i}"] = Flaeche(f"d{i}", ls)
    m.koerper["V1"] = Volumenkoerper("V1", flaechen=list(aussen) + [f"d{i}" for i in range(4)])
    b = [x for x in dg._abnahme_huellen(m) if x.pruefung == "Hülle offen"]
    check("mit Öffnungsringen ist die Hülle dicht", not b,
          b[0].text[:110] if b else "")
    for f in m.flaechen.values():
        f.oeffnungen = []
    b2 = dg._abnahme_huellen(m)
    check("ohne sie hielte man denselben Körper für kaputt",
          len(b2) == 1 and abs(b2[0].wert - 8.0) < 1e-12,
          b2[0].text[:120] if b2 else "kein Befund")


def test_abnahme_meldet_ausgefallene_pruefungen():
    """Eine Prüfung, die gar nicht lief, darf nicht als „bestanden" gelten.

    Die Abnahme führt sechs Teilprüfungen. Zwei davon fingen eine Ausnahme
    stumm ab und gaben eine **leere Liste** zurück — und leer heißt in
    `abnahme()` ausdrücklich „das Netz ist abgenommen". Ein Modell, dessen
    Lagerung in einer Richtung fast nicht hält, wurde damit mit
    „--- Abnahme des Netzes: bestanden ---" quittiert.

    Schlimmer noch der Teilausfall: `restfreiheiten` füllt die Gütewerte je
    Teiltragwerk fortlaufend. Warf es beim 40. von 60, gingen auch die 39
    schon gemessenen Werte mit verloren.

    Und im ausnahmefreien Fall: ein `nan` ging als Formgüte 1,000 ein — ein
    Element, dessen Form sich nicht ermitteln ließ, galt als das formbeste
    überhaupt.
    """
    from statik3d import diagnose as _dg
    from statik3d import singular as _sg
    from statik3d.singular import Halteguete

    m, _n = _zwei_teile(lager_b=True)

    # ---- (a) die Halteguete faellt ganz aus
    echt = _sg.restfreiheiten

    def wirft(*a, **kw):
        raise RuntimeError("Eigenwertproblem nicht lösbar")

    _sg.restfreiheiten = wirft
    try:
        alle = _dg.abnahme(m, warnungen=True)
    finally:
        _sg.restfreiheiten = echt
    namen = [b.pruefung for b in alle]
    check("ein Ausfall der Haltegüte wird benannt",
          "Haltegüte nicht geprüft" in namen, str(namen))
    check("und zwar als Warnung, nicht als Verletzung",
          all(b.stufe == "WARNUNG" for b in alle
              if b.pruefung == "Haltegüte nicht geprüft"),
          str([(b.pruefung, b.stufe) for b in alle]))
    # Der Zusatz ist eine WARNUNG und darum nur dem Aufrufer mit
    # warnungen=True sichtbar - das wird gemessen, nicht behauptet.
    _sg.restfreiheiten = wirft
    try:
        ohne = _dg.abnahme(m, warnungen=False)
    finally:
        _sg.restfreiheiten = echt
    check("ohne warnungen=True hält der Zusatz die Rechnung nicht an",
          not any(str(b.pruefung).endswith("nicht geprüft") for b in ohne),
          str([b.pruefung for b in ohne]))

    # ---- (b) Teilausfall: was schon gemessen war, bleibt stehen
    def wirft_spaeter(model, guete=None, **kw):
        if guete is not None:
            guete.append(Halteguete(wert=8.5e-05, koerper=["Teil B"],
                                    knoten=[2], text="Teil B hält in x kaum"))
        raise RuntimeError("beim vierzigsten Teiltragwerk")

    _sg.restfreiheiten = wirft_spaeter
    try:
        alle2 = _dg.abnahme(m, warnungen=True)
    finally:
        _sg.restfreiheiten = echt
    namen2 = [b.pruefung for b in alle2]
    check("der schon gemessene Mangel überlebt den Teilausfall",
          "Haltegüte" in namen2 and "Haltegüte nicht geprüft" in namen2,
          str(namen2))

    # ---- (c) die Formguete faellt ganz aus
    from statik3d import netzguete as _ng
    echt_g = _ng.guete
    _ng.guete = wirft
    try:
        alle3 = _dg.abnahme(m, warnungen=True)
    finally:
        _ng.guete = echt_g
    check("ein Ausfall der Formgüte wird benannt",
          "Elementgüte nicht geprüft" in [b.pruefung for b in alle3],
          str([b.pruefung for b in alle3]))

    # ---- (d) ohne Ausfall bleibt alles, wie es war
    alle4 = _dg.abnahme(m, warnungen=True)
    check('ohne Ausfall steht kein „nicht geprüft“ da',
          not any(str(b.pruefung).endswith("nicht geprüft") for b in alle4),
          str([b.pruefung for b in alle4]))


def test_nicht_messbare_formguete_gilt_nicht_als_beste():
    """Ein `nan` in der Formgüte darf nicht als 1,000 durchgehen.

    Bis zum 22.09.2026 stand in der Splitterprüfung
    `q[j] if np.isfinite(q[j]) else 1.0`: ein Element, dessen Formgüte sich
    nicht ermitteln ließ, ging als das formbeste überhaupt ein. Jetzt zählt
    es gar nicht mit und erscheint stattdessen als „Elementgüte nicht
    geprüft" mit seiner Anzahl.
    """
    import numpy as _np
    from statik3d import diagnose as _dg
    from statik3d import netzguete as _ng
    from statik3d import mesher
    from statik3d.model import Material as _Mat, Model as _Mod, Volumenkoerper

    m = _Mod("guete")
    m.add_material(_Mat.steel("S235"))
    mesher.grid_box(m, "S235", 1.0, 1.0, 1.0, 2, 1, 1, typ="hex8")
    k = Volumenkoerper("K1", [])
    k.elemente = list(range(len(m.elements)))
    m.koerper["K1"] = k

    echt = _ng.guete

    def mit_nan(model):
        q = _np.ones(len(model.elements), float)
        q[0] = _np.nan               # nicht messbar
        q[1] = 0.04                  # echter Splitter
        return q

    _ng.guete = mit_nan
    try:
        alle = _dg.abnahme(m, warnungen=True)
    finally:
        _ng.guete = echt
    texte = {b.pruefung: b.text for b in alle}
    check("das nicht messbare Element wird gezählt und benannt",
          "Elementgüte nicht geprüft" in texte
          and "bei 1 die Formgüte" in texte["Elementgüte nicht geprüft"],
          texte.get("Elementgüte nicht geprüft", "keine Zeile")[:90])
    check("der echte Splitter wird gefunden",
          "Splitter" in texte and "1 von 1 Elementen" in texte["Splitter"],
          texte.get("Splitter", "keine Zeile")[:90])
    check('die Probe ist scharf: vorher hätte „1 von 2“ dagestanden',
          "1 von 2" not in texte.get("Splitter", ""),
          texte.get("Splitter", "-")[:90])


def _quaderkoerper(m, ecken, name="K1"):
    """Volumenkoerper aus sechs Randflaechen ueber acht vorhandenen Eckknoten
    (Reihenfolge wie hex8: Boden 0-3, Deckel 4-7), Kanten gerade."""
    kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]
    for i, (a, b) in enumerate(kanten):
        m.add_line(f"{name}L{i}", [int(ecken[a]), int(ecken[b])])
    seiten = {"Boden": [0, 1, 2, 3], "Deckel": [4, 5, 6, 7], "S1": [0, 9, 4, 8],
              "S2": [1, 10, 5, 9], "S3": [2, 11, 6, 10], "S4": [3, 8, 7, 11]}
    for s, ls in seiten.items():
        m.add_flaeche(f"{name}{s}", [f"{name}L{i}" for i in ls], material="S235")
    return m.add_koerper(name, [f"{name}{s}" for s in seiten], material="S235")


def test_abnahme_findet_verdrehten_sechsflaechner():
    """Ein verdrehter Sechsflächner ging durch jede Prüfung der Abnahme.

    Nachtrag A vom 22.09.2026: die acht Knoten stimmen, aber die Zuordnung
    Grundknoten -> Deckelknoten ist um eins verdreht (4,5,6,7 -> 5,6,7,4).
    Die Jacobi-Determinante ist überall positiv, die Formgüte 0,707 liegt
    weit über jeder Schranke - und das Element rechnet mit 0,6667 statt 1,0.
    Gemessen vor der Kur: ``abnahme(warnungen=True)`` gab ``[]`` zurück.

    Zwei Merkmale, beide gegen die **Randflächen** des Körpers gemessen und
    nicht gegen das Netz selbst: das Randvolumen der freien Elementseiten
    ist in bilinearer Darstellung mit der Jacobi-Summe identisch (gemessen
    1,6667 gegen 1,6667) und taugt darum nicht als Bezug.

    * **Volumenbilanz**: Summe der Elementvolumina 1,6667 gegen das Volumen
      der Hülle 2,0.
    * **Seiten im Inneren**: die verdrehte Zelle passt nicht mehr zu ihrer
      Nachbarin; deren Seite bei x = 1 und die vier verwundenen Seitenwände
      der verdrehten Zelle liegen im Inneren, nicht auf einer Randfläche.
      Steht eine freie Seite dagegen über die Randfläche hinaus, ist das eine
      Warnung („Netzrand neben der Hülle") und kein Fehler.
    """
    from statik3d import mesher

    def paar(verdreht):
        m = Model("na")
        m.add_material(Material.steel("S235"))
        ids = mesher.grid_box(m, "S235", 2.0, 1.0, 1.0, 2, 1, 1, typ="hex8")
        ecken = [ids[0, 0, 0], ids[2, 0, 0], ids[2, 1, 0], ids[0, 1, 0],
                 ids[0, 0, 1], ids[2, 0, 1], ids[2, 1, 1], ids[0, 1, 1]]
        k = _quaderkoerper(m, ecken)
        k.elemente = [0, 1]
        for kn in ids[0].ravel():
            m.fix(int(kn), "all")
        if verdreht:
            n = list(m.elements[1].nodes)
            m.elements[1].nodes = n[:4] + [n[5], n[6], n[7], n[4]]
        return m

    m = paar(True)
    bef = dg.abnahme(m)
    vb = [b for b in bef if b.pruefung == "Volumenbilanz"]
    check("verdrehter Sechsflächner: die Volumenbilanz reißt",
          len(vb) == 1 and vb[0].objekt == "K1" and abs(vb[0].wert - 1.0 / 6.0) < 1e-6
          and vb[0].stufe == "FEHLER",
          (vb[0].text[:110] if vb else "kein Befund"))
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("und die Seiten im Inneren werden gefunden, am verdrehten Element",
          len(sn) == 1 and sn[0].element == 1 and abs(sn[0].wert - 5.0) < 1e-12,
          (f"{sn[0].wert:.0f} Seiten, Element {sn[0].element}: {sn[0].text[:80]}"
           if sn else "kein Befund"))

    # Gegenprobe: das richtige Paar besteht die Abnahme ohne einen Befund
    m2 = paar(False)
    alle2 = dg.abnahme(m2, warnungen=True)
    check("das richtige Würfelpaar besteht ohne Befund", not alle2,
          str([(b.pruefung, b.text[:50]) for b in alle2]))

    # Gegenprobe: ein abgebildetes 4x4x4-Netz mit windschiefem Deckel (eine
    # Deckelecke 0,2 hoeher) - die Huelle ist dort bilinear, und genau so
    # bildet der Sechsflaechner sie ab. Kein Befund.
    m3 = Model("windschief")
    m3.add_material(Material.steel("S235"))
    E = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1.2], [0, 1, 1]]
    ecken3 = [int(m3.add_node(*p)) for p in E]
    k3 = _quaderkoerper(m3, ecken3)
    els3 = mesher.mesh_koerper(m3, k3, log=[], frei=False)
    for i in range(4):
        m3.fix(ecken3[i], "all")
    neu3 = [b for b in dg.abnahme(m3, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
    check("windschiefer Deckel, abgebildet vernetzt: kein Befund",
          len(els3) == 64 and not neu3,
          f"{len(els3)} Elemente; " + "; ".join(b.text[:60] for b in neu3))

    # Ein einzelnes verdrehtes Element im Innern desselben Netzes: die
    # Bilanz verschiebt sich nur um ein Drittel eines von 64 Elementen, die
    # Seiten im Inneren zeigen es trotzdem - mit seiner Nummer.
    # Ein Element des inneren 2x2x2-Kerns: keine seiner Seiten ist frei
    innen = next(i for i in els3
                 if all(0.25 < c < 0.75 for c in
                        m3.nodes[[int(x) for x in m3.elements[i].nodes]].mean(axis=0)))
    n = list(m3.elements[innen].nodes)
    m3.elements[innen].nodes = n[:4] + [n[5], n[6], n[7], n[4]]
    sn3 = [b for b in dg.abnahme(m3) if b.pruefung == "Seiten im Inneren"]
    check("ein verdrehtes Element im Innern wird über die Seiten gefunden",
          len(sn3) == 1 and sn3[0].element == innen,
          (f"Element {sn3[0].element} (soll {innen}), {sn3[0].wert:.0f} Seiten"
           if sn3 else "kein Befund"))

    # Ein Knoten mitten im Deckel eines abgebildeten 4x4x4-Wuerfels, 0,05
    # nach aussen gedrueckt: die vier Seiten um ihn stehen ueber die Huelle
    # hinaus. Das ist eine WARNUNG, kein Fehler - der Koerper geht hinter
    # ihnen nicht weiter, es fehlt kein Nachbar.
    m4 = Model("beule")
    m4.add_material(Material.steel("S235"))
    W = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    ecken4 = [int(m4.add_node(*p)) for p in W]
    els4 = mesher.mesh_koerper(m4, _quaderkoerper(m4, ecken4), log=[], frei=False)
    for i in range(4):
        m4.fix(ecken4[i], "all")
    mitte = int(np.argmin(np.linalg.norm(m4.nodes - [0.5, 0.5, 1.0], axis=1)))
    m4.nodes[mitte, 2] += 0.05
    alle4 = dg.abnahme(m4, warnungen=True)
    nr = [b for b in alle4 if b.pruefung == "Netzrand neben der Hülle"]
    check("ein nach außen gedrückter Randknoten ist eine Warnung, kein Fehler",
          len(els4) == 64 and len(nr) == 1 and abs(nr[0].wert - 4.0) < 1e-12
          and nr[0].stufe == "WARNUNG"
          and not [b for b in alle4 if b.stufe != "WARNUNG"],
          "; ".join(f"{b.pruefung} ({b.stufe}, {b.wert:.0f})" for b in alle4) or "kein Befund")

    # Ein Riss ohne Weite: zwei Wuerfel aus je fuenf Tetraedern, beide gleich
    # zerlegt (nicht gespiegelt) - die gemeinsame Seite x = 1 ist links ueber
    # die eine, rechts ueber die andere Diagonale geteilt. Der Koerper stimmt
    # (Volumen 2,0), nur die Teilung nicht: eine WARNUNG, kein FEHLER.
    m6 = Model("riss")
    m6.add_material(Material.steel("S235"))
    ids6 = mesher.grid_box(m6, "S235", 2.0, 1.0, 1.0, 2, 1, 1, typ="hex8")
    m6.elements.clear()
    for i in range(2):
        c = [ids6[i, 0, 0], ids6[i + 1, 0, 0], ids6[i + 1, 1, 0], ids6[i, 1, 0],
             ids6[i, 0, 1], ids6[i + 1, 0, 1], ids6[i + 1, 1, 1], ids6[i, 1, 1]]
        for tet in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)]:
            m6.add_element("tet4", [int(c[x]) for x in tet], "S235")
    k6 = _quaderkoerper(m6, [ids6[0, 0, 0], ids6[2, 0, 0], ids6[2, 1, 0], ids6[0, 1, 0],
                             ids6[0, 0, 1], ids6[2, 0, 1], ids6[2, 1, 1], ids6[0, 1, 1]])
    k6.elemente = list(range(len(m6.elements)))
    for kn in ids6[0].ravel():
        m6.fix(int(kn), "all")
    alle6 = dg.abnahme(m6, warnungen=True)
    ri = [b for b in alle6 if b.pruefung == "Riss im Netz"]
    check("ein Riss ohne Weite ist eine Warnung mit vier Seiten, kein Fehler",
          len(ri) == 1 and abs(ri[0].wert - 4.0) < 1e-12 and ri[0].stufe == "WARNUNG"
          and not dg.abnahme(m6),
          "; ".join(f"{b.pruefung} ({b.stufe}, {b.wert:.0f})" for b in alle6) or "kein Befund")

    # Faellt die neue Pruefung aus, steht das da - und die uebrigen laufen
    # weiter (eine Ausnahme aus abnahme() hiesse in der Oberflaeche „Abnahme
    # nicht möglich" fuer alle Pruefungen zugleich)
    echt = dg._polyederhuelle

    def wirft(*a, **kw):
        raise RuntimeError("Hülle nicht lesbar")

    dg._polyederhuelle = wirft
    try:
        m5 = paar(True)
        m5.add_node(9.0, 9.0, 9.0)                   # ein loser Knoten
        alle5 = dg.abnahme(m5, warnungen=True)
    finally:
        dg._polyederhuelle = echt
    namen5 = [b.pruefung for b in alle5]
    check("ein Ausfall der Volumenbilanz wird benannt, der Rest läuft weiter",
          "Volumenbilanz nicht geprüft" in namen5 and "Knoten ohne Element" in namen5,
          str(namen5))


def _wuerfel_angehoben(dz, h):
    """Würfel 1 x 1 x 1 m, die Deckelecke (1, 1, 1) um dz angehoben - der
    Deckel ist windschief (bilinear). Eine Bodenkante ist bei x = 0,5
    geteilt; mit fünf Ecken im Boden geht der Körper an den freien
    Vernetzer (Gegenprüfung vom 23.09.2026)."""
    from statik3d import mesher
    m = Model("angehoben")
    m.add_material(Material.steel("S235"))
    P = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1 + dz],
         [0, 1, 1], [0.5, 0, 0]]
    ecken = [int(m.add_node(*p)) for p in P]
    seiten = [[0, 8, 1, 2, 3], [4, 5, 6, 7], [0, 8, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6],
              [3, 0, 4, 7]]
    kante, fl = {}, []
    for s_i, ring in enumerate(seiten):
        ln = []
        for a, b in zip(ring, ring[1:] + ring[:1]):
            key = (min(a, b), max(a, b))
            if key not in kante:
                kante[key] = f"L{len(kante)}"
                m.add_line(kante[key], [ecken[a], ecken[b]])
            ln.append(kante[key])
        m.add_flaeche(f"F{s_i}", ln, material="S235")
        fl.append(f"F{s_i}")
    k = m.add_koerper("K", fl, material="S235")
    els = [int(i) for i in mesher.mesh_koerper(m, k, log=[], frei=True, h=h)]
    for i in (0, 1, 2, 3):
        m.fix(ecken[i], "all")
    return m, k, els


#: Die Befunde der Netzabnahme gegen die Randflaechen - die Pruefungen „ohne
#: Eingriff kein Befund" filtern darauf. Bis zum 23.09.2026 fehlte die
#: „Lücke im Netzrand“ (und im Filter des windschiefen Deckels auch der
#: Riss): Eine falsche Luecke an jedem Koerper (Verfaelschung in
#: _abnahme_volumenbilanz) liess alle sieben dieser Pruefungen bestehen, bei
#: Kuhn 50:1 stand sie sogar im Detailtext (Nebenbefund B141, gemessen an
#: ec6448c: 88 von 112 bestanden, darunter diese sieben).
_NETZ_BEFUNDE = ("Volumenbilanz", "Seiten im Inneren", "Netzrand neben der Hülle",
                 "Riss im Netz", "Lücke im Netzrand")

_TET_SEITEN = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))


def _tetraeder_masse(m, els):
    """Je Tetraeder aus els die Masse des Hohlraums, den sein Fehlen laesst,
    so wie die Abnahme sie nimmt: t/L (t = 2 V / Summe der Seitenflaechen, L
    die laengste Kante; ABNAHME_RISS_DICKE) und t / Median der Dicken der
    vier Nachbarn ueber seine Seiten (ABNAHME_RISS_NACHBAR, nan ohne vier
    Nachbarn). Damit waehlt eine Pruefung ihr Element nach Eigenschaften und
    nicht nach der Nummer, die der Vernetzer vergibt."""
    from collections import defaultdict
    TET = np.array([[int(x) for x in m.elements[int(i)].nodes] for i in els])
    P = m.nodes[TET]
    V = np.abs(np.linalg.det(P[:, 1:] - P[:, :1])) / 6.0
    A = sum(0.5 * np.linalg.norm(np.cross(P[:, b] - P[:, a], P[:, c] - P[:, a]), axis=1)
            for a, b, c in _TET_SEITEN)
    L = np.max([np.linalg.norm(P[:, a] - P[:, b], axis=1)
                for a in range(4) for b in range(a + 1, 4)], axis=0)
    T = 2.0 * V / A
    an_seite = defaultdict(list)
    for i, kn in enumerate(TET):
        for s in _TET_SEITEN:
            an_seite[tuple(sorted(int(kn[j]) for j in s))].append(i)
    nachbar = np.full(len(TET), np.nan)
    for i, kn in enumerate(TET):
        nb = [j for s in _TET_SEITEN for j in an_seite[tuple(sorted(int(kn[x]) for x in s))]
              if j != i]
        if len(nb) == 4:
            nachbar[i] = T[i] / float(np.median(T[nb]))
    return T / L, nachbar


def test_abnahme_ohne_fehlalarm_am_freien_netz():
    """Richtige Netze des freien Vernetzers rissen die Abnahme (Gegenprüfung
    vom 23.09.2026, M1 a): am Würfel mit angehobener Deckelecke meldete sie
    „FEHLER Seiten im Inneren" (h = 0,25: dz = 0,5 6 Seiten, dz = 1,0 53;
    dz = 1,0 und h = 0,5: 8 Seiten und „FEHLER Volumenbilanz 0,782 %"). Das
    Netz ist richtig: jede innere Seite kommt genau zweimal vor.

    Drei Ursachen. Die Windungszahl rechnete gegen den groben Fächer des
    windschiefen Deckels, der bis |d|/16 = 31,25 mm neben der bilinearen
    Fläche liegt - die Seiten lagen -0,87 bis 5,21 mm daneben. Der freie
    Vernetzer legt Knoten auf Sehnen seines groben Dreiecksnetzes
    (gemessen 7,55 mm, dz·h²/4 = 7,81 mm), und dafür galt dieselbe 1-%-Grenze
    wie an ebenen Flächen. Und die Volumenbilanz rechnete die Sehnen nicht ein.
    Die Kur darf dabei keinen echten Fehler am windschiefen Deckel verdecken.
    """
    from collections import Counter
    from statik3d.elements import solid as sl
    # dz 0,3 und 1,0 bei h 0,25 dazu seit B053 (22./23.09.2026): die Ecken
    # freier Netze behalten die Sehnenzulage, die abgebildeter nicht
    for dz, h in ((0.5, 0.25), (1.0, 0.5), (0.3, 0.25), (1.0, 0.25)):
        m, k, els = _wuerfel_angehoben(dz, h)
        zahl = Counter()
        for i in els:
            e = m.elements[i]
            for s in sl.FLAECHEN_ECKEN[e.typ]:
                zahl[tuple(sorted(int(e.nodes[j]) for j in s))] += 1
        bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
        check(f"freies Netz, Deckelecke {dz} m angehoben, h = {h}: kein Befund",
              max(zahl.values()) == 2 and not bef,
              f"{len(els)} tet4, Seiten höchstens {max(zahl.values())}-fach; "
              + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
        if dz == 0.5:
            # Gegenprobe: ein Tetraeder mit drei Ecken im windschiefen Deckel
            # fehlt - diese Delle ist Elementgroesse tief, nicht Sehnenweite,
            # und die Sehnengrenze darf sie nicht verdecken. Sie ist eine
            # Luecke an der Oberflaeche (Mangel 3 der Gegenpruefung vom
            # 23.09.2026): gemeldet mit dem Volumen des Tetraeders, als
            # WARNUNG, solange sie unter der Grenze der Volumenbilanz bleibt.
            deckel = [i for i in els if sum(
                abs(p[2] - (1 + dz * p[0] * p[1])) < 1e-9 and 1e-9 < p[0] < 1 - 1e-9
                and 1e-9 < p[1] < 1 - 1e-9 for p in m.nodes[m.elements[i].nodes]) == 3]
            weg = deckel[0]
            V_weg = float(dg.elementvolumina(m, [weg])[0])
            k.elemente = [i for i in els if i != weg]
            bef = dg._abnahme_volumenbilanz(m, "K", k, k.elemente)
            lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
            # Das Volumen der Luecke reicht bis zur bilinearen Flaeche, der
            # Tetraeder nur bis zu seiner Sehne. Der Unterschied dV ist das
            # Integral von f - Ebene ueber sein Deckeldreieck, f = 1 + dz·x·y:
            # quadratisch, also exakt mit den Kantenmitten, an denen f - Ebene
            # = -dz·Δx·Δy/4 ist. Bis zum 24.09.2026 stand hier die feste
            # Grenze 1,05·V_weg; je nach Gitterphase des Vernetzers ist die
            # Luecke aber 4,7 bis 9,2 % groesser als der Tetraeder (dV jedes Mal
            # 8,138e-5 m³, der Tetraeder 0,89 bis 1,75 dm³). An acht Phasen
            # gemessen: Luecke = V_weg + dV auf 2·10⁻⁵ genau (24.09.2026).
            oben = [p for p in m.nodes[m.elements[weg].nodes]
                    if abs(p[2] - (1 + dz * p[0] * p[1])) < 1e-9]
            A_o = 0.5 * abs((oben[1][0] - oben[0][0]) * (oben[2][1] - oben[0][1])
                            - (oben[2][0] - oben[0][0]) * (oben[1][1] - oben[0][1]))
            dV = A_o / 3.0 * sum(-dz * (p[0] - q[0]) * (p[1] - q[1]) / 4.0
                                 for p, q in ((oben[0], oben[1]), (oben[1], oben[2]),
                                              (oben[0], oben[2])))
            check("  und ein fehlender Tetraeder am windschiefen Deckel wird als Lücke gemeldet",
                  len(lu) == 1 and lu[0].stufe == "WARNUNG" and dV > 0
                  and abs(lu[0].wert - (V_weg + dV)) < 1e-3 * lu[0].wert
                  and not [b for b in bef if b.pruefung == "Riss im Netz"],
                  f"Element {weg} ({V_weg:.4g} m³, bis zur Fläche {V_weg + dV:.4g} m³): "
                  + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef)
                     or "kein Befund"))
            # Ein Tetraeder mitten im Koerper fehlt: ein geschlossener
            # Hohlraum, aber mit dem Volumen eines Elements - kein Riss
            mitte = [i for i in els
                     if all(0.3 < c < 0.7 for c in m.nodes[m.elements[i].nodes].mean(axis=0))]
            k.elemente = [i for i in els if i != mitte[0]]
            bef = dg._abnahme_volumenbilanz(m, "K", k, k.elemente)
            sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
            check("  ein fehlender Tetraeder im Innern: geschlossen, aber kein Riss",
                  len(sn) == 1 and sn[0].wert == 4.0
                  and not [b for b in bef if b.pruefung == "Riss im Netz"],
                  f"Element {mitte[0]}: "
                  + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef))
            # Ein Tetraeder, der kleiner ist als seine Nachbarn (sein Hohlraum
            # hoechstens ABNAHME_RISS_NACHBAR-mal so dick wie sie), aber nicht
            # flach: nur t/L macht ihn zum FEHLER (am 23.09.2026 am freien
            # Wuerfel 9 solche von 541 inneren Tetraedern). Bis zum 24.09.2026
            # stand hier fest Element 765; am Netz vom 24.09.2026 war 765
            # gar nicht duenner als seine Nachbarn (t/L 9,32 %, 1,01-mal so
            # dick), die Pruefung zeigte die Regel also nicht mehr, und in vier
            # von sieben anderen Gitterphasen lag 765 ausserhalb 5 … 10 % oder
            # an der Huelle. Jetzt nach Eigenschaften: der duennste ueber der
            # Grenze ABNAHME_RISS_DICKE, der naechste am Riss. An acht
            # Gitterphasen gab es 5 bis 17 solche, alle unter 7 % (gemessen
            # 24.09.2026, zweimal).
            tl, tn = _tetraeder_masse(m, els)
            knapp = [j for j in range(len(els))
                     if dg.ABNAHME_RISS_DICKE < tl[j] < 0.10 and tn[j] <= dg.ABNAHME_RISS_NACHBAR]
            j_k = min(knapp, key=lambda j: tl[j]) if knapp else -1
            weg = els[j_k] if knapp else -1
            k.elemente = [i for i in els if i != weg]
            bef = dg._abnahme_volumenbilanz(m, "K", k, k.elemente)
            k.elemente = els
            # Die Elementzahl als Fenster: gemessen 1091 (24.09.2026).
            check("  ein fehlender kleiner Tetraeder, der nicht flach ist (t/L 5 … 10 %, dünner "
                  "als die Nachbarn): FEHLER",
                  _fenster(len(els), 1091) and weg >= 0
                  and [(b.stufe, b.pruefung, b.wert) for b in bef]
                  == [("FEHLER", "Seiten im Inneren", 4.0)],
                  f"{len(els)} tet4, {len(knapp)} Kandidaten, Element {weg}: "
                  f"t/L {tl[j_k] * 100:.2f} %, {tn[j_k]:.3f}-mal so dick wie die Nachbarn: "
                  + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef))
            # Fehlende Tetraeder, die kleiner sind als ihre Nachbarn - ihr
            # Hohlraum ist hoechstens ABNAHME_RISS_NACHBAR-mal so dick wie
            # sie, die Nachbarregel allein liesse ihn als Riss durch -, aber
            # nicht flach (t/L 5 bis 7 %): Nur t/L macht sie zum FEHLER.
            # Gewaehlt nach diesen Eigenschaften, nicht nach der Nummer, die
            # der freie Vernetzer vergibt; bis zum 23.09.2026 stand hier fest
            # Element 765 (Nebenbefund B142). Gemessen 23.09.2026: 16 von 1208
            # Tetraedern mit vier Nachbarn, t/L 5,03 bis 6,25 %, 0,498- bis
            # 0,638-mal so dick wie die Nachbarn; mit ABNAHME_RISS_DICKE = 10
            # war der Hohlraum von 765 „WARNUNG Riss im Netz 4“. Am Netz des
            # Vernetzers vom 23.09.2026 (1085 tet4) sind es 12 von 896
            # (gemessen 24.09.2026). tl, tn von oben.
            wahl = [els[j] for j in range(len(els))
                    if 0.05 < tl[j] < 0.07 and tn[j] <= dg.ABNAHME_RISS_NACHBAR]
            still = []
            for weg in wahl:
                k.elemente = [i for i in els if i != weg]
                bef = dg._abnahme_volumenbilanz(m, "K", k, k.elemente)
                if [(b.stufe, b.pruefung, b.wert) for b in bef] != [("FEHLER", "Seiten im Inneren", 4.0)]:
                    still.append(f"{weg}: " + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}"
                                                         for b in bef) or "kein Befund"))
            k.elemente = els
            check("  fehlende kleine Tetraeder, die nicht flach sind (t/L 5 bis 7 %): je FEHLER 4",
                  wahl and not still,
                  f"{len(wahl)} von {int(np.isfinite(tn).sum())} Tetraedern mit vier Nachbarn; "
                  + ("; ".join(still) if still else "alle FEHLER Seiten im Inneren 4"))

    # Die feine Huelle: am abgebildeten 4 x 4 x 4-Netz (dz = 0,5) wird der
    # Deckelknoten bei (0,75; 0,75) 40 mm nach aussen gedrueckt - dort liegt
    # der grobe Faecher 31,25 mm ueber dem Deckel. Das ist eine Beule, eine
    # WARNUNG. Gegen den groben Faecher gerechnet war es ein FEHLER „Seiten
    # im Inneren" (2 Seiten). Die Grenze fuer Sehnen ist dort 21,6 mm - die
    # Beule liegt darueber und wird gemeldet.
    from statik3d import mesher
    m4 = Model("beule")
    m4.add_material(Material.steel("S235"))
    W = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1.5], [0, 1, 1]]
    ecken4 = [int(m4.add_node(*p)) for p in W]
    k4 = _quaderkoerper(m4, ecken4)
    mesher.mesh_koerper(m4, k4, log=[], frei=False)
    for i in range(4):
        m4.fix(ecken4[i], "all")
    kn = int(np.argmin(np.linalg.norm(m4.nodes - [0.75, 0.75, 1.28125], axis=1)))
    m4.nodes[kn, 2] += 0.04
    bef4 = [b for b in dg.abnahme(m4, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
    check("Beule im windschiefen Deckel: eine WARNUNG, kein FEHLER",
          len(bef4) == 1 and bef4[0].pruefung == "Netzrand neben der Hülle"
          and bef4[0].stufe == "WARNUNG" and bef4[0].wert == 4.0,
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef4) or "kein Befund")

    # Nebenbefund B053 (22./23.09.2026): die Sehnenzulage galt auch für die
    # Ecken der Seiten eines abgebildeten Netzes, dessen Knoten gemessen genau
    # auf der windschiefen Fläche liegen (0,0000 mm). So blieb eine Beule von
    # 25 mm (dz = 0,5) bzw. 100 mm (dz = 1,0) ungenannt, erst 30 bzw. 150 mm
    # waren eine WARNUNG. Die Sehne liegt zwischen den Knoten, nicht an ihnen.
    for dz, beule in ((0.5, 0.025), (1.0, 0.100)):
        m5 = Model("beule")
        m5.add_material(Material.steel("S235"))
        W5 = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1 + dz],
              [0, 1, 1]]
        ecken5 = [int(m5.add_node(*p)) for p in W5]
        k5 = _quaderkoerper(m5, ecken5)
        mesher.mesh_koerper(m5, k5, log=[], frei=False)
        for i in range(4):
            m5.fix(ecken5[i], "all")
        X4 = dg._polyederhuelle(m5, k5)["bilinear"][0]
        oben = [i for i in range(m5.nn)
                if abs(m5.nodes[i, 2] - (1 + dz * m5.nodes[i, 0] * m5.nodes[i, 1])) < 1e-9]
        d_oben = float(dg._bilinear_abstand(m5.nodes[oben], X4).max())
        kn = int(np.argmin(np.linalg.norm(m5.nodes - [0.75, 0.75, 1 + dz * 0.5625], axis=1)))
        m5.nodes[kn, 2] += beule
        bef5 = [b for b in dg.abnahme(m5, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
        check(f"abgebildetes Netz, Deckelecke {dz} m angehoben, Beule {beule * 1e3:.0f} mm: "
              "WARNUNG Netzrand",
              len(oben) == 25 and d_oben < 1e-9
              and [(b.stufe, b.pruefung, b.wert) for b in bef5]
              == [("WARNUNG", "Netzrand neben der Hülle", 4.0)],
              f"Deckelknoten bis {d_oben * 1e3:.4f} mm neben der Fläche; "
              + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef5) or "kein Befund"))


def test_abnahme_luecken_des_vernetzers_sind_risse():
    """Der freie Vernetzer sortiert Tetraeder mit V <= FLACH·h³ aus, und ihre
    Lücken bleiben im Netz. Die Abnahme meldete sie als „FEHLER Seiten im
    Inneren" (Gegenprüfung vom 23.09.2026, M1 b: Platte mit Bohrung 8
    Seiten, Keile am feinen Rand 4) - vor jeder Rechnung die Rückfrage
    „Trotzdem rechnen?", und neu vernetzen ergibt dasselbe Netz. Gemeint war
    die WARNUNG „Riss im Netz"; der alte Risstest verlangte aber Ebenheit auf
    1 % des Seitendurchmessers, die Lücken sind 1,7 bis 11 % dick.
    (Seit 24.09.2026 behält der Vernetzer diese Tetraeder; der Test nimmt
    einen solchen darum von Hand heraus.)

    Ein Riss ist jetzt ein geschlossener Hohlraum, dessen mittlere Dicke
    2V/ΣA höchstens 5 % der längsten Kante seiner Seiten ist (gemessen an
    den Lücken des Vernetzers bis 3,55 %). Die Zulage FLACH·h³ je Seite mit
    h der größten Elementdiagonale im Körper (erste Kur) ließ in abgestuften
    Netzen echte Fehler durch - siehe test_abnahme_riss_misst_am_oertlichen_
    element.
    """
    from statik3d import mesher, mesher3d
    import contextlib
    import io
    import tests.test_sweep as TS
    alt = mesher3d.RANDFELD
    mesher3d.RANDFELD = True
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            m, k = TS.platte_mit_stufe()
            m.netz.sweep = False
            mesher.modell_vernetzen(m, [], workers=1)
    finally:
        mesher3d.RANDFELD = alt
    # Seit 24.09.2026 (Vernetzer, Nachtrag B101) misst flache_tetraeder die
    # eigene Groesse des Tetraeders: die duennen Keile am feinen Rand bleiben
    # im Netz, der Vernetzer laesst dort keine Luecke mehr. Das frei vernetzte
    # Netz hat darum keinen Befund; der Vernetzer vom Stand b98941b liess die
    # Luecke, dort meldet dieselbe Zeile „WARNUNG Riss im Netz 4“ (beides
    # gemessen 24.09.2026). Kommt die Luecke zurueck, meldet das diese
    # Pruefung mit eigenem Namen. Elementzahl als Fenster: 2503 tet4 an allen
    # acht Gitterphasen des BCC-Gitters (b98941b 2502 mit der Luecke).
    def kurz(bef):
        return [(b.stufe, b.pruefung, b.wert) for b in bef]
    bef_frei = kurz(dg._abnahme_volumenbilanz(m, k.name, k, [int(i) for i in k.elemente]))
    check("Keile am feinen Rand, frei vernetzt: das Netz des Vernetzers hat keinen Befund",
          _fenster(len(k.elemente), 2503) and bef_frei == [],
          f"{len(k.elemente)} tet4: {bef_frei or 'kein Befund'}")

    # Die Regeln der Abnahme werden am festgehaltenen Netz geprueft:
    # tests/netz_platte_keile_7ce5510.npz ist das Netz des Vernetzers vom
    # Stand 7ce5510 (dreimal gebaut, bitgleich: 591 Knoten, davon 12 der
    # Geometrie, 2503 tet4). Liefert ein kuenftiger Vernetzer weder die Luecke
    # noch den Splitter an ihrer Stelle, rissen sonst alle Folgepruefungen mit
    # (Gegenpruefung vom 24.09.2026: mit dem Vernetzer von b98941b 0
    # Kandidaten, Element -1).
    m, k = TS.platte_mit_stufe()
    netz = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "netz_platte_keile_7ce5510.npz"))
    geometrie_gleich = (m.nn == len(netz["geo"])
                        and np.array_equal(np.asarray(m.nodes, float), netz["geo"]))
    for p in netz["knoten"]:
        m.add_node(*p)
    werkstoff = next(iter(m.materials))
    els_alle = [int(m.add_element("tet4", [int(x) for x in t], werkstoff)) for t in netz["tet4"]]
    k.elemente = els_alle
    check("  festgehaltenes Netz: Geometrie gleich, 2503 tet4, kein Befund",
          geometrie_gleich and len(els_alle) == 2503
          and kurz(dg._abnahme_volumenbilanz(m, k.name, k, els_alle)) == [],
          f"Geometrie gleich: {geometrie_gleich}; {len(els_alle)} tet4")
    # Der Riss wird von Hand gelegt - heraus kommt ein Tetraeder, wie ihn der
    # Vernetzer bis dahin aussortierte: innen (alle vier Seiten an Nachbarn,
    # jeder Knoten auch in anderen Elementen), flach (t/L hoechstens
    # ABNAHME_RISS_DICKE) und hoechstens FLACH·h³ gross. Gemessen 24.09.2026
    # (zweimal, Netz vor und nach dem Merge 7ce5510 verglichen): das ist genau
    # einer, Element 2478 (V 1,151e-10 m³ = 0,87 FLACH·L³ = 0,92 FLACH·h³,
    # t/L 1,48 %) - derselbe Tetraeder, dessen Luecke der Vernetzer bis dahin
    # an dieser Stelle liess (b98941b: 2502 tet4, Knoten und alle uebrigen
    # Tetraeder gleich). Der duennste Tetraeder des Netzes (Element 1524,
    # t/L 0,76 %), den der erste Entwurf dieses Tests herausnahm, ist aber
    # 89-mal FLACH·L³ gross: nach B050 (ABNAHME_RISS_FLACH) ist sein Fehlen
    # richtig ein FEHLER „Seiten im Inneren 4" und kein Riss (mit
    # abgeschalteter Groessenregel gemessen: WARNUNG Riss 4; eigene Pruefung
    # unten).
    from collections import Counter
    SEITEN = ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3))

    def eigen(i):
        P = m.nodes[m.elements[i].nodes[:4]]
        V_i = abs(float(np.linalg.det(P[1:] - P[0]))) / 6.0
        A_i = sum(0.5 * np.linalg.norm(np.cross(P[b] - P[a], P[c] - P[a])) for a, b, c in SEITEN)
        L_i = max(np.linalg.norm(P[a] - P[b]) for a in range(4) for b in range(a + 1, 4))
        return V_i, 2.0 * V_i / A_i / L_i, L_i
    seiten = Counter(tuple(sorted(int(m.elements[i].nodes[a]) for a in s))
                     for i in els_alle for s in SEITEN)
    benutzt = Counter(int(n) for i in els_alle for n in m.elements[i].nodes[:4])

    def freie_seiten(i):
        kn = m.elements[i].nodes
        return sum(seiten[tuple(sorted(int(kn[a]) for a in s))] == 1 for s in SEITEN)

    def knoten_geteilt(i):
        return min(benutzt[int(n)] for n in m.elements[i].nodes[:4]) >= 2

    def innen(i):
        return freie_seiten(i) == 0 and knoten_geteilt(i)
    E = {i: eigen(i) for i in els_alle}
    L_k = max(e[2] for e in E.values())             # laengste Elementkante des Koerpers
    FLACH_h3 = mesher3d.FLACH * m.netz.ziellaenge ** 3
    FLACH_L3 = mesher3d.FLACH * L_k ** 3
    klein_flach = [i for i in els_alle if innen(i) and E[i][1] <= dg.ABNAHME_RISS_DICKE
                   and E[i][0] <= FLACH_h3]
    riss_el = min(klein_flach, key=lambda i: E[i][1]) if klein_flach else -1
    els = [i for i in els_alle if i != riss_el]
    k.elemente = els
    bef = dg._abnahme_volumenbilanz(m, k.name, k, els)
    ri = [b for b in bef if b.pruefung == "Riss im Netz"]
    V_r, tl_r, _L = E.get(riss_el, (0.0, 0.0, 0.0))
    check("  ein fehlender Tetraeder, so klein wie die aussortierten, ist eine WARNUNG Riss",
          riss_el >= 0 and innen(riss_el) and tl_r <= dg.ABNAHME_RISS_DICKE and V_r <= FLACH_h3
          and len(ri) == 1 and ri[0].stufe == "WARNUNG" and ri[0].wert == 4.0
          and not [b for b in bef if b.stufe == "FEHLER"],
          f"{len(els_alle)} tet4, {len(klein_flach)} Kandidat(en), Element {riss_el} entfernt "
          f"(V {V_r:.4g} m³ = {V_r / FLACH_L3:.2f} FLACH·L³, t/L {tl_r * 100:.2f} %); "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef))
    # Zweite Gegenpruefung, Mangel 3: der Text sagte „Neu vernetzen mit
    # denselben Einstellungen ergibt dasselbe Netz" ohne Einschraenkung - an
    # einem von Hand geaenderten Netz hilft neu vernetzen aber
    text = ri[0].text if ri else ""
    check("  der Text rät zu neu vernetzen nur bei importierten oder von Hand geänderten Netzen",
          "von Hand geändert" in text and "dasselbe Netz" in text
          and "Neu vernetzen mit denselben Einstellungen ergibt dasselbe Netz" not in text,
          text[-300:])
    # Der Text nennt die Groesse, nicht die Herkunft (Benutzerhandbuch, B051):
    # er vergleicht den Hohlraum mit den Luecken, die bleiben, wenn der
    # Vernetzer flache Tetraeder aussortiert. Bis zum 24.09.2026 hiess diese
    # Pruefung „nennt als Herkunft den Vernetzer“ - bei gleicher Bedingung.
    check("  und misst die Größe an den Lücken, die der Vernetzer beim Aussortieren flacher "
          "Tetraeder lässt",
          "so klein wie die Lücken, die bleiben, wenn der Vernetzer flache Tetraeder aussortiert"
          in text, text[:420])
    # Gegenprobe: fehlt ein Tetraeder, der nicht flach ist, ist es kein Riss -
    # die Regel winkt nicht jeden Hohlraum durch. Die Platte ist eine
    # Tetraederlage dick: der fehlende Tetraeder hinterlaesst eine Delle in
    # der Plattenflaeche (offen zur Randflaeche: mindestens eine seiner
    # Seiten liegt auf der Huelle). Das ist eine Luecke im Netzrand mit dem
    # Volumen des Tetraeders (Mangel 3 der Gegenpruefung vom 23.09.2026).
    # Gemessen 24.09.2026 vor und nach dem Merge 7ce5510: Element 1,
    # 7,347e-6 m³, eine Seite auf der Huelle.
    V = dg.elementvolumina(m, els)
    mittel = [i for j, i in enumerate(els)
              if V[j] > 0.5 * float(np.median(V)) and freie_seiten(i) >= 1 and knoten_geteilt(i)
              and all(0.3 < c < 0.7 for c in m.nodes[m.elements[i].nodes].mean(axis=0)[:2]
                      / np.array([0.2, 0.1]))]
    V_weg = float(V[els.index(mittel[0])])
    k.elemente = [i for i in els if i != mittel[0]]
    bef = dg._abnahme_volumenbilanz(m, k.name, k, k.elemente)
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    # (der Riss daneben bleibt der Riss mit 4 Seiten)
    check("  ein fehlender Tetraeder mittlerer Größe (Delle) ist eine Lücke, kein Riss",
          len(lu) == 1 and abs(lu[0].wert - V_weg) < 1e-3 * V_weg
          and [b.wert for b in bef if b.pruefung == "Riss im Netz"] == [4.0]
          and not [b for b in bef if b.pruefung == "Seiten im Inneren"],
          f"Element {mittel[0]} ({V_weg:.4g} m³, {freie_seiten(mittel[0])} Seite(n) auf der Hülle): "
          + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"))

    # Nebenbefund B050 (22./23.09.2026): fehlt ein Tetraeder, der selbst flach
    # ist (t/L ≤ 5 %, dünn gegen die Nachbarn), blieb es bei der WARNUNG Riss
    # ohne Rückfrage - gleich wie groß der Hohlraum ist. Gemeint ist ein
    # innerer flacher Tetraeder in Elementgröße, dessen Hohlraum ohne die
    # Größenregel ein Riss wäre; gewählt wird der größte solche (Nummern sind
    # netzabhängig). Gemessen 24.09.2026 vor und nach dem Merge 7ce5510:
    # Element 58, t/L 4,06 %, 1,752e-6 m³, das 13 250-Fache von FLACH·L³ (L
    # die längste Elementkante des Körpers, 50,9 mm). Die Lücke des
    # Vernetzers (Element 2478 oben) hat das 0,87-Fache, die größte der 30
    # Lücken in den Modellen der Suiten test_mesher3d und test_sweep ebenso
    # (gemessen 23.09.2026).
    def ohne(e):
        k.elemente = [i for i in els if i != e]
        return kurz(dg._abnahme_volumenbilanz(m, k.name, k, k.elemente))
    gross = sorted((i for i in els if innen(i) and E[i][1] <= dg.ABNAHME_RISS_DICKE
                    and E[i][0] > dg.ABNAHME_RISS_FLACH * FLACH_L3), key=lambda i: -E[i][0])
    echt_flach = dg.ABNAHME_RISS_FLACH
    gross_el, ohne_regel = -1, []
    try:
        dg.ABNAHME_RISS_FLACH = float("inf")
        for i in gross:
            ohne_regel = ohne(i)
            if ohne_regel and all(b[:2] == ("WARNUNG", "Riss im Netz") for b in ohne_regel):
                gross_el = i
                break
    finally:
        dg.ABNAHME_RISS_FLACH = echt_flach
    V_g, tl_g, _L = E.get(gross_el, (0.0, 0.0, 0.0))
    bef_g = ohne(gross_el)
    check("  ein fehlender flacher Tetraeder in Elementgröße (t/L ≤ 5 %, über 1000 FLACH·L³): "
          "FEHLER, der Riss daneben bleibt ein Riss",
          gross_el >= 0 and V_g > 1000 * FLACH_L3 and tl_g <= dg.ABNAHME_RISS_DICKE
          and ohne_regel == [("WARNUNG", "Riss im Netz", 8.0)]
          and bef_g == [("FEHLER", "Seiten im Inneren", 4.0), ("WARNUNG", "Riss im Netz", 4.0)],
          f"{len(els_alle)} tet4, Element {gross_el}: V {V_g:.4g} m³ = {V_g / FLACH_L3:.0f} "
          f"FLACH·L³, t/L {tl_g * 100:.2f} %; ohne Größenregel {ohne_regel}; {bef_g}")
    # Gegenprobe und Grenze: ein flacher Tetraeder so klein wie die, die der
    # Vernetzer aussortierte, aber über FLACH·h³ (der kleinste innere flache,
    # den er behält; gemessen 24.09.2026: Element 2414, 1,454e-10 m³ = 1,10
    # FLACH·L³, t/L 1,86 %), bleibt ein Riss - an dieser Größe ist er von
    # ihnen nicht zu trennen (Grenze ABNAHME_RISS_FLACH = 2 FLACH·L³)
    klein = sorted((i for i in els if innen(i) and E[i][1] <= dg.ABNAHME_RISS_DICKE
                    and E[i][0] > FLACH_h3), key=lambda i: E[i][0])
    klein_el = klein[0] if klein else -1
    V_k, tl_k, _L = E.get(klein_el, (0.0, 0.0, 0.0))
    bef_k = ohne(klein_el)
    check("  ein fehlender flacher Tetraeder so klein wie die aussortierten bleibt ein Riss",
          klein_el >= 0 and FLACH_h3 < V_k <= dg.ABNAHME_RISS_FLACH * FLACH_L3
          and bef_k == [("WARNUNG", "Riss im Netz", 8.0)],
          f"Element {klein_el}: V {V_k:.4g} m³ = {V_k / FLACH_L3:.2f} FLACH·L³, "
          f"t/L {tl_k * 100:.2f} %: {bef_k}")
    # Die Groessenregel selbst: der duennste innere Tetraeder des Netzes
    # (Element 1524, t/L 0,76 %, 88,9 FLACH·L³), den der erste Entwurf dieses
    # Tests als Riss herausnahm. Ohne ihn FEHLER „Seiten im Inneren 4“, mit
    # ABNAHME_RISS_FLACH 89, 100 oder 1000 „WARNUNG Riss im Netz 4“ (gemessen
    # 24.09.2026, zweimal). Die Pruefungen oben lesen ihre Grenzen aus dem
    # Modul und blieben bei FLACH 100 und 1000 gruen (Gegenpruefung vom
    # 24.09.2026); diese faengt eine Ruecknahme ab etwa 89. Eine Ruecknahme
    # von ABNAHME_RISS_DICKE (0,02 bis 0,04) fangen die beiden Pruefungen an
    # der Platte mit Bohrung unten (festgehaltenes Netz ec6448c).
    inn = [i for i in els_alle if innen(i)]
    duenn = min(inn, key=lambda i: E[i][1])
    V_d, tl_d, _L = E[duenn]
    k.elemente = [i for i in els_alle if i != duenn]
    bef_d = kurz(dg._abnahme_volumenbilanz(m, k.name, k, k.elemente))
    try:
        dg.ABNAHME_RISS_FLACH = float("inf")
        bef_d_ohne = kurz(dg._abnahme_volumenbilanz(m, k.name, k, k.elemente))
    finally:
        dg.ABNAHME_RISS_FLACH = echt_flach
    check("  der dünnste innere Tetraeder fehlt (flach, aber über 2 FLACH·L³): FEHLER, "
          "ohne die Größenregel wäre es ein Riss",
          tl_d <= 0.05 and V_d > 2.0 * FLACH_L3       # die Grenzen fest, nicht aus dem Modul
          and bef_d == [("FEHLER", "Seiten im Inneren", 4.0)]
          and bef_d_ohne == [("WARNUNG", "Riss im Netz", 4.0)],
          f"Element {duenn}: V {V_d:.4g} m³ = {V_d / FLACH_L3:.1f} FLACH·L³, t/L {tl_d * 100:.2f} %: "
          f"{bef_d}; ohne Größenregel {bef_d_ohne}")
    k.elemente = els_alle

    # Wie dick darf ein Riss gegen die Elemente daneben sein
    # (ABNAHME_RISS_NACHBAR)? Die Luecken der Keile oben sind duenn genug fuer
    # jede Grenze ab 0,25; mit 0,50, 0,85 oder 1,0 bestand die Suite ganz
    # (Nebenbefund B145). Von unten begrenzt die Grenze die Platte mit Bohrung
    # aus test_mesher3d.test_mantellinie_der_bohrung ohne „intelligent“
    # (12 925 tet4): Dort teilt die Abnahme sechs Haufen an Kanten mit mehr
    # als zwei Seiten in 12 Stuecke (t/Nachbar 0,074 bis 0,579). Die beiden
    # dicksten stammen aus zwei verschiedenen Haufen, je 4 Seiten: 0,579
    # (t/L 3,69 %) und 0,570 (t/L 3,24 %), gemessen 24.09.2026.
    # Gemessen 23.09.2026: mit ABNAHME_RISS_NACHBAR 0,58 „WARNUNG Riss im
    # Netz 133“, mit 0,57 dazu „FEHLER Seiten im Inneren 8“ - eine Rueckfrage
    # vor jeder Rechnung an einem Netz des eigenen Vernetzers.
    #
    # Das Netz stammt aus einer Datei: tests/netz_platte_bohrung_ec6448c.npz
    # haelt das Netz des Vernetzers vom Stand ec6448c fest (12 925 tet4, die
    # Knoten nach den 56 Knoten der Geometrie und die tet4). Der Vernetzer vom
    # 23.09.2026 (Fable-Sitzung) gibt fuer dieselbe Platte ein anderes Netz
    # (13 708 tet4) mit eigener Warnung „Lücke im Netzrand bleibt nach 4
    # Durchgängen“, und die Abnahme meldet dort „FEHLER Seiten im Inneren
    # 366“ (vor der Duennregel aus B044 376) - an dem Netz ist die Grenze der
    # Nachbardicke nicht festzulegen (gemessen 24.09.2026; den FEHLER gibt es
    # ebenso mit h 0,04 und 0,06 m). Die Regel der
    # Abnahme wird darum am festgehaltenen Netz geprueft: dort dieselben
    # Befunde wie am 23.09.2026 (0,65 und 0,58 WARNUNG Riss 133, 0,57 dazu
    # FEHLER Seiten im Inneren 8).
    import tests.test_mesher3d as TM
    r_b, R_b, t_b, h_b = 0.010, 0.45, 0.035, 0.05
    mb = TM.neues_modell()
    mb.netz.ziellaenge = h_b
    mb.netz.intelligent = False
    kb = TM.prisma(mb, [[(-R_b, -R_b), (R_b, -R_b), (R_b, R_b), (-R_b, R_b)],
                        [tuple(x) for x in TM.kreis_punkte(r_b, 24, umgekehrt=True)]], t_b)
    netz = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "netz_platte_bohrung_ec6448c.npz"))
    geometrie_gleich = (mb.nn == len(netz["geo"])
                        and np.array_equal(np.asarray(mb.nodes, float), netz["geo"]))
    for p in netz["knoten"]:
        mb.add_node(*p)
    werkstoff = next(iter(mb.materials))
    els_b = [int(mb.add_element("tet4", [int(x) for x in t], werkstoff)) for t in netz["tet4"]]
    kb.elemente = els_b
    bef = dg._abnahme_volumenbilanz(mb, kb.name, kb, els_b)
    check("Platte mit Bohrung ohne „intelligent“, Netz des Vernetzers vom Stand ec6448c: "
          "WARNUNG Riss, kein FEHLER",
          geometrie_gleich and len(els_b) == 12925
          and [(b.stufe, b.wert) for b in bef if b.pruefung == "Riss im Netz"] == [("WARNUNG", 133.0)]
          and not [b for b in bef if b.stufe == "FEHLER"],
          f"Geometrie gleich: {geometrie_gleich}; {len(els_b)} tet4; "
          + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"))
    echt_nachbar = dg.ABNAHME_RISS_NACHBAR
    try:
        dg.ABNAHME_RISS_NACHBAR = 0.58
        b58 = dg._abnahme_volumenbilanz(mb, kb.name, kb, els_b)
        dg.ABNAHME_RISS_NACHBAR = 0.57
        b57 = dg._abnahme_volumenbilanz(mb, kb.name, kb, els_b)
    finally:
        dg.ABNAHME_RISS_NACHBAR = echt_nachbar
    check("  die Grenze der Nachbardicke: mit 0,58 noch der Riss, mit 0,57 FEHLER Seiten im "
          "Inneren 8",
          not [b for b in b58 if b.stufe == "FEHLER"]
          and [(b.stufe, b.pruefung, b.wert) for b in b57 if b.stufe == "FEHLER"]
          == [("FEHLER", "Seiten im Inneren", 8.0)],
          "0,58: " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in b58)
          + " | 0,57: " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in b57))


def test_abnahme_offene_gruppen_sind_kein_riss():
    """Ein Riss braucht zwei Ufer, die sich schließen. Zwei Fälle, in denen
    die Seiten im Inneren eine offene Gruppe bilden - beide FEHLER:

    * drei Würfel in einer Reihe, der mittlere verdreht: die Gruppe ist vorn
      und hinten offen (2 m² Rand bei 6,9 m² Seitenfläche). Die Summe der
      Flächenvektoren verschwindet dort trotzdem, und das scheinbare Volumen
      auch - daran allein gemessen wäre es ein Riss gewesen (so geschehen
      beim ersten Entwurf dieser Nachbesserung).
    * doppelte Knoten: das Netz ist bei x = 0,5 aufgetrennt, jede Seite der
      Trennfläche hat ein Ufer ohne Gegenüber.
    """
    from statik3d import mesher
    m = Model("reihe")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 3.0, 1.0, 1.0, 3, 1, 1, typ="hex8")
    k = _quaderkoerper(m, [ids[0, 0, 0], ids[3, 0, 0], ids[3, 1, 0], ids[0, 1, 0],
                           ids[0, 0, 1], ids[3, 0, 1], ids[3, 1, 1], ids[0, 1, 1]])
    k.elemente = [0, 1, 2]
    for kn in ids[0].ravel():
        m.fix(int(kn), "all")
    n = list(m.elements[1].nodes)
    m.elements[1].nodes = n[:4] + [n[7], n[4], n[5], n[6]]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("drei Würfel, der mittlere verdreht: Seiten im Inneren, kein Riss",
          len(sn) == 1 and sn[0].element == 1 and sn[0].wert == 6.0
          and not [b for b in bef if b.pruefung == "Riss im Netz"],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))

    m2 = Model("doppelt")
    m2.add_material(Material.steel("S235"))
    W = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    ecken2 = [int(m2.add_node(*p)) for p in W]
    k2 = _quaderkoerper(m2, ecken2)
    els2 = [int(i) for i in mesher.mesh_koerper(m2, k2, log=[], frei=False)]
    neu = {}
    for j in els2:
        e = m2.elements[j]
        if m2.nodes[e.nodes].mean(axis=0)[0] > 0.5:
            nn = []
            for kn in e.nodes:
                if abs(m2.nodes[kn][0] - 0.5) < 1e-9:
                    if kn not in neu:
                        neu[kn] = int(m2.add_node(*m2.nodes[kn]))
                    nn.append(neu[kn])
                else:
                    nn.append(kn)
            e.nodes = nn
    bef2 = dg._abnahme_volumenbilanz(m2, "K1", k2, els2)
    sn2 = [b for b in bef2 if b.pruefung == "Seiten im Inneren"]
    check("doppelte Knoten bei x = 0,5: Seiten im Inneren, kein Riss",
          len(sn2) == 1 and sn2[0].wert == 32.0
          and not [b for b in bef2 if b.pruefung == "Riss im Netz"],
          f"{len(neu)} doppelte Knoten; "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef2))


def test_windschiefe_randflaechen_ohne_dreiecksschleife():
    """Je windschiefer Randfläche lief eine Python-Schleife über 1024
    Dreiecke mit je einem Aufruf von punkt_dreieck_abstand (Gegenprüfung vom
    23.09.2026, M2): an 64 000 hex8 mit sechs windschiefen Flächen 4,5 bis
    5,4 s gegen 0,15 s mit ebenen. Jetzt der Fußpunkt nach Newton, gestapelt.

    Zuerst die Genauigkeit gegen eine feine Dreieckszerlegung (64 x 64
    Teilvierecke), dann die Zeit: windschief gegen eben am selben Netz. Das
    Verhältnis hängt nicht daran, wie belastet die Maschine gerade ist.
    """
    import time
    from statik3d import mesher, mesher3d as M3

    def sechsflaechner(schief, n=24):
        m = Model("zeit")
        m.add_material(Material.steel("S235"))
        E = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float)
        if schief:
            E += np.array([[0, 0, 0], [0.05, -0.1, 0.12], [0.1, 0.05, -0.1],
                           [-0.08, 0.1, 0.09], [0.1, 0.07, 0.0], [-0.06, 0.1, 0.15],
                           [0.12, -0.05, 0.2], [0.03, 0.12, -0.1]])
        k = _quaderkoerper(m, [int(m.add_node(*p)) for p in E])
        k.teilung = [n, n, n]
        els = [int(i) for i in mesher.mesh_koerper(m, k, log=[], frei=False, h=1.0 / n)]
        dauer = []
        for _ in range(3):
            t = time.perf_counter()
            bef = dg._abnahme_volumenbilanz(m, "K1", k, els)
            dauer.append(time.perf_counter() - t)
        return len(els), min(dauer), bef, len(dg._polyederhuelle(m, k)["bilinear"])

    n_e, t_eben, b_eben, _ = sechsflaechner(False)
    _, t_schief, b_schief, n_schief = sechsflaechner(True)
    check("sechs windschiefe Randflächen: höchstens das Dreifache der ebenen",
          n_schief == 6 and not b_eben and not b_schief and t_schief < 3.0 * t_eben + 0.02,
          f"{n_e} hex8: eben {t_eben * 1e3:.0f} ms, windschief {t_schief * 1e3:.0f} ms "
          f"({t_schief / t_eben:.1f}-fach)")

    X4 = np.array([[0, 0, 0], [3, 0.2, 0.4], [2.5, 1.1, -0.6], [0.1, 0.9, 0.8]], float)
    rng = np.random.default_rng(3)
    uv = rng.uniform(-0.3, 1.3, (60, 2))
    Q = dg._bilinear_punkt(X4, uv[:, 0], uv[:, 1]) + rng.normal(0.0, 0.1, (60, 3))
    P, T = dg._bilinear_gitter(X4, 64)
    a, b, c = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    fein = np.array([M3.punkt_dreieck_abstand(np.broadcast_to(x, a.shape), a, b, c).min()
                     for x in Q])
    newton = dg._bilinear_abstand(Q, X4)
    # Die Zerlegung liegt um hoechstens |d|/(16*64^2) neben der Flaeche,
    # und Newton misst einen Punkt der Flaeche: nie mehr als der wahre Abstand
    fehler = float(np.linalg.norm(X4[0] - X4[1] + X4[2] - X4[3])) / (16 * 64 ** 2)
    check("Fußpunkt nach Newton: nicht weiter als die feine Zerlegung",
          float((newton - fein).max()) <= fehler + 1e-12,
          f"größte Überschreitung {float((newton - fein).max()):.2e} "
          f"(Zerlegung genau auf {fehler:.1e})")


def _gestuft(verhaeltnis, dz=0.0, n=10, oben=False):
    """Abgestuftes hex8-Netz 1 x 1 x 1 m als Körper K1 (Gegenprüfung vom
    23.09.2026): Zellweiten geometrisch, die kleinste zur größten wie
    1 : verhaeltnis, fein bei x = y = 0 und bei z = 0 (``oben``: bei z = 1).
    Der Deckel ist z = 1 + dz·x·y; alle Lagen sind bilinear, das Netz ist
    also exakt. Element i·n² + j·n + k ist die Zelle (i, j, k)."""
    from statik3d import mesher
    q = verhaeltnis ** (1.0 / (n - 1))
    w = q ** np.arange(n)
    x = np.concatenate([[0.0], np.cumsum(w / w.sum())])
    z = 1.0 - x[::-1] if oben else x
    m = Model("gestuft")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 1.0, 1.0, 1.0, n, n, n, typ="hex8")
    for i in range(n + 1):
        for j in range(n + 1):
            for k in range(n + 1):
                m.nodes[ids[i, j, k]] = [x[i], x[j], z[k] * (1.0 + dz * x[i] * x[j])]
    k = _quaderkoerper(m, [ids[0, 0, 0], ids[n, 0, 0], ids[n, n, 0], ids[0, n, 0],
                           ids[0, 0, n], ids[n, 0, n], ids[n, n, n], ids[0, n, n]])
    k.elemente = list(range(len(m.elements)))
    for kn in ids[:, :, 0].ravel():
        m.fix(int(kn), "all")
    return m, k


def _verdrehen(m, i):
    """Deckelknoten des hex8 um eins versetzt (Nachtrag A); gibt die alten zurück."""
    n = list(m.elements[i].nodes)
    m.elements[i].nodes = n[:4] + [n[5], n[6], n[7], n[4]]
    return n


def test_abnahme_riss_misst_am_oertlichen_element():
    """Mangel 1 der Gegenprüfung vom 23.09.2026: die Riss-Regel maß gegen
    das größte Element im ganzen Körper (Zulage n·FLACH·h_max³). In
    abgestuften Netzen wurde ein verdrehter Sechsflächner damit zur WARNUNG
    „Riss im Netz … Der Körper stimmt": 50:1, Element 111, Volumen 1,343e-6
    → 8,95e-7 m³; bei 46af735 war es ein FEHLER. Ebenso ein fehlender, nicht
    flacher Tetraeder an der Platte mit Bohrung (40 von 40 Proben).

    Ein Riss ist ein Hohlraum, der **dünn** ist gegen seine eigenen Seiten:
    mittlere Dicke 2V/ΣA höchstens ABNAHME_RISS_DICKE mal die längste Kante
    der Gruppe - das hängt nur an der Stelle selbst, nicht an der Abstufung.
    """
    for verh in (50, 100):
        m, k = _gestuft(verh)
        _verdrehen(m, 111)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
        check(f"abgestuft {verh}:1, inneres Element verdreht: FEHLER, kein Riss",
              len(sn) == 1 and sn[0].stufe == "FEHLER" and sn[0].wert == 8.0
              and sn[0].element == 111
              and not [b for b in bef if b.pruefung == "Riss im Netz"],
              "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund")

    # Dasselbe 50:1-Netz in Tetraeder zerlegt (sechs je Zelle um die
    # Raumdiagonale 0-6, das Netz ist konform); ein Tetraeder der feinen
    # Zelle (1, 1, 1) fehlt. Zulage alt 4·FLACH·h_max³ = 9,4e-7 m³, der
    # Tetraeder hat 2,2e-7 m³ - die alte Regel nannte ihn einen Riss.
    m, k = _gestuft(50)
    hexe = [list(e.nodes) for e in m.elements]
    m.elements.clear()
    for c in hexe:
        for t in ((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6)):
            m.add_element("tet4", [int(c[x]) for x in t], "S235")
    k.elemente = list(range(len(m.elements)))
    ohne = dg.abnahme(m, warnungen=True)
    check("abgestuft 50:1 in Tetraedern: ohne Eingriff kein Befund",
          not [b for b in ohne if b.pruefung in _NETZ_BEFUNDE],
          "; ".join(f"{b.stufe} {b.pruefung}" for b in ohne))
    weg = 111 * 6
    k.elemente = [i for i in range(len(m.elements)) if i != weg]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("  ein Tetraeder der feinen Zelle fehlt: FEHLER mit 4 Seiten, kein Riss",
          len(sn) == 1 and sn[0].stufe == "FEHLER" and sn[0].wert == 4.0
          and not [b for b in bef if b.pruefung == "Riss im Netz"],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund")

    # Zwei Hohlraeume, die sich nur an einer Kante beruehren: ein fehlender
    # Tetraeder und ein langer flacher daneben. Zusammengezaehlt waere die
    # mittlere Dicke klein und das Ganze ein Riss - so ging an der Platte mit
    # Bohrung ein fehlender Tetraeder (Element 26949) neben einer Luecke des
    # Vernetzers durch. Getrennt ist der Tetraeder ein FEHLER, der flache ein Riss.
    def hohlraum(P):
        P = np.asarray(P, float)
        seiten = []
        for t, gegen in (((0, 1, 2), 3), ((0, 1, 3), 2), ((0, 2, 3), 1), ((1, 2, 3), 0)):
            s = 0.5 * np.cross(P[t[1]] - P[t[0]], P[t[2]] - P[t[0]])
            if s @ (P[gegen] - P[list(t)].mean(axis=0)) < 0:
                s = -s                          # in den Hohlraum hinein
            seiten.append((t, s))
        return seiten

    Pa = [[0, 0, 0], [1, 0, 0], [0.5, 0.866, 0], [0.5, 0.29, 0.8]]
    Pb = [[0, 0, 0], [1, 0, 0], [0.5, -4.0, 0.02], [0.5, -4.0, -0.02]]
    nummern = {(0, 0, 0): 0, (1, 0, 0): 1}
    F, Xf, S = [], [], []
    for P in (Pa, Pb):
        for t, s in hohlraum(P):
            kn = [nummern.setdefault(tuple(P[j]), len(nummern)) for j in t]
            F.append(kn + [-1])
            Xf.append([P[j] for j in t] + [P[t[0]]])
            S.append(s)
    F, Xf, S = np.array(F), np.array(Xf, float), np.array(S)
    # Die Elemente daneben so dick wie der Tetraeder-Hohlraum selbst
    t_a = 2.0 * abs(float(np.linalg.det(np.array(Pa[1:]) - Pa[0]))) / 6.0 / float(
        np.linalg.norm(S[:4], axis=1).sum())
    riss, _V, _lu, _v = dg._gruppen_im_inneren(None, {}, [], F, Xf, S, np.zeros(8, int),
                                              np.ones(8, bool), None, np.full(8, t_a))
    check("  zwei Hohlräume an einer Kante: der Tetraeder kein Riss, der flache ein Riss",
          not riss[:4].any() and riss[4:].all(), str(riss.astype(int).tolist()))
    # Mit der Größe (ABNAHME_RISS_FLACH, Nebenbefund B050): L = 30 lässt je
    # vier Seiten 2e-6 · 30³ = 0,054 zu - der flache Hohlraum (0,027) bleibt
    # ein Riss, obwohl beide zusammen (0,142) zu groß sind; getrennt wird nach
    # der Form, die Größe zählt je Stück. Mit L = 20 (0,016) ist auch er zu groß.
    r30 = dg._gruppen_im_inneren(None, {}, [], F, Xf, S, np.zeros(8, int), np.ones(8, bool),
                                 None, np.full(8, t_a), L_koerper=30.0)[0]
    r20 = dg._gruppen_im_inneren(None, {}, [], F, Xf, S, np.zeros(8, int), np.ones(8, bool),
                                 None, np.full(8, t_a), L_koerper=20.0)[0]
    check("  mit der Größe: getrennt nach der Form, die Größe je Stück",
          not r30[:4].any() and r30[4:].all() and not r20.any(),
          f"L 30: {r30.astype(int).tolist()}, L 20: {r20.astype(int).tolist()}")

    # Welche Dicke der Elemente daneben zaehlt? Der Median ueber die Seiten -
    # ein einzelner dicker oder duenner Nachbar entscheidet nicht. Mit dem
    # groessten oder dem kleinsten Wert statt des Medians bestand die Suite
    # ganz (Nebenbefund B145). Der flache Hohlraum allein (t/L 0,3 %), die
    # Dicken seiner vier Nachbarn gestreut: Median 1,0 t wie beim fehlenden
    # Sechsflaechner (gemessen 1,00 bis 1,01) ist kein Riss, auch wenn ein
    # Nachbar zehnmal so dick ist; Median 2 t (t/Nachbar 0,5, im Bereich der
    # Luecken des freien Vernetzers bis 0,579) ist ein Riss, auch wenn ein
    # Nachbar nur halb so dick ist.
    t_b = 2.0 * abs(float(np.linalg.det(np.array(Pb[1:]) - Pb[0]))) / 6.0 / float(
        np.linalg.norm(S[4:], axis=1).sum())
    ergebnis = []
    for streu, soll in (((1.0, 1.0, 1.0, 10.0), False), ((0.5, 2.0, 2.0, 2.0), True)):
        r4, _V, _lu, _v = dg._gruppen_im_inneren(None, {}, [], F[4:], Xf[4:], S[4:], np.zeros(4, int),
                                                 np.ones(4, bool), None, t_b * np.array(streu))
        ergebnis.append(bool(r4.all()) == soll and bool(r4.any()) == soll)
    check("  Nachbardicken gestreut: es entscheidet der Median, nicht der dickste oder dünnste",
          all(ergebnis), f"Median t: kein Riss {ergebnis[0]}, Median 2 t: Riss {ergebnis[1]}")


_KUHN = ((0, 1, 2, 6), (0, 2, 3, 6), (0, 3, 7, 6), (0, 7, 4, 6), (0, 4, 5, 6), (0, 5, 1, 6))


def _in_kuhn(m, k):
    """Jede hex8-Zelle in sechs Tetraeder um die Raumdiagonale 0-6 (konform);
    Tetraeder j der Zelle c ist Element 6 c + j."""
    hexe = [list(e.nodes) for e in m.elements]
    m.elements.clear()
    for c in hexe:
        for t in _KUHN:
            m.add_element("tet4", [int(c[x]) for x in t], "S235")
    k.elemente = list(range(len(m.elements)))


def _gleichmaessig(lx, ly, lz, n):
    """hex8-Netz n x n x n über lx x ly x lz als Körper K1; Element
    i·n² + j·n + k ist die Zelle (i, j, k)."""
    from statik3d import mesher
    m = Model("gleich")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", lx, ly, lz, n, n, n, typ="hex8")
    k = _quaderkoerper(m, [ids[0, 0, 0], ids[n, 0, 0], ids[n, n, 0], ids[0, n, 0],
                           ids[0, 0, n], ids[n, 0, n], ids[n, n, n], ids[0, n, n]])
    k.elemente = list(range(len(m.elements)))
    for kn in ids[:, :, 0].ravel():
        m.fix(int(kn), "all")
    return m, k


def test_abnahme_findet_gefaltetes_tetraedernetz():
    """B112 (Nebenbefund der Fehlerrunden vom 22./23.09.2026): Formgüte
    (netzguete) und Elementvolumen rechnen beim Tetraeder mit dem Betrag des
    Volumens. Ein Netz, in dem ein Knoten durch die Gegenseite seiner
    Tetraeder geschoben ist, ging darum ohne Befund durch die Abnahme: am
    10 × 10 × 10-Kuhn-Netz Knoten 665 um 1,2·h verschoben, sechs Tetraeder
    umgestülpt (det J ≤ 0), abnahme(warnungen=True) = []. Ein umgestülpter
    Sechsflächner ergibt dagegen FEHLER Elementgüte.

    Die Abnahme prüft jetzt je gemeinsamer Seite zweier Tetraeder, ob ihre
    Gegenknoten auf verschiedenen Seiten der Ebene liegen. Das hängt nicht an
    der Knotenfolge: zwei vertauschte Knoten in einem Tetraeder sind dasselbe
    Tetraeder mit anderer Nummerierung, die Rechnung ist gleich (gemessen am
    23.09.2026 max|Δu| 1,5e-20 m bei max|u| 4,4e-6 m), und das bleibt ohne
    Befund.
    """
    from statik3d.elements import solid as sl

    def kurz(bef):
        return "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"

    def kuhn():
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 10)
        _in_kuhn(m, k)
        return m, k

    m, k = kuhn()
    mitte = int(np.argmin(np.linalg.norm(m.nodes - np.array([0.5, 0.5, 0.5]), axis=1)))
    check("ungestörtes Kuhn-Netz 10 × 10 × 10: kein Befund, kein Tetraeder mit det J ≤ 0",
          dg.abnahme(m, warnungen=True) == [] and sl.jacobi_pruefung(m) == [],
          kurz(dg.abnahme(m, warnungen=True)))
    umgestuelpt = [3266, 3267, 3271, 3328, 3330, 3335]
    for schub in (1.2, 1.5):
        m, k = kuhn()
        m.nodes[mitte] = m.nodes[mitte] + np.array([schub * 0.1, 0.0, 0.0])
        neg = sorted(e for e, _t, _d in sl.jacobi_pruefung(m))
        bef = dg.abnahme(m, warnungen=True)
        fa = [b for b in bef if b.pruefung == "Netz gefaltet"]
        check(f"Knoten {mitte} um {schub}·h verschoben: FEHLER Netz gefaltet mit den "
              "sechs umgestülpten Tetraedern",
              neg == umgestuelpt and [b.pruefung for b in bef] == ["Netz gefaltet"]
              and fa[0].stufe == "FEHLER" and sorted(fa[0].elemente) == umgestuelpt
              and fa[0].wert == 6.0 and mitte in fa[0].knoten
              and all(str(e) in fa[0].text for e in umgestuelpt),
              f"det J ≤ 0: {neg}; {kurz(bef)}; "
              + (f"Elemente {sorted(fa[0].elemente)}, Knoten {fa[0].knoten}" if fa else ""))
        check("  und abnahme() ohne Warnungen fragt vor dem Rechnen nach",
              [b.pruefung for b in dg.abnahme(m)] == ["Netz gefaltet"],
              kurz(dg.abnahme(m)))
    # Gegenprobe: um 0,5·h verschoben bleibt jedes Tetraeder aufrecht
    m, k = kuhn()
    m.nodes[mitte] = m.nodes[mitte] + np.array([0.05, 0.0, 0.0])
    check("  Gegenprobe: um 0,5·h verschoben ist nichts gefaltet - kein Befund",
          sl.jacobi_pruefung(m) == [] and dg.abnahme(m, warnungen=True) == [],
          kurz(dg.abnahme(m, warnungen=True)))
    # Faellt die Pruefung aus, ist das nicht „nichts gefunden"
    echt = getattr(dg, "_abnahme_faltung", None)

    def wirft(*a, **kw):
        raise RuntimeError("Seitentabelle nicht aufzubauen")

    dg._abnahme_faltung = wirft
    try:
        mit, ohne = dg.abnahme(m, warnungen=True), dg.abnahme(m)
    finally:
        if echt is None:
            del dg._abnahme_faltung
        else:
            dg._abnahme_faltung = echt
    check("  fällt die Prüfung aus: WARNUNG „Faltung nicht geprüft“, hält nicht an",
          [(b.stufe, b.pruefung) for b in mit] == [("WARNUNG", "Faltung nicht geprüft")]
          and ohne == [], kurz(mit))

    # Zwei Knoten in Element 3330 vertauscht: dasselbe Tetraeder, andere
    # Nummerierung - die Rechnung ist gleich, also kein Befund
    ergebnisse = []
    for tauschen in (False, True):
        m, k = kuhn()
        for i, p in enumerate(m.nodes):
            if abs(p[2] - 1.0) < 1e-12:
                m.load_node(i, Fx=1000.0, Fz=-2000.0)
        if tauschen:
            n = list(m.elements[3330].nodes)
            n[0], n[1] = n[1], n[0]
            m.elements[3330].nodes = n
            neg = sl.jacobi_pruefung(m)
            bef = dg.abnahme(m, warnungen=True)
        r = solver.solve_static(m)
        ergebnisse.append(np.asarray(r.u, float).reshape(m.nn, -1)[:, :3])
    du = float(np.abs(ergebnisse[1] - ergebnisse[0]).max())
    u = float(np.abs(ergebnisse[0]).max())
    check("zwei Knoten in Element 3330 vertauscht: det J < 0, Rechnung gleich, kein Befund",
          [e for e, _t, _d in neg] == [3330] and du <= 1e-12 * u and bef == [],
          f"det J ≤ 0: {[e for e, _t, _d in neg]}; max|Δu| {du:.2g} m bei max|u| {u:.2g} m; "
          f"{kurz(bef)}")


def test_faltungsbefund_nennt_das_uebervolumen_der_volumenbilanz():
    """Gegenprüfung vom 24.09.2026 zu B112, Mangel 1: jeder Befund „Netz
    gefaltet“ sagte „Formgüte und Volumenbilanz sehen das nicht“ - eine
    allgemeine Regel aus der einen Messung am Kuhn-Netz 10 × 10 × 10. Sie ist
    falsch: ein umgestülptes Tetraeder geht mit +|V| statt −|V| ins
    Netzvolumen ein, das Netz ist um das Doppelte seines Volumens zu groß, und
    wo die Volumenbilanz läuft (hier für K1, einen Quader), meldet sie das,
    sobald es über ihrer Grenze liegt; wo sie nicht läuft, siehe
    test_faltungsbefund_nur_mit_laufender_volumenbilanz. Gemessen
    am 24.09.2026: Kuhn-Netz 4 × 4 × 4 (Zellen 0,25 m), Knoten 62 um 1,2·h
    verschoben - sechs Tetraeder umgestülpt, Σ|V| − 1 m³ = 2 Σ|V_um| = 6250 cm³,
    und im selben Protokoll FEHLER Volumenbilanz 0,625 % neben dem Satz, sie
    sehe es nicht. Am Kuhn-Netz 10 × 10 × 10 sind es 400 cm³ (0,04 %), dort
    meldet die Volumenbilanz nichts. Der Befund nennt jetzt das Übervolumen
    seiner Tetraeder, und das muss zur Volumenbilanz passen.
    """
    from statik3d.spannungen import dezimal

    for n, erwartet_vb in ((4, True), (10, False)):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, n)
        _in_kuhn(m, k)
        mitte = int(np.argmin(np.linalg.norm(m.nodes - np.array([0.5, 0.5, 0.5]), axis=1)))
        m.nodes[mitte] = m.nodes[mitte] + np.array([1.2 / n, 0.0, 0.0])
        # Unabhaengig vom Pruefling: signierte Volumina, Wuerfel 1 m³
        P = np.asarray(m.nodes, float)[np.array([e.nodes for e in m.elements])]
        V = np.einsum("ij,ij->i", P[:, 1] - P[:, 0],
                      np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0])) / 6.0
        ueber = float(np.abs(V).sum() - 1.0)
        bef = dg.abnahme(m, warnungen=True)
        fa = [b for b in bef if b.pruefung == "Netz gefaltet"]
        vb = [b for b in bef if b.pruefung == "Volumenbilanz"]
        menge = f"{dezimal(ueber * 1e6)} cm³"
        check(f"Kuhn-Netz {n} × {n} × {n}, Knoten {mitte} um 1,2·h: ein Befund „Netz "
              f"gefaltet“ mit den {int((V < 0).sum())} Tetraedern mit V < 0, sein Text "
              f"nennt das Übervolumen {menge} = Σ|V| − 1 m³",
              len(fa) == 1 and sorted(fa[0].elemente) == sorted(np.nonzero(V < 0)[0].tolist())
              and menge in fa[0].text,
              "; ".join(b.text for b in fa) or "kein Befund Netz gefaltet")
        check("  und bestreitet nicht, was die Volumenbilanz sieht",
              all("sehen das nicht" not in b.text and "sieht das nicht" not in b.text
                  for b in fa),
              "; ".join(b.text for b in fa))
        check(f"  Volumenbilanz {'meldet' if erwartet_vb else 'meldet nicht'}: Abweichung "
              f"{dezimal(ueber * 100)} % gegen die Grenze "
              f"{dezimal(dg.ABNAHME_VOLUMENBILANZ * 100, 1)} %",
              (len(vb) == 1 and abs(vb[0].wert - ueber) <= 1e-9) if erwartet_vb else vb == [],
              "; ".join(f"{b.pruefung} {b.wert:.6g}" for b in vb) or "kein Befund Volumenbilanz")


def _signierte_volumina(m, els):
    """V je tet4 mit Vorzeichen - unabhängig vom Prüfling gerechnet."""
    P = np.asarray(m.nodes, float)[np.array([m.elements[i].nodes for i in els])]
    return np.einsum("ij,ij->i", P[:, 1] - P[:, 0],
                     np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0])) / 6.0


def test_faltungsbefund_nur_mit_laufender_volumenbilanz():
    """Zweite Gegenprüfung vom 24.09.2026 zu B112, Mängel 1 und 4: jeder
    Befund „Netz gefaltet“ endete mit „die Volumenbilanz meldet das erst über
    ihrer Grenze“. Die Volumenbilanz läuft aber nur für Elemente in einem
    Körper (_abnahme_netz geht model.koerper durch) und nur, wo die Hülle aus
    geraden Randlinien feststeht (_polyederhuelle, sonst gibt
    _abnahme_volumenbilanz nichts zurück). Gemessen am 24.09.2026, Stand
    4a139f3: Kuhn-Netz 4 × 4 × 4 ohne Körper (als Nastran-BDF gelesen: 125
    Knoten, 384 tet4, kein Körper), Knoten 62 um 1,2·h - Übervolumen 0,625 %
    über der Grenze 0,5 %: nur „Netz gefaltet“, dessen Text die Meldung der
    Volumenbilanz versprach, und kein Befund „Volumenbilanz“; Zylinder aus
    Bogenlinien (tests.test_mesher3d.buchse, h 0,3, 1006 tet4), Knoten 143
    um 1,3·h - Übervolumen 1,642 % des ungefalteten Netzes, ebenso (seit dem
    Vernetzer vom 23.09.2026: 1022 tet4, Knoten 142, 1,643 %). Der Befund
    sagt jetzt je Fall, was ist: mit laufender Volumenbilanz deren Abweichung,
    sonst dass es keine gab. Beim Zylinder liegt das Sehnennetz schon
    ungefaltet 1,637 % unter π r² H, das gefaltete 0,022 % darunter (dritte
    Gegenprüfung, 24.09.2026; am neuen Netz 0,021 %); die Prüfung hält auch
    diese Zahlen fest.
    """
    import tempfile
    from statik3d import mesher3d as M3
    from statik3d.importers import nastran
    from statik3d.spannungen import dezimal
    import tests.test_mesher3d as TM

    alt_satz = "erst über ihrer Grenze"

    def teile(bef):
        return ([b for b in bef if b.pruefung == "Netz gefaltet"],
                [b for b in bef if b.pruefung == "Volumenbilanz"])

    # (a) Kuhn-Netz 4 x 4 x 4 im Koerper K1 (Quader: die Volumenbilanz laeuft)
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 4)
    _in_kuhn(m, k)
    mitte = int(np.argmin(np.linalg.norm(m.nodes - np.array([0.5, 0.5, 0.5]), axis=1)))
    m.nodes[mitte] = m.nodes[mitte] + np.array([0.3, 0.0, 0.0])
    fa, vb = teile(dg.abnahme(m, warnungen=True))
    check("Kuhn 4 × 4 × 4 im Körper K1: „Netz gefaltet“ nennt die Volumenbilanz von K1 "
          "mit ihrer Abweichung, und sie meldet",
          len(fa) == 1 and len(vb) == 1 and "Volumenbilanz von Volumen K1" in fa[0].text
          and f"Abweichung {dezimal(vb[0].wert * 100)} %" in fa[0].text
          and alt_satz not in fa[0].text,
          "; ".join(b.text for b in fa + vb) or "keine Befunde")
    # Bricht die Volumenbilanz nach dem Rechnen ab, geht ihr Befund verloren
    # („Volumenbilanz nicht geprüft“) - dann darf sich der Faltungsbefund
    # nicht auf sie berufen
    echt = dg._abnahme_volumenbilanz

    def bricht_ab(*a, **kw):
        echt(*a, **kw)
        raise RuntimeError("nach der Bilanz abgebrochen")

    dg._abnahme_volumenbilanz = bricht_ab
    try:
        bef = dg.abnahme(m, warnungen=True)
    finally:
        dg._abnahme_volumenbilanz = echt
    fa, vb = teile(bef)
    check("  bricht die Volumenbilanz ab (WARNUNG „nicht geprüft“), sagt der "
          "Faltungsbefund, dass keine lief",
          vb == [] and any(b.pruefung == "Volumenbilanz nicht geprüft" for b in bef)
          and len(fa) == 1 and "für Volumen K1 lief keine Volumenbilanz" in fa[0].text,
          "; ".join(f"{b.stufe} {b.pruefung}" for b in bef) + " | "
          + "; ".join(b.text for b in fa))

    # (b) dasselbe Netz ohne Koerper - wie aus einem Import, einmal ueber den
    # Nastran-Leser, einmal mit geleertem model.koerper
    V = _signierte_volumina(m, range(len(m.elements)))
    ueber = float((np.abs(V).sum() - V.sum()) / V.sum())
    zeilen = ["BEGIN BULK", "MAT1,1,2.1+11,,0.3,7850.", "PSOLID,1,1"]
    zeilen += [f"GRID,{i + 1},,{p[0]:.6f},{p[1]:.6f},{p[2]:.6f}"
               for i, p in enumerate(np.asarray(m.nodes, float))]
    zeilen += [f"CTETRA,{j + 1},1," + ",".join(str(int(x) + 1) for x in e.nodes)
               for j, e in enumerate(m.elements)]
    with tempfile.TemporaryDirectory() as ordner:
        pfad = os.path.join(ordner, "gefaltet.bdf")
        with open(pfad, "w") as f:
            f.write("\n".join(zeilen + ["ENDDATA"]) + "\n")
        mi = nastran.import_bdf(pfad, log=[])
    m.koerper.clear()
    for titel, mm in (("Nastran-Import", mi), ("model.koerper geleert", m)):
        fa, vb = teile(dg.abnahme(mm, warnungen=True))
        check(f"  ohne Körper ({titel}, {len(mm.elements)} tet4, "
              f"{len(getattr(mm, 'koerper', None) or {})} Körper): Übervolumen "
              f"{dezimal(ueber * 100)} % über der Grenze, keine Volumenbilanz - der Befund "
              "sagt das, statt eine Meldung zu versprechen",
              ueber > dg.ABNAHME_VOLUMENBILANZ and len(fa) == 1 and vb == []
              and "keiner Volumenbilanz" in fa[0].text and alt_satz not in fa[0].text,
              "; ".join(b.text for b in fa + vb) or "keine Befunde")

    # (c) Zylinder aus Bogenlinien: keine Huelle ohne Naeherung, keine Bilanz
    m = TM.neues_modell()
    k = TM.buchse(m, 0.5, 0.0, 1.0)
    h = 0.3
    m.netz.ziellaenge = h
    els = [int(x) for x in M3.mesh_koerper_frei(m, k, log=[])]
    X = np.asarray(m.nodes, float)
    benutzt = np.unique(np.array([m.elements[i].nodes for i in els]).ravel())
    r = np.linalg.norm(X[benutzt, :2], axis=1)
    innen = benutzt[(r < 0.5 - 0.6 * h) & (X[benutzt, 2] > 0.6 * h)
                    & (X[benutzt, 2] < 1 - 0.6 * h)]
    kn = int(innen[np.argmin(np.linalg.norm(X[innen] - np.array([0, 0, 0.5]), axis=1))])
    V0 = _signierte_volumina(m, els)
    m.nodes[kn] = X[kn] + np.array([1.3 * h, 0.0, 0.0])
    V = _signierte_volumina(m, els)
    ueber = float((np.abs(V).sum() - V.sum()) / V.sum())
    # Dritte Gegenpruefung vom 24.09.2026: die Handbuecher sagten fuer den
    # Zylinder „Σ |V| − V_Körper = 2 Σ |V_um|“ und „1,642 % zu viel“. Am Stand
    # af2fb40 gemessen: Σ|V| − π r² H − 2 Σ|V_um| = −1,286·10⁻² m³, denn das
    # Sehnennetz liegt schon ungefaltet 1,637 % unter π r² H. Die 1,642 % sind
    # auf das ungefaltete Netz Σ V bezogen, gegen den Zylinder ist das
    # gefaltete Netz 0,022 % zu klein. Die Pruefung haelt diese Zahlen des
    # Textes fest: aendert der Vernetzer sein Netz, faellt sie durch, und die
    # Handbuecher sind nachzumessen. So geschehen mit dem Vernetzer vom
    # 23.09.2026 (Fable-Sitzung): 1022 statt 1006 tet4, Knoten 142 statt 143,
    # wieder 8 umgestuelpte, 2 Σ|V_um| 12 693 cm³ = 1,643 %, Σ V und das
    # Sehnendefizit 1,637 % gleich, gefaltet 0,021 % (−162 cm³) unter dem
    # Zylinder (nachgemessen 24.09.2026).
    vk = np.pi * 0.5 ** 2 * 1.0
    s0, s_betrag = float(V0.sum()), float(np.abs(V).sum())
    um2 = 2.0 * float(np.abs(V[V < 0]).sum())
    check(f"  Zylinder: Σ|V| − Σ V = 2 Σ|V_um| = {um2 * 1e6:.1f} cm³ = "
          f"{um2 / s0 * 100:.3f} % des ungefalteten Netzes (Σ V vor und nach dem Schub "
          f"gleich); gegen π r² H liegt das Sehnennetz {(s0 - vk) / vk * 100:.3f} %, das "
          f"gefaltete {(s_betrag - vk) / vk * 100:.3f} % - wie in Theorie- und "
          "Benutzerhandbuch (1,643 %, −1,637 %, −0,021 %)",
          abs(s_betrag - s0 - um2) <= 1e-12 and abs(float(V.sum()) - s0) <= 1e-12
          and round(um2 / s0 * 100, 3) == 1.643 and round((s0 - vk) / vk * 100, 3) == -1.637
          and round((s_betrag - vk) / vk * 100, 3) == -0.021,
          f"Σ|V| − Σ V − 2 Σ|V_um| = {s_betrag - s0 - um2:.3e} m³, "
          f"Σ V nachher − vorher = {float(V.sum()) - s0:.3e} m³, "
          f"Σ|V| − π r² H − 2 Σ|V_um| = {s_betrag - vk - um2:.3e} m³")
    fa, vb = teile(dg.abnahme(m, warnungen=True))
    check(f"  Zylinder aus Bogenlinien ({len(els)} tet4), Knoten {kn} um 1,3·h: "
          f"Übervolumen {dezimal(ueber * 100)} %, keine Hülle ohne Näherung, keine "
          "Volumenbilanz - der Befund sagt das",
          dg._polyederhuelle(m, k) is None and ueber > dg.ABNAHME_VOLUMENBILANZ
          and len(fa) == 1 and vb == [] and int((V < 0).sum()) == len(fa[0].elemente)
          and f"für Volumen {k.name} lief keine Volumenbilanz" in fa[0].text
          and alt_satz not in fa[0].text,
          "; ".join(b.text for b in fa + vb) or "keine Befunde")


def test_faltungsbefund_nennt_nur_gemessene_abhilfe():
    """Zweite Gegenprüfung vom 24.09.2026 zu B112, Mangel 3: jeder Befund
    „Netz gefaltet“ riet „Die Knoten zurücksetzen oder neu vernetzen.“ Bei
    einer Faltung, die der Vernetzer selbst erzeugt, hat der Anwender keinen
    Knoten verschoben, und der eigene Vernetzer ergibt mit denselben
    Einstellungen dasselbe Netz. Gemessen am 24.09.2026: zwei Würfel
    übereinander mit je eigener Trennfläche (tests.test_fugen.zwei_bloecke,
    unten h 0,5, oben frei vernetzt) - oben mit h 0,12 bis 0,18 gefaltet
    (12 bis 20 umgestülpte), mit 0,19, 0,2 und 0,25 nicht; jeder Aufbau
    zweimal bitgleich samt Befunden. Der Befund nennt jetzt genau das; ändert
    sich der Vernetzer, fällt diese Prüfung durch, und der Text ist
    nachzumessen.
    """
    import tests.test_fugen as TF

    def aufbau(h_oben):
        m = TF.zwei_bloecke("eigene", 0.5, h_oben)
        fa = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Netz gefaltet"]
        return m, fa

    m1, fa1 = aufbau(0.15)
    m2, fa2 = aufbau(0.15)
    gleich = (np.array_equal(np.asarray(m1.nodes), np.asarray(m2.nodes))
              and [list(e.nodes) for e in m1.elements] == [list(e.nodes) for e in m2.elements]
              and [b.elemente for b in fa1] == [b.elemente for b in fa2])
    check("zwei Würfel, eigene Trennflächen, oben h 0,15: gefaltet, und derselbe "
          "Aufbau ergibt dasselbe Netz mit denselben Befunden",
          len(fa1) > 0 and gleich, f"{len(fa1)} Befunde, gleich: {gleich}")
    check("  kein Befund rät mehr „Knoten zurücksetzen oder neu vernetzen“; jeder "
          "nennt, dass derselbe Vernetzer dieselbe Faltung ergibt, und was half",
          fa1 and all("zurücksetzen" not in b.text and "neu vernetzen" not in b.text
                      and "dasselbe Netz mit derselben Faltung" in b.text
                      and "0.19, 0.2 und 0.25 m" in b.text for b in fa1),
          fa1[0].text if fa1 else "kein Befund")
    # Die Zahlen im Text: gefaltet von 0,12 bis 0,18, nicht bei 0,19/0,2/0,25
    falsch = []
    for h_oben in (0.12, 0.13, 0.14, 0.16, 0.17, 0.18, 0.19, 0.2, 0.25):
        m, fa = aufbau(h_oben)
        els = list(m.koerper["Oben"].elemente)
        um = int((_signierte_volumina(m, els) < 0).sum())
        if (h_oben < 0.185) != (len(fa) > 0 and um > 0):
            falsch.append(f"h {h_oben}: {um} umgestülpt, {len(fa)} Befunde")
    check("  die Messung im Befundtext gilt noch: oben 0,12 bis 0,18 gefaltet, "
          "0,19, 0,2 und 0,25 nicht", not falsch, "; ".join(falsch) or "wie im Text")


def test_abnahme_riss_an_laenglichen_zellen():
    """Zweite Gegenprüfung vom 23.09.2026, Mängel 1 und 2: die Riss-Regel der
    zweiten Kur maß die Dicke eines Hohlraums nur an der längsten Kante
    seiner Seiten (t/L ≤ 5 %). In länglichen Zellen folgt die Dicke der
    kurzen Seite, L der langen - ein verdrehter Sechsflächner in einer Zelle
    100 × 100 × 200 mm wurde so zur WARNUNG „Riss im Netz … Der Körper
    stimmt", ohne Rückfrage vor dem Rechnen (t/L 4,37 %; bei 46af735 und
    3f5ae87 FEHLER). Abgestuft 50:1 gingen von je 512 inneren Zellen 357
    verdrehte, 72 fehlende Sechsflächner und 340 fehlende Kuhn-Tetraeder als
    Riss durch. Und ein Sechsflächner im Inneren (Element 292 des
    8 × 8 × 8-Netzes), der an den vier Knoten einer Seite losgelöst ist
    (doppelte Knoten), umschließt mit den Nachbarn einen Hohlraum ohne
    Volumen: WARNUNG „Riss im Netz 10". Liegt die losgelöste Seite auf der
    Hülle, bleiben die Seiten offen (gemessen 23.09.2026 an den Elementen 288
    und 295: 8 Seiten, ihr Rand auf der Hülle).

    Jetzt muss ein Riss auch dünn sein gegen die Elemente daneben
    (ABNAHME_RISS_NACHBAR), und verdrehte Elemente und doppelte Knoten sind
    nie ein Riss.
    """
    def kurz(bef):
        return "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund"

    # Verdrehter Sechsflaechner, gleichmaessiges Netz, Zellen 100 x 100 x 200 mm
    m, k = _gleichmaessig(1.0, 1.0, 2.0, 10)
    _verdrehen(m, 444)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("Zelle 100 × 100 × 200 mm, Element 444 verdreht: FEHLER Seiten im Inneren 8, kein Riss",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 8.0)]
          and bef[0].element == 444, kurz(bef))
    check("  und abnahme() ohne Warnungen fragt vor dem Rechnen nach",
          [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
          str([(b.stufe, b.pruefung) for b in dg.abnahme(m)]))

    # Abgestuft: die Zellen (1, 1, k) werden nach oben immer laenglicher
    # (20:1: 20,5 x 20,5 x 20,5 bis 20,5 x 20,5 x 210,5 mm, 50:1: 11 x 11 x 11
    # bis 11 x 11 x 231 mm)
    for verh in (20, 50):
        m, k = _gestuft(verh)
        still = []
        for kk in range(1, 9):
            e = 110 + kk
            alt = _verdrehen(m, e)
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            m.elements[e].nodes = alt
            if [(b.stufe, b.pruefung) for b in bef] != [("FEHLER", "Seiten im Inneren")]:
                still.append(f"{e}: {kurz(bef)}")
            k.elemente = [x for x in range(1000) if x != e]
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            k.elemente = list(range(1000))
            if ([(b.stufe, b.pruefung, b.wert) for b in bef]
                    != [("FEHLER", "Seiten im Inneren", 6.0)]):
                still.append(f"{e} fehlt: {kurz(bef)}")
        check(f"  abgestuft {verh}:1, Zellen 111 bis 118 verdreht oder fehlend: "
              "je FEHLER, kein Riss", not still, "; ".join(still))

    # Fehlender Kuhn-Tetraeder in denselben Zellen (50:1)
    m, k = _gestuft(50)
    _in_kuhn(m, k)
    alle = list(k.elemente)
    still = []
    for kk in range(1, 9):
        weg = (110 + kk) * 6
        k.elemente = [x for x in alle if x != weg]
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        if [(b.stufe, b.pruefung, b.wert) for b in bef] != [("FEHLER", "Seiten im Inneren", 4.0)]:
            still.append(f"{weg}: {kurz(bef)}")
    check("  Kuhn 50:1, Tetraeder 0 der Zellen 111 bis 118 fehlt: je FEHLER, kein Riss",
          not still, "; ".join(still))
    # Von oben begrenzt ABNAHME_RISS_NACHBAR der fehlende Kuhn-Tetraeder mit
    # dem kleinsten Verhaeltnis t / Dicke der Nachbarn unter denen, die t/L
    # allein zum Riss machte (Nebenbefund B145: mit 0,85 und 1,0 bestand die
    # Suite ganz). Gemessen 23.09.2026 an den inneren Zellen (1 bis 8 je
    # Richtung) der Kuhn-Zerlegung abgestuft 5:1 / 20:1 / 50:1: kleinstes
    # t/Nachbar 0,917 / 0,877 / 0,865, hier Element 710 (Zelle 118, t/L
    # 0,79 %). Zwischen 0,579 (Bohrung, test_abnahme_luecken_des_vernetzers_
    # sind_risse) und 0,865 trennt keine Messung.
    tl, tn = _tetraeder_masse(m, alle)
    innen = np.array([all(1 <= z <= 8 for z in (e // 600, (e // 60) % 10, (e // 6) % 10))
                      for e in alle])
    kand = np.nonzero(innen & (tl <= dg.ABNAHME_RISS_DICKE))[0]
    j = int(kand[np.argmin(tn[kand])])
    k.elemente = [x for x in alle if x != alle[j]]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    k.elemente = alle
    check("  Kuhn 50:1, fehlender Tetraeder mit dem kleinsten t/Nachbar (unter 0,87): FEHLER 4",
          tn[j] < 0.87 and [(b.stufe, b.pruefung, b.wert) for b in bef]
          == [("FEHLER", "Seiten im Inneren", 4.0)],
          f"Element {alle[j]}: t/L {tl[j] * 100:.2f} %, t/Nachbar {tn[j]:.3f}; " + kurz(bef))

    # Doppelte Knoten: die vier Bodenknoten des inneren Elements 292 durch
    # eigene am selben Ort ersetzt - das Element haengt nur noch am Deckel
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    nd = list(m.elements[292].nodes)
    m.elements[292].nodes = [int(m.add_node(*m.nodes[x])) for x in nd[:4]] + nd[4:]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("Element 292 an vier Knoten losgelöst (doppelte Knoten): FEHLER 10, kein Riss",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 10.0)]
          and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"], kurz(bef))
    # ... und im Tetraedernetz, wo keine Kante „verdreht" ist: ein Knoten
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    _in_kuhn(m, k)
    e = 292 * 6
    nd = list(m.elements[e].nodes)
    m.elements[e].nodes = [int(m.add_node(*m.nodes[nd[0]]))] + nd[1:]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  Kuhn-Tetraeder an einem Knoten losgelöst: FEHLER 6, kein Riss",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)],
          kurz(bef))
    # Doppelt heisst naeher als ABNAHME_FUGENNAEHE (1e-6 m), nicht nur
    # deckungsgleich: Bis hierher lagen alle doppelten Knoten der Suite genau
    # aufeinander, und mit der Toleranz 0 bestand sie ganz (Nebenbefund
    # B043). Derselbe Tetraeder, der neue Knoten 5e-7 m daneben: mit der
    # Toleranz 0 war das „WARNUNG Riss im Netz 6“ (gemessen 23.09.2026).
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    _in_kuhn(m, k)
    nd = list(m.elements[e].nodes)
    m.elements[e].nodes = [int(m.add_node(*(m.nodes[nd[0]] + [5e-7, 0.0, 0.0])))] + nd[1:]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  … der neue Knoten 5e-7 m daneben (unter ABNAHME_FUGENNAEHE): FEHLER 6, kein Riss",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)],
          kurz(bef))

    # Verdrehte Elemente der obersten Lage unter windschiefem Deckel
    # (Gegenpruefung: 75 von 324 Faellen nur WARNUNG Riss 8)
    still = []
    for verh, dz, zellen in ((20, 0.5, (159, 519, 729, 289)), (1, 1.0, (729, 289, 889))):
        m, k = _gestuft(verh, dz=dz, oben=True)
        for e in zellen:
            alt = _verdrehen(m, e)
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            m.elements[e].nodes = alt
            if [(b.stufe, b.pruefung) for b in bef] != [("FEHLER", "Seiten im Inneren")]:
                still.append(f"{verh}:1 dz {dz} Element {e}: {kurz(bef)}")
    check("windschiefer Deckel (20:1 dz 0,5 und 1:1 dz 1,0), oberste Lage verdreht: je FEHLER",
          not still, "; ".join(still))


def test_abnahme_windschief_misst_am_oertlichen_element():
    """Mangel 2 der Gegenprüfung vom 23.09.2026: an einer windschiefen
    Randfläche nahm die Sehnengrenze den größten Seitendurchmesser der
    **ganzen** Fläche, und eine Seite galt allein über den Abstand ihrer
    Ecken als „auf der Fläche". Abgestuftes Netz mit Deckel
    z = 1 + 0,5·x·y (exakt), 20:1: Element 559 der obersten Lage verdreht,
    die 8 neuen Seiten stehen senkrecht zum Deckel, Ecken 0 und 14,8 mm
    daneben, die Grenze war rund 24 mm - kein Befund. Bei 46af735 war es
    FEHLER „Seiten im Inneren 8", ebenso für Element 119 und für 50:1.

    Jetzt gilt die Grenze aus den Seiten in der Nachbarschaft, und eine Seite
    auf der Fläche muss auch in ihre Richtung zeigen.
    """
    for verh in (20, 50):
        m, k = _gestuft(verh, dz=0.5, oben=True)
        ohne = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
        check(f"abgestuft {verh}:1, windschiefer Deckel: ohne Eingriff kein Befund", not ohne,
              "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in ohne))
        for el in (119, 559):
            alt = _verdrehen(m, el)
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
            check(f"  {verh}:1, Element {el} unter dem Deckel verdreht: FEHLER mit 8 Seiten",
                  len(sn) == 1 and sn[0].stufe == "FEHLER" and sn[0].wert == 8.0
                  and sn[0].element == el,
                  "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund")
            m.elements[el].nodes = alt
        # Die Richtung: Element 999 in der groben Ecke ist 293 mm (20:1) bzw.
        # 357 mm (50:1) breit, die oberste Lage aber duenn - die Ecken seiner
        # Seiten liegen 17 bis 18 mm (20:1) neben dem Deckel, innerhalb der
        # Sehnengrenze dort. Mit abgeschalteter Richtung gemessen: kein
        # Befund, bei 20:1 und 50:1. Die Seiten stehen 57 bis 87 Grad dagegen.
        alt = _verdrehen(m, 999)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        m.elements[999].nodes = alt
        check(f"  {verh}:1, Element 999 in der groben Ecke verdreht: FEHLER (Richtung)",
              [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
              and bef[0].element == 999,
              "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund")
    # Die oertliche Weite: ein Deckelknoten an der feinen Ecke (Zelle
    # 20,5 mm, 20:1) 2 mm nach aussen gedrueckt ist eine Beule. Mit der
    # Weite der ganzen Flaeche (Grenze rund 24 mm) blieb sie ungenannt,
    # gemessen erst ab 3 mm.
    m, k = _gestuft(20, dz=0.5, oben=True)
    q_ = 20 ** (1.0 / 9)
    w = q_ ** np.arange(10)
    x1 = w[0] / w.sum()
    kn = int(np.argmin(np.linalg.norm(m.nodes - [x1, x1, 1 + 0.5 * x1 * x1], axis=1)))
    m.nodes[kn, 2] += 0.002
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  20:1, Deckelknoten an der feinen Ecke 2 mm hinaus: WARNUNG Netzrand, 4 Seiten",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("WARNUNG", "Netzrand neben der Hülle", 4.0)],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef) or "kein Befund")


def _deckelnormale(dz, x, y):
    """Einheitsnormale des Deckels z = 1 + dz·x·y an der Stelle (x|y)."""
    nrm = np.array([-dz * y, -dz * x, 1.0])
    return nrm / np.linalg.norm(nrm)


def _deckelbeule(dz, x, y, v, alle=False):
    """Würfel 1 x 1 x 1 m, Deckel z = 1 + dz·x·y, abgebildetes 4 x 4 x 4-Netz
    (64 hex8); der Deckelknoten bei (x|y) wird um den Vektor v (m) verschoben
    und das Netz mit Warnungen abgenommen. Gibt Elementzahl, Netzbefunde
    (Stufe, Prüfung, Wert) und den Abstand des Knotens zum Deckel in mm.
    Mit alle=True alle Befunde der Abnahme, auch „Lücke im Netzrand"."""
    from statik3d import mesher
    m = Model("beule")
    m.add_material(Material.steel("S235"))
    E = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
         [0, 0, 1], [1, 0, 1], [1, 1, 1 + dz], [0, 1, 1]]
    ecken = [int(m.add_node(*p)) for p in E]
    els = mesher.mesh_koerper(m, _quaderkoerper(m, ecken), log=[], frei=False)
    for i in range(4):
        m.fix(ecken[i], "all")
    abst = np.linalg.norm(m.nodes - [x, y, 1 + dz * x * y], axis=1)
    kn = int(np.argmin(abst))
    if abst[kn] > 1e-9:
        raise ValueError(f"kein Deckelknoten bei ({x}|{y}), nächster {abst[kn]:.3g} m daneben")
    m.nodes[kn] = m.nodes[kn] + np.asarray(v, float)
    deckel = np.array([[0, 0, 1], [1, 0, 1], [1, 1, 1 + dz], [0, 1, 1]], float)
    d_mm = 1e3 * float(dg._bilinear_abstand(m.nodes[kn][None, :], deckel)[0])
    bef = [b for b in dg.abnahme(m, warnungen=True) if alle or b.pruefung in _NETZ_BEFUNDE]
    return len(els), [(b.stufe, b.pruefung, b.wert) for b in bef], d_mm


def _z_fuer_abstand(dz, x, y, d, oben=True):
    """Verschiebung in z (m, nach oben bzw. unten), nach der der Deckelknoten
    bei (x|y) d (m) neben dem Deckel z = 1 + dz·x·y liegt (Halbieren über
    ``_bilinear_abstand``)."""
    deckel = np.array([[0, 0, 1], [1, 0, 1], [1, 1, 1 + dz], [0, 1, 1]], float)
    p = np.array([x, y, 1 + dz * x * y])
    e = np.array([0.0, 0.0, 1.0 if oben else -1.0])
    lo, hi = 0.0, 4.0 * d
    for _ in range(60):
        t = 0.5 * (lo + hi)
        if dg._bilinear_abstand((p + t * e)[None, :], deckel)[0] < d:
            lo = t
        else:
            hi = t
    return 0.5 * (lo + hi) * e


def test_abnahme_beule_windschief_nach_richtung():
    """Wie groß darf eine Beule im windschiefen Deckel sein, bis die Abnahme
    sie nennt - und in welche Richtung gemessen? Das Benutzerhandbuch sagte
    bis zum 23.09.2026 ohne Richtung, bei um 1 m angehobener Deckelecke
    bleibe „selbst eine Beule von 100 mm ungenannt" (Nebenbefund B020).

    Die Antwort hat sich mit Nebenbefund B053 geändert: die Sehnenzulage gilt
    an den Ecken von Viereckseiten nicht mehr, dort ist die Grenze 1 % des
    Seitendurchmessers. Vorher (Stand der Messungen zu B020, 24.09.2026)
    blieben bei dz = 1,0 an den neun inneren Deckelknoten 80 mm senkrecht
    nach außen ungenannt, 100 mm in z an sechs von ihnen; nach innen 80 mm.

    Seither, gemessen am 24.09.2026 an allen neun inneren Deckelknoten
    (Grenzen halbiert): die erste WARNUNG „Netzrand neben der Hülle" kommt
    senkrecht zur Fläche nach außen wie nach innen bei dz = 0,5 zwischen
    3,55 und 3,88 mm, bei dz = 1,0 zwischen 3,60 und 4,74 mm; in z nach oben
    verschoben erst bei 3,61 bis 4,40 bzw. 3,82 bis 6,95 mm. Maßgebend ist
    der Abstand zur Fläche, nicht die Richtung: in z so weit verschoben, dass
    der Knoten 3,5 mm neben der Fläche liegt, bleibt er ungenannt, 5 mm neben
    ihr ist er an allen neun eine WARNUNG; die halbierten Grenzen als Abstand
    liegen in z und senkrecht je Knoten höchstens 0,2 mm auseinander. Eine
    tiefere Delle melden andere Prüfungen: 20 mm senkrecht nach innen
    (dz = 0,5) sind an allen neun Knoten eine WARNUNG „Lücke im Netzrand“
    (seit B044; mit der Dünnregel t/L ≤ 5 % waren es an sieben Knoten FEHLER
    „Seiten im Inneren", an (0,25|0,75) und (0,75|0,25) die Lücke).

    Abgebildetes 4 x 4 x 4-Netz (64 hex8), Deckel z = 1 + dz·x·y, geprüft
    an allen neun inneren Deckelknoten (x und y je 0,25, 0,5 und 0,75); die
    zwölf Randknoten prüft ``test_abnahme_beule_windschief_randknoten``.
    Die Prüfung hält die Zahlen des Handbuchabsatzes fest: ändert sich die
    Grenze, muss der Absatz mit.
    """
    KNOTEN = tuple((x, y) for x in (0.25, 0.5, 0.75) for y in (0.25, 0.5, 0.75))

    def richtung(dz, x, y, r):
        """außen/innen, senkrecht zur Fläche ("n") oder in z ("z")"""
        v = _deckelnormale(dz, x, y) if r[0] == "n" else np.array([0.0, 0.0, 1.0])
        return v if r[1] == "+" else -v

    def text(bef):
        return "; ".join(f"{s} {p} {w:.3g}" for s, p, w in bef) or "kein Befund"

    def nur_netzrand(bef):
        return bool(bef) and all(s == "WARNUNG" and p == "Netzrand neben der Hülle"
                                 for s, p, _w in bef)

    WARN4 = [("WARNUNG", "Netzrand neben der Hülle", 4.0)]
    NAME = {"n+": "senkrecht nach außen", "z+": "in z nach oben",
            "n-": "senkrecht nach innen", "z-": "in z nach unten"}
    # 3,5 mm bleiben überall ungenannt; 5 mm (dz 0,5) bzw. 7 mm senkrecht und
    # 8,5 mm in z (dz 1,0) sind überall die WARNUNG mit allen vier Seiten
    for dz, r, mm, soll in ((0.5, "n+", 3.5, []), (0.5, "z+", 3.5, []),
                            (0.5, "n-", 3.5, []), (0.5, "z-", 3.5, []),
                            (1.0, "n+", 3.5, []), (1.0, "z+", 3.5, []),
                            (1.0, "n-", 3.5, []), (1.0, "z-", 3.5, []),
                            (0.5, "n+", 5.0, WARN4), (0.5, "z+", 5.0, WARN4),
                            (0.5, "n-", 5.0, WARN4), (0.5, "z-", 5.0, WARN4),
                            (1.0, "n+", 7.0, WARN4), (1.0, "n-", 7.0, WARN4),
                            (1.0, "z+", 8.5, WARN4), (1.0, "z-", 8.5, WARN4)):
        falsch = []
        for x, y in KNOTEN:
            n_el, ist, _d = _deckelbeule(dz, x, y, mm * 1e-3 * richtung(dz, x, y, r), alle=True)
            if n_el != 64 or ist != soll:
                falsch.append(f"({x:g}|{y:g}) {n_el} El.: {text(ist)}")
        check(f"4x4x4, Ecke {dz:g} m hoch, 9 Deckelknoten {mm:g} mm {NAME[r]}: "
              f"{'WARNUNG Netzrand 4' if soll else 'kein Befund'}".replace(".", ","),
              not falsch, " | ".join(falsch))

    # Der Abstand zählt: in z nach oben und unten bis 3,5 bzw. 5 mm neben der Fläche
    for d_mm, ok in ((3.5, lambda b: not b), (5.0, nur_netzrand)):
        falsch = []
        for oben in (True, False):
            for x, y in KNOTEN:
                v = _z_fuer_abstand(1.0, x, y, d_mm * 1e-3, oben=oben)
                n_el, ist, _d = _deckelbeule(1.0, x, y, v, alle=True)
                if n_el != 64 or not ok(ist):
                    falsch.append(f"({x:g}|{y:g}) {'oben' if oben else 'unten'}: {text(ist)}")
        check(f"4x4x4, Ecke 1 m hoch, 9 Deckelknoten in z bis {d_mm:g} mm neben der "
              f"Fläche: ".replace(".", ",") + ("kein Befund" if d_mm < 4 else "WARNUNG Netzrand"),
              not falsch, " | ".join(falsch))

    def grenze(dz, x, y, r):
        """kleinste Verschiebung mit Befund (mm) und ihr Abstand zur Fläche (mm)"""
        e = richtung(dz, x, y, r)
        lo, hi = 0.0, 0.012
        for _ in range(12):
            mitte = 0.5 * (lo + hi)
            if _deckelbeule(dz, x, y, mitte * e, alle=True)[1]:
                hi = mitte
            else:
                lo = mitte
        return hi * 1e3, _deckelbeule(dz, x, y, hi * e, alle=True)[2]
    verschiebung, abstand, auseinander = {}, {}, []
    for dz in (0.5, 1.0):
        for r in ("n+", "n-", "z+"):
            for x, y in KNOTEN:
                v, d = grenze(dz, x, y, r)
                verschiebung.setdefault((dz, r), []).append(v)
                abstand.setdefault((dz, r), []).append(d)
        for i, (x, y) in enumerate(KNOTEN):
            dn, dzz = abstand[(dz, "n+")][i], abstand[(dz, "z+")][i]
            if abs(dn - dzz) > 0.2:
                auseinander.append(f"dz {dz:g} ({x:g}|{y:g}): senkrecht {dn:.2f}, in z {dzz:.2f} mm")
    check("  Grenze als Abstand: in z und senkrecht je Knoten höchstens 0,2 mm auseinander",
          not auseinander, " | ".join(auseinander))
    soll_spanne = {(0.5, "n+"): (3.55, 3.88), (0.5, "n-"): (3.55, 3.88),
                   (0.5, "z+"): (3.61, 4.40), (1.0, "n+"): (3.60, 4.74),
                   (1.0, "n-"): (3.60, 4.74), (1.0, "z+"): (3.82, 6.95)}
    check("  erste WARNUNG: dz 0,5 senkrecht 3,55 bis 3,88 mm, in z 3,61 bis 4,40 mm; "
          "dz 1,0 senkrecht 3,60 bis 4,74 mm, in z 3,82 bis 6,95 mm",
          all(abs(min(verschiebung[k]) - a) <= 0.02 and abs(max(verschiebung[k]) - b) <= 0.02
              for k, (a, b) in soll_spanne.items()),
          "; ".join(f"dz {k[0]:g} {k[1]}: {min(w):.2f} bis {max(w):.2f} mm"
                    for k, w in sorted(verschiebung.items())))

    # Eine tiefere Delle melden andere Prüfungen
    SEITEN4 = [("FEHLER", "Seiten im Inneren", 4.0)]
    falsch = []
    for x, y in KNOTEN:
        n_el, ist, _d = _deckelbeule(0.5, x, y, -0.02 * _deckelnormale(0.5, x, y), alle=True)
        if [(s, p) for s, p, _w in ist] != [("WARNUNG", "Lücke im Netzrand")]:
            falsch.append(f"({x:g}|{y:g}): {text(ist)}")
    check("  20 mm senkrecht nach innen (dz 0,5): an allen neun WARNUNG Lücke im Netzrand",
          not falsch, " | ".join(falsch))

    # Die Zahlen des Theoriehandbuchs am Knoten (0,75|0,75), in z verschoben
    def paare(b):
        return [(s, p) for s, p, _w in b]
    reihe = []
    LUECKE = ("WARNUNG", "Lücke im Netzrand")
    for dz, mm, soll in ((0.5, 4, lambda b: not b), (0.5, 5, lambda b: b == WARN4),
                         (0.5, -4, lambda b: not b), (0.5, -5, lambda b: b == WARN4),
                         (0.5, -15, lambda b: b == WARN4), (0.5, -20, lambda b: paare(b) == [LUECKE]),
                         (0.5, -40, lambda b: b == SEITEN4),
                         (1.0, 6, lambda b: not b), (1.0, 7, nur_netzrand),
                         (1.0, -6, lambda b: not b), (1.0, -7, nur_netzrand),
                         (1.0, -20, lambda b: b == WARN4),
                         (1.0, -25, lambda b: LUECKE in paare(b)
                          and ("FEHLER", "Seiten im Inneren") not in paare(b)),
                         (1.0, -80, lambda b: b == SEITEN4)):
        ist = _deckelbeule(dz, 0.75, 0.75, [0.0, 0.0, mm * 1e-3], alle=True)[1]
        if not soll(ist):
            reihe.append(f"dz {dz:g}, {mm:+d} mm: {text(ist)}")
    check("  (0,75|0,75) in z: dz 0,5 ab 5 mm WARNUNG, innen 20 mm Lücke, 40 mm FEHLER; "
          "dz 1,0 ab 7 mm, innen 25 mm Lücke, 80 mm FEHLER", not reihe, " | ".join(reihe))


def test_abnahme_beule_windschief_randknoten():
    """Die Beule an den zwölf Randknoten des Deckels (auf den Kanten zu den
    Seitenflächen, ohne die vier Ecken).

    Benutzer- und Theoriehandbuch sagten am Stand 99847bf ohne Einschränkung,
    bei um 1 m angehobener Ecke blieben 80 mm senkrecht zur Fläche ungenannt
    und 90 mm seien eine WARNUNG „Netzrand neben der Hülle" (mit 4 Seiten).
    Gemessen war das nur an den neun inneren Deckelknoten (vierte
    Gegenprüfung, 24.09.2026). Seit Nebenbefund B053 (Ecken von Viereckseiten
    ohne Sehnenzulage) gilt an den Randknoten dieselbe kleine Grenze wie
    innen: 3,5 mm senkrecht oder in z nach außen bleiben ungenannt, 5 mm
    (dz 0,5) bzw. 7 mm senkrecht und 8,5 mm in z (dz 1,0) sind an allen zwölf
    eine WARNUNG mit 2 Seiten (gemessen 24.09.2026).

    Senkrecht zum Deckel nach außen verschoben, verlässt ein Randknoten auch
    die ebene Seitenfläche, bei 80 mm um 13,9 bis 48,0 mm - nach außen auf
    den Rändern x = 0 und y = 0 (dort WARNUNG „Netzrand neben der Hülle" mit
    4 statt 2 Seiten), nach innen auf x = 1 und y = 1 (FEHLER „Seiten im
    Inneren" an (1|0,5), (1|0,75), (0,5|1) und (0,75|1)). Dass es an der
    Seitenfläche liegt, zeigt die Zerlegung: der Anteil senkrecht zur
    Seitenfläche allein gibt bei 80 mm an allen zwölf denselben Befund bis
    auf die WARNUNG mit 2 Seiten an (1|0,25) und (0,25|1), der Rest, der in
    der Ebene der Seitenfläche bleibt, bei 60 und 80 mm nur die WARNUNG mit
    2 Seiten.

    Die Prüfung hält die Zahlen des Handbuchabsatzes fest: ändert sich die
    Abnahme an ebenen oder windschiefen Flächen, muss der Absatz mit.
    """
    RAND = tuple([(0.0, t) for t in (0.25, 0.5, 0.75)] + [(t, 0.0) for t in (0.25, 0.5, 0.75)]
                 + [(1.0, t) for t in (0.25, 0.5, 0.75)] + [(t, 1.0) for t in (0.25, 0.5, 0.75)])
    WARN2 = [("WARNUNG", "Netzrand neben der Hülle", 2.0)]
    WARN4 = [("WARNUNG", "Netzrand neben der Hülle", 4.0)]

    def text(bef):
        return "; ".join(f"{s} {p} {w:.0f}" for s, p, w in bef) or "kein Befund"

    def zerlegt(dz, x, y, mm):
        """Verschiebung senkrecht zum Deckel, dazu ihr Anteil senkrecht zur
        Seitenfläche (x = 0/1 bzw. y = 0/1) und der Rest in deren Ebene."""
        v = mm * 1e-3 * _deckelnormale(dz, x, y)
        achse = 0 if x in (0.0, 1.0) else 1
        seite = np.zeros(3)
        seite[achse] = v[achse]
        return v, seite, v - seite

    def pruefe(name, soll_von, verschiebung, dz=1.0):
        falsch = []
        for x, y in RAND:
            n_el, ist, _d = _deckelbeule(dz, x, y, verschiebung(x, y))
            if n_el != 64 or ist != soll_von(x, y):
                falsch.append(f"({x:g}|{y:g}) {n_el} El.: {text(ist)}")
        check(name.replace(".", ","), not falsch, " | ".join(falsch))

    Z = np.array([0.0, 0.0, 1.0])
    for dz, mm, r, soll in ((0.5, 3.5, "senkrecht", []), (0.5, 3.5, "in z", []),
                            (1.0, 3.5, "senkrecht", []), (1.0, 3.5, "in z", []),
                            (0.5, 5.0, "senkrecht", WARN2), (0.5, 5.0, "in z", WARN2),
                            (1.0, 7.0, "senkrecht", WARN2), (1.0, 8.5, "in z", WARN2)):
        pruefe(f"4x4x4, Ecke {dz:g} m hoch, 12 Randknoten {mm:g} mm {r} nach außen: "
               + ("kein Befund" if not soll else "WARNUNG Netzrand 2"),
               lambda x, y, s=soll: s,
               lambda x, y, dz=dz, mm=mm, r=r: mm * 1e-3 * (Z if r == "in z"
                                                           else _deckelnormale(dz, x, y)),
               dz=dz)

    # dz 1,0, 80 mm senkrecht zum Deckel, gemessen 24.09.2026
    def soll_80(x, y):
        if x == 0.0 or y == 0.0:
            return WARN4
        if (x, y) in ((1.0, 0.5), (0.5, 1.0)):
            return [("FEHLER", "Seiten im Inneren", 1.0)] + WARN2
        if (x, y) in ((1.0, 0.75), (0.75, 1.0)):
            return [("FEHLER", "Seiten im Inneren", 2.0)] + WARN2
        return WARN2                               # (1|0,25) und (0,25|1)
    pruefe("4x4x4, Ecke 1 m hoch, 12 Randknoten 80 mm senkrecht: Befund je Rand",
           soll_80, lambda x, y: zerlegt(1.0, x, y, 80)[0])
    # Ursache Seitenfläche: ihr Anteil allein gibt bei 80 mm denselben Befund
    # (ohne die WARNUNG an (1|0,25) und (0,25|1)), der Rest in ihrer Ebene bei
    # 60 und 80 mm nur die WARNUNG mit 2 Seiten
    pruefe("  80 mm zerlegt: nur der Anteil senkrecht zur Seitenfläche, derselbe Befund",
           lambda x, y: [] if (x, y) in ((1.0, 0.25), (0.25, 1.0)) else soll_80(x, y),
           lambda x, y: zerlegt(1.0, x, y, 80)[1])
    for mm in (60, 80):
        pruefe(f"  {mm} mm zerlegt: nur der Rest in der Ebene der Seitenfläche, WARNUNG "
               "Netzrand 2", lambda x, y: WARN2, lambda x, y, mm=mm: zerlegt(1.0, x, y, mm)[2])
    # Die Zahl im Handbuch: bei 80 mm verlässt der Knoten die Seitenfläche
    # um 14 bis 48 mm
    anteil = [1e3 * np.linalg.norm(zerlegt(1.0, x, y, 80)[1]) for x, y in RAND]
    check("  80 mm senkrecht: Randknoten 14 bis 48 mm neben der Seitenfläche",
          (round(min(anteil)), round(max(anteil))) == (14, 48),
          f"{min(anteil):.2f} bis {max(anteil):.2f} mm")


def _extrudiert(m, P2, z0, z1, name="K"):
    """Prisma aus einem Grundriss (Liste von (x, y)), alle Kanten gerade."""
    u = [int(m.add_node(x, y, z0)) for x, y in P2]
    o = [int(m.add_node(x, y, z1)) for x, y in P2]
    kante, fl = {}, []

    def linie(a, b):
        key = (min(a, b), max(a, b))
        if key not in kante:
            kante[key] = f"{name}L{len(kante)}"
            m.add_line(kante[key], [a, b])
        return kante[key]

    n = len(P2)
    m.add_flaeche(f"{name}U", [linie(u[i], u[(i + 1) % n]) for i in range(n)], material="S235")
    m.add_flaeche(f"{name}O", [linie(o[i], o[(i + 1) % n]) for i in range(n)], material="S235")
    fl = [f"{name}U", f"{name}O"]
    for i in range(n):
        a, b = u[i], u[(i + 1) % n]
        c, d = o[(i + 1) % n], o[i]
        m.add_flaeche(f"{name}S{i}", [linie(a, b), linie(b, c), linie(c, d), linie(d, a)],
                      material="S235")
        fl.append(f"{name}S{i}")
    for kn in u:
        m.fix(kn, "all")
    return m.add_koerper(name, fl, material="S235")


def test_abnahme_luecke_im_netzrand():
    """Mangel 3 der Gegenprüfung vom 23.09.2026: der eigene freie Vernetzer
    lässt an 5 von 9 L-, T- und U-Prismen (Standardweg, sweep aus) einen
    Tetraeder an der Oberfläche weg. Die Abnahme meldete „FEHLER Seiten im
    Inneren" mit der Abhilfe „Den Körper neu vernetzen" - und neu vernetzen
    ergibt dasselbe Netz (gemessen: 821 Tetraeder, derselbe FEHLER).

    Beim L-Prisma mit h = 0,25 fehlt der Tetraeder unter dem Deckeldreieck
    (0,818|0,368|0,4) (0,943|0,368|0,4) (1|0,5|0,4) mit der Spitze
    (0,875|0,5|0,2), 5,5155e-4 m³ = 0,079 % des Körpers. Ursache im
    Vernetzer: _innere zählt den Strahl vom Schwerpunkt doppelt, weil er die
    Kante zweier Deckeldreiecke trifft (Befund an Fable). Das ist ein echter
    Netzfehler, aber einer an der Oberfläche und klein: WARNUNG „Lücke im
    Netzrand" mit Ort, Volumen und einer Abhilfe, die gemessen hilft. FEHLER
    bleiben verdrehte Elemente, Hohlräume im Innern, doppelte Knoten und
    Lücken über der Grenze der Volumenbilanz.
    """
    from statik3d import mesher
    import contextlib
    import io
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]
    ergebnisse = []
    for lauf in range(2):
        m = Model("L")
        m.add_material(Material.steel("S235"))
        k = _extrudiert(m, L, 0.0, 0.4)
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.25})
            if lauf:
                mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.25})
        bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
        ergebnisse.append((len(k.elemente), bef, dg.abnahme(m)))
    n_el, bef, fehler = ergebnisse[0]
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    # Seit 23.09.2026 (Vernetzer-Sitzung, Antwort auf diesen Befund) ist die
    # Luecke geschlossen: innen() zaehlt die Kante einmal, die Startpunkte
    # halten Abstand zur Huelle, tetraedern_treu verlangt den Rauminhalt.
    # 634 statt 821 Tetraeder, Rauminhalt auf Rundung gleich der Huelle.
    # Die Elementzahl als Fenster um 634 (gemessen 24.09.2026); das Netz mit
    # der Luecke (821) liegt weit ausserhalb.
    check("L-Prisma h = 0,25, Standardweg: keine „Lücke im Netzrand“ mehr, kein Befund",
          _fenster(n_el, 634) and not bef and not lu and not fehler,
          f"{n_el} Elemente; " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef)
          + " | FEHLER: " + "; ".join(b.pruefung for b in fehler))
    check("  neu vernetzen ergibt dasselbe Netz und denselben Befund",
          ergebnisse[1][0] == n_el and [(b.pruefung, round(b.wert, 9)) for b in ergebnisse[1][1]]
          == [(b.pruefung, round(b.wert, 9)) for b in bef],
          f"{ergebnisse[1][0]} Elemente")

    # Zweite Gegenpruefung, Mangel 4: an einem von Hand geaenderten Netz hilft
    # neu vernetzen. Richtiges freies Netz (h = 0,12), ein Tetraeder mit einer
    # Seite im Deckel geloescht wie mit „Elemente löschen" in der Oberflaeche
    # (Model.elemente_loeschen): eine Luecke. Der Text sagte „Neu vernetzen
    # mit denselben Einstellungen ergibt dasselbe Netz" ohne Einschraenkung.
    m = Model("L")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.12})
    n_frei = len(k.elemente)
    vorher = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
    deckel = [i for i in k.elemente
              if (np.abs(m.nodes[m.elements[i].nodes][:, 2] - 0.4) < 1e-9).sum() == 3
              and 0.1 < m.nodes[m.elements[i].nodes][:, 0].mean() < 0.4
              and 0.8 < m.nodes[m.elements[i].nodes][:, 1].mean() < 1.6]
    m.elemente_loeschen(deckel[:1])
    lu = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Lücke im Netzrand"]
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.12})
    nachher = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
    # n_frei als Fenster um 6155 (gemessen 24.09.2026); die Aussage ist, dass
    # neu vernetzen genau diese Zahl wieder ergibt (len(k.elemente) == n_frei)
    check("  von Hand gelöschtes Element: Lücke, und neu vernetzen stellt das Netz wieder her",
          _fenster(n_frei, 6155) and not vorher and len(lu) == 1 and "von Hand geändert" in lu[0].text
          and len(k.elemente) == n_frei and not nachher,
          f"{n_frei} tet4, vorher {len(vorher)} Befunde, Lücke {[round(b.wert, 7) for b in lu]}, "
          f"neu vernetzt {len(k.elemente)} tet4, {len(nachher)} Befunde")

    text = lu[0].text if lu else ""
    check("  der Text nennt neu vernetzen für importierte oder von Hand geänderte Netze",
          "von Hand geändert" in text and "Neu vernetzen mit denselben" not in text, text[-420:])
    # Nebenbefund B049 (22./23.09.2026): die Abhilfe „Sechsflächner sweepen“
    # ist nur an den fünf Prismen gemessen, und ab Werk ist der Sweep aus,
    # weil er am Drehlager 992 entartete Keile erzeugte (Benutzerhandbuch,
    # Netzeinstellungen). Die Meldung empfahl ihn, ohne das zu sagen. Seit
    # dem Vernetzer vom 23.09.2026 hat das L-Prisma h 0,25 keine Luecke
    # mehr; geprueft wird am Text der von Hand erzeugten Luecke, der
    # dieselbe Abhilfe traegt.
    check("  die Abhilfe Sweep sagt, dass er ab Werk aus ist, warum, und dass danach die "
          "Abnahme zu lesen ist",
          "sweepen" in text and "ab Werk aus" in text and "entartete Keile" in text
          and "Abnahme lesen" in text,
          text[-520:])

    # Nebenbefunde B050/B051 (22./23.09.2026): ein flacher Tetraeder im
    # Inneren desselben Netzes von Hand gelöscht - der flachste unter der
    # Deckelmitte des langen Schenkels, 35 728 mm³, t/L 3,65 %. Das war eine
    # WARNUNG „Riss im Netz 4“ ohne Rückfrage, und der Text nannte als Grund
    # den Vernetzer, der flache Tetraeder aussortiere; der sortiert aber nur
    # V ≤ FLACH·h³ = 1,7 mm³ aus. Ein Hohlraum in Elementgröße ist kein Riss.
    # Seit dem Vernetzer vom 23.09.2026 (6155 statt 6173 tet4) ist der
    # flachste dort 36 097 mm³ mit t/L 3,67 % (nachgemessen 24.09.2026).
    # Bis zum 24.09.2026 legte die Pruefung V auf ±10 mm³ und t/L auf 3,6 bis
    # 3,7 % fest und nahm den flachsten in diesem Fenster; an allen sieben
    # anderen Gitterphasen des BCC-Gitters riss sie daran, obwohl der Befund
    # jedes Mal FEHLER „Seiten im Inneren 4“ war, und in einer Phase lag dort
    # gar kein flacher (t/L 7,03 %). Jetzt nach Eigenschaften, wie bei den
    # Keilen (test_abnahme_luecken_des_vernetzers_sind_risse): der groesste innere Tetraeder, dessen Hohlraum ohne die
    # Groessenregel ein Riss waere (t/L ≤ ABNAHME_RISS_DICKE, hoechstens
    # ABNAHME_RISS_NACHBAR-mal so dick wie die Nachbarn), und er muss ueber
    # 1000 FLACH·L³ gross sein.
    els_l = list(k.elemente)
    tl_l, tn_l = _tetraeder_masse(m, els_l)
    V_l = dg.elementvolumina(m, els_l)
    P_l = m.nodes[np.array([[int(x) for x in m.elements[i].nodes] for i in els_l])]
    L_l = float(np.max([np.linalg.norm(P_l[:, a] - P_l[:, b], axis=1)
                        for a in range(4) for b in range(a + 1, 4)]))
    from statik3d import mesher3d
    FLACH_L3_l = mesher3d.FLACH * L_l ** 3
    rissartig = [j for j in range(len(els_l))
                 if tl_l[j] <= dg.ABNAHME_RISS_DICKE and tn_l[j] <= dg.ABNAHME_RISS_NACHBAR]
    j_f = max(rissartig, key=lambda j: V_l[j]) if rissartig else -1
    flach, tl_f, V_f = els_l[j_f], float(tl_l[j_f]), float(V_l[j_f])
    m.elemente_loeschen([flach])
    bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
           or b.pruefung == "Lücke im Netzrand"]
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    echt_flach = dg.ABNAHME_RISS_FLACH
    try:
        dg.ABNAHME_RISS_FLACH = float("inf")
        bef_ohne = [(b.stufe, b.pruefung, b.wert) for b in dg.abnahme(m, warnungen=True)
                    if b.pruefung in _NETZ_BEFUNDE or b.pruefung == "Lücke im Netzrand"]
    finally:
        dg.ABNAHME_RISS_FLACH = echt_flach
    check("  flacher Tetraeder in Elementgröße von Hand gelöscht (über 1000 FLACH·L³): FEHLER "
          "mit Rückfrage, kein Riss",
          j_f >= 0 and V_f > 1000 * FLACH_L3_l and tl_f <= 0.05
          and [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 4.0)]
          and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"]
          and bef_ohne == [("WARNUNG", "Riss im Netz", 4.0)],
          f"{len(rissartig)} Kandidaten, Element {flach}, V {V_f * 1e9:.0f} mm³ = "
          f"{V_f / FLACH_L3_l:.0f} FLACH·L³, t/L {tl_f * 100:.2f} %, "
          f"{tn_l[j_f]:.3f}-mal so dick wie die Nachbarn: "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef)
          + f"; ohne Größenregel {bef_ohne}")
    text_sn = sn[0].text if sn else ""
    check("  der Text schreibt die Lücke nicht dem Vernetzer zu und nennt ein fehlendes Element",
          "Vernetzer flache Tetraeder aussortiert" not in text_sn
          and "fehlendes Element" in text_sn and "von Hand gelöscht" in text_sn,
          text_sn[-380:])

    # T-Prisma, h = 0,1: bis zum 23.09.2026 lag hier die Luecke an der
    # einspringenden Kante (1,2 | 0,4): zwei Seiten im Inneren, zwei in die
    # Aussparung hinaus (bis 29,2 mm), 2,43e-5 m^3 fehlten (Bilanz 1,17e-5).
    # Seit der Kur im Vernetzer (tetraedern_treu verlangt den Rauminhalt und
    # fuehrt die Huelle an echten Dellen nach) ist sie geschlossen.
    T = [(0, 0), (2, 0), (2, 0.4), (1.2, 0.4), (1.2, 1.5), (0.8, 1.5), (0.8, 0.4), (0, 0.4)]
    m = Model("T")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, T, 0.0, 0.3)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.1})
    bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
    # Die Elementzahl als Fenster: gemessen 5825 (23.09.2026), 5886 (Vernetzer
    # vom 24.09.2026)
    check("T-Prisma h = 0,1, Standardweg: keine Lücke mehr an der einspringenden Kante, kein Befund",
          _fenster(len(k.elemente), 5886) and not bef,
          f"{len(k.elemente)} Elemente; "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))

    # Gegenprobe: ein verdrehter Sechsflächner am Rand (Zelle (0, 5, 5) im
    # abgestuften Netz, sein Hohlraum öffnet sich zur Randfläche x = 0) ist
    # keine Lücke, sondern bleibt ein FEHLER
    m, k = _gestuft(5)
    _verdrehen(m, 55)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  verdrehter Sechsflächner am Rand: FEHLER, keine Lücke",
          any(b.pruefung == "Seiten im Inneren" and b.stufe == "FEHLER" for b in bef)
          and not [b for b in bef if b.pruefung == "Lücke im Netzrand"],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    # Den Fall hielten bis zum 24.09.2026 zwei Regeln, und die Pruefung oben
    # sah nur, dass eine von beiden greift: Ohne _verdrehte_elemente bestand
    # sie weiter (Nebenbefund B144). Gemessen 23.09.2026:
    # * die Erkennung des verdrehten Elements allein - ohne sie „WARNUNG
    #   Lücke im Netzrand 1,212e-4 m³“;
    # * die Duennregel (t/L <= ABNAHME_RISS_DICKE), mit ausgeschalteter
    #   Erkennung: das Ufer hat t/L 4,845 %, also FEHLER (Nebenbefund NB2:
    #   ohne die Duennregel bestand die Suite ganz).
    # Seit B044 (Zweig nb_diagnose) ist die Duennregel der Luecke
    # t/L <= ABNAHME_KNOTENNAEHE (1 %), damit eine duenne echte Luecke eine
    # Luecke bleibt. Der verdrehte Sechsflaechner am Rand haengt jetzt an der
    # Erkennung allein; ohne sie ist er die Luecke von eben. Die Duennregel
    # selbst legt test_abnahme_luecke_duenn_mit_volumen fest (sie kippt am
    # t/L der Gruppe).
    def rand_befunde():
        return [(b.stufe, b.pruefung) for b in dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)]

    echt_verdreht = dg._verdrehte_elemente
    nur_verdreht = rand_befunde()
    dg._verdrehte_elemente = lambda *a, **kw: set()
    try:
        nur_duenn = rand_befunde()
    finally:
        dg._verdrehte_elemente = echt_verdreht
    check("  … erkannt als verdreht (die Dünnregel mit 1 % greift bei t/L 4,845 % nicht): "
          "FEHLER, keine Lücke",
          nur_verdreht == [("FEHLER", "Seiten im Inneren")], str(nur_verdreht))
    check("  … ohne die Erkennung seit B044 die Lücke: der Fall hängt an der Erkennung allein",
          nur_duenn == [("WARNUNG", "Lücke im Netzrand")], str(nur_duenn))
    # ... und in der Ecke: dort liegt der Hohlraum an Randflaechen, und die
    # Volumenbilanz sieht ein Drittel von einem Tausendstel nicht. Im ersten
    # Entwurf dieser Nachbesserung galt der Fall als Luecke - die Seitenkante
    # des verdrehten Elements liegt auf der Diagonale der Nachbarseite, und
    # „beide Knoten im Nachbarn" hielt sie fuer eine gemeinsame Kante.
    m, k = _gestuft(1)
    _verdrehen(m, 9)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  verdrehter Sechsflächner in der Ecke (10 x 10 x 10): FEHLER, keine Lücke",
          [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
          and bef[0].element == 9,
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    # Dritte Gegenpruefung vom 23.09.2026: ein Element an der Oberflaeche, das
    # an Knoten losgeloest ist (doppelte Knoten), ist keine Luecke - es fehlt
    # nichts, das Element haengt an einem Knoten oder schwebt. Kuhn-Tetraeder 2
    # der Zelle 27 an der Seite x = 0 (Element 164) an seinen drei Knoten auf
    # der Huelle oder an allen vier losgeloest: zwei offene Gruppen mit je dem
    # Volumen des Elements, deren Rand auf der Huelle liegt. Ebenso der
    # Sechsflaechner der Zelle 27 an allen acht Knoten.
    still = []
    for welche in ((0, 1, 2), (0, 1, 2, 3)):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        _in_kuhn(m, k)
        nd = list(m.elements[164].nodes)
        for j in welche:
            nd[j] = int(m.add_node(*m.nodes[nd[j]]))
        m.elements[164].nodes = nd
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        if ([(b.stufe, b.pruefung, b.wert) for b in bef] != [("FEHLER", "Seiten im Inneren", 6.0)]
                or [b.pruefung for b in dg.abnahme(m)] != ["Seiten im Inneren"]):
            still.append(f"Knoten {welche}: "
                         + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    m.elements[27].nodes = [int(m.add_node(*m.nodes[x])) for x in m.elements[27].nodes]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    if [(b.stufe, b.pruefung, b.wert) for b in bef] != [("FEHLER", "Seiten im Inneren", 10.0)]:
        still.append("hex8 27 an acht Knoten: "
                     + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    check("  Element an der Oberfläche losgelöst (doppelte Knoten): FEHLER mit Rückfrage, "
          "keine Lücke", not still, " | ".join(still))

    # Gegenprobe: eine Lücke über der Grenze der Volumenbilanz (0,5 %) ist ein
    # FEHLER - am 4 x 4 x 4-Würfel fehlen die acht Elemente einer Ecke (12,5 %)
    m = Model("ecke")
    m.add_material(Material.steel("S235"))
    W = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
    ecken = [int(m.add_node(*p)) for p in W]
    k = _quaderkoerper(m, ecken)
    els = [int(i) for i in mesher.mesh_koerper(m, k, log=[], frei=False)]
    weg = [i for i in els if (m.nodes[m.elements[i].nodes].mean(axis=0) > 0.5).all()]
    k.elemente = [i for i in els if i not in weg]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    check("  eine Ecke von 12,5 % fehlt: die Lücke ist ein FEHLER",
          len(weg) == 8 and len(lu) == 1 and lu[0].stufe == "FEHLER"
          and abs(lu[0].wert - 0.125) < 1e-9,
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))


def test_abnahme_luecke_duenn_mit_volumen():
    """Die Regel t/L der Lücke im Netzrand misst die Dicke der Gruppe gegen
    ihre eigenen Seiten, t = 2·V/A durch L (Befund B029, 23.09.2026: Handbuch
    und Kommentar sagten nur „kein Volumen").

    Seit Nebenbefund B044 (Zweig nb_diagnose, 24.09.2026) ist die Grenze
    ABNAHME_KNOTENNAEHE (1 %) statt ABNAHME_RISS_DICKE (5 %): eine dünne
    echte Lücke - ein von Hand gelöschtes Element an der Oberfläche mit t/L
    2,9 bis 4,5 % - war mit 5 % ein FEHLER statt der Lücke. „Ohne Volumen“
    heißt jetzt: die Seiten liegen im Rahmen der Knotennähe auf dem Fächer
    über der Hülle.

    Geprüft wird die Regel allein: der verdrehte Sechsflächner am Rand des
    abgestuften Netzes 5:1 (Element 55) mit abgeschalteter Regel „verdreht"
    (die im Programm vorher greift). Seine offene Gruppe hat t/L 4,845 % und
    1,21e-4 m³ - ein Drittel der Zelle (3,64e-4 m³). Mit der Grenze 1 % ist
    sie eine WARNUNG „Lücke im Netzrand“ mit diesem Volumen (mit 5 % war sie
    bis B044 ein FEHLER „Seiten im Inneren“). Die Grenze kippt am t/L der
    Gruppe: ABNAHME_KNOTENNAEHE 4,85 % lässt den FEHLER, 4,84 % macht die
    Lücke (gemessen 24.09.2026; durch Halbieren t/L = 4,8455 %). Rechnete die
    Regel die Dicke falsch (etwa ohne den Faktor 2 in t = 2·V/A, dann t/L
    2,42 %), fiele die Prüfung bei 4,84 % durch. ABNAHME_RISS_DICKE ändert
    an der Lücke nichts mehr.
    """
    echt_verdreht = dg._verdrehte_elemente
    echt_nah, echt_dicke = dg.ABNAHME_KNOTENNAEHE, dg.ABNAHME_RISS_DICKE
    try:
        dg._verdrehte_elemente = lambda *a, **kw: set()
        m, k = _gestuft(5)
        V_zelle = float(np.prod(np.ptp(m.nodes[m.elements[55].nodes], axis=0)))
        _verdrehen(m, 55)
        mit = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        dg.ABNAHME_KNOTENNAEHE = 0.0485
        knapp_ueber = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        dg.ABNAHME_KNOTENNAEHE = 0.0484
        knapp_unter = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        dg.ABNAHME_KNOTENNAEHE = echt_nah
        dg.ABNAHME_RISS_DICKE = 0.0485
        dicke_egal = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    finally:
        dg._verdrehte_elemente = echt_verdreht
        dg.ABNAHME_KNOTENNAEHE, dg.ABNAHME_RISS_DICKE = echt_nah, echt_dicke
    lu = [b for b in mit if b.pruefung == "Lücke im Netzrand"]
    check("t/L 4,845 % > 1 %: WARNUNG „Lücke im Netzrand“ an Element 55 mit einem Drittel "
          "der Zelle",
          [(b.stufe, b.pruefung, b.element) for b in mit] == [("WARNUNG", "Lücke im Netzrand", 55)]
          and abs(lu[0].wert / V_zelle - 1.0 / 3.0) < 0.01,
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g} el {b.element}" for b in mit)
          + f" | Zelle {V_zelle:.4g} m³")
    check("  die Grenze kippt am t/L der Gruppe: ABNAHME_KNOTENNAEHE 4,85 % FEHLER, 4,84 % "
          "die Lücke",
          [(b.stufe, b.pruefung) for b in knapp_ueber] == [("FEHLER", "Seiten im Inneren")]
          and [(b.stufe, b.pruefung) for b in knapp_unter] == [("WARNUNG", "Lücke im Netzrand")],
          "4,85 %: " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in knapp_ueber)
          + " | 4,84 %: " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in knapp_unter))
    check("  ABNAHME_RISS_DICKE (die Grenze des Risses) ändert an der Lücke nichts",
          [(b.stufe, b.pruefung) for b in dicke_egal] == [("WARNUNG", "Lücke im Netzrand")],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in dicke_egal))


def test_falsche_knotenzahl():
    """Befund B106: ein Element, dessen Knotenzahl nicht zu seinem Typ passt.

    Am Stand ec6448c (23.09.2026) nahm add_element ein hex8 mit sieben
    Knoten an, check() gab dafuer keine Zeile aus, und erst solve_all brach
    mit "operands could not be broadcast together" ab. Mit neun Knoten,
    deren neunter einen der acht wiederholte, meldete check() einen falschen
    FEHLER ("zusammenfallende Knoten ... Volumen inf m³"); mit einem
    neunten, eigenen Knoten meldete es nichts (gemessen 24.09.2026 an diesem
    Netz am Stand ec6448c: jede der acht Wiederholungen gab den FEHLER, jeder
    der vier uebrigen Knoten keinen). Ein tet4 mit drei Knoten liess check()
    selbst mit IndexError abbrechen (diagnose.entartete_elemente), statt eine
    Liste zu liefern. Richtig: add_element weist die falsche Knotenzahl ab;
    ein so geladenes Element (JSON, Import) nennt check() als FEHLER mit Soll
    und Ist, und die Entartungspruefung laesst es aus - beide Arten von neun
    Knoten. Die uebrigen Zeilen zum selben Element bleiben: das
    Benutzerhandbuch sagte bis 24.09.2026 "die uebrigen Pruefungen lassen es
    aus", gemessen kamen aber "Knoten 999 existiert nicht" und "Material
    'WEG' unbekannt" weiter (zweite Gegenpruefung).
    """
    from statik3d import mesher
    from statik3d.model import Model as _M

    def netz():
        m = Model()
        m.add_material(Material.steel("S235"))
        ids = mesher.grid_box(m, "S235", 1.0, 0.1, 0.1, 2, 1, 1, typ="hex8")
        for j in range(2):
            for k in range(2):
                m.fix(int(ids[0, j, k]), "all")
        m.load_node(int(ids[2, 1, 1]), Fz=-1000.0)
        return m

    m = netz()
    e8 = [int(n) for n in m.elements[1].nodes]
    fremd = next(n for n in range(m.nn) if n not in e8)
    faelle = (("hex8", e8[:7], 8, "7 Knoten"),
              ("hex8", e8 + [e8[0]], 8, "9 Knoten, der neunte wiederholt den ersten"),
              ("hex8", e8 + [fremd], 8, "9 Knoten, der neunte ist ein eigener"),
              ("tet4", e8[:3], 4, "3 Knoten"))
    for typ, kn, soll, titel in faelle:
        try:
            m.add_element(typ, kn, "S235")
            ergebnis = "angenommen"
        except ValueError as ex:
            ergebnis = str(ex)
        check(f"add_element weist {typ} mit {titel} ab",
              ergebnis != "angenommen" and f"{len(kn)}" in ergebnis and f"{soll}" in ergebnis,
              ergebnis[:80])
    check("… und das Modell bleibt bei zwei Elementen", len(m.elements) == 2, str(len(m.elements)))

    # Geladen wie aus einer JSON-Datei: dort geht nichts ueber add_element
    for typ, kn, soll, titel in faelle:
        d = netz().to_dict()
        neu = dict(d["elements"][1])
        neu["typ"], neu["nodes"] = typ, list(kn)
        d["elements"].append(neu)
        mg = _M.from_dict(d)
        try:
            zeilen = mg.check()
            fehler = [z for z in zeilen if z.startswith("FEHLER")]
            ok = (f"FEHLER: Element 2 ({typ}): {len(kn)} Knoten, erwartet {soll}" in fehler
                  and not any("zusammenfallenden Knoten" in z for z in fehler))
            detail = "; ".join(fehler)[:110]
        except Exception as ex:      # noqa: BLE001
            ok, detail = False, f"check() warf {type(ex).__name__}: {ex}"
        check(f"geladen {typ} mit {titel}: check() nennt Soll und Ist, nichts anderes",
              ok, detail)
    # Die Knotenzahl-Zeile ersetzt die uebrigen Pruefungen desselben Elements
    # nicht: ein unbekannter Knoten oder Werkstoff steht weiter da (so sagt es
    # das Benutzerhandbuch, Punkt "Falsche Knotenzahl")
    for aend, erwartet in ((dict(nodes=e8[:6] + [999]), "FEHLER: Element 2: Knoten 999 existiert nicht"),
                           (dict(nodes=e8[:7], mat="WEG"), "FEHLER: Element 2: Material 'WEG' unbekannt")):
        d = netz().to_dict()
        neu = dict(d["elements"][1])
        neu.update(aend)
        d["elements"].append(neu)
        zeilen = _M.from_dict(d).check()
        check(f"geladen hex8 mit 7 Knoten: auch '{erwartet.split(': ', 2)[-1]}'",
              "FEHLER: Element 2 (hex8): 7 Knoten, erwartet 8" in zeilen and erwartet in zeilen,
              "; ".join(z for z in zeilen if z.startswith("FEHLER"))[:140])
    # Gegenprobe: das unveraenderte Netz hat keine solche Zeile
    zeilen = [z for z in netz().check() if "erwartet" in z]
    check("Gegenprobe: richtiges Netz ohne Knotenzahl-FEHLER", not zeilen, "; ".join(zeilen))


def test_abnahme_knoten_ueber_kopplung():
    """Nebenbefund B099 (22./23.09.2026): das abgestufte Netz 20:1 (Knotenlager
    an den 121 Bodenknoten) neu vernetzt mit ``mesher.modell_vernetzen`` ergab
    „FEHLER Knoten ohne Element 117 … sie tragen nichts, und eine Last darauf
    ginge verloren". Die 117 Knoten bleiben mit Absicht stehen - sie tragen
    ein Knotenlager (``Model.netzknoten_loeschen`` schützt sie) - und der
    Vernetzer koppelt sie starr an das neue Netz (306 Kopplungen). Das Modell
    rechnet: Fz = -100 kN, Summe der Reaktionen in z 100 000,0 N. Falsch war
    die Meldung. Ein Knoten, der über Kopplungen in allen drei Richtungen an
    Elementknoten hängt, hat keinen Befund; ein wirklich loser bleibt ein
    FEHLER. Was nur in einem Teil der Richtungen hält (Kopplung in einer
    Richtung, Spaltelement, RBE3-Slave), prüft
    test_abnahme_knoten_in_drei_richtungen.
    """
    from statik3d import mesher
    from statik3d.model import Kopplung
    import contextlib
    import io
    m, k = _gestuft(20)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1)
    belegt = {int(n) for e in m.elements for n in e.nodes}
    ohne = [i for i in range(m.nn) if i not in belegt]
    gekoppelt = {int(x) for kp in m.kopplungen for x in (kp.node_a, kp.node_b)}
    gelagert = {int(s.node) for s in m.supports}

    def knoten_befund():
        return [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Knoten ohne Element"]
    kb = knoten_befund()
    check("20:1 neu vernetzt: 117 gelagerte Knoten ohne Element, angekoppelt - kein Befund",
          len(ohne) == 117 and set(ohne) <= gekoppelt and set(ohne) <= gelagert and not kb,
          f"{len(ohne)} ohne Element, {len(m.kopplungen)} Kopplungen; "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in kb))

    e0 = int(m.elements[k.elemente[0]].nodes[0])
    lose = int(m.add_node(5.0, 5.0, 5.0))
    kb = knoten_befund()
    check("  ein wirklich loser Knoten bleibt ein FEHLER",
          len(kb) == 1 and kb[0].stufe == "FEHLER" and kb[0].wert == 1.0 and kb[0].knoten == [lose],
          "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f} {b.knoten}" for b in kb))
    # Eine Kopplung unter losen Knoten, die an kein Element reicht, und eine
    # Kopplung ohne wirksame Richtung schließen nichts an
    a, b = int(m.add_node(6.0, 5.0, 5.0)), int(m.add_node(7.0, 5.0, 5.0))
    m.kopplungen.append(Kopplung(a, b, [[1.0, 0.0, 0.0]], [float("inf")]))
    c = int(m.add_node(8.0, 5.0, 5.0))
    m.kopplungen.append(Kopplung(c, e0, [[1.0, 0.0, 0.0]], [0.0]))
    # Eine Kopplung in x, y und z an einem Elementknoten schließt an, auch
    # über eine Kette (f über d)
    d, f = (int(m.add_node(9.0 + i, 5.0, 5.0)) for i in range(2))
    xyz = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    m.kopplungen.append(Kopplung(d, e0, xyz, [float("inf")] * 3))
    m.kopplungen.append(Kopplung(f, d, xyz, [1e9] * 3))
    kb = knoten_befund()
    check("  Kopplung ohne Elementknoten oder ohne Richtung: lose; Kopplung in x, y, z "
          "und Kette: angeschlossen",
          len(kb) == 1 and kb[0].wert == 4.0 and sorted(kb[0].knoten) == sorted([lose, a, b, c]),
          "; ".join(f"{b_.stufe} {b_.pruefung} {b_.wert:.0f} {b_.knoten}" for b_ in kb))


def _knoten_am_wuerfel(fall):
    """Würfel 1 x 1 x 1 m aus 2 x 2 x 2 hex8, unten gelagert, und ein Knoten
    ohne Element, der auf die Art ``fall`` am Netz hängt (Gegenprüfung vom
    24.09.2026 zu B099). Rückgabe (Modell, Knoten für die Last, Knoten, die
    die Abnahme als lose nennen muss)."""
    from statik3d import mesher
    from statik3d.model import GapElement
    m = Model("drei Richtungen")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 1.0, 1.0, 1.0, 2, 2, 2, typ="hex8")
    for kn in ids[:, :, 0].ravel():
        m.fix(int(kn), "all")
    oben = [int(x) for x in ids[:, :, 2].ravel()]
    e0 = oben[8]                                            # Ecke (1|1|1)
    starr = float("inf")
    if fall == "RBE3, loser Master und loser Slave":
        s, M = int(m.add_node(2.0, 0.5, 1.0)), int(m.add_node(0.5, 0.5, 1.2))
        m.add_starrkoerper(M, oben + [s], art="RBE3")
        return m, s, [s, M]
    if fall == "RBE3, loser Master an den Deckelknoten":
        M = int(m.add_node(0.5, 0.5, 1.2))
        m.add_starrkoerper(M, oben, art="RBE3")
        return m, M, []
    if fall == "RBE3, Master am Deckelknoten, loser Slave":
        s = int(m.add_node(2.0, 0.5, 1.0))
        m.add_starrkoerper(oben[4], oben[:4] + oben[5:] + [s], art="RBE3")
        return m, s, [s]
    # RBE3 mit losem Master an gehaltenen Slaves, die ihn nicht festlegen (2.
    # Gegenprüfung vom 24.09.2026, Mangel 1): ein Slave, zwei Slaves, drei
    # Slaves auf einer Linie, der Master jeweils daneben. Die Deckelreihe
    # y = 1 (x = 0 / 0,5 / 1) sind oben[2], oben[5], oben[8].
    reihe = [oben[2], oben[5], oben[8]]
    if fall == "RBE3, loser Master 0,3 m über drei Deckelknoten, nicht auf einer Linie":
        M = int(m.add_node(0.5, 0.75, 1.3))
        m.add_starrkoerper(M, [reihe[0], reihe[2], oben[4]], art="RBE3")
        return m, M, []
    if fall.startswith("RBE3, loser Master 0,3 m über"):
        M = int(m.add_node(0.5, 1.0, 1.3))
        sl = {"einem Deckelknoten": [reihe[1]], "zwei Deckelknoten": [reihe[0], reihe[2]],
              "einer Deckelreihe": reihe}[fall.split(" über ")[1].split(",")[0]]
        m.add_starrkoerper(M, sl, art="RBE3")
        if fall.endswith("in x und y angekoppelt"):
            m.kopplungen.append(Kopplung(M, reihe[2], [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [starr] * 2))
            return m, M, []
        return m, M, [M]
    if fall == "RBE3, loser Master auf einer Deckelreihe":
        M = int(m.add_node(0.25, 1.0, 1.0))
        m.add_starrkoerper(M, reihe, art="RBE3")
        return m, M, []
    if fall == "RBE3, loser Master auf seinem einzigen Slave":
        M = int(m.add_node(*m.nodes[reihe[1]]))
        m.add_starrkoerper(M, [reihe[1]], art="RBE3")
        return m, M, []
    if fall == "RBE2, loser Master und loser Slave":
        s, M = int(m.add_node(2.0, 0.5, 1.0)), int(m.add_node(0.5, 0.5, 1.2))
        m.add_starrkoerper(M, oben + [s])
        return m, s, []
    if fall == "RBE2 am Deckelknoten, ein Slave 0,5 m daneben":
        d = int(m.add_node(1.5, 1.0, 1.0))
        m.add_starrkoerper(e0, [d])
        return m, d, [d]
    if fall == "Kopplung nur in z":
        f = int(m.add_node(*m.nodes[e0]))
        m.kopplungen.append(Kopplung(f, e0, [[0.0, 0.0, 1.0]], [starr]))
        return m, f, [f]
    if fall == "Kopplungen in x+y und z, dazu x-y":
        f = int(m.add_node(*m.nodes[e0]))
        m.kopplungen.append(Kopplung(f, e0, [[1.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [starr] * 2))
        m.kopplungen.append(Kopplung(f, oben[7], [[1.0, -1.0, 0.0]], [starr]))
        return m, f, []
    if fall.startswith("Kette: x, y direkt, z über h"):
        f, h = int(m.add_node(*m.nodes[e0])), int(m.add_node(*m.nodes[e0]))
        m.kopplungen.append(Kopplung(h, e0, [[0.0, 0.0, 1.0]], [starr]))
        m.kopplungen.append(Kopplung(f, h, [[0.0, 0.0, 1.0]], [starr]))
        m.kopplungen.append(Kopplung(f, e0, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], [starr] * 2))
        return m, (h if fall.endswith("Last an h") else f), [h]
    if fall == "Kette: x, y, z an h, das nur in z hängt":
        f, h = int(m.add_node(*m.nodes[e0])), int(m.add_node(*m.nodes[e0]))
        m.kopplungen.append(Kopplung(h, e0, [[0.0, 0.0, 1.0]], [starr]))
        m.kopplungen.append(Kopplung(f, h, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                                     [starr] * 3))
        return m, f, [f, h]
    if fall == "Spaltelement an einem Anschlag":
        g, q = int(m.add_node(1.0, 1.0, 1.2)), int(m.add_node(1.0, 1.0, 1.4))
        m.fix(g, "all")
        m.gap_elements.append(GapElement(g, e0))
        m.gap_elements.append(GapElement(q, g))
        return m, q, [q]
    if fall == "Spaltelement allein":
        g = int(m.add_node(1.0, 1.0, 1.2))
        m.gap_elements.append(GapElement(g, e0))
        return m, g, [g]
    if fall == "Anschlag: in x, y, z gelagert, Spaltelement":
        g = int(m.add_node(1.0, 1.0, 1.2))
        m.fix(g, "all")
        m.gap_elements.append(GapElement(g, e0))
        return m, g, []
    if fall == "Spaltelement, Knoten nur in z gelagert":
        g = int(m.add_node(1.0, 1.0, 1.2))
        m.fix(g, [2])
        m.gap_elements.append(GapElement(g, e0))
        return m, g, [g]
    raise KeyError(fall)


def _getragen_je_richtung(bau) -> list:
    """Je 1000 N in x, y und z am Knoten ``ziel`` aus ``bau() -> (Modell,
    ziel)``: gehen sie ganz in die Lager? Gezählt werden nur die Lagerkräfte
    in gelagerten Richtungen: ein Freiheitsgrad ohne Steifigkeit wird beim
    Rechnen gesperrt, und seine „Reaktion" ist die verlorene Last.

    Ganz heißt auch: ohne Hilfsfesselung des Lösers (Singularitaet mit
    ``gefesselt``). Sie hält eine Bewegung fest, die das Modell nicht hält,
    und nimmt den Anteil der Last auf, der an ihr Arbeit leistet. An einem
    Stab mit beiden Enden nur in x, y, z gelagert (die Torsion ist frei) und
    dem Slave eines RBE2 0,5 m daneben in y gingen die 1000 N in z als Kraft
    ganz in die Lager, das Moment 500 Nm um die Stabachse nahm die
    Fesselung (3. Gegenprüfung vom 24.09.2026, Mängel 1 und 2; bis dahin zählte
    der Fall hier als getragen). Das Moment selbst taugt nicht als Maß: Eine
    Kopplung zwischen zwei getrennten Knoten überträgt nur Kräfte, am Würfel
    blieben so 250 bis 500 Nm offen, ohne dass Last verloren ging (gemessen
    24.09.2026, beide Male ohne Fesselung)."""
    import contextlib
    import io
    aus = []
    for F in ((1000.0, 0.0, 0.0), (0.0, 1000.0, 0.0), (0.0, 0.0, 1000.0)):
        m2, ziel2 = bau()
        m2.add_load_case("LF1", "G")
        m2.load_node(ziel2, case="LF1", Fx=F[0], Fy=F[1], Fz=F[2])
        gel: dict = {}
        for s_ in m2.supports:
            gel.setdefault(int(s_.node), set()).update(d for d in s_.dofs if d < 3)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                r = solver.solve_static(m2, case="LF1", workers=1)
            RR = np.asarray(r.reactions).reshape(-1, 6)
            R = np.zeros(3)
            for n_, ds in gel.items():
                for d_ in ds:
                    R[d_] += RR[n_, d_]
            gefesselt = any(getattr(s_, "gefesselt", False)
                            for s_ in (getattr(r, "singular", None) or []))
            aus.append(bool(np.allclose(R, -np.asarray(F), atol=1e-3)) and not gefesselt)
        except Exception:                    # noqa: BLE001 - singulär, Kontakt bricht ab
            aus.append(False)
    return aus


def test_abnahme_knoten_in_drei_richtungen():
    """Gegenprüfung vom 24.09.2026 zu B099, Mängel 1 und 4: Die Kur vom
    23.09.2026 zählte jeden Knoten als angeschlossen, der über irgendeine
    Kopplung, einen starren Körper oder ein Spaltelement mit dem Netz
    verbunden war. Ein Slave eines RBE3 (der Master ist nur das Mittel der
    Slaves), eine Kopplung in nur einer Richtung und ein Spaltelement halten
    aber nicht in allen drei Richtungen: Die Rechnung brach ab
    (Gleichungssystem singulär), oder die Last blieb als Reaktion am Knoten
    selbst stehen und erreichte das Tragwerk nie - ohne Befund der Abnahme.
    Bis zur Kur (ec6448c) war jeder dieser Knoten ein FEHLER.

    Geprüft wird die Abnahme gegen die Rechnung: Je Fall 1000 N am Knoten in
    x, y und z. Nennt ihn die Abnahme nicht, müssen alle drei Lasten in die
    Lager gehen, nennt sie ihn, mindestens eine nicht. Eine Ausnahme mit Absicht: Ein Slave eines
    RBE3 an einem Master mit Element ist durch die Gleichungen festgelegt und
    trägt, bleibt aber lose - das RBE3 soll ihn nicht halten.

    2. Gegenprüfung vom 24.09.2026: Mangel 1 - ein RBE3 hält seinen losen
    Master nur, wenn die gehaltenen Slaves ihn festlegen (nicht bei einem
    Slave, zwei Slaves oder Slaves auf einer Linie mit dem Master daneben;
    bei d7553e4 ohne Befund, die Lasten quer brachen ab). Mangel 2 - der Text
    behauptete für jeden genannten Knoten, eine Last ginge verloren oder die
    Rechnung breche ab, auch für den RBE3-Slave oben und für das Stabende mit
    einem Teil der Momentengelenke, wo alle drei Lasten in die Lager gingen.

    3. Gegenprüfung vom 24.09.2026, Mangel 1: Die Torsion am Master-Ende galt
    als gehalten, sobald dort kein Gelenk saß - auch mit dem Torsionsgelenk
    am anderen Ende oder einem anderen Ende, das nur in x, y, z gelagert ist.
    Dazu zählt eine Last, deren Moment die Hilfsfesselung des Lösers nimmt,
    nicht mehr als getragen (_getragen_je_richtung)."""
    faelle = ["RBE3, loser Master und loser Slave", "RBE3, loser Master an den Deckelknoten",
              "RBE3, Master am Deckelknoten, loser Slave",
              "RBE3, loser Master 0,3 m über einem Deckelknoten",
              "RBE3, loser Master 0,3 m über zwei Deckelknoten",
              "RBE3, loser Master 0,3 m über einer Deckelreihe",
              "RBE3, loser Master auf einer Deckelreihe", "RBE3, loser Master auf seinem einzigen Slave",
              "RBE3, loser Master 0,3 m über drei Deckelknoten, nicht auf einer Linie",
              "RBE3, loser Master 0,3 m über einem Deckelknoten, in x und y angekoppelt",
              "RBE2, loser Master und loser Slave", "RBE2 am Deckelknoten, ein Slave 0,5 m daneben",
              "Kopplung nur in z", "Kopplungen in x+y und z, dazu x-y",
              "Kette: x, y direkt, z über h", "Kette: x, y direkt, z über h, Last an h",
              "Kette: x, y, z an h, das nur in z hängt",
              "Spaltelement allein", "Anschlag: in x, y, z gelagert, Spaltelement",
              "Spaltelement, Knoten nur in z gelagert", "Spaltelement an einem Anschlag"]
    texte = {}
    for fall in faelle:
        m, ziel, soll = _knoten_am_wuerfel(fall)
        kb = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Knoten ohne Element"]
        lose = sorted(kb[0].knoten) if kb else []
        befund_ok = (lose == sorted(soll) and (not kb or (len(kb) == 1 and kb[0].stufe == "FEHLER")))
        if kb:
            texte[fall] = kb[0].text
        getragen = _getragen_je_richtung(lambda f=fall: _knoten_am_wuerfel(f)[:2])
        if fall == "RBE3, Master am Deckelknoten, loser Slave":
            passt = all(getragen)
        else:
            passt = all(getragen) == (ziel not in lose)
        check(f"{fall}: lose {len(soll)}, Rechnung passt dazu",
              befund_ok and passt,
              f"Abnahme {[(b.stufe, b.knoten) for b in kb]}, soll {soll}; x/y/z getragen {getragen}")
    # Mangel 2: Der Text behauptet keinen Verlust als Tatsache - er sagt, was
    # die Abnahme nicht findet, und was folgt, wo der Halt wirklich fehlt. Den
    # RBE3-Slave, der trägt, nennt er als solchen; andere Fälle nicht.
    rbe3 = "RBE3, Master am Deckelknoten, loser Slave"
    ohne_rbe3 = [t for f, t in texte.items() if not f.startswith("RBE3")]
    check("Text: kein Verlust als Tatsache, RBE3-Slave als solcher genannt",
          all("keinen Halt" in t and "ginge" not in t and "Wo der Halt" in t for t in texte.values())
          and "Slave eines RBE3" in texte.get(rbe3, "") and "festlegt" in texte.get(rbe3, "")
          and ohne_rbe3 and not any("RBE3" in t for t in ohne_rbe3),
          texte.get(rbe3, "(kein Befund)")[-260:])
    # Drehsteifer Master: am Stabende hält ein RBE2 auch einen einzelnen
    # Slave, soweit das Stabende die Verdrehung hält. Ein Momentengelenk gibt
    # die Verdrehung um seine lokale Achse frei; der Slave wird dann nur in
    # Richtung (Achse x Versatz) nicht gehalten (Mangel 2: Gelenk 11 mit
    # Versatz in z trug in x, y, z, die Abnahme meldete FEHLER). Geprüft je
    # Versatz in x, y, z gegen die Rechnung, auch am schrägen und am um 30°
    # gerollten Stab.
    #
    # 3. Gegenprüfung vom 24.09.2026, Mangel 1: Die Torsion hält ein Stab nur
    # zusammen mit seinem anderen Ende. Ein Torsionsgelenk dort (Gelenk 3 am
    # eingespannten Anfang) oder ein anderes Ende, das nur in x, y, z
    # gelagert ist, gibt sie auch am Master-Ende frei; bei 8c4fb14 meldete
    # die Abnahme dort nichts, und die Last quer brach ab bzw. ging an die
    # Hilfsfesselung. Dazu je eine Kette aus zwei Stäben (die Torsion kommt
    # über den ersten Stab vom Lager) und eine Rahmenecke (der zweite Stab
    # hält die Torsion des ersten über seine Biegung).
    from statik3d.profiles import make_section as _ms

    def rahmen(punkte, staebe, lager, master, versatz):
        """Stäbe IPE 200 zwischen ``punkte``, je (i, j, Gelenke, roll);
        ``lager`` je (Knoten, Art); ein RBE2 am Knoten ``master`` mit einem
        Slave im Abstand ``versatz``."""
        mb = Model("Stab")
        mb.add_material(Material.steel("S235"))
        mb.add_section(_ms("IPE 200"))
        for p_ in punkte:
            mb.add_node(*p_)
        for i, j, gel_, roll_ in staebe:
            mb.add_element("beam", [i, j], "S235", "IPE 200")
            mb.elements[-1].roll = roll_
            if gel_:
                mb.elements[-1].hinges = list(gel_)
        for n_, art in lager:
            mb.fix(n_, art)
        d_ = int(mb.add_node(*(np.asarray(mb.nodes[master], float) + versatz)))
        mb.add_starrkoerper(master, [d_])
        return mb, d_

    def stab(gelenke, ende, roll=0.0, lager_ende=None):
        """Ein Stab von (0|0|0) nach ``ende``, der Anfang eingespannt."""
        return ([(0.0, 0.0, 0.0), ende], [(0, 1, gelenke, roll)],
                [(0, "all")] + ([(1, lager_ende)] if lager_ende else []), 1)
    # Versatz 0,5 m in x, y, z; am schrägen und am gerollten Stab dazu in
    # Richtung seiner lokalen z-Achse, um die Gelenk 11 dreht (von Hand:
    # Stab (1,1,1) - ez = (-1,-1,2)/√6; um 30° gerollt - ez = (0, -1/2, √3/2))
    achsen = [("x", (0.5, 0.0, 0.0)), ("y", (0.0, 0.5, 0.0)), ("z", (0.0, 0.0, 0.5))]
    x2 = (2.0, 0.0, 0.0)
    gelenkig = stab([], x2, lager_ende="xyz")
    gelenkig[2][0] = (0, "xyz")
    varianten = (("ohne Gelenk", stab([], x2), achsen),
                 ("Gelenke 9, 10, 11", stab([9, 10, 11], x2), achsen),
                 ("Gelenk 11", stab([11], x2), achsen),
                 ("Gelenk 10", stab([10], x2), achsen),
                 ("Gelenk 9", stab([9], x2), achsen),
                 ("Gelenke 10, 11", stab([10, 11], x2), achsen),
                 ("Gelenk 11, Stab schräg", stab([11], (1.2, 1.2, 1.2)),
                  achsen + [("lokal z", tuple(0.5 * np.array([-1.0, -1.0, 2.0]) / np.sqrt(6.0)))]),
                 ("Gelenk 11, um 30° gerollt", stab([11], x2, float(np.radians(30.0))),
                  achsen + [("lokal z", (0.0, -0.25, 0.25 * np.sqrt(3.0)))]),
                 ("Gelenk 3 am eingespannten Anfang", stab([3], x2), achsen),
                 ("Gelenke 3 und 11", stab([3, 11], x2), achsen),
                 ("Gelenke 3 und 9", stab([3, 9], x2), achsen),
                 ("beide Enden nur in x, y, z gelagert", gelenkig, achsen),
                 ("Gelenk 5 am eingespannten Anfang, Ende in x, y, z gelagert",
                  stab([5], x2, lager_ende="xyz"), achsen),
                 ("Kette aus zwei Stäben", ([(0.0, 0.0, 0.0), x2, (4.0, 0.0, 0.0)],
                                            [(0, 1, [], 0.0), (1, 2, [], 0.0)], [(0, "all")], 2), achsen),
                 ("Kette, Gelenk 3 am ersten Stab", ([(0.0, 0.0, 0.0), x2, (4.0, 0.0, 0.0)],
                                                     [(0, 1, [3], 0.0), (1, 2, [], 0.0)], [(0, "all")], 2),
                  achsen),
                 ("Rahmenecke, Gelenk 3 am ersten Stab", ([(0.0, 0.0, 0.0), x2, (2.0, 2.0, 0.0)],
                                                         [(0, 1, [3], 0.0), (1, 2, [], 0.0)],
                                                         [(0, "all"), (2, "xyz")], 1), achsen),
                 ("Rahmenecke, dazu Gelenk 4 am zweiten Stab", ([(0.0, 0.0, 0.0), x2, (2.0, 2.0, 0.0)],
                                                               [(0, 1, [3], 0.0), (1, 2, [4], 0.0)],
                                                               [(0, "all"), (2, "xyz")], 1), achsen))
    zaehl = {True: 0, False: 0}
    for name, bau_, versaetze in varianten:
        for vname, v in versaetze:
            mb, d = rahmen(*bau_, np.asarray(v))
            kb = [x for x in dg.abnahme(mb, warnungen=True) if x.pruefung == "Knoten ohne Element"]
            getragen = _getragen_je_richtung(lambda b_=bau_, w=np.asarray(v): rahmen(*b_, w))
            zaehl[bool(kb)] += 1
            check(f"RBE2 am Stabende, {name}, Slave 0,5 m in {vname}: "
                  f"{'lose' if kb else 'angeschlossen'}, Rechnung passt dazu",
                  (not kb) == all(getragen) and (not kb or kb[0].knoten == [d]),
                  f"Abnahme {[(x.stufe, x.knoten) for x in kb]}; x/y/z getragen {getragen}")
    # beide Seiten müssen vorkommen, sonst prüft die Schleife nichts
    check("  Stabenden: gemeldete und nicht gemeldete Fälle kommen vor",
          zaehl[True] >= 3 and zaehl[False] >= 3, str(zaehl))
    from statik3d import mesher
    ms = Model("Schale")
    ms.add_material(Material.steel("S235"))
    ms.add_shell_prop(ShellProp("t", 0.02))
    ids = mesher.grid_plate(ms, "S235", "t", 1.0, 1.0, 2, 2)
    for n in ids[0, :]:
        ms.fix(int(n), "all")
    d = int(ms.add_node(*(np.asarray(ms.nodes[int(ids[2, 2])]) + [0.0, 0.0, 0.5])))
    ms.add_starrkoerper(int(ids[2, 2]), [d])
    kb = [x for x in dg.abnahme(ms, warnungen=True) if x.pruefung == "Knoten ohne Element"]
    check("RBE2 am Schalenknoten, ein Slave: angeschlossen", not kb,
          str([(x.stufe, x.knoten) for x in kb]))
    from statik3d import examples_lib
    mk = examples_lib.contact_example()
    kb = [x for x in dg.abnahme(mk, warnungen=True) if x.pruefung == "Knoten ohne Element"]
    check("Beispiel „Kontakt: abhebendes Lager“: Anschlag am Spaltelement ohne Befund",
          not kb and len(mk.gap_elements) == 1, str([(x.stufe, x.knoten) for x in kb]))


def _randschleifen_alt(F, Xf, S) -> list:
    """diagnose._randschleifen bis zum 23.09.2026 (je Seite eine
    Python-Schleife mit np.cross) - als Vergleich."""
    zahl: dict = {}
    for i in range(len(F)):
        r = [j for j in range(4) if F[i][j] >= 0]
        P = Xf[i][r]
        n_ring = 0.5 * sum(np.cross(P[j], P[(j + 1) % len(r)]) for j in range(len(r)))
        kn = [int(F[i][j]) for j in r]
        if float(n_ring @ S[i]) < 0.0:
            kn = kn[::-1]
        for j in range(len(kn)):
            a, b = kn[j], kn[(j + 1) % len(kn)]
            zahl[(a, b)] = zahl.get((a, b), 0) + 1
            zahl[(b, a)] = zahl.get((b, a), 0) - 1
    lage: dict = {}
    for i in range(len(F)):
        for j in range(4):
            if F[i][j] >= 0:
                lage[int(F[i][j])] = Xf[i][j]
    weiter: dict = {}
    for (a, b), k in zahl.items():
        for _ in range(max(k, 0)):
            weiter.setdefault(a, []).append(b)
    schleifen = []
    while weiter:
        start = next(iter(weiter))
        schleife, a = [start], start
        while True:
            b = weiter[a].pop()
            if not weiter[a]:
                del weiter[a]
            if b == start or b not in weiter:
                break
            schleife.append(b)
            a = b
        schleifen.append((schleife, np.array([lage[k] for k in schleife])))
    return schleifen


def _seitengruppen_alt(F, nur_paare: bool = False) -> list:
    """diagnose._seitengruppen bis zum 23.09.2026 (Vereinigungs-Suche in
    Python) - als Vergleich."""
    m = len(F)
    an_kante: dict = {}
    for i in range(m):
        ecken = [int(k) for k in F[i] if k >= 0]
        for a, b in zip(ecken, ecken[1:] + ecken[:1]):
            an_kante.setdefault((min(a, b), max(a, b)), []).append(i)
    wurzel = list(range(m))

    def finde(i):
        while wurzel[i] != i:
            wurzel[i] = wurzel[wurzel[i]]
            i = wurzel[i]
        return i

    for seiten in an_kante.values():
        if nur_paare and len(seiten) != 2:
            continue
        for j in seiten[1:]:
            ra, rb = finde(seiten[0]), finde(j)
            if ra != rb:
                wurzel[rb] = ra
    gruppen: dict = {}
    for i in range(m):
        gruppen.setdefault(finde(i), []).append(i)
    return [np.asarray(g) for g in gruppen.values()]


def _nicht_konform(n):
    """tet4-Netz n x n x n über den Einheitswürfel mit derselben Fünferzerlegung
    in jeder Zelle - nicht konform: jede innere Zellseite ist beiderseits
    verschieden in Dreiecke geteilt, ein Riss (so baute grid_box bis c85b9cc)."""
    m = Model("riss")
    m.add_material(Material.steel("S235"))
    ids = np.zeros((n + 1,) * 3, int)
    for i in range(n + 1):
        for j in range(n + 1):
            for kk in range(n + 1):
                ids[i, j, kk] = m.add_node(i / n, j / n, kk / n)
    for i in range(n):
        for j in range(n):
            for kk in range(n):
                c = [ids[i, j, kk], ids[i + 1, j, kk], ids[i + 1, j + 1, kk], ids[i, j + 1, kk],
                     ids[i, j, kk + 1], ids[i + 1, j, kk + 1], ids[i + 1, j + 1, kk + 1],
                     ids[i, j + 1, kk + 1]]
                for t in ((0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)):
                    m.add_element("tet4", [int(c[x]) for x in t], "S235")
    k = _quaderkoerper(m, [ids[0, 0, 0], ids[n, 0, 0], ids[n, n, 0], ids[0, n, 0],
                           ids[0, 0, n], ids[n, 0, n], ids[n, n, n], ids[0, n, n]])
    k.elemente = list(range(len(m.elements)))
    return m, k


def test_abnahme_riss_gestapelt():
    """Nebenbefund B052 (22./23.09.2026): _randschleifen lief je Seite in
    Python mit einem np.cross je Seite, _seitengruppen je Seite und Kante.
    Am nicht konformen tet4-Netz n = 20 (40 000 Elemente, 91 200 Rissseiten)
    brauchte _abnahme_netz bei ec6448c 14,7 bis 15,0 s; im Profil entfielen
    23,2 von 28,5 s auf _randschleifen (282 985 Aufrufe von np.cross). Jetzt
    gestapelt: ein np.cross je Gruppe, gezählt mit np.unique, verkettet wird
    nur der Rand; die Gruppen über scipy.sparse.csgraph.connected_components.
    Neu 2,3 bis 2,7 s im selben Prozess.

    Geprüft: dieselben Gruppen und Randschleifen wie der alte Stand (Reihenfolge
    eingeschlossen), derselbe Befund, und im selben Lauf höchstens die Hälfte
    der Zeit des alten Stands (n = 10, 5000 Elemente, 10 800 Rissseiten).
    """
    import time
    m, k = _nicht_konform(10)
    els = k.elemente
    F, _E = dg._freie_seiten_ecken(m, els)
    Xf = m.nodes[np.maximum(F, 0)]
    viereck = F[:, 3] >= 0
    S = 0.5 * np.cross(Xf[:, 1] - Xf[:, 0], Xf[:, 2] - Xf[:, 0])
    S[viereck] = 0.5 * np.cross(Xf[viereck, 2] - Xf[viereck, 0], Xf[viereck, 3] - Xf[viereck, 1])
    # Wechselnde Richtung der Flächenvektoren, damit auch das Umkehren der
    # Seiten verglichen wird
    S[::3] *= -1.0

    def gleich_gruppen(a, b):
        return len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b))

    def gleich_schleifen(a, b):
        return len(a) == len(b) and all(ka == kb and np.array_equal(Pa, Pb)
                                        for (ka, Pa), (kb, Pb) in zip(a, b))
    # Alle freien Seiten hängen zusammen (eine Gruppe); in viele Gruppen
    # zerfallen sie, wenn nur ein Teil davon genommen wird - zufällig
    # gezogen, fest gesät
    rng = np.random.default_rng(7)
    teile = [np.arange(len(F))] + [np.sort(rng.choice(len(F), z, replace=False))
                                   for z in (600, 2000, 5000)]
    abweichend, n_gruppen = [], 0
    for t_i, auswahl in enumerate(teile):
        Ft = F[auswahl]
        for paare in (False, True):
            g_neu, g_alt = dg._seitengruppen(Ft, nur_paare=paare), _seitengruppen_alt(Ft, paare)
            n_gruppen += len(g_alt)
            if not gleich_gruppen(g_neu, g_alt):
                abweichend.append(f"Gruppen {t_i} {paare}")
            for g in g_alt[:300]:
                idx = auswahl[g]
                if not gleich_schleifen(dg._randschleifen(F[idx], Xf[idx], S[idx]),
                                        _randschleifen_alt(F[idx], Xf[idx], S[idx])):
                    abweichend.append(f"Schleifen {t_i} {g[:3]}")
    # dazu Stücke von je 40 Seiten am Stück, auch aus mehreren Hohlräumen
    for s in range(0, len(F), 40):
        idx = np.arange(s, min(s + 40, len(F)))
        if not gleich_schleifen(dg._randschleifen(F[idx], Xf[idx], S[idx]),
                                _randschleifen_alt(F[idx], Xf[idx], S[idx])):
            abweichend.append(f"Stück {s}")
    check("gestapelt: dieselben Gruppen und Randschleifen wie der alte Stand",
          len(F) == 12000 and n_gruppen > 1000 and not abweichend,
          f"{len(F)} freie Seiten, {n_gruppen} Gruppen verglichen; abweichend {abweichend[:5]}")

    def lauf():
        dauer, bef = [], None
        for _ in range(2):
            t = time.perf_counter()
            bef = dg._abnahme_volumenbilanz(m, "K1", k, els)
            dauer.append(time.perf_counter() - t)
        return min(dauer), [(b.stufe, b.pruefung, b.wert, b.text) for b in bef]
    t_neu, b_neu = lauf()
    echt = dg._randschleifen, dg._seitengruppen
    dg._randschleifen, dg._seitengruppen = _randschleifen_alt, _seitengruppen_alt
    try:
        t_alt, b_alt = lauf()
    finally:
        dg._randschleifen, dg._seitengruppen = echt
    check("  derselbe Befund (WARNUNG Riss im Netz 10 800), in höchstens der halben Zeit",
          b_neu == b_alt and [x[:3] for x in b_neu] == [("WARNUNG", "Riss im Netz", 10800.0)]
          and t_neu <= 0.5 * t_alt,
          f"neu {t_neu:.2f} s, alt {t_alt:.2f} s; {[x[:3] for x in b_neu]}")


def _platte(lx, ly, lz, nx, ny, nz):
    """hex8-Netz nx x ny x nz ueber lx x ly x lz als Koerper K1."""
    from statik3d import mesher
    m = Model("platte")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", lx, ly, lz, nx, ny, nz, typ="hex8")
    k = _quaderkoerper(m, [ids[0, 0, 0], ids[nx, 0, 0], ids[nx, ny, 0], ids[0, ny, 0],
                           ids[0, 0, nz], ids[nx, 0, nz], ids[nx, ny, nz], ids[0, ny, nz]])
    k.elemente = list(range(len(m.elements)))
    for kn in ids[:, :, 0].ravel():
        m.fix(int(kn), "all")
    return m, k


def test_abnahme_luecke_je_regel():
    """Nebenbefunde der Gegenprüfungen vom 22./23.09.2026 (B041): Drei Regeln
    der Lücke im Netzrand legte keine Prüfung fest. Je eine Verfälschung in
    diagnose.py ließ die Suite ganz bestehen (gemessen an ec6448c, 112 von
    112):

    * `_schliesspunkt` ohne „kein gemeinsamer Punkt“ und „Fächer nicht auf
      der Hülle“,
    * `_schliesspunkt` ohne „jede Kante der Schleife in einer Randfläche“,
    * der Fächeranteil des Lückenvolumens mal 0. Alle Lücken der Suite hatten
      eine Schleife, und deren Fächer trägt nichts bei, weil sein Punkt p₀
      der Bezugspunkt des Volumens ist.

    Hier je ein Fall, den nur diese Regel entscheidet.
    """
    def kurz(bef):
        return "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"

    def ohne(m, k, pruef):
        weg = [i for i in k.elemente if pruef(m.nodes[m.elements[i].nodes].mean(axis=0))]
        V = float(dg.elementvolumina(m, weg).sum())
        k.elemente = [i for i in k.elemente if i not in weg]
        return len(weg), V, dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)

    # Kerbe durch die ganze Dicke am Rand y = 0 einer Platte 1 x 1 x 0,125 m
    # (16 x 16 x 2 hex8, zwei Zellen fehlen): Die Schleife laeuft ueber Deckel,
    # Boden und Seitenflaeche, deren Ebenen keinen gemeinsamen Punkt haben -
    # ein Faecher von einem Punkt schliesst sie nicht. Ohne die beiden
    # Abweisungen in _schliesspunkt war es gemessen „WARNUNG Lücke im
    # Netzrand 3,255e-4 m³“, zwei Drittel der fehlenden 4,883e-4 m³: Der
    # Faecher von p0 in halber Hoehe laeuft durch den Koerper (23.09.2026).
    m, k = _platte(1.0, 1.0, 0.125, 16, 16, 2)
    n, V, bef = ohne(m, k, lambda c: 7 / 16 < c[0] < 8 / 16 and c[1] < 1 / 16)
    check("Kerbe durch die ganze Dicke am Rand: FEHLER Seiten im Inneren, keine Lücke",
          n == 2 and [(b.stufe, b.pruefung, b.wert) for b in bef]
          == [("FEHLER", "Seiten im Inneren", 6.0)],
          f"{n} Zellen fehlen ({V:.4g} m³): {kurz(bef)}")

    # Loch durch die ganze Dicke in der Mitte derselben Platte: zwei
    # Schleifen, im Deckel und im Boden, je mit eigenem p0. Der Faecher der
    # zweiten zaehlt mit; ohne ihn waren es gemessen 3,255e-4 statt
    # 4,883e-4 m³ (23.09.2026).
    m, k = _platte(1.0, 1.0, 0.125, 16, 16, 2)
    n, V, bef = ohne(m, k, lambda c: 7 / 16 < c[0] < 8 / 16 and 7 / 16 < c[1] < 8 / 16)
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    check("  Loch durch die ganze Dicke (zwei Schleifen): Lücke mit dem Volumen der Zellen",
          n == 2 and len(bef) == 1 and len(lu) == 1 and lu[0].stufe == "WARNUNG"
          and abs(lu[0].wert - V) < 1e-9 * V,
          f"{n} Zellen fehlen ({V:.6g} m³): " + "; ".join(
              f"{b.stufe} {b.pruefung} {b.wert:.6g}" for b in bef))

    # Jede Kante der Schleife liegt in einer Randflaeche: eine Schleife im
    # Deckel des L-Prismas, deren eine Kante ueber die Aussparung laeuft
    # (Mitte 50 mm neben dem Deckel, Toleranz 16,9 mm). Nur diese Regel
    # weist sie ab. Gemessen am 23.09.2026: ohne sie p0 = (0,34 | 1,04 | 0,4).
    # Die Schwerpunkte der fuenf Faecherdreiecke liegen dann auf dem Deckel
    # (Abstand 0), und nur die misst die Abweisung „Faecher nicht auf der
    # Huelle“. Der Faecher selbst liegt nicht ganz auf dem Deckel: zwei
    # seiner Dreiecke reichen ueber die Aussparung, bis 50 mm neben die
    # Huelle (gemessen 24.09.2026). Gegenprobe: dieselbe Schleife um die
    # Ecke (0,45 | 0,45) herum liegt auf der Huelle.
    m = Model("L")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)], 0.0, 0.4)
    huelle = dg._polyederhuelle(m, k)
    punkte = []
    for ring in ([(0.45, 0.8), (0.65, 0.3), (0.1, 0.3), (0.1, 1.9), (0.4, 1.9)],
                 [(0.45, 0.8), (0.45, 0.45), (0.65, 0.3), (0.1, 0.3), (0.1, 1.9), (0.4, 1.9)]):
        P = np.array([[x, y, 0.4] for x, y in ring])
        tol = dg.ABNAHME_HUELLABSTAND * float(np.linalg.norm(np.ptp(P, axis=0)))
        punkte.append(dg._schliesspunkt(P, huelle, tol))
    check("  Schleife mit einer Kante über der Aussparung des L: kein Schließpunkt",
          punkte[0] is None and punkte[1] is not None and abs(float(punkte[1][2]) - 0.4) < 1e-12,
          f"über die Aussparung: {punkte[0]}, um die Ecke: {punkte[1]}")


def _kurz(bef):
    return "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"


def test_abnahme_nennt_nicht_gepruefte_volumenbilanz():
    """B038 (Nebenbefund vom 22./23.09.2026): Die Volumenbilanz übersprang ohne
    ein Wort Körper mit krummen Randlinien und Volumenelemente, die zu keinem
    Körper gehören (etwa ein reiner Netzimport). Am verdrehten Würfelpaar
    gemessen (ec6448c): mit Körper FEHLER Volumenbilanz und Seiten im Inneren;
    dasselbe Netz ohne Körper ``abnahme(warnungen=True) == []``, also
    „bestanden"; mit einer Randlinie vom Typ Bogen ebenso ``[]``.

    Jetzt steht in beiden Fällen eine WARNUNG „Volumenbilanz nicht geprüft“
    da - sie hält nichts an, aber die Überschrift lautet „bestanden, soweit
    geprüft“.
    """
    from statik3d import mesher

    def paar(verdreht=True):
        m = Model("na")
        m.add_material(Material.steel("S235"))
        ids = mesher.grid_box(m, "S235", 2.0, 1.0, 1.0, 2, 1, 1, typ="hex8")
        k = _quaderkoerper(m, [ids[0, 0, 0], ids[2, 0, 0], ids[2, 1, 0], ids[0, 1, 0],
                               ids[0, 0, 1], ids[2, 0, 1], ids[2, 1, 1], ids[0, 1, 1]])
        k.elemente = [0, 1]
        for kn in ids[0].ravel():
            m.fix(int(kn), "all")
        if verdreht:
            _verdrehen(m, 1)
        return m

    m = paar()
    check("verdrehtes Würfelpaar mit Körper: FEHLER Volumenbilanz und Seiten im Inneren",
          [b.pruefung for b in dg.abnahme(m)] == ["Volumenbilanz", "Seiten im Inneren"],
          _kurz(dg.abnahme(m, warnungen=True)))
    m = paar()
    m.koerper.clear()
    alle = dg.abnahme(m, warnungen=True)
    ng = [b for b in alle if b.pruefung == "Volumenbilanz nicht geprüft"]
    check("dasselbe Netz ohne Körper: WARNUNG „Volumenbilanz nicht geprüft“ mit der Elementzahl",
          len(ng) == 1 and ng[0].stufe == "WARNUNG" and ng[0].wert == 2.0
          and "keinem Körper" in ng[0].text and not dg.abnahme(m),
          _kurz(alle) + " | " + (ng[0].text[:160] if ng else ""))
    m = paar()
    next(iter(m.lines.values())).typ = "arc"
    alle = dg.abnahme(m, warnungen=True)
    ng = [b for b in alle if b.pruefung == "Volumenbilanz nicht geprüft"]
    check("mit einer Randlinie vom Typ Bogen: WARNUNG „nicht geprüft“ mit Körper und Grund",
          len(ng) == 1 and ng[0].objekt == "K1" and "krumme Randlinie" in ng[0].text
          and ng[0].stufe == "WARNUNG" and not dg.abnahme(m),
          _kurz(alle) + " | " + (ng[0].text[:160] if ng else ""))
    # Die Oberflaeche zaehlt jede Zeile, deren Pruefung auf „nicht geprüft"
    # endet, in die Ueberschrift „bestanden, soweit geprüft (N Prüfungen fielen aus)"
    check("  die Zeile zählt in „bestanden, soweit geprüft“",
          bool(ng) and ng[0].pruefung.endswith("nicht geprüft"), str([b.pruefung for b in alle]))
    # Gegenprobe: das richtige Paar mit Koerper bleibt ohne jede Zeile
    m = paar(verdreht=False)
    check("  Gegenprobe: das richtige Paar mit Körper hat keine Zeile",
          not dg.abnahme(m, warnungen=True), _kurz(dg.abnahme(m, warnungen=True)))


def _tstoss(art="hex8"):
    """T-Stoß in einem Körper 2 x 1 x 1 m: links ein hex8 1 x 1 x 1, rechts
    2 x 2 x 2 hex8 der Kante 0,5 - die Knoten der rechten Seite x = 1 liegen
    auf der Seite des linken Elements (netz_r3/tstoss.py); ``tet4``: jede
    Zelle in sechs Kuhn-Tetraeder zerlegt."""
    m = Model("tstoss")
    m.add_material(Material.steel("S235"))
    kn = {}

    def k(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in kn:
            kn[key] = int(m.add_node(x, y, z))
        return kn[key]

    def hexa(x0, y0, z0, d):
        P = [(x0, y0, z0), (x0 + d, y0, z0), (x0 + d, y0 + d, z0), (x0, y0 + d, z0),
             (x0, y0, z0 + d), (x0 + d, y0, z0 + d), (x0 + d, y0 + d, z0 + d), (x0, y0 + d, z0 + d)]
        m.add_element("hex8", [k(*p) for p in P], "S235")

    hexa(0, 0, 0, 1.0)
    for i in range(2):
        for j in range(2):
            for l_ in range(2):
                hexa(1 + 0.5 * i, 0.5 * j, 0.5 * l_, 0.5)
    kb = _quaderkoerper(m, [k(0, 0, 0), k(2, 0, 0), k(2, 1, 0), k(0, 1, 0),
                            k(0, 0, 1), k(2, 0, 1), k(2, 1, 1), k(0, 1, 1)])
    kb.elemente = list(range(len(m.elements)))
    if art == "tet4":
        _in_kuhn(m, kb)
    return m, kb


def _ecke_tstoss(n=8, art="hex8"):
    """hex8-Netz n x n x n über dem Würfel 1 x 1 x 1 m, die Eckzelle (0, 0, 0)
    in 2 x 2 x 2 Zellen geteilt: ihre Knoten auf den drei Seiten zu den
    Nachbarzellen hängen, und der Rand dieser Seiten liegt auf der Hülle."""
    m = Model("ecke")
    m.add_material(Material.steel("S235"))
    h = 1.0 / n
    kn = {}

    def k(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in kn:
            kn[key] = int(m.add_node(x, y, z))
        return kn[key]

    def hexa(x0, y0, z0, d):
        P = [(x0, y0, z0), (x0 + d, y0, z0), (x0 + d, y0 + d, z0), (x0, y0 + d, z0),
             (x0, y0, z0 + d), (x0 + d, y0, z0 + d), (x0 + d, y0 + d, z0 + d), (x0, y0 + d, z0 + d)]
        m.add_element("hex8", [k(*p) for p in P], "S235")

    for i in range(n):
        for j in range(n):
            for l_ in range(n):
                if i == j == l_ == 0:
                    for a in range(2):
                        for b in range(2):
                            for c in range(2):
                                hexa(a * h / 2, b * h / 2, c * h / 2, h / 2)
                else:
                    hexa(i * h, j * h, l_ * h, h)
    kb = _quaderkoerper(m, [k(0, 0, 0), k(1, 0, 0), k(1, 1, 0), k(0, 1, 0),
                            k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)])
    kb.elemente = list(range(len(m.elements)))
    if art == "tet4":
        _in_kuhn(m, kb)
    return m, kb


def _schach(n, fein=None):
    """hex8-Netz n x n x n über dem Würfel 1 x 1 x 1 m; die Zellen in
    ``fein`` (ohne Angabe jede Zelle mit gerader Indexsumme, ein Schachbrett)
    in 2 x 2 x 2 Zellen geteilt - ein T-Stoß an jeder Seite zwischen einer
    feinen und einer groben Zelle (Gegenprüfung vom 23.09.2026,
    g2_nb_diagnose_1/p_schach.py)."""
    m = Model("schach")
    m.add_material(Material.steel("S235"))
    h = 1.0 / n
    kn = {}

    def k(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in kn:
            kn[key] = int(m.add_node(x, y, z))
        return kn[key]

    def hexa(x0, y0, z0, d):
        P = [(x0, y0, z0), (x0 + d, y0, z0), (x0 + d, y0 + d, z0), (x0, y0 + d, z0),
             (x0, y0, z0 + d), (x0 + d, y0, z0 + d), (x0 + d, y0 + d, z0 + d), (x0, y0 + d, z0 + d)]
        m.add_element("hex8", [k(*p) for p in P], "S235")

    for i in range(n):
        for j in range(n):
            for l_ in range(n):
                if ((i + j + l_) % 2 == 0) if fein is None else ((i, j, l_) in fein):
                    for a in range(2):
                        for b in range(2):
                            for c in range(2):
                                hexa(i * h + a * h / 2, j * h + b * h / 2, l_ * h + c * h / 2, h / 2)
                else:
                    hexa(i * h, j * h, l_ * h, h)
    kb = _quaderkoerper(m, [k(0, 0, 0), k(1, 0, 0), k(1, 1, 0), k(0, 1, 0),
                            k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)])
    kb.elemente = list(range(len(m.elements)))
    return m, kb


def _gefunden(bef):
    """Der Teil „Gefunden: …“ des FEHLERs „Seiten im Inneren“."""
    for b in bef:
        if b.pruefung == "Seiten im Inneren":
            i = b.text.find("Gefunden:")
            return b.text[i:b.text.find(". ", i)] if i >= 0 else ""
    return ""


def test_abnahme_t_stoss_nennt_haengende_knoten():
    """B040 (Nebenbefund vom 22./23.09.2026): Ein T-Stoß - ein Ufer feiner
    geteilt als das andere, seine Knoten liegen auf den Seiten des Nachbarn -
    gibt zwei offene Gruppen ohne gemeinsame Kante und damit FEHLER „Seiten
    im Inneren“ (hex8 1 gegen 2 x 2 x 2: 5 Seiten, dasselbe in Kuhn-Tetraedern:
    10; ec6448c). Der Text nannte als Ursache aber nur verdrehtes Element,
    doppelte Knoten oder Hohlraum - die hängenden Knoten fehlten.

    Liegt der T-Stoß in einer Ecke, schließt der Rand beider Ufer an die
    Hülle an. Am Stand ec6448c hielt die Abnahme in Kuhn-Tetraedern jedes
    Ufer für eine „Lücke im Netzrand“ mit dem Volumen des Eckblocks (zwei
    Lücken, zusammen 3906 cm³, nur WARNUNG, ``abnahme() == []``), in hex8
    eines (Lücke 1953 cm³ neben FEHLER 12; nachgemessen am 24.09.2026) -
    obwohl nichts fehlt. Ein Ufer mit Gegenüber ist keine Lücke.

    Die erste Kur (70614f8) suchte die hängenden Knoten nur zwischen offenen
    Gruppen (Gegenprüfung vom 23.09.2026, Mangel 1): der T-Stoß im Inneren -
    zwei geschlossene Gruppen - hieß „verdrehtes Element an 24 Seiten; ein
    Hohlraum im Netz an 6 Seiten“, in Kuhn-Tetraedern „Hohlraum an 60“, und
    im Schachbrett 8 x 8 x 8, wo die feinen Ufer als Riss gelten, hießen die
    groben „Netzrand verfehlt die Randfläche“ mit dem Rat zum Sweep.
    """
    for art, zahl in (("hex8", 5.0), ("tet4", 10.0)):
        m, k = _tstoss(art)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        check(f"T-Stoß {art}: FEHLER Seiten im Inneren {zahl:.0f}, Ursache hängende Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "hängende Knoten" in bef[0].text and "verdrehtes Element" not in bef[0].text,
              _kurz(bef) + " | " + (bef[0].text[bef[0].text.find("Gefunden"):][:200] if bef else ""))
    for art in ("hex8", "tet4"):
        m, k = _ecke_tstoss(8, art)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        check(f"T-Stoß in der Ecke ({art}): FEHLER hängende Knoten, keine Lücke",
              [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
              and "hängende Knoten" in bef[0].text
              and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
              _kurz(bef))
    # T-Stoss im Inneren: die Mittelzelle eines 3 x 3 x 3-Netzes geteilt,
    # Summe der Elementvolumina genau 1 - kein Hohlraum, nichts verdreht
    for art, zahl in (("hex8", 30.0), ("tet4", 60.0)):
        m, k = _schach(3, {(1, 1, 1)})
        if art == "tet4":
            _in_kuhn(m, k)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"T-Stoß im Inneren ({art}): FEHLER {zahl:.0f}, nur hängende Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "hängende Knoten" in gef and f"an {zahl:.0f} Seiten" in gef
              and "verdreht" not in gef and "Hohlraum" not in gef,
              _kurz(bef) + " | " + gef[:160])
    # Schachbrett 8 x 8 x 8: die feinen Ufer gelten als Riss (ihr Rand 9,8 %
    # der Seitenflaeche, unter ABNAHME_RISS_UFER), die groben bleiben FEHLER -
    # ihr Gegenueber ist die Riss-Gruppe
    m, k = _schach(8)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    fehler = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("Schachbrett 8 x 8 x 8: FEHLER 1344 hängende Knoten neben WARNUNG Riss 5376, kein Sweep-Rat",
          [(b.stufe, b.pruefung, b.wert) for b in bef]
          == [("FEHLER", "Seiten im Inneren", 1344.0), ("WARNUNG", "Riss im Netz", 5376.0)]
          and "hängende Knoten" in gef and "an 1344 Seiten" in gef and "Netzrand" not in gef
          and "sweepen" not in fehler[0].text,
          _kurz(bef) + " | " + gef[:160])


def test_abnahme_doppelte_knoten_relativ_zur_kante():
    """B042 (Nebenbefund vom 22./23.09.2026): Doppelte Knoten galten nur bis
    1e-6 m als „am selben Ort“, fest und unabhängig von der Elementgröße. Im
    Block 6 x 6 x 6 über 0,75 m (Zelle 125 mm), in Kuhn-Tetraeder zerlegt, war
    Tetraeder 554 an Knoten 0 oder 1 losgelöst, der neue Knoten 2e-6 oder
    1e-5 m versetzt, nur eine WARNUNG „Riss im Netz 6“ mit ``abnahme() == []``
    - keine Rückfrage vor dem Rechnen (r2_netz_1/r3/p2_doppelt.py, ec6448c).
    Am losgelösten Knoten passt aber nichts zusammen.

    Jetzt zählen zwei Nummern als doppelt, wenn sie näher beieinander liegen
    als 1 % der kürzesten Kante an ihnen, und ein Knoten, den im Körper nur
    ein Element benutzt, macht einen dünnen Hohlraum nie zum Riss - bei 5 mm
    Versatz (4 % der Kante) findet ihn nur noch diese zweite Bedingung.
    """
    for versatz in (2e-6, 1e-5, 1e-3, 5e-3):
        for stelle in (0, 1):
            m, k = _gleichmaessig(0.75, 0.75, 0.75, 6)
            _in_kuhn(m, k)
            nd = list(m.elements[554].nodes)
            nd[stelle] = int(m.add_node(*(m.nodes[nd[stelle]] + versatz * np.array([0.6, 0.0, 0.8]))))
            m.elements[554].nodes = nd
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            check(f"Tetraeder 554 an Knoten {stelle} losgelöst, {versatz:g} m versetzt: FEHLER 6",
                  [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)]
                  and "doppelte Knoten" in bef[0].text
                  and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
                  _kurz(bef))
    # Dasselbe an der Oberflaeche: Kuhn-Tetraeder 164 an der Seite x = 0 des
    # 8 x 8 x 8-Netzes (Zelle 125 mm), an seinen drei Huellknoten losgeloest.
    # Bei ec6448c ab 1e-5 m Versatz nur WARNUNG „Lücke im Netzrand“ 651 cm³,
    # abnahme() leer - obwohl nichts fehlt (gemessen 23.09.2026)
    # Die Ursache im Text: ueber 1 % der Kante (1,25 mm) hiess es bei der
    # ersten Kur (70614f8) „hängende Knoten (ein Ufer feiner geteilt …)“ -
    # beide Ufer sind aber gleich geteilt (Gegenpruefung vom 23.09.2026)
    for versatz in (1e-5, 1.3e-3, 2e-3):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        _in_kuhn(m, k)
        nd = list(m.elements[164].nodes)
        for j in (0, 1, 2):
            nd[j] = int(m.add_node(*(m.nodes[nd[j]] + versatz * np.array([0.6, 0.0, 0.8]))))
        m.elements[164].nodes = nd
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"Tetraeder 164 an der Oberfläche an drei Knoten losgelöst, {versatz:g} m: "
              "FEHLER 6 doppelte Knoten, keine Lücke",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)]
              and "doppelte Knoten" in gef and "an 6 Seiten" in gef and "hängende" not in gef
              and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
              _kurz(bef) + " | " + gef[:120])
    # Sechsflaechner 27 an der Seite x = 0, an seinen vier Huellknoten
    # losgeloest: bei der ersten Kur ab 1,3 mm „verdrehtes Element“ (seine
    # Kanten teilt kein Nachbar mehr)
    for versatz in (1e-5, 2e-3):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        el = m.elements[27]
        P = m.nodes[el.nodes]
        nd = list(el.nodes)
        for j in [j for j in range(8) if abs(P[j][0]) < 1e-9]:
            nd[j] = int(m.add_node(*(P[j] + versatz * np.array([0.6, 0.0, 0.8]))))
        el.nodes = nd
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"Sechsflächner 27 an vier Hüllknoten losgelöst, {versatz:g} m: FEHLER 8 doppelte Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 8.0)]
              and "doppelte Knoten" in gef and "an 8 Seiten" in gef and "verdreht" not in gef,
              _kurz(bef) + " | " + gef[:120])
    # Sechsflaechner 292 im Inneren an allen acht Knoten losgeloest: die
    # Seiten der Nachbarn hiessen bei der ersten Kur „Hohlraum“
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    nd = list(m.elements[292].nodes)
    for j in range(8):
        nd[j] = int(m.add_node(*(m.nodes[nd[j]] + 1e-5 * np.array([0.6, 0.0, 0.8]))))
    m.elements[292].nodes = nd
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("Sechsflächner 292 an allen acht Knoten losgelöst: FEHLER 12, nur doppelte Knoten",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 12.0)]
          and "doppelte Knoten" in gef and "an 12 Seiten" in gef and "Hohlraum" not in gef,
          _kurz(bef) + " | " + gef[:160])
    # Gegenprobe: das verdrehte Eckelement benutzt die Wuerfelecke allein wie
    # im richtigen Netz - es bleibt „verdreht“, nicht „doppelt“
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    _verdrehen(m, 0)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("  Gegenprobe: verdrehtes Eckelement 0 - Ursache verdreht, nicht doppelt",
          [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
          and "verdrehtes Element" in gef and "doppelte" not in gef,
          _kurz(bef) + " | " + gef[:120])
    # Innerer Block 2 x 2 x 2 mit eigenen Knoten auf seiner Oberflaeche: in
    # Kuhn-Tetraedern benutzt jeden Knoten mehr als ein Element, dort findet
    # nur die Suche nach doppelten Knoten die Ursache - bei der ersten Kur
    # (70614f8) „Hohlraum an 96 Seiten“, hex8 „doppelt 24, Hohlraum 24“
    for art, zahl in (("hex8", 48.0), ("tet4", 96.0)):
        m, k = _block_getrennt(1e-5, art)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"innerer Block 2 x 2 x 2 abgetrennt ({art}, 1e-05 m): FEHLER {zahl:.0f}, nur doppelte Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "doppelte Knoten" in gef and f"an {zahl:.0f} Seiten" in gef,
              _kurz(bef) + " | " + gef[:160])


def _block_getrennt(versatz=0.0, art="hex8", lo=3, hi=5, n=8, richtung=(0.6, 0.0, 0.8),
                    haengt_an=None):
    """hex8-Netz n x n x n über dem Würfel 1 x 1 x 1 m, der innere Block der
    Zellen lo..hi-1 je Richtung auf seiner Oberfläche mit eigenen Knoten, um
    ``versatz`` in ``richtung`` (Einheitsvektor) verschoben: eine geschlossene
    Trennfläche im Inneren; ``tet4``: danach in Kuhn-Tetraeder zerlegt.
    ``haengt_an``: Lage eines Knotens der Blockoberfläche, den der Block mit
    dem übrigen Netz teilt (er hängt dort an einem Knoten)."""
    m, k = _gleichmaessig(1.0, 1.0, 1.0, n)
    a, b = lo / n, hi / n
    w = np.asarray(richtung, float)
    neu = {}
    for e in list(k.elemente):
        el = m.elements[e]
        c = m.nodes[el.nodes].mean(axis=0)
        if not ((c > a) & (c < b)).all():
            continue
        nd = []
        for x in el.nodes:
            p = m.nodes[int(x)]
            if haengt_an is not None and np.allclose(p, haengt_an):
                nd.append(int(x))
                continue
            if ((p >= a - 1e-9) & (p <= b + 1e-9)).all() and (
                    (np.abs(p - a) < 1e-9) | (np.abs(p - b) < 1e-9)).any():
                if int(x) not in neu:
                    neu[int(x)] = int(m.add_node(*(p + versatz * w)))
                nd.append(neu[int(x)])
            else:
                nd.append(int(x))
        el.nodes = nd
    if art == "tet4":
        _in_kuhn(m, k)
    return m, k


def _teilung(n, teil, standard=2):
    """hex8-Netz n x n x n Zellen über dem Würfel 1 x 1 x 1 m, jede Zelle in
    standard³ Elemente geteilt, die Zellen in ``teil`` ({(i, j, l): t}) in
    t³ - gleiche Lagen haben eine Knotennummer, verschieden geteilte Nachbarn
    teilen nur die Ecken ihrer Zellen."""
    m = Model("teilung")
    m.add_material(Material.steel("S235"))
    h = 1.0 / n
    kn = {}

    def k(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in kn:
            kn[key] = int(m.add_node(x, y, z))
        return kn[key]

    for i in range(n):
        for j in range(n):
            for l_ in range(n):
                t = teil.get((i, j, l_), standard)
                d = h / t
                for a in range(t):
                    for b in range(t):
                        for c in range(t):
                            x0, y0, z0 = i * h + a * d, j * h + b * d, l_ * h + c * d
                            P = [(x0, y0, z0), (x0 + d, y0, z0), (x0 + d, y0 + d, z0),
                                 (x0, y0 + d, z0), (x0, y0, z0 + d), (x0 + d, y0, z0 + d),
                                 (x0 + d, y0 + d, z0 + d), (x0, y0 + d, z0 + d)]
                            m.add_element("hex8", [k(*p) for p in P], "S235")
    kb = _quaderkoerper(m, [k(0, 0, 0), k(1, 0, 0), k(1, 1, 0), k(0, 1, 0),
                            k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)])
    kb.elemente = list(range(len(m.elements)))
    return m, kb


def test_abnahme_losgeloester_bereich_schraeg_versetzt():
    """Gegenprüfung vom 24.09.2026 zu f2bf6c8 (Mängel M1 und M2): Alle
    Prüfungen der losgelösten Bereiche verschoben in Richtung (0,6 | 0 | 0,8).
    Deren y-Anteil 0 hält die Knoten für die Seiten quer zu y in der Ebene.
    In Richtung (1 | 1 | 1)/√3, aus der Ebene jeder Seite heraus, fand die
    Abnahme das Gegenüber nicht mehr, sobald die Knoten weiter als 1 % der
    längsten Seitenkante von den Seiten entfernt lagen, und der Nachbar des
    losgelösten Bereichs hieß „Hohlraum“. Gemessen an f2bf6c8 im
    8 x 8 x 8-Netz (Kante 125 mm): innerer Block 2 x 2 x 2 in
    Kuhn-Tetraedern bei 2 und 3 mm „hängende Knoten 96“, ab 4 mm „Hohlraum
    96“; hex8 292 an allen acht Knoten ab 3 mm „doppelte Knoten 6; Hohlraum
    6“, der hex8-Block ab 3 mm „doppelte Knoten 24; Hohlraum 24“. In
    Richtung (0,6 | 0 | 0,8) hieß der Tetraeder-Block ab 2 mm „hängende
    Knoten“, obwohl kein Ufer feiner geteilt ist.

    Gegenproben: Ein echter Hohlraum (Element bzw. Block fehlt) heißt weiter
    „Hohlraum“. Ufer, die verschieden geteilt sind und nur die Ecken ihrer
    Zellen teilen (2 x 2 gegen 3 x 3), heißen weiter „hängende Knoten“; die
    T-Stöße prüft test_abnahme_t_stoss_nennt_haengende_knoten.
    """
    r3 = (1 / np.sqrt(3.0),) * 3
    faelle = []
    for v in (2e-3, 3e-3, 5e-3, 1e-2):
        faelle.append((f"Tetraeder-Block (1|1|1)/√3 {v * 1e3:g} mm", 96.0,
                       lambda v=v: _block_getrennt(v, "tet4", richtung=r3)))
    faelle.append(("Tetraeder-Block (0,6|0|0,8) 2 mm", 96.0,
                   lambda: _block_getrennt(2e-3, "tet4")))
    faelle.append(("Tetraeder-Block an einem Knoten hängend, (1|1|1)/√3 5 mm", 96.0,
                   lambda: _block_getrennt(5e-3, "tet4", richtung=r3,
                                           haengt_an=(0.375, 0.375, 0.375))))
    for v in (3e-3, 5e-3):
        faelle.append((f"hex8-Block (1|1|1)/√3 {v * 1e3:g} mm", 48.0,
                       lambda v=v: _block_getrennt(v, "hex8", richtung=r3)))

    def hex292(v, knoten=range(8)):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        nd = list(m.elements[292].nodes)
        for j in knoten:
            nd[j] = int(m.add_node(*(m.nodes[nd[j]] + v * np.asarray(r3))))
        m.elements[292].nodes = nd
        return m, k

    for v in (3e-3, 5e-3):
        faelle.append((f"hex8 292 an allen acht Knoten, (1|1|1)/√3 {v * 1e3:g} mm", 12.0,
                       lambda v=v: hex292(v)))
    faelle.append(("hex8 292 an sieben Knoten, (1|1|1)/√3 5 mm", 12.0,
                   lambda: hex292(5e-3, range(1, 8))))
    for titel, zahl, bau in faelle:
        m, k = bau()
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"{titel}: FEHLER {zahl:.0f}, nur doppelte Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "doppelte Knoten" in gef and f"an {zahl:.0f} Seiten" in gef
              and "Hohlraum" not in gef and "hängende" not in gef,
              _kurz(bef) + " | " + gef[:200])
    # Gegenprobe: Ufer, die nur die Ecken der Zelle teilen und verschieden
    # geteilt sind (2 x 2 gegen 3 x 3, keines verfeinert das andere), bleiben
    # „hängende Knoten“ wie an f2bf6c8 - hiesse ein Gegenueber nur dann
    # haengend, wenn alle Ecken der Seite Knoten des anderen Ufers sind,
    # waeren es „doppelte Knoten“
    for art, zahl, offen in (("hex8", 52.0, True), ("hex8", 78.0, False),
                             ("tet4", 104.0, True), ("tet4", 156.0, False)):
        if offen:
            m, k = _teilung(2, {(1, j, l_): 3 for j in range(2) for l_ in range(2)})
        else:
            m, k = _teilung(3, {(1, 1, 1): 3})
        if art == "tet4":
            _in_kuhn(m, k)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"  Gegenprobe: Ufer 2 x 2 gegen 3 x 3 ({art}, {'an der Hülle' if offen else 'im Inneren'}): "
              f"FEHLER {zahl:.0f}, hängende Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "hängende Knoten" in gef and f"an {zahl:.0f} Seiten" in gef and "doppelte" not in gef,
              _kurz(bef) + " | " + gef[:160])
    # Gegenprobe: echte Hohlraeume bleiben „Hohlraum"
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    k.elemente = [e for e in k.elemente if e != 292]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("  Gegenprobe: hex8 292 fehlt - FEHLER 6, Hohlraum",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)]
          and "Hohlraum" in gef and "an 6 Seiten" in gef and "doppelte" not in gef,
          _kurz(bef) + " | " + gef[:160])
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    _in_kuhn(m, k)
    weg = {e for e in k.elemente
           if ((m.nodes[m.elements[e].nodes].mean(axis=0) > 0.375)
               & (m.nodes[m.elements[e].nodes].mean(axis=0) < 0.625)).all()}
    k.elemente = [e for e in k.elemente if e not in weg]
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("  Gegenprobe: Tetraeder-Block 2 x 2 x 2 fehlt - Hohlraum an 48 Seiten",
          len(weg) == 48 and [b.pruefung for b in bef] == ["Volumenbilanz", "Seiten im Inneren"]
          and "Hohlraum" in gef and "an 48 Seiten" in gef and "doppelte" not in gef,
          f"{len(weg)} entfernt | " + _kurz(bef) + " | " + gef[:160])


def _anisotrop(n, teil):
    """hex8-Netz n x n x n Zellen über dem Würfel 1 x 1 x 1 m, die Zellen in
    ``teil`` ({(i, j, l): (tx, ty, tz)}) je Richtung in tx, ty, tz Elemente
    geteilt - auch nur in einer oder zwei Richtungen. Dann teilen grobes und
    feines Ufer Kanten (Gegenprüfung vom 24.09.2026, zweite Runde, M1:
    g4_nb_diagnose_1/r2/aniso.py)."""
    m = Model("anisotrop")
    m.add_material(Material.steel("S235"))
    h = 1.0 / n
    kn = {}

    def k(x, y, z):
        key = (round(x, 9), round(y, 9), round(z, 9))
        if key not in kn:
            kn[key] = int(m.add_node(x, y, z))
        return kn[key]

    for i in range(n):
        for j in range(n):
            for l_ in range(n):
                tx, ty, tz = teil.get((i, j, l_), (1, 1, 1))
                dx, dy, dz = h / tx, h / ty, h / tz
                for a in range(tx):
                    for b in range(ty):
                        for c in range(tz):
                            x0, y0, z0 = i * h + a * dx, j * h + b * dy, l_ * h + c * dz
                            P = [(x0, y0, z0), (x0 + dx, y0, z0), (x0 + dx, y0 + dy, z0),
                                 (x0, y0 + dy, z0), (x0, y0, z0 + dz), (x0 + dx, y0, z0 + dz),
                                 (x0 + dx, y0 + dy, z0 + dz), (x0, y0 + dy, z0 + dz)]
                            m.add_element("hex8", [k(*p) for p in P], "S235")
    kb = _quaderkoerper(m, [k(0, 0, 0), k(1, 0, 0), k(1, 1, 0), k(0, 1, 0),
                            k(0, 0, 1), k(1, 0, 1), k(1, 1, 1), k(0, 1, 1)])
    kb.elemente = list(range(len(m.elements)))
    return m, kb


def test_abnahme_t_stoss_mit_geteilter_kante():
    """Gegenprüfung vom 24.09.2026, zweite Runde, M1 (B040 für T-Stöße mit
    geteilten Kanten): Ist eine Zelle nur in einer oder zwei Richtungen
    geteilt, teilen grobes und feines Ufer Kanten und liegen in derselben
    Gruppe. Das Gegenüber wurde nur zwischen verschiedenen Gruppen gesucht,
    und der FEHLER nannte eine Ursache, die nicht vorliegt. Gemessen am
    24.09.2026 an 1afa712 (3 x 3 x 3 hex8 über dem Einheitswürfel, Volumen
    genau 1, det J überall positiv): die Mittelzelle in 2 x 1 x 1 geteilt
    „verdrehtes Element an 12 Seiten“, 2 x 2 x 1 an 22, 3 x 1 x 1 an 16,
    3 x 2 x 1 an 28; in der Eckzelle 6 / 11 / 8 / 14. In Kuhn-Tetraedern die
    Mitte 2 x 2 x 1 „Hohlraum an 44 Seiten“, 3 x 2 x 1 „doppelte Knoten an 56
    Seiten“ (f2bf6c8: „Hohlraum an 56“).

    Jetzt findet die Abnahme die geteilte Kante in der Gruppe selbst: eine
    Kante a-b und eine Kette von Knoten darauf, mit a und b über Kanten der
    Gruppe verbunden.
    """
    for wo, zelle in (("Mitte", (1, 1, 1)), ("Ecke", (0, 0, 0))):
        for t, (mitte, ecke) in (((2, 1, 1), (12, 6)), ((1, 1, 2), (12, 6)), ((2, 2, 1), (22, 11)),
                                 ((3, 1, 1), (16, 8)), ((3, 2, 1), (28, 14))):
            zahl = float(mitte if wo == "Mitte" else ecke)
            m, k = _anisotrop(3, {zelle: t})
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            gef = _gefunden(bef)
            check(f"hex8 3 x 3 x 3, {wo} in {t} geteilt: FEHLER {zahl:.0f}, nur hängende Knoten",
                  [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
                  and "hängende Knoten" in gef and f"an {zahl:.0f} Seiten" in gef
                  and "verdreht" not in gef and "Hohlraum" not in gef and "doppelte" not in gef,
                  _kurz(bef) + " | " + gef[:120])
    for t, zahl in (((2, 2, 1), 44.0), ((3, 2, 1), 56.0)):
        m, k = _anisotrop(3, {(1, 1, 1): t})
        _in_kuhn(m, k)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"Kuhn-Tetraeder 3 x 3 x 3, Mitte in {t} geteilt: FEHLER {zahl:.0f}, nur hängende Knoten",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "hängende Knoten" in gef and f"an {zahl:.0f} Seiten" in gef
              and "Hohlraum" not in gef and "doppelte" not in gef,
              _kurz(bef) + " | " + gef[:120])
    # Die geteilte Kante selbst: ein grobes Dreieck a-b-c und zwei feine
    # a-k-x, k-b-x, k die Mitte von a-b. Gegenprobe: ein flaches Dreieck
    # a-k-b hat dieselben drei Kanten, ist aber kein T-Stoss
    a, b, c, k, x = (np.array(p, float) for p in ((0, 0, 0), (1, 0, 0), (0.5, 1, 0), (0.5, 0, 0),
                                                  (0.5, -1, 0.1)))
    F = np.array([[0, 1, 2, -1], [0, 3, 4, -1], [3, 1, 4, -1]])
    Xf = np.array([[a, b, c, a], [a, k, x, a], [k, b, x, k]])
    check("geteilte Kante a-k-b mit Kanten der feinen Seiten: gefunden",
          dg._halbierte_kante(F, Xf, np.arange(3)))
    F = np.array([[0, 1, 2, -1], [0, 3, 1, -1]])
    Xf = np.array([[a, b, c, a], [a, k, b, a]])
    check("  Gegenprobe: flaches Dreieck a-k-b ist keine geteilte Kante",
          not dg._halbierte_kante(F, Xf, np.arange(2)))
    # Gegenprobe: dieselbe Teilung 2 x 1 x 1 in Kuhn-Tetraedern ist ein Riss
    # ohne Weite (an 1afa712 ebenso) - die Ursache fragt nur, was weder Riss
    # noch Luecke ist
    m, k = _anisotrop(3, {(1, 1, 1): (2, 1, 1)})
    _in_kuhn(m, k)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  Gegenprobe: Kuhn-Tetraeder, Mitte in (2, 1, 1) geteilt - WARNUNG Riss 24 wie vorher",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("WARNUNG", "Riss im Netz", 24.0)], _kurz(bef))


def _zelle8(i, j, l_):
    """Element der Zelle (i, j, l) im gleichmäßigen 8 x 8 x 8-Netz."""
    return 64 * i + 8 * j + l_


def _los8(m, e, v, richtung=(1.0, 1.0, 1.0), knoten=range(8)):
    """Element e an den Knoten ``knoten`` losgelöst: eigene Knoten, um v in
    ``richtung`` versetzt."""
    r = np.asarray(richtung, float) / np.linalg.norm(richtung)
    nd = list(m.elements[e].nodes)
    for j in knoten:
        nd[j] = int(m.add_node(*(m.nodes[nd[j]] + v * r)))
    m.elements[e].nodes = nd


def test_abnahme_hohlraum_neben_losgeloestem_bereich():
    """Gegenprüfung vom 24.09.2026, zweite Runde, M2 (und M1 der zweiten
    Gegenprüfung): Seit 1afa712 hieß ein Hohlraum, in dem ein losgelöster
    Bereich liegt, ganz „doppelte Knoten“, ohne zu fragen, ob der Bereich ihn
    ausfüllt. Fehlt ein Element neben einem losgelösten, verschwand der
    Hohlraum aus dem Text. Gemessen an 1afa712 im 8 x 8 x 8-hex8-Netz (Kante
    125 mm): 292 fehlt, 293 an allen acht Knoten losgelöst, 3 bis 10 mm in
    Richtung (1 | 1 | 1)/√3 - „doppelte Knoten an 16 Seiten“ (f2bf6c8:
    „doppelt 6; Hohlraum 10“); der Block 3 x 3 x 3 fehlt bis auf die
    Mittelzelle, die frei darin schwebt - „doppelt 60“ (f2bf6c8: „doppelt 6;
    Hohlraum 54“). Bei 0 und 1 mm (Knoten näher als 1 % der Kante) hieß der
    Hohlraum schon an f2bf6c8 „doppelt“: die doppelten Knoten liegen auf
    seinen Seiten.

    Jetzt heißt ein Hohlraum nur „doppelt“, wenn die losgelösten Bereiche
    darin ihn bis auf höchstens ABNAHME_HOHLRAUM_REST mal das mittlere
    Element am Hohlraum ausfüllen, sonst „Hohlraum“.
    """
    def fall(v, weg, los, knoten=range(8), kuhn=False):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        for e in los:
            _los8(m, e, v, knoten=knoten)
        k.elemente = [e for e in k.elemente if e not in weg]
        if kuhn:
            hexe = [list(m.elements[e].nodes) for e in k.elemente]
            m.elements.clear()
            for c in hexe:
                for t in _KUHN:
                    m.add_element("tet4", [int(c[x]) for x in t], "S235")
            k.elemente = list(range(len(m.elements)))
        return m, k

    kern_weg = {_zelle8(i, j, l_) for i in (2, 3, 4) for j in (2, 3, 4) for l_ in (2, 3, 4)} - {
        _zelle8(3, 3, 3)}
    faelle = []
    for v in (0.0, 3e-3, 1e-2):
        faelle.append((f"292 fehlt, 293 los {v * 1e3:g} mm", 16.0, 6, 10,
                       lambda v=v: fall(v, {292}, {293})))
    faelle.append(("292 und 293 fehlen, 294 los 5 mm", 20.0, 6, 14, lambda: fall(5e-3, {292, 293}, {294})))
    faelle.append(("292 fehlt, 293 an sieben Knoten los 10 mm", 16.0, 6, 10,
                   lambda: fall(1e-2, {292}, {293}, knoten=range(1, 8))))
    faelle.append(("Block 3 x 3 x 3 fehlt, Mittelzelle schwebt (hex8)", 60.0, 6, 54,
                   lambda: fall(0.0, kern_weg, set())))
    faelle.append(("dasselbe in Kuhn-Tetraedern", 120.0, 12, 108,
                   lambda: fall(0.0, kern_weg, set(), kuhn=True)))

    def block_ohne_ecke(v):
        m, k = _block_getrennt(v, "hex8", richtung=(1 / np.sqrt(3.0),) * 3)
        k.elemente = [e for e in k.elemente if e != _zelle8(3, 3, 3)]
        return m, k

    for v in (0.0, 5e-3):
        faelle.append((f"hex8-Block los {v * 1e3:g} mm, seine Zelle (3,3,3) fehlt", 48.0, 24, 24,
                       lambda v=v: block_ohne_ecke(v)))

    def tet_block_neben(v):
        m, k = _block_getrennt(v, "tet4", richtung=(1 / np.sqrt(3.0),) * 3)
        k.elemente = [e for e in k.elemente if e != 6 * _zelle8(5, 4, 4)]
        return m, k

    for v in (0.0, 5e-3):
        faelle.append((f"Tetraeder-Block los {v * 1e3:g} mm, ein Tetraeder daneben fehlt", 100.0, 96, 4,
                       lambda v=v: tet_block_neben(v)))
    # Gegenproben, die an 1afa712 schon richtig waren: das losgeloeste
    # Element liegt weit weg vom Hohlraum bzw. nur in seinem Kasten
    faelle.append(("  Gegenprobe: 292 fehlt, (6,6,6) los 5 mm (weit weg)", 18.0, 12, 6,
                   lambda: fall(5e-3, {292}, {_zelle8(6, 6, 6)})))
    l_weg = {_zelle8(i, 1, 1) for i in (1, 2, 3)} | {_zelle8(1, j, 1) for j in (2, 3)}
    faelle.append(("  Gegenprobe: L-Hohlraum in Kuhn-Tetraedern, (3,3,1) in seinem Kasten los", 68.0, 24, 44,
                   lambda: fall(0.0, l_weg, {_zelle8(3, 3, 1)}, kuhn=True)))
    # Die losgeloesten Zellen liegen im Kasten des Hohlraums, nicht in ihm,
    # und haben zusammen sein Volumen: L aus 9 Zellen, die 3 x 3 x 1 Zellen
    # in seiner Ecke je an allen acht Knoten losgeloest. Nur ueber den Kasten
    # gefragt hiesse der L „doppelt" - es braucht die Windungszahl
    l9 = {_zelle8(i, 1, 1) for i in range(1, 6)} | {_zelle8(1, j, 1) for j in range(2, 6)}
    k9 = {_zelle8(i, j, 1) for i in (3, 4, 5) for j in (3, 4, 5)}
    faelle.append(("  Gegenprobe: L aus 9 Zellen, 3 x 3 x 1 Zellen in seinem Kasten los", 122.0, 84, 38,
                   lambda: fall(0.0, l9, k9)))
    # die Faelle der Gegenpruefung genau so: der Nachbar 300 statt 293, und
    # 292 selbst los, seine Nachbarn 293 und 294 fehlen
    faelle.append(("292 fehlt, 300 los 5 mm", 16.0, 6, 10, lambda: fall(5e-3, {292}, {300})))
    faelle.append(("292 los 3 mm, 293 und 294 fehlen", 20.0, 6, 14, lambda: fall(3e-3, {293, 294}, {292})))
    for titel, zahl, n_d, n_h, bau in faelle:
        m, k = bau()
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
        check(f"{titel}: FEHLER {zahl:.0f}, doppelt {n_d}, Hohlraum {n_h}",
              len(sn) == 1 and sn[0].stufe == "FEHLER" and sn[0].wert == zahl
              and f"doppelte Knoten (" in gef and f") an {n_d} Seiten; ein Hohlraum" in gef
              and gef.endswith(f"an {n_h} Seiten") and "verdreht" not in gef and "hängende" not in gef,
              _kurz(bef) + " | " + gef[-120:])
    # Gegenproben zur Grenze: ein ausgefuellter Hohlraum bleibt „doppelt" -
    # auch der Spalt am losgeloesten Knoten (B042), 30 mm (24 % der Kante)
    # in den Tetraeder hinein, V_rest 0,21 des mittleren Elements
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    _los8(m, 293, 1e-2, knoten=range(1, 8))
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("  Gegenprobe: 293 an sieben Knoten los 10 mm, nichts fehlt - nur doppelte Knoten 12",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 12.0)]
          and "doppelte Knoten" in gef and "an 12 Seiten" in gef and "Hohlraum" not in gef,
          _kurz(bef) + " | " + gef[-80:])
    m, k = _gleichmaessig(0.75, 0.75, 0.75, 6)
    _in_kuhn(m, k)
    nd = list(m.elements[554].nodes)
    nd[1] = int(m.add_node(*(m.nodes[nd[1]] + 3e-2 * np.array([0.6, 0.0, 0.8]))))
    m.elements[554].nodes = nd
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("  Gegenprobe: Tetraeder 554 an Knoten 1 losgelöst, 30 mm - doppelte Knoten 6, kein Hohlraum",
          [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 6.0)]
          and "doppelte Knoten" in gef and "Hohlraum" not in gef,
          _kurz(bef) + " | " + gef[-80:])


def test_abnahme_hohlraum_mit_einspringender_kante():
    """Gegenprüfung vom 24.09.2026, zweite Runde, M2: In hex8 bekam ein
    echter Hohlraum mit einspringender Kante oder Ecke die Ursache
    „verdrehtes Element“ bzw. „doppelte Knoten“, obwohl kein Element verdreht
    oder losgelöst ist. Eine Kante, die nach dem Entfernen nur noch ein
    Element trägt, galt als verdreht, und ein Knoten, den nur ein Element
    benutzt, machte die Gruppe „doppelt“. Gemessen an 1afa712 im
    8 x 8 x 8-hex8-Netz, ganze Zellen entfernt: L aus 3 Zellen „verdrehtes
    Element an 14 Seiten“, Kreuz aus 7 „verdreht an 30“, Block 2 x 2 x 2 ohne
    eine Ecke „doppelte Knoten an 24“, L aus 5 Zellen in der Lage z = 1
    „verdreht an 22“, die Lagen 2 und 3 des Blocks 3 x 3 x 3 ohne die
    Mittelzelle, die an der Lage 4 hängt, „doppelt an 46“. In
    Kuhn-Tetraedern hießen dieselben Hohlräume richtig „Hohlraum“.

    Jetzt zählt für geschlossene Gruppen als verdreht nur, wessen einsame
    Kante die Diagonale einer Nachbarseite ist, und ein Knoten in nur einem
    Element macht einen dicken Hohlraum nicht mehr „doppelt“.
    """
    def ohne(zellen):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        weg = {_zelle8(*z) for z in zellen}
        k.elemente = [e for e in k.elemente if e not in weg]
        return m, k

    blk = {(i, j, l_) for i in (3, 4) for j in (3, 4) for l_ in (3, 4)}
    formen = (
        ("L aus 3 Zellen", {(3, 3, 3), (4, 3, 3), (3, 4, 3)}, 14.0),
        ("Kreuz aus 7 Zellen", {(4, 4, 4), (3, 4, 4), (5, 4, 4), (4, 3, 4), (4, 5, 4), (4, 4, 3), (4, 4, 5)},
         30.0),
        ("Block 2 x 2 x 2 ohne eine Ecke", blk - {(4, 4, 4)}, 24.0),
        ("L aus 5 Zellen in der Lage z = 1", {(1, 1, 1), (2, 1, 1), (3, 1, 1), (1, 2, 1), (1, 3, 1)}, 22.0),
        ("Lagen 2 und 3 des Blocks 3 x 3 x 3, Mittelzelle hängt an Lage 4",
         {(i, j, l_) for i in (2, 3, 4) for j in (2, 3, 4) for l_ in (2, 3)} - {(3, 3, 3)}, 46.0),
    )
    for titel, zellen, zahl in formen:
        m, k = ohne(zellen)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
        check(f"hex8, {titel} fehlt: FEHLER {zahl:.0f}, nur Hohlraum",
              len(sn) == 1 and sn[0].wert == zahl and "Hohlraum" in gef and f"an {zahl:.0f} Seiten" in gef
              and "verdreht" not in gef and "doppelte" not in gef,
              _kurz(bef) + " | " + gef[:120])
    # Das losgeloeste Element neben dem L bleibt „doppelt", der L „Hohlraum"
    m, k = ohne({(1, 1, 1), (2, 1, 1), (3, 1, 1), (1, 2, 1), (1, 3, 1)})
    _los8(m, _zelle8(3, 3, 1), 0.0)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("hex8, L aus 5 Zellen fehlt, (3,3,1) losgelöst: doppelt 12, Hohlraum 22",
          "doppelte Knoten (" in gef and ") an 12 Seiten; ein Hohlraum" in gef and gef.endswith("an 22 Seiten")
          and "verdreht" not in gef, _kurz(bef) + " | " + gef[-80:])
    # Gegenproben: verdrehte Sechsflaechner bleiben „verdreht" - ihre einsame
    # Kante ist die Diagonale einer Nachbarseite
    for e in (292, 36, 0):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        _verdrehen(m, e)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"  Gegenprobe: hex8 {e} verdreht - nur verdrehtes Element",
              [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
              and "verdrehtes Element" in gef and "Hohlraum" not in gef and "doppelte" not in gef,
              _kurz(bef) + " | " + gef[:120])


def _ecke_getrennt(zellen=1, versatz=0.0, n=8):
    """hex8-Netz n x n x n über dem Würfel 1 x 1 x 1 m, der Block der zellen³
    Eckzellen bei (0, 0, 0) auf seinen drei Seiten zu den Nachbarn mit eigenen
    Knoten, um ``versatz`` in Richtung (0,6 | 0 | 0,8) verschoben: eine
    Trennfläche aus doppelten Knoten, deren Rand auf der Hülle liegt."""
    m, k = _gleichmaessig(1.0, 1.0, 1.0, n)
    grenze = zellen / n
    neu = {}
    for e in list(k.elemente):
        el = m.elements[e]
        if not (m.nodes[el.nodes].mean(axis=0) < grenze).all():
            continue
        nd = []
        for x in el.nodes:
            p = m.nodes[int(x)]
            if (p <= grenze + 1e-9).all() and (np.abs(p - grenze) < 1e-9).any():
                if int(x) not in neu:
                    neu[int(x)] = int(m.add_node(*(p + versatz * np.array([0.6, 0.0, 0.8]))))
                nd.append(neu[int(x)])
            else:
                nd.append(int(x))
        el.nodes = nd
    return m, k


def test_abnahme_duenne_luecke_und_ufer_ohne_gegenueber():
    """B044 (Nebenbefund vom 22./23.09.2026): Ob einer offenen Gruppe an der
    Oberfläche ein Stück fehlt, entschied allein t/L ≤ 5 % („ein Ufer ohne
    Volumen“) - dieselbe Längenabhängigkeit wie beim Riss. Am L-Prisma h 0,2
    (1493 tet4, ohne Befund) wurde das von Hand gelöschte Element 62
    (1,643e-4 m³, 2V/A/L der Lücke 2,87 %) ein FEHLER „Seiten im Inneren 3“
    statt einer Lücke; ebenso die Elemente 69 und 70 (4,50 und 3,36 %).
    Das Netz ist das des Vernetzers vom Stand ec6448c (_netz_ec6448c): der
    Vernetzer vom 23.09.2026 gibt dort 1364 tet4 mit anderen Nummern.

    Ein Ufer ohne Volumen gibt es an der Oberfläche nicht: Liegen die Seiten
    weiter als 1 % neben der Hülle, schließen sie mit ihr ein Volumen ein.
    Was „kein Stück fehlt“ wirklich trennt, ist das Gegenüber: Die Ufer einer
    Trennfläche aus doppelten Knoten schließen jedes für sich mit der Hülle
    den ganzen Block dahinter ein, obwohl er vernetzt ist. Um die Eckzelle
    eines 8 x 8 x 8-Netzes, 1e-5 m versetzt: bei ec6448c WARNUNG „Lücke im
    Netzrand“ 1953 cm³ neben FEHLER 3. Das Ufer bleibt ein FEHLER.
    """
    import contextlib
    import io
    from statik3d import mesher
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]
    for weg, V_soll in ((62, 1.6426e-4), (69, 2.4951e-4), (70, 2.2450e-4)):
        m = Model("L")
        m.add_material(Material.steel("S235"))
        k = _extrudiert(m, L, 0.0, 0.4)
        _netz_ec6448c("L020", m, k)
        n_el = len(k.elemente)
        vorher = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE]
        m.elemente_loeschen([weg])
        bef = [b for b in dg.abnahme(m, warnungen=True)
               if b.pruefung in _NETZ_BEFUNDE or b.pruefung == "Lücke im Netzrand"]
        check(f"L-Prisma h 0,2, Element {weg} gelöscht: WARNUNG Lücke {V_soll * 1e6:.0f} cm³, kein FEHLER",
              n_el == 1493 and not vorher
              and [(b.stufe, b.pruefung) for b in bef] == [("WARNUNG", "Lücke im Netzrand")]
              and abs(bef[0].wert - V_soll) < 1e-3 * V_soll and not dg.abnahme(m),
              f"{n_el} tet4, vorher {_kurz(vorher)}; gelöscht: {_kurz(bef)}")
    # Ueber 1 % der Kante (1,25 mm) versetzt hiess die Ursache bei der ersten
    # Kur (70614f8) „hängende Knoten (ein Ufer feiner geteilt …)“, obwohl
    # beide Ufer gleich geteilt sind (Gegenpruefung vom 23.09.2026)
    for versatz, zahl in ((0.0, 6.0), (1e-5, 6.0), (2e-3, 6.0), (5e-3, 8.0)):
        m, k = _ecke_getrennt(1, versatz)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"Trennfläche um die Eckzelle, {versatz:g} m versetzt: FEHLER {zahl:.0f} "
              "(doppelte Knoten), keine Lücke",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", zahl)]
              and "doppelte Knoten" in gef and f"an {zahl:.0f} Seiten" in gef and "hängende" not in gef,
              _kurz(bef) + " | " + gef[:120])


def test_abnahme_netzrand_verfehlt_randflaeche():
    """B046 (Nebenbefund vom 22./23.09.2026): Konforme Netze des eigenen
    Vernetzers bekamen FEHLER „Seiten im Inneren“ mit der Ursache „verdrehtes
    Element, doppelte Knoten oder Hohlraum“ - keine davon trifft zu - und
    einer Abhilfe nur für importierte oder von Hand geänderte Netze. U-Prisma
    h 0,3 auf dem Standardweg (1113 tet4, jede innere Seite genau zweimal):
    FEHLER 4 und WARNUNG Netzrand 9; die freien Seiten laufen an den
    einspringenden Kanten durch den Körper, ihr Rand schließt nicht an die
    Randflächen an.

    Jetzt nennt der Text diese Ursache und die Abhilfe, die gemessen wirkt:
    mit „Sechsflächner sweepen“ ist dasselbe U-Prisma ohne Befund (32 hex8,
    16 pent6). Die Abhilfe steht nur dort, wo diese Ursache vorliegt.

    Das tet4-Netz ist das des Vernetzers vom Stand ec6448c (_netz_ec6448c);
    der Vernetzer vom 23.09.2026 gibt am U-Prisma h 0,3 ein Netz aus 317 tet4
    ohne Befund (gemessen 24.09.2026). Der Sweep laeuft wie bisher.
    """
    import contextlib
    import io
    from collections import Counter
    from statik3d import mesher
    U = [(0, 0), (1.5, 0), (1.5, 1), (1.1, 1), (1.1, 0.3), (0.4, 0.3), (0.4, 1), (0, 1)]
    erg = []
    for sweep in (False, True):
        m = Model("U")
        m.add_material(Material.steel("S235"))
        k = _extrudiert(m, U, 0.0, 0.5)
        m.netz.sweep = sweep
        if not sweep:
            _netz_ec6448c("U030", m, k)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.3})
        erg.append((dict(Counter(m.elements[i].typ for i in k.elemente)),
                    [b for b in dg.abnahme(m, warnungen=True)
                     if b.pruefung in _NETZ_BEFUNDE or b.pruefung == "Lücke im Netzrand"]))
    (typen, bef), (typen_s, bef_s) = erg
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    text = sn[0].text if sn else ""
    check("U-Prisma h 0,3, Standardweg: FEHLER 4 mit der Ursache „Netzrand verfehlt die Randfläche“",
          typen == {"tet4": 1113} and len(sn) == 1 and sn[0].wert == 4.0
          and "Netzrand verfehlt die Randfläche" in text
          and "verdrehtes Element" not in text and "hängende Knoten" not in text,
          f"{typen}: {_kurz(bef)} | {text[text.find('Gefunden'):][:220]}")
    check("  und einer Abhilfe für eigene Netze: Sechsflächner sweepen",
          "sweepen" in text and "U-Prisma" in text, text[-420:])
    check("  gemessen: mit Sweep ohne Befund",
          typen_s == {"hex8": 32, "pent6": 16} and not bef_s, f"{typen_s}: {_kurz(bef_s)}")
    # Gegenprobe: am verdrehten Element steht diese Abhilfe nicht
    m, k = _gleichmaessig(1.0, 1.0, 2.0, 10)
    _verdrehen(m, 444)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    check("  Gegenprobe: verdrehtes Element - Ursache verdreht, kein Rat zum Sweep",
          len(bef) == 1 and "verdrehtes Element" in bef[0].text and "sweepen" not in bef[0].text
          and "Netzrand verfehlt" not in bef[0].text,
          bef[0].text[bef[0].text.find("Gefunden"):][:200] if bef else "kein Befund")


def test_abnahme_luecke_abhilfe_bei_gleicher_elementzahl():
    """B047 (Nebenbefund vom 22./23.09.2026): Die Abhilfe „der Vernetzer gmsh
    bzw. Netgen“ der Lücke im Netzrand war mit rund viermal gröberen Netzen
    gemessen: L-Prisma h 0,25 auf dem hs-Weg eigener Vernetzer 821 tet4, gmsh
    203, Netgen 187 - dieselbe Netzweite ergibt bei ihnen weniger Elemente.

    Nachgemessen bei vergleichbarer Elementzahl (Netzweite 60 bis 70 % der
    eigenen; 0,87- bis 1,05-mal so viele Elemente) an allen fünf Prismen:
    ohne Befund. Der Text sagt das jetzt so. Hier das L-Prisma: gmsh bei
    h 0,15 843 tet4, Netgen 713, beide ohne Befund (23.09.2026).

    Verglichen wird mit dem Netz des eigenen Vernetzers, an dem die Lücke
    gemessen ist (Stand ec6448c, 821 tet4, _netz_ec6448c). Der Vernetzer vom
    23.09.2026 gibt am L-Prisma h 0,25 634 tet4 ohne Lücke (gemessen
    24.09.2026); gegen ihn sind gmsh und Netgen bei h 0,25 0,32- bzw. 0,29-mal
    so fein, bei h 0,15 1,33- bzw. 1,12-mal.
    """
    import contextlib
    import io
    from statik3d import mesher
    from statik3d import vernetzer_extern as vx
    L = [(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)]

    def netz(h, vern=None):
        m = Model("L")
        m.add_material(Material.steel("S235"))
        k = _extrudiert(m, L, 0.0, 0.4)
        if vern:
            m.netz.vernetzer = vern
        if vern is None and h == 0.25:
            _netz_ec6448c("L025", m, k)
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                mesher.modell_vernetzen(m, [], workers=1, hs={"K": h})
        return len(k.elemente), [b for b in dg.abnahme(m, warnungen=True)
                                 if b.pruefung in _NETZ_BEFUNDE or b.pruefung == "Lücke im Netzrand"]

    n0, bef0 = netz(0.25)
    lu = [b for b in bef0 if b.pruefung == "Lücke im Netzrand"]
    text = lu[0].text if lu else ""
    check("L-Prisma h 0,25: die Lücke nennt gmsh/Netgen mit dem Hinweis auf die Elementzahl",
          n0 == 821 and len(lu) == 1 and "gmsh" in text and "Netgen" in text
          and "gleich vielen Elementen" in text and "60 bis 70 % der Netzweite" in text,
          text[text.find("Beseitigt"):][:400])
    for vern in ("gmsh", "netgen"):
        if not (vx.gmsh_verfuegbar() if vern == "gmsh" else vx.netgen_verfuegbar()):
            print(f"    {vern}: nicht installiert, übersprungen")
            continue
        n_gleich, _b = netz(0.25, vern)
        n, bef = netz(0.15, vern)
        check(f"  {vern}: dieselbe Netzweite 22 bis 37 % der Elemente, bei 0,15 m vergleichbar und ohne Befund",
              0.22 <= n_gleich / n0 <= 0.37 and 0.85 <= n / n0 <= 1.1 and not bef,
              f"h 0,25: {n_gleich} tet4 ({n_gleich / n0:.2f}), h 0,15: {n} tet4 ({n / n0:.2f}) | {_kurz(bef)}")


#: Netze des eigenen Vernetzers vom Stand ec6448c, festgehalten fuer
#: Pruefungen der Abnahme, die an genau diesen Netzen gemessen sind (Merge
#: der Nebenbefund-Zweige, 24.09.2026). Der Vernetzer vom 23.09.2026
#: (Fable-Sitzung) gibt fuer dieselben Modelle andere Netze: L-Prisma h 0,2
#: 1364 statt 1493 tet4, h 0,25 634 statt 821 tet4 ohne die Luecke, U-Prisma
#: h 0,3 317 statt 1113 tet4 ohne Befund, die Stufe d 0,45 mm mit FEHLER
#: „Seiten im Inneren 81" statt 5. Die Regeln der Abnahme, um die es in diesen
#: Pruefungen geht, lassen sich an den neuen Netzen nicht mehr zeigen.
#: Erzeugt mit dem Programmstand ec6448c (git archive), Aufbau wie in den
#: Pruefungen: L020 und L025 _extrudiert + mesher.modell_vernetzen mit
#: hs {"K": 0,2 bzw. 0,25}; U030 ebenso mit 0,3 und netz.sweep = False;
#: stufe mesher3d.mesh_koerper_frei, Ziellaenge 0,05, intelligent.
_NETZE_EC6448C = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "netze_vernetzer_ec6448c.npz")


def _netz_ec6448c(name, m, k):
    """Das festgehaltene Netz ``name`` (L020, L025, U030, stufe) in das Modell
    ``m`` legen, dessen Koerper ``k`` mit seiner Geometrie schon steht: die
    Knoten der Geometrie muessen gleich sein, dann folgen die Netzknoten und
    die tet4 in derselben Reihenfolge wie damals (dieselben Elementnummern).
    Gibt die Elementnummern zurueck (auch in ``k.elemente``)."""
    d = np.load(_NETZE_EC6448C)
    geo = d[name + "_geo"]
    if m.nn != len(geo) or not np.array_equal(np.asarray(m.nodes, float), geo):
        raise ValueError(f"Geometrie von {name} passt nicht zum festgehaltenen Netz")
    for p in d[name + "_knoten"]:
        m.add_node(*p)
    werkstoff = next(iter(m.materials))
    k.elemente = [int(m.add_element("tet4", [int(x) for x in t], werkstoff))
                  for t in d[name + "_tet4"]]
    return k.elemente


def _ohne8(zellen, kuhn=False):
    """8 x 8 x 8-hex8-Netz über dem Würfel 1 x 1 x 1 m ohne die Zellen
    ``zellen`` ({(i, j, l)}); ``kuhn``: danach in Kuhn-Tetraeder zerlegt."""
    m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
    weg = {_zelle8(*z) for z in zellen}
    k.elemente = [e for e in k.elemente if e not in weg]
    if kuhn:
        hexe = [list(m.elements[e].nodes) for e in k.elemente]
        m.elements.clear()
        for c in hexe:
            for t in _KUHN:
                m.add_element("tet4", [int(c[x]) for x in t], "S235")
        k.elemente = list(range(len(m.elements)))
    return m, k


def _schnitt8(v, richtung=(0.6, 0.0, 0.8), zmax=1.0, kuhn=True, a=1.0, n=8, lage1=None):
    """hex8-Netz n x n x n über dem Würfel a x a x a; die Zellen mit x > a/2
    (bei ``zmax`` < 1 nur die mit z < zmax·a) bekommen auf der Ebene x = a/2
    eigene Knoten, um v in ``richtung`` (Einheitsvektor) versetzt - bei
    zmax = 1 ist der Körper ganz durchtrennt, sonst reißt er von unten ein;
    ``kuhn``: danach in Kuhn-Tetraeder zerlegt (Gegenprüfung vom 24.09.2026,
    dritte Runde, g6_nb_diagnose/p4c_schnitt.py)."""
    m, k = _gleichmaessig(a, a, a, n)
    if lage1 is not None:
        # abgestuft: die erste Knotenebene ueber dem Boden auf z = lage1
        m.nodes[np.abs(m.nodes[:, 2] - a / n) < 1e-9 * a, 2] = lage1
    w = np.asarray(richtung, float)
    neu = {}
    for e in list(k.elemente):
        el = m.elements[e]
        c = m.nodes[el.nodes].mean(axis=0)
        if not (c[0] > 0.5 * a and c[2] < zmax * a):
            continue
        nd = []
        for x in el.nodes:
            p = m.nodes[int(x)]
            if abs(p[0] - 0.5 * a) < 1e-9 * a and (zmax >= 1.0 or p[2] < (zmax - 1e-9) * a):
                if int(x) not in neu:
                    neu[int(x)] = int(m.add_node(*(p + v * w)))
                nd.append(neu[int(x)])
            else:
                nd.append(int(x))
        el.nodes = nd
    if kuhn:
        _in_kuhn(m, k)
    return m, k


def test_abnahme_mulde_mit_einspringender_kante():
    """Gegenprüfung vom 24.09.2026, dritte Runde, M1: Eine Mulde an der
    Oberfläche eines hex8-Netzes mit einspringender Kante bekam die Ursache
    „doppelte Knoten“, obwohl nichts losgelöst ist. Gemessen an 447a5f8 im
    8 x 8 x 8-hex8-Netz (Kante 125 mm), nur Zellen an der Seite z = 0
    entfernt: L aus 3 Zellen „doppelte Knoten an 11 Seiten“, T aus 4 an 14,
    dasselbe L zwei Lagen tief an 19, L an der Kante x = 0 an 9 (70614f8:
    „verdrehtes Element“). Den Knoten (0,5 | 0,5 | 0) benutzt nach dem
    Entfernen nur noch die Zelle (4, 4, 0), und ihre senkrechte Kante dort
    trägt kein anderes Element - beides galt an offenen Gruppen als sicheres
    Zeichen. In Kuhn-Tetraedern ist dieselbe Mulde eine „Lücke im Netzrand“.

    Jetzt gilt ein Knoten in nur einem Element an offenen Gruppen nur als
    losgelöst, wenn ein anderer Knoten näher liegt als die halbe kürzeste
    Kante (an der Mulde: eine ganze Kante), und verdreht heißt ein Element
    dort wie an geschlossenen Gruppen nur, wenn seine einsame Kante die
    Diagonale einer Nachbarseite ist. Was so übrig bleibt und nicht sicher zu
    unterscheiden ist, heißt „keine sicher bestimmte Ursache“ und nennt die
    möglichen - der FEHLER bleibt.
    """
    formen = (("L aus 3 Zellen", {(3, 3, 0), (4, 3, 0), (3, 4, 0)}, 11.0),
              ("T aus 4 Zellen", {(3, 3, 0), (4, 3, 0), (5, 3, 0), (4, 4, 0)}, 14.0),
              ("L aus 3 Zellen, zwei Lagen tief",
               {(3, 3, 0), (4, 3, 0), (3, 4, 0), (3, 3, 1), (4, 3, 1), (3, 4, 1)}, 19.0),
              ("L aus 3 Zellen an der Kante x = 0", {(0, 3, 0), (0, 4, 0), (1, 3, 0)}, 9.0))
    for titel, zellen, zahl in formen:
        m, k = _ohne8(zellen)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
        check(f"hex8, Mulde {titel} an z = 0: FEHLER {zahl:.0f}, keine sicher bestimmte Ursache",
              [b.pruefung for b in bef] == ["Volumenbilanz", "Seiten im Inneren"] and sn[0].wert == zahl
              and "keine sicher bestimmte Ursache" in gef and "Mulde" in gef and f"an {zahl:.0f} Seiten" in gef
              and "doppelte Knoten (" not in gef and "ein verdrehtes Element (" not in gef
              and "Netzrand verfehlt" not in gef and "sweepen" not in sn[0].text,
              _kurz(bef) + " | " + gef[:160])
        m, k = _ohne8(zellen, kuhn=True)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        check(f"  Gegenprobe: dieselbe Mulde in Kuhn-Tetraedern - Lücke im Netzrand",
              [b.pruefung for b in bef] == ["Volumenbilanz", "Lücke im Netzrand"], _kurz(bef))
    # Gegenproben: Mulden ohne einspringende Kante bleiben Luecken
    for titel, zellen in (("1 Zelle", {(3, 3, 0)}), ("2 Zellen in Reihe", {(3, 3, 0), (4, 3, 0)}),
                          ("Block 2 x 2", {(3, 3, 0), (4, 3, 0), (3, 4, 0), (4, 4, 0)}),
                          ("Eckzelle", {(0, 0, 0)})):
        m, k = _ohne8(zellen)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        check(f"  Gegenprobe: hex8, {titel} fehlt an z = 0 - Lücke im Netzrand, kein FEHLER Seiten im Inneren",
              "Lücke im Netzrand" in [b.pruefung for b in bef]
              and "Seiten im Inneren" not in [b.pruefung for b in bef], _kurz(bef))
    # Gegenproben: verdrehte Sechsflaechner an der Oberflaeche bleiben
    # „verdreht" - ihre einsame Kante ist die Diagonale einer Nachbarseite
    for e in (0, 7, 9, 36, 63):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        _verdrehen(m, e)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"  Gegenprobe: hex8 {e} an der Oberfläche verdreht - verdrehtes Element",
              [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
              and "ein verdrehtes Element (" in gef and "sicher bestimmt" not in gef and "doppelte" not in gef,
              _kurz(bef) + " | " + gef[:120])
    # Gegenproben: an der Oberflaeche losgeloest und weit versetzt (bis 30 mm,
    # 24 % der Kante) bleibt „doppelte Knoten" - der Knoten in nur einem
    # Element hat den Knoten des Nachbarn daneben
    for v in (1e-2, 3e-2):
        m, k = _gleichmaessig(1.0, 1.0, 1.0, 8)
        el = m.elements[27]
        P = m.nodes[el.nodes]
        nd = list(el.nodes)
        for j in [j for j in range(8) if abs(P[j][0]) < 1e-9]:
            nd[j] = int(m.add_node(*(P[j] + v * np.array([0.6, 0.0, 0.8]))))
        el.nodes = nd
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"  Gegenprobe: hex8 27 an vier Hüllknoten losgelöst, {v * 1e3:g} mm - doppelte Knoten 9",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 9.0)]
              and "doppelte Knoten (" in gef and "sicher bestimmt" not in gef, _kurz(bef) + " | " + gef[:120])
        m, k = _ecke_getrennt(1, v)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        check(f"  Gegenprobe: Trennfläche um die Eckzelle, {v * 1e3:g} mm - doppelte Knoten 8",
              [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 8.0)]
              and "doppelte Knoten (" in gef and "an 8 Seiten" in gef and "sicher bestimmt" not in gef,
              _kurz(bef) + " | " + gef[:120])


def test_abnahme_durchtrennter_koerper_heisst_doppelt():
    """Gegenprüfung vom 24.09.2026, dritte Runde, M2: Ein Körper, den
    doppelte Knoten in einem Tetraedernetz ganz durchtrennen, bekam die
    Ursache „der Netzrand verfehlt die Randfläche … kein Knoten doppelt“ und
    den Rat zum Sweep. Gemessen an 447a5f8 im 8 x 8 x 8-Netz (Kante 125 mm)
    in Kuhn-Tetraedern, die Zellen x > 0,5 mit eigenen Knoten auf der Ebene
    x = 0,5: bei 3 mm Versatz in Richtung (0,6 | 0 | 0,8) an 256 Seiten, bei
    5 mm an 264, in Richtung (1 | 1 | 1)/√3 bei 5 mm an 272. Die Knoten liegen
    weiter als 1 % der Kante auseinander, und jeden benutzt mehr als ein
    Element. „Netzrand“ war der Rest für jede offene Gruppe ohne andere
    Ursache.

    Jetzt heißt eine offene Gruppe auch dann „doppelte Knoten“, wenn eine
    ihrer Seiten eine Kopie aus eigenen Knoten neben sich hat: eine andere
    freie Seite, deren Knoten je näher als die halbe kürzeste Kante an einem
    Knoten der ersten liegen. Die Nähe allein
    trennt nicht: an der Stufe unten (Netz des eigenen Vernetzers) liegt ein
    Knoten bei 0,27 der Kante an einem anderen, wie der losgelöste Knoten bei
    30 mm Versatz; eine Kopie hat sie nicht.
    """
    r3 = (1 / np.sqrt(3.0),) * 3
    faelle = [(f"ganz, (0,6|0|0,8) {v * 1e3:g} mm", v, (0.6, 0.0, 0.8), 1.0, zahl)
              for v, zahl in ((3e-3, 256.0), (5e-3, 264.0), (1e-2, 272.0), (3e-2, 272.0))]
    faelle += [(f"ganz, (1|1|1)/√3 {v * 1e3:g} mm", v, r3, 1.0, zahl) for v, zahl in ((5e-3, 272.0), (1e-2, 288.0))]
    faelle += [(f"von unten bis z = 0,5, (0,6|0|0,8) {v * 1e3:g} mm", v, (0.6, 0.0, 0.8), 0.5, 144.0)
               for v in (1e-2, 3e-2)]
    faelle.append(("von unten bis z = 0,5, (1|1|1)/√3 10 mm", 1e-2, r3, 0.5, 152.0))
    for titel, v, richtung, zmax, zahl in faelle:
        m, k = _schnitt8(v, richtung, zmax)
        bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
        gef = _gefunden(bef)
        sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
        check(f"Kuhn-Tetraeder, Schnitt x = 0,5 {titel}: FEHLER {zahl:.0f}, doppelte Knoten, kein Rat zum Sweep",
              len(sn) == 1 and sn[0].stufe == "FEHLER" and sn[0].wert == zahl
              and "doppelte Knoten (" in gef and f"an {zahl:.0f} Seiten" in gef
              and "Netzrand verfehlt" not in gef and "sweepen" not in sn[0].text
              and [b.pruefung for b in dg.abnahme(m)] in (["Seiten im Inneren"],
                                                            ["Volumenbilanz", "Seiten im Inneren"]),
              _kurz(bef) + " | " + gef[:160])
    # Gegenprobe: derselbe Schnitt in hex8 hiess schon an 447a5f8 so
    m, k = _schnitt8(3e-3, kuhn=False)
    gef = _gefunden(dg._abnahme_volumenbilanz(m, "K1", k, k.elemente))
    check("  Gegenprobe: derselbe Schnitt in hex8, 3 mm - doppelte Knoten 128",
          "doppelte Knoten (" in gef and "an 128 Seiten" in gef, gef[:120])
    # Gegenprobe: ein Netz des eigenen Vernetzers mit zwei nahen Knoten (0,27
    # der kuerzesten Kante), ohne Kopie einer Seite - bleibt „Netzrand". Das
    # Netz vom Stand ec6448c (_netz_ec6448c): der Vernetzer vom 23.09.2026
    # gibt fuer diese Stufe 1626 tet4 mit FEHLER „Seiten im Inneren 81"
    # (gemessen 24.09.2026).
    import contextlib
    import io
    from statik3d import mesher3d as M3
    d, a, b = 0.00045, 0.2, 0.1
    m = Model("stufe")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, [(0, 0), (a, 0), (a, b * 0.5), (a - d * 0.8, b * 0.5 + d * 0.6), (a, b), (0, b)],
                    0.0, 0.02)
    m.netz.ziellaenge = 0.05
    m.netz.intelligent = True
    _netz_ec6448c("stufe", m, k)
    bef = dg._abnahme_volumenbilanz(m, k.name, k, k.elemente)
    gef = _gefunden(bef)
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("  Gegenprobe: Stufe d 0,45 mm, t 0,02 m, frei vernetzt - FEHLER 5, Netzrand verfehlt die Randfläche",
          len(sn) == 1 and sn[0].wert == 5.0 and "Netzrand verfehlt die Randfläche" in gef
          and "doppelte Knoten (" not in gef and "sweepen" in sn[0].text,
          f"{len(k.elemente)} tet4: " + _kurz(bef) + " | " + gef[:120])


def test_abnahme_riss_mit_knoten_naeher_als_ein_prozent():
    """Gegenprüfung vom 24.09.2026, dritte Runde, M3 (B042): Die relative
    Knotennähe - doppelt heißen zwei Nummern näher als 1 % der kürzesten
    Kante an ihnen, nicht mehr fest 1e-6 m - hielt keine Prüfung fest. Auf
    fest 1e-6 m verfälscht (``paare[d <= 1e-6]``) bestand test_diagnose
    ganz (214/214), die Prüfung von B042 fängt nur den Knoten in nur einem
    Element. Messbar ändert sich aber das Verhalten: Ein Riss von unten
    (Ebene x = 0,5 nur für z < 0,5, die Seite x > 0,5 mit eigenen Knoten) im
    8 x 8 x 8-Netz in Kuhn-Tetraedern, 2e-6 bis 1e-3 m versetzt, ist an
    447a5f8 FEHLER „Seiten im Inneren 128“ (doppelte Knoten), verfälscht nur
    WARNUNG „Riss im Netz 128“ mit ``abnahme() == []`` - der stille Verlust
    aus B042 (ec6448c ebenso).

    Dazu dieselbe Form bei 10 m und 0,1 m Kantenlänge des Würfels, je 0,8 %
    der Zellkante versetzt: fängt auch eine feste Grenze in anderer Größe.
    """
    for a, versaetze in ((1.0, (2e-6, 1e-5, 1e-4, 1e-3)), (10.0, (1e-2,)), (0.1, (1e-4,))):
        for v in versaetze:
            m, k = _schnitt8(v, zmax=0.5, a=a)
            bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
            gef = _gefunden(bef)
            check(f"Riss von unten, Würfel {a:g} m (Kante {a / 8 * 1e3:g} mm), {v:g} m versetzt "
                  f"({v / (a / 8) * 100:.2g} %): FEHLER 128 doppelte Knoten",
                  [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 128.0)]
                  and "doppelte Knoten (" in gef and "an 128 Seiten" in gef
                  and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
                  _kurz(bef) + " | " + gef[:100])
    # Oertlich statt ueber den Koerper (vierte Gegenpruefung vom 24.09.2026,
    # g7_nbd/p4b_gestuft.py): die unterste Zelllage am Riss nur 10 mm hoch,
    # 1 mm versetzt - 0,8 % der Kante 125 mm, aber 10 % der 10 mm. Mit der
    # kuerzesten Kante des ganzen Koerpers statt der an den beiden Knoten
    # (Verfaelschung "naehe_global_min") hiess das nur WARNUNG "Riss im Netz"
    # mit abnahme() == [], wie an ec6448c.
    m, k = _schnitt8(1e-3, zmax=0.5, lage1=0.01)
    bef = dg._abnahme_volumenbilanz(m, "K1", k, k.elemente)
    gef = _gefunden(bef)
    check("Riss von unten im abgestuften Netz (unterste Lage 10 mm), 1 mm versetzt: FEHLER "
          "doppelte Knoten - die Naehe gilt an den beiden Knoten, nicht am Koerper",
          [(b.stufe, b.pruefung) for b in bef] == [("FEHLER", "Seiten im Inneren")]
          and "doppelte Knoten (" in gef
          and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
          _kurz(bef) + " | " + gef[:100])


def main():
    for f in (test_falsche_knotenzahl,
              test_abnahme_findet_verdrehten_sechsflaechner,
              test_abnahme_ohne_fehlalarm_am_freien_netz,
              test_abnahme_luecken_des_vernetzers_sind_risse,
              test_abnahme_offene_gruppen_sind_kein_riss,
              test_abnahme_riss_misst_am_oertlichen_element,
              test_abnahme_riss_an_laenglichen_zellen,
              test_abnahme_windschief_misst_am_oertlichen_element,
              test_abnahme_beule_windschief_nach_richtung,
              test_abnahme_beule_windschief_randknoten,
              test_abnahme_luecke_im_netzrand,
              test_abnahme_luecke_duenn_mit_volumen,
              test_abnahme_knoten_ueber_kopplung,
              test_abnahme_knoten_in_drei_richtungen,
              test_abnahme_riss_gestapelt,
              test_abnahme_findet_gefaltetes_tetraedernetz,
              test_faltungsbefund_nennt_das_uebervolumen_der_volumenbilanz,
              test_faltungsbefund_nur_mit_laufender_volumenbilanz,
              test_faltungsbefund_nennt_nur_gemessene_abhilfe,
              test_abnahme_luecke_je_regel,
              test_abnahme_nennt_nicht_gepruefte_volumenbilanz,
              test_abnahme_t_stoss_nennt_haengende_knoten,
              test_abnahme_doppelte_knoten_relativ_zur_kante,
              test_abnahme_losgeloester_bereich_schraeg_versetzt,
              test_abnahme_t_stoss_mit_geteilter_kante,
              test_abnahme_hohlraum_neben_losgeloestem_bereich,
              test_abnahme_hohlraum_mit_einspringender_kante,
              test_abnahme_duenne_luecke_und_ufer_ohne_gegenueber,
              test_abnahme_netzrand_verfehlt_randflaeche,
              test_abnahme_luecke_abhilfe_bei_gleicher_elementzahl,
              test_abnahme_mulde_mit_einspringender_kante,
              test_abnahme_durchtrennter_koerper_heisst_doppelt,
              test_abnahme_riss_mit_knoten_naeher_als_ein_prozent,
              test_windschiefe_randflaechen_ohne_dreiecksschleife,
              test_abnahme_meldet_ausgefallene_pruefungen,
              test_nicht_messbare_formguete_gilt_nicht_als_beste,
              test_teiltragwerke, test_unvernetzt, test_koerper_ohne_netz_haelt_an,
              test_meldung_nennt_ursache_und_kanten,
              test_abnahme, test_abnahme_an_der_echten_fuge,
              test_schliesstest_mit_oeffnungsringen, test_solver_meldung):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
