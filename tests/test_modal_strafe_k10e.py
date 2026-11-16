"""
Zusammenfuehrung k10, Nachbesserung 2 (16.11.2026): Modalanalyse mit
Straffedern der Starrkoerper - keine gehaltene Richtung als „frei".

Befund der Gegenpruefung (Runde 2): solve_modal (fix/k10-num) prueft die
Zerlegung von A = K - sigma M mit einer Zufallslast. Seit fix/k10-ring traegt
der frei definierte RBE3 je Masterbewegung eine eigene Straffeder; allein ihr
Rundungsrest hob das Residuum der Probe ueber die Schranke (0,000014 gegen
0,000001), obwohl A regulaer ist - die Pruefung mit getrenntem Strafanteil
gab es nur in der Statik. Danach stufte _MasselosFrei mit
‖A z‖ <= 1e-10 ‖|A| |z|‖ zwei von den Elementen gehaltene, masselose
Richtungen als frei ein (Verdrehung der Ringbaugruppe ueber G It, Biegung
des Arms), weil |A| die Straffedern enthaelt, und nahm sie aus jeder Loesung:
die tiefste Eigenfrequenz fehlte still.

Pruefkoerper (wie Sonde E der Gegenpruefung): Kragarm a-b (L = 3 m, E I =
210 GPa mal 8e-5 m^4, It = 100 cm^4 bzw. 1 000 cm^4), eingespannt in a; an b 64
Speichen auf einen Kreisring R = 0,1 m, RBE3 der Ringknoten auf den Master P
(Bolzen b-P, 0,5 m); seitlicher Arm b-e (1 m, I = 5 cm^4), Punktmasse 100 kg
an e, alle Werkstoffe ohne Dichte.

Sollwerte, je zwei Wege:
* Hand: Nachgiebigkeit c = L³/(3 E I) + 1/(G It/L) + 1/(3 E I_Arm),
  f1 = sqrt(1/(c m))/(2 pi) = 1,910132 Hz (It = 100 cm^4) bzw. 2,652729 Hz
  (It = 1 000 cm^4);
* dasselbe Modell ohne RBE3 (Speichen und Ring tragen nichts bei).
Vor der Behebung: 2,816645 Hz in beiden Faellen und der Hinweis
„Frei beweglich ohne Masse: 2 Richtungen ... (67 Knoten)".

Dazu ein wirklich freier Teil: derselbe Aufbau mit einem losen, gewichtslosen
Stab (zwei Knoten, ohne Lager). Dann ist A singulaer, _MasselosFrei rechnet,
und es muessen genau dessen sechs Starrkoerperbewegungen an seinen zwei Knoten
frei heissen, nicht mehr (vorher 8 Richtungen an 69 Knoten, f1 2,816645 Hz).

Aufruf:  python -m tests.test_modal_strafe_k10e
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

E, NU, I, L = 210e9, 0.3, 8e-5, 3.0
IARM = 5e-8
MASSE = 100.0
#: Toleranz der Frequenz gegen die Hand (Hz): Speichen und Bolzen sind in der
#: Hand starr, im Modell nicht (gemessen bis 0,000021 Hz); der Fehler lag bei
#: 0,9 bzw. 0,16 Hz.
TOL_F = 1e-4


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def hand_f(it):
    G = E / (2 * (1 + NU))
    c = L ** 3 / (3 * E * I) + 1.0 / (G * it / L) + 1.0 / (3 * E * IARM)
    return math.sqrt(1.0 / (c * MASSE)) / (2 * math.pi), c


def modell(it, rbe3=True, los=False, ring=64, R=0.1):
    from statik3d.model import Model, Material, Section
    m = Model("modal_strafe")
    m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=it, zmax=0.1, ymax=0.1))
    m.add_section(Section("S", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.add_section(Section("ARM", A=1e-2, Iy=IARM, Iz=IARM, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    rk = []
    for i in range(ring):
        t = 2 * np.pi * i / ring
        k = m.add_node(L, R * np.cos(t), R * np.sin(t))
        m.add_element("beam", [b, k], "ST", "S")
        rk.append(k)
    p = m.add_node(L + 0.5, 0, 0)
    m.add_element("beam", [b, p], "ST", "S")
    if rbe3:
        m.add_starrkoerper(p, rk, "RBE3", name="Ring")
    e = m.add_node(L, 1.0, 0)
    m.add_element("beam", [b, e], "ST", "ARM")
    m.add_punktmasse(e, MASSE)
    lose = []
    if los:
        f = m.add_node(5.0, 3.0, 0.0)
        g = m.add_node(6.0, 3.0, 0.0)
        m.add_element("beam", [f, g], "ST", "S")
        lose = [f, g]
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(e, Fz=-1000.0, case="LF1")
    return m, e, lose


def modal(m):
    from statik3d import solver
    try:
        return still(solver.solve_modal, m, nmodes=3, workers=1), ""
    except Exception as ex:  # noqa: BLE001
        return None, f"{type(ex).__name__}: {str(ex)[:160]}"


def test_kreisring_regulaer():
    from statik3d import solver
    for it in (1e-6, 1e-5):
        fh, c = hand_f(it)
        tag = f"It = {it * 1e8:.0f} cm4"
        # Statik als Rahmen (war schon richtig)
        m, e, _ = modell(it)
        an = still(solver.solve_all, m, workers=1, design=False)
        w = -np.asarray(an.cases["LF1"].u).reshape(-1, 6)[e, 2] * 1e3
        check(f"{tag}: Statik w(e) = Hand", abs(w - 1000 * c * 1e3) < 1e-3,
              f"{w:.6f} gegen {1000 * c * 1e3:.6f} mm")
        mo, fehler = modal(m)
        ohne, fehler2 = modal(modell(it, rbe3=False)[0])
        if not check(f"{tag}: Modalanalyse rechnet (mit und ohne RBE3)", mo is not None and ohne is not None,
                     fehler or fehler2):
            continue
        f = np.asarray(mo.freqs, float)
        f0 = np.asarray(ohne.freqs, float)
        check(f"{tag}: f1 = Hand", abs(f[0] - fh) < TOL_F, f"{f[0]:.6f} gegen {fh:.6f} Hz")
        check(f"{tag}: f1 = Modell ohne RBE3", abs(f[0] - f0[0]) < TOL_F, f"{f[0]:.6f} gegen {f0[0]:.6f} Hz")
        check(f"{tag}: f2 = Modell ohne RBE3", abs(f[1] - f0[1]) < TOL_F, f"{f[1]:.6f} gegen {f0[1]:.6f} Hz")
        check(f"{tag}: kein Hinweis auf freie Teile", not mo.info.get("frei_ohne_masse"),
              (mo.info.get("frei_hinweis") or "")[:160])


def test_loser_stab():
    it = 1e-6
    fh, _c = hand_f(it)
    m, _e, lose = modell(it, los=True)
    mo, fehler = modal(m)
    if not check("loser Stab: Modalanalyse rechnet", mo is not None, fehler):
        return
    f = np.asarray(mo.freqs, float)
    check("loser Stab: f1 = Hand", abs(f[0] - fh) < TOL_F, f"{f[0]:.6f} gegen {fh:.6f} Hz")
    info = mo.info.get("frei_ohne_masse") or {}
    check("loser Stab: genau 6 freie Richtungen", info.get("richtungen") == 6 and not info.get("mindestens"),
          str(info)[:160])
    check("loser Stab: frei nur an seinen zwei Knoten", sorted(info.get("knoten") or []) == sorted(lose),
          f"{(info.get('knoten') or [])[:10]} gegen {lose}")
    # Ohne RBE3 (kein Strafanteil, bisheriger Weg) dasselbe
    mo2, fehler2 = modal(modell(it, rbe3=False, los=True)[0])
    if check("loser Stab ohne RBE3: Modalanalyse rechnet", mo2 is not None, fehler2):
        info2 = mo2.info.get("frei_ohne_masse") or {}
        check("loser Stab ohne RBE3: f1 = Hand, 6 freie Richtungen an zwei Knoten",
              abs(float(mo2.freqs[0]) - fh) < TOL_F and info2.get("richtungen") == 6
              and sorted(info2.get("knoten") or []) == sorted(lose),
              f"{float(mo2.freqs[0]):.6f} Hz, {str(info2)[:120]}")


def test_einstufung_direkt():
    """_MasselosFrei unmittelbar am regulaeren Kreisringmodell: keine
    Richtung ist frei (vorher 2 an 67 Knoten)."""
    from statik3d import solver, assemble as asm, parallel
    m, _e, _ = modell(1e-6)
    with parallel.arbeiter(m, 1):
        K = asm.stiffness(m, 1, None)
        M = asm.mass(m, 1, None)
    fixed, _v = asm.constrained_dofs(m, K)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Mff = M[fi][:, fi].tocsc()
    sigma = -1e-6 * float(np.abs(Kff.diagonal()).mean() / Mff.diagonal().mean())
    A = (Kff - sigma * Mff).tocsc()
    sa = getattr(K, "_strafanteil", None)
    check("Strafanteil am Kreisringmodell vorhanden", sa is not None and bool(sa.kopplungen))
    if sa is None:
        return
    try:
        fr = solver._MasselosFrei(A, Mff, solver.LinearSolver(A), strafe=sa.lokal(fi, ((-sigma) * M,)))
    except TypeError as ex:
        check("_MasselosFrei nimmt die Pruefung mit Strafanteil", False, str(ex)[:160])
        return
    try:
        check("_MasselosFrei: keine gehaltene Richtung als frei", fr.richtungen == 0,
              f"{fr.richtungen} Richtungen an {len(fr.knoten(m, fi))} Knoten")
    finally:
        fr.freigeben()


def main():
    test_kreisring_regulaer()
    test_loser_stab()
    test_einstufung_direkt()
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
