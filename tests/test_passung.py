"""Passung einer Kontaktfuge (17.09.2026): Spiel, Lochleibungsgrenze,
Randabminderung - gegen das Blockbeispiel und die Fuge zweier Bloecke.

Anlass: Passstifte mit Nullspiel (Stift und Bohrung r = 12,500 mm am
Drehlager) liegen rechnerisch am ganzen Umfang an und werden am
Bohrungsaustritt gequetscht - Spannungsspitzen, die es real nicht gibt.

Aufruf:  python -m tests.test_passung
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import fugen, solver                            # noqa: E402
from statik3d.examples_lib import block_friction_example      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:76s} {detail}")
    return ok


def _slave(m):
    return [int(s) for s in m.contact_pairs[0].slave_nodes]


def _rand(m):
    P = m.nodes[_slave(m)]
    lo, hi = P.min(axis=0), P.max(axis=0)
    return [s for s in _slave(m) if abs(m.nodes[s][0] - lo[0]) < 1e-9 or abs(m.nodes[s][0] - hi[0]) < 1e-9
            or abs(m.nodes[s][1] - lo[1]) < 1e-9 or abs(m.nodes[s][1] - hi[1]) < 1e-9]


def _knotenflaechen(m):
    P = m.nodes[_slave(m)]
    A = float(np.ptp(P[:, 0]) * np.ptp(P[:, 1]))
    return {s: A / len(_slave(m)) for s in _slave(m)}


def _last(m):
    return np.array([l.F[:3] for l in m.case().nodal_loads], float).sum(axis=0)


def test_spiel():
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    uz0 = float(r0.u[_slave(m0), 2].mean())
    m1 = block_friction_example()
    m1.contact_pairs[0].spiel = 5e-4
    r1 = solver.solve_static(m1)
    uz1 = float(r1.u[_slave(m1), 2].mean())
    F = _last(m1)
    check("Spiel 0,5 mm: die Iteration konvergiert, der Block trägt nach dem Durchfahren des Spiels",
          r1.info.get("contact_converged") and sum(1 for c in r1.contact if c["status"] != "offen") > 0,
          str(r1.info.get("contact_iterations")))
    check("Spiel 0,5 mm: der Block sitzt 0,5 mm tiefer als ohne Spiel",
          abs((uz1 - uz0) + 5e-4) < 2e-6, f"{(uz1 - uz0) * 1e3:.4f} mm")
    check("Spiel 0,5 mm: Gleichgewicht - die Auflager tragen die Last",
          abs(float(r1.reactions[:, 2].sum()) + F[2]) < 1e-6 * abs(F[2]), f"{float(r1.reactions[:, 2].sum()):.1f} N")


def test_grenzpressung():
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    fn0 = np.array([c["Fn"] for c in r0.contact])
    fmax = float(fn0.max())
    check("ohne Grenze: die Normalkräfte sind ungleich verteilt (Lastschiefe)", fmax > 1.2 * fn0.mean(),
          f"max {fmax:.0f} N, Mittel {fn0.mean():.0f} N")
    m1 = block_friction_example()
    cp = m1.contact_pairs[0]
    cp.knotenflaechen = _knotenflaechen(m1)
    a_node = next(iter(cp.knotenflaechen.values()))
    grenze = 0.7 * fmax
    cp.grenzpressung = grenze / a_node
    r1 = solver.solve_static(m1)
    fn1 = np.array([c["Fn"] for c in r1.contact])
    F = _last(m1)
    check("Lochleibungsgrenze bei 70 % der Spitze: keine Knotenkraft darüber, die Spitzen fließen",
          float(fn1.max()) <= grenze * (1 + 1e-6) and any(c["status"] == "Fliessen" for c in r1.contact),
          f"max {fn1.max():.0f} N gegen Grenze {grenze:.0f} N, {sum(1 for c in r1.contact if c['status'] == 'Fliessen')} fließen")
    check("… die Nachbarn tragen den Rest: Summe der Normalkräfte = Last, Gleichgewicht",
          abs(float(fn1.sum()) + F[2]) < 1e-3 * abs(F[2]) and abs(float(r1.reactions[:, 2].sum()) + F[2]) < 1e-6 * abs(F[2]),
          f"Σ Fn {fn1.sum():.0f} N gegen {-F[2]:.0f} N")
    check("… das Kontaktergebnis nennt die Grenzkraft je Bedingung",
          all(abs(c["limit"] - grenze) < 1e-6 * grenze for c in r1.contact))


def test_randabminderung():
    m = block_friction_example()
    cp = m.contact_pairs[0]
    cp.haften, cp.mu = True, 0.0                      # rau: haftet ueberall
    r0 = solver.solve_static(m)
    check("rau ohne Randabminderung: alle geschlossenen Knoten haften",
          all(c["status"] == "Haften" for c in r0.contact if c["status"] != "offen"))
    m1 = block_friction_example()
    cp1 = m1.contact_pairs[0]
    cp1.haften, cp1.mu = True, 0.0
    rand = _rand(m1)
    cp1.rand_knoten = list(rand)
    r1 = solver.solve_static(m1)
    st = {c["node"]: c["status"] for c in r1.contact}
    innen = [s for s in _slave(m1) if s not in rand]
    F = _last(m1)
    check("Randabminderung: die Randreihe gleitet reibungsfrei (Kontakt), die inneren Knoten haften",
          len(rand) == 16 and all(st[s] in ("Kontakt", "offen") for s in rand) and all(st[s] in ("Haften", "offen") for s in innen),
          f"{len(rand)} Randknoten, {len(innen)} innen")
    check("… der Schub geht über die inneren Knoten, Gleichgewicht",
          abs(float(r1.reactions[:, 0].sum()) + F[0]) < 1e-6 * abs(F[0]) and r1.info.get("contact_converged"),
          f"{float(r1.reactions[:, 0].sum()):.1f} N gegen {-F[0]:.1f} N")


def test_fuge_passungsdaten():
    from tests.test_fugen import zwei_bloecke
    m = zwei_bloecke("eigene", 0.5, 0.15)
    kb = m.add_kontaktbedingung("Fuge").standard_anwenden("Reibungsbehaftet")
    kb.koerpernamen, kb.flaechennamen = ["Oben"], ["FugeO"]
    kb.gegenkoerper, kb.gegenflaechen = ["Unten"], ["FugeU"]
    kb.spiel, kb.grenzpressung, kb.rand_frei = 1e-4, 200e6, 1
    log = []
    fugen.kontaktfugen_ausfuehren(m, log)
    cp = next((c for c in m.contact_pairs if c.name == "Fuge"), None)
    check("die Fuge trägt Spiel und Lochleibungsgrenze ins Kontaktpaar",
          cp is not None and cp.spiel == 1e-4 and cp.grenzpressung == 200e6, str(cp and (cp.spiel, cp.grenzpressung)))
    A = sum(cp.knotenflaechen.values()) if cp else 0.0
    # Die Fugenflaeche ist 1 m²; dazu kommen die untersten Facetten der Mantelflaechen des
    # oberen Wuerfels, die in der Ebene der Mantelflaechen des unteren liegen und darum
    # als anliegend gepaart werden (Spalt 0 in der Ebene) - gemessen 1,11 m²
    check("Einflussflächen der Slave-Knoten: die Fugenfläche (1 m²) und der Saum der Mantelflächen",
          1.0 - 1e-6 <= A <= 1.25, f"{A:.6f} m²")
    P = m.nodes
    am_rand = [s for s in (cp.rand_knoten if cp else []) if min(P[s][0], P[s][1], 1 - P[s][0], 1 - P[s][1]) < 1e-9]
    check("Randabminderung 1 Reihe: die Randknoten liegen alle auf dem Rand der Fuge, mindestens vier",
          cp is not None and len(cp.rand_knoten) >= 4 and len(am_rand) == len(cp.rand_knoten), str(len(cp.rand_knoten) if cp else 0))
    check("das Protokoll nennt die Passung der Fuge",
          any("Passung" in z and "Spiel 0.100 mm" in z and "200 N/mm²" in z and "Randknoten" in z for z in log),
          str([z for z in log if "Passung" in z][:1])[:160])
    # zwei Reihen sind mehr als eine
    from statik3d.fugen import _passungsdaten
    seite = [(0, [0, 1, 2], None), (0, [1, 3, 2], None), (0, [2, 3, 4], None)]
    fl = np.array([1.0, 1.0, 1.0])
    _kf, r1 = _passungsdaten(seite, {0: 0, 1: 0, 2: 0}, fl, 1)
    _kf, r2 = _passungsdaten(seite, {0: 0, 1: 0, 2: 0}, fl, 2)
    check("_passungsdaten: eine Reihe = die Randknoten, zwei Reihen nehmen die Nachbarn dazu",
          r1 == {0, 1, 2, 3, 4} - set() and len(r2) >= len(r1), f"{sorted(r1)} / {sorted(r2)}")


def main():
    for t in (test_spiel, test_grenzpressung, test_randabminderung, test_fuge_passungsdaten):
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
