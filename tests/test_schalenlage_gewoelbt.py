"""
Lage der Schalenelemente an gewoelbten Flaechen (Befunde A5, A6, A7 und A10
der Pruefagenten vom 14.11.2026, Korrektur Stand 42).

A5: Eine gewoelbte Flaeche mit mehreren nicht zusammenhaengenden Netzstuecken
wurde stueckweise gegen die gesamte Newell-Normale des Randes gerichtet. Am
Zylindersegment 300 Grad (R = 1 m, L = 2 m, 15 x 4 shell4, p = 10 kN/m²) mit
geloeschtem Streifen 40-60 Grad drehte das Stueck 0-40 Grad um:
Lastsumme (-47 496,8; -4 679,1; 0) statt (-21 785,3; 4 679,1; 0) N. Seitdem
entscheidet je Stueck der Umlauf des Vernetzers am Ort des Stuecks (seine
Kanten auf dem Rand der Flaeche), ein Stueck ohne Randkante folgt den
naechsten schon gerichteten Elementen; nur ebene Flaechen gegen die Normale.

A6: In einer Stellung drehte die Stellung nur die Knoten, nicht die
Stuetzpunkte der Boegen; im Situationsmodell richtete StaticSystem neu aus und
wendete alle Elemente (Zylindersegment 120 Grad, Stellung 180 Grad um x:
ΣR (17 320,5; -30 000; 0) statt (-17 320,5; 30 000; 0) N). Seitdem behaelt das
Situationsmodell die Elementlage des Grundmodells, und die Stellung dreht die
Liniengeometrie mit.

A7: Wasserdruck (Naeherungsformel, ohne Richtung) an einem Zylindermantel
270 Grad, Wasser innen bis 2,5 m: |F_x| 78,4 statt 43,4 kN - das Vorzeichen
kam aus dem Vergleich mit der gemittelten Flaechennormale. Seitdem aus der Lage
des Elements zur Flaeche (nach dem Ausrichten +1).

A10: Kontaktfuge Schale auf Schale meldete je nach Umlauf „durchdringend“
(Spalt 2 mm); Wind und Wasserdruck drehten Elemente ohne Meldung.

Zwei Wege je Zahl: Handrechnung (p L mal Sehne bzw. p mal Projektion) und das
Programm (Summe des Lastvektors bzw. der Auflagerkraefte; Elementsumme p A n).

Aufruf:  python -m tests.test_schalenlage_gewoelbt
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
R, L, P = 1.0, 2.0, 1.0e4
SPIEGEL = {"shell3": [0, 2, 1], "shell4": [0, 3, 2, 1], "shell6": [0, 2, 1, 5, 4, 3],
           "shell8": [0, 3, 2, 1, 7, 6, 5, 4]}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


@contextlib.contextmanager
def _still():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _v(x) -> str:
    return "(" + "; ".join(f"{float(c):.1f}" for c in x) + ")"


def _pkt(t, z):
    return (R * math.cos(t), R * math.sin(t), z)


def zylinder(winkel=300.0, nu=15, nv=4, ordnung=1, dreiecke=False):
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher
    m = Model("Z")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=355e6, alpha=1.2e-5))
    m.add_shell_prop(ShellProp("t", 0.01))
    w = math.radians(winkel)
    a0 = m.add_node(*_pkt(0, 0)); a1 = m.add_node(*_pkt(w, 0))
    b0 = m.add_node(*_pkt(0, L)); b1 = m.add_node(*_pkt(w, L))
    m.add_line("U", [a0, a1], "arc", punkte=[_pkt(0, 0), _pkt(w / 2, 0), _pkt(w, 0)])
    m.add_line("S1", [a1, b1])
    m.add_line("O", [b1, b0], "arc", punkte=[_pkt(w, L), _pkt(w / 2, L), _pkt(0, L)])
    m.add_line("S0", [b0, a0])
    f = m.add_flaeche("F", ["U", "S1", "O", "S0"], material="S", dicke="t", teilung=[nu, nv])
    with _still():
        mesher.mesh_flaeche(m, f, dreiecke=dreiecke, ordnung=ordnung)
    return m, f


def _mitte(m, e):
    return m.nodes[[int(k) for k in m.elements[e].nodes]].mean(axis=0)


def _winkel(m, e):
    X = _mitte(m, e)
    return math.degrees(math.atan2(X[1], X[0])) % 360.0


def _radial(m, e):
    """+1, wenn das Element radial nach aussen zeigt, sonst -1."""
    el = m.elements[e]
    X = m.nodes[[int(k) for k in el.nodes[:4]]]
    n = np.cross(X[2] - X[0], X[3] - X[1]) if el.typ in ("shell4", "shell8") \
        else np.cross(X[1] - X[0], X[2] - X[0])
    c = X.mean(axis=0)
    c[2] = 0.0
    return 1 if float(n @ c) > 0 else -1


def _lastsumme(m, fall=None):
    from statik3d import assemble as asm
    F = asm.load_vector(m, m.case(fall))
    return np.asarray(F, float).reshape(-1, 6)[:, :3].sum(axis=0)


def _hand_luecke(von_bis, vorzeichen):
    """p L (Summe der Sehnen) x e_z ueber die Stuecke [(t0, t1), ...] in Grad."""
    s = np.zeros(3)
    for t0, t1 in von_bis:
        s += np.asarray(_pkt(math.radians(t1), 0.0)) - np.asarray(_pkt(math.radians(t0), 0.0))
    return vorzeichen * P * L * np.cross(s, [0.0, 0.0, 1.0])


# --------------------------------------------------------------------------
# A5: gewoelbte Flaeche mit mehreren Netzstuecken
# --------------------------------------------------------------------------
def test_a5_luecke():
    from statik3d import schalenlage as SL, solver
    m, f = zylinder()
    m.add_geometrielast("F", P)
    m.lasten_verteilen()
    F0 = _lastsumme(m)
    s = 1.0 if float(F0 @ _hand_luecke([(0, 300)], 1.0)) > 0 else -1.0
    check("A5 ganze Flaeche: Lastsumme = Hand p L Sehne x z",
          np.allclose(F0, _hand_luecke([(0, 300)], s), atol=0.5), f"{_v(F0)} N")
    weg = [e for e in f.elemente if 40.0 < _winkel(m, e) < 60.0]
    m.elemente_loeschen(weg)
    m.lasten_verteilen()
    meld = SL.schalen_ausrichten(m)
    check("A5 Streifen 40-60 Grad geloescht: kein Element umgedreht", not meld, f"{meld}")
    lagen = {_radial(m, e) for e in f.elemente}
    check("A5 beide Stuecke gleich gerichtet (radial)", len(lagen) == 1, f"{lagen}")
    F1 = _lastsumme(m)
    soll = _hand_luecke([(0, 40), (60, 300)], s)
    check("A5 Lastsumme = Hand (-21 785,3; 4 679,1; 0) N",
          np.allclose(F1, soll, atol=0.5) and np.allclose(np.abs(soll[:2]), [21785.3, 4679.1], atol=0.1),
          f"Programm {_v(F1)}, Hand {_v(soll)}")
    for k in range(m.nn):
        if abs(m.nodes[k, 2]) < 1e-9:
            m.fix(k, [0, 1, 2, 3, 4, 5])
    with _still():
        r = solver.solve_static(m)
    S = np.asarray(r.reactions, float)[:, :3].sum(axis=0)
    check("A5 Rechnung: Summe der Auflagerkraefte = -Hand", np.allclose(S, -soll, atol=0.5),
          f"ΣR {_v(S)} N")


def test_a5_stueck_gespiegelt():
    """Ein ganzes Stueck vom Anwender gespiegelt: es kommt zum Umlauf des
    Randes zurueck (das ist die Lage, die der Vernetzer anlegt)."""
    from statik3d import schalenlage as SL
    for typ, ordnung, dreiecke in (("shell4", 1, False), ("shell8", 2, False), ("shell3", 1, True)):
        m, f = zylinder(ordnung=ordnung, dreiecke=dreiecke)
        vorher = {e: list(m.elements[e].nodes) for e in f.elemente}
        weg = [e for e in f.elemente if 40.0 < _winkel(m, e) < 60.0]
        m.elemente_loeschen(weg)
        # nach dem Loeschen sind die Nummern andere: Lage vor dem Spiegeln merken
        lage0 = {e: _radial(m, e) for e in f.elemente}
        stueck = [e for e in f.elemente if _winkel(m, e) < 40.0]
        for e in stueck:
            el = m.elements[e]
            el.nodes = [el.nodes[j] for j in SPIEGEL[el.typ]]
        meld = SL.schalen_ausrichten(m)
        zurueck = all(_radial(m, e) == lage0[e] for e in f.elemente)
        check(f"A5 {typ}: gespiegeltes Stueck 0-40 Grad zurueck zum Randumlauf",
              zurueck and len(meld) == 1 and f"{len(stueck)} Schalenelemente" in meld[0],
              f"{len(stueck)} gespiegelt; {meld[0][:70] if meld else '-'}")
        del vorher


def test_a5_insel():
    """Ein Stueck ohne Kante auf dem Rand der Flaeche (Insel in der Mitte):
    es folgt den naechsten schon gerichteten Elementen."""
    from statik3d import schalenlage as SL
    m, f = zylinder(nu=15, nv=6)
    z = {e: _mitte(m, e)[2] for e in f.elemente}
    w = {e: _winkel(m, e) for e in f.elemente}
    insel = [e for e in f.elemente if 100 < w[e] < 160 and 0.6 < z[e] < 1.4]
    ring = [e for e in f.elemente if 80 < w[e] < 180 and e not in insel]
    m.elemente_loeschen(ring)
    lage0 = {e: _radial(m, e) for e in f.elemente}
    insel = [e for e in f.elemente if 100 < _winkel(m, e) < 160 and 0.6 < _mitte(m, e)[2] < 1.4]
    for e in insel:
        el = m.elements[e]
        el.nodes = [el.nodes[j] for j in SPIEGEL[el.typ]]
    meld = SL.schalen_ausrichten(m)
    check("A5 Insel ohne Randkante, gespiegelt: zurueck zu den Nachbarstuecken",
          len(insel) > 0 and all(_radial(m, e) == lage0[e] for e in f.elemente),
          f"Insel {len(insel)} Elemente; {meld[0][:60] if meld else '-'}")


def test_a5_eben_unveraendert():
    """Ebene Flaeche mit zwei Stuecken: weiter gegen die Flaechennormale."""
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher, schalenlage as SL
    m = Model("P")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=355e6, alpha=1.2e-5))
    m.add_shell_prop(ShellProp("t", 0.01))
    ids = [m.add_node(*p) for p in [(0, 0, 0), (3, 0, 0), (3, 1, 0), (0, 1, 0)]]
    for j in range(4):
        m.add_line(f"L{j}", [ids[j], ids[(j + 1) % 4]])
    f = m.add_flaeche("P", [f"L{j}" for j in range(4)], material="S", dicke="t", teilung=[6, 2])
    with _still():
        mesher.mesh_flaeche(m, f, dreiecke=False, ordnung=1)
    weg = [e for e in f.elemente if 1.0 < _mitte(m, e)[0] < 2.0]
    m.elemente_loeschen(weg)
    rechts = [e for e in f.elemente if _mitte(m, e)[0] > 2.0]
    for e in rechts:
        el = m.elements[e]
        el.nodes = [el.nodes[j] for j in SPIEGEL[el.typ]]
    SL.schalen_ausrichten(m)
    nz = []
    for e in f.elemente:
        X = m.nodes[m.elements[e].nodes[:4]]
        nz.append(float(np.cross(X[2] - X[0], X[3] - X[1])[2]))
    check("A5 ebene Flaeche, zwei Stuecke, eines gespiegelt: alle zur Normale +z",
          all(v > 0 for v in nz), f"{len(rechts)} gespiegelt")


# --------------------------------------------------------------------------
# A6: Stellung mit gewoelbter Flaeche
# --------------------------------------------------------------------------
def test_a6_stellung():
    from statik3d.bridges.positions import Stellung, drehmatrix
    from statik3d.model import Situation
    from statik3d import schalenlage as SL, solver
    m, f = zylinder(winkel=120.0, nu=6, nv=3)
    lc0 = m.case().name
    m.add_geometrielast("F", P, case=lc0)
    m.add_load_case("LF2")
    m.add_geometrielast("F", P, case="LF2")
    m.lasten_verteilen()
    for k in range(m.nn):
        if abs(m.nodes[k, 0] - R) < 1e-9 and abs(m.nodes[k, 1]) < 1e-9:
            m.fix(k, [0, 1, 2, 3, 4, 5])
    Rm = drehmatrix((1.0, 0.0, 0.0), math.pi)
    st = Stellung("S180", 180.0, "umgeklappt", dreh_achse=(1.0, 0.0, 0.0), dreh_punkt=(0.0, 0.0, 0.0),
                  dreh_winkel=180.0, faelle=["LF2"],
                  dreh_gruppen=sorted({m.elements[e].group for e in f.elemente}))
    # die Stellung dreht die Liniengeometrie mit
    ms = m.copy()
    st.anwenden(ms, m)
    p_alt = np.asarray(m.lines["U"].geometrie["punkte"][1], float)
    p_neu = np.asarray(ms.lines["U"].geometrie["punkte"][1], float)
    N0 = SL.flaechennormale(m, f)
    Ns = SL.flaechennormale(ms, ms.flaechen["F"])
    check("A6 Stellung dreht die Stuetzpunkte des Bogens mit",
          np.allclose(p_neu, Rm @ p_alt, atol=1e-12), f"{np.round(p_neu, 4)}")
    check("A6 Flaechennormale in der Stellung = R mal Grundstellung",
          np.allclose(Ns, Rm @ N0, atol=1e-9), f"{np.round(Ns, 3)}")
    check("A6 Grundmodell unveraendert (Stuetzpunkte)",
          np.allclose(np.asarray(m.lines["U"].geometrie["punkte"][1], float), _pkt(math.radians(60), 0)))
    m.stellungen.append(st)
    m.situationen["U"] = Situation("U", "S180", [], "umgeklappt")
    m.load_cases["LF2"].situation = "U"
    with _still():
        an = solver.solve_all(m, combinations=False)
    alle = an.all_results()
    R0 = np.asarray(alle[lc0].reactions, float)[:, :3].sum(axis=0)
    R2 = np.asarray(alle["LF2"].reactions, float)[:, :3].sum(axis=0)
    hand = -_hand_luecke([(0, 120)], 1.0 if float(R0 @ _hand_luecke([(0, 120)], -1.0)) > 0 else -1.0)
    check("A6 Grundstellung: ΣR = Hand", np.allclose(R0, hand, atol=0.5), f"{_v(R0)}, Hand {_v(hand)}")
    check("A6 Situation 180 Grad: ΣR = R mal Grundstellung (-17 320,5; 30 000; 0) N",
          np.allclose(R2, Rm @ R0, atol=0.5) and np.allclose(np.abs(R2[:2]), [17320.5, 30000.0], atol=0.1),
          f"{_v(R2)}, erwartet {_v(Rm @ R0)}")
    # das Situationsmodell behaelt die Elementlage des Grundmodells
    from statik3d.situationen import situationsmodell
    m_s, _a, _log = situationsmodell(m, "U")
    gleich = all(list(m_s.elements[e].nodes) == list(m.elements[e].nodes) for e in f.elemente)
    with _still():
        meld = SL.schalen_ausrichten(m_s)
    gleich2 = all(list(m_s.elements[e].nodes) == list(m.elements[e].nodes) for e in f.elemente)
    check("A6 Situationsmodell: Elementlage des Grundmodells, kein Umdrehen",
          gleich and gleich2 and not meld, f"{meld}")


def test_a6_stellungsreihe():
    """Dieselbe Stellung ueber Stellungsreihe.rechnen (Stellung.modell)."""
    from statik3d.bridges.positions import Stellung, Stellungsreihe, drehmatrix
    m, f = zylinder(winkel=120.0, nu=6, nv=3)
    lc0 = m.case().name
    m.add_geometrielast("F", P, case=lc0)
    m.lasten_verteilen()
    for k in range(m.nn):
        if abs(m.nodes[k, 0] - R) < 1e-9 and abs(m.nodes[k, 1]) < 1e-9:
            m.fix(k, [0, 1, 2, 3, 4, 5])
    reihe = Stellungsreihe(m, "R")
    reihe.add(Stellung("S180", 180.0, "umgeklappt", dreh_achse=(1.0, 0.0, 0.0), dreh_punkt=(0.0, 0.0, 0.0),
                       dreh_winkel=180.0, faelle=[lc0],
                       dreh_gruppen=sorted({m.elements[e].group for e in f.elemente})))
    with _still():
        reihe.rechnen(kombinationen=False)
    e = reihe.ergebnisse[0]
    R2 = np.asarray(e.reaktion, float)[:, :3].sum(axis=0) if e.reaktion is not None else np.zeros(3)
    soll = drehmatrix((1.0, 0.0, 0.0), math.pi) @ _hand_luecke([(0, 120)], -1.0)
    # Vorzeichen der Grundstellung aus der Rechnung selbst (Weg 2)
    from statik3d import solver
    with _still():
        r0 = solver.solve_static(m, case=lc0)
    R0 = np.asarray(r0.reactions, float)[:, :3].sum(axis=0)
    Rm = drehmatrix((1.0, 0.0, 0.0), math.pi)
    check("A6 Stellungsreihe 180 Grad: ΣR = R mal Grundstellung",
          np.allclose(R2, Rm @ R0, atol=0.5) and np.allclose(np.abs(R2[:2]), np.abs(soll[:2]), atol=0.5),
          f"{_v(R2)}, erwartet {_v(Rm @ R0)}")


# --------------------------------------------------------------------------
# A7: Wasserdruck an einer Schale mit mehr als 180 Grad Bogen
# --------------------------------------------------------------------------
def _mantel270():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher
    phi = math.radians(135.0)
    m = Model("Mantel270")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t10", 0.010))

    def pt(t, z):
        return (math.cos(t), math.sin(t), z)
    pu = m.add_node(*pt(-phi, 0.0)); qu = m.add_node(*pt(phi, 0.0))
    po = m.add_node(*pt(-phi, 3.0)); qo = m.add_node(*pt(phi, 3.0))
    m.add_line("U", [pu, qu], "arc", punkte=[pt(-phi, 0.0), pt(0.0, 0.0), pt(phi, 0.0)])
    m.add_line("O", [qo, po], "arc", punkte=[pt(phi, 3.0), pt(0.0, 3.0), pt(-phi, 3.0)])
    m.add_line("V1", [qu, qo])
    m.add_line("V2", [po, pu])
    m.add_flaeche("M", ["U", "V1", "O", "V2"], material="S235", dicke="t10")
    m.netz.ziellaenge = 0.15
    with _still():
        mesher.modell_vernetzen(m, log=[], workers=1)
    return m


def test_a7_mantel270():
    from statik3d import solver
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    hand = 1.0 * 2 * math.sin(math.radians(135.0)) * 0.5 * 1000.0 * 9.81 * 2.5 ** 2
    for seite in (1, -1):
        m = _mantel270()
        wd = Wasserdruck("W1", flaechen=["M"], h_ow=2.5, verfahren="analytisch", seite=seite, absenkung=False)
        with _still():
            lasten_erzeugen(m, wd)
        lc = m.load_cases[wd.lastfall]
        F = np.asarray(solver.case_loads(m, {wd.lastfall: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)
        S2 = np.zeros(3)
        richtung = set()
        for fl in lc.face_loads:
            e = m.elements[int(fl.elem)]
            X = m.nodes[[int(k) for k in e.nodes[:4]]]
            n = np.cross(X[2] - X[0], X[3] - X[1]) if e.typ in ("shell4", "shell8") \
                else np.cross(X[1] - X[0], X[2] - X[0])
            A = 0.5 * float(np.linalg.norm(n))
            k = float(fl.p) * A * n / np.linalg.norm(n)
            S2 += k
            c = X[:3].mean(axis=0)
            if abs(float(k @ np.array([c[0], c[1], 0.0]))) > 1e-9:
                richtung.add(1 if float(k @ np.array([c[0], c[1], 0.0])) > 0 else -1)
        check(f"A7 seite {seite:+d}: alle Elementlasten radial in einer Richtung", len(richtung) == 1,
              f"{richtung}")
        check(f"A7 seite {seite:+d}: Lastvektor |F_x| = Hand 43 354,5 N, F_y = F_z = 0",
              abs(abs(F[0]) - hand) < 0.005 * hand and abs(F[1]) < 0.005 * hand and abs(F[2]) < 1.0,
              f"Lastvektor {_v(F)}, Hand {hand:.1f}")
        check(f"A7 seite {seite:+d}: Elementsumme p A n = Lastvektor (zweiter Weg)",
              abs(abs(S2[0]) - hand) < 0.01 * hand and float(S2[0] * F[0]) > 0, f"{_v(S2)}")
        # Befund A'11 (14.11.2026, Beleg b8): die Pruefung bestand auch mit
        # vertauschter Wasserseite. Die Flaechennormale zeigt hier radial nach
        # aussen; seite +1 = Wasser aussen, Druck nach innen: F_x = −43 354,5 N,
        # seite −1 (innen): +43 354,5 N
        check(f"A7 seite {seite:+d}: Vorzeichen F_x = {-seite * hand:+.1f} N (Wasser "
              f"{'aussen' if seite > 0 else 'innen'}), Lastvektor und Elementsumme",
              abs(F[0] + seite * hand) < 0.005 * hand and abs(S2[0] + seite * hand) < 0.01 * hand,
              f"Lastvektor F_x {F[0]:.1f}, Elementsumme {S2[0]:.1f}")


# --------------------------------------------------------------------------
# A'7 (14.11.2026, zweite Runde): gewoelbte Flaeche aus EINEM Netzstueck mit
# Loch oder Kerbe - der Randumlauf entscheidet, nicht Stokes gegen den Rand
# --------------------------------------------------------------------------
def _radial_aussen_summe(m, f, s):
    """Zweiter Weg: Summe der Vektorflaechen der Elemente, je Element radial
    nach aussen gerichtet (unabhaengig von der Knotenfolge), mal s p."""
    geo = np.zeros(3)
    for e in f.elemente:
        X = m.nodes[[int(k) for k in m.elements[e].nodes[:4]]]
        v = 0.5 * np.cross(X[2] - X[0], X[3] - X[1])
        c = X.mean(axis=0)
        c[2] = 0.0
        geo += v if float(v @ c) > 0 else -v
    return s * P * geo


def _sehne_z(t0, t1):
    c = np.asarray(_pkt(math.radians(t1), 0.0)) - np.asarray(_pkt(math.radians(t0), 0.0))
    return np.cross(c, [0.0, 0.0, 1.0])


def test_a7s_loch_kerbe():
    """Zylinder 300 Grad, 15 x 6 shell4, p = 10 kN/m² senkrecht; ein grosses
    Loch bzw. eine Kerbe von unten, das Netz bleibt EIN Stueck. Vor der
    Behebung drehte Stokes (Vektorflaeche gegen die Normale des Randes, die das
    Loch nicht kennt) alle Elemente um: Lastsumme (−370,5; 4 844,5; 0) statt
    (370,5; −4 844,5; 0) N. Hand: s p (L Sehne(0-300) − h Sehne(Loch)) x e_z."""
    from statik3d import schalenlage as SL, solver
    for art, auswahl, soll in (
            ("Loch 90-210 Grad, z 1/3..5/3", lambda th, z: 90 < th < 210 and 1 / 3 < z < 5 / 3, (370.5, -4844.5)),
            ("Kerbe von unten 90-210 Grad, z 0..5/3", lambda th, z: 90 < th < 210 and z < 5 / 3,
             (4793.3, -8555.7))):
        m, f = zylinder(nu=15, nv=6)
        m.add_geometrielast("F", P)
        m.lasten_verteilen()
        F0 = _lastsumme(m)
        s = 1.0 if float(F0 @ _hand_luecke([(0, 300)], 1.0)) > 0 else -1.0
        lage0 = {_radial(m, e) for e in f.elemente}
        weg = [e for e in f.elemente if auswahl(_winkel(m, e), _mitte(m, e)[2])]
        kn = sorted({int(k) for e in weg for k in m.elements[e].nodes})
        th = [math.degrees(math.atan2(m.nodes[k, 1], m.nodes[k, 0])) % 360.0 for k in kn]
        zz = [float(m.nodes[k, 2]) for k in kn]
        m.elemente_loeschen(weg)
        idx = sorted(int(e) for e in f.elemente)
        C, ne = SL._ecken(m, idx)
        n_st = len(SL._stuecke(m, idx, SL._vektorflaechen(m, idx, C, ne), C, ne)[1])
        m.lasten_verteilen()
        with _still():
            meld = SL.schalen_ausrichten(m)
        lage1 = {_radial(m, e) for e in f.elemente}
        check(f"A'7 {art}: ein Netzstueck, kein Element umgedreht, Lage wie vorher",
              n_st == 1 and not meld and lage1 == lage0, f"Stuecke {n_st}, Lage {lage0} -> {lage1}, {meld}")
        F1 = _lastsumme(m)
        hand = s * P * (L * _sehne_z(0, 300) - (max(zz) - min(zz)) * _sehne_z(min(th), max(th)))
        geo = _radial_aussen_summe(m, f, s)
        check(f"A'7 {art}: Lastsumme = Hand ({soll[0]:.1f}; {soll[1]:.1f}; 0) N = Elementflaechen radial "
              "(zweiter Weg)",
              np.allclose(F1, hand, atol=0.5) and np.allclose(geo, hand, atol=0.5)
              and np.allclose(hand[:2], soll, atol=0.1),
              f"Programm {_v(F1)}, Hand {_v(hand)}, Weg 2 {_v(geo)}")
        for k in range(m.nn):
            if abs(m.nodes[k, 2] - L) < 1e-9:
                m.fix(k, [0, 1, 2, 3, 4, 5])
        with _still():
            r = solver.solve_static(m)
        S = np.asarray(r.reactions, float)[:, :3].sum(axis=0)
        check(f"A'7 {art}: Rechnung ΣR = −Hand", np.allclose(S, -hand, atol=0.5), f"ΣR {_v(S)} N")


def test_a7s_ganz_unveraendert():
    """Die Regel bleibt fuer die ganze Flaeche: nichts umgedreht; ganz
    gespiegelt (ein Stueck) kommt sie zum Randumlauf zurueck."""
    from statik3d import schalenlage as SL
    m, f = zylinder(nu=15, nv=6)
    lage0 = {e: _radial(m, e) for e in f.elemente}
    with _still():
        meld0 = SL.schalen_ausrichten(m)
    for e in f.elemente:
        el = m.elements[e]
        el.nodes = [el.nodes[j] for j in SPIEGEL[el.typ]]
    with _still():
        meld1 = SL.schalen_ausrichten(m)
    check("A'7 ganze Flaeche: nichts umgedreht; ganz gespiegelt: alle zurueck",
          not meld0 and len(meld1) == 1 and all(_radial(m, e) == lage0[e] for e in f.elemente),
          f"{meld1[0][:60] if meld1 else '-'}")


def test_a7s_wasser_loch():
    """Wasserdruck analytisch am Mantel 270 Grad (R = 1 m, H = 3 m, OW 2,5 m)
    mit grossem Loch −60..60 Grad, z 0,2..2,8 m; das Netz bleibt ein Stueck.
    Vor der Behebung drueckte das Wasser von der falschen Seite (Radialsumme
    +90 902,9 statt −92 709,8 N bei seite +1). Hand radial: −seite ρg ∫(h−z)dz
    mal Bogen (ganz minus Loch); zweiter Weg: Summe p A n der Elementlasten."""
    from statik3d import schalenlage as SL, solver
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    rho_g, hw = 1000.0 * 9.81, 2.5
    phi = math.radians(135.0)

    def integral(z0, z1):
        z1 = min(z1, hw)
        return 0.0 if z1 <= z0 else rho_g * ((hw * z1 - z1 ** 2 / 2) - (hw * z0 - z0 ** 2 / 2))
    for seite in (1, -1):
        m = _mantel270()
        f = m.flaechen["M"]

        def wk(e):
            X = _mitte(m, e)
            return math.degrees(math.atan2(X[1], X[0]))
        weg = [e for e in f.elemente if abs(wk(e)) < 60.0 and 0.2 < _mitte(m, e)[2] < 2.8]
        kn = {int(k) for e in weg for k in m.elements[e].nodes}
        th = [math.degrees(math.atan2(m.nodes[k, 1], m.nodes[k, 0])) for k in kn]
        zz = [float(m.nodes[k, 2]) for k in kn]
        m.elemente_loeschen(weg)
        idx = sorted(int(e) for e in f.elemente)
        C, ne = SL._ecken(m, idx)
        n_st = len(SL._stuecke(m, idx, SL._vektorflaechen(m, idx, C, ne), C, ne)[1])
        wd = Wasserdruck("W1", flaechen=["M"], h_ow=hw, verfahren="analytisch", seite=seite, absenkung=False)
        with _still():
            kw = lasten_erzeugen(m, wd)
        F = np.asarray(solver.case_loads(m, {wd.lastfall: 1.0}, None)[0], float).reshape(-1, 6)[:, :3].sum(axis=0)
        radial, aus, ein = 0.0, 0, 0
        S2 = np.zeros(3)
        for fl in m.load_cases[wd.lastfall].face_loads:
            el = m.elements[int(fl.elem)]
            X = m.nodes[[int(k) for k in el.nodes[:4]]]
            v = 0.5 * np.cross(X[2] - X[0], X[3] - X[1]) if el.typ in ("shell4", "shell8") \
                else 0.5 * np.cross(X[1] - X[0], X[2] - X[0])
            k = float(fl.p) * v
            S2 += k
            c = X.mean(axis=0)
            er = np.array([c[0], c[1], 0.0]) / math.hypot(c[0], c[1])
            radial += float(k @ er)
            aus += float(k @ er) > 0
            ein += float(k @ er) < 0
        hand = -seite * (integral(0.0, hw) * 2 * phi - integral(min(zz), max(zz)) * math.radians(max(th) - min(th)))
        check(f"A'7 Wasser am Mantel 270 Grad mit Loch, seite {seite:+d}: ein Stueck, kein Umdrehen, alle "
              f"Elementlasten {'nach innen' if seite > 0 else 'nach aussen'}",
              n_st == 1 and not kw.get("schalenlage") and (ein if seite > 0 else aus) > 0
              and (aus if seite > 0 else ein) == 0,
              f"Stuecke {n_st}, nach aussen {aus}, nach innen {ein}, {kw.get('schalenlage')}")
        check(f"A'7 Wasser mit Loch, seite {seite:+d}: Radialsumme = Hand {hand:.1f} N (3 %, Sehnen statt "
              "Bogen), Lastvektor = Summe p A n",
              abs(radial - hand) < 0.03 * abs(hand) and np.allclose(F, S2, atol=1.0),
              f"Programm {radial:.1f} N, Lastvektor {_v(F)}, p A n {_v(S2)}")


# --------------------------------------------------------------------------
# A10: Meldungen
# --------------------------------------------------------------------------
def test_a10_fuge_schale_schale():
    from statik3d.model import Model, Material, ShellProp, DofBehaviour
    from statik3d import mesher, fugen
    for oben_auf in (False, True):
        for unten_auf in (False, True):
            m = Model("SS")
            m.add_material(Material.steel("S235"))
            m.add_shell_prop(ShellProp("t", 0.010))

            def platte(name, z, auf):
                ecken = [(0, 0, z), (1, 0, z), (1, 1, z), (0, 1, z)]
                if not auf:
                    ecken = ecken[::-1]
                ids = [m.add_node(*p) for p in ecken]
                for j in range(4):
                    m.add_line(f"{name}{j}", [ids[j], ids[(j + 1) % 4]])
                f = m.add_flaeche(name, [f"{name}{j}" for j in range(4)], material="S235", dicke="t")
                f.teilung = [4, 4]
            platte("Unten", 0.0, unten_auf)
            platte("Oben", 0.002, oben_auf)
            m.add_load_case("LF1", "Q")
            with _still():
                mesher.modell_vernetzen(m, log=[], workers=1)
            kb = {0: DofBehaviour("rigid"), 1: DofBehaviour("rigid"), 2: DofBehaviour("rigid", failure="zug")}
            m.add_kontaktbedingung("K", flaechennamen=["Oben"], gegenflaechen=["Unten"], behaviour=kb)
            log = []
            with _still():
                fugen.kontaktfugen_ausfuehren(m, log)
            z = " ".join(x for x in log if "Kontaktbedingung K" in x)
            check(f"A10 Fuge Schale/Schale (Oben {'+z' if oben_auf else '-z'}, Unten {'+z' if unten_auf else '-z'}): "
                  "Spalt 2 mm, nicht durchdringend",
                  "durchdringend" not in z and "größter 2.00 mm" in z, z[z.find("Spalt"):z.find("Spalt") + 70])


def _wand_gespiegelt():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import mesher
    m = Model("Haut")
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("t", 0.010))
    ids = [m.add_node(*p) for p in [(0, 0, 0), (0, 3, 0), (0, 3, 5), (0, 0, 5)]]
    for j in range(4):
        m.add_line(f"L{j}", [ids[j], ids[(j + 1) % 4]])
    f = m.add_flaeche("Haut", [f"L{j}" for j in range(4)], material="S235", dicke="t", teilung=[3, 5])
    m.add_load_case("LF1", "Q")
    with _still():
        mesher.mesh_flaeche(m, f, dreiecke=False, ordnung=1)
    e = f.elemente[4]
    el = m.elements[e]
    el.nodes = [el.nodes[j] for j in SPIEGEL[el.typ]]
    return m, e


def test_a10_meldung_generatoren():
    from statik3d import wasserdruck as wdm, wind as wm
    m, e = _wand_gespiegelt()
    wd = wdm.Wasserdruck("WD", flaechen=["Haut"], h_ow=4.0, absenkung=False, verfahren="analytisch")
    with _still():
        kw = wdm.lasten_erzeugen(m, wd)
    z = list(kw.get("schalenlage") or [])
    check("A10 Wasserdruck: Kennwerte nennen das Umdrehen (kw['schalenlage'])",
          len(z) == 1 and "umgedreht" in z[0] and f"Element {e}" in z[0], f"{z}")
    m, e = _wand_gespiegelt()
    w = wm.Wind("W1", zone=2, profil="II", richtung=[1.0, 0.0, 0.0], freie_waende=["Haut"])
    with _still():
        kw = wm.lasten_erzeugen(m, w)
    z = list(kw.get("schalenlage") or [])
    check("A10 Wind: Kennwerte nennen das Umdrehen (kw['schalenlage'])",
          len(z) == 1 and "umgedreht" in z[0] and f"Element {e}" in z[0], f"{z}")


# --------------------------------------------------------------------------
# Verfahrenstabelle
# --------------------------------------------------------------------------
def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("schalenlage_gewoelbt")
    check("Merkmal schalenlage_gewoelbt mit Stand 42, VERFAHRENSSTAND >= 42",
          mk is not None and any(w.stand == 42 for w in mk.wechsel) and rv.VERFAHRENSSTAND >= 42,
          f"Stand {rv.VERFAHRENSSTAND}")
    if mk is None:
        check("… betroffen: gewoelbt mit zwei Stuecken ja, gewoelbt ganz nein, leeres Modell nein", False,
              "kein Merkmal")
        check("… betroffen: Situation mit Stellung an gewoelbter Flaeche ja, Wasserdruck am Mantel ja", False,
              "kein Merkmal")
        return
    m_luecke, f = zylinder()
    m_luecke.elemente_loeschen([e for e in f.elemente if 40.0 < _winkel(m_luecke, e) < 60.0])
    m_ganz, _f = zylinder()
    from statik3d.model import Model
    check("… betroffen: gewoelbt mit zwei Stuecken ja, gewoelbt ganz nein, leeres Modell nein",
          mk.betrifft(m_luecke) and not mk.betrifft(m_ganz) and not mk.betrifft(Model("leer")))
    m_st, f_st = zylinder(winkel=120.0, nu=6, nv=3)
    from statik3d.bridges.positions import Stellung
    from statik3d.model import Situation
    m_st.stellungen.append(Stellung("S", 90.0, "", dreh_achse=(1.0, 0.0, 0.0), dreh_winkel=90.0))
    m_st.situationen["U"] = Situation("U", "S", [], "")
    m_w = _mantel270()
    from statik3d.wasserdruck import Wasserdruck, lasten_erzeugen
    with _still():
        lasten_erzeugen(m_w, Wasserdruck("W1", flaechen=["M"], h_ow=2.5, verfahren="analytisch",
                                         absenkung=False))
    check("… betroffen: Situation mit Stellung an gewoelbter Flaeche ja, Wasserdruck am Mantel ja",
          mk.betrifft(m_st) and mk.betrifft(m_w))


def _halbkreis_stellung(bogen=True):
    """Ebene Halbkreisplatte R = 1 m (Durchmesser auf der x-Achse, Rand aus
    zwei Boegen bzw. einem Vieleck) in einer Situation mit Stellung 180° um x
    (Beleg b6 vom 14.11.2026)."""
    from statik3d.model import Model, Material, ShellProp, Situation
    from statik3d import mesher
    from statik3d.bridges.positions import Stellung
    m = Model("Halbkreis")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0, fy=355e6, alpha=1.2e-5))
    m.add_shell_prop(ShellProp("t", 0.02))
    a = m.add_node(-1.0, 0.0, 0.0)
    b = m.add_node(1.0, 0.0, 0.0)
    c = m.add_node(0.0, 1.0, 0.0)
    m.add_line("D", [a, b])
    r2 = math.sqrt(0.5)
    if bogen:
        m.add_line("B1", [b, c], "arc", punkte=[(1.0, 0.0, 0.0), (r2, r2, 0.0), (0.0, 1.0, 0.0)])
        m.add_line("B2", [c, a], "arc", punkte=[(0.0, 1.0, 0.0), (-r2, r2, 0.0), (-1.0, 0.0, 0.0)])
    else:
        m.add_line("B1", [b, c])
        m.add_line("B2", [c, a])
    f = m.add_flaeche("H", ["D", "B1", "B2"], material="S", dicke="t")
    m.netz.ziellaenge = 0.2
    with _still():
        mesher.modell_vernetzen(m, log=[], workers=1)
    m.add_load_case("LF2")
    m.add_geometrielast("H", P, case="LF2")
    m.lasten_verteilen()
    gruppen = sorted({m.elements[e].group for e in f.elemente})
    m.stellungen.append(Stellung("S180", 180.0, "", dreh_achse=(1.0, 0.0, 0.0), dreh_punkt=(0.0, 0.0, 0.0),
                                 dreh_winkel=180.0, dreh_gruppen=gruppen, faelle=["LF2"]))
    m.situationen["U"] = Situation("U", "S180", [], "")
    m.load_cases["LF2"].situation = "U"
    return m


def test_a10s_eben_bogen_stellung():
    """Befund A'10 (14.11.2026): eine bewegte Stellung mit einer EBENEN
    Schalenflaeche mit krummen Randlinien war bis Stand 41 genauso betroffen
    (die Stuetzpunkte der Boegen drehten nicht mit), das Merkmal
    schalenlage_gewoelbt zaehlte nur gewoelbte Flaechen."""
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("schalenlage_gewoelbt")
    check("A'10 ebene Halbkreisplatte mit Boegen in bewegter Stellung: schalenlage_gewoelbt betroffen; "
          "dieselbe Platte mit geraden Randlinien nicht",
          mk is not None and mk.betrifft(_halbkreis_stellung(True)) and not mk.betrifft(_halbkreis_stellung(False)))


def test_verfahrenstabelle_55():
    """Merkmal Stand 55: gewoelbte einteilige Flaeche, bei der Randumlauf und
    Stokes verschieden entscheiden (Loch, Kerbe)."""
    from statik3d import rechenverfahren as rv
    from statik3d.model import Model
    mk = rv.merkmal("schalenlage_gewoelbt_einteilig")
    ok = mk is not None and any(w.stand == 55 for w in mk.wechsel) and rv.VERFAHRENSSTAND >= 55
    check("Merkmal schalenlage_gewoelbt_einteilig mit Stand 55, VERFAHRENSSTAND >= 55", ok,
          f"Stand {rv.VERFAHRENSSTAND}")
    if mk is None:
        check("… betroffen: Zylinder mit Loch ja, ganzer Zylinder nein, Zylinder mit Streifen (Stand 42) nein, "
              "leer nein", False, "kein Merkmal")
        return
    m_loch, f = zylinder(nu=15, nv=6)
    m_loch.elemente_loeschen([e for e in f.elemente if 90 < _winkel(m_loch, e) < 210
                              and 1 / 3 < _mitte(m_loch, e)[2] < 5 / 3])
    m_ganz, _f = zylinder(nu=15, nv=6)
    m_str, f2 = zylinder()
    m_str.elemente_loeschen([e for e in f2.elemente if 40.0 < _winkel(m_str, e) < 60.0])
    from statik3d import schalenlage as SL
    vorher = mk.betrifft(m_loch)
    with _still():
        SL.schalen_ausrichten(m_loch)
    check("… betroffen: Zylinder mit Loch ja (vor und nach dem Ausrichten), ganzer Zylinder nein, Zylinder "
          "mit Streifen (Stand 42) nein, leer nein",
          vorher and mk.betrifft(m_loch) and not mk.betrifft(m_ganz) and not mk.betrifft(m_str)
          and not mk.betrifft(Model("leer")))


def main():
    for t in (test_a5_luecke, test_a5_stueck_gespiegelt, test_a5_insel, test_a5_eben_unveraendert,
              test_a6_stellung, test_a6_stellungsreihe, test_a7_mantel270, test_a7s_loch_kerbe,
              test_a7s_ganz_unveraendert, test_a7s_wasser_loch, test_a10_fuge_schale_schale,
              test_a10_meldung_generatoren, test_verfahrenstabelle, test_a10s_eben_bogen_stellung,
              test_verfahrenstabelle_55):
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
