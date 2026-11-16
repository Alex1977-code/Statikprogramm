"""
Vorkrümmung nach Theorie II. Ordnung bei Stabteilung 1: interne Teilung
gedrückter Stäbe (Runde k10d, Nachbesserung 2, Stand 74).

Befunde der Gegenprüfung Runde 2 vom 16.11.2026 zu 838187d7: Nach Theorie
II. Ordnung, mit einem Element je Stab und Stabteilung 1, wirkte die
Vorkrümmung als Streckenlast im einen Element, war dort aber falsch:

(1) Versatz in Stabrichtung, IPE 300, 6 m, 200 kN: Arm 0,5 m am Ende 13,51
    statt 12,68 kNm (10,4 N/mm²), Arm 1,0 m 17,29 statt 13,87 kNm
    (42,5 N/mm²), Arme −0,3/+0,5 m 15,48 statt 13,45 kNm (25,2 N/mm²).
(2) Federgelenke φy und φz je 2000 kNm/rad an beiden Enden: im Feld 4,38
    statt 3,23 kNm (14,2 N/mm²), am Federgelenk 2,64 statt 3,23 kNm
    (unsichere Seite).

Mit Stabteilung 10 stimmten beide Fälle. Seither teilt Theorie II. Ordnung
gedrückte Stäbe mit Ersatzimperfektionen intern mindestens in 10 Teile
(stabteilung.fein_system mit ``vorkruemmung``), so wie Theorie III. Ordnung
mindestens in 20 Teile.

Bezüge je auf zwei Wegen (Fehlerschwelle 1 N/mm² am Rand, |ΔMz| / W_el,z):
Versatz gegen zwei Modelle mit steifem Balken als Arm (Teilung 0,05 und
0,1 m), Federgelenk gegen 120 Elemente und gegen 20 Elemente, je mit den
Ersatzlasten von Hand und ohne Imperfektionen des Programms.

Aufruf:  python -m tests.test_vorkruemmung_th2_teilung_k10d
"""
import contextlib
import io
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
FEDER = 2e6                     # Nm/rad, φy und φz an beiden Enden


def _modell():
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    m = Model("V")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section(SEC))
    return m


def stab(theorie="II", teilung=1, n_el=1, imp=True, versatz=None, federn=False, hand=False):
    """IPE 300, 6 m, N = 200 kN Druck. ``federn``: Federgelenke φy, φz an
    beiden Stabenden, die Knoten biegesteif gehalten; sonst Gabellager.
    ``hand``: die Ersatzlasten der Vorkrümmung von Hand (q lokal y in jedem
    Element, V an den Stabenden), e_0 = L/250."""
    from statik3d import mesher
    m = _modell()
    ids = mesher.line_of_beams(m, "S235", SEC, (0, 0, 0), (L, 0, 0), n_el)
    ne = len(m.elements)
    if versatz is not None:
        for e in m.elements:
            e.exzentrizitaet = [list(versatz[0]), list(versatz[1])]
    if federn:
        m.elements[0].hinge_springs = [(5, FEDER), (4, FEDER)]
        m.elements[-1].hinge_springs = sorted(set(m.elements[-1].hinge_springs or [])
                                              | {(11, FEDER), (10, FEDER)})
        m.fix(ids[0], [0, 1, 2, 3, 4, 5])
        m.fix(ids[-1], [1, 2, 3, 4, 5])
    else:
        m.fix(ids[0], [0, 1, 2, 3])
        m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N)
    if hand:
        e0 = L / 250.0
        q, V = 8.0 * N * e0 / L ** 2, 4.0 * N * e0 / L
        for e in range(ne):
            m.load_beam(e, qy=q, system="local")
        m.load_node(ids[0], Fy=-V)
        m.load_node(ids[-1], Fy=-V)
    mem = m.add_member("T1", list(range(ne)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m


def starr(a0, a1, h, theorie="II"):
    """Bezug Versatz: der Stab von −a0 bis L + a1 fein geteilt, steife
    Balken als Arme zu den Lagerknoten bei 0 und L, Ersatzlasten von Hand
    (e_0 = Stablänge/250, ohne Imperfektionen des Programms)."""
    from statik3d import mesher
    from statik3d.profiles import make_section
    Ls = L + a0 + a1
    e0 = Ls / 250.0
    q, V = 8.0 * N * e0 / Ls ** 2, 4.0 * N * e0 / Ls
    m = _modell()
    ids = mesher.line_of_beams(m, "S235", SEC, (-a0, 0, 0), (L + a1, 0, 0), int(round(Ls / h)))
    nb = len(m.elements)
    st = make_section(SEC)
    st.name = "STARR"
    for att in ("A", "Iy", "Iz", "It"):
        setattr(st, att, getattr(st, att) * 1e3)
    m.add_section(st)
    A, B = m.add_node(0, 0, 0), m.add_node(L, 0, 0)
    if a0 > 0:
        m.add_element("beam", [A, ids[0]], "S235", "STARR")
    else:
        A = ids[0]
    if a1 > 0:
        m.add_element("beam", [B, ids[-1]], "S235", "STARR")
    else:
        B = ids[-1]
    m.fix(A, [0, 1, 2, 3])
    m.fix(B, [1, 2, 3])
    m.load_node(B, Fx=-N)
    for k in range(nb):
        m.load_beam(k, qy=q, system="local")
    m.load_node(ids[0], Fy=-V)
    m.load_node(ids[-1], Fy=-V)
    m.add_member("T1", list(range(nb)))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m


def rechnen(m, workers=1):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=workers, design=False)
    r = an.combinations["K1"]
    mf = solver.member_forces(m, r, m.members["T1"], n=241)
    return an, r, float(np.abs(mf["Mz"]).max()), mf


def _wz():
    from statik3d.profiles import make_section
    return float(make_section(SEC).Wel_z)


def _sigma(a, b):
    return abs(a - b) / _wz() / 1e6


def _teile(r):
    t = (getattr(r, "info", None) or {}).get("stabteilung") or {}
    return sum(int(v) for v in t.values()) if t else 1


def test_versatz():
    """Versatz in Stabrichtung, ein Element, Stabteilung 1, Theorie II.
    Ordnung: Mz wie die beiden Bezüge mit steifem Arm."""
    for a0, a1 in ((0.0, 0.5), (0.0, 1.0), (0.3, 0.5)):
        _a, _r, R1, _mf = rechnen(starr(a0, a1, 0.05))
        _a, _r, R2, _mf = rechnen(starr(a0, a1, 0.1))
        check(f"Bezüge Versatz −{a0}/+{a1} m: steifer Arm h 0,05 und 0,1 gleich (< 0,1 N/mm²)",
              _sigma(R1, R2) < 0.1, f"{R1 / 1e3:.4f} / {R2 / 1e3:.4f} kNm")
        for t in (1, 10):
            _a, r, M, _mf = rechnen(stab("II", teilung=t, versatz=([-a0, 0, 0], [a1, 0, 0])))
            check(f"Th II, 1 El., Stabteilung {t}, Versatz −{a0}/+{a1} m: Mz wie die Bezüge (< 1 N/mm²)",
                  _sigma(M, R1) < 1.0 and _sigma(M, R2) < 1.0,
                  f"{M / 1e3:.4f} gegen {R1 / 1e3:.4f}/{R2 / 1e3:.4f} kNm, "
                  f"{_sigma(M, R1):.2f} N/mm², {_teile(r)} Teile")


def test_federgelenk():
    """Federgelenke φy, φz an beiden Enden, ein Element, Stabteilung 1,
    Theorie II. Ordnung: Feld und Federgelenk wie die Bezüge."""
    _a, _r, R1, mf1 = rechnen(stab("II", n_el=120, imp=False, federn=True, hand=True))
    _a, _r, R2, mf2 = rechnen(stab("II", n_el=20, imp=False, federn=True, hand=True))
    E1, E2 = abs(float(mf1["Mz"][0])), abs(float(mf2["Mz"][0]))
    check("Bezüge Federgelenk: 120 und 20 Elemente gleich (< 0,1 N/mm²), Feld und Rand",
          _sigma(R1, R2) < 0.1 and _sigma(E1, E2) < 0.1,
          f"Feld {R1 / 1e3:.4f} / {R2 / 1e3:.4f}, Rand {E1 / 1e3:.4f} / {E2 / 1e3:.4f} kNm")
    for ne, t in ((1, 1), (1, 10), (2, 1)):
        _a, r, M, mf = rechnen(stab("II", teilung=t, n_el=ne, federn=True))
        Ma, Mb = abs(float(mf["Mz"][0])), abs(float(mf["Mz"][-1]))
        check(f"Th II, {ne} El., Stabteilung {t}, Federgelenke: Mz im Feld wie die Bezüge (< 1 N/mm²)",
              _sigma(M, R1) < 1.0 and _sigma(M, R2) < 1.0,
              f"{M / 1e3:.4f} gegen {R1 / 1e3:.4f}/{R2 / 1e3:.4f} kNm, {_sigma(M, R1):.2f} N/mm², "
              f"{_teile(r)} Teile")
        check(f"Th II, {ne} El., Stabteilung {t}, Federgelenke: Mz an beiden Federgelenken wie die Bezüge",
              _sigma(Ma, E1) < 1.0 and _sigma(Mb, E1) < 1.0 and _sigma(Ma, E2) < 1.0,
              f"{Ma / 1e3:.4f} / {Mb / 1e3:.4f} gegen {E1 / 1e3:.4f}/{E2 / 1e3:.4f} kNm")


def test_teilung():
    """Wann Theorie II. Ordnung intern teilt: gedrückt mit Ersatzimperfektionen
    mindestens 10 Teile; ohne Imperfektionen bei Stabteilung 1 nicht."""
    _a, r, M, _mf = rechnen(stab("II", teilung=1))
    check("Th II, Gabellager, 1 El., Stabteilung 1, Vorkrümmung: intern 10 Teile",
          _teile(r) == 10, f"{_teile(r)} Teile, Mz {M / 1e3:.4f} kNm")
    _a, r, M, _mf = rechnen(stab("II", teilung=1, imp=False))
    check("Th II ohne Ersatzimperfektionen, Stabteilung 1: nicht geteilt (wie bisher)",
          _teile(r) == 1, f"{_teile(r)} Teile")
    _a, r, M, _mf = rechnen(stab("II", teilung=20))
    check("Th II, Stabteilung 20: weiter 20 Teile (die Mindestteilung senkt nichts)",
          _teile(r) == 20, f"{_teile(r)} Teile")


def test_hinweis_nicht_teilbar():
    """Lässt sich ein gedrückter Stab mit Versatz nicht teilen, sagt es auch
    Theorie II. Ordnung (nicht still ungenau)."""
    from statik3d import stabteilung as st
    from statik3d import solver
    kenn = getattr(st, "VORKRUEMMUNG_KENNUNG_II", "Vorkrümmung nach Theorie II. Ordnung ungenau")
    alt = st.versatz_teile
    st.versatz_teile = lambda model, i, n: None
    try:
        an = _still(solver.solve_all, stab("II", versatz=([0, 0, 0], [0.5, 0, 0])), workers=1, design=False)
    finally:
        st.versatz_teile = alt
    info = an.theorie2.kombinationen["K1"]
    h = [x for x in info.hinweise if kenn in x]
    check("nicht teilbarer Stab mit Versatz, Th II: Hinweis mit Stab und Element",
          bool(h) and "Stab T1 (Element 0)" in h[0] and "in 1 Element" in h[0], " | ".join(info.hinweise)[:240])
    check("nicht teilbarer Stab, Th II: Hinweis auch in an.info (Protokoll und Zusammenfassung)",
          any(kenn in x for x in (an.info.get("laengslast_teilung") or [])), "")
    an = _still(solver.solve_all, stab("II", versatz=([0, 0, 0], [0.5, 0, 0])), workers=1, design=False)
    check("teilbarer Stab mit Versatz, Th II: kein solcher Hinweis",
          not any(kenn in x for x in an.theorie2.kombinationen["K1"].hinweise), "")


def test_arbeitsprozesse():
    """Seriell und über Arbeitsprozesse: dasselbe Ergebnis."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    _a, _r, R_f, _mf = rechnen(stab("II", n_el=120, imp=False, federn=True, hand=True))
    _a, _r, R_v, _mf = rechnen(starr(0.0, 1.0, 0.05))
    for tag, m, R in (("Federgelenke", stab("II", federn=True), R_f),
                      ("Versatz 1,0 m", stab("II", versatz=([0, 0, 0], [1.0, 0, 0])), R_v)):
        # 241 Nachweisstellen: das Maximum liegt beim Versatz nicht an einer
        # der 9 Stellen der Vorgabe (dort 13,73 statt 13,87 kNm, auch mit
        # Stabteilung 10 - eine Frage der Abtastung, nicht der Vorkrümmung)
        m.design.stations = 241
        an = _still(solver.solve_all, m, workers=1, design=False)
        a = _still(check_members, m, an, use_jobs=False)
        b = _still(check_members, m, an, use_jobs=True, workers=2)
        sa, sb = a.members["T1"].stability[0], b.members["T1"].stability[0]
        check(f"Arbeitsprozesse, {tag}: Ausnutzung und Mz_Ed bitgleich mit seriell",
              a.util_max == b.util_max and sa["Mz_Ed"] == sb["Mz_Ed"],
              f"{a.util_max!r} / {b.util_max!r}; {sa['Mz_Ed']!r} / {sb['Mz_Ed']!r}")
        check(f"Arbeitsprozesse, {tag}: Mz_Ed wie der Bezug (< 1 N/mm²)",
              _sigma(abs(float(sb["Mz_Ed"])), R) < 1.0, f"{float(sb['Mz_Ed']) / 1e3:.4f} / {R / 1e3:.4f} kNm")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("vorkruemmung_streckenlast")
    check("Merkmal vorkruemmung_streckenlast: Stand 74, Fehlerkorrektur, nennt die Teilung nach Theorie II",
          mk is not None and mk.wechsel[-1].stand == 74 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and "mindestens in 10 Teilen" in mk.texte.get("neu", ""), f"{mk and mk.texte}")
    if mk is not None:
        check("Merkmal vorkruemmung_streckenlast: Federgelenk- und Versatzmodell betroffen",
              mk.betrifft(stab("II", federn=True)) and mk.betrifft(stab("II", versatz=([0, 0, 0], [0.5, 0, 0]))),
              "")


def main():
    for t in (test_versatz, test_federgelenk, test_teilung, test_hinweis_nicht_teilbar,
              test_arbeitsprozesse, test_merkmal):
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
