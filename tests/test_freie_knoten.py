"""Freie Knoten in der Abnahme: gestuft nach dem, was an ihnen haengt (16.10.2026).

Anlass: Die Netzabnahme am Drehlager-Modell meldete "FEHLER: [Knoten ohne
Element] 67 Knoten im Rechennetz haengen an keinem Element". Gemessen am Modell:
Es sind RFEM-Geometriepunkte (Kreismittelpunkte und Kreispunkte der Stirnflaechen,
Enden dreier Linien, integrierte Knoten von rund 40 Flaechen); an keinem haengt
eine Last, ein Lager, eine Kopplung oder ein Stab. Die Entscheidung des Anwenders:

* mit Last          -> das Ergebnis ist "nicht gueltig" (FEHLER in der Abnahme);
* mit Lager         -> WARNUNG "Lager unwirksam";
* ohne beides       -> Information; die Geometrie bleibt unveraendert, der
  Knoten geht nicht in die Rechnung ein. Wirklich geloescht wird beim
  Vernetzen nur ein Knoten, auf den nichts verweist - auch keine Geometrie.

Aufruf:  python -m tests.test_freie_knoten
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import diagnose as dg                                # noqa: E402
from statik3d import mesher, solver                                # noqa: E402
from statik3d.model import Flaeche, Line, Material, Model          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def wuerfel() -> Model:
    """Würfel 1 x 1 x 1 m aus 2 x 2 x 2 hex8, unten gelagert, oben Druck von 10 kN."""
    m = Model("freie Knoten")
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 1.0, 1.0, 1.0, 2, 2, 2, typ="hex8")
    for kn in ids[:, :, 0].ravel():
        m.fix(int(kn), "all")
    m.load_node(int(ids[1, 1, 2]), Fz=-10e3)
    m.case()
    return m


def befunde(m, name="Knoten ohne Element", stufe=None, warnungen=True):
    return [b for b in dg.abnahme(m, warnungen=warnungen)
            if b.pruefung == name and (stufe is None or b.stufe == stufe)]


def test_last_auf_freiem_knoten():
    print("\n--- Last auf einem freien Knoten: nicht gueltig ---")
    m = wuerfel()
    k = int(m.add_node(3.0, 3.0, 0.0))
    m.load_node(k, Fx=5e3, Fz=-7e3)
    # Abnahme: FEHLER mit Last im Text, schon ohne warnungen=True sichtbar
    b = befunde(m, stufe="FEHLER", warnungen=False)
    check("Abnahme: FEHLER 'Knoten ohne Element' mit dem Knoten", len(b) == 1 and k in b[0].knoten,
          b[0].text[:90] if b else "kein Befund")
    check("Abnahme: der Text nennt die Last und 'nicht gültig'",
          bool(b) and "Last" in b[0].text and "nicht gültig" in b[0].text, b[0].text[:140] if b else "")
    # Rechnung: die lokale Lastpruefung (auto_gehalten) erkennt es, das Ergebnis ist nicht gueltig
    r = solver.solve_static(m, case="LF1")
    text = solver.gueltigkeit(r.info)
    ag = list((r.info or {}).get("auto_gehalten") or [])
    check("Rechnung: Ergebnis 'NICHT gültig' durch die Last am freien Knoten",
          text.startswith("NICHT gültig"), text[:100])
    check("Rechnung: auto_gehalten nennt Knoten und Richtungen der Last",
          {int(x["knoten"]) for x in ag} == {k} and {int(x["fhg"]) for x in ag} == {0, 2},
          str([(x["knoten"], x["fhg"], round(float(x["last"]))) for x in ag]))
    # Moment und Zwangsverformung zaehlen ebenso als Last
    m2 = wuerfel()
    k2 = int(m2.add_node(3.0, 3.0, 0.0))
    m2.load_node(k2, My=100.0)
    check("Moment auf dem freien Knoten: FEHLER in der Abnahme",
          len(befunde(m2, stufe="FEHLER", warnungen=False)) == 1)
    # Last und Lager am selben Knoten: die Last entscheidet
    m3 = wuerfel()
    k3 = int(m3.add_node(3.0, 3.0, 0.0))
    m3.load_node(k3, Fz=-1e3)
    m3.fix(k3, "all")
    check("Last und Lager am freien Knoten: FEHLER (Last zuerst), kein 'Lager unwirksam' allein",
          len(befunde(m3, stufe="FEHLER", warnungen=False)) == 1
          and not [x for x in befunde(m3, "Lager unwirksam")
                   if k3 in x.knoten])


def test_lager_auf_freiem_knoten():
    print("\n--- Lager auf einem freien Knoten: Warnung 'Lager unwirksam' ---")
    m = wuerfel()
    k = int(m.add_node(3.0, 3.0, 0.0))
    m.fix(k, "all")
    ohne = dg.abnahme(m)
    check("ohne warnungen=True hält das Lager nichts an", not ohne, str([b.pruefung for b in ohne]))
    w = befunde(m, "Lager unwirksam", stufe="WARNUNG")
    check("Abnahme: WARNUNG 'Lager unwirksam' mit dem Knoten", len(w) == 1 and k in w[0].knoten,
          w[0].text[:100] if w else "kein Befund")
    check("kein FEHLER 'Knoten ohne Element' für ihn", not befunde(m, stufe="FEHLER"))
    check("auch keine zweite Information für denselben Knoten",
          not [x for x in befunde(m, stufe="INFORMATION") if k in x.knoten])
    r = solver.solve_static(m, case="LF1")
    check("Rechnung: das Ergebnis bleibt gültig (das Lager hält nichts, die Last geht ins Netz)",
          solver.gueltigkeit(r.info) == "", solver.gueltigkeit(r.info)[:80])


def test_nichts_am_freien_knoten():
    print("\n--- Weder Last noch Lager: Information ---")
    m = wuerfel()
    k = int(m.add_node(3.0, 3.0, 0.0))
    check("die Abnahme ohne warnungen=True bleibt leer", not dg.abnahme(m))
    i = befunde(m, stufe="INFORMATION")
    check("Abnahme: INFORMATION mit dem Knoten und der Zahl", len(i) == 1 and k in i[0].knoten
          and abs(i[0].wert - 1.0) < 1e-12, i[0].text[:110] if i else "kein Befund")
    check("kein FEHLER und keine WARNUNG", not befunde(m, stufe="FEHLER")
          and not befunde(m, stufe="WARNUNG") and not befunde(m, "Lager unwirksam"))
    check("der Text sagt, dass der Knoten nicht in die Rechnung eingeht",
          bool(i) and "nicht" in i[0].text and "Rechnung" in i[0].text, i[0].text[:160] if i else "")
    r = solver.solve_static(m, case="LF1")
    check("Rechnung: gültig", solver.gueltigkeit(r.info) == "")


def test_geometriepunkte_bleiben():
    print("\n--- Geometriepunkte bleiben im Modell ---")
    m = wuerfel()
    a, b, c = (int(m.add_node(x, 3.0, 0.0)) for x in (3.0, 3.5, 4.0))
    nur = int(m.add_node(5.0, 5.0, 0.0))                      # nichts verweist darauf
    m.lines["L900"] = Line("L900", nodes=[a, b])
    m.flaechen["F900"] = Flaeche("F900", linien=["L900"], integrierte_knoten=[c])
    nn0, ne0 = int(m.nn), len(m.elements)
    i = befunde(m, stufe="INFORMATION")
    check("Geometriepunkte und der lose Punkt: eine Information mit allen vier",
          len(i) == 1 and abs(i[0].wert - 4.0) < 1e-12, i[0].text[:120] if i else "kein Befund")
    check("der Text trennt Geometriepunkte (3) und Knoten ohne Verweis (1)",
          bool(i) and "Geometrie" in i[0].text, i[0].text[:200] if i else "")
    check("die Abnahme ohne Warnungen bleibt leer", not dg.abnahme(m))
    check("check(): kein 'Knoten ohne Elementanschluss' für Geometriepunkte allein",
          not [z for z in m.check() if "Elementanschluss" in z and "4 Knoten" in z]
          and not [z for z in m.check() if "Elementanschluss" in z and "3 Knoten" in z],
          str([z for z in m.check() if "Elementanschluss" in z]))
    # Vernetzen: geloescht wird nur, worauf nichts verweist
    weg = m.netzknoten_loeschen()
    check("netzknoten_loeschen entfernt nur den Knoten ohne jeden Verweis", weg == 1 and m.nn == nn0 - 1,
          f"weg {weg}, nn {m.nn} von {nn0}")
    check("Linie L900 und die Fläche zeigen weiter auf ihre (nummerierten) Punkte",
          len(m.lines["L900"].nodes) == 2
          and all(0 <= n < m.nn for n in m.lines["L900"].nodes)
          and all(0 <= n < m.nn for n in m.flaechen["F900"].integrierte_knoten)
          and np.allclose(m.nodes[m.lines["L900"].nodes[0]], [3.0, 3.0, 0.0])
          and np.allclose(m.nodes[m.flaechen["F900"].integrierte_knoten[0]], [4.0, 3.0, 0.0]))
    # Speichern, Laden: dasselbe Netz, dieselbe Geometrie
    with tempfile.TemporaryDirectory() as d:
        pf = os.path.join(d, "m.json")
        m.save(pf)
        m2 = Model.load(pf)
    check("Speichern und Laden: gleiche Knoten- und Elementzahl, Linie und Fläche unverändert",
          m2.nn == m.nn and len(m2.elements) == len(m.elements)
          and m2.lines["L900"].nodes == m.lines["L900"].nodes
          and m2.flaechen["F900"].integrierte_knoten == m.flaechen["F900"].integrierte_knoten)
    i2 = [x for x in dg.abnahme(m2, warnungen=True)
          if x.pruefung == "Knoten ohne Element" and x.stufe == "INFORMATION"]
    check("nach dem Laden dieselbe Information (3 Geometriepunkte)",
          len(i2) == 1 and abs(i2[0].wert - 3.0) < 1e-12)


def test_neuvernetzen_entfernt_alte_netzknoten():
    print("\n--- Neu vernetzen: alte Netzknoten ohne Verweis gehen, Geometrie bleibt ---")
    m = wuerfel()
    a = int(m.add_node(3.0, 3.0, 0.0))
    m.lines["L901"] = Line("L901", nodes=[a, a])
    alte = list(range(int(m.nn)))
    # alte Elemente weg (wie beim Neuvernetzen), dann die Knoten des alten Netzes
    m.elemente_loeschen(list(range(len(m.elements))))
    weg = m.netzknoten_loeschen(alte + [a])
    verbleibend = {tuple(np.round(x, 6)) for x in m.nodes}
    check("Der Geometriepunkt bleibt, das alte Netz (ohne Last, Lager) ist weg",
          (3.0, 3.0, 0.0) in verbleibend and weg >= 1, f"weg {weg}, nn {m.nn}")
    check("die Linie zeigt noch auf ihn", all(0 <= n < m.nn for n in m.lines["L901"].nodes)
          and np.allclose(m.nodes[m.lines["L901"].nodes[0]], [3.0, 3.0, 0.0]))


def test_check_zaehlt_nur_tragende_rollen():
    print("\n--- Model.check(): Warnung nur, wo etwas an dem Knoten haengt ---")
    m = wuerfel()
    k = int(m.add_node(3.0, 3.0, 0.0))
    m.load_node(k, Fz=-1.0)
    check("Last auf freiem Knoten: check() warnt weiterhin",
          any("Knoten ohne Elementanschluss" in z for z in m.check()))


def main():
    test_last_auf_freiem_knoten()
    test_lager_auf_freiem_knoten()
    test_nichts_am_freien_knoten()
    test_geometriepunkte_bleiben()
    test_neuvernetzen_entfernt_alte_netzknoten()
    test_check_zaehlt_nur_tragende_rollen()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
