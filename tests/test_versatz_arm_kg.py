"""
Geometrische Steifigkeit des starren Versatz-Arms nach Theorie II. Ordnung,
14.11.2026 (Verfahrensstand 40).

Der Versatz eines Stabendes ist seit Stand 38 ein starrer Arm a vom Knoten
zum Stabende. Dreht sich der Knoten um theta, liegt das Stabende bei
x + a + theta x a; die Stabendkraft F greift dort an. Nach Theorie III.
Ordnung dreht der Arm mit (theorie3._Stab.knoten: Moment a x F mit dem
gedrehten Arm, Tangente [F]x [a]x). Theorie II. Ordnung kannte diesen Anteil
nicht: das Moment a x F blieb beim unverdrehten Arm, das Gleichgewicht am
verformten System fehlte um (theta x a) x F.

Nachstellung am Stand 772ff97: Kragarm 4 m in 8 Elementen, Versatz linear
0 → (0; 0,05; 0,1) m, Druck 200 kN mit Momenten Mx 0,5, My 2, Mz −1 kNm an
der Spitze: Einspannmoment Mz nach Th II 1,35506, nach Th III 1,30120 kNm
(4 %); ohne Versatz stimmen beide auf 1,5e-5. Gelenkstuetze mit axialen
Armen 0,5 m an beiden Enden: alpha_cr 129,54 (Euler des Stabs allein) statt
83,958 (geschlossen, k e tan(k L/2) = 1) - 54 % auf der unsicheren Seite.

Seither der Armanteil K_a = [F]x [a]x am Drehblock jedes Knotens mit Arm
(assemble.versatz_arm_kg), in der Iteration nach Theorie II. Ordnung voll
(unsymmetrisch, die Statik des gedrehten Arms wie Theorie III. Ordnung), in
alpha_cr und im Knicken sein symmetrischer Teil: die Eigenwertloeser dort
setzen Symmetrie voraus, und nach Rayleigh ist alpha_cr aus dem
symmetrischen Teil eine untere Schranke jedes reellen Verzweigungsfaktors
des unsymmetrischen Problems (sichere Seite); liegt F laengs des Arms, sind
beide gleich.

Zwei Wege je Zahl:
1. Theorie III. Ordnung (kleine Last) bzw. die Handstatik am verformten
   System; geschlossene Loesung der Knicklast;
2. das Kurzstabmodell (Stab an eigenen Knoten, steife Kurzstaebe statt
   Versatz) - nach Theorie II. Ordnung nur, wo die Kraft laengs des Arms
   liegt: der Kurzstab bekommt dann mit seiner Normalkraft N_k genau den
   Armanteil; quer zum Kurzstab kennt Theorie II. Ordnung keine
   geometrische Steifigkeit aus Querkraft und Moment.

Aufruf:  python -m tests.test_versatz_arm_kg
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

import tests.test_versatz_starrer_arm as tv  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


def _th3(m):
    from statik3d.theorie3 import solve_theorie3
    r, info = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=10, imperfektionen=False, stabteilung=False)
    return r, info


R2 = (0, 0.05, 0.1)


def _messbeispiel(f):
    return {"Fx": -200e3 * f, "Mx": 0.5e3 * f, "My": 2e3 * f, "Mz": -1e3 * f}


# ---------------------------------------------------------------- Theorie III.
def test_messbeispiel_theorie3():
    """Das Messbeispiel gegen Theorie III. Ordnung bei voller und viertel Last."""
    abw = []
    for f in (1.0, 0.25):
        last = _messbeispiel(f)
        m2, i2, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "II")
        r2 = tv._rechnen(m2)
        m3, i3, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "III")
        r3, info = _th3(m3)
        M2, M3 = r2.reactions[i2[0], 3:], r3.reactions[i3[0], 3:]
        abw.append(tv._rel(M2, M3))
        grenze = 1e-3 if f == 1.0 else 1e-4
        check(f"Th II, Kragarm, Versatz 0 → (0; 0,05; 0,1) m, Druck {200 * f:.0f} kN mit Momenten: "
              f"Einspannmomente wie Th III (auf {grenze:.0e}; vorher 1,97e-2 bzw. 5,8e-3)",
              not info.fehler and abw[-1] < grenze,
              f"Th II {np.round(M2 / 1e3, 5)}, Th III {np.round(M3 / 1e3, 5)} kNm, rel {abw[-1]:.2e}")
    check("… die Abweichung zu Th III fällt mit der Last (2. Ordnung klein): 200/50 kN mindestens Faktor 8",
          abw[1] > 0 and abw[0] / abw[1] >= 8.0, f"{abw[0]:.2e} / {abw[1]:.2e}")


def test_gleichgewicht_verformt():
    """Gleichgewicht am verformten System, von Hand mit u aus Theorie II.
    Ordnung selbst: Einspannmoment + M + (X + u) x F = 0 an der Spitze. Der
    Arm liegt innen; dreht er nicht mit, fehlt (theta x a) x F."""
    last = _messbeispiel(1.0)
    m1, i1, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "I")
    r1 = tv._rechnen(m1)
    m2, i2, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "II")
    r2 = tv._rechnen(m2)
    F = np.array([last.get(k, 0.0) for k in ("Fx", "Fy", "Fz")])
    M = np.array([last.get(k, 0.0) for k in ("Mx", "My", "Mz")])
    X = np.asarray(m2.nodes[i2[-1]], float) + r2.u[i2[-1], :3]
    rest = r2.reactions[i2[0], 3:] + M + np.cross(X, F)
    zuwachs = float(np.linalg.norm(r2.reactions[i2[0], 3:] - r1.reactions[i1[0], 3:]))
    check("Th II, Messbeispiel: ΣM um die Einspannung am verformten System = 0 (Rest ≤ 1 % des Zuwachses "
          "M_II − M_I; vorher ≈ (θ × a) × F)", float(np.linalg.norm(rest)) <= 0.01 * zuwachs,
          f"Rest {np.round(rest, 2)} Nm, Zuwachs {zuwachs:.1f} Nm")


def test_stablast_alpha_cr():
    """Die Stabendkraft des Arms mit den Stablasten (feq): Gelenkstuetze mit
    axialen Armen 0,5 m, Druck 100 kN oben und eine Streckenlast laengs des
    Stabs (−100 kN/m zum Fusspunkt hin). Die Armkraft liegt laengs des Arms -
    das Kurzstabmodell rechnet sie nach Theorie II. Ordnung genau. An den
    inneren Knoten heben sich die Armanteile beider Elemente nur mit den
    Festeinspannkraeften auf (Gleichgewicht des Stabpunkts)."""
    e = 0.5
    mv, _i, _s = _stuetze("versatz", e, qx=-100e3)
    mk, _i, _s = _stuetze("kurzstab", e, qx=-100e3)
    a, ak = tv._rechnen(mv).info.get("alpha_cr"), tv._rechnen(mk).info.get("alpha_cr")
    check("α_cr, dieselbe Stütze mit Streckenlast −100 kN/m längs des Stabs: wie das Kurzstabmodell "
          "(auf 1e-4)", a is not None and ak is not None and abs(a / ak - 1) < 1e-4,
          f"Versatz {a}, Kurzstab {ak}")


def test_ama_symmetrisch():
    """Die Matrix der Iteration bleibt symmetrisch (der schiefsymmetrische
    Teil des Armanteils steht als Last aus dem vorigen Schritt): dasselbe
    Messbeispiel mit dem Gleichungsloeser ama, der nur symmetrische Matrizen
    nimmt - wie Theorie III. Ordnung. Mit der vollen Matrix brach ama ab, und
    Theorie II. Ordnung gab still das Ergebnis I. Ordnung (Zwischenstand des
    Baus, 14.11.2026)."""
    try:
        import ama  # noqa: F401
    except ImportError:
        check("Th II mit ama: ama nicht installiert - übersprungen", True)
        return
    from statik3d import parallel
    st = parallel.settings()
    vorher = st.solver_backend
    try:
        st.solver_backend = "ama"
        last = _messbeispiel(1.0)
        m2, i2, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "II")
        r2 = tv._rechnen(m2)
    finally:
        st.solver_backend = vorher
    m3, i3, _e = tv._kragarm("versatz", (0, 0, 0), R2, 8, last, "III")
    r3, _info = _th3(m3)
    d = tv._rel(r2.reactions[i2[0], 3:], r3.reactions[i3[0], 3:])
    check("Th II mit dem Löser ama, Messbeispiel: Einspannmomente wie Th III (auf 1e-3)",
          r2.info.get("solver") == "ama" and d < 1e-3,
          f"Löser {r2.info.get('solver')}, {np.round(r2.reactions[i2[0], 3:] / 1e3, 5)} kNm, rel {d:.2e}")


# ---------------------------------------------------------------- alpha_cr
def _stuetze(art, e, n=16, P=100e3, seitlich=False, last_mitte=None, qx=0.0):
    """Gelenkstuetze: Knoten 0 gehalten (u, phi_x), Knoten n quer gehalten,
    Druck P in der Knotenlinie. Axial: Knotenlinie L + 2e, Arme (+e; 0; 0)
    und (−e; 0; 0), der Stab 4 m lang. Seitlich: gleicher Arm (0; 0; e).
    art "kurzstab": der Stab an eigenen Knoten, steife Kurzstaebe an den
    Enden. Rueckgabe (Modell, Knoten der Knotenlinie, Knoten des Stabs)."""
    from statik3d.model import Model, Material, Section
    m = Model("S")
    m.add_material(Material("ST", E=tv.E, nu=tv.NU, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=tv.A, Iy=tv.I, Iz=tv.I, It=1e-5, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=tv.STARR[0], Iy=tv.STARR[1], Iz=tv.STARR[1], It=tv.STARR[1],
                          zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    L = tv.L
    if seitlich:
        Ln, r1, r2 = L, np.array([0.0, 0.0, e]), np.array([0.0, 0.0, e])
    else:
        Ln, r1, r2 = L + 2 * e, np.array([e, 0.0, 0.0]), np.array([-e, 0.0, 0.0])

    def r(k):
        return r1 + (r2 - r1) * k / n
    if art == "versatz":
        ids = [m.add_node(Ln * k / n, 0, 0) for k in range(n + 1)]
        stab = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q",
                              exzentrizitaet=[r(k).tolist(), r(k + 1).tolist()]) for k in range(n)]
        st = ids
    else:
        ids = [m.add_node(0, 0, 0), m.add_node(Ln, 0, 0)]
        st = [m.add_node(Ln * k / n + r(k)[0], r(k)[1], r(k)[2]) for k in range(n + 1)]
        stab = [m.add_element("beam", [st[k], st[k + 1]], "ST", "Q") for k in range(n)]
        m.add_element("beam", [ids[0], st[0]], "ST", "STARR")
        m.add_element("beam", [ids[1], st[-1]], "ST", "STARR")
        ids = [ids[0]] + [None] * (n - 1) + [ids[1]]
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2])
    m.load_node(ids[-1], Fx=-P)
    if last_mitte:
        m.load_node(st[n // 2], **last_mitte)
    if qx:
        for i in stab:
            m.load_beam(i, qx=qx, case="LF1")
    m.load_cases["LF1"].theorie = "II"
    return m, ids, st


def test_alpha_cr_axial():
    from scipy.optimize import brentq
    e, P, L = 0.5, 100e3, tv.L
    k = brentq(lambda k: k * e * math.tan(k * L / 2) - 1.0, 1e-6, math.pi / L - 1e-9)
    soll = tv.E * tv.I * k ** 2 / P
    mv, _i, _s = _stuetze("versatz", e)
    a = tv._rechnen(mv).info.get("alpha_cr")
    check(f"α_cr, Gelenkstütze 4 m mit axialen Armen 0,5 m an beiden Enden: k e tan(kL/2) = 1, "
          f"α_cr = {soll:.6f} (geschlossen, auf 1e-5; vorher 129,5388)",
          a is not None and abs(a / soll - 1) < 1e-5, f"Programm {a}")
    mk, _i, _s = _stuetze("kurzstab", e)
    ak = tv._rechnen(mk).info.get("alpha_cr")
    check("… wie das Kurzstabmodell (Kraft längs des Arms; auf 1e-4)",
          a is not None and ak is not None and abs(a / ak - 1) < 1e-4, f"Versatz {a}, Kurzstab {ak}")
    # Theorie II. Ordnung mit kleiner Querlast in Stabmitte gegen das Kurzstabmodell
    last = {"Fy": 1e3, "Fz": -2e3}
    mv, iv, sv = _stuetze("versatz", e, P=4e6, last_mitte=last)
    mk, ik, sk = _stuetze("kurzstab", e, P=4e6, last_mitte=last)
    rv, rk = tv._rechnen(mv), tv._rechnen(mk)
    n = len(sv) - 1
    d = tv._rel(rv.u[sv[n // 2], :3], rk.u[sk[n // 2], :3])
    check("Th II, dieselbe Stütze mit 4 MN (α ≈ 2,1) und Querlast in Stabmitte: Durchbiegung wie mit "
          "Kurzstäben (auf 1e-3)", d < 1e-3,
          f"Versatz {np.round(rv.u[sv[n // 2], :3] * 1e3, 4)}, Kurzstab {np.round(rk.u[sk[n // 2], :3] * 1e3, 4)} mm")


def test_alpha_cr_untere_schranke():
    """Gleicher seitlicher Versatz 0,3 m: der Armanteil ist dort
    unsymmetrisch. alpha_cr aus dem symmetrischen Teil liegt unter dem
    kleinsten reellen Verzweigungsfaktor des vollen Problems (dicht)."""
    import scipy.linalg as sla
    from statik3d import solver, assemble as asm
    m, _i, _s = _stuetze("versatz", 0.3, seitlich=True)
    a = tv._rechnen(m).info.get("alpha_cr")
    sy = solver.StaticSystem(m)
    F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
    u = sy.solve(F)
    Kg = asm.geometric_stiffness(m, u, feq=feq).toarray()
    Ks = asm.geometric_stiffness(m, u, feq=feq, symmetrisch=True).toarray()
    fi = sy.fi
    K = sy.Kff.toarray()
    mu = sla.eigvals(-Kg[np.ix_(fi, fi)], K)
    mu = mu[np.isfinite(mu)]
    reell = mu[np.abs(mu.imag) <= 1e-9 * np.abs(mu).max()].real
    a_voll = 1.0 / reell.max()
    mus = sla.eigvalsh(-Ks[np.ix_(fi, fi)], K)
    a_sym = 1.0 / mus.max()
    check("α_cr, gleicher seitlicher Versatz 0,3 m: α_cr = symmetrischer Teil (dicht, auf 1e-8) und "
          "≤ α_cr des unsymmetrischen Problems (untere Schranke)",
          a is not None and abs(a / a_sym - 1) < 1e-8 and a <= a_voll * (1 + 1e-9)
          and np.allclose(Ks, 0.5 * (Kg + Kg.T), rtol=0.0, atol=1e-12 * np.abs(Kg).max()),
          f"Programm {a}, symmetrisch {a_sym:.6f}, unsymmetrisch {a_voll:.6f}")


# ---------------------------------------------------------------- bitgleich
def test_bitgleich_ohne_versatz():
    """Ohne Versatz (und mit Versatz null) ist die geometrische Steifigkeit
    dieselbe Matrix wie ohne die neuen Angaben (Stablasten, symmetrisch)."""
    from statik3d import solver, assemble as asm
    ok = True
    for ex in ([], [[0, 0, 0], [0, 0, 0]]):
        m, ids, els = tv._kragarm("versatz", (0, 0, 0), (0, 0, 0), 4, _messbeispiel(1.0), "II",
                                  stablasten=({"qz": -2e3},))
        for i in els:
            m.elements[i].exzentrizitaet = ex
        sy = solver.StaticSystem(m)
        F, feq, _q, _t = solver.case_loads(m, {"LF1": 1.0})
        u = sy.solve(F)
        K0 = asm.geometric_stiffness(m, u)
        for kw in ({"feq": feq}, {"feq": feq, "symmetrisch": True}):
            K1 = asm.geometric_stiffness(m, u, **kw)
            ok = ok and K1.shape == K0.shape and np.array_equal(K1.toarray(), K0.toarray())
        ok = ok and asm.versatz_arm_kg(m, u, feq=feq) is None
    check("Ohne Versatz und mit Versatz null: K_G bitgleich mit und ohne Stablasten/symmetrisch, kein "
          "Armanteil", ok)


# ---------------------------------------------------------------- Verfahrenstabelle
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("versatz_arm_kg")
    ok = mk is not None and mk.wechsel[-1].stand == 40 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR \
        and rv.VERFAHRENSSTAND >= 40
    m_ja, _i, _e = tv._kragarm("versatz", (0, 0, 0), (0, 0, 0.1), 2, {"Fx": 1.0}, "II")
    m_gleich, _i, _e = tv._kragarm("versatz", (0, 0, 0.1), (0, 0, 0.1), 2, {"Fx": 1.0}, "II")
    m_nein, _i, _e = tv._kragarm("versatz", (0, 0, 0), (0, 0, 0), 2, {"Fx": 1.0}, "II")
    ok = ok and mk.betrifft(m_ja) and mk.betrifft(m_gleich) and not mk.betrifft(m_nein)
    check("Verfahrenstabelle: „Armanteil der geometrischen Steifigkeit“ Stand 40 als Fehlerkorrektur, "
          "betroffen Stäbe mit Versatz (auch gleichem), nicht ohne", ok, f"Stand {rv.VERFAHRENSSTAND}")


def main():
    np.set_printoptions(suppress=True)
    for t in (test_messbeispiel_theorie3, test_gleichgewicht_verformt, test_ama_symmetrisch,
              test_stablast_alpha_cr,
              test_alpha_cr_axial, test_alpha_cr_untere_schranke, test_bitgleich_ohne_versatz,
              test_verfahrenstabelle):
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
