"""
Nachtrag zur Fehlerliste vom 06.10.2026, Paket Q9 (07.10.2026): Werkstoff.

* N06 test_n06_*: ``steel_grade_from_text`` machte aus „S355N“, „S355M“, „S275N“,
  „S235W“ ... einfach S355, S275, S235 (der Suchausdruck las nur die Zahl). Damit
  galten die Werte der Zeile EN 10025-2 auch fuer Sorten nach EN 10025-3 (N, NL),
  EN 10025-4 (M, ML) und EN 10025-5 (W). Gemessen am Ausgangsstand 63acb15: f_u
  von S355M 490/470 N/mm² statt 470/450, von S275N 430/410 statt 390/370 (jeweils
  <= 40 mm / 40 bis 80 mm), von S235W bei t > 40 mm 360 statt 340 - alles auf der
  unsicheren Seite. Jetzt kennt die Sortentabelle diese Zeilen, und der Text wird
  nach seinem Zusatz gelesen. Was die Tabelle nicht fuehrt (S235N, S275W, S355J0WP),
  ist unbekannt und bekommt keine erfundenen Werte.
* N07 test_n07_*: f_y = 0 in der Werkstofftabelle, der Werkstoffmaske und dem
  Werkstoffdialog wurde still zu „leer“ (Material.fy = 0.0, im Dialog None). Jetzt
  ist 0 (und alles <= 0) ein Eingabefehler, und „leer“ ist davon getrennt: eine
  leer getippte Zelle der Tabelle heisst „kein f_y“ (None), und eine Zelle ohne
  f_y zeigt „“ statt „0“.

Normwerte (Streckgrenze f_y und Zugfestigkeit f_u in N/mm², je Zeile
``(f_y bis 40 mm, f_u bis 40 mm, f_y 40 bis 80 mm, f_u 40 bis 80 mm)``): DIN EN
1993-1-1 Tabelle 3.1. Das Normblatt selbst lag nicht vor; die Werte stammen aus
zwei unabhaengigen Wiedergaben der Tabelle, am 07.10.2026 gelesen:

* Blueprints, ``blueprints/codes/eurocode/en_1993_1_1_2005/chapter_3_materials/
  table_3_1.py`` (https://github.com/Blueprints-org/blueprints), Tabelle
  ``Table3Dot1NominalValuesHotRolledStructuralSteel``;
* Bentley STAAD.Pro Help, Tabelle „Streckgrenze und Zugfestigkeit“ nach
  EN 1993-1-1 Tab. 3.1 (https://docs.bentley.com/LiveContent/web/STAAD.Pro%20Help-v20/
  ja/GUID-977421E0-6039-4A98-B068-D91E10FFFBA0.html; Zeilen S355 EN 10025-2/-3/-4/-5).

Beide stimmen in allen hier benutzten Zeilen ueberein. Nicht belegt war f_u der
Sorten S355 und S355 W bis 40 mm: Bentley vermerkt, die Tabelle der franzoesischen
Fassung unterscheide sich von der des EC3 gerade in diesen beiden Werten (der
Satzwert des EC3 soll 510 sein, nicht 490). Q9 liess beide bei 490 (S355 seit jeher
490/470, S355W 490/490). Der Anwender hat am 07.10.2026 entschieden: 510 nach
Tabelle 3.1 (Nachtrag M26, tests/test_nachtrag_m26.py); NORM unten fuehrt seitdem
S355 mit 510/470 und S355W mit 510/490.

Aufruf:  python -m tests.test_nachtrag_q9
"""
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_nachtrag_q9_"), "einstellungen.json")

from statik3d.model import Model, Material, STEEL_GRADES  # noqa: E402
from statik3d.importers import _common as C  # noqa: E402

try:                    # fehlt am Ausgangsstand 63acb15: dann schlaegt nur diese Gruppe fehl
    from statik3d.model import stahlsorte_schluessel, stahlsorte_norm
except ImportError:
    from statik3d.model import stahlsorte_schluessel
    stahlsorte_norm = None

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def mpa(x):
    return float(x) / 1e6


# --------------------------------------------------------------------------
# Normwerte: EN 1993-1-1 Tabelle 3.1 (Quellen im Kopf dieser Datei)
# --------------------------------------------------------------------------
#: Schluessel der Sortentabelle -> (Erzeugnisnorm, f_y <= 40, f_u <= 40, f_y 40..80, f_u 40..80)
NORM = {
    # EN 10025-2
    "S235": ("EN 10025-2", 235, 360, 215, 360),
    "S275": ("EN 10025-2", 275, 430, 255, 410),
    "S355": ("EN 10025-2", 355, 510, 335, 470),
    # EN 10025-3, normalgeglueht (N) und mit Kerbschlagarbeit bei tiefer Temperatur (NL)
    "S275N": ("EN 10025-3", 275, 390, 255, 370), "S275NL": ("EN 10025-3", 275, 390, 255, 370),
    "S355N": ("EN 10025-3", 355, 490, 335, 470), "S355NL": ("EN 10025-3", 355, 490, 335, 470),
    "S420N": ("EN 10025-3", 420, 520, 390, 520), "S420NL": ("EN 10025-3", 420, 520, 390, 520),
    "S460N": ("EN 10025-3", 460, 540, 430, 540), "S460NL": ("EN 10025-3", 460, 540, 430, 540),
    # EN 10025-4, thermomechanisch gewalzt (M, ML)
    "S275M": ("EN 10025-4", 275, 370, 255, 360), "S275ML": ("EN 10025-4", 275, 370, 255, 360),
    "S355M": ("EN 10025-4", 355, 470, 335, 450), "S355ML": ("EN 10025-4", 355, 470, 335, 450),
    "S420M": ("EN 10025-4", 420, 520, 390, 500), "S420ML": ("EN 10025-4", 420, 520, 390, 500),
    "S460M": ("EN 10025-4", 460, 540, 430, 530), "S460ML": ("EN 10025-4", 460, 540, 430, 530),
    # EN 10025-5, wetterfest (W)
    "S235W": ("EN 10025-5", 235, 360, 215, 340),
    "S355W": ("EN 10025-5", 355, 510, 335, 490),
}

#: Die Zeilen S420 und S460 ohne Zusatz gab es schon: sie tragen die Werte der Zeilen
#: N/NL (EN 10025-2 kennt sie nicht). Unveraendert.
ALT = {"S420": (420, 520, 390, 520), "S460": (460, 540, 430, 540)}


def _werte(g):
    """(f_y 10 mm, f_u 10 mm, f_y 50 mm, f_u 50 mm) der Sorte g in N/mm² - ueber das Material."""
    m = Material.steel(g)
    return (mpa(m.yield_strength(0.010)), mpa(m.ultimate_strength(0.010)),
            mpa(m.yield_strength(0.050)), mpa(m.ultimate_strength(0.050)))


# --------------------------------------------------------------------------
# N06
# --------------------------------------------------------------------------
def test_n06_text_zu_sorte():
    """Der Text wird nach seinem Zusatz gelesen: N, NL, M, ML und W aendern die
    Sorte; J0, J2, JR, K2, „+N“ und Fuellwoerter nicht."""
    faelle = [
        # die Eintraege des Auftrags
        ("S355N", "S355N"), ("S355NL", "S355NL"), ("S355M", "S355M"), ("S355ML", "S355ML"),
        ("S460N", "S460N"), ("S460M", "S460M"), ("S355J2", "S355"), ("S355J2+N", "S355"),
        ("S355W", "S355W"),
        # Schreibweise: Gross/klein, Leerzeichen, Trennstriche
        ("s355n", "S355N"), ("S 355 NL", "S355NL"), ("s  355  m", "S355M"), ("Stahl S 420 N", "S420N"),
        ("Baustahl S275_ML", "S275ML"), ("S355-N", "S355N"),
        # W nach EN 10025-5 steht hinter der Guetegruppe
        ("S355J2W", "S355W"), ("S355K2W", "S355W"), ("S235J0W", "S235W"), ("S235J2W", "S235W"),
        # EN 10025-2 bleibt EN 10025-2 (auch mit Lieferzustand und Fuellwort)
        ("S 235 JR", "S235"), ("S275J0", "S275"), ("S355J2+N", "S355"), ("S355K2+N", "S355"),
        ("S355 Blech", "S355"), ("Baustahl s275", "S275"), ("S355 Mat. 1", "S355"), ("S235", "S235"),
        ("S420", "S420"), ("S460", "S460"),
        # Hohlprofilsorten (EN 10210/10219): Tabelle 3.1 fuehrt sie mit eigenen Werten, die sich nicht
        # eindeutig einer der beiden Normen zuordnen lassen - sie bleiben, wie sie waren
        ("S355J2H", "S355"), ("S355NH", "S355"), ("S355MH", "S355"),
    ]
    for text, soll in faelle:
        ist = C.steel_grade_from_text(text)
        check(f"steel_grade_from_text({text!r}) = {soll}", ist == soll, repr(ist))


def test_n06_unbekannt_ohne_erfundene_werte():
    """Was die Tabelle 3.1 nicht fuehrt, ist unbekannt (None) - der Import
    verfaehrt dann wie mit jeder unbekannten Sorte. Bis zum 07.10.2026 bekam es
    still die Werte der Zeile ohne Zusatz."""
    for text in ("S235N", "S235M", "S235ML", "S275W", "S420W", "S355J0WP", "S355J2WP", "S500", "S450J0",
                 "", None, "Beton C30/37"):
        ist = C.steel_grade_from_text(text)
        check(f"steel_grade_from_text({text!r}) ist unbekannt", ist is None, repr(ist))
    # und die Tabelle selbst erfindet nichts
    for g in ("S235N", "S275W", "S355J0WP", "S355J2"):
        check(f"stahlsorte_schluessel({g!r}) ist unbekannt", stahlsorte_schluessel(g) is None,
              repr(stahlsorte_schluessel(g)))
    try:
        Material.steel("S235N")
        check("Material.steel(\"S235N\") wirft KeyError", False)
    except KeyError:
        check("Material.steel(\"S235N\") wirft KeyError", True)


def test_n06_normwerte():
    """Jede Zeile der Sortentabelle gegen Tabelle 3.1: f_y und f_u bis 40 mm und
    von 40 bis 80 mm, auch an den Grenzen der Dicke."""
    for g, (norm, fy40, fu40, fy80, fu80) in NORM.items():
        check(f"Sortentabelle fuehrt {g}", g in STEEL_GRADES)
        if g not in STEEL_GRADES:
            continue
        t = STEEL_GRADES[g]
        ist = tuple(mpa(x) for x in t)
        check(f"{g} ({norm}): {fy40}/{fu40} bis 40 mm, {fy80}/{fu80} von 40 bis 80 mm",
              ist == (fy40, fu40, fy80, fu80), str(ist))
        m = Material.steel(g)
        ueber = (mpa(m.yield_strength(0.040)), mpa(m.ultimate_strength(0.040)),
                 mpa(m.yield_strength(0.0401)), mpa(m.ultimate_strength(0.0401)),
                 mpa(m.yield_strength(0.080)), mpa(m.ultimate_strength(0.080)))
        check(f"{g}: Dickengrenzen 40 mm (oben) / 40,1 mm (unten) / 80 mm (unten)",
              ueber == (fy40, fu40, fy80, fu80, fy80, fu80), str(ueber))
    for g, w in ALT.items():
        ist = tuple(mpa(x) for x in STEEL_GRADES[g])
        check(f"{g} ohne Zusatz unveraendert {w}", ist == w, str(ist))
    # N und NL, M und ML tragen dieselben Werte
    for z in ("S275", "S355", "S420", "S460"):
        check(f"{z}N = {z}NL und {z}M = {z}ML", STEEL_GRADES.get(z + "N") == STEEL_GRADES.get(z + "NL")
              and STEEL_GRADES.get(z + "M") == STEEL_GRADES.get(z + "ML"))
    # die alten Zeilen blieben vorn: der rfem6-Import nimmt zu einem f_y die erste passende Sorte
    check("Reihenfolge: die fuenf alten Sorten stehen vor den neuen",
          list(STEEL_GRADES)[:5] == ["S235", "S275", "S355", "S420", "S460"], str(list(STEEL_GRADES)[:6]))


def test_n06_kette_text_zu_werten():
    """Der ganze Weg des Imports: Text -> Sorte -> f_y und f_u (auch nach Dicke)
    gegen die Norm. Hier schlug der Ausgangsstand an: „S355M“ rechnete mit f_u 490."""
    texte = ["S355N", "S355NL", "S355M", "S355ML", "S460N", "S460M", "S355J2", "S355J2+N", "S355W"]
    print(f"     {'Text':10s} {'Sorte':8s}  f_y/f_u bei 10 mm   bei 50 mm")
    for text in texte:
        g = C.steel_grade_from_text(text)
        if g is None or g not in STEEL_GRADES:
            check(f"{text}: Sorte {g!r} ist in der Tabelle", False)
            continue
        w = _werte(g)
        print(f"     {text:10s} {g:8s}  {w[0]:g}/{w[1]:g}            {w[2]:g}/{w[3]:g}")
        # die Norm zum Text: J2 und +N gehoeren zur Zeile ohne Zusatz
        zeile = NORM.get(g)
        if zeile is None:
            check(f"{text}: Zeile der Norm vorhanden", False, g)
            continue
        soll = (zeile[1], zeile[2], zeile[3], zeile[4])
        check(f"{text} -> {g}: f_y/f_u {soll[0]}/{soll[1]} (10 mm) und {soll[2]}/{soll[3]} (50 mm)",
              w == soll, str(w))
    # Sicherheit: kein Wert liegt ueber dem der Norm (Ausgangsstand: S355M 490 statt 470)
    for text, f_u_norm in (("S355M", 470), ("S355ML", 470), ("S460M", 540), ("S275N", 390), ("S275M", 370),
                           ("S420M", 520)):
        g = C.steel_grade_from_text(text)
        check(f"{text}: f_u bis 40 mm = {f_u_norm} (nicht mehr als die Norm)",
              g in STEEL_GRADES and mpa(Material.steel(g).ultimate_strength(0.010)) == f_u_norm,
              f"{g} {mpa(Material.steel(g).ultimate_strength(0.010)) if g in STEEL_GRADES else '-'}")
    for text, f_u_norm in (("S355M", 450), ("S460M", 530), ("S275N", 370), ("S275M", 360), ("S235W", 340),
                           ("S420M", 500)):
        g = C.steel_grade_from_text(text)
        check(f"{text}: f_u von 40 bis 80 mm = {f_u_norm}",
              g in STEEL_GRADES and mpa(Material.steel(g).ultimate_strength(0.050)) == f_u_norm,
              f"{g} {mpa(Material.steel(g).ultimate_strength(0.050)) if g in STEEL_GRADES else '-'}")


def test_n06_schreibweise_und_material():
    """Die Schluessel der neuen Zeilen vertragen Gross/klein und Leerzeichen
    (F08), und ein Werkstoff mit solcher Sorte rechnet mit ihren Werten."""
    for eingabe, soll in (("s355m", "S355M"), (" S 355 ML ", "S355ML"), ("s 460 n", "S460N"),
                          ("S235 w", "S235W"), ("s\t275\tnl", "S275NL")):
        check(f"stahlsorte_schluessel({eingabe!r}) = {soll}", stahlsorte_schluessel(eingabe) == soll,
              repr(stahlsorte_schluessel(eingabe)))
    mt = Material("Stahl", grade=" s 355 m ")
    check("Material(grade=' s 355 m ') heisst S355M", mt.grade == "S355M", repr(mt.grade))
    check("… f_y leer: die Sorte gibt f_y 355 / f_u 470 (10 mm) und 335 / 450 (50 mm)",
          (mpa(mt.yield_strength(0.010)), mpa(mt.ultimate_strength(0.010)),
           mpa(mt.yield_strength(0.050)), mpa(mt.ultimate_strength(0.050))) == (355, 470, 335, 450))
    # Datei: eine Sorte mit Zusatz bleibt beim Laden erhalten
    m = Model("Datei")
    m.add_material(Material.steel("S355ML", "Stahl"))
    geladen = Model.from_dict(m.to_dict()).materials["Stahl"]
    check("Datei: S355ML bleibt S355ML und f_u 470", geladen.grade == "S355ML"
          and mpa(geladen.ultimate_strength(0.010)) == 470.0, f"{geladen.grade!r}")


def test_n06_import_und_namen():
    """ensure_material (so legen die Importe einen Werkstoff an) und der Name der
    Sorte, den rfem6_db aus einem f_y bildet."""
    m = Model("Import")
    C.ensure_material(m, "Baustahl s 355 m", quiet=True)
    mt = m.materials["Baustahl s 355 m"]
    check("ensure_material: „Baustahl s 355 m“ wird S355M mit f_u 470",
          mt.grade == "S355M" and mpa(mt.fu) == 470.0 and mpa(mt.fy) == 355.0, f"{mt.grade!r} {mt.fu}")
    log = []
    m2 = Model("Import2")
    C.ensure_material(m2, "S355J0WP", log=log)
    check("ensure_material: „S355J0WP“ (nicht in Tabelle 3.1) bekommt die Werte von S235 mit Warnung",
          m2.materials["S355J0WP"].grade == "S235" and any("unbekannt" in str(x) for x in log), str(log))
    from statik3d.importers import rfem6_db
    for fy, soll in ((235e6, "S235"), (275e6, "S275"), (355e6, "S355"), (420e6, "S420"), (460e6, "S460")):
        name, grade = rfem6_db._material_name(210e9, fy, 1, None)
        check(f"rfem6_db: f_y {fy / 1e6:g} ohne Namen gibt die Sorte {soll} (nicht {soll}N)",
              (name, grade) == (soll, soll), f"{name!r} {grade!r}")


def test_n06_norm_der_sorte():
    """Der Hinweis des HiCAD-Imports nennt die Norm der Sorte (bis dahin immer
    EN 10025-2)."""
    if stahlsorte_norm is None:
        check("statik3d.model.stahlsorte_norm gibt es", False, "ImportError")
        return
    for g, soll in (("S235", "EN 10025-2"), ("S355", "EN 10025-2"), ("S355N", "EN 10025-3"),
                    ("S275NL", "EN 10025-3"), ("S460M", "EN 10025-4"), ("S420ML", "EN 10025-4"),
                    ("S355W", "EN 10025-5"), ("s 355 m", "EN 10025-4"), ("S420", "EN 10025-3"),
                    ("S690", ""), ("", ""), (None, "")):
        check(f"stahlsorte_norm({g!r}) = {soll!r}", stahlsorte_norm(g) == soll, repr(stahlsorte_norm(g)))


def _maske(sorte, fy, werkstoff="Stahl", neu=False):
    """Die echte Werkstoffmaske (``_eigenschaften_uebernehmen``) an einer
    Attrappe: (Modell, Attrappe, gespeicherter Werkstoff)."""
    from statik3d.gui.main import MainWindow
    m = Model("t")
    m.add_material(Material.steel("S235", name="Stahl"))
    s = mock.MagicMock()
    s.model = m
    w = {"name": werkstoff, "E": "210", "nu": "0.3", "rho": "7850", "alpha": "12",
         "fy": fy, "fu": "", "grade": sorte}
    MainWindow._eigenschaften_uebernehmen(s, "werkstoff", werkstoff, w, neu)
    return m, s, m.materials[werkstoff]


def _texte(aufrufe):
    return [str(c.args[0]) for c in aufrufe.call_args_list if c.args]


def test_n06_maske_und_dialog():
    """Die Werkstoffmaske speichert eine Sorte mit Zusatz in der Schreibweise der
    Tabelle, und der Dialog bietet sie an und setzt ihre Werte ein."""
    m, s, mt = _maske("s 355 m", "")
    check("Maske: „s 355 m“ ohne f_y wird als S355M gespeichert, f_u(10 mm) = 470",
          mt.grade == "S355M" and mt.fy is None and mpa(mt.ultimate_strength(0.010)) == 470.0,
          f"{mt.grade!r} fy={mt.fy}")
    check("… ohne Meldung (die Sorte ist der Tabelle bekannt)",
          not _texte(s.info) and not _texte(s.hinweis) and not _texte(s.error), str(_texte(s.info)))
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    d = dg.MaterialDialog(None)
    angebot = [d.grade.itemText(i) for i in range(d.grade.count())]
    check("Dialog: die Auswahl bietet S355M, S355ML, S460N und S355W an",
          all(x in angebot for x in ("S355M", "S355ML", "S460N", "S355W")), ", ".join(angebot))
    d._grade_changed("S355M")
    check("Dialog: „S355M“ setzt f_y 355 und f_u 470 ein", d.fy.value() == 355.0 and d.fu.value() == 470.0,
          f"{d.fy.value()} {d.fu.value()}")
    d.grade.setCurrentText("S355M")
    check("Dialog: das Ergebnis traegt Sorte S355M", d.result_material().grade == "S355M",
          repr(d.result_material().grade))
    d.deleteLater()
    mt = Material.steel("S235")
    mt.grade = "s 355 m"
    d = dg.MaterialDialog(None, mt)
    check("Dialog: ein Werkstoff mit Sorte „s 355 m“ steht als S355M in der Auswahl",
          d.grade.currentText() == "S355M", d.grade.currentText())
    d.deleteLater()
    del app


# --------------------------------------------------------------------------
# N07
# --------------------------------------------------------------------------
def test_n07_maske():
    """Werkstoffmaske: f_y = 0 (und alles <= 0) wird als Hinweis abgewiesen,
    nichts wird gemerkt oder veraendert; „leer“ bleibt gueltig."""
    for fy in ("0", "0,0", "-5"):
        m, s, mt = _maske("S235", fy)
        meldungen = _texte(s.hinweis)
        print("     Hinweis:", meldungen)
        check(f"Maske: f_y {fy!r}: abgewiesen, Werkstoff unveraendert (f_y 235)",
              mpa(mt.fy) == 235.0 and mt.grade == "S235", f"fy={mt.fy}")
        check("… mit einem Hinweis, der „größer als null“ und „leer“ nennt",
              len(meldungen) == 1 and "größer als null" in meldungen[0] and "leer" in meldungen[0],
              str(meldungen))
        check("… kein Schritt zum Rueckgaengig (merken nicht gerufen), kein Fehlerfenster",
              not s.merken.called and not _texte(s.error))
    # „leer“ ist davon getrennt: kein f_y, die Sorte gibt es (oder bei Beton gibt es keines)
    m, s, mt = _maske("S235", "")
    check("Maske: f_y leer wird uebernommen (None), f_y kommt aus der Sorte (235)",
          mt.fy is None and mpa(mt.yield_strength(0.010)) == 235.0 and s.merken.called
          and not _texte(s.hinweis), f"fy={mt.fy}")
    m, s, mt = _maske("C30/37", "")
    check("Maske: Beton „C30/37“ ohne f_y wird uebernommen (None)", mt.fy is None and mt.grade == "C30/37"
          and not _texte(s.hinweis), f"fy={mt.fy}")
    m, s, mt = _maske("S235", "300")
    check("Maske: f_y 300 wird uebernommen", mpa(mt.fy) == 300.0 and not _texte(s.hinweis), f"fy={mt.fy}")
    m, s, mt = _maske("", "0,5")
    check("Maske: ein kleines positives f_y (0,5) wird uebernommen", mpa(mt.fy) == 0.5
          and not _texte(s.hinweis), f"fy={mt.fy}")


def _zelle_fy(wert, fy_vorher=355e6):
    """Die Zelle f_y der Werkstofftabelle (``_mat_aendern``, Spalte 4) an einer Attrappe."""
    from statik3d.gui.main import MainWindow
    m = Model("t")
    mt = Material.steel("S355", name="Stahl")
    mt.fy = fy_vorher
    m.add_material(mt)
    s = mock.MagicMock()
    s.model = m
    s.tbl_mat.modell.zeilen = [["Stahl"]]
    ok = MainWindow._mat_aendern(s, 0, 4, wert)
    return ok, s, mt


def test_n07_zelle_attrappe():
    for wert in (0.0, -3.0):
        ok, s, mt = _zelle_fy(wert)
        meldungen = _texte(s.hinweis)
        print("     Hinweis:", meldungen)
        check(f"Zelle f_y {wert:g}: abgewiesen, f_y bleibt 355", ok is False and mpa(mt.fy) == 355.0,
              f"{ok} fy={mt.fy}")
        check("… ein Hinweis mit „größer als null“, kein Schritt, kein Fehlerfenster",
              len(meldungen) == 1 and "größer als null" in meldungen[0] and not s.merken.called
              and not _texte(s.error), str(meldungen))
    ok, s, mt = _zelle_fy(None)
    check("Zelle f_y leer (None): uebernommen, f_y ist None - nicht 0", ok is True and mt.fy is None,
          f"{ok} fy={mt.fy!r}")
    check("… ein Schritt zum Rueckgaengig, kein Hinweis", s.merken.called and not _texte(s.hinweis))
    ok, s, mt = _zelle_fy(420.0)
    check("Zelle f_y 420: uebernommen (420 N/mm²)", ok is True and mpa(mt.fy) == 420.0, f"{ok} fy={mt.fy}")


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
    w._ungespeichert_fragen = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w)
    w.load_example("frame")
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def test_n07_tabelle_im_fenster():
    """Die Zelle in der echten Tabelle: Eingabe ueber ``setData``, Anzeige,
    Rueckgaengig. Ein leerer f_y steht als leere Zelle da, nicht als „0“."""
    from PySide6 import QtCore
    w, app = _fenster()
    name = list(w.model.materials)[0]
    mt = w.model.materials[name]
    mo = w.tbl_mat.modell
    i_fy = mo.index(0, 4)
    undo = lambda: len(getattr(w, "_undo", []) or [])  # noqa: E731
    check("Vorbereitung: der Werkstoff hat f_y 355, die Zelle bietet 355 an",
          mpa(mt.fy) == 355.0 and mo.data(i_fy, QtCore.Qt.EditRole) == "355",
          repr(mo.data(i_fy, QtCore.Qt.EditRole)))
    # 0 getippt
    w.meldungen.leeren()
    u0 = undo()
    ok = mo.setData(i_fy, "0")
    check("Zelle f_y „0“ getippt: abgewiesen, f_y bleibt 355, kein Schritt",
          ok is False and mpa(mt.fy) == 355.0 and undo() == u0, f"{ok} fy={mt.fy} Schritte {undo() - u0}")
    check("… der Hinweis nennt „größer als null“", w.meldungen.hinweis_mit("größer als null"),
          str(w.meldungen.hinweise[-1:]))
    for text in ("= 0", "-1"):
        w.meldungen.leeren()
        ok = mo.setData(i_fy, text)
        check(f"Zelle f_y {text!r}: ebenfalls abgewiesen", ok is False and mpa(mt.fy) == 355.0
              and w.meldungen.hinweis_mit("größer als null"), f"{ok} fy={mt.fy}")
    # leer getippt: kein f_y
    w.meldungen.leeren()
    ok = mo.setData(i_fy, "")
    check("Zelle f_y leer getippt: uebernommen, f_y ist None (nicht 0,0)", ok is True and mt.fy is None
          and undo() == u0 + 1 and not w.meldungen.hinweise, f"{ok} fy={mt.fy!r}")
    check("… die Zelle zeigt jetzt nichts (nicht „0“), auch beim Bearbeiten",
          mo.data(i_fy) == "" and mo.data(i_fy, QtCore.Qt.EditRole) == "",
          f"{mo.data(i_fy)!r} {mo.data(i_fy, QtCore.Qt.EditRole)!r}")
    # 0 in eine leere Zelle
    w.meldungen.leeren()
    ok = mo.setData(i_fy, "0")
    check("Leere Zelle, „0“ getippt: abgewiesen, f_y bleibt None", ok is False and mt.fy is None
          and w.meldungen.hinweis_mit("größer als null"), f"{ok} fy={mt.fy!r}")
    # eine Zahl in die leere Zelle
    ok = mo.setData(i_fy, "275")
    check("Leere Zelle, „275“ getippt: uebernommen", ok is True and mpa(mt.fy) == 275.0, f"{ok} fy={mt.fy}")
    # Rueckgaengig bis zum Anfang
    w.undo()
    app.processEvents()
    w.undo()
    app.processEvents()
    mt = w.model.materials[name]
    check("Rueckgaengig: f_y wieder 355", mpa(mt.fy) == 355.0, f"fy={mt.fy}")
    # ein Werkstoff, der ohne f_y ins Fenster kommt: leere Zelle
    w.model.materials[name].fy = None
    w.refresh_all()
    app.processEvents()
    mo = w.tbl_mat.modell
    check("Ein Werkstoff ohne f_y: die Zelle zeigt nichts (Ausgangsstand: „0“)",
          mo.data(mo.index(0, 4)) == "", repr(mo.data(mo.index(0, 4))))
    # die Dichte ist ein anderes Feld: 0 bleibt dort zulaessig (wie bisher)
    ok = mo.setData(mo.index(0, 3), "0")
    check("Dichte 0 bleibt zulaessig (nur f_y ist anders)", ok is True and w.model.materials[name].rho == 0.0,
          f"{ok} rho={w.model.materials[name].rho}")
    w.undo()
    app.processEvents()
    w.model.materials[name].fy = 355e6
    w.refresh_all()


def test_n07_dialog():
    """Werkstoffdialog: f_y leer wird nicht als „0“ gezeigt, 0 laesst OK nicht
    durch (die Meldungszeile nennt den Grund), leer und positive Werte gehen."""
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    beton = Material("Beton", E=33e9, nu=0.2, rho=2500.0, alpha=1e-5, fy=None, fu=None, grade="C30/37")
    d = dg.MaterialDialog(None, beton)
    check("Dialog: ein Werkstoff ohne f_y zeigt ein leeres Feld (Ausgangsstand: „0“)", d.fy.text() == "",
          repr(d.fy.text()))
    d.accept()
    check("Dialog: leeres f_y: OK geht durch, f_y bleibt None", d.result() == QtWidgets.QDialog.Accepted
          and d.result_material().fy is None, f"{d.result()} fy={d.result_material().fy!r}")
    d.deleteLater()
    for eingabe in ("0", "-3"):
        d = dg.MaterialDialog(None, beton)
        d.fy.setText(eingabe)
        d.accept()
        text = d.lbl_zahlmeldung.text()
        print("     Meldungszeile:", text)
        check(f"Dialog: f_y {eingabe!r}: OK geht nicht durch (der Dialog bleibt offen)",
              d.result() != QtWidgets.QDialog.Accepted, str(d.result()))
        check("… die Meldungszeile nennt „größer als null“ und ist sichtbar",
              "größer als null" in text and not d.lbl_zahlmeldung.isHidden(), text)
        d.deleteLater()
    d = dg.MaterialDialog(None, beton)
    d.fy.setText("355")
    d.accept()
    check("Dialog: f_y 355: OK geht durch, f_y = 355 N/mm²", d.result() == QtWidgets.QDialog.Accepted
          and mpa(d.result_material().fy) == 355.0, f"{d.result()}")
    d.deleteLater()
    # die Sortenwahl setzt die Werte ein, auch wenn zuvor 0 getippt war: danach ist es gueltig
    d = dg.MaterialDialog(None, beton)
    d.fy.setText("0")
    d._grade_changed("S355")
    d.accept()
    check("Dialog: erst 0, dann Sorte S355 gewaehlt: OK geht durch (f_y 355)",
          d.result() == QtWidgets.QDialog.Accepted and mpa(d.result_material().fy) == 355.0, f"{d.result()}")
    d.deleteLater()
    # der Grund ohne Dialog (die Maske und die Tabelle nehmen denselben Text)
    fehler = getattr(dg, "streckgrenze_fehler", None)
    check("dialogs.streckgrenze_fehler: None und positive Werte sind gueltig, 0 und negative nicht",
          callable(fehler) and fehler(None) == "" and fehler(355) == "" and fehler(0.5) == ""
          and "größer als null" in fehler(0) and "größer als null" in fehler(-1)
          and "größer als null" in fehler(float("nan")))
    del app


def test_handbuch():
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
                        "Benutzerhandbuch.md")
    with open(pfad, encoding="utf-8") as f:
        text = " ".join(f.read().split())
    check("Handbuch: nennt die Sorten mit N, NL, M, ML und W samt Normen",
          "**Sorten mit Zusatz (N, NL, M, ML, W).**" in text and "EN 10025-3" in text
          and "EN 10025-4" in text and "EN 10025-5" in text)
    check("Handbuch: nennt den Stand vor dem 07.10.2026 und ein Beispiel (S355M, f_u 470 statt 490)",
          "Bis zum 07.10.2026 las der Import" in text and "S355M" in text and "470" in text)
    check("Handbuch: nennt, was die Tabelle nicht fuehrt (S355J0WP) und die Hohlprofilsorten",
          "S355J0WP" in text and "Hohlprofil" in text)
    check("Handbuch: f_y = 0 ist ein Eingabefehler, leer bleibt gueltig, Stand vor dem 07.10.2026",
          "**Streckgrenze null.**" in text and "größer als null" in text
          and "Bis zum 07.10.2026 galt eine eingegebene 0" in text)
    check("Handbuch: die Aussage „Die Tabelle kennt nur S235, S275, S355, S420 und S460“ ist ersetzt",
          "Die Tabelle kennt nur S235, S275, S355, S420 und S460" not in text)


def main():
    for t in (test_n06_text_zu_sorte, test_n06_unbekannt_ohne_erfundene_werte, test_n06_normwerte,
              test_n06_kette_text_zu_werten, test_n06_schreibweise_und_material, test_n06_import_und_namen,
              test_n06_norm_der_sorte, test_n06_maske_und_dialog,
              test_n07_maske, test_n07_zelle_attrappe, test_n07_tabelle_im_fenster, test_n07_dialog,
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
