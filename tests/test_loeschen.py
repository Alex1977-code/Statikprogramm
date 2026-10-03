"""
Loeschen im Modell (Plan-Paket 14a, Nachzug 03.10.2026, Gegenpruefung der Taste Entf).

* Stab und Linie loeschen nehmen die Elementlasten und Knotenlasten mit, die
  ``Model.lasten_verteilen`` aus ihren Linienlasten gemacht hat (Kennzeichen
  ``_geo``). Bis dahin blieben sie wirksam und waren in der Lasttabelle
  unsichtbar - die Rechnung trug eine Last, die es nicht mehr gab.
* viele Knoten in einem Zug (``knoten_loeschen_viele``): dasselbe Ergebnis wie
  ``knoten_loeschen`` je Knoten von hinten nach vorn, aber ein Umnummerieren
  statt eines je Knoten. Strg+A und Entf an einem vernetzten Modell war
  quadratisch (``knoten_benutzt_von`` geht je Knoten durch alle Elemente).
* Knotenverweise (Gegenpruefung zu 14a, 03.10.2026): je Verweisart ist der
  Knoten entweder benutzt (Loeschen abgewiesen, mit Grund) oder der Verweis geht
  mit ihm - keiner zeigt danach auf den Nachbarknoten. Stellungen verlieren die
  Namen und Nummern geloeschter Lager und Staebe und sagen es im Protokoll.

Aufruf:  python -m tests.test_loeschen
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from statik3d import mesher, solver
from statik3d.model import Line, Material, Model, Section

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _balken(zwei_staebe: bool = False):
    """Ein Einfeldtraeger aus vier Elementen als Stab „A“ (mit dem zweiten Stab
    „B“ daneben), gelagert."""
    m = Model("Balken")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    n0 = len(m.elements)
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6.0, 0, 0), 4)
    m.add_member("A", list(range(n0, len(m.elements))))
    m.fix(0, [0, 1, 2, 3])
    m.fix(m.nn - 1, [1, 2])
    if zwei_staebe:
        n1 = len(m.elements)
        mesher.line_of_beams(m, "S235", "IPE 300", (0, 5.0, 0), (6.0, 5.0, 0), 4)
        m.add_member("B", list(range(n1, len(m.elements))))
        m.fix(m.nn - 5, [0, 1, 2, 3])
        m.fix(m.nn - 1, [1, 2])
    return m


def _geo(lc, liste):
    return [l for l in getattr(lc, liste) if getattr(l, "_geo", False)]


def test_stab_loeschen_nimmt_die_abgeleiteten_lasten_mit():
    m = _balken(zwei_staebe=True)
    q = 10e3
    m.add_linienlast("A", [0, 0, -q], art="stab")
    m.add_linienlast("B", [0, 0, -q], art="stab")
    m.lasten_verteilen()
    lc = m.case()
    n_alle = len(_geo(lc, "beam_loads"))
    check("Vorbereitung: beide Stäbe tragen abgeleitete Elementlasten (8 Stück)", n_alle == 8, str(n_alle))
    elem_a = set(m.members["A"].elements)
    check("… Stab A vier davon", sum(1 for b in _geo(lc, "beam_loads") if b.elem in elem_a) == 4)
    ohne_last = _balken(zwei_staebe=True)
    ohne_last.add_linienlast("B", [0, 0, -q], art="stab")
    ohne_last.lasten_verteilen()
    ohne_last.stab_loeschen("A")                    # Soll: A ist nie belastet gewesen
    soll = [(b.elem, round(b.a, 9), b.b, tuple(b.q)) for b in _geo(ohne_last.case(), "beam_loads")]
    grund = m.stab_loeschen("A")
    ist = [(b.elem, round(b.a, 9), b.b, tuple(b.q)) for b in _geo(lc, "beam_loads")]
    check("Stab A löschen: die abgeleiteten Elementlasten von A sind weg, die von B bleiben",
          grund == "" and len(ist) == 4 and not any(e in elem_a for e, *_ in ist), f"{len(ist)} Elementlasten")
    check("… und es sind genau die von B (Wert und Lage)", sorted(ist) == sorted(soll), str(ist[:2]))
    check("… die Linienlast von A ist weg, die von B bleibt",
          [ll.ziel for ll in lc.linienlasten] == ["B"], str([ll.ziel for ll in lc.linienlasten]))
    # Rechnung: ein Stab ohne seine Last verformt sich nicht
    m2 = _balken()
    m2.add_linienlast("A", [0, 0, -q], art="stab")
    m2.lasten_verteilen()
    w_vorher = float(np.abs(solver.solve_static(m2).u).max())
    m2.stab_loeschen("A")
    w_nachher = float(np.abs(solver.solve_static(m2).u).max())
    check("Rechnung: mit der Last verformt sich der Träger, nach dem Löschen des Stabs nicht mehr",
          w_vorher > 1e-4 and w_nachher < 1e-12, f"{w_vorher:.3e} -> {w_nachher:.3e} m")
    check("… die Lasttabelle zeigt nichts (n_loads)", m2.case().n_loads == 0, str(m2.case().n_loads))


def test_stab_ohne_linienlast_loeschen_fasst_die_lasten_nicht_an():
    m = _balken(zwei_staebe=True)
    m.add_linienlast("B", [0, 0, -5e3], art="stab")
    m.lasten_verteilen()
    vorher = [id(b) for b in m.case().beam_loads]
    m.stab_loeschen("A")                            # A trägt nichts: nichts neu verteilen
    check("Stab ohne Linienlast: die Elementlasten bleiben dieselben Objekte (kein Neuverteilen)",
          [id(b) for b in m.case().beam_loads] == vorher)


def test_linie_loeschen_nimmt_die_knotenlasten_mit():
    from tests.test_lasten import platte
    m = platte()
    ecke0 = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, ymin=-1e-6, ymax=1e-6)[0])
    ecke1 = int(mesher.select_nodes(m, xmin=3 - 1e-6, ymin=-1e-6, ymax=1e-6)[0])
    m.lines["L1"] = Line("L1", [ecke0, ecke1])
    m.add_linienlast("L1", [0, 0, -4e3], art="linie", von=0.5, bis=2.5)
    n = m.lasten_verteilen()
    lc = m.case()
    check("Vorbereitung: die Linienlast hat Knotenlasten erzeugt", n == 9 and len(_geo(lc, "nodal_loads")) == 9, str(n))
    grund = m.linie_loeschen("L1")
    check("Linie löschen: auch die Knotenlasten daraus sind weg",
          grund == "" and not _geo(lc, "nodal_loads") and not lc.linienlasten,
          f"{len(_geo(lc, 'nodal_loads'))} Knotenlasten, {len(lc.linienlasten)} Linienlasten")
    r = solver.solve_static(m)
    check("Rechnung ohne die Last: Auflagerkräfte null", float(np.abs(r.reactions).max()) < 1e-6,
          f"{float(np.abs(r.reactions).max()):.3e} N")


def test_schleife_mit_einer_verteilung():
    """Für viele Stäbe auf einmal: ``verteilen=False`` und danach ein einziges
    ``lasten_verteilen`` - dasselbe Ergebnis wie je Stab verteilen."""
    a = _balken(zwei_staebe=True)
    b = _balken(zwei_staebe=True)
    for m in (a, b):
        m.add_linienlast("A", [0, 0, -1e3], art="stab")
        m.add_linienlast("B", [0, 0, -2e3], art="stab")
        m.lasten_verteilen()
    a.stab_loeschen("A")
    a.stab_loeschen("B")
    b.stab_loeschen("A", verteilen=False)
    b.stab_loeschen("B", verteilen=False)
    b.lasten_verteilen()
    check("Schleife mit verteilen=False und einem lasten_verteilen: dasselbe wie je Stab",
          not a.case().beam_loads and not b.case().beam_loads,
          f"{len(a.case().beam_loads)} / {len(b.case().beam_loads)}")


# ---------------------------------------------------------------------------
def _modell_mit_anhang():
    """Das Balkenmodell mit freien Knoten, an denen allerlei haengt, und mit
    benutzten Knoten (Element, Linie)."""
    m = _balken()
    m.add_linienlast("A", [0, 0, -1e3], art="stab")
    frei = []
    for i in range(12):
        k = m.add_node(10.0 + i, 1.0, 0.0)
        frei.append(k)
        if i % 3 == 0:
            m.fix(k, [0, 1, 2])
        if i % 2 == 0:
            m.load_node(k, Fz=-1e3 * (i + 1))
        if i % 4 == 1:
            m.add_zwangsverformung(k, [2], [1e-3])
        if i % 5 == 0:
            m.add_punktmasse(k, 100.0 + i)
        if i % 6 == 0:
            m.add_daempfer(k, -1, c=[1e3])
    m.layer_anlegen("Freie", knoten=frei[:6])
    k0, k1 = m.add_node(30.0, 0.0, 0.0), m.add_node(31.0, 0.0, 0.0)
    m.lines["LX"] = Line("LX", [k0, k1])
    m.lasten_verteilen()
    return m, frei, [k0, k1]


def _abbild(m) -> str:
    return json.dumps(m.to_dict(), sort_keys=True, default=str)


def test_viele_knoten_wie_einzeln():
    m, frei, benutzt = _modell_mit_anhang()
    wahl = frei[1:] + benutzt + [0, 2, 99999]       # frei, mit Linie, mit Element, nicht da
    a, b = m.copy(), m.copy()
    gruende_a = {}
    for i in sorted({int(x) for x in wahl}, reverse=True):
        g = a.knoten_loeschen(i)
        if g:
            gruende_a[i] = g
    gruende_b = b.knoten_loeschen_viele(wahl)
    check("viele Knoten in einem Zug: dieselben Gründe wie je Knoten einzeln",
          gruende_a == gruende_b and len(gruende_b) == 5, str(sorted(gruende_b)))
    check("… Knoten, Elemente, Lager, Lasten, Zwang, Masse, Dämpfer, Layer: Zustand identisch",
          _abbild(a) == _abbild(b), f"{a.nn} / {b.nn} Knoten")
    check("… elf freie Knoten sind verschwunden, die benutzten geblieben",
          b.nn == m.nn - len(frei) + 1 and "LX" in b.lines, f"{m.nn} -> {b.nn}")
    z = m.copy()
    check("Gegenprobe: ohne Auswahl (nur gesperrte) ändert sich nichts",
          z.knoten_loeschen_viele(benutzt + [0]) != {} and _abbild(z) == _abbild(m))
    check("knoten_gesperrt nennt dieselben Gründe, ohne etwas zu ändern",
          m.knoten_gesperrt(wahl) == gruende_a and _abbild(m) == _abbild(_modell_mit_anhang()[0]))


def test_viele_knoten_schnell():
    """Strg+A, Entf an einem vernetzten Modell: je Knoten ein Durchgang durch alle
    Elemente war quadratisch."""
    m = Model("Kette")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    n_el = 4000
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (float(n_el), 0, 0), n_el)
    alle = list(range(m.nn))
    t0 = time.time()
    gesperrt = m.knoten_loeschen_viele(alle)
    dt = time.time() - t0
    check("Kette mit 4001 Knoten und 4000 Elementen, alle gewählt: alle gesperrt, unter 2 s",
          len(gesperrt) == len(alle) and m.nn == len(alle) and dt < 2.0, f"{dt:.2f} s")
    # freie Knoten mit Lager und Last: die Hälfte des Modells
    for i in range(3000):
        k = m.add_node(10000.0 + i, 0.0, 0.0)
        m.fix(k, [0, 1, 2])
        m.load_node(k, Fz=-1e3)
    frei = list(range(len(alle), m.nn))
    t0 = time.time()
    gesperrt = m.knoten_loeschen_viele(frei)
    dt = time.time() - t0
    check("3000 freie Knoten mit Lager und Last in einem Zug: alle weg, unter 2 s",
          not gesperrt and m.nn == len(alle) and not any(sp.node >= m.nn for sp in m.supports)
          and dt < 2.0, f"{dt:.2f} s, {m.nn} Knoten, {len(m.supports)} Lager")


# ---------------------------------------------------------------------------
# Knotenverweise (lesende Gegenpruefung zu 14a, 03.10.2026). knoten_loeschen hielt
# einen Knoten nur fuer benutzt, wenn ein Element oder eine Linie an ihm hing, und
# _knotenverweise_abbilden bildete nur die Nummern **hinter** dem geloeschten Knoten
# ab: ein Verweis auf ihn selbst blieb stehen und zeigte danach auf seinen frueheren
# Nachbarn. Stellung.antrieb wurde gar nicht abgebildet. Je Verweisart gilt jetzt eins
# von beiden: der Knoten ist benutzt (Loeschen abgewiesen, mit Grund), oder der Verweis
# geht mit dem Knoten. Geprueft wird ueber den **Ort**: ein Verweis zeigt vor und nach
# dem Loeschen auf denselben Punkt im Raum, oder er ist weg.

def _vier_freie():
    """Der Balken (Knoten 0 bis 4, Lager an 0 und 4) mit vier freien Knoten dahinter:
    j wird als Erstes geloescht (er liegt vor allen anderen), k ist der Knoten mit dem
    Verweis, n sein Nachbar (auf ihn sprang ein stehengebliebener Verweis), p ein
    Partner fuer Verweise mit zwei Knoten."""
    m = _balken()
    j, k, n, p = (m.add_node(20.0 + i, 2.0, 0.0) for i in range(4))
    return m, j, k, n, p


def _orte(m, idx) -> list:
    return [tuple(float(x) for x in m.nodes[int(i)]) if 0 <= int(i) < m.nn else None for i in idx]


def _flaeche_ecke(m, k, p):
    from statik3d.model import Flaeche
    m.flaechen["F1"] = Flaeche("F1", [], ecken=[0, 1, p, k])
    return lambda m: list(m.flaechen["F1"].ecken)


def _flaeche_integriert(m, k, p):
    from statik3d.model import Flaeche
    m.flaechen["F2"] = Flaeche("F2", [], integrierte_knoten=[k])
    return lambda m: list(m.flaechen["F2"].integrierte_knoten)


def _kopplung(m, k, p):
    from statik3d.model import Kopplung
    m.kopplungen.append(Kopplung(k, p, [[1.0, 0.0, 0.0]], [1e9]))
    return lambda m: [m.kopplungen[0].node_a, m.kopplungen[0].node_b]


def _spaltelement(m, k, p):
    m.add_gap_element(k, p)
    return lambda m: [m.gap_elements[0].node_a, m.gap_elements[0].node_b]


def _kontakt_slave(m, k, p):
    m.add_contact_pair("KP1", [k], master_faces=[[0, 1, 2]])
    return lambda m: list(m.contact_pairs[0].slave_nodes)


def _kontakt_master(m, k, p):
    m.add_contact_pair("KP2", [0], master_faces=[[k, p, 1]])
    return lambda m: list(m.contact_pairs[0].master_faces[0])


def _lasteinleitung(m, k, p):
    m.add_lasteinleitung("LE1", k)
    return lambda m: [m.lasteinleitungen["LE1"].knoten]


def _verformungsgrenze(m, k, p):
    m.add_verformungsgrenze("VG1", art="punktpaar", knoten=[k, p], grenzart="absolut", wert=0.01)
    return lambda m: list(m.verformungsgrenzen["VG1"].knoten)


def _antrieb(m, k, p):
    from statik3d.bridges.positions import Stellung
    m.stellungen.append(Stellung("S1", 30.0, antrieb=(k, (0.0, 0.0, 5e4)), faelle=["LF1"]))
    return lambda m: [m.stellungen[0].antrieb[0]]


#: Verweisarten, die den Knoten benutzt machen: (Art, Aufbau, Wort im Grund)
BENUTZT = (("Eckknoten einer Fläche", _flaeche_ecke, "Fläche F1"),
           ("integrierter Knoten einer Fläche", _flaeche_integriert, "Fläche F2"),
           ("Kopplung", _kopplung, "Kopplung"),
           ("Spaltelement", _spaltelement, "Spaltelement"),
           ("Slave-Knoten eines Kontaktpaars", _kontakt_slave, "Kontaktpaar KP1"),
           ("Master-Facette eines Kontaktpaars", _kontakt_master, "Kontaktpaar KP2"),
           ("Lasteinleitung", _lasteinleitung, "Lasteinleitung LE1"),
           ("Verformungsgrenze", _verformungsgrenze, "Verformungsgrenze VG1"),
           ("Antrieb einer Stellung", _antrieb, "Stellung S1"))


def test_benutzte_knoten_werden_abgewiesen():
    for art, aufbau, wort in BENUTZT:
        m, j, k, n, p = _vier_freie()
        lesen = aufbau(m, k, p)
        soll, nn = _orte(m, lesen(m)), m.nn
        grund = m.knoten_loeschen(k)
        check(f"{art}: Löschen abgewiesen, der Grund nennt „{wort}“",
              wort in grund and m.nn == nn and _orte(m, lesen(m)) == soll, f"„{grund}“")
        g_viele = m.copy().knoten_loeschen_viele([k, j])
        check("… knoten_gesperrt und knoten_loeschen_viele sagen dasselbe",
              m.knoten_gesperrt([k]) == {k: grund} and g_viele == {k: grund}, str(g_viele))
        m.knoten_loeschen(j)                        # ein freier Knoten davor: alles rueckt auf
        check("… nach dem Löschen eines Knotens davor zeigt der Verweis auf denselben Ort",
              m.nn == nn - 1 and _orte(m, lesen(m)) == soll, f"{soll} -> {_orte(m, lesen(m))}")
        weg = m.netzknoten_loeschen()               # n ist frei und wird von nichts genannt
        check("… „Knoten des alten Netzes löschen“ lässt ihn ebenfalls stehen",
              weg >= 1 and _orte(m, lesen(m)) == soll, f"{weg} weg, {_orte(m, lesen(m))}")


def test_knoten_tauschen_nimmt_antrieb_und_kantenmitte_mit():
    from statik3d.model import tetp_kantenmitten_gelesen
    m, j, k, n, p = _vier_freie()
    lesen = _antrieb(m, k, p)
    soll = _orte(m, lesen(m))
    m.knoten_tauschen(k, p)
    check("Antrieb einer Stellung: Knoten tauschen nimmt ihn mit", _orte(m, lesen(m)) == soll,
          f"{soll} -> {_orte(m, lesen(m))}")
    m, j, k, n, p = _vier_freie()
    t = [m.add_node(*q) for q in ((30, 0, 0), (31, 0, 0), (30, 1, 0), (30, 0, 1))]
    m.add_element("tetp2", t, "S235")
    m.tetp_kantenmitten = {(t[0], t[1]): np.array([30.5, 0.0, 0.1])}
    m.knoten_tauschen(t[1], j)                       # die Kante laeuft danach von j nach t0
    gelesen = tetp_kantenmitten_gelesen(m.tetp_kantenmitten, m.elements)
    (a, b), = gelesen or {(-1, -1): None}
    check("Kantenmitte: Knoten tauschen nimmt sie mit (dieselbe Kante, Schlüssel aufsteigend)",
          len(gelesen) == 1 and a < b and sorted(_orte(m, [a, b])) == [(30.0, 0.0, 0.0), (31.0, 0.0, 0.0)],
          str(m.tetp_kantenmitten))


def test_verweise_gehen_mit_dem_knoten():
    from statik3d.model import Subsystem, tetp_kantenmitten_gelesen
    # Subsystem: eine Gruppe wie ein Layer - der Knoten geht aus ihr heraus
    m, j, k, n, p = _vier_freie()
    m.subsysteme["T"] = Subsystem("T", knoten=[k, p])
    soll = _orte(m, [p])
    m.knoten_loeschen(k)
    check("Subsystem: der gelöschte Knoten geht heraus, der übrige bleibt am Ort",
          _orte(m, m.subsysteme["T"].knoten) == soll, f"{soll} -> {_orte(m, m.subsysteme['T'].knoten)}")
    # Getrennte Fugenknoten: das Paar gehoert zum geloeschten Knoten und geht mit
    m, j, k, n, p = _vier_freie()
    m.getrennte_knoten["Fuge"] = [[k, p], [1, 2]]
    m.knoten_loeschen(k)
    check("Getrennte Fugenknoten: das Paar mit dem Knoten geht, das andere bleibt",
          [_orte(m, q) for q in m.getrennte_knoten["Fuge"]] == [_orte(_balken(), [1, 2])],
          str(m.getrennte_knoten["Fuge"]))
    # Flaechenlager ueber Knoten: die Einflussflaeche geht mit ihrem Knoten
    m, j, k, n, p = _vier_freie()
    fs = m.add_surface_support(nodes=[k, p], areas=[1.0, 2.0])
    soll = _orte(m, [p])
    m.knoten_loeschen(k)
    check("Flächenlager über Knoten: Knoten und Einflussfläche gehen gemeinsam",
          _orte(m, fs.nodes) == soll and list(fs.areas) == [2.0], f"{fs.nodes}, {fs.areas}")
    m, j, k, n, p = _vier_freie()
    fs = m.add_surface_support(nodes=[k, p], areas=[1.0, 2.0])
    m.knoten_loeschen_viele([k])
    check("… ebenso beim Löschen vieler Knoten", list(fs.areas) == [2.0], str(fs.areas))
    # Starrer Koerper RBE3: die Gewichte stehen parallel zu den Slaves (Gegenpruefung:
    # sie blieben ganz stehen, und assemble rechnete dann mit gleichen Gewichten)
    m, j, k, n, p = _vier_freie()
    sk = m.add_starrkoerper(0, [k, n, p], art="RBE3", gewichte=[1.0, 5.0, 10.0])
    m.knoten_loeschen(k)
    check("Starrer Körper RBE3: der Slave geht samt seinem Gewicht",
          _orte(m, sk.slaves) == [(22.0, 2.0, 0.0), (23.0, 2.0, 0.0)] and list(sk.gewichte) == [5.0, 10.0],
          f"{sk.slaves}, {sk.gewichte}")
    # Kantenmitten eines Tetraeders mit Ordnung p: Schluessel sind Knotenpaare
    m, j, k, n, p = _vier_freie()
    t = [m.add_node(*q) for q in ((30, 0, 0), (31, 0, 0), (30, 1, 0), (30, 0, 1))]
    m.add_element("tetp2", t, "S235")
    mitte = np.array([30.5, 0.0, 0.1])
    m.tetp_kantenmitten = {(t[0], t[1]): mitte}
    m.knoten_loeschen(k)
    gelesen = tetp_kantenmitten_gelesen(m.tetp_kantenmitten, m.elements)
    (a, b), q = next(iter(gelesen.items())) if gelesen else ((-1, -1), None)
    check("Kantenmitte eines tetp-Elements: sie bleibt an ihrer Kante",
          len(gelesen) == 1 and _orte(m, [a, b]) == [(30.0, 0.0, 0.0), (31.0, 0.0, 0.0)]
          and np.allclose(q, mitte), str(m.tetp_kantenmitten))


def _lager_aus_orte(m, st) -> list:
    """Die Orte der Lager, die die Stellung abschaltet (Stellung._lager an einer Kopie)."""
    mc = m.copy()
    vorher = list(mc.supports)
    st._lager(mc)
    return sorted(_orte(mc, [s.node for s in vorher if all(s is not x for x in mc.supports)]))


def _stellungen_mit_lagern():
    """Der Balken mit zwei freien Knoten k, p, je mit einem Knotenlager: das an k heisst
    „Endlager“, das an p hat keinen Namen (Nummer 3; 0 und 1 sind die Balkenlager, 2
    ist das Endlager). Das Lager „Mitte“ am Balkenknoten 2 bleibt immer."""
    from statik3d.bridges.positions import Stellung
    m = _balken()
    k, p = m.add_node(20.0, 2.0, 0.0), m.add_node(21.0, 2.0, 0.0)
    m.fix(k, [0, 1, 2])
    m.supports[-1].name = "Endlager"
    m.fix(p, [0, 1, 2])
    m.fix(2, [1])
    m.supports[-1].name = "Mitte"
    m.stellungen += [Stellung("S1", lager_aus=["Endlager", "Mitte"], faelle=["LF1"]),
                     Stellung("S2", lager_aktiv=["Endlager"], faelle=["LF1"]),
                     Stellung("S3", lager_aktiv=["Endlager", "Mitte"], faelle=["LF1"]),
                     Stellung("S4", lager_aus=["3"], faelle=["LF1"]),
                     Stellung("S5", lager_aus=["2"], faelle=["LF1"])]
    return m, k, p


def test_stellung_lagernamen_nach_knoten_loeschen():
    m, k, p = _stellungen_mit_lagern()
    st = {s.name: s for s in m.stellungen}
    orte_s4 = _lager_aus_orte(m, st["S4"])
    m.knoten_loeschen(k)
    check("Stellung: der Name des gelöschten Lagers geht aus „Deaktivierte Knotenlager“",
          st["S1"].lager_aus == ["Mitte"], str(st["S1"].lager_aus))
    check("… und aus „Lager aktiv“, die übrigen Namen bleiben", st["S3"].lager_aktiv == ["Mitte"],
          str(st["S3"].lager_aktiv))
    check("… war es der einzige Name, ist die Liste leer", st["S2"].lager_aktiv == [],
          str(st["S2"].lager_aktiv))
    check("Lagernummer: das Lager hinter dem gelöschten behält seine Wirkung (3 wird 2)",
          st["S4"].lager_aus == ["2"] and _lager_aus_orte(m, st["S4"]) == orte_s4,
          f"{st['S4'].lager_aus}, {orte_s4} -> {_lager_aus_orte(m, st['S4'])}")
    check("… die Nummer des gelöschten Lagers springt nicht auf das nächste",
          st["S5"].lager_aus == [] and _lager_aus_orte(m, st["S5"]) == [],
          f"{st['S5'].lager_aus}, {_lager_aus_orte(m, st['S5'])}")


def test_stellung_lagernamen_im_protokoll():
    m, k, p = _stellungen_mit_lagern()
    zeilen = []
    m.knoten_loeschen(k, protokoll=zeilen)
    text = "\n".join(zeilen)
    check("Protokoll: je Stellung eine Zeile mit dem gelöschten Lager",
          all(f"Stellung „{s}“" in text for s in ("S1", "S2", "S3", "S5")) and "Endlager" in text,
          text.replace("\n", " | ")[:300])
    check("… die umnummerierte Stellung S4 wird ebenfalls genannt", "Stellung „S4“" in text, text[:300])
    s2 = next((z for z in zeilen if "„S2“" in z), "")
    check("… S2 sagt, dass jetzt alle Lager greifen", "alle Lager" in s2, s2)
    m, k, p = _stellungen_mit_lagern()
    zeilen = []
    m.knoten_loeschen_viele([k], protokoll=zeilen)
    check("… ebenso beim Löschen vieler Knoten", sum("Stellung „" in z for z in zeilen) == 5,
          " | ".join(zeilen)[:300])


def test_stellung_name_und_nummer_zugleich():
    """Stellung._gemeint trifft ein Lager beim Namen **und** bei der Nummer. Heisst
    ein Lager wie eine Nummer, laesst sich der Eintrag nach dem Loeschen nicht
    eindeutig nachziehen - das darf nicht still geschehen (Gegenpruefung 03.10.2026:
    der Eintrag blieb stehen und schaltete still ein anderes Lager ab)."""
    from statik3d.bridges.positions import Stellung
    m = _balken()                                   # Lager 0, 1 am Balken
    k, p, q = (m.add_node(20.0 + i, 2.0, 0.0) for i in range(3))
    for n in (k, p, q):
        m.fix(n, [0, 1, 2])                         # Lager 2, 3, 4
    m.supports[3].name = "3"
    st = Stellung("S1", lager_aus=["3"], faelle=["LF1"])
    m.stellungen.append(st)
    zeilen = []
    m.knoten_loeschen(k, protokoll=zeilen)
    check("Lager heißt „3“ und steht an Platz 3: nach dem Löschen davor sagt das Protokoll, "
          "dass der Eintrag nicht eindeutig ist",
          any("„S1“" in z and "nicht eindeutig" in z for z in zeilen), " | ".join(zeilen))
    m = _balken()
    k, p = m.add_node(20.0, 2.0, 0.0), m.add_node(21.0, 2.0, 0.0)
    m.fix(k, [0, 1, 2])
    m.fix(p, [0, 1, 2])                             # Lager 2 an k, 3 an p
    m.add_line_support([1, 2], name="3")
    st = Stellung("S2", lager_aus=["3"], faelle=["LF1"])
    m.stellungen.append(st)
    zeilen = []
    m.knoten_loeschen(k, protokoll=zeilen)
    check("Ein Linienlager heißt „3“, die Nummer meint Knotenlager 3: ebenso",
          any("„S2“" in z and "nicht eindeutig" in z for z in zeilen), " | ".join(zeilen))
    m = _balken()
    k = m.add_node(20.0, 2.0, 0.0)
    m.fix(k, [0, 1, 2])
    m.stellungen.append(Stellung("S3", lager_aus=["²", "2"], faelle=["LF1"]))
    try:
        m.knoten_loeschen(k)
        ok, text = m.stellungen[0].lager_aus == ["²"], str(m.stellungen[0].lager_aus)
    except ValueError as ex:
        ok, text = False, f"ValueError: {ex}"
    check("Ein Eintrag „²“ ist keine Nummer und bricht nichts ab", ok, text)


def test_stellung_staebe_nach_stab_loeschen():
    from statik3d.bridges.positions import Stellung
    m = _balken(zwei_staebe=True)
    st = Stellung("S1", staebe_aus=["A", "B"], faelle=["LF1"])
    m.stellungen.append(st)
    m.stab_loeschen("A")
    check("Stab löschen: sein Name geht aus „Deaktivierte Stäbe“", st.staebe_aus == ["B"], str(st.staebe_aus))
    m = _balken(zwei_staebe=True)
    st = Stellung("S1", staebe_aus=["A", "B"], faelle=["LF1"])
    m.stellungen.append(st)
    zeilen = []
    m.stab_loeschen("B", protokoll=zeilen)
    check("… und das Protokoll nennt es", any("„S1“" in z and "B" in z for z in zeilen), str(zeilen))


def test_stellung_linien_und_flaechenlager():
    """Linien- und Flaechenlager loescht nur die Oberflaeche (Entf, Baum); sie nimmt den
    Stand vorher (stellungsbezug) und zieht danach nach (stellungen_nachziehen)."""
    from statik3d.bridges.positions import Stellung
    m = _balken()
    for a, b in ((0, 1), (2, 3), (3, 4)):
        m.add_line_support([a, b]).name = ""
    m.add_surface_support(nodes=[0, 1], areas=[1.0, 1.0], name="Boden")
    st = Stellung("S1", linienlager_aus=["0", "2"], flaechenlager_aus=["Boden"], faelle=["LF1"])
    m.stellungen.append(st)
    vorher = m.stellungsbezug()
    del m.line_supports[0]
    del m.surface_supports[0]
    zeilen = m.stellungen_nachziehen(vorher)
    check("Linienlager: die gelöschte Nummer geht, die dahinter rückt auf (2 wird 1)",
          st.linienlager_aus == ["1"], str(st.linienlager_aus))
    check("Flächenlager: der Name des gelöschten geht", st.flaechenlager_aus == [], str(st.flaechenlager_aus))
    check("… das Protokoll nennt alle drei", len(zeilen) == 3 and all("„S1“" in z for z in zeilen),
          str(zeilen))
    check("Ohne Änderung bleibt alles, wie es ist, und nichts steht im Protokoll",
          m.stellungen_nachziehen(m.stellungsbezug()) == [] and st.linienlager_aus == ["1"])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_stab_loeschen_nimmt_die_abgeleiteten_lasten_mit,
              test_stab_ohne_linienlast_loeschen_fasst_die_lasten_nicht_an,
              test_linie_loeschen_nimmt_die_knotenlasten_mit, test_schleife_mit_einer_verteilung,
              test_viele_knoten_wie_einzeln, test_viele_knoten_schnell,
              test_benutzte_knoten_werden_abgewiesen, test_knoten_tauschen_nimmt_antrieb_und_kantenmitte_mit,
              test_verweise_gehen_mit_dem_knoten, test_stellung_lagernamen_nach_knoten_loeschen,
              test_stellung_lagernamen_im_protokoll, test_stellung_name_und_nummer_zugleich,
              test_stellung_staebe_nach_stab_loeschen,
              test_stellung_linien_und_flaechenlager):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
