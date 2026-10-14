"""Stabkraft mit Anfangsdehnung und Zugstaebe in der Konvergenz (13.10.2026).

Temperatur, Vorspannung als eingepraegte Dehnung und die Verriegelung einer
Sollkraft zaehlen in jeder Normalkraft eines Stabs mit - im Ergebnis tat das
Programm das schon, in der geometrischen Steifigkeit (Theorie II. Ordnung,
alpha_cr, Knicken), in der Ausfall-Iteration der Zugstaebe und in Theorie III.
Ordnung (Stab und Seil) bis zum 13.10.2026 nicht:

* Befund 1: ein Zugband mit 70 kN Anfangsdehnung traegt im Ergebnis +6,50 kN,
  die geometrische Steifigkeit rechnete mit -63,50 kN (alpha_cr 1,688).
* Befund 2: ein Zugstab „nur Zug“ mit 500 kN Vorspannung als dT fiel aus und
  trug 0 statt 400 kN.
* Befund 3: Theorie III. Ordnung liess die Vorspannung eines Seils still weg.

Geprueft mit geschlossenen Loesungen:

* Zugband (Kragstuetze mit vorgespanntem Fachwerkstab): K_G des Zugbands ist
  die Formel mit N aus dem Ergebnis; alpha_cr gleich dem der gleichwertigen
  Rechnung, in der statt der Anfangsdehnung der Anker um F L/(E A) verschoben
  wird (Zwangsverformung, ohne Anfangsdehnung).
* Knickstab mit Temperatur-Zwang: alpha_cr = pi^2 E I / L^2 / (E A alpha dT).
* Zugstab „nur Zug“ mit dT-Vorspannung gegen ein Klemmteil: aktiv mit
  F k_K/(k_A + k_K) = 400 kN; unter einer Drucklast faellt er aus, und seine
  Temperaturlast geht mit (u = P/k_K).
* Seil aus zwei Seilelementen, vorgespannt, Querlast in der Mitte, nach
  Theorie III. Ordnung: 2 T w/c = F mit T = E A (c - L0')/L0',
  L0' = L/(1 + N0/(E A)); ebenso mit dT statt Vorspannung und als
  Fachwerkstab (N = E A (c - L)/L + N0).
* Zugstaebe in der Konvergenz: X-Verband, eine Diagonale faellt aus, mit Kontakt
  und mit Plastizitaet; N_D = sqrt(2) H. Ein Zugstab mit Druck nach Abschluss
  (Theorie II. Ordnung iteriert den Ausfall nicht) steht mit Namen und Kraft in
  Protokoll, Zusammenfassung und Konvergenzstand.

Aufruf:  python -m tests.test_stabkraft_anfangsdehnung
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, plastizitaet as pl, solver, theorie2   # noqa: E402
from statik3d.elements import beam3d as bm                                     # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section                 # noqa: E402

RESULTS = []
E = 210e9
NU = 0.3
ALPHA = 1.2e-5


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


def _N(res, e):
    """Normalkraft (Zug positiv) am Stabende - wie Tabelle und Nachweis sie lesen."""
    return float(res.beam_forces[int(e)]["N"][1])


def _u_voll(m, res):
    u = np.zeros(m.ndof)
    u[:m.nn * 6] = np.asarray(res.u, float).ravel()[:m.nn * 6]
    return u


def _n_anfang(m, faktoren):
    """Die Normalkraefte der Anfangsdehnung - leer, wenn es die Schnittstelle
    (noch) nicht gibt (Stand vor dem 13.10.2026: die Pruefung zeigt dann die
    alten Zahlen statt eines Abbruchs)."""
    f = getattr(solver, "anfangsnormalkraefte", None)
    return f(m, faktoren) if f is not None else {}


def _kg(m, u, aktiv=None, n=None):
    try:
        return asm.geometric_stiffness(m, u, aktiv, n_anfang=n)
    except TypeError:
        return asm.geometric_stiffness(m, u, aktiv)


# --------------------------------------------------------------------------
# Befund 1: geometrische Steifigkeit
# --------------------------------------------------------------------------
def _zugband(vorspannung=True, zwang=False, F0=70e3, teile=16):
    """Kragstuetze (Vollquadrat 0,2 m, schubstarr, 3 m,
    ``teile`` Elemente) mit einem Zugband (Rundstahl 30 mm, Fachwerkstab) vom
    Boden in 2 m Abstand zum Kopf. ``vorspannung``: F0 als Anfangsdehnung;
    ``zwang``: stattdessen der Anker um F0 L/(E A) vom Kopf weg verschoben."""
    m = Model("Zugband")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=355e6, alpha=ALPHA))
    q = Section.rectangle("Q", 0.2, 0.2)
    q.Asy = q.Asz = 0.0
    m.add_section(q)
    m.add_section(Section.circle("D", 0.03))
    kn = [m.add_node(0.0, 0.0, 3.0 * k / teile) for k in range(teile + 1)]
    c = m.add_node(2.0, 0.0, 0.0)
    m.fix(kn[0], "all")
    m.fix(c, "all")
    for k in range(teile):
        m.add_element("beam", [kn[k], kn[k + 1]], "S355", "Q")
    band = m.add_element("truss", [c, kn[-1]], "S355", "D")
    m.add_member("Band", [band])
    m.add_load_case("V").gravity = [0, 0, 0]
    if vorspannung:
        m.add_vorspannung("Band", F0, case="V")
    if zwang:
        A = m.sections["D"].A
        Lt = math.sqrt(13.0)
        s = F0 * Lt / (E * A)
        e = np.array([2.0, 0.0, -3.0]) / Lt          # vom Kopf zum Anker
        m.add_zwangsverformung(c, [0, 1, 2], list(s * e), case="V")
    m.design.imperfektionen = False
    return m, band, kn[-1]


def test_zugband_kg():
    print("\n--- Befund 1: Zugband mit Anfangsdehnung – N in K_G und alpha_cr ---")
    m, band, kopf = _zugband()
    r = solver.solve_static(m, case="V")
    N_erg = _N(r, band)
    u = _u_voll(m, r)
    n = _n_anfang(m, {"V": 1.0})
    aktiv = np.zeros(len(m.elements), bool)
    aktiv[band] = True
    Kg = _kg(m, u, aktiv, n)
    e = m.elements[band]
    kl, T3, T, L = asm.beam_local(m, e)
    d = asm.element_dofs(e, m)[:12]
    blk = Kg[d][:, d].toarray()
    # der Fachwerkstab hat die Saitenform N/L (seit dem 14.10.2026; bis dahin
    # die Balkenform 6/5 N/L mit Drehanteilen, tests/test_stab_nachzug.py)
    einheit = T.T @ bm.kg_local_saite(1.0, L) @ T
    N_kg = float(np.sum(blk * einheit) / np.sum(einheit * einheit))
    print(f"   N im Ergebnis {N_erg / 1e3:.4f} kN, N in K_G {N_kg / 1e3:.4f} kN")
    nahe("Zugband: N in der geometrischen Steifigkeit = N im Ergebnis", N_kg, N_erg, 1e-9, "N")
    rest = float(np.abs(blk - N_erg * einheit).max()) / float(np.abs(N_erg * einheit).max())
    check("Zugband: K_G des Zugbands ist die Saitenform mit N aus dem Ergebnis", rest <= 1e-9, f"{rest:.2e}")
    _r2, i2 = theorie2.solve_theorie2(m, {"V": 1.0}, "V", imperfektionen=False)
    mz, bz, _k = _zugband(vorspannung=False, zwang=True)
    rz = solver.solve_static(mz, case="V")
    nahe("gleichwertige Rechnung (Anker verschoben): dasselbe N im Zugband", _N(rz, bz), N_erg, 1e-9, "N")
    _r2z, i2z = theorie2.solve_theorie2(mz, {"V": 1.0}, "V", imperfektionen=False)
    nahe("alpha_cr mit Anfangsdehnung = alpha_cr der gleichwertigen Rechnung", i2.alpha_cr, i2z.alpha_cr,
         1e-8)
    # Gegen Hand: die Zugkraft zeigt immer auf den Anker in Hoehe des
    # Stuetzenfusses, quer zur Ebene wirkt das Zugband als Feder N/L am Kopf;
    # mit P/k = L wird die Kragstuetze zur beidseits gelenkigen:
    # alpha_cr = pi^2 E I/L^2 / N_Stuetze, N_Stuetze = N 3/sqrt(13). Das gilt
    # mit der Saitenform N/L des Fachwerkstabs, die asm.geometric_stiffness
    # seit dem 14.10.2026 ansetzt - bis dahin stand hier die Saite von Hand
    # neben der Balkenform des Programms (alpha_cr des Programms 4 126)
    I = m.sections["Q"].Iy
    N_c = abs(N_erg) * 3.0 / math.sqrt(13.0)
    nahe("alpha_cr des Programms gegen Hand (Zugband als Saite N/L): pi^2 E I/L^2 / N_Stuetze",
         i2.alpha_cr, math.pi ** 2 * E * I / 9.0 / N_c, 1e-5)


def _knickstab(dT=20.0, teile=16):
    """Beidseits gelenkiger Stab 4 m (Vollquadrat 0,1 m, schubstarr), in x an
    beiden Enden gehalten, Erwaermung dT: N = -E A alpha dT aus Zwang."""
    m = Model("Knickstab")
    m.add_material(Material("S", E=E, nu=NU, rho=0.0, fy=355e6, alpha=ALPHA))
    q = Section.rectangle("Q", 0.1, 0.1)
    q.Asy = q.Asz = 0.0
    m.add_section(q)
    Lg = 4.0
    kn = [m.add_node(Lg * k / teile, 0.0, 0.0) for k in range(teile + 1)]
    m.fix(kn[0], [0, 1, 2, 3])
    m.fix(kn[-1], [0, 1, 2])
    m.add_load_case("T").gravity = [0, 0, 0]
    for k in range(teile):
        i = m.add_element("beam", [kn[k], kn[k + 1]], "S", "Q")
        m.load_temp(i, dT, case="T")
    m.design.imperfektionen = False
    return m, Lg


def test_knickstab_temperatur():
    print("\n--- Befund 1: Knickstab mit Temperatur-Zwang – alpha_cr gegen Euler ---")
    dT = 20.0
    m, Lg = _knickstab(dT)
    sec = m.sections["Q"]
    N = E * sec.A * ALPHA * dT
    euler = math.pi ** 2 * E * sec.Iy / Lg ** 2 / N
    r = solver.solve_static(m, case="T")
    nahe("Knickstab: N im Ergebnis = -E A alpha dT", _N(r, 3), -N, 1e-9, "N")
    _r2, i2 = theorie2.solve_theorie2(m, {"T": 1.0}, "T", imperfektionen=False)
    print(f"   alpha_cr {i2.alpha_cr}, Euler {euler:.6f}, Hinweise {i2.hinweise}")
    nahe("Theorie II: alpha_cr = pi^2 E I/L^2 / (E A alpha dT)", i2.alpha_cr if math.isfinite(i2.alpha_cr)
         else 1e99, euler, 1e-4)
    try:
        rb = solver.solve_buckling(m, nmodes=2, case="T")
        lam = float(rb.buckling_factors[0])
    except RuntimeError as ex:
        print(f"   Knicken: {ex}")
        lam = 1e99
    nahe("Knicken (solve_buckling): erster Faktor = Euler", lam, euler, 1e-4)


# --------------------------------------------------------------------------
# Befund 2: Ausfall-Iteration
# --------------------------------------------------------------------------
A_A, A_K = 1e-3, 4e-3
K_A, K_K = E * A_A, E * A_K           # L = 1 m


def _anker(nur="zug", typ="truss", wie="dT", F0=500e3, P=0.0, druckstab=False):
    """Boden G, Kopf H (1 m); Anker G-H (A 1e-3) und Klemmteil G'-H (A 4e-3).
    ``wie``: "dT" (Abkuehlung wie der RFEM-Import), "vorspannung"
    (Anfangsdehnung) oder "sollkraft". ``druckstab``: der Anker ist ein
    Druckstab „nur Druck“ und wird erwaermt (Druck F0)."""
    m = Model("Anker")
    m.add_material(Material("Stahl", E=E, nu=NU, rho=7850, alpha=1e-5))
    m.add_section(Section.circle("A", float(np.sqrt(4 * A_A / np.pi))))
    m.add_section(Section.circle("K", float(np.sqrt(4 * A_K / np.pi))))
    g1, g2, h = m.add_node(0, 0, 0), m.add_node(0, 0, 0), m.add_node(0, 0, 1)
    m.fix(g1, "all")
    m.fix(g2, "all")
    m.fix(h, [0, 1, 3, 4, 5])
    a = m.add_element(typ, [g1, h], "Stahl", "A")
    k = m.add_element("truss", [g2, h], "Stahl", "K")
    if nur and typ != "seil":
        m.elements[a].nur = nur
    m.add_member("A1", [a])
    m.add_member("K1", [k])
    lc = m.add_load_case("V")
    lc.gravity = [0, 0, 0]
    if druckstab:
        m.load_temp(a, F0 / (E * A_A * 1e-5), case="V")
    elif wie == "dT":
        m.load_temp(a, -F0 / (E * A_A * 1e-5), case="V")
    elif wie == "vorspannung":
        m.add_vorspannung("A1", F0, case="V")
    else:
        m.add_vorspannung("A1", F0, case="V", sollkraft=True)
    if P:
        lc.nodal_loads.append(NodalLoad(h, [0, 0, P, 0, 0, 0]))
    return m, a, k, h


def test_ausfall_anfangsdehnung():
    print("\n--- Befund 2: Zugstab „nur Zug“ mit Vorspannung bleibt aktiv ---")
    soll = 500e3 * K_K / (K_A + K_K)
    for wie, typ, nur in (("dT", "truss", "zug"), ("vorspannung", "truss", "zug"),
                          ("dT", "seil", ""), ("vorspannung", "seil", ""),
                          ("sollkraft", "truss", "zug")):
        m, a, k, h = _anker(nur=nur, typ=typ, wie=wie)
        r = solver.solve_static(m, case="V")
        art = f"{'Seil' if typ == 'seil' else 'nur Zug'}, {wie}"
        check(f"{art}: der Anker bleibt aktiv", not (r.info.get("ausfall") or []),
              f"ausgefallen {r.info.get('ausfall')}")
        ziel = 500e3 if wie == "sollkraft" else soll
        nahe(f"{art}: N = " + ("F_soll" if wie == "sollkraft" else "F k_K/(k_A + k_K) = 400 kN"),
             _N(r, a), ziel, 1e-9, "N")
    m, a, k, h = _anker(nur="druck", druckstab=True)
    r = solver.solve_static(m, case="V")
    check("Druckstab „nur Druck“, erwaermt: bleibt aktiv", not (r.info.get("ausfall") or []),
          f"ausgefallen {r.info.get('ausfall')}")
    nahe("Druckstab „nur Druck“, erwaermt: N = -400 kN", _N(r, a), -soll, 1e-9, "N")


def test_ausfall_unter_last():
    print("\n--- Befund 2: Zugstab „nur Zug“ geht unter Last in Druck und faellt aus ---")
    P = -2.5e6
    for wie in ("dT", "vorspannung"):
        m, a, k, h = _anker(wie=wie, P=P)
        r = solver.solve_static(m, case="V")
        check(f"{wie}: der Anker faellt aus", list(r.info.get("ausfall") or []) == [a],
              f"ausgefallen {r.info.get('ausfall')}")
        nahe(f"{wie}: der ausgefallene Anker traegt nichts", abs(_N(r, a)) + 1.0, 1.0, 1e-9, "N")
        nahe(f"{wie}: das Klemmteil traegt P", _N(r, k), P, 1e-9, "N")
        nahe(f"{wie}: u_Kopf = P/k_K – die Vorspannung des Ankers ist mit ihm weg", r.u[h, 2], P / K_K,
             1e-9, "m")


# --------------------------------------------------------------------------
# Befund 3: Theorie III. Ordnung mit Seilvorspannung
# --------------------------------------------------------------------------
def _saite(typ="seil", wie="vorspannung", N0=50e3, F=10e3, L=2.0, D=0.02):
    """Zwei Elemente A-B-C (je L), A und C fest, B frei in x und z; Querlast F
    in B nach unten, ohne Eigengewicht."""
    m = Model("Saite")
    m.add_material(Material("S", E=E, nu=NU, rho=0.0, alpha=ALPHA))
    m.add_section(Section.circle("D", D))
    a, b, c = m.add_node(0, 0, 0), m.add_node(L, 0, 0), m.add_node(2 * L, 0, 0)
    m.fix(a, "all")
    m.fix(c, "all")
    m.fix(b, [1, 3, 4, 5])
    e1 = m.add_element(typ, [a, b], "S", "D")
    e2 = m.add_element(typ, [b, c], "S", "D")
    m.add_member("Saite", [e1, e2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    if N0 and wie == "vorspannung":
        m.add_vorspannung("Saite", N0, case="LF1")
    elif N0:
        for i in (e1, e2):
            m.load_temp(i, -N0 / (E * m.sections["D"].A * ALPHA), case="LF1")
    if F:
        lc.nodal_loads.append(NodalLoad(b, [0, 0, -F, 0, 0, 0]))
    m.design.imperfektionen = False
    return m, e1, b


def _saite_geschlossen(EA, L, N0, F, seil=True):
    """(w, N): 2 N w/c = F, Seil N = EA (c - L0')/L0' mit L0' = L/(1 + N0/EA),
    Fachwerkstab N = EA (c - L)/L + N0."""
    from scipy.optimize import brentq

    def N_von(w):
        c = math.hypot(L, w)
        if seil:
            L0 = L / (1.0 + N0 / EA)
            return EA * (c - L0) / L0
        return EA * (c - L) / L + N0

    w = brentq(lambda w_: 2.0 * N_von(w_) * w_ / math.hypot(L, w_) - F, 1e-12, 0.5 * L, xtol=1e-16,
               rtol=1e-15, maxiter=500)
    return w, N_von(w)


def test_seil_theorie3():
    print("\n--- Befund 3: Theorie III. Ordnung mit Vorspannung (Seil und Fachwerkstab) ---")
    from statik3d.theorie3 import solve_theorie3
    N0, F = 50e3, 10e3
    for typ, wie in (("seil", "vorspannung"), ("seil", "dT"), ("truss", "vorspannung")):
        m, e1, b = _saite(typ, wie, N0, F)
        EA = E * m.sections["D"].A
        w, N = _saite_geschlossen(EA, 2.0, N0, F, seil=typ == "seil")
        res, info = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=4, tol=1e-12, imperfektionen=False)
        art = f"{'Seil' if typ == 'seil' else 'Fachwerkstab'} mit {wie}"
        print(f"   {art}: w {-res.u[b, 2] * 1e3:.6f} mm (geschlossen {w * 1e3:.6f}), "
              f"N {res.beam_end[e1][6] / 1e3:.6f} kN (geschlossen {N / 1e3:.6f}), Hinweise {info.hinweise}")
        check(f"{art}: Theorie III. Ordnung gerechnet", info.gerechnet, info.fehler)
        nahe(f"{art}: Durchhang in der Mitte", -res.u[b, 2], w, 1e-7, "m")
        nahe(f"{art}: Normalkraft", res.beam_end[e1][6], N, 1e-7, "N")
    m, e1, b = _saite("seil", "vorspannung", N0, 0.0)
    res, info = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=1, imperfektionen=False)
    nahe("Seil ohne Last: die Seilkraft ist die Vorspannung", res.beam_end[e1][6], N0, 1e-12, "N")


# --------------------------------------------------------------------------
# Zugstaebe in der Konvergenzbedingung
# --------------------------------------------------------------------------
H_X, P_X = 50e3, 100e3


def _x_verband(kontakt=False, plast=False, N0=0.0, nur="zug"):
    """X-Verband 1 x 1 m in der x-z-Ebene: Stuetzen LC (BL-TL), RC (BR-TR),
    Riegel TC (TL-TR), Diagonalen D1 (TL-BR) und D2 (TR-BL), alle Fachwerk-
    staebe, die Diagonalen „nur Zug“. H in TL nach +x, P in TL und TR nach
    unten. ``kontakt``: die Fusspunkte stehen auf einseitigen Lagern;
    ``plast``: auf einem Wuerfel (hex8, 1 m, Plastizitaet an) statt auf
    Lagern. ``N0``: Vorspannung der Diagonalen als dT."""
    m = Model("X-Verband")
    m.add_material(Material("S355", E=E, nu=NU, rho=0.0, fy=355e6, alpha=1e-5))
    m.add_section(Section.circle("S", 0.05))
    m.add_section(Section.circle("D", 0.02))
    if plast:
        w = [m.add_node(x, y, z) for z in (-1.0, 0.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
        m.add_element("hex8", w, "S355", "")
        for n in w[:4]:
            m.fix(n, [0, 1, 2])
        BL, BR = w[4], w[5]
        for n in w[4:]:
            m.fix(n, [3, 4, 5])
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=3, iterationen=30,
                                         toleranz=1e-8)
    else:
        BL, BR = m.add_node(0, 0, 0), m.add_node(1, 0, 0)
        for n in (BL, BR):
            m.fix(n, [0, 1, 3, 4, 5] if kontakt else "all")
            if kontakt:
                m.add_contact_support(n, direction=(0, 0, 1))
    TL, TR = m.add_node(0, 0, 1), m.add_node(1, 0, 1)
    for n in (TL, TR):
        m.fix(n, [1, 3, 4, 5])
    st = {}
    for name, (p, q_, s) in {"LC": (BL, TL, "S"), "RC": (BR, TR, "S"), "TC": (TL, TR, "S"),
                             "D1": (TL, BR, "D"), "D2": (TR, BL, "D")}.items():
        i = m.add_element("truss", [p, q_], "S355", s)
        if name.startswith("D") and nur:
            m.elements[i].nur = nur
        m.add_member(name, [i])
        st[name] = i
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(TL, [H_X, 0, -P_X, 0, 0, 0]))
    lc.nodal_loads.append(NodalLoad(TR, [0, 0, -P_X, 0, 0, 0]))
    if N0:
        A = m.sections["D"].A
        for name in ("D1", "D2"):
            m.load_temp(st[name], -N0 / (E * A * 1e-5), case="LF1")
    m.design.imperfektionen = False
    return m, st


def _x_pruefen(art, r, st):
    check(f"{art}: die gedrueckte Diagonale D1 faellt aus", list(r.info.get("ausfall") or []) == [st["D1"]],
          f"ausgefallen {r.info.get('ausfall')}")
    nahe(f"{art}: N_D2 = sqrt(2) H", _N(r, st["D2"]), math.sqrt(2.0) * H_X, 1e-6, "N")
    nahe(f"{art}: N_TC = -H", _N(r, st["TC"]), -H_X, 1e-6, "N")
    nahe(f"{art}: N_RC = -P - H", _N(r, st["RC"]), -P_X - H_X, 1e-6, "N")
    zs = r.info.get("stabstatus") or {}
    check(f"{art}: der Stabstatus steht im Ergebnis und ist konvergiert",
          zs.get("konvergiert") is True and zs.get("druck") == [] and zs.get("ausgefallen") == ["D1"],
          f"{zs}")
    check(f"{art}: Konvergenzstand konvergiert", solver.konvergenz_zustand(r.info) == solver.KONVERGIERT,
          solver.konvergenz_zustand(r.info))


def test_stabstatus_kontakt():
    print("\n--- Zugstaebe in der Konvergenz: X-Verband auf einseitigen Lagern (Kontakt) ---")
    m, st = _x_verband(kontakt=True)
    r = solver.solve_static(m, case="LF1")
    check("Kontakt: die Fusspunkte stehen (Kontakt konvergiert)", solver.kontakt_konvergiert(r.info))
    _x_pruefen("Kontakt", r, st)


def test_stabstatus_plastizitaet():
    print("\n--- Zugstaebe in der Konvergenz: X-Verband auf einem Wuerfel mit Plastizitaet ---")
    m, st = _x_verband(plast=True, N0=20e3)
    r = solver.solve_static(m, case="LF1")
    log = (r.info.get("plastizitaet") or {}).get("log") or []
    for z in log:
        print("   ", z)
    _x_pruefen("Plastizitaet", r, st)
    check("Plastizitaet: eine Laststufe mit geaendertem Stabstatus ist erst nach einem weiteren "
          "Newton-Schritt konvergiert", any("Zugstäbe" in z and "geändert" in z for z in log),
          "keine Zeile im Protokoll")


def test_druck_nach_abschluss_gemeldet():
    print("\n--- Ein Zugstab mit Druck nach Abschluss wird gemeldet (Theorie II. Ordnung) ---")
    m, st = _x_verband()
    m.case("LF1").theorie = "II"
    an = solver.solve_all(m, combinations=False)
    r = an.cases["LF1"]
    N1 = _N(r, st["D1"])
    print(f"   Theorie {r.info.get('theorie')}: N_D1 {N1 / 1e3:.3f} kN, stabstatus {r.info.get('stabstatus')}")
    check("Theorie II: D1 traegt Druck (der Ausfall wird dort nicht iteriert)", N1 < -1e3, f"{N1:.1f} N")
    zs = r.info.get("stabstatus") or {}
    druck = zs.get("druck") or []
    check("Theorie II: der Zugstab mit Druck steht mit Namen und Kraft im Ergebnis",
          len(druck) == 1 and druck[0].get("stab") == "D1" and abs(druck[0].get("N", 0.0) - N1) < 1e-6 * abs(N1),
          f"{druck}")
    z = solver.konvergenz_zustand(r.info)
    check("Theorie II: Konvergenzstand nennt den Zugstab mit Druck", z.startswith("NICHT konvergiert")
          and "D1" in z, z)
    s = r.summary()
    check("Theorie II: Zusammenfassung des Ergebnisses nennt ihn mit Kraft", "D1" in s and "kN" in s
          and "Druck" in s, [x for x in s.splitlines() if "D1" in x])
    sa = an.summary()
    check("Theorie II: Zusammenfassung der Berechnung nennt ihn", "D1" in sa and "Druck" in sa,
          [x for x in sa.splitlines() if "D1" in x])


def main():
    for t in (test_zugband_kg, test_knickstab_temperatur, test_ausfall_anfangsdehnung,
              test_ausfall_unter_last, test_seil_theorie3, test_stabstatus_kontakt,
              test_stabstatus_plastizitaet, test_druck_nach_abschluss_gemeldet):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
