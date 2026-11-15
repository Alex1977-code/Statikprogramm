"""
Hinweis Biegedrillknicken je Kombination, Runde k10 (15.11.2026, vom
Anwender freigegeben). Kein Verfahrensstand: es aendert sich nur ein Hinweis.

Bis zu diesem Stand galt ein I-Stab mit den Haken „Nachweis nach EC3“ und
„Biegedrillknicken“ als erfasst, sobald sein Nachweis in an.design ohne
Fehler stand (solver._bdk_hinweise_sammeln: gefuehrt = alle Staebe aus
an.design.members ohne fehler) - und das fuer **jede** Kombination nach
Theorie II. Ordnung und alpha_cr. Der EC3-Nachweis fuehrt aber nur die
GZT-Kombinationen (ec3.design._uls_results: is_uls, Ergebniskombinationen
je Alternative, Lastfaelle nur ohne jede Kombination im Modell) bzw. die
ausgewaehlten (check_members(combos=...)). In einer GZG-Kombination nach
Theorie II. Ordnung oder einem Lastfall nach Theorie II. Ordnung neben
Kombinationen lief kein chi_LT, der Hinweis fehlte dort trotzdem.

Jetzt zaehlt ein Stab je Kombination nur als erfasst, wenn sein
Stabilitaetsnachweis (chi_LT, MemberCheck.stability[...]["combo"]) genau
diese Kombination gefuehrt hat; zusammengefasste gleiche Eintraege („EK1 [1]
= EK2 [1]“) gelten fuer alle ihre Namen (DesignResults.gleiche).

Beispiel: IPE 300, 6 m, Gabellager, N = 200 kN, M = 60 kNm (wie
tests.test_bdk_hinweis_k8, Beispiel A).

Aufruf:  python -m tests.test_bdk_kombination_k10
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []

KENNUNG = "enthalten kein Biegedrillknicken"
T1 = "1 Stab mit Druck und Biegung: T1."


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def _ipe(lf_theorie=""):
    """IPE 300, 6 m, Gabellager, N = 200 kN, M = 60 kNm; Stab T1 mit
    Nachweis nach EC3 und Haken Biegedrillknicken."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("A")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-200e3)
    m.load_node(ids[0], My=60e3)
    m.load_node(ids[-1], My=-60e3)
    mem = m.add_member("T1", list(range(6)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = False
    m.load_cases[m.active_case].theorie = lf_theorie
    return m


def _rechnen(m, design=True):
    from statik3d import solver
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, design=design, progress=lambda t, *a: zeilen.append(str(t)))
    return an, zeilen


def _bdk(an, name):
    """Die Hinweiszeilen Biegedrillknicken der Kombination ``name``."""
    info = (getattr(an.theorie2, "kombinationen", None) or {}).get(name)
    return None if info is None else [h for h in info.hinweise if KENNUNG in h]


def _t1(zeilen):
    return bool(zeilen) and len(zeilen) == 1 and T1 in zeilen[0]


def _zeile_t1(an):
    z = an.info.get("bdk_hinweis") or []
    return len(z) == 1 and T1 in z[0] and T1 in an.summary()


def _chi_lt(an, kombi):
    mc = an.design.members.get("T1") if an.design is not None else None
    return mc is not None and any(s.get("combo") == kombi for s in mc.stability)


# --------------------------------------------------------------------------
def test_gzg():
    """GZT- und GZG-Kombination nach Theorie II. Ordnung: der Nachweis fuehrt
    nur die GZT-Kombination."""
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {lf: 1.0}, "SLS", theorie="II")
    an, z = _rechnen(m)
    check("GZT K1 und GZG K2 nach Th. II mit Nachweisen: χ_LT nur in K1 geführt",
          _chi_lt(an, "K1") and not _chi_lt(an, "K2") and an.design.combinations == ["K1"],
          f"{an.design.combinations}")
    check("GZT K1: kein Hinweis (χ_LT dort geführt)", _bdk(an, "K1") == [], _bdk(an, "K1"))
    check("GZG K2: Hinweis nennt T1 (dort kein Nachweis)", _t1(_bdk(an, "K2")), _bdk(an, "K2"))
    check("GZG K2: eine Zeile je Rechnung mit T1 in an.info, Zusammenfassung und Protokoll",
          _zeile_t1(an) and sum(KENNUNG in x for x in z) == 1, an.info.get("bdk_hinweis"))


def test_lastfall_neben_kombination():
    """Lastfall nach Theorie II. Ordnung, das Modell hat Kombinationen: der
    Nachweis fuehrt die Kombination, nicht den Lastfall."""
    m = _ipe(lf_theorie="II")
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    an, z = _rechnen(m)
    check("Lastfall nach Th. II neben GZT-Kombination K1: Hinweis beim Lastfall nennt T1",
          _t1(_bdk(an, lf)) and not _chi_lt(an, lf), _bdk(an, lf))
    check("... K1 ohne Hinweis", _bdk(an, "K1") == [], _bdk(an, "K1"))
    check("... die Zeile je Rechnung nennt T1", _zeile_t1(an), an.info.get("bdk_hinweis"))
    # Schutz: ohne jede Kombination fuehrt der Nachweis die Lastfaelle
    m = _ipe(lf_theorie="II")
    lf = m.active_case
    an, z = _rechnen(m)
    check("Schutz: nur Lastfall nach Th. II, keine Kombination: Nachweis führt den Lastfall, kein Hinweis",
          _chi_lt(an, lf) and _bdk(an, lf) == [] and not an.info.get("bdk_hinweis"),
          _bdk(an, lf))


def test_ausgewaehlt():
    """Nachweis nur fuer ausgewaehlte Kombinationen (check_members(combos=...))."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {lf: 1.35}, "ULS", theorie="II")
    an, z = _rechnen(m, design=False)
    with contextlib.redirect_stdout(io.StringIO()):
        an.design = check_members(m, an, combos=["K1"])
    solver._bdk_hinweise_sammeln(an)
    check("Nachweis nur für K1 ausgewählt: K1 ohne Hinweis, K2 nennt T1",
          _bdk(an, "K1") == [] and _t1(_bdk(an, "K2")) and _zeile_t1(an),
          f"K1 {_bdk(an, 'K1')} K2 {_bdk(an, 'K2')}")


def test_nachtraeglich():
    """Erst ohne Nachweise rechnen, dann die Nachweise allein starten (GUI
    _design_done, Web start_design), dann wieder ohne."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {lf: 1.0}, "SLS", theorie="II")
    an, z = _rechnen(m, design=False)
    vorher = (_bdk(an, "K1"), _bdk(an, "K2"))
    check("ohne Nachweise: K1 und K2 nennen T1", _t1(vorher[0]) and _t1(vorher[1]), vorher)
    with contextlib.redirect_stdout(io.StringIO()):
        an.design = check_members(m, an)
    solver._bdk_hinweise_sammeln(an)
    check("Nachweise nachträglich: K1 ohne Hinweis, GZG K2 behält T1 (einmal)",
          _bdk(an, "K1") == [] and _t1(_bdk(an, "K2")) and _zeile_t1(an),
          f"K1 {_bdk(an, 'K1')} K2 {_bdk(an, 'K2')}")
    an.design = None
    solver._bdk_hinweise_sammeln(an)
    check("Nachweise wieder entfernt: K1 und K2 nennen T1 je einmal",
          _t1(_bdk(an, "K1")) and _t1(_bdk(an, "K2")) and _zeile_t1(an),
          f"K1 {_bdk(an, 'K1')} K2 {_bdk(an, 'K2')}")


def test_abbruch():
    """Abbruch in den Nachweisen: kein Nachweis gelaufen, alle nennen T1."""
    from statik3d import solver

    class Halt(Exception):
        pass

    def p(t, *a):
        if str(t).startswith("Nachweise EC3"):
            raise Halt("Abbruch")
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {lf: 1.0}, "SLS", theorie="II")
    teil = None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            solver.solve_all(m, workers=1, design=True, progress=p)
    except Halt as ex:
        teil = getattr(ex, "teilanalyse", None)
    check("Abbruch in den Nachweisen: K1 und K2 nennen T1, Zeile in der Teilanalyse",
          teil is not None and _t1(_bdk(teil, "K1")) and _t1(_bdk(teil, "K2")) and _zeile_t1(teil),
          None if teil is None else teil.info.get("bdk_hinweis"))


def test_ergebniskombination():
    """Ergebniskombinationen: GZT-Alternativen gefuehrt (auch zusammengefasste
    gleiche Eintraege), GZG-Alternativen nicht."""
    m = _ipe()
    lf = m.active_case
    m.add_combination("EK1", {}, "ULS", theorie="II", alternativen=[{lf: 1.0}, {lf: 1.2}])
    m.add_combination("EK2", {}, "ULS", theorie="II", alternativen=[{lf: 1.0}])
    m.add_combination("EK3", {}, "SLS", theorie="II", alternativen=[{lf: 1.0}])
    an, z = _rechnen(m)
    gl = getattr(an.design, "gleiche", {}) or {}
    check("gleiche GZT-Alternativen EK1 [1] und EK2 [1] im Nachweis zusammengefasst",
          any(set(v) >= {"EK1 [1]", "EK2 [1]"} for v in gl.values()), gl)
    check("GZT-Alternativen EK1 [1], EK1 [2], EK2 [1]: kein Hinweis",
          all(_bdk(an, k) == [] for k in ("EK1 [1]", "EK1 [2]", "EK2 [1]")),
          {k: _bdk(an, k) for k in ("EK1 [1]", "EK1 [2]", "EK2 [1]")})
    check("GZG-Alternative EK3 [1]: Hinweis nennt T1, Zeile je Rechnung nennt T1",
          _t1(_bdk(an, "EK3 [1]")) and _zeile_t1(an), _bdk(an, "EK3 [1]"))


def test_alle_gzt():
    """Schutz: alle Kombinationen GZT mit Nachweis - kein Hinweis (wie bisher)."""
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS", theorie="II")
    m.add_combination("K2", {lf: 1.35}, "ULS", theorie="II")
    an, z = _rechnen(m)
    check("Schutz: K1 und K2 GZT mit Nachweisen: kein Hinweis, keine Zeile",
          _bdk(an, "K1") == [] and _bdk(an, "K2") == [] and not an.info.get("bdk_hinweis")
          and not any(KENNUNG in x for x in z) and KENNUNG not in an.summary(),
          an.info.get("bdk_hinweis"))


def main():
    for t in (test_gzg, test_lastfall_neben_kombination, test_ausgewaehlt, test_nachtraeglich,
              test_abbruch, test_ergebniskombination, test_alle_gzt):
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
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
