"""
Eingaben werden richtig gelesen - Paket 4 des Oberflaechenplans (24.09.2026).

Vorher gemessen (gui_analyse/validator_probe2.py, validator_probe3.py,
unten/editrolle2.py):

* In Maskenfeldern wurde „33.000“ (E_cm) still zu 33, „2.000.000“ zu 0 bzw.
  beim Tippen zu „2.000000“ - der QDoubleValidator folgt dem Gebietsschema.
* Eine Tabellenzelle mit 1234,5678 m wurde durch F2 und Enter zu 1234,57 m,
  und schon das Oeffnen und Verlassen legte einen Rueckgaengig-Schritt an und
  verwarf die Ergebnisse.
* Das Register Lager/Lasten rechnete in N, die Masken in kN (Faktor 1000).
* Eine getippte Bildunterschrift, Bemerkung oder Symbolgroesse verwarf alle
  Ergebnisse.

Geprueft wird die Regel ohne Qt (statik3d/zahlen.py), das Zahlenfeld in
Maske, Dialog und Tabelle offscreen und das echte Hauptfenster offscreen
(Register, Statusleiste, Ergebnisse behalten).

Aufruf:  python -m tests.test_zahlenfeld
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Einstellungen in eine Wegwerfdatei - die Pruefung darf die des Anwenders
# nicht ueberschreiben
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_zahlenfeld_"), "einstellungen.json")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wirft(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    return False


# --------------------------------------------------------------------------
# Die Regel ohne Oberflaeche
# --------------------------------------------------------------------------
def test_regel():
    from statik3d import zahlen as zl
    werte = {"2,5": 2.5, "2.5": 2.5, "-3": -3.0, "2 000 000": 2e6, "2 000 000": 2e6,
             "2 000": 2000.0, "1,5e5": 1.5e5, "2e6": 2e6, "0.125": 0.125, "1 234.567": 1234.567,
             "33,000": 33.0, "33.0000": 33.0, ",5": 0.5}
    falsch = {t: zl.lesen(t) for t in werte if zl.lesen(t).status != zl.GUELTIG
              or abs(zl.lesen(t).wert - werte[t]) > 1e-12}
    check("gültig: Komma und Punkt, Tausender mit (schmalem) Leerzeichen, Exponent",
          not falsch, str(falsch)[:120])
    les = zl.lesen("2.000.000")
    check("„2.000.000“ ist ungültig, die Meldung nennt „2 000 000“",
          les.status == zl.UNGUELTIG and les.wert is None and "2 000 000" in les.meldung, les.meldung)
    check("… ebenso „1.000,5“, „12,5.3“, „12 5“, „abc“, „-“, „2e“",
          all(zl.lesen(t).status == zl.UNGUELTIG for t in ("1.000,5", "12,5.3", "12 5", "abc", "-", "2e")))
    les = zl.lesen("33.000")
    check("„33.000“ ist mehrdeutig: gelesen 33, Vorschlag 33 000, Hinweis wörtlich",
          les.status == zl.FRAGE and les.wert == 33.0 and les.vorschlag == 33000.0
          and les.meldung == "33,000 – gemeint 33 000?", les.meldung)
    check("… „0.125“ und „1 234.567“ sind nicht mehrdeutig",
          zl.lesen("0.125").status == zl.GUELTIG and zl.lesen("1 234.567").status == zl.GUELTIG)
    check("leer ist leer (kein Fehler, keine Zahl)", zl.lesen("").status == zl.LEER)
    check("ganze Zahl verlangt: „1.5“ ungültig, „12“ gültig",
          zl.lesen("1.5", ganz=True).status == zl.UNGUELTIG and zl.lesen("12", ganz=True).wert == 12.0)
    texte = {33000: "33 000", 1234.5678: "1 234,5678", 0.1 + 0.2: "0,3", 1e-5: "0,00001",
             2e6: "2 000 000", -0.0: "0", -1234.5: "-1 234,5", 7850.0: "7 850"}
    falsch = {x: zl.zahl_text(x) for x, t in texte.items() if zl.zahl_text(x) != t}
    check("schreiben: Komma, Tausender mit Leerzeichen, nie wissenschaftlich", not falsch, str(falsch))
    check("… ohne Tausender für Zellen: 1234,5678", zl.zahl_text(1234.5678, tausender=False) == "1234,5678")
    import re
    check("… auch 1e20 und 1e-20 ohne Exponent",
          not re.search(r"\de", zl.zahl_text(1e20) + zl.zahl_text(1e-20)),
          zl.zahl_text(1e20) + " / " + zl.zahl_text(1e-20))


def test_eine_quelle():
    """Die Ermuedungsmaske und lastspiele_text nutzen dieselbe Regel."""
    from statik3d import zahlen as zl
    from statik3d.model import lastspiele_text
    from statik3d.gui import ermuedungsmaske as em
    check("Ermüdungsmaske: „12 5“ ist keine Zahl (bis 24.09.: still 125)",
          _wirft(em.zahl_lesen, "12 5"))
    check("… „2.000.000“ Lastspiele weiter abgewiesen, mit Vorschlag",
          _wirft(em.lastspiele_lesen, "2.000.000"))
    try:
        em.lastspiele_lesen("500.000")
        text = ""
    except ValueError as ex:
        text = str(ex)
    check("… „500.000“: Meldung nennt „500 000“", "500 000" in text, text)
    check("lastspiele_text ist zahl_text (eine Schreibweise)",
          all(lastspiele_text(x) == zl.zahl_text(x) for x in (2e6, 1.5, 1234.25, 0.1 + 0.2, 123.456789012)))
    # Werte, bei denen die alte Schreibweise anders war (Gegenpruefung K15)
    check("… auch 1234,123456789012 und 1e-12 (alte Schreibweise wich dort ab)",
          all(lastspiele_text(x) == zl.zahl_text(x) for x in (1234.123456789012, 1e-12)),
          f"{lastspiele_text(1234.123456789012)} {lastspiele_text(1e-12)}")


# --------------------------------------------------------------------------
# Das Zahlenfeld in der Maske
# --------------------------------------------------------------------------
def _maske():
    from statik3d.gui import masken as msk
    F = msk.Feld
    mk = msk.Maske("Probe", [F("E_cm", "E_cm [N/mm²]", "zahl", 33000.0),
                             F("x", "x [m]", "zahl", 1.5),
                             F("n", "Anzahl", "ganz", 3),
                             F("bem", "Bemerkung", "text", "")], knopf="Übernehmen")
    gesendet = []
    mk.angewendet.connect(lambda w: gesendet.append(dict(w)))
    mk.show()
    _app().processEvents()
    return mk, gesendet


def test_maske():
    from PySide6 import QtCore, QtGui, QtTest
    app = _app()
    mk, gesendet = _maske()
    e = mk._felder["E_cm"]
    check("Maske zeigt 33000.0 als „33 000“, 1.5 als „1,5“ (Komma, Frage 6)",
          e.text() == "33 000" and mk._felder["x"].text() == "1,5",
          f"{e.text()!r} {mk._felder['x'].text()!r}")
    check("kein QDoubleValidator (folgt dem Gebietsschema des Systems)",
          not isinstance(e.validator(), QtGui.QDoubleValidator), type(e.validator()).__name__)
    e.clear()
    e.setFocus()
    QtTest.QTest.keyClicks(e, "2.000.000")
    app.processEvents()
    check("„2.000.000“ getippt bleibt stehen (nichts verschluckt)", e.text() == "2.000.000", repr(e.text()))
    w = mk.werte()
    check("… und wird nicht still zu 0 oder 2", w["E_cm"] not in (0.0, 2.0, 2e6), repr(w["E_cm"]))
    check("… roter Rahmen, „Übernehmen“ gesperrt",
          "#c0392b" in e.styleSheet() and not mk.btn_anwenden.isEnabled(),
          f"{e.styleSheet()[:40]!r} {mk.btn_anwenden.isEnabled()}")
    meld = getattr(mk, "lbl_zahlmeldung", None)
    check("… Meldung in der Maske nennt die Schreibweise „2 000 000“",
          meld is not None and meld.isVisible() and "2 000 000" in meld.text(),
          meld.text() if meld is not None else "-")
    mk.anwenden()
    check("… „Übernehmen“ (auch per Aufruf) übernimmt nichts", not gesendet)

    e.setText("33.000")
    app.processEvents()
    check("„33.000“: Knopf frei, gelber Hinweis „33,000 – gemeint 33 000?“",
          mk.btn_anwenden.isEnabled() and "33,000 – gemeint 33 000?" in (meld.text() if meld else "")
          and "#e0a800" in e.styleSheet(), meld.text() if meld else "-")
    mk.anwenden()
    check("… erstes „Übernehmen“ fragt nur", not gesendet)
    mk.anwenden()
    check("… zweites „Übernehmen“ bestätigt 33,000",
          len(gesendet) == 1 and gesendet[0]["E_cm"] == 33.0, str(gesendet))
    e.setText("33 000")
    mk.anwenden()
    check("„33 000“ gilt sofort als 33 000 (bis 24.09.: 0)",
          len(gesendet) == 2 and gesendet[1]["E_cm"] == 33000.0, str(gesendet[-1:]))

    gesendet.clear()
    e.setText("1.500")
    e.setFocus()
    QtTest.QTest.keyClick(e, QtCore.Qt.Key_Return)
    app.processEvents()
    check("Eingabetaste bei „1.500“: erst nur Hinweis", not gesendet)
    QtTest.QTest.keyClick(e, QtCore.Qt.Key_Return)
    app.processEvents()
    check("… zweite Eingabetaste übernimmt 1,5", len(gesendet) == 1 and gesendet[0]["E_cm"] == 1.5,
          str(gesendet))

    e.setText("1234.5")
    e.editingFinished.emit()
    check("nach dem Verlassen formatiert: „1234.5“ → „1 234,5“", e.text() == "1 234,5", repr(e.text()))
    e.setText("2.5")
    check("Dezimalpunkt gilt weiter: „2.5“ = 2,5", mk.werte()["E_cm"] == 2.5)
    n = mk._felder["n"]
    n.setText("1.5")
    check("ganze Zahl: „1.5“ sperrt „Übernehmen“", not mk.btn_anwenden.isEnabled())
    n.setText("4")
    check("… „4“ gibt frei", mk.btn_anwenden.isEnabled() and mk.werte()["n"] == 4.0)
    mk.setzen("x", 0.1 + 0.2)
    check("setzen schreibt ohne Rauschen: 0,1 + 0,2 → „0,3“", mk._felder["x"].text() == "0,3",
          mk._felder["x"].text())
    mk.hide()


def test_geaenderte_felder():
    mk, _g = _maske()
    geaendert = getattr(mk, "geaenderte_felder", None)
    check("Maske kennt ihre geänderten Felder", callable(geaendert))
    if not callable(geaendert):
        return
    check("… frisch geöffnet: keine", geaendert() == set(), str(geaendert()))
    mk.setzen("bem", "Hinweis")
    mk._felder["x"].setText("1.5")          # gleiche Zahl, andere Schreibweise
    check("… Bemerkung geändert, x nur anders geschrieben", geaendert() == {"bem"}, str(geaendert()))
    mk.hide()


# --------------------------------------------------------------------------
# Dialoge: dasselbe Feld, OK gesperrt
# --------------------------------------------------------------------------
def test_dialog():
    from PySide6 import QtWidgets
    _app()
    from statik3d.gui import dialogs as dg
    d = dg.MaterialDialog(None)
    ok = d.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
    d.E.setText("2.000.000")
    check("Dialog: „2.000.000“ sperrt OK", not ok.isEnabled())
    check("… value() liefert nicht still 0", _wirft(d.E.value), d.E.text())
    d.E.setText("210")
    check("… „210“ gibt OK frei", ok.isEnabled() and d.E.value() == 210.0)
    d.fy.setText("355.000")
    check("… „355.000“ sperrt OK bis zur Bestätigung", not ok.isEnabled())
    bestaetigen = getattr(d.fy, "bestaetigen", None)
    if callable(bestaetigen):
        bestaetigen()
    check("… bestätigt: OK frei, fy = 355", ok.isEnabled() and d.fy.value() == 355.0)
    d.fy.setText("355 000")
    check("… „355 000“ ist 355 000", ok.isEnabled() and d.fy.value() == 355000.0)
    d.E.setText("2.000.000")
    zeile = getattr(d, "lbl_zahlmeldung", None)
    check("… gesperrt mit sichtbarem Grund: Meldungszeile über den Knöpfen nennt „2 000 000“",
          zeile is not None and not zeile.isHidden() and "2 000 000" in zeile.text(),
          zeile.text() if zeile is not None else "-")
    d.E.setText("210")
    check("… gültig: Meldungszeile wieder weg", zeile is not None and zeile.isHidden())
    d.deleteLater()

    # Volumendialog: Kerbfall „2.000.000“ sperrt OK und wird nie still 0
    from statik3d.model import Model
    kd = dg.KoerperDialog(None, Model())
    ok = kd.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
    kd.kerbfall.setText("2.000.000")
    check("Volumendialog: Kerbfall „2.000.000“ sperrt OK, werte() liefert nicht still 0",
          not ok.isEnabled() and _wirft(kd.werte))
    kd.deleteLater()


def test_programmwerte():
    """Werte, die das Programm selbst in ein Zahlenfeld schreibt, sind nie
    mehrdeutig (f"{123.456:g}" ist 123,456, nicht „gemeint 123 456?“)."""
    from PySide6 import QtWidgets
    _app()
    from statik3d.gui import dialogs as dg
    from statik3d.gui import zahlenfeld as zf
    from statik3d.model import DofBehaviour, Support
    f = zf.Zahlenfeld(None)
    f.setzen("123.456")
    check("Zahlenfeld.setzen(„123.456“) zeigt 123,456 ohne Rückfrage",
          f.text() == "123,456" and not f.offene_frage(), f.text())
    s = Support(0, [])
    s.behaviour = {2: DofBehaviour("spring", 123456.0, "", 0.001125, 0.0, None)}
    d = dg.SupportNonlinearDialog(None, s, "Knotenlager")
    ok = d.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
    typ, k, _fail, slip, _mu, _ref = d.rows[2]
    check("Dialog Nichtlinearität: Feder 123 456 N/m steht als 123,456 kN/m, OK frei",
          ok.isEnabled() and k.value() == 123.456 and slip.value() == 1.125 and not k.offene_frage(),
          f"{k.text()!r} {slip.text()!r} OK={ok.isEnabled()}")
    k.setText("2.000.000")
    check("… „2.000.000“ als Steifigkeit sperrt OK", not ok.isEnabled())
    d.deleteLater()


def test_tippen():
    """Zwischenstaende beim Tippen („-“, „2 0“, „1e“) sind neutral; rot wird
    es erst beim Verlassen oder Uebernehmen."""
    from PySide6 import QtTest
    app = _app()
    mk, gesendet = _maske()
    e = mk._felder["x"]
    meld = mk.lbl_zahlmeldung
    e.clear()
    e.setFocus()
    QtTest.QTest.keyClicks(e, "-")
    app.processEvents()
    check("„-“ getippt: keine Meldungszeile, kein roter Rahmen",
          meld.isHidden() and "#c0392b" not in e.styleSheet(), f"{meld.text()!r} {e.styleSheet()[:30]!r}")
    check("… „Übernehmen“ bleibt dabei gesperrt", not mk.btn_anwenden.isEnabled())
    QtTest.QTest.keyClicks(e, "10")
    app.processEvents()
    check("„-10“: gültig, frei", mk.btn_anwenden.isEnabled() and mk.werte()["x"] == -10.0)
    e.clear()
    QtTest.QTest.keyClicks(e, "2 0")
    app.processEvents()
    check("„2 0“ (auf dem Weg zu 2 000): keine Meldungszeile", meld.isHidden(), meld.text())
    e.editingFinished.emit()
    app.processEvents()
    check("… Feld verlassen: jetzt rot mit Meldung",
          not meld.isHidden() and "#c0392b" in e.styleSheet(), meld.text())
    e.clear()
    QtTest.QTest.keyClicks(e, "1e")
    app.processEvents()
    mk.anwenden()
    app.processEvents()
    check("„1e“ und „Übernehmen“: nichts übernommen, Meldung sichtbar",
          not gesendet and not meld.isHidden(), meld.text())
    e.clear()
    QtTest.QTest.keyClicks(e, "2.000.000")
    app.processEvents()
    check("„2.000.000“ ist kein Zwischenstand: sofort rot",
          not meld.isHidden() and "#c0392b" in e.styleSheet())
    mk.hide()


# --------------------------------------------------------------------------
# Tabellenzellen
# --------------------------------------------------------------------------
def test_tabellenzelle():
    from PySide6 import QtCore
    _app()
    from statik3d.gui.tabellen import Datentabelle, Spalte
    t = Datentabelle([Spalte("Knoten", "", "ganz"), Spalte("x", "m", "zahl", 4, True)], "Knoten")
    t.setzen([[0, 1234.5678]])
    aufrufe = []
    t.modell.aendern = lambda z, k, v: aufrufe.append(v) or True
    idx = t.modell.index(0, 1)
    text = t.modell.data(idx, QtCore.Qt.EditRole)
    check("Zelle öffnet mit voller Genauigkeit „1234,5678“ (bis 24.09.: „1234.57“)",
          text == "1234,5678", repr(text))
    t.modell.setData(idx, text, QtCore.Qt.EditRole)
    check("… ohne Änderung verlassen: kein Aufruf, Wert unverändert",
          not aufrufe and t.modell.zeilen[0][1] == 1234.5678, f"{aufrufe} {t.modell.zeilen[0][1]}")
    ok = t.modell.setData(idx, "33.000", QtCore.Qt.EditRole)
    check("„33.000“ in der Zelle: nicht übernommen, mit Meldung",
          not ok and not aufrufe and "gemeint 33 000" in getattr(t, "letzte_meldung", ""),
          getattr(t, "letzte_meldung", "-"))
    ok = t.modell.setData(idx, "2.000.000", QtCore.Qt.EditRole)
    check("„2.000.000“ in der Zelle: nicht übernommen, mit Meldung",
          not ok and "2 000 000" in getattr(t, "letzte_meldung", ""), getattr(t, "letzte_meldung", "-"))
    ok = t.modell.setData(idx, "2 000,5", QtCore.Qt.EditRole)
    check("„2 000,5“ in der Zelle: 2000,5", ok and t.modell.zeilen[0][1] == 2000.5, str(t.modell.zeilen[0][1]))
    ok = t.modell.setData(idx, "= 2*3,5", QtCore.Qt.EditRole)
    check("Formel bleibt: „= 2*3,5“ = 7", ok and t.modell.zeilen[0][1] == 7.0)
    tg = Datentabelle([Spalte("Knoten", "", "ganz"), Spalte("n", "", "ganz", 0, True)], "Teilung")
    tg.setzen([[0, 4]])
    aufrufe_g = []
    tg.modell.aendern = lambda z, k, v: aufrufe_g.append(v) or True
    ok = tg.modell.setData(tg.modell.index(0, 1), "1.5", QtCore.Qt.EditRole)
    check("Spalte „ganz“: „1.5“ wird abgewiesen (nicht still 2)",
          not ok and not aufrufe_g and tg.modell.zeilen[0][1] == 4, f"{aufrufe_g} {tg.modell.zeilen[0][1]}")


# --------------------------------------------------------------------------
# Hauptfenster: Register, Statusleiste, Ergebnisse behalten
# --------------------------------------------------------------------------
_FENSTER = {}


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.error = lambda text, *a, **k: w.info("FEHLER " + str(text))
    _FENSTER.update(w=w, app=app)
    return w, app


def _label(w, anfang: str) -> str:
    from PySide6 import QtWidgets
    for lb in w.findChildren(QtWidgets.QLabel):
        if lb.text().startswith(anfang):
            return lb.text()
    return ""


def _letzte_kontaktzeile(w) -> str:
    tb = w.tbl_cdef
    it = tb.item(tb.rowCount() - 1, tb.columnCount() - 1) if tb.rowCount() else None
    return it.text() if it is not None else ""


def test_register_einheiten():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.new_model()
    app.processEvents()
    check("Statusleiste zeigt die gewählten Einheiten statt „m · N · Pa“",
          "kN" in w.lbl_einheiten.text() and w.lbl_einheiten.text() != "m · N · Pa", w.lbl_einheiten.text())
    check("Register Lager/Lasten: Kräfte in kN, Momente in kNm",
          "[kN]" in _label(w, "Fx") and "[kNm]" in _label(w, "Mx"), f"{_label(w, 'Fx')} {_label(w, 'Mx')}")
    check("… Streckenlast in kN/m, Flächenlast in kN/m², Feder in kN/m",
          "[kN/m]" in _label(w, "q [") and "[kN/m²]" in _label(w, "p [")
          and "[kN/m]" in _label(w, "Federsteifigkeit"),
          f"{_label(w, 'q [')} {_label(w, 'p [')} {_label(w, 'Federsteifigkeit')}")
    check("Register Kontakt: Steifigkeit in kN/m", "[kN/m]" in _label(w, "Steifigkeit ["),
          _label(w, "Steifigkeit ["))
    check("Flächenlast-Vorgabe −1000 N/m² steht als −1 kN/m²", w.p_face.text() == "-1", w.p_face.text())

    w.beam_p2[0].set(6.0)
    w.beam_n.setValue(6)
    w.make_beams()
    app.processEvents()
    w.sel[0].setText("0"); w.sel[1].setText("0"); w.do_select()
    w.ed_spring.set(5)
    for i, c in enumerate(w.cb_dof):
        c.setChecked(i == 2)
    w.set_support()
    sup = w.model.supports[-1] if w.model.supports else None
    check("Feder 5 im Register = 5000 N/m im Modell (bis 24.09.: 5 N/m)",
          sup is not None and sup.stiffness and sup.stiffness[0] == 5000.0,
          str(sup.stiffness if sup else None))
    w.sel[0].setText("6"); w.sel[1].setText("6"); w.do_select()
    lc = w.model.case()
    n0 = len(lc.nodal_loads)
    w.ld[2].set(-10)
    w.add_load()
    check("Knotenlast −10 im Register = −10 000 N (bis 24.09.: −10 N)",
          len(lc.nodal_loads) == n0 + 1 and lc.nodal_loads[-1].F[2] == -10000.0,
          str(lc.nodal_loads[-1].F if lc.nodal_loads else None))
    w.q[2].set(-2)
    w.add_beam_load()
    check("Streckenlast −2 im Register = −2000 N/m",
          lc.beam_loads and lc.beam_loads[-1].q[2] == -2000.0,
          str(lc.beam_loads[-1].q if lc.beam_loads else None))

    w.sel[0].setText("3"); w.sel[1].setText("3"); w.do_select()
    w.cs_k.set(3)
    w.cs_gap.set(0.002)
    w.add_contact_support()
    cs = w.model.contact_supports[-1] if w.model.contact_supports else None
    check("Register Kontakt: Steifigkeit 3 = 3000 N/m, Spalt 0,002 m",
          cs is not None and cs.stiffness == 3000.0 and abs(cs.gap - 0.002) < 1e-12,
          f"{cs.stiffness if cs else None} {cs.gap if cs else None}")
    zeile = _letzte_kontaktzeile(w)
    check("… die Liste darunter nennt k in kN/m mit Komma: „k 3 kN/m“, „Spalt 0,002 m“, kein „e+“",
          "k 3 kN/m" in zeile and "Spalt 0,002 m" in zeile and "e+" not in zeile, zeile)
    w.cs_k.set(1000000)
    w.add_contact_support()
    zeile = _letzte_kontaktzeile(w)
    check("… 1 000 000 kN/m steht als „1 000 000 kN/m“ (bis 24.09.: „k 1e+09“)",
          "k 1 000 000 kN/m" in zeile, zeile)
    # Kontaktpaar-Dialog: dieselbe Einheit wie das Register
    import statik3d.gui.main as gm
    alt_dialog = gm.ContactPairDialog
    beschriftung = []

    class _Probe(alt_dialog):
        def exec(self):                     # noqa: A003 - Qt-Name
            beschriftung.extend(lb.text() for lb in self.findChildren(QtWidgets.QLabel))
            self.master.setCurrentIndex(self.master.count() - 1)
            self.elist.setText("0")
            self.k.setText("3")
            self.gap.setText("0,002")
            return True
    gm.ContactPairDialog = _Probe
    try:
        n_cp = len(w.model.contact_pairs)
        w.add_contact_pair()
    finally:
        gm.ContactPairDialog = alt_dialog
    cp = w.model.contact_pairs[-1] if len(w.model.contact_pairs) > n_cp else None
    check("Kontaktpaar: Steifigkeit 3 im Dialog = 3000 N/m, Beschriftung [kN/m]",
          cp is not None and cp.stiffness == 3000.0 and abs(cp.gap - 0.002) < 1e-12
          and any("[kN/m]" in t for t in beschriftung),
          f"{cp.stiffness if cp else None} {[t for t in beschriftung if 'steif' in t]}")
    w.sel[0].setText("6"); w.sel[1].setText("6"); w.do_select()

    n0 = len(lc.nodal_loads)
    w.statusBar().clearMessage()
    w.ld[2].setText("2.000.000")
    app.processEvents()
    # vor add_load: den gesperrten Knopf kann niemand druecken, also muss
    # der Grund schon beim Tippen in der Statusleiste stehen
    check("„2.000.000“ im Register: die Statusleiste nennt sofort den Grund („2 000 000“)",
          "2 000 000" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
    w.add_load()
    check("„2.000.000“ im Register: keine Last (bis 24.09.: still eine Last 0)",
          len(lc.nodal_loads) == n0, f"{len(lc.nodal_loads) - n0} Lasten dazu")
    knopf = next((b for b in w.findChildren(QtWidgets.QPushButton) if b.text() == "Knotenlast aufbringen"), None)
    check("… „Knotenlast aufbringen“ gesperrt", knopf is not None and not knopf.isEnabled())
    w.ld[2].setText("1.500")
    app.processEvents()
    w.add_load()
    check("„1.500“ im Register: erst nur Hinweis", len(lc.nodal_loads) == n0)
    w.add_load()
    check("… zweites Mal: 1,5 kN = 1500 N",
          len(lc.nodal_loads) == n0 + 1 and lc.nodal_loads[-1].F[2] == 1500.0,
          str(lc.nodal_loads[-1].F if lc.nodal_loads else None))

    w.ld[2].set(-10)
    w.model.einheiten.kraft = "N"
    w.einheiten_anwenden()
    app.processEvents()
    check("Einheit auf N: Register zeigt [N], der Wert bleibt dieselbe Kraft (−10 000)",
          "[N]" in _label(w, "Fx") and w.ld[2].text() == "-10 000", f"{_label(w, 'Fx')} {w.ld[2].text()!r}")
    check("… Statusleiste folgt", " N " in f" {w.lbl_einheiten.text()} ".replace("·", " "), w.lbl_einheiten.text())
    w.model.einheiten.kraft = "kN"
    w.einheiten_anwenden()
    app.processEvents()


def _gerechnet(w, app):
    from statik3d import solver
    w.load_example("frame")
    app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False))
    app.processEvents()
    return w.analysis is not None


def _undo_n(w):
    return len(getattr(w, "_undo", []) or [])


def test_ergebnisse_behalten():
    from PySide6 import QtCore
    from statik3d.model import Berichtseintrag
    w, app = _fenster()
    check("Rahmen gerechnet", _gerechnet(w, app))
    mk = w._objektmaske("lager_einzeln", "0")
    u0 = _undo_n(w)
    mk.setzen("groesse", 2.0)
    mk.setzen("name", "Fuß links")
    mk.anwenden()
    app.processEvents()
    s0 = w.model.supports[0]
    check("Lagermaske: Name und Symbolgröße übernommen",
          s0.name == "Fuß links" and abs(float(s0.groesse) - 2.0) < 1e-12, f"{s0.name} {s0.groesse}")
    check("… die Ergebnisse bleiben (bis 24.09.: verworfen)", w.analysis is not None)
    check("… ein Rückgängig-Schritt", _undo_n(w) == u0 + 1, f"{_undo_n(w) - u0}")
    mk = w.maskenrand.maske
    u0 = _undo_n(w)
    if mk is not None:
        mk.anwenden()
        app.processEvents()
    check("„Übernehmen“ ohne Änderung: kein Rückgängig-Schritt, Ergebnisse bleiben",
          mk is not None and _undo_n(w) == u0 and w.analysis is not None, f"{_undo_n(w) - u0}")
    w.undo()
    app.processEvents()
    check("Rückgängig der Beschriftung: Name zurück, die Ergebnisse bleiben (bis 24.09.: verworfen)",
          w.model.supports[0].name != "Fuß links" and w.analysis is not None,
          f"{w.model.supports[0].name!r} {w.analysis is not None}")
    w.redo()
    app.processEvents()
    check("… Wiederholen: Name wieder da, die Ergebnisse bleiben",
          w.model.supports[0].name == "Fuß links" and w.analysis is not None)
    w._objektmaske("lager_einzeln", "0")
    app.processEvents()
    mk = w.maskenrand.maske
    if mk is not None:
        mk.setzen("typ0", "frei")
        mk.anwenden()
        app.processEvents()
    check("Lagerwirkung geändert: Ergebnisse verworfen (im Zweifel verwerfen)", w.analysis is None)

    check("neu gerechnet", _gerechnet(w, app))
    w.model.bericht.append(Berichtseintrag(name="Bild 1", quelle="case:LF1"))
    w.refresh_all()
    mk = w._objektmaske("berichtseintrag", "0")
    mk.setzen("beschriftung", "Momente am Rahmen")
    mk.setzen("bemerkung", "zur Prüfung")
    mk.anwenden()
    app.processEvents()
    check("Berichtsbild: Bildunterschrift und Bemerkung übernommen, Ergebnisse bleiben",
          w.model.bericht[0].beschriftung == "Momente am Rahmen" and w.analysis is not None)

    ok = w._lager_aendern(0, 6, 1.5)
    check("Tabelle Lager: Symbolgröße ändern behält die Ergebnisse", ok and w.analysis is not None)
    ok = w._lager_aendern(0, 2, "Fuß A")
    check("Tabelle Lager: Name ändern behält die Ergebnisse", ok and w.analysis is not None)
    lf = str(w.tbl_lastfall.modell.zeilen[0][0])
    ok = w._lastfall_aendern(0, 3, "Eigenlast und Dach")
    check("Tabelle Lastfälle: Beschreibung behält die Ergebnisse",
          ok and w.analysis is not None and w.model.load_cases[lf].description == "Eigenlast und Dach")
    ok = w._bericht_aendern(0, 3, "Neue Unterschrift")
    check("Tabelle Bericht: Bildunterschrift behält die Ergebnisse", ok and w.analysis is not None)

    w.model.add_line("L9", [0, 1])
    w.refresh_all()
    app.processEvents()
    tl = w.tbl_linie.modell
    zl9 = next(i for i, r in enumerate(tl.zeilen) if str(r[0]) == "L9")
    ok = tl.setData(tl.index(zl9, 5), "Kante", QtCore.Qt.EditRole)
    check("Tabelle Linien: Bemerkung behält die Ergebnisse",
          ok and w.model.lines["L9"].comment == "Kante" and w.analysis is not None)
    from statik3d.bridges.positions import Stellung
    i0 = int(w.tbl_lager.modell.zeilen[0][0])
    w._stellungen_obj().append(Stellung("S1", lager_aus=[w._lagerliste()[i0][1].name]))
    ok = w._lager_aendern(0, 2, "Fuß B")
    check("Lagername, den eine Stellung nennt: Umbenennen verwirft die Ergebnisse",
          ok and w.analysis is None)
    w._stellungen_obj().clear()
    check("neu gerechnet", _gerechnet(w, app))

    # Lastmaske: nur die Bemerkung einer Vorspannung
    from statik3d.model import Vorspannung
    fall = w.model.active_case
    w.model.case().vorspannungen.append(Vorspannung("Z1", "stab", 1000.0))
    k_v = len(w.model.case().vorspannungen) - 1
    w._lastmaske(fall, "vorspannungen", k_v)
    mk = w.maskenrand.maske
    mk.setzen("kommentar", "Zugstange")
    mk.anwenden()
    app.processEvents()
    check("Lastmaske: Bemerkung der Vorspannung behält die Ergebnisse",
          w.model.case().vorspannungen[k_v].kommentar == "Zugstange" and w.analysis is not None)
    mk = w.maskenrand.maske
    mk.setzen("F", 2.0)
    mk.anwenden()
    app.processEvents()
    check("… Vorspannkraft geändert: Ergebnisse verworfen",
          abs(w.model.case().vorspannungen[k_v].kraft - 2000.0) < 1e-9 and w.analysis is None)
    w.model.case().vorspannungen.pop(k_v)
    check("neu gerechnet", _gerechnet(w, app))
    # Sammelmaske: Namen mehrerer Lager
    w.sammelmaske("lager", [0, 1])
    mk = w.maskenrand.maske
    mk.setzen("name", "Fuß")
    mk.anwenden()
    app.processEvents()
    check("Sammelmaske Lager: Name behält die Ergebnisse",
          w.model.supports[0].name == "Fuß" and w.analysis is not None)
    w.sammelmaske("lager", [0, 1])
    mk = w.maskenrand.maske
    mk.setzen("d2", "nein")
    mk.anwenden()
    app.processEvents()
    check("… gesperrte Richtung geändert: Ergebnisse verworfen", w.analysis is None)
    check("neu gerechnet", _gerechnet(w, app))

    w.tabelle_zeigen("Knoten")
    app.processEvents()
    tm = w.tbl_knoten.modell
    u0 = _undo_n(w)
    idx = tm.index(1, 1)
    tm.setData(idx, tm.data(idx, QtCore.Qt.EditRole), QtCore.Qt.EditRole)
    app.processEvents()
    check("Knotenzelle geöffnet und unverändert verlassen: kein Rückgängig-Schritt",
          _undo_n(w) == u0, f"{_undo_n(w) - u0}")
    check("… und die Ergebnisse bleiben", w.analysis is not None)
    x_alt = float(w.model.nodes[int(tm.zeilen[1][0])][0])
    tm.setData(idx, "= 1 + 0,25", QtCore.Qt.EditRole)
    app.processEvents()
    check("Knotenzelle geändert: Wert neu, Ergebnisse verworfen",
          abs(float(w.model.nodes[int(tm.zeilen[1][0])][0]) - 1.25) < 1e-12 and w.analysis is None,
          f"{x_alt} → {w.model.nodes[int(tm.zeilen[1][0])][0]}")


def _geometrie_dazu(w):
    """Ein Tetraeder weit neben dem Rahmen (Linien, Flaechen, Volumen) und
    eine Unterlage - ohne Netz, die Rechnung beruehrt beides nicht."""
    import numpy as np
    from statik3d.model import Unterlage
    m = w.model
    n0 = m.nn
    m.add_nodes(np.array([[100, 0, 0], [101, 0, 0], [100, 1, 0], [100, 0, 1.]]))
    for nm, (a, b) in {"T1": (0, 1), "T2": (1, 2), "T3": (2, 0), "T4": (0, 3),
                       "T5": (1, 3), "T6": (2, 3)}.items():
        m.add_line(nm, [n0 + a, n0 + b])
    for nm, ls in {"FT1": ["T1", "T2", "T3"], "FT2": ["T1", "T5", "T4"],
                   "FT3": ["T2", "T6", "T5"], "FT4": ["T3", "T4", "T6"]}.items():
        m.add_flaeche(nm, ls)
    m.add_koerper("VT", ["FT1", "FT2", "FT3", "FT4"])
    m.unterlagen["U1"] = Unterlage("U1")
    w.refresh_all()


def test_nachbesserung():
    """Befunde der Gegenpruefung zu Paket 4 (24.09.2026)."""
    from statik3d import solver
    from statik3d.gui import masken as msk
    from statik3d.model import STANDARDKONTAKTE
    w, app = _fenster()

    # Bettung: „33.000“ in E_cm fragt erst, statt eine 1000-fach zu weiche
    # Feder in k2 zu schreiben
    w.load_example("frame")
    app.processEvents()
    mk = w._objektmaske("lager_einzeln", "0")
    mk.setzen("beton", "auf Beton (Druckkontakt)")
    mk._felder["E_cm"].setText("33.000")
    k2_vorher = mk._felder["k2"].text()
    knopf = mk.zusatzknoepfe["Bettung übernehmen"]
    knopf.click()
    app.processEvents()
    check("Bettung übernehmen, E_cm „33.000“: k2 bleibt, Meldung „gemeint 33 000?“",
          mk._felder["k2"].text() == k2_vorher and "gemeint 33 000" in mk.lbl_zahlmeldung.text(),
          f"k2 {mk._felder['k2'].text()!r} / {mk.lbl_zahlmeldung.text()!r}")
    knopf.click()
    app.processEvents()
    check("… zweiter Klick bestätigt 33 N/mm²: k2 = 3 300 kN/m", mk._felder["k2"].text() == "3 300",
          mk._felder["k2"].text())
    mk._felder["E_cm"].setText("33 000")
    knopf.click()
    app.processEvents()
    check("… „33 000“ gilt sofort: k2 = 3 300 000 kN/m", mk._felder["k2"].text() == "3 300 000",
          mk._felder["k2"].text())

    # Kontaktmaske: ungueltiges μ, dann ein Standardkontakt
    F = msk.Feld
    km = msk.Maske("Kontakt", [
        F("standard", "Standard", "wahl", "Benutzerdefiniert", ["Benutzerdefiniert"] + list(STANDARDKONTAKTE)),
        F("zug", "Zug", "wahl", "", list(w.KONTAKT_ZUG.values())),
        F("schub_x", "Schub x", "wahl", "", list(w.KONTAKT_SCHUB.values())),
        F("schub_y", "Schub y", "wahl", "", list(w.KONTAKT_SCHUB.values())),
        F("dreh", "Drehung", "wahl", "", list(w.KONTAKT_DREH.values())),
        F("mu", "μ", "zahl", 0.3)])
    w._kontaktmaske_verbinden(km)
    km._felder["mu"].setText("0,2.5")
    km._felder["standard"].setCurrentText("Verbund")
    app.processEvents()
    check("Kontaktmaske: μ „0,2.5“, dann „Verbund“: μ = 0, Hinweis nachgeführt (bis 24.09.: ValueError)",
          km._felder["mu"].text() == "0" and km.lbl_hinweis.text().startswith("Verbund"),
          f"{km._felder['mu'].text()!r} {km.lbl_hinweis.text()[:30]!r}")
    km.deleteLater()

    # Sammelmaske: Zahlenfelder, nur Geaendertes wird geschrieben
    m = w.model
    zmax = max(float(p[2]) for p in m.nodes)
    a, b = [i for i in range(m.nn) if float(m.nodes[i][2]) == zmax][:2]
    m.nodes[a][2] = m.nodes[b][2] = 4.1234567
    w._solve_done("all", solver.solve_all(m, design=False))
    app.processEvents()
    u0 = _undo_n(w)
    w.sammelmaske("knoten", [a, b])
    app.processEvents()
    mk = w.maskenrand.maske
    check("Sammelmaske Knoten: z als Zahlenfeld „4,1234567“ (bis 24.09.: „4.12346“)",
          mk._felder["z"].text() == "4,1234567", mk._felder["z"].text())
    mk.anwenden()
    app.processEvents()
    check("… „Übernehmen“ ohne Änderung: z unverändert, kein Rückgängig-Schritt, Ergebnisse bleiben",
          m.nodes[a][2] == 4.1234567 and m.nodes[b][2] == 4.1234567 and _undo_n(w) == u0
          and w.analysis is not None, f"{m.nodes[a][2]} {_undo_n(w) - u0} {w.analysis is not None}")
    mk._felder["z"].setText("4,5")
    mk.anwenden()
    app.processEvents()
    check("… „4,5“ ergibt 4,5 an beiden Knoten (bis 24.09.: Fehler)",
          m.nodes[a][2] == 4.5 and m.nodes[b][2] == 4.5, f"{m.nodes[a][2]} {m.nodes[b][2]}")
    w.sammelmaske("knoten", [a, b])
    app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["z"].setText("7.500")
    mk.anwenden()
    app.processEvents()
    check("… „7.500“ fragt erst nach (bis 24.09.: still 7,5)",
          m.nodes[a][2] == 4.5 and "gemeint 7 500" in mk.lbl_zahlmeldung.text(), mk.lbl_zahlmeldung.text())
    mk.anwenden()
    app.processEvents()
    check("… zweites „Übernehmen“ bestätigt 7,5", m.nodes[a][2] == 7.5 and m.nodes[b][2] == 7.5)
    m.nodes[a][2] = m.nodes[b][2] = 1e-5
    w.sammelmaske("knoten", [a, b])
    app.processEvents()
    mk = w.maskenrand.maske
    check("… 1e-5 steht als „0,00001“ (bis 24.09.: „1e-05“)", mk._felder["z"].text() == "0,00001",
          mk._felder["z"].text())

    # Schnittebene: Programmwerte sind keine Rueckfrage
    w.schnitt_frei = {"normale": (0.0, 1.0, 0.0), "ursprung": (123.4567, 1.5678, 0.9)}
    w.maske_schnittebene()
    app.processEvents()
    mk = w.maskenrand.maske
    felder = [mk._felder[k] for k in ("nx", "ny", "nz", "ox", "oy", "oz")]
    check("Schnittebene: Ursprung 123,4567 öffnet als „123,457“ ohne gelbe Rückfrage",
          not any(f.offene_frage() for f in felder) and mk._felder["ox"].text() == "123,457",
          mk._felder["ox"].text())
    w.schnitt_frei["ursprung"] = (2.3456, 1.5678, 0.9)
    w._schnitt_maske_nachfuehren()
    geschnitten = []
    mk.angewendet.connect(lambda _w: geschnitten.append(1))
    check("… nach dem Nachführen keine offene Rückfrage", not any(f.offene_frage() for f in felder),
          mk._felder["ox"].text())
    mk.anwenden()
    app.processEvents()
    check("… erstes „Schneiden“ schneidet", geschnitten == [1], str(geschnitten))
    w.act_schnitt.setChecked(False)
    w.maskenrand.schliessen()
    app.processEvents()

    # Beschriftungsweg: Linie, Lastfall, Flaeche, Volumen, Unterlage
    check("neu gerechnet", _gerechnet(w, app))
    _geometrie_dazu(w)
    app.processEvents()
    check("… Tetraeder und Unterlage dazu, die Ergebnisse sind noch da", w.analysis is not None)
    mk = w._objektmaske("linie", "T1")
    mk.setzen("kommentar", "Kante")
    mk.anwenden()
    app.processEvents()
    check("Linienmaske: nur Bemerkung, die Ergebnisse bleiben",
          w.model.lines["T1"].comment == "Kante" and w.analysis is not None)
    lf = str(w.model.active_case)
    mk = w._objektmaske("lastfall", lf)
    mk.setzen("beschreibung", "Eigenlast und Dach")
    mk.anwenden()
    app.processEvents()
    check("Lastfallmaske: nur Beschreibung, die Ergebnisse bleiben",
          w.model.load_cases[lf].description == "Eigenlast und Dach" and w.analysis is not None)
    for art, name, attr in (("geoflaeche", "FT1", "flaechen"), ("geokoerper_einzeln", "VT", "koerper")):
        try:
            w._objekt_uebernehmen(art, name, {"kommentar": "Deckel", "vernetzen": False}, False,
                                  geaendert={"kommentar"})
        except Exception as ex:             # noqa: BLE001
            print("   ", art, ex)
        app.processEvents()
        check(f"Maske {art}: nur Bemerkung, die Ergebnisse bleiben",
              getattr(w.model, attr)[name].kommentar == "Deckel" and w.analysis is not None)
    mk = w._objektmaske("geokoerper_einzeln", "VT")
    kf = mk._felder.get("kerbfall")
    if kf is not None:
        kf.setText("2.000.000")
    check("Volumenmaske: Kerbfall „2.000.000“ sperrt „Übernehmen“ (bis 24.09.: Textfeld, Fehler beim Lesen)",
          kf is not None and not mk.btn_anwenden.isEnabled())
    if kf is not None:
        kf.setText("71,5")
    check("… „71,5“ wird 71,5", kf is not None and mk.werte().get("kerbfall") == 71.5,
          str(mk.werte().get("kerbfall")))
    w.maskenrand.schliessen()
    tf = w.tbl_geoflaeche.modell
    z = next((i for i, r in enumerate(tf.zeilen) if str(r[0]) == "FT2"), -1)
    ok = z >= 0 and w._geoflaeche_aendern(z, 7, "Seite")
    check("Tabelle Flächen: Bemerkung (Spalte 7) behält die Ergebnisse", ok and w.analysis is not None, str(z))
    tk = w.tbl_geokoerper.modell
    z = next((i for i, r in enumerate(tk.zeilen) if str(r[0]) == "VT"), -1)
    ok = z >= 0 and w._geokoerper_aendern(z, 8, "Block")
    check("Tabelle Volumen: Bemerkung (Spalte 8) behält die Ergebnisse", ok and w.analysis is not None, str(z))
    tu = w.tbl_unterlagen.modell
    z = next((i for i, r in enumerate(tu.zeilen) if str(r[1]) == "U1"), -1)
    ok = z >= 0 and w._unterlage_aendern(z, 6, "Skizze A") and w._unterlage_aendern(z, 7, "zur Prüfung")
    u = w.model.unterlagen.get("U1")
    check("Tabelle Unterlagen: Beschriftung und Bemerkung behalten die Ergebnisse",
          ok and u is not None and u.beschriftung == "Skizze A" and u.bemerkung == "zur Prüfung"
          and w.analysis is not None, str(z))
    w.undo()
    app.processEvents()
    check("… Rückgängig der Unterlagen-Bemerkung behält die Ergebnisse",
          w.model.unterlagen["U1"].bemerkung == "" and w.analysis is not None)


def test_bemerkung_mit_vernetzen():
    """Gegenprobe: steht „gleich vernetzen“ an, vernetzt „Übernehmen“ auch
    dann, wenn nur die Bemerkung geändert ist - der Beschriftungsweg darf
    das nicht überspringen."""
    import numpy as np
    from statik3d.model import Material, ShellProp
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6))
    m.add_shell_prop(ShellProp("t10", 0.01))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0.]]))
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="t10", material="S235")
    w.refresh_all()
    app.processEvents()
    mk = w._objektmaske("geoflaeche", "F1")
    check("Flächenmaske: „gleich vernetzen“ steht an", bool(mk.werte().get("vernetzen")))
    mk.setzen("kommentar", "Deckblech")
    mk.anwenden()
    app.processEvents()
    f = w.model.flaechen["F1"]
    check("… nur Bemerkung geändert: übernommen und trotzdem vernetzt",
          f.kommentar == "Deckblech" and bool(f.elemente), f"{f.kommentar!r} {len(f.elemente or [])} Elemente")


# --------------------------------------------------------------------------
# Nachkontrolle 25.09.2026: Verlassen mit Tab, Textfelder mit Zahlen,
# Anzeige nie wissenschaftlich
# --------------------------------------------------------------------------
def _rot(feld) -> bool:
    return "#c0392b" in feld.styleSheet()


def _tippen(feld, text):
    from PySide6 import QtCore, QtTest
    feld.setFocus()
    feld.selectAll()
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_Delete)
    QtTest.QTest.keyClicks(feld, text)
    _app().processEvents()


def _tab(feld):
    """Das Feld mit einer echten Tab-Taste verlassen (kein editingFinished.emit:
    Qt sendet es beim Fokusverlust nur bei annehmbarer Eingabe)."""
    from PySide6 import QtCore, QtTest
    QtTest.QTest.keyClick(feld, QtCore.Qt.Key_Tab)
    _app().processEvents()


def test_verlassen_mit_tab():
    """Ein unfertiger Rest („12 5“, „-“, „1e“) wird beim Verlassen rot und
    gemeldet - auch mit Tab (bis 25.09.2026 blieb er neutral, der Knopf war
    ohne Meldung gesperrt)."""
    from PySide6 import QtWidgets
    app = _app()
    mk, _g = _maske()
    mk.activateWindow()
    app.processEvents()
    e = mk._felder["x"]
    for eingabe in ("12 5", "-", "1e"):
        _tippen(e, eingabe)
        neutral = not _rot(e) and mk.lbl_zahlmeldung.isHidden()
        _tab(e)
        check(f"Maske: „{eingabe}“ getippt neutral, Tab: Fokus weg, roter Rahmen, Meldungszeile",
              neutral and not e.hasFocus() and _rot(e) and not mk.lbl_zahlmeldung.isHidden()
              and bool(mk.lbl_zahlmeldung.text()) and not mk.btn_anwenden.isEnabled(),
              f"neutral {neutral} Fokus {e.hasFocus()} rot {_rot(e)} "
              f"Meldung {mk.lbl_zahlmeldung.text()[:50]!r}")
    _tippen(e, "2,5")
    _tab(e)
    check("… danach „2,5“ + Tab: gültig, frei, kein Rot", not _rot(e) and mk.btn_anwenden.isEnabled())
    mk.hide()

    from statik3d.gui import dialogs as dg
    d = dg.MaterialDialog(None)
    d.show()
    d.activateWindow()
    app.processEvents()
    ok = d.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
    _tippen(d.E, "12 5")
    _tab(d.E)
    check("Werkstoffdialog: „12 5“ + Tab: rot, Meldungszeile über OK, OK gesperrt",
          _rot(d.E) and not d.lbl_zahlmeldung.isHidden() and "Leerzeichen" in d.lbl_zahlmeldung.text()
          and not ok.isEnabled(), d.lbl_zahlmeldung.text())
    d.reject()
    d.deleteLater()

    w, app = _fenster()
    w.load_example("frame")
    w.activateWindow()
    app.processEvents()
    w.sel[0].setText("1")
    w.sel[1].setText("1")
    w.do_select()
    w.statusBar().clearMessage()
    _tippen(w.ld[2], "-")
    _tab(w.ld[2])
    check("Register Lasten: „-“ + Tab: rot, Statusleiste nennt den Grund",
          _rot(w.ld[2]) and "keine Zahl" in w.statusBar().currentMessage(),
          w.statusBar().currentMessage()[:60])
    _tippen(w.ld[2], "0")
    _tab(w.ld[2])


def test_textfelder_zahlenregel():
    """Felder, die bis 25.09.2026 als Text mit float(text.replace(',', '.'))
    gelesen wurden, nahmen „1.000“ still als 1 (Werkstoffmaske f_y: 1 N/mm²).
    Jetzt Zahlenfelder bzw. dieselbe Regel: „1.000“ fragt nach oder wird
    abgewiesen."""
    from PySide6 import QtWidgets
    from statik3d import zahlen as zl
    from statik3d.gui import zahlenfeld as zf
    w, app = _fenster()
    fehler = []
    alt_error = w.error
    w.error = lambda text, *a, **k: (fehler.append(str(text)), w.info("FEHLER " + str(text)))

    # die Regel fuer Werte aus Masken, Listen und Zellen
    fw = getattr(zl, "feldwert", None)
    check("zahlen.feldwert: „1.000“ abgewiesen, „1 000“ = 1000, 2.5 bleibt, leer = Vorgabe",
          callable(fw) and _wirft(fw, "1.000") and fw("1 000") == 1000.0 and fw(2.5) == 2.5
          and fw("", 7.0) == 7.0 and fw(None) is None and _wirft(fw, "2.000.000"))
    liste = getattr(zl, "zahlenliste", None)
    check("zahlen.zahlenliste: „1,5, 2“ = [1,5; 2], „1.000, 0“ abgewiesen",
          callable(liste) and liste("1,5, 2") == [1.5, 2.0] and _wirft(liste, "1.000, 0")
          and liste("") == [])

    # Werkstoffmaske f_y / f_u (gemessen 25.09.: „1.000“ -> 1 N/mm²)
    w.new_model()
    app.processEvents()
    name = next(iter(w.model.materials))
    fy_vorher = w.model.materials[name].fy
    mk = w._objektmaske("werkstoff", name) or w.maskenrand.maske
    for key in ("fy", "fu"):
        check(f"Werkstoffmaske {key}: Zahlenfeld", isinstance(mk._felder.get(key), zf.Zahlenfeld),
              type(mk._felder.get(key)).__name__)
    if isinstance(mk._felder.get("fy"), zf.Zahlenfeld):
        mk._felder["fy"].setText("1.000")
        mk.anwenden()
        app.processEvents()
        mt = w.model.materials.get(name)
        check("… f_y „1.000“ + Übernehmen: nichts geschrieben, Meldung „gemeint 1 000?“",
              mt is not None and mt.fy == fy_vorher and "gemeint 1 000" in mk.lbl_zahlmeldung.text(),
              f"fy {getattr(mt, 'fy', None)} {mk.lbl_zahlmeldung.text()[:40]!r}")
        mk._felder["fy"].setText("")
        mk._felder["fu"].setText("")
        mk.anwenden()
        app.processEvents()
        mt = w.model.materials.get(name)
        check("… leer bleibt „aus der Stahlsorte“ (None), nicht 0",
              mt is not None and mt.fy is None and mt.fu is None,
              f"{getattr(mt, 'fy', '-')} {getattr(mt, 'fu', '-')}")
        mk = w.maskenrand.maske
        mk._felder["fy"].setText("355")
        mk.anwenden()
        app.processEvents()
        check("… „355“ = 355 N/mm²", w.model.materials[name].fy == 355e6, str(w.model.materials[name].fy))

    # die uebrigen Masken: Feld ist ein Zahlenfeld, „1.000“ fragt nach
    from statik3d.wasserdruck import Wasserdruck
    w.load_example("frame")
    app.processEvents()
    m = w.model
    m.add_kontaktbedingung("Fuge T")
    m.wasserdruecke["WT"] = Wasserdruck("WT")
    faelle = [("Bemaßung", lambda: w.bemassung_neu("linear"), ("versatz", "nachkomma")),
              ("Schweißnaht", lambda: w.maske_schweissnaht(), ("kf_vorgabe",)),
              ("Netz", lambda: w.maske_netzeinstellungen(), ("h_min", "h_max")),
              ("Passung", lambda: w.maske_passung(), ("mu",)),
              ("Wasserdruck", lambda: w.maske_wasserdruck(), ("h_uw", "z_sohle", "z_uk", "z_ok", "breite")),
              ("Wind", lambda: w.maske_wind(), ("z_schnitt", "z_boden", "cf")),
              ("Schwingung", lambda: w.maske_schwingung(), ("d_kante",))]
    for titel, oeffnen, keys in faelle:
        try:
            oeffnen()
            app.processEvents()
            mk = w.maskenrand.maske
            felder = {k: (mk._felder.get(k) if mk is not None else None) for k in keys}
        except Exception as ex:          # noqa: BLE001
            check(f"{titel}: Maske öffnet", False, repr(ex))
            continue
        art = {k: type(f).__name__ for k, f in felder.items()}
        gut = all(isinstance(f, zf.Zahlenfeld) for f in felder.values())
        frage = []
        if gut:
            for k, f in felder.items():
                f.setText("1.000")
                frage.append(f.offene_frage() or f.ungueltig())
                f.setText("")
        check(f"{titel}: {', '.join(keys)} sind Zahlenfelder, „1.000“ fragt nach",
              gut and all(frage), str(art))

    # Stab-Versatz (Liste y, z): „1.000, 0“ wird abgewiesen, nicht 1 mm
    e0 = 0
    ex_vorher = list(getattr(m.elements[e0], "exzentrizitaet", []) or [])
    mk = w._objektmaske("stabelement", str(e0)) or w.maskenrand.maske
    fehler.clear()
    if mk is not None and "ex_a" in mk._felder:
        mk.setzen("ex_a", "1.000, 0")
        mk.anwenden()
        app.processEvents()
        check("Stab-Versatz „1.000, 0“: abgewiesen mit Meldung, Versatz unverändert",
              list(getattr(m.elements[e0], "exzentrizitaet", []) or []) == ex_vorher
              and any("1.000" in t for t in fehler), f"{m.elements[e0].exzentrizitaet} {fehler[-1:]}")
        mk = w._objektmaske("stabelement", str(e0)) or w.maskenrand.maske
        mk.setzen("ex_a", "12,5, 0")
        mk.anwenden()
        app.processEvents()
        ex = getattr(m.elements[e0], "exzentrizitaet", []) or []
        check("… „12,5, 0“ = 12,5 mm in y", bool(ex) and abs(ex[0][1] - 0.0125) < 1e-12, str(ex))
    else:
        check("Stab-Versatz: Maske mit ex_a", False)
    check("Liste Achse/Gewichte (_zahlenliste): „1.000, 0, 0“ abgewiesen, „0,5, 1“ gelesen",
          _wirft(lambda: w._zahlenliste("1.000, 0, 0", zahl=float))
          and w._zahlenliste("0,5, 1", zahl=float) == [0.5, 1.0])

    # ψ eines Lastfalls
    lf = next(iter(m.load_cases))
    psi_vorher = m.load_cases[lf].psi
    mk = w._objektmaske("lastfall", lf) or w.maskenrand.maske
    fehler.clear()
    mk.setzen("psi", "1.000/0,5/0,3")
    mk.anwenden()
    app.processEvents()
    check("Lastfall ψ „1.000/0,5/0,3“: abgewiesen, ψ unverändert",
          m.load_cases[lf].psi == psi_vorher and any("1.000" in t for t in fehler),
          f"{m.load_cases[lf].psi} {fehler[-1:]}")

    # Beulfeld: Steifentabelle
    from statik3d.gui import dialogs as dg
    d = dg.BeulfeldDialog(None, m)
    d._zeile("laengs")
    d.tbl.item(0, 1).setText("1.000")
    d.show()
    app.processEvents()
    d.accept()                  # wie der OK-Knopf (bb.accepted -> self.accept)
    app.processEvents()
    zeile = getattr(d, "lbl_zahlmeldung", None)
    check("Beulfeld: Steifenlage „1.000“: OK schließt nicht, Meldung nennt „1.000“",
          d.isVisible() and zeile is not None and "1.000" in zeile.text(),
          zeile.text() if zeile is not None else "-")
    d.tbl.item(0, 1).setText("1 000")
    try:
        lage = d.steifen()[0].lage
    except ValueError as ex:
        lage = repr(ex)
    check("… „1 000“ = 1 m", lage == 1.0, str(lage))
    d.deleteLater()

    # Stellung: Antriebsknoten
    sd = dg.StellungDialog(None, None, m)
    ok = sd.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.Ok)
    ist_feld = isinstance(sd.ed_knoten, zf.Zahlenfeld)
    sd.ed_knoten.setText("1.000")
    check("Stellung: Antriebsknoten ist ein ganzes Zahlenfeld, „1.000“ sperrt OK",
          ist_feld and not ok.isEnabled(), f"{type(sd.ed_knoten).__name__} OK {ok.isEnabled()}")
    sd.deleteLater()

    # Profileditor: Knotenkoordinate „1.000“ - OK gesperrt, rote Meldung
    from statik3d.gui.profilmaske import ProfilEditor
    pe = ProfilEditor(None)
    pe.knoten_zufuegen(1, 0.0, 0.0)
    pe.knoten_zufuegen(2, 100.0, 0.0)
    pe.element_zufuegen(1, 2, 10.0)
    ok_vorher = pe.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled()
    try:
        pe.tb_knoten.item(1, 1).setText("1.000")
        pe.aktualisieren()
        info = pe.lbl_werte.text()
    except Exception as ex:              # noqa: BLE001
        info = f"Ausnahme {ex!r}"
    check("Profileditor: y „1.000“ sperrt OK, Meldung nennt „1.000“",
          ok_vorher and not pe.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled()
          and "1.000" in info, info[:80])
    pe.deleteLater()
    w.error = alt_error


def test_listen_anzahl():
    """Listenfelder mit fester Anzahl (25.09.2026, letzte Runde der
    Gegenpruefung): bis dahin kuerzten sie ueberzaehlige Eintraege still -
    „12,5; 1 000“ wurde Versatz z = 1 mm, „1, 0, 0, 5“ eine Achse aus den
    ersten drei, RBE3-Gewichte mit falscher Anzahl still „alle gleich“.
    Jetzt: Meldung mit Feldname, erwarteter und gefundener Anzahl; das Objekt
    bleibt, es entsteht kein leerer Rueckgaengig-Schritt. Leerzeichen als
    Tausender innerhalb eines Eintrags nur, wenn „;“ trennt."""
    from statik3d import zahlen as zl
    w, app = _fenster()
    fehler = []
    alt_error = w.error
    w.error = lambda text, *a, **k: (fehler.append(str(text)), w.info("FEHLER " + str(text)))

    def meldung(fn, *a):
        try:
            fn(*a)
        except (ValueError, TypeError) as ex:
            return str(ex)
        return ""

    # die Regel ohne Oberflaeche
    try:
        gelesen = zl.zahlenliste("12,5; 1 000", 2, "Versatz")
    except (ValueError, TypeError) as ex:
        gelesen = repr(ex)
    check("zahlenliste mit Anzahl: „12,5; 1 000“ = [12,5; 1000] („;“ trennt, Leerzeichen = Tausender)",
          gelesen == [12.5, 1000.0], str(gelesen))
    t = meldung(zl.zahlenliste, "12,5 1 000", 2, "Versatz")
    check("… „12,5 1 000“ ohne „;“: Meldung nennt „1 000“ und „;“ (nicht still 3 Einträge)",
          "1 000" in t and ";" in t, t)
    t = meldung(zl.zahlenliste, "1, 0, 0, 5", 3, "Ersatzachse x, y, z")
    check("… „1, 0, 0, 5“ für drei Werte: Meldung mit Feldname, 3 erwartet, 4 gefunden",
          "Ersatzachse" in t and "3" in t and "4" in t, t)
    t = meldung(zl.zahlenliste, "5", 2, "Versatz")
    check("… zu wenige („5“ für y, z): Meldung", "2" in t and "1" in t, t)
    try:
        ok = zl.zahlenliste("1 0 0", 3) == [1.0, 0.0, 0.0] and zl.zahlenliste("", 3) == []
    except (ValueError, TypeError):
        ok = False
    check("… „1 0 0“ = drei Werte, leer = [] (Vorgabe beim Aufrufer)", ok)

    w.load_example("frame")
    app.processEvents()
    m = w.model
    m.add_feder_prop("FT", [1e6] * 6, [1.0, 0.0, 0.0])
    m.add_starrkoerper(0, [1, 2], "RBE3", [1.0, 2.0])
    w.refresh_all()
    app.processEvents()

    def fall(titel, art, name, key, eingabe, lesen, soll):
        fehler.clear()
        mk = w._objektmaske(art, name) or w.maskenrand.maske
        vorher, u0 = lesen(), _undo_n(w)
        mk.setzen(key, eingabe)
        mk.anwenden()
        app.processEvents()
        nachher, u1 = lesen(), _undo_n(w)
        check(f"{titel} „{eingabe}“: abgewiesen, Meldung, Objekt und Rückgängig unverändert",
              nachher == vorher and u1 == u0 and bool(fehler) and all(s in fehler[-1] for s in soll),
              f"{vorher} -> {nachher} | undo {u0}->{u1} | {fehler[-1:]}")

    def versatz():
        return [list(x) for x in (m.elements[0].exzentrizitaet or [])]
    fall("Stab-Versatz", "stabelement", "0", "ex_a", "12,5 1 000", versatz, ("1 000", ";"))
    fall("Stab-Versatz", "stabelement", "0", "ex_a", "1; 2; 3", versatz, ("Versatz", "2", "3"))
    fall("Stab-Versatz", "stabelement", "0", "ex_a", "5", versatz, ("Versatz", "2", "1"))
    kn = ", ".join(str(n) for n in m.elements[0].nodes)
    fall("Stab-Knoten", "stabelement", "0", "kn", kn + ", x", versatz, ("Knoten", "x"))
    fehler.clear()
    mk = w._objektmaske("stabelement", "0") or w.maskenrand.maske
    mk.setzen("ex_a", "12,5; 1 000")
    mk.anwenden()
    app.processEvents()
    ex = m.elements[0].exzentrizitaet or []
    check("Stab-Versatz „12,5; 1 000“ = y 12,5 mm, z 1 000 mm (nicht still z = 1 mm)",
          bool(ex) and abs(ex[0][1] - 0.0125) < 1e-12 and abs(ex[0][2] - 1.0) < 1e-12 and not fehler,
          f"{ex} {fehler[-1:]}")

    def achse():
        return list(m.federn["FT"].achse)
    fall("Feder Ersatzachse", "feder", "FT", "achse", "1, 0, 0, 5", achse, ("Ersatzachse", "3", "4"))
    fall("Feder Ersatzachse", "feder", "FT", "achse", "1.000, 0, 0", achse, ("1.000",))

    def gewichte():
        return list(m.starrkoerper[-1].gewichte or [])
    i_sk = str(len(m.starrkoerper) - 1)
    fall("RBE3 Gewichte", "starrkoerper", i_sk, "gewichte", "1 000, 2", gewichte, ("1 000", ";"))
    fall("RBE3 Gewichte", "starrkoerper", i_sk, "gewichte", "1; 2; 3", gewichte, ("Gewichte", "2", "3"))
    fehler.clear()
    mk = w._objektmaske("starrkoerper", i_sk) or w.maskenrand.maske
    mk.setzen("gewichte", "1 000; 2")
    mk.anwenden()
    app.processEvents()
    check("RBE3 Gewichte „1 000; 2“ = [1000, 2]", gewichte() == [1000.0, 2.0] and not fehler,
          f"{gewichte()} {fehler[-1:]}")

    lf = next(iter(m.load_cases))

    def lastfall():
        lc = m.load_cases[lf]
        return (lc.psi, lc.category, lc.description)
    fall("Lastfall ψ", "lastfall", lf, "psi", "0,7/0,5", lastfall, ("ψ", "3", "2"))
    fall("Lastfall ψ", "lastfall", lf, "psi", "1.000/0,5/0,3", lastfall, ("1.000",))

    t = meldung(lambda: w._zahlenliste("4, 4, 4", anzahl=(1, 2), feld="Teilung"))
    check("Teilung einer Fläche „4, 4, 4“: Meldung (1 oder 2 Werte), nicht still gekürzt",
          "Teilung" in t and "3" in t, t)
    try:
        ok = w._zahlenliste("4 × 5", anzahl=(1, 2)) == [4, 5] and w._zahlenliste("4", anzahl=(1, 2)) == [4]
    except (ValueError, TypeError):
        ok = False
    check("… „4 × 5“ und „4“ gelesen", ok)
    w.error = alt_error


def test_anzeige_nie_wissenschaftlich():
    """Hinweise und Masken zeigen Zahlen ausgeschrieben (Anwender 12.09.2026:
    „2e+06“ ist unlesbar). Bis 25.09.2026 zeigte der Bettungshinweis
    „3.3e+06 kN/m“."""
    import re
    w, app = _fenster()
    w.load_example("frame")
    app.processEvents()
    mk = w._objektmaske("lager_einzeln", "0")
    mk.setzen("beton", "auf Beton (Druckkontakt)")
    mk._felder["E_cm"].setText("33 000")
    mk.zusatzknoepfe["Bettung übernehmen"].click()
    app.processEvents()
    text = mk.lbl_hinweis.text()
    check("Bettungshinweis: „330 000 MN/m³“ und „3 300 000 kN/m“, kein e+",
          "330 000 MN/m³" in text and "3 300 000 kN/m" in text and not re.search(r"\de[+-]", text), text[:120])
    status = w.statusBar().currentMessage()
    check("… Statusleiste ebenso", "3 300 000" in status and not re.search(r"\de[+-]", status), status[:120])

    # Lager-Wirkung in der Tabelle: Feder 3,3e9 N/m
    from statik3d.model import DofBehaviour
    s = w.model.supports[0]
    s.behaviour = {2: DofBehaviour("spring", 3.3e9, "", 0.0, 0.0, None)}
    try:
        texte = " ".join(w._wirkung(s))
    except Exception as ex:              # noqa: BLE001
        texte = f"Ausnahme {ex!r}"
    check("Lager-Wirkung mit Feder 3,3e9 N/m ohne e+", "Ausnahme" not in texte
          and not re.search(r"\de[+-]", texte), texte[:120])

    # Modellbaum (Gegenpruefung 25.09.2026: „2.5e+06 kg“ an einer Punktmasse)
    from PySide6 import QtWidgets
    w.model.add_punktmasse(0, 2.5e6, [4e6, 4e6, 1.2e7], name="Verschluss")
    w.refresh_all()
    app.processEvents()
    baum, gefunden = [], False
    for b in w.findChildren(QtWidgets.QTreeWidget):
        it = QtWidgets.QTreeWidgetItemIterator(b)
        while it.value():
            x = it.value()
            for c in range(x.columnCount()):
                for t in (x.text(c), x.toolTip(c)):
                    gefunden = gefunden or "2 500 000 kg" in t
                    if re.search(r"\de[+-]\d", t):
                        baum.append(t[:80])
            it += 1
    check("Modellbaum: Punktmasse „2 500 000 kg“, nirgends e+/e-", gefunden and not baum, str(baum[:3]))

    # Quelltext: keine Formate mit Exponent oder ohne Stellen-Garantie in
    # Texten der Oberflaeche - weder :.3g (3300 -> „3.3e+03“) noch einfaches
    # :g (2 500 000 -> „2.5e+06“, seit 25.09.2026 mitgesucht) noch :e
    gui = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statik3d", "gui")
    muster = re.compile(r"\{[^{}]*:[<>^=]?[+ -]?\d*(\.\d+)?[gGeE]\}|[\"']%[\d.]*[gGeE][\"']")
    # Ausnahmen, je mit Grund - kein Anzeigetext, oder ein Text, der wieder
    # gelesen oder als Schluessel benutzt wird:
    erlaubt = (
        # Rundung fuer ein Zahlenfeld: ein Wert, kein Text
        'float(f"',
        # CSV-Ausgabe der Ergebnisse (Datei fuer andere Programme)
        ';".join(f"{v:.6e}"',
        # Kombinationsformel im Textfeld der Maske - wird beim Übernehmen
        # wieder als Formel gelesen (Faktoren wie 1.35)
        'f"{k}: {v:g}" for k, v in (c.factors',
        # Kerbfall-Wahl der Schwingungsmaske: der Wahltext wird mit der
        # Liste verglichen und als Zahl wieder gelesen (zl.feldwert)
        'f"{k:g}" for k in DETAIL_CATEGORIES', 'f"{sn.kerbfall:g}"',
        # Name der Dicke („t = 12 mm“) ist ihr Schluessel im Modell; der
        # Rückgängig-Text nennt denselben Namen
        'ShellProp(f"t = {t*1000:g} mm"', 'self.merken(f"Dicke t = {t * 1000:g} mm")',
        # Name eines Parameterprofils („R 200x100“) ist sein Schluessel
        'masse = "x".join(f"{x:g}" for x in v)',
        # Vorgabe der Farbskala; jede Skala setzt ihr Format selbst
        # (spannungen.skalenformat, Klassen %.0f, Elementwerte %.2f)
        '"label_font_size": 11, "fmt": "%.3g"',
    )
    treffer = []
    for dat in sorted(os.listdir(gui)):
        if not dat.endswith(".py"):
            continue
        with open(os.path.join(gui, dat), encoding="utf-8") as fh:
            for nr, zeile in enumerate(fh, 1):
                if zeile.lstrip().startswith("#") or not muster.search(zeile):
                    continue
                if any(x in zeile for x in erlaubt):
                    continue
                treffer.append(f"{dat}:{nr}")
    check("Oberfläche: keine :g/:.3g/:e-Formate in Anzeigetexten (Ausnahmen begründet)",
          not treffer, f"{len(treffer)}: " + ", ".join(treffer[:12]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_regel, test_eine_quelle, test_maske, test_geaenderte_felder, test_dialog,
              test_programmwerte, test_tippen, test_tabellenzelle, test_register_einheiten,
              test_ergebnisse_behalten, test_nachbesserung, test_bemerkung_mit_vernetzen,
              test_verlassen_mit_tab, test_textfelder_zahlenregel, test_listen_anzahl,
              test_anzeige_nie_wissenschaftlich):
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
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
