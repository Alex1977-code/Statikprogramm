"""
Freistehende Wand aus einem Volumen: Nettolast nur einmal (Kur vom 12.11.2026).

Befund: Eine Wand aus einem Volumen, bei der beide Seitenflaechen als freie
Wand (oder Anzeigetafel) gewaehlt sind, bekam die Nettowindlast doppelt - der
Nettobeiwert c_p,net (DIN EN 1991-1-4, Tab. 7.9) bzw. c_f (7.4.3) wirkte auf
beide Seitenflaechen, jede in Windrichtung. Wand 10 x 0,3 x 3 m, Wind
senkrecht: ΣF_x 53,508 statt 26,754 kN.

Entscheidung des Anwenders (12.11.2026): zwei gegenueberliegende
Seitenflaechen desselben Volumens gelten als eine Wand; die Nettolast wirkt
einmal, auf der luvseitigen Flaeche, in Windrichtung; das Protokoll sagt es
in einem Satz.

Zwei Wege der Zahlen: Handrechnung c_p,net · b_Zone · ∫ q_p dz mit q_p aus den
Formeln der Norm (unabhaengig von wind.q_p ausgeschrieben) und dieselbe Wand
als einzelne Schalenflaeche (gleiche Teilung).

Aufruf:  python -m tests.test_wind_freie_wand_volumen
"""
import contextlib
import copy
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
    """q_p(z) Gelaendekategorie II von Hand (4.8, 4.3, 4.4, 4.7)."""
    z = max(z, zmin)
    ln = math.log(z / z0)
    v_m = 0.19 * ln * v_b0
    return (1.0 + 7.0 / ln) * 0.5 * 1.25 * v_m ** 2


def int_qp(h):
    z = np.linspace(0.0, h, 30001)
    q = np.array([qp_hand(t) for t in z])
    return float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))


L, T, H = 10.0, 0.3, 3.0
#: Wand 10 x 3 m: Zone A je 0,3 h = 0,9 m an beiden Enden, B dazwischen (x_ende <= 5 < 2 h)
HAND_WAND = (2.3 * 2 * 0.9 + 1.4 * (L - 2 * 0.9)) * int_qp(H)
#: Tafel: c_f = 1,8 ueber die ganze Flaeche
HAND_TAFEL = 1.8 * L * int_qp(H)
S30 = (math.cos(math.radians(30)), math.sin(math.radians(30)), 0.0)


def _vernetzen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)


def volumenwand(teil=(1, 100, 30)):
    """Quader x 0 … 0,3, y 0 … 10, z 0 … 3; M3 bei x = 0 (aussen −x), M1 bei x = 0,3 (aussen +x)."""
    m = Model("VW")
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [T, 0, 0], [T, L, 0], [0, L, 0],
                          [0, 0, H], [T, 0, H], [T, L, H], [0, L, H]], float))
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
    k.teilung = list(teil)
    _vernetzen(m)
    return m


def schalenwand():
    """Dieselbe Wand als eine Schale in x = 0, gleiche Teilung (100 x 30)."""
    m = Model("SW")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.add_nodes(np.array([[0, 0, 0], [0, L, 0], [0, L, H], [0, 0, H]], float))
    lin = []
    for i in range(4):
        m.add_line(f"L{i}", [i, (i + 1) % 4])
        lin.append(f"L{i}")
    m.add_flaeche("FW", lin, material="S235", dicke="t10").teilung = [100, 30]
    m.netz.teilung_uebersteuern = False
    _vernetzen(m)
    return m


def summe(m, lf):
    return np.asarray(solver.case_loads(m, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)


def kraft_der_flaechen(m, lastfall, flaechen):
    """Summe ueber den Lastvektor, nur die Elementlasten auf ``flaechen``."""
    from statik3d.assemble import load_vector
    el = set()
    for nm in flaechen:
        el |= {int(e) for e in m.flaechen[nm].elemente}
        el |= {int(e) for e, _s in (m.flaechen[nm].randseiten or [])}
    seiten = {(int(e), int(s)) for nm in flaechen for e, s in (m.flaechen[nm].randseiten or [])}
    lc = LoadCase("nur")
    lc.face_loads = [f for f in m.load_cases[lastfall].face_loads
                     if (int(f.elem), int(f.face)) in seiten or (not seiten and int(f.elem) in el)]
    return np.asarray(load_vector(m, lc), float)[:6 * m.nn].reshape(-1, 6)[:, :3].sum(axis=0)


def erzeugen(m0, richtung, freie=(), schilder=(), flaechen=()):
    m = copy.deepcopy(m0)
    w = wm.Wind("W1", richtung=list(richtung), z_boden=0.0, freie_waende=list(freie),
                schilder=list(schilder), flaechen=list(flaechen))
    kw = wm.lasten_erzeugen(m, w)
    ziele = sorted(str(gl.ziel) for gl in m.load_cases[w.lastfall].geometrielasten)
    return m, w, kw, summe(m, w.lastfall), ziele


def test_volumenwand(mv, ms):
    # zweiter Weg: dieselbe Wand als Schale
    F_s = {}
    for d in ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), S30):
        _m, _w, _k, F, _z = erzeugen(ms, d, freie=["FW"])
        F_s[d] = F
    check("Schalenwand (zweiter Weg) = Hand, Wind +x", abs(F_s[(1.0, 0.0, 0.0)][0] - HAND_WAND) / HAND_WAND < 2e-3,
          f"{F_s[(1.0, 0.0, 0.0)][0] / 1000:.3f} kN, Hand {HAND_WAND / 1000:.3f} kN")
    for d, luv, name in (((1.0, 0.0, 0.0), "M3", "senkrecht +x"), ((-1.0, 0.0, 0.0), "M1", "senkrecht −x"),
                         (S30, "M3", "schräg 30°")):
        m, w, kw, F, ziele = erzeugen(mv, d, freie=["M3", "M1"])
        check(f"Volumenwand beide Seiten, Wind {name}: ΣF einmal = Schalenwand",
              np.allclose(F, F_s[d], rtol=1e-6, atol=1e-6 * HAND_WAND),
              f"F {np.round(F / 1000, 3)} kN, Schale {np.round(F_s[d] / 1000, 3)} kN")
        if d[1] == 0.0:
            check(f"Volumenwand beide Seiten, Wind {name}: ΣF in Windrichtung = Hand",
                  abs(F[0] * d[0] - HAND_WAND) / HAND_WAND < 2e-3 and abs(F[1]) + abs(F[2]) < 1e-6 * HAND_WAND,
                  f"{F[0] / 1000:.3f} kN, Hand {d[0] * HAND_WAND / 1000:.3f} kN")
        lee = "M1" if luv == "M3" else "M3"
        F_lee = kraft_der_flaechen(m, w.lastfall, [lee])
        check(f"Volumenwand, Wind {name}: Last nur auf der Luvseite {luv}",
              ziele == [luv] and np.allclose(F_lee, 0.0, atol=1e-9), f"Lasten auf {ziele}, Lee {lee} {F_lee}")
        saetze = [z for z in wm.erlaeuterung(w, kw) if "gegenüber" in z]
        check(f"Volumenwand, Wind {name}: Protokoll nennt Flächen, Volumen und Luvseite in einem Satz",
              len(saetze) == 1 and all(t in saetze[0] for t in ("M3", "M1", "Volumen K", f"Luvseite {luv}")),
              saetze[0] if saetze else "kein Satz")
    # Anzeigetafel aus einem Volumen: c_f einmal
    m, w, kw, F, ziele = erzeugen(mv, (1.0, 0.0, 0.0), schilder=["M3", "M1"])
    check("Tafel aus Volumen, beide Seiten: ΣF = 1,8 · q_p · A einmal, auf der Luvseite M3",
          abs(F[0] - HAND_TAFEL) / HAND_TAFEL < 2e-3 and ziele == ["M3"],
          f"{F[0] / 1000:.3f} kN, Hand {HAND_TAFEL / 1000:.3f} kN, Lasten auf {ziele}")
    # nur eine Seitenflaeche gewaehlt: wie bisher, einmal, ohne Satz
    for wahl in (["M3"], ["M1"]):
        for d in ((1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)):
            m, w, kw, F, ziele = erzeugen(mv, d, freie=wahl)
            check(f"Volumenwand nur {wahl[0]}, Wind {d[0]:+.0f}x: ΣF einmal in Windrichtung, kein Satz",
                  abs(F[0] * d[0] - HAND_WAND) / HAND_WAND < 2e-3 and ziele == wahl
                  and not any("gegenüber" in z for z in wm.erlaeuterung(w, kw)),
                  f"{F[0] / 1000:.3f} kN")


def test_merkmal(mv, ms):
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_freie_wand_volumen")
    check("Merkmal wind_freie_wand_volumen vorhanden (Stand 39, Fehlerkorrektur, am Modell)",
          mk is not None and mk.wechsel[-1].stand == 39 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.import_korrektur and bool(mk.modellgrund))
    check("VERFAHRENSSTAND mindestens 39", rv.VERFAHRENSSTAND >= 39, str(rv.VERFAHRENSSTAND))
    if mk is None:
        return
    neu, w, _k, _F, _z = erzeugen(mv, (1.0, 0.0, 0.0), freie=["M3", "M1"])
    # alte Last nachbilden: die Leeseite M1 traegt dieselbe Nettolast
    alt = copy.deepcopy(neu)
    gl = alt.load_cases[w.lastfall].geometrielasten[0]
    alt.add_geometrielast("M1", 0.0, art="flaeche", richtung=None, case=w.lastfall,
                          verlauf=copy.deepcopy(gl.verlauf))
    alt.lasten_verteilen()
    F_alt = summe(alt, w.lastfall)
    tafel_alt = copy.deepcopy(alt)
    for g in tafel_alt.load_cases[w.lastfall].geometrielasten:
        g.verlauf["rolle"] = "schild"
    eine, *_r = erzeugen(mv, (1.0, 0.0, 0.0), freie=["M1"])
    schale, *_r = erzeugen(ms, (1.0, 0.0, 0.0), freie=["FW"])
    huelle, *_r = erzeugen(mv, (1.0, 0.0, 0.0), flaechen=["M0", "M1", "M2", "M3", "Dach"])
    check("Merkmal: nachgebildete alte Last (beide Seiten) betroffen, auch als Tafel; ΣF doppelt",
          mk.betrifft(alt) and mk.betrifft(tafel_alt) and abs(F_alt[0] - 2 * HAND_WAND) / HAND_WAND < 4e-3,
          f"ΣF alt {F_alt[0] / 1000:.3f} kN")
    check("Merkmal: neu erzeugt, eine Seite, Schalenwand und Volumenhülle nicht betroffen",
          not mk.betrifft(neu) and not mk.betrifft(eine) and not mk.betrifft(schale) and not mk.betrifft(huelle))
    hinweis = wm.windlasten_hinweis(alt)
    check("Ladehinweis nennt die doppelte Nettolast", any("gegenüber" in h for h in hinweis), str(hinweis)[:160])


def main():
    mv = volumenwand()
    ms = schalenwand()
    test_volumenwand(mv, ms)
    test_merkmal(mv, ms)
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
