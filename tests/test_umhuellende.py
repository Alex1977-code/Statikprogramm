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


def main():
    for t in (test_kombination_mit_alternativen, test_speichern_und_laden,
              test_umbenennen_und_entfernen, test_modellpruefung_sieht_alternativen,
              test_umhuellende_inkrementell_gleich_gestapelt,
              test_alternativen_werden_umhuellende, test_alternativen_im_kontaktmodell):
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
