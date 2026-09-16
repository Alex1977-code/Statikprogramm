"""Abbruch der Kontakt-Iteration (16.09.2026): die Verformung der letzten
geloesten Iteration bleibt als Teilergebnis erhalten, dazu Zeiger (freie
Bewegungen "hebt ab") auf die Teile, deren Kontaktbedingungen zuletzt alle
offen waren.

Probe: der Block des Beispiels "Block mit Reibung" wird nach oben gezogen.
Im ersten Schritt sind alle Bedingungen geschlossen (loesbar), im zweiten
oeffnen sie alle - der Block ist frei, das System singulaer. Ohne
Hilfsfesselung (hier abgeschaltet) kommt solver.KontaktAbbruch mit der
Loesung des ersten Schritts.

Aufruf:  python -m tests.test_abbruch
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
    print(f"{'OK ' if ok else 'FEHLER'} {name:66s} {detail}")
    return ok


def _hochgezogen():
    m = block_friction_example()
    for l in m.case().nodal_loads:
        l.F[2] = abs(l.F[2])
    return m


def test_abbruch():
    m = _hochgezogen()
    alt = solver.StaticSystem.hilfsfesselung
    solver.StaticSystem.hilfsfesselung = lambda self: False
    try:
        ex = None
        try:
            solver.solve_static(m)
        except RuntimeError as e:
            ex = e
    finally:
        solver.StaticSystem.hilfsfesselung = alt
    check("ohne Hilfsfesselung: KontaktAbbruch mit Nummer der letzten geloesten Iteration",
          isinstance(ex, solver.KontaktAbbruch) and ex.iteration >= 1, f"{type(ex).__name__} {getattr(ex, 'iteration', None)}")
    if not isinstance(ex, solver.KontaktAbbruch):
        return
    check("Meldung nennt den singulaeren Schritt und die offenen Bedingungen",
          "singul" in str(ex) and "offen" in str(ex), str(ex)[:120])
    res = ex.teilergebnis
    check("Teilergebnis: Verschiebung (nn, 6) der letzten Iteration, nach oben, Auflagerkraefte null",
          res is not None and res.u is not None and res.u.shape == (m.nn, 6)
          and float(np.abs(res.u).max()) > 0 and float(np.nanmax(res.u[:, 2])) > 0
          and float(np.abs(res.reactions).max()) == 0.0, str(res and res.u.shape))
    check("Teilergebnis: info mit abbruch, Iteration, nicht konvergiert",
          res is not None and res.info.get("abbruch") and res.info.get("abbruch_iteration") == ex.iteration
          and res.info.get("contact_converged") is False, str({k: v for k, v in (res.info if res else {}).items() if k.startswith(("abbruch", "contact_c"))}))
    n_offen = sum(1 for c in (res.contact if res else []) if c["status"] == "offen")
    check("Teilergebnis: Kontaktzustand des singulaeren Schritts - die Mehrheit der Bedingungen offen",
          res is not None and res.contact and n_offen > len(res.contact) / 2,
          f"{n_offen} von {len(res.contact) if res else 0} offen")
    s = res.singular if res else []
    check("Zeiger: eine freie Bewegung 'hebt ab' fuer den Block, Richtung nach oben und in Lastrichtung, der Grossteil der 90 kN geht ins Nichts",
          len(s) >= 1 and s[0].art == "hebt ab" and float(s[0].t[2]) > 0.5 and float(s[0].t[0]) > 0 and s[0].kraft > 60000.0
          and "Block/Platte" in s[0].fugen and len(s[0].knoten) > 0 and "hebt ab" in s[0].text,
          str([(x.koerper, round(x.kraft), x.fugen) for x in s]))
    check("Zusammenfassung beginnt mit ABBRUCH und nennt die Iteration",
          res is not None and res.summary().startswith("ABBRUCH") and "letzten Kontakt-Iteration" in res.summary())
    check("Spannungen zur letzten Verschiebung nachgerechnet", res is not None and len(res.solid_res) > 0
          and "abbruch_nachlauf" not in res.info, str(res.info.get("abbruch_nachlauf", "")))
    check("Ergebnisinfo als Woerterbuch (fuer Bericht und Web)",
          res is not None and res.info.get("singularitaeten") and res.info["singularitaeten"][0]["art"] == "hebt ab")


def test_mit_hilfsfesselung_und_normal():
    # mit Hilfsfesselung wird der freie Block gefesselt: kein Abbruch, ein Ergebnis mit freier Bewegung
    m = _hochgezogen()
    r = solver.solve_static(m)
    check("mit Hilfsfesselung: kein Abbruch, das Ergebnis nennt die freie Bewegung",
          r is not None and not r.info.get("abbruch") and bool(r.singular), str([x.text for x in r.singular][:1]))
    # der unveraenderte Fall rechnet wie bisher durch
    m2 = block_friction_example()
    r2 = solver.solve_static(m2)
    check("Block mit Auflast: durchgerechnet, konvergiert, ohne Abbruch",
          r2.info.get("contact_converged") and not r2.info.get("abbruch"))


def main():
    for t in (test_abbruch, test_mit_hilfsfesselung_und_normal):
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
