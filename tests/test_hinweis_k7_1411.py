"""
Behebungen vom 14.11.2026, Runde k7 (Agent „hinweis“), vom Anwender
freigegeben („ja, alle vier vorschläge einverstanden“):

(1) Hinweis bei Laengslast: ein Stab mit Stablast in Stabrichtung (auch
    Eigengewicht am lotrechten Stab), der in weniger als vier Elementen
    gerechnet wird, bekommt nach Theorie II./III. Ordnung, bei alpha_cr und
    beim Knicken einen Hinweis im Protokoll. Massgebend ist die tatsaechlich
    gerechnete Elementzahl: die interne Stabteilung der Vorgabe (10) teilt
    ohnehin, dort kein Hinweis. Grundlage: Bericht des Agenten „theorie“ (k6),
    Teillast unten 3,376 statt 3,576 kNm.

(2) Laschenstoss ueber 80 mm ohne Dickentabelle: Splice.momenten_rotation
    holte f_y der Lasche vor der Steifigkeit, warf den C4-ValueError, und
    federn_setzen uebersprang den Anschluss - eine fest „gelenkig“
    modellierte Lasche verlor ihr Gelenk, eine von Hand gesetzte Drehfeder
    fiel weg. Jetzt die Steifigkeit ohne f_y, f_y nur fuer M_j,Rd.

Zwei Wege je Zahl: (1) Programm gegen die finite-Differenzen-Loesung der
DGL (wie D/ag_k6_theorie/referenz.py); (2) Steifigkeit ohne f_y gegen die
mit eingetragenem f_y, Verformung gegen die geschlossene Loesung.

Aufruf:  python -m tests.test_hinweis_k7_1411
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


# --------------------------------------------------------------------------
# (1) Hinweis bei Laengslast
# --------------------------------------------------------------------------
H = 5.0           # Saeule 5 m, lotrecht
QX = 1e3          # Querlast [N/m]
QA = 6e6          # Last in Stabrichtung auf dem unteren Meter [N/m]


def _saeule(n, teilung, theorie="II", qa=QA, stab=True, eigengewicht=False, woelb=False):
    """Gelenkig gelagerte Saeule (wie D/ag_k6_theorie/konv_teil_unten.py) in n
    Elementen: Querlast ueberall, Last in Stabrichtung auf dem unteren Meter
    (oder nur Eigengewicht).

    ``woelb``: Balken mit Woelbkrafttorsion - die interne Stabteilung teilt
    sie nicht. Seit Stand 76 (Runde k10e, Nr. 29) teilen Theorie II.
    Ordnung, alpha_cr und Knicken jeden anderen Stab mit wirksamer
    Normalkraft auch bei Stabteilung 1 mindestens in 10 Teile; nur ein nicht
    teilbarer Stab rechnet dort noch in wenigen Elementen und bekommt den
    Hinweis."""
    from statik3d.model import Model, Material, Section
    m = Model("T")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=7850.0 if eigengewicht else 0.0, fy=355e6))
    m.add_section(Section("Q", A=0.1 if eigengewicht else 0.01, Iy=1e-4, Iz=1e-4, It=1e-5,
                          zmax=0.1, ymax=0.05, Iw=1e-7 if woelb else 0.0))
    m.design.imperfektionen = False
    ids = [m.add_node(0, 0, H * j / n) for j in range(n + 1)]
    els = [m.add_element("beam", [ids[j], ids[j + 1]], "ST", "Q", woelb=woelb) for j in range(n)]
    if stab:
        m.add_member("S1", els)
    m.fix(ids[0], [0, 1, 2, 5])
    m.fix(ids[-1], [0, 1])
    for j, e in enumerate(els):
        m.load_beam(e, qx=QX)
        z0, z1 = H * j / n, H * (j + 1) / n
        if not eigengewicht and qa and z0 < 1.0:
            m.load_beam(e, qz=-qa, a=0.0, b=min(1.0, z1) - z0)
    if eigengewicht:
        m.set_gravity(-9.81)
    lc = m.load_cases[m.active_case]
    lc.theorie = theorie
    m.netz.stabteilung = teilung
    return m, ids, els


def _rechnen(m, **kw):
    from statik3d import solver
    zeilen = []
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, design=False, progress=lambda t, *a: zeilen.append(str(t)), **kw)
    return an, zeilen


def _hinweise(zeilen):
    return [z for z in zeilen if "trägt Last in Stabrichtung" in z]


def _My_max(m, an):
    from statik3d import solver
    r = an.cases[list(an.cases)[0]]
    return max(float(np.abs(solver.beam_station_forces(m, r, e, 41)["My"]).max())
               for e in range(len(m.elements)))


def _referenz_fd(n=2000):
    """Weg 2: finite Differenzen der DGL EI w'' = -M, M'' = -q + (P w')'
    (gelenkig/gelenkig, P Druck positiv), wie D/ag_k6_theorie/referenz.py."""
    from scipy import sparse
    from scipy.sparse import linalg as spl
    EI = 210e9 * 1e-4
    h = H / n
    x = np.linspace(0, H, n + 1)
    mi = n - 1

    def P(xx):                         # Druck aus der Last auf dem unteren Meter
        return QA * np.clip(1.0 - xx, 0.0, 1.0)
    D2 = sparse.diags([np.ones(mi - 1), -2 * np.ones(mi), np.ones(mi - 1)], [-1, 0, 1]) / h ** 2
    pp, pm = P(x[1:-1] + h / 2), P(x[1:-1] - h / 2)
    G = sparse.diags([pm[1:], -(pp + pm), pp[:-1]], [-1, 0, 1]) / h ** 2
    A = sparse.bmat([[EI * D2, sparse.identity(mi)], [-G, D2]]).tocsc()
    b = np.concatenate([np.zeros(mi), -np.full(mi, QX)])
    sol = spl.spsolve(A, b)
    return float(np.abs(sol[mi:]).max())


def test_1_grundlage():
    """Die Zahl im Hinweis: Moment bei Stabteilung 1 gegen die DGL."""
    M_ref = _referenz_fd()
    werte = {}
    for n in (1, 3, 4):
        # nicht teilbar (Woelbkrafttorsion): gerechnet in n Elementen
        m, _i, _e = _saeule(n, 1, woelb=True)
        an, _z = _rechnen(m)
        werte[n] = _My_max(m, an)
    m, _i, _e = _saeule(1, 10)
    an, _z = _rechnen(m)
    vorgabe = _My_max(m, an)
    a = {n: (werte[n] - M_ref) / M_ref for n in werte}
    check("(1) DGL-Referenz Teillast unten 3,576 kNm (Weg 2, finite Differenzen)",
          abs(M_ref / 1e3 - 3.576) < 0.003, f"{M_ref / 1e3:.4f} kNm")
    check("(1) Stabteilung 1, ein Element (nicht teilbar): Moment 5 bis 6 % unter der DGL (unsichere Seite)",
          -0.06 <= a[1] <= -0.05, f"{werte[1] / 1e3:.4f} kNm, {a[1] * 100:+.2f} %")
    check("(1) drei Elemente: noch über 2 % zu klein, vier Elemente: unter 2 % (nicht teilbar)",
          a[3] < -0.02 and abs(a[4]) < 0.02, f"3: {a[3] * 100:+.2f} %, 4: {a[4] * 100:+.2f} %")
    check("(1) Vorgabe 10, ein Element des Modells: intern geteilt, unter 0,5 %",
          abs((vorgabe - M_ref) / M_ref) < 0.005, f"{vorgabe / 1e3:.4f} kNm")
    # Stand 76 (Runde k10e, Nr. 29): ein teilbarer Stab rechnet auch mit
    # Stabteilung 1 in mindestens 10 Teilen - bis dahin -5,6 % wie oben
    m, _i, _e = _saeule(1, 1)
    an, _z = _rechnen(m)
    st1 = _My_max(m, an)
    check("(1) Stabteilung 1, ein teilbares Element: seit Stand 76 intern in 10 Teilen, unter 0,5 %",
          abs((st1 - M_ref) / M_ref) < 0.005, f"{st1 / 1e3:.4f} kNm")


def test_1_theorie2():
    # nicht teilbar (Woelbkrafttorsion): seit Stand 76 der Weg zu einem Stab,
    # der mit Stabteilung 1 in einem Element rechnet
    m, _i, _e = _saeule(1, 1, woelb=True)
    an, z = _rechnen(m)
    h = _hinweise(z)
    soll = ("Stab S1 (Element 0) trägt Last in Stabrichtung und ist in 1 Element geteilt – mindestens "
            "4 Elemente empfohlen, sonst kann das Moment bis etwa 6 % auf der unsicheren Seite liegen")
    check("(1) Th. II, Stabteilung 1, ein Element: Hinweis im Protokoll mit Stab, Element ab 0, Zahl",
          any(soll in x and x.startswith("Hinweis") for x in h), " | ".join(h)[:240])
    check("(1) Th. II: Hinweis in an.info und in der Zusammenfassung",
          any(soll in x for x in (an.info.get("laengslast_teilung") or []))
          and soll in an.summary(), str(an.info.get("laengslast_teilung"))[:160])
    info = an.theorie2.kombinationen[list(an.theorie2.kombinationen)[0]]
    check("(1) Th. II: Hinweis auch beim Lastfall im Theoriekapitel (Th2Info.hinweise)",
          any(soll in x for x in info.hinweise), str(info.hinweise)[:160])
    check("(1) Th. II: Meldung ohne wissenschaftliche Schreibweise",
          not any("e+" in x or "e-0" in x for x in h), "")
    m, _i, _e = _saeule(3, 1, woelb=True)
    _an, z = _rechnen(m)
    check("(1) Th. II, Stabteilung 1, drei Elemente: Hinweis nennt 3 Elemente",
          any("ist in 3 Elemente geteilt" in x for x in _hinweise(z)), " | ".join(_hinweise(z))[:200])
    for n, teil, was in ((4, 1, "vier Elemente"), (1, 10, "Vorgabe 10 (intern geteilt)"),
                         (1, 4, "Stabteilung 4 (intern geteilt)"),
                         (1, 1, "Stabteilung 1, teilbar (seit Stand 76 intern in 10)"),
                         (3, 1, "Stabteilung 1, drei teilbare Elemente (seit Stand 76 intern geteilt)")):
        m, _i, _e = _saeule(n, teil)
        an, z = _rechnen(m)
        check(f"(1) Th. II, {was}: kein Hinweis (kein Fehlalarm)",
              not _hinweise(z) and not an.info.get("laengslast_teilung"), " | ".join(_hinweise(z))[:200])
    # ohne Last in Stabrichtung: kein Hinweis
    m, _i, _e = _saeule(1, 1, qa=0.0)
    _an, z = _rechnen(m)
    check("(1) Th. II, nur Querlast (keine Last in Stabrichtung): kein Hinweis", not _hinweise(z),
          " | ".join(_hinweise(z))[:200])
    # Element ohne Stab
    m, _i, _e = _saeule(1, 1, stab=False, woelb=True)
    _an, z = _rechnen(m)
    check("(1) Th. II, Element ohne Stab: Hinweis nennt das Element ab 0",
          any("Element 0 (ohne Stab) trägt Last in Stabrichtung" in x for x in _hinweise(z)),
          " | ".join(_hinweise(z))[:200])


def test_1_eigengewicht():
    m, _i, _e = _saeule(1, 1, eigengewicht=True, woelb=True)
    _an, z = _rechnen(m)
    check("(1) Eigengewicht am lotrechten Stab, ein Element: Hinweis",
          any("Stab S1 (Element 0)" in x for x in _hinweise(z)), " | ".join(_hinweise(z))[:200])
    # waagerechter Stab mit Eigengewicht und Druck aus Knotenlast: keine Last in Stabrichtung
    from statik3d.model import Model, Material, Section
    m = Model("W")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=7850.0, fy=355e6))
    m.add_section(Section("Q", A=0.1, Iy=1e-4, Iz=1e-4, It=1e-5, zmax=0.1, ymax=0.05))
    m.design.imperfektionen = False
    a, b = m.add_node(0, 0, 0), m.add_node(H, 0, 0)
    e = m.add_element("beam", [a, b], "ST", "Q")
    m.add_member("W1", [e])
    m.fix(a, [0, 1, 2, 3]); m.fix(b, [1, 2])
    m.load_node(b, Fx=-1e6)
    m.set_gravity(-9.81)
    m.load_cases[m.active_case].theorie = "II"
    m.netz.stabteilung = 1
    _an, z = _rechnen(m)
    check("(1) waagerechter Stab: Eigengewicht quer, Druck aus Knotenlast: kein Hinweis",
          not _hinweise(z), " | ".join(_hinweise(z))[:200])


def test_1_theorie3():
    m, _i, _e = _saeule(1, 1, theorie="III")
    an, z = _rechnen(m)
    check("(1) Th. III, Stabteilung 1: intern 2 Elemente (doppelt) – Hinweis nennt 2",
          any("Stab S1 (Element 0)" in x and "ist in 2 Elemente geteilt" in x for x in _hinweise(z)),
          " | ".join(_hinweise(z))[:200])
    info = an.theorie3.kombinationen[list(an.theorie3.kombinationen)[0]] if an.theorie3 else None
    check("(1) Th. III: Hinweis im Theoriekapitel (Th3Info.hinweise)",
          info is not None and any("trägt Last in Stabrichtung" in x for x in info.hinweise),
          str(info and info.hinweise)[:160])
    m, _i, _e = _saeule(1, 2, theorie="III")
    _an, z = _rechnen(m)
    check("(1) Th. III, Stabteilung 2: intern 4 Elemente – kein Hinweis", not _hinweise(z),
          " | ".join(_hinweise(z))[:200])


def test_1_alpha_cr():
    # alpha_cr ueber 10: nur alpha_cr bestimmt, nicht nach Th. II gerechnet
    m, _i, _e = _saeule(1, 1, theorie="I", qa=1e6, woelb=True)
    m.design.theorie2 = "auto"
    m.add_combination("K1", {m.active_case: 1.0})
    an, z = _rechnen(m)
    info = (an.theorie2.kombinationen.get("K1") if an.theorie2 else None)
    check("(1) α_cr (auto, α_cr ≥ 10, nicht nach Th. II gerechnet): Kombination nur mit α_cr",
          info is not None and not info.gerechnet and info.alpha_cr >= 10.0,
          f"{info and info.alpha_cr}")
    check("(1) α_cr: Hinweis im Protokoll und im Theoriekapitel",
          any("Stab S1 (Element 0)" in x for x in _hinweise(z))
          and info is not None and any("trägt Last in Stabrichtung" in x for x in info.hinweise),
          " | ".join(_hinweise(z))[:200])
    m, _i, _e = _saeule(1, 10, theorie="I", qa=1e6)
    m.design.theorie2 = "auto"
    m.add_combination("K1", {m.active_case: 1.0})
    _an, z = _rechnen(m)
    check("(1) α_cr mit Vorgabe 10: kein Hinweis", not _hinweise(z), " | ".join(_hinweise(z))[:200])


def test_1_knicken():
    from statik3d import solver
    # Seit Runde k7 (Agent „knick“) teilt auch das Knicken intern: ein Element
    # mit der Vorgabe 10 rechnet in 10 Teilen - kein Hinweis; mit Stabteilung 1
    # bleibt es ein Element - Hinweis
    # Seit Stand 76 (Runde k10e, Nr. 29) teilt das Knicken einen teilbaren
    # Stab auch mit Stabteilung 1 mindestens in 10 Teile - kein Hinweis; ein
    # nicht teilbarer (Woelbkrafttorsion) bleibt ein Element - Hinweis
    for n, teilung, soll, woelb in ((1, 1, True, True), (1, 10, False, False), (4, 10, False, False),
                                    (1, 1, False, False)):
        m, _i, _e = _saeule(n, teilung, theorie="I", woelb=woelb)
        zeilen = []
        with contextlib.redirect_stdout(io.StringIO()):
            r = solver.solve_buckling(m, 2, lambda t, *a: zeilen.append(str(t)), case=m.active_case)
        h = _hinweise(zeilen)
        if soll:
            check("(1) Knicken, ein Element, Stabteilung 1 (nicht teilbar): Hinweis im Protokoll, "
                  "in res.info und in der Zusammenfassung",
                  any("Stab S1 (Element 0)" in x and "in 1 Element geteilt" in x for x in h)
                  and r.info.get("laengslast_teilung") and "trägt Last in Stabrichtung" in r.summary(),
                  " | ".join(h)[:200])
        else:
            was = ("vier Elemente" if n == 4 else "ein Element intern in 10 geteilt" if teilung == 10
                   else "ein Element, Stabteilung 1, teilbar (seit Stand 76 intern in 10)")
            check(f"(1) Knicken, {was}: kein Hinweis",
                  not h and not r.info.get("laengslast_teilung"), " | ".join(h)[:200])


# --------------------------------------------------------------------------
# (2) Laschenstoss ueber 80 mm ohne Dickentabelle
# --------------------------------------------------------------------------
L_, P_ = 4.0, 20e3


def _traeger(t_fl, modell="automatisch", S_j=0.0, eingabe=None, gestuetzt=False):
    """IPE 300, 4 m in 4 Elementen, links eingespannt; Laschenstoss am Ende
    von Element 1 (x = 2 m). gestuetzt: rechts lotrecht gehalten, Last in der
    Mitte; sonst Kragarm mit Last am Ende."""
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    from statik3d.joints import templates, anschluss
    m = Model("L")
    mt = Material.steel("S355")
    if eingabe:
        mt.erzeugnisnorm_setzen(*eingabe)
    m.add_material(mt)
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    ids = mesher.line_of_beams(m, "S355", "IPE300", (0, 0, 0), (L_, 0, 0), n=4)
    m.fix(ids[0], "all")
    if gestuetzt:
        m.fix(ids[-1], [2])
    m.load_node(ids[2] if gestuetzt else ids[-1], Fz=-P_)
    t = templates.propose("lasche", m, 1, end=1, N=0.0, Vz=20e3, My=80e3)
    t.t_fl = t_fl
    j = anschluss.als_joint(t, name="LS")
    j.modellierung = modell
    if S_j:
        j.S_j = S_j
    m.joints[j.name] = j
    return m, ids


def _u(m, ids, k):
    from statik3d import solver
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, combinations=False)
    res = an.cases[list(an.cases)[0]]
    return an, -float(res.u[ids[k]][2])


def test_2_steifigkeit():
    from statik3d.joints import anschluss
    m0, _ = _traeger(0.090)
    m1, _ = _traeger(0.090, eingabe=(300e6, 450e6))
    t0 = anschluss.vorlage(m0, m0.joints["LS"])
    t1 = anschluss.vorlage(m1, m1.joints["LS"])
    g0 = t0.momenten_rotation(stuetze={}, rahmen="ausgesteift")
    g1 = t1.momenten_rotation(stuetze={}, rahmen="ausgesteift")
    check("(2) Lasche 90 mm ohne Dickentabelle: momenten_rotation ohne Ausnahme, Klasse starr wie mit f_y",
          g0.klasse == g1.klasse == "starr" and g0.S_j_ini == g1.S_j_ini, f"{g0.klasse}/{g1.klasse}")
    hw = " ".join(g0.hinweise)
    check("(2) ohne f_y: M_j,Rd nicht bestimmt (0), Hinweis „f_y nach Erzeugnisnorm eintragen“",
          g0.M_j_Rd == 0.0 and "nach Erzeugnisnorm eintragen" in hw and "M_j,Rd" in hw, hw[:200])
    check("(2) mit eingetragenem f_y 300 N/mm²: M_j,Rd bestimmt (> 0)", g1.M_j_Rd > 0.0,
          f"{g1.M_j_Rd / 1e3:.1f} kNm")


def test_2_gelenkig():
    from statik3d.model import Section, Material
    sec = Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107)
    EI = 210e9 * float(sec.Iy)
    GA = float(Material.steel("S355").G) * float(sec.Asz)
    an50, u50 = _u(*_traeger(0.050, "gelenkig", gestuetzt=True), 2)
    an90, u90 = _u(*_traeger(0.090, "gelenkig", gestuetzt=True), 2)
    zu = P_ * (L_ / 2) ** 3 / (3 * EI) + P_ * (L_ / 2) / GA      # Biegung und Schub
    check("(2) fest gelenkig, Lasche 90 mm: Gelenk bleibt, u = u bei 50 mm (vorher ohne Gelenk)",
          abs(u90 - u50) <= 1e-9 + 1e-9 * u50, f"{u90 * 1e3:.4f} / {u50 * 1e3:.4f} mm")
    check("(2) fest gelenkig: u = P a³/(3 EI) + P a/(G A_z) des Kragarms bis zum Gelenk, a = L/2 (geschlossen)",
          abs(u90 - zu) <= 1e-4 * zu, f"{u90 * 1e3:.4f} mm, geschlossen {zu * 1e3:.4f} mm")
    check("(2) fest gelenkig: kein übersprungener Anschluss", not an90.info.get("anschluesse_uebersprungen"),
          str(an90.info.get("anschluesse_uebersprungen"))[:160])


def test_2_feder_von_hand():
    S = 20e6
    _a, us = _u(*_traeger(0.090, "starr"), -1)
    _a, u50 = _u(*_traeger(0.050, S_j=S), -1)
    an, u90 = _u(*_traeger(0.090, S_j=S), -1)
    zu = P_ * (L_ / 2) * (L_ / 2) / S
    check("(2) Drehfeder von Hand 20 MNm/rad, Lasche 90 mm: wie bei 50 mm",
          abs(u90 - u50) <= 1e-9 + 1e-9 * u50, f"{u90 * 1e3:.4f} / {u50 * 1e3:.4f} mm")
    check("(2) Drehfeder: u = u starr + P (L/2)²/S_j (geschlossen)",
          abs((u90 - us) - zu) <= 1e-3 * zu, f"{(u90 - us) * 1e3:.4f} mm, P (L/2)²/S_j {zu * 1e3:.4f} mm")
    _a, ua = _u(*_traeger(0.090), -1)
    check("(2) automatisch (starr): u = u starr, unverändert", abs(ua - us) <= 1e-12 + 1e-9 * us,
          f"{ua * 1e3:.4f} / {us * 1e3:.4f} mm")


def test_2_nachweis():
    from statik3d.joints import anschluss
    m, ids = _traeger(0.090, "gelenkig", gestuetzt=True)
    an, _u0 = _u(m, ids, 2)
    c = anschluss.check_joint(m, m.joints["LS"], dict(an.cases), an)
    check("(2) Anschlussnachweis ohne f_y der Lasche: nicht geführt, Meldung nennt Erzeugnisnorm",
          "nach Erzeugnisnorm eintragen" in (c.fehler or "") and c.status() == "nicht geführt",
          (c.fehler or "")[:160])
    check("(2) Nachweis: Gelenkkennwerte bestimmt (kein „nicht bestimmbar“)",
          c.gelenk is not None and not any("nicht bestimmbar" in h for h in c.hinweise), str(c.hinweise)[:160])


def test_2_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("laschenstoss_ueber_80")
    check("(2) Merkmal laschenstoss_ueber_80: Stand 59, Fehlerkorrektur, VERFAHRENSSTAND ≥ 59",
          mk is not None and mk.wechsel[-1].stand == 59 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 59, str(mk and mk.wechsel))
    if mk is None:
        return
    ja = [_traeger(0.090, "gelenkig")[0], _traeger(0.090, S_j=20e6)[0]]
    nein = [_traeger(0.050, "gelenkig")[0], _traeger(0.090, "gelenkig", eingabe=(300e6, 450e6))[0],
            _traeger(0.090)[0], _traeger(0.090, "starr")[0]]
    check("(2) Merkmal betrifft: 90 mm gelenkig und mit Drehfeder von Hand",
          all(mk.betrifft(x) for x in ja), "")
    check("(2) Merkmal betrifft nicht: 50 mm, mit Eintrag, automatisch (starr wie vorher), fest starr",
          not any(mk.betrifft(x) for x in nein), str([mk.betrifft(x) for x in nein]))


def main():
    for t in (test_1_grundlage, test_1_theorie2, test_1_eigengewicht, test_1_theorie3, test_1_alpha_cr,
              test_1_knicken, test_2_steifigkeit, test_2_gelenkig, test_2_feder_von_hand, test_2_nachweis,
              test_2_merkmal):
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
