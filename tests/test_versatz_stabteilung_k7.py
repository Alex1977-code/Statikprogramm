"""
Behebungen vom 15.11.2026, Runde k7 (Agent „versatzknick“), vom Anwender
freigegeben („1 ja 2 ja“), Verfahrensstand 62.

1  Stäbe mit Versatz der Stabenden (Exzentrizität) werden intern geteilt wie
   alle Balken (statik3d.stabteilung.versatz_teile): die Zwischenknoten liegen
   auf der versetzten Stabachse, den Versatz behalten das erste und das letzte
   Teil, die Teile dazwischen haben keinen. Bis dahin blieben sie ungeteilt und
   rechneten mit ihrer kubischen Biegelinie – Zugband mit Arm 0,3 m und
   Sollkraft 70 kN: Knicken und α_cr „auto“ 801,6 statt 603,4; Theorie III.
   Ordnung am Kragarm mit Versatz quer 0,3 m am Ende: Spitzenverschiebung 7,61
   statt 8,23 mm.
2  solve_buckling fordert Formen nach, bis ein positiver Faktor dabei ist: ein
   Fachwerk mit gezogenem Untergurt lieferte mit drei Formen nur −64,38 /
   −64,38 / −130,78; der kleinste positive Faktor 7765,80 ist der 35. nach
   Betrag.

Sollwerte, zwei Wege:
* Kurzstabmodell: die versetzte Achse von Hand aus kurzen Stäben, die Arme als
  Balken STARR vom Knoten zum Stabende. Für Theorie II. Ordnung und Knicken
  nur mit Armen längs der Stabachse (Zugband, Kragarm mit axialem Versatz):
  ein starrer Balken quer zur Kraft hat in K_G nur seine Normalkraft, nicht
  den Armanteil [F]x [a]x des Versatzes – dort weicht er auch ungeteilt ab
  (Kragarm, Versatz quer: Knicken 3,164 gegen 3,260). Theorie III. Ordnung
  dreht die starren Arme exakt mit; dort gilt der Vergleich auch quer.
* Versatzstab von Hand geteilt: dieselben Zwischenknoten, der Versatz am
  ersten und letzten Element von Hand mit Winkelfunktionen in die Achsen
  seiner Knotenlinie umgerechnet – für Arme quer zur Stabachse (Theorie II.
  Ordnung, Knicken, Schnittgrößen im Feld).
* Fachwerk: dichte Lösung (LAPACK) des Verzweigungsproblems am geteilten
  Modell 7765,802747 (D/ag_k7_versatzknick/fachwerk_dicht.py), im Programm
  gegen α_cr „auto“ (theorie2.groesstes_mu, ein anderes Verfahren).

Aufruf:  python -m tests.test_versatz_stabteilung_k7
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


E = 210e9
LK = 4.0


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def _kragarm(art, ex0, ex1, P=200e3, Hy=1e3, Hz=2e3, teile=10, quadrat=False, starr=False,
             starr_faktor=1.0):
    """Kragarm 4 m längs global x, eingespannt bei x = 0, am Ende Fx = −P, Fy, Fz.
    "versatz": ein Element mit Versatz [ex0, ex1] (die Knotenlinie liegt längs x,
    lokal = global); "kurz": die versetzte Achse von Hand in ``teile`` Elementen,
    die Arme als Balken STARR vom Knoten zum Stabende."""
    from statik3d.model import Model, Material, Section
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    if quadrat:
        m.add_section(Section("Q", A=1e-2, Iy=4e-5, Iz=4e-5, It=1e-5, zmax=0.1, ymax=0.1))
    elif starr:
        m.add_section(Section("Q", A=10.0, Iy=1.0, Iz=1.0, It=1.0, zmax=0.1, ymax=0.1))
    else:
        m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    s = starr_faktor
    m.add_section(Section("STARR", A=10.0 * s, Iy=s, Iz=s, It=s, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    X0, X1 = np.zeros(3), np.array([LK, 0.0, 0.0])
    a = m.add_node(*X0)
    b = m.add_node(*X1)
    m.fix(a, "all")
    if art == "versatz":
        stab = [m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[list(ex0), list(ex1)])]
    else:
        P0, P1 = X0 + np.asarray(ex0, float), X1 + np.asarray(ex1, float)
        n0 = m.add_node(*P0) if np.any(ex0) else a
        n1 = m.add_node(*P1) if np.any(ex1) else b
        ids = [n0] + [m.add_node(*(P0 + (P1 - P0) * k / teile)) for k in range(1, teile)] + [n1]
        stab = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(teile)]
        if np.any(ex0):
            m.add_element("beam", [a, n0], "ST", "STARR")
        if np.any(ex1):
            m.add_element("beam", [n1, b], "ST", "STARR")
    m.add_member("S", stab)
    m.load_node(b, Fx=-P, Fy=Hy, Fz=Hz)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m, stab, b


def _kragarm_hand(ex0, ex1, P=200e3, Hy=1e3, Hz=2e3, teile=10):
    """Der Kragarm mit Versatz in der x-z-Ebene, von Hand in ``teile`` Elemente
    geteilt: Zwischenknoten auf der versetzten Achse, das erste Element mit dem
    Versatz am Anfang, das letzte mit dem am Ende, je in den Achsen seiner
    Knotenlinie mit Winkelfunktionen (Drehwinkel 0: lokal y bleibt global y)."""
    from statik3d.model import Model, Material, Section
    assert ex0[1] == 0 and ex1[1] == 0
    m = Model("H")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    X0, X1 = np.zeros(3), np.array([LK, 0.0, 0.0])
    a0, a1 = np.asarray(ex0, float), np.asarray(ex1, float)
    P0, P1 = X0 + a0, X1 + a1
    a = m.add_node(*X0)
    b = m.add_node(*X1)
    m.fix(a, "all")
    pkt = [X0] + [P0 + (P1 - P0) * k / teile for k in range(1, teile)] + [X1]
    ids = [a] + [m.add_node(*p) for p in pkt[1:-1]] + [b]

    def lokal(A, B, arm):
        # e_x = (dx, 0, dz)/l, e_y = (0, 1, 0), e_z = e_x × e_y = (−dz, 0, dx)/l
        dx, dz = B[0] - A[0], B[2] - A[2]
        l = math.hypot(dx, dz)
        return [(arm[0] * dx + arm[2] * dz) / l, 0.0, (-arm[0] * dz + arm[2] * dx) / l]

    stab = []
    for k in range(teile):
        ex = [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
        if k == 0 and np.any(a0):
            ex[0] = lokal(pkt[0], pkt[1], a0)
        if k == teile - 1 and np.any(a1):
            ex[1] = lokal(pkt[k], pkt[k + 1], a1)
        kw = {"exzentrizitaet": ex} if np.any(ex) else {}
        stab.append(m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q", **kw))
    m.add_member("S", stab)
    m.load_node(b, Fx=-P, Fy=Hy, Fz=Hz)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m, stab, b


def _zugband_versatz(soll, arm):
    from tests.test_versatz_achsen_lotrecht import _zugband
    m, band = _zugband("versatz", soll, arm=arm)
    m.add_combination("K1", {"V": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m, band


def _zugband_kurz(soll, arm):
    from tests.test_knicken_stabteilung_k7 import _zugband
    return _zugband(1, soll=soll, arm=arm)


def _knick(m, nmodes=6, **kw):
    from statik3d import solver
    kw = kw or {"combination": "K1"}
    with contextlib.redirect_stdout(io.StringIO()):
        r = solver.solve_buckling(m, nmodes, **kw)
    f = np.asarray(r.buckling_factors, float)
    pos = f[np.isfinite(f) & (f > 0)]
    return (float(pos.min()) if len(pos) else math.nan), r


def _auto(m):
    from statik3d import theorie2
    with contextlib.redirect_stdout(io.StringIO()):
        return theorie2.check_theorie2(m, None, ["K1"]).kombinationen["K1"].alpha_cr


def _th2(m):
    from statik3d import theorie2
    with contextlib.redirect_stdout(io.StringIO()):
        r, _i = theorie2.solve_theorie2(m, {"LF1": 1.0}, "LF1", imperfektionen=False)
    return r


def _th3(m):
    from statik3d import theorie3
    with contextlib.redirect_stdout(io.StringIO()):
        return theorie3.solve_theorie3(m, {"LF1": 1.0}, "LF1", imperfektionen=False)


def _rel(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.abs(a - b).max() / max(float(np.abs(b).max()), 1e-30))


QUER = (("verschieden quer", [0, 0, 0.1], [0, 0, 0.3]),
        ("gleich quer", [0, 0, 0.2], [0, 0, 0.2]),
        ("nur am Ende quer", [0, 0, 0.0], [0, 0, 0.3]))


# --------------------------------------------------------------------------
# 1  Stabteilung mit Versatz
# --------------------------------------------------------------------------
def test_zugband():
    """Arm längs des Bandes: Kurzstab (Band intern in 10 Teilen, Arm STARR) und
    Versatz geben dasselbe; Knicken = α_cr „auto“. Bekannte Werte des Agenten
    „knick“ (Runde k7): mit Sollkraft 603,44 / 437,44, ohne 3 289,58."""
    for soll in (True, False):
        for arm in (0.3, -0.3):
            lv, rv = _knick(_zugband_versatz(soll, arm)[0], 150)
            lk, _r = _knick(_zugband_kurz(soll, arm), 150)
            av = _auto(_zugband_versatz(soll, arm)[0])
            band = _zugband_versatz(soll, arm)[1]
            check(f"Zugband {'mit' if soll else 'ohne'} Sollkraft, Arm {arm:+.1f}: Knicken Versatz = Kurzstab "
                  "(1e-3) = α_cr „auto“ (1e-6), Band in 10 Teilen",
                  abs(lv / lk - 1) < 1e-3 and abs(av / lv - 1) < 1e-6
                  and (rv.info.get("stabteilung") or {}).get(band) == 10,
                  f"Versatz {lv:.4f}, Kurzstab {lk:.4f}, auto {av:.4f}, Teilung {rv.info.get('stabteilung')}")


def test_axial_kurzstab():
    """Kragarm mit Versatz längs der Stabachse (0,3 m am Anfang, −0,2 m am Ende),
    Druck 200 kN mit Querlasten: Theorie II. Ordnung, Knicken und α_cr gegen das
    Kurzstabmodell von Hand in 10 Elementen."""
    e0, e1 = [0.3, 0, 0], [-0.2, 0, 0]
    lv, rv = _knick(_kragarm("versatz", e0, e1)[0])
    lk, _r = _knick(_kragarm("kurz", e0, e1)[0])
    av = _auto(_kragarm("versatz", e0, e1)[0])
    check("Kragarm, Versatz längs: Knicken Versatz = Kurzstab (1e-5) = α_cr „auto“ (1e-6), 10 Teile",
          abs(lv / lk - 1) < 1e-5 and abs(av / lv - 1) < 1e-6 and rv.info.get("stabteilung") == {0: 10},
          f"Versatz {lv:.6f}, Kurzstab {lk:.6f}, auto {av:.6f}, Teilung {rv.info.get('stabteilung')}")
    mv, sv, bv = _kragarm("versatz", e0, e1)
    mk, sk, bk = _kragarm("kurz", e0, e1)
    rv, rk = _th2(mv), _th2(mk)
    uv, uk = np.asarray(rv.u)[bv][:3], np.asarray(rk.u)[bk][:3]
    fv, fk = np.asarray(rv.beam_end[sv[0]])[[0, 1, 2, 4, 5]], np.asarray(rk.beam_end[sk[0]])[[0, 1, 2, 4, 5]]
    check("Kragarm, Versatz längs, Theorie II. Ordnung: Spitze und Stabanfang wie Kurzstab (1e-4)",
          _rel(uv, uk) < 1e-4 and _rel(fv, fk) < 1e-4 and len(rv.u) == 2,
          f"u {np.round(uv * 1e3, 5)} / {np.round(uk * 1e3, 5)} mm; N,Vy,Vz,My,Mz {np.round(fv / 1e3, 4)} / "
          f"{np.round(fk / 1e3, 4)}")


def test_quer_von_hand():
    """Versatz quer zur Stabachse: Knicken, α_cr und Theorie II. Ordnung gleich
    dem von Hand geteilten Versatzstab (1e-9)."""
    for text, e0, e1 in QUER:
        lv, rv = _knick(_kragarm("versatz", e0, e1)[0])
        lh, _r = _knick(_kragarm_hand(e0, e1)[0])
        av = _auto(_kragarm("versatz", e0, e1)[0])
        check(f"Kragarm, Versatz {text}: Knicken = von Hand geteilt (1e-9) = α_cr „auto“ (1e-6)",
              abs(lv / lh - 1) < 1e-9 and abs(av / lv - 1) < 1e-6,
              f"Versatz {lv:.6f}, von Hand {lh:.6f}, auto {av:.6f}, Teilung {rv.info.get('stabteilung')}")
        mv, sv, bv = _kragarm("versatz", e0, e1)
        mh, sh, bh = _kragarm_hand(e0, e1)
        rv, rh = _th2(mv), _th2(mh)
        uv, uh = np.asarray(rv.u)[bv], np.asarray(rh.u)[bh]
        fv = np.asarray(rv.beam_end[sv[0]], float)
        fh = np.concatenate([np.asarray(rh.beam_end[sh[0]], float)[:6], np.asarray(rh.beam_end[sh[-1]], float)[6:]])
        check(f"Kragarm, Versatz {text}, Theorie II. Ordnung: Spitze und Stabendkräfte = von Hand (1e-9)",
              _rel(uv, uh) < 1e-9 and _rel(fv, fh) < 1e-9,
              f"u_y {uv[1] * 1e3:.6f} / {uh[1] * 1e3:.6f} mm, Mz Anfang {fv[5] / 1e3:.5f} / {fh[5] / 1e3:.5f} kNm")
        # Schnittgroessen im Feld: Stelle x_k = k L/10 auf der Stabachse = Anfang
        # des k-ten Elements von Hand (mit dem Feldanteil N w der Teile)
        from statik3d import solver
        sf = solver.beam_station_forces(mv, rv, sv[0], n=11)
        ref = {c: [] for c in ("N", "Vy", "Vz", "My", "Mz")}
        for k in range(10):
            s = solver.beam_station_forces(mh, rh, sh[k], n=3)
            for c in ref:
                ref[c].append(s[c][0])
        s = solver.beam_station_forces(mh, rh, sh[-1], n=3)
        for c in ref:
            ref[c].append(s[c][-1])
        Lh = sum(mh.element_length(i) for i in sh)
        mitte = solver.beam_station_forces(mh, rh, sh[4], n=3)
        sf_m = solver.beam_station_forces(mv, rv, sv[0], n=21)
        abw = max(_rel(sf[c], ref[c]) for c in ref)
        abw_m = max(abs(sf_m[c][9] - mitte[c][1]) / max(np.abs(ref[c]).max(), 1e-30) for c in ("My", "Mz"))
        check(f"Kragarm, Versatz {text}: Schnittgrößen im Feld an 11 Stellen und in Teilmitte = von Hand "
              "(1e-8), Stablänge auf der Achse",
              abw < 1e-8 and abw_m < 1e-8 and abs(sf["L"] / Lh - 1) < 1e-12,
              f"Abweichung {abw:.1e} / {abw_m:.1e}, L {sf['L']:.6f} / {Lh:.6f} m, "
              f"Mz {np.round(np.asarray(sf['Mz']) / 1e3, 3)}")


def test_theorie3_kurzstab():
    """Theorie III. Ordnung dreht die Arme exakt mit: Versatz gegen das
    Kurzstabmodell von Hand in 20 Elementen (Theorie III teilt doppelt so fein)."""
    for text, e0, e1 in (QUER[0], QUER[2]):
        mv, sv, bv = _kragarm("versatz", e0, e1)
        mk, sk, bk = _kragarm("kurz", e0, e1, teile=20)
        rv, iv = _th3(mv)
        rk, ik = _th3(mk)
        uv, uk = np.asarray(rv.u)[bv][:3], np.asarray(rk.u)[bk][:3]
        fv, fk = np.asarray(rv.beam_end[sv[0]])[:6], np.asarray(rk.beam_end[sk[0]])[:6]
        check(f"Theorie III, Kragarm, Versatz {text}: Spitze und Stabanfang wie Kurzstab (1e-4), 20 Teile",
              not iv.fehler and not ik.fehler and _rel(uv, uk) < 1e-4 and _rel(fv, fk) < 1e-4
              and rv.info.get("stabteilung") == {0: 20},
              f"u {np.round(uv * 1e3, 5)} / {np.round(uk * 1e3, 5)} mm; Mz {fv[5] / 1e3:.5f} / {fk[5] / 1e3:.5f}; "
              f"{iv.fehler!r} {ik.fehler!r}")
        if text == QUER[0][0]:
            from statik3d import solver
            sf = solver.beam_station_forces(mv, rv, sv[0], n=21)
            ref = {c: [solver.beam_station_forces(mk, rk, j, n=3)[c][0] for j in sk]
                   + [solver.beam_station_forces(mk, rk, sk[-1], n=3)[c][-1]] for c in ("N", "My", "Mz")}
            abw = max(_rel(sf[c], ref[c]) for c in ref)
            check("Theorie III, Versatz verschieden quer: N, My, Mz an 21 Stellen wie Kurzstab (1e-4)",
                  abw < 1e-4, f"Abweichung {abw:.1e}")
    # raeumlicher Versatz, quadratischer Querschnitt: Arme STARR mit 1/100 der
    # Steifigkeit (mit voller konvergiert das Kurzstabmodell nicht); Vergleich der
    # Betraege (die Achsen des Kurzstabs drehen um 0,08 Grad gegen die des Stabs)
    e0, e1 = [0, 0.1, 0.05], [0, -0.05, 0.2]
    mv, sv, bv = _kragarm("versatz", e0, e1, quadrat=True)
    mk, sk, bk = _kragarm("kurz", e0, e1, quadrat=True, teile=20, starr_faktor=0.01)
    rv, iv = _th3(mv)
    rk, ik = _th3(mk)
    uv, uk = np.asarray(rv.u)[bv][:3], np.asarray(rk.u)[bk][:3]
    fv, fk = np.asarray(rv.beam_end[sv[0]]), np.asarray(rk.beam_end[sk[0]])
    inv = lambda f: np.array([f[0], math.hypot(f[1], f[2]), f[3], math.hypot(f[4], f[5])])  # noqa: E731
    check("Theorie III, Kragarm, Versatz räumlich: Spitze (2e-3) und N, |V|, Mt, |M| am Anfang (3e-3) wie "
          "Kurzstab",
          not iv.fehler and not ik.fehler and _rel(uv, uk) < 2e-3 and _rel(inv(fv), inv(fk)) < 3e-3
          and rv.info.get("stabteilung") == {0: 20},
          f"u {np.round(uv * 1e3, 4)} / {np.round(uk * 1e3, 4)} mm; {np.round(inv(fv) / 1e3, 4)} / "
          f"{np.round(inv(fk) / 1e3, 4)}")


def test_abbildung():
    """Ergebnis auf dem Modell: nur seine Knoten, Stabendkräfte aus erstem und
    letztem Teil; die Zwischenknoten liegen auf der versetzten Achse."""
    from statik3d import stabteilung
    e0, e1 = [0, 0, 0.1], [0, 0, 0.3]
    m, s, b = _kragarm("versatz", e0, e1)
    vt = stabteilung.versatz_teile(m, 0, 10)
    P0, P1 = np.array([0, 0, 0.1]), np.array([LK, 0, 0.3])
    auf_achse = vt is not None and all(np.linalg.norm(vt[k][0] - (P0 + (P1 - P0) * k / 10)) < 1e-12
                                       for k in range(1, 10))
    nur_enden = vt is not None and bool(vt[0][3]) and bool(vt[-1][3]) and not any(t[3] for t in vt[1:-1])
    check("versatz_teile: Zwischenknoten auf der versetzten Achse, Versatz nur am ersten und letzten Teil",
          auf_achse and nur_enden, str(None if vt is None else [len(t[3]) for t in vt]))
    r = _th2(m)
    check("Theorie II, Versatz: Ergebnis an den 2 Modellknoten, Teilung {0: 10} im Ergebnis",
          len(r.u) == 2 and r.info.get("stabteilung") == {0: 10} and 0 in r.beam_teile,
          f"{len(r.u)} Knoten, {r.info.get('stabteilung')}")


def test_relevanz_und_starr():
    """Schutz: ein Stab mit Versatz unter kleiner Normalkraft (unter RELEVANZ)
    bleibt ungeteilt; ein starrer Kurzstab mit Versatz unter Druck ebenso, und
    die Rechnung bleibt endlich."""
    m, s, b = _kragarm("versatz", [0, 0, 0.1], [0, 0, 0.3], P=1e3)
    r = _th2(m)
    check("Versatz, Druck 1 kN (unter 1e-3 N_E): ungeteilt nach Theorie II. Ordnung",
          "stabteilung" not in r.info, str(r.info.get("stabteilung")))
    m, s, b = _kragarm("versatz", [0, 0, 0.1], [0, 0, 0.3], starr=True)
    r = _th2(m)
    lam, rb = _knick(_kragarm("versatz", [0, 0, 0.1], [0, 0, 0.3], starr=True)[0])
    u = np.asarray(r.u, float)
    check("Starrer Kurzstab mit Versatz unter 200 kN: ungeteilt, Theorie II und Knicken endlich",
          "stabteilung" not in r.info and "stabteilung" not in rb.info and np.all(np.isfinite(u))
          and np.abs(u).max() < 1e-3 and math.isfinite(lam),
          f"{r.info.get('stabteilung')} {rb.info.get('stabteilung')} max|u| {np.abs(u).max():.2e} λ {lam:.4g}")


# --------------------------------------------------------------------------
# 2  Knicken: mindestens ein positiver Faktor
# --------------------------------------------------------------------------
def _fachwerk():
    """Dreieck: Untergurt Balken 2 m, zwei Fachwerkstäbe zum First (1; 0; 1,5),
    Last 50 kN am First (D/ag_k7_knick/bitgleich.py)."""
    from statik3d.model import Model, Material, Section
    m = Model("F")
    m.add_material(Material("S235"))
    m.add_section(Section.rectangle("R", 0.05, 0.05))
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(2, 0, 0)
    n2 = m.add_node(1, 0, 1.5)
    m.add_element("beam", [n0, n1], "S235", "R")
    m.add_element("truss", [n0, n2], "S235", "R")
    m.add_element("truss", [n1, n2], "S235", "R")
    m.fix(n0, "all")
    m.fix(n1, [1, 2, 3, 4, 5])
    m.fix(n2, [1, 3, 4, 5])
    m.load_node(n2, Fz=-50e3)
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.design.theorie2 = "auto"
    return m


#: Dichte Loesung am geteilten Modell (D/ag_k7_versatzknick/fachwerk_dicht.py)
FACHWERK_DICHT = 7765.802747153208
FACHWERK_NEG = (-64.37728916, -64.37728916, -130.7821838)


def test_positiv_nachfordern():
    lam, r = _knick(_fachwerk(), 3, case="LF1")
    f = np.asarray(r.buckling_factors, float)
    a = _auto(_fachwerk())
    check("Fachwerk, 3 Formen angefordert: ein positiver Faktor dabei = dichte Lösung (1e-8) = α_cr „auto“ "
          "(1e-6)",
          math.isfinite(lam) and abs(lam / FACHWERK_DICHT - 1) < 1e-8 and abs(a / lam - 1) < 1e-6,
          f"{lam:.6f}, auto {a:.6f}, {len(f)} Faktoren")
    check("Fachwerk: die ersten drei Faktoren wie bisher (1e-8), aufsteigend nach Betrag, bis zum ersten "
          "positiven",
          len(f) >= 3 and _rel(f[:3], FACHWERK_NEG) < 1e-8 and np.all(np.diff(np.abs(f)) >= -1e-9 * np.abs(f[1:]))
          and f[-1] > 0 and np.all(f[:-1] < 0),
          f"{np.round(f[:4], 5)} … {np.round(f[-2:], 3)}")
    h = r.info.get("knickfaktor_hinweis", "")
    check("Fachwerk: Hinweis im Ergebnis und in der Zusammenfassung, Klartext ohne wissenschaftliche Schreibweise",
          "kein positiver" in h and "7765,80" in h and "Form 35" in h and h in r.summary()
          and "e+" not in h and "e-" not in h.replace("Formen", ""),
          h)
    check("Fachwerk: Eigenformen zu jedem Faktor",
          np.asarray(r.buckling_modes).shape[0] == len(f), str(np.asarray(r.buckling_modes).shape))


def test_kein_positiver():
    """Reiner Zug: es gibt keinen positiven Faktor - Klartext, nichts erfunden."""
    from statik3d.model import Model, Material, Section
    m = Model("Z")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    ids = [m.add_node(0, 0, -k * 1.0) for k in range(5)]
    for k in range(4):
        m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q")
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-100e3)
    lam, r = _knick(m, 3, case="LF1")
    f = np.asarray(r.buckling_factors, float)
    h = r.info.get("knickfaktor_hinweis", "")
    check("Hängender Stab unter Zug: kein positiver Faktor, Hinweis „Kein positiver Knickfaktor“, Faktoren "
          "wie angefordert",
          math.isnan(lam) and len(f) == 3 and np.all(f < 0) and h.startswith("Kein positiver Knickfaktor")
          and h in r.summary(), h)


def test_positiv_schon_da():
    """Schutz: liefern die angeforderten Formen schon einen positiven Faktor,
    bleibt alles wie bisher (Zahl der Faktoren = nmodes, kein Hinweis)."""
    from tests.test_knicken_stabteilung_k7 import _stuetze
    lam, r = _knick(_stuetze([0, 1, 2, 5], [0, 1]), 3, case="LF1")
    check("Gelenkstütze, 3 Formen: 3 Faktoren, kein Hinweis",
          len(r.buckling_factors) == 3 and "knickfaktor_hinweis" not in r.info and lam > 0,
          f"{np.round(r.buckling_factors, 4)}")


# --------------------------------------------------------------------------
def test_merkmale():
    from statik3d import rechenverfahren as rv
    from statik3d import solver
    for name in ("versatz_stabteilung", "knicken_positiver_faktor"):
        mk = rv.merkmal(name)
        check(f"Merkmal {name}: Stand 62, Fehlerkorrektur, VERFAHRENSSTAND >= 62",
              mk is not None and mk.wechsel[-1].stand == 62 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
              and rv.VERFAHRENSSTAND >= 62, f"{mk and mk.wechsel} {rv.VERFAHRENSSTAND}")
    mk = rv.merkmal("versatz_stabteilung")
    if mk is not None:
        check("versatz_stabteilung betrifft: Zugband mit Versatz ja, Kurzstab ohne Versatz nein, Versatz mit "
              "Stabteilung 1 nein",
              mk.betrifft(_zugband_versatz(True, 0.3)[0]) and not mk.betrifft(_zugband_kurz(True, 0.3))
              and not mk.betrifft(_stabteilung_1(_zugband_versatz(True, 0.3)[0])))
        m = _kragarm("versatz", [0, 0, 0.1], [0, 0, 0.3])[0]
        rb = solver.Results(name="K1", kind="buckling", model=m)
        rs = solver.Results(name="LF1", kind="case", model=m)
        check("versatz_stabteilung im Ergebnis: Knicken ja, Theorie I. Ordnung nein",
              bool(mk.im_ergebnis(m, rb)) and not mk.im_ergebnis(m, rs),
              f"{mk.im_ergebnis(m, rb)!r} / {mk.im_ergebnis(m, rs)!r}")
    mk = rv.merkmal("knicken_positiver_faktor")
    if mk is not None:
        m = _fachwerk()
        alt = solver.Results(name="LF1", kind="buckling", model=m)
        alt.buckling_factors = np.array(FACHWERK_NEG)
        neu = solver.Results(name="LF1", kind="buckling", model=m)
        neu.buckling_factors = np.array(list(FACHWERK_NEG) + [FACHWERK_DICHT])
        check("knicken_positiver_faktor im Ergebnis: nur negative Faktoren ja, mit positivem nein",
              bool(mk.im_ergebnis(m, alt)) and not mk.im_ergebnis(m, neu),
              f"{mk.im_ergebnis(m, alt)!r} / {mk.im_ergebnis(m, neu)!r}")


def _stabteilung_1(m):
    m.netz.stabteilung = 1
    return m


def main():
    for t in (test_zugband, test_axial_kurzstab, test_quer_von_hand, test_theorie3_kurzstab, test_abbildung,
              test_relevanz_und_starr, test_positiv_nachfordern, test_kein_positiver, test_positiv_schon_da,
              test_merkmale):
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
