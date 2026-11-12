"""
Theorie II. und III. Ordnung an Staeben, Nebenbefund 16 (09.11.2026): drei
Stellen, die der Umbau der Gruppe 3 (A7, A8) offen liess. Jede Zahl gegen eine
geschlossene Loesung und einen zweiten Rechenweg.

a) Theorie III. Ordnung, Gelenke: die Tangente bekam die geometrische
   Steifigkeit in der vollen Balkenform (6/5 N/L), auch am Balken mit
   Gelenken an beiden Enden. Kragstiel h = 5 m (kst = 3 E I / h³ = 504 kN/m,
   H = 1 kN) mit Pendelstuetze als Balken mit Gelenken (1 Element): die
   Tangente wurde bei 1/1,2 = 5/6 der Knicklast kst h singulaer, darueber
   endete die Rechnung mit „keine Konvergenz“. Soll bei P = 0,9 kst h:
   u = H / (kst - P/h) = 19,841 mm (II. Ordnung von Hand); zweiter Weg:
   dieselbe Pendelstuetze als Fachwerkstab (19,843 mm). Unter 5/6 stimmte das
   Ergebnis schon vorher (das Residuum ist von der Tangente unabhaengig).
b) Geometrische Steifigkeit mit Versatz der Stabenden: k_G wirkte auf die
   Knoten statt auf die Stabenden, waehrend Steifigkeit und Rueckrechnung mit
   dem Versatz rechnen. Druckstab L = 4 m, gabelgelagert, 8 Elemente,
   I_z = 50 I_y, I_T = 1e-5 m⁴, P = 0,5 pi² E I_y / L², der Stab liegt 0,2 m
   neben seiner Knotenlinie (Versatz in lokal y, quer zur Knickrichtung):
   alpha_cr = 2,000 (Euler; der Versatz aendert die Knicklast um die schwache
   Achse nicht). Vorher 1,158: die Drehung um die Stabachse verschob in der
   Rechnung die Druckkraft nicht mit, Abschaetzung
   1 / (1/N_cr + e²/(G I_T)) / P = 1,218. Zweiter Weg: derselbe Stab an
   eigenen Knoten, ueber starre Kurzstaebe an die Knotenlinie gehaengt.
c) Feldanteil N w mit Schubverformung: die Biegelinie im Feld kam nur aus der
   Kruemmung M / (E I). Einfeldtraeger 6 m, q = 5 kN/m, Schubsteifigkeit
   S = G A_s mit N_E / S = 0,1, Druck P = 0,6 N_cr mit N_cr = N_E / (1 + N_E/S)
   (Engesser), ein Element. Geschlossen (Timoshenko-Balken mit Druck):
   M'' + k² M = -q / (1 - P/S), k² = P / (E I (1 - P/S)),
   max M = q E I / P (1/cos(k L/2) - 1) = 57,232 kNm; vorher 50,298 kNm
   (-12,1 %). Zweiter Weg: 48 Elemente (57,318 kNm, +0,15 %).

Nicht behoben (im Bericht mit Zahlen): Laengslasten entlang des Stabes - die
Stabkraft gilt im Element als gleichbleibend.

Aufruf:  python -m tests.test_theorie_nebenbefund16
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
I = 1e-4
EI = E * I


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:88s} {detail}")
    return ok


def _modell(**sec):
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    kw = dict(A=1.0, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.05)
    kw.update(sec)
    m.add_section(Section("Q", **kw))
    return m


def _kette(m, p1, p2, n, typ="beam", **kw):
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    ids = []
    for k in range(n + 1):
        p = p1 + (p2 - p1) * k / n
        if m.nn:
            d = np.linalg.norm(m.nodes - p, axis=1)
            j = int(np.argmin(d))
            if d[j] < 1e-9:
                ids.append(j)
                continue
        ids.append(m.add_node(*p))
    els = [m.add_element(typ, [ids[k], ids[k + 1]], "ST", "Q", **kw) for k in range(n)]
    return ids, els


def _th2(m):
    from statik3d import solver
    m.load_cases["LF1"].theorie = "II"
    m.design.imperfektionen = False
    an = solver.solve_all(m, workers=1, design=False)
    return an.cases["LF1"]


# ---------------------------------------------------------------- a) Theorie III, Gelenke
H_, H_STIEL = 1e3, 5.0
KST = 3 * EI / H_STIEL ** 3


def _stiel_mit_pendel(pendel, P):
    """Kragstiel (8 Elemente) mit Kopflast H; daneben eine Pendelstuetze mit
    der Last P, ueber einen Fachwerkstab an den Stielkopf gehaengt. pendel
    "beam": ein Balken mit Gelenken an beiden Enden, "truss": Fachwerkstab."""
    m = _modell()
    ids, _ = _kette(m, (0, 0, 0), (0, 0, H_STIEL), 8)
    pa, pe = _kette(m, (3, 0, 0), (3, 0, H_STIEL), 1, typ=("truss" if pendel == "truss" else "beam"))
    m.add_element("truss", [ids[-1], pa[-1]], "ST", "Q")
    if pendel == "beam":
        m.add_hinge("GA", end=0, phiy="free", phiz="free")
        m.add_hinge("GE", end=1, phiy="free", phiz="free")
        m.apply_hinge(pe[0], "GA")
        m.apply_hinge(pe[-1], "GE")
        m.fix(pa[0], [5])
        m.fix(pa[-1], [5])
    m.fix(ids[0], "all")
    m.fix(pa[0], [0, 1, 2])
    m.fix(pa[-1], [1])
    m.fix(ids[-1], [1])
    m.load_node(pa[-1], Fz=-P)
    m.load_node(ids[-1], Fx=H_)
    return m, ids


def _th3(pendel, anteil):
    from statik3d.theorie3 import solve_theorie3
    m, ids = _stiel_mit_pendel(pendel, anteil * KST * H_STIEL)
    m.design.imperfektionen = False
    res, info = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=10, imperfektionen=False)
    return float(res.u[ids[-1], 0]), info


def test_a_theorie3_gelenke():
    for anteil, tol_hand in ((0.9, 2e-4), (0.95, 1e-3)):
        soll = H_ / (KST - anteil * KST)
        u_b, info_b = _th3("beam", anteil)
        u_t, info_t = _th3("truss", anteil)
        check(f"III. Ordnung, Pendelstütze als Gelenkbalken, P = {anteil:.2f} kst h: Rechnung konvergiert",
              not info_b.fehler, f"Fehler {info_b.fehler!r}, {info_b.iterationen} Iterationen")
        check(f"… u = H/(kst − P/h) = {soll * 1e3:.3f} mm (II. Ordnung von Hand, auf {tol_hand * 100:.2f} %)",
              not info_b.fehler and abs(u_b / soll - 1) < tol_hand, f"u = {u_b * 1e3:.4f} mm")
        check("… wie mit der Pendelstütze als Fachwerkstab (zweiter Weg, auf 0,01 %)",
              not info_b.fehler and not info_t.fehler and abs(u_b / u_t - 1) < 1e-4,
              f"Gelenkbalken {u_b * 1e3:.4f} mm, Fachwerkstab {u_t * 1e3:.4f} mm")
    # unter 5/6 der Knicklast stimmte das Ergebnis schon vorher (Kontrolle)
    soll = H_ / (KST - 0.5 * KST)
    u_b, info_b = _th3("beam", 0.5)
    check(f"III. Ordnung, P = 0,50 kst h: u = {soll * 1e3:.3f} mm wie bisher (auf 0,1 %)",
          not info_b.fehler and abs(u_b / soll - 1) < 1e-3, f"u = {u_b * 1e3:.4f} mm")


# ---------------------------------------------------------------- b) K_G mit Versatz
L_B = 4.0
P_B = 0.5 * math.pi ** 2 * EI / L_B ** 2


def _stab_versatz(art, e_y, n=8, qz=-1e3):
    """Druckstab, gabelgelagert an der Knotenlinie; der Stab liegt um e_y
    daneben. art "versatz": Exzentrizitaet am Element; "kurzstab": eigene
    Stabknoten, starr angeschlossen; "ohne": mittig."""
    m = _modell(Iz=50 * I)
    if art == "kurzstab":
        from statik3d.model import Section
        m.add_section(Section("STARR", A=1e3, Iy=1e2, Iz=1e2, It=1e2, zmax=0.1, ymax=0.1))
        ref = [m.add_node(L_B * k / n, 0, 0) for k in range(n + 1)]
        st = [m.add_node(L_B * k / n, e_y, 0) for k in range(n + 1)]
        els = [m.add_element("beam", [st[k], st[k + 1]], "ST", "Q") for k in range(n)]
        for a, b in zip(ref, st):
            m.add_element("beam", [a, b], "ST", "STARR")
        ids = ref
    else:
        kw = {} if art == "ohne" else {"exzentrizitaet": [[0, e_y, 0], [0, e_y, 0]]}
        ids, els = _kette(m, (0, 0, 0), (L_B, 0, 0), n, **kw)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-P_B)
    for e in els:
        m.load_beam(e, qz=qz)
    r = _th2(m)
    mitte = ids[len(ids) // 2]
    return r.info.get("alpha_cr"), float(r.u[mitte, 2]), float(r.u[mitte, 3]), r


def test_b_kg_mit_versatz():
    e_y = 0.2
    a_o, w_o, _t, _r = _stab_versatz("ohne", e_y)
    a_k, w_k, t_k, _r = _stab_versatz("kurzstab", e_y)
    a_v, w_v, t_v, r_v = _stab_versatz("versatz", e_y)
    check("II. Ordnung, Druckstab ohne Versatz: alpha_cr = 2,000 (Euler, auf 0,1 %) wie bisher",
          a_o is not None and abs(a_o / 2.0 - 1) < 1e-3, f"alpha_cr = {a_o}")
    check("Stab 0,2 m neben der Knotenlinie über starre Kurzstäbe: alpha_cr = 2,000 (zweiter Weg)",
          a_k is not None and abs(a_k / 2.0 - 1) < 1e-3, f"alpha_cr = {a_k}")
    check("Stab mit Versatz 0,2 m am Element: alpha_cr = 2,000 (Euler, auf 0,1 %; vorher 1,158)",
          a_v is not None and abs(a_v / 2.0 - 1) < 1e-3, f"alpha_cr = {a_v}")
    check("… und wie das Modell mit Kurzstäben (auf 0,01 %)",
          a_v is not None and a_k is not None and abs(a_v / a_k - 1) < 1e-4, f"{a_v} gegen {a_k}")
    # Durchbiegung unter q = 1 kN/m: Vergroesserung 1/(1 - 1/alpha) = 2
    w1 = 5 * 1e3 * L_B ** 4 / (384 * EI)
    check(f"… Durchbiegung in der Mitte wie mit Kurzstäben (auf 0,1 %; etwa 2 · {w1 * 1e3:.4f} mm, vorher −1,1148 mm)",
          abs(w_v / w_k - 1) < 1e-3 and abs(abs(w_v) / (2 * w1) - 1) < 0.01,
          f"Versatz {w_v * 1e3:.4f} mm, Kurzstäbe {w_k * 1e3:.4f} mm, ohne {w_o * 1e3:.4f} mm")
    check("… keine Verdrehung um die Stabachse (wie mit Kurzstäben; vorher 2,0 mrad)",
          abs(t_v) < 1e-6 and abs(t_k) < 1e-6, f"Versatz {t_v * 1e3:.5f} mrad, Kurzstäbe {t_k * 1e3:.5f} mrad")


# ---------------------------------------------------------------- c) Feld mit Schubverformung
L_C, Q_C = 6.0, 5e3


def _einfeld(n, verh):
    """Einfeldtraeger unter q und Druck 0,6 N_cr; verh = N_E / S (0: schubstarr).
    Gibt das groesste Feldmoment, die geschlossene Loesung und alpha_cr."""
    NE = math.pi ** 2 * EI / L_C ** 2
    S = NE / verh if verh else math.inf
    P = 0.6 * NE / (1 + verh)
    k = math.sqrt(P / (EI * (1 - P / S))) if verh else math.sqrt(P / EI)
    soll = Q_C * EI / P * (1 / math.cos(k * L_C / 2) - 1)
    m = _modell()
    if verh:
        m.sections["Q"].Asy = m.sections["Q"].Asz = S / m.materials["ST"].G
    ids, els = _kette(m, (0, 0, 0), (L_C, 0, 0), n)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2])
    m.load_node(ids[-1], Fx=-P)
    for e in els:
        m.load_beam(e, qz=-Q_C)
    r = _th2(m)
    st = r.stations(41)
    return max(float(np.max(np.abs(st[e]["My"]))) for e in els), soll, r.info.get("alpha_cr")


def test_c_feld_mit_schub():
    m1, soll, a1 = _einfeld(1, 0.1)
    m48, _s, a48 = _einfeld(48, 0.1)
    check(f"II. Ordnung, Einfeldträger mit Schubfläche (N_E/S = 0,1), 1 Element: max My = {soll / 1e3:.3f} kNm "
          "(geschlossen, auf 0,5 %)", abs(m1 / soll - 1) < 5e-3,
          f"My = {m1 / 1e3:.3f} kNm ({(m1 / soll - 1) * 100:+.2f} %; vorher 50,298 kNm)")
    check("… zweiter Weg: 48 Elemente treffen die geschlossene Lösung auf 0,5 %",
          abs(m48 / soll - 1) < 5e-3, f"My = {m48 / 1e3:.3f} kNm ({(m48 / soll - 1) * 100:+.2f} %)")
    check("… ein Element und 48 Elemente stimmen auf 0,5 % überein",
          abs(m1 / m48 - 1) < 5e-3, f"{m1 / 1e3:.3f} gegen {m48 / 1e3:.3f} kNm")
    check("… alpha_cr = 1/0,6 = 1,667 mit 48 Elementen (Engesser, auf 0,5 %)",
          a48 is not None and abs(a48 * 0.6 - 1) < 5e-3, f"alpha_cr = {a48}")
    m0, soll0, _a = _einfeld(1, 0.0)
    check(f"Ohne Schubfläche unverändert: max My = {soll0 / 1e3:.3f} kNm (auf 0,1 %)",
          abs(m0 / soll0 - 1) < 1e-3, f"My = {m0 / 1e3:.3f} kNm")


def main():
    for t in (test_a_theorie3_gelenke, test_b_kg_mit_versatz, test_c_feld_mit_schub):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
