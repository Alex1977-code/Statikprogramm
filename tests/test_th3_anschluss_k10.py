"""
Runde k10 (15.11.2026), Theorie III. Ordnung, Verfahrensstand 66.

Punkt 1: Theorie III. Ordnung in einer Situation mit abgeschalteter Schale
brach mit KeyError ab (solver.beam_end_forces, Querschnitt = Name der
Schalendicke). theorie3.solve_theorie3 legte fuer jedes abgeschaltete
Element Stabendkraefte an, auch fuer Schalen; jetzt je Elementart wie
solver.postprocess (solver.inaktive_nullen). Theorie III. Ordnung rechnet
mit abgeschalteter Schale wie mit geloeschter; mit wirkender Schale weist
sie mit Klartext ab („nur für Stabtragwerke“).

Punkt 2: Der Anschluss eines Stabendes an einen Koerper (Kopplung der Gruppe
„Stabende“, starr, und die verteilende Kopplung RBE3 „Stabende“) entging der
Abweisung starrer Kopplungen und Starrkoerper (Runde k8), wenn kein
Koerperknoten mittrug. Theorie I. Ordnung rechnete sie dort trotzdem mit
(ohne Situation wirken alle Kopplungen; die Starrkoerper baut
assemble.starrkoerper immer ein), Theorie III. Ordnung nicht oder als Feder
von 1e4 N/m - still falsche Ergebnisse:
* Kopplung „Stabende“ Kragarmende b - Q ohne Element, Lastknoten P per RBE2
  an Q: Theorie I. Ordnung w(b) = 0,5357 mm, Theorie III. Ordnung 0,0000 mm,
  Summe Rz 0 statt 1 000 N;
* Last 1 kN direkt an Q: w(Q) = 100,5357 statt 0,5357 mm;
* RBE3 „Stabende“ an den gelagerten Knoten eines abgeschalteten Stabes:
  Theorie I. Ordnung und Gegenrechnung (Stab geloescht) 0,0000 mm, Theorie
  III. Ordnung 0,5357 mm.
Jetzt mit Klartext abgewiesen (theorie3._th3_wirkung), auch in der
Modellpruefung; Merkmal theorie3_stabende_anschluss, Stand 66.

Sollwerte, je zwei Wege: Handformel Kragarm L = 3 m, E I = 210 000 N/mm² ·
8 000 cm⁴, F = 1 kN: w = F L³/(3 E I) = 0,5357 mm (mit Feder k = 1e6 N/m in
Reihe: + F/k = 1,5357 mm); Gegenrechnung am Modell ohne das abgeschaltete
Element (bzw. Last direkt am Kragarmende).

Schutz: reine Staebe, federnde Kopplungen (auch der Gruppe „Stabende“) und
der Anschluss an einen abgeschalteten, ungelagerten Koerper rechnen weiter.

Aufruf:  python -m tests.test_th3_anschluss_k10
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E = 210e9
L = 3.0
I = 8e-5
F = 1e3
HAND = F * L ** 3 / (3 * E * I)                     # 0,5357 mm
EINS = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
TEXT_SK = "Theorie III. Ordnung rechnet keine Starrkörper"
TEXT_KP = "Theorie III. Ordnung rechnet keine starren Knotenkopplungen"
#: Runde k10e (16.11.2026, Stand 77, Fehler Nr. 27): Theorie III. Ordnung
#: rechnet Starrkoerper und starre Kopplungen seither mit. Was hier und in
#: den Dateien, die diese Helfer benutzen, als „abgewiesen“ geprueft wurde,
#: ist jetzt zweierlei: die Rechnung trifft die Bezuege (Hand, Theorie I.
#: Ordnung, Gegenrechnung), und die Regel der Wirkung (theorie3._th3_wirkung,
#: _ankerknoten - die Pruefung, die bis Stand 76 abwies) sieht den Anschluss
#: weiter, denn nach ihr richten sich die Merkmale der Staende 64 und 66.
WIRKT_SK = "Starrkörper (RBE2/RBE3"
WIRKT_KP = "starre Knotenkopplungen"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def close(name, ist, soll, rel=1e-6, einheit="mm", faktor=1e3):
    ok = abs(ist - soll) <= rel * max(abs(soll), 1e-12)
    return check(name, ok, f"ist {ist * faktor:.6f} {einheit}, soll {soll * faktor:.6f} {einheit}")


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def basis(stabteilung=1):
    from statik3d.model import Model, Material, Section
    m = Model("K10")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    if stabteilung is not None:
        m.netz.stabteilung = stabteilung
    a = m.add_node(0, 0, 0)
    b = m.add_node(L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    return m, a, b


def platte(m, x0, fest=True):
    """Platte shell4 0,1 × 0,1 m in der Ebene x = x0, ihre vier Knoten (gelagert)."""
    from statik3d.model import ShellProp
    if "t" not in m.shells:
        m.add_shell_prop(ShellProp("t", 0.02))
    n = [m.add_node(x0, 0.1 * dy - 0.05, 0.1 * dz - 0.05) for dy, dz in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("shell4", n, "ST", "t")
    if fest:
        for k in n:
            m.fix(k, "all")
    return n


def situation(m, elemente, lf="LF1"):
    from statik3d.model import Situation
    m.situationen["s"] = Situation("s", "", list(elemente))
    m.load_cases[lf].situation = "s"


def rechne(m, th="III", lf="LF1"):
    """(Analyse, u (nn, 6), Reaktionen (nn, 6), Fehlertext, Ausnahme)"""
    from statik3d import solver
    m.load_cases[lf].theorie = th
    try:
        an = _still(solver.solve_all, m, workers=1, design=False)
    except Exception as ex:          # noqa: BLE001
        return None, None, None, "", f"{type(ex).__name__}: {ex}"
    r = an.cases.get(lf)
    f = ""
    if an.theorie3 is not None and lf in an.theorie3.kombinationen:
        f = an.theorie3.kombinationen[lf].fehler or ""
    u = np.asarray(r.u).reshape(-1, 6)
    R = np.asarray(r.reactions).reshape(-1, 6)
    return an, u, R, f, ""


def th3_pruefung(m):
    return [z for z in m.check() if "Theorie III" in z]


def wirkung_pruefung(m):
    """Je Text der Wirkung (theorie3.kopplung_wirkung_modell, bis Stand 76 die
    Abweisung der Modellpruefung) eine Zeile mit den Lastfaellen und
    Kombinationen - wie die Zeilen „FEHLER: …“ bis Stand 76."""
    from statik3d.theorie3 import kopplung_wirkung_modell
    return [f"WIRKT: {t} (nach Theorie III. Ordnung gestellt: {', '.join(n)})"
            for t, n in kopplung_wirkung_modell(m).items()]


def ist_th3(an, lf="LF1"):
    r = an.cases.get(lf) if an is not None else None
    return r is not None and str(r.info.get("theorie", "")).startswith("III")


# --------------------------------------------------------------------------
# Punkt 1: abgeschaltete Schale
# --------------------------------------------------------------------------
def test_schale_abgeschaltet():
    for st in (1, None):                 # Stabteilung 1 und Vorgabe (intern geteilt)
        txt = "Stabteilung 1" if st == 1 else "Stabteilung Vorgabe"
        m, a, b = basis(st)
        platte(m, 5.0)
        m.load_node(b, Fz=-F)
        situation(m, [1])
        an, u, R, f, ex = rechne(m, "III")
        if not check(f"Situation mit abgeschalteter Schale ({txt}): Theorie III. Ordnung ohne Ausnahme",
                     not ex, ex[:200]):
            continue
        r = an.cases["LF1"]
        check(f"… ({txt}) als Theorie III. Ordnung gerechnet, ohne Fehler",
              str(r.info.get("theorie", "")).startswith("III") and not f, f"{r.info.get('theorie')} {f[:100]!r}")
        m2, a2, b2 = basis(st)
        m2.load_node(b2, Fz=-F)
        _an2, u2, R2, f2, ex2 = rechne(m2, "III")
        w, w2 = -u[b, 2], -u2[b2, 2]
        check(f"… ({txt}) w(b) gleich Gegenrechnung (Schale geloescht) und Hand F L³/(3 E I)",
              not ex2 and abs(w - w2) <= 1e-9 * abs(w2) and abs(w - HAND) <= 1e-4 * HAND,
              f"ist {w * 1e3:.6f} mm, Gegenrechnung {w2 * 1e3:.6f} mm, Hand {HAND * 1e3:.6f} mm")
        close(f"… ({txt}) Summe Rz = F", R[:, 2].sum(), F, 1e-6, "N", 1.0)
        sr = r.shell_res.get(1)
        check(f"… ({txt}) Schale ohne Stabendkräfte, Schalenergebnis null",
              1 not in r.beam_end and sr is not None and not np.any(np.asarray(sr)),
              f"beam_end {1 in r.beam_end}, shell_res {sr}")
        bf = r.beam_forces
        bf2 = _an2.cases["LF1"].beam_forces
        mz = max(abs(x) for i in bf for x in bf[i]["My"]) if bf else float("nan")
        mz2 = max(abs(x) for i in bf2 for x in bf2[i]["My"]) if bf2 else float("nan")
        check(f"… ({txt}) Stabkräfte lesbar, Einspannmoment = Gegenrechnung und F L",
              abs(mz - mz2) <= 1e-6 * F * L and abs(mz - F * L) <= 1e-3 * F * L,
              f"ist {mz:.3f} Nm, Gegenrechnung {mz2:.3f} Nm, Hand {F * L:.3f} Nm")


def test_schale_kombination():
    """Kombination nach Theorie III. Ordnung in der Situation mit abgeschalteter Schale."""
    m, a, b = basis()
    platte(m, 5.0)
    m.load_node(b, Fz=-F)
    situation(m, [1])
    c = m.add_combination("LK1", {"LF1": 1.5}, "ULS")
    c.theorie = "III"
    c.situation = "s"
    from statik3d import solver
    try:
        an = _still(solver.solve_all, m, workers=1, design=False)
        ex = ""
    except Exception as e:               # noqa: BLE001
        an, ex = None, f"{type(e).__name__}: {e}"
    check("Kombination LK1 nach Theorie III. Ordnung, Schale abgeschaltet: ohne Ausnahme", not ex, ex[:200])
    if an is None:
        return
    info = an.theorie3.kombinationen.get("LK1") if an.theorie3 is not None else None
    r = an.combinations.get("LK1")
    w = -np.asarray(r.u).reshape(-1, 6)[b, 2] if r is not None else float("nan")
    check("… gerechnet, w(b) = 1,5 · F L³/(3 E I)",
          info is not None and not info.fehler and abs(w - 1.5 * HAND) <= 1e-4 * HAND,
          f"fehler {getattr(info, 'fehler', None)!r}, w {w * 1e3:.6f} mm, Hand {1.5 * HAND * 1e3:.6f} mm")


def test_schale_wirkt():
    """Schale ohne Situation: Klartext statt Ausnahme, Theorie I. Ordnung bleibt."""
    m, a, b = basis()
    platte(m, 5.0)
    m.load_node(b, Fz=-F)
    an, u, R, f, ex = rechne(m, "III")
    check("Schale ohne Situation: keine Ausnahme, Klartext „nur für Stabtragwerke“",
          not ex and "nur für Stabtragwerke" in f, (ex or f)[:160])
    if not ex:
        close("… das Ergebnis bleibt Theorie I. Ordnung: w(b) = Hand", -u[b, 2], HAND, 1e-4)


# --------------------------------------------------------------------------
# Punkt 2: Anschluss eines Stabendes
# --------------------------------------------------------------------------
def _stabende_rbe2(mit_situation=False):
    """Kopplung „Stabende“ b-Q (Q ohne Element), Lastknoten P per RBE2 an Q."""
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m, a, b = basis()
    if mit_situation:
        c = m.add_node(0, 2, 0)
        d = m.add_node(L, 2, 0)
        m.add_element("beam", [c, d], "ST", "Q")
        m.fix(c, "all")
    q = m.add_node(L, 0, 0)
    p = m.add_node(L, 0, 0.5)
    m.kopplungen.append(Kopplung(b, q, EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    m.add_starrkoerper(p, [q], "RBE2", name="Arm")
    m.load_node(p, Fz=-F)
    if mit_situation:
        situation(m, [1])
    return m, b, p


def test_stabende_rbe2():
    m, b, p = _stabende_rbe2()
    _an1, u1, R1, f1, ex1 = rechne(m, "I")
    close("Kopplung „Stabende“ + RBE2, Theorie I. Ordnung: w(b) = Hand (Bezug)", -u1[b, 2], HAND, 1e-4)
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    wk = wirkung_pruefung(m)
    check("… Wirkung (Merkmale 64/66): Starrkörper „Arm“ und Gruppe Stabende; Modellprüfung ohne FEHLER",
          any(WIRKT_SK in z and "Arm" in z and WIRKT_KP in z and "Stabende" in z for z in wk)
          and not any(z.startswith("FEHLER") for z in pr), f"{wk} {pr}")
    an, u, R, f, ex = rechne(m, "III")
    check("… Theorie III. Ordnung gerechnet (seit Stand 77), keine Ausnahme", not ex and not f, (ex or f)[:200])
    if not ex:
        check("… Ergebnis als Theorie III. Ordnung", ist_th3(an), an.cases["LF1"].info.get("theorie"))
        close("… w(b) = Hand (kleine Last)", -u[b, 2], HAND, 1e-4)
        close("… w(P) = Theorie I. Ordnung", -u[p, 2], -u1[p, 2], 1e-4)
        close("… Summe Rz = F", R[:, 2].sum(), F, 1e-6, "N", 1.0)
    # mit Situation (fremder Kragarm abgeschaltet)
    ms, bs, ps = _stabende_rbe2(True)
    ms.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(ms)
    an, u, R, f, ex = rechne(ms, "III")
    check("… in einer Situation mit abgeschaltetem fremdem Stab: gerechnet, w(b) = Hand, Modellprüfung ohne "
          "FEHLER", not ex and not f and ist_th3(an) and abs(-u[bs, 2] - HAND) <= 1e-4 * HAND
          and not any(z.startswith("FEHLER") for z in pr), (ex or f)[:160])


def test_stabende_last_an_q():
    """Last 1 kN direkt an Q (Kopplung „Stabende“ b-Q starr, Q ohne Element)."""
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m, a, b = basis()
    q = m.add_node(L, 0, 0)
    m.kopplungen.append(Kopplung(b, q, EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    m.load_node(q, Fz=-F)
    _an1, u1, _R1, _f1, _ex1 = rechne(m, "I")
    close("Last an Q, Theorie I. Ordnung: w(Q) = Hand (Bezug)", -u1[q, 2], HAND, 1e-4)
    an, u, R, f, ex = rechne(m, "III")
    check("… Theorie III. Ordnung gerechnet (seit Stand 77; bis Stand 63 w(Q) 100,5357 mm)",
          not ex and not f and ist_th3(an), (ex or f)[:200])
    if not ex:
        close("… w(Q) = Hand = Theorie I. Ordnung", -u[q, 2], -u1[q, 2], 1e-4)
        close("… w(b) = w(Q) (starr)", -u[b, 2], -u[q, 2], 1e-9)
    from statik3d.theorie3 import kopplung_wirkung
    t = kopplung_wirkung(m, None, factors={"LF1": 1.0})
    check("… Wirkung: starre Kopplung der Gruppe Stabende K9", WIRKT_KP in t and "Stabende K9" in t, t[:120])


def _rbe3_an_stab(geloescht=False, gelagert=True):
    """Kragarm a-b; RBE3 „Stabende 1“ von b an die Knoten c, d eines zweiten
    Stabes c-d (quer, beide Knoten gelagert, wenn ``gelagert``). In der
    Situation ist der zweite Stab abgeschaltet; ``geloescht``: Gegenrechnung
    ohne ihn (Knoten, Lager und RBE3 bleiben)."""
    from statik3d.stabeinleitung import STABENDE
    m, a, b = basis()
    c = m.add_node(L, -0.2, 0)
    d = m.add_node(L, 0.2, 0.0)
    e = m.add_node(L, 0.0, 0.2)
    if not geloescht:
        m.add_element("beam", [c, d], "ST", "Q")
        m.add_element("beam", [d, e], "ST", "Q")
    if gelagert:
        for k in (c, d, e):
            m.fix(k, "all")
    m.add_starrkoerper(b, [c, d, e], "RBE3", name=STABENDE + "1")
    m.load_node(b, Fz=-F)
    if not geloescht:
        situation(m, [1, 2])
    return m, b


def test_rbe3_gelagert_abgeschaltet():
    m, b = _rbe3_an_stab()
    _an1, u1, _R1, _f1, _ex1 = rechne(m, "I")
    m2, b2 = _rbe3_an_stab(geloescht=True)
    _an2, u2, _R2, _f2, _ex2 = rechne(m2, "I")
    check("RBE3 „Stabende“ an gelagerten Knoten eines abgeschalteten Stabes: Theorie I. Ordnung = "
          "Gegenrechnung (Stab gelöscht), Stabende gehalten",
          abs(u1[b, 2] - u2[b2, 2]) <= 1e-9 and abs(u1[b, 2]) < 1e-3 * HAND,
          f"w {-u1[b, 2] * 1e3:.6f} mm, Gegenrechnung {-u2[b2, 2] * 1e3:.6f} mm")
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    wk = wirkung_pruefung(m)
    an, u, R, f, ex = rechne(m, "III")
    check("… Theorie III. Ordnung gerechnet (seit Stand 77), w(b) = Theorie I. Ordnung = Gegenrechnung "
          "(gehalten); Wirkung „Stabende 1“, Modellprüfung ohne FEHLER",
          not ex and not f and ist_th3(an) and abs(u[b, 2] - u2[b2, 2]) <= 1e-9
          and any(WIRKT_SK in z and "Stabende 1" in z for z in wk)
          and not any(z.startswith("FEHLER") for z in pr),
          (ex or f)[:160] + f" | {wk} {pr} w {None if u is None else -u[b, 2] * 1e3}")
    # dasselbe mit einer Schale statt der Staebe (Punkt 1 und 2 zusammen)
    from statik3d.stabeinleitung import STABENDE
    ms, a, bs = basis()
    n = platte(ms, L)
    ms.add_starrkoerper(bs, n, "RBE3", name=STABENDE + "1")
    ms.load_node(bs, Fz=-F)
    situation(ms, [1])
    an, u, R, f, ex = rechne(ms, "III")
    _a1, u1s, _R1, _f1, _e1 = rechne(ms, "I")
    check("… mit gelagerter, abgeschalteter Schale: gerechnet, w(b) = Theorie I. Ordnung (gehalten), "
          "statt KeyError oder 0,5357 mm", not ex and not f and ist_th3(an) and abs(u[bs, 2] - u1s[bs, 2]) <= 1e-9
          and abs(u[bs, 2]) < 1e-3 * HAND, (ex or f)[:160])


# --------------------------------------------------------------------------
# Schutz: korrekt rechenbare Modelle bleiben
# --------------------------------------------------------------------------
def test_schutz():
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    # reiner Kragarm
    m, a, b = basis()
    m.load_node(b, Fz=-F)
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    an, u, R, f, ex = rechne(m, "III")
    check("Schutz: reiner Kragarm nach Theorie III. Ordnung gerechnet, w = Hand",
          not ex and not f and not pr and abs(-u[b, 2] - HAND) <= 1e-4 * HAND,
          f"{(ex or f)[:80]!r} {pr} w {-u[b, 2] * 1e3 if u is not None else None}")
    # federnde Kopplung der Gruppe Stabende an Q ohne Element, Last an Q
    k = 1e6
    m, a, b = basis()
    q = m.add_node(L, 0, 0)
    m.kopplungen.append(Kopplung(b, q, EINS, [k] * 3, STABENDE_GRUPPE + "K9"))
    m.load_node(q, Fz=-F)
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    an, u, R, f, ex = rechne(m, "III")
    soll = HAND + F / k
    check("Schutz: federnde Kopplung „Stabende“ (1e6 N/m), Last an Q: gerechnet, w(Q) = F L³/(3 E I) + F/k",
          not ex and not f and not pr and abs(-u[q, 2] - soll) <= 1e-4 * soll,
          f"{(ex or f)[:80]!r} {pr} w {-u[q, 2] * 1e3 if u is not None else None:.6f} mm, soll {soll * 1e3:.6f} mm")
    # RBE3 „Stabende“ an einem abgeschalteten, ungelagerten Koerper
    m, b = _rbe3_an_stab(gelagert=False)
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    an, u, R, f, ex = rechne(m, "III")
    m2, a2, b2 = basis()
    m2.load_node(b2, Fz=-F)
    _an2, u2, _R2, _f2, _ex2 = rechne(m2, "III")
    check("Schutz: RBE3 „Stabende“ an abgeschaltetem, ungelagertem Stab: gerechnet, w(b) = Gegenrechnung "
          "(ohne Anschluss) und Hand",
          not ex and not f and not pr and abs(u[b, 2] - u2[b2, 2]) <= 1e-9 * HAND
          and abs(-u[b, 2] - HAND) <= 1e-4 * HAND,
          f"{(ex or f)[:80]!r} {pr}")
    # starre Kopplung „Stabende“ an einem Knoten eines abgeschalteten, ungelagerten Stabes
    m, a, b = basis()
    c = m.add_node(L, 0, 0)
    d = m.add_node(L, 1, 0)
    m.add_element("beam", [c, d], "ST", "Q")
    m.kopplungen.append(Kopplung(b, c, EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    m.load_node(b, Fz=-F)
    situation(m, [1])
    m.load_cases["LF1"].theorie = "III"
    pr = th3_pruefung(m)
    an, u, R, f, ex = rechne(m, "III")
    check("Schutz: Kopplung „Stabende“ an abgeschaltetem, ungelagertem Stab: gerechnet, w(b) = Hand",
          not ex and not f and not pr and abs(-u[b, 2] - HAND) <= 1e-4 * HAND,
          f"{(ex or f)[:80]!r} {pr}")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    mk = rv.merkmal("theorie3_stabende_anschluss")
    check("Merkmal theorie3_stabende_anschluss: Stand 66, Fehlerkorrektur, fix/k10-th3, VERFAHRENSSTAND 66",
          mk is not None and mk.wechsel[-1].stand == 66 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-th3" and rv.VERFAHRENSSTAND >= 66
          and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m, b, p = _stabende_rbe2()
    m.load_cases["LF1"].theorie = "III"
    m_rbe3, _b = _rbe3_an_stab()
    m_rbe3.load_cases["LF1"].theorie = "III"
    m_th1, _b, _p = _stabende_rbe2()                 # Theorie I. Ordnung: nicht betroffen
    m_k8, a, b8 = basis()                             # zwei Kragarme, schon in Runde k8 abgewiesen
    c = m_k8.add_node(0, 0, 0)
    d = m_k8.add_node(L, 0, 0)
    m_k8.add_element("beam", [c, d], "ST", "Q")
    m_k8.fix(c, "all")
    m_k8.kopplungen.append(Kopplung(b8, d, EINS, [float("inf")] * 3, STABENDE_GRUPPE + "K9"))
    m_k8.load_node(b8, Fz=-F)
    m_k8.load_cases["LF1"].theorie = "III"
    m_frei, _b = _rbe3_an_stab(gelagert=False)
    m_frei.load_cases["LF1"].theorie = "III"
    check("betrifft: Stabende+RBE2 ja, RBE3 an gelagertem abgeschaltetem Stab ja; Theorie I nein, "
          "schon in k8 abgewiesen nein, ungelagert nein",
          mk.betrifft(m) and mk.betrifft(m_rbe3) and not mk.betrifft(m_th1) and not mk.betrifft(m_k8)
          and not mk.betrifft(m_frei),
          f"{mk.betrifft(m)} {mk.betrifft(m_rbe3)} {mk.betrifft(m_th1)} {mk.betrifft(m_k8)} "
          f"{mk.betrifft(m_frei)}")
    an = _still(solver.solve_all, m, workers=1, design=False)
    an2 = _still(solver.solve_all, m_frei, workers=1, design=False)
    check("im Ergebnis: LF1 genannt, beim ungelagerten Anschluss nichts",
          "LF1" in (mk.im_ergebnis(m, an) or "") and not mk.im_ergebnis(m_frei, an2),
          f"{mk.im_ergebnis(m, an)!r} / {mk.im_ergebnis(m_frei, an2)!r}")


def main():
    for t in (test_schale_abgeschaltet, test_schale_kombination, test_schale_wirkt, test_stabende_rbe2,
              test_stabende_last_an_q, test_rbe3_gelagert_abgeschaltet, test_schutz, test_merkmal):
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
