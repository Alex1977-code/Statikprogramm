"""
Ergebnisstatus nach Korrekturen am Kombinationsgenerator, Theorie III und
Kommandozeile (Befunde 41, 42, 44, 45, 46 der Pruefagenten, 11.11.2026).

41  ξ in Regel 6.10b (Korrektur A6 vom 09.11.2026): die Faktoren stehen in den
    gespeicherten Kombinationen. Der Status riet „neu rechnen“, und nach dem
    Neurechnen war er weg - mit unveraenderten falschen Faktoren (LF2 = P mit
    0,85 statt 1,0). Jetzt erkennt das Modell selbst die alten Faktoren; der
    Status raet „Kombinationen neu erzeugen“ und bleibt nach dem Neurechnen,
    bis die Kombinationen neu erzeugt sind.
42  DIN-19704-Lastfall in keiner EN-1990-Kombination (A5): derselbe Mangel -
    der Status verschwand mit dem Neurechnen (Einfeldtraeger 6 m, G 10 kN/m,
    G_A 5 kN/m: Bemessungsmoment 60,75 statt 91,13 kNm, ohne Hinweis).
44  Erdbeben und Montage: der alte Generator liess sie ebenso still weg; das
    Merkmal kannte sie nicht - kein Status. Jetzt: in keiner Kombination des
    Modells -> Status mit dem Weg ueber „DIN 19704“ oder von Hand.
45  Ein Ergebnis nach Theorie III. Ordnung („III. Ordnung“ beginnt mit „II“)
    galt als „alpha_cr bzw. Theorie II. Ordnung“ und bekam den Status der
    Korrekturen 16 b (Versatz) und A7 (Gelenke), die Theorie III nie betrafen.
46  ``--kombinationen`` fing KombinationGesperrt nicht: Traceback statt Meldung.

Aufruf:  python -m tests.test_kur_status
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:92s} {detail}")
    return ok


def _ordner():
    return tempfile.mkdtemp(prefix="kur_status_")


def _traeger(lager_all=False):
    """Einfeldtraeger 6 m aus IPE 300, G 10 kN/m (LF1)."""
    from statik3d import mesher
    from statik3d.model import Material, Model, Section
    m = Model("T")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    if lager_all:
        m.fix(int(ids[0]), "all")
        m.fix(int(ids[-1]), "all")
    else:
        m.fix(int(ids[0]), [0, 1, 2, 3])
        m.fix(int(ids[-1]), [1, 2])
        for n in range(m.nn):
            m.fix(n, [1, 3])
    m.case().category = "G"
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-10e3)
    return m, ids


def _status(an) -> str:
    return str((getattr(an, "info", None) or {}).get("verfahren_betroffen") or "")


def _als_alte_datei(pe, m, stand=7):
    """Die Ergebnisdatei so, wie sie ein Programm vom Stand ``stand`` schrieb (nur
    die Merkmale bis zu diesem Stand)."""
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    with open(pe, "rb") as fh:
        inhalt = erg._Leser(fh, m).load()
    v = inhalt["verfahren"]
    v["stand"] = stand
    v["merkmale"] = {k: w for k, w in v["merkmale"].items() if rv.merkmal(k).wechsel[-1].stand <= stand}
    with open(pe, "wb") as fh:
        erg._Schreiber(fh, m).dump(inhalt)


def _rechnen_schreiben_lesen(m, pe):
    from statik3d import ergebnisse as erg, solver
    an = solver.solve_all(m, workers=1, design=False)
    erg.schreiben(pe, m, an)
    return an, erg.lesen(pe, m)


# ---------------------------------------------------------------------------
# 41  ξ in 6.10b
# ---------------------------------------------------------------------------
def _xi_modell():
    from statik3d.combinations import generate_combinations
    m, ids = _traeger()
    m.add_load_case("LF2", "P", "Vorspannung", nummer=2)
    m.load_node(int(ids[-1]), Fx=-100e3, case="LF2")
    m.add_load_case("LF3", "Q", "Nutzlast", nummer=3)
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-5e3, case="LF3")
    m.design.combination_rule = "6.10ab"
    generate_combinations(m)
    return m


def _xi_wie_vor_dem_0911(m):
    """So erzeugte der Generator bis zum 09.11.2026: ξ auf jeden staendigen Faktor
    (P und, in „G guenstig“, das guenstige G), mit seinem Fingerabdruck."""
    xi = m.design.xi
    for c in m.combinations.values():
        if "6.10b" in str(c.description):
            guenstig = "G guenstig" in str(c.description)
            for k in list(c.factors):
                if k == "LF2" or (guenstig and k == "LF1"):
                    c.factors[k] = round(c.factors[k] * xi, 6)
            c.als_erzeugt("EN 1990")
    return {n: dict(c.factors) for n, c in m.combinations.items() if "6.10b" in str(c.description)}


def test_xi_status_bleibt():
    from statik3d import rechenverfahren as rv
    from statik3d.combinations import generate_combinations
    from statik3d.model import Model
    d = _ordner()
    m = _xi_modell()
    alt = _xi_wie_vor_dem_0911(m)
    lk = sorted(alt)
    check("Ausgang: 6.10b-Faktoren wie vor dem 09.11.2026 (LF2 = P mit 0,85)",
          all(abs(f["LF2"] - 0.85) < 1e-9 for f in alt.values()), str(alt))
    pm, pe = os.path.join(d, "xi.s3d"), os.path.join(d, "xi.ergebnisse")
    m.save(pm)
    m = Model.load(pm)
    an, _ = _rechnen_schreiben_lesen(m, pe)
    _als_alte_datei(pe, m)
    from statik3d import ergebnisse as erg
    a_alt = erg.lesen(pe, m)
    s = _status(a_alt)
    check("alte Datei (Stand 7): Status nennt ξ, die Kombinationen und „Kombinationen neu erzeugen“",
          s.startswith(rv.BETROFFEN) and "ξ in Regel 6.10b" in s and all(n in s for n in lk)
          and "Kombinationen neu erzeugen" in s, s[:200])
    check("neue Rechnung mit denselben Kombinationen: Status bleibt (vorher: kein Status)",
          "ξ in Regel 6.10b" in _status(an) and "Kombinationen neu erzeugen" in _status(an), _status(an)[:160])
    check("… und steht in der Zusammenfassung", "ξ in Regel 6.10b" in an.summary())
    _, a_neu = _rechnen_schreiben_lesen(m, pe)
    check("neu gerechnet, geschrieben, gelesen: Status bleibt (vorher: None)",
          "ξ in Regel 6.10b" in _status(a_neu), repr(_status(a_neu)[:160]))
    check("… die Faktoren sind tatsächlich noch die alten (LF2 0,85)",
          all(abs(m.combinations[n].factors["LF2"] - 0.85) < 1e-9 for n in lk))
    # der Anwender folgt dem Rat: Kombinationen neu erzeugen, dann rechnen
    generate_combinations(m)
    neu = {n: dict(c.factors) for n, c in m.combinations.items() if "6.10b" in str(c.description)}
    check("Kombinationen neu erzeugt: LF2 = P mit 1,0 in jeder 6.10b-Kombination",
          all(abs(f["LF2"] - 1.0) < 1e-9 for f in neu.values()), str(neu))
    an3, a3 = _rechnen_schreiben_lesen(m, pe)
    check("… danach weder bei der Rechnung noch beim Lesen ein Status",
          "ξ" not in _status(an3) and "ξ" not in _status(a3), _status(an3)[:120] + " | " + _status(a3)[:120])


def test_xi_unberuehrt():
    from statik3d import rechenverfahren as rv
    d = _ordner()
    m = _xi_modell()
    pe = os.path.join(d, "xi_neu.ergebnisse")
    an, _ = _rechnen_schreiben_lesen(m, pe)
    _als_alte_datei(pe, m)
    from statik3d import ergebnisse as erg
    a_alt = erg.lesen(pe, m)
    check("richtig erzeugte 6.10b-Kombinationen: kein Status, auch nicht für eine Datei vom Stand 7",
          not _status(an) and "ξ" not in _status(a_alt), _status(a_alt)[:160])
    check("Merkmal „kombination_xi“: betrifft (6.10b im Modell) ja, im Modell kein Mangel",
          rv.merkmal("kombination_xi").betrifft(m) and rv._xi_im_modell(m) == "")
    # von Hand geaendert (ohne Fingerabdruck des Generators): der Generator ersetzt sie nicht
    m2 = _xi_modell()
    for c in m2.combinations.values():
        if "6.10b" in str(c.description):
            c.factors["LF2"] = round(c.factors["LF2"] * m2.design.xi, 6)
    t = rv._xi_im_modell(m2)
    check("von Hand geänderte Kombinationen mit den alten Faktoren: Status sagt „die Faktoren prüfen“",
          "Faktoren prüfen" in t and "neu erzeugen" in t, t[:200])
    # nur die Ergebnisse der betroffenen Kombinationen: ohne gerechnete Kombination kein Status
    from statik3d import solver
    m3 = _xi_modell()
    _xi_wie_vor_dem_0911(m3)
    an3 = solver.solve_all(m3, workers=1, design=False, combinations=False)
    check("nur Lastfälle gerechnet (keine Kombination): kein Status",
          not _status(an3) and rv.modell_betroffen(m3, an3) == "", _status(an3)[:120])


# ---------------------------------------------------------------------------
# 42  DIN-19704-Lastfall fehlt in den EN-1990-Kombinationen
# ---------------------------------------------------------------------------
def test_din19704_status_bleibt():
    import numpy as np
    from statik3d import ergebnisse as erg, rechenverfahren as rv, solver
    from statik3d.combinations import generate_combinations
    from statik3d.model import Model
    d = _ordner()
    m, _ids = _traeger()
    m.add_load_case("LF2", "G_A", "Ausruestung", nummer=2)
    for e in range(len(m.elements)):
        m.load_beam(e, qz=-5e3, case="LF2")
    generate_combinations(m)
    # wie der Generator vor dem 09.11.2026: LF2 (G_A) in keiner Kombination
    for c in m.combinations.values():
        c.factors.pop("LF2", None)
        c.als_erzeugt("EN 1990")
    pm, pe = os.path.join(d, "eft.s3d"), os.path.join(d, "eft.ergebnisse")
    m.save(pm)
    m = Model.load(pm)
    an, a = _rechnen_schreiben_lesen(m, pe)
    my = min(float(np.min(solver.beam_station_forces(m, r, i)["My"]))
             for r in an.combinations.values() for i in range(len(m.elements)))
    check("Ausgang: Bemessungsmoment 60,75 kNm ohne G_A (mit G_A 91,13)", abs(my / 1e3 + 60.75) < 0.01,
          f"{my / 1e3:.2f} kNm")
    check("neue Rechnung: Status nennt LF2 und „Kombinationen neu erzeugen“ (vorher: kein Status)",
          "DIN 19704" in _status(an) and "LF2" in _status(an) and "Kombinationen neu erzeugen" in _status(an),
          _status(an)[:200])
    check("… geschrieben und gelesen: Status bleibt (vorher: None)",
          "LF2" in _status(a) and _status(a).startswith(rv.BETROFFEN), _status(a)[:160])
    check("… Zusammenfassung nennt LF2 (vorher: nein)", "LF2" in an.summary())
    generate_combinations(m)
    an2, a2 = _rechnen_schreiben_lesen(m, pe)
    my2 = min(float(np.min(solver.beam_station_forces(m, r, i)["My"]))
              for r in an2.combinations.values() for i in range(len(m.elements)))
    check("Kombinationen neu erzeugt: Bemessungsmoment 91,13 kNm, kein Status mehr",
          abs(my2 / 1e3 + 91.125) < 0.01 and "DIN 19704" not in _status(an2) and "DIN 19704" not in _status(a2),
          f"{my2 / 1e3:.2f} kNm | {_status(a2)[:100]}")


# ---------------------------------------------------------------------------
# 44  Erdbeben und Montage
# ---------------------------------------------------------------------------
def test_erdbeben_montage():
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    from statik3d.combinations import generate_combinations
    from statik3d.model import Combination
    d = _ordner()
    for kat, text in (("ERD", "Erdbeben"), ("MONT", "Montage")):
        m, ids = _traeger(lager_all=True)
        m.add_load_case("LF2", "Q", "Nutzlast", nummer=2)
        for e in range(len(m.elements)):
            m.load_beam(e, qz=-5e3, case="LF2")
        generate_combinations(m)    # so lief der alte Generator auch mit LF3: er liess ihn weg
        m.add_load_case("LF3", kat, text, nummer=3)
        m.load_node(int(ids[3]), Fy=50e3, case="LF3")
        pe = os.path.join(d, f"{kat}.ergebnisse")
        an, _ = _rechnen_schreiben_lesen(m, pe)
        _als_alte_datei(pe, m)
        a = erg.lesen(pe, m)
        s = _status(a)
        check(f"{text}: alte Datei (Stand 7) trägt den Status, nennt LF3 und den Weg über „DIN 19704“ "
              "(vorher: None)",
              s.startswith(rv.BETROFFEN) and "LF3" in s and "DIN 19704" in s, s[:200])
        check(f"{text}: neue Rechnung ebenso, Zusammenfassung nennt LF3",
              "LF3" in _status(an) and "LF3" in an.summary(), _status(an)[:120])
        # der Anwender legt die Kombination von Hand an (oder mit „DIN 19704“)
        m.combinations["K_ERD"] = Combination("K_ERD", {"LF1": 1.0, "LF3": 1.0}, "ACC")
        check(f"{text}: mit einer Kombination, die LF3 enthält, kein Status mehr",
              rv.modell_betroffen(m) == "", rv.modell_betroffen(m)[:120])


# ---------------------------------------------------------------------------
# 45  Theorie III ist nicht Theorie II
# ---------------------------------------------------------------------------
def test_theorie3_nicht_theorie2():
    import math
    from types import SimpleNamespace as NS
    from statik3d import ergebnisse as erg, rechenverfahren as rv, solver
    from statik3d.model import Material, Model, Section

    def an_(theorie):
        a = NS(cases={"LF1": NS(info={"theorie": theorie}, kind="case")}, combinations={}, alternativen={},
               theorie2=None, theorie3=None)
        a.all_results = lambda: dict(a.cases)
        return a
    check("Prüffunktion alpha_cr/Theorie II: „III. Ordnung“ - nicht betroffen (vorher: LF1)",
          rv._alpha_cr_im_ergebnis(an_("III. Ordnung")) == "", rv._alpha_cr_im_ergebnis(an_("III. Ordnung")))
    check("… „II. Ordnung“ - betroffen (LF1)", "LF1" in rv._alpha_cr_im_ergebnis(an_("II. Ordnung")))
    # Druckstab mit Versatz 0,2 m nach Theorie III (Nachweis des Befunds)
    E, I, L, n = 210e9, 1e-4, 4.0, 8
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1.0, Iy=I, Iz=50 * I, It=1e-5, zmax=0.1, ymax=0.05))
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    els = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q", exzentrizitaet=[[0, 0.2, 0], [0, 0.2, 0]])
           for k in range(n)]
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-0.3 * math.pi ** 2 * E * I / L ** 2)
    for e in els:
        m.load_beam(e, qz=-1e3)
    m.load_cases["LF1"].theorie = "III"
    m.design.imperfektionen = False
    pe = os.path.join(_ordner(), "th3.ergebnisse")
    an, _ = _rechnen_schreiben_lesen(m, pe)
    _als_alte_datei(pe, m)
    a = erg.lesen(pe, m)
    s = _status(a)
    check("Druckstab mit Versatz nur nach Theorie III, Datei vom Stand 7: kein Status „mit Versatz“ "
          "(vorher: alpha_cr bzw. Theorie II. Ordnung: LF1)",
          str(an.cases["LF1"].info.get("theorie")) == "III. Ordnung" and "Versatz" not in s
          and "Theorie II. Ordnung: LF1" not in s, s[:200])


# ---------------------------------------------------------------------------
# 46  --kombinationen mit Erdbeben
# ---------------------------------------------------------------------------
def test_cli_kombinationen_gesperrt():
    from statik3d import cli, examples_lib as ex
    m = ex.frame_example()
    m.case().category = "G"
    m.add_load_case("LF2", "ERD", "Erdbeben", nummer=2)
    m.load_node(1, Fx=1e3, case="LF2")
    p = os.path.join(_ordner(), "erd.json")
    m.save(p)
    fehler, aus = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stderr(fehler), contextlib.redirect_stdout(aus):
            rc = cli.main([p, "--kombinationen", "--still"])
        ausnahme = ""
    except BaseException as exc:         # noqa: BLE001 - genau das ist der Befund
        rc, ausnahme = None, f"{type(exc).__name__}: {str(exc)[:80]}"
    t = fehler.getvalue()
    check("CLI --kombinationen mit Erdbeben-Lastfall: keine Ausnahme, Rückgabe 2 (vorher: KombinationGesperrt)",
          not ausnahme and rc == 2, ausnahme or f"rc {rc}")
    check("… Meldung auf Deutsch nennt LF2, Erdbeben und den Weg über „DIN 19704“, kein Traceback",
          "LF2" in t and "Erdbeben" in t and "DIN 19704" in t and "Traceback" not in t + aus.getvalue(), t[:160])


def main():
    for t in (test_xi_status_bleibt, test_xi_unberuehrt, test_din19704_status_bleibt, test_erdbeben_montage,
              test_theorie3_nicht_theorie2, test_cli_kombinationen_gesperrt):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    print("PySide6 geladen:", "PySide6" in sys.modules)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                    # noqa: BLE001
        pass
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
