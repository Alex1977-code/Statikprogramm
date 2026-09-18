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


def _rippe(m, name="V5", R=0.03, T=0.02):
    """Ein Blech mit **einer** Ausrundung an Ober- und Unterkante: zwei
    Kreisboegen gleichen Radius auf einer Achse laengs der Blechdicke."""
    def kontur(y):
        return (m.add_node(0.0, y, 0.0), m.add_node(0.2, y, 0.0), m.add_node(0.2 + R, y, R),
                m.add_node(0.2 + R, y, 0.25), m.add_node(0.0, y, 0.25))
    u, o = kontur(0.0), kontur(T)
    for tag, (p_, yy) in {"u": (u, 0.0), "o": (o, T)}.items():
        m.add_line(f"{name}_{tag}1", [p_[0], p_[1]])
        m.add_line(f"{name}_{tag}2", [p_[1], p_[2]], "arc",
                   punkte=[(0.2, yy, 0.0), (0.2 + R * 0.7071, yy, R * (1 - 0.7071)), (0.2 + R, yy, R)])
        m.add_line(f"{name}_{tag}3", [p_[2], p_[3]])
        m.add_line(f"{name}_{tag}4", [p_[3], p_[4]])
        m.add_line(f"{name}_{tag}5", [p_[4], p_[0]])
    for i in range(5):
        m.add_line(f"{name}_v{i}", [u[i], o[i]])
    m.add_flaeche(f"{name}_S1", [f"{name}_u{i}" for i in range(1, 6)], material="S355")
    m.add_flaeche(f"{name}_S2", [f"{name}_o{i}" for i in range(1, 6)], material="S355")
    for i in range(1, 6):
        m.add_flaeche(f"{name}_M{i}", [f"{name}_u{i}", f"{name}_v{i % 5}", f"{name}_o{i}",
                                       f"{name}_v{i - 1}"], material="S355")
    return m.add_koerper(name, [f"{name}_S1", f"{name}_S2"] + [f"{name}_M{i}" for i in range(1, 6)],
                         material="S355")


def test_rippe_ist_kein_zylinder():
    """Eine Rippe mit einer Ausrundung hat zwei gleiche Bögen auf einer Achse
    (die Blechdicke) - und galt damit als Zylinder. Am Drehlager bekam V5 auf
    diesem Weg 0,02 mm Spiel und wurde von seinen Nachbarn getrennt, obwohl es
    ein Blech ist (17.09.2026)."""
    m = Model("Rippe")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    _rippe(m)
    z = spiel.zylinder(m, "V5")
    check("eine Rippe mit Ausrundung ist kein Zylinder", not z["ok"], z.get("grund", "")[:110])
    check("… und der Grund nennt den Punkt weit außerhalb der Achse",
          "von der Achse" in z.get("grund", "") and "297" in z.get("grund", "").replace(",", "."),
          z.get("grund", "")[:110])
    erg = spiel.zylinder_spiel(m, "V5", 2e-5, [])
    check("… und „Spiel geben“ weist sie ab, statt ihre Geometrie zu ändern",
          not erg.get("ok"), str(erg.get("grund", ""))[:90])
    # Der echte Stift bleibt einer
    m2, _k = _stift_und_platte()
    check("der Stift wird weiterhin als Zylinder erkannt", spiel.zylinder(m2, "V1")["ok"])
    # und ein Bolzen mit Kopf (zwei Radien) auch: kein Punkt liegt weiter
    # draussen als der Kopfkreis
    from tests.test_fortschritt import _zylinder as _zyl
    m3 = Model("Bolzen")
    m3.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    _zyl(m3, "B1", r=0.02, hoehe=0.08)
    check("ein Zylinder aus zwei Halbbögen je Kreis bleibt erkannt", spiel.zylinder(m3, "B1")["ok"],
          spiel.zylinder(m3, "B1").get("grund", ""))


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


def _stift_durch_zwei_bleche():
    """Ein Stift r = 20 mm durch **zwei** Bleche: die Bohrung hat Kreise in
    beiden. Wird nur einer aufgeweitet, laeuft sie kegelig zu."""
    m = Model("Zwei Bleche")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    k = _zylinder(m, "V1", r=0.02, hoehe=0.08)        # z = 0 … 0,08
    for nr, (z0, z1) in enumerate(((0.0, 0.02), (0.05, 0.08)), start=1):
        # Zwei Bleche um den Stift; ihr Loch sind die Stiftbögen der jeweiligen Höhe
        e = [m.add_node(x, y, z) for z in (z0, z1) for x, y in ((-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1))]
        for i in range(4):
            m.add_line(f"B{nr}U{i}", [e[i], e[(i + 1) % 4]])
            m.add_line(f"B{nr}O{i}", [e[4 + i], e[4 + (i + 1) % 4]])
            m.add_line(f"B{nr}V{i}", [e[i], e[4 + i]])
        # Kreise des Lochs in beiden Deckflächen dieses Blechs
        for tag, zz in (("u", z0), ("o", z1)):
            a_ = m.add_node(-0.02, 0, zz)
            b_ = m.add_node(0.02, 0, zz)
            m.add_line(f"B{nr}K{tag}1", [a_, b_], "arc", punkte=[(-0.02, 0, zz), (0, 0.02, zz), (0.02, 0, zz)])
            m.add_line(f"B{nr}K{tag}2", [b_, a_], "arc", punkte=[(0.02, 0, zz), (0, -0.02, zz), (-0.02, 0, zz)])
        m.add_flaeche(f"B{nr}_unten", [f"B{nr}U{i}" for i in range(4)], material="S355")
        m.flaechen[f"B{nr}_unten"].oeffnungen = [[f"B{nr}Ku1", f"B{nr}Ku2"]]
        m.add_flaeche(f"B{nr}_oben", [f"B{nr}O{i}" for i in range(4)], material="S355")
        m.flaechen[f"B{nr}_oben"].oeffnungen = [[f"B{nr}Ko1", f"B{nr}Ko2"]]
        for i in range(4):
            m.add_flaeche(f"B{nr}_M{i}", [f"B{nr}U{i}", f"B{nr}V{(i + 1) % 4}", f"B{nr}O{i}", f"B{nr}V{i}"],
                          material="S355")
        m.add_koerper(f"Blech{nr}", [f"B{nr}_unten", f"B{nr}_oben"] + [f"B{nr}_M{i}" for i in range(4)],
                      material="S355")
    return m, k


def test_bohrung_aufweiten():
    """Die Bohrung aufweiten statt den Stift zu verkleinern - über ihre ganze
    Länge, also in jedem Bauteil, durch das sie geht (17.09.2026, „damit das
    Modell sauber bleibt sollte die Bohrung über ihre gesamte Länge angepasst
    werden, sonst ergeben sich leichte Kegel im Volumen“)."""
    m, _k = _stift_durch_zwei_bleche()
    z = spiel.zylinder(m, "V1")
    check("der Stift wird erkannt: r = 20 mm", z["ok"] and abs(z["radius"] - 0.02) < 1e-12,
          f"{z.get('radius')} / {z.get('grund')}")
    tr = spiel.bohrungen_zur_achse(m, z["punkt"], z["achse"], z["radius"], ausser="V1")
    check("die Bohrung wird in beiden Blechen gefunden, je vier Bögen",
          sorted(tr) == ["Blech1", "Blech2"] and all(len(v) == 4 for v in tr.values()),
          str({k_: len(v) for k_, v in tr.items()}))
    log = []
    erg = spiel.bohrung_spiel(m, z["punkt"], z["achse"], z["radius"], 2e-5, ausser="V1", log=log)
    check("aufgeweitet: r = 20,010 mm in beiden Blechen",
          erg["ok"] and abs(erg["radius_neu"] - 0.02001) < 1e-9 and sorted(erg["koerper"]) == ["Blech1", "Blech2"],
          str({k_: erg[k_] for k_ in ("radius_neu", "koerper")}))
    # kein Kegel: alle Bohrungskreise haben denselben Radius
    radien = set()
    for kname in ("Blech1", "Blech2"):
        for fn in m.koerper[kname].flaechen:
            for ln in spiel._linien_der_flaeche(m.flaechen[fn]):
                L = m.lines.get(ln)
                try:
                    kr = spiel._bogen_kreis(L, m)
                except ValueError:
                    kr = None
                if kr is not None:
                    radien.add(round(kr[1], 9))
    check("kein Kegel: jeder Bohrungskreis hat r = 20,010 mm",
          radien == {round(0.02001, 9)}, str(sorted(round(x * 1e3, 4) for x in radien)))
    check("der Stift bleibt bei r = 20,000 mm",
          abs(spiel.zylinder(m, "V1")["radius"] - 0.02) < 1e-9,
          f"{spiel.zylinder(m, 'V1')['radius'] * 1e3:.4f} mm")
    check("das Netz der Bleche ist gelöscht (neu vernetzen), das Protokoll nennt beide",
          any("Blech1" in z_ and "Blech2" in z_ for z_ in log), str(log)[:120])
    erg2 = spiel.bohrung_spiel(m, z["punkt"], z["achse"], 0.05, 2e-5, ausser="V1", log=[])
    check("eine Bohrung, die es nicht gibt, wird abgewiesen", not erg2["ok"], erg2.get("grund", "")[:70])
    # Keine Linienkopie ohne Fläche: am Drehlager blieben drei solche liegen,
    # und ihre 71 Netzknoten hingen danach an keinem Element (18.09.2026)
    benutzt = {ln for f in m.flaechen.values() for ln in spiel._linien_der_flaeche(f)}
    waisen = [ln for ln in m.lines if ln not in benutzt]
    check("keine Linie bleibt ohne Fläche zurück (sonst hängen ihre Netzknoten an nichts)",
          not waisen, str(waisen[:6]))


def main():
    for t in (test_rippe_ist_kein_zylinder, test_zylinder_spiel, test_bohrung_aufweiten,
              test_flaechen_spiel):
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
