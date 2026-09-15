"""Verschieben, Drehen, Spiegeln und Kopieren (statik3d/transformieren.py).

Wunsch vom 15.09.2026: „per Rechtsklick auf einen Knoten, Linie, Stab,
Fläche, Volumen verschieben, kopieren, spiegeln, drehen". Geprueft werden die
Abbildungen, die Huelle der Auswahl (Volumen -> Flaechen -> Linien -> Knoten,
Kreisgeometrie), das Netz (bleibt beim Verschieben, faellt beim Spiegeln)
und das Kopieren mit fortlaufenden Namen.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import transformieren as tr                     # noqa: E402
from statik3d.model import Material, Model, ShellProp          # noqa: E402
from statik3d.profiles import make_section                     # noqa: E402
from tests.test_fugen import zwei_bloecke                      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:64s} {detail}")
    return bool(ok)


def _rahmen() -> Model:
    """Ein Rechteck aus vier Linien als Flaeche, ein Kreis, ein Stab aus zwei
    Elementen (Knoten 4-6) - nichts davon vernetzt."""
    m = Model("T")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("d10", 0.01))
    m.add_section(make_section("IPE 200"))
    m.add_nodes([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0], [5, 0, 0], [5, 0, 1], [5, 0, 2]])
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="d10", material="S235")
    m.add_line("K1", typ="circle", mitte=(1.0, 0.5, 0.0), radius=0.25, normale=(0, 0, 1))
    e1 = m.add_element("beam", [4, 5], "S235", "IPE 200")
    e2 = m.add_element("beam", [5, 6], "S235", "IPE 200")
    m.add_member("S1", [e1, e2])
    return m


def _nah(a, b, tol=1e-9) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol))


def test_abbildungen():
    R, t = tr.drehung((0, 0, 0), (0, 0, 1), 90.0)
    check("Drehung 90° um z durch den Ursprung: (1,0,0) → (0,1,0)", _nah(R @ [1, 0, 0] + t, [0, 1, 0]))
    R, t = tr.drehung((1, 0, 0), (0, 0, 1), 180.0)
    check("Drehung 180° um z durch (1,0,0): (2,0,0) → (0,0,0)", _nah(R @ [2, 0, 0] + t, [0, 0, 0]))
    check("… eine Drehung ist keine Spiegelung", not tr.ist_spiegelung(R))
    R, t = tr.spiegelung((0, 0, 1), (0, 0, 1))
    check("Spiegelung an z = 1: (0,0,3) → (0,0,-1), det R = -1",
          _nah(R @ [0, 0, 3] + t, [0, 0, -1]) and tr.ist_spiegelung(R))
    R, t = tr.verketten(*tr.verschiebung((1, 0, 0)), 3)
    check("dreimal verschoben: t = (3,0,0)", _nah(t, [3, 0, 0]) and _nah(R, np.eye(3)))
    R, t = tr.verketten(*tr.drehung((0, 0, 0), (0, 0, 1), 90.0), 2)
    check("zweimal 90° = 180°", _nah(R @ [1, 0, 0] + t, [-1, 0, 0]))


def test_verschieben():
    m = _rahmen()
    vor = m.nodes.copy()
    log = []
    erg = tr.anwenden(m, tr.Auswahl(flaechen=["F1"], linien=["K1"]), *tr.verschiebung((0, 0, 2)), log=log)
    check("Fläche und Kreis verschoben: die vier Randknoten wandern, der Stab nicht",
          erg["knoten"] == 4 and _nah(m.nodes[:4, 2], [2, 2, 2, 2]) and _nah(m.nodes[4:], vor[4:]),
          str(m.nodes[:, 2]))
    check("der Kreis nimmt seinen Mittelpunkt mit", _nah(m.lines["K1"].geometrie["mitte"], [1.0, 0.5, 2.0]),
          str(m.lines["K1"].geometrie))
    check("Protokoll", log and "Knoten" in log[0], str(log))
    erg = tr.anwenden(m, tr.Auswahl(staebe=["S1"]), *tr.drehung((0, 0, 0), (0, 0, 1), 90.0))
    check("Stab um z gedreht: Knoten 4 (5,0,0) → (0,5,0), Knoten 6 (5,0,2) → (0,5,2)",
          erg["knoten"] == 3 and _nah(m.nodes[4], [0, 5, 0]) and _nah(m.nodes[6], [0, 5, 2]), str(m.nodes[4:]))
    erg = tr.anwenden(m, tr.Auswahl(knoten=[0]), *tr.verschiebung((0, 0, -1)))
    check("ein einzelner Knoten", erg["knoten"] == 1 and _nah(m.nodes[0], [0, 0, 1]) and _nah(m.nodes[1], [2, 0, 2]))
    check("Stabelemente bleiben beim Verschieben und Drehen", len(m.elements) == 2)


def test_spiegeln():
    m = zwei_bloecke("eigene")
    n_el = len(m.elements)
    n_oben = len(m.koerper["Oben"].elemente)
    n_unten = len(m.koerper["Unten"].elemente)
    log = []
    erg = tr.anwenden(m, tr.Auswahl(koerper=["Oben"]), *tr.spiegelung((0, 0, 1.0), (0, 0, 1)), log=log)
    check("Oben an z = 1 gespiegelt: das Dach (z = 2) liegt jetzt bei z = 0, der Boden von Unten bleibt",
          _nah(m.nodes[8:12, 2], [0, 0, 0, 0]) and _nah(m.nodes[0:4, 2], [0, 0, 0, 0])
          and _nah(m.nodes[4:8, 2], [1, 1, 1, 1]), str(m.nodes[:12, 2]))
    check("die umgestülpten Tetraeder von Oben sind weg, die von Unten bleiben",
          erg["netz_geloescht"] == n_oben and len(m.elements) == n_el - n_oben
          and not m.koerper["Oben"].elemente and len(m.koerper["Unten"].elemente) == n_unten,
          f"{erg}, {len(m.elements)} von {n_el}")
    check("… die Flächen von Oben ohne Randseiten",
          all(not m.flaechen[f].randseiten for f in m.koerper["Oben"].flaechen))
    check("Protokoll nennt das gelöschte Netz", any("umgestülpt" in z for z in log), str(log))
    m = _rahmen()
    erg = tr.anwenden(m, tr.Auswahl(staebe=["S1"]), *tr.spiegelung((0, 0, 0), (1, 0, 0)))
    check("gespiegelter Stab: Elemente bleiben, x wechselt das Vorzeichen",
          len(m.elements) == 2 and erg["netz_geloescht"] == 0 and _nah(m.nodes[4], [-5, 0, 0]))


def test_kopieren():
    m = _rahmen()
    nn0, ne0 = m.nn, len(m.elements)
    vor = m.nodes.copy()
    log = []
    erg = tr.kopieren(m, tr.Auswahl(flaechen=["F1"], staebe=["S1"], linien=["K1"]),
                      *tr.verschiebung((0, 0, 3)), anzahl=2, log=log)
    check("zwei Kopien: je 7 Knoten, 5 Linien, eine Fläche, ein Stab mit zwei Elementen",
          erg["knoten"] == 14 and len(erg["linien"]) == 10 and erg["flaechen"] == ["F2", "F3"]
          and erg["staebe"] == ["S2", "S3"] and erg["elemente"] == 4 and m.nn == nn0 + 14
          and len(m.elements) == ne0 + 4, str(erg))
    check("das Original bleibt, wie es war", _nah(m.nodes[:nn0], vor) and m.flaechen["F1"].linien == ["L1", "L2", "L3", "L4"])
    f2, f3 = m.flaechen["F2"], m.flaechen["F3"]
    kn2 = [int(n) for ln in f2.linien for n in m.lines[ln].nodes]
    kn3 = [int(n) for ln in f3.linien for n in m.lines[ln].nodes]
    check("F2 liegt bei z = 3, F3 bei z = 6, auf neuen Linien und Knoten",
          all(ln not in ("L1", "L2", "L3", "L4") for ln in f2.linien + f3.linien)
          and _nah(m.nodes[kn2, 2], [3] * len(kn2)) and _nah(m.nodes[kn3, 2], [6] * len(kn3))
          and min(kn2) >= nn0 and f2.dicke == "d10" and f2.material == "S235", str((f2.linien, f3.linien)))
    kreise = [ln for ln in m.lines.values() if ln.typ == "circle"]
    check("die Kreise: das Original und zwei Kopien mit Mittelpunkt bei z = 3 und 6",
          len(kreise) == 3 and sorted(round(float(k.geometrie["mitte"][2]), 9) for k in kreise) == [0.0, 3.0, 6.0]
          and all(abs(float(k.geometrie["radius"]) - 0.25) < 1e-12 for k in kreise))
    s2 = m.members["S2"]
    kn_s2 = [int(n) for e in s2.elements for n in m.elements[e].nodes]
    check("Stab S2: zwei neue Elemente auf neuen Knoten bei z + 3, Querschnitt übernommen",
          len(s2.elements) == 2 and min(kn_s2) >= nn0 and _nah(sorted(set(m.nodes[kn_s2, 2])), [3, 4, 5])
          and all(m.elements[e].sec == "IPE 200" for e in s2.elements), str(kn_s2))
    check("Protokoll", log and "2× kopiert" in log[0], str(log))


def test_kopieren_mit_netz():
    m = zwei_bloecke("eigene")
    n_oben = len(m.koerper["Oben"].elemente)
    ne0, nn0 = len(m.elements), m.nn
    erg = tr.kopieren(m, tr.Auswahl(koerper=["Oben"]), *tr.verschiebung((3, 0, 0)))
    k2 = m.koerper[erg["koerper"][0]]
    check("Volumen samt Netz kopiert: gleich viele Tetraeder, Gruppe = neuer Name, Flächen neu",
          erg["koerper"] == ["V1"] and len(k2.elemente) == n_oben and len(m.elements) == ne0 + n_oben
          and all(m.elements[e].group == "V1" for e in k2.elemente)
          and set(k2.flaechen) == set(erg["flaechen"]) and len(k2.flaechen) == len(m.koerper["Oben"].flaechen),
          str(erg))
    alt = sorted({int(n) for e in m.koerper["Oben"].elemente for n in m.elements[e].nodes})
    neu = sorted({int(n) for e in k2.elemente for n in m.elements[e].nodes})
    check("die Kopie steht 3 m daneben, auf eigenen Knoten",
          min(neu) >= nn0 and abs(float(m.nodes[neu, 0].mean()) - float(m.nodes[alt, 0].mean()) - 3.0) < 1e-9)
    neue_flaechen = [m.flaechen[f] for f in erg["flaechen"]]
    check("die Randseiten der neuen Flächen zeigen auf die neuen Elemente",
          any(f.randseiten for f in neue_flaechen)
          and all(int(e) in set(k2.elemente) for f in neue_flaechen for e, _s in f.randseiten))
    check("das Original hat sein Netz noch", len(m.koerper["Oben"].elemente) == n_oben)
    m = zwei_bloecke("eigene")
    log = []
    erg = tr.kopieren(m, tr.Auswahl(koerper=["Oben"]), *tr.spiegelung((0, 0, 2.0), (0, 0, 1)), log=log)
    k2 = m.koerper[erg["koerper"][0]]
    check("Spiegelkopie: Geometrie ja (Fuge bei z = 3), Tetraeder nein",
          erg["netz_uebergangen"] == n_oben and not k2.elemente and erg["elemente"] == 0
          and any("nicht mitgespiegelt" in z for z in log)
          and abs(max(float(m.nodes[int(n), 2]) for f in k2.flaechen for ln in m.flaechen[f].linien
                      for n in m.lines[ln].nodes) - 3.0) < 1e-9, str((erg, log)))


def main():
    for t in (test_abbildungen, test_verschieben, test_spiegeln, test_kopieren, test_kopieren_mit_netz):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
