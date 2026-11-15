"""
Runde k10 (15.11.2026), zweite Nachbesserung zu Theorie III. Ordnung, Stand 66.

Die zweite Gegenpruefung fand an der Regel fuer den Anschluss eines
Stabendes (theorie3._ankerknoten, _th3_wirkung) zwei Luecken:

* Als Lastknoten zaehlten nur Knoten mit Knotenlast. Eine Punktmasse unter
  Eigengewicht legt in assemble.load_vector ebenso Last an ihren Knoten.
  Kopplung „Stabende“ b-Q starr, Q ohne Element, Punktmasse 101,94 kg an Q,
  LF1 mit g = 9,81 m/s²: Theorie I. Ordnung w(Q) = 0,5357 mm = F L³/(3 E I),
  Theorie III. Ordnung still 100,5357 mm (Straffeder 1e4 N/m). RBE3
  „Stabende 1“ an drei Knoten ohne Element, Punktmasse an einem davon:
  Theorie I. Ordnung w(b) = 0,5357 mm und Summe Rz 1000 N, Theorie III.
  Ordnung still 0 mm und 0 N. Modellpruefung und Merkmal schwiegen.
* Die Regel zaehlte Knotenlasten aus jedem Lastfall. LF1 nach Theorie III.
  Ordnung ohne Last an Q wurde abgewiesen, weil LF2 nach Theorie I. Ordnung
  dort Last hat (falsche Abweisung; richtig ist w(b) = 0,5357 mm wie
  Theorie I. Ordnung und Hand). Jetzt gilt die Last je Lastfall bzw. je
  Kombination mit ihren Lastfaellen und Faktoren (bei einer
  Ergebniskombination je Alternative), in der Rechnung wie in der
  Modellpruefung und im Merkmal.
* Gegenpruefung zu k10b: Die Summe an Q wurde exakt mit null verglichen.
  LK1 = LF1 + 0,1 LF2 + 0,3 LF3 mit -3 N an Q in LF2 und +1 N in LF3 (bzw.
  Punktmasse 1 kg mit g = -3 und +1 m/s²) laesst den Rundungsrest
  -5,55e-17 und wurde abgewiesen, obwohl Theorie I. Ordnung w(b) = 0,535714
  mm = Hand ergibt. Jetzt zaehlt der Knoten erst ab 1e-9 der Betragssumme.

Aufruf:  python -m tests.test_th3_anker_lastfall_k10
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

import tests.test_th3_anschluss_k10 as T  # noqa: E402

RESULTS = T.RESULTS
check = T.check
HAND = T.HAND
F = T.F
L = T.L
G = 9.81
MASSE = F / G                       # 1 kN unter g = 9,81 m/s²


def _merkmal():
    from statik3d import rechenverfahren as rv
    return rv.merkmal("theorie3_stabende_anschluss")


def _kopplung_q(m, b):
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    q = m.add_node(L, 0, 0)
    m.kopplungen.append(Kopplung(b, q, T.EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    return q


def _fehler_zeilen(m):
    return [z for z in T.th3_pruefung(m) if z.startswith("FEHLER")]


# --------------------------------------------------------------------------
# Punktmasse unter Eigengewicht
# --------------------------------------------------------------------------
def pm_kopplung(g_lf="LF1", last_b=False):
    """Kopplung „Stabende“ b-Q starr, Q ohne Element, Punktmasse an Q;
    Eigengewicht im Lastfall ``g_lf`` (None: keiner)."""
    m, a, b = T.basis()
    q = _kopplung_q(m, b)
    m.add_punktmasse(q, MASSE)
    if last_b:
        m.load_node(b, Fz=-F)
    if g_lf is not None:
        if g_lf not in m.load_cases:
            m.add_load_case(g_lf)
        m.load_cases[g_lf].gravity = [0.0, 0.0, -G]
    return m, b, q


def pm_rbe3():
    """RBE3 „Stabende 1“ von b an drei Knoten ohne Element, Punktmasse an c."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = T.basis()
    c = m.add_node(L, -0.2, 0)
    d = m.add_node(L, 0.2, 0)
    e = m.add_node(L, 0.0, 0.2)
    m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
    m.add_punktmasse(c, MASSE)
    m.load_cases["LF1"].gravity = [0.0, 0.0, -G]
    return m, b


def test_punktmasse_kopplung():
    m, b, q = pm_kopplung()
    _an, u, R, f, ex = T.rechne(m, "I")
    ok = not ex and abs(-u[q, 2] - HAND) <= 1e-4 * HAND and abs(R[:, 2].sum() - F) <= 1e-6 * F
    check("Punktmasse an Q (Kopplung „Stabende“ b-Q), Theorie I. Ordnung: w(Q) = F L³/(3 E I), Summe Rz = m g",
          ok, ex or f"w(Q) {-u[q, 2] * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm, Rz {R[:, 2].sum():.3f} N")
    m, b, q = pm_kopplung()
    m.load_cases["LF1"].theorie = "III"
    pr = _fehler_zeilen(m)
    an, u, R, f, ex = T.rechne(m, "III")
    check("… Theorie III. Ordnung abgewiesen (starre Kopplung Gruppe Stabende K9) statt still 100,5357 mm",
          not ex and T.TEXT_KP in f and "Stabende K9" in f
          and not str(an.cases["LF1"].info.get("theorie", "")).startswith("III"), (ex or f)[:160])
    check("… Modellprüfung: FEHLER für LF1", any(T.TEXT_KP in z and "LF1" in z for z in pr), pr)
    mk = _merkmal()
    m, b, q = pm_kopplung()
    m.load_cases["LF1"].theorie = "III"
    check("… Merkmal theorie3_stabende_anschluss: betrifft", mk is not None and mk.betrifft(m),
          mk and mk.betrifft(m))


def test_punktmasse_rbe3():
    m, b = pm_rbe3()
    _an, u, R, f, ex = T.rechne(m, "I")
    ok = not ex and abs(-u[b, 2] - HAND) <= 1e-4 * HAND and abs(R[:, 2].sum() - F) <= 1e-6 * F
    check("Punktmasse an einem Slave des RBE3 „Stabende 1“, Theorie I. Ordnung: w(b) = Hand, Summe Rz = m g",
          ok, ex or f"w(b) {-u[b, 2] * 1e3:.6f} mm, Rz {R[:, 2].sum():.3f} N")
    m, b = pm_rbe3()
    m.load_cases["LF1"].theorie = "III"
    pr = _fehler_zeilen(m)
    an, u, R, f, ex = T.rechne(m, "III")
    check("… Theorie III. Ordnung abgewiesen (Starrkörper Stabende 1) statt still 0 mm und 0 N",
          not ex and T.TEXT_SK in f and "Stabende 1" in f, (ex or f)[:160])
    check("… Modellprüfung: FEHLER", any(T.TEXT_SK in z and "Stabende 1" in z for z in pr), pr)


def test_punktmasse_ohne_eigengewicht():
    """Punktmasse an Q, aber kein Lastfall mit Erdbeschleunigung, bzw. nur ein
    anderer Lastfall nach Theorie I. Ordnung: Q traegt in LF1 nichts."""
    for g_lf, wie in ((None, "ohne Eigengewicht"), ("LF2", "Eigengewicht nur in LF2 (Theorie I.)")):
        m, b, q = pm_kopplung(g_lf, last_b=True)
        m.load_cases["LF1"].theorie = "III"
        pr = _fehler_zeilen(m)
        an, u, R, f, ex = T.rechne(m, "III")
        w3 = float("nan") if ex else -u[b, 2]
        m1, b1, _q = pm_kopplung(g_lf, last_b=True)
        _an1, u1, _R1, _f1, ex1 = T.rechne(m1, "I")
        w1 = float("nan") if ex1 else -u1[b1, 2]
        check(f"Punktmasse an Q, {wie}: LF1 nach Theorie III. Ordnung gerechnet, keine Meldung",
              not ex and not f and not pr and str(an.cases["LF1"].info.get("theorie", "")).startswith("III"),
              f"{(ex or f)[:120]!r} {pr}")
        check(f"… w(b) = Theorie I. Ordnung = F L³/(3 E I)",
              abs(w3 - w1) <= 1e-4 * HAND and abs(w3 - HAND) <= 1e-4 * HAND,
              f"III {w3 * 1e3:.6f} mm, I {w1 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")
        mk = _merkmal()
        m, b, q = pm_kopplung(g_lf, last_b=True)
        m.load_cases["LF1"].theorie = "III"
        check(f"… Merkmal betrifft nicht", mk is not None and not mk.betrifft(m), mk and mk.betrifft(m))


# --------------------------------------------------------------------------
# Last nur in einem anderen Lastfall, Kombinationen
# --------------------------------------------------------------------------
def last_lf2():
    """Kopplung „Stabende“ b-Q, LF1: Last an b; LF2: Last an Q."""
    m, a, b = T.basis()
    q = _kopplung_q(m, b)
    m.load_node(b, Fz=-F)
    m.add_load_case("LF2")
    m.load_node(q, Fz=-F, case="LF2")
    return m, b, q


def test_last_anderer_lastfall():
    m, b, q = last_lf2()
    m.load_cases["LF1"].theorie = "III"
    pr = _fehler_zeilen(m)
    an, u, R, f, ex = T.rechne(m, "III")
    w3 = float("nan") if ex else -u[b, 2]
    m1, b1, _q = last_lf2()
    _an1, u1, _R1, _f1, ex1 = T.rechne(m1, "I")
    w1 = float("nan") if ex1 else -u1[b1, 2]
    check("Last an Q nur in LF2 (Theorie I.): LF1 nach Theorie III. Ordnung gerechnet, keine Meldung",
          not ex and not f and not pr and str(an.cases["LF1"].info.get("theorie", "")).startswith("III"),
          f"{(ex or f)[:120]!r} {pr}")
    check("… w(b) = Theorie I. Ordnung = F L³/(3 E I)",
          abs(w3 - w1) <= 1e-4 * HAND and abs(w3 - HAND) <= 1e-4 * HAND,
          f"III {w3 * 1e3:.6f} mm, I {w1 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")
    mk = _merkmal()
    m, b, q = last_lf2()
    m.load_cases["LF1"].theorie = "III"
    check("… Merkmal betrifft nicht", mk is not None and not mk.betrifft(m), mk and mk.betrifft(m))
    # LF2 selbst nach Theorie III. Ordnung: abgewiesen, und nur LF2 gemeldet
    m, b, q = last_lf2()
    m.load_cases["LF1"].theorie = "III"
    m.load_cases["LF2"].theorie = "III"
    pr = _fehler_zeilen(m)
    from statik3d import solver
    an = T._still(solver.solve_all, m, workers=1, design=False)
    th3 = an.theorie3.kombinationen
    check("LF1 und LF2 nach Theorie III. Ordnung: LF2 abgewiesen, LF1 gerechnet",
          T.TEXT_KP in (th3["LF2"].fehler or "") and not th3["LF1"].fehler,
          f"LF1 {th3['LF1'].fehler!r} LF2 {(th3['LF2'].fehler or '')[:80]!r}")
    check("… Modellprüfung nennt LF2, nicht LF1",
          len(pr) == 1 and "LF2" in pr[0] and "LF1" not in pr[0], pr)
    check("… Merkmal betrifft (LF2)", mk is not None and mk.betrifft(m), mk and mk.betrifft(m))
    im = mk.im_ergebnis(m, an) if mk is not None else ""
    check("… im Ergebnis: LF1 (gerechnet, richtig) nicht genannt", "LF1" not in (im or ""),
          repr(im))


def test_kombinationen():
    from statik3d import solver
    m, b, q = last_lf2()
    for n, fak in (("LK1", {"LF1": 1.5}), ("LK2", {"LF1": 1.0, "LF2": 1.0}), ("LK3", {"LF1": 1.0, "LF2": 0.0})):
        c = m.add_combination(n, fak, "ULS")
        c.theorie = "III"
    pr = _fehler_zeilen(m)
    an = T._still(solver.solve_all, m, workers=1, design=False)
    th3 = an.theorie3.kombinationen

    def w(n):
        r = an.combinations.get(n)
        return -np.asarray(r.u).reshape(-1, 6)[b, 2] if r is not None else float("nan")
    check("LK1 = 1,5 LF1 (keine Last an Q): gerechnet, w(b) = 1,5 F L³/(3 E I)",
          not th3["LK1"].fehler and abs(w("LK1") - 1.5 * HAND) <= 1e-4 * HAND,
          f"{th3['LK1'].fehler!r} w {w('LK1') * 1e3:.6f} mm, Hand {1.5 * HAND * 1e3:.6f} mm")
    check("LK3 = LF1 + 0 · LF2: gerechnet, w(b) = F L³/(3 E I)",
          not th3["LK3"].fehler and abs(w("LK3") - HAND) <= 1e-4 * HAND,
          f"{th3['LK3'].fehler!r} w {w('LK3') * 1e3:.6f} mm")
    check("LK2 = LF1 + LF2 (Last an Q): abgewiesen", T.TEXT_KP in (th3["LK2"].fehler or ""),
          (th3["LK2"].fehler or "")[:120])
    check("… Modellprüfung nennt nur LK2", len(pr) == 1 and "LK2" in pr[0] and "LK1" not in pr[0]
          and "LK3" not in pr[0], pr)


def test_ergebniskombination():
    from statik3d import solver
    m, b, q = last_lf2()
    c = m.add_combination("EK1", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 1.0}])
    c.theorie = "III"
    c2 = m.add_combination("EK2", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF1": 2.0}])
    c2.theorie = "III"
    pr = _fehler_zeilen(m)
    an = T._still(solver.solve_all, m, workers=1, design=False)
    th3 = an.theorie3.kombinationen
    f1, f2 = th3.get("EK1 [1]"), th3.get("EK1 [2]")
    check("EK1: Alternative [1] (LF1) gerechnet, [2] (LF2, Last an Q) abgewiesen",
          f1 is not None and f2 is not None and not f1.fehler and T.TEXT_KP in (f2.fehler or ""),
          f"{getattr(f1, 'fehler', None)!r} / {(getattr(f2, 'fehler', '') or '')[:80]!r}")
    e1 = (getattr(an, "alternativen", None) or {}).get("EK1 [1]")
    w1 = -np.asarray(e1.u).reshape(-1, 6)[b, 2] if e1 is not None else float("nan")
    check("… EK1 [1]: w(b) = F L³/(3 E I)", abs(w1 - HAND) <= 1e-4 * HAND, f"{w1 * 1e3:.6f} mm")
    check("… Modellprüfung nennt EK1, nicht EK2", len(pr) == 1 and "EK1" in pr[0] and "EK2" not in pr[0], pr)
    f3 = [th3.get("EK2 [1]"), th3.get("EK2 [2]")]
    check("EK2 (nur LF1): beide Alternativen gerechnet", all(x is not None and not x.fehler for x in f3),
          [getattr(x, "fehler", None) for x in f3])


def test_sperre_je_faktoren():
    """kopplung_sperre mit den Faktoren der Rechnung (theorie3)."""
    from statik3d.theorie3 import kopplung_sperre
    m, b, q = last_lf2()
    t1 = kopplung_sperre(m, None, factors={"LF1": 1.0})
    t2 = kopplung_sperre(m, None, factors={"LF2": 1.0})
    t12 = kopplung_sperre(m, None, factors={"LF1": 1.0, "LF2": -1.0})
    check("kopplung_sperre je Faktoren: LF1 leer, LF2 und LF1 - LF2 abgewiesen",
          t1 == "" and T.TEXT_KP in t2 and T.TEXT_KP in t12, f"{t1!r} {t2[:60]!r} {t12[:60]!r}")
    m, b, q = pm_kopplung("LF2", last_b=True)
    check("… Punktmasse: Eigengewicht nur in LF2 - LF1 leer, LF2 abgewiesen",
          kopplung_sperre(m, None, factors={"LF1": 1.0}) == ""
          and T.TEXT_KP in kopplung_sperre(m, None, factors={"LF2": 1.0}))


# --------------------------------------------------------------------------
# Lasten, die sich in einer Kombination nur bis auf Rundung aufheben
# --------------------------------------------------------------------------
def rest_modell(art="last", theorie="III"):
    """Kopplung „Stabende“ b-Q starr, Q ohne Element; LF1: Last F an b;
    LK1 = LF1 + 0,1 LF2 + 0,3 LF3, an Q -3 N in LF2 und +1 N in LF3
    (art "last") bzw. Punktmasse 1 kg an Q mit g = -3 und +1 m/s² in z
    (art "masse"). Die Summe an Q ist 0,1 (-3) + 0,3 = -5,55e-17, also
    null bis auf Rundung: Q traegt in LK1 nichts."""
    m, a, b = T.basis()
    q = _kopplung_q(m, b)
    m.add_load_case("LF2")
    m.add_load_case("LF3")
    m.load_node(b, Fz=-F, case="LF1")
    if art == "last":
        m.load_node(q, Fz=-3.0, case="LF2")
        m.load_node(q, Fz=1.0, case="LF3")
    else:
        m.add_punktmasse(q, 1.0)
        m.load_cases["LF2"].gravity = [0.0, 0.0, -3.0]
        m.load_cases["LF3"].gravity = [0.0, 0.0, 1.0]
    c = m.add_combination("LK1", {"LF1": 1.0, "LF2": 0.1, "LF3": 0.3}, "ULS")
    c.theorie = theorie
    return m, b, q


def test_rundungsrest():
    from statik3d import solver
    rest = 0.1 * (-3.0) + 0.3 * 1.0
    check("Vorbedingung: 0,1 (-3) + 0,3 ist in Gleitkomma nicht genau null", rest != 0.0, f"{rest:.20f}")
    for art, wie in (("last", "Knotenlasten -3 N und +1 N"), ("masse", "Punktmasse, g = -3 und +1 m/s²")):
        m, b, q = rest_modell(art, "I")
        an1 = T._still(solver.solve_all, m, workers=1, design=False)
        r1 = an1.combinations.get("LK1")
        w1 = -np.asarray(r1.u).reshape(-1, 6)[b, 2] if r1 is not None else float("nan")
        check(f"LK1 mit Rundungsrest an Q ({wie}), Theorie I. Ordnung: w(b) = F L³/(3 E I)",
              abs(w1 - HAND) <= 1e-4 * HAND, f"{w1 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")
        m, b, q = rest_modell(art)
        pr = _fehler_zeilen(m)
        an = T._still(solver.solve_all, m, workers=1, design=False)
        th3 = an.theorie3.kombinationen
        r = an.combinations.get("LK1")
        w3 = -np.asarray(r.u).reshape(-1, 6)[b, 2] if r is not None else float("nan")
        check(f"… Theorie III. Ordnung: LK1 gerechnet statt abgewiesen, keine Meldung",
              not th3["LK1"].fehler and not pr, f"{(th3['LK1'].fehler or '')[:100]!r} {pr}")
        check(f"… w(b) = Theorie I. Ordnung = F L³/(3 E I) (Abweichung höchstens 0,001 mm)",
              abs(w3 - w1) <= 1e-6 and abs(w3 - HAND) <= 1e-4 * HAND,
              f"III {w3 * 1e3:.6f} mm, I {w1 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")
        mk = _merkmal()
        m, b, q = rest_modell(art)
        check(f"… Merkmal betrifft nicht", mk is not None and not mk.betrifft(m), mk and mk.betrifft(m))
    # Gegenprobe: ein echter kleiner Rest an Q wird weiter erkannt
    from statik3d.theorie3 import kopplung_sperre
    m, b, q = rest_modell("last")
    t = kopplung_sperre(m, None, factors={"LF1": 1.0, "LF2": 0.1, "LF3": 0.3001})
    check("… Gegenprobe: echter Rest 0,0001 N an Q (0,3001 statt 0,3) wird abgewiesen",
          T.TEXT_KP in t, t[:80])


def main():
    for t in (test_punktmasse_kopplung, test_punktmasse_rbe3, test_punktmasse_ohne_eigengewicht,
              test_last_anderer_lastfall, test_kombinationen, test_ergebniskombination, test_sperre_je_faktoren,
              test_rundungsrest):
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
