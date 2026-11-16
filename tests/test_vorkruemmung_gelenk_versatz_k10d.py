"""
Vorkrümmung an Gelenkstäben, Stäben mit Versatz und umgedrehten Elementen
(Runde k10d, Nachbesserung 1, Stand 74).

Befunde der Gegenprüfung vom 16.11.2026 zu 3f5c7a75:

(1) stabteilung.teilen strich das Biegegelenk am Ende eines Balkens, der auch
    am Anfang eines hat. Der Gelenkstab zwischen biegesteifen Knoten war am
    Ende eingespannt: IPE 300, 6 m, 200 kN, Vorkrümmung, Theorie III. Ordnung,
    Stabteilung 1 (automatisch 20 Teile) Mz 6,03 statt 11,48 kNm und 6,03 am
    Gelenk; Theorie II. Ordnung mit Stabteilung 10 und q 5 kN/m 28,33 statt
    54,00 kNm.
(2) Ein Stab mit Versatz, dessen Arm länger als ein Teil ist (Stab 6,5 m, Arm
    0,5 m in Stabrichtung am Ende), blieb ungeteilt; nach Theorie III. Ordnung
    fehlte die Vorkrümmung in einem Element still (Mz 0).

Dazu, im selben Weg behoben: die Endquerkräfte V griffen am Knoten statt am
versetzten Stabende an (Theorie II. Ordnung mit Stabteilung 10 10,53 statt
12,67 kNm), und ein umgedrehtes Element bekam q gegen die anderen.

Bezüge je auf zwei Wegen (Fehlerschwelle 1 N/mm² am Rand, |ΔMz| / W_el,z):
Gelenkstab gegen das Gabellager ohne Gelenke und gegen die geschlossene
Lösung bzw. den Bogen; Versatz gegen ein fein geteiltes Modell mit dem Arm am
letzten Element und gegen einen steifen Balken als Arm, beide mit den
Ersatzlasten von Hand.

Aufruf:  python -m tests.test_vorkruemmung_gelenk_versatz_k10d
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
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


N = 200e3
L = 6.0
SEC = "IPE 300"


def _modell(name="V"):
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    m = Model(name)
    m.add_material(Material.steel("S235"))
    m.add_section(make_section(SEC))
    return m


def stab(theorie="II", teilung=1, n_el=1, imp=True, q_hand=0.0, gelenke=False, versatz=None,
         umgedreht=False, bogen=0.0):
    """IPE 300, 6 m, N = 200 kN Druck. ``gelenke``: Biegegelenke (φy, φz) an
    beiden Elementenden, die Knoten biegesteif gehalten; sonst Gabellager.
    ``umgedreht``: zwei Elemente, das zweite von rechts nach links.
    ``bogen``: geometrisch vorgekrümmt (Parabel mit Stich ``bogen``)."""
    from statik3d import mesher
    m = _modell()
    if bogen:
        ids = [m.add_node(L * k / n_el, 4 * bogen * (L * k / n_el) * (L - L * k / n_el) / L ** 2, 0.0)
               for k in range(n_el + 1)]
        for k in range(n_el):
            m.add_element("beam", [ids[k], ids[k + 1]], "S235", SEC)
    elif umgedreht:
        a, b, c = m.add_node(0, 0, 0), m.add_node(L / 2, 0, 0), m.add_node(L, 0, 0)
        m.add_element("beam", [a, b], "S235", SEC)
        m.add_element("beam", [c, b], "S235", SEC)
        ids = [a, b, c]
    else:
        ids = mesher.line_of_beams(m, "S235", SEC, (0, 0, 0), (L, 0, 0), n_el)
    ne = len(m.elements)
    if versatz is not None:
        for e in m.elements:
            e.exzentrizitaet = [list(versatz[0]), list(versatz[1])]
    if gelenke:
        m.elements[0].hinges = sorted(set(m.elements[0].hinges or []) | {4, 5})
        m.elements[-1].hinges = sorted(set(m.elements[-1].hinges or []) | {10, 11})
        m.fix(ids[0], [0, 1, 2, 3, 4, 5])
        m.fix(ids[-1], [1, 2, 3, 4, 5])
    else:
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N)
    if q_hand:
        for e in range(ne):
            m.load_beam(e, qy=q_hand, system="local")
    mem = m.add_member("T1", list(range(ne)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m


def rechnen(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.combinations["K1"]
    mf = solver.member_forces(m, r, m.members["T1"], n=241)
    return an, r, float(np.abs(mf["Mz"]).max()), mf


def _wz():
    from statik3d.profiles import make_section
    return float(make_section(SEC).Wel_z)


def _sigma(a, b):
    return abs(a - b) / _wz() / 1e6


def _geschlossen(q):
    """Einfeldträger mit Druck N und Querlast q, mit Schubverformung wie das
    Element: M(L/2) = q E I_z/N (1/cos(kL/2) − 1), k² = N/(E I_z (1 − N/(G A_sy)))."""
    m = _modell()
    sec, mat = m.sections[SEC], m.materials["S235"]
    GA = mat.G * float(sec.Asy or 0.0)
    c = (1.0 - N / GA) if GA > 0 else 1.0
    k = math.sqrt(N / (mat.E * sec.Iz * c))
    return q * mat.E * sec.Iz / N * (1.0 / math.cos(k * L / 2.0) - 1.0)


# ---------------------------------------------------------------- (1) Gelenke
def test_teilen_gelenke():
    """stabteilung.teilen: Biegegelenke an beiden Enden bleiben, Verschiebung
    und Torsion an beiden Enden behalten die Kettenregel."""
    from statik3d import stabteilung as st
    for gel, anf, end in (([4, 5, 10, 11], [4, 5], [10, 11]),
                          ([3, 4, 5, 9, 10, 11], [3, 4, 5], [10, 11]),
                          ([5, 11], [5], [11]),
                          ([1, 5, 7, 11], [1, 5], []),
                          ([0, 6], [0], [])):
        m = stab()
        m.elements[0].hinges = list(gel)
        m2, abb, _a = st.teilen(m, None, {0: 4})
        t = abb.teile[0]
        h0, h1 = sorted(m2.elements[t[0]].hinges), sorted(m2.elements[t[-1]].hinges)
        mitte = [m2.elements[j].hinges for j in t[1:-1]]
        check(f"teilen, Gelenke {gel}: erstes Teil {anf}, letztes {end}, Mitte ohne",
              h0 == anf and h1 == end and all(not x for x in mitte), f"{h0} / {h1} / {mitte}")


def test_gelenkstab():
    M_imp = _geschlossen(8.0 * N * (L / 250.0) / L ** 2)
    M_q5 = _geschlossen(5e3)
    # Theorie II. Ordnung, reine Streckenlast 5 kN/m (ohne Imperfektion)
    _a, _r, M_gabel, _mf = rechnen(stab("II", teilung=10, imp=False, q_hand=5e3))
    check("Bezug Th II q 5: Gabellager St 10 und geschlossen stimmen überein (< 0,05 N/mm²)",
          _sigma(M_gabel, M_q5) < 0.05, f"{M_gabel / 1e3:.4f} / {M_q5 / 1e3:.4f} kNm")
    for ne, t in ((1, 10), (2, 10), (1, 20)):
        _a, r, Mz, mf = rechnen(stab("II", teilung=t, n_el=ne, imp=False, q_hand=5e3, gelenke=True))
        rand = max(abs(float(mf["Mz"][0])), abs(float(mf["Mz"][-1])))
        check(f"Gelenkstab Th II q 5, {ne} El., St {t}: Feld wie Gabellager und geschlossen (< 1 N/mm²)",
              _sigma(Mz, M_gabel) < 1.0 and _sigma(Mz, M_q5) < 1.0,
              f"{Mz / 1e3:.4f} / {M_gabel / 1e3:.4f} / {M_q5 / 1e3:.4f} kNm")
        check(f"Gelenkstab Th II q 5, {ne} El., St {t}: am Gelenk kein Moment (< 0,01 kNm)",
              rand < 10.0, f"Mz Rand {rand / 1e3:.4f} kNm")
    # mit Vorkruemmung, Theorie II. und III. Ordnung
    _a, _r, B2, _mf = rechnen(stab("II", n_el=80, imp=False, bogen=L / 250.0))
    _a, _r, B3, _mf = rechnen(stab("III", n_el=80, imp=False, bogen=L / 250.0))
    check("Bezug Vorkrümmung: Bogen 80 El. Th II und geschlossen stimmen überein (< 0,1 N/mm²)",
          _sigma(B2, M_imp) < 0.1, f"{B2 / 1e3:.4f} / {M_imp / 1e3:.4f} kNm")
    for th, B in (("II", B2), ("III", B3)):
        for ne, t in ((1, 1), (1, 10), (10, 1)):
            _a, _r, M_g, _mf = rechnen(stab(th, teilung=t, n_el=ne))
            _a, r, Mz, mf = rechnen(stab(th, teilung=t, n_el=ne, gelenke=True))
            rand = max(abs(float(mf["Mz"][0])), abs(float(mf["Mz"][-1])))
            ok_th = str(r.info.get("theorie", "")).startswith(th)
            check(f"Gelenkstab Vorkrümmung Th {th}, {ne} El., St {t}: wie Gabellager und Bogen (< 1 N/mm²)",
                  ok_th and _sigma(Mz, M_g) < 1.0 and _sigma(Mz, B) < 1.0,
                  f"{Mz / 1e3:.4f} / Gabel {M_g / 1e3:.4f} / Bogen {B / 1e3:.4f} kNm {r.info.get('theorie')}")
            check(f"Gelenkstab Vorkrümmung Th {th}, {ne} El., St {t}: am Gelenk kein Moment",
                  rand < 10.0, f"Mz Rand {rand / 1e3:.4f} kNm")


def test_pendelstab_knicken():
    """Knicken eines Pendelstabs (ein Element, Biegegelenke an beiden Enden,
    Stabteilung 10): Euler-Fall 2 wie das Gabellager, nicht eingespannt."""
    from statik3d import solver
    m = _modell()
    sec, mat = m.sections[SEC], m.materials["S235"]
    GA = mat.G * float(sec.Asy or 0.0)
    Ne = math.pi ** 2 * mat.E * sec.Iz / L ** 2
    N_cr = Ne / (1.0 + Ne / GA)                        # mit Schubverformung (Engesser)
    werte = {}
    for gel in (False, True):
        mm = stab("II", teilung=10, imp=False, gelenke=gel)
        r = _still(solver.solve_buckling, mm, 3)
        f = np.asarray(r.buckling_factors, float)
        werte[gel] = float(f[f > 0].min())
    check("Pendelstab Knicken: Faktor wie Gabellager und Euler (< 0,5 %)",
          abs(werte[True] / werte[False] - 1.0) < 0.005 and abs(werte[True] * N / N_cr - 1.0) < 0.005,
          f"Gelenk {werte[True]:.4f}, Gabel {werte[False]:.4f}, Euler {N_cr / N:.4f}")


# ---------------------------------------------------------------- (2) Versatz
ARM = 0.5


def bezug_versatz(theorie, art):
    """Stab 0 … 6,5 m, Lager bei 0 und am Knoten S (6,0 m), der über einen
    starren Arm 0,5 m in Stabrichtung am Stabende hängt; ohne Imperfektionen,
    q = 8 N e0/L² und V = 4 N e0/L von Hand an den Stabenden.
    ``art`` "arm": 59 Elemente bis 5,9 m, das letzte mit dem Arm (Versatz);
    "starr": 65 Elemente bis 6,5 m und ein steifer Balken von S zum Stabende."""
    from statik3d import mesher
    from statik3d.profiles import make_section
    Ls = L + ARM
    e0 = Ls / 250.0
    q, V = 8 * N * e0 / Ls ** 2, 4 * N * e0 / Ls
    m = _modell("R")
    if art == "arm":
        ids = mesher.line_of_beams(m, "S235", SEC, (0, 0, 0), (5.9, 0, 0), 59)
        S = m.add_node(L, 0, 0)
        m.add_element("beam", [ids[-1], S], "S235", SEC)
        m.elements[-1].exzentrizitaet = [[0, 0, 0], [ARM, 0, 0]]
        nb = len(m.elements)
        m.load_node(ids[0], Fy=-V)
        m.load_node(S, Fy=-V, Mz=-ARM * V)                  # V am Stabende 6,5 m
    else:
        ids = mesher.line_of_beams(m, "S235", SEC, (0, 0, 0), (Ls, 0, 0), 65)
        nb = len(m.elements)
        s = make_section(SEC)
        s.name = "STARR"
        for att in ("A", "Iy", "Iz", "It"):
            setattr(s, att, getattr(s, att) * 1e3)
        m.add_section(s)
        S = m.add_node(L, 0, 0)
        m.add_element("beam", [S, ids[-1]], "S235", "STARR")
        m.load_node(ids[0], Fy=-V)
        m.load_node(ids[-1], Fy=-V)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(S, [1, 2, 3])
    m.load_node(S, Fx=-N)
    for k in range(nb):
        m.load_beam(k, qy=q, system="local")
    m.add_member("T1", list(range(nb)))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m


def test_versatz():
    for th in ("II", "III"):
        _a, _r, R1, _mf = rechnen(bezug_versatz(th, "arm"))
        _a, _r, R2, _mf = rechnen(bezug_versatz(th, "starr"))
        check(f"Bezug Versatz Th {th}: Arm am letzten Element und steifer Balken stimmen überein (< 0,1 N/mm²)",
              _sigma(R1, R2) < 0.1, f"{R1 / 1e3:.4f} / {R2 / 1e3:.4f} kNm")
        fälle = ((1, 1), (1, 10)) if th == "III" else ((1, 10),)
        for ne, t in fälle:
            _a, r, Mz, _mf = rechnen(stab(th, teilung=t, n_el=ne, versatz=([0, 0, 0], [ARM, 0, 0])))
            teile = sum((r.info.get("stabteilung") or {}).values())
            check(f"Versatz 0,5 m in Stabrichtung, Th {th}, {ne} El., St {t}: Mz wie beide Bezüge (< 1 N/mm²)",
                  str(r.info.get("theorie", "")).startswith(th) and _sigma(Mz, R1) < 1.0 and _sigma(Mz, R2) < 1.0,
                  f"{Mz / 1e3:.4f} / {R1 / 1e3:.4f} / {R2 / 1e3:.4f} kNm, Teile {teile}")
            if th == "III":
                check(f"Versatz, Th III, {ne} El., St {t}: intern in 20 Teile geteilt", teile >= 20, f"{teile}")


def test_versatz_teile_verteilt():
    """stabteilung.versatz_teile: 20 Teile verteilt, Zwischenknoten auf der
    Knotenlinie, Stabpunkte gleichmäßig auf der versetzten Achse."""
    from statik3d import stabteilung as st
    from statik3d.elements import beam3d as bm
    m = stab(versatz=([0, 0, 0], [ARM, 0, 0]))
    vt = st.versatz_teile(m, 0, 20)
    ok = vt is not None and len(vt) == 20
    det = ""
    if ok:
        P = []
        for A, B, roll, exz in vt:
            arme = bm.versatz_arme(A, B, roll, exz) if exz else np.zeros((2, 3))
            P.append((A + arme[0], B + arme[1]))
        h = np.array([np.linalg.norm(b - a) for a, b in P])
        stoss = max(float(np.linalg.norm(P[k][1] - P[k + 1][0])) for k in range(19))
        ok = (abs(float(P[0][0][0])) < 1e-12 and abs(float(P[-1][1][0]) - (L + ARM)) < 1e-9
              and np.abs(h - (L + ARM) / 20).max() < 1e-9 and stoss < 1e-9
              and all(0.0 <= float(A[0]) <= L + 1e-12 for A, _B, _r, _e in vt))
        det = f"h {h.min():.6f}…{h.max():.6f}, Stoß {stoss:.2e}"
    check("versatz_teile: Arm länger als ein Teil, verteilt in 20 gleiche Teile", ok, det)


def test_hinweis_nicht_teilbar():
    """Falls ein gedrückter Stab mit Versatz sich nicht teilen lässt: Theorie
    III. Ordnung sagt es (nicht still ohne Vorkrümmung)."""
    from statik3d import stabteilung as st
    from statik3d import solver
    kenn = getattr(st, "VORKRUEMMUNG_KENNUNG", "Vorkrümmung nach Theorie III. Ordnung unvollständig")
    alt = st.versatz_teile
    st.versatz_teile = lambda model, i, n: None
    try:
        m = stab("III", teilung=1, versatz=([0, 0, 0], [ARM, 0, 0]))
        an = _still(solver.solve_all, m, workers=1, design=False)
    finally:
        st.versatz_teile = alt
    info = an.theorie3.kombinationen["K1"]
    h = [x for x in info.hinweise if kenn in x]
    check("nicht teilbarer Stab mit Versatz, Th III: Hinweis mit Stab und Element",
          bool(h) and "Stab T1 (Element 0)" in h[0] and "in 1 Element" in h[0], " | ".join(info.hinweise)[:240])
    check("nicht teilbarer Stab: Hinweis auch in an.info (Protokoll und Zusammenfassung)",
          any(kenn in x for x in (an.info.get("laengslast_teilung") or [])), "")
    # teilbar: kein Hinweis
    an = _still(solver.solve_all, stab("III", teilung=1, versatz=([0, 0, 0], [ARM, 0, 0])), workers=1,
                design=False)
    check("teilbarer Stab mit Versatz, Th III: kein solcher Hinweis",
          not any(kenn in x for x in an.theorie3.kombinationen["K1"].hinweise), "")


def test_gleichgewicht_ersatzlasten():
    """Die Ersatzlasten der Vorkrümmung sind im Gleichgewicht, auch um den
    Ursprung - mit Versatz greift V am versetzten Stabende an."""
    from statik3d import solver, theorie2 as T2
    for tag, kw in (("Versatz 0,5 m in Stabrichtung", dict(versatz=([0, 0, 0], [ARM, 0, 0]))),
                    ("Versatz 0,1 m quer z an beiden Enden", dict(versatz=([0, 0, 0.1], [0, 0, 0.1]))),
                    ("zweites Element umgedreht", dict(umgedreht=True))):
        m = stab("II", **kw)
        an = _still(solver.solve_all, m, workers=1, design=False)
        r = an.combinations["K1"]
        for art, sl in (("Knotenkräfte", None), ("Streckenlast", {})):
            F, _v = T2.ersatzlasten_vorkruemmung(m, r, stablasten=sl)
            Fr = F.reshape(-1, 6)
            X = np.asarray(m.nodes, float)
            SF = Fr[:, :3].sum(axis=0)
            SM = Fr[:, 3:].sum(axis=0) + np.cross(X, Fr[:, :3]).sum(axis=0)
            check(f"Ersatzlasten {art}, {tag}: Σ F = 0 und Σ M = 0",
                  np.abs(SF).max() < 1e-6 and np.abs(SM).max() < 1e-6,
                  f"Σ F {np.round(SF, 6).tolist()}, Σ M {np.round(SM, 6).tolist()} N/Nm")


# ------------------------------------------------------- umgedrehtes Element
def test_umgedreht():
    for th in ("II", "III"):
        for t in (1, 10):
            _a, _r, M_g, _mf = rechnen(stab(th, teilung=t, n_el=2))
            _a, r, Mz, _mf = rechnen(stab(th, teilung=t, umgedreht=True))
            check(f"zweites Element umgedreht, Th {th}, St {t}: Mz wie gleich gerichtet (< 0,01 N/mm²)",
                  _sigma(Mz, M_g) < 0.01, f"{Mz / 1e3:.4f} / {M_g / 1e3:.4f} kNm")


# ---------------------------------------------------------------- Merkmale
def test_merkmale():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    for name, mit, ohne in (("stabteilung_biegegelenke", stab("II", teilung=10, gelenke=True), stab("II")),
                            ("versatz_verteilt", stab("III", versatz=([0, 0, 0], [ARM, 0, 0])),
                             stab("III", versatz=([0, 0, 0.1], [0, 0, 0.1])))):
        mk = rv.merkmal(name)
        check(f"Merkmal {name}: Stand 74, Fehlerkorrektur, 16.11.2026",
              mk is not None and mk.wechsel[-1].stand == 74 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
              and mk.wechsel[-1].datum == "16.11.2026" and rv.VERFAHRENSSTAND >= 74, f"{mk and mk.wechsel}")
        if mk is None:
            continue
        check(f"Merkmal {name}: betroffenes Modell ja, anderes nein",
              mk.betrifft(mit) and not mk.betrifft(ohne), f"{mk.betrifft(mit)} {mk.betrifft(ohne)}")
        an = _still(solver.solve_all, mit, workers=1, design=False)
        check(f"Merkmal {name}: im Ergebnis genannt", bool(mk.im_ergebnis(mit, an)), str(mk.im_ergebnis(mit, an)))


def main():
    for t in (test_teilen_gelenke, test_gelenkstab, test_pendelstab_knicken, test_versatz,
              test_versatz_teile_verteilt, test_hinweis_nicht_teilbar, test_gleichgewicht_ersatzlasten,
              test_umgedreht, test_merkmale):
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
