"""Stabenden auf oder in einem Koerper haengen an dessen Netz (16.09.2026).

RFEM integriert einen Knoten, der auf einer Flaeche liegt, ins Netz; der
freie Vernetzer hier kannte ihn nicht. Am Drehlager endeten deshalb die 64
Zugstaebe der Schrauben an keinem Element, die Deckel hoben ab.

Probe: ein Wuerfel, unten gehalten. Ein Zugstab endet in der Deckelflaeche
(nicht auf einem Netzknoten), ein zweiter im Innern, ein dritter liegt
neben dem Wuerfel (Kragarm, bleibt frei). Der Zug an den freien Enden geht
durch den Wuerfel ins Fundament - vorher ging er ins Leere.

Aufruf:  python -m tests.test_stabende
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import fugen, solver                            # noqa: E402
from statik3d.model import NodalLoad, Section                # noqa: E402
from tests.test_fugen import _flaechenknoten, _wuerfel       # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return ok


def _modell():
    m = _wuerfel(0.5)
    m.add_section(Section("Rund", 1e-4, 1e-9, 1e-9, 1e-9))
    fuss = m.add_node(0.41, 0.47, 1.0)          # in der Deckelflaeche, neben den Netzknoten
    kopf = m.add_node(0.41, 0.47, 1.6)
    innen = m.add_node(0.31, 0.29, 0.56)        # im Innern des Wuerfels
    oben2 = m.add_node(0.31, 0.29, 1.6)
    a3 = m.add_node(2.0, 0.0, 0.5)              # neben dem Wuerfel
    b3 = m.add_node(2.5, 0.0, 0.5)
    e1 = m.add_element("truss", [fuss, kopf], "S235", "Rund", group="Zug")
    e2 = m.add_element("truss", [innen, oben2], "S235", "Rund", group="Innen")
    e3 = m.add_element("truss", [a3, b3], "S235", "Rund", group="Frei")
    m.add_member("Zug", [e1])
    m.add_member("Innen", [e2])
    m.add_member("Frei", [e3])
    return m, fuss, kopf, innen, oben2, a3, b3


def test_anschluss():
    m, fuss, kopf, innen, oben2, a3, b3 = _modell()
    log = []
    b = fugen.stabenden_koppeln(m, log)
    partner = {}
    for k in m.kopplungen:
        partner.setdefault(int(k.node_a), []).append(int(k.node_b))
    check("zwei Stabenden angeschlossen: in der Deckelflaeche und im Innern, der Kragarm bleibt frei",
          b["stabenden"] == 2 and set(partner) == {fuss, innen}
          and all(n not in partner for n in (kopf, oben2, a3, b3)), str(b["anschluesse"]))
    pf = partner.get(fuss, [])
    check("Ende in der Deckelflaeche: 1 bis 3 Knoten der Deckelflaeche (z = 1), keiner darunter",
          1 <= len(pf) <= 3 and all(abs(m.nodes[q][2] - 1.0) < 1e-9 for q in pf), str([np.round(m.nodes[q], 3) for q in pf]))
    pi = partner.get(innen, [])
    check("Ende im Innern: die 4 Knoten des Tetraeders, in dem es liegt",
          len(pi) == 4 and all(0.0 < m.nodes[q][2] < 1.0 + 1e-9 for q in pi), str(len(pi)))
    check("alle Kopplungen starr in drei Richtungen, Gruppe 'Stabende K…'",
          all(k.steifigkeiten == [float("inf")] * 3 and k.gruppe.startswith(fugen.STABENDE_GRUPPE) for k in m.kopplungen))
    check("das Protokoll nennt Stab und Koerper",
          any("Zug (K" in z and "V1" in z and "Knoten an Volumen angeschlossen (Stabende)" in z for z in log), str(log[:1])[:160])
    n1 = len(m.kopplungen)
    fugen.stabenden_koppeln(m, [])
    check("ein zweiter Aufruf legt die Kopplungen nicht doppelt an", len(m.kopplungen) == n1, f"{n1} / {len(m.kopplungen)}")
    # Statik: Zug an den freien Enden geht durch den Wuerfel ins Fundament
    unten = _flaechenknoten(m, 0.0)
    for i in unten:
        m.fix(i, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(kopf, [0, 0, 50e3, 0, 0, 0]))
    lc.nodal_loads.append(NodalLoad(oben2, [0, 0, 20e3, 0, 0, 0]))
    r = solver.solve_static(m, case="LF1")
    R = float(r.reactions[unten, 2].sum())
    check("das Fundament traegt die 70 kN der beiden Zugstaebe (vorher: 0, die Staebe hingen im Leeren)",
          abs(R + 70e3) < 1e-3 * 70e3, f"{R:.1f} N")
    u_f = r.u[fuss, :3]
    u_p = r.u[pf, :3].mean(axis=0)
    check("das Stabende bewegt sich mit den gekoppelten Knoten (starr)",
          float(np.linalg.norm(u_f - u_p)) < 1e-3 * max(float(np.linalg.norm(u_f)), 1e-12), f"{np.linalg.norm(u_f - u_p):.2e} m")
    check("die Zugstaebe tragen ihre Last: der obere Stab 50 kN",
          abs(float(np.linalg.norm(r.u[kopf, :3] - r.u[fuss, :3])) * 210e9 * 1e-4 / 0.6 - 50e3) < 50, "")


def test_integrierte_last_und_lagerknoten():
    """Ein integrierter Knoten (RFEM) mit Knotenlast auf der Deckelflaeche
    und ein Lagerknoten auf einer Mantelflaeche: beide haengen am Netz."""
    m = _wuerfel(0.5)
    last = m.add_node(0.62, 0.36, 1.0)          # auf dem Deckel, integriert
    lager = m.add_node(1.0, 0.44, 0.58)         # auf der Mantelflaeche x = 1
    m.flaechen["Deckel"].integrierte_knoten.append(last)
    leer = m.add_node(0.2, 0.7, 1.0)            # integriert, aber ohne Last, Lager, Stab
    m.flaechen["Deckel"].integrierte_knoten.append(leer)
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(last, [0, 0, -30e3, 0, 0, 0]))
    m.fix(lager, [0])                            # haelt in x
    log = []
    b = fugen.stabenden_koppeln(m, log)
    partner = {}
    for k in m.kopplungen:
        partner.setdefault(int(k.node_a), []).append(int(k.node_b))
    check("integrierter Lastknoten und Lagerknoten angeschlossen (3 Knoten je Seitenflaeche)",
          set(partner) == {last, lager} and 1 <= len(partner[last]) <= 3 and 1 <= len(partner[lager]) <= 3
          and all(abs(m.nodes[q][2] - 1.0) < 1e-9 for q in partner[last])
          and all(abs(m.nodes[q][0] - 1.0) < 1e-9 for q in partner[lager]), str(b["anschluesse"]))
    check("das Protokoll nennt die Gruende Last, integriert und Lager",
          any("integriert" in z and "Lager" in z and "Last" in z for z in log), str(log[:1])[:120])
    check("ein integrierter Knoten ohne Anhang bleibt frei (er traegt nichts, keine Straffeder)",
          leer not in partner, str(b["anschluesse"]))
    unten = _flaechenknoten(m, 0.0)
    for i in unten:
        m.fix(i, [0, 1, 2])
    r = solver.solve_static(m, case="LF1")
    R = float(r.reactions[unten, 2].sum())
    check("die Knotenlast auf dem integrierten Knoten kommt im Fundament an (30 kN; vorher ging sie verloren)",
          abs(R - 30e3) < 1e-3 * 30e3, f"{R:.1f} N")


def test_ohne_koerper_und_ohne_kandidaten():
    m, *_ = _modell()
    m.koerper.clear()
    b = fugen.stabenden_koppeln(m, [])
    check("ohne Koerper nichts zu tun", b["stabenden"] == 0 and not m.kopplungen)
    m2 = _wuerfel(0.5)
    check("ohne Staebe nichts zu tun", fugen.stabenden_koppeln(m2, [])["stabenden"] == 0)


def main():
    for t in (test_anschluss, test_integrierte_last_und_lagerknoten, test_ohne_koerper_und_ohne_kandidaten):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
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
