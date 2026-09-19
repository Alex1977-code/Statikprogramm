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
from statik3d.examples_lib import block_friction_example, hall_frame_example   # noqa: E402

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
    alt_halt = solver._freie_teile_halten
    # Ohne Hilfsfesselung und ohne den Halt (17.09.2026) fuer Teile ohne
    # geschlossene Bedingung - nur so entsteht der Abbruch, der hier geprueft wird
    solver.StaticSystem.hilfsfesselung = lambda self: False
    solver._freie_teile_halten = lambda *a, **k: False
    try:
        ex = None
        try:
            solver.solve_static(m)
        except RuntimeError as e:
            ex = e
    finally:
        solver.StaticSystem.hilfsfesselung = alt
        solver._freie_teile_halten = alt_halt
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
          and "Block/Platte" in s[0].fugen and len(s[0].knoten) > 0
          and ("hebt ab" in s[0].text or "verliert den Halt" in s[0].text),
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


class _Halt(Exception):
    """Steht fuer gui.worker.Abgebrochen: die Ausnahme, die der
    Fortschrittsaufruf wirft, sobald der Anwender anhaelt."""


def _bei_meldung(treffer: str, nach: int):
    """Ein Fortschrittsaufruf, der beim ``nach``-ten Mal abbricht, wenn die
    Meldung mit ``treffer`` beginnt - wie ein Klick auf Abbrechen."""
    n = {"i": 0}

    def melden(text, anteil=None):
        if str(text).startswith(treffer):
            n["i"] += 1
            if n["i"] >= nach:
                raise _Halt(str(text))
    return melden


def test_abbruch_behaelt_gerechnete_lastfaelle():
    """Der Anwender startete am 19.09.2026 versehentlich alle Lastfaelle und
    Kombinationen und brach nach dem ersten Lastfall ab - und stand ohne
    Ergebnis da, obwohl dieser Lastfall fertig gerechnet war ("es waere gut
    wenn gerechnete ergebnisse erhalten blieben"). Was fertig ist, haengt
    jetzt an der Ausnahme und bleibt."""
    m = hall_frame_example()
    n_lf, n_ek = len(m.load_cases), len(m.combinations)
    check(f"Probe: {n_lf} Lastfaelle, {n_ek} Kombinationen", n_lf >= 3 and n_ek >= 3,
          f"{n_lf} / {n_ek}")
    try:
        solver.solve_all(m, progress=_bei_meldung("Lastfall ", 2))
        check("der Lauf bricht ab", False, "er lief durch")
        return
    except _Halt as ex:
        an = getattr(ex, "teilanalyse", None)
    check("die Ausnahme traegt die halbe Analyse", an is not None)
    if an is None:
        return
    check("die zwei fertigen Lastfaelle bleiben erhalten", len(an.cases) == 2,
          f"{len(an.cases)}: {list(an.cases)}")
    check("und sie sind vollstaendig gerechnet, kein halbes Ergebnis",
          all(r.u is not None and np.isfinite(r.u).all() for r in an.cases.values()),
          str([r.name for r in an.cases.values()]))
    check("die Analyse sagt, dass sie abgebrochen ist", an.info.get("abgebrochen") is True,
          str(an.info.get("abgebrochen")))
    check("sie sagt auch, wie viel offen blieb",
          an.info.get("offen", {}).get("lastfaelle") == n_lf - 2
          and an.info.get("offen", {}).get("kombinationen") == n_ek,
          str(an.info.get("offen")))
    # Keine Umhuellende ueber zwei von fuenf Lastfaellen: sie saehe aus wie
    # eine ueber alle und waere schlicht falsch
    check("keine Umhuellenden und keine Nachweise ueber einen halben Satz",
          not an.envelopes and an.design is None and an.fatigue is None, str(list(an.envelopes)))
    # Die Zusammenfassung traegt die Anzeige in der Oberflaeche
    check("die Zusammenfassung laesst sich bilden", "Lastfaelle: 2" in an.summary(),
          an.summary().splitlines()[0] if an.summary() else "")
    # Gegenprobe: derselbe Lauf ohne Abbruch rechnet alles
    ganz = solver.solve_all(m)
    check("ohne Abbruch kommt der ganze Satz - der Abbruch aendert nichts am Verfahren",
          len(ganz.cases) == n_lf and not ganz.info.get("abgebrochen") and bool(ganz.envelopes),
          f"{len(ganz.cases)} Lastfaelle, {len(ganz.envelopes)} Umhuellende")
    # Und die geretteten Verschiebungen sind dieselben wie im ganzen Lauf
    d = max(float(np.abs(an.cases[k].u - ganz.cases[k].u).max()) for k in an.cases)
    bez = max(float(np.abs(ganz.cases[list(an.cases)[0]].u).max()), 1e-30)
    check("die geretteten Lastfaelle stimmen mit dem ganzen Lauf ueberein",
          d <= 1e-12 * bez, f"{d:.2e} m von {bez:.2e} m")


def test_abbruch_in_den_kombinationen_behaelt_lastfaelle_und_kombinationen():
    """Bricht es erst in den Kombinationen ab, bleiben alle Lastfaelle und die
    fertigen Kombinationen."""
    m = hall_frame_example()
    n_lf, n_ek = len(m.load_cases), len(m.combinations)
    try:
        solver.solve_all(m, progress=_bei_meldung("Kombination ", 3))
        check("der Lauf bricht in den Kombinationen ab", False, "er lief durch")
        return
    except _Halt as ex:
        an = getattr(ex, "teilanalyse", None)
    check("auch hier haengt die halbe Analyse an der Ausnahme", an is not None)
    if an is None:
        return
    check("alle Lastfaelle sind fertig", len(an.cases) == n_lf, f"{len(an.cases)} / {n_lf}")
    check("und die fertigen Kombinationen bleiben",
          0 < len(an.combinations) < n_ek, f"{len(an.combinations)} / {n_ek}")
    check("offen gemeldet wird der Rest der Kombinationen",
          an.info.get("offen", {}).get("kombinationen") == n_ek - len(an.combinations),
          str(an.info.get("offen")))


def test_ohne_ein_fertiges_ergebnis_wird_nichts_vorgetaeuscht():
    """Bricht es ab, bevor der erste Lastfall fertig ist, gibt es nichts zu
    retten - dann darf auch keine leere Analyse erscheinen."""
    m = hall_frame_example()
    try:
        solver.solve_all(m, progress=_bei_meldung("", 1))    # gleich die erste Meldung
        check("der Lauf bricht sofort ab", False, "er lief durch")
        return
    except _Halt as ex:
        an = getattr(ex, "teilanalyse", None)
    check("ohne ein fertiges Ergebnis bleibt es beim Abbruch ohne Analyse", an is None,
          str(an))


def main():
    for t in (test_abbruch, test_mit_hilfsfesselung_und_normal,
              test_abbruch_behaelt_gerechnete_lastfaelle,
              test_abbruch_in_den_kombinationen_behaelt_lastfaelle_und_kombinationen,
              test_ohne_ein_fertiges_ergebnis_wird_nichts_vorgetaeuscht):
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
