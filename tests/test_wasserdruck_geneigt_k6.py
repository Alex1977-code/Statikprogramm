"""
Wasserdruck an geneigten Volumenraendern, Breite im Protokoll und globale
Richtung an geneigten Flaechen (Befunde A'8 und A'11 der Befundliste vom
14.11.2026, zweite Runde; Entscheidung des Anwenders vom 14.11.2026; Stand 55).

A'8: Der stroemungsnumerische Wasserdruck rechnete geneigte Schalen seit
Stand 49 analytisch, geneigte Volumenraender aber weiter im Gitter - dort
fehlten 6 bis 9 % der Last (45°, Gitter 40: −7,1 %), und das Protokoll nannte
„Resultierende 0,0 kN“. Seitdem rechnen auch Volumenraender ab
NEIGUNG_NUMERISCH analytisch, mit Satz im Protokoll; die Resultierende im
Protokoll ist die Summe der Elementlasten.

A'11: Die Breite b (F = F_je_m · b) war die groessere Ausdehnung im Grundriss
(45°-Wand 2 m breit: b = 3 m, F 91,97 statt 61,31 kN) und im gemischten
Schnitt die Breite aller Flaechen, obwohl das Druckfeld nur die lotrechten
traegt. Seitdem quer zur Stroemungsrichtung und nur ueber die Flaechen im
Gitter.

Entscheidung: Wasserdruck mit globaler Richtung wirkt auf die Projektion der
Flaeche senkrecht zu dieser Richtung (p A |n·d|), wie im Stahlwasserbau:
45°-Wand 2 m breit, 2,5 m Wasser, Richtung waagerecht → ½γh²b = 61,31 kN
statt 86,64 kN. Die Beispiele Hubtor, Stemmtor und Fischbauchklappe (Richtung
senkrecht zur Haut) bleiben unveraendert und stimmen mit der Handrechnung.

Zwei Wege je Zahl: Handrechnung (½γh²b, geschlossene Integrale) und das
Programm (Lastvektor bzw. Kontrollsumme der Elementlasten).

Aufruf:  python -m tests.test_wasserdruck_geneigt_k6
"""
from __future__ import annotations

import contextlib
import copy
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import mesher, solver                             # noqa: E402
from statik3d import wasserdruck as wdm                         # noqa: E402
from statik3d.model import Material, Model, ShellProp           # noqa: E402

RESULTS = []
RHO, G = 1000.0, 9.81
H_OW, B = 2.5, 2.0
FH = 0.5 * RHO * G * H_OW ** 2 * B          # 61 312,5 N waagerecht


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<100} {detail}")
    return bool(ok)


def fmt(F):
    return "(" + "; ".join(f"{x / 1e3:.3f}" for x in F) + ") kN"


@contextlib.contextmanager
def _still():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _vernetzen(m):
    with _still():
        mesher.modell_vernetzen(m, log=[], workers=1)


def summe(m, lf):
    return np.asarray(solver.case_loads(m, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)


def _schalenmodell():
    m = Model("W")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.netz.ziellaenge = 0.25
    return m


def flaeche(m, name, E, teilung=(8, 12)):
    b0 = m.nn
    m.add_nodes(np.asarray(E, float))
    for i in range(4):
        m.add_line(f"{name}{i}", [b0 + i, b0 + (i + 1) % 4])
    m.add_flaeche(name, [f"{name}{i}" for i in range(4)], material="S235", dicke="t10").teilung = list(teilung)


def ecken_wand(beta, x0=0.0, drehung=0.0):
    """Wand B breit (x), Fuss z = 0, Kopf z = 3 m, gegen die Lotrechte um beta
    nach +y geneigt; um ``drehung`` [°] um z gedreht."""
    t = 3.0 * math.tan(math.radians(beta))
    E = [[x0, 0, 0], [x0 + B, 0, 0], [x0 + B, t, 3.0], [x0, t, 3.0]]
    c, s = math.cos(math.radians(drehung)), math.sin(math.radians(drehung))
    return [[x * c - y * s, x * s + y * c, z] for x, y, z in E]


def volumen_geneigt(beta, T=0.3, L=2.0, rueck=False):
    """Geneigte Platte als Volumen (Beleg s5 des Pruefagenten 2-9): Vorderflaeche
    M0 (Oberwasser, y klein) von (0,0,0)-(L,0,0) bis Kopf z = 3 m, gegen die
    Lotrechte um beta nach +y geneigt; Dicke T in +y. ``rueck``: die Linien
    von M0 andersherum (Flaechennormale zeigt in den Koerper)."""
    m = Model("VG")
    m.add_material(Material.steel("S235"))
    t = 3.0 * math.tan(math.radians(beta))
    m.add_nodes(np.array([[0, 0, 0], [L, 0, 0], [L, T, 0], [0, T, 0],
                          [0, t, 3], [L, t, 3], [L, t + T, 3], [0, t + T, 3]], float))
    n = {"i": 0}

    def linie(a, b):
        n["i"] += 1
        m.add_line(f"L{n['i']}", [a, b])
        return f"L{n['i']}"
    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[1], material="S235")
    for i in range(4):
        rand = [R[0][i], V[(i + 1) % 4], R[1][i], V[i]]
        m.add_flaeche(f"M{i}", rand[::-1] if (rueck and i == 0) else rand, material="S235")
    k = m.add_koerper("K", ["Boden", "Dach", "M0", "M1", "M2", "M3"], material="S235")
    k.teilung = [int(L * 10), 3, 30]
    m.netz.ziellaenge = 0.1
    _vernetzen(m)
    return m


def erzeugen(m, flaechen, **kw):
    wdm._FELD_CACHE.clear()
    wd = wdm.Wasserdruck("W1", flaechen=list(flaechen), absenkung=False, h_ow=H_OW, **kw)
    with _still():
        k = wdm.lasten_erzeugen(m, wd)
    return wd, k, summe(m, wd.lastfall)


def _resultierende_satz(wd, k):
    return [z for z in wdm.erlaeuterung(wd, k) if z.startswith("Resultierende")]


# ---------------------------------------------------------------------------
# A'8: geneigter Volumenrand
# ---------------------------------------------------------------------------
def test_volumenrand():
    for beta, rueck in ((5.0, False), (30.0, False), (45.0, False), (45.0, True)):
        m = volumen_geneigt(beta, rueck=rueck)
        n = wdm.flaechennormale(m, "M0")
        soll = np.array([0.0, FH, -FH * math.tan(math.radians(beta))])
        wd, k, F = erzeugen(m, ["M0"], verfahren="numerisch", seite=1 if n[1] < 0 else -1)
        K = np.asarray(k["kontrolle"]["F"], float)
        ana = k.get("analytisch_flaechen") or {}
        ohne_feld = not any(gl.verlauf.get("feld") for lc in m.load_cases.values() for gl in lc.geometrielasten)
        check(f"A'8 Volumenrand {beta:g}°{' (Rand andersherum)' if rueck else ''}, numerisch gewählt: "
              f"ΣF = Hand (0; 61,313; {-FH * math.tan(math.radians(beta)) / 1e3:.3f}) kN, analytisch, ohne Druckfeld",
              np.allclose(F, soll, rtol=5e-3, atol=5e-3 * np.linalg.norm(soll)) and np.allclose(K, F, atol=1.0)
              and "M0" in ana and ohne_feld,
              f"Lastvektor {fmt(F)}, Kontrollsumme {fmt(K)}, analytisch {list(ana)}")
        satz = [z for z in wdm.erlaeuterung(wd, k) if "Volumenrand" in z and "M0" in z]
        res = _resultierende_satz(wd, k)
        check(f"A'8 Volumenrand {beta:g}°: Satz zum Volumenrand im Protokoll, Resultierende aus der Summe "
              f"der Elementlasten {np.linalg.norm(soll) / 1e3:.1f} kN",
              len(satz) == 1 and len(res) == 1 and "Summe der Elementlasten" in res[0]
              and f"{np.linalg.norm(F) / 1e3:.1f} kN" in res[0],
              (res[0][:150] if res else "kein Satz") + " | " + (satz[0][:80] if satz else "kein Volumensatz"))
    # lotrecht bleibt numerisch
    m = volumen_geneigt(0.0)
    n = wdm.flaechennormale(m, "M0")
    wd, k, F = erzeugen(m, ["M0"], verfahren="numerisch", seite=1 if n[1] < 0 else -1)
    check("A'8 lotrechter Volumenrand bleibt strömungsnumerisch (ΣF_y = Hand 61,313 kN auf 1 %)",
          k.get("verfahren") == "numerisch" and not k.get("analytisch_flaechen")
          and abs(F[1] - FH) < 0.01 * FH, f"{k.get('verfahren')}, {fmt(F)}")


# ---------------------------------------------------------------------------
# A'11: Breite quer zur Stroemung, nur ueber die Flaechen im Gitter
# ---------------------------------------------------------------------------
def test_breite():
    for verf in ("analytisch", "numerisch"):
        m = _schalenmodell()
        flaeche(m, "W", ecken_wand(45.0))
        _vernetzen(m)
        n = wdm.flaechennormale(m, "W")
        wd, k, F = erzeugen(m, ["W"], verfahren=verf, seite=1 if n[1] < 0 else -1)
        check(f"A'11 Wand 45°, {verf} gewählt: Breite 2,000 m, F = ½γh²b = 61,313 kN = ΣF_y der Elementlasten",
              abs(k["breite"] - 2.0) < 1e-9 and abs(k["F"] - FH) < 1e-3 * FH and abs(F[1] - FH) < 5e-3 * FH,
              f"Breite {k['breite']:.3f} m, F {k['F'] / 1e3:.3f} kN, ΣF {fmt(F)}")
    # im Grundriss um 30° gedreht, lotrecht
    m = _schalenmodell()
    flaeche(m, "W", ecken_wand(0.0, drehung=30.0))
    _vernetzen(m)
    n = wdm.flaechennormale(m, "W")
    wd, k, F = erzeugen(m, ["W"], verfahren="analytisch", seite=1)
    check("A'11 lotrechte Wand im Grundriss um 30° gedreht: Breite 2,000 m (quer zur Strömung), "
          "F = 61,313 kN = |ΣF|",
          abs(k["breite"] - 2.0) < 1e-9 and abs(k["F"] - FH) < 1e-3 * FH and abs(np.linalg.norm(F) - FH) < 5e-3 * FH,
          f"Breite {k['breite']:.3f} m, F {k['F'] / 1e3:.3f} kN, ΣF {fmt(F)}")
    # gemischter Schnitt: lotrecht V im Gitter, 45° G analytisch
    m = _schalenmodell()
    flaeche(m, "V", ecken_wand(0.0))
    flaeche(m, "G", ecken_wand(45.0, x0=3.0))
    _vernetzen(m)
    nV = wdm.flaechennormale(m, "V")
    wd, k, F = erzeugen(m, ["V", "G"], verfahren="numerisch", seite=1 if nV[1] < 0 else -1)
    soll = np.array([0.0, 2 * FH, -FH])
    res = _resultierende_satz(wd, k)
    check("A'11 gemischter Schnitt: Breite 2,000 m (nur V im Gitter), F des Druckfelds 61,3 kN, ΣF = Hand "
          "(0; 122,625; −61,313) kN",
          abs(k["breite"] - 2.0) < 1e-9 and abs(k["F"] - FH) < 5e-3 * FH
          and np.allclose(F, soll, rtol=5e-3, atol=5e-3 * np.linalg.norm(soll)),
          f"Breite {k['breite']:.3f} m, F {k['F'] / 1e3:.3f} kN, ΣF {fmt(F)}")
    check("A'11 gemischter Schnitt: Resultierende im Protokoll = Summe der Elementlasten",
          len(res) == 1 and "Summe der Elementlasten" in res[0] and f"{np.linalg.norm(F) / 1e3:.1f} kN" in res[0],
          res[0][:160] if res else "kein Satz")


# ---------------------------------------------------------------------------
# Entscheidung 14.11.2026: globale Richtung → Projektion
# ---------------------------------------------------------------------------
def test_projektion():
    for beta in (0.0, 5.0, 45.0):
        for verf in ("analytisch", "numerisch"):
            m = _schalenmodell()
            flaeche(m, "W", ecken_wand(beta))
            _vernetzen(m)
            n = wdm.flaechennormale(m, "W")
            wd, k, F = erzeugen(m, ["W"], verfahren=verf, richtung=[0.0, 1.0, 0.0], seite=1 if n[1] < 0 else -1)
            # zweiter Weg: Projektion der Elementflaechen auf die x-z-Ebene mal Druck in der Elementmitte
            proj = 0.0
            for fl in m.load_cases[wd.lastfall].face_loads:
                el = m.elements[int(fl.elem)]
                X = m.nodes[[int(i) for i in el.nodes[:4]]]
                v = 0.5 * np.cross(X[2] - X[0], X[3] - X[1])
                z = float(X[:, 2].mean())
                proj += RHO * G * max(H_OW - z, 0.0) * abs(float(v[1]))
            satz = [z for z in wdm.erlaeuterung(wd, k) if "Projektion" in z]
            check(f"Richtung global (0; 1; 0), Wand {beta:g}°, {verf}: ΣF = (0; ½γh²b = 61,313; 0) kN "
                  "= Druck mal Projektion (zweiter Weg), Satz im Protokoll",
                  np.allclose(F, [0.0, FH, 0.0], atol=5e-3 * FH) and abs(proj - FH) < 5e-3 * FH and len(satz) == 1,
                  f"ΣF {fmt(F)}, Projektion {proj / 1e3:.3f} kN, vorher 45°: 86,638 kN")


def test_beispiele():
    """Die Beispiele mit globaler Richtung: die Richtung steht senkrecht zur
    Haut, Projektion = wahre Flaeche - unveraendert, gleich der Handrechnung."""
    from statik3d.beispiele.eingebaut import BEISPIELE
    th = math.atan(1 / 3)
    en_st = np.array([math.sin(th), math.cos(th), 0.0])
    a = math.radians(70.0)
    gw = RHO * G
    hand = {
        "hubtor": {"LF2": 0.5 * gw * (25.0 - 1.0) * 12.0 * np.array([0.0, 1.0, 0.0])},
        "stemmtor": {"LF2": 0.5 * gw * (49.0 - 6.25) * 7.0 * en_st, "LF3": 0.5 * gw * 49.0 * 7.0 * en_st},
        "fischbauchklappe": {"LF2": 0.5 * gw * (9.0 - 0.64) * 15.0 / math.sin(a)
                             * np.array([0.0, math.sin(a), -math.cos(a)])},
    }
    for b in BEISPIELE:
        if b.schluessel not in hand:
            continue
        with _still():
            m = b.bauen()
            if not m.elements:
                mesher.modell_vernetzen(m, log=[], workers=1)
            m.lasten_verteilen()
        for lf, soll in hand[b.schluessel].items():
            F = summe(m, lf)
            check(f"Beispiel {b.titel} {lf}: Lastvektor = Hand {fmt(soll)} (0,1 %)",
                  np.linalg.norm(F - soll) < 1e-3 * np.linalg.norm(soll), f"{fmt(F)}")


# ---------------------------------------------------------------------------
# Verfahrenstabelle Stand 55
# ---------------------------------------------------------------------------
def test_merkmale():
    from statik3d import rechenverfahren as rv
    for name, korrektur in (("wasserdruck_volumen_geneigt", True), ("wasserdruck_richtung_projektion", False)):
        mk = rv.merkmal(name)
        check(f"Merkmal {name}: Stand 55, Fehlerkorrektur{' am Modell' if korrektur else ''}, "
              "VERFAHRENSSTAND >= 55",
              mk is not None and any(w.stand == 55 and w.art == rv.FEHLERKORREKTUR for w in mk.wechsel)
              and bool(getattr(mk, "import_korrektur", False)) == korrektur and rv.VERFAHRENSSTAND >= 55,
              f"Stand {rv.VERFAHRENSSTAND}")
    mk = rv.merkmal("wasserdruck_volumen_geneigt")
    if mk is not None:
        m0 = volumen_geneigt(0.0)
        wd0, _k, _F = erzeugen(m0, ["M0"], verfahren="numerisch", seite=1)
        m45 = volumen_geneigt(45.0)
        wd45, _k, _F = erzeugen(m45, ["M0"], verfahren="numerisch", seite=1)
        alt = copy.deepcopy(m45)
        lc = alt.load_cases[wd45.lastfall]
        lc.geometrielasten = []
        alt.add_geometrielast("M0", 0.0, art="flaeche", richtung=None, case=wd45.lastfall,
                              verlauf=copy.deepcopy(m0.load_cases[wd0.lastfall].geometrielasten[0].verlauf))
        alt.lasten_verteilen()
        check("Merkmal wasserdruck_volumen_geneigt: Druckfeld am geneigten Volumenrand betroffen, neu erzeugt "
              "und lotrecht nicht", mk.betrifft(alt) and not mk.betrifft(m45) and not mk.betrifft(m0))
        h = wdm.wasserdruck_hinweis(alt)
        check("Ladehinweis zum alten Druckfeld am Volumenrand nennt Wasserdruck und Lastfall, rät zum Neuerzeugen",
              len(h) == 1 and "W1" in h[0] and wd45.lastfall in h[0] and "neu erzeugen" in h[0]
              and "Volumen" in h[0] and not wdm.wasserdruck_hinweis(m45), str(h)[:200])
    mk = rv.merkmal("wasserdruck_richtung_projektion")
    if mk is not None:
        m45 = _schalenmodell()
        flaeche(m45, "W", ecken_wand(45.0))
        _vernetzen(m45)
        erzeugen(m45, ["W"], verfahren="analytisch", richtung=[0.0, 1.0, 0.0])
        m0 = _schalenmodell()
        flaeche(m0, "W", ecken_wand(0.0))
        _vernetzen(m0)
        erzeugen(m0, ["W"], verfahren="analytisch", richtung=[0.0, 1.0, 0.0])
        m45o = _schalenmodell()
        flaeche(m45o, "W", ecken_wand(45.0))
        _vernetzen(m45o)
        erzeugen(m45o, ["W"], verfahren="analytisch")
        check("Merkmal wasserdruck_richtung_projektion: 45°-Wand mit Richtung betroffen; lotrecht mit Richtung "
              "und 45° ohne Richtung nicht",
              mk.betrifft(m45) and not mk.betrifft(m0) and not mk.betrifft(m45o))


def main():
    for t in (test_volumenrand, test_breite, test_projektion, test_beispiele, test_merkmale):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                       # noqa: BLE001 - vor der Behebung fehlen Teile
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
