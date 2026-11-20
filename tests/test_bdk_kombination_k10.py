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


KNICK_T1 = ("Die Knickfaktoren enthalten kein Biegedrillknicken (Momentenglied der geometrischen "
            "Steifigkeit fehlt): 1 Stab mit Druck und Biegung: T1.")


def _knicken(m, **kw):
    from statik3d import solver
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_buckling(m, 2, lambda t, *a: zeilen.append(str(t)), **kw)
    return r, zeilen


def _knick_t1(r):
    z = r.info.get("bdk_hinweis") or []
    return len(z) == 1 and KNICK_T1 in z[0] and r.summary().count(KENNUNG) == 1


def _knick_kein(r):
    return not r.info.get("bdk_hinweis") and KENNUNG not in r.summary()


def test_knicken():
    """Runde k10b: Die Knickfaktoren (solve_buckling) zaehlten einen I-Stab
    mit den Haken EC3 und Biegedrillknicken als erfasst, ohne dass ein
    Nachweis lief (bdk_hinweis.hinweis mit ec3=True) - der Hinweis fehlte
    still. Jetzt dieselbe Regel wie nach Theorie II. Ordnung: erfasst nur,
    wo der chi_LT-Nachweis den Grundzustand des Knickens gefuehrt hat."""
    from statik3d import solver
    m = _ipe()
    r, z = _knicken(m, case=m.active_case)
    check("Knicken allein (kein Nachweis gelaufen), T1 mit Haken EC3/BDK: Hinweis nennt T1 "
          "in res.info, Zusammenfassung und Protokoll",
          _knick_t1(r) and sum(KNICK_T1 in x for x in z) == 1,
          f"{r.info.get('bdk_hinweis')} | " + " | ".join(x for x in z if KENNUNG in x)[:160])
    # Grundzustand GZT-Kombination K1; die Analyse mit Nachweisen fuehrt K1
    m = _ipe()
    lf = m.active_case
    m.add_combination("K1", {lf: 1.0}, "ULS")
    m.add_combination("K2", {lf: 1.0}, "SLS")
    an, _z = _rechnen(m)
    r1, _ = _knicken(m, combination="K1")
    r2, _ = _knicken(m, combination="K2")
    ra, _ = _knicken(m, case="all")
    check("Knicken K1 und K2 vor dem Zuordnen der Nachweise: beide nennen T1",
          _knick_t1(r1) and _knick_t1(r2), f"{r1.info.get('bdk_hinweis')} | {r2.info.get('bdk_hinweis')}")
    for r in (r1, r2, ra):
        solver._bdk_nach_nachweisen(an, r)
    check("Nachweise mit χ_LT in K1 geführt: Knicken K1 ohne Hinweis",
          _chi_lt(an, "K1") and _knick_kein(r1), r1.info.get("bdk_hinweis"))
    check("GZG K2 (kein Nachweis): Knicken K2 nennt T1 weiterhin (einmal)",
          not _chi_lt(an, "K2") and _knick_t1(r2), r2.info.get("bdk_hinweis"))
    check("Grundzustand „alle Lastfälle“ (kein Nachweis dieses Zustands): nennt T1", _knick_t1(ra),
          ra.info.get("bdk_hinweis"))
    an.design = None
    solver._bdk_nach_nachweisen(an, r1)
    check("Nachweise wieder entfernt: Knicken K1 nennt T1 wieder, genau einmal", _knick_t1(r1),
          r1.info.get("bdk_hinweis"))
    # Lastfall neben Kombinationen: der Nachweis fuehrt den Lastfall nicht
    an2, _z = _rechnen(m)
    rl, _ = _knicken(m, case=lf)
    solver._bdk_nach_nachweisen(an2, rl)
    check("Knicken Lastfall neben Kombinationen: der Nachweis führt ihn nicht, Hinweis nennt T1",
          _knick_t1(rl), rl.info.get("bdk_hinweis"))
    # Nachweis nicht gefuehrt (Werkstoff ohne f_y): erfasst nichts
    from statik3d.model import Material
    m = _ipe()
    m.add_material(Material("OHNEFY", E=210e9, nu=0.3, rho=0.0))
    for e in m.elements:
        e.mat = "OHNEFY"
    m.add_combination("K1", {m.active_case: 1.0}, "ULS")
    an3, _z = _rechnen(m)
    r3, _ = _knicken(m, combination="K1")
    solver._bdk_nach_nachweisen(an3, r3)
    check("Knicken K1, EC3-Nachweis nicht geführt (Werkstoff ohne f_y): Hinweis nennt T1",
          bool(an3.design.members["T1"].fehler) and _knick_t1(r3), r3.info.get("bdk_hinweis"))
    # Schutz: Knickfaktoren unveraendert, nur der Hinweis
    m = _ipe()
    r, _ = _knicken(m, case=m.active_case)
    import numpy as np
    check("Schutz: Knickfaktoren am IPE 300 positiv und endlich (nur der Hinweis ändert sich)",
          bool(np.all(np.isfinite(r.buckling_factors))) and float(min(abs(r.buckling_factors))) > 0,
          [round(float(x), 4) for x in r.buckling_factors])


def test_knicken_web():
    """Web: Nachweise nach dem Knicken (start_design) und Knicken nach den
    Nachweisen (start_solve kind=buckling) bilden den Hinweis neu."""
    from statik3d.web import server
    m = _ipe()
    m.add_combination("K1", {m.active_case: 1.0}, "ULS")
    st = server.State(m)
    an, _z = _rechnen(m, design=False)
    st.analysis = an
    r, _ = _knicken(m, combination="K1")
    st.results = r
    vorher = _knick_t1(r)
    with contextlib.redirect_stdout(io.StringIO()):
        server.start_design(st)
        st.job.thread.join(300)
    check("Web: Knicken K1, dann Nachweise gestartet: Hinweis zu T1 verschwindet",
          vorher and st.job.status == "fertig" and _knick_kein(st.results),
          f"vorher {vorher} {st.job.status} {st.job.error} | {st.results.info.get('bdk_hinweis')}")
    # ohne Kombination fuehrt der Nachweis den Lastfall: Knicken danach ohne Hinweis,
    # mit Kombination daneben nennt das Knicken des Lastfalls T1
    for kombi, soll in ((False, False), (True, True)):
        m = _ipe()
        if kombi:
            m.add_combination("K1", {m.active_case: 1.0}, "ULS")
        st = server.State(m)
        st.analysis, _z = _rechnen(m)
        with contextlib.redirect_stdout(io.StringIO()):
            server.start_solve(st, {"kind": "buckling", "nmodes": 2})
            st.job.thread.join(300)
        rb = st.results
        ok = st.job.status == "fertig" and rb is not None and (_knick_t1(rb) if soll else _knick_kein(rb))
        check("Web: Knicken nach den Nachweisen, " + ("Lastfall neben K1: Hinweis nennt T1" if kombi else
              "nur Lastfall (Nachweis führt ihn): kein Hinweis"), ok,
              f"{st.job.status} {st.job.error} | {getattr(rb, 'info', {}).get('bdk_hinweis')}")


def _web_job(st, fn, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        fn(st, *a)
        st.job.thread.join(600)
    return st.job.status, st.job.error


def _lt_aus(st):
    from statik3d.web import server
    with contextlib.redirect_stdout(io.StringIO()):
        return server.apply_op(st, {"op": "set_member", "name": "T1", "fields": {"lt_check": False}})


def _mcr(an, name="T1"):
    mc = an.design.members[name]
    return [(s.get("combo"), (s.get("details") or {}).get("M_cr")) for s in mc.stability]


def test_ohne_chi_lt():
    """Nachbesserung k10b (Gegenpruefung, 15.11.2026): Ein Stabilitaets-
    eintrag zaehlte als gefuehrter chi_LT-Nachweis, obwohl chi_LT nicht lief.
    ec3.design.check_member legt ihn schon bei N_Ed > 0 an, auch ohne Haken
    Biegedrillknicken (details: M_cr = inf, chi_LT = 1). Nach set_member
    lt_check aus (nur invalidate("design")) bleiben Knickergebnis bzw.
    Analyse stehen; start_design liess dann den Hinweis still fallen."""
    import math
    from statik3d import solver
    from statik3d.web import server
    # W2: Web, nur Lastfall, Knicken, lt_check aus, Nachweise
    m = _ipe()
    st = server.State(m)
    st.analysis, _z = _rechnen(m, design=False)
    s1 = _web_job(st, server.start_solve, {"kind": "buckling", "nmodes": 2})
    r_vor = st.results
    vorher = _knick_t1(r_vor)
    _lt_aus(st)
    s2 = _web_job(st, server.start_design)
    eint = _mcr(st.analysis)
    ohne = bool(eint) and all(not math.isfinite(float(x)) for _c, x in eint)
    check("Web: Knicken LF1, set_member lt_check aus, Nachweise (χ_LT lief nicht, M_cr = inf): "
          "Hinweis nennt T1 weiter",
          s1[0] == "fertig" and s2[0] == "fertig" and vorher and st.results is r_vor and ohne
          and _knick_t1(st.results),
          f"{s1} {s2} vorher {vorher} Einträge {eint} | {st.results.info.get('bdk_hinweis')}")
    # dasselbe nach Theorie II. Ordnung (vorbestehend aus Runde k10)
    m = _ipe(lf_theorie="II")
    st = server.State(m)
    st.analysis, _z = _rechnen(m, design=False)
    vorher = _zeile_t1(st.analysis)
    _lt_aus(st)
    s2 = _web_job(st, server.start_design)
    check("Web: LF1 nach Th. II, set_member lt_check aus, Nachweise ohne χ_LT: Zeile nennt T1 weiter",
          vorher and s2[0] == "fertig" and _zeile_t1(st.analysis) and _t1(_bdk(st.analysis, m.active_case)),
          f"vorher {vorher} {s2} | {st.analysis.info.get('bdk_hinweis')}")
    # Solverweg: Knicken K1 mit Haken, Analyse mit Nachweisen ohne Haken
    m = _ipe()
    m.add_combination("K1", {m.active_case: 1.0}, "ULS")
    r1, _ = _knicken(m, combination="K1")
    m.members["T1"].lt_check = False
    an, _z = _rechnen(m)
    solver._bdk_nach_nachweisen(an, r1)
    check("Knicken K1 mit Haken, Nachweis K1 danach ohne Haken (Eintrag K1 mit M_cr = inf): nennt T1",
          any(c == "K1" for c, _x in _mcr(an)) and _knick_t1(r1),
          f"{_mcr(an)} | {r1.info.get('bdk_hinweis')}")
    # Schutz: chi_LT lief (M_cr endlich) -> erfasst, kein Hinweis
    m = _ipe()
    st = server.State(m)
    st.analysis, _z = _rechnen(m, design=False)
    _web_job(st, server.start_solve, {"kind": "buckling", "nmodes": 2})
    _web_job(st, server.start_design)
    eint = _mcr(st.analysis)
    check("Schutz: ohne Umschalten läuft χ_LT (M_cr endlich): Knick-Hinweis fällt weg",
          bool(eint) and all(math.isfinite(float(x)) and float(x) > 0 for _c, x in eint)
          and _knick_kein(st.results), f"{eint} | {st.results.info.get('bdk_hinweis')}")


def _web_op(st, op, **kw):
    from statik3d.web import server
    with contextlib.redirect_stdout(io.StringIO()):
        return server.apply_op(st, dict(op=op, **kw))


def _single_knick_t1(st):
    """Die Zusammenfassung des Einzelergebnisses im Browser (state_summary)."""
    from statik3d.web import server
    s = (server.state_summary(st).get("single") or {}).get("summary") or ""
    return KNICK_T1 in s and s.count(KENNUNG) == 1


def test_verworfen_web():
    """Nachbesserung 2 k10b (Gegenpruefung 2, 15.11.2026): Im Browser verwirft
    eine Aenderung an Stab- oder Nachweiseinstellungen (KEEP_DESIGN:
    set_member, design_settings, auto_members; Ermuedungslasten) nur die
    Nachweise (State.invalidate("design"/"ermuedung") -> an.design = None),
    Analyse und Knickergebnis bleiben stehen. Deren Hinweise Biegedrill-
    knicken beruhten weiter auf dem verworfenen Nachweis - der Hinweis fehlte
    still, obwohl kein Nachweis mehr vorlag. Jetzt bilden sie sich dabei neu."""
    from statik3d.web import server
    # Knicken nach den Nachweisen (nur Lastfall: der Nachweis fuehrt ihn), dann verwerfen
    for name, op, kw in (("set_member lt_check aus", "set_member",
                          {"name": "T1", "fields": {"lt_check": False}}),
                         ("set_member Nachweis aus", "set_member",
                          {"name": "T1", "fields": {"design": False}}),
                         ("design_settings", "design_settings",
                          {"fields": {"imperfektionen": False}}),
                         ("Ermüdungslast angelegt", "add_fatigue_load",
                          {"name": "E1", "case_max": None})):
        m = _ipe()
        if op == "add_fatigue_load":
            kw = dict(kw, case_max=m.active_case)
        st = server.State(m)
        st.analysis, _z = _rechnen(m)
        s1 = _web_job(st, server.start_solve, {"kind": "buckling", "nmodes": 2})
        r = st.results
        vorher = s1[0] == "fertig" and _knick_kein(r)
        _web_op(st, op, **kw)
        check(f"Web: Knicken nach den Nachweisen, dann {name} (Nachweise verworfen, nicht neu "
              "gestartet): Knick-Hinweis nennt T1 in res.info und state_summary",
              vorher and st.analysis is not None and st.analysis.design is None and st.results is r
              and _knick_t1(r) and _single_knick_t1(st),
              f"{s1} vorher ohne {vorher} | {r.info.get('bdk_hinweis')}")
    # Schutz: Nachweise danach neu gestartet -> chi_LT laeuft, Hinweis faellt wieder weg
    s2 = _web_job(st, server.start_design)
    check("Schutz: Nachweise danach neu gestartet (χ_LT läuft): Knick-Hinweis fällt wieder weg",
          s2[0] == "fertig" and _knick_kein(st.results), f"{s2} | {st.results.info.get('bdk_hinweis')}")
    # dasselbe nach Theorie II. Ordnung (Hinweis der Analyse, Runde k10)
    for name, fields in (("lt_check aus", {"lt_check": False}), ("Nachweis aus", {"design": False})):
        m = _ipe(lf_theorie="II")
        st = server.State(m)
        st.analysis, _z = _rechnen(m)
        an = st.analysis
        vorher = not an.info.get("bdk_hinweis") and not _bdk(an, m.active_case)
        _web_op(st, "set_member", name="T1", fields=fields)
        check(f"Web: LF1 nach Th. II mit Nachweisen, dann set_member {name} (Nachweise verworfen): "
              "Zeile und Hinweis beim Lastfall nennen T1",
              vorher and st.analysis is an and an.design is None and _zeile_t1(an)
              and _t1(_bdk(an, m.active_case)),
              f"vorher ohne {vorher} | {an.info.get('bdk_hinweis')} | {_bdk(an, m.active_case)}")


def main():
    for t in (test_gzg, test_lastfall_neben_kombination, test_ausgewaehlt, test_nachtraeglich,
              test_abbruch, test_ergebniskombination, test_alle_gzt, test_knicken, test_knicken_web,
              test_ohne_chi_lt, test_verworfen_web):
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
