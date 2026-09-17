"""Spiel geben (17.09.2026): ein Zylinder wird geometrisch um das halbe
Durchmesserspiel verkleinert, nachdem er von den Nachbarn getrennt wurde;
eine ebene Flaeche wird um einen Spalt nach innen versetzt.

Aufruf:  python -m tests.test_spiel
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import mesher, spiel                            # noqa: E402
from statik3d.model import Material, Model                    # noqa: E402
from tests.test_fortschritt import _zylinder                  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def _stift_und_platte():
    """Ein Stift r = 20 mm in einer Platte, die seine Kreisboegen als Loch
    benutzt - wie RFEM Stift und Bohrung ueber dieselben Linien fuehrt."""
    m = Model("Stift")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    k = _zylinder(m, "V1", r=0.02, hoehe=0.08)
    # Platte 0,2 x 0,2 x 0,02 m um den Stift, Loch = die Boegen des Stifts (unten, z = 0)
    e = [m.add_node(x, y, z) for x, y, z in ((-0.1, -0.1, 0), (0.1, -0.1, 0), (0.1, 0.1, 0), (-0.1, 0.1, 0),
                                             (-0.1, -0.1, -0.02), (0.1, -0.1, -0.02), (0.1, 0.1, -0.02), (-0.1, 0.1, -0.02))]
    for i in range(4):
        m.add_line(f"PO{i}", [e[i], e[(i + 1) % 4]])
        m.add_line(f"PU{i}", [e[4 + i], e[4 + (i + 1) % 4]])
        m.add_line(f"PV{i}", [e[i], e[4 + i]])
    m.add_flaeche("P_oben", [f"PO{i}" for i in range(4)], material="S355")
    m.flaechen["P_oben"].oeffnungen = [["V1_u1", "V1_u2"]]
    m.add_flaeche("P_unten", [f"PU{i}" for i in range(4)], material="S355")
    for i in range(4):
        m.add_flaeche(f"P_M{i}", [f"PO{i}", f"PV{(i + 1) % 4}", f"PU{i}", f"PV{i}"], material="S355")
    m.add_koerper("Platte", ["P_oben", "P_unten"] + [f"P_M{i}" for i in range(4)], material="S355")
    return m, k


def _radien(m, name):
    z = spiel.zylinder(m, name)
    k = m.koerper[name]
    kn = sorted({int(n) for fn in k.flaechen for ln in m.flaechen[fn].linien for n in m.lines[ln].nodes})
    P = m.nodes[kn]
    d = P - z["punkt"]
    rad = d - np.outer(d @ z["achse"], z["achse"])
    return np.linalg.norm(rad, axis=1), kn


def test_zylinder_spiel():
    m, k = _stift_und_platte()
    z = spiel.zylinder(m, "V1")
    check("der Stift wird als Zylinder erkannt: r = 20 mm, Achse z, vier Bögen",
          z["ok"] and abs(z["radius"] - 0.02) < 1e-12 and abs(abs(z["achse"][2]) - 1) < 1e-9 and len(z["boegen"]) == 4,
          str({k_: v for k_, v in z.items() if k_ in ("ok", "radius", "grund")}))
    check("die Platte ist kein Zylinder", not spiel.zylinder(m, "Platte")["ok"], spiel.zylinder(m, "Platte")["grund"])
    log = []
    els = mesher.mesh_koerper(m, k, log=[], h=0.01)
    check("vor dem Spiel: der Stift ist vernetzt", len(k.elemente) > 0, str(len(k.elemente)))
    loch_vorher = list(m.flaechen["P_oben"].oeffnungen[0])
    erg = spiel.zylinder_spiel(m, "V1", 1e-4, log)
    check("Spiel 0,1 mm am Durchmesser: der Stift wird von der Platte getrennt (Bögen des Lochs kopiert)",
          erg["ok"] and erg["getrennt"]["linien"] >= 2 and erg["getrennt"]["knoten"] >= 2, str(erg.get("getrennt")))
    check("das Loch der Platte behält seine Linien mit r = 20 mm",
          m.flaechen["P_oben"].oeffnungen[0] == loch_vorher
          and all(abs(spiel.kreis_aus_punkten(m.lines[ln].geometrie["punkte"])[1] - 0.02) < 1e-12 for ln in loch_vorher))
    rad, kn = _radien(m, "V1")
    check("die Knoten des Stifts liegen jetzt auf r = 19,95 mm", np.allclose(rad, 0.01995, atol=1e-9), str(np.round(rad * 1e3, 4)))
    boegen = [ln for fn in k.flaechen for ln in m.flaechen[fn].linien if m.lines[ln].typ == "arc"]
    check("seine Bögen haben r = 19,95 mm, und sie sind nicht die Bögen des Lochs",
          all(abs(spiel.kreis_aus_punkten(m.lines[ln].geometrie["punkte"])[1] - 0.01995) < 1e-9 for ln in boegen)
          and not set(boegen) & set(loch_vorher), str(sorted(set(boegen))))
    check("die Knoten des Stifts sind nicht mehr die Knoten des Lochs",
          not set(kn) & {int(n) for ln in loch_vorher for n in m.lines[ln].nodes})
    check("das Netz des Stifts ist gelöscht, das Protokoll nennt Radius und Spiel",
          not k.elemente and erg["netz_geloescht"] > 0 and any("r = 19.950 mm" in z_ and "0.100 mm" in z_ for z_ in log),
          str(log[-1])[:140])
    els = mesher.mesh_koerper(m, k, log=[], h=0.01)
    P = m.nodes[sorted({int(n) for i in k.elemente for n in m.elements[i].nodes})]
    d = P - z["punkt"]
    rad = np.linalg.norm(d - np.outer(d @ z["achse"], z["achse"]), axis=1)
    check("neu vernetzt: das Netz des Stifts bleibt innerhalb r = 19,95 mm",
          len(k.elemente) > 0 and float(rad.max()) <= 0.01995 + 1e-6, f"{len(k.elemente)} Elemente, r max {rad.max() * 1e3:.4f} mm")
    check("Spiel null oder kein Zylinder wird abgewiesen",
          not spiel.zylinder_spiel(m, "V1", 0.0, [])["ok"] and not spiel.zylinder_spiel(m, "Platte", 1e-4, [])["ok"])


def test_flaechen_spiel():
    from tests.test_fugen import zwei_bloecke
    m = zwei_bloecke("gemeinsam", 0.5)
    check("zwei Blöcke mit gemeinsamer Trennfläche „Fuge“",
          "Fuge" in m.koerper["Oben"].flaechen and "Fuge" in m.koerper["Unten"].flaechen)
    log = []
    erg = spiel.flaechen_spiel(m, "Oben", ["Fuge"], 5e-4, log)
    neu = [fn for fn in m.koerper["Oben"].flaechen if fn != "Fuge"]
    fn_neu = erg["flaechen"][0] if erg["ok"] and erg["flaechen"] else None
    check("die gemeinsame Fläche bekommt für „Oben“ eine Kopie, „Unten“ behält „Fuge“",
          erg["ok"] and erg["getrennt"]["flaechen"] == 1 and fn_neu != "Fuge" and fn_neu in m.koerper["Oben"].flaechen
          and "Fuge" in m.koerper["Unten"].flaechen and "Fuge" not in m.koerper["Oben"].flaechen, str(erg.get("getrennt")))
    z_neu = sorted({round(float(m.nodes[int(n)][2]), 6) for ln in m.flaechen[fn_neu].linien for n in m.lines[ln].nodes})
    z_alt = sorted({round(float(m.nodes[int(n)][2]), 6) for ln in m.flaechen["Fuge"].linien for n in m.lines[ln].nodes})
    check("die Kopie liegt 0,5 mm höher (nach innen in „Oben“), die Fuge von „Unten“ bleibt bei z = 1",
          z_neu == [1.0005] and z_alt == [1.0], f"{z_neu} / {z_alt}")
    check("das Netz von „Oben“ ist gelöscht, „Unten“ behält seines",
          not m.koerper["Oben"].elemente and len(m.koerper["Unten"].elemente) > 0)


def main():
    for t in (test_zylinder_spiel, test_flaechen_spiel):
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
