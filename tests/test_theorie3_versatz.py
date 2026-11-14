"""
Theorie III. Ordnung mit Versatz der Stabenden (Exzentrizitaet), 12.11.2026.

Nachstellung am Stand eb88ecc: Kragarm L = 4 m in 4 Elementen, jedes mit
Versatz (0, 0, 0,1 m) an beiden Enden (der Stab liegt 0,1 m ueber der
Knotenlinie), Zug F = 50 kN in der Knotenlinie am freien Ende. Der Stab
bekommt das Moment F e = 5 kNm, die Spitze hebt sich um
w = F e L² / (2 E I) = 1,905 mm (Theorie I. Ordnung, auch von Hand); Theorie
III. Ordnung gab 0,000 mm und am Stabende 0 statt 5 kNm - der Versatz fiel in
_Stab still weg.

Seither haengt der Stab in Theorie III. Ordnung an seinen Stabenden
P_i = x_i + R_i a_i: der Versatz a_i ist ein starrer Arm, der mit der
Knotendrehung R_i mitdreht, das mitgehende System folgt der Sehne der
Stabenden.

Zwei Wege je Zahl:
1. kleine Last: Theorie III. Ordnung mit Versatz gegen Theorie I. bzw. II.
   Ordnung mit Versatz (und die Handformel);
2. grosse Verdrehung: dasselbe System, der Stab an eigenen Knoten und ueber
   sehr steife Kurzstaebe an die Knotenlinie gehaengt, nach Theorie III.
   Ordnung.

Aufruf:  python -m tests.test_theorie3_versatz
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
E = 210e9
NU = 0.3
G = E / (2 * (1 + NU))
I = 1e-4
IT = 1e-5
EI = E * I
L = 4.0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


def _modell():
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=IT, zmax=0.1, ymax=0.05))
    # Kurzstaebe: E I 1000-fach des Stabes, starr genug (zehnfach weicher
    # aendert die Spitze um 0,14 %), aber nicht so steif, dass die Tangente
    # numerisch versagt (A = 1e3 m², I = 1e2 m⁴: keine Konvergenz)
    m.add_section(Section("STARR", A=1.0, Iy=0.1, Iz=0.1, It=0.1, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    return m


def _kragarm(art, r1, r2, n, lasten, theorie="III", it=IT):
    """Kragarm entlang x, eingespannt in Knoten 0. art "versatz": Versatz
    am Element; "kurzstab": der Stab an eigenen Knoten (x + r), starr ueber
    Kurzstaebe angeschlossen. Der Versatz waechst von r1 (Knoten 0) linear bis
    r2 (Spitze) - je Element der Wert an seinen Enden. lasten: {Fx, Fz, ...}
    an der Spitze. Rueckgabe (Modell, Knoten der Knotenlinie)."""
    m = _modell()
    m.sections["Q"].It = it
    r1, r2 = np.asarray(r1, float), np.asarray(r2, float)

    def r(k):
        return r1 + (r2 - r1) * k / n
    ids = [m.add_node(L * k / n, 0, 0) for k in range(n + 1)]
    if art == "versatz":
        for k in range(n):
            m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q",
                          exzentrizitaet=[r(k).tolist(), r(k + 1).tolist()])
    else:
        st = [m.add_node(L * k / n + r(k)[0], r(k)[1], r(k)[2]) if np.any(r(k)) else ids[k]
              for k in range(n + 1)]
        for k in range(n):
            m.add_element("beam", [st[k], st[k + 1]], "ST", "Q")
        for a, b in zip(ids, st):
            if a != b:
                m.add_element("beam", [a, b], "ST", "STARR")
    m.fix(ids[0], "all")
    m.load_node(ids[-1], **lasten)
    m.load_cases["LF1"].theorie = theorie
    return m, ids


def _th3(m, schritte=10, stabteilung=False):
    from statik3d.theorie3 import solve_theorie3
    return solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=schritte, imperfektionen=False,
                          stabteilung=stabteilung)


def _linear(m):
    from statik3d import solver
    return solver.solve_all(m, workers=1, design=False).cases["LF1"]


def _gleichgewicht(m, res, ids, lasten):
    """Kraft- und Momentensumme (um den Ursprung, in der verformten Lage)
    aus Last und Auflagerkraeften, bezogen auf |F| bzw. |F| L."""
    F = np.zeros((m.nn, 6))
    F[ids[-1]] = [lasten.get(k, 0.0) for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")]
    ges = F + res.reactions
    x = np.asarray(m.nodes) + res.u[:, :3]
    kraft = ges[:, :3].sum(axis=0)
    moment = sum(np.cross(x[k], ges[k, :3]) + ges[k, 3:] for k in range(m.nn))
    fb = float(np.linalg.norm(F[ids[-1], :3])) or 1.0
    return float(np.linalg.norm(kraft)) / fb, float(np.linalg.norm(moment)) / (fb * L)


# ---------------------------------------------------------------- Weg 1: kleine Last
def test_nachstellung_klein():
    e, F = 0.1, 5e3
    soll = F * e * L ** 2 / (2 * EI)
    last = {"Fx": F}
    m1, i1 = _kragarm("versatz", (0, 0, e), (0, 0, e), 4, last, "I")
    m2, i2 = _kragarm("versatz", (0, 0, e), (0, 0, e), 4, last, "II")
    m3, i3 = _kragarm("versatz", (0, 0, e), (0, 0, e), 4, last, "III")
    r1, r2 = _linear(m1), _linear(m2)
    r3, info = _th3(m3)
    w1, w2, w3 = (float(r.u[i[-1], 2]) for r, i in ((r1, i1), (r2, i2), (r3, i3)))
    check(f"Th I mit Versatz 0,1 m, Zug 5 kN: w = F e L²/(2 E I) = {soll * 1e3:.4f} mm (Hand, auf 0,01 %)",
          abs(w1 / soll - 1) < 1e-4, f"{w1 * 1e3:.5f} mm")
    check("Th III mit Versatz: Rechnung ohne Fehler", not info.fehler, repr(info.fehler))
    check("Th III mit Versatz = Th I auf 0,5 % (vorher 0,000 mm)", abs(w3 / w1 - 1) < 5e-3,
          f"Th III {w3 * 1e3:.5f}, Th I {w1 * 1e3:.5f} mm")
    check("… = Th II auf 0,05 %", abs(w3 / w2 - 1) < 5e-4, f"Th III {w3 * 1e3:.5f}, Th II {w2 * 1e3:.5f} mm")
    my1 = float(r1.beam_end[len(m1.elements) - 1][10])
    my3 = float(r3.beam_end[len(m3.elements) - 1][10])
    check(f"… Moment aus dem Versatz in den Stabendkräften: My(Spitze) = −F e = {-F * e / 1e3:.3f} kNm "
          "wie Th I (auf 0,5 %; vorher 0)", abs(my3 / (-F * e) - 1) < 5e-3 and abs(my1 / (-F * e) - 1) < 1e-6,
          f"Th III {my3 / 1e3:.5f}, Th I {my1 / 1e3:.5f} kNm")
    my0 = float(r3.beam_end[0][4])
    check("… und am Stabanfang (Element 0) My = +F e (auf 0,5 %)", abs(my0 / (F * e) - 1) < 5e-3,
          f"{my0 / 1e3:.5f} kNm")
    # die Last geht durch die Einspannung: das Lagermoment kommt nur aus der
    # gehobenen Spitze, My = −F w (Theorie I. Ordnung: 0)
    check("… Lagermoment = −F w (Moment der mitgehobenen Last, auf 1 %)",
          abs(r3.reactions[i3[0], 4] / (-F * w3) - 1) < 1e-2,
          f"{r3.reactions[i3[0], 4]:.4f} Nm, −F w = {-F * w3:.4f} Nm")
    kr, mo = _gleichgewicht(m3, r3, i3, last)
    check("… ΣR = ΣF: Kraft- und Momentensumme in der verformten Lage null (auf 1e-6)",
          kr < 1e-6 and mo < 1e-6, f"Kraft {kr:.2e}, Moment {mo:.2e}")


def test_torsion_klein():
    """Versatz quer (lokal y), Last in z: der Versatz macht Torsion F e."""
    e, F = 0.2, -2e3
    last = {"Fz": F}
    m1, i1 = _kragarm("versatz", (0, e, 0), (0, e, 0), 4, last, "I")
    m3, i3 = _kragarm("versatz", (0, e, 0), (0, e, 0), 4, last, "III")
    r1 = _linear(m1)
    r3, info = _th3(m3)
    soll = -F * e * L / (G * IT)          # Mx = −e F: Last in der Knotenlinie, Stab bei +e
    p1, p3 = float(r1.u[i1[-1], 3]), float(r3.u[i3[-1], 3])
    check(f"Th I mit Versatz quer 0,2 m, Fz = −2 kN: Verdrillung −F e L/(G I_T) = {soll * 1e3:.4f} mrad (Hand, 0,01 %)",
          abs(p1 / soll - 1) < 1e-4, f"{p1 * 1e3:.5f} mrad")
    check("Th III = Th I auf 0,5 % (vorher 0)", not info.fehler and abs(p3 / p1 - 1) < 5e-3,
          f"Th III {p3 * 1e3:.5f}, Th I {p1 * 1e3:.5f} mrad")
    mx3 = float(r3.beam_end[len(m3.elements) - 1][9])
    check("… Torsionsmoment am Stabende = F e (auf 0,5 %)", abs(abs(mx3) / abs(F * e) - 1) < 5e-3,
          f"{mx3:.3f} Nm, F e = {F * e:.3f} Nm")


def test_gelenk_klein():
    """Zwei Elemente mit Versatz (0; 0; 0,1) m, links eingespannt, rechts
    gelenkig gehalten, Stabendgelenk (phi_y) am Stabende hinter dem Versatz,
    Zug 5 kN in der Knotenlinie und 1 kN quer in der Mitte."""
    def modell(th):
        m = _modell()
        ids = [m.add_node(2.0 * k, 0, 0) for k in range(3)]
        els = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q",
                             exzentrizitaet=[[0, 0, 0.1], [0, 0, 0.1]]) for k in range(2)]
        m.add_hinge("GE", end=1, phiy="free")
        m.apply_hinge(els[1], "GE")
        m.fix(ids[0], "all")
        m.fix(ids[2], [1, 2, 3, 4])
        m.load_node(ids[2], Fx=5e3)
        m.load_node(ids[1], Fz=-1e3)
        m.load_cases["LF1"].theorie = th
        return m, ids, els
    m1, i1, e1 = modell("I")
    m3, i3, e3 = modell("III")
    r1 = _linear(m1)
    r3, info = _th3(m3)
    w1, w3 = float(r1.u[i1[1], 2]), float(r3.u[i3[1], 2])
    M1, M3 = float(r1.reactions[i1[0], 4]), float(r3.reactions[i3[0], 4])
    check("Gelenk am Stabende hinter dem Versatz: Th III = Th I, Durchbiegung Mitte und Einspannmoment (auf 0,5 %)",
          not info.fehler and abs(w3 / w1 - 1) < 5e-3 and abs(M3 / M1 - 1) < 5e-3,
          f"w {w3 * 1e3:.5f} / {w1 * 1e3:.5f} mm, My {M3:.2f} / {M1:.2f} Nm")
    mg = abs(float(r3.beam_end[e3[1]][10]))
    check("… Moment am Gelenk 0", mg < 1e-6 * abs(M1), f"{mg:.2e} Nm")


# ---------------------------------------------------------------- Weg 2: grosse Verdrehung
def _vergleich(text, r1, r2, last, it=IT, schritte=20):
    mv, iv = _kragarm("versatz", r1, r2, 8, last, it=it)
    mk, ik = _kragarm("kurzstab", r1, r2, 8, last, it=it)
    rv, infv = _th3(mv, schritte)
    rk, infk = _th3(mk, schritte)
    check(f"{text}: beide Rechnungen ohne Fehler", not infv.fehler and not infk.fehler,
          f"{infv.fehler!r} / {infk.fehler!r}")
    if infv.fehler or infk.fehler:
        return
    uv, uk = rv.u[iv[-1]], rk.u[ik[-1]]
    du = float(np.linalg.norm(uv[:3] - uk[:3])) / float(np.linalg.norm(uk[:3]))
    dth = float(np.linalg.norm(uv[3:] - uk[3:])) / float(np.linalg.norm(uk[3:]))
    grad = math.degrees(float(np.linalg.norm(uk[3:])))
    check("… große Verdrehung an der Spitze (über 20°)", grad > 20.0, f"{grad:.1f}°")
    check("… Verschiebung der Spitze wie mit starren Kurzstäben (auf 0,1 %)", du < 1e-3,
          f"Versatz {np.round(uv[:3] * 1e3, 3)} mm, Kurzstäbe {np.round(uk[:3] * 1e3, 3)} mm")
    check("… Verdrehung der Spitze wie mit starren Kurzstäben (auf 0,1 %)", dth < 1e-3,
          f"Versatz {np.round(np.degrees(uv[3:]), 3)}°, Kurzstäbe {np.round(np.degrees(uk[3:]), 3)}°")
    Rv, Rk = rv.reactions[iv[0]], rk.reactions[ik[0]]
    dr = float(np.linalg.norm(Rv[3:] - Rk[3:])) / max(float(np.linalg.norm(Rk[3:])), 1e-9)
    check("… Einspannmoment wie mit starren Kurzstäben (auf 0,1 %)", dr < 1e-3,
          f"Versatz {np.round(Rv[3:] / 1e3, 3)}, Kurzstäbe {np.round(Rk[3:] / 1e3, 3)} kNm")
    kr, mo = _gleichgewicht(mv, rv, iv, last)
    _kk, mo_k = _gleichgewicht(mk, rk, ik, last)
    check("… ΣR = ΣF: Kraftsumme in der verformten Lage null (auf 1e-5 |F|)", kr < 1e-5, f"{kr:.2e}")
    # Die Momentensumme bleibt um einige 1e-4 F L offen, mit und ohne Versatz
    # (das Th-III-Element wendet k_l mit L0 bei gedehnter Sehne an; Kragarm
    # ohne Versatz bei 35° Drehung: 4,1e-4) - der Versatz fuegt nichts hinzu
    check("… Momentensumme in der verformten Lage wie mit starren Kurzstäben (auf 1e-5 |F| L)",
          abs(mo - mo_k) < 1e-5, f"Versatz {mo:.3e}, Kurzstäbe {mo_k:.3e}")


def test_gross_eben():
    _vergleich("Th III, Versatz (0; 0; 0,2) m, Fz = −2 MN und Fx = 0,3 MN", (0, 0, 0.2), (0, 0, 0.2),
               {"Fz": -2e6, "Fx": 3e5})


def test_gross_raeumlich():
    # I_T = 1,5 I: mit torsionsweichem Stab (I_T = 0,1 I) konvergiert der
    # raeumliche Fall in keinem der beiden Modelle (Grenze des Verfahrens)
    _vergleich("Th III, Versatz (0; 0,15; 0,1) m, Fz = −1,2 MN, Fy = 0,4 MN, Mx = 50 kNm",
               (0, 0.15, 0.1), (0, 0.15, 0.1), {"Fz": -1.2e6, "Fy": 4e5, "Mx": 5e4}, it=1.5e-4)


def test_gross_veraenderlich():
    """Versatz an Anfang und Ende verschieden (linear von 0 auf (0; 0,1; 0,3) m):
    der Stab liegt schraeg zur Knotenlinie."""
    _vergleich("Th III, Versatz von (0; 0; 0) bis (0; 0,1; 0,3) m, Fz = −1,5 MN, Fx = 0,2 MN",
               (0, 0, 0), (0, 0.1, 0.3), {"Fz": -1.5e6, "Fx": 2e5}, it=1.5e-4)


def test_programmweg():
    """Ueber solve_all (Lastfall nach Theorie III, mit interner Stabteilung):
    dasselbe wie der direkte Aufruf; die Stabteilung teilt den Stab mit
    Versatz nicht."""
    e, F = 0.1, 5e3
    m, ids = _kragarm("versatz", (0, 0, e), (0, 0, e), 4, {"Fx": F}, "III")
    r = _linear(m)
    m2, i2 = _kragarm("versatz", (0, 0, e), (0, 0, e), 4, {"Fx": F}, "III")
    r2, _info = _th3(m2)
    w, w2 = float(r.u[ids[-1], 2]), float(r2.u[i2[-1], 2])
    check("Programmweg (solve_all, Lastfall Theorie III): Ergebnis III. Ordnung = direkter Aufruf (auf 1e-9)",
          str(r.info.get("theorie", "")).startswith("III") and abs(w - w2) <= 1e-9 * abs(w2) and abs(w2) > 0,
          f"{r.info.get('theorie')}, {w * 1e3:.6f} / {w2 * 1e3:.6f} mm, Teilung {r.info.get('stabteilung')}")


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("theorie3_versatz")
    ok = mk is not None and mk.wechsel[-1].stand == 34 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR \
        and rv.VERFAHRENSSTAND >= 34
    m_ja, _ = _kragarm("versatz", (0, 0, 0.1), (0, 0, 0.1), 2, {"Fx": 1.0})
    m_nein, _ = _kragarm("versatz", (0, 0, 0), (0, 0, 0), 2, {"Fx": 1.0})
    ok = ok and mk.betrifft(m_ja) and not mk.betrifft(m_nein)
    check("Verfahrenstabelle: „Theorie III. Ordnung mit Versatz“ Stand 34 als Fehlerkorrektur, "
          "Modellmerkmal Stab mit Versatz", ok, f"Stand {rv.VERFAHRENSSTAND}")


def main():
    np.set_printoptions(suppress=True)
    for t in (test_nachstellung_klein, test_torsion_klein, test_gelenk_klein, test_gross_eben, test_gross_raeumlich,
              test_gross_veraenderlich, test_programmweg, test_verfahrenstabelle):
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
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
