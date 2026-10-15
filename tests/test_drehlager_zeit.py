"""Rechenzeit-Hebel am Drehlager (Entscheidung des Anwenders vom 15.10.2026).

Am Drehlager rief jeder Newton-Schritt die Ausfall-Iteration der Zugstaebe, und
die rechnete den Kontakt mindestens zweimal, obwohl immer dieselben drei Staebe
ausfielen (altes E0: 852 Kontaktrunden, 442 neue und 315 nachgefuehrte
Zerlegungen). Die Hebel, jeder mit eigenem Schalter an Plastizitaet (Vorgabe aus,
gespeichert nur abweichend, model.NEUE_FELDER):

* Hebel 1 ``ausfall_annehmen``: die Ausfall-Iteration nimmt die Menge der
  vorigen Loesung an und prueft nach - eine zweite Runde nur bei Verletzung.

Pruefmodell: die Platte mit Strebe „nur Zug“ aus tests/test_kontakt_warmstart
(der Schub drueckt die Strebe, sie faellt aus), mit Fliessen (f_y 30 N/mm2).

Aufruf:  python -m tests.test_drehlager_zeit
"""
import contextlib
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_zeit_"), "einstellungen.json")

from statik3d import plastizitaet as pl, solver                # noqa: E402
from tests import test_kontakt_warmstart as kw                 # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


@contextlib.contextmanager
def zaehlen(z: dict):
    """Kontaktlaeufe (aeussere Aufrufe von solve_with_contact), ihre Runden und die
    Aufrufe der Ausfall-Iteration mit der Zahl ihrer Kontaktlaeufe mitschreiben."""
    alt_c, alt_a = solver.solve_with_contact, solver.solve_with_ausfall
    tiefe = [0]
    z.update(laeufe=0, runden=0, ausfall=[])

    def c(*a, **k):
        tiefe[0] += 1
        try:
            erg = alt_c(*a, **k)
        finally:
            tiefe[0] -= 1
        if tiefe[0] == 0:
            z["laeufe"] += 1
            z["runden"] += int(erg[4].get("contact_iterations", 0) or 0)
        return erg

    def a_(*a, **k):
        vor = z["laeufe"]
        erg = alt_a(*a, **k)
        z["ausfall"].append((z["laeufe"] - vor, tuple(erg[3])))
        return erg
    solver.solve_with_contact, solver.solve_with_ausfall = c, a_
    try:
        yield z
    finally:
        solver.solve_with_contact, solver.solve_with_ausfall = alt_c, alt_a


def strebe_von(m) -> int:
    return next(i for i, e in enumerate(m.elements) if e.typ == "truss" and getattr(e, "nur", "") == "zug"
                and str(getattr(e, "group", "")) == "Strebe")


def eps_max(r) -> float:
    return float((r.info.get("plastizitaet") or {}).get("eps_p_max") or 0.0)


# --------------------------------------------------------------------------
SCHALTER = {"ausfall_annehmen": False}


def test_einstellungen():
    print("\n--- Einstellungen der Hebel ---")
    from statik3d.model import NEUE_FELDER, Model
    pz = pl.Plastizitaet()
    for k, v in SCHALTER.items():
        check(f"{k}: Vorgabe {v!r}, in NEUE_FELDER und NEU_15_10",
              getattr(pz, k, None) == v and NEUE_FELDER["plastizitaet"].get(k, object()) == v
              and pl.Plastizitaet.NEU_15_10.get(k, object()) == v, f"{getattr(pz, k, None)!r}")
    m = kw.platte()
    d0 = m.to_dict()["plastizitaet"]
    check("  mit der Vorgabe nicht in der Datei", not any(k in d0 for k in SCHALTER), str(sorted(d0)))
    for k, v in SCHALTER.items():
        setattr(m.plastizitaet, k, not v)
    d1 = m.to_dict()
    m2 = Model.from_dict(d1)
    check("  abweichend gespeichert und geladen",
          all(k in d1["plastizitaet"] for k in SCHALTER)
          and all(getattr(m2.plastizitaet, k) == getattr(m.plastizitaet, k) for k in SCHALTER),
          str({k: d1["plastizitaet"].get(k) for k in SCHALTER}))


# --------------------------------------------------------------------------
# Hebel 1: Ausfall-Iteration "annehmen und nachpruefen"
# --------------------------------------------------------------------------
def test_hebel1():
    print("\n--- Hebel 1: Ausfall-Iteration annehmen und nachprüfen ---")
    erg = {}
    for an in (False, True):
        with zaehlen({}) as z:
            r, t = kw.rechnen(kw.platte(strebe=True, fy=30e6, schalter={"ausfall_annehmen": an}))
        erg[an] = (r, t, z)
        pz = r.info.get("plastizitaet") or {}
        print(f"      {'an ' if an else 'aus'}: {z['laeufe']} Kontaktläufe, {z['runden']} Runden, "
              f"{len(z['ausfall'])} Ausfall-Aufrufe, Läufe je Aufruf {[n for n, _ in z['ausfall']]}, "
              f"{pz.get('iterationen')} Newton, ε_p {eps_max(r) * 100:.6f} %, {t:.2f} s")
    (ra, _ta, za), (rb, _tb, zb) = erg[False], erg[True]
    check("aus: jede Lösung braucht zwei Kontaktläufe (Stand vor dem 15.10.2026)",
          za["ausfall"] and all(n == 2 for n, _ in za["ausfall"]), str([n for n, _ in za["ausfall"]]))
    check("an: nur die erste Lösung des Lastfalls (ohne Annahme) braucht zwei, jede weitere einen",
          zb["ausfall"] and zb["ausfall"][0][0] == 2 and all(n == 1 for n, _ in zb["ausfall"][1:]),
          str([n for n, _ in zb["ausfall"]]))
    check("  dieselben ausgefallenen Stäbe in jeder Lösung",
          [s for _, s in za["ausfall"]] == [s for _, s in zb["ausfall"]], str(zb["ausfall"][-1][1]))
    pa, pb = ra.info.get("plastizitaet") or {}, rb.info.get("plastizitaet") or {}
    du = kw.max_du(ra, rb)
    check("  dasselbe Ergebnis: |Δu| ≤ 1e-9 m, ε_p auf 1e-5, Newton-Schritte gleich, konvergiert",
          du <= 1e-9 and eps_max(ra) > 0 and abs(eps_max(rb) - eps_max(ra)) <= 1e-5 * eps_max(ra)
          and pa.get("iterationen") == pb.get("iterationen")
          and solver.konvergenz_zustand(ra.info) == solver.konvergenz_zustand(rb.info) == "konvergiert",
          f"|Δu| {du:.1e} m, Δε_p {abs(eps_max(rb) - eps_max(ra)):.1e}")
    check("  weniger als 60 % der Kontaktläufe und der Runden",
          zb["laeufe"] < 0.6 * za["laeufe"] and zb["runden"] < 0.6 * za["runden"],
          f"{zb['laeufe']} statt {za['laeufe']} Läufe, {zb['runden']} statt {za['runden']} Runden")

    # Die Nachpruefung: eine falsche Annahme kostet eine zweite Runde und aendert nichts
    print("      Nachprüfung mit falscher Annahme (direkt an solve_with_ausfall):")
    for rx, name in ((0.6, "Schub drückt die Strebe"), (-0.6, "Schub zieht an der Strebe")):
        m = kw.platte(strebe=True, rx=rx, schalter={"ausfall_annehmen": True})   # Vorgabe ist aus
        s = strebe_von(m)
        system = solver.StaticSystem(m)
        F = solver.case_loads(m, {"LF1": 1.0})[0]
        n0 = solver._anfang_ausfall(m, {"LF1": 1.0}, None, None)
        with zaehlen({}) as z0:
            u0, _R, _a, aus0, _l, _k = solver.solve_with_ausfall(m, system, F, n0=n0)
        richtig = set(aus0)
        falsch = {s} ^ richtig
        with zaehlen({}) as z1:
            u1, _R, _a, aus1, log1, _k = solver.solve_with_ausfall(m, system, F, n0=n0, annahme=richtig)
        with zaehlen({}) as z2:
            u2, _R, _a, aus2, log2, _k = solver.solve_with_ausfall(m, system, F, n0=n0, annahme=falsch)
        d1 = float(np.abs(np.asarray(u1) - np.asarray(u0)).max())
        d2 = float(np.abs(np.asarray(u2) - np.asarray(u0)).max())
        check(f"  {name}: richtige Annahme ein Lauf, falsche zwei, dasselbe Ergebnis",
              z1["laeufe"] == 1 and z2["laeufe"] == 2 and aus1 == aus2 == aus0
              and d1 <= 1e-9 and d2 <= 1e-9,
              f"ohne {z0['laeufe']}, richtig {z1['laeufe']}, falsch {z2['laeufe']} Läufe; "
              f"ausgefallen {aus0}; |Δu| {max(d1, d2):.1e} m")
        check("    die Annahme steht im Protokoll der Iteration",
              any("Annahme" in str(x) for x in log1) and any("Annahme" in str(x) for x in log2),
              str([x for x in log2 if "Annahme" in str(x)])[:120])


def main() -> int:
    for t in (test_einstellungen, test_hebel1):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
