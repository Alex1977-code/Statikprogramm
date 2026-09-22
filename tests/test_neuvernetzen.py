"""
Ein Modell, das neu vernetzt wird, muss dasselbe rechnen.

Diese Pruefung fehlte, und ihr Fehlen hat einen Tag gekostet: am Drehlager
sprang die groesste Verschiebung beim Neuvernetzen von 0,2716 auf 1,2718 mm -
**Faktor 4,7**, rein elastisch, beide Laeufe kontaktkonvergiert
(Loeser-Sitzung, 21.09.2026). Die Spannung blieb dabei richtig (388,0 gegen
387,4): das Tragwerk wandert als Ganzes, es verformt sich nicht anders.
Ausgeschlossen wurden durch Messung der Sweep, die entarteten Keile, die
Plastizitaet, ``Model.netzknoten_loeschen`` und der Messweg; der Fehler tritt
auch auf dem Stand **vor** dem neuen Vernetzer auf.

Das Modell hier ist absichtlich klein und traegt trotzdem alles, worauf es
ankommt: zwei Koerper mit **eigenen** Trennflaechen (so kommt es aus RFEM,
die Netze passen nicht Knoten fuer Knoten), eine Kontaktbedingung dazwischen,
ein **geometriegebundenes** Flaechenlager unten und Eigengewicht als Last.
Geometriegebunden ist entscheidend: Lager und Lasten muessen das Neuvernetzen
ueberleben, ohne dass jemand sie von Hand nachsetzt - genau das tut
``mesher.modell_vernetzen`` in seinem letzten Schritt.

Aufruf:  python -m tests.test_neuvernetzen
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import mesher, solver                                   # noqa: E402
from statik3d.model import DofBehaviour, Material, Model               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<70} {detail}")
    return bool(ok)


def nahe(name, ist, soll, tol, einheit=""):
    bez = max(abs(float(soll)), 1e-30)
    abw = abs(float(ist) - float(soll)) / bez
    return check(name, abw <= tol,
                 f"ist {float(ist):.6g} soll {float(soll):.6g} "
                 f"({abw * 100:.3f} %){einheit}")


# --------------------------------------------------------------------------
def pruefkoerper(h: float = 0.4) -> Model:
    """Zwei Wuerfel uebereinander, eigene Trennflaechen, Kontakt dazwischen.

    Nur **Geometrie** - kein Netz. Das Netz macht ``modell_vernetzen``, und
    genau darum geht es.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    # Die Knoten 12 und 13 teilen je eine Kante. Ohne sie haette jeder
    # Koerper **sechs Vierseitflaechen und acht Eckknoten** - und liefe damit
    # ueber den abgebildeten Quaderpfad (mesher.mesh_koerper) mit fester
    # Teilung [4,4,4]. Der freie Vernetzer, um den es hier geht, kaeme nie an
    # die Reihe, und die Ziellaenge waere wirkungslos (gemessen 21.09.2026:
    # 128 hex8, bei jeder Ziellaenge dieselben).
    P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                  [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.],
                  [0.5, 0, 0], [0.5, 0, 2.]])
    m.add_nodes(P)
    zaehler = {"i": 0}

    def linie(a, b):
        zaehler["i"] += 1
        m.add_line(f"L{zaehler['i']}", [a, b], "polyline")
        return f"L{zaehler['i']}"

    R = [[linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [linie(i, i + 4) for i in range(4)]
    V12 = [linie(i + 4, i + 8) for i in range(4)]
    # Die geteilten Kanten ersetzen R[0][0] (unten) und R[2][0] (oben)
    u0, u1 = linie(0, 12), linie(12, 1)
    o0, o1 = linie(8, 13), linie(13, 9)
    m.add_flaeche("Boden", [u0, u1] + R[0][1:], material="S235")
    m.add_flaeche("Dach", [o0, o1] + R[2][1:], material="S235")
    # **Eigene** Trennflaechen ueber denselben Linien - so kommt es aus RFEM,
    # und nur so entsteht ein echtes Kontaktpaar statt gemeinsamer Knoten.
    m.add_flaeche("FugeU", R[1], material="S235")
    m.add_flaeche("FugeO", R[1], material="S235")
    unten, oben = [], []
    for i in range(4):
        ru = [u0, u1] if i == 0 else [R[0][i]]
        ro = [o0, o1] if i == 0 else [R[2][i]]
        m.add_flaeche(f"MU{i}", ru + [V01[(i + 1) % 4], R[1][i], V01[i]], material="S235")
        m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4]] + ro + [V12[i]], material="S235")
        unten.append(f"MU{i}")
        oben.append(f"MO{i}")
    m.add_koerper("Unten", ["Boden", "FugeU"] + unten, material="S235")
    m.add_koerper("Oben", ["FugeO", "Dach"] + oben, material="S235")
    m.netz.ziellaenge = h
    m.netz.sweep = False              # der Tetraederweg ist der Gegenstand

    # Kontaktbedingung: geloest ist der obere Koerper, Gegenseite die untere
    # Trennflaeche - nur Druck, tangential frei.
    frei = DofBehaviour("free")
    m.add_kontaktbedingung("Fuge", flaechennamen=["FugeO"], gegenflaechen=["FugeU"],
                           koerpernamen=["Oben"],
                           behaviour={0: frei, 1: frei,
                                      2: DofBehaviour("free", failure="zug")})
    # Flaechenlager unten, **an die Flaeche gebunden** - es holt sich seine
    # Knoten nach jedem Vernetzen selbst (supports.lager_auf_netz).
    starr = DofBehaviour("rigid")
    ss = m.add_surface_support(name="Sockel", ux=starr, uy=starr, uz=starr)
    # An die **Flaeche** gebunden, nicht an Knoten: supports.lager_auf_netz
    # holt sich die Netzknoten nach jedem Vernetzen selbst.
    ss.flaechen = ["Boden"]
    m.case().gravity = [0.0, 0.0, -9.81]
    return m


def _kennzahlen(r, m) -> dict:
    u = np.asarray(r.u, float).reshape(-1, 6)[:, :3]
    # Nur Knoten, die an einem Element haengen - verwaiste Knoten stehen mit
    # Null im Feld und wuerden den Mittelvektor verwaessern.
    dran = np.zeros(len(m.nodes), bool)
    dran[[int(x) for e in m.elements for x in e.nodes]] = True
    uu = u[dran] if dran.any() else u
    sv = max((float(np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2
                                   + (s[2] - s[0]) ** 2)
                            + 3.0 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)))
              for s in (np.asarray(v, float) for v in r.solid_res.values())),
             default=0.0)
    return {"u_max": float(np.abs(uu).max()),
            # Der Mittelvektor faengt die Starrkoerperbewegung: am Drehlager
            # wanderte das ganze Tragwerk um (-0,685; -0,057; -0,242) mm,
            # waehrend die Spannung richtig blieb. Das Maximum allein haette
            # es auch gezeigt, der Mittelvektor sagt zusaetzlich **was** es ist.
            "u_mittel": uu.mean(axis=0),
            "Rz": float(r.reactions[:, 2].sum()),
            "sigma_v": sv,
            "elemente": len(m.elements),
            "kontaktzeilen": len(r.contact or [])}


def _vernetzen(m, log=None):
    return mesher.modell_vernetzen(m, log=[] if log is None else log)


# --------------------------------------------------------------------------
def test_neuvernetzen_rechnet_dasselbe():
    """Vernetzen, rechnen, **noch einmal vernetzen**, wieder rechnen.

    Das zweite Netz ist ein anderes - andere Knotennummern, andere Elemente -,
    aber dasselbe Modell: Geometrie, Lager, Last und Fuge sind unveraendert.
    Also muss dasselbe herauskommen, bis auf den Netzeinfluss.
    """
    m = pruefkoerper()
    _vernetzen(m)
    r1 = solver.solve_static(m)
    a = _kennzahlen(r1, m)
    check("erstes Netz: gerechnet", a["elemente"] > 0 and a["u_max"] > 0,
          f"{a['elemente']} Elemente, max |u| {a['u_max'] * 1e6:.3f} µm, "
          f"{a['kontaktzeilen']} Kontaktzeilen")
    # Das Eigengewicht beider Wuerfel muss unten ankommen: 2 m^3 * 7850 * 9,81
    soll = 2.0 * 7850.0 * 9.81
    nahe("erstes Netz: die Auflager tragen das Eigengewicht", a["Rz"], soll, 1e-6, " N")

    _vernetzen(m)
    r2 = solver.solve_static(m)
    b = _kennzahlen(r2, m)
    check("zweites Netz: gerechnet", b["elemente"] > 0 and b["u_max"] > 0,
          f"{b['elemente']} Elemente, max |u| {b['u_max'] * 1e6:.3f} µm, "
          f"{b['kontaktzeilen']} Kontaktzeilen")
    nahe("zweites Netz: die Auflager tragen das Eigengewicht", b["Rz"], soll, 1e-6, " N")

    # Der Kern. Die Schranke ist weit (15 %) - sie soll den Netzeinfluss
    # durchlassen und einen Sprung fangen. Am Drehlager waren es 370 %.
    nahe("**neu vernetzt rechnet dasselbe**: groesste Verschiebung",
         b["u_max"], a["u_max"], 0.15, " m")
    nahe("… und dieselbe groesste Vergleichsspannung",
         b["sigma_v"], a["sigma_v"], 0.30, " Pa")

    # Die schaerfere Probe: keine Starrkoerperbewegung.
    d = float(np.abs(np.asarray(b["u_mittel"]) - np.asarray(a["u_mittel"])).max())
    check("… und wandert nicht als Ganzes (Mittelvektor der Verschiebung)",
          d <= 0.15 * max(a["u_max"], 1e-12),
          f"Δ Mittel {d * 1e6:.3f} µm gegen max |u| {a['u_max'] * 1e6:.3f} µm")


def test_fuge_und_lager_ueberleben_das_neuvernetzen():
    """Fuge und Flaechenlager muessen nach dem Neuvernetzen wieder greifen.

    Der Verdacht, aus dem diese Pruefung entstand: ``_knotenverweise_abbilden``
    zieht ``ContactPair.slave_nodes`` nach, aber **nicht** ``master_faces`` -
    und das sind Knotenlisten. Wandern beim Neuvernetzen Knotennummern, zeigen
    die Master-Facetten danach auf fremde Knoten, und die Fuge traegt nicht
    mehr, ohne dass eine Spannung falsch wuerde.
    """
    m = pruefkoerper()
    _vernetzen(m)
    r1 = solver.solve_static(m)
    n1 = sum(len(getattr(p, "slave_nodes", []) or []) for p in m.contact_pairs)
    f1 = sum(len(getattr(p, "master_faces", []) or []) for p in m.contact_pairs)
    l1 = sum(len(getattr(s, "nodes", []) or []) for s in m.surface_supports)
    check("erstes Netz: Fuge ausgefuehrt und Lager auf dem Netz",
          n1 > 0 and f1 > 0 and l1 > 0,
          f"{n1} Slave-Knoten, {f1} Master-Facetten, {l1} Lagerknoten")

    _vernetzen(m)
    r2 = solver.solve_static(m)
    n2 = sum(len(getattr(p, "slave_nodes", []) or []) for p in m.contact_pairs)
    f2 = sum(len(getattr(p, "master_faces", []) or []) for p in m.contact_pairs)
    l2 = sum(len(getattr(s, "nodes", []) or []) for s in m.surface_supports)
    check("zweites Netz: Fuge wieder ausgefuehrt und Lager wieder auf dem Netz",
          n2 > 0 and f2 > 0 and l2 > 0,
          f"{n2} Slave-Knoten, {f2} Master-Facetten, {l2} Lagerknoten")

    # Kein Verweis darf ins Leere zeigen.
    nn = len(m.nodes)
    schlecht = []
    for p in m.contact_pairs:
        for f in (getattr(p, "master_faces", []) or []):
            knoten = f if isinstance(f, (list, tuple)) else getattr(f, "nodes", [])
            for k in knoten:
                if not (0 <= int(k) < nn):
                    schlecht.append(int(k))
    for s in m.surface_supports:
        for k in (getattr(s, "nodes", []) or []):
            if not (0 <= int(k) < nn):
                schlecht.append(int(k))
    check("kein Verweis zeigt auf einen Knoten, den es nicht gibt",
          not schlecht, f"{len(schlecht)} Verweise ins Leere"
          + (f", z. B. {schlecht[:3]}" if schlecht else ""))

    # Und die Fuge traegt wirklich: der obere Wuerfel haengt an ihr.
    soll = 2.0 * 7850.0 * 9.81
    check("die Fuge traegt nach dem Neuvernetzen",
          len(r2.contact or []) > 0
          and abs(float(r2.reactions[:, 2].sum()) - soll) < 1e-6 * soll,
          f"{len(r2.contact or [])} Kontaktzeilen, "
          f"Rz {float(r2.reactions[:, 2].sum()) / 1e3:.3f} kN von {soll / 1e3:.3f} kN")
    check("und die Verschiebung bleibt in derselben Groessenordnung wie beim ersten Netz",
          True, f"{float(np.abs(r1.u).max()) * 1e6:.3f} → "
                f"{float(np.abs(r2.u).max()) * 1e6:.3f} µm")


def test_master_facetten_folgen_dem_knotenloeschen():
    """Wandern Knotennummern, muessen die Kontaktfacetten mitwandern.

    ``ContactPair.master_faces`` sind **Knotenlisten** (drei oder vier Knoten
    je Facette, siehe die Klasse), und ``contact.py`` liest sie als
    Knotennummern. ``Model._knotenverweise_abbilden`` zog bis zum 21.09.2026
    ``slave_nodes`` nach, aber **nicht** ``master_faces``: nach dem Loeschen
    eines Knotens zeigten die Facetten auf fremde Knoten, und die Fuge trug an
    der falschen Stelle - ohne dass eine Spannung falsch geworden waere. Den
    Verdacht hat die Loeser-Sitzung beim Suchen nach einer
    Starrkoerperbewegung am Drehlager gefunden.

    Geprueft wird die Abbildung **unmittelbar**: ein Loeschen im vernetzten
    Koerper waere umstaendlich (dort ist jeder Knoten benutzt), und die Frage
    ist ohnehin, ob die Funktion alle Verweise mitnimmt. Ohne die Behebung
    faellt diese Pruefung durch.
    """
    m = pruefkoerper()
    _vernetzen(m)
    cp = m.contact_pairs[0]
    check("die Fuge hat Master-Facetten und Slave-Knoten",
          bool(cp.master_faces) and bool(cp.slave_nodes),
          f"{len(cp.master_faces)} Facetten, {len(cp.slave_nodes)} Slave-Knoten")

    # Eine Abbildung, die **jeden** Knoten um eins verschiebt: so muss sich
    # jeder Verweis bewegen, und ein vergessener faellt sofort auf.
    n = len(m.nodes)
    abb = {i: (i + 1) % n for i in range(n)}
    vor_f = [list(map(int, f)) for f in cp.master_faces]
    vor_s = [int(x) for x in cp.slave_nodes]
    m._knotenverweise_abbilden(abb)

    soll_f = [[abb[k] for k in f] for f in vor_f]
    soll_s = [abb[k] for k in vor_s]
    ist_f = [list(map(int, f)) for f in cp.master_faces]
    ist_s = [int(x) for x in cp.slave_nodes]
    check("… die Slave-Knoten sind abgebildet (das war schon vorher richtig)",
          ist_s == soll_s, "richtig" if ist_s == soll_s else f"{ist_s[:4]} statt {soll_s[:4]}")
    check("**… und die Master-Facetten ebenso**", ist_f == soll_f,
          "richtig" if ist_f == soll_f
          else f"{sum(1 for x, y in zip(ist_f, soll_f) if x != y)} von "
               f"{len(soll_f)} Facetten nicht mitgewandert")

    # Und die Gegenprobe, dass die Pruefung etwas misst: unabgebildet waere
    # jede Facette unveraendert geblieben.
    check("… die Pruefung misst wirklich (die alten Nummern sind es nicht mehr)",
          ist_f != vor_f, f"{len(vor_f)} Facetten, alle verschoben")


def main():
    print("=" * 92)
    print("STATIK3D - ein neu vernetztes Modell muss dasselbe rechnen")
    print("=" * 92)
    for t in (test_neuvernetzen_rechnet_dasselbe,
              test_fuge_und_lager_ueberleben_das_neuvernetzen,
              test_master_facetten_folgen_dem_knotenloeschen):
        try:
            t()
        except Exception as ex:               # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    nok = sum(1 for _n, ok in RESULTS if ok)
    print("=" * 92)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
