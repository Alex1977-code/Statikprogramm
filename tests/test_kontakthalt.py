"""Halt fuer Teile ohne geschlossene Bedingung (17.09.2026).

Der nach oben gezogene Block des Beispiels "Block mit Reibung" verliert im
zweiten Schritt (fast) alle Kontaktbedingungen; ohne Halt ist das System
singulaer (tests/test_abbruch.py prueft diesen Abbruch mit abgeschaltetem
Halt). Mit dem Halt bleiben die drei Bedingungen mit dem kleinsten Spalt
geschlossen, der Schritt wird noch einmal geloest, die Iteration konvergiert,
und das Protokoll nennt das gehaltene Teil.

Aufruf:  python -m tests.test_kontakthalt
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                   # noqa: E402
from statik3d.examples_lib import block_friction_example      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


def _hochgezogen():
    m = block_friction_example()
    for l in m.case().nodal_loads:
        l.F[2] = abs(l.F[2])
    return m


def test_halt():
    m = _hochgezogen()
    alt = solver.StaticSystem.hilfsfesselung
    solver.StaticSystem.hilfsfesselung = lambda self: False
    try:
        r = solver.solve_static(m)
    except RuntimeError as ex:
        check("mit Halt: kein Abbruch", False, str(ex)[:120])
        return
    finally:
        solver.StaticSystem.hilfsfesselung = alt
    log = r.info.get("contact_log") or []
    halt = [z for z in log if "Halt für Teile" in z]
    check("mit Halt: kein Abbruch, die Iteration konvergiert",
          r.info.get("contact_converged") and not r.info.get("abbruch"), str(r.info.get("contact_iterations")))
    check("das Protokoll nennt das gehaltene Teil mit Bedingungen und Spalt",
          halt and "Teil 1" in halt[0] and "mit dem kleinsten Spalt" in halt[0] and "mm" in halt[0], str(halt[:1])[:160])
    n_zu = sum(1 for c in r.contact if c["status"] != "offen")
    check("am Ende halten mindestens drei Bedingungen (der Block haengt an drei Punkten)", n_zu >= 3, f"{n_zu} zu")
    Fz = sum(l.F[2] for l in m.case().nodal_loads)
    check("die Auflager tragen die Zuglast ueber die gehaltenen Punkte (Gleichgewicht)",
          abs(float(r.reactions[:, 2].sum()) + Fz) < 1e-6 * abs(Fz), f"{float(r.reactions[:, 2].sum()):.1f} N gegen {-Fz:.1f} N")
    check("die Verschiebung des Blocks ist endlich und klein (kein freies Teil)",
          np.isfinite(r.u).all() and float(np.abs(r.u[:, :3]).max()) < 1e-2, f"{float(np.abs(r.u[:, :3]).max()) * 1e3:.3f} mm")


def test_teile_bedingungen():
    """Eine Bedingung gehoert auch zum Teil ihrer Master-Knoten."""
    from statik3d.contact import ContactSystem
    from statik3d import assemble
    m = block_friction_example()
    system = solver.StaticSystem(m)
    cs = ContactSystem(m, system.K, [], None)
    cs.initialize()
    teile = solver._teile_bedingungen(m, cs)
    namen = {n for n, _kn, _c in teile}
    check("Block (Slave) und Platte (Master) haben Bedingungen", len(teile) >= 2, str(sorted(namen)))
    n_je = {n: len(c) for n, _kn, c in teile}
    check("die Platte als Master-Teil traegt dieselben Bedingungen wie der Block",
          len(set(n_je.values())) == 1, str(n_je))
    # alle Bedingungen oeffnen, dann halten: genau drei mit dem kleinsten Spalt sind zu
    for c in cs.cons:
        c.active = False
        c.g = float(np.random.default_rng(3).uniform(0, 1e-3))
    log = []
    ok = solver._freie_teile_halten(m, cs, log)
    zu = [c for c in cs.cons if c.active]
    kleinste = sorted(cs.cons, key=lambda c: c.g)[:3]
    check("Halt: drei Bedingungen mit dem kleinsten Spalt sind wieder zu, Protokollzeile",
          ok and len(zu) == 3 and set(map(id, zu)) == set(map(id, kleinste)) and log and "gehalten" in log[0], str(log[:1])[:120])
    check("ist genug zu, wird nichts gehalten", not solver._freie_teile_halten(m, cs, []))


def main():
    for t in (test_halt, test_teile_bedingungen):
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
