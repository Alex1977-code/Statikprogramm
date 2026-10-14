"""Last an automatisch gehaltenen Freiheitsgraden (14.10.2026).

Das Programm sperrt jeden Freiheitsgrad ohne Steifigkeit (Diagonale unter
1e-12 der groessten, assemble.constrained_dofs): die Drehungen an Knoten nur
mit Fachwerkstaeben, Seilen oder Volumen, die Querrichtungen einer
Fachwerkstab-Kette, einen Knoten ohne Bauteil. Das ist richtig, solange dort
keine Last ankommt. Kommt eine an, nimmt der gesperrte Freiheitsgrad sie auf
wie ein Lager - bis zum 14.10.2026 still: eine Kette aus zwei Fachwerkstaeben
mit 1 kN quer am Mittelknoten ist ein Mechanismus, die echten Lager trugen
0 kN, u_z war 0, und die Zusammenfassung nannte nur „Summe Auflagerkräfte
[0, 0, 1000] N“.

Geprueft wird:

* **Kette aus zwei Fachwerkstaeben, 1 kN quer am Mittelknoten:** die Kraft
  steht mit Knoten, Richtung und Betrag in ``info['auto_gehalten']``, in der
  Zusammenfassung (WARNUNG und „NICHT GÜLTIG“), im Protokoll (Fortschritt),
  in der Rechenliste („nicht gültig“) und im Bericht; die Summe der
  Auflagerkraefte zaehlt sie nicht mit und nennt sie getrennt; die
  Gesamtzusammenfassung und eine Kombination tragen sie weiter.
* **Fachwerk ohne Mechanismus** (ebener Fachwerktraeger, Raumfachwerk): die
  automatisch gehaltenen Drehungen und Querrichtungen tragen nichts - keine
  Meldung, und die Rechnung ist bitgleich mit der ohne Pruefung.
* **Balkenende mit Knotenmoment an einem Fachwerkknoten:** der Balken traegt
  das Moment, keine Meldung. Dasselbe Moment an einem Knoten nur mit
  Fachwerkstaeben wird gemeldet (Moment ohne Drehsteifigkeit).
* **Die eingebauten Beispiele** bleiben ohne Meldung.

Aufruf:  python -m tests.test_auto_gehalten
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                       # noqa: E402
from statik3d.examples_lib import EXAMPLES, build_example         # noqa: E402
from statik3d.model import Material, Model, Section               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:72s} {detail}")
    return bool(ok)


def eintraege(r) -> list:
    return list((getattr(r, "info", None) or {}).get("auto_gehalten") or [])


def loesen(m, case="LF1", an: bool = True, progress=None):
    """Einen Lastfall mit oder ohne die Pruefung rechnen."""
    alt = getattr(solver, "AUTO_GEHALTEN_PRUEFEN", True)
    solver.AUTO_GEHALTEN_PRUEFEN = an
    try:
        return solver.solve_static(m, case=case, progress=progress)
    finally:
        solver.AUTO_GEHALTEN_PRUEFEN = alt


def ohne_zeit(text: str) -> list:
    return [z for z in str(text).splitlines() if not z.startswith("Rechenzeit")]


# --------------------------------------------------------------------------
# Baukasten
# --------------------------------------------------------------------------
def kette() -> Model:
    """Die Probe: a - c - b aus zwei Fachwerkstaeben, 1 kN quer an c (Knoten 1)."""
    m = Model("Kette")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0))
    m.add_section(Section.circle("D", 0.05))
    a, c, b = m.add_node(0, 0, 0), m.add_node(2, 0, 0), m.add_node(4, 0, 0)
    m.fix(a, [0, 1, 2])
    m.fix(b, [1, 2])
    e1 = m.add_element("truss", [a, c], "S", "D")
    e2 = m.add_element("truss", [c, b], "S", "D")
    m.add_member("S1", [e1, e2])
    m.add_load_case("LF1").gravity = [0, 0, 0]
    m.load_node(c, Fz=-1e3, case="LF1")
    return m


def raumfachwerk() -> Model:
    """Dreibein: drei Fachwerkstaebe von festen Fusspunkten zur Spitze, Last an
    der Spitze in allen drei Richtungen - ein stabiles Raumfachwerk, an dem nur
    Drehungen automatisch gehalten sind."""
    m = Model("Dreibein")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=7850.0))
    m.add_section(Section.circle("D", 0.05))
    fuss = [m.add_node(*p) for p in ((0, 0, 0), (3, 0, 0), (1.5, 2.5, 0))]
    spitze = m.add_node(1.5, 0.8, 3.0)
    for i, k in enumerate(fuss):
        m.fix(k, [0, 1, 2])
        e = m.add_element("truss", [k, spitze], "S", "D")
        m.add_member(f"S{i + 1}", [e])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, -9.81]
    m.load_node(spitze, Fx=2e3, Fy=-1e3, Fz=-5e3, case="LF1")
    return m


def balken_mit_fachwerk(moment_am_balken: bool = True) -> Model:
    """Kragbalken a - b (eingespannt bei a), am Balkenende b schliessen zwei
    Fachwerkstaebe zu gelenkigen Fusspunkten an. ``moment_am_balken``: das
    Knotenmoment M_y = 2 kNm wirkt an b (Balkenende und Fachwerkknoten);
    sonst an einem Knoten d, an dem nur Fachwerkstaebe haengen."""
    m = Model("Balken und Fachwerk")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0))
    m.add_section(Section.circle("D", 0.08))
    a, b = m.add_node(0, 0, 0), m.add_node(3, 0, 0)
    f1, f2 = m.add_node(3, -2, -2), m.add_node(3, 2, -2)
    d = m.add_node(5, 0, 0)
    m.fix(a, "all")
    for k in (f1, f2):
        m.fix(k, [0, 1, 2])
    eb = m.add_element("beam", [a, b], "S", "D")
    m.add_member("B1", [eb])
    for i, k in enumerate((f1, f2)):
        m.add_member(f"F{i + 1}", [m.add_element("truss", [k, b], "S", "D")])
    # Knoten d: drei Fachwerkstaebe (b - d, f1 - d, f2 - d) - raeumlich gehalten
    for i, k in enumerate((b, f1, f2)):
        m.add_member(f"G{i + 1}", [m.add_element("truss", [k, d], "S", "D")])
    m.add_load_case("LF1").gravity = [0, 0, 0]
    m.load_node(b if moment_am_balken else d, My=2e3, case="LF1")
    m.load_node(b, Fz=-1e3, case="LF1")
    return m


# --------------------------------------------------------------------------
# 1) Die Kette aus der Probe
# --------------------------------------------------------------------------
def test_kette_wird_gemeldet():
    meldungen = []
    r = loesen(kette(), progress=lambda t, *a: meldungen.append(str(t)))
    e = eintraege(r)
    check("Kette: genau ein Eintrag in info['auto_gehalten']", len(e) == 1, str(e)[:200])
    if not e:
        return
    x = e[0]
    check("Knoten 1, Richtung z, Last -1000 N (nach unten)",
          x.get("knoten") == 1 and x.get("richtung") == "z" and abs(x.get("last", 0) + 1000.0) < 1e-9,
          str(x)[:200])
    t = str(x.get("text", ""))
    check("der Text nennt Knoten, Betrag, Fachwerkstäbe und Mechanismus",
          t.startswith("Knoten K1:") and "1,000 kN" in t and "nur mit Fachwerkstäben" in t
          and "Mechanismus" in t and "von keinem Bauteil getragen" in t, t)
    R = np.asarray(r.reactions)
    check("die Kraft steht nicht mehr als Auflagerkraft am Mittelknoten",
          R[1, 2] == 0.0, f"R_z(K1) = {R[1, 2]}")
    s = r.summary().splitlines()
    summe = [z for z in s if z.startswith("Summe Auflagerkräfte")]
    check("Summe Auflagerkräfte ohne die automatisch gehaltene Kraft",
          summe == ["Summe Auflagerkräfte    : [0.0, 0.0, 0.0] N"], str(summe))
    getrennt = [z for z in s if z.startswith("Automatisch gehalten")]
    check("und getrennt genannt",
          len(getrennt) == 1 and "[0.0, 0.0, 1000.0] N" in getrennt[0], str(getrennt))
    check("WARNUNG mit dem Text in der Zusammenfassung",
          any(z.startswith("WARNUNG") and "Knoten K1:" in z for z in s), str(s)[:300])
    check("die Zusammenfassung kennzeichnet die Rechnung als NICHT GÜLTIG",
          any(z.startswith("NICHT GÜLTIG") for z in s), str(s)[:300])
    g = solver.gueltigkeit(r.info)
    check("solver.gueltigkeit nennt den Grund", g.startswith("NICHT gültig") and "K1" in g, g)
    check("das Protokoll (Fortschritt) bekommt die WARNUNG",
          any(z.startswith("WARNUNG") and "Knoten K1:" in z for z in meldungen), str(meldungen)[-300:])


def test_kette_rechenliste():
    from statik3d.gui import rechenliste as rl
    r = loesen(kette())
    neu, meldung = rl.zustand_und_meldung(r.info, "")
    check("Rechenliste: „nicht gültig“ mit dem Grund als Meldung",
          neu == rl.NICHT_GUELTIG and "K1" in meldung, f"{neu!r} / {meldung!r}")
    r2 = loesen(raumfachwerk())
    neu2, meldung2 = rl.zustand_und_meldung(r2.info, "")
    check("Rechenliste: das gesunde Fachwerk bleibt ohne Zustand (fertig)",
          neu2 is None and meldung2 == "", f"{neu2!r} / {meldung2!r}")


def test_kette_bericht():
    from statik3d.report import Report
    m = kette()
    r = loesen(m)
    html = Report(m, results=r).html()
    check("Bericht: Kapitel zu Lasten an automatisch gehaltenen Freiheitsgraden",
          "Last an automatisch gehaltenen Freiheitsgraden" in html, "")
    check("Bericht: die Tabelle nennt Knoten, Größe und Last",
          "<td>K1</td>" in html and "F_z" in html and "-1,000 kN" in html, "")
    check("Bericht: und die Warnungen nennen es „Nicht gültig“ mit dem Text",
          "Nicht gültig (" in html and "Knoten K1: F_z" in html and "Mechanismus" in html, "")
    check("Bericht: die Zusammenfassung hat eine rote Zeile „NICHT gültig: 1 Ergebnis (LF1)“",
          "NICHT gültig: 1 Ergebnis (LF1)" in html, "")
    h2 = Report(build_example("truss"), results=loesen(build_example("truss"),
                                                       case=list(build_example("truss").load_cases)[0])).html()
    check("Bericht ohne Mechanismus: kein Kapitel und keine Zeile",
          "automatisch gehaltenen Freiheitsgraden" not in h2 and "NICHT gültig" not in h2, "")


def test_kette_gesamt_und_kombination():
    m = kette()
    lc2 = m.add_load_case("LF2")
    lc2.gravity = [0, 0, 0]
    m.load_node(1, Fy=500.0, case="LF2")
    m.add_combination("LK1", {"LF1": 1.35, "LF2": 1.5})
    an = solver.solve_all(m)
    s = an.summary().splitlines()
    w = [z for z in s if z.startswith("WARNUNG") and "K1" in z]
    check("Gesamtzusammenfassung: je Text eine WARNUNG mit den Ergebnissen",
          len(w) >= 2 and any("LF1" in z for z in w) and any("LF2" in z for z in w), str(w)[:400])
    k = an.combinations.get("LK1")
    e = eintraege(k)
    lasten = sorted((x["richtung"], round(x["last"], 6)) for x in e)
    check("die Kombination trägt beide Anteile mit Faktor",
          lasten == [("y", 750.0), ("z", -1350.0)], str(lasten))
    check("und ist ebenfalls nicht gültig", solver.gueltigkeit(k.info).startswith("NICHT gültig"),
          solver.gueltigkeit(k.info))
    R = np.asarray(k.reactions)
    check("ihre Auflagerkräfte enthalten die gehaltene Kraft nicht",
          float(np.abs(R[1, :3]).max()) == 0.0, str(R[1, :3]))


# --------------------------------------------------------------------------
# 2) Fachwerk ohne Mechanismus: still und bitgleich
# --------------------------------------------------------------------------
def test_fachwerk_still_und_bitgleich():
    for name, bauen in (("ebener Fachwerkträger (Beispiel truss)", lambda: build_example("truss")),
                        ("Raumfachwerk (Dreibein)", raumfachwerk)):
        m1, m2 = bauen(), bauen()
        fall = list(m1.load_cases)[0]
        r_an = loesen(m1, case=fall, an=True)
        r_aus = loesen(m2, case=fall, an=False)
        check(f"{name}: keine Meldung", not eintraege(r_an) and not solver.gueltigkeit(r_an.info),
              str(eintraege(r_an))[:120])
        check(f"{name}: Verschiebungen bitgleich", np.array_equal(r_an.u, r_aus.u), "")
        check(f"{name}: Auflagerkräfte bitgleich", np.array_equal(r_an.reactions, r_aus.reactions), "")
        check(f"{name}: Zusammenfassung gleich (ohne Rechenzeit)",
              ohne_zeit(r_an.summary()) == ohne_zeit(r_aus.summary()), "")
    r = loesen(raumfachwerk())
    soll = np.array([2e3, -1e3, -5e3])
    check("Raumfachwerk: Summe der Auflager = - Knotenlast - Gewicht (Kontrolle)",
          abs(float(np.asarray(r.reactions)[:, :3].sum(axis=0)[0]) + soll[0]) < 1e-6, "")


# --------------------------------------------------------------------------
# 3) Balkenende mit Knotenmoment an einem Fachwerkknoten
# --------------------------------------------------------------------------
def test_balkenende_traegt_moment():
    r = loesen(balken_mit_fachwerk(moment_am_balken=True))
    check("Moment am Balkenende (Fachwerkknoten): keine Meldung", not eintraege(r),
          str(eintraege(r))[:160])
    m = balken_mit_fachwerk(moment_am_balken=True)
    R = np.asarray(r.reactions)
    # Gleichgewicht um den Ursprung: Lager + Last = 0 (Last: M_y 2 kNm und F_z -1 kN an b)
    X = np.asarray(m.nodes, float)
    M_lager = (np.cross(X, R[:, :3]) + R[:, 3:]).sum(axis=0)
    M_last = np.cross(X[1], [0.0, 0.0, -1e3]) + np.array([0.0, 2e3, 0.0])
    check("das Moment kommt an den echten Lagern an (Momentengleichgewicht um 0)",
          float(np.abs(M_lager + M_last).max()) < 1e-6 * 5e3 and R[0, 4] != 0.0,
          f"Rest {M_lager + M_last}, M_y(a) = {R[0, 4]:.3f} Nm")
    r2 = loesen(balken_mit_fachwerk(moment_am_balken=False))
    e = eintraege(r2)
    check("Moment an einem Knoten nur mit Fachwerkstäben: gemeldet",
          len(e) == 1 and e[0].get("knoten") == 4 and e[0].get("richtung") == "My", str(e)[:200])
    if e:
        t = str(e[0].get("text", ""))
        check("mit Betrag in kNm und „ohne Drehsteifigkeit“",
              "2,000 kNm" in t and "ohne Drehsteifigkeit" in t, t)
    s = r2.summary().splitlines()
    getrennt = [z for z in s if z.startswith("Automatisch gehalten")]
    check("das Moment steht getrennt, nicht in der Kraftsumme",
          len(getrennt) == 1 and "Nm" in getrennt[0], str(getrennt))


# --------------------------------------------------------------------------
# 4) Die eingebauten Beispiele bleiben still
# --------------------------------------------------------------------------
def test_beispiele_ohne_meldung():
    for name in EXAMPLES:
        m = build_example(name)
        an = solver.solve_all(m)
        mit = [n for n, r in an.all_results().items() if eintraege(r)]
        check(f"Beispiel {name}: keine Last an automatisch gehaltenen Freiheitsgraden", not mit,
              ", ".join(mit)[:120])


def main():
    for t in (test_kette_wird_gemeldet, test_kette_rechenliste, test_kette_bericht,
              test_kette_gesamt_und_kombination, test_fachwerk_still_und_bitgleich,
              test_balkenende_traegt_moment, test_beispiele_ohne_meldung):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
