"""
Beispielbibliothek (09.11.2026, Freigabe des Anwenders „9 ja“).

* 14 eingebaute Beispiele in drei Gruppen (Stabwerk 6, Flächentragwerk 5,
  Volumen 3), jedes mit Beschreibung und Parametern samt Einheit und Grenzen.
* Mit den Vorgabewerten entsteht dasselbe Modell wie bisher: die acht alten
  Beispiele gleich examples_lib.build_example (Modelldatei ohne meta), die
  sechs Testmodelle gleich den Dateien des Original-Erzeugers (verglichen am
  09.11.2026 mit scratchpad tm_vergleich.py, alle sechs gleich); hier
  stellvertretend Zaehlwerte der Originaldateien.
* Die Werte wirken: Hallenrahmen s_k = 1,0 kN/m², e = 5 m, L = 15 m - die
  Rechnung gibt ΣRz im LF2 = 75,0 kN (Hand: 1,0 · 5 · 15); Hubtor mit 10 m
  Stuetzweite reicht bis x = 10 m und laesst sich vernetzen.
* Grenzen und Querpruefungen: ausserhalb, nicht ganzzahlig, UW >= OW - mit
  Grund, nie still begrenzt.
* Eigene Beispiele aus einem Ordner: eine gute Datei wird geladen und gebaut,
  eine fehlerhafte steht mit Grund und Zeile in der Fehlerliste, ohne die
  anderen zu verhindern.

Aufruf:  python -m tests.test_beispielbibliothek
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _dict(m):
    d = json.loads(json.dumps(m.to_dict(), default=str))
    d.get("meta", {}).pop("beispiel", None)
    return d


def test_verzeichnis():
    from statik3d import beispiele as bib
    alle = bib.eingebaute()
    gruppen = {g: [b.titel for b in alle if b.gruppe == g] for g in bib.GRUPPEN}
    check("14 eingebaute Beispiele: Stabwerk 6, Flächentragwerk 5, Volumen 3",
          len(alle) == 14 and [len(gruppen[g]) for g in bib.GRUPPEN] == [6, 5, 3], str(gruppen))
    schlecht = [b.titel for b in alle if not b.beschreibung or not b.parameter
                or any(not p.einheit and p.name not in ("nf", "felder", "mu") for p in b.parameter)
                or any(not (p.min <= p.wert <= p.max) for p in b.parameter)]
    check("… jedes mit Beschreibung, Parametern mit Einheit, Vorgabe in den Grenzen", not schlecht, str(schlecht))
    check("… Schlüssel eindeutig", len({b.schluessel for b in alle}) == 14)


def test_vorgaben_wie_bisher():
    from statik3d import beispiele as bib
    from statik3d.examples_lib import EXAMPLES, build_example
    abw = [k for k in EXAMPLES if _dict(bib.finden(k).bauen()) != _dict(build_example(k))]
    check("die acht alten Beispiele: mit Vorgabewerten dieselbe Modelldatei", not abw and len(EXAMPLES) == 8,
          str(abw))
    # Zaehlwerte der Dateien des Original-Erzeugers (Desktop\Statik3D\Testmodelle, 09.11.2026)
    soll = {"wippkran": (114, 0, 119), "foerderband": (189, 0, 290), "stemmtor": (288, 304, 0),
            "hubtor": (196, 201, 0), "fischbauchklappe": (44, 51, 0), "spurlager": (16, 14, 0)}
    ist = {}
    for k in soll:
        m = bib.finden(k).bauen()
        ist[k] = (m.nn, len(m.flaechen), len(m.elements))
    check("die sechs Testmodelle: Knoten, Flächen, Elemente wie die Originaldateien", ist == soll, str(ist))
    m = bib.finden("hubtor").bauen()
    check("… im Modell stehen Beispiel und Werte (meta) und die Annahmen",
          m.meta["beispiel"]["schluessel"] == "hubtor" and m.meta["beispiel"]["werte"]["stuetzweite"] == 12.0
          and "alle Werte angenommen" in m.meta.get("annahmen", ""), str(m.meta.get("beispiel")))


def test_werte_wirken():
    from statik3d import beispiele as bib, solver
    m = bib.finden("hall").bauen({"s_k": 1.0, "e": 5.0})
    an = solver.solve_all(m, workers=1, combinations=False)
    Rz = float(np.asarray(an.cases["LF2"].reactions)[:, 2].sum())
    check("Hallenrahmen s_k 1,0 kN/m², e 5 m: ΣRz(LF2) = 75,0 kN (Hand 1,0 · 5 · 15)",
          abs(Rz - 75e3) < 1.0, f"{Rz / 1e3:.3f} kN")
    m = bib.finden("frame").bauen({"L": 8.0, "q": 20.0})
    an = solver.solve_all(m, workers=1, combinations=False)
    r = np.asarray(an.cases[m.active_case].reactions)
    m0 = bib.finden("frame").bauen({"L": 8.0, "q": 0.0})
    r0 = np.asarray(solver.solve_all(m0, workers=1, combinations=False).cases[m0.active_case].reactions)
    dRz = float(r[:, 2].sum() - r0[:, 2].sum())
    check("Rahmen L 8 m, q 20 kN/m: Dachlast in der Lagerkraft 160 kN (Hand 20 · 8)",
          abs(dRz - 160e3) < 1.0 and abs(float(m.nodes[:, 0].max()) - 8.0) < 1e-9, f"{dRz / 1e3:.3f} kN")
    from statik3d import mesher
    m = bib.finden("hubtor").bauen({"stuetzweite": 10.0, "hoehe": 4.0, "ow": 4.0, "uw": 0.0})
    log = []
    mesher.modell_vernetzen(m, log, workers=1)
    lf2 = m.load_cases["LF2"]
    check("Hubtor 10 x 4 m, UW trocken: bis x = 10 m, vernetzt, LF2 „UW trocken“",
          abs(float(m.nodes[:, 0].max()) - 10.0) < 1e-9 and len(m.elements) > 0
          and "UW trocken" in lf2.bezeichnung, f"{len(m.elements)} Elemente, {lf2.bezeichnung}")


def test_grenzen():
    from statik3d import beispiele as bib
    hub = bib.finden("hubtor")
    try:
        hub.bauen({"stuetzweite": 100.0})
        check("Stützweite 100 m (Grenze 40 m): abgewiesen mit Grund", False)
    except ValueError as ex:
        check("Stützweite 100 m (Grenze 40 m): abgewiesen mit Grund",
              "Stützweite" in str(ex) and "außerhalb" in str(ex), str(ex))
    try:
        hub.bauen({"uw": 6.0, "ow": 5.0})
        check("Unterwasser über Oberwasser: abgewiesen", False)
    except ValueError as ex:
        check("Unterwasser über Oberwasser: abgewiesen", "Unterwasser" in str(ex), str(ex))
    try:
        bib.finden("truss").bauen({"nf": 2.5})
        check("Felder 2,5: abgewiesen (ganze Zahl)", False)
    except ValueError as ex:
        check("Felder 2,5: abgewiesen (ganze Zahl)", "ganze Zahl" in str(ex), str(ex))


GUT = '''TITEL = "Mein Kragarm"
GRUPPE = "Stabwerk"
BESCHREIBUNG = "Kragarm IPE 200 mit Endlast"
PARAMETER = [("L", "Länge", 3.0, "m", 0.5, 10.0), ("F", "Endlast", 10.0, "kN", 0.0, 500.0)]


def bauen(werte):
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    m = Model("Kragarm")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (werte["L"], 0, 0), 6)
    m.fix(int(ids[0]), "all")
    m.load_node(int(ids[-1]), Fz=-werte["F"] * 1e3)
    return m
'''

KAPUTT = '''TITEL = "Kaputt"
PARAMETER = [("a", "a", 1.0, "m", 0.0, 2.0)]
x = 1 / 0
def bauen(werte):
    return None
'''


def test_eigene():
    from statik3d import beispiele as bib
    d = tempfile.mkdtemp(prefix="statik3d_beispiele_")
    open(os.path.join(d, "kragarm.py"), "w", encoding="utf-8").write(GUT)
    open(os.path.join(d, "kaputt.py"), "w", encoding="utf-8").write(KAPUTT)
    alle, fehler = bib.alle(d)
    eigene = [b for b in alle if b.eigen]
    check("eigener Ordner: die gute Datei geladen, die fehlerhafte mit Grund und Zeile",
          len(eigene) == 1 and eigene[0].titel == "Mein Kragarm" and len(alle) == 15
          and len(fehler) == 1 and "ZeroDivisionError" in fehler[0][1] and "Zeile 3" in fehler[0][1],
          f"{[b.titel for b in eigene]} {fehler}")
    m = eigene[0].bauen({"L": 4.0})
    check("… das eigene Beispiel baut mit den Werten (L 4 m, F Vorgabe 10 kN)",
          abs(float(m.nodes[:, 0].max()) - 4.0) < 1e-9 and m.meta["beispiel"]["werte"] == {"L": 4.0, "F": 10.0},
          str(m.meta.get("beispiel")))
    ohne, f_ohne = bib.alle(os.path.join(d, "gibt_es_nicht"))
    check("… ohne Ordner: nur die eingebauten, kein Fehler", len(ohne) == 14 and not f_ohne,
          f"{len(ohne)} {f_ohne}")


def main():
    for t in (test_verzeichnis, test_vorgaben_wie_bisher, test_werte_wirken, test_grenzen, test_eigene):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
