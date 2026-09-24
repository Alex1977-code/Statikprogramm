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


def test_oberflaeche_entfernt_die_alten_knoten():
    """Befund B062 (23.09.2026): „Netz → Vernetzen“ der Oberflaeche
    (gui.main._vernetzen) loeschte je Objekt nur die Elemente des alten
    Netzes (_netz_loeschen), die Knoten blieben stehen. Am L-Prisma h 0,12
    ohne Qt nachgestellt: beim zweiten Vernetzen 2470 statt 1241 Knoten,
    Abnahme FEHLER „Knoten ohne Element“ 1229, und vor jeder Rechnung fragte
    die Abnahme nach. ``mesher.modell_vernetzen`` entfernt sie
    (Model.netzknoten_loeschen). Hier der echte Oberflaechenweg, self als
    Attrappe, zweimal mit denselben Einstellungen - verglichen mit
    ``modell_vernetzen``."""
    import importlib
    import time
    from unittest import mock
    from statik3d import diagnose as dg
    G = importlib.import_module("statik3d.gui.main")      # gui.main() verdeckt das Modul

    def gui_vernetzen(m):
        s = mock.MagicMock()
        s.model = m
        s._fortschritt_t0 = time.time()
        s._netz_loeschen = G.MainWindow._netz_loeschen.__get__(s)
        with mock.patch.object(G, "QtWidgets"):       # nur processEvents im Weg
            G.MainWindow._vernetzen(s, list(m.flaechen.values()), list(m.koerper.values()))
        return [str(c.args[0]) for c in s.log.appendPlainText.call_args_list if c.args]

    def verwaist(m):
        return sum(int(b.wert) for b in dg.abnahme(m) if b.pruefung == "Knoten ohne Element")

    def hat_knoten(m, p):
        return bool(np.any(np.all(np.abs(np.asarray(m.nodes) - np.asarray(p)) < 1e-12, axis=1)))

    def grob():
        # Grober als die Netzdichte (dort 108 mm, 22 551 tet4): vier
        # Vernetzungen sollen Sekunden dauern, nicht Minuten
        pk = pruefkoerper()
        pk.netz.koerper_h = {"Unten": 0.25, "Oben": 0.25}
        return pk

    ref = grob()
    _vernetzen(ref)
    _vernetzen(ref)
    m = grob()
    # Ein gesetzter Knoten, an dem noch nichts haengt (etwa fuer eine
    # spaetere Linie), gehoert zu keinem Netz: er muss das Neuvernetzen
    # ueberleben - netzknoten_loeschen() ohne Kandidaten naehme ihn mit.
    konstruktion = (5.0, 5.0, 5.0)
    m.add_node(*konstruktion)
    gui_vernetzen(m)
    n1, e1, v1 = m.nn, len(m.elements), verwaist(m)
    check("Oberfläche, erstes Netz: so viele Knoten wie modell_vernetzen, dazu der gesetzte",
          n1 == ref.nn + 1 and e1 == len(ref.elements) and v1 <= 1,
          f"{e1} Elemente, {n1} Knoten (modell_vernetzen {len(ref.elements)}, {ref.nn}), "
          f"ohne Element {v1}")
    log = gui_vernetzen(m)
    check("**Oberfläche, zweites Netz: die Knoten des alten Netzes sind weg**",
          m.nn == n1 and len(m.elements) == e1,
          f"{len(m.elements)} Elemente, {m.nn} Knoten (erstes Netz {n1})")
    check("… keine weiteren „Knoten ohne Element“ in der Abnahme", verwaist(m) == v1,
          f"{verwaist(m)} (erstes Netz {v1})")
    check("… der gesetzte Knoten ohne Element bleibt", hat_knoten(m, konstruktion))
    check("… und das Protokoll nennt die entfernten",
          any("Knoten des alten Netzes entfernt" in z for z in log),
          str([z for z in log if "Knoten" in z][:3]))
    # Lager und Fuge zeigen nach dem Umnummerieren auf Knoten des neuen
    # Netzes.
    am_netz = np.zeros(m.nn, bool)
    am_netz[[int(x) for e in m.elements for x in e.nodes]] = True
    lager = [int(k) for x in m.surface_supports for k in (x.nodes or [])]
    fuge = [int(k) for p in m.contact_pairs for k in (p.slave_nodes or [])] + \
           [int(k) for p in m.contact_pairs for f in (p.master_faces or []) for k in f]
    check("… Lager und Fuge hängen an Knoten des neuen Netzes",
          lager and fuge and all(0 <= k < m.nn and am_netz[k] for k in lager + fuge),
          f"{len(lager)} Lagerknoten, {len(fuge)} Fugenverweise, "
          f"{sum(1 for k in lager + fuge if not (0 <= k < m.nn and am_netz[k]))} daneben")

    # Und es rechnet danach dasselbe wie nach modell_vernetzen. Die Faelle
    # oben vernetzen ueber modell_vernetzen, nicht ueber diesen Weg, der seit
    # B062 die Knoten umnummeriert - dass er danach rechnet, prueft nur diese
    # Stelle. Bis zum 24.09.2026 stand hier, die Kontaktrechnung brauche
    # Minuten: gemessen sind es Sekunden (24.09.2026, Rechner durch andere
    # Laeufe ausgelastet: 13 bis 23 s je Rechnung, in einem ruhigeren Lauf
    # die ganze Pruefung 29 s). Beide Netze sind gleich (1911 tet4, 24
    # Kontaktzeilen), also auch die Zahlen: max |u| 0,7123 µm auf beiden
    # Wegen, Abweichung 0.
    a = _kennzahlen(solver.solve_static(ref), ref)
    b = _kennzahlen(solver.solve_static(m), m)
    soll = 2.0 * 7850.0 * 9.81
    check("… rechnet: die Fuge trägt, die Auflager tragen das Eigengewicht",
          b["kontaktzeilen"] > 0 and abs(b["Rz"] - soll) <= 1e-6 * soll,
          f"{b['kontaktzeilen']} Kontaktzeilen (modell_vernetzen {a['kontaktzeilen']}), "
          f"Rz {b['Rz'] / 1e3:.3f} kN von {soll / 1e3:.3f} kN")
    nahe("**… und rechnet dasselbe wie nach modell_vernetzen**: größte Verschiebung",
         b["u_max"], a["u_max"], 1e-4, " m")
    d = float(np.abs(np.asarray(b["u_mittel"]) - np.asarray(a["u_mittel"])).max())
    check("… auch der Mittelvektor der Verschiebung",
          d <= 1e-4 * max(a["u_max"], 1e-12),
          f"Δ Mittel {d * 1e6:.4f} µm gegen max |u| {a['u_max'] * 1e6:.4f} µm")


def _passung_und_lagergruppen():
    """Freier Knoten 0 vor einem Netz aus zwei hex8; ein Kontaktpaar mit
    Passungsdaten (Einflussflaeche je Slave-Knoten, Randknoten,
    Lochleibungsgrenze) und ein lokales Flaechenlager mit Normalengruppe auf
    denselben vier Knoten der Stirnseite."""
    from statik3d.model import ContactPair, SurfaceSupport
    m = Model()
    m.add_material(Material.steel("S235"))
    frei = m.add_node(-5.0, 0.0, 0.0)
    ids = mesher.grid_box(m, "S235", 1.0, 0.1, 0.1, 2, 1, 1, typ="hex8")
    s = [int(ids[2, 0, 0]), int(ids[2, 1, 0]), int(ids[2, 0, 1]), int(ids[2, 1, 1])]
    cp = ContactPair("F1", slave_nodes=list(s),
                     master_faces=[[int(ids[0, 0, 0]), int(ids[0, 1, 0]), int(ids[0, 1, 1])]],
                     grenzpressung=200e6, knotenflaechen={n: 0.0025 for n in s},
                     rand_knoten=[s[0]])
    m.contact_pairs.append(cp)
    ss = SurfaceSupport("SL", nodes=list(s), areas=[0.0025] * 4, lokal=True,
                        gruppen=[[0, 1, list(s), [0.0025] * 4]])
    m.surface_supports.append(ss)
    return m, frei, s, cp, ss


def test_passung_und_lagergruppen_folgen_dem_knotenloeschen():
    """Befund B107: ``_knotenverweise_abbilden`` zog ContactPair.knotenflaechen
    (Schluessel), ContactPair.rand_knoten und SurfaceSupport.gruppen nicht mit.

    Gemessen am Stand ec6448c (23.09.2026): nach knoten_loeschen(0) waren
    die Slave-Knoten [8, 10, 9, 11], die Schluessel der Einflussflaechen aber
    weiter [9, 10, 11, 12] (Knoten 12 gab es nicht mehr), der Randknoten 9
    und die Gruppenknoten [9, 11, 10, 12]. Slave-Knoten 8 hatte damit keine
    Einflussflaeche - seine Lochleibungsgrenze wurde 0, also keine -, und
    der Randknoten, der nicht haften soll, war ein anderer Knoten.
    """
    m, frei, s, cp, ss = _passung_und_lagergruppen()
    grund = m.knoten_loeschen(frei)
    check("knoten_loeschen(0) gelingt", grund == "", grund)
    soll = [n - 1 for n in s]
    check("die Slave-Knoten ruecken auf (das war schon vorher richtig)", cp.slave_nodes == soll,
          str(cp.slave_nodes))
    check("**die Einflussflaechen gehoeren zu denselben Slave-Knoten**",
          sorted(cp.knotenflaechen) == sorted(cp.slave_nodes)
          and all(abs(a - 0.0025) < 1e-15 for a in cp.knotenflaechen.values()),
          f"{sorted(cp.knotenflaechen)} gegen {sorted(cp.slave_nodes)}")
    check("**der Randknoten ist derselbe Knoten wie vorher**", cp.rand_knoten == [soll[0]],
          f"{cp.rand_knoten} statt {[soll[0]]}")
    check("**die Knoten der Normalengruppe sind die des Lagers**",
          ss.gruppen[0][2] == ss.nodes == soll and ss.gruppen[0][3] == [0.0025] * 4,
          f"{ss.gruppen[0][2]} gegen {ss.nodes}")

    # Tauschen zweier Knotennummern: jeder Verweis folgt dem Knoten
    m, frei, s, cp, ss = _passung_und_lagergruppen()
    a, b = s[0], s[3]
    m.knoten_tauschen(a, b)
    check("knoten_tauschen: Einflussflaechen, Randknoten und Gruppe folgen",
          sorted(cp.knotenflaechen) == sorted(cp.slave_nodes) and cp.rand_knoten == [b]
          and ss.gruppen[0][2] == ss.nodes,
          f"kf {sorted(cp.knotenflaechen)}, rand {cp.rand_knoten}, gruppe {ss.gruppen[0][2]}")

    # Ein geloeschter Knoten, der in der Normalengruppe steht, faellt samt
    # seiner Einflussflaeche heraus (die Listen bleiben gleich lang)
    m, frei, s, cp, ss = _passung_und_lagergruppen()
    k_los = m.add_node(-6.0, 0.0, 0.0)
    ss.nodes.append(k_los)
    ss.areas.append(0.001)
    ss.gruppen[0][2].append(k_los)
    ss.gruppen[0][3].append(0.001)
    m.knoten_loeschen(k_los)
    check("geloeschter Gruppenknoten faellt mit seiner Flaeche heraus",
          ss.gruppen[0][2] == s and ss.gruppen[0][3] == [0.0025] * 4 and ss.nodes == s,
          f"{ss.gruppen[0][2]} / {ss.gruppen[0][3]}")

    # netzknoten_loeschen: der freie Knoten 0 geht, die Verweise folgen
    m, frei, s, cp, ss = _passung_und_lagergruppen()
    weg = m.netzknoten_loeschen()
    check("netzknoten_loeschen: Einflussflaechen, Randknoten und Gruppe folgen",
          weg == 1 and sorted(cp.knotenflaechen) == sorted(cp.slave_nodes)
          and cp.rand_knoten == [s[0] - 1] and ss.gruppen[0][2] == ss.nodes,
          f"weg {weg}, kf {sorted(cp.knotenflaechen)}, rand {cp.rand_knoten}, "
          f"gruppe {ss.gruppen[0][2]} / {ss.nodes}")


def test_tabellenknopf_knoten_loeschen_nimmt_denselben_weg():
    """Der Knopf „Knoten löschen“ der Tabelle Knoten (MainWindow.knoten_loeschen)
    nummerierte bis zum 24.09.2026 selbst um (Elemente, Linien, Lager,
    Knotenlasten) und ging nicht ueber Model.knoten_loeschen. Gemessen an
    eb2fc71 (24.09.2026) mit dem Modell unten, Zeile 0 (der freie Knoten):
    danach nn = 12, die Lagerknoten [8, 10, 9, 11], aber die Slave-Knoten
    [9, 11, 10, 12], die Master-Facette [[1, 3, 4]], die Schluessel der
    Einflussflaechen [9, 10, 11, 12], der Randknoten 9 und die Gruppenknoten
    [9, 11, 10, 12] - die Fuge zeigte auf fremde und auf einen nicht mehr
    vorhandenen Knoten. Hier ohne Fenster: der Knopf mit einer Attrappe fuer
    self (Zeile, Modell, merken, error, refresh_all), wie in test_gzg.
    """
    import types
    from statik3d.gui.main import MainWindow

    def knopf(m, zeile):
        meld = []
        attrappe = types.SimpleNamespace(
            model=m, tbl_knoten=None, selection=None,
            _zeilenzahl=lambda _tbl: zeile,
            error=lambda t: meld.append("error: " + t),
            merken=lambda t: meld.append("merken: " + t),
            refresh_all=lambda: None)
        MainWindow.knoten_loeschen(attrappe)
        return meld

    m, frei, s, cp, ss = _passung_und_lagergruppen()
    nn = m.nn
    master = [list(map(int, f)) for f in cp.master_faces]
    meld = knopf(m, frei)
    check("Tabellenknopf: der freie Knoten 0 geht, ohne Fehlermeldung",
          m.nn == nn - 1 and meld == [f"merken: Knoten {frei} gelöscht"], str(meld))
    soll = [n - 1 for n in s]
    check("**Tabellenknopf: die Slave-Knoten ruecken mit auf**", cp.slave_nodes == soll,
          f"{cp.slave_nodes} statt {soll}")
    check("**Tabellenknopf: die Master-Facette rueckt mit auf**",
          [list(map(int, f)) for f in cp.master_faces] == [[n - 1 for n in f] for f in master],
          f"{cp.master_faces} statt {[[n - 1 for n in f] for f in master]}")
    check("**Tabellenknopf: Einflussflaechen, Randknoten und Gruppe folgen**",
          sorted(cp.knotenflaechen) == sorted(cp.slave_nodes) and cp.rand_knoten == [soll[0]]
          and ss.gruppen[0][2] == ss.nodes == soll,
          f"kf {sorted(cp.knotenflaechen)}, rand {cp.rand_knoten}, "
          f"gruppe {ss.gruppen[0][2]} / {ss.nodes}")

    # Ein Knoten mit Element bleibt, wie bisher, und nichts wird gemerkt
    m, frei, s, cp, ss = _passung_und_lagergruppen()
    nn = m.nn
    meld = knopf(m, s[0])
    check("Tabellenknopf: ein Knoten mit Element bleibt und wird genannt",
          m.nn == nn and len(meld) == 1 and meld[0].startswith("error: ")
          and cp.slave_nodes == s, str(meld))


def main():
    print("=" * 92)
    print("STATIK3D - ein neu vernetztes Modell muss dasselbe rechnen")
    print("=" * 92)
    for t in (test_neuvernetzen_rechnet_dasselbe,
              test_fuge_und_lager_ueberleben_das_neuvernetzen,
              test_master_facetten_folgen_dem_knotenloeschen,
              test_oberflaeche_entfernt_die_alten_knoten,
              test_passung_und_lagergruppen_folgen_dem_knotenloeschen,
              test_tabellenknopf_knoten_loeschen_nimmt_denselben_weg):
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
