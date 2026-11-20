"""
Vorkrümmung bei grober Stabteilung (Runde k10d, Stand 74).

Befund der Gegenprüfung (16.11.2026): die Vorkrümmung nach 5.3.2(7), Bild
5.4, ging je Element als Knotenkraft halb und halb an die Elementknoten. In
einem Element je Stab hob sie sich mit den Endquerkräften V = 4 N e_0/L auf
und fehlte still. IPE 300, 6 m, gabelgelagert, N = 200 kN, Endmomente 60 kNm,
Theorie II. Ordnung, ein Element, Stabteilung 1: Mz_Ed 0,000 statt 11,52 kNm,
Ausnutzung 1,6377 statt 2,4842. In wenigen Teilen fehlte das Feldmoment
zwischen den Knoten: 3 Teile 10,36, 5 Teile 11,11 kNm. Theorie III. Ordnung
(Knotenkräfte an den Teilen) teilte bei Stabteilung 1 gar nicht.

Behebung: Theorie II. Ordnung setzt q als Streckenlast im Element an
(Festeinspannkräfte und Feld wie eine Streckenlast des Anwenders), Theorie
III. Ordnung teilt gedrückte Stäbe mindestens in 20 Teile.

Bezug auf zwei Wegen: (1) geschlossen, Einfeldträger mit Druck und
gleichmäßiger Querlast, M = q/k² (1/cos(kL/2) − 1) mit k² = N/(E I_z (1 −
N/(G A_sy))) (Schubverformung nach Engesser, wie das Element); (2) das
gleiche Modell ohne Imperfektionen mit der Streckenlast q = 8 N e_0/L² von
Hand in 80 Elementen. Fehlerschwelle 1 N/mm² am Rand: |ΔMz| / W_el,z.

Aufruf:  python -m tests.test_vorkruemmung_k10d
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


N_DRUCK = 200e3
L_IPE = 6.0
E0_L = 1.0 / 250.0          # IPE 300 um z: Knicklinie b, elastisch
Q_V = 8.0 * N_DRUCK * E0_L * L_IPE / L_IPE ** 2


def ipe(theorie="II", teilung=None, n_el=1, moment=60e3, imp=True, q_hand=0.0, roll=0.0):
    """Einfeldträger IPE 300, S235, 6 m, gabelgelagert, N = 200 kN Druck,
    Endmomente ``moment`` (My, gleichbleibend), K1 nach ``theorie``."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    from statik3d import mesher
    m = Model("IPE")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (L_IPE, 0, 0), n_el)
    if roll:
        for e in m.elements:
            e.roll = roll
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N_DRUCK)
    if moment:
        m.load_node(ids[0], My=moment)
        m.load_node(ids[-1], My=-moment)
    if q_hand:
        for e in range(n_el):
            m.load_beam(e, qy=q_hand, system="local")
    mem = m.add_member("T1", list(range(n_el)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    if teilung is not None:
        m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie=theorie)
    return m


def rechnen(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.combinations["K1"]
    mf = solver.member_forces(m, r, m.members["T1"], n=241)
    return an, r, float(np.abs(mf["Mz"]).max()), mf


def bezug_geschlossen():
    """Weg 1, geschlossen mit Schubverformung: w = w_b + w_s, E I w_b'' = −M,
    w_s = M/(G A_sy), M = M_0 + N w. Daraus M'' + k² M = −q/c mit
    c = 1 − N/(G A_sy) und k² = N/(E I_z c), also
    M(L/2) = q E I_z/N (1/cos(kL/2) − 1)."""
    m = ipe()
    sec, mat = m.sections["IPE 300"], m.materials["S235"]
    GA = mat.G * float(sec.Asy or 0.0)
    c = (1.0 - N_DRUCK / GA) if GA > 0 else 1.0
    k = math.sqrt(N_DRUCK / (mat.E * sec.Iz * c))
    return Q_V * mat.E * sec.Iz / N_DRUCK * (1.0 / math.cos(k * L_IPE / 2.0) - 1.0), float(sec.Wel_z)


def test_bezug():
    M1, Wz = bezug_geschlossen()
    _an, _r, M2, _mf = rechnen(ipe(teilung=1, n_el=80, imp=False, q_hand=Q_V, moment=0.0))
    check("Bezug: geschlossen und Streckenlast von Hand (80 Elemente) stimmen überein (< 0,05 N/mm²)",
          abs(M1 - M2) / Wz < 0.05e6, f"{M1 / 1e3:.4f} / {M2 / 1e3:.4f} kNm")
    return M1, M2, Wz


def test_theorie2(M1, M2, Wz):
    """Theorie II. Ordnung: jede Teilung gibt das Feldmoment der Vorkrümmung."""
    from statik3d.ec3.design import check_members
    werte = {}
    for ne, t in ((1, 1), (1, 2), (1, 3), (1, 5), (3, 1), (1, 10), (10, 1)):
        m = ipe("II", teilung=t, n_el=ne)
        an, r, Mz, mf = rechnen(m)
        a = _still(check_members, m, an, use_jobs=False)
        s = a.members["T1"].stability[0]
        werte[(ne, t)] = (Mz, a.util_max)
        abw = max(abs(Mz - M1), abs(Mz - M2)) / Wz / 1e6
        check(f"Th II, {ne} El., Stabteilung {t}: Mz der Vorkrümmung wie der Bezug (< 1 N/mm²)",
              abw < 1.0, f"Mz {Mz / 1e3:.4f} kNm, Bezug {M1 / 1e3:.4f}/{M2 / 1e3:.4f}, Δσ {abw:.3f} N/mm²")
        check(f"Th II, {ne} El., Stabteilung {t}: der Nachweis liest dasselbe Mz_Ed",
              abs(float(s["Mz_Ed"]) - Mz) < 1e-6 * max(Mz, 1.0) + 1.0,
              f"Mz_Ed {float(s['Mz_Ed']) / 1e3:.4f} kNm")
        # gabelgelagert: an den Stabenden kein Moment um z
        check(f"Th II, {ne} El., Stabteilung {t}: Mz an den gelenkigen Enden 0",
              abs(mf["Mz"][0]) < 1.0 and abs(mf["Mz"][-1]) < 1.0,
              f"{mf['Mz'][0]:.3g} / {mf['Mz'][-1]:.3g} Nm")
        Ry = float(np.asarray(r.reactions)[:, 1].sum())
        check(f"Th II, {ne} El., Stabteilung {t}: Ersatzlasten im Gleichgewicht (Σ R_y = 0)",
              abs(Ry) < 1e-6 * Q_V * L_IPE, f"Σ R_y = {Ry:.3g} N")
    u1, u10 = werte[(1, 1)][1], werte[(10, 1)][1]
    check("Th II: Ausnutzung bei einem Element und Stabteilung 1 wie bei zehn Elementen (< 0,1 %)",
          abs(u1 - u10) < 1e-3 * u10, f"{u1:.6f} / {u10:.6f}")


def test_theorie3():
    """Theorie III. Ordnung (ohne Endmoment: mit 60 kNm und ohne Wölbsteifigkeit
    liegt die Last über dem Biegedrillknicken): gedrückte Stäbe mindestens in
    20 Teilen, auch bei Stabteilung 1."""
    from statik3d.model import Model  # noqa: F401
    m_ref = ipe("III", teilung=1, n_el=80, imp=False, q_hand=Q_V, moment=0.0)
    _an, r_ref, M3, _mf = rechnen(m_ref)
    Wz = float(m_ref.sections["IPE 300"].Wel_z)
    check("Th III Bezug: Streckenlast von Hand in 80 Elementen gerechnet",
          str(r_ref.info.get("theorie", "")).startswith("III"), f"{M3 / 1e3:.4f} kNm")
    for ne, t in ((1, 1), (1, 2), (1, 5), (10, 1)):
        m = ipe("III", teilung=t, n_el=ne, moment=0.0)
        an, r, Mz, _mf = rechnen(m)
        teile = r.info.get("stabteilung") or {}
        gesamt = sum(teile.get(i, 1) for i in range(ne))
        abw = abs(Mz - M3) / Wz / 1e6
        check(f"Th III, {ne} El., Stabteilung {t}: gerechnet, mindestens 20 Teile",
              str(r.info.get("theorie", "")).startswith("III") and gesamt >= 20,
              f"{r.info.get('theorie')} {r.info.get('theorie_fehler')} Teile {gesamt}")
        check(f"Th III, {ne} El., Stabteilung {t}: Mz der Vorkrümmung wie der Bezug (< 1 N/mm²)",
              abw < 1.0, f"Mz {Mz / 1e3:.4f} kNm, Bezug {M3 / 1e3:.4f}, Δσ {abw:.3f} N/mm²")


def test_arbeitsprozesse():
    """Seriell und über Arbeitsprozesse: dasselbe Ergebnis, mit Vorkrümmung."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    M1, Wz = bezug_geschlossen()
    m = ipe("II", teilung=1, n_el=1)
    an = _still(solver.solve_all, m, workers=1, design=False)
    a = _still(check_members, m, an, use_jobs=False)
    b = _still(check_members, m, an, use_jobs=True, workers=2)
    sa, sb = a.members["T1"].stability[0], b.members["T1"].stability[0]
    check("Arbeitsprozesse: Ausnutzung und Mz_Ed bitgleich mit seriell",
          a.util_max == b.util_max and sa["Mz_Ed"] == sb["Mz_Ed"],
          f"{a.util_max!r} / {b.util_max!r}; {sa['Mz_Ed']!r} / {sb['Mz_Ed']!r}")
    check("Arbeitsprozesse: Mz_Ed mit der Vorkrümmung (wie der Bezug, < 1 N/mm²)",
          abs(float(sb["Mz_Ed"]) - M1) / Wz < 1e6, f"{float(sb['Mz_Ed']) / 1e3:.4f} / {M1 / 1e3:.4f} kNm")


def test_gedreht():
    """Querschnitt um 90° gedreht (roll): die Vorkrümmung folgt der schwachen
    Achse - Mz wie ungedreht, die Durchbiegung jetzt global in z."""
    M1, Wz = bezug_geschlossen()
    for ne, t in ((1, 1), (4, 1), (1, 10)):
        m = ipe("II", teilung=t, n_el=ne, moment=0.0, roll=math.pi / 2.0)
        _an, r, Mz, _mf = rechnen(m)
        check(f"gedreht 90°, {ne} El., Stabteilung {t}: Mz wie der Bezug (< 1 N/mm²)",
              abs(Mz - M1) / Wz < 1e6, f"{Mz / 1e3:.4f} / {M1 / 1e3:.4f} kNm")
        if ne > 1:
            u = np.asarray(r.u)
            uz, uy = float(np.abs(u[:, 2]).max()), float(np.abs(u[:, 1]).max())
            check(f"gedreht 90°, {ne} El.: Durchbiegung global in z, nicht in y",
                  uz > 0.01 and uy < 1e-9, f"u_y {uy * 1e3:.4f} mm, u_z {uz * 1e3:.3f} mm")


def test_ersatzlasten():
    """ersatzlasten_vorkruemmung: ohne ``stablasten`` die Knotenkräfte wie
    bisher (Theorie III. Ordnung), mit ihnen die Streckenlast; beide im
    Gleichgewicht und quer zur Stabachse."""
    from statik3d import solver, theorie2 as T2
    m = ipe("II", teilung=1, n_el=4, moment=0.0)
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.combinations["K1"]
    F0, v0 = T2.ersatzlasten_vorkruemmung(m, r)
    sl = {}
    F1, v1 = T2.ersatzlasten_vorkruemmung(m, r, stablasten=sl)
    for tag, F in (("Knotenkräfte", F0), ("Streckenlast", F1)):
        Fr = F.reshape(-1, 6)
        check(f"Ersatzlasten {tag}: Σ F = 0 und keine Kraft in Stabrichtung",
              abs(Fr[:, :3].sum()) < 1e-6 and abs(Fr[:, 0]).max() < 1e-9,
              f"Σ {Fr[:, :3].sum():.3g}, max |F_x| {abs(Fr[:, 0]).max():.3g}")
    q = v1["je_stab"][0]["q"]
    check("Streckenlast: in allen vier Elementen q über die ganze Elementlänge",
          sorted(sl.get("q", {})) == [0, 1, 2, 3]
          and all(abs(z[0, 3] - q) < 1e-9 * q and abs(z[0, 1] - 1.5) < 1e-12 for z in sl["q"].values()),
          str({k: np.round(v, 3).tolist() for k, v in (sl.get("q") or {}).items()})[:200])
    # Knotenkräfte: q L_e/2 je Elementknoten (die Zwischenknoten q L_e)
    Fr0 = F0.reshape(-1, 6)
    check("Knotenkräfte (Theorie III. Ordnung) unverändert: Zwischenknoten q L_e",
          abs(abs(Fr0[1, 1]) - q * 1.5) < 1e-6 * q, f"{Fr0[1, 1]:.4f} / {q * 1.5:.4f} N")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    mk = rv.merkmal("vorkruemmung_streckenlast")
    check("Merkmal vorkruemmung_streckenlast: Stand 74, Fehlerkorrektur, 16.11.2026, VERFAHRENSSTAND >= 74",
          mk is not None and mk.wechsel[-1].stand == 74 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].datum == "16.11.2026" and rv.VERFAHRENSSTAND >= 74,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m2, m3 = ipe("II"), ipe("III")
    ohne_imp, linear = ipe("II", imp=False), ipe("I")
    check("Merkmal: Th II und Th III mit Imperfektionen betroffen, ohne Imperfektionen und linear nicht",
          mk.betrifft(m2) and mk.betrifft(m3) and not mk.betrifft(ohne_imp) and not mk.betrifft(linear),
          f"{mk.betrifft(m2)} {mk.betrifft(m3)} {mk.betrifft(ohne_imp)} {mk.betrifft(linear)}")
    an = _still(solver.solve_all, m2, workers=1, design=False)
    an_o = _still(solver.solve_all, ohne_imp, workers=1, design=False)
    im, im_o = mk.im_ergebnis(m2, an) or "", mk.im_ergebnis(ohne_imp, an_o) or ""
    check("Merkmal im Ergebnis: K1 mit Vorkrümmung genannt, ohne Imperfektionen leer",
          "K1" in im and not im_o, f"{im!r} / {im_o!r}")


def main():
    bezug = None
    for t in (test_bezug, test_theorie2, test_theorie3, test_arbeitsprozesse, test_gedreht,
              test_ersatzlasten, test_merkmal):
        print(f"\n--- {t.__name__} ---")
        try:
            if t is test_bezug:
                bezug = t()
            elif t is test_theorie2:
                if bezug is None:
                    raise RuntimeError("kein Bezug")
                t(*bezug)
            else:
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
