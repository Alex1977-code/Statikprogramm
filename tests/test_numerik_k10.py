"""
Runde k10 (15.11.2026, vom Anwender freigegeben), Gruppe Numerik.

Punkt 1, Verfahrensstand 68: eine starre Knotenkopplung an einem RBE2-Knoten
brach mit „Gleichungssystem numerisch singulär (Residuum 0,0000044, Schranke
0,000001)" ab. Ursache in assemble.stiffness: der Strafbeiwert der
Starrkoerper (1e4-mal die groesste Hauptdiagonale) bezog sich auf K *samt*
den Straffedern der starren Kopplungen, die selbst schon 1e4-mal die groesste
Hauptdiagonale der Elemente sind. Der Starrkoerper wurde 1e8-mal so steif wie
die Elemente (Kragarm unten: 8,75e16 gegen 7e8 N/m). Seither bezieht er sich
auf Elemente, Federlager und endliche Kopplungsfedern - wie die starre
Kopplung selbst. Ohne starre Kopplung bleibt die Matrix bitgleich.

Punkt 2 (nur Absturz, kein Stand): eine Schwingungsberechnung mit nur einer
Punktmasse brach mit „ARPACK error -9999: Could not build an Arnoldi
factorization" ab. Ursache: mit n Freiheitsgraden mit Masse hat der Krylov-
Raum des Shift-Invert-Verfahrens (Vektoren M x) hoechstens n Richtungen,
ARPACK verlangt aber mindestens 20 Lanczos-Vektoren. Seither wird bei wenigen
Massen-FHG statisch kondensiert und dicht geloest; es gibt so viele
Eigenformen, wie das System hat, mit Klartext, wenn weniger als angefordert.

Sollwerte, je zwei Wege:
* Kragarm L = 3 m, E I = 210 000 N/mm² · 8 000 cm⁴, F = 1 kN am Ende:
  w = F L³ / (3 E I) = 0,5357 mm (Hand) und dasselbe Modell mit dem Lastknoten
  als zweitem Slave des RBE2 statt der starren Kopplung (Gegenrechnung).
* Punktmasse 100 kg am masselosen Kragarm: f = √(3 E I / (m L³)) / 2π
  = 21,7447 Hz (Hand) und aus der statischen Steifigkeit k = F / w des
  Programms (zweiter Programmweg); Punktmasse an einer Feder k = 1 000 kN/m:
  f = √(k/m) / 2π = 15,9155 Hz.

Runde k10b (zweite Runde Modalanalyse, nur Absturz und Meldung, kein Stand):
* Der dichte Weg passte die Zahl der Formen nicht an die gelieferten Paare an
  (IndexError bei einer Zusatzmasse vom Rang 1 und bei 0,000000000001 kg
  neben 100 kg). Seither zaehlt der Rang der Massenmatrix (Zusatzmasse m n nᵀ
  je Knoten), und Paare im Rundungsrauschen fallen mit Klartext weg. Am
  ARPACK-Weg lieferte eine schraege Wand mit 8 Knoten (Rang 8) bei 10
  angeforderten Formen eine Scheinform mit 0 Hz; Sollwerte aus der gedrehten
  Wand mit achsparalleler Masse und aus eigh(M, K) dicht.
* Der dichte Weg hielt eine volle Matrix n x n_masse (1 Mio. FHG, 201 Spalten:
  1,6 GB); seither nur n_masse² und je Form einen Vektor, Grenze
  MODAL_DICHT_MAX = 2000 Massen-FHG, darueber ARPACK mit Klartext.
* Ein loser RBE3-Slave (ohne Masse, ohne Halt) gab „ARPACK error -9999" oder
  still eine Form mit beliebig mitlaufendem Slave; seither Klartext wie in
  der Statik.

Aufruf:  python -m tests.test_numerik_k10
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


def close(name, ist, soll, rel=1e-6, einheit="mm"):
    ok = abs(ist - soll) <= rel * max(abs(soll), 1e-12)
    return check(name, ok, f"ist {ist:.6f} {einheit}, soll {soll:.6f} {einheit}")


E = 210e9
L = 3.0
I = 8e-5
A = 1e-2
F = 1e3
MASSE = 100.0
HAND = F * L ** 3 / (3 * E * I)                     # 0,5357 mm
INF3 = [float("inf")] * 3
ACHSEN = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def modell(art, maske="keine", mit_arm=False, teile=1, rho=0.0):
    """Kragarm a-b (x = 0..L, eingespannt in a), Q = (L, 0, 0,5) per RBE2 an b,
    Lastknoten P = (L, 0, 0,5) ohne Element.

    art: 'starr'  P per starrer Kopplung an Q (der Fall des Befunds)
         'slave'  P als zweiter Slave des RBE2 (Gegenrechnung, ohne Kopplung)
         'feder'  P per Feder 1e12 N/m an Q (heute schon rechnend: bitgleich)
         'nur_rbe2' kein Q, P direkt per RBE2 an b (ohne Kopplung: bitgleich)
         'nur_starr' P per starrer Kopplung an b, kein Starrkoerper (bitgleich)
         'mitte' P = b-Lage per RBE2 an b (Schwingung)
    maske: 'keine' | 'situation' | 'aus' (zweiter Kragarm abgeschaltet)."""
    from statik3d.model import Model, Material, Section, Kopplung, Situation
    m = Model("k10")
    m.add_material(Material("ST", E=E, nu=0.3, rho=rho, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    if teile == 1:
        m.netz.stabteilung = 1
    knoten = [m.add_node(L * i / teile, 0, 0) for i in range(teile + 1)]
    for i in range(teile):
        m.add_element("beam", [knoten[i], knoten[i + 1]], "ST", "Q")
    a, b = knoten[0], knoten[-1]
    m.fix(a, "all")
    if art == "mitte":
        p = m.add_node(L, 0, 0)
        m.add_starrkoerper(p, [b], "RBE2", name="A")
    elif art == "nur_rbe2":
        p = m.add_node(L, 0, 0.5)
        m.add_starrkoerper(b, [p], "RBE2", name="K")
    elif art == "nur_starr":
        p = m.add_node(L, 0, 0)
        m.kopplungen.append(Kopplung(p, b, ACHSEN, INF3, "starr"))
    else:
        q = m.add_node(L, 0, 0.5)
        p = m.add_node(L, 0, 0.5)
        if art == "slave":
            m.add_starrkoerper(b, [q, p], "RBE2", name="K")
        else:
            m.add_starrkoerper(b, [q], "RBE2", name="K")
            werte = INF3 if art == "starr" else [1e12] * 3
            m.kopplungen.append(Kopplung(p, q, ACHSEN, werte, art))
    if mit_arm:
        c = m.add_node(0, 2, 0)
        d = m.add_node(L, 2, 0)
        e_arm = m.add_element("beam", [c, d], "ST", "Q")
        m.fix(c, "all")
        if maske == "aus":
            m.add_member("S2", [e_arm], aus=True)
    m.add_load_case("LF1", "G")
    if maske == "situation" and mit_arm:
        m.situationen["s"] = Situation("s", "", [len(m.elements) - 1])
        m.load_cases["LF1"].situation = "s"
    return m, b, p


def rechne(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    r = an.cases["LF1"]
    return an, np.asarray(r.u).reshape(-1, 6), np.asarray(r.reactions).reshape(-1, 6)


def _w(art, maske="keine", mit_arm=False):
    m, b, p = modell(art, maske, mit_arm)
    m.load_node(p, Fz=-F, case="LF1")
    an, u, r = rechne(m)
    return u, r, b, p, an


# --------------------------------------------------------------------------
# Punkt 1: starre Kopplung an einem RBE2-Knoten
# --------------------------------------------------------------------------
def test_starre_kopplung_rbe2():
    u0, _r0, b, p, _an = _w("slave")
    gegen_b, gegen_p = -u0[b, 2], -u0[p, 2]
    close("Gegenrechnung (P als zweiter Slave des RBE2): w(b) = F L³/(3 E I)", gegen_b * 1e3, HAND * 1e3, 1e-5)
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        try:
            u, r, b, p, _an = _w("starr", maske, mit_arm)
        except Exception as ex:          # noqa: BLE001
            check(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: rechnet", False,
                  f"{type(ex).__name__}: {str(ex)[:200]}")
            continue
        check(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: rechnet", True)
        close(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: w(b) = F L³/(3 E I)", -u[b, 2] * 1e3,
              HAND * 1e3, 1e-5)
        close(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: w(b) gleich Gegenrechnung", -u[b, 2] * 1e3,
              gegen_b * 1e3, 1e-6)
        close(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: w(P) gleich Gegenrechnung", -u[p, 2] * 1e3,
              gegen_p * 1e3, 1e-6)
        close(f"Starre Kopplung an RBE2-Knoten, Maske {maske}: Summe der Auflagerkräfte Z = F", r[:, 2].sum(),
              F, 1e-6, "N")


def _diag_max(K):
    return float(np.abs(K.diagonal()).max())


def test_strafbeiwert():
    """Der groesste Strafbeiwert bleibt bei 1e4-mal der Elementsteifigkeit
    (RBE2 1e4, starre Kopplung 1e4), nicht 1e8."""
    from statik3d import assemble as asm
    m, _b, _p = modell("starr")
    K0 = asm._assemble_triplets(m, asm._matrix_chunk, None)
    K = asm.stiffness(m)
    q = _diag_max(K) / _diag_max(K0)
    check("Strafbeiwert: größte Hauptdiagonale höchstens 1e4-fach der Elemente (mal Zahl der Beiträge)",
          q <= 1e4 * 4, f"Verhältnis {q:,.0f}".replace(",", " "))


def test_bitgleich():
    """Ohne starre Kopplung neben einem Starrkoerper ist die Matrix bitgleich
    mit dem bisherigen Bezug (Schalter STARRKOERPER_BEZUG_ALT)."""
    from statik3d import assemble as asm
    for art in ("feder", "nur_rbe2", "nur_starr"):
        m, _b, _p = modell(art)
        K_neu = asm.stiffness(m)
        asm.STARRKOERPER_BEZUG_ALT = True
        try:
            K_alt = asm.stiffness(m)
        finally:
            asm.STARRKOERPER_BEZUG_ALT = False
        d = abs(K_neu - K_alt)
        check(f"Bitgleich ohne starre Kopplung neben Starrkörper: {art}", d.nnz == 0 or d.max() == 0.0,
              f"größte Abweichung {d.max() if d.nnz else 0.0}")


def test_ruecknahme():
    """Mit dem alten Bezug kommt der Befund zurueck - das belegt die Ursache."""
    from statik3d import assemble as asm
    asm.STARRKOERPER_BEZUG_ALT = True
    try:
        try:
            _w("starr")
            ok, txt = False, "rechnete"
        except RuntimeError as ex:
            ok, txt = "singul" in str(ex), str(ex)[:120]
    finally:
        asm.STARRKOERPER_BEZUG_ALT = False
    check("Rücknahmeprobe: alter Bezug (K samt Straffedern) ergibt „singulär“", ok, txt)


def test_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("starrkoerper_strafe_bezug")
    check("Merkmal starrkoerper_strafe_bezug: Stand 68, Fehlerkorrektur, VERFAHRENSSTAND >= 68",
          mk is not None and mk.wechsel[-1].stand == 68 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-num" and rv.VERFAHRENSSTAND >= 68,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m_ja, _b, _p = modell("starr")
    m_feder, _b, _p = modell("feder")
    m_rbe2, _b, _p = modell("nur_rbe2")
    m_kp, _b, _p = modell("nur_starr")
    werte = [mk.betrifft(x) for x in (m_ja, m_feder, m_rbe2, m_kp)]
    check("betrifft: RBE2 mit starrer Kopplung ja; mit Feder, RBE2 allein, starre Kopplung allein nein",
          werte == [True, False, False, False], werte)
    m_ja.load_node(_p, Fz=-F, case="LF1")
    an = _still(__import__("statik3d.solver", fromlist=["x"]).solve_all, m_ja, workers=1, design=False)
    t_ja = mk.im_ergebnis(m_ja, an)
    m_feder.load_node(modell("feder")[2], Fz=-F, case="LF1")
    an2 = _still(__import__("statik3d.solver", fromlist=["x"]).solve_all, m_feder, workers=1, design=False)
    t_nein = mk.im_ergebnis(m_feder, an2)
    check("im Ergebnis: LF1 genannt, beim Modell mit Feder nichts", "LF1" in t_ja and t_nein == "",
          f"{t_ja!r} / {t_nein!r}")


# --------------------------------------------------------------------------
# Punkt 2: Schwingung mit wenigen Massen-Freiheitsgraden
# --------------------------------------------------------------------------
def test_punktmasse_kragarm():
    from statik3d import solver
    hand = math.sqrt(3 * E * I / (MASSE * L ** 3)) / (2 * math.pi)
    for maske, mit_arm in (("keine", False), ("situation", True), ("aus", True)):
        m, b, p = modell("mitte", maske, mit_arm, teile=8)
        m.add_punktmasse(p, MASSE)
        aktiv = m.aktive_elemente("s" if maske == "situation" else "")
        try:
            res = _still(solver.solve_modal, m, 8, workers=1, aktiv=aktiv)
        except Exception as ex:          # noqa: BLE001
            check(f"Punktmasse am masselosen Kragarm, Maske {maske}: Eigenformen gerechnet", False,
                  f"{type(ex).__name__}: {str(ex)[:160]}")
            continue
        fr = np.asarray(res.freqs, float)
        check(f"Punktmasse am masselosen Kragarm, Maske {maske}: 3 Eigenformen (3 Massen-FHG) statt 8",
              len(fr) == 3 and res.modes.shape[0] == 3, f"{len(fr)} Formen: {np.round(fr, 4)}")
        hw = str((res.info or {}).get("moden_hinweis", ""))
        check(f"Punktmasse am masselosen Kragarm, Maske {maske}: Klartext „3 von 8“ im Ergebnis und in der "
              "Zusammenfassung", hw.startswith("3 von 8") and hw in res.summary(), hw[:120])
        close(f"Punktmasse am masselosen Kragarm, Maske {maske}: f₁ = √(3EI/(mL³))/2π", fr[0], hand, 1e-6, "Hz")
        close(f"Punktmasse am masselosen Kragarm, Maske {maske}: f₂ = f₁ (Iy = Iz)", fr[1], hand, 1e-6, "Hz")
        # zweiter Programmweg: statische Steifigkeit am Massenpunkt
        kz, kx = [], []
        for richtung in (2, 0):
            m2, b2, p2 = modell("mitte", maske, mit_arm, teile=8)
            m2.load_node(p2, **({"Fz": -F} if richtung == 2 else {"Fx": -F}), case="LF1")
            _an, u, _r = rechne(m2)
            (kz if richtung == 2 else kx).append(F / -u[p2, richtung])
        f_st = math.sqrt(kz[0] / MASSE) / (2 * math.pi)
        f_ax = math.sqrt(kx[0] / MASSE) / (2 * math.pi)
        close(f"Punktmasse am masselosen Kragarm, Maske {maske}: f₁ gleich √(k/m)/2π aus statischer Rechnung",
              fr[0], f_st, 1e-7, "Hz")
        close(f"Punktmasse am masselosen Kragarm, Maske {maske}: f₃ (längs) gleich √(k/m)/2π aus statischer "
              "Rechnung", fr[2], f_ax, 1e-7, "Hz")
        # Form 1: am Massenpunkt nur Querverschiebung, normiert auf 1
        u1 = np.asarray(res.modes[0])[p]
        check(f"Punktmasse am masselosen Kragarm, Maske {maske}: Form 1 quer, normiert",
              abs(abs(u1[0])) < 1e-6 and abs(max(abs(u1[1]), abs(u1[2])) - 1.0) < 1e-9, np.round(u1[:3], 6))


def test_punktmasse_feder():
    """Ein Knoten mit Federlager in z und einer Punktmasse - ein FHG mit Masse."""
    from statik3d.model import Model, Material, Section
    from statik3d import solver
    k = 1e6
    m = Model("feder")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    a = m.add_node(0, 0, 0)
    n = m.add_node(1, 0, 0)
    m.add_element("beam", [a, n], "ST", "Q")
    m.fix(a, "all")
    m.fix(n, [0, 1, 3, 4, 5])
    s = m.add_node(5, 0, 0)
    m.fix(s, [0, 1, 3, 4, 5])
    m.fix(s, [2], stiffness=[k])
    m.add_punktmasse(s, MASSE)
    try:
        res = _still(solver.solve_modal, m, 4, workers=1)
    except Exception as ex:              # noqa: BLE001
        check("Punktmasse an Feder: Eigenform gerechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
        return
    fr = np.asarray(res.freqs, float)
    hand = math.sqrt(k / MASSE) / (2 * math.pi)
    check("Punktmasse an Feder: eine Eigenform statt 4", len(fr) == 1, np.round(fr, 4))
    close("Punktmasse an Feder: f = √(k/m)/2π", fr[0], hand, 1e-9, "Hz")
    hw = str((res.info or {}).get("moden_hinweis", ""))
    check("Punktmasse an Feder: Klartext „1 von 4 … einen Freiheitsgrad mit Masse“",
          hw.startswith("1 von 4") and "einen Freiheitsgrad" in hw, hw[:120])
    # zweiter Programmweg: statische Rechnung, w = F / k
    m.add_load_case("LF1", "G")
    m.load_node(s, Fz=-F, case="LF1")
    _an, u, _r = rechne(m)
    close("Punktmasse an Feder: f gleich √(F/(w m))/2π aus statischer Rechnung", fr[0],
          math.sqrt(F / -u[s, 2] / MASSE) / (2 * math.pi), 1e-9, "Hz")


def test_schutz_arpack():
    """Viele Massen-FHG: weiter ARPACK, ohne Hinweis (Rayleigh wie in k9)."""
    from statik3d import solver
    rho = 1.0 / (A * L)
    hand_f = math.sqrt(3 * E * I / ((MASSE + 33.0 / 140.0) * L ** 3)) / (2 * math.pi)
    m, _b, p = modell("mitte", teile=8, rho=rho)
    m.add_punktmasse(p, MASSE)
    res = _still(solver.solve_modal, m, 2, workers=1)
    check("Schutz: Stab mit Masse rechnet weiter mit ARPACK, zwei Formen, kein Hinweis",
          res.info.get("eigenloeser") == "ARPACK" and len(res.freqs) == 2 and not res.info.get("moden_hinweis"),
          f"{res.info.get('eigenloeser')} {len(res.freqs)}")
    close("Schutz: f₁ nach Rayleigh (wie test_maske_starrkoerper_k9)", float(res.freqs[0]), hand_f, 1e-5, "Hz")


# --------------------------------------------------------------------------
# Runde k10b: Rang der Massenmatrix, loser RBE3-Slave, Speicher des dichten
# Wegs, Grenze zum ARPACK-Weg
# --------------------------------------------------------------------------
def _zusatz(m, knoten, richtung, masse):
    """Zusatzmasse masse · n nᵀ je Knoten (wie schwingung.zusatzmassen)."""
    import scipy.sparse as sp
    n = np.asarray(richtung, float)
    n = n / np.linalg.norm(n)
    blk = masse * np.outer(n, n)
    rows, cols, vals = [], [], []
    for k in knoten:
        for a in range(3):
            for c in range(3):
                if blk[a, c] != 0.0:
                    rows.append(6 * k + a)
                    cols.append(6 * k + c)
                    vals.append(blk[a, c])
    return sp.csr_matrix((vals, (rows, cols)), shape=(m.ndof, m.ndof))


def _drehung_auf_z(n):
    """Drehmatrix Q mit Q n = e_z (Rodrigues)."""
    n = np.asarray(n, float) / np.linalg.norm(n)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(n, z)
    s, c = np.linalg.norm(v), float(n @ z)
    if s < 1e-15:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / s ** 2)


def wand(n_knoten, achse=(1.0, 0.0, 0.0), masse_richtung=(0.36, 0.48, 0.8), masse=50.0):
    """Masseloser Kragarm (L = 3 m, n_knoten Stabelemente) entlang ``achse``,
    eingespannt in a; an jedem freien Knoten eine Zusatzmasse masse · n nᵀ."""
    from statik3d.model import Model, Material, Section
    m = Model("wand")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    e = np.asarray(achse, float) / np.linalg.norm(achse)
    kn = [m.add_node(*(e * L * i / n_knoten)) for i in range(n_knoten + 1)]
    for i in range(n_knoten):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    return m, _zusatz(m, kn[1:], masse_richtung, masse)


def _dicht_eigh(m, Z):
    """Zweiter Weg ohne Eigenloeser des Programms: eigh(M, K) dicht auf den
    freien FHG (K positiv definit, M semidefinit), Frequenzen aufsteigend."""
    import scipy.linalg as sla
    from statik3d import assemble as asm
    K = asm.stiffness(m)
    M = (asm.mass(m) + Z).tocsr()
    fixed, _v = asm.constrained_dofs(m, K)
    fi = np.where(~fixed)[0]
    nu = sla.eigh(M[fi][:, fi].toarray(), K[fi][:, fi].toarray(), eigvals_only=True)
    nu = np.sort(nu[nu > 1e-9 * nu.max()])[::-1]
    return np.sqrt(1.0 / nu) / (2 * math.pi)


def test_zusatzmasse_rang1():
    """Masseloser Kragarm, Zusatzmasse 100 kg · n nᵀ mit schräger Normale am
    Ende: drei FHG mit Masse, eine Eigenform (Befund k10 Runde 1: IndexError)."""
    from statik3d import solver
    n = np.array([0.36, 0.48, 0.8])
    m, _Z = wand(8, masse_richtung=n)
    Z = _zusatz(m, [8], n, MASSE)
    # Hand: Nachgiebigkeit des Kragarmendes L/EA längs, L³/(3EI) quer
    c = n[0] ** 2 * L / (E * A) + (n[1] ** 2 + n[2] ** 2) * L ** 3 / (3 * E * I)
    hand = math.sqrt(1.0 / (MASSE * c)) / (2 * math.pi)
    dicht = _dicht_eigh(m, Z)
    close("Rang-1-Zusatzmasse: Gegenrechnung eigh(M, K) gleich Hand", dicht[0], hand, 1e-9, "Hz")
    check("Rang-1-Zusatzmasse: Gegenrechnung hat genau eine Form", len(dicht) == 1, np.round(dicht, 4))
    try:
        res = _still(solver.solve_modal, m, 8, workers=1, zusatzmasse=Z)
    except Exception as ex:              # noqa: BLE001
        check("Rang-1-Zusatzmasse: rechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
        return
    fr = np.asarray(res.freqs, float)
    check("Rang-1-Zusatzmasse: genau eine Eigenform", len(fr) == 1 and res.modes.shape[0] == 1, np.round(fr, 6))
    close("Rang-1-Zusatzmasse: f = 1/(2π √(m nᵀ C n))", fr[0], hand, 1e-9, "Hz")
    hw = str(res.info.get("moden_hinweis", ""))
    check("Rang-1-Zusatzmasse: Klartext „1 von 8 … 3 Freiheitsgrade … in einer Richtung“",
          hw.startswith("1 von 8") and "3 Freiheitsgrade" in hw and "einer Richtung" in hw, hw[:160])


def test_kleinmasse():
    """100 kg am RBE2-Master, 0,000000000001 kg am Slave: die Formen der
    kleinen Masse liegen im Rundungsrauschen (Befund k10 Runde 1: IndexError)."""
    from statik3d import solver
    hand = math.sqrt(3 * E * I / (MASSE * L ** 3)) / (2 * math.pi)
    for mk in (1e-12, 1e-9):
        m, b, p = modell("mitte", teile=8)
        m.add_punktmasse(p, MASSE)
        m.add_punktmasse(b, mk)
        try:
            res = _still(solver.solve_modal, m, 8, workers=1)
        except Exception as ex:          # noqa: BLE001
            check(f"Kleinmasse {mk:g} kg neben 100 kg: rechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
            continue
        fr = np.asarray(res.freqs, float)
        check(f"Kleinmasse {mk:g} kg neben 100 kg: drei Formen der großen Masse", len(fr) == 3, np.round(fr, 4))
        close(f"Kleinmasse {mk:g} kg: f₁ = √(3EI/(mL³))/2π", fr[0], hand, 1e-6, "Hz")
        close(f"Kleinmasse {mk:g} kg: f₂ = f₁", fr[1], hand, 1e-6, "Hz")
        hw = str(res.info.get("moden_hinweis", ""))
        check(f"Kleinmasse {mk:g} kg: Klartext „3 von 8 … nicht auflösbar“",
              hw.startswith("3 von 8") and "nicht auflösbar" in hw, hw[:160])


def test_wand_rang():
    """Schräge Zusatzmasse an 8 Knoten: 24 FHG mit Masse, Rang 8 - genau 8
    Eigenformen, gleich der gedrehten Wand mit achsparalleler Masse und der
    dichten Gegenrechnung. Vorher bei 10 Formen eine Scheinform mit 0 Hz,
    bei 20 IndexError."""
    from statik3d import solver
    n = np.array([0.36, 0.48, 0.8])
    m1, Z1 = wand(8, masse_richtung=n)
    Q = _drehung_auf_z(n)
    m2, Z2 = wand(8, achse=Q @ np.array([1.0, 0.0, 0.0]), masse_richtung=(0.0, 0.0, 1.0))
    ref = _dicht_eigh(m1, Z1)
    check("Wand: Gegenrechnung eigh(M, K) hat 8 Formen", len(ref) == 8, np.round(ref, 3))
    r2 = _still(solver.solve_modal, m2, 8, workers=1, zusatzmasse=Z2)
    f2 = np.asarray(r2.freqs, float)
    check("Wand gedreht (Masse achsparallel, 8 FHG mit Masse): 8 Formen", len(f2) == 8, np.round(f2, 3))
    check("Wand gedreht: gleich der dichten Gegenrechnung (relativ 0,000001)",
          len(f2) == 8 and np.allclose(f2, ref, rtol=1e-6), np.round(f2 / ref[:len(f2)] - 1, 9))
    for nm in (8, 10, 12, 20):
        try:
            r = _still(solver.solve_modal, m1, nm, workers=1, zusatzmasse=Z1)
        except Exception as ex:          # noqa: BLE001
            check(f"Wand schräg, {nm} Formen angefordert: rechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
            continue
        f = np.asarray(r.freqs, float)
        check(f"Wand schräg, {nm} Formen angefordert: genau 8 Formen, keine mit 0 Hz",
              len(f) == 8 and f.min() > 1.0, np.round(f, 3))
        check(f"Wand schräg, {nm} Formen angefordert: gleich der gedrehten Wand (relativ 0,000001)",
              len(f) == 8 and np.allclose(f, f2, rtol=1e-6), np.round(f[:8], 4))
        hw = str(r.info.get("moden_hinweis", ""))
        if nm > 8:
            check(f"Wand schräg, {nm} Formen angefordert: Klartext „8 von {nm} … 8 unabhängigen Richtungen“",
                  hw.startswith(f"8 von {nm}") and "8 unabhängigen Richtungen" in hw, hw[:160])
    # oberhalb der Grenze des dichten Wegs: 30 Knoten, Rang 30 > 20 Lanczos-Vektoren -> ARPACK
    m3, Z3 = wand(30, masse_richtung=n)
    ref3 = _dicht_eigh(m3, Z3)
    r3 = _still(solver.solve_modal, m3, 8, workers=1, zusatzmasse=Z3)
    f3 = np.asarray(r3.freqs, float)
    check("Wand schräg 30 Knoten (90 FHG mit Masse, Rang 30): ARPACK-Weg, 8 Formen, kein Hinweis",
          r3.info.get("eigenloeser") == "ARPACK" and len(f3) == 8 and not r3.info.get("moden_hinweis"),
          f"{r3.info.get('eigenloeser')} {len(f3)}")
    check("Wand schräg 30 Knoten: gleich der dichten Gegenrechnung (relativ 0,000001)",
          len(f3) == 8 and np.allclose(f3, ref3[:8], rtol=1e-6), np.round(f3, 3))


def test_grenze_dicht():
    """Oberhalb von MODAL_DICHT_MAX bei wenigen Richtungen: ARPACK mit so
    wenigen Lanczos-Vektoren, wie M Richtungen hat - die unteren Formen
    richtig, mit Klartext; ein Abbruch von ARPACK kommt als Klartext."""
    from statik3d import solver
    if not hasattr(solver, "MODAL_DICHT_MAX"):
        check("Grenze des dichten Wegs: MODAL_DICHT_MAX vorhanden", False, "fehlt")
        return
    n = np.array([0.36, 0.48, 0.8])
    m1, Z1 = wand(8, masse_richtung=n)
    ref = _dicht_eigh(m1, Z1)
    alt = solver.MODAL_DICHT_MAX
    solver.MODAL_DICHT_MAX = 10
    try:
        r = _still(solver.solve_modal, m1, 20, workers=1, zusatzmasse=Z1)
    finally:
        solver.MODAL_DICHT_MAX = alt
    f = np.asarray(r.freqs, float)
    check("Grenze (MODAL_DICHT_MAX = 10, 24 FHG mit Masse, Rang 8, 20 Formen): ARPACK, 3 Formen",
          r.info.get("eigenloeser") == "ARPACK" and len(f) == 3, f"{r.info.get('eigenloeser')} {np.round(f, 3)}")
    check("Grenze: die 3 Formen gleich der dichten Gegenrechnung (relativ 0,000001)",
          len(f) == 3 and np.allclose(f, ref[:3], rtol=1e-6), np.round(f, 4))
    hw = str(r.info.get("moden_hinweis", ""))
    check("Grenze: Klartext „3 von 20 … höchstens die unteren 3“", hw.startswith("3 von 20") and "unteren 3" in hw,
          hw[:160])
    # ARPACK bricht ab -> Klartext statt „ARPACK error"
    from scipy.sparse.linalg import ArpackError
    echt = solver.eigsh

    def bricht(*a, **kw):
        raise ArpackError(-9999)
    m4, Z4 = wand(30, masse_richtung=n)
    solver.eigsh = bricht
    try:
        _still(solver.solve_modal, m4, 8, workers=1, zusatzmasse=Z4)
        ok, txt = False, "keine Ausnahme"
    except RuntimeError as ex:
        ok, txt = str(ex).startswith("Eigenschwingungen nicht berechenbar"), str(ex)
    except Exception as ex:              # noqa: BLE001
        ok, txt = False, f"{type(ex).__name__}: {ex}"
    finally:
        solver.eigsh = echt
    check("ARPACK-Abbruch: Klartext „Eigenschwingungen nicht berechenbar“", ok, txt[:200])


def _rbe3_lose(teile, halten=False):
    """Kragarm mit Dichte 7850, Ende b; RBE3-Master P mit Slaves b und dem
    losen Knoten d (ohne Element) - d und P sind ohne Masse und ohne Halt.
    ``halten``: d haengt ueber einen Stab an b (Gegenprobe)."""
    from statik3d.model import Model, Material, Section
    m = Model("rbe3_lose")
    m.add_material(Material("ST", E=E, nu=0.3, rho=7850.0, fy=355e6))
    m.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    kn = [m.add_node(L * i / teile, 0, 0) for i in range(teile + 1)]
    for i in range(teile):
        m.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    m.fix(kn[0], "all")
    d = m.add_node(L, 2, 0)
    p = m.add_node(L, 1, 0)
    if halten:
        m.add_element("beam", [kn[-1], d], "ST", "Q")
    m.add_starrkoerper(p, [kn[-1], d], "RBE3", name="H")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    m.load_node(p, Fz=-F, case="LF1")
    return m


def test_rbe3_lose_schwingung():
    """Loser RBE3-Slave: die Schwingung meldet wie die Statik im Klartext
    (vorher ARPACK -9999 oder, dicht, eine Form mit beliebig mitlaufendem
    Slave ohne Wort)."""
    from statik3d import solver
    for teile, weg in ((1, "dichter Weg"), (8, "ARPACK-Weg")):
        m = _rbe3_lose(teile)
        try:
            _still(solver.solve_modal, m, 8, workers=1)
            ok, txt = False, "keine Meldung, Ergebnis geliefert"
        except RuntimeError as ex:
            txt = str(ex)
            ok = txt.startswith("Eigenschwingungen nicht berechenbar") and "ohne Masse" in txt
        except Exception as ex:          # noqa: BLE001
            ok, txt = False, f"{type(ex).__name__}: {ex}"
        check(f"Loser RBE3-Slave, {weg}: Klartext „Eigenschwingungen nicht berechenbar … ohne Masse“", ok,
              txt[:200])
        try:
            _still(solver.solve_static, m, case="LF1")
            st = "rechnet"
        except RuntimeError as ex:
            st = str(ex)
        check(f"Loser RBE3-Slave, {weg}: die Statik meldet am selben Modell „singulär“", "singulär" in st, st[:120])
    # Gegenprobe: haengt d ueber einen Stab an b, rechnet die Schwingung
    m = _rbe3_lose(8, halten=True)
    try:
        res = _still(solver.solve_modal, m, 4, workers=1)
        check("Gegenprobe: loser Knoten über einen Stab gehalten - rechnet, 4 Formen", len(res.freqs) == 4,
              np.round(res.freqs, 3))
    except Exception as ex:              # noqa: BLE001
        check("Gegenprobe: loser Knoten über einen Stab gehalten - rechnet, 4 Formen", False,
              f"{type(ex).__name__}: {ex}"[:200])


def test_speicher_dicht():
    """Der dichte Weg haelt keine volle Matrix n x n_masse mehr: Spitze in
    _modal_kondensiert hoechstens (k + 20) Vektoren der Laenge n plus die
    kondensierten Matrizen (vorher n x n_masse plus n x k)."""
    import tracemalloc
    from statik3d import solver, assemble as asm
    from statik3d.model import Model, Material, Section
    mo = Model("lang")
    mo.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    mo.add_section(Section("Q", A=A, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    mo.netz.stabteilung = 1
    teile = 2000
    kn = [mo.add_node(L * i / teile, 0, 0) for i in range(teile + 1)]
    for i in range(teile):
        mo.add_element("beam", [kn[i], kn[i + 1]], "ST", "Q")
    mo.fix(kn[0], "all")
    for j in range(1, 21):
        mo.add_punktmasse(kn[j * teile // 20], 10.0)
    K = asm.stiffness(mo)
    M = asm.mass(mo)
    fixed, _v = asm.constrained_dofs(mo, K)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Mff = M[fi][:, fi].tocsc()
    mdf = np.asarray(Mff.diagonal()).ravel()
    n, n_masse, k = Kff.shape[0], int(np.count_nonzero(mdf > 0)), 10
    sigma = -1e-6 * float(np.abs(Kff.diagonal()).mean() / mdf.mean())
    loeser = solver.LinearSolver((Kff - sigma * Mff).tocsc())
    try:
        tracemalloc.start()
        vals, _vecs = solver._modal_kondensiert(loeser, Mff, mdf, sigma, k)
        _cur, spitze = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        loeser.freigeben()
    # (k + 20) Vektoren: die Formen und die Hilfsvektoren je Loesung (gemessen
    # rund 9); die volle Matrix n x n_masse allein waeren 60
    grenze = (k + 20) * n * 8 + 8 * n_masse ** 2 * 8
    check(f"Speicher dichter Weg ({n} FHG, {n_masse} FHG mit Masse, {k} Formen): Spitze höchstens (k + 20) · n · 8 "
          f"Byte + Matrizen", spitze <= grenze, f"Spitze {spitze / 1e6:.2f} MB, Grenze {grenze / 1e6:.2f} MB, "
          f"volle Matrix n x n_masse wäre {n * n_masse * 8 / 1e6:.2f} MB")

def test_merkmal_modal():
    """Merkmal modal_massenrang (Stand 68, Fehlerkorrektur): Modelle mit Teilen
    ohne Masse, nur Eigenformen."""
    from statik3d import rechenverfahren as rv, solver
    mk = rv.merkmal("modal_massenrang")
    check("Merkmal modal_massenrang: Stand 68, Fehlerkorrektur, fix/k10-num",
          mk is not None and mk.wechsel[-1].stand == 68 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].commit == "fix/k10-num" and rv.VERFAHRENSSTAND >= 68,
          f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    if mk is None:
        return
    m_wand, Z = wand(8)
    m_lose = _rbe3_lose(1)
    m_voll, _b, _p = modell("mitte", teile=8, rho=7850.0)
    werte = [mk.betrifft(x) for x in (m_wand, m_lose, m_voll)]
    check("betrifft: gewichtslose Wand ja, loser RBE3-Slave ja, Stab mit Dichte und RBE2-Master nein",
          werte == [True, True, False], werte)
    res = _still(solver.solve_modal, m_wand, 8, workers=1, zusatzmasse=Z)
    t_modal = mk.im_ergebnis(m_wand, res)
    m_wand.add_load_case("LF1", "G")
    m_wand.load_node(8, Fz=-F, case="LF1")
    an = _still(solver.solve_all, m_wand, workers=1, design=False)
    t_statik = mk.im_ergebnis(m_wand, an)
    check("im Ergebnis: Eigenformen genannt, Statik nicht", t_modal.startswith("Eigenformen") and t_statik == "",
          f"{t_modal!r} / {t_statik!r}")


def main():
    tests = [test_starre_kopplung_rbe2, test_strafbeiwert, test_bitgleich, test_ruecknahme, test_merkmal,
             test_punktmasse_kragarm, test_punktmasse_feder, test_schutz_arpack,
             test_zusatzmasse_rang1, test_kleinmasse, test_wand_rang, test_grenze_dicht,
             test_rbe3_lose_schwingung, test_speicher_dicht, test_merkmal_modal]
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
