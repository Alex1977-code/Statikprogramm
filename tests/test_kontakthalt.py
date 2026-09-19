"""Halt fuer Teile ohne geschlossene Bedingung (17.09.2026).

Der nach oben gezogene Block des Beispiels "Block mit Reibung" verliert im
zweiten Schritt (fast) alle Kontaktbedingungen; ohne Halt ist das System
singulaer (tests/test_abbruch.py prueft diesen Abbruch mit abgeschaltetem
Halt). Mit dem Halt bleiben Bedingungen mit dem kleinsten Spalt geschlossen,
der Schritt wird noch einmal geloest, die Iteration konvergiert - und weil
der Block am Ende an den gehaltenen Punkten zieht, hebt er wirklich ab: der
Abbruch kommt dann mit der gehaltenen Lage als Teilergebnis und dem Zeiger.
Ein Stift, dessen gehaltene Punkte in Druck enden, laeuft durch.

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
    """Der nach oben gezogene Block: der Halt rettet den Schritt (kein
    singulaeres System mehr), aber am Ende zieht der Block an den gehaltenen
    Punkten - er hebt wirklich ab. Dann kommt der Abbruch mit der gehaltenen
    Lage als Teilergebnis und dem Zeiger, statt eines stillen Ergebnisses."""
    m = _hochgezogen()
    alt = solver.StaticSystem.hilfsfesselung
    solver.StaticSystem.hilfsfesselung = lambda self: False
    ex = None
    try:
        solver.solve_static(m)
    except RuntimeError as e:
        ex = e
    finally:
        solver.StaticSystem.hilfsfesselung = alt
    check("Block nach oben gezogen: Abbruch, weil die gehaltenen Punkte Zug tragen (er hebt wirklich ab)",
          isinstance(ex, solver.KontaktAbbruch) and "gehaltenen Kontaktpunkten" in str(ex) and "Gleichgewicht" in str(ex),
          str(ex)[:140])
    if not isinstance(ex, solver.KontaktAbbruch):
        return
    r = ex.teilergebnis
    log = (r.info.get("contact_log") if r is not None else None) or []
    halt = [z for z in log if "Halt für Teile" in z]
    check("das Protokoll nennt das gehaltene Teil mit Bedingungen und Spalt",
          halt and "Teil 1" in halt[0] and "mit dem kleinsten Spalt" in halt[0] and "mm" in halt[0], str(halt[:1])[:160])
    check("das Teilergebnis ist die gehaltene Lage: endliche, kleine Verschiebung, Kontaktzustand mit gehaltenen Punkten",
          r is not None and np.isfinite(r.u).all() and float(np.abs(r.u[:, :3]).max()) < 1e-2
          and sum(1 for c in r.contact if c["status"] != "offen") >= 3,
          f"{float(np.abs(r.u[:, :3]).max()) * 1e3:.3f} mm" if r is not None else "")
    s = (r.singular if r is not None else None) or []
    check("Zeiger: der Block hebt ab und haengt an gehaltenen Punkten unter rund 90 kN Zug",
          s and s[0].art == "hebt ab" and "gehaltenen Punkten" in s[0].text and "kN Zug" in s[0].text
          and s[0].koerper == ["Teil 1"], str([x.text[:100] for x in s[:1]]))
    check("die Nummer der letzten geloesten Iteration ist die konvergierte, nicht 0", ex.iteration >= 2, str(ex.iteration))


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


def test_zug_am_teil_gemessen():
    """Ein Teil, das viel Druck abträgt, hebt nicht ab, weil an ein paar
    gehaltenen Punkten wenig zieht. Am Drehlager brach die Rechnung deswegen
    ab: 0,7 bis 20 kN Zug gegen 15 232 kN Schraubenvorspannung und 217,6 kN
    größte Kontaktkraft (19.09.2026, „kann es sein dass die abbruchschranke
    das problem ist“)."""
    from statik3d import solver as slv
    from statik3d.contact import Constraint

    class _CS:
        f_ref = 1.0e6                       # größte Knotenlast 1000 kN

    def _con(fn=0.0, g=0.0, kn=0.0, gehalten=False):
        c = Constraint(kind="surface", dofs=np.zeros(0, int), cn=np.zeros(0), ct=None,
                       g0=0.0, kn=kn, kt=0.0, mu=0.0, node=0, normal=np.array([0.0, 0.0, 1.0]))
        c.active, c.gehalten, c.Fn, c.g = True, gehalten, fn, g
        return c

    # Ein Teil mit 2000 kN Druck und 20 kN Zug an gehaltenen Punkten
    cons = [_con(fn=2.0e6)] + [_con(kn=1.0e6, g=0.02, gehalten=True)]
    alt_tb = slv._teile_bedingungen
    slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons)]
    try:
        zug = slv._gehaltene_unter_zug(None, _CS())
        check("20 kN Zug gegen 2000 kN Druck desselben Teils: kein Abheben", not zug,
              f"{[(n, round(k / 1e3, 1)) for n, _kn, _g, k, _c in zug]} kN")
        # Dasselbe Teil ohne Druck: der Zug hängt an nichts mehr
        cons2 = [_con(kn=1.0e6, g=0.02, gehalten=True)]
        slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons2)]
        zug2 = slv._gehaltene_unter_zug(None, _CS())
        check("ohne Druck bleibt es ein Abheben (der hochgezogene Block)",
              len(zug2) == 1 and abs(zug2[0][3] - 2.0e4) < 1.0, f"{zug2[0][3] / 1e3:.1f} kN" if zug2 else "nichts")
        # Und viel Zug gegen wenig Druck ebenfalls
        cons3 = [_con(fn=1.0e5)] + [_con(kn=1.0e6, g=0.02, gehalten=True)]
        slv._teile_bedingungen = lambda model, cs: [("V30", {1}, cons3)]
        check("20 kN Zug gegen 100 kN Druck (20 %): das ist ein Abheben",
              len(slv._gehaltene_unter_zug(None, _CS())) == 1)
        check("die Schwelle steht als Anteil im Modul", 0.0 < slv.ZUG_ANTEIL < 0.5, str(slv.ZUG_ANTEIL))
    finally:
        slv._teile_bedingungen = alt_tb


def _stift_bedingungen(n_um=8, r=0.05, h=0.08, kn=1e9, kt=1e9):
    """Bedingungen eines Stiftes in einer Bohrung: n_um Knoten je Ring, zwei
    Ringe im Abstand h, Normale radial nach aussen (der Stift schliesst den
    Spalt, wenn er nach aussen geht: cn = -radial). Tangenten sind Umfangs-
    und Achsrichtung. Rueckgabe (Bedingungen, Knotenlage)."""
    from statik3d.contact import Constraint
    cons, lage = [], {}
    for ring, z in enumerate((0.0, h)):
        for k in range(n_um):
            a = 2.0 * np.pi * k / n_um
            radial = np.array([np.cos(a), np.sin(a), 0.0])
            umfang = np.array([-np.sin(a), np.cos(a), 0.0])
            achse = np.array([0.0, 0.0, 1.0])
            knoten = ring * n_um + k
            lage[knoten] = np.array([r * np.cos(a), r * np.sin(a), z])
            dofs = np.array([knoten * 6, knoten * 6 + 1, knoten * 6 + 2])
            cons.append(Constraint(
                kind="surface", dofs=dofs, cn=-radial,
                ct=np.vstack([umfang, achse]), g0=1e-4, kn=kn, kt=kt, mu=0.0,
                node=knoten, normal=radial, label="Stift:Bohrung", haften=True))
    return cons, lage


def _starrmoden(lage, ndof_ges):
    """Feld (ndof_ges, 6): die sechs Starrkoerperbewegungen der Knoten in lage,
    um deren Schwerpunkt, Drehungen mit der groessten Ausladung skaliert."""
    o = np.mean(list(lage.values()), axis=0)
    L = max(float(np.linalg.norm(x - o)) for x in lage.values()) or 1.0
    P = np.zeros((ndof_ges, 6))
    for knoten, x in lage.items():
        r = x - o
        for k in range(3):
            e = np.zeros(3)
            e[k] = 1.0
            P[knoten * 6 + k, k] = 1.0
            P[knoten * 6:knoten * 6 + 3, 3 + k] = np.cross(e, r) / L
    return P


def _kc_auf_moden(cons, lage, schub_halt):
    """Kleinster Eigenwert von P^T Kc P: wie fest die Kontaktsteifigkeit die
    sechs Starrkoerperbewegungen des Stiftes haelt, wenn alle Bedingungen
    offen sind."""
    from statik3d.contact import ContactSystem
    cs = object.__new__(ContactSystem)
    cs.cons, cs.stabilising, cs.phase = cons, False, 1
    for c in cons:
        c.active = False
        c.schub_halt = schub_halt
    ndof = (max(int(c.node) for c in cons) + 1) * 6
    Kc, _Fc = cs.matrices(ndof)
    P = _starrmoden(lage, ndof)
    return float(np.linalg.eigvalsh(P.T @ (Kc @ P)).min())


def test_schub_haelt_den_stift():
    """Ein Stift, dessen Normalbedingungen alle offen stehen, wird von seiner
    Schubbindung gehalten - ohne sie ist die Kontaktsteifigkeit auf allen sechs
    Starrkoerperbewegungen null. Am Drehlager gemessen (19.09.2026): normal
    allein 2,2e-13 bis 3,6e-13, mit dem Schub aller Bedingungen 0,54 bis 0,71."""
    cons, lage = _stift_bedingungen()
    ohne = _kc_auf_moden(cons, lage, schub_halt=False)
    mit = _kc_auf_moden(cons, lage, schub_halt=True)
    check("offene Bedingungen ohne Schubhalt halten den Stift nicht",
          abs(ohne) < 1e-6, f"kleinster Eigenwert {ohne:.3e}")
    check("mit Schubhalt halten sie ihn in allen sechs Starrkoerperbewegungen",
          mit > 1e-3 * 1e9, f"kleinster Eigenwert {mit:.3e}")


def main():
    for t in (test_halt, test_teile_bedingungen, test_zug_am_teil_gemessen,
              test_schub_haelt_den_stift):
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
