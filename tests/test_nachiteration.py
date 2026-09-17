"""Nachiteration vor dem Singulaer-Urteil (16.09.2026).

Straffedern (1e4-fach die groesste Hauptdiagonale) kosten die Faktorisierung
Stellen: am Drehlager brach LF1 mit Residuum 1,3e-6 als "numerisch
singulaer" ab, obwohl derselbe Aufbau kurz zuvor konvergiert war. Ein
Schritt x += K^-1 (b - K x) mit der vorhandenen Faktorisierung holt die
Stellen zurueck; ein wirklich singulaeres System bleibt ueber der Schranke.

Probe: ein Loeser, dessen Loesung je Schritt 3e-6 relativen Fehler traegt,
kommt nach einer Nachiteration unter 1e-6; einer mit 50 % Fehler nicht.

Aufruf:  python -m tests.test_nachiteration
"""
import os
import sys

import numpy as np
from scipy import sparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


def _system(n=60):
    rng = np.random.default_rng(1)
    B = sparse.random(n, n, density=0.1, random_state=1, format="csr")
    K = (B @ B.T + sparse.identity(n) * n).tocsr()      # symmetrisch, positiv definit
    b = rng.normal(size=n)
    return K, b


def _gestoert(ls, fehler):
    """Den exakten Loeser durch einen mit relativem Fehler ``fehler`` ersetzen."""
    exakt = ls._solve
    rng = np.random.default_rng(7)

    def loesen(rhs):
        x = exakt(rhs)
        return x * (1.0 + fehler * rng.uniform(-1, 1, size=x.shape))
    ls._solve = loesen
    return ls


def test_nachiteration():
    K, b = _system()
    ls = _gestoert(solver.LinearSolver(K, backend="superlu"), 3e-6)
    try:
        x = ls.solve(b)
        r = np.linalg.norm(K @ x - b) / np.linalg.norm(b)
        check("Loeser mit 3e-6 Fehler je Schritt: keine Ausnahme, Residuum nach Nachiteration unter 1e-6",
              r < 1e-6 and ls.nachiterationen >= 1, f"Residuum {r:.1e}, {ls.nachiterationen} Nachiterationen")
    except RuntimeError as ex:
        check("Loeser mit 3e-6 Fehler je Schritt: keine Ausnahme", False, str(ex)[:100])
    ls2 = _gestoert(solver.LinearSolver(K, backend="superlu"), 0.5)
    try:
        ls2.solve(b)
        check("Loeser mit 50 % Fehler: bleibt singulaer (Ausnahme)", False)
    except RuntimeError as ex:
        check("Loeser mit 50 % Fehler: bleibt singulaer, die Meldung nennt die Nachiterationen",
              "singulaer" in str(ex) and "Nachiteration" in str(ex), str(ex)[:120])
    ls3 = solver.LinearSolver(K, backend="superlu")
    x = ls3.solve(b)
    check("exakter Loeser: keine Nachiteration noetig",
          ls3.nachiterationen == 0 and np.linalg.norm(K @ x - b) / np.linalg.norm(b) < 1e-10)


def test_einstellung():
    """Die Schranke und die Zahl der Nachiterationen kommen aus den Einstellungen."""
    from statik3d import parallel
    K, b = _system()
    alt = (parallel.settings().solver_residuum, parallel.settings().solver_nachiterationen)
    try:
        parallel.configure(solver_residuum=1e-4, solver_nachiterationen=0)
        ls = _gestoert(solver.LinearSolver(K, backend="superlu"), 3e-6)
        ls.solve(b)
        check("lockere Schranke 1e-4 ohne Nachiteration: 3e-6 Fehler gehen durch, 0 Nachiterationen",
              ls.nachiterationen == 0 and ls.residuum < 1e-4, f"Residuum {ls.residuum:.1e}")
        check("die Beschreibung nennt die Genauigkeit", "Genauigkeit 0.0001" in ls.beschreibung()
              and "Nachiterationen" not in ls.beschreibung(), ls.beschreibung())
        parallel.configure(solver_residuum=1e-9, solver_nachiterationen=3)
        ls2 = _gestoert(solver.LinearSolver(K, backend="superlu"), 3e-6)
        ls2.solve(b)
        check("strenge Schranke 1e-9: erst die Nachiteration bringt 3e-6 darunter",
              ls2.nachiterationen >= 1 and ls2.residuum < 1e-9, f"Residuum {ls2.residuum:.1e}, {ls2.nachiterationen} Schritte")
        parallel.configure(solver_residuum=1e-9, solver_nachiterationen=0)
        ls3 = _gestoert(solver.LinearSolver(K, backend="superlu"), 3e-6)
        try:
            ls3.solve(b)
            check("strenge Schranke ohne Nachiteration: 3e-6 Fehler sind singulaer", False)
        except RuntimeError as ex:
            check("strenge Schranke ohne Nachiteration: Abbruch, die Meldung nennt Schranke und Einstellung",
                  "Schranke 1e-09" in str(ex) and "Einstellungen" in str(ex), str(ex)[:100])
        gespeichert = parallel.GESPEICHERT
        check("beide Werte werden gespeichert", "solver_residuum" in gespeichert and "solver_nachiterationen" in gespeichert)
    finally:
        parallel.configure(solver_residuum=alt[0], solver_nachiterationen=alt[1])


def main():
    for t in (test_nachiteration, test_einstellung):
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
