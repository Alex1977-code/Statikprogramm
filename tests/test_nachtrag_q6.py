"""
Nachtrag vom 06.10.2026, Paket Q6: Verweise im Modell.

* N05 - Das Verteilen von Linienlasten schrieb „n Elementlasten“ in ihren
  Kommentar und ueberschrieb damit den des Anwenders. Der Stand des Verteilens
  steht jetzt in einem eigenen Feld (``Linienlast.verteilt``); Tabelle und
  Bericht zeigen ihn neben dem Kommentar; Dateien von vorher werden beim Laden
  umgestellt, ohne dass die Erkennung alter Windlasten (wind._vom_wind) ihren
  Anker verliert.
* N11 - ``mesher.merge_nodes`` zog nur Elemente, Lager, Knotenlasten und
  Kontakt nach, nicht Linien, Kopplungen, Starrkoerper und alles uebrige, das
  Knoten nennt. Jede Verweisart, die ``Model._knotenverweise_abbilden`` (Loeschen
  eines Knotens) kennt, soll nach dem Zusammenfuehren am selben Ort stehen.
* N18 - ``tetp.aus_tet10`` und ``rfem6_db.keep_structure`` nahmen Knotenlager
  aus der Liste, ohne die Stellungen nachzuziehen: ein Eintrag „Lager 4“ nannte
  danach ein anderes Lager.
* N22 - Browser: ``remove_fatigue_load`` (und ``add_fatigue_load``) verwarf die
  Nachweise, aber nicht den Anschlussnachweis (``analysis.joints``), in dem die
  Ermuedung steht.
* N23 - Der Modellbaum erkannte beim Loeschen eines Winds (und die Windmaske beim
  Umbenennen) dessen Stablasten am Kommentar „Wind <Name>:“, den das Verteilen
  ueberschrieben hatte; jetzt am Merkmal ``erzeuger`` (wind.stablasten_entfernen).

Jede Pruefung ausser den als „Kontrolle“ oder „Vorbereitung“ benannten und den sechs
Verweisarten, die der alte Zusammenfuehrweg schon kannte (Spaltelement, Kontaktlager,
Slave-Knoten und Master-Facette eines Kontaktpaars, Knotenlast, Knotenlager),
schlug auf 3f7b670 fehl.

Aufruf:  python -m tests.test_nachtrag_q6
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_q6_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import mesher  # noqa: E402
from statik3d.model import (FatigueLoad, Flaeche, Kopplung, Layer, Material, Member,  # noqa: E402
                            Model, Section, Subsystem, tetp_kantenmitten_gelesen)

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {detail}")
    return ok


def _rufen(f, *a, **k):
    """Etwas rufen, das es auf dem alten Stand nicht gibt - dann ist das Ergebnis
    die Ausnahme (die Pruefung schlaegt fehl, die Suite laeuft weiter)."""
    try:
        return f(*a, **k)
    except Exception as ex:          # noqa: BLE001
        return ex


# --------------------------------------------------------------------------
# Hilfsmodelle
# --------------------------------------------------------------------------
def _mast(name="Mast") -> Model:
    """Ein Mast aus sechs Stabelementen, unten eingespannt."""
    m = Model("Mast")
    m.add_material(Material("S"))
    m.add_section(Section.pipe("CHS", 0.2, 0.006))
    ids = [m.add_node(0, 0, i * 1.0) for i in range(7)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(6)]
    m.members[name] = Member(name, el)
    m.fix(ids[0], "all")
    return m


def _linienlasten(m, fall=None) -> list:
    return list(m.case(fall).linienlasten)


def _stab_elementlasten(m, fall=None) -> int:
    return sum(1 for b in m.case(fall).beam_loads if getattr(b, "_geo", False))


# --------------------------------------------------------------------------
# N05 - Kommentar beim Verteilen
# --------------------------------------------------------------------------
def test_n05_kommentar_bleibt():
    m = _mast()
    ll = m.add_linienlast("Mast", [0.0, 0.0, -5e3], art="stab")
    ll.kommentar = "Verkleidung, nach Statik Anlage 3"
    n = m.lasten_verteilen()
    check("N05 Modell: nach dem Verteilen steht der Kommentar des Anwenders noch da",
          ll.kommentar == "Verkleidung, nach Statik Anlage 3", repr(ll.kommentar))
    check("N05 Modell: der Stand des Verteilens steht im eigenen Feld „verteilt“ (6 Elementlasten)",
          n == 6 and getattr(ll, "verteilt", None) == "6 Elementlasten", repr(getattr(ll, "verteilt", None)))
    check("N05 Modell: ein zweites Verteilen ändert den Kommentar nicht und verdoppelt nichts",
          (m.lasten_verteilen() == 6 and ll.kommentar == "Verkleidung, nach Statik Anlage 3"
           and _stab_elementlasten(m) == 6), f"{_stab_elementlasten(m)} Elementlasten")
    # Grund, wenn nichts entsteht
    m2 = _mast()
    m2.members["Leer"] = Member("Leer", [])
    l2 = m2.add_linienlast("Leer", [0.0, 0.0, -1e3], art="stab")
    l2.kommentar = "noch zu entwerfen"
    log = []
    m2.lasten_verteilen(log)
    check("N05 Modell: ohne Element steht der Grund in „verteilt“, der Kommentar bleibt",
          getattr(l2, "verteilt", "") == "Stab hat keine Elemente" and l2.kommentar == "noch zu entwerfen",
          f"{getattr(l2, 'verteilt', None)!r} / {l2.kommentar!r}")
    check("N05 Modell: das Protokoll nennt den Grund weiter (Kontrolle des Zählens)",
          any("Stab hat keine Elemente" in z for z in log), str(log))
    # Speichern und Laden
    d = m.to_dict()
    ll_d = [x for lc in d["load_cases"] for x in lc["linienlasten"]]
    check("N05 Datei: der Kommentar wird gespeichert, der Stand des Verteilens nicht",
          len(ll_d) == 1 and ll_d[0]["kommentar"] == "Verkleidung, nach Statik Anlage 3" and "verteilt" not in ll_d[0],
          str(ll_d))
    m3 = Model.from_dict(json.loads(json.dumps(d)))
    l3 = _linienlasten(m3)[0]
    check("N05 Datei: nach dem Laden stehen Kommentar und (neu berechneter) Stand wieder da",
          l3.kommentar == "Verkleidung, nach Statik Anlage 3" and getattr(l3, "verteilt", "") == "6 Elementlasten",
          f"{l3.kommentar!r} / {getattr(l3, 'verteilt', None)!r}")


def test_n05_anzeige():
    """Tabelle (Register Lasten) und Bericht zeigen Kommentar und Stand nebeneinander."""
    from statik3d.report.html import Report
    m = _mast()
    ll = m.add_linienlast("Mast", [0.0, 0.0, -5e3], art="stab", von=1.0, bis=3.0)
    ll.kommentar = "Verkleidung"
    m.lasten_verteilen()
    lc = m.case()
    tab = Report(m)._load_tables(lc)
    zeilen = [t[1] for t in tab if t[0] == "table" and "Linienlasten" in str(t[2])]
    text = json.dumps(zeilen, ensure_ascii=False)
    check("N05 Bericht: die Linienlast-Tabelle nennt „2 Elementlasten“ und den Kommentar „Verkleidung“",
          "2 Elementlasten" in text and "Verkleidung" in text, text[-160:])
    # Fenster
    w, app = _fenster()
    _setzen(w, app, m)
    w.tabelle_zeigen("Lasten")
    app.processEvents()
    zl = [z for z in w.tbl_last.modell.zeilen if str(z[2]) == "Linienlast"]
    letzte = str(zl[0][-1]) if zl else ""
    check("N05 Lasttabelle: die Bemerkung nennt Abschnitt, „2 Elementlasten“ und den Kommentar",
          "2 Elementlasten" in letzte and "Verkleidung" in letzte and "von 1 m bis 3 m" in letzte.replace(",0", ""),
          repr(letzte))
    # Kontrolle: ohne eigenen Kommentar steht nur der Stand da, kein Strichpunkt
    ll.kommentar = ""
    w.refresh_all()
    app.processEvents()
    zl = [z for z in w.tbl_last.modell.zeilen if str(z[2]) == "Linienlast"]
    letzte = str(zl[0][-1]) if zl else ""
    check("N05 Lasttabelle: ohne Kommentar steht nur der Stand da, kein loses „;“",
          "2 Elementlasten" in letzte and ";" not in letzte, repr(letzte))


def test_n05_wind_kommentar_im_programmformat():
    """Der Kommentar der Windlast bleibt jetzt stehen und kommt in Tabelle und Bericht:
    Zahlen mit Dezimalkomma wie im Programm, nicht „1.20“."""
    from statik3d import wind as wm
    from statik3d.wind import Wind
    m = _mast()
    wm.lasten_erzeugen(m, Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    ll = _linienlasten(m, "Wind W")[0]
    check("N05 Wind: der Kommentar der Windlast bleibt stehen, mit c_f und b_ref im Programmformat",
          ll.kommentar.startswith("Wind W: c_f = ") and "b_ref = 0,2 m" in ll.kommentar
          and not re.search(r"\d\.\d", ll.kommentar) and getattr(ll, "verteilt", "") == "6 Elementlasten",
          f"{ll.kommentar!r} / {getattr(ll, 'verteilt', None)!r}")


def _alte_datei(m) -> dict:
    """Die Datei, wie sie vor dem 07.10.2026 geschrieben wurde: der Stand des
    Verteilens steht im Kommentar, ein Merkmal ``erzeuger`` gab es vor dem
    06.10.2026 nicht."""
    d = json.loads(json.dumps(m.to_dict()))
    for lc in d["load_cases"]:
        for x in lc["linienlasten"]:
            x.pop("erzeuger", None)
            x.pop("verteilt", None)
            x["kommentar"] = "6 Elementlasten"
    return d


def test_n05_alte_datei():
    from statik3d import wind as wm
    from statik3d.wind import Wind
    m = _mast()
    w = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    wm.lasten_erzeugen(m, w)
    eigen = m.add_linienlast("Mast", [0.0, 500.0, 0.0], art="stab", case=w.lastfall)
    eigen.kommentar = "von Hand"
    m.lasten_verteilen()
    d = _alte_datei(m)
    # die eigene Last der alten Datei: ein Kommentar, der kein Stand ist, bleibt
    for lc in d["load_cases"]:
        for x in lc["linienlasten"]:
            if x["q"] == [0.0, 500.0, 0.0]:
                x["kommentar"] = "von Hand"
    m2 = Model.from_dict(d)
    ll = {tuple(x.q): x for x in _linienlasten(m2, w.lastfall)}
    wind_ll = [x for x in ll.values() if x.q != [0.0, 500.0, 0.0]]
    check("N05 alte Datei: der Stand im Kommentar („6 Elementlasten“) wird beim Laden abgelöst",
          len(wind_ll) == 1 and wind_ll[0].kommentar == "" and wind_ll[0].verteilt == "6 Elementlasten",
          f"{[(x.kommentar, getattr(x, 'verteilt', None)) for x in wind_ll]}")
    check("N05 alte Datei: die Windlast bekommt dabei ihr Merkmal (erzeuger = wind:W)",
          len(wind_ll) == 1 and wind_ll[0].erzeuger == "wind:W", str([x.erzeuger for x in wind_ll]))
    check("N05 alte Datei: ein echter Kommentar („von Hand“) bleibt",
          ll[(0.0, 500.0, 0.0)].kommentar == "von Hand", repr(ll[(0.0, 500.0, 0.0)].kommentar))
    vorher = (len(_linienlasten(m2, w.lastfall)), _stab_elementlasten(m2, w.lastfall))
    wm.lasten_erzeugen(m2, m2.winde["W"])
    nachher = (len(_linienlasten(m2, w.lastfall)), _stab_elementlasten(m2, w.lastfall))
    check("N05 alte Datei (Kontrolle P1): „Lasten erzeugen“ auf der geladenen Datei verdoppelt nichts",
          vorher == nachher, f"{vorher} -> {nachher}")
    # Erkennung ohne Laden (wie tests.test_wind): der Stand im Kommentar genuegt weiter
    m3 = _mast()
    wm.lasten_erzeugen(m3, Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    erst = (len(_linienlasten(m3, "Wind W")), _stab_elementlasten(m3, "Wind W"))
    for x in _linienlasten(m3, "Wind W"):
        x.kommentar, x.erzeuger = "6 Elementlasten", ""
    wm.lasten_erzeugen(m3, Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    check("N05 Erkennung alter Dateien (Kontrolle): „6 Elementlasten“ ohne Merkmal wird weiter erkannt",
          (len(_linienlasten(m3, "Wind W")), _stab_elementlasten(m3, "Wind W")) == erst,
          f"{erst} -> {(len(_linienlasten(m3, 'Wind W')), _stab_elementlasten(m3, 'Wind W'))}")


# --------------------------------------------------------------------------
# N11 - doppelte Knoten zusammenfuehren
# --------------------------------------------------------------------------
def _basis_knoten():
    """Einfeldtraeger (Knoten 0 bis 4) mit Knoten dahinter: j liegt auf Knoten 0,
    k, n, p sind frei, pd liegt auf p. Nach dem Zusammenfuehren: j -> 0,
    k 6 -> 5, n 7 -> 6, p 8 -> 7, pd 9 -> 7."""
    m = Model("Doppelte")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6.0, 0, 0), 4)
    m.add_member("A", list(range(4)))
    m.fix(0, [0, 1, 2, 3])
    m.fix(4, [1, 2])
    j = m.add_node(0.0, 0.0, 0.0)
    k, n, p = (m.add_node(20.0 + i, 2.0, 0.0) for i in range(3))
    pd = m.add_node(*m.nodes[p])
    return m, j, k, n, p, pd


def _orte(m, ids) -> list:
    return [tuple(round(float(x), 9) for x in m.nodes[int(i)]) if 0 <= int(i) < m.nn else None for i in ids]


def _v_linie(m, j, k, p, pd):
    m.add_line("L1", [j, k, p])
    return lambda m: list(m.lines["L1"].nodes)


def _v_flaeche_ecke(m, j, k, p, pd):
    m.flaechen["F1"] = Flaeche("F1", [], ecken=[j, 1, p, k])
    return lambda m: list(m.flaechen["F1"].ecken)


def _v_flaeche_integriert(m, j, k, p, pd):
    m.flaechen["F2"] = Flaeche("F2", [], integrierte_knoten=[k, j, p, pd])
    return lambda m: list(m.flaechen["F2"].integrierte_knoten)


def _v_kopplung(m, j, k, p, pd):
    m.kopplungen.append(Kopplung(k, p, [[1.0, 0.0, 0.0]], [1e9]))
    return lambda m: [m.kopplungen[0].node_a, m.kopplungen[0].node_b]


def _v_starrkoerper(m, j, k, p, pd):
    m.add_starrkoerper(j, [k, p], art="RBE3", gewichte=[1.0, 2.0])
    return lambda m: [m.starrkoerper[0].master] + list(m.starrkoerper[0].slaves)


def _v_punktmasse(m, j, k, p, pd):
    m.add_punktmasse(k, 100.0)
    return lambda m: [m.punktmassen[0].node]


def _v_daempfer(m, j, k, p, pd):
    m.add_daempfer(k, p, c=[1e3, 0, 0])
    return lambda m: [m.daempfer[0].node_a, m.daempfer[0].node_b]


def _v_layer(m, j, k, p, pd):
    m.layer["L"] = Layer("L", knoten=[j, k, p])
    return lambda m: list(m.layer["L"].knoten)


def _v_subsystem(m, j, k, p, pd):
    m.subsysteme["T"] = Subsystem("T", knoten=[k, p])
    return lambda m: list(m.subsysteme["T"].knoten)


def _v_lasteinleitung(m, j, k, p, pd):
    m.add_lasteinleitung("LE1", k)
    return lambda m: [m.lasteinleitungen["LE1"].knoten]


def _v_verformungsgrenze(m, j, k, p, pd):
    m.add_verformungsgrenze("VG1", art="punktpaar", knoten=[k, p], grenzart="absolut", wert=0.01)
    return lambda m: list(m.verformungsgrenzen["VG1"].knoten)


def _v_linienlager(m, j, k, p, pd):
    m.add_line_support([j, k, p], uz=dict(typ="spring", stiffness=1e6))
    return lambda m: list(m.line_supports[-1].nodes)


def _v_flaechenlager(m, j, k, p, pd):
    m.add_surface_support(nodes=[k, p, pd], areas=[1.0, 2.0, 3.0], uz=dict(typ="spring", stiffness=1e6))
    return lambda m: list(m.surface_supports[-1].nodes)


def _v_flaechenlager_gruppen(m, j, k, p, pd):
    ss = m.add_surface_support(nodes=[k, p], areas=[1.0, 2.0], uz=dict(typ="spring", stiffness=1e6))
    ss.lokal = True
    ss.gruppen = [[2, 1, [k, p], [1.0, 2.0]]]
    return lambda m: list(m.surface_supports[-1].gruppen[0][2])


def _v_zwang(m, j, k, p, pd):
    m.add_zwangsverformung(k, [2], [-0.001])
    return lambda m: [m.case().zwangsverformungen[0].node]


def _v_spalt(m, j, k, p, pd):
    m.add_gap_element(k, p)
    return lambda m: [m.gap_elements[0].node_a, m.gap_elements[0].node_b]


def _v_kontaktlager(m, j, k, p, pd):
    m.add_contact_support(k, (0, 0, 1))
    return lambda m: [m.contact_supports[0].node]


def _v_kontaktpaar_slave(m, j, k, p, pd):
    m.add_contact_pair("KP1", [k, p, pd], master_faces=[[0, 1, 2]])
    return lambda m: list(m.contact_pairs[0].slave_nodes)


def _v_kontaktpaar_master(m, j, k, p, pd):
    m.add_contact_pair("KP2", [0], master_faces=[[j, k, p]])
    return lambda m: list(m.contact_pairs[0].master_faces[0])


def _v_kontaktpaar_passung(m, j, k, p, pd):
    cp = m.add_contact_pair("KP3", [k, p, pd], master_faces=[[0, 1, 2]])
    cp.knotenflaechen = {k: 1.0, p: 2.0, pd: 3.0}
    cp.rand_knoten = [p, pd]
    # gelesen werden die Knoten der Einflussflaechen und der Randknoten
    return lambda m: sorted(m.contact_pairs[0].knotenflaechen) + list(m.contact_pairs[0].rand_knoten)


def _v_antrieb(m, j, k, p, pd):
    from statik3d.bridges.positions import Stellung
    m.stellungen.append(Stellung("S1", 30.0, antrieb=(k, (0.0, 0.0, 5e4)), faelle=["LF1"]))
    return lambda m: [m.stellungen[0].antrieb[0]]


def _v_getrennte(m, j, k, p, pd):
    m.getrennte_knoten["Fuge"] = [[k, p], [j, 1]]
    return lambda m: [n for paar in m.getrennte_knoten["Fuge"] for n in paar]


def _v_knotenlast(m, j, k, p, pd):
    m.load_node(k, Fz=-1e3)
    return lambda m: [m.case().nodal_loads[0].node]


def _v_knotenlager(m, j, k, p, pd):
    m.fix(k, [2])
    return lambda m: [m.supports[-1].node]


#: Verweisarten, die ``Model._knotenverweise_abbilden`` (Loeschen und Tauschen eines
#: Knotens) kennt: (Art, Aufbau). Der Aufbau gibt eine Lesefunktion zurueck, die
#: die Knotennummern des Verweises nennt. Gleich gewordene Knoten fuehrt ein
#: Verweis einmal (Menge), darum vergleicht die Pruefung die **Orte als Menge**;
#: bei Verweisen, die ihre Reihenfolge brauchen, steht dahinter ``True``.
VERWEISE = (("Linie", _v_linie, True),
            ("Eckknoten einer Fläche", _v_flaeche_ecke, True),
            ("integrierter Knoten einer Fläche", _v_flaeche_integriert, False),
            ("Kopplung", _v_kopplung, True),
            ("Starrer Körper (Master und Slaves)", _v_starrkoerper, True),
            ("Punktmasse", _v_punktmasse, True),
            ("Dämpfer", _v_daempfer, True),
            ("Layer", _v_layer, False),
            ("Subsystem", _v_subsystem, False),
            ("Lasteinleitung", _v_lasteinleitung, True),
            ("Verformungsgrenze", _v_verformungsgrenze, True),
            ("Linienlager", _v_linienlager, False),
            ("Flächenlager über Knoten", _v_flaechenlager, False),
            ("Flächenlager, Normalengruppe", _v_flaechenlager_gruppen, True),
            ("Zwangsverformung", _v_zwang, True),
            ("Spaltelement", _v_spalt, True),
            ("Kontaktlager", _v_kontaktlager, True),
            ("Kontaktpaar, Slave-Knoten", _v_kontaktpaar_slave, False),
            ("Kontaktpaar, Master-Facette", _v_kontaktpaar_master, True),
            ("Kontaktpaar, Einflussflächen und Randknoten", _v_kontaktpaar_passung, False),
            ("Antrieb einer Stellung", _v_antrieb, True),
            ("getrennte Fugenknoten", _v_getrennte, True),
            ("Knotenlast", _v_knotenlast, True),
            ("Knotenlager", _v_knotenlager, True))


def test_n11_verweise_folgen_dem_zusammenfuehren():
    for art, aufbau, reihenfolge in VERWEISE:
        m, j, k, n, p, pd = _basis_knoten()
        lesen = aufbau(m, j, k, p, pd)
        soll = _orte(m, lesen(m))
        weg = mesher.merge_nodes(m)
        ist = _orte(m, lesen(m))
        gleich = (ist == soll) if reihenfolge else (set(ist) == set(soll))
        check(f"N11 {art}: nach dem Zusammenfügen am selben Ort ({weg} Knoten weg)",
              weg == 2 and gleich and None not in ist, f"{soll} -> {ist}")
    # Kantenmitten gekruemmter tetp-Kanten: der Schluessel sind zwei Knoten
    m, j, k, n, p, pd = _basis_knoten()
    t = [m.add_node(*q) for q in ((30, 0, 0), (31, 0, 0), (30, 1, 0), (30, 0, 1))]
    m.add_element("tetp2", t, "S235")
    mitte = np.array([30.5, 0.0, 0.1])
    m.tetp_kantenmitten = {(t[0], t[1]): mitte}
    mesher.merge_nodes(m)
    gelesen = tetp_kantenmitten_gelesen(m.tetp_kantenmitten, m.elements)
    (a, b), q = next(iter(gelesen.items())) if gelesen else ((-1, -1), None)
    check("N11 Kantenmitte eines tetp-Elements: sie bleibt an ihrer Kante",
          len(gelesen) == 1 and sorted(_orte(m, [a, b])) == [(30.0, 0.0, 0.0), (31.0, 0.0, 0.0)]
          and np.allclose(q, mitte), str(m.tetp_kantenmitten))


def test_n11_dedupe_und_zaehlung():
    """Kontrollen: was schon galt, gilt weiter."""
    m, j, k, n, p, pd = _basis_knoten()
    m.add_contact_pair("KP", [k, p, pd], master_faces=[[0, 1, 2]])
    mesher.merge_nodes(m)
    sl = m.contact_pairs[0].slave_nodes
    check("N11 Kontrolle: gleich gewordene Slave-Knoten eines Kontaktpaars stehen nur einmal da",
          sorted(sl) == sorted(set(sl)) and len(sl) == 2, str(sl))
    m, j, k, n, p, pd = _basis_knoten()
    ss = m.add_surface_support(nodes=[k, p, pd], areas=[1.0, 2.0, 3.0], uz=dict(typ="spring", stiffness=1e6))
    mesher.merge_nodes(m)
    a_p = dict(zip(ss.nodes, ss.areas))
    check("N11 Flächenlager: die Einflussfläche des zusammengeführten Knotens ist die Summe (2 + 3)",
          len(ss.nodes) == 2 and abs(a_p.get(7, 0.0) - 5.0) < 1e-12 and abs(a_p.get(5, 0.0) - 1.0) < 1e-12,
          f"{ss.nodes} {ss.areas}")
    # Zaehlung und Vorschau stimmen ueberein
    m, j, k, n, p, pd = _basis_knoten()
    vorschau = mesher.doppelte_knoten(m)
    check("N11 Kontrolle: Vorschau (doppelte_knoten) und Zusammenführen zählen gleich",
          vorschau == mesher.merge_nodes(m) == 2 and mesher.doppelte_knoten(m) == 0, str(vorschau))
    # eine Stellung mit Lager und Berechnung: das Ergebnis bleibt bitgleich
    from statik3d import solver
    m, j, k, n, p, pd = _basis_knoten()
    m.load_node(2, Fz=-10e3)
    ref = Model.from_dict(m.to_dict())
    mesher.merge_nodes(ref)
    r = solver.solve_static(ref)
    m0 = Model.from_dict(m.to_dict())
    m0.nodes = m0.nodes[:5]
    r0 = solver.solve_static(m0)
    check("N11 Kontrolle: die Rechnung des Trägers ändert sich durch das Zusammenführen nicht",
          np.allclose(r.u[:5], r0.u[:5], rtol=0, atol=0), f"{float(np.abs(r.u[:5] - r0.u[:5]).max()):.3g}")


# --------------------------------------------------------------------------
# N18 - Lager entfernen, Stellungen nachziehen
# --------------------------------------------------------------------------
def _stellungsziel(m, st, feld="lager_aus", art="lager") -> list:
    """Die Knoten der Lager, die die Stellung in ``feld`` nennt (Schluessel -> Lager)."""
    liste = {"lager": m.supports, "linienlager": m.line_supports,
             "flaechenlager": m.surface_supports}[art]
    schl = m.lagerschluessel(art, liste)
    aus = []
    for x in getattr(st, feld):
        i = schl.index(x) if x in schl else -1
        if i < 0:
            aus.append(None)
        elif art == "lager":
            aus.append(int(liste[i].node))
        else:
            aus.append(tuple(liste[i].nodes))
    return aus


def test_n18_aus_tet10():
    from statik3d.bridges.positions import Stellung
    from statik3d.elements import tetp as tp
    m = Model("tetp")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    ecken = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    kn = [m.add_node(*e) for e in ecken]
    for a, b in tp.TET10_KANTEN:
        kn.append(m.add_node(*(0.5 * (np.asarray(ecken[a], float) + np.asarray(ecken[b], float)))))
    m.add_element("tet10", kn, "S235")
    m.fix(kn[0], "all")                       # Lager 1, heisst „Rand“
    m.fix(kn[1], "all")                       # Lager 2
    m.fix(kn[4], "all")                       # Lager 3 „Mitte“: Mittenknoten der Kante 0-1, faellt weg
    m.fix(kn[2], [2])                         # Lager 4 (ohne Namen): bleibt
    m.supports[0].name, m.supports[2].name = "Rand", "Mitte"
    # „Lager 4“ meint das vierte Lager; „nur diese Lager aktiv“ nennt nur Namen
    m.stellungen.append(Stellung("S1", 0.0, lager_aus=["Lager 4"], lager_aktiv=["Rand", "Mitte"]))
    st = m.stellungen[0]
    vorher = (_stellungsziel(m, st), _stellungsziel(m, st, "lager_aktiv"))
    info = _rufen(tp.aus_tet10, m, ordnung=3)
    nachher = (_stellungsziel(m, st), _stellungsziel(m, st, "lager_aktiv"))
    check("N18 aus_tet10 (Vorbereitung): „Lager 4“ ist das Lager an Ecke 2, „Mitte“ das am Mittenknoten",
          vorher == ([kn[2]], [kn[0], kn[4]]), str(vorher))
    check("N18 aus_tet10: das Lager am Mittenknoten ist weg, drei Lager bleiben",
          not isinstance(info, Exception) and len(m.supports) == 3, f"{info if isinstance(info, Exception) else len(m.supports)}")
    check("N18 aus_tet10: „lager_aus“ nennt weiter das Lager an Ecke 2 (aus „Lager 4“ wurde „Lager 3“)",
          vorher[0] == [kn[2]] and nachher[0] == [kn[2]] and st.lager_aus == ["Lager 3"],
          f"{vorher[0]} -> {nachher[0]}, Eintrag {st.lager_aus}")
    check("N18 aus_tet10: „nur diese Lager aktiv“: das entfernte Lager „Mitte“ geht aus der Liste, „Rand“ bleibt",
          st.lager_aktiv == ["Rand"], str(st.lager_aktiv))
    check("N18 aus_tet10: die Rückgabe sagt, was an den Stellungen geändert wurde",
          isinstance(info, dict) and any("Lager 4" in z for z in info.get("stellungen", []))
          and any("Mitte" in z for z in info.get("stellungen", [])),
          str(info.get("stellungen") if isinstance(info, dict) else info))


def test_n18_keep_structure():
    from statik3d.bridges.positions import Stellung
    from statik3d.importers import rfem6_db
    from statik3d.model import LineSupport, SurfaceSupport
    m = Model("rf6")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_section(Section.i_profile("IPE 300", 0.300, 0.150, 0.0071, 0.0107))
    a, b = m.add_node(0, 0, 0), m.add_node(4, 0, 0)
    f1, f2, f3 = (m.add_node(10.0 + i, 5, 0) for i in range(3))      # freie Knoten ohne Element
    m.add_element("beam", [a, b], "S235", "IPE 300")
    m.fix(f1, "all")                           # Lager 1: freier Knoten, fliegt raus
    m.fix(a, "all")                            # Lager 2
    m.fix(b, [1, 2])                           # Lager 3
    # Linien- und Flaechenlager ohne Namen, damit ihr Schluessel „Linienlager 2“ der Platz ist
    m.line_supports.append(LineSupport("", [f1, f2]))                       # Linienlager 1: fliegt raus
    m.line_supports.append(LineSupport("", [a, b]))                         # Linienlager 2
    m.surface_supports.append(SurfaceSupport("", nodes=[f2, f3], areas=[1.0, 1.0]))   # Flaechenlager 1: raus
    m.surface_supports.append(SurfaceSupport("", nodes=[a, b], areas=[1.0, 1.0]))     # Flaechenlager 2
    m.stellungen.append(Stellung("S1", 0.0, lager_aus=["Lager 3"],
                                 linienlager_aus=["Linienlager 2"], flaechenlager_aus=["Flächenlager 2"]))
    st = m.stellungen[0]
    log = []
    weg = _rufen(rfem6_db.keep_structure, m, log)
    ziel = [_stellungsziel(m, st), _stellungsziel(m, st, "linienlager_aus", "linienlager"),
            _stellungsziel(m, st, "flaechenlager_aus", "flaechenlager")]
    check("N18 keep_structure: drei freie Knoten weg, Lager 1, Linienlager 1 und Flächenlager 1 mit ihnen",
          weg == 3 and len(m.supports) == 2 and len(m.line_supports) == 1 and len(m.surface_supports) == 1,
          f"{weg} {len(m.supports)} {len(m.line_supports)} {len(m.surface_supports)}")
    check("N18 keep_structure: „lager_aus“ nennt weiter das Lager am Stabende (Knoten 1)",
          ziel[0] == [1] and st.lager_aus == ["Lager 2"], f"{ziel[0]} {st.lager_aus}")
    check("N18 keep_structure: „linienlager_aus“ und „flaechenlager_aus“ nennen weiter ihr Lager",
          ziel[1] == [(0, 1)] and ziel[2] == [(0, 1)]
          and st.linienlager_aus == ["Linienlager 1"] and st.flaechenlager_aus == ["Flächenlager 1"],
          f"{ziel[1]} {ziel[2]} {st.linienlager_aus} {st.flaechenlager_aus}")
    check("N18 keep_structure: das Protokoll sagt, welche Einträge sich geändert haben",
          sum("Stellung „S1“" in z for z in log) == 3, str([z for z in log if "Stellung" in z]))


# --------------------------------------------------------------------------
# N22 - Browser: Ermuedungslast und Anschlussnachweis
# --------------------------------------------------------------------------
def _halle_mit_anschluss():
    from statik3d import examples_lib
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose
    m = examples_lib.build_example("hall")
    e_kopf = m.members["Riegel"].elements[0]
    m.joints["K1"] = A.als_joint(propose("kopfplatte", m, e_kopf, end=0, N=-50e3, Vz=150e3, My=300e3), "K1")
    m.fatigue_loads["E1"] = FatigueLoad("E1", case_max="Kran", case_min="LF1", cycles=2e6)
    m.fatigue_loads["E2"] = FatigueLoad("E2", case_max="S", case_min="LF1", cycles=2e6)
    m.joints["K1"].ermuedung = []                  # leer heisst: alle Ermuedungslasten
    return m


def test_n22_browser_ermuedungslast():
    from statik3d import solver
    from statik3d.web.server import State, apply_op
    m = _halle_mit_anschluss()
    st = State(m)
    st.analysis = solver.solve_all(m, design=True, fatigue=True)
    d_vorher = st.analysis.joints.joints["K1"].D if st.analysis.joints is not None else None
    check("N22 Vorbereitung: die Analyse trägt den Anschlussnachweis mit D > 0 (alle Lasten)",
          st.analysis.joints is not None and d_vorher and d_vorher > 0, f"D = {d_vorher}")
    apply_op(st, {"op": "remove_fatigue_load", "name": "E1"})
    an = st.analysis
    check("N22 remove_fatigue_load: Nachweise, Ermüdung und Anschlussnachweis sind verworfen",
          an is None or (an.design is None and an.fatigue is None and an.joints is None),
          f"design {getattr(an, 'design', 0) is None}, fatigue {getattr(an, 'fatigue', 0) is None}, "
          f"joints {getattr(an, 'joints', 0) is None}")
    check("N22 remove_fatigue_load: E1 ist weg, E2 bleibt (Kontrolle)",
          "E1" not in st.model.fatigue_loads and "E2" in st.model.fatigue_loads, str(list(st.model.fatigue_loads)))
    # Kontrolle: die Rechnung der Lastfaelle bleibt stehen, es gilt weiter nur „Nachweise neu“
    check("N22 remove_fatigue_load (Kontrolle): die Ergebnisse der Lastfälle bleiben",
          an is not None and bool(an.cases), f"{len(an.cases) if an is not None else 0} Lastfälle")
    # dasselbe fuer das Anlegen: leere Anschlussliste = alle, eine neue Last aendert D
    m = _halle_mit_anschluss()
    st = State(m)
    st.analysis = solver.solve_all(m, design=True, fatigue=True)
    apply_op(st, {"op": "add_fatigue_load", "name": "E3", "case_max": "S", "case_min": "LF1", "cycles": 1e6})
    an = st.analysis
    check("N22 add_fatigue_load: auch hier ist der Anschlussnachweis verworfen",
          an is None or an.joints is None, f"joints {getattr(an, 'joints', 0) is None}")
    # andere Nachweisoperationen behalten den Anschlussnachweis wie bisher (Kontrolle)
    m = _halle_mit_anschluss()
    st = State(m)
    st.analysis = solver.solve_all(m, design=True, fatigue=False)
    apply_op(st, {"op": "design_settings"})
    check("N22 design_settings (Kontrolle): unverändert - der Anschlussnachweis bleibt, die Nachweise gehen",
          st.analysis is not None and st.analysis.design is None and st.analysis.joints is not None,
          f"design {getattr(st.analysis, 'design', 0) is None}, joints {getattr(st.analysis, 'joints', 0) is None}")


# --------------------------------------------------------------------------
# N23 - Wind loeschen und umbenennen: Stablasten am Merkmal
# --------------------------------------------------------------------------
def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    B = QtWidgets.QMessageBox
    for art in ("critical", "warning", "information"):
        setattr(B, art, staticmethod(lambda *a, **k: B.Ok))
    B.question = staticmethod(lambda *a, **k: B.No)
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    _FENSTER.update(w=w, app=app)
    return w, app


def _setzen(w, app, m):
    from PySide6 import QtWidgets
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        for b in leiste.findChildren(QtWidgets.QPushButton):
            if b.text() == "Verwerfen":
                b.click()
                break
    w.maskenrand.schliessen()
    w._modell_setzen(m)
    app.processEvents()


def _mast_mit_wind(kommentar_aendern: bool):
    from statik3d import wind as wm
    from statik3d.wind import Wind
    m = _mast()
    w = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    wm.lasten_erzeugen(m, w)
    eigen = m.add_linienlast("Mast", [0.0, 500.0, 0.0], art="stab", case=w.lastfall)
    eigen.kommentar = "von Hand"
    m.lasten_verteilen()
    if kommentar_aendern:
        # der Anwender hat den Kommentar der Windlast geaendert
        for x in m.case(w.lastfall).linienlasten:
            if x.erzeuger == "wind:W":
                x.kommentar = "Windlast auf den Mast, geprüft"
    return m, w.lastfall


def test_n23_wind_loeschen():
    w, app = _fenster()
    m, fall = _mast_mit_wind(kommentar_aendern=True)
    _setzen(w, app, m)
    check("N23 Vorbereitung: Windlast (6 Elementlasten) und eine eigene Linienlast im Lastfall",
          len(_linienlasten(w.model, fall)) == 2 and _stab_elementlasten(w.model, fall) == 12,
          f"{len(_linienlasten(w.model, fall))} Linienlasten, {_stab_elementlasten(w.model, fall)} Elementlasten")
    w._baum_loeschen("wind", "W")
    app.processEvents()
    ll = _linienlasten(w.model, fall)
    check("N23 Modellbaum: Wind gelöscht - seine Stablast ist weg, die eigene Linienlast bleibt",
          "W" not in w.model.winde and len(ll) == 1 and ll[0].kommentar == "von Hand", str([(x.q, x.kommentar) for x in ll]))
    check("N23 Modellbaum: die daraus verteilten Elementlasten sind mit weg (6 von 12)",
          _stab_elementlasten(w.model, fall) == 6, str(_stab_elementlasten(w.model, fall)))
    # Datei von vorher: Merkmal fehlt, der Stand steht im Kommentar
    m, fall = _mast_mit_wind(kommentar_aendern=False)
    d = _alte_datei(m)
    for lc in d["load_cases"]:
        for x in lc["linienlasten"]:
            if x["q"] == [0.0, 500.0, 0.0]:
                x["kommentar"] = "von Hand"
    _setzen(w, app, Model.from_dict(d))
    w._baum_loeschen("wind", "W")
    app.processEvents()
    ll = _linienlasten(w.model, fall)
    check("N23 Modellbaum, Datei von vorher (ohne Merkmal): die Windlast wird ebenso erkannt und gelöscht",
          "W" not in w.model.winde and len(ll) == 1 and ll[0].q == [0.0, 500.0, 0.0],
          str([(x.q, x.kommentar) for x in ll]))
    # die Modellfunktion allein: Stand im Kommentar, kein Merkmal (Datei vor dem 06.10.2026,
    # nicht ueber from_dict gegangen) - sie erkennt die Windlast an Lastfall, Stab und Richtung,
    # nicht die eigene Last quer dazu
    from statik3d import wind as wm
    from statik3d.wind import Wind
    m, fall = _mast_mit_wind(kommentar_aendern=False)
    for x in m.case(fall).linienlasten:
        if x.erzeuger:
            x.kommentar, x.erzeuger = "6 Elementlasten", ""
    n = _rufen(getattr(wm, "stablasten_entfernen", None) or (lambda *a: AttributeError("fehlt")), m, m.winde["W"])
    m.lasten_verteilen()
    ll = _linienlasten(m, fall)
    check("N23 wind.stablasten_entfernen: ohne Merkmal an Lastfall, Stab und Richtung, die eigene Last bleibt",
          n == 1 and len(ll) == 1 and ll[0].kommentar == "von Hand" and _stab_elementlasten(m, fall) == 6,
          f"{n} {[(x.q, x.kommentar) for x in ll]}")
    mk = _mast()
    wm.lasten_erzeugen(mk, Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    _setzen(w, app, mk)
    w._baum_loeschen("wind", "W")
    app.processEvents()
    check("N23 Modellbaum: Wind ohne eigene Linienlast - Wind, Stablast und Elementlasten weg",
          "W" not in w.model.winde and not _linienlasten(w.model, "Wind W") and _stab_elementlasten(w.model, "Wind W") == 0)


def test_n23_wind_umbenennen():
    w, app = _fenster()
    m, fall = _mast_mit_wind(kommentar_aendern=True)
    _setzen(w, app, m)
    w.maske_wind("W")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("name", "W2")
    erg = mk.anwenden()
    app.processEvents()
    ll = _linienlasten(w.model, fall)
    marken = sorted(x.erzeuger for x in ll)
    check("N23 Windmaske: Wind „W“ in „W2“ umbenannt - die alte Stablast ist weg, die neue da, die eigene bleibt",
          erg is True and "W2" in w.model.winde and "W" not in w.model.winde
          and marken == ["", "wind:W2"], f"{erg} {marken}")
    check("N23 Windmaske: Elementlasten nicht verdoppelt (12 = 6 Wind + 6 eigene)",
          _stab_elementlasten(w.model, fall) == 12, str(_stab_elementlasten(w.model, fall)))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_n05_kommentar_bleibt, test_n05_anzeige, test_n05_wind_kommentar_im_programmformat,
              test_n05_alte_datei,
              test_n11_verweise_folgen_dem_zusammenfuehren, test_n11_dedupe_und_zaehlung,
              test_n18_aus_tet10, test_n18_keep_structure,
              test_n22_browser_ermuedungslast,
              test_n23_wind_loeschen, test_n23_wind_umbenennen):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    sys.stdout.flush()
    os._exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
