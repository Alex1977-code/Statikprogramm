"""
Behebung vom 15.11.2026, Runde k8 (Agent „th3“), Verfahrensstand 64, vom
Anwender freigegeben („1 ja“).

(a) Theorie III. Ordnung las nur die Knotenkopplungen (asm.kopplungen), nie
die Starrkörper (Model.starrkoerper, RBE2 und RBE3). Kragstütze 4 m mit
Arm 0,3 m quer am Kopf als RBE2: nach Theorie I. Ordnung 7,032 mm, nach
Theorie III. Ordnung still 0,000 mm (der Kopfknoten hing an nichts, seine
Last ging in die automatische Haltung). Derselbe Arm als Balken STARR oder
als Versatz der Stabenden: 8,23 mm. Ein RBE3-Lastknoten am Kragarmende gab
nach Theorie III. Ordnung 0 mm statt F L³/(3 E I).

Starre Knotenkopplungen (Kopplung mit Steifigkeit „inf“) rechnete Theorie
III. Ordnung mit einer Straffeder, deren Bezug eine leere Matrix war: 1e4 N/m.
Zwei Kragarme 3 m, im Feldpunkt starr gekoppelt, 1 kN: Theorie I. Ordnung
und Handrechnung 0,2679 mm, Theorie III. Ordnung 0,5329 mm (nur ein Kragarm
trägt). Kopplungen mit endlicher Federsteifigkeit rechnet sie richtig
(0,3972 mm wie Hand und Theorie I. Ordnung) - sie bleiben.

Behebung: beides wird mit Klartext abgewiesen (theorie3.kopplung_sperre),
wie bei der Wölbkrafttorsion: Meldung, Th3Info.fehler, lineares Ergebnis
markiert, Modellprüfung als FEHLER. Nur Starrkörper und Kopplungen zählen,
an denen in der gerechneten Situation ein wirksames Element hängt.

(b) Web-Schnittstelle: nach einer Knickrechnung zeigte result_payload ohne
gewählte Form die Form 1 (der Browser schickte mode=0 als Vorgabe), auch
wenn ihr Faktor negativ ist. Seither ohne Wahl die maßgebende Form
(solver.massgebende_knickform); eine ausdrücklich gewählte Form bleibt.

Zwei Wege je Zahl: Handformel (Kragarm F L³/(3 E I), Federn in Reihe/parallel)
und Theorie I. Ordnung im Programm; für die Ersatzlösungen des Arms Balken
STARR und Versatz der Stabenden (zwei verschiedene Programmwege).

Runde k10e (16.11.2026, Stand 77, Fehler Nr. 27): Theorie III. Ordnung
rechnet Starrkörper und starre Kopplungen seither als Zwangsbedingung im
mitgedrehten System des Masters (theorie3._Zwang). Wo diese Datei „mit
Klartext abgewiesen“ prüfte, prüft sie jetzt das Ergebnis gegen dieselben
zwei Wege (Hand bzw. Theorie I. Ordnung bei kleiner Last, Balken STARR und
Versatz für den Arm); die Merkmale des Stands 64 betreffen weiter dieselben
Modelle (theorie3.kopplung_wirkung_modell).

Aufruf:  python -m tests.test_th3_starrkoerper_k8
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
E = 210e9
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_SK = "Theorie III. Ordnung rechnet keine Starrkörper"
TEXT_KP = "Theorie III. Ordnung rechnet keine starren Knotenkopplungen"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def nahe(name, ist, soll, rel):
    ok = ist is not None and math.isfinite(ist) and abs(ist - soll) <= rel * max(abs(soll), 1e-30)
    return check(name, ok, f"ist {ist if ist is None else f'{ist:.6g}'}, soll {soll:.6g} (±{rel * 100:g} %)")


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _th3(m, lf="LF1", aktiv=None, stabteilung=True):
    """(Verschiebungen (nn, 6) oder None, Meldung)."""
    from statik3d.theorie3 import solve_theorie3
    try:
        r, info = _still(solve_theorie3, m, {lf: 1.0}, lf, imperfektionen=False, aktiv=aktiv,
                         stabteilung=stabteilung)
    except ValueError as ex:
        return None, str(ex)
    return np.asarray(r.u).reshape(-1, 6), info.fehler


def _th1(m, lf="LF1"):
    from statik3d import solver
    return np.asarray(_still(solver.solve_static, m, case=lf).u).reshape(-1, 6)


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def _kragstuetze(art, P=200e3, Hy=1e3, Hz=2e3, n_st=10):
    """Kragstütze 4 m längs x, eingespannt in a = (0,0,0), Lastknoten
    b = (4,0,0), Stabachse bis (4,0,0,3): der Arm von b zum Stabende 0,3 m
    quer als RBE2 (Master b), als Balken STARR oder als Versatz am Stabende
    (wie ag_k8_starr2/modelle.py der Hauptsitzung)."""
    from statik3d.model import Model, Material, Section
    m = Model("K")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=8e-5, Iz=2e-5, It=1e-5, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=0.1, Iy=1e-2, Iz=1e-2, It=1e-2, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    a = m.add_node(0, 0, 0)
    b = m.add_node(4.0, 0, 0)
    m.fix(a, "all")
    ende = np.array([4.0, 0.0, 0.3])
    if art == "versatz":
        m.netz.stabteilung = n_st
        stab = [m.add_element("beam", [a, b], "ST", "Q", exzentrizitaet=[[0, 0, 0], [0, 0, 0.3]])]
    else:
        m.netz.stabteilung = 1
        ids = [a] + [m.add_node(*(ende * k / n_st)) for k in range(1, n_st + 1)]
        stab = [m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q") for k in range(n_st)]
        if art == "starr":
            m.add_element("beam", [b, ids[-1]], "ST", "STARR")
        else:
            m.add_starrkoerper(b, [ids[-1]], "RBE2", name="Arm")
    m.add_member("S", stab)
    m.load_node(b, Fx=-P, Fy=Hy, Fz=Hz)
    return m, b


L_K = 3.0
I_K = 8e-5
F_K = 1e3


def _kragarm_rbe3():
    """Kragarm 3 m, Last 1 kN am Lastknoten, der über RBE3 am Kragarmende hängt."""
    from statik3d.model import Model, Material, Section
    m = Model("R")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I_K, Iz=I_K, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_K, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    lk = m.add_node(L_K, 0, 0)
    m.add_starrkoerper(lk, [b], "RBE3", name="Last")
    m.load_node(lk, Fz=-F_K)
    return m, b


def _zwei_kragarme(k):
    """Zwei Kragarme 3 m gegeneinander, im Feldpunkt über eine Kopplung
    deckungsgleicher Knoten (x, y, z) mit der Steifigkeit k verbunden."""
    from statik3d.model import Model, Material, Section, Kopplung
    m = Model("KP")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I_K, Iz=I_K, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_K, 0, 0)
    c = m.add_node(L_K, 0, 0)
    d = m.add_node(2 * L_K, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.add_element("beam", [c, d], "ST", "Q")
    m.fix(a, "all")
    m.fix(d, "all")
    m.kopplungen.append(Kopplung(b, c, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [k, k, k], "Fuge"))
    m.load_node(b, Fz=-F_K)
    return m, b


def _mit_situation():
    """Kragarm (Element 0, Last in LF1 und LF2) und daneben ein zweiter
    Kragarm (Element 1) mit einem RBE2 an seinem Ende. Situation „ohne“
    schaltet Element 1 ab: dort hängt am Starrkörper kein wirksames Element."""
    from statik3d.model import Model, Material, Section, Situation
    m = Model("S")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I_K, Iz=I_K, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_K, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    c = m.add_node(0, 2, 0)
    d = m.add_node(L_K, 2, 0)
    m.add_element("beam", [c, d], "ST", "Q")
    m.fix(c, "all")
    g = m.add_node(L_K, 2.5, 0)
    m.add_starrkoerper(d, [g], "RBE2", name="Nebenarm")
    m.situationen["ohne"] = Situation("ohne", "", [1])
    m.load_node(b, Fz=-F_K)
    m.add_load_case("LF2")
    m.load_cases["LF2"].situation = "ohne"
    m.load_node(b, Fz=-F_K, case="LF2")
    m.load_cases["LF1"].theorie = "III"
    m.load_cases["LF2"].theorie = "III"
    return m, b


def _hand_kragarm():
    return F_K * L_K ** 3 / (3 * E * I_K)


# --------------------------------------------------------------------------
# (a) Starrkörper
# --------------------------------------------------------------------------
def test_rbe2_arm():
    m_r, b_r = _kragstuetze("rbe2")
    m_s, b_s = _kragstuetze("starr")
    m_v, b_v = _kragstuetze("versatz")
    u1_r = float(np.abs(_th1(m_r)[b_r, :3]).max())
    u1_s = float(np.abs(_th1(m_s)[b_s, :3]).max())
    print(f"   Th I Kopfknoten: RBE2 {u1_r * 1e3:.3f} mm, Balken STARR {u1_s * 1e3:.3f} mm")
    nahe("Th I: RBE2-Arm wie Balken STARR (zwei Programmwege)", u1_r, u1_s, 1e-3)
    u3_s, f_s = _th3(m_s)
    u3_v, f_v = _th3(m_v)
    w_s = None if u3_s is None else float(np.abs(u3_s[b_s, :3]).max())
    w_v = None if u3_v is None else float(np.abs(u3_v[b_v, :3]).max())
    print(f"   Th III Kopfknoten: Balken STARR {w_s * 1e3:.3f} mm, Versatz {w_v * 1e3:.3f} mm"
          if w_s is not None and w_v is not None else f"   Th III: {f_s} {f_v}")
    check("Th III mit Balken STARR und mit Versatz gerechnet (die Auswege der Meldung)",
          u3_s is not None and u3_v is not None and not f_s and not f_v, f"{f_s} {f_v}")
    if w_s is not None and w_v is not None:
        nahe("Th III: Balken STARR wie Versatz (zwei Programmwege)", w_s, w_v, 5e-3)
        check("Th III größer als Th I (Druck mit Ausmitte)", w_s > 1.1 * u1_s, f"{w_s * 1e3:.3f} mm")
    u3_r, text = _th3(m_r)
    w_r = None if u3_r is None else float(np.abs(u3_r[b_r, :3]).max())
    print(f"   Th III RBE2: {'abgewiesen' if u3_r is None else f'{w_r * 1e3:.3f} mm'} – {text}")
    # seit Stand 77 gerechnet (bis Stand 63 still 0,000 mm, bis 76 abgewiesen)
    check("Th III mit RBE2 gerechnet (seit Stand 77), nicht still 0 mm", u3_r is not None and not text
          and w_r is not None and w_r > 1e-3, text[:120])
    if w_r is not None and w_s is not None and w_v is not None:
        nahe("… Kopfknoten wie Balken STARR (zweiter Programmweg)", w_r, w_s, 1e-3)
        nahe("… Kopfknoten wie Versatz (dritter Programmweg)", w_r, w_v, 5e-3)
    check("Meldung ohne wissenschaftliche Schreibweise", "e+" not in text and "e-0" not in text)


def test_rbe3_lastknoten():
    m, b = _kragarm_rbe3()
    hand = _hand_kragarm()
    w1 = float(-_th1(m)[b, 2])
    nahe("RBE3-Lastknoten Th I = F L³/(3 E I) (Hand)", w1, hand, 1e-3)
    u3, text = _th3(m, stabteilung=False)
    print(f"   Th III: {'abgewiesen' if u3 is None else f'{-u3[b, 2] * 1e3:.4f} mm'} – {text}")
    check("Th III mit RBE3 gerechnet (seit Stand 77), nicht still 0 mm", u3 is not None and not text, text[:120])
    if u3 is not None:
        nahe("… w(b) = F L³/(3 E I) (Hand, kleine Last)", float(-u3[b, 2]), hand, 1e-6)
        nahe("… w(b) = Theorie I. Ordnung", float(-u3[b, 2]), w1, 1e-6)


def test_situation():
    """Nur Starrkörper zählen, an denen ein wirksames Element hängt."""
    from statik3d import solver
    m, b = _mit_situation()
    hand = _hand_kragarm()
    an = _still(solver.solve_all, m, workers=1, design=False)
    i1 = an.theorie3.kombinationen.get("LF1") if an.theorie3 is not None else None
    i2 = an.theorie3.kombinationen.get("LF2") if an.theorie3 is not None else None
    f1 = getattr(i1, "fehler", "") or ""
    f2 = getattr(i2, "fehler", "") or ""
    print(f"   LF1 (Grundstellung): {f1[:100]}")
    print(f"   LF2 (Situation ohne den Nebenarm): {f2[:100]}")
    check("Grundstellung: RBE2 am Nebenarm wirkt mit, Th III gerechnet (seit Stand 77)",
          i1 is not None and not f1, f1[:100])
    r1 = an.cases.get("LF1")
    check("… Ergebnis LF1 nach Theorie III. Ordnung",
          r1 is not None and str(r1.info.get("theorie", "")).startswith("III"),
          str(None if r1 is None else r1.info.get("theorie")))
    w1_ = None if r1 is None else float(-np.asarray(r1.u).reshape(-1, 6)[b, 2])
    nahe("… Kragarmende LF1 nach Th III = F L³/(3 E I) (kleine Last, Hand)", w1_, hand, 1e-3)
    check("Situation mit abgeschaltetem Nebenarm: Th III gerechnet", i2 is not None and not f2, f2[:100])
    r2 = an.cases.get("LF2")
    w2 = None if r2 is None else float(-np.asarray(r2.u).reshape(-1, 6)[b, 2])
    nahe("… Kragarmende nach Th III = F L³/(3 E I) (kleine Last, Hand)", w2, hand, 1e-3)
    msgs = m.check()
    treffer = [z for z in msgs if "Theorie III" in z and z.startswith("FEHLER")]
    check("Modellprüfung: kein FEHLER zu Theorie III. Ordnung (seit Stand 77)", not treffer,
          "; ".join(treffer)[:200])
    m.load_cases["LF1"].theorie = "II"
    check("Modellprüfung nach Theorie II. Ordnung ohne diese Meldung",
          not any(TEXT_SK in z for z in m.check()))


def test_kombination():
    from statik3d import solver
    m, b = _kragstuetze("rbe2")
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    m.combinations["K1"].theorie = "III"
    an = _still(solver.solve_all, m, workers=1, design=False)
    info = an.theorie3.kombinationen.get("K1") if an.theorie3 is not None else None
    f = getattr(info, "fehler", "") or ""
    check("Kombination nach Th III mit RBE2: gerechnet (seit Stand 77)", info is not None and not f, f[:100])
    rk = an.combinations.get("K1")
    check("… Ergebnis der Kombination nach Theorie III. Ordnung",
          rk is not None and str(rk.info.get("theorie", "")).startswith("III"),
          str(None if rk is None else rk.info.get("theorie")))
    if rk is not None:
        ms_, bs_ = _kragstuetze("starr")
        us_, _fs = _th3(ms_)
        wk = float(np.abs(np.asarray(rk.u).reshape(-1, 6)[b, :3]).max())
        nahe("… Kopfknoten wie Balken STARR nach Th III (zweiter Weg)", wk,
             None if us_ is None else float(np.abs(us_[bs_, :3]).max()), 1e-3)
    # die Zusammenfassung zaehlt, was gerechnet ist
    z = [x for x in an.summary().splitlines() if x.startswith("Theorie III. Ordnung")]
    check("… Zusammenfassung: Theorie III. Ordnung 1 von 1 gerechnet",
          any("1 von 1 gerechnet" in x for x in z), "; ".join(z))


# --------------------------------------------------------------------------
# (a) Kopplungen
# --------------------------------------------------------------------------
def test_kopplung_starr():
    m, b = _zwei_kragarme(float("inf"))
    c1 = 3 * E * I_K / L_K ** 3
    hand = F_K / (2 * c1)
    w1 = float(-_th1(m)[b, 2])
    nahe("Starre Kopplung Th I = F/(2 · 3 E I/L³) (Hand)", w1, hand, 1e-3)
    u3, text = _th3(m, stabteilung=False)
    print(f"   Th III: {'abgewiesen' if u3 is None else f'{-u3[b, 2] * 1e3:.4f} mm'} – {text}")
    check("Th III mit starrer Kopplung gerechnet (bis Stand 63 0,5329 statt 0,2679 mm, bis 76 abgewiesen)",
          u3 is not None and not text, text[:120])
    if u3 is not None:
        # Theorie III. Ordnung: die Verkuerzung der beiden Kragarme gibt eine
        # kleine Zugkraft (etwa 20 N), w(b) liegt 0,0000004 mm unter der
        # linearen Hand; zweiter Weg ist darum dasselbe Modell mit einem
        # gemeinsamen Knoten und Gelenk (die Kopplung haelt nur die
        # Verschiebungen) statt der Kopplung, nach Theorie III. Ordnung
        nahe("… w(b) = F/(2 · 3 E I/L³) (Hand, kleine Last)", float(-u3[b, 2]), hand, 1e-5)
        nahe("… w(b) = Theorie I. Ordnung", float(-u3[b, 2]), w1, 1e-5)
        mg, bg = _zwei_kragarme(float("inf"))
        mg.kopplungen.clear()
        mg.elements[1].nodes = [bg, mg.elements[1].nodes[1]]
        mg.elements[1].hinges = [3, 4, 5]
        ug, tg = _th3(mg, stabteilung=False)
        nahe("… w(b) = gemeinsamer Knoten mit Gelenk nach Th III (zweiter Weg, auf 0,0001 %)", float(-u3[b, 2]),
             None if ug is None else float(-ug[bg, 2]), 1e-6)
    from statik3d.theorie3 import kopplung_wirkung
    t = kopplung_wirkung(m, None)
    check("kopplung_wirkung (Merkmal Stand 64) nennt Zahl und Gruppe", "1 Kopplung" in t and "Fuge" in t, t[:160])


def test_kopplung_feder():
    """Federnde Kopplung rechnet Theorie III. Ordnung richtig: sie bleibt."""
    k = 1e6
    m, b = _zwei_kragarme(k)
    c1 = 3 * E * I_K / L_K ** 3
    hand = F_K / (c1 + 1.0 / (1.0 / c1 + 1.0 / k))
    w1 = float(-_th1(m)[b, 2])
    nahe("Federkopplung Th I = Hand (Kragarm parallel zu Feder+Kragarm in Reihe)", w1, hand, 1e-3)
    u3, text = _th3(m, stabteilung=False)
    check("Th III mit federnder Kopplung gerechnet", u3 is not None and not text, text[:120])
    if u3 is not None:
        nahe("… Th III = Hand (kleine Last)", float(-u3[b, 2]), hand, 1e-3)


# --------------------------------------------------------------------------
# Verfahrenstabelle
# --------------------------------------------------------------------------
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    check("Verfahrensstand mindestens 64", rv.VERFAHRENSSTAND >= 64, f"{rv.VERFAHRENSSTAND}")
    mk = rv.merkmal("theorie3_starrkoerper")
    check("Merkmal theorie3_starrkoerper mit Stand 64 (Fehlerkorrektur)",
          mk is not None and any(w.stand == 64 and w.art == rv.FEHLERKORREKTUR for w in mk.wechsel))
    if mk is None:
        check("… betroffen: Th III mit RBE2 ja, mit starrer Kopplung ja", False, "kein Merkmal")
        check("… nicht betroffen: Th II mit RBE2, Th III ohne Starrkörper, Federkopplung, abgeschaltet", False,
              "kein Merkmal")
        return
    m3, _b = _kragstuetze("rbe2")
    m3.load_cases["LF1"].theorie = "III"
    m2, _b = _kragstuetze("rbe2")
    m2.load_cases["LF1"].theorie = "II"
    mo, _b = _kragstuetze("starr")
    mo.load_cases["LF1"].theorie = "III"
    mk_, _b = _zwei_kragarme(float("inf"))
    mk_.load_cases["LF1"].theorie = "III"
    mf, _b = _zwei_kragarme(1e6)
    mf.load_cases["LF1"].theorie = "III"
    ms, _b = _mit_situation()
    ms.load_cases["LF1"].theorie = "II"            # nur LF2 nach III, dort Nebenarm aus
    check("… betroffen: Th III mit RBE2 ja, mit starrer Kopplung ja",
          mk.betrifft(m3) and mk.betrifft(mk_))
    check("… nicht betroffen: Th II mit RBE2, Th III ohne Starrkörper, Federkopplung, abgeschaltet",
          not mk.betrifft(m2) and not mk.betrifft(mo) and not mk.betrifft(mf) and not mk.betrifft(ms))


# --------------------------------------------------------------------------
# (b) Web: ohne gewählte Form die maßgebende
# --------------------------------------------------------------------------
def test_web_knickform():
    from statik3d.web import server as ws
    from statik3d import solver
    from tests.test_knickfaktor_positiv_k8 import _zwei_kragstuetzen, _knick
    m = _zwei_kragstuetzen()
    r = _knick(m)
    soll = solver.massgebende_knickform(r.buckling_factors)
    print(f"   Faktoren {[round(float(f), 3) for f in r.buckling_factors]}, maßgebend Index {soll}")
    check("Knickfaktoren -3 / 6 / -12, maßgebend Form 2 (Index 1)", soll == 1)
    st = ws.State(m)
    st.results = r
    p = ws.result_payload(st, "single")
    check("result_payload ohne Wahl: maßgebende Form", p.get("mode") == soll, f"mode {p.get('mode')}")
    p0 = ws.result_payload(st, "single", mode=0)
    check("result_payload mit gewählter Form 1: bleibt Form 1", p0.get("mode") == 0, f"mode {p0.get('mode')}")
    p2 = ws.result_payload(st, "single", mode=2)
    check("result_payload mit gewählter Form 3: bleibt Form 3", p2.get("mode") == 2, f"mode {p2.get('mode')}")
    # über HTTP: ohne mode-Angabe die maßgebende, mit mode=0 Form 1
    from tests.test_web import Client, KEY
    server, _thread, state = ws.start_server_thread(m, host="127.0.0.1", port=0, key=KEY)
    try:
        state.results = r
        c = Client(server.local_url.rstrip("/"))
        st_, j, _ = c.get("/api/results?which=single")
        check("HTTP ohne mode: maßgebende Form", st_ == 200 and j.get("mode") == soll, f"{st_} {j.get('mode')}")
        st_, j, _ = c.get("/api/results?which=single&mode=0")
        check("HTTP mit mode=0: Form 1", st_ == 200 and j.get("mode") == 0, f"{st_} {j.get('mode')}")
    finally:
        server.shutdown()
    js = open(os.path.join(WURZEL, "statik3d", "web", "static", "app.js"), encoding="utf-8").read()
    check("app.js: ohne Wahl keine Form (mode: null) und kein mode in der Anfrage",
          "mode: null" in js and "S.ro.mode === null ? ''" in js and "&mode=${S.ro.mode}`);" not in js)
    check("app.js: Wechsel des Ergebnisses setzt die Wahl zurück, Auswahlliste zeigt die gelieferte Form",
          "if (k === 'which') { S.ro.mode = null; }" in js and "S.ro.mode ?? R.mode" in js)


# --------------------------------------------------------------------------
# Gegenprüfung vom 15.11.2026 (ag_k8_pruef_th3), drei Befunde
#
# 1. Umgehung über Knoten ohne Element: die Sperre zählte nur Knoten mit
#    Element. Lastknoten P per RBE2 an Q, Q per federnder Kopplung am
#    Kragarmende b, weder P noch Q mit Element: Th III w(b) = 0 mm statt
#    F L³/(3 E I) = 0,5357 mm; mit starrer Kopplung P–Q statt RBE2:
#    w(P) = 100,5357 mm (Straffeder 1e4 N/m). Seither hängt ein Knoten ohne
#    Element über Starrkörper und Kopplungen an seinem Nachbarn.
# 2. Schale mit RBE2-Lastknoten nach Th III: Model.check meldete den
#    Starrkörper als FEHLER, die Rechnung richtig „nur für Stabtragwerke“
#    (CLI und Web brechen bei FEHLER ab). Seither dieselbe Bedingung wie in
#    solve_theorie3.
# 3. Daraus Status „Fehlerkorrektur“ am alten Ergebnis derselben Schale ohne
#    Grund (das alte Verfahren rechnete dort nie nach Th III).
# --------------------------------------------------------------------------
def _kette(starr, mit_situation=False):
    """Kragarm a–b 3 m (Element 0); Q deckungsgleich mit b, über eine federnde
    Kopplung (1e12 N/m) an b; Lastknoten P über RBE2 „Kette“ (starr=False,
    P 0,5 m über Q) oder über eine starre Kopplung, Gruppe „Starr“
    (starr=True, P deckungsgleich), an Q. P und Q ohne Element.
    mit_situation: zweiter Kragarm (Element 1) in LF1 abgeschaltet."""
    from statik3d.model import Model, Material, Section, Kopplung, Situation
    m = Model("U")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I_K, Iz=I_K, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_K, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    q = m.add_node(L_K, 0, 0)
    m.kopplungen.append(Kopplung(q, b, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [1e12] * 3, "Feder"))
    if starr:
        p = m.add_node(L_K, 0, 0)
        m.kopplungen.append(Kopplung(p, q, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], [float("inf")] * 3, "Starr"))
    else:
        p = m.add_node(L_K, 0, 0.5)
        m.add_starrkoerper(p, [q], "RBE2", name="Kette")
    if mit_situation:
        c = m.add_node(0, 2, 0)
        d = m.add_node(L_K, 2, 0)
        m.add_element("beam", [c, d], "ST", "Q")
        m.fix(c, "all")
        m.situationen["s"] = Situation("s", "", [1])
        m.load_cases["LF1"].situation = "s"
    m.load_node(p, Fz=-F_K)
    m.load_cases["LF1"].theorie = "III"
    return m, b, p


def _schale():
    """Platte shell4 1 × 1 m, zwei Ecken eingespannt, Lastknoten über RBE2
    „Arm“ an den beiden freien Ecken, LF1 nach Theorie III. Ordnung."""
    from statik3d.model import Model, Material, ShellProp
    m = Model("Sch")
    m.add_material(Material("S", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_shell_prop(ShellProp("t", 0.01))
    n = [m.add_node(x, y, 0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("shell4", n, "S", "t")
    m.fix(n[0], "all")
    m.fix(n[3], "all")
    p = m.add_node(1.5, 0.5, 0)
    m.add_starrkoerper(p, [n[1], n[2]], "RBE2", name="Arm")
    m.load_node(p, Fz=-100.0)
    m.load_cases["LF1"].theorie = "III"
    return m


def _solve_all_lf1(m):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    info = an.theorie3.kombinationen.get("LF1") if an.theorie3 is not None else None
    return an, an.cases.get("LF1"), (getattr(info, "fehler", "") or "")


def test_umgehung_rbe2_kette():
    hand = _hand_kragarm()
    m, b, p = _kette(starr=False)
    m.load_cases["LF1"].theorie = "I"
    u1 = _th1(m)
    m.load_cases["LF1"].theorie = "III"
    nahe("Kette RBE2 über Knoten ohne Element: Th I w(b) = F L³/(3 E I) (Hand)", float(-u1[b, 2]), hand, 1e-3)
    u3, text = _th3(m, stabteilung=False)
    print(f"   Th III: {'abgewiesen' if u3 is None else f'w(b) {-u3[b, 2] * 1e3:.4f} mm'} – {text[:100]}")
    check("Th III mit RBE2 zwischen Knoten ohne Element gerechnet (bis Stand 63 still w(b) 0 mm)",
          u3 is not None and not text, text[:120])
    if u3 is not None:
        nahe("… w(b) = Hand", float(-u3[b, 2]), hand, 1e-3)
        nahe("… w(P) = Theorie I. Ordnung", float(-u3[p, 2]), float(-u1[p, 2]), 1e-6)
    an, r, f = _solve_all_lf1(m)
    check("… solve_all: nach Theorie III. Ordnung gerechnet",
          not f and r is not None and str(r.info.get("theorie", "")).startswith("III"), f[:100])
    w = None if r is None else float(-np.asarray(r.u).reshape(-1, 6)[b, 2])
    nahe("… Ergebnis w(b) = Hand", w, hand, 1e-3)
    treffer = [z for z in m.check() if "Theorie III" in z and z.startswith("FEHLER")]
    check("… Modellprüfung: kein FEHLER", not treffer, "; ".join(treffer)[:160])
    ms, bs, _p = _kette(starr=False, mit_situation=True)
    _an, rs, fs = _solve_all_lf1(ms)
    ws = None if rs is None else float(-np.asarray(rs.u).reshape(-1, 6)[bs, 2])
    check("… auch in einer Situation mit abgeschaltetem fremdem Element gerechnet", not fs, fs[:100])
    nahe("… dort w(b) = Hand", ws, hand, 1e-3)
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("theorie3_starrkoerper")
    check("… Merkmal theorie3_starrkoerper: betroffen", mk is not None and mk.betrifft(m))


def test_umgehung_starre_kopplung():
    hand = _hand_kragarm()
    m, b, p = _kette(starr=True)
    m.load_cases["LF1"].theorie = "I"
    u1 = _th1(m)
    m.load_cases["LF1"].theorie = "III"
    nahe("Starre Kopplung P–Q, Q federnd an b: Th I w(b) = Hand", float(-u1[b, 2]), hand, 1e-3)
    nahe("… Th I w(P) = Hand (starr, Feder 1e12 N/m vernachlässigbar)", float(-u1[p, 2]), hand, 1e-3)
    u3, text = _th3(m, stabteilung=False)
    print(f"   Th III: {'abgewiesen' if u3 is None else f'w(P) {-u3[p, 2] * 1e3:.4f} mm'} – {text[:100]}")
    check("Th III mit starrer Kopplung zwischen Knoten ohne Element gerechnet (bis Stand 63 w(P) 100,5357 mm)",
          u3 is not None and not text, text[:120])
    if u3 is not None:
        nahe("… w(P) = Hand", float(-u3[p, 2]), hand, 1e-3)
        nahe("… w(P) = Theorie I. Ordnung", float(-u3[p, 2]), float(-u1[p, 2]), 1e-6)
    an, r, f = _solve_all_lf1(m)
    check("… solve_all: nach Theorie III. Ordnung gerechnet",
          not f and r is not None and str(r.info.get("theorie", "")).startswith("III"), f[:100])
    wp = None if r is None else float(-np.asarray(r.u).reshape(-1, 6)[p, 2])
    nahe("… Ergebnis w(P) = Hand", wp, hand, 1e-3)
    treffer = [z for z in m.check() if "Theorie III" in z and z.startswith("FEHLER")]
    check("… Modellprüfung: kein FEHLER", not treffer, "; ".join(treffer)[:160])
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("theorie3_starrkoerper")
    check("… Merkmal theorie3_starrkoerper: betroffen", mk is not None and mk.betrifft(m))


def test_schale_modellpruefung():
    from statik3d.theorie3 import kopplung_sperre_modell
    m = _schale()
    fehler = [z for z in m.check() if z.startswith("FEHLER")]
    check("Schale mit RBE2 nach Th III: Modellprüfung ohne FEHLER zum Starrkörper",
          not any(TEXT_SK in z for z in fehler), "; ".join(fehler)[:160])
    check("… kopplung_sperre_modell leer (nur Stabtragwerke zählen)", kopplung_sperre_modell(m) == {},
          str(list(kopplung_sperre_modell(m)))[:120])
    an, r, f = _solve_all_lf1(m)
    check("… Rechnung meldet „nur für Stabtragwerke“, LF1 linear",
          "nur für Stabtragwerke" in f and TEXT_SK not in f and r is not None
          and r.info.get("theorie") == "I", f[:100])


def test_schale_status():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("theorie3_starrkoerper")
    m = _schale()
    an, _r, _f = _solve_all_lf1(m)
    alt = dict(rv.aktuelle_merkmale(m))
    alt["theorie3_starrkoerper"] = "alt"
    st = rv.betroffen(m, alt, an)
    print(f"   Schale, Ergebnis vor Stand 64: {st[:120]!r}")
    check("Schale: altes Ergebnis nicht „betroffen“ durch Starrkörper nach Th III",
          mk is not None and not mk.betrifft(m) and mk.titel not in st, st[:160])
    # Gegenprobe: Stabmodell mit RBE3-Lastknoten ist wirklich betroffen
    m2, _b = _kragarm_rbe3()
    m2.load_cases["LF1"].theorie = "III"
    an2, _r2, _f2 = _solve_all_lf1(m2)
    alt2 = dict(rv.aktuelle_merkmale(m2))
    alt2["theorie3_starrkoerper"] = "alt"
    st2 = rv.betroffen(m2, alt2, an2)
    check("… Gegenprobe Stab mit RBE3-Lastknoten: betroffen", mk is not None and mk.titel in st2, st2[:160])


def test_kette_am_lager():
    """Restluecke der zweiten Gegenpruefung (R1): P (Last) per RBE2 an den
    eingespannten Knoten Q, beide ohne Element, daneben ein belasteter
    Kragarm. Th III rechnete ohne Meldung und verlor die Last an P
    (Summe Rz 1000 statt 2000 N)."""
    from statik3d.model import Model, Material, Section
    m = Model("L")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I_K, Iz=I_K, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L_K, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    q = m.add_node(0, 2, 0)
    p = m.add_node(0.5, 2, 0)
    m.fix(q, "all")
    m.add_starrkoerper(q, [p], "RBE2", name="Lagerarm")
    m.load_node(b, Fz=-F_K)
    m.load_node(p, Fz=-F_K)
    m.load_cases["LF1"].theorie = "III"
    from statik3d.theorie3 import solve_theorie3
    try:
        r3, i3 = _still(solve_theorie3, m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
        text = i3.fehler or ""
    except ValueError as ex:
        r3, text = None, str(ex)
    check("Th III mit RBE2 nur zwischen Lagerknoten und Lastknoten (ohne Element) gerechnet (seit Stand 77)",
          r3 is not None and not text, text[:100])
    if r3 is not None:
        R3 = np.asarray(r3.reactions).reshape(-1, 6)
        u3 = np.asarray(r3.u).reshape(-1, 6)
        nahe("… Summe Rz = 2 000 N (bis Stand 63 still 1 000 N)", float(R3[:, 2].sum()), 2 * F_K, 1e-9)
        nahe("… Rz am Lagerknoten Q = 1 000 N", float(R3[q, 2]), F_K, 1e-9)
        check("… w(P) = 0 (am eingespannten Knoten)", abs(u3[p, 2]) < 1e-12, f"{u3[p, 2]:.3e} m")
        nahe("… w(b) = Hand", float(-u3[b, 2]), _hand_kragarm(), 1e-3)
    treffer = [z for z in m.check() if "Theorie III" in z and z.startswith("FEHLER")]
    check("… Modellprüfung: kein FEHLER", not treffer, "; ".join(treffer)[:160])
    # Gegenprobe: dieselbe Kette ohne Th III bleibt ohne Meldung
    m.load_cases["LF1"].theorie = "I"
    check("… Gegenprobe Theorie I. Ordnung: keine Meldung", not [z for z in m.check() if TEXT_SK in z])


def main():
    for t in (test_rbe2_arm, test_rbe3_lastknoten, test_situation, test_kombination, test_kopplung_starr,
              test_kopplung_feder, test_verfahrenstabelle, test_web_knickform,
              test_umgehung_rbe2_kette, test_umgehung_starre_kopplung, test_schale_modellpruefung,
              test_schale_status, test_kette_am_lager):
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
