"""Zusammenfuehrung vom 14.10.2026 (integ/gesamt): was zwei Zweige je fuer
sich gebaut hatten, gibt es nur noch einmal.

* Werkstoffart Spannstahl: nur ``Material.art`` (plast/verfestigung). Bis
  dahin kennzeichnete der RFEM-Import Spannstahl fuer die Vorspannkraft
  zusaetzlich in ``model.meta["spannstahl"]``, und der Vorschlag der Sollkraft
  (0,9·f_p0,1k·A) erkannte ihn daran oder am Werkstoffnamen - der
  Stabnachweis aber an ``Material.art``.
* Vorspannung als Last: ein Merkmal und eine Anzeige. Bis dahin nannte die
  Vorspannkraft eine als Temperatur stehende Vorspannung „aus Vorspannung
  952 kN, E = …, α = …“ (``TempLoad.vorspanntext``), der Import dieselbe Last
  „Vorspannung 952 kN (eingeprägte Dehnung, E = …, α = …)“
  (``TempLoad.vorspann_text``). Jetzt steht beides in der Form des Imports.
* Stabenden an 1-3 Knoten: am Rechenstart eine Warnung statt zwei (die
  netzabhaengige Spitze aus spitzenstellen und der Hinweis auf die
  verteilende Einleitung aus stabeinleitung).

Aufruf:  python -m tests.test_zusammenfuehrung
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Material, Model, Section, TempLoad   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:80s} {detail}")
    return ok


SATZ = "Vorspannung 952 kN (eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K)"


def _anker(name="Anker St 835/1030", art=""):
    """Ein Zugstab Rund 40 (Spannstahl-Kennwerte) mit Stabname A1."""
    m = Model()
    m.add_material(Material(name, E=170e9, nu=0.3, rho=7850.0, alpha=1e-5, fy=835e6, fu=1030e6, art=art))
    m.add_section(Section.circle("Rund 40", 0.04))
    a, b = m.add_node(0.0, 0.0, 0.0), m.add_node(0.0, 0.0, 3.0)
    e = m.add_element("truss", [a, b], name, "Rund 40")
    m.add_member("A1", [e])
    return m, e


def test_spannstahl_art():
    print("\n--- Werkstoffart Spannstahl: nur Material.art ---")
    from statik3d import vorspannkraft as vk
    from statik3d.ec3 import spannstahl as sp
    from statik3d.importers import rfem6_db as R6
    from tests.test_spannstahl import _rf6_spannstahl
    tmp = tempfile.mkdtemp()
    try:
        m = R6.read_rf6(_rf6_spannstahl(os.path.join(tmp, "anker.rf6")), log=[])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    mat = list(m.materials.values())[0]
    check("Import Typ 15: Werkstoffart Spannstahl am Werkstoff", getattr(mat, "art", "") == "Spannstahl",
          repr(getattr(mat, "art", None)))
    check("… und keine zweite Kennzeichnung in model.meta[\"spannstahl\"]",
          "spannstahl" not in (m.meta or {}), str((m.meta or {}).get("spannstahl")))
    A = 0.04 ** 2 * 3.141592653589793 / 4
    m1, _e = _anker(art="Spannstahl")
    soll = 0.9 * 835e6 * A
    v1 = vk.vorschlag_sollkraft(m1, "A1", 952e3)
    check("art = Spannstahl: Vorschlag 0,9·f_p0,1k·A", abs(v1 - soll) <= 1e-6 * soll,
          f"{v1 / 1e3:.3f} kN, soll {soll / 1e3:.3f} kN")
    m2, _e = _anker(name="Spannstahl St 835/1030", art="")
    v2 = vk.vorschlag_sollkraft(m2, "A1", 952e3)
    check("nur der Name sagt Spannstahl, die Art nicht: Vorschlag ist der RFEM-Wert",
          abs(v2 - 952e3) < 1e-6, f"{v2 / 1e3:.3f} kN")
    gleich = all(vk.ist_spannstahl(mm, n) == sp.ist_spannstahl(mm.materials[n])
                 for mm in (m1, m2) for n in mm.materials)
    check("Vorspannkraft und Stabnachweis sagen dasselbe, was Spannstahl ist", gleich)


def test_vorspannung_ein_merkmal():
    print("\n--- Vorspannung als Last: ein Merkmal, eine Anzeige ---")
    m, e = _anker(name="Material 3", art="Spannstahl")
    A = m.sections["Rund 40"].A
    dT = -952e3 / (170e9 * A * 1e-5)
    fall = m.active_case
    # wie der Import seit dem 13.10.2026: mit gespeichertem Merkmal
    m.load_temp(e, dT, case=fall, aus_vorspannung=952e3, vorspann_E=170e9, vorspann_alpha=1e-5)
    # wie eine Datei, die vor dem 13.10.2026 aus RFEM kam: nur die Temperatur
    m.load_temp(e, dT, case=fall)
    neu, alt = m.case(fall).temp_loads
    check("gespeichertes Merkmal: der Satz des Imports", neu.vorspann_text(m) == SATZ, neu.vorspann_text(m))
    check("nur die Temperatur (Datei von vorher): derselbe Satz", alt.vorspann_text(m) == SATZ,
          alt.vorspann_text(m))
    check("… Kraft und Umrechnung einzeln wie beim Import",
          alt.vorspann_kraft_text(model=m) == "952 kN"
          and alt.vorspann_umrechnung_text(model=m) == "eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K",
          f"{alt.vorspann_kraft_text(model=m)} | {alt.vorspann_umrechnung_text(model=m)}")
    check("ohne Modell: nur das gespeicherte Merkmal", neu.vorspann_text() == SATZ and alt.vorspann_text() == "",
          f"{neu.vorspann_text()!r} / {alt.vorspann_text()!r}")
    b_neu, b_alt = neu.bezug(m), alt.bezug(m)
    check("Bezug mit Merkmal: nur die Kraft", b_neu == f"Element {e}: {SATZ}", b_neu)
    check("Bezug ohne Merkmal: ΔT und dahinter derselbe Satz",
          b_alt == f"Element {e}: ΔT = {dT:+.1f} K → {SATZ}", b_alt)
    check("die alte Form „aus Vorspannung …, E = …“ gibt es nicht mehr",
          "aus Vorspannung" not in b_alt and not hasattr(TempLoad, "vorspanntext"))
    m3, e3 = _anker()
    m3.elements[e3].typ = "beam"
    balken = TempLoad(e3, 20.0)
    check("eine gewöhnliche Temperatur an einem Balken bleibt eine Temperatur",
          balken.vorspann_text(m3) == "" and balken.bezug(m3) == f"Element {e3}: ΔT = +20.0 K",
          balken.bezug(m3))
    from statik3d import vorspannkraft as vk
    log = []
    vk.import_hinweise(m, log=log)
    zeilen = [z for z in log if "als ΔT gerechnet" in z]
    check("Importhinweis der Umwandlung nennt die Vorspannung in derselben Form",
          zeilen and "als ΔT gerechnet: Vorspannung 952 kN (eingeprägte Dehnung" in zeilen[0], str(zeilen[:1]))


def test_stabenden_eine_warnung():
    print("\n--- Stabenden an 1-3 Knoten: eine Warnung am Rechenstart ---")
    from statik3d import diagnose, fugen, spitzenstellen
    from statik3d import stabeinleitung as SE
    from tests.test_stabeinleitung import lagern_frei, quader, zugstab
    m = quader(h=0.01)
    lagern_frei(m)
    zugstab(m)
    fugen.stabenden_koppeln(m, [])
    bef = diagnose.abnahme(m, warnungen=True)
    stab = [b for b in bef if (b.pruefung == spitzenstellen.PRUEFUNG and b.objekt == spitzenstellen.STABENDE)
            or b.pruefung == SE.PRUEFUNG]
    for b in stab:
        print(f"       {b.pruefung}: {b.text}")
    check("eine Warnung für das Stabende, nicht zwei", len(stab) == 1, f"{len(stab)} Warnungen")
    t = stab[0].text if stab else ""
    check("… sie nennt die mögliche netzabhängige Spannungsspitze",
          "Stabende hängt an" in t and "mögliche netzabhängige Spannungsspitzen" in t, t[:120])
    check("… und den Ausweg, die verteilende Einleitung",
          "Verteilende Einleitung über die Stirnfläche möglich (Modelleinstellung oder je Stabende)" in t, t[-120:])
    check("… als WARNUNG, die nichts anhält", stab and stab[0].stufe == "WARNUNG")


def test_alte_ergebnisdatei_gamma_p():
    print("\n--- Eine Ergebnisdatei von vor gamma_P passt weiter ---")
    # import/lastfaelle legte DesignSettings.gamma_P (Vorgabe 1,0) an; „design“
    # zaehlt in der Rechenkennung (Rechenart und Einstellungen). Gemessen am
    # 14.10.2026: jede Ergebnisdatei, die 46755cc geschrieben hatte (Ankerplatte,
    # Wuerfel mit Vorspannung, kragarm_alt, ohne_kollision), wies integ/gesamt
    # ab - wie am 13.10.2026 plastizitaet.abbruch (65760f6).
    from statik3d import ergebnisse
    m, _e = _anker(art="Spannstahl")
    echt = Model.to_dict

    def wie_vorher(self, *a, **k):
        d = echt(self, *a, **k)
        d.get("design", {}).pop("gamma_P", None)
        return d
    Model.to_dict = wie_vorher
    try:
        k_alt = ergebnisse.kennung(m)           # wie das Programm vor dem 13.10.2026
    finally:
        Model.to_dict = echt
    ok, grund = ergebnisse.passt(k_alt, m)
    check("eine Ergebnisdatei ohne gamma_P passt weiter zum Modell (Vorgabe 1,0)", ok and not grund, grund)
    m.design.gamma_P = 1.35
    ok, grund = ergebnisse.passt(k_alt, m)
    check("… mit gamma_P = 1,35 gilt das Modell als geändert (Rechenart und Einstellungen)",
          not ok and "Rechenart und Einstellungen" in grund, grund)


def test_alte_datei_bitgleich():
    print("\n--- Eine Datei von vor den neuen Feldern bleibt beim Speichern bitgleich ---")
    # vorspannung/kraft prueft das an einer Datei vom Stand 192317a; nach dem
    # Zusammenfuehren schrieb das Speichern dort die Felder vom 13.10.2026 mit
    # ihrer Vorgabe dazu (Werkstoff verfestigung, art, nachweis_ausnehmen, Ep,
    # sigma_pmax, sigma_pm0; Querschnitt A_s, gewinde; design.gamma_P).
    import json
    pa = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                      "vorspannung_alt_192317a", "anker_dT_und_Fv.json")
    tmp = tempfile.mkdtemp()
    try:
        pb = os.path.join(tmp, "neu.json")
        Model.load(pa).save(pb)
        with open(pa, "rb") as f1, open(pb, "rb") as f2:
            a, b = f1.read(), f2.read()
        check("alte Datei: Laden und Speichern bitgleich", a == b, f"{len(a)} / {len(b)} Byte")
        m, _e = _anker(art="Spannstahl")
        mat = next(iter(m.materials.values()))
        mat.verfestigung, mat.nachweis_ausnehmen, mat.Ep, mat.sigma_pmax = 1e-4, True, 205e9, 780e6
        sec = m.sections["Rund 40"]
        sec.A_s, sec.gewinde = 1150e-6, "aufgewalzt"
        m.design.gamma_P = 1.35
        pc = os.path.join(tmp, "gesetzt.json")
        m.save(pc)
        with open(pc, encoding="utf-8") as f:
            d = json.load(f)
        w = next(iter(d["materials"].values()))
        check("gesetzte Werte stehen in der Datei",
              w.get("art") == "Spannstahl" and w.get("verfestigung") == 1e-4 and w.get("nachweis_ausnehmen") is True
              and w.get("Ep") == 205e9 and w.get("sigma_pmax") == 780e6 and "sigma_pm0" not in w
              and d["sections"]["Rund 40"].get("A_s") == 1150e-6 and d["design"].get("gamma_P") == 1.35,
              str({k: w.get(k) for k in ("art", "verfestigung", "nachweis_ausnehmen", "Ep", "sigma_pmax")}))
        m2 = Model.load(pc)
        mat2 = next(iter(m2.materials.values()))
        check("… und kommen beim Laden zurück, die übrigen mit Vorgabe",
              (mat2.art, mat2.verfestigung, mat2.nachweis_ausnehmen, mat2.Ep, mat2.sigma_pmax, mat2.sigma_pm0)
              == ("Spannstahl", 1e-4, True, 205e9, 780e6, None)
              and (m2.sections["Rund 40"].A_s, m2.sections["Rund 40"].gewinde) == (1150e-6, "aufgewalzt")
              and m2.design.gamma_P == 1.35)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _reiches_modell():
    """Quader (Volumenkoerper V1, tet10) mit Zugstab S1, Volumenbereich, einem
    Lastfall mit Vorspannung und Temperatur - je ein Objekt fuer jedes neue Feld."""
    from statik3d.model import Vorspannung
    from tests.test_stabeinleitung import lagern_frei, quader, zugstab
    m = quader(h=0.02, ordnung=1)
    lagern_frei(m)
    _f, _k, e = zugstab(m)
    vol = [i for i, el in enumerate(m.elements) if el.typ in ("tet4", "tet10")]
    m.add_volumenbereich("B1", vol[:10])
    lc = m.case(m.active_case)
    lc.vorspannungen.append(Vorspannung(ziel="S1", art="stab", kraft=10e3))
    m.load_temp(e, -5.0, case=m.active_case)
    m.load_beam(e, qz=-1e3, case=m.active_case)
    return m


def test_neue_felder_ein_mechanismus():
    print("\n--- Neue Felder: ein Mechanismus für alle Pakete (model.NEUE_FELDER) ---")
    import copy
    from statik3d import ergebnisse
    from statik3d import model as M
    # die neuen Felder aller Pakete mit ihrer Vorgabe (Liste des Koordinators
    # vom 14.10.2026); "" = Schluessel der Modelldatei selbst
    soll = {
        "plastizitaet": {"abbruch": "ingenieurmaessig", "pendel_kraft_anteil": 1.0e-3, "pendel_weg": 1.0e-6,
                         "spannstufen": 0},
        "design": {"gamma_P": 1.0},
        "netz": {"krafteinleitung_fein": False, "krafteinleitung_stabenden": False},
        "materials": {"verfestigung": None, "art": "", "nachweis_ausnehmen": False, "Ep": None,
                      "sigma_pmax": None, "sigma_pm0": None},
        "sections": {"A_s": None, "gewinde": ""},
        "koerper": {"nachweis_ausnehmen": False},
        "volumenbereiche": {"eps_grenze": 0.05},
        "members": {"einleitung": {}},
        "starrkoerper": {"momente": []},
        "load_cases": {"faktorisiert": False},
        "load_cases.vorspannungen": {"sollkraft": False, "gruppe": 1},
        "load_cases.temp_loads": {"aus_vorspannung": 0.0, "vorspann_E": 0.0, "vorspann_alpha": 0.0},
        "load_cases.beam_loads": {"bezugslaenge": ""},
        "load_cases.linienlasten": {"bezugslaenge": ""},
        "": {"stabeinleitung": {"art": "punkt", "d_innen": 0.0, "d_aussen": 0.0}},
    }
    tabelle = getattr(M, "NEUE_FELDER", None) or {}
    fehlt = [f"{s}.{f}" for s, ff in soll.items() for f in ff
             if s not in tabelle or f not in tabelle[s] or tabelle[s][f] != ff[f]]
    check("model.NEUE_FELDER führt jedes neue Feld mit seiner Vorgabe", not fehlt, f"fehlt: {fehlt}")
    from statik3d.plastizitaet import Plastizitaet
    neu_pl = dict(getattr(Plastizitaet, "NEU_14_10", {}) or {})
    check("… auch die Einstellungen, die Plastizitaet.als_dict weglässt (NEU_14_10)",
          all(tabelle.get("plastizitaet", {}).get(k, object()) == v for k, v in neu_pl.items()),
          str(neu_pl))
    m = _reiches_modell()
    k_jetzt = ergebnisse.kennung(m)
    echt = Model.to_dict

    def mit_vorgaben(self, *a, **k):
        """Die Modelldatei, wie sie ein Stand vom 13.10.2026 schrieb: jedes
        neue Feld mit seiner Vorgabe darin."""
        d = echt(self, *a, **k)
        for schl, felder in soll.items():
            if schl == "":
                objekte = [d]
            elif "." in schl:
                oben, liste = schl.split(".")
                objekte = [x for lc in d.get(oben, []) for x in lc.get(liste, [])]
            else:
                ziel = d.get(schl)
                objekte = (list(ziel.values()) if schl in ("materials", "sections")
                           else ziel if isinstance(ziel, list) else [ziel])
            for x in objekte:
                if isinstance(x, dict):
                    for f, v in felder.items():
                        x.setdefault(f, copy.deepcopy(v))
        return d
    Model.to_dict = mit_vorgaben
    try:
        k_mit = ergebnisse.kennung(m)
    finally:
        Model.to_dict = echt
    ok, grund = ergebnisse.passt(k_mit, m)
    check("Datei mit allen neuen Feldern auf ihrer Vorgabe: die Ergebnisdatei passt", ok and not grund, grund)
    ok, grund = ergebnisse.passt(k_jetzt, m)
    check("… ebenso ohne die Felder (Datei von davor)", ok and not grund, grund)
    mat, sec = m.materials["S235"], m.sections["Rund 16"]
    lc = m.case(m.active_case)
    vs, tl = lc.vorspannungen[0], lc.temp_loads[0]
    from statik3d.model import Stabeinleitung

    def setze(obj, feld, wert):
        alt = copy.deepcopy(getattr(obj, feld))
        setattr(obj, feld, wert)
        return lambda: setattr(obj, feld, alt)
    faelle = [
        ("Plastizitaet.abbruch", lambda: setze(m.plastizitaet, "abbruch", "streng")),
        ("DesignSettings.gamma_P", lambda: setze(m.design, "gamma_P", 1.35)),
        ("Plastizitaet.pendel_kraft_anteil", lambda: setze(m.plastizitaet, "pendel_kraft_anteil", 2e-3)),
        ("Plastizitaet.pendel_weg", lambda: setze(m.plastizitaet, "pendel_weg", 2e-6)),
        ("Plastizitaet.spannstufen", lambda: setze(m.plastizitaet, "spannstufen", 3)),
        ("Material.verfestigung", lambda: setze(mat, "verfestigung", 1e-4)),
        ("Material.art", lambda: setze(mat, "art", "Spannstahl")),
        ("Material.Ep", lambda: setze(mat, "Ep", 205e9)),
        ("Material.sigma_pmax", lambda: setze(mat, "sigma_pmax", 780e6)),
        ("Material.sigma_pm0", lambda: setze(mat, "sigma_pm0", 700e6)),
        ("Material.nachweis_ausnehmen", lambda: setze(mat, "nachweis_ausnehmen", True)),
        ("Section.A_s", lambda: setze(sec, "A_s", 157e-6)),
        ("Section.gewinde", lambda: setze(sec, "gewinde", "M16")),
        ("Volumenbereich.eps_grenze", lambda: setze(m.volumenbereiche["B1"], "eps_grenze", 0.03)),
        ("Volumenkörper.nachweis_ausnehmen", lambda: setze(m.koerper["V1"], "nachweis_ausnehmen", True)),
        ("Member.einleitung", lambda: setze(m.members["S1"], "einleitung", {"A": {"art": "stirn"}})),
        ("Model.stabeinleitung", lambda: setze(m, "stabeinleitung", Stabeinleitung("stirn"))),
        ("Vorspannung.sollkraft", lambda: setze(vs, "sollkraft", True)),
        ("LoadCase.faktorisiert", lambda: setze(lc, "faktorisiert", True)),
        ("Kategorie NZ", lambda: setze(lc, "category", "NZ")),
        ("TempLoad.aus_vorspannung (Merkmal)", lambda: setze(tl, "aus_vorspannung", 952e3)),
        ("BeamLoad.bezugslaenge", lambda: setze(lc.beam_loads[0], "bezugslaenge", "projektion")),
    ]
    falsch = []
    for name, tun in faelle:
        zurueck = tun()
        ok, grund = ergebnisse.passt(k_jetzt, m)
        zurueck()
        if ok:
            falsch.append(name)
        print(f"       {name:36s} -> {grund}")
    check(f"jedes gesetzte neue Feld macht die Ergebnisdatei ungültig ({len(faelle)} Felder)", not falsch,
          f"passt trotzdem: {falsch}")
    # die Gruppe einer Sollkraft: zaehlt, wenn es eine Sollkraft ist
    vs.sollkraft = True
    k_soll = ergebnisse.kennung(m)
    vs.gruppe = 2
    ok, grund = ergebnisse.passt(k_soll, m)
    vs.gruppe, vs.sollkraft = 1, False
    check("Vorspannung.gruppe einer Sollkraft zählt", not ok, grund)
    ok, grund = ergebnisse.passt(k_jetzt, m)
    check("… und alles zurückgesetzt passt wieder", ok and not grund, grund)
    check("die drei Tabellen von vorher gibt es nicht mehr",
          not any(hasattr(ergebnisse, n) for n in ("NEUE_VORGABEN", "SPAETERE_FELDER", "NEU_AUF_VORGABE")))


def main():
    for t in (test_spannstahl_art, test_vorspannung_ein_merkmal, test_stabenden_eine_warnung,
              test_alte_ergebnisdatei_gamma_p, test_alte_datei_bitgleich, test_neue_felder_ein_mechanismus):
        try:
            t()
        except Exception as ex:          # noqa: BLE001 - jede Pruefung meldet sich
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
