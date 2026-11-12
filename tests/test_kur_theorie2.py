"""
Kur der Befunde 31, 34, 43, 13 und 35 der Pruefagenten (11.11.2026) - Theorie
II. Ordnung an Staeben (eingefuehrt mit b8b4cd1 und 13a1745).

31 Stabendkraefte nach Theorie II. Ordnung an einem Balken mit Stabendgelenk
   oder Federgelenk und Feldlast: _post_chunk liess k_G auf die Stabenden
   wirken, in denen die Kondensation den Lastanteil eingerechnet hat; das
   Gleichungssystem hat K_G = C^T k_G C ohne ihn. Einfeldtraeger 6 m, links
   eingespannt, rechts Stabendgelenk (Knotendrehung gehalten), q = 5 kN/m,
   Druck 0,6 N_cr, ein Element: Stab My(0) 27,04 gegen Lager 22,50 kNm.
   Jetzt gleich. Erster Weg: Gleichgewicht am Lager und am freien Knoten.
   Zweiter Weg: bei einem Element sind alle Knoten-FHG gehalten, das System
   hat keinen Anteil aus k_G - von Hand q L²/8 = 22,50 kNm; und die fein
   unterteilte Rechnung (64 Elemente) trifft mit Element-Gelenk dieselben
   Werte wie mit der Freigabe am Knoten.
34 Der Nachzug „Federgelenk k = 0“ lief bei jedem from_dict und trug in eine
   aktuelle Datei Gelenke ein: Gelenk mit apply_hinge(end=1) ans andere Ende
   gelegt -> Einspannmoment −6,25 auf 0; Gelenk am Element entfernt ->
   −4,69 auf 0. Jetzt nur fuer eine Datei ohne die Kennung federgelenk_null.
43 Der Nachzug verwarf die alte Ergebnisdatei („seit der Rechnung geändert:
   Elementeigenschaften“). Jetzt passt sie gegen den Stand davor und hat den
   Status „Ergebnis möglicherweise betroffen – neu rechnen“ (Stand 17).
13/35 Meldungen zaehlen Elemente ab 0 wie die Tabellen (C13): Hinweis
   „α_cr: Stabteilung zu grob“, Name des Gelenkbalkens im Einzelknicken,
   Ladehinweis des Nachzugs.

Aufruf:  python -m tests.test_kur_theorie2
"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
I = 1e-4
EI = E * I
L = 6.0
Q = 5e3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _modell(A=1.0):
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05))
    return m


def _einfeld(n, art):
    """Einfeldtraeger links eingespannt; rechts gelenkig - ``art``:
    "gelenk" Stabendgelenk phiy/phiz am letzten Element (Knotendrehung
    gehalten), "freigabe" die Knotendrehung frei (ohne Element-Gelenk),
    "feder" Drehfeder k = 2 E I / L am Anfang des ersten Elements."""
    from statik3d import solver
    m = _modell()
    ids = [m.add_node(L * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    m.fix(ids[0], "all")
    if art == "gelenk":
        m.add_hinge("GE", end=1, phiy="free", phiz="free")
        m.apply_hinge(els[-1], "GE")
        m.fix(ids[-1], [1, 2, 3, 4, 5])
    elif art == "feder":
        m.add_hinge("GA", end=0, phiy=2 * EI / L)
        m.apply_hinge(els[0], "GA")
        m.fix(ids[-1], [1, 2, 3])
    else:
        m.fix(ids[-1], [1, 2, 3])
    ncr = (math.pi ** 2 if art == "feder" else 20.19) * EI / L ** 2
    m.load_node(ids[-1], Fx=-0.6 * ncr)
    for e in els:
        m.load_beam(e, qz=-Q)
    m.load_cases["LF1"].theorie = "II"
    m.design.imperfektionen = False
    r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
    b0, bl = r.beam_forces[els[0]], r.beam_forces[els[-1]]
    return dict(My0=float(b0["My"][0]), RM=-float(r.reactions[ids[0], 4]), Vz0=-float(b0["Vz"][0]),
                Rz0=float(r.reactions[ids[0], 2]), VzL=float(bl["Vz"][-1]), RzL=float(r.reactions[ids[-1], 2]),
                MyL=float(bl["My"][-1]))


def _einspann_gelenk_analytisch() -> float:
    """Lagermoment des links eingespannten, rechts gelenkigen Einfeldtraegers
    mit Druck P = 0,6 N_cr und q nach Theorie II. Ordnung: w = A + B x +
    C cos kx + D sin kx + q x² / (2 P), k² = P / (E I); w(0) = w'(0) = 0,
    w(L) = w''(L) = 0; M(0) = E I w''(0) (Betrag)."""
    import numpy as np
    P = 0.6 * 20.19 * EI / L ** 2
    k = math.sqrt(P / EI)
    q = Q                                     # Last nach unten, Betrag
    Amat = np.array([
        [1, 0, 1, 0],
        [0, 1, 0, k],
        [1, L, math.cos(k * L), math.sin(k * L)],
        [0, 0, -k ** 2 * math.cos(k * L), -k ** 2 * math.sin(k * L)]])
    rhs = -np.array([0.0, 0.0, q * L ** 2 / (2 * P), q / P])
    A_, B_, C_, D_ = np.linalg.solve(Amat, rhs)
    return abs(EI * (-k ** 2 * C_ + q / P))


def test_31_gleichgewicht():
    d = _einfeld(1, "gelenk")
    check("31 Stabendgelenk + Feldlast, 1 Element: Stab My(0) = Lagermoment (vorher 27,04 gegen 22,50 kNm)",
          abs(d["My0"] - d["RM"]) < 1e-6 * abs(d["RM"]),
          f"Stab {d['My0'] / 1e3:.4f}  Lager {d['RM'] / 1e3:.4f} kNm")
    check("… Vz(0) = Rz am Lager (vorher 19,51 gegen 18,75 kN), Vz(L) = Rz rechts, My(L) = 0 am Gelenk",
          abs(d["Vz0"] - d["Rz0"]) < 1e-6 * d["Rz0"] and abs(d["VzL"] - d["RzL"]) < 1e-6 * d["RzL"]
          and abs(d["MyL"]) < 1e-6,
          f"Vz(0) {d['Vz0'] / 1e3:.4f}/{d['Rz0'] / 1e3:.4f}, Vz(L) {d['VzL'] / 1e3:.4f}/{d['RzL'] / 1e3:.4f} kN, "
          f"My(L) {d['MyL']:.2e}")
    # Bis zum 12.11.2026 lautete der zweite Weg „alle Knoten-FHG gehalten,
    # kein Anteil aus K_G - von Hand q L²/8 = 22,500 kNm“: das war das
    # Ergebnis eines Elements ohne Teilung, nicht das nach Theorie II.
    # Ordnung. Seit der internen Stabteilung (statik3d.stabteilung) gilt die
    # Loesung der Differentialgleichung (_einspann_gelenk_analytisch).
    soll = _einspann_gelenk_analytisch()
    check("… zweiter Weg: Differentialgleichung EI w^IV + P w'' = q, eingespannt/gelenkig - "
          f"{soll / 1e3:.3f} kNm (auf 0,1 %; ohne Stabteilung waren es 22,500)",
          abs(d["My0"] - soll) < 1e-3 * soll, f"{d['My0'] / 1e3:.4f} kNm")
    d2 = _einfeld(2, "gelenk")
    check("31 2 Elemente: Vz(L) des Gelenkelements = Rz rechts (vorher 7,778 gegen 7,873 kN)",
          abs(d2["VzL"] - d2["RzL"]) < 1e-6 * d2["RzL"] and abs(d2["My0"] - d2["RM"]) < 1e-6 * d2["RM"],
          f"Vz(L) {d2['VzL'] / 1e3:.4f}  Rz {d2['RzL'] / 1e3:.4f} kN")
    f1 = _einfeld(1, "feder")
    check("31 Federgelenk k = 2EI/L + Feldlast, 1 Element: Stab My(0) = Lager (vorher 12,72 gegen 12,06 kNm)",
          abs(f1["My0"] - f1["RM"]) < 1e-6 * abs(f1["RM"]) and abs(f1["Vz0"] - f1["Rz0"]) < 1e-6 * f1["Rz0"],
          f"Stab {f1['My0'] / 1e3:.4f}  Lager {f1['RM'] / 1e3:.4f} kNm; Vz {f1['Vz0'] / 1e3:.4f}/{f1['Rz0'] / 1e3:.4f}")


def _rahmen(feder=False, n=1):
    """Rahmen 6 x 4 m, Riegel aus zwei Haelften (je n Elemente), Stabendgelenk
    (oder Federgelenk) am rechten Ende der rechten Haelfte, Streckenlast auf
    dem Riegel, Druck in den Stielen, Theorie II. Ordnung."""
    from statik3d import solver
    m = _modell(A=0.01)
    a, b, c, d = m.add_node(0, 0, 0), m.add_node(0, 0, 4), m.add_node(6, 0, 4), m.add_node(6, 0, 0)
    kette = [b] + [m.add_node(6.0 * j / (2 * n), 0, 4) for j in range(1, 2 * n)] + [c]
    riegel = [m.add_element("beam", [kette[j], kette[j + 1]], "ST", "Q") for j in range(2 * n)]
    m.add_element("beam", [a, b], "ST", "Q")
    m.add_element("beam", [c, d], "ST", "Q")
    m.fix(a, "all")
    m.fix(d, "all")
    m.add_hinge("G", end=1, **({"phiy": EI / 3.0} if feder else {"phiy": "free"}))
    m.apply_hinge(riegel[-1], "G")
    m.load_node(b, Fx=3e3, Fz=-300e3)
    m.load_node(c, Fz=-300e3)
    for e in riegel:
        m.load_beam(e, qz=-8e3)
    m.load_cases["LF1"].theorie = "II"
    m.design.imperfektionen = False
    r = solver.solve_all(m, workers=1, design=False).cases["LF1"]
    return m, r, c


def _knotenrest(m, r, knoten):
    """Summe der Stabendkraefte (global) am Knoten minus Knotenlast und Lagerkraft."""
    from statik3d import assemble as asm
    s = np.zeros(6)
    for i, e in enumerate(m.elements):
        if knoten not in e.nodes:
            continue
        T = asm.beam_local(m, e)[2]
        fg = T.T @ np.asarray(r.beam_end[i], float)
        k = 0 if int(e.nodes[0]) == knoten else 6
        s += fg[k:k + 6]
    last = np.zeros(6)
    for nl in m.load_cases["LF1"].nodal_loads:
        if int(nl.node) == knoten:
            last += np.asarray(nl.F, float)
    return s - last - np.asarray(r.reactions[knoten], float)


def test_31_knoten():
    for feder in (False, True):
        m, r, c = _rahmen(feder)
        rest = _knotenrest(m, r, c)
        bez = 300e3                     # Knotenlast; vorher Rest 0,08 N bzw. Nm
        check(f"31 Rahmen mit {'Federgelenk' if feder else 'Stabendgelenk'} + Feldlast: Gleichgewicht am "
              f"Riegelknoten (ΣF, ΣM) auf 1e-9 der Knotenlast", np.max(np.abs(rest)) < 1e-9 * bez,
              f"größter Rest {np.max(np.abs(rest)):.3e} (N bzw. Nm)")


def test_31_fein():
    g = _einfeld(64, "gelenk")
    f = _einfeld(64, "freigabe")
    check("31 fein (64 Elemente): Element-Gelenk = Freigabe am Knoten, My(0) und Rz rechts auf 0,01 %",
          abs(g["My0"] / f["My0"] - 1) < 1e-4 and abs(g["RzL"] / f["RzL"] - 1) < 1e-4
          and abs(g["My0"] - g["RM"]) < 1e-6 * g["RM"],
          f"My(0) {g['My0'] / 1e3:.4f} / {f['My0'] / 1e3:.4f} kNm, Rz {g['RzL'] / 1e3:.4f} / {f['RzL'] / 1e3:.4f} kN")
    werte = []
    for n in (1, 2, 4, 8, 16):
        d = _einfeld(n, "gelenk")
        werte.append((n, d["My0"], d["RM"]))
    gleich = all(abs(a - b) < 1e-6 * abs(b) for _n, a, b in werte)
    check("… je Teilung 1, 2, 4, 8, 16: Stab = Lager; 16 Elemente auf 0,1 % an der feinen Rechnung",
          gleich and abs(werte[-1][1] / f["My0"] - 1) < 1e-3,
          "My(0) " + ", ".join(f"{n}: {a / 1e3:.3f}" for n, a, _b in werte) + f" (64 frei {f['My0'] / 1e3:.3f})")


def _kette(m, n, x0=0.0, l=5.0):
    ids = [m.add_node(x0 + l * j / n, 0, 0) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q") for j in range(n)]
    return ids, els


def test_34_aktuelle_datei():
    from statik3d import solver
    from statik3d.model import Model
    m = _modell(A=1.0)
    ids, els = _kette(m, 2)
    m.fix(ids[0], "all")
    m.fix(ids[-1], "all")
    m.add_hinge("G", end=0, phiy=0.0)
    m.apply_hinge(els[0], "G", end=1)
    m.load_node(ids[1], Fz=-5e3)
    r1 = solver.solve_static(m)
    m2 = Model.from_dict(m.to_dict())
    r2 = solver.solve_static(m2)
    check("34 Gelenk mit apply_hinge(end=1): nach Speichern/Öffnen Gelenk-FHG und Einspannmoment unverändert "
          "(vorher [4, 10], −6,25 → 0)",
          m2.elements[els[0]].hinges == [10] and abs(r2.reactions[ids[0], 4] - r1.reactions[ids[0], 4]) < 1e-9
          and not [h for h in m2._ladehinweise if "Federsteifigkeit 0" in h],
          f"{m2.elements[els[0]].hinges}, {r1.reactions[ids[0], 4] / 1e3:.4f} → {r2.reactions[ids[0], 4] / 1e3:.4f} kNm")
    m = _modell(A=1.0)
    ids, els = _kette(m, 2)
    m.fix(ids[0], "all")
    m.fix(ids[-1], [1, 2])
    m.add_hinge("G", end=0, phiy=0.0)
    m.apply_hinge(els[0], "G")
    m.elements[els[0]].hinges = []          # wie Web „hinges“ mode 0 / Oberfläche „keine“
    m.load_node(ids[1], Fz=-5e3)
    r1 = solver.solve_static(m)
    d = m.to_dict()
    m2 = Model.from_dict(d)
    r2 = solver.solve_static(m2)
    check("34 Gelenk am Element entfernt: nach Speichern/Öffnen bleibt es weg (vorher [4], −4,69 → 0 kNm)",
          m2.elements[els[0]].hinges == [] and abs(r2.reactions[ids[0], 4] - r1.reactions[ids[0], 4]) < 1e-9,
          f"{m2.elements[els[0]].hinges}, {r1.reactions[ids[0], 4] / 1e3:.4f} → {r2.reactions[ids[0], 4] / 1e3:.4f} kNm")
    check("34 die Datei trägt die Kennung federgelenk_null = „gelenk“; ohne Federgelenk k = 0 nicht",
          d.get("federgelenk_null") == "gelenk" and "federgelenk_null" not in _modell().to_dict())


def test_34_alte_datei():
    from statik3d.model import Model
    # alte Datei (ohne Kennung), Gelenk mit weiteren FHG: phiz frei, phiy k = 0 - so schrieb
    # apply_hinge bis 09.11.2026 nur phiz (11) ans Element
    m = _modell(A=1.0)
    ids, els = _kette(m, 3)
    m.add_hinge("G", end=1, phiy=0.0, phiz="free")
    m.apply_hinge(els[0], "G")                  # liegt noch: phiz am Ende
    m.apply_hinge(els[1], "G", end=0)           # am Anfang gelegt
    m.apply_hinge(els[2], "G")                  # danach entfernt
    d = m.to_dict()
    d.pop("federgelenk_null", None)
    for ed, h in zip(d["elements"], ([11], [5], [])):
        ed["hinges"] = h
    m2 = Model.from_dict(d)
    hz = [m2.elements[i].hinges for i in els]
    hinw = [h for h in m2._ladehinweise if "Federsteifigkeit 0" in h]
    check("34 alte Datei: Gelenk am Ende 1 ergänzt, am Anfang am Anfang, am entfernten Element nichts",
          hz == [[10, 11], [4, 5], []] and len(hinw) == 2, f"{hz}; {hinw}")


def _alte_dateien(tmp):
    """Durchlauftraeger mit Federgelenk k = 0 als alte Datei (ohne Kennung,
    Element ohne den Gelenk-FHG) und alte Ergebnisdatei (Verfahrensstand 7)."""
    from statik3d import solver, ergebnisse as erg, rechenverfahren as rv
    m = _modell(A=1e-2)
    ids = [m.add_node(x, 0, 0) for x in (0, 1, 2, 3, 4)]
    els = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(4)]
    m.fix(ids[0], "all")
    m.fix(ids[-1], "all")
    m.load_node(ids[2], Fz=-1e4)
    m.add_hinge("FG", end=1, phiy="spring")
    h = m.hinges["FG"]
    h.elemente = [1]
    m.elements[1].hinges = []
    m.elements[1].hinge_springs = []
    an = solver.solve_all(m, workers=1, design=False)
    pm = os.path.join(tmp, "fg.s3d")
    pe = erg.pfad_zu(pm)
    m.save(pm)
    erg.schreiben(pe, m, an)
    with open(pm, encoding="utf-8") as fh:
        d = json.load(fh)
    d.pop("federgelenk_null", None)
    with open(pm, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    with open(pe, "rb") as fh:
        inhalt = erg._Leser(fh, m).load()
    v = inhalt["verfahren"]
    v["stand"] = 7
    v["merkmale"] = {k: w for k, w in v["merkmale"].items() if rv.merkmal(k).wechsel[-1].stand <= 7}
    with open(pe, "wb") as fh:
        erg._Schreiber(fh, m).dump(inhalt)
    return pm, pe


def test_43_ergebnisse():
    from statik3d import ergebnisse as erg
    from statik3d.model import Model
    tmp = tempfile.mkdtemp(prefix="statik3d_kur_th2_")
    pm, pe = _alte_dateien(tmp)
    m2 = Model.load(pm)
    hinw = [h for h in m2._ladehinweise if "Federsteifigkeit 0" in h]
    try:
        an2, fehler = erg.lesen(pe, m2), ""
    except ValueError as ex:
        an2, fehler = None, str(ex)
    betr = str((an2.info.get("verfahren_betroffen") if an2 is not None else "") or "")
    check("43 alte Datei mit Federgelenk k = 0: Gelenk nachgezogen, Ergebnisse geladen "
          "(vorher „seit der Rechnung geändert: Elementeigenschaften“)",
          m2.elements[1].hinges == [10] and len(hinw) == 1 and an2 is not None, fehler[:120] or str(hinw))
    check("… Status „Ergebnis möglicherweise betroffen“ mit dem Merkmal Federgelenk mit Steifigkeit 0",
          "möglicherweise betroffen" in betr and "Federgelenk mit Steifigkeit 0" in betr, betr[:140])
    check("… das Modell behält die nachgezogenen Gelenke (der Vergleich stellt sie danach zurück)",
          m2.elements[1].hinges == [10])
    m3 = Model.load(pm)
    m3.elements[1].hinges = [4, 10]              # der Anwender ändert das Gelenk danach
    try:
        erg.lesen(pe, m3)
        verworfen = False
    except ValueError as ex:
        verworfen = "Elementeigenschaften" in str(ex)
    check("… nach einer Änderung am nachgezogenen Element passt die alte Datei nicht mehr", verworfen)


def test_13_35_nummern():
    from statik3d import solver, theorie2 as T2
    from statik3d.model import Model
    m = _modell(A=1.0)
    # ohne interne Stabteilung (seit 12.11.2026 Vorgabe 10): nur so ist das
    # einzige Element fuer die Knickfigur zu lang und der Hinweis kommt
    m.netz.stabteilung = 1
    a, b = m.add_node(0, 0, 0), m.add_node(6, 0, 0)
    el = m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, [0, 1, 2, 3])
    m.fix(b, [1, 2])
    m.load_node(b, Fx=-100e3)
    m.load_beam(el, qz=-1e3)
    m.load_cases["LF1"].theorie = "II"
    m.design.imperfektionen = False
    an = solver.solve_all(m, workers=1, design=False)
    hin = [h for i in an.theorie2.kombinationen.values() for h in i.hinweise if "Stabteilung" in h]
    check("13/35 α_cr-Hinweis nennt Element 0 (einziges Element; vorher „Element 1“)",
          len(hin) == 1 and "Element 0 ist" in hin[0], hin[0][:60] if hin else "-")
    m = _modell(A=1.0)
    a, b = m.add_node(0, 0, 0), m.add_node(6, 0, 0)
    el = m.add_element("beam", [a, b], "ST", "Q")
    m.add_hinge("GA", end=0, phiy="free", phiz="free")
    m.add_hinge("GE", end=1, phiy="free", phiz="free")
    m.apply_hinge(el, "GA")
    m.apply_hinge(el, "GE")
    m.fix(a, "all")
    m.fix(b, [1, 2, 3, 4, 5])
    m.load_node(b, Fx=-100e3)
    u = solver.StaticSystem(m).solve(solver.case_loads(m, {"LF1": 1.0}, None)[0])
    ein = T2.einzelstab_knicken(m, u)
    check("13/35 Einzelknicken: der Gelenkbalken heißt „Element 0“ (vorher „Element 1“)",
          [x.get("stab") for x in ein] == ["Element 0"], str([x.get("stab") for x in ein]))
    m = _modell(A=1.0)
    ids, els = _kette(m, 4)
    m.add_hinge("G1", end=1, phiy=0.0)
    m.apply_hinge(els[2], "G1")
    d = m.to_dict()
    d.pop("federgelenk_null", None)
    for ed in d["elements"]:
        ed["hinges"] = []
    m2 = Model.from_dict(d)
    hinw = [h for h in m2._ladehinweise if "Federsteifigkeit 0" in h]
    check("13/35 Ladehinweis nennt das geänderte Element 2 (vorher „Element 3“)",
          len(hinw) == 1 and "an Element 2 jetzt" in hinw[0] and m2.elements[2].hinges == [10],
          hinw[0][:70] if hinw else "-")


def main():
    for t in (test_31_gleichgewicht, test_31_knoten, test_31_fein, test_34_aktuelle_datei,
              test_34_alte_datei, test_43_ergebnisse, test_13_35_nummern):
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
