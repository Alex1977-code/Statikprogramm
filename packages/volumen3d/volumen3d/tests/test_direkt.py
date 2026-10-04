"""Direktloeser: Nachiteration im SuperLU-Weg (Plan TP 5, O20, 03.10.2026, Theorie 11.21).

Ohne pypardiso (CI, kuenftig Linux) loest SuperLU das schlecht konditionierte System des geneigten Plattenstreifens (30 Grad, p 3) nur auf einen Spannungsfehler
von 1e-5; mit der Nachiteration auf 2,7e-8 (PARDISO: 2,5e-8). Hier die Einheitspruefung am Direktloeser mit einer Zerlegung, die absichtlich um einen bekannten Betrag
falsch ist, und die Hilfe ``ohne_pardiso`` fuer die Faelle, die den SuperLU-Weg erzwingen.

Aufruf: python -m volumen3d.tests.test_direkt
"""
from __future__ import annotations

import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


@contextlib.contextmanager
def ohne_pardiso():
    """``import pypardiso`` schlaegt fehl (None in sys.modules), der Direktloeser nimmt SuperLU - wie in der CI. Der alte Eintrag kommt danach zurueck."""
    fehlt = object()
    alt = sys.modules.get("pypardiso", fehlt)
    sys.modules["pypardiso"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if alt is fehlt:
            sys.modules.pop("pypardiso", None)
        else:
            sys.modules["pypardiso"] = alt  # type: ignore[assignment]


def _matrix(n: int = 60) -> sp.csr_matrix:
    """Tridiagonal, symmetrisch positiv definit, Kondition rund 21: ein gut konditioniertes System, an dem nur die Zerlegung falsch gemacht wird."""
    return sp.diags([-np.ones(n - 1), 2.2 * np.ones(n), -np.ones(n - 1)], [-1, 0, 1], format="csr")


def test_nachiteration():
    from volumen3d.linalg import direkt
    from volumen3d.linalg.direkt import Direktloeser
    K = _matrix()
    n = K.shape[0]
    F = np.random.default_rng(3).standard_normal((n, 3))
    U_exakt = np.linalg.solve(K.toarray(), F)
    with ohne_pardiso():
        d = Direktloeser(K)
        check("ohne pypardiso rechnet SuperLU, Nachiteration Vorgabe 3 Schritte", d.name == "superlu" and d.nachiteration == direkt.NACHITERATION_STANDARD == 3,
              f"{d.name}, {d.nachiteration}")
        # gesunde Zerlegung: omega schon klein, hoechstens ein Schritt, Ergebnis wie die Dichtloesung
        U = d.loesen(F)
        w_gesund = d.letzte_nachiteration["omega_nachher"]
        check(f"gesunde Zerlegung: omega {w_gesund:.1e} <= 1e-14, hoechstens ein Schritt ({d.letzte_nachiteration['schritte']}), Loesung wie dicht auf 1e-13",
              w_gesund <= 1e-14 and d.letzte_nachiteration["schritte"] <= 1 and np.abs(U - U_exakt).max() < 1e-13 * np.abs(U_exakt).max())
        # Zerlegung einer um 1e-9 |K| gestoerten Matrix: der einfache Loeser hat einen Rueckwaertsfehler von rund 1e-9
        rng = np.random.default_rng(4)
        E = K.copy()
        E.data = E.data * (1e-9 * rng.standard_normal(E.data.size))
        d._lu = spla.splu((K + E).tocsc())
        d.nachiteration = 0
        U0 = d.loesen(F)
        _, w0 = d.rueckwaertsfehler(F, U0)
        e0 = np.abs(U0 - U_exakt).max() / np.abs(U_exakt).max()
        d.nachiteration = 3
        U1 = d.loesen(F)
        info = d.letzte_nachiteration
        e1 = np.abs(U1 - U_exakt).max() / np.abs(U_exakt).max()
        check(f"gestoerte Zerlegung: ohne Nachiteration omega {w0:.1e} und Fehler {e0:.1e}; mit ihr omega {info['omega_nachher']:.1e} in {info['schritte']} Schritt(en), Fehler {e1:.1e}",
              w0 > 1e-10 and e0 > 1e-10 and info["omega_nachher"] <= 1e-14 and 1 <= info["schritte"] <= 3 and e1 < 1e-13 and e1 < 1e-3 * e0,
              f"omega vorher {info['omega_vorher']:.1e}")
        # Nachiteration 0: kein Schritt, die Zerlegung bleibt wie sie ist (der Schalter wirkt)
        d.nachiteration = 0
        d.letzte_nachiteration = {"schritte": -1, "omega_vorher": 0.0, "omega_nachher": 0.0}
        check("Nachiteration 0: keine Schritte, Loesung gleich der einfachen", np.array_equal(d.loesen(F), U0) and d.letzte_nachiteration["schritte"] == -1)
        # Zerlegung, deren Schritt das Ergebnis verschlechtert (K/3 statt K: die Iteration divergiert): der Schritt wird verworfen, die Loesung bleibt die einfache
        d._lu = spla.splu((K / 3.0).tocsc())
        d.nachiteration = 3
        U_schlecht = d.loesen(F)
        check(f"divergierende Zerlegung: Schritt verworfen (Schritte {d.letzte_nachiteration['schritte']}), Loesung unveraendert gegenueber der einfachen",
              d.letzte_nachiteration["schritte"] == 0 and np.allclose(U_schlecht, 3.0 * U_exakt, rtol=1e-12))
        # Nullseite: omega zaehlt Zeilen ohne Nenner nicht, kein Fehler, Loesung null
        d._lu = spla.splu(K.tocsc())
        U_null = d.loesen(np.zeros((n, 2)))
        check("rechte Seite null: Loesung null, kein Schritt", not U_null.any() and d.letzte_nachiteration["schritte"] == 0)
        # eine rechte Seite als Vektor liefert einen Vektor
        check("eine rechte Seite als Vektor liefert einen Vektor", d.loesen(F[:, 0]).shape == (n,))


def test_pardiso_weg_unveraendert():
    """Mit pypardiso (falls vorhanden) bleibt der Weg ohne Nachiteration: derselbe Loeser, Name 'pardiso'."""
    from volumen3d.linalg.direkt import Direktloeser
    try:
        import pypardiso  # noqa: F401
    except ImportError:
        check("pypardiso nicht installiert: Pruefung entfaellt", True, "SuperLU-Weg")
        return
    d = Direktloeser(_matrix())
    F = np.random.default_rng(3).standard_normal((60, 2))
    U = d.loesen(F)
    check("mit pypardiso: Name pardiso, keine Nachiteration aufgezeichnet, Loesung wie dicht auf 1e-12",
          d.name == "pardiso" and d.letzte_nachiteration["schritte"] == 0
          and np.abs(U - np.linalg.solve(_matrix().toarray(), F)).max() < 1e-12 * np.abs(U).max())


if __name__ == "__main__":
    sys.exit(lauf([test_nachiteration, test_pardiso_weg_unveraendert]))
