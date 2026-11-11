"""
Schalenflaechen ohne gemeinsame Linie werden im Netz geteilt (Befund A19 der
Pruefagenten, Entscheidung des Anwenders vom 09.11.2026).

Beruehren sich Schalenflaechen, ohne eine Linie zu teilen, teilt der Vernetzer
sie an fremden Knoten und Linien - wie in RFEM „Knoten auf Linie“ und „Linie
in Fläche“ (mesher._teilplan, mesher.schalen_gemeinsam_vernetzen):

(a) Stoss in der Ebene: Flaeche F (2 x 2 m) hat rechts EINE Linie R1; daneben
    G1 und G2 (je 1 x 1 m) mit eigenen Linien bis zum Knoten (2 | 1). Vorher
    hingen zehn doppelte Knoten lose nebeneinander: u_x rechts 0,7421 mm.
    Jetzt 0,1429 mm. Erster Weg: sigma L / E = 10 N/mm² * 3 m / 210 000 N/mm²
    = 0,142857 mm. Zweiter Weg: dasselbe Modell mit von Hand geteilter Linie.
(b) Rippe auf ungeteilter Platte (2 x 2 m, t = 10 mm, allseits gelenkig,
    10 kN/m²; Rippe 0,2 m hoch laengs y = 1 m): vorher trug die Rippe nichts,
    w in Plattenmitte 33,089 mm (ohne Rippe 33,758 mm). Jetzt 0,512 mm
    (linear) bzw. 0,527 mm (quadratisch). Erster Weg: dieselbe Platte von Hand
    an y = 1 m in zwei Flaechen geteilt, gleiche Netzeinstellung: 0,517 bzw.
    0,525 mm. Zweiter Weg: das von Hand geteilte Modell fein und quadratisch:
    0,528 mm.

Dazu: Rippe kuerzer als die Platte (Zwangslinie mit freien Enden), Flaeche aus
drei Randlinien, lineare und quadratische Elemente, Vierecke und Dreiecke;
die Geometrie bleibt, jede Stelle steht im Protokoll; was sich nicht sauber
teilen laesst (schleifend, nur teilweise in der Flaeche, sich kreuzende
Zwangslinien), bleibt unverbunden und steht mit dem Grund im Protokoll; die
Abnahme warnt nur noch, wo das Netz nicht verbunden ist (Netze von frueher,
nicht teilbare Stellen).

Aufruf:  python -m tests.test_flaechen_teilen
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_flaechen_teilen_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import diagnose, mesher, solver                           # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<86} {detail}")
    return bool(ok)


T = 0.01
SIGMA, E_STAHL = 10e6, 210e9
U_SOLL = SIGMA * 3.0 / E_STAHL          # 0,142857 mm: Scheibe 3 m unter 10 N/mm²


def mm(x, stellen=4) -> str:
    return f"{x * 1e3:.{stellen}f}".replace(".", ",")


def modell(form=2, ordnung=1, dichte="mittel") -> Model:
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D", T))
    m.netz.form = form                    # 2 Vierecke, 0 Dreiecke
    m.netz.ordnung = ordnung
    m.netz.dichte = dichte
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    return m


def lager(m, name, linien, dofs):
    ls = m.add_line_support([], name=name)
    ls.linien = list(linien)
    for d in dofs:
        ls.behaviour[d] = DofBehaviour("rigid")


def stoss(geteilt, form=2, ordnung=1, versatz=0.0, dreieck=False) -> Model:
    """(a) F links, G1 und G2 rechts; ``geteilt``: F hat rechts die zwei Linien
    S1, S2 von G1, G2 statt der einen Linie R1. ``versatz`` rueckt den Knoten
    (2 | 1) von G1/G2 aus der Linie R1. ``dreieck``: F aus drei Randlinien."""
    m = modell(form, ordnung)
    k = [m.add_node(*p) for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0), (2 + versatz, 1, 0),
                                   (3, 0, 0), (3, 1, 0), (3, 2, 0)]]
    m.add_line("R0", [k[0], k[1]])
    m.add_line("S1", [k[1], k[4]]); m.add_line("S2", [k[4], k[2]])
    rechts = ["S1", "S2"]
    if not geteilt:
        m.add_line("R1", [k[1], k[2]])
        rechts = ["R1"]
    if dreieck:
        m.add_line("Hyp", [k[2], k[0]])
        m.add_flaeche("F", ["R0"] + rechts + ["Hyp"], material="S235", dicke="D")
    else:
        m.add_line("R2", [k[2], k[3]]); m.add_line("R3", [k[3], k[0]])
        m.add_flaeche("F", ["R0"] + rechts + ["R2", "R3"], material="S235", dicke="D")
    m.add_line("G0", [k[1], k[5]]); m.add_line("G1r", [k[5], k[6]]); m.add_line("Gm", [k[6], k[4]])
    m.add_line("H1r", [k[6], k[7]]); m.add_line("H2", [k[7], k[2]])
    m.add_flaeche("G1", ["G0", "G1r", "Gm", "S1"], material="S235", dicke="D")
    m.add_flaeche("G2", ["Gm", "H1r", "H2", "S2"], material="S235", dicke="D")
    if dreieck:
        lager(m, "Fest", ["Hyp"], (0, 1, 2))
        lager(m, "Quer", ["R0", "G0", "H2", "G1r", "H1r"], (2, 3, 4))
    else:
        lager(m, "Quer", ["R0", "R2", "R3", "G0", "H2", "G1r", "H1r"], (2, 3, 4))
        lager(m, "Links", ["R3"], (0,))
        m.support(k[0], [1])
    for x in ("G1r", "H1r"):
        m.add_linienlast(x, [SIGMA * T, 0, 0], art="linie", case="LF1")
    return m


def rippe(geteilt, form=2, ordnung=1, x0=0.0, x1=2.0, kreuz=False, dichte="mittel") -> Model:
    """(b) Platte 2 x 2 m, allseits gelenkig, 10 kN/m²; Rippe 0,2 m hoch auf
    y = 1 m von x0 bis x1. ``geteilt``: die Platte ist von Hand an y = 1 m in
    P1 und P2 geteilt (Linie der Rippe gemeinsam). ``kreuz``: eine zweite
    Rippe auf x = 1 m, die die erste ohne gemeinsamen Knoten kreuzt."""
    m = modell(form, ordnung, dichte)
    nr: dict = {}

    def kn(x, y, z=0.0):
        if (x, y, z) not in nr:
            nr[(x, y, z)] = m.add_node(x, y, z)
        return nr[(x, y, z)]

    def li(name, a, b):
        m.add_line(name, [a, b])
        return name
    A, B, C, D = kn(0, 0), kn(2, 0), kn(2, 2), kn(0, 2)
    li("R0", A, B); li("R2", C, D)
    a, b = kn(x0, 1), kn(x1, 1)
    li("M", a, b)
    if geteilt:
        l, r = kn(0, 1), kn(2, 1)
        li("L1", A, l); li("L2", l, D); li("Q1", B, r); li("Q2", r, C)
        mitte = ([li("Ma", l, a)] if x0 > 0 else []) + ["M"] + ([li("Mc", b, r)] if x1 < 2 else [])
        m.add_flaeche("P1", ["R0", "Q1"] + mitte[::-1] + ["L1"], material="S235", dicke="D")
        m.add_flaeche("P2", mitte + ["Q2", "R2", "L2"], material="S235", dicke="D")
        rand, platten = ["R0", "R2", "L1", "L2", "Q1", "Q2"], ["P1", "P2"]
    else:
        li("L", D, A); li("Q", B, C)
        m.add_flaeche("P", ["R0", "Q", "R2", "L"], material="S235", dicke="D")
        rand, platten = ["R0", "R2", "L", "Q"], ["P"]
    li("U", kn(x0, 1, -0.2), kn(x1, 1, -0.2)); li("V0", a, kn(x0, 1, -0.2)); li("V1", b, kn(x1, 1, -0.2))
    m.add_flaeche("Rippe", ["M", "V1", "U", "V0"], material="S235", dicke="D")
    if kreuz:
        li("N", kn(1, 0.5), kn(1, 1.5)); li("NU", kn(1, 0.5, -0.2), kn(1, 1.5, -0.2))
        li("N0", kn(1, 0.5), kn(1, 0.5, -0.2)); li("N1", kn(1, 1.5), kn(1, 1.5, -0.2))
        m.add_flaeche("Rippe2", ["N", "N1", "NU", "N0"], material="S235", dicke="D")
    lager(m, "Rand", rand, (0, 1, 2))
    for p in platten:
        m.add_geometrielast(p, 1e4, "flaeche", richtung=[0, 0, -1], case="LF1")
    return m


def vernetzen(m) -> list:
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log, workers=1)
    return log


def rechnen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        return solver.solve_all(m, workers=1, combinations=False).cases["LF1"]


def netzknoten(m, *flaechen) -> set:
    return {int(k) for f in flaechen for e in (m.flaechen[f].elemente or []) for k in m.elements[int(e)].nodes}


def typen(m, flaeche) -> set:
    return {m.elements[int(e)].typ for e in (m.flaechen[flaeche].elemente or [])}


def u_rechts(m, r) -> float:
    kn = [i for i in netzknoten(m, "G1", "G2") if abs(m.nodes[i, 0] - 3.0) < 1e-9]
    return float(r.u[kn, 0].mean())


def w_mitte(m, r) -> tuple:
    """Durchbiegung der Platte am Knoten bei (1 | 1) und groesste Durchbiegung."""
    pk = sorted(netzknoten(m, *[n for n in ("P", "P1", "P2") if n in m.flaechen]))
    d = np.linalg.norm(m.nodes[pk] - [1.0, 1.0, 0.0], axis=1)
    return float(-r.u[pk[int(np.argmin(d))], 2]), float(d.min()), float(-r.u[pk, 2].min())


def gemeinsam_mit_rippe(m, name="Rippe") -> tuple:
    """(Knoten der Rippe auf der Platte, wie viele davon im Netz der Platte)."""
    rk = [k for k in netzknoten(m, name) if abs(m.nodes[k, 2]) < 1e-9]
    pk = netzknoten(m, *[n for n in ("P", "P1", "P2") if n in m.flaechen])
    return len(rk), len([k for k in rk if k in pk])


def geometrie(m) -> tuple:
    return ({n: (list(ln.nodes), ln.typ) for n, ln in m.lines.items()},
            {n: (list(f.linien), [list(x) for x in (f.oeffnungen or [])]) for n, f in m.flaechen.items()})


# ---------------------------------------------------------------------------
def test_stoss_knoten_auf_linie():
    for form, ordnung, text in ((2, 1, "Vierecke, linear"), (2, 2, "Vierecke, quadratisch"),
                                (0, 1, "Dreiecke, linear"), (0, 2, "Dreiecke, quadratisch")):
        m = stoss(False, form, ordnung)
        vernetzen(m)
        u = u_rechts(m, rechnen(m))
        h = stoss(True, form, ordnung)
        vernetzen(h)
        uh = u_rechts(h, rechnen(h))
        dopp = mesher.doppelte_knoten(m)
        check(f"(a) Stoß, {text}: keine doppelten Knoten, u_x = σL/E = 0,1429 mm (0,1 %)",
              dopp == 0 and abs(u - U_SOLL) / U_SOLL < 1e-3,
              f"doppelte Knoten {dopp}, u_x = {mm(u)} mm, Soll {mm(U_SOLL)} mm")
        check(f"(a) Stoß, {text}: wie das Modell mit von Hand geteilter Linie (0,1 %)",
              abs(u - uh) / uh < 1e-3 and m.nn == h.nn and len(m.elements) == len(h.elements),
              f"{mm(u)} mm, von Hand geteilt {mm(uh)} mm; Knoten {m.nn}/{h.nn}, Elemente "
              f"{len(m.elements)}/{len(h.elements)}")


def test_stoss_protokoll_und_geometrie():
    m = stoss(False)
    vor = geometrie(m)
    log = vernetzen(m)
    # Knotennummer ab 0 wie Tabelle und Modellbaum (C13; Befund 12 vom
    # 11.11.2026 - bis dahin „Knoten 5“ fuer den Knoten 4)
    zeilen = [z for z in log if "Linie R1" in z and "am Knoten 4 geteilt" in z and "Knoten auf Linie" in z]
    check("(a) Protokoll nennt die Stelle (Linie R1, Knoten 4, Knoten auf Linie); Linien und Flächen "
          "des Modells unverändert",
          len(zeilen) == 1 and "G1" in zeilen[0] and "G2" in zeilen[0] and geometrie(m) == vor
          and not any("(Teil" in n for n in m.lines),
          zeilen[0][:110] if zeilen else "keine Zeile")
    check("(a) die geteilte Fläche F frei mit Dreiecken, die Nachbarn G1 und G2 bleiben abgebildete Vierecke",
          typen(m, "F") == {"shell3"} and typen(m, "G1") == {"shell4"} and typen(m, "G2") == {"shell4"}
          and int(m.lines["R1"].nodes[0]) in netzknoten(m, "F") and 4 in netzknoten(m, "F"),
          f"F {sorted(typen(m, 'F'))}, G1 {sorted(typen(m, 'G1'))}, Knoten 4 im Netz von F: "
          f"{4 in netzknoten(m, 'F')}")


def test_dreiecksflaeche():
    """Flaeche aus drei Randlinien, an deren einer Linie zwei Flaechen anschliessen."""
    aus = {}
    for geteilt in (False, True):
        m = stoss(geteilt, dreieck=True)
        vernetzen(m)
        aus[geteilt] = (u_rechts(m, rechnen(m)), mesher.doppelte_knoten(m), m)
    (u, dopp, m), (uh, _d, _h) = aus[False], aus[True]
    s1 = {k for k in netzknoten(m, "G1", "G2") if abs(m.nodes[k, 0] - 2.0) < 1e-9}
    check("Fläche aus drei Randlinien: alle Knoten der Nachbarn auf der Linie R1 sind Knoten von F",
          dopp == 0 and len(s1) > 3 and s1 <= netzknoten(m, "F"),
          f"{len(s1 & netzknoten(m, 'F'))} von {len(s1)}, doppelte Knoten {dopp}")
    check("Fläche aus drei Randlinien: u_x rechts wie mit von Hand geteilter Linie (2 %)",
          abs(u - uh) / uh < 0.02, f"{mm(u)} mm, von Hand geteilt {mm(uh)} mm")


def test_rippe_linie_in_flaeche():
    ref = rippe(True, 2, 2, dichte="fein")
    vernetzen(ref)
    w_ref = w_mitte(ref, rechnen(ref))[0]
    for form, ordnung, text, tol in ((2, 1, "Vierecke, linear", 0.015), (2, 2, "Vierecke, quadratisch", 0.01),
                                     (0, 2, "Dreiecke, quadratisch", 0.01)):
        m = rippe(False, form, ordnung)
        vernetzen(m)
        r = rechnen(m)
        w, d, _wmax = w_mitte(m, r)
        h = rippe(True, form, ordnung)
        vernetzen(h)
        wh = w_mitte(h, rechnen(h))[0]
        n, gem = gemeinsam_mit_rippe(m)
        dopp = mesher.doppelte_knoten(m)
        check(f"(b) Rippe, {text}: alle Knoten der Rippe auf der Platte sind Knoten der Platte",
              n > 3 and gem == n and dopp == 0, f"{gem} von {n}, doppelte Knoten {dopp}")
        check(f"(b) Rippe, {text}: w Mitte wie die von Hand geteilte Platte ({tol * 100:.1f} %)".replace(".", ","),
              d < 1e-9 and abs(w - wh) / wh < tol,
              f"{mm(w)} mm, von Hand geteilt {mm(wh)} mm, ΣRz = {r.reactions[:, 2].sum() / 1e3:.2f} kN "
              "(Soll 40,00)".replace(".", ","))
        if ordnung == 2:
            check(f"(b) Rippe, {text}: w Mitte wie das von Hand geteilte Modell fein, quadratisch (1 %)",
                  abs(w - w_ref) / w_ref < 0.01, f"{mm(w)} mm, Vergleich {mm(w_ref)} mm")


def test_rippe_protokoll_und_geometrie():
    m = rippe(False)
    vor = geometrie(m)
    log = vernetzen(m)
    zw = [z for z in log if "Linie M" in z and "Zwangslinie" in z and "Linie in Fläche" in z and "Fläche P" in z]
    kn = [z for z in log if "Knoten auf Linie" in z and ("Linie L " in z or "Linie Q " in z)]
    check("(b) Protokoll nennt die Zwangslinie M in der Fläche P und die zwei geteilten Randlinien L, Q; "
          "Geometrie unverändert",
          len(zw) == 1 and len(kn) == 2 and geometrie(m) == vor and not any("(Teil" in n for n in m.lines),
          zw[0][:100] if zw else "keine Zeile")


def test_rippe_kuerzer_als_die_platte():
    """Zwangslinie mit beiden Enden im Innern der Flaeche (kein Knoten auf einer Randlinie)."""
    m = rippe(False, x0=0.5, x1=1.5)
    log = vernetzen(m)
    r = rechnen(m)
    w, d, wmax = w_mitte(m, r)
    h = rippe(True, x0=0.5, x1=1.5)
    vernetzen(h)
    wh, _dh, whmax = w_mitte(h, rechnen(h))
    n, gem = gemeinsam_mit_rippe(m)
    check("Rippe kürzer als die Platte: Zwangslinie mit freien Enden, alle Knoten gemeinsam",
          n > 3 and gem == n and any("Zwangslinie" in z and "Linie M" in z for z in log)
          and not any("im Netz am Knoten" in z for z in log), f"{gem} von {n}")
    check("Rippe kürzer als die Platte: w Mitte und w max wie die von Hand geteilte Platte (2 %)",
          d < 1e-9 and abs(w - wh) / wh < 0.02 and abs(wmax - whmax) / whmax < 0.02,
          f"w Mitte {mm(w, 3)} / {mm(wh, 3)} mm, w max {mm(wmax, 3)} / {mm(whmax, 3)} mm")


def test_nicht_teilbar_bleibt_unverbunden():
    # schleifend: der Knoten liegt 0,5 mm neben der Linie
    m = stoss(False, versatz=0.0005)
    log = vernetzen(m)
    # Knoten 4 ab 0 (Befund 12, 11.11.2026; bis dahin „Knoten 5“)
    z = [x for x in log if "schleifend" in x and "Knoten 4 (" in x and "Linie R1" in x and "nicht verbunden" in x]
    ab = diagnose._abnahme_schalen_ohne_linie(m)
    check("schleifend (Knoten 0,5 mm neben der Linie): nicht verbunden, Grund im Protokoll, Abnahme warnt",
          len(z) == 1 and "0,500 mm" in z[0] and 4 not in netzknoten(m, "F") and len(ab) >= 1,
          (z[0][:120] if z else "keine Zeile") + f"; Abnahme {len(ab)}")
    # nur teilweise: die Rippe ragt ueber den Plattenrand hinaus
    m = rippe(False, x0=0.5, x1=2.5)
    log = vernetzen(m)
    z = [x for x in log if "Linie M" in x and "teilweise" in x and "nicht verbunden" in x]
    n, gem = gemeinsam_mit_rippe(m)
    ab = diagnose._abnahme_schalen_ohne_linie(m)
    check("Linie nur teilweise in der Fläche: nicht verbunden, Grund im Protokoll, Abnahme warnt",
          len(z) == 1 and gem == 0 and len(ab) >= 1,
          (z[0][:120] if z else "keine Zeile") + f"; gemeinsame Knoten {gem} von {n}; Abnahme {len(ab)}")
    # zwei Rippen kreuzen sich auf der Platte ohne gemeinsamen Knoten
    m = rippe(False, x0=0.5, x1=1.5, kreuz=True)
    log = vernetzen(m)
    z = [x for x in log if "kreuzt die Zwangslinie" in x and "nicht verbunden" in x]
    n1, g1 = gemeinsam_mit_rippe(m, "Rippe")
    n2, g2 = gemeinsam_mit_rippe(m, "Rippe2")
    ab = diagnose._abnahme_schalen_ohne_linie(m)
    check("zwei sich kreuzende Linien ohne gemeinsamen Knoten: nur die erste wird Zwangslinie, die zweite "
          "bleibt mit Grund unverbunden",
          len(z) == 1 and sorted((g1 == n1, g2 == n2)) == [False, True] and min(g1, g2) == 0 and len(ab) >= 1,
          (z[0][:110] if z else "keine Zeile") + f"; Rippe {g1}/{n1}, Rippe2 {g2}/{n2}; Abnahme {len(ab)}")


def test_abnahme_sieht_auf_das_netz():
    for name, bau in (("(a) Stoß", lambda: stoss(False)), ("(b) Rippe", lambda: rippe(False))):
        m = bau()
        ohne = len(diagnose._abnahme_schalen_ohne_linie(m))
        vernetzen(m)
        neu = len(diagnose._abnahme_schalen_ohne_linie(m))
        # ein Netz von frueher: jede Flaeche fuer sich vernetzt
        alt = bau()
        for f in alt.flaechen.values():
            mesher.mesh_flaeche(alt, f, [])
        ab = diagnose._abnahme_schalen_ohne_linie(alt)
        check(f"Abnahme {name}: neu vernetzt keine Warnung; Netz von früher (jede Fläche für sich) warnt "
              "und verweist auf das Neuvernetzen",
              neu == 0 and ohne == 0 and len(ab) >= 1 and all("Neu vernetzen" in b.text for b in ab),
              f"ohne Netz {ohne}, neu vernetzt {neu}, Netz von früher {len(ab)}")


def test_weg_der_oberflaeche():
    """Die Oberflaeche fragt erst gemeinsame_schalen und vernetzt dann nur die
    Gruppe (gui/main.py, Flaechen vernetzen) - die Gruppe muss die Flaechen an
    den Teilstellen enthalten und fuer sich dasselbe ergeben."""
    m = rippe(False)
    fl = list(m.flaechen.values())
    namen = {g.name for g in mesher.gemeinsame_schalen(m, fl)}
    gruppe = [g for g in fl if g.name in namen]
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        gem = mesher.schalen_gemeinsam_vernetzen(m, gruppe, None, log, {})
    n, g = gemeinsam_mit_rippe(m)
    check("Weg der Oberfläche: Platte und Rippe gehören zur gemeinsamen Gruppe und teilen ihre Knoten",
          namen == {"P", "Rippe"} and set(gem) == namen and n > 3 and g == n, f"Gruppe {sorted(namen)}, {g} von {n}")


def test_teilstellen_fuer_die_verfahrenstabelle():
    fn = getattr(mesher, "flaechen_teilstellen", None)
    aus = {n: (fn(b) if fn else None) for n, b in (
        ("stoss", stoss(False)), ("stoss_geteilt", stoss(True)),
        ("rippe", rippe(False)), ("rippe_geteilt", rippe(True)))}
    check("mesher.flaechen_teilstellen nennt die im Netz geteilten Flächen (F bzw. P), von Hand geteilt keine",
          aus == {"stoss": ["F"], "stoss_geteilt": [], "rippe": ["P"], "rippe_geteilt": []}, str(aus))


def main():
    for t in (test_stoss_knoten_auf_linie,
              test_stoss_protokoll_und_geometrie,
              test_dreiecksflaeche,
              test_rippe_linie_in_flaeche,
              test_rippe_protokoll_und_geometrie,
              test_rippe_kuerzer_als_die_platte,
              test_nicht_teilbar_bleibt_unverbunden,
              test_abnahme_sieht_auf_das_netz,
              test_weg_der_oberflaeche,
              test_teilstellen_fuer_die_verfahrenstabelle):
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
