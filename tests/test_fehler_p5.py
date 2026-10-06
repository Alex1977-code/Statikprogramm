"""
Fehlerliste vom 06.10.2026, Paket P5: Verweise beim Umbenennen und Loeschen.

* F09 - Wer einen Stab umbenennt, verlor Stellung, Schweissnaht und Wind (dazu
  Layer, Subsystem und Vorspannung): sie nannten weiter den alten Namen.
* F10 - Wer eine Kontaktbedingung umbenennt, verlor das Uebermass; ein
  Uebermass ohne Bedingung meldete die Modellpruefung nicht.
* F28 - Beim Loeschen von Stab, Lastfall oder Kombination blieben Verweise
  stehen und hingen sich an ein neues Objekt gleichen Namens.
* F29 - Eine geloeschte Ermuedungslast blieb im Anschlussnachweis
  (``Joint.ermuedung``) stehen.

Je Art gibt es eine zentrale Funktion im Modell (``stab_umbenennen``,
``stab_loeschen``, ``kontaktbedingung_umbenennen``,
``kontaktbedingung_loeschen``, ``kombination_loeschen``,
``ermuedungslast_umbenennen``, ``ermuedungslast_loeschen``, dazu
``remove_load_case``), und alle Wege der Oberflaeche und des Browsers rufen
sie. Beim Loeschen geht ein Verweis mit oder das Loeschen wird mit Grund
abgewiesen - je Verweisart entschieden wie bei den Knoten (PR #20).

Jede Pruefung ausser den als „Kontrolle“ benannten schlug auf 60fe253 fehl.

Aufruf:  python -m tests.test_fehler_p5
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_p5_"), "einstellungen.json")

from statik3d.model import (Model, Material, Section, Berichtseintrag, FatigueLoad,  # noqa: E402
                            Joint, Layer, Subsystem, Kopplung, Volumenkoerper)

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _rufen(f, *a, **k):
    """Eine Modellfunktion rufen, die es auf dem alten Stand nicht gibt - dann
    ist das Ergebnis die Ausnahme (die Pruefung schlaegt fehl, die Suite laeuft
    weiter)."""
    try:
        return f(*a, **k)
    except Exception as ex:          # noqa: BLE001
        return ex


def _basis() -> Model:
    """Zwei Staebe S1 (E0) und S2 (E1) auf drei Knoten, gelagert, mit LF1."""
    m = Model("P5")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    for x in (0, 4, 8):
        m.add_node(x, 0, 0)
    e0 = m.add_element("beam", [0, 1], "S355", "HEB 200")
    e1 = m.add_element("beam", [1, 2], "S355", "HEB 200")
    m.add_member("S1", [e0])
    m.add_member("S2", [e1])
    m.support(0, "all")
    m.support(2, [1, 2, 3])
    m.load_node(1, Fz=-10e3)
    return m


def _stab_verweise(m: Model, name="S2", vg=True, le=True) -> Model:
    """Jeder Verweis, der einen Stab beim Namen nennt."""
    from statik3d.schweissnaehte import Schweissnaht
    from statik3d.wind import Wind
    from statik3d.bridges.positions import Stellung
    if vg:
        m.add_verformungsgrenze("VG1", art="stab", stab=name, wert=300.0)
    if le:
        m.add_lasteinleitung("LE1", 1, stab=name)
    m.schweissnaehte["N1"] = Schweissnaht("N1", staebe=[name, "S1"])
    m.winde["W"] = Wind("W", staebe=[name])
    m.stellungen.append(Stellung("St", 0.0, "x", staebe_aus=[name], faelle=list(m.load_cases)))
    m.layer["L1"] = Layer("L1", staebe=[name])
    m.subsysteme["T1"] = Subsystem("T1", staebe=[name])
    m.add_linienlast(name, [0, 0, -5e3], art="stab")
    m.add_vorspannung(name, 50e3, art="stab")
    return m


def _stabnamen(m: Model, name: str) -> dict:
    """Wo der Name *name* als Stab steht."""
    lc = m.case("LF1")
    return {"Verformungsgrenze": [k for k, x in m.verformungsgrenzen.items() if x.stab == name],
            "Lasteinleitung": [k for k, x in m.lasteinleitungen.items() if x.stab == name],
            "Schweißnaht": [k for k, x in m.schweissnaehte.items() if name in x.staebe],
            "Wind": [k for k, x in m.winde.items() if name in x.staebe],
            "Stellung": [s.name for s in m.stellungen if name in s.staebe_aus],
            "Layer": [k for k, x in m.layer.items() if name in x.staebe],
            "Subsystem": [k for k, x in m.subsysteme.items() if name in x.staebe],
            "Linienlast": [i for i, ll in enumerate(lc.linienlasten) if ll.art == "stab" and ll.ziel == name],
            "Vorspannung": [i for i, v in enumerate(lc.vorspannungen) if v.art == "stab" and v.ziel == name]}


# --------------------------------------------------------------------------
# F09 - Stab umbenennen
# --------------------------------------------------------------------------
def test_f09_stab_umbenennen():
    m = _stab_verweise(_basis())
    # ein dritter Stab hinter S2: an ihm zeigt sich, ob S2 seinen Platz behaelt
    m.add_node(12, 0, 0)
    m.add_member("S3", [m.add_element("beam", [2, 3], "S355", "HEB 200")])
    aus = _rufen(m.stab_umbenennen, "S2", "Riegel")
    alt, neu = _stabnamen(m, "S2"), _stabnamen(m, "Riegel")
    check("F09 Modell: kein Verweis nennt nach dem Umbenennen noch „S2“",
          not any(alt.values()), str({k: v for k, v in alt.items() if v}))
    check("F09 Modell: jeder Verweis nennt „Riegel“ (Verformung, Lasteinleitung, Naht, Wind, Stellung, "
          "Layer, Subsystem, Linienlast, Vorspannung)",
          all(neu.values()), str({k: v for k, v in neu.items() if not v}))
    check("F09 Modell: die Naht behält ihren zweiten Stab S1", m.schweissnaehte["N1"].staebe == ["Riegel", "S1"],
          str(m.schweissnaehte["N1"].staebe))
    check("F09 Modell: Rückgabe nennt, was mitging (Naht, Wind, Stellung)",
          isinstance(aus, list) and any("N1" in z for z in aus) and any("W" in z for z in aus)
          and any("St" in z for z in aus), str(aus))
    check("F09 Modell: der Stab bleibt an seinem Platz in der Reihenfolge",
          list(m.members) == ["S1", "Riegel", "S3"], str(list(m.members)))
    st = m.stellungen[0]
    els = st.deaktivierte_elemente(m)
    check("F09 Wirkung: die Stellung schaltet den umbenannten Stab weiter ab (Element 1)", els == [1], str(els))
    # Ein vorhandener Name wird abgewiesen, ohne etwas zu aendern (Kontrolle)
    vorher, reihe = _stabnamen(m, "Riegel"), list(m.members)
    try:
        m.stab_umbenennen("Riegel", "S1")
        abgewiesen = False
    except ValueError:
        abgewiesen = True
    check("F09 Kontrolle: vorhandener Name abgewiesen, nichts geändert",
          abgewiesen and _stabnamen(m, "Riegel") == vorher and list(m.members) == reihe, "")


# --------------------------------------------------------------------------
# F10 - Kontaktbedingung umbenennen, Uebermass ohne Bedingung
# --------------------------------------------------------------------------
def _fuge(m: Model, name="Fuge") -> Model:
    m.add_kontaktbedingung(name)
    m.add_uebermass(name, 30e-6)
    m.subsysteme["T1"] = Subsystem("T1", kontakte=[name])
    # was das Ausfuehren der Fuge im Netz anlegt (fugen.kontaktfuge_ausfuehren)
    m.add_contact_pair(name, [1], master_faces=[[0, 1, 2]])
    m.add_gap_element(0, 1, group=name)
    m.kopplungen.append(Kopplung(0, 1, [[1, 0, 0]], [1e9], name))
    m.getrennte_knoten[name] = [[1, 2]]
    return m


def _kontaktnamen(m: Model, name: str) -> dict:
    lc = m.case("LF1")
    return {"Übermaß": [u.ziel for u in lc.uebermasse if u.ziel == name],
            "Subsystem": [k for k, s in m.subsysteme.items() if name in s.kontakte],
            "Kontaktpaar": [c.name for c in m.contact_pairs if c.name == name],
            "Spaltelement": [g.group for g in m.gap_elements if g.group == name],
            "Kopplung": [k.gruppe for k in m.kopplungen if k.gruppe == name],
            "getrennte Knoten": [k for k in m.getrennte_knoten if k == name]}


def test_f10_kontaktbedingung_umbenennen():
    m = _fuge(_basis())
    m.add_kontaktbedingung("Zweite")
    aus = _rufen(getattr(m, "kontaktbedingung_umbenennen", None) or (lambda *a: None), "Fuge", "Fuge neu")
    alt, neu = _kontaktnamen(m, "Fuge"), _kontaktnamen(m, "Fuge neu")
    check("F10 Modell: kontaktbedingung_umbenennen benennt die Bedingung um, an ihrem Platz",
          list(m.kontaktbedingungen) == ["Fuge neu", "Zweite"]
          and m.kontaktbedingungen.get("Fuge neu") is not None
          and m.kontaktbedingungen["Fuge neu"].name == "Fuge neu", str(list(m.kontaktbedingungen)))
    check("F10 Modell: kein Verweis nennt danach noch „Fuge“", not any(alt.values()),
          str({k: v for k, v in alt.items() if v}))
    check("F10 Modell: Übermaß, Subsystem, Kontaktpaar, Spaltelement, Kopplung und getrennte Knoten folgen",
          all(neu.values()), str({k: v for k, v in neu.items() if not v}))
    check("F10 Modell: Rückgabe nennt das Übermaß", isinstance(aus, list) and any("Übermaß" in z for z in aus),
          str(aus))


def test_f10_pruefung_uebermass_ohne_bedingung():
    m = _basis()
    m.add_kontaktbedingung("Fuge")
    m.add_uebermass("Fuge", 30e-6)
    m.add_contact_pair("Paar", [1], master_faces=[[0, 1, 2]])
    m.add_uebermass("Paar", 20e-6)
    ohne = [z for z in m.check() if "bermaß" in z]
    check("F10 Kontrolle: Übermaß auf Bedingung und auf Kontaktpaar - keine Zeile", not ohne, str(ohne))
    m.case("LF1").uebermasse[0].ziel = "Weg"
    zeilen = [z for z in m.check() if "bermaß" in z]
    check("F10 Prüfung: ein Übermaß ohne Bedingung und ohne Kontaktpaar ist ein FEHLER",
          len(zeilen) == 1 and zeilen[0].startswith("FEHLER") and "Weg" in zeilen[0], str(zeilen))


# --------------------------------------------------------------------------
# F28 - Stab, Lastfall, Kombination loeschen
# --------------------------------------------------------------------------
def test_f28_stab_loeschen():
    m = _stab_verweise(_basis())
    grund = m.stab_loeschen("S2")
    check("F28 Stab: eine Verformungsgrenze und eine Lasteinleitung sperren das Löschen, mit Grund",
          "S2" in m.members and "VG1" in str(grund) and "LE1" in str(grund), str(grund))
    check("F28 Stab: abgewiesen heißt unverändert (Naht, Wind, Stellung behalten S2)",
          all(_stabnamen(m, "S2").values()), str({k: v for k, v in _stabnamen(m, "S2").items() if not v}))
    del m.verformungsgrenzen["VG1"]
    del m.lasteinleitungen["LE1"]
    zeilen = []
    grund = m.stab_loeschen("S2", protokoll=zeilen)
    rest = _stabnamen(m, "S2")
    check("F28 Stab: ohne Nachweise gelöscht, und kein Verweis nennt S2 mehr",
          grund == "" and "S2" not in m.members and not any(rest.values()),
          f"{grund!r} {[k for k, v in rest.items() if v]}")
    check("F28 Stab: die Naht behält S1", m.schweissnaehte["N1"].staebe == ["S1"], str(m.schweissnaehte["N1"].staebe))
    check("F28 Stab: das Protokoll nennt Naht, Wind, Layer, Subsystem und Vorspannung",
          all(any(w in z for z in zeilen) for w in ("N1", "Wind", "L1", "T1", "Vorspannung")), str(zeilen))
    e2 = m.add_element("beam", [0, 2], "S355", "HEB 200")
    m.add_member("S2", [e2])
    erbt = _stabnamen(m, "S2")
    check("F28 Stab: ein neuer Stab „S2“ erbt nichts", not any(erbt.values()),
          str({k: v for k, v in erbt.items() if v}))
    # Eine Ersatznaht ohne weiteren Stab gaelte danach fuer alle Staebe
    from statik3d.schweissnaehte import Schweissnaht
    m2 = _basis()
    m2.schweissnaehte["E"] = Schweissnaht("E", aequivalent=True, staebe=["S2"])
    grund = m2.stab_loeschen("S2")
    check("F28 Stab: der letzte Stab einer Ersatznaht wird nicht gelöscht (leer hieße „alle Stäbe“)",
          "S2" in m2.members and "Ersatznaht" in str(grund) and m2.schweissnaehte["E"].staebe == ["S2"],
          str(grund))


def test_f28_lastfall_loeschen():
    from statik3d.wind import Wind
    from statik3d.wasserdruck import Wasserdruck
    m = _basis()
    m.add_load_case("LF2", "Q", nummer=2)
    m.add_load_case("LF3", "Q", nummer=3)
    m.winde["W1"] = Wind("W1", lastfall="LF2", lastfall_nr=2)
    m.wasserdruecke["WD"] = Wasserdruck("WD", lastfall="LF2", lastfall_dyn="LF3")
    m.bericht.append(Berichtseintrag(name="Bild LF2", quelle="case:LF2"))
    m.bericht.append(Berichtseintrag(name="Bild LF1", quelle="case:LF1"))
    mit = m.remove_load_case("LF2")
    check("F28 Lastfall: der Wind verliert seinen gelöschten Lastfall (Name und Nummer)",
          m.winde["W1"].lastfall == "" and m.winde["W1"].lastfall_nr == 0,
          f"{m.winde['W1'].lastfall!r} {m.winde['W1'].lastfall_nr}")
    check("F28 Lastfall: der Wasserdruck verliert ihn, sein dynamischer Lastfall bleibt",
          m.wasserdruecke["WD"].lastfall == "" and m.wasserdruecke["WD"].lastfall_dyn == "LF3",
          f"{m.wasserdruecke['WD'].lastfall!r} {m.wasserdruecke['WD'].lastfall_dyn!r}")
    check("F28 Lastfall: das Berichtsbild des Lastfalls geht mit, das andere bleibt",
          [e.quelle for e in m.bericht] == ["case:LF1"], str([e.quelle for e in m.bericht]))
    check("F28 Lastfall: die Rückgabe nennt Wind, Wasserdruck und Berichtsbild",
          any("W1" in z for z in mit) and any("WD" in z for z in mit) and any("Bild LF2" in z for z in mit),
          str(mit))
    m.add_load_case("LF2", "S", nummer=2)
    check("F28 Lastfall: ein neuer LF2 erbt weder Wind noch Wasserdruck noch Bild",
          m.winde["W1"].lastfall != "LF2" and m.wasserdruecke["WD"].lastfall != "LF2"
          and not any(e.quelle == "case:LF2" for e in m.bericht), "")


def _kombi() -> Model:
    from statik3d.bridges.positions import Stellung
    m = _basis()
    m.add_load_case("LF2", "Q", nummer=2)
    m.add_combination("CO1", {"LF1": 1.35, "LF2": 1.5}, typ="FAT", nummer=1, art="LK")
    m.add_combination("CO2", {"LF1": 1.0}, typ="ULS", nummer=2, art="LK")
    m.add_combination("EK1", {}, typ="ULS", alternativen=[{"LF1": 1.35}, {"LF2": 1.5}], nummer=1, art="EK")
    m.fatigue_loads["F1"] = FatigueLoad("F1", "CO1", None)
    m.fatigue_loads["F2"] = FatigueLoad("F2", "", None, folge=["CO1", "LF2", "CO2"])
    m.fatigue_loads["F3"] = FatigueLoad("F3", "LF2", "LF1")
    m.stellungen.append(Stellung("St", 0.0, "x", faelle=["LF1", "LF2"], kombinationen=["CO1", "CO2"]))
    m.bericht.append(Berichtseintrag(name="Bild CO1", quelle="combo:CO1"))
    m.bericht.append(Berichtseintrag(name="Bild EK1", quelle="env:EK1"))
    m.bericht.append(Berichtseintrag(name="Bild CO2", quelle="combo:CO2"))
    m.joints["K1"] = Joint("K1", ermuedung=["F1", "F3"])
    return m


def test_f28_kombination_loeschen():
    m = _kombi()
    zeilen = []
    grund = _rufen(getattr(m, "kombination_loeschen", None) or (lambda *a, **k: None), "CO1", protokoll=zeilen)
    check("F28 Kombination: kombination_loeschen löscht CO1", grund == "" and "CO1" not in m.combinations,
          f"{grund!r} {list(m.combinations)}")
    check("F28 Kombination: die Ermüdungslast aus zwei Zuständen auf CO1 entfällt (wie beim Lastfall)",
          "F1" not in m.fatigue_loads, str(list(m.fatigue_loads)))
    check("F28 Kombination: ein Verlauf verliert das Glied CO1",
          m.fatigue_loads.get("F2") is not None and m.fatigue_loads["F2"].folge == ["LF2", "CO2"],
          str(getattr(m.fatigue_loads.get("F2"), "folge", None)))
    check("F28 Kombination: der Anschluss verliert die entfallene Ermüdungslast", m.joints["K1"].ermuedung == ["F3"],
          str(m.joints["K1"].ermuedung))
    check("F28 Kombination: Stellung.kombinationen und Berichtsbild combo:CO1 gehen mit",
          m.stellungen[0].kombinationen == ["CO2"]
          and [e.quelle for e in m.bericht] == ["env:EK1", "combo:CO2"],
          f"{m.stellungen[0].kombinationen} {[e.quelle for e in m.bericht]}")
    check("F28 Kombination: das Protokoll nennt Ermüdungslasten und Berichtsbild",
          any("F1" in z for z in zeilen) and any("F2" in z for z in zeilen) and any("Bild CO1" in z for z in zeilen),
          str(zeilen))
    check("F28 Kombination: CO1 ist weg, und die Prüfung meldet keinen FEHLER über CO1",
          "CO1" not in m.combinations and not [z for z in m.check() if "CO1" in z],
          str([z for z in m.check() if "CO1" in z]))
    m.add_combination("CO1", {"LF1": 3.0}, typ="FAT", nummer=1, art="LK")
    erbt = [n for n, f in m.fatigue_loads.items() if "CO1" in (f.case_max, f.case_min) or "CO1" in f.folge]
    check("F28 Kombination: eine neue CO1 erbt keine Ermüdungslast und kein Bild",
          not erbt and not any(e.quelle == "combo:CO1" for e in m.bericht), str(erbt))
    # Ergebniskombination: das Bild ihrer Umhuellenden geht mit
    m = _kombi()
    _rufen(getattr(m, "kombination_loeschen", None) or (lambda *a, **k: None), "EK1")
    check("F28 Kombination: eine gelöschte Ergebniskombination nimmt das Bild ihrer Umhüllenden mit",
          "EK1" not in m.combinations and [e.quelle for e in m.bericht] == ["combo:CO1", "combo:CO2"],
          str([e.quelle for e in m.bericht]))


# --------------------------------------------------------------------------
# F29 - Ermuedungslast loeschen und umbenennen
# --------------------------------------------------------------------------
def _ermuedung() -> Model:
    m = _basis()
    m.add_load_case("LF2", "Q", nummer=2)
    for n in ("E1", "E2", "E3"):
        m.fatigue_loads[n] = FatigueLoad(n, "LF2", "LF1")
    m.joints["K1"] = Joint("K1", ermuedung=["E1", "E2"])
    m.joints["K2"] = Joint("K2", ermuedung=["E1"])
    m.joints["K3"] = Joint("K3", ermuedung=[])
    return m


def test_f29_ermuedungslast():
    m = _ermuedung()
    zeilen = []
    grund = _rufen(getattr(m, "ermuedungslast_loeschen", None) or (lambda *a, **k: None), "E1", protokoll=zeilen)
    check("F29 Modell: ermuedungslast_loeschen löscht E1", grund == "" and "E1" not in m.fatigue_loads,
          f"{grund!r} {list(m.fatigue_loads)}")
    check("F29 Modell: E1 geht aus jedem Anschluss", [m.joints[k].ermuedung for k in ("K1", "K2", "K3")]
          == [["E2"], [], []], str([m.joints[k].ermuedung for k in ("K1", "K2", "K3")]))
    check("F29 Modell: das Protokoll sagt, dass K2 jetzt alle Ermüdungslasten nachweist (leer = alle)",
          any("K2" in z and "alle" in z and "E2" in z and "E3" in z for z in zeilen), str(zeilen))
    m.fatigue_loads["E1"] = FatigueLoad("E1", "LF1", None)
    check("F29 Modell: eine neue Last „E1“ geht nicht still in K1 ein", m.joints["K1"].ermuedung == ["E2"],
          str(m.joints["K1"].ermuedung))
    # Umbenennen: zentral im Modell, die Anschluesse folgen
    aus = _rufen(getattr(m, "ermuedungslast_umbenennen", None) or (lambda *a: None), "E2", "Kran")
    check("F29 Modell: ermuedungslast_umbenennen - an ihrem Platz, Anschluss folgt",
          list(m.fatigue_loads) == ["Kran", "E3", "E1"] and m.fatigue_loads["Kran"].name == "Kran"
          and m.joints["K1"].ermuedung == ["Kran"] and isinstance(aus, list) and any("K1" in z for z in aus),
          f"{list(m.fatigue_loads)} {m.joints['K1'].ermuedung} {aus}")
    # Ein Lastfall nimmt seine Ermuedungslasten mit - auch aus dem Anschluss
    m = _ermuedung()
    m.remove_load_case("LF2")
    check("F29 Lastfall: entfallen die Lasten mit LF2, gehen sie aus den Anschlüssen",
          not m.fatigue_loads and all(not j.ermuedung for j in m.joints.values()),
          str({k: j.ermuedung for k, j in m.joints.items()}))


def test_f29_anschlussnachweis():
    """Der Beleg der Fehlerliste (fl_a/t3/probe_a.py, o24_5) an der Halle: K1
    weist E1 und E2 nach; nach dem Loeschen von E1 und dem Neuanlegen einer
    Last „E1“ bleibt D des Anschlusses das von E2 allein."""
    from statik3d import examples_lib, solver
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose
    m = examples_lib.build_example("hall")
    e_kopf = m.members["Riegel"].elements[0]
    m.joints["K1"] = A.als_joint(propose("kopfplatte", m, e_kopf, end=0, N=-50e3, Vz=150e3, My=300e3), "K1")
    m.fatigue_loads["E1"] = FatigueLoad("E1", case_max="Kran", case_min="LF1", cycles=2e6)
    m.fatigue_loads["E2"] = FatigueLoad("E2", case_max="S", case_min="LF1", cycles=2e6)
    m.joints["K1"].ermuedung = ["E1", "E2"]
    an = solver.solve_all(m, design=True, fatigue=False)
    nur_e2 = m.copy()
    nur_e2.joints["K1"].ermuedung = ["E2"]
    del nur_e2.fatigue_loads["E1"]
    D_soll = A.check_joints(nur_e2, an).joints["K1"].D
    _rufen(getattr(m, "ermuedungslast_loeschen", None) or (lambda *a, **k: None), "E1")
    m.fatigue_loads["E1"] = FatigueLoad("E1", case_max="Kran", case_min=None, cycles=5e6)
    c = A.check_joints(m, an).joints["K1"]
    check("F29 Halle: nach Löschen und Neuanlegen von „E1“ ist D von K1 das von E2 allein, ohne Hinweis",
          abs(c.D - D_soll) <= 1e-12 * max(D_soll, 1e-30) and not [h for h in c.hinweise if "gibt es nicht" in h],
          f"D {c.D:.6g} soll {D_soll:.6g}")


# --------------------------------------------------------------------------
# Oberflaeche und Browser: alle Wege rufen die zentralen Funktionen
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


def _zeile(tabelle, text) -> int:
    for r in range(tabelle.rowCount()):
        it = tabelle.item(r, 0)
        if it is not None and it.text() == text:
            return r
    return -1


def test_oberflaeche_stab():
    from tests.meldungen import abfangen
    w, app = _fenster()
    # Umbenennen ueber die Objektmaske
    _setzen(w, app, _stab_verweise(_basis()))
    w._objekt_uebernehmen("stab", "S2", {"name": "Riegel", "elemente": "1", "design": True})
    app.processEvents()
    alt = _stabnamen(w.model, "S2")
    check("F09 Oberfläche (Maske Stab): kein Verweis nennt danach noch S2",
          "Riegel" in w.model.members and not any(alt.values()), str({k: v for k, v in alt.items() if v}))
    # Loeschen im Modellbaum: gesperrt mit Grund, nichts geaendert, kein Rueckgaengig-Schritt
    _setzen(w, app, _stab_verweise(_basis()))
    schritte = len(w._undo)
    mel = abfangen(w)
    w._baum_loeschen("stab", "S2")
    app.processEvents()
    mel.zurueck()
    check("F28 Oberfläche (Modellbaum): Stab mit Verformungsnachweis bleibt, Meldung mit Grund, kein Schritt",
          "S2" in w.model.members and any("VG1" in t for t in mel.alle) and len(w._undo) == schritte,
          str(mel.alle))
    # Loeschen im Modellbaum ohne Nachweise
    _setzen(w, app, _stab_verweise(_basis(), vg=False, le=False))
    w._baum_loeschen("stab", "S2")
    app.processEvents()
    rest = _stabnamen(w.model, "S2")
    check("F28 Oberfläche (Modellbaum): gelöscht, kein Verweis bleibt",
          "S2" not in w.model.members and not any(rest.values()), str({k: v for k, v in rest.items() if v}))
    # Register Staebe „Löschen“
    _setzen(w, app, _stab_verweise(_basis(), vg=False, le=False))
    w.refresh_all()
    w.tbl_mem.setCurrentCell(_zeile(w.tbl_mem, "S2"), 0)
    w.remove_member()
    app.processEvents()
    rest = _stabnamen(w.model, "S2")
    check("F28 Oberfläche (Register Stäbe): gelöscht, kein Verweis bleibt",
          "S2" not in w.model.members and not any(rest.values()), str({k: v for k, v in rest.items() if v}))
    _setzen(w, app, _stab_verweise(_basis()))
    w.refresh_all()
    w.tbl_mem.setCurrentCell(_zeile(w.tbl_mem, "S2"), 0)
    schritte = len(w._undo)
    mel = abfangen(w)
    w.remove_member()
    app.processEvents()
    mel.zurueck()
    check("F28 Oberfläche (Register Stäbe): gesperrt mit Hinweis, kein Rückgängig-Schritt",
          "S2" in w.model.members and mel.hinweis_mit("VG1") and len(w._undo) == schritte, str(mel.alle))
    # Entf in der Ansicht
    _setzen(w, app, _stab_verweise(_basis(), vg=False, le=False))
    w.auswahl_loeschen("stab", ["S2"])
    app.processEvents()
    rest = _stabnamen(w.model, "S2")
    check("F28 Oberfläche (Entf): gelöscht, kein Verweis bleibt",
          "S2" not in w.model.members and not any(rest.values()), str({k: v for k, v in rest.items() if v}))


def test_oberflaeche_kontakt():
    w, app = _fenster()
    m = _fuge(_basis())
    _setzen(w, app, m)
    w._eigenschaften_uebernehmen("kontaktbedingung", "Fuge", {"name": "Fuge neu"})
    app.processEvents()
    ziele = [u.ziel for u in w.model.case("LF1").uebermasse]
    check("F10 Oberfläche (Maske): das Übermaß folgt der umbenannten Bedingung (Beleg probe_fe6)",
          list(w.model.kontaktbedingungen) == ["Fuge neu"] and ziele == ["Fuge neu"],
          f"{list(w.model.kontaktbedingungen)} {ziele}")
    # Eine automatische Bedingung benennt das Programm selbst um, wenn sich ihre Wirkung aendert
    m = _basis()
    m.koerper["A"] = Volumenkoerper("A")
    m.koerper["B"] = Volumenkoerper("B")
    kb = m.add_kontaktbedingung("A–B starr", koerpernamen=["A"], gegenkoerper=["B"], automatisch=True)
    kb.standard_anwenden("Verbund")
    m.add_uebermass("A–B starr", 30e-6)
    # Die Koerper haben keine Geometrie und beruehren sich nicht: die Suche
    # nach Beruehrungen (refresh_all) naehme den Kontakt sonst gleich weg
    w._kontakte_nachfuehren = lambda: None
    _setzen(w, app, m)
    w._eigenschaften_uebernehmen("kontaktbedingung", "A–B starr",
                                 {"name": "A–B starr", "koerper_a": "A", "koerper_b": "B", "zug": "abheben"})
    app.processEvents()
    namen = list(w.model.kontaktbedingungen)
    ziele = [u.ziel for u in w.model.case("LF1").uebermasse]
    check("F10 Oberfläche (automatischer Name): das Übermaß folgt dem neuen Namen",
          len(namen) == 1 and namen[0] != "A–B starr" and ziele == namen, f"{namen} {ziele}")
    del w._kontakte_nachfuehren
    # Entf in der Ansicht: wie der Modellbaum - Uebermass, Kontaktpaar, getrennte Knoten gehen mit
    for weg in ("Entf", "Modellbaum"):
        _setzen(w, app, _fuge(_basis()))
        if weg == "Entf":
            w.auswahl_loeschen("kontakt", ["Fuge"])
        else:
            w._baum_loeschen("kontaktbedingung", "Fuge")
        app.processEvents()
        rest = _kontaktnamen(w.model, "Fuge")
        check(f"F28 Oberfläche ({weg}): Kontaktbedingung gelöscht, kein Verweis bleibt",
              "Fuge" not in w.model.kontaktbedingungen and not any(rest.values()),
              str({k: v for k, v in rest.items() if v}))


def test_kontakte_nachfuehren():
    """Ein automatischer Kontakt, dessen Koerper sich nicht mehr beruehren,
    geht ueber dieselbe Funktion - sein Uebermass mit ihm."""
    from statik3d import kontakte
    m = _basis()
    m.add_kontaktbedingung("A–B starr", koerpernamen=["A"], gegenkoerper=["B"], automatisch=True)
    m.add_uebermass("A–B starr", 30e-6)
    log = []
    r = kontakte.kontakte_nachfuehren(m, log)
    check("F28 automatischer Kontakt entfernt: sein Übermaß geht mit, keine Ausnahme vermerkt",
          r["entfernt"] == ["A–B starr"] and not m.case("LF1").uebermasse and not m.kontakt_ausnahmen,
          f"{r['entfernt']} {[u.ziel for u in m.case('LF1').uebermasse]} {m.kontakt_ausnahmen}")


def test_oberflaeche_kombination_ermuedung():
    from tests.meldungen import abfangen
    w, app = _fenster()

    def nach_co1(text):
        mm = w.model
        check(f"F28 Oberfläche ({text}): CO1 weg, F1 entfällt, F2 ohne CO1, K1 ohne F1, Bild weg",
              "CO1" not in mm.combinations and "F1" not in mm.fatigue_loads
              and "CO1" not in mm.fatigue_loads["F2"].folge and mm.joints["K1"].ermuedung == ["F3"]
              and not any(e.quelle == "combo:CO1" for e in mm.bericht),
              f"{list(mm.combinations)} {list(mm.fatigue_loads)} {mm.joints['K1'].ermuedung}")

    _setzen(w, app, _kombi())
    w._baum_loeschen("kombination", "CO1")
    app.processEvents()
    nach_co1("Modellbaum")
    _setzen(w, app, _kombi())
    w.refresh_all()
    w.tbl_comb.setCurrentCell(_zeile(w.tbl_comb, "CO1"), 0)
    w.remove_combination()
    app.processEvents()
    nach_co1("Register Kombinationen")
    _setzen(w, app, _kombi())
    w.clear_combinations()
    app.processEvents()
    mm = w.model
    check("F28 Oberfläche (Alle Kombinationen löschen): F1 entfällt, Verlauf F2 nur noch LF2, Bilder weg",
          not mm.combinations and "F1" not in mm.fatigue_loads and mm.fatigue_loads["F2"].folge == ["LF2"]
          and not mm.bericht and mm.joints["K1"].ermuedung == ["F3"],
          f"{list(mm.fatigue_loads)} {[e.quelle for e in mm.bericht]} {mm.joints['K1'].ermuedung}")

    def nach_e1(text):
        mm = w.model
        check(f"F29 Oberfläche ({text}): E1 weg und aus jedem Anschluss",
              "E1" not in mm.fatigue_loads
              and [mm.joints[k].ermuedung for k in ("K1", "K2", "K3")] == [["E2"], [], []],
              str([mm.joints[k].ermuedung for k in ("K1", "K2", "K3")]))

    _setzen(w, app, _ermuedung())
    w._baum_loeschen("ermuedungslast", "E1")
    app.processEvents()
    nach_e1("Modellbaum")
    _setzen(w, app, _ermuedung())
    w.refresh_all()
    w.tbl_fatl.setCurrentCell(_zeile(w.tbl_fatl, "E1"), 0)
    w.remove_fatigue_load()
    app.processEvents()
    nach_e1("Register Lastfälle")
    _setzen(w, app, _ermuedung())
    w.maske_ermuedungslasten(name="E1")
    app.processEvents()
    mk = w.maskenrand.maske
    mel = abfangen(w)
    mk.zeile_loeschen()
    app.processEvents()
    mel.zurueck()
    nach_e1("Ermüdungsmaske")
    # Umbenennen in der Maske: der Anschluss folgt (Kontrolle - das tat die Maske schon)
    _setzen(w, app, _ermuedung())
    w.maske_ermuedungslasten(name="E2")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.name.setText("Kran")
    mk.anwenden()
    app.processEvents()
    check("F29 Kontrolle (Ermüdungsmaske umbenennen): der Anschluss folgt, die Zeile bleibt an ihrem Platz",
          w.model.joints["K1"].ermuedung == ["E1", "Kran"] and list(w.model.fatigue_loads) == ["E1", "Kran", "E3"],
          f"{w.model.joints['K1'].ermuedung} {list(w.model.fatigue_loads)}")


def test_browser():
    from statik3d.web.server import State, apply_op, ApiError

    def op(m, **d):
        try:
            return apply_op(State(m), d)
        except ApiError as ex:
            return ex

    m = _stab_verweise(_basis(), vg=False, le=False)
    op(m, op="remove_member", name="S2")
    rest = _stabnamen(m, "S2")
    check("F28 Browser (remove_member): gelöscht, kein Verweis bleibt",
          "S2" not in m.members and not any(rest.values()), str({k: v for k, v in rest.items() if v}))
    # Das Loeschen nimmt die Linienlasten und Vorspannungen des Stabs mit - die
    # Analyse gilt danach nicht mehr (bis dahin blieb sie: remove_member stand
    # unter den Operationen, die nur die Nachweise verwerfen)
    from statik3d import solver
    st = State(_stab_verweise(_basis(), vg=False, le=False))
    st.analysis = solver.solve_all(st.model, design=False, fatigue=False)
    apply_op(st, {"op": "remove_member", "name": "S2"})
    check("F28 Browser (remove_member): die Analyse wird verworfen, der Stab trug Lasten",
          st.analysis is None, type(st.analysis).__name__)
    m = _stab_verweise(_basis())
    r = op(m, op="remove_member", name="S2")
    check("F28 Browser (remove_member): mit Verformungsnachweis abgewiesen, mit Grund",
          "S2" in m.members and isinstance(r, ApiError) and "VG1" in str(r), str(r)[:120])
    m = _kombi()
    op(m, op="remove_combination", name="CO1")
    check("F28 Browser (remove_combination): F1 entfällt, K1 ohne F1, Bild weg",
          "CO1" not in m.combinations and "F1" not in m.fatigue_loads and m.joints["K1"].ermuedung == ["F3"]
          and not any(e.quelle == "combo:CO1" for e in m.bericht), f"{list(m.fatigue_loads)}")
    m = _kombi()
    op(m, op="clear_combinations")
    check("F28 Browser (clear_combinations): F1 entfällt, Verlauf F2 nur noch LF2, Bilder weg",
          not m.combinations and "F1" not in m.fatigue_loads and m.fatigue_loads["F2"].folge == ["LF2"]
          and not m.bericht, f"{list(m.fatigue_loads)} {[e.quelle for e in m.bericht]}")
    m = _ermuedung()
    op(m, op="remove_fatigue_load", name="E1")
    check("F29 Browser (remove_fatigue_load): E1 weg und aus jedem Anschluss",
          "E1" not in m.fatigue_loads and [m.joints[k].ermuedung for k in ("K1", "K2", "K3")] == [["E2"], [], []],
          str([m.joints[k].ermuedung for k in ("K1", "K2", "K3")]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_f09_stab_umbenennen, test_f10_kontaktbedingung_umbenennen,
              test_f10_pruefung_uebermass_ohne_bedingung, test_f28_stab_loeschen, test_f28_lastfall_loeschen,
              test_f28_kombination_loeschen, test_f29_ermuedungslast, test_f29_anschlussnachweis,
              test_kontakte_nachfuehren, test_browser, test_oberflaeche_stab, test_oberflaeche_kontakt,
              test_oberflaeche_kombination_ermuedung):
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
    # ohne Aufraeumen beenden: kein Fenster und keine Rueckfrage bleibt stehen
    os._exit(code)
