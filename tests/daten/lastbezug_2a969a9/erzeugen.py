"""Eine Modelldatei vom Stand **vor** dem Lastbezug (Oberflaechenpaket B, 08.11.2026).

Erzeugt wurde ``alt.modell`` (eine Modelldatei im JSON-Format; die Endung
ist nicht .json, damit tests/test_umstellung_lf_lk sie nicht unter den
Dateien der Fassung 7 und 8 sucht) und ``lastvektor.json`` auf dem Stand 2a969a9
(Integrationsstand 08.11.2026, vor ui/paket-b), im Wurzelverzeichnis eines
Arbeitsbaums auf diesem Commit:

    python tests/daten/lastbezug_2a969a9/erzeugen.py

Das Modell traegt jede Art Flaechen- und Linienlast, die es vor dem Lastbezug
gab: senkrecht auf zwei Platten mit entgegengesetztem Randumlauf (eine mit der
Normalen nach +Z, eine nach -Z - die Ursache von „-5 kN/m² drueckt nach oben“),
mit globaler Richtung, projiziert auf die Oberseite eines Wuerfels, linear
veraenderlich, eine Linienlast auf einer Linie und eine lokale auf einem Stab.
``lastvektor.json`` haelt den Lastvektor des Lastfalls fest (solver.case_loads).

tests/test_paket_b.py laedt die Datei mit dem heutigen Stand und verlangt:
Speichern ergibt dieselbe Datei Zeichen fuer Zeichen, und der Lastvektor ist
derselbe.
"""
import json
import os
import sys

import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(os.path.dirname(os.path.dirname(HIER)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)


def modell():
    from statik3d.model import Model, Material, Section, ShellProp
    from statik3d import mesher
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01, "S235"))
    m.add_section(Section.from_profile("HEB 200"))
    # zwei Platten 2 m x 1 m: P1 im Gegenuhrzeigersinn (Normale +Z), P2 im
    # Uhrzeigersinn (Normale -Z)
    for dx, name, umlauf in ((0.0, "P1", (0, 1, 2, 3)), (3.0, "P2", (0, 3, 2, 1))):
        b = m.nn
        for p in ((0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)):
            m.add_node(p[0] + dx, p[1], p[2])
        linien = []
        for j in range(4):
            ln = f"{name}L{j}"
            m.add_line(ln, [b + umlauf[j], b + umlauf[(j + 1) % 4]])
            linien.append(ln)
        m.add_flaeche(name, linien, material="S235", dicke="D10")
    # Wuerfel 1 m an x = 6 m
    b = m.nn
    for p in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)):
        m.add_node(p[0] + 6.0, p[1], p[2])
    z = {"i": 0}

    def linie(a, c):
        z["i"] += 1
        m.add_line(f"W{z['i']}", [b + a, b + c])
        return f"W{z['i']}"

    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    seiten = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        seiten.append(f"M{i}")
    m.add_koerper("K", ["Boden", "Dach"] + seiten, material="S235")
    # ein Stab
    k0 = m.add_node(0.0, 3.0, 0.0)
    k1 = m.add_node(4.0, 3.0, 0.0)
    e = m.add_element("beam", [k0, k1], "S235", "HEB 200")
    m.add_member("S1", [e])
    m.add_load_case("LF1", "Q", "alle Arten")
    m.add_geometrielast("P1", -5000.0, case="LF1")
    m.add_geometrielast("P2", -5000.0, case="LF1")
    m.add_geometrielast("P1", 1000.0, case="LF1", richtung=[0, 0, -1])
    m.add_geometrielast("Dach", 2000.0, case="LF1", richtung=[0, 0, -1], projiziert=True)
    m.add_geometrielast("M0", 3000.0, case="LF1")
    m.add_geometrielast("P2", 0.0, case="LF1", verlauf={"art": "linear",
                                                         "punkte": [[3, 0, 0, 1000.0], [5, 0, 0, 3000.0]]})
    m.add_linienlast("P1L1", [0.0, 0.0, -4000.0], art="linie", case="LF1")
    m.add_linienlast("S1", [0.0, 0.0, -2000.0], art="stab", system="local", case="LF1")
    mesher.modell_vernetzen(m, log=[])
    return m


def lastvektor(m) -> list:
    from statik3d import solver
    F = np.asarray(solver.case_loads(m, {"LF1": 1.0}, None)[0], float)
    return [float(x) for x in F]


if __name__ == "__main__":
    m = modell()
    m.save(os.path.join(HIER, "alt.modell"))
    with open(os.path.join(HIER, "lastvektor.json"), "w", encoding="utf-8") as f:
        json.dump(lastvektor(m), f)
    print("geschrieben:", len(m.nodes), "Knoten,", len(m.elements), "Elemente")
