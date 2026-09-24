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
    d.deleteLater()


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


def test_register_einheiten():
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
    w.sel[0].setText("6"); w.sel[1].setText("6"); w.do_select()

    n0 = len(lc.nodal_loads)
    w.ld[2].setText("2.000.000")
    app.processEvents()
    w.add_load()
    check("„2.000.000“ im Register: keine Last (bis 24.09.: still eine Last 0)",
          len(lc.nodal_loads) == n0, f"{len(lc.nodal_loads) - n0} Lasten dazu")
    from PySide6 import QtWidgets
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


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_regel, test_eine_quelle, test_maske, test_geaenderte_felder, test_dialog,
              test_tabellenzelle, test_register_einheiten, test_ergebnisse_behalten,
              test_bemerkung_mit_vernetzen):
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
