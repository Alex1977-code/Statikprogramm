"""
Namen der Erzeuger - Paket R2-C1 (Generatoren und Beispiele), 06.10.2026.

Entscheidung des Anwenders vom 04.10.2026: ein Lastfall heisst LF<Nr>, eine
Lastkombination LK<Nr>, eine Ergebniskombination EK<Nr>; der bisherige freie
Name wird zur Bezeichnung („LF3 W_links“). R2-C1 stellt alle Stellen um, die
Namen **erzeugen**: den Kombinationsgenerator (EN 1990), DIN 19704, das
Lastenheft, Wind, Wasserdruck, den Antrieb der Stellungen und die eingebauten
Beispiele. Erzwungen wird noch nichts (Paket R2-E).

Abnahme G1 bis G6 (vorher festgelegt) plus die Faelle der Hauptsitzung aus der
Rueckmeldung von A2 (G7) und die Nebenbefunde aus der Gegenpruefung von A1:

G1  Generator auf der Halle: 72 Kombinationen LK1…LK72, Bezeichnung nach
    Muster, Typ wie vorher, Rechnung (Lastfaelle, Kombinationen, Umhuellende,
    EC3, Ermuedung) zahlengleich mit c5dbb10, Zuordnung ueber die Faktoren
G2  Generator zweimal, dazwischen eine erzeugte Kombination umbenannt und
    eine von Hand geaendert: beide bleiben, die uebrigen werden ersetzt (mit
    ihren Nummern), keine Nummer doppelt
G3  DIN 19704, Lastenheft, Wind, Wasserdruck und der Generator in einem neuen
    Modell: nur LF<n>/LK<n> mit Bezeichnung, keine Kollision, check() ohne neue
    Meldung
G4  Wind „Lasten erzeugen“ zweimal am Mast mit Staeben: gleiche Zahl Linien-
    und Elementlasten, gleiche Summe (auf 36f8d8f: 1 -> 2 und 6 -> 12);
    dasselbe fuer den Wasserdruck und nach Speichern und Laden
G5  alle eingebauten Beispiele: nur LF/LK/EK-Namen, Rechnung zahlengleich mit
    c5dbb10 (Zuordnung alt -> neu ueber die Bezeichnung)
G6  Gesamtlauf ``python -m tests.run_all`` (ohne --gui): diese Suite steht in der
    Liste; der Lauf selbst steht in der Rueckmeldung
G7  jeder Generator findet seine Objekte am Fingerabdruck und nie am Namen:
    ein Modell, dessen erzeugte Kombinationen umbenannt wurden (wie nach der
    Umstellung beim Laden), bekommt beim zweiten Lauf keine Doppel; Wind und
    Wasserdruck schreiben in den umbenannten Lastfall
G8  Nummern halten: eine Nummer, auf die eine Ermuedungslast zeigt, wird nie
    an eine andere Kombination vergeben
G9  Antrieb der Stellung: LF<n> mit der Nummer des Basismodells, nur in der
    Rechenkopie
G10 Lastenheft: LF<n> mit dem Schluessel als Bezeichnung, nie ein vergebener Name
G11 Wind und Wasserdruck: ein gewaehlter Lastfall bleibt, wie er ist
G12 Masken Wind und Wasserdruck (offscreen): das Feld Lastfall ist leer, „Lasten
    erzeugen“ legt LF<n> mit der Bezeichnung an; Umbenennen und Loeschen eines
    Winds nehmen seine Stablasten mit (Merkmal statt Kommentar)

Die Referenzwerte stehen in tests/daten/erzeuger_c5dbb10/referenz.json
(erzeugt von tests/daten/erzeuger_c5dbb10/erzeugen.py auf c5dbb10).

Aufruf:  python -m tests.test_namen_erzeuger
"""
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

import numpy as np  # noqa: E402

from statik3d import examples_lib, solver, wind as wm, wasserdruck as wdm  # noqa: E402
from statik3d import combinations as cb  # noqa: E402
from statik3d.model import (Model, Material, ShellProp, Flaeche, Member, Section, NameVergeben,  # noqa: E402
                            Linienlast, Combination)
from statik3d.wind import Wind  # noqa: E402
from statik3d.wasserdruck import Wasserdruck  # noqa: E402
from statik3d.bridges import lastenheft as lh  # noqa: E402
from statik3d.bridges.din19704 import Regelwerk, GENERATOR as DIN  # noqa: E402
from statik3d.bridges.positions import Stellung  # noqa: E402

RESULTS = []
HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(HIER, "daten", "erzeuger_c5dbb10")
_MESS: dict = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Referenz: Messung der Beispiele auf c5dbb10
# --------------------------------------------------------------------------
def _erzeugen():
    spec = importlib.util.spec_from_file_location("erzeuger_erzeugen", os.path.join(DATEN, "erzeugen.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _referenz() -> dict:
    with open(os.path.join(DATEN, "referenz.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _inhalt(c) -> tuple:
    """Typ, Situation und Faktoren einer Kombination - ihr Inhalt ohne Namen."""
    return (c.typ, c.situation or "", tuple(sorted((k, round(float(v), 6)) for k, v in c.factors.items())))


def vergleiche(ist, soll, pfad: str = "", tol: float = 1e-12) -> tuple:
    """(Zahl der Abweichungen, groesste relative Abweichung, erste Abweichung)."""
    n, worst, erste = 0, 0.0, ""
    if isinstance(soll, dict):
        if not isinstance(ist, dict) or set(ist) != set(soll):
            fehlt = sorted(set(soll) - set(ist or {}))[:2]
            neu = sorted(set(ist or {}) - set(soll))[:2]
            return 1, 0.0, f"{pfad}: Schlüssel verschieden, fehlen {fehlt}, neu {neu}"
        for k in soll:
            a, b, c = vergleiche(ist[k], soll[k], f"{pfad}/{k}", tol)
            n += a
            worst = max(worst, b)
            erste = erste or c
    elif isinstance(soll, list):
        if not isinstance(ist, list) or len(ist) != len(soll):
            return 1, 0.0, f"{pfad}: Länge verschieden"
        for i, (u, v) in enumerate(zip(ist, soll)):
            a, b, c = vergleiche(u, v, f"{pfad}[{i}]", tol)
            n += a
            worst = max(worst, b)
            erste = erste or c
    elif isinstance(soll, float):
        d = abs(float(ist) - soll) / max(abs(soll), 1e-300) if ist != soll else 0.0
        if d > tol:
            return 1, d, f"{pfad}: {ist!r} statt {soll!r}"
        return 0, d, ""
    elif ist != soll:
        return 1, 0.0, f"{pfad}: {ist!r} statt {soll!r}"
    return n, worst, erste


def _messen(name: str):
    """Beispiel *name* bauen und messen (einmal je Lauf)."""
    if name not in _MESS:
        erz = _erzeugen()
        m = examples_lib.build_example(name)
        got = erz.messen(m, erz.alt_namen(name, m), solver)
        _MESS[name] = (m, json.loads(json.dumps(got)))
    return _MESS[name]


# --------------------------------------------------------------------------
# G1: Generator auf der Halle
# --------------------------------------------------------------------------
ART_VORSILBE = {"ULS": "GZT", "ACC": "GZT außergew.", "SLS_CH": "GZG char.",
                "SLS_FR": "GZG häufig", "SLS_QP": "GZG quasi-ständig"}


def test_g1_generator_halle():
    m, got = _messen("hall")
    ks = list(m.combinations.values())
    check("G1 Halle: 72 Kombinationen", len(ks) == 72, str(len(ks)))
    check("G1 … heißen LK1…LK72 in der Reihenfolge der Erzeugung (vorher GZT1…GZT42, GZG43…GZG72)",
          [c.name for c in ks] == [f"LK{i}" for i in range(1, 73)], str([c.name for c in ks[:3]]))
    check("G1 … Nummer = Zahl im Namen, Art LK, vom Generator EN 1990 erzeugt und unberührt",
          all(c.nummer == int(c.name[2:]) and c.art == "LK" and c.erzeugt == "EN 1990" and c.unberuehrt("EN 1990")
              for c in ks))
    typen = Counter(c.typ for c in ks)
    check("G1 … Typen wie vorher: 42 GZT, 21 GZG char., 7 häufig, 2 quasi-ständig",
          typen == Counter({"ULS": 42, "SLS_CH": 21, "SLS_FR": 7, "SLS_QP": 2}), str(dict(typen)))
    check("G1 … Typ je Nummer wie vorher (1…42 GZT, 43…72 GZG)",
          all((c.typ == "ULS") == (c.nummer <= 42) for c in ks))
    check("G1 … Bezeichnung beginnt mit Art des Typs und nennt die Leiteinwirkung",
          all(c.bezeichnung.startswith(ART_VORSILBE[c.typ])
              and (not c.leading or f"Leit {c.leading}" in c.bezeichnung) for c in ks),
          "; ".join(sorted({c.bezeichnung for c in ks})[:2]))
    check("G1 … Muster: „GZT, Leit LF3 (mit LF2, LF5), G günstig“ und „GZG char., Leit LF3“",
          any(re.fullmatch(r"GZT, Leit LF\d \(mit LF\d(, LF\d)*\), G günstig", c.bezeichnung) for c in ks)
          and any(re.fullmatch(r"GZG char., Leit LF\d", c.bezeichnung) for c in ks)
          and any(c.bezeichnung == "GZT, nur ständig" for c in ks),
          "; ".join(c.bezeichnung for c in ks[40:43]))
    check("G1 … jede Bezeichnung nur einmal", len({c.bezeichnung for c in ks}) == 72)
    check("G1 … die Leiteinwirkung steht mit dem Namen des Lastfalls da (LF<n>), nicht mit der Bezeichnung",
          all(re.fullmatch(r"LF\d", c.leading) for c in ks if c.leading))
    check("G1 … Lastfälle LF1…LF5 mit Bezeichnung (Eigengewicht, S, W_links, W_rechts, Kran)",
          [(n, lc.bezeichnung) for n, lc in m.load_cases.items()]
          == [("LF1", "Eigengewicht"), ("LF2", "S"), ("LF3", "W_links"), ("LF4", "W_rechts"), ("LF5", "Kran")])
    # die Rechnung: zahlengleich mit c5dbb10, jede Kombination ueber ihre Faktoren zugeordnet
    n, worst, erste = vergleiche(got, _referenz()["hall"])
    check("G1 Rechnung der Halle zahlengleich mit c5dbb10 (Lastfälle, 72 Kombinationen, 4 Umhüllende, "
          "EC3, Ermüdung)", n == 0, erste or f"größte Abweichung {worst:.2e}")
    check("G1 … darunter der Nachweis (EC3 η = 0,9654) und die Ermüdung (D = 0,0474)",
          abs(got["ec3"]["util_max"] - 0.96535789956772) < 1e-12
          and abs(got["ermuedung"]["Riegel"]["D"] - 0.047403898172854) < 1e-12)


# --------------------------------------------------------------------------
# G2: zweimal erzeugen, dazwischen umbenannt und von Hand geaendert
# --------------------------------------------------------------------------
def test_g2_zweimal_erzeugen():
    m = examples_lib.build_example("hall")
    alt_ids = {c.name: c for c in m.combinations.values()}
    # unveraendert: ein zweiter Lauf gibt dieselben Namen und Nummern zurueck
    cb.generate_combinations(m)
    check("G2 zweiter Lauf ohne Eingriff: dieselben 72 Kombinationen, dieselben Nummern und Inhalte",
          [c.name for c in m.combinations.values()] == [f"LK{i}" for i in range(1, 73)]
          and all(_inhalt(c) == _inhalt(alt_ids[c.name]) for c in m.combinations.values()))
    check("G2 … es sind neue Objekte (ersetzt, nicht stehengeblieben)",
          all(c is not alt_ids[c.name] for c in m.combinations.values()))
    # umbenennen (eine erzeugte) und von Hand aendern (eine andere)
    m.kombination_umbenennen("LK10", "Sonderfall Kran")
    umbenannt = m.combinations["Sonderfall Kran"]
    angefasst = m.combinations["LK20"]
    angefasst.factors["LF1"] = 1.1
    stand_u = (umbenannt.name, umbenannt.nummer, dict(umbenannt.factors))
    stand_a = (angefasst.name, angefasst.nummer, dict(angefasst.factors))
    uebrige = {c.name: c for c in m.combinations.values() if c not in (umbenannt, angefasst)}
    cb.generate_combinations(m)
    ks = list(m.combinations.values())
    nummern = [c.nummer for c in ks if c.art == "LK"]
    check("G2 die umbenannte Kombination bleibt (dasselbe Objekt, unverändert)",
          m.combinations.get("Sonderfall Kran") is umbenannt
          and (umbenannt.name, umbenannt.nummer, dict(umbenannt.factors)) == stand_u)
    check("G2 die von Hand geänderte bleibt (dasselbe Objekt, Faktor 1,1)",
          m.combinations.get("LK20") is angefasst and angefasst.factors["LF1"] == 1.1
          and (angefasst.name, angefasst.nummer, dict(angefasst.factors)) == stand_a)
    check("G2 die übrigen 70 sind ersetzt (neue Objekte) und haben ihre Nummer behalten",
          all(m.combinations[n] is not c and m.combinations[n].nummer == c.nummer
              for n, c in uebrige.items()), f"{len(uebrige)}")
    check("G2 zwei neue entstanden (für die Inhalte der beiden berührten): 74 Kombinationen, LK73 und LK74",
          len(ks) == 74 and "LK73" in m.combinations and "LK74" in m.combinations, str(len(ks)))
    check("G2 keine Nummer doppelt, jeder erzeugte Name ist LK<Nummer>, kein Namenskonflikt",
          len(nummern) == len(set(nummern)) and len(m.combinations) == len(ks)
          and all(c.name == f"LK{c.nummer}" for c in ks if c.erzeugt and c is not umbenannt)
          and not m.namenskollisionen() and not m.doppelte_nummern(),
          str(m.doppelte_nummern()[:1]))
    # ein Handobjekt gleichen Namens wird nie ueberschrieben
    m2 = examples_lib.build_example("hall")
    von_hand = Combination("LK7", {"LF1": 9.99}, "USER", "von Hand", nummer=7, art="LK", bezeichnung="von Hand")
    m2.combinations["LK7"] = von_hand            # an die Stelle der erzeugten LK7
    cb.generate_combinations(m2)
    check("G2 eine Handkombination LK7 bleibt, wie sie ist - der Generator überspringt die Nummer",
          m2.combinations["LK7"] is von_hand and von_hand.factors == {"LF1": 9.99}
          and sum(1 for c in m2.combinations.values() if c.nummer == 7) == 1
          and len(m2.combinations) == 73, str(len(m2.combinations)))


# --------------------------------------------------------------------------
# G3: alle Erzeuger in einem neuen Modell
# --------------------------------------------------------------------------
def _haut(nx: int = 6, nz: int = 20, b: float = 3.0, h: float = 5.0):
    """Senkrechte Haut in der y-z-Ebene bei x = 0 als Flaeche mit Schalen."""
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.012))
    ids = [[m.add_node(0.0, i * b / nx, k * h / nz) for k in range(nz + 1)] for i in range(nx + 1)]
    el = []
    for i in range(nx):
        for k in range(nz):
            el.append(m.add_element("shell4", [ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]],
                                    "S", "t"))
    m.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    for k in range(nz + 1):
        m.fix(ids[0][k], "all")
        m.fix(ids[nx][k], "all")
    return m, el


def _formen(m: Model) -> bool:
    namen = list(m.load_cases) + list(m.combinations)
    return all(re.fullmatch(r"LF\d+", n) for n in m.load_cases) \
        and all(re.fullmatch(r"(LK|EK)\d+", n) for n in m.combinations) and len(set(namen)) == len(namen)


def test_g3_alle_erzeuger_im_neuen_modell():
    m, _el = _haut()
    vorher = m.check()
    log: list = []
    n_lf = lh.lastfaelle_anlegen(m, ["G", "W_S", "W", "Q_BEW"], log=log)
    rw = Regelwerk()
    wd = Wasserdruck("Unter", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                     unterstroemt=True, spalt=0.5, cp_dyn=0.2)
    kw_w = wdm.lasten_erzeugen(m, wd)
    w = Wind("W1", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"])
    kw_wind = wm.lasten_erzeugen(m, w)
    n_din = rw.kombinationen(m, log=log)       # nach allen Lastfaellen, die Erzeuger anlegen
    n_en = cb.generate_combinations(m)
    check("G3 Lastenheft: Lastfälle LF2…LF5 mit dem Schlüssel als Bezeichnung",
          n_lf == ["LF2", "LF3", "LF4", "LF5"]
          and [m.load_cases[n].bezeichnung for n in n_lf] == ["G", "W_S", "W", "Q_BEW"]
          and [m.load_cases[n].nummer for n in n_lf] == [2, 3, 4, 5], str(n_lf))
    check("G3 Wasserdruck: LF6 „Wasser Unter“ und LF7 „Wasser Unter dyn“",
          (wd.lastfall, wd.lastfall_dyn) == ("LF6", "LF7")
          and m.load_cases["LF6"].bezeichnung == "Wasser Unter"
          and m.load_cases["LF7"].bezeichnung == "Wasser Unter dyn"
          and (m.load_cases["LF6"].nummer, m.load_cases["LF7"].nummer) == (6, 7),
          f"{wd.lastfall}, {wd.lastfall_dyn}")
    check("G3 Wind: LF8 „Wind W1“", w.lastfall == "LF8" and m.load_cases["LF8"].bezeichnung == "Wind W1"
          and m.load_cases["LF8"].nummer == 8 and kw_wind["lastfall_nr"] == 8 and kw_w["lastfall_nr"] == 6,
          w.lastfall)
    check("G3 DIN 19704: LK<n> mit Bezeichnung „DIN 19704 Klasse <k>, Leit LF<n>“, Typ ULS, Art LK",
          n_din and all(re.fullmatch(r"LK\d+", n) for n in n_din)
          and all(re.fullmatch(r"DIN 19704 Klasse [123](, Leit LF\d+|, nur ständig)", m.combinations[n].bezeichnung)
                  and m.combinations[n].typ == "ULS" and m.combinations[n].art == "LK"
                  and m.combinations[n].erzeugt == DIN for n in n_din), str(n_din[:3]))
    check("G3 EN 1990 danach: LK-Nummern hinter denen von DIN 19704, keine doppelt",
          n_en and min(c.nummer for c in n_en) > max(m.combinations[n].nummer for n in n_din)
          and not m.doppelte_nummern(), f"{len(n_din)} DIN + {len(n_en)} EN 1990")
    check("G3 nur LF<n> und LK<n>, keine Namenskollision, keine doppelte Nummer, jede Bezeichnung gesetzt",
          _formen(m) and not m.namenskollisionen() and not m.doppelte_nummern()
          and all(lc.bezeichnung for n, lc in m.load_cases.items() if n != "LF1")
          and all(c.bezeichnung for c in m.combinations.values()))
    neu = [z for z in m.check() if z not in vorher]
    check("G3 check() meldet nichts Neues", not neu, "; ".join(neu[:2]))
    # eine Wiederholung aller Erzeuger legt nichts doppelt an
    n_lf0, n_k0 = len(m.load_cases), len(m.combinations)
    rw.kombinationen(m)
    cb.generate_combinations(m)
    wdm.lasten_erzeugen(m, wd)
    wm.lasten_erzeugen(m, w)
    check("G3 jeder Erzeuger noch einmal: dieselben Lastfälle und Kombinationen, dieselben Namen",
          (len(m.load_cases), len(m.combinations)) == (n_lf0, n_k0) and _formen(m)
          and not m.doppelte_nummern(), f"{len(m.load_cases)} LF, {len(m.combinations)} LK")


# --------------------------------------------------------------------------
# G4: Wind und Wasserdruck zweimal - nichts verdoppelt sich
# --------------------------------------------------------------------------
def _mast():
    m = Model("Mast")
    m.add_material(Material("S"))
    m.add_section(Section.pipe("CHS", 0.2, 0.006))
    ids = [m.add_node(0, 0, i * 1.0) for i in range(7)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(6)]
    m.members["Mast"] = Member("Mast", el)
    m.fix(ids[0], "all")
    return m


def _zahlen(m: Model, w: Wind) -> tuple:
    lc = m.load_cases[w.lastfall]
    geo = [b for b in lc.beam_loads if getattr(b, "_geo", False)]
    return (len(lc.linienlasten), len(geo), len(lc.beam_loads),
            round(float(sum(np.linalg.norm(np.asarray(b.q, float)) for b in geo)), 6),
            round(wm.kontrollsumme(m, w)["F_staebe"], 6))


def test_g4_wind_zweimal_am_mast():
    m = _mast()
    w = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    kw1 = wm.lasten_erzeugen(m, w)
    z1 = _zahlen(m, w)
    check("G4 Wind am Mast, erster Lauf: 1 Linienlast, 6 Elementlasten",
          z1[0] == 1 and z1[1] == 6, str(z1))
    kw2 = wm.lasten_erzeugen(m, w)
    z2 = _zahlen(m, w)
    check("G4 zweiter Lauf: wieder 1 Linienlast und 6 Elementlasten (auf 36f8d8f: 2 und 12)",
          z2[0] == 1 and z2[1] == 6, str(z2))
    check("G4 … die Summe der Lasten ist gleich (Kontrollsumme der Stäbe und Summe der q)",
          z1[2:] == z2[2:] and abs(kw2["kontrolle"]["F_staebe"] - kw1["kontrolle"]["F_staebe"]) < 1e-9, str(z2))
    lc = m.load_cases[w.lastfall]
    check("G4 … die Linienlast trägt ihr Merkmal („wind:W“), verteilt zu „6 Elementlasten“, der Kommentar bleibt (N05)",
          lc.linienlasten[0].erzeuger == "wind:W" and lc.linienlasten[0].verteilt == "6 Elementlasten",
          f"{lc.linienlasten[0].erzeuger!r}, {lc.linienlasten[0].verteilt!r}")
    # nach Speichern und Laden (Verteilen schreibt den Kommentar neu) und noch ein Lauf
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    w2 = m2.winde["W"]
    check("G4 nach Speichern und Laden: Merkmal bleibt, gleiche Zahlen",
          m2.load_cases[w2.lastfall].linienlasten[0].erzeuger == "wind:W" and _zahlen(m2, w2) == z1,
          str(_zahlen(m2, w2)))
    wm.lasten_erzeugen(m2, w2)
    check("G4 … und ein dritter Lauf nach dem Laden verdoppelt nichts", _zahlen(m2, w2) == z1, str(_zahlen(m2, w2)))
    # eine Last von Hand auf demselben Stab im selben Lastfall bleibt beim Aufraeumen
    m2.add_linienlast("Mast", (0.0, 500.0, 0.0), art="stab", case=w2.lastfall)
    m2.lasten_verteilen()
    wm.lasten_erzeugen(m2, w2)
    check("G4 eine Handlast auf demselben Stab im selben Lastfall bleibt, die erzeugte ersetzt",
          sorted(ll.erzeuger for ll in m2.load_cases[w2.lastfall].linienlasten) == ["", "wind:W"],
          str([ll.erzeuger for ll in m2.load_cases[w2.lastfall].linienlasten]))
    # Entfernen des ganzen Generierers
    entfernen = getattr(wm, "lasten_entfernen", None)
    if entfernen is not None:
        entfernen(m2, "W")
        m2.lasten_verteilen()
    lc2 = m2.load_cases[w2.lastfall]
    check("G4 lasten_entfernen nimmt die Stablasten des Winds mit und lässt die Handlast",
          entfernen is not None and [ll.erzeuger for ll in lc2.linienlasten] == [""] and len(lc2.linienlasten) == 1)
    # Datei von vor dem Merkmal: der Kommentar „Wind W: …“ gilt, solange er so dasteht
    m3 = _mast()
    w3 = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    wm.lasten_erzeugen(m3, w3)
    ll = m3.load_cases[w3.lastfall].linienlasten[0]
    ll.erzeuger = ""
    ll.kommentar = "Wind W: c_f = 0.80, b_ref = 0.200 m"
    wm.lasten_erzeugen(m3, w3)
    check("G4 alte Datei ohne Merkmal, Kommentar noch „Wind W: …“: wird ersetzt, nicht verdoppelt",
          len(m3.load_cases[w3.lastfall].linienlasten) == 1)
    # Serialisierung: das Merkmal steht nur in der Datei, wenn es gesetzt ist
    d_wind = m.to_dict()["load_cases"]
    d_leer = _mast()
    d_leer.add_linienlast("Mast", (1.0, 0.0, 0.0), art="stab")
    check("G4 Datei: „erzeuger“ nur bei der Wind-Linienlast, eine Handlast schreibt es nicht",
          any(l.get("erzeuger") == "wind:W" for lc_ in d_wind for l in lc_["linienlasten"])
          and all("erzeuger" not in l for lc_ in d_leer.to_dict()["load_cases"] for l in lc_["linienlasten"]))
    check("G4 Datei von vorher (ohne das Feld) lädt: Linienlast ohne Merkmal",
          Linienlast.__dataclass_fields__["erzeuger"].default == ""
          and Model.from_dict(json.loads(json.dumps(d_leer.to_dict()))).load_cases["LF1"].linienlasten[0].erzeuger == "")


def test_g4_wasserdruck_zweimal():
    m, _el = _haut()
    wd = Wasserdruck("Unter", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                     unterstroemt=True, spalt=0.5, cp_dyn=0.2)
    k1 = wdm.lasten_erzeugen(m, wd)
    z1 = [(len(lc.geometrielasten), len(lc.face_loads)) for lc in m.load_cases.values()]
    k2 = wdm.lasten_erzeugen(m, wd)
    z2 = [(len(lc.geometrielasten), len(lc.face_loads)) for lc in m.load_cases.values()]
    check("G4 Wasserdruck zweimal: gleiche Zahl Objekt- und Elementlasten in jedem Lastfall, gleiche Summe",
          z1 == z2 and abs(k2["kontrolle"]["F"][0] - k1["kontrolle"]["F"][0]) < 1e-9
          and len(m.load_cases) == 3, f"{z1} / {z2}")
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    wdm.lasten_erzeugen(m2, m2.wasserdruecke["Unter"])
    z3 = [(len(lc.geometrielasten), len(lc.face_loads)) for lc in m2.load_cases.values()]
    check("G4 … und nach Speichern und Laden", z3 == z1 and len(m2.load_cases) == 3, str(z3))


# --------------------------------------------------------------------------
# G5: alle eingebauten Beispiele
# --------------------------------------------------------------------------
def test_g5_beispiele():
    erz = _erzeugen()
    ref = _referenz()
    t0 = time.time()
    for name in erz.BEISPIELE:
        m, got = _messen(name)
        lfs, kos = list(m.load_cases.values()), list(m.combinations.values())
        check(f"G5 {name}: nur LF-/LK-/EK-Namen, Nummer = Zahl im Namen, jeder Lastfall mit Bezeichnung",
              all(re.fullmatch(r"LF\d+", lc.name) and lc.nummer == int(lc.name[2:]) and lc.bezeichnung for lc in lfs)
              and all(re.fullmatch(r"(LK|EK)\d+", c.name) and c.nummer == int(c.name[2:]) and c.art == c.name[:2]
                      for c in kos) and not m.namenskollisionen() and not m.doppelte_nummern(),
              str([(lc.name, lc.bezeichnung) for lc in lfs]))
        n, worst, erste = vergleiche(got, ref[name])
        check(f"G5 {name}: Rechnung zahlengleich mit c5dbb10 ({got['anzahl']['lastfaelle']} Lastfälle, "
              f"{got['anzahl']['kombinationen']} Kombinationen)", n == 0, erste or f"größte Abweichung {worst:.2e}")
    hall, gate = _MESS["hall"][0], _MESS["gate"][0]
    check("G5 Halle: Ermüdungslast Kranspiele auf LF5; Stauwand: Stauwechsel auf LF2",
          hall.fatigue_loads["Kranspiele"].case_max == "LF5" and gate.fatigue_loads["Stauwechsel"].case_max == "LF2")
    check("G5 Stauwand: LF1 Eigengewicht, LF2 Wasser, LF3 Wasser_Wellen; 23 Kombinationen LK1…LK23",
          [(n, lc.bezeichnung) for n, lc in gate.load_cases.items()]
          == [("LF1", "Eigengewicht"), ("LF2", "Wasser"), ("LF3", "Wasser_Wellen")]
          and list(gate.combinations) == [f"LK{i}" for i in range(1, 24)])
    check("G5 keines der eingebauten Beispiele hat Ergebniskombinationen (also auch keine EK<n>)",
          all(not c.ist_umhuellende and c.art == "LK" for k in ("hall", "gate") for c in _MESS[k][0].combinations.values()))
    print(f"    (alle Beispiele gemessen in {time.time() - t0:.0f} s)")


# --------------------------------------------------------------------------
# G6: Gesamtlauf
# --------------------------------------------------------------------------
def test_g6_in_run_all():
    from tests import run_all
    check("G6 diese Suite steht in tests.run_all.SUITES", "tests.test_namen_erzeuger" in run_all.SUITES)


# --------------------------------------------------------------------------
# G7: Fingerabdruck statt Name
# --------------------------------------------------------------------------
def _umstellen_wie_a2(m: Model, ab: int = 100) -> dict:
    """Jede erzeugte Kombination umbenennen und den Fingerabdruck neu setzen -
    so wie die Umstellung beim Laden (R2-A2) sie hinterlaesst."""
    karte = {}
    for i, c in enumerate(list(m.combinations.values())):
        if c.erzeugt:
            alt = c.name
            neu = f"LK{ab + i}"
            m.kombination_umbenennen(alt, neu)
            c.nummer = ab + i
            c.bezeichnung = c.bezeichnung or alt
            c.als_erzeugt(c.erzeugt)
            karte[alt] = neu
    return karte


def test_g7_fingerabdruck_statt_name():
    # EN 1990
    m = examples_lib.build_example("hall")
    karte = _umstellen_wie_a2(m)
    n0 = len(m.combinations)
    check("G7 Vorbereitung: alle 72 erzeugten Kombinationen umbenannt, Fingerabdruck erneuert",
          n0 == 72 and len(karte) == 72 and all(c.unberuehrt("EN 1990") for c in m.combinations.values()))
    cb.generate_combinations(m)
    check("G7 EN 1990: zweiter Lauf nach der Umbenennung bekommt keine Doppel (72, nicht 144)",
          len(m.combinations) == 72 and not m.namenskollisionen() and not m.doppelte_nummern(),
          str(len(m.combinations)))
    check("G7 … und hält die Nummern der Umgestellten (Inhalt gleich -> Nummer gleich)",
          sorted(c.nummer for c in m.combinations.values()) == list(range(100, 172)),
          str(sorted(c.nummer for c in m.combinations.values())[:3]))
    # DIN 19704
    m, _el = _haut()
    lh.lastfaelle_anlegen(m, ["G", "G_A", "W_S", "W_V", "W"])
    rw = Regelwerk()
    erste = rw.kombinationen(m)
    n1 = len(m.combinations)
    for i, name in enumerate(list(erste)):
        m.kombination_umbenennen(name, f"LK{200 + i}")
        c = m.combinations[f"LK{200 + i}"]
        c.nummer = 200 + i
        c.als_erzeugt(DIN)
    zweite = rw.kombinationen(m)
    check("G7 DIN 19704: erzeugte Kombinationen umbenannt (wie nach der Umstellung), zweiter Lauf: keine Doppel",
          n1 >= 5 and len(m.combinations) == n1 and len(zweite) == n1 and not m.doppelte_nummern(),
          f"{n1} -> {len(m.combinations)}")
    check("G7 … sie behalten ihre Nummern 200…", sorted(c.nummer for c in m.combinations.values())
          == list(range(200, 200 + n1)))
    # DIN 19704 und EN 1990 stoeren einander nicht
    cb.generate_combinations(m)
    k_din = [c for c in m.combinations.values() if c.erzeugt == DIN]
    k_en = [c for c in m.combinations.values() if c.erzeugt == "EN 1990"]
    rw.kombinationen(m)
    check("G7 DIN 19704 und EN 1990 ersetzen nur ihre eigenen",
          len(k_din) == n1 and len(k_en) > 0
          and len([c for c in m.combinations.values() if c.erzeugt == "EN 1990"]) == len(k_en)
          and len([c for c in m.combinations.values() if c.erzeugt == DIN]) == n1)
    # eine berührte DIN-Kombination bleibt
    c0 = next(c for c in m.combinations.values() if c.erzeugt == DIN)
    c0.bezeichnung = "vom Anwender umgetauft"
    rw.kombinationen(m)
    check("G7 eine angefasste DIN-Kombination gehört dem Anwender und bleibt (eine neue entsteht daneben)",
          c0.name in m.combinations and m.combinations[c0.name] is c0
          and len([c for c in m.combinations.values() if c.erzeugt == DIN]) == n1 + 1)
    # alte Datei ohne Fingerabdruck: „auto…“ mit GZT-Namen gilt, sonst nicht
    m = examples_lib.build_example("hall")
    ks = list(m.combinations.values())
    alt = ks[0]
    alt.erzeugt, alt.erzeugt_merkmal = "", ""
    m.kombination_umbenennen(alt.name, "GZT1")
    m.combinations["GZT1"].description = "auto: 6.10 nur staendig, G unguenstig"
    fremd = ks[1]
    fremd.erzeugt, fremd.erzeugt_merkmal = "", ""
    m.kombination_umbenennen(fremd.name, "Handlast")
    cb.generate_combinations(m)
    check("G7 ohne Fingerabdruck gilt „auto…“ nur mit GZT-Namen: GZT1 wird ersetzt, „Handlast“ bleibt",
          "GZT1" not in m.combinations and "Handlast" in m.combinations and len(m.combinations) == 73,
          str(len(m.combinations)))
    # Wind und Wasserdruck: der Lastfall wurde umbenannt (so wie die Umstellung es tut)
    m, _el = _haut()
    wd = Wasserdruck("Unter", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                     unterstroemt=True, spalt=0.5, cp_dyn=0.2)
    wdm.lasten_erzeugen(m, wd)
    w = Wind("W1", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"])
    wm.lasten_erzeugen(m, w)
    m.lastfall_umbenennen("LF2", "LF22")
    m.lastfall_umbenennen("LF4", "LF44")
    n_lf = len(m.load_cases)
    wdm.lasten_erzeugen(m, wd)
    wm.lasten_erzeugen(m, w)
    check("G7 Wasserdruck und Wind schreiben nach dem Umbenennen in ihren Lastfall (kein neuer entsteht)",
          len(m.load_cases) == n_lf and wd.lastfall == "LF22" and w.lastfall == "LF44"
          and len(m.load_cases["LF22"].geometrielasten) == 1 and len(m.load_cases["LF44"].geometrielasten) == 1,
          f"{len(m.load_cases)} Lastfälle, {wd.lastfall}, {w.lastfall}")


# --------------------------------------------------------------------------
# G8: Nummern halten, Verweise nie auf eine andere Kombination
# --------------------------------------------------------------------------
def test_g8_verweis_haelt_die_nummer():
    m = examples_lib.build_example("hall")
    ziel = next(c for c in m.combinations.values() if c.typ == "ULS" and c.leading)
    nm = ziel.name
    verweis = m.add_fatigue_load("Spiele10", nm, None, 1e5)
    check(f"G8 Vorbereitung: Ermüdungslast auf {nm} (GZT mit Leiteinwirkung)",
          ziel.typ == "ULS" and verweis.case_max == nm)
    vorher_check = [z for z in m.check() if "Spiele10" in z]
    m.design.gamma_Q = 1.4              # jede GZT-Kombination mit veraenderlicher Last bekommt neue Faktoren
    cb.generate_combinations(m)
    namen = {c.name: c for c in m.combinations.values()}
    meldungen = [z for z in m.check() if "Spiele10" in z]
    check(f"G8 nach der Änderung der Faktoren: {nm} ist weg und wird nicht an eine andere vergeben",
          nm not in namen and len({c.nummer for c in m.combinations.values()}) == len(m.combinations),
          str(sorted(int(n[2:]) for n in namen)[:12]))
    check("G8 … der Verweis zeigt ins Leere, und check() sagt es (FEHLER), statt still auf eine andere zu zeigen",
          not vorher_check and any(z.startswith("FEHLER") and nm in z for z in meldungen), str(meldungen[:1]))
    # eine Kombination mit demselben Inhalt behaelt Nummer und Verweis
    m2 = examples_lib.build_example("hall")
    k1 = m2.combinations["LK1"]                      # nur staendig - kein Faktor haengt an gamma_Q
    m2.add_fatigue_load("Spiele1", "LK1", None, 1e5)
    m2.design.gamma_Q = 1.4
    cb.generate_combinations(m2)
    check("G8 eine Kombination mit demselben Inhalt (LK1: nur ständig) behält ihre Nummer, der Verweis hält",
          m2.combinations["LK1"].factors == k1.factors and m2.combinations["LK1"].nummer == 1
          and not [z for z in m2.check() if "Spiele1" in z and z.startswith("FEHLER")])
    # neue Kombinationen fuellen die Luecken zuerst, dann geht es hinter der hoechsten weiter
    m3 = examples_lib.build_example("hall")
    m3.design.gamma_Q = 1.4
    cb.generate_combinations(m3)
    nr = sorted(c.nummer for c in m3.combinations.values())
    check("G8 ohne Verweis füllen neue Kombinationen die Lücken: Nummern 1…72 ohne Lücke",
          nr == list(range(1, 73)), str(nr[-3:]))


# --------------------------------------------------------------------------
# G9: Antrieb der Stellung
# --------------------------------------------------------------------------
def test_g9_antrieb():
    m = examples_lib.build_example("hall")
    vorher = list(m.load_cases)
    st = Stellung("S5", 30.0, faelle=["LF1", "LF2"], antrieb=(0, (0.0, 250e3, 0.0)))
    log: list = []
    k = st.modell(m, log)
    neu = [n for n in k.load_cases if n not in vorher]
    check("G9 Antrieb: ein neuer Lastfall LF6 (Nummer hinter der höchsten des Basismodells) „Antrieb S5“",
          neu == ["LF6"] and k.load_cases["LF6"].bezeichnung == "Antrieb S5" and k.load_cases["LF6"].nummer == 6
          and set(k.load_cases) == {"LF1", "LF2", "LF6"}, str(list(k.load_cases)))
    check("G9 … nur in der Rechenkopie: das Basismodell hat ihn nicht",
          list(m.load_cases) == vorher and "LF6" not in m.load_cases)
    check("G9 … das Moment liegt als Knotenlast darin, und jede Kombination mit positiven Faktoren nennt ihn",
          abs(float(k.load_cases["LF6"].nodal_loads[0].F[4]) - 250e3) < 1e-6
          and k.combinations and all("LF6" in c.factors for c in k.combinations.values()
                                     if any(f > 0 for f in c.factors.values())))
    check("G9 … und die Kopie hat weder Namenskollision noch doppelte Nummer",
          not k.namenskollisionen() and not k.doppelte_nummern())


# --------------------------------------------------------------------------
# G10: Lastenheft
# --------------------------------------------------------------------------
def test_g10_lastenheft():
    m = Model("L")
    log: list = []
    n1 = lh.lastfaelle_anlegen(m, log=log)
    check("G10 Standard-Lastfälle: LF2…LF10 mit dem Schlüssel als Bezeichnung, Nummer = Zahl im Namen",
          n1 == [f"LF{i}" for i in range(2, 11)]
          and [m.load_cases[n].bezeichnung for n in n1] == lh.STANDARD
          and all(m.load_cases[n].nummer == int(n[2:]) for n in n1), str(n1))
    check("G10 … Einwirkungsart = Schlüssel, Beschreibung = Einwirkung (unverändert), Protokoll nennt „LF5 W_V“",
          all(m.load_cases[n].category == m.load_cases[n].bezeichnung for n in n1)
          and any("LF4 W_S" in z and "LF5 W_V" in z for z in log), log[-1][:70])
    n2 = lh.lastfaelle_anlegen(m, ["G", "EIS"])
    check("G10 noch einmal: weiter LF11, LF12 - nichts überschrieben, keine Zahl an einen Namen gehängt",
          n2 == ["LF11", "LF12"] and len(m.load_cases) == 12 and _formen(m) and not m.doppelte_nummern(), str(n2))
    try:
        lh.lastfaelle_anlegen(m, ["G"], start_nr=5)
        check("G10 eine belegte erste Nummer weist ab", False)
    except NameVergeben as ex:
        check("G10 eine belegte erste Nummer weist ab, bevor etwas angelegt ist",
              len(m.load_cases) == 12 and "LF5" in str(ex), str(ex)[:70])
    n3 = lh.lastfaelle_anlegen(m, ["G", "Q"], start_nr=20)
    check("G10 eine freie erste Nummer: LF20, LF21", n3 == ["LF20", "LF21"]
          and [m.load_cases[n].nummer for n in n3] == [20, 21], str(n3))
    # der Lastfall der Kombination mit dem Namen LF13 steht im Weg
    m4 = Model("K")
    m4.add_combination("LF2", {"LF1": 1.0})
    try:
        lh.lastfaelle_anlegen(m4, ["G"], start_nr=2)
        check("G10 eine Kombination „LF2“ belegt die Nummer 2", False)
    except NameVergeben:
        check("G10 eine Kombination „LF2“ belegt die Nummer 2 - die Anlage mit Nr. 2 weist ab", True)


# --------------------------------------------------------------------------
# G11: ein gewaehlter Lastfall bleibt, wie er ist
# --------------------------------------------------------------------------
def test_g11_gewaehlter_lastfall():
    m, _el = _haut()
    m.add_load_case("LF2", "W", "vorhanden", activate=False, nummer=2, bezeichnung="Meine Last")
    w = Wind("W1", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"], lastfall="LF2")
    wm.lasten_erzeugen(m, w)
    lc = m.load_cases["LF2"]
    check("G11 Wind in einen vorhandenen Lastfall: Name, Bezeichnung und Nummer bleiben, die Last liegt darin",
          w.lastfall == "LF2" and lc.bezeichnung == "Meine Last" and lc.nummer == 2 and len(lc.geometrielasten) == 1
          and len(m.load_cases) == 2, f"{lc.bezeichnung!r}, {len(m.load_cases)}")
    w2 = Wind("W2", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"], lastfall="Windlast")
    wm.lasten_erzeugen(m, w2)
    check("G11 ein gewählter neuer Name („Windlast“) bleibt, wie er ist - ohne erfundene Bezeichnung",
          "Windlast" in m.load_cases and m.load_cases["Windlast"].bezeichnung == ""
          and m.load_cases["Windlast"].nummer == 3, str(list(m.load_cases)))
    w3 = Wind("W3", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"], lastfall_nr=7)
    wm.lasten_erzeugen(m, w3)
    check("G11 eine eingetragene Nummer (7) ohne Namen: neuer Lastfall LF7 „Wind W3“",
          w3.lastfall == "LF7" and m.load_cases["LF7"].nummer == 7 and m.load_cases["LF7"].bezeichnung == "Wind W3",
          w3.lastfall)
    w4 = Wind("W4", zone=2, profil="Binnenland", richtung=[1, 0, 0], flaechen=["Haut"], lastfall_nr=2)
    vor = (len(m.load_cases), len(m.load_cases["LF2"].geometrielasten))
    try:
        wm.lasten_erzeugen(m, w4)
        check("G11 eine eingetragene Nummer, die ein Lastfall hat (2), weist ab - nichts wird hineingeschrieben", False)
    except NameVergeben as ex:
        check("G11 eine eingetragene Nummer, die ein Lastfall hat (2), weist ab - nichts wird hineingeschrieben",
              vor == (len(m.load_cases), len(m.load_cases["LF2"].geometrielasten)) and "Wind W4" in str(ex),
              str(ex)[:80])
    wd = Wasserdruck("X", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0], unterstroemt=True,
                     spalt=0.5, cp_dyn=0.2, lastfall_nr=20)
    wdm.lasten_erzeugen(m, wd)
    check("G11 Wasserdruck mit eingetragener Nummer 20: LF20 und LF21 (dyn)",
          (wd.lastfall, wd.lastfall_dyn) == ("LF20", "LF21")
          and m.load_cases["LF21"].bezeichnung == "Wasser X dyn", f"{wd.lastfall}, {wd.lastfall_dyn}")


# --------------------------------------------------------------------------
# G12: Masken und Loeschen ueber die Oberflaeche (offscreen)
# --------------------------------------------------------------------------
_FENSTER: dict = {}


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


def _setzen(w, app, m) -> None:
    """Das Modell ins Fenster setzen; eine abgewiesene Maske behaelt ihre Aenderungen
    (Leiste „Übernehmen | Verwerfen“) - verwerfen."""
    from PySide6 import QtWidgets
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        for b in leiste.findChildren(QtWidgets.QPushButton):
            if b.text() == "Verwerfen":
                b.click()
                break
    w.maskenrand.schliessen()
    app.processEvents()
    w._modell_setzen(m)
    app.processEvents()


def test_g12_masken_und_loeschen():
    from tests.meldungen import abfangen
    w, app = _fenster()
    # Wasserdruck: neue Maske, Feld Lastfall leer, Nummer = naechste freie
    m, _el = _haut()
    _setzen(w, app, m)
    w.sel_flaechen = ["Haut"]
    w._baum_geklickt("wasserdruck_neu", "+")
    app.processEvents()
    mk = w.maskenrand.maske
    nr0 = int(mk.werte()["fall_nr"])
    check("G12 Wasserdruck-Maske: das Feld Lastfall ist leer, die Nummer ist die nächste freie (2)",
          mk.werte()["fall"] == "" and nr0 == 2, f"{mk.werte()['fall']!r}, Nr. {nr0}")
    mk.setzen("verfahren", w.WASSERVERFAHREN[1])
    mk.setzen("h_ow", 4.0)
    mk.setzen("richtung", "global x")
    mk.setzen("absenkung", False)
    fehler: list = []
    abf = abfangen(w, fehler)
    mk.anwenden()
    app.processEvents()
    abf.zurueck()
    m = w.model
    wd = m.wasserdruecke.get("W1")
    check("G12 … „Lasten erzeugen“ legt LF2 mit der Bezeichnung „Wasser W1“ an (bis R2-C1 „Wasser W1“)",
          wd is not None and wd.lastfall == "LF2" and m.load_cases["LF2"].bezeichnung == "Wasser W1"
          and m.load_cases["LF2"].nummer == 2 and not fehler, f"{wd and wd.lastfall}, {fehler[:1]}")
    # Wind: neue Maske auf einer Flaeche
    m, _el = _haut()
    _setzen(w, app, m)
    w.sel_flaechen = ["Haut"]
    w._baum_geklickt("wind_neu", "+")
    app.processEvents()
    mk = w.maskenrand.maske
    check("G12 Wind-Maske: das Feld Lastfall ist leer, die Nummer ist die nächste freie (2)",
          mk.werte()["fall"] == "" and int(mk.werte()["fall_nr"]) == 2,
          f"{mk.werte()['fall']!r}, Nr. {mk.werte()['fall_nr']}")
    mk.setzen("zone", "Zone 2 (v_b,0 = 25 m/s)")
    mk.setzen("profil", "Binnenland")
    mk.setzen("richtung", "+x")
    fehler = []
    abf = abfangen(w, fehler)
    mk.anwenden()
    app.processEvents()
    abf.zurueck()
    m = w.model
    wi = m.winde.get("Wind1")
    check("G12 … „Lasten erzeugen“ legt LF2 mit der Bezeichnung „Wind Wind1“ an",
          wi is not None and wi.lastfall == "LF2" and m.load_cases["LF2"].bezeichnung == "Wind Wind1"
          and not fehler, f"{wi and wi.lastfall}, {fehler[:1]}")
    # Mast mit Staeben: Umbenennen und Loeschen nehmen die Stablasten mit
    m = _mast()
    wm.lasten_erzeugen(m, Wind("W1", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    _setzen(w, app, m)
    w.maske_wind("W1")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("name", "W2")
    fehler = []
    abf = abfangen(w, fehler)
    mk.anwenden()
    app.processEvents()
    abf.zurueck()
    m = w.model
    marken = [ll.erzeuger for lc in m.load_cases.values() for ll in lc.linienlasten]
    check("G12 Wind in der Maske umbenannt (W1 -> W2): nur der neue Wind, seine Stablast einmal (auf 36f8d8f blieb die alte)",
          list(m.winde) == ["W2"] and marken == ["wind:W2"] and not fehler, f"{list(m.winde)}, {marken}, {fehler[:1]}")
    w._baum_loeschen("wind", "W2")
    app.processEvents()
    m = w.model
    ueber = [(lc.name, len(lc.linienlasten), sum(1 for b in lc.beam_loads if getattr(b, "_geo", False)))
             for lc in m.load_cases.values()]
    check("G12 Wind im Modellbaum gelöscht: seine Streckenlasten und Elementlasten sind weg",
          not m.winde and all(n == 0 and g == 0 for _a, n, g in ueber), str(ueber))
    w.undo()
    app.processEvents()
    m = w.model
    check("G12 Rückgängig holt den Wind samt seiner Stablast zurück",
          "W2" in m.winde and sum(len(lc.linienlasten) for lc in m.load_cases.values()) == 1)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1500, exit=True)
    for t in (test_g1_generator_halle, test_g2_zweimal_erzeugen, test_g3_alle_erzeuger_im_neuen_modell,
              test_g4_wind_zweimal_am_mast, test_g4_wasserdruck_zweimal, test_g5_beispiele,
              test_g6_in_run_all, test_g7_fingerabdruck_statt_name, test_g8_verweis_haelt_die_nummer,
              test_g9_antrieb, test_g10_lastenheft, test_g11_gewaehlter_lastfall,
              test_g12_masken_und_loeschen):
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
    code = main()
    sys.stdout.flush()
    os._exit(code)
