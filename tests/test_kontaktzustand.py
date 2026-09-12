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

from statik3d import solver, examples_lib  # noqa: E402
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
    # warm duerfen sich in der Verteilung unterscheiden, im Gleichgewicht nicht
    check("warm: dieselbe Loesung wie kalt (LF2, Verschiebungen auf 1e-3)",
          float(np.abs(warm2.u - kalt2.u).max()) < 1e-3 * u_ref,
          f"Abweichung {float(np.abs(warm2.u - kalt2.u).max()) / u_ref:.1e}")
    check("warm: dieselben Auflagerkraefte (LF2)",
          np.allclose(warm2.reactions.sum(axis=0), kalt2.reactions.sum(axis=0), rtol=1e-9, atol=1e-6))
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


def test_einfrieren():
    """Die Zustaende einer Ermuedungslast: der erste nichtlinear, die weiteren
    mit seinem eingefrorenen Kontaktzustand linear - eine Rueckwaerts-
    einsetzung je Zustand, keine Faktorisierung. Am Block mit Reibung
    (Auflast als Grundlast): Zustand H2 = 1,1 H1."""
    from statik3d.model import FatigueLoad
    m = examples_lib.build_example("friction")
    lf1 = list(m.load_cases)[0]
    lasten = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    m.load_cases[lf1].nodal_loads.clear()
    for n, F in lasten:
        m.load_node(n, Fz=F[2])
    m.load_cases[lf1].grundlast = True
    for name, f in (("H1", 1.0), ("H2", 1.1)):
        m.add_load_case(name, "Q")
        for n, F in lasten:
            m.load_node(n, Fx=F[0] * f)
    m.fatigue_loads["E"] = FatigueLoad("E", folge=["H1", "H2"], wiederholungen=1e5)
    check("Referenzen: H2 friert den Zustand von H1 ein, H1 bleibt nichtlinear",
          solver.ermuedungsreferenzen(m) == {"H2": "H1"}, str(solver.ermuedungsreferenzen(m)))
    an = solver.solve_all(m, combinations=False, envelopes=False, fatigue=True)
    h1, h2 = an.cases["H1"], an.cases["H2"]
    folge = list(an.cases)
    check("Reihenfolge: H2 unmittelbar nach seiner Referenz H1 (die Faktorisierung bleibt), "
          "der Grundlastfall danach",
          folge.index("H2") == folge.index("H1") + 1 and folge.index(lf1) > folge.index("H2"), str(folge))
    check("_mit_referenzen_zuerst: Referenz, ihre Zustaende, dann der Rest",
          solver._mit_referenzen_zuerst(["A", "B", "C", "D", "E"], {"C": "B", "E": "B", "D": "A"})
          == ["A", "D", "B", "C", "E"])
    check("H1 nichtlinear (Kontakt-Iteration), H2 eingefroren: 1 Schritt, 0 Faktorisierungen",
          not h1.info.get("contact_frozen") and h1.info.get("contact_iterations", 0) > 1
          and h2.info.get("contact_frozen") and h2.info.get("contact_frozen_from") == "H1"
          and h2.info.get("contact_iterations") == 1 and h2.info.get("contact_factorisations") == 0,
          f"H1 {h1.info.get('contact_iterations')} Schritte, H2 {h2.info.get('contact_iterations')} / "
          f"{h2.info.get('contact_factorisations')}")
    check("eingefroren: Gleichgewicht (Auflager = Last)",
          abs(h2.reactions[:, 0].sum() + 1.1 * sum(F[0] for _n, F in lasten)) < 1e-6 * abs(sum(F[0] for _n, F in lasten)),
          f"Rx = {h2.reactions[:, 0].sum():.1f} N")
    m.design.ermuedung_kontakt_einfrieren = False
    check("ausgeschaltet: keine Referenzen", solver.ermuedungsreferenzen(m) == {})
    voll = solver.solve_cases(m, ["H2"])["H2"]
    u_ref = float(np.abs(voll.u).max())
    abw = float(np.abs(h2.u - voll.u).max()) / u_ref
    check("eingefroren gegen nichtlinear (H2 = 1,1 H1): Verschiebungen auf 10 % gleich",
          abw < 0.10 and not voll.info.get("contact_frozen"), f"Abweichung {abw:.1%}")
    check("Analyse nennt die eingefrorenen Zustaende, Ermuedung wurde gefuehrt",
          an.info.get("kontakt_eingefroren") == {"H2": "H1"} and an.fatigue is not None)


def main():
    for t in (test_sicherung, test_warmstart, test_warmstart_ohne_halt, test_fortschritt_kontakt,
              test_grundlast, test_einfrieren):
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
