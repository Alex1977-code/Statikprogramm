"""
Netzdichte: Elementgroesse je Objekt aus Dichtestufe, Objektgroesse, kleinster
Kante, Grenzen und Elementdeckel; Teilung der Flaechen; Dreiecknetz.
Aufruf:  python -m tests.test_netzdichte
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Netzeinstellungen  # noqa: E402
from statik3d import netzdichte as nd, mesher  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def close(name, got, want, tol=1e-9, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g} {unit}")


def _rechteck(m, name, lx, ly, z=0.0, x0=0.0):
    ids = [m.add_node(x0, 0, z), m.add_node(x0 + lx, 0, z), m.add_node(x0 + lx, ly, z), m.add_node(x0, ly, z)]
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"{name}L{i}", [ids[a], ids[b]])
    return m.add_flaeche(name, [f"{name}L{i}" for i in range(4)], dicke="t", material="S", teilung=[2, 2])


def _modell():
    m = Model()
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.01))
    return m


def test_groessen():
    m = _modell()
    f = _rechteck(m, "F", 4.0, 2.0)
    close("Objektgröße = Diagonale √(16+4)", nd.objektgroesse(m, f), math.sqrt(20.0))
    close("kleinste Kante 2 m", nd.kleinste_kante(m, f), 2.0)
    close("Fläche 8 m²", nd.flaechenmass(m, f), 8.0)
    n = Netzeinstellungen()
    e = nd.elementlaenge(m, n, f)
    close("mittel: h = D/16", e["h"], math.sqrt(20.0) / 16.0)
    check("Begründung nennt die Stufe", "mittel" in e["grund"], e["grund"])
    n.dichte = "grob"
    close("grob: h = D/8", nd.elementlaenge(m, n, f)["h"], math.sqrt(20.0) / 8.0)
    n.dichte = "fein"
    close("fein: h = D/32", nd.elementlaenge(m, n, f)["h"], math.sqrt(20.0) / 32.0)
    n.dichte = "eigene"
    n.ziellaenge = 0.25
    close("eigene: h = Ziellänge", nd.elementlaenge(m, n, f)["h"], 0.25)
    t = nd.teilung_flaeche(m, n, f)
    check("Teilung 4 m / 0.25 = 16, 2 m / 0.25 = 8", t == (16, 8), str(t))
    close("Elementschätzung A/h² = 128", nd.elementlaenge(m, n, f)["n"], 128.0)
    # kleine Kante: schmale Flaeche 4 x 0.1 - intelligente Anpassung zieht h auf die Kante
    g = _rechteck(m, "G", 4.0, 0.1, z=1.0)
    n = Netzeinstellungen(dichte="mittel", intelligent=True)
    D = math.sqrt(16.0 + 0.01)
    e = nd.elementlaenge(m, n, g)
    close("intelligent: h = kleinste Kante 0.1 (unter D/16 = 0.25)", e["h"], 0.1)
    check("… Begründung nennt die Kante", "kleinste Kante" in e["grund"], e["grund"])
    n.intelligent = False
    close("ohne Anpassung: h = D/16", nd.elementlaenge(m, n, g)["h"], D / 16.0)
    # Grenzen
    n = Netzeinstellungen(dichte="mittel", intelligent=True, h_min=0.2)
    close("h_min hält die Kante nicht unter 0.2", nd.elementlaenge(m, n, g)["h"], 0.2)
    n = Netzeinstellungen(dichte="grob", intelligent=True, h_max=0.3)
    close("h_max deckelt D/8 = 0.5 auf 0.3", nd.elementlaenge(m, n, f)["h"], 0.3)
    n = Netzeinstellungen(dichte="mittel", intelligent=True)
    h0 = D / 16.0
    close("Vorgabe h_min = h/4 greift bei winziger Kante", nd.elementlaenge(m, n, _rechteck(m, "H", 4.0, 0.001, z=2.0))["h"],
          math.sqrt(16.0 + 1e-6) / 16.0 / 4.0)
    # Deckel Elementzahl
    n = Netzeinstellungen(dichte="eigene", ziellaenge=0.01, intelligent=False, max_elemente=1000)
    e = nd.elementlaenge(m, n, f)
    close("max_elemente: h = √(A/N) = √(8/1000)", e["h"], math.sqrt(8.0 / 1000.0))
    check("… Begründung nennt den Deckel", "begrenzt" in e["grund"] and abs(e["n"] - 1000) < 1e-9)


def test_volumen():
    m = _modell()
    # Quader 2 x 1 x 0.5 aus sechs Flaechen
    P = [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0), (0, 0, .5), (2, 0, .5), (2, 1, .5), (0, 1, .5)]
    ids = [m.add_node(*p) for p in P]
    kanten = {}

    def linie(a, b):
        key = (min(a, b), max(a, b))
        if key not in kanten:
            kanten[key] = f"K{len(kanten)}"
            m.add_line(kanten[key], [ids[a], ids[b]])
        return kanten[key]
    seiten = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    fl = []
    for i, s in enumerate(seiten):
        ln = [linie(s[j], s[(j + 1) % 4]) for j in range(4)]
        fl.append(m.add_flaeche(f"S{i}", ln, dicke="t", material="S", teilung=[2, 2]).name)
    k = m.add_koerper("Q", fl, material="S") if hasattr(m, "add_koerper") else None
    if k is None:
        from statik3d.model import Volumenkoerper
        k = Volumenkoerper("Q", fl, "S")
        m.koerper["Q"] = k
    close("Rauminhalt 2·1·0,5 = 1 m³", nd.volumenmass(m, k), 1.0, 1e-9)
    close("Objektgröße Diagonale", nd.objektgroesse(m, k), math.sqrt(4 + 1 + 0.25))
    close("kleinste Kante 0,5 m", nd.kleinste_kante(m, k), 0.5)
    n = Netzeinstellungen(dichte="eigene", ziellaenge=0.1, intelligent=False)
    e = nd.elementlaenge(m, n, k)
    close("Tetraeder-Schätzung V/(0,12·h³)", e["n"], 1.0 / (0.12 * 0.001))
    n = Netzeinstellungen(dichte="eigene", ziellaenge=0.01, intelligent=False, max_elemente=5000)
    e = nd.elementlaenge(m, n, k)
    close("Deckel: h = (V/(0,12·N))^(1/3)", e["h"], (1.0 / (0.12 * 5000)) ** (1 / 3))
    v = nd.vorschau(m, n)
    check("Vorschau: 6 Flächen, 1 Volumen, Summen", v["flaechen"] == 6 and v["koerper"] == 1 and v["n_koerper"] == 5000
          and v["n"] == v["n_flaechen"] + v["n_koerper"] and len(v["zeilen"]) == 7, str((v["n_flaechen"], v["n_koerper"])))
    log = []
    n = Netzeinstellungen(dichte="eigene", ziellaenge=0.25, intelligent=False)
    hs = nd.anwenden(m, n, [m.flaechen["S0"]], [k], log)
    check("anwenden: Teilung der Fläche 2 m/0,25 × 1 m/0,25 = 8 × 4, h für das Volumen",
          m.flaechen["S0"].teilung == [8, 4] and abs(hs["Q"] - 0.25) < 1e-12 and len(log) == 2, str((m.flaechen["S0"].teilung, log)))
    n.teilung_uebersteuern = False
    m.flaechen["S0"].teilung = [3, 3]
    nd.anwenden(m, n, [m.flaechen["S0"]], [], None)
    check("ohne Übersteuern bleibt die eigene Teilung", m.flaechen["S0"].teilung == [3, 3])


def test_dreiecke_und_persistenz():
    m = _modell()
    f = _rechteck(m, "F", 2.0, 1.0)
    f.teilung = [4, 2]
    log = []
    els = mesher.mesh_flaeche(m, f, log, dreiecke=True)
    check("Dreiecknetz: 2·4·2 = 16 Dreiecke", len(els) == 16 and all(m.elements[e].typ == "shell3" for e in els)
          and "Dreieckelemente" in log[-1], log[-1:])
    m.netz.form = 0
    g = _rechteck(m, "G", 2.0, 1.0, z=1.0)
    g.teilung = [2, 2]
    els = mesher.mesh_flaeche(m, g, log)
    check("form = 0 in den Netzeinstellungen → Dreiecke", len(els) == 8 and all(m.elements[e].typ == "shell3" for e in els))
    m.netz.form = 2
    h = _rechteck(m, "H", 2.0, 1.0, z=2.0)
    h.teilung = [2, 2]
    els = mesher.mesh_flaeche(m, h, log)
    check("form = 2 → Vierecke", len(els) == 4 and all(m.elements[e].typ == "shell4" for e in els))
    m.netz.dichte = "fein"
    m.netz.h_min = 0.02
    m.netz.max_elemente = 12345
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Netzeinstellungen mit Dichte, Grenzen und Deckel gespeichert",
          m2.netz.dichte == "fein" and m2.netz.h_min == 0.02 and m2.netz.max_elemente == 12345 and m2.netz.intelligent)
    alt = {"ziellaenge": 0.3, "form": 1}
    from statik3d.model import _dc
    n = _dc(Netzeinstellungen, alt)
    check("alte Datei ohne die neuen Felder lädt mit Vorgaben", n.dichte == "mittel" and n.intelligent and n.ziellaenge == 0.3)
    check("Beschreibung nennt Dichte und Form", "mittel" in Netzeinstellungen().beschreibung()
          and "Vierecke" in Netzeinstellungen().beschreibung(), Netzeinstellungen().beschreibung())


def main():
    for f in (test_groessen, test_volumen, test_dreiecke_und_persistenz):
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
