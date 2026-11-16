"""
Runde k10e (16.11.2026), Fehler Nr. 27 der Liste, Verfahrensstand 77:
Theorie III. Ordnung rechnet starre und verteilende Kopplungen.

Seit Stand 71 (fix/k10-maske2, 00ad5ed7) wies Theorie III. Ordnung eine
starre Kopplung eines Stabendes (Kopplung „Stabende“, starre Knotenkopplung)
mit Klartext ab; vorher rechnete sie sie still als Feder von 10 000 N/m.
Ebenso abgewiesen seit Stand 64 (Runde k8): jeder wirkende Starrkoerper
(RBE2, RBE3, verteilende Kopplung eines Stabendes) und jede starre
Knotenkopplung (theorie3.kopplung_sperre). Die Modelle sind rechenbar.

Seither rechnet Theorie III. Ordnung sie als Zwangsbedingung (theorie3._Zwang):
die linearen Zeilen derselben Kopplung wie in Theorie I. Ordnung, im
mitgedrehten System des Masters angesetzt - ein starrer Arm mit grossen
Drehungen wie beim Versatz der Stabenden; die Kraft der Kopplung ist eine
eigene Unbekannte (erweitertes Lagrange-Verfahren), die Bedingung ist am Ende
auf Rundungsniveau erfuellt. Abgewiesen wird nur eine Zwangsbedingung, die
keine Starrkoerperbedingung ist (kommt mit den Kopplungen des Programms nicht
vor).

Sollwerte, je zwei Wege:
* Kragarm L = 3 m, E I = 210 000 N/mm² · 8 000 cm⁴, F = 1 kN:
  w = F L³/(3 E I) = 0,535714 mm (Hand) und Theorie I. Ordnung.
* Halbkreis: Endmoment M = π E I/L ueber einen RBE2-Arm 0,5 m (Master am
  Lastknoten bzw. am Stabende): n gleiche Elemente bilden ein Sehnenpolygon,
  Ende bei x = 0, z = -(L/n)/sin(π/(2n)), Drehung π, Lastknoten 0,5 m
  dahinter (Hand), und dasselbe Moment direkt am Stabende ohne Kopplung.
* Kraeftepaar ±F an einem starren Arm ±h quer zum Stab (starre Scheibe bzw.
  RBE2): das Moment 2 F h cos θ dreht mit; Gleichgewicht E I θ/L = 2 F h cos θ,
  fuer θ = 60° das Sehnenpolygon mit der Elementdrehung θ/n (Hand) und ein
  Modell mit sehr steifen kurzen Staeben statt der Kopplung (in diesem
  Lastfall ohne Normalkraft im Stummel).
* Stabende an drei gelagerten Knoten ohne Element (beidseitig eingespannter
  Balken): w(Mitte) = F L³/(192 E I) und Theorie I. Ordnung.
* Kleine Last: Kragarm mit RBE2-Arm 0,3 m quer, 10 N: Theorie I., II. und
  III. Ordnung gleich, w(P) = F L³/(3 E I) + F a² L/(G I_T) (Hand).
* Kragstuetze mit RBE2-Arm 0,3 m und 200 kN Druck: wie Balken STARR (sehr
  steif, damit der Stummel nicht mitbiegt) und wie Versatz der Stabenden.

Merkmal theorie3_rbe2_angehaengt (Stand 77): Was vorher abgewiesen wurde,
rechnet jetzt - ohne Merkmal. Geaendert hat sich ein Ergebnis, das vorher
ohne Abweisung entstand: Kopplung „Stabende“ b-Q, Q ohne Element, daran per
RBE2 der unbelastete Knoten P - w(P) 0 statt 0,5357 mm. Ergebnisse vor
Stand 71 mit der Feder 10 000 N/m kennzeichnet weiter maske_stabende_kopplung
(00ad5ed7), die vor Stand 64 theorie3_starrkoerper.

Aufruf:  python -m tests.test_th3_starre_kopplung_k10e
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

E = 210e9
L = 3.0
I = 8e-5
F = 1e3
EI = E * I
HAND = F * L ** 3 / (3 * EI)                         # 0,535714 mm
EINS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    sys.stdout.flush()
    return ok


def nahe_mm(name, ist, soll, tol_mm=0.001):
    """Abstand in mm (Fehlerbegriff: 0,001 mm)."""
    ok = ist is not None and soll is not None and all(math.isfinite(x) for x in np.ravel([ist, soll]))
    d = float(np.max(np.abs(np.asarray(ist, float) - np.asarray(soll, float)))) * 1e3 if ok else float("nan")
    return check(name, ok and d <= tol_mm, f"Abweichung {d:.7f} mm (Grenze {tol_mm} mm)")


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def _modell(n=1, A=1e-2, It=1e-5):
    from statik3d.model import Model, Material, Section
    m = Model("k10e")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=It, zmax=0.1, ymax=0.1))
    m.add_section(Section("STEIF", A=100.0, Iy=100.0, Iz=100.0, It=100.0, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    st = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(n)]
    m.add_member("S", st)
    m.fix(ids[0], "all")
    return m, ids


def th3(m, schritte=10, stabteilung=False, aktiv=None):
    """(u (nn, 6) oder None, Fehlertext, Results)."""
    from statik3d.theorie3 import solve_theorie3
    try:
        r, info = _still(solve_theorie3, m, {"LF1": 1.0}, "LF1", imperfektionen=False, schritte=schritte,
                         stabteilung=stabteilung, aktiv=aktiv)
    except ValueError as ex:
        return None, str(ex), None
    return np.asarray(r.u).reshape(-1, 6), info.fehler or "", r


def th1(m):
    from statik3d import solver
    return np.asarray(_still(solver.solve_static, m, case="LF1").u).reshape(-1, 6)


def lage(m, u, k):
    return np.asarray(m.nodes[k], float) + u[k, :3]


def _stabende(m, b, q, gruppe=None):
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    m.kopplungen.append(Kopplung(b, q, EINS, [float("inf")] * 3, gruppe or STABENDE_GRUPPE + f"K{b}"))


# --------------------------------------------------------------------------
# Fehler Nr. 27: starre Kopplung „Stabende“, ueber solve_all und Modellpruefung
# --------------------------------------------------------------------------
def test_fehler27():
    from statik3d import solver
    from statik3d.theorie3 import kopplung_sperre_modell
    from tests import test_stabende_kopplung_k10 as ts
    for maske in ("keine", "eins", "situation", "aus"):
        m, b, q = ts.fall_q(maske)
        m.load_node(q, Fz=-F, case="LF1")
        u1 = np.asarray(_still(solver.solve_all, m, workers=1, design=False).cases["LF1"].u).reshape(-1, 6)
        m.load_cases["LF1"].theorie = "III"
        fehler_pr = [z for z in m.check() if z.startswith("FEHLER") and "Theorie III" in z]
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.cases["LF1"]
        f = an.theorie3.kombinationen["LF1"].fehler if an.theorie3 is not None else "keine Theorie III"
        u = np.asarray(r.u).reshape(-1, 6)
        R = np.asarray(r.reactions).reshape(-1, 6)
        check(f"Kopplung „Stabende“ b-Q starr, 1 kN an Q, Maske {maske}: nach Theorie III. Ordnung gerechnet, "
              "keine Abweisung (auch nicht in der Modellprüfung)",
              not f and str(r.info.get("theorie", "")).startswith("III") and not fehler_pr
              and not kopplung_sperre_modell(m), f"{r.info.get('theorie')} „{(f or '')[:80]}“ {fehler_pr}")
        nahe_mm(f"… Maske {maske}: w(Q) = F L³/(3 E I) (Hand)", -u[q, 2], HAND, 1e-5)
        nahe_mm(f"… Maske {maske}: w(Q) = Theorie I. Ordnung", u[q, 2], u1[q, 2], 1e-5)
        nahe_mm(f"… Maske {maske}: w(b) = w(Q) (starr)", u[b, 2], u[q, 2], 1e-9)
        check(f"… Maske {maske}: Summe Rz = 1 kN", abs(R[:, 2].sum() - F) <= 1e-6 * F, f"{R[:, 2].sum():.6f} N")


# --------------------------------------------------------------------------
# Grosse Drehung: Halbkreis ueber einen RBE2-Arm
# --------------------------------------------------------------------------
def halbkreis(art, n=16, arm=0.5):
    m, ids = _modell(n)
    b = ids[-1]
    M = math.pi * EI / L
    if art == "direkt":
        m.load_node(b, My=M)
        return m, b, b
    p = m.add_node(L + arm, 0, 0)
    if art == "rbe2":                      # Master am Lastknoten P
        m.add_starrkoerper(p, [b], "RBE2", name="Arm")
    elif art == "rbe2_stabende":           # Master am Stabende b
        m.add_starrkoerper(b, [p], "RBE2", name="Arm")
    m.load_node(p, My=M)
    return m, b, p


def test_halbkreis():
    n, arm = 16, 0.5
    z_hand = -(L / n) / math.sin(math.pi / (2 * n))
    soll_b = np.array([0.0, 0.0, z_hand])
    soll_p = soll_b + np.array([-arm, 0.0, 0.0])
    md, bd, _pd = halbkreis("direkt", n)
    ud, fd, _r = th3(md)
    check("Halbkreis, Moment direkt am Stabende (zweiter Weg): gerechnet", ud is not None and not fd, fd[:100])
    nahe_mm("… Stabende auf dem Sehnenpolygon: x = 0, z = -(L/n)/sin(π/2n) (Hand)",
            lage(md, ud, bd) if ud is not None else None, soll_b)
    for art in ("rbe2", "rbe2_stabende"):
        m, b, p = halbkreis(art, n, arm)
        u, f, _r = th3(m)
        wo = "Master am Lastknoten" if art == "rbe2" else "Master am Stabende"
        check(f"Halbkreis über RBE2-Arm {arm} m ({wo}): Theorie III. Ordnung gerechnet", u is not None and not f,
              f[:120])
        if u is None:
            continue
        nahe_mm(f"… Stabende = Hand (Sehnenpolygon, 16 Elemente)", lage(m, u, b), soll_b)
        nahe_mm(f"… Stabende = Moment direkt am Stabende", lage(m, u, b), lage(md, ud, bd) if ud is not None else None)
        nahe_mm(f"… Lastknoten P 0,5 m hinter dem Stabende, Arm um π gedreht (Hand)", lage(m, u, p), soll_p)
        dreh = float(np.linalg.norm(u[b, 3:]))
        check(f"… Drehung am Stabende = π (auf 1e-6 rad), am Lastknoten gleich", abs(dreh - math.pi) <= 1e-6
              and abs(float(np.linalg.norm(u[p, 3:])) - math.pi) <= 1e-6, f"{dreh:.9f} rad")


# --------------------------------------------------------------------------
# Kraeftepaar an einem starren Arm: das Moment dreht mit
# --------------------------------------------------------------------------
H_ARM = 0.25


def kraeftepaar(art, F_p, n=8):
    from statik3d.model import Kopplung
    from statik3d.fugen import STARR_GRUPPE
    m, ids = _modell(n)
    b = ids[-1]
    p1 = m.add_node(L, 0, H_ARM)
    p2 = m.add_node(L, 0, -H_ARM)
    p3 = m.add_node(L, H_ARM, 0)
    if art == "scheibe":
        for p in (p1, p2, p3):
            m.kopplungen.append(Kopplung(b, p, EINS, [float("inf")] * 3, STARR_GRUPPE + "1"))
    elif art == "rbe2":
        m.add_starrkoerper(b, [p1, p2, p3], "RBE2", name="Arm")
    elif art == "stab":
        for p in (p1, p2, p3):
            m.add_element("beam", [b, p], "ST", "STEIF")
    m.load_node(p1, Fx=F_p)
    m.load_node(p2, Fx=-F_p)
    return m, b


def _polygon(theta, n):
    lk = L / n
    x = sum(lk * math.cos((k + 0.5) * theta / n) for k in range(n))
    z = -sum(lk * math.sin((k + 0.5) * theta / n) for k in range(n))
    return np.array([x, 0.0, z])


def test_kraeftepaar():
    n = 8
    theta = math.pi / 3
    F_p = EI * theta / (2 * H_ARM * L * math.cos(theta))
    soll = _polygon(theta, n)
    ms, bs = kraeftepaar("stab", F_p, n)
    us, fs, _r = th3(ms, schritte=30)
    check("Kräftepaar am Arm aus sehr steifen kurzen Stäben (zweiter Weg, 30 Laststufen): gerechnet",
          us is not None and not fs, fs[:100])
    for art in ("scheibe", "rbe2"):
        m, b = kraeftepaar(art, F_p, n)
        u, f, _r = th3(m)
        wo = "starre Scheibe (Kopplungen)" if art == "scheibe" else "RBE2"
        check(f"Kräftepaar ±{F_p / 1e3:.1f} kN am Arm ±{H_ARM} m, {wo}: Theorie III. Ordnung gerechnet",
              u is not None and not f, f[:120])
        if u is None:
            continue
        nahe_mm(f"… Stabende = Sehnenpolygon für θ = 60° (Hand, E I θ/L = 2 F h cos θ)", lage(m, u, b), soll)
        check(f"… Drehung am Stabende = 60° (auf 1e-6 rad)", abs(float(np.linalg.norm(u[b, 3:])) - theta) <= 1e-6,
              f"{float(np.linalg.norm(u[b, 3:])):.9f} rad")
        if us is not None:
            nahe_mm(f"… Stabende = Modell mit steifen Stäben", lage(m, u, b), lage(ms, us, bs))


# --------------------------------------------------------------------------
# Stabende an drei gelagerten Knoten ohne Element
# --------------------------------------------------------------------------
def test_eingespannt():
    m, ids = _modell(2)
    a, c, b = ids
    for q in (m.add_node(L, 0.1, 0.1), m.add_node(L, -0.1, 0.1), m.add_node(L, 0.0, -0.1)):
        m.fix(q, "all")
        _stabende(m, b, q)
    m.load_node(c, Fz=-F)
    u1 = th1(m)
    u3, f, _r = th3(m)
    hand = F * L ** 3 / (192 * EI)
    check("Stabende an drei gelagerten Knoten ohne Element: Theorie III. Ordnung gerechnet", u3 is not None and not f,
          f[:120])
    if u3 is not None:
        nahe_mm("… w(Mitte) = F L³/(192 E I) (Hand, beidseitig eingespannt)", -u3[c, 2], hand, 1e-5)
        nahe_mm("… w(Mitte) = Theorie I. Ordnung", u3[c, 2], u1[c, 2], 1e-5)
        nahe_mm("… Stabende gehalten", u3[b, :3], np.zeros(3), 1e-9)


# --------------------------------------------------------------------------
# Kleine Last: Theorie I., II. und III. Ordnung
# --------------------------------------------------------------------------
def test_kleine_last():
    from statik3d import solver
    a_arm, F_k, It = 0.3, 10.0, 1e-5
    G = E / (2 * 1.3)
    hand = F_k * L ** 3 / (3 * EI) + F_k * a_arm ** 2 * L / (G * It)
    werte = {}
    for th in ("I", "II", "III"):
        m, ids = _modell(4)
        b = ids[-1]
        p = m.add_node(L, a_arm, 0)
        m.add_starrkoerper(p, [b], "RBE2", name="Arm")
        m.load_node(p, Fz=-F_k)
        m.load_cases["LF1"].theorie = th
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.cases["LF1"]
        werte[th] = (-np.asarray(r.u).reshape(-1, 6)[p, 2], str(r.info.get("theorie", "")))
    for th in ("I", "II", "III"):
        # Theorie I. Ordnung traegt keinen Vermerk oder „I“
        check(f"RBE2-Arm 0,3 m quer, 10 N: nach Theorie {th}. Ordnung gerechnet",
              werte[th][1].startswith(th) if th != "I" else not werte[th][1].startswith("II"), werte[th][1])
        nahe_mm(f"… Theorie {th}. Ordnung: w(P) = F L³/(3 E I) + F a² L/(G I_T) (Hand)", werte[th][0], hand, 1e-6)
    nahe_mm("… Theorie III. = Theorie I. Ordnung", werte["III"][0], werte["I"][0], 1e-6)
    nahe_mm("… Theorie III. = Theorie II. Ordnung", werte["III"][0], werte["II"][0], 1e-6)


# --------------------------------------------------------------------------
# Gleichwertiges Modell: sehr steifer kurzer Stab und Versatz
# --------------------------------------------------------------------------
def kragstuetze(art, n_st=10):
    """Kragstütze 4 m, 200 kN Druck mit 1 kN und 2 kN quer am Lastknoten b;
    Arm von b zum Stabende 0,3 m quer: RBE2, sehr steifer Stab oder Versatz."""
    from statik3d.model import Model, Material, Section
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    m.add_section(Section("STEIF", A=100.0, Iy=100.0, Iz=100.0, It=100.0, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    a = m.add_node(0, 0, 0)
    b = m.add_node(4.0, 0, 0)
    m.fix(a, "all")
    ende = np.array([4.0, 0.0, 0.3])
    if art == "versatz":
        m.netz.stabteilung = n_st
        stab = [m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[[0, 0, 0], [0, 0, 0.3]])]
    else:
        m.netz.stabteilung = 1
        ids = [a] + [m.add_node(*(ende * k / n_st)) for k in range(1, n_st + 1)]
        stab = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(n_st)]
        if art == "stab":
            m.add_element("beam", [b, ids[-1]], "ST", "STEIF")
        else:
            m.add_starrkoerper(b, [ids[-1]], "RBE2", name="Arm")
    m.add_member("S", stab)
    m.load_node(b, Fx=-200e3, Fy=1e3, Fz=2e3)
    return m, b


def test_gleichwertig():
    w = {}
    for art in ("rbe2", "stab", "versatz"):
        m, b = kragstuetze(art)
        u, f, _r = th3(m, stabteilung=True)
        w[art] = None if u is None else u[b, :3]
        check(f"Kragstütze 200 kN, Arm 0,3 m als {art}: Theorie III. Ordnung gerechnet", u is not None and not f,
              f[:120])
    if all(v is not None for v in w.values()):
        nahe_mm("… RBE2 = sehr steifer Stab (Kopfknoten)", w["rbe2"], w["stab"])
        check("… RBE2 = Versatz der Stabenden (auf 0,5 %, andere Teilung)",
              float(np.abs(w["rbe2"] - w["versatz"]).max()) <= 5e-3 * float(np.abs(w["versatz"]).max()),
              f"{w['rbe2'] * 1e3} / {w['versatz'] * 1e3} mm")
        check("… Theorie III. Ordnung über Theorie I. Ordnung (Druck mit Ausmitte)",
              float(np.abs(w["rbe2"]).max()) > 1.1 * float(np.abs(th1(kragstuetze("rbe2")[0])[1, :3]).max()))


# --------------------------------------------------------------------------
# Merkmal Stand 77: RBE2 an einem angehaengten Knoten
# --------------------------------------------------------------------------
def angehaengt(maske="keine"):
    """Kragarm, Kopplung „Stabende“ b-Q (Q ohne Element), daran per RBE2 der
    Knoten P 0,5 m darueber, ohne Last; 1 kN an b, LF1 nach Theorie III."""
    from tests import test_stabende_kopplung_k10 as ts
    m, b, q = ts.fall_q(maske)
    p = m.add_node(L, 0, 0.5)
    m.add_starrkoerper(q, [p], "RBE2", name="Haken")
    m.load_node(b, Fz=-F, case="LF1")
    return m, b, q, p


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("theorie3_rbe2_angehaengt")
    check("Merkmal theorie3_rbe2_angehaengt: Stand 77, Fehlerkorrektur, 16.11.2026, VERFAHRENSSTAND 77 = höchster",
          mk is not None and mk.wechsel[-1].stand == 77 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].datum == "16.11.2026" and rv.VERFAHRENSSTAND == 77
          and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    m, b, q, p = angehaengt()
    u1 = th1(m)
    m.load_cases["LF1"].theorie = "III"
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.cases["LF1"]
    u = np.asarray(r.u).reshape(-1, 6)
    check("RBE2 Q-P hinter der Kopplung „Stabende“: Theorie III. Ordnung gerechnet",
          str(r.info.get("theorie", "")).startswith("III"), r.info.get("theorie"))
    nahe_mm("… w(P) = Theorie I. Ordnung (bis Stand 76 automatisch festgehalten: 0 mm)", u[p, 2], u1[p, 2], 1e-5)
    nahe_mm("… w(P) = w(b) = Hand", -u[p, 2], HAND, 1e-5)
    if mk is None:
        return
    check("… Merkmal betrifft", mk.betrifft(m) is True, mk.betrifft(m))
    im = mk.im_ergebnis(m, an) or ""
    check("… im Ergebnis: LF1 genannt", "LF1" in im, repr(im))
    alt = dict(rv.aktuelle_merkmale(m))
    alt["theorie3_rbe2_angehaengt"] = "alt"
    st = rv.betroffen(m, alt, an)
    check("… Ergebnis vom alten Stand: „möglicherweise betroffen“", mk.titel in (st or ""), (st or "")[:160])
    m0, b0, q0 = angehaengt()[:3]
    m0.starrkoerper = []
    m0.load_cases["LF1"].theorie = "III"
    check("betrifft nicht: dasselbe ohne RBE2", not mk.betrifft(m0), mk.betrifft(m0))
    m2, *_r = angehaengt()
    check("betrifft nicht: nach Theorie I. Ordnung", not mk.betrifft(m2), mk.betrifft(m2))
    m3, b3, q3, p3 = angehaengt()
    m3.load_node(p3, Fz=-F, case="LF1")
    m3.load_cases["LF1"].theorie = "III"
    check("betrifft nicht: mit Last an P (bis Stand 76 abgewiesen, jetzt neu gerechnet)", not mk.betrifft(m3),
          mk.betrifft(m3))


def test_alte_staende_gekennzeichnet():
    """Ergebnisse vor Stand 71 (Feder 10 000 N/m) und vor Stand 64 bleiben
    gekennzeichnet: die Merkmale fragen die Wirkung, nicht die Abweisung."""
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    from tests import test_stabende_kopplung_k10 as ts
    m, b, q = ts.fall_q("keine")
    m.load_node(q, Fz=-F, case="LF1")
    m.load_cases["LF1"].theorie = "III"
    an = _still(solver.solve_all, m, workers=1, design=False)
    for name in ("maske_stabende_kopplung", "theorie3_starrkoerper"):
        mk = rv.merkmal(name)
        alt = dict(rv.aktuelle_merkmale(m))
        alt[name] = "alt"
        st = rv.betroffen(m, alt, an) or ""
        check(f"Kopplung „Stabende“ b-Q mit Last an Q nach Theorie III: Ergebnis vor dem Wechsel von {name} "
              "gekennzeichnet", mk is not None and mk.betrifft(m) and mk.titel in st, st[:160])
    m4, b4, q4 = ts.fall_q("keine", k=1e6)
    m4.load_node(q4, Fz=-F, case="LF1")
    m4.load_cases["LF1"].theorie = "III"
    check("… federnde Kopplung: nicht gekennzeichnet (rechnete immer richtig)",
          not rv.merkmal("maske_stabende_kopplung").betrifft(m4) and not rv.merkmal("theorie3_starrkoerper").betrifft(m4))


# --------------------------------------------------------------------------
# Knoten ohne Element, die ihre Kopplung nicht bestimmt
# --------------------------------------------------------------------------
def test_hilfsfesselung():
    """RBE3 „Stabende 1“ am weichen Kragarm (L = 10 m, I = 1e-6 m⁴, 1 N an b)
    mit Slaves c, d, e ohne Element (tests.test_th3_konvergenz_k10d.weich):
    c und d gegeneinander in y bestimmt der RBE3 nicht. Mit 0,5 N in z an c
    rechnet Theorie III. Ordnung mit dieser Bewegung festgehalten und sagt es:
    w(b) = 1,5 N L³/(3 E I) = Theorie I. Ordnung. 1 N in y an c hat kein
    Gleichgewicht - Theorie I. Ordnung bricht ab, Theorie III. Ordnung meldet
    es, statt die Last still in die Fesselung zu geben."""
    from statik3d import solver
    from statik3d.theorie3 import solve_theorie3
    from tests import test_th3_konvergenz_k10d as tk
    fak = {"LF1": 1.0, "LF2": 1.0, "LF3": 1.0, "LF4": 1.0}
    for fy, fz in ((0.0, 0.5), (1.0, 0.0)):
        m, b = tk.weich("I", 0, 0)
        m.load_cases["LF2"].nodal_loads.clear()
        m.load_cases["LF3"].nodal_loads.clear()
        m.load_node(2, Fy=fy, Fz=-fz, case="LF2")
        try:
            an = _still(solver.solve_all, m, workers=1, design=False)
            u1, ex1 = np.asarray(an.combinations["LK1"].u).reshape(-1, 6), ""
        except Exception as ex:          # noqa: BLE001
            u1, ex1 = None, str(ex)
        try:
            r3, info = _still(solve_theorie3, m, fak, "LK1", imperfektionen=False)
            u3, f3, hin = np.asarray(r3.u).reshape(-1, 6), info.fehler or "", " ".join(info.hinweise)
        except ValueError as ex:
            u3, f3, hin = None, str(ex), ""
        if fz:
            check("RBE3 mit Slaves ohne Element, 0,5 N in z an c: Theorie III. Ordnung gerechnet, Hinweis auf die "
                  "festgehaltene Bewegung", u3 is not None and not f3 and "Hilfsfesselung" in hin, (f3 or hin)[:160])
            nahe_mm("… w(b) = 1,5 N L³/(3 E I) (Hand)", -u3[b, 2] if u3 is not None else None, 1.5 * tk.FLEX_W, 1e-5)
            nahe_mm("… w(b) = Theorie I. Ordnung", u3[b, 2] if u3 is not None else None,
                    u1[b, 2] if u1 is not None else None, 1e-5)
        else:
            check("1 N in y am Slave c: Theorie I. Ordnung ohne Gleichgewicht (Abbruch)", u1 is None
                  and "Gleichgewicht" in ex1, ex1[:120])
            check("… Theorie III. Ordnung meldet „kein Gleichgewicht“ statt die Last still in die Fesselung zu geben",
                  "kein Gleichgewicht" in f3 and "Hilfsfesselung" in f3, f3[:160])


# --------------------------------------------------------------------------
# Nicht rechenbare Zwangsbedingung
# --------------------------------------------------------------------------
def test_nicht_rechenbar():
    from statik3d.theorie3 import _Zwang
    X = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    gut = np.zeros((1, 12))
    gut[0, [0, 6]] = [-1.0, 1.0]                     # u_x gleich: Starrkoerperbedingung ohne Drehung
    gut[0, 3:6] = 0.0
    z = _Zwang("gut", "Kopplung", gut, list(range(12)), 0, X)
    check("Zwang u_x(B) = u_x(A): rechenbar", z.rechenbar)
    schlecht = np.zeros((1, 12))
    schlecht[0, [2, 8]] = [-1.0, 1.0]                 # u_z gleich bei Abstand 1 m in x
    schlecht[0, 4] = 0.5                              # Drehung des Masters mit falschem Arm
    z2 = _Zwang("schlecht", "Kopplung", schlecht, list(range(12)), 0, X)
    check("Zwang mit Drehung des Masters, der keine Starrkörperbedingung ist: nicht rechenbar", not z2.rechenbar)


def main():
    for t in (test_fehler27, test_halbkreis, test_kraeftepaar, test_eingespannt, test_kleine_last,
              test_gleichwertig, test_merkmal, test_alte_staende_gekennzeichnet, test_hilfsfesselung,
              test_nicht_rechenbar):
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
