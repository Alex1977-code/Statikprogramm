"""
Befund A'10 der Befundliste vom 14.11.2026 (zweite Runde), Teile des Agenten
„status“ (fix/k6-status), und die Entscheidung des Anwenders vom 14.11.2026
zur erhöhten freien Wand (Stand 56).

S1  Merkmal versatz_achsen_lotrecht (Stand 41): ein Stab mit Versatz, der
    nach Theorie III. Ordnung nur Eigengewicht trägt, ist betroffen – die
    Behebung A2 (Stablast über den mitgedrehten Arm) nimmt jede Stablast,
    auch das Eigengewicht. Kragarm 4 m in 8 Elementen, Versatz 0,5 m,
    ρ·A·g = 400 kN/m: Einspannmoment 3171,17 kNm (Versatzmodell und
    Kurzstabmodell gleich; vor Stand 41: 3061,42 kNm). Vor der Behebung
    zählte das Merkmal nur Stablasten (beam_loads): kein Status. Eine
    Ausnahme beim Lesen der Sollkräfte gilt als „möglicherweise betroffen“.
S2  Korrekturen am Import ohne ``modellgrund`` (Lagerreibung, Stabtypen,
    Vorspannung, Lastkategorien, Eigengewicht aus RFEM) tragen ihren Status
    auch nach „neu rechnen“ (rechenverfahren.modell_teile) – vor der
    Behebung verschwand er bis zum erneuten Öffnen der Ergebnisdatei
    (Kragarm Rundstahl 40 mm aus RFEM: ΣR_z 387,1 statt 394,6 N ohne Status).
    Mit und ohne ``modellgrund`` je genau einmal im Status.
S3  wind.alte_wandzonen prüft auch Windlasten ohne „abmessungen“ (Dateien vor
    Stand 33): freie Wand 30 × 3 m bei 75° zur Wandnormalen 82,73 statt
    94,44 kN (Hand: Zonen quer zum Wind mit l/h = b/h = 2,59: 82,66 kN;
    Zonen entlang der Wand mit l/h = 10: 94,44 kN), auch als Volumenwand.
S4  Erhöhte freie Wand (Entscheidung des Anwenders 14.11.2026): h der
    Tab. 7.9 ist die Höhe der Wand selbst, q_p bleibt in der Höhe der Wand.
    Wand 30 × 3 m auf z = 10 … 13 m: l/h = 10 statt 2,31; Abstand zum Boden
    ≥ h/4: Hinweis „Anzeigetafel nach 7.4.3“ im Protokoll. Ältere Lasten
    dieser Art: Merkmal Stand 56 (Korrektur am Modell „Windlasten neu
    erzeugen“).
S5  Commit-Angabe des Merkmals fuge_an_schalen: „d2711c7, fix/k2-nach“.

Sollwerte von Hand: q_p nach EN 1991-1-4 4.3–4.5 (Geländekategorie II,
Windzone 2), Tab. 7.9 geradlinig, Zonenlängen geschlossen; das Einspannmoment
aus zwei Programmwegen (Versatzmodell und Kurzstabmodell).

Aufruf:  python -m tests.test_status_luecken_1411
"""
from __future__ import annotations

import contextlib
import copy
import io
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

from statik3d import mesher, solver, wind as wm                 # noqa: E402
from statik3d import rechenverfahren as rv                      # noqa: E402
from statik3d.model import Material, Model, Section, ShellProp  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<88} {detail}")
    return bool(ok)


def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


# ---------------------------------------------------------------------------
# S1: Versatz, Theorie III, nur Eigengewicht
# ---------------------------------------------------------------------------
L_K, E_V, N_K = 4.0, 0.5, 8


def kragarm(art="versatz", rho=400e3 / (9.81 * 1e-2), gravity=True, theorie="III"):
    m = Model("K")
    m.add_material(Material("ST", E=210e9, nu=0.3, rho=rho, fy=355e6))
    m.add_material(Material("LEER", E=210e9, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=1e-4, Iz=1e-4, It=1.5e-4, zmax=0.1, ymax=0.05))
    m.add_section(Section("STARR", A=1.0, Iy=0.1, Iz=0.1, It=0.1, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    ids = [m.add_node(L_K * k / N_K, 0, 0) for k in range(N_K + 1)]
    if art == "versatz":
        for k in range(N_K):
            m.add_element("beam", [ids[k], ids[k + 1]], "ST", "Q", exzentrizitaet=[[0, 0, E_V], [0, 0, E_V]])
    else:
        st = [m.add_node(L_K * k / N_K, 0, E_V) for k in range(N_K + 1)]
        for k in range(N_K):
            m.add_element("beam", [st[k], st[k + 1]], "ST", "Q")
        for a, b in zip(ids, st):
            m.add_element("beam", [a, b], "LEER", "STARR")
    m.fix(ids[0], "all")
    m.case("LF1")
    m.load_cases["LF1"].gravity = [0.0, 0.0, -9.81] if gravity else [0.0, 0.0, 0.0]
    m.load_cases["LF1"].theorie = theorie
    return m, ids


def test_s1():
    from statik3d.theorie3 import solve_theorie3
    M = {}
    for art in ("versatz", "kurzstab"):
        m, ids = kragarm(art)
        r, inf = solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=20, imperfektionen=False, stabteilung=False)
        M[art] = -r.reactions[ids[0], 4] / 1e3
    check("S1 Kragarm Versatz 0,5 m, nur Eigengewicht 400 kN/m, Th III: Einspannmoment Versatz = Kurzstab "
          "= 3171,17 kNm", abs(M["versatz"] - M["kurzstab"]) < 0.01 and abs(M["versatz"] - 3171.17) < 0.01,
          f"Versatz {M['versatz']:.2f}, Kurzstab {M['kurzstab']:.2f} kNm (vor Stand 41: 3061,42 kNm)")
    mk = rv.merkmal("versatz_achsen_lotrecht")
    m, _ids = kragarm()
    check("S1 Merkmal versatz_achsen_lotrecht: Versatz + nur Eigengewicht nach Th III betroffen",
          mk is not None and mk.betrifft(m))
    datei = {mk_.name: rv._sicher(lambda: mk_.aktuell(m)) for mk_ in rv.MERKMALE}
    datei["versatz_achsen_lotrecht"] = "alt"
    check("S1 aeltere(): Ergebnisdatei mit Stand-40-Wert nennt versatz_achsen_lotrecht",
          "versatz_achsen_lotrecht" in [x[0].name for x in rv.aeltere(m, datei)])
    st = rv.bewerten(m, rv.merkmale_der_datei({"verfahren": {"stand": 40, "merkmale": {}}}, m))["betroffen"]
    check("S1 Ergebnisdatei Stand 40: Status nennt „Achsen, Stablast und Sollkraft an Stäben mit Versatz“",
          mk is not None and mk.titel in st, st[:120])
    # Gegenproben: ohne Dichte, ohne Schwere, nur Theorie I - nicht betroffen
    for text, kw in (("Dichte 0", {"rho": 0.0}), ("ohne Schwere", {"gravity": False}),
                     ("Theorie I", {"theorie": "I"})):
        m0, _ = kragarm(**kw)
        check(f"S1 Gegenprobe {text}: nicht betroffen", mk is not None and not mk.betrifft(m0))
    # Ausnahme beim Lesen der Sollkraefte: möglicherweise betroffen
    from statik3d import vorspannkraft as vk
    alt = vk.sollkraefte

    def _wirft(*_a, **_k):
        raise RuntimeError("Prüfung")
    vk.sollkraefte = _wirft
    try:
        m1, _ = kragarm(theorie="I")
        ok = mk is not None and mk.betrifft(m1)
    finally:
        vk.sollkraefte = alt
    check("S1 Ausnahme in sollkraefte (Stab mit Versatz): möglicherweise betroffen", ok)


# ---------------------------------------------------------------------------
# S2: Importkorrekturen nach „neu rechnen“
# ---------------------------------------------------------------------------
def test_s2():
    from tests.test_import_einheiten import _rf6_mit_wichte, _rz
    from statik3d.importers import import_file
    from statik3d import examples_lib as ex
    from statik3d.model import DofBehaviour
    tmp = tempfile.mkdtemp()
    try:
        p = _rf6_mit_wichte(os.path.join(tmp, "kragarm.rf6"))
        with contextlib.redirect_stdout(io.StringIO()):
            alt = import_file(p, log=[])
        alt.meta.pop("rfem_eigengewicht", None)          # so stand ein Modell vor dem 14.11.2026 da
        for lc_ in alt.load_cases.values():
            if np.any(lc_.gravity):
                lc_.gravity = [0.0, 0.0, -9.81]
        alt._rfem_eigengewicht_abw = None
        lc = next(lc for lc in alt.load_cases.values() if np.any(lc.gravity))
        mk = rv.merkmal("import_eigengewicht")
        with contextlib.redirect_stdout(io.StringIO()):
            an = solver.solve_all(alt, workers=1, combinations=False)
        A = math.pi * 0.020 ** 2
        rz = abs(_rz(an.cases[lc.name]))
        st = an.info.get("verfahren_betroffen", "") or ""
        check("S2 Eigengewicht aus RFEM (ρ·9,81): nach „neu rechnen“ Status „Eigengewicht aus RFEM“",
              mk is not None and mk.titel in st and "aus RFEM übernommen" in st,
              f"ΣR_z {rz:.1f} N (ρ·g·A·L {7850 * 9.81 * A * 4:.1f}, γ·A·L {78500 * A * 4:.1f}); {st[:90]!r}")
        b = rv.bewerten(alt, {}, an)["betroffen"]
        check("S2 … im Status beim Öffnen genau einmal (nicht doppelt)", b.count(mk.titel) == 1, b[:120])
        # mit modellgrund (der Agent „import“ setzt einen): ebenso, genau einmal
        mg = mk.modellgrund
        mk.modellgrund = mg or "Modell vor dem 14.11.2026 aus RFEM übernommen"
        try:
            st2 = rv.modell_betroffen(alt, an)
            b2 = rv.bewerten(alt, {}, an)["betroffen"]
        finally:
            mk.modellgrund = mg
        check("S2 … mit modellgrund: nach „neu rechnen“ und beim Öffnen je genau einmal",
              st2.count(mk.titel) == 1 and b2.count(mk.titel) == 1, st2[:120])
        # aeltere Importkorrekturen: Lagerreibung (μ = 0,1, RFEM-Vorgabe) und Stabtypen
        m = ex.frame_example()
        m.meta["quelle"] = "C:/x/rahmen.rf6"
        m.meta["rfem_zugstaebe"] = m.meta["rfem_seile"] = True
        m.supports[0].behaviour = {0: DofBehaviour(typ="rigid", mu=0.1, mu_ref=2)}
        with contextlib.redirect_stdout(io.StringIO()):
            an = solver.solve_all(m, design=False)
        st = an.info.get("verfahren_betroffen", "") or ""
        check("S2 Lagerreibung aus RFEM (μ = 0,1): nach „neu rechnen“ Status, Grund „aus RFEM übernommen“",
              "Lagerreibung aus RFEM" in st and "Modell vor dem 15.10.2026 aus RFEM übernommen" in st, st[:120])
        m.meta["rfem_lagerreibung"] = True
        check("S2 … mit Merkmal rfem_lagerreibung: kein Status", "Lagerreibung" not in rv.modell_betroffen(m))
        f = ex.truss_bridge_example()
        f.meta["quelle"] = "C:/x/fachwerk.rf6"
        f.meta["rfem_lagerreibung"] = True
        f.add_member("Gurt", [0], beta_y=1.0, beta_z=1.0)
        check("S2 Stabtypen aus RFEM: Status einer neuen Rechnung (modell_betroffen)",
              "Stabtypen aus RFEM" in rv.modell_betroffen(f), rv.modell_betroffen(f)[:120])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Wind: Handrechnung und Modelle
# ---------------------------------------------------------------------------
def qp_hand(z, v_b0=25.0, z0=0.05, zmin=2.0):
    z = max(z, zmin)
    ln = math.log(z / z0)
    v_m = 0.19 * ln * v_b0
    return (1.0 + 7.0 / ln) * 0.5 * 1.25 * v_m ** 2


def int_qp(z0, z1):
    z = np.linspace(z0, z1, 30001)
    q = np.array([qp_hand(t) for t in z])
    return float(np.sum(0.5 * (q[1:] + q[:-1]) * np.diff(z)))


ZEILE_3, ZEILE_5, ZEILE_10 = (2.3, 1.4, 1.2, 1.2), (2.9, 1.8, 1.4, 1.2), (3.4, 2.1, 1.7, 1.2)


def tab79(l_h):
    if l_h <= 3.0:
        return ZEILE_3
    if l_h >= 10.0:
        return ZEILE_10
    if l_h <= 5.0:
        f, a, b = (l_h - 3.0) / 2.0, ZEILE_3, ZEILE_5
    else:
        f, a, b = (l_h - 5.0) / 5.0, ZEILE_5, ZEILE_10
    return tuple(x + f * (y - x) for x, y in zip(a, b))


def zonen(L, h):
    halb = 0.5 * L
    return (2.0 * min(0.3 * h, halb), 2.0 * max(0.0, min(2.0 * h, halb) - 0.3 * h),
            2.0 * max(0.0, min(4.0 * h, halb) - 2.0 * h), 2.0 * max(0.0, halb - 4.0 * h))


def hand_wand(L, h_zonen, z0, z1, l_zonen=None, faktor=1.0):
    """ΣF senkrecht zur Wand: Zonen nach h_zonen, Zeile nach l/h_zonen, q_p von z0 bis z1;
    ``l_zonen``: Länge, in der die Zonen zählen, ``faktor``: Umrechnung auf die Wandlänge."""
    lz = L if l_zonen is None else l_zonen
    cp = tab79(lz / h_zonen)
    return sum(c * a * faktor for c, a in zip(cp, zonen(lz, h_zonen))) * int_qp(z0, z1)


def _vernetzen(m):
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log=[], workers=1)


def schalenwand(L, z0=0.0, z1=3.0):
    """Schale in der Ebene x = 0, Länge entlang y, von z0 bis z1."""
    m = Model("W")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))
    m.netz.teilung_uebersteuern = False
    m.add_nodes(np.array([[0, 0, z0], [0, L, z0], [0, L, z1], [0, 0, z1]], float))
    for i in range(4):
        m.add_line(f"L{i}", [i, (i + 1) % 4])
    m.add_flaeche("FW", [f"L{i}" for i in range(4)], material="S235", dicke="t10").teilung = \
        [int(round(L * 10)), int(round((z1 - z0) * 10))]
    _vernetzen(m)
    return m


def volumenwand(L=30.0, T=0.3, H=3.0):
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


def wind_erzeugen(m0, richtung, freie=(), z_boden=0.0):
    m = copy.deepcopy(m0)
    w = wm.Wind("W1", richtung=list(richtung), z_boden=z_boden, freie_waende=list(freie))
    with contextlib.redirect_stdout(io.StringIO()):
        kw = wm.lasten_erzeugen(m, w)
    return m, w, kw, summe(m, w.lastfall)


def vor_stand_33(m, w):
    """Die Windlasten wie ein Programmstand vor dem 12.11.2026 (Stand 33): Geometrie des
    Gebäudes ohne „abmessungen“, Zonen quer zum Wind."""
    alt = copy.deepcopy(m)
    geo = wm.gebaeude(w, alt)
    geo.pop("abmessungen", None)
    for gl in alt.load_cases[w.lastfall].geometrielasten:
        gl.verlauf["geometrie"] = dict(geo)
    with contextlib.redirect_stdout(io.StringIO()):
        alt.lasten_verteilen()
    return alt


def ohne(m, w, schluessel):
    alt = copy.deepcopy(m)
    for gl in alt.load_cases[w.lastfall].geometrielasten:
        for k in schluessel:
            gl.verlauf["geometrie"].pop(k, None)
    with contextlib.redirect_stdout(io.StringIO()):
        alt.lasten_verteilen()
    return alt


def _richtung(grad):
    return (math.cos(math.radians(grad)), math.sin(math.radians(grad)), 0.0)


# ---------------------------------------------------------------------------
# S3: Windlasten vor Stand 33, schräg angeströmt
# ---------------------------------------------------------------------------
def test_s3():
    d75 = _richtung(75.0)
    neu, w, _k, F_neu = wind_erzeugen(schalenwand(30.0), d75, freie=["FW"])
    alt = vor_stand_33(neu, w)
    F_alt = summe(alt, w.lastfall)
    c = math.cos(math.radians(75.0))
    soll_alt = hand_wand(30.0, 3.0, 0.0, 3.0, l_zonen=30.0 * c, faktor=1.0 / c)
    soll_neu = hand_wand(30.0, 3.0, 0.0, 3.0)
    check("S3 Wand 30 × 3 m bei 75°, Last vor Stand 33: ΣF_x = Hand (Zonen quer, l/h = 2,59)",
          _rel(F_alt[0], soll_alt) < 2e-3, f"{F_alt[0] / 1e3:.3f} kN, Hand {soll_alt / 1e3:.3f} kN")
    check("S3 … neu erzeugt: ΣF_x = Hand (Zonen entlang, l/h = 10)", _rel(F_neu[0], soll_neu) < 2e-3,
          f"{F_neu[0] / 1e3:.3f} kN, Hand {soll_neu / 1e3:.3f} kN")
    check("S3 alte_wandzonen erkennt die Last vor Stand 33 (ohne „abmessungen“)",
          wm.alte_wandzonen(alt) == [(w.lastfall, "W1")] and not wm.alte_wandzonen(neu), str(wm.alte_wandzonen(alt)))
    h = wm.windlasten_hinweis(alt)
    check("S3 Ladehinweis „Windlasten neu erzeugen“ mit Zonen quer zur Windrichtung",
          any("neu erzeugen" in z and "quer zur" in z and w.lastfall in z for z in h), str(h)[:160])
    mk = rv.merkmal("wind_freie_wand_hoehe")
    check("S3 Merkmal Stand 56 (Korrektur am Modell) betrifft die Last vor Stand 33, die neue nicht",
          mk is not None and mk.betrifft(alt) and not mk.betrifft(neu))
    mz = rv.merkmal("wind_freie_wand_zonen")
    check("S3 … nicht zugleich im Merkmal wind_freie_wand_zonen (Stand 49, Lasten mit Abmessungen der Wand)",
          mz is not None and not mz.betrifft(alt))
    st = rv.modell_betroffen(alt)
    check("S3 Status einer neuen Rechnung: „Windlasten … neu erzeugen“", mk is not None and mk.titel in st
          and "neu erzeugen" in st, st[:140])
    # Volumenwand
    neuv, wv, _k, _F = wind_erzeugen(volumenwand(30.0), d75, freie=["M1", "M3"])
    altv = vor_stand_33(neuv, wv)
    check("S3 Volumenwand 30 × 0,3 × 3 m bei 75°, Last vor Stand 33: erkannt",
          bool(wm.alte_wandzonen(altv)) and mk is not None and mk.betrifft(altv) and not mk.betrifft(neuv),
          str(wm.alte_wandzonen(altv)))
    # Gegenprobe: senkrecht angeströmt ist quer = entlang
    neu0, w0, _k, F0 = wind_erzeugen(schalenwand(10.0), (1, 0, 0), freie=["FW"])
    alt0 = vor_stand_33(neu0, w0)
    check("S3 Gegenprobe senkrecht angeströmt, vor Stand 33: kein Hinweis, gleiche Last",
          not wm.alte_wandzonen(alt0) and mk is not None and not mk.betrifft(alt0)
          and _rel(summe(alt0, w0.lastfall)[0], F0[0]) < 1e-9)


# ---------------------------------------------------------------------------
# S4: erhöhte freie Wand
# ---------------------------------------------------------------------------
def test_s4():
    neu, w, kw, F = wind_erzeugen(schalenwand(30.0, 10.0, 13.0), (1, 0, 0), freie=["FW"])
    soll = hand_wand(30.0, 3.0, 10.0, 13.0)
    soll_alt = hand_wand(30.0, 13.0, 10.0, 13.0)
    check("S4 Wand 30 × 3 m auf z = 10 … 13 m: ΣF_x = Hand mit h = 3 m (l/h = 10), q_p in 10 … 13 m",
          _rel(F[0], soll) < 2e-3, f"{F[0] / 1e3:.3f} kN, Hand {soll / 1e3:.3f} kN (mit h = 13 m: "
          f"{soll_alt / 1e3:.3f} kN)")
    satz = [z for z in wm.erlaeuterung(w, kw) if z.startswith("Freie Wand")]
    check("S4 Protokoll: h = 3,00 m, l/h = 10,00, c_p,net 3,40/2,10/1,70/1,20",
          len(satz) == 1 and "h = 3,00 m" in satz[0] and "l/h = 10,00" in satz[0]
          and "3,40/2,10/1,70/1,20" in satz[0], satz[0][:170] if satz else "")
    check("S4 Protokoll: Abstand zum Boden ≥ h/4 – Anzeigetafel nach 7.4.3, Rolle setzt der Anwender",
          len(satz) == 1 and "Anzeigetafel" in satz[0] and "7.4.3" in satz[0], satz[0][-200:] if satz else "")
    # Abstand unter h/4: h der Wand, aber kein Hinweis
    n2, w2, kw2, F2 = wind_erzeugen(schalenwand(30.0, 0.5, 3.5), (1, 0, 0), freie=["FW"])
    s2 = [z for z in wm.erlaeuterung(w2, kw2) if z.startswith("Freie Wand")]
    soll2 = hand_wand(30.0, 3.0, 0.5, 3.5)
    check("S4 Wand auf z = 0,5 … 3,5 m (Abstand < h/4): h = 3 m, kein Hinweis Anzeigetafel",
          _rel(F2[0], soll2) < 2e-3 and len(s2) == 1 and "Anzeigetafel" not in s2[0],
          f"{F2[0] / 1e3:.3f} kN, Hand {soll2 / 1e3:.3f} kN")
    # Wand am Boden: unverändert (bitgleich mit einer Last ohne h_wand)
    n0, w0, _k0, F0 = wind_erzeugen(schalenwand(30.0), (1, 0, 0), freie=["FW"])
    a0 = ohne(n0, w0, ("h_wand",))
    check("S4 Wand am Boden: Last mit und ohne h_wand bitgleich", np.array_equal(summe(a0, w0.lastfall), F0))
    mk = rv.merkmal("wind_freie_wand_hoehe")
    alt = ohne(neu, w, ("h_wand",))
    F_alt = summe(alt, w.lastfall)
    check("S4 ältere Last der erhöhten Wand (ohne h_wand): rechnet wie vorher mit h = 13 m",
          _rel(F_alt[0], soll_alt) < 2e-3, f"{F_alt[0] / 1e3:.3f} kN, Hand {soll_alt / 1e3:.3f} kN")
    ok = (mk is not None and mk.wechsel[-1].stand == 56 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.wechsel[-1].datum == "14.11.2026" and mk.import_korrektur and bool(mk.modellgrund)
          and "neu erzeugen" in mk.vorschlag)
    check("S4 Merkmal wind_freie_wand_hoehe: Stand 56, Fehlerkorrektur, Korrektur am Modell", ok)
    check("S4 … betrifft die ältere Last der erhöhten Wand, nicht die neue und nicht die Wand am Boden",
          mk is not None and mk.betrifft(alt) and not mk.betrifft(neu) and not mk.betrifft(a0))
    h = wm.windlasten_hinweis(alt)
    check("S4 Ladehinweis zur erhöhten Wand", any("neu erzeugen" in z and "Höhe der Wand" in z for z in h),
          str(h)[:160])
    check("S4 VERFAHRENSSTAND mindestens 56", rv.VERFAHRENSSTAND >= 56, str(rv.VERFAHRENSSTAND))


# ---------------------------------------------------------------------------
# S5: Commit-Angabe fuge_an_schalen
# ---------------------------------------------------------------------------
def test_s5():
    mk = rv.merkmal("fuge_an_schalen")
    check("S5 fuge_an_schalen: Commit „d2711c7, fix/k2-nach“",
          mk is not None and mk.wechsel[-1].commit == "d2711c7, fix/k2-nach",
          mk.wechsel[-1].commit if mk else "")


def main():
    for t in (test_s1, test_s2, test_s3, test_s4, test_s5):
        try:
            t()
        except Exception as ex:                       # noqa: BLE001 - vor der Behebung fehlen Teile
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
