"""
Gruppe 5 der Befundliste, Teil Meldungen (Befunde C2 bis C9 der Pruefagenten,
09.11.2026). Geaendert ist nur, was gemeldet wird - kein Rechenergebnis.

C2 Wasserdruck auf quadratische Schalen (shell8): die Kontrollsumme ist die
   Summe des Lastvektors (vorher 0,0 kN neben einer richtigen Last). Zweiter
   Weg: 1/2 · ρ · g · h² · b = 61 312,5 N.
C3 Abgebildeter Quader 1 x 0,1 x 0,1 m bei Ziellaenge 20 mm: das Protokoll
   nennt 64 Hexaeder und sagt, dass die Teilung des Koerpers die Netzdichte
   ersetzt (vorher „≈ 3472 Elemente“). Zweiter Weg: 4 · 4 · 4 und die Zahl
   der Elemente im Modell.
C4 Nicht ausgefuehrte Kontaktbedingung: die Warnung nennt Namen und Bezug;
   an eigenen Flaechen „zu weich“ (kein gemeinsamer Knoten), an gemeinsamer
   Flaeche „zu steif“ (25 gemeinsame Knoten; zweiter Weg
   fugen.gruppen_je_knoten und 5 · 5 von Hand).
C5 Schalen fliessen nicht: Hinweis im Protokoll und in der Zusammenfassung
   (16 Schalenelemente = 4 · 4; die Dehnung ist σ/E, also elastisch).
C6 Iterationsbudget 2 am Zugstab mit 82 % der Traglast: „Iterationsgrenze
   erreicht“ statt „Kein Gleichgewicht … Mechanismus“; bei 1,2 f_u bleibt der
   festgelegte Satz (letzter konvergierter Lastanteil 490/588 = 83,3 %).
C7 Keine wissenschaftliche Schreibweise und Komma in Fehlertext, Protokoll
   und Zusammenfassung.
C8 Einfeldtraeger mit Mittelgelenk: „Gelenkkette: … beweglich“ in der
   Modellpruefung, im Fehlertext der Rechnung und in der Suche nach freien
   Bewegungen (vorher „Splitterelemente/Nullsteifigkeit“ bzw. nichts).
   Zweiter Weg: Nullraum der Steifigkeit dicht (zwei Eigenwerte null) und der
   Knick von Hand (K · v = 0).
C9 Steifigkeitsunterschied: WARNUNG ab Faktor 1 000 000 (nicht bei 100 000);
   der Faktor ist das Verhaeltnis der E-Moduln und das der
   Elementsteifigkeiten E·A/L aus der Elementmatrix.

Aufruf:  python -m tests.test_gruppe5_meldungen
"""
import contextlib
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

#: wissenschaftliche Schreibweise (2.4e+00, 1e-06, 4.9e-03)
WISS = re.compile(r"\d(?:[.,]\d+)?[eE][+-]?\d+")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def versuch(name, fn):
    """Eine Pruefung, die am alten Stand auch an einer fehlenden Funktion
    scheitern darf: die Ausnahme zaehlt als FAIL, die Zaehlung bleibt gleich."""
    try:
        ok, detail = fn()
    except Exception as ex:                # noqa: BLE001
        ok, detail = False, f"{type(ex).__name__}: {ex}"[:200]
    return check(name, ok, detail)


def _still(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


# --------------------------------------------------------------------------
# C2 Wasserdruck, Kontrollsumme an shell8
# --------------------------------------------------------------------------
def test_c2():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher, solver
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    m = Model("Wand")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    b = m.nn
    m.add_nodes(np.asarray([[0, 0, 0], [2, 0, 0], [2, 0, 3], [0, 0, 3]], float))
    lin = []
    for i in range(4):
        m.add_line(f"W_L{i}", [b + i, b + (i + 1) % 4])
        lin.append(f"W_L{i}")
    m.add_flaeche("W", lin, material="S235", dicke="t10")
    m.netz.ordnung = 2
    m.netz.ziellaenge = 0.25
    _still(mesher.modell_vernetzen, m, log=[], workers=1)
    wd = Wasserdruck("W1", flaechen=["W"], h_ow=2.5, verfahren="analytisch", seite=1, richtung=None)
    kw = lasten_erzeugen(m, wd)
    F = np.asarray(solver.case_loads(m, {wd.lastfall: 1.0}, None)[0], float).reshape(-1, 6)
    summe = F[:, :3].sum(axis=0)
    kontrolle = np.asarray(kw["kontrolle"]["F"], float)
    soll = 0.5 * 1000.0 * 9.81 * 2.5 ** 2 * 2.0
    typen = sorted({e.typ for e in m.elements})
    check("C2 shell8: Kontrollsumme = Summe des Lastvektors (nicht 0,0 kN)",
          typen == ["shell8"] and np.linalg.norm(kontrolle) > 0
          and np.allclose(kontrolle, summe, rtol=1e-9, atol=1e-6) and int(kw["kontrolle"]["n"]) > 0,
          f"{typen}: Kontrollsumme {np.round(kontrolle, 1)} N, n = {kw['kontrolle']['n']}, "
          f"Lastvektor {np.round(summe, 1)} N")
    check("C2 zweiter Weg: Kontrollsumme = ½·ρ·g·h²·b = 61 312,5 N (auf 0,1 %)",
          abs(np.linalg.norm(kontrolle) / soll - 1.0) < 1e-3,
          f"{np.linalg.norm(kontrolle):.1f} N gegen {soll:.1f} N "
          f"({(np.linalg.norm(kontrolle) / soll - 1) * 100:+.3f} %)")


# --------------------------------------------------------------------------
# C3 abgebildeter Quader, Protokoll der Netzdichte
# --------------------------------------------------------------------------
def _quader(m, tag, x0, x1, y0, y1, z0, z1, mat="S235", koerper=True):
    X, Y, Z = [x0, x1], [y0, y1], [z0, z1]
    n = {(i, j, k): m.add_node(X[i], Y[j], Z[k]) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    L = {}

    def lin(a, c):
        key = tuple(sorted((a, c)))
        if key not in L:
            L[key] = f"{tag}L{len(L)}"
            m.add_line(L[key], [n[a], n[c]])
        return L[key]

    def flaeche(name, ecken):
        m.add_flaeche(tag + name, [lin(ecken[q], ecken[(q + 1) % 4]) for q in range(4)], material=mat)
        return tag + name
    F = {"x0": flaeche("x0", [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)]),
         "x1": flaeche("x1", [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
         "y0": flaeche("y0", [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
         "y1": flaeche("y1", [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)]),
         "z0": flaeche("z0", [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]),
         "z1": flaeche("z1", [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])}
    if koerper:
        m.add_koerper(tag, list(F.values()), material=mat)
    return F


def test_c3():
    from statik3d.model import Model, Material
    from statik3d import mesher
    m = Model()
    m.add_material(Material.steel("S235"))
    _quader(m, "Q", 0, 1.0, 0, 0.1, 0, 0.1)
    m.add_load_case("LF1")
    m.netz.ziellaenge = 0.02
    m.netz.dichte = "eigene"
    m.netz.ordnung = 1
    m.netz.sweep = "aus"
    log = []
    _still(mesher.modell_vernetzen, m, log, workers=1)
    n_el = len(m.elements)
    typen = sorted({e.typ for e in m.elements})
    zeilen = [z for z in log if "Volumen Q" in z]
    angekuendigt = [int(x.replace(" ", "")) for z in zeilen
                    for x in re.findall(r"≈ ?(\d[\d ]*) Elemente", z)]
    vern = [z for z in zeilen if "Hexaeder" in z]
    check("C3 Protokoll kündigt keine Elementzahl an, die nicht entsteht (vorher ≈ 3472)",
          n_el == 64 == 4 * 4 * 4 and typen == ["hex8"] and all(a == n_el for a in angekuendigt)
          and any("ersetzt die Netzdichte" in z for z in zeilen),
          f"entstanden {n_el} {typen}, angekündigt {angekuendigt or 'nichts'}; "
          + "; ".join(z.strip()[:150] for z in zeilen if "Netzdichte Volumen" in z))
    check("C3 Vernetzer nennt 64 Hexaeder (4 x 4 x 4) und „nicht nach der Netzdichte“",
          len(vern) == 1 and "64 Hexaeder (4 x 4 x 4)" in vern[0] and "nicht nach der Netzdichte" in vern[0],
          (vern[0].strip()[:170] if vern else "keine Zeile"))


# --------------------------------------------------------------------------
# C4 nicht ausgefuehrte Kontaktbedingung
# --------------------------------------------------------------------------
def _c4_modell(gemeinsam):
    from statik3d.model import Model, Material
    m = Model()
    m.add_material(Material.steel("S235"))
    z = [0]

    def linie(a, c):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, c], "polyline")
        return f"L{z[0]}"

    def ringe(ecken):
        return ([linie(ecken[i], ecken[(i + 1) % 4]) for i in range(4)],
                [linie(ecken[4 + i], ecken[4 + (i + 1) % 4]) for i in range(4)],
                [linie(ecken[i], ecken[4 + i]) for i in range(4)])
    B, H = 0.2, 0.1
    E = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], float) * [B, B, H]
    m.add_nodes(E)
    R0, R1, V = ringe(list(range(8)))
    m.add_flaeche("AB", R0, material="S235")
    m.add_flaeche("AD", R1, material="S235")
    for i in range(4):
        m.add_flaeche(f"AM{i}", [R0[i], V[(i + 1) % 4], R1[i], V[i]], material="S235")
    m.add_koerper("A", ["AB", "AD"] + [f"AM{i}" for i in range(4)], material="S235")
    if gemeinsam:
        m.add_nodes(E[4:] + [0, 0, H])
        S1 = [linie(8 + i, 8 + (i + 1) % 4) for i in range(4)]
        V2 = [linie(4 + i, 8 + i) for i in range(4)]
        m.add_flaeche("OD", S1, material="S235")
        for i in range(4):
            m.add_flaeche(f"OM{i}", [R1[i], V2[(i + 1) % 4], S1[i], V2[i]], material="S235")
        m.add_koerper("O", ["AD", "OD"] + [f"OM{i}" for i in range(4)], material="S235")
    else:
        m.add_nodes(E + [0, 0, H])
        R0, R1, V = ringe(list(range(8, 16)))
        m.add_flaeche("OB", R0, material="S235")
        m.add_flaeche("OD", R1, material="S235")
        for i in range(4):
            m.add_flaeche(f"OM{i}", [R0[i], V[(i + 1) % 4], R1[i], V[i]], material="S235")
        m.add_koerper("O", ["OB", "OD"] + [f"OM{i}" for i in range(4)], material="S235")
    m.netz.ziellaenge = 0.05
    return m


def _c4_lauf(gemeinsam):
    from statik3d import mesher, fugen
    m = _c4_modell(gemeinsam)
    kb = m.add_kontaktbedingung("Fuge oben", koerpernamen=["O"])
    kb.standard_anwenden("Reibungsfrei")
    log = []
    _still(mesher.modell_vernetzen, m, log, workers=1)
    warn = [z for z in log if "nicht ausgeführt" in z]
    gem = sum(1 for s in fugen.gruppen_je_knoten(m).values() if len(s) > 1)
    return m, kb, warn, gem


def test_c4():
    m, kb, warn, gem = _c4_lauf(False)
    check("C4 eigene Flächen: Warnung nennt Namen und Bezug, Folge „zu weich“ (0 gemeinsame Knoten)",
          len(warn) == 1 and "„Fuge oben“ (gelöster Körper O)" in warn[0] and "(zu weich)" in warn[0]
          and "zu steif" not in warn[0] and gem == 0 and not kb.ausgefuehrt,
          f"gemeinsame Knoten {gem}; " + (warn[0].strip()[:230] if warn else "keine Warnung"))
    versuch("C4 Zustand der Bedingung: „hier ohne Verbindung (zu weich)“ statt „hier zu steif“",
            lambda: (kb.zustand(m) == "nicht ausgeführt - hier ohne Verbindung (zu weich)"
                     and kb.verbindung(m) == 0 == gem, kb.zustand(m)))
    m, kb, warn, gem = _c4_lauf(True)
    check("C4 gemeinsame Fläche: Warnung mit Namen, 25 gemeinsame Knoten (= 5 · 5), „zu steif“",
          len(warn) == 1 and "„Fuge oben“ (gelöster Körper O)" in warn[0]
          and "teilen im Netz 25 Knoten" in warn[0] and "(zu steif)" in warn[0]
          and gem == 25 == (round(0.2 / 0.05) + 1) ** 2 and kb.zustand(m) == "nicht ausgeführt - hier zu steif",
          f"gemeinsame Knoten {gem}; " + (warn[0].strip()[:230] if warn else "keine Warnung"))


# --------------------------------------------------------------------------
# C5 Schalen fliessen nicht
# --------------------------------------------------------------------------
def test_c5():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import solver, plastizitaet as pl
    E, fy = 210e9, 355e6
    m = Model("Schale")
    m.add_material(Material("S", E=E, nu=0.3, rho=0.0, fy=fy, fu=490e6))
    m.add_shell_prop(ShellProp("t10", 0.01))
    n = 4
    ids = {(i, j): m.add_node(i / n, j / n, 0.0) for i in range(n + 1) for j in range(n + 1)}
    for i in range(n):
        for j in range(n):
            m.add_element("shell4", [ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1]], "S", "t10")
    for j in range(n + 1):
        m.fix(ids[0, j], [0, 2, 3, 4, 5])
        for i in range(1, n + 1):
            m.fix(ids[i, j], [2, 3, 4, 5])
    m.fix(ids[0, 0], [1])
    s = 1.5 * fy
    for j in range(n + 1):
        m.load_node(ids[n, j], Fx=s * 0.01 * 1.0 * (0.5 if j in (0, n) else 1.0) / n)
    m.plastizitaet = pl.Plastizitaet(an=True)
    r = _still(solver.solve_static, m, workers=1)
    I = r.info.get("plastizitaet") or {}
    U = np.asarray(r.u).reshape(-1, 6)
    eps = float(U[[ids[n, j] for j in range(n + 1)], 0].mean())
    schalen = sum(1 for e in m.elements if e.typ.startswith("shell"))
    hinweis = [z for z in (I.get("log") or []) if "Schalen werden elastisch gerechnet" in z]
    check("C5 Protokoll: Hinweis „Schalen werden elastisch gerechnet (16 Schalenelemente)“",
          len(hinweis) == 1 and "(16 Schalenelemente)" in hinweis[0] and schalen == 16 == n * n
          and (I.get("elastisch") or {}).get("schalen") == 16 and abs(eps / (s / E) - 1.0) < 1e-6,
          f"{schalen} Schalenelemente, ε = {eps * 100:.4f} % (σ/E = {s / E * 100:.4f} %); "
          + (hinweis[0].strip()[:120] if hinweis else "kein Hinweis"))
    zus = [z for z in r.summary().splitlines() if "elastisch gerechnet" in z]
    check("C5 Zusammenfassung: dieselbe Zeile als „Hinweis“",
          len(zus) == 1 and zus[0].startswith("Hinweis") and "(16 Schalenelemente)" in zus[0],
          (zus[0].strip()[:120] if zus else "keine Zeile"))


# --------------------------------------------------------------------------
# C6 Iterationsgrenze statt Traglast
# --------------------------------------------------------------------------
def _zugstab(sigma, plast):
    from tests import pruefkoerper as pk
    L, b = 0.4, 0.1
    m, _ids = pk.quader("hex8", 4, 2, 2, L, b, b, fy=355e6)
    mat = m.materials["S"]
    mat.fu = 490e6
    mat.verfestigung = None
    X = np.asarray(m.nodes, float)
    for k in range(m.nn):
        fx = [d for d in (0, 1, 2) if abs(X[k, d]) < 1e-12]
        if fx:
            m.fix(int(k), fx)
    seiten = pk.randseiten(m, lambda P: bool(np.all(np.abs(P[:, 0] - L) < 1e-12)))
    pk.spannung_auf_seiten(m, seiten, lambda x: (sigma, 0.0, 0.0))
    m.plastizitaet = plast
    return m


def _traglast_text(sigma, **kw):
    from statik3d import solver, plastizitaet as pl
    r = _still(solver.solve_static, _zugstab(sigma, pl.Plastizitaet(an=True, **kw)), workers=1)
    I = r.info.get("plastizitaet") or {}
    return bool(I.get("konvergiert")), str((I.get("traglast") or {}).get("text") or "")


def test_c6():
    from statik3d import plastizitaet as pl

    def entscheidung():
        f = pl._iterationsgrenze
        faellt = f([0.25, 28.6, 3.0, 0.4], 4, 4, None)
        steht = f([467.6] * 25, 25, 25, None)
        mech = f([0.25, 28.6, 3.0, 0.4], 4, 4, {"knoten": 1})
        klein = f([0.25, 28.6], 2, 2, None)
        return (bool(faellt and faellt["faellt"]) and steht is None and mech is None
                and bool(klein) and not klein["faellt"],
                f"fällt {faellt}, steht {steht}, Mechanismus {mech}, Budget 2 {klein}")
    versuch("C6 Entscheidung: fallender Rest = Iterationsgrenze, stehende Änderung/Mechanismus nicht",
            entscheidung)
    konv2, t2 = _traglast_text(400e6, laststufen=3, iterationen=2)
    konv3, _t3 = _traglast_text(400e6, laststufen=3, iterationen=3)
    check("C6 Budget 2 bei 82 % der Traglast: „Iterationsgrenze erreicht“, Zustand bleibt nicht konvergiert",
          not konv2 and konv3 and t2.startswith("Iterationsgrenze erreicht")
          and "mehr Iterationen oder mehr Laststufen wählen" in t2 and "Kein Gleichgewicht gefunden" not in t2
          and "Letzter konvergierter Lastanteil" in t2,
          f"400/490 = {400 / 490 * 100:.0f} % der Traglast, mit 3 Schritten konvergiert: {konv3}; {t2[:150]}")
    konv, t = _traglast_text(588e6, laststufen=3, iterationen=25)
    anteil = re.search(r"Letzter konvergierter Lastanteil: ([\d,]+) %", t)
    wert = float(anteil.group(1).replace(",", ".")) if anteil else float("nan")
    check("C6 1,2 f_u: festgelegter Satz bleibt, Lastanteil = 490/588 (auf 1 %-Punkt); kein Text mit Punkt/e",
          not konv and t.startswith("Kein Gleichgewicht gefunden bei Laststufe")
          and "Iterationsgrenze" not in t and abs(wert - 490.0 / 588.0 * 100.0) < 1.0
          and t2.startswith("Iterationsgrenze") and not WISS.search(t + t2),
          f"Lastanteil {wert} % gegen {490 / 588 * 100:.2f} %; {t[:110]}")


# --------------------------------------------------------------------------
# C8 Gelenkkette (und C7 am Fehlertext)
# --------------------------------------------------------------------------
def _traeger(n=4, L=5.0):
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    m = Model("K")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850, fy=355e6, fu=490e6))
    sec = Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010)
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S355", "HEA200", (0, 0, 0), (L, 0, 0), n=n)
    return m, ids, sec


def _fall_b(**last):
    """Einfeldtraeger 5 m, vier Stabelemente, Gelenk (φ_y, φ_z frei) in Feldmitte."""
    m, ids, sec = _traeger()
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2])
    m.add_hinge("G", end=1, phiy="free", phiz="free")
    m.apply_hinge(1, "G")
    m.load_node(ids[2], **last)
    return m, ids, sec


def _fehlertext(m):
    from statik3d import solver
    try:
        _still(solver.solve_static, m, workers=1)
    except Exception as ex:                # noqa: BLE001
        return str(ex)
    return ""


def test_c8():
    from statik3d import singular as sg, assemble as asm, solver
    m, ids, _sec = _fall_b(Fz=-10000.0)
    z = m.check()
    kette = [x for x in z if "Gelenkkette:" in x]
    check("C8 Modellprüfung: WARNUNG „Gelenkkette: Stabelement E1 … an Knoten K2 ist beweglich“",
          len(kette) == 1 and kette[0].startswith("WARNUNG: Gelenkkette: Stabelement E1 mit Stabendgelenk "
                                                  "an Knoten K2 ist beweglich")
          and "kinematische Kette" in kette[0] and not any(x.startswith("FEHLER") for x in z),
          (kette[0][:120] if kette else f"check(): {z}"))
    text = _fehlertext(m)
    zeilen = text.splitlines()
    check("C8 Fehlertext der Rechnung: FEHLER „Gelenkkette: …“ statt Splitterelemente/Nullsteifigkeit",
          any(x.startswith("FEHLER: Gelenkkette: Stabelement E1") for x in zeilen)
          and "Splitterelemente" not in text and "Nullsteifigkeit" not in text,
          " | ".join(x[:90] for x in zeilen[1:3]))
    check("C7 Fehlertext ohne wissenschaftliche Schreibweise, Residuum und Schranke mit Komma",
          bool(text) and not WISS.search(text) and re.search(r"Residuum \d+(,\d+)?, Schranke 0,000001", text),
          zeilen[0][90:200] if zeilen else "kein Fehler")

    def zweiter_weg():
        # dichter Nullraum der Steifigkeit und der Knick von Hand
        K = asm.stiffness(m, 1, None)
        fixed, _vals, _auto = asm.gesperrte_und_automatische(m, K)
        frei = np.where(~fixed)[0]
        Kf = K.tocsc()[frei][:, frei].toarray()
        w = np.linalg.eigvalsh(Kf)
        null = int((np.abs(w) < 1e-9 * w[-1]).sum())
        # Hand: w(x) = θ·x links, θ·(5 − x) rechts vom Gelenk bei x = 2,5 m;
        # Knotendrehung φ_y = −dw/dx; der Gelenkknoten dreht mit dem rechten Stab
        theta = 1.0
        v = np.zeros((m.nn, 6))
        for k in ids:
            x = float(m.nodes[k][0])
            v[k, 2] = theta * x if x <= 2.5 else theta * (5.0 - x)
            v[k, 4] = -theta if x < 2.5 - 1e-9 else theta
        rest = float(np.linalg.norm((K @ v.ravel())[frei])) / (float(np.abs(K.diagonal()).max()) * float(np.abs(v).max()))
        hand = sg.gelenkkette(m, v.ravel())
        befund = sg.gelenkketten(m)
        gel = sorted({(g[0], g[1]) for g in befund[0].gelenke}) if befund else []
        gel_hand = sorted({(g[0], g[1]) for g in hand["gelenke"]}) if hand else []
        return (null == 2 and rest < 1e-12 and len(befund) == 1 and gel == gel_hand == [(1, ids[2])]
                and not np.any(fixed.reshape(-1, 6)[:, :6][v != 0]),
                f"Eigenwerte null: {null} (kleinste {w[0]:.1e}, {w[1]:.1e}, dann {w[2]:.0f}; größter {w[-1]:.3g}), "
                f"‖K·v_Hand‖ bezogen {rest:.1e}, Gelenk im Befund {gel}, von Hand {gel_hand}")
    versuch("C8 zweiter Weg: Nullraum hat Dimension 2, K·v_Hand = 0, dasselbe Gelenk (E1, K2)", zweiter_weg)

    def freie_bewegungen():
        sing = list(sg.restfreiheiten(m)) + sg.gelenkketten(m)
        sing = sg.auswerten(m, sing, asm.load_vector(m, m.case()))
        x = sg.wichtigste(sing)
        quelle = open(os.path.join(os.path.dirname(os.path.abspath(sg.__file__)), "gui", "main.py"),
                      encoding="utf-8").read()
        return (len(x) == 1 and x[0].text.startswith("Gelenkkette:") and x[0].kraft > 0
                and "kN gehen in dieser Bewegung ins Nichts" in x[0].befund()
                and "sg.gelenkketten(self.model)" in quelle,
                f"{len(sg.restfreiheiten(m))} starre Restfreiheiten; {x[0].text[:60] if x else '-'}; "
                f"{x[0].befund()[:50] if x else ''}")
    versuch("C8 „Freie Bewegungen suchen“: die Kette steht in der Liste, mit Befund zur Last",
            freie_bewegungen)

    def gegenprobe():
        # tragfaehig trotz Gelenk: Gerbertraeger auf drei Lagern - keine Meldung;
        # Fall B unter Laengskraft rechnet weiter: u_x = F·x/(E·A)
        g, gi, _s = _traeger(n=8, L=10.0)
        g.fix(gi[0], [0, 1, 2, 3])
        g.fix(gi[4], [1, 2])
        g.fix(gi[-1], [1, 2])
        g.add_hinge("G", end=1, phiy="free", phiz="free")
        g.apply_hinge(5, "G")
        b, bi, sec = _fall_b(Fx=10000.0)
        r = _still(solver.solve_static, b, workers=1)
        ux = float(np.asarray(r.u).reshape(-1, 6)[bi[2], 0])
        hand = 10000.0 * 2.5 / (210e9 * sec.A)
        zb = b.check()
        return (not [x for x in g.check() if "Gelenkkette" in x] and sg.gelenkketten(g) == []
                and abs(ux / hand - 1.0) < 1e-9 and abs(ux / 2.331980784478336e-05 - 1.0) < 1e-9
                and any(x.startswith("WARNUNG: Gelenkkette:") for x in zb)
                and not any(x.startswith("FEHLER") for x in zb),
                f"Gerberträger: {len(sg.gelenkketten(g))} Ketten; Längskraft: u_x {ux * 1e6:.4f} µm "
                f"(Hand {hand * 1e6:.4f} µm, alter Stand 23,3198 µm)")
    versuch("C8 Gegenprobe: Gerberträger ohne Meldung; Kette ohne Last in ihrer Richtung rechnet weiter",
            gegenprobe)

    def alte_datei():
        # Ergebnisdateien von vor C8 tragen die Felder gelenke/bezogene_energie
        # nicht; Pickle setzt nur das Gespeicherte (Nachkontrolle 11.11.2026:
        # AttributeError beim Lesen einer alten Ergebnisdatei in
        # test_umstellung_lf_lk). Hier wie pickle: __setstate__, sonst __dict__.
        import pickle
        s = sg.Singularitaet(art="gleitet", knoten=[1, 2], text="alt")
        zustand = dict(s.__dict__)
        del zustand["gelenke"], zustand["bezogene_energie"]
        alt = object.__new__(sg.Singularitaet)
        setzen = getattr(alt, "__setstate__", None)
        if setzen is not None:
            setzen(zustand)
        else:
            alt.__dict__.update(zustand)
        wieder = pickle.loads(pickle.dumps(alt))
        return (alt.gelenke == [] and alt.bezogene_energie == 0.0 and alt.text == "alt"
                and wieder.gelenke == [] and wieder.knoten == [1, 2],
                f"gelenke {alt.gelenke!r}, bezogene_energie {alt.bezogene_energie!r}")
    versuch("C8 alte Ergebnisdatei ohne die neuen Felder: Vorgabewerte statt AttributeError", alte_datei)


# --------------------------------------------------------------------------
# C9 Steifigkeitsunterschied
# --------------------------------------------------------------------------
def _kragarm(f):
    """Kragarm 5 m, fuenf Stabelemente, Element 2 mit dem f-fachen E-Modul."""
    from statik3d.model import Material
    m, ids, sec = _traeger(n=5)
    m.materials["S355"].rho = 0.0
    m.add_material(Material("X", E=210e9 * f, nu=0.3, rho=0, fy=355e6, fu=490e6))
    m.elements[2].mat = "X"
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-20000.0)
    return m, ids, sec


def test_c9():
    from statik3d import diagnose as dg, assemble as asm, solver
    m, ids, sec = _kragarm(1e6)
    z = m.check()
    warn = [x for x in z if "Steifigkeitsunterschied" in x]

    def faktor():
        s = dg.steifigkeitsunterschied(m)
        # zweiter Weg: Dehnsteifigkeit aus den Elementmatrizen, dritter: E-Moduln
        k2 = float(asm.beam_local(m, m.elements[2])[0][0, 0])
        k0 = float(asm.beam_local(m, m.elements[0])[0][0, 0])
        e = m.materials["X"].E / m.materials["S355"].E
        return (abs(s["faktor"] / (k2 / k0) - 1.0) < 1e-9 and abs(s["faktor"] / e - 1.0) < 1e-9
                and s["steif"][0] == 2 and s["weich"][0] != 2
                and len(warn) == 1 and warn[0].startswith(
                    "WARNUNG: Steifigkeitsunterschied Faktor 1 000 000 zwischen Element 2 (beam, "
                    "Werkstoff „X“) und Element 0 (beam, Werkstoff „S355“)")
                and not WISS.search(warn[0]),
                f"Faktor {s['faktor']:.6g}, Elementmatrizen {k2 / k0:.6g}, E-Moduln {e:.6g}; "
                + (warn[0][:110] if warn else "keine Warnung"))
    versuch("C9 WARNUNG „Steifigkeitsunterschied Faktor 1 000 000 zwischen Element 2 … und Element 0 …“",
            faktor)

    def schwelle():
        m5, _i, _s = _kragarm(1e5)
        mw, _i, _s = _kragarm(1e-6)
        w5 = [x for x in m5.check() if "Steifigkeitsunterschied" in x]
        ww = [x for x in mw.check() if "Steifigkeitsunterschied" in x]
        return (not w5 and len(warn) == 1 and len(ww) == 1 and "und Element 2 (beam, Werkstoff „X“)" in ww[0]
                and dg.STEIFIGKEITSUNTERSCHIED_WARNUNG == 1e6,
                f"Faktor 100 000: {len(w5)} Warnungen; 1 000 000: {len(warn)}; weich 1/1 000 000: {len(ww)}")
    versuch("C9 Schwelle: keine Warnung bei Faktor 100 000, eine ab 1 000 000 (steif wie weich)", schwelle)

    def ergebnis():
        r = _still(solver.solve_static, m, workers=1)
        uz = float(np.asarray(r.u).reshape(-1, 6)[ids[-1], 2])
        # Hand (Bernoulli, Arbeitssatz): w = P/EI · ∫ (5 − x)² g dx, g = 1/f in 2..3 m
        EI, P = 210e9 * sec.Iy, 20000.0
        hand = P / EI * ((5.0 ** 3 - 3.0 ** 3) / 3.0 + (3.0 ** 3 - 2.0 ** 3) / 3.0 / 1e6 + 2.0 ** 3 / 3.0)
        return (abs(uz / -0.09673269580782497 - 1.0) < 1e-9 and abs(-uz / hand - 1.0) < 0.01
                and len(warn) == 1 and not any(x.startswith("FEHLER") for x in z),
                f"u_z {uz * 1e3:.4f} mm (alter Stand −96,7327 mm, Hand ohne Schub {-hand * 1e3:.4f} mm)")
    versuch("C9 die Warnung sperrt nicht: Faktor 1 000 000 rechnet wie vorher (u_z auf 1 % der Handrechnung)",
            ergebnis)

    def fehlertext():
        m9, _i, _s = _kragarm(1e9)
        t = _fehlertext(m9)
        zl = t.splitlines()
        return (bool(t) and zl[-1].startswith("WARNUNG: Steifigkeitsunterschied Faktor 1 000 000 000 zwischen")
                and any(x.startswith("FEHLER:") for x in zl[1:-1]) and not WISS.search(t),
                " | ".join(x[:70] for x in zl[1:]))
    versuch("C9/C7 Faktor 10⁹: der Fehlertext nennt die Warnung nach dem Befund, ohne e-Schreibweise",
            fehlertext)


# --------------------------------------------------------------------------
# C7 Zusammenfassung und Protokoll
# --------------------------------------------------------------------------
def test_c7():
    from statik3d import solver, plastizitaet as pl
    m = _zugstab(400e6, pl.Plastizitaet(an=True, laststufen=3, iterationen=25))
    r = _still(solver.solve_static, m, workers=1)
    s = r.summary()
    vm = float(np.nanmax(r.node_vm)) / 1e6
    zeile = [x for x in s.splitlines() if x.startswith("max. Vergleichsspannung")]
    summe = [x for x in s.splitlines() if x.startswith("Summe Auflagerkräfte")]
    R = np.asarray(r.reactions, float)[:, :3].sum(axis=0)
    zahlen = [float(x.replace(" ", "").replace(",", ".").replace("−", "-"))
              for x in re.findall(r"[-−]?\d[\d ]*(?:,\d+)?", summe[0].split(":", 1)[1])] if summe else []
    check("C7 Zusammenfassung: Vergleichsspannung und Summe der Auflagerkräfte mit Komma",
          len(zeile) == 1 and f"{vm:.2f}".replace(".", ",") + " MPa" in zeile[0]
          and len(summe) == 1 and "." not in summe[0].split(":", 1)[1] and ";" in summe[0]
          and len(zahlen) == 3 and np.allclose(zahlen, R, atol=0.06) and abs(R[0] + 400e6 * 0.01) < 1.0,
          f"{zeile[0].strip()[:60] if zeile else '-'} | {summe[0].strip() if summe else '-'} "
          f"(ΣR_x {R[0]:.1f} N, Hand −σ·A = {-400e6 * 0.01:.0f} N)")
    log = "\n".join((r.info.get("plastizitaet") or {}).get("log") or [])
    check("C7 Protokoll der Plastizität und Zusammenfassung ohne wissenschaftliche Schreibweise",
          bool(log) and not WISS.search(log) and not WISS.search(s)
          and not re.search(r"\d\.\d", "\n".join(x for x in log.splitlines() if "Laststufe" in x)),
          (WISS.search(log + s).group(0) if WISS.search(log + s) else
           next((x.strip()[:110] for x in log.splitlines() if "Laststufe" in x), "")))


def main():
    for t in (test_c2, test_c3, test_c4, test_c5, test_c6, test_c8, test_c9, test_c7):
        try:
            t()
        except Exception as ex:            # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft durch", False, f"{type(ex).__name__}: {ex}"[:200])
    n = sum(1 for _name, ok in RESULTS if ok)
    print(f"\nErgebnis: {n}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
