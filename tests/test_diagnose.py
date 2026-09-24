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

    NEU = ("Volumenbilanz", "Seiten im Inneren", "Netzrand neben der Hülle")
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
    neu3 = [b for b in dg.abnahme(m3, warnungen=True) if b.pruefung in NEU]
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


_NETZ_BEFUNDE = ("Volumenbilanz", "Seiten im Inneren", "Netzrand neben der Hülle",
                 "Riss im Netz")


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
    for dz, h in ((0.5, 0.25), (1.0, 0.5)):
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
            # Tetraeder nur bis zu seiner Sehne: gemessen 2,892e-4 gegen
            # 2,841e-4 m^3 (1,8 % mehr)
            check("  und ein fehlender Tetraeder am windschiefen Deckel wird als Lücke gemeldet",
                  len(lu) == 1 and lu[0].stufe == "WARNUNG"
                  and V_weg <= lu[0].wert < 1.05 * V_weg
                  and not [b for b in bef if b.pruefung == "Riss im Netz"],
                  f"Element {weg} ({V_weg:.4g} m³): "
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
            # Element 765 ist kleiner als seine Nachbarn: sein Hohlraum ist
            # 0,62-mal so dick wie sie (unter ABNAHME_RISS_NACHBAR), aber nicht
            # flach, t/L 6,17 %. Nur t/L macht ihn zum FEHLER (gemessen
            # 23.09.2026; am freien Wuerfel 9 solche von 541 inneren Tetraedern)
            P = m.nodes[m.elements[765].nodes]
            V_t = abs(float(np.linalg.det(P[1:] - P[0]))) / 6.0
            A_t = sum(0.5 * np.linalg.norm(np.cross(P[b] - P[a], P[c] - P[a]))
                      for a, b, c in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)))
            L_t = max(np.linalg.norm(P[a] - P[b]) for a in range(4) for b in range(a + 1, 4))
            k.elemente = [i for i in els if i != 765]
            bef = dg._abnahme_volumenbilanz(m, "K", k, k.elemente)
            check("  ein fehlender kleiner Tetraeder, der nicht flach ist (t/L 6,2 %): FEHLER",
                  len(els) == 1483 and 0.06 < 2 * V_t / A_t / L_t < 0.065
                  and [(b.stufe, b.pruefung, b.wert) for b in bef]
                  == [("FEHLER", "Seiten im Inneren", 4.0)],
                  f"{len(els)} tet4, t/L {2 * V_t / A_t / L_t * 100:.2f} %: "
                  + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef))
            k.elemente = els

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


def test_abnahme_luecken_des_vernetzers_sind_risse():
    """Der freie Vernetzer sortiert Tetraeder mit V <= FLACH·h³ aus, und ihre
    Lücken bleiben im Netz. Die Abnahme meldete sie als „FEHLER Seiten im
    Inneren" (Gegenprüfung vom 23.09.2026, M1 b: Platte mit Bohrung 8
    Seiten, Keile am feinen Rand 4) - vor jeder Rechnung die Rückfrage
    „Trotzdem rechnen?", und neu vernetzen ergibt dasselbe Netz. Gemeint war
    die WARNUNG „Riss im Netz"; der alte Risstest verlangte aber Ebenheit auf
    1 % des Seitendurchmessers, die Lücken sind 1,7 bis 11 % dick.

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
    els = [int(i) for i in k.elemente]
    bef = dg._abnahme_volumenbilanz(m, k.name, k, els)
    ri = [b for b in bef if b.pruefung == "Riss im Netz"]
    check("Keile am feinen Rand, frei vernetzt: die Lücke ist eine WARNUNG Riss",
          len(ri) == 1 and ri[0].stufe == "WARNUNG" and ri[0].wert == 4.0
          and not [b for b in bef if b.stufe == "FEHLER"],
          f"{len(els)} tet4; " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.0f}" for b in bef))
    # Zweite Gegenpruefung, Mangel 3: der Text sagte „Neu vernetzen mit
    # denselben Einstellungen ergibt dasselbe Netz" ohne Einschraenkung - an
    # einem von Hand geaenderten Netz hilft neu vernetzen aber
    text = ri[0].text if ri else ""
    check("  der Text rät zu neu vernetzen nur bei importierten oder von Hand geänderten Netzen",
          "von Hand geändert" in text and "dasselbe Netz" in text
          and "Neu vernetzen mit denselben Einstellungen ergibt dasselbe Netz" not in text,
          text[-300:])
    # Gegenprobe: fehlt ein Tetraeder, der nicht flach ist, ist es kein Riss -
    # die Regel winkt nicht jeden Hohlraum durch. Die Platte ist eine
    # Tetraederlage dick: der fehlende Tetraeder hinterlaesst eine Delle in
    # der Plattenflaeche (drei Seiten, offen zur Randflaeche). Das ist eine
    # Luecke im Netzrand mit dem Volumen des Tetraeders (Mangel 3 der
    # Gegenpruefung vom 23.09.2026: WARNUNG unter der Grenze der Volumenbilanz).
    V = dg.elementvolumina(m, els)
    mittel = [i for j, i in enumerate(els)
              if V[j] > 0.5 * float(np.median(V))
              and all(0.3 < c < 0.7 for c in m.nodes[m.elements[i].nodes].mean(axis=0)[:2]
                      / np.array([0.2, 0.1]))]
    V_weg = float(V[els.index(mittel[0])])
    k.elemente = [i for i in els if i != mittel[0]]
    bef = dg._abnahme_volumenbilanz(m, k.name, k, k.elemente)
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    # (die Luecke der Keile bleibt daneben der Riss mit 4 Seiten)
    check("  ein fehlender Tetraeder mittlerer Größe (Delle) ist eine Lücke, kein Riss",
          len(lu) == 1 and abs(lu[0].wert - V_weg) < 1e-3 * V_weg
          and [b.wert for b in bef if b.pruefung == "Riss im Netz"] == [4.0]
          and not [b for b in bef if b.pruefung == "Seiten im Inneren"],
          f"Element {mittel[0]} ({V_weg:.4g} m³): "
          + ("; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef) or "kein Befund"))


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


def test_abnahme_riss_an_laenglichen_zellen():
    """Zweite Gegenprüfung vom 23.09.2026, Mängel 1 und 2: die Riss-Regel der
    zweiten Kur maß die Dicke eines Hohlraums nur an der längsten Kante
    seiner Seiten (t/L ≤ 5 %). In länglichen Zellen folgt die Dicke der
    kurzen Seite, L der langen - ein verdrehter Sechsflächner in einer Zelle
    100 × 100 × 200 mm wurde so zur WARNUNG „Riss im Netz … Der Körper
    stimmt", ohne Rückfrage vor dem Rechnen (t/L 4,37 %; bei 46af735 und
    3f5ae87 FEHLER). Abgestuft 50:1 gingen von je 512 inneren Zellen 357
    verdrehte, 72 fehlende Sechsflächner und 340 fehlende Kuhn-Tetraeder als
    Riss durch. Und ein Sechsflächner, der an den vier Knoten einer Seite
    losgelöst ist (doppelte Knoten), umschließt mit den Nachbarn einen
    Hohlraum ohne Volumen: WARNUNG „Riss im Netz 10".

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
        bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
               or b.pruefung == "Lücke im Netzrand"]
        ergebnisse.append((len(k.elemente), bef, dg.abnahme(m)))
    n_el, bef, fehler = ergebnisse[0]
    lu = [b for b in bef if b.pruefung == "Lücke im Netzrand"]
    check("L-Prisma h = 0,25, Standardweg: eine WARNUNG „Lücke im Netzrand“, kein FEHLER",
          n_el == 821 and len(bef) == 1 and len(lu) == 1 and lu[0].stufe == "WARNUNG"
          and not fehler,
          f"{n_el} Elemente; " + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef)
          + " | FEHLER: " + "; ".join(b.pruefung for b in fehler))
    text = lu[0].text if lu else ""
    check("  mit Volumen, Ort und einer Abhilfe, die nicht „neu vernetzen“ heißt",
          bool(lu) and abs(lu[0].wert - 5.5155e-4) < 2e-7 and "0.921" in text
          and "0.412" in text and "dasselbe Netz" in text and "sweepen" in text,
          text[:400])
    check("  neu vernetzen ergibt dasselbe Netz und denselben Befund",
          ergebnisse[1][0] == n_el and [(b.pruefung, round(b.wert, 9)) for b in ergebnisse[1][1]]
          == [(b.pruefung, round(b.wert, 9)) for b in bef],
          f"{ergebnisse[1][0]} Elemente")

    # Zweite Gegenpruefung, Mangel 4: an einem von Hand geaenderten Netz hilft
    # neu vernetzen. Richtiges freies Netz (h = 0,12), ein Tetraeder mit einer
    # Seite im Deckel geloescht wie mit „Elemente löschen" in der Oberflaeche
    # (Model.elemente_loeschen): eine Luecke. Der Text sagte „Neu vernetzen
    # mit denselben Einstellungen ergibt dasselbe Netz" ohne Einschraenkung.
    check("  der Text nennt neu vernetzen für importierte oder von Hand geänderte Netze",
          "von Hand geändert" in text and "Neu vernetzen mit denselben" not in text, text[-420:])
    m = Model("L")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, L, 0.0, 0.4)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.12})
    n_frei = len(k.elemente)
    vorher = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
              or b.pruefung == "Lücke im Netzrand"]
    deckel = [i for i in k.elemente
              if (np.abs(m.nodes[m.elements[i].nodes][:, 2] - 0.4) < 1e-9).sum() == 3
              and 0.1 < m.nodes[m.elements[i].nodes][:, 0].mean() < 0.4
              and 0.8 < m.nodes[m.elements[i].nodes][:, 1].mean() < 1.6]
    m.elemente_loeschen(deckel[:1])
    lu = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Lücke im Netzrand"]
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.12})
    nachher = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
               or b.pruefung == "Lücke im Netzrand"]
    check("  von Hand gelöschtes Element: Lücke, und neu vernetzen stellt das Netz wieder her",
          n_frei == 6173 and not vorher and len(lu) == 1 and "von Hand geändert" in lu[0].text
          and len(k.elemente) == n_frei and not nachher,
          f"{n_frei} tet4, vorher {len(vorher)} Befunde, Lücke {[round(b.wert, 7) for b in lu]}, "
          f"neu vernetzt {len(k.elemente)} tet4, {len(nachher)} Befunde")

    # T-Prisma, h = 0,1: die Luecke liegt an der einspringenden Kante
    # (1,2 | 0,4). Zwei Seiten liegen im Inneren, zwei stehen in die
    # Aussparung hinaus (bis 29,2 mm) - erst mit ihnen liegt der Rand der
    # Gruppe auf der Huelle. Es fehlen 2,43e-5 m^3 (Bilanz 1,17e-5 m^3).
    T = [(0, 0), (2, 0), (2, 0.4), (1.2, 0.4), (1.2, 1.5), (0.8, 1.5), (0.8, 0.4), (0, 0.4)]
    m = Model("T")
    m.add_material(Material.steel("S235"))
    k = _extrudiert(m, T, 0.0, 0.3)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.1})
    bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
           or b.pruefung == "Lücke im Netzrand"]
    check("T-Prisma h = 0,1, Standardweg: Lücke an der einspringenden Kante, kein FEHLER",
          len(k.elemente) == 5997 and len(bef) == 1 and bef[0].pruefung == "Lücke im Netzrand"
          and bef[0].stufe == "WARNUNG" and abs(bef[0].wert - 2.434e-5) < 1e-8,
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
        with contextlib.redirect_stdout(io.StringIO()):
            mesher.modell_vernetzen(m, [], workers=1, hs={"K": 0.2})
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
    # der kuerzesten Kante), ohne Kopie einer Seite - bleibt „Netzrand"
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
    with contextlib.redirect_stdout(io.StringIO()):
        k.elemente = [int(e) for e in M3.mesh_koerper_frei(m, k, log=[])]
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
    for f in (test_abnahme_findet_verdrehten_sechsflaechner,
              test_abnahme_ohne_fehlalarm_am_freien_netz,
              test_abnahme_luecken_des_vernetzers_sind_risse,
              test_abnahme_offene_gruppen_sind_kein_riss,
              test_abnahme_riss_misst_am_oertlichen_element,
              test_abnahme_riss_an_laenglichen_zellen,
              test_abnahme_windschief_misst_am_oertlichen_element,
              test_abnahme_luecke_im_netzrand,
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
