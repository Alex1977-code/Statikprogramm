"""Pendeln mit Periode 2 im Kontaktlauf: erkennen, einfrieren, pruefen (14.10.2026).

Entscheidung des Anwenders vom 14.10.2026 (woertlich): „Bei Pendeln mit
Periode 2 nicht halbieren, sondern erkennen und stabilisieren: Statuswechsel
mit Toleranzen (Durchdringung g_tol, Zug p_tol) oder Status pendelnder Knoten
einfrieren mit anschließender Prüfung. Konvergenz des Kontaktlaufs über
Ingenieurgrößen definieren: Restwechsel nur an Knoten mit zusammen < 0,1 % der
Kontaktkraft und Klaffung/Durchdringung < 1 µm, beides einstellbar.“

Das Pruefmodell pendelt sicher mit Periode 2 (gefunden in einer Suche ueber
rund 380 kleine Modelle, scratchpad kpd_werk/e1, e2, e9): Block B 1 x 1 x 1 m,
tet10, Zellweite 0,2 m, auf einem Flaechenlager „Starr“ an der Sohle (starr,
Ausfall bei Zug, Reibung mu = 0,6 in der Ebene), oben Druck p1 mit Ausmitte
(p1 (1 + 1,8 (2 y - 1)), die Kante y = 0 hebt ab) und Schub 0,7 mu p1 unter
30 Grad. Daneben ein zweiter Block G auf einem reibungsfreien Lager „Grund“
mit 60 N/mm2 - er traegt gut und macht die Kontaktkraft des Modells gross wie
an einem grossen Tragwerk, an dem ein einzelner Knoten pendelt. Pendelschutz
B4 an (Vorgabe). Ohne die Regel endet der Lauf nach 62 Runden am Deckel; ab
Runde 27 wechselt genau ein Knoten der Sohle jede Runde zwischen offen und
geschlossen. Block B steht dabei nahe an der Kippgrenze auf vier Knoten der
Sohle (Resultierende der Lasten bei y = 1,0); einen davon haelt das Programm
waehrend der Iteration geschlossen (Protokoll „Halt für Teile ohne
geschlossene Bedingung“). Darum stimmt die Summe der Auflagerkraefte von
Block B mit und ohne die neue Regel nicht mit der Last ueberein (25 bzw.
29 kN in z bei 500 kN, gemessen 14.10.2026) - das gehoert nicht zu dieser
Regel und wird hier nicht geprueft. In einer Suche ueber rund 680 kleine
Modelle pendelte keines, das ohne Halt oder Hilfsfesselung im Gleichgewicht
steht, mit Periode 2 und kleinem Kraftwechsel (kpd_werk/e9, e13 bis e16).
Das Problem ist homogen in der Last: mit p1 = 0,5 N/mm2 pendelt er mit 28,8 kN (0,048 % der Kontaktkraft) und 0,6 µm, mit
p1 = 5 N/mm2 mit 288 kN (0,44 %) und 6 µm.

Was hier belegt wird:

1. Vorher (Schranken 0 = Regel aus, wie vor dem 14.10.2026): Deckel; mit
   Fliessen halbiert die Plastizitaet an jedem gedeckelten Lauf.
2. p1 = 0,5 N/mm2: erkannt, eingefroren, konvergiert; die Restwechsel liegen
   unter beiden Schranken, das Protokoll nennt Bauteil, Anzahl, Kraftanteil
   und Klaffung. Mit Fliessen halbiert die Plastizitaet nicht.
3. p1 = 5 N/mm2: eingefroren, aber die eingefrorene offene Bedingung ist an
   der letzten Loesung 6 µm durchdrungen - nicht als konvergiert angenommen
   (Grund „pendeln“), das Ergebnis ist vorlaeufig.
4. Gleitrichtungen gehoeren zum Status: am Block auf dem Lager in
   Flaechenachsen (tests.test_kontakt_pendeln, mu 0,6, Schub 1,5 mu p)
   pendeln mit dem Knoten 14 Gleitrichtungen; sie werden mit eingefroren, und
   die Pruefung findet 2,4 % der Kontaktkraft - nicht konvergiert, aber ohne
   die Grenze der Richtungsrunden abzuwarten.
5. Ohne Pendeln bitgleich mit und ohne die Regel; Einstellungen am Modell
   gespeichert und in der Maske.
6. Die Bedingung „Kontaktlauf konvergiert“ im Abbruch der Plastizitaet ist
   vorbereitet (plastizitaet._kontakt_offen) und steht aus
   (KONTAKT_IN_KONVERGENZ): aus nimmt die Plastizitaet Stufen mit gedeckelten
   Kontaktlaeufen an wie bisher, eingeschaltet - nur in dieser Pruefung - erst
   mit einem konvergierten Kontaktlauf (8 statt 6 Newton-Schritte).

Aufruf:  python -m tests.test_pendeln_periode2
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
    tempfile.mkdtemp(prefix="statik3d_pendeln_"), "einstellungen.json")

from statik3d import solver                                    # noqa: E402
from tests import test_kontakt_pendeln as tp                   # noqa: E402

RESULTS = []
FY = 0.3 * 37.09e6  # Streckgrenze Block B: 0,3 der groessten Vergleichsspannung bei p1 0,5 N/mm2


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


@contextlib.contextmanager
def regel(an: bool):
    """solver.PENDEL_STABILISIEREN an oder aus; ohne den Schalter (Stand vor dem
    14.10.2026) bleibt alles, wie es ist."""
    alt = getattr(solver, "PENDEL_STABILISIEREN", None)
    solver.PENDEL_STABILISIEREN = an
    try:
        yield
    finally:
        if alt is None:
            del solver.PENDEL_STABILISIEREN
        else:
            solver.PENDEL_STABILISIEREN = alt


def pendelmodell(p1=0.5e6, p2=60e6, fy=None, laststufen=2, iterationen=10, schwellen=None):
    """Das Pruefmodell (siehe oben); ``fy``: Fliessen im Block B (Block G bleibt
    elastisch), ``schwellen`` (Kraftanteil, Weg) setzt die Einstellungen am
    Modell, (0, 0) schaltet die Regel ab."""
    from statik3d import plastizitaet as pl
    from statik3d.model import Material
    from tests import pruefkoerper as pk
    from tests import pruefmatrix as pm
    mu, rx, w, aus, tol = 0.6, 0.7, 30.0, 0.3, 1e-9
    m = pm.leeres_modell()
    m.materials["S"].nu = 0.3
    pm.block(m, "tet10", (0, 0, 0), (1, 1, 1), 0.2, "B")
    sohle = pm.seiten_von(m, "B", lambda x: abs(x[2]) < tol)
    pm.flaechenlager(m, sohle, "Starr", uz=dict(typ="rigid", failure="zug"),
                     ux=dict(typ="rigid", mu=mu, mu_ref=2), uy=dict(typ="rigid", mu=mu, mu_ref=2))
    deckel = pm.seiten_von(m, "B", lambda x: abs(x[2] - 1) < tol)
    c, s = np.cos(np.radians(w)), np.sin(np.radians(w))
    pk.spannung_auf_seiten(m, deckel, lambda x: np.array(
        [rx * mu * p1 * c, rx * mu * p1 * s, -p1 * (1.0 + 6.0 * aus * (2.0 * x[1] - 1.0))]))
    if p2:
        m.add_material(Material("G", E=m.materials["S"].E, nu=0.3, rho=0.0, fy=None))
        pm.block(m, "tet4", (3, 0, 0), (1, 1, 1), 0.5, "G")
        for e in m.elements:
            if str(e.group) == "G":
                e.mat = "G"
        sohle2 = pm.seiten_von(m, "G", lambda x: abs(x[2]) < tol)
        pm.flaechenlager(m, sohle2, "Grund", uz=dict(typ="rigid", failure="zug"),
                         ux=dict(typ="rigid"), uy=dict(typ="rigid"))
        deckel2 = pm.seiten_von(m, "G", lambda x: abs(x[2] - 1) < tol)
        pk.spannung_auf_seiten(m, deckel2, lambda x: np.array([0.0, 0.0, -p2]))
    m.plastizitaet.an = False
    if fy is not None:
        m.materials["S"].fy = fy
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=laststufen,
                                         iterationen=iterationen, toleranz=1e-3, kontakt="verschachtelt")
    if schwellen is not None:
        m.plastizitaet.pendel_kraft_anteil, m.plastizitaet.pendel_weg = schwellen
    return m


def richtungsmodell():
    """Block auf dem Lager in Flaechenachsen (tests.test_kontakt_pendeln) mit mu 0,6,
    Schub 1,5 mu p in x und 0,5 mu p in y, Ausmitte 1/10, p = 5 N/mm2."""
    alt = (tp.MU, tp.P0)
    tp.MU, tp.P0 = 0.6, 5e6
    try:
        return tp.lager_in_flaechenachsen(typ="tet10", h=0.2, rx=1.5, ry=0.5, ausmitte=0.1)
    finally:
        tp.MU, tp.P0 = alt


def gruende(res):
    return [e.get("grund") for e in (res.info or {}).get("laeufe") or []]


def zeilen(res, *woerter):
    return [z for z in (res.info or {}).get("contact_log") or [] if all(w in z for w in woerter)]


def gleichgewicht(m, res):
    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    Fk = np.asarray(F[:m.nn * 6], float).reshape(-1, 6)[:, :3].sum(0)
    Rk = np.asarray(res.reactions, float)[:, :3].sum(0)
    return float(np.linalg.norm(Rk + Fk) / np.linalg.norm(Fk))


def test_vorher_streng():
    print("\n--- Schranken 0 (Regel aus, wie vor dem 14.10.2026): Deckel ---")
    r = solver.solve_static(pendelmodell(0.5e6, schwellen=(0.0, 0.0)))
    check("p1 0,5 N/mm2, Schranken 0: Deckel, nichts eingefroren",
          not r.info.get("contact_converged") and gruende(r) == ["deckel"] and "contact_pendeln" not in r.info,
          f"konvergiert {r.info.get('contact_converged')}, Gründe {gruende(r)}, Runden {r.info.get('contact_iterations')}")
    with regel(False):
        r0 = solver.solve_static(pendelmodell(0.5e6))
    du = float(np.abs(np.asarray(r.u) - np.asarray(r0.u)).max())
    check("  dasselbe wie mit abgeschalteter Regel (bitgleich)",
          du == 0.0 and r.info.get("contact_iterations") == r0.info.get("contact_iterations"),
          f"max |du| {du:.1e} m, Runden {r.info.get('contact_iterations')} / {r0.info.get('contact_iterations')}")


def test_erkannt_stabilisiert():
    print("\n--- p1 0,5 N/mm2, Vorgabeschranken: erkannt, eingefroren, konvergiert ---")
    m = pendelmodell(0.5e6)
    r = solver.solve_static(m)
    pd = r.info.get("contact_pendeln") or {}
    check("konvergiert, ein Kontaktlauf, Grund leer, früher als der Deckel (62 Runden)",
          r.info.get("contact_converged") and gruende(r) == [""] and r.info.get("contact_iterations", 99) < 62,
          f"Gründe {gruende(r)}, Runden {r.info.get('contact_iterations')}")
    check("  Restwechsel unter beiden Schranken (0,1 % der Kontaktkraft, 1 µm)",
          pd.get("ok") and pd.get("knoten") == 1 and pd.get("anteil", 1.0) < 1e-3 and pd.get("weg", 1.0) < 1e-6,
          f"{pd.get('knoten')} Knoten, {pd.get('kraft', 0) / 1e3:.3g} kN = {100 * pd.get('anteil', 0):.3g} %, "
          f"Weg {pd.get('weg', 0) * 1e6:.3g} µm")
    erk = zeilen(r, "Pendeln mit Periode 2 erkannt")
    ab = zeilen(r, "nach Ingenieurgrößen konvergiert")
    check("  Protokoll: erkannt mit Bauteil und Anzahl, Abschluss mit Kraftanteil und Klaffung je Knoten",
          erk and "B (Starr uz (Ausfall bei Zug)): 1" in erk[0] and ab and "% der Kontaktkraft" in ab[0]
          and "Klaffung/Durchdringung" in ab[0] and "(Knoten " in ab[0] and "öffnet/schließt" in ab[0],
          (ab[0][:220] + " …") if ab else (erk[0][:120] if erk else "keine Zeile"))
    check("  nicht vorläufig", not r.info.get("vorlaeufig")
          and solver.konvergenz_zustand(r.info) == "konvergiert", solver.konvergenz_zustand(r.info))
    lauf = ((r.info.get("laeufe") or [{}])[-1]).get("pendeln") or {}
    check("  Laufbuch: der Lauf trägt die Prüfung", lauf.get("ok") is True and lauf.get("knoten") == 1, str(lauf))


def test_einfrieren_verletzt():
    print("\n--- p1 5 N/mm2: eingefroren, die eingefrorene Bedingung ist 6 µm durchdrungen - nicht konvergiert ---")
    r = solver.solve_static(pendelmodell(5e6))
    pd = r.info.get("contact_pendeln") or {}
    je = list((pd.get("je_knoten") or {}).values())
    check("Pendeln erkannt und eingefroren (ein Knoten, offen)",
          pd.get("knoten") == 1 and zeilen(r, "Pendeln mit Periode 2 erkannt") and je
          and je[0].get("zustand") == "offen", f"{pd.get('knoten')} Knoten, {je[0].get('zustand') if je else ''}")
    check("  Prüfung an der letzten Lösung: Durchdringung über 1 µm",
          pd.get("ok") is False and je and je[0].get("verstoss_weg", 0.0) > 1e-6 and pd.get("weg", 0.0) > 1e-6,
          f"Durchdringung {je[0].get('verstoss_weg', 0) * 1e6 if je else 0:.3g} µm, Weg {pd.get('weg', 0) * 1e6:.3g} µm, "
          f"{100 * pd.get('anteil', 0):.3g} %")
    check("  nicht als konvergiert angenommen: Grund „pendeln“, vorläufig",
          not r.info.get("contact_converged") and gruende(r) == ["pendeln"]
          and solver.konvergenz_zustand(r.info).startswith("NICHT konvergiert")
          and "vorläufig" in solver.konvergenz_zustand(r.info),
          f"{gruende(r)} - {solver.konvergenz_zustand(r.info)}")
    check("  Protokoll sagt, dass die Restwechsel die Schranken überschreiten",
          bool(zeilen(r, "überschreiten die Schranken")), (zeilen(r, "überschreiten") or ["keine"])[0][:160])


def test_gleitrichtungen():
    print("\n--- Gleitrichtungen gehören zum Status: mit eingefroren, geprüft ---")
    # Seit dem 14.10.2026 haelt der Pendelschutz der Gleitrichtung (Vorschlag 2,
    # tests.test_kontakt_warmstart) diese Pendler schon vorher fest; die Regel hier
    # wird ohne ihn geprueft, mit ihm unten
    m = richtungsmodell()
    m.plastizitaet.pendelschutz_winkel = False
    r = solver.solve_static(m)
    pd = r.info.get("contact_pendeln") or {}
    arten = {v.get("art") for v in (pd.get("je_knoten") or {}).values()}
    check("Knoten und Gleitrichtungen eingefroren",
          "Gleitrichtung" in arten and "öffnet/schließt" in arten and pd.get("knoten", 0) >= 2,
          f"{pd.get('knoten')} Knoten, Arten {sorted(arten)}")
    check("  Prüfung: über 0,1 % - nicht konvergiert, ohne die Grenze der Richtungsrunden",
          pd.get("ok") is False and pd.get("anteil", 0.0) > 1e-3 and gruende(r) == ["pendeln"]
          and not zeilen(r, "nicht eingespielt"),
          f"{100 * pd.get('anteil', 0):.3g} %, Weg {pd.get('weg', 0) * 1e6:.3g} µm, Gründe {gruende(r)}, "
          f"Runden {r.info.get('contact_iterations')}")
    r2 = solver.solve_static(richtungsmodell())
    check("  mit dem Pendelschutz der Gleitrichtung (Vorgabe): festgehalten, Prüfung verfehlt, früher",
          gruende(r2) == ["gleitrichtung"] and "contact_pendeln" not in r2.info
          and r2.info.get("contact_iterations", 99) < r.info.get("contact_iterations", 0),
          f"Gründe {gruende(r2)}, Runden {r2.info.get('contact_iterations')} statt {r.info.get('contact_iterations')}")


def test_plastizitaet():
    print("\n--- Mit Fließen: vorher Deckel und Halbieren, nachher erkannt und nicht halbiert ---")
    r0 = solver.solve_static(pendelmodell(0.5e6, fy=FY, schwellen=(0.0, 0.0)))
    pz0 = r0.info.get("plastizitaet") or {}
    lb0 = r0.info.get("laeufe") or []
    check("Schranken 0: Kontaktläufe am Deckel, die Plastizität halbiert",
          pz0.get("halbiert", 0) >= 1 and any(e.get("grund") == "deckel" for e in lb0),
          f"halbiert {pz0.get('halbiert')}, {sum(1 for e in lb0 if e.get('grund') == 'deckel')} von {len(lb0)} "
          f"Läufen am Deckel, Newton {pz0.get('iterationen')}, fließend {pz0.get('fliessend')}")
    r = solver.solve_static(pendelmodell(0.5e6, fy=FY))
    pz = r.info.get("plastizitaet") or {}
    lb = r.info.get("laeufe") or []
    gep = [e for e in lb if e.get("pendeln")]
    check("Vorgabe: kein Halbieren, alle Kontaktläufe konvergiert, Plastizität konvergiert",
          not pz.get("halbiert") and all(e.get("konvergiert") for e in lb) and pz.get("konvergiert") is True,
          f"halbiert {pz.get('halbiert')}, Läufe {len(lb)}, eingefroren in {len(gep)}, Newton {pz.get('iterationen')}, "
          f"fließend {pz.get('fliessend')}")
    check("  … und das Pendeln war da: Läufe mit eingefrorenen Knoten, alle unter den Schranken",
          len(gep) >= 1 and all(e["pendeln"].get("ok") for e in gep),
          str([(e["nr"], e["pendeln"].get("knoten"), round(100 * e["pendeln"].get("anteil", 0), 4)) for e in gep][:6]))


def test_einstellungen():
    print("\n--- Einstellungen am Modell: Vorgabe, Speichern und Laden, Maske ---")
    from statik3d.model import Model
    from statik3d.plastizitaet import Plastizitaet
    pz = Plastizitaet()
    check("Vorgabe 0,1 % und 1 µm", getattr(pz, "pendel_kraft_anteil", None) == 1e-3
          and getattr(pz, "pendel_weg", None) == 1e-6,
          f"{getattr(pz, 'pendel_kraft_anteil', None)}, {getattr(pz, 'pendel_weg', None)}")
    m = Model("x")
    m.plastizitaet.pendel_kraft_anteil, m.plastizitaet.pendel_weg = 2.5e-3, 3e-6
    m2 = Model.from_dict(m.to_dict())
    check("gespeichert und geladen",
          (getattr(m2.plastizitaet, "pendel_kraft_anteil", None), getattr(m2.plastizitaet, "pendel_weg", None))
          == (2.5e-3, 3e-6))
    d = m.to_dict()
    for k in ("pendel_kraft_anteil", "pendel_weg"):
        d["plastizitaet"].pop(k, None)
    m3 = Model.from_dict(d)
    check("ältere Datei ohne die Schlüssel: Vorgabe",
          (getattr(m3.plastizitaet, "pendel_kraft_anteil", None), getattr(m3.plastizitaet, "pendel_weg", None))
          == (1e-3, 1e-6))
    d0 = Model("y").to_dict()["plastizitaet"]
    check("mit der Vorgabe nicht in der Datei (ältere Dateien und ihre Ergebnisdateien passen weiter)",
          "pendel_kraft_anteil" not in d0 and "pendel_weg" not in d0
          and "pendel_kraft_anteil" in m.to_dict()["plastizitaet"], str(sorted(d0)))
    from tests import test_fehler_p15 as p15
    w, app = p15._fenster()
    if not hasattr(w, "sp_pendel_kraft"):
        check("Maske Berechnung: Gruppe „Kontaktlauf“ mit beiden Feldern", False, "keine Felder")
        return
    w.model.plastizitaet.pendel_kraft_anteil, w.model.plastizitaet.pendel_weg = 2.5e-3, 3e-6
    w._plast_anzeigen()
    check("Maske Berechnung zeigt beide Werte (Gruppe „Kontaktlauf“)",
          abs(w.sp_pendel_kraft.value() - 0.25) < 1e-9 and abs(w.sp_pendel_weg.value() - 3.0) < 1e-9,
          f"{w.sp_pendel_kraft.value()} %, {w.sp_pendel_weg.value()} µm")
    w.sp_pendel_kraft.setValue(0.0)
    w.sp_pendel_weg.setValue(0.5)
    w._plast_schreiben(w.model.plastizitaet)
    check("… und schreibt sie ins Modell (0 schaltet die Regel ab)",
          w.model.plastizitaet.pendel_kraft_anteil == 0.0 and abs(w.model.plastizitaet.pendel_weg - 5e-7) < 1e-15,
          f"{w.model.plastizitaet.pendel_kraft_anteil}, {w.model.plastizitaet.pendel_weg}")


def test_kontakt_offen_vorbereitet():
    print("\n--- Bedingung „Kontaktlauf konvergiert“ im Abbruch der Plastizität: vorbereitet, Schalter aus ---")
    from statik3d import plastizitaet as pl
    check("Schalter KONTAKT_IN_KONVERGENZ steht aus (Vorgabe)",
          getattr(pl, "KONTAKT_IN_KONVERGENZ", None) is False, str(getattr(pl, "KONTAKT_IN_KONVERGENZ", None)))
    check("_kontakt_offen ist aufrufbar und ausgeschaltet immer leer",
          hasattr(pl, "_kontakt_offen") and pl._kontakt_offen(object()) == "")
    # Pruefmodell mit Fliessen, Regel aus (Schranken 0), Halbieren aus: die Kontaktlaeufe
    # enden am Deckel, die Plastizitaet urteilt allein an F_p
    alt_h = pl.HALBIEREN_MAX
    pl.HALBIEREN_MAX = 0
    try:
        r0 = solver.solve_static(pendelmodell(0.5e6, fy=FY, schwellen=(0.0, 0.0)))
        pl.KONTAKT_IN_KONVERGENZ = True
        try:
            r1 = solver.solve_static(pendelmodell(0.5e6, fy=FY, schwellen=(0.0, 0.0)))
        finally:
            pl.KONTAKT_IN_KONVERGENZ = False
    finally:
        pl.HALBIEREN_MAX = alt_h
    pz0, pz1 = r0.info.get("plastizitaet") or {}, r1.info.get("plastizitaet") or {}
    deckel0 = sum(1 for e in r0.info.get("laeufe") or [] if e.get("grund") == "deckel")
    check("aus: die Plastizität nimmt die Stufen an, obwohl Kontaktläufe am Deckel enden",
          pz0.get("konvergiert") is True and deckel0 >= 1, f"konvergiert {pz0.get('konvergiert')}, {deckel0} Läufe am Deckel")
    zeilen1 = [z for z in pz1.get("log") or [] if "Kontaktlauf" in z and "nicht konvergiert" in z]
    check("eingeschaltet (nur hier in der Prüfung): Stufe erst mit konvergiertem Kontaktlauf angenommen",
          zeilen1 and int(pz1.get("iterationen", 0)) > int(pz0.get("iterationen", 0)),
          f"Newton {pz0.get('iterationen')} -> {pz1.get('iterationen')}; " + (zeilen1[0][:150] if zeilen1 else "keine Zeile"))


def _bit(r0, r1):
    du = float(np.max(np.abs(np.asarray(r1.u) - np.asarray(r0.u))))
    dR = float(np.max(np.abs(np.asarray(r1.reactions) - np.asarray(r0.reactions))))
    return du, dR


def test_ohne_pendeln_bitgleich():
    print("\n--- Ohne Pendeln: mit und ohne die Regel bitgleich ---")
    from statik3d.examples_lib import block_friction_example
    from tests import test_kontaktzustand as tk
    faelle = [("Block mit Reibung (Beispiel)", lambda: solver.solve_static(block_friction_example())),
              ("Lager in Flächenachsen (B4 löst es)", lambda: solver.solve_static(tp.lager_in_flaechenachsen())),
              ("Block mit Anschlag, tet10", lambda: solver.solve_static(tp.block_auf_reiblager("tet10", 0.25, 1.2, 0.0, True)[0]))]
    for name, f in faelle:
        with regel(False):
            r0 = f()
        r1 = f()
        du, dR = _bit(r0, r1)
        check(f"{name}: gleich", du == 0.0 and dR == 0.0
              and r0.info.get("contact_iterations") == r1.info.get("contact_iterations")
              and "contact_pendeln" not in r1.info,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N, Runden {r1.info.get('contact_iterations')}")
    with regel(False):
        e0 = solver.solve_all(tp.fliessender_reibblock()).all_results()
        f0 = solver.solve_cases(*(lambda mm: (mm[0], [mm[1], "LF2", "LF3"]))(tk._modell()))
    e1 = solver.solve_all(tp.fliessender_reibblock()).all_results()
    f1 = solver.solve_cases(*(lambda mm: (mm[0], [mm[1], "LF2", "LF3"]))(tk._modell()))
    for n in ("LF1", "K1"):
        du, dR = _bit(e0[n], e1[n])
        check(f"Fließender Reibblock {n} (Plastizität, warm): gleich", du == 0.0 and dR == 0.0,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N")
    for n in f0:
        du, dR = _bit(f0[n], f1[n])
        check(f"Block mit Reibung {n} (Folgelastfälle warm): gleich", du == 0.0 and dR == 0.0,
              f"max |du| {du:.1e} m, max |dR| {dR:.1e} N")


def main() -> int:
    for t in (test_vorher_streng, test_erkannt_stabilisiert, test_einfrieren_verletzt, test_gleitrichtungen,
              test_plastizitaet, test_ohne_pendeln_bitgleich, test_einstellungen, test_kontakt_offen_vorbereitet):
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
