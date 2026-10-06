"""
Fehlerliste 06.10.2026, Paket P10, Eintrag F08: die Stahlsorte wird ohne
Rücksicht auf Groß-/Kleinschreibung und Leerzeichen erkannt.

Ausgangsstand 60fe253 (gemessen mit tests/test_fehler_p10.py, siehe unten): Die
Werkstoffmaske speicherte die Sorte, wie sie getippt wurde (``.strip()``), und
die Sortentabelle ``STEEL_GRADES`` kennt nur „S235“ ... „S460“. Mit „s235“ und
eingetragenem f_y entfiel über 40 mm still die Dickenabminderung (235 statt
215 N/mm², unsichere Seite); mit leerem f_y wurde die Streckgrenze 0 und der
Stab „nicht geführt“, obwohl die Maske „leer = aus der Stahlsorte“ verspricht.

Geprüft werden alle Stellen, an denen eine Sorte gelesen wird: das Material
selbst (auch nach Zuweisung von Hand), die Werkstoffmaske (die echte
``_eigenschaften_uebernehmen``), die Tabellenzelle, der Werkstoffdialog, das
Laden einer Datei und der Import (Sorte aus einem Namen).

Aufruf:  python -m tests.test_fehler_p10
"""
import json
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, STEEL_GRADES  # noqa: E402

try:                    # fehlt auf dem Ausgangsstand 60fe253: dann schlaegt nur diese Gruppe fehl
    from statik3d.model import stahlsorte_schluessel, stahlsorte_normiert
except ImportError:
    stahlsorte_schluessel = stahlsorte_normiert = None

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:72s} {detail}")
    return ok


def n_mm2(x):
    return float(x) / 1e6


def test_sortenschluessel():
    """Die Erkennung selbst: Groß/klein und Leerzeichen jeder Art egal, alles
    andere unbekannt (auch „S235JR“: die Tabelle kennt keine Untersorten)."""
    if stahlsorte_schluessel is None:
        check("statik3d.model.stahlsorte_schluessel gibt es", False, "ImportError")
        return
    for eingabe in ("S235", "s235", " s235 ", "S 235", "s 235", "S  235", "s\t235", "S235 ", " S235"):
        check(f"Schlüssel zu {eingabe!r} = S235", stahlsorte_schluessel(eingabe) == "S235",
              repr(stahlsorte_schluessel(eingabe)))
    for g in STEEL_GRADES:
        check(f"jede Sorte der Tabelle wird in Kleinschrift erkannt ({g})",
              stahlsorte_schluessel(g.lower()) == g)
    for eingabe in ("", None, "S690", "S235JR", "xyz", "S2 35 5"):
        check(f"{eingabe!r} ist der Tabelle unbekannt", stahlsorte_schluessel(eingabe) is None,
              repr(stahlsorte_schluessel(eingabe)))
    check("normiert: bekannte Sorte wird zum Schlüssel", stahlsorte_normiert(" s 355 ") == "S355")
    check("normiert: unbekannte Sorte bleibt, wie getippt (nur getrimmt)",
          stahlsorte_normiert("  s690 ") == "s690", repr(stahlsorte_normiert("  s690 ")))
    check("normiert: leer bleibt leer", stahlsorte_normiert(None) == "" and stahlsorte_normiert("  ") == "")


def test_material_kleinschreibung():
    """Die Dickenabminderung und die Sorte bei leerem f_y, mit „s235“."""
    # Mit eingetragenem f_y (so lief die Maske am Ausgangsstand in die unsichere Seite)
    fuer = {"S235": 215.0, "s235": 215.0, "S 235": 215.0, " s 235": 215.0}
    for sorte, soll in fuer.items():
        mt = Material("Stahl", fy=235e6, fu=None, grade=sorte)
        check(f"f_y 235, Sorte {sorte!r}: f_y(50 mm) = {soll:g} N/mm²",
              n_mm2(mt.yield_strength(0.050)) == soll, f"{n_mm2(mt.yield_strength(0.050)):g}")
        check(f"f_y 235, Sorte {sorte!r}: f_y(10 mm) = 235 N/mm²",
              n_mm2(mt.yield_strength(0.010)) == 235.0, f"{n_mm2(mt.yield_strength(0.010)):g}")
        check(f"f_y 235, Sorte {sorte!r}: f_u(50 mm) = 360 N/mm²",
              n_mm2(mt.ultimate_strength(0.050)) == 360.0, f"{n_mm2(mt.ultimate_strength(0.050)):g}")
    # Mit leerem f_y: die Sorte gibt die Werte
    for sorte in ("S235", "s235", "S 235", "s 235"):
        mt = Material("Stahl", grade=sorte)
        check(f"f_y leer, Sorte {sorte!r}: f_y(10 mm) = 235 N/mm² (nicht 0)",
              n_mm2(mt.yield_strength(0.010)) == 235.0, f"{n_mm2(mt.yield_strength(0.010)):g}")
        check(f"f_y leer, Sorte {sorte!r}: f_u(10 mm) = 360 N/mm²",
              n_mm2(mt.ultimate_strength(0.010)) == 360.0, f"{n_mm2(mt.ultimate_strength(0.010)):g}")
    # Von Hand zugewiesen (so schrieb die Tabellenzelle und schreibt jedes Skript):
    mt = Material.steel("S355")
    mt.fy = None
    mt.grade = "s 355"
    check("Sorte nachträglich „s 355“ gesetzt, f_y leer: f_y(10 mm) = 355 N/mm²",
          n_mm2(mt.yield_strength(0.010)) == 355.0, f"{n_mm2(mt.yield_strength(0.010)):g}")
    check("… und f_y(50 mm) = 335 N/mm² (Dickenabminderung)",
          n_mm2(mt.yield_strength(0.050)) == 335.0, f"{n_mm2(mt.yield_strength(0.050)):g}")
    # Unbekannte Sorte: eingetragenes f_y gilt, ohne f_y gibt es nichts zu nehmen
    mu = Material("Frei", fy=300e6, grade="S235JR")
    check("Sorte S235JR (unbekannt), f_y 300: f_y bleibt 300 bei 10 und 50 mm",
          n_mm2(mu.yield_strength(0.010)) == 300.0 and n_mm2(mu.yield_strength(0.050)) == 300.0)
    check("Material.steel nimmt „s 355“", Material.steel("s 355").grade == "S355")
    try:
        Material.steel("S690")
        check("Material.steel(\"S690\") ist unbekannt (KeyError)", False)
    except KeyError:
        check("Material.steel(\"S690\") ist unbekannt (KeyError)", True)


def test_laden_einer_datei():
    """Eine Datei, in der die Sorte klein oder mit Leerzeichen steht (so
    schrieb sie die Werkstoffmaske bis zum 06.10.2026), rechnet nach dem
    Laden wie mit „S235“ - über Model.from_dict und über Datei."""
    m = Model("Datei")
    m.add_material(Material("Stahl", fy=235e6, grade="S235"))
    d = m.to_dict()
    d["materials"]["Stahl"]["grade"] = "s235"
    geladen = Model.from_dict(d)
    mt = geladen.materials["Stahl"]
    check("from_dict: Sorte „s235“ wird zu „S235“", mt.grade == "S235", repr(mt.grade))
    check("from_dict: f_y(50 mm) = 215 N/mm²", n_mm2(mt.yield_strength(0.050)) == 215.0,
          f"{n_mm2(mt.yield_strength(0.050)):g}")
    # Datei auf der Platte, Sorte mit Leerzeichen und ohne f_y
    d["materials"]["Stahl"].update({"grade": " s 235 ", "fy": None, "fu": None})
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "alt.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(d, f)
        geladen = Model.load(pfad)
    mt = geladen.materials["Stahl"]
    check("Datei laden: Sorte „ s 235 “ wird zu „S235“", mt.grade == "S235", repr(mt.grade))
    check("Datei laden: f_y leer, f_y(10 mm) = 235 N/mm² (nicht 0)",
          n_mm2(mt.yield_strength(0.010)) == 235.0, f"{n_mm2(mt.yield_strength(0.010)):g}")
    # eine unbekannte Sorte bleibt in der Datei, wie sie dort steht
    d["materials"]["Stahl"].update({"grade": "S690", "fy": 690e6})
    mt = Model.from_dict(d).materials["Stahl"]
    check("Datei laden: unbekannte Sorte „S690“ bleibt, f_y 690 gilt",
          mt.grade == "S690" and n_mm2(mt.yield_strength(0.050)) == 690.0)
    # eine alte Datei ohne Sorte (None) lädt weiter
    d["materials"]["Stahl"].update({"grade": None, "fy": 235e6})
    mt = Model.from_dict(d).materials["Stahl"]
    check("Datei laden: Sorte null (alte Datei) wird zu leer", mt.grade == "", repr(mt.grade))


def test_import_sorte_aus_text():
    """Der Import liest die Sorte aus Namen („Baustahl s 355“, „S  235 JR“)."""
    from statik3d.importers import _common as C
    faelle = [("S 235 JR", "S235"), ("s235", "S235"), ("s 355", "S355"), ("S  355 J2", "S355"),
              ("Baustahl s275", "S275"), ("s\t460", "S460"), ("Stahl S 420 N", "S420")]
    for text, soll in faelle:
        check(f"steel_grade_from_text({text!r}) = {soll}", C.steel_grade_from_text(text) == soll,
              repr(C.steel_grade_from_text(text)))
    check("steel_grade_from_text(\"S500\") ist unbekannt", C.steel_grade_from_text("S500") is None)
    check("steel_grade_from_text(\"\") ist unbekannt", C.steel_grade_from_text("") is None)
    # am Weg des Imports: ein Name legt den Werkstoff mit der Sorte an
    m = Model("Import")
    C.ensure_material(m, "baustahl s  355", quiet=True)
    mt = m.materials["baustahl s  355"]
    check("ensure_material: „baustahl s  355“ wird Baustahl S355", mt.grade == "S355" and mt.fy == 355e6,
          f"{mt.grade!r} {mt.fy}")


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


def test_werkstoffmaske():
    """Maske rechts: die Sorte wird beim Speichern vereinheitlicht."""
    for sorte, fy in (("S235", "235"), ("s235", "235"), ("s 235", "235"), (" S 235 ", "235")):
        _, s, mt = _maske(sorte, fy)
        check(f"Maske: Sorte {sorte!r}, f_y {fy}: gespeichert „S235“", mt.grade == "S235", repr(mt.grade))
        check(f"Maske: Sorte {sorte!r}, f_y {fy}: f_y(50 mm) = 215 N/mm²",
              n_mm2(mt.yield_strength(0.050)) == 215.0, f"{n_mm2(mt.yield_strength(0.050)):g}")
        check(f"Maske: Sorte {sorte!r}, f_y {fy}: keine Meldung", not _texte(s.hinweis) and not _texte(s.error),
              f"{_texte(s.hinweis)} {_texte(s.error)}")
    for sorte in ("s235", "S 235"):
        _, s, mt = _maske(sorte, "")
        check(f"Maske: Sorte {sorte!r}, f_y leer: f_y bleibt leer, die Sorte gibt 235 N/mm²",
              mt.fy is None and n_mm2(mt.yield_strength(0.010)) == 235.0,
              f"fy={mt.fy} f_y(10 mm)={n_mm2(mt.yield_strength(0.010)):g}")
        check(f"Maske: Sorte {sorte!r}, f_y leer: keine Meldung",
              not _texte(s.hinweis) and not _texte(s.error))
    _, s, mt = _maske("s355", "", werkstoff="Neu", neu=True)
    check("Maske (neu): „s355“, f_y leer: gespeichert „S355“ und f_y(10 mm) = 355 N/mm²",
          mt.grade == "S355" and n_mm2(mt.yield_strength(0.010)) == 355.0, repr(mt.grade))
    # leere Sorte bleibt leer (Werkstoff ohne Sorte, nur f_y)
    _, s, mt = _maske("", "300")
    check("Maske: ohne Sorte, f_y 300: Sorte leer, f_y 300 bei 50 mm",
          mt.grade == "" and n_mm2(mt.yield_strength(0.050)) == 300.0, repr(mt.grade))


def test_werkstoffmaske_unbekannte_sorte():
    """Eine Sorte, die die Tabelle nicht kennt, wird gemeldet, aber übernommen
    (ein Werkstoff darf eine eigene Sorte tragen: S690, oder „C30/37“ bei einem
    Beton). Mit f_y gilt der eingetragene Wert, und die Meldung sagt, dass die
    Dickenabminderung entfällt. Ohne f_y gibt die Sorte nichts her: die Meldung
    sagt, dass Stäbe daraus nicht nachgewiesen werden. Beides ist kein Hinweis
    der Regel 9b (der würde das Übernehmen abweisen), sondern eine Meldung."""
    m, s, mt = _maske("S690", "690")
    check("Maske: unbekannte Sorte „S690“ mit f_y 690: übernommen, wie getippt",
          mt.grade == "S690" and n_mm2(mt.yield_strength(0.050)) == 690.0, repr(mt.grade))
    meldungen = _texte(s.info)
    print("     Meldung:", meldungen)
    check("… mit einer Meldung, die die Sorte und die Tabelle nennt",
          len(meldungen) == 1 and "S690" in meldungen[0] and "S235" in meldungen[0]
          and "Dickenabminderung" in meldungen[0], str(meldungen))
    check("… die kein Hinweis und kein Fehler ist (die Eingabe ist gültig)",
          not _texte(s.hinweis) and not _texte(s.error))

    m, s, mt = _maske("S235JR", "")
    meldungen = _texte(s.info)
    print("     Meldung:", meldungen)
    check("Maske: unbekannte Sorte „S235JR“ ohne f_y: übernommen, wie getippt, f_y bleibt leer",
          mt.grade == "S235JR" and mt.fy is None, f"{mt.grade!r} {mt.fy}")
    check("… mit einer Meldung, die Sorte, Tabelle und die fehlende Streckgrenze nennt",
          len(meldungen) == 1 and "S235JR" in meldungen[0] and "S235" in meldungen[0]
          and "f_y ist leer" in meldungen[0] and "nicht nachgewiesen" in meldungen[0], str(meldungen))
    check("… die kein Hinweis und kein Fehler ist, mit einem Schritt für Rückgängig",
          not _texte(s.hinweis) and not _texte(s.error) and s.merken.called)
    m, s, mt = _maske("C30/37", "")
    check("Maske: eine Betonsorte „C30/37“ ohne f_y wird übernommen", mt.grade == "C30/37", repr(mt.grade))


def _zelle(sorte, fy_vorher):
    from statik3d.gui.main import MainWindow
    m = Model("t")
    mt = Material.steel("S355", name="Stahl")
    mt.fy = fy_vorher
    m.add_material(mt)
    s = mock.MagicMock()
    s.model = m
    s.tbl_mat.modell.zeilen = [["Stahl"]]
    ok = MainWindow._mat_aendern(s, 0, 5, sorte)
    return ok, s, mt


def test_tabellenzelle():
    """Die Zelle „Stahlsorte“ der Werkstofftabelle schreibt dieselbe Form."""
    for sorte in ("s235", "S 235", " s 235 "):
        ok, s, mt = _zelle(sorte, None)
        check(f"Zelle: {sorte!r} gespeichert „S235“", ok and mt.grade == "S235", repr(mt.grade))
        check(f"Zelle: {sorte!r} ohne f_y: f_y(10 mm) = 235 N/mm²", n_mm2(mt.yield_strength(0.010)) == 235.0)
    ok, s, mt = _zelle("S690", 690e6)
    check("Zelle: unbekannte Sorte mit f_y wird übernommen, mit Meldung",
          ok and mt.grade == "S690" and len(_texte(s.info)) == 1 and not _texte(s.hinweis),
          f"{ok} {mt.grade!r} {_texte(s.info)}")
    ok, s, mt = _zelle("S235JR", None)
    check("Zelle: unbekannte Sorte ohne f_y wird übernommen, mit Meldung zur fehlenden Streckgrenze",
          ok and mt.grade == "S235JR" and len(_texte(s.info)) == 1 and "f_y ist leer" in _texte(s.info)[0]
          and not _texte(s.hinweis), f"{ok} {mt.grade!r} {_texte(s.info)}")
    ok, s, mt = _zelle("", None)
    check("Zelle: leere Sorte wird übernommen (Sorte leer)", ok and mt.grade == "", repr(mt.grade))


def test_werkstoffdialog():
    """Der Werkstoffdialog (Auswahl aus der Tabelle) zeigt eine kleingeschriebene
    Sorte als „S235“, nicht als „benutzerdefiniert“."""
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    mt = Material.steel("S235")
    mt.grade = "s 235"             # von Hand gesetzt, wie die Tabellenzelle bis 06.10.2026
    d = dg.MaterialDialog(None, mt)
    check("Dialog: Sorte „s 235“ steht als S235 in der Auswahl", d.grade.currentText() == "S235",
          d.grade.currentText())
    check("Dialog: …und wird als „S235“ zurückgegeben", d.result_material().grade == "S235",
          repr(d.result_material().grade))
    del app


def test_handbuch():
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs",
                        "Benutzerhandbuch.md")
    with open(pfad, encoding="utf-8") as f:
        text = f.read()
    text = " ".join(text.split())
    check("Handbuch: nennt Groß-/Kleinschreibung und Leerzeichen der Stahlsorte",
          "**Schreibweise der Stahlsorte.**" in text and "Groß- und Kleinschreibung" in text
          and "Bis zum 06.10.2026 blieb eine Sorte" in text)
    check("Handbuch: nennt die unbekannte Sorte (S235JR)", "S235JR" in text)


def main():
    for t in (test_sortenschluessel, test_material_kleinschreibung, test_laden_einer_datei,
              test_import_sorte_aus_text, test_werkstoffmaske, test_werkstoffmaske_unbekannte_sorte,
              test_tabellenzelle, test_werkstoffdialog, test_handbuch):
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
