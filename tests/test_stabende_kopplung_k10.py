"""
Behebung vom 15.11.2026, Runde k10c (vom Anwender freigegeben), Verfahrensstand 71:
Kopplung eines Stabendes (Gruppe fugen.STABENDE_GRUPPE) an einem
Koerperknoten ohne jedes Element.

situationen.kopplung_bleibt liess die Kopplung eines Stabendes nur ueber einen
wirksamen Koerperknoten (node_b) gelten - damit ein abgeschalteter Koerper
ueber den Stab nicht wieder auflebt. Ein Knoten ohne jedes Element ist aber
kein Knoten eines abgeschalteten Koerpers. Unter jeder Elementmaske
(Situation, Stab „aus“ und auch eine Einsermaske, die nichts abschaltet - ein
Stab „aus“ ohne Elemente) entfiel die Kopplung, und die Last dahinter ging
still verloren:

* Kragarm 3 m, Kopplung „Stabende“ vom Ende b an Q ohne Element, 1 kN an Q:
  mit Maske w(b) = 0 mm und Summe Rz 0 N, ohne Maske und in der
  Gegenrechnung 0,5357 mm und 1 000 N, Gleichgewichtskontrolle „ok“.
* Theorie II. Ordnung ebenso, Knicken brach mit „Keine Normalkräfte“ ab,
  die Schwingung lieferte 441,41 statt 21,72 Hz.
* Theorie III. Ordnung (theorie3._wirksame_knoten_th3, dieselbe Regel) zaehlte
  die starre Kopplung auch ohne Maske nicht zur Abweisung und rechnete sie
  als Feder von 1e4 N/m.

Seither (situationen.kopplung_bleibt mit ``tot``, situationen.huelle,
theorie3._wirksame_knoten_th3): die Kopplung bleibt auch ueber den wirksamen
Stabknoten, wenn ihr Koerperknoten nicht Knoten eines abgeschalteten
Elements ist - dieselbe Regel wie bei der verteilenden Kopplung (Stand 67).

Sollwerte, je zwei Wege:
* Handformel: Kragarm L = 3 m, E I = 210 000 N/mm² · 8 000 cm⁴, F = 1 kN:
  w = F L³/(3 E I); Theorie II. Ordnung w = F (tan kL − kL)/(N k);
  Knicken N_cr = π² E I/(2 L)²; Schwingung f = √(3 E I/L³ / m_eff)/2π mit
  m_eff = m + 33/140 m_Stab.
* Gegenrechnung: dasselbe Modell, das abgeschaltete Element geloescht
  (seine Knoten bleiben), ohne Maske.

Schutz: Ist der Koerperknoten Knoten eines abgeschalteten Elements, bleibt die
Kopplung weiter weg (der Koerper lebt nicht wieder auf); traegt er ein Lager,
haelt sie wie in der Gegenrechnung (Stand 67).

Aufruf:  python -m tests.test_stabende_kopplung_k10
"""
import contextlib
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def close(name, ist, soll, rel=1e-6, einheit="mm"):
    ok = ist is not None and math.isfinite(ist) and abs(ist - soll) <= rel * max(abs(soll), 1e-12)
    return check(name, ok, f"ist {ist if ist is None else f'{ist:.6f}'} {einheit}, soll {soll:.6f} {einheit}")


E = 210e9
L = 3.0
I = 8e-5
F = 1e3
N = 200e3
HAND = F * L ** 3 / (3 * E * I)                      # 0,5357 mm
TEXT_KP = "Theorie III. Ordnung rechnet keine starren Knotenkopplungen"
#: Masken: Gegenrechnung, ohne Maske, Einsermaske (Stab „aus“ ohne Elemente),
#: Situation, Stab „aus“
MASKEN = ("eins", "situation", "aus")
EINS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _hand_th2():
    k = math.sqrt(N / (E * I))
    return F * (math.tan(k * L) - k * L) / (N * k)


def basis(maske, teile=1, rho=0.0):
    """Kragarm a-b (eingespannt in a) und zweiter Kragarm c-d bei y = 2 m.
    maske: 'geloescht' (c-d fehlt) | 'keine' | 'eins' (Stab „aus“ ohne
    Elemente: Model.grundmaske ist eine Einsermaske) | 'situation' (c-d in
    der Situation s aus) | 'aus' (c-d als Stab „aus“). (Modell, a, b, c, d)"""
    from tests import test_maske_lager_k10 as t
    m, a, b, c, d = t.basis("keine" if maske == "eins" else maske, rho=rho, teile=teile)
    if maske == "eins":
        m.add_member("leer", [], aus=True)
    return m, a, b, c, d


def _aktiv(m, maske):
    if maske in ("geloescht", "keine"):
        return None
    return m.aktive_elemente("s" if maske == "situation" else "")


def stabende(m, b, q, k=None):
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m.kopplungen.append(Kopplung(b, q, EINS, [float("inf") if k is None else k] * 3,
                                 STABENDE_GRUPPE + f"K{b}"))


def fall_q(maske, teile=1, rho=0.0, k=None):
    """Kopplung „Stabende“ vom Ende b an Q = (L, 0, 0) ohne Element."""
    m, a, b, c, d = basis(maske, teile, rho)
    q = m.add_node(L, 0, 0)
    stabende(m, b, q, k)
    return m, b, q


def fall_kette(maske):
    """Kopplung „Stabende“ b-Q, Q per Feder 1e12 N/m an P (Q, P ohne Element)."""
    from statik3d.model import Kopplung
    m, a, b, c, d = basis(maske)
    q = m.add_node(L, 0, 0)
    p = m.add_node(L, 0, 0)
    stabende(m, b, q)
    m.kopplungen.append(Kopplung(p, q, EINS, [1e12] * 3, "Feder"))
    return m, b, p


def rechne(m, lf="LF1"):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.cases[lf]
    return an, r, np.asarray(r.u).reshape(-1, 6), np.asarray(r.reactions).reshape(-1, 6)


# --------------------------------------------------------------------------
# Theorie I. Ordnung
# --------------------------------------------------------------------------
def test_theorie1():
    from statik3d.situationen import wirksame_knoten
    for titel, bauer in (("Last an Q", fall_q), ("Kette Q-Feder-P, Last an P", fall_kette)):
        m0, b0, p0 = bauer("geloescht")
        m0.load_node(p0, Fz=-F, case="LF1")
        _a, _r, u0, r0 = rechne(m0)
        close(f"Th I {titel}, Gegenrechnung: w(b) = F L³/(3 E I)", -u0[b0, 2] * 1e3, HAND * 1e3, 1e-5)
        mk, bk, pk = bauer("keine")
        mk.load_node(pk, Fz=-F, case="LF1")
        _a, _r, uk, rk = rechne(mk)
        close(f"Th I {titel}, ohne Maske: w(b) gleich Gegenrechnung", -uk[bk, 2] * 1e3, -u0[b0, 2] * 1e3, 1e-9)
        for maske in MASKEN:
            m, b, p = bauer(maske)
            m.load_node(p, Fz=-F, case="LF1")
            an, r, u, R = rechne(m)
            kn = wirksame_knoten(m, np.ones(len(m.elements), bool) if maske == "eins" else _aktiv(m, maske))
            check(f"Th I {titel}, Maske {maske}: Lastknoten wirksam", bool(kn[p]), f"{kn[p]}")
            close(f"Th I {titel}, Maske {maske}: w(b) = Hand", -u[b, 2] * 1e3, HAND * 1e3, 1e-5)
            close(f"Th I {titel}, Maske {maske}: w(b) gleich Gegenrechnung", -u[b, 2] * 1e3, -u0[b0, 2] * 1e3,
                  1e-9)
            close(f"Th I {titel}, Maske {maske}: w(Lastknoten) gleich Gegenrechnung", -u[p, 2] * 1e3,
                  -u0[p0, 2] * 1e3, 1e-9)
            close(f"Th I {titel}, Maske {maske}: Summe Rz = 1 kN wie Gegenrechnung", R[:, 2].sum(),
                  r0[:, 2].sum(), 1e-9, "N")


def test_einsermaske_direkt():
    """Einsermaske unmittelbar am Gleichungssystem (solver.StaticSystem mit
    aktiv = Einsen) gegen ohne Maske: Lastvektor und Loesung gleich."""
    from statik3d import solver
    from statik3d import assemble as asm
    m, b, q = fall_q("keine")
    m.load_node(q, Fz=-F, case="LF1")
    lc = m.load_cases["LF1"]
    eins = np.ones(len(m.elements), bool)
    F0 = asm.load_vector(m, lc, None)
    F1 = asm.load_vector(m, lc, eins)
    check("Einsermaske: Lastvektor gleich ohne Maske (Last an Q)", np.array_equal(F0, F1),
          f"|ΔF| {np.abs(F0 - F1).max():.3f} N")
    w = {}
    for name, aktiv in (("ohne", None), ("eins", eins)):
        sy = _still(solver.StaticSystem, m, 1, None, aktiv=aktiv)
        u = np.asarray(_still(sy.solve, asm.load_vector(m, lc, aktiv))).reshape(-1, 6)
        w[name] = -u[b, 2]
    close("Einsermaske am Gleichungssystem: w(b) gleich ohne Maske", w["eins"] * 1e3, w["ohne"] * 1e3, 1e-9)
    close("… und gleich Hand", w["eins"] * 1e3, HAND * 1e3, 1e-5)


# --------------------------------------------------------------------------
# Theorie II. Ordnung, Knicken, Schwingung
# --------------------------------------------------------------------------
def test_theorie2():
    hand = _hand_th2()
    werte = {}
    for maske in ("geloescht", "keine") + MASKEN:
        m, b, q = fall_q(maske, teile=8)
        m.load_node(q, Fx=-N, Fz=-F, case="LF1")
        m.load_cases["LF1"].theorie = "II"
        _an, r, u, R = rechne(m)
        werte[maske] = (-u[b, 2], str((r.info or {}).get("theorie", "")), R[:, 2].sum())
    close("Th II ohne Maske: Gegenrechnung gleich Hand F (tan kL − kL)/(N k)", werte["geloescht"][0] * 1e3,
          hand * 1e3, 2e-3)
    for maske in ("keine",) + MASKEN:
        w, th, rz = werte[maske]
        check(f"Th II, Maske {maske}: nach Theorie II. Ordnung gerechnet", th.startswith("II"), th)
        close(f"Th II, Maske {maske}: w(b) gleich Gegenrechnung", w * 1e3, werte["geloescht"][0] * 1e3, 1e-7)
        close(f"Th II, Maske {maske}: Summe Rz = 1 kN", rz, F, 1e-6, "N")


def test_knicken():
    from statik3d import solver
    hand = math.pi ** 2 * E * I / (2 * L) ** 2
    werte = {}
    for maske in ("geloescht", "keine") + MASKEN:
        m, b, q = fall_q(maske, teile=8)
        m.load_node(q, Fx=-F, case="LF1")
        try:
            r = _still(solver.solve_buckling, m, 2, case="LF1", workers=1)
            f = [float(x) for x in r.buckling_factors if float(x) > 0]
            werte[maske] = f[0] * F if f else float("nan")
        except Exception as ex:          # noqa: BLE001
            werte[maske] = float("nan")
            print(f"     Knicken, Maske {maske}: {type(ex).__name__}: {str(ex)[:120]}")
    close("Knicken ohne Maske: Gegenrechnung N_cr gleich Hand π² E I/(2L)²", werte["geloescht"] / 1e3,
          hand / 1e3, 1e-4, "kN")
    for maske in ("keine",) + MASKEN:
        close(f"Knicken, Druck an Q, Maske {maske}: N_cr gleich Gegenrechnung", werte[maske] / 1e3,
              werte["geloescht"] / 1e3, 1e-7, "kN")


def test_schwingung():
    """Punktmasse 100 kg an Q, Stab 1 kg; solve_modal mit der Maske (wie
    schwingung.nachweis in der Situation seines Wasserdruck-Generierers)."""
    from statik3d import solver
    m_stab = 1.0
    hand = math.sqrt(3 * E * I / L ** 3 / (100.0 + 33.0 / 140.0 * m_stab)) / (2 * math.pi)
    werte = {}
    for maske in ("geloescht", "keine") + MASKEN:
        m, b, q = fall_q(maske, teile=8, rho=m_stab / (1e-2 * L))
        m.add_punktmasse(q, 100.0)
        aktiv = np.ones(len(m.elements), bool) if maske == "eins" else _aktiv(m, maske)
        r = _still(solver.solve_modal, m, 2, workers=1, aktiv=aktiv)
        werte[maske] = float(np.asarray(r.freqs)[0])
    close("Schwingung ohne Maske: Gegenrechnung f₁ nach Hand", werte["geloescht"], hand, 2e-3, "Hz")
    for maske in ("keine",) + MASKEN:
        # 1e-6: ARPACK streut von Lauf zu Lauf um 1e-7 (test_maske_lager_k10)
        close(f"Schwingung, Punktmasse an Q, Maske {maske}: f₁ gleich Gegenrechnung", werte[maske],
              werte["geloescht"], 1e-6, "Hz")


# --------------------------------------------------------------------------
# Theorie III. Ordnung
# --------------------------------------------------------------------------
def test_theorie3():
    from statik3d.theorie3 import starre_kopplung_sperre, solve_theorie3
    from statik3d import solver
    for maske in ("geloescht", "keine") + MASKEN:
        m, b, q = fall_q(maske)
        aktiv = np.ones(len(m.elements), bool) if maske == "eins" else _aktiv(m, maske)
        t = starre_kopplung_sperre(m, aktiv)
        check(f"Th III starre Kopplung „Stabende“ an Q ohne Element, Maske {maske}: abgewiesen wie die "
              "Gegenrechnung", TEXT_KP in t, t[:90])
    # ueber den Einstieg: kein Ergebnis nach Theorie III. Ordnung mit weicher Feder
    for maske in ("keine", "eins", "aus"):
        m, b, q = fall_q(maske)
        m.load_node(q, Fz=-F, case="LF1")
        m.load_cases["LF1"].theorie = "III"
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.cases["LF1"]
        f = ""
        if an.theorie3 is not None and "LF1" in an.theorie3.kombinationen:
            f = an.theorie3.kombinationen["LF1"].fehler or ""
        u = np.asarray(r.u).reshape(-1, 6)
        check(f"Th III über solve_all, Maske {maske}: abgewiesen (Klartext), w(Q) nicht 100,54 mm",
              TEXT_KP in f and abs(-u[q, 2] * 1e3 - 100.5357) > 1.0,
              f"theorie {r.info.get('theorie')}, w(Q) {-u[q, 2] * 1e3:.4f} mm, „{f[:60]}“")
    # federnde Kopplung: gerechnet, w(Q) = Hand + F/k wie die Gegenrechnung
    k = 1e6
    sol = {}
    for maske in ("geloescht", "keine") + MASKEN:
        m, b, q = fall_q(maske, k=k)
        m.load_node(q, Fz=-F, case="LF1")
        aktiv = np.ones(len(m.elements), bool) if maske == "eins" else _aktiv(m, maske)
        try:
            r, _info = _still(solve_theorie3, m, {"LF1": 1.0}, "LF1", imperfektionen=False, aktiv=aktiv)
            sol[maske] = -float(np.asarray(r.u).reshape(-1, 6)[q, 2])
        except Exception as ex:          # noqa: BLE001
            sol[maske] = None
            print(f"     Th III federnd {maske}: {type(ex).__name__}: {str(ex)[:160]}")
    close("Th III federnde Kopplung „Stabende“, Gegenrechnung: w(Q) = F L³/(3 E I) + F/k",
          None if sol["geloescht"] is None else sol["geloescht"] * 1e3, (HAND + F / k) * 1e3, 1e-4)
    for maske in ("keine",) + MASKEN:
        close(f"Th III federnd, Maske {maske}: w(Q) gleich Gegenrechnung",
              None if sol[maske] is None else sol[maske] * 1e3,
              (sol["geloescht"] or float("nan")) * 1e3, 1e-6)


# --------------------------------------------------------------------------
# Spannschritt
# --------------------------------------------------------------------------
def _spann(maske):
    """Quader mit Anker A1 (Sollkraft 50 MN, Stabende-RBE3 an der Oberseite,
    tests.test_spannschritt_kopplung) und daneben der Kragarm a-b mit
    Kopplung „Stabende“ an Q ohne Element, 1 kN an Q im Lastfall V; zweiter
    Kragarm c-d fuer die Maske."""
    from tests.test_spannschritt_kopplung import _anker_modell
    from statik3d.model import Material, Section, Situation
    m, e, M, _oben = _anker_modell("rbe3")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    a = m.add_node(5.0, 0, 0)
    b = m.add_node(5.0 + L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    c = m.add_node(5.0, 2, 0)
    d = m.add_node(5.0 + L, 2, 0)
    if maske != "geloescht":
        arm = m.add_element("beam", [c, d], "ST", "Q")
        if maske == "aus":
            m.add_member("S2", [arm], aus=True)
        if maske == "situation":
            m.situationen["s"] = Situation("s", "", [arm])
            m.load_cases["V"].situation = "s"
    if maske == "eins":
        m.add_member("leer", [], aus=True)
    m.fix(c, "all")
    q = m.add_node(5.0 + L, 0, 0)
    stabende(m, b, q)
    m.load_node(q, Fz=-F, case="V")
    return m, e, b, q


def test_spannschritt():
    from statik3d import solver, vorspannkraft as vk
    alt = vk.LINEAR_WEG
    vk.LINEAR_WEG = vk.WEG_SPANNEN
    werte = {}
    try:
        for maske in ("geloescht", "keine") + MASKEN:
            m, e, b, q = _spann(maske)
            r = _still(solver.solve_static, m, case="V")
            u = np.asarray(r.u).reshape(-1, 6)
            werte[maske] = (float(np.asarray(r.beam_forces[int(e)]["N"], float)[1]), -u[b, 2],
                            ((r.info.get("vorspannung") or {}).get("weg")))
    finally:
        vk.LINEAR_WEG = alt
    n0, w0, weg0 = werte["geloescht"]
    check("Spannschritt, Gegenrechnung: über Spannen und Verriegeln gerechnet", weg0 == vk.WEG_SPANNEN, str(weg0))
    close("Spannschritt, Gegenrechnung: w(b) = F L³/(3 E I)", w0 * 1e3, HAND * 1e3, 1e-5)
    for maske in ("keine",) + MASKEN:
        n, w, weg = werte[maske]
        check(f"Spannschritt, Maske {maske}: über Spannen und Verriegeln", weg == vk.WEG_SPANNEN, str(weg))
        close(f"Spannschritt, Maske {maske}: N_Anker gleich Gegenrechnung", n, n0, 1e-9, "N")
        close(f"Spannschritt, Maske {maske}: w(b) gleich Gegenrechnung (Last an Q wirkt)", w * 1e3, w0 * 1e3, 1e-9)


# --------------------------------------------------------------------------
# Schutz: abgeschalteter Koerper; gelagerter Koerperknoten
# --------------------------------------------------------------------------
def test_schutz():
    """Koerperknoten d am Ende des abgeschalteten Arms (ungelagert): die
    Kopplung bleibt weg, der Arm lebt nicht wieder auf; w(b) = Hand. Liegt d
    am Ort von b und traegt ein Lager (Arm c-d quer, c und d gelagert), haelt
    die Kopplung b wie in der Gegenrechnung."""
    from statik3d.situationen import wirksame_knoten
    from statik3d.theorie3 import _wirksame_knoten_th3
    for maske in ("situation", "aus"):
        m, a, b, c, d = basis(maske)
        stabende(m, b, d)
        m.load_node(b, Fz=-F, case="LF1")
        aktiv = _aktiv(m, maske)
        kn = wirksame_knoten(m, aktiv)
        k3 = _wirksame_knoten_th3(m, aktiv)
        check(f"Schutz, Maske {maske}: Koerperknoten d des abgeschalteten Arms bleibt unwirksam (auch Th III)",
              bool(kn[b] and not kn[d] and not k3[d]), f"b {kn[b]}, d {kn[d]}, Th III d {k3[d]}")
        _an, _r, u, R = rechne(m)
        close(f"Schutz, Maske {maske}: w(b) = Hand", -u[b, 2] * 1e3, HAND * 1e3, 1e-5)
    sol = {}
    for maske in ("geloescht", "eins", "situation", "aus"):
        from tests import test_maske_lager_k10 as t
        from statik3d.model import Situation
        m, a, b, _c, _d = basis("keine" if maske == "eins" else "geloescht")
        if maske == "eins":
            m.add_member("leer", [], aus=True)
        c2 = m.add_node(L, -2, 0)
        d2 = m.add_node(L, 0, 0)
        if maske in ("situation", "aus"):
            arm = m.add_element("beam", [c2, d2], "ST", "Q")
            if maske == "aus":
                m.add_member("Q2", [arm], aus=True)
            else:
                m.situationen["s2"] = Situation("s2", "", [arm])
                m.load_cases["LF1"].situation = "s2"
        m.fix(c2, "all")
        m.fix(d2, "all")
        stabende(m, b, d2)
        m.load_node(b, Fz=-F, case="LF1")
        _an, _r, u, R = rechne(m)
        sol[maske] = (-u[b, 2], R[:, 2].sum())
        del t
    check("Gelagerter Koerperknoten, Gegenrechnung: b gehalten, Summe Rz = 1 kN",
          abs(sol["geloescht"][0]) < 1e-9 and abs(sol["geloescht"][1] - F) < 1e-6 * F, str(sol["geloescht"]))
    for maske in ("eins", "situation", "aus"):
        close(f"Gelagerter Koerperknoten des abgeschalteten Arms, Maske {maske}: Summe Rz gleich Gegenrechnung",
              sol[maske][1], sol["geloescht"][1], 1e-9, "N")
        check(f"… Maske {maske}: w(b) gleich Gegenrechnung (gehalten)",
              abs(sol[maske][0] - sol["geloescht"][0]) <= 1e-9, f"{sol[maske][0]:.3e} m")


# --------------------------------------------------------------------------
# Merkmal Stand 71
# --------------------------------------------------------------------------
def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("maske_stabende_kopplung")
    check("Merkmal maske_stabende_kopplung: Stand 71, Fehlerkorrektur, fix/k10-maske2, VERFAHRENSSTAND = 71",
          mk is not None and mk.wechsel[-1].stand == 71 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-maske2" and rv.VERFAHRENSSTAND == 71,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    mk65 = rv.merkmal("maske_starrkoerper_last")
    mk67 = rv.merkmal("maske_lager_verteilung")
    for maske in MASKEN:
        m, b, q = fall_q(maske)
        m.load_node(q, Fz=-F, case="LF1")
        check(f"betrifft: Last an Q hinter der Kopplung „Stabende“, Maske {maske}; Stände 65 und 67 nicht",
              mk.betrifft(m) and not mk65.betrifft(m) and not mk67.betrifft(m),
              f"{mk.betrifft(m)} {mk65.betrifft(m)} {mk67.betrifft(m)}")
    m, b, q = fall_q("situation", rho=1.0 / (1e-2 * L))
    m.add_punktmasse(q, 100.0)
    m.load_cases["LF1"].gravity = [0.0, 0.0, -9.81]
    check("betrifft: Punktmasse an Q bei Eigengewicht (Situation)", mk.betrifft(m))
    m0, b0, q0 = fall_q("keine")
    m0.load_node(q0, Fz=-F, case="LF1")
    check("betrifft nicht: ohne Maske, Theorie I. Ordnung", not mk.betrifft(m0))
    m3, b3, q3 = fall_q("keine")
    m3.load_node(q3, Fz=-F, case="LF1")
    m3.load_cases["LF1"].theorie = "III"
    m4, b4, q4 = fall_q("keine", k=1e6)
    m4.load_node(q4, Fz=-F, case="LF1")
    m4.load_cases["LF1"].theorie = "III"
    check("betrifft: starre Kopplung nach Theorie III. Ordnung ohne Maske; federnd nicht",
          mk.betrifft(m3) and not mk.betrifft(m4), f"{mk.betrifft(m3)} {mk.betrifft(m4)}")
    m5, a5, b5, c5, d5 = basis("situation")
    stabende(m5, b5, d5)
    m5.load_node(b5, Fz=-F, case="LF1")
    m5.load_node(d5, Fz=-F, case="LF1")
    check("betrifft nicht: Koerperknoten am abgeschalteten Arm (Schutz)", not mk.betrifft(m5))
    m6, b6, q6 = fall_q("aus")
    m6.load_node(q6, Fz=-F, case="LF1")
    an = _still(solver.solve_all, m6, workers=1, design=False)
    im = mk.im_ergebnis(m6, an) or ""
    check("im Ergebnis: LF1 genannt", "LF1" in im, repr(im))


def main():
    for t in (test_theorie1, test_einsermaske_direkt, test_theorie2, test_knicken, test_schwingung,
              test_theorie3, test_spannschritt, test_schutz, test_merkmal):
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
