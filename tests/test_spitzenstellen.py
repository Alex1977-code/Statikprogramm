"""
Netzabhaengige Spannungsspitzen erkennen (Paket 1 des Plans vom 10.10.2026).

Die Regel lautet: **Kraft geht ohne Flaeche in ein Volumen.** Wo eine
Kopplung, ein Stabende, eine Knotenlast, ein Knoten- oder Linienlager oder
eine Linienlast Kraft in Volumenknoten einleitet, ohne dass diese Knoten eine
Flaeche tragen, waechst die Spannung dort mit jeder Netzverfeinerung - am
Drehlager unter den 16 Ankerscheiben bis 1 187 N/mm2 und 39 % plastische
Dehnung. Geprueft wird:

* **Vor der Rechnung** die Einordnung je Stelle - Flaeche, Linie oder Punkt -
  an Koerpern, deren Antwort feststeht: die Platte mit Loch und starrer
  Scheibe darueber (Linie), dieselbe Scheibe auf voller Flaeche (nichts), die
  Einzellast an einem Knoten (Punkt), die Konsole (ihre Endlast auf der
  Oberkante: Linie) und Kragarm, Block, Hohlkugel, Hohlzylinder (nichts: alle
  Lasten und Lager sind Flaechen). Dazu die gebuendelte Warnung der
  Netzabnahme, die nichts anhaelt.
* **Nach der Rechnung** je Stelle Kraft, Zone, Spitze und Rang in
  ``res.info["spitzenstellen"]``; das Merkmal ``auffaellig`` mit beiden
  Bedingungen der Entscheidung vom 10.10.2026 (sigma_v >= 2 f_y in der Zone
  oder F / (A_Huelle f_y) >= 1); Stellen ohne Kraft fallen weg.
* **Speichern und Laden** mit der Ergebnisdatei.
* **Die Schnittstelle fuer Paket 3** (``auffaellige_zonen``) kommt aus dem
  Zustand zum selben Urteil wie der Nachlauf.
* **Die Zone** (Entscheidung des Anwenders vom 13.10.2026: „Netzabhängige
  Zonen sind zu groß … über Radius bzw. max. 1–2 Elementringe begrenzen“):
  die Elemente an den Knoten der Stelle (erster Ring) und deren Nachbarn
  ueber gemeinsame Knoten (zweiter Ring), diese nur bis zum Abstand
  r + 2 h des Schwerpunkts von der Mitte der Stelle. Bis zum 13.10.2026
  waren es alle Elemente im Umkreis max(4 h; r) um die Knoten.
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import diagnose, ergebnisse, examples_lib, fugen, mesher, solver   # noqa: E402
from statik3d import spitzenstellen as sp                                       # noqa: E402
from statik3d.model import Material, Model                                     # noqa: E402

from tests.test_fugen import _RING_A, _RING_RHO, _ringplatte_mit_scheibe       # noqa: E402
from tests import pruefkoerper as pk                                           # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return bool(ok)


def kurz(stellen):
    return [(s["quelle"], s["art"], s["n_knoten"]) for s in stellen]


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def lochplatte(r_scheibe=_RING_A, vorspannung=1.2e6, mit_lager=True):
    """Ringplatte (Lochradius 30 mm, 20 mm dick, hex8) mit starrer Scheibe vom
    Radius ``r_scheibe`` und dem Anker in ihrer Mitte; aussen am Rand fest,
    der Anker oben fest und mit ``vorspannung`` angespannt (LF1). Die Scheibe
    ist schon gekoppelt (fugen.starre_flaechen_koppeln)."""
    m, ids, mitte = _ringplatte_mit_scheibe(r_scheibe)
    fugen.starre_flaechen_koppeln(m, [])
    oben = [n for n in range(m.nn) if np.allclose(m.nodes[n], (0.0, 0.0, m.nodes[mitte][2] + 0.5))][0]
    if mit_lager:
        for n in ids[:, -1, :].ravel():
            m.fix(int(n), [0, 1, 2])
        m.fix(int(oben), "all")
        m.add_load_case("LF1").gravity = [0.0, 0.0, 0.0]
        m.add_vorspannung("Anker", vorspannung, case="LF1")
    return m, ids, mitte


def einzellast_quader():
    """Quader 0,4 x 0,1 x 0,1 m (hex8), bei x = 0 eingespannt, am Ende eine
    Einzellast auf **einem** Knoten der Oberkante."""
    m = Model("Einzellast")
    m.add_material(Material("S355", 210e9, 0.3, 7850, fy=355e6))
    ids = mesher.grid_box(m, "S355", 0.4, 0.1, 0.1, 8, 2, 2, typ="hex8")
    for j in range(ids.shape[1]):
        for k in range(ids.shape[2]):
            m.fix(int(ids[0, j, k]), [0, 1, 2])
    m.load_node(int(ids[-1, 1, -1]), Fz=-10e3)
    return m, ids


# --------------------------------------------------------------------------
# 1) Einordnung vor der Rechnung
# --------------------------------------------------------------------------
def test_lochplatte_linie():
    """Die starre Scheibe ueber der Bohrung haengt nur am Lochrand: eine Linie
    (48 Knoten auf dem Kreis, keine getragene Flaeche)."""
    m, _ids, mitte = lochplatte(mit_lager=False)
    st = sp.kandidaten(m)
    check("Platte mit Loch und starrer Scheibe darüber: genau eine Stelle, eine Linie",
          kurz(st) == [("starre Scheibe", "Linie", 48)], f"{kurz(st)}")
    if st:
        s = st[0]
        check("… ohne getragene Fläche, Hülle ist die Scheibe (π r²), Master das Stabende",
              s["A_trag"] == 0.0 and abs(s["A_huelle"] - np.pi * _RING_A ** 2) < 0.01 * np.pi * _RING_A ** 2
              and s["master"] == mitte,
              f"A_trag {s['A_trag'] * 1e6:.1f} mm², A_Hülle {s['A_huelle'] * 1e6:.1f} mm² "
              f"(π r² = {np.pi * _RING_A ** 2 * 1e6:.1f}), h {s['h'] * 1e3:.2f} mm, r {s['r'] * 1e3:.2f} mm")
        check("… mit einer Zone um den Ring (zwei Elementringe, Radius r + 2 h)",
              len(s["zone"]) > 0 and abs(s["zone_radius"] - (s["r"] + 2 * s["h"])) < 1e-12,
              f"{len(s['zone'])} Elemente, Radius {s['zone_radius'] * 1e3:.1f} mm")
        soll = _zwei_ringe(m, s)
        check("… die Zone sind genau die zwei Ringe (der zweite bis r + 2 h), eigene Auswertung",
              set(int(e) for e in s["zone"]) == soll,
              f"{len(s['zone'])} Elemente, eigene {len(soll)}; nur Programm "
              f"{sorted(set(int(e) for e in s['zone']) - soll)[:5]}, nur eigene {sorted(soll - set(int(e) for e in s['zone']))[:5]}")


def _zwei_ringe(m, s) -> set:
    """Die Zone nach der Regel vom 13.10.2026, unabhaengig vom Programm: Ring 1
    die Volumenelemente mit einem Knoten der Stelle, Ring 2 die mit einem
    Eckknoten aus Ring 1, dieser nur mit Schwerpunkt (Mittel der Ecken)
    hoechstens r + 2 h von der Mitte der Stelle."""
    from statik3d.elements import solid as sl
    S = set(int(k) for k in s["knoten"])
    vol = [(i, e) for i, e in enumerate(m.elements) if e.typ in sl.ECKEN_NATUERLICH]
    ecken = {i: [int(k) for k in e.nodes[:len(sl.ECKEN_NATUERLICH[e.typ])]] for i, e in vol}
    ring1 = {i for i, e in vol if S & set(int(k) for k in e.nodes)}
    n1 = set(k for i in ring1 for k in ecken[i])
    c = np.asarray(s["mitte"], float)
    grenze = float(s["r"]) + 2.0 * float(s["h"])
    ring2 = {i for i, _e in vol if i not in ring1 and n1 & set(ecken[i])
             and float(np.linalg.norm(np.asarray(m.nodes, float)[ecken[i]].mean(axis=0) - c)) <= grenze + 1e-12}
    return ring1 | ring2


def test_scheibe_auf_flaeche():
    """Dieselbe Scheibe, aber mit 42 mm Radius: sie liegt auf dem Kreisring
    der Oberseite auf und traegt ihn - eine Flaeche, keine Stelle."""
    m, _ids, _mitte = lochplatte(r_scheibe=_RING_A + _RING_RHO[3], mit_lager=False)
    st = sp.kandidaten(m)
    check("Scheibe auf der Fläche: keine Stelle", st == [], f"{kurz(st)}")


def test_einzellast_punkt():
    m, _ids = einzellast_quader()
    st = sp.kandidaten(m)
    check("Einzellast an einem Knoten: ein Punkt", kurz(st) == [("Knotenlast", "Punkt", 1)], f"{kurz(st)}")


def test_konsole_linie():
    """Die Konsole der Beispiele: die Einspannung ist eine Flaeche, die Endlast
    steht auf den 7 Knoten der Oberkante - eine echte Linienlast auf einem
    Volumen, und sie ist die einzige Meldung."""
    m = examples_lib.build_example("solid")
    st = sp.kandidaten(m)
    check("Konsole: nur die Endlast, als Linie auf 7 Knoten",
          kurz(st) == [("Knotenlast", "Linie", 7)], f"{kurz(st)}")


def test_ohne_stellen():
    """Kragarm (hex8, tet10, tet4), Block mit Reibung, Hohlkugel, Hohlzylinder:
    alle Lasten und Lager sind Flaechen - nichts zu melden."""
    faelle = []
    kr = pk.Kragarm()
    for typ in ("hex8", "tet10", "tet4"):
        faelle.append((f"Kragarm {typ}", kr.modell(typ, 8, 2, 4)[0]))
    faelle.append(("Block mit Reibung", examples_lib.build_example("friction")))
    faelle.append(("Hohlkugel", pk.Hohlkugel().modell("hex8", 4, 2)))
    faelle.append(("Hohlzylinder", pk.Hohlzylinder().modell("hex8", 6, 2)))
    for name, m in faelle:
        st = sp.kandidaten(m, zonen=False)
        check(f"{name}: keine Stelle", st == [], f"{kurz(st)}")


def test_grobes_netz():
    """Ist das Netz nur ein Element breit, ist eine ganz gelagerte Seite
    kleiner als 2 h^2 - und doch eine Flaeche des Modells: zwei hex8
    uebereinander, Boden ganz fest. Vier Eckknoten desselben Bodens in einem
    4 x 4 x 4-Netz sind dagegen vier Punktlager."""
    m = Model("Würfelpaar")
    m.add_material(Material.steel("S235"))
    U = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    m.add_nodes(np.vstack([U, U[4:] + [0, 0, 1.0]]))
    m.add_element("hex8", list(range(8)), "S235")
    m.add_element("hex8", [4, 5, 6, 7, 8, 9, 10, 11], "S235")
    for k in range(4):
        m.fix(k, "all")
    st = sp.kandidaten(m, zonen=False)
    check("zwei hex8, Boden ganz gelagert (ein Element breit): keine Stelle", st == [], f"{kurz(st)}")
    m2 = Model("Würfel 4x4x4")
    m2.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m2, "S235", 1.0, 1.0, 1.0, 4, 4, 4, typ="hex8")
    for i, j in ((0, 0), (-1, 0), (-1, -1), (0, -1)):
        m2.fix(int(ids[i, j, 0]), "all")
    st2 = sp.kandidaten(m2, zonen=False)
    check("vier Eckknoten gelagert: vier Punktlager", kurz(st2) == [("Knotenlager", "Punkt", 1)] * 4,
          f"{kurz(st2)}")


def test_warnung_in_der_abnahme():
    """Die Netzabnahme nennt die Stellen gebuendelt, eine Zeile je Art, als
    WARNUNG - sie haelt die Rechnung nicht an."""
    m, _ids, _mitte = lochplatte()
    alle = diagnose.abnahme(m, warnungen=True)
    w = [b for b in alle if b.pruefung == sp.PRUEFUNG]
    check("die Abnahme nennt die Stellen als Warnung, eine Zeile je Art",
          len(w) == 1 and w[0].stufe == "WARNUNG"
          and "1 starre Scheibe koppelt nur einen Lochrand" in w[0].text
          and "netzabhängige Spannungsspitzen" in w[0].text,
          " | ".join(b.text for b in w))
    check("ohne warnungen=True hält sie nichts an",
          not [b for b in diagnose.abnahme(m) if b.pruefung == sp.PRUEFUNG])
    zeilen = sp.warnzeilen(
        [dict(quelle="starre Scheibe", art="Linie", n_knoten=40, lochrand=True)] * 64
        + [dict(quelle="Stabende", art="Punkt", n_knoten=k, lochrand=False) for k in [1, 3] * 24])
    check("gebündelt wie am Drehlager: eine Zeile je Art",
          zeilen == ["64 starre Scheiben koppeln nur einen Lochrand (40 Knoten)",
                     "48 Stabenden hängen an 1–3 Knoten"], f"{zeilen}")


# --------------------------------------------------------------------------
# 2) Nach der Rechnung
# --------------------------------------------------------------------------
def _gerechnet():
    """Lochplatte mit 1,2 MN Ankerkraft (LF1) und einer Knotenlast in LF2,
    die in LF1 keine Kraft hat."""
    m, ids, mitte = lochplatte(vorspannung=1.2e6)
    m.add_load_case("LF2").gravity = [0.0, 0.0, 0.0]
    m.load_node(int(ids[5, 3, -1]), Fz=-5e3, case="LF2")
    an = solver.solve_all(m)
    return m, ids, mitte, an


def test_nach_der_rechnung(gerechnet):
    m, _ids, mitte, an = gerechnet
    r = an.cases["LF1"]
    info = r.info.get("spitzenstellen") or {}
    st = info.get("stellen") or []
    check("LF1: zwei Stellen geprüft, die Knotenlast aus LF2 hat hier keine Kraft und fällt weg",
          info.get("kandidaten") == 2 and info.get("ohne_kraft") == 1 and kurz(st) == [("starre Scheibe", "Linie", 48)],
          f"{info.get('kandidaten')} Kandidaten, {info.get('ohne_kraft')} ohne Kraft, {kurz(st)}")
    if not st:
        return
    s = st[0]
    e = [i for i, el in enumerate(m.elements) if el.typ == "truss"][0]
    N = abs(float(solver.beam_end_forces(m, e, r.beam_end[e])["N"][1]))
    check("die Kraft durch die Scheibe ist die Ankerkraft",
          abs(s["kraft"] - N) <= 1e-9 * N, f"{s['kraft'] / 1e3:.3f} kN / Anker {N / 1e3:.3f} kN")
    A = np.pi * _RING_A ** 2
    check("F / (A_Hülle · f_y) über die Scheibenfläche",
          abs(s["pressung_fy"] - N / (s["A_huelle"] * 355e6)) < 1e-12 and s["pressung_fy"] > 1.0,
          f"{s['pressung_fy']:.3f} (F / (π r² f_y) = {N / (A * 355e6):.3f})")
    sv = {i: float(np.sqrt(0.5 * ((v[0] - v[1]) ** 2 + (v[1] - v[2]) ** 2 + (v[2] - v[0]) ** 2)
                            + 3 * (v[3] ** 2 + v[4] ** 2 + v[5] ** 2))) for i, v in r.solid_res.items()}
    zone = [int(i) for i in s["zone"]]
    # sigma_v an den Integrationspunkten, unabhaengig nachgerechnet ueber die
    # Punktspannungen der Plastizitaet mit eps_p = 0 (elastisch)
    from statik3d import plastizitaet as pl
    z = pl.Zustand()
    for i in zone:
        z.eps_p[i] = np.zeros((1, 6))
    ip = {i: float(sp.vergleichsspannung(sig).max())
          for i, (_xi, sig) in pl.punktspannungen(m, np.asarray(r.u, float).ravel(), z).items()}
    check("die Spitze ist das größte σ_v der Zone an den Integrationspunkten, σ_v / f_y daraus",
          abs(s["sv_max"] - max(ip[i] for i in zone)) <= 1e-9 * s["sv_max"]
          and abs(s["sv_fy"] - s["sv_max"] / 355e6) < 1e-12,
          f"σ_v {s['sv_max'] / 1e6:.1f} N/mm², σ_v/f_y {s['sv_fy']:.2f}")
    check("… daneben der Elementwert des Ergebnisses (Ecken und Mitte), nur berichtet",
          abs(s["sv_auswertepunkt_max"] - max(sv[i] for i in zone)) < 1e-6,
          f"{s['sv_auswertepunkt_max'] / 1e6:.1f} N/mm² an den Auswertepunkten")
    check("auffällig, Rang 1, und die Zone ist als Elementmenge abrufbar",
          s["auffaellig"] and s["rang"] == 1 and info.get("auffaellig") == [s["nr"]]
          and set(sp.zonen_elemente(r).tolist()) == set(zone)
          and int(sp.zonen_maske(m, r).sum()) == len(zone),
          f"Gründe {s['gruende']}")
    check("die Zone liegt ganz in der Platte und sind die zwei Ringe um die Ringknoten",
          all(m.elements[i].typ == "hex8" for i in zone) and set(int(i) for i in zone) == _zwei_ringe(m, s),
          f"{len(zone)} Elemente")
    r2 = an.cases["LF2"]
    st2 = (r2.info.get("spitzenstellen") or {}).get("stellen") or []
    art2 = {x["quelle"]: x for x in st2}
    check("LF2: die Knotenlast ist ein Punkt mit ihrer Kraft (5 kN)",
          "Knotenlast" in art2 and abs(art2["Knotenlast"]["kraft"] - 5e3) < 1e-6
          and art2["Knotenlast"]["art"] == "Punkt" and art2["Knotenlast"]["pressung_fy"] is None,
          f"{kurz(st2)}")


def test_auffaellig_beide_bedingungen():
    """Entscheidung des Anwenders vom 10.10.2026: auffaellig ist eine Stelle,
    wenn in ihrer Zone sigma_v >= 2 f_y gilt **oder** die Pressung ueber die
    Huelle die Streckgrenze erreicht, F / (A_Huelle f_y) >= 1. Ohne f_y
    entfaellt die Pruefung. Am Punkt ist die Huelle eine Elementseite - ihre
    Pressung waechst mit dem Netz und zaehlt nicht."""
    m, _ids, _mitte = lochplatte(mit_lager=False)
    st = sp.kandidaten(m)
    s = st[0]
    zone = np.asarray(s["zone"], int)
    A, fy = s["A_huelle"], 355e6

    def urteil(sv_fy, pressung, model=m, stellen=st):
        F = pressung * A * fy
        sv = {int(i): 0.5 * fy for i in zone}
        sv[int(zone[len(zone) // 2])] = sv_fy * fy
        erg = sp.bewerten(model, stellen, [np.array([0.0, 0.0, F])], sv, {})
        x = erg["stellen"][0] if erg["stellen"] else None
        return x
    a = urteil(2.05, 0.2)
    check("σ_v ≥ 2 f_y allein: auffällig", a["auffaellig"] and a["gruende"] == ["σ_v ≥ 2·f_y"], f"{a['gruende']}")
    b = urteil(1.5, 1.05)
    check("F / (A_Hülle · f_y) ≥ 1 allein: auffällig", b["auffaellig"] and b["gruende"] == ["F/(A·f_y) ≥ 1"],
          f"{b['gruende']}")
    c = urteil(1.95, 0.95)
    check("knapp unter beiden Grenzen: nicht auffällig, bleibt aber zur Diagnose stehen",
          not c["auffaellig"] and c["gruende"] == [] and c["rang"] == 1, f"σ_v/f_y {c['sv_fy']:.2f}, {c['pressung_fy']:.2f}")
    d = urteil(2.5, 1.5)
    check("beide: auffällig mit beiden Gründen", d["auffaellig"] and len(d["gruende"]) == 2, f"{d['gruende']}")
    # ohne f_y: die Pruefung entfaellt
    m.materials["S355"].fy = 0.0
    e = urteil(3.0, 3.0)
    check("Werkstoff ohne f_y: keine Prüfung, nicht auffällig",
          not e["auffaellig"] and e["sv_fy"] is None and e["pressung_fy"] is None, f"{e['gruende']}")
    m.materials["S355"].fy = 355e6
    # Punkt: keine Pressung ueber die Huelle
    mq, _ids = einzellast_quader()
    sq = sp.kandidaten(mq)
    f = sp.bewerten(mq, sq, [np.array([0.0, 0.0, -1e9])], {int(i): 1.0 * 355e6 for i in sq[0]["zone"]}, {})
    g = f["stellen"][0]
    check("am Punkt zählt nur σ_v: 1 GN auf einem Knoten macht ihn nicht auffällig",
          not g["auffaellig"] and g["pressung_fy"] is None, f"{g['art']}, {g['gruende']}")
    h = sp.bewerten(mq, sq, [np.zeros(3)], {int(i): 3 * 355e6 for i in sq[0]["zone"]}, {})
    check("eine Stelle ohne Kraft fällt weg, auch mit hoher Spannung",
          h["stellen"] == [] and h["ohne_kraft"] == 1)


def test_speichern_und_laden(gerechnet):
    m, _ids, _mitte, an = gerechnet
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "lochplatte.ergebnisse")
        ergebnisse.schreiben(pfad, m, an)
        an2 = ergebnisse.lesen(pfad, m)
    a = an.cases["LF1"].info["spitzenstellen"]
    b = an2.cases["LF1"].info.get("spitzenstellen") or {}
    gleich = (len(a["stellen"]) == len(b.get("stellen") or [])
              and all(np.array_equal(x["zone"], y["zone"]) and np.array_equal(x["knoten"], y["knoten"])
                      and x["auffaellig"] == y["auffaellig"] and x["kraft"] == y["kraft"]
                      and x["sv_max"] == y["sv_max"] and x["rang"] == y["rang"]
                      for x, y in zip(a["stellen"], b.get("stellen") or [])))
    check("Speichern und Laden: Stellen, Zonen, Kraft, Spitze und Merkmal kommen gleich zurück",
          gleich and b.get("auffaellig") == a["auffaellig"],
          f"{len(b.get('stellen') or [])} Stellen")
    check("… und die Zone ist nach dem Laden abrufbar",
          np.array_equal(sp.zonen_elemente(an2.cases["LF1"]), sp.zonen_elemente(an.cases["LF1"])))
    # Eine Ergebnisdatei von vor dem 10.10.2026 traegt den Eintrag nicht:
    # nachholen rechnet ihn aus dem gespeicherten Ergebnis nach
    for r in an2.cases.values():
        r.info.pop("spitzenstellen", None)
    n = sp.nachholen(m, an2)
    c = an2.cases["LF1"].info.get("spitzenstellen") or {}
    check("nachholen ergänzt ein geladenes Ergebnis ohne Eintrag - mit demselben Urteil",
          n == 2 and c.get("auffaellig") == a["auffaellig"]
          and [x["kraft"] for x in c["stellen"]] == [x["kraft"] for x in a["stellen"]], f"{n} Ergebnisse")
    # Ein Eintrag der Fassung 1 (vor dem 13.10.2026) traegt die groessere
    # Zone von davor: nachholen wertet ihn neu aus, einer der Fassung 2 bleibt
    for r in an2.cases.values():
        e = r.info["spitzenstellen"]
        e["fassung"] = 1
        for x in e["stellen"]:
            x["zone"] = np.arange(len(m.elements), dtype=np.int32)
    n = sp.nachholen(m, an2)
    c = an2.cases["LF1"].info.get("spitzenstellen") or {}
    check("nachholen wertet einen Eintrag der Fassung 1 (größere Zone) neu aus, Fassung 2 bleibt",
          n == 2 and c.get("fassung") == sp.FASSUNG == 2
          and all(np.array_equal(x["zone"], y["zone"]) for x, y in zip(c["stellen"], a["stellen"]))
          and sp.nachholen(m, an2) == 0, f"{n} Ergebnisse, Fassung {c.get('fassung')}")


def test_schnittstelle_paket3(gerechnet):
    """auffaellige_zonen: aus Verschiebungen, sigma_v und eps_p je Element
    dieselben auffaelligen Stellen wie der Nachlauf - und es fasst nur
    Elemente der Zonen an."""
    m, _ids, _mitte, an = gerechnet
    r = an.cases["LF1"]
    st = sp.kandidaten(m)
    gefragt: set = set()
    u = np.asarray(r.u, float).ravel()
    punkte = sp.punktspannungen_der_zonen(m, st)
    zonen = set(int(i) for s in st for i in s["zone"])
    check("die Punktspannungen bauen ihren Operator nur über die Zonenelemente",
          punkte.elemente == zonen, f"{len(punkte.elemente)} Elemente, Zonen {len(zonen)}, Netz {len(m.elements)}")
    ip = punkte.sigma_v(u)

    def sigma_v(elemente):
        gefragt.update(int(i) for i in elemente)
        return np.array([ip[int(i)] for i in elemente])
    # was der Loeser je Lastfall bildet: aequivalente Elementlasten (hier die
    # Vorspannung des Ankers) und Temperaturen
    _F, feq, _q, temp = solver.case_loads(m, r.info.get("factors") or {"LF1": 1.0})
    aus = sp.auffaellige_zonen(m, st, u, sigma_v, {}, reaktionen=r.reactions,
                               faktoren=r.info.get("factors"), feq=feq, temp=temp)
    nach = [x for x in r.info["spitzenstellen"]["stellen"] if x["auffaellig"]]
    check("auffaellige_zonen: dieselben Stellen mit derselben Spitze wie der Nachlauf",
          [x["nr"] for x in aus] == [x["nr"] for x in nach]
          and [x["sv_max"] for x in aus] == [x["sv_max"] for x in nach],
          f"{[x['nr'] for x in aus]} / {[x['nr'] for x in nach]}")
    check("… und fragt σ_v nur für Elemente der Zonen ab",
          gefragt and gefragt <= zonen, f"{len(gefragt)} Elemente, Zonen {len(zonen)}, Netz {len(m.elements)}")
    if aus:
        F_n = aus[0]["kraft"]
        F_a = r.info["spitzenstellen"]["stellen"][0]["kraft"]
        check("die Kraft aus u (mit Vorspannung über feq/temp des Lösers) gleicht der des Nachlaufs",
              abs(F_n - F_a) <= 1e-6 * F_a, f"{F_n / 1e3:.3f} / {F_a / 1e3:.3f} kN")


def main():
    gerechnet = None
    for t in (test_lochplatte_linie, test_scheibe_auf_flaeche, test_einzellast_punkt, test_konsole_linie,
              test_ohne_stellen, test_grobes_netz, test_warnung_in_der_abnahme, "rechnen",
              test_nach_der_rechnung,
              test_auffaellig_beide_bedingungen, test_speichern_und_laden, test_schnittstelle_paket3):
        if t == "rechnen":
            try:
                gerechnet = _gerechnet()
            except Exception as ex:      # noqa: BLE001
                import traceback
                traceback.print_exc()
                RESULTS.append((f"Lochplatte rechnen (Ausnahme: {ex})", False))
            continue
        print(f"\n--- {t.__name__} ---")
        try:
            if t in (test_nach_der_rechnung, test_speichern_und_laden, test_schnittstelle_paket3):
                if gerechnet is None:
                    RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
                    continue
                t(gerechnet)
            else:
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
