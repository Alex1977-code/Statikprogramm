"""
Gebundene Seitenmitten auf der Sehne duerfen kein Element umstuelpen
(Befund B1 der Drehlager-Abnahme Q4, 08.10.2026).

Mittel rechnete am Drehlager nicht: "Element 580467 (tet10 im Volumen V29):
Tet10 mit negativer Jacobi-Determinante". Der Vernetzer hatte die
Seitenmitten an den gekruemmten Flaechen auf die Geometrie gesetzt und
geprueft (V29: kleinste bezogene Determinante 0,191); danach setzte
assemble.mittelknoten_auf_sehne (Q1) die gebundenen Mitten zurueck auf die
Sehne. Fuenf duenne tet10 in V29 (Kanten 3,3 neben 49 mm) mit genau einer
gebundenen Mitte auf der Sehne und einer um 2,06 % gekruemmten Nachbarkante
stuelpten sich dabei um (bezogene Determinante bis -0,88).

Der Pruefkoerper ist ein Ausschnitt des gespeicherten Mittel-Netzes
(scratchpad q4_dl_werk/netz_mittel.json, Stand 7ce2292): die fuenf
umgestuelpten tet10 und zwei Ringe Nachbarn, 872 tet10 und 1 875 Knoten in
tests/netz_drehlager_v29_7ce2292.npz, dazu die 202 Bindungen des ganzen
Netzes. Gebunden wird im Ausschnitt ueber ein Flaechenlager an den Ecken der
Kontaktseiten - das gibt genau dieselben 202 Bindungen.

Geprueft wird hier:

* der Ausschnitt wie gespeichert (Mitten schon auf der Sehne, fuenf tet10
  umgestuelpt): danach keines umgestuelpt, jedes Element mit gebundener
  Mitte mindestens SEHNE_MINDESTGUETE, die Steifigkeit laesst sich
  aufstellen, und nur die Mitten der gerade gezogenen Elemente bewegen sich;
* der Mechanismus: die gebundenen Mitten der fuenf wieder gekruemmt wie ihre
  Nachbarkante (gleicher Radius, Pfeil 1,013 mm) - alle gueltig; das Setzen
  auf die Sehne allein stuelpt sie um, mit dem Geradeziehen nicht;
* Hauptprozess und Arbeiter sehen dasselbe Netz (parallel.vor_dem_pickeln,
  assemble.stiffness, gepickelte Kopie), zweimal gebaut bitgleich, ein
  zweiter Aufruf aendert nichts;
* ohne Befund bleibt alles bitgleich: am tet10-Wuerfel mit Flaechenlager
  bleibt eine gekruemmte Mitte an einem Element mit gebundener Mitte
  gekruemmt, wenn das Element gueltig bleibt.

Aufruf:  python -m tests.test_sehne_gueltig
"""
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, parallel                      # noqa: E402
from statik3d.elements.solid import jacobi_volumen_stapel           # noqa: E402
from statik3d.model import Material, Model                          # noqa: E402

RESULTS = []
DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netz_drehlager_v29_7ce2292.npz")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return bool(ok)


def _ausschnitt(gekruemmt=False):
    """Der Ausschnitt V29 als Modell; ``gekruemmt``: die gebundenen Mitten der
    fuenf umgestuelpten tet10 wieder neben der Sehne (wie vor Q1)."""
    z = np.load(DATEI)
    m = Model()
    m.add_material(Material.steel("S355"))
    m.add_nodes(z["X"])
    for row in z["E"]:
        m.add_element("tet10", [int(x) for x in row], "S355", group="V29")
    ecken = sorted({int(x) for x in z["bind"][:, 1:].ravel()})
    m.add_surface_support(name="Kontakt", nodes=ecken, areas=[1.0] * len(ecken),
                          ux=dict(typ="rigid"), uy=dict(typ="rigid"), uz=dict(typ="rigid"))
    if gekruemmt:
        m.nodes[z["gekruemmt_knoten"]] = z["gekruemmt_X"]
    return m, z


def _guete(m, E):
    """Bezogene Jacobi-Determinante det_min/det_max je tet10 (wie der Vernetzer)."""
    d = jacobi_volumen_stapel("tet10", np.asarray(m.nodes, float)[np.asarray(E)])
    return np.where(d["det_max"] > 0, d["det_min"] / d["det_max"], -1.0)


def _mit_gebundener_mitte(m, E):
    gb = np.zeros(m.nn, bool)
    gb[[mm for mm, _a, _b in asm.mittelknoten_bindungen(m)]] = True
    return gb[np.asarray(E)[:, 4:]].any(axis=1)


def _mitten_von(m, elemente):
    return {int(x) for i in elemente for x in m.elements[int(i)].nodes[4:]}


# --------------------------------------------------------------------------
def test_ausschnitt_wie_gespeichert():
    m, z = _ausschnitt()
    E = z["E"]
    q0 = _guete(m, E)
    check("Ausschnitt V29 wie gespeichert: fünf tet10 umgestülpt",
          int((q0 <= 0).sum()) == 5 and set(np.flatnonzero(q0 <= 0)) == set(z["umgestuelpt"].tolist()),
          f"{int((q0 <= 0).sum())} umgestülpt, kleinste bezogene Determinante {q0.min():.3f}")
    check("… die Bindung im Ausschnitt ist die des ganzen Netzes (202)",
          {(a, frozenset((x, y))) for a, x, y in asm.mittelknoten_bindungen(m)}
          == {(int(a), frozenset((int(x), int(y)))) for a, x, y in z["bind"]})
    X0 = np.array(m.nodes, copy=True)
    log = []
    asm.mittelknoten_auf_sehne(m, log)
    q1 = _guete(m, E)
    check("danach: kein tet10 umgestülpt", int((q1 <= 0).sum()) == 0,
          f"{int((q1 <= 0).sum())} umgestülpt, kleinste {q1.min():.3f}")
    mit = _mit_gebundener_mitte(m, E)
    schwelle = getattr(asm, "SEHNE_MINDESTGUETE", 0.1)
    check(f"… jedes Element mit gebundener Mitte hat mindestens {schwelle:g}",
          bool((q1[mit] >= schwelle).all()), f"kleinste {q1[mit].min():.3f} an {int(mit.sum())}")
    g = getattr(m, "_mitten_gerade_gezogen", None) or {}
    liste = set(g.get("liste", []))
    check("… die fünf umgestülpten sind gerade gezogen", set(z["umgestuelpt"].tolist()) <= liste,
          f"{g.get('elemente')} Elemente, {g.get('knoten')} Mitten, größter Weg "
          f"{1e3 * g.get('weg', 0.0):.3f} mm, {g.get('runden')} Runden")
    X = np.asarray(m.nodes)
    ok = all(np.array_equal(X[mm], 0.5 * (X[a] + X[b])) for mm, a, b in asm.mittelknoten_bindungen(m))
    check("… die gebundenen Mitten stehen genau auf der Sehne", ok)
    gerade_kn = _mitten_von(m, liste)
    bewegt = set(np.flatnonzero(np.any(X != X0, axis=1)).tolist())
    check("… bewegt haben sich nur Mitten der gerade gezogenen Elemente", bewegt <= gerade_kn and bewegt,
          f"{len(bewegt)} Knoten bewegt, {len(gerade_kn)} Mitten in gerade gezogenen Elementen")
    unberuehrt = ~np.isin(np.asarray(E), list(bewegt)).any(axis=1)
    check("… Elemente ohne bewegten Knoten bitgleich (Koordinaten)",
          np.array_equal(X[np.asarray(E)[unberuehrt]], X0[np.asarray(E)[unberuehrt]]),
          f"{int(unberuehrt.sum())} von {len(E)} Elementen")
    text = " ".join(str(x) for x in log)
    check("… das Protokoll nennt die Zahl der gerade gezogenen Elemente und den Weg",
          f"{g.get('elemente')} Elemente ganz gerade gezogen" in text and "größter Weg" in text, text[-260:])
    X1 = np.array(m.nodes, copy=True)
    asm.mittelknoten_auf_sehne(m)
    check("zweiter Aufruf: nichts mehr zu ändern", np.array_equal(np.asarray(m.nodes), X1))
    try:
        K = asm.stiffness(m, workers=1)
        ok, text = bool(np.isfinite(K.data).all()) and K.shape[0] == m.ndof, f"{K.nnz} Nichtnullen"
    except ValueError as ex:
        ok, text = False, str(ex)[:120]
    check("die Steifigkeit lässt sich aufstellen", ok, text)


def test_mechanismus():
    """Gebundene Mitten wieder gekruemmt wie ihre Nachbarkante: gueltig. Erst
    das Setzen auf die Sehne stuelpt um - jetzt mit Geradeziehen nicht mehr."""
    m, z = _ausschnitt(gekruemmt=True)
    E = z["E"]
    q0 = _guete(m, E)
    fuenf = z["umgestuelpt"]
    check("gebundene Mitten gekrümmt wie die Nachbarkante: die fünf gültig",
          bool((q0[fuenf] > 0.5).all()) and int((q0 <= 0).sum()) == 0,
          f"bezogene Determinante der fünf {np.round(q0[fuenf], 3).tolist()}")
    n, versetzt, gross = asm.mittelknoten_auf_sehne(m, [])
    q1 = _guete(m, E)
    check("nach dem Setzen auf die Sehne: kein tet10 umgestülpt",
          int((q1 <= 0).sum()) == 0 and versetzt == 5,
          f"{versetzt} versetzt ({1e3 * gross:.3f} mm), {int((q1 <= 0).sum())} umgestülpt, "
          f"die fünf {np.round(q1[fuenf], 3).tolist()}")
    m2, _z = _ausschnitt()
    asm.mittelknoten_auf_sehne(m2)
    check("… dasselbe Netz wie aus dem gespeicherten Stand", np.array_equal(m.nodes, m2.nodes))


def test_haupt_und_arbeiter():
    """Hauptprozess (vor dem Pickeln), Aufstellen und Arbeiter sehen dasselbe Netz."""
    a, _z = _ausschnitt()
    parallel.vor_dem_pickeln(a)
    b, _z = _ausschnitt()
    asm.stiffness(b, workers=1)
    check("vor_dem_pickeln und stiffness geben bitgleiche Knoten", np.array_equal(a.nodes, b.nodes))
    c = pickle.loads(pickle.dumps(a, protocol=pickle.HIGHEST_PROTOCOL))
    asm.mittelknoten_auf_sehne(c)
    check("… die gepickelte Kopie (Arbeiter) ändert nichts mehr", np.array_equal(a.nodes, c.nodes))
    d, _z = _ausschnitt()
    perm = np.arange(len(d.elements))[::-1]
    d.elements = [d.elements[int(i)] for i in perm]
    asm.mittelknoten_auf_sehne(d)
    check("… Elemente in umgekehrter Reihenfolge: dieselben Knoten", np.array_equal(a.nodes, d.nodes))


def test_ohne_befund_bitgleich():
    """tet10-Wuerfel mit Flaechenlager am Boden: eine gekruemmte Mitte an
    einem Element mit gebundener Mitte bleibt gekruemmt, wenn das Element
    gueltig bleibt; nichts wird gerade gezogen."""
    from tests.test_kontaktseiten import _wuerfel, _flaechenlager
    m = _wuerfel()
    _flaechenlager(m)
    bind = asm.mittelknoten_bindungen(m)
    gb = {mm for mm, _a, _b in bind}
    X = np.asarray(m.nodes)
    wahl = None
    for i, e in enumerate(m.elements):
        if e.typ != "tet10" or not gb & {int(x) for x in e.nodes[4:]}:
            continue
        for k, (a, b) in enumerate(((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))):
            mm = int(e.nodes[4 + k])
            if mm not in gb:
                wahl = (i, mm, int(e.nodes[a]), int(e.nodes[b]))
                break
        if wahl:
            break
    i, mm, a, b = wahl
    L = float(np.linalg.norm(X[a] - X[b]))
    t = (X[b] - X[a]) / L
    n = np.cross(t, [0.0, 0.0, 1.0]) if abs(t[2]) < 0.9 else np.cross(t, [1.0, 0.0, 0.0])
    n /= np.linalg.norm(n)
    m.nodes[mm] = 0.5 * (X[a] + X[b]) + 0.01 * L * n
    X0 = np.array(m.nodes, copy=True)
    asm.mittelknoten_auf_sehne(m)
    g = getattr(m, "_mitten_gerade_gezogen", None) or {}
    check("Würfel: eine Mitte 1 % gekrümmt an einem Element mit gebundener Mitte - bleibt",
          np.array_equal(m.nodes, X0) and g.get("elemente") == 0,
          f"Element {i}, Mitte {mm}; gerade gezogen {g.get('elemente')}")


def main():
    for f in (test_ausschnitt_wie_gespeichert, test_mechanismus, test_haupt_und_arbeiter,
              test_ohne_befund_bitgleich):
        print(f"\n== {f.__name__}")
        try:
            f()
        except Exception as ex:                        # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
