"""
Befunde C2, B4, B5 und B6 der Befundliste vom 14.11.2026 (fix/k5-b-windwasser, Stand 49).

C2  Mischprofil „Inseln der Nordsee“ (DIN EN 1991-1-4/NA, Tab. NA.B.2): die
    Werte sind absolut, q_p = 1,1 kN/m² bis 2 m, darüber 1,5·(z/10)^0,19
    kN/m² bis 300 m. Vor der Behebung als Faktoren auf q_b gelesen und mit
    einer dritten Stufe über 50 m: z = 10 m 0,844 statt 1,500 kN/m².
B4  Freistehende Wand, Tab. 7.9 (φ = 1, ohne Eckausbildung): c_p,net hängt
    von l/h ab (Zeilen l/h ≤ 3, = 5, ≥ 10, dazwischen linear). Vor der
    Behebung immer die Zeile l/h ≤ 3: Wand 30 × 3 m ΣF_x 68,547 statt
    94,443 kN, 15 × 3 m 37,716 statt 47,581 kN.
B5  Die Zonen A–D zählen entlang der Wand ab ihren freien Enden (Bild 7.19),
    nicht quer zur Windrichtung; eine Schale nahezu parallel zum Wind
    (|n·d| < 0,1) bekommt wie seit Stand 43 eine Volumenfläche keine
    Nettolast, das Vorzeichen hängt nie vom Umlauf ab. Vor der Behebung:
    Wand 20 × 3 m bei 45° Zonen quer zum Wind, parallel ±39,395 kN je nach Umlauf.
B6  Strömungsnumerischer Wasserdruck: an Schalen, die gegen die Lotrechte
    um mehr als 0,1° geneigt oder waagerecht sind, rechnet das Programm
    analytisch und sagt es im Protokoll. Vor der Behebung: 80° ΣF
    (−2,635; 0,465) statt (61,313; −10,811) kN, waagerecht 0 statt 78,48 kN.

Sollwerte von Hand: q_p nach EN 1991-1-4 4.3–4.5 (Geländekategorie II,
Windzone 2), die Zonenlängen der Wand geschlossen, Tab. 7.9 von Hand
interpoliert; Wasserdruck F = ½·ρ·g·h²·b/sin α senkrecht zur Wand bzw.
ρ·g·(h − z)·A.

Aufruf:  python -m tests.test_wind_wasser_b_1411
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

from statik3d import mesher, solver, wind as wm                 # noqa: E402
from statik3d import wasserdruck as wdm                          # noqa: E402
from statik3d.model import Material, Model, ShellProp            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<88} {detail}")
    return bool(ok)


def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


# ---------------------------------------------------------------------------
# Handrechnung Wind
# ---------------------------------------------------------------------------
def qp_hand(z, v_b0=25.0, z0=0.05, zmin=2.0):
    """q_p(z) Gelaendekategorie II von Hand (4.3, 4.4, 4.5, Windzone 2)."""
    z = max(z, zmin)
    ln = math.log(z / z0)
    v_m = 0.19 * ln * v_b0
    return (1.0 + 7.0 / ln) * 0.5 * 1.25 * v_m ** 2


def int_qp(h):
    z = np.linspace(0.0, h, 30001)
    q = np.array([qp_hand(t) for t in z])
    return float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))


#: Tab. 7.9, φ = 1, ohne Eckausbildung: A, B, C, D
ZEILE_3, ZEILE_5, ZEILE_10 = (2.3, 1.4, 1.2, 1.2), (2.9, 1.8, 1.4, 1.2), (3.4, 2.1, 1.7, 1.2)


def tab79(l_h):
    """c_p,net von Hand: Zeilen 3, 5, 10, dazwischen geradlinig."""
    if l_h <= 3.0:
        return ZEILE_3
    if l_h >= 10.0:
        return ZEILE_10
    if l_h <= 5.0:
        f, a, b = (l_h - 3.0) / 2.0, ZEILE_3, ZEILE_5
    else:
        f, a, b = (l_h - 5.0) / 5.0, ZEILE_5, ZEILE_10
    return tuple(x + f * (y - x) for x, y in zip(a, b))


def hand_wand(L, h, cp=None):
    """ΣF einer freien Wand L x h senkrecht zur Wand: Zonen A (0,3h), B (bis 2h),
    C (bis 4h), D ab beiden freien Enden entlang der Wand, geschlossen."""
    cp = cp or tab79(L / h)
    halb = 0.5 * L
    a = 2.0 * min(0.3 * h, halb)
    b = 2.0 * max(0.0, min(2.0 * h, halb) - 0.3 * h)
    c = 2.0 * max(0.0, min(4.0 * h, halb) - 2.0 * h)
    d = 2.0 * max(0.0, halb - 4.0 * h)
    return (cp[0] * a + cp[1] * b + cp[2] * c + cp[3] * d) * int_qp(h)


# ---------------------------------------------------------------------------
# Modelle
# ---------------------------------------------------------------------------
def _vernetzen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)


def _modell():
    m = Model("B")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.netz.teilung_uebersteuern = False
    return m


def _schale(m, name, P, teilung):
    i0 = len(m.nodes)
    m.add_nodes(np.asarray(P, float))
    lin = []
    for i in range(4):
        m.add_line(f"{name}_L{i}", [i0 + i, i0 + (i + 1) % 4])
        lin.append(f"{name}_L{i}")
    m.add_flaeche(name, lin, material="S235", dicke="t10").teilung = list(teilung)


def wand(L, h=3.0, rueck=False, drehung=0.0):
    """Schalenwand L x h, Fuss bei z = 0, in der Ebene x = 0 (Laenge entlang y), um
    ``drehung`` [°] um die z-Achse gedreht; ``rueck``: Linien andersherum."""
    m = _modell()
    c, s = math.cos(math.radians(drehung)), math.sin(math.radians(drehung))
    P = [[0, 0, 0], [0, L, 0], [0, L, h], [0, 0, h]]
    P = [[x * c - y * s, x * s + y * c, z] for x, y, z in P]
    _schale(m, "FW", P[::-1] if rueck else P, [int(round(L * 10)), int(round(h * 10))])
    _vernetzen(m)
    return m


def volumenwand(L=10.0, T=0.3, H=3.0):
    """Quader x 0 … T, y 0 … L, z 0 … H: M0 Stirn y = 0, M1 x = T, M2 Stirn y = L, M3 x = 0."""
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
    k.teilung = [1, int(round(L * 10)), int(round(H * 10))]
    _vernetzen(m)
    return m


def summe(m, lf):
    return np.asarray(solver.case_loads(m, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)


def wind_erzeugen(m0, richtung, freie=(), **kw_wind):
    m = copy.deepcopy(m0)
    w = wm.Wind("W1", richtung=list(richtung), z_boden=0.0, freie_waende=list(freie), **kw_wind)
    with contextlib.redirect_stdout(io.StringIO()):
        kw = wm.lasten_erzeugen(m, w)
    ziele = sorted(str(gl.ziel) for gl in m.load_cases[w.lastfall].geometrielasten)
    return m, w, kw, summe(m, w.lastfall), ziele


def fmt(F):
    return "(" + "; ".join(f"{x / 1000:+.3f}" for x in F) + ") kN"


# ---------------------------------------------------------------------------
# C2: Inseln der Nordsee
# ---------------------------------------------------------------------------
def test_c2():
    w4 = wm.Wind("N", zone=4, profil="Inseln der Nordsee")
    w2 = wm.Wind("N2", zone=2, profil="Inseln der Nordsee")
    k1 = wm.Wind("K1", zone=4, profil="I")
    for z in (1.0, 2.0, 5.0, 10.0, 40.0, 100.0, 250.0):
        soll = 1100.0 if z <= 2.0 else 1500.0 * (z / 10.0) ** 0.19
        check(f"C2 Nordsee z = {z:g} m: q_p = {soll / 1000:.3f} kN/m² (NA.B.2, absolut)",
              _rel(wm.q_p(z, w4), soll) < 1e-9, f"Programm {wm.q_p(z, w4) / 1000:.3f} kN/m²")
    check("C2 Nordsee über 50 m ohne eigene Stufe: q_p(100 m) = 1,5 · 10^0,19 kN/m²",
          _rel(wm.q_p(100.0, w4), 1500.0 * 10.0 ** 0.19) < 1e-9, f"{wm.q_p(100.0, w4) / 1000:.3f} kN/m²")
    check("C2 Nordsee absolut: unabhängig von Windzone und q_b",
          all(abs(wm.q_p(z, w2) - wm.q_p(z, w4)) < 1e-9 for z in (1.0, 10.0, 60.0)))
    # zweiter Weg: das Profil entspricht der Gelaendekategorie I (EN-Formel, Windzone 4)
    abw = [abs(wm.q_p(z, w4) / wm.q_p(z, k1) - 1.0) for z in (5.0, 10.0, 20.0, 40.0, 100.0)]
    check("C2 zweiter Weg: Nordsee 5–100 m innerhalb 6 % der Kategorie I (EN-Formel, WZ 4)",
          max(abw) < 0.06, f"größte Abweichung {max(abw) * 100:.1f} %")
    zeilen = wm.erlaeuterung(w4, wm.kennwerte(w4))
    satz = [z for z in zeilen if "Nordsee" in z]
    check("C2 Protokoll: absolute Werte genannt (1,1 und 1,5 kN/m²), nicht „Vielfaches von q_b“",
          len(satz) == 1 and "1,1 kN/m²" in satz[0] and "1,5" in satz[0] and "Vielfaches" not in satz[0],
          satz[0][:150] if satz else str(zeilen)[:150])


# ---------------------------------------------------------------------------
# B4: Tab. 7.9 nach l/h
# ---------------------------------------------------------------------------
def test_b4():
    for L, soll_beleg in ((9.0, 24.356e3), (15.0, 47.581e3), (30.0, 94.443e3), (10.0, None), (21.0, None)):
        _m, _w, _k, F, _z = wind_erzeugen(wand(L), (1, 0, 0), freie=["FW"])
        soll = hand_wand(L, 3.0)
        extra = f", Beleg {soll_beleg / 1000:.3f} kN" if soll_beleg else ""
        check(f"B4 Wand {L:g} × 3 m (l/h = {L / 3:.2f}), Wind +x: ΣF_x = Hand Tab. 7.9",
              _rel(F[0], soll) < 2e-3 and abs(F[1]) + abs(F[2]) < 1e-6 * soll
              and (soll_beleg is None or _rel(soll, soll_beleg) < 1e-4),
              f"{F[0] / 1000:.3f} kN, Hand {soll / 1000:.3f} kN{extra}")
    # c_p,net am Punkt: Zone A einer Wand mit l/h = 4 (zwischen den Zeilen 3 und 5)
    m, w, _k, _F, _z = wind_erzeugen(wand(12.0), (1, 0, 0), freie=["FW"])
    gl = m.load_cases[w.lastfall].geometrielasten[0]
    c, zone = wm.beiwert_am_punkt(gl.verlauf["param"], gl.verlauf["geometrie"], "freie_wand", (0.0, 0.1, 1.0))
    check("B4 l/h = 4: Zone A c_p,net = 2,6 (zwischen 2,3 und 2,9)", zone == "A" and abs(c - 2.6) < 1e-9,
          f"{zone} {c:.3f}")
    c, zone = wm.beiwert_am_punkt(gl.verlauf["param"], gl.verlauf["geometrie"], "freie_wand", (0.0, 4.0, 1.0))
    check("B4 l/h = 4: Zone B c_p,net = 1,6", zone == "B" and abs(c - 1.6) < 1e-9, f"{zone} {c:.3f}")


# ---------------------------------------------------------------------------
# B5: Zonen entlang der Wand, paralleler Wind
# ---------------------------------------------------------------------------
def test_b5():
    r2 = math.sqrt(0.5)
    soll10 = hand_wand(10.0, 3.0)
    soll20 = hand_wand(20.0, 3.0)
    for rueck in (False, True):
        _m, _w, _k, F, _z = wind_erzeugen(wand(20.0, rueck=rueck), (r2, r2, 0), freie=["FW"])
        check(f"B5 Wand 20 × 3 m, Wind 45°, Umlauf {'rück' if rueck else 'vor'}: ΣF = (Hand; 0; 0), "
              "Zonen entlang der Wand", _rel(F[0], soll20) < 2e-3 and abs(F[1]) + abs(F[2]) < 1e-6 * soll20,
              f"{fmt(F)}, Hand {soll20 / 1000:.3f} kN")
    # 80° zwischen Normale und Wind (|n·d| = 0,17 ≥ 0,1): volle Nettolast senkrecht zur Wand
    d80 = (math.cos(math.radians(80.0)), math.sin(math.radians(80.0)), 0.0)
    for rueck in (False, True):
        _m, _w, _k, F, _z = wind_erzeugen(wand(10.0, rueck=rueck), d80, freie=["FW"])
        check(f"B5 Wand, Wind 80° zur Normalen, Umlauf {'rück' if rueck else 'vor'}: ΣF_x = +Hand",
              _rel(F[0], soll10) < 2e-3 and abs(F[1]) + abs(F[2]) < 1e-6 * soll10, fmt(F))
    # gedrehte Wand (30° um z), Wind senkrecht zu ihr: dieselbe Kraft wie die ungedrehte
    n30 = (math.cos(math.radians(30.0)), math.sin(math.radians(30.0)), 0.0)
    _m, _w, _k, F, _z = wind_erzeugen(wand(30.0, drehung=30.0), n30, freie=["FW"])
    soll30 = hand_wand(30.0, 3.0)
    check("B5 Wand 30 m um 30° gedreht, Wind senkrecht: |ΣF| = Hand, in Windrichtung",
          _rel(float(np.linalg.norm(F)), soll30) < 2e-3 and float(F @ np.asarray(n30)) > 0.999 * np.linalg.norm(F),
          f"{fmt(F)}, Hand {soll30 / 1000:.3f} kN")
    # paralleler Wind: keine Nettolast, gleich wie Umlauf und Windsinn
    for rueck in (False, True):
        for d in ((0, 1, 0), (0, -1, 0)):
            m, w, kw, F, ziele = wind_erzeugen(wand(10.0, rueck=rueck), d, freie=["FW"])
            satz = [z for z in wm.erlaeuterung(w, kw) if "FW" in z and "parallel" in z]
            check(f"B5 Schalenwand, Wind {d} parallel, Umlauf {'rück' if rueck else 'vor'}: ΣF = 0, "
                  "keine Last, Satz im Protokoll", np.allclose(F, 0.0, atol=1e-9) and not ziele and len(satz) == 1,
                  f"{fmt(F)}, Lasten auf {ziele}")
    # Schale und Volumen gleich: 45° und parallel
    mv = volumenwand(L=20.0)
    for d, soll in (((r2, r2, 0), np.array([soll20, 0.0, 0.0])), ((0, 1, 0), np.zeros(3))):
        _m, _w, _k, Fs, _z = wind_erzeugen(wand(20.0), d, freie=["FW"])
        _m, _w, _k, Fv, _z = wind_erzeugen(mv, d, freie=["M1", "M3"])
        check(f"B5 Schale und Volumen 20 × 0,3 × 3 m, Wind {tuple(round(x, 3) for x in d)}: gleiche ΣF = Soll",
              np.allclose(Fs, soll, rtol=2e-3, atol=1e-6 * soll20)
              and np.allclose(Fv, soll, rtol=2e-3, atol=1e-6 * soll20),
              f"Schale {fmt(Fs)}, Volumen {fmt(Fv)}")


# ---------------------------------------------------------------------------
# B6: Wasserdruck numerisch an geneigten und waagerechten Schalen
# ---------------------------------------------------------------------------
RHO, G = 1000.0, 9.81


def wasserwand(ecken, teilung=(8, 12)):
    m = Model("W")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.add_nodes(np.asarray(ecken, float))
    for i in range(4):
        m.add_line(f"L{i}", [i, (i + 1) % 4])
    f = m.add_flaeche("W", [f"L{i}" for i in range(4)], material="S235", dicke="t10")
    f.teilung = list(teilung)
    m.netz.ziellaenge = 0.25
    _vernetzen(m)
    return m


def geneigt(grad, lehnt="ab", L=3.0):
    """Wand 2 m breit, L lang an der Boeschung, Fuss bei z = 0, ``grad`` gegen die
    Waagerechte; Oberwasser auf der Seite y < 0, Stroemung +y. Rueckgabe Modell,
    ow_seite und Soll-ΣF fuer ein Oberwasser von 2,5 m (rein hydrostatisch)."""
    a = math.radians(grad)
    s = 1.0 if lehnt == "ab" else -1.0
    top = [0.0, s * L * math.cos(a), L * math.sin(a)]
    E = [[0, 0, 0], [2, 0, 0], [2, top[1], top[2]], [0, top[1], top[2]]]
    n = np.cross(np.subtract(E[1], E[0]), np.subtract(E[3], E[0]))
    n = n / np.linalg.norm(n)
    n_ow = n if n[1] < 0 else -n
    soll = -0.5 * RHO * G * 2.5 ** 2 * 2.0 / math.sin(a) * n_ow
    return wasserwand(E), ("Oberseite" if n[1] < 0 else "Unterseite"), soll


def wasser_erzeugen(m, **kw):
    wdm._FELD_CACHE.clear()
    wd = wdm.Wasserdruck("W1", flaechen=["W"], absenkung=False, **kw)
    with contextlib.redirect_stdout(io.StringIO()):
        k = wdm.lasten_erzeugen(m, wd)
    return wd, k, summe(m, wd.lastfall)


def test_b6():
    for grad, lehnt in ((80.0, "ab"), (80.0, "zu"), (60.0, "ab"), (88.5, "ab"), (88.5, "zu")):
        m, ow, soll = geneigt(grad, lehnt)
        wd, k, F = wasser_erzeugen(m, h_ow=2.5, verfahren="numerisch", ow_flaeche="W", ow_seite=ow)
        satz = [z for z in wdm.erlaeuterung(wd, k) if "analytisch" in z and "W" in z and "0,1°" in z]
        check(f"B6 Schale {grad:g}° lehnt {lehnt}, numerisch gewählt: ΣF = Hand (analytisch gerechnet)",
              np.allclose(F, soll, rtol=5e-3, atol=5e-3 * np.linalg.norm(soll)), f"{fmt(F)}, Hand {fmt(soll)}")
        check(f"B6 Schale {grad:g}° lehnt {lehnt}: Satz im Protokoll, Last ohne Druckfeld",
              len(satz) == 1 and not any(gl.verlauf.get("feld") for lc in m.load_cases.values()
                                         for gl in lc.geometrielasten),
              satz[0][:120] if satz else "kein Satz")
    m, ow, soll = geneigt(80.0, "ab")
    wd, k, F = wasser_erzeugen(m, h_ow=2.5, verfahren="numerisch", ow_flaeche="W", ow_seite=ow)
    check("B6 80°: Kennwert F = ½·ρ·g·h²·b = 61,31 kN (vorher 0)", _rel(k["F"], 0.5 * RHO * G * 2.5 ** 2 * 2) < 2e-3,
          f"{k['F'] / 1000:.3f} kN")
    # waagerecht: Platte 2 x 2 m bei z = 1 m, Oberwasser 3 m
    P = [[0, 0, 1], [2, 0, 1], [2, 2, 1], [0, 2, 1]]
    for seite, vz in (("Oberseite", -1.0), ("Unterseite", 1.0)):
        m = wasserwand(P, (8, 8))
        wd, k, F = wasser_erzeugen(m, h_ow=3.0, verfahren="numerisch", ow_flaeche="W", ow_seite=seite)
        soll = np.array([0.0, 0.0, vz * RHO * G * 2.0 * 4.0])
        check(f"B6 waagerechte Platte, Oberwasser auf der {seite}: ΣF_z = {vz * 78.48:+.2f} kN",
              np.allclose(F, soll, rtol=2e-3, atol=1e-3), fmt(F))
    # gemischt: lotrechte Wand V (x 0 … 2) und um 10° geneigte G (x 3 … 5) im selben Schnitt -
    # G rechnet analytisch und bleibt aus dem Gitter, V numerisch wie allein
    a80 = math.radians(80.0)
    top = [0.0, 3.0 * math.cos(a80), 3.0 * math.sin(a80)]
    m = Model("W")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    for name, E in (("V", [[0, 0, 0], [2, 0, 0], [2, 0, 3], [0, 0, 3]]),
                    ("G", [[3, 0, 0], [5, 0, 0], [5, top[1], top[2]], [3, top[1], top[2]]])):
        b0 = m.nn
        m.add_nodes(np.asarray(E, float))
        for i in range(4):
            m.add_line(f"{name}{i}", [b0 + i, b0 + (i + 1) % 4])
        m.add_flaeche(name, [f"{name}{i}" for i in range(4)], material="S235", dicke="t10").teilung = [8, 12]
    m.netz.ziellaenge = 0.25
    _vernetzen(m)
    wdm._FELD_CACHE.clear()
    wd = wdm.Wasserdruck("W1", flaechen=["V", "G"], absenkung=False, h_ow=2.5, verfahren="numerisch",
                         ow_flaeche="V", ow_seite="Oberseite")
    with contextlib.redirect_stdout(io.StringIO()):
        k = wdm.lasten_erzeugen(m, wd)
    F = summe(m, wd.lastfall)
    soll = np.array([0.0, 61.218e3 + 61.313e3, -10.811e3])
    check("B6 lotrechte und geneigte Schale im selben Schnitt: V numerisch (61,218), G analytisch (61,313; "
          "−10,811)", np.allclose(F, soll, rtol=2e-3, atol=0.03e3) and list(k.get("analytisch_flaechen", {})) == ["G"],
          f"{fmt(F)}, Soll {fmt(soll)}")
    # lotrecht bleibt numerisch (Feld im Verlauf, Wert der Stroemungsrechnung)
    m, ow, soll = geneigt(90.0, "ab")
    wd, k, F = wasser_erzeugen(m, h_ow=2.5, verfahren="numerisch", ow_flaeche="W", ow_seite=ow)
    hat_feld = all(gl.verlauf.get("feld") for lc in m.load_cases.values() for gl in lc.geometrielasten)
    check("B6 lotrechte Schale bleibt numerisch: Druckfeld im Verlauf, ΣF_y = 61,218 kN (Feld)",
          hat_feld and k.get("verfahren") == "numerisch" and abs(F[1] / 1000 - 61.218) < 0.01
          and not any("0,1°" in z for z in wdm.erlaeuterung(wd, k)), fmt(F))


# ---------------------------------------------------------------------------
# Verfahrensmerkmale (Stand 49)
# ---------------------------------------------------------------------------
def test_merkmale():
    from statik3d import rechenverfahren as rv
    check("VERFAHRENSSTAND mindestens 49", rv.VERFAHRENSSTAND >= 49, str(rv.VERFAHRENSSTAND))
    for name, modell in (("wind_nordsee", False), ("wind_nordsee_staebe", True), ("wind_freie_wand_lh", False),
                         ("wind_freie_wand_zonen", True), ("wasserdruck_geneigt", True)):
        mk = rv.merkmal(name)
        ok = (mk is not None and mk.wechsel[-1].stand == 49 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
              and mk.wechsel[-1].datum == "14.11.2026" and mk.wechsel[-1].commit == "fix/k5-b-windwasser")
        if ok and modell:
            ok = mk.import_korrektur and bool(mk.modellgrund) and "neu erzeugen" in mk.vorschlag
        check(f"Merkmal {name}: Stand 49, Fehlerkorrektur" + (", Korrektur am Modell" if modell else ""), ok)
    mk = rv.merkmal("wind_nordsee")
    if mk is not None:
        m = wand(10.0)
        mn, *_r = wind_erzeugen(m, (1, 0, 0), freie=["FW"], profil="Inseln der Nordsee", zone=4)
        m2, *_r = wind_erzeugen(m, (1, 0, 0), freie=["FW"])
        check("Merkmal wind_nordsee: betrifft das Modell mit Nordsee-Wind, nicht das mit Kat. II",
              mk.betrifft(mn) and not mk.betrifft(m2))
    mk = rv.merkmal("wind_nordsee_staebe")
    if mk is not None:
        from statik3d.model import Member, Section
        m = wand(10.0)
        m.add_section(Section.pipe("CHS", 0.2, 0.006))
        ids = [m.add_node(5.0, 5.0, i * 1.0) for i in range(11)]
        el = [m.add_element("beam", [ids[i], ids[i + 1]], "S235", "CHS") for i in range(10)]
        m.members["Mast"] = Member("Mast", el)
        neu, wn, *_r = wind_erzeugen(m, (1, 0, 0), staebe=["Mast"], profil="Inseln der Nordsee", zone=4)
        alt = copy.deepcopy(neu)
        for ll in alt.load_cases[wn.lastfall].linienlasten:
            ll.q = [0.5625 * x for x in ll.q]
            ll.q2 = [0.5625 * x for x in ll.q2] if ll.q2 is not None else None
        alt.lasten_verteilen()
        h = wm.windlasten_hinweis(alt)
        check("Merkmal wind_nordsee_staebe: Stablast mit q_p nach altem Profil betroffen, neu erzeugt nicht; "
              "Ladehinweis", mk.betrifft(alt) and not mk.betrifft(neu)
              and any("Nordsee" in z and wn.lastfall in z and "neu erzeugen" in z for z in h), str(h)[:160])
    mk = rv.merkmal("wind_freie_wand_lh")
    if mk is not None:
        m30, *_r = wind_erzeugen(wand(30.0), (1, 0, 0), freie=["FW"])
        m9, *_r = wind_erzeugen(wand(9.0), (1, 0, 0), freie=["FW"])
        check("Merkmal wind_freie_wand_lh: Wand 30 × 3 m betroffen, 9 × 3 m (l/h = 3) nicht",
              mk.betrifft(m30) and not mk.betrifft(m9))
    mk = rv.merkmal("wind_freie_wand_zonen")
    if mk is not None:
        r2 = math.sqrt(0.5)
        neu45, w45, _k, F45, _z = wind_erzeugen(wand(20.0), (r2, r2, 0), freie=["FW"])
        alt45 = copy.deepcopy(neu45)
        for gl in alt45.load_cases[w45.lastfall].geometrielasten:
            for k in ("laengs", "s_min", "s_max", "l"):
                gl.verlauf["geometrie"].pop(k, None)
        alt45.lasten_verteilen()
        F45a = summe(alt45, w45.lastfall)
        neu0, w0, *_r = wind_erzeugen(wand(10.0), (1, 0, 0), freie=["FW"])
        alt0 = copy.deepcopy(neu0)
        for gl in alt0.load_cases[w0.lastfall].geometrielasten:
            for k in ("laengs", "s_min", "s_max", "l"):
                gl.verlauf["geometrie"].pop(k, None)
        alt0.lasten_verteilen()
        F0a, F0n = summe(alt0, w0.lastfall), summe(neu0, w0.lastfall)
        # Schale parallel zum Wind mit Nettolast (wie vor der Behebung erzeugt)
        neup, wp, *_r = wind_erzeugen(wand(10.0), (0, 1, 0), freie=["FW"])
        altp = copy.deepcopy(neup)
        v = copy.deepcopy(neu45.load_cases[w45.lastfall].geometrielasten[0].verlauf)
        v["geometrie"]["richtung"] = [0.0, 1.0, 0.0]
        for k in ("laengs", "s_min", "s_max", "l"):
            v["geometrie"].pop(k, None)
        altp.add_geometrielast("FW", 0.0, art="flaeche", richtung=None, case=wp.lastfall, verlauf=v)
        altp.lasten_verteilen()
        check("Merkmal wind_freie_wand_zonen: alte Last bei 45° und parallele Schalenlast betroffen",
              mk.betrifft(alt45) and mk.betrifft(altp) and _rel(F45a[0], F45[0]) > 0.01,
              f"45° alt {F45a[0] / 1000:.3f} statt {F45[0] / 1000:.3f} kN")
        check("Merkmal wind_freie_wand_zonen: neu erzeugte Lasten und alte senkrecht angeströmte nicht betroffen "
              "(dort dieselbe Last)", not mk.betrifft(neu45) and not mk.betrifft(neup) and not mk.betrifft(neu0)
              and not mk.betrifft(alt0) and np.allclose(F0a, F0n, rtol=1e-12, atol=1e-9))
        h = wm.windlasten_hinweis(alt45)
        check("Ladehinweis zur alten Wandlast nennt Wind und Lastfall und rät zum Neuerzeugen",
              any("W1" in z and w45.lastfall in z and "neu erzeugen" in z and "entlang" in z for z in h),
              str(h)[:200])
    mk = rv.merkmal("wasserdruck_geneigt")
    if mk is not None:
        m90, ow90, _s = geneigt(90.0, "ab")
        wd90, _k, _F = wasser_erzeugen(m90, h_ow=2.5, verfahren="numerisch", ow_flaeche="W", ow_seite=ow90)
        m80, ow80, _s = geneigt(80.0, "ab")
        wd80, _k, _F = wasser_erzeugen(m80, h_ow=2.5, verfahren="numerisch", ow_flaeche="W", ow_seite=ow80)
        alt80 = copy.deepcopy(m80)
        lc = alt80.load_cases[wd80.lastfall]
        v = copy.deepcopy(m90.load_cases[wd90.lastfall].geometrielasten[0].verlauf)
        lc.geometrielasten = []
        alt80.add_geometrielast("W", 0.0, art="flaeche", richtung=None, case=wd80.lastfall, verlauf=v)
        alt80.lasten_verteilen()
        check("Merkmal wasserdruck_geneigt: Druckfeld auf der geneigten Schale betroffen, neu erzeugt "
              "und lotrecht nicht", mk.betrifft(alt80) and not mk.betrifft(m80) and not mk.betrifft(m90))
        h = wdm.wasserdruck_hinweis(alt80)
        check("Ladehinweis zum alten Druckfeld nennt Wasserdruck und Lastfall und rät zum Neuerzeugen",
              len(h) == 1 and "W1" in h[0] and wd80.lastfall in h[0] and "neu erzeugen" in h[0]
              and not wdm.wasserdruck_hinweis(m80), str(h)[:160])


def main():
    for t in (test_c2, test_b4, test_b5, test_b6, test_merkmale):
        try:
            t()
        except Exception as ex:                       # noqa: BLE001 - vor der Behebung fehlen Teile
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
