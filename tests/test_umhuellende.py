"""
Umhuellende aus Kombinationen mit Alternativen.

Eine RFEM-Ergebniskombination "LF1/p oder LF2/p oder ..." ist keine Summe,
sondern Minimum und Maximum je Ergebnisgroesse ueber ihre Alternativen. Die
Pruefungen vergleichen die Umhuellende ueber Alternativen mit der Umhuellenden
ueber dieselben, einzeln gerechneten Kombinationen - und die inkrementelle
Umhuellende bitgleich mit der gestapelten.

Aufruf:  python -m tests.test_umhuellende
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import (Model, Material, Section, Situation, Combination,  # noqa: E402
                            GRUNDSTELLUNG)
from statik3d import solver, mesher  # noqa: E402

RESULTS = []
E, L, F = 210e9, 2.0, 10e3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6e} ana={want:.6e} Abw={err * 100:.4f}% {unit}")


def _kragarm_drei_lastfaelle(n: int = 4) -> tuple:
    """Kragarm auf der x-Achse mit drei Lastfaellen an der Spitze: LF1 Fz,
    LF2 Fy, LF3 Mx - drei Richtungen, damit Min und Max je Freiheitsgrad aus
    verschiedenen Alternativen kommen."""
    m = Model("Umhuellende")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.1, 0.2)
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (L, 0, 0), n)
    m.fix(ids[0], "all")
    spitze = ids[-1]
    m.add_load_case("LF1", "G")
    m.load_node(spitze, Fz=-F, case="LF1")
    m.add_load_case("LF2", "Q")
    m.load_node(spitze, Fy=F, case="LF2")
    m.add_load_case("LF3", "Q")
    m.load_node(spitze, Mx=0.5 * F, case="LF3")
    return m, ids


# --------------------------------------------------------------------------
# Modell
# --------------------------------------------------------------------------
def test_kombination_mit_alternativen():
    c = Combination("EK", {}, "ULS",
                    alternativen=[{"LF1": 1.0}, {"LF2": 1.0}, {"LF1": 1.0, "LF3": 1.5}])
    check("die Lastfaelle aller Alternativen, in Reihenfolge",
          c.lastfaelle() == ["LF1", "LF2", "LF3"], str(c.lastfaelle()))
    check("die Formel zeigt 'oder'",
          c.formula() == "1·LF1 oder 1·LF2 oder 1·LF1 + 1.5·LF3", c.formula())
    check("ist_umhuellende nur mit Alternativen",
          c.ist_umhuellende and not Combination("K", {"LF1": 1.0}).ist_umhuellende)
    check("eine gewoehnliche Kombination nennt ihre Lastfaelle wie bisher",
          Combination("K", {"LF1": 1.35, "LF2": 0.0, "LF3": 1.5}).lastfaelle() == ["LF1", "LF3"])
    lang = Combination("L", {}, "ULS", alternativen=[{f"LF{i}": 1.0} for i in range(1, 65)])
    check("lange Formeln werden gekuerzt",
          lang.formula().endswith("… (64 Alternativen)") and lang.formula().startswith("1·LF1 oder"),
          lang.formula())


def test_speichern_und_laden():
    m, _ids = _kragarm_drei_lastfaelle()
    m.combinations["EK"] = Combination("EK", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 2.0}])
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("die Alternativen ueberleben Speichern und Laden",
          m2.combinations["EK"].alternativen == [{"LF1": 1.0}, {"LF2": 2.0}],
          str(m2.combinations["EK"].alternativen))
    alt = dict(d)
    alt["combinations"] = [{k: v for k, v in c.items() if k != "alternativen"} for c in d["combinations"]]
    m3 = Model.from_dict(alt)
    check("eine alte Datei ohne das Feld bleibt lesbar",
          m3.combinations["EK"].alternativen == [] and not m3.combinations["EK"].ist_umhuellende)


def test_umbenennen_und_entfernen():
    """Ein umbenannter oder geloeschter Lastfall zieht durch alle Alternativen
    - Oberflaeche und Web rufen dieselben Methoden."""
    c = Combination("EK", {"LF1": 1.35}, "ULS",
                    alternativen=[{"LF1": 1.0}, {"LF2": 1.0}, {"LF1": 1.0, "LF3": 1.5}])
    c.lastfall_umbenennen("LF1", "Eigengewicht")
    check("umbenannt in Faktoren und Alternativen",
          c.factors == {"Eigengewicht": 1.35}
          and c.alternativen == [{"Eigengewicht": 1.0}, {"LF2": 1.0}, {"Eigengewicht": 1.0, "LF3": 1.5}],
          str(c.alternativen))
    c.lastfall_entfernen("LF2")
    check("ein entfernter Lastfall verschwindet, eine leere Alternative entfaellt",
          c.alternativen == [{"Eigengewicht": 1.0}, {"Eigengewicht": 1.0, "LF3": 1.5}],
          str(c.alternativen))
    c.lastfall_entfernen("LF3")
    check("und bleibt sonst erhalten",
          c.alternativen == [{"Eigengewicht": 1.0}, {"Eigengewicht": 1.0}] and c.factors == {"Eigengewicht": 1.35})


def test_modellpruefung_sieht_alternativen():
    m, _ids = _kragarm_drei_lastfaelle()
    m.situationen["Ausfall"] = Situation("Ausfall", "", [])
    m.load_cases["LF2"].situation = "Ausfall"
    m.combinations["EK"] = Combination("EK", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 1.0}])
    msgs = [x for x in m.check() if "EK" in x and "anderen Situation" in x]
    check("eine Alternative aus fremder Situation wird beanstandet", bool(msgs), str(m.check()))
    m.combinations["EK"].situation = "Ausfall"
    m.combinations["EK"].alternativen = [{"LF2": 1.0}, {"LF2": 1.5}]
    check("in der eigenen Situation nicht", not [x for x in m.check() if "EK" in x], str(m.check()))
    m.combinations["EK"].alternativen = [{"LF9": 1.0}]
    check("ein unbekannter Lastfall in einer Alternative wird beanstandet",
          any("EK" in x and "LF9" in x and "unbekannt" in x for x in m.check()), str(m.check()))


# --------------------------------------------------------------------------
# Loeser: inkrementelle Umhuellende
# --------------------------------------------------------------------------
def _gleich(a, b) -> bool:
    return np.array_equal(np.asarray(a), np.asarray(b))


def test_umhuellende_inkrementell_gleich_gestapelt():
    """Die inkrementelle Umhuellende ist bitgleich mit der gestapelten - auch
    in der Herkunft (bei Gleichstand gewinnt das erste Ergebnis, wie argmin)."""
    m, _ids = _kragarm_drei_lastfaelle()
    cases = solver.solve_cases(m)
    alt = solver.Envelope(m, cases, "U")
    neu = solver.Envelope(m, {}, "U")
    for k, r in cases.items():
        neu.aufnehmen(k, r)
    check("Namen", neu.names == alt.names, str(neu.names))
    check("u_min/u_max bitgleich", _gleich(neu.u_min, alt.u_min) and _gleich(neu.u_max, alt.u_max))
    check("Herkunft der Verschiebungen bitgleich",
          _gleich(neu.u_min_src, alt.u_min_src) and _gleich(neu.u_max_src, alt.u_max_src))
    check("Auflagerkraefte und Herkunft bitgleich",
          _gleich(neu.r_min, alt.r_min) and _gleich(neu.r_max, alt.r_max)
          and _gleich(neu.r_min_src, alt.r_min_src) and _gleich(neu.r_max_src, alt.r_max_src))
    check("Stabschnittgroessen je Station bitgleich (Werte und Herkunft)",
          set(neu.beam) == set(alt.beam) and all(
              _gleich(neu.beam[i][k][j], alt.beam[i][k][j])
              for i in alt.beam for k in ("N", "Vy", "Vz", "Mt", "My", "Mz") for j in range(4))
          and all(_gleich(neu.beam[i]["x"], alt.beam[i]["x"]) for i in alt.beam))
    check("Vergleichsspannung, Herkunft und Ausnutzung bitgleich",
          _gleich(neu.node_vm_max, alt.node_vm_max) and _gleich(neu.node_vm_src, alt.node_vm_src)
          and neu.util == alt.util)
    check("die Herkunft nennt verschiedene Ergebnisse",
          len(set(alt.u_max_src[-1, :3].tolist()) | set(alt.u_min_src[-1, :3].tolist())) >= 2,
          str(alt.u_max_src[-1]))
    # Umhuellende in Umhuellende
    e1 = solver.Envelope(m, {k: cases[k] for k in ("LF1", "LF2")}, "A")
    e2 = solver.Envelope(m, {"LF3": cases["LF3"]}, "B")
    ges = solver.Envelope(m, {}, "G")
    ges.aufnehmen_umhuellende(e1)
    ges.aufnehmen_umhuellende(e2)
    check("Umhuellende ueber Umhuellende = Umhuellende ueber alle (Werte)",
          _gleich(ges.u_max, alt.u_max) and _gleich(ges.u_min, alt.u_min)
          and _gleich(ges.node_vm_max, alt.node_vm_max) and ges.util == alt.util
          and all(_gleich(ges.beam[i][k][j], alt.beam[i][k][j])
                  for i in alt.beam for k in ("N", "My") for j in range(2)))
    check("und in der Herkunft, auf die Ergebnisse bezogen",
          ges.names == alt.names and _gleich(ges.u_max_src, alt.u_max_src)
          and _gleich(ges.u_min_src, alt.u_min_src) and _gleich(ges.node_vm_src, alt.node_vm_src)
          and all(_gleich(ges.beam[i][k][j], alt.beam[i][k][j])
                  for i in alt.beam for k in ("N", "My") for j in (2, 3)),
          str(ges.names))
    leer = solver.Envelope(m, {}, "leer")
    check("eine leere Umhuellende hat Nullfelder und keine Namen",
          leer.names == [] and leer.u_max.shape == (m.nn, 6) and not leer.beam
          and float(np.abs(leer.u_max).max()) == 0.0)


# --------------------------------------------------------------------------
# Loeser: Kombinationen mit Alternativen werden Umhuellende
# --------------------------------------------------------------------------
def test_alternativen_werden_umhuellende():
    """Die Umhuellende ueber die Alternativen ist die Umhuellende ueber dieselben,
    einzeln gerechneten Kombinationen; Lastfall-Alternativen mit Faktor 1
    kommen ohne neue Loesung aus."""
    m, _ids = _kragarm_drei_lastfaelle()
    m.combinations["EK"] = Combination("EK", {}, "ULS",
                                       alternativen=[{"LF1": 1.0}, {"LF2": 1.0}, {"LF1": 1.35, "LF3": 1.5}])
    m.combinations["K1"] = Combination("K1", {"LF1": 1.0})
    m.combinations["K2"] = Combination("K2", {"LF2": 1.0})
    m.combinations["K3"] = Combination("K3", {"LF1": 1.35, "LF3": 1.5})
    m.combinations["G1"] = Combination("G1", {"LF2": 1.5}, "SLS_CH")
    an = solver.solve_all(m, combinations=True, envelopes=True)
    check("EK ist kein Kombinationsergebnis", "EK" not in an.combinations, str(sorted(an.combinations)))
    check("sondern eine Umhuellende", "EK" in an.envelopes, str(list(an.envelopes)))
    ek = an.envelopes["EK"]
    ref = solver.Envelope(m, {k: an.combinations[k] for k in ("K1", "K2", "K3")}, "ref")
    check("= Umhuellende ueber die einzeln gerechneten Alternativen",
          np.allclose(ek.u_max, ref.u_max) and np.allclose(ek.u_min, ref.u_min)
          and np.allclose(ek.r_max, ref.r_max) and np.allclose(ek.node_vm_max, ref.node_vm_max)
          and all(np.allclose(ek.beam[i][k][j], ref.beam[i][k][j])
                  for i in ref.beam for k in ("N", "Vy", "Vz", "Mt", "My", "Mz") for j in range(2)))
    check("die Herkunft nennt Lastfall oder Alternative",
          ek.names == ["LF1", "LF2", "EK [3]"], str(ek.names))
    info = an.info.get("umhuellende", {}).get("EK", {})
    check("zwei Lastfall-Alternativen wiederverwendet, eine geloest",
          info.get("alternativen") == 3 and info.get("geloest") == 1, str(info))
    uls = an.envelopes["ULS"]
    check("die Umhuellende ULS enthaelt die Alternativen und die Kombinationen",
          np.allclose(uls.u_max, ref.u_max) and np.allclose(uls.u_min, ref.u_min)
          and set(uls.names) == {"K1", "K2", "K3", "LF1", "LF2", "EK [3]"}, str(uls.names))
    check("die Art-Umhuellenden stehen vor denen der Kombinationen",
          list(an.envelopes).index("ULS") < list(an.envelopes).index("EK")
          and "SLS_CH" in an.envelopes, str(list(an.envelopes)))
    check("die Umhuellende SLS_CH ist davon unberuehrt",
          an.envelopes["SLS_CH"].names == ["G1"], str(an.envelopes["SLS_CH"].names))


def test_alternativen_im_kontaktmodell():
    """Im Kontaktmodell wird eine zusammengesetzte Alternative direkt geloest,
    eine Lastfall-Alternative weiterhin wiederverwendet."""
    m, ids = _kragarm_drei_lastfaelle()
    m.support(ids[-1], [2], uz=dict(failure="zug"))
    check("das Modell ist ein Kontaktmodell", m.has_contact)
    m.combinations["EK"] = Combination("EK", {}, "ULS",
                                       alternativen=[{"LF1": 1.0}, {"LF1": 1.0, "LF2": 1.0}])
    m.combinations["K12"] = Combination("K12", {"LF1": 1.0, "LF2": 1.0})
    an = solver.solve_all(m, combinations=True, envelopes=True)
    info = an.info.get("umhuellende", {}).get("EK", {})
    check("zwei Alternativen, eine direkt geloest",
          info.get("alternativen") == 2 and info.get("geloest") == 1, str(info))
    ek = an.envelopes["EK"]
    ref = solver.Envelope(m, {"LF1": an.cases["LF1"], "K12": an.combinations["K12"]}, "ref")
    check("= Umhuellende ueber Lastfall und direkt geloeste Kombination",
          np.allclose(ek.u_max, ref.u_max) and np.allclose(ek.u_min, ref.u_min), str(ek.names))
    check("nur eine Umhuellende ULS und die von EK, keine Lastfall-Umhuellende",
          set(an.envelopes) == {"ULS", "EK"}, str(list(an.envelopes)))


# --------------------------------------------------------------------------
# Nachweise: die Alternativen einer Ergebniskombination werden nachgewiesen
# (Befund FE11, 22.09.2026)
# --------------------------------------------------------------------------
def _kragarm_nachweis(kombi: str, typ: str = "ULS") -> tuple:
    """Kragarm mit Stab S1, LF1 Fz = -10 kN, LF2 Fz = -20 kN an der Spitze.

    ``kombi``: "EK" (nur die oder-Kombination g·LF1 oder g·LF1 + q·LF2),
    "K" (dieselbe unguenstigste Summe als gewoehnliche Kombination K2), "K+EK"
    (K1 = LF1 + LF2 neben der EK) oder "" (gar keine Kombination). Im GZT ist
    g = 1,35 und q = 1,5, im GZG beide 1,0."""
    m = Model("oder")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S235", "R", (0, 0, 0), (2.0, 0, 0), 4)
    m.fix(ids[0], "all")
    m.add_member("S1", list(range(len(m.elements))))
    m.add_load_case("LF1", "G")
    m.load_node(ids[-1], Fz=-1.0e4, case="LF1")
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fz=-2.0e4, case="LF2")
    g, q = (1.35, 1.5) if typ == "ULS" else (1.0, 1.0)
    if "EK" in kombi:
        m.combinations["EK1"] = Combination(
            "EK1", {}, typ, alternativen=[{"LF1": g}, {"LF1": g, "LF2": q}])
    if kombi == "K":
        m.add_combination("K2", {"LF1": g, "LF2": q}, typ)
    if kombi == "K+EK":
        m.add_combination("K1", {"LF1": 1.0, "LF2": 1.0}, typ)
    return m, ids


def test_nachweis_sieht_die_alternativen():
    """Ein Modell nur mit der oder-Kombination muss dieselbe Ausnutzung
    liefern wie die gleichwertige gewoehnliche Kombination. Vorher wies der
    Stabnachweis still die unfaktorisierten Lastfaelle nach: 0,170 statt 0,370
    (Faktor 4,35e4/2e4 = 2,175, Kragarm linear)."""
    m_k, _ = _kragarm_nachweis("K")
    d_k = solver.solve_all(m_k, design=True).design
    u_k = d_k.members["S1"].util
    m_e, _ = _kragarm_nachweis("EK")
    d_e = solver.solve_all(m_e, design=True).design
    u_e = d_e.members["S1"].util
    check("nur oder-EK: dieselbe Ausnutzung wie die gewoehnliche Kombination",
          abs(u_e - u_k) < 1e-9 and u_k > 0.3, f"EK {u_e:.4f} / K {u_k:.4f}")
    check("nachgewiesen gegen die Alternativen der EK, nicht die Lastfaelle",
          d_e.combinations == ["EK1 [1]", "EK1 [2]"], str(d_e.combinations))
    check("die Spalte Kombination nennt die EK und ihre Alternative",
          d_e.members["S1"].governing.get("combo") == "EK1 [2]",
          str(d_e.members["S1"].governing.get("combo")))
    check("die Zusammenfassung zaehlt zwei Kombinationen, keine Warnung",
          "2 Kombinationen" in d_e.summary() and "WARNUNG" not in d_e.summary(),
          d_e.summary()[:90])
    # neben einer gewoehnlichen Kombination wird die EK nicht mehr uebergangen
    m_b, _ = _kragarm_nachweis("K+EK")
    d_b = solver.solve_all(m_b, design=True).design
    # in der Reihenfolge des Modells: EK1 ist vor K1 angelegt
    check("K1 neben EK1: beide werden nachgewiesen",
          d_b.combinations == ["EK1 [1]", "EK1 [2]", "K1"], str(d_b.combinations))
    check("und die EK ist massgebend (4,35e4 gegen 3e4 N)",
          abs(d_b.members["S1"].util - u_k) < 1e-9
          and d_b.members["S1"].governing.get("combo") == "EK1 [2]",
          f"{d_b.members['S1'].util:.4f} {d_b.members['S1'].governing.get('combo')}")


def test_rueckfall_nur_ohne_kombinationen():
    """Auf die Lastfaelle faellt der Nachweis nur zurueck, wenn das Modell gar
    keine Kombination hat. Fehlt das Ergebnis einer vorhandenen Kombination,
    wird sie als nicht nachgewiesen gemeldet - nicht still ersetzt."""
    from statik3d.ec3.design import check_members
    m0, _ = _kragarm_nachweis("")
    d0 = solver.solve_all(m0, design=True).design
    check("ohne Kombinationen gelten die Lastfaelle selbst",
          d0.combinations == ["LF1", "LF2"], str(d0.combinations))
    m1, _ = _kragarm_nachweis("K")
    an1 = solver.solve_all(m1, combinations=False)
    d1 = check_members(m1, an1)
    check("Kombination ohne Ergebnis: kein Rueckfall auf die Lastfaelle",
          d1.combinations == [] and not d1.members, str(d1.combinations))
    check("sondern eine Warnung, die die Kombination nennt",
          any("K2" in w and "nicht nachgewiesen" in w for w in getattr(d1, "warnungen", []))
          and "K2" in d1.summary() and "nicht nachgewiesen" in d1.summary(),
          d1.summary()[:120])
    from statik3d.report import Report
    an1.design = d1
    html = Report(m1, an1).html()
    check("der Bericht nennt sie im Kapitel und im Gesamturteil",
          "Kombination K2 nicht nachgewiesen" in html
          and "Kein Nachweis geführt – nicht geführt wurden" in html)


def test_gzg_sieht_die_alternativen():
    """Dasselbe fuer die Verformungsnachweise: eine GZG-Ergebniskombination
    wird ueber ihre Alternativen gefuehrt, nicht ueber die Lastfaelle."""
    ergebnis = {}
    for kombi in ("K", "EK"):
        m, ids = _kragarm_nachweis(kombi, "SLS_CH")
        m.add_verformungsgrenze("Spitze", "knoten", knoten=[ids[-1]], groesse="uz",
                                grenzart="absolut", wert=0.05, situation="SLS_CH")
        ergebnis[kombi] = solver.solve_all(m, design=True).gzg
    c_k, c_e = ergebnis["K"].checks["Spitze"], ergebnis["EK"].checks["Spitze"]
    check("GZG nur oder-EK: dieselbe Ausnutzung wie die gewoehnliche",
          abs(c_e.util - c_k.util) < 1e-9 and c_k.util > 0,
          f"EK {c_e.util:.4f} / K {c_k.util:.4f}")
    check("GZG: massgebend ist die Alternative der EK",
          c_e.kombination == "EK1 [2]", c_e.kombination)
    # ohne Situation (alle GZG): der Rueckfall auf die Lastfaelle greift nicht
    m, ids = _kragarm_nachweis("EK", "SLS_CH")
    m.add_verformungsgrenze("Alle", "knoten", knoten=[ids[-1]], groesse="uz",
                            grenzart="absolut", wert=0.05, situation="")
    g = solver.solve_all(m, design=True).gzg
    check("GZG ohne Situation: die Alternativen, nicht die Lastfaelle",
          sorted(g.kombinationen) == ["EK1 [1]", "EK1 [2]"], str(g.kombinationen))


def _block(n: int = 4):
    """Hexaederstab 0,1 x 0,1 x 0,4 m, Fuss eingespannt, Kopf mit zwei
    Lastfaellen gezogen - fuer den Volumennachweis."""
    m = Model("Block")
    m.add_material(Material.steel("S355"))
    ids = {}
    for k in range(n + 1):
        for j in range(2):
            for i in range(2):
                ids[(i, j, k)] = m.add_node(0.1 * i, 0.1 * j, 0.4 * k / n)
    els = []
    for k in range(n):
        els.append(m.add_element("hex8", [
            ids[(0, 0, k)], ids[(1, 0, k)], ids[(1, 1, k)], ids[(0, 1, k)],
            ids[(0, 0, k + 1)], ids[(1, 0, k + 1)], ids[(1, 1, k + 1)],
            ids[(0, 1, k + 1)]], "S355"))
    for j in range(2):
        for i in range(2):
            m.fix(ids[(i, j, 0)], "all")
    m.add_load_case("LF1", "G")
    m.add_load_case("LF2", "Q")
    for j in range(2):
        for i in range(2):
            m.load_node(ids[(i, j, n)], Fz=2.5e5 / 4, case="LF1")
            m.load_node(ids[(i, j, n)], Fz=5.0e5 / 4, case="LF2")
    m.add_volumenbereich("Schaft", els)
    return m


def test_volumen_sieht_die_alternativen():
    """Und fuer den Volumennachweis."""
    m_k = _block()
    m_k.add_combination("K2", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    v_k = solver.solve_all(m_k, design=True).volumen.bereiche["Schaft"]
    m_e = _block()
    m_e.combinations["EK1"] = Combination(
        "EK1", {}, "ULS", alternativen=[{"LF1": 1.35}, {"LF1": 1.35, "LF2": 1.5}])
    vr = solver.solve_all(m_e, design=True).volumen
    v_e = vr.bereiche["Schaft"]
    check("Volumen nur oder-EK: dieselbe Ausnutzung wie die gewoehnliche",
          abs(v_e.util - v_k.util) < 1e-9 and v_k.util > 0,
          f"EK {v_e.util:.4f} / K {v_k.util:.4f}")
    check("Volumen: massgebend ist die Alternative der EK",
          v_e.kombination == "EK1 [2]" and vr.kombinationen == ["EK1 [1]", "EK1 [2]"],
          f"{v_e.kombination} {vr.kombinationen}")


def test_kontaktmodell_alternativen_fuer_nachweise():
    """Im Kontaktmodell laesst sich eine Alternative nicht aus den Lastfaellen
    ueberlagern: ihr direkt geloestes Ergebnis wird aufbewahrt, die Nachweise
    sehen es - auch nach Speichern und Laden der Ergebnisse."""
    import tempfile
    from statik3d.ec3.design import _uls_results
    from statik3d import ergebnisse
    m, ids = _kragarm_drei_lastfaelle()
    m.support(ids[-1], [2], uz=dict(failure="zug"))
    m.combinations["EK"] = Combination("EK", {}, "ULS",
                                       alternativen=[{"LF1": 1.0}, {"LF1": 1.0, "LF2": 1.0}])
    m.combinations["K12"] = Combination("K12", {"LF1": 1.0, "LF2": 1.0})
    an = solver.solve_all(m, combinations=True, envelopes=True)
    warn: list = []
    uls = _uls_results(m, an, warnungen=warn)
    check("Kontakt: die Nachweise sehen die direkt geloeste Alternative",
          "EK [2]" in uls and np.allclose(uls["EK [2]"].u, an.combinations["K12"].u)
          and not warn, f"{list(uls)} {warn}")
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "k.ergebnisse")
        ergebnisse.schreiben(pfad, m, an)
        an2 = ergebnisse.lesen(pfad, m)
    warn2: list = []
    uls2 = _uls_results(m, an2, warnungen=warn2)
    check("und nach Speichern und Laden der Ergebnisse",
          "EK [2]" in uls2 and np.allclose(uls2["EK [2]"].u, an.combinations["K12"].u)
          and not warn2, f"{list(uls2)} {warn2}")
    an2.alternativen = {}
    warn3: list = []
    uls3 = _uls_results(m, an2, warnungen=warn3)
    check("fehlt sie, wird sie gemeldet statt still weggelassen",
          "EK [2]" not in uls3
          and any("EK [2]" in w and "nicht nachgewiesen" in w for w in warn3), str(warn3))


# --------------------------------------------------------------------------
# Theorie II./III. Ordnung einer Ergebniskombination (Befund FE12, 22.09.2026)
# --------------------------------------------------------------------------
def _druckkragarm(theorie2: str = "ein", theorie_ek: str = "", druck: float = 5.0e5) -> tuple:
    """Kragarm unter Druck mit Querlast in y (schwache Achse): 1,35·LF1 +
    1,5·LF2 gibt N = 1,425e6 N gegen N_cr = pi^2 E I_z/(2L)^2 = 2,16e6 N -
    nach II. Ordnung waechst die Querverschiebung deutlich. Ohne
    Imperfektionen, damit K2 und die gleiche Alternative dasselbe rechnen.
    ``druck`` = 5e4 statt 5e5 N gibt alpha_cr 31,94 (EK1 [1]) und 15,13
    (EK1 [2], K2), gemessen 23.09.2026 - dann bleibt "auto" bei I. Ordnung."""
    m = Model("Druck")
    m.add_material(Material("S", E=E, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (L, 0, 0), 4)
    m.fix(ids[0], "all")
    m.add_load_case("LF1", "G")
    m.load_node(ids[-1], Fx=-druck, Fy=1.0e3, case="LF1")
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fx=-druck, Fy=2.0e3, case="LF2")
    m.design.theorie2 = theorie2
    m.design.imperfektionen = False
    m.combinations["EK1"] = Combination(
        "EK1", {}, "ULS", theorie=theorie_ek,
        alternativen=[{"LF1": 1.35}, {"LF1": 1.35, "LF2": 1.5}])
    m.combinations["K2"] = Combination("K2", {"LF1": 1.35, "LF2": 1.5}, "ULS",
                                       theorie=theorie_ek)
    return m, ids


def test_theorie2_der_ergebniskombination():
    """Die Theorie der EK gilt fuer ihre Alternativen. Vorher legte Theorie II.
    Ordnung fuer die EK ein Nullergebnis in an.combinations (factors leer),
    zaehlte es als 'am verformten System gerechnet', und die Umhuellende der
    EK blieb eine lineare Ueberlagerung."""
    from statik3d.ec3.design import _uls_results
    m, ids = _druckkragarm("ein")
    an = solver.solve_all(m)
    spitze = ids[-1]
    check("II. Ordnung: die EK ist kein Kombinationsergebnis",
          "EK1" not in an.combinations, str(list(an.combinations)))
    t2 = an.theorie2
    check("Th2: keine Zeile fuer die EK selbst, eine je Alternative",
          "EK1" not in t2.kombinationen
          and {"EK1 [1]", "EK1 [2]"} <= set(t2.kombinationen), str(list(t2.kombinationen)))
    check("Th2: jede Zeile gerechnet und mit Last (u_I > 0)",
          all(i.gerechnet and i.u_max_I > 0 for i in t2.kombinationen.values()),
          str({k: (i.gerechnet, round(i.u_max_I, 6)) for k, i in t2.kombinationen.items()}))
    check("Th2: die Zusammenfassung zaehlt K2 und die zwei Alternativen",
          t2.summary().startswith("Theorie II. Ordnung: 3 von 3"), t2.summary()[:70])
    k2 = an.combinations["K2"]
    lin = solver.solve_combination(m, Combination("lin", {"LF1": 1.35, "LF2": 1.5}, "ULS"),
                                   an.cases, nichtlinear=False)
    ek = an.envelopes["EK1"]
    w_ek, w_k2 = float(ek.u_max[spitze, 1]), float(k2.u[spitze, 1])
    w_lin = float(lin.u[spitze, 1])
    check("Th2: EK-Umhuellende zeigt den Zuwachs der massgebenden Alternative",
          k2.info.get("theorie") == "II. Ordnung" and abs(w_ek - w_k2) <= 1e-9 * abs(w_k2)
          and w_ek > 1.5 * w_lin,
          f"EK {w_ek * 1e3:.3f} mm, K2 (II) {w_k2 * 1e3:.3f} mm, linear {w_lin * 1e3:.3f} mm")
    uls = _uls_results(m, an)
    check("Th2: die Nachweise sehen die Alternativen nach II. Ordnung",
          list(uls) == ["EK1 [1]", "EK1 [2]", "K2"]
          and np.allclose(uls["EK1 [2]"].u, k2.u)
          and uls["EK1 [2]"].info.get("theorie") == "II. Ordnung", str(list(uls)))
    check("Th2: die Umhuellende ULS enthaelt keine Nullzeile der EK",
          "EK1" not in an.envelopes["ULS"].names, str(an.envelopes["ULS"].names))


def test_theorie2_leere_kombination_schreibt_nichts():
    """Eine Kombination ohne Lastfall mit Faktor ungleich null ergibt nach II.
    Ordnung nichts - und darf kein Nullergebnis als 'gerechnet' ablegen."""
    from statik3d.theorie2 import check_theorie2
    m, _ids = _druckkragarm("ein")
    m.combinations["K0"] = Combination("K0", {}, "ULS")
    an = solver.Analysis(m)
    t2 = check_theorie2(m, an, combos=["K0"])
    i0 = t2.kombinationen.get("K0")
    check("leere Kombination: kein Ergebnis in an.combinations",
          "K0" not in an.combinations and i0 is not None and not i0.gerechnet,
          f"{list(an.combinations)} {None if i0 is None else (i0.gerechnet, i0.hinweise)}")


def test_theorie3_der_ergebniskombination():
    """Dasselbe fuer eine EK mit theorie = 'III'."""
    m, ids = _druckkragarm("aus", theorie_ek="III")
    an = solver.solve_all(m)
    spitze = ids[-1]
    t3 = an.theorie3
    check("III. Ordnung: die EK ist kein Kombinationsergebnis",
          "EK1" not in an.combinations, str(list(an.combinations)))
    check("Th3: eine Zeile je Alternative, keine fuer die EK",
          t3 is not None and "EK1" not in t3.kombinationen
          and {"EK1 [1]", "EK1 [2]"} <= set(t3.kombinationen),
          str(list(t3.kombinationen)) if t3 is not None else "keine")
    w_ek = float(an.envelopes["EK1"].u_max[spitze, 1])
    w_k2 = float(an.combinations["K2"].u[spitze, 1])
    check("Th3: die EK-Umhuellende ist die Alternative nach III. Ordnung",
          an.combinations["K2"].info.get("theorie") == "III. Ordnung"
          and abs(w_ek - w_k2) <= 1e-9 * abs(w_k2),
          f"EK {w_ek * 1e3:.3f} mm, K2 (III) {w_k2 * 1e3:.3f} mm")


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung vom 23.09.2026
# --------------------------------------------------------------------------
def test_hoehere_theorie_ohne_abgelegtes_ergebnis():
    """Eine Alternative, die nach Theorie II./III. Ordnung zu rechnen ist und
    deren Ergebnis nicht abgelegt wurde (Rechnung ohne Kombinationen,
    Ergebnisdatei von vor der Kur), wird gemeldet - vorher wurde sie still
    linear ueberlagert: EK1 [2] 3,321 statt 9,705 mm."""
    from statik3d.ec3.design import _uls_results
    m, _ids = _druckkragarm("ein")
    an0 = solver.solve_all(m, combinations=False)
    w0: list = []
    uls0 = _uls_results(m, an0, warnungen=w0)
    check("Th2 ohne Kombinationen: die Alternativen nicht linear nachgewiesen",
          not any(k.startswith("EK1") for k in uls0), str(list(uls0)))
    check("sondern gemeldet, mit Theorie II. Ordnung als Grund",
          all(any(f"EK1 [{k}]" in w and "Theorie II. Ordnung" in w for w in w0)
              for k in (1, 2)), str([w[:90] for w in w0]))
    an = solver.solve_all(m)
    an.alternativen = {}
    w1: list = []
    uls1 = _uls_results(m, an, warnungen=w1)
    check("Th2 ohne abgelegte Alternativen (alte Ergebnisdatei): ebenso",
          list(uls1) == ["K2"] and len(w1) == 2, f"{list(uls1)} {len(w1)} Warnungen")
    # theorie2 "auto" mit alpha_cr >= 10: die Rechnung bleibt fuer jede
    # Alternative bei I. Ordnung (Th2-Zeile ohne "gerechnet"), die
    # Ueberlagerung ist dann das Ergebnis - keine Warnung
    m2, _ = _druckkragarm("auto", druck=5.0e4)
    an2 = solver.solve_all(m2)
    w2: list = []
    uls2 = _uls_results(m2, an2, warnungen=w2)
    t2 = an2.theorie2.kombinationen
    check("Th2 auto, alpha_cr >= 10: linear wie K2, keine Warnung",
          not w2 and "EK1 [2]" in uls2 and not t2["EK1 [2]"].gerechnet
          and np.allclose(uls2["EK1 [2]"].u, an2.combinations["K2"].u),
          f"{w2[:1]} {({k: round(i.alpha_cr, 2) for k, i in t2.items()})}")
    m3, _ = _druckkragarm("aus", theorie_ek="III")
    an3 = solver.solve_all(m3, combinations=False)
    w3: list = []
    uls3 = _uls_results(m3, an3, warnungen=w3)
    check("Th3 ohne Kombinationen: gemeldet statt linear",
          not any(k.startswith("EK1") for k in uls3)
          and any("EK1 [2]" in w and "Theorie III. Ordnung" in w for w in w3),
          f"{list(uls3)} {[w[:90] for w in w3]}")


def test_lastfall_hoeherer_ordnung_ohne_abgelegtes_ergebnis():
    """Eine Alternative mit einem Lastfall nach Theorie II. Ordnung laesst
    sich nicht aus den Lastfaellen ueberlagern: die volle Rechnung legt sie
    ab, fehlt sie, wird sie gemeldet."""
    from statik3d.ec3.design import _uls_results
    m, _ = _kragarm_nachweis("EK")
    m.load_cases["LF2"].theorie = "II"
    an = solver.solve_all(m, design=True)
    check("Lastfall nach II. Ordnung: volle Rechnung ohne Warnung, Alternative abgelegt",
          not an.design.warnungen and "EK1 [2]" in an.alternativen,
          f"{an.design.warnungen} {list(an.alternativen)}")
    an.alternativen = {}
    w: list = []
    uls = _uls_results(m, an, warnungen=w)
    check("fehlt sie, wird sie mit dem Lastfall gemeldet",
          list(uls) == ["EK1 [1]"] and any("EK1 [2]" in x and "Lastfall LF2" in x for x in w),
          f"{list(uls)} {[x[:100] for x in w]}")


def test_alternative_bei_theorie_I_aus_linearen_lastfaellen():
    """Eine Alternative einer EK nach II. Ordnung, die bei I. Ordnung bleibt
    (theorie2 "auto", alpha_cr >= 10), ist die Ueberlagerung der LINEAREN
    Lastfaelle - wie die gewoehnliche Kombination. Vorher faltete solve_all
    die EK erst nach _lastfaelle_hoeherer_ordnung: mit LF2 auf theorie "II"
    kam ein Gemisch heraus (1,35·LF1 linear + 1,5·LF2 nach II. Ordnung),
    wurde abgelegt und nachgewiesen - gemessen 23.09.2026 an diesem Modell
    EK1 [2] 3,374407 statt 3,320749 mm, EK1 [3] 1,562553 statt 1,526781 mm."""
    from statik3d.ec3.design import _uls_results
    from statik3d.solver import Results
    m, ids = _druckkragarm("auto", druck=5.0e4)
    m.load_cases["LF2"].theorie = "II"
    m.combinations["EK1"].alternativen.append({"LF2": 1.0})
    m.combinations["K3"] = Combination("K3", {"LF2": 1.0}, "ULS")
    an = solver.solve_all(m)
    spitze = ids[-1]
    lin = solver.solve_cases(m)                   # rein linear, ohne Theorie je Lastfall
    t2 = an.theorie2.kombinationen
    lf2 = an.cases["LF2"]
    check("Voraussetzung: LF2 nach II. Ordnung, sichtbar groesser als linear",
          lf2.info.get("theorie") == "II. Ordnung"
          and lf2.u[spitze, 1] > 1.01 * lin["LF2"].u[spitze, 1],
          f"{lf2.u[spitze, 1] * 1e3:.6f} gegen {lin['LF2'].u[spitze, 1] * 1e3:.6f} mm")
    check("Voraussetzung: alle Kombinationen und Alternativen bleiben bei I. Ordnung",
          all(not t2[n].gerechnet for n in ("K2", "K3", "EK1 [1]", "EK1 [2]", "EK1 [3]")),
          str({k: (i.gerechnet, round(i.alpha_cr, 2)) for k, i in t2.items()}))
    soll2 = Results.combine(m, [(lin["LF1"], 1.35), (lin["LF2"], 1.5)], "soll2")
    k2, k3 = an.combinations["K2"], an.combinations["K3"]
    check("gewoehnliche Kombination: Ueberlagerung der linearen Lastfaelle (Schutz)",
          np.allclose(k2.u, soll2.u, rtol=1e-12, atol=0)
          and np.allclose(k3.u, lin["LF2"].u, rtol=1e-12, atol=0),
          f"K2 {k2.u[spitze, 1] * 1e3:.6f} mm, K3 {k3.u[spitze, 1] * 1e3:.6f} mm")
    w: list = []
    uls = _uls_results(m, an, warnungen=w)
    a2, a3 = uls.get("EK1 [2]"), uls.get("EK1 [3]")
    check("EK1 [2] im Nachweis gleich K2, kein Gemisch mit LF2 nach II. Ordnung",
          a2 is not None and np.allclose(a2.u, k2.u, rtol=1e-12, atol=0),
          "fehlt" if a2 is None else f"{a2.u[spitze, 1] * 1e3:.6f} gegen K2 "
                                     f"{k2.u[spitze, 1] * 1e3:.6f} mm")
    check("EK1 [3] = 1,0·LF2 im Nachweis gleich K3 (LF2 linear)",
          a3 is not None and np.allclose(a3.u, k3.u, rtol=1e-12, atol=0),
          "fehlt" if a3 is None else f"{a3.u[spitze, 1] * 1e3:.6f} gegen K3 "
                                     f"{k3.u[spitze, 1] * 1e3:.6f} mm")
    env = an.envelopes["EK1"]
    check("EK-Umhuellende gleich der Umhuellenden ueber K2 und K3, keine Warnung",
          abs(float(env.u_max[spitze, 1]) - float(k2.u[spitze, 1]))
          <= 1e-12 * abs(float(k2.u[spitze, 1])) and not w,
          f"{float(env.u_max[spitze, 1]) * 1e3:.6f} gegen {float(k2.u[spitze, 1]) * 1e3:.6f} mm"
          f", {w[:1]}")


def test_stellungsreihe_ohne_kombinationen():
    """Eine Stellungsreihe, die ohne Kombinationen rechnet, aber Nachweise
    fuehren soll, weist nichts nach - das muss beim eta stehen. Vorher:
    eta = 0.000, ok = True und im Bericht 'Umhüllende: eta = 0.000'."""
    from statik3d.bridges.positions import Stellungsreihe, Stellung
    m, _ = _kragarm_nachweis("K")
    r = Stellungsreihe(m, "Kragarm")
    r.add(Stellung("S1", 0.0, "geschlossen"))
    u = r.rechnen(kombinationen=False, nachweise=True)
    e = r.ergebnis("S1")
    # getattr: so zeigt die Ruecknahmeprobe den alten Zustand als FAIL mit
    # Zahlen statt als Ausnahme
    w = list(getattr(e, "warnungen", None) or [])
    check("ohne Kombinationen: die Stellung ist nicht ok",
          not e.ok and any("K2" in x for x in w), f"ok {e.ok}, eta {e.eta:.3f}, {w[:1]}")
    b = u.bericht()
    check("Bericht: kein 'eta = 0.000' als Ergebnis, sondern der Hinweis",
          "Umhüllende: eta =" not in b and "eta nicht bestimmt" in b
          and "Kombination K2 nicht nachgewiesen" in b,
          [z for z in b.splitlines() if "Umhüllende" in z or "WARNUNG" in z][:2])
    kurz = u.kurztext() if hasattr(u, "kurztext") else f"eta = {u.eta:.3f}"
    check("die Zeile nach dem Rechnen sagt es ebenso",
          "nicht bestimmt" in kurz and "NICHT VOLLSTÄNDIG" in kurz, kurz)
    soll = solver.solve_all(m, design=True).design.members["S1"].util
    u2 = r.rechnen(kombinationen=True, nachweise=True)
    e2 = r.ergebnis("S1")
    hinweis = u2.warnhinweis() if hasattr(u2, "warnhinweis") else ""
    check("mit Kombinationen: ok, eta wie der Stabnachweis, kein Hinweis",
          e2.ok and abs(e2.eta - soll) < 1e-9 and hinweis == ""
          and f"Umhüllende: eta = {soll:.3f}" in u2.bericht(),
          f"eta {e2.eta:.4f} soll {soll:.4f}, {hinweis}")


def test_keine_warnung_ohne_verlangten_nachweis():
    """Verlangt kein Stab (Bereich, Beulfeld, Anschluss) einen Nachweis, darf
    keine fehlende GZT-Kombination gemeldet werden. Vorher kippte ein Modell
    nur mit GZG-Kombinationen und Staeben ohne Nachweis im Gesamturteil von
    'Alle Nachweise erfüllt.' auf 'nicht geführt: EC3 (1 Warnung)'."""
    from statik3d.report import Report
    from statik3d.ec3.volumen import check_volumen
    from statik3d.ec3.beulen import check_beulen, check_lasteinleitungen
    from statik3d.joints.anschluss import check_joints
    m, ids = _kragarm_nachweis("K", "SLS_CH")
    m.members["S1"].design = False
    m.add_verformungsgrenze("Spitze", "knoten", knoten=[ids[-1]], groesse="uz",
                            grenzart="absolut", wert=0.05, situation="SLS_CH")
    an = solver.solve_all(m, design=True)
    check("nur GZG, Stab ohne Nachweis: keine EC3-Warnung",
          not an.design.warnungen, str(an.design.warnungen))
    html = Report(m, an).html()
    check("das Gesamturteil bleibt 'Alle Nachweise erfüllt.'",
          "Alle Nachweise erfüllt." in html and "nicht geführt wurden" not in html)
    leer = [f(m, an) for f in (check_beulen, check_lasteinleitungen, check_joints)]
    check("ohne Beulfeld, Stelle und Anschluss: keine Warnung",
          all(not x.warnungen for x in leer), str([x.warnungen for x in leer]))
    m2, _ = _kragarm_nachweis("K", "SLS_CH")
    an2 = solver.solve_all(m2, design=True)
    check("Gegenprobe: verlangt der Stab einen Nachweis, bleibt die Warnung",
          any("keine des Grenzzustands der Tragfähigkeit" in w for w in an2.design.warnungen),
          str(an2.design.warnungen))
    mb = _block()
    mb.add_combination("C1", {"LF1": 1.0}, "SLS_CH")
    mb.volumenbereiche["Schaft"].design = False
    anb = solver.solve_all(mb)
    vb = check_volumen(mb, anb)
    mb.volumenbereiche["Schaft"].design = True
    vb2 = check_volumen(mb, anb)
    check("Volumen: Warnung nur, wenn der Bereich einen Nachweis verlangt",
          not vb.warnungen and bool(vb2.warnungen), f"{vb.warnungen} / {vb2.warnungen}")


def main():
    for t in (test_kombination_mit_alternativen, test_speichern_und_laden,
              test_umbenennen_und_entfernen, test_modellpruefung_sieht_alternativen,
              test_umhuellende_inkrementell_gleich_gestapelt,
              test_alternativen_werden_umhuellende, test_alternativen_im_kontaktmodell,
              test_nachweis_sieht_die_alternativen, test_rueckfall_nur_ohne_kombinationen,
              test_gzg_sieht_die_alternativen, test_volumen_sieht_die_alternativen,
              test_kontaktmodell_alternativen_fuer_nachweise,
              test_theorie2_der_ergebniskombination,
              test_theorie2_leere_kombination_schreibt_nichts,
              test_theorie3_der_ergebniskombination,
              test_hoehere_theorie_ohne_abgelegtes_ergebnis,
              test_lastfall_hoeherer_ordnung_ohne_abgelegtes_ergebnis,
              test_alternative_bei_theorie_I_aus_linearen_lastfaellen,
              test_stellungsreihe_ohne_kombinationen,
              test_keine_warnung_ohne_verlangten_nachweis):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
