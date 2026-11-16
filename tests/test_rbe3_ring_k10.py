"""
Runde k10c (15.11.2026), Gruppe G: Kreisring-RBE3 numerisch singulaer.

Befund (zweite Gegenpruefung der Gruppe D): ein gesunder Kreisring-RBE3 mit
64 Slaves, dessen Master zusaetzlich ueber einen Bolzenstab gehalten ist und
dessen Ringknoten ueber wirksame Speichen am Stabende haengen, brach mit
„Gleichungssystem numerisch singulaer" ab (Residuum 0,039 bzw. 0,013). Ohne
RBE3 rechnete dasselbe Modell richtig.

Ursache: Die Straffedern k Gᵀ G der Starrkoerper und Verteilkopplungen
stehen mit k bis 10 000-mal der groessten Hauptdiagonale in K, beim
allgemeinen RBE3 zusaetzlich mit der Gewichtssumme im Quadrat (am Ring das
51 200 000-fache der Elemente). Schon die auf doppelte Genauigkeit gerundete
exakte Loesung hat im Strafanteil den Rest k Gᵀ (G δu), |δu| = eps |u|;
bewegt sich der Ring mit dem Kragarm als Ganzes, liegt dieser Rest ueber der
Schranke 0,000001 ||F||. Dazu nahm die automatische Fesselung die groesste
Hauptdiagonale samt Straffedern als Bezug: 1e-12 davon lag ueber der
Torsionssteifigkeit des Kragarms (w(P) 0,135 statt 0,848 mm).

Erster Versuch (ef235e50): Zeilen orthonormiert, Strafbeiwert auf die
gekoppelten Knoten bezogen. Die Gegenpruefung fand zwei Fehler daran: bei Fy
und Mx blieb die Abweisung (Rest knapp ueber der Schranke), und ein RBE3 mit
vielen Slaves und freiem Master verlor die Gewichtssumme im Quadrat - an
einer Elastomerschicht mit 441 Slaves lag der Master 0,198 mm neben der
exakten Zwangsbedingung.

Behebung (Nachbesserung 1, 16.11.2026): Die Matrix ist wieder die von
e2799fa2. Scheitert die Pruefung an einem Modell mit Starrkoerpern und hat
die Zerlegung keinen Pivot angehoben, rechnet LinearSolver.solve das
Residuum mit getrenntem Strafanteil (statik3d.strafanteil): K₀ u +
Σ k Gᵀ (G u) - F, den Rest im Zeilenraum der Kopplungen als Verletzung der
Zwangsbedingung (gegen 0,000001 max|u|), den Rest ausserhalb gegen dieselbe
Schranke wie bisher. Die automatische Fesselung bezieht sich auf die
Hauptdiagonale ohne die Straffedern der frei definierten RBE3 (Merkmal
rbe3_fesselung_bezug, Stand 70, Fehlerkorrektur: ein Gelenkstab neben einer
Flaeche mit 441 Slaves bog sich auf c0dc985c um 0 statt 0,794 mm).

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


def test_ruecknahme():
    """Ruecknahmeprobe: ohne die Pruefung mit getrenntem Strafanteil
    (strafanteil.PRUEFUNG = False) bricht der gesunde Ring wieder mit
    „numerisch singulaer" ab - sie ist es, die ihn rechnen laesst."""
    from statik3d import solver, strafanteil as sa
    sa.PRUEFUNG = False
    try:
        m, _b, _p, _rk = modell(1)
        try:
            _still(solver.solve_static, m, case="LF1")
            txt = "rechnet"
        except RuntimeError as ex:
            txt = str(ex)
    finally:
        sa.PRUEFUNG = True
    check("Ruecknahme: ohne getrennten Strafanteil „numerisch singulaer“", "singul" in txt, txt[:120])


def test_gelenkstab_neben_rbe3():
    """Automatische Fesselung (Merkmal rbe3_fesselung_bezug, Stand 70): ein
    gelenkig gelagerter Stab (L = 2 m, I = 1 000 000 mm⁴, F = 1 kN in der
    Mitte) neben einer Stahlschicht mit frei definiertem RBE3 auf 441 Slaves.
    Hand: w = F L³/(48 E I) = 0,793651 mm, Endverdrehung F L²/(16 E I).
    c0dc985c: 0,000000 mm (Verschiebungen und Drehungen des Stabes still
    festgehalten, Bezug samt Straffeder des RBE3)."""
    from tests.pruefkoerper import quader
    from statik3d.model import Material, Section
    from statik3d import solver
    Ls, Is = 2.0, 1e-6
    m, _ids = quader("hex8", 20, 20, 1, 0.4, 0.4, 0.02, E=E, nu=0.3)
    X0 = np.asarray(m.nodes, float)
    oben = [k for k in range(m.nn) if abs(X0[k, 2] - 0.02) < 1e-9]
    for k in range(m.nn):
        if abs(X0[k, 2]) < 1e-9:
            m.fix(k, [0, 1, 2])
    P = m.add_node(0.2, 0.2, 0.12)
    m.add_starrkoerper(P, oben, "RBE3", name="Flaeche")
    m.add_material(Material("ST2", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q2", A=1e-3, Iy=Is, Iz=Is, It=1e-6, zmax=0.05, ymax=0.05))
    a, c, b = m.add_node(2.0, 0, 0), m.add_node(3.0, 0, 0), m.add_node(4.0, 0, 0)
    m.add_element("beam", [a, c], "ST2", "Q2")
    m.add_element("beam", [c, b], "ST2", "Q2")
    m.fix(a, [0, 1, 2, 3])
    m.fix(b, [1, 2])
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(c, Fz=-F, case="LF1")
    m.load_node(P, Fz=-1e5, case="LF1")
    res = _still(solver.solve_static, m, case="LF1")
    u = np.asarray(res.u, float).reshape(-1, 6)
    nah("Gelenkstab neben RBE3 (441 Slaves): w(Mitte) = F L³/(48 E I)", -u[c, 2] * 1e3,
        F * Ls ** 3 / (48 * E * Is) * 1e3, 0.00001)
    nah("Gelenkstab neben RBE3: Endverdrehung = F L²/(16 E I)", abs(u[a, 4]) * 1e3,
        F * Ls ** 2 / (16 * E * Is) * 1e3, 0.00001, "mrad")


def test_merkmal():
    """Merkmal rbe3_fesselung_bezug: Stand 70, Fehlerkorrektur; betrifft den
    frei definierten RBE3, nicht Scheibe und nicht RBE2."""
    from statik3d import rechenverfahren as rv, solver
    mk = rv.merkmal("rbe3_fesselung_bezug")
    check("Merkmal rbe3_fesselung_bezug: Stand 70, Fehlerkorrektur, VERFAHRENSSTAND >= 70",
          mk is not None and mk.wechsel[-1].stand == 70 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-ring" and rv.VERFAHRENSSTAND >= 70,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m_ring = modell(1)[0]
    m_scheibe = modell(1, name="Scheibe F1")[0]
    m_rbe2 = modell(1, name="R2", art="RBE2")[0]
    werte = [mk.betrifft(x) for x in (m_ring, m_scheibe, m_rbe2)]
    check("betrifft: RBE3 Ring ja; Scheibe und RBE2 nein", werte == [True, False, False], werte)
    an = _still(solver.solve_all, m_ring, workers=1, design=False)
    an2 = _still(solver.solve_all, m_scheibe, workers=1, design=False)
    t_ja, t_nein = mk.im_ergebnis(m_ring, an), mk.im_ergebnis(m_scheibe, an2)
    check("im Ergebnis: LF1 genannt, bei der Scheibe nichts", "LF1" in t_ja and t_nein == "",
          f"{t_ja!r} / {t_nein!r}")


NAMEN = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]


def _last_modell(n_stab, last, name):
    m, b, p, rk = modell(n_stab, name=name)
    m.load_cases["LF1"].nodal_loads = []
    m.load_node(p, case="LF1", **last)
    return m, b, p, rk


def exakt_allgemein(m, master, slaves, lasten: dict, frei=None):
    """Wie exakt(), fuer beliebige Knotenlasten {Knoten: {"Fy": ...}} und mit
    den freien FHG ``frei`` (Vorgabe: alle ausser Knoten 0)."""
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
    G = g_definition(X, master, slaves)
    n = K.shape[0]
    fr = np.arange(6, n) if frei is None else np.asarray(frei)
    Fv = np.zeros(n)
    for kn, d in lasten.items():
        for k, v in d.items():
            Fv[6 * kn + NAMEN.index(k)] += v
    Gf = sparse.csr_matrix(G[:, fr])
    Aks = sparse.bmat([[K[fr][:, fr], Gf.T], [Gf, None]]).tocsc()
    x = sla.spsolve(Aks, np.concatenate([Fv[fr], np.zeros(6)]))
    u = np.zeros(n)
    u[fr] = x[:len(fr)]
    return u[:6 * m.nn].reshape(-1, 6)


def test_lastrichtungen():
    """Befund 1 der Gegenpruefung: derselbe gesunde Ring bei Fy, Mx (1 und
    100 kNm), Fx, My und Fy mit Fz - allgemein und als Scheibe. ef235e50
    wies Fy und Mx als „numerisch singulaer" ab (Rest 0,0000011 bis
    0,0000017 gegen 0,000001)."""
    from statik3d import solver
    lasten = (dict(Fy=1e4), dict(Mx=1e3), dict(Mx=1e5), dict(Fx=1e5), dict(My=1e3), dict(Fy=1e4, Fz=-1e3))
    for name in ("Ring", "Scheibe F1"):
        for last in lasten:
            titel = f"{name}, {', '.join(f'{k} {v:g}' for k, v in last.items())}"
            m, b, p, rk = _last_modell(1, last, name)
            try:
                res = _still(solver.solve_static, m, case="LF1")
            except RuntimeError as ex:
                check(f"{titel}: rechnet", False, str(ex)[:160])
                continue
            check(f"{titel}: rechnet", True)
            u = np.asarray(res.u, float)[:6 * m.nn].reshape(-1, 6)
            ue = exakt_allgemein(m, p, rk, {p: last})
            dv = float(np.abs(u[:, :3] - ue[:, :3]).max()) * 1e3
            check(f"{titel}: Verschiebungen gegen exakte Zwangsbedingung <= 0,00001 mm", dv <= 1e-5,
                  f"Abweichung {dv:.7f} mm bei max|u| {np.abs(ue[:, :3]).max() * 1e3:.6f} mm")
            R0 = np.asarray(res.reactions, float)[0, :3]
            Fs = np.array([last.get(k, 0.0) for k in NAMEN[:3]])
            dR = float(np.abs(R0 + Fs).max())
            check(f"{titel}: Auflagerkraft gleich Last (0,000001 der Last)",
                  dR <= 1e-6 * max(float(np.abs(Fs).max()), 1e3), f"Abweichung {dR:.5f} N")


def test_viele_slaves():
    """Befund 2 der Gegenpruefung: allgemeiner RBE3 mit 441 Slaves auf einer
    Elastomerschicht 0,4 x 0,4 x 0,02 m (hex8 20 x 20 x 1, E = 5 N/mm²),
    Unterseite gelagert, Master 0,1 m ueber der Mitte frei, Fz = 160 kN
    (1 N/mm²). ef235e50: Master 0,198 mm neben der exakten Zwangsbedingung
    (Spalt F/k (1 + 1/n)), e2799fa2: 0,000001 mm."""
    from tests.pruefkoerper import quader
    from statik3d import solver
    nx, Lq, H, Fz = 20, 0.4, 0.02, 1.6e5
    m, ids = quader("hex8", nx, nx, 1, Lq, Lq, H, E=5e6, nu=0.3)
    X0 = np.asarray(m.nodes, float)
    oben = [k for k in range(m.nn) if abs(X0[k, 2] - H) < 1e-9]
    unten = [k for k in range(m.nn) if abs(X0[k, 2]) < 1e-9]
    for k in unten:
        m.fix(k, [0, 1, 2])
    P = m.add_node(Lq / 2, Lq / 2, H + 0.1)
    m.add_starrkoerper(P, oben, "RBE3", name="Flaeche")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(P, Fz=-Fz, case="LF1")
    try:
        res = _still(solver.solve_static, m, case="LF1")
    except RuntimeError as ex:
        check("441 Slaves: rechnet", False, str(ex)[:160])
        return
    u = np.asarray(res.u, float)[:6 * m.nn].reshape(-1, 6)
    n = 6 * m.nn
    fest = {6 * k + j for k in unten for j in range(3)}
    # frei: Verschiebungen der Volumenknoten (ohne Lager) und alle FHG des Masters
    frei = [i for i in range(n) if i not in fest and (i % 6 < 3 or i // 6 == P)]
    ue = exakt_allgemein(m, P, oben, {P: {"Fz": -Fz}}, frei=frei)
    nah("441 Slaves: Masterverschiebung gegen exakte Zwangsbedingung", -u[P, 2] * 1e3, -ue[P, 2] * 1e3, 0.00001)
    dv = float(np.abs(u[:P, :3] - ue[:P, :3]).max()) * 1e3
    check("441 Slaves: Volumenknoten gegen exakte Zwangsbedingung <= 0,00001 mm", dv <= 1e-5, f"{dv:.7f} mm")


def test_speichen_aus_bleibt_abgewiesen():
    """Schutz: sind die Speichen abgeschaltet (Situation), haengen die 64
    Ringknoten nur am RBE3 - 186 Bewegungen ohne Steifigkeit (3 x 64 - 6).
    Das bleibt eine Abweisung; die neue Pruefung greift nur ohne angehobene
    Pivots. (ef235e50 rechnete hier mit Ringknoten bis 41 mm weit.)"""
    from statik3d.model import Situation
    from statik3d import solver
    m, b, p, rk = modell(1)
    ring = set(rk)
    speichen = [i for i, e in enumerate(m.elements) if e.typ == "beam" and int(e.nodes[1]) in ring]
    m.situationen["s"] = Situation("s", "", speichen)
    m.load_cases["LF1"].situation = "s"
    try:
        _still(solver.solve_static, m, case="LF1")
        txt = "rechnet"
    except RuntimeError as ex:
        txt = str(ex)
    check("Schutz: Ring mit abgeschalteten Speichen wird abgewiesen („singulaer“)", "singul" in txt, txt[:120])


def test_automatische_fesselung():
    """Schutz: Bezug der automatischen Fesselung ohne die Straffedern - am
    gesunden Ring wird kein FHG mit Steifigkeit der Elemente festgehalten
    (c0dc985c: die Drehungen des Kragarms, w(P) 0,135 statt 0,848 mm)."""
    from statik3d import assemble as asm
    m, b, p, rk = modell(1)
    K = asm.stiffness(m)
    sk = list(m.starrkoerper)
    m.starrkoerper.clear()
    K0 = asm.stiffness(m)
    m.starrkoerper.extend(sk)
    _f, _v, auto = asm.gesperrte_und_automatische(m, K)
    d0 = np.abs(np.asarray(K0.diagonal()).ravel())
    mit = np.flatnonzero(auto & (d0 > 0))
    check("Schutz: kein FHG mit Elementsteifigkeit automatisch festgehalten", mit.size == 0,
          f"{mit.size} FHG, z. B. {mit[:6].tolist()}")


def test_strafanteil_getrennt():
    """Schutz: der getrennte Strafanteil (K._strafanteil) gibt genau die Matrix
    wieder - K - K₀ = Σ k Gᵀ G, die Zeilen K₀R sind die von K₀ (RBE3 allgemein,
    Scheibe und RBE2)."""
    from scipy import sparse
    from statik3d import assemble as asm
    for name, art in (("Ring", "RBE3"), ("Scheibe F1", "RBE3"), ("R2", "RBE2")):
        m, b, p, rk = modell(1, name=name, art=art)
        K = asm.stiffness(m).tocsr()
        sa = getattr(K, "_strafanteil", None)
        if not check(f"Strafanteil {name}: vorhanden", sa is not None and len(sa.kopplungen) == 1):
            continue
        sk = list(m.starrkoerper)
        m.starrkoerper.clear()
        K0 = asm.stiffness(m).tocsr()
        m.starrkoerper.extend(sk)
        P = sparse.csr_matrix(K.shape)
        for kp in sa.kopplungen:
            Gd = kp.G.toarray()
            r, c = np.meshgrid(kp.fhg, kp.fhg, indexing="ij")
            P = P + sparse.coo_matrix(((kp.k * (Gd.T @ Gd)).ravel(), (r.ravel(), c.ravel())), shape=K.shape)
        rel = abs(K - K0 - P).max() / abs(P).max()
        check(f"Strafanteil {name}: K - K0 = Summe k GᵀG", rel <= 1e-12, f"relativ {rel:.1e}")
        dR = abs(sa.K0R - K0[sa.R]).max() if sa.R.size else 0.0
        check(f"Strafanteil {name}: Zeilen K0R gleich K0", dR == 0.0, f"{dR}")


def main():
    tests = [test_ring_allgemein, test_ring_scheibe, test_lastrichtungen, test_viele_slaves,
             test_speichen_aus_bleibt_abgewiesen, test_automatische_fesselung, test_strafanteil_getrennt,
             test_pruefung_kraftsumme, test_verteilung_hand, test_ruecknahme, test_gelenkstab_neben_rbe3,
             test_merkmal]
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
