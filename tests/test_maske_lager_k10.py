"""
Behebung vom 15.11.2026, Runde k10 (vom Anwender freigegeben), Verfahrensstand 67:
Elementmaske am gelagerten Knoten abgeschalteter Elemente (N1), an der
verteilenden Kopplung eines Stabendes mit Slaves ohne Element (N2), und das
Merkmal des Stands 65 fuer Schwingungsnachweise in einer Situation.

N1: situationen.wirksame_knoten nahm als Ausgangspunkt nur Lagerknoten, an
denen im ganzen Modell kein Element haengt. Ein Lagerknoten, dessen Elemente
alle abgeschaltet sind, trug nicht mit, und eine Last, die ueber eine
Kopplung an ihm haengt, entfiel still (Fall M8 der zweiten k9-Gegenpruefung:
toter Arm c-d, Lager an c, Y per Feder an c, 5 kN an Y - mit Maske Summe Rz
1 000 N, Gegenrechnung 6 000 N, Gleichgewichtskontrolle „ok“).
theorie3._wirksame_knoten_th3 hatte dieselbe Regel.

N2: Bei der verteilenden Kopplung eines Stabendes (stabeinleitung.ist_verteilkopplung)
loeste nur ein wirksamer Slave die Huelle aus, damit ein abgeschalteter
Koerper ueber den Stab nicht wieder auflebt. Ein Slave ohne jedes Element ist
aber kein Koerperknoten: Master b am wirksamen Kragarmende, einziger Slave Q
ohne Element, 1 kN an Q - mit Maske w = 0 und Summe Rz 0 N, Gegenrechnung
0,535714 mm und 1 000 N (Fall V1). Dazu bei einem einzigen Slave und einem
Master ohne Stab die Warnung „invalid value encountered in divide“ in
stabeinleitung.wirksame_gewichte (Normale null, e1 = 0/0).

Schwingung: Der Schwingungsnachweis rechnet die Eigenformen in der Situation
seines Wasserdruck-Generierers (schwingung.nachweis -> solve_modal mit der
Maske); dort maskiert assemble.kopplungen ueber dieselbe Huelle. Das Merkmal
maske_starrkoerper_last (Stand 65) sah nur die Lastfaelle der Situationen
und den Spannschritt.

Sollwerte, je zwei Wege:
* Handformel: Kragarm L = 3 m, E I = 210 000 N/mm² · 8 000 cm⁴, F = 1 kN am
  Ende: w = F L³ / (3 E I) = 0,5357 mm; Federkette m an k: f = √(k/m) / 2π.
* Gegenrechnung: dasselbe Modell, das abgeschaltete Element geloescht (seine
  Knoten bleiben), ohne Maske.

Schutz: Am ganz abgeschalteten Arm ohne Lager bleibt alles unwirksam; der
Endknoten d des abgeschalteten Arms als Slave der verteilenden Kopplung lebt
ueber den Stab nicht wieder auf.

Aufruf:  python -m tests.test_maske_lager_k10
"""
import contextlib
import io
import math
import os
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def close(name, ist, soll, rel=1e-6, einheit="mm"):
    ok = ist is not None and math.isfinite(ist) and abs(ist - soll) <= rel * max(abs(soll), 1e-12)
    return check(name, ok, f"ist {ist if ist is None else f'{ist:.6f}'} {einheit}, soll {soll:.6f} {einheit}")


E = 210e9
L = 3.0
I = 8e-5
F = 1e3
HAND = F * L ** 3 / (3 * E * I)                     # 0,5357 mm
TEXT_SK = "Theorie III. Ordnung rechnet keine Starrkörper"
TEXT_KP = "Theorie III. Ordnung rechnet keine starren Knotenkopplungen"
MASKEN = ("situation", "aus")


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def basis(maske, rho=0.0, teile=1):
    """Kragarm a-b (x = 0..L, eingespannt in a, ``teile`` Elemente), zweiter
    Kragarm c-d bei y = 2 m (eingespannt in c, ein Element). maske: 'keine' |
    'situation' (c-d in der Situation s aus) | 'aus' (c-d als Stab „aus“) |
    'geloescht' (Gegenrechnung: das Element c-d fehlt, seine Knoten bleiben).
    Rueckgabe (Modell, a, b, c, d)."""
    from statik3d.model import Model, Material, Section, Situation
    m = Model("k10")
    m.add_material(Material("ST", E=E, nu=0.3, rho=rho, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    kn = [m.add_node(L * i / teile, 0, 0) for i in range(teile + 1)]
    for i in range(teile):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    a, b = kn[0], kn[-1]
    m.fix(a, "all")
    c = m.add_node(0, 2, 0)
    d = m.add_node(L, 2, 0)
    e_arm = None
    if maske != "geloescht":
        e_arm = m.add_element("beam", [c, d], "ST", "Q")
        if maske == "aus":
            m.add_member("S2", [e_arm], aus=True)
    m.fix(c, "all")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    if maske == "situation":
        m.situationen["s"] = Situation("s", "", [e_arm])
        m.load_cases["LF1"].situation = "s"
    return m, a, b, c, d


def _feder(a, b, k=1e12, starr=False):
    from statik3d.model import Kopplung
    return Kopplung(a, b, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [float("inf") if starr else k] * 3, "Feder")


def _aktiv(m, maske):
    return m.aktive_elemente("s" if maske == "situation" else "")


def rechne(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.cases["LF1"]
    return an, np.asarray(r.u).reshape(-1, 6), np.asarray(r.reactions).reshape(-1, 6)


def _gg_ok(an):
    gg = an.cases["LF1"].info.get("gleichgewicht_global") or {}
    return gg.get("ok")


# --------------------------------------------------------------------------
# N1: gelagerter Knoten, dessen Elemente alle abgeschaltet sind
# --------------------------------------------------------------------------
def m8(maske, starr=False, k=1e12):
    """Fall M8: Y = (0, 2, 0,5) ohne Element per Feder an den Lagerknoten c
    des abgeschalteten Arms; 1 kN an b, 5 kN an Y."""
    m, a, b, c, d = basis(maske)
    y = m.add_node(0, 2, 0.5)
    m.kopplungen.append(_feder(y, c, k=k, starr=starr))
    m.load_node(b, Fz=-F, case="LF1")
    m.load_node(y, Fz=-5 * F, case="LF1")
    return m, b, c, d, y


def test_n1_m8():
    from statik3d.situationen import wirksame_knoten
    m0, b0, c0, _d0, y0 = m8("geloescht")
    an0, u0, r0 = rechne(m0)
    close("M8 Gegenrechnung: Summe Rz = 6 kN (Hand: alles geht ins Lager)", r0[:, 2].sum(), 6 * F, 1e-9, "N")
    close("M8 Gegenrechnung: Rz(c) = 5 kN (Hand)", r0[c0, 2], 5 * F, 1e-9, "N")
    for maske in MASKEN:
        m, b, c, d, y = m8(maske)
        kn = wirksame_knoten(m, _aktiv(m, maske))
        check(f"M8 Maske {maske}: Lagerknoten c und Y wirksam, Arm-Ende d nicht",
              bool(kn[c] and kn[y] and not kn[d]), f"c {kn[c]}, Y {kn[y]}, d {kn[d]}")
        an, u, r = rechne(m)
        close(f"M8 Maske {maske}: Summe Rz = 6 kN (Hand)", r[:, 2].sum(), 6 * F, 1e-9, "N")
        close(f"M8 Maske {maske}: Summe Rz gleich Gegenrechnung", r[:, 2].sum(), r0[:, 2].sum(), 1e-9, "N")
        close(f"M8 Maske {maske}: Rz(c) = 5 kN wie Gegenrechnung", r[c, 2], r0[c0, 2], 1e-9, "N")
        close(f"M8 Maske {maske}: w(b) = F L³/(3 E I) und Gegenrechnung", -u[b, 2] * 1e3, HAND * 1e3)
        close(f"M8 Maske {maske}: w(Y) gleich Gegenrechnung", -u[y, 2] * 1e6, -u0[y0, 2] * 1e6, 1e-6, "µm")
        check(f"M8 Maske {maske}: Gleichgewichtskontrolle ok, Last 6 kN darin",
              _gg_ok(an) is True and abs(abs((an.cases["LF1"].info.get("gleichgewicht_global") or {})
                                             .get("F_last", [0, 0, 0])[2]) - 6 * F) < 1e-6,
              str((an.cases["LF1"].info.get("gleichgewicht_global") or {}).get("F_last")))


def test_n1_last_am_lager():
    """Last unmittelbar am Lagerknoten c des abgeschalteten Arms: in der
    Gegenrechnung geht sie ins Lager."""
    sol = {}
    for maske in ("geloescht",) + MASKEN:
        m, a, b, c, d = basis(maske)
        m.load_node(b, Fz=-F, case="LF1")
        m.load_node(c, Fz=-2 * F, case="LF1")
        _an, _u, r = rechne(m)
        sol[maske] = (r[:, 2].sum(), r[c, 2])
    close("Last 2 kN am Lagerknoten c, Gegenrechnung: Rz(c) = 2 kN (Hand)", sol["geloescht"][1], 2 * F, 1e-9, "N")
    for maske in MASKEN:
        close(f"Last am Lagerknoten c, Maske {maske}: Rz(c) = 2 kN wie Gegenrechnung", sol[maske][1],
              sol["geloescht"][1], 1e-9, "N")
        close(f"Last am Lagerknoten c, Maske {maske}: Summe Rz = 3 kN wie Gegenrechnung", sol[maske][0],
              sol["geloescht"][0], 1e-9, "N")


def test_n1_schutz():
    """Ganz abgeschalteter Arm ohne Lager an der Kette: unwirksam wie bisher
    (RBE3 mit Master d und Slave Q, Last an Q). Lager c wird wirksam, d nicht."""
    from statik3d.situationen import wirksame_knoten
    for maske in MASKEN:
        m, a, b, c, d = basis(maske)
        q = m.add_node(L, 2, 0.5)
        m.add_starrkoerper(d, [q], "RBE3", name="R")
        m.load_node(b, Fz=-F, case="LF1")
        m.load_node(q, Fz=-5 * F, case="LF1")
        kn = wirksame_knoten(m, _aktiv(m, maske))
        check(f"Schutz toter Arm, Maske {maske}: d und Q unwirksam, Lager c wirksam",
              bool(kn[c] and not kn[d] and not kn[q]), f"c {kn[c]}, d {kn[d]}, Q {kn[q]}")
        _an, u, r = rechne(m)
        close(f"Schutz toter Arm, Maske {maske}: Summe Rz = 1 kN (Last am toten Arm wirkt nicht)", r[:, 2].sum(),
              F, 1e-9, "N")
        close(f"Schutz toter Arm, Maske {maske}: w(b) = Hand", -u[b, 2] * 1e3, HAND * 1e3)


def test_n1_theorie3():
    """Dieselbe Regel in theorie3._wirksame_knoten_th3: die starre Kopplung
    Y-c am Lagerknoten des abgeschalteten Arms wirkt (wie in der
    Gegenrechnung) und wird darum abgewiesen; federnd rechnet Theorie III.
    Ordnung die Last an Y mit (Summe Rz wie Gegenrechnung)."""
    from statik3d.theorie3 import starre_kopplung_sperre, _wirksame_knoten_th3, solve_theorie3
    m0, *_r = m8("geloescht", starr=True)
    gegen = starre_kopplung_sperre(m0, None)
    check("Th III Gegenrechnung: starre Kopplung am Lager c abgewiesen", TEXT_KP in gegen, gegen[:90])
    for maske in MASKEN:
        m, b, c, d, y = m8(maske, starr=True)
        aktiv = _aktiv(m, maske)
        kn = _wirksame_knoten_th3(m, aktiv)
        check(f"Th III Maske {maske}: Lager c und Y wirksam, d nicht", bool(kn[c] and kn[y] and not kn[d]),
              f"c {kn[c]}, Y {kn[y]}, d {kn[d]}")
        t = starre_kopplung_sperre(m, aktiv)
        check(f"Th III Maske {maske}: starre Kopplung am Lager c abgewiesen wie in der Gegenrechnung",
              TEXT_KP in t, t[:90])
    # federnd: gerechnet, Summe Rz wie Gegenrechnung
    sol = {}
    for maske in ("geloescht",) + MASKEN:
        m, b, c, d, y = m8(maske)
        aktiv = None if maske == "geloescht" else _aktiv(m, maske)
        try:
            r, info = _still(solve_theorie3, m, {"LF1": 1.0}, "LF1", imperfektionen=False, aktiv=aktiv)
            sol[maske] = float(np.asarray(r.reactions).reshape(-1, 6)[:, 2].sum())
        except Exception as ex:          # noqa: BLE001
            sol[maske] = None
            print(f"     Th III {maske}: {type(ex).__name__}: {str(ex)[:160]}")
    close("Th III federnd, Gegenrechnung: Summe Rz = 6 kN (Hand)", sol["geloescht"], 6 * F, 1e-6, "N")
    for maske in MASKEN:
        close(f"Th III federnd, Maske {maske}: Summe Rz gleich Gegenrechnung", sol[maske], sol["geloescht"],
              1e-6, "N")


# --------------------------------------------------------------------------
# N2: verteilende Kopplung eines Stabendes, Slave ohne Element
# --------------------------------------------------------------------------
def v1(maske):
    """Fall V1: RBE3 „Stabende K1“ mit Master b und einzigem Slave
    Q = (L, 0, 0,5) ohne Element; 1 kN an Q."""
    from statik3d import stabeinleitung as se
    m, a, b, c, d = basis(maske)
    q = m.add_node(L, 0, 0.5)
    m.add_starrkoerper(b, [q], "RBE3", name=se.STABENDE + "1")
    m.load_node(q, Fz=-F, case="LF1")
    return m, b, q, d


def test_n2_v1():
    from statik3d.situationen import wirksame_knoten
    from statik3d import stabeinleitung as se
    m0, b0, q0, _d = v1("geloescht")
    check("V1 ist eine verteilende Kopplung (stabeinleitung.ist_verteilkopplung)",
          se.ist_verteilkopplung(m0.starrkoerper[0]), m0.starrkoerper[0].name)
    _an0, u0, r0 = rechne(m0)
    close("V1 Gegenrechnung: w(b) = F L³/(3 E I)", -u0[b0, 2] * 1e3, HAND * 1e3)
    close("V1 Gegenrechnung: Summe Rz = 1 kN", r0[:, 2].sum(), F, 1e-9, "N")
    for maske in MASKEN:
        m, b, q, d = v1(maske)
        kn = wirksame_knoten(m, _aktiv(m, maske))
        check(f"V1 Maske {maske}: Slave Q wirksam", bool(kn[q] and kn[b]), f"Q {kn[q]}, b {kn[b]}")
        an, u, r = rechne(m)
        close(f"V1 Maske {maske}: w(b) = Hand", -u[b, 2] * 1e3, HAND * 1e3)
        close(f"V1 Maske {maske}: w(b) gleich Gegenrechnung", -u[b, 2] * 1e3, -u0[b0, 2] * 1e3, 1e-9)
        close(f"V1 Maske {maske}: Summe Rz = 1 kN wie Gegenrechnung", r[:, 2].sum(), r0[:, 2].sum(), 1e-9, "N")


def test_n2_schutz():
    """Die Regel des Stabendes bleibt: Ist ein Slave Knoten eines
    abgeschalteten Elements (Ende d des abgeschalteten Arms), macht der Master
    die Kopplung nicht wirksam - der abgeschaltete Koerper lebt ueber den Stab
    nicht wieder auf; die Last an d wirkt nicht."""
    from statik3d.situationen import wirksame_knoten
    from statik3d import stabeinleitung as se
    for maske in MASKEN:
        m, a, b, c, d = basis(maske)
        q = m.add_node(L, 1, 0.5)
        m.add_starrkoerper(b, [d, q], "RBE3", name=se.STABENDE + "1")
        m.load_node(b, Fz=-F, case="LF1")
        kn = wirksame_knoten(m, _aktiv(m, maske))
        check(f"Schutz Stabende, Maske {maske}: Slaves d (abgeschalteter Arm) und Q bleiben unwirksam",
              bool(kn[b] and not kn[d] and not kn[q]), f"b {kn[b]}, d {kn[d]}, Q {kn[q]}")


def test_n2_theorie3():
    """Dieselbe Regel in theorie3: die verteilende Kopplung mit Slave ohne
    Element wirkt (Gegenrechnung) - Theorie III. Ordnung weist sie ab, statt
    die Last an Q still zu verlieren."""
    from statik3d.theorie3 import starrkoerper_sperre
    m0, *_r = v1("geloescht")
    t0 = starrkoerper_sperre(m0, None)
    check("Th III V1 Gegenrechnung (ohne Maske): Starrkörper abgewiesen", TEXT_SK in t0, t0[:90])
    for maske in MASKEN:
        m, *_r = v1(maske)
        t = starrkoerper_sperre(m, _aktiv(m, maske))
        check(f"Th III V1 Maske {maske}: abgewiesen wie in der Gegenrechnung", TEXT_SK in t, t[:90])


def test_n2_warnung():
    """Ein Slave, Master ohne Stab: Normale null, e1 = 0/0 (RuntimeWarning
    „invalid value encountered in divide“, NaN in Abstand und Lage)."""
    from statik3d import stabeinleitung as se
    from statik3d.model import Model, Material, Section
    faelle = {}
    # (a) Fall V2 der Gegenpruefung: Master Q ohne Element, einziger Slave d
    m, a, b, c, d = basis("keine")
    q = m.add_node(L, 1, 0)
    m.add_starrkoerper(q, [d], "RBE3", name=se.STABENDE + "1")
    faelle["Master ohne Stab, Slave daneben"] = m
    # (b) einziger Slave am Ort des Masters, Master ohne Stab
    m2 = Model("k10 w")
    m2.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m2.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    p = m2.add_node(1, 1, 1)
    s = m2.add_node(1, 1, 1)
    m2.add_starrkoerper(p, [s], "RBE3", name=se.STABENDE + "1")
    faelle["einziger Slave am Ort des Masters"] = m2
    for text, mm in faelle.items():
        with warnings.catch_warnings(record=True) as w_:
            warnings.simplefilter("always")
            with np.errstate(all="warn"):
                wk = se.wirksame_gewichte(mm, mm.starrkoerper[-1], bindung=set())
        laut = [str(x.message) for x in w_ if issubclass(x.category, RuntimeWarning)]
        endlich = all(np.all(np.isfinite(np.asarray(wk[k], float))) for k in ("P", "normale", "w"))
        endlich = endlich and math.isfinite(wk["abstand_vorher"]) and math.isfinite(wk["abstand_nachher"])
        check(f"wirksame_gewichte, {text}: keine RuntimeWarning, alles endlich", not laut and endlich,
              f"Warnungen {laut[:2]}, P {wk['P']}, n {wk['normale']}, Abstand {wk['abstand_vorher']}")


# --------------------------------------------------------------------------
# Schwingung in einer Situation
# --------------------------------------------------------------------------
def _schwingung_dazu(m, situation):
    """Wasserdruck-Generierer in ``situation`` und ein Schwingungsnachweis
    dazu - wie die Maske Schwingung sie anlegt."""
    from statik3d.wasserdruck import Wasserdruck
    from statik3d.schwingung import Schwingungsnachweis
    m.wasserdruecke["W1"] = Wasserdruck("W1", situation=situation, flaechen=[0])
    m.schwingungen["Schwingung 1"] = Schwingungsnachweis("Schwingung 1", wasserdruck="W1")


def kette_modal(maske, k=1e4, masse=100.0):
    """Schwingung, Stand 65: Q = (L, 0, 0) per RBE2 an b, P per Feder k an
    Q (P und Q ohne Element), Punktmasse an P; Stab 1 kg. Kein Lastfall in
    der Situation - nur der Schwingungsnachweis rechnet dort."""
    m, a, b, c, d = basis(maske, rho=1.0 / (1e-2 * L), teile=8)
    m.load_cases.pop("LF1")
    q = m.add_node(L, 0, 0)
    p = m.add_node(L, 0, 0)
    m.add_starrkoerper(b, [q], "RBE2", name="K")
    m.kopplungen.append(_feder(p, q, k=k))
    m.add_punktmasse(p, masse)
    _schwingung_dazu(m, "s" if maske == "situation" else "")
    return m


def lager_modal(maske, k=1e4, masse=100.0):
    """Schwingung, Stand 67 (N1): Y ohne Element per Feder k an den
    Lagerknoten c des abgeschalteten Arms, Punktmasse an Y."""
    m, a, b, c, d = basis(maske, rho=1.0 / (1e-2 * L), teile=8)
    m.load_cases.pop("LF1")
    y = m.add_node(0, 2, 0.5)
    m.kopplungen.append(_feder(y, c, k=k))
    m.add_punktmasse(y, masse)
    _schwingung_dazu(m, "s" if maske == "situation" else "")
    return m


def _f1(m, maske):
    from statik3d import solver
    aktiv = None if maske == "geloescht" else _aktiv(m, maske)
    return float(np.asarray(_still(solver.solve_modal, m, 2, workers=1, aktiv=aktiv).freqs)[0])


def test_schwingung():
    """Die Huelle wirkt in der Schwingung ueber die Kopplungen (die
    Punktmassen maskiert die Massenmatrix nicht): f₁ gleich Gegenrechnung
    und Hand; das Merkmal erkennt den Schwingungsnachweis in der Situation."""
    from statik3d import rechenverfahren as rv
    from statik3d.situationen import kopplung_bleibt, aktive_knoten, wirksame_knoten
    k_balken = 3 * E * I / L ** 3
    hand_kette = math.sqrt(1.0 / (1.0 / 1e4 + 1.0 / k_balken) / 100.0) / (2 * math.pi)
    hand_lager = math.sqrt(1e4 / 100.0) / (2 * math.pi)
    for name, bauer, hand in (("Kette RBE2-Feder (Stand 65)", kette_modal, hand_kette),
                              ("Lager des abgeschalteten Arms (Stand 67)", lager_modal, hand_lager)):
        f0 = _f1(bauer("geloescht"), "geloescht")
        close(f"Schwingung {name}, Gegenrechnung: f₁ nach Hand", f0, hand, 2e-3, "Hz")
        for maske in MASKEN:
            m = bauer(maske)
            f = _f1(m, maske)
            # 1e-6: f₁ der Kette streut von Lauf zu Lauf um 1,5e-7 (ARPACK,
            # gemessen 15.11.2026 auch bei der Gegenrechnung selbst: 1,5873031
            # bis 1,5873034 Hz in vier Laeufen); der Fehler vor der Behebung
            # ist 441 statt 1,59 Hz
            close(f"Schwingung {name}, Maske {maske}: f₁ gleich Gegenrechnung", f, f0, 1e-6, "Hz")
            close(f"Schwingung {name}, Maske {maske}: f₁ nach Hand", f, hand, 2e-3, "Hz")
    # Die Huelle aendert in der Schwingung die Kopplung: Stand 64 liess P-Q fallen
    m = kette_modal("situation")
    aktiv = _aktiv(m, "situation")
    kp = m.kopplungen[-1]
    check("Schwingung Kette: die Kopplung P-Q fiel bis Stand 64 weg und bleibt seit Stand 65",
          not kopplung_bleibt(m, kp, aktive_knoten(m, aktiv)) and kopplung_bleibt(m, kp, wirksame_knoten(m, aktiv)))
    mk = rv.merkmal("maske_starrkoerper_last")
    for maske in MASKEN:
        m = kette_modal(maske)
        check(f"Merkmal maske_starrkoerper_last: Schwingung in der Situation (Maske {maske}) betroffen",
              mk is not None and bool(mk.betrifft(m)), f"{mk and mk.betrifft(m)}")
    m_ohne = kette_modal("geloescht")
    check("Merkmal maske_starrkoerper_last: Schwingung ohne Maske nicht betroffen",
          mk is not None and not mk.betrifft(m_ohne))
    m = kette_modal("situation")
    an = _analyse_mit_schwingung(m)
    im = (mk.im_ergebnis(m, an) or "") if mk else ""
    check("Merkmal maske_starrkoerper_last im Ergebnis: Schwingung 1 genannt", "Schwingung 1" in im, repr(im))
    an.schwingung = None
    im2 = (mk.im_ergebnis(m, an) or "") if mk else ""
    check("… ohne Schwingungsergebnis in der Analyse: nichts genannt", im2 == "", repr(im2))
    mk67 = rv.merkmal("maske_lager_verteilung")
    m = lager_modal("situation")
    an = _analyse_mit_schwingung(m)
    check("Merkmal maske_lager_verteilung: Schwingung am Lager des abgeschalteten Arms betroffen, im Ergebnis "
          "genannt", mk67 is not None and mk67.betrifft(m) and "Schwingung 1" in (mk67.im_ergebnis(m, an) or ""),
          f"{mk67 and mk67.betrifft(m)} {mk67 and mk67.im_ergebnis(m, an)!r}")
    check("… dieselbe Schwingung zaehlt nicht zum Merkmal des Stands 65",
          mk is not None and not mk.betrifft(m), f"{mk and mk.betrifft(m)}")


def _analyse_mit_schwingung(m):
    from statik3d.solver import Analysis
    from statik3d.schwingung import SchwingungsErgebnis
    an = Analysis(m)
    an.schwingung = SchwingungsErgebnis("Schwingung 1", "W1")
    return an


# --------------------------------------------------------------------------
# Merkmal Stand 67
# --------------------------------------------------------------------------
def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("maske_lager_verteilung")
    check("Merkmal maske_lager_verteilung: Stand 67, Fehlerkorrektur, fix/k10-maske, VERFAHRENSSTAND = 67",
          mk is not None and mk.wechsel[-1].stand == 67 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-maske" and rv.VERFAHRENSSTAND >= 67,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    mk65 = rv.merkmal("maske_starrkoerper_last")
    for maske in MASKEN:
        m, *_r = m8(maske)
        m2, *_r = v1(maske)
        check(f"betrifft M8 und V1 (Maske {maske}): ja; Merkmal des Stands 65 nein",
              mk.betrifft(m) and mk.betrifft(m2) and not mk65.betrifft(m) and not mk65.betrifft(m2),
              f"{mk.betrifft(m)} {mk.betrifft(m2)} {mk65.betrifft(m)} {mk65.betrifft(m2)}")
    m0, *_r = m8("geloescht")
    m_v0, *_r = v1("geloescht")
    m_nur_b, a, b, c, d = basis("situation")
    m_nur_b.load_node(b, Fz=-F, case="LF1")
    m_nur_b.kopplungen.append(_feder(m_nur_b.add_node(L, 1, 0), b))
    check("betrifft nicht: ohne Maske (M8, V1), Last nur am wirksamen Arm",
          not mk.betrifft(m0) and not mk.betrifft(m_v0) and not mk.betrifft(m_nur_b),
          f"{mk.betrifft(m0)} {mk.betrifft(m_v0)} {mk.betrifft(m_nur_b)}")
    m, *_r = m8("situation")
    an = _still(solver.solve_all, m, workers=1, design=False)
    an2 = _still(solver.solve_all, m_nur_b, workers=1, design=False)
    check("im Ergebnis: LF1 genannt, beim Modell ohne Last am Lager nichts",
          "LF1" in (mk.im_ergebnis(m, an) or "") and not mk.im_ergebnis(m_nur_b, an2),
          f"{mk.im_ergebnis(m, an)!r} / {mk.im_ergebnis(m_nur_b, an2)!r}")
    # Last am Lagerknoten ohne Kopplung: auch das aendert das Ergebnis (test_n1_last_am_lager)
    m3, a, b, c, d = basis("aus")
    m3.load_node(c, Fz=-2 * F, case="LF1")
    check("betrifft: Last unmittelbar am Lagerknoten des abgeschalteten Arms", mk.betrifft(m3))


def main():
    for t in (test_n1_m8, test_n1_last_am_lager, test_n1_schutz, test_n1_theorie3, test_n2_v1, test_n2_schutz,
              test_n2_theorie3, test_n2_warnung, test_schwingung, test_merkmal):
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
