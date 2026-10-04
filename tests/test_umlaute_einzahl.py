"""
Umlaute und Einzahl in den Texten, die der Anwender liest (Teilpaket 11c des
Oberflaechenplans, 03.10.2026).

Bis zum 03.10.2026 schrieb die Zeile der EC3-Nachweise an einem einzelnen
Traeger „Nachweise EC3: 1 Staebe, 1 Kombinationen, … - alle erfuellt“, der
Fortschritt „Ermuedung: 1 Staebe mit Kerbfall“, die Statusleiste „Netz:
2 Knoten · 1 Elemente“, jede Tabelle mit einer Zeile „1 Zeilen“ und die
Sammelmaske eines Elements „1 Elemente bearbeiten“. Geprueft wird an echten
Ausgaben, nicht am Quelltext:

* EC3: Zusammenfassung, Gesamtzeile der Analyse, Kopf der Tabelle, Hinweis
  „Torsion schöpft …“;
* Ermuedung: Zusammenfassung, Fortschritt, Kopf der Tabelle, Kerbfallliste;
* die uebrigen Nachweiszeilen (Volumen, Beulen, Lasteinleitung, GZG,
  Knicklaengen) und der Kerbfallvorschlag im Protokoll;
* „Modell prüfen“ (Model.check, diagnose.meldungen);
* Statusleiste, Tabellenfuss, Auswahl im Modellbaum und Sammelmaske im
  Offscreen-Fenster.

Zu jeder Einzahl steht eine Mehrzahl daneben: „1 Stab“ allein bewiese
nicht, dass zwei Staebe nicht auch „2 Stab“ hiessen.

Aufruf:  python -m tests.test_umlaute_einzahl
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_umlaute_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

#: ASCII-Umschreibungen, die in diesen Texten nicht mehr stehen duerfen - nur
#: zusammen mit einer positiven Pruefung des neuen Textes benutzt
UMSCHREIBUNG = re.compile(r"Staebe|erfuellt|Ermuedung|Auftraeg|massgebend|Laengs|geprueft|"
                          r"schweiss|Stumpfstoss|Oberflaeche|\bfuer\b|ueberhoehung|schoepft|"
                          r"faehig|Flaeche|ueberschritten")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _traeger(staebe=1, q=-10000.0, fatigue=False):
    """Einfeldtraeger IPE 300 S235, L = 6 m, sechs Elemente, eine
    GZT-Kombination; als ein Stab oder in *staebe* Stuecke geteilt."""
    from statik3d import mesher
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (6, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3]); m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=q)
    if staebe == 1:
        m.add_member("Traeger", list(range(6)), detail_category=71e6 if fatigue else None)
    else:
        m.add_member("A", [0, 1, 2]); m.add_member("B", [3, 4, 5])
    m.add_combination("K1", {"LF1": 1.0}, "ULS")
    if fatigue:
        m.add_fatigue_load("E1", "LF1", None, 2e6)
    return m


def test_anzahl():
    from statik3d.begriffe import anzahl
    import numpy as np
    check("anzahl: 1 Stab, 2 Stäbe, 0 Stäbe",
          (anzahl(1, "Stab", "Stäbe"), anzahl(2, "Stab", "Stäbe"), anzahl(0, "Stab", "Stäbe"))
          == ("1 Stab", "2 Stäbe", "0 Stäbe"))
    check("anzahl: numpy-Zahl 1 ist Einzahl", anzahl(np.int64(1), "Zeile", "Zeilen") == "1 Zeile")


def test_ec3():
    from statik3d import solver
    from statik3d.ec3.design import check_members
    an = solver.solve_all(_traeger(), design=True)
    s = an.design.summary()
    print("     summary():", s)
    check("EC3: „Nachweise EC3: 1 Stab, 1 Kombination, max. Ausnutzung …“",
          s.startswith("Nachweise EC3: 1 Stab, 1 Kombination, max. Ausnutzung"), s[:60])
    check("EC3: die Zeile endet mit „ - alle erfüllt“", s.endswith(" - alle erfüllt"), s[-30:])
    check("EC3: keine ASCII-Umschreibung in der Zeile", not UMSCHREIBUNG.search(s), s)
    zeilen = [z for z in an.summary().splitlines() if z.startswith("Nachweise EC3")]
    check("EC3: auch Analysis.summary() sagt „1 Stab“ und „alle erfüllt“",
          bool(zeilen) and "1 Stab," in zeilen[0] and zeilen[0].endswith(" - alle erfüllt"), str(zeilen))
    kopf = an.design.table()[0]
    check("EC3: Tabellenkopf „maßgebender Nachweis“ (Bericht, Kommandozeile)",
          kopf[6] == "maßgebender Nachweis", str(kopf))
    # Mehrzahl daneben
    s2 = solver.solve_all(_traeger(staebe=2), design=True).design.summary()
    check("EC3: zwei Stäbe heißen „2 Stäbe“", s2.startswith("Nachweise EC3: 2 Stäbe, 1 Kombination,"), s2[:60])
    # Nicht erfuellt: zehnfache Last
    s3 = solver.solve_all(_traeger(q=-100000.0), design=True).design.summary()
    check("EC3: „ - 1 Stab NICHT erfüllt“", " - 1 Stab NICHT erfüllt" in s3, s3[-40:])
    # Kein Stab mit Nachweis: Zeile und Fortschritt
    m0 = _traeger(); m0.members.clear()
    an0 = solver.solve_all(m0, design=True)
    texte = []
    d0 = check_members(m0, an0, progress=texte.append)
    check("EC3: ohne Stab „Nachweise EC3: keine Stäbe“ und Fortschritt „keine Stäbe mit Nachweis“",
          d0.summary().startswith("Nachweise EC3: keine Stäbe")
          and "Nachweise EC3: keine Stäbe mit Nachweis" in texte, f"{d0.summary()[:40]} {texte}")


def test_torsion():
    import numpy as np
    from statik3d.profiles import make_section
    from statik3d.ec3.resistance import section_check
    ipe = make_section("IPE 300")
    fvd = 235e6 / np.sqrt(3)
    Mt = 6.0 * fvd * ipe.It / max(ipe.tf, ipe.tw)
    r = section_check(ipe, 235e6, 0, 0, 200e3, Mt, 50e3, 0, 1.0)
    t = r["checks"]["V_z + tau_t (6.2.6/6.2.7)"][1]
    check("EC3: „Torsion schöpft die Schubtragfähigkeit allein aus“",
          t.startswith("Torsion schöpft die Schubtragfähigkeit allein aus: "), t[:60])


def test_ermuedung():
    from statik3d import solver
    from statik3d.ec3.fatigue import check_fatigue, DETAIL_EXAMPLES
    m = _traeger(fatigue=True)
    an = solver.solve_all(m, design=True, fatigue=True)
    s = an.fatigue.summary()
    print("     summary():", s)
    check("Ermüdung: „Ermüdung: 1 Stab, max. Schädigung D = …“",
          s.startswith("Ermüdung: 1 Stab, max. Schädigung D = "), s[:60])
    fm = an.fatigue.members["Traeger"]
    check("Ermüdung: maßgebender Ort nennt „1 Stufe)“ bei einer Stufe",
          len(fm.kollektiv) == 1 and fm.governing.endswith(", 1 Stufe)"), fm.governing)
    check("Ermüdung: Tabellenkopf letzte Spalte „maßgebend“", an.fatigue.table()[0][-1] == "maßgebend",
          str(an.fatigue.table()[0][-1]))
    texte = []
    check_fatigue(m, an, progress=lambda t, *a: texte.append(t), anteil=(0.0, 1.0))
    print("     Fortschritt:", texte)
    check("Ermüdung: Fortschritt „Ermüdung: 1 Stab mit Kerbfall“ … „Ermüdung fertig“",
          "Ermüdung: 1 Stab mit Kerbfall" in texte and "Ermüdung fertig" in texte
          and any(t.startswith("Ermüdung Traeger: D = ") for t in texte), str(texte))
    check("Ermüdung: kein Fortschrittstext mit ASCII-Umschreibung",
          bool(texte) and not any(UMSCHREIBUNG.search(t) for t in texte), str(texte))
    check("Ermüdung: Kerbfall 125 „Längsnaht durchgeschweißt, geprüft …“",
          DETAIL_EXAMPLES[125] == "Längsnaht durchgeschweißt, geprüft (Tab. 8.2); Brennschnitt maschinell (8.1, 3)",
          DETAIL_EXAMPLES[125])
    check("Ermüdung: Kerbfall 100 „Stumpfstoß quer, geprüft, Schweißnahtüberhöhung …“",
          DETAIL_EXAMPLES[100].startswith("Stumpfstoß quer, geprüft, Schweißnahtüberhöhung"), DETAIL_EXAMPLES[100])
    alt = [t for t in DETAIL_EXAMPLES.values() if UMSCHREIBUNG.search(t)]
    check("Ermüdung: keine Kerbfallbeschreibung mit ASCII-Umschreibung", not alt and len(DETAIL_EXAMPLES) == 14,
          str(alt[:2]))
    # Mehrzahl daneben: zwei Staebe mit Kerbfall
    m2 = _traeger(staebe=2)
    for mem in m2.members.values():
        mem.detail_category = 71e6
    m2.add_fatigue_load("E1", "LF1", None, 2e6)
    s2 = solver.solve_all(m2, fatigue=True).fatigue.summary()
    check("Ermüdung: zwei Stäbe heißen „2 Stäbe“", s2.startswith("Ermüdung: 2 Stäbe, "), s2[:40])


def test_weitere_nachweise():
    from statik3d.ec3.volumen import VolumenResults, VolumenCheck
    from statik3d.ec3.beulen import BeulResults, BeulCheck, EinleitungResults, EinleitungCheck
    from statik3d.gzg import GZGResults, GrenzeCheck
    from statik3d.ec3.knicklaengen import KnicklaengenErgebnis, Knicklaenge
    w = {"sigma_v": 100e6, "f_yd": 235e6}
    v1 = VolumenResults(bereiche={"B1": VolumenCheck("B1", util=0.4, werte=w)}).summary()
    v2 = VolumenResults(bereiche={"B1": VolumenCheck("B1", util=0.4, werte=w),
                                  "B2": VolumenCheck("B2", util=0.3, werte=w)}).summary()
    check("Volumen: „1 Bereich,“ und „2 Bereiche,“",
          "): 1 Bereich, max." in v1 and "): 2 Bereiche, max." in v2, f"{v1[:50]} | {v2[:50]}")
    b1 = BeulResults(felder={"F1": BeulCheck("F1", util=0.5)}, kombinationen=["K1"]).summary()
    b2 = BeulResults(felder={"F1": BeulCheck("F1", util=0.5), "F2": BeulCheck("F2", util=0.2)},
                     kombinationen=["K1", "K2"]).summary()
    check("Beulen: „1 Feld, 1 Kombination,“ und „2 Felder, 2 Kombinationen,“",
          b1.startswith("Beulen (EN 1993-1-5): 1 Feld, 1 Kombination, ")
          and b2.startswith("Beulen (EN 1993-1-5): 2 Felder, 2 Kombinationen, "), f"{b1[:50]} | {b2[:50]}")
    e1 = EinleitungResults(stellen={"S1": EinleitungCheck("S1", util=0.5, F_Ed=1e3, F_Rd=2e3)}).summary()
    check("Lasteinleitung: „1 Stelle,“", e1.startswith("Lasteinleitung (EN 1993-1-5, 6): 1 Stelle, "), e1[:50])
    g1 = GZGResults(checks={"G1": GrenzeCheck("G1", util=0.5, grenztext="L/300")}).summary()
    g2 = GZGResults(checks={"G1": GrenzeCheck("G1", util=0.5, grenztext="L/300"),
                            "G2": GrenzeCheck("G2", util=0.1, grenztext="L/300")}).summary()
    check("GZG: „1 Nachweis,“ und „2 Nachweise,“",
          g1.startswith("Verformungen (GZG): 1 Nachweis, ") and g2.startswith("Verformungen (GZG): 2 Nachweise, "),
          f"{g1[:40]} | {g2[:40]}")
    k1 = KnicklaengenErgebnis(alpha_cr=2.0, modus=0, grundzustand="LF1",
                              staebe={"S1": Knicklaenge("S1", 3.0, -1e3, 2.0, beteiligt=True)}).summary()
    check("Knicklängen: „1 von 1 Stab beteiligt“", k1.endswith(": 1 von 1 Stab beteiligt"), k1[-40:])


def test_ergebnisprotokoll():
    """Runde 2 (03.10.2026): die Zeilen der Rechnung selbst - Analysis.summary(),
    Results.summary(), Umhuellende - und die Beschreibungen von Layer,
    Subsystem, Situation und Kontaktbedingung. Bis dahin „Lastfaelle: 1“,
    „Gleichungsloeser“, „Summe Auflagerkraefte“, „1 Ergebnisse“, „1 Stäbe“,
    „V1 an 1 Flächen“."""
    from statik3d import solver
    from statik3d.model import Subsystem, Situation, Kontaktbedingung
    m = _traeger()
    an = solver.solve_all(m)
    zeilen = an.summary().splitlines()
    check("Analysis.summary(): „Lastfälle: 1   Kombinationen: 1   Rechenzeit …“",
          zeilen[0].startswith("Lastfälle: 1   Kombinationen: 1   Rechenzeit: "), zeilen[0][:60])
    umh = [z for z in zeilen if z.startswith("Umhüllende GZT")]
    check("Umhüllende mit einem Ergebnis: „Umhüllende GZT: 1 Ergebnis“",
          umh == ["Umhüllende GZT: 1 Ergebnis"], str(umh))
    rs = an.cases["LF1"].summary().splitlines()
    print("     Results.summary():", rs)
    check("Results.summary(): „Gleichungslöser“ und „Summe Auflagerkräfte“",
          any(z.startswith("Gleichungslöser         : ") for z in rs)
          and any(z.startswith("Summe Auflagerkräfte    : [") for z in rs), str(rs))
    check("Results.summary(): der Doppelpunkt steht in jeder Zeile an derselben Stelle (24)",
          all(z.index(":") == 24 for z in rs if ":" in z[:26]), str([z[:26] for z in rs]))
    check("Results.summary(): keine ASCII-Umschreibung", bool(rs) and not any(UMSCHREIBUNG.search(z) for z in rs)
          and not any(w in z for z in rs for w in ("loeser", "Loeser", "kraefte", "koerper")), str(rs))
    L = m.layer_anlegen("Deckel", staebe=["Traeger"], elemente=[0, 1])
    check("Layer: „1 Stab, 2 Elemente“", L.bezug() == "1 Stab, 2 Elemente", L.bezug())
    sub = Subsystem("S", elemente=[0], knoten=[0, 1], beruehrung=[0], kontakte=["K"])
    check("Subsystem: „1 Element, 2 Knoten, 1 Berührungselement, 1 Kontakt“",
          sub.bezug() == "1 Element, 2 Knoten, 1 Berührungselement, 1 Kontakt", sub.bezug())
    sit = Situation("S", deaktiviert=[3])
    check("Situation: „unbewegt, 1 Element aus“", sit.bezug() == "unbewegt, 1 Element aus", sit.bezug())
    kb1 = Kontaktbedingung(name="KB", koerpernamen=["V1"], gegenflaechen=["F1"])
    kb2 = Kontaktbedingung(name="KB", flaechennamen=["F1", "F2"])
    kb3 = Kontaktbedingung(name="KB", gegenflaechen=["F1"])
    check("Kontaktbedingung: „V1 an 1 Fläche“, „2 Kontaktflächen“, „1 zugeordnete Fläche“",
          (kb1.fuge(), kb2.fuge(), kb3.fuge()) == ("V1 an 1 Fläche", "2 Kontaktflächen", "1 zugeordnete Fläche"),
          str((kb1.fuge(), kb2.fuge(), kb3.fuge())))


def test_runde3():
    """Gegenpruefung 03.10.2026: anzahl mit 1.0, Kontakt-Zusammenfassung,
    Plastizitaet in Protokoll und Fortschritt, Diagnose (Pronomen und Verb bei
    einem Element), Grund einer nicht passenden Ergebnisdatei."""
    import numpy as np
    from statik3d.begriffe import anzahl
    from statik3d import contact as ct, diagnose, solver, plastizitaet as pl
    from statik3d.model import Model, Material, NodalLoad
    from statik3d.gui import rechenliste as rl
    check("anzahl: 1.0 ist Einzahl, ganze Zahlen ohne „.0“, 1,5 bleibt Mehrzahl",
          (anzahl(1.0, "Stab", "Stäbe"), anzahl(2.0, "Stab", "Stäbe"), anzahl(np.float64(1.0), "Stab", "Stäbe"),
           anzahl(1.5, "Stab", "Stäbe"), anzahl("alle", "Objekt", "Objekte"))
          == ("1 Stab", "2 Stäbe", "1 Stab", "1.5 Stäbe", "alle Objekte"),
          str((anzahl(1.0, "Stab", "Stäbe"), anzahl(2.0, "Stab", "Stäbe"), anzahl(1.5, "Stab", "Stäbe"))))
    k1 = ct.summary([{"status": "Haften", "Fn": 1e3}])
    k2 = ct.summary([{"status": "Haften", "Fn": 1e3}, {"status": "offen", "Fn": 0.0}])
    check("Kontakt: „1 von 1 Bedingung aktiv“, „1 von 2 Bedingungen aktiv“",
          k1.startswith("Kontakt: 1 von 1 Bedingung aktiv,") and k2.startswith("Kontakt: 1 von 2 Bedingungen aktiv,"),
          f"{k1} | {k2}")
    # Plastizitaet: ein Hexaeder unter Zug ueber f_y (wie tests/test_plastizitaet)
    E, NU, FY = 210e9, 0.3, 355e6
    m = Model("Zug")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", n, "S355", "")
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1]); m.fix(n[1], [1]); m.fix(n[3], [0])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for i in n[4:]:
        lc.nodal_loads.append(NodalLoad(i, [0, 0, 1.1 * FY / 4.0, 0, 0, 0]))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2, iterationen=60, toleranz=1e-8)
    texte = []
    r = solver.solve_static(m, progress=lambda t, *a: texte.append(str(t)))
    log = (r.info.get("plastizitaet") or {}).get("log", [])
    zeile = [z for z in log if z.startswith("Plastizität: ") and "ε_p,eq max" in z]
    check("Plastizität im Protokoll: „Plastizität: 1 Element fließt, ε_p,eq max …, … in 2 Laststufen“",
          bool(zeile) and zeile[0].startswith("Plastizität: 1 Element fließt, ε_p,eq max ")
          and "in 2 Laststufen" in zeile[0], str(zeile[:1]))
    schritt = [t for t in texte if t.startswith("Plastizität: Laststufe") and "fließt" in t]
    check("Plastizität im Fortschritt: „… 1 Element fließt, Änderung …“, die Rechenliste liest die Änderung weiter",
          bool(schritt) and "1 Element fließt, Änderung " in schritt[0] and rl.MASS.search(schritt[0]) is not None,
          str(schritt[:1]))
    # Diagnose: ein entartetes Element, eine Umwandlung
    d = {"entartete_elemente": [(4, "hex8", "alle Knoten auf einer Ebene")],
         "entartet_umgewandelt": {"hex8→pent6": 1},
         "unvernetzte_flaechen": [], "unvernetzte_koerper": [], "ohne_lager": [], "nur_kontakt": [], "lose_knoten": 0}
    t = diagnose.meldungen(m, d)
    print("     meldungen:", t)
    check("Diagnose: „1 entartetes Element … trägt es nichts und wird … übergangen … Wo es stört“",
          any(z.startswith("WARNUNG: 1 entartetes Element ohne Ausdehnung - ohne Steifigkeit trägt es nichts "
                           "und wird bei der Rechnung übergangen") and "Wo es stört" in z for z in t), str(t))
    check("Diagnose: „1 Element aus einem entarteten Volumenelement … wurde umgewandelt … - seine Genauigkeit“",
          any(z.startswith("Hinweis: 1 Element aus einem entarteten Volumenelement") and "wurde umgewandelt" in z
              and " - seine Genauigkeit ist die des Keils" in z for z in t), str(t))
    d2 = dict(d, entartet_umgewandelt={"hex8→pent6": 2},
              entartete_elemente=[(4, "hex8", "eben"), (5, "hex8", "eben")])
    t2 = diagnose.meldungen(m, d2)
    check("Diagnose, Mehrzahl daneben: „tragen sie nichts“, „ - ihre Genauigkeit“",
          any("tragen sie nichts und werden" in z for z in t2)
          and any(" - ihre Genauigkeit ist die des Keils" in z for z in t2), str(t2))
    from statik3d import ergebnisse as erg
    k = erg.kennung(m)
    k["lastfaelle"] = list(k.get("lastfaelle", [])) + ["Neu"]
    ok, grund = erg.passt(k, m)
    check("Ergebnisdatei passt nicht: „die Lastfälle sind andere“", not ok and grund == "die Lastfälle sind andere",
          grund)


def test_kerbfallvorschlag():
    from statik3d.ec3 import kerbfaelle
    log = []
    kerbfaelle.anwenden(_traeger(), log)
    zeile = next((z for z in log if z.startswith("Kerbfälle vorgeschlagen")), "")
    log2 = []
    kerbfaelle.anwenden(_traeger(staebe=2), log2)
    zeile2 = next((z for z in log2 if z.startswith("Kerbfälle vorgeschlagen")), "")
    check("Kerbfallvorschlag: „1 Stab mit gewalztem Querschnitt“, „2 Stäbe mit …“",
          "1 Stab mit gewalztem Querschnitt:" in zeile and "2 Stäbe mit gewalztem Querschnitt:" in zeile2,
          f"{zeile[:70]} | {zeile2[:70]}")


def test_pruefen():
    from statik3d.model import FaceLoad
    from statik3d import diagnose
    m = _traeger()
    m.case().face_loads.append(FaceLoad(elem=99, p=1e3))
    msgs = m.check()
    z = [x for x in msgs if "Element 99" in x]
    check("Modell prüfen: „Flächenlast auf Element 99 - das Element gibt es nicht“",
          bool(z) and "Flächenlast auf Element 99 - das Element gibt es nicht" in z[0], str(z))
    d = {"unvernetzte_flaechen": ["F1"], "unvernetzte_koerper": [], "ohne_lager": [],
         "nur_kontakt": [[1, 2]], "lose_knoten": 1, "teile": 1}
    t = diagnose.meldungen(m, d)
    print("     meldungen:", t)
    check("Modell prüfen: „WARNUNG: 1 Fläche ohne Netz“",
          any(x.startswith("WARNUNG: 1 Fläche ohne Netz") for x in t), str(t))
    check("Modell prüfen: „Hinweis: 1 Teiltragwerk ist nur durch Kontakt gehalten“",
          any(x.startswith("Hinweis: 1 Teiltragwerk ist nur durch Kontakt gehalten") for x in t), str(t))
    check("Modell prüfen: „Hinweis: 1 Knoten trägt kein Element“",
          any(x.startswith("Hinweis: 1 Knoten trägt kein Element") for x in t), str(t))
    d2 = dict(d, unvernetzte_flaechen=["F1", "F2"], nur_kontakt=[[1], [2]], lose_knoten=3)
    t2 = diagnose.meldungen(m, d2)
    check("Modell prüfen: Mehrzahl „2 Flächen“, „2 Teiltragwerke sind“, „3 Knoten tragen“",
          any(x.startswith("WARNUNG: 2 Flächen ohne Netz") for x in t2)
          and any(x.startswith("Hinweis: 2 Teiltragwerke sind nur") for x in t2)
          and any(x.startswith("Hinweis: 3 Knoten tragen kein Element") for x in t2), str(t2))


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, 9b): sonst
    # oeffnete ein Fehler ein Fenster, und ein Hinweis bliebe ungesehen
    from tests.meldungen import abfangen
    _FENSTER.update(w=w, app=app, meldungen=abfangen(w, protokoll=True))
    return w, app


def test_oberflaeche():
    from statik3d import solver
    from statik3d.gui import tabellen as tab
    from statik3d.model import Material, Section
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 300"))
    a, b = m.add_node(0.0, 0.0, 0.0), m.add_node(4.0, 0.0, 0.0)
    m.add_element("beam", [a, b], "S235", "IPE 300")
    m.add_member("S1", [0])
    m.support(a, "all")
    m.load_node(b, Fz=-1e3)
    w.refresh_all(); app.processEvents()
    check("Statusleiste: „Netz: 2 Knoten · 1 Element“", w.lbl_netz.text() == "Netz: 2 Knoten · 1 Element",
          w.lbl_netz.text())
    w.analysis = solver.solve_all(m)
    w._refresh_status()
    check("Statusleiste: „Solver: 1 Ergebnis“ (ein Lastfall)", w.lbl_solver.text() == "Solver: 1 Ergebnis",
          w.lbl_solver.text())
    w.analysis = None
    w._baum_objekt_waehlen("stab", "S1"); app.processEvents()
    check("Auswahl im Modellbaum: „1 Stab ausgewählt (Modellbaum)“",
          w.lbl_sel.text() == "1 Stab ausgewählt (Modellbaum)", w.lbl_sel.text())
    check("Auswahl für ein neues Subsystem: „1 Stab“ (bis dahin „1 Stäbe“)",
          w._auswahl_beschreibung() == "1 Stab", w._auswahl_beschreibung())
    t = tab.Datentabelle([tab.Spalte("A"), tab.Spalte("B")], "Probe")
    t.setzen([["x", "1"]])
    eins = t.lbl_zeilen.text()
    t.setzen([["x", "1"], ["y", "2"]])
    check("Tabellenfuß: „1 Zeile“, „2 Zeilen“", (eins, t.lbl_zeilen.text()) == ("1 Zeile", "2 Zeilen"),
          f"{eins} | {t.lbl_zeilen.text()}")
    w.sammelmaske("element", ["0"]); app.processEvents()
    mr = w.maskenrand
    titel = mr.maske.titel if mr.offen() and mr.maske is not None else None
    check("Sammelmaske eines Elements: „1 Element bearbeiten“", titel == "1 Element bearbeiten", repr(titel))
    _abbruch_mit_teilergebnis(w, app)
    # Kopfzeile mit „Kontakte zeigen“: eine Bedingung (zwei Darsteller je Bedingung)
    w.act_kontakte.blockSignals(True)
    w.act_kontakte.setChecked(True)
    alt_d = list(getattr(w, "_kontakt_darsteller", []) or [])
    w._kontakt_darsteller = ["kontaktflaeche0", "kontakttext0"]
    sicht = w._sicht_text()
    w._kontakt_darsteller = alt_d
    w.act_kontakte.setChecked(False)
    w.act_kontakte.blockSignals(False)
    check("Kopfzeile: „Kontakte: 1 Bedingung farbig mit Schild“", "Kontakte: 1 Bedingung farbig mit Schild" in sicht,
          sicht)
    # Abnahme des Netzes vor dem Rechnen: eine Verletzung
    import types
    from statik3d import diagnose as dg
    echt, fragen = dg.abnahme, []
    alt_f = w._fragen
    dg.abnahme = lambda *a, **k: [types.SimpleNamespace(stufe="FEHLER", pruefung="Elementgüte", text="Probe")]
    w._fragen = lambda titel, text: (fragen.append(text), False)[1]
    try:
        w._abnahme_bestaetigen()
    finally:
        dg.abnahme, w._fragen = echt, alt_f
    check("Abnahme vor dem Rechnen: „Das Netz reißt 1 Prüfung:“",
          bool(fragen) and fragen[0].startswith("Das Netz reißt 1 Prüfung:"), str(fragen[:1])[:80])
    mel = _FENSTER["meldungen"]
    check("Oberfläche: unterwegs kein Fehler und kein Hinweis", not mel.alle, str(mel.alle[:3]))


def _abbruch_mit_teilergebnis(w, app):
    """Abbruch nach dem einzigen Lastfall - derselbe Weg wie in
    test_gui_smoke (Abschnitt „Abbruch mit Teilergebnis“), hier offscreen:
    Statuszeile und Protokoll sagen „1 Lastfall bleibt erhalten“."""
    import time
    from statik3d import solver

    class _Halt(Exception):
        pass

    def halt(text, anteil=None):
        if str(text).startswith("Lastfall "):
            raise _Halt(str(text))

    ex_teil = None
    try:
        solver.solve_all(w.model, progress=halt)
    except _Halt as ex:
        ex_teil = ex
    an = getattr(ex_teil, "teilanalyse", None)
    if not check("Abbruch: der abgebrochene Lauf trägt den einen Lastfall",
                 an is not None and len(an.cases) == 1 and not an.combinations,
                 str(list(an.cases)) if an is not None else "keine Teilanalyse"):
        return
    vorher = w.log.blockCount()
    w.worker = type("_ProbeWorker", (), {"ausnahme": ex_teil, "abbruch_angefordert": True})()
    w._rechnung_name = "Probe-Teillauf"
    w._rechnung_t0 = time.time()
    w._rechnet_gerade = True
    w._bg_abgebrochen(7.0)
    app.processEvents()
    neu = w.log.toPlainText().splitlines()[vorher:]
    status = w.statusBar().currentMessage()
    check("Abbruch: Statuszeile „Probe-Teillauf abgebrochen (nach 7 s) - 1 Lastfall bleibt erhalten“",
          status.startswith("Probe-Teillauf abgebrochen (nach 7 s) - 1 Lastfall bleibt erhalten"), status[:90])
    check("Abbruch: auch die ABBRUCH-Zeile im Protokoll sagt „1 Lastfall bleibt erhalten“",
          any(z.startswith("ABBRUCH") and "1 Lastfall bleibt erhalten" in z for z in neu),
          str([z for z in neu if "ABBRUCH" in z][:1]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_anzahl, test_ec3, test_torsion, test_ermuedung, test_weitere_nachweise,
              test_ergebnisprotokoll, test_runde3, test_kerbfallvorschlag, test_pruefen, test_oberflaeche):
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
    # Kein w.close(): die Rueckfrage „Ungespeicherte Änderungen“ bliebe stehen
    os._exit(0 if n_ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
