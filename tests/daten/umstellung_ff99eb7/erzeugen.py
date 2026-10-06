"""Pruefkoerper fuer tests/test_umstellung_lf_lk.py (Paket R2-A2, 06.10.2026):
eine Modelldatei der Fassung 8 samt Ergebnisdatei, geschrieben vom Stand
ff99eb7 (R2-A1) - also **vor** der Umstellung auf LF/LK/EK.

* ``hallenrahmen.json/.ergebnisse`` - der Hallenrahmen (Beispiel hall) mit
  freien Namen und je einem Verweis jeder Art auf Lastfaelle und
  Kombinationen: Lastfaelle LF1, S, W_links, W_rechts, Kran und LF9 (behaelt
  Name und Nummer, die uebrigen zaehlen dahinter weiter); die erzeugten
  Kombinationen GZT1 … GZG72 (mit Fingerabdruck von R2-A1); die Hand-
  kombination K1 (Leiteinwirkung S); die Ermuedungskombination
  „Ermüdung Kran“ (Summe) als Zustand der Ermuedungslast FK; die
  Ergebniskombination „Bemessung GZT“ nach Theorie II. Ordnung - ihre
  Alternativen stehen abgelegt in der Ergebnisdatei (analysis.alternativen,
  theorie2.kombinationen), die Nachweise muessen sie dort finden; die
  Ergebniskombination EK7 (behaelt ihren Namen); eine Verformungsgrenze
  (GZG, je Kombination); eine Stellung mit Lastfaellen und Kombinationen;
  Wind und Wasserdruck auf W_links und S; Berichtseintraege auf Lastfall,
  Kombination und Umhuellende; aktiver Lastfall S. Gerechnet mit
  ``solve_all(design=True, fatigue=True)``.

Erzeugt mit dem Baum von ff99eb7:

    python tests/daten/umstellung_ff99eb7/erzeugen.py <baum ff99eb7> <zielordner>
"""
import os
import sys


def hallenrahmen():
    from statik3d.examples_lib import build_example
    from statik3d.model import Combination, FatigueLoad, Berichtseintrag, Verformungsgrenze
    from statik3d.bridges.positions import Stellung
    from statik3d.wind import Wind
    from statik3d.wasserdruck import Wasserdruck
    from statik3d import mesher
    m = build_example("hall")
    m.name = "Hallenrahmen Umstellung"
    # von den 72 erzeugten Kombinationen acht - die Ergebnisdatei bliebe sonst
    # bei 1,2 MB; erzeugt und unberuehrt sind sie trotzdem
    behalten = {"GZT1", "GZT2", "GZT3", "GZT4", "GZG43", "GZG44", "GZG45", "GZG46"}
    m.combinations = {n: c for n, c in m.combinations.items() if n in behalten}
    ecke = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=6 - 1e-6)[0])
    m.add_load_case("LF9", "Q", "Anprall", activate=False)
    m.load_node(ecke, Fx=5000.0, case="LF9")
    m.add_combination("K1", {"LF1": 1.35, "S": 1.5, "W_links": 0.9}, "ULS", "von Hand", "S")
    m.add_combination("Ermüdung Kran", {"Kran": 1.0}, "FAT", "Kranüberfahrt")
    m.fatigue_loads["FK"] = FatigueLoad("FK", "Ermüdung Kran", None, cycles=2e5)
    m.combinations["Bemessung GZT"] = Combination(
        "Bemessung GZT", {}, "ULS", "Ergebniskombination nach Theorie II. Ordnung", theorie="II",
        alternativen=[{"LF1": 1.35, "S": 1.5}, {"LF1": 1.35, "W_links": 1.5, "S": 0.75},
                      {"LF1": 1.0, "Kran": 1.5}])
    m.combinations["EK7"] = Combination("EK7", {}, "ULS", "aus RFEM",
                                        alternativen=[{"LF1": 1.0}, {"LF1": 1.35, "S": 1.5}])
    m.verformungsgrenzen["Riegel w"] = Verformungsgrenze("Riegel w", "stab", "Riegel", wert=300.0)
    m.stellungen.append(Stellung("S1", 0.0, "geschlossen", faelle=["LF1", "S", "W_links"],
                                 kombinationen=["K1", "Bemessung GZT"]))
    m.winde["W1"] = Wind("W1", lastfall="W_links")
    m.wasserdruecke["WD1"] = Wasserdruck("WD1", lastfall="S", lastfall_dyn="S")
    m.bericht += [
        Berichtseintrag("Bild 1", "case:W_links", "Verschiebung",
                        beschriftung="Lastfall W_links · Verschiebung"),
        Berichtseintrag("Stabkräfte · Kombination K1", "combo:K1", art="tabelle", tabelle="Stabkräfte"),
        Berichtseintrag("Bild 2", "env:Bemessung GZT", "Verschiebung",
                        beschriftung="Umhüllende Bemessung GZT · Verschiebung"),
        Berichtseintrag("Bild 3", "env:ULS", "Verschiebung", beschriftung="Umhüllende GZT · Verschiebung"),
        Berichtseintrag("Bild 4", "combo:GZT3", "Verschiebung", beschriftung="Kombination GZT3 · Verschiebung")]
    m.active_case = "S"
    return m


def main():
    baum, ziel = sys.argv[1], sys.argv[2]
    sys.path.insert(0, baum)
    from statik3d import solver, ergebnisse
    from statik3d.model import FORMAT_VERSION
    os.makedirs(ziel, exist_ok=True)
    m = hallenrahmen()
    an = solver.solve_all(m, design=True, fatigue=True)
    pfad = os.path.join(ziel, "hallenrahmen.json")
    m.save(pfad)
    ergebnisse.schreiben(ergebnisse.pfad_zu(pfad), m, an)
    print(f"Fassung {FORMAT_VERSION}: {len(m.load_cases)} Lastfälle, {len(m.combinations)} Kombinationen, "
          f"Alternativen abgelegt {sorted(an.alternativen)}, Theorie II {sorted(an.theorie2.kombinationen) if an.theorie2 else None}")
    print(an.summary())


if __name__ == "__main__":
    main()
