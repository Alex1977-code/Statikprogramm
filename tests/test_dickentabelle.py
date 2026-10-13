"""
Die Dickentabelle des Werkstoffs geht beim Uebernehmen nicht verloren (13.10.2026).

Der RFEM-Import legt f_y und f_u je Erzeugnisdicke am Werkstoff ab (``fy_dicke``,
``fu_dicke``: [[t_max, Wert], ...]; S355 etwa bis 16 mm 355, bis 40 mm 345 ...).
Die Werkstoffmaske („Übernehmen“) und der Werkstoffdialog bauten den Werkstoff
neu und kopierten nur die Felder, die sie kannten: schon eine geaenderte Dichte
leerte beide Tabellen - an einem Werkstoff, den der Anwender gar nicht angefasst
hatte. Dasselbe traf jedes Feld, das die Maske nicht zeigt.

Entscheidung fuer den Fall, dass der Anwender f_y oder f_u **selbst** aendert:
Die Tabelle bleibt, ihre duennste Stufe folgt dem neuen Wert, die uebrigen Stufen
bleiben, und das Protokoll sagt es mit der entstandenen Tabelle. Begruendung: f_y
und f_u am Werkstoff sind per Definition der Wert der duennsten Stufe (Import,
Tooltip des Dialogs); die Nachweise lesen aber zuerst die Tabelle - bliebe sie
unveraendert, waere die Eingabe fuer Staebe und Schalen wirkungslos, wuerde sie
verworfen, gingen die Stufen der dickeren Erzeugnisse ohne Absicht verloren.

Geprueft wird:

* Maske: Dichte, Name, Verfestigung geaendert - beide Tabellen, Art, Verfestigung
  und ein der Maske unbekanntes Feld bleiben, f_y und f_u bleiben bitgleich, keine
  Meldung zur Tabelle;
* Maske: f_y bzw. f_u selbst geaendert - duennste Stufe folgt, Rest bleibt,
  Meldung mit der entstandenen Tabelle, die Nachweise lesen den neuen Wert;
* Maske: f_y geleert - Tabelle bleibt, Meldung; f_y wieder dasselbe getippt -
  keine Meldung;
* Maske zeigt die Tabelle an („nach Dicke“), ein Werkstoff ohne Tabelle nicht;
* Dialog: dieselben Faelle, dazu eine eigene Sorte (nicht in der Tabelle), die
  das Ergebnis nicht verliert, und der Wechsel der Stahlsorte, der die Tabelle
  der Quelldatei ausdruecklich (Anzeige im Dialog, Meldung) ersetzt.

Aufruf:  python -m tests.test_dickentabelle
"""
import copy
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_dickentabelle_"), "einstellungen.json")

from statik3d.model import Material           # noqa: E402

RESULTS = []
_FENSTER = {}

FY_TAB = [[0.016, 355e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6]]
FU_TAB = [[0.040, 470e6], [0.080, 470e6]]


def check(name, ok, detail=""):
    ok = bool(ok)
    detail = str(detail).replace("\n", " | ")
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def _werkstoff(**plus):
    """Ein Werkstoff wie aus dem RFEM-Import: f_y/f_u = duennste Stufe, beide Tabellen."""
    kw = dict(E=210e9, nu=0.3, rho=7850.0, alpha=1.2e-5, fy=355e6, fu=470e6, grade="S355",
              fy_dicke=copy.deepcopy(FY_TAB), fu_dicke=copy.deepcopy(FU_TAB),
              art="Spannstahl", verfestigung=1e-4)
    kw.update(plus)
    return Material("RF", **kw)


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
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _uebernehmen(w, app, felder, mat=None):
    """Die echte Werkstoffmaske rechts: Felder setzen, „Übernehmen“. Gibt (Werkstoff,
    neue Protokollzeilen) zurueck."""
    m = w.model
    if "RF" in m.materials:
        del m.materials["RF"]
    m.add_material(mat or _werkstoff())
    mk = w._objektmaske("werkstoff", "RF") or w.maskenrand.maske
    app.processEvents()
    for k, v in felder.items():
        f = mk._felder[k]
        (f.setCurrentText if hasattr(f, "setCurrentText") else f.setText)(v)
    vor = w.log.toPlainText()
    ok = mk.anwenden()
    app.processEvents()
    zeilen = w.log.toPlainText()[len(vor):]
    name = felder.get("name", "RF")
    return m.materials[name], zeilen, ok


def test_maske_anderes_feld():
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    for was, felder in (("Dichte", {"rho": "7800"}), ("Name", {"name": "RF2"}),
                        ("Verfestigung", {"verfestigung": "E/250"}),
                        ("Wärmedehnzahl", {"alpha": "13"})):
        vorlage = _werkstoff()
        vorlage.zusatz = "unbekannt"              # ein Feld, das die Maske nicht kennt
        mt, zeilen, ok = _uebernehmen(w, app, felder, mat=vorlage)
        check(f"Maske, {was} geändert: Übernehmen gelungen", ok)
        check(f"… fy_dicke bleibt", mt.fy_dicke == FY_TAB, str(mt.fy_dicke))
        check(f"… fu_dicke bleibt", mt.fu_dicke == FU_TAB, str(mt.fu_dicke))
        check(f"… f_y und f_u bleiben bitgleich", mt.fy == 355e6 and mt.fu == 470e6, f"{mt.fy!r} {mt.fu!r}")
        check(f"… Art bleibt", mt.art == "Spannstahl", repr(mt.art))
        check(f"… ein unbekanntes Feld bleibt", getattr(mt, "zusatz", None) == "unbekannt",
              repr(getattr(mt, "zusatz", None)))
        check(f"… die Verfestigung bleibt, wenn nicht geändert",
              abs(mt.verfestigung - (0.004 if was == "Verfestigung" else 1e-4)) < 1e-12, repr(mt.verfestigung))
        check(f"… keine Meldung zur Dickentabelle", "Dickentabelle" not in zeilen, zeilen[-200:])
        if was == "Dichte":
            check("… die Dichte gilt", mt.rho == 7800.0, repr(mt.rho))
        if was == "Name":
            check("… der alte Name ist weg", "RF" not in w.model.materials)
            del w.model.materials["RF2"]


def test_maske_fy_selbst():
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    mt, zeilen, ok = _uebernehmen(w, app, {"fy": "360"})
    check("Maske, f_y 355 → 360: Übernehmen gelungen", ok)
    check("… f_y gilt", mt.fy == 360e6, repr(mt.fy))
    check("… die dünnste Stufe folgt, die übrigen bleiben",
          mt.fy_dicke == [[0.016, 360e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6]], str(mt.fy_dicke))
    check("… fu_dicke bleibt", mt.fu_dicke == FU_TAB, str(mt.fu_dicke))
    check("… die Nachweise lesen den neuen Wert (10 mm 360, 30 mm 345)",
          mt.yield_strength(0.010) == 360e6 and mt.yield_strength(0.030) == 345e6,
          f"{mt.yield_strength(0.010)} {mt.yield_strength(0.030)}")
    check("… das Protokoll sagt es mit der entstandenen Tabelle",
          "Dickentabelle" in zeilen and "≤16: 360" in zeilen and "≤40: 345" in zeilen
          and "f_p0,1k" in zeilen, zeilen[-300:])
    mt, zeilen, ok = _uebernehmen(w, app, {"fu": "480"})
    check("Maske, f_u 470 → 480: dünnste Stufe folgt, Rest bleibt",
          mt.fu == 480e6 and mt.fu_dicke == [[0.040, 480e6], [0.080, 470e6]] and mt.fy_dicke == FY_TAB,
          f"{mt.fu_dicke} {mt.fy_dicke}")
    check("… das Protokoll nennt f_pk (Art Spannstahl)", "Dickentabelle" in zeilen and "f_pk" in zeilen, zeilen[-300:])
    mt, zeilen, ok = _uebernehmen(w, app, {"fy": ""})
    check("Maske, f_y geleert: Tabelle bleibt unverändert",
          mt.fy is None and mt.fy_dicke == FY_TAB and mt.fu_dicke == FU_TAB, f"{mt.fy!r} {mt.fy_dicke}")
    check("… das Protokoll sagt, dass die Tabelle weiter gilt", "Dickentabelle" in zeilen and "bleibt" in zeilen,
          zeilen[-300:])
    mt, zeilen, ok = _uebernehmen(w, app, {"fy": "355,0"})
    check("Maske, f_y dasselbe getippt (355,0): keine Meldung, Tabelle bleibt",
          mt.fy_dicke == FY_TAB and "Dickentabelle" not in zeilen, zeilen[-200:])


def test_maske_zeigt_tabelle():
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    m = w.model
    m.add_material(_werkstoff())
    m.add_material(Material("Glatt", fy=355e6, fu=470e6, grade="S355"))
    mk = w._objektmaske("werkstoff", "RF") or w.maskenrand.maske
    app.processEvents()
    lb = mk._felder.get("nach_dicke")
    check("Maske mit Tabelle: Feld „nach Dicke“ nennt beide Tabellen",
          lb is not None and "≤16: 355" in lb.text() and "≤40: 470" in lb.text(),
          lb.text() if lb is not None else "kein Feld")
    mk = w._objektmaske("werkstoff", "Glatt") or w.maskenrand.maske
    app.processEvents()
    check("Maske ohne Tabelle: kein Feld „nach Dicke“", "nach_dicke" not in mk._felder)


def test_tabellenzelle():
    """Die Zelle f_y der Werkstofftabelle folgt derselben Regel wie die Maske."""
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    w.model.add_material(_werkstoff())
    w.refresh_all()
    app.processEvents()
    z = [str(r[0]) for r in w.tbl_mat.modell.zeilen].index("RF")
    vor = w.log.toPlainText()
    ok = w._mat_aendern(z, 3, 7800.0)
    mt = w.model.materials["RF"]
    check("Zelle Dichte: Tabellen bleiben, keine Meldung zur Tabelle",
          ok and mt.fy_dicke == FY_TAB and mt.fu_dicke == FU_TAB and "Dickentabelle" not in w.log.toPlainText()[len(vor):])
    vor = w.log.toPlainText()
    ok = w._mat_aendern(z, 4, 360.0)
    zeilen = w.log.toPlainText()[len(vor):]
    check("Zelle f_y → 360: dünnste Stufe folgt, Rest bleibt",
          ok and mt.fy == 360e6 and mt.fy_dicke == [[0.016, 360e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6]]
          and mt.fu_dicke == FU_TAB, str(mt.fy_dicke))
    check("… das Protokoll sagt es", "Dickentabelle" in zeilen and "≤16: 360" in zeilen, zeilen[-250:])


def test_dialog():
    from statik3d.gui import dialogs as dg
    # nichts angefasst
    vorlage = _werkstoff()
    vorlage.zusatz = "unbekannt"
    d = dg.MaterialDialog(None, vorlage)
    neu = d.result_material()
    check("Dialog, nichts geändert: beide Tabellen bleiben", neu.fy_dicke == FY_TAB and neu.fu_dicke == FU_TAB,
          f"{neu.fy_dicke} {neu.fu_dicke}")
    check("… f_y und f_u bleiben bitgleich", neu.fy == 355e6 and neu.fu == 470e6, f"{neu.fy!r} {neu.fu!r}")
    check("… Art, Verfestigung und ein unbekanntes Feld bleiben",
          neu.art == "Spannstahl" and neu.verfestigung == 1e-4 and getattr(neu, "zusatz", None) == "unbekannt")
    check("… die Vorlage ist nicht verändert", vorlage.fy_dicke == FY_TAB)
    check("… das Ergebnis teilt keine Liste mit der Vorlage", neu.fy_dicke is not vorlage.fy_dicke
          and bool(neu.fy_dicke) and neu.fy_dicke[0] is not vorlage.fy_dicke[0])
    d.deleteLater()
    # Dichte
    d = dg.MaterialDialog(None, _werkstoff())
    d.rho.set(7800.0)
    neu = d.result_material()
    check("Dialog, Dichte geändert: Tabellen bleiben, Dichte gilt",
          neu.fy_dicke == FY_TAB and neu.fu_dicke == FU_TAB and neu.rho == 7800.0, str(neu.rho))
    check("… keine Meldung zur Tabelle", not [z for z in getattr(d, "dicken_meldungen", []) if "Dickentabelle" in z])
    d.deleteLater()
    # f_y selbst
    d = dg.MaterialDialog(None, _werkstoff())
    d.fy.set(360.0)
    neu = d.result_material()
    check("Dialog, f_y → 360: dünnste Stufe folgt, Rest bleibt",
          neu.fy == 360e6 and neu.fy_dicke == [[0.016, 360e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6]],
          str(neu.fy_dicke))
    check("… der Dialog meldet es mit der Tabelle",
          any("Dickentabelle" in z and "≤16: 360" in z for z in getattr(d, "dicken_meldungen", [])),
          str(getattr(d, "dicken_meldungen", None)))
    d.deleteLater()
    # eigene Sorte
    d = dg.MaterialDialog(None, _werkstoff(grade="S690"))
    neu = d.result_material()
    check("Dialog: eine eigene Sorte (S690) geht nicht verloren", neu.grade == "S690", repr(neu.grade))
    d.deleteLater()
    # Wechsel der Stahlsorte: die Tabelle der Quelldatei entfaellt ausdruecklich
    d = dg.MaterialDialog(None, _werkstoff())
    d.grade.setCurrentText("S235")
    anzeige = d.lbl_dicke.text()
    neu = d.result_material()
    check("Dialog, Stahlsorte S355 → S235: Werte der Sorte, Tabellen der Quelldatei entfallen",
          neu.fy == 235e6 and neu.fy_dicke == [] and neu.fu_dicke == [], f"{neu.fy} {neu.fy_dicke}")
    check("… der Dialog zeigt es an und meldet es",
          "entfällt" in anzeige
          and any("Dickentabelle" in z and "entfällt" in z for z in getattr(d, "dicken_meldungen", [])),
          f"{anzeige!r} {getattr(d, 'dicken_meldungen', None)}")
    d.deleteLater()
    # neuer Werkstoff
    d = dg.MaterialDialog(None)
    neu = d.result_material()
    check("Dialog ohne Vorlage: keine Tabelle, kein Absturz", neu.fy_dicke == [] and neu.fu_dicke == [])
    d.deleteLater()


def main():
    for t in (test_maske_anderes_feld, test_maske_fy_selbst, test_maske_zeigt_tabelle, test_tabellenzelle,
              test_dialog):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    # ein Fenster ist offen: ohne Rueckfrage beenden
    os._exit(main())
