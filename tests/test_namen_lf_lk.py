"""
Namen der Lastfaelle und Kombinationen - Paket R2-A1 (Datenmodell), 04.10.2026.

Entscheidung des Anwenders vom 04.10.2026: ein Lastfall heisst LF<Nr>, eine
Lastkombination LK<Nr>, eine Ergebniskombination EK<Nr>; der bisherige freie
Name wird zur Bezeichnung („LF3 W_links“). A1 erzwingt noch nichts, sondern
bereitet vor:

* Felder ``LoadCase.bezeichnung``, ``Combination.nummer``, ``art`` (LK/EK)
  und ``bezeichnung``, gespeichert und geladen (Dateifassung bleibt 8);
* Nummernvergabe aus einer Hand (``Model.naechste_nummer``), die Felder und
  Namen der Form LF<n>/LK<n>/EK<n> beachtet;
* zentrale Umbenennung ``Model.lastfall_umbenennen`` und
  ``kombination_umbenennen``, die jeden Verweis der Bestandsaufnahme
  (Abschnitt 2.1) mitnimmt und einen vergebenen Namen abweist;
* alle Umbenennwege der Oberflaeche und des Webservers rufen sie;
* der Kombinationsgenerator ueberschreibt keine Kombination mehr.

Abnahme N1 bis N9 (vorher festgelegt): jede Zeile schlug auf 36f8d8f fehl,
ausser N9 - der Vergleich mit 36f8d8f selbst (Generator unter den Beispielen
unveraendert; die Rechnung bytegleich misst ein eigenes Skript gegen den
alten Baum).

Nachbesserung nach der Gegenpruefung von d58b8b7 (Abnahme A1-1 bis A1-6):
G1 Ergebnisse folgen jeder Namensaenderung (Analyse, Stellungsreihe und ihre
Umhuellende werden auf jedem Weg verworfen, auch im Browser; eine
Ergebnisdatei mit fremder Kombination laedt nicht), G2 offene Masken folgen
oder schliessen mit Hinweis, G3 kein Weg legt an oder kopiert an der
Namenspruefung vorbei, G4 Nummern und Namensformen eindeutig, G5 der
Generator ersetzt nur Eigenes und Unberuehrtes, F3/S3 Stand der Art bis C2
und Berichtstexte nur ueber den Klartext der Quelle, L4 Rueckgaengig,
Wiederholen und Ergebniskombination ueber die Oberflaeche. Jede dieser
Pruefungen schlug auf d58b8b7 fehl, ausser den als „Kontrolle“ benannten.

Aufruf:  python -m tests.test_namen_lf_lk
"""
import hashlib
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Neu und Beispiel ohne die Rueckfrage „Ungespeicherte Änderungen“
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_namen_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Combination, FatigueLoad, Berichtseintrag  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d import mesher, solver  # noqa: E402

RESULTS = []
_FENSTER = {}
HIER = os.path.dirname(os.path.abspath(__file__))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Pruefmodell: Kragarm mit je einem Verweis jeder Art auf Lastfall „W“
# --------------------------------------------------------------------------
def _kragarm() -> Model:
    """IPE 200, 2 m, Lastfaelle LF1 (G), W (Wind), LF3 (Q) mit Einzellast an
    der Spitze; Stab mit Kerbfall fuer die Ermuedung."""
    m = Model("Namen")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (2, 0, 0), 4)
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.case("LF1").category = "G"
    m.load_node(ids[-1], Fz=-10000.0, case="LF1")
    m.add_load_case("W", "W", "Wind von links", activate=False)
    m.load_node(ids[-1], Fy=4000.0, Fz=-25000.0, case="W")
    m.add_load_case("LF3", "Q", "Nutzlast", activate=False)
    m.load_node(ids[-1], Fz=-5000.0, case="LF3")
    m.add_member("Kragarm", list(range(4)), detail_category=71e6)
    return m


def _mit_verweisen(m: Model) -> Model:
    """Je ein Verweis jeder Art aus der Bestandsaufnahme R2, Abschnitt 2.1, auf
    den Lastfall „W“ - und auf die Kombination K1 und die Ergebnis-
    kombination EK1."""
    from statik3d.bridges.positions import Stellung
    from statik3d.wind import Wind
    from statik3d.wasserdruck import Wasserdruck
    k1 = m.add_combination("K1", {"LF1": 1.35, "W": 1.5, "LF3": 1.05}, "ULS", "von Hand", "W")
    k1.bemessungssituation = "GZT ständig/vorübergehend"
    m.combinations["EK1"] = Combination("EK1", {}, "ULS", "aus RFEM",
                                        bemessungssituation="GZT (STR/GEO) - ständig",
                                        alternativen=[{"LF1": 1.35, "W": 1.5}, {"LF1": 1.0, "LF3": 1.5}])
    m.fatigue_loads["F_max"] = FatigueLoad("F_max", "W", "LF1", cycles=1e5)
    m.fatigue_loads["F_min"] = FatigueLoad("F_min", "LF3", "W", cycles=1e5)
    m.fatigue_loads["F_folge"] = FatigueLoad("F_folge", folge=["LF1", "W", "LF3"], wiederholungen=1e5)
    m.fatigue_loads["F_komb"] = FatigueLoad("F_komb", "K1", None, cycles=1e4)
    m.stellungen.append(Stellung("S1", 0.0, "geschlossen", faelle=["LF1", "W", "LF3"],
                                 kombinationen=["K1", "EK1"]))
    m.winde["W1"] = Wind("W1", lastfall="W")
    m.wasserdruecke["WD1"] = Wasserdruck("WD1", lastfall="W", lastfall_dyn="W")
    m.active_case = "W"
    m.bericht += [
        Berichtseintrag("Bild 1", "case:W", "Verschiebung", beschriftung="Lastfall W · Verschiebung"),
        Berichtseintrag("Stabkräfte · Lastfall W", "case:W", art="tabelle", tabelle="Stabkräfte"),
        Berichtseintrag("Bild 2", "case:W", "Verschiebung", beschriftung="Lastfall W · Windlast von links"),
        Berichtseintrag("Bild 3", "combo:K1", "Verschiebung", beschriftung="Kombination K1 · Verschiebung"),
        Berichtseintrag("Bild 4", "env:EK1", "Verschiebung", beschriftung="Umhüllende EK1 · Verschiebung"),
        Berichtseintrag("Bild 5", "env:ULS", "Verschiebung", beschriftung="Umhüllende GZT · Verschiebung"),
        Berichtseintrag("Bild 6", "case:LF1", "Verschiebung", beschriftung="Lastfall LF1 · Verschiebung")]
    return m


def _modell() -> Model:
    return _mit_verweisen(_kragarm())


def _fundstellen(d, alt: str, pfad: str = "") -> list:
    """Jede Stelle der gespeicherten Form, an der der Name *alt* steht: als
    Schluessel, als Wert, als Quelle case:/combo:/env: und als ganzes Wort in
    Name oder Beschriftung eines Berichtseintrags. Die Einwirkungskategorie
    (category „W“) ist kein Name."""
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            if k == alt:
                out.append(f"{pfad}/{k} (Schlüssel)")
            if k == "category":
                continue
            out += _fundstellen(v, alt, f"{pfad}/{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out += _fundstellen(v, alt, f"{pfad}[{i}]")
    elif isinstance(d, str):
        art, _, wert = d.partition(":")
        if d == alt or (art in ("case", "combo", "env") and wert == alt):
            out.append(f"{pfad} = {d!r}")
        elif ("/bericht" in pfad and pfad.endswith(("/name", "/beschriftung"))
              and re.search(rf"(?<!\w){re.escape(alt)}(?!\w)", d)):
            out.append(f"{pfad} = {d!r}")
    return out


def _werte(an, umbenannt: dict) -> dict:
    """Alle Rechenwerte mit dem Namen nach dem Umbenennen als Schluessel:
    Verschiebungen je Lastfall und Kombination, Umhuellende (min/max),
    Ausnutzung EC3 und Ermuedung je Stab."""
    def nn(n):
        return umbenannt.get(n, n)
    out = {}
    for n, r in an.cases.items():
        out[("Lastfall", nn(n))] = np.asarray(r.u, float)
    for n, r in an.combinations.items():
        out[("Kombination", nn(n))] = np.asarray(r.u, float)
    for n, e in an.envelopes.items():
        out[("Umhüllende", nn(n))] = np.concatenate([np.ravel(e.u_min), np.ravel(e.u_max)])
    if an.design is not None:
        for n, mc in an.design.members.items():
            out[("EC3", n)] = np.array([mc.util], float)
    if an.fatigue is not None:
        for n, fm in an.fatigue.members.items():
            out[("Ermüdung", n)] = np.array([fm.util], float)
    return out


def _rechnung_gleich(name, vor, nach):
    fehlt = sorted(set(vor) ^ set(nach))
    du = max((float(np.max(np.abs(vor[k] - nach[k]))) if vor[k].size else 0.0
              for k in vor if k in nach), default=float("nan"))
    return check(name, not fehlt and du == 0.0,
                 f"{len(vor)} Werte, max|du| = {du:g}" + (f", fehlt {fehlt[:3]}" if fehlt else ""))


def _rechnen(m):
    return solver.solve_all(m, design=True, fatigue=True)


def _gezaehlt(methode: str):
    """Model.<methode> mit Zaehler umhuellen; (Zaehler, Rueckbau). Fehlt die
    Methode (Stand vor R2-A1), bleibt der Zaehler bei null."""
    zaehler = [0]
    alt = getattr(Model, methode, None)
    if alt is None:
        return zaehler, lambda: None

    def gezaehlt(self, *a, **k):
        zaehler[0] += 1
        return alt(self, *a, **k)
    setattr(Model, methode, gezaehlt)
    return zaehler, lambda: setattr(Model, methode, alt)


# --------------------------------------------------------------------------
# Pruefungen der Verweise nach dem Umbenennen
# --------------------------------------------------------------------------
def _pruefe_lastfall(weg: str, m: Model, alt="W", neu="LF9", stellung=True):
    """Jeder Verweis auf den Lastfall *alt* zeigt auf *neu*, keiner auf *alt*."""
    k1, ek1 = m.combinations.get("K1"), m.combinations.get("EK1")
    check(f"{weg}: Lastfall heißt {neu}, Reihenfolge bleibt",
          list(m.load_cases) == ["LF1", neu, "LF3"] and m.load_cases[neu].name == neu,
          str(list(m.load_cases)))
    check(f"{weg}: aktiver Lastfall folgt", m.active_case == neu, m.active_case)
    check(f"{weg}: Faktoren und Alternativen der Kombinationen folgen",
          k1 is not None and neu in k1.factors and alt not in k1.factors
          and ek1 is not None and neu in ek1.alternativen[0] and alt not in ek1.alternativen[0],
          f"{k1 and k1.factors}, {ek1 and ek1.alternativen}")
    check(f"{weg}: Leiteinwirkung (leading) folgt", k1 is not None and k1.leading == neu,
          repr(k1 and k1.leading))
    fl = m.fatigue_loads
    check(f"{weg}: Ermüdungslasten folgen (oberer, unterer Zustand, Verlauf)",
          fl["F_max"].case_max == neu and fl["F_min"].case_min == neu
          and fl["F_folge"].folge == ["LF1", neu, "LF3"] and fl["F_komb"].case_max == "K1",
          f"{fl['F_max'].case_max}, {fl['F_min'].case_min}, {fl['F_folge'].folge}")
    if stellung:
        st = m.stellungen[0]
        check(f"{weg}: Lastfallliste der Stellung folgt", st.faelle == ["LF1", neu, "LF3"], str(st.faelle))
    check(f"{weg}: Wind und Wasserdruck folgen (lastfall, lastfall_dyn)",
          m.winde["W1"].lastfall == neu and m.wasserdruecke["WD1"].lastfall == neu
          and m.wasserdruecke["WD1"].lastfall_dyn == neu,
          f"{m.winde['W1'].lastfall}, {m.wasserdruecke['WD1'].lastfall}, "
          f"{m.wasserdruecke['WD1'].lastfall_dyn}")
    b = m.bericht
    check(f"{weg}: Berichtseinträge: Quelle case:{neu}",
          [e.quelle for e in b[:3]] == [f"case:{neu}"] * 3 and b[5].quelle == "env:ULS"
          and b[6].quelle == "case:LF1", str([e.quelle for e in b]))
    check(f"{weg}: eingefrorene Texte mit dem Namen als Ganzes folgen, „Windlast“ bleibt",
          b[0].beschriftung == f"Lastfall {neu} · Verschiebung"
          and b[1].name == f"Stabkräfte · Lastfall {neu}"
          and b[2].beschriftung == f"Lastfall {neu} · Windlast von links"
          and b[6].beschriftung == "Lastfall LF1 · Verschiebung",
          f"{b[0].beschriftung!r}, {b[1].name!r}, {b[2].beschriftung!r}")
    unbekannt = [z for z in m.check() if "unbekannt" in z]
    check(f"{weg}: Modellprüfung meldet nichts „unbekannt“", not unbekannt, "; ".join(unbekannt)[:90])
    rest = _fundstellen(m.to_dict(), alt)
    check(f"{weg}: in der gespeicherten Form steht „{alt}“ nirgends mehr", not rest, "; ".join(rest[:3]))


def _pruefe_kombination(weg: str, m: Model, alt="K1", neu="LK7", vorher=None):
    c = m.combinations.get(neu)
    check(f"{weg}: Kombination heißt {neu}, Reihenfolge bleibt",
          c is not None and c.name == neu and alt not in m.combinations
          and list(m.combinations) == [neu, "EK1"], str(list(m.combinations)))
    if vorher is not None:
        check(f"{weg}: dasselbe Objekt - leading und bemessungssituation bleiben",
              c is vorher and c.leading == "W" and c.bemessungssituation == "GZT ständig/vorübergehend",
              f"leading {c and c.leading!r}, {c and c.bemessungssituation!r}, "
              f"dasselbe Objekt {c is vorher}")
    check(f"{weg}: Ermüdungslast mit der Kombination als Zustand folgt",
          m.fatigue_loads["F_komb"].case_max == neu, repr(m.fatigue_loads["F_komb"].case_max))
    check(f"{weg}: Kombinationsliste der Stellung folgt",
          m.stellungen[0].kombinationen == [neu, "EK1"], str(m.stellungen[0].kombinationen))
    b = m.bericht
    check(f"{weg}: Berichtsbild combo:{neu} mit Beschriftung",
          b[3].quelle == f"combo:{neu}" and b[3].beschriftung == f"Kombination {neu} · Verschiebung",
          f"{b[3].quelle}, {b[3].beschriftung!r}")
    rest = _fundstellen(m.to_dict(), alt)
    check(f"{weg}: in der gespeicherten Form steht „{alt}“ nirgends mehr", not rest, "; ".join(rest[:3]))


# --------------------------------------------------------------------------
# N1 - Lastfall umbenennen
# --------------------------------------------------------------------------
def test_n1_lastfall_umbenennen():
    m = _modell()
    vorher = _fundstellen(m.to_dict(), "W")
    check("N1 Prüfmodell: jede Verweisart nennt „W“", len(vorher) >= 18, f"{len(vorher)} Fundstellen")
    vor = _werte(_rechnen(m), {"W": "LF9"})
    try:
        m.lastfall_umbenennen("W", "LF9")
    except Exception as ex:      # noqa: BLE001
        check("N1 Model.lastfall_umbenennen läuft", False, repr(ex))
        return
    _pruefe_lastfall("N1 Modell", m)
    nachher = _fundstellen(m.to_dict(), "LF9")
    check("N1 genauso viele Fundstellen für LF9 wie vorher für W", len(nachher) == len(vorher),
          f"{len(nachher)} gegen {len(vorher)}")
    _rechnung_gleich("N1 Rechnung vorher und nachher gleich", vor, _werte(_rechnen(m), {}))

    # Der Webserver ruft dieselbe Funktion (bis A1 ohne Stellungen und Bericht)
    from statik3d.web import OPS
    m = _modell()
    zaehler, zurueck = _gezaehlt("lastfall_umbenennen")
    try:
        OPS["edit_case"](None, m, {"name": "W", "fields": {"new_name": "LF9"}})
    finally:
        zurueck()
    check("N1 Web edit_case ruft Model.lastfall_umbenennen", zaehler[0] == 1, str(zaehler[0]))
    _pruefe_lastfall("N1 Web", m)


# --------------------------------------------------------------------------
# N2 - Kombination und Ergebniskombination umbenennen
# --------------------------------------------------------------------------
def test_n2_kombination_umbenennen():
    m = _modell()
    vor = _werte(_rechnen(m), {"K1": "LK7", "EK1": "EK5"})
    k1 = m.combinations["K1"]
    try:
        m.kombination_umbenennen("K1", "LK7")
    except Exception as ex:      # noqa: BLE001
        check("N2 Model.kombination_umbenennen läuft", False, repr(ex))
        return
    _pruefe_kombination("N2 Kombination", m, vorher=k1)
    ek = m.combinations["EK1"]
    m.kombination_umbenennen("EK1", "EK5")
    b = m.bericht
    check("N2 Ergebniskombination: Name, Alternativen und Bemessungssituation",
          list(m.combinations) == ["LK7", "EK5"] and m.combinations["EK5"] is ek and ek.name == "EK5"
          and len(ek.alternativen) == 2 and ek.bemessungssituation == "GZT (STR/GEO) - ständig",
          str(list(m.combinations)))
    check("N2 Stellung nennt EK5", m.stellungen[0].kombinationen == ["LK7", "EK5"],
          str(m.stellungen[0].kombinationen))
    check("N2 Berichtsbild env:EK5, die Umhüllende GZT (env:ULS) bleibt",
          b[4].quelle == "env:EK5" and b[4].beschriftung == "Umhüllende EK5 · Verschiebung"
          and b[5].quelle == "env:ULS" and b[5].beschriftung == "Umhüllende GZT · Verschiebung",
          f"{b[4].quelle} {b[4].beschriftung!r}, {b[5].quelle}")
    rest = _fundstellen(m.to_dict(), "EK1")
    check("N2 in der gespeicherten Form steht „EK1“ nirgends mehr", not rest, "; ".join(rest[:3]))
    nach = _werte(_rechnen(m), {})
    _rechnung_gleich("N2 Rechnung vorher und nachher gleich", vor, nach)

    # Eine Ergebniskombination, die wie eine Umhuellende des Programms heisst
    # („ULS“), liegt seit R1 unter „ULS (Ergebniskombination)“: das Bild dieser
    # Umhuellenden folgt dem neuen Namen, das Bild der Umhuellenden GZT nicht
    m = Model("R1")
    m.add_load_case("LF2", "Q", activate=False)
    m.add_combination("K2", {"LF1": 1.35, "LF2": 1.5}, "ULS")
    m.combinations["ULS"] = Combination("ULS", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 1.0}])
    m.bericht += [Berichtseintrag("Bild 1", "env:ULS (Ergebniskombination)", "u",
                                  beschriftung="Umhüllende ULS (Ergebniskombination) · u"),
                  Berichtseintrag("Bild 2", "env:ULS", "u", beschriftung="Umhüllende GZT · u")]
    m.kombination_umbenennen("ULS", "EK8")
    b = m.bericht
    check("N2 R1-Schlüssel: env:ULS (Ergebniskombination) wird env:EK8, env:ULS bleibt",
          b[0].quelle == "env:EK8" and b[0].beschriftung == "Umhüllende EK8 · u"
          and b[1].quelle == "env:ULS" and b[1].beschriftung == "Umhüllende GZT · u",
          f"{b[0].quelle} {b[0].beschriftung!r}, {b[1].quelle} {b[1].beschriftung!r}")


# --------------------------------------------------------------------------
# N3 - vergebene Namen werden abgewiesen
# --------------------------------------------------------------------------
def test_n3_vergebener_name():
    m = _modell()
    m.combinations["K [1]"] = Combination("K [1]", {"LF1": 1.0}, "ULS")
    stand = json.dumps(m.to_dict(), sort_keys=True, default=str)
    faelle = [("Lastfall → Name einer Kombination", "lastfall_umbenennen", "W", "K1", "K1"),
              ("Lastfall → Name eines Lastfalls", "lastfall_umbenennen", "W", "LF1", "LF1"),
              ("Lastfall → Name einer Alternative „EK1 [1]“", "lastfall_umbenennen", "W", "EK1 [1]",
               "Alternative 1"),
              ("Kombination → „EK1 [2]“", "kombination_umbenennen", "K1", "EK1 [2]", "Alternative 2"),
              ("Kombination → Name eines Lastfalls", "kombination_umbenennen", "K1", "W", "W"),
              ("Kombination → Name einer Kombination", "kombination_umbenennen", "K1", "EK1", "EK1"),
              ("Ergebniskombination → „K“ neben einer Kombination „K [1]“", "kombination_umbenennen",
               "EK1", "K", "K [1]")]
    for text, methode, alt, neu, im_text in faelle:
        fn = getattr(m, methode, None)
        if fn is None:
            check(f"N3 {text}: abgewiesen", False, f"Model.{methode} fehlt")
            continue
        try:
            fn(alt, neu)
            meldung = None
        except ValueError as ex:
            meldung = str(ex)
        jetzt = json.dumps(m.to_dict(), sort_keys=True, default=str)
        check(f"N3 {text}: abgewiesen mit Text, Modell unverändert",
              meldung is not None and im_text in meldung and jetzt == stand,
              (meldung or "nicht abgewiesen")[:90])


# --------------------------------------------------------------------------
# N4 - Oberflaeche: Maske, Dialog und Tabellenwege
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


def _aufraeumen(w, app):
    """Eine abgewiesene Maske behaelt ihre Aenderungen (Paket 13m): die Leiste
    „Übernehmen | Verwerfen“ hielte jede naechste Maske an - verwerfen."""
    from PySide6 import QtWidgets
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        for b in leiste.findChildren(QtWidgets.QPushButton):
            if b.text() == "Verwerfen":
                b.click()
                break
    w.maskenrand.schliessen()
    app.processEvents()


def _setzen(w, app, m):
    _aufraeumen(w, app)
    w._modell_setzen(m)
    app.processEvents()


def _maske_anwenden(w, app, art, name, werte: dict):
    _aufraeumen(w, app)
    w._objektmaske(art, name)
    app.processEvents()
    mk = w.maskenrand.maske
    for k, v in werte.items():
        mk.setzen(k, v)
    mk.anwenden()
    app.processEvents()


class _Lastfalldialog:
    """Attrappe des Lastfalldialogs: der Name wird *neuer_name*."""
    neuer_name = "LF9"

    def __init__(self, _fenster, lc, *_a, **_k):
        self.lc = lc

    def exec(self):
        return True

    def values(self):
        return (self.neuer_name, self.lc.category, self.lc.description, self.lc.exclusive_group)

    def situation_name(self):
        return self.lc.situation

    def theorie_name(self):
        return self.lc.theorie


def _kombinationsdialog(name):
    """Der echte Kombinationsdialog, nur mit neuem Namen und ohne Warten."""
    from statik3d.gui import dialogs as dg

    class Dialog(dg.CombinationDialog):
        def exec(self):
            self.name.setText(name)
            return True
    return Dialog


def test_n4_oberflaeche():
    import importlib
    from unittest import mock
    from tests.meldungen import abfangen
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()
    lf_zaehler, lf_zurueck = _gezaehlt("lastfall_umbenennen")
    k_zaehler, k_zurueck = _gezaehlt("kombination_umbenennen")
    try:
        # -- Lastfall: Maske rechts, Dialog (Tabelle unten), Register ---------
        _setzen(w, app, _modell())
        _maske_anwenden(w, app, "lastfall", "W", {"name": "LF9"})
        _pruefe_lastfall("N4 Maske Lastfall", w.model)

        _setzen(w, app, _modell())
        _Lastfalldialog.neuer_name = "LF9"
        with mock.patch.object(G.dg, "LoadCaseDialog", _Lastfalldialog):
            w.lastfall_bearbeiten("W")
        app.processEvents()
        _pruefe_lastfall("N4 Dialog Lastfall (Tabelle unten)", w.model)

        _setzen(w, app, _modell())
        w.model.active_case = "W"
        with mock.patch.object(G, "LoadCaseDialog", _Lastfalldialog):
            w.edit_case()
        app.processEvents()
        _pruefe_lastfall("N4 Register Lastfälle (edit_case)", w.model)
        check("N4 alle drei Lastfallwege rufen Model.lastfall_umbenennen", lf_zaehler[0] == 3,
              str(lf_zaehler[0]))

        # -- Kombination: Maske, Dialog (Tabelle unten), Register -----------
        _setzen(w, app, _modell())
        k1 = w.model.combinations["K1"]
        _maske_anwenden(w, app, "kombination", "K1", {"name": "LK7"})
        _pruefe_kombination("N4 Maske Kombination", w.model, vorher=k1)

        _setzen(w, app, _modell())
        k1 = w.model.combinations["K1"]
        with mock.patch.object(G.dg, "CombinationDialog", _kombinationsdialog("LK7")):
            w.kombination_bearbeiten("K1")
        app.processEvents()
        _pruefe_kombination("N4 Dialog Kombination (Tabelle unten)", w.model, vorher=k1)

        _setzen(w, app, _modell())
        k1 = w.model.combinations["K1"]
        w.refresh_all()
        app.processEvents()
        w.tbl_comb.setCurrentCell(list(w.model.combinations).index("K1"), 0)
        with mock.patch.object(G, "CombinationDialog", _kombinationsdialog("LK7")):
            w.edit_combination()
        app.processEvents()
        _pruefe_kombination("N4 Register Kombinationen (edit_combination)", w.model, vorher=k1)
        check("N4 alle drei Kombinationswege rufen Model.kombination_umbenennen", k_zaehler[0] == 3,
              str(k_zaehler[0]))
    finally:
        lf_zurueck()
        k_zurueck()

    # -- Doppelte Namen: Hinweis, kein Ueberschreiben, kein Verschwinden -------
    def doppelt(text, aufruf, im_hinweis):
        _setzen(w, app, _modell())
        m = w.model
        vorher = (dict(m.load_cases), dict(m.combinations))
        stand = json.dumps(m.to_dict(), sort_keys=True, default=str)
        mel = abfangen(w)
        try:
            aufruf(m)
            app.processEvents()
        finally:
            mel.zurueck()
        gleich = (dict(m.load_cases) == vorher[0] and dict(m.combinations) == vorher[1]
                  and json.dumps(m.to_dict(), sort_keys=True, default=str) == stand)
        check(f"N4 {text}: Hinweis, nichts überschrieben, nichts verschwunden",
              mel.hinweis_mit(im_hinweis) and not mel.fehler and gleich,
              f"Hinweise {mel.hinweise[:1]}, Fehler {mel.fehler[:1]}, Modell gleich {gleich}")

    def lf_dialog(name, weg):
        def f(m):
            _Lastfalldialog.neuer_name = name
            if weg == "tabelle":
                with mock.patch.object(G.dg, "LoadCaseDialog", _Lastfalldialog):
                    w.lastfall_bearbeiten("W")
            else:
                m.active_case = "W"
                with mock.patch.object(G, "LoadCaseDialog", _Lastfalldialog):
                    w.edit_case()
        return f

    def k_dialog(name, weg):
        def f(m):
            if weg == "tabelle":
                with mock.patch.object(G.dg, "CombinationDialog", _kombinationsdialog(name)):
                    w.kombination_bearbeiten("K1")
            else:
                w.refresh_all()
                app.processEvents()
                w.tbl_comb.setCurrentCell(list(m.combinations).index("K1"), 0)
                with mock.patch.object(G, "CombinationDialog", _kombinationsdialog(name)):
                    w.edit_combination()
        return f

    doppelt("Maske Lastfall → Name einer Kombination",
            lambda m: _maske_anwenden(w, app, "lastfall", "W", {"name": "K1"}), "K1")
    doppelt("Dialog Lastfall → vorhandener Lastfall", lf_dialog("LF3", "tabelle"), "LF3")
    doppelt("Register Lastfall → vorhandener Lastfall", lf_dialog("LF3", "register"), "LF3")
    doppelt("Register Lastfall → Name einer Kombination", lf_dialog("EK1", "register"), "EK1")
    doppelt("Maske Kombination → Name eines Lastfalls",
            lambda m: _maske_anwenden(w, app, "kombination", "K1", {"name": "W"}), "W")
    doppelt("Dialog Kombination → vorhandene Kombination", k_dialog("EK1", "tabelle"), "EK1")
    doppelt("Register Kombination → „EK1 [2]“", k_dialog("EK1 [2]", "register"), "EK1 [2]")

    # -- Nummern: Zelle der Lastfalltabelle und Maske -------------------------
    _setzen(w, app, _modell())
    m = w.model
    z = [str(r[0]) for r in w.tbl_lastfall.modell.zeilen].index("W")
    mel = abfangen(w)
    try:
        ok = w._lastfall_aendern(z, 1, 1)
    finally:
        mel.zurueck()
    check("N4 Nummernzelle: Nr. 1 (gehört LF1) wird mit Hinweis abgewiesen",
          not ok and mel.hinweis_mit("Nr. 1", "LF1") and m.load_cases["W"].nummer == 0,
          f"{ok}, {mel.hinweise[:1]}, Nr. {m.load_cases['W'].nummer}")
    mel = abfangen(w)
    try:
        ok = w._lastfall_aendern(z, 1, 12)
    finally:
        mel.zurueck()
    check("N4 Nummernzelle: freie Nr. 12 wird übernommen",
          ok and not mel.alle and m.load_cases["W"].nummer == 12, f"{ok}, {mel.alle[:1]}")
    mel = abfangen(w)
    try:
        _maske_anwenden(w, app, "lastfall", "LF3", {"nummer": 12})
    finally:
        mel.zurueck()
    check("N4 Maske Lastfall: Nr. 12 (gehört W) wird mit Hinweis abgewiesen",
          mel.hinweis_mit("Nr. 12", "W") and m.load_cases["LF3"].nummer == 0,
          f"{mel.hinweise[:1]}, Nr. {m.load_cases['LF3'].nummer}")


# --------------------------------------------------------------------------
# N5 - Wind auf einem umbenannten Lastfall
# --------------------------------------------------------------------------
def test_n5_wind_nach_umbenennen():
    from statik3d.model import Section, Member
    from statik3d import wind as wm
    from statik3d.wind import Wind

    def mast():
        m = Model("Mast")
        m.add_material(Material("S"))
        m.add_section(Section.pipe("CHS", 0.2, 0.006))
        ids = [m.add_node(0, 0, i * 1.0) for i in range(7)]
        el = [m.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(6)]
        m.members["Mast"] = Member("Mast", el)
        m.fix(ids[0], "all")
        wm.lasten_erzeugen(m, Wind("W1", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
        return m

    for weg in ("Modell", "Maske"):
        m = mast()
        n0 = len(m.load_cases["Wind W1"].linienlasten)
        if weg == "Modell":
            fn = getattr(m, "lastfall_umbenennen", None)
            if fn is None:
                check("N5 Modell: Model.lastfall_umbenennen vorhanden", False)
                continue
            fn("Wind W1", "LF5")
        else:
            w, app = _fenster()
            _setzen(w, app, m)
            _maske_anwenden(w, app, "lastfall", "Wind W1", {"name": "LF5"})
            m = w.model
        kw = wm.lasten_erzeugen(m, m.winde["W1"])
        # Gezaehlt wird nicht genau: ein zweites „Lasten erzeugen“ verdoppelt
        # die Stablasten schon auf 36f8d8f ohne Umbenennen (Nebenbefund, im
        # Bericht von R2-A1 genannt)
        check(f"N5 {weg}: „Lasten erzeugen“ schreibt in den umbenannten Lastfall, kein neuer Lastfall",
              list(m.load_cases) == ["LF1", "LF5"] and kw.get("lastfall") == "LF5"
              and len(m.load_cases["LF5"].linienlasten) >= n0 > 0 and m.winde["W1"].lastfall == "LF5",
              f"{list(m.load_cases)}, {m.winde['W1'].lastfall}, {kw.get('lastfall')}")


# --------------------------------------------------------------------------
# N6 - der Generator ueberschreibt keine Handkombination
# --------------------------------------------------------------------------
def test_n6_generator_ueberschreibt_nicht():
    from statik3d.combinations import generate_combinations

    def bau(hand: bool):
        m = Model("G")
        m.add_load_case("LF2", "Q", activate=False)
        if hand:
            m.add_combination("GZT2", {"LF2": 9.99}, "USER", "von Hand")
        return m
    ohne = generate_combinations(bau(False))
    m = bau(True)
    erzeugt = generate_combinations(m)
    hand = m.combinations.get("GZT2")
    namen = [c.name for c in erzeugt]
    check("N6 Handkombination „GZT2“ bleibt unverändert",
          hand is not None and hand.factors == {"LF2": 9.99} and hand.typ == "USER"
          and hand.description == "von Hand", str(hand and (hand.factors, hand.typ)))
    check("N6 der Generator nimmt freie Nummern: alle erzeugt, keiner heißt GZT2",
          len(erzeugt) == len(ohne) and "GZT2" not in namen and len(set(namen)) == len(namen)
          and all(n in m.combinations for n in namen) and len(m.combinations) == len(ohne) + 1,
          f"{namen}")
    # ein zweiter Lauf ersetzt nur die eigenen (description „auto…“)
    generate_combinations(m)
    check("N6 erneut erzeugt: die Handkombination bleibt",
          m.combinations.get("GZT2") is hand and hand.factors == {"LF2": 9.99},
          str(list(m.combinations)))


# --------------------------------------------------------------------------
# N7 - Nummernvergabe aus einer Hand
# --------------------------------------------------------------------------
def test_n7_nummernvergabe():
    m = Model()
    lc = m.load_cases.get("LF1")
    check("N7 leeres Modell: der Vorgabelastfall ist LF1 mit Nr. 1",
          lc is not None and lc.nummer == 1, f"Nr. {lc and lc.nummer}")
    fn = getattr(m, "naechste_nummer", None)
    check("N7 nächste freie Nummer je Art: LF 2, LK 1, EK 1",
          fn is not None and (fn("LF"), fn("LK"), fn("EK")) == (2, 1, 1)
          and m.naechste_lastfallnummer() == 2,
          str(fn and (fn("LF"), fn("LK"), fn("EK"))) + f", naechste_lastfallnummer {m.naechste_lastfallnummer()}")
    # Felder und Namen zaehlen: Name LF7 belegt 7, Feld nummer 4 an „Q“
    m.add_load_case("LF7", "Q", activate=False)
    m.add_load_case("Q", "Q", activate=False).nummer = 4
    m.add_combination("LK3", {"LF1": 1.0}, "ULS")
    ek = m.add_combination("Hülle", {}, "ULS")
    ek.alternativen = [{"LF1": 1.0}]
    ek.art, ek.nummer = "EK", 5
    m.add_combination("EK2", {"LF1": 1.0}, "ULS").art = "EK"
    check("N7 Namen LF<n>/LK<n>/EK<n> und Felder nummer: LF 8, LK 4, EK 6",
          fn is not None and (fn("LF"), fn("LK"), fn("EK")) == (8, 4, 6),
          str(fn and (fn("LF"), fn("LK"), fn("EK"))))

    # Oberflaeche: „Neu“ am Zweig Lastfaelle schlaegt Name und Nummer gleich vor
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    w._baum_neu("lastfaelle")
    app.processEvents()
    mk = w.maskenrand.maske
    werte = mk.werte() if mk is not None else {}
    check("N7 leeres Modell, Lastfall anlegen: Maske schlägt LF2 mit Nr. 2 vor (nicht LF2/Nr. 1)",
          werte.get("name") == "LF2" and int(werte.get("nummer") or 0) == 2,
          f"{werte.get('name')}/Nr. {werte.get('nummer')}")
    mk.anwenden()
    app.processEvents()
    lc = w.model.load_cases.get("LF2")
    check("N7 … und legt LF2 mit Nr. 2 an", lc is not None and lc.nummer == 2,
          f"{list(w.model.load_cases)}, Nr. {lc and lc.nummer}")
    # Name und Nummer aus derselben Quelle, auch wenn kein Name LF<n> mehr da
    # ist: LF1 heisst „G“, Nr. 4 traegt „Q“ - vorgeschlagen wird LF5 mit Nr. 5
    m = Model()
    m.lastfall_umbenennen("LF1", "G") if hasattr(m, "lastfall_umbenennen") else None
    m.add_load_case("Q", "Q", activate=False).nummer = 4
    _setzen(w, app, m)
    w._baum_neu("lastfaelle")
    app.processEvents()
    mk = w.maskenrand.maske
    werte = mk.werte() if mk is not None else {}
    check("N7 ohne Namen LF<n>: die Maske schlägt LF5 mit Nr. 5 vor (Name und Nummer aus einer Hand)",
          werte.get("name") == "LF5" and int(werte.get("nummer") or 0) == 5,
          f"{werte.get('name')}/Nr. {werte.get('nummer')}")
    _aufraeumen(w, app)


# --------------------------------------------------------------------------
# N8 - Speichern und Laden
# --------------------------------------------------------------------------
def test_n8_speichern_laden():
    m = Model()
    try:
        m.add_load_case("LF2", "W", "Wind von links, Böen nach Zone 2", activate=False, bezeichnung="W_links")
        m.add_combination("LK7", {"LF1": 1.35, "LF2": 1.5}, "ULS", "6.10, Leit W_links", "LF2",
                          nummer=7, art="LK", bezeichnung="GZT ständig")
        m.combinations["EK3"] = Combination("EK3", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF2": 1.0}],
                                            nummer=3, bezeichnung="Umhüllende Wind")
        # aus RFEM: eine Ergebniskombination mit nur einer Alternative ist dort
        # eine Summe - die Art EK bleibt trotzdem (Entscheidung 04.10.2026)
        m.combinations["EK4"] = Combination("EK4", {"LF1": 1.0}, "ULS", nummer=4, art="EK")
    except TypeError as ex:
        check("N8 Felder bezeichnung, nummer, art vorhanden", False, repr(ex))
        return
    check("N8 Vorgabe der Art: EK mit Alternativen, sonst LK; gesetzte Art bleibt",
          m.combinations["EK3"].art == "EK" and m.combinations["LK7"].art == "LK"
          and m.combinations["EK4"].art == "EK", str({n: c.art for n, c in m.combinations.items()}))
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_namen_n8_"), "m.json")
    m.save(pfad)
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    m2 = Model.load(pfad)
    felder = lambda mm: ([(lc.name, lc.nummer, lc.bezeichnung, lc.description)       # noqa: E731
                          for lc in mm.load_cases.values()],
                         [(c.name, c.nummer, c.art, c.bezeichnung, c.description, c.leading)
                          for c in mm.combinations.values()])
    check("N8 Speichern und Laden: bezeichnung, nummer und art gleich", felder(m2) == felder(m),
          str(felder(m2)))
    check("N8 Dateifassung bleibt 8", d.get("format") == 8, str(d.get("format")))

    # Alte Datei ohne die Felder (Fassung 8, 68db45b)
    alt_pfad = os.path.join(HIER, "daten", "fachbegriffe_68db45b", "modell.json")
    with open(alt_pfad, encoding="utf-8") as f:
        alt = json.load(f)
    ma = Model.from_dict(json.loads(json.dumps(alt)))
    arten = {n: c.art for n, c in ma.combinations.items()}
    check("N8 alte Datei: Art aus den Alternativen (GZT, Ermüdung EK, K1…K8 LK), Nummer 0, Bezeichnung leer",
          arten == {**{f"K{i}": "LK" for i in range(1, 9)}, "GZT": "EK", "Ermüdung": "EK"}
          and all(c.nummer == 0 and c.bezeichnung == "" for c in ma.combinations.values())
          and all(lc.bezeichnung == "" for lc in ma.load_cases.values()), str(arten))
    neu = ma.to_dict()
    for lc in neu["load_cases"]:
        lc.pop("bezeichnung", None)
    for c in neu["combinations"]:
        for k in ("nummer", "art", "bezeichnung", "erzeugt", "erzeugt_merkmal"):
            c.pop(k, None)
    check("N8 alte Datei lädt wie bisher: Lastfälle, Kombinationen, aktiver Lastfall gleich",
          neu["load_cases"] == alt["load_cases"] and neu["combinations"] == alt["combinations"]
          and neu["active_case"] == alt["active_case"],
          f"{len(neu['combinations'])} Kombinationen")


# --------------------------------------------------------------------------
# A1 Punkte 4 und 5: Anzeige und Sicherheitsnetz
# --------------------------------------------------------------------------
def test_anzeige_und_kollisionen():
    from statik3d.model import LoadCase
    from statik3d import begriffe as bg
    a_lf = getattr(bg, "anzeige_lastfall", None)
    a_k = getattr(bg, "anzeige_kombination", None)
    ok = a_lf is not None and a_k is not None
    if ok:
        lc = LoadCase("LF3")
        lc.bezeichnung = "W_links"
        c = Combination("LK7", {"LF3": 1.5}, "ULS")
        c.bezeichnung = "GZT"
        ok = (a_lf(lc) == "LF3 W_links" and a_k(c) == "LK7 GZT"
              and a_lf(LoadCase("LF4")) == "LF4" and a_k(Combination("EK2")) == "EK2")
    check("Anzeige „LF3 W_links“, „LK7 GZT“, ohne Bezeichnung nur der Name", ok)
    m = _kragarm()
    m.combinations["EK1"] = Combination("EK1", {}, "ULS", alternativen=[{"LF1": 1.0}, {"W": 1.0}])
    m.add_load_case("EK1 [2]", "Q", activate=False)
    fehler = [z for z in m.namenskollisionen() if "EK1 [2]" in z]
    check("Sicherheitsnetz: Lastfall „EK1 [2]“ neben der Ergebniskombination EK1 ist ein FEHLER",
          len(fehler) == 1 and fehler[0].startswith("FEHLER") and "Lastfall" in fehler[0], str(fehler))


# --------------------------------------------------------------------------
# N9 - Beispiele: der Generator nennt seine Kombinationen wie auf 36f8d8f
# --------------------------------------------------------------------------
#: sha256 ueber [Name, Typ, Faktoren, Leit, Beschreibung, Situation] aller
#: Kombinationen, gemessen auf 36f8d8f (scratchpad r2a1_kombi_digest.py)
KOMBINATIONEN_36F8D8F = {
    "hall": (72, "57ff9ee638c4d185a6d4fadf91a50da60da9235050d5cf7232dd40021af5a228"),
    "gate": (23, "4518df19b1dd40cf0fa48043526426a761775f31bbabcf350a49a71b06230cd6"),
}


def test_n9_beispiele():
    from statik3d.examples_lib import build_example
    for name, (n, digest) in KOMBINATIONEN_36F8D8F.items():
        m = build_example(name)
        zeilen = [[c.name, c.typ, sorted(c.factors.items()), c.leading, c.description, c.situation]
                  for c in m.combinations.values()]
        ist = hashlib.sha256(json.dumps(zeilen, ensure_ascii=True).encode()).hexdigest()
        check(f"N9 Beispiel {name}: {n} Kombinationen wie auf 36f8d8f (Namen, Faktoren, Leit)",
              len(zeilen) == n and ist == digest, f"{len(zeilen)}, {ist[:12]}")


# ==========================================================================
# Nachbesserung nach der Gegenpruefung von d58b8b7 (04.10.2026): G1 bis G5,
# F3, S3 und L4. Jede Pruefung schlug auf d58b8b7 fehl, ausser denen, die
# ausdruecklich als Kontrolle markiert sind (Rueckgaengig, Wiederholen).
# ==========================================================================
def _stand(m) -> str:
    """Die gespeicherte Form als Text, mit Reihenfolge - fuer „unverändert“."""
    return json.dumps(m.to_dict(), default=str)


def _rechnen_im_fenster(w, app, stellungen=True):
    """Rechnen wie „Berechnen“ und - mit ``stellungen`` - die Stellungsreihe
    samt ihrer Umhuellenden: alles, was ein Namenswechsel verwerfen muss."""
    an = solver.solve_all(w.model, design=True, fatigue=True)
    w._solve_done("all", an)
    app.processEvents()
    if stellungen:
        w.stellungen_rechnen()
        app.processEvents()
    return an


def _lf_dialog(G, w, alt, neu):
    from unittest import mock
    _Lastfalldialog.neuer_name = neu
    with mock.patch.object(G.dg, "LoadCaseDialog", _Lastfalldialog):
        w.lastfall_bearbeiten(alt)


def _lf_register(G, w, alt, neu):
    from unittest import mock
    w.model.active_case = alt
    _Lastfalldialog.neuer_name = neu
    with mock.patch.object(G, "LoadCaseDialog", _Lastfalldialog):
        w.edit_case()


def _k_dialog(G, w, alt, neu):
    from unittest import mock
    with mock.patch.object(G.dg, "CombinationDialog", _kombinationsdialog(neu)):
        w.kombination_bearbeiten(alt)


def _k_register(G, w, app, alt, neu):
    from unittest import mock
    w.refresh_all()
    app.processEvents()
    w.tbl_comb.setCurrentCell(list(w.model.combinations).index(alt), 0)
    with mock.patch.object(G, "CombinationDialog", _kombinationsdialog(neu)):
        w.edit_combination()


class _NeuerLastfall(_Lastfalldialog):
    """Attrappe „Lastfall hinzufügen…“: ein neuer Lastfall *neuer_name*."""
    def __init__(self, *_a, **_k):
        from statik3d.model import LoadCase
        self.lc = LoadCase("x", "Q", "neu")


def test_g1_ergebnisse_folgen():
    """A1-1: Umbenennen, Anlegen, Kopieren und Loeschen eines Lastfalls oder
    einer Kombination verwerfen Analyse, Stellungsreihe und die Umhuellende
    der Stellungen - auf jedem Weg so, wie die Maske es tut."""
    import importlib
    from unittest import mock
    from statik3d.model import Combination as K
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()

    class Auto(G.AutoCombinationDialog):
        def exec(self):
            return True

    class NeueKombination:
        def __init__(self, *_a, **_k):
            pass

        def exec(self):
            return True

        def result(self):
            return K("K9", {"LF1": 1.0}, "ULS", "neu")

    def neu_lastfall(name):
        def f():
            _NeuerLastfall.neuer_name = name
            with mock.patch.object(G, "LoadCaseDialog", _NeuerLastfall):
                w.add_case()
        return f

    def baum_neu(zweig, werte):
        def f():
            _aufraeumen(w, app)
            w._baum_neu(zweig)
            app.processEvents()
            mk = w.maskenrand.maske
            for k, v in werte.items():
                mk.setzen(k, v)
            mk.anwenden()
        return f

    def register_loeschen_kombination():
        w.refresh_all()
        app.processEvents()
        w.tbl_comb.setCurrentCell(list(w.model.combinations).index("K1"), 0)
        w.remove_combination()

    def kopieren():
        w.model.active_case = "W"
        w.copy_case()

    def loeschen_register():
        w.model.active_case = "LF3"
        w.remove_case()

    def auto():
        with mock.patch.object(G, "AutoCombinationDialog", Auto):
            w.auto_combinations()

    def neue_kombination():
        with mock.patch.object(G, "CombinationDialog", NeueKombination):
            w.add_combination()

    wege = [
        ("Maske Lastfall umbenennen", lambda: _maske_anwenden(w, app, "lastfall", "W", {"name": "LF9"})),
        ("Dialog Lastfall umbenennen", lambda: _lf_dialog(G, w, "W", "LF9")),
        ("Register Lastfall umbenennen", lambda: _lf_register(G, w, "W", "LF9")),
        ("Maske Kombination umbenennen", lambda: _maske_anwenden(w, app, "kombination", "K1", {"name": "LK7"})),
        ("Dialog Kombination umbenennen", lambda: _k_dialog(G, w, "K1", "LK7")),
        ("Register Kombination umbenennen", lambda: _k_register(G, w, app, "K1", "LK7")),
        ("Lastfall hinzufügen (Dialog)", neu_lastfall("W2")),
        ("Kombination hinzufügen (Dialog)", neue_kombination),
        ("Neu: Lastfall (Modellbaum)", baum_neu("lastfaelle", {})),
        ("Neu: Kombination (Modellbaum)", baum_neu("kombinationen", {"faktoren": "LF1: 1"})),
        ("Lastfall kopieren", kopieren),
        ("Lastfall löschen (Register)", loeschen_register),
        ("Lastfall löschen (Modellbaum)", lambda: w._baum_loeschen("lastfall", "LF3")),
        ("Kombination löschen (Register)", register_loeschen_kombination),
        ("Kombination löschen (Modellbaum)", lambda: w._baum_loeschen("kombination", "K1")),
        ("Alle Kombinationen löschen", lambda: w.clear_combinations()),
        ("Kombinationen erzeugen (EN 1990)", auto),
        ("Kombinationen nach DIN 19704", lambda: w.din19704_bilden()),
        ("Lastfälle nach DIN 19704", lambda: w._din19704_lastfaelle_anlegen({"e_G": True, "start": 0})),
    ]
    for text, weg in wege:
        _setzen(w, app, _modell())
        _rechnen_im_fenster(w, app)
        vorher = (w.analysis is not None, w.stellungsreihe is not None, w.umhuellende is not None)
        namen = (list(w.model.load_cases), list(w.model.combinations))
        fehler = ""
        try:
            weg()
            app.processEvents()
        except Exception as ex:      # noqa: BLE001
            fehler = repr(ex)
        geaendert = (list(w.model.load_cases), list(w.model.combinations)) != namen
        try:
            w._fill_result_selector()
            liste = [w.cb_result.itemText(i) for i in range(w.cb_result.count())]
        except Exception as ex:      # noqa: BLE001
            liste = [f"AUSNAHME {ex!r}"]
        check(f"G1 {text}: Analyse, Stellungsreihe und ihre Umhüllende verworfen, keine Ausnahme",
              all(vorher) and geaendert and not fehler and w.analysis is None
              and w.stellungsreihe is None and w.umhuellende is None and not liste,
              f"vorher {vorher}, geändert {geaendert}, {fehler[:60]} Analyse {w.analysis is not None}, "
              f"Reihe {w.stellungsreihe is not None}, Hülle {w.umhuellende is not None}, Liste {liste[:2]}")

    # Ein neu angelegter Lastfall „W“ nach dem Umbenennen zeigt keine Ergebnisse
    # seines Vorgaengers
    _setzen(w, app, _modell())
    _rechnen_im_fenster(w, app, stellungen=False)
    _lf_dialog(G, w, "W", "LF9")
    neu_lastfall("W")()
    app.processEvents()
    w._fill_result_selector()
    liste = [w.cb_result.itemText(i) for i in range(w.cb_result.count())]
    check("G1 neuer Lastfall „W“ nach dem Umbenennen: keine Ergebnisse des alten „W“",
          "W" in w.model.load_cases and w.analysis is None and not any("Lastfall W" in t for t in liste),
          str(liste[:3]))

    # Webwege: Analyse, Stellungsreihe und Umhuellende des Zustands
    from statik3d.web import State, apply_op
    webwege = [("add_case", {"name": "Q9", "category": "Q"}),
               ("edit_case", {"name": "W", "fields": {"new_name": "LF9"}}),
               ("copy_case", {"name": "W"}),
               ("remove_case", {"name": "LF3"}),
               ("add_combination", {"name": "K9", "factors": "LF1=1.0"}),
               ("remove_combination", {"name": "K1"}),
               ("clear_combinations", {}),
               ("auto_combinations", {}),
               ("din19704", {})]
    for op, d in webwege:
        m = _modell()
        st = State(m)
        # die Stellungen des Browsers haelt der Zustand, nicht das Modell
        st.stellungen = list(m.stellungen)
        apply_op(st, {"op": "stellungen_rechnen"})
        st.analysis = solver.solve_all(m)
        vorher = (st.analysis is not None, getattr(st, "stellungsreihe", None) is not None,
                  getattr(st, "umhuellende", None) is not None)
        try:
            apply_op(st, dict(d, op=op))
            fehler = ""
        except Exception as ex:      # noqa: BLE001
            fehler = repr(ex)
        check(f"G1 Web {op}: Analyse, Stellungsreihe und Umhüllende verworfen",
              all(vorher) and not fehler and st.analysis is None
              and getattr(st, "stellungsreihe", None) is None and getattr(st, "umhuellende", None) is None,
              f"vorher {vorher}, {fehler[:60]}, Reihe {getattr(st, 'stellungsreihe', None) is not None}")
    # Die Stellungen des Browsers stehen im Zustand, nicht im Modell: auch sie
    # folgen dem Umbenennen (sonst scheiterte die naechste Stellungsrechnung
    # mit „Lastfall 'W' gibt es im Modell nicht“)
    import copy
    m = _modell()
    st = State(m)
    st.stellungen = [copy.deepcopy(m.stellungen[0])]
    apply_op(st, {"op": "edit_case", "name": "W", "fields": {"new_name": "LF9"}})
    check("G1 Web edit_case: die Stellungen des Browsers folgen (W -> LF9)",
          st.stellungen[0].faelle == ["LF1", "LF9", "LF3"], str(st.stellungen[0].faelle))


def test_g1_ergebnisdatei():
    """A1-1, Teil Datei: nach dem Umbenennen gespeichert und geoeffnet - keine
    Ausnahme und keine Ergebnisse unter falschem Namen; ebenso eine aeltere
    Ergebnisdatei, deren Kombination danach im Modell umbenannt wurde."""
    import importlib
    from tests.meldungen import abfangen
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()
    ordner = tempfile.mkdtemp(prefix="statik3d_namen_g1_")

    def fremde_namen():
        an = w.analysis
        if an is None:
            return []
        return [k for k in an.combinations if k not in w.model.combinations] + \
            [k for k in an.cases if k not in w.model.load_cases]

    for text, weg in (("Dialog Kombination", lambda: _k_dialog(G, w, "K1", "LK7")),
                      ("Register Lastfall", lambda: _lf_register(G, w, "W", "LF9"))):
        p = os.path.join(ordner, f"{text.split()[0]}.json")
        _setzen(w, app, _modell())
        _rechnen_im_fenster(w, app, stellungen=False)
        w.path = p
        w.save_model()
        weg()
        app.processEvents()
        w.save_model()
        mel = abfangen(w)
        try:
            ok = w.modell_laden(p, fragen=False)
            fehler = ""
        except Exception as ex:      # noqa: BLE001
            ok, fehler = False, repr(ex)
        finally:
            mel.zurueck()
        app.processEvents()
        check(f"G1 Datei: {text} umbenannt, gespeichert, geöffnet - ohne Ausnahme, keine fremden Namen",
              ok and not fehler and not fremde_namen() and not mel.fehler,
              f"{fehler[:70]} fremd {fremde_namen()} Fehler {mel.fehler[:1]}")

    # Eine Ergebnisdatei, die vor dieser Nachbesserung neben eine umbenannte
    # Kombination geschrieben wurde: die Kombination heisst in der Datei
    # schon LK7, die Ergebnisse noch K1
    from statik3d.model import Model as M
    p = os.path.join(ordner, "alt.json")
    _setzen(w, app, _modell())
    _rechnen_im_fenster(w, app, stellungen=False)
    w.path = p
    w.save_model()
    m2 = M.load(p)
    m2.kombination_umbenennen("K1", "LK7")
    m2.save(p)
    try:
        ok = w.modell_laden(p, fragen=False)
        fehler = ""
    except Exception as ex:      # noqa: BLE001
        ok, fehler = False, repr(ex)
    app.processEvents()
    # das Oeffnen beginnt ein neues Protokoll (_protokoll_neu)
    log = w.log.toPlainText().splitlines()
    check("G1 ältere Ergebnisdatei mit Kombination K1 neben LK7 im Modell: nicht geladen, ohne Ausnahme",
          ok and not fehler and w.analysis is None
          and any("Ergebnisdatei nicht geladen" in z and "K1" in z for z in log),
          f"{fehler[:70]} Analyse {w.analysis is not None}, {[z for z in log if 'rgebnis' in z][:1]}")


def test_g2_offene_masken():
    """A1-2: offene Masken ziehen einen umbenannten Namen nach - Wind,
    Wasserdruck, Ermuedung, Stellung, Lastfilter; eine Maske, die es nicht
    kann, wird mit Hinweis geschlossen."""
    import importlib
    from statik3d.model import Section, Member
    from statik3d import wind as wm
    from statik3d.wind import Wind
    from tests.meldungen import abfangen
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()

    # Wind: Mast nach N5 mit offener Maske
    m = Model("Mast")
    m.add_material(Material("S"))
    m.add_section(Section.pipe("CHS", 0.2, 0.006))
    ids = [m.add_node(0, 0, i * 1.0) for i in range(7)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(6)]
    m.members["Mast"] = Member("Mast", el)
    m.fix(ids[0], "all")
    wm.lasten_erzeugen(m, Wind("W1", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    m.add_combination("K1", {"LF1": 1.0, "Wind W1": 1.5})
    _setzen(w, app, m)
    _aufraeumen(w, app)
    w.maske_wind("W1")
    app.processEvents()
    _lf_dialog(G, w, "Wind W1", "LF5")
    app.processEvents()
    mk = w.maskenrand.maske
    fall = mk.werte().get("fall") if mk is not None else None
    mel = abfangen(w)
    try:
        if mk is not None:
            mk.anwenden()
            app.processEvents()
    finally:
        mel.zurueck()
    m = w.model
    check("G2 Windmaske: das Feld Lastfall folgt (LF5), „Übernehmen“ legt keinen „Wind W1“ an",
          fall == "LF5" and list(m.load_cases) == ["LF1", "LF5"] and m.winde["W1"].lastfall == "LF5"
          and len(m.load_cases["LF5"].linienlasten) >= 1 and set(m.combinations["K1"].factors) == {"LF1", "LF5"},
          f"Feld {fall!r}, {list(m.load_cases)}, Meldungen {mel.alle[:1]}")

    # Wasserdruck: senkrechte Haut, Maske offen
    from statik3d.model import ShellProp, Flaeche
    from statik3d import wasserdruck as wdm
    from statik3d.wasserdruck import Wasserdruck
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.012))
    nx, nz = 2, 8
    kn = [[m.add_node(0.0, i * 3.0 / nx, k * 5.0 / nz) for k in range(nz + 1)] for i in range(nx + 1)]
    el = [m.add_element("shell4", [kn[i][k], kn[i + 1][k], kn[i + 1][k + 1], kn[i][k + 1]], "S", "t")
          for i in range(nx) for k in range(nz)]
    m.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    for k in range(nz + 1):
        m.fix(kn[0][k], "all")
        m.fix(kn[nx][k], "all")
    wdm.lasten_erzeugen(m, Wasserdruck("WD1", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                                       absenkung=False, verfahren="analytisch"))
    alt_fall = m.wasserdruecke["WD1"].lastfall
    _setzen(w, app, m)
    _aufraeumen(w, app)
    w.maske_wasserdruck("WD1")
    app.processEvents()
    _lf_dialog(G, w, alt_fall, "LF6")
    app.processEvents()
    mk = w.maskenrand.maske
    fall = mk.werte().get("fall") if mk is not None else None
    if mk is not None:
        mk.anwenden()
        app.processEvents()
    m = w.model
    check("G2 Wasserdruckmaske: das Feld Lastfall folgt (LF6), „Übernehmen“ legt den alten nicht an",
          fall == "LF6" and alt_fall not in m.load_cases and "LF6" in m.load_cases
          and m.wasserdruecke["WD1"].lastfall == "LF6",
          f"{alt_fall!r} -> Feld {fall!r}, {list(m.load_cases)}")

    # Ermuedungsmaske: der Editor folgt, „Übernehmen“ schreibt LF9
    _setzen(w, app, _modell())
    _aufraeumen(w, app)
    w.maske_ermuedungslasten(name="F_max")
    app.processEvents()
    _lf_dialog(G, w, "W", "LF9")
    app.processEvents()
    mk = w.maskenrand.maske
    werte = mk.werte() if mk is not None else {}
    r = mk.anwenden() if mk is not None else None
    app.processEvents()
    f = w.model.fatigue_loads["F_max"]
    check("G2 Ermüdungsmaske: der Editor zeigt LF9, „Übernehmen“ gelingt mit LF9",
          werte.get("oben") == "LF9" and r is not None and (f.case_max, f.case_min) == ("LF9", "LF1"),
          f"oben {werte.get('oben')!r}, Übernehmen {'gelungen' if r is not None else 'abgewiesen'}, "
          f"{(f.case_max, f.case_min)}")

    # Stellungsmaske: die angehakten Lastfaelle folgen
    _setzen(w, app, _modell())
    _aufraeumen(w, app)
    w._objektmaske("stellung", "S1")
    app.processEvents()
    _lf_dialog(G, w, "W", "LF9")
    app.processEvents()
    mk = w.maskenrand.maske
    if mk is not None:
        mk.anwenden()
        app.processEvents()
    st = w.model.stellungen[0]
    check("G2 Stellungsmaske: „Übernehmen“ nach dem Umbenennen schreibt LF9, nicht W",
          mk is not None and st.faelle == ["LF1", "LF9", "LF3"], f"{st.faelle}")

    # Kombinationsmaske K1: Faktoren und Formel folgen einem umbenannten Lastfall
    _setzen(w, app, _modell())
    _aufraeumen(w, app)
    w._objektmaske("kombination", "K1")
    app.processEvents()
    _lf_dialog(G, w, "W", "LF9")
    app.processEvents()
    mk = w.maskenrand.maske
    werte = mk.werte() if mk is not None and w.maskenrand.offen() else {}
    mel = abfangen(w)
    try:
        if werte:
            mk.anwenden()
            app.processEvents()
    finally:
        mel.zurueck()
    check("G2 Kombinationsmaske: Faktoren und Formel nennen LF9, „Übernehmen“ ohne Hinweis",
          "LF9:" in str(werte.get("faktoren", "")) and "W:" not in str(werte.get("faktoren", ""))
          and "·LF9" in str(werte.get("formel", "")) and not mel.alle
          and set(w.model.combinations["K1"].factors) == {"LF1", "LF9", "LF3"},
          f"{werte.get('faktoren')!r} | {werte.get('formel')!r} | {mel.alle[:1]}")

    # Lastfilter
    _setzen(w, app, _modell())
    _aufraeumen(w, app)
    w._lasten_fuellen()
    w.cb_lastfilter.setCurrentText("W")
    w._lasten_fuellen()
    _lf_dialog(G, w, "W", "LF9")
    app.processEvents()
    check("G2 Lastfilter folgt dem Umbenennen (W -> LF9)", w.cb_lastfilter.currentText() == "LF9",
          repr(w.cb_lastfilter.currentText()))

    # Masken, die nicht folgen koennen: geschlossen, mit Hinweis
    for text, oeffnen, weg, alt in (
            ("Maske Lastfall W, Register benennt W um",
             lambda: w._objektmaske("lastfall", "W"), lambda: _lf_register(G, w, "W", "LF9"), "W"),
            ("Maske Kombination K1, Dialog benennt K1 um",
             lambda: w._objektmaske("kombination", "K1"), lambda: _k_dialog(G, w, "K1", "LK7"), "K1")):
        _setzen(w, app, _modell())
        _aufraeumen(w, app)
        oeffnen()
        app.processEvents()
        mel = abfangen(w)
        try:
            weg()
            app.processEvents()
        finally:
            mel.zurueck()
        offen = w.maskenrand.maske is not None and w.maskenrand.offen()
        check(f"G2 {text}: Maske geschlossen, Hinweis nennt „{alt}“",
              not offen and mel.hinweis_mit(f"„{alt}“", "geschlossen") and not mel.fehler,
              f"offen {offen}, {mel.alle[:1]}")


def test_g3_anlegen_kopieren():
    """A1-3: kein Weg legt an oder kopiert an der Namenspruefung vorbei, die
    Nummer kommt aus naechste_nummer, nichts wird still ueberschrieben, eine
    Kopie erbt keine Nummer."""
    import importlib
    from unittest import mock
    from statik3d.web import State, OPS, ApiError
    from statik3d.gui import dialogs as dg
    from tests.meldungen import abfangen
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()

    # GUI: Kopieren neben einer Kombination „W_Kopie“ und einem Lastfall „W_Kopie 2“
    m = _modell()
    m.load_cases["W"].nummer = 5
    m.add_combination("W_Kopie", {"LF1": 1.0}, "ULS", "von Hand")
    m.add_load_case("W_Kopie 2", "Q", "eigener", activate=False)
    _setzen(w, app, m)
    m = w.model
    frei = m.naechste_nummer("LF")
    vorher = dict(m.load_cases)
    m.active_case = "W"
    w.copy_case()
    app.processEvents()
    neu = [n for n in m.load_cases if n not in vorher]
    check("G3 GUI Kopieren: freier Name, nichts überschrieben, keine geerbte Nummer",
          len(neu) == 1 and neu[0] not in ("W_Kopie", "W_Kopie 2") and not m.namenskollisionen()
          and m.combinations["W_Kopie"].factors == {"LF1": 1.0}
          and m.load_cases["W_Kopie 2"].description == "eigener"
          and m.load_cases[neu[0]].nummer == frei,
          f"{neu}, Nr. {m.load_cases[neu[0]].nummer if neu else '-'} (frei {frei}), {m.namenskollisionen()[:1]}")

    # GUI: Vorschlag „Lastfall hinzufügen…“ = naechste freie Nummer
    m = Model()
    m.add_load_case("LF3", "Q", activate=False)
    _setzen(w, app, m)
    erfasst = []

    class Vorschlag(dg.LoadCaseDialog):
        def exec(self):
            erfasst.append(self.name.text())
            return False
    with mock.patch.object(G, "LoadCaseDialog", Vorschlag):
        w.add_case()
    check("G3 „Lastfall hinzufügen…“ schlägt die nächste freie Nummer vor (LF4, nicht LF3)",
          erfasst == ["LF4"], str(erfasst))
    _NeuerLastfall.neuer_name = "LF8"
    with mock.patch.object(G, "LoadCaseDialog", _NeuerLastfall):
        w.add_case()
    lc = w.model.load_cases.get("LF8")
    check("G3 „Lastfall hinzufügen…“ LF8: Nummer aus dem Namen (8)", lc is not None and lc.nummer == 8,
          f"Nr. {lc and lc.nummer}")

    # Web: anlegen, kopieren, Kombination anlegen
    def web(op, d, m):
        st = State(m)
        try:
            OPS[op](st, m, d)
            return ""
        except (ApiError, ValueError) as ex:
            return str(ex)

    for text, op, d, im in (("add_case „K1“ (Name einer Kombination)", "add_case", {"name": "K1"}, "K1"),
                            ("add_case „EK1 [2]“", "add_case", {"name": "EK1 [2]"}, "Alternative"),
                            ("copy_case W -> „K1“", "copy_case", {"name": "W", "new": "K1"}, "K1"),
                            ("add_combination „W“", "add_combination", {"name": "W", "factors": "LF1=1"}, "W"),
                            ("add_combination „K1“ (vorhanden)", "add_combination",
                             {"name": "K1", "factors": "LF1=1"}, "K1")):
        m = _modell()              # je Zeile frisch: eine angenommene stoert die naechste nicht
        s0 = _stand(m)
        meldung = web(op, d, m)
        check(f"G3 Web {text}: abgewiesen mit Text, Modell unverändert",
              meldung and im in meldung and _stand(m) == s0, meldung[:80] or "angenommen")
    m = _modell()
    m.load_cases["W"].nummer = 5
    frei = m.naechste_nummer("LF")
    meldung = web("copy_case", {"name": "W"}, m)
    kopie = [n for n in m.load_cases if n not in ("LF1", "W", "LF3")]
    check("G3 Web copy_case W: freier Name, Nummer nicht geerbt",
          not meldung and len(kopie) == 1 and m.load_cases[kopie[0]].nummer == frei,
          f"{meldung} {kopie} Nr. {[m.load_cases[k].nummer for k in kopie]} (frei {frei})")
    meldung = web("add_case", {"name": "LF7"}, m)
    check("G3 Web add_case LF7: Nummer 7", not meldung and m.load_cases["LF7"].nummer == 7,
          meldung or f"Nr. {m.load_cases['LF7'].nummer}")
    meldung = web("add_combination", {"name": "LK5", "factors": "LF1=1.35"}, m)
    c = m.combinations.get("LK5")
    check("G3 Web add_combination LK5: Art LK, Nummer 5", not meldung and c is not None
          and c.art == "LK" and c.nummer == 5, meldung or f"{c and (c.art, c.nummer)}")

    # DIN 19704: Handkombination „DIN LF1“ bleibt, der Generator nimmt einen freien Namen
    from statik3d.bridges.din19704 import Regelwerk
    from statik3d.bridges import lastenheft as lh
    m = Model("DIN")
    lh.lastfaelle_anlegen(m, ["G", "W_S", "W"])
    m.add_combination("DIN LF1.1", {"G": 9.9}, "ULS", "von Hand")
    rw = Regelwerk()
    namen = rw.kombinationen(m)
    hand = m.combinations["DIN LF1.1"]
    check("G3 DIN 19704: Handkombination bleibt, erzeugte heißen frei, keine Kollision",
          hand.factors == {"G": 9.9} and hand.description == "von Hand" and "DIN LF1.1" not in namen
          and len(set(namen)) == len(namen) and not m.namenskollisionen()
          and all(m.combinations[n].nummer > 0 for n in namen)
          and len({m.combinations[n].nummer for n in namen}) == len(namen),
          f"{namen[:4]}, Nummern {[m.combinations[n].nummer for n in namen][:4]}")
    n_vorher = len(m.combinations)
    rw.kombinationen(m)
    check("G3 DIN 19704 erneut: ersetzt nur die eigenen, keine Verdopplung, Hand bleibt",
          len(m.combinations) == n_vorher and m.combinations["DIN LF1.1"].factors == {"G": 9.9},
          f"{n_vorher} -> {len(m.combinations)}")

    # Wind, Wasserdruck, Lastenheft mit ausdruecklicher Nummer oder belegtem Namen
    from statik3d.model import Section, Member, NameVergeben
    from statik3d import wind as wm
    from statik3d.wind import Wind

    def mast():
        mm = Model("Mast")
        mm.add_material(Material("S"))
        mm.add_section(Section.pipe("CHS", 0.2, 0.006))
        kn = [mm.add_node(0, 0, i * 1.0) for i in range(4)]
        mm.members["Mast"] = Member("Mast", [mm.add_element("beam", [kn[i], kn[i + 1]], "S", "CHS")
                                             for i in range(3)])
        mm.fix(kn[0], "all")
        return mm
    for text, aufbau, im in (
            ("Wind mit Lastfall-Nr. 1 (gehört LF1)",
             lambda mm: Wind("W1", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"], lastfall_nr=1),
             "Nr. 1"),
            ("Wind, dessen gewählter Lastfall wie eine Kombination heißt",
             lambda mm: (mm.add_combination("Wind W1", {"LF1": 1.0}), Wind("W1", zone=3, profil="II",
                                                                         richtung=[1, 0, 0], staebe=["Mast"],
                                                                         lastfall="Wind W1"))[1],
             "Wind W1")):
        mm = mast()
        wd = aufbau(mm)
        s0 = _stand(mm)
        try:
            wm.lasten_erzeugen(mm, wd)
            meldung = ""
        except NameVergeben as ex:
            meldung = str(ex)
        check(f"G3 {text}: abgewiesen (NameVergeben), Modell unverändert",
              im in meldung and _stand(mm) == s0, meldung[:80] or "angenommen")
    # ohne eigene Wahl: der Vorschlag „Wind W1“ ist als Kombination vergeben -
    # ein freier Name, die Kombination bleibt
    mm = mast()
    mm.add_combination("Wind W1", {"LF1": 1.0}, "ULS", "von Hand")
    kw = wm.lasten_erzeugen(mm, Wind("W1", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"]))
    check("G3 Wind ohne eigene Wahl neben einer Kombination „Wind W1“: freier Name, Kombination bleibt",
          kw["lastfall"] != "Wind W1" and kw["lastfall"] in mm.load_cases
          and mm.combinations["Wind W1"].factors == {"LF1": 1.0} and not mm.namenskollisionen(),
          str(kw["lastfall"]))
    # Wasserdruck mit eingetragener Nummer, die LF1 gehoert
    from statik3d.model import ShellProp, Flaeche
    from statik3d import wasserdruck as wdm
    from statik3d.wasserdruck import Wasserdruck
    mm = Model("Schütz")
    mm.add_material(Material("S"))
    mm.add_shell_prop(ShellProp("t", 0.012))
    kn = [[mm.add_node(0.0, i * 1.5, k * 1.25) for k in range(5)] for i in range(3)]
    el = [mm.add_element("shell4", [kn[i][k], kn[i + 1][k], kn[i + 1][k + 1], kn[i][k + 1]], "S", "t")
          for i in range(2) for k in range(4)]
    mm.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    s0 = _stand(mm)
    try:
        wdm.lasten_erzeugen(mm, Wasserdruck("WD1", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                                            absenkung=False, verfahren="analytisch", lastfall_nr=1))
        meldung = ""
    except NameVergeben as ex:
        meldung = str(ex)
    check("G3 Wasserdruck mit Lastfall-Nr. 1 (gehört LF1): abgewiesen (NameVergeben), Modell unverändert",
          "Nr. 1" in meldung and _stand(mm) == s0, meldung[:80] or "angenommen")
    mm = Model()
    s0 = _stand(mm)
    try:
        lh.lastfaelle_anlegen(mm, ["G", "W_S"], start_nr=1)
        meldung = ""
    except NameVergeben as ex:
        meldung = str(ex)
    check("G3 Lastenheft ab Nr. 1 (gehört LF1): abgewiesen, Modell unverändert",
          "Nr. 1" in meldung and _stand(mm) == s0, meldung[:80] or "angenommen")
    mm = Model()
    mm.add_combination("G", {"LF1": 1.0}, "ULS", "von Hand")
    neu = lh.lastfaelle_anlegen(mm, ["G"])
    check("G3 Lastenheft neben einer Kombination „G“: freier Name, Kombination bleibt",
          len(neu) == 1 and neu[0] != "G" and mm.combinations["G"].factors == {"LF1": 1.0}
          and not mm.namenskollisionen(), str(neu))
    # GUI: „Lastfälle nach DIN 19704“ mit belegter Nummer - ein Hinweis
    _setzen(w, app, Model())
    mel = abfangen(w)
    s0 = _stand(w.model)
    try:
        w._din19704_lastfaelle_anlegen({"e_G": True, "start": 1})
    finally:
        mel.zurueck()
    check("G3 GUI „Lastfälle nach DIN 19704“ ab Nr. 1: Hinweis, Modell unverändert",
          mel.hinweis_mit("Nr. 1") and not mel.fehler and _stand(w.model) == s0, str(mel.alle[:1]))


def test_g4_nummern_namensformen():
    """A1-4: eine Nummer gehoert genau einem Objekt seiner Art; Namen, die
    sich nur in Gross/Klein, Leerzeichen oder fuehrenden Nullen unterscheiden,
    sind derselbe Name."""
    def bau():
        mm = _kragarm()
        mm.load_cases["LF3"].nummer = 7
        mm.add_combination("K1", {"LF1": 1.0}, "ULS")
        mm.combinations["EK1"] = Combination("EK1", {}, "ULS", alternativen=[{"LF1": 1.0}, {"W": 1.0}])
        return mm
    for neu, im in (("LF7", "7"), ("LF 3", "LF3"), ("LF03", "LF3"), ("lf1", "LF1"), ("LF1 ", "Leerzeichen"),
                    ("k1", "K1"), ("ek1 [2]", "Alternative"), ("EK1  [2]", "Alternative")):
        m = bau()
        s0 = _stand(m)
        try:
            m.lastfall_umbenennen("W", neu)
            meldung = ""
        except ValueError as ex:
            meldung = str(ex)
        check(f"G4 Lastfall W -> „{neu}“: abgewiesen, Modell unverändert",
              meldung and im in meldung and _stand(m) == s0, meldung[:80] or "angenommen")
    m = bau()
    try:
        m.lastfall_umbenennen("W", "LF8")
        meldung = ""
    except ValueError as ex:
        meldung = str(ex)
    check("G4 Kontrolle (bestand schon vorher): „LF8“ ist frei und wird angenommen", not meldung and "LF8" in m.load_cases, meldung)
    # Eine Datei mit doppelter Nummer laedt und warnt
    d = _kragarm().to_dict()
    for lc in d["load_cases"]:
        if lc["name"] in ("W", "LF3"):
            lc["nummer"] = 2
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    zeilen = [z for z in m2.check() if "Nr. 2" in z]
    check("G4 Datei mit doppelter Nr. 2 (W und LF3) lädt und warnt (WARNUNG, kein FEHLER)",
          len(zeilen) == 1 and zeilen[0].startswith("WARNUNG") and "W" in zeilen[0] and "LF3" in zeilen[0]
          and not [z for z in m2.check() if z.startswith("FEHLER") and "Nr." in z], str(zeilen))
    m3 = _kragarm()
    m3.load_cases["LF3"].nummer = 7
    m3.add_load_case("LF7", "Q", activate=False)
    zeilen = [z for z in m3.check() if "Nr. 7" in z]
    check("G4 LF3 mit Nr. 7 neben „LF7“: WARNUNG", len(zeilen) == 1 and zeilen[0].startswith("WARNUNG"),
          str(zeilen))


def test_g5_generator_besitz():
    """A1-5: der Generator ersetzt nur, was er selbst erzeugt hat und was
    niemand angefasst hat; eine umbenannte oder geaenderte erzeugte
    Kombination gehoert dem Anwender."""
    from statik3d.combinations import generate_combinations
    m = _kragarm()
    erzeugt = generate_combinations(m)
    n0 = len(m.combinations)
    erste = erzeugt[0].name
    faktoren = dict(m.combinations[erste].factors)
    m.fatigue_loads["F"] = FatigueLoad("F", erste, None, cycles=1e5)
    m.kombination_umbenennen(erste, "LK50")
    zweite = erzeugt[1].name
    doppelt = {k: 2 * v for k, v in m.combinations[zweite].factors.items()}
    m.combinations[zweite].factors = dict(doppelt)
    generate_combinations(m)
    lk = m.combinations.get("LK50")
    check("G5 umbenannte erzeugte Kombination LK50 bleibt, die Ermüdung findet sie",
          lk is not None and lk.factors == faktoren and m.fatigue_loads["F"].case_max == "LK50"
          and not [z for z in m.check() if "unbekannt" in z], f"{lk and lk.factors}")
    check("G5 von Hand geänderte erzeugte Kombination bleibt",
          zweite in m.combinations and m.combinations[zweite].factors == doppelt,
          f"{zweite}: {m.combinations.get(zweite) and m.combinations[zweite].factors}")
    check("G5 die übrigen erzeugten werden ersetzt, nicht verdoppelt (zwei Anwender-Kombinationen mehr)",
          len(m.combinations) == n0 + 2, f"{n0} -> {len(m.combinations)}")
    # Ein umbenannter Lastfall macht eine erzeugte Kombination nicht zur eigenen
    m = _kragarm()
    generate_combinations(m)
    n0 = len(m.combinations)
    m.lastfall_umbenennen("W", "LF9")
    generate_combinations(m)
    check("G5 Kontrolle (bestand schon vorher): Lastfall umbenannt, erneut erzeugt: keine Verdopplung",
          len(m.combinations) == n0 and all("W" not in c.factors for c in m.combinations.values()),
          f"{n0} -> {len(m.combinations)}")


def test_s3_bericht_f3_art():
    """A1-6: eingefrorene Texte folgen nur dem Klartext der Quelle
    („Lastfall W“), kein ganzes Wort mehr („W-Richtung“ bleibt); Docstring und
    Handbuch beschreiben den Stand der Art LK/EK bis C2."""
    m = _kragarm()
    m.bericht += [Berichtseintrag("Bild W", "case:W", "u", beschriftung="W-Richtung, Bild W"),
                  Berichtseintrag("Bild 2", "case:W", "u", beschriftung="Lastfall W · u")]
    m.lastfall_umbenennen("W", "LF9")
    b = m.bericht
    check("S3 „W-Richtung, Bild W“ bleibt, „Lastfall W · u“ folgt, Quelle folgt immer",
          b[0].beschriftung == "W-Richtung, Bild W" and b[0].name == "Bild W"
          and b[1].beschriftung == "Lastfall LF9 · u" and [e.quelle for e in b] == ["case:LF9"] * 2,
          f"{b[0].beschriftung!r} {b[0].name!r} {b[1].beschriftung!r}")
    doc = Combination.__doc__ or ""
    with open(os.path.join(os.path.dirname(HIER), "docs", "Benutzerhandbuch.md"), encoding="utf-8") as f:
        hb = f.read()
    check("F3 Docstring und Handbuch: RFEM-Import mit einer Alternative speichert bis C2 die Art LK",
          "C2" in doc and "Fassung" in doc and "bis zum Paket C2" in hb, "")


def test_l4_rueckgaengig_und_ek():
    """L4: Rueckgaengig und Wiederholen nach jedem Umbenennweg (Kontrolle: das
    Umbenennen aendert die gespeicherte Form wirklich), und eine
    Ergebniskombination ueber die Oberflaeche."""
    import importlib
    G = importlib.import_module("statik3d.gui.main")
    w, app = _fenster()
    wege = [("Maske Lastfall", lambda: _maske_anwenden(w, app, "lastfall", "W", {"name": "LF9"})),
            ("Dialog Lastfall", lambda: _lf_dialog(G, w, "W", "LF9")),
            ("Register Lastfall", lambda: _lf_register(G, w, "W", "LF9")),
            ("Maske Kombination", lambda: _maske_anwenden(w, app, "kombination", "K1", {"name": "LK7"})),
            ("Dialog Kombination", lambda: _k_dialog(G, w, "K1", "LK7")),
            ("Register Kombination", lambda: _k_register(G, w, app, "K1", "LK7"))]
    for text, weg in wege:
        _setzen(w, app, _modell())
        s0 = _stand(w.model)
        weg()
        app.processEvents()
        s1 = _stand(w.model)
        w.undo()
        app.processEvents()
        s2 = _stand(w.model)
        w.redo()
        app.processEvents()
        s3 = _stand(w.model)
        check(f"L4 Kontrolle (bestand schon vorher) {text}: Rückgängig und Wiederholen exakt, umbenannt",
              s1 != s0 and s2 == s0 and s3 == s1, f"geändert {s1 != s0}, zurück {s2 == s0}, wieder {s3 == s1}")
    for text, weg in (("Maske", lambda: _maske_anwenden(w, app, "kombination", "EK1", {"name": "EK5"})),
                      ("Dialog", lambda: _k_dialog(G, w, "EK1", "EK5")),
                      ("Register", lambda: _k_register(G, w, app, "EK1", "EK5"))):
        _setzen(w, app, _modell())
        _rechnen_im_fenster(w, app, stellungen=False)
        ek = w.model.combinations["EK1"]
        alternativen = [dict(a) for a in ek.alternativen]
        weg()
        app.processEvents()
        c = w.model.combinations.get("EK5")
        b = w.model.bericht
        kontrolle = " (Kontrolle, bestand schon vorher)" if text == "Maske" else ""
        check(f"L4 Ergebniskombination über {text}{kontrolle}: dasselbe Objekt, Alternativen, Art EK, "
              "Bild env:EK5, "
              "Analyse verworfen",
              c is ek and c.alternativen == alternativen and c.art == "EK"
              and c.bemessungssituation == "GZT (STR/GEO) - ständig" and b[4].quelle == "env:EK5"
              and w.analysis is None,
              f"{c is ek}, {c and c.art}, {b[4].quelle}, Analyse {w.analysis is not None}")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_n1_lastfall_umbenennen, test_n2_kombination_umbenennen, test_n3_vergebener_name,
              test_n4_oberflaeche, test_n5_wind_nach_umbenennen, test_n6_generator_ueberschreibt_nicht,
              test_n7_nummernvergabe, test_n8_speichern_laden, test_anzeige_und_kollisionen,
              test_n9_beispiele, test_g1_ergebnisse_folgen, test_g1_ergebnisdatei, test_g2_offene_masken,
              test_g3_anlegen_kopieren, test_g4_nummern_namensformen, test_g5_generator_besitz,
              test_s3_bericht_f3_art, test_l4_rueckgaengig_und_ek):
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
