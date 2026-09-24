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
    check("  und nennt als Herkunft den Vernetzer, der flache Tetraeder aussortiert",
          "Vernetzer flache Tetraeder aussortiert" in text, text[:420])
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

    # Nebenbefund B050 (22./23.09.2026): fehlt ein Tetraeder, der selbst flach
    # ist (t/L ≤ 5 %, dünn gegen die Nachbarn), blieb es bei der WARNUNG Riss
    # ohne Rückfrage - gleich wie groß der Hohlraum ist. Element 53 dieses
    # Netzes: t/L 4,06 %, 1,752e-6 m³, das 13 250-Fache von FLACH·L³ (L die
    # längste Elementkante des Körpers, 50,9 mm). Die Lücke des Vernetzers
    # daneben hat das 0,87-Fache, die größte der 30 Lücken in den Modellen der
    # Suiten test_mesher3d und test_sweep ebenso (gemessen 23.09.2026).
    def eigen(i):
        P = m.nodes[m.elements[i].nodes]
        V_i = abs(float(np.linalg.det(P[1:] - P[0]))) / 6.0
        A_i = sum(0.5 * np.linalg.norm(np.cross(P[b] - P[a], P[c] - P[a]))
                  for a, b, c in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)))
        L_i = max(np.linalg.norm(P[a] - P[b]) for a in range(4) for b in range(a + 1, 4))
        return V_i, 2.0 * V_i / A_i / L_i

    def kurz(bef):
        return [(b.stufe, b.pruefung, b.wert) for b in bef]
    V53, tl53 = eigen(53)
    k.elemente = [i for i in els if i != 53]
    bef = dg._abnahme_volumenbilanz(m, k.name, k, k.elemente)
    check("  ein fehlender flacher Tetraeder in Elementgröße (t/L 4,1 %, 1,75 cm³): FEHLER, "
          "die Lücke des Vernetzers bleibt ein Riss",
          len(els) == 2701 and abs(V53 - 1.752e-6) < 1e-9 and 0.040 < tl53 < 0.041
          and kurz(bef) == [("FEHLER", "Seiten im Inneren", 4.0), ("WARNUNG", "Riss im Netz", 4.0)],
          f"V {V53:.4g} m³, t/L {tl53 * 100:.2f} %: {kurz(bef)}")
    # Gegenprobe und Grenze: ein flacher Tetraeder so klein wie die, die der
    # Vernetzer aussortiert (Element 2179, 1,454e-10 m³ = 1,10 FLACH·L³),
    # bleibt ein Riss - an dieser Größe ist er von ihnen nicht zu trennen
    V2179, _tl = eigen(2179)
    k.elemente = [i for i in els if i != 2179]
    bef = dg._abnahme_volumenbilanz(m, k.name, k, k.elemente)
    check("  ein fehlender flacher Tetraeder so klein wie die aussortierten bleibt ein Riss",
          abs(V2179 - 1.454e-10) < 1e-12 and kurz(bef) == [("WARNUNG", "Riss im Netz", 8.0)],
          f"V {V2179:.4g} m³: {kurz(bef)}")
    k.elemente = els


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
    # Nebenbefund B049 (22./23.09.2026): die Abhilfe „Sechsflächner sweepen“
    # ist nur an den fünf Prismen gemessen, und ab Werk ist der Sweep aus,
    # weil er am Drehlager 992 entartete Keile erzeugte (Benutzerhandbuch,
    # Netzeinstellungen). Die Meldung empfahl ihn, ohne das zu sagen.
    check("  die Abhilfe Sweep sagt, dass er ab Werk aus ist, warum, und dass danach die "
          "Abnahme zu lesen ist",
          "ab Werk aus" in text and "entartete Keile" in text and "Abnahme lesen" in text,
          text[-520:])
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

    # Nebenbefunde B050/B051 (22./23.09.2026): ein flacher Tetraeder im
    # Inneren desselben Netzes von Hand gelöscht - der flachste unter der
    # Deckelmitte des langen Schenkels, 35 728 mm³, t/L 3,65 %. Das war eine
    # WARNUNG „Riss im Netz 4“ ohne Rückfrage, und der Text nannte als Grund
    # den Vernetzer, der flache Tetraeder aussortiere; der sortiert aber nur
    # V ≤ FLACH·h³ = 1,7 mm³ aus. Ein Hohlraum in Elementgröße ist kein Riss.
    def t_l(i):
        P = m.nodes[m.elements[i].nodes]
        V = abs(float(np.linalg.det(P[1:] - P[0]))) / 6.0
        A = sum(0.5 * np.linalg.norm(np.cross(P[b] - P[a], P[c] - P[a]))
                for a, b, c in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)))
        L = max(np.linalg.norm(P[a] - P[b]) for a in range(4) for b in range(a + 1, 4))
        return 2.0 * V / A / L, V
    innen_l = [i for i in k.elemente
               if 0.1 < m.nodes[m.elements[i].nodes][:, 0].mean() < 0.4
               and 0.3 < m.nodes[m.elements[i].nodes][:, 1].mean() < 1.7
               and 0.12 < m.nodes[m.elements[i].nodes][:, 2].mean() < 0.28]
    flach = min(innen_l, key=lambda i: t_l(i)[0])
    tl_f, V_f = t_l(flach)
    m.elemente_loeschen([flach])
    bef = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung in _NETZ_BEFUNDE
           or b.pruefung == "Lücke im Netzrand"]
    sn = [b for b in bef if b.pruefung == "Seiten im Inneren"]
    check("  flacher Tetraeder in Elementgröße von Hand gelöscht (35 728 mm³): FEHLER mit "
          "Rückfrage, kein Riss",
          abs(V_f - 3.5728e-5) < 1e-8 and 0.036 < tl_f < 0.037
          and [(b.stufe, b.pruefung, b.wert) for b in bef] == [("FEHLER", "Seiten im Inneren", 4.0)]
          and [b.pruefung for b in dg.abnahme(m)] == ["Seiten im Inneren"],
          f"Element {flach}, V {V_f * 1e9:.0f} mm³, t/L {tl_f * 100:.2f} %: "
          + "; ".join(f"{b.stufe} {b.pruefung} {b.wert:.4g}" for b in bef))
    text_sn = sn[0].text if sn else ""
    check("  der Text schreibt die Lücke nicht dem Vernetzer zu und nennt ein fehlendes Element",
          "Vernetzer flache Tetraeder aussortiert" not in text_sn
          and "fehlendes Element" in text_sn and "von Hand gelöscht" in text_sn,
          text_sn[-380:])

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


def main():
    for f in (test_abnahme_findet_verdrehten_sechsflaechner,
              test_abnahme_ohne_fehlalarm_am_freien_netz,
              test_abnahme_luecken_des_vernetzers_sind_risse,
              test_abnahme_offene_gruppen_sind_kein_riss,
              test_abnahme_riss_misst_am_oertlichen_element,
              test_abnahme_riss_an_laenglichen_zellen,
              test_abnahme_windschief_misst_am_oertlichen_element,
              test_abnahme_luecke_im_netzrand,
              test_abnahme_knoten_ueber_kopplung,
              test_abnahme_knoten_in_drei_richtungen,
              test_abnahme_riss_gestapelt,
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
