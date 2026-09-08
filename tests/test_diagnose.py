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


def test_teiltragwerke():
    m, n = _zwei_teile()
    teile = dg.teiltragwerke(m)
    check("zwei Teiltragwerke, je zwei Knoten", len(teile) == 2 and sorted(len(g) for g in teile) == [2, 2])
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


def main():
    for f in (test_teiltragwerke, test_unvernetzt, test_koerper_ohne_netz_haelt_an,
              test_abnahme, test_abnahme_an_der_echten_fuge, test_solver_meldung):
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
