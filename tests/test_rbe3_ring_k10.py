"""
Runde k10c (15.11.2026), Gruppe G: Kreisring-RBE3 numerisch singulaer.

Befund (zweite Gegenpruefung der Gruppe D): ein gesunder Kreisring-RBE3 mit
64 Slaves, dessen Master zusaetzlich ueber einen Bolzenstab gehalten ist und
dessen Ringknoten ueber wirksame Speichen am Stabende haengen, brach mit
„Gleichungssystem numerisch singulaer" ab (Residuum 0,039 bzw. 0,013). Ohne
RBE3 rechnete dasselbe Modell richtig.

Ursache (assemble.starrkoerper), zwei Teile:
1. Die sechs Zeilen des allgemeinen RBE3 (verbindung.starrkoerper_matrix)
   gingen unbearbeitet in k Gᵀ G: am Master stand die Gewichtssumme (64) im
   Quadrat, die Strafe war das 51 200 000-fache der groessten Hauptdiagonale
   der Elemente statt das 10 000-fache. Liegt der Master neben der Ringebene,
   sind Kraft- und Momentenzeilen ausserdem fast parallel.
2. k bezog sich (auch bei den verteilenden Kopplungen „Scheibe"/„Stabende")
   auf die groesste Hauptdiagonale des ganzen Modells - hier die 64 Speichen
   von 0,1 m an einem Knoten. Der Rundungsfehler eps k |u| in K u lag dann
   allein schon ueber der Residuumsschranke 0,000001 ||F||.
Behebung: Zeilen des allgemeinen RBE3 orthonormiert, Strafbeiwert jedes RBE3
1e4-mal die groesste Hauptdiagonale der Freiheitsgrade, die er koppelt.

Sollwerte, zwei Wege:
* Gegenrechnung: dasselbe Modell mit dem RBE3 als exakter Zwangsbedingung
  (Lagrange-Multiplikatoren, G hier unabhaengig von verbindung.py aus der
  Definition des RBE3 aufgebaut, ohne Strafverfahren).
* Hand: Ring starr am Stabende b, w(b) = F L³/(3EI) + F a L²/(2EI),
  w(P) = w(b) + a φ(b) (die Speichen geben dazu 0,000016 mm).
* Gleichgewicht: Auflagerkraft 1 000 N, Einspannmoment F (L + a) = 3 500 Nm.

Aufruf:  python -m tests.test_rbe3_ring_k10
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


def nah(name, ist, soll, tol, einheit="mm"):
    return check(name, abs(ist - soll) <= tol,
                 f"ist {ist:.7f} {einheit}, soll {soll:.7f} {einheit}, Abweichung {abs(ist - soll):.7f}")


E, I, A, L, AH, R, F = 210e9, 8e-5, 1e-2, 3.0, 0.5, 0.1, 1e3
EI = E * I


def modell(n_stab=1, ring=64, name="Ring", art="RBE3"):
    """Kragarm (n_stab Staebe, 3 m) mit 64 Speichen von 0,1 m am Ende b,
    Kreisring der Speichenenden als RBE3 auf den Master P 0,5 m vor b, P
    zusaetzlich ueber einen Bolzenstab b-P gehalten, Fz = -1 kN an P."""
    from statik3d.model import Model, Material, Section
    m = Model("k10c")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    h = L / n_stab
    kn = [m.add_node(i * h, 0, 0) for i in range(n_stab + 1)]
    for i in range(n_stab):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    b = kn[-1]
    rk = []
    for i in range(ring):
        t = 2 * np.pi * i / ring
        k = m.add_node(L, R * np.cos(t), R * np.sin(t))
        m.add_element("beam", [b, k], "ST", "Q")
        rk.append(k)
    p = m.add_node(L + AH, 0, 0)
    m.add_element("beam", [b, p], "ST", "Q")
    m.add_starrkoerper(p, rk, art, name=name)
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(p, Fz=-F, case="LF1")
    return m, b, p, rk


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def g_definition(X, m, slaves):
    """RBE3 aus der Definition (Gewichte 1): sum (u_i - u_m - th_m x r_i) = 0
    und sum r_i x (u_i - u_m - th_m x r_i) = 0, unabhaengig von verbindung.py."""
    n = 6 * len(X)

    def skew(a):
        return np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    Gm = np.zeros((6, n))
    for s in slaves:
        r = X[s] - X[m]
        B = np.zeros((3, n))
        B[:, 6 * s:6 * s + 3] = np.eye(3)
        B[:, 6 * m:6 * m + 3] -= np.eye(3)
        B[:, 6 * m + 3:6 * m + 6] += skew(r)
        Gm[:3] += B
        Gm[3:] += skew(r) @ B
    return Gm


def exakt(m, p, slaves):
    """Gegenrechnung: Elemente ohne Starrkoerper, RBE3 als exakte
    Zwangsbedingung (Lagrange), Knoten 0 eingespannt."""
    from scipy import sparse
    from scipy.sparse import linalg as sla
    from statik3d import assemble as asm
    sk = list(m.starrkoerper)
    m.starrkoerper.clear()
    try:
        K = asm.stiffness(m).tocsr()
    finally:
        m.starrkoerper.extend(sk)
    X = np.asarray(m.nodes, float)
    G = g_definition(X, p, slaves)
    n = K.shape[0]
    fr = np.arange(6, n)
    Fv = np.zeros(n)
    Fv[6 * p + 2] = -F
    Kf = K[fr][:, fr]
    Gf = sparse.csr_matrix(G[:, fr])
    Aks = sparse.bmat([[Kf, Gf.T], [Gf, None]]).tocsc()
    x = sla.spsolve(Aks, np.concatenate([Fv[fr], np.zeros(6)]))
    u = np.zeros(n)
    u[fr] = x[:len(fr)]
    return u.reshape(-1, 6)


def hand():
    wb = F * L ** 3 / (3 * EI) + F * AH * L ** 2 / (2 * EI)
    pb = F * L ** 2 / (2 * EI) + F * AH * L / EI
    return wb, wb + AH * pb


def _ring_fall(n_stab, name, titel):
    from statik3d import solver
    m, b, p, rk = modell(n_stab, name=name)
    try:
        res = _still(solver.solve_static, m, case="LF1")
    except RuntimeError as ex:
        check(f"{titel}: rechnet", False, str(ex)[:200])
        return
    check(f"{titel}: rechnet", True)
    u = np.asarray(res.u, float).reshape(-1, 6)
    ue = exakt(m, p, rk)
    wb_h, wp_h = hand()
    nah(f"{titel}: w(P) gegen exakte Zwangsbedingung", -u[p, 2] * 1e3, -ue[p, 2] * 1e3, 0.00001)
    nah(f"{titel}: w(b) gegen exakte Zwangsbedingung", -u[b, 2] * 1e3, -ue[b, 2] * 1e3, 0.00001)
    nah(f"{titel}: w(b) gegen Hand", -u[b, 2] * 1e3, wb_h * 1e3, 0.00001)
    nah(f"{titel}: w(P) gegen Hand (Ring starr an b)", -u[p, 2] * 1e3, wp_h * 1e3, 0.0001)
    Rz = float(np.asarray(res.reactions)[0, 2])
    My = float(np.asarray(res.reactions)[0, 4])
    nah(f"{titel}: Auflagerkraft Rz (Schranke des Loesers)", Rz, F, 0.01, "N")
    nah(f"{titel}: Einspannmoment |My| = F (L + a)", abs(My), F * (L + AH), 0.01, "Nm")


def test_ring_allgemein():
    """Der gemeldete Fall: allgemeiner RBE3 „Ring", 1 und 100 Staebe."""
    _ring_fall(1, "Ring", "RBE3 Ring, 1 Stab")
    _ring_fall(100, "Ring", "RBE3 Ring, 100 Staebe")


def test_ring_scheibe():
    """Dieselbe Lage als verteilende Kopplung „Scheibe" (Kreisring der
    Einleitung, stabeinleitung.zwangsmatrix)."""
    _ring_fall(1, "Scheibe F1", "Scheibe (verteilend), 1 Stab")
    _ring_fall(100, "Scheibe F1", "Scheibe (verteilend), 100 Staebe")


def test_strafbeiwert():
    """Strafe bezogen auf die gekoppelten Knoten: groesste Hauptdiagonale mit
    RBE3 hoechstens 2*10 000-mal die der Ringknoten, nicht 51 200 000-mal
    die des ganzen Modells."""
    from statik3d import assemble as asm
    m, b, p, rk = modell(1)
    K = asm.stiffness(m)
    sk = list(m.starrkoerper)
    m.starrkoerper.clear()
    Ke = asm.stiffness(m)
    m.starrkoerper.extend(sk)
    d_ring = max(float(abs(Ke.diagonal()[6 * k + j])) for k in rk for j in range(3))
    v = float(abs(K.diagonal()).max()) / d_ring
    check("Strafbeiwert: groesste Hauptdiagonale mit RBE3 / Ringknoten <= 20 000", v <= 2.0e4, f"{v:,.0f}")
    v2 = float(abs(K.diagonal()).max()) / float(abs(Ke.diagonal()).max())
    check("Strafbeiwert: nicht mehr 51 200 000-mal die Elemente (<= 10 000)", v2 <= 1.0e4, f"{v2:,.0f}")


def test_pruefung_kraftsumme():
    """stabeinleitung.pruefen liest den Strafbeiwert je Kopplung: die Kraft der
    Scheibe in die Ringknoten gleicht die des Bolzenstabs."""
    from statik3d import solver, stabeinleitung as se
    m, b, p, rk = modell(1, name="Scheibe F1")
    res = _still(solver.solve_static, m, case="LF1")
    erg = se.pruefen(m, res, F_norm=F)
    check("Pruefung Kraftsumme: Kopplung geprueft und ohne Abweichung",
          erg.get("geprueft") == 1 and not erg.get("abweichend"),
          f"geprueft {erg.get('geprueft')}, abweichend {len(erg.get('abweichend') or [])}, "
          f"max dF {erg.get('max_dF', 0):.6f} N")


def test_verteilung_hand():
    """Schutz (vorher wie nachher): freier Master in der Mitte von vier
    gelagerten Slaves (Quadrat 2a = 0,2 m). Fz = 1 kN: je 250 N; Mx = 1 kNm:
    Rz = ±M y_i / sum y² = ±2 500 N (klassischer RBE3)."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver
    m = Model("vier")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    a = 0.1
    sl = [m.add_node(x, y, 0) for x, y in ((a, a), (-a, a), (-a, -a), (a, -a))]
    for s in sl:
        m.fix(s, "all")
    p = m.add_node(0, 0, 0)
    m.add_starrkoerper(p, sl, "RBE3", name="Vier")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(p, Fz=-F, Mx=1e3, case="LF1")
    res = _still(solver.solve_static, m, case="LF1")
    R = np.asarray(res.reactions, float)
    rz = [float(R[s, 2]) for s in sl]
    y = [a, a, -a, -a]
    soll = [F / 4 - 1e3 * yi / (4 * a * a) for yi in y]
    ok = max(abs(r - s) for r, s in zip(rz, soll)) <= 0.01
    check("Schutz: Verteilung eines freien RBE3 auf vier Slaves (Fz und Mx)", ok,
          f"ist {[round(r, 3) for r in rz]}, soll {[round(s, 3) for s in soll]} N")


def test_rbe2_bitgleich():
    """RBE2 ist nicht betroffen: Matrix mit und ohne Behebung bitgleich."""
    from statik3d import assemble as asm
    m, b, p, rk = modell(1, art="RBE2")
    K1 = asm.stiffness(m).tocsr()
    asm.RBE3_STRAFE_ALT = True
    try:
        K0 = asm.stiffness(m).tocsr()
    finally:
        asm.RBE3_STRAFE_ALT = False
    d = abs(K1 - K0)
    check("RBE2: Matrix bitgleich mit dem Stand vor der Behebung", d.nnz == 0 or d.max() == 0.0,
          f"nnz der Differenz {d.nnz}")


def test_ruecknahme():
    """Ruecknahmeprobe: mit dem alten Strafbeiwert bricht der Ring wieder ab."""
    from statik3d import assemble as asm, solver
    asm.RBE3_STRAFE_ALT = True
    try:
        m, _b, _p, _rk = modell(1)
        try:
            _still(solver.solve_static, m, case="LF1")
            txt = "rechnet"
        except RuntimeError as ex:
            txt = str(ex)
    finally:
        asm.RBE3_STRAFE_ALT = False
    check("Ruecknahme: alter Strafbeiwert meldet „numerisch singulaer“", "singul" in txt, txt[:120])


def main():
    tests = [test_ring_allgemein, test_ring_scheibe, test_strafbeiwert, test_pruefung_kraftsumme,
             test_verteilung_hand, test_rbe2_bitgleich, test_ruecknahme]
    fehl = []
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__, False))
            fehl.append(f"{t.__name__} (Ausnahme: {type(ex).__name__}: {str(ex)[:200]})")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    fehl += [n for n, ok in RESULTS if not ok and not any(n in f for f in fehl)]
    if fehl:
        print("FEHLGESCHLAGEN:", fehl)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
