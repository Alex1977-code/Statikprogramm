"""Netzabhaengige Zonen an der Gueltigkeitsgrenze und der Wortlaut der
Traglastmeldung (Vorgaben des Anwenders vom 16.10.2026, Punkte 1 und 2).

Punkt 1, woertlich: „Netzabhängige Zonen von der 20-%-Grenze ausnehmen und nur
warnen: ja, wenn (a) die Zone vom Programm als netzabhängig markiert ist, (b)
die Dehnung über 20 % vollständig innerhalb der Zone bleibt, (c) die Rechnung
konvergiert ist und das Gleichgewicht stimmt, (d) die Zone über die Laststufen
nicht wächst. Sonst Ergebnis ‚nicht gültig‘.“

Punkt 2, woertlich: „Kein Gleichgewicht gefunden bei Laststufe X. Mögliche
Ursache: Traglast überschritten oder örtlicher Mechanismus an <Ort>. Letzter
konvergierter Lastanteil: …%.“ Liegt die wachsende Fließzone in einer
netzabhängigen Zone oder an einer Krafteinleitung, heißt es: „örtlicher
Mechanismus an Krafteinleitung – Modell prüfen“.

Geprueft wird:

* die Entscheidung je Bedingung (a) bis (d) an der Funktion selbst,
* an der Ankerplatte aus tests/test_spitzen_abbruch (Lochrand, auffaellige
  Stelle) mit einer kleinen Grenze: bleibt die Ueberschreitung in der Zone,
  ist das Ergebnis gueltig mit WARNUNG; reicht sie hinaus, nicht gueltig mit
  dem Grund (b),
* der Wortlaut am Zugstab aus tests/test_traglast (1,2 F_lim, Fliesszone im
  Stab: „Traglast überschritten oder örtlicher Mechanismus an …“) und am
  selben Stab mit einer Einzellast an einem Knoten (Fliesszone an der
  Krafteinleitung: „örtlicher Mechanismus an Krafteinleitung – Modell prüfen“).

Aufruf:  python -m tests.test_traglast_meldung
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import solver                                         # noqa: E402
from statik3d import plastizitaet as pl                             # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:240]}")
    return ok


# ---------------------------------------------------------------------------
def test_entscheidung():
    print("\n--- 1. Ausnahme der netzabhängigen Zone: die vier Bedingungen ---")
    zone = {1, 2, 3, 4}
    voll = dict(ueber={2, 3}, zonen_el=zone, markiert=True, konvergiert=True, gleichgewicht_ok=True,
                vorher={2, 3})
    ok, gr = pl.grenze_netzabhaengig(**voll)
    check("alle vier erfüllt: ausgenommen, kein Grund", ok and not gr, gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, markiert=False))
    check("(a) keine markierte Zone: nicht ausgenommen, Grund (a)", not ok and any("(a)" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, ueber={2, 3, 9}))
    check("(b) ein Element über der Grenze außerhalb der Zone: Grund (b)",
          not ok and any("(b)" in g and "1 Element" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, konvergiert=False))
    check("(c) nicht konvergiert: Grund (c)", not ok and any("(c)" in g and "konvergiert" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, gleichgewicht_ok=False))
    check("(c) Gleichgewicht nicht erfüllt: Grund (c)", not ok and any("(c)" in g and "Gleichgewicht" in g
                                                                      for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, gleichgewicht_ok=None))
    check("(c) Gleichgewicht nicht bestimmt: nicht ausgenommen", not ok and any("(c)" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, vorher={2}))
    check("(d) in der letzten Laststufe ein Element dazu: die Zone wächst, Grund (d)",
          not ok and any("(d)" in g and "wächst" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, vorher=None))
    check("(d) nur eine Laststufe: Wachstum nicht prüfbar, nicht ausgenommen",
          not ok and any("(d)" in g for g in gr), gr)
    ok, gr = pl.grenze_netzabhaengig(**dict(voll, vorher=set()))
    check("(d) in der vorletzten Laststufe noch nichts über der Grenze: die Zone wächst",
          not ok and any("(d)" in g for g in gr), gr)


def _ankerplatte(grenze, P=0.3e6):
    from tests import test_spitzen_abbruch as T
    m, _ids, _mitte, _e = T.ankerplatte(P=P, abbruch="ingenieurmaessig")
    m.plastizitaet.dehnungsgrenze = grenze
    return m


def test_ankerplatte():
    print("\n--- 2. Ankerplatte: Überschreitung nur in der netzabhängigen Zone am Lochrand ---")
    m = _ankerplatte(0.02)
    r = solver.solve_static(m, workers=1)
    pz = r.info.get("plastizitaet") or {}
    dg = pz.get("dehnungsgrenze") or {}
    g = solver.gueltigkeit(r.info)
    ep = float(pz.get("eps_p_max") or 0.0)
    check("Grenze 2 %: ε_p,max liegt darüber (sonst prüft der Fall nichts)", ep > 0.02, f"{ep * 100:.3f} %")
    check("die Prüfung steht im Ergebnis (Bedingungen und Urteil)",
          isinstance(dg.get("netzabhaengig_pruefung"), dict), str(dg)[:240])
    pr = dg.get("netzabhaengig_pruefung") or {}
    check("(a) die Stelle am Lochrand ist als netzabhängig markiert", pr.get("markiert") is True, str(pr)[:200])
    check("(b) die Elemente über 2 % liegen alle in der Zone", pr.get("ausserhalb") == 0, str(pr)[:200])
    check("(c) konvergiert und im Gleichgewicht", pr.get("konvergiert") is True and pr.get("gleichgewicht_ok") is True,
          str(pr)[:200])
    if dg.get("netzabhaengig"):
        check("ausgenommen: Ergebnis gültig (keine Meldung „nicht gültig“)", not g, g[:200])
        s = r.summary()
        check("… mit WARNUNG in der Zusammenfassung, die die netzabhängige Zone nennt",
              any(z.startswith("WARNUNG") and "netzabhängig" in z for z in s.splitlines()), "")
        check("… und im Protokoll", any(z.startswith("WARNUNG") and "netzabhängig" in z for z in pz.get("log") or []),
              "")
    else:
        # (d) nicht erfuellt: dann muss der Grund (d) genannt und das Ergebnis nicht gueltig sein
        check("nicht ausgenommen: nur wegen (d), nicht gültig mit Grund",
              g.startswith("NICHT gültig") and any("(d)" in x for x in dg.get("ausnahme_nicht") or []), g[:240])
    # Mit 0,6 MN Zuglast fliesst die Platte auch ausserhalb der Zone (gemessen 16
    # von 64 fliessenden Elementen, ε_p,max 33 %); mit 0,3 MN nur die 48 der Zone
    m = _ankerplatte(1e-5, P=0.6e6)
    r = solver.solve_static(m, workers=1)
    dg = (r.info.get("plastizitaet") or {}).get("dehnungsgrenze") or {}
    g = solver.gueltigkeit(r.info)
    check("0,6 MN, Grenze 0,001 %: Überschreitung auch außerhalb der Zone – NICHT gültig",
          g.startswith("NICHT gültig") and "kleiner Verzerrungen" in g, g[:200])
    check("… der Grund (b) steht im Ergebnis und im Text",
          any("(b)" in x for x in dg.get("ausnahme_nicht") or []) and "(b)" in g, str(dg.get("ausnahme_nicht"))[:200])


def test_wortlaut():
    print("\n--- 3. Wortlaut der Traglastmeldung ---")
    from tests import test_traglast as T
    muster = re.compile(r"^Kein Gleichgewicht gefunden bei Laststufe \d+ \([0-9,]+ % der Last\)\. "
                        r"Mögliche Ursache: (.+)\. Letzter konvergierter Lastanteil: [0-9,]+ %\.")
    m = T.zugstab(1.2, "tet4")
    r = solver.solve_static(m, workers=1)
    tl = (r.info.get("plastizitaet") or {}).get("traglast") or {}
    t = str(tl.get("text", ""))
    mt = muster.match(t)
    check("Zugstab 1,2 F_lim: der Satz des Anwenders", mt is not None, t)
    check("… Ursache „Traglast überschritten oder örtlicher Mechanismus an <Ort>“ mit Körper und Element",
          mt is not None and mt.group(1).startswith("Traglast überschritten oder örtlicher Mechanismus an ")
          and "Element" in mt.group(1), mt.group(1) if mt else "")
    check("… nicht „an Krafteinleitung“ (die Fließzone liegt im Stab)", "Krafteinleitung" not in t, "")
    lam = float(tl.get("lastfaktor", -1))
    check("… der letzte konvergierte Lastanteil ist der Lastfaktor in Prozent",
          f"{lam * 100:.2f}".replace(".", ",").rstrip("0").rstrip(",") in t.replace(" ", ""), f"λ {lam}")
    ort = tl.get("ort") or {}
    X = np.asarray(ort.get("xyz") or [9, 9, 9], float)
    check("… der Ort liegt im fließenden Teil (x ≤ 0,8 L)", X[0] <= 0.8 * T.L_ZUG + 1e-9, str(X))
    g = solver.gueltigkeit(r.info)
    check("… NICHT gültig mit diesem Satz", g.startswith("NICHT gültig: Kein Gleichgewicht gefunden"), g[:120])
    # Einzellast an einem Knoten des fliessenden Stabs (ohne elastischen Kopf)
    # (gemessen: 0,5 F_lim konvergiert mit ε_p 18,6 %, 1,0 F_lim nicht)
    m = T.zugstab(0.5, "tet4")
    for e in m.elements:
        e.mat = "S355"
    lc = m.load_cases["LF1"]
    lc.nodal_loads = lc.nodal_loads[:1]
    k = int(lc.nodal_loads[0].node)
    lc.nodal_loads[0].F = [1.0 * T.F_LIM, 0.0, 0.0, 0.0, 0.0, 0.0]
    r = solver.solve_static(m, workers=1)
    tl = (r.info.get("plastizitaet") or {}).get("traglast") or {}
    t = str(tl.get("text", ""))
    check("Einzellast F_lim an einem Knoten: kein Gleichgewicht", tl.get("ueberschritten") is True, t[:160])
    mt = muster.match(t)
    check("… der Satz des Anwenders mit „örtlicher Mechanismus an Krafteinleitung – Modell prüfen“",
          mt is not None and mt.group(1).startswith("örtlicher Mechanismus an Krafteinleitung – Modell prüfen"), t)
    ort = tl.get("ort") or {}
    el = ort.get("element")
    check("… das Element des Orts hängt am belasteten Knoten",
          el is not None and k in [int(x) for x in m.elements[int(el)].nodes], f"Element {el}, Knoten {k}")


def main():
    test_entscheidung()
    test_wortlaut()
    test_ankerplatte()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
