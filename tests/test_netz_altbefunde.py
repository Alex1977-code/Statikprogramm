"""
Zwei alte Netzbefunde der Pruefagenten vom 11.11.2026, zur Behebung
freigegeben am 12.11.2026.

Befund 11: Die Kur A22 (elementbezogenes Flaechenlager zieht beim Loeschen
von Elementen mit) steckte nur in Model.elemente_loeschen. Die Oberflaeche
vernetzt ueber MainWindow._netz_loeschen, das die Flaechenlager nicht
nachzog: zwei Flaechen A (x 0..1) und B (x 1..2), Bettung auf den vier
Elementen von B (x-Mitten 1,25 und 1,75); nach dem Neuvernetzen von A lag
die Bettung auf [4, 5, 6, 7] mit x-Mitten 0,125 - auf Flaeche A, ohne
Meldung. Jetzt laeuft jedes Loeschen ueber Model.elemente_loeschen. Lag das
Lager auf **allen** Elementen einer Flaeche (oder eines Koerpers mit
face = -1), die neu vernetzt wird, folgt es deren neuem Netz (derselbe Ort,
eindeutig); lag es nur auf einem Teil, ist der Ort im neuen Netz nicht
eindeutig - das Lager meldet „Netz geändert – Lager prüfen“ und liegt nie
still auf anderen Elementen.

Befund 39: Eine Rippe mit eigener Linie auf dem Plattenrand (gleiche zwei
Knoten wie die Randlinie der Platte, anderer Name) war nur verbunden, wenn
zufaellig ein fremder Knoten auf der Linie lag (17 Rippenknoten auf R0,
davon 2 Plattenknoten; mit fremdem Knoten 20 von 20). Jetzt legt der
Vernetzer doppelte Linien immer auf eine (mesher._teilplan), mit
Protokollzeile. Zweiter Weg: dieselbe Geometrie mit einer gemeinsamen Linie
gibt dasselbe Netz und dieselbe Verformung; Platte 4 m aus zwei Flaechen
(Befund A vom 09.11.2026): max w 149,6 mm mit gemeinsamer Linie, getrennt
398 mm.

Aufruf:  python -m tests.test_netz_altbefunde
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_netz_altbefunde_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import diagnose, mesher, solver, supports                 # noqa: E402
from statik3d.model import DofBehaviour, Material, Model, ShellProp     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<92} {detail}")
    return bool(ok)


def still(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **kw)


# ---------------------------------------------------------------------------
# Befund 11
# ---------------------------------------------------------------------------
def zwei_flaechen(h=0.5) -> Model:
    """A (x 0..1) und B (x 1..2), gemeinsame Linie a1, je 1 m²."""
    m = Model("Z")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0.]]))
    m.add_line("a0", [0, 1]); m.add_line("a1", [1, 2]); m.add_line("a2", [2, 3]); m.add_line("a3", [3, 0])
    m.add_line("b0", [1, 4]); m.add_line("b1", [4, 5]); m.add_line("b2", [5, 2])
    m.add_flaeche("A", ["a0", "a1", "a2", "a3"], material="S235", dicke="t12")
    m.add_flaeche("B", ["b0", "b1", "b2", "a1"], material="S235", dicke="t12")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    still(mesher.modell_vernetzen, m, [], workers=1)
    return m


def x_mitten(m, els):
    return [float(m.nodes[m.elements[int(i)].nodes].mean(axis=0)[0]) for i in els if 0 <= int(i) < len(m.elements)]


def flaeche_von(m, ss) -> float:
    return float(sum(supports.tributary_areas(m, [int(e) for e in ss.elements], ss.face).values()))


def lager_meldung(m, ss) -> list:
    return [b for b in diagnose.eingabepruefung(m)
            if b.objekt == ss.name and "Netz geändert – Lager prüfen" in b.text]


def gui_vernetzen(m, flaechen=None, koerper=None) -> list:
    """Der echte Weg der Oberflaeche (MainWindow._vernetzen mit _netz_loeschen),
    das Fenster als Attrappe - wie tests.test_neuvernetzen."""
    import importlib
    import time
    from unittest import mock
    G = importlib.import_module("statik3d.gui.main")
    s = mock.MagicMock()
    s.model = m
    s._fortschritt_t0 = time.time()
    s._netz_loeschen = G.MainWindow._netz_loeschen.__get__(s)
    s._vernetzen_netz = G.MainWindow._vernetzen_netz.__get__(s)
    with mock.patch.object(G, "QtWidgets"):
        still(G.MainWindow._vernetzen, s,
              list(m.flaechen.values()) if flaechen is None else flaechen,
              list(m.koerper.values()) if koerper is None else koerper)
    return [str(c.args[0]) for c in s.log.appendPlainText.call_args_list if c.args]


def test_oberflaeche_nachbarflaeche():
    """Nachstellung s3.py: Bettung auf B, A wird in der Oberflaeche neu vernetzt."""
    m = zwei_flaechen()
    ss = m.add_surface_support(elements=list(m.flaechen["B"].elemente), name="Bettung",
                               uz=DofBehaviour("spring", stiffness=1e7))
    gui_vernetzen(m, flaechen=[m.flaechen["A"]], koerper=[])
    xm = x_mitten(m, ss.elements)
    check("**Befund 11, Oberfläche: A neu vernetzt – die Bettung bleibt auf B** (x-Mitten > 1)",
          sorted(ss.elements) == sorted(m.flaechen["B"].elemente) and xm and min(xm) > 1.0,
          f"Bettung {ss.elements}, x-Mitten {[round(x, 3) for x in xm]}, B {m.flaechen['B'].elemente}")
    check("… Bettungsfläche 1,000 m² wie vorher, keine Meldung",
          abs(flaeche_von(m, ss) - 1.0) < 1e-9 and not lager_meldung(m, ss),
          f"{flaeche_von(m, ss):.4f} m²")


def test_ganze_flaeche_folgt(weg):
    """Bettung auf ALLEN Elementen von A, A wird feiner neu vernetzt: dieselbe
    Flaeche (1 m²), jetzt auf dem neuen Netz von A."""
    m = zwei_flaechen()
    ss = m.add_surface_support(elements=list(m.flaechen["A"].elemente), name="Bettung",
                               uz=DofBehaviour("spring", stiffness=1e7))
    n_vor = len(ss.elements)
    m.netz.ziellaenge = 0.25
    log = []
    if weg == "Oberfläche":
        log = gui_vernetzen(m, flaechen=[m.flaechen["A"]], koerper=[])
    else:
        still(mesher.modell_vernetzen, m, log, workers=1, flaechen=[m.flaechen["A"]], koerper=[])
    A = sorted(int(e) for e in m.flaechen["A"].elemente)
    xm = x_mitten(m, ss.elements)
    check(f"**Befund 11, {weg}: Bettung auf ganz A, A neu vernetzt – sie folgt dem neuen Netz von A**",
          sorted(ss.elements) == A and len(A) > n_vor and xm and max(xm) < 1.0,
          f"Bettung {len(ss.elements)} Elemente (vorher {n_vor}), A {len(A)}")
    check(f"… {weg}: Bettungsfläche 1,000 m², keine Meldung „Netz geändert“, Protokoll nennt es",
          abs(flaeche_von(m, ss) - 1.0) < 1e-9 and not lager_meldung(m, ss)
          and any("Bettung" in z and "folgt" in z for z in log),
          f"{flaeche_von(m, ss):.4f} m², Protokoll {[z for z in log if 'Bettung' in z][:1]}")


def test_teil_der_flaeche_meldet(weg):
    """Bettung auf zwei der vier Elemente von A: im neuen Netz ist der Ort
    nicht eindeutig - Meldung, nie still auf anderen Elementen."""
    m = zwei_flaechen()
    alt = list(m.flaechen["A"].elemente)[:2]
    ss = m.add_surface_support(elements=alt, name="Bettung", uz=DofBehaviour("spring", stiffness=1e7))
    if weg == "Oberfläche":
        gui_vernetzen(m, flaechen=[m.flaechen["A"]], koerper=[])
    else:
        still(mesher.modell_vernetzen, m, [], workers=1, flaechen=[m.flaechen["A"]], koerper=[])
    mel = lager_meldung(m, ss)
    check(f"**Befund 11, {weg}: Bettung auf einem Teil von A, A neu vernetzt – Meldung, kein Element mehr**",
          ss.elements == [] and mel and mel[0].stufe != "WARNUNG",
          f"Bettung {ss.elements}, Meldung {[b.text[:70] for b in mel]}")


def test_beide_flaechen_teilweise():
    """Bettung auf ganz B und halb A, beide neu vernetzt: B folgt, der Teil auf A
    entfaellt - die Meldung sagt es, die Bettung liegt nur auf B."""
    m = zwei_flaechen()
    ss = m.add_surface_support(elements=list(m.flaechen["A"].elemente)[:2] + list(m.flaechen["B"].elemente),
                               name="Bettung", uz=DofBehaviour("spring", stiffness=1e7))
    gui_vernetzen(m)
    xm = x_mitten(m, ss.elements)
    mel = lager_meldung(m, ss)
    check("Befund 11, Oberfläche: ganz B und halb A – B folgt, halb A entfällt mit WARNUNG (2 Elemente)",
          sorted(ss.elements) == sorted(m.flaechen["B"].elemente) and min(xm) > 1.0
          and mel and mel[0].stufe == "WARNUNG" and int(mel[0].wert) == 2,
          f"Bettung {ss.elements}, Meldung {[b.text[:90] for b in mel]}")


def quader() -> Model:
    m = Model()
    m.add_material(Material.steel("S235"))
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    m.add_nodes(P)
    L = {}
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]:
        L[(a, b)] = m.add_line(f"L{a}{b}", [a, b]).name
    def fl(name, kanten):
        m.add_flaeche(name, [L[k] for k in kanten], material="S235")
    fl("U", [(0, 1), (1, 2), (2, 3), (3, 0)]); fl("O", [(4, 5), (5, 6), (6, 7), (7, 4)])
    fl("V", [(0, 1), (1, 5), (4, 5), (0, 4)]); fl("H", [(2, 3), (3, 7), (6, 7), (2, 6)])
    fl("Li", [(3, 0), (0, 4), (7, 4), (3, 7)]); fl("Re", [(1, 2), (2, 6), (5, 6), (1, 5)])
    m.add_koerper("K", ["U", "O", "V", "H", "Li", "Re"], material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = 0.5
    still(mesher.modell_vernetzen, m, [], workers=1)
    return m


def test_koerper():
    """Koerper: face = -1 (alle Aussenflaechen) folgt dem neuen Netz (6 m²);
    eine einzelne Elementseite (face = 0) ist im neuen Netz nicht dieselbe -
    Meldung."""
    m = quader()
    K = m.koerper["K"]
    alle = m.add_surface_support(elements=list(K.elemente), name="Huelle",
                                 uz=DofBehaviour("spring", stiffness=1e7))
    seite = m.add_surface_support(elements=list(K.elemente), name="Seite0", face=0,
                                  uz=DofBehaviour("spring", stiffness=1e7))
    a_vor = flaeche_von(m, alle)
    m.netz.ziellaenge = 0.34
    still(mesher.modell_vernetzen, m, [], workers=1)
    check("Befund 11, Körper: Lager auf allen Elementen, face = -1, folgt dem neuen Netz (6,000 m²)",
          sorted(alle.elements) == sorted(K.elemente) and abs(flaeche_von(m, alle) - 6.0) < 1e-6
          and abs(a_vor - 6.0) < 1e-6 and not lager_meldung(m, alle),
          f"{len(alle.elements)} Elemente, {flaeche_von(m, alle):.4f} m² (vorher {a_vor:.4f})")
    check("… face = 0 (eine Elementseite) folgt nicht, sondern meldet",
          seite.elements == [] and bool(lager_meldung(m, seite)), f"{seite.elements}")


def test_entfallen_dann_vernetzen():
    """Netz loeschen und spaeter vernetzen: dazwischen meldet das Lager, danach
    folgt es; gibt der Anwender ihm vorher neue Elemente, folgt es nicht mehr."""
    m = zwei_flaechen()
    A = m.flaechen["A"]
    ss = m.add_surface_support(elements=list(A.elemente), name="Bettung", uz=DofBehaviour("spring", stiffness=1e7))
    m.elemente_loeschen(list(A.elemente))
    A.elemente = []
    supports.lager_auf_netz(m, [])
    zwischen = bool(lager_meldung(m, ss)) and ss.elements == []
    still(mesher.modell_vernetzen, m, [], workers=1, flaechen=[A], koerper=[])
    check("Befund 11: Netz von A gelöscht – Meldung; A später vernetzt – das Lager folgt",
          zwischen and sorted(ss.elements) == sorted(A.elemente) and not lager_meldung(m, ss),
          f"{ss.elements}")
    m2 = zwei_flaechen()
    A2, B2 = m2.flaechen["A"], m2.flaechen["B"]
    ss2 = m2.add_surface_support(elements=list(A2.elemente), name="Bettung",
                                 uz=DofBehaviour("spring", stiffness=1e7))
    m2.elemente_loeschen(list(A2.elemente))
    A2.elemente = []
    ss2.elements = list(B2.elemente)           # der Anwender setzt das Lager neu
    still(mesher.modell_vernetzen, m2, [], workers=1, flaechen=[A2], koerper=[])
    check("… neu gesetzt vor dem Vernetzen: das Lager bleibt, wo der Anwender es hinlegte",
          sorted(ss2.elements) == sorted(B2.elemente) and not lager_meldung(m2, ss2), f"{ss2.elements}")


def test_speichern_und_laden():
    import json
    m = zwei_flaechen()
    A = m.flaechen["A"]
    ss = m.add_surface_support(elements=list(A.elemente), name="Bettung", uz=DofBehaviour("spring", stiffness=1e7))
    m.elemente_loeschen(list(A.elemente))
    A.elemente = []
    d = json.loads(json.dumps(m.to_dict()))
    m2 = Model.from_dict(d)
    still(mesher.modell_vernetzen, m2, [], workers=1, flaechen=[m2.flaechen["A"]], koerper=[])
    ss2 = m2.surface_supports[0]
    check("Befund 11: der Vormerk übersteht Speichern und Laden – nach dem Vernetzen folgt das Lager",
          sorted(ss2.elements) == sorted(m2.flaechen["A"].elemente) and ss2.elements, f"{ss2.elements}")
    m3 = zwei_flaechen()
    m3.add_surface_support(elements=[0, 1], name="X", uz=DofBehaviour("spring", stiffness=1e7))
    d3 = m3.to_dict()["surface_supports"][0]
    check("… ein Lager ohne Vormerk schreibt das neue Feld nicht in die Datei", "folgt" not in d3,
          str(sorted(d3)))


def test_web_loeschen():
    """Derselbe Fehler im Web-Weg (web/server.py _remove_elements)."""
    from statik3d.web import server as W
    m = zwei_flaechen()
    ss = m.add_surface_support(elements=list(m.flaechen["B"].elemente), name="Bettung",
                               uz=DofBehaviour("spring", stiffness=1e7))
    W._remove_elements(m, {int(m.flaechen["A"].elemente[0])})
    xm = x_mitten(m, ss.elements)
    check("Befund 11, Web: ein Element von A gelöscht – die Bettung bleibt auf B (1,000 m²)",
          xm and min(xm) > 1.0 and abs(flaeche_von(m, ss) - 1.0) < 1e-9,
          f"{ss.elements} x-Mitten {[round(x, 3) for x in xm]}")


def test_verfahrenstabelle_11():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("flaechenlager_neuvernetzen")
    m = zwei_flaechen()
    m.add_surface_support(elements=list(m.flaechen["B"].elemente), name="Bettung",
                          uz=DofBehaviour("spring", stiffness=1e7))
    m2 = zwei_flaechen()
    s2 = m2.add_surface_support(name="Geo", uz=DofBehaviour("spring", stiffness=1e7))
    s2.flaechen = ["B"]
    m3 = zwei_flaechen()
    check("Verfahrenstabelle: Merkmal „flaechenlager_neuvernetzen“, Stand 37, Fehlerkorrektur; betrifft "
          "nur elementbezogene Flächenlager auf Flächen/Körpern",
          mk is not None and mk.wechsel[-1].stand == 37 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 37 and mk.betrifft(m) and not mk.betrifft(m2) and not mk.betrifft(m3),
          f"{mk.modellmerkmal if mk else 'fehlt'}")


# ---------------------------------------------------------------------------
# Befund 39
# ---------------------------------------------------------------------------
def rippe_am_rand(doppelt=True, fremd=False, form=2) -> Model:
    """Platte P 2 x 2 m, Rippe 0,2 m nach unten am Rand y = 0 (Linie R0 A-B).
    ``doppelt``: die Rippe hat die eigene Linie R0d (dieselben Knoten),
    sonst teilt sie R0. ``fremd``: dazu eine Flaeche N mit Knoten (1|0) auf R0."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D", 0.01))
    m.netz.form = form
    m.netz.dichte = "mittel"
    A, B, C, D = [m.add_node(*p) for p in [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)]]
    m.add_line("R0", [A, B]); m.add_line("Q", [B, C]); m.add_line("R2", [C, D]); m.add_line("L", [D, A])
    m.add_flaeche("P", ["R0", "Q", "R2", "L"], material="S235", dicke="D")
    a2, b2 = m.add_node(0, 0, -0.2), m.add_node(2, 0, -0.2)
    unten = "R0d" if doppelt else "R0"
    if doppelt:
        m.add_line("R0d", [A, B])
    m.add_line("U", [a2, b2]); m.add_line("V0", [A, a2]); m.add_line("V1", [B, b2])
    if fremd:
        k = m.add_node(1, 0, 0); e = m.add_node(1, -1, 0); f = m.add_node(0, -1, 0)
        m.add_line("N1", [A, k]); m.add_line("N2", [k, e]); m.add_line("N3", [e, f]); m.add_line("N4", [f, A])
        m.add_flaeche("N", ["N1", "N2", "N3", "N4"], material="S235", dicke="D")
    m.add_flaeche("Rippe", [unten, "V1", "U", "V0"], material="S235", dicke="D")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0.0, 0.0, -9.81]
    ls = m.add_line_support([], name="Auflager")
    ls.linien = ["L", "Q", "V0", "V1"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def knoten_von(m, f) -> set:
    return {int(k) for e in (m.flaechen[f].elemente or []) for k in m.elements[int(e)].nodes}


def auf_r0(m, kn) -> set:
    X = np.asarray(m.nodes)
    return {i for i in kn if abs(X[i, 1]) < 1e-9 and abs(X[i, 2]) < 1e-9}


def test_doppellinie_verbunden():
    aus = {}
    for fremd in (False, True):
        m = rippe_am_rand(doppelt=True, fremd=fremd)
        log = []
        still(mesher.modell_vernetzen, m, log, workers=1)
        r = auf_r0(m, knoten_von(m, "Rippe"))
        aus[fremd] = (len(r), len(r & knoten_von(m, "P")), log)
    (n0, g0, log0), (n1, g1, _l) = aus[False], aus[True]
    check("**Befund 39: Rippe mit eigener Linie auf dem Plattenrand – alle Rippenknoten auf R0 sind "
          "Plattenknoten, ohne fremden Knoten**", n0 > 2 and g0 == n0, f"{g0} von {n0}")
    check("… mit fremdem Knoten auf R0 ebenso (unabhängig vom Nachbarn)", n1 > 2 and g1 == n1, f"{g1} von {n1}")
    check("… das Protokoll nennt die doppelte Linie",
          any("R0" in z and "R0d" in z and "dieselben" in z for z in log0),
          str([z for z in log0 if "R0d" in z][:1]))


def netz_signatur(m):
    X = np.round(np.asarray(m.nodes, float), 9)
    els = sorted(tuple(sorted(tuple(X[int(k)]) for k in m.elements[int(e)].nodes))
                 for f in m.flaechen.values() for e in (f.elemente or []))
    return els


def w_max(m) -> float:
    r = still(solver.solve_all, m, workers=1, combinations=False).cases["LF1"]
    dran = sorted({int(k) for e in m.elements for k in e.nodes})
    return float(np.abs(np.asarray(r.u)[dran, 2]).max())


def test_doppellinie_wie_gemeinsame_linie():
    """Zweiter Weg: dieselbe Rippe an der gemeinsamen Linie R0."""
    for form in (2, 0):
        a, b = rippe_am_rand(doppelt=True, form=form), rippe_am_rand(doppelt=False, form=form)
        still(mesher.modell_vernetzen, a, [], workers=1)
        still(mesher.modell_vernetzen, b, [], workers=1)
        sa, sb = netz_signatur(a), netz_signatur(b)
        wa, wb = w_max(a), w_max(b)
        art = "Vierecke" if form == 2 else "Dreiecke"
        check(f"**Befund 39, {art}: doppelte Linie = gemeinsame Linie – dasselbe Netz, dieselbe Verformung**",
              len(sa) == len(sb) and sa == sb and abs(wa - wb) <= 1e-9 * max(wb, 1e-12),
              f"{len(sa)}/{len(sb)} Elemente, w_max {wa * 1e3:.4f} / {wb * 1e3:.4f} mm")


def platte_4m(doppelt: bool) -> Model:
    """Befund A vom 09.11.2026 (Testmodelle/gegenprobe_zwei_flaechen.py):
    Platte 4 x 2 m, t = 10 mm, aus F1 und F2, gelenkig an x = 0 und x = 4,
    Eigengewicht. ``doppelt``: F2 hat an x = 2 die eigene Linie L7d."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D10", 0.01))
    for p in [(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 2, 0), (2, 2, 0), (0, 2, 0)]:
        m.add_node(*p)
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L7", "L5", "L6"], material="S235", dicke="D10")
    if doppelt:
        m.add_line("L7d", [4, 1])
    m.add_flaeche("F2", ["L2", "L3", "L4", "L7d" if doppelt else "L7"], material="S235", dicke="D10")
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    ls = m.add_line_support([], name="LL")
    ls.linien = ["L6", "L3"]
    for d in (0, 1, 2):
        ls.behaviour[d] = DofBehaviour("rigid")
    return m


def test_platte_4m():
    a, b = platte_4m(True), platte_4m(False)
    still(mesher.modell_vernetzen, a, [], workers=1)
    still(mesher.modell_vernetzen, b, [], workers=1)
    wa, wb = w_max(a), w_max(b)
    X = np.asarray(a.nodes)
    mitte = [i for i in knoten_von(a, "F1") & knoten_von(a, "F2") if abs(X[i, 0] - 2) < 1e-9]
    check("**Befund 39, Platte 4 m aus zwei Flächen mit doppelter Mittellinie: max w = 149,6 mm wie mit "
          "gemeinsamer Linie (Befund A), nicht 398 mm**",
          abs(wa * 1e3 - 149.6) < 0.05 and abs(wa - wb) <= 1e-9 * wb and len(mitte) == 12,
          f"doppelt {wa * 1e3:.2f} mm, gemeinsam {wb * 1e3:.2f} mm, {len(mitte)} gemeinsame Knoten auf x = 2")


def bogen_rippe(gleich: bool) -> Model:
    """Viertelkreisscheibe (R 1 m) mit Bogenrand; eine Rippe nach unten am
    Bogen mit eigener Bogenlinie zwischen denselben Knoten. ``gleich``: der
    Bogen der Rippe ist derselbe, sonst ein anderer Bogen (Stich nach aussen)."""
    import math
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_shell_prop(ShellProp("D", 0.01))
    m.netz.dichte = "mittel"
    O, A, B = m.add_node(0, 0, 0), m.add_node(1, 0, 0), m.add_node(0, 1, 0)
    c = math.sqrt(0.5)
    mitte = (c, c) if gleich else (0.8, 0.8)
    m.add_line("Ox", [O, A]); m.add_line("Oy", [B, O])
    m.add_line("Bg", [A, B], "arc", punkte=[(1, 0, 0), (c, c, 0), (0, 1, 0)])
    m.add_flaeche("S", ["Ox", "Bg", "Oy"], material="S235", dicke="D")
    m.add_line("Bgd", [A, B], "arc", punkte=[(1, 0, 0), (mitte[0], mitte[1], 0), (0, 1, 0)])
    a2, b2 = m.add_node(1, 0, -0.2), m.add_node(0, 1, -0.2)
    m.add_line("Bu", [a2, b2], "arc", punkte=[(1, 0, -0.2), (mitte[0], mitte[1], -0.2), (0, 1, -0.2)])
    m.add_line("Va", [A, a2]); m.add_line("Vb", [B, b2])
    m.add_flaeche("Rippe", ["Bgd", "Vb", "Bu", "Va"], material="S235", dicke="D")
    return m


def test_doppelter_bogen():
    m = bogen_rippe(True)
    log = []
    still(mesher.modell_vernetzen, m, log, workers=1)
    gem = knoten_von(m, "S") & knoten_von(m, "Rippe")
    m2 = bogen_rippe(False)
    still(mesher.modell_vernetzen, m2, [], workers=1)
    gem2 = knoten_von(m2, "S") & knoten_von(m2, "Rippe")
    check("Befund 39, Bogen: derselbe Bogen doppelt – Rippe und Scheibe teilen alle Bogenknoten",
          len(gem) > 3, f"{len(gem)} gemeinsame Knoten")
    check("… ein anderer Bogen zwischen denselben Knoten wird nicht zusammengelegt (nur die Enden)",
          len(gem2) == 2, f"{len(gem2)} gemeinsame Knoten")


def test_verfahrenstabelle_39():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("doppelte_randlinien")
    check("Verfahrenstabelle: Merkmal „doppelte_randlinien“, Stand 37, Fehlerkorrektur; betrifft die "
          "doppelte Linie, nicht die gemeinsame",
          mk is not None and mk.wechsel[-1].stand == 37 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and mk.betrifft(rippe_am_rand(True)) and not mk.betrifft(rippe_am_rand(False))
          and mk.betrifft(platte_4m(True)) and not mk.betrifft(platte_4m(False)),
          f"{mk.modellmerkmal if mk else 'fehlt'}")


def main():
    tests = [test_oberflaeche_nachbarflaeche,
             lambda: test_ganze_flaeche_folgt("Oberfläche"),
             lambda: test_ganze_flaeche_folgt("modell_vernetzen"),
             lambda: test_teil_der_flaeche_meldet("Oberfläche"),
             lambda: test_teil_der_flaeche_meldet("modell_vernetzen"),
             test_beide_flaechen_teilweise,
             test_koerper,
             test_entfallen_dann_vernetzen,
             test_speichern_und_laden,
             test_web_loeschen,
             test_verfahrenstabelle_11,
             test_doppellinie_verbunden,
             test_doppellinie_wie_gemeinsame_linie,
             test_platte_4m,
             test_doppelter_bogen,
             test_verfahrenstabelle_39]
    for t in tests:
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{getattr(t, '__name__', 'test')} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 96)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
