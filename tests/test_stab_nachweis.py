"""
Stab mit Nachweis: Zusammenfassen, leere Staebe, Teilen und Kettenwarnung
(Plan-Teilpaket C14, Nachbesserung Runde 2 vom 03.10.2026).

Die Nachpruefung von 61c025b fand drei Fehler beim Zusammenfassen, Luecken
beim leeren Stab und eine flutende Kettenwarnung. Die Abnahme A1 bis A18 ist
vorher festgelegt (scratchpad/c14stab_pruef2/NACHBESSERUNG-C14-RUNDE2.md); die
Faelle und Zahlen stammen aus deren Pruefskripten (pruef_modell.py,
pruef_gui2.py, pruef_extra.py) und sind dort gemessen. Gepruefte Grundsaetze:

* G1: „Stäbe zusammenfassen“ verliert nichts und aendert keine Bedeutung - es
  weist ab und nennt jeden Grund mit Stab und Wert (feste Knicklaengen,
  verschiedene Nachweisparameter, „aus“, verschiedene Vorspannungen,
  Linienlasten, die nicht verlustfrei mitgehen, Verweise auf irgendeinen Stab
  der Kette); sonst rechnet der Stab wie ein von vornherein ganzer (A1 bis A7);
* G1 lockerer (Nachtrag 04.10.2026, Entscheidung des Anwenders): verschiedene
  Linienlasten gehen mit, jede auf dem Abschnitt, auf dem sie vorher lag; die
  Elementlasten jedes Elements bleiben, Auflagerkraefte und Verschiebungen
  auch (L1 bis L8);
* G2: ein leerer Stab ist im EC3-Nachweis, in der Web-Ampel, in der Ermuedung
  und im Bericht als nicht nachgewiesen sichtbar (A8, A9);
* G3: Zusammenfassen, Teilen und „Stab“ um ein vorhandenes Element verwerfen
  die Ergebnisse wie jede andere Modellaenderung (A10);
* G4: Teilen erhaelt die Linienlasten des Stabs sofort (A11);
* G5: die Kettenwarnung ist genau (Lager je Ausweichrichtung, Glieder ohne
  Nachweis, feste Knicklaengen, Querschnitte) und flutet nicht (einmal je
  Kette, Etikett hoechstens 8 Zeilen) (A12 bis A16); H-4 (A17).

A18 (Beispiele gegen e4a3c90) laeuft als Skript der Nachpruefung
(beispiele_dump.py, beispiele_vergleich.py), weil die Vergleichsdaten
ausserhalb des Projekts liegen.

Aufruf:  python -m tests.test_stab_nachweis
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_stabnachweis_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: das Modell des Anwenders mit 648 Staeben (A16); fehlt es, entfaellt diese Pruefung
CBG = os.environ.get("STATIK3D_CBG", os.path.join(os.path.expanduser("~"), "Desktop", "Statik3D", "cbg.json"))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# ---------------------------------------------------------------------------
# Modelle (wie in pruef_modell.py der Nachpruefung)
# ---------------------------------------------------------------------------
def stuetze(n=3, h=6.0, sec="HEB 200", Lcr=None, m=None):
    """Stuetze 6 m aus n Staeben, unten eingespannt, oben seitlich gehalten,
    600 kN Druck und 5 kN quer, Kombinationen nach EN 1990 (``m``: in dieses
    Modell, etwa das des Fensters)."""
    from statik3d.model import Model, Material, Section
    from statik3d.combinations import generate_combinations
    m = m if m is not None else Model("Stuetze")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile(sec))
    for i in range(n + 1):
        m.add_node(0, 0, h * i / n)
    m.support(0, "all")
    m.support(n, [0, 1])
    g = next(iter(m.load_cases))
    m.load_node(n, Fz=-600e3, Fx=5e3, case=g)
    for i in range(n):
        e = m.add_element("beam", [i, i + 1], "S355", sec)
        kw = {"Lcr_y": Lcr, "Lcr_z": Lcr} if Lcr is not None else {}
        m.add_member(f"S{i + 1}", [e], **kw)
    generate_combinations(m)
    return m, g


def eta(an):
    return {k: (round(float(x.util), 6), round(float(x.L), 6)) for k, x in an.design.members.items()}


def du_max(a, b):
    import numpy as np
    return max(float(np.max(np.abs(a.cases[k].u - b.cases[k].u))) for k in a.cases)


def zustand(m):
    """Was das Zusammenfassen anfassen wuerde - zum Vergleich vorher/nachher."""
    from dataclasses import asdict
    return ({k: asdict(v) for k, v in m.members.items()},
            {k: [(ll.ziel, ll.von, ll.bis) for ll in lc.linienlasten] for k, lc in m.load_cases.items()},
            {k: [(v.ziel, v.kraft) for v in (getattr(lc, "vorspannungen", None) or [])]
             for k, lc in m.load_cases.items()})


def abgewiesen(m, namen=("S1", "S2", "S3")):
    """(Grund, Modell unveraendert) eines Zusammenfassens, das abgewiesen werden soll."""
    vor = zustand(m)
    try:
        m.staebe_zusammenfassen(list(namen))
    except ValueError as ex:
        return str(ex), zustand(m) == vor
    return "", zustand(m) == vor


# ---------------------------------------------------------------------------
# G1: Zusammenfassen
# ---------------------------------------------------------------------------
def test_a1_feste_knicklaengen():
    from statik3d import solver
    m, g = stuetze(Lcr=12.0)
    an0 = solver.solve_all(m, design=True)
    grund, gleich = abgewiesen(m)
    an1 = solver.solve_all(m, design=True)
    check("A1 Lcr_y = Lcr_z = 12 m an allen: abgewiesen, Grund nennt S1, S2, S3 und 12 m",
          all(f"{s}: feste Knicklänge" in grund for s in ("S1", "S2", "S3")) and "Lcr_y = 12 m" in grund
          and "erst auf β·L zurücksetzen" in grund, grund[:160])
    check("A1 … Modell unverändert, Ausnutzung bleibt 3,591763",
          gleich and eta(an0) == eta(an1) == {f"S{i}": (3.591763, 2.0) for i in (1, 2, 3)}, str(eta(an1)))


def test_a2_eine_feste_knicklaenge():
    m, g = stuetze()
    m.members["S2"].Lcr_z = 1.0
    grund, gleich = abgewiesen(m)
    check("A2 nur S2 Lcr_z = 1 m: abgewiesen, Grund nennt S2", "S2: feste Knicklänge Lcr_z = 1 m" in grund
          and "S1:" not in grund and gleich, grund[:160])


def test_a3_parameter_verschieden():
    from statik3d import solver
    m, g = stuetze()
    m.members["S2"].detail_category = 71e6
    m.members["S3"].beta_z = 0.7
    m.add_fatigue_load("F", g, None, 1e6)
    an0 = solver.solve_all(m, design=True, fatigue=True)
    grund, gleich = abgewiesen(m)
    an1 = solver.solve_all(m, design=True, fatigue=True)
    check("A3 S2 Kerbfall 71, S3 β_z 0,7: abgewiesen, Grund nennt beide Unterschiede mit Wert",
          "Kerbfall" in grund and "S2 71 N/mm²" in grund and "β_z" in grund and "S3 0,7" in grund and gleich,
          grund[:200])
    d0, d1 = an0.fatigue.members["S2"].util, an1.fatigue.members["S2"].util
    check("A3 … Ermüdung D = 0,634 bleibt", round(d0, 3) == round(d1, 3) == 0.634, f"{d0:.4f} / {d1:.4f}")


def test_a4_gleiche_parameter():
    m, g = stuetze()
    for s in m.members.values():
        s.detail_category = 71e6
    try:
        name, _h = m.staebe_zusammenfassen(["S1", "S2", "S3"])
    except ValueError as ex:
        name = ""
        print("    ", ex)
    check("A4 alle drei Kerbfall 71, sonst gleich: zusammengefasst, Kerbfall 71 bleibt",
          name == "S1" and list(m.members) == ["S1"] and m.members["S1"].detail_category == 71e6,
          str({k: (v.elements, v.detail_category) for k, v in m.members.items()}))


def test_a5_aus():
    for s in ("S2", "S1"):
        m, g = stuetze()
        m.members[s].aus = True
        grund, gleich = abgewiesen(m)
        check(f"A5 {s} aus = True: abgewiesen, Grund nennt „deaktiviert“ mit {s}",
              "deaktiviert" in grund and f"{s} ja" in grund and gleich, grund[:160])


def test_a6_verweise_und_vorspannung():
    from statik3d.bridges.positions import Stellung
    m, g = stuetze()
    m.stellungen = [Stellung("P1", staebe_aus=["S1"])]
    grund, gleich = abgewiesen(m)
    check("A6 Stellung P1 mit staebe_aus = [S1] (erster Stab): abgewiesen, nennt „Stellung P1“",
          "S1 wird verwendet von Stellung P1" in grund and gleich, grund[:160])
    m, g = stuetze()
    m.add_verformungsgrenze("V1", art="stab", stab="S1", groesse="ux", wert=300.0)
    grund, gleich = abgewiesen(m)
    check("A6 Verformungsnachweis V1 auf S1: abgewiesen, nennt ihn",
          "S1 wird verwendet von Verformungsnachweis V1" in grund and gleich, grund[:160])
    m, g = stuetze()
    m.add_vorspannung("S1", 50e3, case=g)
    grund, gleich = abgewiesen(m)
    check("A6 Vorspannung nur an S1: abgewiesen, nennt die Vorspannung",
          "Vorspannung 50 kN" in grund and "S1" in grund and gleich, grund[:200])


def test_a7_ohne_unterschiede():
    from statik3d import solver
    m, g = stuetze()
    an0 = solver.solve_all(m, design=True)
    name, _h = m.staebe_zusammenfassen(["S1", "S2", "S3"])
    an1 = solver.solve_all(m, design=True)
    ref, _g = stuetze()
    ref.members.clear()
    ref.add_member("S1", [0, 1, 2])
    an_r = solver.solve_all(ref, design=True)
    check("A7 Kette ohne Verweise und Unterschiede: zusammengefasst, Verschiebungen gleich (max|du| = 0)",
          name == "S1" and du_max(an0, an1) == 0.0, f"max|du| = {du_max(an0, an1):.3e}")
    check("A7 … Nachweis wie ein von vornherein ganzer Stab: 1,075798 bei L = 6 m",
          eta(an1) == eta(an_r) == {"S1": (1.075798, 6.0)}
          and an1.design.members["S1"].governing == an_r.design.members["S1"].governing, str(eta(an1)))
    # gleiche Linienlasten und Vorspannungen gehen mit, die Rechnung bleibt
    m, g = stuetze()
    for s in ("S1", "S2", "S3"):
        m.add_linienlast(s, [2e3, 0, 0], von=0.5, bis=1.5, case=g)
        m.add_vorspannung(s, 20e3, case=g)
    m.lasten_verteilen()
    an0 = solver.solve_all(m, design=False)
    name, _h = m.staebe_zusammenfassen(["S1", "S2", "S3"])
    an1 = solver.solve_all(m, design=False)
    lasten = [(ll.ziel, ll.von, ll.bis) for ll in m.load_cases[g].linienlasten]
    vsp = [(v.ziel, v.kraft) for v in m.load_cases[g].vorspannungen]
    check("A7 … gleiche Linienlasten und Vorspannungen an allen: mitgenommen, Rechnung gleich",
          lasten == [("S1", 0.5, 1.5), ("S1", 2.5, 3.5), ("S1", 4.5, 5.5)] and vsp == [("S1", 20e3)]
          and du_max(an0, an1) <= 1e-12 * max(1e-30, float(abs(an0.cases[g].u).max())),
          f"{lasten} {vsp} max|du| = {du_max(an0, an1):.3e}")


# ---------------------------------------------------------------------------
# Nachtrag 04.10.2026: verschiedene Linienlasten gehen verlustfrei mit (L1 bis L8)
# ---------------------------------------------------------------------------
def traeger(n=2, L=3.0, m=None, kerbfall=None):
    """Gelenkig gelagerter Traeger IPE 300 aus n Staeben je L m. Jeder Stab
    hat zwei Elemente (L/3 und 2L/3), damit eine Abschnittslast auch ein
    Element im Inneren des Stabs trifft. Lasten setzt der Aufrufer, danach
    :func:`fertig`."""
    from statik3d.model import Model, Material, Section
    m = m if m is not None else Model("Traeger")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 300"))
    xs = [0.0] + [x for i in range(n) for x in (i * L + L / 3, (i + 1) * L)]
    for x in xs:
        m.add_node(x, 0, 0)
    m.support(0, [0, 1, 2, 3])
    m.support(len(xs) - 1, [1, 2])
    g = next(iter(m.load_cases))
    for i in range(n):
        e = [m.add_element("beam", [2 * i + k, 2 * i + k + 1], "S355", "IPE 300") for k in (0, 1)]
        m.add_member(f"S{i + 1}", e, detail_category=kerbfall)
    return m, g


def fertig(m):
    from statik3d.combinations import generate_combinations
    m.lasten_verteilen()
    generate_combinations(m)
    return m


def elementlasten(m):
    """Die Elementlasten je Lastfall: (Element, q, System, q2, a, b)."""
    return {k: sorted(((int(l.elem), tuple(map(float, l.q)), l.system,
                        None if l.q2 is None else tuple(map(float, l.q2)), float(l.a),
                        None if l.b is None else float(l.b)) for l in lc.beam_loads),
                      key=lambda t: (t[0], t[2], t[4]))
            for k, lc in m.load_cases.items()}


def abweichung(a, b):
    """Groesste Abweichung zweier :func:`elementlasten` (N/m und m); unendlich,
    wenn Zahl, Element, System oder „bis zum Elementende“ verschieden sind."""
    import math
    if a.keys() != b.keys():
        return math.inf
    d = 0.0
    for k in a:
        if len(a[k]) != len(b[k]):
            return math.inf
        for x, y in zip(a[k], b[k]):
            if (x[0], x[2], x[3] is None, x[5] is None) != (y[0], y[2], y[3] is None, y[5] is None):
                return math.inf
            paare = list(zip(x[1], y[1])) + list(zip(x[3] or (), y[3] or ())) + [(x[4], y[4])]
            if x[5] is not None:
                paare.append((x[5], y[5]))
            d = max([d] + [abs(p - q) for p, q in paare])
    return d


def linienlasten(m, g):
    return [(ll.ziel, ll.von, ll.bis) for ll in m.load_cases[g].linienlasten]


def zusammenfassen(m, namen):
    """(Name, Hinweise) - oder ("", [Grund]), wenn abgewiesen."""
    try:
        return m.staebe_zusammenfassen(list(namen))
    except ValueError as ex:
        return "", [str(ex)]


def rechnung_gleich(an0, an1, g):
    """(max|du|, |u|max, |ΔR|, |R|) im Lastfall g - R die Summe der Auflagerkraefte."""
    import numpy as np
    u0, u1 = np.asarray(an0.cases[g].u, float), np.asarray(an1.cases[g].u, float)
    R0 = np.asarray(an0.cases[g].reactions, float).reshape(-1, 6).sum(axis=0)
    R1 = np.asarray(an1.cases[g].reactions, float).reshape(-1, 6).sum(axis=0)
    return (float(np.max(np.abs(u1 - u0))), float(np.max(np.abs(u0))),
            float(np.max(np.abs(R1 - R0))), float(np.max(np.abs(R0))))


def _rechnung_ok(r):
    du, u, dR, R = r
    return u > 0 and R > 0 and du <= 1e-9 * u and dR <= 1e-9 * R


def test_l1_verschiedene_linienlasten():
    from statik3d import solver
    m, g = traeger()
    m.add_linienlast("S1", [0, 0, -5e3], case=g)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    fertig(m)
    b0, an0 = elementlasten(m), solver.solve_all(m, design=False)
    name, hinweise = zusammenfassen(m, ["S1", "S2"])
    lasten = linienlasten(m, g)
    check("L1 S1 −5 kN/m, S2 −9 kN/m: zusammengefasst, jede Last auf ihrem Abschnitt (0–3 m, 3–6 m)",
          name == "S1" and list(m.members) == ["S1"] and m.members["S1"].elements == [0, 1, 2, 3]
          and lasten == [("S1", 0.0, 3.0), ("S1", 3.0, 6.0)], f"{lasten} {hinweise}"[:200])
    d = abweichung(b0, elementlasten(m))
    check("L1 … Elementlasten jedes Elements gleich wie vorher", name == "S1" and d <= 1e-9,
          f"größte Abweichung {d:.3e}")
    r = rechnung_gleich(an0, solver.solve_all(m, design=False), g) if name else (1.0, 0.0, 1.0, 0.0)
    check("L1 … Summe der Auflagerkräfte und max|du| gleich (≤ 1e-9 relativ)", _rechnung_ok(r),
          "max|du| = {:.3e} bei |u|max {:.3e}, |ΔR| = {:.3e} bei |R| {:.3e}".format(*r))


def test_l2_last_nur_auf_dem_mittleren():
    from statik3d import solver
    m, g = traeger(n=3)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    fertig(m)
    b0, an0 = elementlasten(m), solver.solve_all(m, design=False)
    name, hinweise = zusammenfassen(m, ["S1", "S2", "S3"])
    lasten = linienlasten(m, g)
    b1 = elementlasten(m)
    check("L2 drei Stäbe, Last nur auf S2: zusammengefasst, Last nur auf dem mittleren Abschnitt 3–6 m",
          name == "S1" and lasten == [("S1", 3.0, 6.0)]
          and sorted({x[0] for x in b1[g]}) == [2, 3] and abweichung(b0, b1) <= 1e-9,
          f"{lasten} Elemente {sorted({x[0] for x in b1[g]})} {hinweise}"[:200])
    r = rechnung_gleich(an0, solver.solve_all(m, design=False), g) if name else (1.0, 0.0, 1.0, 0.0)
    check("L2 … Rechnung gleich (≤ 1e-9 relativ)", _rechnung_ok(r),
          "max|du| = {:.3e} bei |u|max {:.3e}, |ΔR| = {:.3e} bei |R| {:.3e}".format(*r))


def test_l3_lastarten():
    """Jede Art der Linienlast am Stab: was verlustfrei geht, geht mit; was
    nicht, wird mit Grund abgewiesen und laesst das Modell unveraendert."""
    import numpy as np
    from statik3d import solver

    def mitnehmen(titel, lasten_setzen, erwartet, rollen=0.0):
        m, g = traeger()
        for e in m.elements:
            e.roll = rollen
        lasten_setzen(m, g)
        fertig(m)
        b0, an0 = elementlasten(m), solver.solve_all(m, design=False)
        name, hinweise = zusammenfassen(m, ["S1", "S2"])
        lasten = [(ll.ziel, ll.von, ll.bis, ll.system, None if ll.q2 is None else ll.q2[2] / 1e3)
                  for ll in m.load_cases[g].linienlasten]
        d = abweichung(b0, elementlasten(m))
        r = rechnung_gleich(an0, solver.solve_all(m, design=False), g) if name else (1.0, 0.0, 1.0, 0.0)
        check(f"L3 {titel}: verlustfrei zusammengefasst", name == "S1" and lasten == erwartet
              and d <= 1e-9 and _rechnung_ok(r),
              f"{lasten} Abw. {d:.1e} max|du| {r[0]:.1e} {hinweise}"[:200])

    def abweisen(titel, lasten_setzen, teile):
        m, g = traeger()
        lasten_setzen(m, g)
        fertig(m)
        grund, gleich = abgewiesen(m, ("S1", "S2"))
        check(f"L3 {titel}: abgewiesen, der Grund nennt Stab und Wert, Modell unverändert",
              grund and all(t in grund for t in teile) and gleich, grund[:220])

    mitnehmen("Trapezlast über S1 (−5 … −9 kN/m bis zum Ende), gleichmäßige Last über S2",
              lambda m, g: (m.add_linienlast("S1", [0, 0, -5e3], q2=[0, 0, -9e3], case=g),
                            m.add_linienlast("S2", [0, 0, -9e3], case=g)),
              [("S1", 0.0, 3.0, "global", -9.0), ("S1", 3.0, 6.0, "global", None)])
    mitnehmen("Trapezlast auf einem Abschnitt von S2 (0,5–2,5 m), gleichmäßige auf S1",
              lambda m, g: (m.add_linienlast("S1", [0, 0, -5e3], case=g),
                            m.add_linienlast("S2", [0, 0, -2e3], q2=[0, 0, -8e3], von=0.5, bis=2.5, case=g)),
              [("S1", 0.0, 3.0, "global", None), ("S1", 3.5, 5.5, "global", -8.0)])
    mitnehmen("Last im lokalen System auf S2 (Elemente um 10° gedreht), globale auf S1",
              lambda m, g: (m.add_linienlast("S1", [0, 0, -5e3], case=g),
                            m.add_linienlast("S2", [0, 3e3, -9e3], system="local", case=g)),
              [("S1", 0.0, 3.0, "global", None), ("S1", 3.0, 6.0, "local", None)], rollen=np.radians(10.0))
    mitnehmen("gleichmäßige Last auf S1 mit „bis“ 5 m über das Stabende (3 m) hinaus",
              lambda m, g: (m.add_linienlast("S1", [0, 0, -5e3], von=1.0, bis=5.0, case=g),
                            m.add_linienlast("S2", [0, 0, -9e3], case=g)),
              [("S1", 1.0, 3.0, "global", None), ("S1", 3.0, 6.0, "global", None)])
    abweisen("Trapezlast auf S1 mit „bis“ 5 m über das Stabende (3 m) hinaus",
             lambda m, g: m.add_linienlast("S1", [0, 0, -5e3], q2=[0, 0, -9e3], bis=5.0, case=g),
             ("S1", "trapezförmig", "bis 5 m", "3 m"))
    abweisen("Linienlast auf S1 ganz außerhalb des Stabs (ab 4 m, Stab 3 m)",
             lambda m, g: m.add_linienlast("S1", [0, 0, -5e3], von=4.0, case=g),
             ("S1", "außerhalb", "von 4 m"))


def test_l4_vorspannung():
    m, g = traeger()
    m.add_linienlast("S1", [0, 0, -5e3], case=g)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    m.add_vorspannung("S1", 50e3, case=g)
    fertig(m)
    grund, gleich = abgewiesen(m, ("S1", "S2"))
    check("L4 S1 Vorspannung 50 kN, S2 keine: weiter abgewiesen, Grund nennt beide, Modell unverändert",
          "Vorspannung 50 kN" in grund and "S1" in grund and "S2 keine" in grund
          and "Linienlast" not in grund and gleich, grund[:200])


def test_l5_gleiche_linienlast():
    from statik3d import solver
    m, g = traeger(n=3)
    for s in ("S1", "S2", "S3"):
        m.add_linienlast(s, [0, 0, -5e3], case=g)
    fertig(m)
    b0, an0 = elementlasten(m), solver.solve_all(m, design=False)
    name, hinweise = zusammenfassen(m, ["S1", "S2", "S3"])
    lasten = linienlasten(m, g)
    r = rechnung_gleich(an0, solver.solve_all(m, design=False), g)
    check("L5 gleiche Linienlast an allen drei Stäben: wie bisher zusammengefasst, max|du| = 0",
          name == "S1" and lasten == [("S1", 0.0, 3.0), ("S1", 3.0, 6.0), ("S1", 6.0, 9.0)]
          and abweichung(b0, elementlasten(m)) <= 1e-9 and r[0] == 0.0,
          f"{lasten} max|du| = {r[0]:.3e} {hinweise}"[:200])


def _l1_im_fenster():
    w, app = _fenster()
    w.new_model()
    m, g = traeger(m=w.model)
    m.add_linienlast("S1", [0, 0, -5e3], case=g)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    fertig(m)
    w.refresh_all()
    app.processEvents()
    return w, app, g


def test_l6_rueckgaengig():
    from dataclasses import asdict
    w, app, g = _l1_im_fenster()

    def stand(m):
        return ({k: asdict(v) for k, v in m.members.items()},
                {k: [asdict(ll) for ll in lc.linienlasten] for k, lc in m.load_cases.items()},
                elementlasten(m))
    vorher = stand(w.model)
    name = w.staebe_zusammenfassen(["S1", "S2"])
    app.processEvents()
    zusammen = list(w.model.members)
    w.undo()
    app.processEvents()
    check("L6 Rückgängig nach L1: Stäbe S1, S2 und ihre Linienlasten exakt wieder da",
          name == "S1" and zusammen == ["S1"] and stand(w.model) == vorher,
          f"{zusammen} -> {sorted(w.model.members)} {linienlasten(w.model, g)}")


def test_l7_speichern_laden():
    from statik3d.model import Model
    m, g = traeger()
    m.add_linienlast("S1", [0, 0, -5e3], case=g)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    fertig(m)
    b0 = elementlasten(m)
    name, _h = zusammenfassen(m, ["S1", "S2"])
    pfad = os.path.join(tempfile.mkdtemp(prefix="stabnachweis_l7_"), "l1.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    check("L7 Speichern und Laden nach L1: dieselben Linienlasten und Elementlasten",
          name == "S1" and linienlasten(m2, g) == linienlasten(m, g) == [("S1", 0.0, 3.0), ("S1", 3.0, 6.0)]
          and elementlasten(m2) == elementlasten(m) and abweichung(b0, elementlasten(m2)) <= 1e-9,
          f"{linienlasten(m2, g)} Abw. {abweichung(b0, elementlasten(m2)):.1e}")


def test_l8_nachweise():
    from statik3d import solver
    m, g = traeger(kerbfall=71e6)
    m.add_linienlast("S1", [0, 0, -5e3], case=g)
    m.add_linienlast("S2", [0, 0, -9e3], case=g)
    m.add_fatigue_load("F", g, None, 1e6)
    fertig(m)
    name, hinweise = zusammenfassen(m, ["S1", "S2"])
    an1 = solver.solve_all(m, design=True, fatigue=True)
    # von vornherein ein Stab mit denselben Abschnittslasten
    ref, _g = traeger(kerbfall=71e6)
    ref.members.clear()
    ref.add_member("S1", [0, 1, 2, 3], detail_category=71e6)
    ref.add_linienlast("S1", [0, 0, -5e3], von=0.0, bis=3.0, case=g)
    ref.add_linienlast("S1", [0, 0, -9e3], von=3.0, case=g)
    ref.add_fatigue_load("F", g, None, 1e6)
    fertig(ref)
    an_r = solver.solve_all(ref, design=True, fatigue=True)
    e1, e_r = eta(an1), eta(an_r)
    check("L8 EC3 nach L1 wie ein von vornherein ganzer Stab mit denselben Abschnittslasten (L = 6 m)",
          name == "S1" and e1 == e_r and e1["S1"][1] == 6.0
          and an1.design.members["S1"].governing == an_r.design.members["S1"].governing,
          f"{e1} / {e_r} {hinweise}"[:200])
    f1 = an1.fatigue.members["S1"].util if name else None
    f_r = an_r.fatigue.members["S1"].util
    check("L8 Ermüdung nach L1 wie beim ganzen Stab (Kerbfall 71)",
          f1 is not None and round(f1, 9) == round(f_r, 9) and f_r > 0, f"D = {f1} / {f_r}")


# ---------------------------------------------------------------------------
# G2: leerer Stab
# ---------------------------------------------------------------------------
def rahmen_leer(kerbfall=None):
    """Rahmen aus pruef_modell.py: S2 verliert sein Element (wie Entf am Stabelement)."""
    from statik3d.model import Model, Material, Section
    from statik3d.combinations import generate_combinations
    m = Model("Rahmen")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    for x in ((0, 0, 0), (0, 0, 4), (6, 0, 4), (6, 0, 0)):
        m.add_node(*x)
    m.support(0, "all")
    m.support(3, "all")
    m.load_cases.clear()
    m.add_load_case("G", "G")
    m.add_load_case("Q", "Q")
    m.load_node(1, Fx=15e3, case="Q")
    m.load_node(2, Fz=-60e3, case="G")
    e = [m.add_element("beam", ab, "S355", "HEB 300") for ab in ([0, 1], [1, 2], [2, 3], [1, 2])]
    kf = kerbfall or {}
    for i, s in ((0, "S1"), (1, "S2"), (2, "S3")):
        m.add_member(s, [e[i]], detail_category=kf.get(s))
    m.add_fatigue_load("Spiel", "Q", None, 2e6)
    generate_combinations(m)
    m.elemente_loeschen([e[1]])
    return m


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_a8_leerer_stab_ermuedung():
    from statik3d import solver
    from statik3d.report import write_report
    tmp = tempfile.mkdtemp(prefix="stabnachweis_a8_")
    for titel, kf, design in (("alle drei mit Kerbfall", {"S1": 71e6, "S2": 71e6, "S3": 71e6}, True),
                              ("nur S2 mit Kerbfall", {"S2": 71e6}, True),
                              ("nur S2, nur Ermüdung gerechnet", {"S2": 71e6}, False)):
        m = rahmen_leer(kf)
        an = solver.solve_all(m, design=design, fatigue=True)
        s = an.fatigue.summary()
        tabelle = " ".join(" ".join(z) for z in an.fatigue.table())
        check(f"A8 leerer S2, {titel}: Ermüdung nennt S2 als nicht nachgewiesen",
              "nicht geführt: Stab S2" in s and "keine Stäbe oder Volumen mit Kerbfall" not in s
              and "S2 hat kein Stabelement – Ermüdung nicht nachgewiesen" in tabelle, s)
        pfad = os.path.join(tmp, f"{len(kf)}{design}.html")
        write_report(m, an, pfad)
        t = _text(open(pfad, encoding="utf-8").read())
        urteil = re.search(r"nicht geführt wurden:[^.]{0,160}", t)
        check(f"A8 … der Bericht zählt die Ermüdung als nicht geführt ({titel})",
              urteil is not None and "(Ermüdung)" in urteil.group(0), urteil.group(0) if urteil else t[:120])


def test_a9_leerer_stab_ec3():
    from statik3d import solver
    from statik3d.web import server as srv
    m = rahmen_leer()
    an = solver.solve_all(m, design=True)
    s = an.design.summary()
    # Positiv (11c, Gegenpruefung 03.10.2026): bis dahin "alle erfuellt" not in s,
    # seit den Umlauten immer wahr
    check("A9 leerer Stab, EC3: die Zeile endet mit „ - 1 nicht geführt: S2 (kein Stabelement …)“",
          s.splitlines()[0].endswith(") - 1 nicht geführt: S2 (kein Stabelement – Stab löschen oder neu zeichnen)"), s)
    from statik3d.ec3.design import check_members
    s_ohne = check_members(m, an, members=["S1", "S3"], use_jobs=False).summary().splitlines()[0]
    check("A9 Gegenstück: ohne S2 endet dieselbe Zeile auf „ - alle erfüllt“",
          s_ohne.startswith("Nachweise EC3: 2 Stäbe, ") and s_ohne.endswith(" m) - alle erfüllt"), s_ohne)
    st = srv.State(m)
    st.analysis = an
    pl = srv.design_payload(st)["design"]
    check("A9 … Web-Ampel nicht „ok“, die Sammelzeile nennt S2",
          pl["status"] != "ok" and "S2" in pl["summary"], f"{pl['status']} {pl['summary'][:120]}")


# ---------------------------------------------------------------------------
# G3: Ergebnisse veralten; G4: Teilen erhaelt die Lasten
# ---------------------------------------------------------------------------
def _fenster():
    if "w" in _FENSTER:
        _FENSTER["w"].activateWindow()
        _FENSTER["app"].processEvents()
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    # Fehler und Hinweise (9b) landen beide in der Liste und zaehlen wie im
    # Programm; ein abgewiesenes „Übernehmen“ gilt so auch hier als gescheitert
    from tests.meldungen import abfangen
    abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    _FENSTER.update(w=w, app=app)
    return w, app


def balken_mit_querstab(m=None):
    """Balken 8 m (Stab S1 aus drei Elementen) mit Linienlast 10 kN/m und einem
    Querstab, dessen freies Ende 5 mm neben der Achse bei x = 4 m endet."""
    from statik3d.model import Model, Material, Section
    m = m if m is not None else Model("Teilen")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    for x in (0, 2, 6, 8):
        m.add_node(x, 0, 0)
    m.support(0, "all")
    m.support(3, [1, 2, 3])
    g = next(iter(m.load_cases))
    e = [m.add_element("beam", ab, "S355", "HEB 200") for ab in ([0, 1], [1, 2], [2, 3])]
    m.add_member("S1", e)
    a = m.add_node(4, 0.005, 0)
    b = m.add_node(4, 3, 0)
    m.support(b, "all")
    m.add_element("beam", [b, a], "S355", "HEB 200")
    m.add_linienlast("S1", [0, 0, -10e3], case=g)
    m.lasten_verteilen()
    return m, g


def _belastet(m, g):
    return sum((l.b if l.b is not None else m.element_length(l.elem)) - l.a for l in m.load_cases[g].beam_loads)


def test_a11_teilen_erhaelt_lasten():
    import numpy as np
    from statik3d import solver
    from statik3d.importers import hicad_szn
    m, g = balken_mit_querstab()
    r = hicad_szn.an_staebe_anschliessen(m, 0.01, [])
    an = solver.solve_all(m, design=False)
    Rz = float(np.asarray(an.cases[g].reactions).reshape(-1, 6)[:, 2].sum())
    check("A11 Teilen eines 8-m-Stabs mit Linienlast: belastete Länge 8 m, Summe Auflager z 80000 N",
          r["geteilt"] == 1 and abs(_belastet(m, g) - 8.0) < 1e-9 and abs(Rz - 80000.0) < 1e-6,
          f"belastet {_belastet(m, g):.3f} m, R_z {Rz:.1f} N")


def test_a10_ergebnis_veraltet():
    from PySide6 import QtWidgets
    from statik3d import solver, ergebnisse as erg
    w, app = _fenster()
    tmp = tempfile.mkdtemp(prefix="stabnachweis_a10_")

    def rechnen():
        w.refresh_all()
        app.processEvents()
        w._solve_done("all", solver.solve_all(w.model, design=True))
        app.processEvents()

    def gespeichert(datei):
        pfad = os.path.join(tmp, datei)
        w.path = pfad
        w.save_model()
        app.processEvents()
        return os.path.exists(erg.pfad_zu(pfad))

    w.new_model()
    stuetze(m=w.model)
    rechnen()
    vorher = w.analysis is not None and gespeichert("vorher.json")
    w.staebe_zusammenfassen(["S1", "S2", "S3"])
    app.processEvents()
    check("A10 nach „Stäbe zusammenfassen“: Ergebnis verworfen, keine Ergebnisdatei gespeichert",
          vorher and list(w.model.members) == ["S1"] and w.analysis is None and w.results is None
          and not gespeichert("zusammen.json"), f"{w.analysis is not None} {sorted(w.model.members)}")
    w.new_model()
    balken_mit_querstab(m=w.model)
    rechnen()
    alt = QtWidgets.QInputDialog.getDouble
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (10.0, True))
    try:
        w.staebe_anschliessen()
    finally:
        QtWidgets.QInputDialog.getDouble = alt
    app.processEvents()
    check("A10 nach dem Teilen („Freie Stabenden anschließen…“): Ergebnis verworfen, keine Ergebnisdatei",
          len(w.model.elements) == 5 and w.analysis is None and not gespeichert("geteilt.json"),
          f"{len(w.model.elements)} Elemente, {w.analysis is not None}")
    # „Stab“ um ein vorhandenes Element aendert nur die Staebe
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_node(0, 0, 0)
    m.add_node(4, 0, 0)
    m.support(0, "all")
    m.load_node(1, Fz=-1e3)
    m.add_element("beam", [0, 1], "S355", "HEB 300")
    rechnen()
    w._maske_stab_anlegen({"knoten": [0, 1], "mat": "S355", "sec": "HEB 300"})
    check("A10 nach „Stab“ um ein vorhandenes Element: Ergebnis verworfen",
          list(w.model.members) == ["S1"] and w.analysis is None, f"{sorted(w.model.members)} {w.analysis is not None}")


# ---------------------------------------------------------------------------
# G5: Kettenwarnung
# ---------------------------------------------------------------------------
def kette(n=3, sec="HEB 200"):
    """Senkrechte Kette aus n Staeben (6 m), unten eingespannt, oben gehalten."""
    from statik3d.model import Model, Material, Section
    m = Model("Kette")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile(sec))
    for i in range(n + 1):
        m.add_node(0, 0, 6.0 * i / n)
    m.support(0, "all")
    m.support(n, [0, 1, 2])
    for i in range(n):
        e = m.add_element("beam", [i, i + 1], "S355", sec)
        m.add_member(f"S{i + 1}", [e])
    return m


def _ketten(m):
    return [(list(k["staebe"]), list(k["knoten"]), k["achsen"]) for k in m.stabketten_frei()]


def test_a12_lager_je_richtung():
    m = kette()
    m.support(1, [2])
    check("A12 Lager am Zwischenknoten nur uz (Achsrichtung): Warnung an K1, K2 für beide Achsen",
          _ketten(m) == [(["S1", "S2", "S3"], [1, 2], "yz")], str(_ketten(m)))
    m = kette()
    m.support(1, [5])
    check("A12 Lager nur φz (Drehung): Warnung an K1, K2", _ketten(m) == [(["S1", "S2", "S3"], [1, 2], "yz")],
          str(_ketten(m)))
    m = kette()
    m.support(1, [0])
    k = _ketten(m)
    # senkrechter Stab: lokale z-Achse = global x (beam3d.local_axes) - ux haelt das
    # Ausweichen in z, also das Knicken um y; um z knickt die ganze Kette
    check("A12 Lager nur ux: Kette S1–S3 nur noch für die andere Achse (z), für y nur S2–S3",
          sorted(k) == sorted([(["S1", "S2", "S3"], [1, 2], "z"), (["S2", "S3"], [2], "y")]), str(k))
    m = kette()
    m.fix(1, [0, 1], stiffness=[1.0, 1.0])
    check("A12 Feder an K1 (Knotenlager mit Steifigkeit) zählt als Halt", _ketten(m) == [(["S2", "S3"], [2], "yz")],
          str(_ketten(m)))
    texte = [z for z in kette().check() if "Kette" in z]
    check("A12 „Prüfen“: eine Warnung je Kette, sie nennt die Stäbe",
          texte == ["WARNUNG: Stäbe S1, S2 und S3 bilden eine Kette mit freien Zwischenknoten K1 und K2 – "
                    "Knicklänge prüfen oder „Stäbe zusammenfassen“"], str(texte))


def test_a13_glieder_ohne_nachweis():
    m = kette()
    m.members["S2"].design = False
    k = m.stabketten_frei()
    check("A13 S2.design = False: Warnung für S1 und S3, S2 als Glied genannt",
          [x["staebe"] for x in k] == [["S1", "S3"]] and k[0]["knoten"] == [1, 2]
          and "S2 (ohne Nachweis)" in m.stabkette_text(k[0]), str(k))
    m = kette()
    del m.members["S2"]
    k = m.stabketten_frei()
    check("A13 S2 nur Stabelement: Warnung für S1 und S3, das Stabelement als Glied genannt",
          [x["staebe"] for x in k] == [["S1", "S3"]] and "Stabelement E1" in m.stabkette_text(k[0]), str(k))


def test_a14_feste_knicklaengen():
    m = kette()
    for s in m.members.values():
        s.Lcr_y = s.Lcr_z = 6.0
    check("A14 alle Stäbe mit fester Lcr für beide Achsen: keine Kettenwarnung", not m.stabketten_frei(),
          str(_ketten(m)))
    m = kette()
    m.members["S1"].Lcr_z = 6.0
    check("A14 … S1 nur um z fest: S1 nur noch für y gewarnt",
          sorted(_ketten(m)) == sorted([(["S1", "S2", "S3"], [1, 2], "y"), (["S2", "S3"], [1, 2], "z")]),
          str(_ketten(m)))


def test_a15_querschnitte_verschieden():
    from statik3d.model import Section
    m = kette()
    m.add_section(Section.from_profile("HEB 300"))
    m.elements[1].sec = "HEB 300"
    t = [z for z in m.check() if "Kette" in z]
    check("A15 Kette mit verschiedenen Querschnitten: Text rät nicht zu „Stäbe zusammenfassen“, sondern zur Hand",
          len(t) == 1 and "Stäbe zusammenfassen" not in t[0] and "von Hand setzen" in t[0], str(t))


def test_a16_etikett():
    from statik3d.ec3.design import check_members
    from statik3d.model import Model

    class _Leer:
        cases, combinations = {}, {}

        def all_results(self):
            return {}
    w, app = _fenster()
    # 12 getrennte Ketten - mehr, als das Etikett zeigen soll
    m = kette()
    for j in range(1, 12):
        a = m.add_node(10.0 * j, 0, 0)
        for i in range(3):
            b = m.add_node(10.0 * j, 0, 2.0 * (i + 1))
            e = m.add_element("beam", [a, b], "S355", "HEB 200")
            m.add_member(f"K{j}S{i + 1}", [e])
            a = b
        m.support(a - 3, "all")
        m.support(a, [0, 1, 2])
    d = check_members(m, _Leer(), combos=[])
    zeilen = [z for z in d.summary().splitlines() if z.startswith("WARNUNG (Knicklänge)")]
    alle = [z for z in d.summary().splitlines() if z.startswith("WARNUNG")]
    e_zeilen = w._etikett_kuerzen(d.summary()).splitlines()
    check("A16 12 Ketten: Protokoll 12 Kettenzeilen, Etikett höchstens 8 Warnzeilen und „… und n weitere, siehe Prüfen“",
          len(m.stabketten_frei()) == 12 and len(zeilen) == 12
          and sum(1 for z in e_zeilen if z.startswith("WARNUNG")) == 8
          and e_zeilen[-1] == f"… und {len(alle) - 8} weitere, siehe Prüfen",
          f"{len(zeilen)} / {len(alle)} / {e_zeilen[-1]!r}")
    if not os.path.exists(CBG):
        print(f"     (cbg.json nicht gefunden: {CBG} – die Prüfung am Modell des Anwenders entfällt)")
        return
    m = Model.load(CBG)
    ketten = m.stabketten_frei()
    d = check_members(m, _Leer(), combos=[])
    zeilen = [z for z in d.summary().splitlines() if z.startswith("WARNUNG (Knicklänge)")]
    alle = [z for z in d.summary().splitlines() if z.startswith("WARNUNG")]
    pruefen = [z for z in m.check() if "bilden eine Kette" in z]
    e_zeilen = w._etikett_kuerzen(d.summary()).splitlines()
    check(f"A16 cbg.json: {len(ketten)} Ketten, je eine Warnzeile im Protokoll und in „Prüfen“, Etikett 8 + Rest",
          len(zeilen) == len(ketten) == len(pruefen) > 0
          and sum(1 for z in e_zeilen if z.startswith("WARNUNG")) == min(8, len(alle))
          and (len(alle) <= 8 or e_zeilen[-1] == f"… und {len(alle) - 8} weitere, siehe Prüfen"),
          f"{len(ketten)} Ketten, {len(zeilen)} Zeilen, {len(pruefen)} in Prüfen, Ende {e_zeilen[-1][:40]!r}")


def test_a17_gegenlaeufig():
    from statik3d.model import Material, Section
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_node(0, 0, 0)
    m.add_node(4, 0, 0)
    m.add_element("beam", [1, 0], "S355", "HEB 300")
    w._maske_stab_anlegen({"knoten": [0, 1], "mat": "S355", "sec": "HEB 300"})
    st = w.statusBar().currentMessage()
    check("A17 „Stab“ um das gegenläufige Element E0 (K1→K0): die Meldung nennt K1–K0",
          "Stab S1 um das vorhandene Stabelement E0 angelegt: K1–K0" in st, repr(st))


def test_handbuch():
    from tests.handbuch import absatz
    k = absatz("Stäbe (Kette von Stabelementen) legt der Befehl")
    check("Handbuch Kapitel 8: Zusammenfassen weist ab (feste Längen, Parameter, Lasten, Verweise), Stand vorher",
          "erst auf β·L zurücksetzen" in k and "Kerbfall, β-Werte, Wölbrandbedingung" in k
          and "auch der erste" in k and "Bis zur zweiten Fassung vom 03.10.2026" in k, k[:100])
    check("Handbuch Kapitel 8: verschiedene Linienlasten gehen mit, was nicht verlustfrei geht, Stand vor dem 04.10.2026",
          "auch wenn die Stäbe verschiedene haben" in k and "auf dem Abschnitt, auf dem sie vorher lag" in k
          and "trapezförmige Last, die über ihren Stab hinausreicht" in k and "außerhalb ihres Stabs" in k
          and "Bis zum 04.10.2026 wies das Zusammenfassen verschiedene Linienlasten ab" in k, k[:100])
    check("Handbuch Kapitel 8: Kettenwarnung je Ausweichrichtung, Federn halten, einmal je Kette, Etikett 8 Zeilen",
          "einmal je Kette" in k and "je Ausweichrichtung" in k and "Federelement" in k
          and "höchstens acht" in k and "87 Ketten" in k, k[:100])
    a = absatz("**Was beim Stab mit Nachweis zu beachten ist**")
    check("Handbuch: leerer Stab als nicht geführt, Teilen verteilt Linienlasten neu, Ergebnisse verworfen",
          "als nicht geführt" in a and "verteilt die Linienlasten" in a and "verwerfen die Ergebnisse" in a, a[:100])
    check("Handbuch: beim Zusammenfassen gehen verschiedene Linienlasten mit, Stand vor dem 04.10.2026",
          "verschiedene Linienlasten, gehen sie mit" in a and "auf dem Abschnitt, auf dem sie vorher lag" in a
          and "Bis zum 04.10.2026 wies das Zusammenfassen" in a, a[:100])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_a1_feste_knicklaengen, test_a2_eine_feste_knicklaenge, test_a3_parameter_verschieden,
              test_a4_gleiche_parameter, test_a5_aus, test_a6_verweise_und_vorspannung, test_a7_ohne_unterschiede,
              test_l1_verschiedene_linienlasten, test_l2_last_nur_auf_dem_mittleren, test_l3_lastarten,
              test_l4_vorspannung, test_l5_gleiche_linienlast, test_l6_rueckgaengig, test_l7_speichern_laden,
              test_l8_nachweise,
              test_a8_leerer_stab_ermuedung, test_a9_leerer_stab_ec3, test_a10_ergebnis_veraltet,
              test_a11_teilen_erhaelt_lasten, test_a12_lager_je_richtung, test_a13_glieder_ohne_nachweis,
              test_a14_feste_knicklaengen, test_a15_querschnitte_verschieden, test_a16_etikett,
              test_a17_gegenlaeufig, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
