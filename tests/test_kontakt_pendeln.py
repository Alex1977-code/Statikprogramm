"""Pendeln der Reibung an der Haftgrenze (Befund B4, 08.10.2026).

Am Drehlager (Mittel, LF1) kam der elastische Kontaktlauf nicht zur Ruhe: fuenf
Reibknoten des Flaechenlagers "Starr" drehten ihre Gleitrichtung jede Runde um
150 bis 180 Grad, zwei weitere sprangen jede Runde zwischen Haften und Gleiten,
bis nach 40 Wechselrunden der Deckel griff. Der Pendelschutz in contact.py
(UMKEHR_HAFTET, PENDEL_EINZELN) aendert nur die Aktualisierung pendelnder
Knoten, nicht die Kontaktbedingung.

Was hier belegt wird - jede Behauptung mit einer Zahl:

1. Kleines Modell, das das Pendeln nachstellt: Block 1 x 1 x 1 m (tet10,
   Kante 0,25 m) auf einem Flaechenlager in Flaechenachsen wie "Starr" am
   Drehlager - Sohle und die untere Haelfte der Seite x = L (Knagge), starr mit
   Ausfall, Reibung mu 0,1 in der Ebene. An der Kante tragen die Sohlenknoten
   Reibung nur in y (x ist die Normale der Knagge), wie die pendelnden Knoten am
   Drehlager. Oben 50 N/mm2 Druck mit Ausmitte 1/12 in y und Schub 1,2 mu p in x,
   0,3 mu p in y. Ohne den Schutz kehrt ein Kantenknoten (Grenze 172 kN) seine
   Gleitrichtung jede Runde genau um (Weg +-9 bis 11 um um die Ausgangslage),
   der Lauf endet nach 75 Runden am Deckel; mit ihm haftet der Knoten, und der
   Lauf konvergiert.
2. Am Endzustand gilt Coulomb: kein haftender Knoten ausserhalb des Kegels
   (Faktor 1 + 1e-6, wie die Iteration), jede Reibkraft gleitender Knoten
   parallel zu ihrem Weg, und das Gleichgewicht stimmt auf die Genauigkeit,
   mit der die Iteration endet: die Gleitrichtungen gelten als eingespielt,
   wenn sie sich um weniger als contact.QUER_TOL = 1e-4 rad drehen, die
   gemeldete Reibkraft kann also um bis zu QUER_TOL mal mu N (hier 500 N bei
   5 MN) neben der Kraft der letzten Loesung liegen.
3. Wo nichts pendelt, rechnet der Schutz bitgleich wie ohne ihn (Block mit
   Reibung aus den Beispielen, Block mit Anschlag) - auch in warm gestarteten
   Laeufen: am fliessenden Reibblock (Plastizitaet mit Kontakt, wie
   tests.test_fehler_p8) starten die Kontaktlaeufe aus dem vorigen Zustand.
   Bis zur Nachbesserung vom 08.10.2026 galt dort jeder gleitend uebernommene
   Knoten, der in der ersten Runde haftete, als pendelnd (gleit_runde -1 traf
   runde_nr - 1); 13 Knoten wurden markiert und einzeln umgestellt, LF1 brauchte
   88 statt 84 Kontaktrunden, K1 97 statt 90.
4. Abschluss nach dem Ingenieurkriterium (solver.ABSCHLUSS_INGENIEUR): pendelt
   etwas, ist der Lauf fertig, wenn sich Vergleichsspannung und Verschiebungen
   zwischen zwei Runden kaum noch aendern und die Loesung im Gleichgewicht ist.
   Am Pendelfall aus 1 (Schutz aus): der Kantenknoten laeuft je Runde +-10 um
   bei u_max 0,4 mm - das ist nicht vernachlaessig, der Lauf endet weiter am
   Deckel. Mit weiten Schranken wird der Zustand angenommen; dann stammen die
   gemeldeten Kraefte aus derselben Loesung (Gleichgewicht auf 1e-6 statt
   5e-3), und das Protokoll nennt den pendelnden Knoten mit Kraft und Weg.

Aufruf:  python -m tests.test_kontakt_pendeln
"""
import contextlib
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import contact, solver                           # noqa: E402
from statik3d.examples_lib import block_friction_example       # noqa: E402
from tests import pruefkoerper as pk                           # noqa: E402
from tests import pruefmatrix as pm                            # noqa: E402

RESULTS = []
MU = 0.1
P0 = 50e6


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


@contextlib.contextmanager
def schutz(an: bool):
    """Pendelschutz an oder aus (Ruecknahmeprobe); ohne die Schalter in contact.py
    (Stand vor dem 08.10.2026) bleibt alles, wie es ist."""
    alt = (getattr(contact, "UMKEHR_HAFTET", None), getattr(contact, "PENDEL_EINZELN", None))
    contact.UMKEHR_HAFTET = contact.PENDEL_EINZELN = an
    try:
        yield
    finally:
        contact.UMKEHR_HAFTET, contact.PENDEL_EINZELN = alt


def lager_in_flaechenachsen(typ="tet10", h=0.25, rx=1.2, ry=0.3, ausmitte=1.0 / 12, L=1.0, H=1.0):
    """Block auf einem Flaechenlager in Flaechenachsen (lokal, wie "Starr" am Drehlager):
    Sohle (Normale -z) und untere Haelfte der Seite x = L (Normale +x), FHG 2 starr mit
    Ausfall bei Zug, FHG 0/1 starr mit Reibung mu bezogen auf die Normale. Oben Druck P0
    mit Ausmitte in y und Schub rx mu P0, ry mu P0."""
    m = pm.leeres_modell()
    m.materials["S"].nu = 0.3
    tol = 1e-9
    pm.block(m, typ, (0, 0, 0), (L, L, H), h, "B")
    sohle = pm.seiten_von(m, "B", lambda x: abs(x[2]) < tol)
    seite = pm.seiten_von(m, "B", lambda x: abs(x[0] - L) < tol and x[2] < 0.5 * H + 1e-9)
    ts, tk = pm.einflussflaechen(m, sohle), pm.einflussflaechen(m, seite)
    alle = sorted(set(ts) | set(tk))
    ss = m.add_surface_support(name="Starr", nodes=alle, areas=[ts.get(n, 0.0) + tk.get(n, 0.0) for n in alle],
                               uz=dict(typ="spring", stiffness=pm.BETTUNG_DREHLAGER, failure="zug"),
                               ux=dict(typ="rigid", mu=MU, mu_ref=2), uy=dict(typ="rigid", mu=MU, mu_ref=2))
    ss.lokal = True
    ss.gruppen = [[2, -1, sorted(ts), [ts[n] for n in sorted(ts)]],
                  [0, 1, sorted(tk), [tk[n] for n in sorted(tk)]]]
    deckel = pm.seiten_von(m, "B", lambda x: abs(x[2] - H) < tol)
    pk.spannung_auf_seiten(m, deckel, lambda x: np.array(
        [rx * MU * P0, ry * MU * P0, -P0 * (1.0 + 6.0 * ausmitte * (2.0 * x[1] / L - 1.0))]))
    m.plastizitaet.an = False
    return m


def block_auf_reiblager(typ="tet10", h=0.25, r=0.6, winkel=0.0, anschlag=False, L=1.0, H=1.0):
    """Block auf einem Flaechenlager wie das Fundament am Drehlager; Schub r mu p unter
    ``winkel`` zur x-Achse. ``anschlag``: die obere Haelfte der Seite x = L liegt an einem
    Flaechenlager ohne Zug (der Rest des Schubs geht dorthin)."""
    m = pm.leeres_modell()
    m.materials["S"].nu = 0.3
    tol = 1e-9
    pm.block(m, typ, (0, 0, 0), (L, L, H), h, "B")
    sohle = pm.seiten_von(m, "B", lambda x: abs(x[2]) < tol)
    knoten, _A = pm.flaechenlager(m, sohle, "Starr",
                                  uz=dict(typ="spring", stiffness=pm.BETTUNG_DREHLAGER, failure="zug"),
                                  ux=dict(typ="rigid", mu=MU, mu_ref=2), uy=dict(typ="rigid", mu=MU, mu_ref=2))
    if anschlag:
        seite = pm.seiten_von(m, "B", lambda x: abs(x[0] - L) < tol and x[2] > 0.5 * H - 1e-9)
        pm.flaechenlager(m, seite, "Anschlag",
                         ux=dict(typ="spring", stiffness=pm.BETTUNG_DREHLAGER, failure="druck"))
    deckel = pm.seiten_von(m, "B", lambda x: abs(x[2] - H) < tol)
    c, s = math.cos(math.radians(winkel)), math.sin(math.radians(winkel))
    pk.spannung_auf_seiten(m, deckel, lambda x: np.array([r * MU * P0 * c, r * MU * P0 * s, -P0]))
    m.plastizitaet.an = False
    return m, knoten


def rechnen(m):
    """Loesen und das Kontaktsystem am Ende festhalten (fuer die Coulomb-Pruefung)."""
    letzte = {}
    alt = contact.ContactSystem.results

    def gemerkt(self):
        letzte["cs"] = self
        return alt(self)
    contact.ContactSystem.results = gemerkt
    try:
        res = solver.solve_static(m)
    finally:
        contact.ContactSystem.results = alt
    return res, letzte.get("cs")


def coulomb(res, cs):
    """(groesster Winkel Reibkraft/Weg gleitender Knoten in Grad, groesstes |Ft|/(mu Fn)
    haftender, Zahl gleitend, Zahl haftend)."""
    u = np.asarray(res.u, float).ravel()
    winkel, kegel = [], []
    for c in cs.cons:
        if not (c.active and c.ct is not None and c.mu > 0 and not c.haften):
            continue
        dt = np.array([c.ct[0] @ u[c.dofs], c.ct[1] @ u[c.dofs]])
        if c.slip and np.linalg.norm(dt) > 0 and np.linalg.norm(c.Ft) > 0:
            cw = float(dt @ c.Ft) / (np.linalg.norm(dt) * np.linalg.norm(c.Ft))
            winkel.append(math.degrees(math.acos(max(-1.0, min(1.0, cw)))))
        elif not c.slip:
            kegel.append(float(np.linalg.norm(c.Ft)) / max(c.mu * max(c.Fn, 0.0), 1e-300))
    return (max(winkel) if winkel else 0.0), (max(kegel) if kegel else 0.0), len(winkel), len(kegel)


def gleichgewicht(m, res):
    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    Fk = np.asarray(F[:m.nn * 6], float).reshape(-1, 6)[:, :3].sum(0)
    Rk = np.asarray(res.reactions, float)[:, :3].sum(0)
    return float(np.linalg.norm(Rk + Fk) / np.linalg.norm(Fk)), Rk


def grund(res):
    return [lauf.get("grund") for lauf in (res.info or {}).get("laeufe") or []]


def test_pendeln_an_der_haftgrenze():
    print("\n--- Lager in Flaechenachsen: ein Kantenknoten mit Reibung in einer Richtung pendelt ---")
    m = lager_in_flaechenachsen()
    with schutz(False):
        res0, _cs0 = rechnen(m)
    check("ohne Pendelschutz: Deckel (das Pendeln ist nachgestellt)",
          not res0.info.get("contact_converged") and "deckel" in grund(res0),
          f"konvergiert {res0.info.get('contact_converged')}, Grund {grund(res0)}, "
          f"Runden {res0.info.get('contact_iterations')}")
    m = lager_in_flaechenachsen()
    with schutz(True):
        res, cs = rechnen(m)
    w, k, n_g, n_h = coulomb(res, cs)
    gg, Rk = gleichgewicht(m, res)
    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    sF = np.asarray(F[:m.nn * 6], float).reshape(-1, 6)[:, :3].sum(0)
    # Die Iteration endet, wenn sich keine Gleitrichtung mehr um QUER_TOL dreht:
    # dieselbe Genauigkeit hier, auf die ganze Reibkraft mu N bezogen
    tol = contact.QUER_TOL * MU * P0 * 1.0
    check("mit Pendelschutz: konvergiert",
          res.info.get("contact_converged") and grund(res) == [""],
          f"Runden {res.info.get('contact_iterations')}, Zerlegungen "
          f"{res.info.get('contact_factorisations')}, gleitend {n_g}, haftend {n_h}")
    check("  Coulomb am Endzustand: Reibkraft parallel zum Weg, Haften im Kegel",
          w < 1.0 and k <= 1.0 + 1e-6, f"max {w:.3f} Grad, |Ft|/muFn haftend max {k:.6f}")
    check("  Gleichgewicht (Genauigkeit der Iteration)",
          gg * float(np.linalg.norm(sF)) <= tol,
          f"|sR+sF| {gg * float(np.linalg.norm(sF)):.1f} N (Grenze {tol:.0f} N), |sR+sF|/|sF| {gg:.2e}")


def test_ohne_pendeln_bitgleich():
    print("\n--- Wo nichts pendelt, aendert der Schutz nichts (bitgleich) ---")
    faelle = [("Block mit Reibung (Beispiel)", block_friction_example),
              ("Block mit Anschlag, tet4", lambda: block_auf_reiblager("tet4", 0.25, 1.2, 0.0, True)[0]),
              ("Block mit Anschlag, tet10", lambda: block_auf_reiblager("tet10", 0.25, 1.2, 0.0, True)[0])]
    for name, bau in faelle:
        with schutz(False):
            r0, _ = rechnen(bau())
        with schutz(True):
            r1, _ = rechnen(bau())
        du = float(np.max(np.abs(np.asarray(r1.u) - np.asarray(r0.u))))
        dR = float(np.max(np.abs(np.asarray(r1.reactions) - np.asarray(r0.reactions))))
        check(f"{name}: dasselbe Ergebnis mit und ohne Schutz",
              du == 0.0 and dR == 0.0 and r1.info.get("contact_converged")
              and r1.info.get("contact_iterations") == r0.info.get("contact_iterations"),
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N, Runden {r1.info.get('contact_iterations')}")


def fliessender_reibblock():
    """Block mit Reibung, Streckgrenze auf 60 % der elastischen Vergleichsspannung,
    dazu K1 = 1,35 LF1 - wie tests.test_fehler_p8._modell mit der Vorgabe
    „verschachtelt“: die Kontaktlaeufe der Plastizitaet starten warm."""
    from statik3d import plastizitaet as pl
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
             if m0.elements[i].mat == "S235")
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * q0
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2, iterationen=40,
                                     toleranz=1e-4, kontakt="verschachtelt")
    m.add_combination("K1", {next(iter(m.load_cases)): 1.35}, "ULS")
    return m


def test_warmstart_ohne_pendeln():
    print("\n--- Warm gestartete Laeufe: gleitend uebernommen und gleich haftend ist kein Pendeln ---")
    erg = {}
    for an in (False, True):
        with schutz(an):
            erg[an] = solver.solve_all(fliessender_reibblock()).all_results()
    for n in ("LF1", "K1"):
        r0, r1 = erg[False][n], erg[True][n]
        du = float(np.max(np.abs(np.asarray(r1.u) - np.asarray(r0.u))))
        dR = float(np.max(np.abs(np.asarray(r1.reactions) - np.asarray(r0.reactions))))
        it0, it1 = r0.info.get("contact_iterations"), r1.info.get("contact_iterations")
        pz = r1.info.get("plastizitaet") or {}
        marken = int(np.count_nonzero(np.asarray((r1.kontaktzustand or {}).get("pendel", []), int)))
        check(f"Fliessender Reibblock {n} (Plastizitaet, warm gestartet): wie ohne Schutz",
              du == 0.0 and dR == 0.0 and it1 == it0 and pz.get("konvergiert") is True,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N, Kontaktrunden {it1} (ohne Schutz {it0}), "
              f"Pendelmarken {marken}")


def test_ingenieurkriterium():
    print("\n--- Abschluss nach dem Ingenieurkriterium, wenn etwas pendelt ---")
    alt = (solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL, solver.ABSCHLUSS_GLEICHGEWICHT)
    m = lager_in_flaechenachsen()
    with schutz(False):
        res0, _ = rechnen(m)
    ing0 = res0.info.get("contact_ingenieur")
    check("Schranken wie im Programm: +-10 um je Runde sind nicht vernachlaessigbar, Deckel",
          not res0.info.get("contact_converged") and "deckel" in grund(res0) and not ing0,
          f"konvergiert {res0.info.get('contact_converged')}, Grund {grund(res0)}")
    try:
        solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL = 1e12, 1.0
        m = lager_in_flaechenachsen()
        with schutz(False):
            res, _cs = rechnen(m)
    finally:
        solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL, solver.ABSCHLUSS_GLEICHGEWICHT = alt
    ing = res.info.get("contact_ingenieur") or {}
    gg, _Rk = gleichgewicht(m, res)
    zeilen = [z for z in res.info.get("contact_log") or [] if "Ingenieurkriterium" in z or "pendeln noch" in z]
    check("weite Schranken: Zustand angenommen, konvergiert",
          res.info.get("contact_converged") and ing.get("runde"),
          f"Runde {ing.get('runde')}, pendelnd {ing.get('pendelnd')}, Richtungen {ing.get('richtungen_pendeln')}")
    check("  gemeldete Kraefte aus derselben Loesung: Gleichgewicht auf 1e-6 (Deckel: 5e-3)",
          gg <= 1e-6 and ing.get("gleichgewicht", 1.0) <= 1e-6, f"|sR+sF|/|sF| {gg:.2e}")
    check("  Protokoll nennt den pendelnden Knoten mit Kraft und Weg (WARNUNG)",
          any(z.startswith("WARNUNG") and "Reibkraft" in z and "µm" in z for z in zeilen),
          (zeilen[-1][:150] + " …") if zeilen else "keine Zeile")


def main() -> int:
    for t in (test_pendeln_an_der_haftgrenze, test_ohne_pendeln_bitgleich, test_warmstart_ohne_pendeln,
              test_ingenieurkriterium):
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
    sys.exit(main())
