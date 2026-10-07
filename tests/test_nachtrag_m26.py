"""
Nachtrag 2 zur Fehlerliste, Eintrag M26 (07.10.2026): Zugfestigkeit f_u von S355.

Das Programm fuehrte f_u von S355 bis 40 mm Erzeugnisdicke seit jeher mit 490 N/mm²,
und Paket Q9 liess S355 und S355W dabei. DIN EN 1993-1-1 Tabelle 3.1 nennt 510. Der
Anwender hat am 07.10.2026 entschieden: S355 bis 40 mm Erzeugnisdicke 510 N/mm²,
S355W (EN 10025-5) ebenso 510 bis 40 mm und 490 von 40 bis 80 mm; S355 von 40 bis
80 mm bleibt 335/470, alle uebrigen Sorten bleiben, wie sie sind.

Was hier festgehalten wird:

* die Tabelle (S355 und S355W an den Dickengrenzen 40 mm, 40,1 mm und 80 mm, alle
  anderen Zeilen unveraendert);
* die Kette Text -> Sorte -> f_u (Importe, Werkstoffdialog, Werkstoff ohne eigenes f_u);
* alte Modelle: f_u ist am Werkstoff gespeichert. Ein Werkstoff der Sorte S355 oder
  S355W mit genau dem bisherigen Tabellenwert 490 folgt beim Oeffnen der neuen Tabelle
  und sagt es im Protokoll; ein anderer Wert (von Hand), eine andere Sorte (S355N hat
  490 nach EN 10025-3), ein Werkstoff ohne Sorte und eine Tabelle nach Dicke aus der
  Quelldatei (RFEM) bleiben;
* die Anschlussnachweise rechnen mit 510 - auch dort, wo f_u fest eingetragen war
  (Rueckfall eines Werkstoffs ohne Angaben, Vorgaben von Naht, Schraube und Vorlage);
* das Handbuch.

Aufruf:  python -m tests.test_nachtrag_m26
"""
import inspect
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_nachtrag_m26_"), "einstellungen.json")

from statik3d.model import Model, Material, STEEL_GRADES  # noqa: E402
from statik3d.importers import _common as C  # noqa: E402

RESULTS = []

#: die Zeile, die die Hinweise beim Oeffnen tragen muessen
ZEILE = "f_u 490 → 510 N/mm² nach EN 1993-1-1 Tab. 3.1"


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def mpa(x):
    return float(x) / 1e6


#: alle Sorten ausser S355 und S355W: (f_y <= 40, f_u <= 40, f_y 40..80, f_u 40..80) in N/mm²,
#: unveraendert gegenueber dem Stand vor M26 (Q9, test_nachtrag_q9.NORM)
UEBRIGE = {
    "S235": (235, 360, 215, 360), "S275": (275, 430, 255, 410),
    "S420": (420, 520, 390, 520), "S460": (460, 540, 430, 540),
    "S275N": (275, 390, 255, 370), "S275NL": (275, 390, 255, 370),
    "S355N": (355, 490, 335, 470), "S355NL": (355, 490, 335, 470),
    "S420N": (420, 520, 390, 520), "S420NL": (420, 520, 390, 520),
    "S460N": (460, 540, 430, 540), "S460NL": (460, 540, 430, 540),
    "S275M": (275, 370, 255, 360), "S275ML": (275, 370, 255, 360),
    "S355M": (355, 470, 335, 450), "S355ML": (355, 470, 335, 450),
    "S420M": (420, 520, 390, 500), "S420ML": (420, 520, 390, 500),
    "S460M": (460, 540, 430, 530), "S460ML": (460, 540, 430, 530),
    "S235W": (235, 360, 215, 340),
}


# --------------------------------------------------------------------------
# die Tabelle
# --------------------------------------------------------------------------
def test_tabelle():
    """S355 und S355W: f_u 510 bis 40 mm; die Dickengrenzen; alles andere bleibt."""
    for g, soll in (("S355", (355, 510, 335, 470)), ("S355W", (355, 510, 335, 490))):
        ist = tuple(mpa(x) for x in STEEL_GRADES[g])
        check(f"{g}: Zeile der Tabelle {soll}", ist == soll, str(ist))
        m = Material.steel(g)
        check(f"{g}: Material.steel traegt f_u {soll[1]} N/mm² und Sorte {g}",
              mpa(m.fu) == soll[1] and m.grade == g, f"{mpa(m.fu)} {m.grade!r}")
        fu = [mpa(m.ultimate_strength(t)) for t in (0.010, 0.040, 0.0401, 0.080)]
        check(f"{g}: f_u bei 10 mm, 40 mm (oben), 40,1 mm und 80 mm (unten) = "
              f"{soll[1]}, {soll[1]}, {soll[3]}, {soll[3]}",
              fu == [soll[1], soll[1], soll[3], soll[3]], str(fu))
        fy = [mpa(m.yield_strength(t)) for t in (0.010, 0.040, 0.0401, 0.080)]
        check(f"{g}: f_y unveraendert {soll[0]} bis 40 mm und {soll[2]} darueber",
              fy == [soll[0], soll[0], soll[2], soll[2]], str(fy))
    check("S355 ohne eigenes f_u: die Sorte gibt 510 (10 mm) und 470 (50 mm)",
          (mpa(Material("Stahl", grade="S355").ultimate_strength(0.010)),
           mpa(Material("Stahl", grade="S355").ultimate_strength(0.050))) == (510.0, 470.0))
    check("S355W ohne eigenes f_u: die Sorte gibt 510 (10 mm) und 490 (50 mm)",
          (mpa(Material("Stahl", grade="S355W").ultimate_strength(0.010)),
           mpa(Material("Stahl", grade="S355W").ultimate_strength(0.050))) == (510.0, 490.0))
    for g, soll in UEBRIGE.items():
        ist = tuple(mpa(x) for x in STEEL_GRADES.get(g, ()))
        check(f"{g} bleibt {soll}", ist == soll, str(ist))
    check("die Tabelle fuehrt genau diese Sorten (keine neue, keine fehlt)",
          set(STEEL_GRADES) == set(UEBRIGE) | {"S355", "S355W"}, str(sorted(set(STEEL_GRADES) ^ set(UEBRIGE))))


def test_kette():
    """Text -> Sorte -> f_u: die Wege, auf denen ein Werkstoff zu seiner Zugfestigkeit kommt."""
    for text, sorte, fu10, fu50 in (
            ("S355", "S355", 510, 470), ("S355J2", "S355", 510, 470), ("S355J2+N", "S355", 510, 470),
            ("Baustahl s 355", "S355", 510, 470), ("S355J2W", "S355W", 510, 490),
            ("S355K2W", "S355W", 510, 490),
            ("S355N", "S355N", 490, 470), ("S355NL", "S355NL", 490, 470), ("S355M", "S355M", 470, 450),
            ("S235", "S235", 360, 360), ("S275", "S275", 430, 410)):
        g = C.steel_grade_from_text(text)
        if g not in STEEL_GRADES:
            check(f"{text!r}: Sorte {g!r} steht in der Tabelle", False)
            continue
        m = Material.steel(g)
        ist = (g, mpa(m.ultimate_strength(0.010)), mpa(m.ultimate_strength(0.050)))
        check(f"{text!r} -> {sorte}: f_u {fu10} (10 mm) und {fu50} (50 mm)", ist == (sorte, fu10, fu50), str(ist))
    # so legen die Importe einen Werkstoff an
    mo = Model("Import")
    C.ensure_material(mo, "Baustahl S355J2", quiet=True)
    mt = mo.materials["Baustahl S355J2"]
    check("ensure_material: „Baustahl S355J2“ ist S355 mit f_u 510 und f_y 355",
          mt.grade == "S355" and mpa(mt.fu) == 510.0 and mpa(mt.fy) == 355.0, f"{mt.grade!r} {mt.fu}")
    mo2 = Model("Import2")
    C.ensure_material(mo2, "S355J2W", quiet=True)
    mt = mo2.materials["S355J2W"]
    check("ensure_material: „S355J2W“ ist S355W mit f_u 510 (10 mm) und 490 (50 mm)",
          mt.grade == "S355W" and (mpa(mt.ultimate_strength(0.010)), mpa(mt.ultimate_strength(0.050))) == (510.0, 490.0),
          f"{mt.grade!r} {mt.fu}")
    # der Werkstoffdialog setzt die Werte der Sorte ein
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    d = dg.MaterialDialog(None)
    d._grade_changed("S355")
    check("Dialog: die Sorte S355 setzt f_y 355 und f_u 510 ein", (d.fy.value(), d.fu.value()) == (355.0, 510.0),
          f"{d.fy.value()} {d.fu.value()}")
    d._grade_changed("S355W")
    check("Dialog: die Sorte S355W setzt f_u 510 ein", d.fu.value() == 510.0, f"{d.fu.value()}")
    d._grade_changed("S355N")
    check("Dialog: die Sorte S355N bleibt bei f_u 490", d.fu.value() == 490.0, f"{d.fu.value()}")
    d.deleteLater()
    del app


# --------------------------------------------------------------------------
# alte Modelle
# --------------------------------------------------------------------------
def _alte_datei(werkstoffe):
    """Eine Datei, wie sie vor M26 gespeichert wurde: {Name: Material} mit dem f_u,
    das jeweils am Werkstoff steht. Rueckgabe: (Pfad, Dateiinhalt als dict)."""
    m = Model("Alt")
    for name, mt in werkstoffe.items():
        m.materials[name] = mt
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_m26_"), "alt.json")
    m.save(pfad)
    with open(pfad, encoding="utf-8") as f:
        return pfad, json.load(f)


def _s(grade, fu, **kw):
    """Werkstoff der Sorte mit f_y wie die Tabelle und dem gegebenen f_u."""
    return Material(kw.pop("name", "Stahl"), 210e9, 0.3, 7850.0, 1.2e-5, 355e6, fu, grade, **kw)


def _zeilen(m):
    return [z for z in getattr(m, "_ladehinweise", []) if "f_u" in z]


def test_altes_modell():
    """Das Oeffnen stellt einen Tabellenwert 490 der Sorten S355 und S355W auf die neue
    Tabelle um und sagt es im Protokoll; alles andere bleibt."""
    pfad, _d = _alte_datei({
        "A": _s("S355", 490e6, name="A"),
        "B": _s("S355W", 490e6, name="B"),
        "C": _s("S355", 500e6, name="C"),                   # von Hand: anderer Wert
        "D": _s("S355N", 490e6, name="D"),                  # 490 ist dort die Tabelle (EN 10025-3)
        "E": _s("S235", 490e6, name="E"),                   # von Hand
        "F": _s("S355", 490e6, name="F", fu_dicke=[[0.016, 490e6], [0.040, 490e6], [0.063, 470e6]]),
        "G": _s("", 490e6, name="G"),                       # keine Sorte
        "H": Material("H", 210e9, 0.3, 7850.0, 1.2e-5, None, None, "S355"),   # f_u kommt zur Laufzeit
        "I": _s("S355M", 470e6, name="I"),
        "J": _s("S355", 510e6, name="J"),                   # schon die neue Tabelle
        "S355": _s("S355", 490e6, name="S355"),             # Name wie die Sorte
    })
    m = Model.load(pfad)
    fu = {n: mpa(mt.fu) if mt.fu else None for n, mt in m.materials.items()}
    check("S355 mit f_u 490 wird 510", fu["A"] == 510.0, str(fu["A"]))
    check("S355W mit f_u 490 wird 510", fu["B"] == 510.0, str(fu["B"]))
    check("S355 mit eingetragenem f_u 500 (von Hand) bleibt 500", fu["C"] == 500.0, str(fu["C"]))
    check("S355N mit f_u 490 bleibt 490 (Tabellenwert von EN 10025-3)", fu["D"] == 490.0, str(fu["D"]))
    check("S235 mit f_u 490 (von Hand) bleibt 490", fu["E"] == 490.0, str(fu["E"]))
    check("S355 mit Tabelle nach Dicke aus der Quelldatei bleibt bei 490 und behaelt die Tabelle",
          fu["F"] == 490.0 and m.materials["F"].fu_dicke == [[0.016, 490e6], [0.040, 490e6], [0.063, 470e6]],
          f"{fu['F']} {m.materials['F'].fu_dicke}")
    check("ein Werkstoff ohne Sorte mit f_u 490 bleibt 490", fu["G"] == 490.0, str(fu["G"]))
    check("S355 ohne gespeichertes f_u bleibt ohne f_u (die Sorte gibt es zur Laufzeit: 510)",
          fu["H"] is None and mpa(m.materials["H"].ultimate_strength(0.010)) == 510.0,
          f"{fu['H']} {mpa(m.materials['H'].ultimate_strength(0.010))}")
    check("S355M mit f_u 470 bleibt 470", fu["I"] == 470.0, str(fu["I"]))
    check("S355 mit f_u 510 bleibt 510", fu["J"] == 510.0, str(fu["J"]))
    z = _zeilen(m)
    check("das Protokoll nennt genau drei Werkstoffe (A, B und S355), je mit der Zeile der Tabelle",
          len(z) == 3 and all(ZEILE in x for x in z)
          and any(x.startswith("Werkstoff A (S355): ") for x in z)
          and any(x.startswith("Werkstoff B (S355W): ") for x in z)
          and any(x.startswith("Werkstoff S355: ") for x in z), str(z))
    check("die Rechnung nimmt den neuen Wert: ultimate_strength(10 mm) von A = 510",
          mpa(m.materials["A"].ultimate_strength(0.010)) == 510.0)
    # gespeichert und wieder geoeffnet: nichts mehr umzustellen
    pfad2 = os.path.join(tempfile.mkdtemp(prefix="statik3d_m26_"), "neu.json")
    m.save(pfad2)
    m2 = Model.load(pfad2)
    check("nach dem Speichern steht 510 in der Datei, und das erneute Oeffnen meldet nichts",
          mpa(m2.materials["A"].fu) == 510.0 and not _zeilen(m2), str(_zeilen(m2)))
    # nur das Oeffnen stellt um, nicht from_dict: das tragen auch die Arbeiter der Rechnung und die
    # Nachweispakete (jobs.py) vom Modell im Speicher zu ihrem Prozess - dort muss der Werkstoff
    # genau so ankommen, wie er hier steht (ein von Hand gesetztes 490 bleibt 490)
    m3 = Model.from_dict(_d)
    check("from_dict stellt nichts um (Modell im Speicher, Arbeiterprozess): f_u 490 bleibt, keine Zeile",
          mpa(m3.materials["A"].fu) == 490.0 and not _zeilen(m3), f"{mpa(m3.materials['A'].fu)} {_zeilen(m3)}")
    mm = Model("Speicher")
    mm.materials["S355"] = _s("S355", 490e6, name="S355")      # von Hand gesetzt in dieser Sitzung
    check("Umlauf to_dict/from_dict im Speicher: ein von Hand gesetztes f_u 490 bleibt 490",
          mpa(Model.from_dict(mm.to_dict()).materials["S355"].fu) == 490.0)


def test_altes_modell_importieren():
    """Der Weg „Importieren“ einer Modelldatei sagt dasselbe wie das Oeffnen - auch beim Anhaengen."""
    from statik3d import importers
    pfad, _d = _alte_datei({"A": _s("S355", 490e6, name="A")})
    log = []
    mi = importers.import_file(pfad, log=log)
    check("Importieren: f_u 510 und die Zeile im Protokoll",
          mpa(mi.materials["A"].fu) == 510.0 and any(str(z).startswith("Hinweis: Werkstoff A (S355):")
                                                       and ZEILE in str(z) for z in log), str(log[:4]))
    ziel = Model("Ziel")
    ziel.add_material(Material.steel("S235", "Basis"))
    log2 = []
    mz = importers.import_file(pfad, model=ziel, log=log2)
    fu = [mpa(mt.fu) for mt in mz.materials.values() if mt.grade == "S355"]
    check("Anhaengen: f_u 510 und die Zeile im Protokoll", fu and all(x == 510.0 for x in fu)
          and any(ZEILE in str(z) for z in log2), f"{fu} {log2[:4]}")
    # Browser: ein hochgeladenes Modell ist eine geoeffnete Datei
    from statik3d.web import server
    st = server.State()
    server.replace_model(st, _d)
    check("Browser (Modell laden): f_u 510 und die Zeile im Protokoll des Servers",
          mpa(st.model.materials["A"].fu) == 510.0 and any("Hinweis: Werkstoff A (S355): " in z and ZEILE in z
                                                           for z in st.log), str(st.log[-3:]))
    # Kommandozeile: ``python -m statik3d.cli <Modelldatei>`` sagt es ebenso (ohne --still)
    import subprocess
    r = subprocess.run([sys.executable, "-m", "statik3d.cli", pfad], capture_output=True, text=True,
                       encoding="utf-8", timeout=300,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    check("Kommandozeile: die Zeile steht in der Ausgabe (die Datei hat kein Netz, die Rechnung bricht danach ab)",
          "Hinweis: Werkstoff A (S355): " in r.stdout and ZEILE in r.stdout,
          " | ".join((r.stdout[:200] + r.stderr[-200:]).splitlines()))


def test_ergebnisdatei_alter_modelle():
    """Hat das Oeffnen f_u umgestellt, passt die Ergebnisdatei von vor der Umstellung nicht mehr zum
    Modell (die Anschlussnachweise haengen an f_u): sie wird nicht geladen, und der Grund nennt die
    Werkstoffe. Ein Werkstoff, der nichts umstellt, laedt seine Ergebnisse wie bisher."""
    from statik3d import solver, examples_lib, ergebnisse as erg
    for umstellen in (True, False):
        m = examples_lib.build_example("frame")
        mt = m.materials["S355"]
        mt.grade = "S355"
        mt.fu = 490e6 if umstellen else 500e6          # 500: von Hand, bleibt
        pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_m26_erg_"), "alt.json")
        an = solver.solve_all(m)
        m.save(pfad)
        erg.schreiben(erg.pfad_zu(pfad), m, an)
        g = Model.load(pfad)
        try:
            erg.lesen(erg.pfad_zu(pfad), g)
            grund = ""
        except ValueError as ex:
            grund = str(ex)
        if umstellen:
            check("alte Datei mit Ergebnissen: f_u umgestellt, die Ergebnisse passen nicht mehr (Werkstoffe)",
                  mpa(g.materials["S355"].fu) == 510.0 and "Werkstoffe" in grund, grund)
        else:
            check("Datei ohne Umstellung (f_u 500 von Hand): die Ergebnisse werden geladen",
                  mpa(g.materials["S355"].fu) == 500.0 and not grund, grund)


# --------------------------------------------------------------------------
# Anschluesse
# --------------------------------------------------------------------------
def _hall_mit_anschluessen():
    from statik3d import examples_lib
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose
    m = examples_lib.build_example("hall")
    r = m.members["Riegel"]
    e_kopf, e_lasche = r.elements[0], r.elements[len(r.elements) // 2]
    m.joints["K1"] = A.als_joint(propose("kopfplatte", m, e_kopf, end=0, N=-50e3, Vz=150e3, My=300e3), "K1")
    m.joints["S1"] = A.als_joint(propose("lasche", m, e_lasche, end=1, N=-50e3, Vz=50e3, My=200e3), "S1")
    return m


def _widerstaende(m, name, **kraefte):
    from statik3d.joints import anschluss as A
    j = A.vorlage(m, m.joints[name]).design(**kraefte)
    return {c.name: c.R for c in j.checks}


def test_anschluesse_rechnen_mit_510():
    """Die Nachweise, die f_u brauchen, wachsen mit 510/490; die mit f_y bleiben."""
    m = _hall_mit_anschluessen()
    check("Hallenrahmen: der Werkstoff S355 traegt f_u 510", mpa(m.materials["S355"].fu) == 510.0,
          str(mpa(m.materials["S355"].fu)))
    m490 = _hall_mit_anschluessen()
    m490.materials["S355"].fu = 490e6          # von Hand eingetragen: so rechnete der Stand davor
    kopf = dict(N=-50e3, Vz=150e3, My=300e3)
    neu, alt = _widerstaende(m, "K1", **kopf), _widerstaende(m490, "K1", **kopf)
    faktor = 510.0 / 490.0
    for n in ("Lochleibung F_b,Rd", "Durchstanzen B_p,Rd", "Kehlnaht am Flansch: Vergleichsspannung",
              "Kehlnaht am Steg: Vergleichsspannung"):
        check(f"Kopfplatte: {n} waechst mit f_u (510/490)", n in neu and abs(neu[n] / alt[n] - faktor) < 1e-9,
              f"{neu.get(n, 0):.6g} / {alt.get(n, 0):.6g}")
    for n in ("Abscheren F_v,Rd", "Zug F_t,Rd"):
        check(f"Kopfplatte: {n} haengt an der Schraube und bleibt", n in neu and neu[n] == alt[n])
    lasche = dict(N=-50e3, Vz=50e3, My=200e3)
    neu, alt = _widerstaende(m, "S1", **lasche), _widerstaende(m490, "S1", **lasche)
    for n in ("Lasche: Zug Nettoquerschnitt N_u,Rd", "Flansch des Traegers: Zug Nettoquerschnitt N_u,Rd",
              "Lochleibung F_b,Rd"):
        check(f"Laschenstoss: {n} waechst mit f_u (510/490)", n in neu and abs(neu[n] / alt[n] - faktor) < 1e-9,
              f"{neu.get(n, 0):.6g} / {alt.get(n, 0):.6g}")
    check("Laschenstoss: die Bruttoquerschnitt-Tragfaehigkeit (f_y) bleibt",
          neu["Lasche: Zug Bruttoquerschnitt N_pl,Rd"] == alt["Lasche: Zug Bruttoquerschnitt N_pl,Rd"])


def test_anschluesse_fest_eingetragene_werte():
    """Wo f_u fest im Quelltext stand (Rueckfall ohne Werkstoffangaben, Vorgaben), gilt die Tabelle."""
    import statik3d.joints.design as design
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose, JointTemplate
    from statik3d.joints.welds import Fillet, Butt
    f510 = 510e6
    check("die Sortentabelle gibt S355 510 N/mm² (Bezug der folgenden Pruefungen)",
          STEEL_GRADES["S355"][1] == f510, str(STEEL_GRADES["S355"][1]))
    check("Vorgabe der Kehlnaht (Fillet) ist f_u von S355", Fillet(a=0.005, length=0.3).fu == f510,
          str(Fillet(a=0.005, length=0.3).fu))
    check("Vorgabe der Stumpfnaht (Butt) ist f_u von S355", Butt(thickness=0.010, length=0.3).fu == f510,
          str(Butt(thickness=0.010, length=0.3).fu))
    check("Vorgabe der Anschlussvorlage (JointTemplate) ist f_u von S355", JointTemplate().fu == f510,
          str(JointTemplate().fu))
    check("Vorgabe des Schraubennachweises (check_bolt, f_u des Blechs) ist f_u von S355",
          inspect.signature(design.check_bolt).parameters["fu"].default == f510,
          str(inspect.signature(design.check_bolt).parameters["fu"].default))
    # ein Werkstoff ohne f_u, f_y und Sorte: die Anschluesse nehmen S355 - mit f_u 510
    m = _hall_mit_anschluessen()
    m.materials["S355"] = Material("S355")
    t = A.vorlage(m, m.joints["K1"])
    check("Anschluss aus einem Werkstoff ohne Angaben: Sorte S355, f_y 355, f_u 510",
          (t.grade, mpa(t.fy), mpa(t.fu)) == ("S355", 355.0, 510.0), f"{t.grade} {mpa(t.fy)} {mpa(t.fu)}")
    r = m.members["Riegel"]
    e = r.elements[0]
    for art, kw in (("kopfplatte", dict(end=0, N=-50e3, Vz=100e3, My=100e3)),
                    ("lasche", dict(end=1, N=-50e3, Vz=50e3, My=100e3)),
                    ("diagonale", dict(end=1, N=100e3))):
        p = propose(art, m, e, **kw)
        check(f"Vorschlag „{art}“ aus einem Werkstoff ohne Angaben: f_u 510", p.fu == f510, f"{mpa(p.fu)}")


def test_beispiele():
    """Die Beispiele von examples_lib: wer die Sortentabelle nutzt, hat 510; wer f_y selbst tragt, bleibt."""
    from statik3d import examples_lib
    for name in ("hall", "gate"):
        mt = examples_lib.build_example(name).materials["S355"]
        check(f"Beispiel {name}: S355 aus der Tabelle, f_u 510 (10 mm) und 470 (50 mm)",
              (mpa(mt.ultimate_strength(0.010)), mpa(mt.ultimate_strength(0.050))) == (510.0, 470.0),
              f"{mpa(mt.ultimate_strength(0.010))}")
    for name in ("frame", "truss", "plate", "solid"):
        m = examples_lib.build_example(name)
        mt = next(iter(m.materials.values()))
        if name in ("frame", "truss", "solid"):
            check(f"Beispiel {name}: Werkstoff mit eigenem f_y ohne Sorte, f_u = 1,3 f_y bleibt",
                  mpa(mt.ultimate_strength(0.010)) == 461.5 and not mt.grade, f"{mpa(mt.ultimate_strength(0.010))}")
    for name in ("contact", "friction"):
        mt = examples_lib.build_example(name).materials["S235"]
        check(f"Beispiel {name}: S235 bleibt bei f_u 360", mpa(mt.ultimate_strength(0.010)) == 360.0)


def test_handbuch():
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
                        "Benutzerhandbuch.md")
    with open(pfad, encoding="utf-8") as f:
        text = " ".join(f.read().split())
    check("Handbuch: der Absatz „Zugfestigkeit von S355 und S355W“ nennt 510 und die Norm",
          "**Zugfestigkeit von S355 und S355W.**" in text and "510 N/mm²" in text
          and "DIN EN 1993-1-1 Tabelle 3.1" in text)
    check("Handbuch: nennt den Stand vor dem 07.10.2026 (490)",
          "Bis zum 07.10.2026 stand f_u von S355 und S355W bis 40 mm bei 490 N/mm²" in text)
    check("Handbuch: nennt die Umstellung alter Dateien samt Protokollzeile und was bleibt",
          ZEILE in text and "von Hand eingetragener" in text and "S355N" in text)
    check("Handbuch: nennt den Wert von 40 bis 80 mm (S355 470, S355W 490)",
          "S355 470 und S355W 490 N/mm²" in text)
    check("Handbuch: die Kopfplatten-Zahlen (Druckflansch ab 320 kNm bei N = −100 kN, vorher 300) sind nachgezogen",
          "ab 320 kNm (N = −100 kN, η = 0,993)" in text and "Bis zum 07.10.2026 war er bei N = −100 kN schon ab 300 kNm"
          in text and "ab 300 kNm (N = −100 kN, η = 0,933)" not in text)


def main():
    for t in (test_tabelle, test_kette, test_altes_modell, test_altes_modell_importieren,
              test_ergebnisdatei_alter_modelle, test_anschluesse_rechnen_mit_510, test_anschluesse_fest_eingetragene_werte, test_beispiele,
              test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
