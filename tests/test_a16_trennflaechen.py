"""
Deckungsgleiche Trennflaechen als eine gemeinsame Flaeche vernetzen (Befund
A16 der Pruefagenten, Entscheidung des Anwenders vom 09.11.2026).

Haben zwei Volumenkoerper je eine eigene Flaeche ueber denselben Randlinien
(so kommt es aus RFEM) und nennt keine Kontaktbedingung die Stelle, vernetzt
mesher.koerper_vernetzen beide als EINE gemeinsame Flaeche - gemeinsame
Knoten. Bis dahin hingen die Koerper nur an den Knoten der Randlinien
zusammen; zwei Wuerfel uebereinander unter Zug verformten sich 52 % mehr als
ein Block. Die Geometrie bleibt, wie sie ist; jede Stelle steht im Protokoll.

Modelle (Stahl, E = 210 000 N/mm², Zug 10 N/mm² oben, Symmetrielager):
  * zwei Wuerfel 1 m uebereinander (abgebildete Quader, hex8 und hex20)
  * zwei Dreiecksprismen uebereinander (freies Netz tet4/tet10, Sweep,
    Arbeitsprozesse)
  * Wuerfel und darauf ein Koerper mit Satteldach (abgebildet neben frei)

Soll, auf zwei Wegen: geschlossen u_z(oben) = σ·L/E = 10 · 2000 / 210 000 =
0,095238 mm und σ_z = F/A = 10 N/mm² in jedem Element; dazu dasselbe Modell
mit EINER gemeinsamen Trennflaeche (anderer Eingabeweg) - Knoten fuer Knoten
dieselbe Verformung. Die Knotenzahlen im Protokoll werden an den Koordinaten
nachgezaehlt.

Nicht zusammengelegt wird: mit einer Kontaktbedingung an den Flaechen oder
nur an den Koerpern (Befund A17), bei Netzen, die nicht zusammenpassen
(Teilung 4 gegen 3; hex20 neben tet10) - dann steht der Grund im Protokoll -,
und wenn nur einer der beiden Koerper vernetzt wird. Die Abnahme warnt
„Trennfläche doppelt“ nur noch bei einem vorhandenen, getrennten Netz.

Aufruf:  python -m tests.test_a16_trennflaechen
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []
SIG = 10e6
E_STAHL = 210e9
U_SOLL = SIG * 2.0 / E_STAHL * 1e3          # mm, geschlossene Loesung σ·L/E


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def mm(x):
    """Zahl mit Komma, sechs Stellen (fuer die Ausgabe der Pruefung)."""
    return f"{x:.6f}".replace(".", ",")


# ------------------------------------------------------------------ Modelle

def _bau(form, eigene):
    """Zwei Koerper „Unten“ und „Oben“ mit der Trennflaeche bei z = 1 m -
    eigene Flaechen FugeU/FugeO ueber denselben Linien oder eine gemeinsame
    Flaeche Fuge. Rueckgabe: Modell, Lagerflaechen (u_x, u_y), Lastflaechen."""
    from statik3d.model import Model, Material
    m = Model("A16")
    m.add_material(Material.steel("S235"))
    z = [0]

    def L(a, c):
        z[0] += 1
        m.add_line(f"L{z[0]}", [a, c])
        return f"L{z[0]}"
    if form == "prismen":
        n = 3
        P = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    else:
        n = 4
        P = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]
    P = [[x, y, zz] for zz in (0.0, 1.0, 2.0) for x, y, _ in P]
    if form == "haus":
        P += [[0, 0.5, 2.5], [1, 0.5, 2.5]]
    m.add_nodes(np.array(P, float))
    R = [[L(o + i, o + (i + 1) % n) for i in range(n)] for o in (0, n, 2 * n)]
    V01 = [L(i, i + n) for i in range(n)]
    V12 = [L(i + n, i + 2 * n) for i in range(n)]
    m.add_flaeche("Boden", R[0], material="S235")
    if eigene:
        m.add_flaeche("FugeU", R[1], material="S235")
        m.add_flaeche("FugeO", R[1], material="S235")
        fu, fo = "FugeU", "FugeO"
    else:
        m.add_flaeche("Fuge", R[1], material="S235")
        fu = fo = "Fuge"
    un = [m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % n], R[1][i], V01[i]], material="S235").name
          for i in range(n)]
    ob = [m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % n], R[2][i], V12[i]], material="S235").name
          for i in range(n)]
    if form == "haus":
        first = L(12, 13)
        g0 = [L(8, 12), L(12, 11)]
        g1 = [L(9, 13), L(13, 10)]
        m.add_flaeche("DachS", [R[2][0], g1[0], first, g0[0]], material="S235")
        m.add_flaeche("DachN", [R[2][2], g0[1], first, g1[1]], material="S235")
        m.add_flaeche("GiebelW", [R[2][3], g0[0], g0[1]], material="S235")
        m.add_flaeche("GiebelO", [R[2][1], g1[0], g1[1]], material="S235")
        oben = ["DachS", "DachN", "GiebelW", "GiebelO"]
        last = ["DachS", "DachN"]
    else:
        m.add_flaeche("Dach", R[2], material="S235")
        oben = last = ["Dach"]
    m.add_koerper("Unten", ["Boden", fu] + un, material="S235")
    m.add_koerper("Oben", [fo] + oben + ob, material="S235")
    # die Seiten in y = 0 sind MU0/MO0, die in x = 0 die letzten (MU2 bzw. MU3)
    return m, {"ux": [f"MU{n - 1}", f"MO{n - 1}"], "uy": ["MU0", "MO0"]}, last


def _geometrie(m):
    """Abdruck der Geometrie: Knoten der Linien, Linien der Flaechen, Flaechen
    der Koerper (in ihrer Reihenfolge)."""
    return (tuple((n, tuple(int(k) for k in l.nodes)) for n, l in m.lines.items()),
            tuple((n, tuple(f.linien)) for n, f in m.flaechen.items()),
            tuple((n, tuple(k.flaechen)) for n, k in m.koerper.items()))


def _vernetzen(m, ordnung=1, sweep="aus", workers=1, h=0.25):
    from statik3d import mesher
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    m.netz.ordnung = ordnung
    m.netz.sweep = sweep
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, log, workers=workers)
    return log


def _lauf(form, eigene, ordnung=1, sweep="aus", workers=1, rechnen=True, vorher=None):
    from statik3d.model import DofBehaviour
    from statik3d import solver
    m, sym, last = _bau(form, eigene)
    m.add_load_case("LF1")
    m.case("LF1").gravity = [0.0, 0.0, 0.0]
    m.active_case = "LF1"
    for name, flaechen, d in (("X", sym["ux"], 0), ("Y", sym["uy"], 1), ("Z", ["Boden"], 2)):
        ss = m.add_surface_support(name=name)
        ss.flaechen = list(flaechen)
        ss.behaviour[d] = DofBehaviour("rigid")
    for f in last:
        m.add_geometrielast(f, -SIG, "flaeche", case="LF1")
    if vorher:
        vorher(m)
    geo = _geometrie(m)
    log = _vernetzen(m, ordnung, sweep, workers)
    res = None
    if rechnen:
        with contextlib.redirect_stdout(io.StringIO()):
            res = solver.solve_all(m, workers=1, combinations=False).cases["LF1"]
    return m, log, res, geo


def _fuge(m):
    """Knoten bei z = 1 m: (von Unten, von Oben, doppelte Orte) - gezaehlt an
    den Koordinaten und den Elementen der Koerper, nicht an den Flaechen."""
    X = np.asarray(m.nodes)
    auf = {i for i in range(len(X)) if abs(X[i, 2] - 1.0) < 1e-9}
    ku = {int(n) for e in m.koerper["Unten"].elemente for n in m.elements[e].nodes} & auf
    ko = {int(n) for e in m.koerper["Oben"].elemente for n in m.elements[e].nodes} & auf
    alle = sorted(ku | ko)
    doppelt = len(alle) - len({tuple(np.round(X[i], 9)) for i in alle})
    return ku, ko, doppelt


def _seitenknoten(m, flaeche):
    """(Knoten, Elemente) der Elementseiten, die bei der Flaeche stehen."""
    from statik3d.elements import solid as sl
    kn, els = set(), set()
    for e, s in m.flaechen[flaeche].randseiten or []:
        el = m.elements[int(e)]
        kn.update(int(el.nodes[j]) for j in sl.FLAECHEN[el.typ][int(s)])
        els.add(int(e))
    return kn, els


def _oben(m, res):
    X = np.asarray(m.nodes)
    top = np.where(np.abs(X[:, 2] - 2.0) < 1e-9)[0]
    return res.u[top, 2] * 1e3


def _gleich(ma, ra, mb, rb):
    """Groesster Unterschied der Verschiebung Knoten fuer Knoten (ueber die
    Koordinaten zugeordnet), mm; None, wenn die Netze verschiedene Knoten haben."""
    fa = {tuple(np.round(x, 8)): ra.u[i, :3] for i, x in enumerate(np.asarray(ma.nodes))}
    fb = {tuple(np.round(x, 8)): rb.u[i, :3] for i, x in enumerate(np.asarray(mb.nodes))}
    if len(fa) != ma.nn or len(fb) != mb.nn or set(fa) != set(fb):
        return None
    return max(float(np.abs(fa[k] - fb[k]).max()) for k in fa) * 1e3


def _zeilen(log, wort):
    return [z for z in log if wort in z]


def _einheitlich(tag, form, ordnung, sweep, typen, n_fuge, workers=1):
    """Eigene Trennflaechen ohne Kontakt gegen geschlossene Loesung und gegen
    das Modell mit gemeinsamer Flaeche; je Weg zwei Pruefungen."""
    from collections import Counter
    m, log, r, _g = _lauf(form, True, ordnung, sweep, workers)
    mg, _lg, rg, _g = _lauf(form, False, ordnung, sweep, workers)
    u = _oben(m, r)
    ku, ko, doppelt = _fuge(m)
    ist = dict(Counter(e.typ for e in m.elements))
    check(f"{tag}: u_z(oben) = σ·L/E = {mm(U_SOLL)} mm; Fuge {n_fuge} gemeinsame Knoten",
          set(ist) == set(typen) and abs(u.min() - U_SOLL) < 1e-6 and abs(u.max() - U_SOLL) < 1e-6
          and ku == ko and len(ku) == n_fuge and doppelt == 0
          and len(_zeilen(log, "Trennfläche zusammengelegt")) == 1,
          f"{mm(u.min())} … {mm(u.max())} mm, {sorted(ist)}, Fuge {len(ku)}/{len(ko)}/{len(ku & ko)}")
    d = _gleich(m, r, mg, rg)
    check("… zweiter Weg: Knoten für Knoten gleich dem Modell mit gemeinsamer Trennfläche",
          d is not None and d < 1e-9, f"größter Unterschied {mm(d) if d is not None else 'Netze verschieden'} mm")
    return m, log, r


# --------------------------------------------------------------- Pruefungen

def test_wuerfel():
    m, log, r = _einheitlich("A16 zwei Würfel (abgebildet, hex8), eigene Flächen ohne Kontakt",
                             "wuerfel", 1, "aus", ["hex8"], 25)
    S = np.array(list(r.solid_res.values()))[:, 2] / 1e6
    Rz = float(r.reactions[:, 2].sum()) / 1e6
    check("… σ_z = F/A = 10,000 N/mm² in jedem Element, ΣR_z = −10 MN",
          abs(S.min() - 10.0) < 1e-6 and abs(S.max() - 10.0) < 1e-6 and abs(Rz + 10.0) < 1e-9,
          f"σ_z {mm(S.min())} … {mm(S.max())}, ΣR_z {mm(Rz)} MN")
    z = _zeilen(log, "Trennfläche zusammengelegt")
    check("… das Protokoll nennt die Stelle: Körper Unten und Oben, Flächen FugeU und FugeO, 25 Knoten",
          len(z) == 1 and all(w in z[0] for w in ("Unten", "Oben", "FugeU", "FugeO", "25 gemeinsame Knoten"))
          and not z[0].startswith("WARNUNG"), z[0][:110] if z else "keine Zeile")
    _einheitlich("A16 zwei Würfel (hex20)", "wuerfel", 2, "aus", ["hex20"], 65)


def test_nur_im_netz():
    from statik3d import mesher
    m, sym, last = _bau("wuerfel", True)
    geo = _geometrie(m)
    m.netz.ziellaenge, m.netz.dichte, m.netz.ordnung, m.netz.sweep = 0.25, "eigene", 1, "aus"
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        aus = mesher.koerper_vernetzen(m, list(m.koerper.values()), log=log, cache={}, workers=1, ordnung=1)
    ku, eu = _seitenknoten(m, "FugeU")
    ko, eo = _seitenknoten(m, "FugeO")
    check("zusammengelegt nur im Netz: Rückgabe nennt die Stelle, Linien, Flächen und Körper unverändert",
          aus.get("zusammengelegt") == [("FugeU", "FugeO", "Unten", "Oben")] and _geometrie(m) == geo
          and m.koerper["Oben"].flaechen[0] == "FugeO",
          f"{aus.get('zusammengelegt')}, Oben: {m.koerper['Oben'].flaechen[:2]}")
    check("… jede der beiden Flächen trägt die 16 Seiten ihres Körpers, beide dieselben 25 Knoten",
          len(m.flaechen["FugeU"].randseiten) == 16 and len(m.flaechen["FugeO"].randseiten) == 16
          and eu <= set(m.koerper["Unten"].elemente) and eo <= set(m.koerper["Oben"].elemente)
          and ku == ko and len(ku) == 25,
          f"FugeU {len(m.flaechen['FugeU'].randseiten)} Seiten, FugeO {len(m.flaechen['FugeO'].randseiten)}, "
          f"gemeinsam {len(ku & ko)} von {len(ku)}/{len(ko)}")


def test_kontakt():
    """Mit Kontaktbedingung wird nichts zusammengelegt - der Unterschied zum
    Modell ohne Bedingung ist die Pruefung (25 gemeinsame Knoten gegen die 16
    der Randlinien oder weniger)."""
    m0, log0, _r, _g = _lauf("wuerfel", True, rechnen=False)
    n0 = len(_fuge(m0)[0] & _fuge(m0)[1])
    for tag, kw in (("an den Flächen", dict(flaechennamen=["FugeO"], gegenflaechen=["FugeU"])),
                    ("nur an den Körpern (A17)", dict(koerpernamen=["Oben"], gegenkoerper=["Unten"]))):
        def kontakt(m, _kw=kw):
            m.add_kontaktbedingung("K1", **_kw).standard_anwenden("Reibungsbehaftet")
        m, log, _r, geo = _lauf("wuerfel", True, rechnen=False, vorher=kontakt)
        ku, ko, _d = _fuge(m)
        check(f"Kontaktbedingung {tag}: nicht zusammengelegt (ohne Bedingung 25 gemeinsame Knoten)",
              n0 == 25 and len(ku) == 25 and len(ko) == 25 and len(ku & ko) <= 16
              and not _zeilen(log, "Trennfläche") and _geometrie(m) == geo,
              f"ohne {n0}, mit {len(ku & ko)} gemeinsam; Zeilen „Trennfläche“: {len(_zeilen(log, 'Trennfläche'))}")


def test_teilung():
    def teilung(m):
        m.koerper["Oben"].teilung = [3, 3, 3]
    m, log, r, geo = _lauf("wuerfel", True, vorher=teilung)
    ku, ko, _d = _fuge(m)
    z = _zeilen(log, "Trennfläche nicht zusammengelegt")
    zahlen = f"{len(ku)} Knoten von Unten, {len(ko)} von Oben, {len(ku & ko)} gemeinsam)"
    check("Teilung 4 gegen 3: nicht zusammengelegt, das Protokoll sagt warum (Körper, Flächen, Knotenzahlen)",
          len(z) == 1 and z[0].startswith("WARNUNG") and "passen" in z[0] and zahlen in z[0]
          and all(w in z[0] for w in ("Unten", "Oben", "FugeU", "FugeO"))
          and not _zeilen(log, "Trennfläche zusammengelegt"),
          f"gezählt {zahlen[:-1]}")
    from statik3d import diagnose as dg
    w = [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Trennfläche doppelt"]
    su, eu = _seitenknoten(m, "FugeU")
    so, eo = _seitenknoten(m, "FugeO")
    check("… Netz getrennt wie bisher, Geometrie unverändert; die Abnahme warnt und nennt das Neuvernetzen",
          (len(ku), len(ko)) == (25, 16) and su == ku and so == ko and _geometrie(m) == geo
          and len(eu) == 16 and len(eo) == 9 and m.nn == len({int(n) for e in m.elements for n in e.nodes})
          and len(w) == 1 and w[0].stufe == "WARNUNG"
          and "Neuvernetzen" in w[0].text and "FugeU" in w[0].text and "FugeO" in w[0].text,
          w[0].text[:90] if w else "keine Warnung")


def test_abnahme():
    from statik3d import diagnose as dg
    from statik3d import mesher

    def doppelt(m):
        return [b for b in dg.abnahme(m, warnungen=True) if b.pruefung == "Trennfläche doppelt"]
    m, _log, _r, _g = _lauf("wuerfel", True, rechnen=False)
    check("Abnahme: zusammengelegte Stelle - keine WARNUNG „Trennfläche doppelt“", not doppelt(m),
          f"{len(doppelt(m))} Warnungen")
    m, _s, _l = _bau("wuerfel", True)
    check("… unvernetztes Modell: keine Warnung (es gibt noch kein getrenntes Netz)",
          not dg._abnahme_deckungsgleiche_flaechen(m))
    alt = getattr(mesher, "TRENNFLAECHEN_ZUSAMMENLEGEN", None)
    mesher.TRENNFLAECHEN_ZUSAMMENLEGEN = False          # ein Netz wie bis zum 09.11.2026
    try:
        m, log, _r, _g = _lauf("wuerfel", True, rechnen=False)
    finally:
        mesher.TRENNFLAECHEN_ZUSAMMENLEGEN = alt
    ku, ko, _d = _fuge(m)
    w = doppelt(m)
    check("… vorhandenes altes, getrenntes Netz (16 von 25 Knoten gemeinsam): die WARNUNG bleibt",
          alt is True and len(ku & ko) == 16 and len(w) == 1 and w[0].stufe == "WARNUNG"
          and "Neuvernetzen" in w[0].text and w[0].objekt == "Unten/Oben",
          w[0].text[:90] if w else "keine Warnung")
    with contextlib.redirect_stdout(io.StringIO()):
        log = _vernetzen(m)
    ku, ko, _d = _fuge(m)
    check("… dasselbe Modell neu vernetzt: zusammengelegt, die Warnung ist weg",
          ku == ko and len(ku) == 25 and not doppelt(m) and len(_zeilen(log, "Trennfläche zusammengelegt")) == 1,
          f"gemeinsam {len(ku & ko)}")


def test_wege():
    _einheitlich("freies Netz (zwei Prismen, tet4)", "prismen", 1, "aus", ["tet4"], 17)
    _einheitlich("freies Netz (tet10)", "prismen", 2, "aus", ["tet10"], 51)
    _einheitlich("Sweep (hex8 und pent6)", "prismen", 1, "immer", ["hex8", "pent6"], 17)
    _einheitlich("freies Netz in zwei Arbeitsprozessen (tet4)", "prismen", 1, "aus", ["tet4"], 17, workers=2)
    # abgebildeter Wuerfel neben frei vernetztem Koerper: keine geschlossene Loesung (Satteldach) -
    # Vergleich mit dem Modell mit gemeinsamer Flaeche und Gleichgewicht ΣR_z = Last (Dachgrundriss 1 m²)
    m, log, r, _g = _lauf("haus", True)
    mg, _lg, rg, _g = _lauf("haus", False)
    ku, ko, doppelt = _fuge(m)
    d = _gleich(m, r, mg, rg)
    Rz = float(r.reactions[:, 2].sum()) / 1e6
    check("abgebildet neben frei (hex8/tet4): 25 gemeinsame Knoten, gleich dem Modell mit gemeinsamer Fläche",
          ku == ko and len(ku) == 25 and doppelt == 0 and d is not None and d < 1e-9
          and abs(Rz + 10.0) < 1e-6 and len(_zeilen(log, "Trennfläche zusammengelegt")) == 1,
          f"Fuge {len(ku & ko)} von {len(ku)}/{len(ko)}, Unterschied "
          f"{mm(d) if d is not None else 'Netze verschieden'} mm, ΣR_z {mm(Rz)} MN")
    # hex20 neben tet10: als eine Flaeche vernetzt passen die Seitenmitten nicht (die Zahlen des
    # Protokolls sind die des Versuchs - nachgezaehlt am Modell mit gemeinsamer Flaeche)
    m, log, _r, geo = _lauf("haus", True, ordnung=2, rechnen=False)
    mg, _lg, _r, _g = _lauf("haus", False, ordnung=2, rechnen=False)
    ku, ko, _d = _fuge(m)
    gu, go, _d = _fuge(mg)
    z = _zeilen(log, "Trennfläche nicht zusammengelegt")
    zahlen = f"{len(gu)} Knoten von Unten, {len(go)} von Oben, {len(gu & go)} gemeinsam)"
    check("hex20 neben tet10 (Seitenmitten passen nicht): nicht zusammengelegt, Grund im Protokoll",
          len(z) == 1 and "passen" in z[0] and zahlen in z[0] and _geometrie(m) == geo
          and gu != go and len(ku & ko) == 16 and not _zeilen(log, "Trennfläche zusammengelegt"),
          f"als eine Fläche: {zahlen[:-1]}; getrennt: {len(ku & ko)} gemeinsam (Randlinien)")


def test_nicht_im_lauf():
    from statik3d import mesher
    m, _s, _l = _bau("wuerfel", True)
    m.netz.ziellaenge, m.netz.dichte, m.netz.ordnung, m.netz.sweep = 0.25, "eigene", 1, "aus"
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        aus = mesher.koerper_vernetzen(m, [m.koerper["Oben"]], log=log, cache={}, workers=1, ordnung=1)
    z = _zeilen(log, "Trennfläche nicht zusammengelegt")
    check("nur ein Körper im Lauf: nicht zusammengelegt, das Protokoll nennt den fehlenden Körper",
          len(z) == 1 and z[0].startswith("WARNUNG") and "Körper Unten wird in diesem Lauf nicht mit vernetzt" in z[0]
          and not aus.get("zusammengelegt") and m.koerper["Oben"].elemente and not m.koerper["Unten"].elemente,
          z[0][60:190] if z else "keine Zeile")
    # verschiedene integrierte Knoten: die beiden Flaechen sind nicht dieselbe Vernetzungsaufgabe
    m, _s, _l = _bau("wuerfel", True)
    m.add_nodes(np.array([[0.5, 0.5, 1.0]]))
    m.flaechen["FugeO"].integrierte_knoten = [m.nn - 1]
    s = mesher.trennstellen(m)
    log = []
    stellen = mesher._trennstellen_des_laufs(m, list(m.koerper.values()), log)
    z = _zeilen(log, "Trennfläche nicht zusammengelegt")
    check("verschiedene integrierte Knoten in den beiden Flächen: Hindernis, im Protokoll genannt",
          len(s) == 1 and "integrierte" in s[0]["hindernis"] and not stellen and len(z) == 1
          and "integrierte Knoten" in z[0], z[0][60:200] if z else "keine Zeile")


def main():
    for t in (test_wuerfel, test_nur_im_netz, test_kontakt, test_teilung, test_abnahme, test_wege,
              test_nicht_im_lauf):
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
    sys.exit(main())
