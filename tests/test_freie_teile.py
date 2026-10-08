"""
Frei bewegliche Teile erkennen und mit Namen melden (B5, 08.10.2026).

Am Drehlager meldet PARDISO in jeder Faktorisierung gestoerte Pivots (Entwurf
22-40, Mittel 34-52). Die Ursache sind Bauteile, die in ihrer Ebene durch
nichts gehalten sind - die Lastverteilplatten V1-V28 an der Fuge
„Lagerbock-Unterlegbleche“, die nur senkrecht traegt - und Stabknoten ohne
Querhalt. Das Programm soll sie **nennen**, nicht lagern: Bauteil, Richtung,
und was sie heute haelt. Die Vorabsuche (singular.restfreiheiten) findet sie
dort nicht - das Flaechenlager „Starr“ hat Reibung 0,1, und Reibung zaehlt in
der Vorabpruefung als Halt -, die Zahl der gestoerten Pivots aber ist eine
Messung an der Matrix selbst.

Geprueft wird:

* **Platte auf Block, nur reibungsfreier Kontakt, unter Druck.** Die Platte
  ist in ihrer Ebene frei: die Meldung nennt sie, die Richtungen (Verschiebung
  in x und y, Drehung um z) und die Fuge, die sie nur senkrecht haelt - in
  Zusammenfassung, Protokollzeile (``WARNUNG``) und Bericht.
* **Mit Reibung, mit Feder, seitlich gehalten:** keine Meldung, und keine
  einzige zusaetzliche Loesung (die Suche laeuft nur bei gestoerten Pivots).
* **Viele gleiche Platten** stehen in einer Zeile, natuerlich sortiert.
* **Schiefe Ebene:** die Richtung wird als Normale genannt, nicht als x und y.
* **Stabknoten ohne Querhalt:** Stab und Knoten werden genannt.
* **Die Beispiele** frame, plate, solid, truss, hall, contact, friction, gate
  bekommen keine Meldung.
* **Die Rechnung bleibt bitgleich**, und die Suche kostet hoechstens sechs
  Loesungen auf dem vorhandenen Faktor.

Aufruf:  python -m tests.test_freie_teile
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import singular as sg, solver                      # noqa: E402
from statik3d.examples_lib import EXAMPLES, build_example         # noqa: E402
from statik3d.model import ContactPair, Material, Model          # noqa: E402
from statik3d.profiles import make_section                        # noqa: E402
from tests.test_singular import auf_unterlage                     # noqa: E402

RESULTS = []

F_LAST = 1.0e6          # N


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:68s} {detail}")
    return bool(ok)


def teile(r) -> list:
    return list((r.info or {}).get("freie_teile") or [])


def warnzeilen(r) -> list:
    return [z for z in r.summary().splitlines() if z.startswith("WARNUNG")]


class Zaehler:
    """Zaehlt die Loesungen auf einem PARDISO-Faktor (PyPardisoSolver.solve)."""

    def __enter__(self):
        import pypardiso
        self.klasse = pypardiso.PyPardisoSolver
        self.alt = self.klasse.solve
        self.n = 0
        zaehler = self

        def solve(ps, A, b, *a, **kw):
            zaehler.n += 1
            return zaehler.alt(ps, A, b, *a, **kw)
        self.klasse.solve = solve
        return self

    def __exit__(self, *exc):
        self.klasse.solve = self.alt
        return False


def loesen(m, an: bool = True):
    """Lastfall LF1 mit oder ohne die Suche nach freien Teilen."""
    alt = getattr(sg, "PIVOTBEFUND", True)
    sg.PIVOTBEFUND = an
    try:
        with Zaehler() as z:
            r = solver.solve_static(m, case="LF1")
    finally:
        sg.PIVOTBEFUND = alt
    return r, z.n


# --------------------------------------------------------------------------
# Baukasten
# --------------------------------------------------------------------------
def platten_auf_block(n: int, mu: float = 0.0, name: str = "P", last: float = -F_LAST) -> Model:
    """``n`` Einheitswuerfel-Platten nebeneinander auf einem festen, breiten Block.

    Jede Platte ist ein eigenes Bauteil („P1“ ... „Pn“), nur ueber Kontakt mit
    dem Block verbunden; ``mu`` > 0 haelt sie in der Fugenebene.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    breite = 2.0 * n + 2.0
    unten = np.array([[-1, -1, 0], [breite, -1, 0], [breite, 2, 0], [-1, 2, 0],
                      [-1, -1, 1], [breite, -1, 1], [breite, 2, 1], [-1, 2, 1.]])
    m.add_nodes(unten)
    m.add_element("hex8", list(range(8)), "S235", group="Block")
    for k in range(4):
        m.fix(k, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    slaves = []
    for i in range(n):
        x0 = 2.0 * i
        ecken = np.array([[x0, 0, 1], [x0 + 1, 0, 1], [x0 + 1, 1, 1], [x0, 1, 1.],
                          [x0, 0, 2], [x0 + 1, 0, 2], [x0 + 1, 1, 2], [x0, 1, 2.]])
        k0 = len(m.nodes)
        m.add_nodes(ecken)
        m.add_element("hex8", list(range(k0, k0 + 8)), "S235", group=f"{name}{i + 1}")
        slaves += [k0, k0 + 1, k0 + 2, k0 + 3]
        for k in range(k0 + 4, k0 + 8):
            m.load_node(k, Fz=last / (4.0 * n))
    m.contact_pairs.append(ContactPair("Fuge", slave_nodes=slaves, master_elements=[0], mu=mu))
    return m


STAB_KNOTEN = 5          # Nummer des Stabendknotens am schiefen Anschlag


def stab_mit_freiem_knoten() -> Model:
    """Ein Zugstab S7 endet an einem schiefen Anschlag - sein Endknoten ist frei.

    Das Stabende (Knoten 5) liegt in einem Kontaktpaar gegen eine Facette,
    deren Normale (0,71 | 0 | 0,71) schraeg zu den Achsen steht. Der Stab haelt
    nur laengs (y), der Kontakt nur in Richtung der Normalen: die Richtung
    (0,71 | 0 | -0,71) dazwischen hat nichts - ein Stabknoten ohne Querhalt, der
    nur ueber den Kontakt ueberhaupt als Freiheitsgrad stehen bleibt (ohne
    Kontakt sperrt das Programm Freiheitsgrade ohne Steifigkeit stillschweigend,
    assemble.constrained_dofs). Dazu eine gesunde Stabkette H1-H4, damit es
    Vergleichsknoten gibt.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    s = np.sqrt(0.5)
    n, e1, e2 = np.array([s, 0, s]), np.array([s, 0, -s]), np.array([0, 1.0, 0])
    facette = [int(m.add_node(*c)) for c in (-2 * e1 - 2 * e2, 2 * e1 - 2 * e2,
                                              2 * e1 + 2 * e2, -2 * e1 + 2 * e2)]
    for k in facette:
        m.fix(k, "all")
    a, b = m.add_node(0, -3, 0), m.add_node(0, 0, 0)
    assert int(b) == STAB_KNOTEN
    e = m.add_element("truss", [a, b], "S235", "IPE 200", group="Zugstab")
    m.add_member("S7", [e])
    m.fix(a, [0, 1, 2])
    m.contact_pairs.append(ContactPair("Anschlag", slave_nodes=[int(b)], master_faces=[facette]))
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.load_node(b, Fx=-1e3 * n[0], Fz=-1e3 * n[2])
    # gesunde Kette ueber x: H0 fest, H1-H4 nur laengs beweglich, Zug am Ende
    kette = [int(m.add_node(5.0 + i, 5.0, 0.0)) for i in range(5)]
    m.fix(kette[0], [0, 1, 2])
    for i in range(4):
        ei = m.add_element("truss", [kette[i], kette[i + 1]], "S235", "IPE 200", group="Kette")
        m.add_member(f"H{i + 1}", [ei])
    m.load_node(kette[-1], Fx=1.0e4)
    return m


# --------------------------------------------------------------------------
# 1) Platte auf Block: die Meldung
# --------------------------------------------------------------------------
def test_platte_reibungsfrei_wird_genannt():
    r, _n = loesen(auf_unterlage(last=-F_LAST))
    t = teile(r)
    check("die frei bewegliche Platte steht in info['freie_teile']",
          len(t) == 1, f"{len(t)} Eintraege")
    if not t:
        return
    e = t[0]
    check("sie wird beim Namen genannt: Oben", e.get("namen") == ["Oben"], str(e.get("namen")))
    check("es ist ein Bauteil, kein Stab", e.get("art") == "koerper", str(e.get("art")))
    b = e.get("bewegung", "")
    check("Verschiebung in x und y", "frei verschieblich" in b and "(x, y)" in b, b)
    check("Drehung um z", "um z" in b and "drehbar" in b, b)
    h = e.get("haltung", "")
    check("was sie hält: die Fuge, reibungsfrei", "Fuge" in h and "reibungsfrei" in h, h)
    check("der fertige Satz nennt Name, Richtungen und die Bitte zu lagern",
          "Oben" in e["text"] and "(x, y)" in e["text"] and "um z" in e["text"]
          and "lagern" in e["text"], e["text"])
    # Zusammenfassung
    w = warnzeilen(r)
    check("die Zusammenfassung hat eine WARNUNG-Zeile mit dem Namen",
          len(w) == 1 and "Oben" in w[0] and "(x, y)" in w[0], str(w))
    # Die Suche hat gerechnet und das gesagt
    s = r.info.get("freie_teile_suche") or {}
    check("die Suche nennt gestoerte Pivots und Zahl der Loesungen",
          s.get("gestoerte_pivots") == 3 and 1 <= s.get("zusatzloesungen", 0) <= 6,
          str(s))


def test_bericht_fuehrt_die_teile_auf():
    from statik3d.report import Report
    m = auf_unterlage(last=-F_LAST)
    r, _n = loesen(m)
    html = Report(m, results=r).html()
    check("der Bericht hat ein Kapitel „Frei bewegliche Teile“",
          "Frei bewegliche Teile" in html, "")
    check("es nennt das Bauteil und die Richtungen",
          "Oben" in html and "frei verschieblich" in html and "(x, y)" in html, "")
    check("und steht auch bei den Warnungen des Berichts",
          html.count("frei verschieblich") >= 2, str(html.count("frei verschieblich")))


def test_bericht_sagt_nur_wahres_zur_hilfsfesselung():
    """Das Kapitel „Freie Bewegungen“ behauptete bis zum 08.10.2026 immer, jede
    Bewegung sei mit einer Hilfsfesselung festgehalten - auch wo die Rechnung
    ohne sie gelang (Platte auf Block: ``gefesselt`` False)."""
    from statik3d.report import Report
    from tests.test_singular import wuerfel
    m = auf_unterlage(last=-F_LAST)
    r, _n = loesen(m)
    html = Report(m, results=r).html()
    check("Platte auf Block: das Kapitel sagt, dass nichts festgehalten wurde",
          "ohne Hilfsfesselung gelungen" in html
          and "jede Bewegung ist mit einer Hilfsfesselung festgehalten" not in html, "")
    # Gegenprobe: der freie Wuerfel mit Netto-Last wird wirklich gefesselt
    w = wuerfel()
    for k in (4, 5, 6, 7):
        w.load_node(k, Fz=F_LAST / 4)
    r2 = solver.solve_static(w, case="LF1")
    html2 = Report(w, results=r2).html()
    check("freier Würfel: dort steht die Hilfsfesselung weiter",
          "jede Bewegung ist mit einer Hilfsfesselung festgehalten" in html2
          and "ohne Hilfsfesselung gelungen" not in html2, "")


def test_gesamtanalyse_buendelt():
    """Die Zusammenfassung der ganzen Rechnung nennt dasselbe Teil nur einmal."""
    m = auf_unterlage(last=-F_LAST)
    lc2 = m.add_load_case("LF2")
    lc2.gravity = [0, 0, 0]
    for k in (12, 13, 14, 15):
        m.load_node(k, Fz=-0.5 * F_LAST / 4.0)
    an = solver.solve_all(m, combinations=False)
    w = [z for z in an.summary().splitlines() if z.startswith("WARNUNG")]
    check("zwei Lastfälle, dasselbe Teil: eine WARNUNG-Zeile für beide",
          len(w) == 1 and "Oben" in w[0] and "bei 2 Ergebnissen: LF1, LF2" in w[0], str(w)[:200])
    check("und jedes der beiden Ergebnisse trägt die Meldung",
          all(teile(an.cases[n]) for n in ("LF1", "LF2")), "")


def test_kombination_traegt_die_teile():
    from statik3d.solver import Results
    m = auf_unterlage(last=-F_LAST)
    r, _n = loesen(m)
    k = Results.combine(m, [(r, 1.35)], name="K1", kind="combination")
    check("eine Ueberlagerung zeigt dieselben freien Teile",
          [e["text"] for e in teile(k)] == [e["text"] for e in teile(r)] and teile(k) != [],
          str([e.get("namen") for e in teile(k)]))
    check("und die Zusammenfassung der Ueberlagerung warnt ebenso",
          len(warnzeilen(k)) == 1, str(warnzeilen(k)))


# --------------------------------------------------------------------------
# 2) Gegenprobe: gehalten -> keine Meldung, keine zusaetzliche Loesung
# --------------------------------------------------------------------------
def test_gehalten_keine_meldung():
    faelle = {
        "mit Reibung (mu = 0,3)": auf_unterlage(last=-F_LAST, mu=0.3),
        "seitlich gehalten": auf_unterlage(last=-F_LAST, seitlich=True),
    }
    m_feder = auf_unterlage(last=-F_LAST)
    for k in (8, 9, 10, 11):
        m_feder.fix(k, [0, 1], stiffness=[1e8, 1e8])
    faelle["mit Federn in x und y"] = m_feder
    for name, m in faelle.items():
        r, n_an = loesen(m, an=True)
        _r0, n_aus = loesen(m, an=False)
        check(f"{name}: keine freien Teile, keine WARNUNG",
              not teile(r) and not warnzeilen(r), str(teile(r)))
        check(f"{name}: keine zusätzliche Lösung",
              n_an == n_aus and "freie_teile_suche" not in r.info, f"{n_an} gegen {n_aus}")


# --------------------------------------------------------------------------
# 3) Viele Platten: eine Zeile, natuerlich sortiert
# --------------------------------------------------------------------------
def test_viele_platten_eine_zeile():
    m = platten_auf_block(12)
    r, _n = loesen(m)
    t = teile(r)
    check("zwoelf gleiche Platten: ein einziger Eintrag", len(t) == 1, f"{len(t)}")
    if not t:
        return
    namen = t[0]["namen"]
    soll = [f"P{i}" for i in range(1, 13)]
    check("alle zwölf, natürlich sortiert (P2 vor P10)", namen == soll, str(namen))
    text = t[0]["text"]
    check("der Satz kürzt: erste sechs, „…“, letzte, Zahl der Bauteile",
          "P1, P2, P3, P4, P5, P6" in text and "P12" in text and "12 Bauteile" in text, text[:120])
    check("eine WARNUNG-Zeile für alle", len(warnzeilen(r)) == 1, str(len(warnzeilen(r))))

    # Mit Reibung: keine einzige
    r2, _n2 = loesen(platten_auf_block(12, mu=0.3))
    check("dieselben Platten mit Reibung: keine Meldung", not teile(r2), str(teile(r2)))

    # Nur eine von drei Platten frei (die beiden anderen seitlich gehalten)
    m3 = platten_auf_block(3)
    for p in (1, 3):                     # P1 und P3 seitlich halten, P2 bleibt frei
        k0 = 8 + 8 * (p - 1)
        for k in range(k0, k0 + 4):
            m3.fix(k, [0, 1])
    r3, _n3 = loesen(m3)
    t3 = teile(r3)
    check("zwei von drei Platten gehalten: nur P2 wird genannt",
          len(t3) == 1 and t3[0]["namen"] == ["P2"], str([e["namen"] for e in t3]))


# --------------------------------------------------------------------------
# 4) Schiefe Ebene
# --------------------------------------------------------------------------
def test_schiefe_ebene_nennt_die_normale():
    w = np.radians(30.0)
    R = np.array([[np.cos(w), 0, np.sin(w)], [0, 1, 0], [-np.sin(w), 0, np.cos(w)]])
    m = auf_unterlage()
    m.nodes = np.asarray(m.nodes) @ R.T
    n = R @ np.array([0, 0, 1.0])          # Normale der Fuge
    for k in (12, 13, 14, 15):
        m.load_node(k, Fx=-F_LAST / 4 * n[0], Fy=-F_LAST / 4 * n[1], Fz=-F_LAST / 4 * n[2])
    r, _n = loesen(m)
    t = teile(r)
    check("auch die geneigte Platte wird genannt", len(t) == 1 and t[0]["namen"] == ["Oben"],
          str([e.get("namen") for e in t]))
    if not t:
        return
    b = t[0]["bewegung"]
    check("die Ebene wird über ihre Normale genannt, nicht als x und y",
          "senkrecht zu (0.50, 0.00, 0.87)" in b and "(x, y)" not in b, b)
    check("die Drehung auch (um die Normale)", "um (0.50, 0.00, 0.87)" in b, b)


# --------------------------------------------------------------------------
# 5) Wie weit liegt ein gesundes Modell von der Schwelle?
# --------------------------------------------------------------------------
def test_gesunde_modelle_haben_einen_haufen():
    """Die Schwelle der Haufentrennung (PIVOT_DEKADEN, PIVOT_TRENNUNG) ist gemessen.

    Gesunde Modelle (keine gestoerten Pivots) bekommen zufaellige rechte Seiten
    wie in der Suche; ihre Antworten duerfen keinen zweiten, um Zehnerpotenzen
    hoeheren Haufen bilden. Zum Vergleich die Modelle mit freien Teilen: dort
    liegen die Haufen 14 und mehr Zehnerpotenzen auseinander. Beide Zahlen
    stehen in der Ausgabe.
    """
    gemessen = {}
    for name in ("frame", "plate", "solid", "truss", "hall", "gate"):
        m = build_example(name)
        sys_ = solver.StaticSystem(m)
        ls = sys_.solver
        A = sg.zufallsantworten(m, sys_.fi, ls, 4)
        a = np.sqrt((A[:, :, :3] ** 2).sum(axis=(0, 2)))
        maske, abstand, trennung = sg.verstaerkte_knoten(a)
        spanne = float(np.log10(a[a > 0].max() / a[a > 0].min()))
        gemessen[name] = (abstand, trennung)
        check(f"Beispiel {name}: kein zweiter Haufen (Spanne {spanne:.1f} Dekaden)",
              not maske.any(), f"Abstand {abstand:.2f} Dekaden, Trennung {trennung:.2f}")
    check(f"die gesunden Modelle liegen unter den Schwellen ({sg.PIVOT_DEKADEN:g} Dekaden / {sg.PIVOT_TRENNUNG:g})",
          all(ab < sg.PIVOT_DEKADEN or tr < sg.PIVOT_TRENNUNG for ab, tr in gemessen.values()),
          "; ".join(f"{k} {ab:.1f}/{tr:.2f}" for k, (ab, tr) in gemessen.items()))
    # Gegenstueck: Modelle mit freien Teilen (Pivots angehoben)
    for titel, m in (("Platte auf Block", auf_unterlage(last=-F_LAST)),
                     ("zwölf Platten", platten_auf_block(12)),
                     ("Stab am Anschlag", stab_mit_freiem_knoten())):
        s = solver.solve_static(m, case="LF1").info.get("freie_teile_suche") or {}
        check(f"{titel}: der obere Haufen liegt weit ueber den Schwellen",
              s.get("abstand_dekaden", 0.0) >= 2 * sg.PIVOT_DEKADEN,
              f"{s.get('abstand_dekaden', 0.0):.1f} Dekaden Abstand")


# --------------------------------------------------------------------------
# 6) Stab und Knoten
# --------------------------------------------------------------------------
def test_stabknoten_ohne_querhalt():
    m = stab_mit_freiem_knoten()
    r, _n = loesen(m)
    t = teile(r)
    check("der Knoten ohne Querhalt wird genannt", len(t) == 1, str(len(t)))
    if not t:
        return
    e = t[0]
    check("es ist ein Knoten an Staeben", e.get("art") == "stab", str(e.get("art")))
    check("der Stab S7 steht mit Namen da (die gesunde Kette H1-H4 nicht)",
          e.get("namen") == ["S7"], str(e.get("namen")))
    check("der Knoten steht mit seiner Nummer da", f"K{STAB_KNOTEN}" in e["text"], e["text"])
    check("quer zur Stabachse, in der Richtung dazwischen",
          e["bewegung"] == "quer zur Stabachse in Richtung (0.71, 0.00, -0.71) frei verschieblich",
          e["bewegung"])
    check("gehalten nur durch den Anschlag",
          "Fuge „Anschlag“" in e["haltung"], e["haltung"])
    check("eine WARNUNG-Zeile", len(warnzeilen(r)) == 1, str(warnzeilen(r)))


# --------------------------------------------------------------------------
# 6) Die Beispiele bleiben still
# --------------------------------------------------------------------------
def test_beispiele_ohne_meldung():
    for name in EXAMPLES:
        m = build_example(name)
        r = solver.solve_static(m, case=list(m.load_cases)[0])
        check(f"Beispiel {name}: keine freien Teile", not teile(r) and not warnzeilen(r),
              str(teile(r))[:60])


# --------------------------------------------------------------------------
# 7) Bitgleich und billig
# --------------------------------------------------------------------------
def test_rechnung_bitgleich_und_billig():
    for name, bauen in (("Platte reibungsfrei", lambda: auf_unterlage(last=-F_LAST)),
                        ("zwölf Platten", lambda: platten_auf_block(12)),
                        ("Stab ohne Querhalt", stab_mit_freiem_knoten),
                        ("Platte mit Reibung", lambda: auf_unterlage(last=-F_LAST, mu=0.3))):
        r_an, n_an = loesen(bauen(), an=True)
        r_aus, n_aus = loesen(bauen(), an=False)
        check(f"{name}: Verschiebungen bitgleich mit und ohne Suche",
              np.array_equal(r_an.u, r_aus.u), f"max |du| = {float(np.abs(r_an.u - r_aus.u).max()):g}")
        check(f"{name}: Auflagerkräfte bitgleich",
              np.array_equal(r_an.reactions, r_aus.reactions), "")
        extra = n_an - n_aus
        gefunden = bool(teile(r_an))
        check(f"{name}: höchstens sechs zusätzliche Lösungen" if gefunden
              else f"{name}: keine zusätzliche Lösung",
              (1 <= extra <= 6) if gefunden else extra == 0,
              f"{extra} zusätzlich ({n_an} gegen {n_aus})")
        check(f"{name}: ohne Suche kein Eintrag", not teile(r_aus), "")


def main():
    for f in (test_platte_reibungsfrei_wird_genannt, test_bericht_fuehrt_die_teile_auf,
              test_bericht_sagt_nur_wahres_zur_hilfsfesselung, test_gesamtanalyse_buendelt,
              test_kombination_traegt_die_teile, test_gehalten_keine_meldung,
              test_viele_platten_eine_zeile, test_schiefe_ebene_nennt_die_normale,
              test_gesunde_modelle_haben_einen_haufen,
              test_stabknoten_ohne_querhalt, test_beispiele_ohne_meldung,
              test_rechnung_bitgleich_und_billig):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
