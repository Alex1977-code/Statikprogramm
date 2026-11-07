"""Knagge mit Lagerfuge "Ausfall bei Zug", ueber geteilte Knoten an einem gehaltenen
Koerper (05.11.2026, kontakt/pendeln-rt).

Anlass: Mittel-Z mu 0,2 auf fd34e1b brach in Spannstufe 1/3 ab - "kein statisches
Gleichgewicht - V112 hebt ab und haengt an 4 gehaltenen Kontaktpunkten unter 0.9 kN Zug;
V111 ... 7 ... 0.7 kN". Dieselbe Stufe lief auf addd95a durch. V111 und V112 sind Knaggen
unter V36; sie teilen mit V36 je 97 Knoten (mit V108 bzw. V110 je 86), Kontaktbedingungen
haben sie nur aus dem Flaechenlager "Starr" (Ausfall bei Zug). Das Halten vor der Loesung
(solver.VORAB_HALTEN, fd34e1b) pruefte den Rang je Koerper aus dessen eigenen
Kontaktbedingungen und Lagern - die Verbindung ueber geteilte Knoten sah es nicht, hielt
die Knaggen an ihren naechsten Punkten fest, und die strenge Endpruefung fand dort Zug.

Pruefkoerper: Kragblock (Koerper "Block"), an einem Ende eingespannt; am freien Ende
darunter eine Knagge (Koerper "Knagge"), die mit dem Block Knoten teilt und auf einem
Flaechenlager "Starr" mit Ausfall bei Zug steht, ohne Querlast. Eine Last nach oben am
freien Ende hebt die Knagge vom Lager ab (alle Bedingungen offen) - der Block traegt sie.

Geprueft wird: die Knagge gilt nicht als frei (keine Meldung "nicht gehalten", kein Halt),
der Lauf konvergiert, alle Bedingungen der Knagge sind offen, das Ergebnis gleicht dem
ohne das Halten vor der Loesung. Dazu: ein Halt, der am Ende nur Zug unter
pendel_kraft_anteil der Kontaktkraft traegt, bricht nicht ab, sondern wird als offen
angenommen; der nach oben gezogene Block (tests/test_kontakthalt) bricht weiter ab.

Aufruf:  python -m tests.test_knagge_gehalten
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import solver                                         # noqa: E402
from statik3d.model import Volumenkoerper                           # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:200]}")
    return ok


def knagge_modell(F=20e3, h=0.05, druck=0.0):
    """Kragblock 0,6 x 0,2 x 0,2 m (tet4), bei x = 0 eingespannt; Knagge 0,1 x 0,2 x 0,1 m
    darunter am freien Ende (x 0,5 ... 0,6, z -0,1 ... 0), ein Netz - geteilte Knoten;
    Flaechenlager "Starr" uz mit Ausfall bei Zug an der Unterseite der Knagge; Last F nach
    oben am freien Ende des Blocks. ``druck``: dazu ein eigener Sockelkoerper (ohne
    Verbindung, seitlich an zwei Knoten gehalten) auf einer Lagerfuge "Sockel" (Ausfall bei
    Zug) mit so viel Druck - die Kontaktkraft, an der der Zug eines Halts am Ende gemessen
    wird."""
    from tests import pruefkoerper as pk
    from tests import pruefmatrix as pm
    m = pm.leeres_modell()
    m.materials["S"].nu = 0.3
    nx, ny, nz = int(round(0.6 / h)), int(round(0.2 / h)), int(round(0.3 / h))
    q, _ids = pk.quader("tet4", nx, ny, nz, 0.6, 0.2, 0.3)
    neu = {i: m.add_node(*(q.nodes[i] + np.array([0.0, 0.0, -0.1]))) for i in range(q.nn)}
    X = np.asarray(m.nodes, float)
    blk, kng = [], []
    for e in q.elements:
        kn = [neu[int(k)] for k in e.nodes]
        c = X[kn].mean(axis=0)
        if c[2] < 0.0 and c[0] < 0.5:
            continue                                  # unter dem Block nur die Knagge
        i = m.add_element(e.typ, kn, "S", group="Knagge" if c[2] < 0.0 else "Block")
        (kng if c[2] < 0.0 else blk).append(int(i))
    m.koerper["Block"] = Volumenkoerper("Block", elemente=blk)
    m.koerper["Knagge"] = Volumenkoerper("Knagge", elemente=kng)
    benutzt = {int(k) for e in m.elements for k in e.nodes}
    X = np.asarray(m.nodes, float)
    for k in benutzt:
        if abs(X[k, 0]) < 1e-9:
            m.fix(int(k), "all")
    sohle = pm.seiten_von(m, "Knagge", lambda x: abs(x[2] + 0.1) < 1e-9)
    pm.flaechenlager(m, sohle, "Starr", uz=dict(typ="rigid", failure="zug"))
    if druck:
        n_vor = len(m.elements)
        pm.block(m, "tet4", (1.0, 0.0, 0.0), (0.2, 0.2, 0.2), h, "Sockelblock")
        m.koerper["Sockelblock"] = Volumenkoerper("Sockelblock", elemente=list(range(n_vor, len(m.elements))))
        unten = pm.seiten_von(m, "Sockelblock", lambda x: abs(x[2]) < 1e-9)
        pm.flaechenlager(m, unten, "Sockel", uz=dict(typ="rigid", failure="zug"))
        Xs = np.asarray(m.nodes, float)
        sk = sorted({int(k) for i in range(n_vor, len(m.elements)) for k in m.elements[i].nodes})
        ecke = [k for k in sk if abs(Xs[k, 2]) < 1e-9 and abs(Xs[k, 0] - 1.0) < 1e-9 and abs(Xs[k, 1]) < 1e-9]
        ecke2 = [k for k in sk if abs(Xs[k, 2]) < 1e-9 and abs(Xs[k, 0] - 1.2) < 1e-9 and abs(Xs[k, 1]) < 1e-9]
        m.fix(ecke[0], ["ux", "uy"])
        m.fix(ecke2[0], ["uy"])
        oben_s = [k for k in sk if abs(Xs[k, 2] - 0.2) < 1e-9]
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    ende = [k for k in benutzt if abs(X[k, 0] - 0.6) < 1e-9 and X[k, 2] > 0.2 - 1e-9]
    for k in ende:
        m.load_node(int(k), Fz=F / len(ende))
    if druck:
        for k in oben_s:
            m.load_node(int(k), Fz=-druck / len(oben_s))

    m.active_case = "LF1"
    m.plastizitaet.an = False
    return m


def rechnen(m):
    meld = []
    r = solver.solve_static(m, workers=1, progress=lambda t_, *a: meld.append(str(t_)))
    return r, [str(z) for z in r.info.get("contact_log") or []] + meld


def test_knagge():
    print("\n--- Knagge an geteilten Knoten, Lagerfuge Ausfall bei Zug, ohne Querlast ---")
    alt = solver.VORAB_HALTEN
    try:
        solver.VORAB_HALTEN = False
        r0, _l0 = rechnen(knagge_modell())
    finally:
        solver.VORAB_HALTEN = alt
    try:
        r, log = rechnen(knagge_modell())
        fehler = ""
    except Exception as ex:                          # noqa: BLE001
        r, log, fehler = None, [], f"{type(ex).__name__}: {str(ex)[:160]}"
    check("der Lauf bricht nicht ab und konvergiert", r is not None and r.info.get("contact_converged") is True,
          fehler or f"Runden {r.info.get('contact_iterations')}")
    if r is None:
        return
    check("… die Knagge gilt nicht als frei: keine Meldung „nicht gehalten“, kein Halt",
          not any("nicht gehalten" in z or "Halt für Teile" in z for z in log),
          next((z for z in log if "nicht gehalten" in z or "Halt für Teile" in z), "")[:200])
    akt = sum(1 for c in r.contact if c["status"] != "offen")
    check("… die Knagge hebt ab: alle Bedingungen der Lagerfuge offen", len(r.contact) > 0 and akt == 0,
          f"aktiv {akt} von {len(r.contact)}")
    du = float(np.abs(np.asarray(r.u) - np.asarray(r0.u)).max())
    check("… Ergebnis wie ohne das Halten vor der Lösung (u bis 1e-9 relativ)",
          du <= 1e-9 * float(np.abs(np.asarray(r0.u)).max()), f"max |Δu| {du:.2e} m")


def test_kleiner_zug_angenommen():
    print("\n--- Halt mit Zug unter der Toleranz am Ende: als offen angenommen, kein Abbruch ---")
    from statik3d import contact
    m = knagge_modell(F=1e3, druck=2e6)
    # Der Halt wird hier erzwungen: die Knagge gilt als eigenes Teil ohne Verbindung
    # (Gruppierung ueber geteilte Knoten aus) - wie auf fd34e1b
    alt = solver.TEILE_UEBER_KNOTEN
    try:
        solver.TEILE_UEBER_KNOTEN = False
        r, log = rechnen(m)
        fehler = ""
    except Exception as ex:                          # noqa: BLE001
        r, log, fehler = None, [], f"{type(ex).__name__}: {str(ex)[:160]}"
    finally:
        solver.TEILE_UEBER_KNOTEN = alt
    check("ohne Gruppierung: gehalten, am Ende kleiner Zug - als offen angenommen, kein Abbruch",
          r is not None and any("als offen angenommen" in z for z in log),
          fehler or next((z for z in log if "als offen angenommen" in z), "keine Zeile")[:200])
    _ = contact


def main():
    test_knagge()
    test_kleiner_zug_angenommen()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
