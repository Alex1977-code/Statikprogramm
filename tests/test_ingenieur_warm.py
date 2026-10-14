"""Ingenieurkriterium in warm gestarteten Kontaktlaeufen (08.10.2026 abends).

Das Ingenieurkriterium (solver.ABSCHLUSS_INGENIEUR, Befund B4) beendete bis
hierher nur den kalten Kontaktlauf eines Lastfalls. Jeder Newton-Schritt der
Plastizitaet und jeder Folgelastfall startet aber warm vom vorigen Zustand; pendelte
die Aktivmenge dort, lief der Lauf bis zum Deckel (40 Wechselrunden, dazu bis zu 60
Richtungsrunden). Am Drehlager (Mittel, LF1) betrifft das alle plastischen Laeufe.

Was hier belegt wird - jede Behauptung mit einer Zahl:

1. Kleines Modell mit Fliessen und pendelnder Reibung, warm gestartet: der Block
   aus tests.test_kontakt_pendeln (Lager in Flaechenachsen wie "Starr", Kantenknoten
   mit Reibung in einer Richtung) mit Streckgrenze 60 N/mm2, zwei Laststufen,
   Pendelschutz aus - so pendelt die Gleitrichtung des Kantenknotens in jedem Lauf,
   wie am Drehlager trotz Pendelschutz die Aktivmenge. Die Schranken fuer
   Spannungs- und Verschiebungsaenderung sind weit gesetzt: das Modell ist grob, ein
   Knoten traegt 3 % der Last und pendelt +-10 um bei u_max 0,5 mm; geprueft wird der
   Weg, nicht die Schranke (sie ist kalt in tests.test_kontakt_pendeln geprueft und
   warm dieselbe Funktion). Ohne die Aenderung endete jeder warme Lauf am Deckel
   (69 Runden), die Plastizitaet halbierte elfmal und konvergierte nicht.
2. Folgelastfall (LF2 = 1,05 LF1, Start vom Zustand aus LF1): warm angenommen,
   ohne Neustart; vorher 69 Runden bis zum Deckel.
3. Die Warmstartpruefung (fremder Start) laesst die angenommenen Pendler stehen: wird
   der Zustand eine Runde spaeter angenommen, steht der Kantenknoten gegen seine
   Startrichtung - ohne die Ausnahme setzte die Pruefung ihn zurueck, und der Lauf
   pendelte von vorn (15 statt 6 Runden, gemessen).
4. Wo nichts pendelt, bitgleich: fliessender Reibblock (wie tests.test_fehler_p8, alle
   Kontaktlaeufe der Plastizitaet warm) und Block mit Reibung LF1 -> LF2 -> LF3 (wie
   tests.test_kontaktzustand) rechnen mit und ohne Ingenieurkriterium dasselbe.
   Ein warmer Lauf kehrt oft zu seinem Startzustand zurueck, bevor er streng endet;
   das ist kein Pendeln (_zyklus_bestaetigt).
5. Der Pendelschutz wirkt auch warm: mit ihm konvergiert derselbe fliessende Block
   streng, ohne das Kriterium zu brauchen.
6. Umkehr in Fortsetzungen desselben Lastfalls zaehlt ab Runde 2 (09.10.2026): der
   Pendler des Vorlaufs pendelt im naechsten Newton-Schritt weiter; vorher wurde
   fruehestens in Runde 5 angenommen. Aus einem fremden Start (Folgelastfall) bleibt
   es bei Runde 5.
7. Normalbedingung im Kriterium gegen max(f_tol, 1e-5 |sum F|) (09.10.2026,
   Entscheidung des Anwenders): am Drehlager liegt f_tol (0,95 N) unter der
   Genauigkeit der Loesung (1,3 N), eine streifende Bedingung pendelte mit 1 bis 3 N.
   Am Pruefblock ist die Loesung genauer; geprueft wird mit einem eingespielten Zug
   in der Sicht des Kriteriums: 100 N (ueber f_tol, unter 1e-5 |sum F| = 504 N)
   wird angenommen, 2 000 N nicht - der Lauf endet dann weiter am Deckel.
8. Protokoll je Kontaktrunde (09.10.2026): wo sich die Runde am meisten bewegt
   (Knoten, Bauteil, Verformungsanteil nach Abzug der Starrkoerperbewegung des
   Bauteils) und, wenn das Kriterium geprueft und nicht angenommen hat, an welcher
   Schranke. Am Pruefblock mit Programmschranken: "Δu ... µm > ... µm".

Aufruf:  python -m tests.test_ingenieur_warm
"""
import os
import re as _re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                    # noqa: E402
from tests import test_kontakt_pendeln as tp                   # noqa: E402

RESULTS = []
FY = 60e6


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


class weite_schranken:
    """Delta sigma und Delta u weit, Gleichgewicht, Zug und Durchdringung wie im Programm."""

    def __enter__(self):
        self.alt = (solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL)
        solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL = 1e12, 1.0

    def __exit__(self, *a):
        solver.ABSCHLUSS_SPANNUNG, solver.ABSCHLUSS_WEG_ANTEIL = self.alt


def fliessender_block():
    from statik3d import plastizitaet as pl
    m = tp.lager_in_flaechenachsen()
    m.materials["S"].fy = FY
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2, iterationen=25,
                                     toleranz=1e-3, kontakt="verschachtelt")
    return m


def folgelast_modell(f=1.05):
    m = tp.lager_in_flaechenachsen()
    lf1 = list(m.load_cases)[0]
    basis = [(nl.node, list(nl.F)) for nl in m.load_cases[lf1].nodal_loads]
    m.add_load_case("LF2", "Q")
    for n, F in basis:
        m.load_node(n, Fx=F[0] * f, Fy=F[1] * f, Fz=F[2] * f)
    m.active_case = lf1
    return m, lf1


def laufbuch(res):
    return (res.info or {}).get("laeufe") or []


def warm_angenommen(res):
    return [z for z in (res.info or {}).get("contact_log") or []
            if "Ingenieurkriterium" in z and "(warm gestartet)" in z]


def u_max(res):
    return float(np.linalg.norm(np.asarray(res.u, float)[:, :3], axis=1).max())


def test_fliessen_warm():
    print("\n--- Fliessender Block, pendelnde Gleitrichtung, alle plastischen Laeufe warm ---")
    m = fliessender_block()
    lf = list(m.load_cases)[0]
    with weite_schranken(), tp.schutz(False):
        res = solver.solve_cases(m, [lf])[lf]
    info = res.info or {}
    pz = info.get("plastizitaet") or {}
    lb = laufbuch(res)
    nicht = [e for e in lb if not e.get("konvergiert", True)]
    warm = [e for e in lb if e.get("warm")]
    check("alle Kontaktlaeufe konvergiert, keiner am Deckel",
          lb and not nicht and info.get("contact_converged"),
          f"{len(lb)} Laeufe, {info.get('contact_iterations')} Runden, nicht konvergiert {len(nicht)}, "
          f"Gruende {sorted({str(e.get('grund')) for e in nicht})}")
    zeilen = warm_angenommen(res)
    check("warm gestartete Laeufe enden nach dem Ingenieurkriterium",
          len(warm) >= 2 and len(zeilen) >= 1,
          f"{len(warm)} warme Laeufe, {len(zeilen)} davon nach dem Kriterium: "
          + (zeilen[0][:110] + " …" if zeilen else "keiner"))
    runden = [int(_re.search(r"in Runde (\d+)", z).group(1)) for z in zeilen]
    check("Fortsetzung: Umkehr zaehlt ab Runde 2, angenommen vor Runde 5",
          runden and min(runden) < 5, f"angenommen in den Runden {runden}")
    check("Plastizitaet konvergiert, nicht halbiert",
          pz.get("konvergiert") is True and not pz.get("halbiert"),
          f"Newton {pz.get('iterationen')}, halbiert {pz.get('halbiert')}, fliessend {pz.get('fliessend')}, "
          f"eps_p max {pz.get('eps_p_max')}")
    gg, _Rk = tp.gleichgewicht(m, res)
    check("  gemeldete Kraefte aus derselben Loesung: Gleichgewicht auf 1e-6",
          gg <= 1e-6, f"|sR+sF|/|sF| {gg:.2e}")
    # Zum Vergleich der strenge Weg: Pendelschutz an, Kriterium unnoetig
    m2 = fliessender_block()
    res2 = solver.solve_cases(m2, [lf])[lf]
    pz2 = (res2.info or {}).get("plastizitaet") or {}
    lb2 = laufbuch(res2)
    check("Pendelschutz an (warm wie kalt): streng konvergiert, ohne Ingenieurkriterium",
          lb2 and all(e.get("konvergiert", True) for e in lb2) and pz2.get("konvergiert") is True
          and not any("Ingenieurkriterium" in z for z in (res2.info or {}).get("contact_log") or []),
          f"{len(lb2)} Laeufe, {(res2.info or {}).get('contact_iterations')} Runden, Newton {pz2.get('iterationen')}")
    du = float(np.abs(np.asarray(res.u, float)[:, :3] - np.asarray(res2.u, float)[:, :3]).max())
    de = abs(float(pz.get("eps_p_max") or 0.0) - float(pz2.get("eps_p_max") or 0.0))
    check("  Ergebnis wie streng: max |du| <= 1e-3 u_max, eps_p max auf 1e-3 genau",
          du <= 1e-3 * u_max(res2) and de <= 1e-3 * float(pz2.get("eps_p_max") or 1.0),
          f"max |du| {du * 1e6:.3f} um bei u_max {u_max(res2) * 1e3:.4f} mm ({du / u_max(res2):.1e}), "
          f"eps_p max {pz.get('eps_p_max'):.6e} / {pz2.get('eps_p_max'):.6e}")


def test_folgelastfall():
    print("\n--- Folgelastfall warm vom Zustand des vorigen Lastfalls ---")
    m, lf1 = folgelast_modell(1.05)
    with weite_schranken(), tp.schutz(False):
        erg = solver.solve_cases(m, [lf1, "LF2"])
    r = erg["LF2"]
    info = r.info or {}
    lb = laufbuch(r)
    zr = [int(_re.search(r"in Runde (\d+)", z).group(1)) for z in warm_angenommen(r)]
    check("fremder Start: Umkehr zaehlt erst nach vier Runden in diesem Lauf (Runde 5)",
          zr == [5], f"angenommen in Runde {zr}")
    check("LF2 = 1,05 LF1 warm: nach dem Kriterium angenommen, kein Neustart",
          info.get("contact_converged") and info.get("contact_warm") and warm_angenommen(r)
          and not any(e.get("neustart") for e in lb) and int(info.get("contact_iterations") or 99) <= 10,
          f"konvergiert {info.get('contact_converged')}, warm {info.get('contact_warm')}, "
          f"Runden {info.get('contact_iterations')}, Gruende {[e.get('grund') for e in lb]}")
    F = solver.case_loads(m, {"LF2": 1.0})[0]
    Fk = np.asarray(F[:m.nn * 6], float).reshape(-1, 6)[:, :3].sum(0)
    Rk = np.asarray(r.reactions, float)[:, :3].sum(0)
    gg = float(np.linalg.norm(Rk + Fk) / np.linalg.norm(Fk))
    check("  Gleichgewicht der angenommenen Loesung auf 1e-6", gg <= 1e-6, f"{gg:.2e}")


def test_pendler_bleiben_stehen():
    print("\n--- Warmstartpruefung nach dem Abschluss: die Pendler sind angenommen ---")
    m, lf1 = folgelast_modell(1.0)
    echt = solver._ingenieur_abschluss
    schon = set()

    def erste_warme_ab(model, system, cs, *a):
        # synthetisch: die erste Pruefung jedes warmen Laufs lehnt ab - angenommen wird
        # eine Runde spaeter, der Kantenknoten steht dann gegen seine Startrichtung
        if getattr(cs, "warm", False) and id(cs) not in schon:
            schon.add(id(cs))
            return None
        return echt(model, system, cs, *a)
    solver._ingenieur_abschluss = erste_warme_ab
    try:
        with weite_schranken(), tp.schutz(False):
            erg = solver.solve_cases(m, [lf1, "LF2"])
    finally:
        solver._ingenieur_abschluss = echt
    r = erg["LF2"]
    info = r.info or {}
    zur = [z for z in info.get("contact_log") or [] if z.startswith("Warmstart:")]
    check("angenommen eine Runde spaeter: kein Zuruecksetzen, kein Neustart",
          info.get("contact_converged") and warm_angenommen(r) and not zur
          and not any(e.get("neustart") for e in laufbuch(r)),
          f"Runden {info.get('contact_iterations')}, Zuruecksetzen: {zur[0][:90] if zur else 'keins'}")


def test_normalschranke():
    print("\n--- Normalbedingung im Kriterium: Schranke relativ zur Last ---")
    from statik3d import contact
    alt_zv = contact.ContactSystem.zustand_verstoesse
    alt_nv = getattr(contact.ContactSystem, "normal_verstoesse", None)
    erg = {}
    for z in (100.0, 2000.0):
        # eingespielt: eine geschlossene Bedingung traegt in jeder Loesung z N Zug - nur
        # in der Sicht des Kriteriums (vor dem 09.10.2026 zustand_verstoesse, seither
        # normal_verstoesse); die Iteration selbst bleibt unberuehrt
        def zv(self, u, lam=None, _z=z):
            v = alt_zv(self, u, lam)
            if _z > self.f_tol:
                v["zug"] += 1
                v["zug_max"] = max(v["zug_max"], _z)
            return v

        def nv(self, u, lam=None, _z=z):
            v = alt_nv(self, u, lam)
            if _z > v["zug_max"]:
                v["zug_max"], v["zug_bei"] = _z, ("eingespielt", -1)
            return v
        contact.ContactSystem.zustand_verstoesse = zv
        if alt_nv is not None:
            contact.ContactSystem.normal_verstoesse = nv
        try:
            m = tp.lager_in_flaechenachsen()
            with weite_schranken(), tp.schutz(False):
                erg[z] = (m, solver.solve_static(m))
        finally:
            contact.ContactSystem.zustand_verstoesse = alt_zv
            if alt_nv is not None:
                contact.ContactSystem.normal_verstoesse = alt_nv
    m, r = erg[100.0]
    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    sF = float(np.linalg.norm(np.asarray(F[:m.nn * 6], float).reshape(-1, 6)[:, :3].sum(0)))
    ing = r.info.get("contact_ingenieur") or {}
    zeile = next((z for z in r.info.get("contact_log") or [] if "Ingenieurkriterium" in z), "")
    check("100 N Zug (ueber f_tol, unter 1e-5 |sum F|): angenommen",
          r.info.get("contact_converged") and ing.get("runde"),
          f"Runde {ing.get('runde')}, Schranke {ing.get('normal_grenze')} N, 1e-5 |sum F| = {1e-5 * sF:.0f} N")
    check("  Protokoll nennt Schranke und groessten Verstoss",
          "Schranke" in zeile and "Zug höchstens 100 N" in zeile, zeile[-120:])
    r2 = erg[2000.0][1]
    check("2 000 N Zug (ueber 1e-5 |sum F|): nicht angenommen, Deckel wie bisher",
          not r2.info.get("contact_converged") and not r2.info.get("contact_ingenieur"),
          f"konvergiert {r2.info.get('contact_converged')}, Runden {r2.info.get('contact_iterations')}")


def test_protokoll_je_runde():
    print("\n--- Protokoll je Runde: Ort der groessten Bewegung, Grund der Ablehnung ---")
    m = tp.lager_in_flaechenachsen()
    zeilen = []
    with tp.schutz(False):
        solver.solve_static(m, progress=lambda t, a=None: zeilen.append(str(t)))
    kz = [z for z in zeilen if z.startswith("Kontakt-Iteration ")]
    ort = [z for z in kz[1:] if "größtes Δu" in z and "Verformungsanteil" in z]
    check("ab der zweiten Runde: Knoten, Bauteil und Verformungsanteil der groessten Bewegung",
          kz and len(ort) == len(kz) - 1, (ort[-1][-110:] if ort else str(kz[-1:])[:110]))
    # seit dem 14.10.2026 (Vorschlag 4) misst das Kriterium zuerst Δσ und nennt dann
    # diese Schranke - oder Δσ erfuellt und die Wegschranke
    ab = [z for z in kz if "Ingenieurkriterium nicht erfüllt: Δu" in z
          or "Ingenieurkriterium nicht erfüllt: Δσ_v" in z]
    check("geprueft und nicht angenommen: die Runde nennt die Schranke (Δσ oder Δu)",
          len(ab) >= 1, (ab[-1][-90:] if ab else "keine Zeile"))


def _bit(r0, r1):
    du = float(np.max(np.abs(np.asarray(r1.u) - np.asarray(r0.u))))
    dR = float(np.max(np.abs(np.asarray(r1.reactions) - np.asarray(r0.reactions))))
    return du, dR


def test_ohne_pendeln_bitgleich():
    print("\n--- Wo nichts pendelt, rechnet das Kriterium warm bitgleich ---")
    from tests import test_kontaktzustand as tk
    erg = {}
    for an in (False, True):
        alt = solver.ABSCHLUSS_INGENIEUR
        solver.ABSCHLUSS_INGENIEUR = an
        try:
            erg[an] = (solver.solve_all(tp.fliessender_reibblock()).all_results(),
                       solver.solve_cases(*(lambda mm: (mm[0], [mm[1], "LF2", "LF3"]))(tk._modell())))
        finally:
            solver.ABSCHLUSS_INGENIEUR = alt
    for n in ("LF1", "K1"):
        r0, r1 = erg[False][0][n], erg[True][0][n]
        du, dR = _bit(r0, r1)
        it0, it1 = r0.info.get("contact_iterations"), r1.info.get("contact_iterations")
        check(f"Fliessender Reibblock {n} (Plastizitaet, warm): mit und ohne Kriterium gleich",
              du == 0.0 and dR == 0.0 and it0 == it1,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N, Kontaktrunden {it1} (ohne Kriterium {it0})")
    for n in erg[False][1]:
        r0, r1 = erg[False][1][n], erg[True][1][n]
        du, dR = _bit(r0, r1)
        it0, it1 = r0.info.get("contact_iterations"), r1.info.get("contact_iterations")
        check(f"Block mit Reibung {n} (Folgelastfaelle warm): mit und ohne Kriterium gleich",
              du == 0.0 and dR == 0.0 and it0 == it1,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N, Kontaktrunden {it1} (ohne Kriterium {it0})")


def main() -> int:
    for t in (test_fliessen_warm, test_folgelastfall, test_pendler_bleiben_stehen, test_normalschranke,
              test_protokoll_je_runde, test_ohne_pendeln_bitgleich):
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
