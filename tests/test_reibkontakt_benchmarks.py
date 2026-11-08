"""Benchmarks fuer den Kontakt mit und ohne Reibung (Vorgabe des Anwenders, 08.11.2026).

Vier Faelle mit bekannter Loesung; die Erwartung steht vor der Rechnung fest und
kommt aus der Analytik:

B1  Hertz, mu = 0: Zylinder R 100 mm auf Ebene, ebene Dehnung, Stahl auf Stahl.
    a = sqrt(4 P' R / (pi E*)), p0 = 2 P' / (pi a), E* = E / (2 (1 - nu^2)).
    Grenzen: p0 2 %, Kontaktrand a innerhalb eines Elements, Gleichgewicht 0,1 %.
    Modell aus der Sicherung vom 01.10.2026 (pruefmatrix_zusatz.py, Abschnitt H1),
    hier eigenstaendig; Netz a/8. Die 0,34 % der Sicherung waren mit der „Kur“
    gemessen (Fangbereiche contact.AUFLIEGEND/DECKUNGSGLEICH auf null); mit dem
    Fangbereich 1e-3 lag p0 rund 25 % zu tief, seit 08.11.2026 (1e-6) nicht mehr.
    Die Ursachenprobe rechnet einmal mit AUFLIEGEND = 0.
B2  Klotz auf schiefer Ebene, mu = 1: Stahlplatte 0,4 x 0,4 x 0,02 m (hex8 4 x 4 x 1)
    unter Eigengewicht auf einer starren, festen Platte, das ganze Modell um alpha
    um die y-Achse gedreht. Flach, damit das Kippmoment des Hangabtriebs die
    Pressung kaum ungleich macht (Ausmitte e = h/2 tan alpha = 8 mm, b/6 = 67 mm):
    nur dann gilt die Analytik des starren Klotzes auch an jedem Knoten. Bei 40 Grad
    (tan 40 = 0,84 < 1) haftet jeder Kontaktknoten, die Reibkraft ist der
    Hangabtrieb G sin(alpha), die Normalkraft G cos(alpha). Bei 50 Grad (tan 50 =
    1,19 > 1) gibt es kein Gleichgewicht: das Ergebnis muss Gleiten zeigen und darf
    nicht still „konvergiert“ mit einer Haftkraft melden.
    B2b: ein Wuerfel 0,4 m (hex8 4 x 4 x 4) bei 50 Grad - die Fuge klafft dort
    (e = 0,24 m > b/6); dasselbe ehrliche Kennzeichen, dazu der Deckel von 40 Runden.
B3  Scherklotz nach Oden/Pires: elastischer Block 0,4 x 0,2 m (ebene Dehnung) auf
    starrer Unterlage, mu = 0,5. Die Normalkraft N kommt im Spannschritt (weiche
    Zugglieder mit Endvorspannung, wirken wie eine Totlast), die Schubkraft
    T = a mu N im Lastfall danach, a = 0,3 / 0,6 / 0,8 / 0,9 / 0,99 je ein Lastfall.
    Erwartung (Aussagen des Anwenders): die Gleitzone beginnt am Rand der
    geschlossenen Fuge, waechst mit T nach innen (die Haftzone jeder Stufe liegt in
    der vorigen), ein zusammenhaengender Kern haftet, bei 0,99 mu N gleiten
    mindestens 75 % der Knoten; Gleichgewicht der Fuge 0,1 %, Coulomb je Knoten.
    Der Schub auf dem Deckel kippt den Block (e = T H / N bis 0,1 m > L/6): die
    Fuge klafft an der Seite -x, der Kern liegt an der Seite +x, nicht in der Mitte.
B4  Zapfen in Buchse: Ringe in ebener Dehnung (Zapfen r 20 … 40 mm, Buchse 40 …
    80 mm, 48 Teilungen am Umfang), mu = 0,3. Die Innenkante des Zapfens wird radial
    um delta aufgeweitet (gleichmaessige Pressung) und um theta verdreht
    (Weggroesse, damit auch der Gleitzustand ein Gleichgewicht hat). Grenzmoment
    M_grenz = mu Sum(Fn_i r_i) aus den berechneten Normalkraeften. Haftstufe
    (theta fuer 0,5 M_grenz aus der Torsionssteifigkeit der Ringe): alle haften,
    M = k theta auf 2 %; Gleitstufe (theta fuer 3 M_grenz): alle gleiten,
    M = M_grenz auf 0,5 %.

Jede Pruefung hat eine Gegenprobe (Monkeypatch nur hier): bewusst falsche
Erwartung bzw. veraenderte Reibung - die Pruefung muss dann anschlagen.

Bekannte Befunde stehen in BEKANNTE_BEFUNDE: die Pruefung bleibt, wie sie ist, ihr
Ergebnis wird gedruckt, laesst den Gesamtlauf aber nicht scheitern.

Aufruf:  python -m tests.test_reibkontakt_benchmarks
"""
import contextlib
import math
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_reibkontakt_bm_"), "einstellungen.json")

from statik3d import mesher, solver                                   # noqa: E402
from statik3d.elements import solid as sl                             # noqa: E402
from statik3d.model import ContactPair, Material, Model, Section, ShellProp  # noqa: E402
from tests import pruefkoerper as pk                                  # noqa: E402

E_ST, NU_ST = 210e9, 0.3
MPA = 1e6

RESULTS = []          # (Name, ok, bekannter Befund)

#: Bekannte Befunde am Programm: Name der Pruefung -> Beschreibung. Schlaegt eine
#: dieser Pruefungen an, steht sie als BEFUND im Protokoll und laesst den Lauf nicht
#: scheitern; besteht sie, steht dort „Befund behoben?“.
BEKANNTE_BEFUNDE: dict = {
    # B1 Hertz (p0 −24 % hex8, −27 % tet4, Rand 2 Elemente zu kurz) war bis 08.11.2026 ein
    # Befund des Fangbereichs AUFLIEGEND 1e-3; mit 1e-6 behoben, die Pruefungen gelten wieder
    "B2 Ebene 50°: alle geschlossenen Kontaktknoten gleiten":
        "Endzustand am Deckel (40 Runden, vorläufig): 22 von 25 Knoten gleiten, 3 Knoten am "
        "hangabwärtigen Rand (y = −0,2 / 0 / +0,2 m) stehen auf „Haften“ (Fn 3,1 / 6,2 / 3,1 N, Ft 0,8 / 6,0 / 0,8 N), obwohl das Protokoll "
        "„alle Knoten gleiten … das Bauteil rutscht“ meldet. Den fehlenden Hangabtrieb (45,1 N = 24 %) trägt "
        "die grobe Reststeifigkeit; sie erscheint in den Auflagerkräften der Platte (ΣR_z = G = 246,4 N), "
        "die Gleichgewichtskontrolle meldet daher ok (08.11.2026)",
}


def zahl(x, nd=2):
    if x is None:
        return "–"
    try:
        if not np.isfinite(x):
            return "–"
    except TypeError:
        return str(x)
    return f"{x:.{nd}f}".replace(".", ",")


def rel(ist, soll):
    return (ist / soll - 1.0) * 100.0 if soll else float("nan")


def check(name, ok, detail="", stumm=False):
    ok = bool(ok)
    befund = name in BEKANNTE_BEFUNDE
    if not stumm:
        RESULTS.append((name, ok, befund))
    if ok:
        marke = "OK    " if not befund else "OK (Befund behoben?)"
    else:
        marke = "FEHLER" if not befund else "BEFUND"
    print(f"{marke} {name:88s} {detail}", flush=True)
    return ok


def _konv_text(info):
    info = info or {}
    return (f"konvergiert {info.get('contact_converged')}, Runden {info.get('contact_iterations')}, "
            f"Zustand „{solver.konvergenz_zustand(info)}“, vorläufig „{solver.kontakt_vorlaeufig(info)}“")


def _fuge(res, name):
    return [c for c in (res.contact or []) if str(c.get("label", "")).startswith(name)]


@contextlib.contextmanager
def _mu_faktor(f):
    """Gegenprobe: jede Rechnung in diesem Block mit f-fachem Reibbeiwert."""
    alt = solver.solve_static

    def mit(m, *a, **k):
        for cp in m.contact_pairs:
            if not hasattr(cp, "_mu_vorher"):
                cp._mu_vorher = cp.mu
            cp.mu = cp._mu_vorher * f
        return alt(m, *a, **k)
    solver.solve_static = mit
    try:
        yield
    finally:
        solver.solve_static = alt


# ==========================================================================
# B1 Hertz, mu = 0 (aus der Sicherung vom 01.10.2026, H1)
# ==========================================================================
R_H = 0.1            # Zylinderradius [m]
A_ZIEL = 1e-3        # angestrebte halbe Kontaktbreite [m]
W_FAKTOR = 30.0      # Modellbreite, -hoehe und -tiefe in a
N_HERTZ = 8          # Elemente je a


def e_stern(E=E_ST, nu=NU_ST):
    """E* fuer zwei gleiche Werkstoffe: 1/E* = 2 (1 - nu^2)/E."""
    return E / (2.0 * (1.0 - nu ** 2))


def hertz(P_linie, R=R_H):
    """Hertz, Zylinder auf Ebene, Linienlast P' [N/m]: (a, p0)."""
    a = np.sqrt(4.0 * P_linie * R / (np.pi * e_stern()))
    return a, 2.0 * P_linie / (np.pi * a)


def gestuft(h0, bis, fein, wachstum=1.25):
    """0, h0, 2 h0, ... bis ``fein``, dann geometrisch wachsend bis ``bis``."""
    x = list(np.arange(0.0, fein + 0.5 * h0, h0))
    d = h0
    while x[-1] < bis - 1e-12:
        d *= wachstum
        x.append(min(bis, x[-1] + d))
    return np.asarray(x)


def hertz_modell(typ, n):
    """Halbes Modell (Symmetrie x = 0), eine Elementlage dick (t = h0), uy = 0
    ueberall. Unten der Block z <= 0, oben das Zylindersegment mit Unterkante
    z = R - sqrt(R^2 - x^2) (Knoten auf dem Kreis), Oberkante eben; auf ihr die
    gleichmaessige Druckspannung zur Linienlast P' (Hertz zu a = A_ZIEL)."""
    a = A_ZIEL
    h0 = a / n
    t = h0
    W = W_FAKTOR * a
    xs = gestuft(h0, W, 2.0 * a)
    ds = gestuft(h0, W, 2.0 * a)              # Abstaende von der Kontaktebene
    Hc = ds[-1]
    m = Model(f"Hertz_{typ}_{n}")
    m.add_material(Material("S", E=E_ST, nu=NU_ST, rho=0.0))
    m.case("LF1").gravity = [0, 0, 0]
    ids = {}
    for koerper in ("Block", "Zylinder"):
        for k in range(len(ds)):
            for j in (0, 1):
                for i, x in enumerate(xs):
                    if koerper == "Block":
                        z = -ds[len(ds) - 1 - k]
                    else:
                        zb = R_H - np.sqrt(R_H ** 2 - x ** 2)
                        z = zb + ds[k] * (Hc - zb) / Hc
                    ids[(koerper, i, j, k)] = m.add_node(x, j * t, z)
    elemente = {"Block": [], "Zylinder": []}
    for koerper in ("Block", "Zylinder"):
        for k in range(len(ds) - 1):
            for i in range(len(xs) - 1):
                z = [ids[(koerper, i + (c & 1), (c >> 1) & 1, k + ((c >> 2) & 1))] for c in range(8)]
                if typ == "hex8":
                    elemente[koerper].append(m.add_element("hex8", [z[c] for c in pk.HEX_AUS_ZELLE], "S",
                                                           group=koerper))
                else:
                    for tet in pk.KUHN:
                        kn = [z[c] for c in tet]
                        if pk._tet_volumen(m.nodes[kn]) < 0:
                            kn[1], kn[2] = kn[2], kn[1]
                        elemente[koerper].append(m.add_element("tet4", kn, "S", group=koerper))
    X = np.asarray(m.nodes, float)
    tol = 1e-12
    for nd in range(m.nn):
        dofs = [1]
        if abs(X[nd, 0]) < tol:
            dofs.append(0)
        m.fix(nd, dofs)
    unten = [nd for nd in range(m.nn) if abs(X[nd, 2] + Hc) < tol]
    for nd in unten:
        m.fix(nd, [2])
    zyl_knoten = {int(x) for i in elemente["Zylinder"] for x in m.elements[i].nodes}
    zb = R_H - np.sqrt(np.maximum(R_H ** 2 - X[:, 0] ** 2, 0.0))
    slave = sorted(nd for nd in zyl_knoten if abs(X[nd, 2] - zb[nd]) < 1e-12 and X[nd, 0] <= 4 * a + tol)
    master = []
    for i in elemente["Block"]:
        e = m.elements[i]
        for f in sl.FLAECHEN_ECKEN[e.typ]:
            kn = [int(e.nodes[c]) for c in f]
            if np.all(np.abs(X[kn, 2]) < tol) and np.all(X[kn, 0] <= 5 * a + tol):
                master.append(kn)
    m.contact_pairs.append(ContactPair("Hertz", slave_nodes=slave, master_faces=master, mu=0.0,
                                       search_radius=2.0 * a))
    P_linie = np.pi * a ** 2 * e_stern() / (4.0 * R_H)
    P_halb = 0.5 * P_linie * t
    q = P_halb / (xs[-1] * t)
    oben = pk.randseiten(m, lambda P: bool(np.all(np.abs(P[:, 2] - Hc) < 1e-12)))
    pk.spannung_auf_seiten(m, oben, lambda x: np.array([0.0, 0.0, -q]))
    return m, {"slave": slave, "unten": unten, "t": t, "h0": h0, "P_halb": P_halb}


def hertz_auswerten(m, res, meta):
    """Soll aus der gemessenen Auflagerkraft; p0 aus der Knotenkraft der Mittellinie
    durch ihre Einflussbreite; Kontaktrand zwischen letztem tragenden und erstem
    offenen Knoten."""
    X = np.asarray(m.nodes, float)
    t, h0 = meta["t"], meta["h0"]
    P_halb = float(res.reactions[meta["unten"], 2].sum())
    P_linie = 2.0 * P_halb / t
    a_H, p0_H = hertz(P_linie)
    cf = np.asarray(res.contact_forces if res.contact_forces is not None else np.zeros((m.nn, 3)), float)
    je_x: dict = {}
    for nd in meta["slave"]:
        key = round(float(X[nd, 0]), 12)
        je_x[key] = je_x.get(key, 0.0) + float(cf[nd, 2])
    xs_s = np.array(sorted(je_x))
    Fx = np.array([je_x[x] for x in xs_s])
    breite = np.empty(len(xs_s))
    for i in range(len(xs_s)):
        li = xs_s[i - 1] if i > 0 else xs_s[0]
        re = xs_s[i + 1] if i + 1 < len(xs_s) else xs_s[-1]
        breite[i] = 0.5 * (re - li) if i > 0 else 0.5 * (re - xs_s[0])
    p = Fx / (breite * t)
    p0_FE = float(p[0])
    traeger = np.flatnonzero(Fx > 1e-6 * max(float(Fx.max()), 1e-30))
    x_last = float(xs_s[traeger[-1]]) if len(traeger) else 0.0
    x_next = float(xs_s[traeger[-1] + 1]) if len(traeger) and traeger[-1] + 1 < len(xs_s) else float("nan")
    if x_last <= a_H <= x_next:
        da = 0.0
    else:
        da = (min(abs(a_H - x_last), abs(a_H - x_next))) / h0 * np.sign(x_last - a_H)
    return {"P_linie": P_linie, "a_H": a_H, "p0_H": p0_H, "p0_FE": p0_FE, "x_last": x_last, "x_next": x_next,
            "da": da, "F_kontakt": float(Fx.sum()), "P_halb": P_halb, "P_soll": meta["P_halb"]}


def hertz_pruefen(typ, w, stumm=False, zusatz=""):
    ok = []
    ok.append(check(f"B1 Hertz {typ}{zusatz}: p0 auf 2 %",
                    abs(rel(w["p0_FE"], w["p0_H"])) <= 2.0,
                    f"Soll {zahl(w['p0_H'] / MPA, 1)} N/mm², Ist {zahl(w['p0_FE'] / MPA, 1)} N/mm², "
                    f"Abweichung {zahl(rel(w['p0_FE'], w['p0_H']))} %", stumm))
    ok.append(check(f"B1 Hertz {typ}{zusatz}: Kontaktrand a innerhalb eines Elements",
                    abs(w["da"]) <= 1.0,
                    f"Soll a {zahl(w['a_H'] * 1e3, 4)} mm, Ist Rand zwischen {zahl(w['x_last'] * 1e3, 4)} und "
                    f"{zahl(w['x_next'] * 1e3, 4)} mm, Abweichung {zahl(w['da'])} Elemente", stumm))
    ok.append(check(f"B1 Hertz {typ}{zusatz}: Gleichgewicht ΣF_Kontakt = ΣR = Last (0,1 %)",
                    abs(rel(w["F_kontakt"], w["P_halb"])) <= 0.1 and abs(rel(w["P_halb"], w["P_soll"])) <= 0.1,
                    f"Last {zahl(w['P_soll'], 3)} N, ΣR {zahl(w['P_halb'], 3)} N "
                    f"({zahl(rel(w['P_halb'], w['P_soll']), 4)} %), ΣF_Kontakt {zahl(w['F_kontakt'], 3)} N "
                    f"({zahl(rel(w['F_kontakt'], w['P_halb']), 4)} %)", stumm))
    return all(ok)


_HERTZ = {}


@contextlib.contextmanager
def _ohne_fangbereich():
    """Ursachenprobe B1 (Monkeypatch nur hier): kein Anfangsspalt wird auf Berührung gesetzt."""
    from statik3d import contact as ct
    alt = ct.AUFLIEGEND
    ct.AUFLIEGEND = 0.0
    try:
        yield
    finally:
        ct.AUFLIEGEND = alt


def _hertz_lauf(typ):
    t0 = time.perf_counter()
    m, meta = hertz_modell(typ, N_HERTZ)
    res = solver.solve_static(m, workers=1)
    dt = time.perf_counter() - t0
    w = hertz_auswerten(m, res, meta)
    print(f"     {typ}: {m.nn} Knoten, {len(m.elements)} Elemente, P′ {zahl(w['P_linie'] / 1e3, 1)} kN/m, "
          f"{_konv_text(res.info)}, Rechenzeit {zahl(dt, 1)} s")
    return m, res, meta, w


def test_hertz():
    print("\n--- B1 Hertz: Zylinder auf Ebene, μ = 0, ebene Dehnung, Netz a/8 ---")
    for typ in ("hex8", "tet4"):
        m, res, meta, w = _hertz_lauf(typ)
        check(f"B1 Hertz {typ}: Kontakt konvergiert", res.info.get("contact_converged")
              and not solver.kontakt_vorlaeufig(res.info), _konv_text(res.info))
        hertz_pruefen(typ, w)
    print("\n--- Ursachenprobe B1: dieselben Modelle mit contact.AUFLIEGEND = 0 (Monkeypatch) ---")
    for typ in ("hex8", "tet4"):
        with _ohne_fangbereich():
            m, res, meta, w = _hertz_lauf(typ)
        _HERTZ[typ] = (m, res, meta)
        hertz_pruefen(typ, w, zusatz=" [AUFLIEGEND = 0]")


def gegenprobe_hertz():
    """Falsche Erwartung: E* = E/(1 - nu^2) (ein Koerper starr gedacht) statt
    E/(2 (1 - nu^2)) - p0 laege um den Faktor sqrt 2 daneben. Geprueft am Lauf der
    Ursachenprobe, der mit richtiger Erwartung besteht."""
    print("\n--- Gegenprobe B1: falsches E* = E/(1 − ν²) (Monkeypatch e_stern), Lauf mit AUFLIEGEND = 0 ---")
    g = globals()
    alt = g["e_stern"]
    g["e_stern"] = lambda E=E_ST, nu=NU_ST: E / (1.0 - nu ** 2)
    try:
        m, res, meta = _HERTZ["hex8"]
        w = hertz_auswerten(m, res, meta)
        schlaegt = not hertz_pruefen("hex8", w, stumm=True, zusatz=" [Gegenprobe]")
    finally:
        g["e_stern"] = alt
    check("Gegenprobe B1: mit falschem E* schlägt die Hertz-Prüfung an", schlaegt)


# ==========================================================================
# B2 Klotz auf schiefer Ebene, mu = 1
# ==========================================================================
MU_EBENE = 1.0
RHO = 7850.0
G_ERD = 9.81
B_KLOTZ, H_KLOTZ, NZ_KLOTZ = 0.4, 0.02, 1          # flache Platte (B2)
H_WUERFEL, NZ_WUERFEL = 0.4, 4                       # Wuerfel (B2b)


def schiefe_ebene(alpha_grad, mu=MU_EBENE, h=H_KLOTZ, nz=NZ_KLOTZ):
    """Starre, feste Platte 1,0 x 1,0 m (Schale, E 2,1e14), darauf ein Stahlklotz
    0,4 x 0,4 x h (hex8 4 x 4 x nz, rho 7 850) unter Eigengewicht; alles um alpha
    um die y-Achse gedreht (Hang faellt in +x). Der Klotz ist in der Hangrichtung
    frei; quer dazu halten die Knoten der Symmetrieebene y = 0 uy fest (verhindert
    auch das Drehen um die Normale, kostet bei symmetrischer Last nichts)."""
    m = Model(f"Schiefe Ebene {alpha_grad:g} Grad")
    m.add_material(Material("S235", E=E_ST, nu=NU_ST, rho=RHO))
    m.add_material(Material("Starr", E=210e12, nu=NU_ST, rho=0.0))
    m.add_shell_prop(ShellProp("t = 50 mm", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t = 50 mm", 1.0, 1.0, 2, 2, origin=(-0.5, -0.5, 0))
    for k in pl.ravel():
        m.fix(int(k), "all")
    platte = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S235", B_KLOTZ, B_KLOTZ, h, 4, 4, nz, origin=(-0.2, -0.2, 0.0))
    unten = [int(k) for k in box[:, :, 0].ravel()]
    for k in box[:, 2, :].ravel():
        m.fix(int(k), [1])
    m.add_contact_pair("Klotz/Ebene", unten, platte, mu=mu)
    a = math.radians(alpha_grad)
    X = np.asarray(m.nodes, float)
    x, z = X[:, 0].copy(), X[:, 2].copy()
    X[:, 0] = x * math.cos(a) + z * math.sin(a)
    X[:, 2] = -x * math.sin(a) + z * math.cos(a)
    m.nodes = X
    m.case("LF1").gravity = [0.0, 0.0, -G_ERD]
    m.active_case = "LF1"
    G = RHO * B_KLOTZ ** 2 * h * G_ERD
    n = np.array([math.sin(a), 0.0, math.cos(a)])        # Normale der Ebene (nach oben)
    s = np.array([math.cos(a), 0.0, -math.sin(a)])       # hangabwaerts
    return m, unten, G, n, s


def ebene_rechnen(alpha_grad, mu=MU_EBENE, h=H_KLOTZ, nz=NZ_KLOTZ):
    m, unten, G, n, s = schiefe_ebene(alpha_grad, mu, h, nz)
    t0 = time.perf_counter()
    res = solver.solve_static(m, workers=1)
    dt = time.perf_counter() - t0
    fuge = _fuge(res, "Klotz/Ebene")
    F = np.sum([np.asarray(c["F_vek"], float) for c in fuge], axis=0) if fuge else np.zeros(3)
    # F_vek: Kraft auf den Klotz. Normalanteil = G cos a, Reibung = -G sin a (hangaufwaerts)
    zu = [c for c in fuge if c["status"] != "offen"]
    haft = [c for c in zu if c["status"] == "Haften"]
    gleit = [c for c in zu if c["status"] == "Gleiten"]
    ausn = max((float(c["Ft"]) / (mu * float(c["Fn"])) for c in zu if float(c["Fn"]) > 0), default=0.0)
    coul = max((abs(float(c["Ft"]) - mu * float(c["Fn"])) / max(mu * float(c["Fn"]), 1e-300)
                for c in gleit if float(c["Fn"]) > 0), default=0.0)
    log = res.info.get("contact_log") or []
    rutsch = [z for z in log if "Reibung reicht" in z or "das Bauteil rutscht" in z]
    deckel = sum(1 for z in log if "Nachpruefung der Reibung nach" in z)
    u = np.asarray(res.u, float).reshape(m.nn, -1)[:, :3]
    weg = float(np.max(u[unten] @ s))
    Rz = float(np.asarray(res.reactions, float)[:, 2].sum())
    return {"res": res, "G": G, "Fn": float(F @ n), "Ft": float(-(F @ s)), "zu": zu, "haft": haft,
            "gleit": gleit, "ausn": ausn, "coul": coul, "rutsch": rutsch, "deckel": deckel, "weg": weg,
            "Rz": Rz, "dt": dt, "m": m}


def ebene_40_pruefen(e, alpha=40.0, mu=MU_EBENE, stumm=False, zusatz=""):
    a = math.radians(alpha)
    Fn_soll, Ft_soll = e["G"] * math.cos(a), e["G"] * math.sin(a)
    info = e["res"].info
    ok = []
    ok.append(check(f"B2 Ebene {alpha:g}°{zusatz}: Kontakt konvergiert, nicht vorläufig",
                    info.get("contact_converged") and not solver.kontakt_vorlaeufig(info), _konv_text(info), stumm))
    ok.append(check(f"B2 Ebene {alpha:g}°{zusatz}: alle Kontaktknoten haften (|Ft| < μ Fn)",
                    len(e["zu"]) > 0 and len(e["haft"]) == len(e["zu"]) and e["ausn"] < 1.0,
                    f"haftend {len(e['haft'])} von {len(e['zu'])} geschlossenen, gleitend {len(e['gleit'])}, "
                    f"max |Ft|/(μ Fn) {zahl(e['ausn'], 3)} (Soll < 1, Mittel tan α/μ = {zahl(math.tan(a) / mu, 3)})",
                    stumm))
    ok.append(check(f"B2 Ebene {alpha:g}°{zusatz}: Reibkraft = Hangabtrieb G sin α (0,1 %)",
                    abs(rel(e["Ft"], Ft_soll)) <= 0.1,
                    f"Soll {zahl(Ft_soll, 1)} N, Ist {zahl(e['Ft'], 1)} N, Abweichung {zahl(rel(e['Ft'], Ft_soll), 4)} %",
                    stumm))
    ok.append(check(f"B2 Ebene {alpha:g}°{zusatz}: Normalkraft = G cos α (0,1 %)",
                    abs(rel(e["Fn"], Fn_soll)) <= 0.1,
                    f"Soll {zahl(Fn_soll, 1)} N, Ist {zahl(e['Fn'], 1)} N, Abweichung {zahl(rel(e['Fn'], Fn_soll), 4)} %",
                    stumm))
    ok.append(check(f"B2 Ebene {alpha:g}°{zusatz}: der Klotz bewegt sich nicht (Weg hangab < 1 µm)",
                    e["weg"] < 1e-6, f"Weg hangab {zahl(e['weg'] * 1e6, 3)} µm", stumm))
    return all(ok)


def ebene_50_pruefen(e, name, stumm=False):
    """Kein Gleichgewicht moeglich. Was das Programm tut (gemessen 08.11.2026): der
    Kontakt heisst nicht konvergiert, das Ergebnis traegt die Kennzeichnung
    „vorläufig“, das Protokoll sagt „alle Knoten gleiten ... das Bauteil rutscht,
    grobe Reststeifigkeit haelt es“ (bzw. „Reibung reicht nicht fuer das
    Gleichgewicht“); den fehlenden Hangabtrieb traegt die Reststeifigkeit. Geprueft
    wird genau das, dazu: die Fuge zeigt keine Reibkraft ueber mu Fn (keine falsche
    Haftkraft) und alle geschlossenen Knoten gleiten. Eine stille Konvergenz waere
    ein Fehler."""
    a = math.radians(50.0)
    info = e["res"].info
    gg = info.get("gleichgewicht_global") or {}
    rest = e["G"] * math.sin(a) - e["Ft"]
    print(f"     {name}: G {zahl(e['G'], 1)} N, {_konv_text(info)}, Rechenzeit {zahl(e['dt'], 1)} s")
    print(f"     ΣFn {zahl(e['Fn'], 1)} N (G cos α {zahl(e['G'] * math.cos(a), 1)} N), Reibkraft hangauf "
          f"{zahl(e['Ft'], 1)} N (G sin α {zahl(e['G'] * math.sin(a), 1)} N, Rest {zahl(rest, 1)} N "
          f"= {zahl(100 * rest / (e['G'] * math.sin(a)), 1)} % ohne Fuge), ΣR_z {zahl(e['Rz'], 1)} N, "
          f"Gleichgewichtskontrolle ok {gg.get('ok')} (rel_F {zahl(100 * float(gg.get('rel_F', float('nan'))), 1)} %), "
          f"Weg hangab {zahl(e['weg'] * 1e6, 3)} µm, Deckelzeilen {e['deckel']}")
    for z in e["rutsch"][:2]:
        print(f"     Meldung: {z[:220]}")
    ok = []
    ok.append(check(f"{name}: keine stille Konvergenz (nicht konvergiert und „vorläufig“ gekennzeichnet)",
                    (not info.get("contact_converged")) and bool(solver.kontakt_vorlaeufig(info)),
                    _konv_text(info), stumm))
    ok.append(check(f"{name}: Protokoll meldet „das Bauteil rutscht“ bzw. „Reibung reicht nicht“", bool(e["rutsch"]),
                    f"{len(e['rutsch'])} Zeilen", stumm))
    ok.append(check(f"{name}: keine falsche Haftkraft (je Knoten |Ft| ≤ μ Fn, gleitend = μ Fn; ΣFt ≤ μ ΣFn)",
                    e["ausn"] <= 1.0 + 1e-6 and e["coul"] <= 1e-6 and e["Ft"] <= MU_EBENE * e["Fn"] * (1 + 1e-6),
                    f"max |Ft|/(μ Fn) {zahl(e['ausn'], 6)}, gleitend größte Abweichung {e['coul']:.1e}, "
                    f"Reibkraft {zahl(e['Ft'], 1)} N ≤ μ ΣFn {zahl(MU_EBENE * e['Fn'], 1)} N", stumm))
    ok.append(check(f"{name}: alle geschlossenen Kontaktknoten gleiten",
                    len(e["zu"]) > 0 and len(e["gleit"]) == len(e["zu"]),
                    f"gleitend {len(e['gleit'])} von {len(e['zu'])}, haftend {len(e['haft'])} "
                    f"(Fn {', '.join(zahl(float(c['Fn']), 2) for c in e['haft'])} N)", stumm))
    return all(ok)


def test_schiefe_ebene():
    print("\n--- B2 Platte auf schiefer Ebene, μ = 1: haftet bei 40°, gleitet bei 50° ---")
    e = ebene_rechnen(40.0)
    print(f"     40°: G {zahl(e['G'], 1)} N, {_konv_text(e['res'].info)}, Rechenzeit {zahl(e['dt'], 1)} s")
    ebene_40_pruefen(e)
    ebene_50_pruefen(ebene_rechnen(50.0), "B2 Ebene 50°")
    print("\n--- B2b Würfel 0,4 m bei 50° (Fuge klafft) ---")
    e = ebene_rechnen(50.0, h=H_WUERFEL, nz=NZ_WUERFEL)
    ebene_50_pruefen(e, "B2b Würfel 50°")
    from statik3d import contact as ct
    n_r = int(e["res"].info.get("contact_iterations") or 0)
    check(f"B2b Würfel 50°: der Lauf endet am Deckel (höchstens {ct.MAX_CYCLES} Runden)",
          n_r <= ct.MAX_CYCLES + 1,
          f"{n_r} Runden, {e['deckel']} Zeilen „Nachprüfung der Reibung nach {ct.MAX_CYCLES} Runden abgebrochen“")


def gegenprobe_ebene():
    """mu = 0 statt 1 bei 40 Grad: der Klotz darf nicht mehr haften. Und die
    50-Grad-Pruefung muss eine still konvergierte Meldung erkennen: dasselbe
    Ergebnis mit contact_converged = True und ohne Kennzeichnung vorgelegt."""
    print("\n--- Gegenprobe B2: 40° mit μ = 0 (Monkeypatch solve_static) ---")
    try:
        with _mu_faktor(0.0):
            e = ebene_rechnen(40.0)
        print(f"     {_konv_text(e['res'].info)}, Rechenzeit {zahl(e['dt'], 1)} s")
        schlaegt = not ebene_40_pruefen(e, stumm=True, zusatz=" [Gegenprobe μ = 0]")
        txt = ""
    except Exception as ex:                 # noqa: BLE001
        schlaegt, txt = True, f"Rechnung bricht ab: {type(ex).__name__}: {str(ex)[:160]}"
    check("Gegenprobe B2: mit μ = 0 schlägt die Haft-Prüfung bei 40° an", schlaegt, txt)
    print("\n--- Gegenprobe B2 50°: still „konvergiert“ vorgelegt (Monkeypatch kontakt_vorlaeufig) ---")
    e = ebene_rechnen(50.0)
    e["res"].info["contact_converged"] = True
    e["res"].info.pop("vorlaeufig", None)
    alt = solver.kontakt_vorlaeufig
    solver.kontakt_vorlaeufig = lambda info: ""
    try:
        schlaegt = not ebene_50_pruefen(e, "B2 Ebene 50° [Gegenprobe still]", stumm=True)
    finally:
        solver.kontakt_vorlaeufig = alt
    check("Gegenprobe B2 50°: eine stille Konvergenz schlägt an", schlaegt)


# ==========================================================================
# B3 Scherklotz nach Oden/Pires
# ==========================================================================
MU_OP = 0.5
N_OP = 100e3
L_OP, H_OP, T_OP = 0.4, 0.2, 0.025
NX_OP, NZ_OP = 16, 8
ANTEILE_OP = (0.3, 0.6, 0.8, 0.9, 0.99)


def scherklotz(anteile=ANTEILE_OP, mu=MU_OP):
    """Block L x T x H (hex8 16 x 1 x 8) auf starrer, fester Platte, uy ueberall
    gehalten (ebene Dehnung). N: je Deckelknoten ein senkrechtes Zugglied zu einem
    festen Punkt 1 m unter der Fuge mit Endvorspannung (Anteil der Einflussbreite);
    die Glieder sind weich (EA/L 2,1e5 N/m, gegen rund 1e9 N/m des Blocks), ihre Kraft
    bleibt nach dem Verriegeln praktisch die Vorspannung - N wirkt wie eine Totlast,
    zuerst (Spannschritt). T = a mu N in +x als gleichmaessiger Schub auf dem Deckel,
    je Anteil a ein Lastfall."""
    m = Model("Scherklotz Oden/Pires")
    m.add_material(Material("S235", E=E_ST, nu=NU_ST, rho=0.0))
    m.add_material(Material("Starr", E=210e12, nu=NU_ST, rho=0.0))
    m.add_shell_prop(ShellProp("t = 50 mm", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t = 50 mm", 1.0, 0.2, 4, 2, origin=(-0.5, -0.1, 0))
    for k in pl.ravel():
        m.fix(int(k), "all")
    platte = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S235", L_OP, T_OP, H_OP, NX_OP, 1, NZ_OP, origin=(-L_OP / 2, -T_OP / 2, 0.0))
    for k in box.ravel():
        m.fix(int(k), [1])
    unten = [int(k) for k in box[:, :, 0].ravel()]
    deckel = [int(k) for k in box[:, :, -1].ravel()]
    m.add_contact_pair("Block/Unterlage", unten, platte, mu=mu)
    X = np.asarray(m.nodes, float)
    dx = L_OP / NX_OP
    gewicht = {k: (0.5 if abs(abs(X[k, 0]) - L_OP / 2) < 1e-9 else 1.0) for k in deckel}
    summe = sum(gewicht.values())
    m.add_section(Section("Zugglied", 1e-6, 1e-12, 1e-12, 2e-12))
    glieder = []
    for i, k in enumerate(deckel):
        p = m.add_node(X[k, 0], X[k, 1], -1.0)
        m.fix(p, "all")
        e = m.add_element("truss", [k, p], "S235", "Zugglied")
        m.add_member(f"Z{i}", [e])
        glieder.append((f"Z{i}", N_OP * gewicht[k] / summe))
    m.load_cases.clear()
    for a in anteile:
        lf = f"T{a:g}"
        m.add_load_case(lf).gravity = [0.0, 0.0, 0.0]
        for name, P in glieder:
            m.add_vorspannung(name, P, case=lf, sollkraft=True)
        for k in deckel:
            m.case(lf).nodal_loads.append(_knotenlast(k, a * mu * N_OP * gewicht[k] / summe, 0.0, 0.0))
    m.plastizitaet.an = False
    return m, unten, dx


def _knotenlast(n, fx, fy, fz):
    from statik3d.model import NodalLoad
    return NodalLoad(int(n), [fx, fy, fz, 0.0, 0.0, 0.0])


def scherklotz_rechnen(anteile=ANTEILE_OP, mu_rechnung=None):
    m, unten, dx = scherklotz(anteile)
    X = np.asarray(m.nodes, float)
    aus = []
    for a in anteile:
        t0 = time.perf_counter()
        res = solver.solve_static(m, case=f"T{a:g}", workers=1)
        dt = time.perf_counter() - t0
        fuge = _fuge(res, "Block/Unterlage")
        # je x-Stelle der Status (beide Knoten y = -T/2 und +T/2)
        st: dict = {}
        coul = 0.0
        for c in fuge:
            x = round(float(X[int(c["node"]), 0]), 9)
            st.setdefault(x, set()).add(c["status"])
            if c["status"] == "Haften" and float(c["Fn"]) > 0:
                coul = max(coul, float(c["Ft"]) / (MU_OP * float(c["Fn"])) - 1.0)
            if c["status"] == "Gleiten" and float(c["Fn"]) > 0:
                coul = max(coul, abs(float(c["Ft"]) / (MU_OP * float(c["Fn"])) - 1.0))
        F = np.sum([np.asarray(c["F_vek"], float) for c in fuge], axis=0)
        gleit_x = sorted(x for x, s in st.items() if "Gleiten" in s)
        haft_x = sorted(x for x, s in st.items() if s == {"Haften"})
        n_gl = sum(1 for c in fuge if c["status"] == "Gleiten")
        n_zu = sum(1 for c in fuge if c["status"] != "offen")
        aus.append({"a": a, "res": res, "dt": dt, "Fx": float(F[0]), "Fz": float(F[2]), "gleit_x": gleit_x,
                    "haft_x": haft_x, "n_gl": n_gl, "n_zu": n_zu, "coul": coul, "alle_x": sorted(st)})
    return aus, dx


def _bild(e):
    """Zeile je x-Stelle: G gleitet, H haftet, o offen."""
    z = ""
    for x in e["alle_x"]:
        z += "G" if x in e["gleit_x"] else ("H" if x in e["haft_x"] else "o")
    return z


def _zusammenhaengend(teil, reihe):
    """Liegen die Stellen ``teil`` in der geordneten Reihe ``reihe`` lueckenlos beieinander?"""
    idx = [i for i, x in enumerate(reihe) if x in teil]
    return bool(idx) and idx == list(range(idx[0], idx[-1] + 1))


def scherklotz_pruefen(laeufe, dx, stumm=False, zusatz=""):
    ok = []
    haft_vorher, n_vorher, erste = None, 0, None
    for e in laeufe:
        a = e["a"]
        T, info = a * MU_OP * N_OP, e["res"].info
        print(f"     a = {zahl(a)}: T {zahl(T / 1e3, 2)} kN, Fuge −x … +x  {_bild(e)}  "
              f"(G gleitet, H haftet, o offen; gleitend {e['n_gl']} von {e['n_zu']}), {_konv_text(info)}, "
              f"Rechenzeit {zahl(e['dt'], 1)} s")
        ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: Kontakt konvergiert, nicht vorläufig",
                        info.get("contact_converged") and not solver.kontakt_vorlaeufig(info), _konv_text(info), stumm))
        ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: Gleichgewicht der Fuge ΣFt = T, ΣFn = N (0,1 %)",
                        abs(rel(-e["Fx"], T)) <= 0.1 and abs(rel(e["Fz"], N_OP)) <= 0.1,
                        f"Soll T {zahl(T / 1e3, 3)} kN, Ist {zahl(-e['Fx'] / 1e3, 3)} kN ({zahl(rel(-e['Fx'], T), 4)} %); "
                        f"Soll N {zahl(N_OP / 1e3, 3)} kN, Ist {zahl(e['Fz'] / 1e3, 3)} kN ({zahl(rel(e['Fz'], N_OP), 4)} %)",
                        stumm))
        ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: Coulomb je Knoten (haftend ≤ μ Fn, gleitend = μ Fn, 1e-6)",
                        e["coul"] <= 1e-6, f"größte Verletzung {e['coul']:.1e}", stumm))
        gl, haft = set(e["gleit_x"]), set(e["haft_x"])
        zu = [x for x in e["alle_x"] if x in gl or x in haft]
        if haft_vorher is not None:
            ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: die Gleitzone wandert nach innen "
                            "(Haftzone in der vorigen, nicht weniger Gleitknoten)",
                            haft <= haft_vorher and e["n_gl"] >= n_vorher,
                            f"haftend {len(haft)} x-Stellen (vorher {len(haft_vorher)}), "
                            f"gleitend {e['n_gl']} Knoten (vorher {n_vorher})", stumm))
        haft_vorher, n_vorher = haft, e["n_gl"]
        if a < 0.99:
            ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: ein zusammenhängender Kern haftet",
                            _zusammenhaengend(haft, zu),
                            f"haftend x = {zahl(min(haft) * 1e3, 0) if haft else '–'} … "
                            f"{zahl(max(haft) * 1e3, 0) if haft else '–'} mm ({len(haft)} von {len(zu)} Stellen)",
                            stumm))
        if erste is None and gl:
            erste = a
            ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: das Gleiten beginnt am Rand der geschlossenen "
                            "Fuge (zusammenhängend, mit einer Randstelle)",
                            _zusammenhaengend(gl, zu) and (zu[0] in gl or zu[-1] in gl),
                            f"erste Stufe mit Gleiten; gleitend x = {zahl(min(gl) * 1e3, 0)} … "
                            f"{zahl(max(gl) * 1e3, 0)} mm, geschlossen {zahl(zu[0] * 1e3, 0)} … "
                            f"{zahl(zu[-1] * 1e3, 0)} mm", stumm))
        if a >= 0.99:
            anteil = e["n_gl"] / max(e["n_zu"], 1)
            ok.append(check(f"B3 Oden/Pires a = {zahl(a)}{zusatz}: fast alles gleitet (≥ 75 % der Knoten)",
                            anteil >= 0.75, f"{zahl(anteil * 100, 1)} % gleitend", stumm))
    if erste is None:
        ok.append(check(f"B3 Oden/Pires{zusatz}: in keiner Stufe gleitet etwas", False, "", stumm))
    return all(ok)


def test_oden_pires():
    print("\n--- B3 Scherklotz nach Oden/Pires: N im Spannschritt, dann T = a μ N, μ = 0,5 ---")
    laeufe, dx = scherklotz_rechnen()
    scherklotz_pruefen(laeufe, dx)


def gegenprobe_oden_pires():
    """mu in der Rechnung verdoppelt (Auswertung mit mu 0,5): bei 0,99 mu N haftet dann
    der groesste Teil, die Pruefung „fast alles gleitet“ muss anschlagen."""
    print("\n--- Gegenprobe B3: Rechnung mit 2 μ (Monkeypatch solve_static), Erwartung mit μ ---")
    with _mu_faktor(2.0):
        laeufe, dx = scherklotz_rechnen(anteile=(0.3, 0.99))
    schlaegt = not scherklotz_pruefen(laeufe, dx, stumm=True, zusatz=" [Gegenprobe 2 μ]")
    check("Gegenprobe B3: mit doppeltem μ schlägt die Oden/Pires-Prüfung an", schlaegt)


# ==========================================================================
# B4 Zapfen in Buchse: Reibmoment M = mu Sum(Fn r)
# ==========================================================================
MU_Z = 0.3
R_I, R_K, R_A, T_Z = 0.02, 0.04, 0.08, 0.01      # Zapfen innen, Kontakt, Buchse aussen, Dicke
N_UMFANG, N_RADIAL = 48, 4
DELTA = 5e-6                                      # radiale Aufweitung der Zapfen-Innenkante


def zapfen(drehungen, mu=MU_Z):
    """Zwei Ringe (hex8) in ebener Dehnung (uz ueberall gehalten): Zapfen R_I … R_K,
    Buchse R_K … R_A, an der Fuge knotengleich. Buchse aussen fest. Die Innenkante
    des Zapfens ist gelagert und bekommt je Lastfall die Zwangsverformung
    u = DELTA e_r + theta R_I e_t. Kontaktpaar: Zapfen aussen (Slave) gegen die
    Innenseiten der Buchse (Master)."""
    m = Model("Zapfen in Buchse")
    m.add_material(Material("S235", E=E_ST, nu=NU_ST, rho=0.0))
    phis = np.linspace(0.0, 2 * np.pi, N_UMFANG, endpoint=False)
    ids = {}
    elemente = {"Zapfen": [], "Buchse": []}
    for koerper, r0, r1 in (("Zapfen", R_I, R_K), ("Buchse", R_K, R_A)):
        rs = np.linspace(r0, r1, N_RADIAL + 1)
        for i, r in enumerate(rs):
            for j, p in enumerate(phis):
                for k in (0, 1):
                    ids[(koerper, i, j, k)] = m.add_node(r * math.cos(p), r * math.sin(p), k * T_Z)
        for i in range(N_RADIAL):
            for j in range(N_UMFANG):
                j1 = (j + 1) % N_UMFANG
                kn = [ids[(koerper, i, j, 0)], ids[(koerper, i + 1, j, 0)], ids[(koerper, i + 1, j1, 0)],
                      ids[(koerper, i, j1, 0)], ids[(koerper, i, j, 1)], ids[(koerper, i + 1, j, 1)],
                      ids[(koerper, i + 1, j1, 1)], ids[(koerper, i, j1, 1)]]
                elemente[koerper].append(m.add_element("hex8", kn, "S235", group=koerper))
    X = np.asarray(m.nodes, float)
    r = np.hypot(X[:, 0], X[:, 1])
    for nd in range(m.nn):
        m.fix(nd, [2])
    innen = [ids[("Zapfen", 0, j, k)] for j in range(N_UMFANG) for k in (0, 1)]
    aussen = [ids[("Buchse", N_RADIAL, j, k)] for j in range(N_UMFANG) for k in (0, 1)]
    for nd in innen + aussen:
        m.fix(nd, [0, 1])
    slave = [ids[("Zapfen", N_RADIAL, j, k)] for j in range(N_UMFANG) for k in (0, 1)]
    master = []
    for i in elemente["Buchse"]:
        e = m.elements[i]
        for f in sl.FLAECHEN_ECKEN[e.typ]:
            kn = [int(e.nodes[c]) for c in f]
            if np.all(np.abs(r[kn] - R_K) < 1e-9):
                master.append(kn)
    m.contact_pairs.append(ContactPair("Zapfen/Buchse", slave_nodes=slave, master_faces=master, mu=mu,
                                       search_radius=0.25 * (R_K - R_I)))
    m.load_cases.clear()
    for name, th in drehungen:
        m.add_load_case(name).gravity = [0.0, 0.0, 0.0]
        for nd in innen:
            p = math.atan2(X[nd, 1], X[nd, 0])
            ux = DELTA * math.cos(p) - th * R_I * math.sin(p)
            uy = DELTA * math.sin(p) + th * R_I * math.cos(p)
            m.add_zwangsverformung(nd, [0, 1], [ux, uy], case=name)
    m.plastizitaet.an = False
    return m, innen, slave


def zapfen_auswerten(m, res, innen, slave, mu=MU_Z):
    X = np.asarray(m.nodes, float)
    R = np.asarray(res.reactions, float)
    M = float(np.sum(X[innen, 0] * R[innen, 1] - X[innen, 1] * R[innen, 0]))      # Moment der Lager auf den Zapfen
    fuge = _fuge(res, "Zapfen/Buchse")
    sFn = sum(float(c["Fn"]) for c in fuge)
    sFnr = sum(float(c["Fn"]) * float(np.hypot(*X[int(c["node"]), :2])) for c in fuge)
    zu = [c for c in fuge if c["status"] != "offen"]
    haft = sum(1 for c in zu if c["status"] == "Haften")
    gleit = sum(1 for c in zu if c["status"] == "Gleiten")
    M_reib = 0.0
    for c in fuge:
        x = X[int(c["node"])]
        f = np.asarray(c["F_vek"], float)
        M_reib += float(x[0] * f[1] - x[1] * f[0])          # Moment der Fuge auf den Zapfen
    return {"M": M, "M_reib": M_reib, "sFn": sFn, "M_grenz": mu * sFnr, "zu": len(zu), "haft": haft,
            "gleit": gleit, "n": len(fuge)}


def k_dreh():
    """Drehsteifigkeit der beiden Ringe (Torsion in der Ebene, haftend verbunden):
    tau = M/(2 pi r^2 t), d(theta)/dr = 2 tau/(G r) -> theta = M/(4 pi G t) (1/R_I^2 - 1/R_A^2)."""
    G = E_ST / (2.0 * (1.0 + NU_ST))
    return 4.0 * np.pi * G * T_Z / (1.0 / R_I ** 2 - 1.0 / R_A ** 2)


def zapfen_rechnen():
    t0 = time.perf_counter()
    m, innen, slave = zapfen([("Z0", 0.0)])
    r0 = solver.solve_static(m, case="Z0", workers=1)
    w0 = zapfen_auswerten(m, r0, innen, slave)
    k = k_dreh()
    th_h = 0.5 * w0["M_grenz"] / k
    th_g = 3.0 * w0["M_grenz"] / k
    m, innen, slave = zapfen([("Haften", th_h), ("Gleiten", th_g)])
    rh = solver.solve_static(m, case="Haften", workers=1)
    rg = solver.solve_static(m, case="Gleiten", workers=1)
    dt = time.perf_counter() - t0
    return {"w0": w0, "r0": r0, "th_h": th_h, "th_g": th_g, "k": k, "dt": dt,
            "wh": zapfen_auswerten(m, rh, innen, slave), "rh": rh,
            "wg": zapfen_auswerten(m, rg, innen, slave), "rg": rg}


def zapfen_pruefen(z, mu=MU_Z, stumm=False, zusatz=""):
    ok = []
    w0, wh, wg = z["w0"], z["wh"], z["wg"]
    p = w0["sFn"] / (2 * np.pi * R_K * T_Z)
    print(f"     Pressfuge: ΣFn {zahl(w0['sFn'] / 1e3, 3)} kN (p ≈ {zahl(p / MPA, 2)} N/mm²), "
          f"M_grenz = μ Σ Fn r = {zahl(w0['M_grenz'] / 1e3, 5)} kNm, k = {zahl(z['k'] / 1e6, 3)} MNm/rad, "
          f"θ Haften {zahl(z['th_h'] * 1e6, 3)} µrad, θ Gleiten {zahl(z['th_g'] * 1e6, 3)} µrad, "
          f"Rechenzeit {zahl(z['dt'], 1)} s")
    for name, r in (("Z0", z["r0"]), ("Haften", z["rh"]), ("Gleiten", z["rg"])):
        ok.append(check(f"B4 Zapfen {name}{zusatz}: Kontakt konvergiert, nicht vorläufig",
                        r.info.get("contact_converged") and not solver.kontakt_vorlaeufig(r.info),
                        _konv_text(r.info), stumm))
    ok.append(check(f"B4 Zapfen Z0{zusatz}: Pressung über den ganzen Umfang (alle {w0['n']} Knoten geschlossen)",
                    w0["zu"] == w0["n"] > 0, f"{w0['zu']} von {w0['n']} geschlossen", stumm))
    M_h_soll = z["k"] * z["th_h"]
    ok.append(check(f"B4 Zapfen Haften{zusatz}: alle Knoten haften, M = k θ auf 2 % (unter M_grenz)",
                    wh["haft"] == wh["zu"] == wh["n"] and abs(rel(wh["M"], M_h_soll)) <= 2.0,
                    f"haftend {wh['haft']} von {wh['n']}; Soll M {zahl(M_h_soll, 2)} Nm, Ist {zahl(wh['M'], 2)} Nm, "
                    f"Abweichung {zahl(rel(wh['M'], M_h_soll))} %; M_grenz {zahl(wh['M_grenz'], 2)} Nm", stumm))
    ok.append(check(f"B4 Zapfen Gleiten{zusatz}: alle Knoten gleiten", wg["gleit"] == wg["zu"] == wg["n"],
                    f"gleitend {wg['gleit']} von {wg['n']}", stumm))
    ok.append(check(f"B4 Zapfen Gleiten{zusatz}: Grenzmoment M = μ Σ Fn r auf 0,5 %",
                    abs(rel(wg["M"], wg["M_grenz"])) <= 0.5,
                    f"Soll μ Σ Fn r {zahl(wg['M_grenz'], 2)} Nm (ΣFn {zahl(wg['sFn'] / 1e3, 3)} kN), "
                    f"Ist M {zahl(wg['M'], 2)} Nm, Abweichung {zahl(rel(wg['M'], wg['M_grenz']), 3)} %", stumm))
    ok.append(check(f"B4 Zapfen Gleiten{zusatz}: Moment der Lager + Moment der Fuge = 0 (0,1 %)",
                    abs(rel(-wg["M_reib"], wg["M"])) <= 0.1,
                    f"Lager {zahl(wg['M'], 3)} Nm, Fuge {zahl(wg['M_reib'], 3)} Nm", stumm))
    return all(ok)


def test_zapfen():
    print("\n--- B4 Zapfen in Buchse: Reibmoment M = μ Σ Fn r, μ = 0,3 ---")
    zapfen_pruefen(zapfen_rechnen())


def gegenprobe_zapfen():
    """mu in der Rechnung halbiert, Erwartung mit mu 0,3: das Grenzmoment liegt bei der
    Haelfte, die Pruefung muss anschlagen."""
    print("\n--- Gegenprobe B4: Rechnung mit μ/2 (Monkeypatch solve_static), Erwartung mit μ ---")
    with _mu_faktor(0.5):
        z = zapfen_rechnen()
    # die Erwartung rechnet mit dem vollen mu (zapfen_auswerten: mu = MU_Z)
    schlaegt = not zapfen_pruefen(z, stumm=True, zusatz=" [Gegenprobe μ/2]")
    check("Gegenprobe B4: mit halbem μ schlägt die Grenzmoment-Prüfung an", schlaegt)


def main() -> int:
    t_ges = time.perf_counter()
    for t in (test_hertz, gegenprobe_hertz, test_schiefe_ebene, gegenprobe_ebene,
              test_oden_pires, gegenprobe_oden_pires, test_zapfen, gegenprobe_zapfen):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft ohne Ausnahme", False, str(ex)[:160])
    n_ok = sum(1 for _n, ok, _b in RESULTS if ok)
    befunde = [n for n, ok, b in RESULTS if not ok and b]
    fehler = [n for n, ok, b in RESULTS if not ok and not b]
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Prüfungen bestanden, {len(befunde)} bekannte Befunde, "
          f"{len(fehler)} Fehler; Laufzeit {zahl(time.perf_counter() - t_ges, 1)} s")
    for n in befunde:
        print(f"BEFUND: {n}: {BEKANNTE_BEFUNDE[n]}")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
