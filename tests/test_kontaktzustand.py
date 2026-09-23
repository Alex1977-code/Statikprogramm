"""
Kontaktzustand wiederverwenden: Warmstart und behaltene Faktorisierung.

Die Kontakt-Iteration beginnt bisher bei jedem Lastfall bei der Geometrie und
faktorisiert in jedem Schritt neu - am Drehlager 42 Schritte zu je 10 bis
13 s, 18 min je Lastfall. Zustaende einer Ermuedungskombination unterscheiden
sich wenig: der naechste Lastfall beginnt beim konvergierten Zustand des
vorigen (Warmstart), und ein Schritt mit unveraenderter Kontaktsteifigkeit
setzt nur rueckwaerts ein (Signatur). Geprueft am Block mit Reibung (Auflast
90 kN, Horizontalkraft 20 kN, mu = 0,3: teilweises Gleiten).

Aufruf:  python -m tests.test_kontaktzustand
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import contact, solver, examples_lib  # noqa: E402
from statik3d.contact import ContactSystem  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def _modell():
    """Block mit Reibung, drei Lastfaelle: LF1 wie das Beispiel, LF2 dieselben
    Lasten mal 1,1 (aehnlicher Zustand), LF3 gleich LF1."""
    m = examples_lib.build_example("friction")
    lf1 = list(m.load_cases)[0]
    basis = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    for name, f in (("LF2", 1.1), ("LF3", 1.0)):
        m.add_load_case(name, "Q")
        for n, F in basis:
            m.load_node(n, Fx=F[0] * f, Fy=F[1] * f, Fz=F[2] * f)
    m.active_case = lf1
    return m, lf1


def test_sicherung():
    m, lf1 = _modell()
    system = solver.StaticSystem(m)
    cs = ContactSystem(m, system.K, [])
    cs.initialize()
    z = cs.zustand()
    check("Sicherung: eine Kennung, je Bedingung aktiv/gleitet/Fn", z["kennung"][0] == len(cs.cons)
          and len(z["aktiv"]) == len(cs.cons) == len(z["Fn"]), str(z["kennung"][0]))
    cs.cons[0].active = not cs.cons[0].active
    cs.cons[1].slip = True
    cs.cons[1].slip_dir = np.array([1.0, 0.0])
    cs.cons[1].Fn = 123.0
    z2 = cs.zustand()
    s_a, s_b = cs.signatur(), None
    cs.initialize()
    s_b = cs.signatur()
    check("Signatur aendert sich mit der Aktivmenge", s_a != s_b)
    ok = cs.zustand_setzen(z2)
    check("Sicherung uebernommen: Aktivmenge, Gleiten, Richtung, Fn",
          ok and cs.cons[0].active == bool(z2["aktiv"][0]) and cs.cons[1].slip
          and cs.cons[1].Fn == 123.0 and np.allclose(cs.cons[1].slip_dir, [1.0, 0.0])
          and cs.signatur() == s_a)
    fremd = dict(z2)
    fremd["kennung"] = (len(cs.cons) + 1, ())
    check("eine fremde Sicherung wird abgelehnt", not cs.zustand_setzen(fremd))


def test_warmstart():
    m, lf1 = _modell()
    t = time.time()
    kalt = solver.solve_cases(m, [lf1])[lf1]
    t_kalt = time.time() - t
    check("kalt: Kontakt konvergiert, Zustand gesichert",
          kalt.info.get("contact_converged") and kalt.kontaktzustand is not None
          and not kalt.info.get("contact_warm"),
          f"{kalt.info.get('contact_iterations')} Schritte, "
          f"{kalt.info.get('contact_factorisations')} Faktorisierungen, {t_kalt:.2f} s")
    check("kalt: weniger Faktorisierungen als Schritte (unveraenderte Matrix bleibt)",
          kalt.info.get("contact_factorisations", 99) < kalt.info.get("contact_iterations", 0),
          f"{kalt.info.get('contact_factorisations')} < {kalt.info.get('contact_iterations')}")
    # LF2 und LF3 kalt (einzeln) und warm (in der Reihe nach LF1)
    kalt2 = solver.solve_cases(m, ["LF2"])["LF2"]
    kalt3 = solver.solve_cases(m, ["LF3"])["LF3"]
    reihe = solver.solve_cases(m, [lf1, "LF2", "LF3"])
    warm2, warm3 = reihe["LF2"], reihe["LF3"]
    check("warm: LF2 startet beim Zustand von LF1",
          warm2.info.get("contact_warm") and warm2.info.get("contact_converged"))
    u_ref = float(np.abs(kalt2.u).max())
    # Haften/Gleiten ist am Rand der Reibgrenze nicht eindeutig: kalt und
    # warm duerfen sich in der Verteilung unterscheiden, im Gleichgewicht nicht.
    # **Haftanker sind wegabhaengig:** wo ein Knoten zu haften beginnt, legt
    # die Gleitgeschichte fest, und quer zur Last (hier y) darf ein haftender
    # Knoten jede Querkraft im Reibkegel tragen. Gemessen 22.09.2026 an LF2:
    # mit dem hex8 bis dahin (punktweise Volumendehnung) 1,0e-5, mit der
    # projizierten Volumendehnung (A1 der Element-Sitzung) 1,46e-3 * u_ref -
    # nur in u_y der Fussknoten, wo u_y selbst 0,01 bis 0,02 µm betraegt;
    # u_x und u_z hoechstens 6,9e-4, die Auflagerkraefte gleich. Darum wird
    # die Lastebene (x, z) wie bisher auf 1e-3 geprueft, quer dazu auf 5e-3.
    du = np.abs(np.asarray(warm2.u) - np.asarray(kalt2.u)).reshape(-1, 6)[:m.nn]
    check("warm: dieselbe Loesung wie kalt in der Lastebene (LF2, u_x, u_z auf 1e-3)",
          float(du[:, [0, 2]].max()) < 1e-3 * u_ref,
          f"Abweichung {float(du[:, [0, 2]].max()) / u_ref:.1e}")
    check("warm: quer zur Last (u_y) auf 5e-3 - Haftanker wegabhaengig",
          float(du[:, 1].max()) < 5e-3 * u_ref, f"Abweichung {float(du[:, 1].max()) / u_ref:.1e}")
    check("warm: dieselben Auflagerkraefte (LF2), beide Laeufe konvergiert",
          np.allclose(warm2.reactions.sum(axis=0), kalt2.reactions.sum(axis=0), rtol=1e-9, atol=1e-6)
          and warm2.info.get("contact_converged") and kalt2.info.get("contact_converged"))
    from statik3d.elements import solid as _sl
    dsv = max(abs(_sl.von_mises(np.asarray(warm2.solid_res[i])) - _sl.von_mises(np.asarray(kalt2.solid_res[i])))
              for i in kalt2.solid_res)
    check("warm: Vergleichsspannung wie kalt auf 1 N/mm² (das Maß des Anwenders)", dsv <= 1e6,
          f"größte Abweichung {dsv / 1e6:.3f} N/mm²")
    check("warm: hoechstens so viele Schritte wie kalt (LF2)",
          warm2.info.get("contact_iterations", 99) <= kalt2.info.get("contact_iterations", 0),
          f"warm {warm2.info.get('contact_iterations')} / kalt {kalt2.info.get('contact_iterations')}")
    # LF3 (= LF1) folgt in der Reihe auf LF2: Warmstart aus dessen Zustand
    check("warm: LF3 nach LF2 in wenigen Schritten (hoechstens 8, hoechstens 3 Faktorisierungen)",
          warm3.info.get("contact_warm")
          and warm3.info.get("contact_iterations", 99) <= 8
          and warm3.info.get("contact_factorisations", 99) <= 3,
          f"{warm3.info.get('contact_iterations')} Schritte, "
          f"{warm3.info.get('contact_factorisations')} Faktorisierungen")
    check("warm: LF3 trifft LF1 und den kalten LF3 (Verschiebungen auf 1e-3)",
          float(np.abs(warm3.u - kalt.u).max()) < 1e-3 * u_ref
          and float(np.abs(warm3.u - kalt3.u).max()) < 1e-3 * u_ref)
    # Derselbe Lastfall gleich noch einmal, mit demselben System: ein Schritt,
    # keine neue Faktorisierung (die letzte bleibt im System), dieselbe Loesung
    # bis auf die Setzrunde der Reibkraft (dF < 1e-4 f_ref, gemessen 1,5e-5)
    systeme = {}
    a = solver.solve_cases(m, [lf1], systeme=systeme)[lf1]
    b = solver.solve_cases(m, [lf1], systeme=systeme)[lf1]
    check("derselbe Lastfall noch einmal: 1 Schritt, 0 Faktorisierungen, dieselbe Loesung auf 1e-4",
          b.info.get("contact_warm") and b.info.get("contact_iterations") == 1
          and b.info.get("contact_factorisations") == 0
          and float(np.abs(b.u - a.u).max()) < 1e-4 * max(float(np.abs(a.u).max()), 1e-30),
          f"{b.info.get('contact_iterations')} Schritte, {b.info.get('contact_factorisations')} Fakt., "
          f"Abweichung {float(np.abs(b.u - a.u).max()) / max(float(np.abs(a.u).max()), 1e-30):.1e}")
    # Ein ganz anderer Lastfall (Horizontalkraft umgekehrt): der gesicherte
    # Zustand passt nicht, der Warmstart wird verworfen, das Ergebnis stimmt
    m.add_load_case("LF4", "Q")
    for nl in m.load_cases[lf1].nodal_loads:
        m.load_node(nl.node, Fx=-nl.F[0], Fy=nl.F[1], Fz=nl.F[2])
    kalt4 = solver.solve_cases(m, ["LF4"])["LF4"]
    reihe4 = solver.solve_cases(m, [lf1, "LF4"])
    warm4 = reihe4["LF4"]
    check("umgekehrte Last: Warmstart verworfen, Neustart von der Geometrie",
          not warm4.info.get("contact_warm")
          and any("Warmstart verworfen" in str(z) for z in warm4.info.get("contact_log", [])),
          str([z for z in warm4.info.get("contact_log", []) if "Warmstart" in str(z)])[:120])
    check("umgekehrte Last: dieselben Auflagerkraefte wie kalt",
          np.allclose(warm4.reactions.sum(axis=0), kalt4.reactions.sum(axis=0), rtol=1e-9, atol=1e-6)
          and float(np.abs(warm4.u - kalt4.u).max()) < 1e-3 * float(np.abs(kalt4.u).max()))
    # Kombination direkt mit Kontakt: Warmstart aus dem System
    m.add_combination("K", {lf1: 1.0, "LF2": 0.0}, typ="ULS")
    systeme = {}
    solver.solve_cases(m, [lf1], systeme=systeme)
    komb = solver.solve_combinations(m, ["K"], use_jobs=False, systeme=systeme)["K"]
    check("Kombination: Warmstart aus dem Zustand des Systems",
          komb.info.get("contact_warm") and komb.info.get("contact_iterations", 99) <= 2,
          f"{komb.info.get('contact_iterations')} Schritte")


def test_warmstart_ohne_halt():
    """Ein Warmstart, dessen Zustand im ersten Schritt keinen Halt laesst
    (alle Bedingungen offen - wie ein Lager mit Ausfall, das im vorigen
    Lastfall offen war), wird verworfen und kalt neu gerechnet statt mit
    „singulaer“ abzubrechen (test_web, 12.09.2026)."""
    m = examples_lib.build_example("friction")
    lf = list(m.load_cases)[0]
    kalt = solver.solve_cases(m, [lf])[lf]
    z = dict(kalt.kontaktzustand)
    z["aktiv"] = np.zeros_like(z["aktiv"])
    z["gleitet"] = np.zeros_like(z["gleitet"])
    system = solver.StaticSystem(m)
    F, _feq, _q, _temp = solver.case_loads(m, {lf: 1.0}, None)
    u, R, cons, cf, info = solver.solve_with_contact(m, system, F, start=z)
    check("Warmstart ohne Halt wird verworfen und kalt neu gerechnet",
          any("kein Gleichgewicht" in s for s in info["contact_log"]) and info["contact_converged"]
          and not info["contact_warm"], str([s for s in info["contact_log"] if "Warmstart" in s])[:90])
    check("… mit demselben Ergebnis wie der kalte Lauf",
          float(np.abs(u.reshape(kalt.u.shape) - kalt.u).max()) < 1e-9 * float(np.abs(kalt.u).max()),
          f"{float(np.abs(u.reshape(kalt.u.shape) - kalt.u).max()):.2e}")


def test_fortschritt_kontakt():
    """Die Kontakt-Iteration meldet einen wachsenden Anteil im Fenster ihres
    Lastfalls (0,35 … 0,60 in solve_all) - ein Balken statt eines Streifens."""
    m = examples_lib.build_example("friction")
    lf = list(m.load_cases)[0]
    meldungen = []

    def cb(text, anteil=None):
        meldungen.append((str(text), anteil))
    solver.solve_cases(m, [lf], progress=cb)
    it = [a for tx, a in meldungen if tx.startswith("Kontakt-Iteration")]
    check("jede Kontakt-Iteration meldet einen Anteil", len(it) > 3 and all(a is not None for a in it),
          f"{len(it)} Schritte")
    check("… wachsend, im Fenster 0,35 … 0,60 des Gesamtlaufs",
          all(b > a for a, b in zip(it, it[1:])) and 0.35 <= min(it) and max(it) <= 0.60,
          f"{it[0]:.3f} … {it[-1]:.3f}")
    ohne = []
    system = solver.StaticSystem(m)
    F, _feq, _q, _temp = solver.case_loads(m, {lf: 1.0}, None)
    solver.solve_with_contact(m, system, F, progress=lambda tx, a=None: ohne.append((tx, a)))
    check("ohne Fenster (Einzelaufruf) bleibt es beim Text",
          all(a is None for tx, a in ohne if tx.startswith("Kontakt-Iteration")))


def test_grundlast():
    """Eine Grundlast (Vorspannung, Eigengewicht) wirkt in jeder direkt
    geloesten Rechnung mit: der Block mit Reibung, Auflast als Grundlast,
    Horizontalkraft als eigener Lastfall - allein geloest dasselbe wie die
    Kombination aus beiden. Linear (ohne Kontakt) aendert die Marke nichts."""
    m = examples_lib.build_example("friction")
    lf1 = list(m.load_cases)[0]
    lasten = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    m.load_cases[lf1].nodal_loads.clear()
    for n, F in lasten:                       # LF1: nur die Auflast (Grundlast)
        m.load_node(n, Fz=F[2])
    m.load_cases[lf1].grundlast = True
    m.add_load_case("H", "Q")
    for n, F in lasten:                       # H: nur die Horizontalkraft
        m.load_node(n, Fx=F[0])
    m.add_combination("P+H", {lf1: 1.0, "H": 1.0}, typ="ULS")
    allein = solver.solve_cases(m, ["H"])["H"]
    check("Lastfall allein: die Grundlast wirkt mit und steht im Ergebnis",
          allein.info.get("grundlast") == [lf1], str(allein.info.get("grundlast")))
    komb = solver.solve_combinations(m, ["P+H"], use_jobs=False)["P+H"]
    u_ref = float(np.abs(komb.u).max())
    check("… und liefert dasselbe wie die Kombination Grundlast + H (auf 1e-4)",
          float(np.abs(allein.u - komb.u).max()) < 1e-4 * u_ref
          and np.allclose(allein.reactions.sum(axis=0), komb.reactions.sum(axis=0), rtol=1e-6, atol=1e-3),
          f"Abweichung {float(np.abs(allein.u - komb.u).max()) / u_ref:.1e}")
    check("die Kombination selbst zaehlt die Grundlast nicht doppelt",
          "grundlast" not in komb.info)
    m.load_cases[lf1].grundlast = False
    ohne = solver.solve_cases(m, ["H"])["H"]
    check("ohne Marke: nur die Horizontalkraft (anderes Ergebnis, keine Grundlast)",
          "grundlast" not in ohne.info and float(np.abs(ohne.u - allein.u).max()) > 1e-3 * u_ref)
    # linear: die Marke aendert am Lastfallergebnis nichts
    ml = examples_lib.build_example("frame")
    namen = list(ml.load_cases)
    a = solver.solve_cases(ml, [namen[-1]])[namen[-1]]
    ml.load_cases[namen[0]].grundlast = True
    b = solver.solve_cases(ml, [namen[-1]])[namen[-1]]
    check("linear: die Grundlast bleibt ein gewoehnlicher Lastfall (Ueberlagerung)",
          "grundlast" not in b.info and float(np.abs(a.u - b.u).max()) == 0.0)
    # Speichern und Laden halten die Marke
    from statik3d.model import Model
    d = m.to_dict()
    m2 = Model.from_dict(d)
    liste = next(v for v in d.values() if isinstance(v, list) and v and isinstance(v[0], dict)
                 and v[0].get("name") == lf1)
    check("die Marke ueberlebt Speichern und Laden", m2.load_cases["H"].grundlast is False
          and liste[0].get("grundlast") is False and m2.load_cases[lf1].grundlast is False)


def _ermuedungsblock(faktoren):
    """Block mit Reibung, Auflast als Grundlast, je Zustand eine Horizontallast
    (Faktor auf die des Beispiels) - alle Zustaende einer Ermuedungslast."""
    from statik3d.model import FatigueLoad
    m = examples_lib.build_example("friction")
    lf1 = list(m.load_cases)[0]
    lasten = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    m.load_cases[lf1].nodal_loads.clear()
    for n, F in lasten:
        m.load_node(n, Fz=F[2])
    m.load_cases[lf1].grundlast = True
    for name, f in faktoren:
        m.add_load_case(name, "Q")
        for n, F in lasten:
            m.load_node(n, Fx=F[0] * f)
    m.fatigue_loads["E"] = FatigueLoad("E", folge=[x for x, _ in faktoren], wiederholungen=1e5)
    return m, lf1, lasten


def _abweichung(a, b):
    """(max |du| / max |u|, max |d sigma_v| in Pa) zweier Ergebnisse."""
    from statik3d.elements import solid as _sl
    u_ref = float(np.abs(b.u).max())
    du = float(np.abs(np.asarray(a.u) - np.asarray(b.u)).max()) / u_ref
    dsv = max((abs(_sl.von_mises(np.asarray(a.solid_res[i])) - _sl.von_mises(np.asarray(b.solid_res[i])))
               for i in b.solid_res), default=0.0)
    return du, float(dsv)


def test_einfrieren():
    """Die Zustaende einer Ermuedungslast: der erste nichtlinear, die weiteren
    mit seinem eingefrorenen Kontaktzustand linear - eine Rueckwaerts-
    einsetzung je Zustand, keine Faktorisierung, **wenn der Zustand passt**.
    Am Block mit Reibung (Auflast als Grundlast): H2 = H1 passt und bleibt
    eingefroren; H3 = 1,1 H1 hebt vier haftende Knoten ueber den Reibkegel -
    bis zum 22.09.2026 hiess das trotzdem "konvergiert" und lag 7,0 % neben
    der nichtlinearen Loesung, jetzt wird es nachgerechnet."""
    m, lf1, lasten = _ermuedungsblock((("H1", 1.0), ("H2", 1.0), ("H3", 1.1)))
    check("Referenzen: H2 und H3 frieren den Zustand von H1 ein, H1 bleibt nichtlinear",
          solver.ermuedungsreferenzen(m) == {"H2": "H1", "H3": "H1"}, str(solver.ermuedungsreferenzen(m)))
    an = solver.solve_all(m, combinations=False, envelopes=False, fatigue=True)
    h1, h2, h3 = an.cases["H1"], an.cases["H2"], an.cases["H3"]
    folge = list(an.cases)
    check("Reihenfolge: H2 unmittelbar nach seiner Referenz H1 (die Faktorisierung bleibt), "
          "der Grundlastfall danach",
          folge.index("H2") == folge.index("H1") + 1 and folge.index(lf1) > folge.index("H3"), str(folge))
    check("_mit_referenzen_zuerst: Referenz, ihre Zustaende, dann der Rest",
          solver._mit_referenzen_zuerst(["A", "B", "C", "D", "E"], {"C": "B", "E": "B", "D": "A"})
          == ["A", "D", "B", "C", "E"])
    check("H1 nichtlinear (Kontakt-Iteration), H2 eingefroren: 1 Schritt, 0 Faktorisierungen",
          not h1.info.get("contact_frozen") and h1.info.get("contact_iterations", 0) > 1
          and h2.info.get("contact_frozen") and h2.info.get("contact_frozen_from") == "H1"
          and h2.info.get("contact_iterations") == 1 and h2.info.get("contact_factorisations") == 0
          and not h2.info.get("contact_frozen_verworfen"),
          f"H1 {h1.info.get('contact_iterations')} Schritte, H2 {h2.info.get('contact_iterations')} / "
          f"{h2.info.get('contact_factorisations')}")
    last = sum(F[0] for _n, F in lasten)
    check("eingefroren: Gleichgewicht (Auflager = Last)",
          abs(h2.reactions[:, 0].sum() + last) < 1e-6 * abs(last), f"Rx = {h2.reactions[:, 0].sum():.1f} N")
    v3 = h3.info.get("contact_frozen_verworfen") or {}
    check("H3 = 1,1 H1: der eingefrorene Zustand passt nicht (haftende Knoten ueber dem Reibkegel) "
          "und wird verworfen",
          v3.get("kegel", 0) > 0 and not h3.info.get("contact_frozen")
          and h3.info.get("contact_frozen_from") == "H1", str(v3))
    check("H3 nichtlinear nachgerechnet und konvergiert",
          h3.info.get("contact_iterations", 0) > 1 and h3.info.get("contact_converged"),
          f"{h3.info.get('contact_iterations')} Schritte")
    check("die Meldung nennt den Grund und das Nachrechnen",
          any("passt aber nicht zu dieser Last" in z and "nachgerechnet" in z
              for z in h3.info.get("contact_log", [])))
    m.design.ermuedung_kontakt_einfrieren = False
    check("ausgeschaltet: keine Referenzen", solver.ermuedungsreferenzen(m) == {})
    voll = solver.solve_cases(m, ["H2", "H3"])
    du2, dsv2 = _abweichung(h2, voll["H2"])
    # gemessen 22.09.2026: du 2,1e-6 (Genauigkeit der Iteration), d sigma_v 0,0000 N/mm2
    check("H2 eingefroren gegen nichtlinear: gleich (u auf 1e-4, sigma_v auf 1 N/mm2)",
          du2 < 1e-4 and dsv2 <= 1e6 and not voll["H2"].info.get("contact_frozen"),
          f"du {du2:.1e}, d sigma_v {dsv2 / 1e6:.4f} N/mm2")
    du3, dsv3 = _abweichung(h3, voll["H3"])
    check("H3 nachgerechnet gegen nichtlinear: sigma_v auf 1 N/mm2, u auf 1e-3",
          du3 < 1e-3 and dsv3 <= 1e6, f"du {du3:.1e}, d sigma_v {dsv3 / 1e6:.4f} N/mm2")
    check("Analyse nennt die eingefrorenen Zustaende, Ermuedung wurde gefuehrt",
          an.info.get("kontakt_eingefroren") == {"H2": "H1", "H3": "H1"} and an.fatigue is not None,
          str(an.info.get("kontakt_eingefroren")))


def test_eingefroren_nur_wenn_der_zustand_passt():
    """Jede Art, auf die ein eingefrorener Zustand nicht passt, wird erkannt
    und nachgerechnet. Gemessen am 22.09.2026 (Block mit Reibung, Referenz H1),
    Abweichung des eingefrorenen Ergebnisses zur nichtlinearen Loesung, das
    bis dahin "konvergiert" hiess: 0,5 H1 18,8 % (Durchdringung, Gleiten gegen
    die Richtung), -1,0 H1 70,0 % (Zug an geschlossenen Bedingungen).
    Ruecknahmeprobe ohne die Pruefung: dann bliebe -1,0 H1 eingefroren und falsch."""
    faktoren = (("H1", 1.0), ("H4", 0.5), ("H5", -1.0))
    m, _lf1, _l = _ermuedungsblock(faktoren)
    an = solver.solve_all(m, combinations=False, envelopes=False, fatigue=True)
    m.design.ermuedung_kontakt_einfrieren = False
    voll = solver.solve_cases(m, ["H4", "H5"])
    erwartet = {"H4": ("durchdringung", "gegen"), "H5": ("zug",)}
    for name, arten in erwartet.items():
        v = an.cases[name].info.get("contact_frozen_verworfen") or {}
        check(f"{name}: verworfen wegen {', '.join(arten)}",
              all(v.get(a, 0) > 0 for a in arten), str(v))
        du, dsv = _abweichung(an.cases[name], voll[name])
        check(f"{name}: nachgerechnet wie nichtlinear (sigma_v auf 1 N/mm2, u auf 1e-3)",
              an.cases[name].info.get("contact_converged") and du < 1e-3 and dsv <= 1e6,
              f"du {du:.1e}, d sigma_v {dsv / 1e6:.4f} N/mm2")
    # Ruecknahmeprobe: ohne die Pruefung bliebe H5 eingefroren - und falsch
    alt = ContactSystem.zustand_verstoesse
    ContactSystem.zustand_verstoesse = lambda self, u: {"zug": 0, "zug_max": 0.0, "durchdringung": 0,
                                                        "durchdringung_max": 0.0, "kegel": 0,
                                                        "kegel_max": 0.0, "gegen": 0}
    try:
        m2, _a, _b = _ermuedungsblock(faktoren)
        an2 = solver.solve_all(m2, combinations=False, envelopes=False, fatigue=True)
    finally:
        ContactSystem.zustand_verstoesse = alt
    du, _dsv = _abweichung(an2.cases["H5"], voll["H5"])
    check("Ruecknahme: ohne die Pruefung hiesse -1,0 H1 eingefroren und konvergiert, "
          "laege aber weit daneben",
          an2.cases["H5"].info.get("contact_frozen") and an2.cases["H5"].info.get("contact_converged")
          and du > 0.3, f"du {du:.1%}")


def test_zustand_verstoesse_je_art():
    """ContactSystem.zustand_verstoesse liest nur: Zug an einer geschlossenen,
    Durchdringung an einer offenen, Haften ueber dem Kegel, Gleiten gegen die
    Richtung - und ein Verbund darf Zug tragen."""
    from statik3d.contact import Constraint
    cs = object.__new__(ContactSystem)
    cs.f_tol, cs.tol, cs.log = 1.0, 1e-12, []

    def bed(**k):
        c = Constraint(kind="surface", dofs=np.array([0, 1, 2]), cn=np.array([0.0, 0.0, 1.0]),
                       ct=np.vstack([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), g0=0.0, kn=1e9, kt=1e9,
                       mu=k.pop("mu", 0.3), node=0, normal=np.array([0.0, 0.0, 1.0]), label="Fuge:0")
        for key, val in k.items():
            setattr(c, key, val)
        return c

    # u = (ux, uy, uz); g = uz, Fn = -kn g; |Ft| = kt |ux|; mu Fn = 0,3 * 1000 N
    faelle = [
        ("geschlossen unter Druck, haftend im Kegel", dict(active=True, slip=False), [1e-7, 0, -1e-6], {}),
        ("geschlossen unter Zug", dict(active=True, slip=False), [0, 0, 1e-6], {"zug": 1}),
        ("Verbund unter Zug", dict(active=True, slip=False, zug=True, mu=0.0), [0, 0, 1e-6], {}),
        ("offen, durchdrungen", dict(active=False), [0, 0, -1e-6], {"durchdringung": 1}),
        ("offen mit Spalt", dict(active=False), [0, 0, 1e-6], {}),
        ("haftend ueber dem Kegel", dict(active=True, slip=False), [1e-6, 0, -1e-6], {"kegel": 1}),
        ("gleitend gegen die Richtung", dict(active=True, slip=True, slip_dir=np.array([1.0, 0.0])),
         [-1e-6, 0, -1e-6], {"gegen": 1}),
    ]
    for name, zust, u, soll in faelle:
        cs.cons = [bed(**zust)]
        v = cs.zustand_verstoesse(np.array(u, float))
        ist = {k: v[k] for k in ("zug", "durchdringung", "kegel", "gegen") if v[k]}
        check(f"zustand_verstoesse: {name}", ist == soll, str(ist))
    check("zustand_verstoesse setzt nichts um", cs.cons[0].active and cs.cons[0].slip)



def _haftende_ueber_kegel(n=10, mu=0.3, kn=1.0e9, kt=1.0e9):
    """n haftende Reibknoten, alle ueber dem Coulomb-Kegel, mit verschieden
    starkem Verstoss. Rueckgabe (ContactSystem-Stumpf, u)."""
    from statik3d.contact import ContactSystem, Constraint
    cons = []
    u = np.zeros(3 * n)
    for i in range(n):
        dofs = np.array([3 * i, 3 * i + 1, 3 * i + 2])
        c = Constraint(kind="surface", dofs=dofs, cn=np.array([0.0, 0.0, 1.0]),
                       ct=np.vstack([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]),
                       g0=0.0, kn=kn, kt=kt, mu=mu, node=i,
                       normal=np.array([0.0, 0.0, 1.0]), label="Fuge:%d" % i)
        c.active, c.slip, c.Fn = True, False, 0.0
        cons.append(c)
        u[3 * i + 2] = -1.0e-6                       # Druck: Fn = kn*1e-6 = 1000 N
        # Schub ueber mu*Fn = 300 N, mit steigendem Verstoss je Knoten
        u[3 * i] = (1.0 + 0.1 * i) * 4.0e-7
    cs = object.__new__(ContactSystem)
    cs.cons, cs.phase, cs.log = cons, 2, []
    cs.f_tol, cs.tol, cs.dF_slip = 1.0, 1e-12, 0.0
    cs.f_ref = 1.0e4
    cs.gleit_anteil, cs.gleit_guete = contact.GLEIT_ANTEIL, float("inf")
    return cs, u


def test_phase2_loest_mehrere_haftende_auf_einmal():
    """Phase 2 liess je Runde nur den staerksten Verstoss ins Gleiten. Am
    Drehlager sind das bis zu 40 Runden je Lastfall, jede mit einer
    Faktorisierung von 476.214 Zeilen zu 4,23 s - 56 Kontaktschritte und 276 s
    je warmem Lastfall, davon 86 % Faktorisierung (19.09.2026).

    ama loest das seit Stufe 3 anders und geprueft: je Schritt geht hoechstens
    der Anteil `anteil` der haftenden Knoten ins Gleiten, staerkster Verstoss
    zuerst (ama.dicht.newton_reibung). Dieselbe Regel hier."""
    cs, u = _haftende_ueber_kegel(n=40)
    cs._update_states(u)
    gleiten = sum(1 for c in cs.cons if c.slip)
    check("ein Anteil der haftenden Knoten geht je Runde ins Gleiten",
          gleiten == 4, f"{gleiten} von 40, erwartet 4 (Anteil {contact.GLEIT_ANTEIL:g})")
    check("nicht alle auf einmal - die Monotonie bleibt", gleiten < 40, f"{gleiten} von 40")
    # der staerkste Verstoss muss dabei sein
    check("der staerkste Verstoss gleitet", cs.cons[-1].slip, "Knoten 39 (groesster Schub)")
    check("der schwaechste bleibt haften", not cs.cons[0].slip, "Knoten 0")



def test_gleitanteil_passt_sich_dem_guetemass_an():
    """Der feste Anteil von 10 % ist geraten. Ein semiglatter Newton misst nach
    jedem Schritt, ob das Guetemass faellt, und passt an - `qp_kegel` in ama
    macht genau das mit einer Liniensuche auf |Phi|^2 + |r|^2.

    Hier ist das Guetemass, wie weit die haftenden Knoten ueber dem Coulomb-
    Kegel liegen (Summe, bezogen auf die Kraftskala). Faellt es, darf die
    naechste Runde mehr Knoten umstellen; faellt es nicht, weniger."""
    cs, u = _haftende_ueber_kegel(n=40)
    a0 = cs.gleit_anteil
    cs._update_states(u)                       # erste Runde: Guetemass wird gesetzt
    g1 = cs.gleit_guete
    check("das Guetemass wird gemessen", g1 > 0.0, f"{g1:.3e}")

    # zweite Runde mit kleinerem Verstoss: es faellt -> der Anteil waechst
    u2 = u.copy()
    for i in range(40):
        u2[3 * i] *= 0.5
    cs._update_states(u2)
    check("faellt das Guetemass, waechst der Anteil", cs.gleit_anteil > a0,
          f"{a0:g} -> {cs.gleit_anteil:g}")
    check("aber nicht ueber die Schranke", cs.gleit_anteil <= contact.GLEIT_ANTEIL_MAX,
          f"{cs.gleit_anteil:g} <= {contact.GLEIT_ANTEIL_MAX:g}")

    # dritte Runde mit groesserem Verstoss: es steigt -> der Anteil faellt
    a2 = cs.gleit_anteil
    u3 = u.copy()
    for i in range(40):
        u3[3 * i] *= 4.0
    cs._update_states(u3)
    check("steigt das Guetemass, faellt der Anteil", cs.gleit_anteil < a2,
          f"{a2:g} -> {cs.gleit_anteil:g}")
    check("aber nicht unter die Schranke", cs.gleit_anteil >= contact.GLEIT_ANTEIL_MIN,
          f"{cs.gleit_anteil:g} >= {contact.GLEIT_ANTEIL_MIN:g}")


def _runde(cs, u):
    """Eine Runde am Stumpf: (changed, Eintrag als dict nach RUNDEN_FELDER)."""
    changed = cs._update_states(u)
    return changed, dict(zip(contact.RUNDEN_FELDER, cs.runden[-1]))


def test_runden_zaehlen_die_wechselarten():
    """Je Runde ein Zahlentupel mit den Wechselarten (Buchfuehrung, 22.09.2026).

    Der Deckel MAX_CYCLES zaehlt jede Runde mit irgendeinem Wechsel. Welche
    Art die 40 Runden am Drehlager fuellt - Oeffnen/Schliessen in Fugen, neues
    Gleiten, Fliessen -, stand nirgends. Gezaehlt werden **Ereignisse**: ein
    wieder geschlossener Reibknoten traegt Fn = 0 aus der offenen Runde und
    geht in derselben Runde ins Gleiten - das ist ein Schliessen **und** ein
    Gleiten nach Wiederschliessen, kein echter Kegelverstoss. Ein
    Oeffnungsversuch einer einfrierenden Bedingung aendert active nicht - er
    ist nur ein Einfrieren. Der Stumpf kennt kein __init__ (object.__new__):
    die Ablage muss trotzdem entstehen, sonst brechen die Stumpftests."""
    from statik3d.contact import Constraint
    cs, u = _haftende_ueber_kegel(n=40)
    check("der Stumpf hat keine Rundenablage (wie aus object.__new__)",
          not hasattr(cs, "runden"))
    changed, r = _runde(cs, u)
    check("erste Runde: Ablage angelegt, ein Eintrag", len(cs.runden) == 1, str(len(cs.runden)))
    check("40 Verstoesse bei 40 haftenden, Anteil 0,1: 4 echte neue Gleiter",
          r["verstoesse"] == 40 and r["H"] == 40 and r["gleiten_neu"] == 4
          and abs(r["a"] - contact.GLEIT_ANTEIL) < 1e-15 and r["bedingungen"] == 4,
          f"Verstoesse {r['verstoesse']}, H {r['H']}, neu {r['gleiten_neu']}, a {r['a']:g}")
    check("sonst kein Ereignis, Phase 2, und die Runde meldet einen Wechsel",
          changed and sum(r[k] for k in contact.RUNDEN_EREIGNISSE) == 4 and r["phase"] == 2,
          str({k: r[k] for k in contact.RUNDEN_EREIGNISSE if r[k]}))

    # Zweite Runde, von Hand gestellt: Bedingung 0 war offen und schliesst
    # (Fn = 0 -> Grenze 0 -> Verhaeltnis unendlich, ganz vorn), Bedingung 1
    # oeffnet, Bedingung 2 hat schon achtmal gewechselt und friert beim
    # Oeffnungsversuch ein, dazu eine reibungsfreie Bedingung, die schliesst.
    frei = Constraint(kind="surface", dofs=np.array([120, 121, 122]), cn=np.array([0.0, 0.0, 1.0]),
                      ct=None, g0=0.0, kn=1.0e9, kt=1.0e9, mu=0.0, node=40,
                      normal=np.array([0.0, 0.0, 1.0]), label="Glatt:40")
    cs.cons.append(frei)
    u2 = np.concatenate([u.copy(), [0.0, 0.0, -1.0e-6]])
    c0, c1, c2 = cs.cons[0], cs.cons[1], cs.cons[2]
    c0.active, c0.slip = False, False
    c2.toggles = 8
    u2[3 * 1 + 2] = +1.0e-6            # Bedingung 1 hebt ab: Zug 1000 N > f_tol
    u2[3 * 2 + 2] = +1.0e-6            # Bedingung 2 wollte auch abheben
    changed, r = _runde(cs, u2)
    check("Schliessen an der Reibstelle und reibungsfrei getrennt",
          r["schliessen_reib"] == 1 and r["schliessen_frei"] == 1,
          f"reib {r['schliessen_reib']}, frei {r['schliessen_frei']}")
    check("Oeffnen: nur Bedingung 1 - Bedingung 2 friert ein und bleibt zu",
          r["oeffnen_reib"] == 1 and r["oeffnen_frei"] == 0 and r["eingefroren_neu"] == 1
          and c2.active and c2.frozen and not c1.active,
          f"oeffnen {r['oeffnen_reib']}, eingefroren {r['eingefroren_neu']}")
    check("der wieder geschlossene Reibknoten gleitet - als Gleiten nach Wiederschliessen, "
          "nicht als Kegelverstoss",
          c0.slip and r["gleiten_nach_schliessen"] == 1,
          f"nach Schliessen {r['gleiten_nach_schliessen']}, neu {r['gleiten_neu']}")
    n_ereignisse = sum(r[k] for k in contact.RUNDEN_EREIGNISSE)
    check("Ereignisse und verschiedene Bedingungen werden getrennt gezaehlt",
          n_ereignisse > r["bedingungen"] >= 1,
          f"{n_ereignisse} Ereignisse an {r['bedingungen']} Bedingungen")
    check("eine Runde mit Ereignis ist genau eine, die einen Wechsel meldet",
          changed and n_ereignisse > 0)
    # Dritte Runde ohne Aenderung: kein Ereignis, kein Wechsel
    for c in cs.cons:
        c.frozen = True                 # nichts darf mehr oeffnen oder schliessen
        if c.ct is not None:
            c.slip = True               # und nichts mehr ins Gleiten gehen
            c.slip_dir = np.array([1.0, 0.0])
    changed, r = _runde(cs, u2)
    check("eine Runde ohne Wechsel hat kein Ereignis",
          not changed and sum(r[k] for k in contact.RUNDEN_EREIGNISSE) == 0,
          str({k: r[k] for k in contact.RUNDEN_EREIGNISSE if r[k]}))
    check("je Aufruf genau ein Eintrag", len(cs.runden) == 3, str(len(cs.runden)))

    # Ein gebautes System beginnt leer; initialize und zustand_setzen fangen neu an
    m, _lf1 = _modell()
    system = solver.StaticSystem(m)
    echt = ContactSystem(m, system.K, [])
    check("ein gebautes System beginnt mit leerer Ablage", echt.runden == [])
    echt.initialize()
    z = echt.zustand()
    leer = (2,) + (0,) * (len(contact.RUNDEN_FELDER) - 1)
    echt.runden.append(leer)
    echt.initialize()
    check("initialize() leert die Ablage", echt.runden == [])
    echt.runden.append(leer)
    check("zustand_setzen() leert sie ebenso", echt.zustand_setzen(z) and echt.runden == [])


def _handzustand():
    """Fuenf Bedingungen, Bits von Hand gesetzt - fuer die Kennung."""
    cs, _u = _haftende_ueber_kegel(n=5)
    for c, (a, s, y, h) in zip(cs.cons, ((1, 0, 0, 0), (1, 1, 0, 0), (0, 0, 0, 1),
                                         (1, 0, 1, 0), (1, 1, 0, 0))):
        c.active, c.slip, c.yielding, c.schub_halt = bool(a), bool(s), bool(y), bool(h)
    cs.phase = 2
    return cs


#: Die Kennung von _handzustand, einmal gerechnet (22.09.2026). Sie haengt an
#: hashlib, nicht am je Prozess gesaeten hash() - jeder Testlauf ist ein neuer
#: Prozess, und sie muss trotzdem stimmen.
HANDZUSTAND_KENNUNG = "acf4eadff1c4a21d"


def test_endzustand_kennung_ist_prozessfest():
    """Die Kennung des Endzustands eines Kontaktlaufs muss sich zwischen zwei
    Rechnungen, Prozessen und Tagen vergleichen lassen. ``signatur()`` kann das
    nicht: sie hasht mit dem eingebauten hash(), und der ist je Prozess anders
    gesaet (PYTHONHASHSEED). Gegenprobe im selben Test: ein gekipptes Bit
    aendert die Kennung, eine andere Normalkraft nicht (Fn und Gleitrichtung
    stehen nur im Lastvektor Fc)."""
    cs = _handzustand()
    k = cs.endzustand_kennung()
    check("fester Wert fuer den handgesetzten Zustand (prozessfest)",
          k == HANDZUSTAND_KENNUNG, f"{k} gegen {HANDZUSTAND_KENNUNG}")
    check("16 Hexziffern", len(k) == 16 and all(ch in "0123456789abcdef" for ch in k), k)
    for name, feld in (("aktiv", "active"), ("gleitet", "slip"), ("fliesst", "yielding"),
                       ("Schubhalt", "schub_halt")):
        cs2 = _handzustand()
        setattr(cs2.cons[0], feld, not getattr(cs2.cons[0], feld))
        check(f"ein gekipptes Bit '{name}' aendert die Kennung", cs2.endzustand_kennung() != k)
    cs3 = _handzustand()
    cs3.phase = 1
    check("eine andere Phase aendert die Kennung", cs3.endzustand_kennung() != k)
    cs4 = _handzustand()
    cs4.cons[1].Fn = 12345.0
    cs4.cons[1].slip_dir = np.array([0.0, 1.0])
    check("Normalkraft und Gleitrichtung stehen nicht darin", cs4.endzustand_kennung() == k)
    # Ueber Prozesse: dieselbe Kennung unter zwei verschiedenen Hash-Saatwerten
    import subprocess
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = ("import sys; sys.path.insert(0, %r); import tests.test_kontaktzustand as t; "
            "print(t._handzustand().endzustand_kennung())" % wurzel)
    kennungen = set()
    for saat in ("1", "4711"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env=dict(os.environ, PYTHONHASHSEED=saat), timeout=300)
        zeilen = out.stdout.strip().splitlines()
        kennungen.add(zeilen[-1] if zeilen else "Fehler: " + out.stderr[-160:])
    check("zwei Prozesse mit verschiedenem Hash-Saatwert: dieselbe Kennung",
          kennungen == {k}, str(kennungen))


def test_start_angeboten_und_genutzt():
    """Woher der Warmstart eines Lastfalls kam - angeboten und genutzt
    getrennt (22.09.2026). Angeboten ist nicht genutzt: der Warmstart kann
    verworfen werden (umgekehrte Last)."""
    m, lf1 = _modell()
    reihe = solver.solve_cases(m, [lf1, "LF2", "LF3"])
    i1, i2, i3 = reihe[lf1].info, reihe["LF2"].info, reihe["LF3"].info
    check("der erste Lastfall: nichts angeboten, nichts genutzt",
          i1.get("start_angeboten_von") is None and i1.get("start_genutzt") is False,
          f"{i1.get('start_angeboten_von')} / {i1.get('start_genutzt')}")
    check("LF2 vom Zustand von LF1, genutzt",
          i2.get("start_angeboten_von") == f"Lastfall {lf1}" and i2.get("start_genutzt") is True,
          f"{i2.get('start_angeboten_von')} / {i2.get('start_genutzt')}")
    check("LF3 vom Zustand von LF2, genutzt",
          i3.get("start_angeboten_von") == "Lastfall LF2" and i3.get("start_genutzt") is True,
          f"{i3.get('start_angeboten_von')} / {i3.get('start_genutzt')}")
    check("im Laufbuch: der angebotene Start heisst Quelle 0, kalt heisst None",
          i2["laeufe"][0]["start_von_lauf"] == 0 and i2["laeufe"][0]["warm"]
          and i1["laeufe"][0]["start_von_lauf"] is None,
          f"{i2['laeufe'][0]['start_von_lauf']} / {i1['laeufe'][0]['start_von_lauf']}")
    # Umgekehrte Last: angeboten, aber verworfen
    m.add_load_case("LF4", "Q")
    for nl in m.load_cases[lf1].nodal_loads:
        m.load_node(nl.node, Fx=-nl.F[0], Fy=nl.F[1], Fz=nl.F[2])
    i4 = solver.solve_cases(m, [lf1, "LF4"])["LF4"].info
    check("umgekehrte Last: angeboten von LF1, aber nicht genutzt (verworfen, Neustart)",
          i4.get("start_angeboten_von") == f"Lastfall {lf1}" and i4.get("start_genutzt") is False
          and i4["laeufe"][0]["neustart"] and not i4["laeufe"][0]["warm"],
          f"{i4.get('start_angeboten_von')} / {i4.get('start_genutzt')} / "
          f"Neustart {i4['laeufe'][0]['neustart']}")
    # Kombination: vom Zustand, den das System vom letzten Lastfall haelt
    m.add_combination("K", {lf1: 1.0, "LF2": 0.0}, typ="ULS")
    systeme = {}
    solver.solve_cases(m, [lf1], systeme=systeme)
    ik = solver.solve_combinations(m, ["K"], use_jobs=False, systeme=systeme)["K"].info
    check("Kombination: angeboten vom Lastfall, dessen Zustand das System haelt",
          ik.get("start_angeboten_von") == f"Lastfall {lf1}" and ik.get("start_genutzt") is True,
          f"{ik.get('start_angeboten_von')} / {ik.get('start_genutzt')}")


def test_start_beim_einfrieren_und_im_ausfallweg():
    """Eingefroren: der Start wird angeboten, aber nicht genutzt, und der
    Lauf heisst im Laufbuch 'eingefroren'. Der naechste Lastfall startet vom
    Zustand **vor** dem eingefrorenen - der hinterlaesst keinen. Im
    Ausfallweg (Zugstab mit Kontakt) wird nie ein Start weitergereicht, das
    steht als Vermerk da."""
    from statik3d.model import FatigueLoad, Section
    m = examples_lib.build_example("friction")
    lf1 = list(m.load_cases)[0]
    lasten = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    m.load_cases[lf1].nodal_loads.clear()
    for n, F in lasten:
        m.load_node(n, Fz=F[2])
    m.load_cases[lf1].grundlast = True
    # H2 = H1: der eingefrorene Zustand passt und bleibt eingefroren (seit dem
    # 22.09.2026 wird ein Zustand, der nicht passt, nachgerechnet - dann waere
    # H2 kein eingefrorener Lauf mehr; siehe test_eingefroren_nur_wenn_der_zustand_passt)
    for name, f in (("H1", 1.0), ("H2", 1.0)):
        m.add_load_case(name, "Q")
        for n, F in lasten:
            m.load_node(n, Fx=F[0] * f)
    m.fatigue_loads["E"] = FatigueLoad("E", folge=["H1", "H2"], wiederholungen=1e5)
    an = solver.solve_all(m, combinations=False, envelopes=False, fatigue=True)
    h2, g = an.cases["H2"].info, an.cases[lf1].info
    check("H2 eingefroren: angeboten von H1, nicht genutzt, im Laufbuch 'eingefroren'",
          h2.get("contact_frozen") and h2.get("start_angeboten_von") == "Lastfall H1"
          and h2.get("start_genutzt") is False and h2["laeufe"][0]["grund"] == "eingefroren",
          f"{h2.get('start_angeboten_von')} / {h2.get('start_genutzt')} / {h2['laeufe'][0]['grund']}")
    check("der Lastfall nach dem eingefrorenen startet vom Zustand davor (H1)",
          g.get("start_angeboten_von") == "Lastfall H1", str(g.get("start_angeboten_von")))

    m2 = examples_lib.build_example("friction")
    lf = list(m2.load_cases)[0]
    m2.add_load_case("LF2", "Q")
    for nl in m2.load_cases[lf].nodal_loads:
        m2.load_node(nl.node, Fx=nl.F[0] * 1.1, Fy=nl.F[1], Fz=nl.F[2])
    ecke = max(range(m2.nn), key=lambda k: tuple(m2.nodes[k][[2, 0, 1]]))
    oben = m2.add_node(float(m2.nodes[ecke][0]), float(m2.nodes[ecke][1]),
                       float(m2.nodes[ecke][2]) + 1.0)
    m2.fix(oben, "all")
    m2.add_section(Section.rectangle("Z", 0.01, 0.01))
    e = m2.add_element("truss", [ecke, oben], "S235", "Z")
    m2.elements[e].nur = "zug"
    check("Pruefmodell: Kontakt und ein Zugstab (Ausfallweg)",
          m2.has_contact and m2.hat_ausfallstaebe())
    ia = solver.solve_cases(m2, [lf, "LF2"])["LF2"].info
    check("Ausfallweg: nichts angeboten, mit Vermerk, und der Lauf ist kalt",
          ia.get("start_angeboten_von") is None and ia.get("start_genutzt") is False
          and ia.get("start_vermerk") == "Ausfallweg ohne Warmstart"
          and bool(ia.get("laeufe")) and not ia["laeufe"][0]["warm"]
          and ia["laeufe"][0]["start_von_lauf"] is None,
          f"{ia.get('start_angeboten_von')} / {ia.get('start_vermerk')}")


def test_kette_und_auftrag_stehen_im_ergebnis():
    """Zwei Wege, auf denen ein Lastfall oder eine Kombination **kalt**
    beginnt, obwohl seriell ein Warmstart angeboten wuerde (Gegenpruefung
    22.09.2026, Vorschlag 5 des Entwurfs mit der Gegenprobe): der erste
    Lastfall jeder Kette, und jede Kombination, die als eigener Auftrag
    rechnet. Ohne Angabe stuende dort nur "start_angeboten_von: None" -
    nicht zu unterscheiden von einem Fehler.

    Die Ketten laufen hier nicht in Prozessen: run_jobs wird wie in
    test_solver_ext ersetzt, geprueft wird das Einsammeln."""
    from statik3d import jobs
    import statik3d.parallel as _p
    m, lf1 = _modell()
    namen = [lf1, "LF2", "LF3"]

    class _Erg:
        def __init__(self, result):
            self.ok, self.result, self.error = True, result, ""

    def run_jobs_stub(jobs_, workers=None, progress=None):
        return [_Erg({n: solver.Results(name=n, kind="case", model=None)
                      for n in (j.payload.get("cases") or [])}) for j in jobs_]

    alt_p = _p.run_jobs
    _p.run_jobs = run_jobs_stub
    try:
        out = solver._cases_in_ketten(m, namen, 2, None, None)
    finally:
        _p.run_jobs = alt_p
    ketten = {n: out[n].info.get("kette") for n in namen if n in out}
    check("jeder Lastfall traegt (Kette, Zahl der Ketten)",
          len(ketten) == 3 and all(isinstance(k, tuple) and k[1] == 2 for k in ketten.values())
          and {k[0] for k in ketten.values()} == {1, 2}, str(ketten))

    m.add_combination("K", {lf1: 1.0, "LF2": 0.5}, typ="ULS")
    ij = jobs._job_solve_combination(m.to_dict(), "K").info
    check("Kombination als Auftrag: nichts angeboten, mit Vermerk",
          ij.get("start_angeboten_von") is None and ij.get("start_genutzt") is False
          and ij.get("start_vermerk") == "Auftrag ohne Warmstart",
          f"{ij.get('start_angeboten_von')} / {ij.get('start_vermerk')}")
    check("dieselbe Kombination seriell hat keinen solchen Vermerk",
          "start_vermerk" not in solver.solve_combination(m, m.combinations["K"]).info)


def main():
    for t in (test_sicherung, test_warmstart, test_warmstart_ohne_halt, test_fortschritt_kontakt,
              test_grundlast, test_einfrieren, test_eingefroren_nur_wenn_der_zustand_passt,
              test_zustand_verstoesse_je_art,
              test_phase2_loest_mehrere_haftende_auf_einmal,
              test_gleitanteil_passt_sich_dem_guetemass_an,
              test_runden_zaehlen_die_wechselarten,
              test_endzustand_kennung_ist_prozessfest,
              test_start_angeboten_und_genutzt,
              test_start_beim_einfrieren_und_im_ausfallweg,
              test_kette_und_auftrag_stehen_im_ergebnis):
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
