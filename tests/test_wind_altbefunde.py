"""
Drei aeltere Befunde der Pruefagenten zu Wind und projizierter Last (Kur vom 12.11.2026).

Befund 8  Freistehende Wand und Anzeigetafel aus Schalen: die Windkraft wirkte
          in Richtung der Elementnormalen, also je nach Umlauf der Randlinien
          mit oder gegen den Wind (Wand 10 x 3 m: ΣF_x +26,01 bzw. −26,01 kN).
          c_p,net (Tab. 7.9) und c_f der Tafel (7.4.3) gelten in Windrichtung.
Befund 9  Projizierte Last mit linearem Verlauf: der Windschatten richtete sich
          nach gl.p (Wert bei A), nicht nach dem wirkenden Wert. A = 0, B = −5
          kN/m² global Z traf die Unterseite des Blocks statt das Dach.
Befund 13 wind.gebaeude() nahm freie Waende, Schilder und Staebe in h, b, d
          des Gebaeudes auf; Quader 10 x 10 x 10 m mit einer freien Wand 30 m
          daneben: b 45 statt 10 m, d 30 statt 10 m.

Zweiter Weg der Zahlen: Handrechnung q_p · c · A mit q_p aus den Formeln der
Norm (4.8, 4.3, 4.4, 4.7), hier unabhaengig von wind.q_p ausgeschrieben.

Aufruf:  python -m tests.test_wind_altbefunde
"""
import contextlib
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import mesher, solver, wind as wm                         # noqa: E402
from statik3d.model import LoadCase, Material, Model, ShellProp          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<78} {detail}")
    return bool(ok)


def qp_hand(z, v_b0=25.0, z0=0.05, zmin=2.0):
    """q_p(z) Gelaendekategorie II von Hand: k_r = 0,19 (z0 = z0,II), c_r = k_r ln(z/z0),
    v_m = c_r v_b, I_v = 1/ln(z/z0), q_p = (1 + 7 I_v) ½ ρ v_m², unter z_min mit z_min."""
    z = max(z, zmin)
    ln = math.log(z / z0)
    v_m = 0.19 * ln * v_b0
    return (1.0 + 7.0 / ln) * 0.5 * 1.25 * v_m ** 2


def neues_modell():
    m = Model("Wind")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    return m


def platte(m, name, ecken):
    base = m.nn
    m.add_nodes(np.asarray(ecken, float))
    lin = []
    for i in range(4):
        nm = f"{name}_L{i}"
        m.add_line(nm, [base + i, base + (i + 1) % 4])
        lin.append(nm)
    m.add_flaeche(name, lin, material="S235", dicke="t10")


def vernetzen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)


def summe(m, lf):
    return np.asarray(solver.case_loads(m, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)


def kraft_der_flaechen(m, lastfall, flaechen):
    """Summe ueber den Lastvektor, nur die Elementlasten auf ``flaechen``."""
    from statik3d.assemble import load_vector
    el = set()
    for n in flaechen:
        el |= {int(e) for e in m.flaechen[n].elemente}
    lc = LoadCase("nur")
    lc.face_loads = [f for f in m.load_cases[lastfall].face_loads if int(f.elem) in el]
    return np.asarray(load_vector(m, lc), float)[:6 * m.nn].reshape(-1, 6)[:, :3].sum(axis=0)


# ---------------------------------------------------------------------------
# Befund 8
# ---------------------------------------------------------------------------
def _wand(ecken, rueck, rolle, richtung, z_boden=None):
    m = neues_modell()
    platte(m, "FW", ecken[::-1] if rueck else ecken)
    vernetzen(m)
    kw = {"freie_waende": ["FW"]} if rolle == "freie_wand" else {"schilder": ["FW"]}
    w = wm.Wind("W1", richtung=list(richtung), z_boden=z_boden, **kw)
    k = wm.lasten_erzeugen(m, w)
    return m, w, summe(m, w.lastfall), np.asarray(k["kontrolle"]["F"], float)


def test_befund8():
    # Wand 1 x 2 m in der Ebene x = 0: l/2 = 0,5 < 0,3 h = 0,6 -> ganz Zone A,
    # z <= z_min -> q_p konstant: F = 2,3 q_p(2) 2 m² in Windrichtung
    wand = [[0, 0, 0], [0, 1, 0], [0, 1, 2], [0, 0, 2]]
    soll_w = 2.3 * qp_hand(2.0) * 2.0
    # Tafel 4 x 1,5 m, Unterkante 0,5 m ueber Gelaende: F = 1,8 q_p(2) 6 m²
    tafel = [[0, 0, 0.5], [0, 4, 0.5], [0, 4, 2.0], [0, 0, 2.0]]
    soll_t = 1.8 * qp_hand(2.0) * 6.0
    for rolle, ecken, soll, zb in (("freie_wand", wand, soll_w, None), ("schild", tafel, soll_t, 0.0)):
        for richtung in ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)):
            for rueck in (False, True):
                m, w, F, K = _wand(ecken, rueck, rolle, richtung, zb)
                Fx = float(F[0]) * richtung[0]
                check(f"B8 {rolle}, Wind {richtung[0]:+.0f}x, Umlauf {'rück' if rueck else 'vor'}: "
                      f"ΣF in Windrichtung = Hand",
                      abs(Fx - soll) / soll < 1e-6 and abs(F[1]) + abs(F[2]) < 1e-6 * soll,
                      f"F_x {F[0] / 1000:.3f} kN, Hand {soll * richtung[0] / 1000:.3f} kN")
                check(f"B8 {rolle}, Wind {richtung[0]:+.0f}x, Umlauf {'rück' if rueck else 'vor'}: "
                      f"Kontrollsumme = Lastvektor",
                      np.allclose(K, F, atol=1e-6 * soll), f"{K[0] / 1000:.3f} kN")
    # grosse Wand 10 x 3 m (Zonen A und B, q_p ueber die Hoehe): beide Umlaeufe gleich, in +x
    gross = [[0, 0, 0], [0, 10, 0], [0, 10, 3], [0, 0, 3]]
    _m, _w, F1, _k = _wand(gross, False, "freie_wand", (1.0, 0.0, 0.0))
    _m, _w, F2, _k = _wand(gross, True, "freie_wand", (1.0, 0.0, 0.0))
    check("B8 Wand 10 x 3 m: beide Umlaeufe gleich, in Windrichtung",
          F1[0] > 0 and np.allclose(F1, F2, rtol=1e-9, atol=1e-6), f"{F1[0] / 1000:.3f} / {F2[0] / 1000:.3f} kN")
    # schraeg angestroemt (Wind unter 30° zur Normalen): Kraft senkrecht zur Wand,
    # Komponente in Windrichtung positiv, gleich fuer beide Umlaeufe
    d = (math.cos(math.radians(30)), math.sin(math.radians(30)), 0.0)
    _m, _w, F1, _k = _wand(wand, False, "freie_wand", d)
    _m, _w, F2, _k = _wand(wand, True, "freie_wand", d)
    check("B8 Wand schräg angeströmt: Kraft senkrecht zur Wand, mit dem Wind, umlaufunabhängig",
          F1[0] > 0 and abs(F1[1]) < 1e-9 * F1[0] and np.allclose(F1, F2, rtol=1e-9),
          f"{F1[0] / 1000:.3f} / {F2[0] / 1000:.3f} kN")


def test_befund8_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_netto_richtung")
    check("B8 Merkmal wind_netto_richtung vorhanden (Stand 33, Fehlerkorrektur)",
          mk is not None and mk.wechsel[-1].stand == 33 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR)
    if mk is None:
        return
    wand = [[0, 0, 0], [0, 1, 0], [0, 1, 2], [0, 0, 2]]
    m1, *_r = _wand(wand, False, "freie_wand", (1.0, 0.0, 0.0))
    m2, *_r = _wand(wand, True, "freie_wand", (1.0, 0.0, 0.0))
    check("B8 Merkmal: nur die Wand mit Elementnormale gegen den Wind ist betroffen",
          not mk.betrifft(m1) and mk.betrifft(m2))


# ---------------------------------------------------------------------------
# Befund 9
# ---------------------------------------------------------------------------
def _block(pa, pb):
    m = Model("Block")
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, .5, 0], [0, .5, 0],
                  [0, 0, .2], [1, 0, .2], [1, .5, .2], [0, .5, .2]], float)
    m.add_nodes(P)
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
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
    k = m.add_koerper("K", ["Boden", "Dach", "M0", "M1", "M2", "M3"], material="S235")
    k.teilung = [4, 2, 2]
    m.add_load_case("LF1", "Q")
    m.add_geometrielast("K", pa, art="koerper", case="LF1", projiziert=True, bezug="global", achse="z",
                        verlauf={"art": "linear", "punkte": [[0, 0, 0, pa], [1, 0, 0, pb]]})
    vernetzen(m)
    m.lasten_verteilen()
    F = {}
    for f in m.case("LF1").face_loads:
        z = round(float(m._seitenmitte(f.elem, f.face)[2]), 3)
        lc = LoadCase("x")
        lc.face_loads = [f]
        from statik3d.assemble import load_vector
        F[z] = F.get(z, 0.0) + float(np.asarray(load_vector(m, lc), float)[:6 * m.nn].reshape(-1, 6)[:, 2].sum())
    return m, F


def test_befund9():
    # Hand: Grundriss 1 x 0,5 m, p(x) linear; Kraft = ∫ p(x) 0,5 dx
    for pa, pb, soll in ((-5000.0, -5000.0, {0.2: -2500.0}),
                         (0.0, -5000.0, {0.2: -1250.0}),
                         (-5000.0, 0.0, {0.2: -1250.0}),
                         (5000.0, -5000.0, {0.0: 625.0, 0.2: -625.0}),
                         (0.0, 5000.0, {0.0: 1250.0})):
        _m, F = _block(pa, pb)
        ok = set(F) == set(soll) and all(abs(F[z] - soll[z]) < 1e-6 * 2500 for z in soll)
        check(f"B9 linear A {pa / 1000:+.0f} B {pb / 1000:+.0f} kN/m²: Seiten und Kräfte",
              ok, "ist " + ", ".join(f"z {z}: {v:.1f} N" for z, v in sorted(F.items()))
              + " | Hand " + ", ".join(f"z {z}: {v:.1f} N" for z, v in sorted(soll.items())))


def test_befund9_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("projiziert_verlauf_vorzeichen")
    check("B9 Merkmal projiziert_verlauf_vorzeichen vorhanden (Stand 33, Fehlerkorrektur)",
          mk is not None and mk.wechsel[-1].stand == 33 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR)
    if mk is None:
        return
    m1, _f = _block(-5000.0, -5000.0)
    m2, _f = _block(0.0, -5000.0)
    m3, _f = _block(5000.0, -5000.0)
    check("B9 Merkmal: gleiches Vorzeichen nicht betroffen, Vorzeichenwechsel zu gl.p betroffen",
          not mk.betrifft(m1) and mk.betrifft(m2) and mk.betrifft(m3))


# ---------------------------------------------------------------------------
# Befund 13
# ---------------------------------------------------------------------------
QUADER = {"Luv": [[0, 0, 0], [0, 0, 10], [0, 10, 10], [0, 10, 0]],
          "Lee": [[10, 0, 0], [10, 10, 0], [10, 10, 10], [10, 0, 10]],
          "S1": [[0, 0, 0], [10, 0, 0], [10, 0, 10], [0, 0, 10]],
          "S2": [[0, 10, 0], [0, 10, 10], [10, 10, 10], [10, 10, 0]],
          "Dach": [[0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]]}
FREI = [[-20, 15, 0], [-20, 45, 0], [-20, 45, 3], [-20, 15, 3]]


def _quader(bau=True, frei=False, tafel=False):
    m = neues_modell()
    if bau:
        for nm, E in QUADER.items():
            platte(m, nm, E)
    if frei:
        platte(m, "FW", FREI)
    if tafel:
        platte(m, "T", [[30, -10, 1.0], [30, -6, 1.0], [30, -6, 2.0], [30, -10, 2.0]])
    vernetzen(m)
    w = wm.Wind("W1", flaechen=list(QUADER) if bau else [], freie_waende=["FW"] if frei else [],
                schilder=["T"] if tafel else [], richtung=[1.0, 0.0, 0.0])
    return m, w


def test_befund13():
    m0, w0 = _quader()
    g0 = wm.gebaeude(w0, m0)
    k0 = wm.lasten_erzeugen(m0, w0)
    F0 = kraft_der_flaechen(m0, w0.lastfall, list(QUADER))
    m1, w1 = _quader(frei=True, tafel=True)
    g1 = wm.gebaeude(w1, m1)
    k1 = wm.lasten_erzeugen(m1, w1)
    F1 = kraft_der_flaechen(m1, w1.lastfall, list(QUADER))
    check("B13 h/b/d ohne freie Wand 10/10/10 m", np.allclose([g0["h"], g0["b"], g0["d"]], 10.0),
          f"{g0['h']:.2f}/{g0['b']:.2f}/{g0['d']:.2f}")
    check("B13 h/b/d mit freier Wand und Tafel unverändert 10/10/10 m, Luvkante 0, quer 0..10",
          np.allclose([g1["h"], g1["b"], g1["d"]], 10.0) and abs(g1["x_luv"]) < 1e-9
          and abs(g1["t_min"]) < 1e-9 and abs(g1["t_max"] - 10.0) < 1e-9,
          f"{g1['h']:.2f}/{g1['b']:.2f}/{g1['d']:.2f}, x_luv {g1['x_luv']:.2f}, t {g1['t_min']:.2f}..{g1['t_max']:.2f}")
    check("B13 Kennwerte e und h/d aus dem Baukörper (e = 10, h/d = 1)",
          abs(k1["e"] - 10.0) < 1e-9 and abs(k1["h_d"] - 1.0) < 1e-9, f"e {k1['e']:.2f}, h/d {k1['h_d']:.3f}")
    check("B13 ΣF der Gebäudeflächen gleich mit und ohne freie Wand",
          np.allclose(F0, F1, rtol=1e-9, atol=1e-6), f"{np.round(F0 / 1000, 3)} / {np.round(F1 / 1000, 3)} kN")
    # Zweiter Weg: Luv + Lee von Hand, h/d = 1: (0,8 + 0,5) b ∫ q_p dz
    z = np.linspace(0.0, 10.0, 20001)
    q = np.array([qp_hand(zz) for zz in z])
    soll = 1.3 * 10.0 * float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))
    Fx = float(kraft_der_flaechen(m1, w1.lastfall, ["Luv", "Lee"])[0])
    check("B13 Luv + Lee mit freier Wand = Hand (h/d = 1) auf 2 %",
          abs(Fx - soll) / soll < 0.02, f"{Fx / 1000:.3f} kN, Hand {soll / 1000:.3f} kN")
    # die freie Wand rechnet mit ihren eigenen Abmessungen: allein gleich wie neben dem Gebaeude
    m2, w2 = _quader(bau=False, frei=True)
    wm.lasten_erzeugen(m2, w2)
    FW2 = kraft_der_flaechen(m2, w2.lastfall, ["FW"])
    FW1 = kraft_der_flaechen(m1, w1.lastfall, ["FW"])
    check("B13 freie Wand neben dem Gebäude wie allein (eigene Zonen A–D)",
          FW2[0] > 0 and np.allclose(FW1, FW2, rtol=1e-9, atol=1e-6),
          f"{FW1[0] / 1000:.3f} / {FW2[0] / 1000:.3f} kN")
    # Tafel: q_p konstant (z <= 2 m), F = 1,8 q_p(2) 4 m²
    T = kraft_der_flaechen(m1, w1.lastfall, ["T"])
    soll_t = 1.8 * qp_hand(2.0) * 4.0
    check("B13 Tafel neben dem Gebäude = Hand 1,8 q_p A",
          abs(T[0] - soll_t) / soll_t < 1e-6, f"{T[0] / 1000:.3f} kN, Hand {soll_t / 1000:.3f} kN")


def test_befund13_alte_last():
    """Windlasten, die vor der Kur mit freier Wand erzeugt sind, tragen die alten
    Abmessungen im Verlauf: sie werden beim Oeffnen und im Status genannt."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_abmessungen")
    check("B13 Merkmal wind_abmessungen vorhanden (Stand 33, am Modell)",
          mk is not None and mk.wechsel[-1].stand == 33 and mk.import_korrektur and bool(mk.modellgrund))
    if mk is None:
        return
    m1, w1 = _quader(frei=True)
    wm.lasten_erzeugen(m1, w1)
    neu = mk.betrifft(m1)
    # alte Last nachbilden: Abmessungen aller Objekte, ohne Kennung
    for gl in m1.load_cases[w1.lastfall].geometrielasten:
        g = gl.verlauf["geometrie"]
        g.pop("abmessungen", None)
        g.update({"b": 45.0, "d": 30.0, "x_luv": -20.0, "t_max": 45.0})
    alt = mk.betrifft(m1)
    hinweis = wm.windlasten_hinweis(m1)
    m0, w0 = _quader()
    wm.lasten_erzeugen(m0, w0)
    for gl in m0.load_cases[w0.lastfall].geometrielasten:
        gl.verlauf["geometrie"].pop("abmessungen", None)
    check("B13 alte Last mit freier Wand betroffen, neu erzeugte und alte ohne freie Wand nicht",
          alt and not neu and not mk.betrifft(m0), f"alt {alt}, neu {neu}, ohne Wand {mk.betrifft(m0)}")
    check("B13 Ladehinweis nennt die alte Windlast", any("Abmessungen" in h for h in hinweis), str(hinweis)[:160])


def main():
    test_befund8()
    test_befund8_merkmal()
    test_befund9()
    test_befund9_merkmal()
    test_befund13()
    test_befund13_alte_last()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
