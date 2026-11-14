"""
Freistehende Wand aus mehreren Flaechen und quer angestroemte Volumenflaechen
(Behebung vom 14.11.2026, Befunde A8, A9 und A10 der Pruefagenten).

A8: Eine freie Wand aus mehreren Flaechen zaehlte die Zonen A bis D (Tab. 7.9)
und die Hoehe h je Teilflaeche. Wand 30 x 3 m aus drei Flaechen je 10 m:
ΣF_x 80,262 statt 68,547 kN (+17 %); Wand 10 x 3 m aus zwei Flaechen
uebereinander: 25,411 statt 26,754 kN (−5 %). Nach der Behebung bilden
Flaechen derselben Rolle, die sich beruehren, eine Wand; Enden, h und Zonen
kommen aus der ganzen Wand.

A9: Stirnflaechen, Boden und Dach eines Volumens mit der Rolle freie Wand
bildeten ein Luv/Lee-Paar und bekamen eine einseitige Nettolast quer zum Wind
(Wand 10 x 0,3 x 3 m, Wind +x: F_y −1,182 kN, Protokoll „Luvseite M0“). Nach
der Behebung bilden Volumenflaechen mit |n · d| < 0,1 kein Paar und tragen
keine Nettolast; das Protokoll nennt sie in einem Satz.

A10 (Teil): der Ladehinweis „Abmessungen“ verglich an freien Waenden auch d
und x_luv, die dort nicht wirken (Wand + Mast: Hinweis, obwohl ΣF gleich).

Zwei Wege der Zahlen: Handrechnung c_p,net · Zonenlaenge · ∫ q_p dz mit q_p
aus den Formeln der Norm (unabhaengig von wind.q_p ausgeschrieben) und
dieselbe Wand als eine einzige Schalenflaeche (Programm, gleiche Teilung).

Aufruf:  python -m tests.test_wind_freie_wand_ganz
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

from statik3d import mesher, solver, wind as wm                          # noqa: E402
from statik3d.model import Material, Member, Model, Section, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<84} {detail}")
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


H = 3.0
IQ = int_qp(H)
#: Wand 30 x 3 m, Zonen ab beiden Enden: A 0,9 m, B bis 6 m, C bis 12 m, D die mittleren 6 m
HAND_30 = (2.3 * 2 * 0.9 + 1.4 * 2 * (6.0 - 0.9) + 1.2 * 2 * (12.0 - 6.0) + 1.2 * (30.0 - 24.0)) * IQ
#: Wand 10 x 3 m: A 0,9 m je Ende, B dazwischen
HAND_10 = (2.3 * 2 * 0.9 + 1.4 * (10.0 - 2 * 0.9)) * IQ
#: Stirnflaeche 0,3 x 3 m als freie Wand, ganz in Zone A
HAND_STIRN = 2.3 * 0.3 * IQ


def _vernetzen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)


def _schale(m, name, P, teilung):
    i0 = len(m.nodes)
    m.add_nodes(np.asarray(P, float))
    lin = []
    for i in range(4):
        m.add_line(f"{name}_L{i}", [i0 + i, i0 + (i + 1) % 4])
        lin.append(f"{name}_L{i}")
    m.add_flaeche(name, lin, material="S235", dicke="t10").teilung = list(teilung)


def schalenwand(stuecke, x=0.0):
    """Wand in der Ebene x = konst. aus Rechtecken (y0, y1, z0, z1), Teilung 0,1 m."""
    m = Model("SW")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.netz.teilung_uebersteuern = False
    for i, (y0, y1, z0, z1) in enumerate(stuecke):
        _schale(m, f"F{i}", [[x, y0, z0], [x, y1, z0], [x, y1, z1], [x, y0, z1]],
                [int(round((y1 - y0) * 10)), int(round((z1 - z0) * 10))])
    _vernetzen(m)
    return m, [f"F{i}" for i in range(len(stuecke))]


def volumenwand():
    """Quader x 0 … 0,3, y 0 … 10, z 0 … 3: M0 Stirn y = 0 (aussen −y), M1 x = 0,3,
    M2 Stirn y = 10, M3 x = 0 (aussen −x)."""
    m = Model("VW")
    m.add_material(Material.steel("S235"))
    T, L = 0.3, 10.0
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
    k.teilung = [1, 100, 30]
    _vernetzen(m)
    return m


def summe(m, lf):
    return np.asarray(solver.case_loads(m, {lf: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)


def erzeugen(m0, richtung, freie=(), schilder=(), **kw_wind):
    m = copy.deepcopy(m0)
    w = wm.Wind("W1", richtung=list(richtung), z_boden=0.0, freie_waende=list(freie),
                schilder=list(schilder), **kw_wind)
    with contextlib.redirect_stdout(io.StringIO()):
        kw = wm.lasten_erzeugen(m, w)
    ziele = sorted(str(gl.ziel) for gl in m.load_cases[w.lastfall].geometrielasten)
    return m, w, kw, summe(m, w.lastfall), ziele


def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


# ---------------------------------------------------------------------------
# A8: freie Wand aus mehreren Flaechen
# ---------------------------------------------------------------------------
def test_a8():
    eine30, n1 = schalenwand([(0, 30, 0, 3)])
    drei30, n3 = schalenwand([(0, 10, 0, 3), (10, 20, 0, 3), (20, 30, 0, 3)])
    _m, _w, _k, F1, _z = erzeugen(eine30, (1, 0, 0), freie=n1)
    m3, w3, _k, F3, _z = erzeugen(drei30, (1, 0, 0), freie=n3)
    check("A8 zweiter Weg: Wand 30 m als eine Fläche = Hand", _rel(F1[0], HAND_30) < 2e-3,
          f"{F1[0] / 1000:.3f} kN, Hand {HAND_30 / 1000:.3f} kN")
    check("A8 Wand 30 m aus drei Flächen: ΣF_x = Hand (Zonen ab den Wandenden)",
          _rel(F3[0], HAND_30) < 2e-3 and abs(F3[1]) + abs(F3[2]) < 1e-6 * HAND_30,
          f"{F3[0] / 1000:.3f} kN, Hand {HAND_30 / 1000:.3f} kN")
    check("A8 Wand 30 m aus drei Flächen: ΣF = eine Fläche", np.allclose(F3, F1, rtol=1e-6, atol=1e-6 * HAND_30),
          f"{np.round(F3 / 1000, 3)} / {np.round(F1 / 1000, 3)} kN")
    g = [gl.verlauf["geometrie"] for gl in m3.load_cases[w3.lastfall].geometrielasten]
    check("A8 jede Teilfläche trägt die Enden der ganzen Wand (t 0 … 30 m, h = 3 m)",
          len(g) == 3 and all(abs(x["t_min"]) < 1e-9 and abs(x["t_max"] - 30.0) < 1e-9
                              and abs(x["h"] - 3.0) < 1e-9 for x in g),
          str([(round(x["t_min"], 3), round(x["t_max"], 3), round(x["h"], 3)) for x in g]))
    eine10, e1 = schalenwand([(0, 10, 0, 3)])
    zwei10, e2 = schalenwand([(0, 10, 0, 1.5), (0, 10, 1.5, 3)])
    _m, _w, _k, G1, _z = erzeugen(eine10, (1, 0, 0), freie=e1)
    m2, w2, _k, G2, _z = erzeugen(zwei10, (1, 0, 0), freie=e2)
    check("A8 zweiter Weg: Wand 10 m als eine Fläche = Hand", _rel(G1[0], HAND_10) < 2e-3,
          f"{G1[0] / 1000:.3f} kN, Hand {HAND_10 / 1000:.3f} kN")
    check("A8 Wand 10 m aus zwei Flächen übereinander: ΣF_x = Hand (h = 3 m für beide)",
          _rel(G2[0], HAND_10) < 2e-3 and np.allclose(G2, G1, rtol=1e-6, atol=1e-6 * HAND_10),
          f"{G2[0] / 1000:.3f} kN, Hand {HAND_10 / 1000:.3f} kN")
    h = sorted(round(gl.verlauf["geometrie"]["h"], 6) for gl in m2.load_cases[w2.lastfall].geometrielasten)
    check("A8 untere Teilfläche mit h der ganzen Wand (3 m statt 1,5 m)", h == [3.0, 3.0], str(h))
    # Gegenprobe: zwei getrennte Waende (5 m Luecke) bleiben zwei Waende, jede mit eigenen Enden
    getrennt, ng = schalenwand([(0, 10, 0, 3), (15, 25, 0, 3)])
    _m, _w, _k, Fg, _z = erzeugen(getrennt, (1, 0, 0), freie=ng)
    check("A8 Gegenprobe: zwei getrennte Wände je 10 m = 2 × Hand der 10-m-Wand",
          _rel(Fg[0], 2 * HAND_10) < 2e-3, f"{Fg[0] / 1000:.3f} kN, Hand {2 * HAND_10 / 1000:.3f} kN")
    # Tafel aus zwei Flaechen: c_f gleichfoermig, die Summe aendert sich nicht (nur h)
    _m, _w, _k, Ft, _z = erzeugen(zwei10, (1, 0, 0), schilder=e2)
    check("A8 Tafel aus zwei Flächen: ΣF_x = 1,8 · 10 m · ∫ q_p dz", _rel(Ft[0], 1.8 * 10.0 * IQ) < 2e-3,
          f"{Ft[0] / 1000:.3f} kN, Hand {1.8 * 10.0 * IQ / 1000:.3f} kN")


# ---------------------------------------------------------------------------
# A9: quer angestroemte Flaechen eines Volumens
# ---------------------------------------------------------------------------
def test_a9(mv):
    m, w, kw, F, ziele = erzeugen(mv, (1, 0, 0), freie=["M0", "M1", "M2", "M3"])
    check("A9 Volumen, vier Seiten, Wind +x: ΣF = (Hand; 0; 0), Last nur auf M3",
          _rel(F[0], HAND_10) < 2e-3 and abs(F[1]) < 1e-6 * HAND_10 and abs(F[2]) < 1e-6 * HAND_10
          and ziele == ["M3"], f"{np.round(F / 1000, 3)} kN, Lasten auf {ziele}")
    # schraeger Wind 45°: die Stirnflaeche (quer zur Seitenflaeche) ist keine Teilflaeche
    # der Seitenwand - deren Enden bleiben, wie mit den Seiten allein gewaehlt
    r2 = math.sqrt(0.5)
    _m, _w, _k, F45, _z = erzeugen(mv, (r2, r2, 0), freie=["M0", "M1", "M2", "M3"])
    _m, _w, _k, F45s, _z = erzeugen(mv, (r2, r2, 0), freie=["M3", "M1"])
    check("A9/A8 Volumen, vier Seiten, Wind 45°: F_x wie mit M3/M1 allein, F_y = Stirn M0 (Hand)",
          _rel(F45[0], F45s[0]) < 1e-9 and _rel(F45[1], HAND_STIRN) < 2e-3,
          f"{np.round(F45 / 1000, 3)} kN, M3/M1 allein {np.round(F45s / 1000, 3)} kN")
    prot = wm.erlaeuterung(w, kw)
    satz = [z for z in prot if "parallel" in z]
    check("A9 Protokoll: ein Satz nennt M0 und M2 ohne Nettolast, keine Luvseite M0/M2",
          len(satz) == 1 and "M0" in satz[0] and "M2" in satz[0] and "Volumens K" in satz[0]
          and not any("Luvseite M0" in z or "Luvseite M2" in z for z in prot),
          satz[0] if satz else str(prot[-2:]))
    for d in ((1, 0, 0), (0, 1, 0)):
        m, w, kw, F, ziele = erzeugen(mv, d, freie=["Boden", "Dach", "M0", "M1", "M2", "M3"])
        soll = np.array([HAND_10, 0.0, 0.0]) if d[0] else np.array([0.0, HAND_STIRN, 0.0])
        check(f"A9 Volumen, alle sechs Flächen, Wind {d}: keine Last quer zum Wind, ΣF = Hand",
              np.allclose(F, soll, rtol=2e-3, atol=1e-6 * HAND_10) and "Boden" not in ziele and "Dach" not in ziele,
              f"{np.round(F / 1000, 3)} kN, Soll {np.round(soll / 1000, 3)} kN, Lasten auf {ziele}")
    m, w, kw, F, ziele = erzeugen(mv, (1, 0, 0), freie=["M0"])
    check("A9 nur die Stirnfläche M0, Wind +x (parallel): keine Last, Satz im Protokoll",
          np.allclose(F, 0.0, atol=1e-9) and not ziele and any("M0" in z and "parallel" in z
                                                                for z in wm.erlaeuterung(w, kw)),
          f"{np.round(F / 1000, 3)} kN, Lasten auf {ziele}")
    m, w, kw, F, ziele = erzeugen(mv, (0, 1, 0), freie=["M3", "M1"])
    check("A9 Seiten M3/M1, Wind +y (parallel): keine Nettolast quer zum Wind",
          np.allclose(F, 0.0, atol=1e-9) and not ziele, f"{np.round(F / 1000, 3)} kN, Lasten auf {ziele}")
    m, w, kw, F, ziele = erzeugen(mv, (0, 1, 0), freie=["M0"])
    check("A9 Stirnfläche M0 senkrecht angeströmt (Wind +y): ΣF_y = 2,3 · 0,3 m · ∫ q_p dz",
          _rel(F[1], HAND_STIRN) < 2e-3 and abs(F[0]) < 1e-9, f"{np.round(F / 1000, 3)} kN")
    # Windkanal, Aufriss: M0/M2 liegen nicht in der Schnittebene und kommen aus der Norm
    m, w, kw, F, ziele = erzeugen(mv, (1, 0, 0), freie=["M0", "M1", "M2", "M3"], verfahren="windkanal",
                                  schnittart="aufriss", gitter=10, schritte=400, re=100.0)
    check("A9 Windkanal Aufriss, vier Seiten, Wind +x: F_y = 0, keine Last auf M0/M2",
          abs(F[1]) < 1e-6 * abs(F[0]) and "M0" not in ziele and "M2" not in ziele,
          f"{np.round(F / 1000, 3)} kN, Lasten auf {ziele}")


# ---------------------------------------------------------------------------
# A10: Hinweis „Abmessungen“ an freien Waenden nur nach h, t_min, t_max
# ---------------------------------------------------------------------------
def _wand_mit_mast():
    m, namen = schalenwand([(0, 10, 0, 3)])
    m.add_section(Section.pipe("CHS", 0.2, 0.006))
    ids = [m.add_node(1.0, 5.0, i * 0.5) for i in range(7)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S235", "CHS") for i in range(6)]
    m.members["Mast"] = Member("Mast", el)
    return m, namen


def _alt_wie_vor_stand_33(m, w):
    """Die Geometrie der Wandlast wie vor dem 12.11.2026: Abmessungen aller Objekte, ohne Kennung."""
    geo = wm.gebaeude(w, m, alle=True)
    geo.pop("abmessungen", None)
    for gl in m.load_cases[w.lastfall].geometrielasten:
        if gl.verlauf.get("rolle") in wm.ROLLEN_NETTO:
            gl.verlauf["geometrie"] = dict(geo)
    m.lasten_verteilen()


def test_a10():
    from statik3d import rechenverfahren as rv
    m0, namen = _wand_mit_mast()
    m, w, _k, F_neu, _z = erzeugen(m0, (1, 0, 0), freie=namen, staebe=["Mast"])
    _alt_wie_vor_stand_33(m, w)
    g = m.load_cases[w.lastfall].geometrielasten[0].verlauf["geometrie"]
    F_alt = summe(m, w.lastfall)
    check("A10 nachgebildete alte Last: d = 1 m (Mast), sonst h, t gleich; ΣF gleich",
          abs(g["d"] - 1.0) < 1e-9 and np.allclose(F_alt, F_neu, rtol=1e-12, atol=1e-9),
          f"d {g['d']:.3f} m, ΣF {np.round(F_alt / 1000, 3)} kN")
    check("A10 kein Hinweis „Abmessungen“, Merkmal wind_abmessungen nicht betroffen",
          not wm.alte_abmessungen(m) and not rv.merkmal("wind_abmessungen").betrifft(m)
          and not any("Abmessungen" in z for z in wm.windlasten_hinweis(m)), str(wm.alte_abmessungen(m)))
    # Gegenprobe: andere Enden (t_max) bleiben ein Hinweis
    for gl in m.load_cases[w.lastfall].geometrielasten:
        if gl.verlauf.get("rolle") in wm.ROLLEN_NETTO:
            gl.verlauf["geometrie"]["t_max"] = 15.0
    check("A10 Gegenprobe: andere Wandenden (t_max 15 statt 10 m) bleiben ein Hinweis",
          wm.alte_abmessungen(m) == [(w.lastfall, "W1")], str(wm.alte_abmessungen(m)))


# ---------------------------------------------------------------------------
# Merkmal und Ladehinweis (Stand 43)
# ---------------------------------------------------------------------------
def test_merkmal(mv):
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("wind_freie_wand_ganz")
    check("Merkmal wind_freie_wand_ganz vorhanden (Stand 43, Fehlerkorrektur, am Modell)",
          mk is not None and mk.wechsel[-1].stand == 43 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.import_korrektur and bool(mk.modellgrund) and "neu erzeugen" in mk.vorschlag)
    check("VERFAHRENSSTAND mindestens 43", rv.VERFAHRENSSTAND >= 43, str(rv.VERFAHRENSSTAND))
    if mk is None:
        return
    # A8 alt: die untere Teilflaeche mit ihren eigenen Abmessungen (h = 1,5 m)
    zwei10, e2 = schalenwand([(0, 10, 0, 1.5), (0, 10, 1.5, 3)])
    neu8, w8, _k, F8, _z = erzeugen(zwei10, (1, 0, 0), freie=e2)
    alt8 = copy.deepcopy(neu8)
    for gl in alt8.load_cases[w8.lastfall].geometrielasten:
        geo = dict(gl.verlauf["geometrie"])
        kn = wm._flaechenknoten(alt8, str(gl.ziel))
        geo["h"] = float(alt8.nodes[sorted(kn)][:, 2].max()) - float(geo["z_boden"])
        gl.verlauf["geometrie"] = geo
    alt8.lasten_verteilen()
    F8a = summe(alt8, w8.lastfall)
    # A9 alt: Stirnflaeche M0 mit Nettolast quer zum Wind
    neu9, w9, _k, _F, _z = erzeugen(mv, (1, 0, 0), freie=["M0", "M1", "M2", "M3"])
    alt9 = copy.deepcopy(neu9)
    v = copy.deepcopy(alt9.load_cases[w9.lastfall].geometrielasten[0].verlauf)
    v["netto"] = [0.0, -1.0, 0.0]
    alt9.add_geometrielast("M0", 0.0, art="flaeche", richtung=None, case=w9.lastfall, verlauf=v)
    alt9.lasten_verteilen()
    F9a = summe(alt9, w9.lastfall)
    check("Merkmal: nachgebildete alte Lasten betroffen (Teilfläche h = 1,5 m; Stirn M0 quer)",
          mk.betrifft(alt8) and mk.betrifft(alt9) and _rel(F8a[0], F8[0]) > 0.02 and abs(F9a[1]) > 0.5e3,
          f"ΣF_x alt {F8a[0] / 1000:.3f} statt {F8[0] / 1000:.3f} kN; F_y alt {F9a[1] / 1000:.3f} kN")
    eine, *_r = erzeugen(mv, (1, 0, 0), freie=["M3", "M1"])
    drei, n3 = schalenwand([(0, 10, 0, 3), (10, 20, 0, 3), (20, 30, 0, 3)])
    drei, *_r = erzeugen(drei, (1, 0, 0), freie=n3)
    check("Merkmal: neu erzeugte Lasten nicht betroffen",
          not mk.betrifft(neu8) and not mk.betrifft(neu9) and not mk.betrifft(eine) and not mk.betrifft(drei))
    h8 = wm.windlasten_hinweis(alt8)
    h9 = wm.windlasten_hinweis(alt9)
    check("Ladehinweis nennt Wind und Lastfall und rät zum Neuerzeugen",
          any("W1" in z and w8.lastfall in z and "neu erzeugen" in z for z in h8)
          and any("W1" in z and w9.lastfall in z and "neu erzeugen" in z for z in h9),
          (str(h8) + str(h9))[:200])
    check("keine Zahl in wissenschaftlicher Schreibweise in den Hinweisen",
          not any(c in "".join(h8 + h9) for c in ("e+", "e-0")))


def main():
    test_a8()
    mv = volumenwand()
    test_a9(mv)
    test_a10()
    test_merkmal(mv)
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
